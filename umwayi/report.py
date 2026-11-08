"""Layer 6: weekly progress report from git history.

Reads git history through ONE fixed `git log` command (a list of arguments,
never a shell string), counts commits per day, lists subjects, and writes a
new numbered draft under drafts/. It never overwrites a file, never runs a git
command that writes, and never uses the network. Author names and emails are
never read: the format asks git only for the date and the subject.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from umwayi import drafts, logbook
from umwayi.errors import UmwayiError
from umwayi.taskqueue import is_valid_date

DRAFTS_DIR = drafts.DRAFTS_DIR
GIT_TIMEOUT_SECONDS = 30
MAX_SUBJECT = 200
MAX_COMMITS = 50000  # git is asked for one more; reaching it is a refusal, never a silent cut

# The one git command this tool runs. "-C <root>" goes after "git"; nothing else changes.
# There is no --since: git stops walking at the first commit older than the
# date, so a commit with an older date on top would hide newer ones. The days
# are filtered here instead.
#   --no-pager, core.pager=cat     never start a pager
#   core.fsmonitor=false           never start a file system monitor program
#   log.showSignature=false        never start gpg
#   --no-merges                    merge commits are left out
#   --date=short-local, %cd        committer date as YYYY-MM-DD in local time
#   %x1f                           a separator that cannot appear in a subject
GIT_LOG_ARGS = (
    "--no-pager",
    "-c", "core.pager=cat",
    "-c", "core.fsmonitor=false",
    "-c", "log.showSignature=false",
    "log",
    "--no-merges",
    "--no-color",
    "--date=short-local",
    "--format=%cd%x1f%s",
    f"--max-count={MAX_COMMITS + 1}",
)

_EMAIL = re.compile(r"[^\s@<>()\[\]]+@[^\s@<>()\[\]]+\.[^\s@<>()\[\]]+")


@dataclass(frozen=True)
class Commit:
    day: str
    subject: str


@dataclass(frozen=True)
class Report:
    since: str
    until: str
    commits: list
    text: str


def git_log_argv(root: Path) -> list:
    return ["git", "-C", str(root), *GIT_LOG_ARGS]


def clean_subject(subject: str) -> str:
    s = "".join(ch if ch.isprintable() else " " for ch in subject)
    s = _EMAIL.sub("[email removed]", s)
    s = " ".join(s.split())
    if len(s) > MAX_SUBJECT:
        s = s[: MAX_SUBJECT - 3] + "..."
    return s or "(no subject)"


def read_git_log(root: Path, since: str, until: str) -> list:
    """Run the fixed git log command, parse it, keep the days from since to until. No shell, no network."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    try:
        proc = subprocess.run(
            git_log_argv(root),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=GIT_TIMEOUT_SECONDS,
            env=env,
            shell=False,
            check=False,
        )
    except FileNotFoundError:
        raise UmwayiError("report: git is not installed or not on the PATH") from None
    except subprocess.TimeoutExpired:
        raise UmwayiError(f"report: git log took longer than {GIT_TIMEOUT_SECONDS} seconds") from None
    except OSError:
        raise UmwayiError("report: git could not be started") from None
    if proc.returncode != 0:
        raise UmwayiError("report: git log failed (is the root inside a git repository with at least one commit?)")
    text = proc.stdout.decode("utf-8", errors="replace")
    lines = [l for l in text.splitlines() if l]
    if len(lines) > MAX_COMMITS:
        raise UmwayiError(f"report: the history has more than {MAX_COMMITS} commits, which this report does not read")
    commits = []
    for n, line in enumerate(lines, 1):
        day, sep, subject = line.partition("\x1f")
        if not sep or not is_valid_date(day):
            raise UmwayiError(f"report: git log output line {n} could not be read")
        if since <= day <= until:
            commits.append(Commit(day, clean_subject(subject)))
    return commits


def render(since: str, until: str, commits: list) -> str:
    per_day: dict = {}
    for c in commits:
        per_day.setdefault(c.day, []).append(c.subject)
    out = [
        "# Progress report (draft)",
        "",
        f"From {since} to {until}. Commits: {len(commits)} (merge commits are not counted).",
        "",
        "## Commits per day",
        "",
    ]
    if not per_day:
        out += ["No commits in this period.", ""]
    else:
        out += ["| day | commits |", "| --- | --- |"]
        out += [f"| {d} | {len(per_day[d])} |" for d in sorted(per_day)]
        out += ["", "## Subjects", ""]
        for d in sorted(per_day):
            out += [f"### {d}", ""] + [f"- {s}" for s in per_day[d]] + [""]
    out += ["This is a draft for the owner. Nothing was published or pushed."]
    return "\n".join(out) + "\n"


def build(root: Path, since: str, until: str) -> Report:
    if not is_valid_date(since) or not is_valid_date(until):
        raise UmwayiError("report: dates must be real dates YYYY-MM-DD")
    if since > until:
        raise UmwayiError("report: --since is after today, there is nothing to report")
    commits = read_git_log(root, since, until)
    return Report(since, until, commits, render(since, until, commits))


Draft = drafts.Draft


def create_draft(root: Path, text: str) -> Draft:
    """Write text to a new drafts/report-NNNN.md. Never overwrites."""
    return drafts.create(root, "report", text)


def remove_draft(root: Path, draft: Draft) -> None:
    drafts.remove(root, draft)


def make(root: Path, since: str, today: str) -> tuple[Report, str]:
    """`umwayi report`: build the report, write the draft, log it. Undo the draft if the log fails."""
    rep = build(root, since, today)
    draft = create_draft(root, rep.text)
    rel = draft.rel
    entry = logbook.Entry(
        date=today,
        source="umwayi report",
        added=f"wrote {rel}: {len(rep.commits)} commits from {since} to {today}",
        checked="read git history with the one fixed git log command; author names and emails were not read; "
        "the draft name was new",
        not_done="Nothing was published or pushed. No git command that writes was run. No network was used.",
    )
    try:
        logbook.append(root, entry)
    except Exception as e:
        reason = f": {e}" if isinstance(e, UmwayiError) else ""
        try:
            remove_draft(root, draft)
        except OSError:
            raise UmwayiError(f"the logbook write failed AND {rel} could not be removed, delete it by hand") from None
        raise UmwayiError("the logbook write failed, so the draft was removed" + reason) from None
    return rep, rel


def days_before(today: str, days: int) -> str:
    return date.fromordinal(date.fromisoformat(today).toordinal() - days).isoformat()
