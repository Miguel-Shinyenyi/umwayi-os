"""W78 step 6 (5b): Landlock confinement (umwayi/confine.py).

Pure tests run everywhere: the access masks by ABI, the struct bytes, the plan (reasons), the argument parser, the refusal when the
kernel has no Landlock (the command is never run). Kernel tests run a real child through `python -m umwayi.confine` and need Landlock;
without it they are skipped with a fixed reason, and the first line on standard error says which: `confine tests: landlock ABI N`
or `confine tests: landlock not available (reason): the kernel tests are skipped`. A skipped test shows nothing: only the CI log line
tells whether they ran. They were not run on the author's machines (macOS; Docker Desktop's kernel has no Landlock): CI is the first run.

The kernel tests check the kernel's own refusal: the child reports the errno of its own failed call, and a planted fault runs the same
child unconfined, where the call succeeds.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from umwayi import confine

REPO = Path(__file__).resolve().parent.parent
ABI = confine.abi_version()
SKIP = "landlock is not available on this kernel: the kernel tests are skipped"


def setUpModule():
    sys.stderr.write("confine tests: " + (f"landlock ABI {ABI}" if ABI else f"landlock not available ({SKIP.split(':')[0]})") + "\n")
    sys.stderr.flush()


def need_landlock(fn):
    return unittest.skipUnless(ABI, SKIP)(fn)


class MaskTests(unittest.TestCase):
    def test_the_handled_rights_grow_with_the_abi(self):
        self.assertEqual(confine.handled_fs(1), (1 << 13) - 1)
        self.assertEqual(confine.handled_fs(2) & confine.FS_REFER, confine.FS_REFER)
        self.assertEqual(confine.handled_fs(2) & confine.FS_TRUNCATE, 0)
        self.assertEqual(confine.handled_fs(3) & confine.FS_TRUNCATE, confine.FS_TRUNCATE)
        self.assertEqual(confine.handled_fs(4) & confine.FS_IOCTL_DEV, 0)
        self.assertEqual(confine.handled_fs(5) & confine.FS_IOCTL_DEV, confine.FS_IOCTL_DEV)
        self.assertEqual(confine.handled_fs(8), 0xFFFF)

    def test_the_attr_size_and_bytes_follow_the_abi(self):
        self.assertEqual([confine.attr_size(a) for a in (1, 3, 4, 5, 6, 8)], [8, 8, 16, 16, 24, 24])
        self.assertEqual(len(confine.attr_bytes(1, 7, 0)), 8)
        self.assertEqual(confine.attr_bytes(4, 7, 3), (7).to_bytes(8, "little") + (3).to_bytes(8, "little"))
        self.assertEqual(len(confine.rule_bytes(5, 9)), 12)  # packed: 8 + 4, no padding

    def test_a_write_tree_gets_every_handled_right_and_a_read_tree_only_read_and_execute(self):
        self.assertEqual(confine.write_rights(5), confine.handled_fs(5))
        self.assertEqual(confine.READ_RIGHTS & (confine.FS_WRITE_FILE | confine.FS_MAKE_REG | confine.FS_REMOVE_FILE), 0)


class PlanTests(unittest.TestCase):
    def test_no_landlock_is_unavailable_and_no_network_on_an_old_abi_is_kernel(self):
        for abi in (None, 0):
            with self.assertRaises(confine.ConfineRefused) as cm:
                confine.plan(abi, False)
            self.assertEqual(cm.exception.reason, "unavailable")
        for abi in (1, 2, 3):
            with self.assertRaises(confine.ConfineRefused) as cm:
                confine.plan(abi, True)
            self.assertEqual(cm.exception.reason, "kernel")
            self.assertEqual(confine.plan(abi, False)[1], 0)
        self.assertEqual(confine.plan(4, True)[1], confine.NET_BIND_TCP | confine.NET_CONNECT_TCP)

    def test_every_reason_is_in_the_fixed_list_and_has_a_step(self):
        from umwayi import enforce
        for r in confine.REASONS:
            self.assertIn(r, enforce.REASONS)
            self.assertTrue(confine.refusal(r).startswith(f"refused: not confined ({r}). Allowed next: "))


class ParseTests(unittest.TestCase):
    def test_the_fixed_shape(self):
        argv = confine.argv(["/usr"], ["/w"], ["/bin/true", "a"], no_network=True)
        self.assertEqual(argv[1:3], ["-m", "umwayi.confine"])
        self.assertEqual(confine.parse(argv[3:]), (["/usr"], ["/w"], True, ["/bin/true", "a"]))

    def test_anything_else_is_refused(self):
        for bad in ([], ["--"], ["--read", "/usr"], ["--read", "rel", "--", "/bin/true"], ["--x", "--", "/bin/true"],
                    ["--read", "/usr", "--", "true"], ["--write", "--", "/bin/true"]):
            with self.subTest(bad=bad):
                self.assertIsNone(confine.parse(bad))
                self.assertEqual(confine.main(bad), confine.EXIT_USAGE)


class NoLandlockTests(unittest.TestCase):
    def test_without_landlock_the_command_is_never_run(self):
        with mock.patch.object(confine, "abi_version", lambda: None), mock.patch.object(os, "posix_spawn") as execv, \
                mock.patch.object(sys, "stderr") as err:
            code = confine.main(["--read", "/usr", "--", sys.executable])
        self.assertEqual(code, confine.EXIT_REFUSED)
        execv.assert_not_called()
        written = "".join(c.args[0] for c in err.write.call_args_list)
        self.assertIn("refused: not confined (unavailable). Allowed next:", written)

    def test_a_command_that_is_not_an_executable_file_is_a_profile_refusal(self):
        with mock.patch.object(os, "posix_spawn") as execv:
            self.assertEqual(confine.main(["--read", "/usr", "--", "/nonexistent/prog"]), confine.EXIT_REFUSED)
        execv.assert_not_called()

    def test_umwayi_never_falls_back_to_running_unconfined(self):
        src = (REPO / "umwayi" / "confine.py").read_text(encoding="utf-8")
        self.assertEqual(src.count("os.posix_spawn("), 1)
        self.assertNotIn("subprocess", src)
        self.assertLess(src.index("apply(read, write, no_net)"), src.index("os.posix_spawn(command[0]"))


CHILD = r"""
import errno, json, os, socket, sys
out = {}
def attempt(name, fn):
    try:
        fn(); out[name] = 0
    except OSError as e:
        out[name] = e.errno
w, other, listener = sys.argv[1], sys.argv[2], int(sys.argv[3])
def write(path):
    with open(path, "w") as f: f.write("x")
attempt("write_inside", lambda: write(os.path.join(w, "a.txt")))
attempt("mkdir_inside", lambda: os.mkdir(os.path.join(w, "d")))
attempt("remove_inside", lambda: os.remove(os.path.join(w, "a.txt")))
attempt("write_outside", lambda: write(os.path.join(other, "b.txt")))
attempt("read_unlisted", lambda: open(os.path.join(other, "secret.txt")).read())
import subprocess
attempt("exec_unlisted", lambda: subprocess.run([os.path.join(other, "prog")], timeout=5))
def connect():
    s = socket.socket(); s.settimeout(3); s.connect(("127.0.0.1", listener)); s.close()
attempt("tcp_connect", connect)
print(json.dumps(out))
"""


class KernelCase(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="ucf"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.work = self.base / "work"
        self.other = self.base / "other"
        self.work.mkdir()
        self.other.mkdir()
        (self.other / "secret.txt").write_text("s", encoding="utf-8")
        shutil.copy("/bin/true" if os.path.exists("/bin/true") else "/usr/bin/true", self.other / "prog")
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(8)
        self.addCleanup(self.srv.close)
        self.port = self.srv.getsockname()[1]

    def reads(self):
        real = os.path.realpath(sys.executable)
        cand = {sys.prefix, sys.base_prefix, sys.exec_prefix, os.path.dirname(real), os.path.dirname(os.path.dirname(real)),
                "/usr", "/lib", "/lib64", "/etc", "/proc", "/dev", "/bin", "/sbin", "/opt"}
        out = []
        for p in sorted(cand):
            if os.path.isdir(p) and not any(str(self.base).startswith(p.rstrip("/") + "/") for p in [p]):
                out.append(p)
        return out

    def run_child(self, confined=True, no_network=False, read=None, write=None, extra_cmd=None):
        cmd = [sys.executable, "-c", CHILD, str(self.work), str(self.other), str(self.port)]
        argv = confine.argv(self.reads() if read is None else read, [str(self.work)] if write is None else write, cmd,
                            no_network=no_network) if confined else cmd
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(REPO)}
        return subprocess.run(argv, capture_output=True, text=True, timeout=60, env=env, cwd=str(self.work))

    def result(self, **kw):
        p = self.run_child(**kw)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return json.loads(p.stdout.strip().splitlines()[-1])


EACCES = 13


@unittest.skipUnless(ABI, SKIP)
class KernelTests(KernelCase):
    def test_writes_inside_the_work_folder_work_and_every_other_path_is_refused_by_the_kernel(self):
        r = self.result()
        self.assertEqual((r["write_inside"], r["mkdir_inside"], r["remove_inside"]), (0, 0, 0))
        self.assertEqual(r["write_outside"], EACCES)
        self.assertEqual(r["read_unlisted"], EACCES)
        self.assertFalse((self.other / "b.txt").exists())

    def test_an_unlisted_program_cannot_be_executed(self):
        self.assertEqual(self.result()["exec_unlisted"], EACCES)
        self.assertEqual(self.result(confined=False)["exec_unlisted"], 0)

    def test_planted_fault_the_same_child_unconfined_is_not_refused(self):
        r = self.result(confined=False)
        self.assertEqual((r["write_outside"], r["read_unlisted"]), (0, 0))  # so the refusals above are the kernel's, not ours
        self.assertTrue((self.other / "b.txt").exists())

    def test_the_exit_code_of_the_command_is_the_exit_code_of_the_program(self):
        for code in (0, 3):
            argv = confine.argv(self.reads(), [str(self.work)], [sys.executable, "-c", f"import sys; sys.exit({code})"])
            p = subprocess.run(argv, capture_output=True, text=True, timeout=60, env={"PATH": os.environ.get("PATH", "")})
            self.assertEqual(p.returncode, code, p.stdout + p.stderr)

    def test_the_network_is_open_without_the_option(self):
        self.assertEqual(self.result()["tcp_connect"], 0)

    def test_the_restriction_is_inherited_by_what_the_command_starts(self):
        script = ("import subprocess, sys, json;"
                  f"p = subprocess.run([sys.executable, '-c', 'open({str(self.other / 'child.txt')!r}, \"w\")'], capture_output=True);"
                  "print(json.dumps({'code': p.returncode, 'err': p.stderr.decode()[-80:]}))")
        argv = confine.argv(self.reads(), [str(self.work)], [sys.executable, "-c", script])
        p = subprocess.run(argv, capture_output=True, text=True, timeout=60, env={"PATH": os.environ.get("PATH", "")}, cwd=str(self.work))
        got = json.loads(p.stdout.strip().splitlines()[-1])
        self.assertNotEqual(got["code"], 0, p.stdout + p.stderr)
        self.assertIn("PermissionError", got["err"])
        self.assertFalse((self.other / "child.txt").exists())

    def test_a_listed_path_that_does_not_exist_refuses_and_the_command_is_not_run(self):
        marker = self.base / "marker"
        argv = confine.argv(["/usr", str(self.base / "nope")], [str(self.work)],
                            [sys.executable, "-c", f"open({str(marker)!r}, 'w')"])
        p = subprocess.run(argv, capture_output=True, text=True, timeout=60, env={"PATH": os.environ.get("PATH", "")})
        self.assertEqual(p.returncode, confine.EXIT_REFUSED, p.stdout + p.stderr)
        self.assertIn("refused: not confined (profile). Allowed next:", p.stderr)
        self.assertFalse(marker.exists())

    def test_a_file_can_be_listed_instead_of_a_folder(self):
        f = self.other / "secret.txt"
        script = f"print(open({str(f)!r}).read())"
        argv = confine.argv(self.reads() + [str(f)], [str(self.work)], [sys.executable, "-c", script])
        p = subprocess.run(argv, capture_output=True, text=True, timeout=60, env={"PATH": os.environ.get("PATH", "")})
        self.assertEqual((p.returncode, p.stdout.strip()), (0, "s"), p.stdout + p.stderr)


@unittest.skipUnless(ABI and ABI >= confine.NET_ABI, "landlock network rules need ABI 4 (kernel 6.7): the network tests are skipped")
class NetworkTests(KernelCase):
    def test_no_network_refuses_tcp_connect_with_the_kernels_error(self):
        self.assertEqual(self.result(no_network=True)["tcp_connect"], EACCES)

    def test_planted_fault_the_same_connect_without_the_option_works(self):
        self.assertEqual(self.result(no_network=False)["tcp_connect"], 0)


@unittest.skipUnless(ABI and ABI < confine.NET_ABI, "this kernel has the network ABI: the old-kernel refusal is tested by plan() only")
class OldKernelTests(KernelCase):
    def test_no_network_on_an_old_kernel_is_refused_with_kernel_and_the_command_is_not_run(self):
        p = self.run_child(no_network=True)
        self.assertEqual(p.returncode, confine.EXIT_REFUSED)
        self.assertIn("(kernel)", p.stderr)


if __name__ == "__main__":
    unittest.main()
