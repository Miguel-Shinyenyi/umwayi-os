"""L7: the story check and the honesty scan of the pull request text (tools/pr_story.py), with planted faults.

An owner-stop pull request with a short or empty story fails; a pull request that does not stop for the owner only gets a warning; an
overclaim phrase fails in any pull request; the cooperative sentence and negations do not; the placeholder text of the template is not a
story; and the real template and workflow carry the lines the check reads.
"""
import json
import os
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


class OwnerStopFromFilesTests(unittest.TestCase):
    """K1: the owner stop is derived from the changed files, so the body cannot claim no for a pull request that touches code."""

    def test_planted_fault_a_workflow_edit_with_owner_stop_no_fails(self):
        fails, _ = pr_story.check("pull_request", body(stop="no"), [".github/workflows/ci.yml"])
        self.assertEqual(len(fails), 1)
        self.assertIn(".github/workflows/ci.yml", fails[0])
        self.assertIn("says `Owner stop: no`", fails[0])

    def test_a_body_with_no_owner_stop_line_fails_when_a_code_file_changed(self):
        fails, _ = pr_story.check("pull_request", "## Story\n\nno line here\n", ["umwayi/cli.py"])
        self.assertTrue(any("has no `Owner stop: yes` line" in f for f in fails))

    def test_every_kind_of_non_doc_file_makes_an_owner_stop(self):
        for f in ("umwayi/cli.py", "tools/pr_green.py", "adapters/claude_code/hook.py", "guidance.yaml", "units.yaml", "rules.yaml",
                  ".github/pull_request_template.md", "ui/src/app.js", "site/app/page.js", "pyproject.toml", "umwayi.json"):
            with self.subTest(f=f):
                self.assertEqual(pr_story.owner_stop_files([f]), [f])
                self.assertTrue(pr_story.check("pull_request", body(stop="no"), [f])[0])

    def test_docs_tests_and_the_generated_files_of_the_test_map_need_no_owner_stop(self):
        files = ["docs/a.md", "docs-parts/status-log/x.md", "tests/test_x.py", "tests/data/x.txt", "README.md", "PROJECT.md",
                 ".kiro/specs/umwayi-os/tasks.md", "tools/ci_map.json", "tools/ci_map_table.md", "tools/ci_shards.json"]
        self.assertEqual(pr_story.owner_stop_files(files), [])
        self.assertEqual(pr_story.check("pull_request", body(stop="no"), files), ([], []))

    def test_one_code_file_among_docs_makes_it_an_owner_stop_and_the_message_names_it(self):
        fails, _ = pr_story.check("pull_request", body(stop="no"), ["docs/a.md", "tests/test_x.py", "tools/story_video.py"])
        self.assertIn("tools/story_video.py", fails[0])
        self.assertNotIn("docs/a.md", fails[0])

    def test_a_body_that_says_yes_is_fine_for_a_docs_only_pull_request_and_for_a_code_one(self):
        self.assertEqual(pr_story.check("pull_request", body(stop="yes"), ["docs/a.md"]), ([], []))
        self.assertEqual(pr_story.check("pull_request", body(stop="yes"), ["umwayi/cli.py"]), ([], []))

    def test_a_long_list_is_cut_and_counted(self):
        fails, _ = pr_story.check("pull_request", body(stop="no"), [f"umwayi/m{i}.py" for i in range(8)])
        self.assertIn("and 3 more", fails[0])

    def test_files_that_could_not_be_read_only_warn_and_only_for_a_body_that_says_no(self):
        fails, warns = pr_story.check("pull_request", body(stop="no"), None)
        self.assertEqual(fails, [])
        self.assertTrue(any("could not be read" in w for w in warns))
        self.assertFalse(any("could not be read" in w for w in pr_story.check("pull_request", body(stop="yes"), None)[1]))

    def test_without_the_files_the_old_behaviour_is_unchanged(self):
        self.assertEqual(pr_story.check("pull_request", body(stop="no")), ([], []))

    def test_k3_the_first_text_of_pr_209_failed_the_scan_and_the_corrected_text_passed(self):
        """PR 209 quoted the two example phrases it scans for and failed its own check; rewording them passed. Keep that case."""
        first = body(extra='It fails text such as "is enforced" or "is sandboxed", unless it is negated.')
        fails, _ = pr_story.check("pull_request", first, ["tools/pr_story.py"])
        self.assertTrue(any("claims more" in f for f in fails))
        fixed = body(stop="yes", extra="It fails text that uses the words as a plain claim about a feature.")
        self.assertEqual([f for f in pr_story.check("pull_request", fixed, ["tools/pr_story.py"])[0] if "claims more" in f], [])


class GitTests(unittest.TestCase):
    """The changed files are read with git from the two commits of the event."""

    def repo(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        root = Path(d.name)
        run = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=root, check=True, capture_output=True, text=True)
        run("init", "-q", "-b", "main")
        (root / "docs").mkdir()
        (root / "docs" / "a.md").write_text("a", encoding="utf-8")
        run("add", "-A")
        run("commit", "-q", "-m", "base")
        base = run("rev-parse", "HEAD").stdout.strip()
        run("checkout", "-q", "-b", "feature")
        (root / "docs" / "b.md").write_text("b", encoding="utf-8")
        (root / "tool.py").write_text("x = 1\n", encoding="utf-8")
        run("add", "-A")
        run("commit", "-q", "-m", "feature")
        return root, base, run("rev-parse", "HEAD").stdout.strip()

    def test_changed_files_come_from_the_three_dot_diff(self):
        root, base, head = self.repo()
        self.assertEqual(sorted(pr_story.changed_files(base, head, root)), ["docs/b.md", "tool.py"])

    def test_a_bad_sha_an_unknown_commit_or_a_missing_one_is_none(self):
        root, base, head = self.repo()
        for b, h in ((None, head), (base, None), ("x" * 40, head), ("0" * 40, "1" * 40), ("main", "feature")):
            with self.subTest(b=b, h=h):
                self.assertIsNone(pr_story.changed_files(b, h, root))

    def test_the_real_command_fails_a_body_that_says_no_for_a_pull_request_that_changed_code(self):
        root, base, head = self.repo()
        event = {"pull_request": {"body": body(stop="no"), "base": {"sha": base}, "head": {"sha": head}}}
        f = root / "event.json"
        f.write_text(json.dumps(event), encoding="utf-8")
        env = dict(os.environ, PYTHONPATH=str(REPO))
        p = subprocess.run([sys.executable, "-m", "tools.pr_story", "--event-file", str(f)], cwd=root, capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("tool.py", p.stdout)
        event["pull_request"]["body"] = body(stop="yes")
        f.write_text(json.dumps(event), encoding="utf-8")
        p = subprocess.run([sys.executable, "-m", "tools.pr_story", "--event-file", str(f)], cwd=root, capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


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
