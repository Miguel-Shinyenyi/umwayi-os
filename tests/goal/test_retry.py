"""W9.14: `umwayi goal retry G T --budget-uu N [--goal-budget-uu M]`, the owner's retry of one task.

A retry is a new task (the next free id) from the packet of a task that failed or was stopped, with a new budget from
the owner (W9.R6.5, W9.R15.7). It needs a terminal, starts nothing, writes one logbook entry, and stands in the place of
the task it replaces in the run order. Every refusal is exit 2 and changes nothing (a byte snapshot). Nothing raises a
budget by itself: only the owner's `--goal-budget-uu` does, and never lowers it.
"""

import json
import os
import subprocess
import sys

from tests.goal import cmdsupport as cs
from tests.goal import runsupport as rs
from tests.goal.test_owner_commands import snapshot
from umwayi import goal as gl
from umwayi import goalpacket as gp
from umwayi import goalrun as gr
from umwayi import goalstate as gs
from umwayi import logbook

FAIL = {"steps": [{"exit": 2}], "spend": 4}


class RetryCase(cs.CmdCase):
    def failed(self, tasks=1):
        goal = self.g_approved(tasks)
        self.assertEqual(self.call("run", goal, scripts=[FAIL]), 2, self.err)
        self.assertEqual(gs.read_task(self.root, goal, "T-01")["state"], "failed")
        return goal

    def good(self, goal, task):
        return [{"steps": rs.builder_steps(goal, task), "spend": 5}, {"steps": rs.tester_steps(), "spend": 2},
                {"steps": rs.check_steps(), "spend": 2}]

    def starts(self, goal):
        """Every helper start of the goal, read from the task event logs (each call makes a new spawn double)."""
        n = 0
        for task in gs.list_tasks(self.root, goal):
            path = gs.events_path(self.root, goal, task)
            if path.exists():
                n += sum(1 for line in path.read_text().splitlines() if '"kind":"started"' in line.replace(" ", ""))
        return n

    def retry_entries(self):
        return [e for e in logbook.read_checked(self.root) if e.source == gs.SOURCE and "added as a retry" in e.added]

    def state(self):
        return snapshot(self.root, str(self.root) + "-worktrees")

    def refused(self, *args, words=None, **kw):
        before = self.state()
        self.err.clear()
        self.assertEqual(self.call("retry", *args, **kw), 2, self.err)
        if words:
            self.assertIn(words, "\n".join(self.err))
        self.assertIn("Nothing changed", "\n".join(self.err))
        self.assertEqual(self.state(), before)


class RetryTests(RetryCase):
    def test_a_failed_task_gets_a_new_task_from_the_same_packet_with_the_owners_budget(self):
        goal = self.failed()
        old = gs.read_task(self.root, goal, "T-01")
        started = self.starts(goal)
        self.assertEqual(self.call("retry", goal, "T-01", 25), 0, self.err)
        new = gs.read_task(self.root, goal, "T-02")
        self.assertEqual((new["state"], new["reason"], new["seq"], new[gs.RETRY_KEY]), ("queued", "approved", 0, "T-01"))
        p, q = gp.packet_from_dict(old["packet"]), gp.packet_from_dict(new["packet"])
        for field in ("goal", "context", "checks", "size", "files", "model", "effort"):
            self.assertEqual(getattr(q, field), getattr(p, field), field)
        self.assertEqual((q.id, q.budget_uu), ("T-02", 25))
        self.assertEqual(q.outcome["status_file"], f"docs-parts/status-log/{goal}-T-02.md")
        self.assertEqual(new["sha256"], q.sha256())
        self.assertEqual(gs.read_task(self.root, goal, "T-01"), old)  # the replaced task keeps its file and spend
        self.assertEqual(self.starts(goal), started)  # nothing was started
        entries = self.retry_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].added, f"Goal {goal} task T-02 added as a retry of task T-01: packet "
                                           f"{q.sha256()[:8]}, budget 25 UU")
        self.assertEqual(gr.goal_status(self.root, goal), "active")
        v = gs.view(self.root)[goal]
        self.assertEqual((v.retries, v.tasks["T-02"].state), ({"T-02": "T-01"}, "queued"))
        self.assertIn("Nothing was started", "\n".join(self.out))

    def test_the_retry_runs_in_its_own_worktree_and_reaches_in_review(self):
        goal = self.failed()
        old_tree = gr.GIT.worktree_path(self.root, goal, "T-01")
        self.assertTrue(os.path.isdir(old_tree))
        self.assertEqual(self.call("retry", goal, "T-01", 25), 0, self.err)
        self.assertEqual(self.call("run", goal, scripts=self.good(goal, "T-02")), 0, self.err)
        t = gs.read_task(self.root, goal, "T-02")
        self.assertEqual((t["state"], t["branch"]), ("in review", gp.branch_name(goal, "T-02")))
        self.assertTrue(os.path.isdir(old_tree))  # the failed task's worktree is left as it was
        self.assertEqual(gs.read_task(self.root, goal, "T-01")["state"], "failed")
        self.assertEqual(gr.goal_status(self.root, goal), "waiting")

    def test_the_retry_takes_the_place_of_the_task_it_replaces_in_the_run_order(self):
        goal = self.failed(tasks=2)
        self.assertEqual(self.call("retry", goal, "T-01", 25), 0, self.err)
        self.assertEqual(gs.read_task(self.root, goal, "T-03")[gs.RETRY_KEY], "T-01")
        tasks = [gs.read_task(self.root, goal, t) for t in gs.list_tasks(self.root, goal)]
        self.assertEqual([t["id"] for t in gs.run_order(tasks)], ["T-01", "T-03", "T-02"])
        self.assertEqual([t["id"] for t in gs.live_tasks(tasks)], ["T-03", "T-02"])
        self.assertEqual(self.call("run", goal, scripts=self.good(goal, "T-03")), 0, self.err)
        self.assertEqual(gs.read_task(self.root, goal, "T-03")["state"], "in review")
        self.assertEqual(gs.read_task(self.root, goal, "T-02")["state"], "queued")  # still waits for T-03's merge
        before = self.starts(goal)
        self.assertGreater(before, 0)
        self.assertEqual(self.call("run", goal), 0, self.err)  # T-03 is not merged: nothing new starts
        self.assertEqual(self.starts(goal), before)

    def test_the_builder_order_check_sees_the_retry_not_the_failed_task(self):
        goal = self.failed(tasks=2)
        self.assertEqual(self.call("retry", goal, "T-01", 25), 0, self.err)
        out = self.run_task(goal, "T-02", [])  # T-02 asked to run before its earlier task (the retry) is merged
        self.assertEqual(out.word, "order")
        self.assertEqual(gs.read_task(self.root, goal, "T-02")["state"], "queued")

    def test_a_stopped_task_can_be_retried(self):
        goal = self.g_approved()
        gs.change_state(self.root, goal, "T-01", "needs owner", "unclear", when=self.when, now=self.clock())
        self.assertEqual(self.call("answer", goal, "T-01", "no"), 0, self.err)
        self.assertEqual(gs.read_task(self.root, goal, "T-01")["state"], "stopped")
        self.assertEqual(self.call("retry", goal, "T-01", 20), 0, self.err)
        self.assertEqual(gs.read_task(self.root, goal, "T-02")["state"], "queued")

    def test_a_retry_of_a_retry_follows_the_first_place(self):
        goal = self.failed(tasks=2)
        self.assertEqual(self.call("retry", goal, "T-01", 20), 0, self.err)
        self.assertEqual(self.call("run", goal, scripts=[FAIL]), 2, self.err)
        self.assertEqual(gs.read_task(self.root, goal, "T-03")["state"], "failed")
        self.assertEqual(self.call("retry", goal, "T-03", 20), 0, self.err)
        tasks = [gs.read_task(self.root, goal, t) for t in gs.list_tasks(self.root, goal)]
        self.assertEqual([t["id"] for t in gs.live_tasks(tasks)], ["T-04", "T-02"])

    def test_status_and_report_name_the_retry(self):
        goal = self.failed()
        self.assertEqual(self.call("retry", goal, "T-01", 25), 0, self.err)
        ctx = gl.Ctx(self.root, int(self.clock()), self.out.append, self.err.append, tty=lambda: False, env_kw={})
        status = "\n".join(gl.status_lines(ctx, goal))
        self.assertIn(f"Goal {goal}  active  (0 of 1 tasks merged, 0 in review)", status)
        self.assertIn("  Task T-01  failed (builder), retried as T-02", status)
        report = gl.report_lines(ctx, goal)
        self.assertIn("- Retried as: T-02", report)
        self.assertIn("- A retry of: T-01", report)


class RetryBudgetTests(RetryCase):
    def test_a_budget_the_goal_cannot_cover_is_refused_and_the_owner_can_raise_the_goal_budget(self):
        goal = self.failed()  # goal 100, plan 20, T-01 spent 4
        self.refused(goal, "T-01", 90, words="does not cover 114 UU")
        self.refused(goal, "T-01", 90, goal_budget_uu=113, words="must cover 114 UU")
        self.refused(goal, "T-01", 90, goal_budget_uu=99, words="can only raise the goal budget of 100 UU")
        self.assertEqual(self.call("retry", goal, "T-01", 90, goal_budget_uu=114), 0, self.err)
        self.assertEqual(gs.read_goal(self.root, goal)["goal_budget_uu"], 114)
        self.assertTrue(self.retry_entries()[0].added.endswith(", budget 90 UU, goal budget 114 UU"))
        self.assertEqual(gs.view(self.root)[goal].goal_budget, 114)
        g = gs.read_goal(self.root, goal)
        (gs.goal_dir(self.root, goal) / "goal.json").write_text(json.dumps(dict(g, goal_budget_uu=100)))
        gs.repair(self.root, when=self.when, now=self.clock())  # the logbook wins: the raise is in the entry
        self.assertEqual(gs.read_goal(self.root, goal)["goal_budget_uu"], 114)

    def test_the_other_unfinished_tasks_budgets_count(self):
        goal = self.failed(tasks=2)  # T-02 queued with 30 UU left of its budget
        self.refused(goal, "T-01", 47, words="does not cover 101 UU")
        self.assertEqual(self.call("retry", goal, "T-01", 46), 0, self.err)

    def test_the_cap_of_the_retry_run_is_its_own_budget(self):
        goal = self.failed()
        self.assertEqual(self.call("retry", goal, "T-01", 7), 0, self.err)
        self.call("run", goal, scripts=self.good(goal, "T-02"))
        started = [json.loads(line) for line in gs.events_path(self.root, goal, "T-02").read_text().splitlines()
                   if '"started"' in line]
        self.assertLessEqual(max(s["data"]["cap_uu"] for s in started), 7)

    def test_a_budget_outside_one_to_per_day_is_refused(self):
        goal = self.failed()
        self.refused(goal, "T-01", 501, words="from 1 UU to limits.per_day")


class RetryRefusalTests(RetryCase):
    def test_without_a_terminal_nothing_changes(self):
        goal = self.failed()
        before = self.state()
        self.terminal = False
        self.assertEqual(self.call("retry", goal, "T-01", 25), 2)
        self.assertIn("needs a terminal", "\n".join(self.err))
        self.assertEqual(self.state(), before)

    def test_only_a_failed_or_stopped_task(self):
        goal = self.g_approved()
        self.refused(goal, "T-01", 25, words="only a task that failed or was stopped can be retried")
        self.refused(goal, "T-07", 25, words="has no task T-07")

    def test_a_task_is_retried_once(self):
        goal = self.failed()
        self.assertEqual(self.call("retry", goal, "T-01", 25), 0, self.err)
        self.refused(goal, "T-01", 25, words="already retried as T-02")

    def test_a_stopped_goal_is_not_retried(self):
        goal = self.failed()
        self.assertEqual(self.call("stop", goal), 0, self.err)
        self.refused(goal, "T-01", 25, words="start a new goal")

    def test_a_goal_that_is_not_approved_is_not_retried(self):
        goal = self.g_start()
        self.refused(goal, "T-01", 25)

    def test_usage_errors_are_64_and_never_1(self):
        for args in (["retry", "G-0001", "T-01"], ["retry", "G-1", "T-01", "--budget-uu", "5"],
                     ["retry", "G-0001", "X-01", "--budget-uu", "5"], ["retry", "G-0001", "T-01", "--budget-uu", "x"]):
            with self.subTest(args=args):
                r = self.umwayi(*args)
                self.assertEqual(r.returncode, 64, r.stderr)

    def test_a_real_process_without_a_terminal_is_2(self):
        goal = self.failed()
        r = self.umwayi("retry", goal, "T-01", "--budget-uu", "25")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertNotIn("T-02.json", os.listdir(gs.goal_dir(self.root, goal)))


class RetryRecordTests(RetryCase):
    def test_a_lost_task_file_is_rebuilt_from_the_entry(self):
        goal = self.failed()
        self.assertEqual(self.call("retry", goal, "T-01", 25), 0, self.err)
        path = gs.goal_dir(self.root, goal) / "T-02.json"
        want = path.read_bytes()
        path.unlink()  # the write after the entry failed
        self.assertIn(f"{goal} T-02 retry file", gs.repair(self.root, when=self.when, now=self.clock()))
        self.assertEqual(path.read_bytes(), want)

    def test_a_lost_file_whose_packet_no_longer_matches_is_not_rebuilt(self):
        goal = self.failed()
        self.assertEqual(self.call("retry", goal, "T-01", 25), 0, self.err)
        (gs.goal_dir(self.root, goal) / "T-02.json").unlink()
        old = gs.read_task(self.root, goal, "T-01")
        old["packet"]["checks"] = ["A check that someone changed by hand afterwards, pass or fail."]
        (gs.goal_dir(self.root, goal) / "T-01.json").write_text(json.dumps(old))
        gs.repair(self.root, when=self.when, now=self.clock())
        self.assertFalse((gs.goal_dir(self.root, goal) / "T-02.json").exists())

    def test_a_failed_record_write_changes_nothing_and_is_2(self):
        goal = self.failed()
        before = self.state()
        from unittest import mock
        with mock.patch.object(gs, "_append_entry", side_effect=OSError("planted")):
            self.assertEqual(self.call("retry", goal, "T-01", 25), 2)
        self.assertEqual(self.state(), before)

    def test_a_retry_entry_for_a_task_that_did_not_fail_is_not_a_fixed_shape_sequence(self):
        goal = self.g_approved()
        e = gs.retry_entry(self.when, goal, "T-02", "T-01", "0" * 8, 5)
        entries = list(logbook.read_checked(self.root)) + [e]
        with self.assertRaises(gs.EntryError):
            gs.parse_entries(entries)

    def test_a_second_retry_entry_for_the_same_task_is_refused_by_the_reader(self):
        goal = self.failed()
        self.assertEqual(self.call("retry", goal, "T-01", 25), 0, self.err)
        e = gs.retry_entry(self.when, goal, "T-03", "T-01", "0" * 8, 5)
        with self.assertRaises(gs.EntryError):
            gs.parse_entries(list(logbook.read_checked(self.root)) + [e])

    def test_a_task_file_with_a_bad_retry_of_does_not_read(self):
        goal = self.failed()
        self.assertEqual(self.call("retry", goal, "T-01", 25), 0, self.err)
        path = gs.goal_dir(self.root, goal) / "T-02.json"
        for bad in ("T-02", "T-09", "x", 1):
            with self.subTest(bad=bad):
                obj = json.loads(path.read_text())
                obj[gs.RETRY_KEY] = bad
                path.write_text(json.dumps(obj))
                with self.assertRaises(gs.GoalError):
                    gs.read_task(self.root, goal, "T-02")


if __name__ == "__main__":
    import unittest
    unittest.main()
