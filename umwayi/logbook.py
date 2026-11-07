"""Layer 5 (minimal): append-only logbook writer.

This is only the smallest part of layer 5 that layer 3 needs: append one
entry to LOGBOOK.md. The file is only ever opened in append mode, so
earlier lines are never edited. See tasks.md for what layer 5 still needs
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
