"""W9.8 / W9.R2.6, W9.R9.6, W9.R17.3: the owner commands approve, answer and merged.

Without a terminal on standard input and output each is exit 2 and changes nothing (a byte snapshot of the root and of
the worktree root). With a fake terminal they do what the spec says. (The example rules of the adapters that deny
these commands to an AI helper wait for the owner: the pinned hashes of tests/test_starter_rules.py.)
"""

import hashlib
import os
import unittest
from pathlib import Path

from tests.goal import cmdsupport as cs
from tests.goal import runsupport as rs
from umwayi import goalstate as gs

REPO = Path(__file__).resolve().parents[2]


def snapshot(*folders):
    out = {}
    for folder in folders:
        folder = Path(folder)
        if not folder.exists():
            continue
        for p in sorted(folder.rglob("*")):
            if ".git" in p.parts:
                continue
            if p.is_file() and not p.is_symlink():
                out[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
            else:
                out[str(p)] = "dir"
    return out


class NoTerminalTests(cs.CmdCase):
    def assert_refused_and_unchanged(self, name, *args, **kw):
        before = snapshot(self.root, str(self.root) + "-worktrees")
        self.terminal = False
        self.assertEqual(self.call(name, *args, **kw), 2)
        self.assertIn("needs a terminal", "\n".join(self.err))
        self.assertEqual(snapshot(self.root, str(self.root) + "-worktrees"), before)
        self.terminal = True

    def in_review(self):
        goal = self.g_approved()
        scripts = [{"steps": rs.builder_steps(goal, "T-01"), "spend": 3}, {"steps": rs.tester_steps()}, {"steps": rs.check_steps()}]
        self.assertEqual(self.call("run", goal, scripts=scripts), 0, self.err)
        return goal

    def test_approve_without_a_terminal(self):
        goal = self.g_start()
        self.assert_refused_and_unchanged("approve", goal, "claude-build", "kiro-test", "sonnet", "high", 30, 100)
        self.assertFalse(gs.read_goal(self.root, goal)["approved"])

    def test_answer_without_a_terminal(self):
        goal = self.g_approved()
        gs.change_state(self.root, goal, "T-01", "needs owner", "unclear", when=self.when, now=self.clock())
        self.assert_refused_and_unchanged("answer", goal, "T-01", "yes")
        self.assertEqual(gs.read_task(self.root, goal, "T-01")["state"], "needs owner")

    def test_merged_without_a_terminal(self):
        goal = self.in_review()
        rs.git(self.root, "merge", "-q", "--squash", "umwayi/g-0001-t-01")
        rs.git(self.root, "commit", "-q", "-m", "squash")
        self.assert_refused_and_unchanged("merged", goal, "T-01", rs.git(self.root, "rev-parse", "HEAD"))
        self.assertEqual(gs.read_task(self.root, goal, "T-01")["state"], "in review")

    def test_the_terminal_check_comes_before_anything_is_read(self):
        self.terminal = False
        self.assertEqual(self.call("answer", "G-0099", "T-01", "yes"), 2)  # no such goal: still the terminal sentence
        self.assertIn("needs a terminal", "\n".join(self.err))


class AnswerTests(cs.CmdCase):
    def needs_owner(self):
        goal = self.g_approved()
        gs.change_state(self.root, goal, "T-01", "needs owner", "unclear", when=self.when, now=self.clock())
        return goal

    def test_yes_queues_it_again_and_starts_nothing(self):
        goal = self.needs_owner()
        self.assertEqual(self.call("answer", goal, "T-01", "yes"), 0, self.err)
        self.assertEqual(gs.read_task(self.root, goal, "T-01")["state"], "queued")
        self.assertEqual(self.children.started(), 0)
        self.assertIn("Answering starts nothing", "\n".join(self.out))

    def test_no_stops_it(self):
        goal = self.needs_owner()
        self.assertEqual(self.call("answer", goal, "T-01", "no"), 0)
        self.assertEqual((gs.read_task(self.root, goal, "T-01")["state"], gs.read_task(self.root, goal, "T-01")["reason"]),
                         ("stopped", "owner"))

    def test_an_answer_after_the_deadline_is_refused_and_the_denial_is_logged_once(self):
        goal = self.needs_owner()
        self.clock.advance(25 * 3600)
        self.assertEqual(self.call("answer", goal, "T-01", "yes"), 2)
        self.assertIn("timed out", "\n".join(self.err))
        self.assertEqual(self.call("answer", goal, "T-01", "yes"), 2)
        denials = [e for e in self.entries() if e.source == gs.SOURCE and e.added.startswith("Approval denied")]
        self.assertEqual(len(denials), 1)

    def test_a_task_that_does_not_need_the_owner_is_refused(self):
        goal = self.g_approved()
        self.assertEqual(self.call("answer", goal, "T-01", "yes"), 2)


class MergedTests(cs.CmdCase):
    def in_review(self):
        goal = self.g_approved()
        scripts = [{"steps": rs.builder_steps(goal, "T-01"), "spend": 3}, {"steps": rs.tester_steps()}, {"steps": rs.check_steps()}]
        self.assertEqual(self.call("run", goal, scripts=scripts), 0, self.err)
        return goal

    def test_a_squash_merge_is_declared_with_its_commit_and_the_worktree_is_removed(self):
        goal = self.in_review()
        rs.git(self.root, "merge", "-q", "--squash", "umwayi/g-0001-t-01")
        rs.git(self.root, "commit", "-q", "-m", "squash")
        sha = rs.git(self.root, "rev-parse", "HEAD")
        self.assertEqual(self.call("merged", goal, "T-01", sha), 0, self.err)
        t = gs.read_task(self.root, goal, "T-01")
        self.assertEqual((t["state"], t["reason"], t["commit"]), ("merged", "declared", sha))
        self.assertFalse(os.path.exists(str(self.root) + "-worktrees/g-0001-t-01"))
        self.assertIn("umwayi/g-0001-t-01", rs.git(self.root, "branch", "--list"))

    def test_a_commit_that_is_not_on_main_is_refused(self):
        goal = self.in_review()
        tip = gs.read_task(self.root, goal, "T-01")["tip"]
        self.assertEqual(self.call("merged", goal, "T-01", tip), 2)  # on the branch only
        self.assertEqual(self.call("merged", goal, "T-01", "a" * 40), 2)  # not a commit
        self.assertEqual(self.call("merged", goal, "T-01"), 2)  # without --commit the tip, not on main
        self.assertEqual(gs.read_task(self.root, goal, "T-01")["state"], "in review")

    def test_a_task_that_is_not_in_review_is_refused(self):
        goal = self.g_approved()
        self.assertEqual(self.call("merged", goal, "T-01", "b" * 40), 2)


if __name__ == "__main__":
    unittest.main()
