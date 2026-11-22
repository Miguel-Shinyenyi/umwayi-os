"""W78 step 1B follow-up (W78c): a real owner terminal for the tests, from the standard library `pty` module only.

`umwayi queue answer` and `umwayi enforce set cooperative` run only at the owner's terminal: standard input and standard
output must both be terminals (`umwayi.goal._is_terminal`). A test that answers a queue row therefore gives the command a
real pseudo-terminal, never a mock of the check:

  * `owner_terminal()`: for a test that calls `umwayi.cli.main` in its own process. While the block runs, `sys.stdin`
    and `sys.stdout` are the two ends of the slave side of a new pseudo-terminal, set to raw mode. Anything written to
    `sys.stdout` is read and dropped by a thread, so a write never blocks.
  * `run_at_terminal(argv, ...)`: for a test that starts `python -m umwayi` as a child process. The child's standard
    input and output are the slave side; its output is read from the master side and returned as `stdout`, with
    `stderr` on a pipe as before. The result is a `subprocess.CompletedProcess`, like `subprocess.run`. Its `umask`
    is passed to the child as `subprocess.Popen` does (-1 leaves the umask of the test process).
  * `needs_terminal(argv)`: True when the arguments run `queue answer`, the one command the tests move onto it.

Linux and macOS only (pty), like the rest of umwayi.
"""
import contextlib
import os
import pty
import subprocess
import sys
import threading
import tty


def needs_terminal(argv) -> bool:
    args = [str(a) for a in argv]
    return any(args[i:i + 2] == ["queue", "answer"] for i in range(len(args) - 1))


def _drain(fd, sink):
    while True:
        try:
            data = os.read(fd, 65536)
        except OSError:  # EIO on Linux when the last slave end is closed
            return
        if not data:
            return
        sink.append(data)


@contextlib.contextmanager
def owner_terminal():
    master, slave = pty.openpty()
    tty.setraw(slave)
    fin = os.fdopen(os.dup(slave), "r", encoding="utf-8")
    fout = os.fdopen(os.dup(slave), "w", encoding="utf-8")
    os.close(slave)
    sink = []
    reader = threading.Thread(target=_drain, args=(master, sink), daemon=True)
    reader.start()
    old = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = fin, fout
    try:
        yield
    finally:
        sys.stdin, sys.stdout = old
        for f in (fout, fin):
            try:
                f.close()
            except OSError:
                pass
        reader.join(5)
        os.close(master)


def run_at_terminal(argv, *, cwd=None, env=None, timeout=120, input_text=None, umask=-1):
    master, slave = pty.openpty()
    tty.setraw(slave)
    sink = []
    try:
        proc = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=subprocess.PIPE, cwd=cwd, env=env, umask=umask)
    finally:
        os.close(slave)
    reader = threading.Thread(target=_drain, args=(master, sink), daemon=True)
    reader.start()
    try:
        if input_text:
            os.write(master, input_text.encode("utf-8"))
        _out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        _out, err = proc.communicate()
        raise
    finally:
        reader.join(5)
        os.close(master)
    stdout = b"".join(sink).decode("utf-8", "replace")
    return subprocess.CompletedProcess(argv, proc.returncode, stdout, err.decode("utf-8", "replace"))


def maybe_terminal(argv):
    """`owner_terminal()` when the arguments run `queue answer`, else a block that changes nothing."""
    return owner_terminal() if needs_terminal(argv) else contextlib.nullcontext()


def run(argv, *, capture_output=True, text=True, env=None, cwd=None, timeout=120, input=None, umask=-1, **kw):
    """A drop-in for `subprocess.run(argv, capture_output=True, text=True, ...)` in the test helpers that start umwayi:
    the child gets a real terminal when it runs `queue answer`, and pipes as before otherwise."""
    if not needs_terminal(argv):
        return subprocess.run(argv, capture_output=capture_output, text=text, env=env, cwd=cwd, timeout=timeout,
                              input=input, umask=umask, **kw)
    return run_at_terminal(argv, cwd=cwd, env=env, timeout=timeout, input_text=input, umask=umask)
