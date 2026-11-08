"""The run lock: one AI helper, job or workflow run at a time, never waiting."""

import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import entry_text, without_run_lock, write_sealed_logbook
from umwayi import logbook, runlock
from umwayi.cli import main
from umwayi.logbook import parse

REPO = Path(__file__).resolve().parent.parent
RULES = (REPO / "rules.yaml").read_text(encoding="utf-8")
QUEUE = (
    "# Queue\n\n| id | kind | title | status | recommendation | answer | answered |\n"
    "| --- | --- | --- | --- | --- | --- | --- |\n| Q-0001 | task | Write the post | open | | | |\n"
)
LOOP = ("name: content-loop\nsteps:\n  - name: collect\n    command: queue-list\n"
        "  - name: brief\n    command: steward\n  - name: draft\n    command: social-draft\n"
        "    article: articles/week.md\n  - name: approve\n    command: approve\n")
ARTICLE = "---\ntitle: Week 45\nlink: https://example.org/week-45\n---\n\nThis week I built the run lock.\n"
JOBS = "jobs:\n  - name: open-queue\n    command: queue-list\n    min_gap_days: 1\n"

RUNNERS = {
    "steward": ["steward"],
    "social": ["social", "draft", "articles/week.md"],
    "job": ["run", "jobs.yaml", "--job", "open-queue"],
    "workflow": ["workflow", "run", "content-loop"],
}
SOURCES = {"steward": "umwayi steward", "social": "umwayi social", "job": "umwayi run", "workflow": "umwayi workflow"}

# A real process: wait for the start signal, then run one umwayi command. While it holds the
# run lock it sleeps once (inside logbook.read_checked, which every runner calls after taking the
# lock), so two runs that start together are sure to overlap.
CHILD = r"""
import os, sys, time
from unittest import mock
from umwayi import logbook
import umwayi.cli as cli
root, ready, go, argv = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
real = logbook.read_checked
slept = []
def slow(r):
    if not slept:
        slept.append(1)
        time.sleep(1.5)
    return real(r)
open(ready, "w").close()
deadline = time.monotonic() + 30
while not os.path.exists(go):
    if time.monotonic() > deadline:
        sys.exit(99)
    time.sleep(0.002)
with mock.patch("umwayi.logbook.read_checked", slow):
    code = cli.main(["--root", root, *argv])
sys.exit(code)
"""


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "rules.yaml").write_text(RULES, encoding="utf-8")
        (self.root / "umwayi.json").write_text(json.dumps({
            "memory_dir": "memory", "private_paths": [], "social_channels": ["linkedin", "mastodon"]}))
        (self.root / "articles").mkdir()
        (self.root / "articles" / "week.md").write_text(ARTICLE, encoding="utf-8")
        (self.root / "workflows").mkdir()
        (self.root / "workflows" / "content-loop.yaml").write_text(LOOP, encoding="utf-8")
        (self.root / "jobs.yaml").write_text(JOBS, encoding="utf-8")
        (self.root / "queue.md").write_text(QUEUE, encoding="utf-8")
        self.log = self.root / "LOGBOOK.md"
        p = mock.patch.object(logbook, "LOCK_WAIT_SECONDS", 10)
        p.start()
        self.addCleanup(p.stop)

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        old = sys.stderr
        sys.stderr = err
        try:
            with mock.patch("umwayi.cli._today", return_value="2026-11-07"):
                code = main(["--root", str(self.root), *argv], out=out)
        finally:
            sys.stderr = old
        return code, out.getvalue(), err.getvalue()

    def entries(self):
        return [p.entry for p in parse(self.log.read_text(encoding="utf-8"))[0]] if self.log.exists() else []

    def snap(self):
        out = {}
        for dp, dn, fn in os.walk(self.root):
            for d in dn:
                out[os.path.relpath(os.path.join(dp, d), self.root) + "/"] = "folder"
            for f in fn:
                full = os.path.join(dp, f)
                out[os.path.relpath(full, self.root)] = Path(full).read_bytes()
        return out

    def assert_free(self):
        """The run lock can be taken again: it was released."""
        with runlock.held(self.root):
            pass


@unittest.skipIf(runlock.fcntl is None, "fcntl is not available on this platform")
class TwoRealProcessesTests(Base):
    def race(self, a, b):
        signal = Path(tempfile.mkdtemp(prefix="umwayi-race-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(signal, ignore_errors=True))
        go = signal / "go"
        env = dict(os.environ, PYTHONPATH=str(REPO))
        procs = []
        for k, name in enumerate((a, b)):
            ready = signal / f"ready-{k}"
            procs.append((name, ready, subprocess.Popen(
                [sys.executable, "-c", CHILD, str(self.root), str(ready), str(go), *RUNNERS[name], "--date", "2026-11-07"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)))
        deadline = time.monotonic() + 30
        while not all(r.exists() for _, r, _ in procs):  # both processes are up and waiting
            self.assertLess(time.monotonic(), deadline, "the processes did not start")
            time.sleep(0.01)
        go.touch()  # start both at the same moment
        results = []
        for name, _, p in procs:
            out, err = p.communicate(timeout=60)
            results.append((name, p.returncode, out.decode(), err.decode()))
        return results

    def test_two_runs_at_once_never_both_write(self):
        pairs = [("steward", "steward"), ("social", "social"), ("steward", "social"),
                 ("job", "job"), ("workflow", "workflow"), ("job", "workflow"), ("steward", "workflow")]
        for a, b in pairs:
            with self.subTest(pair=f"{a} and {b}"):
                self.setUp_fresh()
                results = self.race(a, b)
                busy = [r for r in results if "holds the run lock" in r[2]]
                ran = [r for r in results if "holds the run lock" not in r[2]]
                self.assertEqual(len(busy), 1, results)
                self.assertEqual(len(ran), 1, results)
                name, code, out, err = busy[0]
                self.assertEqual(code, 3)
                self.assertTrue(out.startswith("Ask me first\nRule: (none)\nReason: Another umwayi run"), out)
                # the logbook is whole and has exactly one "busy" entry, from the run that was refused
                self.assertEqual(self.cli("logbook", "verify")[0], 0)
                stops = [e for e in self.entries() if "another umwayi run holds the run lock" in e.added]
                self.assertEqual(len(stops), 1)
                self.assertEqual(stops[0].source, SOURCES[name])
                # only one run wrote drafts and queue items
                self.assertEqual(self.drafts_written(), self.drafts_of(ran[0][0]))
                self.assertEqual(self.queue_rows(), 1 + (1 if ran[0][0] == "workflow" else 0))
                self.assert_free()

    def setUp_fresh(self):
        import shutil
        for name in ("drafts", ".umwayi"):
            shutil.rmtree(self.root / name, ignore_errors=True)
        self.log.unlink(missing_ok=True)
        (self.root / "queue.md").write_text(QUEUE, encoding="utf-8")

    def drafts_written(self):
        d = self.root / "drafts"
        return sorted(os.listdir(d)) if d.exists() else []

    def drafts_of(self, runner):
        return {
            "steward": ["steward-0001.md"],
            "social": ["post-linkedin-0001.md", "post-mastodon-0001.md"],
            "job": [],
            "workflow": ["post-linkedin-0001.md", "post-mastodon-0001.md", "steward-0001.md"],
        }[runner]

    def queue_rows(self):
        return sum(1 for line in (self.root / "queue.md").read_text().splitlines() if line.startswith("| Q-"))


class HeldLockTests(Base):
    def test_a_held_lock_gives_ask_me_first_one_entry_and_no_change(self):
        for name, argv in RUNNERS.items():
            with self.subTest(runner=name):
                with runlock.held(self.root):  # another run is going
                    n = len(self.entries())
                    before = without_run_lock(self.snap())
                    code, out, _ = self.cli(*argv)
                    after = without_run_lock(self.snap())
                self.assertEqual(code, 3)
                self.assertTrue(out.startswith("Ask me first\nRule: (none)\nReason: Another umwayi run"))
                new = self.entries()[n:]
                self.assertEqual(len(new), 1)
                self.assertEqual(new[0].source, SOURCES[name])
                self.assertIn("another umwayi run holds the run lock", new[0].added)
                changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
                self.assertEqual([c for c in changed if c not in ("LOGBOOK.md", ".umwayi/logbook.sha256", ".umwayi/")], [])
                self.assert_free()

    def test_the_lock_never_waits(self):
        with runlock.held(self.root):
            start = time.monotonic()
            self.assertEqual(self.cli("steward")[0], 3)
            self.assertLess(time.monotonic() - start, 2.0)

    def test_the_kill_switch_still_comes_first(self):
        self.cli("kill", "on")
        with runlock.held(self.root):
            code, out, _ = self.cli("steward")
        self.assertEqual(code, 3)
        self.assertIn("The kill switch is on", out)

    def test_owner_commands_do_not_take_the_lock(self):
        with runlock.held(self.root):
            self.assertEqual(self.cli("queue", "add", "--kind", "task", "x")[0], 0)
            self.assertEqual(self.cli("check", '{"type": "read_memory"}')[0], 0)
            self.assertEqual(self.cli("workflow", "validate", "content-loop")[0], 0)


class ReleaseTests(Base):
    def test_released_after_success_and_after_every_stop(self):
        cases = {
            "success": lambda: None,
            "a No": lambda: (self.root / "rules.yaml").write_text(
                RULES + "  - id: no-steward\n    title: t\n    text: t\n    verdict: no\n    matchers:\n"
                        "      helper__exists: true\n      type: read_queue\n"),
            "broken rules": lambda: (self.root / "rules.yaml").write_text("rules: [\n"),
            "tampered logbook": lambda: (write_sealed_logbook(self.root, "# Logbook\n" + entry_text(date="2026-11-01")),
                                         self.log.write_text("tampered")),
            "malformed queue": lambda: (self.root / "queue.md").write_text("broken\n"),
            "bad workflow file": lambda: (self.root / "workflows" / "content-loop.yaml").write_text("name: x\n"),
            "bad jobs file": lambda: (self.root / "jobs.yaml").write_text("jobs: [\n"),
        }
        for case, setup in cases.items():
            for name, argv in RUNNERS.items():
                with self.subTest(case=case, runner=name):
                    self.setUp()
                    setup()
                    self.cli(*argv)
                    self.assert_free()

    def test_released_after_an_unexpected_error_and_after_ctrl_c(self):
        for exc in (RuntimeError("boom"), KeyboardInterrupt()):
            for name, argv in RUNNERS.items():
                with self.subTest(exc=type(exc).__name__, runner=name):
                    with mock.patch("umwayi.logbook.read_checked", side_effect=exc):
                        code, _, _ = self.cli(*argv)
                    self.assertEqual(code, 2)
                    self.assert_free()

    def test_released_when_the_process_dies(self):
        code = (
            "import os, sys\nfrom umwayi import runlock\n"
            f"with runlock.held({str(self.root)!r}):\n    os._exit(0)\n"
        )
        subprocess.run([sys.executable, "-c", code], env=dict(os.environ, PYTHONPATH=str(REPO)), check=True)
        self.assert_free()


class FailClosedTests(Base):
    def test_no_locking_on_this_platform_gives_ask_me_first(self):
        for name, argv in RUNNERS.items():
            with self.subTest(runner=name):
                n = len(self.entries())
                with mock.patch.object(runlock, "fcntl", None):
                    code, out, _ = self.cli(*argv)
                self.assertEqual(code, 3)
                self.assertIn("could not be taken (file locking is not available on this platform)", out)
                self.assertFalse((self.root / "drafts").exists())
                new = self.entries()[n:]
                self.assertEqual([e.added.endswith("the run lock could not be taken") for e in new], [True])

    def test_the_os_refusing_the_lock_gives_ask_me_first(self):
        class FakeFcntl:
            LOCK_EX, LOCK_NB, LOCK_UN = 2, 4, 8

            @staticmethod
            def flock(fd, op):
                raise OSError(5, "I/O error")
        with mock.patch.object(runlock, "fcntl", FakeFcntl):
            code, out, _ = self.cli("steward")
        self.assertEqual(code, 3)
        self.assertIn("the operating system refused the lock", out)

    def test_a_linked_lock_file_gives_ask_me_first(self):
        (self.root / ".umwayi").mkdir()
        try:
            (self.root / ".umwayi" / "run.lock").symlink_to(self.root / "queue.md")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not supported")
        before = (self.root / "queue.md").read_bytes()
        code, out, _ = self.cli("steward")
        self.assertEqual(code, 3)
        self.assertIn("cannot be opened", out)
        self.assertEqual((self.root / "queue.md").read_bytes(), before)

    def test_a_lock_folder_gives_ask_me_first(self):
        (self.root / ".umwayi" / "run.lock").mkdir(parents=True)
        self.assertEqual(self.cli("run", "jobs.yaml", "--job", "open-queue")[0], 3)

    def test_the_lock_file_is_never_deleted(self):
        self.cli("steward")
        self.assertTrue((self.root / ".umwayi" / "run.lock").is_file())


if __name__ == "__main__":
    unittest.main()
