"""Tests of the test tools themselves (W6.1.1): the generators, the shrinker, the oracle and the catalogue.

They do not need `umwayi/servegate.py`, so they pass before the code exists. If the catalogue and the oracle disagree,
the catalogue (written from W6.R16.1) or the oracle (written from W6.R5) is wrong, and no gate test can be trusted.
"""

import unittest

from tests.serve import gen, oracle
from tests.serve.support import TOKEN


def _cases(seed, n):
    g = gen.Gen(seed)
    return [gen.describe(gen.random_req(g)) for _ in range(n)]


class GeneratorTests(unittest.TestCase):
    def test_the_same_seed_gives_the_same_cases(self):
        self.assertEqual(_cases(11, 300), _cases(11, 300))

    def test_another_seed_gives_other_cases(self):
        self.assertNotEqual(_cases(11, 300), _cases(12, 300))

    def test_only_getrandbits_and_random_are_used(self):
        # the numbers must not depend on the Python version: below() is rejection sampling over getrandbits
        g = gen.Gen(5)
        self.assertEqual([g.below(1) for _ in range(5)], [0] * 5)
        seen = {g.below(7) for _ in range(500)}
        self.assertEqual(seen, set(range(7)))
        import inspect
        src = inspect.getsource(gen.Gen)
        for banned in ("randrange", "randint", ".choice(", ".shuffle(", ".sample(", "uniform", "gauss"):
            self.assertNotIn(banned, src)

    def test_the_catalogue_has_at_least_45_named_faults_with_distinct_names(self):
        names = [m.name for m in gen.MUTATIONS]
        self.assertEqual(len(names), len(set(names)))
        self.assertGreaterEqual(len(gen.MUST), 45)
        self.assertGreaterEqual(len(gen.BENIGN), 10)
        self.assertEqual({m.word for m in gen.MUST},
                         {"method", "peer", "header", "host", "target", "token", "origin", "route", "length", "type",
                          "rate"})

    def test_every_route_has_a_golden_request_and_a_cap(self):
        self.assertEqual(set(gen.GOLDEN), set(gen.ROUTE_IDS))
        for rid in gen.ROUTE_IDS:
            if gen.GOLDEN[rid][0] == "POST":
                self.assertIn(rid, gen.BODY_CAPS)


class ShrinkerTests(unittest.TestCase):
    def test_it_finds_a_planted_two_header_fault(self):
        def failing(r):
            have = {(n, v) for n, v in r.headers}
            return ("X-A", "1") in have and ("X-B", "2") in have

        for seed in (1, 2, 3):
            g = gen.Gen(seed)
            r = gen.random_req(g)
            for _ in range(30):
                r.add(g.text("abcdefXYZ-", 3, 8), g.text("0123456789abcdef", 1, 60))
            r.headers.insert(g.below(len(r.headers)), ["X-A", "1"])
            r.headers.insert(g.below(len(r.headers)), ["X-B", "2"])
            self.assertTrue(failing(r))
            small = gen.shrink(r, failing)
            self.assertEqual(sorted(map(tuple, small.headers)), [("X-A", "1"), ("X-B", "2")])
            self.assertLessEqual(len(small.target), 1)

    def test_it_shortens_a_value_that_causes_the_failure(self):
        r = gen.good("status")
        r.add("X-Long", "z" * 400)
        small = gen.shrink(r, lambda q: any(n == "X-Long" and len(v) >= 1 for n, v in q.headers))
        self.assertEqual([tuple(h) for h in small.headers], [("X-Long", "z")])


class OracleAgreesWithTheCatalogueTests(unittest.TestCase):
    def verdict(self, req):
        return oracle.judge(*oracle.from_req(req))

    def test_every_golden_request_is_allowed_with_its_route(self):
        for rid in gen.ROUTE_IDS:
            with self.subTest(route=rid):
                v = self.verdict(gen.good(rid))
                self.assertEqual(v[:2], ("allow", rid), v)

    def test_every_fault_is_refused_with_its_word(self):
        applied = 0
        for rid in gen.ROUTE_IDS:
            base = gen.good(rid)
            for m in gen.MUST:
                if not m.applies(base):
                    continue
                applied += 1
                with self.subTest(route=rid, fault=m.name):
                    v = self.verdict(gen.apply_mutation(base, m))
                    self.assertEqual(v[0], "refuse", v)
                    self.assertEqual(v[2], m.word, v)
        self.assertGreater(applied, 500)

    def test_every_fault_applies_to_at_least_one_route(self):
        for m in gen.MUTATIONS:
            with self.subTest(fault=m.name):
                self.assertTrue(any(m.applies(gen.good(r)) for r in gen.ROUTE_IDS))

    def test_harmless_changes_change_nothing(self):
        for rid in gen.ROUTE_IDS:
            base = gen.good(rid)
            first = self.verdict(base)
            for m in gen.BENIGN:
                if not m.applies(base):
                    continue
                with self.subTest(route=rid, change=m.name):
                    self.assertEqual(self.verdict(gen.apply_mutation(base, m)), first)

    def test_a_refusal_after_the_token_is_marked_authed_and_one_before_is_not(self):
        r = gen.apply_mutation(gen.good("status"), next(m for m in gen.MUST if m.name == "origin_null"))
        self.assertEqual(self.verdict(r), ("refuse", 403, "origin", True))
        r = gen.apply_mutation(gen.good("status"), next(m for m in gen.MUST if m.name == "host_localhost"))
        self.assertEqual(self.verdict(r), ("refuse", 403, "host", False))

    def test_the_throttle_in_the_oracle(self):
        r = gen.good("status")
        r.set("Authorization", "Bearer " + gen.TOKEN2)
        r.locked_until = r.mono + 10
        self.assertEqual(self.verdict(r)[:3], ("refuse", 429, "rate"))
        r.locked_until = r.mono
        self.assertEqual(self.verdict(r)[:3], ("refuse", 401, "token"))
        r = gen.good("status")
        r.locked_until = r.mono + 10
        self.assertEqual(self.verdict(r)[:2], ("allow", "status"))  # a valid token is never slowed by failures

    def test_the_bucket_arithmetic_in_the_oracle(self):
        r = gen.good("status")
        r.buckets["auth"] = (0.0, r.mono - 0.05)  # 0.5 token: not yet
        self.assertEqual(self.verdict(r)[2], "rate")
        r.buckets["auth"] = (0.0, r.mono - 0.1)  # exactly 1 token
        self.assertEqual(self.verdict(r)[:2], ("allow", "status"))

    def test_the_fixed_token_has_the_shape_of_a_real_one(self):
        self.assertEqual(len(TOKEN), 48)
        self.assertTrue(TOKEN.startswith("umt1_"))


if __name__ == "__main__":
    unittest.main()
