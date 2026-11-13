"""W19 part 5: the Kiro Crew lessons as checks. `umwayi stalls check EVENTS.json`.

Small pure functions over a JSON list of builder events. They report four things (W9.R9, W9.R10, W9.R11):

  stall    a builder with no push or real event for 30 minutes
  loop     the same error signature twice in a row
  no       an owner approval with no answer past its deadline, or answered after it: it counts as No, never as Yes
  refused  a status that shows only "connected" with no last event time

Rules of this module:
  - It reads one file and changes nothing. It is not wired into any schedule.
  - It never repeats text from the file. Every string in the file is checked against a closed list or a strict
    pattern first, so what is printed is a short id that passed the pattern, a number or a fixed word.
  - Time is passed in (`now`). Nothing here reads a clock except `check_file` when the caller gives no clock.
  - Fail closed: anything unreadable or malformed is `Malformed` (exit 2). It is never read as "nothing found".
  - Exit codes: 0 nothing found, 3 a finding (Ask me first), 2 unreadable or malformed, 64 usage. Never 1.
"""

from __future__ import annotations

import datetime
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from umwayi import fsutil

MAX_BYTES = 1_000_000  # the same limit as routing.py
MAX_EVENTS = 20_000
STALL_SECONDS = 1800  # W9.R10.1: 30 minutes with no progress
LOOP_COUNT = 2  # W9.R10.1: two errors in a row with the same signature

KINDS = ("push", "state", "started", "output", "error", "fingerprint", "approval_requested", "approval_answered",
         "check_result", "skipped", "stopped", "status", "poll", "waiting")
STATES = ("queued", "running", "in review", "needs owner", "merged", "failed", "stopped")
# W9.R11.2 and the owner's answer to question 3: these reset the stall timer. Output, poll, waiting and status do not.
# A fingerprint counts only when it says changed: true.
PROGRESS_KINDS = ("push", "state", "started", "error", "approval_requested", "approval_answered", "check_result",
                  "skipped", "stopped")
KEYS = ("builder", "t", "kind", "sig", "id", "deadline", "connected", "last_event", "state", "changed")

_ID = re.compile(r"[A-Za-z0-9._-]{1,40}\Z")
_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_SIG = re.compile(r"[0-9a-f]{16}\Z")


class Malformed(Exception):
    """The input is unreadable or malformed. The message is fixed words and numbers, never file text."""


@dataclass(frozen=True)
class Event:
    n: int  # position in the file, from 1
    builder: str
    t: datetime.datetime
    kind: str
    sig: str | None = None
    id: str | None = None
    deadline: datetime.datetime | None = None
    connected: bool | None = None
    last_event: datetime.datetime | None = None
    has_last_event: bool = False
    state: str | None = None
    changed: bool = False


@dataclass(frozen=True)
class Finding:
    rule: str  # STALL, STOP, NO or REFUSED
    builder: str
    line: str


def _pairs(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise Malformed("a key is repeated")
        d[k] = v
    return d


def _bad_constant(_name):
    raise Malformed("the file is not valid JSON")


def _time(value, n: int, what: str) -> datetime.datetime:
    if not isinstance(value, str) or not _TIME.match(value):
        raise Malformed(f"event {n}: {what} is not a UTC time like 2026-11-13T09:30:00Z")
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        raise Malformed(f"event {n}: {what} is not a real time") from None


def _id(value, n: int, what: str) -> str:
    if not isinstance(value, str) or not _ID.match(value):
        raise Malformed(f"event {n}: {what} must be 1 to 40 letters, digits, dots, dashes or underscores")
    return value


def parse(data: bytes, now: datetime.datetime) -> list[Event]:
    """Bytes of the events file to a list of events, strict and total: it returns events or raises Malformed."""
    if len(data) > MAX_BYTES:
        raise Malformed(f"the file is larger than {MAX_BYTES} bytes")
    try:
        text = data.decode("utf-8")
        raw = json.loads(text, object_pairs_hook=_pairs, parse_constant=_bad_constant)
    except Malformed:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise Malformed("the file is not valid UTF-8 JSON") from None
    if not isinstance(raw, list):
        raise Malformed("the file must hold one JSON list of events")
    if len(raw) > MAX_EVENTS:
        raise Malformed(f"the list has more than {MAX_EVENTS} events")
    out: list[Event] = []
    approvals: dict[str, int] = {}
    for n, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise Malformed(f"event {n}: it must be a JSON object")
        if any(k not in KEYS for k in item):
            raise Malformed(f"event {n}: it has a key that is not allowed")
        for needed in ("builder", "t", "kind"):
            if needed not in item:
                raise Malformed(f"event {n}: a required key is missing")
        kind = item["kind"]
        if not isinstance(kind, str) or kind not in KINDS:
            raise Malformed(f"event {n}: the kind is not one of the allowed kinds")
        builder = _id(item["builder"], n, "the builder")
        t = _time(item["t"], n, "t")
        if t > now:
            raise Malformed(f"event {n}: t is in the future")
        kw: dict = {}
        if "sig" in item:
            if kind != "error" or not isinstance(item["sig"], str) or not _SIG.match(item["sig"]):
                raise Malformed(f"event {n}: sig must be 16 lower case hex characters and only on an error")
            kw["sig"] = item["sig"]
        if kind == "error" and "sig" not in kw:
            raise Malformed(f"event {n}: an error needs a sig")
        if "id" in item:
            if kind not in ("approval_requested", "approval_answered"):
                raise Malformed(f"event {n}: id is only for approval events")
            kw["id"] = _id(item["id"], n, "the id")
        if kind in ("approval_requested", "approval_answered") and "id" not in kw:
            raise Malformed(f"event {n}: an approval event needs an id")
        if "deadline" in item:
            if kind != "approval_requested":
                raise Malformed(f"event {n}: deadline is only for approval_requested")
            kw["deadline"] = _time(item["deadline"], n, "the deadline")
        if kind == "approval_requested":
            if "deadline" not in kw:
                raise Malformed(f"event {n}: an approval request needs a deadline")
            if kw["deadline"] <= t:
                raise Malformed(f"event {n}: the deadline must be after t")
            if kw["id"] in approvals:
                raise Malformed(f"event {n}: an approval id is used twice")
            approvals[kw["id"]] = n
        if kind == "approval_answered" and kw["id"] not in approvals:
            raise Malformed(f"event {n}: an answer has no earlier request")
        if "state" in item:
            if kind != "state" or not isinstance(item["state"], str) or item["state"] not in STATES:
                raise Malformed(f"event {n}: state must be an allowed state and only on a state event")
            kw["state"] = item["state"]
        if kind == "state" and "state" not in kw:
            raise Malformed(f"event {n}: a state event needs a state")
        if "changed" in item:
            if kind != "fingerprint" or not isinstance(item["changed"], bool):
                raise Malformed(f"event {n}: changed must be true or false and only on a fingerprint")
            kw["changed"] = item["changed"]
        if "connected" in item:
            if kind != "status" or not isinstance(item["connected"], bool):
                raise Malformed(f"event {n}: connected must be true or false and only on a status")
            kw["connected"] = item["connected"]
        if kind == "status" and "connected" not in kw:
            raise Malformed(f"event {n}: a status needs connected")
        if "last_event" in item:
            if kind != "status":
                raise Malformed(f"event {n}: last_event is only for a status")
            kw["has_last_event"] = item["last_event"] is not None
            if item["last_event"] is not None:
                le = _time(item["last_event"], n, "last_event")
                if le > now:
                    raise Malformed(f"event {n}: last_event is in the future")
                kw["last_event"] = le
        out.append(Event(n=n, builder=builder, t=t, kind=kind, **kw))
    return out


def _by_builder(events: list[Event]) -> dict[str, list[Event]]:
    groups: dict[str, list[Event]] = {}
    for e in sorted(events, key=lambda e: (e.t, e.n)):  # time order, file order for equal times
        groups.setdefault(e.builder, []).append(e)
    return groups


def is_progress(e: Event) -> bool:
    """A push or a real event. Output, poll, waiting, status and an unchanged fingerprint are not."""
    if e.kind == "fingerprint":
        return e.changed
    return e.kind in PROGRESS_KINDS


def is_active(history: list[Event]) -> bool:
    """False once the builder's last state, started or stopped event says it is not running (question 7)."""
    active = True
    for e in history:
        if e.kind == "started":
            active = True
        elif e.kind == "stopped":
            active = False
        elif e.kind == "state":
            active = e.state == "running"
    return active


def stalled_seconds(history: list[Event], now: datetime.datetime) -> int | None:
    """Seconds since the last push or real event (or since the first event if there is none); None if not active."""
    if not history or not is_active(history):
        return None
    marks = [e.t for e in history if is_progress(e)]
    ref = max(marks) if marks else history[0].t
    return max(0, int((now - ref).total_seconds()))


def find_stalls(events: list[Event], now: datetime.datetime) -> list[Finding]:
    out = []
    for builder, history in sorted(_by_builder(events).items()):
        secs = stalled_seconds(history, now)
        if secs is not None and secs >= STALL_SECONDS:
            out.append(Finding("STALL", builder, f"STALL {builder} {secs // 60} min no push or event"))
    return out


def find_loops(events: list[Event]) -> list[Finding]:
    out = []
    for builder, history in sorted(_by_builder(events).items()):
        if not is_active(history):
            continue
        errors = [e for e in history if e.kind == "error"]
        for a, b in zip(errors, errors[LOOP_COUNT - 1:]):
            if a.sig == b.sig:
                out.append(Finding("STOP", builder, f"STOP {builder} same error twice, sig {a.sig[:8]}"))
                break
    return out


def find_unanswered(events: list[Event], now: datetime.datetime) -> list[Finding]:
    """An approval is No when nobody answered by its deadline, or the answer came at or after it."""
    requests = {e.id: e for e in events if e.kind == "approval_requested"}
    answers: dict[str, datetime.datetime] = {}
    for e in sorted(events, key=lambda e: (e.t, e.n)):
        if e.kind == "approval_answered" and e.id not in answers:
            answers[e.id] = e.t
    out = []
    for aid, req in sorted(requests.items()):
        answered = answers.get(aid)
        if answered is None:
            if now >= req.deadline:
                out.append(Finding("NO", req.builder, f"NO {aid} timed out, counts as No"))
        elif answered >= req.deadline:
            out.append(Finding("NO", req.builder, f"NO {aid} answered after the deadline, counts as No"))
    return out


def find_bare_status(events: list[Event]) -> list[Finding]:
    return [Finding("REFUSED", e.builder, f"REFUSED {e.builder} status has no last event time")
            for e in sorted(events, key=lambda e: (e.builder, e.t, e.n))
            if e.kind == "status" and e.last_event is None]


def check_events(events: list[Event], now: datetime.datetime) -> list[Finding]:
    """All four checks. Pure: the same events and the same `now` give the same findings in the same order."""
    return (find_stalls(events, now) + find_loops(events) + find_unanswered(events, now) + find_bare_status(events))


def check_file(path: Path, now: datetime.datetime) -> list[Finding]:
    """Read one regular file (at most MAX_BYTES) and check it. Raises Malformed when it cannot be trusted."""
    try:
        data = fsutil.read_regular(Path(path), MAX_BYTES)
    except fsutil.TooBig:
        raise Malformed(f"the file is larger than {MAX_BYTES} bytes") from None
    except OSError:
        raise Malformed("the file cannot be read: it must be a regular file that exists") from None
    return check_events(parse(data, now), now)


def utc_now(clock=None) -> datetime.datetime:
    """The time of day in UTC, to the second. `clock` returns seconds since the epoch (default time.time)."""
    seconds = (clock or time.time)()
    return datetime.datetime.fromtimestamp(int(seconds), tz=datetime.timezone.utc)
