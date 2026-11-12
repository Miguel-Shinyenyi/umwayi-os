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
import queue
import re
import secrets
import signal
import sys
import threading
import time
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

from umwayi import agents, budget, fsutil, kill, logbook, rules, runlock, servegate, servetoken, taskqueue, view
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
MAX_ROWS = 500  # rows of queue.list; beyond that the response says `more`
REQUEST_LINE = re.compile(r"(GET|POST|DELETE|[A-Z]{1,16}) (\S+) (HTTP/1\.[01])\r\n")  # the gate judges the target

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


# ----------------------------------------------------------------------------------------- one request


@dataclass(frozen=True)
class Ctx:
    """What the entry of a request needs: its id, the token's id, the route (None before one matched), the method, the
    start on the monotonic clock and the date."""
    rid: str
    tid: str
    route: object
    method: str
    started: float
    today: str


class _Job:
    """A piece of work a handler thread hands to the main thread."""

    def __init__(self, fn):
        self.fn = fn
        self.result = None
        self.error = None
        self.done = threading.Event()
        self.started = threading.Event()
        self.lock = threading.Lock()
        self.cancelled = False


_BUSY = object()  # what _in_main gives back when the work was not started in time


def _code_of(word: str) -> int:
    return WORDS[word][1] if word in WORDS else servegate.WORD_CODE[word]


_WORD_OF_CODE = {0: "done", 1: "refused", 2: "error", 3: "ask", 64: "usage"}
# the exit code the command line gives when a command raises UmwayiError (W6.R7.4): 1 for the queue, kill and logbook
_ERROR_CODE = {"agents.list": 2, "agents.check": 2, "budget.status": 2}


def _declared_length(facts) -> int:
    for name, value in facts.headers:
        if name.lower() == "content-length":
            return int(value)
    return 0


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
        self.pump = None  # set by the server: the queue the main thread takes work from (see _in_main)
        self.closing = False

    # ------------------------------------------------------------------ the main thread

    def _in_main(self, fn, wait: bool = True, limit=None):
        """Run `fn` on the main thread. A logbook write holds the termination signals off while it runs, and a handler
        can only be swapped in the main thread (logbook._held_off), so the handler threads of the server hand all the
        work that may write the logbook to the main thread of `umwayi serve`, which runs it one at a time. With no pump
        (the tests, or a caller that already is the main thread) it runs here. `limit` is how long work may wait for
        its turn (a write waits 5 seconds, then it is `busy`); None waits as long as the server runs."""
        if self.pump is None or threading.current_thread() is threading.main_thread():
            return fn()
        job = _Job(fn)
        self.pump.put(job)
        if not wait:
            return None
        if limit is not None and not job.started.wait(limit):
            with job.lock:
                if not job.started.is_set():
                    job.cancelled = True
                    return _BUSY
        while not job.done.wait(1.0):
            if self.closing:
                raise OSError("the server is stopping")
        if job.error is not None:
            raise job.error
        return job.result

    def pump_once(self, timeout: float) -> bool:
        """Run one piece of work from a handler thread. Called in a loop by the main thread of `umwayi serve`."""
        try:
            job = self.pump.get(timeout=timeout)
        except queue.Empty:
            return False
        with job.lock:
            if job.cancelled:
                return True
            job.started.set()
        try:
            job.result = job.fn()
        except (Exception, KeyboardInterrupt) as e:
            job.error = e
        finally:
            job.done.set()
        return True

    # ------------------------------------------------------------------ the election clock

    def _newest_logbook_date(self):
        """The newest date in the logbook, looked up again only when the file changed (a stat per request)."""
        try:
            st = os.stat(self.root / logbook.LOGBOOK_NAME)
        except OSError:
            return None
        key = (st.st_mtime_ns, st.st_size, st.st_ino)
        if key != self._log_key:
            self._log_date = logbook.newest_date(self.root)
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
            if verdict.authed and record is not None:
                # a valid token, turned away after the token check (origin, route, length, type): one entry
                self._in_main(lambda: self._log_gate_refusal(verdict, facts, record, started), wait=False)
            else:
                self._count(verdict.word)
            self._after_request()
            return gate_response(verdict)
        if verdict.route == "page":
            return self.page_response()
        route = servegate.route_by_id(verdict.route)
        raw = read_body(_declared_length(facts)) if route.method == "POST" else b""  # read only after the gate said Allow
        limit = self.lock_wait if route.cls in ("write", "run") else None
        response = self._in_main(lambda: self.run_pipeline(verdict, facts, raw, record, started), limit=limit)
        if response is _BUSY:
            self._count("busy")
            return json_response("busy", None, False)
        self._after_request()
        return response

    def _log_gate_refusal(self, verdict, facts, record, started) -> None:
        if self.degraded:
            self._count(verdict.word)
            return
        ctx = Ctx(_new_request_id(), record["id"], verdict.route, facts.method, started, self._today())
        self._write(ctx, verdict.word, "not read", "not run", False, gate=True)

    def _after_request(self) -> None:
        if self.pump is None:  # with a pump the main thread flushes the summary in its own loop
            self.flush_summary()

    def page_response(self) -> Response:
        data, _why = read_page(self.page_path)
        if data is None:
            return json_response("page", None, False)
        return Response(200, _headers("text/html; charset=utf-8", len(data), (("Content-Security-Policy", PAGE_CSP),)),
                        data)

    # ------------------------------------------------------------------ the pipeline (W6.R7)

    def run_pipeline(self, verdict, facts, raw_body, record=None, started=None) -> Response:
        """The steps of W6.R7 for a request the gate allowed, in order, stopping at the first that refuses: the request
        id, the body, the write lock, the kill switch, the rules check, the command, the request entry. It cannot be
        entered with a refusal."""
        if not isinstance(verdict, servegate.Allow):
            raise TypeError("the pipeline is entered only with an Allow from the gate")
        route = servegate.route_by_id(verdict.route)
        started = self._clock() if started is None else started
        ctx = Ctx(_new_request_id(), record["id"] if record else "T-00000000", route, facts.method, started,
                  self._today())
        if self.degraded and route.id != "kill.on":
            if route.id == "status":  # fixed words, no entry, no rules check
                code, data = HANDLERS["status"](self, {}, ctx.today)
                return json_response("done", ctx.rid, False, data, ok=True)
            if not self._recovered(ctx.today):
                return json_response("logbook", ctx.rid, False)
        params = dict(verdict.params)
        if route.method == "POST":
            body = servegate.parse_body(route, raw_body)
            if isinstance(body, servegate.Refuse):
                return self._finish(ctx, "body", "not read", "not run", False)
            params.update(body)
        locked = route.cls in ("write", "run")  # one write at a time (W6.R7.2)
        if locked and not self.write_lock.acquire(timeout=self.lock_wait):
            return self._finish(ctx, "busy", "not read", "not run", False)
        try:
            return self._steps(ctx, route, params)
        finally:
            if locked:
                self.write_lock.release()

    def _steps(self, ctx: Ctx, route, params: dict) -> Response:
        ks = kill.state(self.root)  # the function the agents read it with
        stopped = route.stopped and kill.stopped(ks)
        if route.skips_rules:
            answer_text = "skipped"  # only kill.on: an emergency stop does not wait for a rule
            exit_code = 0
        else:
            action = json.dumps({"type": "serve_request", "route": route.id, "class": route.cls, "platform": "web"})
            decision, logged = rules.check_and_log(
                action, self.root / RULES_FILE, self.root, ctx.today, log=True, kill_state=ks,
                stop_reason=kill.reason(ks) if stopped else None)
            answer_text, exit_code = decision.answer, decision.exit_code
            if not logged:  # an answer that was not logged is not given
                return self._finish(ctx, "logbook", ks, answer_text, False)
            if stopped:
                return self._finish(ctx, "kill", ks, answer_text, False)
            if exit_code == 2:
                return self._finish(ctx, "rules", ks, answer_text, False)
            if exit_code != 0:  # Ask me first (or anything else that is not a Yes): the owner is asked in the queue
                try:
                    taskqueue.add_once(self.root, "decision", f"The web page asks first: may it do {route.id}?", "",
                                       ctx.today)
                except UmwayiError:
                    pass
                return self._finish(ctx, "ask", ks, answer_text, False)
        try:
            code, data = HANDLERS[route.id](self, params, ctx.today)
        except UsageError:
            code, data = 64, None
        except UmwayiError:
            code, data = _ERROR_CODE.get(route.id, 1), None
        except (Exception, KeyboardInterrupt) as e:
            _report(e)
            code, data = 2, None
        word = _WORD_OF_CODE.get(code, "error")
        return self._finish(ctx, word, ks, answer_text, True, data if code == 0 else None,
                            changed=route.cls in ("write", "run") and code == 0)

    def _finish(self, ctx: Ctx, word: str, kill_text: str, rules_text: str, ran: bool, data=None,
                changed: bool = False) -> Response:
        """Write the request entry and build the response. An entry that cannot be written is not reported as done."""
        if not self._write(ctx, word, kill_text, rules_text, ran):
            return json_response("logbook", ctx.rid, False, {"changed": True} if changed else None)
        self.served += 1
        return json_response(word, ctx.rid, True, data, ok=word == "done")

    def _write(self, ctx: Ctx, word: str, kill_text: str, rules_text: str, ran: bool, gate: bool = False) -> bool:
        """One entry for a request that carried a valid token (W6.R13.1). False, and the degraded state, when it fails."""
        outcome = "done" if word == "done" else f"refused ({word})"
        ms = int(max(0.0, self._clock() - ctx.started) * 1000)
        route = ctx.route.id if hasattr(ctx.route, "id") else (ctx.route or "no route")
        try:
            logbook.append(self.root, logbook.Entry(
                ctx.today, "umwayi serve",
                f"Request {ctx.rid}: {ctx.method} {route}, {outcome} (exit {_code_of(word)}), {ms} ms",
                f"Token {ctx.tid} valid. " + ("The gate refused the request." if gate else "Host and Origin exact.")
                + f" Kill switch {kill_text}. Rules check {rules_text}.",
                "The body, the headers and the token were not recorded." + ("" if ran else " The command was not run.")))
        except Exception:
            self.degraded = True
            return False
        return True

    def _recovered(self, today: str) -> bool:
        """Leave the degraded state when the logbook can be written again, with one entry that says so."""
        try:
            logbook.check_writable(self.root, today)
            logbook.append(self.root, logbook.Entry(
                today, "umwayi serve", "The logbook can be written again; the degraded state ended.",
                "A test write passed the same checks as an append.", "No request was recorded by this entry."))
        except Exception:
            return False
        self.degraded = False
        return True

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


def _new_request_id() -> str:
    return "R-" + secrets.token_hex(4)


def _report(e: BaseException) -> None:
    """Only the type name goes to the server's own stderr: an exception text may hold a path or a file's text."""
    try:
        sys.stderr.write(f"umwayi serve: a request stopped with an unexpected error ({type(e).__name__}).\n")
    except Exception:
        pass


# -------------------------------------------------------------------------------------------- the handlers
#
# Each handler is a few lines: it reads parameters the gate and `parse_body` already checked, calls the core function
# the command line calls, and returns (the exit code of the command, the data of the response). No handler holds a
# rule, a path or a file format of its own (W6.R1.1). A response is a subset of what the command prints (W6.R8.2).


def _h_status(b: Backend, params: dict, today: str) -> tuple:
    rec = servetoken.read_record(b.root)
    token = None
    if rec is not None:
        token = {"id": rec["id"], "created": rec["created"], "expires": rec["expires"],
                 "days_left": servetoken.days_left(rec, today)}
    return 0, {"kill_switch": kill.state(b.root), "token": token, "degraded": b.degraded}


def _h_kill_on(b: Backend, params: dict, today: str) -> tuple:
    result = kill.turn_on(b.root, today, params.get("reason"))
    return result.code, {"kill_switch": "on"}


def _h_snapshot(b: Backend, params: dict, today: str) -> tuple:
    entries, chain_length = logbook.read_checked_chain(b.root)  # the tamper check, as `view snapshot` makes it
    data = view.gather(b.root, today, entries, chain_length)
    if not view.valid(data):
        raise UmwayiError("serve: the snapshot did not have the shape of schema 1")
    return 0, data


def _h_queue_list(b: Backend, params: dict, today: str) -> tuple:
    rows = taskqueue.list_rows(b.root, params["status"], params["kind"])
    shown = [{"id": r.id, "kind": r.kind, "status": r.status, "answered": r.answered, "title": r.title,
              "recommendation": r.recommendation, "answer": r.answer} for r in rows[:MAX_ROWS]]
    return 0, {"rows": shown, "more": len(rows) > MAX_ROWS}


def _h_logbook_verify(b: Backend, params: dict, today: str) -> tuple:
    report = logbook.verify(b.root, None)
    if report.problems:
        return 1, None  # the names of the problems stay with the command line
    _entries, chain_length = logbook.read_checked_chain(b.root)
    return 0, {"entries": report.entries, "chain_length": chain_length, "problems": 0}


def _h_budget_status(b: Backend, params: dict, today: str) -> tuple:
    code, lines = budget.status(b.root, today, today)
    return code, {"lines": lines}


def _h_agents_list(b: Backend, params: dict, today: str) -> tuple:
    found = agents.load(b.root, None)
    return 0, {"agents": [{"name": a.name, "platform": a.platform, "transport": a.transport} for a in found]}


_CHECK_LINE = re.compile(r"(ok|no|not run): ([A-Za-z0-9 ._-]{1,60}): ")


def _h_agents_check(b: Backend, params: dict, today: str) -> tuple:
    result = agents.check_agent(b.root, params["name"], None, None)
    checks = []
    for line in result.lines:  # the name and the mark of each check; the detail may hold a path, so it stays out
        m = _CHECK_LINE.match(line)
        if m:
            checks.append({"name": m.group(2), "ok": {"ok": True, "no": False}.get(m.group(1))})
    return result.code, {"gated": result.code == 0, "checks": checks}


def _h_queue_add(b: Backend, params: dict, today: str) -> tuple:
    row, added = taskqueue.add_row(b.root, params["kind"], params["title"], params.get("recommendation", ""), today,
                                   params.get("if_not_open", False))
    return 0, {"id": row.id, "added": added}


def _h_queue_answer(b: Backend, params: dict, today: str) -> tuple:
    row = taskqueue.answer(b.root, params["id"], params["answer"], today, revisit_if=params.get("revisit_if"))
    return 0, {"id": row.id, "answered": row.answered}


def _h_queue_close(b: Backend, params: dict, today: str) -> tuple:
    row = taskqueue.close(b.root, params["id"], today)
    return 0, {"id": row.id, "status": row.status}


HANDLERS = {"status": _h_status, "snapshot": _h_snapshot, "queue.list": _h_queue_list,
            "logbook.verify": _h_logbook_verify, "budget.status": _h_budget_status, "agents.list": _h_agents_list,
            "agents.check": _h_agents_check, "queue.add": _h_queue_add, "queue.answer": _h_queue_answer,
            "queue.close": _h_queue_close, "kill.on": _h_kill_on}


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
            with self.count_lock:
                self.active += 1
            try:
                super().process_request(request, client_address)
            except BaseException:
                self._finished()
                raise

        def process_request_thread(self, request, client_address):
            try:
                super().process_request_thread(request, client_address)
            finally:
                self._finished()

        def _finished(self):
            with self.count_lock:
                self.active -= 1
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
        self.server.active = 0
        self.server.count_lock = threading.Lock()
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

    def begin_stop(self) -> None:
        """Stop accepting. `shutdown` waits for the accept loop to end, so it runs in a thread of its own and the main
        thread goes on running the work the handlers still wait for."""
        threading.Thread(target=self.server.shutdown, name="umwayi-serve-stop", daemon=True).start()

    def idle(self) -> bool:
        with self.server.count_lock:
            return self.server.active == 0

    def close(self) -> None:
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
    backend.pump = queue.Queue()  # the handler threads hand their work to this thread (Backend._in_main)
    stopping, deadline = False, 0.0
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
        while True:
            backend.pump_once(0.2)
            backend.flush_summary()
            if stop.is_set():
                if not stopping:
                    stopping, deadline = True, time.monotonic() + 5.0
                    running.begin_stop()
                # keep running the work of requests in flight until they are done, for at most 5 seconds
                if running.idle() or time.monotonic() > deadline:
                    break
    finally:
        for s, h in previous.items():
            signal.signal(s, h)
        backend.closing = True
        if not stopping:
            running.begin_stop()
        running.close()
    backend.pump = None
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
