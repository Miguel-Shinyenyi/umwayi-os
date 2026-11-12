"""The request gate of `umwayi serve` (workstream W6, requirements W6.R5 and W6.R6).

One pure function, `decide(facts, state)`, answers "may this request even be looked at". It reads no file, no clock and
no network, writes nothing, and imports nothing that does (only hmac, hashlib, json, re and dataclasses; a test checks
the imports and the names used). The server shell reads the facts off the connection and the state off the token record,
the date and a monotonic clock, calls `decide`, and swaps the state it gets back in.

The checks run in the order of W6.R5.2 and the first one that fails decides:

     1 protocol (version, method)       7 token (and the throttle, and the bucket of all authenticated requests)
     2 peer (and channel)               8 Origin and fetch metadata
     3 headers                          9 route (and the query)
     4 Host                            10 body (length and type)
     5 target                          11 rate (the bucket of the route's class)
     6 the page (needs no token)

A caller without a valid token learns nothing about routes, methods or limits: checks 8 to 11 come after the token.
A refusal carries one fixed word and nothing from the request; the response bytes for a word are always the same.
`parse_body` is the second pure function: it turns the bytes of a body into parameters or a refusal.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass

LOOPBACK = "127.0.0.1"
CHANNELS = ("local",)  # a closed set of one (W6.R12.4): a relay would be a second member, decided after Dec 3

# the fixed words of a refusal (W6.R15.2) and the exit code the command line would give; `body` is a usage error
WORD_CODE = {"method": 2, "peer": 2, "header": 2, "host": 2, "target": 2, "token": 2, "origin": 2, "route": 2,
             "length": 2, "type": 2, "rate": 2, "body": 64, "error": 2}
GATE_WORDS = tuple(WORD_CODE)

MAX_HEADERS = 64
MAX_HEADER_VALUE = 4096
MAX_HEADER_BLOCK = 16 * 1024
MAX_TARGET = 512
MAX_QUERY_VALUE = 16
MAX_BODY_STRING = 4096
THROTTLE_FAILS = 5  # failed token checks ...
THROTTLE_WINDOW = 60.0  # ... within this many seconds lock out the failures until this long passes without one
# (rate per second, burst) of the bucket of all authenticated requests and of each class (W6.R14.2)
RATES = {"auth": (10.0, 30), "read": (5.0, 20), "write": (2.0, 6), "run": (1.0, 3)}

_NAME = re.compile(r"[A-Za-z0-9-]+")
_VALUE = re.compile(r"[\x20-\x7e]*")
_TARGET = re.compile(r"[\x21-\x7e]+")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_TOKEN = re.compile(r"umt1_[A-Za-z0-9_-]{43}")
_LENGTH = re.compile(r"[1-9][0-9]*")
_QUERY_VALUE = re.compile(r"[a-z0-9_-]{0,%d}" % MAX_QUERY_VALUE)
_ID = re.compile(r"Q-[0-9]{4,}")
_NAME_PARAM = re.compile(r"[a-z0-9_-]{1,40}")
_PARAM = {"id": _ID, "name": _NAME_PARAM}
_JSON_TYPES = ("application/json", "application/json; charset=utf-8")
_FORBIDDEN = frozenset({"transfer-encoding", "expect", "upgrade", "content-encoding", "te", "trailer"})
_SINGLE = ("host", "origin", "authorization", "content-length", "content-type", "sec-fetch-site", "sec-fetch-mode",
           "sec-fetch-dest")
_METHODS = ("GET", "POST", "DELETE")
_VERSIONS = ("HTTP/1.0", "HTTP/1.1")


# -------------------------------------------------------------------------------------------- the data


@dataclass(frozen=True)
class Facts:
    """What the server read off the connection, as it came. `headers` keeps every line, in order, duplicates included.
    `server` and `port` are the socket's own address, read from the socket and not from the request."""
    version: str
    method: str
    target: str
    headers: tuple
    peer: str
    server: str
    port: int
    channel: str = "local"


@dataclass(frozen=True)
class Bucket:
    tokens: float
    stamp: float


@dataclass(frozen=True)
class State:
    """What the gate is given besides the request. `record` is the token record as read for this request (or None),
    `date` the election clock date, `mono` a monotonic time in seconds. The rest is the gate's memory: a bucket of all
    authenticated requests and one for each class (None means full), the times of the newest failed token checks and
    the time until which failed tokens are locked out."""
    record: object
    date: str
    mono: float
    auth: object = None
    read: object = None
    write: object = None
    run: object = None
    fails: tuple = ()
    locked_until: float = 0.0


@dataclass(frozen=True)
class Allow:
    route: str
    params: dict
    body_cap: int


@dataclass(frozen=True)
class Refuse:
    """`authed` is True when the token was valid and a place was taken from the bucket of all authenticated requests:
    such a refusal is logged. Any other refusal is only counted. `route` is set when the route was already known."""
    status: int
    word: str
    authed: bool = False
    retry_after: int = 0
    route: object = None


@dataclass(frozen=True)
class Route:
    id: str
    method: str
    path: str  # with {id} and {name} for the parameters; the form of docs/serve.md
    cls: str  # page, read, write or run
    body_cap: int
    stopped: bool  # refused while the kill switch is on or unknown
    skips_rules: bool = False  # only kill.on: an emergency stop does not wait for a rule (W6-Q2)
    query: tuple = ()  # the keys of the query string the route lists
    fields: tuple = ()  # (name, "str" or "bool") of a body
    required: tuple = ()


# The closed table (W6.R8.1). Adding a route needs the owner's approval, a row in docs/serve.md and a test row.
ROUTES = (
    Route("page", "GET", "/", "page", 0, False),
    Route("status", "GET", "/v1/status", "read", 0, False),
    Route("snapshot", "GET", "/v1/snapshot", "read", 0, False),
    Route("queue.list", "GET", "/v1/queue", "read", 0, False, query=("status", "kind")),
    Route("logbook.verify", "GET", "/v1/logbook", "read", 0, False),
    Route("budget.status", "GET", "/v1/budget", "read", 0, False),
    Route("agents.list", "GET", "/v1/agents", "read", 0, False),
    Route("agents.check", "POST", "/v1/agents/{name}/check", "run", 64, True),
    Route("queue.add", "POST", "/v1/queue", "write", 4096, True,
          fields=(("kind", "str"), ("title", "str"), ("recommendation", "str"), ("if_not_open", "bool")),
          required=("kind", "title")),
    Route("queue.answer", "POST", "/v1/queue/{id}/answer", "write", 4096, True,
          fields=(("answer", "str"), ("revisit_if", "str")), required=("answer",)),
    Route("queue.close", "POST", "/v1/queue/{id}/close", "write", 64, True),
    Route("kill.on", "POST", "/v1/kill/on", "write", 512, False, skips_rules=True, fields=(("reason", "str"),)),
)
_BY_ID = {r.id: r for r in ROUTES}


def route_by_id(route_id: str) -> Route:
    return _BY_ID[route_id]


# --------------------------------------------------------------------------------------- the response


def refusal_body(word: str) -> bytes:
    """The bytes of the response to a gate refusal: the same for the same word, whatever the request was."""
    obj = {"schema": 1, "ok": False, "code": WORD_CODE[word], "word": word, "request": None, "logged": False}
    return json.dumps(obj, separators=(",", ":")).encode("ascii")


def digest_hex(token: str) -> str:
    """The SHA-256 of a token, as the record keeps it."""
    return hashlib.sha256(token.encode("ascii")).hexdigest()


# ------------------------------------------------------------------------------------------ the gate


def decide(facts, state):
    """(verdict, next state). Never raises: any exception inside is a refusal with the word `error`."""
    try:
        return _run_checks(facts, state)
    except Exception:  # a bug or garbage of any kind refuses, it never allows
        return Refuse(500, "error"), state


def _no(status, word, authed=False, retry_after=0, route=None):
    return Refuse(status, word, authed, retry_after, route)


def _typed(f) -> bool:
    if type(f) is not Facts:
        return False
    for v in (f.version, f.method, f.target, f.peer, f.server, f.channel):
        if type(v) is not str:
            return False
    if type(f.port) is not int or type(f.headers) not in (tuple, list):
        return False
    for h in f.headers:
        if type(h) not in (tuple, list) or len(h) != 2 or type(h[0]) is not str or type(h[1]) is not str:
            return False
    return True


def _take(bucket, rate, burst, now):
    """(a place was free, the bucket afterwards). A bucket that is None is full."""
    if bucket is None:
        tokens = float(burst)
    else:
        gained = (now - bucket.stamp) * rate
        tokens = min(float(burst), bucket.tokens + (gained if gained > 0 else 0.0))
    if tokens >= 1.0:
        return True, Bucket(tokens - 1.0, now)
    return False, Bucket(tokens, now)


def _record_ok(rec, date) -> bool:
    """A record the gate can compare with: a digest of 64 lowercase hex digits and an expiry later than the date."""
    if type(rec) is not dict:
        return False
    digest, expires = rec.get("sha256"), rec.get("expires")
    if type(digest) is not str or not _HEX64.fullmatch(digest):
        return False
    if type(expires) is not str or not _DATE.fullmatch(expires):
        return False
    if type(date) is not str or not _DATE.fullmatch(date):
        return False
    return date < expires  # the day of the expiry date is already too late


def _match(path: str, method: str):
    """(route, params) for an exact match of the path and the method; the string "method" for a known path with
    another method; None for an unknown path."""
    segs = path.split("/")[1:]
    known = False
    for r in ROUTES:
        want = r.path.split("/")[1:]
        if len(want) != len(segs):
            continue
        params = {}
        for have, w in zip(segs, want):
            if w.startswith("{"):
                pattern = _PARAM[w[1:-1]]
                if not pattern.fullmatch(have):
                    break
                params[w[1:-1]] = have
            elif have != w:
                break
        else:
            known = True
            if r.method == method:
                return r, params
    return "method" if known else None


def _page_meta_ok(origin, site, mode, dest, own) -> bool:
    if origin is not None and origin != own:
        return False
    if site is not None and site not in ("same-origin", "none"):
        return False
    if mode is not None and mode != "navigate":
        return False
    return dest is None or dest == "document"


def _api_meta_ok(method, origin, site, mode, dest, own) -> bool:
    if method != "GET" and origin is None:
        return False  # a browser always sends Origin with a POST or a DELETE
    if origin is not None and origin != own:
        return False
    if site is not None and site != "same-origin":
        return False
    if mode is not None and mode not in ("cors", "same-origin"):
        return False
    return dest is None or dest == "empty"


def _query(route, query: str):
    """The parameters of a query string, or None when it does not fit the route (word `target`)."""
    out = {}
    for pair in query.split("&"):
        key, eq, value = pair.partition("=")
        if not eq or key not in route.query or key in out or not _QUERY_VALUE.fullmatch(value):
            return None
        out[key] = value if value else None
    return out


def _run_checks(f, s):
    if not _typed(f):
        return _no(500, "error"), s
    now = s.mono
    method, target = f.method, f.target

    # 1 protocol
    if f.version not in _VERSIONS or method not in _METHODS:
        return _no(405, "method"), s
    # 2 peer: the connection, the socket's own address and the channel
    if f.peer != LOOPBACK or f.server != LOOPBACK or f.channel not in CHANNELS or not 1 <= f.port <= 65535:
        return _no(403, "peer"), s
    # 3 headers
    if len(f.headers) > MAX_HEADERS:
        return _no(403, "header"), s
    h: dict = {}
    block = 0
    for name, value in f.headers:
        if not _NAME.fullmatch(name) or len(value) > MAX_HEADER_VALUE or not _VALUE.fullmatch(value):
            return _no(403, "header"), s
        block += len(name) + len(value) + 4
        low = name.lower()
        if low in _FORBIDDEN or low.startswith("proxy-"):
            return _no(403, "header"), s
        if low == "connection" and value.lower() not in ("close", "keep-alive"):
            return _no(403, "header"), s
        h.setdefault(low, []).append(value)
    if block > MAX_HEADER_BLOCK:
        return _no(403, "header"), s
    for low in _SINGLE:
        if len(h.get(low, ())) > 1:
            return _no(403, "header"), s
    one = {low: values[0] for low, values in h.items()}
    # 4 Host: exactly ours, which is what stops DNS rebinding, and holds for a request with a valid token too
    own_host = f"{LOOPBACK}:{f.port}"
    if one.get("host") != own_host:
        return _no(403, "host"), s
    # 5 target
    if len(target) > MAX_TARGET or not _TARGET.fullmatch(target) or target[0] != "/":
        return _no(403, "target"), s
    if "%" in target or "\\" in target or ";" in target or "#" in target or "//" in target:
        return _no(403, "target"), s
    path, mark, query = target.partition("?")
    if "?" in query:
        return _no(403, "target"), s
    for seg in path.split("/")[1:]:
        if seg == "." or seg == "..":
            return _no(403, "target"), s
    own_origin = f"http://{own_host}"
    origin, site, mode, dest = (one.get("origin"), one.get("sec-fetch-site"), one.get("sec-fetch-mode"),
                                one.get("sec-fetch-dest"))
    length = one.get("content-length")

    # 6 the page: the one request that needs no token
    if method == "GET" and path == "/":
        if mark:
            return _no(403, "target"), s
        if not _page_meta_ok(origin, site, mode, dest, own_origin):
            return _no(403, "origin"), s
        if length is not None and length != "0":
            return _no(413, "length", route="page"), s
        return Allow("page", {}, 0), s

    # 7 token
    presented = None
    auth = one.get("authorization")
    if auth is not None and auth.startswith("Bearer ") and _TOKEN.fullmatch(auth[7:]):
        presented = auth[7:]
    locked = now < s.locked_until
    valid = False
    if presented is not None and _record_ok(s.record, s.date):
        valid = hmac.compare_digest(hashlib.sha256(presented.encode("ascii")).digest(),
                                    bytes.fromhex(s.record["sha256"]))
    if not valid:
        recent = tuple(t for t in s.fails if now - t < THROTTLE_WINDOW)
        fails = (recent + (now,))[-THROTTLE_FAILS:]
        until = s.locked_until
        if locked or len(fails) >= THROTTLE_FAILS:
            until = now + THROTTLE_WINDOW
        nxt = State(s.record, s.date, now, s.auth, s.read, s.write, s.run, fails, until)
        if locked:
            return _no(429, "rate", retry_after=int(THROTTLE_WINDOW)), nxt
        return _no(401, "token"), nxt
    free, auth_bucket = _take(s.auth, RATES["auth"][0], RATES["auth"][1], now)
    s = State(s.record, s.date, now, auth_bucket, s.read, s.write, s.run, s.fails, s.locked_until)
    if not free:
        return _no(429, "rate", retry_after=1), s

    # 8 Origin and fetch metadata
    if not _api_meta_ok(method, origin, site, mode, dest, own_origin):
        return _no(403, "origin", True), s
    # 9 route, and the query it lists
    found = _match(path, method)
    if found is None:
        return _no(404, "route", True), s
    if found == "method":
        return _no(405, "method", True), s
    route, params = found
    if mark:
        asked = _query(route, query)
        if asked is None:
            return _no(403, "target", True, route=route.id), s
        params.update(asked)
    for key in route.query:
        params.setdefault(key, None)
    # 10 body
    if method != "POST":
        if length is not None and length != "0":
            return _no(413, "length", True, route=route.id), s
    else:
        if length is None or not _LENGTH.fullmatch(length):
            return _no(411, "length", True, route=route.id), s
        if len(length) > 6 or int(length) > route.body_cap:
            return _no(413, "length", True, route=route.id), s
        ctype = one.get("content-type")
        if ctype is None or ctype.lower() not in _JSON_TYPES:
            return _no(415, "type", True, route=route.id), s
    # 11 rate: the bucket of the route's class
    rate, burst = RATES[route.cls]
    free, bucket = _take(getattr(s, route.cls), rate, burst, now)
    s = State(s.record, s.date, now, s.auth, bucket if route.cls == "read" else s.read,
              bucket if route.cls == "write" else s.write, bucket if route.cls == "run" else s.run, s.fails,
              s.locked_until)
    if not free:
        return _no(429, "rate", retry_after=1, route=route.id), s
    return Allow(route.id, params, route.body_cap), s


# ------------------------------------------------------------------------------------------ the body


def _no_duplicates(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate key")
        out[key] = value
    return out


def _refuse_constant(_name):
    raise ValueError("not a plain JSON number")


def parse_body(route, raw):
    """The parameters in the bytes of a body, or Refuse(400, "body"). `route` is a route id or a Route. UTF-8 only, no
    BOM, one JSON object, no duplicate key, no key the route does not list, no NaN, Infinity or float, only the types
    the route lists, strings of printable characters on one line. The length limits that belong to the queue (a title
    of 200 characters, an answer of 500) are the queue's: the core function refuses them, so they are not copied here."""
    try:
        r = route if isinstance(route, Route) else _BY_ID[route]
        if type(raw) is not bytes or not raw or len(raw) > r.body_cap:
            return _no(400, "body")
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates, parse_constant=_refuse_constant,
                          parse_float=_refuse_constant)
        kinds = dict(r.fields)
        if type(data) is not dict or not set(data) <= set(kinds) or not set(r.required) <= set(data):
            return _no(400, "body")
        for key, value in data.items():
            if kinds[key] == "bool":
                if type(value) is not bool:
                    return _no(400, "body")
            elif type(value) is not str or len(value) > MAX_BODY_STRING or not value.isprintable():
                return _no(400, "body")
        return data
    except Exception:  # bad UTF-8, bad JSON, too deep, too big a number: all the same answer
        return _no(400, "body")
