"""Layer 5 (minimal): append-only logbook writer, plus a reader for queue ids.

This is only the smallest part of layer 5 that layer 3 needs: append one
entry to LOGBOOK.md, and read back which queue ids were ever used. The file
is only ever opened in append mode, so earlier lines are never edited. See tasks.md for what layer 5 still needs
(tamper check, reading entries back, wiring layers 2 and 4).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from umwayi.errors import UmwayiError

LOGBOOK_NAME = "LOGBOOK.md"
HEADER = "# Logbook\n"
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# entries put the id first in the "Added" line, before any user text


@dataclass(frozen=True)
class Entry:
    date: str  # YYYY-MM-DD
    source: str  # which command wrote this
    added: str  # what was added
    checked: str  # what was checked
    not_done: str  # what was not done


def render(entry: Entry) -> str:
    """The text of one entry, starting with a blank line."""
    if not _DATE.match(entry.date):
        raise UmwayiError("logbook: date must be YYYY-MM-DD")
    for name in ("source", "added", "checked", "not_done"):
        value = getattr(entry, name)
        if not isinstance(value, str) or not value.strip():
            raise UmwayiError(f"logbook: '{name}' must not be empty")
        if not value.isprintable():
            raise UmwayiError(f"logbook: '{name}' must be one line of plain text")
    return (
        f"\n## {entry.date}\n"
        f"\n"
        f"- Source: {entry.source}\n"
        f"- Added: {entry.added}\n"
        f"- Checked: {entry.checked}\n"
        f"- Not done: {entry.not_done}\n"
    )


def append(root: Path, entry: Entry) -> None:
    """Append one entry to <root>/LOGBOOK.md. Never edits earlier lines."""
    block = render(entry)
    path = Path(root) / LOGBOOK_NAME
    if path.is_symlink():
        raise UmwayiError("logbook: LOGBOOK.md must not be a symbolic link")
    try:
        # "a+b": every write goes to the end of the file, whatever the position.
        with open(path, "a+b") as f:
            size = f.seek(0, os.SEEK_END)
            prefix = b""
            if size == 0:
                prefix = HEADER.encode("utf-8")
            else:
                f.seek(size - 1)
                if f.read(1) != b"\n":
                    prefix = b"\n"  # finish the last line; nothing earlier is touched
            f.write(prefix + block.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        raise UmwayiError("logbook: cannot append to LOGBOOK.md") from None


def logged_ids(root: Path, prefix: str = "Q") -> set[int]:
    """Numbers of the ids with this prefix (Q-0001 is 1, A-0001 is 1) named in logbook entries.

    A missing LOGBOOK.md means no ids. A logbook that exists but cannot be
    read is an error, never an empty answer. Only the id at the very start of
    an "Added" line counts, so a title that merely contains "Q-9999" is ignored.
    """
    if not re.fullmatch(r"[A-Z]", prefix):
        raise UmwayiError("logbook: id prefix must be one capital letter")
    pattern = re.compile(rf"^- Added: {prefix}-(\d{{4,}}) ", re.MULTILINE)
    path = Path(root) / LOGBOOK_NAME
    if path.is_symlink():
        raise UmwayiError("logbook: LOGBOOK.md must not be a symbolic link")
    if not path.exists():
        return set()
    try:
        text = path.read_bytes().decode("utf-8")
    except OSError:
        raise UmwayiError("logbook: LOGBOOK.md cannot be read") from None
    except UnicodeDecodeError:
        raise UmwayiError("logbook: LOGBOOK.md is not valid UTF-8") from None
    return {int(m.group(1)) for m in pattern.finditer(text)}
