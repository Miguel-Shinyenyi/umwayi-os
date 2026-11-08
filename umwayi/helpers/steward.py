"""Layer 7: Steward, the AI helper that reads the queue and proposes tasks.

`umwayi steward [--waiting-days N]` takes three steps, each checked by the
rules and logged by the helper base:

  1. read_queue    read queue.md (read only)
  2. read_logbook  read LOGBOOK.md (read only), to learn when each row was added
  3. write_draft   write one proposal, drafts/steward-NNNN.md

The proposal lists open items, items waiting longer than N days, answered
items not closed yet, and suggested next tasks as plain text. Steward never
edits the queue, never answers an item and never runs another command.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from umwayi import logbook, taskqueue
from umwayi.helpers.base import Helper, Outcome, Result, run as run_helper

DEFAULT_WAITING_DAYS = 7
MAX_WAITING_DAYS = 365
MAX_SUGGESTIONS = 20
_ADDED = re.compile(r"^(Q-\d{4,}) \((task|decision)\) as open: ")


@dataclass(frozen=True)
class Item:
    row: taskqueue.Row
    added: str | None  # date from the logbook, or None if it is not there
    days: int | None


def added_dates(entries: list) -> dict:
    """Queue id to the date of its 'umwayi queue add' logbook entry."""
    out: dict = {}
    for e in entries:
        if e.source == "umwayi queue add":
            m = _ADDED.match(e.added)
            if m and m.group(1) not in out:
                out[m.group(1)] = e.date
    return out


def _days(earlier: str, later: str) -> int:
    return max(0, date.fromisoformat(later).toordinal() - date.fromisoformat(earlier).toordinal())


def proposal(rows: list, entries: list, today: str, waiting_days: int) -> str:
    """The proposal text. Pure: reads nothing, writes nothing."""
    dates = added_dates(entries)
    items = [Item(r, dates.get(r.id), _days(dates[r.id], today) if r.id in dates else None) for r in rows]
    open_items = [i for i in items if i.row.status == "open"]
    late = sorted((i for i in open_items if i.days is not None and i.days > waiting_days),
                  key=lambda i: (-i.days, i.row.id))
    unknown = [i for i in open_items if i.days is None]
    answered = [i for i in items if i.row.status == "answered"]

    def since(i: Item) -> str:
        if i.days is None:
            return "added date not in the logbook"
        return f"open since {i.added} ({i.days} day{'s' if i.days != 1 else ''})"

    out = [
        "# Steward proposal (draft)",
        "",
        f"Date: {today}. Queue rows read: {len(rows)}. "
        f"Waiting longer than {waiting_days} day{'s' if waiting_days != 1 else ''} counts as late.",
        "",
        f"## Open items ({len(open_items)})",
        "",
    ]
    out += [f"- {i.row.id} {i.row.kind}, {since(i)}: {i.row.title}" for i in open_items] or ["None."]
    out += ["", f"## Waiting longer than {waiting_days} days ({len(late)})", ""]
    out += [f"- {i.row.id} {i.row.kind}, {i.days} days: {i.row.title}" for i in late] or ["None."]
    out += ["", f"## Answered but not closed ({len(answered)})", ""]
    out += [f"- {i.row.id} {i.row.kind}, answered {i.row.answered}: {i.row.title}" for i in answered] or ["None."]

    suggestions = []
    for i in late:
        if i.row.kind == "decision":
            rec = f" Recommendation: {i.row.recommendation}" if i.row.recommendation else ""
            suggestions.append(f"Answer {i.row.id} (decision, waiting {i.days} days): {i.row.title}.{rec}")
        else:
            suggestions.append(f"Do or close {i.row.id} (task, open {i.days} days): {i.row.title}.")
    for i in answered:
        suggestions.append(f"Close {i.row.id}: it was answered on {i.row.answered}.")
    for i in open_items:
        if i.row.kind == "decision" and i not in late and i.days is not None:
            suggestions.append(f"Answer {i.row.id} when you can: {i.row.title}.")
    for i in unknown:
        suggestions.append(f"Check {i.row.id}: its added date is not in the logbook.")
    out += ["", "## Suggested next tasks", ""]
    if not suggestions:
        out.append("Nothing waits. The queue has no open or answered rows." if not open_items
                   else "Nothing is late. Keep working on the open tasks.")
    else:
        shown = suggestions[:MAX_SUGGESTIONS]
        out += [f"{k}. {s}" for k, s in enumerate(shown, 1)]
        if len(suggestions) > len(shown):
            out.append(f"And {len(suggestions) - len(shown)} more.")
    out += [
        "",
        "This is a draft from the AI helper Steward. It changed nothing in the queue and answered nothing. "
        "The owner decides what to do.",
    ]
    return "\n".join(out) + "\n"


def run(root: Path, today: str, waiting_days: int = DEFAULT_WAITING_DAYS) -> Result:
    root = Path(root)
    helper = Helper(root, "steward", today)

    def read_queue() -> Outcome:
        if not (root / taskqueue.QUEUE_NAME).exists() and not (root / taskqueue.QUEUE_NAME).is_symlink():
            return Outcome("queue.md does not exist yet, so 0 rows", "Nothing was changed.", value=[])
        rows = taskqueue.list_rows(root)
        return Outcome(f"read queue.md ({len(rows)} rows)", "queue.md was only read, nothing was changed.", value=rows)

    def read_logbook() -> Outcome:
        entries = logbook.read_checked(root)
        return Outcome(f"read LOGBOOK.md ({len(entries)} entries)", "LOGBOOK.md was only read.", value=entries)

    def body() -> list:
        rows = helper.step("read_queue", read_queue).value
        entries = helper.step("read_logbook", read_logbook).value
        text = proposal(rows, entries, today, waiting_days)
        d = helper.step("write_draft", lambda: helper.draft("steward", text, "a proposal from the queue")).value
        open_n = sum(1 for r in rows if r.status == "open")
        return [
            f"Wrote {d.rel}.",
            f"Queue rows read: {len(rows)}, open: {open_n}.",
            "It is a draft. Steward changed nothing in the queue and answered nothing.",
        ]

    return run_helper(helper, body)
