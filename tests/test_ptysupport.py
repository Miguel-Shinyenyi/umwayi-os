"""W78d: the umask of `tests/ptysupport.py` reaches the child on the terminal path as well as on the pipe path.

`run()` always took a `umask` keyword, but `run_at_terminal()` had no such parameter, so a test that gave the child a
real terminal (a command that runs `queue answer`) silently ignored it. A short `python3 -c` child writes a file; its
mode shows the umask the child ran with. Standard library only.
"""
import os
import stat
import sys
import tempfile
import unittest

from tests import ptysupport

CODE = ("import os, sys\n"
        "open(sys.argv[1], 'w').close()\n"
        "print('tty' if os.isatty(1) else 'pipe')\n")


def mode_of(path):
    return stat.S_IMODE(os.stat(path).st_mode)


class UmaskTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="umwayi-pty-")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))
        self.target = os.path.join(self.dir, "made")
        old = os.umask(0)
        os.umask(old)
        self.parent_mode = 0o666 & ~old  # what a new file gets when the child keeps the umask of this process

    def child(self, *extra):
        return [sys.executable, "-c", CODE, self.target, *extra]

    def test_run_at_terminal_passes_the_umask_to_the_child(self):
        r = ptysupport.run_at_terminal(self.child(), umask=0o077)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("tty", r.stdout)  # the child really had a terminal
        self.assertEqual(mode_of(self.target), 0o600)

    def test_run_on_the_terminal_path_passes_the_umask_too(self):
        r = ptysupport.run(self.child("queue", "answer"), umask=0o077)  # these two words put the child on a terminal
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("tty", r.stdout)
        self.assertEqual(mode_of(self.target), 0o600)

    def test_run_on_the_pipe_path_still_passes_the_umask(self):
        r = ptysupport.run(self.child(), umask=0o077)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("pipe", r.stdout)
        self.assertEqual(mode_of(self.target), 0o600)

    def test_without_a_umask_both_paths_keep_the_umask_of_the_test(self):
        ptysupport.run_at_terminal(self.child())
        self.assertEqual(mode_of(self.target), self.parent_mode)
        os.remove(self.target)
        ptysupport.run(self.child("queue", "answer"))
        self.assertEqual(mode_of(self.target), self.parent_mode)

    def test_a_different_umask_gives_a_different_mode_on_the_terminal_path(self):
        ptysupport.run_at_terminal(self.child(), umask=0o000)
        self.assertEqual(mode_of(self.target), 0o666)


if __name__ == "__main__":
    unittest.main()
