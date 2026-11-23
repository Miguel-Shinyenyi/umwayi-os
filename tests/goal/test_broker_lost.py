"""W78 step 5 (5a3): the enforcement broker ended before a helper's run did, and the goal task stops.

`agent run` writes one entry (source `umwayi agent run`, "Enforcement broker lost during the run of agent NAME") and exits 2. The
supervisor reads only that line. The task goes to `needs owner` (reason unclear, cause `broker_lost`) and the next step does not start.
No answer is No: until then every call of the run was refused by the hook. Nothing is undone.
"""
import unittest
from unittest import mock

from tests.goal import cmdsupport as cs
from tests.goal import runsupport as rs
from umwayi import goalrun as gr
from umwayi import goalstate as gs
from umwayi import logbook


class SinceTests(cs.CmdCase):
    def add(self, source, added):
        logbook.append(self.root, logbook.Entry("2026-11-23", source, added, "x", "x"))

    def test_the_agents_entry_after_the_mark_is_found_and_nothing_else_is(self):
        self.add("umwayi agent run", "Enforcement broker lost during the run of agent reviewer")  # before the mark
        mark = gr.logbook_mark(self.root)
        self.assertFalse(gr.broker_lost_since(self.root, mark))
        self.add("umwayi check", "Enforcement broker lost during the run of agent reviewer")  # a helper's source: not read
        self.add("umwayi agent run", "Enforcement broker lost during the run of agent reviewer and more")
        self.assertFalse(gr.broker_lost_since(self.root, mark))
        self.add("umwayi agent run", "Enforcement broker lost during the run of agent reviewer")
        self.assertTrue(gr.broker_lost_since(self.root, mark))
        self.assertFalse(gr.broker_lost_since(self.root, None))


class GoalStopTests(cs.CmdCase):
    def run_goal(self, lost):
        goal = self.g_approved()
        scripts = [{"steps": rs.builder_steps(goal, "T-01"), "spend": 3}, {"steps": rs.tester_steps(), "spend": 2},
                   {"steps": rs.check_steps(), "spend": 1}]
        with mock.patch.object(gr, "broker_lost_since", lambda root, mark: lost):
            return goal, self.call("run", goal, scripts=scripts)

    def test_a_lost_broker_stops_the_task_before_the_tester(self):
        goal, code = self.run_goal(True)
        self.assertEqual(code, 3, self.err)
        t = gs.read_task(self.root, goal, "T-01")
        self.assertEqual((t["state"], t["reason"]), ("needs owner", "unclear"))
        self.assertIn("Cause: broker_lost.", self.logbook_text())
        self.assertEqual(self.children.started(), 1)
        self.assertIn("enforcement broker of the builder run ended", (self.root / "queue.md").read_text(encoding="utf-8"))

    def test_no_lost_broker_is_the_task_as_it_was(self):
        goal, code = self.run_goal(False)
        self.assertEqual(code, 0, self.err)
        self.assertNotIn("broker_lost", self.logbook_text())

    def test_planted_fault_without_the_stop_the_task_would_go_on(self):
        goal = self.g_approved()
        scripts = [{"steps": rs.builder_steps(goal, "T-01"), "spend": 3}, {"steps": rs.tester_steps(), "spend": 2},
                   {"steps": rs.check_steps(), "spend": 1}]
        self.assertEqual(self.call("run", goal, scripts=scripts), 0, self.err)  # the same run with nothing lost


if __name__ == "__main__":
    unittest.main()
