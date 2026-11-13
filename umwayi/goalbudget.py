"""Goal orchestration (W9.5): the ledger window, the caps and the budget account of a goal (W9.R15).

Pure over a `budget.Ledger`: no clock, no file, no process. What a run spent is read from the budget ledger (the logbook
entries of `umwayi budget`), never from the AI helper's own word. A foreign run of the same agent inside the window is
counted too, which over-counts and is safe (KNOWN-LIMITS 218).
"""

from __future__ import annotations

from umwayi import budget, units

ROLES = ("guide", "builder", "tester", "check")


def _int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def run_ids(ledger):
    """The ids of all reserved runs: the 'before' side of a window."""
    return frozenset(ledger.reserves)


def spent_micros(before, ledger, agent):
    """Micros of the runs of `agent` that appear in `ledger` and not in `before`: the settle if there is one, else the
    full reservation."""
    total = 0
    for run, r in ledger.reserves.items():
        if run in before or r.agent != agent:
            continue
        s = ledger.settles.get(run)
        total += s.micros if s is not None else r.micros
    return total


def spent_uu(before, ledger, agent):
    return units.uu(spent_micros(before, ledger, agent))


def day_left_uu(ledger, u, agent, platform, day):
    """What the day limits still allow, in whole UU (the child checks the same limits itself)."""
    return budget.fit(ledger, u, agent, platform, day).left_today_uu()


def cap(task_left, goal_left, per_run, day_left):
    """The cap for the next run: the smallest of the four, in whole UU. Under 1 means no run. Bad input means no run."""
    vals = (task_left, goal_left, per_run, day_left)
    if not all(_int(v) for v in vals):
        return 0
    return max(0, min(vals))


def next_cap(task_left, goal_left, per_run, day_left):
    """(cap, why): why is `ok`, or the limit that refused the run: goal, task, day or run."""
    c = cap(task_left, goal_left, per_run, day_left)
    if c >= 1:
        return c, "ok"
    for why, v in (("goal", goal_left), ("task", task_left), ("day", day_left), ("run", per_run)):
        if not _int(v) or v < 1:
            return 0, why
    return 0, "run"


def approval_problem(task_budgets, goal_budget, per_day, plan_uu=0):
    """None, or `task_budget` / `goal_budget` (W9.R5.5, W9.R15.1). Every task has a budget of 1 to the per-day limit and
    the goal budget covers them and the planning run."""
    if not isinstance(task_budgets, dict) or not task_budgets:
        return "task_budget"
    for v in task_budgets.values():
        if not _int(v) or not 1 <= v <= per_day:
            return "task_budget"
    if not _int(goal_budget) or goal_budget < sum(task_budgets.values()) + (plan_uu if _int(plan_uu) else 0):
        return "goal_budget"
    return None


def plan_budget_problem(plan_uu, per_run):
    return None if _int(plan_uu) and 1 <= plan_uu <= per_run else "plan_budget"


def cap_option_ok(n, per_run):
    """`--cap-uu N` is a whole number from 1 to `per_run` (above it is a usage error, exit 64)."""
    return _int(n) and 1 <= n <= per_run


class Account:
    """What a goal has spent, by task and role, against its budgets."""

    def __init__(self, goal_budget, plan_uu, task_budgets):
        self.goal_budget = goal_budget
        self.plan_uu = plan_uu
        self.task_budgets = dict(task_budgets)
        self._spent = {t: {} for t in self.task_budgets}

    def task_spent(self, task):
        return sum(self._spent[task].values())

    def task_left(self, task):
        return self.task_budgets[task] - self.task_spent(task)

    def goal_left(self):
        return self.goal_budget - self.plan_uu - sum(sum(v.values()) for v in self._spent.values())

    def next_cap(self, task, per_run, day_left):
        return next_cap(self.task_left(task), self.goal_left(), per_run, day_left)

    def record(self, task, role, uu, cap=None):
        """Add a run's spend. Returns True if it passed the cap that was handed out."""
        if task not in self._spent or role not in ROLES or not _int(uu) or uu < 0:
            raise ValueError("bad spend")
        self._spent[task][role] = self._spent[task].get(role, 0) + uu
        return cap is not None and uu > cap
