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
    """Drop the run lock file from a file snapshot, and the .umwayi/ folder if only the lock is in it.

    The lock file is created by the first locked run and never deleted; it holds no data.
    """
    out = {k: v for k, v in snapshot.items() if k != RUN_LOCK}
    if ".umwayi/" in out and not any(k.startswith(".umwayi/") and k != ".umwayi/" for k in out):
        del out[".umwayi/"]
    return out
