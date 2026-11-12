"""Seeded generators, the golden requests, the mutation catalogue and the shrinker for the gate tests (W6.R16.1).

No outside package. Every random choice comes from `random.Random(seed)` through `getrandbits` and `random()` only,
which give the same numbers on Python 3.10 to 3.13, so the same seed gives the same cases everywhere.

The golden table below is written from the route table of W6.R8.1 and is deliberately a second copy: a route that
exists in the code and not here (or the other way round) fails a test.
"""

import copy
import json
import random
import string
from dataclasses import dataclass, field

from tests.serve.support import DATE, PORT, TOKEN, TOKEN2, record, servegate

# route id -> (method, path with the query, body or None, class)
GOLDEN = {
    "page": ("GET", "/", None, "page"),
    "status": ("GET", "/v1/status", None, "read"),
    "snapshot": ("GET", "/v1/snapshot", None, "read"),
    "queue.list": ("GET", "/v1/queue?status=open&kind=task", None, "read"),
    "logbook.verify": ("GET", "/v1/logbook", None, "read"),
    "budget.status": ("GET", "/v1/budget", None, "read"),
    "agents.list": ("GET", "/v1/agents", None, "read"),
    "agents.check": ("POST", "/v1/agents/helper/check", {}, "run"),
    "queue.add": ("POST", "/v1/queue", {"kind": "task", "title": "T"}, "write"),
    "queue.answer": ("POST", "/v1/queue/Q-0001/answer", {"answer": "A"}, "write"),
    "queue.close": ("POST", "/v1/queue/Q-0001/close", {}, "write"),
    "kill.on": ("POST", "/v1/kill/on", {}, "write"),
}
BODY_CAPS = {"agents.check": 64, "queue.add": 4096, "queue.answer": 4096, "queue.close": 64, "kill.on": 512}
ROUTE_IDS = tuple(GOLDEN)
MONO = 1000.0


class Gen:
    """The one source of randomness. Only getrandbits and random() are used, so a seed means the same on every Python."""

    def __init__(self, seed):
        self.seed = seed
        self.r = random.Random(seed)

    def bits(self, n):
        return self.r.getrandbits(n)

    def rand(self):
        return self.r.random()

    def below(self, n):
        if n <= 1:
            return 0
        k = (n - 1).bit_length()
        while True:
            v = self.r.getrandbits(k)
            if v < n:
                return v

    def between(self, lo, hi):
        return lo + self.below(hi - lo + 1)

    def pick(self, seq):
        seq = list(seq)
        return seq[self.below(len(seq))]

    def chance(self, p):
        return self.r.random() < p

    def text(self, alphabet, lo, hi):
        return "".join(self.pick(alphabet) for _ in range(self.between(lo, hi)))

    def shuffled(self, seq):
        seq = list(seq)
        for i in range(len(seq) - 1, 0, -1):
            j = self.below(i + 1)
            seq[i], seq[j] = seq[j], seq[i]
        return seq


NAME_CHARS = string.ascii_letters + string.digits + "-"
HOSTILE = ["\x00", "\x01", "\t", "\r", "\n", "\x7f", "\u00e9", "\u202e", "\ud800", "%", "\\", ";", "#", "?", "&",
           "=", " ", "/", ".", "'", '"', "<", ">", "\u0131", "\U0001f600"]
ALPHA = string.ascii_letters + string.digits + "-_/.:=,; "


# ----------------------------------------------------------------------------------------------- a request


@dataclass
class Req:
    """A request and the state the gate is given, as plain mutable fields. `facts()` and `state()` build the real ones."""
    route: str
    method: str
    target: str
    headers: list
    version: str = "HTTP/1.1"
    peer: str = "127.0.0.1"
    server: str = "127.0.0.1"
    port: int = PORT
    channel: str = "local"
    body: bytes = b""
    rec: object = field(default_factory=lambda: record(TOKEN))
    date: str = DATE
    mono: float = MONO
    buckets: dict = field(default_factory=dict)  # "auth", "read", "write", "run" -> (tokens, stamp)
    fails: tuple = ()
    locked_until: float = 0.0

    def facts(self):
        return servegate.Facts(self.version, self.method, self.target,
                               tuple((n, v) for n, v in self.headers), self.peer, self.server, self.port,
                               self.channel)

    def state(self):
        b = {k: servegate.Bucket(*v) for k, v in self.buckets.items()}
        return servegate.State(copy.deepcopy(self.rec), self.date, self.mono, b.get("auth"), b.get("read"),
                               b.get("write"), b.get("run"), tuple(self.fails), self.locked_until)

    def clone(self):
        return copy.deepcopy(self)

    # header helpers (names compare without case)
    def get(self, name):
        return [v for n, v in self.headers if n.lower() == name.lower()]

    def set(self, name, value):
        for h in self.headers:
            if h[0].lower() == name.lower():
                h[1] = value
                return self
        self.headers.append([name, value])
        return self

    def drop(self, name):
        self.headers = [h for h in self.headers if h[0].lower() != name.lower()]
        return self

    def add(self, name, value):
        self.headers.append([name, value])
        return self


def good(route, token=TOKEN, port=PORT):
    """The golden request of a route: what the page's client sends, with the state that lets it through."""
    method, target, body, _cls = GOLDEN[route]
    headers = [["Host", f"127.0.0.1:{port}"], ["User-Agent", "umwayi-test"], ["Accept", "*/*"]]
    raw = b""
    if route != "page":
        headers.append(["Authorization", f"Bearer {token}"])
    if method == "POST":
        raw = json.dumps(body).encode("utf-8")
        headers += [["Origin", f"http://127.0.0.1:{port}"], ["Content-Type", "application/json"],
                    ["Content-Length", str(len(raw))]]
    return Req(route, method, target, headers, port=port, body=raw, rec=record(token))


def is_post(r):
    return r.method in ("POST", "DELETE")


def needs_token(r):
    return r.route != "page"


# ---------------------------------------------------------------------------------------- the catalogue


@dataclass(frozen=True)
class Mutation:
    name: str
    word: str  # the word of the first check that fails; None for a benign mutation
    applies: object  # Req -> bool
    apply: object  # (Req) -> None, changes the request in place


def _always(r):
    return True


def _v1(r):
    return r.route != "page"


def _split(target):
    path, q, query = target.partition("?")
    return path, (q + query) if q else ""


def _with_target(r, path_fn=None, query_fn=None):
    path, query = _split(r.target)
    if path_fn:
        path = path_fn(path)
    if query_fn:
        query = query_fn(query)
    r.target = path + query


def _flip(s):
    """A string that differs from s in exactly one character."""
    return s[:-1] + ("a" if s[-1:] != "a" else "b") if s else "a"


def _hdr(name, value, applies=_always):
    return lambda r: r.add(name, value)


def _build():
    M = []

    def must(name, word, apply, applies=_always):
        M.append(Mutation(name, word, applies, apply))

    def benign(name, apply, applies=_always):
        M.append(Mutation(name, None, applies, apply))

    port = str(PORT)
    # Host
    must("host_localhost", "host", lambda r: r.set("Host", "localhost:" + port))
    must("host_other_port", "host", lambda r: r.set("Host", "127.0.0.1:" + str(PORT + 1)))
    must("host_other_address", "host", lambda r: r.set("Host", "127.0.0.2:" + port))
    must("host_missing", "host", lambda r: r.drop("Host"))
    must("host_duplicated", "header", lambda r: r.add("Host", "127.0.0.1:" + port))
    must("host_empty", "host", lambda r: r.set("Host", ""))
    must("host_without_port", "host", lambda r: r.set("Host", "127.0.0.1"))
    must("host_name_of_another_site", "host", lambda r: r.set("Host", "evil.example:" + port))
    # Origin
    must("origin_missing_on_post", "origin", lambda r: r.drop("Origin"), is_post)
    must("origin_null", "origin", lambda r: r.set("Origin", "null"))
    must("origin_other_host", "origin", lambda r: r.set("Origin", "http://localhost:" + port))
    must("origin_other_port", "origin", lambda r: r.set("Origin", "http://127.0.0.1:" + str(PORT + 1)))
    must("origin_https", "origin", lambda r: r.set("Origin", "https://127.0.0.1:" + port))
    must("origin_empty", "origin", lambda r: r.set("Origin", ""))
    must("origin_with_slash", "origin", lambda r: r.set("Origin", "http://127.0.0.1:" + port + "/"))
    must("origin_duplicated", "header", lambda r: r.set("Origin", "http://127.0.0.1:" + port).add(
        "Origin", "http://127.0.0.1:" + port))
    # the token
    must("token_missing", "token", lambda r: r.drop("Authorization"), _v1)
    must("token_empty", "token", lambda r: r.set("Authorization", "Bearer "), _v1)
    must("token_truncated", "token", lambda r: r.set("Authorization", "Bearer " + TOKEN[:-1]), _v1)
    must("token_extended", "token", lambda r: r.set("Authorization", "Bearer " + TOKEN + "A"), _v1)
    must("token_lowercased", "token", lambda r: r.set("Authorization", "Bearer " + TOKEN.lower()), _v1)
    must("token_prefixed", "token", lambda r: r.set("Authorization", "Bearer x" + TOKEN), _v1)
    must("token_one_character_changed", "token", lambda r: r.set("Authorization", "Bearer " + _flip(TOKEN)), _v1)
    must("token_padded_with_a_space", "token", lambda r: r.set("Authorization", "Bearer " + TOKEN + " "), _v1)
    must("token_two_spaces_after_scheme", "token", lambda r: r.set("Authorization", "Bearer  " + TOKEN), _v1)
    must("token_scheme_lowercase", "token", lambda r: r.set("Authorization", "bearer " + TOKEN), _v1)
    must("token_scheme_basic", "token", lambda r: r.set("Authorization", "Basic " + TOKEN), _v1)
    must("token_without_scheme", "token", lambda r: r.set("Authorization", TOKEN), _v1)
    must("token_two_headers", "header", lambda r: r.add("Authorization", "Bearer " + TOKEN), _v1)
    must("token_of_another_record", "token", lambda r: r.set("Authorization", "Bearer " + TOKEN2), _v1)
    must("record_expired", "token", lambda r: setattr(r, "date", "2026-12-12"), _v1)
    must("record_long_expired", "token", lambda r: setattr(r, "date", "2027-06-01"), _v1)
    must("record_revoked", "token", lambda r: setattr(r, "rec", None), _v1)
    must("record_without_digest", "token", lambda r: setattr(r, "rec", {"id": "T-1", "expires": "2026-12-12"}), _v1)
    must("token_in_query", "target", lambda r: _with_target(
        r, query_fn=lambda q: (q + "&" if q else "?") + "token=" + TOKEN), _v1)
    # headers
    must("header_transfer_encoding", "header", _hdr("Transfer-Encoding", "chunked"))
    must("header_expect", "header", _hdr("Expect", "100-continue"))
    must("header_upgrade", "header", _hdr("Upgrade", "websocket"))
    must("header_content_encoding", "header", _hdr("Content-Encoding", "gzip"))
    must("header_te", "header", _hdr("TE", "trailers"))
    must("header_trailer", "header", _hdr("Trailer", "X-A"))
    must("header_proxy_connection", "header", _hdr("Proxy-Connection", "keep-alive"))
    must("header_proxy_authorization", "header", _hdr("Proxy-Authorization", "Basic x"))
    must("connection_upgrade", "header", _hdr("Connection", "upgrade"))
    must("header_65_lines", "header", lambda r: [r.add(f"X-H{i}", "v") for i in range(62)])
    must("header_value_5000_bytes", "header", _hdr("X-Big", "a" * 5000))
    must("header_block_over_16_kb", "header", lambda r: [r.add(f"X-B{i}", "b" * 4000) for i in range(5)])
    must("header_value_with_nul", "header", _hdr("X-Nul", "a\x00b"))
    must("header_value_with_cr", "header", _hdr("X-Cr", "a\rb"))
    must("header_value_with_lf", "header", _hdr("X-Lf", "a\nb"))
    must("header_name_with_a_space", "header", _hdr("Bad Name", "v"))
    must("header_name_empty", "header", _hdr("", "v"))
    must("header_folded_line", "header", lambda r: r.headers.append([" X-Fold", "continued"]))
    must("header_non_ascii_value", "header", _hdr("X-Latin", "caf\u00e9"))
    must("fetch_site_duplicated", "header", lambda r: r.add("Sec-Fetch-Site", "same-origin").add(
        "Sec-Fetch-Site", "same-origin"))
    # body length and type
    must("content_length_missing", "length", lambda r: r.drop("Content-Length"), is_post)
    must("content_length_doubled", "header", lambda r: r.add("Content-Length", r.get("Content-Length")[0]), is_post)
    must("content_length_negative", "length", lambda r: r.set("Content-Length", "-1"), is_post)
    must("content_length_hex", "length", lambda r: r.set("Content-Length", "0x10"), is_post)
    must("content_length_seven_digits", "length", lambda r: r.set("Content-Length", "1000000"), is_post)
    must("content_length_over_the_cap", "length",
         lambda r: r.set("Content-Length", str(BODY_CAPS[r.route] + 1)), is_post)
    must("content_length_zero", "length", lambda r: r.set("Content-Length", "0"), is_post)
    must("content_length_with_plus", "length", lambda r: r.set("Content-Length", "+5"), is_post)
    must("content_type_missing", "type", lambda r: r.drop("Content-Type"), is_post)
    must("content_type_text", "type", lambda r: r.set("Content-Type", "text/plain"), is_post)
    must("content_type_form", "type", lambda r: r.set("Content-Type", "application/x-www-form-urlencoded"), is_post)
    must("content_type_json_other_charset", "type", lambda r: r.set("Content-Type", "application/json; charset=latin1"),
         is_post)
    must("body_on_a_get", "length", lambda r: r.add("Content-Length", "5"), lambda r: r.method == "GET")
    # peer, protocol, method
    must("peer_not_loopback", "peer", lambda r: setattr(r, "peer", "10.0.0.5"))
    must("peer_empty", "peer", lambda r: setattr(r, "peer", ""))
    must("server_address_not_loopback", "peer", lambda r: setattr(r, "server", "0.0.0.0"))
    must("channel_not_local", "peer", lambda r: setattr(r, "channel", "relay"))
    for m in ("OPTIONS", "HEAD", "PUT", "PATCH", "CONNECT", "TRACE", "get", "DELETEX", ""):
        must(f"method_{m or 'empty'}", "method", lambda r, m=m: setattr(r, "method", m))
    for v in ("HTTP/0.9", "HTTP/2.0", "HTTP/1.2", "http/1.1", ""):
        must(f"version_{v.replace('/', '_') or 'empty'}", "method", lambda r, v=v: setattr(r, "version", v))
    must("method_swapped_to_post_on_a_get_route", "method", lambda r: (
        setattr(r, "method", "POST"), r.add("Origin", f"http://127.0.0.1:{PORT}"),
        r.add("Content-Type", "application/json"), r.add("Content-Length", "2")), lambda r: r.method == "GET"
        and r.route not in ("queue.list",) and r.route != "page")
    must("method_swapped_to_get_on_a_post_route", "method", lambda r: (
        setattr(r, "method", "GET"), r.drop("Content-Length"), r.drop("Content-Type")),
        lambda r: r.method == "POST" and r.route != "queue.add")
    # the target
    must("target_percent", "target", lambda r: _with_target(r, lambda p: p.rstrip("/") + "/%41"))
    must("target_dot_dot", "target", lambda r: _with_target(r, lambda p: p.rstrip("/") + "/.."))
    must("target_single_dot", "target", lambda r: _with_target(r, lambda p: p.rstrip("/") + "/."))
    must("target_double_slash", "target", lambda r: _with_target(r, lambda p: p.rstrip("/") + "//x"))
    must("target_backslash", "target", lambda r: _with_target(r, lambda p: p.rstrip("/") + "/\\x"))
    must("target_semicolon", "target", lambda r: _with_target(r, lambda p: p.rstrip("/") + "/;x"))
    must("target_fragment", "target", lambda r: setattr(r, "target", r.target + "#frag"))
    must("target_control_character", "target", lambda r: setattr(r, "target", r.target + "\x01"))
    must("target_non_ascii", "target", lambda r: setattr(r, "target", r.target + "\u00e9"))
    must("target_with_a_space", "target", lambda r: setattr(r, "target", r.target + " x"))
    must("target_absolute_form", "target", lambda r: setattr(r, "target", "http://127.0.0.1:" + port + r.target))
    must("target_authority_form", "target", lambda r: setattr(r, "target", "127.0.0.1:" + port))
    must("target_asterisk", "target", lambda r: setattr(r, "target", "*"))
    must("target_513_characters", "target", lambda r: setattr(r, "target", "/" + "a" * 512))
    must("target_unknown_query_key", "target", lambda r: _with_target(
        r, query_fn=lambda q: (q + "&" if q else "?") + "zz=1"))
    must("target_repeated_query_key", "target", lambda r: setattr(r, "target", "/v1/queue?kind=task&kind=task"),
         lambda r: r.route == "queue.list")
    must("target_bad_query_value", "target", lambda r: setattr(r, "target", "/v1/queue?status=Open%20"),
         lambda r: r.route == "queue.list")
    must("target_trailing_slash", "route", lambda r: _with_target(r, lambda p: p + "/"), _v1)
    must("target_upper_case", "route", lambda r: _with_target(r, lambda p: p.upper()), _v1)
    must("target_unknown_route", "route", lambda r: setattr(r, "target", "/v1/nothing"), _v1)
    must("target_unknown_under_a_route", "route", lambda r: _with_target(r, lambda p: p + "/extra"), _v1)
    must("target_id_with_three_digits", "route", lambda r: setattr(r, "target", "/v1/queue/Q-001/answer"
                                                                 if r.route == "queue.answer" else "/v1/queue/Q-001/close"),
         lambda r: r.route in ("queue.answer", "queue.close"))
    must("target_agent_name_upper_case", "route", lambda r: setattr(r, "target", "/v1/agents/Helper/check"),
         lambda r: r.route == "agents.check")
    must("target_agent_name_41_characters", "route", lambda r: setattr(r, "target", "/v1/agents/" + "a" * 41 + "/check"),
         lambda r: r.route == "agents.check")
    # fetch metadata
    must("fetch_site_cross_site", "origin", _hdr("Sec-Fetch-Site", "cross-site"), _v1)
    must("fetch_site_none_on_an_api_request", "origin", _hdr("Sec-Fetch-Site", "none"), _v1)
    must("fetch_mode_navigate_on_an_api_request", "origin", _hdr("Sec-Fetch-Mode", "navigate"), _v1)
    must("fetch_dest_document_on_an_api_request", "origin", _hdr("Sec-Fetch-Dest", "document"), _v1)
    must("fetch_site_empty", "origin", _hdr("Sec-Fetch-Site", ""))
    must("page_fetch_site_cross_site", "origin", _hdr("Sec-Fetch-Site", "cross-site"), lambda r: r.route == "page")
    must("page_fetch_mode_cors", "origin", _hdr("Sec-Fetch-Mode", "cors"), lambda r: r.route == "page")
    must("page_fetch_dest_empty", "origin", _hdr("Sec-Fetch-Dest", "empty"), lambda r: r.route == "page")
    # rate (state)
    must("authenticated_bucket_empty", "rate", lambda r: r.buckets.__setitem__("auth", (0.0, r.mono)), _v1)
    must("class_bucket_empty", "rate", lambda r: r.buckets.__setitem__(GOLDEN[r.route][3], (0.0, r.mono)), _v1)

    # harmless changes
    benign("header_names_upper_case", lambda r: [h.__setitem__(0, h[0].upper()) for h in r.headers])
    benign("header_names_lower_case", lambda r: [h.__setitem__(0, h[0].lower()) for h in r.headers])
    benign("header_order_reversed", lambda r: r.headers.reverse())
    benign("extra_accept_headers", lambda r: (r.add("Accept", "application/json"), r.add("Accept-Language", "en"),
                                              r.add("Accept-Encoding", "gzip")))
    benign("extra_user_agent_and_cache_control", lambda r: (r.set("User-Agent", "other/1"),
                                                            r.add("Cache-Control", "no-cache")))
    benign("a_cookie_is_ignored", lambda r: r.add("Cookie", "a=b"))
    benign("connection_keep_alive", lambda r: r.add("Connection", "keep-alive"))
    benign("connection_close", lambda r: r.add("Connection", "close"))
    benign("connection_close_upper_case", lambda r: r.add("Connection", "Keep-Alive"))
    benign("http_1_0", lambda r: setattr(r, "version", "HTTP/1.0"))
    benign("charset_on_the_content_type", lambda r: r.set("Content-Type", "application/json; charset=utf-8"), is_post)
    benign("good_fetch_metadata", lambda r: (r.add("Sec-Fetch-Site", "same-origin"), r.add("Sec-Fetch-Mode", "cors"),
                                             r.add("Sec-Fetch-Dest", "empty")), _v1)
    benign("good_page_fetch_metadata", lambda r: (r.add("Sec-Fetch-Site", "none"), r.add("Sec-Fetch-Mode", "navigate"),
                                                  r.add("Sec-Fetch-Dest", "document")), lambda r: r.route == "page")
    benign("origin_on_a_get", lambda r: r.add("Origin", f"http://127.0.0.1:{PORT}"), lambda r: r.method == "GET"
           and not r.get("Origin"))
    benign("a_long_but_legal_header", lambda r: r.add("X-Long", "a" * 4096))
    benign("sixty_four_headers", lambda r: [r.add(f"X-H{i}", "v") for i in range(64 - len(r.headers))])
    return tuple(M)


MUTATIONS = _build()
MUST = tuple(m for m in MUTATIONS if m.word is not None)
BENIGN = tuple(m for m in MUTATIONS if m.word is None)
assert len(MUST) >= 45, len(MUST)


def apply_mutation(req, m):
    out = req.clone()
    m.apply(out)
    return out


# ----------------------------------------------------------------------------- random cases and garbage


def _wild(g, r):
    """One uncontrolled change: not a named fault, whatever the generator thinks of."""
    k = g.below(11)
    if k == 0:
        r.add(g.text(NAME_CHARS + g.pick(["", " ", "\x00", "_", "\u00e9"]), 0, 12),
              g.text(ALPHA + "".join(HOSTILE), 0, g.pick([8, 8, 200, 5000])))
    elif k == 1 and r.target:
        i = g.below(len(r.target))
        r.target = r.target[:i] + g.pick(HOSTILE) + r.target[i + 1:]
    elif k == 2:
        r.method = g.pick(["GET", "POST", "DELETE", "PUT", "get", "", "G", "GET ", g.text(string.ascii_uppercase, 1, 9)])
    elif k == 3:
        r.version = g.pick(["HTTP/1.1", "HTTP/1.0", "HTTP/0.9", "HTTP/1.1 ", "HTTP", "", g.text(ALPHA, 0, 12)])
    elif k == 4:
        r.set("Host", g.pick([f"127.0.0.1:{PORT}", "localhost", "127.0.0.1", f"127.0.0.1:{PORT} ", "[::1]:" + str(PORT),
                             g.text(ALPHA, 0, 20)]))
    elif k == 5 and r.headers:
        r.headers.append(list(g.pick(r.headers)))  # a duplicate of some header
    elif k == 6 and r.headers:
        del r.headers[g.below(len(r.headers))]
    elif k == 7:
        r.set("Content-Length", g.pick(["0", "1", "2", "10", "99999", "-3", "1e3", "٣", g.text("0123456789", 0, 9), ""]))
    elif k == 8:
        r.set("Authorization", g.pick(["Bearer " + TOKEN, "Bearer " + TOKEN2, "Bearer", "Bearer ", TOKEN,
                                       "Bearer " + g.text(string.ascii_letters + "_-", 0, 60)]))
    elif k == 9:
        r.set("Origin", g.pick([f"http://127.0.0.1:{PORT}", "null", "", "http://127.0.0.1", g.text(ALPHA, 0, 25)]))
    else:
        r.peer = g.pick(["127.0.0.1", "127.0.0.1", "::1", "localhost", "", "0.0.0.0"])


def random_state(g, r):
    r.rec = g.pick([record(TOKEN)] * 6 + [record(TOKEN2), None, {"sha256": "x"}, {"sha256": record(TOKEN)["sha256"]},
                                         {"sha256": record(TOKEN)["sha256"].upper(), "expires": "2026-12-12"},
                                         {"sha256": record(TOKEN)["sha256"], "expires": "2026-13-45x"},
                                         record(TOKEN, expires="2026-11-12"), record(TOKEN, expires="2099-01-01")])
    r.date = g.pick([DATE, DATE, "2026-12-11", "2026-12-12", "2030-01-01", "2026-01-01"])
    r.mono = float(g.between(100, 100000)) + g.rand()
    for name in ("auth", "read", "write", "run"):
        if g.chance(0.4):
            r.buckets[name] = (g.rand() * g.pick([0.5, 3, 40]), r.mono - g.rand() * g.pick([0.01, 1, 30, 5000]))
    if g.chance(0.3):
        times = sorted(r.mono - g.rand() * g.pick([1, 30, 90]) for _ in range(g.between(1, 5)))
        r.fails = tuple(times)
        r.locked_until = r.mono + g.pick([-5.0, 0.0, 30.0, 59.0]) if g.chance(0.5) else 0.0


def random_req(g):
    r = good(g.pick(ROUTE_IDS))
    for _ in range(g.pick([0, 0, 1, 1, 2, 3, 4])):
        pool = [m for m in MUTATIONS if m.applies(r)]
        m = g.pick(pool)
        m.apply(r)
    for _ in range(g.pick([0, 0, 0, 1, 2])):
        _wild(g, r)
    if g.chance(0.35):
        random_state(g, r)
    return r


def garbage_facts(g):
    """A Facts whose fields have the wrong type or wild content: the gate must still answer."""
    junk = [None, 5, 1.5, b"GET", ["GET"], {"a": 1}, (), "", "x" * 20000, "\x00", "\ud800", True]
    f = good(g.pick(ROUTE_IDS)).facts()
    fields = ["version", "method", "target", "headers", "peer", "server", "port", "channel"]
    kw = {n: getattr(f, n) for n in fields}
    for n in g.shuffled(fields)[: g.between(1, 3)]:
        kw[n] = g.pick(junk)
    if g.chance(0.4):
        kw["headers"] = g.pick([(("Host", None),), ((None, "x"),), (("Host",),), ("Host: x",), (("a", "b", "c"),),
                                [["Host", "127.0.0.1:8765"]], (("H" * 9000, "v"),), tuple(("X", "v") for _ in range(5000))])
    return servegate.Facts(**kw)


# ------------------------------------------------------------------------------------------- shrinking


def shrink(req, failing):
    """The smallest request found that `failing(req)` still calls a failure: delete a header, shorten a value, shorten
    the target, until nothing more can be taken away. `failing` must be True for `req` itself."""
    cur = req.clone()
    changed = True
    while changed:
        changed = False
        for i in range(len(cur.headers) - 1, -1, -1):
            cand = cur.clone()
            del cand.headers[i]
            if failing(cand):
                cur, changed = cand, True
        for i in range(len(cur.headers)):
            val = cur.headers[i][1]
            if len(val) > 1:
                cand = cur.clone()
                cand.headers[i][1] = val[: len(val) // 2]
                if failing(cand):
                    cur, changed = cand, True
        if len(cur.target) > 1:
            cand = cur.clone()
            cand.target = cur.target[: max(1, len(cur.target) // 2)]
            if failing(cand):
                cur, changed = cand, True
    return cur


def describe(req):
    """A request in one readable block, for a failure message (the token is shown as TOKEN)."""
    h = "; ".join(f"{n}: {v[:60]!r}" for n, v in req.headers)
    return (f"{req.method!r} {req.target[:100]!r} {req.version!r} peer={req.peer!r} server={req.server!r} "
            f"channel={req.channel!r} headers=[{h}] rec={req.rec!r} date={req.date} mono={req.mono} "
            f"buckets={req.buckets} fails={req.fails} locked_until={req.locked_until}").replace(TOKEN, "TOKEN")
