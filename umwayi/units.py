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
class Units:
    """A valid units.yaml (or none: present False, every reading unknown under the placeholders)."""
    present: bool
    sha256: str | None  # of the file's bytes; None when there is no file
    platforms: dict = field(default_factory=dict)  # name -> PlatformUnits
    models: dict = field(default_factory=dict)  # name -> {type: Rate}
    limits: dict = field(default_factory=lambda: dict(PLACEHOLDERS))  # name -> UU
    given_limits: dict = field(default_factory=dict)  # only the limits the file names

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
        if key not in ("version", "platforms", "models", "limits"):
            problem(f"{_name(key)} is not allowed at the top, only version, platforms, models and limits", key)
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

    if problems:
        return None, sorted(problems, key=lambda p: p.line)
    return Units(True, sha256, platforms, models, limits, given), []


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
               + ", ".join(f"{k} {v} UU" for k, v in units.limits.items())]


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
