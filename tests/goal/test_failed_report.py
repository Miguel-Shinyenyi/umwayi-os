"""F1 of the 2026-11-18 recordings, built with R1 and option (b) of docs/failed-task-report-design.md.

R1: when a task ends after its builder ran, the branch and tip of the builder's work are recorded with the failed or
stopped move, so the report names them and the worktree. The branch is computed from the ids, the tip is the head of
the kept worktree, the path is computed from the ids. No helper text reaches the report.
(b): the tester and the check prompts name the two files that every task may change by right, so a check that says
"only these files" is not failed by them.
"""

import re
import unittest
from unittest import mock

from tests.goal import cmdsupport as cs
from tests.goal import runsupport as rs
from umwayi import goalpacket as gp
from umwayi import goalrun as gr
from umwayi import goalstate as gs

SECRET = "F1-SECRET-never-in-a-report"
HEX = re.compile(r"[0-9a-f]{40}")


class FailedReportCase(cs.CmdCase):
    def run_goal(self, scripts):
        goal = self.g_approved()
        code = self.call("run", goal, scripts=scripts)
        return goal, code

    def report(self, goal):
        self.out.clear()
        self.assertEqual(self.call("report", goal), 0, self.err)
        return "\n".join(self.out)


class RecordedTipTests(FailedReportCase):
    def failed_by_the_tester(self):
        return self.run_goal([{"steps": rs.builder_steps("G-0001", "T-01"), "spend": 3},
                              {"steps": rs.tester_steps(("fail",)), "spend": 2}])

    def test_a_task_the_tester_failed_keeps_its_branch_and_tip(self):
        goal, code = self.failed_by_the_tester()
        self.assertEqual(code, 2, self.err)
        t = gs.read_task(self.root, goal, "T-01")
        self.assertEqual((t["state"], t["reason"], t["branch"]), ("failed", "tests", "umwayi/g-0001-t-01"))
        self.assertRegex(t["tip"], HEX)
        self.assertRegex(self.logbook_text(), rf"task T-01: running to failed \(reason tests\).*branch umwayi/g-0001-t-01, tip {t['tip']}")

    def test_the_report_names_the_branch_the_tip_and_the_worktree(self):
        goal, _ = self.failed_by_the_tester()
        t = gs.read_task(self.root, goal, "T-01")
        text = self.report(goal)
        self.assertIn(f"- Branch: umwayi/g-0001-t-01, tip {t['tip'][:12]} (kept, not merged)", text)
        path = gr.GIT.worktree_path(str(self.root), goal, "T-01")
        self.assertIn(f"- Worktree: {path} (exists)", text)
        self.assertRegex(text, r"- Files changed: \d")
        self.assertNotIn("not counted", text.split("## T-01")[1].split("##")[0])
        self.assertNotIn("(none)", text.split("- Branch:")[1].split("\n")[0])

    def test_a_builder_that_made_no_commit_says_so(self):
        goal, code = self.run_goal([{"steps": [{"write": "umwayi/piece1.py", "text": "x\n"}, {"exit": 0}], "spend": 1}])
        self.assertEqual(code, 2, self.err)
        t = gs.read_task(self.root, goal, "T-01")
        self.assertEqual((t["state"], t["reason"], t["branch"], t["tip"]), ("failed", "outcome", "", ""))
        text = self.report(goal)
        self.assertIn("- Branch: (none), tip (none) (no commit was recorded)", text)
        self.assertIn("- Worktree: ", text)

    def test_a_task_whose_builder_never_started_has_no_worktree_line(self):
        goal = self.g_approved()
        self.gate_code = 2  # the agents can no longer be gated, so no builder starts
        self.assertEqual(self.call("run", goal, scripts=[]), 3)
        text = self.report(goal)
        self.assertIn("- Branch: (none), tip (none)", text)
        self.assertNotIn("(no commit was recorded)", text)
        self.assertNotIn("- Worktree:", text)

    def test_a_task_in_review_is_as_before(self):
        goal, code = self.run_goal([{"steps": rs.builder_steps("G-0001", "T-01"), "spend": 3},
                                    {"steps": rs.tester_steps(), "spend": 2}, {"steps": rs.check_steps(), "spend": 1}])
        self.assertEqual(code, 0, self.err)
        text = self.report(goal)
        self.assertRegex(text, r"- Branch: umwayi/g-0001-t-01, tip [0-9a-f]{12}\n")
        self.assertNotIn("(kept, not merged)", text)

    def test_no_helper_text_reaches_the_report(self):
        goal, _ = self.run_goal([{"steps": [{"print": SECRET}] + rs.builder_steps("G-0001", "T-01"), "spend": 3},
                                 {"steps": [{"print": SECRET}] + rs.tester_steps(("fail",)), "spend": 2}])
        self.assertNotIn(SECRET, self.report(goal) + self.logbook_text())

    def test_work_found_reads_nothing_when_no_builder_started_or_the_head_is_the_base(self):
        class Fake(gr._Run):
            def __init__(self):
                pass
        r = Fake()
        r.root, r.base, r.branch, r.worktree = self.root, "a" * 40, "umwayi/g-0001-t-01", None
        self.assertIsNone(r.work_found())
        r.worktree = "/nowhere"
        self.assertIsNone(r.work_found())  # no builder_started
        r.builder_started = True
        self.assertIsNone(r.work_found())  # git cannot answer for a path that is not there


class OwnFilesPromptTests(FailedReportCase):
    OWN = gp.own_files("G-0001", "T-01")

    def packet(self):
        return type("P", (), {"goal": "Do the thing.", "checks": ("Only hello.py changed.",)})()

    def test_the_tester_prompt_names_both_files_by_right(self):
        text = gr.tester_prompt(self.packet(), "umwayi/g-0001-t-01", "a" * 40, "N", own=self.OWN)
        for name in self.OWN:
            self.assertIn(name, text)
        self.assertIn("allowed for every task by right", text)
        self.assertIn("Judge each check without them", text)
        self.assertLess(text.index("allowed for every task"), text.index("If you cannot tell"))

    def test_the_check_prompt_names_both_files_too(self):
        text = gr.check_prompt(self.packet(), "umwayi/g-0001-t-01", "a" * 40, 3, ((1, "pass", "Looked."),), "N", own=self.OWN)
        for name in self.OWN:
            self.assertIn(name, text)

    def test_without_the_names_the_prompts_are_what_they_were(self):
        for text in (gr.tester_prompt(self.packet(), "b", "a" * 40, "N"),
                     gr.check_prompt(self.packet(), "b", "a" * 40, 3, ((1, "pass", "Looked."),), "N")):
            self.assertNotIn("by right", text)
        self.assertEqual(gr.own_files_line(()), [])

    def test_the_names_are_fixed_text_never_the_guides_words(self):
        packet = type("P", (), {"goal": f"Do {SECRET}.", "checks": (f"Check {SECRET}",)})()
        line = "\n".join(gr.own_files_line(self.OWN))
        self.assertNotIn(SECRET, line)
        self.assertIn(f"docs-parts/status-log/G-0001-T-01.md and docs-parts/known-limits/G-0001-T-01.md", line)
        self.assertIn(SECRET, gr.tester_prompt(packet, "b", "a" * 40, "N", own=self.OWN))  # only the guide's own check text

    def test_a_real_run_gives_the_tester_and_the_check_the_two_names(self):
        seen = {}

        def spy(name, real):
            def wrapper(*a, **kw):
                text = real(*a, **kw)
                seen.setdefault(name, []).append(text)
                return text
            return wrapper
        with mock.patch.object(gr, "tester_prompt", spy("tester", gr.tester_prompt)), \
                mock.patch.object(gr, "check_prompt", spy("check", gr.check_prompt)):
            goal, code = self.run_goal([{"steps": rs.builder_steps("G-0001", "T-01"), "spend": 3},
                                        {"steps": rs.tester_steps(), "spend": 2}, {"steps": rs.check_steps(), "spend": 1}])
        self.assertEqual(code, 0, self.err)
        for role in ("tester", "check"):
            self.assertEqual(len(seen[role]), 1, role)
            for name in self.OWN:
                self.assertIn(name, seen[role][0], role)


if __name__ == "__main__":
    unittest.main()
