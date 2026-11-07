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
