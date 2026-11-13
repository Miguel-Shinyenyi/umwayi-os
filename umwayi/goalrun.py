"""Goal orchestration (W9.7): the supervisor. The first code that starts an AI helper, so it fails closed everywhere.

What it does (W9.R7, W9.R8, W9.R10, W9.R16, W9.R17), and nothing else:

  * the start steps of a run, in the fixed order of W9.R7 (kill switch, state, the rules action `goal_start`, the gate
    checks, the independence rule, the run lock and the worktree preconditions, the budget cap, the start entry, the
    worktree, the child);
  * the one child: `[sys.executable, "-m", "umwayi", "agent", "run", NAME, "-", ...]`, the prompt on its standard input,
    no shell, in its own process group (`_spawn` is the only place a process is started);
  * the watch of that child, once a second: the kill switch, the logbook and the goal folder, the work fingerprint every
    30 seconds, the stall and loop judge of `goalwatch`, and the stop of W9.R10.5;
  * the scope check after the builder, the tester run, the guide's check run, `in review`, the merge observation and
    the cleanup call after merged.

What it never does: `git push`, `merge`, `rebase`, `pull`, `fetch`, `reset`, `clean`, `checkout`, `switch`, `branch`,
`commit` or any other git write beyond the worktree functions of `umwayi/goalgit.py` (this module starts no git
process; every git question goes through `umwayi/goalgit.py`), a force flag, a network call, a pull request.
It starts no AI helper any other way. It is not wired into the command line: `umwayi/goal.py` (W9.8) calls it.

The return value of a run is an `Outcome` with the exit code the command gives (W9.R3.2): 0 the task is in review (or the
plan was made), 2 a task failed or stopped or a record could not be written, 3 the owner is needed or the kill switch is
on. A crash is never 0 or 3: the caller maps an unexpected error to 2.

Standard library only. No text of the work (goal text, prompt, helper output, diff) reaches an entry, an event or an
Outcome; the Outcome holds fixed words.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import queue
import re
import secrets
import signal
import stat
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from umwayi import agents, budget, goalbudget, goaldocs, goalgit as gg, goallog, goalpacket as gp, goalstate as gs, goalwatch as gw
from umwayi import kill, logbook, rules, runlock, taskqueue, units
from umwayi.errors import ConfigError, UmwayiError, UsageError

POLL_S = 1.0  # the watch wakes this often
FINGERPRINT_S = 30.0
OUTPUT_S = 5.0
POLL_EVENT_S = 30.0
STOP_GRACE_S = 10.0  # between SIGTERM to the child and SIGKILL to its group (W9.R10.5)
BUSY_TRIES = 5  # the run lock is probed this many times, 60 seconds apart (W9.R7.6)
BUSY_WAIT_S = 60.0
MAX_FILE_READ = 2 * 1024 * 1024  # the fingerprint reads a file up to this size (design.md, "The work fingerprint")
MAX_PART_FILE = 64 * 1024  # a status or limits part is read up to this size
CHILD_PREFIX = [sys.executable, "-m", "umwayi", "agent", "run"]
RECORD_FAILED = gs.RECORD_FAILED
PLATFORM_OPTIONS = ("claude-code", "kiro")  # the platform table of W9.R15.6: these take a model and an effort

TAGS = {"guide": "UMWAYI-PLAN", "tester": "UMWAYI-RESULT", "check": "UMWAYI-CHECK"}
TAG_LIMITS = {"UMWAYI-PLAN": gp.MAX_PLAN_BYTES, "UMWAYI-RESULT": gp.MAX_RESULT_BYTES, "UMWAYI-CHECK": gp.MAX_CHECK_BYTES}

_TIMEOUT_TEXT = re.compile(r"was stopped after its timeout of \d+ min")
_BUDGET_TEXT = re.compile(r"was stopped: it passed its budget of \d+ UU")


# ----------------------------------------------------------------------------------------------- the outcome


@dataclass(frozen=True)
class Outcome:
    """What a run ended as: the exit code of W9.R3.2, the task's state and reason word, and one fixed word."""
    exit: int
    state: str = ""
    reason: str = ""
    word: str = ""

    @property
    def ok(self):
        return self.exit == 0


# `reason_for` is the only chooser of a reason word (W9.R6.2): this module names causes, never reasons.
def _outcome(cause, word=""):
    state, reason = gp.reason_for(cause)
    return Outcome(EXIT_OF_STATE[state], state, reason, word or cause)


REFUSED_CAUSE = {"stale": "main_behind_origin", "leftover": "worktree_leftover", "dirty": "worktree_not_clean",
                 "config": "worktree_not_made"}
EXIT_OF_STATE = {"queued": 0, "running": 0, "in review": 0, "merged": 0, "needs owner": 3, "failed": 2, "stopped": 2}


class _Done(Exception):
    """Internal: the run ends here with this outcome (always after the state was recorded, or nothing changed)."""

    def __init__(self, outcome):
        super().__init__(outcome.word)
        self.outcome = outcome


# ----------------------------------------------------------------------------------------------- the environment


def _spawn(argv, cwd, environ):
    """The one place a child is started (W9.R7.9): an argument list, no shell, a pipe for the prompt and for the
    output, its own process group. Anything else of `argv` than the prefix is data built by `child_argv`."""
    return subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            start_new_session=True, cwd=str(cwd), env=environ, shell=False, close_fds=True)


def _gate(root, name, workdir=None):
    """`agents.check_agent`, for the folder of the task when there is one. An agent module that cannot check a given
    folder (before W9.6b) gives a refusal, never a pass."""
    if workdir is None:
        return agents.check_agent(root, name)
    if "workdir" not in inspect.signature(agents.check_agent).parameters:
        return agents.Result(64, ["agent check --workdir is not available"])
    return agents.check_agent(root, name, workdir=workdir)


class StopFlag:
    """Set by SIGTERM, SIGHUP or Ctrl-C (W9.R16.3), or by a test. The watch reads it every second."""

    def __init__(self):
        self.name = None

    def set(self, name):
        if self.name is None:
            self.name = name

    def is_set(self):
        return self.name is not None


@dataclass
class Env:
    """Everything the supervisor reads from outside, so a test can replace each piece and nothing else. `clock` is the time of day in seconds (UTC), `mono` a
    monotonic clock for the watch; `policy` replaces the stall and loop numbers (a test only)."""
    root: Path
    clock: object = time.time
    mono: object = time.monotonic
    sleep: object = time.sleep
    spawn: object = _spawn
    gate: object = _gate
    nonce: object = lambda: secrets.token_hex(8)  # noqa: E731
    environ: object = None
    out: object = lambda text: None  # noqa: E731  one line for the owner's terminal
    policy: object = None
    stop: StopFlag = field(default_factory=StopFlag)
    busy_wait: float = BUSY_WAIT_S

    def __post_init__(self):
        self.root = Path(os.path.realpath(self.root))

    def now(self):
        return int(self.clock())

    def when(self):
        day = datetime.fromtimestamp(self.now(), timezone.utc).strftime("%Y-%m-%d")
        return rules.election_clock(self.root, day)

    def child_environ(self):
        return dict(os.environ if self.environ is None else self.environ)


class _Git:
    """The questions the supervisor asks of git, each one a call into `umwayi/goalgit.py` (the only place git is started).
    No argument list is built here. A non-zero answer of a read is `Refused("config")`, never a guess."""

    def worktree_path(self, root, goal, task):
        return gg.worktree_path(gg.real_root(root), goal, None if task == "plan" else task)

    def _ask(self, name, root, **kw):
        r = gg.run_git(name, root, **kw)
        return r

    def status(self, root, path):
        r = self._ask("status", root, worktree=path)
        if not r.ok:
            raise gg.Refused("config")
        out = []
        for e in r.out.split(b"\0"):
            if e:
                out.append((e[:2].decode("ascii", "replace"), e[3:].decode("utf-8", "replace")))
        return out

    def head(self, root, path):
        r = self._ask("head", root, worktree=path)
        if not r.ok or not r.text():
            raise gg.Refused("config")
        return r.text()

    def count_ahead(self, root, path, base):
        r = self._ask("count_ahead", root, worktree=path, BASE=base)
        if not r.ok or not r.text().isdigit():
            raise gg.Refused("config")
        return int(r.text())

    def changed(self, root, path, base):
        r = self._ask("changed", root, worktree=path, BASE=base)
        if not r.ok:
            raise gg.Refused("config")
        parts = r.out.split(b"\0")
        return [(parts[i].decode("ascii", "replace"), parts[i + 1].decode("utf-8", "replace"))
                for i in range(0, len(parts) - 1, 2)]

    def is_ancestor(self, root, tip):
        try:
            return self._ask("is_ancestor", root, TIP=tip).ok
        except ValueError:
            return False  # not a commit name: not on main

    def commit_exists(self, root, sha):
        try:
            return self._ask("commit_exists", root, SHA=sha).ok
        except ValueError:
            return False


    def root_ok(self, root):
        """The root is a git work tree with a local `main` (W9.R5.5). Any failure to ask is False."""
        try:
            return gg.is_repo(root) and gg.has_main(root)
        except UmwayiError:
            return False


GIT = _Git()

# ----------------------------------------------------------------------------------------------- the prompts

# W9.R5, W9.R8 and design.md "The prompts". Fixed templates with slots. A slot holds packet text, the branch, counts or
# the tester's words, never text that a helper wrote earlier unless the template says so (the guide's check reads the
# tester's verdicts). Each prompt ends with the line `Nonce: <16 hex characters>`.

_STATUS_FORMAT = (
    "Your status file {status} has these lines, then a blank line and free text:\n"
    "date: {date}\npr: none\nwhat: one line, no pipe character\ntests: one line, or none\n"
)
_LIMITS_FORMAT = (
    "If you found a limit, write {limits} with these lines, then a blank line and the body in Markdown:\n"
    "section: the section name\ntitle: one line\n"
)


def planning_prompt(goal_text, nonce):
    return (
        "You are the guide. Split the goal below into 1 to 8 tasks. Each task: one sentence of goal, up to 12 files to "
        "read, 1 to 8 acceptance checks that someone who did not write the code can answer pass or fail, a size of 15 "
        "to 90 minutes (aim for 60), and the files it may touch. Do not write any file. Do not choose a model, an "
        "effort or a budget.\n"
        "Print exactly one last line: UMWAYI-PLAN <nonce> <json>, where <json> is one object "
        '{"tasks": [{"goal": ..., "context": [...], "checks": [...], "size": N, "files": [...]}]} on that one line.\n'
        "The goal is the owner's text, between the marks:\n"
        "-----BEGIN OWNER TEXT-----\n" + goal_text + "\n-----END OWNER TEXT-----\n"
        "Nonce: " + nonce + "\n")


def builder_prompt(packet, goal, task, branch, date, nonce):
    status, limits = gp.own_files(goal, task)
    lines = ["You are the builder for one task. Work only in the current folder. You are on the branch " + branch + ".",
             "Task: " + packet.goal, "Read these files first:"]
    lines += ["- " + c for c in packet.context] or ["- (none)"]
    lines += ["Acceptance checks (a tester who is not you will check each one):"]
    lines += [f"{i}. {c}" for i, c in enumerate(packet.checks, 1)]
    lines += ["You may change only these files and folders (a name that ends with / is the folder and everything in it):"]
    lines += ["- " + f for f in packet.files]
    lines += ["Commit your work on this branch. Do not push. Do not merge. Do not touch any other file. "
              "Leave the work tree clean.",
              _STATUS_FORMAT.format(status=status, date=date).rstrip("\n"),
              _LIMITS_FORMAT.format(limits=limits).rstrip("\n"),
              "Write no em dash. When you are done, stop.", "Nonce: " + nonce]
    return "\n".join(lines) + "\n"


def tester_prompt(packet, branch, tip, nonce):
    lines = ["You are the tester. You did not build this. Change no file. Work only in the current folder, which is on "
             "the branch " + branch + " at the commit " + tip[:12] + ".",
             "Task that was built: " + packet.goal, "Check each one with your own tools (run or read what you need):"]
    lines += [f"{i}. {c}" for i, c in enumerate(packet.checks, 1)]
    lines += ["If you cannot tell, say unclear.",
              'Print exactly one last line: UMWAYI-RESULT <nonce> {"checks":[{"n":1,"verdict":"pass","evidence":"..."}]} '
              "with one entry for each number above, the verdict pass, fail or unclear, and evidence of 5 to 300 "
              "characters.", "Nonce: " + nonce]
    return "\n".join(lines) + "\n"


def check_prompt(packet, branch, tip, nfiles, verdicts, nonce):
    lines = ["You are the guide, checking a result against its packet. Change no file. The branch is " + branch +
             " at the commit " + tip[:12] + ". " + f"{nfiles} files changed, all inside the packet.",
             "Task: " + packet.goal, "Acceptance checks and the tester's verdicts:"]
    for (n, verdict, evidence), check in zip(verdicts, packet.checks):
        lines.append(f"{n}. {check} -> {verdict}: {evidence}")
    lines += ["Answer accept, reject or unclear.",
              'Print exactly one last line: UMWAYI-CHECK <nonce> {"verdict":"accept","reason":"..."}',
              "Nonce: " + nonce]
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------------------------- the child's argument list


def options_for(platform, model, effort):
    """The model and effort words that `agent run` may be given (W9.R15.6): only for the platforms of the table, only if
    the word is set. Empty means the platform's own default."""
    if platform not in PLATFORM_OPTIONS:
        return []
    out = []
    if model:
        out += ["--model", model]
    if effort:
        out += ["--effort", effort]
    return out


def child_argv(name, cap_uu, workdir, model_effort=()):
    """The whole argument list of the one child. The prompt is never in it (W9.R3.5): it goes on standard input."""
    if not (isinstance(cap_uu, int) and not isinstance(cap_uu, bool) and cap_uu >= 1):
        raise ValueError("a run needs a cap of at least 1 UU")
    argv = CHILD_PREFIX + [name, "-", "--cap-uu", str(cap_uu)] + list(model_effort)
    if workdir is not None:
        argv += ["--workdir", str(workdir)]
    return argv


def cause_of_exit(code, saw_timeout=False, saw_budget=False):
    """The cause for the exit code of `agent run` that is not 0 (W9.R7.8): 3 asks the owner, 2 fails the run, 64 is a
    config problem. Anything else (a signal, 1, a code that `agent run` never gives) fails the run: closed."""
    if code == 3:
        return "task_budget_spent" if saw_budget else "agent_exit_3"
    if code == 64:
        return "agent_exit_64"
    if code == 2 and saw_timeout:
        return "agent_timeout"
    return "agent_exit_2" if code == 2 else "agent_exit_nonzero"


# ----------------------------------------------------------------------------------------------- reading the child's output


class TagCapture:
    """Keeps the lines that start with one tag (`UMWAYI-PLAN `, `UMWAYI-RESULT `, `UMWAYI-CHECK `), each cut at `limit`
    plus one byte (so `parse_result_line` sees `size`), at most four different ones. Everything else is dropped as it
    arrives: memory is bounded however much the child prints. The 4096 byte bound of the event stream (W9.R12.5) is too
    small for a plan of 32 KB, so the tagged lines have a bound of their own."""

    MAX_KEPT = 4

    def __init__(self, tag, limit):
        self.prefix = tag.encode("ascii") + b" "
        self.limit = limit + 1
        self.lines = []
        self._buf = bytearray()
        self._skip = False  # the rest of this line is not a tagged line

    def _end_line(self):
        line = bytes(self._buf)
        skip, self._skip = self._skip, False
        self._buf.clear()
        if not skip and line.startswith(self.prefix) and line not in self.lines and len(self.lines) < self.MAX_KEPT:
            self.lines.append(line)

    def feed(self, chunk):
        data = bytes(chunk)
        while data:
            nl = data.find(b"\n")
            piece, data = (data, b"") if nl == -1 else (data[:nl], data[nl + 1:])
            if not self._skip:
                self._buf += piece[:self.limit - len(self._buf)]
                n = len(self.prefix)
                head = bytes(self._buf[:n])
                if not (head == self.prefix if len(self._buf) >= n else self.prefix.startswith(head)):
                    self._buf.clear()
                    self._skip = True
            if nl != -1:
                self._end_line()

    def finish(self):
        if self._buf and not self._skip:
            self._end_line()

    def text(self):
        return b"\n".join(self.lines).decode("utf-8", "replace")


class OutputReader(threading.Thread):
    """Reads the child's standard output with a bound and keeps only counts, error signatures and the tagged lines.

    Errors go on a bounded queue as (kind, value) pairs; counts are read under a lock. The thread never raises and
    never lets a flood grow memory: a full queue holds the thread, so the pipe holds the child, and the watch still
    runs (W9.R12.5)."""

    def __init__(self, stream, tag=None):
        super().__init__(daemon=True)
        self._stream = stream
        self._lines = goallog.LineReader()
        self._capture = TagCapture(tag, TAG_LIMITS[tag]) if tag else None
        self._lock = threading.Lock()
        self.queue = queue.Queue(maxsize=4096)
        self.line_count = self.byte_count = self.skipped = 0
        self.saw_timeout = self.saw_budget = False
        self.done = threading.Event()

    def _line(self, text, flagged):
        with self._lock:
            self.line_count += 1
            if flagged:
                self.skipped += 1
        if _TIMEOUT_TEXT.search(text):
            self.saw_timeout = True
        if _BUDGET_TEXT.search(text):
            self.saw_budget = True
        sig = gw.signature(text)
        if sig is not None:
            self.queue.put(("error", sig))

    def run(self):
        try:
            fd = self._stream.fileno()
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                with self._lock:
                    self.byte_count += len(chunk)
                if self._capture is not None:
                    self._capture.feed(chunk)
                for text, flagged in self._lines.feed(chunk):
                    self._line(text, flagged)
            if self._capture is not None:
                self._capture.finish()
            for text, flagged in self._lines.flush():
                self._line(text, flagged)
        except Exception:  # a broken pipe or a closed stream ends the reading; the exit code is what counts
            pass
        finally:
            self.done.set()

    def take_counts(self, last):
        """(lines, bytes, skipped) since `last` (a tuple), and the new total."""
        with self._lock:
            total = (self.line_count, self.byte_count, self.skipped)
        return tuple(a - b for a, b in zip(total, last)), total

    def tagged_text(self):
        return self._capture.text() if self._capture is not None else ""


# ----------------------------------------------------------------------------------------------- the work fingerprint


def _hash_file(path):
    """SHA-256 of a file's bytes, read with a 2 MB cap (a larger file counts its size and mtime), or a word for what
    is not a plain file. Read only."""
    try:
        st = os.lstat(path)
    except OSError:
        return "gone"
    if stat.S_ISLNK(st.st_mode):
        try:
            return "link:" + hashlib.sha256(os.readlink(path).encode("utf-8", "replace")).hexdigest()
        except OSError:
            return "gone"
    if not stat.S_ISREG(st.st_mode):
        return "other"
    if st.st_size > MAX_FILE_READ:
        return f"big:{st.st_size}:{int(st.st_mtime)}"
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read(MAX_FILE_READ + 1)).hexdigest()
    except OSError:
        return "gone"


def fingerprint(head, entries, folder, own=()):
    """The work fingerprint of design.md: SHA-256 of the tip, the sorted status lines, and for each changed path the
    SHA-256 of its contents. `entries` is a list of (code, path) from `git status`. Left out: the task's own two files
    and anything under `.umwayi/`. Pure but for the file reads."""
    skip = set(own)
    keep = sorted((c, p) for c, p in entries if p not in skip and not (p == ".umwayi" or p.startswith(".umwayi/")))
    h = hashlib.sha256()
    h.update(str(head).encode("utf-8", "replace") + b"\0")
    for code, path in keep:
        h.update(f"{code} {path}\n".encode("utf-8", "replace"))
    h.update(b"\0")
    for _code, path in sorted(keep, key=lambda e: e[1]):
        h.update(path.encode("utf-8", "replace") + b"\0" + _hash_file(os.path.join(str(folder), path)).encode("ascii") + b"\0")
    return h.hexdigest()


# ----------------------------------------------------------------------------------------------- the kill switch for all goals


def goal_status(root, goal):
    """The state of a goal as W9.R6.4 derives it, or `plan` before approval. Read from the files."""
    g = gs.read_goal(root, goal)
    if g["stopped"]:
        return "stopped"  # the goal-level stop of W9.R16 (the derived state alone would read the tasks)
    if not g["approved"]:
        return "plan" if not g["refused"] else "refused"
    states = []
    for task in gs.list_tasks(root, goal):
        t = gs.read_task(root, goal, task)
        if not t["dropped"]:
            states.append(t["state"])
    return gp.goal_state(states, stopped=bool(g["stopped"]))


def kill_all(env):
    """W9.R16.2: while the kill switch is on, every goal that is `active` or in `plan` is marked stopped with the reason
    `kill`, each with its own entry, so `status` shows no goal as ready. Queued tasks stay queued. Returns the goals."""
    stopped = []
    for goal in gs.list_goals(env.root):
        if goal_status(env.root, goal) in ("active", "plan"):
            if gs.stop_goal(env.root, goal, "kill", when=env.when(), now=env.now()):
                stopped.append(goal)
    return stopped


# ----------------------------------------------------------------------------------------------- one run of one task


@dataclass
class RoleResult:
    code: int | None  # the exit code of the child; None when it never ran to its own end
    why: str | None  # None, or kill, signal, log, stalled, looping: why the supervisor stopped it
    reader: object
    spent_uu: int
    cap_uu: int
    over: bool  # the run passed its cap (the ledger says so)


class _Run:
    """The state of one task through its runs: the builder, the scope check, the tester and the guide's check."""

    def __init__(self, env, goal, task):
        self.env, self.goal, self.task = env, goal, task
        self.root = env.root
        self.g = gs.read_goal(self.root, goal)
        self.t = gs.read_task(self.root, goal, task)
        self.packet = gp.packet_from_dict(self.t["packet"])
        self.branch = gp.branch_name(goal, task)
        self.own = gp.own_files(goal, task)
        self.writer = None
        self.worktree = None
        self.base = None
        self.tip = None
        self.spent = {}  # role -> UU spent in this process
        self.prior = int(self.t.get("spent_uu") or 0)
        self.nfiles = 0
        self.verdicts = ()

    # ---- small helpers

    def agent_of(self, role):
        return {"builder": self.g["builder"], "tester": self.g["tester"], "check": self.g["guide"],
                "guide": self.g["guide"]}[role]

    def model_effort(self, role):
        if role == "builder":
            return self.packet.model, self.packet.effort
        if role == "tester":
            return self.g["tester_model"], self.g["tester_effort"]
        return self.g["guide_model"], self.g["guide_effort"]

    def spent_total(self):
        return self.prior + sum(self.spent.values())

    def say(self, text):
        self.env.out(text)

    def events(self):
        if self.writer is None:
            self.writer = self.open_writer(gs.events_path(self.root, self.goal, self.task))
        return self.writer

    def open_writer(self, path):
        """The only writer of an event log. A torn tail gets its newline and one `torn` record; every other bad line already
        in the log gets one `skipped` record, once (W9.R12.3, W9.R12.4)."""
        w = goallog.Writer(path, self.env.clock).open()
        w.record_skips()
        return w

    def account(self):
        budgets, spent = {}, {}
        for task in gs.list_tasks(self.root, self.goal):
            t = gs.read_task(self.root, self.goal, task)
            if t["dropped"] or t["packet"].get("budget_uu") in (None, ""):
                continue
            budgets[task] = int(t["packet"]["budget_uu"])
            spent[task] = int(t.get("spent_uu") or 0)
        acct = goalbudget.Account(int(self.g["goal_budget_uu"]), int(self.g["plan_budget_uu"]), budgets)
        for task, uu in spent.items():
            if task != self.task and uu:
                acct.record(task, "builder", uu)
        if self.prior:
            acct.record(self.task, "builder", self.prior)
        for role, uu in self.spent.items():  # the runs of this process, counted as soon as they end
            if uu:
                acct.record(self.task, role, uu)
        return acct

    # ---- recording a change (W9.R13.1): the entry is the change, the files follow

    def move(self, new, reason, **kw):
        try:
            return gs.change_state(self.root, self.goal, self.task, new, reason, when=self.env.when(), now=self.env.now(),
                                   spent_uu=self.spent_total(), **kw)
        except gs.RecordFailed:
            self.say(RECORD_FAILED)
            raise _Done(Outcome(2, "", "", "record")) from None
        except gs.GoalError:
            raise _Done(Outcome(2, "", "", "state")) from None

    def finish(self, cause, **kw):
        """Record the end named by `cause` and stop. `reason_for` chooses state and reason."""
        new, reason = gp.reason_for(cause)
        self.discard_unused_worktree()
        self.move(new, reason, **kw)
        raise _Done(Outcome(EXIT_OF_STATE[new], new, reason, cause))

    def record_event(self, kind, data):
        try:
            self.events().append(kind, data)
        except goallog.LogWriteFailed:
            self.say(RECORD_FAILED)
            raise _Done(Outcome(2, "", "", "record")) from None

    # ---- the start steps (W9.R7), in this order

    def stop_running(self, cause, **kw):
        """End the running task as `stopped` (kill, signal, log). The kill switch also marks every other goal (W9.R16.2)."""
        new, reason = gp.reason_for(cause)
        self.discard_unused_worktree()
        self.move(new, reason, **kw)
        self.t = gs.read_task(self.root, self.goal, self.task)
        if cause == "kill_switch":
            kill_all(self.env)
        raise _Done(Outcome(EXIT_OF_STATE[new], new, reason, cause))

    def step_kill(self):  # 1
        """`on` or `unknown` refuses before anything else is read (W9.R7.1). A running task is stopped with `kill`
        (so the run is exit 2); a queued one stays queued (exit 3). Every other active goal is marked (W9.R16.2)."""
        self.step_signal()
        if not kill.stopped(kill.state(self.root)):
            return
        if gs.read_task(self.root, self.goal, self.task)["state"] == "running":
            self.stop_running("kill_switch")
        kill_all(self.env)
        raise _Done(Outcome(3, self.t["state"], "kill", "kill_switch"))

    def platform_of(self, agent):
        """The platform of an agent, read from agents.yaml only after the kill switch and the state were checked. An
        agents file that cannot be read or does not hold the name is a config problem (needs owner), never a Yes."""
        try:
            return agents.find(agents.load(self.root), agent).platform
        except (UsageError, ConfigError):
            self.finish("agent_cannot_be_gated")

    def goal_stopped(self):
        """True once `umwayi goal stop` (or anything else) recorded a stop of this goal. A goal file that cannot be read
        counts as stopped: closed."""
        try:
            return bool(gs.read_goal(self.root, self.goal)["stopped"])
        except gs.GoalError:
            return True

    def step_signal(self):
        """SIGTERM, SIGHUP or Ctrl-C between two runs, or while waiting for the run lock (W9.R16.3): nothing starts."""
        if self.env.stop.is_set():
            if gs.read_task(self.root, self.goal, self.task)["state"] == "running":
                self.stop_running("signal_received")
            raise _Done(Outcome(2, self.t["state"], "signal", "signal_received"))

    def step_state(self, role):  # 2
        t = gs.read_task(self.root, self.goal, self.task)
        self.t = t
        want = "queued" if role == "builder" else "running"
        if t["state"] != want or self.g["stopped"] or not self.g["approved"]:
            raise _Done(Outcome(2, t["state"], "", "state"))
        if gp.packet_from_dict(t["packet"]).sha256() != t["sha256"]:
            self.finish("packet_changed")
        if role == "builder":
            for earlier in gs.list_tasks(self.root, self.goal):
                if earlier >= self.task:
                    break
                e = gs.read_task(self.root, self.goal, earlier)
                if not e["dropped"] and e["state"] != "merged":
                    raise _Done(Outcome(2, t["state"], "", "order"))

    def step_rules(self, role, agent, platform):  # 3
        e = self.env
        action = {"type": "goal_start", "goal": self.goal, "task": self.task, "role": role, "agent": agent,
                  "platform": platform, "budget_uu": int(self.packet.budget_uu)}
        decision, logged = rules.check_and_log(json.dumps(action), self.root / "rules.yaml", self.root, e.when(),
                                               kill_state=kill.state(self.root))
        if not logged:
            raise _Done(Outcome(2, self.t["state"], "", "unlogged"))  # a check that cannot be logged is No
        if decision.answer == rules.NO:
            self.finish("rules_said_no")
        # `goal_start` joins NEVER_AUTONOMY in W9.8. Until then no autonomy may turn Ask me first into Yes here.
        if decision.answer != rules.YES or decision.autonomy is not None:
            self.finish("rules_said_ask")

    def step_gate(self, agent, workdir=None):  # 4 and, for the folder of the task, 8
        try:
            result = self.env.gate(self.root, agent, workdir)
        except (UsageError, ConfigError):
            self.finish("agent_cannot_be_gated")
        if getattr(result, "code", 2) != 0:
            self.finish("agent_cannot_be_gated")

    def step_roles(self):  # 5
        if not gp.roles_ok(self.g["guide"], self.g["builder"], self.g["tester"]):
            raise _Done(Outcome(2, self.t["state"], "", "roles"))

    def step_lock(self):  # 6, the run lock: probed, never held (the child holds it for its own run)
        for i in range(BUSY_TRIES):
            try:
                with runlock.held(self.root):
                    return
            except runlock.RunLockBusy:
                if i + 1 < BUSY_TRIES:
                    self.say(f"The run lock is held. Waiting {int(self.env.busy_wait)} s (try {i + 1} of {BUSY_TRIES}).")
                    self.env.sleep(self.env.busy_wait)
                    self.step_signal()
            except runlock.RunLockUnavailable:
                self.finish("agent_cannot_be_gated")
        self.finish("run_lock_busy")

    def step_worktree_preconditions(self):  # 6, for a builder
        """BASE, `stale`, `leftover` (a folder, a registration, a branch, an unlisted folder, the cap of eight, another
        task file with the same path or branch), all by `goalgit.start_check`, which creates nothing."""
        self.base = self.check_start()

    def check_start(self):
        try:
            return gg.start_check(self.root, self.goal, self.task_or_none())
        except gg.Refused as r:
            self.say(str(r))
            if r.reason == "leftover" and r.found and all(kind == "cap" for kind, _t in r.found):
                self.finish("worktree_cap")
            self.finish(REFUSED_CAUSE[r.reason])
        except gg.GitError:
            self.finish("worktree_not_made")

    def task_or_none(self):
        return self.task

    def step_budget(self, role, agent, platform):  # 7
        today = self.env.when()
        try:
            u = units.load(self.root, today)
        except ConfigError:
            self.finish("agent_cannot_be_gated")
        ledger = budget.read_ledger(self.root)
        per_run = u.limits["per_run"]
        day_left = goalbudget.day_left_uu(ledger, u, agent, platform, today)
        cap, why = self.account().next_cap(self.task, per_run, day_left)
        if cap < 1:
            if why == "goal":
                self.stop_goal_for_budget()
            if why == "task":
                self.finish("task_budget_spent")
            self.finish("budget_said_ask")
        return cap, goalbudget.run_ids(ledger)

    def stop_goal_for_budget(self):
        """The goal budget is spent: no run starts; the goal is stopped with `budget`, one entry, one queue decision
        (W9.R15.4). A task that was running cannot stay running: it is failed with `budget` first."""
        taskqueue.add_once(self.root, "decision", f"Goal {self.goal} stopped: its budget is spent",
                           "Raise the budget with a new umwayi goal approve, or leave it stopped. Answering this item "
                           "starts nothing.", self.env.when())
        if gs.read_task(self.root, self.goal, self.task)["state"] == "running":
            self.discard_unused_worktree()
            self.move("failed", "budget")
        gs.stop_goal(self.root, self.goal, "budget", when=self.env.when(), now=self.env.now())
        raise _Done(Outcome(2, "stopped", "budget", "goal_budget_spent"))

    # ---- the child and its watch

    def start_role(self, role, prompt):
        """Steps 1 to 8, then the child and its watch. Returns a RoleResult. Raises _Done when the run ends here."""
        agent = self.agent_of(role)
        self.step_kill()
        self.step_state(role)
        platform = self.platform_of(agent)
        self.step_rules(role, agent, platform)
        self.step_gate(agent)
        self.step_roles()
        self.step_lock()
        if role == "builder":
            self.step_worktree_preconditions()
        else:
            self.require_clean()
        cap, before = self.step_budget(role, agent, platform)
        if role == "builder":
            self.begin_builder(agent, cap)
        model, effort = self.model_effort(role)
        argv = child_argv(agent, cap, self.worktree, options_for(platform, model, effort))
        fp_fn = self.fp_all(self.own) if role == "builder" else None
        return self.run_child(role, argv, prompt, fp_fn, cap, before, agent, TAGS.get(role))

    def begin_builder(self, agent, cap):
        """Step 8: the start entry (with BASE), then the worktree, its checks, the gate for it."""
        self.move("running", "start", role="builder", agent=agent, cap_uu=cap, base=self.base,
                  facts=[("kill", {}), ("rules", {}), ("packet", {"h": self.t["sha256"][:8]}), ("lock", {}),
                         ("spent", {"a": str(self.spent_total()), "b": str(int(self.packet.budget_uu))})])
        self.t = gs.read_task(self.root, self.goal, self.task)
        self.make_worktree()
        path = self.worktree
        self.append_worktree_entry("made")
        self.record_event("worktree", {"action": "made", "base": self.base[:8]})
        self.step_gate(agent, path)

    def make_worktree(self):
        """`goalgit.make`: leftover once more, the worktree root, `worktree add -b`, then the checks. A wrong new worktree
        was removed by goalgit (no force) and is `dirty`."""
        try:
            made = gg.make(self.root, self.goal, self.task, self.base)
        except gg.Refused as r:
            self.finish(REFUSED_CAUSE[r.reason])
        except gg.GitError:
            self.finish("worktree_not_made")
        self.worktree = made.path

    def append_worktree_entry(self, action, how=None):
        try:
            entry = gs.worktree_entry(self.env.when(), self.goal, self.task, action, base=self.base, how=how)
            logbook.append(self.root, entry)
        except (UmwayiError, ValueError):
            self.say(RECORD_FAILED)
            raise _Done(Outcome(2, "", "", "record")) from None

    def discard_unused_worktree(self):
        """A worktree that was made and in which no builder ever started is removed at once (W9.R8.13), by
        `goalgit.remove_unused` (clean and at BASE, no force)."""
        path, self.worktree = self.worktree, None
        if path is None or getattr(self, "builder_started", False):
            self.worktree = path
            return
        try:
            done = gg.remove_unused(self.root, self.goal, self.task_or_none(), self.base)
            if done.removed:
                # no logbook entry: the entry of a removal is the one "after merged"; this is an undo of our own step
                self.events().append("worktree", {"action": "removed", "base": self.base[:8]})
        except (UmwayiError, ValueError):
            pass  # left over: the next start says so (`leftover`)

    def run_child(self, role, argv, prompt, fp_fn, cap, before, agent, nonce_tag):
        e = self.env
        proc = e.spawn(argv, self.root, e.child_environ())
        # The `started` event, with the pid, comes before the prompt: the child reads its prompt first and does nothing
        # until it has it, so no helper acts before the start is on record. If the event cannot be written the child is
        # stopped and nothing was given to it.
        try:
            self.record_event("started", {"role": role, "agent": agent, "cap_uu": cap, "pid": proc.pid})
        except _Done:
            self.stop_child(proc)
            raise
        if role == "builder":
            self.builder_started = True
        feeder = threading.Thread(target=_feed, args=(proc.stdin, prompt.encode("utf-8")), daemon=True)
        feeder.start()
        reader = OutputReader(proc.stdout, TAGS.get(role))
        reader.start()
        try:
            why = self.watch(role, proc, reader, fp_fn)
        finally:
            if proc.poll() is None:
                self.stop_child(proc)
        reader.done.wait(2.0)
        try:
            proc.stdout.close()
        except OSError:
            pass
        code = proc.returncode
        after = budget.read_ledger(self.root)
        uu = goalbudget.spent_uu(before, after, agent)
        self.spent[role] = self.spent.get(role, 0) + uu
        return RoleResult(code, why, reader, uu, cap, uu > cap)

    def stop_child(self, proc):
        """SIGTERM to the child (which stops the AI helper and its group, settles the budget and writes its entries),
        10 seconds of grace, then SIGKILL to the child's group (W9.R10.5)."""
        e = self.env
        if proc.poll() is None:
            try:
                os.kill(proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            end = e.mono() + STOP_GRACE_S
            while proc.poll() is None and e.mono() < end:
                e.sleep(0.1)
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass

    def watch(self, role, proc, reader, fp_fn):
        """Once a second: the kill switch, a signal, the logbook and the goal folder, the fingerprint every 30 s, the
        events, the judge. Returns None (the child ended by itself) or why it was stopped."""
        e = self.env
        policy = e.policy or gw.Policy.for_role(role)
        start = e.mono()
        history = [("start", start)]
        next_fp, next_out, next_poll = start + FINGERPRINT_S, start + OUTPUT_S, start + POLL_EVENT_S
        last_fp = fp_fn()[0] if fp_fn else None
        counts, lines_seen = (0, 0, 0), 0
        why = None
        w = None
        try:
            w = self.events()
            while True:
                now = e.mono()
                while True:  # errors: one event each, and a point for the judge
                    try:
                        kind, sig = reader.queue.get_nowait()
                    except queue.Empty:
                        break
                    history.append(("error", now, sig))
                    w.append("error", {"sig": sig})
                new, total = reader.take_counts(counts)
                if total[0] > lines_seen:  # the policy decides whether output is progress (not for a builder)
                    history.append(("output", now))
                lines_seen = total[0]
                if now >= next_out:
                    if any(new):
                        w.append("output", {"lines": new[0], "bytes": new[1], "skipped": new[2]})
                        counts = total
                    next_out = now + OUTPUT_S
                if proc.poll() is not None:
                    break
                if e.stop.is_set():
                    why = "signal"
                elif kill.stopped(kill.state(self.root)):
                    why = "kill"
                elif self.goal_stopped():
                    why = "owner"  # `umwayi goal stop` (W9.R16.3): the owner ended the goal while this child ran
                else:
                    try:
                        logbook.check_writable(self.root, e.when())
                        w.probe()
                    except UmwayiError:
                        why = "log"
                if why is None and fp_fn is not None and now >= next_fp:
                    fp, n = fp_fn()
                    changed = fp != last_fp
                    w.append("fingerprint", {"changed": changed, "files": n})
                    if changed:
                        history.append(("progress", now))
                    last_fp, next_fp = fp, now + FINGERPRINT_S
                if why is None and now >= next_poll:
                    w.append("poll", {})
                    next_poll = now + POLL_EVENT_S
                if why is None:
                    verdict = gw.judge(history, now, policy)
                    if isinstance(verdict, gw.Stop):
                        why = verdict.reason
                if why is not None:
                    break
                e.sleep(POLL_S)
        except goallog.LogWriteFailed:
            why = "log"
        if why is not None:
            self.stop_child(proc)
            try:
                if w is not None:
                    w.append("stopped", {"reason": why})
            except goallog.LogWriteFailed:
                why = "log"
        # the last lines of output and the last counts
        reader.done.wait(2.0)
        try:
            new, total = reader.take_counts(counts)
            if w is not None and any(new):
                w.append("output", {"lines": new[0], "bytes": new[1], "skipped": new[2]})
            while True:
                try:
                    _kind, sig = reader.queue.get_nowait()
                except queue.Empty:
                    break
                w.append("error", {"sig": sig})
        except goallog.LogWriteFailed:
            why = why or "log"
        return why

    # ---- what the end of a run means

    def after_stop(self, role, res):
        """A run that the supervisor stopped, or that went over its cap: the task's end. Returns normally if the run
        ended by itself and under its cap."""
        if res.why == "kill":
            self.stop_running("kill_switch")
        if res.why == "signal":
            self.stop_running("signal_received")
        if res.why == "log":
            self.stop_running("log_write_failed")
        if res.why == "owner":
            self.stop_running("owner_stop")
        if res.why == "stalled":
            self.finish("no_progress")
        if res.why == "looping":
            self.finish("same_error_twice")
        if res.over:
            self.finish("task_budget_spent")

    def after_exit(self, res):
        if res.code != 0:
            cause = cause_of_exit(res.code, res.reader.saw_timeout, res.reader.saw_budget)
            self.finish(cause)

    # ---- the task, end to end (W9.R8)

    def go_pipeline(self):
        """queued to in review: the builder, the scope check, the tester, the guide's check (W9.R8). Returns an Outcome."""
        e = self.env
        nonce = e.nonce()
        prompt = builder_prompt(self.packet, self.goal, self.task, self.branch, e.when(), nonce)
        res = self.start_role("builder", prompt)
        self.after_stop("builder", res)
        self.after_exit(res)
        self.scope_check()
        self.tester_run()
        self.check_run()
        if self.tip_moved():
            self.finish("tip_moved")
        facts = [("scope", {"n": str(self.nfiles)}),
                 ("tester", {"name": self.g["tester"], "p": str(len(self.verdicts)), "m": str(len(self.verdicts))}),
                 ("guide", {"name": self.g["guide"], "word": "accept"}),
                 ("spent", {"a": str(self.spent_total()), "b": str(int(self.packet.budget_uu))})]
        self.move("in review", "checked", branch=self.branch, tip=self.tip, facts=facts, not_done="nodiff")
        return Outcome(0, "in review", "checked", "in_review")


    def scope_check(self):
        """After the builder exits 0, by umwayi alone (W9.R8.3): a commit, a clean tree, only allowed paths, a status file
        that parses, a limits file that parses if there is one. A failure ends the task and the tester is not started."""
        git, path, root = GIT, self.worktree, self.root
        if git.count_ahead(root, path, self.base) < 1:
            self.finish("no_commit")
        if git.status(root, path):
            self.finish("tree_not_clean")
        changed = [p for _code, p in git.changed(root, path, self.base)]
        bad = gp.scope_violations(changed, self.packet.files, own=self.own)
        if bad:
            self.finish("protected_file_changed" if any(isinstance(b, str) and gp.is_protected(b) for b in bad)
                        else "file_outside_packet")
        name = f"{self.goal}-{self.task}.md"
        try:
            part = _read_part(path, self.own[0], goaldocs.read_status_part, name)
        except goaldocs.PartError:
            self.finish("status_file_invalid")
        if part is None:
            self.finish("status_file_missing")
        try:
            _read_part(path, self.own[1], goaldocs.read_limits_part, name)
        except goaldocs.PartError:
            self.finish("limits_file_invalid")
        self.tip = git.head(root, path)
        self.nfiles = len(changed)


    def fp_all(self, own=()):
        git, path, root = GIT, self.worktree, self.root

        def make():
            entries = git.status(root, path)
            return fingerprint(git.head(root, path), entries, path, own), len(entries)
        return make


    def require_clean(self):
        """The tester and the guide's check start only in a clean worktree at the tip the scope check passed (W9.R8.12)."""
        if self.tip_moved():
            self.finish("worktree_not_clean")


    def changed_since(self, before):
        return self.fp_all()()[0] != before


    def tip_moved(self):
        return bool(GIT.status(self.root, self.worktree)) or GIT.head(self.root, self.worktree) != self.tip


    def tester_run(self):
        nonce = self.env.nonce()
        prompt = tester_prompt(self.packet, self.branch, self.tip, nonce)
        before = self.fp_all()()[0]
        res = self.start_role("tester", prompt)
        self.after_stop("tester", res)
        if self.fp_all()()[0] != before or self.tip_moved():
            self.finish("readonly_role_changed_tree")
        self.after_exit(res)
        parsed = gp.parse_verdict(res.reader.tagged_text(), nonce, len(self.packet.checks))
        if not parsed.ok:
            self.finish("result_unparsed")
        for n, verdict, _evidence in parsed.value:
            self.record_event("check_result", {"n": n, "verdict": verdict})
        self.verdicts = parsed.value
        words = {v for _n, v, _e in parsed.value}
        if "fail" in words:
            self.finish("check_failed")
        if "unclear" in words:
            self.finish("check_unclear")


    def check_run(self):
        nonce = self.env.nonce()
        prompt = check_prompt(self.packet, self.branch, self.tip, self.nfiles, self.verdicts, nonce)
        before = self.fp_all()()[0]
        res = self.start_role("check", prompt)
        self.after_stop("check", res)
        if self.fp_all()()[0] != before or self.tip_moved():
            self.finish("readonly_role_changed_tree")
        self.after_exit(res)
        parsed = gp.parse_check(res.reader.tagged_text(), nonce)
        if not parsed.ok:
            self.finish("result_unparsed")
        verdict = parsed.value[0]
        if verdict == "reject":
            self.finish("guide_rejected")
        if verdict != "accept":
            self.finish("guide_unclear")


def _feed(pipe, data):
    """The prompt goes to the child's standard input, then the pipe is closed. A child that is gone is not an error."""
    try:
        pipe.write(data)
    except (BrokenPipeError, OSError, ValueError):
        pass
    finally:
        try:
            pipe.close()
        except (BrokenPipeError, OSError, ValueError):
            pass


class _Signals:
    """SIGTERM, SIGHUP and Ctrl-C set the stop flag while a run is going (W9.R16.3); the old handlers come back after.
    Only the main thread may install a handler; elsewhere the flag is set by whoever owns the thread."""

    NAMES = (("SIGTERM", "SIGTERM"), ("SIGHUP", "SIGHUP"), ("SIGINT", "SIGINT"))

    def __init__(self, env):
        self.env, self.old = env, {}

    def __enter__(self):
        if threading.current_thread() is not threading.main_thread():
            return self
        for name, _w in self.NAMES:
            sig = getattr(signal, name, None)
            if sig is not None:
                self.old[sig] = signal.signal(sig, lambda *_a: self.env.stop.set("signal"))
        return self

    def __exit__(self, *exc):
        for sig, handler in self.old.items():
            signal.signal(sig, handler)
        return False


def _read_part(folder, rel, reader, name):
    """A part file the builder wrote: None if it is not there; raises goaldocs.PartError if it is not a regular file or
    does not parse (W9.R8.3 c and d). Read only, with a size cap, never through a link."""
    path = os.path.join(str(folder), rel)
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError:
        raise goaldocs.PartError("cannot be read") from None
    if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_PART_FILE:
        raise goaldocs.PartError("is not a regular file of a normal size")
    with open(path, "rb") as f:
        return reader(name, f.read(MAX_PART_FILE + 1))


# ----------------------------------------------------------------------------------------------- the task, end to end
def run_task(env, goal, task):
    """Run one queued task from `queued` to `in review`, or to whatever ends it. The caller holds the goal lock and has
    done the first steps of the supervisor (the tamper check, repair, expired approvals, lost supervisors). Returns an
    Outcome; raises nothing for a refusal, a failure or a stop. An unexpected error propagates: the caller exits 2."""
    run = _Run(env, goal, task)
    with _Signals(env):
        try:
            return run.go_pipeline()
        except _Done as d:
            return d.outcome
        except gs.RecordFailed:
            env.out(RECORD_FAILED)
            return Outcome(2, "", "", "record")

# ----------------------------------------------------------------------------------------------- the planning run


class _PlanRun(_Run):
    """The guide's planning run (W9.R5.1, W9.R8.15). It has no task: its events are the goal's, its worktree is
    `g-0007-plan` at BASE with no branch, and it is removed only when the plan is approved, denied or discarded."""

    def __init__(self, env, goal):
        self.env, self.goal, self.task = env, goal, "plan"
        self.root = env.root
        self.g = gs.read_goal(self.root, goal)
        self.t = {"state": "plan", "sha256": ""}
        self.packet = None
        self.writer = None
        self.worktree = None
        self.base = None
        self.tip = None
        self.spent = {}
        self.prior = 0
        self.own = ()

    def events(self):
        if self.writer is None:
            self.writer = self.open_writer(gs.goal_dir(self.root, self.goal) / "goal.events.jsonl")
        return self.writer

    def agent_of(self, role):
        return self.g["guide"]

    def model_effort(self, role):
        return self.g["guide_model"], self.g["guide_effort"]

    def ask_owner(self, cause, title):
        """Ask me first, a closed door, or a config problem before the plan exists: one queue decision, exit 3, and no
        change to the goal (the goal stays in `plan` with no packets, W9.R5.2)."""
        taskqueue.add_once(self.root, "decision", title,
                           "Answering this item starts nothing. Fix the cause, then start a new goal.", self.env.when())
        raise _Done(Outcome(3, "plan", "", cause))

    def finish(self, cause, **kw):
        self.ask_owner(cause, f"Goal {self.goal} could not start its planning run ({cause})")

    def stop_running(self, cause, **kw):
        kill_all(self.env)
        raise _Done(Outcome(3 if cause == "kill_switch" else 2, "plan", "", cause))

    def step_kill(self):
        if self.env.stop.is_set():
            raise _Done(Outcome(2, "plan", "signal", "signal_received"))
        if kill.stopped(kill.state(self.root)):
            kill_all(self.env)
            raise _Done(Outcome(3, "plan", "kill", "kill_switch"))

    def step_signal(self):
        if self.env.stop.is_set():
            raise _Done(Outcome(2, "plan", "signal", "signal_received"))

    def step_state(self, role):
        if self.g["plan"] is not None or self.g["approved"] or self.g["stopped"] or self.g["refused"]:
            raise _Done(Outcome(2, "plan", "", "state"))

    def step_rules(self, role, agent, platform):
        action = {"type": "goal_start", "goal": self.goal, "task": "plan", "role": "guide", "agent": agent,
                  "platform": platform, "budget_uu": int(self.g["plan_budget_uu"])}
        decision, logged = rules.check_and_log(json.dumps(action), self.root / "rules.yaml", self.root, self.env.when(),
                                               kill_state=kill.state(self.root))
        if not logged:
            raise _Done(Outcome(2, "plan", "", "unlogged"))
        if decision.answer == rules.NO:
            gs.stop_goal(self.root, self.goal, "owner", when=self.env.when(), now=self.env.now())
            raise _Done(Outcome(2, "stopped", "owner", "rules_said_no"))
        if decision.answer != rules.YES or decision.autonomy is not None:
            self.finish("rules_said_ask")

    def step_roles(self):
        return

    def step_worktree_preconditions(self):
        self.base = self.check_start()

    def task_or_none(self):
        return None

    def step_budget(self, role, agent, platform):
        today = self.env.when()
        try:
            u = units.load(self.root, today)
        except ConfigError:
            self.finish("agent_cannot_be_gated")
        ledger = budget.read_ledger(self.root)
        cap = goalbudget.cap(int(self.g["plan_budget_uu"]), int(self.g["plan_budget_uu"]), u.limits["per_run"],
                             goalbudget.day_left_uu(ledger, u, agent, platform, today))
        if cap < 1:
            self.finish("budget_said_ask")
        return cap, goalbudget.run_ids(ledger)

    def begin_builder(self, agent, cap):
        try:
            made = gg.make_plan(self.root, self.goal, self.base)
        except gg.Refused as r:
            self.finish(REFUSED_CAUSE[r.reason])
        except gg.GitError:
            self.finish("worktree_not_made")
        self.worktree = made.path
        path = made.path
        try:
            logbook.append(self.root, gs.worktree_entry(self.env.when(), self.goal, "", "made", base=self.base))
        except (UmwayiError, ValueError):
            self.env.out(RECORD_FAILED)
            raise _Done(Outcome(2, "", "", "record")) from None
        self.record_event("worktree", {"action": "made", "base": self.base[:8]})
        try:
            self.step_gate(agent, path)
        except _Done:
            self.remove_unused()
            raise

    def remove_unused(self):
        try:
            gg.remove_unused(self.root, self.goal, None, self.base)
        except UmwayiError:
            pass

    def run(self):
        e = self.env
        agent = self.agent_of("guide")
        nonce = e.nonce()
        self.step_kill()
        self.step_state("guide")
        platform = self.platform_of(agent)
        self.step_rules("guide", agent, platform)
        self.step_gate(agent)
        self.step_lock()
        self.step_worktree_preconditions()
        cap, before = self.step_budget("guide", agent, platform)
        self.begin_builder(agent, cap)
        model, effort = self.model_effort("guide")
        argv = child_argv(agent, cap, self.worktree, options_for(platform, model, effort))
        res = self.run_child("guide", argv, planning_prompt(self.g["text"], nonce), None, cap, before, agent, None)
        word = self.plan_word(res, nonce)
        if word is not None:
            gs.refuse_plan(self.root, self.goal, agent, word, when=e.when(), now=e.now())
            raise _Done(Outcome(2, "plan", "", word))
        return res

    def plan_word(self, res, nonce):
        """None, or the fixed word that refuses the plan (W9.R5.2, W9.R5.3). Stops end the run in place."""
        if res.why == "kill":
            kill_all(self.env)
            raise _Done(Outcome(3, "plan", "kill", "kill_switch"))
        if res.why == "signal":
            raise _Done(Outcome(2, "plan", "signal", "signal_received"))
        if res.why == "log":
            raise _Done(Outcome(2, "", "", "record"))
        if res.why == "owner":
            raise _Done(Outcome(2, "stopped", "owner", "owner_stop"))
        if res.why in ("stalled", "looping"):
            return "stalled" if res.why == "stalled" else "looping"
        if GIT.status(self.root, self.worktree) or GIT.head(self.root, self.worktree) != self.base:
            return "readonly"
        if res.over:
            return "budget"
        if res.code != 0:
            return "builder"
        parsed = gp.parse_result_line(res.reader.tagged_text(), "UMWAYI-PLAN", nonce, gp.MAX_PLAN_BYTES)
        if not parsed.ok:
            return "unclear"
        try:
            self.packets = gp.parse_plan(parsed.raw, file_size=self.file_size, is_private=self.is_private)
        except gp.PlanError as err:
            return err.word
        return None

    def file_size(self, rel):
        path = os.path.join(str(self.worktree), rel)
        try:
            st = os.lstat(path)
        except OSError:
            return None
        return st.st_size if stat.S_ISREG(st.st_mode) else None

    def is_private(self, rel):
        from umwayi import config
        try:
            private = config.load_config(self.root).private_paths
        except UmwayiError:
            return True  # fail closed: a root whose config cannot be read has every path private
        norm = rel.strip("/")
        return any(norm == p.strip("/") or norm.startswith(p.strip("/") + "/") for p in private)


def run_plan(env, goal):
    """The planning run of `goal start` (W9.R5.1): the guide is started once in the plan worktree with the planning
    prompt. On success the plan is recorded as a proposal (plan.json, the entry, the approval request, one queue row)
    and the Outcome has exit 0; a refused plan is exit 2 with its word and the goal stays in `plan` with no packets
    (no retry); a rule, the kill switch, the run lock or a worktree problem is exit 3 and changes nothing. The plan
    worktree stays until `remove_plan_worktree`."""
    run = _PlanRun(env, goal)
    with _Signals(env):
        try:
            res = run.run()
            gs.record_plan(env.root, goal, run.packets, run.agent_of("guide"), when=env.when(), now=env.now())
            return Outcome(0, "plan", "", "planned")
        except _Done as d:
            return d.outcome
        except gs.RecordFailed:
            env.out(RECORD_FAILED)
            return Outcome(2, "", "", "record")


def remove_plan_worktree(env, goal):
    """The plan's worktree is removed when the plan is approved, denied or discarded (W9.R8.15), by `goalgit.remove_plan`:
    only if it is clean, never forced. A plan whose tree changed (`readonly`) keeps it as evidence. Returns a word."""
    try:
        done = gg.remove_plan(env.root, goal)
    except UmwayiError:
        return "kept"
    if done.removed:
        try:
            logbook.append(env.root, gs.worktree_entry(env.when(), goal, "", "removed"))
        except (UmwayiError, ValueError):
            env.out(RECORD_FAILED)
        return "removed"
    return "none" if done.why == "gone" else "kept"


# ----------------------------------------------------------------------------------------------- merges and cleanup


def observe_merges(env, goal):
    """W9.R17.2. For each task `in review`, the read-only question `git merge-base --is-ancestor TIP main`. True moves the
    task to `merged` (reason observed, one entry) and then the cleanup of its worktree. Never fetches: the local `main` is
    the owner's. Returns the list of tasks moved."""
    moved = []
    for task in gs.list_tasks(env.root, goal):
        t = gs.read_task(env.root, goal, task)
        tip = t.get("tip") or ""
        if t["state"] != "in review" or not tip:
            continue
        if GIT.is_ancestor(env.root, tip):
            gs.change_state(env.root, goal, task, "merged", "observed", when=env.when(), now=env.now(), commit=tip)
            moved.append(task)
            cleanup_merged(env, goal, task, "observed")
    return moved


def declared_merge_problem(env, sha):
    """None, or a fixed word why the owner's `merged --commit SHA` is refused (W9.R17.3): the commit must exist and be on
    the local `main`. The command checks the terminal."""
    if not (isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha)):
        return "shape"
    if not GIT.commit_exists(env.root, sha):
        return "missing"
    if not GIT.is_ancestor(env.root, sha):
        return "not_on_main"
    return None


def cleanup_merged(env, goal, task, how):
    """Cleanup only after the owner's merged (W9.R8.13): `goalgit.remove_after_merged` (the task file says `merged`, the
    tree is clean, `git worktree remove PATH` without force), then one entry. A tree that is not clean, or git refusing,
    leaves it (listed by `status`). The branch is never deleted. Returns `removed`, `kept` or `none`."""
    try:
        done = gg.remove_after_merged(env.root, goal, task)
    except UmwayiError:
        return "kept"
    if done.why == "not merged" or done.why == "gone":
        return "none"
    if not done.removed:
        return "kept"
    try:
        logbook.append(env.root, gs.worktree_entry(env.when(), goal, task, "removed", how=how))
    except (UmwayiError, ValueError):
        env.out(RECORD_FAILED)
    return "removed"


def sweep_unused(env):
    """A worktree that was made and in which no builder ever started (the start failed after the creation, or the process
    died) is removed when clean at its base (W9.R8.13). Returns the (goal, task) removed."""
    out = []
    for goal in gs.list_goals(env.root):
        for task in gs.list_tasks(env.root, goal):
            t = gs.read_task(env.root, goal, task)
            if t["state"] in ("queued", "dropped", "plan", "merged") or not t.get("base"):
                continue
            path = GIT.worktree_path(env.root, goal, task)
            if not os.path.lexists(path):
                continue
            data = gs.events_path(env.root, goal, task)
            started = [ev for ev in (goallog.read(data.read_bytes())[0] if data.exists() else [])
                       if ev["kind"] == "started" and ev["data"]["role"] == "builder"]
            if started:
                continue
            try:
                if gg.remove_unused(env.root, goal, task, t["base"]).removed:
                    out.append((goal, task))
            except (UmwayiError, ValueError):
                pass
    return out


# ----------------------------------------------------------------------------------------------- the supervisor


def supervise(env, goal):
    """`goal run G` (design.md, "The supervisor, step by step", steps 2 to 10). The tamper check of the logbook and the
    strict parse of the goal entries come first; either failing raises and nothing starts. Then repair, expired
    approvals, a lost supervisor, the kill switch, the merge observation, the pick, and one task. The caller prints
    the report and maps an unexpected error to exit 2. A held goal lock raises `GoalLockBusy` (exit 3)."""
    with gs.lock(env.root):
        logbook.read_checked_chain(env.root)  # a broken chain or record stops everything (exit 2 by the caller)
        gs.view(env.root)
        when, now = env.when(), env.now()
        gs.repair(env.root, when=when, now=now)
        gs.deny_expired(env.root, when=when, now=now)
        gs.mark_lost(env.root, when=when, now=now, holding=True)
        sweep_unused(env)
        if kill.stopped(kill.state(env.root)):
            kill_all(env)
            return Outcome(3, "", "kill", "kill_switch")
        observe_merges(env, goal)
        g = gs.read_goal(env.root, goal)
        if not g["approved"] or g["stopped"]:
            return Outcome(2, "stopped" if g["stopped"] else "plan", g["stopped"] or "", "not_runnable")
        earlier_done = True
        for task in gs.list_tasks(env.root, goal):
            t = gs.read_task(env.root, goal, task)
            if t["dropped"] or t["state"] == "merged":
                continue
            if t["state"] == "queued" and earlier_done:
                return run_task(env, goal, task)
            return Outcome(EXIT_OF_STATE.get(t["state"], 2), t["state"], t["reason"], "waiting")
        return Outcome(0, "merged", "", "all_merged")
