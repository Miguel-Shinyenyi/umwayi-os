"""Layer 3: the queue (queue.md).

queue.md is plain Markdown with exactly one table. A person can read and
edit it by hand. The parser is strict: anything unexpected is an error with
a line number (never the text of the line), and nothing is changed.

Only the row a command touches is rewritten. Every other byte of the file
stays as it was. Every change is written to the logbook; if that fails, the
queue.md change is rolled back.

Columns: id, kind, title, status, recommendation, answer, answered.
The old six column layout (no answer column) is refused everywhere except
`migrate`, which converts it once.

(The module is not called queue.py on purpose: that would shadow the
standard library `queue` when a file inside the package is run directly.)
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from umwayi import logbook
from umwayi.errors import UmwayiError

QUEUE_NAME = "queue.md"
COLUMNS = ("id", "kind", "title", "status", "recommendation", "answer", "answered")
LEGACY_COLUMNS = ("id", "kind", "title", "status", "recommendation", "answered")
KINDS = ("task", "decision")
STATUSES = ("open", "answered", "closed")
MAX_TITLE = 200
MAX_RECOMMENDATION = 500
MAX_ANSWER = MAX_RECOMMENDATION  # same limits as a recommendation
# Old answered rows have no answer text, but a new answered row must have one.
MIGRATED_ANSWER = "not recorded before migration"

LEGACY_MESSAGE = (
    "queue.md uses the old six column layout (no answer column). "
    "Run 'umwayi queue migrate' once to convert it. Nothing was changed."
)

_ID = re.compile(r"^Q-(\d{4,})$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SEP = re.compile(r"^:?-{3,}:?$")

HEADER_LINE = "| " + " | ".join(COLUMNS) + " |"
SEPARATOR_LINE = "| " + " | ".join("---" for _ in COLUMNS) + " |"

TEMPLATE = (
    "# Queue\n"
    "\n"
    "Tasks and decisions that wait for the owner. You can edit this file by hand.\n"
    "Kinds: task, decision. Statuses: open, answered, closed. Dates are YYYY-MM-DD.\n"
    "An open row has no answer. An answered row has an answer and the date answered.\n"
    "\n" + HEADER_LINE + "\n" + SEPARATOR_LINE + "\n"
)


@dataclass(frozen=True)
class Row:
    id: str
    kind: str
    title: str
    status: str
    recommendation: str
    answer: str  # "" while open
    answered: str  # "" or YYYY-MM-DD

    def cells(self) -> tuple[str, ...]:
        return (
            self.id, self.kind, self.title, self.status,
            self.recommendation, self.answer, self.answered,
        )


@dataclass
class Doc:
    lines: list[str]  # file lines, without "\n"
    trailing_newline: bool
    rows: list[Row]
    row_lines: list[int]  # index into lines for each row
    table_start: int  # index of the header line
    table_end: int  # index just after the last table line

    def text(self) -> str:
        return "\n".join(self.lines) + ("\n" if self.trailing_newline else "")


# ------------------------------------------------------------- validation


def is_valid_date(value: str) -> bool:
    if not isinstance(value, str) or not _DATE.match(value):
        return False
    try:
        date(int(value[:4]), int(value[5:7]), int(value[8:10]))
    except ValueError:
        return False
    return True


def _check_text(value: str, what: str, limit: int, required: bool) -> str:
    v = value.strip() if isinstance(value, str) else ""
    if required and not v:
        raise UmwayiError(f"{what} must not be empty")
    if len(v) > limit:
        raise UmwayiError(f"{what} is longer than {limit} characters")
    if not v.isprintable():
        raise UmwayiError(f"{what} must be one line of plain text")
    if "|" in v:
        raise UmwayiError(f"{what} must not contain the | character")
    return v


# ---------------------------------------------------------------- parsing


def _cells(line: str, n: int) -> list[str]:
    s = line.rstrip()
    if len(s) < 2 or not s.startswith("|") or not s.endswith("|"):
        raise UmwayiError(f"queue.md line {n}: table lines must start and end with |")
    return [c.strip() for c in s[1:-1].split("|")]


def _parse_row(cells: list[str], n: int, legacy: bool) -> Row:
    width = len(LEGACY_COLUMNS) if legacy else len(COLUMNS)
    if len(cells) != width:
        raise UmwayiError(f"queue.md line {n}: expected {width} columns, found {len(cells)}")
    if legacy:
        rid, kind, title, status, rec, answered = cells
        answer = ""
    else:
        rid, kind, title, status, rec, answer, answered = cells
    if not _ID.match(rid):
        raise UmwayiError(f"queue.md line {n}: id must look like Q-0001")
    if kind not in KINDS:
        raise UmwayiError(f"queue.md line {n}: kind must be one of: {', '.join(KINDS)}")
    if status not in STATUSES:
        raise UmwayiError(f"queue.md line {n}: status must be one of: {', '.join(STATUSES)}")
    if not title:
        raise UmwayiError(f"queue.md line {n}: title must not be empty")
    if answered and not is_valid_date(answered):
        raise UmwayiError(f"queue.md line {n}: answered must be empty or a real date YYYY-MM-DD")
    if status == "answered" and not answered:
        raise UmwayiError(f"queue.md line {n}: an answered row needs the date answered")
    if status == "open" and answered:
        raise UmwayiError(f"queue.md line {n}: an open row must not have a date answered")
    if not legacy:
        if status == "open" and answer:
            raise UmwayiError(f"queue.md line {n}: an open row must have an empty answer")
        if status == "answered" and not answer:
            raise UmwayiError(f"queue.md line {n}: an answered row needs an answer")
    return Row(rid, kind, title, status, rec, answer, answered)


def parse(text: str, legacy: bool = False) -> Doc:
    """Parse queue.md. With legacy=True, read the old six column layout instead."""
    if "\r" in text:
        raise UmwayiError("queue.md: Windows line endings are not supported, use plain newlines")
    if "\x00" in text:
        raise UmwayiError("queue.md: file contains a NUL character")
    trailing = text.endswith("\n")
    lines = text.split("\n")
    if trailing:
        lines.pop()

    # find table blocks: runs of lines that start with |
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
        raise UmwayiError("queue.md: no table found")
    if len(blocks) > 1:
        raise UmwayiError(f"queue.md line {blocks[1][0] + 1}: only one table is allowed")
    start, end = blocks[0]
    if end - start < 2:
        raise UmwayiError(f"queue.md line {start + 1}: the table needs a header and a separator line")

    header = [c.casefold() for c in _cells(lines[start], start + 1)]
    expected = LEGACY_COLUMNS if legacy else COLUMNS
    if header == list(LEGACY_COLUMNS) and not legacy:
        raise UmwayiError(LEGACY_MESSAGE)
    if header != list(expected):
        raise UmwayiError(f"queue.md line {start + 1}: columns must be: {' | '.join(expected)}")
    sep = _cells(lines[start + 1], start + 2)
    if len(sep) != len(expected) or not all(_SEP.match(c) for c in sep):
        raise UmwayiError(f"queue.md line {start + 2}: the separator line must look like | --- | --- |")

    rows: list[Row] = []
    row_lines: list[int] = []
    seen: set[str] = set()
    for k in range(start + 2, end):
        row = _parse_row(_cells(lines[k], k + 1), k + 1, legacy)
        if row.id in seen:
            raise UmwayiError(f"queue.md line {k + 1}: duplicate id")
        seen.add(row.id)
        rows.append(row)
        row_lines.append(k)
    return Doc(lines, trailing, rows, row_lines, start, end)


def format_row(row: Row) -> str:
    return "| " + " | ".join(row.cells()) + " |"


def _id_number(row_id: str) -> int:
    return int(_ID.match(row_id).group(1))


def next_id(doc: Doc, logged: set[int] = frozenset()) -> str:
    """One more than the highest id found in queue.md or in the logbook."""
    highest = max([_id_number(r.id) for r in doc.rows] + list(logged), default=0)
    return f"Q-{highest + 1:04d}"


# ---------------------------------------------------------------- file io


def _queue_path(root: Path) -> Path:
    return Path(root) / QUEUE_NAME


def _read(path: Path) -> str:
    if path.is_symlink():
        raise UmwayiError("queue.md must not be a symbolic link")
    if not path.is_file():
        raise UmwayiError("queue.md was not found in the root (umwayi queue add creates it)")
    try:
        return path.read_bytes().decode("utf-8")
    except OSError:
        raise UmwayiError("queue.md cannot be read") from None
    except UnicodeDecodeError:
        raise UmwayiError("queue.md is not valid UTF-8") from None


def _atomic_write(path: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".queue-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if path.exists():
            shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _commit(root: Path, path: Path, old_text: str | None, new_text: str, entry: logbook.Entry) -> None:
    """Write queue.md, then the logbook. If the logbook fails, undo the queue change."""
    try:
        _atomic_write(path, new_text.encode("utf-8"))
    except OSError:
        raise UmwayiError("queue.md cannot be written, nothing was changed") from None
    try:
        logbook.append(root, entry)
    except Exception as e:
        reason = f": {e}" if isinstance(e, UmwayiError) else ""
        try:
            if old_text is None:
                os.unlink(path)
            else:
                _atomic_write(path, old_text.encode("utf-8"))
        except Exception:
            raise UmwayiError(
                "the logbook write failed AND queue.md could not be restored: check queue.md by hand"
            ) from None
        raise UmwayiError("the logbook write failed, so the queue change was undone" + reason) from None


def _require_date(when: str) -> str:
    if not is_valid_date(when):
        raise UmwayiError("date must be a real date in the form YYYY-MM-DD")
    return when


def _check_id(row_id: str) -> str:
    if not isinstance(row_id, str) or not _ID.match(row_id):
        raise UmwayiError("id must look like Q-0001")
    return row_id


# --------------------------------------------------------------- commands


def list_rows(root: Path, status: str | None = None, kind: str | None = None) -> list[Row]:
    doc = parse(_read(_queue_path(root)))
    return [r for r in doc.rows if (status is None or r.status == status) and (kind is None or r.kind == kind)]


def add(root: Path, kind: str, title: str, recommendation: str, when: str) -> Row:
    when = _require_date(when)
    if kind not in KINDS:
        raise UmwayiError(f"kind must be one of: {', '.join(KINDS)}")
    title = _check_text(title, "title", MAX_TITLE, required=True)
    recommendation = _check_text(recommendation or "", "recommendation", MAX_RECOMMENDATION, required=False)

    path = _queue_path(root)
    if path.exists() or path.is_symlink():
        old_text: str | None = _read(path)
        doc = parse(old_text)
        created = False
    else:
        old_text = None
        doc = parse(TEMPLATE)
        created = True

    # Ids are never reused: look at the logbook too. If it cannot be read, refuse.
    try:
        logged = logbook.logged_ids(root)
    except UmwayiError as e:
        raise UmwayiError(
            f"cannot add: {e}. The logbook is needed to make sure an id is never reused. Nothing was changed."
        ) from None

    row = Row(next_id(doc, logged), kind, title, "open", recommendation, "", "")
    insert_at = doc.table_end
    new_lines = doc.lines[:insert_at] + [format_row(row)] + doc.lines[insert_at:]
    new_doc = Doc(new_lines, True if created else doc.trailing_newline or insert_at == len(doc.lines), [], [], 0, 0)
    new_text = new_doc.text()

    # safety net: the result must parse, hold the new row last, and keep every old line
    check = parse(new_text)
    if check.rows[-1] != row or check.rows[:-1] != doc.rows:
        raise UmwayiError("internal check failed, nothing was changed")
    if check.lines[:insert_at] + check.lines[insert_at + 1 :] != doc.lines:
        raise UmwayiError("internal check failed, nothing was changed")

    before = "queue.md did not exist, so it was created from the template" if created else (
        f"queue.md parsed with no errors ({len(doc.rows)} rows before)"
    )
    entry = logbook.Entry(
        date=when,
        source="umwayi queue add",
        added=f"{row.id} ({row.kind}) as open: {row.title}",
        checked=(
            f"{before}; {row.id} is one more than the highest id in queue.md and the logbook; "
            "text has no | character or line break"
        ),
        not_done="No other row was changed. Nothing was sent or published.",
    )
    _commit(root, path, old_text, new_text, entry)
    return row


def _transition(root: Path, row_id: str, new_status: str, when: str, command: str, answer_text: str = "") -> Row:
    when = _require_date(when)
    row_id = _check_id(row_id)
    if new_status == "answered":
        answer_text = _check_text(answer_text, "answer", MAX_ANSWER, required=True)
    path = _queue_path(root)
    old_text = _read(path)
    doc = parse(old_text)
    idx = next((i for i, r in enumerate(doc.rows) if r.id == row_id), None)
    if idx is None:
        raise UmwayiError(f"no row with id {row_id} in queue.md, nothing was changed")
    old = doc.rows[idx]
    if new_status == "answered":
        if old.status != "open":
            raise UmwayiError(f"{row_id} is {old.status}, only an open row can be answered")
        new = Row(old.id, old.kind, old.title, "answered", old.recommendation, answer_text, when)
        added = f"{row_id} marked answered on {when} (status open to answered, {len(answer_text)} characters of answer)"
        not_done = "No other row was changed. The answer text is stored in queue.md and not copied here."
    else:
        if old.status == "closed":
            raise UmwayiError(f"{row_id} is already closed")
        new = Row(old.id, old.kind, old.title, "closed", old.recommendation, old.answer, old.answered)
        added = f"{row_id} closed on {when} (status {old.status} to closed)"
        not_done = "No other row was changed. The answer and the date answered were left as they were."

    line_no = doc.row_lines[idx]
    new_lines = list(doc.lines)
    new_lines[line_no] = format_row(new)
    new_text = Doc(new_lines, doc.trailing_newline, [], [], 0, 0).text()

    # safety net: only the target row may differ
    check = parse(new_text)
    expected_rows = list(doc.rows)
    expected_rows[idx] = new
    if check.rows != expected_rows:
        raise UmwayiError("internal check failed, nothing was changed")
    if [l for i, l in enumerate(check.lines) if i != line_no] != [
        l for i, l in enumerate(doc.lines) if i != line_no
    ]:
        raise UmwayiError("internal check failed, nothing was changed")

    entry = logbook.Entry(
        date=when,
        source=f"umwayi queue {command}",
        added=added,
        checked=f"queue.md parsed with no errors ({len(doc.rows)} rows); {row_id} exists and was {old.status}",
        not_done=not_done,
    )
    _commit(root, path, old_text, new_text, entry)
    return new


def answer(root: Path, row_id: str, answer_text: str, when: str) -> Row:
    return _transition(root, row_id, "answered", when, "answer", answer_text)


def close(root: Path, row_id: str, when: str) -> Row:
    return _transition(root, row_id, "closed", when, "close")


def migrate(root: Path, when: str) -> int:
    """Convert the old six column layout to the current one. Returns the row count.

    Old open and closed rows get an empty answer. Old answered rows get the
    fixed text MIGRATED_ANSWER, because a current answered row must have an
    answer and the real text was never stored. Lines outside the table are
    not touched.
    """
    when = _require_date(when)
    path = _queue_path(root)
    old_text = _read(path)
    try:
        parse(old_text)  # the current layout?
    except UmwayiError as e:
        if str(e) != LEGACY_MESSAGE:
            raise
    else:
        raise UmwayiError("queue.md already has the current layout, nothing to migrate and nothing was changed")
    doc = parse(old_text, legacy=True)

    new_rows = [
        Row(r.id, r.kind, r.title, r.status, r.recommendation,
            MIGRATED_ANSWER if r.status == "answered" else "", r.answered)
        for r in doc.rows
    ]
    new_lines = list(doc.lines)
    new_lines[doc.table_start] = HEADER_LINE
    new_lines[doc.table_start + 1] = SEPARATOR_LINE
    for ln, row in zip(doc.row_lines, new_rows):
        new_lines[ln] = format_row(row)
    new_text = Doc(new_lines, doc.trailing_newline, [], [], 0, 0).text()

    # safety net: current layout, same rows plus the answer column, other lines untouched
    check = parse(new_text)
    if check.rows != new_rows:
        raise UmwayiError("internal check failed, nothing was changed")
    if check.lines[: doc.table_start] != doc.lines[: doc.table_start] or (
        check.lines[doc.table_end :] != doc.lines[doc.table_end :]
    ):
        raise UmwayiError("internal check failed, nothing was changed")
    for old_row, new_row in zip(doc.rows, check.rows):
        if (old_row.id, old_row.kind, old_row.title, old_row.status, old_row.recommendation, old_row.answered) != (
            new_row.id, new_row.kind, new_row.title, new_row.status, new_row.recommendation, new_row.answered,
        ):
            raise UmwayiError("internal check failed, nothing was changed")

    placeholders = sum(1 for r in new_rows if r.answer)
    entry = logbook.Entry(
        date=when,
        source="umwayi queue migrate",
        added=(
            f"answer column added to queue.md for {len(new_rows)} rows "
            f"({placeholders} answered rows got the text '{MIGRATED_ANSWER}', the others an empty answer)"
        ),
        checked="the old six column layout parsed with no errors; the result parsed in the current layout; "
        "no other column and no line outside the table changed",
        not_done="The real answers of old answered rows were not recovered. No row was added, answered or closed.",
    )
    _commit(root, path, old_text, new_text, entry)
    return len(new_rows)
