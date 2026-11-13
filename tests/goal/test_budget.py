"""W9.5 / W9.R15 (pitfall 7): cost growing with autonomy. The ledger window, the caps and the budget account.

Tests first. The module under test is umwayi/goalbudget.py, pure over a `budget.Ledger`. The tests that start a fake
agent which overspends and is stopped belong to the supervisor (W9.7) and `--cap-uu` is W9.6.
"""

import unittest

from tests.goal import gen
from umwayi import budget, units
from umwayi import goalbudget as gb

U = units.MICROS_PER_UU
DAY = "2026-11-13"


def run_id(n):
    return f"{n:016x}"


def reserve(n, agent="claude-build", platform="claude-code", uu=30, date=DAY):
    return budget.Reserve(run_id(n), agent, platform, uu * U, date)


def settle(n, uu, agent="claude-build", platform="claude-code", reserved_uu=30):
    return budget.Settle(run_id(n), agent, platform, "measured", uu * U, (), (0, 0, 0, 0), 1, max(0, reserved_uu - uu) * U)


def ledger(reserves=(), settles=()):
    return budget.Ledger(reserves={r.run: r for r in reserves}, settles={s.run: s for s in settles})


class WindowTests(unittest.TestCase):
    def test_a_settled_run_counts_what_it_settled(self):
        before = gb.run_ids(ledger())
        after = ledger([reserve(1)], [settle(1, 12)])
        self.assertEqual(gb.spent_micros(before, after, "claude-build"), 12 * U)
        self.assertEqual(gb.spent_uu(before, after, "claude-build"), 12)

    def test_a_reserved_run_with_no_settle_counts_its_full_reservation(self):
        self.assertEqual(gb.spent_uu(frozenset(), ledger([reserve(1, uu=30)]), "claude-build"), 30)

    def test_runs_before_the_window_do_not_count(self):
        old = ledger([reserve(1)], [settle(1, 9)])
        before = gb.run_ids(old)
        new = ledger([reserve(1), reserve(2)], [settle(1, 9), settle(2, 4)])
        self.assertEqual(gb.spent_uu(before, new, "claude-build"), 4)

    def test_a_foreign_run_of_the_same_agent_is_counted_and_another_agent_is_not(self):
        after = ledger([reserve(1), reserve(2, agent="someone-else"), reserve(3)],
                       [settle(1, 5), settle(2, 50, agent="someone-else"), settle(3, 7)])  # run 3 was not ours: over-count
        self.assertEqual(gb.spent_uu(frozenset(), after, "claude-build"), 12)
        self.assertEqual(gb.spent_uu(frozenset(), after, "someone-else"), 50)
        self.assertEqual(gb.spent_uu(frozenset(), after, "nobody"), 0)

    def test_the_sum_is_rounded_up_to_whole_uu(self):
        after = ledger([reserve(1)], [budget.Settle(run_id(1), "claude-build", "claude-code", "measured", 1, (), (0, 0, 0, 0), 1, 0)])
        self.assertEqual(gb.spent_uu(frozenset(), after, "claude-build"), 1)
        self.assertEqual(gb.spent_uu(frozenset(), ledger(), "claude-build"), 0)

    def test_run_ids_is_a_frozenset_of_reserved_ids(self):
        ids = gb.run_ids(ledger([reserve(1), reserve(2)]))
        self.assertEqual(ids, frozenset({run_id(1), run_id(2)}))
        self.assertIsInstance(ids, frozenset)


class CapTests(unittest.TestCase):
    def test_the_cap_is_the_smallest_of_the_four_in_whole_uu(self):
        self.assertEqual(gb.cap(10, 5, 100, 50), 5)
        self.assertEqual(gb.cap(10, 50, 7, 50), 7)
        self.assertEqual(gb.cap(10, 50, 100, 3), 3)
        self.assertEqual(gb.cap(2, 50, 100, 50), 2)
        self.assertEqual(gb.cap(0, 50, 100, 50), 0)
        self.assertEqual(gb.cap(-5, 50, 100, 50), 0)

    def test_bad_input_gives_no_run(self):
        for args in ((None, 5, 5, 5), ("a", 5, 5, 5), (5, 5, 5, float("nan")), (True, 5, 5, 5), (5.5, 5, 5, 5)):
            self.assertEqual(gb.cap(*args), 0, args)

    def test_the_reason_a_run_is_refused(self):
        self.assertEqual(gb.next_cap(0, 50, 100, 50), (0, "task"))
        self.assertEqual(gb.next_cap(10, 0, 100, 50), (0, "goal"))
        self.assertEqual(gb.next_cap(10, 10, 100, 0), (0, "day"))
        self.assertEqual(gb.next_cap(10, 10, 0, 50), (0, "run"))
        self.assertEqual(gb.next_cap(10, 5, 100, 50), (5, "ok"))
        self.assertEqual(gb.next_cap(0, 0, 100, 50), (0, "goal"))  # the goal budget is the stronger stop


class ApprovalTests(unittest.TestCase):
    def test_an_approval_needs_a_budget_for_every_task_and_for_the_goal(self):
        self.assertIsNone(gb.approval_problem({"T-01": 30, "T-02": 30}, 60, 500))
        self.assertEqual(gb.approval_problem({"T-01": 30, "T-02": None}, 100, 500), "task_budget")
        self.assertEqual(gb.approval_problem({"T-01": 0}, 100, 500), "task_budget")
        self.assertEqual(gb.approval_problem({"T-01": 501}, 1000, 500), "task_budget")
        self.assertEqual(gb.approval_problem({"T-01": True}, 100, 500), "task_budget")
        self.assertEqual(gb.approval_problem({"T-01": 30}, None, 500), "goal_budget")
        self.assertEqual(gb.approval_problem({"T-01": 30, "T-02": 30}, 59, 500), "goal_budget")
        self.assertEqual(gb.approval_problem({}, 100, 500), "task_budget")

    def test_the_goal_budget_must_cover_the_tasks_and_the_plan_run_has_a_number(self):
        self.assertEqual(gb.approval_problem({"T-01": 30}, 40, 500, plan_uu=11), "goal_budget")
        self.assertIsNone(gb.approval_problem({"T-01": 30}, 41, 500, plan_uu=11))

    def test_the_plan_budget_is_1_to_per_run(self):
        self.assertIsNone(gb.plan_budget_problem(1, 100))
        self.assertIsNone(gb.plan_budget_problem(100, 100))
        for bad in (0, 101, None, True, "5", -1):
            self.assertEqual(gb.plan_budget_problem(bad, 100), "plan_budget", repr(bad))

    def test_cap_option_above_per_run_is_refused(self):
        self.assertTrue(gb.cap_option_ok(1, 100))
        self.assertTrue(gb.cap_option_ok(100, 100))
        for bad in (0, 101, -1, None, True, "7"):
            self.assertFalse(gb.cap_option_ok(bad, 100), repr(bad))


class AccountTests(unittest.TestCase):
    def test_planning_counts_in_the_goal_budget(self):
        a = gb.Account(goal_budget=100, plan_uu=20, task_budgets={"T-01": 40, "T-02": 40})
        self.assertEqual(a.goal_left(), 80)
        self.assertEqual(a.task_left("T-01"), 40)

    def test_every_role_of_a_task_counts_in_the_task(self):
        a = gb.Account(goal_budget=100, plan_uu=0, task_budgets={"T-01": 40})
        a.record("T-01", "builder", 10)
        a.record("T-01", "tester", 6)
        a.record("T-01", "check", 3)
        self.assertEqual(a.task_spent("T-01"), 19)
        self.assertEqual(a.task_left("T-01"), 21)
        self.assertEqual(a.goal_left(), 81)

    def test_the_next_cap_follows_the_account(self):
        a = gb.Account(goal_budget=50, plan_uu=20, task_budgets={"T-01": 40})
        self.assertEqual(a.next_cap("T-01", 100, 500), (30, "ok"))
        a.record("T-01", "builder", 25)
        self.assertEqual(a.next_cap("T-01", 100, 500), (5, "ok"))
        a.record("T-01", "tester", 5)
        self.assertEqual(a.next_cap("T-01", 100, 500), (0, "goal"))

    def test_a_run_that_passes_its_cap_is_flagged(self):
        a = gb.Account(goal_budget=50, plan_uu=0, task_budgets={"T-01": 40})
        self.assertFalse(a.record("T-01", "builder", 10, cap=10))
        self.assertTrue(a.record("T-01", "builder", 11, cap=10))

    def test_unknown_tasks_and_bad_numbers_are_refused(self):
        a = gb.Account(goal_budget=50, plan_uu=0, task_budgets={"T-01": 40})
        for args in (("T-09", "builder", 1), ("T-01", "builder", -1), ("T-01", "builder", True), ("T-01", "wizard", 1)):
            with self.assertRaises(ValueError, msg=str(args)):
                a.record(*args)

    def test_property_the_caps_never_add_up_to_more_than_the_goal_budget(self):
        def make(g):
            budgets = {f"T-0{i}": g.between(1, 60) for i in range(1, g.between(2, 5))}
            goal = g.between(sum(budgets.values()) // 2, sum(budgets.values()) + 30)
            plan = g.between(0, 15)
            runs = [(g.pick(list(budgets)), g.pick(["builder", "tester", "check"]), g.rand()) for _ in range(g.between(3, 25))]
            return budgets, max(goal, plan + 1), plan, runs, g.between(1, 100), g.between(0, 400)

        def check(case):
            budgets, goal, plan, runs, per_run, day_left = case
            a = gb.Account(goal_budget=goal, plan_uu=plan, task_budgets=budgets)
            total = plan
            for task, role, frac in runs:
                cap, why = a.next_cap(task, per_run, day_left)
                if why != "ok":
                    if cap != 0:
                        return False
                    continue
                if cap < 1 or cap > per_run or cap > a.task_left(task) or cap > a.goal_left():
                    return False
                spend = int(cap * frac)  # a fake agent that spends no more than its cap
                a.record(task, role, spend, cap=cap)
                total += spend
                if total > goal or a.task_spent(task) > budgets[task]:
                    return False
            return True

        gen.run_property(self, make, check, cases=1250, seeds=gen.SEEDS)


class PlantedFaultTests(unittest.TestCase):
    """The faults of W9.R15.8 that live in this module. The contract passes on the real code and fails on each fault."""

    def contract(self, cap=gb.cap, account_cls=gb.Account):
        self.assertEqual(cap(10, 5, 100, 50), 5)      # a goal budget checked only at approval would give 10
        self.assertEqual(cap(10, 50, 100, 3), 3)      # day limits ignored would give 10
        self.assertEqual(cap(10, 50, 7, 50), 7)
        self.assertEqual(cap(2, 50, 100, 50), 2)      # the task's own budget, not what the helper says it needs
        a = account_cls(goal_budget=100, plan_uu=20, task_budgets={"T-01": 40})
        self.assertEqual(a.goal_left(), 80)           # planning counted
        a.record("T-01", "tester", 6)
        self.assertEqual(a.task_left("T-01"), 34)     # the tester counted

    def test_the_contract_passes_on_the_real_code(self):
        self.contract()

    def test_fault_goal_budget_checked_only_at_approval(self):
        with self.assertRaises(AssertionError):
            self.contract(cap=lambda t, g, r, d: min(t, r, d))

    def test_fault_day_limits_ignored(self):
        with self.assertRaises(AssertionError):
            self.contract(cap=lambda t, g, r, d: min(t, g, r))

    def test_fault_cap_taken_from_the_agents_own_report(self):
        reported = 99
        with self.assertRaises(AssertionError):
            self.contract(cap=lambda t, g, r, d: min(reported, g, r, d))

    def test_fault_planning_not_counted(self):
        class NoPlan(gb.Account):
            def goal_left(self):
                return self.goal_budget - sum(sum(v.values()) for v in self._spent.values())

        with self.assertRaises(AssertionError):
            self.contract(account_cls=NoPlan)

    def test_fault_tester_not_counted(self):
        class NoTester(gb.Account):
            def record(self, task, role, uu, cap=None):
                if role == "tester":
                    return False
                return super().record(task, role, uu, cap)

        with self.assertRaises(AssertionError):
            self.contract(account_cls=NoTester)


class PureModuleGuard(unittest.TestCase):
    def test_goalbudget_reads_no_clock_file_or_process(self):
        import ast
        from pathlib import Path
        src = (Path(__file__).resolve().parents[2] / "umwayi" / "goalbudget.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        names = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                names |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                names.add((n.module or "").split(".")[0])
        names.discard("__future__")
        self.assertLessEqual(names, {"umwayi", "dataclasses", "math"})
        used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        for forbidden in ("time", "os", "sys", "subprocess", "open", "socket"):
            self.assertNotIn(forbidden, used)


if __name__ == "__main__":
    unittest.main()
