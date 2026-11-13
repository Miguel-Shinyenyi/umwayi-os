"""W19 part 3b: the model routing table and task log checker. `umwayi routing check PATH`.

Two records are kept in docs/, each one a markdown table. The header of the first table in the file says which kind
the file is.

The routing table (docs/model-routing.md) proposes model options. It never picks one: the owner always chooses the
model. Columns, in this order:

    | platform | model | strengths | task types | source | source date | review_by |

The task log (docs/task-log.md) is the record of how the work of building umwayi-os was done. Columns, in this order:

    | task | area | model chosen | outcome | review result | credits used | date |

This code checks that the file exists and is well formed. It never claims that the content is true: it does not read
the vendor page, and a strength that is wrong passes. It never suggests, ranks or picks a model.

Strict and fail closed: any problem is a failure, nothing is guessed or repaired, and a failure line names a row by
its line and a column by its name but never repeats text from the file (safety rule 2). Standard library only, no
network, no scheduling, nothing is written. It is a command the owner runs; no job, timer or workflow starts it.
Exit codes in the command line: 0 well formed, 2 any failure or error, 64 usage; never 1 or 3.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

from umwayi import fsutil

MAX_BYTES = 1_000_000
MAX_CELL = 600
MAX_REVIEW_DAYS = 45  # the longest wait between the day a source was read and the day it must be read again

ROUTING_COLUMNS = ("platform", "model", "strengths", "task types", "source", "source date", "review_by")
LOG_COLUMNS = ("task", "area", "model chosen", "outcome", "review result", "credits used", "date")

PLATFORMS = ("Kiro", "OpenCode")
VENDOR_HOSTS = {"Kiro": ("kiro.dev",), "OpenCode": ("opencode.ai", "docs.opencode.ai")}
TASK_TYPES = (
    "general", "hard-multistep", "routine-multistep", "scoped-coding", "bug-fix", "review", "docs", "refactor",
    "long-context", "agent-work", "high-volume", "budget", "multilingual", "structured-decision", "private-local",
)
OUTCOMES = ("merged", "closed not merged", "open")
REVIEWS = ("approved", "changes requested", "none recorded")

_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_SEPARATOR_CELL = re.compile(r":?-{3,}:?")
_URL = re.compile(r"https://([a-z0-9][a-z0-9.-]*)(/[A-Za-z0-9._~/%-]+)")
_AREA = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
_CREDITS = re.compile(r"(?:[0-9]{1,7}(?:\.[0-9]{1,2})?|unknown)")


def _cells(line: str) -> list[str] | None:
    s = line.strip()
    if len(s) < 2 or not s.startswith("|") or not s.endswith("|"):
        return None
    return [c.strip() for c in s[1:-1].split("|")]


def _date(text: str) -> datetime.date | None:
    if not _DATE.fullmatch(text):
        return None
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        return None


def _bad_cell(cell: str) -> bool:
    return len(cell) > MAX_CELL or any(ord(ch) < 32 or ord(ch) == 127 for ch in cell)


def _header_at(lines: list[str]) -> int | None:
    return next((i for i, ln in enumerate(lines) if ln.lstrip().startswith("|")), None)


def kind_of(text: str) -> str | None:
    """"routing table" or "task log" from the header of the first table, or None if it is neither."""
    lines = text.splitlines()
    at = _header_at(lines)
    header = _cells(lines[at]) if at is not None else None
    if header is not None and tuple(header) == ROUTING_COLUMNS:
        return "routing table"
    if header is not None and tuple(header) == LOG_COLUMNS:
        return "task log"
    return None


def table_rows(text: str) -> list[list[str]]:
    """The cells of each row of the first table, after its header and separator. Not checked: use check_text."""
    lines = text.splitlines()
    at = _header_at(lines)
    if at is None:
        return []
    rows = []
    for ln in lines[at + 2:]:
        cells = _cells(ln) if ln.strip().startswith("|") else None
        if cells is not None:
            rows.append(cells)
    return rows


def _common_cells(at: str, columns: tuple[str, ...], cells: list[str]) -> list[str]:
    return [f"{at}: the {name} is too long or holds a control character"
            for name, cell in zip(columns, cells) if _bad_cell(cell)]


def _routing_row(at: str, cells: list[str], today: datetime.date) -> list[str]:
    platform, model, strengths, types, source, sdate, review = cells
    out: list[str] = []
    if platform not in PLATFORMS:
        out.append(f"{at}: the platform must be Kiro or OpenCode")
    if not model:
        out.append(f"{at}: the model is empty")
    if not strengths:
        out.append(f"{at}: the strengths are empty")
    parts = [t.strip() for t in types.split(",")] if types else []
    if not parts or any(t not in TASK_TYPES for t in parts) or len(set(parts)) != len(parts):
        out.append(f"{at}: the task types must be a comma separated list, each from the fixed list, none twice")
    m = _URL.fullmatch(source)
    if m is None:
        out.append(f"{at}: the source must be an https page address with a host and a path, and nothing else")
    elif platform in PLATFORMS and m.group(1) not in VENDOR_HOSTS[platform]:
        out.append(f"{at}: the source must be a page of the vendor of the platform")
    read = _date(sdate)
    if read is None:
        out.append(f"{at}: the source date must be a real date written YYYY-MM-DD")
    elif read > today:
        out.append(f"{at}: the source date is in the future")
    due = _date(review)
    if due is None:
        out.append(f"{at}: the review_by must be a real date written YYYY-MM-DD")
    else:
        if read is not None and due <= read:
            out.append(f"{at}: the review_by must be after the source date")
        elif read is not None and (due - read).days > MAX_REVIEW_DAYS:
            out.append(f"{at}: the review_by must be within {MAX_REVIEW_DAYS} days of the source date")
        if due < today:
            out.append(f"{at}: the review_by is past, the source must be read again")
    return out


def _log_row(at: str, cells: list[str], today: datetime.date) -> list[str]:
    task, area, model, outcome, review, credits, date = cells
    out: list[str] = []
    if not task:
        out.append(f"{at}: the task is empty")
    if not _AREA.fullmatch(area):
        out.append(f"{at}: the area must be lowercase letters, digits and hyphens, at most 40 characters")
    if not model:
        out.append(f"{at}: the model chosen is empty (write unknown if it was not recorded)")
    if outcome not in OUTCOMES:
        out.append(f"{at}: the outcome must be merged, closed not merged or open")
    if review not in REVIEWS:
        out.append(f"{at}: the review result must be approved, changes requested or none recorded")
    if not _CREDITS.fullmatch(credits):
        out.append(f"{at}: the credits used must be unknown or a plain number with at most two decimals")
    day = _date(date)
    if day is None:
        out.append(f"{at}: the date must be a real date written YYYY-MM-DD")
    elif day > today:
        out.append(f"{at}: the date is in the future")
    return out


def check_text(text: str, today: datetime.date) -> list[str]:
    """The failures of a routing table or a task log, one line each, in a fixed order. An empty list means the file
    is well formed. `today` is the day used for "in the future" and "past"."""
    lines = text.splitlines()
    at = _header_at(lines)
    if at is None:
        return ["no table found: the file needs a routing table or a task log"]
    kind = kind_of(text)
    if kind is None:
        return [f"line {at + 1}: the table header is neither the routing table header nor the task log header"]
    columns = ROUTING_COLUMNS if kind == "routing table" else LOG_COLUMNS
    sep = _cells(lines[at + 1]) if at + 1 < len(lines) else None
    if sep is None or len(sep) != len(columns) or not all(_SEPARATOR_CELL.fullmatch(c) for c in sep):
        return [f"line {at + 2}: the header must be followed by a separator row such as | --- | --- |"]

    failures: list[str] = []
    seen: dict[tuple[str, ...], int] = {}
    rows = 0
    for i in range(at + 2, len(lines)):
        if not lines[i].strip().startswith("|"):
            continue
        rows += 1
        where = f"line {i + 1}"
        cells = _cells(lines[i])
        if cells is None or len(cells) != len(columns):
            failures.append(f"{where}: the row must have exactly {len(columns)} columns")
            continue
        failures += _common_cells(where, columns, cells)
        if kind == "routing table":
            failures += _routing_row(where, cells, today)
            key = (cells[0], cells[1])
            label = "the model is listed twice for one platform"
        else:
            failures += _log_row(where, cells, today)
            key = (cells[0],)
            label = "the task is listed twice"
        if all(key):
            if key in seen:
                failures.append(f"{where}: duplicate: {label}, first on line {seen[key]}")
            else:
                seen[key] = i + 1
    if rows == 0:
        failures.append(f"the {kind} has no rows")
    return failures


def check_file(path: Path, today: datetime.date) -> list[str]:
    """Read the file at `path` (a regular file, UTF-8, at most MAX_BYTES) and check it."""
    try:
        data = fsutil.read_regular(Path(path), MAX_BYTES)
    except fsutil.TooBig:
        return [f"the file is larger than {MAX_BYTES} bytes"]
    except OSError:
        return ["the file cannot be read: it must be a regular file that exists"]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return ["the file is not valid UTF-8 text"]
    return check_text(text, today)
