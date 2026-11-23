"""W78 5(d): `umwayi check` itself says the allowed next step after a No and an Ask me first, so every adapter gets it.

The step is one of two fixed sentences chosen by the answer; no rule text, action or helper input reaches it. It is added after everything
a reader used before: in the text output a line after `Reason:`, in the JSON a key `allowed_next` after the others. A Yes has none. The
adapter gate (`adapters/common/umwayi_gate.py`) says the same two sentences, and a test holds the two lists equal.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from umwayi import rules

REPO = Path(__file__).resolve().parent.parent
RULES = """rules:
  - id: read-yes
    title: reads
    text: Reading is allowed.
    verdict: yes
    matchers:
      type: read
  - id: pay-no
    title: no money
    text: "Allowed next: the rule's own text must not become the step."
    verdict: no
    matchers:
      type: pay
  - id: ask-it
    title: ask
    text: The owner decides.
    verdict: ask
    matchers:
      type: deploy
"""


class CheckCase(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory(prefix="uan")
        self.addCleanup(self._t.cleanup)
        self.root = Path(self._t.name)
        (self.root / "rules.yaml").write_text(RULES, encoding="utf-8")

    def check(self, typ, *flags):
        p = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "check", *flags, json.dumps({"type": typ})],
                           capture_output=True, text=True, timeout=60, env=dict(os.environ, PYTHONPATH=str(REPO)))
        self.assertIn(p.returncode, (0, 2, 3), p.stdout + p.stderr)
        return p


class AnswerTests(CheckCase):
    def test_a_no_and_an_ask_say_the_step_in_the_text_after_the_old_lines_and_a_yes_does_not(self):
        no = self.check("pay").stdout
        self.assertEqual(no.splitlines()[0], "No")
        self.assertEqual(no.splitlines()[1], "Rule: pay-no")
        self.assertTrue(no.splitlines()[2].startswith("Reason: "))
        self.assertEqual(no.splitlines()[-1], f"Allowed next: {rules.ALLOWED_NEXT['No']}.")
        ask = self.check("deploy").stdout
        self.assertEqual(ask.splitlines()[-1], f"Allowed next: {rules.ALLOWED_NEXT['Ask me first']}.")
        self.assertNotIn("Allowed next", self.check("read").stdout)

    def test_the_json_has_the_key_last_for_a_no_and_an_ask_and_not_for_a_yes(self):
        no = json.loads(self.check("pay", "--json").stdout)
        keys = list(no)
        self.assertGreater(keys.index("allowed_next"), keys.index("action_ok"))  # after every key an adapter read before
        self.assertEqual(no["allowed_next"], rules.ALLOWED_NEXT["No"])
        self.assertEqual(json.loads(self.check("deploy", "--json").stdout)["allowed_next"], rules.ALLOWED_NEXT["Ask me first"])
        self.assertNotIn("allowed_next", json.loads(self.check("read", "--json").stdout))

    def test_the_step_never_comes_from_a_rules_text_or_the_action(self):
        out = self.check("pay", "--json").stdout
        self.assertEqual(json.loads(out)["allowed_next"], rules.ALLOWED_NEXT["No"])  # the rule's text said otherwise
        for word in ("deploy", "pay"):
            self.assertNotIn(word, json.loads(self.check(word, "--json").stdout)["allowed_next"])

    def test_no_rule_matching_and_an_unreadable_action_are_ask_me_first_with_the_step(self):
        self.assertIn("Allowed next", self.check("unknown").stdout)
        p = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "check", "not json"], capture_output=True, text=True,
                           timeout=60, env=dict(os.environ, PYTHONPATH=str(REPO)))
        self.assertEqual(p.returncode, 3)
        self.assertIn("Allowed next", p.stdout)


class GateTests(unittest.TestCase):
    def test_the_adapter_gate_says_the_same_two_sentences(self):
        sys.path.insert(0, str(REPO))
        from adapters.common import umwayi_gate as g
        self.assertEqual(g.NEXT_STEPS["no"], rules.ALLOWED_NEXT["No"])
        self.assertEqual(g.NEXT_STEPS["ask"], rules.ALLOWED_NEXT["Ask me first"])

    def test_planted_fault_a_yes_never_has_a_step(self):
        self.assertIsNone(rules.Decision("Yes", "r", "x").allowed_next)


if __name__ == "__main__":
    unittest.main()
