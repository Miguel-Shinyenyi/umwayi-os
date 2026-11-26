"""Goal publish step 2: the push of the branch of a task in review (umwayi/goalpush.py). `origin` is always a local bare
repo, so nothing here uses the network."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from umwayi import goalgit as gg, goalpush, goalstate as gs, kill, logbook

WHEN = "2026-11-26"
GOAL, TASK, REPO = "G-0002", "T-01", "owner/project"
BRANCH = "umwayi/g-0002-t-01"
REF = "refs/heads/" + BRANCH


def rules_text(verdict):
    if verdict is None:
        return "rules: []\n"
    return (f"rules:\n  - id: publish-test\n    title: test\n    text: test\n    cause: test\n    verdict: {verdict}\n"
            f"    matchers:\n      type: goal_publish\n      repo: [{REPO}]\n")


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="umwayi-goalpush-")
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.root = base / "root"
        self.bare = base / "remote" / "owner" / "project.git"
        self.root.mkdir()
        self.bare.mkdir(parents=True)
        self.git(self.bare, "init", "--quiet", "--bare")
        self.git(self.root, "init", "--quiet")
        self.git(self.root, "symbolic-ref", "HEAD", "refs/heads/main")
        self.commit("one")
        self.git(self.root, "update-ref", REF, "HEAD")
        self.git(self.root, "update-ref", "refs/heads/umwayi/g-0002-t-02", "HEAD")
        self.tip = self.git(self.root, "rev-parse", REF)
        self.git(self.root, "remote", "add", "origin", str(self.bare))
        (self.root / "rules.yaml").write_text(rules_text("yes"), encoding="utf-8")

    def git(self, directory, *args):
        argv = ["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false",
                "-c", "core.hooksPath=/dev/null", "-C", str(directory), *args]
        return subprocess.run(argv, env=gg.git_env(), check=True, capture_output=True, text=True).stdout.strip()

    def commit(self, message):
        self.git(self.root, "commit", "--quiet", "--allow-empty", "-m", message)

    def refs(self):
        return self.git(self.bare, "for-each-ref", "--format=%(refname) %(objectname)")

    def log(self, entry):
        logbook.append(self.root, entry)

    def goal_entries(self):
        self.log(gs.started_entry(WHEN, GOAL, 20, "0123abcd", "guide", 100))
        self.log(gs.planned_entry(WHEN, GOAL, "guide", 1, 60, 20, "0123abcd"))
        self.log(gs.plan_approved_entry(WHEN, GOAL, [TASK], [], "builder", "tester", "guide", 500))

    def move(self, old, new, reason, **kw):
        self.log(gs.state_entry(WHEN, GOAL, TASK, old, new, reason, **kw))

    def in_review(self, branch=BRANCH, tip=None):
        self.goal_entries()
        self.move("queued", "running", "start")
        self.move("running", "in review", "checked", branch=branch, tip=tip or self.tip)

    def push(self, goal=GOAL, task=TASK, repo=REPO):
        return goalpush.push(self.root, goal, task, repo, when=WHEN)

    def entries(self):
        return [e for e in logbook.read_checked(self.root) if e.source == goalpush.SOURCE]

    def spy(self, before_push=None, result=None):
        """Record every argument list of the module. `before_push` runs just before the push."""
        calls, real = [], goalpush._git

        def run(argv):
            calls.append(list(argv))
            if "push" in argv:
                if before_push:
                    before_push()
                if result is not None:
                    return result()
            return real(argv)

        patcher = mock.patch.object(goalpush, "_git", run)
        patcher.start()
        self.addCleanup(patcher.stop)
        return calls

    def pushes(self, calls):
        return [c for c in calls if "push" in c]

    def refused(self, word, **kw):
        calls = self.spy()
        self.assertEqual(self.push(**kw), word)
        self.assertEqual(self.pushes(calls), [])
        self.assertEqual(self.refs(), "")


class PushTests(Base):
    def test_a_push_creates_only_the_task_branch(self):
        self.in_review()
        self.git(self.root, "tag", "-a", "v1", "-m", "v1", self.tip)
        self.git(self.root, "config", "push.followTags", "true")
        self.git(self.root, "config", "remote.origin.push", "refs/heads/*:refs/heads/*")
        self.assertEqual(self.push(), "pushed")
        self.assertEqual(self.refs(), f"{REF} {self.tip}")

    def test_the_argument_list_is_fixed_and_never_forced(self):
        self.in_review()
        calls = self.spy()
        self.assertEqual(self.push(), "pushed")
        self.assertEqual(self.pushes(calls), [[
            "git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c", "remote.origin.mirror=false",
            "-C", str(self.root), "push", "--no-follow-tags", "--recurse-submodules=no", "origin",
            f"{self.tip}:{REF}"]])

    def test_the_runner_uses_no_shell(self):
        self.in_review()
        with mock.patch.object(gg.subprocess, "Popen", wraps=subprocess.Popen) as popen:
            self.assertEqual(self.push(), "pushed")
        for call in popen.call_args_list:
            self.assertIsInstance(call.args[0], list)
            self.assertFalse(call.kwargs.get("shell", False))

    def test_a_mirror_setting_pushes_only_the_task_branch(self):
        self.in_review()
        self.git(self.root, "config", "remote.origin.mirror", "true")
        self.assertEqual(self.push(), "pushed")
        self.assertEqual(self.refs(), f"{REF} {self.tip}")

    def test_a_push_that_is_not_a_fast_forward_fails_and_changes_nothing(self):
        self.in_review()
        self.commit("two")
        self.git(self.root, "push", "--quiet", "origin", "HEAD:" + REF)
        before = self.refs()
        self.assertEqual(self.push(), "failed")
        self.assertEqual(self.refs(), before)
        self.assertEqual(self.entries()[-1].checked, "Pushes run: 1. Branches confirmed pushed: 0.")


class NameAndStateTests(Base):
    def test_a_task_that_is_not_known_pushes_nothing(self):
        self.refused("state")

    def test_every_other_state_pushes_nothing(self):
        steps = (lambda: self.goal_entries(),  # queued
                 lambda: self.move("queued", "running", "start", branch=BRANCH, tip=self.tip),
                 lambda: self.move("running", "needs owner", "unclear", branch=BRANCH, tip=self.tip),
                 lambda: self.move("needs owner", "queued", "answered"),
                 lambda: self.move("queued", "stopped", "owner"))
        calls = self.spy()
        for step in steps:
            step()
            self.assertEqual(self.push(), "state")
        self.assertEqual(self.pushes(calls), [])
        self.assertEqual(self.refs(), "")

    def test_a_failed_task_pushes_nothing(self):
        self.goal_entries()
        self.move("queued", "running", "start")
        self.move("running", "failed", "tests", branch=BRANCH, tip=self.tip)
        self.refused("state")

    def test_a_merged_task_pushes_nothing(self):
        self.in_review()
        self.move("in review", "merged", "observed", commit=self.tip)
        self.refused("state")

    def test_a_stopped_goal_pushes_nothing(self):
        self.in_review()
        self.log(gs.goal_stopped_entry(WHEN, GOAL, "owner"))
        self.refused("state")

    def test_a_recorded_branch_of_another_task_pushes_nothing(self):
        self.in_review(branch="umwayi/g-0002-t-02")
        self.refused("state")

    def test_a_short_tip_pushes_nothing(self):
        self.in_review(tip=self.tip[:12])
        self.refused("state")

    def test_a_branch_that_moved_after_review_pushes_nothing(self):
        self.in_review()
        self.commit("later")
        self.git(self.root, "update-ref", REF, "HEAD")
        self.refused("moved")

    def test_a_missing_branch_pushes_nothing(self):
        self.in_review()
        self.git(self.root, "update-ref", "-d", REF)
        self.refused("moved")

    def test_no_input_can_name_main_or_add_a_word(self):
        self.in_review()
        calls = self.spy()
        for kw in ({"goal": "main"}, {"task": "main"}, {"goal": "G-0002\n"}, {"task": "T-01\n"},
                   {"repo": REPO + "\n"}, {"task": "T-01:refs/heads/main"}, {"goal": "+G-0002"},
                   {"repo": "--force"}, {"repo": None}, {"goal": None}, {"task": "T-001"}):
            self.assertEqual(self.push(**kw), "name", msg=str(kw))
        self.assertEqual(calls, [])
        self.assertEqual(self.refs(), "")

    def test_the_argument_builder_refuses_main_and_a_plus(self):
        for tip, branch in ((self.tip, "main"), (self.tip, "+" + BRANCH), (self.tip, BRANCH + ":refs/heads/main"),
                            ("+" + self.tip, BRANCH), ("main", BRANCH), (self.tip, BRANCH + "\n")):
            with self.assertRaises(ValueError, msg=(tip, branch)):
                goalpush.push_argv(str(self.root), tip, branch)


class OriginTests(Base):
    def test_an_origin_that_is_another_repo_pushes_nothing(self):
        self.in_review()
        self.refused("origin", repo="owner/other")

    def test_a_second_push_url_pushes_nothing(self):
        self.in_review()
        self.git(self.root, "remote", "set-url", "--add", "--push", "origin", str(self.bare))
        self.git(self.root, "remote", "set-url", "--add", "--push", "origin", str(self.bare.parent / "x.git"))
        self.refused("origin")

    def test_no_origin_pushes_nothing(self):
        self.in_review()
        self.git(self.root, "remote", "remove", "origin")
        self.refused("origin")

    def test_which_urls_name_the_repo(self):
        def says(url):
            with mock.patch.object(goalpush, "_git", lambda argv: (0, (url + "\n").encode())):
                return goalpush._origin_is("/x", REPO)

        for url in ("https://github.com/owner/project", "https://github.com/owner/project.git",
                    "git@github.com:owner/project.git", "ssh://git@github.com/owner/project.git"):
            self.assertTrue(says(url), url)
        for url in ("https://example.invalid/owner/project.git", "https://github.com/owner/project-two",
                    "https://github.com/someone/owner/project", "ext::owner/project.git", "owner/project.git"):
            self.assertFalse(says(url), url)


class RulesTests(Base):
    def answer(self, text, word):
        self.in_review()
        (self.root / "rules.yaml").write_text(text, encoding="utf-8")
        self.refused(word)
        self.assertEqual(self.entries(), [])

    def test_no_leaves_the_bare_repo_unchanged(self):
        self.answer(rules_text("no"), "no")

    def test_ask_leaves_the_bare_repo_unchanged(self):
        self.answer(rules_text("ask"), "ask")

    def test_no_rule_leaves_the_bare_repo_unchanged(self):
        self.answer(rules_text(None), "ask")

    def test_unlogged_leaves_the_bare_repo_unchanged(self):
        self.in_review()
        with mock.patch.object(logbook, "append", side_effect=logbook.UmwayiError("planted")):
            self.refused("unlogged")


class KillTests(Base):
    def test_the_kill_switch_leaves_the_bare_repo_unchanged(self):
        self.in_review()
        kill.turn_on(self.root, WHEN)
        self.refused("kill")
        self.assertEqual([e.checked for e in self.entries()], ["Pushes run: 0."])

    def test_an_unknown_switch_state_pushes_nothing(self):
        self.in_review()
        with mock.patch.object(kill, "state", return_value=kill.UNKNOWN):
            self.refused("kill")

    def test_a_switch_turned_on_after_the_first_entry_stops_the_push(self):
        self.in_review()
        real = logbook.append

        def append(root, entry):
            real(root, entry)
            if entry.added.endswith("push attempt starts"):
                kill.turn_on(self.root, WHEN)

        with mock.patch.object(logbook, "append", append):
            self.refused("kill")
        self.assertEqual(self.entries()[-1].checked, "Pushes run: 0. Branches confirmed pushed: 0.")


class LogbookTests(Base):
    def test_one_entry_before_the_push_and_one_after_with_counts_only(self):
        self.in_review()
        seen = []
        self.spy(before_push=lambda: seen.extend(self.entries()))
        self.assertEqual(self.push(), "pushed")
        self.assertEqual([e.added for e in seen], [f"Goal {GOAL} task {TASK}: push attempt starts"])
        first, second = self.entries()
        self.assertEqual((first.checked, first.not_done), ("Branches to push: 1.", "No push has run yet."))
        self.assertEqual(second.added, f"Goal {GOAL} task {TASK}: push attempt ended")
        self.assertEqual(second.checked, "Pushes run: 1. Branches confirmed pushed: 1.")
        self.assertEqual(second.not_done, "No pull request was opened and nothing was merged.")

    def failing_append(self, ending):
        real = logbook.append

        def append(root, entry):
            if entry.added.endswith(ending):
                raise logbook.UmwayiError("planted")
            real(root, entry)

        return mock.patch.object(logbook, "append", append)

    def test_no_push_runs_if_the_first_entry_fails(self):
        self.in_review()
        with self.failing_append("push attempt starts"):
            self.refused("unlogged")

    def test_a_failed_second_entry_is_not_reported_as_pushed(self):
        self.in_review()
        with self.failing_append("push attempt ended"):
            self.assertEqual(self.push(), "unrecorded")

    def test_git_output_is_never_in_an_entry_and_a_failed_push_has_both_entries(self):
        self.in_review()
        self.spy(result=lambda: (1, b"SECRET-GIT-OUTPUT"))
        self.assertEqual(self.push(), "failed")
        self.assertEqual(len(self.entries()), 2)
        self.assertNotIn("SECRET-GIT-OUTPUT", (self.root / "LOGBOOK.md").read_text(encoding="utf-8"))

    def test_a_git_error_in_the_push_has_both_entries(self):
        self.in_review()

        def boom():
            raise gg.GitError("planted")

        self.spy(result=boom)
        self.assertEqual(self.push(), "failed")
        self.assertEqual(len(self.entries()), 2)

    def test_an_unexpected_error_in_the_push_still_has_the_second_entry(self):
        self.in_review()

        def boom():
            raise RuntimeError("planted")

        self.spy(result=boom)
        with self.assertRaises(RuntimeError):
            self.push()
        self.assertEqual(len(self.entries()), 2)

    def test_the_goal_entries_still_parse_after_a_push(self):
        self.in_review()
        self.assertEqual(self.push(), "pushed")
        self.assertEqual(gs.view(self.root)[GOAL].tasks[TASK].state, "in review")


if __name__ == "__main__":
    unittest.main()
