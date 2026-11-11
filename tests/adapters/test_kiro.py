"""The Kiro adapter, run as a real child process, the way a Kiro command action runs it."""

import json
import time
import unittest

from tests.adapters.support import REPO, SECRET, AdapterCase

HOOK = REPO / "adapters" / "kiro" / "hook.py"
RULES = REPO / "adapters" / "kiro" / "rules.example.yaml"


def event(tool, tool_input):
    return {"hook_event_name": "PreToolUse", "cwd": "/tmp", "session_id": "abc123", "tool_name": tool,
            "tool_input": tool_input}


READ = event("read_file", {"path": "/p/a.py"})
RM = event("execute_bash", {"command": "rm -rf /p"})
WRITE = event("fs_write", {"path": "/p/a.py", "text": "x"})
MCP = event("mcp_postgres_query", {"sql": "SELECT 1"})


class KiroCase(AdapterCase):
    HOOK, RULES = HOOK, RULES

    def hook(self, payload, **kw):
        code, out, err = self.raw(payload, **kw)
        # the contract, for every run: exit 0 (allow, nothing on stdout) or 2 (deny, reason on stderr); never 1
        self.assertIn(code, (0, 2), f"exit {code}\n{out}\n{err}")
        if code == 0:
            self.assertEqual(out, "", "allow prints nothing: Kiro adds stdout to the agent's context")
        else:
            self.assertTrue(err.strip(), "a deny always says why on stderr")
            self.assertEqual(out, "")
        self.assertNotIn(SECRET, out + err)
        self.assertNotIn("Traceback", err)
        return code, out, err


class AnswerTests(KiroCase):
    def test_yes_allows(self):
        self.assertEqual(self.hook(READ), (0, "", ""))

    def test_no_denies_with_exit_2(self):
        code, _, err = self.hook(RM)
        self.assertEqual(code, 2)
        self.assertIn("umwayi: No (rule kiro-no-destroy)", err)
        self.assertEqual(self.queue_rows(), [])  # a No adds no queue item

    def test_ask_me_first_is_deny_plus_one_queue_item(self):
        code, _, err = self.hook(WRITE)
        self.assertEqual(code, 2)
        self.assertIn("Kiro has no ask, so this call is denied.", err)
        self.assertIn("Added Q-0001 (decision): Kiro asks first: may it do tool_fs_write?", err)
        rows = self.queue_rows()
        self.assertEqual(len(rows), 1)
        self.assertIn("| decision | Kiro asks first: may it do tool_fs_write? | open |", rows[0])
        self.assertIn("Answering this item does not allow the call.", rows[0])

    def test_no_second_queue_item_while_one_is_open(self):
        for _ in range(3):
            code, _, err = self.hook(WRITE)
            self.assertEqual(code, 2)
        self.assertEqual(len(self.queue_rows()), 1)
        self.assertIn("Already open, nothing added: Q-0001", err)
        self.assertEqual(len(self.queue_rows()), 1)
        self.hook(MCP)  # another type: its own item
        self.assertEqual(len(self.queue_rows()), 2)
        self.assertEqual(self.umwayi("queue", "answer", "Q-0001", "--answer", "seen", "--revisit-if", "none").returncode, 0)
        self.hook(WRITE)  # once answered, the next ask adds a new item
        self.assertEqual(len(self.queue_rows()), 3)

    def test_a_queue_that_cannot_be_written_still_denies(self):
        (self.root / "queue.md").write_text("broken\n")
        code, _, err = self.hook(WRITE)
        self.assertEqual(code, 2)
        self.assertIn("warning: the queue item could not be added", err)
        self.assertEqual((self.root / "queue.md").read_text(), "broken\n")

    def test_input_fields_are_sent_with_a_prefix_and_cannot_replace_type(self):
        self.assertEqual(self.hook(event("read_file", {"path": "/p", "type": "tool_execute_bash"}))[0], 0)
        self.assertEqual(self.hook(event("execute_bash", {"command": "ls", "platform": "other"}))[0], 2)  # Ask me first

    def test_unknown_tools_and_mcp_are_denied_with_a_queue_item(self):
        self.assertEqual(self.hook(MCP)[0], 2)
        self.assertEqual(self.hook(event("brand_new_tool", {}))[0], 2)
        self.assertEqual(len(self.queue_rows()), 2)


class FailClosedTests(KiroCase):
    def test_a_broken_or_missing_rules_file_denies_without_a_queue_item(self):
        rules = self.root / "rules.yaml"
        for name, setup in {"not yaml": lambda: rules.write_text("rules: [\n"), "missing": lambda: rules.unlink(),
                            "bad verdict": lambda: rules.write_text("rules:\n  - id: a\n    title: t\n    text: t\n    verdict: maybe\n")}.items():
            with self.subTest(rules=name):
                rules.write_text(RULES.read_text())
                setup()
                for p in (READ, RM, WRITE):
                    code, _, err = self.hook(p)
                    self.assertEqual(code, 2)
                    self.assertIn("rules.yaml could not be used", err)
        self.assertEqual(self.queue_rows(), [])

    def test_a_crash_inside_the_adapter_blocks(self):
        for target in ("adapters.common.umwayi_gate:decide", "adapters.common.umwayi_gate:generic_action",
                       "adapters.common.umwayi_gate:run_check", "adapters.common.umwayi_gate:read_hook_input",
                       "adapters.common.umwayi_gate:parse_args", "adapters.common.umwayi_gate:add_queue_item"):
            for effect in ("crash", "interrupt"):
                with self.subTest(target=target, effect=effect):
                    code, _, err = self.hook(WRITE, fault=f"{target}:{effect}")
                    self.assertEqual(code, 2)
                    self.assertIn("blocked by an unexpected error", err)

    def test_a_crash_inside_umwayi_blocks(self):
        for target in ("umwayi.rules:decide", "umwayi.rules:load_rules", "umwayi.logbook:render"):
            with self.subTest(target=target):
                self.assertEqual(self.hook(READ, fault=f"{target}:crash")[0], 2)
        code, _, err = self.hook(WRITE, fault="umwayi.taskqueue:add_once:crash")  # the queue add crashes
        self.assertEqual(code, 2)
        self.assertIn("warning: the queue item could not be added", err)

    def test_bad_input_blocks(self):
        cases = ["{not json", "", "  \n", [1], '"x"', b"\xff\xfe", {"hook_event_name": "PreToolUse", "tool_input": {}},
                 event(5, {}), event("", {}), event("read_file", "a.py"), {**READ, "hook_event_name": "PostToolUse"},
                 {k: v for k, v in READ.items() if k != "hook_event_name"}, b'{"x": "' + b"a" * 1_000_001 + b'"}']
        for payload in cases:
            with self.subTest(payload=str(payload)[:30]):
                self.assertEqual(self.hook(payload)[0], 2)
        self.assertEqual(self.entries(), [])

    def test_a_missing_root_is_refused_by_name(self):
        code, _, err = self.hook(READ, args=[])
        self.assertEqual(code, 2)
        self.assertIn("umwayi hook: blocked, --root is required", err)
        self.assertNotIn("unexpected error", err)

    def test_bad_arguments_block(self):
        for args in ([], ["--root"], ["--root", str(self.tmp / "nope")], ["--root", str(self.root), "--timeout", "x"],
                     ["--root", str(self.root), "--allow"], ["--help"], ["--root", str(self.root), "--no-ask"]):
            with self.subTest(args=args):
                self.assertEqual(self.hook(READ, args=args)[0], 2)

    def test_a_timeout_blocks_in_time(self):
        start = time.monotonic()
        code, _, err = self.hook(READ, args=["--root", str(self.root), "--timeout", "1"], fault="umwayi.rules:load_rules:hang")
        self.assertLess(time.monotonic() - start, 10)
        self.assertEqual(code, 2)
        self.assertIn("did not answer within 1 seconds", err)

    def test_umwayi_not_found_blocks(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        self.assertEqual(self.hook(READ, args=["--root", str(self.root), "--umwayi-src", str(empty)],
                                   pythonpath=[str(self.site)])[0], 2)


class KillSwitchTests(KiroCase):
    def test_on_or_unknown_denies_everything_without_a_queue_item(self):
        self.kill_on()
        for p in (READ, WRITE, MCP):
            code, _, err = self.hook(p)
            self.assertEqual(code, 2)
            self.assertIn("the kill switch is on", err)
        self.assertEqual(self.queue_rows(), [])
        self.assertIn("- Added: The kill switch gave No; action type: tool_read_file", self.added_lines())
        self.assertTrue(any("kill switch: on" in l for l in self.checked_lines()))
        self.kill_off()
        self.assertEqual(self.hook(READ)[0], 0)
        self.kill_unknown()
        code, _, err = self.hook(READ)
        self.assertEqual(code, 2)
        self.assertIn("kill switch", err.lower())


class LogbookTests(KiroCase):
    def test_one_entry_per_check_and_verify_stays_ok(self):
        payloads = [READ, RM, READ, event("execute_bash", {"command": f"curl -H 'X: {SECRET}' x"})]
        for n, p in enumerate(payloads, 1):
            self.hook(p)
            self.assertEqual(len([e for e in self.entries() if e == "- Source: umwayi check"]), n)
        v = self.umwayi("logbook", "verify")
        self.assertEqual(v.returncode, 0, v.stdout)
        text = self.log.read_text()
        self.assertNotIn(SECRET, text)
        self.assertNotIn("rm -rf", text)


if __name__ == "__main__":
    unittest.main()
