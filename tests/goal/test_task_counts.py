"""W78 5(g): when a task leaves `running`, the logbook gets one `counts` entry: how many No and Ask me first answers the
rules gave to the helper's calls while the task ran, and how many guard findings. Counts only. A count is not proof of
obedience, and the entry says so.
"""
import unittest

from tests.goal import runsupport as rs
from tests.goal.test_blocked import DELETE, RULES, SECRET, SHELL
from umwayi import goalstate as gs
from umwayi import logbook


def counts(root):
    return [e for e in logbook.read_checked(root) if e.source == gs.SOURCE and e.added.endswith(": counts")]


class CountTests(rs.RunCase):
    def setUp(self):
        super().setUp()
        (self.root / "rules.yaml").write_text(RULES, encoding="utf-8")

    def run_builder(self, steps, rest=None):
        goal = self.approved(1)
        return goal, self.run_task(goal, "T-01", [{"steps": steps, "spend": 5}] + (rest or []))

    def test_two_asks_and_one_no_are_three_numbers(self):
        goal, out = self.run_builder([{"hook": SHELL}, {"hook": SHELL}, {"hook": DELETE}, {"exit": 2}])
        (e,) = counts(self.root)
        self.assertIn("1 No, 2 Ask me first, 0 guard findings.", e.checked)
        self.assertIn("A count is not proof of obedience", e.not_done)

    def test_a_task_without_a_refusal_counts_zeros_and_a_clean_run_writes_one_entry(self):
        goal, out = self.run_builder(rs.builder_steps(), [{"steps": rs.tester_steps()}, {"steps": rs.check_steps()}])
        self.assertEqual(out.state, "in review")
        (e,) = counts(self.root)
        self.assertIn("0 No, 0 Ask me first, 0 guard findings.", e.checked)

    def test_the_entry_holds_no_word_of_the_call_and_the_log_chain_still_reads(self):
        self.run_builder([{"hook": SHELL}, {"exit": 2}])
        text = (self.root / "LOGBOOK.md").read_text(encoding="utf-8")
        self.assertNotIn(SECRET, text)
        self.assertEqual(len(counts(self.root)), 1)
        gs.view(self.root)  # the state reader accepts the new entry kind

    def test_planted_fault_an_unreadable_logbook_writes_no_count_and_does_not_stop_the_move(self):
        from umwayi import goalrun as gr
        self.assertIsNone(gr.count_since(self.root, None))


if __name__ == "__main__":
    unittest.main()
