"""The request gate, property based (W6.R16.1). `umwayi/servegate.py`, written in W6.2.

No outside package. Each property runs UMWAYI_PROP_N cases (default 5000) for each of three fixed seeds and one seed
drawn per run; a failure prints the seed, the case number and the smallest request the shrinker found.
"""

import ast
import copy
import dataclasses
import hashlib
import json
import os
import re
import string
import unittest
from unittest import mock

from tests.serve import gen, oracle
from tests.serve.support import PORT, REPO, TOKEN, TOKEN2, servegate

PROP_N = int(os.environ.get("UMWAYI_PROP_N", "5000"))
FIXED_SEEDS = (1, 2, 3)
DRAWN_SEED = int.from_bytes(os.urandom(4), "big")
SEEDS = FIXED_SEEDS + (DRAWN_SEED,)
WORDS = {"method", "peer", "header", "host", "target", "token", "origin", "route", "length", "type", "rate", "body",
         "error"}
STATUS = {"method": {405}, "peer": {403}, "header": {403}, "host": {403}, "target": {403}, "token": {401},
          "origin": {403}, "route": {404}, "length": {411, 413}, "type": {415}, "rate": {429}, "body": {400},
          "error": {500}}


def norm(v):
    if isinstance(v, servegate.Allow):
        return ("allow", v.route, dict(v.params))
    return ("refuse", v.status, v.word, v.authed)


def at(state, t):
    return dataclasses.replace(state, mono=t)


def decide_req(req):
    verdict, _state = servegate.decide(req.facts(), req.state())
    return verdict


class Prop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print(f"\n[serve gate properties] drawn seed {DRAWN_SEED}, {PROP_N} cases per seed", flush=True)

    def forall(self, make, check):
        """Run check(case) on PROP_N cases for each seed; check returns None or a text that says what was wrong."""
        for seed in SEEDS:
            g = gen.Gen(seed)
            for i in range(PROP_N):
                case = make(g)
                msg = check(case)
                if msg:
                    small = ""
                    if isinstance(case, gen.Req):
                        small = "\nsmallest request found: " + gen.describe(gen.shrink(case, lambda c: check(c) is not None))
                    self.fail(f"seed {seed}, case {i}: {msg}{small}")


# ---------------------------------------------------------------------------------------------- total


class TotalTests(Prop):
    def test_decide_is_total_over_requests_and_garbage(self):
        def check(case):
            facts, state = (case.facts(), case.state()) if isinstance(case, gen.Req) else case
            v, nxt = servegate.decide(facts, state)
            if not isinstance(v, (servegate.Allow, servegate.Refuse)):
                return f"not a verdict: {v!r}"
            if isinstance(v, servegate.Refuse):
                if v.word not in WORDS:
                    return f"word {v.word!r} is not in the fixed set"
                if v.status not in STATUS[v.word]:
                    return f"status {v.status} does not fit word {v.word}"
            elif v.route not in gen.ROUTE_IDS:
                return f"route {v.route!r} is not in the table"
            if not isinstance(nxt, servegate.State):
                return "the second value is not a State"
            return None

        self.forall(gen.random_req, check)
        base = gen.good("status").state()
        self.forall(lambda g: (gen.garbage_facts(g), base), check)

    def test_garbage_types_are_an_error_not_a_guess(self):
        base = gen.good("status").state()
        for bad in (None, 5, b"GET", ["GET"]):
            f = gen.good("status").facts()
            for field in ("version", "method", "target", "headers", "peer", "server", "port", "channel"):
                if field == "port" and bad == 5:
                    continue  # a whole number is the right type for a port
                with self.subTest(field=field, value=bad):
                    kw = {n: getattr(f, n) for n in ("version", "method", "target", "headers", "peer", "server",
                                                     "port", "channel")}
                    kw[field] = bad
                    v, _ = servegate.decide(servegate.Facts(**kw), base)
                    self.assertEqual((v.status, v.word), (500, "error"))

    def test_a_planted_exception_inside_gives_500_error(self):
        req = gen.good("status")
        with mock.patch.object(servegate.module(), "_run_checks", side_effect=RuntimeError("planted")):
            v, nxt = servegate.decide(req.facts(), req.state())
        self.assertEqual((v.status, v.word, v.authed), (500, "error", False))
        self.assertEqual(nxt, req.state())

    def test_a_planted_recursion_error_is_also_an_error_verdict(self):
        req = gen.good("status")
        with mock.patch.object(servegate.module(), "_run_checks", side_effect=RecursionError()):
            v, _ = servegate.decide(req.facts(), req.state())
        self.assertEqual(v.word, "error")


# ------------------------------------------------------------------------------------ against the oracle


class OracleTests(Prop):
    def test_decide_gives_the_answer_of_the_oracle(self):
        def check(r):
            got = norm(decide_req(r))
            want = oracle.judge(*oracle.from_req(r))
            if got[0] == "allow" and want[0] == "refuse":
                return f"UNSOUND: the gate allows {got}, the oracle refuses {want}"
            if got != tuple(want):
                return f"the gate says {got}, the oracle says {tuple(want)}"
            return None

        self.forall(gen.random_req, check)

    def test_every_golden_request_is_allowed_with_its_route_and_cap(self):
        for rid in gen.ROUTE_IDS:
            with self.subTest(route=rid):
                v = decide_req(gen.good(rid))
                self.assertIsInstance(v, servegate.Allow, v)
                self.assertEqual(v.route, rid)
                self.assertEqual(v.body_cap, gen.BODY_CAPS.get(rid, 0))


# ------------------------------------------------------------------------------------- one fault refuses


class OneFaultTests(Prop):
    def test_every_fault_is_refused_with_its_word_on_every_route(self):
        n = 0
        for rid in gen.ROUTE_IDS:
            base = gen.good(rid)
            for m in gen.MUST:
                if not m.applies(base):
                    continue
                n += 1
                with self.subTest(route=rid, fault=m.name):
                    v = decide_req(gen.apply_mutation(base, m))
                    self.assertIsInstance(v, servegate.Refuse, f"{m.name} was allowed")
                    self.assertEqual(v.word, m.word)
                    self.assertIn(v.status, STATUS[m.word])
        self.assertGreater(n, 500)

    GROUPS = {"good_fetch_metadata": "fetch", "good_page_fetch_metadata": "fetch", "charset_on_the_content_type": "content",
              "http_1_0": "version", "extra_accept_headers": "extra", "extra_user_agent_and_cache_control": "extra",
              "a_cookie_is_ignored": "extra", "a_long_but_legal_header": "extra", "sixty_four_headers": "extra",
              "connection_keep_alive": "connection", "connection_close": "connection", "connection_upgrade": "connection",
              "connection_close_upper_case": "connection", "origin_on_a_get": "origin",
              "method_swapped_to_post_on_a_get_route": "method", "method_swapped_to_get_on_a_post_route": "method",
              "header_names_upper_case": "names", "header_names_lower_case": "names", "header_order_reversed": "names"}

    @classmethod
    def group(cls, name):
        """Mutations of one group touch the same part of a request and could hide each other, so a chain takes one."""
        if name in cls.GROUPS:
            return cls.GROUPS[name]
        head = name.split("_")[0]
        if head in ("token", "record"):
            return "token"
        if head in ("peer", "server", "channel"):
            return "peer"
        if head in ("authenticated", "class"):
            return "rate"
        if head in ("fetch", "page"):
            return "fetch"
        if head in ("content", "body"):
            return "content"
        return head

    def chain(self, g):
        r = gen.good(g.pick(gen.ROUTE_IDS))
        chosen, used = [], set()
        for m in g.shuffled(gen.MUTATIONS):
            if len(chosen) >= g.between(1, 3) or not m.applies(r):
                continue
            grp = self.group(m.name)
            if grp in used or m.name in ("a_long_but_legal_header", "sixty_four_headers"):
                continue
            used.add(grp)
            chosen.append(m)
        if not any(m.word for m in chosen):
            chosen.append(g.pick([m for m in gen.MUST if m.applies(r) and self.group(m.name) not in used] or gen.MUST[:1]))
        for m in g.shuffled(chosen):
            m.apply(r)
        r.chain = [m for m in chosen]  # noqa: for the message only
        return r

    def test_a_chain_of_up_to_three_faults_is_refused_when_one_is_a_must_refuse(self):
        def check(r):
            musts = {m.word for m in r.chain if m.word}
            if not musts:
                return None  # the generator found nothing that applies to this route
            v = decide_req(r)
            if not isinstance(v, servegate.Refuse):
                return f"allowed after {[m.name for m in r.chain]}"
            if v.word not in musts:
                return f"word {v.word} is not one of {sorted(musts)} after {[m.name for m in r.chain]}"
            return None

        self.forall(self.chain, check)


# ------------------------------------------------------------------------------------- harmless changes


class HarmlessTests(Prop):
    LIMITS = ("a_long_but_legal_header", "sixty_four_headers")

    def test_each_harmless_change_changes_nothing(self):
        for rid in gen.ROUTE_IDS:
            base = gen.good(rid)
            first = norm(decide_req(base))
            self.assertEqual(first[0], "allow")
            for m in gen.BENIGN:
                if m.applies(base):
                    with self.subTest(route=rid, change=m.name):
                        self.assertEqual(norm(decide_req(gen.apply_mutation(base, m))), first)

    def test_any_mix_of_harmless_changes_changes_nothing(self):
        def make(g):
            r = gen.good(g.pick(gen.ROUTE_IDS))
            r.first = norm(decide_req(r))
            for m in g.shuffled([m for m in gen.BENIGN if m.name not in self.LIMITS and m.applies(r)])[: g.between(1, 4)]:
                m.apply(r)
            return r

        self.forall(make, lambda r: None if norm(decide_req(r)) == r.first else f"changed from {r.first}")


# ------------------------------------------------------------------------------- pure and deterministic


class Violation(BaseException):
    """Not an Exception, so the gate's own catch-all cannot hide it."""


class Boom:
    def __getattr__(self, name):
        raise Violation("the gate must not touch os.environ")

    def __getitem__(self, k):
        raise Violation("the gate must not touch os.environ")

    def get(self, *a):
        raise Violation("the gate must not touch os.environ")


class PureTests(Prop):
    def test_same_input_same_output_and_the_input_is_unchanged(self):
        def check(r):
            facts, state = r.facts(), r.state()
            facts0, state0 = copy.deepcopy(facts), copy.deepcopy(state)
            a = servegate.decide(facts, state)
            b = servegate.decide(facts, state)
            if a != b:
                return "two calls with the same input gave different answers"
            if facts != facts0 or state != state0 or facts.headers != facts0.headers:
                return "decide changed its input"
            return None

        self.forall(gen.random_req, check)

    def test_decide_runs_with_files_sockets_clocks_and_environment_patched_to_raise(self):
        import builtins
        import os as _os
        import socket
        import time

        def boom(*a, **k):
            raise Violation("the gate must do no I/O and read no clock")

        cases = [gen.random_req(gen.Gen(9)) for _ in range(20)] + [gen.good(r) for r in gen.ROUTE_IDS]
        with mock.patch.object(builtins, "open", boom), mock.patch.object(_os, "open", boom), \
                mock.patch.object(socket, "socket", boom), mock.patch.object(time, "time", boom), \
                mock.patch.object(time, "monotonic", boom), mock.patch.object(time, "sleep", boom), \
                mock.patch.object(_os, "environ", Boom()):
            for r in cases:
                servegate.decide(r.facts(), r.state())

    def test_the_module_imports_only_what_the_spec_allows(self):
        tree = ast.parse((REPO / "umwayi" / "servegate.py").read_text(encoding="utf-8"))
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                found.add((node.module or "").split(".")[0])
        self.assertLessEqual(found, {"__future__", "hmac", "hashlib", "json", "re", "dataclasses"}, found)

    def test_the_module_names_no_clock_no_file_no_environment_and_no_socket(self):
        tree = ast.parse((REPO / "umwayi" / "servegate.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                self.assertNotIn(node.id, {"open", "exec", "eval", "compile", "__import__", "input", "print", "globals"})
            if isinstance(node, ast.Attribute):
                self.assertNotIn(node.attr, {"environ", "time", "monotonic", "socket", "system", "popen", "getenv",
                                             "read_text", "read_bytes", "write_text", "write_bytes"})


# ------------------------------------------------------------------------------------------- the token


def strange_tokens(g):
    shapes = [lambda: "".join(g.pick(string.ascii_letters + string.digits + "-_") for _ in range(43)),
              lambda: g.text(string.printable[:-5], 0, 70), lambda: "",
              lambda: g.text(string.ascii_letters + "-_", 43, 43)]
    return "umt1_" + g.pick(shapes)() if g.chance(0.7) else g.pick(shapes)()


class TokenTests(Prop):
    def refusal_bytes(self, word):
        return servegate.refusal_body(word)

    def test_random_strings_are_refused_with_the_bytes_of_a_missing_token(self):
        missing = gen.good("status").drop("Authorization")
        want_v = decide_req(missing)
        want = self.refusal_bytes(want_v.word)
        self.assertEqual((want_v.status, want_v.word), (401, "token"))

        def make(g):
            r = gen.good(g.pick([x for x in gen.ROUTE_IDS if x != "page"]))
            r.set("Authorization", "Bearer " + strange_tokens(g))
            return r

        def check(r):
            if (r.get("Authorization") or [""])[0] == "Bearer " + TOKEN:
                return None
            v = decide_req(r)
            if (v.status, v.word) != (401, "token"):
                return f"got {v}"
            if self.refusal_bytes(v.word) != want:
                return "the response bytes differ from those of a missing token"
            return None

        self.forall(make, check)

    def test_the_real_token_with_one_change_is_refused_the_same_way(self):
        variants = []
        for i in range(len(TOKEN)):
            variants.append(TOKEN[:i] + ("A" if TOKEN[i] != "A" else "B") + TOKEN[i + 1:])  # changed
            variants.append(TOKEN[:i] + TOKEN[i + 1:])  # removed
            variants.append(TOKEN[:i] + "A" + TOKEN[i:])  # inserted
            if TOKEN[i].isalpha():
                variants.append(TOKEN[:i] + TOKEN[i].swapcase() + TOKEN[i + 1:])  # case changed
        variants += [" " + TOKEN, TOKEN + " ", TOKEN.upper(), TOKEN.lower()]
        for tok in variants:
            r = gen.good("queue.list")
            r.set("Authorization", "Bearer " + tok)
            v = decide_req(r)
            self.assertEqual((v.status, v.word), (401, "token"), tok)

    def test_the_comparison_is_made_with_compare_digest_on_digests(self):
        with mock.patch.object(servegate.hmac, "compare_digest", wraps=servegate.hmac.compare_digest) as spy:
            decide_req(gen.good("status"))
        self.assertEqual(spy.call_count, 1)
        a, b = spy.call_args[0]
        self.assertEqual((len(a), len(b)), (32, 32))
        self.assertEqual(a, hashlib.sha256(TOKEN.encode()).digest())

    def test_the_fifth_failure_locks_and_a_valid_token_still_passes(self):
        bad = gen.good("status")
        bad.set("Authorization", "Bearer " + TOKEN2)
        state = bad.state()
        words = []
        for i in range(8):
            facts = bad.facts()
            state = at(state, 1000.0 + i)
            v, state = servegate.decide(facts, state)
            words.append((v.status, v.word))
        self.assertEqual(words[:5], [(401, "token")] * 5)
        self.assertEqual(words[5:], [(429, "rate")] * 3)
        self.assertEqual(servegate.decide(bad.facts(), state)[0].retry_after, 60)
        good = gen.good("status")
        v, state = servegate.decide(good.facts(), at(state, 1008.0))
        self.assertIsInstance(v, servegate.Allow)  # failures never slow a valid token

    def test_failures_spread_over_more_than_a_minute_do_not_lock(self):
        bad = gen.good("status")
        bad.set("Authorization", "Bearer " + TOKEN2)
        state = bad.state()
        for i in range(12):
            state = at(state, 1000.0 + 15 * i)  # 4 per minute
            v, state = servegate.decide(bad.facts(), state)
            self.assertEqual((v.status, v.word), (401, "token"), i)

    def test_the_lock_ends_after_60_seconds_without_a_failure(self):
        bad = gen.good("status")
        bad.set("Authorization", "Bearer " + TOKEN2)
        state = bad.state()
        for i in range(5):
            state = at(state, 1000.0 + i)
            _, state = servegate.decide(bad.facts(), state)
        for moment, want in ((1010.0, 429), (1063.9, 429), (1064.0, 401)):
            v, _ = servegate.decide(bad.facts(), at(state, moment))
            self.assertEqual(v.status, want, moment)

    def test_a_failure_while_locked_extends_the_lock(self):
        bad = gen.good("status")
        bad.set("Authorization", "Bearer " + TOKEN2)
        state = bad.state()
        for i in range(5):
            state = at(state, 1000.0 + i)
            _, state = servegate.decide(bad.facts(), state)
        state = at(state, 1050.0)
        v, state = servegate.decide(bad.facts(), state)
        self.assertEqual(v.status, 429)
        v, _ = servegate.decide(bad.facts(), at(state, 1100.0))
        self.assertEqual(v.status, 429)  # 60 seconds had not passed since the failure at 1050

    def test_under_the_lock_a_token_of_the_wrong_shape_is_not_compared(self):
        bad = gen.good("status")
        bad.set("Authorization", "Bearer short")
        bad.locked_until = bad.mono + 30
        with mock.patch.object(servegate.hmac, "compare_digest", wraps=servegate.hmac.compare_digest) as spy:
            v = decide_req(bad)
        self.assertEqual((v.status, v.word), (429, "rate"))
        self.assertEqual(spy.call_count, 0)

    def test_a_good_token_of_a_revoked_or_broken_record_is_never_compared(self):
        for rec in (None, {"sha256": "zz", "expires": "2026-12-12"}, {"expires": "2026-12-12"}):
            r = gen.good("status")
            r.rec = rec
            with mock.patch.object(servegate.hmac, "compare_digest", wraps=servegate.hmac.compare_digest) as spy:
                v = decide_req(r)
            self.assertEqual(v.word, "token")
            self.assertEqual(spy.call_count, 0)

    def test_the_record_is_judged_on_the_date_it_is_given(self):
        for date, ok in (("2026-11-12", True), ("2026-12-11", True), ("2026-12-12", False), ("2026-12-13", False),
                         ("2027-01-01", False), ("not a date", False), ("", False)):
            r = gen.good("status")
            r.date = date
            self.assertEqual(isinstance(decide_req(r), servegate.Allow), ok, date)


# ----------------------------------------------------------------------------------------------- no leak


class LeakTests(Prop):
    def test_no_marked_value_reaches_the_response_bytes(self):
        def make(g):
            r = gen.random_req(g)
            marks = []
            for i in range(g.between(1, 4)):
                m = "ZQX" + g.text("0123456789ABCDEF", 12, 24)
                marks.append(m)
                r.add(f"X-Mark{i}", m)
            r.target = r.target + ("&" if "?" in r.target else "?") + "mark=" + g.text("0123456789abcdef", 6, 10)
            r.marks = marks
            return r

        def check(r):
            v = decide_req(r)
            if not isinstance(v, servegate.Refuse):
                return None
            body = servegate.refusal_body(v.word).decode("ascii")
            for mark in r.marks + [TOKEN]:  # every piece of four characters of a marked value or the token
                for i in range(len(mark) - 3):
                    if mark[i:i + 4] in body:
                        return f"{mark[i:i + 4]!r} of a marked value is in the response bytes"
            for p in [val for _n, val in r.headers] + [r.target]:
                if len(p) >= 6 and p in body:
                    return f"the request value {p[:20]!r} is in the response bytes"
            return None

        self.forall(make, check)

    def test_a_refusal_is_the_same_bytes_for_the_same_word(self):
        seen = {}

        def check(r):
            v = decide_req(r)
            if isinstance(v, servegate.Refuse):
                b = servegate.refusal_body(v.word)
                if seen.setdefault(v.word, b) != b:
                    return "two responses for one word differ"
            return None

        self.forall(gen.random_req, check)

    def test_the_envelope_of_a_refusal(self):
        for w in sorted(WORDS):
            obj = json.loads(servegate.refusal_body(w).decode("ascii"))
            self.assertEqual(list(obj), ["schema", "ok", "code", "word", "request", "logged"])
            self.assertEqual((obj["schema"], obj["ok"], obj["word"], obj["request"], obj["logged"]),
                             (1, False, w, None, False))
            self.assertEqual(obj["code"], 64 if w == "body" else 2)


# ------------------------------------------------------------------------------------ the truth table


class TruthTableTests(unittest.TestCase):
    """Enumerated, not sampled: 8 Host values, 8 Origin values, 5 Sec-Fetch-Site values, 3 methods, the page and a route."""

    HOSTS = ["good", "other_port", "localhost", "no_port", "empty", "other_address", "missing", "doubled"]
    ORIGINS = ["missing", "good", "null", "localhost", "other_port", "https", "empty", "doubled"]
    SITES = [None, "same-origin", "same-site", "cross-site", "none"]
    P = str(PORT)

    def host_value(self, k):
        return {"good": f"127.0.0.1:{self.P}", "other_port": f"127.0.0.1:{PORT + 1}", "localhost": f"localhost:{self.P}",
                "no_port": "127.0.0.1", "empty": "", "other_address": f"127.0.0.2:{self.P}"}.get(k)

    def origin_value(self, k):
        return {"good": f"http://127.0.0.1:{self.P}", "null": "null", "localhost": f"http://localhost:{self.P}",
                "other_port": f"http://127.0.0.1:{PORT + 1}", "https": f"https://127.0.0.1:{self.P}",
                "empty": ""}.get(k)

    def build(self, host, origin, site, method, kind):
        if kind == "page":
            r = gen.good("page")
        elif method == "GET":
            r = gen.good("status")
        elif method == "POST":
            r = gen.good("queue.close")
        else:
            r = gen.good("status")
            r.method = "DELETE"
        r.drop("Host").drop("Origin").drop("Sec-Fetch-Site")
        if host == "doubled":
            r.add("Host", self.host_value("good")).add("Host", self.host_value("good"))
        elif host != "missing":
            r.add("Host", self.host_value(host))
        if origin == "doubled":
            r.add("Origin", self.origin_value("good")).add("Origin", self.origin_value("good"))
        elif origin != "missing":
            r.add("Origin", self.origin_value(origin))
        if site:
            r.add("Sec-Fetch-Site", site)
        return r

    def expected(self, host, origin, site, method, kind):
        if host == "doubled" or origin == "doubled":
            return "header"
        if host != "good":
            return "host"
        if kind == "page":
            if origin not in ("missing", "good"):
                return "origin"
            return "origin" if site not in (None, "same-origin", "none") else "allow"
        if method != "GET" and origin == "missing":
            return "origin"
        if origin not in ("missing", "good"):
            return "origin"
        if site not in (None, "same-origin"):
            return "origin"
        return "method" if method == "DELETE" else "allow"

    def test_every_combination(self):
        n = 0
        for host in self.HOSTS:
            for origin in self.ORIGINS:
                for site in self.SITES:
                    for kind, methods in (("page", ("GET",)), ("route", ("GET", "POST", "DELETE"))):
                        for method in methods:
                            r = self.build(host, origin, site, method, kind)
                            want = self.expected(host, origin, site, method, kind)
                            v = decide_req(r)
                            got = "allow" if isinstance(v, servegate.Allow) else v.word
                            n += 1
                            self.assertEqual(got, want, f"host={host} origin={origin} site={site} {method} {kind}")
        self.assertEqual(n, 8 * 8 * 5 * 4)


# ------------------------------------------------------------------------------------------------ rate


class RateTests(Prop):
    def run_timeline(self, g, with_noise):
        """Valid requests of random classes at random times; returns the verdicts for the valid ones only. The noise
        (invalid tokens in between) is drawn from a second stream, so the valid requests are the same with and without."""
        noise = gen.Gen(g.seed * 7919 + 1)
        state = gen.good("status").state()
        t = 1000.0
        out, times = [], []
        for _ in range(g.between(20, 120)):
            t += g.pick([0.0, 0.0, 0.001, 0.02, 0.1, 0.3, 1.0, 2.0, 30.0]) * g.rand()
            rid = g.pick([r for r in gen.ROUTE_IDS if r != "page"])
            if with_noise:
                for _ in range(noise.pick([0, 0, 1, 3, 8])):
                    bad = gen.good("status")
                    bad.set("Authorization", "Bearer " + TOKEN2)
                    _, state = servegate.decide(bad.facts(), at(state, t))
            v, state = servegate.decide(gen.good(rid).facts(), at(state, t))
            out.append((rid, isinstance(v, servegate.Allow), v.word if isinstance(v, servegate.Refuse) else None))
            times.append(t)
        return out, times

    def test_allowed_requests_in_any_window_stay_within_burst_plus_rate_times_window(self):
        limits = {"auth": (10.0, 30), "read": (5.0, 20), "write": (2.0, 6), "run": (1.0, 3)}
        for seed in SEEDS:
            g = gen.Gen(seed)
            for case in range(max(20, PROP_N // 50)):
                out, times = self.run_timeline(g, with_noise=g.chance(0.5))
                for name, (rate, burst) in limits.items():
                    ts = [t for (rid, ok, _), t in zip(out, times)
                          if ok and (name == "auth" or gen.GOLDEN[rid][3] == name)]
                    for i in range(len(ts)):
                        for j in range(i, len(ts)):
                            window = ts[j] - ts[i]
                            self.assertLessEqual(j - i + 1, burst + rate * window + 1e-6,
                                                 f"seed {seed} case {case} {name} window {window}")

    def test_a_flood_of_invalid_tokens_never_lowers_the_allowance_of_a_valid_one(self):
        for seed in SEEDS:
            for case in range(max(10, PROP_N // 100)):
                quiet, _ = self.run_timeline(gen.Gen(seed * 1000 + case), with_noise=False)
                noisy, _ = self.run_timeline(gen.Gen(seed * 1000 + case), with_noise=True)
                self.assertEqual(noisy, quiet, f"seed {seed} case {case}")

    def test_a_refusal_for_rate_is_429_with_a_retry_after(self):
        r = gen.good("queue.list")
        r.buckets["auth"] = (0.0, r.mono)
        v = decide_req(r)
        self.assertEqual((v.status, v.word, v.authed), (429, "rate", False))
        self.assertGreaterEqual(v.retry_after, 1)

    def test_a_refusal_before_the_token_does_not_take_a_place(self):
        r = gen.good("queue.list")
        r.set("Host", "localhost:1")
        before = r.state()
        _, after = servegate.decide(r.facts(), before)
        self.assertEqual(after, before)

    def test_the_bucket_refills_with_time(self):
        r = gen.good("queue.list")
        r.buckets["read"] = (0.0, r.mono - 0.2)  # 5 per second: one place after 0.2 seconds
        self.assertIsInstance(decide_req(r), servegate.Allow)
        r.buckets["read"] = (0.0, r.mono - 0.1)
        self.assertEqual(decide_req(r).word, "rate")


# --------------------------------------------------------------------------------------- closed table


class ClosedTableTests(Prop):
    METHODS = ["GET", "POST", "DELETE"]

    def near_misses(self, g):
        """A request for a path that is close to a route, with headers that are right for its method."""
        rid = g.pick([r for r in gen.ROUTE_IDS])
        method, target, _body, _c = gen.GOLDEN[rid]
        path, q, query = target.partition("?")
        kind = g.below(9)
        if kind == 1:
            path = path.upper()
        elif kind == 2:
            path += "/"
        elif kind == 3:
            path += "/" + g.pick(["x", "check", "answer", "v1"])
        elif kind == 4:
            path = path.replace("Q-0001", g.pick(["Q-1", "Q-00001", "q-0001", "Q-000a", "0001", "Q-", "Q-12345"]))
        elif kind == 5:
            path = path.replace("helper", g.pick(["Helper", "", "a" * 41, "a b", "a.b", "ok_1-2", "x"]))
        elif kind == 6:
            method = g.pick(self.METHODS)
        elif kind == 7:
            path = path.replace("v1", g.pick(["v2", "V1", "", "v1x"]))
        elif kind == 8:
            path = g.pick(["/v1", "/v1/", "/v1/queue/Q-0001", "/v1/agents/helper", "/v1/kill", "/v1/kill/off", "/",
                           "/v1/admin", "/v1/rules", "/v1/token", "/v1/serve", "/v1/queue/Q-0001/reopen"])
        r = gen.good("queue.close" if method == "POST" else "status")
        r.method, r.target = method, path + (q + query)
        if method == "POST":
            r.set("Content-Length", "2")
        elif method == "DELETE":
            r.drop("Content-Length")
        r.drop("Authorization").add("Authorization", "Bearer " + TOKEN)
        if method == "GET" and path == "/":
            r.drop("Authorization")
        return r

    def test_decide_allows_exactly_the_rows_of_the_table(self):
        shapes = {}
        for rid, (method, target, _b, _c) in gen.GOLDEN.items():
            shapes[(method, target.partition("?")[0])] = rid

        def want(r):
            path, q, query = r.target.partition("?")
            if q and not (r.method == "GET" and path == "/v1/queue" and query == "status=open&kind=task"):
                return None  # only queue.list takes a query
            if (r.method, path) in shapes:
                return shapes[(r.method, path)]
            m = re.fullmatch(r"/v1/queue/(Q-\d{4,})/(answer|close)", path)
            if m and r.method == "POST":
                return "queue." + m.group(2)
            m = re.fullmatch(r"/v1/agents/([a-z0-9_-]{1,40})/check", path)
            if m and r.method == "POST":
                return "agents.check"
            return None

        def check(r):
            v = decide_req(r)
            expected = want(r)
            if expected is None and isinstance(v, servegate.Allow):
                return f"allowed {r.method} {r.target} as {v.route}"
            if expected is not None and not (isinstance(v, servegate.Allow) and v.route == expected):
                return f"{r.method} {r.target} should be {expected}, got {norm(v)}"
            return None

        self.forall(self.near_misses, check)

    def test_the_routes_of_the_code_equal_the_golden_table_and_the_docs(self):
        code = {(r.id, r.method, r.path) for r in servegate.ROUTES}
        docs = set()
        for line in (REPO / "docs" / "serve.md").read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\| ([a-z.]+) \| `(GET|POST|DELETE) ([^`?]+)(?:\?[^`]*)?` \| ", line)
            if m and m.group(1) not in ("id",):
                docs.add((m.group(1), m.group(2), m.group(3)))
        self.assertEqual(code, docs)
        self.assertEqual({r.id for r in servegate.ROUTES}, set(gen.ROUTE_IDS))
        by_id = {r.id: r for r in servegate.ROUTES}
        for rid, (method, target, _b, cls) in gen.GOLDEN.items():
            self.assertEqual(by_id[rid].method, method)
            self.assertEqual(by_id[rid].cls, cls)
            self.assertEqual(by_id[rid].body_cap, gen.BODY_CAPS.get(rid, 0), rid)

    def test_the_docs_table_columns_match_the_routes(self):
        rows = {}
        for line in (REPO / "docs" / "serve.md").read_text(encoding="utf-8").splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 8 and cells[0] in gen.GOLDEN:
                rows[cells[0]] = cells
        self.assertEqual(set(rows), set(gen.ROUTE_IDS))
        for r in servegate.ROUTES:
            cells = rows[r.id]
            self.assertEqual(cells[4], r.cls, r.id)
            self.assertEqual(int(cells[7]), r.body_cap, r.id)
            if r.id == "kill.on":
                self.assertTrue(cells[5].startswith("never"))
                self.assertTrue(r.skips_rules)
                self.assertFalse(r.stopped)
            else:
                self.assertEqual(cells[5], "yes" if r.stopped else "no", r.id)
                self.assertFalse(r.skips_rules)

    def test_no_route_can_turn_the_switch_off_touch_a_token_or_name_a_path(self):
        banned = ("off", "token", "serve", "rules", "autonomy", "archive", "schedule", "publish", "run", "login",
                  "seal", "settle", "calibrate", "recover", "anchor", "petition", "reopen", "memory", "upload", "file")
        for r in servegate.ROUTES:
            parts = re.split(r"[/.{}]+", r.path.lower() + "." + r.id.lower())
            for b in banned:
                self.assertNotIn(b, parts, f"{r.id} {r.path}")


# ------------------------------------------------------------------------------------------- channel


class ChannelTests(Prop):
    def test_any_channel_but_local_is_refused(self):
        def make(g):
            r = gen.good(g.pick(gen.ROUTE_IDS))
            r.channel = g.pick(["relay", "remote", "Local", "local ", "", "LOCAL", g.text(string.printable[:-5], 1, 8)])
            return r

        self.forall(make, lambda r: None if decide_req(r).word == "peer" else "a channel other than local was not refused")

    def test_the_channel_is_a_closed_set_of_one(self):
        self.assertEqual(tuple(servegate.CHANNELS), ("local",))


# --------------------------------------------------------------------------------- the body parser


def fits(route, params):
    """Independent check that params fit the route's schema (types, no unknown key)."""
    schema = {
        "agents.check": ({}, ()),
        "queue.close": ({}, ()),
        "queue.add": ({"kind": str, "title": str, "recommendation": str, "if_not_open": bool}, ("kind", "title")),
        "queue.answer": ({"answer": str, "revisit_if": str}, ("answer",)),
        "kill.on": ({"reason": str}, ()),
    }[route]
    types, required = schema
    if not isinstance(params, dict) or not set(params) <= set(types) or not set(required) <= set(params):
        return False
    for k, v in params.items():
        if type(v) is not types[k]:
            return False
        if type(v) is str and (not v.isprintable() or len(v) > 4096):
            return False
    return True


class BodyParserTests(Prop):
    OK = {
        "agents.check": [b"{}", b' { } '],
        "queue.close": [b"{}"],
        "queue.add": [b'{"kind":"task","title":"T"}', b'{"kind":"decision","title":"T","recommendation":"r","if_not_open":true}',
                      '{"kind":"task","title":"caf\u00e9"}'.encode("utf-8")],
        "queue.answer": [b'{"answer":"A"}', b'{"answer":"A","revisit_if":"none"}'],
        "kill.on": [b"{}", b'{"reason":"because"}'],
    }
    BAD = [
        b"", b" ", b"null", b"[]", b"[1]", b"1", b'"x"', b"true", b"{", b"}{", b"{}{}", b"{} x", b"{'a':1}",
        b'{"a":1}', b'{"kind":"task","title":"T","extra":1}', b'{"kind":"task","kind":"task","title":"T"}',
        b'{"kind":NaN}', b'{"kind":Infinity}', b'{"kind":-Infinity}', b'{"kind":1.5}', b'{"kind":1e3}',
        b'{"kind":"task","title":5}', b'{"kind":"task","title":null}', b'{"kind":"task","title":true}',
        b'{"kind":"task","title":"a\\u0000b"}', b'{"kind":"task","title":"\\ud800"}', b'{"kind":"task","title":"a\nb"}',
        b'{"kind":"task","title":"' + b"a" * 4097 + b'"}', b"\xef\xbb\xbf{}", b"\xff\xfe{}", b'{"kind":"task","title":"\xff"}',
        b'{"kind":"task","title":"T","if_not_open":"yes"}', b'{"kind":"task","title":"T","if_not_open":1}',
        b'{"answer":["A"]}', b'{"answer":{"a":"b"}}', b'{"reason":5}', b'{"a":{"b":{"c":{"d":{"e":{"f":{"g":1}}}}}}}',
        b"[" * 2000 + b"]" * 2000, b'{"a":' * 500 + b"1" + b"}" * 500, b'{"kind":' + b"9" * 400 + b"}",
    ]

    def test_good_bodies_are_parsed_to_exactly_their_fields(self):
        for route, bodies in self.OK.items():
            for raw in bodies:
                with self.subTest(route=route, body=raw[:40]):
                    p = servegate.parse_body(route, raw)
                    self.assertNotIsInstance(p, servegate.Refuse, p)
                    self.assertEqual(p, json.loads(raw.decode("utf-8")))
                    self.assertTrue(fits(route, p))

    def test_bad_bodies_are_refused_with_400_body_on_every_route(self):
        for route in self.OK:
            for raw in self.BAD:
                with self.subTest(route=route, body=raw[:40]):
                    p = servegate.parse_body(route, raw)
                    self.assertIsInstance(p, servegate.Refuse, f"{route} accepted {raw[:40]!r}")
                    self.assertEqual((p.status, p.word), (400, "body"))

    def test_missing_required_fields_and_unknown_keys_are_refused(self):
        for route, raw in (("queue.add", b"{}"), ("queue.add", b'{"kind":"task"}'), ("queue.answer", b"{}"),
                           ("queue.close", b'{"x":1}'), ("agents.check", b'{"x":"y"}'), ("kill.on", b'{"x":"y"}')):
            p = servegate.parse_body(route, raw)
            self.assertIsInstance(p, servegate.Refuse, (route, raw))
            self.assertEqual((p.status, p.word), (400, "body"))

    def test_a_body_over_the_cap_is_refused_before_it_is_parsed(self):
        raw = b'{"reason":"' + b"a" * 600 + b'"}'
        self.assertGreater(len(raw), 512)
        p = servegate.parse_body("kill.on", raw)
        self.assertEqual((p.status, p.word), (400, "body"))
        with mock.patch.object(servegate.json, "loads", side_effect=AssertionError("parsed")):
            servegate.parse_body("kill.on", raw)

    def test_the_parser_is_total_over_random_bytes_and_json(self):
        pieces = [b"{", b"}", b"[", b"]", b'"', b":", b",", b"null", b"true", b"1", b"-0", b"1.0", b"NaN", b"\\u0000",
                  b"\\ud800", b"\xef\xbb\xbf", b"\x00", b"\xff", b"kind", b"title", b"answer", b" ", b"\n"]

        def make(g):
            route = g.pick(sorted(self.OK))
            if g.chance(0.5):
                raw = b"".join(g.pick(pieces) for _ in range(g.between(0, 40)))
            else:
                raw = bytes(g.bits(8) for _ in range(g.between(0, 60)))
            if g.chance(0.2):
                raw = b'{"kind":"task","title":"x"' + raw + b"}"
            return route, raw

        def check(case):
            route, raw = case
            p = servegate.parse_body(route, raw)
            if isinstance(p, servegate.Refuse):
                return None if (p.status, p.word) == (400, "body") else f"refusal {p}"
            return None if fits(route, p) else f"accepted {raw[:60]!r} as {p!r}"

        self.forall(make, check)

    def test_big_integers_floats_and_deep_nesting_do_not_crash(self):
        for raw in (b'{"kind":' + b"9" * 5000 + b"}", b"[" * 100000, b'{"a":' * 100000):
            p = servegate.parse_body("queue.add", raw[:4096] if len(raw) > 4096 else raw)
            self.assertIsInstance(p, servegate.Refuse)


if __name__ == "__main__":
    unittest.main()
