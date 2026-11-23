"""Goal orchestration (W9.5): the state files of a goal, the strict `umwayi goal` logbook entries, the write order,
repair, the denial of expired approvals and the supervisor lock.

Nothing here starts an AI helper. The logbook is the record of state: a change is a logbook entry first and the files
follow it (W9.R13). Entries have fixed shapes, built and parsed here only (W9.R18). They hold ids, words, counts and
hashes, never the goal text, a prompt, a diff or helper output.

State lives under `.umwayi/goals/G-0007/` (mode 0700): `goal.json`, `plan.json`, `T-02.json` and `T-02.events.jsonl`.
`.umwayi/goal.lock` (mode 0600) is the one-supervisor lock (W9.R19).
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from umwayi import fsutil, goalbudget, goallog, goalpacket as gp, logbook, taskqueue
from umwayi.errors import UmwayiError

try:
    import fcntl
except ImportError:  # for example on Windows
    fcntl = None

SOURCE = "umwayi goal"
GOALS_REL = ".umwayi/goals"
LOCK_REL = ".umwayi/goal.lock"
MAX_GOAL_FILE = 8 * 1024
MAX_TASK_FILE = 64 * 1024
MAX_TEXT = 1000
ROLES = ("guide", "builder", "tester", "check")
GOAL_STOP_REASONS = gp.REASONS["stopped"] + ("budget",)
RECORD_FAILED = "umwayi could not write its record, so it stopped (exit 2)"
_BUSY = {errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES}


class GoalError(UmwayiError):
    """A refusal: nothing was changed (exit 2). Never quotes a path, a packet or an OS message."""


class RecordFailed(GoalError):
    """A record write failed at `step` (0 queue, 1 check, 2 entry, 3 file, 4 event, 5 tidy). The supervisor must stop."""

    def __init__(self, step):
        super().__init__(RECORD_FAILED)
        self.step = step


class GoalLockBusy(UmwayiError):
    """Another umwayi goal command holds the lock (exit 3)."""


class EntryError(UmwayiError):
    """A `umwayi goal` entry that is not one of the fixed shapes, or a sequence the state table does not allow."""


# ------------------------------------------------------------------------------------------------ files

_GOAL_ID = re.compile(r"^G-\d{4,}$")
_TASK_ID = re.compile(r"^T-\d{2}$")
_NAME = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
GOAL_KEYS = ("version", "goal", "text", "length", "text_sha256", "created", "guide", "guide_model", "guide_effort",
             "plan_budget_uu", "plan_hours", "wait_hours", "plan", "approved", "builder", "tester", "goal_budget_uu",
             "tester_model", "tester_effort", "stopped", "refused")
TASK_KEYS = ("version", "id", "state", "reason", "seq", "dropped", "packet", "sha256", "approval", "base", "branch", "tip",
             "commit", "spent_uu")
TASK_STATES = gp.STATES + ("plan", "dropped")


def _real_dir(path, create):
    if os.path.islink(path):
        raise GoalError("a state folder is a link, so nothing was done")
    if os.path.lexists(path):
        if not os.path.isdir(path):
            raise GoalError("a state folder is not a folder, so nothing was done")
    elif create:
        os.mkdir(path, 0o700)
    return Path(path)


def goals_dir(root, create=False):
    root = Path(root)
    _real_dir(root / ".umwayi", create)
    return _real_dir(root / GOALS_REL, create)


def goal_dir(root, goal, create=False):
    if not (isinstance(goal, str) and _GOAL_ID.fullmatch(goal)):
        raise GoalError("bad goal id")
    base = goals_dir(root, create)
    return _real_dir(base / goal, create)


def _task_id(task):
    if not (isinstance(task, str) and _TASK_ID.fullmatch(task)):
        raise GoalError("bad task id")
    return task


def _read_json(path, limit, what):
    if os.path.islink(path):
        raise GoalError(f"the {what} file is a link, so nothing was done")
    try:
        data = fsutil.read_regular(path, limit)
    except OSError:
        raise GoalError(f"the {what} file cannot be read (missing, not a regular file or too big)") from None
    try:
        obj = json.loads(data.decode("utf-8"))
    except (ValueError, RecursionError):
        raise GoalError(f"the {what} file is not valid JSON") from None
    if not isinstance(obj, dict):
        raise GoalError(f"the {what} file has the wrong shape")
    return obj


# W55a: the measured spend of the planning run, in UU, written once the run has ended (planned or refused). A goal file
# from before W55a has no such key, so the key is optional; when it is there it is a whole number of 0 or more.
PLAN_SPENT_KEY = "plan_spent_uu"
# W55b: where the first refused context entry of a refused plan was ({"task": N, "entry": N, "why": WORD}), never its
# path. Optional: only a plan refused for one context entry has it.
REFUSED_CONTEXT_KEY = "refused_context"
# The first protected path of a plan refused as `protected` ({"task": N, "entry": ENTRY}). ENTRY is the text of the
# protected list (goalpacket.PROTECTED) that matched, never the plan's own path. Optional.
REFUSED_PROTECTED_KEY = "refused_protected"


def _check_refused_context(c):
    if not (isinstance(c, dict) and set(c) == {"task", "entry", "why"} and c["why"] in gp.CONTEXT_WHYS
            and all(isinstance(c[k], int) and not isinstance(c[k], bool) and 1 <= c[k] <= 999 for k in ("task", "entry"))):
        raise GoalError("the goal file has the wrong shape")
    return c


def _check_refused_protected(c):
    if not (isinstance(c, dict) and set(c) == {"task", "entry"} and c["entry"] in gp.PROTECTED
            and isinstance(c["task"], int) and not isinstance(c["task"], bool) and 1 <= c["task"] <= 999):
        raise GoalError("the goal file has the wrong shape")
    return c


def refused_protected_words(c):
    """`task 1, docs-parts/`: the task and the protected list entry that matched, never the plan's own path."""
    return f"task {c['task']}, {c['entry']}"


def refused_context_words(c):
    """`task 1, entry 2, private`: the place of the refused context entry and why, never its path."""
    return f"task {c['task']}, entry {c['entry']}, {c['why']}"


def _check_goal(obj, goal):
    keys = set(obj) - {PLAN_SPENT_KEY, REFUSED_CONTEXT_KEY, REFUSED_PROTECTED_KEY}
    if keys != set(GOAL_KEYS) or obj["goal"] != goal or obj["version"] != 1:
        raise GoalError("the goal file has the wrong shape")
    if REFUSED_CONTEXT_KEY in obj:
        _check_refused_context(obj[REFUSED_CONTEXT_KEY])
    if REFUSED_PROTECTED_KEY in obj:
        _check_refused_protected(obj[REFUSED_PROTECTED_KEY])
    if PLAN_SPENT_KEY in obj:
        v = obj[PLAN_SPENT_KEY]
        if not (isinstance(v, int) and not isinstance(v, bool) and v >= 0):
            raise GoalError("the goal file has the wrong shape")
    return obj


def _with_plan_spent(g, plan_spent_uu):
    if plan_spent_uu is None:
        return dict(g)
    if not (isinstance(plan_spent_uu, int) and not isinstance(plan_spent_uu, bool) and plan_spent_uu >= 0):
        raise GoalError("the plan spend must be a whole number of UU")
    return dict(g, **{PLAN_SPENT_KEY: plan_spent_uu})


def plan_used_uu(g):
    """The UU the planning run counts for in what `status`, `report` and the goal map show: the measured spend when
    the run recorded it (W55a), else, for a goal from before W55a, the plan budget once a plan exists (the old,
    safe over-count). The caps of the supervisor still count the whole plan budget."""
    if PLAN_SPENT_KEY in g:
        return int(g[PLAN_SPENT_KEY])
    return int(g["plan_budget_uu"]) if g["plan"] is not None or g["approved"] else 0


# W56: a builder blocked by the rules gate. The words come from fixed lists only: the answer is No or Ask me first, the
# action type one of BLOCK_TYPES (any other tool type is `tool_other`), the rule an id of rules.yaml or `none` when no
# rule matched (an id that rules.yaml no longer holds is `unlisted`). Never a command, a path or any other argument.
BLOCKED_KEY = "blocked"
BLOCK_ANSWERS = ("No", "Ask me first")
BLOCK_TYPES = tuple("tool_" + n for n in (
    # the Kiro tool ids of adapters/kiro/rules.example.yaml
    "read_file", "grep_search", "execute_bash", "execute_pwsh", "fs_write", "fs_append", "str_replace", "delete_file",
    # the tools of adapters/common/umwayi_gate.py FIELDS (Claude Code and the generic adapter)
    "bash", "powershell", "write", "edit", "multiedit", "read", "notebookedit", "glob", "grep", "webfetch", "websearch",
    "agent",
    # the shell tool of rules.SHELL_TYPES that is in neither list above (W55b)
    "shell",
    # the fixed words of umwayi_gate.type_for, and the word for every other tool
    "mcp", "unknown", "long_name", "other"))
BLOCK_RULE_RX = r"[a-z0-9][a-z0-9_-]{0,99}"
# W55b: the first word of a blocked shell command, in the shape of rules.command_word (`other` for any other word)
BLOCK_COMMAND_RX = r"[a-z][a-z_.+-]{0,21}[0-9]{0,2}"
BLOCK_SHELL_TYPES = ("tool_bash", "tool_powershell", "tool_execute_bash", "tool_execute_pwsh", "tool_shell")  # rules.SHELL_TYPES
BLOCK_KEYS = {"rule", "answer", "type"}


def block_words(rule_id, answer, action_type, rule_ids, command=None):
    """The fixed words of one block: {"rule", "answer", "type"}, and "command" (W55b) for a shell call whose entry named
    the first word of its command. `rule_ids` is the set of ids in rules.yaml now."""
    if answer not in BLOCK_ANSWERS:
        raise ValueError("answer")
    if rule_id is None:
        rule = "none"
    elif isinstance(rule_id, str) and re.fullmatch(BLOCK_RULE_RX, rule_id) and rule_id in rule_ids:
        rule = rule_id
    else:
        rule = "unlisted"
    if action_type in BLOCK_TYPES:
        kind = action_type
    elif isinstance(action_type, str) and action_type.startswith("tool_mcp_"):
        kind = "tool_mcp"  # a Kiro MCP tool is mcp_SERVER_TOOL: the server and tool names are not kept
    else:
        kind = "tool_other"
    out = {"rule": rule, "answer": answer, "type": kind}
    if command is not None and kind in BLOCK_SHELL_TYPES:
        out["command"] = command if isinstance(command, str) and re.fullmatch(BLOCK_COMMAND_RX, command) else "other"
    return out


def _check_blocked(b):
    if not (isinstance(b, dict) and set(b) in (BLOCK_KEYS, BLOCK_KEYS | {"command"}) and b["answer"] in BLOCK_ANSWERS
            and b["type"] in BLOCK_TYPES and isinstance(b["rule"], str) and re.fullmatch(BLOCK_RULE_RX, b["rule"])):
        raise GoalError("the task file has the wrong shape")
    if "command" in b and not (b["type"] in BLOCK_SHELL_TYPES and isinstance(b["command"], str)
                               and re.fullmatch(BLOCK_COMMAND_RX, b["command"])):
        raise GoalError("the task file has the wrong shape")
    return b


def _command_part(b):
    return f", command word {b['command']}" if "command" in b else ""


def block_sentence(b):
    """`rule kiro-ask-shell gave Ask me first for action type tool_execute_bash` (or `no rule gave ...`), and for a shell
    call `..., command word git` (W55b)."""
    who = "no rule" if b["rule"] == "none" else f"rule {b['rule']}"
    return f"{who} gave {b['answer']} for action type {b['type']}{_command_part(b)}"


# W54: the measured spend of each role of a task, in UU, kept when every run of that role was settled with a measured
# reading; `null` once one was not. Optional, so older task files read. It is the goal history a proposal reads.
MEASURED_KEY = "measured_uu"
MEASURED_ROLES = ("builder", "tester", "check")


def _check_measured(m):
    if not (isinstance(m, dict) and set(m) <= set(MEASURED_ROLES)
            and all(v is None or (isinstance(v, int) and not isinstance(v, bool) and v >= 0) for v in m.values())):
        raise GoalError("the task file has the wrong shape")
    return m


def _check_task(obj, task):
    keys = set(obj) - {BLOCKED_KEY, MEASURED_KEY}
    if keys != set(TASK_KEYS) or obj["id"] != task or obj["version"] != 1 or obj["state"] not in TASK_STATES:
        raise GoalError("the task file has the wrong shape")
    if BLOCKED_KEY in obj:
        _check_blocked(obj[BLOCKED_KEY])
    if not (isinstance(obj["seq"], int) and not isinstance(obj["seq"], bool) and obj["seq"] >= 0):
        raise GoalError("the task file has the wrong shape")
    if MEASURED_KEY in obj:
        _check_measured(obj[MEASURED_KEY])
    try:
        gp.packet_from_dict(obj["packet"])
    except ValueError:
        raise GoalError("the task file has the wrong shape") from None
    return obj


def read_goal(root, goal):
    return _check_goal(_read_json(goal_dir(root, goal) / "goal.json", MAX_GOAL_FILE, "goal"), goal)


def read_task(root, goal, task):
    _task_id(task)
    return _check_task(_read_json(goal_dir(root, goal) / f"{task}.json", MAX_TASK_FILE, "task"), task)


def _dump(obj, limit):
    data = (json.dumps(obj, sort_keys=True, indent=1) + "\n").encode("utf-8")
    if len(data) > limit:
        raise GoalError("a state file would be too big")
    return data


def _write_file(path, data):
    """The one write of a state file: atomic, mode 0600. A test replaces this to inject a fault."""
    fsutil.atomic_write(Path(path), data, 0o600)


def write_goal(root, goal, obj):
    _write_file(goal_dir(root, goal) / "goal.json", _dump(_check_goal(obj, goal), MAX_GOAL_FILE))


def write_task(root, goal, task, obj):
    _task_id(task)
    _write_file(goal_dir(root, goal) / f"{task}.json", _dump(_check_task(obj, task), MAX_TASK_FILE))


def list_goals(root):
    d = goals_dir(root)
    if not d.exists():
        return []
    return sorted(p.name for p in d.iterdir() if _GOAL_ID.fullmatch(p.name) and p.is_dir() and not p.is_symlink())


def list_tasks(root, goal):
    d = goal_dir(root, goal)
    return sorted(p.stem for p in d.glob("T-??.json") if _TASK_ID.fullmatch(p.stem))


def events_path(root, goal, task):
    return goal_dir(root, goal) / f"{_task_id(task)}.events.jsonl"


def _logged_goal_ids(root):
    ids = set()
    for e in logbook.read_checked(root):
        if e.source == SOURCE:
            ids |= {m for m in re.findall(r"G-\d{4,}", e.added)}
    return ids


def next_goal_id(root):
    nums = [int(g[2:]) for g in list_goals(root)] + [int(g[2:]) for g in _logged_goal_ids(root)]
    return f"G-{max(nums, default=0) + 1:04d}"


# ------------------------------------------------------------------------------------------------ the lock


@contextmanager
def lock(root):
    """The one supervisor per root (W9.R19.3): flock on `.umwayi/goal.lock`. Held means exit 3."""
    if fcntl is None:
        raise GoalError("file locking is not available here, so nothing was done")
    _real_dir(Path(root) / ".umwayi", True)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(Path(root) / LOCK_REL, flags, 0o600)
    except OSError:
        raise GoalError("the goal lock cannot be opened (is it a link or a folder?)") from None
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            if e.errno in _BUSY:
                raise GoalLockBusy("another umwayi goal command holds the goal lock (.umwayi/goal.lock). "
                                   "Nothing was done.") from None
            raise GoalError("the operating system refused the goal lock") from None
        try:
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        os.close(fd)


def lock_free(root):
    p = Path(root) / LOCK_REL
    if not os.path.lexists(p):
        return True
    try:
        with lock(root):
            return True
    except GoalLockBusy:
        return False
    except GoalError:
        return False


# ------------------------------------------------------------------------------------------------ entry shapes

_ID = {"g": r"G-\d{4,}", "t": r"T-\d{2}"}
_NAME_RX = r"[a-z][a-z0-9-]{0,31}"
_HEX_RX = r"[0-9a-f]{8,64}"
_H8_RX = r"[0-9a-f]{8}"
_BRANCH_RX = r"umwayi/g-\d{4,}-t-\d{2}"
_DT_RX = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}"
_STATE_RX = "|".join(re.escape(s) for s in gp.STATES)
_REASON_RX = "|".join(sorted({re.escape(r) for rs in gp.REASONS.values() for r in rs}))
_ROLE_RX = "|".join(ROLES)
_WORD_RX = r"[a-z]{3,12}"
_N = r"\d{1,9}"

# name -> (template, {slot: regex}). A checked line is a sequence of these sentences and nothing else.
FACTS = {
    "none": ("Nothing else was checked.", {}),
    "kill": ("Kill switch off.", {}),
    "rules": ("Rules check Yes (goal_start).", {}),
    "packet": ("Packet {h} unchanged.", {"h": _H8_RX}),
    "lock": ("Run lock free.", {}),
    "spent": ("Spent {a} of {b} UU.", {"a": _N, "b": _N}),
    "scope": ("Scope: {n} files, all allowed.", {"n": _N}),
    "tester": ("Tester {name}: {p} of {m} checks pass.", {"name": _NAME_RX, "p": _N, "m": _N}),
    "guide": ("Guide {name}: {word}.", {"name": _NAME_RX, "word": "accept|reject|unclear"}),
    "queue": ("Queue row added first.", {}),
    "default_no": ("Default answer No.", {}),
    "row_closed": ("Queue row closed.", {}),
    "roles": ("The tester and the guide are not the builder.", {}),
    "plan_ok": ("The plan passed every check.", {}),
    "plan_bad": ("First problem: {word}.", {"word": _WORD_RX}),
    # W54: the budgets the owner took from the system's proposal at approval (task ids and UU, and the goal budget)
    "proposed": ("Proposed and accepted: {items}.",
                 {"items": r"(?:T-\d{2} \d{1,9}(?:, T-\d{2} \d{1,9})*(?:; goal budget \d{1,9})?|goal budget \d{1,9})"}),
    # W55b: the place of the first refused context entry of a plan and why, never the path
    "plan_context": ("Context entry {entry} of task {task}: {why}.",
                     {"entry": r"\d{1,3}", "task": r"\d{1,3}", "why": "|".join(gp.CONTEXT_WHYS)}),
    # the task of a plan refused as protected and the protected list entry that matched, never the plan's own path
    "plan_protected": ("Protected path of task {task}: {entry}.",
                       {"task": r"\d{1,3}", "entry": "|".join(re.escape(x) for x in gp.PROTECTED)}),
    # W78 5(g): counts only, per task: the rules' refusals and Ask me first answers the umwayi checks wrote while the task ran, and
    # the watched-file findings
    "counted": ("Counted from the logbook since the task started: {no} No, {ask} Ask me first, {guard} guard findings.",
                {"no": r"\d{1,6}", "ask": r"\d{1,6}", "guard": r"\d{1,6}"}),
    "main_ok": ("The local main is not behind origin/main.", {}),
    "no_leftover": ("No leftover.", {}),
    "clean_base": ("Clean at base.", {}),
    "gate_ok": ("Gate checks passed for the worktree.", {}),
    "wt_count": ("Worktrees in the root: {a} of {b}.", {"a": _N, "b": _N}),
    "wt_clean": ("The worktree was clean.", {}),
    "wt_removed": ("The command git worktree remove ran without force.", {}),
    "branch_kept": ("The branch {branch} was kept.", {"branch": _BRANCH_RX}),
    # W55a: the fixed word of the cause of a failed task (a key of goalpacket.CAUSES), never any content
    "cause": ("Cause: {word}.", {"word": "|".join(sorted(gp.CAUSES))}),
    # W56: the rule and the action type of the call that blocked the builder, fixed words only (block_words)
    "blocked": ("Blocked: {who} gave {answer} for action type {type}{cmd}.",
                {"who": rf"no rule|rule {BLOCK_RULE_RX}", "answer": "|".join(BLOCK_ANSWERS),
                 "type": "|".join(BLOCK_TYPES), "cmd": rf"(?:, command word {BLOCK_COMMAND_RX})?"}),
}


def blocked_fact(b):
    """The `blocked` fact of the fixed words of one block."""
    _check_blocked(b)
    return ("blocked", {"who": "no rule" if b["rule"] == "none" else f"rule {b['rule']}", "answer": b["answer"],
                        "type": b["type"], "cmd": _command_part(b)})


def _blocked_of_fact(d):
    who = d["who"]
    out = {"rule": "none" if who == "no rule" else who[len("rule "):], "answer": d["answer"], "type": d["type"]}
    if d.get("cmd"):
        out["command"] = d["cmd"][len(", command word "):]
    return out
NOT_DONE = {
    "text": "The goal text, the prompt and the helper's output were not recorded.",
    "nodiff": "No diff, file content or helper output was recorded. Nothing was pushed or merged.",
    "nothing": "Nothing was started and nothing was answered.",
    "wt": "Nothing was pushed or merged. The owner's working copy was not touched.",
    "nodelete": "No branch was deleted and nothing was forced.",
    "counts": "Only three numbers were kept. A count is not proof of obedience: a helper with none may never have tried, and a "
              "count says nothing of what was not asked.",
}


def _compile(template, slots):
    out, pos = [], 0
    for m in re.finditer(r"\{(\w+)\}", template):
        out.append(re.escape(template[pos:m.start()]))
        out.append(f"(?P<{m.group(1)}>{slots[m.group(1)]})")
        pos = m.end()
    out.append(re.escape(template[pos:]))
    return re.compile("".join(out))


_FACT_RX = {name: _compile(t, s) for name, (t, s) in FACTS.items()}
_SENTENCE_SPLIT = re.compile(r"(?<=\.) (?=[A-Z])")


def _checked(facts):
    out = []
    for item in facts:
        try:
            name, args = item
            template, slots = FACTS[name]
        except (KeyError, TypeError, ValueError):
            raise ValueError("unknown fact") from None
        text = template.format(**args)
        if not _FACT_RX[name].fullmatch(text):
            raise ValueError("fact value outside its pattern")
        out.append(text)
    if not out:
        raise ValueError("a checked line needs a fact")
    return " ".join(out)


def _parse_checked(text):
    facts = []
    for sentence in _SENTENCE_SPLIT.split(text):
        for name, rx in _FACT_RX.items():
            m = rx.fullmatch(sentence)
            if m:
                facts.append((name, m.groupdict()))
                break
        else:
            raise EntryError("a umwayi goal entry is not one of the fixed shapes")
    return facts


def _entry(when, added, facts, not_done):
    return logbook.Entry(when, SOURCE, added, _checked(facts), NOT_DONE[not_done])


def _need(rx, value):
    if not (isinstance(value, str) and re.fullmatch(rx, value)):
        raise ValueError("value outside its pattern")
    return value


def _gid(g):
    return _need(_ID["g"], g)


def _tid(t):
    return _need(_ID["t"], t)


def _list(ids):
    ids = [_tid(i) for i in ids]
    return ",".join(ids) if ids else "none"


def state_entry(when, goal, task, old, new, reason, role=None, agent=None, cap_uu=None, branch=None, tip=None, base=None,
                commit=None, facts=None, not_done="text"):
    if not gp.can_move(old, new) or old == "plan" or reason not in gp.REASONS.get(new, ()):
        raise ValueError("not a move of the state table")
    s = f"Goal {_gid(goal)} task {_tid(task)}: {old} to {new} (reason {reason})"
    if (role is None) != (agent is None):
        raise ValueError("role and agent go together")
    if role is not None:
        if role not in ROLES:
            raise ValueError("role")
        s += f", role {role}, agent {_need(_NAME_RX, agent)}"
    if cap_uu is not None:
        s += f", cap {_need(_N, str(cap_uu))} UU"
    if branch is not None or tip is not None:
        s += f", branch {_need(_BRANCH_RX, branch)}, tip {_need(_HEX_RX, tip)}"
    if base is not None:
        s += f", base {_need(_HEX_RX, base)}"
    if commit is not None:
        s += f", commit {_need(_HEX_RX, commit)}"
    return _entry(when, s, facts or [("none", {})], not_done)


def started_entry(when, goal, length, h8, guide, plan_uu):
    return _entry(when, f"Goal {_gid(goal)} started: goal text {_need(_N, str(length))} characters sha256 {_need(_H8_RX, h8)}, "
                        f"guide {_need(_NAME_RX, guide)}, plan budget {_need(_N, str(plan_uu))} UU", [("none", {})], "text")


def planned_entry(when, goal, agent, packets, minutes, length, h8):
    return _entry(when, f"Goal {_gid(goal)} planned by agent {_need(_NAME_RX, agent)}: {_need(_N, str(packets))} packets, "
                        f"{_need(_N, str(minutes))} minutes, goal text {_need(_N, str(length))} characters sha256 "
                        f"{_need(_H8_RX, h8)}", [("plan_ok", {})], "text")


def plan_refused_entry(when, goal, agent, word, context=None, protected=None):
    facts = [("plan_bad", {"word": word})]
    if protected is not None:
        facts.append(("plan_protected", {"task": str(protected["task"]), "entry": protected["entry"]}))
    if context is not None:
        facts.append(("plan_context", {"entry": str(context["entry"]), "task": str(context["task"]), "why": context["why"]}))
    return _entry(when, f"Goal {_gid(goal)} plan refused (reason {_need(_WORD_RX, word)}), guide {_need(_NAME_RX, agent)}",
                  facts, "nothing")


def accepted_items(accepted, goal_budget=None):
    """`T-01 182, T-03 95; goal budget 402`: what was taken from the proposal (W54), or None when nothing was."""
    parts = ", ".join(f"{_tid(t)} {_need(_N, str(n))}" for t, n in accepted)
    if goal_budget is not None:
        g = f"goal budget {_need(_N, str(goal_budget))}"
        parts = f"{parts}; {g}" if parts else g
    return parts or None


def plan_approved_entry(when, goal, kept, dropped, builder, tester, guide, goal_budget, accepted=None):
    facts = [("roles", {})] + ([("proposed", {"items": accepted})] if accepted else [])
    return _entry(when, f"Goal {_gid(goal)} plan approved: kept {_list(kept)}, dropped {_list(dropped)}, builder "
                        f"{_need(_NAME_RX, builder)}, tester {_need(_NAME_RX, tester)}, guide {_need(_NAME_RX, guide)}, "
                        f"goal budget {_need(_N, str(goal_budget))} UU", facts, "text")


def approval_requested_entry(when, goal, task, reason, deadline):
    _need(_DT_RX, deadline)
    if task:
        s = (f"Approval requested: task {_tid(task)} of goal {_gid(goal)} needs the owner (reason "
             f"{_need(_REASON_RX, reason)}), deadline {deadline} UTC")
    else:
        s = f"Approval requested: plan of goal {_gid(goal)} waits for the owner, deadline {deadline} UTC"
    return _entry(when, s, [("queue", {}), ("default_no", {})], "nothing")


def approval_answered_entry(when, goal, task, answer):
    if answer not in ("yes", "no"):
        raise ValueError("answer")
    what = f"task {_tid(task)} of goal {_gid(goal)}" if task else f"plan of goal {_gid(goal)}"
    return _entry(when, f"Approval answered: {what}, answer {answer}", [("none", {})], "nothing")


def approval_denied_entry(when, goal, task, deadline):
    what = f"task {_tid(task)} of goal {_gid(goal)}" if task else f"plan of goal {_gid(goal)}"
    return _entry(when, f"Approval denied: {what} (timed out), deadline {_need(_DT_RX, deadline)} UTC",
                  [("row_closed", {}), ("default_no", {})], "nothing")


def goal_stopped_entry(when, goal, reason):
    if reason not in GOAL_STOP_REASONS:
        raise ValueError("reason")
    return _entry(when, f"Goal {_gid(goal)} stopped (reason {reason})", [("none", {})], "text")


def worktree_entry(when, goal, task, action, base=None, how=None):
    g = _gid(goal)
    if action == "made":
        base = _need(_HEX_RX, base)
        if task:
            s = f"Goal {g} task {_tid(task)}: worktree made, base {base}, branch {gp.branch_name(g, task)}"
            facts = [("main_ok", {}), ("no_leftover", {}), ("clean_base", {}), ("gate_ok", {})]
        else:
            s, facts = f"Goal {g} plan worktree made, base {base}", [("main_ok", {}), ("clean_base", {})]
        return _entry(when, s, facts, "wt")
    if action == "removed":
        if task:
            if how not in ("observed", "declared"):
                raise ValueError("how")
            return _entry(when, f"Goal {g} task {_tid(task)}: worktree removed after merged ({how})",
                          [("wt_clean", {}), ("wt_removed", {}), ("branch_kept", {"branch": gp.branch_name(g, task)})],
                          "nodelete")
        return _entry(when, f"Goal {g} plan worktree removed", [("wt_clean", {}), ("wt_removed", {})], "nodelete")
    raise ValueError("action")


def counts_entry(when, goal, task, no, ask, guard):
    """W78 5(g): one entry per task end, with three numbers and nothing else. Never a word, a path or a rule id."""
    return _entry(when, f"Goal {_gid(goal)} task {_tid(task)}: counts",
                  [("counted", {"no": str(no), "ask": str(ask), "guard": str(guard)})], "counts")


def docs_entry(when, status_parts, limits_parts):
    return _entry(when, f"Docs built: {_need(_N, str(status_parts))} status parts, {_need(_N, str(limits_parts))} limits parts",
                  [("none", {})], "nothing")


_G, _T, _NM = f"(?P<goal>{_ID['g']})", f"(?P<task>{_ID['t']})", _NAME_RX
_SHAPES = (
    ("state", re.compile(
        rf"Goal {_G} task {_T}: (?P<old>{_STATE_RX}) to (?P<new>{_STATE_RX}) \(reason (?P<reason>{_REASON_RX})\)"
        rf"(?:, role (?P<role>{_ROLE_RX}), agent (?P<agent>{_NM}))?(?:, cap (?P<cap_uu>{_N}) UU)?"
        rf"(?:, branch (?P<branch>{_BRANCH_RX}), tip (?P<tip>{_HEX_RX}))?(?:, base (?P<base>{_HEX_RX}))?"
        rf"(?:, commit (?P<commit>{_HEX_RX}))?")),
    ("started", re.compile(rf"Goal {_G} started: goal text (?P<length>{_N}) characters sha256 (?P<h8>{_H8_RX}), guide "
                           rf"(?P<guide>{_NM}), plan budget (?P<plan_uu>{_N}) UU")),
    ("planned", re.compile(rf"Goal {_G} planned by agent (?P<agent>{_NM}): (?P<packets>{_N}) packets, (?P<minutes>{_N}) "
                           rf"minutes, goal text (?P<length>{_N}) characters sha256 (?P<h8>{_H8_RX})")),
    ("plan_refused", re.compile(rf"Goal {_G} plan refused \(reason (?P<word>{_WORD_RX})\), guide (?P<agent>{_NM})")),
    ("plan_approved", re.compile(
        rf"Goal {_G} plan approved: kept (?P<kept>T-\d{{2}}(?:,T-\d{{2}})*), dropped "
        rf"(?P<dropped>none|T-\d{{2}}(?:,T-\d{{2}})*), builder (?P<builder>{_NM}), tester (?P<tester>{_NM}), guide "
        rf"(?P<guide>{_NM}), goal budget (?P<budget>{_N}) UU")),
    ("approval_requested", re.compile(
        rf"Approval requested: task {_T} of goal {_G} needs the owner \(reason (?P<reason>{_REASON_RX})\), deadline "
        rf"(?P<deadline>{_DT_RX}) UTC")),
    ("approval_requested", re.compile(
        rf"Approval requested: plan of goal {_G} waits for the owner, deadline (?P<deadline>{_DT_RX}) UTC")),
    ("approval_answered", re.compile(rf"Approval answered: task {_T} of goal {_G}, answer (?P<answer>yes|no)")),
    ("approval_answered", re.compile(rf"Approval answered: plan of goal {_G}, answer (?P<answer>yes|no)")),
    ("approval_denied", re.compile(
        rf"Approval denied: task {_T} of goal {_G} \(timed out\), deadline (?P<deadline>{_DT_RX}) UTC")),
    ("approval_denied", re.compile(
        rf"Approval denied: plan of goal {_G} \(timed out\), deadline (?P<deadline>{_DT_RX}) UTC")),
    ("goal_stopped", re.compile(rf"Goal {_G} stopped \(reason (?P<reason>{'|'.join(GOAL_STOP_REASONS)})\)")),
    ("worktree", re.compile(rf"Goal {_G} task {_T}: worktree made, base (?P<base>{_HEX_RX}), branch (?P<branch>{_BRANCH_RX})")),
    ("worktree", re.compile(rf"Goal {_G} task {_T}: worktree removed after merged \((?P<how>observed|declared)\)")),
    ("worktree", re.compile(rf"Goal {_G} plan worktree made, base (?P<base>{_HEX_RX})")),
    ("worktree", re.compile(rf"Goal {_G} plan worktree removed")),
    ("docs_built", re.compile(rf"Docs built: (?P<status>{_N}) status parts, (?P<limits>{_N}) limits parts")),
    ("counts", re.compile(rf"Goal {_G} task {_T}: counts")),
)
_NOT_DONE_VALUES = set(NOT_DONE.values())


def parse_entry(entry):
    """The fields of one `umwayi goal` entry, or an EntryError. Strict: the added line, the checked sentences and the
    not-done sentence must each be one of the fixed shapes. The error never quotes the entry."""
    bad = EntryError("a umwayi goal entry is not one of the fixed shapes")
    if getattr(entry, "source", None) != SOURCE:
        raise bad
    for kind, rx in _SHAPES:
        m = rx.fullmatch(entry.added)
        if not m:
            continue
        d = m.groupdict()
        if entry.not_done not in _NOT_DONE_VALUES:
            raise bad
        rec = SimpleNamespace(kind=kind, goal=d.get("goal"), task=d.get("task") or "", old=None, new=None, reason=None,
                              role=None, agent=None, cap_uu=None, branch=None, tip=None, base=None, commit=None,
                              deadline=None, answer=None, how=None, fields=d, facts=_parse_checked(entry.checked))
        for k in ("old", "new", "reason", "role", "agent", "branch", "tip", "base", "commit", "deadline", "answer", "how"):
            if d.get(k) is not None:
                setattr(rec, k, d[k])
        if d.get("cap_uu") is not None:
            rec.cap_uu = int(d["cap_uu"])
        if kind == "state" and (not gp.can_move(rec.old, rec.new) or rec.reason not in gp.REASONS[rec.new]):
            raise bad
        if kind == "state" and (rec.branch is not None) != (rec.tip is not None):
            raise bad
        if kind in ("approval_requested", "approval_answered", "approval_denied"):
            rec.is_plan = not rec.task
        return rec
    raise bad


# ------------------------------------------------------------------------------------------------ the derived state


class TaskView:
    def __init__(self, tid):
        self.id, self.state, self.reason, self.prev, self.seq = tid, "queued", "approved", None, 0
        self.role = self.agent = self.base = self.branch = self.tip = self.commit = self.deadline = None
        self.cause = None  # W55a: the cause word of the last state entry, when it named one
        self.blocked = None  # W56: the fixed words of the block named by the last state entry, when it named one


class GoalView:
    def __init__(self, gid):
        self.id, self.planned, self.refused, self.approved = gid, False, None, False
        self.kept, self.dropped, self.builder, self.tester, self.guide = (), (), None, None, None
        self.goal_budget, self.stopped, self.plan_deadline, self.tasks = None, None, None, {}


def parse_entries(entries):
    """Derive every goal from the `umwayi goal` entries (oldest first), strictly. Entries of other sources are ignored.
    A shape that is not one of the fixed ones, or a sequence the state table does not allow, is an EntryError."""
    goals = {}
    bad = EntryError("a umwayi goal entry does not follow the entries before it")

    def need(rec):
        v = goals.get(rec.goal)
        if v is None:
            raise bad
        return v

    for e in entries:
        if getattr(e, "source", None) != SOURCE:
            continue
        r = parse_entry(e)
        k = r.kind
        if k == "docs_built":
            continue
        if k == "started":
            if r.goal in goals:
                raise bad
            goals[r.goal] = GoalView(r.goal)
            continue
        v = need(r)
        if k == "planned":
            if v.planned or v.refused:
                raise bad
            v.planned = True
        elif k == "plan_refused":
            if v.planned or v.refused:
                raise bad
            v.refused = r.fields["word"]
        elif k == "plan_approved":
            if not v.planned or v.approved:
                raise bad
            kept = tuple(r.fields["kept"].split(","))
            dropped = () if r.fields["dropped"] == "none" else tuple(r.fields["dropped"].split(","))
            if len(set(kept)) != len(kept) or set(kept) & set(dropped):
                raise bad
            v.approved, v.kept, v.dropped = True, kept, dropped
            v.builder, v.tester, v.guide, v.goal_budget = r.fields["builder"], r.fields["tester"], r.fields["guide"], int(
                r.fields["budget"])
            v.tasks = {t: TaskView(t) for t in kept}
        elif k == "goal_stopped":
            v.stopped = r.reason
        elif k == "state":
            t = v.tasks.get(r.task)
            if t is None or t.state != r.old:
                raise bad
            t.prev, t.state, t.reason, t.seq = r.old, r.new, r.reason, t.seq + 1
            t.cause = next((d["word"] for name, d in r.facts if name == "cause"), None)
            t.blocked = next((_blocked_of_fact(d) for name, d in r.facts if name == "blocked"), None)
            for a in ("role", "agent", "base", "branch", "tip", "commit"):
                if getattr(r, a) is not None:
                    setattr(t, a, getattr(r, a))
        elif k in ("worktree", "counts"):
            if r.task and r.task not in v.tasks:
                raise bad
        elif k == "approval_requested":
            if r.is_plan:
                if not v.planned or v.approved or v.stopped:
                    raise bad
                v.plan_deadline = r.deadline
            else:
                t = v.tasks.get(r.task)
                if t is None or t.state in ("merged", "failed", "stopped"):
                    raise bad
                t.deadline = r.deadline
        else:  # answered or denied
            if r.is_plan:
                if v.plan_deadline is None:
                    raise bad
                v.plan_deadline = None
            else:
                t = v.tasks.get(r.task)
                if t is None or t.deadline is None:
                    raise bad
                t.deadline = None
    return goals


def view(root):
    """The goals as the logbook says (a tamper checked read). The files may be behind; this is the truth."""
    return parse_entries(logbook.read_checked(root))


# ------------------------------------------------------------------------------------------------ the write order

# W9.R13.1. The order of a change: (0) the queue row, (1) the logbook and the folder are writable, (2) the logbook entry,
# (3) the state file, (4) the event. The entry is the change; the files follow it. `tidy` closes a queue row afterwards.
STEP_ORDER = ("queue", "check", "probe", "entry", "file", "event", "tidy")
STEP_NO = {"queue": 0, "check": 1, "probe": 1, "entry": 2, "file": 3, "event": 4, "tidy": 5}


def _queue_row(root, title, recommendation, when):
    row, _added = taskqueue.add_once(root, "decision", title, recommendation, when)
    return row.id


def _check_logbook(root, when):
    logbook.check_writable(root, when)


def _probe(writer):
    writer.probe()


def _append_entry(root, entry):
    logbook.append(root, entry)


def _append_event(writer, kind, data):
    writer.append(kind, data)


def _close_row(root, row_id, text, when):
    """Answer and close an open queue row with the functions the command line uses. A row already closed is left."""
    rows = [r for r in taskqueue.list_rows(root) if r.id == row_id and r.status == "open"]
    if rows:
        taskqueue.answer(root, row_id, text, when, revisit_if="none")
        taskqueue.close(root, row_id, when)


def _run_step(step, fn, *args, **kwargs):
    """Run one step. Any failure is a RecordFailed with the step number; nothing quotes the cause."""
    try:
        return fn(*args, **kwargs)
    except Exception:
        raise RecordFailed(STEP_NO[step]) from None


def _commit(root, when, now, probe_path, entries, files, queue=None, event=None, tidy=None):
    """One change in the fixed order. `files(ctx)` gives the (path, bytes) pairs once the queue row is known."""
    ctx = {"row": None}
    box = {}

    def writer():
        if "w" not in box:
            box["w"] = goallog.Writer(probe_path, lambda: now).open()
        return box["w"]

    def do_queue():
        if queue:
            ctx["row"] = _queue_row(root, queue[0], queue[1], when)

    def do_entries():
        for e in entries:
            _append_entry(root, e)

    def do_files():
        for path, data in files(ctx):
            _write_file(path, data)

    def do_event():
        if event:
            _append_event(writer(), *event)

    def do_tidy():
        if tidy:
            tidy(ctx)

    steps = {"queue": do_queue, "check": lambda: _check_logbook(root, when), "probe": lambda: _probe(writer()),
             "entry": do_entries, "file": do_files, "event": do_event, "tidy": do_tidy}
    for name in STEP_ORDER:
        _run_step(name, steps[name])
    return ctx


def _dt(epoch):
    return datetime.fromtimestamp(int(epoch), timezone.utc).strftime("%Y-%m-%d %H:%M")


def _dt_epoch(text):
    return int(datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp())


def _stamp(now):
    return int(now)


def _row_title(goal, task, reason):
    if task:
        return f"Goal {goal} task {task} needs you ({reason})"
    return f"Goal {goal} has a plan that waits for you"


def _row_recommendation(task):
    what = "umwayi goal answer" if task else "umwayi goal approve"
    return (f"Use {what}. Answering this queue item starts nothing. Silence past the deadline means No.")


def _task_obj(packet, goal, state, reason, seq, dropped=False, approval=None):
    p = packet.to_dict()
    return {"version": 1, "id": packet.id, "state": state, "reason": reason, "seq": seq, "dropped": dropped, "packet": p,
            "sha256": packet.sha256(), "approval": approval, "base": "", "branch": "", "tip": "", "commit": "",
            "spent_uu": 0}


# ------------------------------------------------------------------------------------------------ goal lifecycle


def _need_text(text):
    if not (isinstance(text, str) and 10 <= len(text) <= MAX_TEXT and text.isprintable()):
        raise GoalError("the goal text must be 10 to 1000 printable characters")
    return text


def _hours(v, what):
    if not (isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 168):
        raise GoalError(f"{what} must be a whole number of hours from 1 to 168")
    return v


def start_goal(root, text, guide, plan_budget_uu, *, when, now, plan_hours=168, wait_hours=24, guide_model="",
               guide_effort=""):
    """Make the goal folder and goal.json, then write the `started` entry (the file first: a folder without an entry is
    harmless and its id is never reused). Returns the goal id."""
    _need_text(text)
    if not (isinstance(guide, str) and _NAME.fullmatch(guide)):
        raise GoalError("the guide must be an agent name")
    if not (isinstance(plan_budget_uu, int) and not isinstance(plan_budget_uu, bool) and plan_budget_uu >= 1):
        raise GoalError("the plan budget must be a whole number of UU, at least 1")
    _hours(plan_hours, "--plan-hours")
    _hours(wait_hours, "--wait-hours")
    goals_dir(root)  # refuses a link before anything is made
    goal = next_goal_id(root)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    obj = {"version": 1, "goal": goal, "text": text, "length": len(text), "text_sha256": digest, "created": int(now),
           "guide": guide, "guide_model": guide_model, "guide_effort": guide_effort, "plan_budget_uu": plan_budget_uu,
           "plan_hours": plan_hours, "wait_hours": wait_hours, "plan": None, "approved": False, "builder": "",
           "tester": "", "goal_budget_uu": 0, "tester_model": "", "tester_effort": "", "stopped": None, "refused": None}
    _run_step("check", _check_logbook, root, when)

    def make():
        d = goal_dir(root, goal, create=True)
        _write_file(d / "goal.json", _dump(obj, MAX_GOAL_FILE))

    _run_step("file", make)
    _run_step("entry", _append_entry, root, started_entry(when, goal, len(text), digest[:8], guide, plan_budget_uu))
    return goal


def _goal_events(root, goal):
    return goal_dir(root, goal) / "goal.events.jsonl"


def record_plan(root, goal, packets, agent, *, when, now, plan_spent_uu=None):
    """The plan is a proposal: plan.json, the `planned` entry, the approval request (7 days) and one queue row."""
    g = read_goal(root, goal)
    if g["plan"] is not None or g["stopped"] or g["refused"]:
        raise GoalError("this goal already has a plan, or it was stopped")
    plan = {"asked": int(now), "deadline": int(now) + g["plan_hours"] * 3600, "row": None, "answer": None}
    dump = _dump({"tasks": [p.to_dict() for p in packets]}, MAX_TASK_FILE)
    _run_step("file", _write_file, goal_dir(root, goal) / "plan.json", dump)
    minutes = sum(p.size for p in packets)
    entries = [planned_entry(when, goal, agent, len(packets), minutes, g["length"], g["text_sha256"][:8]),
               approval_requested_entry(when, goal, "", None, _dt(plan["deadline"]))]

    def files(ctx):
        plan["row"] = ctx["row"]
        return [(goal_dir(root, goal) / "goal.json", _dump(dict(_with_plan_spent(g, plan_spent_uu), plan=plan), MAX_GOAL_FILE))]

    _commit(root, when, now, _goal_events(root, goal), entries, files, queue=(_row_title(goal, "", None), _row_recommendation("")))


def refuse_plan(root, goal, agent, word, *, when, now, plan_spent_uu=None, context=None, protected=None):
    """A plan that failed a check: the goal stays in `plan` with no packets and the word is recorded (W9.R5.2). For a
    refused context entry, `context` ({"task", "entry", "why"}, W55b) says where and why, never the path."""
    g = read_goal(root, goal)
    if g["plan"] is not None or g["refused"] or g["stopped"]:
        raise GoalError("this goal already has a plan, or it was stopped")
    new = dict(_with_plan_spent(g, plan_spent_uu), refused=word)
    if context is not None:
        if word != "context":
            raise GoalError("only a plan refused for a context entry names one")
        new[REFUSED_CONTEXT_KEY] = dict(_check_refused_context(context))
    if protected is not None:
        if word != "protected":
            raise GoalError("only a plan refused as protected names one")
        new[REFUSED_PROTECTED_KEY] = dict(_check_refused_protected(protected))
    try:
        entry = plan_refused_entry(when, goal, agent, word, context, protected)
    except ValueError:
        raise GoalError("a value of the change is outside its pattern") from None
    _commit(root, when, now, _goal_events(root, goal), [entry],
            lambda ctx: [(goal_dir(root, goal) / "goal.json", _dump(new, MAX_GOAL_FILE))])


def _timed_out():
    return GoalError("this approval timed out and was denied")


def _deny_plan(root, goal, g, when, now):
    plan = dict(g["plan"], answer="no")
    entries = [approval_denied_entry(when, goal, "", _dt(plan["deadline"])), goal_stopped_entry(when, goal, "unanswered")]
    _commit(root, when, now, _goal_events(root, goal), entries,
            lambda ctx: [(goal_dir(root, goal) / "goal.json", _dump(dict(g, plan=plan, stopped="unanswered"), MAX_GOAL_FILE))],
            tidy=lambda ctx: _close_row(root, plan["row"], "No: timed out", when) if plan["row"] else None)


def approve_plan(root, goal, *, builder, tester, guide, model, effort, task_budget_uu, goal_budget_uu, budgets=None,
                 keep=None, tester_model="", tester_effort="", per_day=500, when, now, accepted=None):
    """The owner's approval of the plan (the caller checked the terminal). Fills the packets, queues the kept tasks."""
    g = read_goal(root, goal)
    plan = g["plan"]
    if plan is None or g["approved"] or g["stopped"]:
        raise GoalError("this goal has no plan that waits for approval")
    if now >= plan["deadline"]:
        _deny_plan(root, goal, g, when, now)
        raise _timed_out()
    if not gp.roles_ok(guide, builder, tester) or guide != g["guide"]:
        raise GoalError("the tester and the guide must differ from the builder, and the guide is the one chosen at start")
    raw = _read_json(goal_dir(root, goal) / "plan.json", MAX_TASK_FILE, "plan")
    try:
        proposed = [gp.packet_from_dict(t) for t in raw["tasks"]]
    except (KeyError, TypeError, ValueError):
        raise GoalError("the plan file has the wrong shape") from None
    ids = [p.id for p in proposed]
    kept_ids = ids if keep is None else list(keep)
    if not kept_ids or any(k not in ids for k in kept_ids) or len(set(kept_ids)) != len(kept_ids):
        raise GoalError("--keep must name tasks of the plan")
    kept_ids = [i for i in ids if i in kept_ids]
    dropped_ids = [i for i in ids if i not in kept_ids]
    per_task = {i: (budgets or {}).get(i, task_budget_uu) for i in kept_ids}
    if goalbudget.approval_problem(per_task, goal_budget_uu, per_day):
        raise GoalError("every task needs a budget from 1 UU to the day limit, and the goal budget must cover them")
    filled = {}
    for p in proposed:
        if p.id in kept_ids:
            try:
                filled[p.id] = gp.fill_packet(p, goal, model, effort, per_task[p.id], per_day)
            except ValueError:
                raise GoalError("the model, the effort or a budget is not allowed") from None
        else:
            filled[p.id] = p
    base = goal_dir(root, goal)
    _run_step("check", _check_logbook, root, when)

    def prefile():
        for i in ids:
            drop = i in dropped_ids
            _write_file(base / f"{i}.json", _dump(_task_obj(filled[i], goal, "dropped" if drop else "plan", "", 0, drop),
                                                   MAX_TASK_FILE))

    _run_step("file", prefile)
    entries = [approval_answered_entry(when, goal, "", "yes"),
               plan_approved_entry(when, goal, kept_ids, dropped_ids, builder, tester, guide, goal_budget_uu, accepted)]

    def files(ctx):
        out = [(base / f"{i}.json", _dump(_task_obj(filled[i], goal, "queued", "approved", 0), MAX_TASK_FILE)) for i in kept_ids]
        new = dict(g, plan=dict(plan, answer="yes"), approved=True, builder=builder, tester=tester, goal_budget_uu=goal_budget_uu,
                   tester_model=tester_model, tester_effort=tester_effort)
        return out + [(base / "goal.json", _dump(new, MAX_GOAL_FILE))]

    _commit(root, when, now, _goal_events(root, goal), entries, files,
            tidy=lambda ctx: _close_row(root, plan["row"], "Yes", when) if plan["row"] else None)


def change_state(root, goal, task, new, reason, *, when, now, role=None, agent=None, cap_uu=None, branch=None, tip=None,
                 base=None, commit=None, facts=None, not_done="text", spent_uu=None, pre=(), close_row=None, blocked=None,
                 recommendation=None, measured_uu=None):
    """Move one task to a new state in the fixed write order (W9.R13.1). Raises GoalError for a move the table does not
    allow (nothing changed) and RecordFailed when a record write fails. Returns the new task object.

    W56: `blocked` (the fixed words of `block_words`) is kept in the task file of a task that needs the owner because
    the rules gate blocked its builder; any later move drops it. `recommendation` replaces the fixed text of the queue
    row of a move to `needs owner`."""
    g = read_goal(root, goal)
    t = read_task(root, goal, task)
    old = t["state"]
    if old not in gp.STATES or not gp.can_move(old, new) or reason not in gp.REASONS.get(new, ()):
        raise GoalError("that move is not in the state table")
    if blocked is not None:
        if new != "needs owner":
            raise GoalError("only a task that needs the owner keeps a block")
        _check_blocked(blocked)
    if recommendation is not None and not (new == "needs owner" and isinstance(recommendation, str)
                                           and 1 <= len(recommendation) <= 400 and recommendation.isprintable()):
        raise GoalError("a value of the change is outside its pattern")
    try:
        state = state_entry(when, goal, task, old, new, reason, role=role, agent=agent, cap_uu=cap_uu, branch=branch, tip=tip,
                            base=base, commit=commit, facts=facts, not_done=not_done)
    except ValueError:
        raise GoalError("a value of the change is outside its pattern") from None
    entries = list(pre)
    approval = None
    queue = None
    if new == "needs owner":
        deadline = int(now) + g["wait_hours"] * 3600
        approval = {"kind": "needs-owner", "asked": int(now), "deadline": deadline, "row": None}
        entries.append(approval_requested_entry(when, goal, task, reason, _dt(deadline)))
        queue = (_row_title(goal, task, reason), recommendation or _row_recommendation(task))
    entries.append(state)
    obj = dict(t, state=new, reason=reason, seq=t["seq"] + 1, approval=approval)
    obj.pop(BLOCKED_KEY, None)
    if blocked is not None:
        obj[BLOCKED_KEY] = dict(blocked)
    for key, val in (("branch", branch), ("tip", tip), ("base", base), ("commit", commit)):
        if val is not None:
            obj[key] = val
    if spent_uu is not None:
        obj["spent_uu"] = spent_uu
    if measured_uu is not None:  # W54: a file fact like spent_uu, not in the entry
        try:
            obj[MEASURED_KEY] = dict(_check_measured(measured_uu))
        except GoalError:
            raise GoalError("a value of the change is outside its pattern") from None

    def files(ctx):
        if approval is not None:
            approval["row"] = ctx["row"]
        return [(goal_dir(root, goal) / f"{task}.json", _dump(obj, MAX_TASK_FILE))]

    tidy = (lambda ctx: _close_row(root, close_row[0], close_row[1], when)) if close_row and close_row[0] else None
    path = events_path(root, goal, task)
    _commit(root, when, now, path, entries, files, queue=queue,
            event=("state", {"from": old, "to": new, "reason": reason, "recovered": False}), tidy=tidy)
    return obj


def answer_approval(root, goal, task, answer, *, when, now):
    """The owner's answer to a task that needs them (or `no` to a plan). Refused once the deadline has passed; the denial
    is then logged, once, and the answer is not accepted."""
    if answer not in ("yes", "no"):
        raise GoalError("the answer must be yes or no")
    if not task:
        g = read_goal(root, goal)
        if g["plan"] is None or g["approved"] or g["stopped"] or g["plan"]["answer"] is not None:
            raise GoalError("nothing waits for the owner here")
        if now >= g["plan"]["deadline"]:
            _deny_plan(root, goal, g, when, now)
            raise _timed_out()
        if answer == "yes":
            raise GoalError("approve the plan with umwayi goal approve")
        plan = dict(g["plan"], answer="no")
        _commit(root, when, now, _goal_events(root, goal),
                [approval_answered_entry(when, goal, "", "no"), goal_stopped_entry(when, goal, "owner")],
                lambda ctx: [(goal_dir(root, goal) / "goal.json", _dump(dict(g, plan=plan, stopped="owner"), MAX_GOAL_FILE))],
                tidy=lambda ctx: _close_row(root, plan["row"], "No", when) if plan["row"] else None)
        return
    t = read_task(root, goal, task)
    a = t["approval"]
    if t["state"] == "stopped" and t["reason"] == "unanswered":
        raise _timed_out()  # already denied and logged once
    if t["state"] != "needs owner" or not a:
        raise GoalError("nothing waits for the owner here")
    if now >= a["deadline"]:
        _deny_task(root, goal, task, a, when, now)
        raise _timed_out()
    new, reason = ("queued", "answered") if answer == "yes" else ("stopped", "owner")
    change_state(root, goal, task, new, reason, when=when, now=now, pre=[approval_answered_entry(when, goal, task, answer)],
                 close_row=(a["row"], "Yes" if answer == "yes" else "No"))


def _deny_task(root, goal, task, a, when, now):
    change_state(root, goal, task, "stopped", "unanswered", when=when, now=now,
                 pre=[approval_denied_entry(when, goal, task, _dt(a["deadline"]))], close_row=(a["row"], "No: timed out"))


def deny_expired(root, *, when, now):
    """Every writing command begins here (W9.R9.5): each approval past its deadline is denied and logged, once, even if no
    process ran in between. Returns [(goal, task or "")]."""
    done = []
    for goal in list_goals(root):
        g = read_goal(root, goal)
        p = g["plan"]
        if p and p["answer"] is None and not g["approved"] and not g["stopped"] and now >= p["deadline"]:
            _deny_plan(root, goal, g, when, now)
            done.append((goal, ""))
        for task in list_tasks(root, goal):
            t = read_task(root, goal, task)
            a = t["approval"]
            if t["state"] == "needs owner" and a and now >= a["deadline"]:
                _deny_task(root, goal, task, a, when, now)
                done.append((goal, task))
    return done


def stop_goal(root, goal, reason, *, when, now, queued_too=False):
    """The goal-level stop (W9.R16). Idempotent: a stopped goal changes nothing. With `queued_too` every queued task is
    stopped with the reason `owner`. Returns True if anything changed."""
    if reason not in GOAL_STOP_REASONS:
        raise GoalError("that is not a reason to stop a goal")
    g = read_goal(root, goal)
    changed = False
    if not g["stopped"]:
        entries, plan, tidy = [], g["plan"], None
        if plan and plan["answer"] is None and not g["approved"]:
            plan = dict(plan, answer="no")
            entries.append(approval_answered_entry(when, goal, "", "no"))
            tidy = lambda ctx: _close_row(root, plan["row"], "No", when) if plan["row"] else None  # noqa: E731
        entries.append(goal_stopped_entry(when, goal, reason))
        _commit(root, when, now, _goal_events(root, goal), entries,
                lambda ctx: [(goal_dir(root, goal) / "goal.json", _dump(dict(g, plan=plan, stopped=reason), MAX_GOAL_FILE))],
                tidy=tidy)
        changed = True
    if queued_too:
        for task in list_tasks(root, goal):
            if read_task(root, goal, task)["state"] == "queued":
                change_state(root, goal, task, "stopped", "owner", when=when, now=now)
                changed = True
    return changed


# ------------------------------------------------------------------------------------------------ repair


def _file_state(root, goal, task):
    try:
        return read_task(root, goal, task)
    except GoalError:
        return None


def behind(root):
    """[(goal, task)] whose state file is behind the logbook (what a read-only command reports)."""
    out = []
    for goal, v in view(root).items():
        for task, tv in v.tasks.items():
            t = _file_state(root, goal, task)
            if t is not None and (t["state"] == "plan" or t["seq"] < tv.seq):
                out.append((goal, task))
    return out


def repair(root, *, when, now):
    """Make the files agree with the logbook, which wins (W9.R13.5). Idempotent. Returns a list of fixed words."""
    done = []
    for goal, v in view(root).items():
        if not goal_dir(root, goal).exists():
            continue
        g = read_goal(root, goal)
        want = dict(g)
        if v.approved:
            want.update(approved=True, builder=v.builder, tester=v.tester, goal_budget_uu=v.goal_budget)
        if v.stopped:
            want["stopped"] = v.stopped
        if v.planned and g["plan"] is None and v.plan_deadline:
            dl = _dt_epoch(v.plan_deadline)
            want["plan"] = {"asked": dl - g["plan_hours"] * 3600, "deadline": dl, "row": None, "answer": None}
        if want != g:
            _run_step("file", _write_file, goal_dir(root, goal) / "goal.json", _dump(want, MAX_GOAL_FILE))
            done.append(f"{goal} goal file")
        for task, tv in v.tasks.items():
            t = _file_state(root, goal, task)
            if t is None:
                continue
            if t["seq"] > tv.seq:
                fixed = dict(t, state=tv.state, reason=tv.reason, seq=tv.seq)
                fixed.pop(BLOCKED_KEY, None)
                _run_step("file", _write_file, goal_dir(root, goal) / f"{task}.json", _dump(fixed, MAX_TASK_FILE))
                done.append(f"{goal} {task} file ahead")
                if gp.can_move(tv.state, "needs owner"):
                    change_state(root, goal, task, "needs owner", "unclear", when=when, now=now)
                continue
            fixed = dict(t)
            if t["state"] == "plan" or t["seq"] < tv.seq:
                fixed.update(state=tv.state, reason=tv.reason, seq=tv.seq)
                fixed.pop(BLOCKED_KEY, None)  # W56: the logbook's block, if its last state entry named one
                if tv.blocked is not None and tv.state == "needs owner":
                    fixed[BLOCKED_KEY] = dict(tv.blocked)
                for key in ("branch", "tip", "base", "commit"):
                    if getattr(tv, key):
                        fixed[key] = getattr(tv, key)
                if tv.state == "needs owner" and tv.deadline:
                    dl = _dt_epoch(tv.deadline)
                    title = _row_title(goal, task, tv.reason)
                    row = taskqueue.find_open(root, "decision", title)
                    fixed["approval"] = {"kind": "needs-owner", "asked": dl - g["wait_hours"] * 3600, "deadline": dl,
                                         "row": row.id if row else None}
                _run_step("file", _write_file, goal_dir(root, goal) / f"{task}.json", _dump(fixed, MAX_TASK_FILE))
                done.append(f"{goal} {task} file")
            if tv.seq:
                w = goallog.Writer(events_path(root, goal, task), lambda: now).open()
                data = goallog.read(events_path(root, goal, task).read_bytes() if events_path(root, goal, task).exists() else b"")[0]
                if sum(1 for e in data if e["kind"] == "state") < tv.seq:
                    _run_step("event", _append_event, w, "state",
                              {"from": tv.prev, "to": tv.state, "reason": tv.reason, "recovered": True})
                    done.append(f"{goal} {task} event")
    return done


def find_lost(root, holding=False):
    """[(goal, task)] that are `running` while no supervisor holds the lock (W9.R19.5). A command that holds the lock
    itself passes holding=True: any running task then belongs to a supervisor that is gone."""
    if not holding and not lock_free(root):
        return []
    out = []
    for goal in list_goals(root):
        for task in list_tasks(root, goal):
            t = _file_state(root, goal, task)
            if t is not None and t["state"] == "running":
                out.append((goal, task))
    return out


def mark_lost(root, *, when, now, holding=False):
    lost = find_lost(root, holding)
    for goal, task in lost:
        change_state(root, goal, task, "stopped", "supervisor", when=when, now=now)
    return lost
