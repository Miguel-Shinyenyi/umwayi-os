"""W9.5 / W9.R18: the `umwayi goal` logbook entries have fixed shapes, parsed strictly.

Tests first. The module under test is umwayi/goalstate.py (the builders and the strict parser).
"""

import itertools
import unittest

from tests.goal.goalsupport import SENTINEL, GoalCase, plan_bytes
from umwayi import goalpacket as gp
from umwayi import goalstate as gs
from umwayi import logbook

D = "2026-11-13"
ROLES = (None, "guide", "builder", "tester", "check")


def transitions():
    for old, news in gp.TRANSITIONS.items():
        for new in news:
            yield old, new


class ShapeTests(unittest.TestCase):
    def test_every_transition_reason_and_role_round_trips(self):
        n = 0
        for (old, new), role in itertools.product(transitions(), ROLES):
            for reason in gp.REASONS[new]:
                kw = dict(role=role, agent="claude-build" if role else None)
                e = gs.state_entry(D, "G-0007", "T-02", old, new, reason, **kw)
                self.assertEqual(e.source, "umwayi goal")
                rec = gs.parse_entry(e)
                self.assertEqual((rec.kind, rec.goal, rec.task, rec.old, rec.new, rec.reason, rec.role, rec.agent),
                                 ("state", "G-0007", "T-02", old, new, reason, role, kw["agent"]))
                n += 1
        self.assertGreater(n, 150)

    def test_the_optional_parts_round_trip(self):
        e = gs.state_entry(D, "G-0007", "T-02", "running", "in review", "checked", branch="umwayi/g-0007-t-02", tip="9f1c2e0a",
                           facts=[("scope", {"n": 3}), ("tester", {"name": "kiro-test", "p": 2, "m": 2}),
                                  ("guide", {"name": "claude-guide", "word": "accept"}), ("spent", {"a": 27, "b": 40})])
        rec = gs.parse_entry(e)
        self.assertEqual((rec.branch, rec.tip), ("umwayi/g-0007-t-02", "9f1c2e0a"))
        self.assertEqual([f[0] for f in rec.facts], ["scope", "tester", "guide", "spent"])
        e = gs.state_entry(D, "G-0007", "T-02", "queued", "running", "start", role="builder", agent="claude-build", cap_uu=30,
                           base="9f1c2e0a")
        rec = gs.parse_entry(e)
        self.assertEqual((rec.cap_uu, rec.base), (30, "9f1c2e0a"))
        e = gs.state_entry(D, "G-0007", "T-02", "in review", "merged", "declared", commit="a" * 40)
        self.assertEqual(gs.parse_entry(e).commit, "a" * 40)

    def test_the_other_shapes_round_trip(self):
        cases = [
            (gs.started_entry(D, "G-0007", 212, "ab12cd34", "claude-guide", 30), "started"),
            (gs.planned_entry(D, "G-0007", "claude-guide", 5, 270, 212, "ab12cd34"), "planned"),
            (gs.plan_refused_entry(D, "G-0007", "claude-guide", "field"), "plan_refused"),
            (gs.plan_approved_entry(D, "G-0007", ["T-01", "T-02"], ["T-03"], "claude-build", "kiro-test", "claude-guide", 100),
             "plan_approved"),
            (gs.plan_approved_entry(D, "G-0007", ["T-01"], [], "claude-build", "kiro-test", "claude-guide", 100), "plan_approved"),
            (gs.approval_requested_entry(D, "G-0007", "T-03", "unclear", "2026-11-13 14:00"), "approval_requested"),
            (gs.approval_requested_entry(D, "G-0007", "", None, "2026-11-13 14:00"), "approval_requested"),
            (gs.approval_answered_entry(D, "G-0007", "T-03", "yes"), "approval_answered"),
            (gs.approval_answered_entry(D, "G-0007", "", "no"), "approval_answered"),
            (gs.approval_denied_entry(D, "G-0007", "T-03", "2026-11-13 14:00"), "approval_denied"),
            (gs.approval_denied_entry(D, "G-0007", "", "2026-11-13 14:00"), "approval_denied"),
            (gs.goal_stopped_entry(D, "G-0007", "kill"), "goal_stopped"),
            (gs.worktree_entry(D, "G-0007", "T-02", "made", base="9f1c2e0a"), "worktree"),
            (gs.worktree_entry(D, "G-0007", "T-01", "removed", how="observed"), "worktree"),
            (gs.worktree_entry(D, "G-0007", "", "made", base="9f1c2e0a"), "worktree"),
            (gs.worktree_entry(D, "G-0007", "", "removed"), "worktree"),
            (gs.docs_entry(D, 3, 2), "docs_built"),
        ]
        for entry, kind in cases:
            self.assertEqual(gs.parse_entry(entry).kind, kind, entry.added)
            self.assertEqual(entry.source, "umwayi goal")

    def test_builders_refuse_values_outside_their_patterns(self):
        with self.assertRaises(ValueError):
            gs.state_entry(D, "G-7", "T-02", "queued", "running", "start")
        with self.assertRaises(ValueError):
            gs.state_entry(D, "G-0007", "T-02", "queued", "running", "bogus")
        with self.assertRaises(ValueError):
            gs.state_entry(D, "G-0007", "T-02", "queued", "merged", "observed")
        with self.assertRaises(ValueError):
            gs.state_entry(D, "G-0007", "T-02", "queued", "running", "start", agent="Bad Name", role="builder")
        with self.assertRaises(ValueError):
            gs.state_entry(D, "G-0007", "T-02", "queued", "running", "start", branch="main\nrm -rf")
        with self.assertRaises(ValueError):
            gs.state_entry(D, "G-0007", "T-02", "queued", "running", "start", facts=[("no_such_fact", {})])
        with self.assertRaises(ValueError):
            gs.started_entry(D, "G-0007", 212, "NOTHEX", "claude-guide", 30)

    def test_an_entry_that_is_not_a_shape_is_refused(self):
        good = gs.state_entry(D, "G-0007", "T-02", "queued", "running", "start")
        for added in ("Goal G-0007 did something", "", good.added + " extra", good.added.replace("start", "bogus"),
                      "Goal G-0007 task T-02: queued to running (reason start)\nmore", "Goal g-0007 task T-02: queued to running (reason start)"):
            bad = logbook.Entry(D, "umwayi goal", added, good.checked, good.not_done)
            with self.assertRaises(gs.EntryError, msg=repr(added)):
                gs.parse_entry(bad)
        for checked in ("", "Free text the helper wrote.", good.checked + " Extra sentence."):
            with self.assertRaises(gs.EntryError, msg=repr(checked)):
                gs.parse_entry(logbook.Entry(D, "umwayi goal", good.added, checked, good.not_done))
        with self.assertRaises(gs.EntryError):
            gs.parse_entry(logbook.Entry(D, "umwayi goal", good.added, good.checked, "Anything at all."))

    def test_error_text_never_quotes_the_entry(self):
        bad = logbook.Entry(D, "umwayi goal", "SENTINEL-SECRET nonsense", "c", "n")
        try:
            gs.parse_entry(bad)
        except gs.EntryError as e:
            self.assertNotIn("SENTINEL", str(e))


def raw_state(goal, task, old, new, reason):
    """An entry in the state shape that the builder would refuse to make, as a hand editor could write it."""
    return logbook.Entry(D, "umwayi goal", f"Goal {goal} task {task}: {old} to {new} (reason {reason})",
                         "Nothing else was checked.", "The goal text, the prompt and the helper's output were not recorded.")


class SequenceTests(unittest.TestCase):
    def good_entries(self):
        return [
            gs.started_entry(D, "G-0001", 50, "ab12cd34", "claude-guide", 20),                      # 0
            gs.planned_entry(D, "G-0001", "claude-guide", 2, 80, 50, "ab12cd34"),                   # 1
            gs.approval_requested_entry(D, "G-0001", "", None, "2026-11-20 21:20"),                 # 2
            gs.approval_answered_entry(D, "G-0001", "", "yes"),                                     # 3
            gs.plan_approved_entry(D, "G-0001", ["T-01", "T-02"], [], "claude-build", "kiro-test", "claude-guide", 100),  # 4
            gs.state_entry(D, "G-0001", "T-01", "queued", "running", "start", role="builder", agent="claude-build"),     # 5
            gs.state_entry(D, "G-0001", "T-01", "running", "in review", "checked"),                  # 6
        ]

    def test_a_good_sequence_is_derived(self):
        v = gs.parse_entries(self.good_entries())["G-0001"]
        self.assertEqual((v.tasks["T-01"].state, v.tasks["T-02"].state), ("in review", "queued"))
        self.assertEqual(v.tasks["T-01"].seq, 2)
        self.assertEqual((v.builder, v.tester, v.guide), ("claude-build", "kiro-test", "claude-guide"))

    def test_entries_of_other_sources_are_ignored(self):
        other = logbook.Entry(D, "umwayi queue add", "Q-0001 added", "c", "n")
        self.assertEqual(len(gs.parse_entries([other] + self.good_entries())), 1)

    def test_a_sequence_that_skips_a_state_is_refused(self):
        e = self.good_entries()[:5] + [raw_state("G-0001", "T-01", "queued", "in review", "checked")]
        with self.assertRaises(gs.EntryError):
            gs.parse_entries(e)

    def test_old_state_must_be_the_current_state(self):
        e = self.good_entries()[:6]
        e.append(gs.state_entry(D, "G-0001", "T-01", "queued", "running", "start"))  # it is already running
        with self.assertRaises(gs.EntryError):
            gs.parse_entries(e)

    def test_a_state_entry_before_the_goal_or_for_an_unknown_task_is_refused(self):
        with self.assertRaises(gs.EntryError):
            gs.parse_entries(self.good_entries()[4:])
        e = self.good_entries()[:5] + [gs.state_entry(D, "G-0001", "T-05", "queued", "running", "start")]
        with self.assertRaises(gs.EntryError):
            gs.parse_entries(e)

    def test_a_dropped_task_has_no_state_entries(self):
        e = self.good_entries()[:4] + [gs.plan_approved_entry(D, "G-0001", ["T-01"], ["T-02"], "claude-build", "kiro-test",
                                                              "claude-guide", 100)]
        v = gs.parse_entries(e)["G-0001"]
        self.assertEqual(list(v.tasks), ["T-01"])
        e.append(gs.state_entry(D, "G-0001", "T-02", "queued", "running", "start"))
        with self.assertRaises(gs.EntryError):
            gs.parse_entries(e)

    def test_nothing_comes_out_of_a_terminal_state(self):
        e = self.good_entries()[:6] + [gs.state_entry(D, "G-0001", "T-01", "running", "failed", "tests"),
                                       raw_state("G-0001", "T-01", "failed", "queued", "answered")]
        with self.assertRaises(gs.EntryError):
            gs.parse_entries(e)

    def test_a_goal_planned_twice_or_approved_twice_is_refused(self):
        e = self.good_entries()
        with self.assertRaises(gs.EntryError):
            gs.parse_entries(e[:2] + [e[1]])
        with self.assertRaises(gs.EntryError):
            gs.parse_entries(e[:5] + [e[4]])

    def test_a_task_cannot_run_before_the_plan_is_approved(self):
        e = self.good_entries()[:2] + [gs.state_entry(D, "G-0001", "T-01", "queued", "running", "start")]
        with self.assertRaises(gs.EntryError):
            gs.parse_entries(e)

    def test_an_answer_with_no_request_is_refused_and_a_request_is_closed_by_one_answer(self):
        e = self.good_entries()[:2]
        with self.assertRaises(gs.EntryError):
            gs.parse_entries(e + [gs.approval_answered_entry(D, "G-0001", "", "yes")])
        req = gs.approval_requested_entry(D, "G-0001", "", None, "2026-11-13 14:00")
        v = gs.parse_entries(e + [req])["G-0001"]
        self.assertEqual(v.plan_deadline, "2026-11-13 14:00")
        v = gs.parse_entries(e + [req, gs.approval_denied_entry(D, "G-0001", "", "2026-11-13 14:00")])["G-0001"]
        self.assertIsNone(v.plan_deadline)
        with self.assertRaises(gs.EntryError):
            gs.parse_entries(e + [req, gs.approval_denied_entry(D, "G-0001", "", "2026-11-13 14:00"),
                                  gs.approval_answered_entry(D, "G-0001", "", "yes")])


class LogbookTests(GoalCase):
    def test_no_goal_text_or_packet_text_is_in_the_logbook(self):
        text = f"{SENTINEL} and more words to make a goal."
        goal = self.started(text=text)
        from umwayi import goalpacket
        data = plan_bytes(2).replace(b"Do the numbered piece of work number 1 now.", SENTINEL.encode() + b" in a packet goal")
        gs.record_plan(self.root, goal, goalpacket.parse_plan(data), "claude-guide", when=self.when, now=self.clock())
        gs.approve_plan(self.root, goal, builder="claude-build", tester="kiro-test", guide="claude-guide", model="sonnet",
                        effort="high", task_budget_uu=30, goal_budget_uu=100, per_day=500, when=self.when, now=self.clock())
        self.move(goal, "T-01", "running", "start", role="builder", agent="claude-build")
        self.move(goal, "T-01", "failed", "tests")
        self.assertNotIn("SENTINEL", self.logbook_text())
        self.assertIn(SENTINEL, (self.root / ".umwayi" / "goals" / goal / "goal.json").read_text())  # the owner's own file

    def test_the_real_logbook_parses_and_matches_the_files(self):
        goal = self.approved()
        self.move(goal, "T-01", "running", "start", role="builder", agent="claude-build", cap_uu=30)
        view = gs.view(self.root)[goal]
        self.assertEqual(view.tasks["T-01"].state, "running")
        self.assertEqual(view.tasks["T-01"].state, gs.read_task(self.root, goal, "T-01")["state"])

    def test_logbook_verify_is_ok_after_a_fake_goal_with_every_kind_of_end(self):
        logbook.append(self.root, logbook.Entry(self.when, "test", "Chain start", "Checked.", "Nothing."))
        logbook.seal(self.root, self.when, "test", start_chain=True)
        ends = []
        for end in ("merged", "failed", "stopped_owner", "stopped_kill", "stopped_unanswered", "in review", "needs owner",
                    "stopped_goal"):
            goal = self.approved(n=1)
            ends.append(goal)
            if end == "stopped_goal":
                gs.stop_goal(self.root, goal, "owner", when=self.when, now=self.clock())
                continue
            self.move(goal, "T-01", "running", "start", role="builder", agent="claude-build", cap_uu=30)
            if end == "merged":
                self.move(goal, "T-01", "in review", "checked", branch="umwayi/g-0001-t-01", tip="9f1c2e0a")
                self.move(goal, "T-01", "merged", "observed")
            elif end == "failed":
                self.move(goal, "T-01", "failed", "stalled")
            elif end == "stopped_owner":
                self.move(goal, "T-01", "stopped", "owner")
            elif end == "stopped_kill":
                self.move(goal, "T-01", "stopped", "kill")
            elif end == "stopped_unanswered":
                self.move(goal, "T-01", "needs owner", "unclear")
                self.clock.advance(25 * 3600)
                gs.deny_expired(self.root, when=self.when, now=self.clock())
            elif end == "in review":
                self.move(goal, "T-01", "in review", "checked", branch="umwayi/g-0001-t-01", tip="9f1c2e0a")
            elif end == "needs owner":
                self.move(goal, "T-01", "needs owner", "ask")
        report = logbook.verify(self.root)
        self.assertEqual(report.problems, [])
        self.assertTrue(report.chain_note)
        views = gs.view(self.root)
        self.assertEqual(len(views), len(ends))


if __name__ == "__main__":
    unittest.main()
