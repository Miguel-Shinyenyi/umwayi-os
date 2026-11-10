"""Budget governor, task B.8: the budget_check action type and `umwayi budget status` (B.R1.10, B.R1.12, B.R3.1).

Every test runs `python -m umwayi ...` as a real child process.
"""

import unittest

from tests.agents.support import tree_state
from tests.budget.support import BudgetCase, days_ago, today

END = {"do": "exit", "code": 0}


class BudgetCheckTests(BudgetCase):
    def test_yes_goes_on_and_is_logged_as_a_check(self):
        r = self.run_agent("reviewer", END)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        checks = [e.added for e in self.entries() if e.source == "umwayi check"]
        self.assertEqual(checks, ["Rule agents-yes gave Yes; action type: agent_run",
                                  "Rule budget-yes gave Yes; action type: budget_check"])

    def test_no_is_2_and_nothing_is_reserved_or_started(self):
        r = self.run_agent("spendno", END)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(r.stdout.splitlines()[:3], ["No", "Rule: budget-no", "Reason: This agent has no budget."])
        self.assertIn("Agent spendno was not started.", r.stdout)
        self.assertEqual(self.started(), [])
        self.assertEqual(self.reserves(), [])

    def test_ask_me_first_is_3_with_one_queue_item_once(self):
        for _ in range(2):
            r = self.run_agent("spendask", END)
            self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
            self.assertEqual(r.stdout.splitlines()[0], "Ask me first")
        queue = (self.root / "queue.md").read_text(encoding="utf-8")
        self.assertEqual(queue.count("Spend up to 100 UU on agent spendask?"), 1)
        self.assertEqual(self.started(), [])
        self.assertEqual(self.reserves(), [])

    def test_the_ask_line_says_what_was_added(self):
        r = self.run_agent("spendask", END)
        self.assertIn("Added queue item Q-0001 (decision) for the owner. Answering it does not start the agent; add a "
                      "Yes rule for budget_check to allow it.", r.stdout)
        r = self.run_agent("spendask", END)
        self.assertIn("Queue item Q-0001 already asks the owner about this. Nothing was added.", r.stdout)

    def test_the_budget_check_comes_after_the_limits(self):
        self.limits(per_day=0)
        r = self.run_agent("spendno", END)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)  # the limit refuses first: no rule is asked
        self.assertFalse([e for e in self.entries() if "budget_check" in e.added])


class StatusTests(BudgetCase):
    ROWS = [
        (days_ago(1), "reviewer", "claude-code", 1000000, "measured", 990000),  # another day: not counted today
        (today(), "reviewer", "claude-code", 1000000, "measured", 120000),
        (today(), "second", "claude-code", 1000000, "declared", 400000),
        (today(), "helper", "kiro", 1000000, "unknown", 1000000),
        (today(), "reviewer", "claude-code", 1000000, None, 0),  # open: no settle
    ]

    def test_status_on_a_fixed_ledger(self):
        self.write_ledger(self.ROWS)
        r = self.budget("status")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        lines = r.stdout.splitlines()
        self.assertEqual(lines[0], f"Budget for {today()} (1 UU is one US cent of estimated list price; a "
                                   "subscription is not billed by it)")
        self.assertEqual(lines[1:], [
            "per_day: used 152 UU, reserved 100 UU, left 248 UU (limit 500 UU)",
            "per_agent_per_day helper: used 100 UU, reserved 0 UU, left 200 UU (limit 300 UU)",
            "per_agent_per_day reviewer: used 12 UU, reserved 100 UU, left 188 UU (limit 300 UU)",
            "per_agent_per_day second: used 40 UU, reserved 0 UU, left 260 UU (limit 300 UU)",
            "per_platform_per_day claude-code: used 52 UU, reserved 100 UU, left 248 UU (limit 400 UU)",
            "per_platform_per_day kiro: used 100 UU, reserved 0 UU, left 300 UU (limit 400 UU)",
            "per_run: 100 UU reserved for every start; unknown_worst_case: 100 UU",
            "Of used: measured 8%, declared 26%, unknown 66%",
            "1 reservation(s) of this day have no settle and count in full; if no agent runs now, run umwayi budget "
            "settle-lost --by NAME",
            "There is no units.yaml: every reading is unknown and the limits are the placeholders.",
            "Nothing was started or written.",
        ])
        y = self.budget("status", "--date", days_ago(1))
        self.assertIn("per_day: used 99 UU, reserved 0 UU, left 401 UU", y.stdout)
        self.assertIn("Of used: measured 100%, declared 0%, unknown 0%", y.stdout)

    def test_status_writes_nothing(self):
        self.write_ledger(self.ROWS)
        self.limits(per_day=700)
        before = tree_state(self.root)
        r = self.budget("status")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("per_day: used 152 UU, reserved 100 UU, left 448 UU (limit 700 UU)", r.stdout)
        self.assertIn("units.yaml changed since the last logged change; the change is logged before the next start",
                      r.stdout)
        self.assertEqual(tree_state(self.root), before)
        for args in (("validate",), ("calibrate",), ("status", "--date", days_ago(3))):
            self.budget(*args)
            self.assertEqual(tree_state(self.root), before, args)

    def test_status_with_a_broken_logbook_is_2(self):
        self.write_ledger(self.ROWS)
        with open(self.root / "LOGBOOK.md", "a", encoding="utf-8") as f:
            f.write("edited\n")
        r = self.budget("status")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("Nothing was started or written.", r.stdout)

    def test_usage_errors_are_64(self):
        self.assertEqual(self.budget("status", "--date", "2026-13-01").returncode, 64)
        self.assertEqual(self.budget("settle-lost").returncode, 64)
        self.assertEqual(self.budget("nothing").returncode, 64)


if __name__ == "__main__":
    unittest.main()
