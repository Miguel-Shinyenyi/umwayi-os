"""G-0059 build 2 (docs/seatbelt-signin-design.md): the `token_env` key of an agent, checked and recorded, and nothing passes it yet.

The key holds the NAME of the owner's token variable, never a value. These tests use a planted fake value and show that it never reaches an error, a
line or a child environment. No token is created, read or asked for, and no helper is started."""
import os
import unittest
from unittest import mock

from umwayi import agents

from tests.agents.support import AgentCase

NAME = "CLAUDE_CODE_OAUTH_TOKEN"
PLANTED = "sk-ant-oat01-PLANTED-FAKE-VALUE"
HEAD = "agents:\n  - name: c\n    platform: claude-code\n    command: claude\n    workdir: {work}\n"


class KeyTests(AgentCase):
    def load(self, extra):
        self.write_agents(HEAD + extra)
        return agents.find(agents.load(self.root), "c")

    def refused(self, extra, head=HEAD):
        """The problem lines of agents.yaml (never the text of a line), joined; the file must have at least one."""
        self.write_agents(head + extra)
        loaded, problems = agents.check_text((self.root / "agents.yaml").read_text(encoding="utf-8"), self.root)
        self.assertIsNone(loaded)
        self.assertTrue(problems, "the file was accepted")
        return " ".join(p.message for p in problems)

    def test_the_name_with_confine_true_is_accepted_and_recorded(self):
        a = self.load(f"    confine: true\n    token_env: {NAME}\n")
        self.assertEqual(a.token_env, NAME)

    def test_an_agent_without_the_key_has_none(self):
        self.assertIsNone(self.load("    confine: true\n").token_env)

    def test_any_other_name_or_a_value_is_refused_and_the_message_never_echoes_it(self):
        for bad in ("ANTHROPIC_API_KEY", "MY_TOKEN", PLANTED, "''", "5"):
            msg = self.refused(f"    confine: true\n    token_env: {bad}\n")
            self.assertIn("token_env", msg, bad)
            self.assertNotIn("PLANTED", msg, bad)

    def test_without_confine_true_it_is_refused(self):
        self.assertIn("confine", self.refused(f"    token_env: {NAME}\n"))
        self.assertIn("confine", self.refused(f"    confine: false\n    token_env: {NAME}\n"))

    def test_it_is_only_for_claude_code(self):
        kiro = "agents:\n  - name: k\n    platform: kiro\n    command: kiro-cli\n    workdir: {work}\n"
        self.assertIn("only for platform claude-code", self.refused(f"    confine: true\n    token_env: {NAME}\n", head=kiro))


class NothingPassesItYetTests(unittest.TestCase):
    def test_env_keep_still_refuses_the_name(self):
        self.assertIsNotNone(agents.keep_problem(NAME))

    def test_no_child_environment_carries_the_variable_or_its_value(self):
        with mock.patch.dict(os.environ, {NAME: PLANTED, "PATH": "/usr/bin"}):
            fake = type("A", (), {"platform": "claude-code", "env_keep": ()})()
            self.assertNotIn(NAME, agents.enforced_env(os.environ, fake))
            self.assertNotIn(NAME, agents.claude_env(os.environ))
            self.assertNotIn(PLANTED, "".join(agents.claude_env(os.environ).values()))

    def test_the_logbook_line_is_fixed_and_holds_the_name_only(self):
        line = agents.token_line(NAME)
        self.assertEqual(line, "token variable CLAUDE_CODE_OAUTH_TOKEN passed to the helper (the name only; the value was not read)")
        self.assertNotIn("=", line)
        with self.assertRaises(ValueError):
            agents.token_line("ANTHROPIC_API_KEY")

    def test_nothing_in_agents_calls_the_line_yet(self):
        src = open(agents.__file__, encoding="utf-8").read()
        self.assertEqual(src.count("token_line("), 1)  # its definition only: the start that writes it is a later build


if __name__ == "__main__":
    unittest.main()
