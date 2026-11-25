"""G-0050: macOS Seatbelt behind a refusal that fails closed. These tests run on Linux (the CI runner) and on a Mac alike and start nothing.

They show three things and not a fourth. They show that while `CHECKED_ON_MAC` is False the start is refused, that the argument list a start
WOULD use is built from the right paths when the switch is patched on, and that the agent start asks `start_allowed` first. They do NOT show
that a real Claude Code runs under the profile on a Mac: CI has no macOS, so that is the owner's check (docs/seatbelt-check.md), and nothing
here claims it.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from umwayi import agents, confine, seatbelt


class RefusedWhileNotCheckedTests(unittest.TestCase):
    def test_the_switch_is_still_off(self):
        self.assertFalse(seatbelt.CHECKED_ON_MAC)  # a pull request that flips it must change this test on purpose, after the owner's check

    def test_start_is_not_allowed_and_confined_argv_refuses_with_a_fixed_reason(self):
        ok, why = seatbelt.start_allowed()
        self.assertFalse(ok)
        with self.assertRaises(confine.ConfineRefused) as cm:
            seatbelt.confined_argv(["/usr/bin/true"], "/tmp", "/tmp/root", "/tmp/t", None, sys.executable, "/tmp")
        self.assertEqual(cm.exception.reason, why)
        self.assertIn(why, ("platform", "unavailable"))

    def test_run_paths_still_refuses_off_linux_unless_a_caller_brings_its_own_system_folders(self):
        with mock.patch.object(confine, "platform_is_not_linux", lambda: True), self.assertRaises(confine.ConfineRefused) as cm:
            confine.run_paths("/usr/bin/true", "/tmp", "/tmp/root", "/tmp/t", None, sys.executable, "/tmp")
        self.assertEqual(cm.exception.reason, "platform")


class BuiltFromTheRightPathsTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="usb")))
        self.addCleanup(__import__("shutil").rmtree, self.base, True)
        for d in ("root", "work", "tmp", "home"):
            (self.base / d).mkdir()

    def build(self, workdir=None, **kw):
        with mock.patch.object(seatbelt, "start_allowed", lambda: (True, "")):
            return seatbelt.confined_argv(["/usr/bin/true", "--version"], workdir or str(self.base / "work"), str(self.base / "root"),
                                          str(self.base / "tmp"), str(self.base / "home"), sys.executable, str(self.base), **kw)

    def test_the_list_is_sandbox_exec_a_profile_and_the_command_with_no_shell(self):
        a = self.build()
        self.assertEqual(a[:2], [seatbelt.SANDBOX_EXEC, "-p"])
        self.assertEqual(a[3:], ["/usr/bin/true", "--version"])
        self.assertNotIn("sh", [os.path.basename(x) for x in a[:2]])

    def test_the_work_folder_and_the_private_temp_folder_are_writable_and_the_root_is_not_listed(self):
        profile = self.build()[2]
        write_line = [l for l in profile.splitlines() if l.startswith("(allow file-write*")][0]
        self.assertIn(f'(subpath "{self.base / "work"}")', write_line)
        self.assertIn(f'(subpath "{self.base / "tmp"}")', write_line)
        self.assertNotIn(str(self.base / "root"), profile.replace(f'(literal "{self.base}")', ""))  # at most a folder above it, by name

    def test_a_work_folder_that_holds_the_root_is_refused_with_profile(self):
        with self.assertRaises(confine.ConfineRefused) as cm:
            self.build(workdir=str(self.base))
        self.assertEqual(cm.exception.reason, "profile")

    def test_a_path_that_could_close_the_profile_string_is_refused_with_profile(self):
        bad = self.base / 'wo"rk'
        bad.mkdir()
        with self.assertRaises(confine.ConfineRefused) as cm:
            self.build(workdir=str(bad))
        self.assertEqual(cm.exception.reason, "profile")

    def test_there_is_no_network_rule_so_the_network_is_open_as_in_limit_344(self):
        profile = self.build()[2]
        self.assertIn("(allow network*)", profile)
        self.assertNotIn("(deny network*)", profile)


class AgentStartTests(unittest.TestCase):
    def test_the_agent_start_asks_start_allowed_before_any_seatbelt_argument_list(self):
        text = Path(agents.__file__).read_text(encoding="utf-8")
        src = text.split("def _confine_argv", 1)[1].split("def _confine_end", 1)[0]
        self.assertLess(src.index("seatbelt.start_allowed()"), src.index("seatbelt.confined_argv("))
        self.assertIn("if ok:", src)  # a refusal falls through to the old path, which refuses off Linux


if __name__ == "__main__":
    unittest.main()
