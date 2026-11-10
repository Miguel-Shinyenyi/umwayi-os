"""The security scan (tasks.md S.2.3, requirements S.R6 and S.R7): file modes, links, paths and races.

Every test runs `python -m umwayi ...` as a real child process in the whole-system test's world
(tests/whole_system_support.py): a temporary root, HOME, XDG_CONFIG_HOME and TMPDIR, and the fakes on PATH.

  modes   every file and folder umwayi makes, under umask 022 and 077: the canary folder 0700, the capture file and
          the intent 0600, the unit files exactly 0644, everything else the owner's umask (S-Q9)
  links   a symbolic link (to a file outside the root, to /dev/zero, to a folder) and a hard link in place of each
          file umwayi reads or writes: refused or handled as its layer says, never a write outside the root, never
          a hang
  paths   every path argument with .., an absolute or relative path where the other is expected, a newline, a very
          long name and a non-UTF-8 name: refused, no traceback, no control character, nothing written
  races   LOGBOOK.md swapped for a link between the check and the append, and links planted where umwayi creates
          with O_EXCL
  chmod   umwayi changes a mode only on a file it has just made
"""

import ast
import json
import os
import shutil
import stat
import subprocess
import sys
import time
import unittest
from pathlib import Path

from tests.budget.support import api_request, logs
from tests.whole_system_support import REPO, World

PKG = REPO / "umwayi"
OUTSIDE = "OUTSIDE-CONTENT-must-not-change\n"
# made only while it holds a secret or an approval-like token: 0600 or 0700 whatever the umask (S-Q9)
PRIVATE = {".umwayi/logbook.pending": 0o600, "canary folder": 0o700, "canary file": 0o600, "capture file": 0o600}


def mode(p: Path) -> int:
    return stat.S_IMODE(os.lstat(p).st_mode)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = World()
        cls.w.build()
        cls.w.save()

    @classmethod
    def tearDownClass(cls):
        cls.w.cleanup()

    def setUp(self):
        self.w.restore()
        self.outside = self.w.base / "outside.txt"
        self.outside.write_text(OUTSIDE, encoding="utf-8")
        self.outdir = self.w.base / "outdir"
        self.outdir.mkdir()

    def assert_outside_untouched(self):
        self.assertEqual(self.outside.read_text(encoding="utf-8"), OUTSIDE, "umwayi wrote to a file outside the root")
        self.assertEqual(os.listdir(self.outdir), [], "umwayi wrote into a folder outside the root")


# ===================================================================== S.R6 modes


class ModeTests(Base):
    def made(self, umask: int) -> dict:
        """Run a day of writes under this umask; return {label: mode} of everything umwayi made."""
        w = self.w
        u = lambda *a, **k: w.u(*a, umask=umask, **k)  # noqa: E731
        self.assertEqual(u("queue", "add", "--kind", "task", "One").returncode, 0)
        self.assertEqual(u("archive", "move", "notes.md", "--lines", "4-5", "--reason", "old").returncode, 0)
        self.assertEqual(u("steward").returncode, 0)
        self.assertEqual(u("social", "draft", "articles/example.md").returncode, 0)
        self.assertEqual(u("publish-draft", "drafts/steward-0001.md", "--approved-by", "Owner").returncode, 0)
        self.assertEqual(u("kill", "on").returncode, 0)
        self.assertEqual(u("kill", "off").returncode, 0)
        self.assertEqual(u("schedule", "install", "answered-queue", "--approved-by", "Owner").returncode, 0)
        capture = w.base / "capture.jsonl"
        self.assertEqual(u("agent", "run", "reviewer", "--prompt", "go", extra={
            "UMWAYI_TELEMETRY_CAPTURE": str(capture),
            "FAKE_SCRIPT": json.dumps([{"do": "otlp", "body": logs(api_request())}, {"do": "exit", "code": 0}])}
        ).returncode, 0)
        out = {}
        # the canary folder and its file exist only during a Claude Code ACP chat: look while the agent waits
        w.node_answers({"turns": [[{"sleep": 30}]]})
        since = time.time()
        p = w.start("agent", "chat", "acp-reviewer", umask=umask)
        p.stdin.write("go\n")
        p.stdin.flush()
        w.wait_for(lambda c: c.get("event") == "session_start_hook", "the canary", proc=p, since=since)
        [folder] = [f for f in w.tmpdir.iterdir() if f.name.startswith("umwayi-canary-")]
        out["canary folder"] = mode(folder)
        [token] = list(folder.iterdir())
        out["canary file"] = mode(token)
        p.terminate()
        w.finish(p)
        # the intent exists while a write holds it: a planted crash after the append leaves it for the next write
        r = u("queue", "add", "--kind", "task", "Two", fault="umwayi.logbook:_record_hash:crash")
        self.assertNotEqual(r.returncode, 0)
        out[".umwayi/logbook.pending"] = mode(w.root / ".umwayi" / "logbook.pending")
        self.assertEqual(u("queue", "add", "--kind", "task", "Three").returncode, 0)  # recovers it
        out["capture file"] = mode(capture)
        for top in (w.root, w.units):
            for p_ in sorted(top.rglob("*")):
                rel = p_.relative_to(w.root).as_posix() if top == w.root else "units/" + p_.name
                if top == w.root and rel.split("/")[0] in ("memory", "workflows", "articles") or rel in (
                        "rules.yaml", "agents.yaml", "units.yaml", "jobs.yaml", "schedule.yaml", "umwayi.json",
                        "notes.md"):
                    continue  # written by the test, not by umwayi
                out[rel] = mode(p_)
        out["units folder"] = mode(w.units)
        return out

    def expected(self, label: str, umask: int, is_dir: bool) -> int:
        if label in PRIVATE:
            return PRIVATE[label]
        if label.startswith("units/"):
            return 0o644
        return (0o777 if is_dir else 0o666) & ~umask

    def check(self, umask: int):
        got = self.made(umask)
        wrong = {}
        for label, m in got.items():
            path = self.w.root / label if not label.startswith(("units", "canary", "capture")) else None
            is_dir = (label in ("canary folder", "units folder") or (path is not None and path.is_dir()))
            want = self.expected(label, umask, is_dir)
            if m != want:
                wrong[label] = f"{oct(m)}, not {oct(want)}"
        for label in ("LOGBOOK.md", "queue.md", ".umwayi", ".umwayi/logbook.sha256", ".umwayi/logbook.lock",
                      ".umwayi/run.lock", "archive/INDEX.md", "archive/A-0001.txt", "drafts", "outbox",
                      "units folder", ".umwayi/logbook.pending", "canary folder", "canary file", "capture file"):
            self.assertIn(label, got, f"{label} was not made")
        self.assertTrue([x for x in got if x.startswith("units/")], "no unit file was made")
        self.assertEqual(wrong, {})

    def test_modes_under_umask_022(self):
        self.check(0o022)

    def test_modes_under_umask_077(self):
        self.check(0o077)


# ===================================================================== S.R7 links


# (file, a command that makes it first or None, the command that reads or writes it, its answer for each kind)
LINK_ROWS = [
    ("rules.yaml", None, ["check", '{"type": "read_memory"}', "--no-log"], 3),
    ("umwayi.json", None, ["memory", "bundle"], 64),
    ("memory/master.md", None, ["memory", "bundle"], 0),  # skipped, never read
    ("jobs.yaml", None, ["run", "{jobs}", "--job", "open-queue"], 64),
    ("workflows/content-loop.yaml", None, ["workflow", "validate", "content-loop"], 64),
    ("schedule.yaml", None, ["schedule", "validate"], 64),
    ("units.yaml", None, ["budget", "validate"], 64),
    ("agents.yaml", None, ["agent", "validate"], 64),
    ("articles/example.md", None, ["social", "draft", "articles/example.md"], 1),
    ("queue.md", ["queue", "add", "--kind", "task", "x"], ["queue", "add", "--kind", "task", "y"], 1),
    ("LOGBOOK.md", ["queue", "add", "--kind", "task", "x"], ["queue", "add", "--kind", "task", "y"], 1),
    (".umwayi/logbook.sha256", ["queue", "add", "--kind", "task", "x"], ["queue", "add", "--kind", "task", "y"], 1),
    (".umwayi/logbook.pending", ["queue", "add", "--kind", "task", "x"], ["queue", "add", "--kind", "task", "y"], 1),
    (".umwayi/logbook.lock", ["queue", "add", "--kind", "task", "x"], ["queue", "add", "--kind", "task", "y"], 1),
    (".umwayi/run.lock", None, ["steward"], 3),
    (".umwayi/KILL", None, ["steward"], 3),  # a KILL that is a link still means on (fail closed)
    ("archive/INDEX.md", ["archive", "move", "notes.md", "--lines", "4-4", "--reason", "r"], ["archive", "verify"], 1),
]


class LinkTests(Base):
    def plant(self, rel: str, kind: str):
        p = self.w.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(p)
        elif p.exists() or p.is_symlink():
            p.unlink()
        p.symlink_to({"outside": self.outside, "devzero": Path("/dev/zero"), "folder": self.outdir}[kind])

    def test_a_symbolic_link_in_place_of_each_file(self):
        for rel, seed, cmd, code in LINK_ROWS:
            for kind in ("outside", "devzero", "folder"):
                with self.subTest(file=rel, link=kind):
                    self.w.restore()
                    self.outside.write_text(OUTSIDE, encoding="utf-8")
                    self.outdir.mkdir(exist_ok=True)
                    if seed:
                        self.assertEqual(self.w.u(*seed).returncode, 0)
                    self.plant(rel, kind)
                    args = [str(self.w.root / "jobs.yaml") if a == "{jobs}" else a for a in cmd]
                    try:
                        r = self.w.u(*args, timeout=30)
                    except subprocess.TimeoutExpired:
                        self.fail(f"umwayi {' '.join(cmd)} hung on {rel} linked to {kind}")
                    self.assertEqual(r.returncode, code, r.stdout + r.stderr)
                    self.assertNotIn("Traceback", r.stdout + r.stderr)
                    self.assert_outside_untouched()

    def test_a_hard_link_to_a_file_outside_the_root(self):
        w = self.w
        rows = [(".umwayi/logbook.lock", 1), ("LOGBOOK.md", 1), ("queue.md", 0), (".umwayi/logbook.sha256", 0),
                ("archive/INDEX.md", 0)]
        for rel, code in rows:
            with self.subTest(file=rel):
                w.restore()
                self.assertEqual(w.u("queue", "add", "--kind", "task", "x").returncode, 0)
                self.assertEqual(w.u("archive", "move", "notes.md", "--lines", "4-4", "--reason", "r").returncode, 0)
                p = w.root / rel
                outside = w.base / "linked-outside"
                outside.unlink(missing_ok=True)
                shutil.copy2(p, outside)  # the same bytes, so every check on the content passes
                p.unlink()
                os.link(outside, p)
                before = outside.read_bytes()
                r = w.u("queue", "add", "--kind", "task", "y") if rel != "archive/INDEX.md" else \
                    w.u("archive", "move", "notes.md", "--lines", "5-5", "--reason", "r2")
                self.assertEqual(r.returncode, code, r.stdout + r.stderr)
                self.assertEqual(outside.read_bytes(), before, f"umwayi wrote through a hard link at {rel}")


# ===================================================================== S.R7 races


class RaceTests(Base):
    def test_logbook_swapped_for_a_link_between_the_check_and_the_append(self):
        w = self.w
        self.assertEqual(w.u("queue", "add", "--kind", "task", "x").returncode, 0)
        p = w.start("queue", "add", "--kind", "task", "y", fault="umwayi.logbook:_append_bytes:pause",
                    extra={"UMWAYI_FAULT_PAUSE": "3"})
        pending = w.root / ".umwayi" / "logbook.pending"
        end = time.monotonic() + 30
        while not pending.exists() and time.monotonic() < end:  # the intent is written just before the append
            time.sleep(0.02)
        self.assertTrue(pending.exists(), "the write never reached its append")
        log = w.root / "LOGBOOK.md"
        shutil.copy2(log, self.outside)
        before = self.outside.read_bytes()
        log.unlink()
        log.symlink_to(self.outside)
        code, out, err, _left = w.finish(p, timeout=60)
        self.assertNotEqual(code, 0, out + err)
        self.assertEqual(self.outside.read_bytes(), before, "the append followed a link swapped in after the check")

    def test_links_where_umwayi_creates_with_o_excl(self):
        w = self.w
        cases = [
            (w.unit_file("answered-queue", "service"), ["schedule", "install", "answered-queue", "--approved-by", "O"],
             2),
            (w.base / "capture.jsonl", ["agent", "run", "reviewer", "--prompt", "go"], 2),
            (w.root / "drafts" / "steward-0001.md", ["steward"], 0),  # the next free number is taken instead
        ]
        for path, cmd, code in cases:
            with self.subTest(path=path.name):
                w.restore()
                self.outside.write_text(OUTSIDE, encoding="utf-8")
                self.outdir.mkdir(exist_ok=True)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.symlink_to(self.outside)
                extra = {"UMWAYI_TELEMETRY_CAPTURE": str(path), "FAKE_SCRIPT": json.dumps([{"do": "exit", "code": 0}])}
                r = w.u(*cmd, extra=extra)
                self.assertEqual(r.returncode, code, r.stdout + r.stderr)
                self.assert_outside_untouched()


# ===================================================================== S.R7 paths


class PathTests(Base):
    def test_every_path_argument_with_bad_shapes(self):
        w = self.w
        (w.base / "outside.md").write_text("x\ny\n", encoding="utf-8")
        bad = {"..": "../outside.md", "newline": "no\nsuch", "long": "a" * 5000,
               "non-UTF-8": os.fsdecode(b"bad\xff.md"), "absolute outside": str(w.base / "outside.md")}
        cmds = [
            ("--agents", lambda v: ["agent", "validate", "--agents", v]),
            ("schedule --file", lambda v: ["schedule", "validate", "--file", v]),
            ("--prompt-file", lambda v: ["agent", "run", "reviewer", "--prompt-file", v]),
            ("a jobs file", lambda v: ["run", v, "--job", "open-queue"]),
            ("a workflow name", lambda v: ["workflow", "validate", v]),
            ("an archive source", lambda v: ["archive", "move", v, "--lines", "1-1", "--reason", "r"]),
            ("an article", lambda v: ["social", "draft", v]),
            ("a draft", lambda v: ["publish-draft", v, "--approved-by", "O"]),
            ("--rules", lambda v: ["check", '{"type": "read_memory"}', "--rules", v, "--no-log"]),
        ]
        before = {str(p): p.stat().st_mtime_ns for p in w.base.rglob("*") if p.is_file() and w.root not in p.parents}
        for shape, value in bad.items():
            for name, make in cmds:
                with self.subTest(argument=name, shape=shape):
                    r = w.u(*make(value))
                    text = r.stdout + r.stderr
                    self.assertNotIn("Traceback", text)
                    self.assertNotIn("unexpected error", text)
                    self.assertFalse([c for c in text if ord(c) < 32 and c not in "\n\t"], "a control character")
                    if not (name == "--prompt-file" and shape == "absolute outside"):  # the owner's own prompt file
                        self.assertNotEqual(r.returncode, 0, text)
            with self.subTest(argument="--root", shape=shape):
                r = subprocess.run([sys.executable, "-m", "umwayi", "--root", value, "queue", "list"],
                                   capture_output=True, text=True, env=w.env(), cwd=str(w.base), timeout=60)
                self.assertNotIn("Traceback", r.stdout + r.stderr)
                self.assertNotIn("unexpected error", r.stdout + r.stderr)
                self.assertNotEqual(r.returncode, 0)
            with self.subTest(argument="UMWAYI_TELEMETRY_CAPTURE", shape=shape):
                r = w.u("agent", "run", "reviewer", "--prompt", "go", extra={"UMWAYI_TELEMETRY_CAPTURE": value,
                                                                            "FAKE_SCRIPT": "[]"})
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertNotIn("Traceback", r.stdout + r.stderr)
        after = {str(p): p.stat().st_mtime_ns for p in w.base.rglob("*") if p.is_file() and w.root not in p.parents}
        changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
        changed = {k for k in changed if not k.endswith(("fake-calls.jsonl", "node-calls.jsonl", "outside.md"))
                   and "__pycache__" not in k}  # Python's own bytecode files
        self.assertEqual(sorted(changed), [], "something outside the root was written")


# ===================================================================== S.R6.3 chmod


class ChmodGuardTests(unittest.TestCase):
    ALLOWED = {("fsutil.py", "atomic_write"), ("fsutil.py", "_umask"), ("schedule.py", "_create")}  # _umask reads it

    def test_umwayi_changes_a_mode_only_on_a_file_it_has_just_made(self):
        found = set()
        for f in sorted(PKG.rglob("*.py")):
            tree = ast.parse(f.read_text(encoding="utf-8"))
            for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
                for node in ast.walk(fn):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and \
                            node.func.attr in ("chmod", "fchmod", "lchmod", "copymode", "copystat", "umask"):
                        found.add((f.name, fn.name))
        self.assertEqual(sorted(found - self.ALLOWED), [], "a mode is changed outside the places that make a file")
        src = (PKG / "fsutil.py").read_text(encoding="utf-8")
        self.assertIn("mkstemp", src)  # the file whose mode atomic_write sets is the temporary file it just made


if __name__ == "__main__":
    unittest.main()
