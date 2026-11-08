"""The SessionStart canary of a Claude Code ACP chat (layer 10 part 7, requirement 10.R11.4).

    python3 canary.py --dir DIR --token TOKEN

umwayi gives this command to the adapter in the same inline settings as the layer 9
PreToolUse hook. When it runs, it creates one empty file DIR/TOKEN (O_EXCL, mode 0600,
never following a link) and exits 0. That file shows umwayi that command hooks from those
settings run in this very session, before the first prompt is sent.

It prints nothing, on stdout or stderr, and never reads its input. Any bad argument (not
exactly --dir and --token once each, a folder that is not an absolute path to an existing
folder, a token that is not 32 lowercase hex characters), a file that already exists, or
any other error: exit 2 and no file. Standard library only; it never imports umwayi.
"""

import os
import stat
import sys

TOKEN_LENGTH = 32
HEX = frozenset("0123456789abcdef")
BAD = 2


def parse(args):
    """{"--dir": DIR, "--token": TOKEN}, or None for anything else."""
    if len(args) != 4:
        return None
    found = {}
    for flag, value in ((args[0], args[1]), (args[2], args[3])):
        if flag not in ("--dir", "--token") or flag in found:
            return None
        found[flag] = value
    folder, token = found["--dir"], found["--token"]
    if len(token) != TOKEN_LENGTH or not set(token) <= HEX:
        return None
    if not folder.startswith("/") or "\x00" in folder or ".." in folder.split("/"):
        return None
    return found


def main(args) -> int:
    found = parse(args)
    if found is None:
        return BAD
    folder = found["--dir"]
    try:
        st = os.lstat(folder)
    except OSError:
        return BAD
    if not stat.S_ISDIR(st.st_mode):  # a link to a folder is refused too
        return BAD
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(os.path.join(folder, found["--token"]), flags, 0o600)
    except OSError:
        return BAD
    os.close(fd)
    return 0


if __name__ == "__main__":
    try:
        code = main(sys.argv[1:])
    except BaseException:  # noqa: BLE001 - every error is exit 2, with no output
        code = BAD
    sys.exit(code)
