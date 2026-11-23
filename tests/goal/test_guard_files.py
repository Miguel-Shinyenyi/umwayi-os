"""W78 step 3 (W41 C1, Q5): a watched file changed during a helper's run stops the task.

Every role is a helper that is started through `agent run`: the builder, the tester, the guide's check and the guide's planning
run. The supervisor reads the watched files (umwayi/watched.py) before it starts the child and again after the child ends. A
change is the cause word `guard_file_changed`: the task goes to `needs owner` (reason unclear), the next step does not start,
nothing is undone, and the entry and the queue row name the files by their fixed names only. A planning run that changes one
has its plan refused (`guard`). A change to a file that is not on the list is not a finding.
"""
import unittest

from tests.goal import cmdsupport as cs
from tests.goal import runsupport as rs
from umwayi import goalstate as gs
from umwayi import watched

GUARDED = ("units.yaml", "guidance.yaml", "agents.yaml", "rules.yaml", "autonomy.yaml", ".umwayi/enforcement.yaml",
           ".kiro/steering/umwayi", "tools/tool.py")


class GuardCase(cs.CmdCase):
    def edit(self, name):
        """A step that changes a root file the way a helper outside its worktree could. A file that exists keeps being valid:
        a comment line is added; a file that is absent is created."""
        path = self.root / name
        text = path.read_text(encoding="utf-8") + "# changed by the helper\n" if path.exists() else "# new\n"
        return {"write": str(path), "text": text}

    def run_goal(self, builder=(), tester=(), check=()):
        goal = self.g_approved()
        scripts = [{"steps": rs.builder_steps(goal, "T-01", extra=list(builder)), "spend": 3},
                   {"steps": list(tester) + rs.tester_steps(), "spend": 2},
                   {"steps": list(check) + rs.check_steps(), "spend": 1}]
        return goal, self.call("run", goal, scripts=scripts)

    def task(self, goal):
        t = gs.read_task(self.root, goal, "T-01")
        return t["state"], t["reason"]

    def assert_stopped(self, goal, code, name, started):
        self.assertEqual(code, 3, self.err)  # needs owner is exit 3
        self.assertEqual(self.task(goal), ("needs owner", "unclear"))
        log = self.logbook_text()
        self.assertIn("Cause: guard_file_changed.", log)
        self.assertIn(f"Guard files changed during the run: {name}.", log)
        self.assertEqual(self.children.started(), started)  # the next step did not start
        rows = (self.root / "queue.md").read_text(encoding="utf-8")
        self.assertIn(f"A guard file changed during the", rows)
        self.assertIn(name, rows)


class BuilderChangesAWatchedFileTests(GuardCase):
    def test_each_watched_name_stops_the_task_before_the_tester_starts(self):
        for name in GUARDED:
            with self.subTest(name=name):
                self.setUp()
                shown = "tools" if name.startswith("tools/") else name
                goal, code = self.run_goal(builder=[self.edit(name)])
                self.assert_stopped(goal, code, shown, started=1)

    def test_nothing_is_undone(self):
        goal, code = self.run_goal(builder=[self.edit("units.yaml")])
        self.assertTrue((self.root / "units.yaml").exists())
        self.assertIn("# new", (self.root / "units.yaml").read_text(encoding="utf-8"))

    def test_two_files_are_both_named_in_list_order(self):
        goal, code = self.run_goal(builder=[self.edit("units.yaml"), self.edit("agents.yaml")])
        self.assertIn("Guard files changed during the run: units.yaml, agents.yaml.", self.logbook_text())

    def test_a_file_that_is_not_watched_is_no_finding(self):
        goal, code = self.run_goal(builder=[{"write": str(self.root / "README.md"), "text": "changed\n"},
                                            {"write": str(self.root / "docs" / "status-log.md"), "text": "changed\n"}])
        self.assertEqual(code, 0, self.err)
        self.assertEqual(self.task(goal), ("in review", "checked"))

    def test_no_change_is_no_finding(self):
        goal, code = self.run_goal()
        self.assertEqual(code, 0, self.err)
        self.assertNotIn("guard_file_changed", self.logbook_text())

    def test_the_words_never_hold_a_path_or_a_word_of_the_helper(self):
        goal, code = self.run_goal(builder=[{"write": str(self.root / "tools" / "SECRET-NAME-never-shown.py"), "text": "x\n"}])
        self.assertIn("Guard files changed during the run: tools.", self.logbook_text())
        self.assertNotIn("SECRET-NAME-never-shown", self.logbook_text() + (self.root / "queue.md").read_text(encoding="utf-8"))


class OtherRolesTests(GuardCase):
    def test_a_tester_that_changes_a_watched_file_stops_the_task_before_the_check(self):
        goal, code = self.run_goal(tester=[self.edit("guidance.yaml")])
        self.assert_stopped(goal, code, "guidance.yaml", started=2)

    def test_the_guides_check_that_changes_a_watched_file_stops_the_task_in_place_of_review(self):
        goal, code = self.run_goal(check=[self.edit("units.yaml")])
        self.assert_stopped(goal, code, "units.yaml", started=3)
        self.assertNotEqual(self.task(goal), ("in review", "checked"))

    def test_a_planning_run_that_changes_a_watched_file_has_its_plan_refused(self):
        line = cs.plan_line()
        code = self.call("start", cs.GOAL_TEXT, "claude-guide", 20,
                         scripts=[{"steps": [self.edit("units.yaml"), line], "spend": 4}])
        self.assertEqual(code, 2, self.err)
        goal = gs.list_goals(self.root)[-1]
        self.assertEqual(gs.read_goal(self.root, goal)["refused"], "guard")
        self.assertIn("(guard)", "\n".join(self.err))


class StopsTests(GuardCase):
    def test_planted_fault_a_finding_that_does_not_stop_the_task_is_the_opposite_of_the_rule(self):
        """With `changed` returning nothing the same run goes to review: so only the finding stops it. (A tools file is used: a bad
        units.yaml would stop the next start for its own reason.)"""
        from unittest import mock
        with mock.patch.object(watched, "changed", lambda before, after: []):
            goal, code = self.run_goal(builder=[self.edit("tools/tool.py")])
        self.assertEqual(code, 0, self.err)
        self.assertEqual(self.task(goal), ("in review", "checked"))

    def test_the_mode_file_is_watched_in_every_mode(self):
        (self.root / ".umwayi").mkdir(exist_ok=True)
        (self.root / ".umwayi" / "enforcement.yaml").write_text("enforcement: enforced\n", encoding="utf-8")
        goal, code = self.run_goal(builder=[{"write": str(self.root / ".umwayi" / "enforcement.yaml"),
                                             "text": "enforcement: enforced\nagents:\n  claude-build:\n    enforcement: cooperative\n    until: 2099-01-01\n"}])
        self.assert_stopped(goal, code, ".umwayi/enforcement.yaml", started=1)


if __name__ == "__main__":
    unittest.main()
