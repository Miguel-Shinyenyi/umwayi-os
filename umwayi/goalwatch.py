"""Goal orchestration (W9.4): the error signature, the stall and loop judge, and the approval record with its deadline.

Pure: no clock, no file and no process. The time `now` is always passed in. Nothing here raises on a bad history: a
judge that cannot read its input says Continue, because the supervisor has its own stops (kill switch, budget, log).
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field

STALL_SECONDS = 1800
REPEAT_ERRORS = 2
PLAN_HOURS = 168
WAIT_HOURS = 24
MAX_HOURS = 168

_MARKERS = ("error", "fatal", "traceback (most recent call last)", "exception", "failed", "panic", "npm err!", "cannot ",
            "no such file")
_QUOTED = re.compile(r"\"[^\"]*\"|'[^']*'")
_HEXWORD = re.compile(r"\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*[0-9])[0-9a-f]{6,}\b")
_DIGITS = re.compile(r"\d+")
_GOAL = re.compile(r"^G-\d{4,}$")
_TASK = re.compile(r"^T-\d{2}$")


def signature(line):
    """The first 16 hex characters of the SHA-256 of a normalized error line, or None if the line is not an error.

    Normal form: lower case; text in quotes and any word with a path separator become `P`; a word of 6 or more hex
    characters with both a letter and a digit becomes `H`; runs of digits become `#`; white space collapsed; cut at 200.
    """
    if not isinstance(line, str):
        return None
    low = line.strip().lower()
    if not low.startswith(_MARKERS):
        return None
    t = _QUOTED.sub("P", low)
    t = " ".join("P" if ("/" in w or "\\" in w) else w for w in t.split())
    t = _HEXWORD.sub("H", t)
    t = _DIGITS.sub("#", t)
    t = " ".join(t.split())[:200]
    return hashlib.sha256(t.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Policy:
    stall_s: int = STALL_SECONDS
    repeat: int = REPEAT_ERRORS
    output_is_progress: bool = False

    @staticmethod
    def for_role(role):
        """A builder's progress is a changed tree; a tester's, guide's or check's is any output (W9.R10.3)."""
        return Policy(output_is_progress=role != "builder")


@dataclass(frozen=True)
class Stop:
    reason: str


class Continue:
    def __repr__(self):
        return "CONTINUE"


CONTINUE = Continue()


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def judge(history, now, policy):
    """Continue or Stop(reason) from the history so far. `history` is a list of tuples (kind, time) or
    (`error`, time, signature) with kind start, progress, output or error. Events after `now` have not happened.

    A stall is any gap of `stall_s` or more between two progress points (the start counts, and so does `now`), so a
    Stop stays a Stop for a later `now` and a longer history. Two errors in a row with one signature are `looping`:
    other output and edits between them do not break the run.
    """
    try:
        pol = policy if isinstance(policy, Policy) else Policy()
        if not _num(now):
            return CONTINUE
        stamps, errors = [], []
        for e in (history if isinstance(history, (list, tuple)) else []):
            if not (isinstance(e, tuple) and len(e) >= 2 and isinstance(e[0], str) and _num(e[1]) and e[1] <= now):
                continue
            kind, t = e[0], e[1]
            if kind in ("start", "progress") or (kind == "output" and pol.output_is_progress):
                stamps.append(t)
            elif kind == "error" and len(e) >= 3 and isinstance(e[2], str):
                errors.append((t, e[2]))
        errors.sort(key=lambda x: x[0])
        need = max(2, pol.repeat) if _num(pol.repeat) else 2
        sigs = [s for _t, s in errors]
        for i in range(len(sigs) - need + 1):
            if len(set(sigs[i:i + need])) == 1:
                return Stop("looping")
        if stamps:
            points = sorted(stamps) + [now]
            if any(b - a >= pol.stall_s for a, b in zip(points, points[1:])):
                return Stop("stalled")
        return CONTINUE
    except Exception:
        return CONTINUE


# ------------------------------------------------------------------------------------------------ approvals


def _t(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


@dataclass(frozen=True)
class Approval:
    """One approval: a kind, the goal and task, when it was asked, a required deadline, and the default answer, which is
    always No and cannot be set (W9.R9.1)."""
    kind: str
    goal: str
    task: str
    asked: float
    deadline: float
    default: str = field(default="no", init=False)
    answer: str | None = None
    answered_at: float | None = None

    def __post_init__(self):
        if self.kind not in ("plan", "needs-owner"):
            raise ValueError("approval kind")
        if not (isinstance(self.goal, str) and _GOAL.fullmatch(self.goal)):
            raise ValueError("approval goal")
        if self.kind == "plan":
            if self.task != "":
                raise ValueError("a plan approval has no task")
        elif not (isinstance(self.task, str) and _TASK.fullmatch(self.task)):
            raise ValueError("approval task")
        if not _t(self.asked) or not _t(self.deadline) or self.deadline <= self.asked:
            raise ValueError("an approval needs a deadline later than the time it was asked")
        if self.answer not in (None, "yes", "no"):
            raise ValueError("approval answer")


def deadline_for(kind, asked, hours=None):
    """The deadline: 168 hours for a plan, 24 for a task that needs the owner, or `hours` (1 to 168)."""
    if kind not in ("plan", "needs-owner"):
        raise ValueError("approval kind")
    if hours is None:
        hours = PLAN_HOURS if kind == "plan" else WAIT_HOURS
    if not isinstance(hours, int) or isinstance(hours, bool) or not 1 <= hours <= MAX_HOURS:
        raise ValueError("hours must be 1 to 168")
    return asked + hours * 3600


def with_answer(a, answer, at):
    """The approval with the owner's answer, or ValueError if the answer is not yes/no or comes at or after the deadline."""
    if answer not in ("yes", "no") or not _t(at) or at >= a.deadline:
        raise ValueError("this approval timed out and was denied")
    return Approval(a.kind, a.goal, a.task, a.asked, a.deadline, answer, at)


def outcome(a, now):
    """yes or no if answered in time; no once the deadline has passed; open before that. Silence is never yes."""
    if a.answer is not None:
        return a.answer
    return "no" if _t(now) and now >= a.deadline else "open"


def expired(approvals, now):
    """The approvals with no answer whose deadline is `now` or earlier."""
    if not _t(now) or not isinstance(approvals, (list, tuple)):
        return []
    return [a for a in approvals if isinstance(a, Approval) and a.answer is None and a.deadline <= now]


def effective_now(system, newest_seen):
    """The later of the system time and the newest time any record shows, so a clock set back revives nothing."""
    vals = [v for v in (system, newest_seen) if _t(v)]
    return max(vals) if vals else 0


def ago(seconds):
    if not _t(seconds) or seconds < 0:
        return "age unknown"
    s = int(seconds)
    if s < 60:
        return f"{s} s ago"
    if s < 3600:
        return f"{s // 60} min ago"
    return f"{s // 3600} h ago"


def countdown(left):
    if not _t(left) or left <= 0:
        return "denied now"
    s = int(left)
    if s < 60:
        return f"denied in {s} s"
    if s < 3600:
        return f"denied in {s // 60} min"
    return f"denied in {s // 3600} h"


def approval_sentence(a, now):
    return f"Asked {ago(now - a.asked)}, {countdown(a.deadline - now)}."
