"""Layer 10 part 7b, tasks 10.26 to 10.28: the Claude Code ACP chat (requirement 10.R11 items 4, 5, 10, 11).

Every test runs `python -m umwayi agent chat ...` as a real child process. `node` is the fake of
tests/agents/fake_node.py: it answers the gate checks and, for `node ADAPTER`, execs the scripted
ACP agent of tests/agents/fake_agent.py in its Claude flavour, which reads
`_meta.claudeCode.options.settings` of session/new, runs its SessionStart hooks (the canary) and
runs its PreToolUse hooks before a permission request. No real Node, adapter or Claude Code.
No test asserts a short duration: they wait for events with generous timeouts.
"""

import json
import os
import re
import signal
import subprocess
import sys
import time
import unittest
from pathlib import Path

from umwayi import acp, agents
from umwayi.telemetry import TELEMETRY_NAMES

from tests.agents.support import RULES as BASE_RULES
from tests.agents.support import SECRET, alive
from tests.agents.test_agents_claude_acp_gate import ClaudeAcpCase

AGENTS = """agents:
  - name: reviewer
    platform: claude-code
    command: claude
    transport: acp
    workdir: {work}
  - name: slow
    platform: claude-code
    command: claude
    transport: acp
    workdir: {work}
    timeout_minutes: 1
  - name: quick
    platform: claude-code
    command: claude
    workdir: {work}
  - name: blocked
    platform: claude-code
    command: claude
    transport: acp
    workdir: {work}
"""
RULES = BASE_RULES + """  - id: perm-read-claude
    title: reading is fine in a Claude Code ACP chat
    text: Allowed.
    verdict: yes
    matchers:
      type: acp_permission
      platform: claude-code
      kind: read
  - id: claude-acp-chat-blocked
    title: this Claude Code ACP chat never starts
    text: Never.
    verdict: no
    matchers:
      type: agent_run
      agent: blocked
      platform: claude-code
      mode: chat
      transport: acp
"""
OPTIONS = [
    {"optionId": "o-always", "name": "Always allow", "kind": "allow_always"},
    {"optionId": "o-allow", "name": "Allow", "kind": "allow_once"},
    {"optionId": "o-reject", "name": "Reject", "kind": "reject_once"},
]
REFUSED_GATE = "Refused agent reviewer: the first gate could not be confirmed in the ACP session"
NOT_SENT = "The first gate could not be confirmed in the ACP session. Nothing was sent."
MODE_TEXT = "The agent did not accept the default permission mode."
HEX32 = re.compile(r"^[0-9a-f]{32}$")


class ClaudeChatCase(ClaudeAcpCase):
    def setUp(self):
        super().setUp()
        self.fake("claude-acp")
        self.write_rules(RULES)
        self.write_agents(AGENTS)
        self.tmpdir = self.tmp / "tmpdir"  # TMPDIR of umwayi, so a leftover canary folder can be seen
        self.tmpdir.mkdir()

    def spec(self, acp_spec=None, **answers):
        self.answers(acp=acp_spec or {}, fake_log=str(self.fake_log), **answers)

    def env_extra(self, extra=None):
        return dict({"TMPDIR": str(self.tmpdir)}, **(extra or {}))

    def chat(self, owner="", name="reviewer", extra=None, fault=None):
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "chat", name],
                           input=owner, capture_output=True, text=True, timeout=180,
                           env=self.env(self.env_extra(extra), fault), cwd=str(self.tmp))
        self.assertIn(r.returncode, {0, 2, 3, 64}, r.stdout + r.stderr)
        self.alive_at_exit = self.agent_pids_alive()
        self.wait_root_quiet()
        return r

    def start_chat(self, name="reviewer", extra=None, fault=None):
        p = subprocess.Popen([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "chat", name],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             env=self.env(self.env_extra(extra), fault), cwd=str(self.tmp))
        self.addCleanup(self._reap, p)
        return p

    def say(self, p, text):
        p.stdin.write(text)
        p.stdin.flush()

    def sent(self, method=None):
        msgs = [c["msg"] for c in self.calls() if c.get("event") == "acp_in"]
        return [m for m in msgs if method is None or m.get("method") == method]

    def methods(self):
        return [m.get("method") for m in self.sent() if "method" in m]

    def canary_args(self, new):
        [group] = new["params"]["_meta"]["claudeCode"]["options"]["settings"]["hooks"]["SessionStart"]
        args = group["hooks"][0]["args"]
        return args[args.index("--dir") + 1], args[args.index("--token") + 1]

    def leftovers(self):
        return sorted(p.name for p in self.tmpdir.iterdir() if p.name.startswith(agents.CANARY_PREFIX))

    def log_text(self):
        p = self.root / "LOGBOOK.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def kill_on(self):
        (self.root / ".umwayi").mkdir(exist_ok=True)
        (self.root / ".umwayi" / "KILL").write_text("", encoding="utf-8")

    def assert_agent_gone(self):
        self.assertEqual(self.alive_at_exit, [], "an agent process was still running when umwayi exited")
        pids = [c["pid"] for c in self.calls() if c.get("started") or c.get("event") == "spawn"]
        self.assertTrue(pids)
        for pid in pids:
            self.assertFalse(alive(pid), f"pid {pid} is still alive")

    def assert_nothing_left(self):
        self.assertEqual(self.leftovers(), [], "a canary folder was left behind")


class SessionTests(ClaudeChatCase):
    def test_session_new_carries_exactly_the_meta_and_the_folder_goes(self):
        self.spec()
        r = self.chat("hello\n:quit\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        [init] = self.sent("initialize")
        self.assertEqual(init["params"]["clientCapabilities"], {})
        [new] = self.sent("session/new")
        folder, token = self.canary_args(new)
        self.assertRegex(token, HEX32)
        self.assertTrue(Path(folder).name.startswith(agents.CANARY_PREFIX))
        self.assertEqual(str(Path(folder).parent), str(self.tmpdir))
        want = agents.claude_acp_session_meta(sys.executable, self.root, folder, token, self.src)
        self.assertEqual(new["params"], {"cwd": str(self.work), "mcpServers": [], "_meta": want})
        opts = new["params"]["_meta"]["claudeCode"]["options"]
        self.assertIs(opts["allowDangerouslySkipPermissions"], False)
        self.assertEqual(set(opts), {"allowDangerouslySkipPermissions", "settings"})  # no maxBudgetUsd (10.R11.12)
        settings = opts["settings"]
        self.assertIs(settings["disableAllHooks"], False)
        self.assertEqual(settings["hooks"]["SessionStart"], [{"hooks": [{
            "type": "command", "command": sys.executable,
            "args": [str(self.src / agents.CLAUDE_ACP_CANARY), "--dir", folder, "--token", token], "timeout": 10}]}])
        hooks = [c for c in self.calls() if c.get("event") == "session_start_hook"]
        self.assertEqual([h["code"] for h in hooks], [0])  # the real canary.py ran and wrote the file
        self.assertFalse(os.path.exists(folder), "the canary folder was not removed")
        self.assert_nothing_left()
        self.assert_agent_gone()

    def test_the_pre_tool_use_entry_is_the_one_agent_run_passes(self):
        self.spec()
        self.chat(":quit\n")
        [new] = self.sent("session/new")
        acp_pre = new["params"]["_meta"]["claudeCode"]["options"]["settings"]["hooks"]["PreToolUse"]
        r = self.umwayi("run", "quick", "--prompt", "hello")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        [run] = [c for c in self.calls() if c.get("prog") == "claude" and c.get("started")]
        run_settings = json.loads(run["argv"][run["argv"].index("--settings") + 1])
        self.assertEqual(acp_pre, run_settings["hooks"]["PreToolUse"])
        self.assertEqual(acp_pre, [{"matcher": "*", "hooks": [{
            "type": "command", "command": sys.executable,
            "args": [str(self.src / "adapters" / "claude_code" / "hook.py"), "--root", str(self.root)],
            "timeout": 30, "onFailure": "block"}]}])

    def test_canary_seen_then_set_mode_default_comes_before_the_first_prompt(self):
        self.spec({"canary_delay": 3})  # the canary runs a few seconds after session/new; umwayi waits for it
        r = self.chat(f"hello {SECRET}\n:quit\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.methods(), ["initialize", "session/new", "session/set_mode", "session/prompt"])
        [mode] = self.sent("session/set_mode")
        self.assertEqual(mode["params"], {"sessionId": "sess-1", "modeId": "default"})
        self.assertIn(f"you said: hello {SECRET}", r.stdout)
        self.assertNotIn(SECRET, self.log_text())
        started = [e for e in self.run_entries() if e.added.startswith("Started agent reviewer (claude-code, acp, chat)")]
        self.assertEqual(len(started), 1)
        self.assert_nothing_left()

    def test_a_fresh_token_and_folder_every_start(self):
        self.spec()
        self.chat(":quit\n")
        self.chat(":quit\n")
        news = self.sent("session/new")
        self.assertEqual(len(news), 2)
        (f1, t1), (f2, t2) = (self.canary_args(n) for n in news)
        self.assertNotEqual(t1, t2)
        self.assertNotEqual(f1, f2)
        self.assert_nothing_left()

    def test_the_child_environment_is_the_allow_list(self):
        self.spec()
        r = self.chat(":quit\n", extra={"ANTHROPIC_API_KEY": SECRET, "NODE_OPTIONS": "--x", "LANG": "C.UTF-8"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        [chat] = [c for c in self.node_calls() if c["probe"] == "chat"]
        names = set(chat["env"])
        # plus the telemetry names of this chat's own receiver (budget governor, B.R2.2), and nothing else
        self.assertLessEqual(names, set(agents.CHILD_ENV_NAMES) | set(agents.CHILD_ENV_SET) | set(TELEMETRY_NAMES))
        self.assertLessEqual(set(TELEMETRY_NAMES), names)
        self.assertIn("LANG", names)
        self.assertNotIn("ANTHROPIC_API_KEY", names)
        self.assertNotIn("NODE_OPTIONS", names)
        self.assertEqual(chat["protocol"], "v1")
        self.assertEqual(chat["argv"], [str(self.node), str(self.adapter)])
        self.assertEqual(chat["cwd"], str(self.work))
        [started] = [c for c in self.calls() if c.get("prog") == "claude-acp" and c.get("started")]
        self.assertEqual(started["pid"], chat["pid"])  # the same process, exec'd into the scripted agent
        self.assertEqual(started["sid"], started["pid"], "the adapter is not in its own session")
        self.assertEqual(started["pgid"], started["pid"], "the adapter is not in its own process group")

    def test_a_tool_call_goes_through_the_hook_first_then_the_rules_with_platform_claude_code(self):
        read = {"claude_tool": {"tool": "Read", "input": {"file_path": "/etc/hostname"}},
                "permission": {"toolCall": {"toolCallId": "c1", "title": "Read TRAP", "kind": "read", "name": "Read"},
                               "options": OPTIONS}}
        rm = {"claude_tool": {"tool": "Bash", "input": {"command": "rm -rf /"}},
              "permission": {"toolCall": {"toolCallId": "c2", "title": "rm", "kind": "execute", "name": "Bash"},
                             "options": OPTIONS}}
        self.spec({"turns": [[read, rm]]})
        r = self.chat("go\n:quit\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        tools = [(c["tool"], c["decision"]) for c in self.calls() if c.get("event") == "tool"]
        self.assertEqual(tools, [("Read", "allow"), ("Bash", "deny")])
        answers = [c["answer"]["result"]["outcome"] for c in self.calls() if c.get("event") == "permission_answer"]
        self.assertEqual(answers, [{"outcome": "selected", "optionId": "o-allow"}])  # none for the denied Bash
        text = self.log_text()
        self.assertIn("rules matched: perm-read-claude", text)  # only an action with platform claude-code matches
        self.assertNotIn("TRAP", text)


class GateTests(ClaudeChatCase):
    def assert_refused_in_session(self, r, text):
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(text, r.stdout)
        self.assertNotIn("session/prompt", self.methods())
        self.assertNotIn("you said", r.stdout)
        self.assert_nothing_left()
        self.assert_agent_gone()

    def test_the_gate_wait_is_30_seconds(self):
        self.assertEqual(acp.GATE_WAIT, 30.0)

    def test_canary_never_run_is_refused_before_any_prompt(self):
        self.spec({"canary": "never"})
        r = self.chat(f"hello {SECRET}\n:quit\n", extra={"UMWAYI_TEST_GATE_WAIT": "3"})
        self.assert_refused_in_session(r, NOT_SENT)
        self.assertNotIn("session/set_mode", self.methods())
        refused = [e for e in self.run_entries() if e.added.startswith("Refused agent")]
        self.assertEqual([e.added for e in refused], [REFUSED_GATE])
        self.assertNotIn(SECRET, self.log_text())

    def test_canary_run_only_at_the_first_prompt_is_refused(self):
        self.spec({"canary": "first_prompt"})
        r = self.chat("hello\n:quit\n", extra={"UMWAYI_TEST_GATE_WAIT": "3"})
        self.assert_refused_in_session(r, NOT_SENT)
        self.assertEqual([c for c in self.calls() if c.get("event") == "session_start_hook"], [])

    def test_set_mode_answered_with_an_error_ends_with_2(self):
        self.spec({"set_mode_error": True})
        r = self.chat("hello\n:quit\n")
        self.assert_refused_in_session(r, MODE_TEXT)
        self.assertEqual(self.methods(), ["initialize", "session/new", "session/set_mode"])

    def test_a_missing_canary_script_starts_nothing(self):
        (self.src / agents.CLAUDE_ACP_CANARY).unlink()
        self.spec()
        r = self.chat("hello\n")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("the canary hook", r.stdout)
        self.assertEqual([c for c in self.node_calls() if c["started"]], [])
        self.assertEqual(self.sent(), [])
        self.assert_nothing_left()

    def test_a_canary_folder_inside_the_root_starts_nothing(self):
        inside = self.root / "tmp"
        inside.mkdir()
        self.spec()
        r = self.chat("hello\n", extra={"TMPDIR": str(inside)})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("outside the root and the workdir", r.stdout)
        self.assertEqual([c for c in self.node_calls() if c["started"]], [])
        self.assertEqual(list(inside.iterdir()), [])

    def test_a_failing_gate_check_starts_nothing(self):
        self.spec(auth_exit=1)
        r = self.chat("hello\n")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(agents.SIGNIN_TEXT, r.stdout)
        self.assertEqual([c for c in self.node_calls() if c["started"]], [])
        self.assert_nothing_left()

    def test_the_rules_see_platform_claude_code_mode_chat_and_transport_acp_and_no_starts_nothing(self):
        self.spec()
        r = self.chat("hello\n", name="blocked")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(self.node_calls(), [])
        self.assertIn("rules matched: agent-no, claude-acp-chat-blocked", self.log_text())

    def test_the_kill_switch_before_the_start_starts_nothing(self):
        self.kill_on()
        self.spec()
        r = self.chat("hello\n")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertEqual(self.node_calls(), [])
        self.assert_nothing_left()


class KiroUnchangedTests(ClaudeChatCase):
    def test_a_kiro_acp_chat_sends_no_meta_no_set_mode_and_does_not_wait(self):
        self.write_agents(AGENTS + "  - name: k\n    platform: kiro\n    command: kiro-cli\n    transport: acp\n"
                                   "    workdir: {work}\n")
        self.write_rules(RULES.replace("agent: [reviewer, slow, stubborn, quick]",
                                       "agent: [reviewer, slow, stubborn, quick, k]"))
        self.kiro_hook_file(command=self.kiro_command(python=sys.executable))
        r = self.chat("hello\n:quit\n", name="k", extra={"FAKE_ACP": "{}"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.methods(), ["initialize", "session/new", "session/prompt"])
        [new] = self.sent("session/new")
        self.assertEqual(new["params"], {"cwd": str(self.work), "mcpServers": []})
        self.assertEqual(self.node_calls(), [])
        self.assert_nothing_left()


class StopTests(ClaudeChatCase):
    """Every stop leaves nothing alive: the adapter, a child in a new session, a command that ignores the cancel."""

    def running(self, turn, name="reviewer", extra=None, fault=None, settle=2.5, **spec):
        self.spec(dict({"turns": [turn]}, **spec))
        p = self.start_chat(name=name, extra=extra, fault=fault)
        self.say(p, "go\n")
        n = sum(1 for a in turn if any(k.startswith("spawn") for k in a))
        end = time.monotonic() + 60
        while len([c for c in self.calls() if c.get("event") == "spawn"]) < n:
            if time.monotonic() > end:
                self.fail(f"the fake did not start its children; calls: {self.calls()}")
            time.sleep(0.05)
        time.sleep(settle)  # at least two watcher passes, so umwayi has seen the children in /proc
        return p

    def test_the_kill_switch_stops_the_group_and_every_descendant(self):
        # ignore_eof: an adapter that does not exit when its stdin closes, so only the signals stop it
        p = self.running([{"spawn": True}, {"spawn_setsid": True}, {"spawn_stubborn": True}, {"wait_cancel": True}],
                         ignore_eof=True)
        self.kill_on()
        code, out, _ = self.finish(p, timeout=90)  # SIGKILL follows after 10 s for the stubborn one
        self.assertEqual(code, 3, out)
        self.assertIn("The kill switch stopped agent reviewer (exit 3).", out)
        self.assert_agent_gone()
        self.assert_nothing_left()

    def test_a_background_command_orphaned_while_the_chat_runs_is_still_stopped(self):
        p = self.running([{"spawn_orphan": True}, {"wait_cancel": True}])
        mid = [c["pid"] for c in self.calls() if c.get("intermediate")][0]
        end = time.monotonic() + 30
        while alive(mid) and time.monotonic() < end:  # its parent is gone: only /proc tracking still knows it
            time.sleep(0.05)
        self.kill_on()
        code, out, _ = self.finish(p, timeout=90)
        self.assertEqual(code, 3, out)
        self.assert_agent_gone()
        self.assert_nothing_left()

    def test_sigterm_to_umwayi_stops_everything(self):
        p = self.running([{"spawn_setsid": True}, {"wait_cancel": True}])
        p.send_signal(signal.SIGTERM)
        code, out, _ = self.finish(p, timeout=90)
        self.assertEqual(code, 2, out)
        self.assertEqual(self.run_entries()[-1].added, "Agent reviewer was stopped: umwayi got SIGTERM")
        self.assert_agent_gone()
        self.assert_nothing_left()

    def test_the_timeout_stops_everything(self):
        p = self.running([{"spawn_setsid": True}, {"wait_cancel": True}], name="slow",
                         extra={"UMWAYI_TEST_MINUTE": "15"})
        code, out, _ = self.finish(p, timeout=120)
        self.assertEqual(code, 2, out)
        self.assertIn("timeout of 1 min", out)
        self.assert_agent_gone()
        self.assert_nothing_left()

    def test_quit_stops_a_background_command_left_by_a_clean_exit(self):
        p = self.running([{"spawn_setsid": True}, {"chunk": "started it"}])
        self.say(p, ":quit\n")
        p.stdin.close()
        code, out, err = self.finish(p, timeout=90)
        self.assertEqual(code, 0, out + err)
        self.assert_agent_gone()
        self.assert_nothing_left()

    def test_quit_right_after_a_background_command_is_started_still_stops_it(self):
        # no settle time: umwayi looks in /proc once more before the adapter's clean exit orphans the command
        p = self.running([{"spawn_setsid": True}, {"chunk": "started it"}], settle=0)
        self.say(p, ":quit\n")
        p.stdin.close()
        code, out, err = self.finish(p, timeout=90)
        self.assertEqual(code, 0, out + err)
        self.assert_agent_gone()

    def test_a_failing_logbook_stops_everything(self):
        p = self.running([{"spawn_setsid": True}, {"wait_cancel": True}])
        with open(self.root / "LOGBOOK.md", "a", encoding="utf-8") as f:
            f.write("edited by hand\n")  # the logbook check fails: a stop with exit 2
        code, out, _ = self.finish(p, timeout=90)
        self.assertEqual(code, 2, out)
        self.assertIn("The logbook can no longer be written", out)
        self.assert_agent_gone()
        self.assert_nothing_left()

    def test_a_crash_in_umwayi_stops_everything(self):
        # a child in the adapter's group: the crash comes at the first watcher pass, maybe before umwayi saw it
        self.spec({"turns": [[{"spawn": True}, {"wait_cancel": True}]]})
        r = self.chat("go\n", fault="umwayi.logbook:check_writable:crash", extra={"UMWAYI_FAULT_TEXT": SECRET})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn(SECRET, r.stdout + r.stderr)
        self.assert_agent_gone()
        self.assert_nothing_left()

    def test_the_adapter_crashing_ends_the_chat_with_2(self):
        self.spec({"turns": [[{"spawn_setsid": True}, {"exit": 1}]]})
        r = self.chat("go\n")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("The agent closed the connection", r.stdout)
        self.assert_agent_gone()
        self.assert_nothing_left()


if __name__ == "__main__":
    unittest.main()
