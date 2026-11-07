"""Layers 2, 3 and 4 all write the logbook through the same checked append."""

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import entry_text, write_sealed_logbook
from umwayi import logbook
from umwayi.cli import main
from umwayi.logbook import parse

OLD_QUEUE = (
    "# Queue\n\n| id | kind | title | status | recommendation | answered |\n"
    "| --- | --- | --- | --- | --- | --- |\n| Q-0001 | task | Old | open | | |\n"
)
RULES = "rules:\n  - id: r\n    title: t\n    text: t\n    verdict: yes\n    matchers:\n      type: read\n"


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "umwayi.json").write_text(json.dumps({"memory_dir": "memory", "private_paths": []}))
        (self.root / "notes.md").write_text("# Notes\nkeep one\nold alpha beta\nkeep two\n", encoding="utf-8")
        (self.root / "rules.yaml").write_text(RULES, encoding="utf-8")
        self.log = self.root / "LOGBOOK.md"
        p = mock.patch.object(logbook, "LOCK_WAIT_SECONDS", 0)
        p.start()
        self.addCleanup(p.stop)

    def run_cli(self, *argv, clock="2026-11-07"):
        out, err = io.StringIO(), io.StringIO()
        old = sys.stderr
        sys.stderr = err
        try:
            with mock.patch("umwayi.cli._today", return_value=clock):
                code = main(["--root", str(self.root), *argv], out=out)
        finally:
            sys.stderr = old
        return code, out.getvalue(), err.getvalue()

    def snap(self):
        return {os.path.relpath(os.path.join(dp, f), self.root): Path(dp, f).read_bytes()
                for dp, _d, fs in os.walk(self.root) for f in fs}

    # one command per layer 3 and 4 write path, each as (argv, setup)
    def write_commands(self):
        (self.root / "queue.md").write_text(
            "# Queue\n\n| id | kind | title | status | recommendation | answer | answered |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n| Q-0001 | task | Old | open | | | |\n", encoding="utf-8")
        return [
            ("queue add", ["queue", "add", "--kind", "task", "New"]),
            ("queue answer", ["queue", "answer", "Q-0001", "--answer", "yes"]),
            ("queue close", ["queue", "close", "Q-0001"]),
            ("archive move", ["archive", "move", "notes.md", "--lines", "3-3", "--reason", "r"]),
        ]


class TamperChecksReachEveryLayerTests(Base):
    def each(self, prepare, fragment, date_arg=()):
        for name, argv in self.write_commands():
            with self.subTest(command=name):
                prepare()
                before = self.snap()
                code, out, err = self.run_cli(*argv, *date_arg)
                self.assertEqual((code, out), (1, ""), err)
                self.assertIn(fragment, err)
                self.assertEqual(self.snap(), before, f"{name} left changes behind")

    def test_hand_edit_of_an_earlier_logbook_line(self):
        def prepare():
            write_sealed_logbook(self.root, "# Logbook\n" + entry_text(date="2026-01-01"))
            self.log.write_text(self.log.read_text().replace("- Added: x", "- Added: EDITED"), encoding="utf-8")
        self.each(prepare, "does not match its recorded hash")

    def test_deleted_logbook_line(self):
        def prepare():
            write_sealed_logbook(self.root, "# Logbook\n" + entry_text(date="2026-01-01"))
            lines = self.log.read_text().split("\n")
            del lines[6]
            self.log.write_text("\n".join(lines), encoding="utf-8")
        self.each(prepare, "does not match its recorded hash")

    def test_no_hash_record(self):
        self.each(lambda: self.log.write_text("# Logbook\n" + entry_text(date="2026-01-01"), encoding="utf-8"),
                  "no hash record")

    def test_a_refusal_says_the_change_was_undone_and_why(self):
        self.log.write_text("# Logbook\n" + entry_text(date="2026-01-01"), encoding="utf-8")
        self.write_commands()
        _, _, err = self.run_cli("queue", "add", "--kind", "task", "x")
        self.assertIn("the logbook write failed, so the queue change was undone", err)
        self.assertIn("umwayi logbook seal", err)
        _, _, err = self.run_cli("archive", "move", "notes.md", "--lines", "3-3", "--reason", "r")
        self.assertIn("the logbook write failed, so the move was undone", err)

    def test_backwards_date(self):
        write_sealed_logbook(self.root, "# Logbook\n" + entry_text(date="2026-06-01"))
        self.each(lambda: write_sealed_logbook(self.root, "# Logbook\n" + entry_text(date="2026-06-01")),
                  "before the date of the last entry", date_arg=("--date", "2026-05-31"))

    def test_lock_held(self):
        def prepare():
            write_sealed_logbook(self.root, "# Logbook\n" + entry_text(date="2026-01-01"))
            (self.root / ".umwayi" / "logbook.lock").write_text("1\n")
        self.each(prepare, "another umwayi command")

    def test_malformed_logbook(self):
        self.each(lambda: write_sealed_logbook(self.root, "# Logbook\nstray\n"), "format problem")

    def test_migrate_is_checked_too(self):
        (self.root / "queue.md").write_text(OLD_QUEUE, encoding="utf-8")
        write_sealed_logbook(self.root, "# Logbook\n" + entry_text(date="2026-01-01"))
        self.log.write_text("changed", encoding="utf-8")
        before = self.snap()
        code, _, err = self.run_cli("queue", "migrate")
        self.assertEqual(code, 1)
        self.assertIn("does not match", err)
        self.assertEqual(self.snap(), before)


class WholeSystemTests(Base):
    def test_every_layer_writes_a_logbook_that_verifies(self):
        steps = [
            ["queue", "add", "--kind", "task", "One"],
            ["queue", "add", "--kind", "decision", "Two", "--recommendation", "yes"],
            ["queue", "answer", "Q-0002", "--answer", "go"],
            ["queue", "close", "Q-0001"],
            ["archive", "move", "notes.md", "--lines", "3-3", "--reason", "old"],
            ["check", '{"type": "read", "secret": "sk-live-TOPSECRET"}'],
        ]
        for argv in steps:
            code, _, err = self.run_cli(*argv)
            self.assertEqual(code, 0, err)
        # a queue.md must exist for the queue steps; the first add created it
        entries, problems = parse(self.log.read_text(encoding="utf-8"))
        self.assertEqual(problems, [])
        self.assertEqual([p.entry.source for p in entries], [
            "umwayi queue add", "umwayi queue add", "umwayi queue answer", "umwayi queue close",
            "umwayi archive move", "umwayi check"])
        self.assertEqual(logbook.verify(self.root).problems, [])
        self.assertNotIn("TOPSECRET", self.log.read_text(encoding="utf-8"))
        code, out, _ = self.run_cli("logbook", "verify")
        self.assertEqual(code, 0)
        self.assertIn("ok: 6 entries", out)

    def test_migrate_logs_and_verifies(self):
        (self.root / "queue.md").write_text(OLD_QUEUE, encoding="utf-8")
        self.assertEqual(self.run_cli("queue", "migrate")[0], 0)
        self.assertEqual(logbook.verify(self.root).problems, [])

    def test_a_hand_edit_is_caught_by_verify_and_blocks_every_layer_until_sealed(self):
        self.assertEqual(self.run_cli("queue", "add", "--kind", "task", "One")[0], 0)
        self.log.write_text(self.log.read_text().replace("One", "Uno"), encoding="utf-8")
        self.assertEqual(self.run_cli("logbook", "verify")[0], 1)
        self.assertEqual(self.run_cli("queue", "add", "--kind", "task", "Two")[0], 1)
        self.assertEqual(self.run_cli("archive", "move", "notes.md", "--lines", "3-3", "--reason", "r")[0], 1)
        self.assertEqual(self.run_cli("check", '{"type": "read"}')[0], 3)
        self.assertEqual(self.run_cli("logbook", "seal", "--by", "owner")[0], 0)
        self.assertEqual(self.run_cli("logbook", "verify")[0], 0)
        self.assertEqual(self.run_cli("queue", "add", "--kind", "task", "Two")[0], 0)
        self.assertEqual(self.run_cli("check", '{"type": "read"}')[0], 0)


if __name__ == "__main__":
    unittest.main()
