"""Layer 8: the kill switch, .umwayi/KILL.

While the switch is on, every AI helper, job and workflow stops before doing
anything, with exit 3 (Ask me first) and one logbook entry.

    umwayi kill on [--reason TEXT]   create .umwayi/KILL
    umwayi kill off                  remove it
    umwayi kill status               on (exit 3), off (exit 0) or unknown (exit 3)

State, read without following links:
  * off      .umwayi is missing, or it is a readable folder with no KILL in it
  * on       anything named KILL exists in .umwayi (a file, a folder, a link)
  * unknown  .umwayi is not a normal folder, or it or KILL cannot be read

Fail closed: unknown stops runs exactly like on.

Turning the switch on must work even when the logbook is broken, so `on`
creates the file first and then tries to log it. Turning it off is the
opposite: if the logbook cannot record it, the switch stays on.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from umwayi import logbook
from umwayi.errors import UmwayiError, UsageError

STATE_DIR = ".umwayi"
KILL_NAME = "KILL"
KILL_REL = f"{STATE_DIR}/{KILL_NAME}"
OFF, ON, UNKNOWN = "off", "on", "unknown"
MAX_REASON = 200


@dataclass(frozen=True)
class Result:
    code: int
    lines: list


def state(root: Path) -> str:
    d = Path(root) / STATE_DIR
    try:
        st = os.lstat(d)
    except FileNotFoundError:
        return OFF
    except OSError:
        return UNKNOWN
    if not stat.S_ISDIR(st.st_mode):
        return UNKNOWN  # a file or a symbolic link where the folder should be
    try:
        os.lstat(d / KILL_NAME)
    except FileNotFoundError:
        try:
            os.listdir(d)  # make sure "not there" is not a folder we cannot read
        except OSError:
            return UNKNOWN
        return OFF
    except OSError:
        return UNKNOWN
    return ON


def stopped(st: str) -> bool:
    """True unless the switch is known to be off."""
    return st != OFF


def reason(st: str) -> str:
    if st == ON:
        return f"The kill switch is on ({KILL_REL} exists). Turn it off with 'umwayi kill off'."
    return (f"The kill switch state could not be read ({STATE_DIR} or {KILL_REL} is not a normal, readable "
            "file or folder), so everything stops.")


def short(st: str) -> str:
    return "the kill switch is on" if st == ON else "the kill switch state could not be read"


def _entry(today: str, added: str, checked: str, not_done: str) -> logbook.Entry:
    return logbook.Entry(today, "umwayi kill", added, checked, not_done)


def turn_on(root: Path, today: str, why: str | None = None) -> Result:
    root = Path(root)
    if why is not None:
        why = why.strip()
        if not why or len(why) > MAX_REASON or not why.isprintable():
            raise UsageError(f"kill: --reason must be one line of plain text (1 to {MAX_REASON} characters)")
    st = state(root)
    if st == ON:
        return Result(0, ["The kill switch is already on. Nothing was changed."])
    d = root / STATE_DIR
    if st == UNKNOWN:
        raise UmwayiError(
            f"kill: {STATE_DIR} is not a normal, readable folder, so {KILL_REL} cannot be created. "
            "Runs already stop while the state cannot be read."
        )
    try:
        d.mkdir(exist_ok=True)
        fd = os.open(d / KILL_NAME, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
    except FileExistsError:
        return Result(0, ["The kill switch is already on. Nothing was changed."])
    except OSError:
        raise UmwayiError(f"kill: {KILL_REL} could not be created") from None
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(f"on since {today}\n".encode("ascii"))
    except OSError:
        pass  # the file exists, so the switch is on; its text does not matter
    lines = ["The kill switch is on. Every AI helper, job and workflow stops until 'umwayi kill off'."]
    added = "the kill switch was turned on" + (f": {why}" if why else "")
    try:
        logbook.append(root, _entry(today, added, f"{KILL_REL} did not exist and was created",
                                    "No run was stopped by this command itself. Nothing else was changed."))
    except Exception as e:
        w = str(e).rstrip(". ") if isinstance(e, UmwayiError) else "an unexpected error"
        lines.append(f"The logbook could not be written ({w}). Nothing was logged, but the switch is on.")
    return Result(0, lines)


def turn_off(root: Path, today: str) -> Result:
    root = Path(root)
    st = state(root)
    if st == OFF:
        return Result(0, ["The kill switch is already off. Nothing was changed."])
    if st == UNKNOWN:
        raise UmwayiError(f"kill: the state cannot be read, so it was not turned off. Check {STATE_DIR} by hand.")
    path = root / KILL_REL
    if path.is_symlink() or not path.is_file():
        raise UmwayiError(f"kill: {KILL_REL} is not a normal file. Remove it by hand if you want the switch off.")
    try:
        content = path.read_bytes()
        os.unlink(path)
    except OSError:
        raise UmwayiError(f"kill: {KILL_REL} could not be removed, the switch stays on") from None
    try:
        logbook.append(root, _entry(today, "the kill switch was turned off", f"{KILL_REL} existed and was removed",
                                    "No run was started by this command. Nothing else was changed."))
    except Exception as e:
        w = str(e).rstrip(". ") if isinstance(e, UmwayiError) else "an unexpected error"
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
            with os.fdopen(fd, "wb") as f:
                f.write(content)
        except FileExistsError:
            pass
        except OSError:
            raise UmwayiError(
                f"kill: the logbook could not record turning the switch off ({w}) AND {KILL_REL} could not be "
                "put back. The switch is OFF. Turn it on again with 'umwayi kill on'."
            ) from None
        raise UmwayiError(f"kill: the logbook could not record turning the switch off ({w}), so it stays on") from None
    return Result(0, ["The kill switch is off."])


def status(root: Path) -> Result:
    st = state(root)
    if st == OFF:
        return Result(0, ["off"])
    return Result(3, [st, reason(st)])
