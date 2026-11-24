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


class CiKernelTests(unittest.TestCase):
    """A14: a result is never claimed from a skipped test. On GitHub Actions the kernel tests must run, not skip."""

    def test_on_the_ci_runner_the_kernel_tests_run_and_do_not_skip(self):
        if os.environ.get("GITHUB_ACTIONS") != "true" or not sys.platform.startswith("linux"):
            self.skipTest("only the Linux runner of GitHub Actions has to run the kernel tests")
        self.assertTrue(ABI, "Landlock is not available on the CI runner, so the kernel tests were skipped: that is not a pass")

    def test_planted_fault_a_ci_runner_without_landlock_fails_the_test_instead_of_skipping(self):
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}), mock.patch.object(sys, "platform", "linux"), \
                mock.patch.dict(globals(), {"ABI": 0}):
            with self.assertRaises(AssertionError):
                self.test_on_the_ci_runner_the_kernel_tests_run_and_do_not_skip()


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
    def test_no_landlock_is_unavailable_and_no_tcp_on_an_old_abi_is_kernel(self):
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
        argv = confine.argv(["/usr"], ["/w"], ["/bin/true", "a"], no_tcp=True)
        self.assertEqual(argv[1], str(REPO / "umwayi" / "confine.py"))
        self.assertEqual(confine.parse(argv[2:]), (["/usr"], ["/w"], True, ["/bin/true", "a"]))

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
        self.assertLess(src.index("apply(read, write, no_tcp)"), src.index("os.posix_spawn(command[0]"))


class F1Tests(unittest.TestCase):
    """F1 (a to i): the hardening of the confinement. Each has a planted fault; the ones that need the kernel are in KernelF1Tests."""

    def test_f1h_a_kernel_that_reports_a_newer_abi_than_the_table_knows_fails_with_the_words_table_needs_review(self):
        self.assertFalse(confine.table_needs_review(None))
        self.assertFalse(confine.table_needs_review(confine.TABLE_REVIEWED_ABI))
        self.assertTrue(confine.table_needs_review(confine.TABLE_REVIEWED_ABI + 1))
        self.assertFalse(confine.table_needs_review(ABI), f"table needs review: this kernel reports Landlock ABI {ABI}, the table of "
                                                          f"umwayi/confine.py was reviewed for ABI {confine.TABLE_REVIEWED_ABI}")

    def test_f1i_no_step_suggests_a_way_round_the_refusal(self):
        for reason, step in confine.STEPS.items():
            with self.subTest(reason=reason):
                self.assertNotIn("cooperative", step.lower())
                self.assertNotIn("enforcement:", step)
        for reason in ("unavailable", "kernel", "platform"):
            self.assertIn("the owner chooses the mode of this agent by hand", confine.STEPS[reason])
        agents_src = (REPO / "umwayi" / "agents.py").read_text(encoding="utf-8")
        self.assertNotIn("enforce set cooperative --agent", agents_src)  # the broker refusal does not suggest it either

    def test_f1g_the_flag_says_tcp_and_the_help_and_the_docstring_say_what_it_does_not_block(self):
        self.assertEqual(confine.parse(["--no-tcp", "--", "/bin/true"])[2], True)
        self.assertIsNone(confine.parse(["--no-network", "--", "/bin/true"]))
        self.assertIn("--no-tcp", confine.argv([], [], ["/bin/true"], no_tcp=True))
        self.assertIn("blocks TCP only", confine.__doc__)
        err = subprocess.run([sys.executable, str(REPO / "umwayi" / "confine.py"), "--bogus"], capture_output=True, text=True)
        self.assertEqual(err.returncode, confine.EXIT_USAGE)
        self.assertIn("blocks TCP only: not UDP, not abstract Unix sockets", err.stderr)

    def test_f1f_the_docstring_says_a_write_tree_is_also_readable_and_executable(self):
        self.assertIn("a write tree is also readable and executable", " ".join(confine.__doc__.split()))

    def test_f1e_the_wrappers_own_codes_are_not_the_ordinary_codes_of_a_program_and_the_line_names_the_reason(self):
        self.assertEqual((confine.EXIT_REFUSED, confine.EXIT_USAGE), (125, 124))
        self.assertTrue({0, 1, 2, 64, 126, 127, 130, 143}.isdisjoint({confine.EXIT_REFUSED, confine.EXIT_USAGE}))
        p = subprocess.run([sys.executable, str(REPO / "umwayi" / "confine.py"), "--read", "/usr", "--", "/nonexistent/prog"],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, confine.EXIT_REFUSED)
        self.assertEqual(confine.read_refusal(p.stderr), "profile")
        self.assertIsNone(confine.read_refusal("hello\nrefused: not confined (made-up). Allowed next: x.\n"))
        self.assertIsNone(confine.read_refusal(""))

    def run_wrapper(self, command, slow_start=0.0):
        """The wrapper with the restriction call replaced by one that does nothing, so these tests need no Landlock. It prints `ready` before
        main starts. slow_start holds the process start for that many seconds, so a signal can arrive while the child starts."""
        code = ("import os, sys, time; sys.path.insert(0, %r); from umwayi import confine; confine.apply = lambda *a, **k: 8\n"
                "real = os.posix_spawn\n"
                "os.posix_spawn = lambda *a, **k: (time.sleep(%r), real(*a, **k))[1]\n"
                "print('ready', flush=True)\n"
                "sys.exit(confine.main(['--read', '/usr', '--'] + %r))\n" % (str(REPO), slow_start, command))
        p = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(p.stdout.readline().strip(), "ready")
        return p

    def test_f1e_a_command_that_exits_2_64_124_or_125_is_its_own_code_and_not_a_refusal(self):
        for code in (2, 64, 124, 125):
            with self.subTest(code=code):
                p = self.run_wrapper([sys.executable, "-c", f"import sys; sys.exit({code})"])
                err = p.communicate(timeout=30)[1]
                self.assertEqual(p.returncode, code)
                self.assertIsNone(confine.read_refusal(err))  # so a caller that reads the line is not fooled by the code

    def test_f1d_a_sigterm_that_arrives_while_the_child_starts_or_after_is_passed_on(self):
        import signal
        import time
        sleep = shutil.which("sleep")
        for slow, delay in ((0.8, 0.3), (0.0, 0.5)):  # in the middle of the start (held), and while the child runs
            with self.subTest(during_the_start=bool(slow)):
                p = self.run_wrapper([sleep, "30"], slow_start=slow)
                time.sleep(delay)
                p.send_signal(signal.SIGTERM)
                p.communicate(timeout=30)
                self.assertEqual(p.returncode, 143)  # the child was ended by the signal, 128 + 15, not left running

    def test_f1c_close_inherited_closes_every_descriptor_above_2(self):
        script = Path(tempfile.mkdtemp(prefix="uf1c")) / "t.py"
        script.write_text("import os, sys\nsys.path.insert(0, %r)\nfrom umwayi import confine\n"
                          "fd = os.open('/dev/null', os.O_RDONLY)\nos.set_inheritable(fd, True)\nconfine.close_inherited()\n"
                          "try:\n    os.fstat(fd)\nexcept OSError:\n    print('closed')\nelse:\n    print('open')\n" % str(REPO), encoding="utf-8")
        self.addCleanup(shutil.rmtree, script.parent, True)
        p = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
        self.assertEqual(p.stdout.strip(), "closed", p.stderr)

    def test_f1c_every_process_start_of_the_agents_module_closes_inherited_files(self):
        src = (REPO / "umwayi" / "agents.py").read_text(encoding="utf-8")
        self.assertEqual(src.count("subprocess.Popen("), 2)
        self.assertEqual(src.count("close_fds=True, pass_fds=()"), 3)  # the two starts and the short programs of _run_child


class RunPathsF1Tests(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory(prefix="uf1")
        self.addCleanup(self._t.cleanup)
        self.base = Path(self._t.name).resolve()
        for d in ("root", "work", "tmp", "home/.claude", "bin", "deep/install/bin"):
            (self.base / d).mkdir(parents=True)
        (self.base / "bin" / "x").write_text("#!/bin/sh\n", encoding="utf-8")
        (self.base / "deep" / "install" / "bin" / "y").write_text("#!/bin/sh\n", encoding="utf-8")
        self.kw = dict(command=str(self.base / "bin" / "x"), workdir=str(self.base / "work"), root=str(self.base / "root"),
                       tmp=str(self.base / "tmp"), home=str(self.base / "home"), python=sys.executable, source=str(REPO))

    def run_paths(self, **over):
        return confine.run_paths(**dict(self.kw, **over))

    @unittest.skipUnless(sys.platform.startswith("linux"), "the lists are Linux paths")
    def test_f1a_a_write_root_that_holds_or_lies_inside_the_umwayi_root_is_refused_with_profile(self):
        (self.base / "root" / "inside").mkdir()
        (self.base / "root" / "inside" / ".claude").mkdir()
        cases = {"work folder holds the root": dict(workdir=str(self.base)), "work folder inside the root": dict(workdir=str(self.base / "root" / "inside")),
                 "temp folder inside the root": dict(tmp=str(self.base / "root" / "inside")),
                 "home config inside the root": dict(home=str(self.base / "root" / "inside")),
                 "config dir holds the root": dict(config_dir=str(self.base)), "config dir inside the root": dict(config_dir=str(self.base / "root" / "inside"))}
        for name, over in cases.items():
            with self.subTest(case=name), self.assertRaises(confine.ConfineRefused) as cm:
                self.run_paths(**over)
            self.assertEqual(cm.exception.reason, "profile")
        self.run_paths()  # planted fault: the same call without any of them is fine

    @unittest.skipUnless(sys.platform.startswith("linux"), "the lists are Linux paths")
    def test_f1b_only_the_install_folder_of_the_command_is_listed_not_the_folder_above_it(self):
        read, _ = self.run_paths()
        self.assertIn(str(self.base / "bin"), read)
        self.assertNotIn(str(self.base), read)  # the folder above `bin` would have granted everything below it
        read2, _ = self.run_paths(command=str(self.base / "deep" / "install" / "bin" / "y"))
        self.assertIn(str(self.base / "deep" / "install" / "bin"), read2)
        self.assertNotIn(str(self.base / "deep" / "install"), read2)
        self.assertNotIn(str(self.base / "deep"), read2)


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

    def run_child(self, confined=True, no_tcp=False, read=None, write=None, extra_cmd=None):
        cmd = [sys.executable, "-c", CHILD, str(self.work), str(self.other), str(self.port)]
        argv = confine.argv(self.reads() if read is None else read, [str(self.work)] if write is None else write, cmd,
                            no_tcp=no_tcp) if confined else cmd
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

    def test_f1c_the_confined_command_inherits_no_open_file(self):
        f = os.open("/dev/null", os.O_RDONLY)
        fd = os.dup2(f, 9, inheritable=True)
        os.close(f)
        self.addCleanup(os.close, fd)
        script = "import os, json; print(json.dumps(sorted(int(x) for x in os.listdir('/proc/self/fd'))))"
        argv = confine.argv(self.reads(), [str(self.work)], [sys.executable, "-c", script])
        p = subprocess.run(argv, capture_output=True, text=True, timeout=60, env={"PATH": os.environ.get("PATH", "")}, cwd=str(self.work),
                           pass_fds=(fd,))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertNotIn(9, json.loads(p.stdout.strip().splitlines()[-1]))  # the descriptor the parent passed on is closed

    def test_f1_a_refusal_at_runtime_has_the_wrappers_own_code_and_the_fixed_line(self):
        argv = confine.argv(self.reads() + [str(self.base / "nope")], [str(self.work)], [sys.executable, "-c", "print(1)"])
        p = subprocess.run(argv, capture_output=True, text=True, timeout=60, env={"PATH": os.environ.get("PATH", "")})
        self.assertEqual(p.returncode, confine.EXIT_REFUSED)
        self.assertEqual(confine.read_refusal(p.stderr), "profile")
        self.assertEqual(p.stdout, "")

    def test_the_exit_code_of_the_command_is_the_exit_code_of_the_program(self):
        for code in (0, 3):
            argv = confine.argv(self.reads(), [str(self.work)], [sys.executable, "-c", f"import sys; sys.exit({code})"])
            p = subprocess.run(argv, capture_output=True, text=True, timeout=60, env={"PATH": os.environ.get("PATH", "")})
            self.assertEqual(p.returncode, code, p.stdout + p.stderr)

    def test_the_network_is_open_without_the_option(self):
        self.assertEqual(self.result()["tcp_connect"], 0)

    def test_the_restriction_is_inherited_by_what_the_command_starts(self):
        # the command is a shell that starts another shell (a grandchild of this program) which tries to write outside
        target = self.other / "child.txt"
        sh = shutil.which("sh") or "/bin/sh"
        inner = f"{sh} -c 'echo x > {target}' 2>&1; echo code=$?"
        argv = confine.argv(self.reads(), [str(self.work)], [sh, "-c", inner])
        p = subprocess.run(argv, capture_output=True, text=True, timeout=60, env={"PATH": os.environ.get("PATH", "")}, cwd=str(self.work))
        self.assertIn("Permission denied", p.stdout + p.stderr, p.stdout + p.stderr)  # the kernel's EACCES, from the grandchild
        self.assertNotIn("code=0", p.stdout)
        self.assertFalse(target.exists())
        control = subprocess.run([sh, "-c", inner], capture_output=True, text=True, timeout=60)  # planted fault: unconfined it works
        self.assertIn("code=0", control.stdout, control.stdout + control.stderr)

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
    def test_no_tcp_refuses_tcp_connect_with_the_kernels_error(self):
        self.assertEqual(self.result(no_tcp=True)["tcp_connect"], EACCES)

    def test_planted_fault_the_same_connect_without_the_option_works(self):
        self.assertEqual(self.result(no_tcp=False)["tcp_connect"], 0)


@unittest.skipUnless(ABI and ABI < confine.NET_ABI, "this kernel has the network ABI: the old-kernel refusal is tested by plan() only")
class OldKernelTests(KernelCase):
    def test_no_tcp_on_an_old_kernel_is_refused_with_kernel_and_the_command_is_not_run(self):
        p = self.run_child(no_tcp=True)
        self.assertEqual(p.returncode, confine.EXIT_REFUSED)
        self.assertIn("(kernel)", p.stderr)


if __name__ == "__main__":
    unittest.main()
