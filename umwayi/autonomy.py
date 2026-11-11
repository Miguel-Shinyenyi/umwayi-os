"""Layer 13, slice 5: graded autonomy (13.R9 to 13.R12, design.md "Slice 5: Graded autonomy").

A score per action class, from the owner's own record, that can move an Ask me first to Yes, and nothing else:

  * Off by default. With no `autonomy.yaml`, or `enabled: false`, `consider` returns the decision unchanged, so the
    answer, the JSON and the check's own logbook entry are the bytes of before (13.R12).
  * Only an Ask me first that the rules gave, only when every matching Ask rule opts its class in (the `autonomy`
    field of rules.yaml, parsed in rules.py), only in a check that logs. A No and a Yes are never moved.
  * Thirteen gates, in the fixed order of the design; the first that fails leaves Ask me first and its word is
    written in the check's entry. Every move is written with its inputs, and a move that cannot be logged is not
    made: the caller's write turns it back into Ask me first (the layer 2 rule).
  * The inputs are only the chained logbook entries of the sources `umwayi autonomy record` and `umwayi autonomy`,
    each line read with `fullmatch`, and the end of a check entry that has the move shape. One entry out of shape,
    unchained or a duplicate makes the whole record invalid, and no class moves anywhere (13.R11).
  * The score reads the class word, the outcome word and the date of those entries. It reads no queue row, no
    answer, no reason, no rule title, text or cause, and no other logbook line (13.R9.7).
  * `autonomy.yaml` is logged before it is first used (13.R7.5). It can be logged only once the hash chain has
    started; until then graded autonomy cannot move anything anyway.

Standard library only, no network. This module writes the logbook only through `logbook.append_with`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date as _date, timedelta
from math import floor, sqrt
from pathlib import Path

from umwayi import kill, logbook, miniyaml, rules
from umwayi.errors import UmwayiError, UsageError
from umwayi.fsutil import NotRegular, TooBig, read_regular

SETTINGS_NAME = "autonomy.yaml"
MAX_SETTINGS_BYTES = 64 * 1024
RECORD_SOURCE = "umwayi autonomy record"
SETTINGS_SOURCE = "umwayi autonomy"
CHECK_SOURCE = "umwayi check"
OUTCOMES = ("approved", "edited", "rejected", "reverted")
MAX_BY = 40

# every setting is required (L13-Q5): name and allowed range, or None for true and false
KEYS = (
    ("version", (1, 1)),
    ("enabled", None),
    ("window_days", (1, 3650)),
    ("min_decisions", (1, 1000000)),
    ("min_lower_bound", (1, 1000)),
    ("confidence_z", (100, 400)),
    ("revert_weight", (1, 100)),
    ("max_cost_uu", (0, 1000000)),
    ("cooldown_days", (1, 3650)),
    ("max_moves_per_day", (1, 1000)),
)

# the gate words (design.md, "The gates, in order")
AUTONOMY_OFF, SETTINGS_INVALID, NO_LOG, KILL_SWITCH, CHAIN, INPUTS_INVALID = (
    "autonomy-off", "settings-invalid", "no-log", "kill-switch", "chain", "inputs-invalid")
NOT_OPTED_IN, ELECTION_LAPSED, CLASS_MISMATCH, OPT_IN_LAPSED = (
    "not-opted-in", "election-lapsed", "class-mismatch", "opt-in-lapsed")
IRREVERSIBLE, COST, COOLDOWN, LOW_DATA, LOW_SCORE, DAILY_CAP = (
    "irreversible", "cost", "cooldown", "low-data", "low-score", "daily-cap")

# the fixed shapes (design.md, "Data shapes")
RECORD_CHECKED = ("the hash chain was intact before this entry; the class and the outcome were checked against the "
                  "allowed words")
RECORD_NOT_DONE = "Nothing was moved or changed by this entry. The score is computed when a check runs, not here."
SETTINGS_CHECKED = ("autonomy.yaml was read and validated before this entry; this entry is written before the new "
                    "values are first used; settings: ")
REMOVED_CHECKED = "autonomy.yaml is no longer in the root; graded autonomy is off from the next check on"
SETTINGS_NOT_DONE = "Only the setting names and numbers are logged. Nothing was moved by this entry."
REMOVED = "autonomy.yaml removed"

_CLASS = re.compile(r"[a-z][a-z0-9_-]{0,39}")
_REF = re.compile(r"Q-\d{4,}")
_RECORD = re.compile(r"outcome (approved|edited|rejected|reverted) for class ([a-z][a-z0-9_-]{0,39}) recorded by "
                     r"([^;|]{1,40})(?:; ref (Q-\d{4,}))?")
_VALUE = r"(?:\d{1,7}|true|false)"
_SETTING = rf"[a-z_]{{1,20}} {_VALUE}"
_SET_FIRST = re.compile(r"autonomy\.yaml first logged \(sha256 ([0-9a-f]{64})\)")
_SET_CHANGED = re.compile(rf"autonomy\.yaml changed \(sha256 ([0-9a-f]{{64}})\): (?:no setting changed|"
                          rf"[a-z_]{{1,20}} {_VALUE} to {_VALUE}(?:; [a-z_]{{1,20}} {_VALUE} to {_VALUE})*)")
_SET_CHECKED = re.compile(re.escape(SETTINGS_CHECKED) + rf"({_SETTING}(?:, {_SETTING})*)")
_MOVE_ADDED = re.compile(r"Rule [a-z0-9][a-z0-9_-]* gave Ask me first and autonomy moved it to Yes; action type: "
                         r"[A-Za-z0-9_.:-]{1,40}")
_MOVE_TAIL = re.compile(r"; autonomy: moved to Yes; class ([a-z][a-z0-9_-]{0,39}); approved \d+; edited \d+; "
                        r"rejected \d+; reverted \d+; weight \d+; n \d+; score \d+ per mille; needs n \d+ and score "
                        r"\d+; reversible yes; cost \d+ of \d+ UU; moves today \d+ of \d+\Z")


# ------------------------------------------------------------------ the score


def wilson_steps(a: int, e: int, r: int, v: int, revert_weight: int, confidence_z: int) -> dict:
    """The lower end of the Wilson score interval, step by step, in the one fixed order of the design."""
    s = a
    f = e + r + revert_weight * v
    n = s + f
    z = confidence_z / 100
    if n == 0:
        return dict(s=s, f=f, n=n, p=0.0, centre=0.0, spread=0.0, bound=0.0)
    p = s / n
    centre = p + z * z / (2 * n)
    spread = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    bound = (centre - spread) / (1 + z * z / n)
    return dict(s=s, f=f, n=n, p=p, centre=centre, spread=spread, bound=bound)


def wilson(a: int, e: int, r: int, v: int, revert_weight: int, confidence_z: int) -> int:
    """The score in per mille, rounded down and kept between 0 and 1000 (13.R10.2). No record scores 0."""
    steps = wilson_steps(a, e, r, v, revert_weight, confidence_z)
    if steps["n"] == 0:
        return 0
    return max(0, min(1000, floor(steps["bound"] * 1000)))


# ------------------------------------------------------------------ autonomy.yaml


@dataclass(frozen=True)
class Settings:
    values: tuple  # ((name, value), ...) in the order of KEYS

    def __getattr__(self, name):
        for k, v in self.values:
            if k == name:
                return v
        raise AttributeError(name)


def parse_settings(text: str) -> tuple:
    """(Settings or None, problems): every problem as (line number or None, message). Never the text of a line."""
    try:
        data = miniyaml.loads(text)
    except miniyaml.YamlError as e:
        msg = str(e)
        m = re.match(r"line (\d+): (.*)", msg)
        return None, [(int(m.group(1)), m.group(2))] if m else [(None, msg)]
    if not isinstance(data, dict):
        return None, [(None, "the file must be a mapping of settings")]
    lines = {}
    for n, line in enumerate(text.split("\n"), 1):
        m = re.match(r"^([A-Za-z0-9_]+)\s*:", line)
        if m and m.group(1) not in lines:
            lines[m.group(1)] = n
    problems = []
    known = dict(KEYS)
    for key in data:
        if key not in known:
            problems.append((lines.get(key), f"{key} is not a setting"))
    values = []
    for key, rng in KEYS:
        if key not in data:
            problems.append((None, f"{key} is missing"))
            continue
        v = data[key]
        if rng is None:
            if not isinstance(v, bool):
                problems.append((lines.get(key), f"{key} must be true or false"))
                continue
        elif isinstance(v, bool) or not isinstance(v, int) or not rng[0] <= v <= rng[1]:
            problems.append((lines.get(key), f"{key} must be 1" if key == "version" else
                             f"{key} must be a whole number from {rng[0]} to {rng[1]}"))
            continue
        values.append((key, v))
    problems.sort(key=lambda p: (p[0] is None, p[0] or 0))
    return (None if problems else Settings(tuple(values))), problems


def read_settings(root: Path) -> tuple:
    """("absent" | "invalid" | "valid", Settings or None, SHA-256 or None, problems)."""
    path = Path(root) / SETTINGS_NAME
    if not path.exists() and not path.is_symlink():
        return "absent", None, None, []
    try:
        data = read_regular(path, MAX_SETTINGS_BYTES)
        text = data.decode("utf-8")
    except TooBig:
        return "invalid", None, None, [(None, f"larger than {MAX_SETTINGS_BYTES} bytes")]
    except NotRegular:
        return "invalid", None, None, [(None, "not a regular file")]
    except OSError:
        return "invalid", None, None, [(None, "cannot be read")]
    except UnicodeDecodeError:
        return "invalid", None, None, [(None, "not valid UTF-8")]
    settings, problems = parse_settings(text)
    if settings is None:
        return "invalid", None, None, problems
    return "valid", settings, logbook.sha256_hex(data), []


def _word(v) -> str:
    return ("true" if v else "false") if isinstance(v, bool) else str(v)


def _settings_state(entry) -> tuple | None:
    """(sha256 or None for removed, ((name, word), ...) or None) of a settings entry in a fixed shape, else None."""
    if entry.source != SETTINGS_SOURCE or entry.not_done != SETTINGS_NOT_DONE:
        return None
    if entry.added == REMOVED and entry.checked == REMOVED_CHECKED:
        return (None, None)
    m = _SET_FIRST.fullmatch(entry.added) or _SET_CHANGED.fullmatch(entry.added)
    c = _SET_CHECKED.fullmatch(entry.checked)
    if not m or not c:
        return None
    state = tuple(tuple(item.split(" ", 1)) for item in c.group(1).split(", "))
    return (m.group(1), state)


def _newest_settings(entries: list):
    for e in reversed(entries):
        found = _settings_state(e)
        if found is not None:
            return found
    return None


def log_settings(root: Path, when: str, settings: Settings | None, digest: str | None) -> None:
    """Log autonomy.yaml (or its removal) before it is used, once per change, decided under the logbook lock."""
    def build(entries):
        last = _newest_settings(entries)
        if settings is None:  # removed
            if last is None or last[0] is None:
                return None
            return logbook.Entry(when, SETTINGS_SOURCE, REMOVED, REMOVED_CHECKED, SETTINGS_NOT_DONE)
        if last is not None and last[0] == digest:
            return None
        state = tuple((k, _word(v)) for k, v in settings.values)
        checked = SETTINGS_CHECKED + ", ".join(f"{k} {v}" for k, v in state)
        if last is None or last[1] is None:
            added = f"autonomy.yaml first logged (sha256 {digest})"
        else:
            old = dict(last[1])
            changes = [f"{k} {old[k]} to {v}" for k, v in state if k in old and old[k] != v]
            added = f"autonomy.yaml changed (sha256 {digest}): " + ("; ".join(changes) or "no setting changed")
        return logbook.Entry(when, SETTINGS_SOURCE, added, checked, SETTINGS_NOT_DONE)
    logbook.append_with(Path(root), when, build)


# ------------------------------------------------------------------ the inputs


class _Invalid:
    def __repr__(self):
        return "INVALID"


INVALID = _Invalid()


@dataclass(frozen=True)
class Inputs:
    outcomes: tuple  # (date, class, outcome), oldest first
    moves: tuple  # (date, class) of every logged move


def read_inputs(pairs: list):
    """The owner's record and the moves, from (Entry, Chain value) pairs, or INVALID (13.R9.6, 13.R11)."""
    outcomes, moves, refs = [], [], set()
    for e, chain in pairs:
        if e.source == RECORD_SOURCE:
            m = _RECORD.fullmatch(e.added)
            if (chain is None or not m or m.group(3) != m.group(3).strip() or e.checked != RECORD_CHECKED
                    or e.not_done != RECORD_NOT_DONE):
                return INVALID
            outcome, cls, ref = m.group(1), m.group(2), m.group(4)
            if ref is not None:
                if (ref, outcome) in refs:
                    return INVALID
                refs.add((ref, outcome))
            outcomes.append((e.date, cls, outcome))
        elif e.source == SETTINGS_SOURCE:
            if chain is None or _settings_state(e) is None:
                return INVALID
        elif e.source == CHECK_SOURCE and _MOVE_ADDED.fullmatch(e.added):
            m = _MOVE_TAIL.search(e.checked)
            if chain is None or not m:
                return INVALID
            moves.append((e.date, m.group(1)))
    return Inputs(tuple(outcomes), tuple(moves))


@dataclass(frozen=True)
class Counts:
    a: int
    e: int
    r: int
    v: int
    cooldown_until: str | None
    moves_today: int


def count(inputs: Inputs, cls: str, today: str, day: str, settings: Settings) -> Counts:
    """The four counts over the window that ends today, the end of the cooldown, and the moves logged on `day`."""
    end = _date.fromisoformat(today)
    start = end - timedelta(days=settings.window_days)
    tally = dict.fromkeys(OUTCOMES, 0)
    until = None
    for d, c, outcome in inputs.outcomes:
        if c != cls:
            continue
        when = _date.fromisoformat(d)
        if start < when <= end:
            tally[outcome] += 1
        if outcome in ("rejected", "reverted") and when <= end:
            stop = when + timedelta(days=settings.cooldown_days)
            if stop >= end and (until is None or stop.isoformat() > until):
                until = stop.isoformat()
    moves = sum(1 for d, c in inputs.moves if c == cls and d == day)
    return Counts(tally["approved"], tally["edited"], tally["rejected"], tally["reverted"], until, moves)


# ------------------------------------------------------------------ the move (step 8 of the verdict order)


def _no_move(decision, word: str):
    return replace(decision, autonomy={"moved": False, "gate": word}, autonomy_text=f"; autonomy: no move ({word})")


def consider(root: Path, when: str, decision, rules_path: Path, rules_logged: bool):
    """The thirteen gates for a logged check that gave Ask me first. Returns the decision, moved or not."""
    try:
        loaded = rules.load_rules(rules_path)
    except UmwayiError:
        return decision
    matched = [r for r in loaded if r.id in set(decision.matched)]
    if not any(r.autonomy is not None for r in matched):
        return decision  # no rule opts in: the behaviour of before
    # gate 1: on and valid; the file is logged before it is used, which needs the hash chain
    state, settings, digest, _problems = read_settings(root)
    try:
        pairs = logbook.read_chained(root)
    except UmwayiError:
        pairs = None
    chained = pairs is not None and any(c is not None for _e, c in pairs)
    if state == "absent":
        if chained:
            try:
                log_settings(root, when, None, None)
            except UmwayiError:
                pass
        return decision
    if state == "invalid":
        return _no_move(decision, SETTINGS_INVALID)
    logged = False
    if chained:
        try:
            log_settings(root, when, settings, digest)
            logged = True
        except UmwayiError:
            logged = False
    if settings.enabled is not True:
        return decision
    # gate 2: this is a check that logs (the caller only asks when it logs)
    # gate 3: the kill switch, read on every call
    if kill.state(root) != kill.OFF:
        return _no_move(decision, KILL_SWITCH)
    # gate 4: the record is intact
    if not chained or not logged or not rules_logged or loaded.sha256 != decision.rules_sha256:
        return _no_move(decision, CHAIN)
    try:
        pairs = logbook.read_chained(root)  # again: the settings entry may have been appended
    except UmwayiError:
        return _no_move(decision, CHAIN)
    inputs = read_inputs(pairs)
    if inputs is INVALID:
        return _no_move(decision, INPUTS_INVALID)
    # gate 5: the rules
    if decision.lapsed:
        return _no_move(decision, ELECTION_LAPSED)
    asks = [r for r in matched if r.verdict == rules.ASK]
    if not asks or any(r.autonomy is None for r in asks) or decision.action_type is None:
        return _no_move(decision, NOT_OPTED_IN)
    # gate 6: one class
    if len({r.autonomy.cls for r in asks}) != 1:
        return _no_move(decision, CLASS_MISMATCH)
    opt = asks[0].autonomy
    # gate 7: the opt-in's own review_by, on the election clock
    today = rules.election_clock(root, when)
    if any(r.review_by is not None and r.review_by < today for r in asks):
        return _no_move(decision, OPT_IN_LAPSED)
    # gates 8 and 9: the owner's declarations
    if opt.reversible is not True:
        return _no_move(decision, IRREVERSIBLE)
    if opt.cost_uu > settings.max_cost_uu:
        return _no_move(decision, COST)
    c = count(inputs, opt.cls, today, when, settings)
    # gate 10: cooldown
    if c.cooldown_until is not None:
        return _no_move(decision, COOLDOWN)
    n = c.a + c.e + c.r + settings.revert_weight * c.v
    # gate 11: data
    if n < settings.min_decisions:
        return _no_move(decision, LOW_DATA)
    # gate 12: score
    score = wilson(c.a, c.e, c.r, c.v, settings.revert_weight, settings.confidence_z)
    if score < settings.min_lower_bound:
        return _no_move(decision, LOW_SCORE)
    # gate 13: daily cap
    if c.moves_today >= settings.max_moves_per_day:
        return _no_move(decision, DAILY_CAP)
    text = (f"; autonomy: moved to Yes; class {opt.cls}; approved {c.a}; edited {c.e}; rejected {c.r}; reverted "
            f"{c.v}; weight {settings.revert_weight}; n {n}; score {score} per mille; needs n {settings.min_decisions} "
            f"and score {settings.min_lower_bound}; reversible yes; cost {opt.cost_uu} of {settings.max_cost_uu} UU; "
            f"moves today {c.moves_today + 1} of {settings.max_moves_per_day}")
    why = (f"Rule {decision.rule_id} gave Ask me first, and graded autonomy moved it to Yes: class {opt.cls}, score "
           f"{score} per mille of {n} weighted outcomes, needs {settings.min_lower_bound}.")
    return replace(decision, answer=rules.YES, reason=why,
                   autonomy={"moved": True, "class": opt.cls, "score": score, "gate": None}, autonomy_text=text)


# ------------------------------------------------------------------ umwayi autonomy record


def _check_record_args(cls, outcome, by, ref, when):
    if not isinstance(cls, str) or not _CLASS.fullmatch(cls):
        raise UsageError("autonomy record: --class must be a lowercase letter, then up to 39 lowercase letters, "
                         "digits, _ or -. Nothing was written.")
    if outcome not in OUTCOMES:
        raise UsageError(f"autonomy record: --outcome must be one of {', '.join(OUTCOMES)}. Nothing was written.")
    b = by.strip() if isinstance(by, str) else ""
    if not b or len(b) > MAX_BY or not b.isprintable() or ";" in b or "|" in b:
        raise UsageError(f"autonomy record: --by must be one line of plain text, 1 to {MAX_BY} characters, without "
                         "; or |. Nothing was written.")
    if ref is not None and not _REF.fullmatch(ref):
        raise UsageError("autonomy record: --ref must look like Q-0007. Nothing was written.")
    if not logbook.real_date(when):
        raise UsageError("autonomy record: date must be a real date YYYY-MM-DD. Nothing was written.")
    return b


def record(root: Path, cls: str, outcome: str, by: str, ref: str | None, when: str) -> logbook.Entry:
    """`umwayi autonomy record`: one chained entry of the fixed shape (13.R9.5)."""
    by = _check_record_args(cls, outcome, by, ref, when)
    root = Path(root)
    try:
        pairs = logbook.read_chained(root)
    except UmwayiError as e:
        raise UmwayiError(f"autonomy record: the logbook is not intact ({e}). Nothing was written.") from None
    if not any(c is not None for _e, c in pairs):
        raise UmwayiError("autonomy record: the hash chain has not started, so an outcome cannot be recorded. Start "
                          "it once with 'umwayi logbook seal --chain --by NAME'. Nothing was written.")
    added = f"outcome {outcome} for class {cls} recorded by {by}" + (f"; ref {ref}" if ref else "")
    entry = logbook.Entry(when, RECORD_SOURCE, added, RECORD_CHECKED, RECORD_NOT_DONE)

    def build(entries):
        if ref is not None:
            for e in entries:
                m = _RECORD.fullmatch(e.added) if e.source == RECORD_SOURCE else None
                if m and m.group(4) == ref and m.group(1) == outcome:
                    raise UmwayiError(f"autonomy record: {ref} was already recorded as {outcome}. Nothing was "
                                      "written.")
        return entry
    logbook.append_with(root, when, build)
    return entry


# ------------------------------------------------------------------ umwayi autonomy validate


def validate(root: Path) -> tuple:
    root = Path(root)
    lines = []
    state, settings, _digest, problems = read_settings(root)
    for line, msg in problems:
        lines.append(f"autonomy.yaml line {line}: {msg}" if line else f"autonomy.yaml: {msg}")
    rules_problem = 0
    try:
        rules.load_rules(root / "rules.yaml")
    except UmwayiError as e:
        lines.append(f"rules.yaml: {str(e).removeprefix('rules.yaml: ')}")
        rules_problem = 1
    count_ = len(problems) + rules_problem
    if count_:
        lines.append(f"{count_} problem(s) found. Graded autonomy is off until they are fixed.")
        return 64, lines
    if state == "absent":
        return 0, ["There is no autonomy.yaml: graded autonomy is off."]
    return 0, [f"autonomy.yaml is valid: graded autonomy is {'on' if settings.enabled else 'off'}."]


# ------------------------------------------------------------------ umwayi autonomy status


def status(root: Path, only: str | None, when: str) -> tuple:
    """`umwayi autonomy status`: per class, the counts, the score and the first gate that holds it. Writes nothing."""
    if only is not None and not _CLASS.fullmatch(only):
        raise UsageError("autonomy status: --class must be a lowercase letter, then up to 39 lowercase letters, "
                         "digits, _ or -")
    root = Path(root)
    state, settings, _digest, _problems = read_settings(root)
    try:
        loaded = rules.load_rules(root / "rules.yaml")
    except UmwayiError:
        loaded = []
    declared: dict = {}
    for r in loaded:
        if r.autonomy is not None:
            declared.setdefault(r.autonomy.cls, []).append(r)
    inputs, why_not = None, None
    try:
        pairs = logbook.read_chained(root)
        if not any(c is not None for _e, c in pairs):
            why_not = "the hash chain has not started"
        else:
            inputs = read_inputs(pairs)
            if inputs is INVALID:
                why_not = "invalid"
    except UmwayiError:
        why_not = "the logbook is not intact"
    recorded = sorted({c for _d, c, _o in inputs.outcomes}) if isinstance(inputs, Inputs) else []
    classes = sorted(set(declared) | set(recorded))
    if only is not None:
        classes = [only] if only in classes else []
    switch = kill.state(root)
    today = rules.election_clock(root, when)
    on = state == "valid" and settings.enabled is True
    lines = []
    if only is not None and not classes:
        lines.append(f"class {only}: no rule opts it in and no outcome is recorded")
    for cls in classes:
        rs = declared.get(cls, [])
        if rs:
            opt = rs[0].autonomy
            cost = f"cost {opt.cost_uu} of {settings.max_cost_uu} UU" if state == "valid" else f"cost {opt.cost_uu} UU"
            lines.append(f"class {cls}   rule {', '.join(r.id for r in rs)}   reversible "
                         f"{'yes' if opt.reversible else 'no'}   {cost}")
        else:
            opt = None
            lines.append(f"class {cls}   rule none   (no rule opts this class in)")
        if not isinstance(inputs, Inputs):
            continue
        if state != "valid":
            t = dict.fromkeys(OUTCOMES, 0)
            for _d, c, o in inputs.outcomes:
                if c == cls:
                    t[o] += 1
            note = "every outcome recorded; no settings, so no score" if state == "absent" else \
                "every outcome recorded; the settings are invalid, so no score"
            lines.append(f"  approved {t['approved']}  edited {t['edited']}  rejected {t['rejected']}  reverted "
                         f"{t['reverted']}  ({note})")
            if state == "invalid":
                lines.append(f"  state: Ask me first ({SETTINGS_INVALID})")
            continue
        c = count(inputs, cls, today, when, settings)
        n = c.a + c.e + c.r + settings.revert_weight * c.v
        score = wilson(c.a, c.e, c.r, c.v, settings.revert_weight, settings.confidence_z)
        lines.append(f"  approved {c.a}  edited {c.e}  rejected {c.r}  reverted {c.v}  weight {settings.revert_weight}"
                     f"  n {n}  score {score} per mille  (needs n {settings.min_decisions}, score "
                     f"{settings.min_lower_bound})")
        if not on:
            word = AUTONOMY_OFF
        elif switch != kill.OFF:
            word = KILL_SWITCH
        elif opt is None:
            word = NOT_OPTED_IN
        elif any(r.review_by is not None and r.review_by < today for r in rs):
            word = OPT_IN_LAPSED
        elif not opt.reversible:
            word = IRREVERSIBLE
        elif opt.cost_uu > settings.max_cost_uu:
            word = COST
        elif c.cooldown_until is not None:
            word = COOLDOWN
        elif n < settings.min_decisions:
            word = LOW_DATA
        elif score < settings.min_lower_bound:
            word = LOW_SCORE
        elif c.moves_today >= settings.max_moves_per_day:
            word = DAILY_CAP
        else:
            word = None
        cool = f"cooldown until {c.cooldown_until}" if c.cooldown_until else "no cooldown"
        lines.append(f"  {cool}   moves today {c.moves_today} of {settings.max_moves_per_day}   state: "
                     + (f"Ask me first ({word})" if word else "eligible"))
    if state == "absent":
        head = "graded autonomy: off (no autonomy.yaml)."
    elif state == "invalid":
        head = "graded autonomy: off (autonomy.yaml is invalid, see umwayi autonomy validate)."
    elif not settings.enabled:
        head = "graded autonomy: off (enabled: false)."
    else:
        head = "graded autonomy: on."
    if isinstance(inputs, Inputs):
        tail = f"inputs: intact ({len(inputs.outcomes)} outcomes)."
    elif why_not == "invalid":
        tail = "inputs: invalid, so no class is moved and no score is shown."
    else:
        tail = f"inputs: cannot be read ({why_not}), so no class is moved and no score is shown."
    lines.append(f"{head} {tail} kill switch: {switch}.")
    return 0, lines
