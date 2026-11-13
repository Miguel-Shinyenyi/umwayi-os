"""W9.2 / W9.R2.2: the tester is not the builder. One pure function, tested over every pair of names."""

import itertools
import unittest

from tests.goal import gen
from umwayi import goalpacket as gp

NAMES = ["claude-build", "kiro-test", "claude-guide", "a", "z9", "kiro", "x" * 32]


class RolesTests(unittest.TestCase):
    def test_every_triple_of_names(self):
        for guide, builder, tester in itertools.product(NAMES, repeat=3):
            expect = tester != builder and guide != builder
            self.assertEqual(gp.roles_ok(guide, builder, tester), expect, (guide, builder, tester))

    def test_the_tester_equal_to_the_builder_is_refused_for_every_name(self):
        for n in NAMES:
            self.assertFalse(gp.roles_ok("other", n, n))

    def test_the_guide_equal_to_the_builder_is_refused_for_every_name(self):
        for n in NAMES:
            self.assertFalse(gp.roles_ok(n, n, "other"))

    def test_bad_names_are_refused(self):
        for bad in ("", "A", "1abc", "a b", "a_b", "x" * 33, "a\n", None, 5, ("a",)):
            self.assertFalse(gp.roles_ok(bad, "builder", "tester"), repr(bad))
            self.assertFalse(gp.roles_ok("guide", bad, "tester"), repr(bad))
            self.assertFalse(gp.roles_ok("guide", "builder", bad), repr(bad))

    def test_names_that_differ_only_by_case_or_space_are_not_the_same_agent_but_are_bad_names(self):
        self.assertFalse(gp.roles_ok("guide", "Builder", "builder"))
        self.assertFalse(gp.roles_ok("guide", "builder ", "builder"))

    def test_random_names_never_raise(self):
        def make(g):
            return [g.pick([g.text("abc-9", 0, 5), None, 3, g.text("ABC \n", 0, 4)]) for _ in range(3)]

        def check(case):
            return isinstance(gp.roles_ok(*case), bool)

        gen.run_property(self, make, check, cases=1000, seeds=gen.SEEDS)

    def test_weak_independence_is_a_warning_on_the_same_platform_and_model(self):
        self.assertTrue(gp.weak_independence(("claude-code", "sonnet"), ("claude-code", "sonnet")))
        self.assertFalse(gp.weak_independence(("claude-code", "sonnet"), ("kiro", "sonnet")))
        self.assertFalse(gp.weak_independence(("claude-code", "sonnet"), ("claude-code", "opus")))
        # no model word on both sides counts as the same default model on the same platform
        self.assertTrue(gp.weak_independence(("kiro", ""), ("kiro", "")))
        self.assertFalse(gp.weak_independence(("kiro", ""), ("kiro", "x")))


if __name__ == "__main__":
    unittest.main()
