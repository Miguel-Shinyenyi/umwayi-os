"""Layer 10 part 7c-2: `umwayi agent login NAME` (10.38, 10.R12.9) and Kiro subscription first (10.39, 10.R12.13).

Every test runs `python -m umwayi agent ...` as a real child process. For Claude Code the sign-in is the fake
`node` (tests/agents/fake_node.py) answering `ADAPTER --cli auth login --claudeai`: it prints a planted URL, code
and secret and can flip the scripted `auth status --json` to a subscription. For Kiro it is the fake `kiro-cli`
answering `login` and `whoami`. No real Claude Code or Kiro, no network, no key, no real login.
"""

import fcntl
import json
import os
import select
import signal
import subprocess
import sys
import termios
import time
import unittest

from umwayi import agents, runlock, taskqueue

from tests.agents.support import RULES, SECRET, AgentCase, alive
from tests.agents.test_agents_claude_acp_gate import ALLOWED, ClaudeAcpCase

AGENTS = """agents:
  - name: reviewer
    platform: claude-code
    command: claude
    transport: acp
    workdir: {work}
  - name: blocked
    platform: claude-code
    command: claude
    transport: acp
    workdir: {work}
  - name: asker
    platform: claude-code
    command: claude
    transport: acp
    workdir: {work}
  - name: unruled
    platform: claude-code
    command: claude
    transport: acp
    workdir: {work}
  - name: terminal
    platform: claude-code
    command: claude
    workdir: {work}
  - name: helper
    platform: kiro
    command: kiro-cli
    workdir: {work}
  - name: kacp
    platform: kiro
    command: kiro-cli
    transport: acp
    workdir: {work}
"""
LOGIN_RULES = RULES + """  - id: login-yes
    title: these agents may sign in
    text: The owner allows these sign-ins.
    verdict: yes
    matchers:
      type: agent_login
      agent: [reviewer, helper, kacp]
  - id: login-no
    title: blocked may not sign in
    text: Never.
    verdict: no
    matchers:
      type: agent_login
      agent: blocked
  - id: login-ask
    title: asker needs the owner
    text: The owner decides.
    verdict: ask
    matchers:
      type: agent_login
      agent: asker
  - id: start-unruled
    title: unruled may start, nothing more
    text: Only a start rule.
    verdict: yes
    matchers:
      type: agent_run
      agent: [unruled, terminal, helper, kacp]
"""
SUB = {"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "max",
       "email": "owner@example.invalid", "orgId": "org-PLANTED", "orgName": "Planted Org"}
SIGNED_OUT = {"loggedIn": False, "authMethod": "none", "email": "owner@example.invalid"}
KEY_IN_FRONT = {"loggedIn": True, "authMethod": "claude.ai", "apiKeySource": "ANTHROPIC_API_KEY",
                "subscriptionType": "max", "email": "owner@example.invalid"}
PLANTED = ("owner@example.invalid", "org-PLANTED", "Planted Org", "PLANTED-CODE", "claude.example.invalid",
           "login.example.invalid", SECRET)
LOGIN_ARGV_TAIL = ["--cli", "auth", "login", "--claudeai"]


class LoginCase(ClaudeAcpCase):
    def setUp(self):
        super().setUp()
        self.write_rules(LOGIN_RULES)
        self.write_agents(AGENTS)

    def login(self, name="reviewer", extra=None, **kw):
        return self.umwayi("login", name, extra=extra, **kw)

    def logins(self) -> list:
        return [c for c in self.node_calls() if c.get("probe") == "login run"]

    def kept(self, r=None) -> str:
        """What umwayi kept: its logbook and its queue (never the sign-in's output)."""
        text = ""
        for name in ("LOGBOOK.md", "queue.md"):
            p = self.root / name
            if p.exists():
                text += p.read_text(encoding="utf-8")
        return text + ((r.stderr) if r is not None else "")

    def assert_nothing_kept(self, r=None):
        kept = self.kept(r)
        for p in PLANTED:
            self.assertNotIn(p, kept)

    def login_entries(self) -> list:
        return [e.added for e in self.entries() if e.source == agents.SOURCE]

    def _wait_node_login(self, p, timeout=60):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.logins():
                return self.logins()[0]
            if p.poll() is not None:
                self.fail(f"umwayi exited ({p.returncode}) before the login started: {self._proc_output(p)}")
            time.sleep(0.05)
        self.fail("the login did not start")


# ====================================================== Claude Code: the sign-in itself


class ClaudeLoginTests(LoginCase):
    def test_a_login_that_signs_in_gives_the_subscription_line_and_0(self):
        self.answers(auth_json=SIGNED_OUT, auth_exit=1, login_flips_to=SUB, secret=SECRET)
        r = self.login()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.lines(r)[-1], "Claude subscription OK (plan: max).")
        [run] = self.logins()
        self.assertEqual(run["argv"], [str(self.node), str(self.adapter), *LOGIN_ARGV_TAIL])
        self.assertEqual(run["cwd"], str(self.work))
        self.assertEqual(run["stdin"], 0)  # umwayi never writes to it
        probes = [c["probe"] for c in self.node_calls()]
        self.assertEqual(probes, ["node version", "adapter version", "claude code version", "login", "login run",
                                  "login"])  # no hook checks: the sign-in runs no agent and no tool
        added = self.login_entries()
        self.assertEqual(added[0], "Started login for agent reviewer (claude.ai)")
        self.assertEqual(added[1], "Login for agent reviewer ended: subscription OK (plan: max)")
        self.assertEqual([e.added for e in self.entries() if e.source == "umwayi check"
                          and "agent_login" in e.added], ["Rule login-yes gave Yes; action type: agent_login"])
        self.assert_nothing_kept(r)
        self.assertNotIn("owner@example.invalid", r.stdout)  # the login check's own output is never shown
        self.assertFalse(any(c.get("started") for c in self.node_calls()), "an agent was started")

    def test_a_failed_login_gives_2_with_the_refusal_line(self):
        self.answers(auth_json=SIGNED_OUT, auth_exit=1, login_exit=1)
        r = self.login()
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertTrue(self.lines(r)[-1].startswith("Refused: login: not signed in. Sign in to Claude Code with "
                                                     "your Claude subscription first"), r.stdout)
        self.assertEqual(len(self.logins()), 1)
        self.assertIn("Login for agent reviewer ended: not gated (login: not signed in.", self.login_entries()[-1])
        self.assertIn("the login exited with code 1", self.entries()[-1].checked)

    def test_a_key_still_in_front_after_the_login_gives_2(self):
        self.answers(auth_json=SIGNED_OUT, auth_exit=1, login_flips_to=KEY_IN_FRONT)
        r = self.login()
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("Refused: login: an API key from ANTHROPIC_API_KEY pays, not your Claude subscription",
                      r.stdout)
        self.assert_nothing_kept(r)

    def test_already_a_subscription_starts_nothing_and_gives_0(self):
        self.answers(auth_json=SUB)
        r = self.login()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.lines(r)[-1], "Claude subscription OK (plan: max). Nothing was started.")
        self.assertEqual(self.logins(), [])
        self.assertEqual(self.login_entries(), ["Login for agent reviewer not needed: Claude subscription OK (plan: max)"])

    def test_the_environment_is_child_env_plus_only_the_login_names(self):
        self.answers(auth_json=SIGNED_OUT, auth_exit=1, login_flips_to=SUB)
        extra = {"BROWSER": "/usr/bin/true", "DISPLAY": ":9", "SSH_TTY": "/dev/pts/9", "TERM": "xterm",
                 "CLAUDE_CODE_OAUTH_REFRESH_TOKEN": SECRET, "CLAUDE_CODE_OAUTH_SCOPES": SECRET,
                 "CLAUDE_CODE_REMOTE": "1", "ANTHROPIC_API_KEY": SECRET, "KIRO_API_KEY": SECRET,
                 "SOMETHING_ELSE": SECRET}
        r = self.login(extra=extra)
        self.assertEqual(r.returncode, 0, r.stdout)
        [run] = self.logins()
        names = set(run["env"])
        self.assertLessEqual(names, ALLOWED | set(agents.LOGIN_ENV_NAMES))
        self.assertLessEqual({"BROWSER", "DISPLAY", "SSH_TTY", "TERM"}, names)
        for never in ("CLAUDE_CODE_OAUTH_REFRESH_TOKEN", "CLAUDE_CODE_OAUTH_SCOPES", "CLAUDE_CODE_REMOTE",
                      "ANTHROPIC_API_KEY", "KIRO_API_KEY", "SOMETHING_ELSE"):
            self.assertNotIn(never, names)
        self.assertFalse(run["secret_in_env"])
        after = [c for c in self.node_calls() if c["probe"] == "login"][-1]  # the check after: the start env only
        self.assertLessEqual(set(after["env"]), ALLOWED)

    def test_the_kill_switch_during_the_login_gives_3_and_nothing_alive(self):
        self.answers(auth_json=SIGNED_OUT, auth_exit=1, login_hang=True)
        p = self.start_umwayi("login", "reviewer")
        run = self._wait_node_login(p)
        (self.root / ".umwayi").mkdir(exist_ok=True)
        (self.root / ".umwayi" / "KILL").write_text("", encoding="utf-8")
        code, out, _ = self.finish(p)
        self.assertEqual(code, 3, out)
        self.assertIn("The kill switch stopped the login for agent reviewer (exit 3).", out)
        self.assertFalse(alive(run["pid"]))
        self.assertEqual(self.login_entries()[-1], "The kill switch stopped the login for agent reviewer")

    def test_the_limit_and_the_logbook_stop_the_login_with_2(self):
        self.answers(auth_json=SIGNED_OUT, auth_exit=1, login_hang=True)
        p = self.start_umwayi("login", "reviewer", extra={"UMWAYI_TEST_LOGIN_TIMEOUT": "2"})
        run = self._wait_node_login(p)
        code, out, _ = self.finish(p)
        self.assertEqual(code, 2, out)
        self.assertIn("The login for agent reviewer was stopped after its limit of", out)
        self.assertFalse(alive(run["pid"]))
        os.remove(self.bin / "node-calls.jsonl")
        p = self.start_umwayi("login", "reviewer")
        run = self._wait_node_login(p)
        with open(self.root / "LOGBOOK.md", "a", encoding="utf-8") as f:
            f.write("edited by hand while the login runs\n")
        code, out, _ = self.finish(p)
        self.assertEqual(code, 2, out)
        self.assertIn("The logbook can no longer be written", out)
        self.assertIn("so the login for agent reviewer was stopped", out)
        self.assertFalse(alive(run["pid"]))

    def test_the_login_gets_the_owners_terminal_and_umwayi_never_reads_it(self):
        """On a real pseudo terminal: what the sign-in prints reaches the owner's screen, never umwayi."""
        self.answers(auth_json=SIGNED_OUT, auth_exit=1, login_flips_to=SUB, secret=SECRET)
        master, slave = os.openpty()

        def controlling_terminal():
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        p = subprocess.Popen([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "login", "reviewer"],
                             stdin=slave, stdout=slave, stderr=slave, env=self.env(), cwd=str(self.tmp),
                             start_new_session=True, preexec_fn=controlling_terminal)
        os.close(slave)
        self.addCleanup(lambda: (p.poll() is None and p.kill(), os.close(master)))
        screen = b""
        end = time.monotonic() + 60
        while p.poll() is None and time.monotonic() < end:
            r, _, _ = select.select([master], [], [], 0.2)
            if r:
                try:
                    screen += os.read(master, 65536)
                except OSError:
                    break
        p.wait(timeout=30)
        self.assertEqual(p.returncode, 0, screen)
        self.assertIn(b"PLANTED-CODE", screen)  # the owner sees the sign-in
        self.assertIn(b"Claude subscription OK (plan: max).", screen)
        [run] = self.logins()
        self.assertTrue(run["tty"], "the sign-in did not get the terminal")
        self.assert_nothing_kept()


# ======================================================= Claude Code: what starts nothing


class ClaudeLoginRefusedTests(LoginCase):
    def assert_no_login(self):
        self.assertEqual(self.logins(), [], "a login was started")

    def test_rules_no_ask_and_no_login_rule_start_nothing(self):
        self.answers(auth_json=SIGNED_OUT, auth_exit=1)
        r = self.login("blocked")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("Rule: login-no", r.stdout)
        for _ in range(2):
            r = self.login("asker")
            self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("already asks the owner", r.stdout)
        self.assertEqual([x.title for x in taskqueue.list_rows(self.root, status="open")], ["Log in agent asker?"])
        r = self.login("unruled")  # a rule for agent_run never allows a sign-in
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("Log in agent unruled?", [x.title for x in taskqueue.list_rows(self.root, status="open")])
        self.assert_no_login()
        self.assertEqual(self.node_calls(), [])  # the rules come before every gate check

    def test_the_run_lock_and_the_kill_switch_give_3(self):
        self.answers(auth_json=SIGNED_OUT, auth_exit=1)
        with runlock.held(self.root):
            r = self.login()
        self.assertEqual(r.returncode, 3, r.stdout)
        (self.root / ".umwayi" / "KILL").write_text("", encoding="utf-8")
        r = self.login()
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assert_no_login()

    def test_a_failing_gate_check_before_the_login_starts_nothing(self):
        self.answers(auth_json=SIGNED_OUT, auth_exit=1, adapter_version="0.100.0\n")
        r = self.login()
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("no: adapter version", r.stdout)
        self.assertIn("Refused: the login for agent reviewer cannot be started (exit 2). Nothing was started.", r.stdout)
        self.assert_no_login()
        self.assertTrue(self.login_entries()[-1].startswith("Refused login for agent reviewer: not gated (adapter version"))

    def test_only_claude_code_acp_and_kiro_agents_can_sign_in(self):
        r = self.login("terminal")
        self.assertEqual(r.returncode, 64, r.stdout + r.stderr)
        self.assertIn("agent login is only for platform claude-code with transport acp, or platform kiro", r.stderr)
        self.assertEqual(self.login("nobody").returncode, 64)
        self.assertEqual(self.umwayi("login").returncode, 64)
        self.assertEqual(self.umwayi("login", "reviewer", "extra").returncode, 64)
        self.assert_no_login()

    def test_agent_run_and_agent_chat_never_start_a_login_and_name_it(self):
        self.answers(auth_json=SIGNED_OUT, auth_exit=1)
        r = self.umwayi("chat", "unruled")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual(self.lines(r)[-1], "Run umwayi agent login unruled to sign in.")
        r = self.umwayi("run", "unruled", "--prompt", "x",
                        extra={"FAKE_CLAUDE_AUTH": json.dumps(SIGNED_OUT), "FAKE_CLAUDE_AUTH_EXIT": "1"})
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual(self.lines(r)[-1], "Run umwayi agent login unruled to sign in.")
        self.assert_no_login()
        self.assertFalse(any(c.get("argv", [])[:2] == ["auth", "login"] for c in self.calls()))

    def test_a_terminal_claude_agent_is_not_told_to_use_agent_login(self):
        r = self.umwayi("run", "terminal", "--prompt", "x",
                        extra={"FAKE_CLAUDE_AUTH": json.dumps(SIGNED_OUT), "FAKE_CLAUDE_AUTH_EXIT": "1"})
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertNotIn("agent login", r.stdout)


# ============================================================================ Kiro (10.39)


class KiroCase(AgentCase):
    def setUp(self):
        super().setUp()
        self.fake("kiro-cli")
        self.write_rules(LOGIN_RULES)
        self.write_agents(AGENTS)
        self.kiro_hook_file(command=self.kiro_command(python=sys.executable))
        self.state = self.tmp / "kiro-signed-in"

    def kiro(self, **extra):
        return dict({"KIRO_API_KEY": SECRET, "FAKE_PLANT": SECRET}, **extra)

    def by(self, probe):
        return [c for c in self.calls() if c.get("probe") == probe]

    def assert_no_key(self):
        recorded = [c for c in self.calls() if "env_keys" in c]
        self.assertTrue(recorded)
        for c in recorded:
            self.assertNotIn("KIRO_API_KEY", c["env_keys"], c.get("argv"))


class KiroTests(KiroCase):
    def test_kiro_api_key_never_reaches_run_chat_acp_whoami_or_login(self):
        r = self.umwayi("run", "helper", "--prompt", "hello", extra=self.kiro())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "chat", "helper"],
                           input="", capture_output=True, text=True, timeout=120, env=self.env(self.kiro()),
                           cwd=str(self.tmp))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "chat", "kacp"],
                           input=":quit\n", capture_output=True, text=True, timeout=120,
                           env=self.env(self.kiro(FAKE_ACP="{}")), cwd=str(self.tmp))
        self.assertIn(r.returncode, (0, 2), r.stdout + r.stderr)
        r = self.umwayi("login", "helper", extra=self.kiro(FAKE_KIRO_WHOAMI_EXIT="1", FAKE_KIRO_STATE=str(self.state)))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        starts = [c["argv"][:1] for c in self.calls() if c.get("started")]
        self.assertEqual(starts, [["chat"], ["chat"], ["acp"]])
        self.assertTrue(self.by("whoami") and self.by("kiro login"))
        self.assert_no_key()

    def test_whoami_failing_refuses_every_start_and_names_agent_login(self):
        r = self.umwayi("run", "helper", "--prompt", "hello", extra=self.kiro(FAKE_KIRO_WHOAMI_EXIT="1"))
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("no: login: Kiro is not signed in (kiro-cli whoami exited 1). Sign in to Kiro first "
                      "(kiro-cli login), then try again.", r.stdout)
        self.assertEqual(self.lines(r)[-1], "Run umwayi agent login helper to sign in.")
        self.assertEqual([c for c in self.calls() if c.get("started")], [])
        self.assertIn("Refused agent helper: not gated (login: Kiro is not signed in", self.entries()[-1].added)
        for text in (r.stdout, r.stderr, (self.root / "LOGBOOK.md").read_text(encoding="utf-8")):
            self.assertNotIn("owner@example.invalid", text)
            self.assertNotIn(SECRET, text)
        r = self.umwayi("check", "helper", extra=self.kiro(FAKE_KIRO_WHOAMI_EXIT="1"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("not run: hook script", r.stdout)

    def test_whoami_that_hangs_refuses_after_15_s(self):
        t = time.monotonic()
        r = self.umwayi("run", "helper", "--prompt", "hello", extra=self.kiro(FAKE_KIRO_WHOAMI_HANG="1"))
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("Kiro is not signed in (no answer within 15 s)", r.stdout)
        self.assertLess(time.monotonic() - t, 60)
        self.assertEqual([c for c in self.calls() if c.get("started")], [])

    def test_agent_login_for_kiro(self):
        r = self.umwayi("login", "helper", extra=self.kiro())  # whoami already 0
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.lines(r)[-1], "Kiro login OK. Nothing was started.")
        self.assertEqual(self.by("kiro login"), [])
        r = self.umwayi("login", "kacp", extra=self.kiro(FAKE_KIRO_WHOAMI_EXIT="1", FAKE_KIRO_STATE=str(self.state)))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.lines(r)[-1], "Kiro login OK.")
        [run] = self.by("kiro login")
        self.assertEqual(run["argv"], ["login"])  # no flags, ever
        added = [e.added for e in self.entries() if e.source == agents.SOURCE]
        self.assertEqual(added[-2:], ["Started login for agent kacp (kiro-cli login)",
                                      "Login for agent kacp ended: Kiro login OK"])
        self.state.unlink()
        r = self.umwayi("login", "helper", extra=self.kiro(FAKE_KIRO_WHOAMI_EXIT="1", FAKE_KIRO_LOGIN_EXIT="1"))
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertTrue(self.lines(r)[-1].startswith("Refused: login: Kiro is not signed in"), r.stdout)
        log = (self.root / "LOGBOOK.md").read_text(encoding="utf-8")
        for p in ("PLANTED-CODE", "login.example.invalid", SECRET, "owner@example.invalid"):
            self.assertNotIn(p, log)
        self.assert_no_key()

    def test_the_kill_switch_stops_a_kiro_login(self):
        p = self.start_umwayi("login", "helper", extra=self.kiro(FAKE_KIRO_WHOAMI_EXIT="1", FAKE_KIRO_LOGIN_HANG="1"))
        run = self.wait_for(lambda c: c.get("probe") == "kiro login", timeout=60, what="the Kiro login", proc=p)
        (self.root / ".umwayi").mkdir(exist_ok=True)
        (self.root / ".umwayi" / "KILL").write_text("", encoding="utf-8")
        code, out, _ = self.finish(p)
        self.assertEqual(code, 3, out)
        self.assertFalse(alive(run["pid"]))


# ============================================================================ units and guards


class UnitTests(unittest.TestCase):
    def agent(self, platform, transport="cli"):
        return agents.Agent(name="a", platform=platform, command="x", transport=transport, workdir="/w",
                            kiro_agent=None, trust_tools=(), max_turns=None, timeout_minutes=30)

    def test_build_argv_for_login(self):
        argv, stdin = agents.build_argv(self.agent("claude-code", "acp"), agents.LOGIN, "/n/node", "/r", "/py",
                                        src=agents.umwayi_src())
        self.assertEqual(argv, ["/n/node", str(agents.claude_acp_path(agents.CLAUDE_ACP_ADAPTER)), *LOGIN_ARGV_TAIL])
        self.assertIsNone(stdin)
        for transport in ("cli", "acp"):
            self.assertEqual(agents.build_argv(self.agent("kiro", transport), agents.LOGIN, "/k", "/r", "/py")[0],
                             ["/k", "login"])
        with self.assertRaises(agents.UsageError):
            agents.build_argv(self.agent("claude-code", "cli"), agents.LOGIN, "/c", "/r", "/py")

    def test_every_forbidden_login_word_is_refused_in_any_list(self):
        for word in agents.LOGIN_FORBIDDEN:
            for form in (word, word + "=x"):
                with self.subTest(word=form):
                    with self.assertRaises(RuntimeError):
                        agents._assert_allowed(["/k", "login", form])
        agents._assert_allowed(["/c", "-p", "--console is fine in a prompt"], skip=2)

    def test_login_env_and_kiro_env(self):
        env = {"HOME": "/h", "PATH": "/p", "BROWSER": "b", "NO_BROWSER": "1", "CLAUDE_CODE_OAUTH_REFRESH_TOKEN": "s",
               "CLAUDE_CODE_REMOTE": "1", "ANTHROPIC_API_KEY": "s", "KIRO_API_KEY": "s", "KIRO_HOME": "/k", "X": "y",
               "DISPLAY": 5}
        self.assertEqual(agents.login_env(env), {"HOME": "/h", "PATH": "/p", "BROWSER": "b", "NO_BROWSER": "1",
                                                 **agents.CHILD_ENV_SET})
        k = agents.kiro_env(env)
        self.assertNotIn("KIRO_API_KEY", k)
        self.assertEqual(k["KIRO_HOME"], "/k")  # the owner's choice of Kiro folder, not a credential
        self.assertEqual(set(env) - set(k), {"KIRO_API_KEY"})
        for never in ("CLAUDE_CODE_OAUTH_REFRESH_TOKEN", "CLAUDE_CODE_OAUTH_SCOPES", "CLAUDE_CODE_REMOTE"):
            self.assertNotIn(never, agents.LOGIN_ENV_NAMES)

    def test_no_test_argument_list_holds_console_email_or_sso(self):
        import ast
        from pathlib import Path
        for path in sorted(Path(__file__).parent.glob("*.py")) + [Path(agents.__file__)]:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.List) and len(node.elts) > 1:
                    words = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                    for bad in ("--console", "--email", "--sso"):
                        self.assertNotIn(bad, words, f"{path.name} line {node.lineno}")


if __name__ == "__main__":
    unittest.main()
