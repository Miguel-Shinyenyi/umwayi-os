"""Layer 10 part 3: `umwayi agent run` for Claude Code (tasks.md 10.8 to 10.11).

Every test runs `python -m umwayi ... agent run ...` as a real child process. The fake
`claude` runs the layer 9 hook from --settings for scripted tool calls, the way the
Claude Code hooks reference describes, so the tests see what the hook allowed, asked
or denied. No real Claude Code is run.
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import time
import unittest

from umwayi import agents, runlock, taskqueue

from tests.agents.support import REPO, SECRET, AgentCase, alive

AGENTS = """agents:
  - name: reviewer
    platform: claude-code
    command: claude
    workdir: {work}
    max_turns: 7
  - name: blocked
    platform: claude-code
    command: claude
    workdir: {work}
  - name: asker
    platform: claude-code
    command: claude
    workdir: {work}
  - name: slow
    platform: claude-code
    command: claude
    workdir: {work}
    timeout_minutes: 1
  - name: helper
    platform: kiro
    command: kiro-cli
    workdir: {work}
"""
READ = {"do": "tool", "tool": "Read", "input": {"file_path": "/etc/hostname"}}
LS = {"do": "tool", "tool": "Bash", "input": {"command": "ls"}}
RM = {"do": "tool", "tool": "Bash", "input": {"command": "rm -rf /"}}
LOOP = {"do": "loop_tools", "tool": "Read", "input": {"file_path": "/etc/hostname"}, "every": 0.2, "for": 40}
LAST_LS = {"do": "term_tool", "tool": "Bash", "input": {"command": "ls"}}


class RunCase(AgentCase):
    def setUp(self):
        super().setUp()
        self.fake("claude")
        self.fake("kiro-cli")
        self.write_rules()
        self.write_agents(AGENTS)

    def run_agent(self, name="reviewer", *steps, prompt="Fix the failing test", extra=None, **kw):
        env = dict(self.script(*steps), **(extra or {}))
        return self.umwayi("run", name, "--prompt", prompt, extra=env, **kw)

    def start_run(self, name="reviewer", *steps, extra=None, **kw):
        env = dict(self.script(*steps), **(extra or {}))
        return self.start_umwayi("run", name, "--prompt", "Do the long task", extra=env, **kw)

    def first_tool(self):
        return self.wait_for(lambda c: c.get("event") == "tool", what="the first tool call")

    def assert_agent_gone(self):
        self.assertEqual(self.alive_at_exit, [], "an agent process was still running when umwayi exited")
        for c in self.calls():
            if c.get("started"):
                self.assertFalse(alive(c["pid"]), "the agent is still running")
                with self.assertRaises(ProcessLookupError):
                    os.killpg(c["pgid"], 0)  # nothing left in its process group
            if c.get("event") == "spawn":
                self.assertFalse(alive(c["pid"]), "a process the agent started is still running")

    def log_text(self) -> str:
        p = self.root / "LOGBOOK.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def verify_logbook(self):
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "logbook", "verify"],
                           capture_output=True, text=True, env=self.env())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class YesRunsTests(RunCase):
    def test_yes_starts_claude_code_with_the_gate_and_every_tool_call_goes_through_the_hook(self):
        r = self.run_agent("reviewer", READ, LS, RM, prompt=f"Fix the test {SECRET}")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Agent reviewer finished (exit 0)", r.stdout)
        [start] = self.started()
        self.assertEqual(start["cwd"], str(self.work))
        self.assertEqual(start["stdin"], "")
        # the owner's environment, unchanged: umwayi adds and removes no variable (10.R5.8)
        self.assertEqual(set(start["env_keys"]), set(self.env(self.script(READ, LS, RM))))
        self.assertEqual(start["pgid"], start["pid"])  # its own process group
        self.assertEqual(start["sid"], start["pid"])  # and its own session
        argv = start["argv"]
        self.assertEqual(argv[:3], ["-p", "--permission-mode", "default"])
        self.assertEqual(argv[-1], f"Fix the test {SECRET}")
        self.assertEqual(argv[-3:-1], ["--max-turns", "7"])
        settings = json.loads(argv[argv.index("--settings") + 1])
        hook = settings["hooks"]["PreToolUse"][0]["hooks"][0]
        self.assertEqual(hook["args"], [str(REPO / "adapters" / "claude_code" / "hook.py"), "--root", str(self.root)])
        for bad in agents.FORBIDDEN_FLAGS:
            self.assertNotIn(bad, argv[:-1])
        self.assertEqual([(t["tool"], t["decision"]) for t in self.tools()],
                         [("Read", "allow"), ("Bash", "ask"), ("Bash", "deny")])

    def test_one_check_one_start_one_end_entry_and_never_the_prompt(self):
        r = self.run_agent("reviewer", READ, prompt=f"secret task {SECRET}")
        self.assertEqual(r.returncode, 0)
        added = [e.added for e in self.run_entries()]
        self.assertEqual(len(added), 2)
        self.assertTrue(added[0].startswith("Started agent reviewer (claude-code, cli): "), added)
        self.assertTrue(added[1].startswith("Agent reviewer exited with code 0 after "), added)
        checks = [e for e in self.entries() if e.source == "umwayi check" and "agent_run" in e.added]
        self.assertEqual(len(checks), 1)
        self.assertIn("Rule agent-yes gave Yes", checks[0].added)
        self.assertNotIn(SECRET, self.log_text())
        self.assertNotIn(SECRET, r.stdout + r.stderr)
        self.assertFalse((self.root / "queue.md").exists())
        self.verify_logbook()

    def test_the_prompt_from_a_file_or_stdin_is_passed_exactly(self):
        text = "Line one\nline two: é ✓\n"
        f = self.tmp / "prompt.txt"
        f.write_text(text, encoding="utf-8")
        r = self.umwayi("run", "reviewer", "--prompt-file", str(f), extra=self.script())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.started()[-1]["argv"][-1], text)
        p = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "run", "reviewer", "-"],
                           input=text.encode("utf-8"), capture_output=True, env=self.env(self.script()), cwd=self.tmp)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.started()[-1]["argv"][-1], text)

    def test_a_process_the_agent_left_running_is_stopped_after_it_exits(self):
        r = self.run_agent("reviewer", {"do": "spawn"}, READ)
        self.assertEqual(r.returncode, 0)
        self.assert_agent_gone()

    def test_the_agent_failing_is_exit_2_with_its_code_in_the_logbook(self):
        for step, words in (({"do": "exit", "code": 1}, "with code 1"), ({"do": "exit", "code": 143}, "with code 143"),
                            ({"do": "crash"}, "with code 1"), ({"do": "exit", "code": 4}, "with code 4")):
            with self.subTest(step=step):
                r = self.run_agent("reviewer", step)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn(words, self.run_entries()[-1].added)
        self.verify_logbook()


class StopsBeforeStartTests(RunCase):
    def assert_nothing_ran(self):
        self.assertEqual(self.calls(), [], "a platform program was run")

    def test_rules_no_starts_nothing(self):
        r = self.run_agent("blocked", READ)
        self.assertEqual(r.returncode, 2)
        self.assertIn("Rule: agent-no", r.stdout)
        self.assert_nothing_ran()
        self.assertEqual(self.run_entries(), [])  # only the check entry
        self.assertEqual(len([e for e in self.entries() if "agent_run" in e.added]), 1)

    def test_ask_me_first_adds_one_queue_item_once_and_starts_nothing(self):
        r = self.run_agent("asker", READ)
        self.assertEqual(r.returncode, 3)
        self.assertIn("Added queue item Q-0001", r.stdout)
        r = self.run_agent("asker", READ)
        self.assertEqual(r.returncode, 3)
        self.assertIn("Queue item Q-0001 already asks the owner about this. Nothing was added.", r.stdout)
        rows = taskqueue.list_rows(self.root, status="open")
        self.assertEqual([(x.kind, x.title) for x in rows], [("decision", "Start agent asker (run)?")])
        self.assert_nothing_ran()

    def test_kill_switch_on_or_unknown_before_the_start(self):
        (self.root / ".umwayi").mkdir()
        (self.root / ".umwayi" / "KILL").write_text("", encoding="utf-8")
        r = self.run_agent("reviewer", READ)
        self.assertEqual(r.returncode, 3)
        self.assertIn("The kill switch is on", r.stdout)
        self.assertEqual(len(self.run_entries()), 1)
        self.assertEqual([e for e in self.entries() if "agent_run" in e.added], [])  # no rule was asked
        self.assert_nothing_ran()
        shutil.rmtree(self.root / ".umwayi")
        (self.root / ".umwayi").write_text("not a folder", encoding="utf-8")
        r = self.run_agent("reviewer", READ)
        self.assertEqual(r.returncode, 3)
        self.assert_nothing_ran()

    def test_run_lock_held_gives_3(self):
        with runlock.held(self.root):
            r = self.run_agent("reviewer", READ)
        self.assertEqual(r.returncode, 3)
        self.assertIn("holds the run lock", r.stdout)
        self.assert_nothing_ran()
        self.assertIn("another umwayi run holds the run lock", self.run_entries()[-1].added)

    def test_a_broken_logbook_starts_nothing(self):
        self.run_agent("reviewer", READ)
        with open(self.root / "LOGBOOK.md", "a", encoding="utf-8") as f:
            f.write("edited by hand\n")
        os.remove(self.fake_log)
        r = self.run_agent("reviewer", READ)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("nothing is started", r.stdout)
        self.assert_nothing_ran()

    def test_a_start_entry_that_cannot_be_written_starts_nothing(self):
        r = self.run_agent("reviewer", READ, extra={"UMWAYI_TEST_BREAK_LOGBOOK_AFTER_GATE": "1",
                                                     "UMWAYI_TEST_ROOT": str(self.root)})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("The logbook could not record the start, so nothing is started", r.stdout)
        self.assertEqual(self.started(), [])

    def test_not_gated_is_refused_with_an_entry(self):
        r = self.run_agent("reviewer", READ, extra={"FAKE_CLAUDE_VERSION": "2.1.294"})
        self.assertEqual(r.returncode, 2)
        self.assertIn("Refused: agent reviewer cannot be gated", r.stdout)
        self.assertEqual(self.started(), [])
        self.assertIn("Refused agent reviewer: not gated (version: 2.1.294 is older than 2.1.295",
                      self.run_entries()[-1].added)
        (self.bin / "claude").unlink()
        r = self.run_agent("reviewer", READ, extra={"PATH": str(self.bin)})
        self.assertEqual(r.returncode, 2)
        self.assertIn("not found on PATH", self.run_entries()[-1].added)

    def test_chat_is_not_built_and_starts_nothing(self):
        r = self.umwayi("chat", "reviewer")
        self.assertEqual(r.returncode, 64)
        self.assert_nothing_ran()
        self.assertFalse((self.root / "LOGBOOK.md").exists())


class PromptTests(RunCase):
    def test_prompts_that_cannot_be_used_are_64_before_anything_else(self):
        (self.root / ".umwayi").mkdir()
        (self.root / ".umwayi" / "KILL").write_text("", encoding="utf-8")  # step 1 comes before the kill switch
        big = self.tmp / "big.txt"
        big.write_bytes(b"x" * (100 * 1024 + 1))
        bad = self.tmp / "bad.txt"
        bad.write_bytes(b"\xff\xfe")
        link = self.tmp / "link.txt"
        os.symlink(bad, link)
        cases = {
            "no prompt": ([], None), "two ways": (["--prompt", "a", "--prompt-file", str(big)], None),
            "a word instead of -": (["please"], None), "- and --prompt": (["-", "--prompt", "a"], b"b"),
            "leading dash": (["--prompt=-p do it"], None), "leading dash on stdin": (["-"], b"--bare do it"),
            "empty": (["--prompt", ""], None), "spaces only": (["--prompt", "   "], None),
            "too big file": (["--prompt-file", str(big)], None), "too big stdin": (["-"], b"y" * (100 * 1024 + 1)),
            "not UTF-8": (["--prompt-file", str(bad)], None), "a link": (["--prompt-file", str(link)], None),
            "missing file": (["--prompt-file", str(self.tmp / "nope")], None), "a folder": (["--prompt-file", str(self.tmp)], None),
            "NUL on stdin": (["-"], b"a\x00b"),
        }
        for label, (args, stdin) in cases.items():
            with self.subTest(case=label):
                p = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "run", "reviewer",
                                    *args], input=stdin, capture_output=True, env=self.env(), cwd=self.tmp)
                self.assertEqual(p.returncode, 64, p.stdout + p.stderr)
        self.assertEqual(self.calls(), [])
        self.assertFalse((self.root / "LOGBOOK.md").exists())

    def test_exactly_100_kb_is_accepted(self):
        f = self.tmp / "max.txt"
        f.write_bytes(b"z" * (100 * 1024))
        r = self.umwayi("run", "reviewer", "--prompt-file", str(f), extra=self.script())
        self.assertEqual(r.returncode, 0, r.stderr)


class StopsWhileRunningTests(RunCase):
    def test_kill_switch_turned_on_mid_run_stops_the_agent_and_its_next_call_is_denied(self):
        p = self.start_run("reviewer", LAST_LS, {"do": "spawn"}, LOOP)
        self.first_tool()
        (self.root / ".umwayi").mkdir(exist_ok=True)
        (self.root / ".umwayi" / "KILL").write_text("", encoding="utf-8")
        t = time.monotonic()
        code, out, _ = self.finish(p)
        self.assertLess(time.monotonic() - t, 5, "the agent was not stopped within a few seconds")
        self.assertEqual(code, 3, out)
        self.assertIn("The kill switch stopped agent reviewer (exit 3).", out)
        self.assertTrue(any(c.get("event") == "term" for c in self.calls()), "the agent got no SIGTERM")
        last = self.tools()[-1]
        self.assertEqual((last["tool"], last["decision"]), ("Bash", "deny"))  # the hook denies while the switch is on
        self.assertEqual(self.run_entries()[-1].added, "The kill switch stopped agent reviewer")
        self.assert_agent_gone()

    def test_an_agent_that_ignores_sigterm_gets_sigkill_after_10_seconds(self):
        p = self.start_run("reviewer", {"do": "ignore_term"}, LOOP)
        self.wait_for(lambda c: c.get("event") == "ignoring_term")
        self.first_tool()
        (self.root / ".umwayi").mkdir(exist_ok=True)
        (self.root / ".umwayi" / "KILL").write_text("", encoding="utf-8")
        t = time.monotonic()
        code, out, _ = self.finish(p)
        took = time.monotonic() - t
        self.assertEqual(code, 3, out)
        self.assertGreater(took, 9.5)
        self.assertLess(took, 16)
        self.assert_agent_gone()

    def test_the_logbook_failing_mid_run_stops_the_agent(self):
        p = self.start_run("reviewer", LAST_LS, LOOP)
        self.first_tool()
        with open(self.root / "LOGBOOK.md", "a", encoding="utf-8") as f:
            f.write("edited by hand while the agent runs\n")
        code, out, _ = self.finish(p)
        self.assertEqual(code, 2, out)
        self.assertIn("The logbook can no longer be written", out)
        self.assertEqual(self.tools()[-1]["decision"], "deny")  # its checks cannot be recorded, so the hook denies
        self.assert_agent_gone()

    def test_sigterm_to_umwayi_stops_the_agent_and_what_it_started(self):
        p = self.start_run("reviewer", {"do": "spawn"}, LOOP)
        self.wait_for(lambda c: c.get("event") == "spawn")
        self.first_tool()
        p.send_signal(signal.SIGTERM)
        code, out, _ = self.finish(p)
        self.assertEqual(code, 2, out)
        self.assertIn("got SIGTERM, so agent reviewer was stopped (exit 2)", out)
        self.assertEqual(self.run_entries()[-1].added, "Agent reviewer was stopped: umwayi got SIGTERM")
        self.assert_agent_gone()
        self.verify_logbook()

    def test_ctrl_c_and_sighup_to_umwayi_stop_the_agent(self):
        for sig, words in ((signal.SIGINT, "Ctrl-C"), (signal.SIGHUP, "SIGHUP")):
            with self.subTest(signal=words):
                os.remove(self.fake_log) if self.fake_log.exists() else None
                p = self.start_run("reviewer", LOOP)
                self.first_tool()
                p.send_signal(sig)
                code, out, _ = self.finish(p)
                self.assertEqual(code, 2, out)
                self.assertIn(words, self.run_entries()[-1].added)
                self.assert_agent_gone()

    def test_timeout_minutes_stops_the_run(self):
        p = self.start_run("slow", LOOP, extra={"UMWAYI_TEST_MINUTE": "2"})  # a "minute" of 2 s, test only
        self.first_tool()
        code, out, _ = self.finish(p)
        self.assertEqual(code, 2, out)
        self.assertIn("was stopped after its timeout of 1 min (exit 2)", out)
        self.assertEqual(self.run_entries()[-1].added, "Agent slow stopped after its timeout of 1 min")
        self.assert_agent_gone()

    def test_an_unexpected_error_in_umwayi_while_it_watches_stops_the_agent_and_is_2(self):
        p = self.start_run("reviewer", LOOP, fault="umwayi.logbook:check_writable:crash",
                           extra={"UMWAYI_FAULT_TEXT": SECRET})
        code, out, err = self.finish(p)
        self.assertEqual(code, 2, out + err)
        self.assertIn("stopped by an unexpected error (RuntimeError)", err)
        self.assertNotIn(SECRET, out + err)
        self.assertIn("umwayi hit an unexpected error (RuntimeError)", self.run_entries()[-1].added)
        self.assert_agent_gone()

    def test_an_unexpected_error_before_the_start_starts_nothing(self):
        for target in ("umwayi.agents:gate_checks", "umwayi.agents:build_argv", "umwayi.runlock:held",
                       "umwayi.rules:check_and_log"):
            with self.subTest(target=target):
                r = self.run_agent("reviewer", READ, fault=f"{target}:crash")
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertEqual(self.started(), [])


if __name__ == "__main__":
    unittest.main()
