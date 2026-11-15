"""W9.8 / W9.R3: the goal commands, their exit codes and the order of their steps (umwayi/goal.py, umwayi/cli.py).

The commands are called as functions with a fake terminal and the fake agent of tests/goal/fake_agent.py as a real
child process; a few run `python -m umwayi goal ...` as a real child process. Standard library only, no network, no
real AI helper.
"""

import json
import unittest
from unittest import mock

from tests.goal import cmdsupport as cs
from tests.goal import runsupport as rs
from umwayi import goal as gl
from umwayi import goalrun as gr
from umwayi import goalstate as gs
from umwayi import guidance, kill, logbook, rules


class StartTests(cs.CmdCase):
    def test_start_makes_a_plan_that_waits_and_exits_0(self):
        goal = self.g_start(2)
        g = gs.read_goal(self.root, goal)
        self.assertIsNotNone(g["plan"])
        self.assertFalse(g["approved"])
        self.assertIn(f"Goal {goal} has a plan that waits for you.", "\n".join(self.out))
        self.assertIn("T-02", "\n".join(self.out))

    def test_a_refused_plan_is_exit_2(self):
        code = self.call("start", cs.GOAL_TEXT, "claude-guide", 20, scripts=[{"steps": [{"print": "no plan"}]}])
        self.assertEqual(code, 2)
        goal = gs.list_goals(self.root)[-1]
        self.assertEqual(gs.read_goal(self.root, goal)["refused"], "unclear")

    def test_the_kill_switch_is_exit_3_and_makes_nothing(self):
        kill.turn_on(self.root, self.when)
        self.assertEqual(self.call("start", cs.GOAL_TEXT, "claude-guide", 20), 3)
        self.assertEqual(gs.list_goals(self.root), [])
        self.assertEqual(self.children.started(), 0)

    def test_no_rule_for_goal_start_is_exit_3(self):
        (self.root / "rules.yaml").write_text("rules: []\n", encoding="utf-8")
        self.assertEqual(self.call("start", cs.GOAL_TEXT, "claude-guide", 20, scripts=[{"steps": [cs.plan_line()]}]), 3)
        self.assertEqual(self.children.started(), 0)

    def test_a_plan_budget_above_per_run_is_refused_with_2(self):
        self.assertEqual(self.call("start", cs.GOAL_TEXT, "claude-guide", 101), 2)
        self.assertEqual(self.call("start", cs.GOAL_TEXT, "claude-guide", 0), 2)
        self.assertEqual(gs.list_goals(self.root), [])

    def test_a_guide_that_is_not_an_agent_is_64(self):
        self.assertEqual(self.call("start", cs.GOAL_TEXT, "nobody", 20), 64)
        self.assertEqual(gs.list_goals(self.root), [])

    def test_bad_model_or_effort_is_64(self):
        self.assertEqual(self.call("start", cs.GOAL_TEXT, "claude-guide", 20, "a b", ""), 64)
        self.assertEqual(self.call("start", cs.GOAL_TEXT, "claude-guide", 20, "", "extreme"), 64)

    def test_a_goal_text_too_short_is_2(self):
        self.assertEqual(self.call("start", "short", "claude-guide", 20), 2)

    def test_a_held_goal_lock_is_exit_3(self):
        with gs.lock(self.root):
            self.assertEqual(self.call("start", cs.GOAL_TEXT, "claude-guide", 20), 3)


class GuardTests(cs.CmdCase):
    def test_start_approve_and_run_call_the_guard_before_anything_else(self):
        for name, args in (("start", (cs.GOAL_TEXT, "claude-guide", 20)), ("run", ("G-0001",))):
            with self.subTest(command=name):
                with mock.patch.object(guidance, "guard", side_effect=guidance.AskFirst("guidance.yaml is missing")) as g:
                    with mock.patch.object(gs, "lock", side_effect=AssertionError("the lock came before the guard")):
                        self.assertEqual(self.call(name, *args), 3)
                    self.assertEqual(g.call_count, 1)

    def test_approve_calls_the_guard_after_the_terminal_check(self):
        goal = self.g_start()
        with mock.patch.object(guidance, "guard", side_effect=guidance.AskFirst("missing")):
            self.assertEqual(self.g_approve(goal), 3)
        self.assertFalse(gs.read_goal(self.root, goal)["approved"])

    def test_a_missing_guidance_file_is_ask_me_first_and_a_bad_one_is_64(self):
        (self.root / "guidance.yaml").unlink()
        self.assertEqual(self.call("start", cs.GOAL_TEXT, "claude-guide", 20), 3)
        (self.root / "guidance.yaml").write_text("not: [valid\n", encoding="utf-8")
        self.assertEqual(self.call("start", cs.GOAL_TEXT, "claude-guide", 20), 64)
        self.assertEqual(gs.list_goals(self.root), [])


class ApproveTests(cs.CmdCase):
    def test_approve_queues_the_tasks_and_removes_the_plan_worktree(self):
        goal = self.g_start(2)
        wt = gr.GIT.worktree_path(self.root, goal, "plan")
        self.assertTrue(__import__("os").path.isdir(wt))
        self.assertEqual(self.g_approve(goal), 0, self.err)
        self.assertEqual([gs.read_task(self.root, goal, t)["state"] for t in ("T-01", "T-02")], ["queued", "queued"])
        self.assertFalse(__import__("os").path.exists(wt))
        self.assertEqual(self.children.started(), 0)  # approve starts nothing

    def refused(self, goal, **kw):
        before = (self.root / "LOGBOOK.md").read_bytes()
        files = {p.name: p.read_bytes() for p in gs.goal_dir(self.root, goal).iterdir() if p.is_file()}
        self.assertEqual(self.g_approve(goal, **kw), 2, self.err)
        self.assertEqual((self.root / "LOGBOOK.md").read_bytes(), before)
        self.assertEqual({p.name: p.read_bytes() for p in gs.goal_dir(self.root, goal).iterdir() if p.is_file()}, files)

    def test_every_refusal_changes_nothing(self):
        goal = self.g_start()
        for kw in (dict(tester="claude-build"), dict(builder="claude-guide"), dict(tester="nobody"),
                   dict(model="a b"), dict(effort="extreme"), dict(goal_budget_uu=29), dict(goal_budget_uu=45),
                   dict(task_budget_uu=0), dict(task_budget_uu=501), dict(keep=["T-09"]), dict(budget=["T-05=3"]),
                   dict(wait_hours=0), dict(plan_hours=169)):
            with self.subTest(**{k: str(v) for k, v in kw.items()}):
                self.refused(goal, **kw)

    def test_the_planning_budget_must_be_covered_by_the_goal_budget(self):
        goal = self.g_start()
        self.refused(goal, goal_budget_uu=49)  # 30 for the task and 20 for the plan
        self.assertEqual(self.g_approve(goal, goal_budget_uu=50), 0, self.err)

    def test_a_builder_timeout_too_short_for_the_largest_task_names_the_number(self):
        goal = self.g_start(size=80)
        self.refused(goal)
        self.assertIn("needs at least 120", "\n".join(self.err))

    def test_an_agent_that_cannot_be_gated_is_refused(self):
        goal = self.g_start()
        self.gate_code = 2
        self.refused(goal)

    def test_a_root_that_is_not_a_git_repo_is_refused(self):
        goal = self.g_start()
        with mock.patch.object(gr.GIT, "root_ok", lambda root: False):
            self.refused(goal)

    def test_a_timed_out_plan_is_refused(self):
        goal = self.g_start()
        self.clock.advance(169 * 3600)
        self.assertEqual(self.g_approve(goal), 2)
        self.assertEqual(gs.read_goal(self.root, goal)["stopped"], "unanswered")

    def test_keep_drops_the_others_and_budget_overrides_one(self):
        goal = self.g_start(3)
        self.assertEqual(self.g_approve(goal, keep=["T-01", "T-03"], budget=["T-03=10"], goal_budget_uu=100), 0, self.err)
        states = {t: gs.read_task(self.root, goal, t) for t in ("T-01", "T-02", "T-03")}
        self.assertTrue(states["T-02"]["dropped"])
        self.assertEqual(states["T-03"]["packet"]["budget_uu"], 10)

    def test_a_bad_budget_argument_is_64(self):
        goal = self.g_start()
        self.assertEqual(self.g_approve(goal, budget=["T-1=3"]), 64)
        self.assertEqual(self.g_approve(goal, keep=["T1"]), 64)

    def test_wait_hours_sets_the_deadline_of_a_task_that_needs_the_owner(self):
        goal = self.g_start()
        self.assertEqual(self.g_approve(goal, wait_hours=2), 0, self.err)
        gs.change_state(self.root, goal, "T-01", "needs owner", "unclear", when=self.when, now=self.clock())
        a = gs.read_task(self.root, goal, "T-01")["approval"]
        self.assertEqual(a["deadline"] - a["asked"], 2 * 3600)

    def test_same_platform_and_model_is_a_warning_not_a_refusal(self):
        text = (self.root / "agents.yaml").read_text()
        text = text.replace("  - name: kiro-test\n    platform: kiro\n    command: kiro-cli\n",
                            "  - name: kiro-test\n    platform: claude-code\n    command: claude\n")
        text = text.replace("    trust_tools: [read_file]\n", "")
        (self.root / "agents.yaml").write_text(text)
        goal = self.g_start()
        self.assertEqual(self.g_approve(goal, tester_model="sonnet"), 0, self.err)
        self.assertIn("independence is weak", "\n".join(self.err))


class RunTests(cs.CmdCase):
    def scripts(self, goal="G-0001"):
        return [{"steps": rs.builder_steps(goal, "T-01"), "spend": 5}, {"steps": rs.tester_steps()}, {"steps": rs.check_steps()}]

    def test_run_takes_a_task_to_in_review_exits_0_and_prints_the_report(self):
        goal = self.g_approved()
        self.assertEqual(self.call("run", goal, scripts=self.scripts(goal)), 0, self.err)
        self.assertEqual(gs.read_task(self.root, goal, "T-01")["state"], "in review")
        text = "\n".join(self.out)
        self.assertIn(f"# Report of goal {goal}", text)
        self.assertTrue((gs.goal_dir(self.root, goal) / "report.md").exists())

    def test_run_exits_2_when_the_task_fails(self):
        goal = self.g_approved()
        self.assertEqual(self.call("run", goal, scripts=[{"steps": [{"exit": 2}]}]), 2)

    def test_run_exits_3_when_the_task_needs_the_owner_and_says_how_to_answer(self):
        goal = self.g_approved()
        self.assertEqual(self.call("run", goal, scripts=[{"steps": [{"exit": 3}]}]), 3)
        self.assertIn(f"Answer with: umwayi goal answer {goal} T-01 yes", "\n".join(self.out))

    def test_run_exits_3_with_the_kill_switch_on(self):
        goal = self.g_approved()
        kill.turn_on(self.root, self.when)
        self.assertEqual(self.call("run", goal, scripts=self.scripts(goal)), 3)
        self.assertEqual(self.children.started(), 0)

    def test_run_with_the_goal_lock_held_is_3(self):
        goal = self.g_approved()
        with gs.lock(self.root):
            self.assertEqual(self.call("run", goal), 3)

    def test_a_goal_that_does_not_exist_is_2(self):
        self.assertEqual(self.call("run", "G-0099"), 2)

    def test_an_unexpected_error_is_2_and_prints_no_exception_text(self):
        goal = self.g_approved()
        import io
        import sys
        from umwayi import cli
        err = io.StringIO()
        with mock.patch.object(gr, "supervise", side_effect=RuntimeError("SECRET-TEXT")), mock.patch.object(sys, "stderr", err):
            out = io.StringIO()
            code = cli.main(["--root", str(self.root), "goal", "run", goal], out=out)
        self.assertEqual(code, 2)
        self.assertNotIn("SECRET-TEXT", err.getvalue() + out.getvalue())
        self.assertIn("RuntimeError", err.getvalue())


class StopTests(cs.CmdCase):
    def test_stop_stops_the_goal_and_every_queued_task_and_is_idempotent(self):
        goal = self.g_approved(2)
        self.terminal = False  # stop is open to everyone
        self.assertEqual(self.call("stop", goal), 0)
        self.assertEqual(gs.read_goal(self.root, goal)["stopped"], "owner")
        self.assertEqual([gs.read_task(self.root, goal, t)["state"] for t in ("T-01", "T-02")], ["stopped", "stopped"])
        n = len(logbook.read_checked(self.root))
        self.assertEqual(self.call("stop", goal), 0)
        self.assertEqual(len(logbook.read_checked(self.root)), n)
        self.assertIn("already stopped", self.out[-1])

    def test_stop_of_a_plan_removes_the_plan_worktree(self):
        goal = self.g_start()
        self.assertEqual(self.call("stop", goal), 0)
        self.assertFalse(__import__("os").path.exists(gr.GIT.worktree_path(self.root, goal, "plan")))

    def test_stop_reaches_a_running_supervisor_within_its_watch(self):
        goal = self.g_approved()
        c = self.ctx([{"steps": [{"silent": 7}], "spend": 1}], policy=gr.gw.Policy(stall_s=10_000))
        self.at_tick(self.ticks + 3, lambda: gs.stop_goal(self.root, goal, "owner", when=self.when, now=self.clock(), queued_too=True))
        self.assertEqual(gl.dispatch(c, cs.ARGS["run"](goal)), 2)
        self.assertEqual((gs.read_task(self.root, goal, "T-01")["state"], gs.read_task(self.root, goal, "T-01")["reason"]),
                         ("stopped", "owner"))
        for p in self.children.procs:
            self.assertIsNotNone(p.poll())


class CliTests(cs.CmdCase):
    """Through `python -m umwayi goal ...` as a real child process: wrong use is 64, never 1."""

    def test_wrong_use_is_64(self):
        for argv in (["start", "x"], ["approve", "G-0001"], ["answer", "G-0001", "T-01", "maybe"], ["show"],
                     ["start", "x" * 20, "--guide", "a", "--plan-budget-uu", "abc"], ["run", "G-1"],
                     ["merged", "G-0001", "T-01", "--commit", "xyz"], ["frobnicate"]):
            with self.subTest(argv=argv):
                r = self.umwayi(*argv)
                self.assertEqual(r.returncode, 64, r.stdout + r.stderr)

    def test_status_show_and_report_exit_0(self):
        goal = self.g_approved()
        for argv in (["status"], ["status", goal], ["show", goal], ["report", goal]):
            with self.subTest(argv=argv):
                r = self.umwayi(*argv)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_owner_commands_without_a_terminal_are_2(self):
        goal = self.g_start()
        r = self.umwayi("approve", goal, "--builder", "claude-build", "--tester", "kiro-test", "--model", "m",
                        "--effort", "high", "--task-budget-uu", "30", "--goal-budget-uu", "100")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("needs a terminal", r.stderr)

    def test_goal_docs_and_guard_still_route_to_their_own_code(self):
        r = self.umwayi("guard")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith("Yes: guidance.yaml is well formed"))


class RulesTests(unittest.TestCase):
    def test_goal_start_is_on_the_never_list(self):
        self.assertIn("goal_start", rules.NEVER_AUTONOMY)

    def test_a_rule_that_opts_goal_start_in_to_autonomy_is_malformed(self):
        text = ("rules:\n  - id: g\n    title: t\n    text: x.\n    verdict: ask\n    autonomy:\n      class: goals\n"
                "      reversible: true\n      cost_uu: 1\n    matchers:\n      type: goal_start\n")
        with self.assertRaises(Exception):
            rules.parse_rules(text)

    def test_the_example_rules_load_and_allow_nothing(self):
        from pathlib import Path
        from umwayi.rules import decide, parse_rules
        repo = Path(__file__).resolve().parents[2]
        ex = parse_rules((repo / "goal.rules.example.yaml").read_text(encoding="utf-8"))
        self.assertEqual(ex, [])
        action = {"type": "goal_start", "goal": "G-0001", "task": "T-01", "role": "builder", "agent": "a",
                  "platform": "claude-code", "budget_uu": 3}
        self.assertEqual(decide(ex, action).answer, rules.ASK)

    def test_the_schedule_refuses_the_word_goal(self):
        from umwayi import schedule
        problems = schedule.check_text("schedules:\n  - name: g\n    run: goal\n    every: daily\n    at: \"03:00\"\n",
                                       __import__("pathlib").Path("/tmp")) if hasattr(schedule, "check_text") else None
        if problems is None:
            self.skipTest("schedule has no check_text")
        text = json.dumps([getattr(p, "message", str(p)) for p in (problems[1] if isinstance(problems, tuple) else problems)])
        self.assertIn("run must be job or workflow", text)


class FirstRunFindingsTests(cs.CmdCase):
    """W55a: findings of the first real goal runs by Claude Code in a scratch root (items 1, 2 and 4 through the
    commands). Words only reach a record or a status line, never content."""

    def refused(self, spend=4):
        code = self.call("start", cs.GOAL_TEXT, "claude-guide", 20, scripts=[{"steps": [{"print": "no plan line"}], "spend": spend}])
        self.assertEqual(code, 2, self.err)
        return gs.list_goals(self.root)[-1]

    def test_1_status_and_report_show_the_measured_spend_of_a_refused_plan(self):
        goal = self.refused(spend=4)
        self.assertEqual(gs.read_goal(self.root, goal)[gs.PLAN_SPENT_KEY], 4)
        self.out.clear()
        self.assertEqual(self.call("status", goal), 0)
        self.assertIn("  Spent: 4 of 20 UU on the goal.", self.out)
        self.out.clear()
        self.assertEqual(self.call("report", goal), 0)
        text = "\n".join(self.out)
        self.assertIn("- Spent: 4 UU,", text)
        self.assertIn("- Planning run: 4 UU of its budget of 20 UU, the plan was refused (unclear)", text)

    def test_1_a_good_plan_records_its_measured_spend_too(self):
        goal = self.g_start()
        self.assertEqual(gs.read_goal(self.root, goal)[gs.PLAN_SPENT_KEY], 5)

    def test_1_a_goal_file_from_before_w55a_still_reads_and_counts_the_plan_budget(self):
        goal = self.g_start()
        g = gs.read_goal(self.root, goal)
        del g[gs.PLAN_SPENT_KEY]
        (gs.goal_dir(self.root, goal) / "goal.json").write_text(json.dumps(g), encoding="utf-8")
        self.assertEqual(gs.plan_used_uu(gs.read_goal(self.root, goal)), 20)
        for bad in (-1, True, "4", 1.5):
            with self.subTest(plan_spent=repr(bad)):
                (gs.goal_dir(self.root, goal) / "goal.json").write_text(json.dumps(dict(g, plan_spent_uu=bad)))
                with self.assertRaises(gs.GoalError):
                    gs.read_goal(self.root, goal)

    def test_2_a_refused_plan_removes_its_plan_worktree(self):
        goal = self.refused()
        self.assertFalse(__import__("os").path.exists(gr.GIT.worktree_path(self.root, goal, "plan")))
        self.assertNotIn("plan worktree removed", self.logbook_text())  # the undo of our own step: an event only

    def test_4_the_cause_word_of_a_failed_task_is_in_its_entry_status_and_report(self):
        goal = self.g_approved()
        steps = rs.builder_steps(goal, "T-01")[:-1] + [{"write": "umwayi/left-over.py", "text": "x"}, {"exit": 0}]
        self.assertEqual(self.call("run", goal, scripts=[{"steps": steps, "spend": 2}]), 2)
        [entry] = [e for e in self.entries() if "running to failed" in e.added]
        self.assertIn("(reason outcome)", entry.added)
        self.assertIn("Cause: tree_not_clean.", entry.checked)
        self.out.clear()
        self.call("status", goal)
        self.assertIn("  Task T-01  failed (outcome: tree_not_clean)", self.out)
        self.out.clear()
        self.call("report", goal)
        self.assertIn("- Cause: tree_not_clean", self.out)
        gs.view(self.root)  # the new entry shape parses strictly

    def test_4_other_cause_words_scope_and_status_file_missing(self):
        for name, files, status, want in (("scope", {"umwayi/other.py": "x"}, rs.STATUS_PART, "file_outside_packet"),
                                          ("missing status", {"umwayi/piece1.py": "x"}, None, "status_file_missing")):
            with self.subTest(case=name):
                self.setUp()
                goal = self.g_approved()
                steps = rs.builder_steps(goal, "T-01", files=files, status=status)
                self.call("run", goal, scripts=[{"steps": steps, "spend": 1}])
                [entry] = [e for e in self.entries() if "running to failed" in e.added]
                self.assertIn(f"Cause: {want}.", entry.checked)

    def test_4_an_unknown_cause_word_is_refused_by_the_entry_shape(self):
        with self.assertRaises(ValueError):
            gs.state_entry(self.when, "G-0001", "T-01", "running", "failed", "outcome",
                           facts=[("cause", {"word": "rm -rf something"})])

    def test_6_the_guidance_message_names_the_missing_source_path(self):
        text = cs.GUIDANCE.replace('source_repo: hub\n    source: "understanding-first.md#3"',
                                   'source_repo: umwayi-os\n    source: ".kiro/steering/missing.md#1"')
        (self.root / "guidance.yaml").write_text(text, encoding="utf-8")
        with self.assertRaises(guidance.SourceChanged) as e:
            guidance.load(self.root)
        self.assertIn("(.kiro/steering/missing.md)", str(e.exception))


if __name__ == "__main__":
    unittest.main()
