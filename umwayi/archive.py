"""Layer 4: the archive.

`move` cuts an exact block of text out of a file, stores it in its own file
under archive/, adds a row to archive/INDEX.md and leaves one pointer line
behind. `verify` recomputes every SHA-256 fingerprint and compares it with
the index. Nothing here uses the network.

Safety rules:
  * Fail closed. Anything unexpected is an error and nothing is changed.
  * The three files (source, archive file, index) all change or none do. They
    are written copy first (archive file, index) and delete last (source). If
    any step fails, including the logbook write, the finished steps are undone.
  * `verify` only reads.
  * Error messages never contain file content.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

from umwayi import logbook
from umwayi.config import load_config
from umwayi.errors import UmwayiError
from umwayi.fsutil import atomic_write
from umwayi.memory import is_private
from umwayi.taskqueue import is_valid_date

ARCHIVE_DIR = "archive"
INDEX_NAME = "INDEX.md"
COLUMNS = ("id", "source", "moved", "reason", "words", "sha256")
MAX_REASON = 500
MAX_MARKER = 200

_ID = re.compile(r"^A-(\d{4,})$")
_ARCHIVE_FILE = re.compile(r"^(A-\d{4,})\.txt$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_WORDS = re.compile(r"^\d+$")
_SEP = re.compile(r"^:?-{3,}:?$")
_LINE_RE = re.compile(rb"[^\n]*\n|[^\n]+")

# Files the archive must never cut text out of: they have their own rules.
_PROTECTED_FILES = {"logbook.md", "queue.md", "rules.yaml", "umwayi.json"}
_PROTECTED_FOLDERS = {ARCHIVE_DIR, ".umwayi", ".git"}

TEMPLATE = (
    "# Archive index\n"
    "\n"
    "Blocks of text moved out of other files. Each row is one file in this folder.\n"
    "Do not edit by hand: 'umwayi archive verify' compares every file with its SHA-256 fingerprint.\n"
    "\n"
    "| " + " | ".join(COLUMNS) + " |\n"
    "| " + " | ".join("---" for _ in COLUMNS) + " |\n"
)

OK = "ok"
CHANGED = "changed"
MISSING = "missing"
NOT_IN_INDEX = "not in the index"


@dataclass(frozen=True)
class IndexRow:
    id: str
    source: str
    moved: str
    reason: str
    words: int
    sha256: str

    def cells(self) -> tuple[str, ...]:
        return (self.id, self.source, self.moved, self.reason, str(self.words), self.sha256)


@dataclass
class IndexDoc:
    lines: list[str]
    trailing_newline: bool
    rows: list[IndexRow]
    table_end: int  # index just after the last table line

    def text(self) -> str:
        return "\n".join(self.lines) + ("\n" if self.trailing_newline else "")


@dataclass(frozen=True)
class MoveResult:
    id: str
    source: str
    first_line: int  # 1-based, inclusive
    last_line: int
    words: int
    sha256: str
    archive_path: str  # root relative, forward slashes
    pointer: str


@dataclass(frozen=True)
class VerifyResult:
    id: str
    status: str
    path: str


# ---------------------------------------------------------- index parsing


def _cells(line: str, n: int) -> list[str]:
    s = line.rstrip()
    if len(s) < 2 or not s.startswith("|") or not s.endswith("|"):
        raise UmwayiError(f"archive index line {n}: table lines must start and end with |")
    return [c.strip() for c in s[1:-1].split("|")]


def parse_index(text: str) -> IndexDoc:
    if "\r" in text:
        raise UmwayiError("archive index: Windows line endings are not supported, use plain newlines")
    if "\x00" in text:
        raise UmwayiError("archive index: file contains a NUL character")
    trailing = text.endswith("\n")
    lines = text.split("\n")
    if trailing:
        lines.pop()

    blocks: list[tuple[int, int]] = []
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            blocks.append((i, j))
            i = j
        else:
            i += 1
    if not blocks:
        raise UmwayiError("archive index: no table found")
    if len(blocks) > 1:
        raise UmwayiError(f"archive index line {blocks[1][0] + 1}: only one table is allowed")
    start, end = blocks[0]
    if end - start < 2:
        raise UmwayiError(f"archive index line {start + 1}: the table needs a header and a separator line")

    header = [c.casefold() for c in _cells(lines[start], start + 1)]
    if header != list(COLUMNS):
        raise UmwayiError(f"archive index line {start + 1}: columns must be: {' | '.join(COLUMNS)}")
    sep = _cells(lines[start + 1], start + 2)
    if len(sep) != len(COLUMNS) or not all(_SEP.match(c) for c in sep):
        raise UmwayiError(f"archive index line {start + 2}: the separator line must look like | --- | --- |")

    rows: list[IndexRow] = []
    seen: set[str] = set()
    for k in range(start + 2, end):
        n = k + 1
        cells = _cells(lines[k], n)
        if len(cells) != len(COLUMNS):
            raise UmwayiError(f"archive index line {n}: expected {len(COLUMNS)} columns, found {len(cells)}")
        rid, source, moved, reason, words, sha = cells
        if not _ID.match(rid):
            raise UmwayiError(f"archive index line {n}: id must look like A-0001")
        if not source or source.startswith("/") or ".." in source.split("/"):
            raise UmwayiError(f"archive index line {n}: source must be a relative path")
        if not is_valid_date(moved):
            raise UmwayiError(f"archive index line {n}: moved must be a real date YYYY-MM-DD")
        if not reason:
            raise UmwayiError(f"archive index line {n}: reason must not be empty")
        if not _WORDS.match(words):
            raise UmwayiError(f"archive index line {n}: words must be a whole number")
        if not _SHA.match(sha):
            raise UmwayiError(f"archive index line {n}: sha256 must be 64 lowercase hex characters")
        if rid in seen:
            raise UmwayiError(f"archive index line {n}: duplicate id")
        seen.add(rid)
        rows.append(IndexRow(rid, source, moved, reason, int(words), sha))
    return IndexDoc(lines, trailing, rows, end)


def format_row(row: IndexRow) -> str:
    return "| " + " | ".join(row.cells()) + " |"


def _read_index(index_path: Path) -> str:
    if index_path.is_symlink():
        raise UmwayiError("archive: INDEX.md must not be a symbolic link")
    try:
        return index_path.read_bytes().decode("utf-8")
    except OSError:
        raise UmwayiError("archive: INDEX.md cannot be read") from None
    except UnicodeDecodeError:
        raise UmwayiError("archive: INDEX.md is not valid UTF-8") from None


# --------------------------------------------------------------- helpers


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _check_reason(reason: str) -> str:
    v = reason.strip() if isinstance(reason, str) else ""
    if not v:
        raise UmwayiError("reason must not be empty")
    if len(v) > MAX_REASON:
        raise UmwayiError(f"reason is longer than {MAX_REASON} characters")
    if not v.isprintable():
        raise UmwayiError("reason must be one line of plain text")
    if "|" in v:
        raise UmwayiError("reason must not contain the | character")
    return v


def _check_marker(value: str, what: str) -> str:
    v = value.strip() if isinstance(value, str) else ""
    if not v:
        raise UmwayiError(f"{what} marker must not be empty")
    if len(v) > MAX_MARKER or not v.isprintable():
        raise UmwayiError(f"{what} marker must be one short line of plain text")
    return v


def _resolve_source(root: Path, source: str) -> tuple[Path, str]:
    """Return (path, root relative posix path). Refuse anything unsafe."""
    if not isinstance(source, str) or not source.strip():
        raise UmwayiError("source file must be given")
    root_abs = Path(os.path.abspath(root))
    p = Path(source)
    if ".." in p.parts:
        raise UmwayiError("source path must not contain '..'")
    if p.is_absolute():
        try:
            rel = Path(os.path.normpath(p)).relative_to(root_abs)
        except ValueError:
            raise UmwayiError("source file must be inside the root") from None
    else:
        rel = Path(os.path.normpath(p))
    if not rel.parts or rel.is_absolute():
        raise UmwayiError("source file must be a file inside the root")
    rel_posix = rel.as_posix()
    if not rel_posix.isprintable():
        raise UmwayiError("source path must be plain text")
    if "|" in rel_posix:
        raise UmwayiError("source path must not contain the | character")
    cur = root_abs
    for part in rel.parts:
        cur = cur / part
        if cur.is_symlink():
            raise UmwayiError("source file must not be a symbolic link, or inside a linked folder")
    if not cur.exists():
        raise UmwayiError("source file was not found")
    if not cur.is_file():
        raise UmwayiError("source must be a regular file")
    return cur, rel_posix


def _check_not_protected(rel_posix: str) -> None:
    parts = rel_posix.casefold().split("/")
    if parts[0] in _PROTECTED_FOLDERS or (len(parts) == 1 and parts[0] in _PROTECTED_FILES):
        raise UmwayiError(
            "source is a protected file (the logbook, queue, rules, config, archive folder or git data)"
        )


def _split_lines(data: bytes) -> list[bytes]:
    """Lines including their '\\n'. A '\\r' stays part of the line."""
    return _LINE_RE.findall(data)


def _select_by_lines(n_lines: int, first: int, last: int) -> tuple[int, int]:
    if first > last:
        raise UmwayiError("the line range is empty (the start is after the end)")
    if first < 1 or last > n_lines:
        raise UmwayiError(f"the line range is outside the file (the file has {n_lines} lines)")
    return first - 1, last  # 0-based start, exclusive end


def _select_by_markers(lines: list[bytes], start: str, end: str) -> tuple[int, int]:
    start = _check_marker(start, "start")
    end = _check_marker(end, "end")
    if start == end:
        raise UmwayiError("the start and end markers must be different")
    texts = [l.decode("utf-8").strip() for l in lines]
    starts = [i for i, t in enumerate(texts) if t == start]
    ends = [i for i, t in enumerate(texts) if t == end]
    if not starts:
        raise UmwayiError("the start marker was not found as a whole line")
    if not ends:
        raise UmwayiError("the end marker was not found as a whole line")
    if len(starts) > 1:
        raise UmwayiError("the start marker appears more than once")
    if len(ends) > 1:
        raise UmwayiError("the end marker appears more than once")
    if ends[0] < starts[0]:
        raise UmwayiError("the end marker comes before the start marker")
    return starts[0], ends[0] + 1  # both marker lines are part of the block


def _next_id(index: IndexDoc, logged: set[int]) -> str:
    highest = max([int(_ID.match(r.id).group(1)) for r in index.rows] + list(logged), default=0)
    return f"A-{highest + 1:04d}"


# ------------------------------------------------------------------ move


def move(
    root: Path,
    source: str,
    reason: str,
    when: str,
    lines: tuple[int, int] | None = None,
    start: str | None = None,
    end: str | None = None,
) -> MoveResult:
    root = Path(root)
    if not is_valid_date(when):
        raise UmwayiError("date must be a real date in the form YYYY-MM-DD")
    reason = _check_reason(reason)
    by_markers = start is not None or end is not None
    if (lines is None) == (not by_markers) or (by_markers and (start is None or end is None)):
        raise UmwayiError("give either a line range, or both a start and an end marker")

    # --- the source file: refuse anything unsafe, before reading it
    config = load_config(root)  # no config means the private paths are unknown: refuse
    src_path, rel = _resolve_source(root, source)
    _check_not_protected(rel)
    if is_private(rel, config.private_paths):
        raise UmwayiError("source is a private path from umwayi.json")

    try:
        src_bytes = src_path.read_bytes()
    except OSError:
        raise UmwayiError("source file cannot be read") from None
    try:
        src_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise UmwayiError("source file is not valid UTF-8 text") from None

    src_lines = _split_lines(src_bytes)
    if by_markers:
        first, stop = _select_by_markers(src_lines, start, end)
    else:
        first, stop = _select_by_lines(len(src_lines), lines[0], lines[1])
    block_lines = src_lines[first:stop]
    block = b"".join(block_lines)
    words = len(block.decode("utf-8").split())
    if words == 0:
        raise UmwayiError("the block has no words, there is nothing to archive")
    fingerprint = sha256_hex(block)

    # --- the archive folder and the index
    arch_dir = root / ARCHIVE_DIR
    index_path = arch_dir / INDEX_NAME
    if arch_dir.is_symlink() or (arch_dir.exists() and not arch_dir.is_dir()):
        raise UmwayiError("archive must be a normal folder")
    dir_exists = arch_dir.is_dir()
    old_index_bytes: bytes | None = None
    if index_path.exists() or index_path.is_symlink():
        old_index_text = _read_index(index_path)
        old_index_bytes = old_index_text.encode("utf-8")
        index = parse_index(old_index_text)
        index_is_new = False
    else:
        index = parse_index(TEMPLATE)
        index_is_new = True

    # --- ids are never reused: look at the logbook too, refuse if it cannot be read
    try:
        logged = logbook.logged_ids(root, "A")
    except UmwayiError as e:
        raise UmwayiError(
            f"cannot move: {e}. The logbook is needed to make sure an id is never reused. Nothing was changed."
        ) from None
    aid = _next_id(index, logged)
    archive_rel = f"{ARCHIVE_DIR}/{aid}.txt"
    archive_file = arch_dir / f"{aid}.txt"
    if archive_file.exists() or archive_file.is_symlink():
        raise UmwayiError(f"{archive_rel} already exists but is not in the index, nothing was changed")

    # --- build every new file in memory and check it
    last = block_lines[-1]
    terminator = b"\r\n" if last.endswith(b"\r\n") else b"\n" if last.endswith(b"\n") else b""
    pointer = f"[archived {aid}: {archive_rel}]"
    new_src = b"".join(src_lines[:first]) + pointer.encode("utf-8") + terminator + b"".join(src_lines[stop:])

    new_row = IndexRow(aid, rel, when, reason, words, fingerprint)
    new_index_lines = index.lines[: index.table_end] + [format_row(new_row)] + index.lines[index.table_end :]
    trailing = True if index_is_new else index.trailing_newline or index.table_end == len(index.lines)
    new_index_text = IndexDoc(new_index_lines, trailing, [], 0).text()
    check = parse_index(new_index_text)
    if check.rows[-1] != new_row or check.rows[:-1] != index.rows:
        raise UmwayiError("internal check failed, nothing was changed")
    if check.lines[: index.table_end] + check.lines[index.table_end + 1 :] != index.lines:
        raise UmwayiError("internal check failed, nothing was changed")
    # the source must be the old source with exactly the block swapped for the pointer line
    if _split_lines(new_src) != src_lines[:first] + [pointer.encode("utf-8") + terminator] + src_lines[stop:]:
        raise UmwayiError("internal check failed, nothing was changed")
    if b"".join(src_lines[:first]) + block + b"".join(src_lines[stop:]) != src_bytes:
        raise UmwayiError("internal check failed, nothing was changed")

    entry = logbook.Entry(
        date=when,
        source="umwayi archive move",
        added=(
            f"{aid} moved from {rel} (lines {first + 1} to {stop}, {words} words, {len(block)} bytes) "
            f"to {archive_rel} with SHA-256 {fingerprint}; index row and one pointer line added"
        ),
        checked=(
            "source is a regular file inside the root, not a symbolic link, not private, not protected; "
            "block is non-empty valid UTF-8; "
            f"index parsed with no errors ({len(index.rows)} rows before); "
            f"{aid} is one more than the highest id in the index and the logbook; "
            "the archive file was read back and its SHA-256 matched"
        ),
        not_done=(
            "No text outside the block was changed. Nothing was deleted: the block is in the archive file. "
            "It was not restored anywhere (restore is not built yet)."
        ),
    )

    # --- write: copy first (archive file, index), delete last (source), then the logbook
    undo: list[tuple[str, object]] = []
    phase = "writing"
    try:
        if not dir_exists:
            arch_dir.mkdir()
            undo.append(("archive folder", lambda: _remove_dir_if_empty(arch_dir)))
        atomic_write(archive_file, block)
        undo.append(("archive file", lambda: os.unlink(archive_file)))
        if sha256_hex(archive_file.read_bytes()) != fingerprint:
            raise UmwayiError("the archive file did not read back correctly")

        atomic_write(index_path, new_index_text.encode("utf-8"))
        undo.append(("index", lambda: _restore(index_path, old_index_bytes)))

        if src_path.read_bytes() != src_bytes:
            raise UmwayiError("the source file changed while it was being moved")
        atomic_write(src_path, new_src)
        undo.append(("source file", lambda: _restore(src_path, src_bytes)))

        phase = "logbook"
        logbook.append(root, entry)
    except BaseException as exc:
        failed = []
        for name, fn in reversed(undo):
            try:
                fn()
            except Exception:
                failed.append(name)
        if failed:
            raise UmwayiError(
                "the move failed AND these could not be restored, check them by hand: " + ", ".join(failed)
            ) from None
        if not isinstance(exc, Exception):
            raise
        if phase == "logbook":
            reason = f": {exc}" if isinstance(exc, UmwayiError) else ""
            raise UmwayiError("the logbook write failed, so the move was undone" + reason) from None
        if isinstance(exc, UmwayiError):
            raise UmwayiError(f"{exc}; the move was undone") from None
        raise UmwayiError("a file could not be written, so the move was undone") from None

    return MoveResult(aid, rel, first + 1, stop, words, fingerprint, archive_rel, pointer)


def _restore(path: Path, old: bytes | None) -> None:
    if old is None:
        os.unlink(path)
    else:
        atomic_write(path, old)


def _remove_dir_if_empty(path: Path) -> None:
    try:
        os.rmdir(path)
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------- verify


def verify(root: Path) -> list[VerifyResult]:
    """Compare every archive file with the index. Reads only, changes nothing."""
    arch_dir = Path(root) / ARCHIVE_DIR
    if arch_dir.is_symlink() or not arch_dir.is_dir():
        raise UmwayiError("archive: there is no archive folder, so there is nothing to verify against")
    index_path = arch_dir / INDEX_NAME
    if not index_path.is_symlink() and not index_path.is_file():
        raise UmwayiError("archive: archive/INDEX.md was not found")
    index = parse_index(_read_index(index_path))

    results: list[VerifyResult] = []
    for row in index.rows:
        rel = f"{ARCHIVE_DIR}/{row.id}.txt"
        path = arch_dir / f"{row.id}.txt"
        if path.is_symlink():
            status = CHANGED
        elif not path.exists():
            status = MISSING
        elif not path.is_file():
            status = CHANGED
        else:
            try:
                status = OK if sha256_hex(path.read_bytes()) == row.sha256 else CHANGED
            except OSError:
                status = CHANGED
        results.append(VerifyResult(row.id, status, rel))

    known = {f"{r.id}.txt" for r in index.rows} | {INDEX_NAME}
    try:
        names = sorted(os.listdir(arch_dir))
    except OSError:
        raise UmwayiError("archive: the archive folder cannot be read") from None
    for name in names:
        if name in known:
            continue
        m = _ARCHIVE_FILE.match(name)
        results.append(VerifyResult(m.group(1) if m else name, NOT_IN_INDEX, f"{ARCHIVE_DIR}/{name}"))
    return results
