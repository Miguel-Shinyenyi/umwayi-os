"""Layer 10, part 7 task 10.29 (a Claude Code ACP chat end to end with the fake) and part 7c task 10.36 (the watch
of the adapter's `_auth/status_update` during an ACP chat, 10.R12.8).

Every test runs `python -m umwayi agent chat ...` as a real child process, with the fake `node`
(tests/agents/fake_node.py) and the scripted fake ACP agent in its Claude flavour (tests/agents/fake_agent.py):
it runs the canary and the PreToolUse hooks of the inline settings, sends permission requests in the adapter's
shape and pushes notifications. No real Node, no real Claude Code, no network, no key, no real login.
"""

import json
import sys
import unittest

from tests.agents.support import RULES as BASE_RULES
from tests.agents.support import SECRET
from tests.agents.test_agents_claude_acp_chat import OPTIONS, ClaudeChatCase

AGENTS = """agents:
  - name: reviewer
    platform: claude-code
    command: claude
    transport: acp
    workdir: {work}
  - name: helper
    platform: kiro
    command: kiro-cli
    transport: acp
    workdir: {work}
"""
RULES = BASE_RULES + """  - id: kiro-acp-yes
    title: the Kiro ACP helper may start
    text: Allowed.
    verdict: yes
    matchers:
      type: agent_run
      agent: helper
  - id: hook-read-claude
    title: the hook sees a Claude Code read
    text: Allowed.
    verdict: yes
    matchers:
      type: tool_read
      platform: claude-code
  - id: hook-bash-claude
    title: the hook sees a Claude Code shell command
    text: The owner confirms.
    verdict: ask
    matchers:
      type: tool_bash
      platform: claude-code
  - id: perm-read-claude
    title: reading is fine in a Claude Code ACP chat
    text: Allowed.
    verdict: yes
    matchers:
      type: acp_permission
      platform: claude-code
      kind: read
  - id: perm-plan-claude
    title: leaving plan mode is fine, in the default mode
    text: Allowed.
    verdict: yes
    matchers:
      type: acp_permission
      platform: claude-code
      kind: switch_mode
  - id: perm-think-claude
    title: no subagent thinking here
    text: Never.
    verdict: no
    matchers:
      type: acp_permission
      platform: claude-code
      kind: think
"""
# The options of ExitPlanMode in the adapter (NOTES-layer10.md, part 7 (e)): every allow_always switches the mode
# away from default; the only allow_once keeps default.
PLAN_OPTIONS = [
    {"optionId": "auto", "name": "Yes, and auto mode", "kind": "allow_always"},
    {"optionId": "bypassPermissions", "name": "Yes, and bypass permissions", "kind": "allow_always"},
    {"optionId": "acceptEdits", "name": "Yes, and auto-accept edits", "kind": "allow_always"},
    {"optionId": "default", "name": "Yes, and manually approve edits", "kind": "allow_once"},
    {"optionId": "plan", "name": "No, keep planning", "kind": "reject_once"},
]
LEAKS = ("CHUNK-" + SECRET, "TITLE-" + SECRET, "RAW-" + SECRET, "PLAN-" + SECRET, "PROMPT-" + SECRET,
         "LABEL-" + SECRET, "push@example.invalid", "owner@example.invalid", "org-PLANTED", "Planted Org")


def permission(call_id, name, kind, title, raw, options=OPTIONS):
    """A permission request in the adapter's shape: toolCallId, name, status, rawInput, title, kind."""
    return {"toolCall": {"toolCallId": call_id, "name": name, "status": "pending", "rawInput": raw, "title": title,
                         "kind": kind, "content": [], "locations": []}, "options": options}


def auth_push(kind=None, status=None):
    params = {"authStatus": status if status is not None else
              {"kind": kind, "label": "LABEL-" + SECRET, "account": {"email": "push@example.invalid", "plan": "max"}}}
    return {"notify": {"method": "_auth/status_update", "params": params}}


class TurnCase(ClaudeChatCase):
    def setUp(self):
        super().setUp()
        self.write_rules(RULES)
        self.write_agents(AGENTS)

    def answered(self):
        return [c["answer"]["result"]["outcome"].get("optionId", c["answer"]["result"]["outcome"]["outcome"])
                for c in self.calls() if c.get("event") == "permission_answer"]

    def checks(self):
        return [e for e in self.entries() if e.source == "umwayi check"]

    def assert_no_leak(self, r):
        log = self.log_text()
        queue = (self.root / "queue.md").read_text(encoding="utf-8") if (self.root / "queue.md").exists() else ""
        for text in LEAKS:
            self.assertNotIn(text, log, f"{text} is in the logbook")
            self.assertNotIn(text, queue, f"{text} is in the queue")
            self.assertNotIn(text, r.stderr)
        [new] = self.sent("session/new")
        folder, token = self.canary_args(new)
        self.assertNotIn(token, log)
        self.assertNotIn(token, r.stdout + r.stderr)


# ============================================================================== 10.29


class WholeTurnTests(TurnCase):
    def test_a_whole_turn_hook_first_then_the_rules_and_nothing_of_it_logged(self):
        read = {"claude_tool": {"tool": "Read", "input": {"file_path": "/etc/hostname"}},
                "permission": permission("c1", "Read", "read", "Read TITLE-" + SECRET, {"file_path": "RAW-" + SECRET})}
        ls = {"claude_tool": {"tool": "Bash", "input": {"command": "ls"}},
              "permission": permission("c2", "Bash", "execute", "ls", {"command": "ls RAW-" + SECRET})}
        rm = {"claude_tool": {"tool": "Bash", "input": {"command": "rm -rf /"}},
              "permission": permission("c3", "Bash", "execute", "rm", {"command": "rm -rf /"})}
        plan = {"permission": permission("c4", "ExitPlanMode", "switch_mode", "Ready to code?",
                                         {"plan": "PLAN-" + SECRET}, options=PLAN_OPTIONS)}
        think = {"permission": permission("c5", "Task", "think", "Think it over", {"prompt": "RAW-" + SECRET})}
        turn = [{"chunk": "Working on it CHUNK-" + SECRET + "\n"},
                {"tool_call": {"title": "Read TITLE-" + SECRET, "kind": "read"}},
                read, ls, rm, plan, think, {"chunk": "all done\n"}]
        self.spec({"turns": [turn]})
        r = self.chat(f"go PROMPT-{SECRET}\ny\n:quit\n")  # y: the owner's answer to the Bash ls permission
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("all done", r.stdout)  # the conversation is on the owner's screen, and only there
        # 1. the PreToolUse hook ran first, for every tool call (rm never reached a permission request)
        tools = [(c["tool"], c["decision"]) for c in self.calls() if c.get("event") == "tool"]
        self.assertEqual(tools, [("Read", "allow"), ("Bash", "ask"), ("Bash", "deny")])
        # 2. permission requests answered by the rules: read Yes, execute asked of the owner (y), ExitPlanMode Yes
        #    keeps default (the only allow_once, never an allow_always mode switch), think No
        self.assertEqual(self.answered(), ["o-allow", "o-allow", "default", "o-reject"])
        # 3. one umwayi check entry for each hook call and each permission request, with platform claude-code
        checks = self.checks()
        hook = [e for e in checks if "action type: tool_" in e.added]
        self.assertEqual(len(hook), 3)
        self.assertEqual([e.added.split("action type: ")[1] for e in hook], ["tool_read", "tool_bash", "tool_bash"])
        self.assertIn("hook-read-claude", hook[0].checked)
        self.assertIn("hook-bash-claude", hook[1].checked)
        self.assertIn("bash-no-rm", hook[2].checked)
        perms = [e for e in checks if "action type: acp_permission" in e.added]
        self.assertEqual(len(perms), 4)
        self.assertIn("perm-read-claude", perms[0].checked)
        self.assertIn("rules matched: none", perms[1].checked)  # execute: no rule, so Ask me first
        self.assertIn("perm-plan-claude", perms[2].checked)
        self.assertIn("perm-think-claude", perms[3].checked)
        # 4. the mode stayed default: set_mode default once, and no allow_always option was ever chosen
        self.assertEqual([m["params"]["modeId"] for m in self.sent("session/set_mode")], ["default"])
        self.assertFalse(set(self.answered()) & {"auto", "bypassPermissions", "acceptEdits", "o-always"})
        # 5. nothing of the conversation, the token or the sign-in output in the logbook or the queue
        self.assert_no_leak(r)
        runs = [e.added for e in self.entries() if e.source == "umwayi agent run"]
        self.assertEqual(len(runs), 2)
        self.assertTrue(runs[0].startswith("Started agent reviewer (claude-code, acp, chat): "), runs[0])
        self.assertTrue(runs[1].startswith("Agent reviewer exited with code 0 after "), runs[1])
        self.assertEqual(self.alive_at_exit, [], "an agent process was still running when umwayi exited")
        self.assert_nothing_left()

    def test_exit_codes_follow_10_r8(self):
        cases = (
            ("the end of input after a whole turn", {}, "go\n", 0, False),
            ("the adapter exits in the middle of a turn", {"turns": [[{"exit": 3}]]}, "go\n", 2, False),
            ("the kill switch before the start", {}, "go\n", 3, True),
        )
        for name, spec, owner, code, kill_on in cases:
            with self.subTest(case=name):
                if kill_on:
                    self.kill_on()
                self.spec(spec)
                r = self.chat(owner)
                self.assertEqual(r.returncode, code, r.stdout + r.stderr)
                self.assertNotEqual(r.returncode, 1)


# ============================================================================== 10.36


class AuthWatchTests(TurnCase):
    def running_turn(self, *actions):
        return [{"chunk": "working\n"}, {"spawn": True}, *actions, {"chunk": "still here\n"}, {"sleep": 1},
                {"chunk": "turn over\n"}]

    def test_a_push_that_another_payer_pays_stops_the_chat_mid_turn_with_2(self):
        for kind in ("api_key", "none", "gateway", "external"):
            with self.subTest(kind=kind):
                self.fake_log.unlink(missing_ok=True)  # one chat per subtest: its own calls only
                self.spec({"turns": [self.running_turn(auth_push(kind), {"sleep": 30})]})
                r = self.chat("go\n")
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("The Claude Code login changed and a subscription no longer pays, so agent reviewer "
                              "was stopped (exit 2).", r.stdout)
                self.assertNotIn("turn over", r.stdout)  # stopped in the middle of the turn
                stops = [e for e in self.entries() if e.source == "umwayi agent run" and "was stopped" in e.added]
                self.assertEqual(stops[-1].added, "Agent reviewer was stopped: the Claude Code login changed and a "
                                                  "subscription no longer pays")
                self.assert_agent_gone()  # the adapter and the child it started: the 7b stop
                self.assert_nothing_left()
                self.assert_no_leak(r)

    def test_account_and_unreadable_pushes_change_nothing(self):
        pushes = [auth_push("account"), auth_push(status={"label": "no kind"}), auth_push(status="not an object"),
                  auth_push("API KEY!"), auth_push(status={"kind": 7}),
                  {"notify": {"method": "_auth/status_update"}}]
        self.spec({"turns": [self.running_turn(*pushes)]})
        r = self.chat("go\n:quit\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("turn over", r.stdout)
        self.assertEqual(len([c for c in self.calls() if c.get("event") == "notify_sent"]), len(pushes))
        self.assertFalse(any("subscription no longer pays" in e.added for e in self.entries()))
        self.assert_no_leak(r)

    def test_a_kiro_acp_chat_has_no_watch(self):
        self.kiro_hook_file(command=self.kiro_command(python=sys.executable))
        spec = {"turns": [[{"chunk": "kiro working\n"}, auth_push("api_key"), {"chunk": "kiro done\n"}]]}
        r = self.chat("go\n:quit\n", name="helper", extra={"FAKE_ACP": json.dumps(spec)})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("kiro done", r.stdout)
        self.assertFalse(any("subscription no longer pays" in e.added for e in self.entries()))


if __name__ == "__main__":
    unittest.main()
