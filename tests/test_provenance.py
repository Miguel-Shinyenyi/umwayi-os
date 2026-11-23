"""W49: the provenance record of a goal task (umwayi/provenance.py). No signature and no key: nothing here signs or verifies.

  * `structure_hash`: comments, blank lines and quotes leave it the same; a changed docstring or a changed line changes it; source that
    does not parse has none.
  * `build`: an added, a modified and a deleted file are all listed; each hash equals hashlib of the bytes; a link is refused.
  * `store`: 0700 folders, 0600 file, written once; an existing record is kept and refused; nothing is written into the worktree.
  * the written entry: a fixed shape, no path and no content; a hand edit does not parse; a logbook with no chain gets no record.
  * `compare`: unchanged, structure, changed, unnamed. Not a proof of origin.
  * a goal run with `"provenance": {"record": true}` in umwayi.json: one record, one entry before the `in review` entry, hashes equal
    to the files; off by default; no chain is `needs owner` (config) and no record.
Each rule has a planted fault.
"""
import hashlib
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

from tests.goal import cmdsupport as cs
from tests.goal import runsupport as rs
from umwayi import config as cfg
from umwayi import goalstate as gs
from umwayi import logbook, provenance
from umwayi.errors import ConfigError

SENTINEL = "SECRET-PATH-AND-CONTENT-9"


class StructureTests(unittest.TestCase):
    def test_comments_spacing_and_quotes_do_not_change_it_but_code_and_docstrings_do(self):
        a = provenance.structure_hash(b'def f(x):\n    """doc"""\n    return x + 1\n')
        self.assertEqual(a, provenance.structure_hash(b"# note\ndef f( x ):\n\n    '''doc'''\n    return (x+1)  # more\n"))
        self.assertNotEqual(a, provenance.structure_hash(b'def f(x):\n    """doc two"""\n    return x + 1\n'))
        self.assertNotEqual(a, provenance.structure_hash(b'def f(x):\n    """doc"""\n    return x + 2\n'))

    def test_source_that_does_not_parse_has_none(self):
        self.assertIsNone(provenance.structure_hash(b"def (:\n"))
        self.assertIsNone(provenance.structure_hash(b"\xff\xfe\x00"))


class BuildCase(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory(prefix="umwayi-prov-")
        self.addCleanup(self._t.cleanup)
        self.root = Path(self._t.name) / "root"
        self.wt = Path(self._t.name) / "wt"
        (self.wt / "umwayi").mkdir(parents=True)
        (self.root / ".umwayi").mkdir(parents=True)
        (self.wt / "umwayi" / "a.py").write_bytes(b"x = 1\n")
        (self.wt / "umwayi" / "b.py").write_bytes(b"y = 2\n")
        (self.wt / "notes.md").write_bytes(b"hello\n")

    def build(self, changed):
        return provenance.build("G-0007", "T-02", "b" * 40, "t" * 40, "p" * 64, changed, str(self.wt), "2026-11-23T00:00:00Z")


class BuildTests(BuildCase):
    def test_added_modified_and_deleted_are_listed_and_the_hashes_are_the_bytes(self):
        r = self.build([("A", "umwayi/a.py"), ("M", "notes.md"), ("D", "old/gone.py")])
        self.assertEqual([f["path"] for f in r["files"]], ["notes.md", "umwayi/a.py"])
        self.assertEqual(r["removed"], ["old/gone.py"])
        by = {f["path"]: f for f in r["files"]}
        self.assertEqual(by["umwayi/a.py"]["sha256"], hashlib.sha256(b"x = 1\n").hexdigest())
        self.assertEqual(by["umwayi/a.py"]["bytes"], 6)
        self.assertIsNotNone(by["umwayi/a.py"]["ast_sha256"])
        self.assertIsNone(by["notes.md"]["ast_sha256"])

    def test_a_link_and_a_missing_file_are_refused(self):
        os.symlink(self.wt / "notes.md", self.wt / "link.md")
        for rel in ("link.md", "nope.md"):
            with self.subTest(rel=rel), self.assertRaises(provenance.ProvenanceError) as cm:
                self.build([("A", rel)])
            self.assertEqual(cm.exception.reason, "unreadable")

    def test_too_many_files_and_too_many_bytes_are_refused_not_cut(self):
        with self.assertRaises(provenance.ProvenanceError) as cm:
            self.build([("A", f"f{i}.md") for i in range(provenance.MAX_FILES + 1)])
        self.assertEqual(cm.exception.reason, "too_many")
        old, provenance.MAX_BYTES = provenance.MAX_BYTES, 8
        self.addCleanup(setattr, provenance, "MAX_BYTES", old)
        with self.assertRaises(provenance.ProvenanceError) as cm:
            self.build([("A", "umwayi/a.py"), ("A", "umwayi/b.py")])
        self.assertEqual(cm.exception.reason, "too_big")

    def test_the_bytes_are_canonical_and_end_in_one_newline(self):
        data = provenance.canonical(self.build([("A", "umwayi/a.py")]))
        self.assertTrue(data.endswith(b"}\n") and data.count(b"\n") == 1)
        self.assertEqual(json.loads(data)["kind"], "umwayi-provenance")

    def test_planted_fault_the_hash_of_a_changed_file_differs(self):
        r = self.build([("A", "notes.md")])
        (self.wt / "notes.md").write_bytes(b"hello!\n")
        self.assertNotEqual(self.build([("A", "notes.md")])["files"][0]["sha256"], r["files"][0]["sha256"])


class StoreTests(BuildCase):
    def test_written_once_with_the_modes_and_never_into_the_worktree(self):
        before = sorted(p.relative_to(self.wt).as_posix() for p in self.wt.rglob("*"))
        data = provenance.canonical(self.build([("A", "notes.md")]))
        path = provenance.store(self.root, "G-0007", "T-02", data)
        self.assertEqual(path.read_bytes(), data)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        self.assertEqual(sorted(p.relative_to(self.wt).as_posix() for p in self.wt.rglob("*")), before)
        self.assertEqual([p.name for p in path.parent.iterdir()], ["T-02.json"])  # no temporary file left

    def test_an_existing_record_is_refused_and_keeps_its_bytes(self):
        path = provenance.store(self.root, "G-0007", "T-02", b"first\n")
        with self.assertRaises(provenance.ProvenanceError) as cm:
            provenance.store(self.root, "G-0007", "T-02", b"second\n")
        self.assertEqual(cm.exception.reason, "exists")
        self.assertEqual(path.read_bytes(), b"first\n")
        self.assertEqual([p.name for p in path.parent.iterdir()], ["T-02.json"])

    def test_bad_ids_are_refused(self):
        for g, t in (("../G-0001", "T-01"), ("G-0001", "../T"), ("G-1", "T-01")):
            with self.subTest(g=g), self.assertRaises(ValueError):
                provenance.record_path(self.root, g, t)


class EntryTests(BuildCase):
    def entry(self):
        r = self.build([("A", "umwayi/a.py"), ("A", "notes.md"), ("D", "old/gone.py")])
        return provenance.written_entry("2026-11-23", "G-0007", "T-02", r, provenance.canonical(r))

    def test_the_shape_reads_back_with_its_counts(self):
        got = provenance.parse_written(self.entry())
        self.assertEqual((got["goal"], got["task"], got["files"], got["fingerprints"], got["removed"]), ("G-0007", "T-02", 2, 1, 1))
        self.assertRegex(got["sha256"], r"^[0-9a-f]{64}$")

    def test_no_path_and_no_content_is_in_the_entry(self):
        (self.wt / "notes.md").write_text(SENTINEL, encoding="utf-8")
        r = self.build([("A", "notes.md"), ("D", f"{SENTINEL}/x.py")])
        e = provenance.written_entry("2026-11-23", "G-0007", "T-02", r, provenance.canonical(r))
        self.assertNotIn(SENTINEL, e.added + e.checked + e.not_done)

    def test_a_hand_edited_entry_and_another_source_do_not_parse(self):
        e = self.entry()
        for bad in (e.added.replace("written", "signed"), e.added + " extra", e.added.replace("G-0007", "G-7"),
                    e.added.replace("sha256 ", "sha256 zz")):
            with self.subTest(bad=bad[:40]):
                self.assertIsNone(provenance.parse_written(logbook.Entry(e.date, e.source, bad, e.checked, e.not_done)))
        self.assertIsNone(provenance.parse_written(logbook.Entry(e.date, "umwayi check", e.added, e.checked, e.not_done)))

    def test_no_chain_gets_no_record(self):
        with self.assertRaises(provenance.ProvenanceError) as cm:
            provenance.make(self.root, "G-0007", "T-02", "b" * 40, "t" * 40, "p" * 64, [("A", "notes.md")], str(self.wt), "2026-11-23")
        self.assertEqual(cm.exception.reason, "no_chain")
        self.assertFalse((self.root / provenance.FOLDER).exists())


class CompareTests(unittest.TestCase):
    def record(self, raw=b"x = 1\n", py=None):
        return {"python": py or f"{sys.version_info[0]}.{sys.version_info[1]}",
                "files": [{"path": "a.py", "sha256": hashlib.sha256(raw).hexdigest(), "ast_sha256": provenance.structure_hash(raw)}]}

    def test_the_four_answers(self):
        r = self.record()
        self.assertEqual(provenance.compare(r, "a.py", b"x = 1\n"), "unchanged")
        self.assertEqual(provenance.compare(r, "a.py", b"# a comment\nx   =   1\n"), "structure")
        self.assertEqual(provenance.compare(r, "a.py", b"x = 2\n"), "changed")
        self.assertEqual(provenance.compare(r, "other.py", b"x = 1\n"), "unnamed")

    def test_another_python_minor_version_compares_bytes_only(self):
        r = self.record(py="2.0")
        self.assertEqual(provenance.compare(r, "a.py", b"# a comment\nx = 1\n"), "changed")

    def test_planted_fault_a_changed_byte_is_never_unchanged(self):
        self.assertNotEqual(provenance.compare(self.record(), "a.py", b"x = 1 \n"), "unchanged")


class ConfigTests(unittest.TestCase):
    def load(self, extra):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "umwayi.json").write_text(json.dumps(dict({"memory_dir": "m", "private_paths": []}, **extra)), encoding="utf-8")
            return cfg.load_config(Path(d))

    def test_off_by_default_and_on_when_asked(self):
        self.assertFalse(self.load({}).provenance_record)
        self.assertFalse(self.load({"provenance": {}}).provenance_record)
        self.assertTrue(self.load({"provenance": {"record": True}}).provenance_record)

    def test_anything_else_is_refused(self):
        for bad in ({"provenance": []}, {"provenance": {"record": "yes"}}, {"provenance": {"record": True, "public_key": "k"}}):
            with self.subTest(bad=bad), self.assertRaises(ConfigError):
                self.load(bad)


class GoalCase(cs.CmdCase):
    def provenance_on(self):
        p = self.root / "umwayi.json"
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"memory_dir": "memory", "private_paths": []}
        data["provenance"] = {"record": True}
        p.write_text(json.dumps(data), encoding="utf-8")

    def chain(self):
        logbook.seal(self.root, "2026-11-23", "test", start_chain=True)

    def go(self, chain=False):
        goal = self.g_approved()
        if chain:
            self.chain()
        scripts = [{"steps": rs.builder_steps(goal, "T-01"), "spend": 3}, {"steps": rs.tester_steps(), "spend": 2},
                   {"steps": rs.check_steps(), "spend": 1}]
        return goal, self.call("run", goal, scripts=scripts)

    def entries(self):
        return [e for e in logbook.read_checked(self.root) if e.source in (provenance.SOURCE, gs.SOURCE)]


class GoalTests(GoalCase):
    def test_a_record_and_its_entry_come_before_in_review_and_the_hashes_are_the_files(self):
        self.provenance_on()
        goal, code = self.go(chain=True)
        self.assertEqual(code, 0, self.err)
        path = self.root / provenance.FOLDER / goal / "T-01.json"
        rec = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(rec["goal"], goal)
        names = {f["path"] for f in rec["files"]}
        self.assertIn("umwayi/piece1.py", names)
        by = {f["path"]: f for f in rec["files"]}
        self.assertEqual(by["umwayi/piece1.py"]["sha256"], hashlib.sha256(b"x = 1\n").hexdigest())
        order = [("prov" if e.source == provenance.SOURCE else e.added) for e in self.entries()]
        i = order.index("prov")
        self.assertTrue(any("running to in review" in o for o in order[i + 1:]), order)
        self.assertFalse(any("running to in review" in o for o in order[:i]), order)
        self.assertEqual(provenance.parse_written([e for e in self.entries() if e.source == provenance.SOURCE][0])["sha256"],
                         hashlib.sha256(path.read_bytes()).hexdigest())

    def test_off_by_default_no_record_and_no_entry(self):
        goal, code = self.go(chain=True)
        self.assertEqual(code, 0, self.err)
        self.assertFalse((self.root / provenance.FOLDER).exists())
        self.assertEqual([e for e in self.entries() if e.source == provenance.SOURCE], [])

    def test_on_with_no_chain_is_needs_owner_config_and_no_record(self):
        self.provenance_on()
        goal, code = self.go()
        self.assertEqual(code, 3, self.err)
        t = gs.read_task(self.root, goal, "T-01")
        self.assertEqual((t["state"], t["reason"]), ("needs owner", "config"))
        self.assertIn("Cause: provenance_not_recorded.", self.logbook_text())
        self.assertFalse((self.root / provenance.FOLDER).exists())

    def test_the_worktree_and_branch_hold_nothing_of_the_record(self):
        self.provenance_on()
        goal, code = self.go(chain=True)
        self.assertEqual(code, 0, self.err)
        import subprocess
        files = subprocess.run(["git", "-C", str(self.root), "ls-tree", "-r", "--name-only", gs.read_task(self.root, goal, "T-01")["branch"]],
                               capture_output=True, text=True).stdout
        self.assertNotIn("provenance", files)


if __name__ == "__main__":
    unittest.main()
