"""W9.8 / W9.R20: the report. `umwayi goal report G` writes .umwayi/goals/G/report.md (a draft, mode 0600, never in
outbox/) and prints it; `run` prints it at the end. Per task: the state and reason, the runs, the minutes, the UU, the
files changed, the branch and tip, the tester's verdict words, the guide's word, the skipped lines; for the goal: the
spend, what needs the owner, what waits to be merged and the docs. It names no helper output, no diff, no file content.
"""

import os
import stat
import unittest

from tests.goal import cmdsupport as cs
from tests.goal import runsupport as rs
from umwayi import goalstate as gs

SENTINEL = "SENTINEL-IN-THE-HELPER-OUTPUT"
PLANTED_PATH = "/etc/some-planted-path-in-output"


class ReportTests(cs.CmdCase):
    def in_review(self, extra=()):
        goal = self.g_approved()
        builder = [{"print": SENTINEL}, {"print": PLANTED_PATH}] + list(extra) + rs.builder_steps(goal, "T-01")
        scripts = [{"steps": builder, "spend": 9}, {"steps": [{"print": SENTINEL}] + rs.tester_steps(), "spend": 2},
                   {"steps": rs.check_steps(), "spend": 1}]
        self.assertEqual(self.call("run", goal, scripts=scripts), 0, self.err)
        return goal

    def report(self, goal):
        self.out.clear()
        self.assertEqual(self.call("report", goal), 0, self.err)
        path = gs.goal_dir(self.root, goal) / "report.md"
        return path, path.read_text(encoding="utf-8")

    def test_the_report_of_a_task_in_review(self):
        goal = self.in_review()
        path, text = self.report(goal)
        self.assertEqual(text, "\n".join(self.out) + "\n")  # what is printed is what is written
        self.assertEqual(stat.S_IMODE(os.lstat(path).st_mode), 0o600)
        for want in ("## T-01: in review (checked)", "- Runs: builder claude-build (cap 30 UU), tester kiro-test",
                     "check claude-guide", "- Spent: 12 of 30 UU", "- Files changed: 2",
                     "- The tester's verdicts: 1 pass", "- The guide's word: accept",
                     "- Waiting for your merge: T-01 (branch umwayi/g-0001-t-01", "- Needs you: nothing",
                     cs.GOAL_TEXT, "Check 1: Check number 1 of the piece can be answered pass or fail."):
            self.assertIn(want, text)

    def test_no_helper_output_and_no_planted_path_reach_the_report(self):
        goal = self.in_review()
        _path, text = self.report(goal)
        self.assertNotIn(SENTINEL, text)
        self.assertNotIn(PLANTED_PATH, text)
        self.assertNotIn("Looked at check", text)  # the tester's evidence is not stored, so it is never shown

    def test_the_report_of_a_failed_task_and_of_one_that_needs_the_owner(self):
        goal = self.g_approved()
        self.assertEqual(self.call("run", goal, scripts=[{"steps": [{"exit": 2}], "spend": 1}]), 2)
        _p, text = self.report(goal)
        self.assertIn("## T-01: failed (builder)", text)
        goal2 = self.g_approved()
        self.assertEqual(self.call("run", goal2, scripts=[{"steps": [{"exit": 3}], "spend": 1}]), 3)
        _p, text = self.report(goal2)
        self.assertIn("- Needs you: T-01 (ask)", text)

    def test_the_report_is_never_in_outbox(self):
        goal = self.in_review()
        self.report(goal)
        self.assertFalse((self.root / "outbox").exists())

    def test_a_dropped_task_is_listed_as_dropped(self):
        goal = self.g_start(2)
        self.assertEqual(self.g_approve(goal, keep=["T-02"]), 0, self.err)
        _p, text = self.report(goal)
        self.assertIn("## T-01: dropped at approval", text)


if __name__ == "__main__":
    unittest.main()
