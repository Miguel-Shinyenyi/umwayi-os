"""W78 step 8 (W41 C2) in a goal: tool calls the platform reported and no hook checked stop the task.

`agent run` writes one entry (source `umwayi agent run`, "Unchecked tool calls during the run of agent NAME: N") and exits 2.
The supervisor reads only that number after each role's run. The task goes to `needs owner` (reason unclear, cause
`unchecked_tool_call`), the next step does not start, nothing is undone, and the counts entry holds N as guard findings.
A planning run with such calls has its plan refused. The ids stay in the agent's own entry; the task's entry holds the number.
"""
import unittest
from unittest import mock

from tests.goal import cmdsupport as cs
from tests.goal import runsupport as rs
from umwayi import goalrun as gr
from umwayi import goalstate as gs
from umwayi import logbook


class UncheckedSinceTests(cs.CmdCase):
    def add(self, source, added):
        logbook.append(self.root, logbook.Entry("2026-11-23", source, added, "x", "x"))

    def test_the_numbers_of_the_agents_entries_after_the_mark_are_added(self):
        self.add("umwayi agent run", "Unchecked tool calls during the run of agent a: 9")  # before the mark
        mark = gr.logbook_mark(self.root)
        self.add("umwayi agent run", "Unchecked tool calls during the run of agent reviewer: 2")
        self.add("umwayi agent run", "Unchecked tool calls during the run of agent second: 1")
        self.assertEqual(gr.unchecked_since(self.root, mark), 3)

    def test_other_sources_and_other_words_count_nothing(self):
        mark = gr.logbook_mark(self.root)
        self.add("umwayi check", "Unchecked tool calls during the run of agent reviewer: 5")  # a helper cannot write this source
        self.add("umwayi agent run", "Unchecked tool calls during the run of agent reviewer: five")
        self.add("umwayi agent run", "Unchecked tool calls during the run of agent reviewer: 5 and more")
        self.assertEqual(gr.unchecked_since(self.root, mark), 0)

    def test_no_mark_counts_nothing(self):
        self.assertEqual(gr.unchecked_since(self.root, None), 0)


class GoalStopTests(cs.CmdCase):
    def counts(self):
        import re
        return [int(re.search(r"(\d+) guard findings", e.checked).group(1)) for e in logbook.read_checked(self.root)
                if e.source == gs.SOURCE and e.added.endswith(": counts")]

    def run_goal(self):
        goal = self.g_approved()
        scripts = [{"steps": rs.builder_steps(goal, "T-01"), "spend": 3}, {"steps": rs.tester_steps(), "spend": 2},
                   {"steps": rs.check_steps(), "spend": 1}]
        with mock.patch.object(gr, "unchecked_since", lambda root, mark: 2):
            return goal, self.call("run", goal, scripts=scripts)

    def test_the_builder_with_unchecked_calls_stops_the_task_before_the_tester(self):
        goal, code = self.run_goal()
        self.assertEqual(code, 3, self.err)
        t = gs.read_task(self.root, goal, "T-01")
        self.assertEqual((t["state"], t["reason"]), ("needs owner", "unclear"))
        log = self.logbook_text()
        self.assertIn("Cause: unchecked_tool_call.", log)
        self.assertIn("Tool calls with no check entry during the run: 2.", log)
        self.assertEqual(self.children.started(), 1)  # the tester did not start
        self.assertIn("2 tool call(s) of the builder ran with no check entry", (self.root / "queue.md").read_text(encoding="utf-8"))

    def test_the_counts_entry_holds_the_number_from_a_real_event(self):
        self.run_goal()
        self.assertEqual(self.counts(), [2])

    def test_no_unchecked_calls_is_the_task_as_it_was(self):
        goal = self.g_approved()
        scripts = [{"steps": rs.builder_steps(goal, "T-01"), "spend": 3}, {"steps": rs.tester_steps(), "spend": 2},
                   {"steps": rs.check_steps(), "spend": 1}]
        self.assertEqual(self.call("run", goal, scripts=scripts), 0, self.err)
        self.assertEqual(self.counts(), [0])
        self.assertNotIn("unchecked_tool_call", self.logbook_text())

    def test_planted_fault_without_the_check_the_task_would_go_on(self):
        goal = self.g_approved()
        scripts = [{"steps": rs.builder_steps(goal, "T-01"), "spend": 3}, {"steps": rs.tester_steps(), "spend": 2},
                   {"steps": rs.check_steps(), "spend": 1}]
        with mock.patch.object(gr._Run, "finish_unchecked", lambda self, role, n: None):
            code = self.call("run", goal, scripts=scripts)
        # with the stop removed the same two reported calls change nothing: this is what the tests above would catch
        self.assertEqual(gs.read_task(self.root, goal, "T-01")["state"], "in review", self.err)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
