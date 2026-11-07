"""Layer 5: the logbook (LOGBOOK.md).

An append-only record of every change. This module is the one place that
writes it, and every layer uses the same checked `append`.

Rules:
  * The logbook file is only ever opened in append mode (to write) or read.
    Earlier bytes are never edited by this tool.
  * Tamper check: after every write the SHA-256 of the whole file is recorded
    in .umwayi/logbook.sha256. Before every write it is recomputed. If it does
    not match, or the record is missing for an existing logbook, nothing is
    written. Only the explicit `seal` command records a hash for an unrecorded
    or hand-edited logbook. Nothing is sealed automatically.
  * Every entry must be well formed, and entry dates never go backwards.
  * A lock file (.umwayi/logbook.lock) stops two writers from interleaving.
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

import hashlib
import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date as _date
from pathlib import Path

from umwayi.errors import UmwayiError
from umwayi.fsutil import atomic_write

LOGBOOK_NAME = "LOGBOOK.md"
HEADER_LINE = "# Logbook"
HEADER = HEADER_LINE + "\n"
STATE_DIR = ".umwayi"
RECORD_NAME = "logbook.sha256"
LOCK_NAME = "logbook.lock"
LOCK_WAIT_SECONDS = 3.0  # how long an append waits for another writer
_LOCK_POLL_SECONDS = 0.02

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HEADING = re.compile(r"^## (\d{4}-\d{2}-\d{2})$")
_RECORD = re.compile(r"^([0-9a-f]{64})\n?$")
FIELDS = (("Source", "source"), ("Added", "added"), ("Checked", "checked"), ("Not done", "not_done"))
MAX_BY = 100


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


def render(entry: Entry) -> str:
    """The text of one entry, starting with a blank line."""
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
    return "".join(lines)


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
            if len(bullets) > len(FIELDS):
                problems.append(Problem(f"line {first_bullet + len(FIELDS) + 1}", "unexpected text after the entry"))

        if len(problems) == found and when is not None and len(values) == len(FIELDS):
            entries.append(ParsedEntry(h + 1, Entry(when, **values)))
    return entries, problems


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


def _write_and_record(root: Path, existing: bytes | None, block: str) -> str:
    """Append the block, then record the hash of the whole file. Returns the hash."""
    path = Path(root) / LOGBOOK_NAME
    new_file = not existing
    payload = ((HEADER if new_file else "") + block).encode("utf-8")
    try:
        # append mode: every write goes to the end of the file, earlier bytes are never touched
        with open(path, "ab") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        raise UmwayiError("logbook: cannot append to LOGBOOK.md") from None
    try:
        digest = sha256_hex(path.read_bytes())
        atomic_write(record_path(root), (digest + "\n").encode("ascii"))
    except OSError:
        raise UmwayiError(
            "logbook: the entry was written but its hash could not be recorded, "
            "so the next write will be refused until 'umwayi logbook seal' is run"
        ) from None
    return digest


# -------------------------------------------------------------------- lock


@contextmanager
def _lock(root: Path):
    state_dir = Path(root) / STATE_DIR
    if state_dir.is_symlink() or (state_dir.exists() and not state_dir.is_dir()):
        raise UmwayiError("logbook: .umwayi must be a normal folder")
    try:
        state_dir.mkdir(exist_ok=True)
    except OSError:
        raise UmwayiError("logbook: cannot create the .umwayi folder") from None
    lock = state_dir / LOCK_NAME
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise UmwayiError(
                    "logbook: another umwayi command is writing the logbook (the lock file "
                    ".umwayi/logbook.lock exists). Try again in a moment. If no other umwayi command is "
                    "running, delete that file. Nothing was written."
                ) from None
            time.sleep(_LOCK_POLL_SECONDS)
        except OSError:
            raise UmwayiError("logbook: cannot create the lock file .umwayi/logbook.lock") from None
    try:
        os.write(fd, f"{os.getpid()}\n".encode("ascii"))
    finally:
        os.close(fd)
    try:
        yield
    finally:
        try:
            os.unlink(lock)
        except OSError:
            pass


# ------------------------------------------------------------------ append


def _check_before_write(root: Path, when: str) -> bytes | None:
    """The shared checks for append and seal-less writes. Returns the current bytes."""
    data = _read_logbook(root)
    state = _record_state(root, data)
    if state not in ("ok", "none"):
        raise UmwayiError("logbook: " + _STATE_MESSAGES[state])
    if data:
        entries, problems = parse(_decode(data))
        if problems:
            raise UmwayiError(
                f"logbook: LOGBOOK.md has {len(problems)} format problem(s). "
                "See 'umwayi logbook verify'. Nothing was written."
            )
        _check_not_backwards(entries, when)
    return data


def _check_not_backwards(entries: list, when: str) -> None:
    if entries and when < entries[-1].entry.date:
        raise UmwayiError(
            f"logbook: the date {when} is before the date of the last entry ({entries[-1].entry.date}). "
            "Dates never go backwards. Nothing was written."
        )


def append(root: Path, entry: Entry) -> None:
    """Append one entry. Checked: lock, hash record, format, date order."""
    block = render(entry)
    with _lock(root):
        data = _check_before_write(root, entry.date)
        _write_and_record(root, data, block)


# -------------------------------------------------------------------- seal


def seal(root: Path, when: str, by: str) -> SealResult:
    """Record the hash of the logbook as it is now and log that it was sealed.

    Only runs when asked. Refuses a logbook with format problems, and a
    logbook that is already sealed and intact.
    """
    if not real_date(when):
        raise UmwayiError("logbook: date must be a real date YYYY-MM-DD")
    by = by.strip() if isinstance(by, str) else ""
    if not by or len(by) > MAX_BY or not by.isprintable():
        raise UmwayiError(f"logbook: --by must be one short line of plain text (1 to {MAX_BY} characters)")
    with _lock(root):
        data = _read_logbook(root)
        if not data:
            raise UmwayiError("logbook: there is no logbook to seal. Nothing was written.")
        entries, problems = parse(_decode(data))
        if problems:
            raise UmwayiError(
                f"logbook: LOGBOOK.md has {len(problems)} format problem(s) and cannot be sealed. "
                "See 'umwayi logbook verify', fix the file by hand, then seal. Nothing was written."
            )
        state = _record_state(root, data)
        if state == "ok":
            raise UmwayiError("logbook: LOGBOOK.md is already sealed and intact, nothing to do.")
        _check_not_backwards(entries, when)
        before = {
            "unsealed": "was missing",
            "mismatch": "did not match the file (earlier lines may have been edited by hand)",
            "record_bad": "was malformed",
        }[state]
        old_hash = sha256_hex(data)
        entry = Entry(
            date=when,
            source="umwayi logbook seal",
            added=(
                f"Seal by {by}: the logbook was sealed with {len(entries)} earlier entries; "
                f"its SHA-256 before this entry was {old_hash}"
            ),
            checked=(
                "the format of every earlier entry is valid and no date goes backwards; "
                f"the earlier hash record {before}"
            ),
            not_done=(
                "The earlier entries were not rewritten or judged. Sealing records what the file holds now, "
                "it does not prove the file was never edited before."
            ),
        )
        digest = _write_and_record(root, data, render(entry))
    return SealResult(len(entries), digest)


# ------------------------------------------------------------------ verify


def verify(root: Path) -> Report:
    """Check the format and the hash record. Reads only, changes nothing."""
    try:
        data = _read_logbook(root)
    except UmwayiError as e:
        return Report(0, [Problem("file", str(e).removeprefix("logbook: "))])
    entries: list = []
    problems: list[Problem] = []
    if data is None:
        problems.append(Problem("file", "LOGBOOK.md was not found"))
    else:
        try:
            entries, found = parse(_decode(data))
            problems.extend(found)
        except UmwayiError as e:
            problems.append(Problem("file", str(e).removeprefix("logbook: ")))
    state = _record_state(root, data)
    record_problems = {
        "unsealed": "there is no hash record, run 'umwayi logbook seal --by NAME' after checking the file",
        "mismatch": "the file does not match its recorded hash, it was changed since the last umwayi write",
        "logbook_missing": "a hash record exists but the logbook is missing, it may have been deleted",
        "record_bad": "the hash record is malformed or not a normal file",
    }
    if state in record_problems:
        problems.append(Problem("record", record_problems[state]))
    return Report(len(entries), problems)


# ------------------------------------------------------------ checked read


def read_checked(root: Path) -> list:
    """All entries of an intact logbook, oldest first. Reads only, takes no lock.

    No logbook gives an empty list. A logbook that fails the tamper check or
    has format problems is an error, so callers can refuse before they act.
    """
    data = _read_logbook(root)
    state = _record_state(root, data)
    if state not in ("ok", "none"):
        raise UmwayiError("logbook: " + _STATE_MESSAGES[state])
    if not data:
        return []
    entries, problems = parse(_decode(data))
    if problems:
        raise UmwayiError(
            f"logbook: LOGBOOK.md has {len(problems)} format problem(s). See 'umwayi logbook verify'."
        )
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
