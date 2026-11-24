"""F4b and F4c: a pull request whose base is not main fails `plan`; the pull request template says "Base branch is main".

The planted faults run the real command on event files made by the test: a pull request on main passes; a pull request on another branch
(the stack that was retired) fails with the exact words; a push passes; an unreadable or empty event fails closed.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools import pr_base

REPO = Path(__file__).resolve().parent.parent


def event(base_ref=None, kind="pull_request"):
    if kind == "push":
        return {"ref": "refs/heads/main", "commits": []}
    return {"pull_request": {"number": 7, "base": {"ref": base_ref}} if base_ref is not None else {"number": 7}}


class CheckTests(unittest.TestCase):
    def test_main_passes_and_any_other_base_fails_with_the_words(self):
        self.assertEqual(pr_base.check("pull_request", "main"), (True, "base is main"))
        ok, line = pr_base.check("pull_request", "w78-broker-wiring")
        self.assertFalse(ok)
        self.assertIn("base is not main; one PR at a time", line)
        self.assertIn("w78-broker-wiring", line)

    def test_near_misses_fail(self):
        for base in ("Main", "main ", "master", "origin/main", "", None, 5):
            with self.subTest(base=base):
                self.assertFalse(pr_base.check("pull_request", base)[0])

    def test_a_push_and_other_events_are_not_checked(self):
        for ev in ("push", "workflow_dispatch"):
            self.assertTrue(pr_base.check(ev, None)[0])


class CommandTests(unittest.TestCase):
    def run_cmd(self, *args):
        p = subprocess.run([sys.executable, "-m", "tools.pr_base", *args], cwd=REPO, capture_output=True, text=True, timeout=30)
        self.assertIn(p.returncode, (0, 2, 64), p.stdout + p.stderr)
        return p

    def event_file(self, doc):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        f = Path(d.name) / "event.json"
        f.write_text(doc if isinstance(doc, str) else json.dumps(doc), encoding="utf-8")
        return str(f)

    def test_a_pull_request_event_on_main_is_exit_0(self):
        self.assertEqual(self.run_cmd("--event-file", self.event_file(event("main"))).returncode, 0)

    def test_planted_fault_a_pull_request_event_with_another_base_is_exit_2_and_says_so(self):
        p = self.run_cmd("--event-file", self.event_file(event("some-other-branch")))
        self.assertEqual(p.returncode, 2)
        self.assertIn("base is not main; one PR at a time", p.stderr)

    def test_a_push_event_passes(self):
        self.assertEqual(self.run_cmd("--event-file", self.event_file(event(kind="push"))).returncode, 0)

    def test_an_unreadable_a_broken_and_a_baseless_event_fail_closed(self):
        for doc in ("{", "[]", "", event()):
            with self.subTest(doc=str(doc)[:20]):
                self.assertEqual(self.run_cmd("--event-file", self.event_file(doc)).returncode, 2)
        self.assertEqual(self.run_cmd("--event-file", "/nonexistent/event.json").returncode, 2)

    def test_the_flags_form_and_usage(self):
        self.assertEqual(self.run_cmd("--event", "pull_request", "--base-ref", "main").returncode, 0)
        self.assertEqual(self.run_cmd("--event", "pull_request", "--base-ref", "x").returncode, 2)
        self.assertEqual(self.run_cmd("--bogus").returncode, 64)
        self.assertEqual(self.run_cmd().returncode, 64)


class FilesTests(unittest.TestCase):
    def test_the_plan_job_runs_the_check_first_from_the_event_file_and_never_from_a_template_value(self):
        text = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        step = 'run: python -m tools.pr_base --event-file "$GITHUB_EVENT_PATH"'
        self.assertEqual(text.count(step), 1)
        self.assertLess(text.index(step), text.index("Decide which tests run"))
        self.assertGreater(text.index(step), text.index("actions/setup-python@v5"))

    def test_the_pull_request_template_says_base_branch_is_main_and_puts_the_story_above_the_record(self):
        t = (REPO / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
        self.assertIn("Base branch is main", t)
        self.assertLess(t.index("## Story"), t.index("## Record"))
        self.assertIn("Made with umwayi-os", t)  # the line that was there stays


if __name__ == "__main__":
    unittest.main()
