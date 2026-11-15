"""Config and usage errors exit 64. Unexpected errors exit 2 in every command and never print their message."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from umwayi.cli import EXIT_CRASH, main
from umwayi.errors import ConfigError, UmwayiError, UsageError

REPO = Path(__file__).resolve().parent.parent
SECRET = "sk-live-TOPSECRET-crash-text"

QUEUE = (
    "# Queue\n\n| id | kind | title | status | recommendation | answer | answered |\n"
    "| --- | --- | --- | --- | --- | --- | --- |\n| Q-0001 | task | One | open | | | |\n"
)

# command line, and the function inside it that is made to crash
COMMANDS = [
    (["check", '{"type": "read"}'], "umwayi.cli.rules.check_and_log"),
    (["queue", "list"], "umwayi.cli.taskqueue.list_rows"),
    (["queue", "add", "--kind", "task", "x"], "umwayi.cli.taskqueue.add"),
    (["queue", "answer", "Q-0001", "--answer", "x"], "umwayi.cli.taskqueue.answer"),
    (["queue", "close", "Q-0001"], "umwayi.cli.taskqueue.close"),
    (["queue", "migrate"], "umwayi.cli.taskqueue.migrate"),
    (["archive", "move", "notes.md", "--lines", "1-1", "--reason", "r"], "umwayi.cli.archive.move"),
    (["archive", "verify"], "umwayi.cli.archive.verify"),
    (["memory", "bundle"], "umwayi.cli.load_bundle"),
    (["logbook", "verify"], "umwayi.cli.logbook.verify"),
    (["logbook", "seal", "--by", "me"], "umwayi.cli.logbook.seal"),
    (["run", "jobs.yaml", "--job", "x"], "umwayi.cli.jobs.run"),
    (["report", "--since", "2026-11-01"], "umwayi.cli.report.make"),
    (["publish-draft", "drafts/a.md"], "umwayi.cli.publish.publish"),
    (["steward"], "umwayi.cli.steward.run"),
    (["social", "draft", "a.md"], "umwayi.cli.social.draft"),
    (["workflow", "validate", "content-loop"], "umwayi.cli.workflow.validate_file"),
    (["workflow", "run", "content-loop"], "umwayi.cli.workflow.run"),
    (["kill", "on"], "umwayi.cli.kill.turn_on"),
    (["kill", "off"], "umwayi.cli.kill.turn_off"),
    (["kill", "status"], "umwayi.cli.kill.state"),
    (["view", "snapshot"], "umwayi.cli.view.snapshot"),
    (["feedback", "export"], "umwayi.cli.feedback.export"),
    (["serve"], "umwayi.serve.run"),
    (["serve", "token", "status"], "umwayi.cli.servetoken.status"),
    (["serve", "token", "revoke"], "umwayi.cli.servetoken.revoke"),
    (["goal", "docs", "build"], "umwayi.cli.goaldocs.build"),
    (["goal", "docs", "check"], "umwayi.cli.goaldocs.check"),
    (["goal", "start", "Build the thing in small safe steps.", "--guide", "g", "--plan-budget-uu", "5"], "umwayi.goal.start"),
    (["goal", "show", "G-0001"], "umwayi.goal.show"),
    (["goal", "approve", "G-0001", "--builder", "b", "--tester", "t", "--model", "m", "--effort", "high",
      "--task-budget-uu", "3", "--goal-budget-uu", "9"], "umwayi.goal.approve"),
    (["goal", "run", "G-0001"], "umwayi.goal.run"),
    (["goal", "status"], "umwayi.goal.status"),
    (["goal", "answer", "G-0001", "T-01", "yes"], "umwayi.goal.answer"),
    (["goal", "merged", "G-0001", "T-01"], "umwayi.goal.merged"),
    (["goal", "stop", "G-0001"], "umwayi.goal.stop"),
    (["goal", "report", "G-0001"], "umwayi.goal.report"),
    (["concerns", "check", "concerns.md"], "umwayi.cli.concerns.check_file"),
    (["routing", "check", "model-routing.md"], "umwayi.cli.routing.check_file"),
    (["stalls", "check", "events.json"], "umwayi.cli.stalls.check_file"),
]


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        old = sys.stderr
        sys.stderr = err
        try:
            with mock.patch("umwayi.cli._today", return_value="2026-11-07"):
                code = main(["--root", str(self.root), *argv], out=out)
        finally:
            sys.stderr = old
        return code, out.getvalue(), err.getvalue()


class CrashTests(Base):
    def setUp(self):
        super().setUp()
        (self.root / "umwayi.json").write_text(json.dumps({"memory_dir": "memory", "private_paths": []}))

    def test_every_command_turns_an_unexpected_error_into_exit_2(self):
        for argv, target in COMMANDS:
            for exc in (RuntimeError(SECRET), KeyError(SECRET), ZeroDivisionError(), KeyboardInterrupt()):
                with self.subTest(command=" ".join(argv[:2]), exc=type(exc).__name__):
                    with mock.patch(target, side_effect=exc):
                        code, out, err = self.cli(*argv)
                    self.assertEqual(code, EXIT_CRASH)
                    self.assertEqual(code, 2)
                    self.assertIn("stopped by an unexpected error", err)
                    self.assertIn(type(exc).__name__, err)
                    self.assertNotIn(SECRET, out + err)

    def test_a_crash_is_never_0_1_or_3(self):
        with mock.patch("umwayi.cli.rules.check_and_log", side_effect=RuntimeError("x")):
            self.assertNotIn(self.cli("check", '{"type": "read"}')[0], (0, 1, 3, 64))

    def test_a_known_refusal_still_exits_1(self):
        with mock.patch("umwayi.cli.taskqueue.list_rows", side_effect=UmwayiError("refused")):
            self.assertEqual(self.cli("queue", "list")[0], 1)

    def test_real_process_crash_exits_2(self):
        code = (
            "import sys\nfrom unittest import mock\nimport umwayi.cli as c\n"
            f"with mock.patch('umwayi.cli.taskqueue.list_rows', side_effect=RuntimeError({SECRET!r})):\n"
            f"    sys.exit(c.main(['--root', {str(self.root)!r}, 'queue', 'list']))\n"
        )
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           env=dict(os.environ, PYTHONPATH=str(REPO)))
        self.assertEqual(r.returncode, 2)
        self.assertNotIn(SECRET, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)


class ConfigAndUsageTests(Base):
    def test_config_error_is_a_usage_error(self):
        self.assertTrue(issubclass(ConfigError, UsageError))
        self.assertTrue(issubclass(UsageError, UmwayiError))

    def test_missing_or_bad_config_exits_64_in_every_command_that_reads_it(self):
        (self.root / "notes.md").write_text("some words\n", encoding="utf-8")
        (self.root / "drafts").mkdir()
        (self.root / "drafts" / "a.md").write_text("a draft\n", encoding="utf-8")
        (self.root / "a.md").write_text("---\ntitle: t\nlink: https://x.org\n---\n", encoding="utf-8")
        commands = [
            ["memory", "bundle"],
            ["archive", "move", "notes.md", "--lines", "1-1", "--reason", "r"],
            ["publish-draft", "drafts/a.md", "--approved-by", "me"],
            ["social", "draft", "a.md"],
        ]
        for config in (None, "{broken", '{"memory_dir": "memory"}', '{"memory_dir": "m", "private_paths": [], "x": 1}'):
            cfg = self.root / "umwayi.json"
            if config is None:
                cfg.unlink(missing_ok=True)
            else:
                cfg.write_text(config, encoding="utf-8")
            for argv in commands:
                with self.subTest(config=config, command=argv[0]):
                    code, out, err = self.cli(*argv)
                    self.assertEqual((code, out), (64, ""))
                    self.assertIn("config", err)

    def test_jobs_and_workflow_files_are_config(self):
        self.assertEqual(self.cli("run", "nope.yaml")[0], 64)
        (self.root / "bad.yaml").write_text("jobs: [\n", encoding="utf-8")
        self.assertEqual(self.cli("run", "bad.yaml")[0], 64)
        self.assertEqual(self.cli("workflow", "validate", "nope")[0], 64)

    def test_bad_argument_values_exit_64_and_change_nothing(self):
        (self.root / "queue.md").write_text(QUEUE, encoding="utf-8")
        (self.root / "umwayi.json").write_text(json.dumps({"memory_dir": "memory", "private_paths": []}))
        (self.root / "notes.md").write_text("some words\n", encoding="utf-8")
        cases = [
            ["queue", "add", "--kind", "task", "has | pipe"],
            ["queue", "add", "--kind", "task", ""],
            ["queue", "add", "--kind", "task", "ok", "--recommendation", "a|b"],
            ["queue", "answer", "Q-0001", "--answer", ""],
            ["queue", "answer", "q-1", "--answer", "x"],
            ["queue", "close", "nonsense"],
            ["archive", "move", "notes.md", "--lines", "1-1", "--reason", ""],
            ["archive", "move", "notes.md", "--start", "X", "--end", "X", "--reason", "r"],
            ["logbook", "seal", "--by", ""],
            ["kill", "on", "--reason", "two\nlines"],
        ]
        for argv in cases:
            with self.subTest(argv=argv):
                before = sorted(p.name for p in self.root.rglob("*"))
                code, out, _ = self.cli(*argv)
                self.assertEqual((code, out), (64, ""))
                self.assertEqual(sorted(p.name for p in self.root.rglob("*")), before)
        self.assertEqual((self.root / "queue.md").read_text(), QUEUE)

    def test_goal_has_only_docs_and_wrong_use_is_64_and_changes_nothing(self):
        (self.root / "umwayi.json").write_text(json.dumps({"memory_dir": "memory", "private_paths": []}))
        for argv in (["goal"], ["goal", "docs"], ["goal", "start", "x"], ["goal", "docs", "build", "x"]):
            with self.subTest(argv=argv):
                before = sorted(p.name for p in self.root.rglob("*"))
                code, out, _ = self.cli(*argv)
                self.assertEqual((code, out), (64, ""))
                self.assertEqual(sorted(p.name for p in self.root.rglob("*")), before)

    def test_goal_docs_is_2_and_never_1_or_3_on_a_refusal(self):
        for cmd in ("build", "check"):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.cli("goal", "docs", cmd)[0], 2)  # no docs-parts here: refused, nothing written

    def test_data_problems_stay_exit_1(self):
        (self.root / "queue.md").write_text(QUEUE, encoding="utf-8")
        self.assertEqual(self.cli("queue", "answer", "Q-0099", "--answer", "x")[0], 1)  # well formed, not there
        (self.root / "queue.md").write_text("broken\n", encoding="utf-8")
        self.assertEqual(self.cli("queue", "list")[0], 1)  # a data file, not config


if __name__ == "__main__":
    unittest.main()
