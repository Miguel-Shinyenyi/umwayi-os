"""One run at a time: the run lock, .umwayi/run.lock.

Every AI helper (steward, social), every job (`umwayi run`) and every workflow
(`umwayi workflow run`) holds this lock for its whole run, so two of them can
never write at the same time. The lock is fcntl.flock with LOCK_EX | LOCK_NB:

  * held by another run  -> RunLockBusy        (the caller answers Ask me first, exit 3)
  * not available here   -> RunLockUnavailable (fail closed: the caller answers Ask me first)

It never waits. The lock is released when the `with` block ends, on every exit
path, and the operating system releases it if the process dies. The file is
never deleted, because deleting a flock file lets two processes lock two
different files with the same name.

This is separate from .umwayi/logbook.lock, which only guards one logbook append.
"""

from __future__ import annotations

import errno
import os
from contextlib import contextmanager
from pathlib import Path

from umwayi.errors import UmwayiError

try:
    import fcntl
except ImportError:  # for example on Windows
    fcntl = None

STATE_DIR = ".umwayi"
LOCK_NAME = "run.lock"
LOCK_REL = f"{STATE_DIR}/{LOCK_NAME}"
_BUSY = {errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES}


class RunLockBusy(UmwayiError):
    """Another run holds the lock."""


class RunLockUnavailable(UmwayiError):
    """The lock cannot be taken here, so nothing may run."""


BUSY_REASON = (
    f"Another umwayi run (an AI helper, a job or a workflow) holds the run lock ({LOCK_REL}). "
    "Nothing was done. Try again when it has finished."
)


def unavailable_reason(e: Exception) -> str:
    return f"The run lock {LOCK_REL} could not be taken ({e}), so nothing runs."


@contextmanager
def held(root: Path, name: str = LOCK_NAME):
    """Hold the run lock for the whole block, or raise at once. `name` is another lock file of the same folder with the
    same rules (W6: .umwayi/serve.lock, one `umwayi serve` for a root); the default is the run lock."""
    if fcntl is None:
        raise RunLockUnavailable("file locking is not available on this platform")
    d = Path(root) / STATE_DIR
    if d.is_symlink() or (d.exists() and not d.is_dir()):
        raise RunLockUnavailable(f"{STATE_DIR} is not a normal folder")
    try:
        d.mkdir(exist_ok=True)
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(d / name, flags, 0o666)
    except OSError:
        raise RunLockUnavailable(f"{STATE_DIR}/{name} cannot be opened (is it a link or a folder?)") from None
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            if e.errno in _BUSY:
                raise RunLockBusy(BUSY_REASON) from None
            raise RunLockUnavailable("the operating system refused the lock") from None
        try:
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass  # closing the file below releases it too
    finally:
        os.close(fd)
