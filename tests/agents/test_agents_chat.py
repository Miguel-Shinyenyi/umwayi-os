"""Layer 10 part 5: `umwayi agent chat NAME` with transport cli (tasks.md 10.14 and 10.15).

Every test runs `python -m umwayi ... agent chat ...` as a real child process, with fake
`claude` and `kiro-cli` programs in chat mode (they echo the lines they read).

The interactive tests use a real pseudo terminal (os.openpty): umwayi is started as a
session leader with the pty as its controlling terminal, so Ctrl-C written to the pty
reaches the terminal's foreground process group, as on a real terminal. The exit code
tests feed stdin from a pipe; that is said in each one.
"""

import fcntl
import os
import select
import shutil
import signal
import subprocess
import sys
import termios
import time
import unittest

from umwayi import agents, runlock, taskqueue

from tests.agents.support import REPO, SECRET, AgentCase, alive

AGENTS = """agents:
  - name: reviewer
    platform: claude-code
    command: claude
    workdir: {work}
  - name: slow
    platform: claude-code
    command: claude
    workdir: {work}
    timeout_minutes: 1
  - name: blocked
    platform: claude-code
    command: claude
    workdir: {work}
  - name: asker
    platform: claude-code
    command: claude
    workdir: {work}
  - name: runonly
    platform: claude-code
    command: claude
    workdir: {work}
  - name: kiro
    platform: kiro
    command: kiro-cli
    workdir: {work}
    trust_tools: [read_file]
  - name: kiro-agent
    platform: kiro
    command: kiro-cli
    workdir: {work}
    kiro_agent: site-agent
  - name: kiro-acp
    platform: kiro
    command: kiro-cli
    transport: acp
    workdir: {work}
"""
RULES = """rules:
  - id: chat-yes
    title: these may start
    text: Allowed.
    verdict: yes
    matchers:
      type: agent_run
      agent: [reviewer, slow, kiro, kiro-agent, kiro-acp, runonly]
  - id: runonly-no-chat
    title: runonly may not chat
    text: Only headless runs for this one.
    verdict: no
    matchers:
      type: agent_run
      agent: runonly
      mode: chat
      transport: cli
  - id: blocked-no
    title: never
    text: Never.
    verdict: no
    matchers:
      type: agent_run
      agent: blocked
  - id: asker-ask
    title: ask
    text: Ask.
    verdict: ask
    matchers:
      type: agent_run
      agent: asker
  - id: read-yes
    title: reading is fine
    text: Allowed.
    verdict: yes
    matchers:
      type: [tool_read, tool_read_file]
  - id: bash-no
    title: no shell
    text: Never.
    verdict: no
    matchers:
      type: tool_bash
"""
# A minimal job control "shell": run argv[3:] as a foreground job in its own process group.
SHELL = r"""
import os, signal, subprocess, sys, time

def foreground_job():
    signal.signal(signal.SIGTTOU, signal.SIG_IGN)  # what shells do before they hand over the terminal
    os.setpgrp()
    os.tcsetpgrp(0, os.getpid())
    signal.signal(signal.SIGTTOU, signal.SIG_DFL)

p = subprocess.Popen(sys.argv[3:], preexec_fn=foreground_job)
with open(sys.argv[1], "w") as f:
    f.write(str(p.pid))
code = p.wait()
signal.signal(signal.SIGTTOU, signal.SIG_IGN)
os.tcsetpgrp(0, os.getpgrp())  # take the terminal back, as a shell does
with open(sys.argv[2], "w") as f:
    f.write(str(code if code >= 0 else 128 - code))
time.sleep(30)  # stay the session leader until the test is done
"""
SPAWN = {"do": "spawn"}
SPAWN_SETSID = {"do": "spawn_setsid"}


class ChatCase(AgentCase):
    def setUp(self):
        super().setUp()
        self.fake("claude")
        self.fake("kiro-cli")
        self.write_rules(RULES)
        self.write_agents(AGENTS)
        self.kiro_hook_file(command=self.kiro_command(python=sys.executable))

    # ------------------------------------------------------------ a pseudo terminal and a "shell"

    def start_pty(self, name="reviewer", *steps, extra=None, fault=None):
        """umwayi agent chat as a foreground job on a pseudo terminal, the way a shell runs it.

        A small "shell" process is the session leader with the pty as its controlling terminal. It
        starts umwayi in its own process group, gives that group the terminal, writes umwayi's pid and
        exit code to files, and stays alive, so umwayi is never the session leader (whose exit would
        send SIGHUP to the foreground group).
        """
        master, slave = os.openpty()
        self.slave_name = os.ttyname(slave)
        self.pidfile, self.codefile = self.tmp / "umwayi.pid", self.tmp / "umwayi.code"
        for f in (self.pidfile, self.codefile):
            if f.exists():
                f.unlink()

        def make_controlling_terminal():
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        cmd = [sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "chat", name]
        self.shell = subprocess.Popen([sys.executable, "-c", SHELL, str(self.pidfile), str(self.codefile), *cmd],
                                      stdin=slave, stdout=slave, stderr=slave,
                                      env=self.env(dict(self.script(*steps), **(extra or {})), fault),
                                      cwd=str(self.tmp), start_new_session=True, preexec_fn=make_controlling_terminal)
        os.close(slave)
        self.addCleanup(self._close_pty, master)
        self.screen = b""
        end = time.monotonic() + 20
        while not (self.pidfile.exists() and self.pidfile.read_text().strip()) and time.monotonic() < end:
            time.sleep(0.02)
        self.umwayi_pid = int(self.pidfile.read_text())
        return self.umwayi_pid, master

    def _close_pty(self, master):
        for pid in [self.umwayi_pid] + self.agent_pids_alive():
            if alive(pid):
                os.kill(pid, signal.SIGKILL)
        if self.shell.poll() is None:
            self.shell.kill()
        self.shell.wait(timeout=30)
        try:
            os.close(master)
        except OSError:
            pass

    def umwayi_code(self):
        t = self.codefile.read_text().strip() if self.codefile.exists() else ""
        return int(t) if t else None

    def read_until(self, master, text: str, timeout: float = 20) -> str:
        end = time.monotonic() + timeout
        while text.encode() not in self.screen:
            left = end - time.monotonic()
            if left <= 0:
                self.fail(f"timed out waiting for {text!r} on the terminal; got: {self.screen!r}")
            r, _, _ = select.select([master], [], [], min(left, 0.2))
            if r:
                try:
                    chunk = os.read(master, 4096)
                except OSError:  # EIO: nothing holds the terminal open any more
                    chunk = b""
                if not chunk:
                    time.sleep(0.05)
                self.screen += chunk
        return self.screen.decode("utf-8", "replace")

    def drain(self, master):
        try:
            while select.select([master], [], [], 0.1)[0]:
                chunk = os.read(master, 4096)
                if not chunk:
                    break
                self.screen += chunk
        except OSError:
            pass
        return self.screen.decode("utf-8", "replace")

    def type(self, master, text: str):
        os.write(master, text.encode("utf-8"))

    def wait_exit(self, pid, master, timeout: float = 30) -> int:
        end = time.monotonic() + timeout
        while self.umwayi_code() is None and time.monotonic() < end:
            self.drain(master)
        code = self.umwayi_code()
        self.assertIsNotNone(code, "umwayi did not exit")
        self.alive_at_exit = self.agent_pids_alive()  # the moment umwayi exited; the "shell" is still there
        self.drain(master)
        self.assertIn(code, (0, 2, 3, 64))
        return code

    # ------------------------------------------------------------ helpers

    def chat_pipe(self, name="reviewer", lines="/quit\n", *steps, extra=None):
        """umwayi agent chat with stdin from a pipe (not a terminal)."""
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "chat", name],
                           input=lines, capture_output=True, text=True, timeout=60,
                           env=self.env(dict(self.script(*steps), **(extra or {}))), cwd=str(self.tmp))
        self.assertIn(r.returncode, (0, 2, 3, 64), r.stdout + r.stderr)
        return r

    def assert_agent_gone(self):
        self.assertEqual(self.alive_at_exit, [], "an agent process was still running when umwayi exited")
        for c in self.calls():
            if c.get("started") or c.get("event") == "spawn":
                self.assertFalse(alive(c["pid"]))

    def log_text(self) -> str:
        p = self.root / "LOGBOOK.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def kill_on(self):
        (self.root / ".umwayi").mkdir(exist_ok=True)
        (self.root / ".umwayi" / "KILL").write_text("", encoding="utf-8")


class TerminalTests(ChatCase):
    """With a real pseudo terminal."""

    def test_the_queue_summary_comes_before_any_agent_output_and_the_agent_gets_the_terminal(self):
        taskqueue.add(self.root, "decision", "Publish the November article?", "", "2026-11-08")
        taskqueue.add(self.root, "task", "Answer the reviewer", "", "2026-11-08")
        p, m = self.start_pty("reviewer")
        screen = self.read_until(m, "agent ready")
        self.assertLess(screen.index("Open in the queue: 2 item(s)."), screen.index("agent ready"))
        self.assertIn("Q-0001 (decision): Publish the November article?", screen)
        self.assertIn("Q-0002 (task): Answer the reviewer", screen)
        self.type(m, f"hello {SECRET}\n")
        self.read_until(m, f"agent: hello {SECRET}")
        self.type(m, "/quit\n")
        self.assertEqual(self.wait_exit(p, m), 0)
        self.assertIn("Agent reviewer finished (exit 0)", self.screen.decode())
        [start] = self.started()
        self.assertTrue(start["stdin_tty"] and start["stdout_tty"])
        self.assertEqual(start["ttyname"], self.slave_name)  # the owner's terminal, unchanged
        self.assertEqual(start["pgid"], p)  # umwayi's process group (umwayi leads its job's group)
        self.assertEqual(start["foreground"], p)  # and that group has the terminal
        self.assertEqual(start["stdin"], "")
        self.assertEqual([c["text"] for c in self.calls() if c.get("event") == "line"], [f"hello {SECRET}", "/quit"])
        self.assertNotIn(SECRET, self.log_text())
        self.assert_agent_gone()

    def test_ctrl_c_reaches_the_agent_and_does_not_stop_umwayi(self):
        p, m = self.start_pty("reviewer")
        self.read_until(m, "agent ready")
        self.type(m, "\x03")
        self.assertIs(self.started()[0]["sigint_ignored"], False, "the agent inherited SIGINT ignored")
        self.wait_for(lambda c: c.get("event") == "sigint", what="the agent to get Ctrl-C")
        time.sleep(0.3)
        self.assertIsNone(self.umwayi_code(), "Ctrl-C stopped umwayi")
        self.assertTrue(alive(p))
        self.type(m, "still here\n")
        self.read_until(m, "agent: still here")
        self.type(m, "/quit\n")
        self.assertEqual(self.wait_exit(p, m), 0)
        self.assert_agent_gone()

    def test_ctrl_c_before_the_start_still_stops_umwayi(self):
        # the gate checks run `claude -v`; make it hang so umwayi is still before the start
        p, m = self.start_pty("reviewer", extra={"FAKE_CLAUDE_HANG": "1"})
        self.wait_for(lambda c: c.get("argv") == ["-v"], what="the version check")
        self.type(m, "\x03")
        self.assertEqual(self.wait_exit(p, m), 2)
        self.assertEqual(self.started(), [])

    def test_the_kill_switch_stops_the_agent_and_what_it_started_even_in_another_session(self):
        p, m = self.start_pty("reviewer", SPAWN, SPAWN_SETSID)
        self.read_until(m, "agent ready")
        time.sleep(1.2)  # at least one watcher pass, so the children have been seen
        self.kill_on()
        t, wall = time.monotonic(), time.time()
        self.assertEqual(self.wait_exit(p, m), 3)
        self.assertLess(time.monotonic() - t, 14)
        term = self.wait_for(lambda c: c.get("event") == "term", what="SIGTERM to the agent")
        self.assertLess(term["t"] - wall, 3, "umwayi did not send SIGTERM soon after the kill switch went on")
        self.assertIn("The kill switch stopped agent reviewer (exit 3).", self.screen.decode())
        self.assertEqual(len([c for c in self.calls() if c.get("event") == "spawn"]), 2)
        self.assert_agent_gone()

    def test_the_terminal_mode_is_put_back_after_an_agent_that_left_it_raw(self):
        p, m = self.start_pty("reviewer", {"do": "raw"})
        before = termios.tcgetattr(m)
        self.wait_for(lambda c: c.get("event") == "raw", what="the agent to make the terminal raw")
        self.assertFalse(termios.tcgetattr(m)[3] & termios.ECHO)  # raw now: no echo
        self.kill_on()
        self.assertEqual(self.wait_exit(p, m), 3)
        after = termios.tcgetattr(m)
        self.assertTrue(after[3] & termios.ECHO and after[3] & termios.ICANON, "the terminal was left raw")
        self.assertEqual(after[3], before[3])

    def test_a_process_orphaned_while_the_agent_runs_is_still_stopped(self):
        p, m = self.start_pty("reviewer", {"do": "spawn_orphan"})
        self.read_until(m, "agent ready")
        mid = self.wait_for(lambda c: c.get("intermediate"), what="the intermediate process")
        orphan = self.wait_for(lambda c: c.get("orphan"), what="the orphan")
        end = time.monotonic() + 10
        while alive(mid["pid"]) and time.monotonic() < end:
            time.sleep(0.1)
        time.sleep(1.5)  # the intermediate has exited; the orphan now has another parent
        self.assertTrue(alive(orphan["pid"]))
        self.kill_on()
        self.assertEqual(self.wait_exit(p, m), 3)
        self.assert_agent_gone()

    def test_sigterm_to_umwayi_stops_the_chat(self):
        p, m = self.start_pty("reviewer", SPAWN)
        self.read_until(m, "agent ready")
        time.sleep(1.2)
        os.kill(p, signal.SIGTERM)  # umwayi only, not its group
        self.assertEqual(self.wait_exit(p, m), 2)
        self.assertEqual(self.run_entries()[-1].added, "Agent reviewer was stopped: umwayi got SIGTERM")
        self.assert_agent_gone()

    def test_an_agent_that_ignores_sigterm_gets_sigkill_after_10_seconds(self):
        p, m = self.start_pty("reviewer", {"do": "ignore_term"})
        self.read_until(m, "agent ready")
        self.kill_on()
        t = time.monotonic()
        self.assertEqual(self.wait_exit(p, m, timeout=40), 3)
        took = time.monotonic() - t
        self.assertGreater(took, 9.5)
        self.assertLess(took, 16)
        self.assert_agent_gone()

    def test_the_timeout_stops_the_chat(self):
        p, m = self.start_pty("slow", extra={"UMWAYI_TEST_MINUTE": "2"})
        self.read_until(m, "agent ready")
        self.assertEqual(self.wait_exit(p, m), 2)
        self.assertEqual(self.run_entries()[-1].added, "Agent slow stopped after its timeout of 1 min")
        self.assert_agent_gone()

    def test_a_failing_logbook_stops_the_chat(self):
        p, m = self.start_pty("reviewer")
        self.read_until(m, "agent ready")
        with open(self.root / "LOGBOOK.md", "a", encoding="utf-8") as f:
            f.write("edited by hand\n")
        self.assertEqual(self.wait_exit(p, m), 2)
        self.assertIn("The logbook can no longer be written", self.screen.decode())
        self.assert_agent_gone()

    def test_an_unexpected_error_in_umwayi_during_a_chat_stops_the_agent(self):
        p, m = self.start_pty("reviewer", fault="umwayi.logbook:check_writable:crash")
        self.assertEqual(self.wait_exit(p, m), 2)
        self.assertIn("umwayi hit an unexpected error (RuntimeError)", self.run_entries()[-1].added)
        self.assert_agent_gone()

    def test_what_the_agent_left_running_is_stopped_after_a_normal_exit(self):
        p, m = self.start_pty("reviewer", SPAWN)
        self.read_until(m, "agent ready")
        time.sleep(1.2)
        self.type(m, "/quit\n")
        self.assertEqual(self.wait_exit(p, m), 0)
        self.assert_agent_gone()

    def test_tool_calls_in_a_chat_go_through_the_hook(self):
        p, m = self.start_pty("reviewer")
        self.read_until(m, "agent ready")
        self.type(m, "/tool Read\n")
        self.read_until(m, "tool Read: allow")
        self.type(m, "/tool Bash\n")
        self.read_until(m, "tool Bash: deny")
        self.type(m, "/quit\n")
        self.assertEqual(self.wait_exit(p, m), 0)

    def test_a_kiro_chat_on_the_terminal(self):
        p, m = self.start_pty("kiro")
        self.read_until(m, "agent ready")
        self.type(m, "/tool read_file\n")
        self.read_until(m, "tool read_file: allow")
        self.type(m, "/tool fs_write\n")
        self.read_until(m, "tool fs_write: deny-hook")  # no rule: Ask me first, and Kiro has no ask
        self.type(m, "/quit\n")
        self.assertEqual(self.wait_exit(p, m), 0)
        self.assertEqual(self.started()[0]["argv"], ["chat", "--v3"])
        self.assert_agent_gone()


class StepsAndExitCodesTests(ChatCase):
    """stdin from a pipe, not a terminal."""

    def test_yes_and_the_agent_exits_0_is_0_and_the_lines_arrive_unchanged(self):
        r = self.chat_pipe("reviewer", f"one\ntwo {SECRET}\n/quit\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertLess(r.stdout.index("Open in the queue: 0 item(s)."), r.stdout.index("agent ready"))
        self.assertEqual([c["text"] for c in self.calls() if c.get("event") == "line"], ["one", f"two {SECRET}", "/quit"])
        added = [e.added for e in self.run_entries()]
        self.assertTrue(added[0].startswith("Started agent reviewer (claude-code, cli, chat): "), added)
        self.assertTrue(added[1].startswith("Agent reviewer exited with code 0 after "), added)
        self.assertNotIn(SECRET, self.log_text())
        self.assertNotIn("one", " ".join(e.added + e.checked + e.not_done for e in self.run_entries()))

    def test_the_agent_failing_is_2(self):
        r = self.chat_pipe("reviewer", "/exit 1\n")
        self.assertEqual(r.returncode, 2)
        self.assertIn("with code 1", self.run_entries()[-1].added)

    def test_the_rules_see_mode_chat_and_transport_cli(self):
        r = self.chat_pipe("runonly")
        self.assertEqual(r.returncode, 2, r.stdout)  # the chat-only No rule matched
        self.assertIn("Rule: runonly-no-chat", r.stdout)
        self.assertEqual(self.started(), [])
        r = self.umwayi("run", "runonly", "--prompt", "x", extra=self.script())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)  # the same agent may run headless

    def test_rules_no_and_ask_start_nothing_and_ask_adds_one_item_once(self):
        self.assertEqual(self.chat_pipe("blocked").returncode, 2)
        self.assertEqual(self.chat_pipe("asker").returncode, 3)
        r = self.chat_pipe("asker")
        self.assertEqual(r.returncode, 3)
        self.assertIn("already asks the owner", r.stdout)
        self.assertEqual([x.title for x in taskqueue.list_rows(self.root, status="open")], ["Start agent asker (chat)?"])
        self.assertEqual(self.calls(), [])

    def test_the_kill_switch_and_the_run_lock_before_the_start_are_3(self):
        with runlock.held(self.root):
            self.assertEqual(self.chat_pipe("reviewer").returncode, 3)
        self.kill_on()
        self.assertEqual(self.chat_pipe("reviewer").returncode, 3)
        self.assertEqual(self.calls(), [])

    def test_not_gated_is_2_and_starts_nothing(self):
        r = self.chat_pipe("reviewer", extra={"FAKE_CLAUDE_VERSION": "2.1.0"})
        self.assertEqual(r.returncode, 2)
        self.assertIn("cannot be gated", r.stdout)
        shutil.rmtree(self.work / ".kiro")
        r = self.chat_pipe("kiro")
        self.assertEqual(r.returncode, 2)
        self.assertIn("no: kiro hook file", r.stdout)
        self.assertEqual(self.started(), [])

    def test_a_broken_logbook_before_the_start_is_2(self):
        (self.root / "LOGBOOK.md").write_text("# Logbook\n\nedited by hand\n", encoding="utf-8")
        self.assertEqual(self.chat_pipe("reviewer").returncode, 2)
        self.assertEqual(self.calls(), [])

    def test_kiro_acp_chat_is_64_and_says_it_is_part_6(self):
        r = self.chat_pipe("kiro-acp")
        self.assertEqual(r.returncode, 64)
        self.assertIn("ACP chat is layer 10 part 6", r.stderr)
        self.assertEqual(self.calls(), [])
        self.assertFalse((self.root / "LOGBOOK.md").exists())

    def test_the_chat_argument_lists(self):
        self.chat_pipe("reviewer")
        argv = self.started()[-1]["argv"]
        self.assertEqual(argv[:3], ["--permission-mode", "default", "--settings"])
        self.assertEqual(len(argv), 4)  # no -p, no prompt
        self.assertIn(str(REPO / "adapters" / "claude_code" / "hook.py"), argv[3])
        self.chat_pipe("kiro")
        self.assertEqual(self.started()[-1]["argv"], ["chat", "--v3"])  # trust_tools is never used in a chat
        self.chat_pipe("kiro-agent")
        self.assertEqual(self.started()[-1]["argv"], ["chat", "--v3", "--agent", "site-agent"])
        for c in self.started():
            for bad in agents.FORBIDDEN_FLAGS + ("--no-interactive", "-p"):
                self.assertNotIn(bad, c["argv"])
            self.assertFalse(any(a.startswith("--trust-tools") for a in c["argv"]))

    def test_the_old_sigint_handler_is_back_on_every_exit_path(self):
        code = ("import signal, sys\nfrom umwayi import cli\n"
                "rc = cli.main(['--root', sys.argv[1], 'agent', 'chat', sys.argv[2]])\n"
                "print('HANDLER', signal.getsignal(signal.SIGINT) is signal.default_int_handler, rc)\n")
        for name, lines, want in (("reviewer", "/quit\n", 0), ("blocked", "", 2), ("reviewer", "/exit 4\n", 2)):
            with self.subTest(agent=name, lines=lines):
                r = subprocess.run([sys.executable, "-c", code, str(self.root), name], input=lines, capture_output=True,
                                   text=True, env=self.env(self.script()), cwd=str(self.tmp), timeout=60)
                self.assertIn(f"HANDLER True {want}", r.stdout, r.stdout + r.stderr)

    def test_chat_takes_no_prompt(self):
        self.assertEqual(self.umwayi("chat", "reviewer", "--prompt", "x").returncode, 64)
        self.assertEqual(self.calls(), [])


class ProcessTreeTests(unittest.TestCase):
    """In process: the /proc helpers the chat stop relies on."""

    def test_descendants_are_found_and_a_reused_pid_is_never_matched(self):
        child = subprocess.Popen([sys.executable, "-c",
                                  "import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', "
                                  "'import time; time.sleep(30)']); time.sleep(30)"])
        self.addCleanup(lambda: (child.kill(), child.wait()))
        end = time.monotonic() + 10
        found = {}
        while len(found) < 1 and time.monotonic() < end:
            found = agents._descendants(child.pid)
            time.sleep(0.05)
        self.assertEqual(len(found), 1)  # the grandchild
        [(pid, start)] = found.items()
        self.addCleanup(lambda: os.kill(pid, signal.SIGKILL) if alive(pid) else None)
        self.assertTrue(agents._same_process(pid, start))
        self.assertFalse(agents._same_process(pid, start + 1))  # same pid, other start time: another process
        self.assertIn(child.pid, agents._descendants(os.getpid()))
        os.kill(pid, signal.SIGKILL)
        time.sleep(0.3)
        self.assertFalse(agents._same_process(pid, start))  # dead, or a zombie until reaped

    def test_proc_stat_of_a_missing_pid(self):
        self.assertIsNone(agents._proc_stat(2 ** 22 + 12345))


class ChatArgumentListTests(unittest.TestCase):
    def test_every_chat_list(self):
        for kiro_agent in (None, "a", "Site_agent-1"):
            for tools in ((), ("read_file",), agents.KIRO_TOOL_IDS):
                a = agents.Agent("k", "kiro", "kiro-cli", "cli", "/w", kiro_agent=kiro_agent, trust_tools=tools)
                argv, stdin = agents.build_argv(a, agents.CHAT, "/bin/kiro-cli", "/r", "/usr/bin/python3")
                self.assertEqual(argv, ["/bin/kiro-cli", "chat", "--v3"] + (["--agent", kiro_agent] if kiro_agent else []))
                self.assertIsNone(stdin)
        for turns in (None, 5):
            a = agents.Agent("c", "claude-code", "claude", "cli", "/w", max_turns=turns)
            argv, stdin = agents.build_argv(a, agents.CHAT, "/bin/claude", "/r", "/usr/bin/python3")
            self.assertEqual(argv[:4], ["/bin/claude", "--permission-mode", "default", "--settings"])
            self.assertEqual(len(argv), 5)  # max_turns is print mode only
            self.assertIsNone(stdin)


if __name__ == "__main__":
    unittest.main()
