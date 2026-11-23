"""W9.16 in a goal: the supervisor writes a scope file for every Claude Code run and gives it to `agent run --scope-file`.

The builder's scope is the packet's files and its two own files. A tester, a guide's check and a planning run get an empty scope: a file
write of theirs is No. A Kiro run gets no scope file (its hook is a file of the owner's, not set by umwayi). The scope file is written
next to the goal's records and replaced for each run. A scope file that cannot be written ends the task before the run (fail closed).
"""
import json
import unittest
from unittest import mock

from tests.goal import cmdsupport as cs
from tests.goal import runsupport as rs
from umwayi import goalrun as gr
from umwayi import goalstate as gs
from umwayi import scope


def flags(argv):
    return argv[argv.index("--scope-file") + 1] if "--scope-file" in argv else None


class ChildArgvTests(unittest.TestCase):
    def test_the_option_is_added_only_when_given(self):
        base = gr.child_argv("a", 5, "/w")
        self.assertNotIn("--scope-file", base)
        self.assertEqual(gr.child_argv("a", 5, "/w", scope_file="/s.json")[-2:], ["--scope-file", "/s.json"])


class RunTests(cs.CmdCase):
    def run_goal(self):
        goal = self.g_approved()
        scripts = [{"steps": rs.builder_steps(goal, "T-01"), "spend": 3}, {"steps": rs.tester_steps(), "spend": 2},
                   {"steps": rs.check_steps(), "spend": 1}]
        code = self.call("run", goal, scripts=scripts)
        return goal, code

    def test_each_claude_run_gets_its_scope_and_the_kiro_tester_gets_none(self):
        goal, code = self.run_goal()
        self.assertEqual(code, 0, self.err)
        argvs = [a for a, _ in self.children.calls]
        by_agent = {a[5]: a for a in argvs}
        self.assertIsNotNone(flags(by_agent["claude-build"]))
        self.assertIsNone(flags(by_agent["kiro-test"]))  # Kiro's hook is the owner's file
        self.assertIsNotNone(flags(by_agent["claude-guide"]))

    def test_the_builders_scope_is_the_packet_and_the_checks_scope_is_empty(self):
        goal, code = self.run_goal()
        by_agent = {a[5]: a for a, _ in self.children.calls}
        builder = scope.load(flags(by_agent["claude-build"]))
        check = scope.load(flags(by_agent["claude-guide"]))
        packet = gs.read_task(self.root, goal, "T-01")
        self.assertEqual(builder["files"], list(json.loads(json.dumps(builder["files"]))))
        self.assertEqual(builder["own"], [f"docs-parts/status-log/{goal}-T-01.md", f"docs-parts/known-limits/{goal}-T-01.md"])
        self.assertTrue(builder["files"])
        self.assertEqual((check["files"], check["own"]), ([], []))
        self.assertEqual(builder["worktree"], by_agent["claude-build"][by_agent["claude-build"].index("--workdir") + 1])
        self.assertEqual(oct(__import__("os").stat(flags(by_agent["claude-build"])).st_mode & 0o777), "0o600")
        self.assertIn(goal, flags(by_agent["claude-build"]))

    def test_a_scope_file_that_cannot_be_written_ends_the_task_before_the_run(self):
        goal = self.g_approved()
        scripts = [{"steps": rs.builder_steps(goal, "T-01"), "spend": 3}]
        with mock.patch.object(scope, "make", side_effect=ValueError("worktree")):
            code = self.call("run", goal, scripts=scripts)
        self.assertEqual(self.children.started(), 0)
        self.assertNotEqual(code, 0)
        self.assertEqual(gs.read_task(self.root, goal, "T-01")["state"], "needs owner")


if __name__ == "__main__":
    unittest.main()
