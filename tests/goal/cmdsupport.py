"""Support for the tests of the goal commands (W9.8): a RunCase (a git root, three agents, rules that allow goal_start)
with a guidance.yaml that loads, and a way to run a command of umwayi/goal.py with a fake terminal and the fake agent.

The commands are called as functions with a context, so a test can say whether standard input and output are a
terminal. A few tests run `python -m umwayi goal ...` as a real child process, which never has a terminal.
"""

import os
import subprocess
import sys
from types import SimpleNamespace

from tests.goal import runsupport as rs
from tests.goal.fakeroot import REPO
from umwayi import agents
from umwayi import goal as gl
from umwayi import goalstate as gs

GUIDANCE = """version: 1
guidance:
  - id: goal-sentence-present
    source_repo: hub
    source: "understanding-first.md#3"
    text: "A task states its goal in one sentence before any work starts."
    kind: enforce
    check: goal_sentence_present
    applies_to: task
    tier: 3
    source_hash: "2f0405e879b6615f34c5168161153363896e26eab43981dc6db1d96b0c1f6bc0"
"""
GOAL_TEXT = "Build the thing the owner asked for, in small safe steps."


def plan_line(tasks=1, size=40):
    obj = {"tasks": [{"goal": f"Do the numbered piece of work number {i} now.", "context": [],
                      "checks": [f"Check number {i} of the piece can be answered pass or fail."], "size": size,
                      "files": [f"umwayi/piece{i}.py"]} for i in range(1, tasks + 1)]}
    return {"result": "UMWAYI-PLAN", "body": obj}


def ns(**kw):
    return SimpleNamespace(**kw)


class CmdCase(rs.RunCase):
    def setUp(self):
        super().setUp()
        (self.root / "guidance.yaml").write_text(GUIDANCE, encoding="utf-8")
        text = (self.root / "agents.yaml").read_text(encoding="utf-8")
        (self.root / "agents.yaml").write_text(text.replace("  - name: claude-build\n    platform: claude-code\n",
                                                            "  - name: claude-build\n    platform: claude-code\n"
                                                            "    timeout_minutes: 90\n"), encoding="utf-8")
        self.err = []
        self.terminal = True
        self.gate_code = 0

    def gate(self, root, name, workdir=None):
        return agents.Result(self.gate_code, [])

    def ctx(self, scripts=(), **kw):
        self.make_env(scripts)
        env_kw = dict(clock=self.clock, mono=self.clock, sleep=self.sleep, spawn=self.children.spawn, busy_wait=1.0)
        env_kw.update(kw)
        return gl.Ctx(self.root, int(self.clock()), self.out.append, self.err.append, tty=lambda: self.terminal,
                      gate=self.gate, env_kw=env_kw)

    def call(self, name, *args, scripts=(), **kw):
        """Run one command function the way dispatch does (every error to its exit code)."""
        c = self.ctx(scripts)
        return gl.dispatch(c, ARGS[name](*args, **kw))

    # ---- a goal at each stage, through the commands

    def g_start(self, tasks=1, size=40):
        code = self.call("start", GOAL_TEXT, "claude-guide", 20, scripts=[{"steps": [plan_line(tasks, size)], "spend": 5}])
        self.assertEqual(code, 0, self.err)
        return gs.list_goals(self.root)[-1]

    def g_approve(self, goal, **kw):
        a = dict(builder="claude-build", tester="kiro-test", model="sonnet", effort="high", task_budget_uu=30,
                 goal_budget_uu=100)
        a.update(kw)
        return self.call("approve", goal, **a)

    def g_approved(self, tasks=1):
        goal = self.g_start(tasks)
        self.assertEqual(self.g_approve(goal), 0, self.err)
        return goal

    def umwayi(self, *args, stdin=subprocess.DEVNULL):
        env = dict(os.environ, PYTHONPATH=str(REPO))
        return subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "goal", *args],
                              capture_output=True, text=True, env=env, stdin=stdin, timeout=120)


ARGS = {
    "start": lambda text, guide, n, model="", effort="": ns(goal_command="start", text=text, guide=guide,
                                                            plan_budget_uu=n, guide_model=model, guide_effort=effort),
    "show": lambda goal: ns(goal_command="show", goal=goal),
    "run": lambda goal: ns(goal_command="run", goal=goal),
    "status": lambda goal=None: ns(goal_command="status", goal=goal),
    "stop": lambda goal: ns(goal_command="stop", goal=goal),
    "report": lambda goal: ns(goal_command="report", goal=goal),
    "answer": lambda goal, task, answer: ns(goal_command="answer", goal=goal, task=task, answer=answer),
    "merged": lambda goal, task, commit=None: ns(goal_command="merged", goal=goal, task=task, commit=commit),
    "approve": lambda goal, builder, tester, model, effort, task_budget_uu, goal_budget_uu, budget=(), keep=None,
    tester_model="", tester_effort="", plan_hours=None, wait_hours=None: ns(
        goal_command="approve", goal=goal, builder=builder, tester=tester, model=model, effort=effort,
        task_budget_uu=task_budget_uu, goal_budget_uu=goal_budget_uu, budget=list(budget), keep=keep,
        tester_model=tester_model, tester_effort=tester_effort, plan_hours=plan_hours, wait_hours=wait_hours),
}
