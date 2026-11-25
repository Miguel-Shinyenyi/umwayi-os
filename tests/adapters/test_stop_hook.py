"""B-0012, item 3: the Claude Code Stop hook (adapters/claude_code/stop_hook.py).

It keeps a session from ending its turn while the queue is low and a free task is pending, at most three times in a row, and lets it stop in
every other case: the kill switch on or unreadable, every pending task blocked, a queue that is not low, a bad input, another event, a
broken pr-queue.md. It fails OPEN (it only nudges; it is not a gate). Planted cases: the count of blocks, the reset, the fourth is let through.
"""
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from adapters.claude_code import stop_hook as sh
from umwayi import kill, logbook, taskqueue

REPO = Path(__file__).resolve().parent.parent.parent
HEAD = "| branch | title | order | stops | status | pr | head |\n|---|---|---|---|---|---|---|\n"
STOP = {"hook_event_name": "Stop", "session_id": "s1", "stop_hook_active": False}


class Base(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name)
        (self.root / "pr-queue.md").write_text("keep_ready: 2\n\n" + HEAD, encoding="utf-8")

    def task(self, title):
        taskqueue.add_once(self.root, "task", title, "", "2026-11-24")

    def run_hook(self, event=STOP, *extra, raw=None):
        out, err = io.StringIO(), io.StringIO()
        code = sh.main(["--root", str(self.root), *extra], io.StringIO(raw if raw is not None else json.dumps(event)), out, err)
        return code, out.getvalue(), err.getvalue()

    def counter(self, sid="s1"):
        p = self.root / ".umwayi" / "stop-hook" / sid
        return p.read_text(encoding="utf-8") if p.exists() else None


class BlockTests(Base):
    def test_a_low_queue_with_a_free_task_blocks_with_the_documented_json_and_the_queue_low_line(self):
        self.task("Build the next thing")
        code, out, err = self.run_hook()
        self.assertEqual(code, 0)
        doc = json.loads(out)
        self.assertEqual(sorted(doc), ["decision", "reason"])
        self.assertEqual(doc["decision"], "block")
        self.assertIn("queue low: 0 of 2 branches ready, 1 task(s) pending: build Build the next thing next.", doc["reason"])
        self.assertIn("Do not end the turn", doc["reason"])
        self.assertIn("(block 1 of 3)", doc["reason"])
        self.assertNotIn("Nothing is started", doc["reason"])
        self.assertEqual(self.counter(), "1")

    def test_planted_fault_it_blocks_three_times_in_a_row_and_the_fourth_stop_is_let_through(self):
        self.task("Build the next thing")
        blocks = [bool(self.run_hook()[1]) for _ in range(5)]
        self.assertEqual(blocks, [True, True, True, False, False])
        code, out, err = self.run_hook()
        self.assertEqual((code, out), (0, ""))
        self.assertIn("letting the session stop", err)

    def test_the_limit_can_be_set_from_1_to_10(self):
        self.task("Build the next thing")
        self.assertEqual([bool(self.run_hook(STOP, "--max-blocks", "1")[1]) for _ in range(3)], [True, False, False])

    def test_the_count_is_kept_per_session_and_is_deleted_when_the_queue_is_no_longer_low(self):
        self.task("Build the next thing")
        self.run_hook(STOP)
        self.run_hook(dict(STOP, session_id="s2"))
        self.assertEqual((self.counter("s1"), self.counter("s2")), ("1", "1"))
        (self.root / "pr-queue.md").write_text("keep_ready: 0\n\n" + HEAD, encoding="utf-8")  # no longer low
        self.assertEqual(self.run_hook()[1], "")
        self.assertIsNone(self.counter("s1"))
        self.assertEqual(self.counter("s2"), "1")

    def test_no_pr_queue_file_and_a_pending_task_is_low_too(self):
        (self.root / "pr-queue.md").unlink()
        self.task("Build the next thing")
        self.assertIn("block", self.run_hook()[1])


class LetStopTests(Base):
    def test_nothing_pending_or_enough_branches_ready_lets_the_session_stop(self):
        self.assertEqual(self.run_hook()[1:], ("", ""))
        self.task("Build the next thing")
        (self.root / "pr-queue.md").write_text("keep_ready: 1\n\n" + HEAD + "| a-branch | First | 1 | no | local | - | abc1234 |\n", encoding="utf-8")
        self.assertEqual(self.run_hook()[1], "")

    def test_when_every_pending_task_is_blocked_the_session_may_stop(self):
        self.task("One [blocked: an answer]")
        self.task("Two [blocked: a file]")
        self.assertEqual(self.run_hook()[1], "")
        self.task("A free task")
        self.assertIn("A free task", json.loads(self.run_hook()[1])["reason"])

    def test_the_kill_switch_on_lets_the_session_stop_and_so_does_one_that_cannot_be_read(self):
        self.task("Build the next thing")
        kill.turn_on(self.root, "2026-11-24")
        self.assertEqual(self.run_hook()[1], "")
        kill.turn_off(self.root, "2026-11-24")
        self.assertIn("block", self.run_hook()[1])

    def test_another_event_a_subagent_stop_and_bad_input_are_let_through(self):
        self.task("Build the next thing")
        for raw in (json.dumps({"hook_event_name": "SubagentStop", "session_id": "s1"}), json.dumps({"hook_event_name": "PreToolUse"}),
                    json.dumps([1]), "null", "{", "", "not json"):
            with self.subTest(raw=raw[:20]):
                self.assertEqual(self.run_hook(raw=raw)[:2], (0, ""))

    def test_a_broken_pr_queue_and_a_bad_argument_let_the_session_stop_and_never_exit_1_or_2(self):
        self.task("Build the next thing")
        (self.root / "pr-queue.md").write_text("| not | the | table |\n", encoding="utf-8")
        self.assertEqual(self.run_hook()[:2], (0, ""))
        for extra in (("--max-blocks", "0"), ("--max-blocks", "11"), ("--max-blocks", "x"), ("--bogus",)):
            with self.subTest(extra=extra):
                code, out, err = self.run_hook(STOP, *extra)
                self.assertEqual((code, out), (0, ""))

    def test_a_session_id_that_is_not_plain_is_counted_as_unknown(self):
        self.task("Build the next thing")
        self.run_hook(dict(STOP, session_id="../../etc/x"))
        self.assertEqual(self.counter("unknown"), "1")
        self.assertEqual(sorted(p.name for p in (self.root / ".umwayi" / "stop-hook").iterdir()), ["unknown"])

    def test_nothing_but_the_counter_file_is_written(self):
        self.task("Build the next thing")
        before = {p.name: p.read_bytes() for p in self.root.iterdir() if p.is_file()}
        self.run_hook()
        self.assertEqual({p.name: p.read_bytes() for p in self.root.iterdir() if p.is_file()}, before)


class ProcessTests(Base):
    def test_the_real_script_prints_the_json_on_stdout_exits_0_and_the_example_settings_point_at_it(self):
        self.task("Build the next thing")
        p = subprocess.run([sys.executable, str(REPO / "adapters" / "claude_code" / "stop_hook.py"), "--root", str(self.root)],
                           input=json.dumps(STOP), capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["decision"], "block")
        example = json.loads((REPO / "adapters" / "claude_code" / "stop-hook.example.json").read_text(encoding="utf-8"))
        cmd = example["hooks"]["Stop"][0]["hooks"][0]
        self.assertEqual(cmd["type"], "command")
        self.assertIn("adapters/claude_code/stop_hook.py --root", cmd["command"])

    def test_no_argument_prints_usage_and_exits_0(self):
        p = subprocess.run([sys.executable, str(REPO / "adapters" / "claude_code" / "stop_hook.py")], input="", capture_output=True, text=True,
                           timeout=60)
        self.assertEqual((p.returncode, p.stdout), (0, ""))
        self.assertIn("usage", p.stderr)


if __name__ == "__main__":
    unittest.main()
