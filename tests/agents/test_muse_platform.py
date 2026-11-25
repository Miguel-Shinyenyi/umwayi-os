"""M2 part 2, step 1 (docs/muse-start-design.md): a Muse agent has a row and checks, and no start.

Every test runs `python -m umwayi ... agent check|run ...` as a real child process, with a fake `muse` first on PATH that answers `--version` and
does nothing else. No real Muse is run, and the fake never starts a model. A run and a chat are refused with a fixed text and nothing is started."""
import re
import sys
import unittest

from umwayi import agents, muse

from tests.agents.support import REPO, AgentCase

AGENT = "agents:\n  - name: m\n    platform: muse\n    command: muse\n    workdir: {work}\n"
FAKE = "#!{py}\nimport sys\nif sys.argv[1:] == ['--version']:\n    print('muse 0.3.1')\n    sys.exit(0)\nsys.exit(97)  # anything else is a start, and no test may start one\n"


class MuseCase(AgentCase):
    def setUp(self):
        super().setUp()
        self.fake_muse()
        self.write_agents(AGENT)

    def fake_muse(self, version_exit=0):
        p = self.bin / "muse"
        text = FAKE.format(py=sys.executable)
        if version_exit:
            text = text.replace("sys.exit(0)", f"sys.exit({version_exit})", 1)
        p.write_text(text, encoding="utf-8")
        p.chmod(0o755)

    def lines_of(self, r):
        return {m.group(2): (m.group(1), m.group(3)) for m in
                (re.match(r"^(ok|no|not run): ([a-z ]+): (.*)$", ln) for ln in r.stdout.splitlines()) if m}

    def write_hook_file(self, command):
        (self.work / ".muse").mkdir(parents=True, exist_ok=True)
        (self.work / ".muse" / "hooks.json").write_text(muse.muse_hooks_text(command), encoding="utf-8")


class TableTests(unittest.TestCase):
    def test_the_row_is_fixed_and_pins_no_version(self):
        p = agents.PLATFORMS["muse"]
        self.assertEqual((p.commands, p.transports, p.min_version), (("muse",), ("cli",), (0, 0, 0)))
        self.assertTrue((REPO / p.hook).is_file())

    def test_a_run_builds_no_command_line_while_the_start_is_not_built(self):
        with self.assertRaises(Exception) as cm:
            agents.build_argv(type("A", (), {"platform": "muse"})(), agents.RUN, "/usr/bin/muse", REPO, sys.executable, prompt="hello")
        self.assertIn("not built yet", str(cm.exception))


class CheckTests(MuseCase):
    def test_the_agents_file_accepts_platform_muse(self):
        r = self.umwayi("validate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_missing_command_ends_the_checks_at_the_first_line(self):
        (self.bin / "muse").unlink()
        r = self.umwayi("check", "m")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        lines = self.lines_of(r)
        self.assertEqual(lines["command"][0], "no")
        self.assertEqual(lines["version"], ("not run", "an earlier check failed"))
        self.assertIn("Nothing was started.", r.stdout)

    def test_a_version_command_that_fails_ends_the_checks(self):
        self.fake_muse(version_exit=3)
        r = self.umwayi("check", "m")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(self.lines_of(r)["version"][0], "no")

    def test_without_a_hook_file_the_check_names_the_file_and_the_command_it_must_call(self):
        r = self.umwayi("check", "m")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        lines = self.lines_of(r)
        self.assertEqual((lines["command"][0], lines["version"][0], lines["hook file"][0]), ("ok", "ok", "no"))
        self.assertIn("hook_file_missing", lines["hook file"][1])
        self.assertIn("the sign-in is not checked", lines["version"][1])
        self.assertEqual(lines["key variables"], ("not run", "an earlier check failed"))

    def test_with_the_hook_file_the_agent_is_gated_and_nothing_is_started(self):
        r = self.umwayi("check", "m")
        command = re.search(r"PreToolUse command `([^`]+)`", r.stdout).group(1)
        self.write_hook_file(command)
        r = self.umwayi("check", "m", extra={"META_API_KEY": "SECRET-VALUE-1", "MUSE_TOKEN": "SECRET-VALUE-2"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        lines = self.lines_of(r)
        self.assertEqual([lines[k][0] for k in ("command", "version", "hook file", "key variables")], ["ok"] * 4)
        self.assertIn("META_API_KEY", lines["key variables"][1])
        self.assertIn("MUSE_TOKEN", lines["key variables"][1])
        self.assertNotIn("SECRET-VALUE", r.stdout + r.stderr)  # names only, never a value
        self.assertIn("A Muse run is not built yet", r.stdout)

    def test_a_hook_file_that_calls_something_else_is_refused(self):
        self.write_hook_file("echo not-the-gate")
        r = self.umwayi("check", "m")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(self.lines_of(r)["hook file"][0], "no")


class RunIsRefusedTests(MuseCase):
    def test_a_run_is_not_started_and_the_fake_is_never_run_as_a_start(self):
        r = self.umwayi("run", "m", "--prompt", "hello")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)  # refused: by the rules, the hook file or the fixed text, never started
        self.assertNotIn("exited with code 97", r.stdout + r.stderr)  # the fake exits 97 for anything but --version
        self.assertNotIn("finished (exit", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
