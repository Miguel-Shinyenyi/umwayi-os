"""Goal orchestration (W9.2): the task packet, the plan parser, the protected list, the scope check, the state table,
the roles rule and the strict readers of the helpers' result lines.

Pure: this module imports only `json`, `re`, `hashlib`, `dataclasses` and `posixpath`. It reads no file, no clock and
starts no process. Nothing here starts an AI helper (W9.R1, W9.R7). Text in a packet is data: it is never a path, a
command line or a URL to umwayi (W9.R4.2).

Errors name a fixed word and a packet number and never quote the text that was refused (W9.R5.3).
"""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
from dataclasses import dataclass

MAX_PLAN_BYTES = 32 * 1024
MAX_DEPTH = 4
MAX_TASKS = 8
MAX_TOTAL_MINUTES = 480
MIN_SIZE, MAX_SIZE = 15, 90
MAX_CONTEXT_FILES, MAX_CONTEXT_BYTES = 12, 200 * 1024
MAX_CHECKS, MAX_FILES = 8, 20
TEXT_MIN, TEXT_MAX = 10, 200
MAX_RESULT_BYTES = 8192
MAX_CHECK_BYTES = 4096
EVIDENCE_MIN, EVIDENCE_MAX = 5, 300

EFFORTS = ("low", "medium", "high", "xhigh", "max")
_MODEL = re.compile(r"^[A-Za-z0-9._:/-]{1,64}$")
_NAME = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
_GOAL_ID = re.compile(r"^G-\d{4,}$")
_TASK_ID = re.compile(r"^T-\d{2}$")
_NONCE = re.compile(r"^[0-9a-f]{16}$")
_SECOND_SENTENCE = re.compile(r"[.!?]\s+\S")

# W9.R4.5: a fixed list. A trailing slash means the folder and everything under it.
PROTECTED = (
    "rules.yaml", "autonomy.yaml", "agents.yaml", "units.yaml", "umwayi.json", "schedule.yaml", "jobs.yaml",
    "workflows/", "LOGBOOK.md", "queue.md", ".umwayi/", ".kiro/steering/", ".github/",
    "docs/status-log.md", "docs/KNOWN-LIMITS.md", ".gitignore", "docs-parts/",
    "adapters/claude_code/rules.example.yaml", "adapters/kiro/rules.example.yaml",
    "adapters/stdio/rules.example.yaml", "adapters/opencode/rules.example.yaml",
)

# ----------------------------------------------------------------------------------------------- the states

STATES = ("queued", "running", "in review", "needs owner", "merged", "failed", "stopped")
TRANSITIONS = {
    "queued": ("running", "needs owner", "stopped"),
    "running": ("in review", "failed", "needs owner", "stopped"),
    "in review": ("merged",),
    "needs owner": ("queued", "stopped"),
    "merged": (),
    "failed": (),
    "stopped": (),
}
REASONS = {
    "queued": ("approved", "answered"),
    "running": ("start",),
    "in review": ("checked",),
    "merged": ("observed", "declared"),
    "failed": ("builder", "outcome", "scope", "tests", "rejected", "stalled", "looping", "budget", "timeout", "readonly"),
    "stopped": ("kill", "owner", "log", "signal", "unanswered", "supervisor"),
    "needs owner": ("ask", "unclear", "busy", "dirty", "leftover", "stale", "config"),
}

# One cause, one (state, reason). `reason_for` is the only function that chooses a reason word (W9.R6.2).
CAUSES = {
    # failed
    "agent_exit_nonzero": ("failed", "builder"),
    "agent_exit_2": ("failed", "builder"),
    "no_commit": ("failed", "outcome"),
    "tree_not_clean": ("failed", "outcome"),
    "status_file_missing": ("failed", "outcome"),
    "status_file_invalid": ("failed", "outcome"),
    "limits_file_invalid": ("failed", "outcome"),
    "file_outside_packet": ("failed", "scope"),
    "protected_file_changed": ("failed", "scope"),
    "check_failed": ("failed", "tests"),
    "guide_rejected": ("failed", "rejected"),
    "no_progress": ("failed", "stalled"),
    "same_error_twice": ("failed", "looping"),
    "task_budget_spent": ("failed", "budget"),
    "agent_timeout": ("failed", "timeout"),
    "readonly_role_changed_tree": ("failed", "readonly"),
    # stopped
    "kill_switch": ("stopped", "kill"),
    "owner_stop": ("stopped", "owner"),
    "owner_answered_no": ("stopped", "owner"),
    "rules_said_no": ("stopped", "owner"),
    "log_write_failed": ("stopped", "log"),
    "signal_received": ("stopped", "signal"),
    "deadline_passed": ("stopped", "unanswered"),
    "supervisor_lost": ("stopped", "supervisor"),
    # needs owner
    "rules_said_ask": ("needs owner", "ask"),
    "budget_said_ask": ("needs owner", "ask"),
    "agent_exit_3": ("needs owner", "ask"),
    "result_unparsed": ("needs owner", "unclear"),
    "result_incomplete": ("needs owner", "unclear"),
    "packet_changed": ("needs owner", "unclear"),
    "tip_moved": ("needs owner", "unclear"),
    "check_unclear": ("needs owner", "unclear"),
    "guide_unclear": ("needs owner", "unclear"),
    "run_lock_busy": ("needs owner", "busy"),
    "worktree_not_clean": ("needs owner", "dirty"),
    "worktree_leftover": ("needs owner", "leftover"),
    "worktree_cap": ("needs owner", "leftover"),
    "main_behind_origin": ("needs owner", "stale"),
    "agent_cannot_be_gated": ("needs owner", "config"),
    "worktree_not_made": ("needs owner", "config"),
    "agent_exit_64": ("needs owner", "config"),
    # the other moves
    "owner_answered_yes": ("queued", "answered"),
    "plan_approved": ("queued", "approved"),
    "child_started": ("running", "start"),
    "checked_all": ("in review", "checked"),
    "merge_observed": ("merged", "observed"),
    "merge_declared": ("merged", "declared"),
}


def reason_for(cause):
    """(new state, reason word) for a cause. An unknown cause is a ValueError, never a guess."""
    try:
        return CAUSES[cause]
    except (KeyError, TypeError):
        raise ValueError("unknown cause") from None


def can_move(old, new):
    """True if the table allows the move. `plan` is the state before approval, and it only leads to `queued`."""
    if old == "plan":
        return new == "queued"
    return isinstance(old, str) and isinstance(new, str) and new in TRANSITIONS.get(old, ())


def goal_state(states, stopped=False):
    """The state of a goal, read from its tasks (W9.R6.4). Never stored."""
    states = list(states)
    if not states:
        return "stopped" if stopped else "plan"
    if "failed" in states:
        return "failed"
    if "stopped" in states:
        return "stopped"
    if all(s == "merged" for s in states):
        return "merged"
    if "running" in states:
        return "active"
    first = next(s for s in states if s != "merged")
    return "active" if first == "queued" else "waiting"


# ----------------------------------------------------------------------------------------------- ids and names


def own_files(goal, task):
    """(status file, limits file) of a task, by right (W9.R4.6)."""
    _ids(goal, task)
    return (f"docs-parts/status-log/{goal}-{task}.md", f"docs-parts/known-limits/{goal}-{task}.md")


def branch_name(goal, task):
    _ids(goal, task)
    return f"umwayi/{goal.lower()}-{task.lower()}"


def _ids(goal, task):
    if not (isinstance(goal, str) and isinstance(task, str) and _GOAL_ID.fullmatch(goal) and _TASK_ID.fullmatch(task)):
        raise ValueError("bad goal or task id")


def roles_ok(guide, builder, tester):
    """W9.R2.2: the tester is not the builder, and neither is the guide. All three must be agent names."""
    names = (guide, builder, tester)
    if not all(isinstance(n, str) and _NAME.fullmatch(n) for n in names):
        return False
    return tester != builder and guide != builder


def weak_independence(a, b):
    """True when two agents share the platform and the model word: a warning, not a refusal (W9-Q2)."""
    try:
        return tuple(a) == tuple(b)
    except TypeError:
        return False


# ----------------------------------------------------------------------------------------------- the packet


class PlanError(ValueError):
    """A plan or packet that is refused. `word` is a fixed word, `index` the packet number (1 based) or 0."""

    def __init__(self, word, index=0):
        super().__init__(f"plan refused: {word}" + (f" (packet {index})" if index else ""))
        self.word = word
        self.index = index


@dataclass(frozen=True)
class Packet:
    id: str
    goal: str
    context: tuple
    checks: tuple
    outcome: dict
    size: int
    model: str
    effort: str
    files: tuple
    budget_uu: int | None

    def to_dict(self):
        return {"id": self.id, "goal": self.goal, "context": list(self.context), "checks": list(self.checks),
                "outcome": dict(self.outcome), "size": self.size, "model": self.model, "effort": self.effort,
                "files": list(self.files), "budget_uu": self.budget_uu}

    def sha256(self):
        """The SHA-256 of the canonical JSON of the packet: sorted keys, no spaces (W9.R4.7)."""
        text = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(text.encode("ascii")).hexdigest()


PACKET_KEYS = ("id", "goal", "context", "checks", "outcome", "size", "model", "effort", "files", "budget_uu")
GUIDE_KEYS = ("goal", "context", "checks", "size", "files")


def _int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _text_ok(s):
    return isinstance(s, str) and TEXT_MIN <= len(s) <= TEXT_MAX and s.isprintable() and not _SECOND_SENTENCE.search(s)


def _norm_parts(path):
    """The components of a repo-relative path, or None if the path is not a plain relative path."""
    if not isinstance(path, str) or not path or "\x00" in path or "\\" in path or path.startswith("/"):
        return None
    if any(ord(c) < 32 or ord(c) == 127 for c in path):
        return None
    parts = [p for p in path.split("/") if p not in ("", ".")]
    if not parts or ".." in parts:
        return None
    return parts


def _compare_form(parts):
    """The spelling used to compare with the protected list: case folded, no trailing dots or spaces."""
    return [p.casefold().rstrip(" .") for p in parts]


_PROTECTED_FORMS = tuple((tuple(_compare_form([p for p in name.split("/") if p])), name.endswith("/")) for name in PROTECTED)


def is_protected(path):
    """True if `path` names, or sits under, a protected file or folder, in any spelling (W9.R4.5)."""
    if isinstance(path, bytes):
        try:
            path = path.decode("utf-8")
        except UnicodeDecodeError:
            return True
    if not isinstance(path, str):
        return True
    raw = path.replace("\\", "/") if isinstance(path, str) else path
    # a `..` is resolved here for the comparison only; a plan that contains one is refused before this point
    norm = posixpath.normpath(raw.lstrip("/") or ".")
    if norm == "." or norm.startswith(".."):
        return False
    form = tuple(_compare_form([p for p in norm.split("/") if p]))
    for prot, _folder in _PROTECTED_FORMS:
        if form[:len(prot)] == prot:
            return True
    return False


def files_problem(entry):
    """None if `entry` may be listed in `files`, else a fixed word: `files` or `protected`."""
    parts = _norm_parts(entry)
    if parts is None or any(c in entry for c in "*?[]"):
        return "files"
    if is_protected(entry):
        return "protected"
    return None


def _strict_loads(data):
    def pairs(items):
        keys = [k for k, _ in items]
        if len(keys) != len(set(keys)):
            raise _Dup()
        return dict(items)

    def no_float(_s):
        raise ValueError("not a whole number")

    def no_const(_s):
        raise ValueError("not json")

    return json.loads(data, object_pairs_hook=pairs, parse_float=no_float, parse_constant=no_const)


class _Dup(ValueError):
    pass


def _depth(v, d=0):
    """The nesting depth of containers: a scalar adds nothing."""
    if isinstance(v, dict):
        return max([d + 1] + [_depth(x, d + 1) for x in v.values()])
    if isinstance(v, list):
        return max([d + 1] + [_depth(x, d + 1) for x in v])
    return d


def parse_plan(data, file_size=None, is_private=None):
    """The guide's plan object as bytes -> a tuple of Packets (T-01 ...), or a PlanError (W9.R4.2, W9.R5.3).

    `file_size(path)` gives the size of a regular, non-link file or None; `is_private(path)` is True for a private
    path. They are passed in so this module stays pure; with `file_size` left out the context files are not looked up.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise PlanError("encoding")
    if len(data) > MAX_PLAN_BYTES:
        raise PlanError("bytes")
    if bytes(data).startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")):
        raise PlanError("encoding")
    try:
        text = bytes(data).decode("utf-8")
    except UnicodeDecodeError:
        raise PlanError("encoding") from None
    try:
        obj = _strict_loads(text)
    except _Dup:
        raise PlanError("duplicate") from None
    except RecursionError:
        raise PlanError("depth") from None
    except ValueError:
        raise PlanError("json") from None
    if _depth(obj) > MAX_DEPTH:
        raise PlanError("depth")
    if not isinstance(obj, dict):
        raise PlanError("type")
    if set(obj) != {"tasks"}:
        raise PlanError("field")
    tasks = obj["tasks"]
    if not isinstance(tasks, list):
        raise PlanError("type")
    if not 1 <= len(tasks) <= MAX_TASKS:
        raise PlanError("count")
    packets, total = [], 0
    for i, t in enumerate(tasks, 1):
        packets.append(_guide_task(t, i, file_size, is_private))
        total += packets[-1].size
    if total > MAX_TOTAL_MINUTES:
        raise PlanError("total")
    return tuple(packets)


def _guide_task(t, i, file_size, is_private):
    if not isinstance(t, dict):
        raise PlanError("type", i)
    if set(t) - set(GUIDE_KEYS):
        raise PlanError("field", i)
    if set(GUIDE_KEYS) - set(t):
        raise PlanError("field", i)
    goal = t["goal"]
    if not _text_ok(goal):
        raise PlanError("goal", i)
    context = t["context"]
    if not isinstance(context, list) or len(context) > MAX_CONTEXT_FILES:
        raise PlanError("context", i)
    total = 0
    for c in context:
        parts = _norm_parts(c)
        if parts is None:
            raise PlanError("context", i)
        if is_private is not None and is_private(c):
            raise PlanError("context", i)
        if file_size is not None:
            size = file_size(c)
            if not _int(size) or size < 0:
                raise PlanError("context", i)
            total += size
    if total > MAX_CONTEXT_BYTES:
        raise PlanError("context", i)
    checks = t["checks"]
    if not isinstance(checks, list) or not 1 <= len(checks) <= MAX_CHECKS or not all(_text_ok(c) for c in checks):
        raise PlanError("checks", i)
    size = t["size"]
    if not _int(size) or not MIN_SIZE <= size <= MAX_SIZE:
        raise PlanError("size", i)
    files = t["files"]
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise PlanError("files", i)
    for f in files:
        word = files_problem(f)
        if word:
            raise PlanError(word, i)
    return Packet(f"T-{i:02d}", goal, tuple(context), tuple(checks), {}, size, "", "", tuple(files), None)


def fill_packet(packet, goal, model, effort, budget_uu, per_day):
    """The owner's fields (model, effort, budget) and the outcome, at approval. A bad value is a ValueError."""
    status, limits = own_files(goal, packet.id)
    if not (isinstance(model, str) and _MODEL.fullmatch(model)):
        raise ValueError("model")
    if effort not in EFFORTS:
        raise ValueError("effort")
    if not _int(budget_uu) or not _int(per_day) or not 1 <= budget_uu <= per_day:
        raise ValueError("budget")
    outcome = {"status_file": status, "limits_file": limits, "branch": branch_name(goal, packet.id)}
    return Packet(packet.id, packet.goal, packet.context, packet.checks, outcome, packet.size, model, effort, packet.files,
                  budget_uu)


def packet_from_dict(d):
    """A stored packet, read as strictly as a plan: exactly the ten fields (W9.R4.1)."""
    if not isinstance(d, dict) or set(d) != set(PACKET_KEYS):
        raise ValueError("packet fields")
    if not (isinstance(d["id"], str) and _TASK_ID.fullmatch(d["id"])):
        raise ValueError("packet id")
    if not (_text_ok(d["goal"]) and isinstance(d["context"], list) and isinstance(d["checks"], list)
            and isinstance(d["files"], list) and all(isinstance(x, str) for x in d["context"] + d["checks"] + d["files"])):
        raise ValueError("packet text")
    if not _int(d["size"]):
        raise ValueError("packet size")
    o = d["outcome"]
    if o != {} and not (isinstance(o, dict) and set(o) == {"status_file", "limits_file", "branch"}
                        and all(isinstance(v, str) for v in o.values())):
        raise ValueError("packet outcome")
    if not (isinstance(d["model"], str) and isinstance(d["effort"], str)):
        raise ValueError("packet owner fields")
    if d["budget_uu"] is not None and not _int(d["budget_uu"]):
        raise ValueError("packet budget")
    return Packet(d["id"], d["goal"], tuple(d["context"]), tuple(d["checks"]), dict(o), d["size"], d["model"], d["effort"],
                  tuple(d["files"]), d["budget_uu"])


# ----------------------------------------------------------------------------------------------- scope


def _scope_norm(path):
    """The normalized form of a changed path, or None if it is always a violation."""
    if isinstance(path, bytes):
        try:
            path = path.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if not isinstance(path, str) or not path or "\x00" in path or "\\" in path or path.startswith("/"):
        return None
    if any(ord(c) < 32 or ord(c) == 127 for c in path):
        return None
    parts = [p for p in path.split("/") if p not in ("", ".")]
    if not parts or ".." in parts:
        return None
    return "/".join(parts)


def scope_violations(changed, files, own=()):
    """The changed paths that the packet does not allow (W9.R8.3). Always a violation: an absolute path, `..`, a backslash,
    a NUL or control character, bytes that are not UTF-8, a protected path unless it is one of the task's own two
    files. Comparing is case sensitive. The result lists the paths as they were given and never raises."""
    allowed_files, allowed_dirs = set(), []
    for f in list(files or ()):
        folder = isinstance(f, str) and f.endswith("/")
        n = _scope_norm(f)
        if n is None:
            continue
        if folder:
            allowed_dirs.append(n + "/")
        else:
            allowed_files.add(n)
    own_set = {n for n in (_scope_norm(o) for o in (own or ())) if n is not None}
    bad = []
    try:
        items = list(changed)
    except TypeError:
        return []
    for c in items:
        n = _scope_norm(c)
        if n is None:
            bad.append(c)
        elif n in own_set:
            continue
        elif is_protected(n):
            bad.append(c)
        elif n in allowed_files or any(n.startswith(d) for d in allowed_dirs):
            continue
        else:
            bad.append(c)
    return bad


# ----------------------------------------------------------------------------------------------- result lines


RESULT_WORDS = ("missing", "doubled", "nonce", "json", "shape", "size")


@dataclass(frozen=True)
class Parsed:
    ok: bool
    value: object = None
    word: str = ""
    raw: bytes = b""


def _fail(word):
    return Parsed(False, None, word)


def parse_result_line(text, tag, nonce, limit):
    """Find the one line that starts with `TAG ` in a helper's output and read `TAG NONCE JSON` from it (W9.R5.2).

    Total: any bytes or text give a Parsed, never an exception. Two different tagged lines are `doubled` and refused,
    so a forged line left in the repo cannot win by being first or last. The nonce must match; the JSON must be an
    object and the line at most `limit` bytes. Words: missing, doubled, nonce, json, shape, size.
    """
    try:
        if not (isinstance(nonce, str) and _NONCE.fullmatch(nonce)):
            return _fail("nonce")
        if isinstance(text, str):
            text = text.encode("utf-8", "replace")
        elif not isinstance(text, (bytes, bytearray)):
            return _fail("missing")
        prefix = tag.encode("ascii") + b" "
        found = []
        for ln in bytes(text).split(b"\n"):
            ln = ln.rstrip(b"\r")
            if ln.startswith(prefix) and ln not in found:
                found.append(ln)
        if not found:
            return _fail("missing")
        if len(found) > 1:
            return _fail("doubled")
        ln = found[0]
        if len(ln) > limit:
            return _fail("size")
        rest = ln[len(prefix):]
        want = nonce.encode("ascii") + b" "
        if not rest.startswith(want):
            return _fail("nonce")
        body = rest[len(want):]
        try:
            value = _strict_loads(body.decode("utf-8"))
        except (ValueError, RecursionError, UnicodeDecodeError):
            return _fail("json")
        if not isinstance(value, dict):
            return _fail("shape")
        return Parsed(True, value, "", body)
    except Exception:  # total by design: nothing a helper prints may crash the supervisor
        return _fail("json")


def _evidence_ok(s):
    return isinstance(s, str) and EVIDENCE_MIN <= len(s) <= EVIDENCE_MAX and s.isprintable()


def parse_verdict(text, nonce, count):
    """The tester's answer: exactly one entry per check number 1..count (W9.R8.5). value: ((n, verdict, evidence), ...)."""
    if not _int(count) or not 1 <= count <= MAX_CHECKS:
        return _fail("shape")
    r = parse_result_line(text, "UMWAYI-RESULT", nonce, MAX_RESULT_BYTES)
    if not r.ok:
        return r
    v = r.value
    if set(v) != {"checks"} or not isinstance(v["checks"], list) or len(v["checks"]) != count:
        return _fail("shape")
    seen = {}
    for c in v["checks"]:
        if not (isinstance(c, dict) and set(c) == {"n", "verdict", "evidence"}):
            return _fail("shape")
        n = c["n"]
        if not _int(n) or not 1 <= n <= count or n in seen:
            return _fail("shape")
        if c["verdict"] not in ("pass", "fail", "unclear") or not _evidence_ok(c["evidence"]):
            return _fail("shape")
        seen[n] = (n, c["verdict"], c["evidence"])
    return Parsed(True, tuple(seen[n] for n in sorted(seen)), "", r.raw)


def parse_check(text, nonce):
    """The guide's check answer: `UMWAYI-CHECK NONCE {"verdict": ..., "reason": ...}` (W9.R8.6). value: (verdict, reason)."""
    r = parse_result_line(text, "UMWAYI-CHECK", nonce, MAX_CHECK_BYTES)
    if not r.ok:
        return r
    v = r.value
    if set(v) != {"verdict", "reason"} or v["verdict"] not in ("accept", "reject", "unclear") or not _evidence_ok(v["reason"]):
        return _fail("shape")
    return Parsed(True, (v["verdict"], v["reason"]), "", r.raw)
