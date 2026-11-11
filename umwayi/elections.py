"""Layer 13, slice 1: elections. `umwayi rules due` lists the rules that have a `review_by` date.

A Yes rule is in force through the whole of its `review_by` day; from the next day it counts as Ask me first (the
lapse itself is in rules.decide). This module only reads: it writes no file and no logbook entry, and it prints no
rule title, text or cause, only ids, dates, counts and fixed words. Standard library only.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from umwayi import rules
from umwayi.errors import UmwayiError

DEFAULT_WITHIN = 14
MAX_WITHIN = 3650
FAR_DAYS = 366  # a review_by further ahead than this is listed as `far`, and still counts as in force (13.R3.4)
CANNOT_LIST = "Ask me first: rules.yaml is missing or broken, so umwayi cannot list the rules."


def _days(n: int) -> str:
    return f"{n} day" + ("" if n == 1 else "s")


def due(root: Path, within: int = DEFAULT_WITHIN, when: str | None = None) -> tuple[int, list[str]]:
    """(exit code, output lines). 0 when no rule has lapsed, 3 when one has or the rules cannot be read.

    Lists, oldest first and then by id: the rules that lapsed, those due within `within` days, and every rule more
    than 366 days ahead as `far`. `when` is the --date option; the date used is the election clock (the latest of
    the system date, `when` and the newest logbook date).
    """
    try:
        loaded = rules.load_rules(Path(root) / "rules.yaml")
    except UmwayiError:  # the message is not printed: it could name a rule
        return 3, [CANNOT_LIST]
    today = date.fromisoformat(rules.election_clock(root, when))
    rows = []  # (word, review_by, rule id, text of the days)
    for r in sorted((r for r in loaded if r.review_by), key=lambda r: (r.review_by, r.id)):
        delta = (date.fromisoformat(r.review_by) - today).days
        if delta < 0:
            rows.append(("lapsed", r.review_by, r.id, f"{_days(-delta)} ago"))
        elif delta > FAR_DAYS:
            rows.append(("far", r.review_by, r.id, f"in {_days(delta)}"))
        elif delta <= within:
            rows.append(("due", r.review_by, r.id, f"in {_days(delta)}"))
    width = max((len(row[2]) for row in rows), default=0)
    lines = [f"{word:<6}  {day}  {rid:<{width}}  {text}" for word, day, rid, text in rows]
    lines.append(f"Yes rules without review_by: {sum(1 for r in loaded if r.verdict == rules.YES and not r.review_by)}")
    return (3 if any(row[0] == "lapsed" for row in rows) else 0), lines
