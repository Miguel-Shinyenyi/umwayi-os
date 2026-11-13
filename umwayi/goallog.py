"""Goal orchestration (W9.3): the event log of a task, its total reader, its writer and the bounded line reader.

The log is `T-02.events.jsonl`: one JSON object per line, at most 4096 bytes, keys exactly `n`, `at`, `kind`, `data`,
`crc` (W9.R12). This module is the only code that touches an event log, and the supervisor is its only writer.

One bad line must never stall the log (pitfall 4): `read` is total, skips bad lines and says why; the writer records
each skip once, without the text of the line. The logbook is not one of these logs: a logbook that fails its tamper
check still stops every start (W9.R12.1).

The crc is CRC-32 of the canonical JSON of n, at, kind and data. It finds a torn or garbled line. It is not a defence
against someone who rewrites a line (KNOWN-LIMITS 224).
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from umwayi.errors import UmwayiError

MAX_LINE = 4096
MAX_LOG = 8 * 1024 * 1024
SKIP_REASONS = ("utf8", "long", "json", "shape", "kind", "order", "crc", "torn")

_WORD = re.compile(r"^[a-z][a-z0-9 _-]{0,31}$")
_HEX8 = re.compile(r"^[0-9a-f]{8}$")
_HEX16 = re.compile(r"^[0-9a-f]{16}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_AT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_BIG = 2 ** 31


def _int(v):
    return isinstance(v, int) and not isinstance(v, bool) and 0 <= v < _BIG


def _bool(v):
    return isinstance(v, bool)


def _word(v):
    return isinstance(v, str) and bool(_WORD.fullmatch(v))


def _hex(rx):
    return lambda v: isinstance(v, str) and bool(rx.fullmatch(v))


# kind -> ({key: check}, real). A `fingerprint` is real only when it changed; the others by kind (W9.R11.2).
KINDS = {
    "state": ({"from": _word, "to": _word, "reason": _word, "recovered": _bool}, True),
    "started": ({"role": _word, "agent": _word, "cap_uu": _int, "pid": _int}, True),
    "output": ({"lines": _int, "bytes": _int, "skipped": _int}, True),
    "error": ({"sig": _hex(_HEX16)}, True),
    "fingerprint": ({"changed": _bool, "files": _int}, True),
    "approval_requested": ({"kind": _word}, True),
    "approval_answered": ({"kind": _word, "answer": _word}, True),
    "check_result": ({"n": _int, "verdict": _word}, True),
    "skipped": ({"line": _int, "offset": _int, "length": _int, "reason": lambda v: v in SKIP_REASONS,
                 "sha256": _hex(_HEX64)}, True),
    "stopped": ({"reason": _word}, True),
    "worktree": ({"action": lambda v: v in ("made", "removed"), "base": _hex(_HEX8)}, True),
    "poll": ({}, False),
    "waiting": ({"left_s": _int}, False),
}
FSYNC_KINDS = ("state", "stopped")


class LogWriteFailed(UmwayiError):
    """An event could not be written. The supervisor must stop (W9.R13.2). Never quotes a path or an OS message."""


# --------------------------------------------------------------------------------------------- the shape


def _crc(n, at, kind, data):
    text = json.dumps({"n": n, "at": at, "kind": kind, "data": data}, sort_keys=True, separators=(",", ":"))
    return f"{zlib.crc32(text.encode('utf-8')) & 0xFFFFFFFF:08x}"


def _real_time(at):
    if not (isinstance(at, str) and _AT.fullmatch(at)):
        return False
    try:
        datetime.strptime(at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def _shape_ok(obj):
    if not isinstance(obj, dict) or set(obj) != {"n", "at", "kind", "data", "crc"}:
        return False
    if not (_int(obj["n"]) and obj["n"] >= 1 and _real_time(obj["at"]) and isinstance(obj["kind"], str)
            and isinstance(obj["data"], dict) and isinstance(obj["crc"], str)):
        return False
    return bool(_HEX8.fullmatch(obj["crc"]))


def _data_ok(kind, data):
    spec = KINDS[kind][0]
    return set(data) == set(spec) and all(check(data[k]) for k, check in spec.items())


def valid_event(obj):
    """True if `obj` is a whole, well formed event with a correct crc. Total: any value gives True or False."""
    try:
        if not _shape_ok(obj) or obj["kind"] not in KINDS or not _data_ok(obj["kind"], obj["data"]):
            return False
        return obj["crc"] == _crc(obj["n"], obj["at"], obj["kind"], obj["data"])
    except Exception:
        return False


def is_real(event):
    """A real event moves 'the last real event' of the status; a poll, a wait and an unchanged fingerprint do not."""
    if not valid_event(event):
        return False
    if event["kind"] == "fingerprint":
        return bool(event["data"]["changed"])
    return KINDS[event["kind"]][1]


def make_line(n, at, kind, data):
    """One event as bytes with its newline. A value that would not read back as valid is a ValueError."""
    obj = {"n": n, "at": at, "kind": kind, "data": data, "crc": ""}
    if not (_int(n) and n >= 1 and _real_time(at) and kind in KINDS and isinstance(data, dict) and _data_ok(kind, data)):
        raise ValueError("not a valid event")
    obj["crc"] = _crc(n, at, kind, data)
    line = json.dumps(obj, separators=(",", ":"), ensure_ascii=True).encode("ascii") + b"\n"
    if len(line) - 1 > MAX_LINE:
        raise ValueError("event too long")
    return line


# --------------------------------------------------------------------------------------------- the reader


@dataclass(frozen=True)
class Skip:
    line: int  # 1 based line number
    offset: int  # byte offset of the start of the line
    length: int  # bytes, without the newline
    reason: str
    sha256: str  # of the bad line, never its text


@dataclass
class LogRead:
    events: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    torn: bool = False
    torn_offset: int = 0
    last_n: int = 0


def _classify(line, last_n):
    """(event, None) for a good line, or (None, reason word)."""
    if len(line) > MAX_LINE:
        return None, "long"
    try:
        text = line.decode("utf-8")
    except UnicodeDecodeError:
        return None, "utf8"
    try:
        obj = json.loads(text)
    except (ValueError, RecursionError):
        return None, "json"
    if not _shape_ok(obj):
        return None, "shape"
    if obj["kind"] not in KINDS:
        return None, "kind"
    if not _data_ok(obj["kind"], obj["data"]):
        return None, "shape"
    if obj["crc"] != _crc(obj["n"], obj["at"], obj["kind"], obj["data"]):
        return None, "crc"
    if obj["n"] <= last_n:
        return None, "order"
    return obj, None


def read_full(data):
    """Read a whole log. Never raises, never loops without taking a byte, and takes linear time (W9.R12.2)."""
    out = LogRead()
    if not isinstance(data, (bytes, bytearray)):
        return out
    data = bytes(data)
    pos, line_no, size = 0, 0, len(data)
    while pos < size:
        end = data.find(b"\n", pos)
        if end == -1:  # no newline: a torn tail is waiting, not bad (W9.R12.4)
            out.torn, out.torn_offset = True, pos
            break
        line_no += 1
        line = data[pos:end]
        ev, reason = _classify(line, out.last_n)
        if ev is not None:
            out.events.append(ev)
            out.last_n = ev["n"]
        else:
            out.skipped.append(Skip(line_no, pos, len(line), reason, hashlib.sha256(line).hexdigest()))
        pos = end + 1
    return out


def read(data):
    """(events, skipped): the good events in order and one Skip for each bad line."""
    r = read_full(data)
    return r.events, r.skipped


# --------------------------------------------------------------------------------------------- the stream reader


class LineReader:
    """Lines from a child's output with a bound (W9.R12.5): at most 4096 bytes of a line are kept, the rest of an
    over-long line is thrown away to the next newline, and bytes that are not UTF-8 are replaced. `feed` gives
    (text, flagged) pairs; flagged means the line was over-long or not UTF-8 (it adds to a skipped count)."""

    def __init__(self):
        self._buf = bytearray()
        self._over = False

    def buffered(self):
        return len(self._buf)

    def _emit(self):
        raw = bytes(self._buf)
        flagged = self._over
        text = raw.decode("utf-8", "replace")
        if "\ufffd" in text and b"\xef\xbf\xbd" not in raw:
            flagged = True
        self._buf.clear()
        self._over = False
        return text, flagged

    def feed(self, chunk):
        out = []
        data = bytes(chunk) if chunk else b""
        while data:
            nl = data.find(b"\n")
            piece, data = (data, b"") if nl == -1 else (data[:nl], data[nl + 1:])
            room = MAX_LINE - len(self._buf)
            if len(piece) > room:
                self._over = True
                piece = piece[:room]
            self._buf += piece
            if nl != -1:
                out.append(self._emit())
        return out

    def flush(self):
        if not self._buf and not self._over:
            return []
        return [self._emit()]


# --------------------------------------------------------------------------------------------- the writer


def _write(fd, data):
    return os.write(fd, data)


def _fsync(fd):
    os.fsync(fd)


def _stamp(now):
    return datetime.utcfromtimestamp(int(now)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _failed():
    return LogWriteFailed("umwayi could not write its record, so it stopped (exit 2)")


class Writer:
    """The one writer of an event log. Every failure raises LogWriteFailed; nothing is truncated or rotated."""

    def __init__(self, path, clock):
        self.path = Path(path)
        self._clock = clock
        self.n = 0
        self._recorded = set()

    def open(self):
        """Read what is there, add the missing newline of a torn tail with one `torn` record, and return self."""
        try:
            data = self._read_all()
        except OSError:
            raise _failed() from None
        res = read_full(data)
        self.n = res.last_n
        self._recorded = {e["data"]["offset"] for e in res.events if e["kind"] == "skipped"}
        if res.torn:
            line = data[res.torn_offset:]
            self._raw_append(b"\n")
            self._record(Skip(0, res.torn_offset, len(line), "torn", hashlib.sha256(line).hexdigest()),
                         line_no=data.count(b"\n") + 1)
        return self

    def _read_all(self):
        from umwayi import fsutil
        if not os.path.lexists(self.path):
            return b""
        return fsutil.read_regular(self.path, MAX_LOG + MAX_LINE + 1)

    def _size(self):
        try:
            return os.lstat(self.path).st_size
        except FileNotFoundError:
            return 0

    def _raw_append(self, data):
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        try:
            fd = os.open(self.path, flags, 0o600)
        except OSError:
            raise _failed() from None
        try:
            if self._size() + len(data) > MAX_LOG:
                raise _failed()
            try:
                done = _write(fd, data)
            except OSError:
                raise _failed() from None
            if done != len(data):
                raise _failed()
            return fd
        finally:
            os.close(fd)

    def append(self, kind, data):
        """Append one event; `kind` and `data` must be valid (ValueError otherwise, and nothing is written)."""
        n = self.n + 1
        line = make_line(n, _stamp(self._clock()), kind, data)
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        try:
            fd = os.open(self.path, flags, 0o600)
        except OSError:
            raise _failed() from None
        try:
            if self._size() + len(line) > MAX_LOG:
                raise _failed()
            try:
                done = _write(fd, line)
                if done != len(line):
                    raise _failed()
                if kind in FSYNC_KINDS:
                    _fsync(fd)
            except OSError:
                raise _failed() from None
        finally:
            os.close(fd)
        self.n = n

    def probe(self):
        """A real write in the goal folder, so a read-only folder or a full disk is found now (W9.R13.1)."""
        p = self.path.parent / ".probe"
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        try:
            fd = os.open(p, flags, 0o600)
        except OSError:
            raise _failed() from None
        try:
            try:
                if _write(fd, b"0") != 1:
                    raise _failed()
            except OSError:
                raise _failed() from None
        finally:
            os.close(fd)
            try:
                os.unlink(p)
            except OSError:
                pass

    def _record(self, skip, line_no=None):
        self.append("skipped", {"line": line_no if line_no is not None else skip.line, "offset": skip.offset,
                                "length": skip.length, "reason": skip.reason, "sha256": skip.sha256})
        self._recorded.add(skip.offset)

    def record_skips(self):
        """Append one `skipped` event for each bad line not recorded yet. The same line is never recorded twice."""
        try:
            data = self._read_all()
        except OSError:
            raise _failed() from None
        count = 0
        for s in read_full(data).skipped:
            if s.offset in self._recorded:
                continue
            self._record(s)
            count += 1
        return count
