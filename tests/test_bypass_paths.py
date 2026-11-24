"""J1: the planted-bypass test. What stops an agent that uses a path that never calls the gate?

The six paths of docs/bypass-resistance-design.md, tried from inside a confined run. The pass condition of a path is a refusal by the
confinement (the kernel, errno EACCES), never by the gate: no test here calls the rules gate or a hook. Each kernel check has a planted
fault: the same child run UNconfined must succeed, so the refusal is the kernel's and not the test's.

A path that is NOT blocked is a finding, not a failure to hide (KNOWN-LIMITS 344): a TCP connect is not blocked by the run path as it is
built, so path 1 asserts that finding. A call to a host on port 443 is not blocked by anything here, and `--no-tcp` cannot be used as it is
for a helper that must reach its model. When someone wires a block, test_path_1_* fails and the limit, the table and every claim must be
updated in the same change.

The kernel parts run only where Landlock exists (the CI runner reports ABI 8); on a Mac or a container without it they are SKIPPED, and a
skip is reported as a skip, never as a pass (lesson A14: tests/test_confine.py fails a CI runner that has no Landlock instead of skipping).
Not tried here, and so not proven: a real `git push` with a stored token, and what a REAL enforced run lists to read; both wait for the first
real enforced run (W40).
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from umwayi import confine

REPO = Path(__file__).resolve().parent.parent
ABI = confine.abi_version()
SKIP = "landlock is not available on this kernel: the kernel parts of the bypass test are skipped, not passed"
EACCES = 13
DESIGN = REPO / "docs" / "bypass-resistance-design.md"


def setUpModule():
    sys.stderr.write("bypass tests: " + (f"landlock ABI {ABI}" if ABI else "landlock not available: the kernel parts are SKIPPED") + "\n")
    sys.stderr.flush()


CHILD = r"""
import json, os, socket, subprocess, sys
work, other, cred, port = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
out = {}
def attempt(name, fn):
    try:
        fn(); out[name] = 0
    except OSError as e:
        out[name] = e.errno
def write(path):
    with open(path, "w") as f: f.write("x")
def shell(cmd):
    p = subprocess.run(["/bin/sh", "-c", cmd], capture_output=True, text=True, timeout=20)
    if p.returncode == 0: return 0
    raise OSError(13 if "Permission denied" in p.stderr else -1, p.stderr[:80])
attempt("write_inside", lambda: write(os.path.join(work, "a.txt")))
attempt("write_outside", lambda: write(os.path.join(other, "b.txt")))
attempt("read_credential", lambda: open(cred).read())
def connect():
    s = socket.socket(); s.settimeout(3); s.connect(("127.0.0.1", port)); s.close()
attempt("tcp_connect", connect)
attempt("shell_write_outside", lambda: shell("echo x > " + os.path.join(other, "c.txt")))
attempt("second_interpreter_write_outside",
        lambda: shell(sys.executable + " -c \"open(" + repr(os.path.join(other, "d.txt")) + ", 'w').write('x')\""))
print(json.dumps(out))
"""


class DesignNoteTests(unittest.TestCase):
    """Run everywhere: the note, the limit and the finding stay tied to this test."""

    def test_the_note_has_six_paths_and_this_file_has_a_test_for_each(self):
        rows = re.findall(r"(?m)^\| ([1-9]) \| ", DESIGN.read_text(encoding="utf-8"))
        self.assertEqual(rows, ["1", "2", "3", "4", "5", "6"])
        names = {n for n in dir(KernelTests) if n.startswith("test_path_")} | {n for n in dir(NotTriedTests) if n.startswith("test_path_")}
        for n in range(1, 7):
            self.assertTrue(any(x.startswith(f"test_path_{n}_") for x in names), f"no test for path {n}")

    def test_finding_the_run_path_builds_the_confined_command_without_no_tcp(self):
        src = (REPO / "umwayi" / "agents.py").read_text(encoding="utf-8")
        self.assertIn("return confine.argv(read, write, argv)", src)
        self.assertNotIn("no_tcp", src)  # when this changes, limit 344, the design note and every claim about the network must change too

    def test_limit_344_and_the_note_say_plainly_that_a_call_to_a_host_on_443_is_not_blocked(self):
        limits = (REPO / "docs" / "KNOWN-LIMITS.md").read_text(encoding="utf-8")
        self.assertIn("344.", limits)
        self.assertIn("any host on 443", limits)
        self.assertIn("a call to a host on port 443 is not blocked", DESIGN.read_text(encoding="utf-8"))

    def test_this_file_imports_nothing_of_umwayi_but_the_confinement_so_no_gate_or_hook_can_be_called(self):
        import ast
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        umwayi = [(n.module, [a.name for a in n.names]) for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("umwayi")]
        self.assertEqual(umwayi, [("umwayi", ["confine"])])
        self.assertEqual([n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import) and n.names[0].name.startswith("umwayi")], [])


@unittest.skipUnless(ABI, SKIP)
class KernelTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="ubp"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.work, self.other, self.home = self.base / "work", self.base / "other", self.base / "home"
        for d in (self.work, self.other, self.home):
            d.mkdir()
        self.cred = self.home / ".git-credentials"
        self.cred.write_text("https://user:planted-token@example.invalid\n", encoding="utf-8")  # a planted credential, not a real one
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(8)
        self.addCleanup(self.srv.close)
        self.port = self.srv.getsockname()[1]

    def reads(self):
        real = os.path.realpath(sys.executable)
        cand = {sys.prefix, sys.base_prefix, sys.exec_prefix, os.path.dirname(real), os.path.dirname(os.path.dirname(real)),
                "/usr", "/lib", "/lib64", "/etc", "/proc", "/dev", "/bin", "/sbin", "/opt"}
        return sorted(p for p in cand if os.path.isdir(p) and not str(self.base).startswith(p.rstrip("/") + "/"))

    def run_child(self, confined=True, no_tcp=False):
        cmd = [sys.executable, "-c", CHILD, str(self.work), str(self.other), str(self.cred), str(self.port)]
        argv = confine.argv(self.reads(), [str(self.work)], cmd, no_tcp=no_tcp) if confined else cmd
        p = subprocess.run(argv, capture_output=True, text=True, timeout=120, env={"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(REPO)},
                           cwd=str(self.work))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return json.loads(p.stdout.strip().splitlines()[-1])

    def test_path_1_a_tcp_connect_is_not_blocked_by_the_run_path_as_built_and_is_blocked_only_with_no_tcp(self):
        built = self.run_child()  # the command exactly as agents.py builds it: no no_tcp
        self.assertEqual(built["tcp_connect"], 0, "FINDING (limit 344): the confined run has the network open")
        if ABI >= confine.NET_ABI:
            self.assertEqual(self.run_child(no_tcp=True)["tcp_connect"], EACCES)  # the option exists and works, and refuses ALL TCP
        self.assertEqual(self.run_child(confined=False)["tcp_connect"], 0)  # planted fault: unconfined is open too, so only the option closes it

    def test_path_2_a_stored_credential_in_the_home_folder_cannot_be_read_and_the_push_is_not_tried(self):
        self.assertEqual(self.run_child()["read_credential"], EACCES)
        self.assertEqual(self.run_child(confined=False)["read_credential"], 0)

    def test_path_3_a_write_outside_the_allowed_folders_is_refused_by_the_kernel(self):
        r = self.run_child()
        self.assertEqual((r["write_inside"], r["write_outside"]), (0, EACCES))
        self.assertFalse((self.other / "b.txt").exists())
        control = self.run_child(confined=False)  # planted fault: without the confinement the same write works
        self.assertEqual(control["write_outside"], 0)
        self.assertTrue((self.other / "b.txt").exists())

    def test_path_4_a_read_of_a_credential_file_outside_the_listed_folders_is_refused(self):
        self.assertEqual(self.run_child()["read_credential"], EACCES)
        self.assertEqual(self.run_child(confined=False)["read_credential"], 0)

    def test_path_5_a_second_process_cannot_drop_the_confinement(self):
        r = self.run_child()
        self.assertEqual(r["second_interpreter_write_outside"], EACCES)  # a fresh interpreter started by the child is refused too
        self.assertFalse((self.other / "d.txt").exists())
        self.assertEqual(self.run_child(confined=False)["second_interpreter_write_outside"], 0)  # planted fault

    def test_path_6_a_shell_command_that_never_goes_through_a_hook_is_refused_by_the_kernel(self):
        r = self.run_child()
        self.assertEqual(r["shell_write_outside"], EACCES)  # no gate and no hook is involved: the refusal is the kernel's
        self.assertFalse((self.other / "c.txt").exists())
        self.assertEqual(self.run_child(confined=False)["shell_write_outside"], 0)  # planted fault


class NotTriedTests(unittest.TestCase):
    """Two things the note lists as not proven are stated here so they cannot be mistaken for proven."""

    def test_path_2_the_push_itself_and_the_logbook_line_that_names_the_layer_are_not_built(self):
        text = DESIGN.read_text(encoding="utf-8")
        self.assertIn("none for a push", text)
        self.assertIn("not built", text)


if __name__ == "__main__":
    unittest.main()
