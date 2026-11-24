"""M4 a: the `providers` section of units.yaml, and `provider_gate`.

A provider names a cost kind (free credits, subscription or paid), the limit the provider sets (in UU) and, written by the owner, an
acceptance. Without an acceptance a free credit or subscription provider is Ask me first; a paid provider is Ask me first on every goal.
Nothing here spends or stops anything: the gate is a pure function until the Muse route (M2) calls it. These tests call `check_text`
directly (no child process, so they run on any machine) and the real `budget validate` once.
"""
import tempfile
import unittest
from pathlib import Path

from umwayi import units

TODAY = "2026-11-24"
BASE = "version: 1\n"
MUSE = """providers:
  muse:
    cost_kind: free_credits
    limit:
      credits_uu: 14000
"""
ACCEPT = """    acceptance:
      accepted_free: true
      date: 2026-11-23
      amount_uu: 14000
      source: owner
"""


def parse(text):
    return units.check_text(text, TODAY)


def problems(text):
    u, p = parse(text)
    return [x.message for x in p] if p else []


class ParseTests(unittest.TestCase):
    def test_a_file_without_providers_is_as_before(self):
        u, p = parse(BASE)
        self.assertEqual((p, u.providers), ([], {}))

    def test_a_free_credit_provider_with_and_without_an_acceptance_loads(self):
        u, p = parse(BASE + MUSE)
        self.assertEqual((p, u.providers["muse"].cost_kind, u.providers["muse"].limit, u.providers["muse"].acceptance), ([], "free_credits", {"credits_uu": 14000}, None))
        u, p = parse(BASE + MUSE + ACCEPT)
        self.assertEqual(u.providers["muse"].acceptance["amount_uu"], 14000)
        self.assertEqual(u.providers["muse"].acceptance["accepted_free"], True)

    def test_each_cost_kind_takes_only_its_own_limit_keys(self):
        self.assertEqual(problems(BASE + "providers:\n  a:\n    cost_kind: subscription\n    limit:\n      five_hour_uu: 500\n      weekly_uu: 4000\n"), [])
        self.assertEqual(problems(BASE + "providers:\n  a:\n    cost_kind: paid\n    limit:\n      cap_uu: 300\n"), [])
        for bad in ("free_credits\n    limit:\n      weekly_uu: 5", "subscription\n    limit:\n      credits_uu: 5", "paid\n    limit:\n      credits_uu: 5"):
            with self.subTest(bad=bad[:30]):
                self.assertTrue(problems(BASE + "providers:\n  a:\n    cost_kind: " + bad + "\n"))

    def test_planted_faults_each_is_a_problem_with_a_line_number(self):
        cases = {
            "a bad cost kind": "providers:\n  a:\n    cost_kind: free\n    limit:\n      credits_uu: 1\n",
            "no limit": "providers:\n  a:\n    cost_kind: free_credits\n",
            "a negative limit": "providers:\n  a:\n    cost_kind: free_credits\n    limit:\n      credits_uu: -5\n",
            "an unknown key": "providers:\n  a:\n    cost_kind: free_credits\n    limit:\n      credits_uu: 5\n    note: x\n",
            "an upper case name": "providers:\n  Muse:\n    cost_kind: free_credits\n    limit:\n      credits_uu: 5\n",
            "providers not a mapping": "providers: 3\n",
        }
        for label, body in cases.items():
            with self.subTest(label):
                u, p = parse(BASE + body)
                self.assertIsNone(u)
                self.assertTrue(p and all(x.line >= 1 for x in p), label)

    def test_an_acceptance_must_be_whole_and_true_and_dated_and_not_in_the_future(self):
        head = MUSE + "    acceptance:\n"
        good = "      accepted_free: true\n      date: 2026-11-23\n      amount_uu: 14000\n      source: owner\n"
        self.assertEqual(problems(BASE + head + good), [])
        for label, body in {
            "accepted false": good.replace("true", "false"),
            "a future date": good.replace("2026-11-23", "2026-12-24"),
            "a date that is not real": good.replace("2026-11-23", "2026-13-40"),
            "an amount that is not a number": good.replace("14000", "lots"),
            "a source that is not owner or https": good.replace("owner", "a friend"),
            "a missing key": good.replace("      source: owner\n", ""),
            "an extra key": good + "      note: x\n",
        }.items():
            with self.subTest(label):
                self.assertTrue(problems(BASE + head + body), label)

    def test_a_paid_provider_takes_no_acceptance(self):
        text = BASE + "providers:\n  a:\n    cost_kind: paid\n    limit:\n      cap_uu: 300\n" + ACCEPT
        self.assertTrue(any("asks on every goal" in m for m in problems(text)))

    def test_the_change_entry_state_lists_the_provider_and_its_acceptance_without_a_secret_field(self):
        u, _ = parse(BASE + MUSE + ACCEPT)
        st = u.state()
        self.assertEqual(st["providers.muse.cost_kind"], "free_credits")
        self.assertEqual(st["providers.muse.limit.credits_uu"], "14000")
        self.assertEqual(st["providers.muse.acceptance"], "14000 UU (2026-11-23, owner)")


class GateTests(unittest.TestCase):
    def gate(self, text, name="muse"):
        u, p = parse(text)
        self.assertEqual(p, [])
        return units.provider_gate(u, name)

    def test_an_accepted_free_provider_is_yes_and_every_other_state_asks_with_a_fixed_reason(self):
        self.assertEqual(self.gate(BASE + MUSE + ACCEPT), ("yes", "accepted"))
        self.assertEqual(self.gate(BASE + MUSE), ("ask", "no_acceptance"))
        self.assertEqual(self.gate(BASE + MUSE + ACCEPT, "nobody"), ("ask", "provider_unknown"))
        self.assertEqual(self.gate(BASE), ("ask", "provider_unknown"))
        paid = BASE + "providers:\n  muse:\n    cost_kind: paid\n    limit:\n      cap_uu: 300\n"
        self.assertEqual(self.gate(paid), ("ask", "paid_asks_every_goal"))

    def test_a_subscription_needs_an_acceptance_too(self):
        sub = BASE + "providers:\n  muse:\n    cost_kind: subscription\n    limit:\n      weekly_uu: 4000\n"
        self.assertEqual(self.gate(sub), ("ask", "no_acceptance"))
        self.assertEqual(self.gate(sub + ACCEPT), ("yes", "accepted"))


class ValidateTests(unittest.TestCase):
    def test_validate_names_the_providers_and_a_file_without_them_prints_as_before(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "units.yaml").write_text(BASE + MUSE, encoding="utf-8")
            code, lines = units.validate(root, TODAY)
            self.assertEqual(code, 0)
            self.assertTrue(lines[0].endswith("; 1 provider(s)"), lines[0])
            (root / "units.yaml").write_text(BASE, encoding="utf-8")
            self.assertNotIn("provider", units.validate(root, TODAY)[1][0])


if __name__ == "__main__":
    unittest.main()
