"""Layer 11: scheduled runs through systemd user timers (requirements 11.R1 to 11.R7, design.md "Layer 11").

`schedule.yaml` lists entries; each runs one existing umwayi front door (`umwayi run JOBS --job JOB` or
`umwayi workflow run NAME`) daily, weekly or monthly at a fixed local time. This module:

  * reads and checks the file (11.R1), with line numbers;
  * renders one systemd user service and one timer per entry from fixed templates (11.R2), and a crontab line
    that is only printed;
  * installs and removes the two unit files through the kill switch, the rules, the run lock and the logbook
    (11.R4), and compares installed files with what it would write (11.R3).

It never runs systemctl, crontab, loginctl or any other program: it imports no program runner. It prints the
`systemctl --user` commands for the owner to type. What a timer starts is an existing front door, which checks
the kill switch, the run lock, the rules and the logbook itself (layers 6 and 8); nothing new can run.

Every path written into a unit file or a cron line obeys the path rule (letters, digits and / . _ + - only), so
no quoting, no systemd specifier (%) and no variable expansion ($) is ever needed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from umwayi import agents, jobs, kill, logbook, miniyaml, rules, runlock, taskqueue, workflow
from umwayi.errors import ConfigError, UmwayiError, UsageError
from umwayi.fsutil import fsync_dir

SCHEDULE_FILE = "schedule.yaml"
MAX_FILE_BYTES = 64 * 1024
MAX_ENTRIES = 20
MAX_PATH = 1024
MAX_BY = 100
SOURCE = "umwayi schedule"
UNIT_PREFIX = "umwayi"
START_LIMIT = "30min"  # L11-Q7
STOP_LIMIT = "15s"
RUNS = ("job", "workflow")  # L11-Q5: never an agent
EVERY_DAYS = {"daily": 1, "weekly": 7, "monthly": 28}
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
KEYS_JOB = {"name", "run", "job", "jobs_file", "every", "at", "day"}
KEYS_WORKFLOW = {"name", "run", "workflow", "every", "at", "day"}
DEFAULT_JOBS_FILE = "jobs.yaml"
INSTALL_ACTION = "schedule_install"
REMOVE_ACTION = "schedule_remove"
INSTALL_ASK_TITLE = "Install schedule {name}?"
REMOVE_ASK_TITLE = "Remove schedule {name}?"
INSTALL_ASK_RECOMMENDATION = ("Install it only if you want this job or workflow to run on its own. To allow it, run "
                              "umwayi schedule install NAME --approved-by YOUR_NAME, or add a Yes rule for "
                              "schedule_install.")
REMOVE_ASK_RECOMMENDATION = "Remove it if this schedule should no longer run. Add a Yes rule for schedule_remove."
LINGER_LINE = ("Timers run only while you are logged in, unless you enable lingering yourself (loginctl enable-linger); "
               "umwayi never does.")

_NAME = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
_AT = re.compile(r"^([01][0-9]|2[0-3]):([0-5][0-9])$")
_SAFE_PATH = re.compile(r"^/[A-Za-z0-9/._+-]*$")
_PLAIN_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,39}$")
_UNIT = re.compile(r"^umwayi-([0-9a-f]{8})-([a-z][a-z0-9-]{0,31})\.(service|timer)$")


@dataclass(frozen=True)
class Problem:
    where: str  # "line 3", "path" or "file"
    message: str

    def render(self) -> str:
        return f"{self.where}: {self.message}"


@dataclass(frozen=True)
class Entry:
    name: str
    run: str  # job or workflow
    target: str  # the job name or the workflow name
    jobs_file: str | None  # relative to the root, for run: job
    every: str
    at: str  # HH:MM
    day: object  # a weekday word, a day of month, or None
    line: int


@dataclass(frozen=True)
class Result:
    code: int
    lines: list


@dataclass(frozen=True)
class Paths:
    """Every path that goes into a unit file or a cron line, each a real path that obeys the path rule."""
    root: str
    schedule_file: str
    python: str
    src: str


# ------------------------------------------------------------------ the file


def schedule_path(root: Path, given: str | None) -> Path:
    return Path(given) if given else Path(root) / SCHEDULE_FILE


def read_file(path: Path, root: Path) -> str:
    """The text of the schedule file. Missing, a link, outside the root, too big, not UTF-8: a config error (64)."""
    shown = path.name if path.name.isprintable() else "the schedule file"
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        raise ConfigError(f"schedule: {shown} was not found") from None
    except OSError:
        raise ConfigError(f"schedule: {shown} cannot be read") from None
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise ConfigError(f"schedule: {shown} must be a regular file, not a link or a folder")
    real_root = os.path.realpath(root)
    if not _inside(os.path.realpath(path), real_root):
        raise ConfigError(f"schedule: {shown} must be inside the umwayi root")
    if st.st_size > MAX_FILE_BYTES:
        raise ConfigError(f"schedule: {shown} is larger than {MAX_FILE_BYTES} bytes")
    try:
        data = path.read_bytes()
    except OSError:
        raise ConfigError(f"schedule: {shown} cannot be read") from None
    if len(data) > MAX_FILE_BYTES:
        raise ConfigError(f"schedule: {shown} is larger than {MAX_FILE_BYTES} bytes")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise ConfigError(f"schedule: {shown} is not valid UTF-8") from None


def _inside(child: str, parent: str) -> bool:
    return child == parent or child.startswith(parent.rstrip("/") + "/")


def _line_map(text: str) -> dict:
    """Where the top key, each entry and each entry key is, as 1-based line numbers (after miniyaml accepted it)."""
    toks = miniyaml._tokenize(text)
    found: dict = {}
    if not toks:
        return found
    top = toks[0][0]
    i = 0
    while i < len(toks):
        ind, t, n = toks[i]
        kv = miniyaml._split_key(t) if ind == top and not miniyaml._is_item(t) else None
        if kv is None:
            i += 1
            continue
        found[(kv[0],)] = n
        i += 1
        if kv[0] != "schedules":
            continue
        idx, item_ind = 0, None
        while i < len(toks) and (toks[i][0] > top or (toks[i][0] == top and miniyaml._is_item(toks[i][1]))):
            jind, jt, jn = toks[i]
            if miniyaml._is_item(jt) and (item_ind is None or jind == item_ind):
                item_ind = jind
                idx += 1
                found[("schedules", idx)] = jn
                rest = jt[1:].strip()
                kv2 = miniyaml._split_key(rest) if rest else None
                if kv2:
                    found[("schedules", idx, kv2[0])] = jn
            elif idx:
                kv2 = miniyaml._split_key(jt)
                if kv2 and jind > item_ind:
                    found.setdefault(("schedules", idx, kv2[0]), jn)
            i += 1
    return found


def _key_text(key) -> str:
    return f"'{key}'" if isinstance(key, str) and _PLAIN_KEY.match(key) else "a key"


def _jobs_file_problem(value, root_real: str) -> str | None:
    if not isinstance(value, str) or not value or len(value) > MAX_PATH or not value.isprintable():
        return "jobs_file must be a relative path to the jobs file inside the root"
    if value.startswith("/") or "\\" in value or ".." in PurePosixPath(value).parts:
        return "jobs_file must be a relative path inside the root, with no '..'"
    if not _inside(os.path.realpath(os.path.join(root_real, value)), root_real):
        return "jobs_file must stay inside the root"
    return None


def check_text(text: str, root: Path) -> tuple:
    """(entries, problems). Every problem has a line number; all problems are found at once (11.R1)."""
    root_real = os.path.realpath(root)
    try:
        data = miniyaml.loads(text)
    except miniyaml.YamlError as e:
        return [], [Problem("file", f"not valid YAML for umwayi ({e})")]
    lines = _line_map(text)
    problems: list = []

    def line(*key) -> int:
        while key and key not in lines:
            key = key[:-1]
        return lines.get(key, 1)

    def problem(message: str, *key) -> None:
        problems.append(Problem(f"line {line(*key)}", message))

    if not isinstance(data, dict) or set(data) != {"schedules"}:
        problem("the file must have exactly one top key, 'schedules', holding a list")
        return [], problems
    items = data["schedules"]
    if not isinstance(items, list) or not items:
        problem("'schedules' must be a list with at least one entry", "schedules")
        return [], problems
    if len(items) > MAX_ENTRIES:
        problem(f"at most {MAX_ENTRIES} entries are allowed", "schedules")
    entries, seen = [], set()
    for i, item in enumerate(items, 1):
        here = ("schedules", i)
        if not isinstance(item, dict):
            problem("each entry must be a mapping of keys", *here)
            continue
        found = len(problems)
        name = item.get("name")
        if not isinstance(name, str) or not _NAME.match(name):
            problem("name must be a lowercase letter, then lowercase letters, digits and '-' (up to 32)", *here, "name")
            name = None
        elif name in seen:
            problem("this name is already used by an earlier entry", *here, "name")
        else:
            seen.add(name)
        run = item.get("run")
        if run not in RUNS:
            problem("run must be job or workflow (an agent cannot be scheduled)", *here, "run")
            run = None
        allowed = KEYS_JOB if run == "job" else KEYS_WORKFLOW if run == "workflow" else KEYS_JOB | KEYS_WORKFLOW
        for key in item:
            if key not in allowed:
                problem(f"{_key_text(key)} is not allowed in an entry" + (f" with run: {run}" if run else ""),
                        *here, key)
        for key in ("name", "run", "every", "at") + (("job",) if run == "job" else ("workflow",) if run else ()):
            if key not in item:
                problem(f"'{key}' is missing", *here)
        every = item.get("every")
        if "every" in item and every not in EVERY_DAYS:
            problem("every must be daily, weekly or monthly", *here, "every")
            every = None
        at = item.get("at")
        if "at" in item and not (isinstance(at, str) and _AT.match(at)):
            problem("at must be a local time HH:MM from 00:00 to 23:59, written in quotes", *here, "at")
            at = None
        day = item.get("day")
        if every == "daily" and "day" in item:
            problem("day is not used with every: daily", *here, "day")
        elif every == "weekly" and day not in WEEKDAYS:
            problem("a weekly entry needs day: one of mon, tue, wed, thu, fri, sat, sun", *here, "day" if "day" in item else "every")
        elif every == "monthly" and not (isinstance(day, int) and not isinstance(day, bool) and 1 <= day <= 28):
            problem("a monthly entry needs day: a day of the month from 1 to 28", *here, "day" if "day" in item else "every")
        target = jobs_file = None
        if run == "job" and "job" in item:
            target = item["job"]
            jobs_file = item.get("jobs_file", DEFAULT_JOBS_FILE)
            why = _jobs_file_problem(jobs_file, root_real)
            if why:
                problem(why, *here, "jobs_file")
            elif not (isinstance(target, str) and jobs._NAME.match(target)):
                problem("job must be a job name from the jobs file", *here, "job")
            else:
                try:
                    found_jobs = jobs.load_jobs(Path(root_real) / jobs_file)
                except UsageError:
                    problem("the jobs file is missing or not valid; check it with umwayi run", *here, "jobs_file")
                else:
                    job = next((j for j in found_jobs if j.name == target), None)
                    if job is None:
                        problem("there is no job with this name in the jobs file", *here, "job")
                    elif every in EVERY_DAYS and job.min_gap_days > EVERY_DAYS[every]:
                        problem(f"the job's min_gap_days ({job.min_gap_days}) is longer than the {every} period "
                                f"({EVERY_DAYS[every]} days), so most runs would be refused", *here, "every")
        elif run == "workflow" and "workflow" in item:
            target = item["workflow"]
            try:
                workflow.check_name(target if isinstance(target, str) else "")
                workflow.load(Path(root_real), target)
            except UsageError:
                problem("there is no valid workflow with this name in workflows/ (check it with umwayi workflow "
                        "validate)", *here, "workflow")
        if len(problems) == found and name and run and every and at and target:
            entries.append(Entry(name, run, target, jobs_file, every, at, day if every != "daily" else None,
                                 line(*here)))
    return entries, problems


def path_problems(paths: Paths) -> list:
    """The path rule (11.R1.4), one problem per path that breaks it. The message never holds the path's text."""
    out = []
    for role, value in (("the root path", paths.root), ("the schedule file path", paths.schedule_file),
                        ("the path of the Python running umwayi", paths.python),
                        ("the umwayi source folder path", paths.src)):
        if not _safe_path(value):
            out.append(Problem("path", f"{role} has a character a unit file cannot hold safely (allowed: letters, "
                                       "digits, / . _ + -), or a '.' or '..' part, or is longer than 1024 characters. "
                                       "Move it and try again."))
    return out


def _safe_path(value: str) -> bool:
    if not isinstance(value, str) or len(value) > MAX_PATH or not _SAFE_PATH.match(value):
        return False
    return not any(part in (".", "..") for part in value.split("/")[1:])


def current_paths(root: Path, file_path: Path) -> Paths:
    return Paths(os.path.realpath(root), os.path.realpath(file_path), os.path.realpath(sys.executable),
                 os.path.realpath(agents.umwayi_src()))


def load(root: Path, given: str | None = None) -> tuple:
    """(entries, paths) of a valid schedule file whose paths obey the path rule, or a config error (64)."""
    root = Path(root)
    path = schedule_path(root, given)
    entries, problems = check_text(read_file(path, root), root)
    paths = current_paths(root, path)
    problems = problems + path_problems(paths)
    if problems:
        raise ConfigError(f"schedule: {len(problems)} problem(s) found, see 'umwayi schedule validate'. "
                          "Nothing was changed.")
    return entries, paths


def find(entries: list, name: str) -> Entry:
    if not isinstance(name, str) or not _NAME.match(name):
        raise UsageError("schedule: the name must be a lowercase letter, then lowercase letters, digits and '-' "
                         "(up to 32)")
    for e in entries:
        if e.name == name:
            return e
    raise UsageError(f"schedule: there is no entry {name} in the schedule file")


def validate_file(root, given: str | None = None) -> Result:
    """`umwayi schedule validate`: 0 when valid, 64 with every problem otherwise. Writes nothing."""
    root = Path(root)
    path = schedule_path(root, given)
    entries, problems = check_text(read_file(path, root), root)
    problems = problems + path_problems(current_paths(root, path))
    if problems:
        lines = [f"problem: {p.render()}" for p in problems]
        return Result(64, lines + [f"{len(problems)} problem(s) found in {path.name}"])
    return Result(0, [f"ok: {len(entries)} schedule(s): " + ", ".join(f"{e.name} ({e.run} {e.target}, {e.every})"
                                                                       for e in entries)])


# ------------------------------------------------------------------ rendering


def root_id(root_real: str) -> str:
    return hashlib.sha256(root_real.encode("utf-8")).hexdigest()[:8]


def unit_base(paths: Paths, entry: Entry) -> str:
    return f"{UNIT_PREFIX}-{root_id(paths.root)}-{entry.name}"


def calendar(entry: Entry) -> str:
    """The OnCalendar= value, in the normal forms of systemd.time(7)."""
    hm = f"{entry.at}:00"
    if entry.every == "daily":
        return f"*-*-* {hm}"
    if entry.every == "weekly":
        return f"{entry.day.capitalize()} *-*-* {hm}"
    return f"*-*-{entry.day:02d} {hm}"


def _command(paths: Paths, entry: Entry) -> str:
    """The one front door the service runs (11.R2.2). Never a shell, never an agent."""
    if entry.run == "job":
        jobs_path = os.path.realpath(os.path.join(paths.root, entry.jobs_file))
        if not _safe_path(jobs_path):
            raise ConfigError("schedule: the jobs file path has a character a unit file cannot hold safely (allowed: "
                              "letters, digits, / . _ + -). Move it and try again.")
        return f"{paths.python} -m umwayi --root {paths.root} run {jobs_path} --job {entry.target}"
    if entry.run == "workflow":
        return f"{paths.python} -m umwayi --root {paths.root} workflow run {entry.target}"
    raise ConfigError("schedule: only a job or a workflow can be scheduled")


def _header(paths: Paths, entry: Entry) -> str:
    return (f"# Written by umwayi schedule install for the entry {entry.name} of {paths.schedule_file}.\n"
            "# umwayi schedule check compares this file byte for byte: change the schedule file, not this file.\n")


def render(paths: Paths, entry: Entry) -> tuple:
    """(service text, timer text): the exact bytes of design.md, layer 11. Deterministic."""
    base = unit_base(paths, entry)
    service = (
        _header(paths, entry)
        + "[Unit]\n"
        + f"Description=umwayi scheduled run {entry.name} ({paths.root})\n"
        + "\n[Service]\n"
        + "Type=oneshot\n"
        + f"WorkingDirectory={paths.root}\n"
        + f"Environment=PYTHONPATH={paths.src}\n"
        + f"ExecStart={_command(paths, entry)}\n"
        + f"TimeoutStartSec={START_LIMIT}\n"
        + f"TimeoutStopSec={STOP_LIMIT}\n"
        + "KillMode=control-group\n"
    )
    timer = (
        _header(paths, entry)
        + "[Unit]\n"
        + f"Description=umwayi schedule {entry.name} ({paths.root})\n"
        + "\n[Timer]\n"
        + f"OnCalendar={calendar(entry)}\n"
        + "Persistent=true\n"
        + f"Unit={base}.service\n"
        + "\n[Install]\n"
        + "WantedBy=timers.target\n"
    )
    return service, timer


def cron_line(paths: Paths, entry: Entry) -> str:
    """The equivalent crontab line, printed only (L11-Q2). umwayi never installs a crontab."""
    hh, mm = entry.at.split(":")
    fields = {"daily": f"{int(mm)} {int(hh)} * * *",
              "weekly": f"{int(mm)} {int(hh)} * * {WEEKDAYS.index(entry.day) + 1 if entry.day else 0}",
              "monthly": f"{int(mm)} {int(hh)} {entry.day} * *"}[entry.every]
    return (f"# umwayi schedule {entry.name}: the same run as the timer {unit_base(paths, entry)}.timer. "
            "umwayi never installs a crontab.\n"
            f"{fields} /usr/bin/env PYTHONPATH={paths.src} {_command(paths, entry)}\n")


# ------------------------------------------------------------------ the unit folder


def unit_dir(environ=None) -> Path:
    """$XDG_CONFIG_HOME/systemd/user, or $HOME/.config/systemd/user (the user unit load path)."""
    environ = os.environ if environ is None else environ
    xdg = environ.get("XDG_CONFIG_HOME")
    if isinstance(xdg, str) and xdg.startswith("/"):
        return Path(xdg) / "systemd" / "user"
    home = environ.get("HOME")
    if not (isinstance(home, str) and home.startswith("/")):
        raise UmwayiError("schedule: HOME is not set to an absolute path, so the systemd user unit folder is not "
                          "known. Nothing was changed.")
    return Path(home) / ".config" / "systemd" / "user"


def _folder_state(folder: Path) -> str:
    """missing, ok, or bad (a link, a file, unreadable)."""
    try:
        st = os.lstat(folder)
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "bad"
    return "ok" if stat.S_ISDIR(st.st_mode) else "bad"


def _file_state(path: Path, want: bytes) -> str:
    """missing, same, changed, or not_regular."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "not_regular"
    if not stat.S_ISREG(st.st_mode):
        return "not_regular"
    try:
        with open(path, "rb") as f:
            have = f.read(len(want) + 1)
    except OSError:
        return "not_regular"
    return "same" if have == want else "changed"


def _drop_ins(folder: Path, base: str) -> list:
    return [f"{base}.{kind}.d" for kind in ("service", "timer") if os.path.lexists(folder / f"{base}.{kind}.d")]


def _enable_link(folder: Path, base: str) -> Path:
    return folder / "timers.target.wants" / f"{base}.timer"


def commands_to_enable(base: str) -> list:
    return ["To start it, run:", "  systemctl --user daemon-reload", f"  systemctl --user enable --now {base}.timer",
            LINGER_LINE]


# ------------------------------------------------------------------ show and check


def show(root, name: str | None = None, cron: bool = False, given: str | None = None) -> Result:
    """`umwayi schedule show`: what install would write, and where. Writes nothing."""
    entries, paths = load(root, given)
    chosen = [find(entries, name)] if name is not None else entries
    lines: list = []
    if cron:
        for e in chosen:
            lines.append(cron_line(paths, e).rstrip("\n"))
        return Result(0, lines)
    folder = unit_dir()
    for e in chosen:
        base = unit_base(paths, e)
        service, timer = render(paths, e)
        lines.append(f"Schedule {e.name}: {base}.service and {base}.timer in {folder}")
        lines.append(f"--- {folder / (base + '.service')}")
        lines.append(service.rstrip("\n"))
        lines.append(f"--- {folder / (base + '.timer')}")
        lines.append(timer.rstrip("\n"))
    return Result(0, lines)


def check(root, name: str | None = None, given: str | None = None) -> Result:
    """`umwayi schedule check`: installed files against what umwayi would write. 0 only when all match. Writes nothing."""
    entries, paths = load(root, given)
    chosen = [find(entries, name)] if name is not None else entries
    folder = unit_dir()
    fs = _folder_state(folder)
    if fs == "bad":
        return Result(2, [f"The unit folder {folder} is not a normal folder (a link or a file), so nothing can be "
                          "checked."])
    lines, good = [], True
    for e in chosen:
        base = unit_base(paths, e)
        service, timer = render(paths, e)
        states = {"service": _file_state(folder / f"{base}.service", service.encode("utf-8")),
                  "timer": _file_state(folder / f"{base}.timer", timer.encode("utf-8"))}
        drops = _drop_ins(folder, base) if fs == "ok" else []
        enabled = fs == "ok" and os.path.lexists(_enable_link(folder, base))
        if set(states.values()) == {"missing"}:
            what = "not installed"
        elif set(states.values()) == {"same"}:
            what = "installed"
        else:
            parts = [f"the {k} is {'not installed' if v == 'missing' else 'changed by hand' if v == 'changed' else 'not a regular file' if v == 'not_regular' else 'as umwayi wrote it'}"
                     for k, v in states.items()]
            what = "partly installed or changed: " + "; ".join(parts)
        extra = [f"drop-in {d} next to it can override it" for d in drops]
        extra.append("enabled" if enabled else "not enabled")
        lines.append(f"{e.name} ({base}): {what}; " + "; ".join(extra))
        if what != "installed" or drops:
            good = False
    if name is None and fs == "ok":
        names = {e.name for e in entries}
        rid = root_id(paths.root)
        for f in sorted(os.listdir(folder)):
            m = _UNIT.match(f)
            if m and m.group(1) == rid and m.group(2) not in names:
                lines.append(f"left over: {f} (no entry in the schedule file)")
                good = False
    lines.append("All schedules are installed as umwayi wrote them." if good else
                 "Not every schedule is installed as umwayi wrote it (exit 2).")
    return Result(0 if good else 2, lines)


# ------------------------------------------------------------------ install and remove


def _check_by(approved_by: str | None) -> str | None:
    if approved_by is None:
        return None
    approved_by = approved_by.strip()
    if not approved_by or len(approved_by) > MAX_BY or not approved_by.isprintable():
        raise UsageError(f"schedule: --approved-by must be one short line of plain text (1 to {MAX_BY} characters)")
    return approved_by


def _log(root: Path, today: str, added: str, checked: str, not_done: str) -> str | None:
    """One entry. None, or why it could not be written."""
    try:
        logbook.append(root, logbook.Entry(today, SOURCE, added, checked, not_done))
    except UmwayiError as e:
        return str(e).rstrip(". ")
    return None


def _with_why(code: int, lines: list, why: str | None) -> Result:
    if why is not None:
        lines = lines + [f"The logbook could not be written ({why}). Nothing was logged."]
    return Result(code, lines)


def _ask_rules(root: Path, today: str, action: dict, title: str, recommendation: str,
               approved_by: str | None) -> tuple:
    """(decision, stop Result or None). Every check is one `umwayi check` entry (rules.check_and_log)."""
    decision, logged = rules.check_and_log(json.dumps(action), Path(root) / "rules.yaml", Path(root), today)
    verdict = [decision.answer, f"Rule: {decision.rule_id or '(none)'}", f"Reason: {decision.reason}"]
    if not logged:
        return decision, Result(2, verdict + ["The logbook could not record the check, so nothing was changed (exit 2)."])
    if decision.answer == rules.NO:
        return decision, Result(2, verdict + ["Nothing was changed."])
    if decision.answer == rules.ASK and approved_by is None:
        try:
            row, added = taskqueue.add_once(root, "decision", title, recommendation, today)
            note = (f"Added queue item {row.id} (decision) for the owner." if added else
                    f"Queue item {row.id} already asks the owner about this. Nothing was added.")
        except UmwayiError as e:
            note = f"The queue item could not be added ({str(e).rstrip('. ')})."
        return decision, Result(3, verdict + ["Nothing was changed.", note])
    if decision.answer not in (rules.YES, rules.ASK):
        return decision, Result(2, verdict + ["Nothing was changed."])
    return decision, None


def _create(path: Path, data: bytes) -> None:
    """A new regular file with exactly these bytes, mode 0644. Never overwrites, never follows a link."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
    try:
        os.fchmod(fd, 0o644)
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)


def _unlink(path: Path) -> bool:
    try:
        os.unlink(path)
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


def install(root, name: str, today: str, approved_by: str | None = None, given: str | None = None) -> Result:
    """`umwayi schedule install NAME` (11.R4.1). 0, 2, 3 or 64. Writes two unit files and starts nothing."""
    root = Path(root)
    approved_by = _check_by(approved_by)
    entries, paths = load(root, given)
    entry = find(entries, name)
    base = unit_base(paths, entry)
    service, timer = (t.encode("utf-8") for t in render(paths, entry))
    folder = unit_dir()
    files = [(folder / f"{base}.service", service), (folder / f"{base}.timer", timer)]
    paths_text = [f"  {p}" for p, _ in files]

    # already installed, byte for byte: nothing to ask, nothing to write
    if _folder_state(folder) == "ok" and all(_file_state(p, d) == "same" for p, d in files):
        return Result(0, [f"Schedule {entry.name} is already installed. Nothing was changed."] + paths_text
                      + commands_to_enable(base))

    not_done = "Nothing was written to the unit folder."
    # the kill switch first
    st = kill.state(root)
    if kill.stopped(st):
        why = _log(root, today, f"Schedule {entry.name} was not installed: {kill.short(st)}",
                   "the kill switch was checked before anything else", not_done)
        return _with_why(3, [rules.ASK, "Rule: (none)", f"Reason: {kill.reason(st)}",
                             f"Schedule {entry.name} was not installed."], why)

    # the rules
    action = {"type": INSTALL_ACTION, "schedule": entry.name, "run": entry.run, "target": entry.target,
              "every": entry.every}
    decision, stop = _ask_rules(root, today, action, INSTALL_ASK_TITLE.format(name=entry.name),
                                INSTALL_ASK_RECOMMENDATION, approved_by)
    if stop is not None:
        return stop

    # the run lock, held to the end
    try:
        with runlock.held(root):
            return _install_locked(root, today, entry, base, folder, files, paths_text, decision, approved_by)
    except (runlock.RunLockBusy, runlock.RunLockUnavailable) as e:
        busy = isinstance(e, runlock.RunLockBusy)
        reason = runlock.BUSY_REASON if busy else runlock.unavailable_reason(e)
        short = "another umwayi run holds the run lock" if busy else "the run lock could not be taken"
        why = _log(root, today, f"Schedule {entry.name} was not installed: {short}",
                   "the kill switch, the rules, then the run lock", not_done)
        return _with_why(3, [rules.ASK, "Rule: (none)", f"Reason: {reason}",
                             f"Schedule {entry.name} was not installed."], why)


def _install_locked(root, today, entry, base, folder, files, paths_text, decision, approved_by) -> Result:
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        raise UmwayiError(f"schedule: the unit folder {folder} could not be made. Nothing was written.") from None
    if _folder_state(folder) != "ok":
        raise UmwayiError(f"schedule: the unit folder {folder} is not a normal folder (a link or a file). Nothing was "
                          "written.")
    for p, d in files:
        state = _file_state(p, d)
        if state not in ("missing", "same"):
            raise UmwayiError(f"schedule: {p.name} is already in the unit folder and is not what umwayi would write. "
                              "It is never overwritten; remove it by hand if it is not wanted. Nothing was written.")
    created = []
    try:
        for p, d in files:
            if _file_state(p, d) == "same":
                continue  # an identical file from an earlier, interrupted install is kept as it is
            _create(p, d)
            created.append(p)
        fsync_dir(folder)
    except BaseException:
        for p in reversed(created):
            _unlink(p)
        if created:
            try:
                fsync_dir(folder)
            except OSError:
                pass
        raise
    how = (f"rule {decision.rule_id or '(none)'} gave {decision.answer}"
           + (f", approved by {approved_by}" if decision.answer == rules.ASK else ""))
    hashes = " and ".join(f"{p.name} SHA-256 {hashlib.sha256(d).hexdigest()}" for p, d in files)
    try:
        why = _log(root, today,
                   f"Installed schedule {entry.name} ({entry.run} {entry.target}, {entry.every}): {base}.service and "
                   f"{base}.timer in {folder}",
                   f"the kill switch was off; {how}; the run lock was held; {hashes}",
                   "Nothing was started: the owner enables the timer with systemctl --user.")
    except BaseException:
        for p in reversed(created):
            _unlink(p)
        raise
    if why is not None:
        removed = all(_unlink(p) for p in reversed(created))
        lines = [f"The logbook could not record the install ({why}), so the files were removed (exit 2)."]
        if not removed:
            lines.append("Some of the files could not be removed; run umwayi schedule check and remove them by hand.")
        return Result(2, lines)
    lines = [f"Installed schedule {entry.name}:"] + paths_text
    if decision.answer == rules.ASK:
        lines.append(f"Approved by: {approved_by}")
    lines.append("umwayi does not start it.")
    return Result(0, lines + commands_to_enable(base))


def remove(root, name: str, today: str, given: str | None = None) -> Result:
    """`umwayi schedule remove NAME` (11.R4.2). 0, 2, 3 or 64. Not stopped by the kill switch, no run lock."""
    root = Path(root)
    entries, paths = load(root, given)
    entry = find(entries, name)
    base = unit_base(paths, entry)
    service, timer = (t.encode("utf-8") for t in render(paths, entry))
    folder = unit_dir()
    files = [(folder / f"{base}.timer", timer), (folder / f"{base}.service", service)]  # the timer goes first
    fs = _folder_state(folder)
    if fs == "bad":
        return Result(2, [f"The unit folder {folder} is not a normal folder (a link or a file). Nothing was removed."])
    states = {p: _file_state(p, d) for p, d in files} if fs == "ok" else {p: "missing" for p, _ in files}
    if set(states.values()) == {"missing"} and not (fs == "ok" and _drop_ins(folder, base)):
        return Result(0, [f"Schedule {entry.name} is not installed. Nothing was changed."])
    if os.path.lexists(_enable_link(folder, base)):
        return Result(2, [f"Schedule {entry.name} is enabled. Run these first, then try again:",
                          f"  systemctl --user disable --now {base}.timer",
                          f"  systemctl --user clean --what=state {base}.timer", "Nothing was removed."])
    drops = _drop_ins(folder, base)
    bad = [p.name for p, s in states.items() if s in ("changed", "not_regular")]
    if drops or bad:
        what = "; ".join([f"{d} is a drop-in" for d in drops] + [f"{b} is not what umwayi wrote" for b in bad])
        return Result(2, [f"Schedule {entry.name} was not removed: {what}. Remove it by hand.", "Nothing was removed."])

    action = {"type": REMOVE_ACTION, "schedule": entry.name}
    decision, stop = _ask_rules(root, today, action, REMOVE_ASK_TITLE.format(name=entry.name),
                                REMOVE_ASK_RECOMMENDATION, None)
    if stop is not None:
        return stop

    present = [(p, d) for p, d in files if states[p] == "same"]
    removed = []
    try:
        for p, d in present:
            os.unlink(p)
            removed.append((p, d))
        fsync_dir(folder)
    except BaseException:
        _put_back(folder, removed)
        raise
    why = _log(root, today, f"Removed schedule {entry.name}: {', '.join(p.name for p, _ in present)} from {folder}",
               f"rule {decision.rule_id or '(none)'} gave {decision.answer}; the timer was not enabled; every file was "
               "exactly what umwayi writes",
               "The owner runs systemctl --user daemon-reload. Nothing else was changed.")
    if why is not None:
        back = _put_back(folder, removed)
        lines = [f"The logbook could not record the removal ({why}), so the files were put back (exit 2)."]
        if not back:
            lines.append("Some of the files could not be put back; run umwayi schedule show and check.")
        return Result(2, lines)
    return Result(0, [f"Removed schedule {entry.name}:"] + [f"  {p}" for p, _ in present]
                  + ["Now run:", "  systemctl --user daemon-reload"])


def _put_back(folder: Path, removed: list) -> bool:
    ok = True
    for p, d in reversed(removed):
        try:
            _create(p, d)
        except OSError:
            ok = False
    try:
        fsync_dir(folder)
    except OSError:
        pass
    return ok
