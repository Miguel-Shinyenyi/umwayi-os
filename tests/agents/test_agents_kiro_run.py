"""Layer 10 part 4: `umwayi agent run` for Kiro (tasks.md 10.12 and 10.13).

Every test runs `python -m umwayi ... agent run ...` as a real child process. The fake
`kiro-cli` reads the instruction from stdin, runs the hook command from the hook file it
finds the way the Kiro hook docs describe, and denies any tool not in --trust-tools.
No real kiro-cli is run.
"""

import os
import shutil
import signal
import subprocess
import sys
import time
import unittest

from umwayi import agents, taskqueue

from tests.agents.support import SECRET, AgentCase, alive

AGENTS = """agents:
  - name: kiro
    platform: kiro
    command: kiro-cli
    workdir: {work}
    trust_tools: [read_file, fs_write]
  - name: kiro-agent
    platform: kiro
    command: kiro-cli
    workdir: {work}
    kiro_agent: site-agent
    trust_tools: [read_file]
  - name: kiro-none
    platform: kiro
    command: kiro-cli
    workdir: {work}
  - name: kiro-slow
    platform: kiro
    command: kiro-cli
    workdir: {work}
    trust_tools: [read_file]
    timeout_minutes: 1
  - name: kiro-acp
    platform: kiro
    command: kiro-cli
    transport: acp
    workdir: {work}
    trust_tools: [read_file]
  - name: kiro-no
    platform: kiro
    command: kiro-cli
    workdir: {work}
  - name: kiro-ask
    platform: kiro
    command: kiro-cli
    workdir: {work}
"""
RULES = """rules:
  - id: kiro-start
    title: these Kiro agents may start
    text: Allowed.
    verdict: yes
    matchers:
      type: agent_run
      agent: [kiro, kiro-agent, kiro-none, kiro-slow, kiro-acp]
  - id: kiro-start-no
    title: never
    text: Never.
    verdict: no
    matchers:
      type: agent_run
      agent: kiro-no
  - id: kiro-start-ask
    title: owner decides
    text: Ask.
    verdict: ask
    matchers:
      type: agent_run
      agent: kiro-ask
  - id: kiro-read
    title: read and search
    text: Allowed.
    verdict: yes
    matchers:
      platform: kiro
      type: [tool_read_file, tool_grep_search]
  - id: kiro-no-write
    title: no writes
    text: Never.
    verdict: no
    matchers:
      platform: kiro
      type: tool_fs_write
  - id: kiro-ask-shell
    title: shell asks
    text: Ask.
    verdict: ask
    matchers:
      platform: kiro
      type: tool_execute_bash
"""
READ = {"do": "tool", "tool": "read_file", "input": {"path": "/etc/hostname"}}
GREP = {"do": "tool", "tool": "grep_search", "input": {"pattern": "x"}}
WRITE = {"do": "tool", "tool": "fs_write", "input": {"path": "/tmp/x", "text": "y"}}
BASH = {"do": "tool", "tool": "execute_bash", "input": {"command": "ls"}}
LOOP = {"do": "loop_tools", "tool": "read_file", "input": {"path": "/etc/hostname"}, "every": 0.2, "for": 40}
LAST_READ = {"do": "term_tool", "tool": "read_file", "input": {"path": "/etc/hostname"}}


class KiroRunCase(AgentCase):
    def setUp(self):
        super().setUp()
        self.fake("kiro-cli")
        self.fake("claude")
        self.write_rules(RULES)
        self.write_agents(AGENTS)
        self.hook_file = self.kiro_hook_file(command=self.kiro_command(python=sys.executable))

    def run_kiro(self, name="kiro", *steps, prompt="Summarise the open TODOs", extra=None, **kw):
        env = dict(self.script(*steps), **(extra or {}))
        return self.umwayi("run", name, "--prompt", prompt, extra=env, **kw)

    def start_kiro(self, name="kiro", *steps, extra=None, **kw):
        env = dict(self.script(*steps), **(extra or {}))
        return self.start_umwayi("run", name, "--prompt", "A long task", extra=env, **kw)

    def first_tool(self):
        return self.wait_for(lambda c: c.get("event") == "tool", what="the first tool call")

    def kill_on(self):
        (self.root / ".umwayi").mkdir(exist_ok=True)
        (self.root / ".umwayi" / "KILL").write_text("", encoding="utf-8")

    def assert_agent_gone(self):
        self.assertEqual(self.alive_at_exit, [], "an agent process was still running when umwayi exited")
        for c in self.calls():
            if c.get("started"):
                self.assertFalse(alive(c["pid"]))
                with self.assertRaises(ProcessLookupError):
                    os.killpg(c["pgid"], 0)
            if c.get("event") == "spawn":
                self.assertFalse(alive(c["pid"]))

    def log_text(self) -> str:
        p = self.root / "LOGBOOK.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def assert_nothing_started(self):
        self.assertEqual(self.started(), [], "kiro-cli was started")


class KiroYesTests(KiroRunCase):
    def test_yes_runs_with_the_prompt_on_stdin_the_hook_and_trust_tools(self):
        r = self.run_kiro("kiro", READ, GREP, WRITE, BASH, prompt=f"Summarise {SECRET}")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        [start] = self.started()
        self.assertEqual(start["argv"], ["chat", "--v3", "--no-interactive", "--trust-tools=read_file,fs_write"])
        self.assertEqual(start["stdin"], f"Summarise {SECRET}")
        self.assertEqual(start["cwd"], str(self.work))
        self.assertEqual(start["pgid"], start["pid"])
        self.assertFalse(any(SECRET in a for a in start["cmdline"]), "the prompt is in the process arguments")
        self.assertEqual([(t["tool"], t["decision"], t["hook"]) for t in self.tools()], [
            ("read_file", "allow", "allow-hook"),  # Yes, and in trust_tools
            ("grep_search", "deny-untrusted", "allow-hook"),  # Yes, but not in trust_tools: the fake denies it
            ("fs_write", "deny-hook", "deny-hook"),  # in trust_tools, but the rules say No: the hook blocks
            ("execute_bash", "deny-hook", "deny-hook"),  # Ask me first: Kiro has no ask, so the hook blocks
        ])
        self.assertIn("Kiro asks first: may it do tool_execute_bash?",
                      [x.title for x in taskqueue.list_rows(self.root, status="open")])
        added = [e.added for e in self.run_entries()]
        self.assertEqual(len(added), 2)
        self.assertTrue(added[0].startswith("Started agent kiro (kiro, cli): "))
        self.assertTrue(added[1].startswith("Agent kiro exited with code 0 after "))
        self.assertNotIn(SECRET, self.log_text())
        self.assertNotIn(SECRET, r.stdout + r.stderr)

    def test_kiro_agent_becomes_agent_and_no_trust_tools_means_no_flag(self):
        self.assertEqual(self.run_kiro("kiro-agent", READ).returncode, 0)
        self.assertEqual(self.started()[-1]["argv"],
                         ["chat", "--v3", "--no-interactive", "--agent", "site-agent", "--trust-tools=read_file"])
        r = self.run_kiro("kiro-none", READ)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.started()[-1]["argv"], ["chat", "--v3", "--no-interactive"])
        self.assertEqual(self.tools()[-1]["decision"], "deny-untrusted")  # nothing trusted, nothing runs
        for c in self.started():
            for bad in agents.FORBIDDEN_FLAGS:
                self.assertNotIn(bad, c["argv"])

    def test_the_prompt_is_never_in_any_process_arguments_or_the_logbook(self):
        p = self.start_umwayi("run", "kiro", "-", stdin=subprocess.PIPE,
                              extra=self.script({"do": "loop_tools", "tool": "read_file", "input": {}, "every": 0.2,
                                                 "for": 2}))
        p.stdin.write(f"Find {SECRET} in the code\n")
        p.stdin.close()
        self.first_tool()
        with open(f"/proc/{p.pid}/cmdline", "rb") as f:
            umwayi_args = f.read().decode("utf-8", "replace")
        code, out, err = self.finish(p)
        self.assertEqual(code, 0, out + err)
        self.assertNotIn(SECRET, umwayi_args)
        start = self.started()[0]
        self.assertNotIn(SECRET, " ".join(start["cmdline"]))
        self.assertEqual(start["stdin"], f"Find {SECRET} in the code\n")
        self.assertNotIn(SECRET, self.log_text())

    def test_a_prompt_that_looks_like_a_flag_stays_on_stdin(self):
        f = self.tmp / "p.txt"
        f.write_text("--trust-all-tools --agent evil please", encoding="utf-8")
        r = self.umwayi("run", "kiro", "--prompt-file", str(f), extra=self.script(READ))
        self.assertEqual(r.returncode, 0, r.stderr)
        start = self.started()[0]
        self.assertEqual(start["argv"], ["chat", "--v3", "--no-interactive", "--trust-tools=read_file,fs_write"])
        self.assertEqual(start["stdin"], "--trust-all-tools --agent evil please")

    def test_an_acp_agent_runs_headless_too(self):
        r = self.run_kiro("kiro-acp", READ)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.started()[0]["argv"], ["chat", "--v3", "--no-interactive", "--trust-tools=read_file"])

    def test_kiro_failing_is_exit_2_with_its_code(self):
        for code in (1, 3, 4):
            with self.subTest(code=code):
                r = self.run_kiro("kiro", {"do": "exit", "code": code})
                self.assertEqual(r.returncode, 2)
                self.assertIn(f"with code {code}", self.run_entries()[-1].added)

    def test_the_same_acp_agent_can_also_chat_over_acp(self):
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "chat", "kiro-acp"],
                           input=":quit\n", capture_output=True, text=True, env=self.env(), cwd=str(self.tmp), timeout=90)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.started()[0]["argv"], ["acp", "--agent-engine=v3"])


class KiroRefusedTests(KiroRunCase):
    def test_rules_no_and_ask_start_nothing_and_ask_adds_one_item_once(self):
        self.assertEqual(self.run_kiro("kiro-no", READ).returncode, 2)
        self.assertEqual(self.run_kiro("kiro-ask", READ).returncode, 3)
        r = self.run_kiro("kiro-ask", READ)
        self.assertEqual(r.returncode, 3)
        self.assertIn("already asks the owner", r.stdout)
        self.assertEqual([x.title for x in taskqueue.list_rows(self.root, status="open")], ["Start agent kiro-ask (run)?"])
        self.assertEqual(self.calls(), [])

    def assert_refused_for_the_hook_file(self):
        r = self.run_kiro("kiro", READ)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("no: kiro hook file: ", r.stdout)
        self.assertIn("Refused agent kiro: not gated (kiro hook file:", self.run_entries()[-1].added)
        self.assert_nothing_started()

    def test_a_missing_hook_file_refuses(self):
        self.hook_file.unlink()
        self.assert_refused_for_the_hook_file()

    def test_a_wrong_hook_file_refuses(self):
        for label, command in (("another root", self.kiro_command(python=sys.executable, root=self.work)),
                               ("extra arguments", self.kiro_command(python=sys.executable) + " --timeout 1"),
                               ("a command before it", "true; " + self.kiro_command(python=sys.executable)),
                               ("the Claude Code hook", self.kiro_command(python=sys.executable).replace("kiro/hook.py",
                                                                                                       "claude_code/hook.py"))):
            with self.subTest(case=label):
                self.kiro_hook_file(command=command)
                self.assert_refused_for_the_hook_file()

    def test_a_matcher_limited_hook_file_refuses(self):
        hook = {"trigger": "PreToolUse", "matcher": "execute_bash",
                "action": {"type": "command", "command": self.kiro_command(python=sys.executable)}}
        self.kiro_hook_file(hook=hook)
        self.assert_refused_for_the_hook_file()

    def test_a_hook_file_removed_between_two_runs_refuses_the_second(self):
        self.assertEqual(self.run_kiro("kiro", READ).returncode, 0)
        self.hook_file.unlink()
        self.assertEqual(self.run_kiro("kiro", READ).returncode, 2)
        self.assertEqual(len(self.started()), 1)

    def test_a_broken_logbook_before_the_start_starts_nothing(self):
        (self.root / "LOGBOOK.md").write_text("# Logbook\n\nedited by hand\n", encoding="utf-8")
        r = self.run_kiro("kiro", READ)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("nothing is started", r.stdout)
        self.assertEqual(self.calls(), [])

    def test_the_kill_switch_before_the_start(self):
        self.kill_on()
        r = self.run_kiro("kiro", READ)
        self.assertEqual(r.returncode, 3)
        self.assertEqual(self.calls(), [])


class KiroStopsTests(KiroRunCase):
    def test_kill_switch_mid_run_stops_kiro_and_its_next_call_is_denied(self):
        p = self.start_kiro("kiro", LAST_READ, {"do": "spawn"}, LOOP)
        self.first_tool()
        self.kill_on()
        t, wall = time.monotonic(), time.time()
        code, out, _ = self.finish(p)
        self.assertLess(time.monotonic() - t, 14)  # within the 10 s SIGKILL grace and a margin
        term = self.wait_for(lambda c: c.get("event") == "term", what="SIGTERM to the agent")
        self.assertLess(term["t"] - wall, 3, "umwayi did not send SIGTERM soon after the kill switch went on")
        self.assertEqual(code, 3, out)
        self.assertEqual(self.tools()[-1]["decision"], "deny-hook")  # read_file is Yes and trusted, but the switch is on
        self.assertEqual(self.run_entries()[-1].added, "The kill switch stopped agent kiro")
        self.assert_agent_gone()

    def test_sigterm_to_umwayi_stops_kiro_and_what_it_started(self):
        p = self.start_kiro("kiro", {"do": "spawn"}, LOOP)
        self.wait_for(lambda c: c.get("event") == "spawn")
        self.first_tool()
        p.send_signal(signal.SIGTERM)
        code, out, _ = self.finish(p)
        self.assertEqual(code, 2, out)
        self.assertEqual(self.run_entries()[-1].added, "Agent kiro was stopped: umwayi got SIGTERM")
        self.assert_agent_gone()

    def test_the_timeout_stops_kiro(self):
        p = self.start_kiro("kiro-slow", LOOP, extra={"UMWAYI_TEST_MINUTE": "2"})
        self.first_tool()
        code, out, _ = self.finish(p)
        self.assertEqual(code, 2, out)
        self.assertEqual(self.run_entries()[-1].added, "Agent kiro-slow stopped after its timeout of 1 min")
        self.assert_agent_gone()

    def test_a_failing_logbook_stops_kiro(self):
        p = self.start_kiro("kiro", LAST_READ, LOOP)
        self.first_tool()
        with open(self.root / "LOGBOOK.md", "a", encoding="utf-8") as f:
            f.write("edited by hand\n")
        code, out, _ = self.finish(p)
        self.assertEqual(code, 2, out)
        self.assertIn("The logbook can no longer be written", out)
        self.assertEqual(self.tools()[-1]["decision"], "deny-hook")
        self.assert_agent_gone()

    def test_a_kiro_that_ignores_sigterm_gets_sigkill_after_10_seconds(self):
        p = self.start_kiro("kiro", {"do": "ignore_term"}, LOOP)
        self.wait_for(lambda c: c.get("event") == "ignoring_term")
        self.first_tool()
        self.kill_on()
        t = time.monotonic()
        code, out, _ = self.finish(p)
        took = self.exited_at - t  # SIGKILL follows after 10 s
        self.assertEqual(code, 3, out)
        self.assertGreater(took, 9.5)
        self.assertLess(took, 25)  # generous: SIGKILL comes at 10 s, not at a minute
        self.assert_agent_gone()

    def test_an_unexpected_error_in_umwayi_while_kiro_runs_stops_it(self):
        p = self.start_kiro("kiro", LOOP, fault="umwayi.logbook:check_writable:crash")
        code, out, err = self.finish(p)
        self.assertEqual(code, 2, out + err)
        self.assertIn("umwayi hit an unexpected error (RuntimeError)", self.run_entries()[-1].added)
        self.assert_agent_gone()

    def test_a_kiro_that_never_reads_a_big_prompt_is_still_stopped_by_the_kill_switch(self):
        f = self.tmp / "big.txt"
        f.write_bytes(b"x" * (100 * 1024))  # more than a pipe buffer holds
        p = self.start_umwayi("run", "kiro", "--prompt-file", str(f), extra=dict(self.script(LOOP), FAKE_NO_STDIN="1"))
        self.first_tool()
        self.kill_on()
        t, wall = time.monotonic(), time.time()
        code, out, _ = self.finish(p, timeout=30)
        self.assertLess(time.monotonic() - t, 14)
        term = self.wait_for(lambda c: c.get("event") == "term", timeout=2,
                             what="SIGTERM (umwayi was stuck writing the prompt and did not watch the kill switch)")
        self.assertLess(term["t"] - wall, 3)
        self.assertEqual(code, 3, out)
        self.assert_agent_gone()


class KiroArgumentListTests(unittest.TestCase):
    """In process: every Kiro list the builders can make is exactly the documented one (10.R5.4, 10.R5.7)."""

    def test_every_kiro_run_list(self):
        tool_sets = [(), ("read_file",), ("read_file", "fs_write"), agents.KIRO_TOOL_IDS]
        n = 0
        for transport in ("cli", "acp"):
            for kiro_agent in (None, "site-agent", "A_b-1"):
                if transport == "acp" and kiro_agent:
                    continue
                for tools in tool_sets:
                    a = agents.Agent("k", "kiro", "kiro-cli", transport, "/w", kiro_agent=kiro_agent, trust_tools=tools)
                    for prompt in ("plain", "--trust-all-tools", "-p --bare bypassPermissions", "line\nline"):
                        argv, stdin = agents.build_argv(a, agents.RUN, "/bin/kiro-cli", "/r", "/usr/bin/python3",
                                                        prompt=prompt)
                        want = ["/bin/kiro-cli", "chat", "--v3", "--no-interactive"]
                        if kiro_agent:
                            want += ["--agent", kiro_agent]
                        if tools:
                            want.append("--trust-tools=" + ",".join(tools))
                        with self.subTest(transport=transport, agent=kiro_agent, tools=tools, prompt=prompt):
                            self.assertEqual(argv, want)
                            self.assertEqual(stdin, prompt)
                            self.assertNotIn(prompt, argv)
                            for bad in agents.FORBIDDEN_FLAGS:
                                self.assertNotIn(bad, argv)
                        n += 1
        self.assertEqual(n, 4 * 4 * (3 + 1))


if __name__ == "__main__":
    unittest.main()
