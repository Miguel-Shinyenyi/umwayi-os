"""W78 step 6 (5b): confine a process with Landlock (Linux), in a small program that runs before the helper.

`python umwayi/confine.py --read PATH ... --write PATH ... [--no-network] -- COMMAND ARG ...` builds a Landlock ruleset, restricts
itself, and then runs COMMAND as its only child and gives its exit code. The command and every process it starts inherit the
restriction. Landlock is
the kernel's own: a refused write fails in the helper with the kernel's EACCES, not with a message of umwayi.

  * Everything that Landlock can handle on this kernel is handled. Reads, executes and writes are allowed only below the listed paths:
    `--read` gives read and execute, `--write` gives read, write, create, remove, rename and truncate. A path that is not listed is
    refused, so the allow list must hold what the command needs (its interpreter, its libraries, its work folder).
  * `--no-network` handles TCP bind and connect with no rule, so no TCP connection is made. That needs ABI 4 (kernel 6.7); on an older
    kernel the start is refused, reason `kernel`. UDP and abstract Unix sockets are not covered by what this module sets.
  * Fails closed. If the kernel has no Landlock, it is off at boot, a rule cannot be added or the restriction fails, the command is
    NOT run: exit 2 and one line, `refused: not confined (REASON). Allowed next: ...`, REASON from the fixed list of enforce.REASONS.
    It never falls back to running the command unconfined.
  * Exit codes: 2 refused, 64 bad arguments; otherwise the command's own code (128 plus the signal number when a signal ended it).
    SIGTERM and SIGINT sent to this program are passed on to the command.

Not built here: the start of a helper through this program (`umwayi agent run` does not use it yet), the paths a real Claude Code, Kiro
or OpenCode needs, the broker socket, or macOS (Seatbelt is step 7). The tests run where Landlock is there (the CI runner reports
ABI 8 on its kernel) and skip with a fixed reason where it is not; a skipped test shows nothing.

Standard library only (ctypes). No network import.
"""
from __future__ import annotations

import ctypes
import os
import signal
import struct
import sys

SYS_CREATE, SYS_ADD, SYS_RESTRICT = 444, 445, 446  # the same numbers on x86_64 and aarch64
CREATE_VERSION = 1 << 0
RULE_PATH_BENEATH = 1
PR_SET_NO_NEW_PRIVS = 38

# filesystem access rights, by the ABI that introduced them
FS_EXECUTE, FS_WRITE_FILE, FS_READ_FILE, FS_READ_DIR = 1 << 0, 1 << 1, 1 << 2, 1 << 3
FS_REMOVE_DIR, FS_REMOVE_FILE = 1 << 4, 1 << 5
FS_MAKE_CHAR, FS_MAKE_DIR, FS_MAKE_REG, FS_MAKE_SOCK = 1 << 6, 1 << 7, 1 << 8, 1 << 9
FS_MAKE_FIFO, FS_MAKE_BLOCK, FS_MAKE_SYM = 1 << 10, 1 << 11, 1 << 12
FS_REFER = 1 << 13  # ABI 2
FS_TRUNCATE = 1 << 14  # ABI 3
FS_IOCTL_DEV = 1 << 15  # ABI 5
NET_BIND_TCP, NET_CONNECT_TCP = 1 << 0, 1 << 1  # ABI 4
NET_ABI = 4

READ_RIGHTS = FS_EXECUTE | FS_READ_FILE | FS_READ_DIR
EXIT_REFUSED, EXIT_USAGE = 2, 64
REASONS = ("unavailable", "kernel", "profile", "platform")  # a subset of enforce.REASONS, the fixed list


class ConfineRefused(Exception):
    def __init__(self, reason: str):
        assert reason in REASONS
        super().__init__(reason)
        self.reason = reason


def handled_fs(abi: int) -> int:
    """Every filesystem right this kernel's ABI knows."""
    mask = (1 << 13) - 1  # ABI 1: bits 0 to 12
    if abi >= 2:
        mask |= FS_REFER
    if abi >= 3:
        mask |= FS_TRUNCATE
    if abi >= 5:
        mask |= FS_IOCTL_DEV
    return mask


def write_rights(abi: int) -> int:
    return handled_fs(abi)  # a writable tree gets every right the ABI handles: read, write, create, remove, rename, truncate


def attr_size(abi: int) -> int:
    """The size of `struct landlock_ruleset_attr` for this ABI: 8 bytes (fs), 16 with net (ABI 4), 24 with scoped (ABI 6)."""
    return 8 if abi < 4 else 16 if abi < 6 else 24


def plan(abi: int | None, no_network: bool) -> tuple:
    """(handled fs mask, handled net mask) or ConfineRefused. `unavailable`: no Landlock here. `kernel`: no network rule on this ABI."""
    if abi is None or abi < 1:
        raise ConfineRefused("unavailable")
    if no_network and abi < NET_ABI:
        raise ConfineRefused("kernel")
    return handled_fs(abi), (NET_BIND_TCP | NET_CONNECT_TCP if no_network else 0)


def _libc():
    return ctypes.CDLL(None, use_errno=True)


def abi_version() -> int | None:
    """The ABI the kernel reports, or None (not Linux, no libc, no Landlock, off at boot). Creates nothing."""
    if not sys.platform.startswith("linux"):
        return None
    try:
        r = _libc().syscall(SYS_CREATE, None, 0, CREATE_VERSION)
    except (OSError, AttributeError):
        return None
    return int(r) if r >= 1 else None


def attr_bytes(abi: int, fs: int, net: int) -> bytes:
    """`struct landlock_ruleset_attr`: handled_access_fs, handled_access_net (ABI 4), scoped (ABI 6, none handled), as u64s."""
    fields = [fs, net, 0][: attr_size(abi) // 8]
    return struct.pack("=" + "Q" * len(fields), *fields)


def rule_bytes(access: int, fd: int) -> bytes:
    """`struct landlock_path_beneath_attr`, packed: allowed_access (u64), parent_fd (s32). 12 bytes."""
    return struct.pack("=Qi", access, fd)


def apply(read_paths, write_paths, no_network: bool = False, abi: int | None = None) -> int:
    """Restrict this process. Returns the ABI used. Raises ConfineRefused; then no restriction is in force. A path that does not
    exist is `profile`: the allow list is wrong, and a start with a wrong list is refused rather than made wider or narrower."""
    abi = abi_version() if abi is None else abi
    fs, net = plan(abi, no_network)
    libc = _libc()
    attr = attr_bytes(abi, fs, net)
    ruleset = libc.syscall(SYS_CREATE, attr, len(attr), 0)
    if ruleset < 0:
        raise ConfineRefused("unavailable")
    try:
        for paths, access in ((read_paths, READ_RIGHTS & fs), (write_paths, write_rights(abi) & fs)):
            for p in paths:
                try:
                    fd = os.open(p, os.O_PATH | os.O_CLOEXEC)
                except OSError:
                    raise ConfineRefused("profile") from None
                try:
                    rule = rule_bytes(access if os.path.isdir(p) else access & ~(FS_READ_DIR | FS_REMOVE_DIR | FS_MAKE_CHAR | FS_MAKE_DIR
                                                                               | FS_MAKE_REG | FS_MAKE_SOCK | FS_MAKE_FIFO
                                                                               | FS_MAKE_BLOCK | FS_MAKE_SYM | FS_REMOVE_FILE | FS_REFER),
                                      fd)
                    if libc.syscall(SYS_ADD, ruleset, RULE_PATH_BENEATH, rule, 0) != 0:
                        raise ConfineRefused("profile")
                finally:
                    os.close(fd)
        if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
            raise ConfineRefused("unavailable")
        if libc.syscall(SYS_RESTRICT, ruleset, 0) != 0:
            raise ConfineRefused("unavailable")
    finally:
        os.close(ruleset)
    return abi


def argv(read_paths, write_paths, command, no_network: bool = False) -> list:
    """The one argument list that runs `command` confined. The supervisor runs it with its own process start, never a shell."""
    out = [sys.executable, os.path.abspath(__file__)]  # by path, not `-m`: it imports only the standard library, so it needs no PYTHONPATH
    for p in read_paths:
        out += ["--read", str(p)]
    for p in write_paths:
        out += ["--write", str(p)]
    if no_network:
        out.append("--no-network")
    return out + ["--"] + [str(c) for c in command]


STEPS = {
    "unavailable": "set `enforcement: cooperative` for this agent with an `until` date, at your terminal, or run on a Linux kernel with Landlock",
    "kernel": "run on a kernel with Landlock network rules (6.7 or later), or allow the network by setting cooperative at your terminal",
    "profile": "fix the allow list: every listed path must exist, and the work folder must not hold the umwayi root",
    "platform": "run on Linux, or set `enforcement: cooperative` for this agent with an `until` date, at your terminal",
}

SYSTEM_READ = ("/usr", "/lib", "/lib64", "/bin", "/sbin", "/etc", "/opt", "/proc", "/dev", "/sys")


def _real(p) -> str:
    return os.path.realpath(p)


def _inside(child: str, parent: str) -> bool:
    return child == parent or child.startswith(parent.rstrip("/") + "/")


def run_paths(command: str, workdir: str, root: str, tmp: str, home: str | None, python: str, source: str,
              config_dir: str | None = None) -> tuple:
    """(read paths, write paths) for one helper run, the paths that exist, sorted. Read and execute: the system folders, the folders
    of the command and of the Python that runs the hook, the umwayi source (the hook is there). Write: the work folder, a private
    temporary folder (given to the helper as TMPDIR; /tmp itself is not listed, so the broker's folder there is not reachable), and
    the helper's own config (`~/.claude`, `~/.claude.json`, or CLAUDE_CONFIG_DIR). Landlock can not take a path out of a listed
    tree, so a work folder that holds the umwayi root is refused (`profile`): the logbook and the guard files would be writable."""
    if platform_is_not_linux():
        raise ConfineRefused("platform")
    work, rt = _real(workdir), _real(root)
    if _inside(rt, work):
        raise ConfineRefused("profile")
    reads = set(SYSTEM_READ)
    for exe in (command, python):
        real = _real(exe)
        reads |= {os.path.dirname(real), os.path.dirname(os.path.dirname(real))}
    reads |= {_real(sys.prefix), _real(sys.base_prefix), _real(source)}
    writes = {work, _real(tmp)}
    if home:
        writes |= {_real(os.path.join(home, ".claude")), _real(os.path.join(home, ".claude.json"))}
    if config_dir:
        writes.add(_real(config_dir))
    reads = {p for p in reads if p != "/" and os.path.exists(p)}
    writes = {p for p in writes if os.path.exists(p)}
    return sorted(reads), sorted(writes)


def platform_is_not_linux() -> bool:
    return not sys.platform.startswith("linux")


def refusal(reason: str) -> str:
    return f"refused: not confined ({reason}). Allowed next: {STEPS[reason]}."


def parse(args: list):
    """(read paths, write paths, no_network, command) from the fixed shape, or None."""
    read, write, no_net, i = [], [], False, 0
    while i < len(args) and args[i] != "--":
        flag = args[i]
        if flag == "--no-network":
            no_net, i = True, i + 1
        elif flag in ("--read", "--write") and i + 1 < len(args) and args[i + 1] != "--" and os.path.isabs(args[i + 1]):
            (read if flag == "--read" else write).append(args[i + 1])
            i += 2
        else:
            return None
    command = args[i + 1:]
    if i >= len(args) or not command or not os.path.isabs(command[0]):
        return None
    return read, write, no_net, command


def main(args=None) -> int:
    parsed = parse(list(sys.argv[1:] if args is None else args))
    if parsed is None:
        sys.stderr.write("umwayi.confine: usage: --read PATH ... --write PATH ... [--no-network] -- /absolute/command args\n")
        return EXIT_USAGE
    read, write, no_net, command = parsed
    if not os.path.isfile(command[0]) or not os.access(command[0], os.X_OK):
        sys.stderr.write(refusal("profile") + "\n")
        return EXIT_REFUSED
    try:
        apply(read, write, no_net)
    except ConfineRefused as e:
        sys.stderr.write(refusal(e.reason) + "\n")
        return EXIT_REFUSED
    try:
        pid = os.posix_spawn(command[0], command, dict(os.environ))  # the child inherits the restriction; this program stays as its parent
    except OSError:
        sys.stderr.write(refusal("profile") + "\n")
        return EXIT_REFUSED
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda s, _f, pid=pid: _forward(pid, s))
    while True:
        try:
            _, status = os.waitpid(pid, 0)
            break
        except InterruptedError:
            continue
    return os.waitstatus_to_exitcode(status) if os.waitstatus_to_exitcode(status) >= 0 else 128 - os.waitstatus_to_exitcode(status)


def _forward(pid: int, sig: int) -> None:
    try:
        os.kill(pid, sig)
    except OSError:
        pass


if __name__ == "__main__":
    sys.exit(main())
