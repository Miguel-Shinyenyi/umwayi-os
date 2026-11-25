"""tools.pr_open and tools.pr_watch: the steps that were skipped or reordered by hand, and the waiter that told nobody.

Both run on fakes: no git, no gh and no network are used, and nothing is pushed or opened."""
import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from tools import pr_open, pr_story, pr_watch

SHA = "a" * 40
STORY = " ".join(["The owner asked for one safe way to open a pull request, like a checklist read before a flight."] * 12)
GOOD = f"Owner stop: yes. This changes a tools script.\n\n## Story\n\n{STORY}\n\n## Record\n\n- Changed: tools/x.py\n"


class Fake:
    """A stand-in for `sh`: answers by the first words of the command and records every command."""

    def __init__(self, branch="feature", dirty="", open_prs="0", ancestor=0, push=0, create=("https://github.com/o/r/pull/250", 0), after_dirty="x", docs=0):
        self.calls, self.branch, self.dirty, self.open_prs, self.ancestor, self.push = [], branch, dirty, open_prs, ancestor, push
        self.create, self.after_dirty, self.status_calls, self.docs = create, after_dirty, 0, docs

    def __call__(self, args, cwd=None):
        self.calls.append(list(args))
        a = list(args)
        if a[:3] == ["git", "branch", "--show-current"]:
            return 0, self.branch, ""
        if a[:3] == ["git", "status", "--porcelain"]:
            self.status_calls += 1
            return 0, (self.dirty if self.status_calls == 1 else "" if self.status_calls == 2 else self.after_dirty), ""  # start, after the docs build, after the number
        if a[:3] == ["gh", "pr", "list"]:
            return 0, self.open_prs, ""
        if a[:2] == ["git", "merge-base"]:
            return self.ancestor, "", ""
        if a[:2] == ["git", "rev-parse"]:
            return 0, SHA, ""
        if "docs" in a and "build" in a:
            return self.docs, "", "refused" if self.docs else ""
        if a[:2] == ["git", "push"]:
            return self.push, "", "denied" if self.push else ""
        if a[:3] == ["gh", "pr", "create"]:
            return self.create[1], self.create[0], ""
        return 0, "", ""

    def said(self, *words):
        return any(all(w in c for w in words) for c in self.calls)


def run_open(fake, body=GOOD, changed=("tools/x.py",)):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(pr_story, "changed_files", return_value=list(changed)), redirect_stdout(out), redirect_stderr(err):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "body.md"
            f.write_text(body, encoding="utf-8")
            rc = pr_open.main(["--title", "T", "--body-file", str(f)], run=fake)
    return rc, out.getvalue(), err.getvalue()


class OpenStopsBeforeAnythingIsPushedTests(unittest.TestCase):
    def assert_stopped(self, fake, rc, err, word):
        self.assertEqual(rc, 1, err)
        self.assertIn(word, err)
        self.assertFalse(fake.said("git", "push"))
        self.assertFalse(fake.said("gh", "pr", "create"))

    def test_main_or_a_detached_head(self):
        for branch in ("main", ""):
            fake = Fake(branch=branch)
            rc, _, err = run_open(fake)
            self.assert_stopped(fake, rc, err, "not a feature branch")

    def test_a_dirty_tree(self):
        fake = Fake(dirty=" M tools/x.py")
        rc, _, err = run_open(fake)
        self.assert_stopped(fake, rc, err, "not clean")

    def test_another_pull_request_is_open(self):
        fake = Fake(open_prs="1")
        rc, _, err = run_open(fake)
        self.assert_stopped(fake, rc, err, "one at a time")

    def test_gh_gives_no_answer_about_the_open_pull_requests(self):
        fake = Fake(open_prs="")
        rc, _, err = run_open(fake)
        self.assert_stopped(fake, rc, err, "no answer")

    def test_a_refused_docs_build_stops_before_the_pull_request_exists(self):
        fake = Fake(docs=1)
        rc, _, err = run_open(fake)
        self.assert_stopped(fake, rc, err, "docs build was refused")

    def test_the_branch_does_not_hold_main(self):
        fake = Fake(ancestor=1)
        rc, _, err = run_open(fake)
        self.assert_stopped(fake, rc, err, "merge_main")

    def test_a_text_that_overclaims_fails_the_scan(self):
        fake = Fake()
        rc, _, err = run_open(fake, body=GOOD.replace("a checklist", "a checklist, and the agent is enforced"))
        self.assert_stopped(fake, rc, err, "fails the scan")

    def test_an_owner_stop_written_as_no_for_a_tools_change_fails_the_scan(self):
        fake = Fake()
        rc, _, err = run_open(fake, body=GOOD.replace("Owner stop: yes", "Owner stop: no"))
        self.assert_stopped(fake, rc, err, "fails the scan")


class OpenHappyPathTests(unittest.TestCase):
    def test_push_then_open_then_number_then_push_again_in_that_order(self):
        fake = Fake()
        rc, out, err = run_open(fake)
        self.assertEqual(rc, 0, err)
        names = [" ".join(c[:3]) for c in fake.calls]
        order = [names.index("git push -q"), names.index("gh pr create"), [i for i, c in enumerate(fake.calls) if "tools.pr_number" in c][0]]
        self.assertEqual(order, sorted(order))
        self.assertEqual(sum(1 for c in fake.calls if c[:2] == ["git", "push"]), 2)  # before opening, and after the number is written
        self.assertIn("opened: pull request 250", out)
        self.assertIn("python -m tools.pr_watch 250 --stop-at green", out)

    def test_no_second_push_when_the_number_changed_nothing(self):
        fake = Fake(after_dirty="")
        rc, _, _ = run_open(fake)
        self.assertEqual(rc, 0)
        self.assertEqual(sum(1 for c in fake.calls if c[:2] == ["git", "push"]), 1)

    def test_a_failed_push_is_exit_2_and_nothing_is_opened(self):
        fake = Fake(push=1)
        rc, _, err = run_open(fake)
        self.assertEqual(rc, 2)
        self.assertIn("403", err)
        self.assertFalse(fake.said("gh", "pr", "create"))

    def test_a_pull_request_that_did_not_open_is_exit_2(self):
        fake = Fake(create=("", 1))
        rc, _, _ = run_open(fake)
        self.assertEqual(rc, 2)

    def test_usage_and_a_missing_body_file(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(pr_open.main([]), 64)
            self.assertEqual(pr_open.main(["--title", "T", "--body-file", "/nonexistent/body.md"]), 64)

    def test_it_reads_no_token(self):
        src = open(pr_open.__file__, encoding="utf-8").read()
        self.assertNotIn("auth token", src)
        self.assertNotIn("GH_TOKEN", src)


class Seq:
    def __init__(self, items):
        self.items = list(items)

    def __call__(self, pr):
        return self.items.pop(0) if len(self.items) > 1 else self.items[0]


def run_watch(states, greens, stop_at="merged"):
    lines = []
    rc = pr_watch.watch(250, stop_at, state_of=Seq(states), green_of=Seq(greens), sleep=lambda s: None, say=lines.append, interval=0, max_polls=50)
    return rc, lines


class WatchTests(unittest.TestCase):
    def test_a_merge_ends_the_wait_with_one_line(self):
        rc, lines = run_watch(["OPEN", "OPEN", "MERGED"], [(False, "still running: test")])
        self.assertEqual((rc, lines), (0, ["PR 250 MERGED"]))

    def test_a_close_ends_the_wait_too(self):
        rc, lines = run_watch(["CLOSED"], [(False, "x")])
        self.assertEqual((rc, lines), (0, ["PR 250 CLOSED"]))

    def test_a_failed_check_ends_it_with_exit_2(self):
        rc, lines = run_watch(["OPEN"], [(False, "failed: result, test (3.10, shard 1/3)")])
        self.assertEqual(rc, 2)
        self.assertIn("CHECK FAILED", lines[0])

    def test_green_is_said_once_and_the_wait_goes_on_to_the_merge(self):
        rc, lines = run_watch(["OPEN", "OPEN", "OPEN", "MERGED"], [(True, "green at abc1234")])
        self.assertEqual(rc, 0)
        self.assertEqual(sum(1 for l in lines if "green" in l), 1)
        self.assertEqual(lines[-1], "PR 250 MERGED")

    def test_stop_at_green_ends_at_the_first_green(self):
        rc, lines = run_watch(["OPEN", "OPEN"], [(False, "still running: test"), (True, "green at abc1234")], stop_at="green")
        self.assertEqual(rc, 0)
        self.assertEqual(len(lines), 1)
        self.assertIn("waiting for the owner's word", lines[0])

    def test_running_checks_are_not_a_failure(self):
        rc, lines = run_watch(["OPEN", "OPEN", "MERGED"], [(False, "still running: test"), (False, "no check run for this head yet")])
        self.assertEqual((rc, lines), (0, ["PR 250 MERGED"]))

    def test_ten_silent_polls_end_the_watch_with_exit_3_and_say_so(self):
        rc, lines = run_watch([None], [(None, "no answer")])
        self.assertEqual(rc, 3)
        self.assertIn("WATCH ENDED", lines[0])

    def test_usage(self):
        with redirect_stderr(io.StringIO()):
            for bad in ([], ["x"], ["1", "--stop-at"], ["1", "--stop-at", "never"], ["1", "2"]):
                self.assertEqual(pr_watch.main(bad), 64, bad)


if __name__ == "__main__":
    unittest.main()
