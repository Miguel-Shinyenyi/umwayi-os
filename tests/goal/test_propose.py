"""W54: the system proposes the per task UU; the owner approves or changes the number; the hard cap never rises.

Pure first (`umwayi/goalpropose.py`): each source, the bounds, the id. Then through the commands: `goal show` with the
roles prints the proposal and writes nothing; `goal approve --accept-proposed ID` takes exactly the shown numbers, is
refused when the proposal changed or a task has no history, and the owner's numbers win; the approval entry names what
was taken; nothing raises an approved budget; the supervisor keeps the measured spend of each role as history.
"""

import json
import random
import unittest
from fractions import Fraction
from unittest import mock

from tests.goal import cmdsupport as cs
from tests.goal import runsupport as rs
from tests.goal.test_owner_commands import snapshot
from umwayi import budget, goalbudget, goalpacket as gp, goalpropose as gpr, goalstate as gs, logbook, units

R_B = gpr.Role("builder", "claude-build", "claude-code", "sonnet", "high")
R_T = gpr.Role("tester", "kiro-test", "kiro", "", "")
R_C = gpr.Role("check", "claude-guide", "claude-code", "", "")
ROLES = (R_B, R_T, R_C)


def inputs(**kw):
    a = dict(per_run=100, per_day=500, run_uu={"kiro": ("unknown", 100)}, history={}, calibrate={}, units_sha256="")
    a.update(kw)
    return gpr.Inputs(**a)


def packet(i=1, size=40):
    return gp.Packet(f"T-{i:02d}", f"Do the numbered piece of work number {i} now.", (),
                     (f"Check number {i} of the piece can be answered pass or fail.",), {}, size, "", "",
                     (f"umwayi/piece{i}.py",), None)


class SourceTests(unittest.TestCase):
    def test_a_kiro_run_is_its_declared_uu(self):
        t = gpr.term_for(R_T, 40, inputs(run_uu={"kiro": ("declared", 40)}))
        self.assertEqual((t.uu, t.source), (40, "declared"))

    def test_an_unknown_kiro_run_is_the_unknown_100_and_never_less(self):
        t = gpr.term_for(R_T, 15, inputs())
        self.assertEqual((t.uu, t.source), (100, "unknown"))
        hist = {R_T.key(): (1, 1, 1, 1, 1, 1)}  # history never lowers a Kiro role
        self.assertEqual(gpr.term_for(R_T, 15, inputs(history=hist)).uu, 100)

    def test_five_history_tasks_give_a_number_and_four_do_not(self):
        five = {R_B.key(): (Fraction(1),) * 5}
        t = gpr.term_for(R_B, 40, inputs(history=five))
        self.assertEqual((t.uu, t.source, t.count), (60, "history", 5))  # 1.5 x 1 UU per minute x 40 minutes
        four = {R_B.key(): (Fraction(1),) * 4}
        self.assertEqual(gpr.term_for(R_B, 40, inputs(history=four)).source, "no history")

    def test_the_tester_and_check_history_is_per_task_not_per_minute(self):
        hist = {R_C.key(): (10, 10, 10, 10, 20)}
        self.assertEqual(gpr.term_for(R_C, 15, inputs(history=hist)).uu, 30)
        self.assertEqual(gpr.term_for(R_C, 90, inputs(history=hist)).uu, 30)

    def test_calibrate_for_the_model_then_for_all_runs(self):
        self.assertEqual(gpr.term_for(R_B, 40, inputs(calibrate={"sonnet": 33, "": 50})).uu, 33)
        t = gpr.term_for(R_B, 40, inputs(calibrate={"": 50}))
        self.assertEqual((t.uu, t.source), (50, "calibrate"))

    def test_no_history_is_the_smallest_cap_and_marks_the_task(self):
        p = gpr.propose_task("T-01", 40, ROLES, inputs())
        self.assertEqual([(t.role, t.uu, t.source) for t in p.terms],
                         [("builder", 1, "no history"), ("tester", 100, "unknown"), ("check", 1, "no history")])
        self.assertTrue(p.no_history)
        self.assertEqual(gpr.kiro_floor(p), 100)

    def test_history_comes_before_calibrate(self):
        both = inputs(history={R_B.key(): (Fraction(1, 2),) * 6}, calibrate={"": 80})
        self.assertEqual(gpr.term_for(R_B, 40, both).source, "history")


class BoundTests(unittest.TestCase):
    def test_terms_and_totals_stay_inside_the_limits_for_random_inputs(self):
        for seed in (1, 2, 3, random.randrange(10 ** 6)):
            rnd = random.Random(seed)
            for _ in range(500):
                per_run, per_day = rnd.randint(1, 300), rnd.randint(1, 900)
                hist = {k: tuple(Fraction(rnd.randint(0, 5000), rnd.randint(1, 90)) if k[0] == "builder"
                                 else rnd.randint(0, 5000) for _ in range(rnd.randint(0, 9)))
                        for k in (R_B.key(), R_C.key())}
                inp = inputs(per_run=per_run, per_day=per_day, history=hist,
                             run_uu={"kiro": (rnd.choice(["declared", "unknown"]), rnd.randint(1, 400))},
                             calibrate=rnd.choice([{}, {"": rnd.randint(1, 400)}]))
                size = rnd.randint(gp.MIN_SIZE, gp.MAX_SIZE)
                p = gpr.propose_task("T-01", size, ROLES, inp)
                with self.subTest(seed=seed):
                    self.assertTrue(all(1 <= t.uu <= per_run for t in p.terms), p)
                    self.assertLessEqual(p.total, per_day)
                    other = gpr.propose_task("T-01", gp.MAX_SIZE + gp.MIN_SIZE - size, ROLES, inp)
                    self.assertEqual(p.terms[1:], other.terms[1:])  # the size scales the builder's term only

    def test_the_percentile_is_the_one_calibrate_uses(self):
        rnd = random.Random(7)
        for _ in range(300):
            runs = [rnd.randint(1, 3_000_000) for _ in range(rnd.randint(1, 60))]
            self.assertEqual(budget.per_run_proposal_uu(runs), -(-3 * gpr.p95(runs) // (2 * units.MICROS_PER_UU)))

    def test_a_huge_size_cannot_pass_per_run_or_per_day(self):
        inp = inputs(per_run=50, per_day=120, history={R_B.key(): (Fraction(100),) * 5, R_C.key(): (999,) * 5})
        p = gpr.propose_task("T-01", gp.MAX_SIZE, ROLES, inp)
        self.assertEqual([t.uu for t in p.terms], [50, 50, 50])
        self.assertEqual(p.total, 120)


class IdTests(unittest.TestCase):
    def test_the_same_inputs_give_the_same_id_and_any_change_another(self):
        base = gpr.propose([packet()], ROLES, inputs(units_sha256="a" * 64), 20)
        self.assertEqual(base.id, gpr.propose([packet()], ROLES, inputs(units_sha256="a" * 64), 20).id)
        self.assertRegex(base.id, r"^[0-9a-f]{8}$")
        changed = [
            gpr.propose([packet(size=41)], ROLES, inputs(units_sha256="a" * 64), 20),
            gpr.propose([packet()], (R_B, gpr.Role("tester", "kiro-two", "kiro", "", ""), R_C),
                        inputs(units_sha256="a" * 64), 20),
            gpr.propose([packet()], ROLES, inputs(units_sha256="b" * 64), 20),
            gpr.propose([packet()], ROLES, inputs(units_sha256="a" * 64, history={R_B.key(): (Fraction(1),)}), 20),
            gpr.propose([packet()], ROLES, inputs(units_sha256="a" * 64, calibrate={"": 9}), 20),
            gpr.propose([packet()], ROLES, inputs(units_sha256="a" * 64), 21),
        ]
        for p in changed:
            self.assertNotEqual(p.id, base.id)

    def test_the_lines_name_each_part_and_never_a_text(self):
        p = gpr.propose([packet()], ROLES, inputs(history={R_B.key(): (Fraction(1),) * 7, R_C.key(): (20,) * 5},
                                                  calibrate={}), 20)
        per_task, tail = gpr.lines(p)
        self.assertEqual(per_task["T-01"], "    Proposed: 190 UU = builder 60 (history, 7 tasks) + tester 100 (unknown) "
                                           "+ check 30 (history, 5 tasks)")
        self.assertEqual(tail, f"  Proposed goal budget: 210 UU (the tasks 190, the planning run 20). Proposal id {p.id}.")
        self.assertNotIn("piece", per_task["T-01"] + tail)


class WindowTests(unittest.TestCase):
    def test_only_runs_that_were_all_settled_measured_count(self):
        led = budget.Ledger()
        led.reserves = {"r1": budget.Reserve("r1", "a", "claude-code", 10, "2026-11-16"),
                        "r2": budget.Reserve("r2", "a", "claude-code", 10, "2026-11-16")}
        s = lambda run, tag: budget.Settle(run, "a", "claude-code", tag, 5, (), (0, 0, 0, 0), 0, 5)  # noqa: E731
        led.settles = {"r1": s("r1", "measured")}
        self.assertFalse(goalbudget.window_measured(frozenset(), led, "a"))  # r2 has no settle
        led.settles["r2"] = s("r2", "unknown")
        self.assertFalse(goalbudget.window_measured(frozenset(), led, "a"))
        led.settles["r2"] = s("r2", "measured")
        self.assertTrue(goalbudget.window_measured(frozenset(), led, "a"))
        self.assertFalse(goalbudget.window_measured(frozenset({"r1", "r2"}), led, "a"))  # no run in the window

    def test_calibrate_numbers_need_twenty_runs_over_seven_days(self):
        def ledger(n_runs, n_days, models=("claude-sonnet",)):
            led = budget.Ledger()
            for i in range(n_runs):
                run = f"r{i:03d}"
                led.reserves[run] = budget.Reserve(run, "a", "claude-code", 10, f"2026-11-{1 + i % n_days:02d}")
                led.settles[run] = budget.Settle(run, "a", "claude-code", "measured", 100_000 + i, models, (0, 0, 0, 0), 0, 0)
            return led
        self.assertEqual(gpr._calibrate_numbers(ledger(19, 7)), {})
        self.assertEqual(gpr._calibrate_numbers(ledger(20, 6)), {})
        got = gpr._calibrate_numbers(ledger(20, 7))
        self.assertEqual(set(got), {"", "claude-sonnet"})
        self.assertEqual(got[""], budget.per_run_proposal_uu([100_000 + i for i in range(20)]))


class ProposalCase(cs.CmdCase):
    def show(self, goal, **kw):
        a = dict(builder="claude-build", tester="kiro-test", model="sonnet", effort="high")
        a.update(kw)
        self.out.clear()
        code = self.call("show", goal, **a)
        return code, "\n".join(self.out)

    def proposal_id(self, text):
        import re
        return re.search(r"Proposal id ([0-9a-f]{8})\.", text).group(1)

    def seed_history(self, n=5, builder_uu=40, check_uu=20, size=40):
        """n earlier goals whose task T-01 reached in review with a measured builder and check spend."""
        for _ in range(n):
            goal = self.planned(1)
            gs.approve_plan(self.root, goal, builder="claude-build", tester="kiro-test", guide="claude-guide",
                            model="sonnet", effort="high", task_budget_uu=30, goal_budget_uu=100, per_day=500,
                            when=self.when, now=self.clock())
            t = gs.read_task(self.root, goal, "T-01")
            t["packet"]["size"] = size
            t = dict(t, state="in review", sha256=gp.packet_from_dict(t["packet"]).sha256(),
                     **{gs.MEASURED_KEY: {"builder": builder_uu, "tester": None, "check": check_uu}})
            gs.write_task(self.root, goal, "T-01", t)


class ShowTests(ProposalCase):
    def test_show_with_the_roles_prints_the_proposal_and_writes_nothing(self):
        goal = self.g_start()
        before = snapshot(self.root, str(self.root) + "-worktrees")
        code, text = self.show(goal)
        self.assertEqual(code, 0, self.err)
        self.assertIn("    Proposed: no history for the builder: give a number with --budget T-01=N", text)
        self.assertRegex(text, r"Proposed goal budget: 122 UU \(the tasks 102, the planning run 20\)\. Proposal id [0-9a-f]{8}\.")
        self.assertEqual(snapshot(self.root, str(self.root) + "-worktrees"), before)

    def test_show_without_the_roles_prints_the_hint(self):
        goal = self.g_start()
        self.out.clear()
        self.assertEqual(self.call("show", goal), 0)
        self.assertIn(cs.gl.PROPOSAL_HINT, "\n".join(self.out))

    def test_show_needs_all_four_role_words_together(self):
        goal = self.g_start()
        self.assertEqual(self.call("show", goal, builder="claude-build"), 64)

    def test_history_of_earlier_goals_makes_a_number(self):
        self.seed_history(5)
        goal = self.g_start(size=40)
        code, text = self.show(goal)
        self.assertEqual(code, 0, self.err)
        self.assertIn("    Proposed: 190 UU = builder 60 (history, 5 tasks) + tester 100 (unknown) + check 30 "
                      "(history, 5 tasks)", text)


class HistoryTests(ProposalCase):
    def test_only_tasks_in_review_or_merged_are_history(self):
        self.seed_history(5)
        for goal in gs.list_goals(self.root)[:1]:  # one of the five did not reach review
            t = gs.read_task(self.root, goal, "T-01")
            gs.write_task(self.root, goal, "T-01", dict(t, state="failed", reason="tests"))
        goal = self.g_start(size=40)
        self.assertIn("no history for the builder", self.show(goal)[1])

    def test_another_model_or_effort_is_not_history(self):
        self.seed_history(5)
        goal = self.g_start(size=40)
        self.assertIn("no history for the builder", self.show(goal, model="opus")[1])
        self.assertIn("no history for the builder", self.show(goal, effort="low")[1])


class AcceptTests(ProposalCase):
    def test_accept_takes_exactly_the_shown_numbers(self):
        self.seed_history(5)
        goal = self.g_start(tasks=2, size=40)
        _code, text = self.show(goal)
        pid = self.proposal_id(text)
        self.assertEqual(self.call("approve", goal, "claude-build", "kiro-test", "sonnet", "high", None, None,
                                   accept_proposed=pid), 0, self.err)
        for task in ("T-01", "T-02"):
            self.assertEqual(gs.read_task(self.root, goal, task)["packet"]["budget_uu"], 190)
        self.assertEqual(gs.read_goal(self.root, goal)["goal_budget_uu"], 400)
        entry = [e for e in logbook.read_checked(self.root) if "plan approved" in e.added][-1]
        self.assertIn("Proposed and accepted: T-01 190, T-02 190; goal budget 400.", entry.checked)

    def test_the_owners_numbers_win(self):
        self.seed_history(5)
        goal = self.g_start(tasks=2, size=40)
        pid = self.proposal_id(self.show(goal)[1])
        self.assertEqual(self.call("approve", goal, "claude-build", "kiro-test", "sonnet", "high", None, 500,
                                   budget=["T-02=150"], accept_proposed=pid), 0, self.err)
        self.assertEqual([gs.read_task(self.root, goal, t)["packet"]["budget_uu"] for t in ("T-01", "T-02")], [190, 150])
        self.assertEqual(gs.read_goal(self.root, goal)["goal_budget_uu"], 500)
        entry = [e for e in logbook.read_checked(self.root) if "plan approved" in e.added][-1]
        self.assertIn("Proposed and accepted: T-01 190.", entry.checked)

    def test_a_changed_proposal_is_refused_and_nothing_changes(self):
        self.seed_history(5)
        goal = self.g_start()
        pid = self.proposal_id(self.show(goal)[1])
        self.seed_history(1, builder_uu=80)  # new history after the owner read it
        before = snapshot(self.root, str(self.root) + "-worktrees")
        self.err.clear()
        self.assertEqual(self.call("approve", goal, "claude-build", "kiro-test", "sonnet", "high", None, None,
                                   accept_proposed=pid), 2)
        self.assertIn("The proposal changed since you read it", "\n".join(self.err))
        self.assertEqual(snapshot(self.root, str(self.root) + "-worktrees"), before)
        self.assertFalse(gs.read_goal(self.root, goal)["approved"])

    def test_no_history_needs_the_owners_number(self):
        goal = self.g_start()
        pid = self.proposal_id(self.show(goal)[1])
        self.err.clear()
        self.assertEqual(self.call("approve", goal, "claude-build", "kiro-test", "sonnet", "high", None, None,
                                   accept_proposed=pid), 2)
        self.assertIn("No history for T-01", "\n".join(self.err))
        self.assertFalse(gs.read_goal(self.root, goal)["approved"])
        self.assertEqual(self.call("approve", goal, "claude-build", "kiro-test", "sonnet", "high", None, None,
                                   budget=["T-01=120"], accept_proposed=pid), 0, self.err)
        self.assertEqual(gs.read_goal(self.root, goal)["goal_budget_uu"], 140)

    def test_a_budget_below_the_kiro_runs_is_a_warning_not_a_refusal(self):
        goal = self.g_start()
        pid = self.proposal_id(self.show(goal)[1])
        self.err.clear()
        self.assertEqual(self.call("approve", goal, "claude-build", "kiro-test", "sonnet", "high", 30, 100,
                                   accept_proposed=pid), 0, self.err)
        self.assertIn("Warning: task T-01 has 30 UU, less than the 100 UU", "\n".join(self.err))

    def test_without_numbers_or_an_id_is_usage_and_a_bad_id_too(self):
        goal = self.g_start()
        self.assertEqual(self.call("approve", goal, "claude-build", "kiro-test", "sonnet", "high", None, None), 64)
        self.assertEqual(self.call("approve", goal, "claude-build", "kiro-test", "sonnet", "high", None, None,
                                   accept_proposed="nothex!!"), 64)

    def test_without_a_terminal_accept_changes_nothing(self):
        goal = self.g_start()
        pid = self.proposal_id(self.show(goal)[1])
        self.terminal = False
        self.assertEqual(self.call("approve", goal, "claude-build", "kiro-test", "sonnet", "high", None, None,
                                   budget=["T-01=50"], accept_proposed=pid), 2)
        self.assertFalse(gs.read_goal(self.root, goal)["approved"])

    def test_an_approved_budget_never_rises_by_a_later_proposal(self):
        goal = self.g_start()
        pid = self.proposal_id(self.show(goal)[1])
        self.assertEqual(self.call("approve", goal, "claude-build", "kiro-test", "sonnet", "high", None, None,
                                   budget=["T-01=60"], accept_proposed=pid), 0, self.err)
        self.seed_history(6, builder_uu=90)
        before = snapshot(gs.goal_dir(self.root, goal))
        code, text = self.show(goal)
        self.assertEqual(code, 0)
        self.assertIn("this proposal is information only", text)
        self.assertEqual(snapshot(gs.goal_dir(self.root, goal)), before)
        self.assertEqual(gs.read_task(self.root, goal, "T-01")["packet"]["budget_uu"], 60)
        self.assertEqual(self.call("approve", goal, "claude-build", "kiro-test", "sonnet", "high", 999, 9999), 2)


class MeasuredTests(rs.RunCase):
    def test_the_supervisor_keeps_the_measured_spend_of_each_role(self):
        goal = self.approved(1)
        out = self.run_task(goal, "T-01", [{"steps": rs.builder_steps(), "spend": 7}, {"steps": rs.tester_steps(), "spend": 3},
                                           {"steps": rs.check_steps(), "spend": 2}])
        self.assertEqual(out.state, "in review", out)
        self.assertEqual(gs.read_task(self.root, goal, "T-01")[gs.MEASURED_KEY], {"builder": 7, "tester": 3, "check": 2})

    def test_a_run_that_was_not_settled_measured_is_not_history(self):
        goal = self.approved(1)
        with mock.patch.object(goalbudget, "window_measured", lambda before, led, agent: agent != "kiro-test"):
            self.run_task(goal, "T-01", [{"steps": rs.builder_steps(), "spend": 7}, {"steps": rs.tester_steps(), "spend": 3},
                                         {"steps": rs.check_steps(), "spend": 2}])
        self.assertEqual(gs.read_task(self.root, goal, "T-01")[gs.MEASURED_KEY], {"builder": 7, "tester": None, "check": 2})

    def test_a_bad_measured_key_does_not_read(self):
        goal = self.approved(1)
        t = gs.read_task(self.root, goal, "T-01")
        for bad in ({"builder": -1}, {"guide": 3}, {"builder": True}, ["builder"]):
            with self.subTest(bad=bad):
                (gs.goal_dir(self.root, goal) / "T-01.json").write_text(json.dumps(dict(t, **{gs.MEASURED_KEY: bad})))
                with self.assertRaises(gs.GoalError):
                    gs.read_task(self.root, goal, "T-01")


if __name__ == "__main__":
    unittest.main()
