"""R2.2 and R2.3 of the 2026-11-18 recordings: the goal commands say what they know.

(a) `goal approve` prints what it approves, with the budgets, before it changes anything.
(b) `goal start`, `goal show` and `goal approve` print the enforcement mode of each agent.
(c) `goal show` of a refused goal gives the reason word that `goal status` gives.
(d) A plan refused as protected names the protected list entry that matched, never the plan's own path.
"""

import json
import unittest
from datetime import date, timedelta

from tests.goal import cmdsupport as cs
from umwayi import enforce
from umwayi import goalpacket as gp
from umwayi import goalstate as gs

SECRET = "R2-SECRET-never-in-a-record"


class WordsCase(cs.CmdCase):
    def today(self):
        return self.ctx().when

    def make_cooperative(self, agent):
        today = self.today()  # the system date or later: the test clock is only a fake epoch
        until = (date.fromisoformat(today) + timedelta(days=7)).isoformat()
        r = enforce.set_mode(self.root, "cooperative", agent=agent, until=until, today=today,
                             tty=lambda: True, confirm=lambda: "cooperative")
        self.assertEqual(r.code, 0, r.lines)

    def text(self, lines):
        return "\n".join(lines)


class ApproveSaysWhatItApprovesTests(WordsCase):
    def test_approve_prints_the_goal_the_tasks_and_every_budget_before_the_done_line(self):
        goal = self.g_start(tasks=2)
        self.out.clear()
        self.assertEqual(self.g_approve(goal, task_budget_uu=30, goal_budget_uu=100), 0, self.err)
        out = self.text(self.out)
        self.assertIn(f"Approving goal {goal}: 2 tasks, 0 dropped.", out)
        self.assertIn("builder claude-build, tester kiro-test", out)
        self.assertIn("T-01 30 UU, T-02 30 UU", out)
        self.assertIn("Goal budget 100 UU", out)
        self.assertLess(out.index("Approving goal"), out.index(f"Approved goal {goal}"))

    def test_a_refused_approval_prints_no_summary(self):
        goal = self.g_start()
        self.out.clear()
        self.assertEqual(self.g_approve(goal, builder="claude-guide"), 2)
        self.assertNotIn("Approving goal", self.text(self.out))

    def test_approve_names_a_dropped_task(self):
        goal = self.g_start(tasks=2)
        self.out.clear()
        self.assertEqual(self.g_approve(goal, keep=["T-01"]), 0, self.err)
        out = self.text(self.out)
        self.assertIn("1 tasks, 1 dropped.", out)
        self.assertNotIn("T-02 30 UU", out)


class ModePerAgentTests(WordsCase):
    def test_start_and_show_print_one_mode_line_for_each_agent(self):
        self.make_cooperative("claude-guide")
        self.out.clear()
        goal = self.g_start()
        out = self.text(self.out)
        self.assertRegex(out, r"enforcement for guide claude-guide: cooperative \(agent, until \d{4}-\d\d-\d\d\)")
        self.out.clear()
        self.assertEqual(self.call("show", goal), 0)
        self.assertRegex(self.text(self.out), r"enforcement for guide claude-guide: cooperative")

    def test_after_approval_the_builder_and_the_tester_have_their_own_line(self):
        self.make_cooperative("claude-build")
        goal = self.g_approved()
        self.out.clear()
        self.assertEqual(self.call("show", goal), 0)
        lines = [l for l in self.out if l.startswith("enforcement for ")]
        self.assertEqual(len(lines), 3, lines)
        by_role = {l.split()[2]: l for l in lines}
        self.assertIn("cooperative", by_role["builder"])
        self.assertIn("enforcement: enforced".replace("enforcement:", "enforcement for guide claude-guide:"), by_role["guide"])
        self.assertIn("enforced", by_role["tester"])
        self.assertFalse(any(l == "enforcement: enforced" for l in self.out))

    def test_approve_prints_the_mode_of_each_role_before_it_changes_anything(self):
        goal = self.g_start()
        self.make_cooperative("kiro-test")
        self.out.clear()
        self.assertEqual(self.g_approve(goal), 0, self.err)
        out = self.text(self.out)
        self.assertRegex(out, r"enforcement for tester kiro-test: cooperative")
        self.assertIn("enforcement for builder claude-build: enforced", out)


class RefusedShowTests(WordsCase):
    def refuse(self, tasks_edit):
        line = cs.plan_line()
        tasks_edit(line["body"]["tasks"][0])
        code = self.call("start", cs.GOAL_TEXT, "claude-guide", 20, scripts=[{"steps": [line], "spend": 4}])
        self.assertEqual(code, 2, self.err)
        return gs.list_goals(self.root)[-1]

    def test_show_of_a_refused_goal_gives_the_reason_word(self):
        goal = self.refuse(lambda t: t.update(size=999))
        self.out.clear()
        self.assertEqual(self.call("show", goal), 0)
        self.assertIn(f"Goal {goal}: refused (size).", self.text(self.out))

    def test_show_and_status_agree_on_the_reason(self):
        goal = self.refuse(lambda t: t.update(files=["docs-parts/known-limits/X.md"]))
        self.out.clear()
        self.assertEqual(self.call("show", goal), 0)
        shown = self.text(self.out)
        self.out.clear()
        self.assertEqual(self.call("status", goal), 0)
        status = self.text(self.out)
        self.assertIn("refused (protected: task 1, docs-parts/)", shown)
        self.assertIn("The plan was refused (protected: task 1, docs-parts/).", status)

    def test_a_goal_that_is_not_refused_keeps_its_word(self):
        goal = self.g_start()
        self.out.clear()
        self.assertEqual(self.call("show", goal), 0)
        self.assertNotIn("refused", self.text(self.out))


class ProtectedPathTests(WordsCase):
    def start_with_files(self, files):
        line = cs.plan_line(tasks=2)
        line["body"]["tasks"][1]["files"] = files
        code = self.call("start", cs.GOAL_TEXT, "claude-guide", 20, scripts=[{"steps": [line], "spend": 4}])
        self.assertEqual(code, 2, self.err)
        return gs.list_goals(self.root)[-1]

    def test_the_task_and_the_protected_entry_are_logged_and_shown_never_the_path(self):
        for files, entry in ((["docs-parts/known-limits/X.md"], "docs-parts/"), ([f"rules.yaml"], "rules.yaml"),
                             ([f".UMWAYI/{SECRET}"], ".umwayi/"), ([f"workflows/{SECRET}.yml"], "workflows/"),
                             (["umwayi/ok.py", f".github/{SECRET}/x"], ".github/")):
            with self.subTest(entry=entry):
                self.setUp()
                goal = self.start_with_files(files)
                g = gs.read_goal(self.root, goal)
                self.assertEqual((g["refused"], g[gs.REFUSED_PROTECTED_KEY]), ("protected", {"task": 2, "entry": entry}))
                words = f"protected: task 2, {entry}"
                self.assertIn(f"was refused ({words})", self.text(self.err))
                self.assertIn(f"Protected path of task 2: {entry}.", self.logbook_text())
                self.out.clear()
                self.call("status", goal)
                self.call("report", goal)
                every = "\n".join([self.logbook_text(), self.text(self.out), self.text(self.err)]
                                  + [p.read_text(encoding="utf-8") for p in gs.goal_dir(self.root, goal).iterdir() if p.is_file()])
                self.assertNotIn(SECRET, every)

    def test_a_plan_refused_for_another_reason_names_no_protected_entry(self):
        goal = self.start_with_files(["a.py", "*.py"])
        g = gs.read_goal(self.root, goal)
        self.assertEqual(g["refused"], "files")
        self.assertNotIn(gs.REFUSED_PROTECTED_KEY, g)

    def test_the_parser_gives_the_list_entry_and_never_the_path(self):
        tasks = [{"goal": "Do the numbered piece of work number 1 now.", "context": [],
                  "checks": ["Check number 1 of the piece can be answered pass or fail."], "size": 40,
                  "files": [f"Docs-Parts/{SECRET}.md"]}]
        with self.assertRaises(gp.PlanError) as cm:
            gp.parse_plan(json.dumps({"tasks": tasks}).encode(), file_size=lambda p: 1)
        self.assertEqual((cm.exception.word, cm.exception.index, cm.exception.protected), ("protected", 1, "docs-parts/"))
        self.assertNotIn(SECRET, str(cm.exception))

    def test_protected_entry_agrees_with_is_protected(self):
        for path in ("rules.yaml", "docs-parts/a", "DOCS-PARTS/a", ".umwayi/x/y", "umwayi/goal.py", "docs/a.md", "src/rules.yaml"):
            with self.subTest(path=path):
                self.assertEqual(gp.protected_entry(path) is not None, gp.is_protected(path))
        self.assertIsNone(gp.protected_entry(7))
        self.assertIsNone(gp.protected_entry("../rules.yaml"))

    def test_a_goal_file_with_a_bad_refused_protected_does_not_read(self):
        goal = self.start_with_files(["rules.yaml"])
        path = gs.goal_dir(self.root, goal) / "goal.json"
        g = json.loads(path.read_text(encoding="utf-8"))
        for bad in ({"task": 1, "entry": SECRET}, {"task": 0, "entry": "rules.yaml"}, {"task": 1, "entry": "rules.yaml", "path": SECRET},
                    {"task": True, "entry": "rules.yaml"}, "rules.yaml"):
            with self.subTest(bad=bad):
                path.write_text(json.dumps(dict(g, refused_protected=bad)), encoding="utf-8")
                with self.assertRaises(gs.GoalError):
                    gs.read_goal(self.root, goal)

    def test_only_a_protected_refusal_may_name_an_entry(self):
        with self.assertRaises(gs.GoalError):
            gs.refuse_plan(self.root, "G-0001", "claude-guide", "files", when="2026-11-22", now=0,
                           protected={"task": 1, "entry": "rules.yaml"})

    def test_every_protected_entry_is_a_valid_logbook_word(self):
        for entry in gp.PROTECTED:
            with self.subTest(entry=entry):
                e = gs.plan_refused_entry("2026-11-22", "G-0001", "claude-guide", "protected", None, {"task": 1, "entry": entry})
                self.assertIn(f"Protected path of task 1: {entry}.", str(e))


if __name__ == "__main__":
    unittest.main()
