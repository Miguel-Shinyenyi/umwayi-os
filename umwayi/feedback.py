"""W33: `umwayi feedback export`. A summary of the logbook that a tester can paste into a feedback issue.

    umwayi feedback export

It prints counts and dates and nothing else: the number of entries, the count of entries for each kind (the command that
wrote it, from a fixed list of names; any other source is counted as "other"), the count of the checks for each verdict
(Yes, No, Ask me first), the first and last date, whether the hash chain is intact, and the budget spent in UU.

It holds no path, no command text, no rule text, no file content and no text of any logbook entry. Every word it prints is
a fixed word of this file or a number or a date in the fixed form YYYY-MM-DD. It reads only: it writes no file and appends
no logbook entry. It uses the layer's own readers (logbook.verify for the tamper check and the chain, logbook.read_checked_chain
for the entries, budget.parse_ledger and budget.day_totals for the budget).

Fail closed: a logbook that does not pass its check (a hand edit, a broken chain, a format problem, an unreadable file) gives
exit 2 and no summary at all, and the message holds no text of the logbook.

Exit codes: 0 done, 2 the logbook failed its check or an unexpected error, 64 usage. Never 1 or 3.
Standard library only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from umwayi import budget, logbook, units
from umwayi.errors import UmwayiError

# The kinds that are named. A source that is not one of these is counted as "other", so a source that holds text of the
# owner (a name, a path) can never reach the output.
KINDS = (
    "umwayi agent run", "umwayi archive move", "umwayi autonomy", "umwayi autonomy record", "umwayi budget", "umwayi check",
    "umwayi decision reopen", "umwayi goal", "umwayi kill", "umwayi logbook recover", "umwayi logbook seal", "umwayi petition",
    "umwayi publish-draft", "umwayi queue add", "umwayi queue answer", "umwayi queue close", "umwayi queue migrate",
    "umwayi report", "umwayi rules", "umwayi run", "umwayi schedule", "umwayi serve", "umwayi view snapshot",
)
OTHER = "other"
CHECK_KIND = "umwayi check"
VERDICTS = ("Yes", "No", "Ask me first")
UNREADABLE = "unreadable"
# "<who> gave <verdict>" at the start of the Added line of a check. <who> is a rule id, "No rule" or the word of what
# stopped the check; it is never printed.
_GAVE = re.compile(r"^[^;]{1,120}? gave (Yes|No|Ask me first)(?: and autonomy moved it to Yes)?;")

REFUSED = ("feedback: the logbook did not pass its check, so no summary was made. Nothing was changed. "
           "Run 'umwayi logbook verify' yourself, and read what it says before you share it.")
NO_LOGBOOK = ("feedback: there is no logbook in this folder yet, so there is nothing to summarise. Nothing was changed. "
              "Run umwayi in the folder you used, or use --root.")
HEADER = "umwayi feedback export: counts and dates only; no paths, commands, rules or file contents."


@dataclass(frozen=True)
class Result:
    code: int
    lines: list


def kind_of(source: str) -> str:
    return source if source in KINDS else OTHER


def verdict_of(added: str) -> str:
    m = _GAVE.match(added)
    return m.group(1) if m else UNREADABLE


def _budget_uu(entries: list) -> int:
    led = budget.parse_ledger(entries)
    micros = 0
    for day in sorted({r.date for r in led.reserves.values()}):
        t = budget.day_totals(led, day)
        micros += t.used + t.reserved  # an open reservation counts in full
    return units.uu(micros)


def summary(entries: list, chain_length: int) -> list:
    """The lines of the summary, from entries that already passed the checked readers."""
    kinds = {}
    verdicts = {v: 0 for v in (*VERDICTS, UNREADABLE)}
    for e in entries:
        k = kind_of(e.source)
        kinds[k] = kinds.get(k, 0) + 1
        if e.source == CHECK_KIND:
            verdicts[verdict_of(e.added)] += 1
    lines = [HEADER, f"entries: {len(entries)}", "entries by kind:"]
    named = sorted(k for k in kinds if k != OTHER)
    lines += [f"  {k}: {kinds[k]}" for k in named]
    if OTHER in kinds:
        lines.append(f"  {OTHER}: {kinds[OTHER]}")
    if not kinds:
        lines.append("  none")
    lines.append(f"checks by verdict ({CHECK_KIND}):")
    lines += [f"  {v}: {n}" for v, n in verdicts.items()]
    dates = sorted(e.date for e in entries)
    lines.append(f"dates: first {dates[0]}, last {dates[-1]}" if dates else "dates: none")
    lines.append(f"chain: intact, {chain_length} entries in the chain" if chain_length else "chain: not started")
    lines.append(f"budget spent: {_budget_uu(entries)} UU (an open reservation counts in full)")
    return lines


def export(root) -> Result:
    root = Path(root)
    try:
        if not (root / "LOGBOOK.md").is_file():
            return Result(2, [NO_LOGBOOK])
        report = logbook.verify(root)
        if report.problems:
            return Result(2, [REFUSED])
        entries, chain_length = logbook.read_checked_chain(root)
        return Result(0, summary(entries, chain_length))
    except UmwayiError:
        return Result(2, [REFUSED])
