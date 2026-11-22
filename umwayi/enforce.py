"""W78 step 1A: the enforcement mode and `umwayi enforce check|set` (docs/enforced-default-design.md).

One setting, `enforcement`: `enforced` (the default) or `cooperative`. It lives in `.umwayi/enforcement.yaml`:

    enforcement: enforced              # or cooperative, which then needs `until`
    until: 2026-11-24                  # only with cooperative
    agents:
      NAME: {enforcement: cooperative, until: 2026-11-24}     (written as a block, not inline)
    goals:
      G-0007: ...

Rules of the file, all fixed here:
  * A missing file is `enforced`. A malformed file is exit 64 (a ConfigError). An entry that is `cooperative` has a real
    `until` date no more than 30 days from today; an entry that is `enforced` has no `until`.
  * An `until` that is in the past means `enforced` again, with no action.
  * Only the owner at the terminal, with the typed word, switches to `cooperative` (exit 3 and nothing changed
    otherwise). Switching to `enforced` is allowed at any time. Both write one logbook entry.

What this slice does NOT do: nothing is enforced yet. The launcher, the platform sandbox, the confined process, the
broker and detect-after are not built, so `umwayi enforce check` says `refused (reason)` for every part of enforced.
The setting is only recorded and shown. No page says enforced by default (the one flag REAL_ENFORCED_RUN_DONE below).

Exit codes: 0, 2, 3, 64. Never 1. A crash is 2. Standard library only. Reads and writes only the settings file and the
logbook. It starts nothing and reads no credential.
"""
from __future__ import annotations

import hashlib
import os
import re
import stat
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from umwayi import agents, fsutil, logbook, miniyaml
from umwayi.errors import ConfigError, UmwayiError, UsageError

OK, NO, ASK, USAGE = 0, 2, 3, 64
SOURCE = "umwayi enforce"
FILE_REL = ".umwayi/enforcement.yaml"
ENFORCED, COOPERATIVE = "enforced", "cooperative"
MODES = (ENFORCED, COOPERATIVE)
MAX_DAYS, DEFAULT_DAYS = 30, 7
MAX_FILE_BYTES = 16 * 1024
CONFIRM_WORD = "cooperative"

# The W41 C1 watched list is built in step 3. The mode file is on it from the first line of that list (W78.R5).
WATCHED_GUARD_FILES = (FILE_REL,)

# The build record. The default flip is allowed to be claimed on a page only after the minimum profile exists and one
# real enforced run (W40) has finished a goal. Build step 10 sets this with the README and what-it-is.md in one release.
REAL_ENFORCED_RUN_DONE = False
OVERCLAIM = re.compile(r"enforced by default|enforcement is enforced|sandboxed by default", re.I)
CLAIM_PAGES = ("README.md", "PROJECT.md", "docs/what-it-is.md", "docs/goals.md")
TODAY_NOTE = "enforcement is cooperative today and enforced where built"

# The five parts of "enforced" (design note section 2) and the fixed list of reasons (section 3).
PARTS = ("environment", "confinement", "detect-after", "network", "untrusted-read")
REASONS = ("unavailable", "kernel", "dependency", "profile", "platform", "broker", "network")
# Section 5(d): every refusal is "refused: REASON. Allowed next: STEP." with both from fixed lists.
STEPS = {
    "switch": "run `umwayi enforce set cooperative --agent NAME --until DATE` at your terminal, or wait for the build",
    "terminal": "run this command at your terminal",
    "confirm": "run it again and type the word cooperative when asked",
    "until": "give --until with a date from today to 30 days ahead",
    "fix_file": f"fix or remove {FILE_REL}, then run `umwayi enforce check`",
    "look": f"look at {FILE_REL} and the logbook, then run `umwayi enforce set enforced` or set it again at your terminal",
    "agents": "fix agents.yaml (see `umwayi agent validate`), then run this again",
    "none": "nothing; this is a fact of this machine",
}
GOAL_ID = re.compile(r"^G-\d{4,}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def refusal(reason: str, step: str) -> str:
    """The one shape of a refusal. Both words are looked up in the fixed lists, so no input text can reach it."""
    if step not in STEPS:
        raise KeyError(step)
    return f"refused: {reason}. Allowed next: {STEPS[step]}."


@dataclass(frozen=True)
class Entry:
    mode: str
    until: str | None = None


@dataclass(frozen=True)
class Settings:
    base: Entry = Entry(ENFORCED)
    agents: dict = field(default_factory=dict)
    goals: dict = field(default_factory=dict)


def _real_date(text):
    if not isinstance(text, str) or not _DATE.fullmatch(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _entry(node, where, today):
    if not isinstance(node, dict) or not set(node) <= {"enforcement", "until"}:
        raise ConfigError(f"enforce: {where} must hold only enforcement and until")
    mode = node.get("enforcement")
    if mode not in MODES:
        raise ConfigError(f"enforce: {where} enforcement must be enforced or cooperative")
    until = node.get("until")
    if mode == ENFORCED:
        if until is not None:
            raise ConfigError(f"enforce: {where} has an until date but is enforced")
        return Entry(ENFORCED)
    d = _real_date(until)
    if d is None:
        raise ConfigError(f"enforce: {where} is cooperative and needs until: YYYY-MM-DD, a real date")
    if d > today + timedelta(days=MAX_DAYS):
        raise ConfigError(f"enforce: {where} until is more than {MAX_DAYS} days away")
    return Entry(COOPERATIVE, until)


def parse(text: str, today: date) -> Settings:
    """The settings of a file text. A bad file is a ConfigError (exit 64); the message never holds file text."""
    try:
        data = miniyaml.loads(text)
    except miniyaml.YamlError:
        raise ConfigError("enforce: the settings file cannot be read as YAML") from None
    if data is None:
        data = {}
    if not isinstance(data, dict) or not set(data) <= {"enforcement", "until", "agents", "goals"}:
        raise ConfigError("enforce: the settings file allows only enforcement, until, agents and goals")
    if "enforcement" not in data:
        raise ConfigError("enforce: the settings file needs the key enforcement")
    base = _entry({k: data[k] for k in ("enforcement", "until") if k in data}, "the top", today)
    out = {}
    for key, pattern in (("agents", None), ("goals", GOAL_ID)):
        block = data.get(key, {})
        if block is None:
            block = {}
        if not isinstance(block, dict):
            raise ConfigError(f"enforce: {key} must be a mapping")
        found = {}
        for name, node in block.items():
            ok = isinstance(name, str) and (pattern.fullmatch(name) if pattern else re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", name))
            if not ok:
                raise ConfigError(f"enforce: a name under {key} is not allowed")
            found[name] = _entry(node, f"{key} entry {name}", today)
        out[key] = found
    return Settings(base, out["agents"], out["goals"])


def read(root, today: date) -> Settings:
    """The settings of a root: a missing file is enforced (W78.R1). A link, a folder, a big or a bad file is exit 64."""
    path = Path(root) / FILE_REL
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return Settings()
    except OSError:
        raise ConfigError("enforce: the settings file cannot be read") from None
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode) or st.st_size > MAX_FILE_BYTES:
        raise ConfigError("enforce: the settings file must be a normal file of at most 16 KB")
    try:
        text = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        raise ConfigError("enforce: the settings file cannot be read as UTF-8") from None
    return parse(text, today)


def _active(entry: Entry | None, today: date) -> bool:
    return entry is not None and entry.mode == COOPERATIVE and _real_date(entry.until) is not None \
        and _real_date(entry.until) >= today


def mode_for(settings: Settings, agent: str | None, goal: str | None, today: date) -> tuple:
    """(mode, scope, until) in force. Cooperative only while an entry that applies is unexpired; the narrowest one
    names the scope. Anything else, and anything expired, is enforced (W78.R1, W78.R4)."""
    for scope, entry in (("goal", settings.goals.get(goal) if goal else None),
                         ("agent", settings.agents.get(agent) if agent else None), ("all", settings.base)):
        if _active(entry, today):
            return COOPERATIVE, scope, entry.until
    return ENFORCED, None, None


def mode_line(mode: str, scope: str | None, until: str | None) -> str:
    return "enforcement: enforced" if mode == ENFORCED else f"enforcement: cooperative ({scope}, until {until})"


def mode_of(root, agent: str | None = None, goal: str | None = None, today=None) -> str:
    """ENFORCED or COOPERATIVE for one agent (or goal), and never raises: a settings file that cannot be read is
    ENFORCED, so an error never relaxes anything (W78 step 2)."""
    try:
        t = today if isinstance(today, date) else date.fromisoformat(today) if today else date.today()
        return mode_for(read(root, t), agent, goal, t)[0]
    except Exception:
        return ENFORCED


def explicit_mode_of(root, agent: str | None = None, goal: str | None = None, today=None) -> str | None:
    """The mode of an agent when the owner wrote a mode file, else None. A missing file reads as enforced (W78.R1), but nothing
    that enforced means is built yet, so a start with no mode file keeps today's environment: only a start under a mode
    file that says `enforced` takes the scrubbed environment (W78 step 2). A file that cannot be read counts as written and
    as enforced, so an error never relaxes anything. Never raises."""
    try:
        os.lstat(Path(root) / FILE_REL)
    except FileNotFoundError:
        return None
    except OSError:
        return ENFORCED
    return mode_of(root, agent, goal, today)


def mode_text(root, agent: str | None = None, goal: str | None = None, today=None) -> str:
    """The text for the start entry, every goal packet prompt and `goal show`. Never raises: a settings file that
    cannot be read shows as enforced with its reason (no part is enforced yet, so nothing depends on it)."""
    try:
        t = today if isinstance(today, date) else date.fromisoformat(today) if today else date.today()
        return mode_line(*mode_for(read(root, t), agent, goal, t))
    except Exception:
        return "enforcement: enforced (the settings file cannot be read)"


def status_line(root, today=None) -> str:
    """The status line: the mode in force and the plain statement that nothing is enforced yet (design note 6)."""
    return f"{mode_text(root, today=today)}. {TODAY_NOTE[0].upper()}{TODAY_NOTE[1:]}."


def pages_overclaim(root) -> list:
    """W78.R16: the pages that say enforced by default before the build record has the real enforced run."""
    if REAL_ENFORCED_RUN_DONE:
        return []
    found = []
    for rel in CLAIM_PAGES:
        try:
            text = (Path(root) / rel).read_text(encoding="utf-8")
        except OSError:
            continue
        if OVERCLAIM.search(text):
            found.append(rel)
    return found


# ---------------------------------------------------------------- what this machine can enforce


def probe(agent, platform: str | None = None) -> dict:
    """{part: reason or None (ready)} for one agent. B1, B2, the broker, the launcher and detect-after are not built,
    so every part is refused with its honest reason (W78.R14: never `ready` when it is not). Reads nothing."""
    platform = platform or sys.platform
    if not (platform.startswith("linux") or platform == "darwin"):
        return {p: "platform" for p in PARTS}
    return {"environment": "unavailable",
            "confinement": "unavailable" if agent.platform == "claude-code" else "broker",
            "detect-after": "unavailable",
            "network": "network",
            "untrusted-read": "unavailable"}


def check(root, today=None, agents_file=None, probe_fn=None) -> agents.Result:
    """`umwayi enforce check`. Reads only; writes nothing; starts nothing; reads no credential."""
    t = _day(today)
    try:
        settings = read(root, t)
    except ConfigError as e:
        return agents.Result(USAGE, [str(e), refusal("settings file", "fix_file")])
    try:
        listed = agents.load(root, agents_file)
    except (ConfigError, UsageError) as e:
        return agents.Result(USAGE, [str(e), refusal("agents.yaml", "agents")])
    try:
        sync = _file_matches_logbook(root)
    except UmwayiError as e:
        return agents.Result(NO, [str(e), refusal("logbook", "look")])
    lines = [mode_line(*mode_for(settings, None, None, t)), f"{TODAY_NOTE[0].upper()}{TODAY_NOTE[1:]}."]
    code = OK
    if sync is False:
        lines.append(refusal("the settings file does not match the last mode entry of the logbook", "look"))
        code = ASK
    probe_fn = probe_fn or probe
    for a in listed:
        mode, scope, until = mode_for(settings, a.name, None, t)
        lines.append(f"agent {a.name} ({a.platform}): {mode_line(mode, scope, until)}")
        result = probe_fn(a)
        reasons = []
        for part in PARTS:
            r = result.get(part, "unavailable")
            if r is not None and r not in REASONS:
                r = "unavailable"
            lines.append(f"  {part}: " + ("ready" if r is None else f"refused ({r})"))
            if r is not None:
                reasons.append(r)
        if mode == ENFORCED and reasons:
            lines.append(f"  {refusal('not confined (' + reasons[0] + ')', 'switch')}")
            if code == OK:
                code = NO
    lines.append(f"{len(listed)} agent(s) checked. Nothing was started and nothing was written.")
    return agents.Result(code, lines)


# ---------------------------------------------------------------- the switch


def _day(today) -> date:
    if isinstance(today, date):
        return today
    return date.fromisoformat(today) if today else date.today()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _last_logged_sha(root):
    for e in reversed(logbook.read_checked(Path(root))):
        if e.source == SOURCE:
            m = re.search(r"sha256 ([0-9a-f]{64})", e.checked)
            return m.group(1) if m else None
    return None


def _file_matches_logbook(root):
    """True or None (no file: enforced, nothing to match) or False (a file that no umwayi entry explains)."""
    path = Path(root) / FILE_REL
    if not os.path.lexists(path):
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return False
    return _last_logged_sha(root) == _sha(data)


def render(settings: Settings) -> str:
    def block(e, pad):
        out = [f"{pad}enforcement: {e.mode}"]
        if e.mode == COOPERATIVE:
            out.append(f"{pad}until: {e.until}")
        return out
    lines = ["# umwayi enforcement mode (W78). Written by `umwayi enforce set`; the owner switches it at the terminal.",
             *block(settings.base, "")]
    for key, items in (("agents", settings.agents), ("goals", settings.goals)):
        if items:
            lines.append(f"{key}:")
            for name in sorted(items):
                lines += [f"  {name}:", *block(items[name], "    ")]
    return "\n".join(lines) + "\n"


def _typed(prompt="Type the word cooperative to switch enforcement to cooperative: "):
    sys.stdout.write(prompt)
    sys.stdout.flush()
    return sys.stdin.readline().strip()


def set_mode(root, mode, agent=None, goal=None, until=None, today=None, tty=None, confirm=None) -> agents.Result:
    """`umwayi enforce set enforced|cooperative [--agent NAME | --goal ID] [--until DATE]`."""
    root = Path(root)
    t = _day(today)
    if mode not in MODES:
        raise UsageError("enforce set: the mode is enforced or cooperative")
    if agent is not None and goal is not None:
        raise UsageError("enforce set: give --agent or --goal, not both")
    if until is not None and mode == ENFORCED:
        raise UsageError("enforce set: --until is only for cooperative")
    if agent is not None:
        agents.check_name(agent)
        if all(a.name != agent for a in agents.load(root)):
            raise UsageError(f"enforce set: there is no agent named {agent} in agents.yaml")
    if goal is not None:
        if not GOAL_ID.fullmatch(goal):
            raise UsageError("enforce set: a goal id looks like G-0007")
        from umwayi import goalstate
        if goal not in goalstate.list_goals(root):
            raise UsageError(f"enforce set: there is no goal {goal} in this root")
    if mode == COOPERATIVE:
        until = until or (t + timedelta(days=DEFAULT_DAYS)).isoformat()
        d = _real_date(until)
        if d is None:
            raise UsageError("enforce set: --until is a date, YYYY-MM-DD")
        if d < t:
            raise UsageError("enforce set: --until is in the past")
        if d > t + timedelta(days=MAX_DAYS):
            raise UsageError(f"enforce set: cooperative lasts at most {MAX_DAYS} days")
        if tty is None:
            from umwayi import goal as goalmod
            tty = goalmod._is_terminal  # the owner terminal check of the goal commands, unchanged
        if not tty():
            return agents.Result(ASK, ["Ask me first: switching to cooperative is the owner's, at a terminal.",
                                       refusal("not the owner's terminal", "terminal"), "Nothing was changed."])
        if (confirm or _typed)().strip() != CONFIRM_WORD:
            return agents.Result(ASK, ["Ask me first: the typed word was not given.", refusal("no confirmation", "confirm"),
                                       "Nothing was changed."])
    settings = read(root, t)
    new = Entry(COOPERATIVE, until) if mode == COOPERATIVE else Entry(ENFORCED)
    if agent is not None:
        items = dict(settings.agents)
        items.pop(agent, None) if mode == ENFORCED else items.__setitem__(agent, new)
        settings, scope = Settings(settings.base, items, settings.goals), f"agent {agent}"
    elif goal is not None:
        items = dict(settings.goals)
        items.pop(goal, None) if mode == ENFORCED else items.__setitem__(goal, new)
        settings, scope = Settings(settings.base, settings.agents, items), f"goal {goal}"
    else:
        settings, scope = Settings(new, settings.agents, settings.goals), "all"
    data = render(settings).encode("utf-8")
    path = root / FILE_REL
    before = path.read_bytes() if path.is_file() and not path.is_symlink() else None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fsutil.atomic_write(path, data)
        logbook.append(root, logbook.Entry(
            t.isoformat(), SOURCE,
            f"enforcement set to {mode} for {scope}" + (f" until {until}" if mode == COOPERATIVE else ""),
            f"settings file {FILE_REL} sha256 {_sha(data)}; "
            + ("the owner's terminal and the typed word were checked" if mode == COOPERATIVE else "switching to enforced needs no confirmation"),
            "No agent was started. Nothing is enforced yet: the parts of enforced are not built."))
    except Exception:
        try:  # the logbook could not record it, so the file goes back as it was (like turning the kill switch off)
            if before is None:
                path.unlink(missing_ok=True)
            else:
                fsutil.atomic_write(path, before)
        except OSError:
            pass
        raise
    return agents.Result(OK, [f"{mode_line(*mode_for(settings, agent, goal, t))} for {scope}." if mode == COOPERATIVE
                              else f"enforcement: enforced for {scope}.", "One logbook entry was written."])
