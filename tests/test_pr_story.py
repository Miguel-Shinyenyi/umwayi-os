"""L7: the story check and the honesty scan of the pull request text (tools/pr_story.py), with planted faults.

An owner-stop pull request with a short or empty story fails; a pull request that does not stop for the owner only gets a warning; an
overclaim phrase fails in any pull request; the cooperative sentence and negations do not; the placeholder text of the template is not a
story; and the real template and workflow carry the lines the check reads.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools import pr_story

REPO = Path(__file__).resolve().parent.parent
STORY = " ".join(["word"] * 120)


def body(story=STORY, stop="yes", extra=""):
    return f"Owner stop: {stop}\nVideo: none, docs only\n\n## Story\n\n{story}\n\n## Record\n\ntechnical. {extra}\n"


class CheckTests(unittest.TestCase):
    def test_a_long_story_on_an_owner_stop_pr_passes_with_nothing_to_say(self):
        self.assertEqual(pr_story.check("pull_request", body()), ([], []))

    def test_planted_fault_an_owner_stop_pr_with_a_short_or_empty_or_placeholder_story_fails(self):
        for story in ("", "Too short.", "(What changed and why, in plain words.)", " ".join(["w"] * 99)):
            with self.subTest(story=story[:20]):
                fails, _ = pr_story.check("pull_request", body(story))
                self.assertEqual(len(fails), 1)
                self.assertIn("needs at least 100", fails[0])

    def test_exactly_100_words_pass_and_the_owner_stop_and_video_lines_are_not_counted(self):
        self.assertEqual(pr_story.check("pull_request", body(" ".join(["w"] * 100))), ([], []))

    def test_a_pr_that_does_not_stop_for_the_owner_gets_a_warning_not_a_failure(self):
        fails, warns = pr_story.check("pull_request", body("short", stop="no"))
        self.assertEqual(fails, [])
        self.assertEqual(len(warns), 1)
        self.assertIn("advised", warns[0])

    def test_a_body_with_no_owner_stop_line_or_no_body_warns_and_only_fails_on_an_overclaim(self):
        self.assertEqual(pr_story.check("pull_request", "just text")[0], [])
        self.assertTrue(pr_story.check("pull_request", "just text")[1])
        self.assertEqual(pr_story.check("pull_request", None)[0], [])
        self.assertEqual(pr_story.check("pull_request", 5)[0], [])

    def test_the_story_is_only_the_text_under_the_story_heading(self):
        text = "Owner stop: yes\n## Record\n" + STORY + "\n## Story\nshort\n"
        self.assertEqual(len(pr_story.check("pull_request", text)[0]), 1)
        self.assertEqual(pr_story.story_of("## Story\nabc\n## Record\nxyz"), "abc")
        self.assertEqual(pr_story.story_of("<!-- ## Story\nhidden -->\nnone"), "")

    def test_a_push_is_not_checked(self):
        self.assertEqual(pr_story.check("push", None), ([], []))


class HonestyTests(unittest.TestCase):
    def test_planted_fault_each_overclaim_phrase_fails(self):
        for phrase in ("The rules are enforced by default.", "Enforcement is enforced now.", "Helpers are sandboxed by default.",
                       "The runs are now enforced.", "The helper is confined.", "This feature is enforced."):
            with self.subTest(phrase=phrase):
                fails, _ = pr_story.check("pull_request", body(extra=phrase))
                self.assertTrue(any("claims more" in f for f in fails), phrase)

    def test_the_cooperative_sentence_and_negations_pass(self):
        for ok in ("Enforcement is cooperative today and enforced where built.", "It is not enforced yet.",
                   "It is not sandboxed.", "Enforcement is Cooperative Today and Enforced where built."):
            with self.subTest(ok=ok):
                fails, _ = pr_story.check("pull_request", body(extra=ok))
                self.assertEqual(fails, [], ok)

    def test_a_bare_word_only_warns(self):
        fails, warns = pr_story.check("pull_request", body(extra="The confined start of the helper."))
        self.assertEqual(fails, [])
        self.assertTrue(any("confined" in w for w in warns))

    def test_a_comment_is_not_scanned(self):
        self.assertEqual(pr_story.check("pull_request", body(extra="<!-- is sandboxed -->"))[0], [])


class CommandTests(unittest.TestCase):
    def run_cmd(self, doc):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        f = Path(d.name) / "event.json"
        f.write_text(doc if isinstance(doc, str) else json.dumps(doc), encoding="utf-8")
        p = subprocess.run([sys.executable, "-m", "tools.pr_story", "--event-file", str(f)], cwd=REPO, capture_output=True, text=True, timeout=30)
        self.assertIn(p.returncode, (0, 2), p.stdout + p.stderr)
        return p

    def test_the_real_command_on_event_files(self):
        ok = self.run_cmd({"pull_request": {"body": body()}})
        self.assertEqual((ok.returncode, ok.stdout.strip()), (0, "pr_story: nothing to report"))
        bad = self.run_cmd({"pull_request": {"body": body("short")}})
        self.assertEqual(bad.returncode, 2)
        self.assertIn("::error::the story", bad.stdout)
        warn = self.run_cmd({"pull_request": {"body": body("short", stop="no")}})
        self.assertEqual(warn.returncode, 0)
        self.assertIn("::warning::", warn.stdout)
        self.assertEqual(self.run_cmd({"ref": "refs/heads/main"}).returncode, 0)

    def test_an_unreadable_event_file_does_not_fail_the_story_rule_by_itself(self):
        self.assertEqual(self.run_cmd("{").returncode, 0)

    def test_usage(self):
        self.assertEqual(pr_story.main([]), 64)
        self.assertEqual(pr_story.main(["--x", "y"]), 64)


class FilesTests(unittest.TestCase):
    def test_the_template_has_the_lines_and_the_headings_the_check_reads(self):
        t = (REPO / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
        for needle in ("Owner stop:", "Video:", "Limits and honesty:", "## Story", "## Record", "Base branch is main"):
            self.assertIn(needle, t)
        self.assertLess(t.index("## Story"), t.index("## Record"))
        self.assertEqual(pr_story.check("pull_request", t)[0], [], "an unfilled template is not an owner-stop PR: it says Owner stop: no")

    def test_the_plan_job_runs_the_story_check_from_the_event_file_after_the_base_check(self):
        text = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        step = 'run: python -m tools.pr_story --event-file "$GITHUB_EVENT_PATH"'
        self.assertEqual(text.count(step), 1)
        self.assertLess(text.index("tools.pr_base --event-file"), text.index(step))
        self.assertLess(text.index(step), text.index("Decide which tests run"))


if __name__ == "__main__":
    unittest.main()
