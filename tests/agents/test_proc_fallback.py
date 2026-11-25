"""W36: the agent tests wait for the processes of a root to finish by listing every process. Where there is no /proc (macOS) they use `ps`.
This pins the `ps` path on any machine, by hiding /proc from the helper, so a Mac does not error with FileNotFoundError: /proc."""
import os
import shutil
import unittest
from unittest import mock

from tests.agents import support


class CommandLinesTests(unittest.TestCase):
    def test_the_ps_path_lists_this_process_when_there_is_no_proc(self):
        if shutil.which("ps") is None:
            self.skipTest("ps is not on the PATH: the ps path is not shown here (a skip, not a pass)")
        real = os.path.isdir
        with mock.patch.object(support.os.path, "isdir", lambda p: False if p == "/proc" else real(p)):
            found = {pid: cmd for pid, cmd in support.command_lines()}
        self.assertIn(os.getpid(), found)
        self.assertTrue(all(isinstance(c, bytes) for c in found.values()))

    @unittest.skipUnless(os.path.isdir("/proc"), "no /proc on this machine: the /proc path is not shown here")
    def test_the_proc_path_lists_this_process_too(self):
        self.assertIn(os.getpid(), {pid for pid, _ in support.command_lines()})


if __name__ == "__main__":
    unittest.main()
