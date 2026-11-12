"""W20, Part D: tools/affected_tests.py gives the same answer as the CI decider for the same changed files, because it
calls the same function; it reads the working tree against a base; and it fails closed."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_ci_plan import ASSIGN, DATA, git, table
from tools import affected_tests, ci_plan

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "tools" / "affected_tests.py"


def cli(*args, cwd=REPO):
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True)


class SameAnswerTests(unittest.TestCase):
    def test_every_row_of_the_ci_table_gives_the_same_plan(self):
        rows = [(n, p) for n, p, _ in table() if not isinstance(p, tuple)]
        self.assertGreater(len(rows), 20)
        for name, paths in rows:
            want = ci_plan.dumps(ci_plan.build_plan(paths, "pull_request", DATA, ASSIGN))
            self.assertEqual(ci_plan.dumps(affected_tests.plan_for(paths)), want, name)

    def test_the_command_line_prints_the_ci_plan_for_the_same_files(self):
        for paths in (["ui/src/main.js"], ["umwayi/cli.py"], ["docs/queue.md", "site/app/page.js"], ["unknown.bin"],
                      ["ui/src/a.js", "docs/a.js"], [".github/workflows/ci.yml"]):
            r = cli("--json", "--files", *paths)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.strip(), ci_plan.dumps(ci_plan.build_plan(paths, "pull_request", DATA, ASSIGN)), paths)

    def test_it_has_no_rules_of_its_own(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("ci_plan.build_plan(", text)
        for word in ("routes", "reads_match", "startswith("):
            self.assertNotIn(word, text.split('"""')[2], word)

    def test_the_modules_are_the_selected_files(self):
        plan = affected_tests.plan_for(["ui/src/main.js"])
        mods = ci_plan.test_modules(plan, DATA)
        self.assertEqual(mods, sorted(f[:-3].replace("/", ".") for f in plan["python"]["files"]))
        self.assertIn("tests.test_ui_package", mods)
        self.assertIsNone(ci_plan.test_modules(affected_tests.plan_for(["umwayi/cli.py"]), DATA))
        self.assertEqual(ci_plan.node_dirs(affected_tests.plan_for(["umwayi/cli.py"])), [])
        self.assertEqual(ci_plan.node_dirs(affected_tests.plan_for(["ui/src/main.js"])), ["ui", "site"])


class FailClosedTests(unittest.TestCase):
    def test_unknown_path_says_full_suite(self):
        r = cli("--files", "mystery.bin")
        self.assertIn("FULL SUITE", r.stdout)
        self.assertIn("all test modules", r.stdout)

    def test_workflow_map_and_tools_change_say_full_suite(self):
        for p in (".github/workflows/ci.yml", "tools/ci_map.json", "tools/ci_plan.py", "tools/affected_tests.py"):
            self.assertIn("FULL SUITE", cli("--files", p).stdout, p)

    def test_an_unreadable_base_means_everything(self):
        r = cli("--base", "no-such-ref-anywhere")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("FULL SUITE", r.stdout)
        self.assertIn("could not be read", r.stdout)

    def test_a_ui_change_does_not_say_full_suite(self):
        r = cli("--files", "ui/src/main.js")
        self.assertNotIn("FULL SUITE", r.stdout)
        self.assertIn("tests.test_ui_package", r.stdout)
        self.assertIn("not run here", r.stdout)

    def test_usage_errors_exit_64(self):
        for args in (["--bogus"], ["--base"], ["--python", "python3"], ["--files", "a", "--files", "b"]):
            self.assertEqual(cli(*args).returncode, 64, args)


class WorkingTreeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="umwayi-affected-")
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name)
        git(self.d, "init", "-q", "-b", "main")
        (self.d / "a.txt").write_text("a\n" * 20)
        (self.d / "ui").mkdir()
        (self.d / "ui" / "x.js").write_text("x\n" * 20)
        git(self.d, "add", "-A")
        git(self.d, "commit", "-q", "-m", "one")
        git(self.d, "checkout", "-q", "-b", "feature")

    def test_commits_edits_and_new_files_are_all_seen(self):
        (self.d / "b.txt").write_text("b\n")
        git(self.d, "add", "b.txt")
        git(self.d, "commit", "-q", "-m", "two")
        (self.d / "a.txt").write_text("changed\n")
        (self.d / "new.txt").write_text("new\n")
        got = ci_plan.local_changed_paths("main", self.d)
        self.assertEqual(sorted(set(got)), ["a.txt", "b.txt", "new.txt"])

    def test_a_rename_across_areas_shows_both_sides(self):
        git(self.d, "mv", "ui/x.js", "a2.js")
        got = ci_plan.local_changed_paths("main", self.d)
        self.assertEqual(sorted(set(got)), ["a2.js", "ui/x.js"])

    def test_nothing_changed_is_an_empty_list_which_runs_everything(self):
        got = ci_plan.local_changed_paths("main", self.d)
        self.assertEqual(got, [])
        self.assertTrue(affected_tests.plan_for(got)["full"])

    def test_a_missing_base_is_none(self):
        self.assertIsNone(ci_plan.local_changed_paths("nope", self.d))
        self.assertIsNone(ci_plan.local_changed_paths("--output=x", self.d))

    def test_a_folder_that_is_not_a_repository_is_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(ci_plan.local_changed_paths("main", d))


class RunTests(unittest.TestCase):
    def plan(self, files, node=False):
        p = affected_tests.plan_for(["docs/queue.md"])
        p["python"]["files"] = files
        p["node"] = node
        return p

    def test_run_passes_for_a_small_module(self):
        self.assertEqual(affected_tests.run_all(self.plan(["tests/test_ci_workflow.py"]), DATA, [sys.executable]), 0)

    def test_run_fails_when_the_interpreter_is_missing(self):
        self.assertEqual(affected_tests.run_all(self.plan(["tests/test_ci_workflow.py"]), DATA, ["/no/such/python"]), 2)

    def test_run_fails_when_a_module_does_not_exist(self):
        self.assertEqual(affected_tests.run_all(self.plan(["tests/test_does_not_exist.py"]), DATA, [sys.executable]), 2)


if __name__ == "__main__":
    unittest.main()
