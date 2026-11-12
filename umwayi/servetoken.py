"""The token of `umwayi serve` (workstream W6, requirement W6.R4): create, rotate, revoke and status.

A token is 32 random bytes from `secrets.token_bytes`, written as `umt1_` and 43 characters of unpadded base64url. It is
shown once, on a terminal, by `create` and `rotate`. Only its SHA-256 is kept, in `.umwayi/serve.token` (mode 0600, a
JSON file with exactly five keys). The server reads that file for every request (`read_record`), so a rotation or a
revoke is seen on the next request without a restart.

Every change is one logbook entry that names the id and the dates, never the token. The order is the one of `kill off`:
act, log, and undo when the entry cannot be written (the old record is put back byte for byte, and nothing is shown).
Exit codes of the commands: 0 done, 1 refused (a record exists, none exists, not a terminal), 2 an unexpected error or
an entry that could not be written, 64 usage; never 3.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import stat
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from umwayi import fsutil, logbook
from umwayi.errors import UmwayiError, UsageError

STATE_DIR = ".umwayi"
RECORD_NAME = "serve.token"
RECORD_REL = f"{STATE_DIR}/{RECORD_NAME}"
SOURCE = "umwayi serve"
MODE = 0o600
MAX_RECORD = 1024
DEFAULT_DAYS, MAX_DAYS = 30, 90
KEYS = ("schema", "id", "sha256", "created", "expires")
_ID = re.compile(r"T-[0-9a-f]{8}")
_HEX64 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class Result:
    code: int
    lines: list


def digest_hex(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def new_token() -> tuple:
    """(the token, its public id). The id is not derived from the token."""
    token = "umt1_" + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")
    return token, "T-" + secrets.token_hex(4)


def _record_path(root: Path) -> Path:
    return Path(root) / STATE_DIR / RECORD_NAME


def _no_duplicates(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate key")
        out[key] = value
    return out


def _refuse(_name):
    raise ValueError("not a plain JSON value")


def _days_between(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def read_record(root: Path):
    """The record as a dict, or None when it is missing or not exactly what `create` writes: a link, a folder or a file
    over 1 KB, bad JSON, a duplicate or extra or missing key, a schema other than 1, an id or digest of the wrong shape,
    a date that is not real, an expiry that is not after the creation, or a life over 90 days."""
    try:
        d = Path(root) / STATE_DIR
        if not stat.S_ISDIR(os.lstat(d).st_mode):
            return None
        path = d / RECORD_NAME
        if not stat.S_ISREG(os.lstat(path).st_mode):  # a link is not followed
            return None
        text = fsutil.read_regular(path, MAX_RECORD).decode("utf-8")
        rec = json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_refuse, parse_float=_refuse)
    except (OSError, ValueError, RecursionError):
        return None
    if type(rec) is not dict or tuple(sorted(rec)) != tuple(sorted(KEYS)) or type(rec["schema"]) is not int \
            or rec["schema"] != 1:
        return None
    if type(rec["id"]) is not str or not _ID.fullmatch(rec["id"]):
        return None
    if type(rec["sha256"]) is not str or not _HEX64.fullmatch(rec["sha256"]):
        return None
    for key in ("created", "expires"):
        if type(rec[key]) is not str or not logbook.real_date(rec[key]):
            return None
    if not 1 <= _days_between(rec["created"], rec["expires"]) <= MAX_DAYS:
        return None
    return rec


def days_left(rec: dict, today: str) -> int:
    return _days_between(today, rec["expires"])


def _check_days(days) -> int:
    if type(days) is not int or not 1 <= days <= MAX_DAYS:
        raise UsageError(f"serve token: --days must be a whole number from 1 to {MAX_DAYS}")
    return days


def _text(rec: dict) -> bytes:
    return (json.dumps(rec, indent=2) + "\n").encode("utf-8")


def _state_dir(root: Path) -> Path:
    d = Path(root) / STATE_DIR
    if d.is_symlink() or (d.exists() and not d.is_dir()):
        raise UmwayiError(f"serve token: {STATE_DIR} is not a normal folder, so nothing was changed")
    d.mkdir(exist_ok=True)
    return d


def _entry(today: str, added: str, checked: str, not_done: str) -> logbook.Entry:
    return logbook.Entry(today, SOURCE, added, checked, not_done)


def _terminal_only() -> Result:
    return Result(1, ["serve token: the token is shown once, and only on a terminal (a pipe, a file or a CI log would "
                      "keep it). Run this command in a terminal. Nothing was changed."])


def _failed(why: str) -> Result:
    return Result(2, [f"serve token: the logbook could not record it ({why}), so nothing was changed and no token was "
                      "shown."])


def _shown(token: str, rec: dict) -> list:
    return [f"Token: {token}", f"Id: {rec['id']}", f"Expires: {rec['expires']}",
            "Shown once. umwayi keeps only a fingerprint of it."]


def _fresh(today: str, days: int) -> tuple:
    token, tid = new_token()
    expires = (date.fromisoformat(today) + timedelta(days=days)).isoformat()
    return token, {"schema": 1, "id": tid, "sha256": digest_hex(token), "created": today, "expires": expires}


def create(root: Path, days: int, today: str, is_terminal: bool) -> Result:
    days = _check_days(days)
    if not is_terminal:
        return _terminal_only()
    root = Path(root)
    d = _state_dir(root)
    path = d / RECORD_NAME
    if os.path.lexists(path):
        return Result(1, [f"serve token: {RECORD_REL} already exists. Use 'umwayi serve token rotate' for a new token "
                          "or 'umwayi serve token revoke' to remove it. Nothing was changed."])
    token, rec = _fresh(today, days)
    fsutil.atomic_write(path, _text(rec), mode=MODE)
    try:
        logbook.append(root, _entry(
            today, f"Created token {rec['id']}, expires on {rec['expires']}.",
            f"The record {RECORD_REL} was written with mode 0600 and holds a SHA-256 only.",
            "The value was shown once on the terminal and not recorded."))
    except BaseException as e:
        os.unlink(path)
        if isinstance(e, UmwayiError):
            return _failed(str(e).rstrip(". "))
        raise
    return Result(0, _shown(token, rec))


def rotate(root: Path, days: int, today: str, is_terminal: bool) -> Result:
    days = _check_days(days)
    if not is_terminal:
        return _terminal_only()
    root = Path(root)
    old = read_record(root)
    if old is None:
        return Result(1, [f"serve token: there is no valid token record to rotate. Use 'umwayi serve token create'. "
                          "Nothing was changed."])
    path = _record_path(root)
    old_bytes = fsutil.read_regular(path, MAX_RECORD)
    token, rec = _fresh(today, days)
    fsutil.atomic_write(path, _text(rec), mode=MODE)
    try:
        logbook.append(root, _entry(
            today, f"Rotated token {old['id']} to {rec['id']}, expires on {rec['expires']}.",
            f"The record {RECORD_REL} was written with mode 0600 and holds a SHA-256 only.",
            "The value was shown once on the terminal and not recorded."))
    except BaseException as e:
        fsutil.atomic_write(path, old_bytes, mode=MODE)
        if isinstance(e, UmwayiError):
            return _failed(str(e).rstrip(". "))
        raise
    return Result(0, _shown(token, rec))


def revoke(root: Path, today: str) -> Result:
    root = Path(root)
    path = _record_path(root)
    if not os.path.lexists(path):
        return Result(1, ["serve token: there is no token record to revoke. Nothing was changed."])
    old = read_record(root)
    tid = old["id"] if old else "(unreadable record)"
    old_bytes = None
    if old is not None:
        old_bytes = fsutil.read_regular(path, MAX_RECORD)
    os.unlink(path)
    try:
        logbook.append(root, _entry(today, f"Revoked token {tid}.", f"The record {RECORD_REL} was removed.",
                                    "No token value was read or recorded."))
    except BaseException as e:
        if old_bytes is not None:
            fsutil.atomic_write(path, old_bytes, mode=MODE)
        if isinstance(e, UmwayiError):
            return _failed(str(e).rstrip(". "))
        raise
    return Result(0, [f"Revoked token {tid}. Every request is refused until a new token is created."])


def status(root: Path, today: str) -> Result:
    """Reads only. Does not look at the logbook and prints no digest and no token."""
    path = _record_path(root)
    if not os.path.lexists(path):
        return Result(0, ["No token."])
    rec = read_record(root)
    if rec is None:
        return Result(0, ["The token record cannot be read or is not valid, so every request is refused. Use "
                          "'umwayi serve token revoke' and then 'umwayi serve token create'."])
    left = days_left(rec, today)
    tail = f"{left} days left" if left > 0 else "expired"
    return Result(0, [f"Token {rec['id']}: created {rec['created']}, expires {rec['expires']}, {tail}"])
