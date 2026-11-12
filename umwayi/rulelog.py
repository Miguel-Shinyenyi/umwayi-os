"""Layer 13, slice 3: the rules change log (13.R7).

Every check, and every other command that asks the rules, calls `ensure_logged` with the SHA-256 of the exact bytes of
rules.yaml it read and the rules it parsed, before it uses them. When the SHA-256 of the bytes is not the one of the newest
`umwayi rules` entry, one entry is written first:

    Added:    rules.yaml first logged (sha256 HEX); rules N
              rules.yaml changed (sha256 HEX); rules A to B; added ID, ID; removed ID; changed ID verdict no to yes
              rules.yaml changed (sha256 HEX); rules A to B; no rule changed
    Checked:  rules.yaml was read and parsed before this entry; this entry is written before the new rules are first
              used; state: ID VERDICT[ review_by DATE]; ...
    Not done: Only rule ids, verdicts, dates and counts are logged, not rule text. No action was checked by this entry.

It holds no rule title, text or cause. The reader matches all three lines against these shapes with `fullmatch`, so
an entry in another shape is not read. More than MAX_LISTED rules are counted, not listed, and the next change is a
new baseline. If the entry cannot be written, `ensure_logged` says why, and the caller turns every Yes into Ask me
first (a No stays a No). This module only reads rules.yaml through its caller and never writes it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from umwayi import logbook
from umwayi.errors import UmwayiError

SOURCE = "umwayi rules"
MAX_LISTED = 200
CHECKED_HEAD = ("rules.yaml was read and parsed before this entry; this entry is written before the new rules are "
                "first used; state: ")
NOT_DONE = "Only rule ids, verdicts, dates and counts are logged, not rule text. No action was checked by this entry."
NO_RULES = "no rules"
NOT_LISTED = "too many rules to list"
NO_CHANGE = "no rule changed"
NEW_BASELINE = "the earlier state was not listed, so this entry is a new baseline"
TOO_MANY_CHANGES = f"the rules are not listed (more than {MAX_LISTED})"

_WORDS = {"Yes": "yes", "No": "no", "Ask me first": "ask"}
_AUTO = r"[a-z][a-z0-9_-]{0,39} reversible (?:yes|no) cost \d{1,7}"  # layer 13, slice 5: the opt-in of a rule
_ITEM = rf"[a-z0-9][a-z0-9_-]* (?:yes|no|ask)(?: review_by \d{{4}}-\d{{2}}-\d{{2}})?(?: autonomy {_AUTO})?"
_FIRST = re.compile(r"rules\.yaml first logged \(sha256 ([0-9a-f]{64})\); rules (\d{1,9})")
_CHANGED = re.compile(r"rules\.yaml changed \(sha256 ([0-9a-f]{64})\); rules \d{1,9} to (\d{1,9}); "
                      r"[a-z0-9][a-z0-9 ,;_()-]*")
_CHECKED = re.compile(re.escape(CHECKED_HEAD) + rf"({re.escape(NO_RULES)}|{re.escape(NOT_LISTED)}|{_ITEM}(?:; {_ITEM})*)")
_ONE = re.compile(rf"([a-z0-9][a-z0-9_-]*) (yes|no|ask)(?: review_by (\d{{4}}-\d{{2}}-\d{{2}}))?(?: autonomy ({_AUTO}))?")


@dataclass(frozen=True)
class Logged:
    sha256: str
    count: int
    state: tuple | None  # ((id, verdict word, review_by or None, opt-in or None), ...), or None when not listed


def _read(entry) -> Logged | None:
    """The logged version an entry names, or None when it is not a rules entry in exactly the fixed shape."""
    if entry.source != SOURCE or entry.not_done != NOT_DONE:
        return None
    m = _FIRST.fullmatch(entry.added) or _CHANGED.fullmatch(entry.added)
    c = _CHECKED.fullmatch(entry.checked)
    if not m or not c:
        return None
    body = c.group(1)
    if body == NOT_LISTED:
        state = None
    elif body == NO_RULES:
        state = ()
    else:
        state = tuple((x.group(1), x.group(2), x.group(3), x.group(4)) for x in map(_ONE.fullmatch, body.split("; ")))
    return Logged(m.group(1), int(m.group(2)), state)


def newest(entries: list) -> Logged | None:
    """The newest rules entry in the fixed shape, or None when there is none."""
    for e in reversed(entries):
        found = _read(e)
        if found is not None:
            return found
    return None


def _opt_in(rule) -> str | None:
    a = getattr(rule, "autonomy", None)
    if a is None:
        return None
    return f"{a.cls} reversible {'yes' if a.reversible else 'no'} cost {a.cost_uu}"


def _state(rules: list) -> tuple:
    return tuple((r.id, _WORDS[r.verdict], r.review_by, _opt_in(r)) for r in rules)


def _state_text(state: tuple) -> str:
    if len(state) > MAX_LISTED:
        return NOT_LISTED
    if not state:
        return NO_RULES
    return "; ".join(f"{rid} {word}" + (f" review_by {day}" if day else "") + (f" autonomy {auto}" if auto else "")
                     for rid, word, day, auto in state)


def _changes(old: tuple, new: tuple) -> str:
    before = {rid: (word, day, auto) for rid, word, day, auto in old}
    after = {rid: (word, day, auto) for rid, word, day, auto in new}
    added = [rid for rid, _w, _d, _a in new if rid not in before]
    removed = [rid for rid, _w, _d, _a in old if rid not in after]
    changed = []
    for rid, word, day, auto in new:
        if rid not in before:
            continue
        old_word, old_day, old_auto = before[rid]
        if old_word != word:
            changed.append(f"{rid} verdict {old_word} to {word}")
        if old_day != day:
            changed.append(f"{rid} review_by {old_day or 'none'} to {day or 'none'}")
        if old_auto != auto:
            changed.append(f"{rid} autonomy {old_auto or 'none'} to {auto or 'none'}")
    parts = ([f"added {', '.join(added)}"] if added else []) + ([f"removed {', '.join(removed)}"] if removed else []) \
        + ([f"changed {', '.join(changed)}"] if changed else [])
    return "; ".join(parts) or NO_CHANGE


def entry(when: str, digest: str, rules: list, last: Logged | None) -> logbook.Entry:
    """The rules entry for these rules, compared with the last logged version (or the baseline when there is none)."""
    state = _state(rules)
    if last is None:
        added = f"rules.yaml first logged (sha256 {digest}); rules {len(state)}"
    else:
        head = f"rules.yaml changed (sha256 {digest}); rules {last.count} to {len(state)}; "
        if len(state) > MAX_LISTED:
            added = head + TOO_MANY_CHANGES
        elif last.state is None:
            added = head + NEW_BASELINE
        else:
            added = head + _changes(last.state, state)
    return logbook.Entry(when, SOURCE, added, CHECKED_HEAD + _state_text(state), NOT_DONE)


def _why(e: Exception) -> str:
    return str(e).removeprefix("logbook: ").rstrip(". ")


def ensure_logged(root: Path, digest: str, rules: list, when: str) -> str | None:
    """Make sure these rules (parsed from bytes with this SHA-256) are the last logged version before they are used.
    None when they are (or were just logged); otherwise why the entry could not be written, and then no Yes may
    come from these rules.

    A read without the lock finds the usual case (nothing changed) without waiting for a writer. A change is
    decided again under the logbook lock, so two checks that see it at once write it once.
    """
    try:
        last = newest(logbook.read_checked(Path(root)))
    except UmwayiError as e:
        return _why(e)
    if last is not None and last.sha256 == digest:
        return None

    def build(current: list):
        now = newest(current)
        if now is not None and now.sha256 == digest:
            return None
        return entry(when, digest, rules, now)

    try:
        logbook.append_with(Path(root), when, build)
    except UmwayiError as e:
        return _why(e)
    return None
