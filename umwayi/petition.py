"""Layer 13, slice 3: Courts. `umwayi petition RULE_ID --helper NAME --reason TEXT [--date D]` (13.R6).

An AI helper that thinks a No is wrong can say so to the owner. The petition becomes one open queue item, with
the fixed title `Petition against rule RULE_ID by HELPER` and a recommendation that marks the reason as untrusted
text. It never changes the verdict: this module reads rules.yaml only through `rules.load_rules`, to see that the
rule exists and says No, has no code path that writes it, and never asks the rules for an answer.

The order: the arguments (64), the petition lock, the tamper and chain check of the logbook (1), rules.yaml read
(1), the rule exists with the verdict No (1), the same open petition (prints `Already open, nothing added`, 0),
the four count limits (1), then the row and its entry in one queue commit. The limits are counted from queue.md
(open petitions) and the logbook (petitions accepted today), never from the command line. A refused petition
writes nothing, so a flood cannot grow the logbook.

The reason is untrusted: it goes into queue.md only, never into the logbook (the entry holds its length) and never
into a message. No code of layer 13 reads it.
"""

from __future__ import annotations

import errno
import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from umwayi import logbook, rules, taskqueue
from umwayi.errors import UmwayiError, UsageError

try:
    import fcntl
except ImportError:  # for example on Windows
    fcntl = None

SOURCE = "umwayi petition"
MAX_REASON = 200
MAX_RULE_ID = 100
OPEN_PER_HELPER = 3
OPEN_IN_ALL = 10
ACCEPTED_PER_HELPER = 5
ACCEPTED_IN_ALL = 10
RECOMMENDATION_HEAD = "Petition, untrusted text from an AI helper: "
LOCK_NAME = "petition.lock"
LOCK_WAIT_SECONDS = 3.0
_LOCK_POLL_SECONDS = 0.05
_BUSY = {errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES}
NOTHING = "Nothing was written."

_RULE_ID = re.compile(r"[a-z0-9][a-z0-9_-]*")
_HELPER = re.compile(r"[a-z][a-z0-9_-]{0,39}")
_TITLE = re.compile(r"Petition against rule ([a-z0-9][a-z0-9_-]*) by ([a-z][a-z0-9_-]{0,39})")
_ACCEPTED = re.compile(r"Q-\d{4,} \(decision\) as open: Petition against rule ([a-z0-9][a-z0-9_-]*) by "
                       r"([a-z][a-z0-9_-]{0,39})")
_WORDS = {rules.YES: "Yes", rules.NO: "No", rules.ASK: "Ask me first"}


@dataclass(frozen=True)
class Petitioned:
    row: taskqueue.Row
    added: bool  # False when the same petition was already open


def title(rule_id: str, helper: str) -> str:
    return f"Petition against rule {rule_id} by {helper}"


# ------------------------------------------------------------------ arguments


def _check_args(rule_id, helper, reason, when) -> tuple:
    if not isinstance(rule_id, str) or len(rule_id) > MAX_RULE_ID or not _RULE_ID.fullmatch(rule_id):
        raise UsageError(f"petition: RULE_ID must be a rule id (lowercase letters, digits, _ and -, up to "
                         f"{MAX_RULE_ID} characters). " + NOTHING)
    if not isinstance(helper, str) or not _HELPER.fullmatch(helper):
        raise UsageError("petition: --helper must be a name: a lowercase letter, then up to 39 lowercase letters, "
                         "digits, _ or -. " + NOTHING)
    r = reason.strip() if isinstance(reason, str) else ""
    if not r or len(r) > MAX_REASON or not r.isprintable() or "|" in r:
        raise UsageError(f"petition: --reason must be one line of plain text, 1 to {MAX_REASON} characters, "
                         "without |. " + NOTHING)
    if not logbook.real_date(when):
        raise UsageError("petition: date must be a real date YYYY-MM-DD. " + NOTHING)
    return rule_id, helper, r


# ------------------------------------------------------------------ the lock


@contextmanager
def _held(root: Path):
    """One petition at a time, from the counts to the commit: fcntl.flock on .umwayi/petition.lock."""
    state = Path(root) / logbook.STATE_DIR
    if state.is_symlink() or (state.exists() and not state.is_dir()):
        raise UmwayiError("petition: .umwayi must be a normal folder. " + NOTHING)
    if fcntl is None:
        raise UmwayiError("petition: file locking is not available on this platform. " + NOTHING)
    try:
        state.mkdir(exist_ok=True)
        fd = os.open(state / LOCK_NAME, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
                     | getattr(os, "O_CLOEXEC", 0), 0o644)
    except OSError:
        raise UmwayiError("petition: the lock file .umwayi/petition.lock cannot be opened (is it a link or a "
                          "folder?). " + NOTHING) from None
    try:
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as e:
                if e.errno not in _BUSY:
                    raise UmwayiError("petition: the operating system refused the lock on .umwayi/petition.lock. "
                                      + NOTHING) from None
                if time.monotonic() >= deadline:
                    raise UmwayiError("petition: another petition holds the lock .umwayi/petition.lock. Try again "
                                      "in a moment. " + NOTHING) from None
                time.sleep(_LOCK_POLL_SECONDS)
        yield
    finally:
        os.close(fd)


# ------------------------------------------------------------------ the counts


def _open_petitions(root: Path) -> list:
    """(rule id, helper, row) of every open petition in queue.md. A missing queue.md has none."""
    path = Path(root) / taskqueue.QUEUE_NAME
    if not path.exists() and not path.is_symlink():
        return []
    out = []
    for row in taskqueue.list_rows(root, status="open", kind="decision"):
        m = _TITLE.fullmatch(row.title)
        if m:
            out.append((m.group(1), m.group(2), row))
    return out


def _accepted_on(entries: list, when: str) -> list:
    """(rule id, helper) of every petition the logbook shows as accepted on this logbook day."""
    out = []
    for e in entries:
        if e.source == SOURCE and e.date == when:
            m = _ACCEPTED.fullmatch(e.added)
            if m:
                out.append((m.group(1), m.group(2)))
    return out


def _refuse(limit: str, count: int, cap: int):
    raise UmwayiError(f"petition: refused, the limit of {cap} {limit} is reached ({count} of {cap}). " + NOTHING)


# ------------------------------------------------------------------ the command


def petition(root: Path, rule_id: str, helper: str, reason: str, when: str) -> Petitioned:
    rule_id, helper, reason = _check_args(rule_id, helper, reason, when)
    root = Path(root)
    with _held(root):
        try:
            entries = logbook.read_checked(root)
        except UmwayiError as e:
            raise UmwayiError(f"petition: the logbook is not intact ({e}). " + NOTHING) from None
        try:
            loaded = rules.load_rules(root / "rules.yaml")
        except UmwayiError as e:
            raise UmwayiError(f"petition: rules.yaml cannot be read ({e}). " + NOTHING) from None
        found = next((r for r in loaded if r.id == rule_id), None)
        if found is None:
            raise UmwayiError(f"petition: there is no rule {rule_id} in rules.yaml; only a No rule can be "
                              "petitioned. " + NOTHING)
        if found.verdict != rules.NO:
            raise UmwayiError(f"petition: rule {rule_id} has the verdict {_WORDS[found.verdict]}; only a No rule can "
                              "be petitioned. " + NOTHING)

        open_now = _open_petitions(root)
        same = next((row for rid, who, row in open_now if rid == rule_id and who == helper), None)
        if same is not None:
            return Petitioned(same, False)
        accepted = _accepted_on(entries, when)
        mine_open = sum(1 for _r, who, _row in open_now if who == helper)
        mine_today = sum(1 for _r, who in accepted if who == helper)
        if mine_open >= OPEN_PER_HELPER:
            _refuse("open petitions for one AI helper", mine_open, OPEN_PER_HELPER)
        if len(open_now) >= OPEN_IN_ALL:
            _refuse("open petitions in all", len(open_now), OPEN_IN_ALL)
        if mine_today >= ACCEPTED_PER_HELPER:
            _refuse("petitions accepted today for one AI helper", mine_today, ACCEPTED_PER_HELPER)
        if len(accepted) >= ACCEPTED_IN_ALL:
            _refuse("petitions accepted today in all", len(accepted), ACCEPTED_IN_ALL)

        def entry_for(row):
            return logbook.Entry(
                date=when,
                source=SOURCE,
                added=f"{row.id} (decision) as open: {row.title}",
                checked=(f"rule {rule_id} exists with verdict No; limits held (open for this helper {mine_open + 1} "
                         f"of {OPEN_PER_HELPER}, open in all {len(open_now) + 1} of {OPEN_IN_ALL}, accepted today "
                         f"for this helper {mine_today + 1} of {ACCEPTED_PER_HELPER}, in all {len(accepted) + 1} of "
                         f"{ACCEPTED_IN_ALL}); reason {len(reason)} characters"),
                not_done=("The rule, rules.yaml and every answer were not changed. The reason text is in queue.md "
                          "and not copied here."),
            )

        row = taskqueue.add_with_entry(root, "decision", title(rule_id, helper), RECOMMENDATION_HEAD + reason, when,
                                       entry_for)
    return Petitioned(row, True)


def render(p: Petitioned) -> list:
    if not p.added:
        return [f"Already open, nothing added: {p.row.id} (decision): {p.row.title}"]
    return [
        f"Added {p.row.id} (decision): {p.row.title}",
        "The rule, rules.yaml and every answer were not changed. The owner reads the petition in the queue.",
        f"The owner answers it with: umwayi queue answer {p.row.id} --answer TEXT --revisit-if TEXT",
    ]
