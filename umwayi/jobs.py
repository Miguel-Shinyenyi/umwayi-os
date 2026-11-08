"""Layer 6: the schedule runner.

`umwayi run JOBFILE [--job NAME]` runs one job from a jobs file. A job names a
command word from the fixed allow list below. There are no shell strings and
no way to name another program: the command word picks a Python function
inside umwayi.

Order of work for one run:
  0. The kill switch. If it is on, or its state cannot be read, the run stops
     before anything else with exit 3 and one logbook entry.
  1. Read the jobs file strictly. Pick the job.            (error: exit 64)
  2. Read the logbook (tamper checked). Apply the gap rule. (refusal: exit 1)
  3. Ask the rules: action {"type": "run_job", "job": NAME, "command": WORD}.
     No stops the job (exit 2), Ask me first stops it (exit 3). Either way one
     logbook entry says the job was stopped.
  4. Do the work in memory, or write the new draft.         (error: exit 1)
  5. Append one logbook entry. If that fails, the draft is removed, nothing is
     printed and the job counts as not run (Ask me first, exit 3).
  6. Print the result.

Nothing is scheduled by this module. A cron line or similar calls `umwayi run`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from umwayi import kill, logbook, miniyaml, report, rules, taskqueue
from umwayi.errors import ConfigError, UmwayiError, UsageError

ALLOWED_COMMANDS = ("report", "check", "queue-list")
_COMMON = {"name", "command", "min_gap_days"}
_OPTIONS = {"report": {"since_days"}, "check": {"action_type"}, "queue-list": {"status"}}
_REQUIRED = {"report": {"since_days"}, "check": {"action_type"}, "queue-list": set()}
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
_TYPE = re.compile(r"^[A-Za-z0-9_.:-]{1,40}$")
MAX_GAP_DAYS = 366
MAX_SINCE_DAYS = 366
MAX_JOBFILE_BYTES = 64 * 1024


@dataclass(frozen=True)
class Job:
    name: str
    command: str
    min_gap_days: int
    options: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Result:
    code: int
    lines: list


# -------------------------------------------------------------- jobs file


def _int(value, what: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ConfigError(f"jobs file: {what} must be a whole number from {low} to {high}")
    return value


def parse_jobs(text: str) -> list:
    try:
        data = miniyaml.loads(text)
    except miniyaml.YamlError as e:
        raise ConfigError(f"jobs file: {e}") from None
    if not isinstance(data, dict) or set(data) != {"jobs"}:
        raise ConfigError("jobs file: the top level must be a single 'jobs' list")
    items = data["jobs"]
    if not isinstance(items, list) or not items:
        raise ConfigError("jobs file: 'jobs' must be a list with at least one job")
    jobs, seen = [], set()
    for i, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise ConfigError(f"jobs file: job #{i} must be a mapping")
        name = item.get("name")
        if not isinstance(name, str) or not _NAME.match(name):
            raise ConfigError(f"jobs file: job #{i} needs a name of lowercase letters, digits and '-' (up to 40)")
        if name in seen:
            raise ConfigError(f"jobs file: duplicate job name '{name}'")
        seen.add(name)
        command = item.get("command")
        if command not in ALLOWED_COMMANDS:
            raise ConfigError(
                f"jobs file: job '{name}' has a command that is not on the allow list ({', '.join(ALLOWED_COMMANDS)})"
            )
        allowed = _COMMON | _OPTIONS[command]
        if set(item) - allowed:
            raise ConfigError(f"jobs file: job '{name}' has a field that is not allowed for '{command}'")
        missing = (_REQUIRED[command] | {"min_gap_days"}) - set(item)
        if missing:
            raise ConfigError(f"jobs file: job '{name}' is missing: {', '.join(sorted(missing))}")
        gap = _int(item["min_gap_days"], f"min_gap_days of job '{name}'", 1, MAX_GAP_DAYS)
        options: dict = {}
        if command == "report":
            options["since_days"] = _int(item["since_days"], f"since_days of job '{name}'", 1, MAX_SINCE_DAYS)
        elif command == "check":
            t = item["action_type"]
            if not isinstance(t, str) or not _TYPE.match(t):
                raise ConfigError(f"jobs file: action_type of job '{name}' must be one plain word (up to 40)")
            options["action_type"] = t
        elif "status" in item:
            if item["status"] not in taskqueue.STATUSES:
                raise ConfigError(f"jobs file: status of job '{name}' must be one of: {', '.join(taskqueue.STATUSES)}")
            options["status"] = item["status"]
        jobs.append(Job(name, command, gap, options))
    return jobs


def load_jobs(path: Path) -> list:
    path = Path(path)
    if path.is_symlink():
        raise ConfigError("jobs file: must not be a symbolic link")
    if not path.is_file():
        raise ConfigError("jobs file: was not found")
    try:
        data = path.read_bytes()
    except OSError:
        raise ConfigError("jobs file: cannot be read") from None
    if len(data) > MAX_JOBFILE_BYTES:
        raise ConfigError("jobs file: is too large")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ConfigError("jobs file: is not valid UTF-8") from None
    return parse_jobs(text)


def select(jobs: list, name: str | None) -> Job:
    if name is None:
        if len(jobs) != 1:
            raise UsageError(f"the jobs file has {len(jobs)} jobs, choose one with --job NAME")
        return jobs[0]
    for j in jobs:
        if j.name == name:
            return j
    raise UsageError("there is no job with that name in the jobs file")


# ---------------------------------------------------------------- gap rule


_RAN = re.compile(r"^Job ([a-z0-9-]+) ran ")


def last_run(entries: list, name: str) -> str | None:
    """The date of the last 'Job NAME ran' entry from umwayi run, or None."""
    days = [e.date for e in entries if e.source == "umwayi run" and (m := _RAN.match(e.added)) and m.group(1) == name]
    return max(days) if days else None


def days_between(earlier: str, later: str) -> int:
    return date.fromisoformat(later).toordinal() - date.fromisoformat(earlier).toordinal()


# --------------------------------------------------------------------- run


def run(root: Path, jobfile: Path, name: str | None, today: str) -> Result:
    root = Path(root)
    if not taskqueue.is_valid_date(today):
        raise UsageError("run: date must be a real date YYYY-MM-DD")

    # --- 0. the kill switch, before the jobs file is even read
    st = kill.state(root)
    if kill.stopped(st):
        lines = [rules.ASK, "Rule: (none)", f"Reason: {kill.reason(st)}", "The job did not run. Nothing was read."]
        try:
            logbook.append(root, logbook.Entry(
                today, "umwayi run", f"A job run was stopped before the jobs file was read: {kill.short(st)}",
                "the kill switch was checked before anything else",
                "The job did not run. Nothing was read, written, published or pushed."))
        except Exception as e:
            why = str(e).rstrip(". ") if isinstance(e, UmwayiError) else "an unexpected error"
            lines.append(f"The logbook could not be written ({why}). Nothing was logged.")
        return Result(3, lines)

    job = select(load_jobs(jobfile), name)

    # --- 2. the gap rule, from the tamper checked logbook
    try:
        entries = logbook.read_checked(root)
    except UmwayiError as e:
        raise UmwayiError(f"cannot run job '{job.name}': {e} The job did not run.") from None
    last = last_run(entries, job.name)
    if last is not None:
        gap = days_between(last, today)
        if gap < 0:
            raise UmwayiError(f"cannot run job '{job.name}': its last run ({last}) is after today. The job did not run.")
        if gap < job.min_gap_days:
            raise UmwayiError(
                f"job '{job.name}' ran {gap} day(s) ago on {last}; the minimum gap is {job.min_gap_days} day(s). "
                "The job did not run."
            )
    gap_note = f"last run {last}, minimum gap {job.min_gap_days} day(s) kept" if last else "no earlier run"

    # --- 3. the rules
    action = {"type": "run_job", "job": job.name, "command": job.command}
    decision = rules.check(json.dumps(action), root / "rules.yaml")
    checked_base = (
        f"jobs file parsed with no errors; {job.command} is on the allow list; {gap_note}; "
        f"{'rule ' + decision.rule_id if decision.rule_id else 'no rule'} gave {decision.answer} for action type run_job"
    )
    if decision.answer != rules.YES:
        lines = [decision.answer, f"Rule: {decision.rule_id or '(none)'}", f"Reason: {decision.reason}"]
        entry = logbook.Entry(
            date=today,
            source="umwayi run",
            added=f"Job {job.name} stopped before running (command {job.command}): "
            f"{'rule ' + decision.rule_id if decision.rule_id else 'no rule'} gave {decision.answer}",
            checked=checked_base,
            not_done="The job did not run. Nothing was written, published or pushed.",
        )
        try:
            logbook.append(root, entry)
        except Exception as e:
            why = str(e).rstrip(". ") if isinstance(e, UmwayiError) else "an unexpected error"
            lines.append(f"The logbook could not be written ({why}). Nothing was logged.")
        lines.append(f"Job {job.name} did not run.")
        return Result(decision.exit_code, lines)

    # --- 4. do the work
    draft = None
    code = 0
    if job.command == "report":
        since = report.days_before(today, job.options["since_days"])
        rep = report.build(root, since, today)
        draft = report.create_draft(root, rep.text)
        added = f"Job {job.name} ran (command report): wrote {draft.rel} with {len(rep.commits)} commits from {since} to {today}"
        output = [f"Job {job.name} ran.", f"Wrote {draft.rel} ({len(rep.commits)} commits from {since} to {today})."]
        not_done = "Nothing was published or pushed. No shell, no network and no git command that writes were used."
    elif job.command == "queue-list":
        status = job.options.get("status")
        rows = taskqueue.list_rows(root, status=status)
        added = f"Job {job.name} ran (command queue-list): listed {len(rows)} rows" + (f" with status {status}" if status else "")
        output = [f"Job {job.name} ran.", f"{len(rows)} rows" + (f" with status {status}:" if status else ":")]
        output += [f"{r.id}  {r.kind:<8}  {r.status:<8}  {r.title}" for r in rows]
        not_done = "queue.md was only read, nothing was changed. No shell and no network were used."
    else:  # check
        t = job.options["action_type"]
        inner = rules.check(json.dumps({"type": t}), root / "rules.yaml")
        code = inner.exit_code
        added = (
            f"Job {job.name} ran (command check): "
            f"{'rule ' + inner.rule_id if inner.rule_id else 'no rule'} gave {inner.answer} for action type {t}"
        )
        output = [f"Job {job.name} ran.", inner.answer, f"Rule: {inner.rule_id or '(none)'}", f"Reason: {inner.reason}"]
        not_done = "The checked action was not run. No shell and no network were used."

    # --- 5. one logbook entry; if it fails the job counts as not run
    entry = logbook.Entry(date=today, source="umwayi run", added=added, checked=checked_base, not_done=not_done)
    try:
        logbook.append(root, entry)
    except Exception as e:
        why = str(e).rstrip(". ") if isinstance(e, UmwayiError) else "an unexpected error"
        if draft is not None:
            try:
                report.remove_draft(root, draft)
            except OSError:
                raise UmwayiError(f"the logbook write failed AND {draft.rel} could not be removed, delete it by hand") from None
        return Result(3, [
            rules.ASK,
            "Rule: (none)",
            f"Reason: The logbook could not be written ({why}). Nothing was logged, so job {job.name} did not run.",
        ])
    return Result(code, output)
