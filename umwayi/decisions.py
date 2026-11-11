"""Layer 13, slice 2: Reversal. `umwayi decision reopen ID_OR_HASH --reason TEXT --by NAME [--date D]`.

A closed decision (a queue row of kind decision, answered or closed) is reopened as a question, never rewritten:

  * one NEW logbook entry says it is a reopen and names the old entry by its full hash (its Chain value);
  * one NEW queue row (kind decision, status open) is opened, in the same queue commit as the entry;
  * the old entry, the old row and every other logbook line are never changed or marked. This module writes
    nothing itself: its one write is `taskqueue.add_with_entry`, which appends one entry through the checked
    append of the logbook.

The order (design.md, "Slice 2: Reversal"): the arguments (64), the lock, the tamper and chain check (1),
queue.md parsed (1), the old entry resolved (1), the row is a decision that is not open (1), no earlier reopen of
that entry whose row is still open (1), then the new row and the entry in one queue commit.

A decision that was reopened before and whose reopening row is answered or closed is reopened through that row:
the link then names the newest closing entry of the reopening row (13.R4.8), so every closing entry is reopened
at most once and the reopens form one chain that can be followed by hash from the newest entry back to the first.

Messages hold ids, dates, hashes and fixed words, never the reason, an answer or a revisit text (13.R1.8). The
command's output shows the revisit text the owner recorded, because that is what the reopen is for (13.R5.4).
"""

from __future__ import annotations

import errno
import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from umwayi import logbook, taskqueue
from umwayi.errors import UmwayiError, UsageError

try:
    import fcntl
except ImportError:  # for example on Windows
    fcntl = None

SOURCE = "umwayi decision reopen"
ANSWER_SOURCE = "umwayi queue answer"
CLOSE_SOURCE = "umwayi queue close"
CLOSING_SOURCES = (ANSWER_SOURCE, CLOSE_SOURCE)
MAX_REASON = 300
MAX_BY = 40
LOCK_NAME = "reopen.lock"
LOCK_WAIT_SECONDS = 3.0
_LOCK_POLL_SECONDS = 0.05
_BUSY = {errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES}

NOT_RECORDED = "not recorded before layer 13"
NO_ANSWER = "not recorded, closed without an answer"

_ID = re.compile(r"Q-\d{4,}")
_HASH = re.compile(r"[0-9a-f]{64}")
_CLOSING_ID = re.compile(r"^(Q-\d{4,}) ")  # the id at the start of a closing entry's Added line
_REVISIT = re.compile(r"(Q-\d{4,}) marked answered on \d{4}-\d{2}-\d{2} \(status open to answered, \d+ characters "
                      r"of answer\); revisit if: (.{1,200})")
_CLOSED = re.compile(r"(Q-\d{4,}) closed on \d{4}-\d{2}-\d{2} \(status (open|answered) to closed\)")
_REOPEN = re.compile(r"Reopen of entry ([0-9a-f]{64}) \((Q-\d{4,}) (?:answered|closed) on \d{4}-\d{2}-\d{2}\); "
                     r"new decision (Q-\d{4,}) opened by ([^;|]{1,40}); reason: (.{1,300})")

NOTHING = "Nothing was changed."


@dataclass(frozen=True)
class Reopened:
    asked: str  # the id the owner named, or the id of the entry the hash named
    old_id: str  # the decision whose closing entry is linked (the end of its chain of reopens)
    new_id: str
    old_hash: str
    old_source: str
    old_date: str
    revisit: str


# ------------------------------------------------------------------ arguments


def _check_target(target) -> str:
    if isinstance(target, str) and (_ID.fullmatch(target) or _HASH.fullmatch(target)):
        return target
    raise UsageError("decision reopen: the target is a queue id like Q-0007 or a hash of 64 lowercase hex "
                     "characters (the Chain value of a logbook entry). " + NOTHING)


def _check_line(value, what: str, limit: int, forbidden: str) -> str:
    v = value.strip() if isinstance(value, str) else ""
    if not v or len(v) > limit or not v.isprintable() or any(c in v for c in forbidden):
        shown = " or ".join(forbidden)
        raise UsageError(f"decision reopen: {what} must be one line of plain text, 1 to {limit} characters, "
                         f"without {shown}. " + NOTHING)
    return v


# ------------------------------------------------------------------ the lock


@contextmanager
def _held(root: Path):
    """One reopen at a time: fcntl.flock on .umwayi/reopen.lock, from the checks to the commit.

    Waits up to LOCK_WAIT_SECONDS, then refuses. Without a .umwayi folder there is no hash record and so no
    intact chained logbook: nothing is created, and the read that follows refuses.
    """
    state = Path(root) / logbook.STATE_DIR
    if state.is_symlink() or (state.exists() and not state.is_dir()):
        raise UmwayiError("decision reopen: .umwayi must be a normal folder. " + NOTHING)
    if not state.exists():
        yield
        return
    if fcntl is None:
        raise UmwayiError("decision reopen: file locking is not available on this platform. " + NOTHING)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(state / LOCK_NAME, flags, 0o644)
    except OSError:
        raise UmwayiError("decision reopen: the lock file .umwayi/reopen.lock cannot be opened (is it a link or a "
                          "folder?). " + NOTHING) from None
    try:
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as e:
                if e.errno not in _BUSY:
                    raise UmwayiError("decision reopen: the operating system refused the lock on "
                                      ".umwayi/reopen.lock. " + NOTHING) from None
                if time.monotonic() >= deadline:
                    raise UmwayiError("decision reopen: another reopen holds the lock .umwayi/reopen.lock. Try "
                                      "again in a moment. " + NOTHING) from None
                time.sleep(_LOCK_POLL_SECONDS)
        yield
    finally:
        os.close(fd)  # lets go of the lock


# ------------------------------------------------------------------ reading the record


def _closing_id(entry) -> str | None:
    """The id of a closing entry (a queue answer or close), or None for any other entry."""
    if entry.source not in CLOSING_SOURCES:
        return None
    m = _CLOSING_ID.match(entry.added)
    return m.group(1) if m else None


class _Record:
    """The chained logbook and queue.md, read once under the lock."""

    def __init__(self, pairs: list, rows: list):
        self.pairs = pairs
        self.rows = {r.id: r for r in rows}
        self.closing: dict = {}  # id -> indexes of its closing entries, oldest first
        self.by_hash: dict = {}
        self.reopens: dict = {}  # linked hash -> (index, new id)
        for i, (e, c) in enumerate(pairs):
            rid = _closing_id(e)
            if rid is not None:
                self.closing.setdefault(rid, []).append(i)
            if c is not None:
                self.by_hash[c] = i
                if e.source == SOURCE:
                    m = _REOPEN.fullmatch(e.added)
                    if m and m.group(1) not in self.reopens:
                        self.reopens[m.group(1)] = (i, m.group(3))

    def newest_closing(self, rid: str) -> int | None:
        found = self.closing.get(rid)
        return found[-1] if found else None

    def row_ok(self, rid: str, missing: str) -> None:
        """The row is a decision that is not open, or a refusal."""
        row = self.rows.get(rid)
        if row is None:
            raise UmwayiError(missing)
        if row.kind != "decision":
            raise UmwayiError(f"decision reopen: {rid} is a {row.kind}; only a decision can be reopened. " + NOTHING)
        if row.status == "open":
            raise UmwayiError(f"decision reopen: {rid} is open; only an answered or closed decision can be "
                              "reopened. " + NOTHING)

    def revisit(self, index: int) -> str:
        """What would change my mind, as recorded in the answer entry of this closing entry (13.R5.4)."""
        entry = self.pairs[index][0]
        rid = _closing_id(entry)
        if entry.source == CLOSE_SOURCE:
            m = _CLOSED.fullmatch(entry.added)
            if m and m.group(1) == rid and m.group(2) == "open":
                return NO_ANSWER
            answers = [i for i in self.closing.get(rid, []) if i < index and self.pairs[i][0].source == ANSWER_SOURCE]
            if not answers:
                return NOT_RECORDED
            entry = self.pairs[answers[-1]][0]
        m = _REVISIT.fullmatch(entry.added)
        return m.group(2) if m and m.group(1) == rid else NOT_RECORDED


def _read(root: Path) -> _Record:
    try:
        pairs = logbook.read_chained(root)
    except UmwayiError as e:
        raise UmwayiError(f"decision reopen: the logbook is not intact ({e}). " + NOTHING) from None
    if not any(c is not None for _e, c in pairs):
        raise UmwayiError("decision reopen: the hash chain has not started, so no entry can be linked by its hash. "
                          "Start it once with 'umwayi logbook seal --chain --by NAME'. " + NOTHING)
    rows = taskqueue.list_rows(root)
    return _Record(pairs, rows)


def _resolve(rec: _Record, target: str) -> tuple:
    """(the id that was asked for, the index of the old entry) or a refusal (13.R4.2, 13.R4.5)."""
    if _HASH.fullmatch(target):
        index = rec.by_hash.get(target)
        if index is None:
            raise UmwayiError("decision reopen: no entry of the logbook has this hash. " + NOTHING)
        rid = _closing_id(rec.pairs[index][0])
        if rid is None:
            raise UmwayiError("decision reopen: the entry with this hash is not a closing entry of a decision "
                              "(umwayi queue answer or umwayi queue close). " + NOTHING)
        if rec.newest_closing(rid) != index:
            raise UmwayiError(f"decision reopen: the entry with this hash is not the newest closing entry of {rid}. "
                              + NOTHING)
        rec.row_ok(rid, f"decision reopen: queue.md and the logbook disagree: queue.md has no row {rid}. " + NOTHING)
        return rid, index
    rid = target
    index = rec.newest_closing(rid)
    if index is None:
        rec.row_ok(rid, f"decision reopen: no row with id {rid} in queue.md. " + NOTHING)
        raise UmwayiError(f"decision reopen: {rid} has no closing entry in the logbook (it was answered or closed "
                          "by hand or before the logbook), so there is no entry to link. " + NOTHING)
    rec.row_ok(rid, f"decision reopen: no row with id {rid} in queue.md. " + NOTHING)
    if rec.pairs[index][1] is None:
        raise UmwayiError(f"decision reopen: the closing entry of {rid} was written before the hash chain started, "
                          "so it has no hash to link. " + NOTHING)
    return rid, index


def _follow(rec: _Record, index: int) -> int:
    """From an old entry to the end of its chain of reopens: the newest closing entry not reopened yet (13.R4.8).

    A reopening row that is still open refuses (13.R4.5). A reopening row that queue.md does not have, or that is
    answered or closed in queue.md with no closing entry after the reopen, means queue.md and the logbook disagree.
    """
    for _ in range(len(rec.pairs) + 1):  # each hop moves to a later entry, so this always ends
        old_hash = rec.pairs[index][1]
        if old_hash is None:
            raise UmwayiError("decision reopen: the old entry was written before the hash chain started. " + NOTHING)
        if old_hash not in rec.reopens:
            return index
        reopen_at, new_id = rec.reopens[old_hash]
        rid = _closing_id(rec.pairs[index][0])
        row = rec.rows.get(new_id)
        if row is None:
            raise UmwayiError(f"decision reopen: queue.md and the logbook disagree: the logbook says {rid} was "
                              f"reopened as {new_id}, and queue.md has no row {new_id}. The row is not made again. "
                              + NOTHING)
        if row.status == "open":
            raise UmwayiError(f"decision reopen: {rid} was already reopened as {new_id}, which is still open. Answer "
                              f"or close {new_id} first. " + NOTHING)
        nxt = rec.newest_closing(new_id)
        if nxt is None or nxt < reopen_at or row.kind != "decision":
            raise UmwayiError(f"decision reopen: queue.md and the logbook disagree: {new_id} is {row.status} in "
                              "queue.md but the logbook has no closing entry for it. " + NOTHING)
        index = nxt
    raise UmwayiError("decision reopen: the chain of reopens could not be followed. " + NOTHING)


def _cut(text: str, limit: int) -> str:
    """At most `limit` characters, never cut in the middle of a word."""
    if len(text) <= limit:
        return text
    head = text[:limit]
    if text[limit] != " " and " " in head:
        head = head.rsplit(" ", 1)[0]
    return head.rstrip()


# ------------------------------------------------------------------ the command


def reopen(root: Path, target: str, reason: str, by: str, when: str) -> Reopened:
    """Reopen a closed decision: one new entry and one new open row, in one queue commit (13.R4)."""
    target = _check_target(target)
    reason = _check_line(reason, "--reason", MAX_REASON, "|")
    by = _check_line(by, "--by", MAX_BY, "|;")
    if not logbook.real_date(when):
        raise UsageError("decision reopen: date must be a real date YYYY-MM-DD. " + NOTHING)
    root = Path(root)
    with _held(root):
        rec = _read(root)
        asked, index = _resolve(rec, target)
        index = _follow(rec, index)
        old_entry, old_hash = rec.pairs[index]
        old_id = _closing_id(old_entry)
        rec.row_ok(old_id, f"decision reopen: queue.md and the logbook disagree: queue.md has no row {old_id}. "
                   + NOTHING)
        revisit = rec.revisit(index)
        verb = "answered" if old_entry.source == ANSWER_SOURCE else "closed"

        def entry_for(row):
            return logbook.Entry(
                date=when,
                source=SOURCE,
                added=(f"Reopen of entry {old_hash} ({old_id} {verb} on {old_entry.date}); new decision {row.id} "
                       f"opened by {by}; reason: {reason}"),
                checked=(f"the hash chain was intact before this entry; {old_hash} is a chained entry of source "
                         f"{old_entry.source} for {old_id}; {old_id} is a decision that is not open; "
                         f"revisit if recorded then: {revisit}"),
                not_done=(f"The old entry, the old row {old_id} and the rules were not changed or marked. "
                          "Nothing was decided again."),
            )

        row = taskqueue.add_with_entry(
            root, "decision", f"Reopen decision {old_id}",
            _cut(f"Reopened on {when} by {by}: {reason}", taskqueue.MAX_RECOMMENDATION), when, entry_for)
    return Reopened(asked, old_id, row.id, old_hash, old_entry.source, old_entry.date, revisit)


def render(r: Reopened) -> list:
    lines = []
    if r.asked != r.old_id:
        lines.append(f"{r.asked} was reopened before; the newest decision in its chain of reopens is {r.old_id}.")
    lines += [
        f"Reopened {r.old_id} as {r.new_id} (decision, open): Reopen decision {r.old_id}",
        f"Linked entry: {r.old_hash} ({r.old_source}, {r.old_date})",
        f"Revisit if recorded then: {r.revisit}",
        f"The old entry and the old row {r.old_id} were not changed or marked. Nothing was decided again.",
        f"Answer it with: umwayi queue answer {r.new_id} --answer TEXT --revisit-if TEXT",
    ]
    return lines
