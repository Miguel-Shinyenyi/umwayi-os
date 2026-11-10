"""Layer 5: the logbook (LOGBOOK.md).

An append-only record of every change. This module is the one place that
writes it, and every layer uses the same checked `append`.

Rules:
  * The logbook file is only ever opened in append mode (to write) or read.
    Earlier bytes are never edited by this tool. The one exception is
    `recover_torn_tail`, which the owner runs by hand: it cuts off only bytes
    that no hash record ever covered and that are exactly the start of the
    entry an interrupted write intended.
  * Tamper check: after every write the SHA-256 of the whole file is recorded
    in .umwayi/logbook.sha256. Before every write it is recomputed. If it does
    not match, or the record is missing for an existing logbook, nothing is
    written. Only the explicit `seal` command records a hash for an unrecorded
    or hand-edited logbook. Nothing is sealed automatically.
  * Every entry must be well formed, and entry dates never go backwards.
  * A lock (fcntl.flock on .umwayi/logbook.lock) stops two writers from
    interleaving. The kernel lets go of it when a writer dies, so a killed
    writer never leaves a lock behind. The file is never deleted.
  * Crash safety (Layer 5 addendum): before a write appends anything, it
    records its intent in .umwayi/logbook.pending (the record it started from,
    the whole file's hash and length before and after, the exact bytes). A
    write stopped half way (SIGKILL, a power cut) is finished or dropped by the
    next writer only when the files are in exactly one of the two states the
    intent names, and that recovery writes one entry. Anything else is refused
    like a hand edit.
  * SIGTERM, SIGHUP, SIGINT and SIGQUIT do not cut a write: they are held off
    from writing the intent to removing it and delivered once afterwards.
    Writes run in the main thread only.
  * Error messages never contain the text of a logbook line.

File format:

    # Logbook

    ## 2026-11-07

    - Source: umwayi queue add
    - Added: ...
    - Checked: ...
    - Not done: ...
"""

from __future__ import annotations

import errno
import hashlib
import os
import re
import signal
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date as _date
from pathlib import Path

from umwayi.errors import UmwayiError, UsageError
from umwayi.fsutil import atomic_write, fsync_dir

try:
    import fcntl
except ImportError:  # for example on Windows: the logbook cannot be written there
    fcntl = None

LOGBOOK_NAME = "LOGBOOK.md"
HEADER_LINE = "# Logbook"
HEADER = HEADER_LINE + "\n"
STATE_DIR = ".umwayi"
RECORD_NAME = "logbook.sha256"
LOCK_NAME = "logbook.lock"
PENDING_NAME = "logbook.pending"
LOCK_WAIT_SECONDS = 3.0  # how long a write waits for another writer
_LOCK_POLL_SECONDS = 0.02
READ_SETTLE_SECONDS = 1.0  # how long a reader waits for a write it saw half way to settle

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HEADING = re.compile(r"^## (\d{4}-\d{2}-\d{2})$")
_RECORD = re.compile(r"^([0-9a-f]{64})\n?$")
_HEX = re.compile(r"[0-9a-f]{64}")
FIELDS = (("Source", "source"), ("Added", "added"), ("Checked", "checked"), ("Not done", "not_done"))
MAX_BY = 100

INTENT_MAGIC = "umwayi logbook intent 1"
INTENT_KINDS = ("write", "recover", "seal")
MAX_INTENT_ENTRY = 1 << 20  # an entry is a few hundred bytes; anything this big is not an intent umwayi wrote
_HELD_SIGNALS = tuple(getattr(signal, n) for n in ("SIGTERM", "SIGHUP", "SIGINT", "SIGQUIT") if hasattr(signal, n))
_BUSY = {errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES}
RECOVER_SOURCE = "umwayi logbook recover"
SEAL_SOURCE = "umwayi logbook seal"
CHAIN_PREFIX = "- Chain: "
_ANCHOR = re.compile(r"([1-9][0-9]{0,9}):([0-9a-f]{64})")


@dataclass(frozen=True)
class Entry:
    date: str  # YYYY-MM-DD
    source: str  # which command wrote this
    added: str  # what was added
    checked: str  # what was checked
    not_done: str  # what was not done


@dataclass(frozen=True)
class ParsedEntry:
    line: int  # 1-based line of the "## date" heading
    entry: Entry
    chain: str | None = None  # the value of its "- Chain:" line (hash chain addendum), or None
    text: str = ""  # the lines from "## DATE" through "- Not done:", each with its newline: what the chain hashes


@dataclass(frozen=True)
class ChainState:
    """The hash chain of a parsed logbook (Layer 5 addendum, "Logbook hash chain")."""
    started: bool
    values: tuple  # the Chain value of every chained entry that checked out, oldest first
    broken: "Problem | None" = None  # the first broken entry; never its text or its Chain value


@dataclass(frozen=True)
class Problem:
    where: str  # "line 12", "record" or "file"
    message: str

    def render(self) -> str:
        return f"{self.where}: {self.message}"


@dataclass(frozen=True)
class Report:
    entries: int
    problems: list
    notes: list = field(default_factory=list)  # information, not problems (an interrupted write that can be recovered)
    chain_note: str = ""  # information about the hash chain when it is not broken (started or not, and its length)


@dataclass(frozen=True)
class SealResult:
    entries_before: int
    sha256: str


def real_date(value: str) -> bool:
    if not isinstance(value, str) or not _DATE.match(value):
        return False
    try:
        _date(int(value[:4]), int(value[5:7]), int(value[8:10]))
    except ValueError:
        return False
    return True


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------------ render


def chain_value(prev: str, text: str) -> str:
    """The Chain value of an entry: SHA-256 of the previous value, one newline, and the entry text."""
    return hashlib.sha256((prev + "\n" + text).encode("utf-8")).hexdigest()


def render(entry: Entry, prev: str | None = None) -> str:
    """The text of one entry, starting with a blank line. With prev (the newest Chain value, or for the first
    chained entry the SHA-256 of the file before it) the entry ends with its Chain line."""
    if not real_date(entry.date):
        raise UmwayiError("logbook: date must be a real date YYYY-MM-DD")
    for _label, name in FIELDS:
        value = getattr(entry, name)
        if not isinstance(value, str) or not value.strip():
            raise UmwayiError(f"logbook: '{name}' must not be empty")
        if not value.isprintable() or value != value.strip():
            raise UmwayiError(f"logbook: '{name}' must be one line of plain text without spaces at the ends")
    lines = [f"\n## {entry.date}\n", "\n"]
    for label, name in FIELDS:
        lines.append(f"- {label}: {getattr(entry, name)}\n")
    block = "".join(lines)
    if prev is not None:
        if not (isinstance(prev, str) and _HEX.fullmatch(prev)):
            raise UmwayiError("logbook: the previous Chain value must be 64 lowercase hex characters")
        block += f"{CHAIN_PREFIX}{chain_value(prev, block[1:])}\n"
    return block


# ------------------------------------------------------------------- parse


def parse(text: str) -> tuple[list, list]:
    """Parse a whole logbook. Returns (entries, problems).

    Problems carry a line number and a generic message, never the line text.
    """
    if text == "":
        return [], [Problem("file", "the logbook is empty, it must start with the line '# Logbook'")]
    problems: list[Problem] = []
    entries: list[ParsedEntry] = []
    ends_with_newline = text.endswith("\n")
    lines = text.split("\n")
    if ends_with_newline:
        lines.pop()
    n = len(lines)
    if lines[0] != HEADER_LINE:
        problems.append(Problem("line 1", "the first line must be the logbook header"))
    if not ends_with_newline:
        problems.append(Problem(f"line {n}", "the file does not end with a newline, the last entry may be cut off"))

    heads = [i for i in range(1, n) if lines[i].startswith("##")]
    first = heads[0] if heads else n
    for i in range(1, first):
        if heads and i == first - 1 and lines[i] == "":
            continue  # the one blank line before the first entry
        problems.append(Problem(
            f"line {i + 1}", "unexpected blank line" if lines[i] == "" else "text outside the header and entries"))
    if heads and first == 1:
        problems.append(Problem("line 2", "missing blank line before the first entry"))

    previous = None
    for k, h in enumerate(heads):
        nxt = heads[k + 1] if k + 1 < len(heads) else n
        has_next = k + 1 < len(heads)
        body = lines[h + 1 : nxt]
        found = len(problems)

        if has_next:
            if body and body[-1] == "":
                body = body[:-1]
            else:
                problems.append(Problem(f"line {nxt}", "missing blank line before the next entry"))

        m = _HEADING.match(lines[h])
        when = m.group(1) if m and real_date(m.group(1)) else None
        if when is None:
            problems.append(Problem(f"line {h + 1}", "the entry heading must be '## ' and a real date YYYY-MM-DD"))
        elif previous is not None and when < previous:
            problems.append(Problem(f"line {h + 1}", "the date goes backwards compared with an earlier entry"))
        if when is not None:
            previous = when if previous is None else max(previous, when)

        values: dict[str, str] = {}
        chain = None
        if not body:
            problems.append(Problem(f"line {h + 1}", "the entry is cut off after its heading"))
        else:
            if body[0] == "":
                bullets, first_bullet = body[1:], h + 2  # 0-based index of the first bullet
            else:
                problems.append(Problem(f"line {h + 2}", "missing blank line after the entry heading"))
                bullets, first_bullet = body, h + 1
            for i, (label, name) in enumerate(FIELDS):
                line_no = first_bullet + i + 1
                if i >= len(bullets):
                    problems.append(Problem(f"line {line_no - 1}", f"the entry is cut off, the {label} field is missing"))
                    break
                prefix = f"- {label}: "
                if not bullets[i].startswith(prefix):
                    problems.append(Problem(f"line {line_no}", f"expected the {label} field here"))
                    break
                value = bullets[i][len(prefix):]
                if not value.strip() or not value.isprintable() or value != value.strip():
                    problems.append(Problem(f"line {line_no}", f"the {label} field is empty or not plain text"))
                    continue
                values[name] = value
            rest, rest_line = bullets[len(FIELDS):], first_bullet + len(FIELDS) + 1
            if rest and rest[0].startswith(CHAIN_PREFIX):
                value = rest[0][len(CHAIN_PREFIX):]
                if _HEX.fullmatch(value):
                    chain = value
                else:
                    problems.append(Problem(f"line {rest_line}", "the Chain field is not 64 lowercase hex characters"))
                rest, rest_line = rest[1:], rest_line + 1
            if rest:
                problems.append(Problem(f"line {rest_line}", "unexpected text after the entry"))

        if len(problems) == found and when is not None and len(values) == len(FIELDS):
            text_lines = "".join(x + "\n" for x in lines[h:first_bullet + len(FIELDS)])
            entries.append(ParsedEntry(h + 1, Entry(when, **values), chain, text_lines))
    return entries, problems


# ------------------------------------------------------------- the hash chain


def chain_state(text: str, entries: list) -> ChainState:
    """Walk the chain from its start (the first entry with a Chain line, which must be a seal entry).

    The previous value of the first chained entry is the SHA-256 of the file before it: every line before the
    blank line that starts its block. Every later entry must have a Chain line that matches. The walk stops at
    the first broken entry, because every later value follows from it.
    """
    start = next((i for i, p in enumerate(entries) if p.chain is not None), None)
    if start is None:
        return ChainState(False, ())
    first = entries[start]
    if first.entry.source != SEAL_SOURCE:
        return ChainState(True, (), Problem(f"entry {start + 1} (line {first.line})",
                                            "an entry before the start of the chain has a Chain line"))
    lines = text.split("\n")
    prev = sha256_hex("".join(x + "\n" for x in lines[:first.line - 2]).encode("utf-8"))
    values: list = []
    for i in range(start, len(entries)):
        p = entries[i]
        if p.chain is None:
            return ChainState(True, tuple(values), Problem(
                f"entry {i + 1} (line {p.line})", "the entry has no Chain line but comes after the start of the chain"))
        if p.chain != chain_value(prev, p.text):
            return ChainState(True, tuple(values), Problem(f"entry {i + 1} (line {p.line + 6})",
                                                           "the Chain value does not match"))
        values.append(p.chain)
        prev = p.chain
    return ChainState(True, tuple(values))


def _newest(cs: ChainState) -> str | None:
    """The previous value for the next entry: the newest Chain value, or None while the chain is not started."""
    if cs.broken is not None:
        raise UmwayiError(f"logbook: LOGBOOK.md: the hash chain is broken at {cs.broken.where}. "
                          "Check it with 'umwayi logbook verify'. Nothing was written.")
    return cs.values[-1] if cs.started else None


def parse_anchor(value: str) -> tuple:
    """(count, value) from COUNT:HEX, or a usage error (exit 64)."""
    m = _ANCHOR.fullmatch(value) if isinstance(value, str) else None
    if not m:
        raise UsageError("logbook: an anchor is COUNT:HEX, the number of chained entries (from 1) and 64 lowercase "
                         "hex characters, as 'umwayi logbook anchor' prints it")
    return int(m.group(1)), m.group(2)


# -------------------------------------------------------- reading and state


def _read_logbook(root: Path) -> bytes | None:
    """The bytes of LOGBOOK.md, or None if there is none. Unreadable is an error."""
    path = Path(root) / LOGBOOK_NAME
    if path.is_symlink():
        raise UmwayiError("logbook: LOGBOOK.md must not be a symbolic link")
    if not path.exists():
        return None
    try:
        return path.read_bytes()
    except OSError:
        raise UmwayiError("logbook: LOGBOOK.md cannot be read") from None


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise UmwayiError("logbook: LOGBOOK.md is not valid UTF-8") from None


def record_path(root: Path) -> Path:
    return Path(root) / STATE_DIR / RECORD_NAME


def _record_state(root: Path, data: bytes | None) -> str:
    """One of: none, ok, unsealed, mismatch, logbook_missing, record_bad."""
    rec = record_path(root)
    if rec.is_symlink():
        return "record_bad"
    has_record = rec.exists()
    recorded = None
    if has_record:
        try:
            m = _RECORD.match(rec.read_bytes().decode("ascii"))
        except (OSError, UnicodeDecodeError):
            return "record_bad"
        if not m:
            return "record_bad"
        recorded = m.group(1)
    if data is None:
        return "logbook_missing" if has_record else "none"
    if data == b"" and not has_record:
        return "none"  # an empty file holds nothing to protect
    if not has_record:
        return "unsealed"
    return "ok" if sha256_hex(data) == recorded else "mismatch"


_STATE_MESSAGES = {
    "unsealed": (
        "LOGBOOK.md has no hash record (.umwayi/logbook.sha256). Check it with 'umwayi logbook verify', "
        "then record it with 'umwayi logbook seal --by NAME'. Nothing was written."
    ),
    "mismatch": (
        "LOGBOOK.md does not match its recorded hash: it was changed since the last umwayi write. "
        "Check it with 'umwayi logbook verify'. Nothing was written."
    ),
    "logbook_missing": (
        "LOGBOOK.md is missing but its hash record exists, so the logbook may have been deleted. Nothing was written."
    ),
    "record_bad": (
        "the hash record .umwayi/logbook.sha256 is malformed or not a normal file. Nothing was written."
    ),
}


def pending_path(root: Path) -> Path:
    return Path(root) / STATE_DIR / PENDING_NAME


def lock_path(root: Path) -> Path:
    return Path(root) / STATE_DIR / LOCK_NAME


def _record_value(root: Path) -> str:
    """The record as one word: 64 hex characters, "none" (no record) or "bad" (malformed or not a file)."""
    rec = record_path(root)
    if rec.is_symlink():
        return "bad"
    if not rec.exists():
        return "none"
    try:
        m = _RECORD.match(rec.read_bytes().decode("ascii"))
    except (OSError, UnicodeDecodeError):
        return "bad"
    return m.group(1) if m else "bad"


# ---------------------------------------------------------------- the intent


@dataclass(frozen=True)
class Intent:
    """What one write is about to do, recorded before it appends anything."""
    kind: str  # write, recover or seal
    pid: int
    start: str  # the writer's start time in clock ticks after boot, or "unknown"
    record: str  # the record when the write started: 64 hex, "none" or "bad"
    before: str  # SHA-256 of the whole file before the write
    before_len: int
    after: str  # SHA-256 of the whole file the write intends
    after_len: int
    entry: bytes  # exactly the bytes it appends

    def encode(self) -> bytes:
        head = (
            f"{INTENT_MAGIC}\nkind {self.kind}\nwriter {self.pid} {self.start}\nrecord {self.record}\n"
            f"before {self.before} {self.before_len}\nafter {self.after} {self.after_len}\nentry {len(self.entry)}\n"
        )
        return head.encode("ascii") + self.entry


def _number(word: str) -> int:
    if not (word.isascii() and word.isdigit()) or len(word) > 18:
        raise ValueError(word)
    return int(word)


def _parse_intent(raw: bytes) -> Intent | None:
    """The intent, or None when it is not exactly in the format umwayi writes."""
    parts = raw.split(b"\n", 7)
    if len(parts) != 8:
        return None
    try:
        head = [p.decode("ascii") for p in parts[:7]]
    except UnicodeDecodeError:
        return None

    def words(line: str, name: str, n: int) -> list:
        w = line.split(" ")
        if len(w) != n + 1 or w[0] != name:
            raise ValueError(line)
        return w[1:]

    try:
        if head[0] != INTENT_MAGIC:
            return None
        (kind,) = words(head[1], "kind", 1)
        pid, start = words(head[2], "writer", 2)
        (record,) = words(head[3], "record", 1)
        before, before_len = words(head[4], "before", 2)
        after, after_len = words(head[5], "after", 2)
        (entry_len,) = words(head[6], "entry", 1)
        pid_n, before_n, after_n, entry_n = (_number(pid), _number(before_len), _number(after_len),
                                             _number(entry_len))
    except ValueError:
        return None
    if kind not in INTENT_KINDS or not (start == "unknown" or (start.isascii() and start.isdigit())):
        return None
    if not (record in ("none", "bad") or _HEX.fullmatch(record)):
        return None
    if not (_HEX.fullmatch(before) and _HEX.fullmatch(after)):
        return None
    entry = parts[7]
    if len(entry) != entry_n or entry_n == 0 or entry_n > MAX_INTENT_ENTRY or after_n != before_n + entry_n:
        return None
    if kind == "write" and record != before and not (record == "none" and before_n == 0):
        return None  # an ordinary write starts from a file that matches its record
    return Intent(kind, pid_n, start, record, before, before_n, after, after_n, entry)


def _read_intent(root: Path) -> tuple[bool, Intent | None]:
    """(present, intent). present with None means the intent file is malformed, a link or not a file."""
    p = pending_path(root)
    if p.is_symlink():
        return True, None
    if not p.exists():
        return False, None
    if not p.is_file():
        return True, None
    try:
        raw = p.read_bytes()
    except OSError:
        return True, None
    return True, _parse_intent(raw)


def _classify(intent: Intent | None, data: bytes | None, record: str) -> str:
    """Where an interrupted write left the files.

    completed         the file is exactly what the intent intended, the record is the one it started from or the new one
    not_written       the file is exactly the state before, the record is the one it started from
    seal_not_written  as not_written, for an interrupted seal: nothing to finish, the logbook is as it was
    torn              the state before plus only the start of the intended bytes (a power cut during the append)
    bad_intent        the intent is malformed or does not add up
    tamper            anything else: never accepted automatically
    """
    if intent is None:
        return "bad_intent"
    if data is None and intent.before_len != 0:
        return "tamper"  # the logbook is gone
    f = data or b""
    n, b = len(f), intent.before_len
    if n == intent.after_len and sha256_hex(f) == intent.after:
        if f[b:] != intent.entry or sha256_hex(f[:b]) != intent.before:
            return "bad_intent"
        return "completed" if record in (intent.record, intent.after) else "tamper"
    if n == b and sha256_hex(f) == intent.before:
        if sha256_hex(f + intent.entry) != intent.after:
            return "bad_intent"
        if record != intent.record:
            return "tamper"
        return "seal_not_written" if intent.kind == "seal" else "not_written"
    if b < n < intent.after_len and f[b:] == intent.entry[: n - b] and sha256_hex(f[:b]) == intent.before:
        return "torn" if record == intent.record else "tamper"
    return "tamper"


def _describe_writer(intent: Intent) -> str:
    if intent.start != "unknown":
        try:
            secs = int(intent.start) / os.sysconf("SC_CLK_TCK")
            return f"writer PID {intent.pid}, started {secs:.2f} s after boot"
        except (ValueError, OSError, AttributeError, ZeroDivisionError):
            pass
    return f"writer PID {intent.pid}, start time unknown"


def _writer() -> tuple[int, str]:
    """This process: its PID and its start time in clock ticks after boot (Linux), for messages only."""
    pid = os.getpid()
    try:
        stat = Path(f"/proc/{pid}/stat").read_bytes().decode("ascii", "replace")
        start = stat.rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return pid, "unknown"
    return pid, start if start.isascii() and start.isdigit() else "unknown"


_TORN = (
    "LOGBOOK.md ends with part of an entry that was being written when the write stopped (a power cut or a "
    "crash). Run 'umwayi logbook recover --torn-tail --by NAME' to cut it back to the last recorded entry. "
    "Nothing was written."
)
_BAD_INTENT = (
    "the intent of an interrupted write (.umwayi/logbook.pending) is malformed or not a normal file. "
    "Check the logbook with 'umwayi logbook verify', then seal it with 'umwayi logbook seal --by NAME'. "
    "Nothing was written."
)
_INTERRUPTED_TAMPER = (
    "LOGBOOK.md does not match its recorded hash: an interrupted write was found, but the files do not match "
    "what it intended. Check it with 'umwayi logbook verify'. Nothing was written."
)
_OUTSIDE = (
    "LOGBOOK.md changed while this entry was being written: something other than this umwayi write added or "
    "changed bytes. Nothing was recorded, and every write is refused until the owner checks it with "
    "'umwayi logbook verify' and seals it."
)
_INTENT_MESSAGES = {"torn": _TORN, "bad_intent": _BAD_INTENT, "tamper": _INTERRUPTED_TAMPER}


# ---------------------------------------------------------------- signals


@contextmanager
def _held_off():
    """SIGTERM, SIGHUP, SIGINT and SIGQUIT wait until the block ends, then each one that came is delivered once.

    The signals are blocked in this thread, and their Python handlers are swapped for a recorder for the same
    span, because in a process with more threads the kernel may deliver a signal to another thread and Python
    would then run the handler here, in the middle of the write. Only the main thread can swap handlers, so a
    write from any other thread is refused before anything is touched.
    """
    if threading.current_thread() is not threading.main_thread():
        raise UmwayiError("logbook: a logbook write must run in the main thread. Nothing was written.")
    received: list = []

    def recorder(signum, _frame):
        received.append(signum)

    old_mask = signal.pthread_sigmask(signal.SIG_BLOCK, _HELD_SIGNALS) if hasattr(signal, "pthread_sigmask") else None
    old: dict = {}
    try:
        for sig in _HELD_SIGNALS:
            old[sig] = signal.signal(sig, recorder)
        yield
    finally:
        for sig, handler in old.items():
            signal.signal(sig, handler if handler is not None else signal.SIG_DFL)
        if old_mask is not None:
            signal.pthread_sigmask(signal.SIG_SETMASK, old_mask)  # a signal still pending goes to its own handler now
        for sig in dict.fromkeys(received):
            signal.raise_signal(sig)


# ------------------------------------------------------------- one write
#
# Steps 3 to 6 of the design, each its own function so a test can hold a writer between any two of them.


def _write_intent(root: Path, raw: bytes) -> None:
    atomic_write(pending_path(root), raw)
    fsync_dir(Path(root) / STATE_DIR)


def _append_bytes(root: Path, payload: bytes, created: bool) -> None:
    path = Path(root) / LOGBOOK_NAME
    # append mode: every write goes to the end of the file, earlier bytes are never touched
    with open(path, "ab") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    if created:
        fsync_dir(Path(root))


def _record_hash(root: Path, expected: str) -> None:
    """Record the hash only if the whole file is exactly what this write intended."""
    try:
        now = sha256_hex((Path(root) / LOGBOOK_NAME).read_bytes())
    except OSError:
        now = None
    if now != expected:
        raise UmwayiError("logbook: " + _OUTSIDE)
    atomic_write(record_path(root), (expected + "\n").encode("ascii"))
    fsync_dir(Path(root) / STATE_DIR)


def _drop_intent(root: Path) -> None:
    try:
        os.unlink(pending_path(root))
    except FileNotFoundError:
        return
    fsync_dir(Path(root) / STATE_DIR)


def _write(root: Path, data: bytes | None, block: str, kind: str, record: str) -> str:
    """One write of one block on top of `data` (the file as checked by the caller). Returns the new hash.

    Called under the lock. The intent is written whole before the first byte is appended, and removed only
    after the record. Signals are held off for all of it.
    """
    new_file = not data
    payload = ((HEADER if new_file else "") + block).encode("utf-8")
    before = data or b""
    h = hashlib.sha256(before)
    h.update(payload)
    pid, start = _writer()
    intent = Intent(kind, pid, start, record, sha256_hex(before), len(before), h.hexdigest(),
                    len(before) + len(payload), payload)
    with _held_off():
        try:
            _write_intent(root, intent.encode())
        except OSError:
            try:
                _drop_intent(root)
            except OSError:
                pass
            raise UmwayiError("logbook: cannot write the intent .umwayi/logbook.pending. Nothing was written.") from None
        try:
            _append_bytes(root, payload, created=data is None)
        except OSError:
            if _unchanged(root, data):
                try:
                    _drop_intent(root)
                except OSError:
                    pass
                raise UmwayiError("logbook: cannot append to LOGBOOK.md. Nothing was written.") from None
            raise UmwayiError(
                "logbook: cannot append to LOGBOOK.md, and part of the entry may have been written. The next write "
                "checks the file against the intent .umwayi/logbook.pending."
            ) from None
        try:
            _record_hash(root, intent.after)
        except OSError:
            raise UmwayiError(
                "logbook: the entry was written but its hash could not be recorded. The next write finishes the "
                "record from the intent .umwayi/logbook.pending, or refuses if the files changed."
            ) from None
        try:
            _drop_intent(root)
        except OSError:
            raise UmwayiError(
                "logbook: the entry was written and recorded, but the intent .umwayi/logbook.pending could not be "
                "removed. The next write removes it."
            ) from None
    return intent.after


def _unchanged(root: Path, data: bytes | None) -> bool:
    try:
        now = _read_logbook(root)
    except UmwayiError:
        return False
    return (now or b"") == (data or b"")


# -------------------------------------------------------------------- lock


def _holder(fd: int) -> str:
    try:
        words = os.pread(fd, 64, 0).decode("ascii", "replace").split()
    except OSError:
        return "PID unknown"
    return f"PID {words[0]}" if words and words[0].isdigit() else "PID unknown"


@contextmanager
def _lock(root: Path):
    """fcntl.flock on .umwayi/logbook.lock for the whole block. The kernel lets go when the holder dies."""
    state_dir = Path(root) / STATE_DIR
    if state_dir.is_symlink() or (state_dir.exists() and not state_dir.is_dir()):
        raise UmwayiError("logbook: .umwayi must be a normal folder")
    if fcntl is None:
        raise UmwayiError("logbook: file locking is not available on this platform, so the logbook cannot be "
                          "written. Nothing was written.")
    try:
        state_dir.mkdir(exist_ok=True)
    except OSError:
        raise UmwayiError("logbook: cannot create the .umwayi folder") from None
    path = state_dir / LOCK_NAME
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    while True:
        try:
            fd = os.open(path, flags, 0o644)
        except OSError:
            raise UmwayiError("logbook: cannot open the lock file .umwayi/logbook.lock (is it a link or a "
                              "folder?). Nothing was written.") from None
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            who = _holder(fd)
            os.close(fd)
            if e.errno not in _BUSY:
                raise UmwayiError("logbook: the operating system refused the lock on .umwayi/logbook.lock. "
                                  "Nothing was written.") from None
            if time.monotonic() >= deadline:
                raise UmwayiError(
                    f"logbook: another umwayi command ({who}) holds the logbook lock (.umwayi/logbook.lock) and "
                    "is writing the logbook. Try again in a moment. Nothing was written."
                ) from None
            time.sleep(_LOCK_POLL_SECONDS)
            continue
        try:
            a, b = os.fstat(fd), os.stat(path, follow_symlinks=False)
            same = (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino)
        except OSError:
            same = False
        if not same:  # the file was replaced after we opened it: our lock guards nothing, try again
            os.close(fd)
            if time.monotonic() >= deadline:
                raise UmwayiError("logbook: the lock file .umwayi/logbook.lock keeps being replaced. "
                                  "Nothing was written.")
            continue
        break
    try:
        pid, start = _writer()
        try:
            os.pwrite(fd, f"{pid:>10} {start:>20}\n".encode("ascii"), 0)  # fixed width: names the holder in messages
        except OSError:
            pass
        yield
    finally:
        os.close(fd)  # lets go of the lock


# --------------------------------------------------------------- recovery


def _recovery_entry(when: str, state: str, intent: Intent) -> Entry:
    who = _describe_writer(intent)
    if state == "completed":
        added = f"Recovered an interrupted logbook write ({who}): the entry was written in full and its hash is now recorded"
        checked = ("the file matched the intent the writer recorded before it wrote; the earlier hash record matched "
                   "the intent; the format is valid and no date goes backwards; no writer held the logbook lock")
    else:
        added = f"Recovered an interrupted logbook write ({who}): the entry was never written and the intent was dropped"
        checked = ("the file matched the state before the write; the hash record matched the intent; the format is "
                   "valid and no date goes backwards; no writer held the logbook lock")
    return Entry(when, RECOVER_SOURCE, added, checked,
                 "The interrupted command did not finish; what it was doing was not redone.")


def _recover(root: Path, when: str) -> str | None:
    """Under the lock: finish or drop an interrupted write, with one entry. None when there is nothing to recover."""
    present, intent = _read_intent(root)
    if not present:
        return None
    data = _read_logbook(root)
    record = _record_value(root)
    state = _classify(intent, data, record)
    if state in _INTENT_MESSAGES:
        raise UmwayiError("logbook: " + _INTENT_MESSAGES[state])
    if state == "seal_not_written":  # the seal never happened: nothing to finish, the logbook is as it was
        with _held_off():
            _drop_intent(root)
        return state
    if intent.kind == "recover":
        # A recovery that was itself stopped: its entry is the recovery entry, so finish its own steps (the intent
        # file is already the right one) instead of logging the recovery a second time.
        with _held_off():
            if state == "not_written":
                _append_bytes(root, intent.entry, created=data is None)
            if record != intent.after:
                _record_hash(root, intent.after)
            _drop_intent(root)
        return state
    prev = None
    if data:
        text = _decode(data)
        entries, problems = parse(text)
        if problems:
            raise UmwayiError(
                f"logbook: an interrupted write was found, but LOGBOOK.md has {len(problems)} format problem(s). "
                "See 'umwayi logbook verify'. Nothing was written."
            )
        _check_not_backwards(entries, when)
        prev = _newest(chain_state(text, entries))  # a completed write is finished only on an intact chain
    _write(root, data, render(_recovery_entry(when, state, intent), prev), "recover", record)
    return state


# ------------------------------------------------------------------ append


def _check_before_write(root: Path, when: str) -> tuple:
    """The shared checks for append and check_writable: the hash record, the format, the date, then the hash
    chain. Returns (the current bytes, the previous Chain value for the next entry or None)."""
    data = _read_logbook(root)
    state = _record_state(root, data)
    if state not in ("ok", "none"):
        raise UmwayiError("logbook: " + _STATE_MESSAGES[state])
    prev = None
    if data:
        text = _decode(data)
        entries, problems = parse(text)
        if problems:
            raise UmwayiError(
                f"logbook: LOGBOOK.md has {len(problems)} format problem(s). "
                "See 'umwayi logbook verify'. Nothing was written."
            )
        _check_not_backwards(entries, when)
        prev = _newest(chain_state(text, entries))
    return data, prev


def _check_not_backwards(entries: list, when: str) -> None:
    if entries and when < entries[-1].entry.date:
        raise UmwayiError(
            f"logbook: the date {when} is before the date of the last entry ({entries[-1].entry.date}). "
            "Dates never go backwards. Nothing was written."
        )


def check_writable(root: Path, when: str) -> None:
    """Raise UmwayiError if an append dated `when` would be refused now. Adds no entry of its own.

    Runs the same checks as append (hash record, format, date order) under the same
    lock, so a write in progress is never mistaken for a hand-edited file. Like a
    write, it first recovers a write that was interrupted (one recovery entry), so a
    running agent is not stopped by something the next write would finish anyway.
    Used by `umwayi agent run` to stop an agent once the logbook can no longer record its checks.
    """
    with _lock(root):
        _recover(root, when)
        _check_before_write(root, when)


def append(root: Path, entry: Entry) -> None:
    """Append one entry. Checked: lock, interrupted writes, hash record, format, date order."""
    block = render(entry)
    with _lock(root):
        _recover(root, entry.date)
        data, prev = _check_before_write(root, entry.date)
        if prev is not None:
            block = render(entry, prev)  # chained: under the same lock and the same intent as every write
        _write(root, data, block, "write", _record_value(root))


# -------------------------------------------------------------------- seal


def _validate_by(when: str, by: str) -> str:
    if not real_date(when):
        raise UsageError("logbook: date must be a real date YYYY-MM-DD")
    by = by.strip() if isinstance(by, str) else ""
    if not by or len(by) > MAX_BY or not by.isprintable():
        raise UsageError(f"logbook: --by must be one short line of plain text (1 to {MAX_BY} characters)")
    return by


def seal(root: Path, when: str, by: str, start_chain: bool = False) -> SealResult:
    """Record the hash of the logbook as it is now and log that it was sealed.

    Only runs when asked. Refuses a logbook with format problems, and a
    logbook that is already sealed and intact, except with start_chain (`seal --chain`, allowed once): then
    the seal entry starts the hash chain. A seal of a logbook whose chain is not started always starts it; a
    broken chain is refused, because the chain is what proves the earlier entries. An interrupted write that can be
    recovered is recovered first; the intent of one that cannot is dropped by the
    seal, because the owner accepts the file as it is.
    """
    by = _validate_by(when, by)
    with _lock(root):
        present, intent = _read_intent(root)
        dropped = False
        if present:
            state = _classify(intent, _read_logbook(root), _record_value(root))
            if state == "torn":
                raise UmwayiError("logbook: " + _TORN)
            if state in ("completed", "not_written", "seal_not_written"):
                _recover(root, when)
            else:
                dropped = True
        data = _read_logbook(root)
        if not data:
            raise UmwayiError("logbook: there is no logbook to seal. Nothing was written.")
        text = _decode(data)
        entries, problems = parse(text)
        if problems:
            raise UmwayiError(
                f"logbook: LOGBOOK.md has {len(problems)} format problem(s) and cannot be sealed. "
                "See 'umwayi logbook verify', fix the file by hand, then seal. Nothing was written."
            )
        cs = chain_state(text, entries)
        if cs.broken is not None:
            raise UmwayiError(f"logbook: LOGBOOK.md: the hash chain is broken at {cs.broken.where}, and a seal cannot "
                              "accept a broken chain: the chain is what proves the earlier entries. Restore LOGBOOK.md "
                              "from a copy you trust (for example git). Nothing was written.")
        state = _record_state(root, data)
        if start_chain and cs.started:
            raise UmwayiError("logbook: the hash chain is already started; seal --chain is allowed once. "
                              "Nothing was written.")
        if state == "ok" and not dropped and not start_chain:
            raise UmwayiError("logbook: LOGBOOK.md is already sealed and intact, nothing to do."
                              + ("" if cs.started else " To start the hash chain, run umwayi logbook seal --chain "
                                                       "--by NAME."))
        _check_not_backwards(entries, when)
        before = {
            "ok": "matched the file",
            "unsealed": "was missing",
            "mismatch": "did not match the file (earlier lines may have been edited by hand)",
            "record_bad": "was malformed",
        }[state]
        if dropped:
            before += "; the intent of an interrupted write (.umwayi/logbook.pending) did not match the file and was dropped"
        old_hash = sha256_hex(data)
        starts = not cs.started  # the genesis: the previous value of the first chained entry is the file's hash
        what = "the hash chain was started" if state == "ok" and not dropped else "the logbook was sealed"
        entry = Entry(
            date=when,
            source=SEAL_SOURCE,
            added=(
                f"Seal by {by}: {what} with {len(entries)} earlier entries; "
                f"its SHA-256 before this entry was {old_hash}"
            ),
            checked=(
                "the format of every earlier entry is valid and no date goes backwards; "
                f"the earlier hash record {before}"
                + ("; this entry starts the hash chain" if starts else "; the hash chain is intact")
            ),
            not_done=(
                "The earlier entries were not rewritten or judged. Sealing records what the file holds now, "
                "it does not prove the file was never edited before."
            ),
        )
        digest = _write(root, data, render(entry, old_hash if starts else cs.values[-1]), "seal",
                        _record_value(root))
    return SealResult(len(entries), digest)


# ------------------------------------------------------------- torn tail


@dataclass(frozen=True)
class TornResult:
    cut: int  # bytes cut off
    logged: bool  # False when the interrupted write was a seal: the logbook still needs one


def _cut_torn_tail(root: Path, length: int) -> None:
    """The one place the tool removes bytes: back to `length`, which the caller proved is the recorded state."""
    path = Path(root) / LOGBOOK_NAME
    os.truncate(path, length)
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def recover_torn_tail(root: Path, when: str, by: str) -> TornResult:
    """`umwayi logbook recover --torn-tail --by NAME`: cut back the start of an entry that a power cut left behind.

    Only when an intent is present, the file holds exactly the state before it plus a strict prefix of the
    entry it intended, and the record is the one it started from. Then one entry says who cut how much.
    """
    by = _validate_by(when, by)
    with _lock(root):
        present, intent = _read_intent(root)
        if not present:
            raise UmwayiError("logbook: there is no interrupted write (.umwayi/logbook.pending), so there is no "
                              "torn tail to cut. Nothing was written.")
        data = _read_logbook(root)
        record = _record_value(root)
        state = _classify(intent, data, record)
        if state != "torn":
            why = {
                "completed": "the interrupted write is complete; the next write finishes it",
                "not_written": "the interrupted write never started appending; the next write drops it",
                "seal_not_written": "the interrupted seal never started appending; the next write drops it",
            }.get(state, "the files do not match what the interrupted write intended")
            raise UmwayiError(f"logbook: LOGBOOK.md does not end with a torn tail ({why}). Nothing was written.")
        cut = len(data) - intent.before_len
        entry = Entry(
            when, RECOVER_SOURCE,
            f"Recover by {by}: cut back a torn tail of {cut} bytes left by an interrupted logbook write "
            f"({_describe_writer(intent)})",
            f"the first {intent.before_len} bytes matched the hash before the write; the {cut} extra bytes were "
            "exactly the start of the entry the writer intended; the hash record matched the intent",
            "The cut bytes were part of an entry that was never finished and are not kept. The interrupted "
            "command did not finish.",
        )
        render(entry)  # a bad --by or date is refused before anything is cut
        with _held_off():  # the cut and its entry: no signal comes between them
            try:
                _cut_torn_tail(root, intent.before_len)
            except OSError:
                raise UmwayiError("logbook: the torn tail could not be cut. Run the command again.") from None
            if intent.kind == "seal":  # nothing can be logged: the record was never good. The owner seals again.
                _drop_intent(root)
                return TornResult(cut, False)
            data = _read_logbook(root)
            prev = None
            if data:
                text = _decode(data)
                entries, problems = parse(text)
                if problems:
                    raise UmwayiError(f"logbook: after the cut, LOGBOOK.md has {len(problems)} format problem(s). "
                                      "See 'umwayi logbook verify'.")
                _check_not_backwards(entries, when)
                prev = _newest(chain_state(text, entries))
            _write(root, data, render(entry, prev), "recover", record)
    return TornResult(cut, True)


# ------------------------------------------------------------- reading


def _view(root: Path) -> tuple[bytes | None, str | None, str | None]:
    """What a reader that takes no lock sees: (data, problem, info).

    problem is None when the logbook is consistent: intact, or one of the two exact states of an interrupted
    or running write. Otherwise a key of _STATE_MESSAGES or _INTENT_MESSAGES. A reader that catches a write
    half way reads again until two looks agree, for up to READ_SETTLE_SECONDS, so a running write is not
    mistaken for a hand edit.
    """
    deadline = time.monotonic() + READ_SETTLE_SECONDS
    last = None
    while True:
        present, intent = _read_intent(root)
        data = _read_logbook(root)
        record = _record_value(root)
        problem, info = _judge(root, present, intent, data, record)
        if problem is None:
            return data, None, info
        look = (present, intent, data, record)
        if look == last or time.monotonic() >= deadline:
            return data, problem, info
        last = look
        time.sleep(_LOCK_POLL_SECONDS)


def _judge(root, present, intent, data, record) -> tuple[str | None, str | None]:
    if present:
        state = _classify(intent, data, record)
        if state == "completed":
            return None, ("a logbook write is in progress or was interrupted; the file matches what it intended "
                          "(completed); the next write recovers it")
        if state == "not_written":
            return None, ("a logbook write is in progress or was interrupted; the file matches the state before it "
                          "(not written); the next write recovers it")
        if state != "seal_not_written":
            return state, None
        info = "an interrupted seal was found; it was never written, so the logbook is as it was before the seal"
    else:
        info = None
    state = _record_state(root, data)
    return (None if state in ("ok", "none") else state), info


# ------------------------------------------------------------------ verify


def verify(root: Path, anchor: tuple | None = None) -> Report:
    """Check the format, the hash record, the hash chain, any interrupted write, and an anchor (COUNT, HEX) if
    given. Reads only, changes nothing."""
    return _verify(root, anchor)[0]


def _verify(root: Path, anchor: tuple | None = None) -> tuple:
    try:
        data, problem, info = _view(root)
    except UmwayiError as e:
        return Report(0, [Problem("file", str(e).removeprefix("logbook: "))]), ChainState(False, ())
    entries: list = []
    problems: list[Problem] = []
    notes = [info] if info else []
    chain_note = ""
    cs = ChainState(False, ())
    if data is None:
        problems.append(Problem("file", "LOGBOOK.md was not found"))
    else:
        try:
            text = _decode(data)
            entries, found = parse(text)
            problems.extend(found)
            cs = chain_state(text, entries)
        except UmwayiError as e:
            problems.append(Problem("file", str(e).removeprefix("logbook: ")))
    if cs.broken is not None:
        problems.append(cs.broken)
    elif cs.started:
        chain_note = f"the hash chain is intact: {len(cs.values)} chained entries"
    elif data is not None:
        chain_note = "the hash chain is not started (umwayi logbook seal --chain --by NAME starts it)"
    if anchor is not None:
        count, value = anchor
        if len(cs.values) < count:
            problems.append(Problem("anchor", f"the chain is shorter than the anchor ({len(cs.values)} of {count} "
                                              "chained entries)"))
        elif cs.values[count - 1] != value:
            problems.append(Problem("anchor", f"the chain differs from the anchor at chained entry {count}"))
    record_problems = {
        "unsealed": "there is no hash record, run 'umwayi logbook seal --by NAME' after checking the file",
        "mismatch": "the file does not match its recorded hash, it was changed since the last umwayi write",
        "logbook_missing": "a hash record exists but the logbook is missing, it may have been deleted",
        "record_bad": "the hash record is malformed or not a normal file",
        "tamper": "an interrupted write was found, but the file does not match what it intended",
        "bad_intent": "the intent of an interrupted write (.umwayi/logbook.pending) is malformed or not a normal file",
    }
    if problem == "torn":
        problems.append(Problem("file", "LOGBOOK.md ends with part of an entry that was being written when the write "
                                        "stopped; 'umwayi logbook recover --torn-tail --by NAME' cuts it back"))
    elif problem in record_problems:
        problems.append(Problem("record", record_problems[problem]))
    return Report(len(entries), problems, notes, chain_note), cs


def anchor(root: Path) -> tuple:
    """`umwayi logbook anchor`: (count, newest Chain value) of a logbook that verifies. Writes nothing."""
    report, cs = _verify(root)
    if report.problems:
        raise UmwayiError(f"logbook: LOGBOOK.md does not verify ({len(report.problems)} problem(s)), so it is never "
                          "anchored. Check it with 'umwayi logbook verify'. No anchor was printed.")
    if not cs.started:
        raise UmwayiError("logbook: the hash chain is not started, so there is nothing to anchor. Start it with "
                          "'umwayi logbook seal --chain --by NAME'. No anchor was printed.")
    return len(cs.values), cs.values[-1]


# ------------------------------------------------------------ checked read


def read_checked(root: Path) -> list:
    """All entries of an intact logbook, oldest first. Reads only, takes no lock.

    No logbook gives an empty list. A logbook that fails the tamper check or
    has format problems is an error, so callers can refuse before they act.
    A write that is running, or was interrupted in one of the two exact states
    the next write recovers, reads as the file it left.
    """
    data, problem, _info = _view(root)
    if problem is not None:
        raise UmwayiError("logbook: " + (_STATE_MESSAGES.get(problem) or _INTENT_MESSAGES[problem]))
    if not data:
        return []
    text = _decode(data)
    entries, problems = parse(text)
    if problems:
        raise UmwayiError(
            f"logbook: LOGBOOK.md has {len(problems)} format problem(s). See 'umwayi logbook verify'."
        )
    cs = chain_state(text, entries)
    if cs.broken is not None:
        raise UmwayiError(f"logbook: LOGBOOK.md: the hash chain is broken at {cs.broken.where}. "
                          "See 'umwayi logbook verify'.")
    return [p.entry for p in entries]


# --------------------------------------------------------------- id reader


def logged_ids(root: Path, prefix: str = "Q") -> set[int]:
    """Numbers of the ids with this prefix (Q-0001 is 1, A-0001 is 1) named in logbook entries.

    A missing LOGBOOK.md means no ids. A logbook that exists but cannot be
    read is an error, never an empty answer. Only the id at the very start of
    an "Added" line counts, so a title that merely contains "Q-9999" is ignored.
    This reads leniently on purpose: counting too many ids is safe.
    """
    if not re.fullmatch(r"[A-Z]", prefix):
        raise UmwayiError("logbook: id prefix must be one capital letter")
    pattern = re.compile(rf"^- Added: {prefix}-(\d{{4,}}) ", re.MULTILINE)
    data = _read_logbook(root)
    if data is None:
        return set()
    return {int(m.group(1)) for m in pattern.finditer(_decode(data))}
