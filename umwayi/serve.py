"""`umwayi serve`: the local backend for the web page (workstream W6, requirements W6.R2, W6.R3, W6.R14, W6.R15).

The page may send the same request the command line would, to this server on the owner's own machine and to nothing
else (steering rule 10). The server binds the literal address 127.0.0.1 and nothing changes that: no flag, no setting,
no variable of the process's surroundings. A request meets the gate (`servegate.decide`, pure), the kill switch, the rules check and the
logbook, in that order, by calling the same functions the command line calls (W6.R7).

This module holds the shell (the strict reader, the handler class, the limits, the lock, the bind, the page, start and
stop) and the pipeline. `http.server` and `socket` are imported only inside `_classes`, the function that makes the
server, so importing any umwayi module still loads no network library (the guard tests allow exactly this).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import signal
import sys
import threading
import time
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

from umwayi import fsutil, kill, logbook, rules, runlock, servegate, servetoken
from umwayi.errors import UmwayiError, UsageError

LOOPBACK = "127.0.0.1"
LOCK_NAME = "serve.lock"
RULES_FILE = "rules.yaml"
MAX_HANDLERS = 16  # requests handled at once; the 17th is answered 503 at once (W6.R14.1)
READ_TIMEOUT = 5.0  # one socket read
REQUEST_DEADLINE = 10.0  # the whole request, so a trickle of bytes is cut too
LOCK_WAIT = 5.0  # a write waits this long for the one write lock
SUMMARY_SECONDS = 60.0
MAX_COUNT = 1_000_000  # a counter of the summary stops here
MAX_PAGE = 2_500_000
MAX_BUILD_JSON = 1 << 20
REQUEST_LINE = re.compile(r"(GET|POST|DELETE|[A-Z]{1,16}) (\S{1,512}) (HTTP/1\.[01])\r\n")

# the pipeline words (W6.R15.2): word -> (HTTP status, the exit code the command line would give)
WORDS = {"done": (200, 0), "refused": (409, 1), "usage": (400, 64), "error": (500, 2), "ask": (403, 3), "kill": (403, 3),
         "budget": (403, 3), "rules": (403, 2), "logbook": (500, 2), "busy": (503, 2), "page": (503, 2),
         "body": (400, 64)}
_REASON = {200: "OK", 400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found",
           405: "Method Not Allowed", 409: "Conflict", 411: "Length Required", 413: "Payload Too Large",
           415: "Unsupported Media Type", 429: "Too Many Requests", 500: "Internal Server Error",
           503: "Service Unavailable"}
PAGE_CSP = "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"


def _today() -> str:
    """The system clock, as `cli._today` reads it. A request cannot choose a date."""
    return date.today().isoformat()


# --------------------------------------------------------------------------------------------- responses


@dataclass(frozen=True)
class Response:
    status: int
    headers: tuple
    body: bytes


def _headers(content_type: str, length: int, extra=()) -> tuple:
    """The headers of every response (W6.R6.6). No cookie, and never an Access-Control header."""
    return (("Content-Type", content_type), ("Content-Length", str(length)), ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"), ("Referrer-Policy", "no-referrer"),
            ("Cross-Origin-Resource-Policy", "same-origin"), ("Cross-Origin-Opener-Policy", "same-origin"),
            ("Connection", "close"), ("Server", "umwayi")) + tuple(extra)


def envelope(word: str, request, logged: bool, data=None, ok: bool = False) -> bytes:
    """The JSON object every API response is (W6.R15.2). `data` only when ok, or the one `changed` note."""
    status, code = WORDS[word]
    obj = {"schema": 1, "ok": ok, "code": code, "word": word, "request": request, "logged": logged}
    if data is not None:
        obj["data"] = data
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def json_response(word: str, request, logged: bool, data=None, ok: bool = False) -> Response:
    body = envelope(word, request, logged, data, ok)
    return Response(WORDS[word][0], _headers("application/json; charset=utf-8", len(body)), body)


def gate_response(refuse) -> Response:
    """The response to a gate refusal: the same bytes for the same word, whatever the request was."""
    body = servegate.refusal_body(refuse.word)
    extra = (("Retry-After", str(refuse.retry_after)),) if refuse.status == 429 else ()
    return Response(refuse.status, _headers("application/json; charset=utf-8", len(body), extra), body)


# ------------------------------------------------------------------------------------------------ the page


def default_page() -> Path:
    """ui/dist/index.html beside the package, if it is there."""
    return Path(__file__).resolve().parent.parent / "ui" / "dist" / "index.html"


def _link_free(path: Path) -> bool:
    """Neither the file nor a folder above it inside the checkout is a link (W6.R2.3). A page outside the checkout is
    judged by the file and its own folder."""
    path = Path(os.path.abspath(path))
    if path.is_symlink() or path.parent.is_symlink():
        return False
    checkout = Path(__file__).resolve().parent.parent
    if checkout in path.parents:
        return not any(p.is_symlink() for p in path.parents if p != checkout and checkout in p.parents)
    return True


def read_page(path) -> tuple:
    """(the bytes, "") when `path` is a regular file of at most 2.5 MB whose SHA-256 equals the one in build.json beside
    it and nothing on the way is a link; otherwise (None, a short reason word). Read again for every request."""
    if path is None:
        return None, "missing"
    path = Path(path)
    try:
        if not _link_free(path):
            return None, "link"
        data = fsutil.read_regular(path, MAX_PAGE)
    except fsutil.TooBig:
        return None, "too big"
    except fsutil.NotRegular:
        return None, "not a file"
    except OSError:
        return None, "missing"
    try:
        build = fsutil.read_regular(path.parent / "build.json", MAX_BUILD_JSON).decode("utf-8")
        want = json.loads(build).get("page")
    except (OSError, ValueError, AttributeError):
        return None, "no build.json"
    if type(want) is not str or want != hashlib.sha256(data).hexdigest():
        return None, "changed"
    return data, ""


# ------------------------------------------------------------------------------------------------ the backend


class Backend:
    """Everything a request needs, without a socket: the gate's state, the summary counters, the degraded state and
    the pipeline. The server shell reads Facts off a connection and calls `handle`; the tests call it directly."""

    def __init__(self, root, port, page=None, today=None, clock=None, lock_wait=LOCK_WAIT):
        self.root = Path(root)
        self.port = port
        self.page_path = Path(page) if page is not None else default_page()
        self._today = today or _today
        self._clock = clock or time.monotonic
        self.lock_wait = lock_wait
        self.write_lock = threading.Lock()
        self.degraded = False
        self.served = 0
        self._state = servegate.State(None, "", 0.0)
        self._state_lock = threading.Lock()
        self._counts: dict = {}
        self._summary_lock = threading.Lock()
        self._last_flush = self._clock()
        self._log_key = None
        self._log_date = None

    # ------------------------------------------------------------------ the election clock

    def _newest_logbook_date(self):
        """The newest date in the logbook, read again only when the file changed (a stat, not a read, per request)."""
        try:
            st = os.stat(self.root / logbook.LOGBOOK_NAME)
        except OSError:
            return None
        key = (st.st_mtime_ns, st.st_size, st.st_ino)
        if key != self._log_key:
            try:
                dates = [e.date for e in logbook.read_checked(self.root) if logbook.real_date(e.date)]
                self._log_date = max(dates) if dates else None
            except Exception:  # a broken logbook: the request will fail closed at the rules check
                self._log_date = None
            self._log_key = key
        return self._log_date

    def election_date(self) -> str:
        """The latest of the date and the newest logbook date, so a clock set back does not revive an expired token."""
        days = [d for d in (self._today(), self._newest_logbook_date()) if d]
        return max(days)

    # ------------------------------------------------------------------ the summary of requests with no token

    def _count(self, word: str) -> None:
        with self._summary_lock:
            self._counts[word] = min(self._counts.get(word, 0) + 1, MAX_COUNT)

    def flush_summary(self, force: bool = False) -> None:
        """One entry for the refusals counted since the last one, at most once a minute (or when forced, at shutdown).
        The counts are kept when the entry cannot be written."""
        with self._summary_lock:
            now = self._clock()
            if not self._counts or (not force and now - self._last_flush < SUMMARY_SECONDS):
                return
            total = sum(self._counts.values())
            words = ", ".join(f"{w} {n}" for w, n in sorted(self._counts.items(), key=lambda kv: (-kv[1], kv[0])))
            noun = "request" if total == 1 else "requests"
            self._last_flush = now
            try:
                logbook.append(self.root, logbook.Entry(
                    self._today(), "umwayi serve",
                    f"Refused {total} {noun} before a token was checked or after the rate limit, in the last 60 "
                    f"seconds: {words}.",
                    "The count is from memory since the last summary. No request is named.",
                    "No address, header or body was recorded."))
            except Exception:
                return
            self._counts.clear()

    # ------------------------------------------------------------------ one request

    def handle(self, facts, read_body) -> Response:
        """Facts in, a Response out. `read_body(n)` is called only after the gate allowed the request."""
        try:
            return self._handle(facts, read_body)
        except (Exception, KeyboardInterrupt) as e:
            _report(e)
            return json_response("error", None, False)

    def _handle(self, facts, read_body) -> Response:
        started = self._clock()
        record = servetoken.read_record(self.root)
        with self._state_lock:
            state = replace(self._state, record=record, date=self.election_date(), mono=started)
            verdict, self._state = servegate.decide(facts, state)
        if isinstance(verdict, servegate.Refuse):
            self._count(verdict.word)
            self.flush_summary()
            return gate_response(verdict)
        if verdict.route == "page":
            return self.page_response()
        response = self.run_pipeline(verdict, facts, read_body)
        self.flush_summary()
        return response

    def page_response(self) -> Response:
        data, _why = read_page(self.page_path)
        if data is None:
            return json_response("page", None, False)
        return Response(200, _headers("text/html; charset=utf-8", len(data), (("Content-Security-Policy", PAGE_CSP),)),
                        data)

    def run_pipeline(self, verdict, facts, read_body) -> Response:
        """The steps of W6.R7 for a request the gate allowed. It cannot be entered with a refusal."""
        if not isinstance(verdict, servegate.Allow):
            raise TypeError("the pipeline is entered only with an Allow from the gate")
        return json_response("error", None, False)  # the pipeline is built in the next step (W6.5)

    def shutdown(self, word: str) -> bool:
        """The last summary and the stop entry. True when the stop entry was written."""
        self.flush_summary(force=True)
        try:
            logbook.append(self.root, logbook.Entry(
                self._today(), "umwayi serve", f"Stopped ({word}), {self.served} requests served, 0 chats stopped.",
                "Every request was finished or cut before this entry.", "The token and the requests were not recorded."))
        except Exception:
            return False
        return True


def _report(e: BaseException) -> None:
    """Only the type name goes to the server's own stderr: an exception text may hold a path or a file's text."""
    try:
        sys.stderr.write(f"umwayi serve: a request stopped with an unexpected error ({type(e).__name__}).\n")
    except Exception:
        pass


# --------------------------------------------------------------------------------------- the server shell


def _classes():
    """(server class, handler class), made on first use, so http.server and socket are imported only when a server
    starts (the guard tests allow exactly these imports in this module, inside this function)."""
    global _CLASSES
    if _CLASSES is not None:
        return _CLASSES
    import socket
    from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer

    class _Handler(BaseHTTPRequestHandler):
        server_version = "umwayi"
        sys_version = ""
        timeout = READ_TIMEOUT

        def log_message(self, *_args):  # never print a request line, a header or a peer
            pass

        def setup(self):
            super().setup()
            # a request that trickles in one byte at a time passes every 5 s read: cut the whole request at 10 s
            self._deadline = threading.Timer(REQUEST_DEADLINE, self._cut)
            self._deadline.daemon = True
            self._deadline.start()

        def _cut(self):
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        def finish(self):
            self._deadline.cancel()
            try:
                super().finish()
            except OSError:
                pass

        def _facts(self):
            """The request exactly as on the wire. The standard parser is not used: it accepts HTTP/0.9, folds and
            merges headers and hides duplicates. A line that is not exactly right becomes facts the gate refuses."""
            empty = servegate.Facts("", "", "", (), self.client_address[0], *self.connection.getsockname()[:2])
            line = self.rfile.readline(8193)
            m = REQUEST_LINE.fullmatch(line.decode("latin-1"))
            if not m:
                return empty
            headers = []
            while len(headers) < servegate.MAX_HEADERS + 1:
                raw = self.rfile.readline(servegate.MAX_HEADER_VALUE + 1 + 256)
                if raw == b"\r\n":
                    break
                if not raw.endswith(b"\r\n") or raw[:1] in (b" ", b"\t"):
                    headers.append(("", ""))  # a bare line feed, a line too long, a fold, or the end of the stream
                    break
                name, colon, value = raw[:-2].decode("latin-1").partition(":")
                headers.append((name if colon else "", value.strip(" \t")))
            host, port = self.connection.getsockname()[:2]
            return servegate.Facts(m.group(3), m.group(1), m.group(2), tuple(headers), self.client_address[0], host,
                                   port)

        def _read_body(self, n):
            return self.rfile.read(n)

        def handle_one_request(self):
            self.close_connection = True
            try:
                facts = self._facts()
                response = self.server.backend.handle(facts, self._read_body)
            except OSError:  # a timeout, a reset or an end of stream: nothing to answer
                return
            except Exception as e:
                _report(e)
                response = json_response("error", None, False)
            try:
                head = f"HTTP/1.1 {response.status} {_REASON.get(response.status, 'Error')}\r\n"
                head += "".join(f"{k}: {v}\r\n" for k, v in response.headers) + "\r\n"
                self.wfile.write(head.encode("latin-1") + response.body)
                self.wfile.flush()
            except OSError:
                pass

    class _Server(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = False  # a port in use is a refusal at start, not a shared port
        request_queue_size = MAX_HANDLERS

        def server_bind(self):
            # HTTPServer.server_bind asks the name service for the host's name; the server never connects out
            super(HTTPServer, self).server_bind()
            self.server_name = LOOPBACK
            self.server_port = self.socket.getsockname()[1]

        def process_request(self, request, client_address):
            """At most MAX_HANDLERS requests at once. One more is answered 503 and closed at once, here in the accepting
            thread, so no thread is started for it."""
            if not self.slots.acquire(blocking=False):
                body = envelope("busy", None, False)
                try:
                    request.settimeout(0.5)
                    request.sendall(b"HTTP/1.1 503 Service Unavailable\r\n"
                                    + "".join(f"{k}: {v}\r\n" for k, v in _headers(
                                        "application/json; charset=utf-8", len(body))).encode("latin-1")
                                    + b"\r\n" + body)
                except OSError:
                    pass
                self.shutdown_request(request)
                return
            try:
                super().process_request(request, client_address)
            except BaseException:
                self.slots.release()
                raise

        def process_request_thread(self, request, client_address):
            try:
                super().process_request_thread(request, client_address)
            finally:
                self.slots.release()

        def handle_error(self, request, client_address):  # never print a traceback with request content
            pass

    _CLASSES = (_Server, _Handler)
    return _CLASSES


_CLASSES = None


class Running:
    """A server that is bound and serving, in a thread of its own. `stop` ends it and waits for the requests in flight."""

    def __init__(self, backend: Backend, port: int):
        server_class, handler_class = _classes()
        self.backend = backend
        self.server = server_class((LOOPBACK, port), handler_class)
        self.server.backend = backend
        self.server.slots = threading.BoundedSemaphore(MAX_HANDLERS)
        host, bound = self.server.socket.getsockname()[:2]
        if host != LOOPBACK or (port and bound != port):  # read back what the socket really is (W6.R3.2)
            self.server.server_close()
            raise UmwayiError("serve: the socket is not bound to 127.0.0.1, so nothing was started")
        self.port = bound
        backend.port = bound
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.2},
                                       name="umwayi-serve", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        # wait for the requests in flight (at most 5 seconds), then close the socket
        deadline = time.monotonic() + 5.0
        taken = 0
        while taken < MAX_HANDLERS and time.monotonic() < deadline:
            if self.server.slots.acquire(timeout=max(0.0, deadline - time.monotonic())):
                taken += 1
            else:
                break
        self.server.server_close()
        self.thread.join(5.0)


# --------------------------------------------------------------------------------------- start and stop


def _check_root(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise UsageError("serve: the root is not a normal folder")


def run(root, port: int, page, out, err) -> int:
    """`umwayi serve`. 0 stopped by Ctrl-C or SIGTERM, 1 the logbook failed its tamper check (nothing started), 2 an
    unexpected error or a stop that could not be recorded, 64 usage or config; never 3. The arguments are checked first,
    then the root, the tamper check, the token, the lock and the bind (W6.R2.2)."""
    root = Path(root)
    try:
        if page is not None:
            p = Path(page)
            if not p.is_file():
                raise UsageError("serve: --page must name a file that exists")
        _check_root(root)
        try:
            logbook.read_checked_chain(root)  # the tamper check: a broken logbook starts nothing
        except UmwayiError as e:
            err.write(f"umwayi: serve: refused, the logbook failed its check ({str(e).rstrip('. ')}). Nothing was "
                      "started.\n")
            return 1
        backend = Backend(root, port, page)
        rec = servetoken.read_record(root)
        today = backend.election_date()
        if rec is None or not today < rec["expires"]:
            raise UsageError("serve: there is no valid token (none, or it has expired). Run 'umwayi serve token "
                             "create' or 'umwayi serve token rotate' in a terminal first.")
        with runlock.held(root, LOCK_NAME):
            return _serve(backend, rec, today, port, out, err)
    except UsageError as e:
        err.write(f"umwayi: error: {e}\n")
        return 64
    except runlock.RunLockBusy:
        err.write("umwayi: error: serve: another 'umwayi serve' holds the lock for this root. Nothing was started.\n")
        return 64
    except runlock.RunLockUnavailable as e:
        err.write(f"umwayi: error: serve: {e}. Nothing was started.\n")
        return 64


def _serve(backend: Backend, rec: dict, today: str, port: int, out, err) -> int:
    try:
        running = Running(backend, port)
    except OSError:
        raise UsageError(f"serve: port {port} cannot be bound on 127.0.0.1 (is it in use?). Nothing was started.") \
            from None
    except UmwayiError:
        err.write("umwayi: serve: the socket did not read back as 127.0.0.1. Nothing was started.\n")
        return 2
    page_ok = read_page(backend.page_path)
    page_text = "yes (SHA-256 matches build.json)" if page_ok[0] is not None else f"no ({page_ok[1]})"
    try:
        logbook.append(backend.root, logbook.Entry(
            today, "umwayi serve", f"Started on {LOOPBACK}:{running.port}.",
            f"The logbook chain was intact. Token {rec['id']} expires on {rec['expires']}. Page served: {page_text}.",
            "No request was served before this entry."))
    except UmwayiError as e:
        running.server.server_close()
        err.write(f"umwayi: serve: the start could not be logged ({str(e).rstrip('. ')}). Nothing was started.\n")
        return 2
    stop = threading.Event()
    reason = []

    def on_signal(signum, _frame):
        reason.append("sigint" if signum == signal.SIGINT else "sigterm")
        stop.set()

    previous = {s: signal.signal(s, on_signal) for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        running.start()
        out.write(f"Listening on http://{LOOPBACK}:{running.port}" + ("" if page_ok[0] is not None else " (page not served)")
                  + "\n")
        left = (_ordinal(rec["expires"]) - _ordinal(today))
        out.write(f"Token {rec['id']} expires on {rec['expires']} ({left} days left).\n")
        if left <= 7:
            out.write("The token runs out soon: run 'umwayi serve token rotate' in a terminal.\n")
        if not _has_serve_rule(backend.root):
            out.write("No rule matches a serve_request, so every request will get Ask me first; see "
                      "serve.rules.example.yaml.\n")
        out.flush()
        while not stop.wait(1.0):
            backend.flush_summary()
    finally:
        for s, h in previous.items():
            signal.signal(s, h)
        running.stop()
    return 0 if backend.shutdown(reason[0] if reason else "stopped") else 2


def _ordinal(day: str) -> int:
    return date.fromisoformat(day).toordinal()


def _has_serve_rule(root: Path) -> bool:
    """True when some rule matches a serve_request (the hint of W6.R15.5 is for the owner who has none)."""
    try:
        loaded = rules.load_rules(root / RULES_FILE)
    except UmwayiError:
        return False
    sample = {"type": "serve_request", "route": "queue.list", "class": "read", "platform": "web"}
    return any(rules.rule_matches(r, sample) for r in loaded)
