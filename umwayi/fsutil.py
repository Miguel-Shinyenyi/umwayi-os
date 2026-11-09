"""Small file helpers shared by layers that write files."""

from __future__ import annotations

import errno
import os
import shutil
import tempfile
from pathlib import Path


def _umask() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return mask


def atomic_write(path: Path, data: bytes) -> None:
    """Write data to path through a temporary file in the same folder.

    Either the whole new content is in place or the old file is untouched.
    An existing file keeps its permissions; a new file gets the normal
    permissions for the current umask (not the private mode of a temp file).
    """
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=".umwayi-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if path.exists():
            shutil.copymode(path, tmp)
        else:
            os.chmod(tmp, 0o666 & ~_umask())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def fsync_dir(path: Path) -> None:
    """Make a rename or removal in this folder durable (a power cut cannot undo it after this returns).

    A file system that cannot fsync a folder (EINVAL) is skipped: there is nothing more to do there.
    """
    fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        try:
            os.fsync(fd)
        except OSError as e:
            if e.errno not in (errno.EINVAL, getattr(errno, "ENOTSUP", errno.EINVAL)):
                raise
    finally:
        os.close(fd)
