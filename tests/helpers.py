"""Shared helpers for tests."""

from pathlib import Path

from umwayi import logbook


def write_sealed_logbook(root, text):
    """Write a logbook by hand and record its hash, as if umwayi had written it."""
    root = Path(root)
    data = text.encode("utf-8")
    (root / "LOGBOOK.md").write_bytes(data)
    (root / ".umwayi").mkdir(exist_ok=True)
    logbook.record_path(root).write_text(logbook.sha256_hex(data) + "\n", encoding="ascii")


def entry_text(date="2026-01-01", source="hand", added="x", checked="y", not_done="z"):
    """One well formed entry (starting with a blank line), as the writer would produce."""
    return logbook.render(logbook.Entry(date, source, added, checked, not_done))


RUN_LOCK = ".umwayi/run.lock"


def without_run_lock(snapshot: dict) -> dict:
    """Drop the lock files from a file snapshot, and the .umwayi/ folder if only locks are in it.

    Both are flock files, created by the first locked run or logbook write and never deleted; they hold no
    data (the logbook lock holds the PID of its last holder, for messages): the run lock, and since the crash
    safety addendum (L5.1) the logbook lock.
    """
    out = {k: v for k, v in snapshot.items() if k not in (RUN_LOCK, ".umwayi/logbook.lock")}
    if ".umwayi/" in out and not any(k.startswith(".umwayi/") and k != ".umwayi/" for k in out):
        del out[".umwayi/"]
    return out


LOGBOOK_LOCK = ".umwayi/logbook.lock"


def without_logbook_lock(snapshot: dict) -> dict:
    """Drop the logbook lock file from a file snapshot.

    Since the crash safety addendum (L5.1) the lock is fcntl.flock on this file, which is created by the
    first write and never deleted. It holds only the PID of the last holder, for messages.
    """
    return {k: v for k, v in snapshot.items() if k != LOGBOOK_LOCK}


def hold_logbook_lock(root):
    """Hold the logbook lock from this process, as a running umwayi writer would. Returns a function that lets go.

    flock belongs to an open file, so a second open of the same file in this process cannot take it either.
    """
    import fcntl
    import os
    d = Path(root) / ".umwayi"
    d.mkdir(exist_ok=True)
    fd = os.open(d / "logbook.lock", os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.pwrite(fd, f"{4242:>10} {'unknown':>20}\n".encode("ascii"), 0)
    closed = []

    def release():
        if not closed:
            closed.append(True)
            os.close(fd)
    return release


def logbook_lock_held(root) -> bool:
    """True if some process holds the logbook lock now (a probe that takes and at once lets go)."""
    import errno
    import fcntl
    import os
    path = Path(root) / ".umwayi" / "logbook.lock"
    if not path.exists():
        return False
    fd = os.open(path, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as e:
        if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
            return True
        raise
    finally:
        os.close(fd)
    return False


def after_rules(entries: list) -> list:
    """The entries after the first one, which must be the `umwayi rules` entry (layer 13, L13.3: 13.R7.2, the
    first command that asks the rules in a root logs them first). Entries are Entry or ParsedEntry objects."""
    first = entries[0] if entries else None
    source = getattr(getattr(first, "entry", first), "source", None)
    assert source == "umwayi rules", f"the first entry is {source!r}, not the rules entry"
    return list(entries[1:])


def log_rules(root, when="2026-11-07"):
    """Log the rules of root/rules.yaml once (the baseline `umwayi rules` entry), as the first check in a root does.
    For tests that snapshot a root and expect a refusal to change nothing: their rules are then already logged."""
    from umwayi import rules
    logged, why = rules.log_rules_change("{}", Path(root) / "rules.yaml", Path(root), when)
    assert logged is not None and why is None, why
