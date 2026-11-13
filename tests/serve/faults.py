"""The catalogue of planted faults for `umwayi serve` (W6.10, W6.R16.10). Test data only: nothing here is imported by the product.

Each fault is a small edit (exact text to exact text, found exactly once) of one source file, applied by `tests/serve/mutation.py` to a
throwaway copy of the tree, never to the real one. `tests` are the tests that should catch it, cheapest first; the run stops at the first
one that fails. `r16` names the item of W6.R16.10 the fault is (empty for the extra mutants of the four files). `expect` is "caught"
for all of them; a fault that is known to change nothing a test can see says `equivalent` and why, and the report shows it as a survivor
with that reason, never as caught.
"""

from dataclasses import dataclass, field

GATE = "tests.serve.test_gate_properties"
WIRE = "tests.serve.test_wire"
ENT = "tests.serve.test_entries"
FAIL = "tests.serve.test_failclosed"
SAME = "tests.serve.test_samecode"
TOK = "tests.serve.test_token"
SCEN = "tests.serve.test_scenarios"
GAPS = "tests.serve.test_gaps"
NODE = "node:ui/test/client.test.mjs"
NODE_SCEN = "tests.serve.test_scenarios.RealPageClient"

GATE_PY = "umwayi/servegate.py"
SERVE_PY = "umwayi/serve.py"
TOKEN_PY = "umwayi/servetoken.py"
CLIENT_JS = "ui/src/api/client.js"


@dataclass(frozen=True)
class Fault:
    id: str
    name: str
    file: str
    edits: tuple  # ((old, new), ...), each old found exactly once in the file
    tests: tuple
    r16: str = ""
    expect: str = "caught"
    why: str = ""  # for an equivalent fault: why no test can see it


def F(id, name, file, old, new, tests, r16="", expect="caught", why=""):
    edits = tuple(old) if isinstance(old, list) else ((old, new),)
    return Fault(id, name, file, edits, tuple(tests), r16, expect, why)


FAULTS = [
    # ------------------------------------------------------------------ the faults named in W6.R16.10
    F("R1", "the token compared with ==", GATE_PY,
      'valid = hmac.compare_digest(hashlib.sha256(presented.encode("ascii")).digest(),\n'
      '                                    bytes.fromhex(s.record["sha256"]))',
      'valid = hashlib.sha256(presented.encode("ascii")).hexdigest() == s.record["sha256"]',
      [GATE], "the token compared with =="),
    F("R2", "the digest not compared at all", GATE_PY,
      'valid = hmac.compare_digest(hashlib.sha256(presented.encode("ascii")).digest(),\n'
      '                                    bytes.fromhex(s.record["sha256"]))',
      "valid = True", [GATE, SCEN], "the digest not compared at all"),
    F("R3a", "the digest of the token in the request entry", SERVE_PY,
      'ctx = Ctx(_new_request_id(), record["id"] if record else "T-00000000", route, facts.method, started,',
      'ctx = Ctx(_new_request_id(), record["sha256"] if record else "T-00000000", route, facts.method, started,',
      [ENT, SCEN], "the token in the entry, the output or an error"),
    F("R3b", "the token in the logbook entry of `token create`", TOKEN_PY,
      'today, f"Created token {rec[\'id\']}, expires on {rec[\'expires\']}.",',
      'today, f"Created token {token}, expires on {rec[\'expires\']}.",',
      [TOK, SCEN], "the token in the entry, the output or an error"),
    F("R3c", "the token in the start line of the server", SERVE_PY,
      'out.write(f"Token {rec[\'id\']} expires on {rec[\'expires\']} ({left} days left).\\n")',
      'out.write(f"Token {rec[\'id\']} {rec[\'sha256\']} expires on {rec[\'expires\']} ({left} days left).\\n")',
      [WIRE], "the token in the entry, the output or an error"),
    F("R4", "the record written 0644", TOKEN_PY, "MODE = 0o600", "MODE = 0o644", [TOK, SCEN], "the record written 0644"),
    F("R5", "the Host check skipped", GATE_PY, 'if one.get("host") != own_host:', "if False:", [GATE, SCEN], "the Host check skipped"),
    F("R6", "localhost allowed", GATE_PY, 'if one.get("host") != own_host:',
      'if one.get("host") not in (own_host, f"localhost:{f.port}"):', [GATE, SCEN], "localhost allowed"),
    F("R7", "a missing Origin allowed on POST", GATE_PY, 'if method != "GET" and origin is None:', "if False:",
      [GATE, SCEN], "a missing Origin allowed on POST"),
    F("R8", "Origin: null allowed", GATE_PY,
      'if origin is not None and origin != own:\n        return False\n    if site is not None and site != "same-origin":',
      'if origin is not None and origin not in (own, "null"):\n        return False\n    if site is not None and site != "same-origin":',
      [GATE, SCEN], "Origin: null allowed"),
    F("R9", "an Access-Control-Allow-Origin header added", SERVE_PY,
      '("Connection", "close"), ("Server", "umwayi")) + tuple(extra)',
      '("Connection", "close"), ("Server", "umwayi"), ("Access-Control-Allow-Origin", "*")) + tuple(extra)',
      [WIRE, SCEN], "an Access-Control-Allow-Origin added"),
    F("R10a", "the socket bound to the all-addresses string, read back skipped", SERVE_PY,
      [('self.server = server_class((LOOPBACK, port), handler_class)', 'self.server = server_class(("0.0.0.0", port), handler_class)'),
       ("if host != LOOPBACK or (port and bound != port):", "if False:")], None,
      [SCEN, WIRE], "the socket bound to the all-addresses string"),
    F("R10b", "the socket bound to the all-addresses string (the read back stays)", SERVE_PY,
      'self.server = server_class((LOOPBACK, port), handler_class)',
      'self.server = server_class(("0.0.0.0", port), handler_class)', [SCEN, WIRE], "the socket bound to the all-addresses string"),
    F("R11", "the kill switch not read for the write routes (chats are not built: W4)", SERVE_PY,
      "stopped = route.stopped and kill.stopped(ks)", "stopped = False", [SCEN, SAME], "the kill switch not read for chats"),
    F("R12", "the rules check skipped on one route (queue.close)", SERVE_PY,
      "if route.skips_rules:", 'if route.skips_rules or route.id == "queue.close":', [SAME, FAIL], "the rules check skipped on one route"),
    F("R13a", "the rules answer ignored (No)", SERVE_PY,
      "            if exit_code == 2:\n                return self._finish(ctx, \"rules\", ks, answer_text, False)\n",
      "", [FAIL, SAME], "the rules answer ignored"),
    F("R13b", "the rules answer ignored (Ask me first)", SERVE_PY,
      "if exit_code != 0:  # Ask me first", "if False:  # Ask me first", [FAIL, SAME], "the rules answer ignored"),
    F("R14", "a Yes taken from an unlogged check", SERVE_PY, "if not logged:  # an answer that was not logged is not given",
      "if False:  # an answer that was not logged is not given", [FAIL, ENT], "a Yes taken from an unlogged check"),
    F("R15", "the request entry skipped", SERVE_PY, "if not self._write(ctx, word, kill_text, rules_text, ran):",
      "if False:", [ENT, SCEN], "the request entry skipped"),
    F("R16", "the entry holding the body (the parameters)", SERVE_PY,
      "return self._finish(ctx, word, ks, answer_text, True,", "return self._finish(ctx, word, str(params), answer_text, True,",
      [ENT, SCEN], "the entry holding the body"),
    F("R17", "OPTIONS answered like a method of the table", GATE_PY, '_METHODS = ("GET", "POST", "DELETE")',
      '_METHODS = ("GET", "POST", "DELETE", "OPTIONS")', [GATE, WIRE], "OPTIONS answered 200"),
    F("R18", "a duplicate header accepted", GATE_PY, "if len(h.get(low, ())) > 1:", "if len(h.get(low, ())) > 2:",
      [GATE], "a duplicate header accepted"),
    F("R19", "Content-Length absent accepted", GATE_PY, "if length is None or not _LENGTH.fullmatch(length):",
      "if length is not None and not _LENGTH.fullmatch(length):", [GATE], "Content-Length absent accepted"),
    F("R20", "a body read before the gate", SERVE_PY,
      "        record = servetoken.read_record(self.root)\n        with self._state_lock:",
      "        read_body(1)\n        record = servetoken.read_record(self.root)\n        with self._state_lock:",
      [FAIL, SAME], "a body read before the gate"),
    F("R21", "an unknown JSON key accepted", GATE_PY,
      [("if type(data) is not dict or not set(data) <= set(kinds) or not set(r.required) <= set(data):",
        "if type(data) is not dict or not set(r.required) <= set(data):"),
       ("            if kinds[key] == \"bool\":", "            if kinds.get(key) == \"bool\":")], None,
      [GATE, FAIL], "an unknown JSON key accepted"),
    F("R22a", "the rate bucket of the class off", GATE_PY,
      '    if not free:\n        return _no(429, "rate", retry_after=1, route=route.id), s',
      "    if False:\n        return _no(429, \"rate\", retry_after=1, route=route.id), s", [GATE], "the rate bucket off"),
    F("R22b", "the bucket of all authenticated requests off", GATE_PY,
      '    if not free:\n        return _no(429, "rate", retry_after=1), s', "    if False:\n        return _no(429, \"rate\", retry_after=1), s",
      [GATE], "the rate bucket off"),
    F("R23", "the throttle applied to a valid token", GATE_PY, "    if not valid:\n        recent = ",
      "    if locked:\n        valid = False\n    if not valid:\n        recent = ", [GATE, SCEN], "the throttle applied to a valid token"),
    F("R24", "a route added without a table row", GATE_PY,
      '    Route("kill.on", "POST", "/v1/kill/on", "write", 512, False, skips_rules=True, fields=(("reason", "str"),)),\n)',
      '    Route("kill.on", "POST", "/v1/kill/on", "write", 512, False, skips_rules=True, fields=(("reason", "str"),)),\n'
      '    Route("status.ping", "GET", "/v1/ping", "read", 0, False),\n)', [GATE, "tests.test_docs"], "a route added without a table row"),
    F("R25", "a kill.off route added", GATE_PY,
      '    Route("kill.on", "POST", "/v1/kill/on", "write", 512, False, skips_rules=True, fields=(("reason", "str"),)),\n)',
      '    Route("kill.on", "POST", "/v1/kill/on", "write", 512, False, skips_rules=True, fields=(("reason", "str"),)),\n'
      '    Route("kill.off", "POST", "/v1/kill/off", "write", 512, False, skips_rules=True),\n)', [GATE, SCEN], "a kill.off route added"),
    F("R27", "a path in agents.list", SERVE_PY,
      '{"name": a.name, "platform": a.platform, "transport": a.transport} for a in found',
      '{"name": a.name, "platform": a.platform, "transport": a.transport, "workdir": a.workdir} for a in found',
      [SAME, ENT, FAIL], "a path in agents.list"),
    F("R28", "the page served without the build.json match", SERVE_PY,
      'if type(want) is not str or want != hashlib.sha256(data).hexdigest():', "if False:", [WIRE], "the page served without the build.json match"),
    F("R29", "a rotation not seen by a running server", SERVE_PY,
      "        record = servetoken.read_record(self.root)\n        with self._state_lock:",
      '        record = getattr(self, "_rec", None) or servetoken.read_record(self.root)\n        self._rec = record\n'
      "        with self._state_lock:", [WIRE, SCEN, TOK], "rotation not seen by a running server"),
    F("R30a", "an expired token accepted (any date)", GATE_PY, "return date < expires  # the day of the expiry date is already too late",
      "return True", [GATE, SCEN], "an expired token accepted"),
    F("R30b", "an expired token accepted on the day of expiry", GATE_PY,
      "return date < expires  # the day of the expiry date is already too late", "return date <= expires", [GATE], "an expired token accepted"),

    # ------------------------------------------------------------------------ more mutants of servegate.py
    F("G1", "the peer check dropped", GATE_PY, "if f.peer != LOOPBACK or f.server != LOOPBACK", "if f.server != LOOPBACK", [GATE]),
    F("G2", "the channel check dropped", GATE_PY, "or f.channel not in CHANNELS or", "or", [GATE]),
    F("G3", "the forbidden headers allowed", GATE_PY, 'if low in _FORBIDDEN or low.startswith("proxy-"):',
      'if low.startswith("proxy-"):', [GATE]),
    F("G4", "a percent sign in the target allowed", GATE_PY, 'if "%" in target or', "if", [GATE]),
    F("G5", "a dot dot segment allowed", GATE_PY, 'if seg == "." or seg == "..":', 'if seg == ".":', [GATE]),
    F("G6", "a double slash allowed", GATE_PY, ' or ";" in target or "#" in target or "//" in target:', ' or ";" in target or "#" in target:', [GATE]),
    F("G7", "the content type not checked", GATE_PY, "if ctype is None or ctype.lower() not in _JSON_TYPES:", "if ctype is None:", [GATE]),
    F("G8", "a body on a GET allowed", GATE_PY, 'if method != "POST":\n        if length is not None and length != "0":',
      'if method != "POST":\n        if False:', [GATE]),
    F("G9", "an unknown query key allowed", GATE_PY, "if not eq or key not in route.query or key in out", "if not eq or key in out", [GATE]),
    F("G10", "a cross-site request allowed", GATE_PY, 'if site is not None and site != "same-origin":\n        return False\n    if mode is not None and mode not in ("cors"',
      'if False:\n        return False\n    if mode is not None and mode not in ("cors"', [GATE, SCEN]),
    F("G11", "the protocol version not checked", GATE_PY, "if f.version not in _VERSIONS or method not in _METHODS:",
      "if method not in _METHODS:", [GATE]),
    F("G12", "the body cap doubled", GATE_PY, "int(length) > route.body_cap:", "int(length) > route.body_cap * 2:", [GATE]),
    F("G13", "five failures made fifty", GATE_PY, "THROTTLE_FAILS = 5", "THROTTLE_FAILS = 50", [GATE, SCEN]),
    F("G14", "the lock-out never applies", GATE_PY, "locked = now < s.locked_until", "locked = False", [GATE, SCEN]),
    F("G15", "the header count limit raised", GATE_PY, "MAX_HEADERS = 64", "MAX_HEADERS = 640", [GATE]),
    F("G16", "a duplicate key in a body accepted", GATE_PY, '        if key in out:\n            raise ValueError("duplicate key")',
      "        if False:\n            raise ValueError(\"duplicate key\")", [GATE, SCEN]),
    F("G17", "a float in a body accepted", GATE_PY, "parse_float=_refuse_constant)", "parse_float=float)", [GATE, SCEN], expect="equivalent",
      why="no route has a number field (every field is a string or a true or false), so a float is refused by the type check of the same function "
          "whether or not the parser reads it; the parser's own refusal is a second lock"),
    F("G18", "an unprintable character in a body string accepted", GATE_PY, "or not value.isprintable():", ":", [GATE]),
    F("G19", "the query value shape not checked", GATE_PY, "or not _QUERY_VALUE.fullmatch(value):", ":", [GAPS, GATE]),
    F("G20", "the page's fetch metadata not checked", GATE_PY, "if not _page_meta_ok(origin, site, mode, dest, own_origin):", "if False:", [GATE]),
    F("G21", "Host with a trailing dot or other port allowed by a prefix match", GATE_PY, 'if one.get("host") != own_host:',
      'if not str(one.get("host")).startswith(own_host):', [GATE, SCEN]),

    # ---------------------------------------------------------------------- more mutants of servetoken.py
    F("T1", "a token of 2 random bytes", TOKEN_PY, "secrets.token_bytes(32)", "secrets.token_bytes(2)", [TOK, SCEN]),
    F("T2", "no limit on days", TOKEN_PY, "if type(days) is not int or not 1 <= days <= MAX_DAYS:", "if type(days) is not int or not 1 <= days:", [GAPS, TOK]),
    F("T3", "an extra key in the record accepted", TOKEN_PY, "tuple(sorted(rec)) != tuple(sorted(KEYS))", "not set(KEYS) <= set(rec)", [TOK]),
    F("T4", "a link taken as the record", TOKEN_PY, "if not stat.S_ISREG(os.lstat(path).st_mode):  # a link is not followed",
      "if not stat.S_ISREG(os.stat(path).st_mode):", [TOK]),
    F("T5", "the old record not put back after a failed entry (rotate)", TOKEN_PY,
      "        fsutil.atomic_write(path, old_bytes, mode=MODE)\n        if isinstance(e, UmwayiError):\n            return _failed(str(e).rstrip(\". \"))\n        raise\n    return Result(0, _shown(token, rec))\n\n\ndef revoke",
      "        if isinstance(e, UmwayiError):\n            return _failed(str(e).rstrip(\". \"))\n        raise\n    return Result(0, _shown(token, rec))\n\n\ndef revoke", [TOK]),
    F("T6", "a token shown to a pipe by create", TOKEN_PY, "    days = _check_days(days)\n    if not is_terminal:\n        return _terminal_only()\n    root = Path(root)\n    d = _state_dir(root)",
      "    days = _check_days(days)\n    root = Path(root)\n    d = _state_dir(root)", [TOK]),
    F("T7", "the created record not removed after a failed entry", TOKEN_PY, "    except BaseException as e:\n        os.unlink(path)\n",
      "    except BaseException as e:\n", [TOK]),
    F("T8", "a life of 900 days allowed in a record", TOKEN_PY, "DEFAULT_DAYS, MAX_DAYS = 30, 90", "DEFAULT_DAYS, MAX_DAYS = 30, 900", [TOK]),
    F("T9", "the digest of a different algorithm", TOKEN_PY, "return hashlib.sha256(token.encode(\"ascii\")).hexdigest()",
      "return hashlib.sha1(token.encode(\"ascii\")).hexdigest() + '0' * 24", [TOK, SCEN]),

    # ------------------------------------------------------------------------ more mutants of serve.py
    F("S1", "the 16 slot limit raised to 1600", SERVE_PY, "MAX_HANDLERS = 16", "MAX_HANDLERS = 1600", [WIRE]),
    F("S2", "the tamper check at the start skipped", SERVE_PY,
      "            logbook.read_checked_chain(root)  # the tamper check: a broken logbook starts nothing", "            pass", [WIRE]),
    F("S3", "an expired token accepted at the start", SERVE_PY, 'if rec is None or not today < rec["expires"]:', "if rec is None:", [WIRE]),
    F("S4", "the one server per root lock skipped", SERVE_PY, "with runlock.held(root, LOCK_NAME):", "if True:", [SCEN, WIRE]),
    F("S5", "a refusal after a valid token not logged", SERVE_PY, "if verdict.authed and record is not None:", "if False:", [ENT, SCEN]),
    F("S6", "the degraded state never entered", SERVE_PY, "            self.degraded = True\n            return False", "            return False", [ENT, SCEN]),
    F("S7", "the no-store header dropped", SERVE_PY, '("Cache-Control", "no-store"),\n            ("X-Content-Type-Options", "nosniff"),', '("X-Content-Type-Options", "nosniff"),', [WIRE]),
    F("S8", "the page's frame-ancestors policy dropped", SERVE_PY, "PAGE_CSP = \"frame-ancestors 'none'; base-uri",
      "PAGE_CSP = \"base-uri", [WIRE]),
    F("S9", "the whole-request deadline made very long", SERVE_PY, "REQUEST_DEADLINE = 10.0", "REQUEST_DEADLINE = 1000.0", [WIRE]),
    F("S10", "queue add forgets if_not_open", SERVE_PY, 'params.get("recommendation", ""), today,\n                                   params.get("if_not_open", False))',
      'params.get("recommendation", ""), today,\n                                   False)', [SAME, SCEN]),
    F("S11", "the last summary not written at shutdown", SERVE_PY, "        self.flush_summary(force=True)\n        try:", "        try:", [SCEN, ENT]),
    F("S12", "a linked page file followed", SERVE_PY, "        if not _link_free(path):\n            return None, \"link\"\n", "", [WIRE]),
    F("S13", "a page over 2.5 MB served", SERVE_PY, "MAX_PAGE = 2_500_000", "MAX_PAGE = 250_000_000", [WIRE]),
    F("S14", "the port may be shared", SERVE_PY, "allow_reuse_address = False", "allow_reuse_address = True", [WIRE, SCEN], expect="equivalent",
      why="on Linux a listening socket is not shared by SO_REUSEADDR (it only lets a server bind while old connections are in TIME_WAIT), so a port in use is still refused; the only difference is a quick restart on a fixed port, which no test pins"),
    F("S16", "the write lock not taken", SERVE_PY, "locked = route.cls in (\"write\", \"run\")  # one write at a time", "locked = False  # one write at a time",
      [SAME, WIRE, SCEN], expect="equivalent",
      why="every pipeline runs one at a time on the main thread (KNOWN-LIMITS 233), so the write lock can never be contended; it is kept as a second lock for the day the pipeline moves to threads"),
    F("S17", "the kill switch state not logged in the entry", SERVE_PY, 'f" Kill switch {kill_text}. Rules check {rules_text}."',
      'f" Rules check {rules_text}."', [ENT]),
    F("S18", "the request id not random but fixed", SERVE_PY, 'return "R-" + secrets.token_hex(4)', 'return "R-00000000"', [GAPS, ENT]),

    # --------------------------------------------------------------------------- mutants of the page client
    F("C1", "the client works on localhost", CLIENT_JS, "const ORIGIN = /^http:\\/\\/127\\.0\\.0\\.1:([0-9]{2,5})$/;",
      "const ORIGIN = /^http:\\/\\/(127\\.0\\.0\\.1|localhost):([0-9]{2,5})$/;", [NODE, NODE_SCEN]),
    F("C2", "the token kept after a token refusal", CLIENT_JS, "else if (got.word === 'token') token = null;", "else if (got.word === 'token') token = token;",
      [NODE, NODE_SCEN]),
    F("C3", "the token kept after the client stops", CLIENT_JS, "    halted = true;\n    token = null;", "    halted = true;", [NODE]),
    F("C4", "cookies sent", CLIENT_JS, "credentials: 'omit'", "credentials: 'include'", [NODE]),
    F("C5", "redirects followed", CLIENT_JS, "redirect: 'error'", "redirect: 'follow'", [NODE]),
    F("C6", "the request mode not same-origin", CLIENT_JS, "mode: 'same-origin'", "mode: 'cors'", [NODE]),
    F("C7", "the content type of the answer not checked", CLIENT_JS,
      "if (type !== 'application/json; charset=utf-8') throw new Error('shape');", "", [NODE]),
    F("C8", "a token of any length accepted", CLIENT_JS, "const TOKEN = /^umt1_[A-Za-z0-9_-]{43}$/;", "const TOKEN = /^umt1_[A-Za-z0-9_-]+$/;", [NODE]),
    F("C9", "an unknown query key sent", CLIENT_JS, "Object.keys(q).some((k) => !route.query.includes(k))", "false", [NODE]),
    F("C10", "an item id of any shape sent", CLIENT_JS, "if (typeof a.id !== 'string' || !ID.test(a.id)) return null;",
      "if (typeof a.id !== 'string') return null;", [NODE]),
    F("C11", "a kill.off route in the client table", CLIENT_JS, "  'kill.on': Object.freeze({ method: 'POST', path: '/v1/kill/on', query: [], fields: [['reason', 'str']], required: [] }),\n});",
      "  'kill.on': Object.freeze({ method: 'POST', path: '/v1/kill/on', query: [], fields: [['reason', 'str']], required: [] }),\n"
      "  'kill.off': Object.freeze({ method: 'POST', path: '/v1/kill/off', query: [], fields: [], required: [] }),\n});", [NODE]),
    F("C12", "the client keeps going after a word it should stop on", CLIENT_JS, "if (got.stop) halt();", "", [NODE]),
    F("C13", "the status of an answer not matched to its word", CLIENT_JS, "if (!statuses.includes(status) || env.code !== code) return null;",
      "if (env.code !== code) return null;", [NODE]),
    F("C14", "an absolute address sent", CLIENT_JS, "res = await send(req.path, init);", "res = await send('http://127.0.0.1:1' + req.path, init);",
      [NODE, NODE_SCEN]),
]
