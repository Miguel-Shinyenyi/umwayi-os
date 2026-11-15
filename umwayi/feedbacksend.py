"""W29: `umwayi feedback send [--note TEXT | --note-file FILE] [--out FILE]`. Opt in only, and it sends nothing over a network.

It builds a bundle (a header with the umwayi and Python versions and the system name, the W33 export of
umwayi/feedback.py, the tester's own note), runs every line through the one filter `feedback.redact`, shows the tester
every line exactly as it would leave, and writes the file only after a typed yes in a real terminal. The tester sends the
file by hand. The kill switch (on or unknown) blocks it. One logbook entry is written after the file, with the bundle's
SHA-256 only; if it cannot be written the file is removed.

Exit codes: 0 written, or the tester did not type yes (nothing written); 2 refused (no terminal, the kill switch, the
logbook check) or an unexpected error; 64 usage. Never 1 or 3. Standard library only, and no network module.
"""

from __future__ import annotations

import getpass
import hashlib
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from umwayi import __version__, kill, logbook
from umwayi.errors import UmwayiError, UsageError
from umwayi.feedback import export, redact

MAX_NOTE_BYTES = 16 * 1024
MAX_NOTE_LINES = 200
SEND_SOURCE = "umwayi feedback send"
SHOW_BEGIN = "----- what would leave, line by line -----"
SHOW_END = "----- end of what would leave -----"
NOT_A_TERMINAL = ("feedback: this needs a real terminal, so that you can read the bundle and type yes yourself. "
                  "Nothing was written and nothing was sent.")
KILLED = ("feedback: the kill switch is on (or cannot be read), so nothing was written and nothing was sent. "
          "Turn it off with umwayi kill off if you mean to, then run this again.")
NOTHING = "Nothing was written and nothing was sent."
PROMPT = "Type yes to write this to the file above so that you can send it by hand. Anything else writes nothing: "


def _terminal():
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError, OSError):
        return False


def _ask(prompt):
    sys.stdout.write(prompt)
    sys.stdout.flush()
    line = sys.stdin.readline()
    if not line:
        raise EOFError
    return line.rstrip("\n")


def _read_note(note, note_file):
    if note is not None and note_file is not None:
        raise UsageError("feedback: give --note or --note-file, not both")
    if note_file is not None:
        p = Path(note_file)
        try:
            if p.is_symlink() or not p.is_file():
                raise UsageError("feedback: the note file is not a regular file")
            data = p.read_bytes()
        except OSError:
            raise UsageError("feedback: the note file cannot be read") from None
        if len(data) > MAX_NOTE_BYTES:
            raise UsageError(f"feedback: the note file is larger than {MAX_NOTE_BYTES // 1024} KB")
        try:
            note = data.decode("utf-8")
        except UnicodeDecodeError:
            raise UsageError("feedback: the note file is not UTF-8 text") from None
    if note is None:
        return []
    if len(note.encode("utf-8")) > MAX_NOTE_BYTES:
        raise UsageError(f"feedback: the note is larger than {MAX_NOTE_BYTES // 1024} KB")
    lines = note.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    if len(lines) > MAX_NOTE_LINES:
        raise UsageError(f"feedback: the note has more than {MAX_NOTE_LINES} lines")
    return lines


def _target(root, out, now):
    if out is None:
        stamp = datetime.fromtimestamp(now, timezone.utc).strftime("%Y%m%d-%H%M%S")
        folder = root / ".umwayi" / "feedback"
        for n in range(1, 100):
            p = folder / (f"feedback-{stamp}.txt" if n == 1 else f"feedback-{stamp}-{n}.txt")
            if not os.path.lexists(p):
                return p, True
        raise UsageError("feedback: too many bundles this second; try again")
    p = Path(out)
    if p.suffix != ".txt":
        raise UsageError("feedback: --out must name a new file that ends in .txt")
    if os.path.lexists(p):
        raise UsageError("feedback: --out names a file that is already there; nothing is ever overwritten")
    if not p.parent.is_dir() or p.parent.is_symlink():
        raise UsageError("feedback: the folder of --out does not exist")
    return p, False


def bundle(root, note_lines, now):
    """(the lines of the bundle after the filter, how many things were hidden). Raises UmwayiError when the export
    refuses (a missing logbook or one that fails its check)."""
    r = export(root)
    if r.code != 0:
        raise UmwayiError(r.lines[0])
    raw = ["umwayi feedback bundle, version 1",
           f"made: {datetime.fromtimestamp(now, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
           f"umwayi: {__version__}", f"python: {platform.python_version()}", f"system: {platform.system() or 'unknown'}",
           "summary of the logbook:", *r.lines, "note:", *(note_lines or ["(no note)"]), "end of the bundle"]
    home = os.environ.get("HOME") or os.path.expanduser("~")
    try:
        user = getpass.getuser()
    except Exception:
        user = None
    out, hidden = [], 0
    for line in raw:
        clean, n = redact(line, home=home, root=str(root), user=user)
        out.append(clean)
        hidden += n
    return out, hidden


def _write_new(path, data):
    """Write a new file with mode 0600 and never replace one that is there."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags, 0o600)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)


def send(root, note=None, note_file=None, out=None, *, today, now, say, warn):
    """W29. Returns the exit code. `say` and `warn` take one line each."""
    root = Path(root)
    note_lines = _read_note(note, note_file)
    target, default = _target(root, out, now)
    if not _terminal():
        warn(NOT_A_TERMINAL)
        return 2
    try:
        ks = kill.state(root)
    except Exception:
        ks = kill.UNKNOWN
    if ks != kill.OFF:
        warn(KILLED)
        return 2
    try:
        lines, hidden = bundle(root, note_lines, now)
    except UmwayiError as e:
        warn(str(e))
        return 2
    text = "\n".join(lines) + "\n"
    data = text.encode("utf-8")
    say(f"This is the whole feedback bundle. {hidden} things were hidden by the filter (secrets, emails, home paths).")
    say(f"Read every line. It would be written to: {target}")
    say(SHOW_BEGIN)
    for line in lines:
        say(line)
    say(SHOW_END)
    try:
        answer = _ask(PROMPT)
    except (EOFError, KeyboardInterrupt):
        answer = None
    if answer != "yes":
        say("")
        say(NOTHING)
        return 0
    digest = hashlib.sha256(data).hexdigest()
    try:
        if default:
            for d in (root / ".umwayi", root / ".umwayi" / "feedback"):
                if os.path.islink(d) or (os.path.lexists(d) and not os.path.isdir(d)):
                    raise OSError("not a folder")
                if not d.exists():
                    os.mkdir(d, 0o700)
        _write_new(target, data)
    except OSError:
        warn("feedback: the file could not be written. " + NOTHING)
        return 2
    try:
        logbook.append(root, logbook.Entry(
            today, SEND_SOURCE,
            f"feedback_send: a feedback bundle of {len(lines)} lines was written for the tester to send by hand "
            f"(sha256 {digest})",
            f"the logbook passed its check; the kill switch was off; the tester typed yes in a terminal; "
            f"{hidden} things were hidden by the filter",
            "Nothing was sent. The text of the bundle, the note and the path of the file are not in the logbook."))
    except (UmwayiError, OSError):
        try:
            os.unlink(target)
        except OSError:
            pass
        warn("feedback: the logbook entry could not be written, so the file was taken back. " + NOTHING)
        return 2
    say(f"Wrote the bundle to {target}")
    say("Nothing was sent. Send this file to the owner by hand, for example attach it to a feedback issue.")
    return 0

