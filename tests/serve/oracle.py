"""The oracle: a deliberately naive second implementation of the request gate, written from the text of W6.R5.

It shares no code with `umwayi/servegate.py` (it does not import it). It is slow and repeats itself on purpose: plain
loops, no regular expressions for the shapes, one check after another in the order of W6.R5.2. When the gate and the
oracle disagree on any generated case, one of them does not do what the text says.

`judge(facts_dict, state_dict)` takes plain values and returns ("allow", route, params) or
("refuse", status, word, authed). `from_req` turns a tests.serve.gen.Req into those plain values.
"""

import hashlib
import hmac

DIGITS = "0123456789"
HEX = "0123456789abcdef"
B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
NAME_OK = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-"
SINGLE = ["host", "origin", "authorization", "content-length", "content-type", "sec-fetch-site", "sec-fetch-mode",
          "sec-fetch-dest"]
FORBIDDEN = ["transfer-encoding", "expect", "upgrade", "content-encoding", "te", "trailer"]
LOOP = "127.0.0.1"

# (id, method, [segments], class, body cap, query keys)   a segment is a word or ("id",) or ("name",)
TABLE = [
    ("page", "GET", [], "page", 0, []),
    ("status", "GET", ["v1", "status"], "read", 0, []),
    ("snapshot", "GET", ["v1", "snapshot"], "read", 0, []),
    ("queue.list", "GET", ["v1", "queue"], "read", 0, ["status", "kind"]),
    ("logbook.verify", "GET", ["v1", "logbook"], "read", 0, []),
    ("budget.status", "GET", ["v1", "budget"], "read", 0, []),
    ("agents.list", "GET", ["v1", "agents"], "read", 0, []),
    ("agents.check", "POST", ["v1", "agents", ("name",), "check"], "run", 64, []),
    ("queue.add", "POST", ["v1", "queue"], "write", 4096, []),
    ("queue.answer", "POST", ["v1", "queue", ("id",), "answer"], "write", 4096, []),
    ("queue.close", "POST", ["v1", "queue", ("id",), "close"], "write", 64, []),
    ("kill.on", "POST", ["v1", "kill", "on"], "write", 512, []),
]
RATE = {"auth": (10.0, 30), "read": (5.0, 20), "write": (2.0, 6), "run": (1.0, 3)}


def from_req(r):
    facts = {"version": r.version, "method": r.method, "target": r.target, "headers": [tuple(h) for h in r.headers],
             "peer": r.peer, "server": r.server, "port": r.port, "channel": r.channel}
    state = {"record": r.rec, "date": r.date, "mono": r.mono, "buckets": dict(r.buckets), "fails": list(r.fails),
             "locked_until": r.locked_until}
    return facts, state


def _all_str(*vals):
    for v in vals:
        if type(v) is not str:
            return False
    return True


def _is_date(s):
    if type(s) is not str or len(s) != 10:
        return False
    for i, c in enumerate(s):
        if i in (4, 7):
            if c != "-":
                return False
        elif c not in DIGITS:
            return False
    return True


def _is_hex64(s):
    if type(s) is not str or len(s) != 64:
        return False
    for c in s:
        if c not in HEX:
            return False
    return True


def _token_shaped(s):
    if len(s) != 48 or s[:5] != "umt1_":
        return False
    for c in s[5:]:
        if c not in B64:
            return False
    return True


def _refill(bucket, name, now):
    rate, burst = RATE[name]
    if bucket is None:
        return float(burst)
    tokens, stamp = bucket
    gained = (now - stamp) * rate
    if gained < 0:
        gained = 0
    return min(float(burst), tokens + gained)


def _take(buckets, name, now):
    tokens = _refill(buckets.get(name), name, now)
    if tokens >= 1:
        return True
    return False


def _split_target(t):
    if "?" in t:
        i = t.index("?")
        return t[:i], t[i + 1:], True
    return t, "", False


def _route_match(path, method):
    """(route row, params) for an exact match of path and method; ("method", None) for a known path with another
    method; None for an unknown path."""
    segs = path.split("/")[1:]
    seen_path = False
    for row in TABLE:
        rid, rmethod, pattern = row[0], row[1], row[2]
        if rid == "page":
            ok = segs == [""]
            params = {}
        else:
            ok = len(segs) == len(pattern)
            params = {}
            if ok:
                for s, p in zip(segs, pattern):
                    if isinstance(p, tuple):
                        if p[0] == "id":
                            good = len(s) >= 6 and s[:2] == "Q-" and all(c in DIGITS for c in s[2:])
                        else:
                            good = 1 <= len(s) <= 40 and all(c in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in s)
                        if not good:
                            ok = False
                            break
                        params[p[0]] = s
                    elif s != p:
                        ok = False
                        break
        if ok:
            seen_path = True
            if rmethod == method:
                return row, params
    return ("method", None) if seen_path else None


def judge(f, s):
    try:
        return _judge(f, s)
    except Exception:
        return ("refuse", 500, "error", False)


def _judge(f, s):
    # wrong types are an error, never a guess
    if not _all_str(f["version"], f["method"], f["target"], f["peer"], f["server"], f["channel"]):
        return ("refuse", 500, "error", False)
    if type(f["port"]) is not int or type(f["headers"]) not in (tuple, list):
        return ("refuse", 500, "error", False)
    heads = []
    for h in f["headers"]:
        if type(h) not in (tuple, list) or len(h) != 2 or not _all_str(h[0], h[1]):
            return ("refuse", 500, "error", False)
        heads.append((h[0], h[1]))
    method, target, port = f["method"], f["target"], f["port"]
    now = s["mono"]

    # 1 protocol
    if f["version"] not in ("HTTP/1.0", "HTTP/1.1"):
        return ("refuse", 405, "method", False)
    if method not in ("GET", "POST", "DELETE"):
        return ("refuse", 405, "method", False)
    # 2 peer (and the channel, and the server's own address)
    if f["peer"] != LOOP or f["server"] != LOOP or f["channel"] != "local" or not 1 <= port <= 65535:
        return ("refuse", 403, "peer", False)
    # 3 headers
    if len(heads) > 64:
        return ("refuse", 403, "header", False)
    total = 0
    count = {}
    connection_values = []
    for name, value in heads:
        if name == "" or any(c not in NAME_OK for c in name):
            return ("refuse", 403, "header", False)
        if len(value) > 4096 or any(not 32 <= ord(c) <= 126 for c in value):
            return ("refuse", 403, "header", False)
        total += len(name) + len(value) + 4
        low = name.lower()
        count[low] = count.get(low, 0) + 1
        if low in FORBIDDEN or low[:6] == "proxy-":
            return ("refuse", 403, "header", False)
        if low == "connection":
            connection_values.append(value)
    if total > 16384:
        return ("refuse", 403, "header", False)
    for v in connection_values:
        if v.lower() not in ("close", "keep-alive"):
            return ("refuse", 403, "header", False)
    for low in SINGLE:
        if count.get(low, 0) > 1:
            return ("refuse", 403, "header", False)

    def one(name):
        for n, v in heads:
            if n.lower() == name:
                return v
        return None

    # 4 host
    if one("host") != f"{LOOP}:{port}":
        return ("refuse", 403, "host", False)
    # 5 target
    if len(target) > 512 or target == "" or target[0] != "/":
        return ("refuse", 403, "target", False)
    for c in target:
        if not 33 <= ord(c) <= 126 or c in "%\\;#":
            return ("refuse", 403, "target", False)
    if "//" in target:
        return ("refuse", 403, "target", False)
    path, query, has_query = _split_target(target)
    if "?" in query:
        return ("refuse", 403, "target", False)
    for seg in path.split("/")[1:]:
        if seg in (".", ".."):
            return ("refuse", 403, "target", False)

    origin = one("origin")
    site, mode, dest = one("sec-fetch-site"), one("sec-fetch-mode"), one("sec-fetch-dest")
    own_origin = f"http://{LOOP}:{port}"

    # 6 the page
    if method == "GET" and path == "/":
        if has_query:
            return ("refuse", 403, "target", False)
        if origin is not None and origin != own_origin:
            return ("refuse", 403, "origin", False)
        if site is not None and site not in ("same-origin", "none"):
            return ("refuse", 403, "origin", False)
        if mode is not None and mode != "navigate":
            return ("refuse", 403, "origin", False)
        if dest is not None and dest != "document":
            return ("refuse", 403, "origin", False)
        cl = one("content-length")
        if cl is not None and cl != "0":
            return ("refuse", 413, "length", False)
        return ("allow", "page", {})

    # 7 token
    record = s["record"]
    locked = now < s["locked_until"]
    auth = one("authorization")
    presented = None
    if auth is not None and auth[:7] == "Bearer " and _token_shaped(auth[7:]):
        presented = auth[7:]
    record_ok = (type(record) is dict and _is_hex64(record.get("sha256")) and _is_date(record.get("expires"))
                 and _is_date(s["date"]) and s["date"] < record["expires"])
    valid = False
    if presented is not None and record_ok:
        valid = hmac.compare_digest(hashlib.sha256(presented.encode()).digest(), bytes.fromhex(record["sha256"]))
    if not valid:
        if locked:
            return ("refuse", 429, "rate", False)
        return ("refuse", 401, "token", False)
    if not _take(s["buckets"], "auth", now):
        return ("refuse", 429, "rate", False)

    # 8 origin and fetch metadata
    if method in ("POST", "DELETE") and origin is None:
        return ("refuse", 403, "origin", True)
    if origin is not None and origin != own_origin:
        return ("refuse", 403, "origin", True)
    if site is not None and site != "same-origin":
        return ("refuse", 403, "origin", True)
    if mode is not None and mode not in ("cors", "same-origin"):
        return ("refuse", 403, "origin", True)
    if dest is not None and dest != "empty":
        return ("refuse", 403, "origin", True)

    # 9 route
    found = _route_match(path, method)
    if found is None:
        return ("refuse", 404, "route", True)
    if found[0] == "method":
        return ("refuse", 405, "method", True)
    row, params = found
    rid, cls, cap, keys = row[0], row[3], row[4], row[5]
    if has_query:
        seen = []
        for pair in query.split("&"):
            if "=" not in pair:
                return ("refuse", 403, "target", True)
            k, v = pair.split("=", 1)
            if k not in keys or k in seen:
                return ("refuse", 403, "target", True)
            seen.append(k)
            if len(v) > 16 or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in v):
                return ("refuse", 403, "target", True)
            params[k] = v if v != "" else None
    for k in keys:
        params.setdefault(k, None)

    # 10 body
    cl = one("content-length")
    if method in ("GET", "DELETE"):
        if cl is not None and cl != "0":
            return ("refuse", 413, "length", True)
    else:
        if cl is None or cl == "" or any(c not in DIGITS for c in cl) or cl[0] == "0":
            return ("refuse", 411, "length", True)
        if len(cl) > 6 or int(cl) > cap:
            return ("refuse", 413, "length", True)
        ct = one("content-type")
        if ct is None or ct.lower() not in ("application/json", "application/json; charset=utf-8"):
            return ("refuse", 415, "type", True)

    # 11 rate
    if not _take(s["buckets"], cls, now):
        return ("refuse", 429, "rate", False)
    return ("allow", rid, params)
