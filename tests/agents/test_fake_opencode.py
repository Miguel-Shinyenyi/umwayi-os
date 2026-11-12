"""Layer 10 part 8, task 10.47: the fake `opencode acp` (tests/agents/fake_opencode.py).

The fake is test equipment, so it is tested like code: the tests here start it directly, with the inline config that
`agents.opencode_inline_config()` builds, speak ACP to it and check what it does against what OpenCode 2.2.7 was seen
to do (adapters/NOTES-layer10.md, "OpenCode 2.2.7 on a real install"). The chat tests of 10.48 and 10.49 rely on it.

What is checked: initialize, session/new (absolute cwd only, the three config options, the model of the inline
config, the free default model when the config is ignored), the canary in every mode (0600, never over an existing
file), auth_required, the tool table through the real layer 9 hook and the real starter rules (Yes asks, No fails
with the fixed text and no request, Code Mode fails, the V2 shape of every request), the answers once, always, reject
and cancelled, cancel, an ignored end of input, an invalid inline config, and what the fake records.
"""

import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

from umwayi import agents

from tests.agents.support import AgentCase, REPO

TOKEN = "0123456789abcdef0123456789abcdef"
DENIED = "umwayi: this tool call was not allowed by the rules"


class Driver:
    """Speaks JSON-RPC to the fake over its pipes."""

    def __init__(self, proc):
        self.proc = proc
        self.n = 0
        self.seen = []

    def send(self, obj):
        self.proc.stdin.write((json.dumps(obj) + "\n").encode())
        self.proc.stdin.flush()

    def call(self, method, params):
        self.n += 1
        self.send({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params})
        return self.n

    def read(self):
        line = self.proc.stdout.readline()
        if not line:
            return None
        msg = json.loads(line)
        self.seen.append(msg)
        return msg

    def until(self, rid):
        """Read until the answer to `rid`; return (answer, the messages before it)."""
        before = []
        while True:
            msg = self.read()
            if msg is None:
                return None, before
            if msg.get("id") == rid and "method" not in msg:
                return msg, before
            before.append(msg)

    def prompt(self, text, answers=None):
        """One prompt; `answers` is the list of option ids (or None for cancelled) given to the requests, in order."""
        rid = self.call("session/prompt", {"sessionId": "ses_fake0000000001", "prompt": [{"type": "text", "text": text}]})
        answers = list(answers or [])
        events = []
        while True:
            msg = self.read()
            if msg is None:
                return None, events
            if msg.get("id") == rid and "method" not in msg:
                return msg, events
            events.append(msg)
            if msg.get("method") == "session/request_permission":
                a = answers.pop(0) if answers else "once"
                outcome = {"outcome": "cancelled"} if a is None else {"outcome": "selected", "optionId": a}
                self.send({"jsonrpc": "2.0", "id": msg["id"], "result": {"outcome": outcome}})


class FakeOpenCodeCase(AgentCase):
    def setUp(self):
        super().setUp()
        (self.root / "rules.yaml").write_text(
            (REPO / "adapters" / "opencode" / "rules.example.yaml").read_text(encoding="utf-8"), encoding="utf-8")
        self.folder = self.tmp / "canary"
        self.folder.mkdir(mode=0o700)
        self.canary = self.folder / "canary"
        self.procs = []

    def tearDown(self):
        for p in self.procs:
            if p.poll() is None:
                p.kill()
            p.wait()
            for s in (p.stdin, p.stdout, p.stderr):
                if s:
                    s.close()

    def agent(self, provider="opencode", model="opencode/big-pickle"):
        return agents.Agent("o", "opencode", str(self.bin / "opencode"), "acp", str(self.work),
                            provider=provider, model=model)

    def config(self, token=TOKEN, agent=None):
        return agents.opencode_inline_config(agent or self.agent(), self.root, token, self.folder, sys.executable, REPO)

    def start(self, raw=None, **cfg):
        """Start the fake in `acp` mode with the inline config (or `raw` text) and return a Driver."""
        self.fake_opencode(**cfg)
        content = self.config() if raw is None else raw
        env = {"PATH": os.environ["PATH"], "OPENCODE_CONFIG_CONTENT": content}
        proc = subprocess.Popen([str(self.bin / "opencode"), "acp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, cwd=str(self.work), env=env)
        self.procs.append(proc)
        return Driver(proc)

    def open(self, **cfg):
        """Start, initialize, session/new. Returns (driver, initialize answer, session/new answer)."""
        d = self.start(**cfg)
        init, _ = d.until(d.call("initialize", {"protocolVersion": 1, "clientCapabilities": {}}))
        new, _ = d.until(d.call("session/new", {"cwd": str(self.work), "mcpServers": []}))
        return d, init, new

    def log(self):
        if not self.fake_log.exists():
            return []
        return [json.loads(x) for x in self.fake_log.read_text(encoding="utf-8").splitlines() if x]

    def events(self, name):
        return [e for e in self.log() if e.get("event") == name]

    def finish(self, d):
        d.proc.stdin.close()
        return d.proc.wait(timeout=20)


def option(new, name):
    return next(o for o in new["result"]["configOptions"] if o["id"] == name)


class Protocol(FakeOpenCodeCase):
    def test_initialize_offers_the_login(self):
        d, init, new = self.open()
        self.assertEqual(init["result"]["protocolVersion"], 1)
        self.assertEqual(init["result"]["authMethods"][0]["id"], "opencode-login")
        self.assertEqual(new["result"]["sessionId"], "ses_fake0000000001")
        self.finish(d)

    def test_session_new_has_three_config_options(self):
        d, _, new = self.open()
        self.assertEqual([o["id"] for o in new["result"]["configOptions"]], ["model", "effort", "mode"])
        self.assertEqual(option(new, "model")["currentValue"], "opencode/big-pickle")
        self.assertEqual(option(new, "mode")["currentValue"], "build")
        self.finish(d)

    def test_model_is_the_one_of_the_inline_config(self):
        self.fake_opencode()
        agent = self.agent("ollama", "ollama/qwen3-coder")
        d = self.start(raw=self.config(agent=agent))
        d.until(d.call("initialize", {"protocolVersion": 1}))
        new, _ = d.until(d.call("session/new", {"cwd": str(self.work), "mcpServers": []}))
        self.assertEqual(option(new, "model")["currentValue"], "ollama/qwen3-coder")
        self.finish(d)

    def test_model_setting_overrides_what_is_reported(self):
        d, _, new = self.open(acp={"model": "other/model"})
        self.assertEqual(option(new, "model")["currentValue"], "other/model")
        self.finish(d)

    def test_ignored_config_gives_the_free_default_and_no_canary(self):
        d, _, new = self.open(acp={"ignore_config": True}, fake_log=str(self.fake_log))
        self.assertEqual(option(new, "model")["currentValue"], "opencode/big-pickle")
        self.assertFalse(self.canary.exists())
        self.finish(d)

    def test_relative_cwd_is_an_error(self):
        d = self.start()
        d.until(d.call("initialize", {"protocolVersion": 1}))
        answer, _ = d.until(d.call("session/new", {"cwd": "work", "mcpServers": []}))
        self.assertEqual(answer["error"]["code"], -32602)
        self.assertEqual(d.proc.wait(timeout=20), 0)

    def test_initialize_garbage(self):
        d = self.start(acp={"init": "garbage"})
        d.call("initialize", {"protocolVersion": 1})
        self.assertEqual(d.proc.stdout.readline().decode().strip(), "this is not json")
        self.finish(d)

    def test_initialize_other_protocol_version(self):
        d = self.start(acp={"init": {"protocolVersion": 2}})
        init, _ = d.until(d.call("initialize", {"protocolVersion": 1}))
        self.assertEqual(init["result"]["protocolVersion"], 2)
        self.finish(d)

    def test_initialize_error(self):
        d = self.start(acp={"init": {"error": {"code": -32603, "message": "boom"}}})
        init, _ = d.until(d.call("initialize", {"protocolVersion": 1}))
        self.assertEqual(init["error"]["message"], "boom")
        self.finish(d)

    def test_auth_required_at_session_new(self):
        d = self.start(acp={"auth_required": "session_new"})
        d.until(d.call("initialize", {"protocolVersion": 1}))
        answer, _ = d.until(d.call("session/new", {"cwd": str(self.work), "mcpServers": []}))
        self.assertEqual(answer["error"], {"code": -32000, "message": "auth_required"})
        self.assertEqual(d.proc.wait(timeout=20), 0)

    def test_auth_required_at_prompt(self):
        d, _, _ = self.open(acp={"auth_required": "prompt"})
        answer, _ = d.prompt("hi")
        self.assertEqual(answer["error"]["code"], -32000)
        self.finish(d)

    def test_set_mode_is_answered(self):
        d, _, _ = self.open()
        answer, _ = d.until(d.call("session/set_mode", {"sessionId": "ses_fake0000000001", "modeId": "plan"}))
        self.assertEqual(answer["result"], {})
        self.finish(d)

    def test_default_turn_echoes_the_prompt(self):
        d, _, _ = self.open()
        answer, events = d.prompt("hello there")
        self.assertEqual(answer["result"]["stopReason"], "end_turn")
        texts = [e["params"]["update"]["content"]["text"] for e in events
                 if e["params"]["update"]["sessionUpdate"] == "agent_message_chunk"]
        self.assertEqual(texts, ["you said: hello there"])
        self.finish(d)

    def test_turns_are_used_in_order(self):
        d, _, _ = self.open(acp={"turns": [[{"chunk": "one"}], [{"chunk": "two"}]]})
        for want in ("one", "two"):
            _, events = d.prompt("x")
            self.assertEqual(events[0]["params"]["update"]["content"]["text"], want)
        self.finish(d)


class Canary(FakeOpenCodeCase):
    def test_written_at_session_new_with_mode_0600(self):
        d, _, _ = self.open()
        self.assertEqual(self.canary.read_text(), TOKEN)
        self.assertEqual(self.canary.stat().st_mode & 0o777, 0o600)
        self.assertTrue(self.events("canary")[0]["written"])
        self.finish(d)

    def test_never_written(self):
        d, _, _ = self.open(acp={"canary": "never"})
        d.prompt("hi")
        self.assertFalse(self.canary.exists())
        self.finish(d)

    def test_wrong_token(self):
        d, _, _ = self.open(acp={"canary": "wrong"})
        self.assertNotEqual(self.canary.read_text(), TOKEN)
        self.assertEqual(len(self.canary.read_text()), len(TOKEN))
        self.finish(d)

    def test_late(self):
        d, _, _ = self.open(acp={"canary": "late", "canary_delay": 1.5})
        self.assertFalse(self.canary.exists())
        deadline = time.time() + 10
        while not self.canary.exists() and time.time() < deadline:
            time.sleep(0.1)
        self.assertEqual(self.canary.read_text(), TOKEN)
        self.finish(d)

    def test_first_prompt(self):
        d, _, _ = self.open(acp={"canary": "first_prompt"})
        self.assertFalse(self.canary.exists())
        d.prompt("hi")
        self.assertEqual(self.canary.read_text(), TOKEN)
        self.finish(d)

    def test_an_existing_file_is_not_overwritten(self):
        self.canary.write_text("old")
        d, _, _ = self.open()
        self.assertEqual(self.canary.read_text(), "old")
        self.assertFalse(self.events("canary")[0]["written"])
        self.finish(d)


class Tools(FakeOpenCodeCase):
    def run_tool(self, tool, inp, answers=None, **extra):
        d, _, _ = self.open(acp={"turns": [[dict({"tool": tool, "input": inp}, **extra)]]})
        answer, events = d.prompt("go", answers)
        self.assertEqual(answer["result"]["stopReason"], "end_turn")
        self.finish(d)
        requests = [e for e in events if e.get("method") == "session/request_permission"]
        updates = [e["params"]["update"] for e in events
                   if e.get("method") == "session/update" and e["params"]["update"]["sessionUpdate"] == "tool_call_update"]
        return requests, updates, events

    def test_read_is_asked_with_kind_read(self):
        requests, updates, _ = self.run_tool("read", {"path": str(self.work / "a.txt")})
        self.assertEqual(len(requests), 1)
        call = requests[0]["params"]["toolCall"]
        self.assertEqual((call["name"], call["kind"], call["status"]), ("read", "read", "pending"))
        self.assertEqual(call["locations"], [{"path": str(self.work / "a.txt")}])
        self.assertEqual([o["optionId"] for o in requests[0]["params"]["options"]], ["once", "always", "reject"])
        self.assertEqual(updates[0]["status"], "completed")

    def test_search_kinds(self):
        for tool in ("grep", "glob"):
            requests, _, _ = self.run_tool(tool, {"pattern": "x", "path": str(self.work)})
            self.assertEqual(requests[0]["params"]["toolCall"]["kind"], "search", tool)

    def test_secret_file_fails_with_the_fixed_text_and_no_request(self):
        requests, updates, _ = self.run_tool("read", {"path": str(self.work / ".env")})
        self.assertEqual(requests, [])
        self.assertEqual(updates[0]["status"], "failed")
        self.assertEqual(updates[0]["content"][0]["content"]["text"], DENIED)

    def test_code_mode_execute_fails_with_no_request(self):
        requests, updates, _ = self.run_tool("execute", {"code": "1+1"})
        self.assertEqual(requests, [])
        self.assertEqual(updates[0]["status"], "failed")
        self.assertEqual(updates[0]["content"][0]["content"]["text"], DENIED)

    def test_rule_no_fails_with_no_request(self):
        requests, updates, _ = self.run_tool("shell", {"command": "rm -rf build"})
        self.assertEqual(requests, [])
        self.assertEqual(updates[0]["status"], "failed")

    def test_shell_request_has_kind_execute_and_cwd(self):
        requests, _, _ = self.run_tool("shell", {"command": "npm test"})
        call = requests[0]["params"]["toolCall"]
        self.assertEqual(call["kind"], "execute")
        self.assertEqual(call["rawInput"]["command"], "npm test")
        self.assertEqual(call["rawInput"]["cwd"], str(self.work))
        self.assertEqual(call["locations"], [{"path": str(self.work)}])

    def test_write_and_edit_carry_a_diff(self):
        for tool in ("write", "edit"):
            requests, _, _ = self.run_tool(tool, {"path": str(self.work / "a.py"), "content": "x"})
            call = requests[0]["params"]["toolCall"]
            self.assertEqual(call["kind"], "edit", tool)
            self.assertEqual(call["content"][0]["type"], "diff")

    def test_webfetch_subagent_question_kinds(self):
        want = {"webfetch": ("fetch", {"url": "https://example.com"}),
                "subagent": ("think", {"agent": "general", "description": "d", "prompt": "p"}),
                "question": ("other", {})}
        for tool, (kind, inp) in want.items():
            requests, _, _ = self.run_tool(tool, inp)
            self.assertEqual(requests[0]["params"]["toolCall"]["kind"], kind, tool)

    def test_child_session_request_has_the_meta(self):
        requests, _, _ = self.run_tool("read", {"path": str(self.work / "a.txt")}, child=True)
        call = requests[0]["params"]["toolCall"]
        self.assertTrue(call["toolCallId"].startswith("ses_child0000000001:"))
        meta = call["_meta"]["opencode/child-session"]
        self.assertEqual((meta["id"], meta["parentID"], meta["depth"]), ("ses_child0000000001", "ses_fake0000000001", 1))

    def test_request_without_a_name(self):
        requests, _, _ = self.run_tool("read", {"path": str(self.work / "a.txt")}, no_name=True)
        call = requests[0]["params"]["toolCall"]
        self.assertNotIn("name", call)
        self.assertNotIn("rawInput", call)
        self.assertEqual(call["kind"], "read")

    def test_unknown_tool_is_denied_by_the_ask_rule_of_the_plugin(self):
        requests, updates, _ = self.run_tool("brand_new_tool", {})
        self.assertEqual(requests, [])
        self.assertEqual(updates[0]["status"], "failed")

    def test_hook_runs_before_the_request(self):
        self.run_tool("read", {"path": str(self.work / "a.txt")})
        order = [e["event"] for e in self.log() if e.get("event") in ("tool", "request_sent")]
        self.assertEqual(order, ["tool", "request_sent"])
        self.assertEqual(self.events("tool")[0]["verdict"], "allow")

    def test_hook_that_cannot_run_denies(self):
        bad = json.loads(self.config())
        bad["plugins"][0]["options"]["hook"] = [str(self.tmp / "no-such-hook")]
        d, _, _ = self.open_raw(json.dumps(bad), acp={"turns": [[{"tool": "read", "input": {"path": "/x"}}]]})
        answer, events = d.prompt("go")
        self.assertEqual([e for e in events if e.get("method") == "session/request_permission"], [])
        self.finish(d)

    def open_raw(self, raw, **cfg):
        d = self.start(raw=raw, **cfg)
        d.until(d.call("initialize", {"protocolVersion": 1}))
        new, _ = d.until(d.call("session/new", {"cwd": str(self.work), "mcpServers": []}))
        return d, None, new

    def test_owner_yes_for_execute_runs_without_a_request(self):
        with open(self.root / "rules.yaml", "a", encoding="utf-8") as f:
            f.write("  - id: owner-yes-execute\n    title: t\n    text: t\n    cause: c\n    verdict: yes\n"
                    "    matchers:\n      platform: opencode\n      type: tool_execute\n")
        requests, updates, _ = self.run_tool("execute", {"code": "1+1"})
        self.assertEqual(requests, [])
        self.assertEqual(updates[0]["status"], "completed")


class Answers(FakeOpenCodeCase):
    def answered(self, answers):
        d, _, _ = self.open(acp={"turns": [[{"tool": "read", "input": {"path": "/x/a"}}]]})
        _, events = d.prompt("go", answers)
        self.finish(d)
        update = [e["params"]["update"] for e in events if e.get("method") == "session/update"
                  and e["params"]["update"]["sessionUpdate"] == "tool_call_update"][0]
        return update["status"], self.events("permission_answer")[0]["outcome"]

    def test_once_runs_the_tool(self):
        self.assertEqual(self.answered(["once"]), ("completed", "once"))

    def test_always_runs_the_tool_and_is_recorded(self):
        self.assertEqual(self.answered(["always"]), ("completed", "always"))

    def test_reject_fails_the_tool(self):
        self.assertEqual(self.answered(["reject"]), ("failed", "reject"))

    def test_cancelled_fails_the_tool(self):
        self.assertEqual(self.answered([None]), ("failed", "cancelled"))


class Lifecycle(FakeOpenCodeCase):
    def test_cancel_ends_the_turn_cancelled(self):
        d, _, _ = self.open(acp={"turns": [[{"chunk": "a"}, {"wait_cancel": True}]]})
        rid = d.call("session/prompt", {"sessionId": "ses_fake0000000001", "prompt": [{"type": "text", "text": "x"}]})
        d.send({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": "ses_fake0000000001"}})
        answer, _ = d.until(rid)
        self.assertEqual(answer["result"]["stopReason"], "cancelled")
        self.assertEqual(len(self.events("got_cancel")), 1)
        self.finish(d)

    def test_end_of_input_ends_it(self):
        d, _, _ = self.open()
        self.assertEqual(self.finish(d), 0)
        self.assertEqual(len(self.events("acp_eof")), 1)
        self.assertEqual(len(self.events("end")), 1)

    def test_ignore_eof_keeps_running_until_killed(self):
        d, _, _ = self.open(acp={"ignore_eof": True})
        d.proc.stdin.close()
        time.sleep(1.0)
        self.assertIsNone(d.proc.poll())
        d.proc.kill()
        d.proc.wait()

    def test_exit_action(self):
        d, _, _ = self.open(acp={"turns": [[{"exit": 7}]]})
        d.call("session/prompt", {"sessionId": "ses_fake0000000001", "prompt": [{"type": "text", "text": "x"}]})
        self.assertEqual(d.proc.wait(timeout=20), 7)

    def test_term_is_recorded_and_ends_143(self):
        d, _, _ = self.open()
        d.proc.terminate()
        self.assertEqual(d.proc.wait(timeout=20), 143)
        self.assertEqual(len(self.events("term")), 1)

    def test_spawn_records_a_child_that_outlives_nothing_until_killed(self):
        d, _, _ = self.open(acp={"turns": [[{"spawn": True}]]})
        d.prompt("x")
        pid = self.events("spawn")[0]["pid"]
        os.kill(pid, 0)
        os.kill(pid, 9)
        self.finish(d)

    def test_stderr_text(self):
        d, _, _ = self.open(acp={"stderr": "hello from stderr"})
        self.finish(d)
        self.assertIn("hello from stderr", d.proc.stderr.read().decode())

    def test_invalid_inline_config_exits_1(self):
        d = self.start(raw="{not json")
        self.assertEqual(d.proc.wait(timeout=20), 1)
        self.assertIn("not valid JSON", d.proc.stderr.read().decode())
        self.assertEqual(len(self.events("config_invalid")), 1)

    def test_start_is_recorded(self):
        d, _, _ = self.open()
        started = self.log()[0]
        self.assertEqual((started["argv"], started["mode"], started["started"]), (["acp"], "acp", True))
        self.assertEqual(json.loads(started["config_content"])["plugins"][0]["options"]["token"], TOKEN)
        self.assertIn("OPENCODE_CONFIG_CONTENT", started["env_keys"])
        self.finish(d)

    def test_every_message_in_is_recorded(self):
        d, _, _ = self.open()
        d.prompt("zzz")
        methods = [e["msg"].get("method") for e in self.events("acp_in")]
        self.assertEqual(methods[:3], ["initialize", "session/new", "session/prompt"])
        self.finish(d)

    def test_version_mode_still_works(self):
        self.fake_opencode(version="opencode v2.2.7")
        r = subprocess.run([str(self.bin / "opencode"), "--version"], capture_output=True, text=True, timeout=20)
        self.assertEqual(r.stdout.strip(), "opencode v2.2.7")
        self.assertFalse(self.log()[0]["started"])


if __name__ == "__main__":
    unittest.main()
