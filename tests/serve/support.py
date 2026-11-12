"""Shared helpers for the tests of `umwayi serve`: lazy imports, a fixed root, rules, a token, a child process.

The modules under test are imported on first use (`servegate.decide` imports `umwayi.servegate` then), so that before
the code exists each test fails by itself, with ModuleNotFoundError, instead of one import error hiding all of them.
"""

import base64
import hashlib
import importlib
import io
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATE = "2026-11-12"
PORT = 8765

# Fixed tokens. Both have the shape of a real one (umt1_ and 43 characters of base64url) and hold upper and lower case
# letters, digits, - and _, so a case change or a character change always gives a different string.
TOKEN = "umt1_u8jzPde0IgxLd6GncfBAepfJBd0Kh8oOOL8dKLzd-oc"
TOKEN2 = "umt1_J2isAjIhKtJ0RlgLKOmxgJTeKdNnFRIBXuDL7DxtpYl"
TOKEN_ID = "T-91ab02cd"
SENTINEL = "SENTINEL-4f7a-do-not-leak"


class Lazy:
    """A module that is imported when an attribute is read."""

    def __init__(self, name):
        self._name = name

    def __getattr__(self, attr):
        return getattr(importlib.import_module(self._name), attr)


servegate = Lazy("umwayi.servegate")
servetoken = Lazy("umwayi.servetoken")
serve = Lazy("umwayi.serve")


def digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def record(token: str = TOKEN, created: str = DATE, expires: str = "2026-12-12", tid: str = TOKEN_ID) -> dict:
    return {"schema": 1, "id": tid, "sha256": digest(token), "created": created, "expires": expires}


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


# --------------------------------------------------------------------------------------------- a root

QUEUE = ("# Queue\n\n| id | kind | title | status | recommendation | answer | answered |\n"
         "| --- | --- | --- | --- | --- | --- | --- |\n")

RULES_ALL_YES = """\
- id: serve-yes
  title: The web page may do what the command line may
  text: Every request of the web page is allowed (tests only).
  verdict: yes
  matchers:
    - field: type
      op: equals
      values: [serve_request]
"""


def rules_text(read="yes", write="yes", run="yes") -> str:
    """A rules.yaml with one rule per class of request (the example of W6.R17.4 with the verdicts chosen)."""
    parts = []
    for cls, verdict in (("read", read), ("write", write), ("run", run)):
        if verdict is None:
            continue
        parts.append(f"- id: serve-{cls}\n  title: Web {cls}\n  text: Web requests of class {cls}.\n"
                     f"  verdict: {verdict}\n  matchers:\n    - field: type\n      op: equals\n"
                     f"      values: [serve_request]\n    - field: class\n      op: equals\n      values: [{cls}]\n")
    return "".join(parts)


def make_root(tmp: Path, rules: str | None = None, queue: bool = True, token: str | None = TOKEN,
              expires: str = "2026-12-12") -> Path:
    """A fresh root: umwayi.json, rules.yaml, queue.md and the token record (the digest only)."""
    root = Path(tmp)
    (root / "umwayi.json").write_text(json.dumps({"memory_dir": "memory", "private_paths": []}))
    (root / "memory").mkdir(exist_ok=True)
    (root / "memory" / "master.md").write_text("me\n")
    (root / "rules.yaml").write_text(rules if rules is not None else rules_text())
    if queue:
        (root / "queue.md").write_text(QUEUE)
    (root / ".umwayi").mkdir(exist_ok=True)
    if token is not None:
        p = root / ".umwayi" / "serve.token"
        p.write_text(json.dumps(record(token, expires=expires), indent=2) + "\n")
        os.chmod(p, 0o600)
    return root


def snapshot_tree(root: Path, skip=(".umwayi/logbook.lock", ".umwayi/serve.lock", ".umwayi/run.lock")) -> dict:
    """Every file under root: relative path -> bytes (folders as None). Used to prove that a refusal changed nothing."""
    out = {}
    root = Path(root)
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if rel in skip:
            continue
        out[rel] = None if p.is_dir() else p.read_bytes()
    return out


def write_agents(root: Path, workdir: Path, name: str = "helper") -> Path:
    """An agents.yaml with one Kiro agent whose command and folder carry a sentinel (they are paths: never in a response)."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    path = Path(root) / "agents.yaml"
    path.write_text(f"agents:\n  - name: {name}\n    platform: kiro\n    command: kiro-cli\n    workdir: {workdir}\n")
    return path


LOGBOOK_FILES = ("LOGBOOK.md", ".umwayi/logbook.sha256", ".umwayi/logbook.pending")


def state_files(root: Path) -> dict:
    """Every file of the root except the logbook and its record: what a refusal must leave byte for byte as it was."""
    return {k: v for k, v in snapshot_tree(root).items() if k not in LOGBOOK_FILES}


def logbook_entries(root: Path) -> list:
    from umwayi import logbook
    return logbook.read_checked(Path(root))


def make_logbook(root: Path) -> None:
    """Start a logbook (one entry), so that the tamper check has a record to compare."""
    from umwayi import logbook
    logbook.append(Path(root), logbook.Entry(DATE, "tests", "start", "start", "start"))


class TtyOut(io.StringIO):
    """A stand-in for a terminal: the token commands print only to a terminal."""

    def isatty(self):
        return True


# ------------------------------------------------------------------------------- a real server process


class Server:
    """`python -m umwayi serve --port 0` as a child process, with HOME in a temporary folder. Use as a context manager."""

    def __init__(self, root: Path, extra=(), env=None, home=None):
        self.root = Path(root)
        self.extra = list(extra)
        self.env = dict(os.environ)
        self.env["PYTHONPATH"] = str(REPO)
        self.env["HOME"] = str(home or tempfile.mkdtemp(prefix="umwayi-home-"))
        self.env["PYTHONUNBUFFERED"] = "1"
        self.env.update(env or {})
        self.proc = None
        self.port = None
        self.first_lines = []

    def __enter__(self):
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "umwayi", "--root", str(self.root), "serve", "--port", "0", *self.extra],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env, cwd=str(REPO))
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            line = self.proc.stdout.readline().decode("utf-8", "replace")
            if not line:
                break
            self.first_lines.append(line.rstrip("\n"))
            m = re.match(r"^Listening on http://127\.0\.0\.1:(\d+)", line)
            if m:
                self.port = int(m.group(1))
                return self
        self.stop()
        raise AssertionError("the server did not start: " + repr(self.first_lines) + self.proc.stderr.read().decode())

    def __exit__(self, *exc):
        self.stop()

    def stop(self, sig=None):
        import signal
        if getattr(self, "_stopped", False):
            return self.proc.returncode
        self._stopped = True
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(sig or signal.SIGTERM)
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        out = b""
        err = b""
        if self.proc:
            try:
                out = self.proc.stdout.read()
                err = self.proc.stderr.read()
            except Exception:
                pass
        self.stdout_rest = out.decode("utf-8", "replace")
        self.stderr = err.decode("utf-8", "replace")
        return self.proc.returncode if self.proc else None

    def raw(self, data: bytes, read_timeout: float = 12.0, shutdown_write: bool = False) -> bytes:
        """Send raw bytes on a new connection and return everything the server answers until it closes."""
        s = socket.create_connection(("127.0.0.1", self.port), timeout=read_timeout)
        try:
            s.sendall(data)
            if shutdown_write:
                s.shutdown(socket.SHUT_WR)
            chunks = []
            while True:
                try:
                    c = s.recv(65536)
                except (socket.timeout, ConnectionError):
                    break
                if not c:
                    break
                chunks.append(c)
            return b"".join(chunks)
        finally:
            s.close()

    def request(self, method, path, token=TOKEN, body=None, headers=None, origin=True, host=None):
        """One request with the headers a same-origin fetch of the page sends. Returns (status, headers dict, json)."""
        h = {"Host": host or f"127.0.0.1:{self.port}"}
        if token is not None:
            h["Authorization"] = f"Bearer {token}"
        data = b""
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
            h["Content-Length"] = str(len(data))
        if origin and method != "GET":
            h["Origin"] = f"http://127.0.0.1:{self.port}"
        h.update(headers or {})
        head = f"{method} {path} HTTP/1.1\r\n" + "".join(f"{k}: {v}\r\n" for k, v in h.items()) + "\r\n"
        return parse_response(self.raw(head.encode() + data))


def parse_response(raw: bytes):
    """(status, headers, body bytes) of one HTTP response read to the end of the connection."""
    head, _, body = raw.partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    if not lines or not lines[0].startswith("HTTP/1."):
        return 0, {}, raw
    status = int(lines[0].split()[1])
    headers = {}
    for ln in lines[1:]:
        k, _, v = ln.partition(":")
        headers.setdefault(k.strip().lower(), []).append(v.strip())
    return status, headers, body


def envelope(body: bytes) -> dict:
    return json.loads(body.decode("utf-8"))


class Clock:
    """A monotonic clock the test moves by hand. Every request of InProc moves it one second, so no rate limit trips."""

    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class Reply:
    def __init__(self, status, headers, body):
        self.status, self.headers, self.raw = status, headers, body
        try:
            self.env = json.loads(body.decode("utf-8")) if body.startswith(b"{") else None
        except ValueError:
            self.env = None

    @property
    def word(self):
        return self.env and self.env["word"]

    @property
    def code(self):
        return self.env and self.env["code"]

    @property
    def ok(self):
        return self.env and self.env["ok"]

    @property
    def data(self):
        return self.env and self.env.get("data")

    def __repr__(self):
        return f"Reply({self.status}, {self.raw[:200]!r})"


class InProc:
    """The backend without a socket: Facts go in, a Response comes out. Same code path as the live server."""

    def __init__(self, root, today=DATE, port=PORT, page=None, tick=1.0, **backend_kw):
        self.root, self.today, self.port, self.tick = Path(root), today, port, tick
        self.clock = Clock()
        self.body_reads = []
        self.backend = serve.Backend(self.root, port, page=page, today=lambda: self.today, clock=self.clock, **backend_kw)

    def request(self, method, path, body=None, token=TOKEN, extra=(), drop=(), raw=None, origin=True):
        data = raw if raw is not None else (json.dumps({} if body is None else body).encode() if method == "POST" else b"")
        headers = [("Host", f"127.0.0.1:{self.port}"), ("Accept", "*/*")]
        if token is not None and path != "/":
            headers.append(("Authorization", f"Bearer {token}"))
        if method == "POST":
            if origin:
                headers.append(("Origin", f"http://127.0.0.1:{self.port}"))
            headers += [("Content-Type", "application/json"), ("Content-Length", str(len(data)))]
        headers = [h for h in headers if h[0] not in drop] + list(extra)
        facts = servegate.Facts("HTTP/1.1", method, path, tuple(headers), "127.0.0.1", "127.0.0.1", self.port, "local")

        def read_body(n):
            self.body_reads.append(n)
            return data[:n]

        self.clock.t += self.tick
        r = self.backend.handle(facts, read_body)
        return Reply(r.status, {k.lower(): v for k, v in r.headers}, r.body)

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.request("POST", path, body, **kw)


class RootCase(unittest.TestCase):
    """A test with a fresh root in a temporary folder."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        (self.tmp / "root").mkdir()
        self.root = make_root(self.tmp / "root")
