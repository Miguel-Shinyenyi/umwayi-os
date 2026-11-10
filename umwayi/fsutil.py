"""Small file helpers shared by layers that write files."""

from __future__ import annotations

import errno
import os
import shutil
import stat
import tempfile
from pathlib import Path


def _umask() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return mask


class NotRegular(OSError):
    """The path is not a regular file (a folder, a device such as /dev/zero, a FIFO)."""


class TooBig(OSError):
    """The file is larger than the reader allows."""


def read_regular(path: Path, limit: int) -> bytes:
    """The bytes of a regular file of at most `limit` bytes (S.2: a file that is /dev/zero, a FIFO or a folder, or
    a link to one, never hangs a reader or fills its memory). A link to a regular file is followed. Never blocks
    on open: O_NONBLOCK, which a regular file ignores."""
    fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise NotRegular(f"{path} is not a regular file")
        if st.st_size > limit:
            raise TooBig(f"{path} is larger than {limit} bytes")
        chunks, left = [], limit + 1
        while left > 0:
            chunk = os.read(fd, min(left, 1 << 16))
            if not chunk:
                break
            chunks.append(chunk)
            left -= len(chunk)
        data = b"".join(chunks)
        if len(data) > limit:
            raise TooBig(f"{path} is larger than {limit} bytes")
        return data
    finally:
        os.close(fd)


def atomic_write(path: Path, data: bytes, mode: int | None = None) -> None:
    """Write data to path through a temporary file in the same folder.

    Either the whole new content is in place or the old file is untouched.
    With mode, the file gets exactly that mode (a private file, S-Q9). Without
    it, an existing file keeps its permissions and a new file gets the normal
    permissions for the current umask (not the private mode of a temp file).
    """
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=".umwayi-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        elif path.exists():
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
