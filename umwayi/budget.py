"""Budget governor, tasks B.3 to B.5 and B.8: the ledger in the logbook, limits, change entries, status, calibrate.

The ledger is read from chained logbook entries with source `umwayi budget` only (approved answer B-Q1); there is
no second ledger file. Three fixed shapes, each one Added line:

    reserve  Reserved run R for agent A (P): 1000000 micros (100 UU)
    settle   Settled run R for agent A (P): measured 123456 micros (13 UU); models m1, m2; tokens input I,
             output O, cache_read CR, cache_creation CC; requests N; released 876544 micros
    change   units.yaml changed (sha256 HEX): limits.per_day 500 to 600; models.m.input none to 3000000
             (2026-11-09, owner)

Anything else with that source is a ledger problem: every start and `budget status` are refused (exit 2), like a
broken chain. A reservation without a settle counts in full (B-Q4) until `umwayi budget settle-lost --by NAME`.
A day is the logbook date of the reservation; a run that passes midnight counts on the day it was reserved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from umwayi import logbook, runlock, units
from umwayi.errors import ConfigError, UmwayiError, UsageError

SOURCE = "umwayi budget"
MIN_RUNS, MIN_DAYS = 20, 7  # B.R1.8: calibration needs at least 20 measured runs over at least 7 days
DAY_LIMITS = ("per_day", "per_agent_per_day", "per_platform_per_day")

_N = r"(0|[1-9][0-9]{0,15})"
_WORD = r"([a-z][a-z0-9-]{0,31})"
_RUN = r"([0-9a-f]{16})"
_MODEL = r"[A-Za-z0-9._:/-]{1,64}"
_RESERVE = re.compile(rf"^Reserved run {_RUN} for agent {_WORD} \({_WORD}\): {_N} micros \({_N} UU\)$")
_SETTLE = re.compile(
    rf"^Settled run {_RUN} for agent {_WORD} \({_WORD}\): (measured|declared|unknown) {_N} micros \({_N} UU\); "
    rf"models (none|{_MODEL}(?:, {_MODEL}){{0,9}}); tokens input {_N}, output {_N}, cache_read {_N}, "
    rf"cache_creation {_N}; requests {_N}; released {_N} micros$")
_CHANGE = re.compile(r"^units\.yaml changed \((sha256 [0-9a-f]{64}|removed)\): (.+)$")
_VAL = r"(none|[a-z_]{1,20}|[0-9]{1,13}(?: \([0-9]{4}-[0-9]{2}-[0-9]{2}, [^\s;,()]{1,210}\))?)"
_ITEM = re.compile(rf"^([A-Za-z0-9._:/-]{{1,200}}) {_VAL} to {_VAL}$")
NO_CHANGE = "no rate or limit changed"


class LedgerError(UmwayiError):
    """A `umwayi budget` entry that is not one of the fixed shapes. Never quotes the entry."""


@dataclass(frozen=True)
class Reserve:
    run: str
    agent: str
    platform: str
    micros: int
    date: str


@dataclass(frozen=True)
class Settle:
    run: str
    agent: str
    platform: str
    tag: str
    micros: int
    models: tuple
    tokens: tuple  # input, output, cache_read, cache_creation
    requests: int
    released: int


@dataclass
class Ledger:
    reserves: dict = field(default_factory=dict)  # run -> Reserve, oldest first
    settles: dict = field(default_factory=dict)  # run -> Settle
    units_state: dict = field(default_factory=dict)  # the rates and limits of the newest change entry
    units_hash: str | None = None  # "sha256 HEX", "removed", or None when no change was ever logged

    def open_runs(self) -> list:
        return [r for run, r in self.reserves.items() if run not in self.settles]


def _bad(number: int, what: str) -> LedgerError:
    return LedgerError(f"budget: logbook entry {number} (source {SOURCE}) is not {what}. Every agent start is "
                       "refused until the logbook is restored from a copy you trust (for example git).")


def parse_ledger(entries: list) -> Ledger:
    """The ledger of the logbook entries (oldest first). A malformed budget entry is a LedgerError."""
    led = Ledger()
    for number, e in enumerate(entries, 1):
        if e.source != SOURCE:
            continue
        m = _RESERVE.match(e.added)
        if m:
            run, agent, platform, micros, shown = m.group(1), m.group(2), m.group(3), int(m.group(4)), int(m.group(5))
            if shown != units.uu(micros) or run in led.reserves:
                raise _bad(number, "a reservation with a new run id and its UU")
            led.reserves[run] = Reserve(run, agent, platform, micros, e.date)
            continue
        m = _SETTLE.match(e.added)
        if m:
            g = m.groups()
            run, agent, platform, tag = g[0], g[1], g[2], g[3]
            micros, shown = int(g[4]), int(g[5])
            r = led.reserves.get(run)
            if (r is None or run in led.settles or r.agent != agent or r.platform != platform
                    or shown != units.uu(micros) or int(g[12]) != max(0, r.micros - micros)):
                raise _bad(number, "the one settle of an earlier reservation")
            models = () if g[6] == "none" else tuple(g[6].split(", "))
            led.settles[run] = Settle(run, agent, platform, tag, micros, models,
                                      tuple(int(x) for x in g[7:11]), int(g[11]), int(g[12]))
            continue
        m = _CHANGE.match(e.added)
        if m:
            state = dict(led.units_state)
            if m.group(2) != NO_CHANGE:
                for item in m.group(2).split("; "):
                    im = _ITEM.match(item)
                    if not im:
                        raise _bad(number, "a units.yaml change entry")
                    key, old, new = im.groups()
                    if state.get(key, "none") != old:
                        raise _bad(number, "a units.yaml change entry that follows the one before it")
                    if new == "none":
                        state.pop(key, None)
                    else:
                        state[key] = new
            led.units_state = state
            led.units_hash = m.group(1)
            continue
        raise _bad(number, "one of the fixed budget shapes")
    return led


def read_ledger(root: Path) -> Ledger:
    """From an intact logbook only (read_checked refuses a broken chain or a hand edit)."""
    return parse_ledger(logbook.read_checked(root))


# ------------------------------------------------------------ change entries (B.5)


def pending_change(u: units.Units, led: Ledger) -> str | None:
    """The Added text of the change entry the current units.yaml needs, or None when it was logged already."""
    now = f"sha256 {u.sha256}" if u.present else "removed"
    if now == (led.units_hash or "removed"):
        return None
    new, old = u.state(), led.units_state
    items = [f"{k} {old.get(k, 'none')} to {new.get(k, 'none')}" for k in sorted(set(old) | set(new))
             if old.get(k) != new.get(k)]
    return f"units.yaml changed ({now}): " + ("; ".join(items) if items else NO_CHANGE)


def change_entry(when: str, added: str) -> logbook.Entry:
    return logbook.Entry(when, SOURCE, added, "units.yaml was read and validated before the reservation; this entry "
                         "is written before the new values are first used",
                         "Only names and numbers are logged. Nothing was started by this entry.")


# ------------------------------------------------------------ totals and limits (B.4)


@dataclass
class Day:
    used: int = 0
    reserved: int = 0
    by_agent: dict = field(default_factory=dict)  # name -> [used, reserved]
    by_platform: dict = field(default_factory=dict)
    by_tag: dict = field(default_factory=lambda: {t: 0 for t in units.TAGS})

    def _add(self, d: dict, key: str, i: int, micros: int) -> None:
        d.setdefault(key, [0, 0])[i] += micros


def day_totals(led: Ledger, day: str) -> Day:
    out = Day()
    for run, r in led.reserves.items():
        if r.date != day:
            continue
        s = led.settles.get(run)
        if s is None:  # open: counted in full (B-Q4)
            out.reserved += r.micros
            out._add(out.by_agent, r.agent, 1, r.micros)
            out._add(out.by_platform, r.platform, 1, r.micros)
        else:
            out.used += s.micros
            out.by_tag[s.tag] += s.micros
            out._add(out.by_agent, r.agent, 0, s.micros)
            out._add(out.by_platform, r.platform, 0, s.micros)
    return out


@dataclass(frozen=True)
class Fit:
    ok: bool
    need: int  # micros, the per-run cap
    left: dict  # limit name -> micros left before this reservation
    limit: str | None = None  # the first limit that does not fit

    def left_uu(self, name: str) -> int:
        return max(0, self.left[name]) // units.MICROS_PER_UU

    def left_today_uu(self) -> int:
        return min(self.left_uu(n) for n in DAY_LIMITS)


def fit(led: Ledger, u: units.Units, agent: str, platform: str, day: str) -> Fit:
    """Does a reservation of per_run fit per_day, per_agent_per_day and per_platform_per_day? (B.R1.6)"""
    t = day_totals(led, day)
    need = units.limit_micros(u.limits["per_run"])
    a = t.by_agent.get(agent, [0, 0])
    p = t.by_platform.get(platform, [0, 0])
    left = {"per_day": units.limit_micros(u.limits["per_day"]) - t.used - t.reserved,
            "per_agent_per_day": units.limit_micros(u.limits["per_agent_per_day"]) - sum(a),
            "per_platform_per_day": units.limit_micros(u.limits["per_platform_per_day"]) - sum(p)}
    for name in DAY_LIMITS:
        if need > left[name]:
            return Fit(False, need, left, name)
    return Fit(True, need, left)


def refused_text(agent: str, f: Fit) -> str:
    return (f"Refused agent {agent}: the budget limit {f.limit} has {f.left_uu(f.limit)} UU left, a run needs "
            f"{units.uu(f.need)} UU")


def reserve_text(run: str, agent: str, platform: str, micros: int) -> str:
    return f"Reserved run {run} for agent {agent} ({platform}): {micros} micros ({units.uu(micros)} UU)"


def settle_text(run: str, agent: str, platform: str, reserved: int, reading: units.Reading, report: dict | None) -> str:
    report = report or {}
    models = ", ".join(report.get("models") or []) or "none"
    by_type = report.get("by_type") or {}
    tok = ", ".join(f"{t} {by_type.get(t, 0)}" for t in units.TOKEN_TYPES)
    return (f"Settled run {run} for agent {agent} ({platform}): {reading.tag} {reading.micros} micros "
            f"({units.uu(reading.micros)} UU); models {models}; tokens {tok}; requests {report.get('requests', 0)}; "
            f"released {max(0, reserved - reading.micros)} micros")


def settle_checked(u: units.Units, reading: units.Reading, report: dict | None) -> str:
    sha = u.sha256 if u.present else "none (no units.yaml)"
    if report is None:
        got = "no telemetry receiver for this platform"
    else:
        refused = report.get("refused") or {}
        got = (f"reports accepted {report.get('accepted', 0)}, refused {sum(refused.values())}"
               + (" (" + ", ".join(f"{n} answered {c}" for c, n in sorted(refused.items())) + ")" if refused else ""))
    return f"units.yaml sha256 {sha}; reading: {reading.why}; {got}"


SETTLE_NOT_DONE = "No prompt, response or other telemetry content was kept or logged."


def entry(when: str, added: str, checked: str, not_done: str) -> logbook.Entry:
    return logbook.Entry(when, SOURCE, added, checked, not_done)


# ------------------------------------------------------------ status (B.8)


def _pct(part: int, whole: int) -> int:
    return (200 * part + whole) // (2 * whole) if whole else 0


def status(root: Path, day: str, today: str) -> tuple:
    """(code, lines) for `umwayi budget status`. Reads only: starts nothing and writes nothing."""
    try:
        u = units.load(root, today)
    except ConfigError as e:
        return 64, [str(e)]
    try:
        led = read_ledger(root)
    except UmwayiError as e:
        return 2, [str(e), "Nothing was started or written."]
    t = day_totals(led, day)
    lim = u.limits

    def line(label: str, used: int, reserved: int, limit_uu: int) -> str:
        left = max(0, units.limit_micros(limit_uu) - used - reserved)
        return (f"{label}: used {units.uu(used)} UU, reserved {units.uu(reserved)} UU, left "
                f"{left // units.MICROS_PER_UU} UU (limit {limit_uu} UU)")

    lines = [f"Budget for {day} (1 UU is one US cent of estimated list price; a subscription is not billed by it)",
             line("per_day", t.used, t.reserved, lim["per_day"])]
    for name, (used, res) in sorted(t.by_agent.items()):
        lines.append(line(f"per_agent_per_day {name}", used, res, lim["per_agent_per_day"]))
    for name, (used, res) in sorted(t.by_platform.items()):
        lines.append(line(f"per_platform_per_day {name}", used, res, lim["per_platform_per_day"]))
    lines.append(f"per_run: {lim['per_run']} UU reserved for every start; unknown_worst_case: "
                 f"{lim['unknown_worst_case']} UU")
    if t.used:
        lines.append(f"Of used: measured {_pct(t.by_tag['measured'], t.used)}%, declared "
                     f"{_pct(t.by_tag['declared'], t.used)}%, unknown {_pct(t.by_tag['unknown'], t.used)}%")
    else:
        lines.append("Of used: nothing was used on this day")
    lost = [r for r in led.open_runs() if r.date == day]
    if lost:
        lines.append(f"{len(lost)} reservation(s) of this day have no settle and count in full; if no agent runs now, "
                     "run umwayi budget settle-lost --by NAME")
    if pending_change(u, led) is not None:
        lines.append("units.yaml changed since the last logged change; the change is logged before the next start")
    if not u.present:
        lines.append("There is no units.yaml: every reading is unknown and the limits are the placeholders.")
    lines.append("Nothing was started or written.")
    return 0, lines


# ------------------------------------------------------------ calibrate (B.5, B-Q3)


def calibrate(root: Path, today: str) -> tuple:
    """(code, lines) for `umwayi budget calibrate`. Only proposes; the owner edits units.yaml (B-Q3)."""
    try:
        u = units.load(root, today)
    except ConfigError as e:
        return 64, [str(e)]
    try:
        led = read_ledger(root)
    except UmwayiError as e:
        return 2, [str(e), "Nothing was changed."]
    runs, days = [], {}
    for run, s in led.settles.items():
        if s.tag != units.MEASURED:
            continue
        runs.append(s.micros)
        d = led.reserves[run].date
        days[d] = days.get(d, 0) + s.micros
    if len(runs) < MIN_RUNS or len(days) < MIN_DAYS:
        return 0, [f"Not enough data: {len(runs)} measured run(s) over {len(days)} day(s). Calibration needs at least "
                   f"{MIN_RUNS} measured runs over at least {MIN_DAYS} days ({max(0, MIN_RUNS - len(runs))} more "
                   f"run(s), {max(0, MIN_DAYS - len(days))} more day(s)). Nothing was changed."]
    runs.sort()
    k = -(-95 * len(runs) // 100)  # nearest rank
    p95 = runs[k - 1]
    totals = sorted(days.values())
    m = len(totals)
    twice_median = 2 * totals[m // 2] if m % 2 else totals[m // 2 - 1] + totals[m // 2]
    median = f"{twice_median // 2}" + (".5" if twice_median % 2 else "")
    per_run = -(-(3 * p95) // (2 * units.MICROS_PER_UU))
    per_day = -(-twice_median // units.MICROS_PER_UU)
    return 0, [
        f"Data: {len(runs)} measured run(s) over {len(days)} day(s) (the newest {max(days)}, the oldest {min(days)}).",
        f"95th percentile of one measured run (nearest rank {k} of {len(runs)}): {p95} micros ({units.uu(p95)} UU).",
        f"Median measured day: {median} micros (of {m} day totals).",
        f"Proposed limits.per_run: {per_run} UU (1.5 times the 95th percentile, rounded up; now {u.limits['per_run']} UU).",
        f"Proposed limits.per_day: {per_day} UU (2 times the median day, rounded up; now {u.limits['per_day']} UU).",
        "Nothing was changed. To apply, edit units.yaml yourself; the change is logged before it is first used.",
    ]


# ------------------------------------------------------------ settle-lost (B-Q4)


def settle_lost(root: Path, when: str, by: str) -> tuple:
    """(code, lines): settle every reservation without a settle, as unknown at the worst case (never zero)."""
    if not isinstance(by, str) or not by.strip() or len(by) > logbook.MAX_BY or not by.isprintable():
        raise UsageError(f"budget: --by must be a name of 1 to {logbook.MAX_BY} printable characters")
    by = by.strip()
    u = units.load(root, when)
    try:
        with runlock.held(root):
            led = read_ledger(root)
            lost = led.open_runs()
            if not lost:
                return 0, ["No reservation is without a settle. Nothing was written."]
            worst = units.limit_micros(u.limits["unknown_worst_case"])
            reading = units.Reading(units.UNKNOWN, worst, f"the run ended without a settle (umwayi was stopped by "
                                    f"SIGKILL or a crash); settled by {by} with umwayi budget settle-lost")
            lines = []
            for r in lost:
                try:
                    logbook.append(root, entry(when, settle_text(r.run, r.agent, r.platform, r.micros, reading, None),
                                               settle_checked(u, reading, None), SETTLE_NOT_DONE))
                except UmwayiError as e:
                    return 2, lines + [f"The logbook could not be written ({str(e).rstrip('. ')}). Run {r.run} "
                                       "still counts in full."]
                lines.append(f"Settled lost run {r.run} of agent {r.agent} ({r.date}): unknown {units.uu(worst)} UU.")
            return 0, lines + [f"{len(lost)} lost reservation(s) settled."]
    except runlock.RunLockBusy:
        return 3, ["Ask me first", "Reason: an agent or another umwayi run holds the run lock, so a reservation may "
                   "still be in use. Nothing was written."]
    except runlock.RunLockUnavailable as e:
        return 2, [f"The run lock could not be taken ({runlock.unavailable_reason(e)}). Nothing was written."]
