"""G8: lessons of rounds 4 to 6 as checks that fail a push or a build, each with a planted fault.

  a. `docs/testing.md` keeps its bullets: the first words of each bullet are pinned in `tests/data/testing_md_bullets.txt`; a bullet that
     is lost (not moved on purpose, with the pin edited in the same pull request) fails the build.
  b. `tools/pre_push.py` names the tests a change can break: the guards, the guard tests of the package touched, and every test file that
     mentions the name of a file the branch changes or moves (PR 196 failed because one did and I had not looked).
  e. `tools/pr_green.py` says green only for the checks of the exact head commit (an older run, a run still going, a failed run, or no
     `result` check is not green).
  f. Every status part that main holds is still in the branch: a part (one row of the status log) is never lost on a rebase or a merge.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools import pr_green, pre_push

REPO = Path(__file__).resolve().parent.parent
PINS = REPO / "tests" / "data" / "testing_md_bullets.txt"
PIN_LEN = 40


def bullets(text: str) -> list:
    """The first PIN_LEN characters of each `- ` bullet of the page, outside the generated table block."""
    out, inside = [], False
    for line in text.split("\n"):
        if "ci-map:begin" in line:
            inside = True
        elif "ci-map:end" in line:
            inside = False
        elif not inside and line.startswith("- "):
            out.append(line[:PIN_LEN])
    return out


def lost(pins: list, text: str) -> list:
    have = set(bullets(text))
    return [p for p in pins if p not in have]


def missing_parts(base_files: list, now_files: list) -> list:
    return sorted(set(base_files) - set(now_files))


class BulletTests(unittest.TestCase):
    def test_no_bullet_of_docs_testing_md_is_lost(self):
        pins = PINS.read_text(encoding="utf-8").split("\n")
        pins = [p for p in pins if p]
        self.assertEqual(lost(pins, (REPO / "docs" / "testing.md").read_text(encoding="utf-8")), [],
                         "a bullet of docs/testing.md is gone: put it back, or edit tests/data/testing_md_bullets.txt in the same pull request")

    def test_planted_fault_a_page_with_one_bullet_removed_is_found(self):
        text = (REPO / "docs" / "testing.md").read_text(encoding="utf-8")
        pins = [p for p in PINS.read_text(encoding="utf-8").split("\n") if p]
        first = next(l for l in text.split("\n") if l.startswith("- "))
        cut = text.replace(first + "\n", "", 1)
        self.assertEqual(lost(pins, cut), [first[:PIN_LEN]])

    def test_the_pins_are_the_bullets_of_the_page_now(self):
        pins = [p for p in PINS.read_text(encoding="utf-8").split("\n") if p]
        self.assertEqual(pins, bullets((REPO / "docs" / "testing.md").read_text(encoding="utf-8")))


class PrePushTests(unittest.TestCase):
    def tree(self, files: dict) -> Path:
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        root = Path(d.name)
        for rel, text in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8")
        return root

    def test_a_test_that_names_a_moved_file_is_found_even_when_the_path_is_written_in_pieces(self):
        # PR 196: tests/test_w21_goldens.py wrote REPO / "docs" / "testing.md" and I did not know it read the page
        root = self.tree({"tests/test_golden.py": 'p = REPO / "docs" / "testing.md"\n', "tests/test_other.py": "x = 1\n",
                          "tests/test_scan_files.py": "", "tests/test_system.py": "", "tests/test_automation.py": ""})
        mods = pre_push.modules_for(["docs/testing.md"], root)
        self.assertIn("tests.test_golden", mods)
        self.assertNotIn("tests.test_other", mods)

    def test_the_guards_always_run_and_a_package_runs_its_guard_test(self):
        root = self.tree({"tests/test_scan_files.py": "", "tests/test_system.py": "", "tests/test_automation.py": "",
                          "tests/agents/test_agents_gate.py": ""})
        self.assertEqual(pre_push.modules_for(["README.md"], root), ["tests.test_automation", "tests.test_scan_files", "tests.test_system"])
        mods = pre_push.modules_for(["umwayi/agents.py"], root)
        self.assertIn("tests.agents.test_agents_gate", mods)
        self.assertIn("tests.test_scan_files", mods)

    def test_a_changed_test_file_runs_and_a_deleted_one_does_not_make_a_bad_name(self):
        root = self.tree({"tests/test_new.py": "x = 1\n"})
        self.assertEqual(pre_push.modules_for(["tests/test_new.py", "tests/test_gone.py"], root), ["tests.test_new"])

    def test_a_status_part_is_not_searched_for_by_name(self):
        root = self.tree({"tests/test_x.py": "w916-scope-during-run.md\n"})
        self.assertEqual(pre_push.modules_for(["docs-parts/status-log/w916-scope-during-run.md"], root), [])

    def test_on_the_real_repository_a_change_to_a_page_a_test_names_finds_that_test(self):
        mods = pre_push.modules_for(["docs/seatbelt-check.md", "tools/ci_map.json"], REPO)
        self.assertIn("tests.test_ci_map", mods)
        self.assertIn("tests.test_docs", mods)

    def test_the_hook_is_written_once_and_never_over_a_hook_that_is_not_ours(self):
        root = self.tree({"README.md": "x"})
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        self.assertEqual(pre_push.install_hook(root), "written")
        self.assertEqual(pre_push.install_hook(root), "already ours")
        hook = root / ".git" / "hooks" / "pre-push"
        self.assertIn("tools.pre_push", hook.read_text(encoding="utf-8"))
        hook.write_text("#!/bin/sh\necho someone else\n", encoding="utf-8")
        self.assertEqual(pre_push.install_hook(root), "refused")
        self.assertIn("someone else", hook.read_text(encoding="utf-8"))

    def test_the_command_refuses_other_words(self):
        self.assertEqual(pre_push.main(["--frobnicate"]), 64)

    def git_repo(self):
        root = self.tree({"a.txt": "1"})
        run = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=root, check=True, capture_output=True)
        run("init", "-q", "-b", "main")
        run("add", "-A")
        run("commit", "-q", "-m", "one")
        return root, run

    def test_a7_a_branch_that_is_behind_main_is_refused(self):
        root, run = self.git_repo()
        run("branch", "feature")
        run("checkout", "-q", "feature")
        run("checkout", "-q", "main")
        (root / "b.txt").write_text("2")
        run("add", "-A")
        run("commit", "-q", "-m", "two")
        run("update-ref", "refs/remotes/origin/main", "main")
        run("checkout", "-q", "feature")
        self.assertTrue(pre_push.behind_main("origin/main", root))  # main has a commit that the feature branch lacks
        run("merge", "-q", "--no-edit", "origin/main")
        self.assertFalse(pre_push.behind_main("origin/main", root))


class PrGreenTests(unittest.TestCase):
    HEAD = "a" * 40
    OLD = "b" * 40

    def run_(self, name, conclusion="success", status="completed", sha=None):
        return {"name": name, "status": status, "conclusion": conclusion, "head_sha": sha or self.HEAD}

    def all_green(self):
        return [self.run_("plan"), self.run_("test (3.10, shard 1/3)"), self.run_("node", "skipped"), self.run_("result"),
                self.run_("Vercel", "failure")]  # a host's check is not a test

    def test_green_only_when_every_run_is_for_the_head_and_result_succeeded(self):
        ok, why = pr_green.verdict(self.HEAD, self.all_green())
        self.assertTrue(ok, why)

    def test_planted_fault_a_green_run_of_an_older_commit_is_not_green(self):
        runs = self.all_green()
        runs[1] = self.run_("test (3.10, shard 1/3)", sha=self.OLD)
        ok, why = pr_green.verdict(self.HEAD, runs)
        self.assertFalse(ok)
        self.assertIn("older commit", why)

    def test_a_run_still_going_a_failed_run_and_a_missing_result_are_not_green(self):
        self.assertIn("still running", pr_green.verdict(self.HEAD, self.all_green()[:3] + [self.run_("result", None, "in_progress")])[1])
        self.assertIn("failed: node", pr_green.verdict(self.HEAD, [self.run_("result"), self.run_("node", "failure")])[1])
        self.assertIn("`result` check is not there", pr_green.verdict(self.HEAD, [self.run_("plan")])[1])
        self.assertFalse(pr_green.verdict(self.HEAD, [])[0])
        self.assertFalse(pr_green.verdict(self.HEAD, [self.run_("result", "cancelled")])[0])

    def with_id(self, run, i):
        return dict(run, id=i)

    def test_the_newest_run_of_a_name_decides_a_skipped_draft_result_before_the_real_one_does_not_hide_it(self):
        # G-0004: a draft run left a skipped `result` on the same commit; the real run's `result` came later (a higher id) and passed
        runs = [self.with_id(self.run_("result", "skipped"), 1), self.with_id(self.run_("plan", "skipped"), 2),
                self.with_id(self.run_("plan"), 11), self.with_id(self.run_("test (3.10, shard 1/3)"), 12), self.with_id(self.run_("result"), 13)]
        ok, why = pr_green.verdict(self.HEAD, runs)
        self.assertTrue(ok, why)
        self.assertEqual(len(pr_green.newest(runs)), 3)

    def test_planted_fault_a_skipped_draft_result_that_is_newer_than_the_real_one_is_not_green(self):
        # the race of PR 217: the real run was cancelled by a newer skipped draft run, so the newest result is the skipped one
        runs = [self.with_id(self.run_("plan"), 21), self.with_id(self.run_("result", "failure"), 22),
                self.with_id(self.run_("plan", "skipped"), 31), self.with_id(self.run_("result", "skipped"), 32)]
        ok, why = pr_green.verdict(self.HEAD, runs)
        self.assertFalse(ok)
        self.assertIn("`result` did not finish with success", why)

    def test_an_older_cancelled_run_does_not_make_a_newer_passing_run_red_and_a_newer_failure_does(self):
        old_cancelled = self.with_id(self.run_("test (3.10, shard 1/3)", "cancelled"), 5)
        new_pass = self.with_id(self.run_("test (3.10, shard 1/3)"), 9)
        self.assertTrue(pr_green.verdict(self.HEAD, [old_cancelled, new_pass, self.with_id(self.run_("result"), 10)])[0])
        new_fail = self.with_id(self.run_("test (3.10, shard 1/3)", "failure"), 9)
        old_pass = self.with_id(self.run_("test (3.10, shard 1/3)"), 5)
        ok, why = pr_green.verdict(self.HEAD, [old_pass, new_fail, self.with_id(self.run_("result"), 10)])
        self.assertFalse(ok)
        self.assertIn("failed: test (3.10, shard 1/3)", why)

    def test_runs_with_no_id_keep_the_old_behaviour(self):
        self.assertEqual(len(pr_green.newest(self.all_green())), 5)

    def test_the_command_refuses_other_words(self):
        self.assertEqual(pr_green.main([]), 64)
        self.assertEqual(pr_green.main(["abc"]), 64)


class StatusPartsKeptTests(unittest.TestCase):
    def test_the_function_names_a_lost_part(self):
        self.assertEqual(missing_parts(["a.md", "b.md"], ["a.md"]), ["b.md"])
        self.assertEqual(missing_parts(["a.md"], ["a.md", "c.md"]), [])

    def test_every_status_part_of_main_is_still_here(self):
        r = subprocess.run(["git", "ls-tree", "-r", "--name-only", "origin/main", "--", "docs-parts/status-log"], cwd=REPO,
                           capture_output=True, text=True, check=False)
        if r.returncode != 0 or not r.stdout.strip():
            self.skipTest("origin/main is not in this clone: nothing to compare")
        base = [l for l in r.stdout.split("\n") if l]
        now = [str(p.relative_to(REPO)) for p in (REPO / "docs-parts" / "status-log").glob("*.md")]
        self.assertEqual(missing_parts(base, now), [], "a status part of main is gone from this branch: a row of the status log was lost")


if __name__ == "__main__":
    unittest.main()
