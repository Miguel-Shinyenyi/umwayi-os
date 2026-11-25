"""Budget governor, tasks B.1 and B.2: units.yaml, micros and UU, readings and tags.

The unit UU is one US cent of estimated list price (B.R1.1). The ledger keeps whole micros of a dollar
(integers, never floats); UU = micros / 10000 rounded up, computed only when a limit is checked or a value
is shown (B.R1.2). units.yaml in the root says how each platform's reading becomes micros:

    version: 1
    platforms:
      claude-code:
        reading: usd_micros        # measured, from the telemetry receiver (umwayi/telemetry.py)
        fallback: tokens           # only token counts arrived: priced with the rates under models
      kiro:
        reading: runs
        run_micros:
          value: 400000
          date: 2026-11-09
          source: owner
    models:                        # micros per million tokens, by type
      claude-sonnet-5:
        input:
          value: 3000000
          date: 2026-11-09
          source: https://example.com/pricing
    limits:                        # UU; a limit that is not given keeps its placeholder
      per_run: 100

A provider is a source of limits (M4 a, the Muse route). It is optional and does not change any reading above:

    providers:
      example-provider:          # EXAMPLE ONLY, not a record: no file of this repository holds an acceptance
        cost_kind: free_credits    # free_credits, subscription or paid
        limit:                     # what the provider sets, in UU (one UU is one cent)
          credits_uu: 1000         # free_credits: credits_uu; subscription: five_hour_uu and or weekly_uu; paid: cap_uu
        acceptance:                # the owner writes this, only after accepting; leave it out to withdraw or not give it
          accepted_free: true      # only true is allowed: to say no, remove the whole acceptance block
          date: 2026-01-01
          amount_uu: 1000
          source: owner

Two optional keys of a provider set its pacing period (M4 b): `until` (the next date the allowance renews or ends, a real date) and
`horizon_days` (1 to 366, default 30, used when `until` is absent or already past). `pace` spreads what is left over that period.

Three optional keys of a provider set its stop line (M4 d): `stop_left_pct` (free credits: stop new runs when this percent of the amount at
acceptance is left; default 5; 0 removes the stop), `five_hour_stop_pct` (default 80) and `weekly_stop_pct` (default 90), the percent of a
subscription allowance used at which new runs stop (100 removes the stop). `heads_up` and `stop_gate` are pure: nothing calls them yet.

An optional `goals` section gives a long-running goal a share of one provider's allowance (M4 h). Nothing starts or stops by it yet:

    goals:
      example-goal:              # EXAMPLE ONLY
        provider: example-provider # a provider of the section above
        share: 60                  # a whole percent, 1 to 100; the shares on one provider may add up to 80 at most (20 percent is the owner's)

A video line (L9, the PR video rule) is the owner's cap on concept videos, in UU. It is optional, and without it videos are OFF:

    video:
      mode: on          # on or off; off means no video, whatever the numbers say
      per_video: 50     # the most one video may cost (its estimate, written before it is made)
      per_day: 100      # the most the videos of one day may cost together

`video_gate` answers Yes (`within_cap`) or No with a fixed reason: `video_off` (mode off, no video line, or a cap of 0), `owner_off` (the owner turned videos off for this pull request), `over_per_video` or `over_per_day`. A free local render has an estimate of 0 UU and still needs the owner to turn videos on. Nothing calls the gate yet, so no video is made, written to the logbook or put on a waiting list by it.

Without an acceptance a free credit or subscription provider is Ask me first; a paid provider is Ask me first on every goal, so an
acceptance does not apply to it (`provider_gate`). Nothing here starts, stops or spends anything yet: the pacing, the heads up, the stop
line and the goal shares are later parts of M4.

Readings are tagged measured (the agent's own report), declared (rates in units.yaml) or unknown. An unknown
reading counts at limits.unknown_worst_case, never zero (B.R1.4). Every problem has a line number and never the
text of a line; a problem is a config error (exit 64).
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path

from umwayi import goalshare as _goalshare
from umwayi import miniyaml
from umwayi.errors import ConfigError

UNITS_FILE = "units.yaml"
MAX_FILE_BYTES = 64 * 1024
MICROS_PER_UU = 10_000
MAX_NUMBER = 10 ** 12  # every value in units.yaml and every number from telemetry: 0 to 10^12
MEASURED, DECLARED, UNKNOWN = "measured", "declared", "unknown"
TAGS = (MEASURED, DECLARED, UNKNOWN)

# B.R1.7: the placeholders until calibrated, in UU
LIMIT_NAMES = ("per_run", "per_day", "per_agent_per_day", "per_platform_per_day", "unknown_worst_case")
PLACEHOLDERS = {"per_run": 100, "per_day": 500, "per_agent_per_day": 300, "per_platform_per_day": 400,
                "unknown_worst_case": 100}
READINGS = ("usd_micros", "tokens", "credits", "runs")
TOKEN_TYPES = ("input", "output", "cache_read", "cache_creation")
PLATFORM_KEYS = ("reading", "fallback", "run_micros", "credit_micros", "credits_per_run")
COST_KINDS = ("free_credits", "subscription", "paid")
DEFAULT_HORIZON_DAYS = 30
HEADS_UP_LEVELS = (50, 20, 10)  # percent left of the amount at acceptance that make a louder line
DEFAULT_STOP_LEFT_PCT, DEFAULT_FIVE_HOUR_STOP_PCT, DEFAULT_WEEKLY_STOP_PCT = 5, 80, 90
MAX_HORIZON_DAYS = 366
# the limit keys a cost kind takes; a subscription needs at least one allowance
LIMIT_KEYS = {"free_credits": ("credits_uu",), "subscription": ("five_hour_uu", "weekly_uu"), "paid": ("cap_uu",)}
ACCEPTANCE_KEYS = ("accepted_free", "date", "amount_uu", "source")
VIDEO_KEYS = ("mode", "per_video", "per_day")
VIDEO_MODES = ("on", "off")
RATE_KEYS = ("value", "date", "source")

_PLATFORM = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
MODEL_NAME = re.compile(r"^[A-Za-z0-9._:/-]{1,64}$")
_SOURCE = re.compile(r"^(owner|https://[A-Za-z0-9._~:/?#@!$&'*+=%-]{1,200})$")
_YAML_LINE = re.compile(r"^line (\d+): (.*)$")
_PLAIN_KEY = re.compile(r"^[A-Za-z0-9_.:/-]{1,64}$")


def uu(micros: int) -> int:
    """micros to UU, rounded up (B.R1.2). Only called when a limit is checked or a value is shown."""
    return -(-int(micros) // MICROS_PER_UU)


def limit_micros(value_uu: int) -> int:
    return int(value_uu) * MICROS_PER_UU


@dataclass(frozen=True)
class Rate:
    value: int
    date: str
    source: str

    def show(self) -> str:
        return f"{self.value} ({self.date}, {self.source})"


@dataclass(frozen=True)
class PlatformUnits:
    reading: str
    fallback: str | None = None
    run_micros: Rate | None = None
    credit_micros: Rate | None = None
    credits_per_run: Rate | None = None


@dataclass(frozen=True)
class ProviderUnits:
    cost_kind: str
    limit: dict  # key -> UU
    acceptance: dict | None = None  # accepted_free, date, amount_uu, source
    until: str | None = None  # the next date the allowance renews or ends
    horizon_days: int = DEFAULT_HORIZON_DAYS
    stop_left_pct: int = DEFAULT_STOP_LEFT_PCT
    five_hour_stop_pct: int = DEFAULT_FIVE_HOUR_STOP_PCT
    weekly_stop_pct: int = DEFAULT_WEEKLY_STOP_PCT


@dataclass(frozen=True)
class GoalShare:
    """A long-running goal's share of one provider's allowance (M4 h): the provider and a whole percent from 1 to 100."""
    provider: str
    share: int


@dataclass(frozen=True)
class VideoUnits:
    mode: str  # on or off
    per_video: int  # UU
    per_day: int  # UU


@dataclass(frozen=True)
class Units:
    """A valid units.yaml (or none: present False, every reading unknown under the placeholders)."""
    present: bool
    sha256: str | None  # of the file's bytes; None when there is no file
    platforms: dict = field(default_factory=dict)  # name -> PlatformUnits
    models: dict = field(default_factory=dict)  # name -> {type: Rate}
    limits: dict = field(default_factory=lambda: dict(PLACEHOLDERS))  # name -> UU
    given_limits: dict = field(default_factory=dict)  # only the limits the file names
    providers: dict = field(default_factory=dict)  # name -> ProviderUnits
    video: VideoUnits | None = None  # None: no video line, so videos are off
    goals: dict = field(default_factory=dict)  # name -> GoalShare (M4 h)

    def state(self) -> dict:
        """Every rate, limit and reading word the file states, as name -> shown value (for the change entry)."""
        out = {}
        for name, p in sorted(self.platforms.items()):
            out[f"platforms.{name}.reading"] = p.reading
            if p.fallback:
                out[f"platforms.{name}.fallback"] = p.fallback
            for key in ("run_micros", "credit_micros", "credits_per_run"):
                rate = getattr(p, key)
                if rate is not None:
                    out[f"platforms.{name}.{key}"] = rate.show()
        for name, rates in sorted(self.models.items()):
            for t in TOKEN_TYPES:
                if t in rates:
                    out[f"models.{name}.{t}"] = rates[t].show()
        for name in LIMIT_NAMES:
            if name in self.given_limits:
                out[f"limits.{name}"] = str(self.given_limits[name])
        if self.video is not None:
            out["video.mode"] = self.video.mode
            out["video.per_video"] = str(self.video.per_video)
            out["video.per_day"] = str(self.video.per_day)
        for name, p in sorted(self.providers.items()):
            out[f"providers.{name}.cost_kind"] = p.cost_kind
            for key, value in sorted(p.limit.items()):
                out[f"providers.{name}.limit.{key}"] = str(value)
            if p.until:
                out[f"providers.{name}.until"] = p.until
            if p.horizon_days != DEFAULT_HORIZON_DAYS:
                out[f"providers.{name}.horizon_days"] = str(p.horizon_days)
            if p.acceptance is not None:
                a = p.acceptance
                out[f"providers.{name}.acceptance"] = f"{a['amount_uu']} UU ({a['date']}, {a['source']})"
        for name, g in sorted(self.goals.items()):
            out[f"goals.{name}.provider"] = g.provider
            out[f"goals.{name}.share"] = str(g.share)
        return out


@dataclass(frozen=True)
class Problem:
    line: int
    message: str

    def render(self) -> str:
        return f"line {self.line}: {self.message}"


@dataclass(frozen=True)
class Reading:
    tag: str  # measured, declared or unknown
    micros: int
    why: str  # how it was read; names and numbers only


# ------------------------------------------------------------ the file


def units_path(root: Path) -> Path:
    return Path(root) / UNITS_FILE


def read_bytes(root: Path) -> bytes | None:
    """The bytes of units.yaml, or None when there is none. A link, a folder or too big: a config error."""
    path = units_path(root)
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError:
        raise ConfigError(f"budget: {UNITS_FILE} cannot be read") from None
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise ConfigError(f"budget: {UNITS_FILE} must be a regular file, not a link or a folder")
    if st.st_size > MAX_FILE_BYTES:
        raise ConfigError(f"budget: {UNITS_FILE} is larger than {MAX_FILE_BYTES} bytes")
    try:
        data = path.read_bytes()
    except OSError:
        raise ConfigError(f"budget: {UNITS_FILE} cannot be read") from None
    if len(data) > MAX_FILE_BYTES:
        raise ConfigError(f"budget: {UNITS_FILE} is larger than {MAX_FILE_BYTES} bytes")
    return data


def _line_map(text: str) -> dict:
    """path tuple -> 1-based line, for the nested block mappings of units.yaml (no lists)."""
    found: dict = {}
    stack: list = []  # (indent, key)
    for ind, t, n in miniyaml._tokenize(text):
        kv = miniyaml._split_key(t) if not miniyaml._is_item(t) else None
        if kv is None:
            continue
        while stack and stack[-1][0] >= ind:
            stack.pop()
        stack.append((ind, kv[0]))
        found.setdefault(tuple(k for _i, k in stack), n)
    return found


def _whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_NUMBER


def _real_date(value) -> bool:
    from umwayi.logbook import real_date
    return isinstance(value, str) and real_date(value)


def _name(key) -> str:
    return f"'{key}'" if isinstance(key, str) and _PLAIN_KEY.match(key) else "a key"


def _number_problem(value, what: str) -> str | None:
    if isinstance(value, float):
        return f"{what} must be a whole number, not a decimal"
    if not _whole(value):
        return f"{what} must be a whole number from 0 to {MAX_NUMBER}"
    return None


def check_text(text: str, today: str, sha256: str | None = None) -> tuple:
    """(Units or None, problems). today (the logbook date) is the latest date a rate may carry."""
    try:
        data = miniyaml.loads(text)
    except miniyaml.YamlError as e:
        m = _YAML_LINE.match(str(e))
        return None, [Problem(int(m.group(1)), m.group(2)) if m else Problem(1, "the file cannot be read as YAML")]
    where = _line_map(text)

    def line(*path) -> int:
        for k in range(len(path), 0, -1):
            if path[:k] in where:
                return where[path[:k]]
        return 1

    problems: list = []

    def problem(message: str, *path) -> None:
        problems.append(Problem(line(*path), message))

    if not isinstance(data, dict):
        return None, [Problem(1, "the file must be a mapping with version, platforms, models and limits")]
    for key in data:
        if key not in ("version", "platforms", "models", "limits", "providers", "video", "goals"):
            problem(f"{_name(key)} is not allowed at the top, only version, platforms, models, limits, providers, video and goals", key)
    if data.get("version") != 1 or isinstance(data.get("version"), bool):
        problem("version must be 1", "version")

    def rate(value, label: str, *path) -> Rate | None:
        if not isinstance(value, dict):
            problem(f"{label} must be a mapping with value, date and source", *path)
            return None
        ok = True
        for key in value:
            if key not in RATE_KEYS:
                problem(f"{label}: {_name(key)} is not allowed, only value, date and source", *path, key)
                ok = False
        for key in RATE_KEYS:
            if key not in value:
                problem(f"{label} needs {key}", *path)
                ok = False
        if "value" in value:
            wrong = _number_problem(value["value"], f"{label}: value")
            if wrong:
                problem(wrong, *path, "value")
                ok = False
        if "date" in value:
            d = value["date"]
            if not _real_date(d):
                problem(f"{label}: date must be a real date YYYY-MM-DD", *path, "date")
                ok = False
            elif d > today:
                problem(f"{label}: date must not be in the future", *path, "date")
                ok = False
        if "source" in value:
            s = value["source"]
            if not isinstance(s, str) or not _SOURCE.match(s):
                problem(f"{label}: source must be owner or an https URL without spaces, commas, semicolons or "
                        "brackets", *path, "source")
                ok = False
        return Rate(value["value"], value["date"], value["source"]) if ok else None

    platforms: dict = {}
    raw = data.get("platforms")
    if "platforms" in data and not isinstance(raw, dict):
        problem("platforms must be a mapping of platform names", "platforms")
        raw = {}
    for name, p in (raw or {}).items():
        label = f"platforms.{name}" if isinstance(name, str) and _PLATFORM.match(name) else "a platform"
        if not (isinstance(name, str) and _PLATFORM.match(name)):
            problem("a platform name must be a lowercase letter, then lowercase letters, digits and '-'",
                    "platforms", name)
            continue
        if not isinstance(p, dict):
            problem(f"{label} must be a mapping with reading", "platforms", name)
            continue
        before = len(problems)
        for key in p:
            if key not in PLATFORM_KEYS:
                problem(f"{label}: {_name(key)} is not allowed", "platforms", name, key)
        reading = p.get("reading")
        if "reading" not in p:
            problem(f"{label} needs reading", "platforms", name)
        elif reading not in READINGS:
            problem(f"{label}: reading must be one of: {', '.join(READINGS)}", "platforms", name, "reading")
        fallback = p.get("fallback")
        if "fallback" in p and (reading != "usd_micros" or fallback != "tokens"):
            problem(f"{label}: fallback may only be tokens, and only with reading usd_micros", "platforms", name,
                    "fallback")
        needs = {"runs": ("run_micros",), "credits": ("credit_micros", "credits_per_run")}.get(reading, ())
        for key in ("run_micros", "credit_micros", "credits_per_run"):
            if key in p and key not in needs:
                problem(f"{label}: {key} is only for reading "
                        f"{'runs' if key == 'run_micros' else 'credits'}", "platforms", name, key)
            elif key not in p and key in needs:
                problem(f"{label}: reading {reading} needs {key}", "platforms", name)
        rates = {key: rate(p[key], f"{label}.{key}", "platforms", name, key) for key in needs if key in p}
        if len(problems) == before:
            platforms[name] = PlatformUnits(reading, fallback, rates.get("run_micros"), rates.get("credit_micros"),
                                            rates.get("credits_per_run"))

    models: dict = {}
    raw = data.get("models")
    if "models" in data and not isinstance(raw, dict):
        problem("models must be a mapping of model names", "models")
        raw = {}
    for name, m in (raw or {}).items():
        if not (isinstance(name, str) and MODEL_NAME.match(name)):
            problem("a model name must be 1 to 64 letters, digits or . _ : / -", "models", name)
            continue
        label = f"models.{name}"
        if not isinstance(m, dict) or not m:
            problem(f"{label} must be a mapping of token types ({', '.join(TOKEN_TYPES)})", "models", name)
            continue
        found = {}
        for t, value in m.items():
            if t not in TOKEN_TYPES:
                problem(f"{label}: {_name(t)} is not a token type, only {', '.join(TOKEN_TYPES)}", "models", name, t)
                continue
            r = rate(value, f"{label}.{t}", "models", name, t)
            if r is not None:
                found[t] = r
        models[name] = found

    limits = dict(PLACEHOLDERS)
    given: dict = {}
    raw = data.get("limits")
    if "limits" in data and not isinstance(raw, dict):
        problem("limits must be a mapping of limits in UU", "limits")
        raw = {}
    for key, value in (raw or {}).items():
        if key not in LIMIT_NAMES:
            problem(f"limits: {_name(key)} is not a limit, only {', '.join(LIMIT_NAMES)}", "limits", key)
            continue
        wrong = _number_problem(value, f"limits.{key}")
        if wrong:
            problem(wrong + " (UU)", "limits", key)
            continue
        limits[key] = given[key] = value

    providers: dict = {}
    raw = data.get("providers")
    if "providers" in data and not isinstance(raw, dict):
        problem("providers must be a mapping of provider names", "providers")
        raw = {}
    for name, p in (raw or {}).items():
        if not (isinstance(name, str) and _PLATFORM.match(name)):
            problem("a provider name must be a lowercase letter, then lowercase letters, digits and '-'", "providers", name)
            continue
        label = f"providers.{name}"
        if not isinstance(p, dict):
            problem(f"{label} must be a mapping with cost_kind and limit", "providers", name)
            continue
        before = len(problems)
        for key in p:
            if key not in ("cost_kind", "limit", "acceptance", "until", "horizon_days", "stop_left_pct", "five_hour_stop_pct", "weekly_stop_pct"):
                problem(f"{label}: {_name(key)} is not allowed, only cost_kind, limit, acceptance, until, horizon_days and the stop keys",
                        "providers", name, key)
        for key in ("stop_left_pct", "five_hour_stop_pct", "weekly_stop_pct"):
            if key in p and (isinstance(p[key], bool) or not isinstance(p[key], int) or not 0 <= p[key] <= 100):
                problem(f"{label}: {key} must be a whole number from 0 to 100", "providers", name, key)
        if "until" in p and not _real_date(p["until"]):
            problem(f"{label}: until must be a real date YYYY-MM-DD", "providers", name, "until")
        if "horizon_days" in p and (isinstance(p["horizon_days"], bool) or not isinstance(p["horizon_days"], int)
                                    or not 1 <= p["horizon_days"] <= MAX_HORIZON_DAYS):
            problem(f"{label}: horizon_days must be a whole number from 1 to {MAX_HORIZON_DAYS}", "providers", name, "horizon_days")
        kind = p.get("cost_kind")
        if kind not in COST_KINDS:
            problem(f"{label}: cost_kind must be one of: {', '.join(COST_KINDS)}", "providers", name, "cost_kind")
        found: dict = {}
        lim = p.get("limit")
        if not isinstance(lim, dict) or not lim:
            problem(f"{label} needs limit, a mapping of the limits the provider sets (in UU)", "providers", name, "limit")
        else:
            allowed = LIMIT_KEYS.get(kind, ())
            for key, value in lim.items():
                if key not in allowed:
                    problem(f"{label}.limit: {_name(key)} is not a limit of cost_kind {kind}"
                            + (f", only {', '.join(allowed)}" if allowed else ""), "providers", name, "limit", key)
                    continue
                wrong = _number_problem(value, f"{label}.limit.{key}")
                if wrong:
                    problem(wrong + " (UU)", "providers", name, "limit", key)
                else:
                    found[key] = value
            if allowed and not any(k in lim for k in allowed):
                problem(f"{label}.limit needs {' or '.join(allowed)}", "providers", name, "limit")
        acc = p.get("acceptance")
        accepted = None
        if "acceptance" in p:
            if kind == "paid":
                problem(f"{label}: a paid provider asks on every goal, so it takes no acceptance", "providers", name, "acceptance")
            elif not isinstance(acc, dict):
                problem(f"{label}.acceptance must be a mapping with accepted_free, date, amount_uu and source",
                        "providers", name, "acceptance")
            else:
                ok = True
                for key in acc:
                    if key not in ACCEPTANCE_KEYS:
                        problem(f"{label}.acceptance: {_name(key)} is not allowed, only {', '.join(ACCEPTANCE_KEYS)}",
                                "providers", name, "acceptance", key)
                        ok = False
                for key in ACCEPTANCE_KEYS:
                    if key not in acc:
                        problem(f"{label}.acceptance needs {key}", "providers", name, "acceptance")
                        ok = False
                if ok:
                    if acc["accepted_free"] is not True:
                        problem(f"{label}.acceptance: accepted_free must be true (remove the acceptance to withdraw it)",
                                "providers", name, "acceptance", "accepted_free")
                        ok = False
                    if not _real_date(acc["date"]):
                        problem(f"{label}.acceptance: date must be a real date YYYY-MM-DD", "providers", name, "acceptance", "date")
                        ok = False
                    elif acc["date"] > today:
                        problem(f"{label}.acceptance: date must not be in the future", "providers", name, "acceptance", "date")
                        ok = False
                    wrong = _number_problem(acc["amount_uu"], f"{label}.acceptance.amount_uu")
                    if wrong:
                        problem(wrong + " (UU)", "providers", name, "acceptance", "amount_uu")
                        ok = False
                    if not isinstance(acc["source"], str) or not _SOURCE.match(acc["source"]):
                        problem(f"{label}.acceptance: source must be owner or an https URL without spaces, commas, semicolons or "
                                "brackets", "providers", name, "acceptance", "source")
                        ok = False
                if ok:
                    accepted = dict(acc)
        if len(problems) == before:
            providers[name] = ProviderUnits(kind, found, accepted, p.get("until"), p.get("horizon_days", DEFAULT_HORIZON_DAYS),
                                            p.get("stop_left_pct", DEFAULT_STOP_LEFT_PCT),
                                            p.get("five_hour_stop_pct", DEFAULT_FIVE_HOUR_STOP_PCT),
                                            p.get("weekly_stop_pct", DEFAULT_WEEKLY_STOP_PCT))

    goals: dict = {}
    raw_goals = data.get("goals")
    if "goals" in data and not isinstance(raw_goals, dict):
        problem("goals must be a mapping of goal names", "goals")
        raw_goals = {}
    taken: dict = {}  # provider -> the shares already given, in file order
    for name, g in (raw_goals or {}).items():
        if not (isinstance(name, str) and _PLATFORM.match(name)):
            problem("a goal name must be a lowercase letter, then lowercase letters, digits and '-'", "goals", name)
            continue
        label = f"goals.{name}"
        if not isinstance(g, dict) or set(g) != {"provider", "share"}:
            problem(f"{label} must be a mapping with exactly provider and share", "goals", name)
            continue
        prov, share = g["provider"], g["share"]
        if not isinstance(prov, str) or prov not in providers:
            problem(f"{label}: provider must name a provider of the providers section that is valid", "goals", name, "provider")
            continue
        if not isinstance(share, int) or isinstance(share, bool) or not 1 <= share <= 100:
            problem(f"{label}: share must be a whole percent from 1 to 100", "goals", name, "share")
            continue
        fits, why = _goalshare.shares_ok(taken.get(prov, []), share)
        if not fits:
            problem(f"{label}: {why}: the shares of the goals on {prov} may not add up above "
                    f"{100 - _goalshare.DEFAULT_RESERVE_PCT} percent (the rest is the owner's own use)", "goals", name, "share")
            continue
        taken.setdefault(prov, []).append(share)
        goals[name] = GoalShare(prov, share)

    video = None
    if "video" in data:
        raw = data["video"]
        if not isinstance(raw, dict):
            problem("video must be a mapping with mode, per_video and per_day", "video")
        else:
            before = len(problems)
            for key in raw:
                if key not in VIDEO_KEYS:
                    problem(f"video: {_name(key)} is not allowed, only {', '.join(VIDEO_KEYS)}", "video", key)
            for key in VIDEO_KEYS:
                if key not in raw:
                    problem(f"video needs {key}", "video")
            if raw.get("mode") not in VIDEO_MODES and "mode" in raw:
                problem("video: mode must be on or off", "video", "mode")
            for key in ("per_video", "per_day"):
                if key in raw:
                    wrong = _number_problem(raw[key], f"video.{key}")
                    if wrong:
                        problem(wrong + " (UU)", "video", key)
            if len(problems) == before:
                video = VideoUnits(raw["mode"], raw["per_video"], raw["per_day"])

    if problems:
        return None, sorted(problems, key=lambda p: p.line)
    return Units(True, sha256, platforms, models, limits, given, providers, video, goals), []


def load(root: Path, today: str) -> Units:
    """The valid units.yaml, or the placeholders when there is none. Invalid: a config error (exit 64)."""
    data = read_bytes(root)
    if data is None:
        return Units(False, None)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ConfigError(f"budget: {UNITS_FILE} is not valid UTF-8") from None
    units, problems = check_text(text, today, hashlib.sha256(data).hexdigest())
    if problems:
        raise ConfigError(f"budget: {UNITS_FILE} has {len(problems)} problem(s), see 'umwayi budget validate'. "
                          "Nothing was started.")
    return units


def validate(root: Path, today: str) -> tuple:
    """(code, lines) for `umwayi budget validate`. Reads only."""
    data = read_bytes(root)
    if data is None:
        return 0, [f"ok: there is no {UNITS_FILE}; every reading is unknown and counts at the worst case, under "
                   "the placeholder limits (" + ", ".join(f"{k} {v} UU" for k, v in PLACEHOLDERS.items()) + ")"]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return 64, [f"problem: line 1: {UNITS_FILE} is not valid UTF-8", f"1 problem(s) found in {UNITS_FILE}"]
    units, problems = check_text(text, today)
    if problems:
        return 64, [f"problem: {p.render()}" for p in problems] + [f"{len(problems)} problem(s) found in {UNITS_FILE}"]
    return 0, [f"ok: {UNITS_FILE} is valid: {len(units.platforms)} platform(s), {len(units.models)} model(s); limits "
               + ", ".join(f"{k} {v} UU" for k, v in units.limits.items())
               + (f"; {len(units.providers)} provider(s)" if units.providers else "")
               + (f"; videos {units.video.mode}" if units.video else "")]


def pace(p: ProviderUnits, left_uu: int, today: str, days_left_in_week: int | None = None):
    """(share_uu, days) or None. The share is what may be spent today so the allowance lasts its period (M4 b): the UU left over the days
    to `until` (or `horizon_days` when there is no future `until`) for free credits; the weekly allowance left over the days left in the
    owner's week (7 when the caller does not know) for a subscription with a weekly allowance. A subscription with only a five hour
    allowance and a paid provider have no daily share (None). The share rounds down, and is at least 0. Pure: it spends nothing."""
    from datetime import date as _date
    if p.cost_kind == "free_credits":
        days = p.horizon_days
        if p.until and p.until > today:
            days = (_date.fromisoformat(p.until) - _date.fromisoformat(today)).days
    elif p.cost_kind == "subscription" and "weekly_uu" in p.limit:
        days = days_left_in_week if days_left_in_week else 7
    else:
        return None
    days = max(1, days)
    return max(0, int(left_uu)) // days, days


def pacing_line(share_uu: int, days: int, estimate_uu: int) -> str | None:
    """The line that goes with a goal whose estimate is above today's share, or None when it fits."""
    if estimate_uu <= share_uu:
        return None
    return (f"pacing: this goal is estimated at {estimate_uu} UU, above today's share of {share_uu} UU "
            f"(what is left spread over {days} day(s)). It may run; the allowance will not last the period at this rate.")


def percent_left(amount_uu: int, left_uu: int) -> int:
    """Whole percent of the amount that is left, rounded down, from 0 to 100. An amount of 0 is 0."""
    if amount_uu <= 0:
        return 0
    return max(0, min(100, int(left_uu) * 100 // int(amount_uu)))


def heads_up_level(amount_uu: int, left_uu: int):
    """The lowest of 50, 20 and 10 that the percent left is at or under, or None when more than half is left."""
    if amount_uu <= 0:
        return min(HEADS_UP_LEVELS)
    hit = [lv for lv in HEADS_UP_LEVELS if int(left_uu) * 100 <= lv * int(amount_uu)]  # exact: 50.01 percent left has not crossed 50
    return min(hit) if hit else None


def heads_up(p: ProviderUnits, left_uu: int, today: str, estimate_uu: int | None = None, days_left_in_week: int | None = None) -> list:
    """The lines at the start of a goal (M4 c): the limit left, today's share, the estimate and the pacing line when the goal is over the
    share, and a louder line when the limit left has crossed 50, 20 or 10 percent of the amount at acceptance. [] for a provider with no
    acceptance (the gate asks first) and for a paid one (it asks on every goal; a heads up is not enough). Pure: it prints and stops nothing."""
    if p.acceptance is None or p.cost_kind == "paid":
        return []
    amount = p.acceptance["amount_uu"]
    pct = percent_left(amount, left_uu)
    line = f"heads up: {left_uu} of {amount} UU left ({pct} percent)"
    pace_result = pace(p, left_uu, today, days_left_in_week)
    share = pace_result[0] if pace_result else None
    if pace_result:
        line += f"; today's share is {share} UU over {pace_result[1]} day(s)"
    if estimate_uu is not None:
        line += f"; this goal is estimated at {estimate_uu} UU"
    out = [line + "."]
    if pace_result and estimate_uu is not None:
        over = pacing_line(share, pace_result[1], estimate_uu)
        if over:
            out.append(over)
    level = heads_up_level(amount, left_uu)
    if level is not None:
        out.append(f"HEADS UP: under {level} percent of the amount at acceptance is left ({left_uu} of {amount} UU).")
    return out


def stop_gate(p: ProviderUnits, left_uu=None, five_hour_used_pct=None, weekly_used_pct=None) -> tuple:
    """(decision, reason) for a NEW run (M4 d). decision is "yes", "no" or "ask". Reasons: credits_low (a free credit provider at or under the
    stop line of the amount at acceptance, 5 percent by default, so the card on file is never charged by accident), five_hour_stop and
    weekly_stop (a subscription at or over 80 and 90 percent of its allowance by default), use_unknown (the reading the stop needs is not
    known: ask), paid_asks_every_goal, and within_limits. The owner moves or removes a stop by hand with the stop keys. Pure."""
    if p.cost_kind == "paid":
        return "ask", "paid_asks_every_goal"
    if p.cost_kind == "free_credits":
        if p.acceptance is None or left_uu is None:
            return "ask", "use_unknown"
        if p.stop_left_pct > 0 and int(left_uu) * 100 <= p.stop_left_pct * int(p.acceptance["amount_uu"]):
            return "no", "credits_low"
        return "yes", "within_limits"
    needs_five = "five_hour_uu" in p.limit and p.five_hour_stop_pct < 100
    needs_week = "weekly_uu" in p.limit and p.weekly_stop_pct < 100
    if (needs_five and five_hour_used_pct is None) or (needs_week and weekly_used_pct is None):
        return "ask", "use_unknown"
    if needs_five and five_hour_used_pct >= p.five_hour_stop_pct:
        return "no", "five_hour_stop"
    if needs_week and weekly_used_pct >= p.weekly_stop_pct:
        return "no", "weekly_stop"
    return "yes", "within_limits"


def video_gate(units: Units, estimate_uu: int, spent_today_uu: int = 0, pr_off: bool = False) -> tuple:
    """(decision, reason) before a video is made (L9). decision is "yes" or "no". The reasons are fixed words: owner_off (the owner turned videos
    off for this pull request: it wins over everything), video_off (mode off, no video line, or a cap of 0), over_per_video, over_per_day, and
    within_cap. The estimate is the cost in UU written BEFORE the video is made; a free local render is 0. Pure: it makes, logs and stops nothing."""
    if pr_off:
        return "no", "owner_off"
    v = units.video
    if v is None or v.mode != "on" or v.per_video <= 0 or v.per_day <= 0:
        return "no", "video_off"
    if estimate_uu > v.per_video:
        return "no", "over_per_video"
    if spent_today_uu + estimate_uu > v.per_day:
        return "no", "over_per_day"
    return "yes", "within_cap"


def provider_gate(units: Units, provider: str) -> tuple:
    """(decision, reason) for a provider before a goal starts. decision is "yes" or "ask" (Ask me first). The reasons are fixed words:
    provider_unknown (not in units.yaml), no_acceptance (a free credit or subscription provider the owner has not accepted) and
    paid_asks_every_goal (a paid provider is never accepted once). This is the whole of M4 a: it spends and stops nothing."""
    p = units.providers.get(provider)
    if p is None:
        return "ask", "provider_unknown"
    if p.cost_kind == "paid":
        return "ask", "paid_asks_every_goal"
    if p.acceptance is None:
        return "ask", "no_acceptance"
    return "yes", "accepted"


# ------------------------------------------------------------ readings (B.2)


def model_word(name) -> str:
    """A model name as it may appear in the logbook: the plain name, or `other`."""
    return name if isinstance(name, str) and MODEL_NAME.match(name) else "other"


def price_tokens(units: Units, tokens: dict) -> int | None:
    """micros for {(model, type): count} at the declared rates, rounded up; None if any model or type has no rate."""
    total = 0
    for (model, t), count in tokens.items():
        if not count:
            continue
        r = units.models.get(model, {}).get(t)
        if r is None:
            return None
        total += count * r.value
    return -(-total // 1_000_000)


def reading(units: Units, platform: str, report: dict | None, started: bool, reserved: int) -> Reading:
    """The reading of one run (B.R1.3, B.R1.4, B.R2.5).

    report is the telemetry receiver's totals (Claude Code), or None for a platform umwayi reads nothing from.
    started False: the agent never started, so nothing was spent (declared 0).
    """
    worst = limit_micros(units.limits["unknown_worst_case"])
    if not started:
        return Reading(DECLARED, 0, "the agent never started")
    p = units.platforms.get(platform)
    if report is not None and report.get("invalid"):
        so_far = current_micros(units, platform, report) or 0
        return Reading(UNKNOWN, max(reserved, so_far), f"the telemetry was not valid ({report['invalid']}); "
                                                         "settled at the full reservation")
    if report is not None and (p is None or p.reading == "usd_micros"):
        if report.get("requests"):
            return Reading(MEASURED, report["event_micros"], "the api_request events of the agent's own report")
        if report.get("metric_seen"):
            return Reading(MEASURED, report["metric_micros"], "the claude_code.cost.usage metric of the agent's "
                                                              "own report")
        if p is not None and p.fallback == "tokens" and report.get("tokens"):
            priced = price_tokens(units, report["tokens"])
            if priced is not None:
                return Reading(DECLARED, priced, "token counts of the agent's own report at the rates in units.yaml")
            return Reading(UNKNOWN, worst, "token counts arrived for a model or type without a rate")
        return Reading(UNKNOWN, worst, "no report arrived")
    if p is None:
        return Reading(UNKNOWN, worst, f"units.yaml declares nothing for {platform}")
    if p.reading == "runs":
        return Reading(DECLARED, p.run_micros.value, "one run at platforms." + platform + ".run_micros")
    if p.reading == "credits":
        return Reading(DECLARED, p.credits_per_run.value * p.credit_micros.value,
                       f"platforms.{platform}.credits_per_run times platforms.{platform}.credit_micros")
    if p.reading == "tokens" and report is not None and report.get("tokens"):
        priced = price_tokens(units, report["tokens"])
        if priced is not None:
            return Reading(DECLARED, priced, "token counts of the agent's own report at the rates in units.yaml")
        return Reading(UNKNOWN, worst, "token counts arrived for a model or type without a rate")
    return Reading(UNKNOWN, worst, f"umwayi reads no {p.reading} from {platform}")


def current_micros(units: Units, platform: str, report: dict | None) -> int:
    """What a running agent has spent so far by its own report, for the mid-run cap. 0 while nothing is known."""
    if not report:
        return 0
    if report.get("requests"):
        return report["event_micros"]
    if report.get("metric_seen"):
        return report["metric_micros"]
    p = units.platforms.get(platform)
    if p is not None and (p.fallback == "tokens" or p.reading == "tokens") and report.get("tokens"):
        return price_tokens(units, report["tokens"]) or 0
    return 0


def sha256_of(root: Path) -> str | None:
    data = read_bytes(root)
    return None if data is None else hashlib.sha256(data).hexdigest()


def goal_lines(u: Units) -> list:
    """The lines of `umwayi budget status` for the goal shares (M4 h): per goal, its share and the caps that follow from it.

    Only a free credit provider with an acceptance has a month to share (the credits at acceptance over the horizon, Q8); for any other
    provider the caps are not computed and the line says so. What a goal has USED is not recorded per goal yet, so the lines show the
    full caps and say that. Pure: it reads the units and writes nothing."""
    out = []
    for name, g in sorted(u.goals.items()):
        p = u.providers[g.provider]
        head = f"goal {name}: share {g.share}% of {g.provider}"
        if p.cost_kind != "free_credits" or p.acceptance is None:
            out.append(head + "; the caps are not computed (they need free credits with the owner's acceptance)")
            continue
        c = _goalshare.caps(g.share, p.acceptance["amount_uu"], None, None, horizon_days=p.horizon_days)
        out.append(head + f"; at most {c['monthly_left']} UU in the {p.horizon_days} day period, {c['weekly_left']} UU a week, "
                   f"{c['daily_full']} UU a day. Use per goal is not recorded yet, so these are the full caps, not what is left.")
    return out
