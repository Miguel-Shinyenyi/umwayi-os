"""Layer 10 part 6: `umwayi agent chat NAME` with transport acp, for Kiro (tasks.md 10.16 to 10.19).

Every test runs `python -m umwayi ... agent chat ...` as a real child process. The agent is a
scripted fake ACP agent behind `kiro-cli acp` (tests/agents/fake_agent.py, FAKE_ACP). The owner
side is a pipe: either all the owner's lines at once (subprocess.run), or written while the chat
runs (Popen). No test asserts a short duration: they wait for events with generous timeouts.
No real kiro-cli is run.
"""

import json
import os
import signal
import subprocess
import sys
import time
import unittest

from umwayi import acp, agents, runlock, taskqueue

from tests.agents.support import CODES, SECRET, AgentCase, alive

AGENTS = """agents:
  - name: k
    platform: kiro
    command: kiro-cli
    transport: acp
    workdir: {work}
  - name: k-slow
    platform: kiro
    command: kiro-cli
    transport: acp
    workdir: {work}
    timeout_minutes: 1
  - name: k-no
    platform: kiro
    command: kiro-cli
    transport: acp
    workdir: {work}
  - name: k-ask
    platform: kiro
    command: kiro-cli
    transport: acp
    workdir: {work}
"""
RULES = """rules:
  - id: start-ok
    title: may start
    text: Allowed.
    verdict: yes
    matchers:
      type: agent_run
      agent: [k, k-slow]
      mode: chat
      transport: acp
  - id: start-no
    title: never
    text: Never.
    verdict: no
    matchers:
      type: agent_run
      agent: k-no
  - id: start-ask
    title: owner decides
    text: Ask.
    verdict: ask
    matchers:
      type: agent_run
      agent: k-ask
  - id: perm-read
    title: reading is fine
    text: Allowed.
    verdict: yes
    matchers:
      type: acp_permission
      kind: read
  - id: perm-delete
    title: never delete
    text: Never.
    verdict: no
    matchers:
      type: acp_permission
      kind: delete
  - id: perm-execute
    title: commands need the owner
    text: Ask.
    verdict: ask
    matchers:
      type: acp_permission
      kind: execute
  - id: perm-title-trap
    title: would match if the title were in the action
    text: The title is never in the action.
    verdict: no
    matchers:
      type: acp_permission
      title__contains: [TRAP]
  - id: perm-tool
    title: one tool is never allowed
    text: Never.
    verdict: no
    matchers:
      type: acp_permission
      tool: dangerous_tool
"""
OPTIONS = [  # allow_always first, so a test sees that it is never taken
    {"optionId": "o-always", "name": "Always allow", "kind": "allow_always"},
    {"optionId": "o-allow", "name": "Allow once", "kind": "allow_once"},
    {"optionId": "o-never", "name": "Never", "kind": "reject_always"},
    {"optionId": "o-reject", "name": "Reject", "kind": "reject_once"},
]


def perm(kind=None, title="Run a tool", name=None, options=OPTIONS):
    tc = {"toolCallId": "call-1", "title": title, "status": "pending"}
    if kind is not None:
        tc["kind"] = kind
    if name is not None:
        tc["name"] = name
    p = {"toolCall": tc}
    if options is not None:
        p["options"] = options
    return {"permission": p}


class AcpCase(AgentCase):
    def setUp(self):
        super().setUp()
        self.fake("kiro-cli")
        self.write_rules(RULES)
        self.write_agents(AGENTS)
        self.kiro_hook_file(command=self.kiro_command(python=sys.executable))

    def env_for(self, spec, extra=None):
        return dict({"FAKE_ACP": json.dumps(spec or {})}, **(extra or {}))

    def chat(self, owner="", spec=None, name="k", extra=None, fault=None):
        """A chat with all the owner's lines given at once on a pipe."""
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "chat", name],
                           input=owner, capture_output=True, text=True, timeout=120,
                           env=self.env(self.env_for(spec, extra), fault), cwd=str(self.tmp))
        self.assertIn(r.returncode, CODES, r.stdout + r.stderr)
        self.alive_at_exit = self.agent_pids_alive()
        self.wait_root_quiet()
        return r

    def start_chat(self, spec=None, name="k", extra=None):
        """A chat whose owner lines are written while it runs."""
        p = subprocess.Popen([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "chat", name],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             env=self.env(self.env_for(spec, extra)), cwd=str(self.tmp))
        self.addCleanup(self._reap, p)
        return p

    def say(self, p, text):
        p.stdin.write(text)
        p.stdin.flush()

    def sent(self, method):
        return [c["msg"] for c in self.calls() if c.get("event") == "acp_in" and c["msg"].get("method") == method]

    def answers(self):
        return [c["answer"]["result"]["outcome"] for c in self.calls() if c.get("event") == "permission_answer"]

    def chosen(self):
        return [o.get("optionId", o["outcome"]) for o in self.answers()]

    def assert_agent_gone(self):
        self.assertEqual(self.alive_at_exit, [], "an agent process was still running when umwayi exited")
        for c in self.calls():
            if c.get("started") or c.get("event") == "spawn":
                self.assertFalse(alive(c["pid"]))

    def log_text(self):
        p = self.root / "LOGBOOK.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def kill_on(self):
        (self.root / ".umwayi").mkdir(exist_ok=True)
        (self.root / ".umwayi" / "KILL").write_text("", encoding="utf-8")


class TurnTests(AcpCase):
    def test_a_whole_turn(self):
        spec = {"turns": [[{"chunk": "Hello "}, {"tool_call": {"title": "Read notes.md", "kind": "read"}},
                           {"chunk": "all done"}]]}
        r = self.chat(f"hello {SECRET}\n:quit\n", spec)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = r.stdout
        self.assertLess(out.index("Open in the queue: 0 item(s)."), out.index("Connected."))
        self.assertIn("Hello ", out)
        self.assertIn("tool: Read notes.md [read]", out)
        self.assertIn("all done", out)
        self.assertIn("[stop reason: end_turn]", out)
        [init] = self.sent("initialize")
        self.assertEqual(init["params"]["protocolVersion"], 1)
        self.assertEqual(init["params"]["clientCapabilities"], {})  # no fs, no terminal
        self.assertEqual(init["params"]["clientInfo"]["name"], "umwayi")
        [new] = self.sent("session/new")
        self.assertEqual(new["params"], {"cwd": str(self.work), "mcpServers": []})
        [prompt] = self.sent("session/prompt")
        self.assertEqual(prompt["params"], {"sessionId": "sess-1", "prompt": [{"type": "text", "text": f"hello {SECRET}"}]})
        [start] = self.started()
        self.assertEqual(start["argv"], ["acp", "--agent-engine=v3"])
        added = [e.added for e in self.run_entries()]
        self.assertTrue(added[0].startswith("Started agent k (kiro, acp, chat): "), added)
        self.assertTrue(added[-1].startswith("Agent k exited with code 0"), added)
        self.assert_agent_gone()

    def test_the_end_of_owner_input_ends_the_chat_with_0(self):
        r = self.chat("one\ntwo\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([m["params"]["prompt"][0]["text"] for m in self.sent("session/prompt")], ["one", "two"])
        self.assertIn("you said: two", r.stdout)

    def test_umwayi_commands_are_not_sent_to_the_agent(self):
        taskqueue.add(self.root, "decision", "Publish the article?", "", "2026-11-08")
        r = self.chat(":queue\n:nope\n:quit\n")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Q-0001 (decision): Publish the article?", r.stdout.split("Connected.")[1])
        self.assertIn("Unknown umwayi command. Use :queue or :quit.", r.stdout)
        self.assertEqual(self.sent("session/prompt"), [])

    def test_other_update_types_are_ignored(self):
        spec = {"turns": [[{"update": {"sessionUpdate": "plan", "entries": []}},
                           {"update": {"sessionUpdate": "something_new_in_v3", "x": 1}},
                           {"update": "not an object"}, {"update": {"sessionUpdate": "agent_message_chunk", "content": 5}},
                           {"chunk": "still fine"}]]}
        r = self.chat("go\n:quit\n", spec)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("still fine", r.stdout)

    def test_agent_stderr_goes_to_umwayi_stderr(self):
        r = self.chat(":quit\n", {"stderr": "fake-kiro: a log line"})
        self.assertIn("fake-kiro: a log line", r.stderr)

    def test_control_bidi_zero_width_and_tag_characters_are_made_visible(self):
        evil = "a\x1b[2Jb\u202ec\u200bd\U000e0041e\x9bf\rg"
        spec = {"turns": [[{"chunk": evil}, {"tool_call": {"title": f"rm {evil}", "kind": "exe\x1bcute"}}]]}
        r = self.chat("go\n:quit\n", spec)
        self.assertEqual(r.returncode, 0)
        shown = "a\\u001b[2Jb\\u202ec\\u200bd\\U000e0041e\\u009bf\\u000dg"
        self.assertIn(shown, r.stdout)
        self.assertIn(f"tool: rm {shown} [exe\\u001bcute]", r.stdout)
        for raw in ("\x1b", "\u202e", "\u200b", "\U000e0041", "\x9b", "\r"):
            self.assertNotIn(raw, r.stdout)

    def test_nothing_of_the_conversation_is_in_the_logbook(self):
        spec = {"turns": [[{"chunk": f"agent says {SECRET}"}, {"tool_call": {"title": f"tool {SECRET}", "kind": "read"}},
                           perm(kind="read", title=f"permission {SECRET}")]]}
        r = self.chat(f"owner says {SECRET}\n:quit\n", spec)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.chosen(), ["o-allow"])
        log = self.log_text()
        self.assertNotIn(SECRET, log)
        self.assertNotIn("sk-live", log)
        self.assertIn("action type: acp_permission", log)


class PermissionTests(AcpCase):
    def test_yes_no_and_ask_me_first_answered_y_n_and_empty(self):
        spec = {"turns": [[perm("read")], [perm("delete")], [perm("execute")], [perm("execute")], [perm("execute")],
                          [perm("execute")]]}
        r = self.chat("1\n2\n3\ny\n4\nn\n5\n\n6\nyes\n:quit\n", spec)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # Yes, No, Ask+y, Ask+n, Ask+empty, Ask+"yes" (only y allows)
        self.assertEqual(self.chosen(), ["o-allow", "o-reject", "o-allow", "o-reject", "o-reject", "o-reject"])
        self.assertEqual(r.stdout.count("Allow once? [y/N]"), 4)
        checks = [e for e in self.entries() if "acp_permission" in e.added]
        self.assertEqual(len(checks), 6)  # one logbook entry per permission request

    def test_never_an_always_option_and_never_an_invented_one(self):
        cases = [
            (perm("read", options=[OPTIONS[0], OPTIONS[3]]), "o-reject"),  # Yes, only allow_always: reject_once
            (perm("read", options=[OPTIONS[0]]), "cancelled"),  # Yes, nothing usable: cancelled
            (perm("read", options=[OPTIONS[0], OPTIONS[2]]), "cancelled"),  # only *_always
            (perm("delete", options=[OPTIONS[1]]), "cancelled"),  # No, no reject option: cancelled
            (perm("read", options="not a list"), "cancelled"),
            (perm("read", options=None), "cancelled"),
            (perm("read", options=[{"optionId": 5, "kind": "allow_once"}, {"kind": "reject_once"}]), "cancelled"),
        ]
        spec = {"turns": [[c[0]] for c in cases]}
        r = self.chat("".join(f"{i}\n" for i in range(len(cases))) + ":quit\n", spec)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.chosen(), [c[1] for c in cases])

    def test_the_title_is_never_in_the_action_but_kind_and_a_plain_tool_name_are(self):
        spec = {"turns": [[perm("read", title="TRAP read a file")],  # a title rule would say No
                          [perm("read", name="dangerous_tool")],  # a plain tool name is in the action: No
                          [perm("read", name="dangerous tool!")],  # not a plain word: left out, so Yes
                          [perm("rea d")]]}  # a kind that is not a plain word: left out, no rule: Ask
        r = self.chat("1\n2\n3\n4\nn\n:quit\n", spec)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.chosen(), ["o-allow", "o-reject", "o-allow", "o-reject"])

    def test_a_permission_while_the_kill_switch_is_on_is_rejected(self):
        p = self.start_chat({"turns": [[{"sleep": 0}, {"wait_cancel": True}]]})
        self.say(p, "go\n")
        self.wait_for(lambda c: c.get("event") == "acp_in" and c["msg"].get("method") == "session/prompt", timeout=60)
        # the rules check itself, in process, while the switch is on
        run = agents._Run(self.root, agents.find(agents.load(self.root), "k"), None, lambda: "2026-11-08",
                          mode=agents.CHAT)
        self.kill_on()
        self.assertEqual(run._permission({"kind": "read"}), acp.REJECT)
        code, out, _ = self.finish(p, timeout=90)
        self.assertEqual(code, 3, out)


class PermissionCheckTests(AcpCase):
    """In process: _Run._permission, the rules check behind every ACP permission answer."""

    def run_obj(self):
        return agents._Run(self.root, agents.find(agents.load(self.root), "k"), None, lambda: "2026-11-08",
                           mode=agents.CHAT)

    def test_yes_ask_and_no_from_the_rules(self):
        run = self.run_obj()
        self.assertEqual(run._permission({"kind": "read"}), acp.ALLOW)
        self.assertEqual(run._permission({"kind": "execute"}), acp.ASK)
        self.assertEqual(run._permission({"kind": "delete"}), acp.REJECT)
        self.assertEqual(run._permission({"kind": "read", "title": "TRAP"}), acp.ALLOW)
        self.assertEqual(len([e for e in self.entries() if "acp_permission" in e.added]), 4)

    def test_a_check_that_cannot_be_logged_is_a_reject(self):
        (self.root / "LOGBOOK.md").write_text("# Logbook\n\nedited by hand\n", encoding="utf-8")
        self.assertEqual(self.run_obj()._permission({"kind": "read"}), acp.REJECT)

    def test_the_kill_switch_makes_every_permission_a_reject(self):
        self.kill_on()
        self.assertEqual(self.run_obj()._permission({"kind": "read"}), acp.REJECT)


class RefusedRequestTests(AcpCase):
    def test_fs_and_terminal_requests_get_method_not_found_and_nothing_is_read_or_run(self):
        secret_file = self.tmp / "secret.txt"
        secret_file.write_text(SECRET, encoding="utf-8")
        marker = self.tmp / "ran"
        spec = {"turns": [[{"request": {"method": "fs/read_text_file", "params": {"sessionId": "sess-1",
                                                                                  "path": str(secret_file)}}},
                           {"request": {"method": "fs/write_text_file", "params": {"path": str(marker), "content": "x"}}},
                           {"request": {"method": "terminal/create", "params": {"command": "touch", "args": [str(marker)]}}},
                           {"request": {"method": "_kiro/auth/getAccessToken", "params": {}}}]]}
        r = self.chat("go\n:quit\n", spec)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        answers = [c["answer"] for c in self.calls() if c.get("event") == "request_answer"]
        self.assertEqual(len(answers), 4)
        for a in answers:
            self.assertEqual(a["error"]["code"], -32601)
            self.assertNotIn("result", a)
        self.assertFalse(marker.exists())
        self.assertNotIn(SECRET, r.stdout + r.stderr + json.dumps(answers))


class EndsTests(AcpCase):
    def test_protocol_version_2_ends_with_2(self):
        r = self.chat("hello\n", {"init": {"protocolVersion": 2}})
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("protocol version 2", r.stdout)
        self.assertEqual(self.sent("session/new"), [])
        self.assertIn("ACP chat with agent k ended: the agent answered another protocol version than 1",
                      self.run_entries()[-1].added)
        self.assert_agent_gone()

    def test_an_initialize_error_and_a_sign_in_error(self):
        r = self.chat("hello\n", {"init": {"error": {"code": -32603, "message": "boom"}}})
        self.assertEqual(r.returncode, 2)
        self.assertIn("answered initialize with an error", r.stdout)
        r = self.chat("hello\n", {"new": {"error": {"code": -32000, "message": "Authentication required"}}})
        self.assertEqual(r.returncode, 2)
        self.assertIn("Sign in with kiro-cli login, then try again.", r.stdout)
        self.assertEqual(self.sent("session/prompt"), [])

    def test_a_garbage_line_and_a_line_over_4_mb_end_with_2(self):
        for label, act in (("garbage", {"garbage": "this is not { json"}), ("array", {"garbage": "[1, 2]"}),
                           ("empty", {"garbage": ""}), ("big", {"big": 4 * 1024 * 1024 + 10})):
            with self.subTest(case=label):
                os.remove(self.fake_log) if self.fake_log.exists() else None
                r = self.chat("go\nagain\n", {"turns": [[act]]})
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertEqual(len(self.sent("session/prompt")), 1)
                self.assert_agent_gone()
        self.assertIn("a line longer than 4 MB", r.stdout)

    def test_a_dropped_connection_ends_the_chat_and_the_prompt_is_not_sent_again(self):
        r = self.chat("go\nsecond\n", {"turns": [[{"chunk": "part"}, {"exit": 0}]]})
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("The agent closed the connection", r.stdout)
        self.assertEqual(len(self.sent("session/prompt")), 1)
        self.assertEqual(len(self.started()), 1)

    def test_an_agent_that_does_not_exit_after_the_chat_is_stopped_and_2(self):
        r = self.chat(":quit\n", {"ignore_eof": True})
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("did not exit after the chat ended", r.stdout)
        self.assert_agent_gone()

    def test_a_broken_logbook_before_the_start_starts_nothing(self):
        (self.root / "LOGBOOK.md").write_text("# Logbook\n\nedited by hand\n", encoding="utf-8")
        r = self.chat("hi\n")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("nothing is started", r.stdout)
        self.assertEqual(self.calls(), [])

    def test_start_steps(self):
        self.assertEqual(self.chat("hi\n", name="k-no").returncode, 2)
        self.assertEqual(self.chat("hi\n", name="k-ask").returncode, 3)
        self.assertEqual(self.chat("hi\n", name="k-ask").returncode, 3)
        self.assertEqual([x.title for x in taskqueue.list_rows(self.root, status="open")], ["Start agent k-ask (chat)?"])
        with runlock.held(self.root):
            self.assertEqual(self.chat("hi\n").returncode, 3)
        for f in (self.work / ".kiro" / "hooks").iterdir():
            f.unlink()
        r = self.chat("hi\n")
        self.assertEqual(r.returncode, 2)
        self.assertIn("no: kiro hook file", r.stdout)
        self.kill_on()
        self.assertEqual(self.chat("hi\n").returncode, 3)
        self.assertEqual(self.started(), [])


class StopTests(AcpCase):
    def running(self, spec, name="k", extra=None):
        p = self.start_chat(spec, name=name, extra=extra)
        self.say(p, "go\n")
        self.wait_for(lambda c: c.get("event") == "acp_in" and c["msg"].get("method") == "session/prompt",
                      timeout=60, what="the prompt")
        return p

    def test_the_kill_switch_cancels_and_stops(self):
        p = self.running({"turns": [[{"spawn": True}, {"wait_cancel": True}]]})
        self.wait_for(lambda c: c.get("event") == "spawn", timeout=60)
        self.kill_on()
        # generous on purpose: the switch is checked every second and SIGKILL follows after 10 s
        code, out, _ = self.finish(p, timeout=30)
        self.assertEqual(code, 3, out)
        self.assertIn("The kill switch stopped agent k (exit 3).", out)
        self.wait_for(lambda c: c.get("event") == "got_cancel", timeout=5, what="session/cancel")
        self.assert_agent_gone()

    def test_sigterm_to_umwayi_stops_the_chat(self):
        p = self.running({"turns": [[{"spawn": True}, {"wait_cancel": True}]]})
        self.wait_for(lambda c: c.get("event") == "spawn", timeout=60)
        p.send_signal(signal.SIGTERM)
        code, out, _ = self.finish(p, timeout=90)
        self.assertEqual(code, 2, out)
        self.assertEqual(self.run_entries()[-1].added, "Agent k was stopped: umwayi got SIGTERM")
        self.assert_agent_gone()

    def test_the_timeout_stops_the_chat(self):
        p = self.running({"turns": [[{"wait_cancel": True}]]}, name="k-slow", extra={"UMWAYI_TEST_MINUTE": "2"})
        code, out, _ = self.finish(p, timeout=90)
        self.assertEqual(code, 2, out)
        self.assertIn("timeout of 1 min", out)
        self.assert_agent_gone()

    def test_a_failing_logbook_stops_the_chat(self):
        p = self.running({"turns": [[{"wait_cancel": True}]]})
        with open(self.root / "LOGBOOK.md", "a", encoding="utf-8") as f:
            f.write("edited by hand\n")
        code, out, _ = self.finish(p, timeout=90)
        self.assertEqual(code, 2, out)
        self.assertIn("The logbook can no longer be written", out)
        self.assert_agent_gone()


class CrashTests(AcpCase):
    def test_an_unexpected_error_in_umwayi_during_an_acp_chat_stops_the_agent(self):
        r = self.chat("go\n", {"turns": [[{"spawn": True}, {"wait_cancel": True}]]},
                      fault="umwayi.logbook:check_writable:crash", extra={"UMWAYI_FAULT_TEXT": SECRET})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("stopped by an unexpected error (RuntimeError)", r.stderr)
        self.assertNotIn(SECRET, r.stdout + r.stderr)
        self.assertIn("umwayi hit an unexpected error (RuntimeError)", self.run_entries()[-1].added)
        self.assert_agent_gone()


class CtrlCTests(AcpCase):
    def test_ctrl_c_answers_open_permissions_cancelled_cancels_the_turn_and_umwayi_goes_on(self):
        p = self.start_chat({"turns": [[perm("execute"), {"wait_cancel": True}]]})
        self.say(p, "go\n")
        self.wait_for(lambda c: c.get("event") == "request_sent", timeout=60, what="the permission request")
        time.sleep(0.5)  # umwayi now asks the owner "Allow once?"
        p.send_signal(signal.SIGINT)
        self.wait_for(lambda c: c.get("event") == "permission_answer", timeout=60)
        self.assertEqual(self.answers(), [{"outcome": "cancelled"}])
        self.wait_for(lambda c: c.get("event") == "got_cancel", timeout=60, what="session/cancel")
        self.assertIsNone(p.poll(), "Ctrl-C stopped umwayi")
        self.say(p, "after\n:quit\n")
        p.stdin.close()
        code, out, err = self.finish(p, timeout=90)
        self.assertEqual(code, 0, out + err)
        self.assertIn("[stop reason: cancelled]", out)
        self.assertIn("you said: after", out)
        self.assert_agent_gone()

    def test_ctrl_c_with_no_turn_running_does_nothing(self):
        p = self.start_chat({})
        self.wait_for(lambda c: c.get("event") == "acp_in" and c["msg"].get("method") == "session/new", timeout=60)
        time.sleep(0.5)
        p.send_signal(signal.SIGINT)
        time.sleep(0.5)
        self.assertIsNone(p.poll())
        self.say(p, ":quit\n")
        p.stdin.close()
        code, out, _ = self.finish(p, timeout=90)
        self.assertEqual(code, 0)
        self.assertIn("no turn is running", out)

    def test_an_agent_that_ignores_the_cancel_gives_the_owner_back_after_10_seconds(self):
        p = self.start_chat({"turns": [[{"ignore_cancel": 60}]]})
        self.say(p, "go\n")
        self.wait_for(lambda c: c.get("event") == "acp_in" and c["msg"].get("method") == "session/prompt", timeout=60)
        time.sleep(0.5)
        p.send_signal(signal.SIGINT)
        self.say(p, ":quit\n")  # read only after the 10 s cancel wait
        p.stdin.close()
        code, out, _ = self.finish(p, timeout=120)
        self.assertIn("did not answer the cancel within 10 s", out)
        self.assertEqual(code, 2)  # the agent was busy and did not exit after the chat, so it was stopped
        self.assert_agent_gone()


class UnitTests(unittest.TestCase):
    def test_select_outcome(self):
        self.assertEqual(acp.select_outcome(OPTIONS, "allow_once"), {"outcome": "selected", "optionId": "o-allow"})
        self.assertEqual(acp.select_outcome(OPTIONS, "reject_once"), {"outcome": "selected", "optionId": "o-reject"})
        self.assertEqual(acp.select_outcome([OPTIONS[0]], "allow_once"), {"outcome": "cancelled"})
        self.assertEqual(acp.select_outcome([OPTIONS[1]], "reject_once"), {"outcome": "cancelled"})
        self.assertEqual(acp.select_outcome([OPTIONS[3]], "allow_once"), {"outcome": "selected", "optionId": "o-reject"})
        self.assertEqual(acp.select_outcome(None, "allow_once"), {"outcome": "cancelled"})

    def test_an_unknown_answer_from_the_rules_is_reject(self):
        for answer in ("Maybe", None, "", "yes", 3):
            self.assertEqual(agents.permission_verdict(answer), acp.REJECT)
        self.assertEqual(agents.permission_verdict("Yes"), acp.ALLOW)
        self.assertEqual(agents.permission_verdict("Ask me first"), acp.ASK)
        self.assertEqual(agents.permission_verdict("No"), acp.REJECT)

    def test_the_permission_action(self):
        a = agents.permission_action("k", {"title": "TRAP", "kind": "execute", "name": "execute_bash", "rawInput": {"x": 1},
                                           "locations": [{"path": "/etc"}]})
        self.assertEqual(a, {"type": "acp_permission", "agent": "k", "platform": "kiro", "kind": "execute",
                             "tool": "execute_bash"})
        self.assertEqual(agents.permission_action("k", {"kind": "Execute!", "name": "a b"}),
                         {"type": "acp_permission", "agent": "k", "platform": "kiro"})
        self.assertEqual(agents.permission_action("k", "not a dict"), {"type": "acp_permission", "agent": "k",
                                                                        "platform": "kiro"})

    def test_safe_text_keeps_newline_and_tab(self):
        self.assertEqual(acp.safe_text("a\nb\tc é ✓"), "a\nb\tc é ✓")
        self.assertEqual(acp.safe_text("\x00\x7f\u2066\u2069\ufeff\u2028"), "\\u0000\\u007f\\u2066\\u2069\\ufeff\\u2028")

    def test_the_acp_argument_list(self):
        a = agents.Agent("k", "kiro", "kiro-cli", "acp", "/w")
        argv, stdin = agents.build_argv(a, agents.CHAT, "/bin/kiro-cli", "/r", "/usr/bin/python3")
        self.assertEqual(argv, ["/bin/kiro-cli", "acp", "--agent-engine=v3"])
        self.assertIsNone(stdin)
        for bad in ("--agent", "--model", "--effort", "--trust-all-tools", "--trust-tools") + agents.FORBIDDEN_FLAGS:
            self.assertFalse(any(w == bad or w.startswith(bad + "=") for w in argv))


class AcpCodeGuardTests(unittest.TestCase):
    def test_acp_py_is_small_standard_library_only_and_starts_nothing(self):
        import ast
        src = (agents.Path(acp.__file__)).read_text(encoding="utf-8")
        tree = ast.parse(src)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertLessEqual(imported, {"__future__", "json", "os", "queue", "re", "threading", "time", "collections"})
        self.assertEqual([n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
                          and isinstance(n.value, ast.Name) and n.value.id == "os"], ["read"])  # os.read only
        for bad in ("subprocess", "socket", "Popen", "os.system", '"allow_always"', '"reject_always"'):
            self.assertNotIn(bad, src)  # it starts nothing, and never names an *_always option to choose it


if __name__ == "__main__":
    unittest.main()
