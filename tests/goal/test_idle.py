"""W60: the idle line. `umwayi goal status` and `umwayi up` say when a goal is idle while tasks remain, or that a task
waits for the owner, from one pure function (`goalpacket.idle_line`). It reads goal state only and writes nothing.

The table below maps a list of task states to the one expected line (or none). Each case has a planted fault: a copy of
the function with one change, which the table must catch. The command tests run on a real root with today's UTC date
(tests/goal/fakeroot.py) and check that nothing is written and no exit code changes.
"""

import ast
import inspect
import textwrap
import unittest
from pathlib import Path

from tests.goal import cmdsupport as cs
from umwayi import goal as gl
from umwayi import goalpacket as gp
from umwayi import goalstate as gs
from umwayi import up

G = "G-0007"
NEXT = "Next: python -m umwayi goal run G-0007"

TABLE = [
    # (name, [(task, state), ...], expected line or None)
    ("one queued", [("T-01", "queued")], f"Idle: 1 task queued and nothing is running. {NEXT}"),
    ("merged then queued", [("T-01", "merged"), ("T-02", "queued"), ("T-03", "queued")],
     f"Idle: 2 tasks queued and nothing is running. {NEXT}"),
    ("running", [("T-01", "running"), ("T-02", "queued")], None),
    ("in review", [("T-01", "in review"), ("T-02", "queued")], None),
    ("needs owner", [("T-01", "needs owner"), ("T-02", "queued")], "Waiting for you: T-01 needs an answer."),
    ("needs owner alone", [("T-01", "merged"), ("T-02", "needs owner")], "Waiting for you: T-02 needs an answer."),
    ("two need the owner", [("T-01", "needs owner"), ("T-02", "needs owner"), ("T-03", "queued")],
     "Waiting for you: T-01, T-02 need an answer."),
    ("failed before queued", [("T-01", "failed"), ("T-02", "queued")], None),
    ("stopped before queued", [("T-01", "stopped"), ("T-02", "queued")], None),
    ("nothing remains", [("T-01", "merged"), ("T-02", "merged")], None),
    ("no tasks", [], None),
    ("unknown state", [("T-01", "queued"), ("T-02", "sleeping")], None),
    ("bad task id", [("T-1", "queued")], None),
]


def mismatches(fn):
    return [name for name, tasks, want in TABLE if fn(G, tasks) != want]


def planted(old, new):
    """A copy of idle_line with one text change, compiled in the module's own names."""
    src = textwrap.dedent(inspect.getsource(gp.idle_line))
    assert src.count(old) == 1, old
    names = dict(vars(gp))
    exec(compile(src.replace(old, new), "<planted>", "exec"), names)
    return names["idle_line"]


class TableTests(unittest.TestCase):
    def test_every_row_of_the_table(self):
        for name, tasks, want in TABLE:
            with self.subTest(name):
                self.assertEqual(gp.idle_line(G, tasks), want)

    def test_a_bad_goal_id_prints_nothing(self):
        for goal in ("G-7", "g-0007", "", None, "G-0007; rm -rf /"):
            self.assertIsNone(gp.idle_line(goal, [("T-01", "queued")]))

    def test_planted_fault_a_running_task_prints_idle(self):
        fault = planted('in _BUSY for', 'in ("in review", "failed", "stopped") for')
        self.assertIn("running", mismatches(fault))

    def test_planted_fault_needs_owner_prints_idle_not_waiting(self):
        fault = planted("    if owner:\n", "    if False:\n")
        self.assertIn("needs owner", mismatches(fault))

    def test_planted_fault_an_empty_queue_prints_a_line(self):
        fault = planted("if not queued or", "if")
        self.assertIn("nothing remains", mismatches(fault))
        self.assertIn("no tasks", mismatches(fault))

    def test_planted_fault_in_review_prints_idle(self):
        fault = planted('in _BUSY for', 'in ("running", "failed", "stopped") for')
        self.assertIn("in review", mismatches(fault))

    def test_planted_fault_a_failed_task_before_the_queue_prints_idle(self):
        fault = planted('in _BUSY for', 'in ("running", "in review") for')
        self.assertEqual(sorted(mismatches(fault)), ["failed before queued", "stopped before queued"])

    def test_the_function_is_pure(self):
        """No file, clock, process or network: it calls nothing but its own text and list helpers."""
        tree = ast.parse(textwrap.dedent(inspect.getsource(gp.idle_line)))
        called = {n.func.id if isinstance(n.func, ast.Name) else n.func.attr
                  for n in ast.walk(tree) if isinstance(n, ast.Call)}
        self.assertLessEqual(called, {"isinstance", "fullmatch", "list", "all", "len", "sum", "any", "join"})


class CommandTests(cs.CmdCase):
    def snapshot(self):
        return {p: p.read_bytes() for p in sorted(self.root.rglob("*")) if p.is_file()}

    def status(self, goal=None):
        self.out.clear()
        code = self.call("status", goal)
        return code, list(self.out)

    def test_an_approved_goal_with_queued_tasks_says_idle(self):
        goal = self.g_approved(tasks=2)
        before = self.snapshot()
        code, lines = self.status(goal)
        self.assertEqual(code, 0)
        self.assertIn(f"  Idle: 2 tasks queued and nothing is running. Next: python -m umwayi goal run {goal}", lines)
        self.assertEqual(self.snapshot(), before)  # it writes nothing, the logbook included

    def test_a_running_task_says_nothing_new(self):
        goal = self.g_approved(tasks=2)
        gs.change_state(self.root, goal, "T-01", "running", "start", when=self.when, now=self.clock(), role="builder",
                        agent="claude-build", cap_uu=30, base="a" * 40)
        code, lines = self.status(goal)
        self.assertEqual(code, 0)
        self.assertFalse([l for l in lines if "Idle:" in l or "Waiting for you:" in l], lines)

    def test_a_task_that_needs_the_owner_says_waiting(self):
        goal = self.g_approved(tasks=2)
        gs.change_state(self.root, goal, "T-01", "needs owner", "busy", when=self.when, now=self.clock())
        code, lines = self.status(goal)
        self.assertEqual(code, 0)
        self.assertIn("  Waiting for you: T-01 needs an answer.", lines)
        self.assertFalse([l for l in lines if "Idle:" in l], lines)

    def test_a_plan_or_a_stopped_goal_says_nothing_new(self):
        plan = self.g_start()
        stopped = self.g_approved()
        gs.stop_goal(self.root, stopped, "owner", when=self.when, now=self.clock())  # its task stays queued
        self.assertEqual(gs.read_task(self.root, stopped, "T-01")["state"], "queued")
        code, lines = self.status()
        self.assertEqual(code, 0)
        self.assertFalse([l for l in lines if "Idle:" in l or "Waiting for you:" in l], (plan, lines))

    def test_umwayi_up_shows_the_same_line_and_keeps_its_goal_step(self):
        goal = self.g_approved(tasks=1)
        before = self.snapshot()
        step, lines = up._goal_lines(self.root)
        self.assertEqual((step.mark, step.name), ("ok", "goals"))
        self.assertIn(f"  Idle: 1 task queued and nothing is running. Next: python -m umwayi goal run {goal}", lines)
        self.assertEqual(self.snapshot(), before)

    def test_the_line_comes_from_the_one_function(self):
        src = Path(gl.__file__).read_text(encoding="utf-8")
        self.assertEqual(src.count("gp.idle_line("), 1)
        self.assertNotIn("Idle:", src)  # the words live only in goalpacket.idle_line


if __name__ == "__main__":
    unittest.main()
