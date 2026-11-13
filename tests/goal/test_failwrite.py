"""W9.5 / W9.R13 (pitfall 5): a failed log write must not let work continue.

A fault at each of the five steps of the write order, for each transition of the table. The parts that need a running
child (it is gone within 12 seconds, nothing starts after, exit 2) belong to the supervisor (W9.7) and are not here:
this module tests the record that the supervisor relies on.
"""

import errno
import unittest
from unittest import mock

from tests.goal import gen
from tests.goal.goalsupport import GoalCase
from umwayi import goallog, logbook
from umwayi import goalpacket as gp
from umwayi import goalstate as gs
from umwayi.errors import UmwayiError

# step number -> (the hook that a fault is injected into)
HOOKS = {0: "_queue_row", 1: "_check_logbook", 2: "_append_entry", 3: "_write_file", 4: "_append_event"}
PATH = {  # how to reach each state from "queued" through legal moves
    "queued": [],
    "running": [("running", "start")],
    "in review": [("running", "start"), ("in review", "checked")],
    "needs owner": [("needs owner", "ask")],
}
CASES = [(old, new, reason) for old, news in gp.TRANSITIONS.items() for new in news for reason in gp.REASONS[new][:1]
         if old in PATH]


class FailWriteTests(GoalCase):
    def at(self, old):
        goal = self.approved(n=1)
        for new, reason in PATH[old]:
            self.move(goal, "T-01", new, reason, **({"role": "builder", "agent": "claude-build"} if new == "running" else {}))
        return goal

    def last_logbook_state(self, goal, task="T-01"):
        return gs.view(self.root)[goal].tasks[task].state

    def seq_pair(self, goal):
        return gs.read_task(self.root, goal, "T-01")["seq"], gs.view(self.root)[goal].tasks["T-01"].seq

    def test_a_fault_at_every_step_for_every_transition(self):
        done = 0
        for old, new, reason in CASES:
            for step, hook in HOOKS.items():
                if step == 0 and new != "needs owner":
                    continue  # no queue row is added for this change
                with self.subTest(old=old, new=new, step=step):
                    self.setUp()
                    goal = self.at(old)
                    before_entries = len(self.entries())
                    before_file = gs.read_task(self.root, goal, "T-01")
                    with mock.patch.object(gs, hook, side_effect=OSError(errno.ENOSPC, "full")):
                        with self.assertRaises(gs.RecordFailed) as cm:
                            self.move(goal, "T-01", new, reason)
                    self.assertEqual(cm.exception.step, step)
                    self.assertIsInstance(cm.exception, UmwayiError)
                    file_seq, log_seq = self.seq_pair(goal)
                    if step <= 2:
                        # the change did not happen: no state entry, the file is as it was
                        self.assertEqual(log_seq, before_file["seq"])
                        self.assertEqual(gs.read_task(self.root, goal, "T-01"), before_file)
                        state_entries = [e for e in self.entries()[before_entries:] if e.source == gs.SOURCE]
                        self.assertEqual(state_entries, [])
                    else:
                        # the logbook has the change; the file is behind (step 3) or right with the event missing (step 4)
                        self.assertEqual(log_seq, before_file["seq"] + 1)
                        self.assertEqual(file_seq, before_file["seq"] + (0 if step == 3 else 1))
                    self.assertLessEqual(file_seq, log_seq)  # the file is never ahead of the logbook
                    gs.repair(self.root, when=self.when, now=self.clock())
                    t = gs.read_task(self.root, goal, "T-01")
                    self.assertEqual(t["state"], self.last_logbook_state(goal))
                    self.assertEqual(t["seq"], self.seq_pair(goal)[1])
                    if step >= 3:
                        events = goallog.read((self.root / ".umwayi" / "goals" / goal / "T-01.events.jsonl").read_bytes())[0]
                        recovered = [e for e in events if e["kind"] == "state" and e["data"]["recovered"]]
                        self.assertEqual(len(recovered), 1)
                    done += 1
        self.assertGreaterEqual(done, 25)

    def test_repair_is_idempotent(self):
        goal = self.at("queued")
        with mock.patch.object(gs, "_write_file", side_effect=OSError("x")):
            with self.assertRaises(gs.RecordFailed):
                self.move(goal, "T-01", "running", "start")
        self.assertTrue(gs.repair(self.root, when=self.when, now=self.clock()))
        self.assertEqual(gs.repair(self.root, when=self.when, now=self.clock()), [])

    def test_a_file_ahead_of_the_logbook_is_needs_owner_unclear(self):
        goal = self.at("queued")
        t = gs.read_task(self.root, goal, "T-01")
        t.update(state="running", seq=1)
        gs.write_task(self.root, goal, "T-01", t)  # a state the logbook never recorded
        gs.repair(self.root, when=self.when, now=self.clock())
        t = gs.read_task(self.root, goal, "T-01")
        self.assertEqual((t["state"], t["reason"]), ("needs owner", "unclear"))
        self.assertEqual(self.last_logbook_state(goal), "needs owner")

    def test_a_read_only_command_shows_the_logbook_state(self):
        goal = self.at("queued")
        with mock.patch.object(gs, "_write_file", side_effect=OSError("x")):
            with self.assertRaises(gs.RecordFailed):
                self.move(goal, "T-01", "running", "start")
        view = gs.view(self.root)[goal]
        self.assertEqual(view.tasks["T-01"].state, "running")
        self.assertEqual(gs.read_task(self.root, goal, "T-01")["state"], "queued")
        self.assertEqual(gs.behind(self.root), [(goal, "T-01")])

    def test_a_full_disk_while_the_event_log_is_written_and_a_read_only_goal_folder(self):
        goal = self.at("queued")
        for exc in (OSError(errno.ENOSPC, "full"), OSError(errno.EROFS, "read-only"), OSError(errno.EACCES, "denied")):
            with mock.patch.object(goallog, "_write", side_effect=exc):
                with self.assertRaises(gs.RecordFailed) as cm:
                    self.move(goal, "T-01", "running", "start")
                self.assertLessEqual(cm.exception.step, 1)  # the probe stops it before the logbook is touched
            self.assertEqual(self.state(goal, "T-01"), "queued")
        self.assertEqual(self.last_logbook_state(goal), "queued")

    def test_the_logbook_made_unwritable_stops_the_change(self):
        goal = self.at("queued")
        with mock.patch.object(logbook, "check_writable", side_effect=UmwayiError("logbook: broken")):
            with self.assertRaises(gs.RecordFailed) as cm:
                self.move(goal, "T-01", "running", "start")
        self.assertEqual(cm.exception.step, 1)
        self.assertEqual(self.last_logbook_state(goal), "queued")

    def test_the_error_text_never_quotes_the_path_or_the_os_message(self):
        goal = self.at("queued")
        with mock.patch.object(gs, "_write_file", side_effect=OSError(errno.EIO, str(self.root))):
            with self.assertRaises(gs.RecordFailed) as cm:
                self.move(goal, "T-01", "running", "start")
        self.assertNotIn(str(self.root), str(cm.exception))
        self.assertIn("umwayi could not write its record, so it stopped", str(cm.exception))

    def test_the_move_must_follow_the_table_and_the_current_state(self):
        goal = self.at("queued")
        for new, reason in (("merged", "observed"), ("in review", "checked"), ("failed", "tests")):
            with self.assertRaises(gs.GoalError):
                self.move(goal, "T-01", new, reason)
        with self.assertRaises(gs.GoalError):
            self.move(goal, "T-01", "running", "bogus")
        with self.assertRaises(gs.GoalError):
            self.move(goal, "T-01", "stopped", "stalled")  # a failed-state reason for a stopped task
        self.assertEqual(self.state(goal, "T-01"), "queued")

    def test_property_random_faults_never_leave_a_started_task_without_its_start_entry(self):
        moves = [("running", "start"), ("in review", "checked"), ("merged", "observed"), ("failed", "tests"),
                 ("needs owner", "ask"), ("queued", "answered"), ("stopped", "kill"), ("failed", "stalled")]

        def make(g):
            return [(g.pick(moves), g.pick([None] * 6 + list(HOOKS.values()))) for _ in range(g.between(1, 8))], g.bits(1)

        def check(case):
            steps, _ = case
            self.setUp()
            goal = self.approved(n=1)
            for (new, reason), hook in steps:
                try:
                    if hook is None:
                        self.move(goal, "T-01", new, reason)
                    else:
                        with mock.patch.object(gs, hook, side_effect=OSError("fault")):
                            self.move(goal, "T-01", new, reason)
                except gs.RecordFailed:
                    # the supervisor stops; the next command repairs before it does anything else (W9.R13.5)
                    gs.repair(self.root, when=self.when, now=self.clock())
                except gs.GoalError:
                    pass
                f = gs.read_task(self.root, goal, "T-01")
                v = gs.view(self.root)[goal].tasks["T-01"]
                if f["seq"] > v.seq:
                    return False  # the file is ahead of the logbook
                if f["state"] == "running" and f["seq"] == v.seq and v.state != "running":
                    return False
            gs.repair(self.root, when=self.when, now=self.clock())
            f = gs.read_task(self.root, goal, "T-01")
            return f["state"] == gs.view(self.root)[goal].tasks["T-01"].state

        gen.run_property(self, make, check, cases=60, seeds=gen.SEEDS, shrinkable=False)


class PlantedFaultTests(GoalCase):
    """The faults of W9.R13.7 that live in this module. Each is caught by the same contract the real code passes."""

    def contract(self):
        for step, hook in HOOKS.items():
            self.setUp()
            goal = self.approved(n=1)
            with mock.patch.object(gs, hook, side_effect=OSError("fault")):
                with self.assertRaises(gs.RecordFailed):
                    self.move(goal, "T-01", "needs owner", "ask")
            file_seq = gs.read_task(self.root, goal, "T-01")["seq"]
            log_seq = gs.view(self.root)[goal].tasks["T-01"].seq
            self.assertLessEqual(file_seq, log_seq)  # never ahead
        self.setUp()
        goal = self.approved(n=1)
        with mock.patch.object(gs, "_write_file", side_effect=OSError("fault")):
            with self.assertRaises(gs.RecordFailed):
                self.move(goal, "T-01", "running", "start")
        gs.repair(self.root, when=self.when, now=self.clock())
        self.assertEqual(gs.read_task(self.root, goal, "T-01")["state"], "running")  # the logbook wins

    def test_the_contract_passes_on_the_real_code(self):
        self.contract()

    def test_fault_entry_written_after_the_state_file(self):
        real = gs.STEP_ORDER
        wrong = tuple("file" if x == "entry" else "entry" if x == "file" else x for x in real)
        self.assertNotEqual(real, wrong)
        with mock.patch.object(gs, "STEP_ORDER", wrong):
            with self.assertRaises(AssertionError):
                self.contract()

    def test_fault_failed_event_append_ignored(self):
        with mock.patch.object(gs, "_run_step", lambda step, fn, *a, **k: _swallow(fn, *a, **k)):
            with self.assertRaises(AssertionError):
                self.contract()

    def test_fault_probe_skipped(self):
        with mock.patch.object(gs, "STEP_ORDER", tuple(s for s in gs.STEP_ORDER if s != "probe")):
            with self.assertRaises(AssertionError):
                self.contract_probe()

    def contract_probe(self):
        goal = self.approved(n=1)
        with mock.patch.object(goallog, "_write", side_effect=OSError(errno.ENOSPC, "full")):
            with self.assertRaises(gs.RecordFailed):
                self.move(goal, "T-01", "running", "start")
        # the change must not have happened: the probe stops it before the logbook is touched
        self.assertEqual(gs.view(self.root)[goal].tasks["T-01"].state, "queued")

    def test_the_probe_check_passes_on_the_real_code(self):
        self.contract_probe()

    def test_fault_repair_prefers_the_file_over_the_logbook(self):
        with mock.patch.object(gs, "repair", lambda *a, **k: []):
            with self.assertRaises(AssertionError):
                self.contract()


def _swallow(fn, *a, **k):
    try:
        return fn(*a, **k)
    except Exception:
        return None


if __name__ == "__main__":
    unittest.main()
