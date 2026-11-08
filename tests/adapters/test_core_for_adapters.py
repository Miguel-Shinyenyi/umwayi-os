"""The two core options the adapters use: check --kill-switch and queue add --if-not-open."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RULES = "rules:\n  - id: ok-read\n    title: t\n    text: Reading is fine.\n    verdict: yes\n    matchers:\n      type: tool_read\n"
TITLE = "Kiro asks first: may it do tool_fs_write?"


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "rules.yaml").write_text(RULES)

    def u(self, *args):
        env = dict(os.environ, PYTHONPATH=str(REPO))
        return subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), *args],
                              capture_output=True, text=True, env=env)

    def log(self):
        p = self.root / "LOGBOOK.md"
        return p.read_text() if p.exists() else ""


class KillSwitchFlagTests(Base):
    def check(self, *extra):
        r = self.u("check", '{"type": "tool_read"}', "--json", *extra)
        return r.returncode, json.loads(r.stdout)

    def test_json_always_reports_the_kill_switch(self):
        self.assertEqual(self.check()[1]["kill_switch"], "off")
        self.assertEqual(self.u("kill", "on").returncode, 0)
        self.assertEqual(self.check()[1]["kill_switch"], "on")

    def test_without_the_flag_the_owner_check_is_unchanged(self):
        self.u("kill", "on")
        code, data = self.check()
        self.assertEqual((code, data["answer"]), (0, "Yes"))

    def test_with_the_flag_on_or_unknown_is_no_and_logged(self):
        self.u("kill", "on")
        code, data = self.check("--kill-switch")
        self.assertEqual((code, data["answer"], data["rule_id"], data["logged"]), (2, "No", None, True))
        self.assertIn("The kill switch is on", data["reason"])
        self.assertIn("- Added: The kill switch gave No; action type: tool_read", self.log())
        self.assertIn("kill switch: on", self.log())
        self.u("kill", "off")
        code, data = self.check("--kill-switch")
        self.assertEqual((code, data["answer"]), (0, "Yes"))
        self.assertIn("kill switch: off", self.log())
        import shutil
        shutil.rmtree(self.root / ".umwayi")
        (self.root / ".umwayi").write_text("x")
        code, data = self.check("--kill-switch")
        self.assertEqual((code, data["answer"], data["kill_switch"]), (2, "No", "unknown"))

    def test_the_text_answer_too(self):
        self.u("kill", "on")
        r = self.u("check", '{"type": "tool_read"}', "--kill-switch")
        self.assertEqual(r.returncode, 2)
        self.assertTrue(r.stdout.startswith("No\nRule: (none)\nReason: The kill switch is on"))


class IfNotOpenTests(Base):
    def add(self, title=TITLE, kind="decision"):
        return self.u("queue", "add", "--kind", kind, title, "--recommendation", "r", "--if-not-open")

    def rows(self):
        q = self.root / "queue.md"
        return [l for l in q.read_text().splitlines() if l.startswith("| Q-")] if q.exists() else []

    def test_adds_once_while_open(self):
        r = self.add()
        self.assertEqual((r.returncode, r.stdout.strip()), (0, f"Added Q-0001 (decision): {TITLE}"))
        r = self.add()
        self.assertEqual((r.returncode, r.stdout.strip()), (0, f"Already open, nothing added: Q-0001 (decision): {TITLE}"))
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.log().count("- Source: umwayi queue add"), 1)  # no entry when nothing changes

    def test_answered_or_closed_items_and_other_kinds_do_not_count(self):
        self.add()
        self.add(kind="task")
        self.assertEqual(len(self.rows()), 2)
        self.u("queue", "answer", "Q-0001", "--answer", "x")
        self.add()
        self.u("queue", "close", "Q-0003")
        self.add()
        self.assertEqual(len(self.rows()), 4)

    def test_without_the_flag_it_adds_every_time(self):
        self.u("queue", "add", "--kind", "decision", TITLE)
        self.u("queue", "add", "--kind", "decision", TITLE)
        self.assertEqual(len(self.rows()), 2)

    def test_refusals(self):
        self.assertEqual(self.add(title="a | b").returncode, 64)
        self.assertEqual(self.add(title="").returncode, 64)
        (self.root / "queue.md").write_text("broken\n")
        self.assertEqual(self.add().returncode, 1)
        self.assertEqual((self.root / "queue.md").read_text(), "broken\n")


class NoPlatformFilesTests(unittest.TestCase):
    def test_no_settings_or_hook_files_are_in_the_repo(self):
        self.assertFalse((REPO / ".claude").exists())
        self.assertFalse((REPO / ".kiro" / "hooks").exists())
        self.assertEqual(sorted(p.name for p in (REPO / ".kiro").iterdir()), ["specs", "steering"])


if __name__ == "__main__":
    unittest.main()
