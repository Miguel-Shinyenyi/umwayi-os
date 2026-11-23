"""G2a: the rehearsal of signing and verifying with a throwaway key (tools/provenance_rehearsal.py).

It makes a scratch root, a throwaway key and an agent of its own, so that the owner sees the prompts before the real signing. These tests
run the real `ssh-keygen` and `ssh-agent`; they are skipped with a reason when the tools are missing. They check that the rehearsal
works from its own printed pieces, that the owner's key and agent are not touched, and that cleanup ends the agent and removes the folder
and only a folder the tool made.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools import provenance_rehearsal as rh
from umwayi import provsign

try:
    TOOLS = provsign.find_ssh_keygen() and shutil.which("ssh-agent") and shutil.which("ssh-add")
except provsign.SignError:
    TOOLS = None


@unittest.skipUnless(TOOLS, "ssh-keygen, ssh-agent and ssh-add are needed")
class RehearsalTests(unittest.TestCase):
    def setUp(self):
        self.old = os.environ.get("SSH_AUTH_SOCK")
        self.addCleanup(self.restore)
        self.got = rh.prepare()
        self.addCleanup(rh.cleanup, self.got["folder"])

    def restore(self):
        if self.old is None:
            os.environ.pop("SSH_AUTH_SOCK", None)
        else:
            os.environ["SSH_AUTH_SOCK"] = self.old

    def test_the_pieces_sign_and_verify_and_a_change_is_exit_3(self):
        os.environ["SSH_AUTH_SOCK"] = self.got["sock"]
        got = provsign.sign_task(self.got["root"], "G-0001", "T-01", "2026-01-01", self.got["public_key"], lambda lines: True)
        self.assertTrue(got["key"].startswith("SHA256:"))
        self.assertEqual(provsign.verify_path(self.got["root"], "umwayi/hello.py", self.got["public_key"])[0], 0)
        (Path(self.got["root"]) / "umwayi" / "hello.py").write_text("print('changed')\n", encoding="utf-8")
        self.assertEqual(provsign.verify_path(self.got["root"], "umwayi/hello.py", self.got["public_key"])[0], 3)

    def test_the_commands_carry_the_throwaway_agent_and_never_the_owners_paths(self):
        text = "\n".join(self.got["commands"])
        self.assertIn(f"SSH_AUTH_SOCK={self.got['sock']}", text)
        self.assertNotIn(".ssh", text)
        self.assertNotIn("id_ed25519", text)
        self.assertTrue(self.got["public_key"].startswith(self.got["folder"]))  # the key is inside the scratch folder

    def test_the_owners_agent_variable_is_not_changed_by_preparing(self):
        self.assertEqual(os.environ.get("SSH_AUTH_SOCK"), self.old)


class CleanupTests(unittest.TestCase):
    def test_cleanup_refuses_a_folder_this_tool_did_not_make(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "keep.txt").write_text("mine", encoding="utf-8")
            with self.assertRaises(ValueError):
                rh.cleanup(d)
            self.assertTrue((Path(d) / "keep.txt").exists())

    @unittest.skipUnless(TOOLS, "ssh-keygen, ssh-agent and ssh-add are needed")
    def test_cleanup_ends_the_agent_and_removes_the_folder(self):
        got = rh.prepare()
        pgrep = lambda: subprocess.run(["pgrep", "-f", f"ssh-agent -a {got['sock']}"], capture_output=True, text=True).stdout.split()
        self.assertTrue(pgrep())
        rh.cleanup(got["folder"])
        self.assertFalse(Path(got["folder"]).exists())
        self.assertFalse(pgrep())

    def test_the_command_line_refuses_other_words(self):
        self.assertEqual(rh.main(["bogus"]), 64)
        self.assertEqual(rh.main([]), 64)


if __name__ == "__main__":
    unittest.main()
