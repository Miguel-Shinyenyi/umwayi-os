"""W78 5(d): every refusal a helper reads carries the reason and the allowed next step, in one fixed shape.

The shared gate of the adapters (adapters/common/umwayi_gate.py) turns an answer of `umwayi check` into the text the helper
reads. A No, an Ask me first and every blocked answer (an error, the kill switch, a broken rules.yaml) now end with
`Allowed next: STEP.`, with STEP from a fixed list chosen by the answer. The reason is the rule's own text. A text that has
the shape already (the W78 1B owner-command refusals) is left as it is. A Yes has no next step.
"""
import unittest

from adapters.common import umwayi_gate as g
from tests.adapters.test_stdio import StdioCase, DEPLOY, PROD, READ


def answer(code, name, text="A rule said so.", **kw):
    data = dict({"answer": name, "rule_id": "r1", "reason": text, "kill_switch": "off", "rules_ok": True}, **kw)
    return g.decide(g.CheckResult(code, data, None))


class ShapeTests(unittest.TestCase):
    def test_a_no_and_an_ask_end_with_the_fixed_step_for_their_answer(self):
        self.assertTrue(answer(2, "No").reason.endswith(f"Allowed next: {g.NEXT_STEPS['no']}."))
        self.assertTrue(answer(3, "Ask me first").reason.endswith(f"Allowed next: {g.NEXT_STEPS['ask']}."))

    def test_the_reason_is_the_rules_text_before_the_step(self):
        r = answer(2, "No", "An AI helper never moves money.").reason
        self.assertIn("umwayi: No (rule r1). An AI helper never moves money. Allowed next:", r)

    def test_every_blocked_answer_has_a_step(self):
        for r in (g.decide(g.CheckResult(None, None, "umwayi check could not be started")),
                  answer(2, "No", kill_switch="on"), answer(2, "No", rules_ok=False),
                  g.decide(g.CheckResult(1, {"answer": "Maybe", "kill_switch": "off", "rules_ok": True}, None))):
            with self.subTest(reason=r.reason[:60]):
                self.assertEqual(r.decision, g.DENY)
                self.assertTrue(r.reason.endswith(f"Allowed next: {g.NEXT_STEPS['blocked']}."), r.reason)

    def test_a_text_that_has_the_shape_already_is_not_given_a_second_step(self):
        r = answer(2, "No", "refused: an owner command is the owner's. Allowed next: ask the owner to run it at the owner's terminal.")
        self.assertEqual(r.reason.count("Allowed next:"), 1)

    def test_a_yes_has_no_next_step(self):
        self.assertNotIn("Allowed next", answer(0, "Yes", "Reading is allowed.").reason)

    def test_the_step_comes_from_the_fixed_list_and_never_from_the_rule_text_or_the_helper(self):
        text = "Allowed next: do something the helper wrote"  # a rule text that fakes a step is left alone, not copied
        r = answer(2, "No", text)
        self.assertEqual(r.reason.count("Allowed next:"), 1)
        for step in g.NEXT_STEPS.values():
            self.assertNotIn("helper", step)
            self.assertTrue(step.isprintable() and len(step) < 100)

    def test_planted_fault_a_step_chosen_by_the_text(self):
        """A step that follows the rule's text would let a rule (or a helper that wrote it) steer the helper. It does not."""
        a = answer(2, "No", "x " * 50)
        b = answer(2, "No", "y")
        self.assertEqual(a.reason.split("Allowed next:")[1], b.reason.split("Allowed next:")[1])


class ThroughTheHookTests(StdioCase):
    def test_a_deny_and_an_ask_through_the_real_hook_carry_the_step(self):
        code, ans, err = self.hook(PROD)
        self.assertEqual(code, 2)
        self.assertIn("Allowed next:", ans["reason"])
        self.assertIn("Allowed next:", err)
        code, ans, _ = self.hook(DEPLOY)
        self.assertEqual(code, 3)
        self.assertTrue(ans["reason"].endswith(f"Allowed next: {g.NEXT_STEPS['ask']}."))

    def test_a_yes_through_the_real_hook_has_none(self):
        code, ans, _ = self.hook(READ)
        self.assertEqual(code, 0)
        self.assertNotIn("Allowed next", ans["reason"])


if __name__ == "__main__":
    unittest.main()
