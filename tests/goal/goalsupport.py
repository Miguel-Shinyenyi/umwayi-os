"""Helpers shared by the state tests (W9.5): a goal made through the public functions of umwayi/goalstate.py."""

import json

from tests.goal.fakeroot import DATE, FakeRoot
from umwayi import goalpacket as gp
from umwayi import goalstate as gs

GOAL_TEXT = "Build the thing the owner asked for, in small safe steps."
SENTINEL = "SENTINEL-GOAL-TEXT-must-not-reach-the-logbook"


def plan_bytes(n=2, size=40):
    tasks = [{"goal": f"Do the numbered piece of work number {i} now.", "context": [],
              "checks": [f"Check number {i} of the piece can be answered pass or fail."], "size": size,
              "files": [f"umwayi/piece{i}.py", f"tests/goal/test_piece{i}.py"]} for i in range(1, n + 1)]
    return json.dumps({"tasks": tasks}).encode("utf-8")


class GoalCase(FakeRoot):
    """A root plus a way to make a goal at each stage."""

    def started(self, text=GOAL_TEXT, plan_hours=168, wait_hours=24):
        return gs.start_goal(self.root, text, "claude-guide", 20, when=self.when, now=self.clock(),
                             plan_hours=plan_hours, wait_hours=wait_hours)

    def planned(self, n=2, **kw):
        goal = self.started(**kw)
        gs.record_plan(self.root, goal, gp.parse_plan(plan_bytes(n)), "claude-guide", when=self.when, now=self.clock())
        return goal

    def approved(self, n=2, keep=None, goal_budget=100, **kw):
        goal = self.planned(n, **kw)
        gs.approve_plan(self.root, goal, builder="claude-build", tester="kiro-test", guide="claude-guide", model="sonnet",
                        effort="high", task_budget_uu=30, goal_budget_uu=goal_budget, keep=keep, per_day=500,
                        when=self.when, now=self.clock())
        return goal

    def move(self, goal, task, new, reason, **kw):
        kw.setdefault("when", self.when)
        kw.setdefault("now", self.clock())
        return gs.change_state(self.root, goal, task, new, reason, **kw)

    def state(self, goal, task):
        return gs.read_task(self.root, goal, task)["state"]
