"""W78 step 7 (Task 9): macOS confinement with Seatbelt (`sandbox-exec`), built behind a refusal.

`sandbox-exec -p PROFILE COMMAND ...` runs COMMAND under a Seatbelt profile. This module makes the profile text and the argument list
and has a self test for the owner to run on the Mac. It is NOT used to start a helper: `CHECKED_ON_MAC` is False, so `agent run` for an
agent with `confine: true` on macOS is refused with reason `platform` (as before), and it stays so until the owner has run the steps in
the pull request on a Mac and a later pull request sets the constant.

Why: CI has no macOS, so nothing here has run on a Mac in a test. Apple marks `sandbox-exec` deprecated and does not document the profile
language. Whether a profile that allows a real Claude Code (its sign-in in the Keychain, its API, `node`) is right has not been checked.

  * The profile is `(deny default)` and then allows: process fork and exec below the read paths; file reads below the read paths; file
    writes below the write paths; the system calls any program needs to start (sysctl read, mach lookup, signal to itself); the network
    unless `no_network`.
  * Paths go into the profile as quoted `(subpath "...")` strings. A path with a quote, a backslash or a control character is refused
    (`profile`): the profile text is never built from text that could close the string.
  * The program is the fixed path `/usr/bin/sandbox-exec`, run without a shell.

Standard library only. No network import.
"""
from __future__ import annotations

import os
import sys

SANDBOX_EXEC = "/usr/bin/sandbox-exec"
CHECKED_ON_MAC = False  # a later pull request sets this after the owner's check on a Mac (docs/seatbelt-check.md steps)
SYSTEM_READ = ("/usr", "/bin", "/sbin", "/System", "/Library", "/private/etc", "/private/var/db", "/dev", "/opt")
BAD = ('"', "\\", "\x00", "\n", "\r")


class SeatbeltRefused(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _quote(path: str) -> str:
    if not isinstance(path, str) or not path.startswith("/") or any(c in path for c in BAD) or any(ord(c) < 32 for c in path):
        raise SeatbeltRefused("profile")
    return f'(subpath "{os.path.normpath(path)}")'


def _ancestors(path: str):
    q = os.path.dirname(os.path.normpath(path))
    out = ["/"]
    while q not in ("/", ""):
        out.append(q)
        q = os.path.dirname(q)
    return [_quote(a)[len('(subpath "'):-2] for a in out]


def profile(read_paths, write_paths, no_network: bool = False) -> str:
    """The Seatbelt profile text. Raises SeatbeltRefused("profile") for a path that is not a plain absolute path."""
    reads = " ".join(_quote(p) for p in sorted(set(read_paths) | set(write_paths)))
    writes = " ".join(_quote(p) for p in sorted(set(write_paths)))
    ancestors = sorted({a for p in set(read_paths) | set(write_paths) for a in _ancestors(p)})
    lines = [
        "(version 1)",
        "(deny default)",
        "(allow process-fork)",
        f"(allow process-exec {reads})",
        f"(allow file-read* {reads})",
        "(allow file-read-metadata)",
        # a program resolves a path by reading each folder above it; the folders themselves (their names, not what is in them) are
        # listed, so `getcwd` and imports work. Found on a Mac: without these a Python does not start.
        *[f'(allow file-read* (literal "{a}"))' for a in ancestors],
        "(allow sysctl-read)",
        "(allow mach-lookup)",
        "(allow signal (target self))",
    ]
    if writes:
        lines.append(f"(allow file-write* {writes})")
    lines.append("(deny network*)" if no_network else "(allow network*)")
    return "\n".join(lines) + "\n"


def argv(read_paths, write_paths, command, no_network: bool = False) -> list:
    """The argument list that runs `command` (absolute path first) under the profile. Never a shell."""
    command = [str(c) for c in command]
    if not command or not os.path.isabs(command[0]):
        raise SeatbeltRefused("profile")
    return [SANDBOX_EXEC, "-p", profile(read_paths, write_paths, no_network)] + command


def available() -> bool:
    return sys.platform == "darwin" and os.access(SANDBOX_EXEC, os.X_OK)


def start_allowed() -> tuple:
    """(True, "") or (False, reason): may a helper be started under Seatbelt on this machine? Not before the owner's check."""
    if sys.platform != "darwin":
        return False, "platform"
    if not available():
        return False, "unavailable"
    if not CHECKED_ON_MAC:
        return False, "platform"  # built, not checked on a Mac: refused
    return True, ""


def _run(args: list) -> tuple:
    """(exit code, standard output) of a program, started without a shell, with the output read through a pipe."""
    r, w = os.pipe()
    actions = [(os.POSIX_SPAWN_DUP2, w, 1), (os.POSIX_SPAWN_CLOSE, r), (os.POSIX_SPAWN_CLOSE, w)]
    pid = os.posix_spawn(args[0], args, dict(os.environ), file_actions=actions)
    os.close(w)
    chunks = []
    with os.fdopen(r, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            chunks.append(chunk)
            if sum(map(len, chunks)) > 1 << 20:
                break
    _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status), b"".join(chunks).decode("utf-8", "replace")


def selftest() -> dict:
    """What the owner runs on a Mac (`python -m umwayi.seatbelt selftest`): a few real commands under a profile, each answered with
    what happened. It writes only below a fresh temporary folder it makes and removes. It does not start a helper and reads no key."""
    import tempfile
    if not available():
        return {"available": False, "reason": "sandbox-exec is not there or this is not macOS"}
    base = os.path.realpath(tempfile.mkdtemp(prefix="useat"))
    work, other = os.path.join(base, "work"), os.path.join(base, "other")
    os.makedirs(work)
    os.makedirs(other)
    with open(os.path.join(other, "secret.txt"), "w", encoding="utf-8") as f:
        f.write("s")
    reads = [p for p in SYSTEM_READ if os.path.exists(p)] + [os.path.realpath(sys.prefix), os.path.dirname(os.path.realpath(sys.executable))]
    script = (
        "import json, os, socket, sys\nout = {}\n"
        "def t(name, fn):\n    try:\n        fn(); out[name] = 'ok'\n    except OSError as e:\n        out[name] = 'refused' if e.errno in (1, 13) else f'error {e.errno}'\n"
        f"t('write_inside', lambda: open({os.path.join(work, 'a.txt')!r}, 'w').write('x'))\n"
        f"t('write_outside', lambda: open({os.path.join(other, 'b.txt')!r}, 'w').write('x'))\n"
        f"t('read_unlisted', lambda: open({os.path.join(other, 'secret.txt')!r}).read())\n"
        "t('network', lambda: socket.create_connection(('127.0.0.1', 9), timeout=1))\n"
        "print(json.dumps(out))\n")
    result = {"available": True, "macos": __import__("platform").mac_ver()[0]}
    here = os.getcwd()
    os.chdir(work)  # the child starts here, and a program asks for its folder at start
    try:
        for label, no_net in (("with_network", False), ("no_network", True)):
            try:
                code, out = _run(argv(reads, [work], [sys.executable, "-c", script], no_net))
                result[label] = {"exit": code, "out": out.strip().splitlines()[-1:] or []}
            except OSError as e:
                result[label] = {"error": type(e).__name__}
    finally:
        os.chdir(here)
    import shutil
    shutil.rmtree(base, ignore_errors=True)
    return result


TESTING_SWITCH = "--i-am-testing"


def _parse_run(args: list):
    """(read, write, no_network, testing, command) from `--read P ... --write P ... [--no-network] [--i-am-testing] -- /abs/command args`,
    or None."""
    read, write, no_net, testing, i = [], [], False, False, 0
    while i < len(args) and args[i] != "--":
        if args[i] == "--no-network":
            no_net, i = True, i + 1
        elif args[i] == TESTING_SWITCH:
            testing, i = True, i + 1
        elif args[i] in ("--read", "--write") and i + 1 < len(args) and args[i + 1] != "--":
            (read if args[i] == "--read" else write).append(args[i + 1])
            i += 2
        else:
            return None
    command = args[i + 1:]
    return (read, write, no_net, testing, command) if i < len(args) and command else None


def main(args=None) -> int:
    import json
    args = list(sys.argv[1:] if args is None else args)
    if args == ["selftest"]:
        print(json.dumps(selftest(), indent=2))
        return 0 if available() else 2
    if args and args[0] == "run":  # the owner's try of a real command: `run --read P --write W [--no-network] -- /abs/cmd args`
        parsed = _parse_run(args[1:])
        if parsed is None:
            sys.stderr.write("usage: python -m umwayi.seatbelt run --read PATH ... --write PATH ... [--no-network] [--i-am-testing] "
                             "-- /absolute/command ...\n")
            return 64
        read, write, no_net, testing, command = parsed
        allowed, why = start_allowed()
        if not allowed and not (testing and available()):
            # F3a: while CHECKED_ON_MAC is False a run is a hand test, and the owner says so by typing the switch
            sys.stderr.write(f"refused: not confined ({why}). Allowed next: this is not checked on a Mac yet; to try it by hand, "
                             f"type {TESTING_SWITCH} before the --.\n")
            return 2
        try:
            full = argv(read, write, command, no_net)
        except SeatbeltRefused as e:
            sys.stderr.write(f"refused: not confined ({e.reason}).\n")
            return 2
        pid = os.posix_spawn(full[0], full, dict(os.environ))
        return os.waitstatus_to_exitcode(os.waitpid(pid, 0)[1])
    sys.stderr.write("usage: python -m umwayi.seatbelt selftest | run ...\n")
    return 64


if __name__ == "__main__":
    sys.exit(main())
