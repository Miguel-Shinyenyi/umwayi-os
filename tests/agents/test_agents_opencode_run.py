"""W9.13: `umwayi agent run o` for an OpenCode agent (docs/opencode-goal-helper-design.md, rules R1 to R14).

Every test runs `python -m umwayi agent run o ...` as a real child process with the fake `opencode acp` of
tests/agents/fake_opencode.py and a copy of the source tree, the way the chat tests do. A run is the chat start with the
owner taken out: the same gate checks, canary and model compare, then one `session/prompt` with the given prompt, the
agent's message text on standard output, and the end at the first answer. Each rule has a planted fault: the test
asserts what the rule says, and the fault is the opposite of it.
"""

import json
import re
import subprocess
import sys
import unittest

from umwayi import acp, agents

from tests.agents.support import alive
from tests.agents.test_agents_opencode_chat import ChatCase
from tests.agents.test_agents_opencode_gate import YES_RULE
from tests.agents.test_agents_opencode_turns import RULES, tool

RUN_ID = re.compile(r"run ([0-9a-f]{16})")


class RunCase(ChatCase):
    def run_run(self, prompt="Say hello.", extra=None, fault=None, acp_spec=None, args=(), timeout=180):
        if acp_spec is not None:
            self.spec(acp_spec)
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "run", "o", "--prompt",
                            prompt, *args], capture_output=True, text=True, timeout=timeout,
                           env=self.env(self.env_extra(extra), fault), cwd=str(self.tmp))
        self.assertIn(r.returncode, {0, 2, 3, 64}, r.stdout + r.stderr)  # R12: never 1
        self.alive_at_exit = self.agent_pids_alive()
        self.wait_root_quiet()
        return r

    def prompts(self):
        return self.sent("session/prompt")

    def new_sessions(self):
        return self.sent("session/new")


class WhatARunDoesTests(RunCase):
    def test_a_run_sends_one_prompt_and_prints_only_the_message_text(self):
        """R5, R8: one session/prompt, and only the agent's message text on standard output; nothing else of the chat."""
        r = self.run_run("Reply with a tag.", acp_spec={"turns": [[{"chunk": "first part, "}, {"chunk": "UMWAYI-RESULT n {}"}]]})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("first part, UMWAYI-RESULT n {}", r.stdout)
        for never in ("Connected.", "[stop reason", "tool:", "Type a message"):
            self.assertNotIn(never, r.stdout)
        [prompt] = self.prompts()
        self.assertEqual(prompt["params"]["prompt"], [{"type": "text", "text": "Reply with a tag."}])
        self.assertIn("Agent o finished (exit 0)", r.stdout)
        self.assert_agent_gone()
        self.assert_nothing_left()

    def test_the_program_is_opencode_acp_and_never_opencode_run_or_a_shell(self):
        """R1."""
        self.run_run()
        rec = self.start_record()
        self.assertEqual(rec["argv"], ["acp"])
        self.assertEqual(rec["mode"], "acp")

    def test_planted_fault_the_argument_list_with_run_is_refused_by_the_builder(self):
        a = agents.Agent("o", "opencode", "opencode", "acp", "/w", provider="ollama", model="ollama/m")
        argv, stdin = agents.build_argv(a, agents.RUN, "/usr/bin/opencode", self.root, sys.executable)
        self.assertEqual(argv, ["/usr/bin/opencode", "acp"])
        self.assertIsNone(stdin)
        self.assertNotIn("run", argv)

    def test_no_file_and_no_terminal_capability_is_offered(self):
        """R7: clientCapabilities is empty."""
        self.run_run()
        [init] = self.sent("initialize")
        self.assertEqual(init["params"]["clientCapabilities"], {})

    def test_the_session_is_new_in_the_agents_workdir_with_no_mcp_server(self):
        self.run_run()
        [new] = self.new_sessions()
        self.assertEqual(new["params"]["mcpServers"], [])
        self.assertNotIn("_meta", new["params"])

    def test_the_start_entry_names_the_platform_the_transport_and_the_mode(self):
        """R13."""
        self.run_run()
        started = [e for e in self.run_entries() if e.added.startswith("Started agent o")]
        self.assertEqual(len(started), 1)
        self.assertIn("(opencode, acp)", started[0].added)
        self.assertIn("enforcement:", started[0].checked)
        self.assertIn("agent_run (run)", started[0].checked)


class BeforeThePromptTests(RunCase):
    def test_no_prompt_is_sent_before_the_canary(self):
        """R3: a canary that never comes is exit 2 with no prompt sent."""
        r = self.run_run(acp_spec={"canary": "never"}, extra={"UMWAYI_TEST_GATE_WAIT": "2"})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(self.prompts(), [])
        self.assertIn("Refused agent o: the first gate could not be confirmed in the ACP session", self.log_text())
        self.assert_agent_gone()
        self.assert_nothing_left()

    def test_a_late_canary_is_waited_for_and_then_the_prompt_goes(self):
        r = self.run_run(acp_spec={"canary": "late", "canary_delay": 1.5})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(self.prompts()), 1)

    def test_a_wrong_canary_is_not_a_canary(self):
        r = self.run_run(acp_spec={"canary": "wrong"}, extra={"UMWAYI_TEST_GATE_WAIT": "2"})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(self.prompts(), [])

    def test_a_model_that_is_not_the_agents_is_exit_2_with_no_prompt(self):
        """R4, with no case folding."""
        for model in ("other/model", "OLLAMA/M"):
            with self.subTest(model=model):
                self.setUp()
                r = self.run_run(acp_spec={"model": model})
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertEqual(self.prompts(), [])
                self.assertIn("The agent reported another model than ollama/m", r.stdout)

    def test_a_sign_in_is_asked_for_and_nothing_is_signed_in(self):
        r = self.run_run(acp_spec={"auth_required": "prompt"})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("Run opencode auth login first, then try again.", r.stdout)


class OptionsAndRulesTests(RunCase):
    def test_an_effort_is_refused_for_an_opencode_agent(self):
        """R9: 64, before anything is written."""
        r = self.run_run(args=("--effort", "high"))
        self.assertEqual(r.returncode, 64, r.stdout + r.stderr)
        self.assertIn("--effort is not offered for an OpenCode agent", r.stdout + r.stderr)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.log_text(), "")

    def test_a_model_that_is_not_the_agents_is_refused_and_the_agents_own_is_taken(self):
        r = self.run_run(args=("--model", "ollama/other"))
        self.assertEqual(r.returncode, 64, r.stdout + r.stderr)
        self.assertEqual(self.log_text(), "")
        ok = self.run_run(args=("--model", "ollama/m"))
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.assertEqual(self.start_record()["argv"], ["acp"])  # the model is never an argument

    def test_login_is_still_refused_for_opencode(self):
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "login", "o"],
                           capture_output=True, text=True, timeout=60, env=self.env(self.env_extra()), cwd=str(self.tmp))
        self.assertEqual(r.returncode, 64, r.stdout + r.stderr)

    def test_with_no_yes_rule_for_agent_run_nothing_starts(self):
        """R14 for the run itself: no rule means Ask me first, exit 3, nothing started."""
        self.write_rules("rules:\n  - id: other\n    title: other\n    text: x\n    verdict: yes\n    matchers:\n      type: agent_run\n      agent: nobody\n")
        r = self.run_run()
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertEqual(self.calls(), [])

    def test_the_kill_switch_stops_a_run_before_it_starts(self):
        self.kill_on()
        r = self.run_run()
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertEqual(self.calls(), [])


class PermissionsTests(RunCase):
    def setUp(self):
        super().setUp()
        self.write_rules(RULES)

    def answers(self):
        return [c["outcome"] for c in self.calls() if c.get("event") == "permission_answer"]

    def test_an_ask_me_first_is_rejected_and_the_run_goes_on(self):
        """R6: the edit request is Ask me first in these rules, and nobody is there to answer."""
        r = self.run_run(acp_spec={"turns": [[tool("write", path="x.py", content="x = 1"), {"chunk": "done"}]]})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("done", r.stdout)
        self.assertEqual(self.answers(), ["reject"])
        self.assertNotIn("The agent asks to use a tool", r.stdout)

    def test_a_yes_is_allowed_once_and_always_is_never_chosen(self):
        r = self.run_run(acp_spec={"turns": [[tool("read", path="README.md"), {"chunk": "read it"}]]})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.answers(), ["once"])
        self.assertNotIn("always", self.answers())

    def test_a_no_is_rejected(self):
        r = self.run_run(acp_spec={"turns": [[tool("grep", pattern="x"), {"chunk": "searched"}]]})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.answers(), ["reject"])

    def test_the_tool_line_of_the_chat_is_not_printed_and_no_tool_output_is_taken_as_the_agents_text(self):
        """R8: a tool title never reaches standard output, so it cannot carry a tag."""
        r = self.run_run(acp_spec={"turns": [[tool("read", path="UMWAYI-RESULT-in-a-path.md"), {"chunk": "ok"}]]})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("UMWAYI-RESULT-in-a-path", r.stdout)

    def test_every_permission_request_is_one_logbook_check(self):
        self.run_run(acp_spec={"turns": [[tool("read", path="a.md"), tool("write", path="b.py", content="x")]]})
        perms = [e for e in self.entries() if e.source == "umwayi check" and "action type: acp_permission" in e.added]
        self.assertEqual(len(perms), 2)


class StopTests(RunCase):
    def test_the_kill_switch_during_a_run_stops_it(self):
        """R11."""
        self.spec({"turns": [[{"chunk": "working"}, {"sleep": 60}]]})
        p = subprocess.Popen([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "run", "o", "--prompt", "go"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, stdin=subprocess.DEVNULL,
                             env=self.env(self.env_extra()), cwd=str(self.tmp))
        self.addCleanup(self._reap, p)
        self.wait_for(lambda c: c.get("event") == "acp_in" and c["msg"].get("method") == "session/prompt", "the prompt")
        self.kill_on()
        code, out, _ = self.finish(p)
        self.assertEqual(code, 3, out)
        self.assertIn("The kill switch stopped agent o (exit 3).", out)
        self.assert_agent_gone()
        self.assert_nothing_left()

    def test_the_timeout_stops_a_run(self):
        self.write_agents(self.agents_text_with_timeout(1))
        self.spec({"turns": [[{"sleep": 120}]]})
        r = self.run_run(extra={"UMWAYI_TEST_MINUTE": "1"}, timeout=120)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("timeout", (r.stdout + self.log_text()).lower())
        self.assert_agent_gone()

    def agents_text_with_timeout(self, minutes):
        from tests.agents.test_agents_opencode_gate import oc
        return oc(provider="ollama", model="ollama/m", workdir=str(self.deep), extra=f"    timeout_minutes: {minutes}\n")

    def test_the_agent_leaves_nothing_running_when_the_run_ends(self):
        r = self.run_run(acp_spec={"turns": [[{"spawn": True}, {"chunk": "started it"}]]})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_agent_gone()
        self.assert_nothing_left()


class BudgetTests(RunCase):
    def test_a_run_is_declared_or_unknown_never_measured(self):
        """R10: no units.yaml rate for opencode means unknown, counted at the worst case."""
        self.run_run()
        text = self.log_text()
        settles = re.findall(r"Settled run [0-9a-f]{16} for agent o \(opencode\): (\w+)", text)
        self.assertTrue(settles, text)
        self.assertEqual(set(settles), {"unknown"})
        self.assertNotIn("measured", " ".join(settles))

    def test_a_declared_rate_makes_it_declared(self):
        (self.root / "units.yaml").write_text(
            "version: 1\nlimits:\n  per_day: 1000000\n  per_agent_per_day: 1000000\n  per_platform_per_day: 1000000\n"
            "platforms:\n  opencode:\n    reading: runs\n    run_micros:\n      value: 150000\n      date: 2026-11-17\n"
            "      source: owner\n", encoding="utf-8")
        r = self.run_run()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(re.findall(r"Settled run [0-9a-f]{16} for agent o \(opencode\): (\w+) (\d+) micros", self.log_text()),
                         [("declared", "150000")])


if __name__ == "__main__":
    unittest.main()
