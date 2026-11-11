"""Layer 12, UI.2: `umwayi view snapshot`. One JSON file of counts for the web page, and one logbook entry.

    umwayi view snapshot [--out PATH] [--date D]

The file holds whole numbers, one of the words on, off, unknown, and dates. It never holds text from any file (no
title, answer, rule, schedule name, archive pointer, memory line or logbook line), a path or a secret (12.R4.2).
Nothing is parsed here: every count comes from the layer's own reader (logbook.read_checked_chain for the tamper
check and the logbook counts, budget.parse_ledger and budget.day_totals, taskqueue.list_rows, rules.load_rules,
kill.state, schedule.counts). A reader that raises gives null for its part (12.R4.3).

Order: the arguments (64), the tamper check (1, nothing is written), gather, render, write the file through the
shared atomic writer (mode 0600), then the one logbook entry. If the entry cannot be written the file is put back as
it was, and the exit is 2. It asks the rules nothing and does not look at the kill switch: it starts no run, and the
owner needs it most when the switch is on.

Exit codes: 0 done, 1 the tamper check failed, 64 usage, 2 anything unexpected. Never 3.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import stat
from datetime import date, timedelta
from pathlib import Path

from umwayi import budget, fsutil, kill, logbook, rules, schedule, taskqueue, units
from umwayi.errors import UmwayiError, UsageError

SCHEMA = 1
SOURCE = "umwayi view snapshot"
STATE_DIR = ".umwayi"
DEFAULT_OUT = f"{STATE_DIR}/snapshot.json"
MAX_OUT = 1024  # characters of --out
MAX_FILE = 4096  # an earlier snapshot is read up to this size; the page refuses a file over 4 KB too
MAX_COUNT = 1_000_000_000
MODE = 0o600
DAYS = 7
WORDS = (kill.ON, kill.OFF, kill.UNKNOWN)
KEYS = ("schema", "date", "queue", "rules", "logbook", "budget", "kill_switch", "schedule")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

CHECKED = "the logbook chain was intact before the write"
NOT_DONE = "no text, path or secret of any file is in the snapshot; the page was not opened"


# ------------------------------------------------------------------ the shape (12.R4.2, 12.R9.1)


def _whole(v) -> bool:
    return type(v) is int and 0 <= v <= MAX_COUNT


def _real_date(v) -> bool:
    if not isinstance(v, str) or not _DATE.match(v):
        return False
    try:
        date.fromisoformat(v)
    except ValueError:
        return False
    return True


def _numbers(v, names: tuple) -> bool:
    return isinstance(v, dict) and set(v) == set(names) and all(_whole(v[n]) for n in names)


def valid(obj) -> bool:
    """True if obj has exactly the fields of 12.R4.2 with the right types and ranges. A part may be null."""
    if not isinstance(obj, dict) or set(obj) != set(KEYS):
        return False
    if type(obj["schema"]) is not int or obj["schema"] != SCHEMA or not _real_date(obj["date"]):
        return False
    if obj["kill_switch"] not in WORDS:
        return False
    for name, fields in (("queue", ("open", "answered")), ("rules", ("yes", "no", "ask")),
                         ("logbook", ("entries", "chain_length")), ("schedule", ("entries", "installed", "enabled"))):
        if obj[name] is not None and not _numbers(obj[name], fields):
            return False
    b = obj["budget"]
    if b is None:
        return True
    if not isinstance(b, dict) or set(b) != {"days"} or not isinstance(b["days"], list) or len(b["days"]) != DAYS:
        return False
    return all(isinstance(d, dict) and set(d) == {"date", "used_uu"} and _real_date(d["date"])
               and _whole(d["used_uu"]) for d in b["days"])


# ------------------------------------------------------------------ --out (12.R4.6)


def _lstat(path: Path):
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError as e:
        if e.errno in (errno.ENAMETOOLONG, errno.ENOTDIR, errno.ELOOP):
            raise UsageError("view: --out is not a path this system can use. Nothing was changed.") from None
        raise


class Target:
    """Where the snapshot goes: the path, its name inside the root, what is there now, and a folder to make."""

    def __init__(self, path: Path, name: str, old, make_dir):
        self.path, self.name, self.old, self.make_dir = path, name, old, make_dir


def _parts(root: Path, given) -> tuple:
    if given is None:
        return DEFAULT_OUT.split("/"), True
    if not isinstance(given, str) or not 1 <= len(given) <= MAX_OUT or not given.isprintable():
        raise UsageError(f"view: --out must be a path of 1 to {MAX_OUT} printable characters on one line")
    if not given.endswith(".json"):
        raise UsageError("view: --out must end in .json")
    if ".." in given.split("/"):
        raise UsageError("view: --out must not have a .. part")
    rel = given
    if given.startswith("/"):
        rel = None
        for base in (os.path.abspath(root), os.path.realpath(root)):
            prefix = base.rstrip("/") + "/"
            if given.startswith(prefix):
                rel = given[len(prefix):]
                break
        if rel is None:
            raise UsageError("view: --out must stay inside the root")
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if not parts:
        raise UsageError("view: --out must name a file inside the root")
    return parts, False


def resolve_out(root: Path, given) -> Target:
    """The target of --out (default .umwayi/snapshot.json), or a usage error (64). Never echoes the given path."""
    root = Path(root)
    parts, default = _parts(root, given)
    cur, make_dir = root, None
    for i, part in enumerate(parts[:-1]):
        cur = cur / part
        st = _lstat(cur)
        if st is None:
            if default and i == 0:
                make_dir = cur  # the state folder of a root that has no logbook yet
                continue
            raise UsageError("view: the folder of --out does not exist. Nothing was changed.")
        if stat.S_ISLNK(st.st_mode):
            raise UsageError("view: --out must not go through a link. Nothing was changed.")
        if not stat.S_ISDIR(st.st_mode):
            raise UsageError("view: a part of --out before the file is not a folder. Nothing was changed.")
    path = cur / parts[-1]
    name = "/".join(parts)
    st = _lstat(path) if make_dir is None else None
    if st is None:
        return Target(path, name, None, make_dir)
    refusal = ("view: --out names a file that was not written by umwayi view snapshot, so it is left alone. "
               "Nothing was changed.")
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
        raise UsageError(refusal)  # a link, a folder, a device or a FIFO, or a file with a second name
    try:
        data = fsutil.read_regular(path, MAX_FILE)
        ours = valid(json.loads(data.decode("utf-8"), parse_constant=_no_constant))
    except (OSError, ValueError, RecursionError):  # TooBig and NotRegular are OSErrors; UnicodeError is a ValueError
        ours = False
    if not ours:
        raise UsageError(refusal)
    return Target(path, name, (data, stat.S_IMODE(st.st_mode)), None)


def _no_constant(_name):
    raise ValueError("not a JSON number")


# ------------------------------------------------------------------ gather (12.R4.2, 12.R4.3)


def _clamp(n: int) -> int:
    return min(int(n), MAX_COUNT)


def _queue(root: Path) -> dict:
    rows = taskqueue.list_rows(root)
    return {"open": _clamp(sum(r.status == "open" for r in rows)),
            "answered": _clamp(sum(r.status == "answered" for r in rows))}


def _rules(root: Path) -> dict:
    found = rules.load_rules(root / "rules.yaml")
    return {key: _clamp(sum(r.verdict == word for r in found))
            for key, word in (("yes", rules.YES), ("no", rules.NO), ("ask", rules.ASK))}


def _budget(entries: list, days: list) -> dict:
    led = budget.parse_ledger(entries)
    out = []
    for day in days:
        t = budget.day_totals(led, day)
        out.append({"date": day, "used_uu": _clamp(units.uu(t.used + t.reserved))})  # reserved counts in full
    return {"days": out}


def _kill(root: Path) -> str:
    try:
        st = kill.state(root)
    except Exception:
        return kill.UNKNOWN
    return st if st in WORDS else kill.UNKNOWN


def _schedule(root: Path) -> dict:
    entries, installed, enabled = schedule.counts(root)
    return {"entries": _clamp(entries), "installed": _clamp(installed), "enabled": _clamp(enabled)}


def _part(fn, *args):
    """A part that cannot be read is null, never zero and never a guess."""
    try:
        return fn(*args)
    except Exception:
        return None


def week_ending(when: str) -> list:
    """The seven days, oldest first, the last one is `when`."""
    try:
        last = date.fromisoformat(when)
        return [(last - timedelta(days=DAYS - 1 - i)).isoformat() for i in range(DAYS)]
    except (ValueError, OverflowError):
        raise UsageError("view: --date is too early for a week of seven days") from None


def gather(root: Path, when: str, entries: list, chain_length: int) -> dict:
    days = week_ending(when)
    return {
        "schema": SCHEMA,
        "date": when,
        "queue": _part(_queue, root),
        "rules": _part(_rules, root),
        "logbook": {"entries": _clamp(len(entries)), "chain_length": _clamp(chain_length)},
        "budget": _part(_budget, entries, days),
        "kill_switch": _kill(root),
        "schedule": _part(_schedule, root),
    }


def render(data: dict) -> bytes:
    """Fixed key order, two spaces of indent and a final newline: the same input gives the same bytes."""
    if not valid(data):
        raise UmwayiError("view: the snapshot did not have the shape of schema 1, so nothing was written")
    return (json.dumps(data, indent=2, ensure_ascii=True) + "\n").encode("ascii")


# ------------------------------------------------------------------ the command


def _put_back(target: Target) -> None:
    try:
        if target.old is None:
            try:
                os.unlink(target.path)
            except FileNotFoundError:
                pass
        else:
            fsutil.atomic_write(target.path, target.old[0], mode=target.old[1])
        if target.make_dir is not None:
            try:
                os.rmdir(target.make_dir)  # only if it is empty again
            except OSError:
                pass
    except Exception:
        raise UmwayiError("view: the logbook could not record the snapshot and the file could not be put back. "
                          "Check the snapshot file by hand.") from None


def snapshot(root, out, when: str) -> tuple:
    """(exit code, lines) of `umwayi view snapshot`. Usage errors are raised as UsageError (64)."""
    root = Path(root)
    if not taskqueue.is_valid_date(when):
        raise UsageError("view: --date must be a real date in the form YYYY-MM-DD")
    week_ending(when)
    target = resolve_out(root, out)
    try:
        entries, chain_length = logbook.read_checked_chain(root)  # the tamper check, before anything is written
    except UmwayiError as e:
        return 1, [f"Refused: {e}", "No snapshot was written and nothing was changed. "
                   "'umwayi logbook verify' says where the logbook is wrong."]
    if entries and when < entries[-1].date:
        raise UsageError("view: --date is before the date of the last logbook entry, and dates never go backwards")
    blob = render(gather(root, when, entries, chain_length))
    if target.make_dir is not None:
        os.mkdir(target.make_dir)
    try:
        fsutil.atomic_write(target.path, blob, mode=MODE)
    except BaseException:
        if target.make_dir is not None:
            try:
                os.rmdir(target.make_dir)
            except OSError:
                pass
        raise
    digest = hashlib.sha256(blob).hexdigest()
    try:
        logbook.append(root, logbook.Entry(when, SOURCE, f"Wrote a snapshot of counts to {target.name} "
                                           f"(SHA-256 {digest})", CHECKED, NOT_DONE))
    except BaseException as e:
        _put_back(target)
        if isinstance(e, UmwayiError):
            raise UmwayiError("view: the logbook could not record the snapshot, so the file was put back "
                              f"({str(e).rstrip('. ')}). Nothing else was changed.") from None
        raise
    return 0, [f"Wrote a snapshot of counts to {target.name} (SHA-256 {digest}). It holds numbers only: "
               "no text, path or secret of any file."]
