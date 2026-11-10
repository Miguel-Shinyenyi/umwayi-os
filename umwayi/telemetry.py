"""Budget governor, task B.6: the OTLP/HTTP JSON receiver for one Claude Code run (B.R2).

A standard library ThreadingHTTPServer on 127.0.0.1, a free port, for one run only. It accepts only
POST /v1/metrics and POST /v1/logs from a loopback peer, with the exact run header (compared in constant time),
a Content-Length of at most 1 MB (16 MB per run in all) and Content-Type application/json. Anything else is
answered 401, 404, 411, 413 or 415 and never read. A body is parsed, the counts are taken from the named
paths only, and it is dropped:

    claude_code.cost.usage          (USD, a sum)                     -> metric micros
    claude_code.token.usage         (tokens by type and model)       -> metric tokens
    the claude_code.api_request event (cost_usd_micros, the four token counts, model) -> event micros, requests

Nothing else of a body is read, kept or logged: no prompt, no response, no tool detail. A number is an integer
from 0 to 10^12 (for cost.usage also a finite double, made micros rounded up); anything else marks the run
invalid, which stops it (exit 2) and settles the full reservation. A report the receiver had to refuse after the
run header matched (too big, no length, not JSON) marks it invalid too: part of the cost would be missing.

This is the only umwayi module with network code (tests/test_system.py allows exactly this one import). http.server is
imported only when a receiver starts, so importing umwayi, the hook path and every other command load no network
module. The receiver binds 127.0.0.1 only.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import math
import os
import re
import threading
import time
from collections import Counter

from umwayi.units import MAX_NUMBER, model_word

LOOPBACK = "127.0.0.1"  # the only address a receiver binds

HEADER = "x-umwayi-run"
PATHS = ("/v1/metrics", "/v1/logs")
MAX_BODY = 1 << 20  # bytes per body
MAX_RUN = 16 << 20  # bytes per run, all bodies together
SECRET_BYTES = 16  # the run header: a fresh secrets.token_hex of this many bytes per run (B.R2.2)
MAX_MODELS = 10  # distinct model names kept for the settle entry; more are counted as `other`
READ_TIMEOUT = 5.0  # seconds for one read of a request
REQUEST_DEADLINE = 10.0  # seconds for a whole request, however slowly it trickles in (S-Q6)
MAX_HANDLERS = 16  # requests handled at once; more are answered 503 and closed at once (S-Q7)
BUSY = b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
COST_METRIC = "claude_code.cost.usage"
TOKEN_METRIC = "claude_code.token.usage"
METRIC_TYPES = {"input": "input", "output": "output", "cacheRead": "cache_read", "cacheCreation": "cache_creation"}
EVENT_TOKENS = {"input_tokens": "input", "output_tokens": "output", "cache_read_tokens": "cache_read",
                "cache_creation_tokens": "cache_creation"}
EVENT_KEYS = ("event.name", "model", "cost_usd_micros", "cost_usd", *EVENT_TOKENS)


def telemetry_env(port: int, secret: str) -> dict:
    """The environment umwayi sets for a Claude Code start (B.R2.2). Every other OTEL_* name is removed first."""
    return {
        "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
        "OTEL_METRICS_EXPORTER": "otlp",
        "OTEL_LOGS_EXPORTER": "otlp",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
        "OTEL_EXPORTER_OTLP_ENDPOINT": f"http://127.0.0.1:{int(port)}",
        "OTEL_EXPORTER_OTLP_HEADERS": f"{HEADER}={secret}",
        "OTEL_METRIC_EXPORT_INTERVAL": "5000",
        "OTEL_LOGS_EXPORT_INTERVAL": "5000",
        "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE": "delta",
        "OTEL_LOG_USER_PROMPTS": "0",
        "OTEL_LOG_ASSISTANT_RESPONSES": "0",
        "OTEL_LOG_TOOL_DETAILS": "0",
        "OTEL_LOG_RAW_API_BODIES": "0",
        "OTEL_TRACES_EXPORTER": "none",
    }


TELEMETRY_NAMES = tuple(telemetry_env(0, "x"))
# Removed from every Claude Code environment before TELEMETRY_ENV is added, so no export goes elsewhere.
REMOVED_EXACT = ("BETA_TRACING_ENDPOINT", "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA", "CLAUDE_CODE_ENABLE_TELEMETRY")


def removed(name: str) -> bool:
    return name.startswith("OTEL_") or name in REMOVED_EXACT


class Invalid(Exception):
    """A number or a shape umwayi will not count. The text is fixed and names no value."""


def _number(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_NUMBER:
        raise Invalid("a count was not an integer from 0 to 10^12")
    return value


def _usd_to_micros(value) -> int:
    """US dollars (a JSON whole number or a finite double, never below 0) to micros, rounded up. A negative number
    is invalid on every path, so no report can subtract from a run."""
    if isinstance(value, bool):
        raise Invalid("a cost was not a number")
    if isinstance(value, int):
        if value < 0:
            raise Invalid("a cost was not a non-negative finite number")
        micros = value * 1_000_000
    elif isinstance(value, float) and math.isfinite(value) and value >= 0:
        micros = math.ceil(round(value * 1_000_000, 6))
    else:
        raise Invalid("a cost was not a non-negative finite number")
    if micros > MAX_NUMBER:
        raise Invalid("a cost was above 10^12 micros")
    return micros


def _list(value) -> list:
    if value is None:
        return []
    if not isinstance(value, list):
        raise Invalid("a report did not have the OTLP JSON shape")
    return value


def _dict(value) -> dict:
    if not isinstance(value, dict):
        raise Invalid("a report did not have the OTLP JSON shape")
    return value


def _attrs(items, keys) -> dict:
    """Only the named attribute keys, as {key: the OTLP AnyValue mapping}. Every other attribute is skipped unread."""
    out = {}
    for a in _list(items):
        a = _dict(a)
        k = a.get("key")
        if isinstance(k, str) and k in keys:
            out[k] = _dict(a.get("value"))
    return out


def _string(v: dict | None):
    return v.get("stringValue") if isinstance(v, dict) else None


def _int_value(v: dict) -> int:
    if set(v) != {"intValue"}:
        raise Invalid("a count was not an integer from 0 to 10^12")
    return _number(v["intValue"])


class Totals:
    """The counts of one run, folded from every accepted body. Integers only; thread safe."""

    def __init__(self):
        self.lock = threading.Lock()
        self.requests = 0
        self.event_micros = 0
        self.metric_micros = 0
        self.metric_seen = False
        self.event_tokens = Counter()  # (model, type) -> count
        self.metric_tokens = Counter()
        self.models: list = []
        self.invalid: str | None = None
        self.refused = Counter()  # HTTP status -> count
        self.accepted = 0
        self.bytes = 0
        self.active = 0  # requests being handled now

    def _model(self, name) -> str:
        word = model_word(name)
        if word not in self.models:
            if len(self.models) >= MAX_MODELS:
                word = "other"
            if word not in self.models:
                self.models.append(word)
        return word

    def fold_metrics(self, body) -> None:
        cost, tokens, seen, models = 0, Counter(), False, []
        for rm in _list(_dict(body).get("resourceMetrics")):
            for sm in _list(_dict(rm).get("scopeMetrics")):
                for m in _list(_dict(sm).get("metrics")):
                    m = _dict(m)
                    name = m.get("name")
                    if name not in (COST_METRIC, TOKEN_METRIC):
                        continue
                    data = m.get("sum") if "sum" in m else m.get("gauge")
                    for dp in _list(_dict(data).get("dataPoints")):
                        dp = _dict(dp)
                        attrs = _attrs(dp.get("attributes"), ("type", "model"))
                        model = _string(attrs.get("model"))
                        if name == COST_METRIC:
                            if "asDouble" in dp:
                                cost += _usd_to_micros(dp["asDouble"])
                            elif "asInt" in dp:
                                cost += _usd_to_micros(_number(dp["asInt"]))
                            else:
                                raise Invalid("a cost data point had no value")
                            seen = True
                        else:
                            if "asInt" not in dp:
                                raise Invalid("a count was not an integer from 0 to 10^12")
                            t = METRIC_TYPES.get(_string(attrs.get("type")))
                            n = _number(dp["asInt"])
                            tokens[(model, t or "other")] += n
                        if model is not None:
                            models.append(model)
        with self.lock:
            self.metric_micros += cost
            self.metric_seen = self.metric_seen or seen
            for (model, t), n in tokens.items():
                self.metric_tokens[(self._model(model), t)] += n
            for model in models:
                self._model(model)
            self._check_total()

    def fold_logs(self, body) -> None:
        requests, cost, tokens, models = 0, 0, Counter(), []
        for rl in _list(_dict(body).get("resourceLogs")):
            for sl in _list(_dict(rl).get("scopeLogs")):
                for rec in _list(_dict(sl).get("logRecords")):
                    rec = _dict(rec)
                    attrs = _attrs(rec.get("attributes"), EVENT_KEYS)
                    body_name = _string(rec.get("body")) if isinstance(rec.get("body"), dict) else None
                    if _string(attrs.get("event.name")) != "api_request" and body_name != "claude_code.api_request":
                        continue  # any other event (a prompt, a tool result) is skipped unread
                    requests += 1
                    if "cost_usd_micros" in attrs:
                        cost += _int_value(attrs["cost_usd_micros"])
                    elif "cost_usd" in attrs:
                        v = attrs["cost_usd"]
                        cost += _usd_to_micros(v.get("doubleValue", v.get("intValue")))
                    else:
                        raise Invalid("an api_request event had no cost")
                    model = _string(attrs.get("model"))
                    for key, t in EVENT_TOKENS.items():
                        if key in attrs:
                            tokens[(model, t)] += _int_value(attrs[key])
                    models.append(model)
        with self.lock:
            self.requests += requests
            self.event_micros += cost
            for (model, t), n in tokens.items():
                self.event_tokens[(self._model(model), t)] += n
            for model in models:
                self._model(model)
            self._check_total()

    def _check_total(self) -> None:
        if max(self.event_micros, self.metric_micros) > MAX_NUMBER:
            self.invalid = self.invalid or "the total was above 10^12 micros"

    def mark_invalid(self, why: str) -> None:
        with self.lock:
            self.invalid = self.invalid or why

    def report(self) -> dict:
        """A plain copy for units.reading(): numbers and model words only."""
        with self.lock:
            tokens = self.event_tokens if self.requests else self.metric_tokens
            return {"requests": self.requests, "event_micros": self.event_micros, "metric_micros": self.metric_micros,
                    "metric_seen": self.metric_seen, "tokens": dict(tokens),
                    "by_type": {t: sum(n for (_m, tt), n in tokens.items() if tt == t)
                                for t in ("input", "output", "cache_read", "cache_creation")},
                    "models": list(self.models), "invalid": self.invalid, "accepted": self.accepted,
                    "refused": dict(self.refused)}


_CLASSES = None


def _classes():
    """(server class, handler class), made on first use, so http.server is imported only when a receiver starts."""
    global _CLASSES
    if _CLASSES is not None:
        return _CLASSES
    import socket  # the receiver's own: the whole-request deadline shuts a connection down (S-Q6)
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # the one network import of umwayi

    class _Handler(BaseHTTPRequestHandler):
        server_version = "umwayi"
        sys_version = ""
        timeout = READ_TIMEOUT

        def log_message(self, *_args):  # never print a request line, a header or a peer
            pass

        def setup(self):
            super().setup()
            # S-Q6: a request that trickles in one byte at a time passes every 5 s read; cut the whole request here.
            # Cut before its run header matched, it is nobody's report; after, the read fails and the run is invalid.
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

        def _answer(self, code: int) -> None:
            if code != 200:
                with self.server.totals.lock:
                    self.server.totals.refused[code] += 1
            self.close_connection = True
            try:
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", "2")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(b"{}")
            except OSError:
                pass

        def _refuse_other(self):
            self._enter()
            try:
                self._answer(404)
            finally:
                self._leave()

        do_GET = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _refuse_other

        def _enter(self):
            with self.server.totals.lock:
                self.server.totals.active += 1

        def _leave(self):
            with self.server.totals.lock:
                self.server.totals.active -= 1

        def do_POST(self):
            self._enter()
            try:
                self._post()
            finally:
                self._leave()

        def _post(self):
            totals: Totals = self.server.totals
            try:
                loopback = ipaddress.ip_address(self.client_address[0]).is_loopback
            except ValueError:
                loopback = False
            if not loopback:
                return self._answer(401)
            if self.path not in PATHS:
                return self._answer(404)
            given = self.headers.get_all(HEADER) or []
            if len(given) != 1 or not hmac.compare_digest(given[0].encode("utf-8", "replace"), self.server.secret):
                return self._answer(401)  # missing, wrong, or given more than once
            # from here on the report is the agent's own: a refusal means part of its cost is missing
            lengths = self.headers.get_all("Content-Length") or []
            length = lengths[0] if len(lengths) == 1 else None
            if not lengths or (length is not None and (not length.isdigit() or len(length) > 12)):
                totals.mark_invalid("a report came without a Content-Length")
                return self._answer(411)
            if len(lengths) != 1:
                totals.mark_invalid("a report gave its Content-Length more than once")
                return self._answer(400)
            if self.headers.get("Transfer-Encoding") is not None:
                totals.mark_invalid("a report used a Transfer-Encoding")
                return self._answer(400)
            n = int(length)
            if n > MAX_BODY:
                totals.mark_invalid("a report was larger than 1 MB")
                return self._answer(413)
            with totals.lock:
                over = totals.bytes + n > MAX_RUN
                if not over:
                    totals.bytes += n
            if over:
                totals.mark_invalid("the reports of the run were larger than 16 MB in all")
                return self._answer(413)
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            encoding = (self.headers.get("Content-Encoding") or "identity").strip().lower()
            if ctype != "application/json" or encoding != "identity":
                totals.mark_invalid("a report was not plain JSON")
                return self._answer(415)
            try:
                raw = self.rfile.read(n)
            except OSError:
                totals.mark_invalid("a report could not be read")
                return self._answer(400)
            if len(raw) != n:
                totals.mark_invalid("a report was shorter than its Content-Length")
                return self._answer(400)
            try:
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError, RecursionError):
                totals.mark_invalid("a report was not JSON")
                return self._answer(400)
            finally:
                del raw
            if self.server.capture is not None:
                self.server.capture.write(self.path, body)
            try:
                if self.path == "/v1/metrics":
                    totals.fold_metrics(body)
                else:
                    totals.fold_logs(body)
            except Invalid as e:
                totals.mark_invalid(str(e))
                return self._answer(400)
            except RecursionError:
                totals.mark_invalid("a report did not have the OTLP JSON shape")
                return self._answer(400)
            finally:
                del body
            with totals.lock:
                totals.accepted += 1
            return self._answer(200)


    class _Server(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = False

        def process_request(self, request, client_address):
            """S-Q7: at most MAX_HANDLERS requests at once. One more is answered 503 and closed at once, here in the
            accepting thread, so no thread is started for it."""
            if not self.slots.acquire(blocking=False):
                with self.totals.lock:
                    self.totals.refused[503] += 1
                try:
                    request.settimeout(0.5)
                    request.sendall(BUSY)
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


CAPTURE_ENV = "UMWAYI_TELEMETRY_CAPTURE"  # B.10: the owner's one capture of a real export, names and shapes only
MAX_CAPTURE_LINES = 200
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9._]{0,63}$")
_EVENT = re.compile(r"^claude_code\.[a-z_.]{1,60}$")
_NAME_KEYS = ("key", "name")  # their values are field or metric names, kept when they look like names


def shape(value, under: str | None = None):
    """The shape of a report: every mapping key, every attribute key and every metric or event name that looks like a
    name, and the type of every other value. Never a value: no number, no text, no model name, no prompt."""
    if isinstance(value, dict):
        return {k if _NAME.match(str(k)) else "<key>": shape(v, k) for k, v in value.items()}
    if isinstance(value, list):
        out = []
        for v in value:
            s = shape(v)
            if s not in out:
                out.append(s)
        return out
    if isinstance(value, bool):
        return "<bool>"
    if isinstance(value, int):
        return "<int>"
    if isinstance(value, float):
        return "<float>"
    if isinstance(value, str):
        if under in _NAME_KEYS and _NAME.match(value):
            return value
        if under == "stringValue" and _EVENT.match(value):
            return value
        return "<string>"
    return "<null>" if value is None else "<other>"


class Capture:
    """B.10: one JSON line per new shape to a new file (mode 0600, never overwritten). Names and types only."""

    def __init__(self, path: str):
        if not os.path.isabs(path):
            raise OSError("the capture file must be an absolute path")
        self.fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        self.seen: set = set()
        self.lock = threading.Lock()

    def write(self, path: str, body) -> None:
        line = json.dumps({"path": path, "shape": shape(body)}, sort_keys=True)
        with self.lock:
            if line in self.seen or len(self.seen) >= MAX_CAPTURE_LINES:
                return
            self.seen.add(line)
            os.write(self.fd, (line + "\n").encode("utf-8"))

    def close(self) -> None:
        try:
            os.close(self.fd)
        except OSError:
            pass


class Receiver:
    """The receiver of one run. start() returns the port; stop() after the agent is stopped, on every way out."""

    def __init__(self, secret: str, capture: str | None = None):
        self.secret = secret
        self.totals = Totals()
        self.server = None
        self.thread = None
        self.capture_path = capture
        self.capture = None

    def start(self) -> int:
        server_class, handler_class = _classes()
        self.capture = Capture(self.capture_path) if self.capture_path else None
        self.server = server_class((LOOPBACK, 0), handler_class)
        self.server.totals = self.totals
        self.server.slots = threading.BoundedSemaphore(MAX_HANDLERS)
        self.server.capture = self.capture
        self.server.secret = self.secret.encode("ascii")
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.1},
                                       name="umwayi-telemetry", daemon=True)
        self.thread.start()
        return self.server.server_address[1]

    def drain(self, grace: float) -> None:
        """Wait, at most grace seconds, until no report is being received."""
        end = time.monotonic() + grace
        while time.monotonic() < end:
            with self.totals.lock:
                if self.totals.active == 0:
                    return
            time.sleep(0.05)

    def stop(self) -> None:
        if self.capture is not None:
            self.capture.close()
        if self.server is None:
            return
        try:
            self.server.shutdown()
            self.server.server_close()
        except OSError:
            pass
        self.server = None
