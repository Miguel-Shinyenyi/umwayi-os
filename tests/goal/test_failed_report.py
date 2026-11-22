"""F1 of the 2026-11-18 recordings, built with R1 and option (b) of docs/failed-task-report-design.md.

R1: when a task ends after its builder ran, the branch and tip of the builder's work are recorded with the failed or
stopped move, so the report names them and the worktree. The branch is computed from the ids, the tip is the head of
the kept worktree, the path is computed from the ids. No helper text reaches the report.
(b): the tester and the check prompts name the two files that every task may change by right, so a check that says
"only these files" is not failed by them.
"""

import os
import json
import re
import shutil
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
        self.assertIn(f"- Worktree: {path} (exists, kept until you remove it with git worktree remove)", text)
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


class KeptWorktreeTests(FailedReportCase):
    """F1 open question 3: the report says a failed task's worktree is kept until the owner removes it, and the code
    does keep it. umwayi removes a worktree only when no builder started, or after the task is merged."""

    def test_a_failed_tasks_worktree_is_still_there_after_another_run_and_the_report_says_so(self):
        goal, code = RecordedTipTests.failed_by_the_tester(self)
        self.assertEqual(code, 2, self.err)
        path = gr.GIT.worktree_path(str(self.root), goal, "T-01")
        self.assertTrue(os.path.isdir(path))
        self.call("run", goal, scripts=[])  # the supervisor runs its sweep of unused worktrees again
        self.assertTrue(os.path.isdir(path), "a failed task's worktree must not be removed by umwayi")
        self.assertIn("exists, kept until you remove it with git worktree remove", self.report(goal))

    def test_the_rule_by_state(self):
        from umwayi import goal as gl
        for state in ("failed", "stopped", "needs owner"):
            self.assertIn("kept until you remove it", gl._worktree_rule(state))
        self.assertIn("removes it after the merge", gl._worktree_rule("in review"))
        self.assertEqual(gl._worktree_rule("merged"), "exists")

    def test_a_task_in_review_says_it_goes_after_the_merge(self):
        goal, code = self.run_goal([{"steps": rs.builder_steps("G-0001", "T-01"), "spend": 3},
                                    {"steps": rs.tester_steps(), "spend": 2}, {"steps": rs.check_steps(), "spend": 1}])
        self.assertEqual(code, 0, self.err)
        self.assertIn("umwayi removes it after the merge if the tree is clean", self.report(goal))

    def test_a_removed_worktree_says_removed(self):
        goal, _ = RecordedTipTests.failed_by_the_tester(self)
        shutil.rmtree(gr.GIT.worktree_path(str(self.root), goal, "T-01"))
        self.assertIn("(removed)", self.report(goal))


class PlanningPromptTests(FailedReportCase):
    """Option (a) of F1: the guide is told that the two part files are always allowed."""

    def test_the_planning_prompt_names_the_two_files_and_says_not_to_list_or_check_them(self):
        p = gr.planning_prompt("Build the thing in small steps.", "0123456789abcdef")
        self.assertIn("docs-parts/status-log/G-NNNN-T-NN.md", p)
        self.assertIn("docs-parts/known-limits/G-NNNN-T-NN.md", p)
        self.assertIn("Do not list them in the files.", p)
        self.assertIn("Never name them in a check that says no other file changed or that only some files changed.", p)
        self.assertTrue(p.endswith("Nonce: 0123456789abcdef\n"))

    def test_the_planning_prompt_states_the_limits_of_a_check_from_the_parser_constants(self):
        """Found by a real goal run: the guide's plan was refused as `checks` in 3 of 9 tries because the prompt did not say a
        check is one sentence of 10 to 200 characters. The numbers come from the parser's own constants, so the two cannot drift."""
        p = gr.planning_prompt("Build the thing in small steps.", "0123456789abcdef")
        self.assertIn(f"one sentence of {gp.TEXT_MIN} to {gp.TEXT_MAX} characters", p)
        self.assertIn("no second sentence", p)
        with mock.patch.object(gp, "TEXT_MAX", 300):
            self.assertIn("10 to 300 characters", gr.planning_prompt("x", "n"))  # planted: a changed limit shows in the prompt

    def test_the_limits_the_prompt_names_are_the_ones_the_parser_enforces(self):
        def plan(check):
            task = {"goal": "Do the numbered piece of work number 1 now.", "context": [], "checks": [check], "size": 40,
                    "files": ["x.py"]}
            return json.dumps({"tasks": [task]}).encode()
        ok = "c" * gp.TEXT_MAX
        self.assertEqual(len(gp.parse_plan(plan(ok), file_size=lambda p: 1)), 1)
        for bad in ("c" * (gp.TEXT_MAX + 1), "c" * (gp.TEXT_MIN - 1), "It prints hello. It exits with code 0.", "one\ntwo is not one line"):
            with self.subTest(check=bad[:30]):
                with self.assertRaises(gp.PlanError) as cm:
                    gp.parse_plan(plan(bad), file_size=lambda p: 1)
                self.assertEqual(cm.exception.word, "checks")

    def test_the_real_start_gives_the_guide_that_prompt(self):
        seen = []
        real = gr.planning_prompt

        def spy(*a, **kw):
            seen.append(real(*a, **kw))
            return seen[-1]
        with mock.patch.object(gr, "planning_prompt", spy):
            self.g_start()
        self.assertEqual(len(seen), 1)
        self.assertIn("Never name them in a check", seen[0])

    def test_a_guide_that_writes_the_only_check_anyway_still_gets_a_plan(self):
        """The recommendation: advise, do not refuse at the plan stage (word matching misses and hits wrongly)."""
        line = cs.plan_line()
        line["body"]["tasks"][0]["checks"] = ["git status shows only umwayi/piece1.py as a new or changed file."]
        code = self.call("start", cs.GOAL_TEXT, "claude-guide", 20, scripts=[{"steps": [line], "spend": 5}])
        self.assertEqual(code, 0, self.err)
        goal = gs.list_goals(self.root)[-1]
        self.assertIsNone(gs.read_goal(self.root, goal)["refused"])

    def test_a_guide_that_lists_a_part_file_in_files_is_still_refused_as_protected(self):
        line = cs.plan_line()
        line["body"]["tasks"][0]["files"] = ["umwayi/piece1.py", "docs-parts/status-log/G-0001-T-01.md"]
        code = self.call("start", cs.GOAL_TEXT, "claude-guide", 20, scripts=[{"steps": [line], "spend": 5}])
        self.assertEqual(code, 2)
        self.assertEqual(gs.read_goal(self.root, gs.list_goals(self.root)[-1])["refused"], "protected")


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
