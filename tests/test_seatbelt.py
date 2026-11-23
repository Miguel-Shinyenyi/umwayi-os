"""W78 step 7 (Task 9): the Seatbelt profile and argument list for macOS (umwayi/seatbelt.py), built behind a refusal.

Pure tests run everywhere: the profile text, the quoting of paths (a path that could close the string is refused), the fixed program,
and `start_allowed`, which refuses with `platform` while `CHECKED_ON_MAC` is False. The real-command tests run only on a Mac with
`sandbox-exec`; CI has no macOS, so they are skipped there and the owner's check on the Mac is the first run on their machine.
Nothing starts a helper through Seatbelt.
"""
import os
import sys
import unittest
from unittest import mock

from umwayi import seatbelt as sb

MAC = sys.platform == "darwin" and sb.available()


class ProfileTests(unittest.TestCase):
    def test_the_profile_denies_by_default_and_lists_what_is_allowed(self):
        p = sb.profile(["/usr", "/System"], ["/work/wt"], no_network=False)
        self.assertTrue(p.startswith("(version 1)\n(deny default)\n"))
        self.assertIn('(allow file-read* (subpath "/System") (subpath "/usr") (subpath "/work/wt"))', p)
        self.assertIn('(allow file-write* (subpath "/work/wt"))', p)
        self.assertIn('(allow process-exec (subpath "/System") (subpath "/usr") (subpath "/work/wt"))', p)
        self.assertIn("(allow network*)", p)
        self.assertNotIn("(deny network*)", p)

    def test_no_network_denies_it(self):
        p = sb.profile(["/usr"], ["/w"], no_network=True)
        self.assertIn("(deny network*)", p)
        self.assertNotIn("(allow network*)", p)

    def test_the_folders_above_a_listed_path_are_listed_as_names_only(self):
        p = sb.profile(["/a/b/c"], [])
        for a in ("/", "/a", "/a/b"):
            self.assertIn(f'(allow file-read* (literal "{a}"))', p)
        self.assertNotIn('(literal "/a/b/c")', p)

    def test_no_write_paths_means_no_write_rule(self):
        self.assertNotIn("file-write*", sb.profile(["/usr"], []))

    def test_a_path_that_could_close_the_string_or_is_not_absolute_is_refused(self):
        for bad in ('/a"b', "/a\\b", "/a\nb", "/a\x00b", "relative", "", None, "/a\x07b"):
            with self.subTest(bad=bad), self.assertRaises(sb.SeatbeltRefused) as cm:
                sb.profile([bad], [])
            self.assertEqual(cm.exception.reason, "profile")

    def test_the_text_is_the_same_for_the_same_paths_in_any_order(self):
        self.assertEqual(sb.profile(["/b", "/a"], ["/w2", "/w1"]), sb.profile(["/a", "/b"], ["/w1", "/w2"]))

    def test_planted_fault_a_path_with_a_quote_would_otherwise_widen_the_profile(self):
        with self.assertRaises(sb.SeatbeltRefused):
            sb.profile(['/x") (allow file-write* (subpath "/'], [])


class ArgvTests(unittest.TestCase):
    def test_the_program_is_fixed_and_the_command_comes_after_the_profile(self):
        argv = sb.argv(["/usr"], ["/w"], ["/bin/echo", "hi"])
        self.assertEqual((argv[0], argv[1]), ("/usr/bin/sandbox-exec", "-p"))
        self.assertEqual(argv[3:], ["/bin/echo", "hi"])
        self.assertEqual(argv[2], sb.profile(["/usr"], ["/w"]))

    def test_a_command_that_is_not_an_absolute_path_is_refused(self):
        for cmd in ([], ["echo"], ["rel/echo"]):
            with self.assertRaises(sb.SeatbeltRefused):
                sb.argv(["/usr"], [], cmd)

    def test_the_module_starts_no_shell(self):
        src = open(sb.__file__, encoding="utf-8").read()
        for bad in ("shell=True", "os.system", "os.popen"):
            self.assertNotIn(bad, src)


class RefusalTests(unittest.TestCase):
    def test_it_is_not_checked_on_a_mac_so_a_start_is_refused(self):
        self.assertFalse(sb.CHECKED_ON_MAC)
        with mock.patch.object(sb, "available", lambda: True), mock.patch.object(sys, "platform", "darwin"):
            self.assertEqual(sb.start_allowed(), (False, "platform"))

    def test_off_a_mac_the_reason_is_platform_and_without_the_program_unavailable(self):
        with mock.patch.object(sys, "platform", "linux"):
            self.assertEqual(sb.start_allowed(), (False, "platform"))
        with mock.patch.object(sys, "platform", "darwin"), mock.patch.object(sb, "available", lambda: False):
            self.assertEqual(sb.start_allowed(), (False, "unavailable"))

    def test_only_a_set_flag_would_allow_it(self):
        with mock.patch.object(sb, "available", lambda: True), mock.patch.object(sys, "platform", "darwin"), \
                mock.patch.object(sb, "CHECKED_ON_MAC", True):
            self.assertEqual(sb.start_allowed(), (True, ""))

    def test_nothing_in_agents_uses_seatbelt_yet(self):
        agents_src = open(os.path.join(os.path.dirname(sb.__file__), "agents.py"), encoding="utf-8").read()
        self.assertNotIn("seatbelt", agents_src)


class RunRefusalTests(unittest.TestCase):
    """F3a: `run` refuses while CHECKED_ON_MAC is False, unless the owner types the switch, and the refusal names the switch."""

    ARGS = ["run", "--read", "/usr", "--write", "/tmp/x", "--", "/usr/bin/true"]

    def run_main(self, args, available=True):
        import io
        err = io.StringIO()
        with mock.patch.object(sb, "available", lambda: available), mock.patch.object(sys, "stderr", err), \
                mock.patch.object(os, "posix_spawn", return_value=123) as spawn, mock.patch.object(os, "waitpid", return_value=(123, 0)):
            code = sb.main(args)
        return code, err.getvalue(), spawn

    def test_without_the_switch_it_is_refused_with_platform_and_names_the_switch_and_starts_nothing(self):
        code, err, spawn = self.run_main(self.ARGS)
        self.assertEqual(code, 2)
        self.assertIn("refused: not confined (platform). Allowed next:", err)
        self.assertIn("--i-am-testing", err)
        spawn.assert_not_called()

    def test_with_the_switch_on_a_mac_with_sandbox_exec_it_runs(self):
        code, err, spawn = self.run_main(["run", "--read", "/usr", "--i-am-testing", "--", "/usr/bin/true"])
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(spawn.call_args.args[0], sb.SANDBOX_EXEC)

    def test_the_switch_does_not_help_where_sandbox_exec_is_missing(self):
        code, err, spawn = self.run_main(["run", "--read", "/usr", "--i-am-testing", "--", "/usr/bin/true"], available=False)
        self.assertEqual(code, 2)
        spawn.assert_not_called()

    def test_a_flag_that_is_not_the_switch_is_a_usage_error(self):
        code, err, spawn = self.run_main(["run", "--read", "/usr", "--i-am-sure", "--", "/usr/bin/true"])
        self.assertEqual(code, 64)
        spawn.assert_not_called()

    def test_the_selftest_still_works_without_the_switch(self):
        import io
        out = io.StringIO()
        with mock.patch.object(sb, "selftest", return_value={"available": True}), mock.patch.object(sb, "available", lambda: True), \
                mock.patch.object(sys, "stdout", out):
            self.assertEqual(sb.main(["selftest"]), 0)
        self.assertIn('"available": true', out.getvalue())


@unittest.skipUnless(MAC, "needs macOS with sandbox-exec: the owner's check")
class RealMacTests(unittest.TestCase):
    def test_the_selftest_shows_the_kernel_refusals_on_this_mac(self):
        r = sb.selftest()
        import json
        for label, no_net in (("with_network", False), ("no_network", True)):
            got = json.loads(r[label]["out"][0])
            self.assertEqual((got["write_inside"], got["write_outside"], got["read_unlisted"]), ("ok", "refused", "refused"), r)
        self.assertEqual(json.loads(r["no_network"]["out"][0])["network"], "refused")
        self.assertNotEqual(json.loads(r["with_network"]["out"][0])["network"], "refused")


if __name__ == "__main__":
    unittest.main()
