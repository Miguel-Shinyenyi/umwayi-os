"""W28: `umwayi login [--agents PATH]`, the login wizard.

Every test runs `python -m umwayi login` as a real child process with the fakes of layer 10: the fake `node` for a Claude Code
agent with transport acp (its sign-in is `ADAPTER --cli auth login --claudeai`), the fake `claude` for transport cli (only its
`auth status --json`), the fake `kiro-cli` (`whoami` and `login`) and the fake `opencode`. A sign-in is offered only on a real
pseudo terminal. No real login, no network, no key. Planted words stand for what must never reach umwayi's output, its
logbook or its queue: the email and organisation the login check's output holds, the code and secret a sign-in prints, and
the value of KIRO_API_KEY, which must never reach any child either.
"""

import fcntl
import json
import os
import select
import subprocess
import sys
import termios
import time
import unittest

from umwayi import agents

from tests.agents.support import SECRET
from tests.agents.test_agents_login import PLANTED, SIGNED_OUT, SUB, LoginCase

SUB_ENV = {"FAKE_CLAUDE_AUTH": json.dumps(SUB), "FAKE_CLAUDE_AUTH_EXIT": "0"}
KEY_WORD = "PLANTED-KIRO-KEY-VALUE"  # the value of KIRO_API_KEY: it must never be passed, shown or kept
AGENTS = """agents:
  - name: reviewer
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
  - name: oc
    platform: opencode
    command: opencode
    workdir: {work}
    provider: opencode
    model: opencode/big-pickle
"""
ONLY_KIRO = """agents:
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
ASK_KIRO = """  - id: login-ask-kiro
    title: kacp asks
    text: The owner decides.
    verdict: ask
    matchers:
      type: agent_login
      agent: kacp
"""
FORBIDDEN = agents.LOGIN_FORBIDDEN + ("--social", "--identity-provider", "--license", "--email", "--account", "--provider")


class WizardCase(LoginCase):
    def setUp(self):
        super().setUp()
        self.write_agents(AGENTS)
        self.fake_opencode()
        self.state = self.tmp / "kiro-signed-in"

    def env_extra(self, **extra):
        base = {"KIRO_API_KEY": KEY_WORD, "FAKE_PLANT": SECRET, "FAKE_KIRO_STATE": str(self.state),
                "FAKE_CLAUDE_AUTH": '{"loggedIn": false, "authMethod": "none", "email": "owner@example.invalid"}',
                "FAKE_CLAUDE_AUTH_EXIT": "1"}
        base.update(extra)
        return base

    def wizard(self, *args, extra=None):
        """The wizard with pipes: not a terminal, so it only reports."""
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "login", *args],
                           capture_output=True, text=True, env=self.env(self.env_extra(**(extra or {}))),
                           cwd=str(self.tmp), stdin=subprocess.DEVNULL, timeout=120)
        self.assertIn(r.returncode, (0, 2, 3, 64), r.stdout + r.stderr)
        return r

    def on_terminal(self, answers, extra=None, timeout=120):
        """The wizard on a pseudo terminal. Each time it asks [y/N], the next answer is typed. Returns (code, screen)."""
        master, slave = os.openpty()

        def controlling_terminal():
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        p = subprocess.Popen([sys.executable, "-m", "umwayi", "--root", str(self.root), "login"],
                             stdin=slave, stdout=slave, stderr=slave, env=self.env(self.env_extra(**(extra or {}))),
                             cwd=str(self.tmp), start_new_session=True, preexec_fn=controlling_terminal)
        os.close(slave)
        self.addCleanup(lambda: (p.poll() is None and p.kill(), os.close(master)))
        screen, asked, todo = b"", 0, list(answers)
        end = time.monotonic() + timeout
        while p.poll() is None and time.monotonic() < end:
            r, _, _ = select.select([master], [], [], 0.2)
            if r:
                try:
                    screen += os.read(master, 65536)
                except OSError:
                    break
            if screen.count(b"[y/N] ") > asked:
                asked += 1
                os.write(master, ((todo.pop(0) if todo else "") + "\n").encode())
        try:
            while True:
                r, _, _ = select.select([master], [], [], 0.2)
                if not r:
                    break
                chunk = os.read(master, 65536)
                if not chunk:
                    break
                screen += chunk
        except OSError:
            pass
        p.wait(timeout=30)
        return p.returncode, screen.decode("utf-8", "replace").replace("\r\n", "\n")

    def kill_on(self):
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "kill", "on", "--reason", "test"],
                           capture_output=True, text=True, env=self.env(), cwd=str(self.tmp), timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def by(self, probe):
        return [c for c in self.calls() if c.get("probe") == probe]

    def nothing_started(self):
        self.assertEqual(self.by("kiro login"), [], "a Kiro sign-in was started")
        self.assertEqual(self.logins(), [], "a Claude sign-in was started")
        self.assertEqual([c for c in self.calls() if c.get("started")], [], "an agent was started")
        self.assertFalse(any(c.get("started") for c in self.node_calls()), "an agent was started")

    def assert_never_kept_or_shown(self, text):
        """umwayi's own lines, its logbook and its queue never hold a planted word or the key."""
        for p in PLANTED + (KEY_WORD,):
            self.assertNotIn(p, text)
            self.assertNotIn(p, self.kept())

    def assert_no_key_passed(self):
        """KIRO_API_KEY never reaches a Kiro program (10.R12.13) or the Claude Code sign-in (the allow list of 10.R11.9);
        no program gets a word that picks an account or lists accounts."""
        recorded = [c for c in self.calls() if "env_keys" in c and c.get("prog") == "kiro-cli"]
        recorded += [c for c in self.node_calls() if "env_keys" in c]
        for c in recorded:
            self.assertNotIn("KIRO_API_KEY", c["env_keys"], c.get("argv"))
        for c in self.calls() + self.node_calls():
            argv = c.get("argv", [])
            for w in argv:
                self.assertNotIn(w, FORBIDDEN, argv)
            self.assertFalse("auth" in argv and "list" in argv, argv)

    def umwayi_lines(self, screen):
        """The lines umwayi wrote itself: the report, the prompts and what agent login prints (never the sign-in's)."""
        own = ("ok: ", "needs a sign-in: ", "cannot be checked: ", "not offered: ", "Sign in agent ", "Agent ",
               "Claude subscription", "Kiro login", "Refused", "The kill switch", "Not a terminal", "Ask me first",
               "Rule:", "Reason:", "Added queue item", "Queue item")
        return "\n".join(line for line in screen.splitlines() if line.startswith(own))


# ================================================================ the report, without a terminal


class ReportTests(WizardCase):
    def test_one_line_per_agent_and_nothing_started_without_a_terminal(self):
        self.answers(auth_json=SIGNED_OUT, auth_exit=1, secret=SECRET)
        r = self.wizard(extra={"FAKE_KIRO_WHOAMI_EXIT": "1"})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        lines = self.lines(r)
        self.assertTrue(lines[0].startswith("needs a sign-in: reviewer (claude-code, acp): not signed in."), lines)
        self.assertTrue(lines[1].startswith("needs a sign-in: terminal (claude-code, cli): not signed in."), lines)
        self.assertTrue(lines[1].endswith(" umwayi starts no sign-in for a Claude Code agent with transport cli."))
        self.assertEqual(lines[2], "needs a sign-in: helper (kiro, cli): Kiro is not signed in (kiro-cli whoami exited 1). "
                                   "Sign in to Kiro first (kiro-cli login), then try again.")
        self.assertTrue(lines[3].startswith("needs a sign-in: kacp (kiro, acp): Kiro is not signed in"))
        self.assertEqual(lines[4], "not offered: oc (opencode, acp): umwayi does not check or start an OpenCode sign-in. "
                                   "If your route needs one, run opencode auth login yourself.")
        self.assertEqual(lines[5], "Not a terminal, so no sign-in is offered. Run umwayi login on a terminal, or umwayi "
                                   "agent login NAME, to sign in.")
        self.assertEqual(len(lines), 6)
        self.assertNotIn("[y/N]", r.stdout)
        self.nothing_started()
        self.assertFalse((self.root / "LOGBOOK.md").exists(), "the report wrote the logbook")
        self.assertFalse((self.root / "queue.md").exists(), "the report wrote the queue")
        self.assert_never_kept_or_shown(r.stdout + r.stderr)
        self.assert_no_key_passed()

    def test_every_agent_signed_in_is_0_and_offers_nothing(self):
        self.answers(auth_json=SUB, secret=SECRET)
        r = self.wizard(extra=SUB_ENV)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        lines = self.lines(r)
        self.assertEqual([l.split(":")[0] for l in lines], ["ok", "ok", "ok", "ok", "not offered"])
        self.assertIn("ok: reviewer (claude-code, acp): Claude subscription (plan: max)", lines)
        self.assertIn("ok: terminal (claude-code, cli): Claude subscription (plan: max)", lines)
        self.nothing_started()
        self.assert_never_kept_or_shown(r.stdout + r.stderr)

    def test_an_agent_that_cannot_be_checked_is_2(self):
        os.unlink(self.bin / "kiro-cli")
        self.answers(auth_json=SUB, secret=SECRET)
        r = self.wizard(extra=SUB_ENV)
        self.assertEqual(r.returncode, 2)
        self.assertIn("cannot be checked: helper (kiro, cli): command: kiro-cli was not found on PATH", r.stdout)
        self.nothing_started()

    def test_only_opencode_is_not_checked_and_starts_nothing(self):
        self.write_agents("agents:\n  - name: oc\n    platform: opencode\n    command: opencode\n    workdir: {work}\n"
                          "    provider: opencode\n    model: opencode/big-pickle\n")
        r = self.wizard()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(self.lines(r)), 1)
        self.assertEqual(self.calls(), [], "opencode was asked something")

    def test_the_kill_switch_holds_every_sign_in_and_is_3(self):
        self.kill_on()
        self.write_agents(ONLY_KIRO)
        r = self.wizard(extra={"FAKE_KIRO_WHOAMI_EXIT": "1"})
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("The kill switch is on, so no sign-in is offered.", r.stdout)
        self.nothing_started()

    def test_usage_errors_are_64(self):
        (self.root / "agents.yaml").unlink()
        self.assertEqual(self.wizard().returncode, 64)
        self.write_agents("agents: [1]\n")
        self.assertEqual(self.wizard().returncode, 64)
        self.write_agents(ONLY_KIRO)
        self.assertEqual(self.wizard("--agents", "missing.yaml").returncode, 64)
        self.assertEqual(self.wizard("helper").returncode, 64)  # no agent name: the wizard walks the file
        self.nothing_started()


# ================================================================ on a terminal


class TerminalTests(WizardCase):
    def setUp(self):
        super().setUp()
        self.write_agents(ONLY_KIRO)

    def test_yes_starts_the_agents_own_sign_in_and_no_starts_nothing(self):
        code, screen = self.on_terminal(["y", "n"], extra={"FAKE_KIRO_WHOAMI_EXIT": "1"})
        self.assertEqual(code, 2, screen)  # kacp said no, so it is still not signed in
        self.assertIn("Sign in agent helper now? [y/N] ", screen)
        self.assertIn("Sign in agent kacp now? [y/N] ", screen)
        self.assertIn("Kiro login OK.", screen)
        self.assertIn("Agent kacp was not signed in. Nothing was started.", screen)
        [run] = self.by("kiro login")
        self.assertEqual(run["argv"], ["login"])  # the tool's own login, with no word added
        self.assertTrue(run["tty"], "the sign-in did not get the terminal")
        added = [e.added for e in self.entries() if e.source == agents.SOURCE]
        self.assertEqual(added, ["Started login for agent helper (kiro-cli login)", "Login for agent helper ended: Kiro login OK"])
        self.assertIn("Rule login-yes gave Yes; action type: agent_login",
                      [e.added for e in self.entries() if e.source == "umwayi check"])
        self.assertIn(SECRET, screen)  # the owner sees what the sign-in printed, on the owner's terminal
        self.assert_never_kept_or_shown(self.umwayi_lines(screen))
        self.assertNotIn(KEY_WORD, screen)
        self.assert_no_key_passed()

    def test_yes_to_every_agent_signs_in_one_at_a_time_and_is_0(self):
        code, screen = self.on_terminal(["yes", "Y"], extra={"FAKE_KIRO_WHOAMI_EXIT": "1"})
        self.assertEqual(code, 0, screen)
        self.assertEqual(screen.count("[y/N] "), 2)
        runs = self.by("kiro login")
        self.assertEqual(len(runs), 1, "the second agent was already signed in after the first sign-in")
        self.assertEqual(screen.count("Kiro login OK"), 2)
        self.assert_never_kept_or_shown(self.umwayi_lines(screen))

    def test_an_empty_answer_or_anything_else_is_no(self):
        code, screen = self.on_terminal(["", "maybe"], extra={"FAKE_KIRO_WHOAMI_EXIT": "1"})
        self.assertEqual(code, 2, screen)
        self.nothing_started()
        self.assertFalse((self.root / "LOGBOOK.md").exists())

    def test_ask_me_first_for_agent_login_starts_nothing_and_is_3(self):
        self.write_rules((self.root / "rules.yaml").read_text(encoding="utf-8") + ASK_KIRO)
        self.write_agents("agents:\n  - name: kacp\n    platform: kiro\n    command: kiro-cli\n    transport: acp\n"
                          "    workdir: {work}\n")
        code, screen = self.on_terminal(["y"], extra={"FAKE_KIRO_WHOAMI_EXIT": "1"})
        self.assertEqual(code, 3, screen)
        self.assertIn("Ask me first", screen)
        self.assertIn("Log in agent kacp?", (self.root / "queue.md").read_text(encoding="utf-8"))
        self.nothing_started()

    def test_rules_no_for_agent_login_starts_nothing_and_is_2(self):
        self.write_rules((self.root / "rules.yaml").read_text(encoding="utf-8").replace("agent: [reviewer, helper, kacp]",
                                                                                          "agent: [reviewer]"))
        self.write_agents("agents:\n  - name: blocked\n    platform: kiro\n    command: kiro-cli\n    workdir: {work}\n")
        rules = (self.root / "rules.yaml").read_text(encoding="utf-8").replace("agent: blocked", "agent: [blocked]")
        self.write_rules(rules)
        code, screen = self.on_terminal(["y"], extra={"FAKE_KIRO_WHOAMI_EXIT": "1"})
        self.assertEqual(code, 2, screen)
        self.assertIn("Rule: login-no", screen)
        self.nothing_started()

    def test_the_kill_switch_on_a_terminal_offers_nothing(self):
        self.kill_on()
        code, screen = self.on_terminal(["y", "y"], extra={"FAKE_KIRO_WHOAMI_EXIT": "1"})
        self.assertEqual(code, 3, screen)
        self.assertNotIn("[y/N]", screen)
        self.nothing_started()

    def test_a_claude_cli_agent_is_never_offered_a_sign_in(self):
        self.write_agents("agents:\n  - name: terminal\n    platform: claude-code\n    command: claude\n    workdir: {work}\n")
        code, screen = self.on_terminal(["y"])
        self.assertEqual(code, 2, screen)
        self.assertNotIn("[y/N]", screen)
        self.assertIn("umwayi starts no sign-in for a Claude Code agent with transport cli.", screen)
        self.nothing_started()
        self.assertNotIn("owner@example.invalid", screen)

    def test_a_claude_acp_agent_signs_in_with_the_claude_ai_login_only(self):
        self.answers(auth_json=SIGNED_OUT, auth_exit=1, login_flips_to=SUB, secret=SECRET)
        self.write_agents("agents:\n  - name: reviewer\n    platform: claude-code\n    command: claude\n    transport: acp\n"
                          "    workdir: {work}\n")
        code, screen = self.on_terminal(["y"])
        self.assertEqual(code, 0, screen)
        self.assertIn("Claude subscription OK (plan: max).", screen)
        [run] = self.logins()
        self.assertEqual(run["argv"][-4:], ["--cli", "auth", "login", "--claudeai"])
        self.assert_never_kept_or_shown(self.umwayi_lines(screen))
        self.assert_no_key_passed()


# ================================================================ the code


class CodeTests(unittest.TestCase):
    def test_the_wizard_starts_nothing_itself_and_reads_no_secret(self):
        from pathlib import Path
        text = (Path(agents.__file__).with_name("loginwizard.py")).read_text(encoding="utf-8")
        for bad in ("subprocess", "os.environ", "Popen", "os.system", "getpass", "KIRO_API_KEY", "--social", "--email",
                    "opencode auth list", "whoami", "open(", "json.loads"):
            self.assertNotIn(bad, text.split('"""', 2)[2], bad)
        self.assertIn("agents.login_agent(", text)
        self.assertEqual(text.count("agents.login_agent("), 1, "one way to start a sign-in, the same as agent login")


if __name__ == "__main__":
    unittest.main()
