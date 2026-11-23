"""W41 B1 (W78 step 4): Claude Code's own sandbox settings for a start under a mode file that says `enforced`.

  * `agents.sandbox_problem`: None only when the --settings JSON holds exactly the three fixed keys (enabled, failIfUnavailable,
    allowUnsandboxedCommands false) and this machine can host the sandbox: macOS (built in), or Linux with `bwrap` and `socat` on
    PATH. Otherwise a reason from the fixed list: `profile` (missing or unreadable block), `platform`, `dependency`.
  * `claude_settings(sandbox=True)` adds the block; the default adds nothing, so today's start is unchanged.
  * `agent check` and the start share one gate: an enforced Claude Code agent with no sandbox is refused (exit 2) and nothing is
    started. A cooperative agent and a root with no mode file are as they were. The ACP adapter takes no --settings, so an
    enforced ACP agent is refused with `profile`.
  * Real starts (the fake claude records its argv): the sandbox block is in --settings when enforced and absent otherwise.

What none of this shows: that the sandbox holds. It reads the settings and looks for the tools. No real Claude Code ran.
Each rule has a planted fault.
"""
import datetime
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests.agents.support import RULES, AgentCase
from umwayi import agents, enforce

GOOD = agents.claude_settings("python3", Path("/h/hook.py"), Path("/r"), sandbox=True)


class ProblemTests(unittest.TestCase):
    def problem(self, text=GOOD, platform="darwin", tools=("bwrap", "socat")):
        with mock.patch.object(agents, "_platform", lambda: platform), \
                mock.patch.object(agents, "_which", lambda n: "/usr/bin/" + n if n in tools else None):
            return agents.sandbox_problem(text)

    def test_the_fixed_block_on_macos_and_on_linux_with_both_tools_is_none(self):
        self.assertIsNone(self.problem())
        self.assertIsNone(self.problem(platform="linux"))

    def test_the_block_is_the_three_fixed_keys(self):
        self.assertEqual(json.loads(GOOD)["sandbox"], {"enabled": True, "failIfUnavailable": True, "allowUnsandboxedCommands": False})

    def test_a_missing_or_changed_block_is_profile(self):
        good = json.loads(GOOD)
        cases = {"none": agents.claude_settings("python3", Path("/h"), Path("/r")), "not json": "{", "list": "[]",
                 "disabled": json.dumps(dict(good, sandbox=dict(good["sandbox"], enabled=False))),
                 "no fail": json.dumps(dict(good, sandbox={"enabled": True, "allowUnsandboxedCommands": False})),
                 "unsandboxed allowed": json.dumps(dict(good, sandbox=dict(good["sandbox"], allowUnsandboxedCommands=True))),
                 "extra key": json.dumps(dict(good, sandbox=dict(good["sandbox"], excludedCommands=["git"])))}
        for name, text in cases.items():
            with self.subTest(case=name):
                self.assertEqual(self.problem(text)[0], "profile")

    def test_a_platform_that_cannot_host_it_is_platform(self):
        self.assertEqual(self.problem(platform="win32")[0], "platform")

    def test_a_missing_tool_on_linux_is_dependency_and_names_it(self):
        for tools, name in (((), "bwrap and socat"), (("socat",), "bwrap"), (("bwrap",), "socat")):
            with self.subTest(tools=tools):
                r, text = self.problem(platform="linux", tools=tools)
                self.assertEqual(r, "dependency")
                self.assertIn(name + " not found", text)
                self.assertIn("umwayi installs nothing", text)

    def test_every_reason_is_in_the_fixed_list(self):
        for kw in ({"text": "{"}, {"platform": "win32"}, {"platform": "linux", "tools": ()}):
            self.assertIn(self.problem(**kw)[0], enforce.REASONS)

    def test_planted_fault_a_fallback_would_pass_a_missing_block(self):
        """A check that did not look at the block would return None for these. The tests above fail it."""
        self.assertIsNotNone(self.problem("{"))
        self.assertIsNotNone(self.problem(agents.claude_settings("python3", Path("/h"), Path("/r"))))


class SettingsTests(unittest.TestCase):
    def test_the_default_has_no_sandbox_key_so_today_is_unchanged(self):
        self.assertNotIn("sandbox", json.loads(agents.claude_settings("python3", Path("/h"), Path("/r"))))

    def test_the_hook_entry_is_the_same_with_and_without(self):
        a = json.loads(agents.claude_settings("python3", Path("/h/hook.py"), Path("/r")))
        b = json.loads(GOOD)
        b.pop("sandbox")
        self.assertEqual(a, b)


class GateCase(AgentCase):
    def setUp(self):
        super().setUp()
        self.fake("claude")
        self.write_rules(RULES.replace("agent: [reviewer, slow, stubborn, quick]", "agent: [reviewer]"))
        self.write_agents("agents:\n  - name: reviewer\n    platform: claude-code\n    command: claude\n    workdir: {work}\n    env_keep: [FAKE_LOG, FAKE_SCRIPT, FAKE_PLANT, FAKE_KIRO_STATE, FAKE_CLAUDE_AUTH, FAKE_CLAUDE_AUTH_EXIT]\n")
        self.roomy_budget()
        self.fake_sandbox_tools()

    def mode_file(self, text):
        (self.root / ".umwayi").mkdir(exist_ok=True)
        (self.root / ".umwayi" / "enforcement.yaml").write_text(text, encoding="utf-8")

    def check(self, platform="linux", tools=("bwrap", "socat")):
        import os
        env = {"PATH": os.pathsep.join([str(self.bin), os.environ.get("PATH", "")]), "HOME": str(self.home),
               "FAKE_LOG": str(self.fake_log)}
        with mock.patch.dict(os.environ, env), mock.patch.object(agents, "_platform", lambda: platform), \
                mock.patch.object(agents, "_which", lambda n: "/usr/bin/" + n if n in tools else None):
            return agents.check_agent(self.root, "reviewer", home=self.home)


class GateTests(GateCase):
    def test_an_enforced_agent_with_the_tools_is_gated_and_the_start_line_shows_the_block(self):
        self.mode_file("enforcement: enforced\n")
        r = self.check()
        text = "\n".join(r.lines)
        self.assertEqual(r.code, 0, text)
        self.assertIn("ok: sandbox settings:", text)
        self.assertIn("not tested: whether the sandbox holds", text)
        shown = json.dumps(json.dumps({"sandbox": agents.SANDBOX_SETTINGS}, separators=(",", ":")))[2:-2]  # inside the argv list
        self.assertIn(shown[1:-1], text)

    def test_an_enforced_agent_without_bwrap_is_refused_with_dependency_and_exit_2(self):
        self.mode_file("enforcement: enforced\n")
        r = self.check(tools=("socat",))
        text = "\n".join(r.lines)
        self.assertEqual(r.code, 2, text)
        self.assertIn("no: sandbox settings: refused (dependency): bwrap not found on PATH", text)
        self.assertIn("Not gated", text)
        self.assertNotIn("would start", text)

    def test_an_unsupported_platform_is_refused_with_platform(self):
        self.mode_file("enforcement: enforced\n")
        r = self.check(platform="win32")
        self.assertEqual(r.code, 2)
        self.assertIn("refused (platform)", "\n".join(r.lines))

    def test_a_mode_file_that_cannot_be_read_is_enforced_and_refused_without_the_tools(self):
        self.mode_file("a: [\n")
        self.assertEqual(self.check(tools=()).code, 2)

    def test_no_mode_file_and_cooperative_have_no_sandbox_check_and_keep_today(self):
        until = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
        for text in (None, f"enforcement: enforced\nagents:\n  reviewer:\n    enforcement: cooperative\n    until: {until}\n"):
            if text:
                self.mode_file(text)
            r = self.check(tools=())
            lines = "\n".join(r.lines)
            with self.subTest(mode="none" if text is None else "cooperative"):
                self.assertEqual(r.code, 0, lines)
                self.assertNotIn("sandbox", lines)

    def test_the_acp_adapter_takes_no_sandbox_settings_so_an_enforced_acp_agent_is_refused(self):
        self.write_agents("agents:\n  - name: reviewer\n    platform: claude-code\n    command: claude\n    transport: acp\n    workdir: {work}\n    env_keep: [FAKE_LOG, FAKE_SCRIPT, FAKE_PLANT, FAKE_KIRO_STATE, FAKE_CLAUDE_AUTH, FAKE_CLAUDE_AUTH_EXIT]\n")
        self.mode_file("enforcement: enforced\n")
        r = self.check()
        text = "\n".join(r.lines)
        self.assertEqual(r.code, 2, text)
        self.assertIn("refused (profile): the Claude Code ACP adapter takes no sandbox settings", text)

    def test_planted_fault_a_fallback_to_cooperative_would_start_it(self):
        """The start must not fall back by itself: with the tools missing and the mode enforced the exit is 2, not 0."""
        self.mode_file("enforcement: enforced\n")
        self.assertNotEqual(self.check(tools=()).code, 0)


class RealStartTests(GateCase):
    def setUp(self):
        super().setUp()
        self.write_agents("agents:\n  - name: reviewer\n    platform: claude-code\n    command: claude\n    workdir: {work}\n"
                          "    env_keep: [FAKE_LOG, FAKE_SCRIPT, FAKE_PLANT, FAKE_KIRO_STATE, FAKE_CLAUDE_AUTH, FAKE_CLAUDE_AUTH_EXIT]\n")

    def start(self):
        import subprocess
        extra = dict(self.script({"do": "exit", "code": 0}))
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "run", "reviewer", "--prompt", "hello"],
                           capture_output=True, text=True, timeout=120, env=self.env(extra), cwd=str(self.tmp))
        return r, [c for c in self.calls() if c.get("started")]

    def settings_of(self, call):
        argv = call["argv"]
        return json.loads(argv[argv.index("--settings") + 1])

    def test_an_enforced_start_passes_the_block_and_a_cooperative_or_default_start_does_not(self):
        self.mode_file("enforcement: enforced\n")
        r, started = self.start()
        self.assertTrue(started, r.stdout + r.stderr)
        self.assertEqual(self.settings_of(started[-1])["sandbox"], agents.SANDBOX_SETTINGS)
        until = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
        self.mode_file(f"enforcement: enforced\nagents:\n  reviewer:\n    enforcement: cooperative\n    until: {until}\n")
        r, started2 = self.start()
        self.assertEqual(len(started2), 2, r.stdout + r.stderr)
        self.assertNotIn("sandbox", self.settings_of(started2[-1]))
        (self.root / ".umwayi" / "enforcement.yaml").unlink()
        r, started3 = self.start()
        self.assertNotIn("sandbox", self.settings_of(started3[-1]))


if __name__ == "__main__":
    unittest.main()
