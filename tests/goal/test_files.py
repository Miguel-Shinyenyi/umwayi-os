"""W9.5 / W9.R19: the state files, the modes, the caps, the one supervisor lock, a lost supervisor, `.gitignore`."""

import json
import os
import unittest
from pathlib import Path

from tests.goal.goalsupport import GoalCase
from umwayi import goalstate as gs
from umwayi.errors import UmwayiError

REPO = Path(__file__).resolve().parents[2]


def mode(p):
    return os.stat(p).st_mode & 0o777


class FileTests(GoalCase):
    def test_modes_and_names(self):
        goal = self.approved()
        d = self.root / ".umwayi" / "goals" / goal
        self.assertEqual(mode(self.root / ".umwayi" / "goals"), 0o700)
        self.assertEqual(mode(d), 0o700)
        for name in ("goal.json", "plan.json", "T-01.json", "T-02.json"):
            self.assertTrue((d / name).is_file(), name)
            self.assertEqual(mode(d / name), 0o600, name)
        with gs.lock(self.root):
            self.assertEqual(mode(self.root / ".umwayi" / "goal.lock"), 0o600)

    def test_goal_ids_count_up_and_are_never_reused(self):
        self.assertEqual(self.started(), "G-0001")
        self.assertEqual(self.started(), "G-0002")
        import shutil
        shutil.rmtree(self.root / ".umwayi" / "goals" / "G-0002")  # the folder is gone, the logbook still names it
        self.assertEqual(self.started(), "G-0003")

    def test_goal_json_holds_the_text_hash_length_budgets_and_flags(self):
        goal = self.approved()
        g = gs.read_goal(self.root, goal)
        self.assertEqual(g["goal"], goal)
        self.assertEqual(g["length"], len(g["text"]))
        self.assertEqual(len(g["text_sha256"]), 64)
        self.assertEqual((g["builder"], g["tester"], g["guide"], g["goal_budget_uu"], g["plan_budget_uu"]),
                         ("claude-build", "kiro-test", "claude-guide", 100, 20))
        self.assertIsNone(g["stopped"])
        self.assertEqual(g["plan"]["answer"], "yes")

    def test_task_json_holds_the_approved_packet_and_its_hash(self):
        goal = self.approved()
        t = gs.read_task(self.root, goal, "T-01")
        self.assertEqual((t["id"], t["state"], t["seq"]), ("T-01", "queued", 0))
        from umwayi import goalpacket as gp
        self.assertEqual(gp.packet_from_dict(t["packet"]).sha256(), t["sha256"])
        self.assertEqual((t["packet"]["model"], t["packet"]["effort"], t["packet"]["budget_uu"]), ("sonnet", "high", 30))

    def test_a_dropped_task_is_recorded_and_never_queued(self):
        goal = self.approved(n=3, keep=["T-01", "T-03"])
        self.assertTrue(gs.read_task(self.root, goal, "T-02")["dropped"])
        self.assertEqual(gs.read_task(self.root, goal, "T-02")["state"], "dropped")
        self.assertEqual(self.state(goal, "T-03"), "queued")
        with self.assertRaises(gs.GoalError):
            self.move(goal, "T-02", "running", "start")

    def test_a_link_in_place_of_a_state_file_is_refused(self):
        goal = self.approved()
        p = self.root / ".umwayi" / "goals" / goal / "T-02.json"
        target = self.root / "elsewhere.json"
        target.write_text(p.read_text())
        p.unlink()
        os.symlink(target, p)
        with self.assertRaises(UmwayiError):
            gs.read_task(self.root, goal, "T-02")
        with self.assertRaises(UmwayiError):
            self.move(goal, "T-02", "running", "start")

    def test_a_folder_where_a_file_should_be_is_refused(self):
        goal = self.approved()
        p = self.root / ".umwayi" / "goals" / goal / "goal.json"
        p.unlink()
        p.mkdir()
        with self.assertRaises(UmwayiError):
            gs.read_goal(self.root, goal)

    def test_a_link_in_place_of_the_goals_folder_is_refused(self):
        (self.root / ".umwayi").mkdir()
        other = self.root / "other"
        other.mkdir()
        os.symlink(other, self.root / ".umwayi" / "goals")
        with self.assertRaises(UmwayiError):
            self.started()
        self.assertEqual(list(other.iterdir()), [])

    def test_size_caps(self):
        goal = self.approved()
        d = self.root / ".umwayi" / "goals" / goal
        (d / "goal.json").write_text(json.dumps({"x": "y" * 9000}))
        with self.assertRaises(UmwayiError):
            gs.read_goal(self.root, goal)
        (d / "T-01.json").write_text(json.dumps({"x": "y" * 70000}))
        with self.assertRaises(UmwayiError):
            gs.read_task(self.root, goal, "T-01")
        self.assertEqual((gs.MAX_GOAL_FILE, gs.MAX_TASK_FILE), (8 * 1024, 64 * 1024))

    def test_a_state_file_that_is_not_the_expected_shape_is_refused(self):
        goal = self.approved()
        d = self.root / ".umwayi" / "goals" / goal
        for bad in ("[]", "null", "{not json", '{"id": "T-02"}', json.dumps({"id": "T-09", "state": "queued"})):
            (d / "T-02.json").write_text(bad)
            with self.assertRaises(UmwayiError, msg=bad):
                gs.read_task(self.root, goal, "T-02")

    def test_ids_are_checked_before_a_path_is_made(self):
        for bad in ("../x", "G-1", "G-0001/../../x", "g-0001", "", "G-0001\n"):
            with self.assertRaises(UmwayiError, msg=repr(bad)):
                gs.goal_dir(self.root, bad)
        goal = self.approved()
        for bad in ("T-1", "T-001", "../T-01", "t-01", ""):
            with self.assertRaises(UmwayiError, msg=repr(bad)):
                gs.read_task(self.root, goal, bad)

    def test_gitignore_lines_are_present(self):
        text = (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn(".umwayi/goals/", text)
        self.assertIn(".umwayi/goal.lock", text)


class LockTests(GoalCase):
    def test_a_second_supervisor_is_refused(self):
        with gs.lock(self.root):
            with self.assertRaises(gs.GoalLockBusy):
                with gs.lock(self.root):
                    pass
            self.assertFalse(gs.lock_free(self.root))
        self.assertTrue(gs.lock_free(self.root))
        with gs.lock(self.root):  # free again after the block
            pass

    def test_the_lock_is_not_the_run_lock(self):
        from umwayi import runlock
        with gs.lock(self.root):
            with runlock.held(self.root):
                pass

    def test_a_link_or_folder_in_place_of_the_lock_is_refused(self):
        (self.root / ".umwayi").mkdir()
        os.symlink(self.root / "x", self.root / ".umwayi" / "goal.lock")
        with self.assertRaises(UmwayiError):
            with gs.lock(self.root):
                pass

    def test_a_busy_lock_message_is_the_locks_sentence(self):
        with gs.lock(self.root):
            try:
                with gs.lock(self.root):
                    pass
            except gs.GoalLockBusy as e:
                self.assertIn("another umwayi goal command", str(e))


class LostSupervisorTests(GoalCase):
    def test_a_running_task_with_the_lock_free_is_found_and_stopped_with_supervisor(self):
        goal = self.approved()
        self.move(goal, "T-01", "running", "start", role="builder", agent="claude-build", cap_uu=30)
        self.assertEqual(gs.find_lost(self.root), [(goal, "T-01")])
        stopped = gs.mark_lost(self.root, when=self.when, now=self.clock())
        self.assertEqual(stopped, [(goal, "T-01")])
        t = gs.read_task(self.root, goal, "T-01")
        self.assertEqual((t["state"], t["reason"]), ("stopped", "supervisor"))
        self.assertEqual(gs.find_lost(self.root), [])

    def test_a_running_task_with_the_lock_held_is_not_lost(self):
        goal = self.approved()
        self.move(goal, "T-01", "running", "start", role="builder", agent="claude-build", cap_uu=30)
        with gs.lock(self.root):
            self.assertEqual(gs.find_lost(self.root), [])

    def test_other_states_are_never_lost(self):
        goal = self.approved()
        self.move(goal, "T-01", "needs owner", "ask")
        self.assertEqual(gs.find_lost(self.root), [])


if __name__ == "__main__":
    unittest.main()
