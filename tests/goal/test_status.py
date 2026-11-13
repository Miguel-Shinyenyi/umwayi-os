"""W9.8 / W9.R11: pitfall 3, a status that shows only "connected".

`umwayi goal status` prints, in order: what waits for the owner with its age and the time left, the task and its state,
the last real event and its age, the supervisor line after it, the child's line, the spend and the skipped lines. A poll
never moves the last real event, a time in the future is `age unknown`, more than 5 minutes is QUIET, and no text of a
helper is ever in a line. The status of five goals in every state is a golden (tests/goal/golden/status.txt; set
UMWAYI_UPDATE_GOLDEN=1 to rewrite it, then read the diff). Each check has a planted fault that it must catch.
"""

import os
import unittest
from pathlib import Path
from unittest import mock

from tests.goal import cmdsupport as cs
from tests.goal import runsupport as rs
from umwayi import goal as gl
from umwayi import goallog
from umwayi import goalstate as gs

GOLDEN = Path(__file__).with_name("golden") / "status.txt"
SENTINEL = "SENTINEL-HELPER-OUTPUT-never-in-status"


def stamp(epoch):
    return goallog._stamp(epoch)


class StatusCase(cs.CmdCase):
    def running(self, minutes_silent=20, polls=True):
        """A task `running` with a builder that started, one output event, then nothing real for N minutes; the
        supervisor's polls go on (fake clock). The goal lock is held as a live supervisor would hold it."""
        goal = self.g_approved()
        gs.change_state(self.root, goal, "T-01", "running", "start", when=self.when, now=self.clock(), role="builder",
                        agent="claude-build", cap_uu=30, base="a" * 40)
        w = goallog.Writer(gs.events_path(self.root, goal, "T-01"), self.clock).open()
        w.append("started", {"role": "builder", "agent": "claude-build", "cap_uu": 30, "pid": os.getpid()})
        w.append("output", {"lines": 14, "bytes": 900, "skipped": 0})
        for _ in range(minutes_silent * 2):
            self.clock.advance(30)
            if polls:
                w.append("poll", {})
        return goal

    def lines(self, goal=None, held=True):
        c = self.ctx()
        if held:
            with gs.lock(self.root):
                return gl.status_lines(c, goal)
        return gl.status_lines(c, goal)


class StatusTests(StatusCase):
    def scenario_quiet_and_alive(self):
        goal = self.running(20)
        text = self.lines(goal)
        last = next(l for l in text if l.strip().startswith("Last event:"))
        self.assertIn("output: 14 lines, 20 min ago", last)
        self.assertIn("QUIET for 20 min", last)
        sup = next(i for i, l in enumerate(text) if "Supervisor:" in l)
        self.assertGreater(sup, text.index(last))  # the supervisor line comes after the last event, never alone
        self.assertIn("Supervisor: alive (last poll 0 s ago)", text[sup])
        return text

    def test_a_silent_builder_shows_its_last_real_event_its_age_and_quiet(self):
        self.scenario_quiet_and_alive()

    def test_planted_fault_a_poll_counted_as_real(self):
        with self.assertRaises(AssertionError):
            with mock.patch.dict(goallog.KINDS, {"poll": ({}, True)}):
                self.scenario_quiet_and_alive()

    def test_planted_fault_a_status_built_from_the_process_only(self):
        with self.assertRaises((AssertionError, StopIteration)):
            with mock.patch.object(gl, "_task_lines", lambda ctx, goal, g, t, alive: ["  Supervisor: alive."]):
                self.scenario_quiet_and_alive()

    def test_the_last_event_is_shown_when_the_process_line_is_missing(self):
        goal = self.running(20)
        text = self.lines(goal, held=False)
        self.assertTrue(any("Last event: output: 14 lines, 20 min ago" in l for l in text))
        self.assertTrue(any("Supervisor: lost" in l for l in text))

    def test_polls_every_second_never_change_the_last_real_event(self):
        goal = self.running(5)
        before = [l for l in self.lines(goal) if "Last event" in l]
        w = goallog.Writer(gs.events_path(self.root, goal, "T-01"), self.clock).open()
        for _ in range(60):
            w.append("poll", {})
        self.assertEqual([l for l in self.lines(goal) if "Last event" in l], before)

    def scenario_future(self):
        goal = self.running(0)
        w = goallog.Writer(gs.events_path(self.root, goal, "T-01"), lambda: self.clock() + 3600).open()
        w.append("error", {"sig": "3fa91c20b1c4d5e6"})
        last = next(l for l in self.lines(goal) if "Last event" in l)
        self.assertIn("age unknown", last)
        self.assertIn("QUIET for age unknown", last)

    def test_an_event_dated_in_the_future_is_age_unknown_and_quiet(self):
        self.scenario_future()

    def test_planted_fault_an_age_in_the_future_shown_as_0(self):
        with self.assertRaises(AssertionError):
            with mock.patch.object(gl, "_age", lambda ctx, t: None if t is None else max(0, ctx.now - t)):
                self.scenario_future()

    def scenario_sentinel(self):
        goal = self.g_approved()
        scripts = [{"steps": [{"print": SENTINEL}, {"error": f"Error: {SENTINEL}"}] + rs.builder_steps(goal, "T-01"), "spend": 2},
                   {"steps": [{"print": SENTINEL}] + rs.tester_steps()}, {"steps": rs.check_steps()}]
        self.assertEqual(self.call("run", goal, scripts=scripts), 0, self.err)
        text = "\n".join(self.lines(goal, held=False))
        self.assertNotIn(SENTINEL, text)
        self.assertIn("in review", text)

    def test_a_sentinel_in_the_helper_output_never_appears_in_the_status(self):
        self.scenario_sentinel()

    def test_planted_fault_the_helpers_text_in_the_line(self):
        def leaky(ev):
            return f"{ev['kind']} {SENTINEL}"
        with self.assertRaises(AssertionError):
            with mock.patch.object(gl, "_event_words", leaky):
                self.scenario_sentinel()

    def test_what_waits_for_the_owner_comes_first_with_age_and_time_left(self):
        goal = self.g_approved()
        gs.change_state(self.root, goal, "T-01", "needs owner", "unclear", when=self.when, now=self.clock())
        self.clock.advance(3 * 3600)
        text = self.lines(held=False)
        self.assertEqual(text[0], "Waiting for you")
        self.assertIn(f"Goal {goal} task T-01 needs you (unclear). Asked 3 h ago, denied in 21 h.", text[1])

    def test_status_writes_nothing_and_takes_no_lock(self):
        goal = self.running(3)
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file() and ".git" not in p.parts}
        with gs.lock(self.root):  # a supervisor holds it; status still works
            self.assertEqual(self.call("status"), 0)
        after = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file() and ".git" not in p.parts}
        self.assertEqual(after, before)

    def test_skipped_log_lines_are_counted(self):
        goal = self.running(1)
        with open(gs.events_path(self.root, goal, "T-01"), "ab") as f:
            f.write(b"not an event\n")
        self.assertTrue(any("Skipped log lines: 1" in l for l in self.lines(goal)))


class GoldenTests(StatusCase):
    def five_goals(self):
        # 1 a plan that waits, 2 a task that needs the owner, 3 a running task, 4 in review, 5 stopped
        g1 = self.g_start()
        g2 = self.g_approved()
        gs.change_state(self.root, g2, "T-01", "needs owner", "busy", when=self.when, now=self.clock())
        g4 = self.g_approved()
        gs.change_state(self.root, g4, "T-01", "running", "start", when=self.when, now=self.clock())
        gs.change_state(self.root, g4, "T-01", "in review", "checked", when=self.when, now=self.clock(),
                        branch=f"umwayi/{g4.lower()}-t-01", tip="b" * 40, spent_uu=17)
        g5 = self.g_approved()
        gs.stop_goal(self.root, g5, "owner", when=self.when, now=self.clock(), queued_too=True)
        g3 = self.g_approved()
        gs.change_state(self.root, g3, "T-01", "running", "start", when=self.when, now=self.clock(), role="builder",
                        agent="claude-build", cap_uu=30, base="a" * 40)
        w = goallog.Writer(gs.events_path(self.root, g3, "T-01"), self.clock).open()
        w.append("started", {"role": "builder", "agent": "claude-build", "cap_uu": 30, "pid": 0})
        w.append("fingerprint", {"changed": True, "files": 3})
        self.clock.advance(7 * 60)
        return [g1, g2, g3, g4, g5]

    def test_the_status_of_five_goals_in_every_state_is_the_golden(self):
        self.five_goals()
        text = "\n".join(self.lines(held=False)) + "\n"
        if os.environ.get("UMWAYI_UPDATE_GOLDEN"):
            GOLDEN.write_text(text, encoding="utf-8")
        self.assertEqual(text, GOLDEN.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
