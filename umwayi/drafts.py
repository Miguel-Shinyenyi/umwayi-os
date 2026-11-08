"""Numbered draft files under drafts/, shared by layers 6 and 7.

A draft is created with O_CREAT | O_EXCL, so an existing file is never
overwritten. The number is one more than the highest PREFIX-NNNN.md already
in drafts/. If a name is taken meanwhile, the next number is tried.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from umwayi.errors import UmwayiError

DRAFTS_DIR = "drafts"
_PREFIX = re.compile(r"^[a-z][a-z0-9-]{0,40}$")


@dataclass(frozen=True)
class Draft:
    rel: str  # root relative path, for example drafts/report-0001.md
    made_folder: bool  # True if this call created drafts/


def _remove_folder(folder: Path, made_folder: bool) -> None:
    if made_folder:
        try:
            os.rmdir(folder)  # only if it is still empty
        except OSError:
            pass


def create(root: Path, prefix: str, text: str) -> Draft:
    """Write text to a new drafts/PREFIX-NNNN.md. Never overwrites."""
    if not isinstance(prefix, str) or not _PREFIX.match(prefix):
        raise UmwayiError("drafts: the draft name prefix must be lowercase letters, digits and '-'")
    folder = Path(root) / DRAFTS_DIR
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise UmwayiError("drafts must be a normal folder")
    made_folder = not folder.exists()
    try:
        folder.mkdir(exist_ok=True)
        names = os.listdir(folder)
    except OSError:
        raise UmwayiError("the drafts folder cannot be created or read") from None
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d{{4,}})\.md$")
    numbers = [int(m.group(1)) for m in map(pattern.match, names) if m]
    n = max(numbers, default=0) + 1
    data = text.encode("utf-8")
    for _ in range(100):
        name = f"{prefix}-{n:04d}.md"
        path = folder / name
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
        except FileExistsError:
            n += 1
            continue
        except OSError:
            _remove_folder(folder, made_folder)
            raise UmwayiError("the draft could not be created") from None
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
        except OSError:
            try:
                os.unlink(path)
            except OSError:
                pass
            _remove_folder(folder, made_folder)
            raise UmwayiError("the draft could not be written") from None
        return Draft(f"{DRAFTS_DIR}/{name}", made_folder)
    raise UmwayiError("could not find a free draft name")


def remove(root: Path, draft: Draft) -> None:
    """Undo create: remove the file, and drafts/ if that call made it."""
    os.unlink(Path(root) / draft.rel)
    _remove_folder(Path(root) / DRAFTS_DIR, draft.made_folder)
