"""W9.4 and W9.5 / W9.R9 (pitfall 1): an approval that waits silently.

The pure part is `goalwatch.Approval`, `expired`, `effective_now` and the countdown text. The state part is
`goalstate` (the queue row, the logbook entries, `deny_expired`, the refusals). The status line and the terminal
line (W9.R9.3 c and d) belong to the commands of W9.8 and are not tested here.
"""

import unittest

from tests.goal import gen
from tests.goal.goalsupport import GoalCase
from umwayi import goalstate as gs
from umwayi import goalwatch as gw
from umwayi import taskqueue
from umwayi.errors import UmwayiError

H = 3600


def appr(asked=1000, deadline=1000 + 24 * H, kind="needs-owner", goal="G-0007", task="T-03"):
    return gw.Approval(kind=kind, goal=goal, task=task, asked=asked, deadline=deadline)


class ApprovalRecordTests(unittest.TestCase):
    def test_a_record_without_a_deadline_cannot_be_made(self):
        for bad in (None, 0, -5, "tomorrow", 1000, 999, float("nan"), float("inf"), True):
            with self.assertRaises(ValueError, msg=repr(bad)):
                gw.Approval(kind="needs-owner", goal="G-0007", task="T-03", asked=1000, deadline=bad)
        with self.assertRaises(TypeError):
            gw.Approval(kind="needs-owner", goal="G-0007", task="T-03", asked=1000)

    def test_the_default_answer_is_always_no_and_cannot_be_set(self):
        self.assertEqual(appr().default, "no")
        with self.assertRaises(TypeError):
            gw.Approval(kind="plan", goal="G-0007", task="", asked=1, deadline=2, default="yes")
        with self.assertRaises(Exception):
            appr().default = "yes"

    def test_kinds_and_ids(self):
        gw.Approval(kind="plan", goal="G-0007", task="", asked=1, deadline=2)
        for kw in (dict(kind="other"), dict(goal="g-7"), dict(task="T-3"), dict(task="")):
            with self.assertRaises(ValueError, msg=str(kw)):
                appr(**kw)
        with self.assertRaises(ValueError):
            gw.Approval(kind="plan", goal="G-0007", task="T-01", asked=1, deadline=2)

    def test_deadlines_are_168_hours_for_a_plan_and_24_for_a_task(self):
        self.assertEqual(gw.deadline_for("plan", 1000), 1000 + 168 * H)
        self.assertEqual(gw.deadline_for("needs-owner", 1000), 1000 + 24 * H)
        self.assertEqual(gw.deadline_for("needs-owner", 1000, hours=1), 1000 + H)
        for bad in (0, 169, -1, 1.5, True, "5"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                gw.deadline_for("plan", 1000, hours=bad)

    def test_an_answer_is_late_at_or_after_the_deadline(self):
        a = appr()
        self.assertEqual(gw.with_answer(a, "yes", a.deadline - 1).answer, "yes")
        for t in (a.deadline, a.deadline + 1, a.deadline + 10 ** 6):
            with self.assertRaises(ValueError):
                gw.with_answer(a, "yes", t)
        with self.assertRaises(ValueError):
            gw.with_answer(a, "maybe", a.asked)

    def test_outcome_never_yes_without_an_answer(self):
        a = appr()
        self.assertEqual(gw.outcome(a, a.deadline - 1), "open")
        self.assertEqual(gw.outcome(a, a.deadline), "no")
        self.assertEqual(gw.outcome(gw.with_answer(a, "yes", a.asked + 5), a.deadline + 99), "yes")
        self.assertEqual(gw.outcome(gw.with_answer(a, "no", a.asked + 5), a.asked + 6), "no")

    def test_expired_lists_those_at_or_past_the_deadline_with_no_answer(self):
        a, b, c = appr(deadline=2000), appr(deadline=3000, task="T-04"), gw.with_answer(appr(deadline=2000, task="T-05"), "yes", 1500)
        self.assertEqual(gw.expired([a, b, c], 1999), [])
        self.assertEqual(gw.expired([a, b, c], 2000), [a])
        self.assertEqual(gw.expired([a, b, c], 5000), [a, b])
        self.assertEqual(gw.expired([], 5000), [])

    def test_expired_ignores_garbage_and_a_bad_now(self):
        self.assertEqual(gw.expired([None, 5, "x"], 5000), [])
        self.assertEqual(gw.expired([appr()], None), [])
        self.assertEqual(gw.expired(None, 5000), [])

    def test_a_clock_set_back_never_revives_an_approval(self):
        a = appr(deadline=2000)
        seen_newest = 2500  # the newest time any logbook entry or earlier command saw
        now = gw.effective_now(1000, seen_newest)
        self.assertEqual(now, 2500)
        self.assertEqual(gw.expired([a], now), [a])
        self.assertEqual(gw.effective_now(None, 5), 5)
        self.assertEqual(gw.effective_now(None, None), 0)
        self.assertEqual(gw.effective_now(7, "x"), 7)

    def test_texts(self):
        self.assertEqual(gw.ago(5), "5 s ago")
        self.assertEqual(gw.ago(240), "4 min ago")
        self.assertEqual(gw.ago(3 * H + 100), "3 h ago")
        self.assertEqual(gw.ago(-5), "age unknown")
        self.assertEqual(gw.ago(None), "age unknown")
        self.assertEqual(gw.countdown(21 * H + 5), "denied in 21 h")
        self.assertEqual(gw.countdown(5 * 60), "denied in 5 min")
        self.assertEqual(gw.countdown(30), "denied in 30 s")
        self.assertEqual(gw.countdown(0), "denied now")
        self.assertEqual(gw.countdown(-9), "denied now")
        a = appr(asked=0, deadline=24 * H)
        self.assertEqual(gw.approval_sentence(a, 3 * H), "Asked 3 h ago, denied in 21 h.")

    def test_property_an_answer_after_the_deadline_is_never_accepted_and_silence_is_never_yes(self):
        def make(g):
            asked = g.between(0, 10 ** 6)
            deadline = asked + g.between(1, 10 ** 5)
            return asked, deadline, g.between(asked, deadline + 10 ** 5), g.between(0, deadline + 2 * 10 ** 5), g.chance(0.5)

        def check(case):
            asked, deadline, answer_at, now, answers = case
            a = gw.Approval(kind="needs-owner", goal="G-0001", task="T-01", asked=asked, deadline=deadline)
            if answers:
                try:
                    a2 = gw.with_answer(a, "yes", answer_at)
                except ValueError:
                    if answer_at < deadline:
                        return False
                    a2 = a
                else:
                    if answer_at >= deadline:
                        return False
            else:
                a2 = a
            res = gw.outcome(a2, now)
            if a2.answer is None and res == "yes":
                return False
            if a2.answer is None and now >= deadline and res != "no":
                return False
            return True

        gen.run_property(self, make, check, cases=1250, seeds=gen.SEEDS)


class ApprovalStateTests(GoalCase):
    """The queue row, the logbook entries and the deadline, enforced when a command next runs."""

    def needs_owner_task(self, wait_hours=24):
        goal = self.approved(wait_hours=wait_hours)
        self.move(goal, "T-01", "needs owner", "unclear")
        return goal

    def open_rows(self):
        return [r for r in taskqueue.list_rows(self.root) if r.status == "open"]

    def added_lines(self):
        return [e.added for e in self.entries() if e.source == gs.SOURCE]

    def test_an_approval_is_visible_in_the_logbook_and_the_queue_before_the_state_changes(self):
        goal = self.approved()
        self.assertEqual(len(self.open_rows()), 0)
        self.move(goal, "T-01", "needs owner", "unclear")
        rows = self.open_rows()
        self.assertEqual(len(rows), 1)
        self.assertIn("G-0001", rows[0].title)
        self.assertIn("T-01", rows[0].title)
        lines = self.added_lines()
        req = [i for i, a in enumerate(lines) if a.startswith("Approval requested: task T-01 of goal G-0001")]
        st = [i for i, a in enumerate(lines) if a.startswith("Goal G-0001 task T-01: queued to needs owner")]
        self.assertEqual((len(req), len(st)), (1, 1))
        self.assertLess(req[0], st[0])  # the approval is written before the change, not after
        self.assertIn("deadline 2026-11-07 21:20 UTC", lines[req[0]])  # 24 hours after the fake clock
        self.assertEqual(self.state(goal, "T-01"), "needs owner")

    def test_a_task_in_needs_owner_always_has_an_open_row_and_a_row_that_cannot_be_added_blocks_the_change(self):
        from unittest import mock
        goal = self.approved()
        with mock.patch.object(gs, "_queue_row", side_effect=UmwayiError("queue.md is broken")):
            with self.assertRaises(gs.RecordFailed):
                self.move(goal, "T-01", "needs owner", "ask")
        self.assertEqual(self.state(goal, "T-01"), "queued")
        self.assertEqual(self.open_rows(), [])

    def test_the_plan_waits_168_hours_and_is_visible_too(self):
        goal = self.planned()
        rows = self.open_rows()
        self.assertEqual(len(rows), 1)
        self.assertIn(f"Goal {goal} has a plan that waits for you", rows[0].title)
        req = [a for a in self.added_lines() if a.startswith(f"Approval requested: plan of goal {goal}")]
        self.assertEqual(len(req), 1)
        self.assertIn("deadline 2026-11-13 21:20 UTC", req[0])

    def test_at_the_deadline_minus_a_second_it_is_open_and_yes_works(self):
        goal = self.needs_owner_task()
        self.clock.advance(24 * H - 1)
        self.assertEqual(gs.deny_expired(self.root, when=self.when, now=self.clock()), [])
        gs.answer_approval(self.root, goal, "T-01", "yes", when=self.when, now=self.clock())
        self.assertEqual(self.state(goal, "T-01"), "queued")
        self.assertEqual(self.open_rows(), [])

    def test_at_the_deadline_it_is_no_with_no_process_running_in_between(self):
        goal = self.needs_owner_task()
        self.clock.advance(24 * H)
        denied = gs.deny_expired(self.root, when=self.when, now=self.clock())
        self.assertEqual(denied, [(goal, "T-01")])
        t = gs.read_task(self.root, goal, "T-01")
        self.assertEqual((t["state"], t["reason"]), ("stopped", "unanswered"))
        self.assertEqual(self.open_rows(), [])
        row = [r for r in taskqueue.list_rows(self.root) if "T-01" in r.title][0]
        self.assertEqual((row.status, row.answer), ("closed", "No: timed out"))
        denials = [a for a in self.added_lines() if a.startswith("Approval denied: task T-01 of goal")]
        self.assertEqual(len(denials), 1)
        self.assertIn("(timed out), deadline 2026-11-07 21:20 UTC", denials[0])
        self.assertEqual(gs.deny_expired(self.root, when=self.when, now=self.clock() + 99999), [])  # logged once
        self.assertEqual(len([a for a in self.added_lines() if a.startswith("Approval denied")]), 1)

    def test_answer_after_the_deadline_is_refused_exit_2_and_the_denial_is_logged_once(self):
        goal = self.needs_owner_task()
        self.clock.advance(24 * H + 86400)
        for _ in range(2):
            with self.assertRaises(gs.GoalError) as cm:
                gs.answer_approval(self.root, goal, "T-01", "yes", when=self.when, now=self.clock())
            self.assertIn("this approval timed out and was denied", str(cm.exception))
        self.assertEqual(self.state(goal, "T-01"), "stopped")
        self.assertEqual(len([a for a in self.added_lines() if a.startswith("Approval denied")]), 1)

    def test_approve_after_the_deadline_is_refused_and_the_plan_is_denied(self):
        goal = self.planned()
        self.clock.advance(168 * H)
        with self.assertRaises(gs.GoalError) as cm:
            gs.approve_plan(self.root, goal, builder="claude-build", tester="kiro-test", guide="claude-guide", model="sonnet",
                            effort="high", task_budget_uu=30, goal_budget_uu=100, per_day=500, when=self.when, now=self.clock())
        self.assertIn("timed out", str(cm.exception))
        self.assertEqual(self.open_rows(), [])
        self.assertTrue(gs.read_goal(self.root, goal)["stopped"] == "unanswered")
        self.assertEqual(len([a for a in self.added_lines() if a.startswith("Approval denied: plan of goal")]), 1)

    def test_enforcement_does_not_need_the_run_command(self):
        # deny_expired is the first thing every writing command calls; here it is called with nothing else running
        goal = self.planned(plan_hours=1)
        self.clock.advance(H)
        self.assertEqual(gs.deny_expired(self.root, when=self.when, now=self.clock()), [(goal, "")])
        self.assertEqual(gs.read_goal(self.root, goal)["stopped"], "unanswered")

    def test_a_clock_set_back_does_not_revive_a_denied_approval(self):
        goal = self.needs_owner_task()
        self.clock.advance(24 * H)
        gs.deny_expired(self.root, when=self.when, now=self.clock())
        with self.assertRaises(gs.GoalError):
            gs.answer_approval(self.root, goal, "T-01", "yes", when=self.when, now=self.clock() - 10 * H)
        self.assertEqual(self.state(goal, "T-01"), "stopped")

    def test_answer_no_stops_the_task_with_reason_owner(self):
        goal = self.needs_owner_task()
        gs.answer_approval(self.root, goal, "T-01", "no", when=self.when, now=self.clock())
        t = gs.read_task(self.root, goal, "T-01")
        self.assertEqual((t["state"], t["reason"]), ("stopped", "owner"))
        self.assertEqual([r.status for r in taskqueue.list_rows(self.root) if "T-01" in r.title], ["closed"])

    def test_answer_rules(self):
        goal = self.approved()
        with self.assertRaises(gs.GoalError):  # the task does not wait for the owner
            gs.answer_approval(self.root, goal, "T-01", "yes", when=self.when, now=self.clock())
        self.move(goal, "T-01", "needs owner", "ask")
        for bad in ("maybe", "", None, "YES", True):
            with self.assertRaises(gs.GoalError):
                gs.answer_approval(self.root, goal, "T-01", bad, when=self.when, now=self.clock())
        self.assertEqual(self.state(goal, "T-01"), "needs owner")


if __name__ == "__main__":
    unittest.main()
