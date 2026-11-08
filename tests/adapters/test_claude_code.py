"""The Claude Code adapter, run as a real child process, exactly as Claude Code runs it.

Faults are made by a sitecustomize.py that patches one function in the child
process only (the adapter, or the umwayi check it starts), never in the code.
"""

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / "adapters" / "claude_code" / "hook.py"
EXAMPLE_RULES = REPO / "adapters" / "claude_code" / "rules.example.yaml"
SECRET = "sk-live-ADAPTER-TEST-SECRET"

SITECUSTOMIZE = r'''
import os
fault = os.environ.get("UMWAYI_FAULT")
if fault:
    import importlib, time
    module, name, effect = fault.split(":")
    try:
        mod = importlib.import_module(module)
    except ImportError:
        mod = None
    if mod is not None:
        real = getattr(mod, name)
        def patched(*a, **k):
            if effect == "crash":
                raise RuntimeError(os.environ.get("UMWAYI_FAULT_TEXT", "injected"))
            if effect == "interrupt":
                raise KeyboardInterrupt
            if effect == "hang":
                time.sleep(30)
            return real(*a, **k)
        setattr(mod, name, patched)
'''


def call(tool, tool_input, **extra):
    return {"session_id": "s1", "transcript_path": "/tmp/t.jsonl", "cwd": "/tmp", "permission_mode": "default",
            "hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input,
            "tool_use_id": "toolu_1", **extra}


READ = call("Read", {"file_path": "/home/me/project/a.py"})
RM = call("Bash", {"command": "rm -rf /home/me/project", "description": "clean"})
WRITE = call("Write", {"file_path": "/home/me/project/a.py", "content": "print(1)\n"})
MCP = call("mcp__github__create_issue", {"title": "x"})


class AdapterBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="umwayi-adapter-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.root = self.tmp / "home"
        self.root.mkdir()
        shutil.copy(EXAMPLE_RULES, self.root / "rules.yaml")
        self.site = self.tmp / "site"
        self.site.mkdir()
        (self.site / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
        self.log = self.root / "LOGBOOK.md"

    def hook(self, payload, args=None, fault=None, pythonpath=None, timeout=60):
        """Run the hook as Claude Code does: JSON on stdin, read stdout, stderr and the exit code."""
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "UMWAYI_FAULT")}
        env["PYTHONPATH"] = os.pathsep.join(pythonpath if pythonpath is not None else [str(self.site), str(REPO)])
        if fault:
            env["UMWAYI_FAULT"] = fault
            env["UMWAYI_FAULT_TEXT"] = SECRET
        if isinstance(payload, (dict, list)):
            data = json.dumps(payload).encode("utf-8")
        elif isinstance(payload, str):
            data = payload.encode("utf-8")
        else:
            data = payload
        argv = args if args is not None else ["--root", str(self.root)]
        r = subprocess.run([sys.executable, str(HOOK), *argv], input=data, capture_output=True,
                           env=env, cwd=self.tmp, timeout=timeout)
        out, err = r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")
        # the contract, for every single run: never exit 1, and only 0 with one JSON decision or 2
        self.assertIn(r.returncode, (0, 2), f"exit {r.returncode}\n{out}\n{err}")
        if r.returncode == 0:
            decision = json.loads(out)  # exactly one JSON object
            self.assertEqual(set(decision), {"hookSpecificOutput"})
            hso = decision["hookSpecificOutput"]
            self.assertEqual(hso["hookEventName"], "PreToolUse")
            self.assertIn(hso["permissionDecision"], ("allow", "deny", "ask"))
            self.assertIsInstance(hso["permissionDecisionReason"], str)
        else:
            self.assertEqual(out, "", "exit 2 must not print a decision")
            self.assertTrue(err.startswith("umwayi hook: blocked"), err)
        self.assertNotIn(SECRET, out + err)
        self.assertNotIn("Traceback", err)
        return r.returncode, out, err

    def decision(self, result):
        code, out, _ = result
        return json.loads(out)["hookSpecificOutput"]["permissionDecision"] if code == 0 else "blocked"

    def assert_blocks(self, result):
        """Blocked: exit 2, or a deny decision. Never allow or ask."""
        self.assertIn(self.decision(result), ("blocked", "deny"), result)

    def entries(self):
        if not self.log.exists():
            return []
        return [l for l in self.log.read_text(encoding="utf-8").splitlines() if l.startswith("- Source: ")]

    def verify(self):
        env = dict(os.environ, PYTHONPATH=str(REPO))
        return subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "logbook", "verify"],
                              capture_output=True, text=True, env=env)


class AnswerTests(AdapterBase):
    def test_no_blocks(self):
        r = self.hook(RM)
        self.assertEqual(self.decision(r), "deny")
        self.assertIn("umwayi: No (rule cc-no-destroy)", json.loads(r[1])["hookSpecificOutput"]["permissionDecisionReason"])

    def test_ask_me_first_asks(self):
        r = self.hook(WRITE)
        self.assertEqual(self.decision(r), "ask")
        self.assertIn("umwayi: Ask me first (rule cc-ask-write)", r[1])
        self.assertEqual(self.decision(self.hook(MCP)), "ask")  # no rule: Ask me first
        self.assertEqual(self.decision(self.hook(call("SomeNewTool", {}))), "ask")

    def test_yes_allows(self):
        r = self.hook(READ)
        self.assertEqual(json.loads(r[1]), {"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "allow",
            "permissionDecisionReason": "umwayi: Yes (rule cc-read). Reading and searching files is allowed."}})

    def test_the_example_rules(self):
        cases = [
            (call("Glob", {"pattern": "**/*.py"}), "allow"),
            (call("Grep", {"pattern": "TODO", "path": "/home/me/p"}), "allow"),
            (call("Read", {"file_path": "/home/me/p/.env"}), "deny"),
            (call("Bash", {"command": "npm test"}), "ask"),
            (call("Bash", {"command": "git push origin main"}), "deny"),
            (call("Bash", {"command": "RM -RF /"}), "deny"),  # matching ignores case
            (call("Bash", {"command": "umwayi kill off"}), "deny"),
            (call("Bash", {"command": "echo x > rules.yaml"}), "deny"),
            (call("Edit", {"file_path": "/home/me/p/rules.yaml", "old_string": "a", "new_string": "b"}), "deny"),
            (call("Write", {"file_path": "/home/me/p/LOGBOOK.md", "content": "x"}), "deny"),
            (call("Write", {"file_path": "/home/me/.claude/settings.json", "content": "{}"}), "deny"),
            (call("Write", {"file_path": "/home/me/p/.umwayi/KILL", "content": ""}), "deny"),
            (call("WebFetch", {"url": "https://example.org", "prompt": "x"}), "ask"),
            (call("Agent", {"subagent_type": "Explore", "prompt": "x"}), "ask"),
        ]
        for payload, expected in cases:
            with self.subTest(tool=payload["tool_name"], input=str(payload["tool_input"])[:40]):
                self.assertEqual(self.decision(self.hook(payload)), expected)


class BrokenRulesTests(AdapterBase):
    def test_a_broken_or_missing_rules_file_never_allows(self):
        rules = self.root / "rules.yaml"
        for name, setup in {
            "not yaml": lambda: rules.write_text("rules: [\n"),
            "bad verdict": lambda: rules.write_text("rules:\n  - id: a\n    title: t\n    text: t\n    verdict: maybe\n"),
            "empty": lambda: rules.write_text(""),
            "not utf8": lambda: rules.write_bytes(b"\xff\xfe"),
            "a folder": lambda: (rules.unlink(), rules.mkdir()),
            "missing": lambda: rules.unlink(),
        }.items():
            with self.subTest(rules=name):
                if rules.is_dir():
                    rules.rmdir()
                shutil.copy(EXAMPLE_RULES, rules)
                setup()
                for payload in (READ, RM, WRITE, MCP):
                    r = self.hook(payload)
                    self.assertEqual(self.decision(r), "deny")
                    self.assertIn("rules.yaml could not be used", r[1])


class CrashTests(AdapterBase):
    def test_a_crash_inside_the_adapter_blocks(self):
        for target in ("adapters.common.umwayi_gate:decide", "adapters.common.umwayi_gate:tool_action",
                       "adapters.common.umwayi_gate:run_check", "adapters.common.umwayi_gate:read_hook_input",
                       "json:dumps"):
            for effect in ("crash", "interrupt"):
                with self.subTest(target=target, effect=effect):
                    code, out, err = self.hook(READ, fault=f"{target}:{effect}")
                    self.assertEqual((code, out), (2, ""))
                    self.assertIn("blocked by an unexpected error", err)

    def test_a_crash_inside_umwayi_check_blocks(self):
        for target in ("umwayi.rules:decide", "umwayi.rules:load_rules", "umwayi.logbook:render"):
            with self.subTest(target=target):
                self.assert_blocks(self.hook(READ, fault=f"{target}:crash"))

    def test_umwayi_that_cannot_be_found_blocks(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        r = self.hook(READ, args=["--root", str(self.root), "--umwayi-src", str(empty)], pythonpath=[str(self.site)])
        self.assert_blocks(r)


class BadInputTests(AdapterBase):
    def test_bad_input_blocks(self):
        cases = {
            "bad json": "{not json",
            "empty stdin": "",
            "only spaces": "   \n",
            "a list": [1, 2],
            "a string": '"PreToolUse"',
            "not utf8": b"\xff\xfe{}",
            "no tool_name": {"hook_event_name": "PreToolUse", "tool_input": {}},
            "tool_name not a string": {"hook_event_name": "PreToolUse", "tool_name": 5, "tool_input": {}},
            "empty tool_name": call("", {}),
            "no tool_input": {"hook_event_name": "PreToolUse", "tool_name": "Read"},
            "tool_input not an object": call("Read", "a.py"),
            "another event": {**READ, "hook_event_name": "PostToolUse"},
            "no event": {k: v for k, v in READ.items() if k != "hook_event_name"},
            "too large": b'{"x": "' + b"a" * 1_000_001 + b'"}',
        }
        for name, payload in cases.items():
            with self.subTest(input=name):
                code, out, err = self.hook(payload)
                self.assertEqual((code, out), (2, ""))
        self.assertEqual(self.entries(), [])  # nothing reached umwayi check

    def test_bad_arguments_block(self):
        for args in ([], ["--root"], ["--root", str(self.tmp / "nope")], ["--root", str(self.root), "--timeout", "x"],
                     ["--root", str(self.root), "--timeout", "0"], ["--root", str(self.root), "--allow-all"],
                     ["--help"]):
            with self.subTest(args=args):
                self.assertEqual(self.hook(READ, args=args)[0], 2)

    def test_an_action_too_large_for_umwayi_is_denied(self):
        self.assert_blocks(self.hook(call("Bash", {"command": "echo " + "a" * 70_000})))


class TimeoutTests(AdapterBase):
    def test_a_slow_umwayi_check_is_denied_in_time(self):
        start = time.monotonic()
        r = self.hook(READ, args=["--root", str(self.root), "--timeout", "1"], fault="umwayi.rules:load_rules:hang")
        self.assertLess(time.monotonic() - start, 10)
        self.assertEqual(self.decision(r), "deny")
        self.assertIn("did not answer within 1 seconds", r[1])


class LogbookTests(AdapterBase):
    def test_each_check_writes_one_logbook_entry_and_verify_stays_ok(self):
        payloads = [READ, RM, WRITE, MCP, READ, call("Bash", {"command": f"curl -H 'Authorization: {SECRET}' x"})]
        for n, p in enumerate(payloads, 1):
            self.hook(p)
            self.assertEqual(len(self.entries()), n)
        self.hook("not json")  # blocked before umwayi check: no entry
        self.assertEqual(len(self.entries()), len(payloads))
        v = self.verify()
        self.assertEqual(v.returncode, 0, v.stdout)
        self.assertIn(f"ok: {len(payloads)} entries", v.stdout)
        text = self.log.read_text(encoding="utf-8")
        self.assertNotIn(SECRET, text)
        self.assertNotIn("rm -rf", text)  # only the action type is logged, never the command
        self.assertIn("action type: tool_bash", text)

    def test_a_broken_logbook_denies(self):
        self.hook(READ)
        self.log.write_text(self.log.read_text().replace("tool_read", "tool_edit"))  # a hand edit
        self.assertEqual(self.decision(self.hook(READ)), "deny")
        self.assertEqual(self.decision(self.hook(RM)), "deny")


class UnitTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(REPO))
        self.addCleanup(sys.path.remove, str(REPO))
        from adapters.common import umwayi_gate
        self.gate = umwayi_gate

    def test_type_names(self):
        t = self.gate.type_for
        self.assertEqual([t("Bash"), t("Write"), t("WebFetch"), t("MultiEdit"), t("mcp__github__create_issue"),
                          t("x" * 36), t("x" * 35), t("!!!")],
                         ["tool_bash", "tool_write", "tool_webfetch", "tool_multiedit", "tool_mcp",
                          "tool_long_name", "tool_" + "x" * 35, "tool_unknown"])

    def test_only_the_listed_fields_are_sent(self):
        a = self.gate.tool_action("claude-code", "Write", {"file_path": "/p/a", "content": SECRET}, {"permission_mode": "default"})
        self.assertEqual(a, {"type": "tool_write", "platform": "claude-code", "tool": "Write", "path": "/p/a",
                             "permission_mode": "default"})
        a = self.gate.tool_action("claude-code", "Bash", {"command": ["not", "a", "string"]})
        self.assertNotIn("command", a)
        a = self.gate.tool_action("claude-code", "mcp__srv__do_it", {"x": SECRET})
        self.assertEqual((a["mcp_server"], a["mcp_tool"]), ("srv", "do_it"))
        self.assertNotIn(SECRET, json.dumps(a))
        a = self.gate.tool_action("claude-code", "Read", {"file_path": "/p"}, {"agent_type": "has spaces ok?"})
        self.assertNotIn("agent_type", a)

    def test_decide_is_fail_closed(self):
        R, d = self.gate.CheckResult, self.gate.decide
        ok = {"rules_ok": True}
        cases = [
            (R(0, {**ok, "answer": "Yes"}, None), "allow"),
            (R(3, {**ok, "answer": "Ask me first"}, None), "ask"),
            (R(2, {**ok, "answer": "No"}, None), "deny"),
            (R(0, {**ok, "answer": "No"}, None), "deny"),
            (R(2, {**ok, "answer": "Yes"}, None), "deny"),
            (R(3, {**ok, "answer": "Yes"}, None), "deny"),
            (R(0, {**ok, "answer": "Ask me first"}, None), "deny"),
            (R(0, {"answer": "Yes"}, None), "deny"),  # rules_ok missing
            (R(0, {"answer": "Yes", "rules_ok": "true"}, None), "deny"),  # not a real true
            (R(3, {"answer": "Ask me first", "rules_ok": False}, None), "deny"),
            (R(1, {**ok, "answer": "Yes"}, None), "deny"),
            (R(64, {**ok, "answer": "Yes"}, None), "deny"),
            (R(None, None, "timeout"), "deny"),
            (R(0, None, "no JSON"), "deny"),
            (R(0, {**ok, "answer": "yes"}, None), "deny"),
        ]
        for result, expected in cases:
            with self.subTest(result=result):
                self.assertEqual(d(result).decision, expected)


class SeparationTests(unittest.TestCase):
    def imports(self, path):
        names = set()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names.add(node.module)
        return names

    def test_the_core_never_imports_adapters_and_stays_standard_library(self):
        stdlib = set(sys.stdlib_module_names)
        for f in sorted((REPO / "umwayi").rglob("*.py")):
            for name in self.imports(f):
                with self.subTest(file=f.relative_to(REPO).as_posix(), imports=name):
                    self.assertFalse(name.split(".")[0] == "adapters")
                    self.assertTrue(name.split(".")[0] in stdlib or name.split(".")[0] == "umwayi", name)

    def test_the_shared_adapter_code_is_standard_library_and_never_imports_umwayi(self):
        stdlib = set(sys.stdlib_module_names)
        for f in sorted((REPO / "adapters").rglob("*.py")):
            for name in self.imports(f):
                with self.subTest(file=f.relative_to(REPO).as_posix(), imports=name):
                    self.assertNotEqual(name.split(".")[0], "umwayi")
                    self.assertTrue(name.split(".")[0] in stdlib or name.split(".")[0] == "adapters", name)

    def test_check_json_has_the_fields_adapters_trust(self):
        env = dict(os.environ, PYTHONPATH=str(REPO))
        with tempfile.TemporaryDirectory() as d:
            shutil.copy(EXAMPLE_RULES, Path(d) / "rules.yaml")
            r = subprocess.run([sys.executable, "-m", "umwayi", "--root", d, "check", '{"type": "tool_read", "platform": "claude-code"}',
                                "--json", "--no-log"], capture_output=True, text=True, env=env)
            data = json.loads(r.stdout)
            self.assertEqual((r.returncode, data["answer"], data["rule_id"], data["rules_ok"], data["action_ok"], data["logged"]),
                             (0, "Yes", "cc-read", True, True, False))
            (Path(d) / "rules.yaml").write_text("rules: [\n")
            data = json.loads(subprocess.run([sys.executable, "-m", "umwayi", "--root", d, "check", "{}", "--json", "--no-log"],
                                             capture_output=True, text=True, env=env).stdout)
            self.assertEqual((data["answer"], data["rules_ok"], data["action_ok"]), ("Ask me first", False, True))
            data = json.loads(subprocess.run([sys.executable, "-m", "umwayi", "--root", d, "check", "nope", "--json", "--no-log"],
                                             capture_output=True, text=True, env=env).stdout)
            self.assertEqual((data["rules_ok"], data["action_ok"]), (False, False))

    def test_no_settings_file_is_changed_by_this_repo(self):
        self.assertFalse((REPO / ".claude").exists())
        for f in REPO.rglob("settings*.json"):
            self.assertNotIn(".claude", f.parts, f)

    def test_the_example_rules_load(self):
        sys.path.insert(0, str(REPO))
        try:
            from umwayi.rules import load_rules
            ids = [r.id for r in load_rules(EXAMPLE_RULES)]
        finally:
            sys.path.remove(str(REPO))
        self.assertIn("cc-read", ids)
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
