"""W78 step 5 (5a): the enforcement broker. A small separate process that answers a confined helper's hook and writes the log.

Design: docs/enforcement-broker-design.md. Built alone: nothing starts it yet. No supervisor starts it, no hook asks it and no
confinement exists, so no default changes. It is the piece a confined helper will need, because a confined hook can not write
the logbook and a helper that could would be able to edit it.

  * One process per run, not the supervisor and not confined. Started with a fixed argument list (`argv`): `--root`, `--table`,
    `--sock`. The process start is the supervisor's (this module starts no program).
    The root never comes from a request or from the environment.
  * One Unix socket in a private folder made by the supervisor (way 2 of the design). Each hook makes its own connection.
  * The run table is a file the supervisor writes: run id, agent, platform, task, mode, ended. A request from a run that is not
    in it, or that has ended, is refused. The platform of a check comes from the table, never from the request.
  * Two requests only: `check` (the same rules check as `umwayi check`, run here, never a shell, the entry written here with the
    logbook's lock and chain checks) and `answer_status` (read only). `log` is not built (open question 3 of the design).
  * The answer holds a verdict word and a rule id. Never file content, rule text or an echo of the request.
  * Limits: one JSON line of 4 KiB, a 10 second deadline, 16 connections at once, 20 requests a second for a run.
  * The kill switch on or unreadable: every check is No. A logbook that cannot be written or whose chain is broken: No.
  * No answer is No: `ask` gives No when the broker cannot be reached.
  * It writes only the logbook family (through `logbook.append`) and queue rows (through `umwayi.taskqueue`). It never writes a
    guard file or goal state. `WRITES` below is the whole list, and a test compares it with the code.
  * Exit codes: 0 asked to stop; 2 could not start, ended on an error or its parent ended; 64 bad arguments. Never 1.

Standard library only. `socket` is imported inside the functions that need it (the third exception to product rule 5, approved
2026-11-22, named by file in tests/test_system.py).
"""
from __future__ import annotations

import json
import os
import re
import signal
import stat
import sys
import threading
import time
from collections import deque
from pathlib import Path

from umwayi import kill, logbook, rules, taskqueue
from umwayi.errors import UmwayiError

SOURCE = "umwayi broker"
MAX_REQUEST_BYTES = 4096
DEADLINE_S = 10.0
MAX_CONNECTIONS = 16
RATE_PER_S = 20
MAX_TABLE_BYTES = 64 * 1024
MAX_REFUSAL_ENTRIES = 20  # refusals logged per minute, the rest are counted: a flood must not fill the logbook
WRITES = ("the logbook family through logbook.append", "queue rows through taskqueue.add_once")  # B10: the whole list
REQUEST_TYPES = ("check", "answer_status")
# the words of a refusal: fixed, never taken from a request
WHYS = ("bad_request", "too_big", "unknown_type", "unknown_run", "run_ended", "rate", "busy", "kill_switch", "log_failed",
        "table", "no_answer", "timeout")
EXIT_OK, EXIT_NO, EXIT_USAGE = 0, 2, 64

RUN_ID = re.compile(r"^[0-9a-f]{16}$")
_PLAIN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_RULE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_SOCK_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


class TableError(UmwayiError):
    pass


def read_table(path) -> dict:
    """{run id: {agent, platform, task, mode, ended}} from the run table file, strict. Raises TableError."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        raise TableError("table") from None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_TABLE_BYTES:
            raise TableError("table")
        data = os.read(fd, MAX_TABLE_BYTES + 1)
    finally:
        os.close(fd)
    try:
        doc = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise TableError("table") from None
    runs = doc.get("runs") if isinstance(doc, dict) and doc.get("version") == 1 and set(doc) == {"version", "runs"} else None
    if not isinstance(runs, dict):
        raise TableError("table")
    for rid, row in runs.items():
        if not (isinstance(rid, str) and RUN_ID.match(rid) and isinstance(row, dict)
                and set(row) == {"agent", "platform", "task", "mode", "ended"}
                and all(isinstance(row[k], str) and _PLAIN.match(row[k]) for k in ("agent", "platform", "task", "mode"))
                and isinstance(row["ended"], bool)):
            raise TableError("table")
    return runs


def write_table(path, runs: dict) -> None:
    """The supervisor's side: write the run table atomically (a temporary file, then a rename), 0600."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    data = json.dumps({"version": 1, "runs": runs}, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def check_folder(folder) -> None:
    """The private run folder: a real folder of ours, mode 0700, no link. Raises TableError."""
    try:
        st = os.lstat(folder)
    except OSError:
        raise TableError("table") from None
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o700:
        raise TableError("table")


class Broker:
    """The state of one broker: the root, the table path, the limits. `handle` takes one request line and gives the answer."""

    def __init__(self, root, table):
        self.root, self.table = Path(root), table
        self.lock = threading.Lock()
        self.recent = {}  # run id -> deque of request times
        self.refused = {}  # why -> count
        self.logged_refusals = deque()
        self.conns = threading.BoundedSemaphore(MAX_CONNECTIONS)

    # ------------------------------------------------------------------ one request

    def handle(self, line: bytes) -> dict:
        if len(line) > MAX_REQUEST_BYTES:
            return self.refuse("too_big", None)
        try:
            req = json.loads(line.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return self.refuse("bad_request", None)
        if not isinstance(req, dict) or not isinstance(req.get("type"), str):
            return self.refuse("bad_request", None)
        rid = req.get("run")
        valid = rid if isinstance(rid, str) and RUN_ID.match(rid) else None
        if req["type"] not in REQUEST_TYPES:
            return self.refuse("unknown_type", valid)
        allowed = {"type", "run", "action"} if req["type"] == "check" else {"type", "run"}
        if set(req) != allowed or valid is None:  # a path, a command, a root or any other key is refused
            return self.refuse("bad_request", valid)
        try:
            row = read_table(self.table).get(valid)
        except TableError:
            return self.refuse("table", valid)
        if row is None:
            return self.refuse("unknown_run", valid)
        if row["ended"]:
            return self.refuse("run_ended", valid)
        if not self.within_rate(valid):
            return self.refuse("rate", valid)
        if req["type"] == "answer_status":
            return {"answer": self.status(valid), "rule": None}
        action = req["action"]
        if not isinstance(action, dict):
            return self.refuse("bad_request", valid)
        action = dict(action, platform=row["platform"])  # the table says the platform, not the request
        return self.check(valid, action)

    def within_rate(self, rid: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self.lock:
            q = self.recent.setdefault(rid, deque())
            while q and now - q[0] >= 1.0:
                q.popleft()
            if len(q) >= RATE_PER_S:
                return False
            q.append(now)
            return True

    # ------------------------------------------------------------------ check

    def check(self, rid: str, action: dict) -> dict:
        """The rules check of `umwayi check`, run in this process. The kill switch on or unreadable is No; the entry is written
        here, through the checked append. An entry that cannot be written (a lock held, a broken chain) is No."""
        st = kill.state(self.root)
        stop = kill.reason(st) if kill.stopped(st) else None
        try:
            decision, logged = rules.check_and_log(json.dumps(action, separators=(",", ":")), self.root / "rules.yaml", self.root,
                                                   rules.system_today(), kill_state=st, stop_reason=stop)
        except Exception:  # an unexpected error is No, never an exception out of a request
            return self.refuse("log_failed", rid)
        if not logged:
            return self.refuse("log_failed", rid, log=False)
        answer = decision.answer
        if stop is not None:
            answer = rules.NO
        if answer == rules.ASK:
            self.queue_row(rid, decision.action_type)
        rule = decision.rule_id if isinstance(decision.rule_id, str) and _RULE_ID.match(decision.rule_id) else None
        return {"answer": answer, "rule": rule}

    def queue_title(self, rid: str) -> str:
        return f"Ask me first in run {rid}"

    def queue_row(self, rid: str, action_type) -> None:
        """One queue row for an Ask me first, in fixed words: the run id and the action type (a plain word), nothing else."""
        kind = action_type if isinstance(action_type, str) and _PLAIN.match(action_type) else "unknown"
        try:
            taskqueue.add_once(self.root, "decision", self.queue_title(rid),
                               f"A helper of run {rid} asked for an action of type {kind} and the rules said Ask me first. "
                               "The call was refused. Add a Yes rule to rules.yaml if it should be allowed.", rules.system_today())
        except UmwayiError:
            pass  # the answer is still Ask me first; the row is the owner's list, not the gate

    def status(self, rid: str) -> str:
        """`open`, `answered` or `none`: the state of the newest queue row of this run. Never the answer text."""
        try:
            rows = [r for r in taskqueue.list_rows(self.root) if r.title == self.queue_title(rid)]
        except UmwayiError:
            return "none"
        if not rows:
            return "none"
        return "open" if rows[-1].status == "open" else "answered"

    # ------------------------------------------------------------------ a refusal

    def refuse(self, why: str, rid: str | None, log: bool = True) -> dict:
        """No, with a word from WHYS. Counted, and logged as one entry with the word and a valid run id, never the request."""
        assert why in WHYS
        with self.lock:
            self.refused[why] = self.refused.get(why, 0) + 1
            now = time.monotonic()
            while self.logged_refusals and now - self.logged_refusals[0] >= 60.0:
                self.logged_refusals.popleft()
            room = log and len(self.logged_refusals) < MAX_REFUSAL_ENTRIES
            if room:
                self.logged_refusals.append(now)
        if room:
            try:
                logbook.append(self.root, logbook.Entry(
                    rules.system_today(), SOURCE, f"Refused a request: {why}",
                    f"run {rid}" if rid else "no valid run id", "The request was not copied. Nothing was run for it."))
            except UmwayiError:
                pass
        return {"answer": rules.NO, "rule": None, "why": why}


# ----------------------------------------------------------------------------------------------- the process


def _read_line(conn, deadline: float) -> bytes | None:
    """One line of at most MAX_REQUEST_BYTES, read before the deadline however slowly it comes. None: too big or too slow."""
    import socket
    buf = b""
    while b"\n" not in buf:
        left = deadline - time.monotonic()
        if left <= 0:
            return None
        conn.settimeout(left)
        try:
            chunk = conn.recv(MAX_REQUEST_BYTES + 1 - len(buf))
        except (socket.timeout, OSError):
            return None
        if not chunk:
            return None
        buf += chunk
        if len(buf) > MAX_REQUEST_BYTES:
            return b"x" * (MAX_REQUEST_BYTES + 1)
    return buf.split(b"\n", 1)[0]


def _reader(broker: Broker, conn, work) -> None:
    """A thread per connection: read one line before the deadline, then hand it to the main thread. The logbook write must run in
    the main thread (umwayi/logbook.py), so every request is answered there, one at a time: one writer."""
    try:
        line = _read_line(conn, time.monotonic() + DEADLINE_S)
    except Exception:
        line = None
    work.put((conn, line))


def _answer(broker: Broker, conn, line) -> None:
    try:
        answer = broker.refuse("timeout", None) if line is None else broker.handle(line)
        conn.settimeout(2.0)
        conn.sendall((json.dumps(answer, separators=(",", ":")) + "\n").encode("utf-8"))
    except Exception:
        pass
    finally:
        try:
            conn.close()
        finally:
            broker.conns.release()


def _accept(srv, broker: Broker, work, stop: threading.Event) -> None:
    import socket
    while not stop.is_set():
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            continue
        except OSError:
            stop.set()
            return
        if not broker.conns.acquire(blocking=False):  # a 17th connection is told no and closed
            try:
                conn.sendall(b'{"answer":"No","rule":null,"why":"busy"}\n')
            except OSError:
                pass
            finally:
                conn.close()
            with broker.lock:
                broker.refused["busy"] = broker.refused.get("busy", 0) + 1
            continue
        threading.Thread(target=_reader, args=(broker, conn, work), daemon=True).start()


def serve(root, table, sock_path, parent: int | None = None, stop: threading.Event | None = None) -> int:
    """Listen on `sock_path` until stopped. Returns the exit code: 0 stopped, 2 an error or the parent ended. Must run in the main
    thread: it answers every request there."""
    import queue
    import socket
    sock_path = Path(sock_path)
    try:
        check_folder(sock_path.parent)
        if not _SOCK_NAME.match(sock_path.name):
            return EXIT_USAGE
        if os.path.lexists(sock_path):
            return EXIT_NO  # never replace a path: a planted file or link is an error
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(sock_path))
        os.chmod(sock_path, 0o600)
        srv.listen(MAX_CONNECTIONS)
        srv.settimeout(0.5)
    except (OSError, TableError):
        return EXIT_NO
    stop = stop or threading.Event()
    broker = Broker(root, table)
    work = queue.Queue()
    parent = os.getppid() if parent is None else parent
    code = EXIT_OK
    threading.Thread(target=_accept, args=(srv, broker, work, stop), daemon=True).start()
    try:
        while True:
            if os.getppid() != parent:  # the supervisor ended: the next run starts a new broker
                code = EXIT_NO
                break
            try:
                conn, line = work.get(timeout=0.25)
            except queue.Empty:
                if stop.is_set():
                    code = code or EXIT_OK
                    break
                continue
            _answer(broker, conn, line)
    finally:
        stop.set()
        srv.close()
        try:
            os.unlink(sock_path)
        except OSError:
            pass
    return code


def main(argv=None) -> int:
    """`python -m umwayi.broker --root R --table T --sock S`. Exactly these three, no other, and no environment variable."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 6 or args[0::2] != ["--root", "--table", "--sock"]:
        return EXIT_USAGE
    root, table, sock = (Path(a) for a in args[1::2])
    if not root.is_dir():
        return EXIT_USAGE
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    return serve(root, table, sock, stop=stop)


# ----------------------------------------------------------------------------------------------- the clients


def ask(sock_path, request: dict, timeout: float = DEADLINE_S) -> dict:
    """What a hook does: one connection, one request line, one answer line. No answer, an answer that is not the fixed shape, a
    refusal or a timeout is No. It never raises."""
    import socket
    no = {"answer": rules.NO, "rule": None, "why": "no_answer"}
    try:
        line = (json.dumps(request, separators=(",", ":")) + "\n").encode("utf-8")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(str(sock_path))
            s.sendall(line)
            buf = b""
            while b"\n" not in buf and len(buf) < 1024:
                chunk = s.recv(1024)
                if not chunk:
                    break
                buf += chunk
        got = json.loads(buf.split(b"\n", 1)[0].decode("utf-8"))
    except Exception:
        return no
    if not (isinstance(got, dict) and got.get("answer") in (rules.YES, rules.NO, rules.ASK, "open", "answered", "none")):
        return no
    return got


class Handle:
    """The supervisor's side: the broker process it started and the socket path."""

    def __init__(self, proc, sock_path):
        self.proc, self.sock_path = proc, Path(sock_path)

    def lost(self) -> bool:
        """True once the broker has ended. A supervisor that sees this stops the task: no answer is No."""
        return self.proc.poll() is not None

    def stop(self) -> int | None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except Exception:
                self.proc.kill()
                self.proc.wait()
        return self.proc.returncode


def argv(root, table, sock) -> list:
    """The one argument list that starts a broker. The supervisor runs it with its own process start (never a shell) and gives the
    child an environment of PATH, LANG and the import path only: nothing that names a root."""
    return [sys.executable, "-m", "umwayi.broker", "--root", str(root), "--table", str(table), "--sock", str(sock)]


def wait_for(handle: Handle, wait_s: float = 5.0) -> Handle:
    """Wait until the broker's socket is there. Raises TableError (reason `table`) when the process ends first, the socket does not
    appear, or the socket path was there before it started (a planted file or link is never replaced)."""
    end = time.monotonic() + wait_s
    while time.monotonic() < end:
        if handle.proc.poll() is not None:
            raise TableError("table")
        if os.path.exists(handle.sock_path):
            return handle
        time.sleep(0.02)
    handle.proc.kill()
    raise TableError("table")


if __name__ == "__main__":
    sys.exit(main())
