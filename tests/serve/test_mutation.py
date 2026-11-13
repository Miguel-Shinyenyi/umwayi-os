"""Tests of the mutation tool and of its catalogue (W6.10, W6.R16.10). The full pass (`python -m tests.serve.mutation`) takes
about twenty minutes and is run by hand and for the pull request; here the tool is tested on a tiny tree of its own, the catalogue
is checked against the real sources, and a few real faults are run against a copy."""

import importlib
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.serve import faults, mutation
from tests.serve.faults import FAULTS, Fault

REPO = mutation.REPO

# the faults of W6.R16.10, by their words; each must be in the catalogue (the ones that cannot be built yet are listed with why)
R16_10 = [
    "the token compared with ==", "the digest not compared at all", "the token in the entry, the output or an error",
    "the record written 0644", "the Host check skipped", "localhost allowed", "a missing Origin allowed on POST",
    "Origin: null allowed", "an Access-Control-Allow-Origin added", "the socket bound to the all-addresses string",
    "the kill switch not read for chats", "the rules check skipped on one route", "the rules answer ignored",
    "a Yes taken from an unlogged check", "the request entry skipped", "the entry holding the body", "OPTIONS answered 200",
    "a duplicate header accepted", "Content-Length absent accepted", "a body read before the gate",
    "an unknown JSON key accepted", "the rate bucket off", "the throttle applied to a valid token",
    "a route added without a table row", "a kill.off route added", "a path in agents.list",
    "the page served without the build.json match", "rotation not seen by a running server", "an expired token accepted",
]
# what the serve tests read from the root of the checkout (a copy for the real faults needs no more)
COPIED = ("umwayi", "tests", "ui", "adapters", "docs", "tools", "rules.yaml", ".gitignore", "serve.rules.example.yaml",
          "pyproject.toml", "agents.example.yaml", "autonomy.example.yaml", "schedule.example.yaml", "jobs.yaml", "README.md",
          "PROJECT.md", "docs-parts")
NOT_BUILT = {"a chat message logged with its text": "the chat routes are W4 and are not built"}


def cli():
    """The command line module, imported by name (it copies and hashes the whole tree; see its docstring)."""
    return importlib.import_module("tests.serve.mutation_cli")


class Catalogue(unittest.TestCase):
    def test_ids_are_unique_and_there_are_at_least_forty_faults(self):
        ids = [f.id for f in FAULTS]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(FAULTS), 40)

    def test_every_edit_is_found_exactly_once_in_the_real_source(self):
        for f in FAULTS:
            text = mutation.path_of(f.file).read_text(encoding="utf-8")
            for old, new in f.edits:
                with self.subTest(fault=f.id):
                    self.assertEqual(text.count(old), 1, f"{f.id}: the text to change is not found exactly once in {f.file}")
                    self.assertNotEqual(old, new)

    def test_every_fault_changes_one_of_the_four_files_and_names_tests_that_exist(self):
        files = {faults.GATE_PY, faults.SERVE_PY, faults.TOKEN_PY, faults.CLIENT_JS}
        for f in FAULTS:
            with self.subTest(fault=f.id):
                self.assertIn(f.file, files)
                self.assertTrue(f.tests)
                for t in f.tests:
                    if t.startswith("node:"):
                        self.assertTrue(mutation.path_of(t[5:]).is_file(), t)
                    else:
                        parts = t.split(".")
                        n = 3 if parts[1] == "serve" else 2
                        self.assertTrue(mutation.path_of("/".join(parts[:n])).with_suffix(".py").is_file(), t)

    def test_every_fault_of_w6_r16_10_is_in_the_catalogue(self):
        named = {f.r16 for f in FAULTS if f.r16}
        for word in R16_10:
            with self.subTest(fault=word):
                self.assertIn(word, named)
        self.assertEqual(set(NOT_BUILT), {"a chat message logged with its text"})  # the one item that waits for W4

    def test_the_four_files_all_have_faults(self):
        by_file = {}
        for f in FAULTS:
            by_file[f.file] = by_file.get(f.file, 0) + 1
        for name in (faults.GATE_PY, faults.SERVE_PY, faults.TOKEN_PY, faults.CLIENT_JS):
            self.assertGreaterEqual(by_file.get(name, 0), 8, name)

    def test_an_equivalent_fault_gives_its_reason(self):
        for f in FAULTS:
            if f.expect == "equivalent":
                self.assertGreater(len(f.why), 40, f.id)


class Harness(unittest.TestCase):
    """The tool on a tree of its own: one module, one test."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tree = Path(self._tmp.name) / "tree"
        (self.tree / "tests").mkdir(parents=True)
        (self.tree / "tests" / "__init__.py").write_text("")
        (self.tree / "mod.py").write_text("def add(a, b):\n    return a + b\n")
        (self.tree / "tests" / "test_mod.py").write_text(
            "import unittest\nimport mod\n\n\nclass T(unittest.TestCase):\n    def test_add(self):\n"
            "        self.assertEqual(mod.add(2, 3), 5)\n")
        self.before = mutation.tree_hashes(self.tree)

    def fault(self, old, new, **kw):
        return Fault("X", "a test fault", "mod.py", ((old, new),), ("tests.test_mod",), **kw)

    def test_a_fault_the_test_sees_is_caught_and_the_file_is_put_back(self):
        o = mutation.run_fault(self.fault("a + b", "a - b"), self.tree, 30)
        self.assertEqual(o.status, "caught")
        self.assertEqual(o.detail, "tests.test_mod")
        self.assertEqual(mutation.tree_hashes(self.tree), self.before)

    def test_a_fault_no_test_sees_survives(self):
        o = mutation.run_fault(self.fault("a + b", "b + a"), self.tree, 30)
        self.assertEqual(o.status, "survived")
        self.assertEqual(mutation.tree_hashes(self.tree), self.before)

    def test_a_fault_that_does_not_compile_is_invalid_and_not_caught(self):
        o = mutation.run_fault(self.fault("a + b", "a + +"), self.tree, 30)
        self.assertEqual(o.status, "invalid")
        self.assertEqual(mutation.tree_hashes(self.tree), self.before)

    def test_text_not_found_or_found_twice_is_not_applied(self):
        self.assertEqual(mutation.run_fault(self.fault("nothing like this", "x"), self.tree, 30).status, "notfound")
        (self.tree / "mod.py").write_text("def add(a, b):\n    return a + b  # a + b\n")
        before = mutation.tree_hashes(self.tree)
        self.assertEqual(mutation.run_fault(self.fault("a + b", "a - b"), self.tree, 30).status, "notfound")
        self.assertEqual(mutation.tree_hashes(self.tree), before)

    def test_a_hang_counts_as_caught_and_the_children_are_gone(self):
        marker = Path(self._tmp.name) / "child.pid"
        # the changed module starts a child that outlives it and then never returns
        child = "import os,sys,time;open(sys.argv[1],'w').write(str(os.getpid()));time.sleep(600)"
        hang = ("import subprocess, sys\n"
                f"subprocess.Popen([sys.executable, '-c', {child!r}, {str(marker)!r}])\n"
                "while True:\n    pass\n")
        o = mutation.run_fault(self.fault("def add(a, b):", hang + "def add(a, b):"), self.tree, 3)
        self.assertEqual(o.status, "caught")
        self.assertIn("did not finish", o.detail)
        self.assertEqual(mutation.tree_hashes(self.tree), self.before)
        if marker.exists():
            pid = int(marker.read_text())
            gone = False
            for _ in range(50):
                try:
                    os.kill(pid, 0)
                except OSError:
                    gone = True
                    break
                import time
                time.sleep(0.1)
            self.assertTrue(gone, "the child of the hanging test was left running")

    def test_the_second_test_is_run_only_if_the_first_passes(self):
        (self.tree / "tests" / "test_two.py").write_text(
            "import unittest\nimport mod\n\n\nclass T(unittest.TestCase):\n    def test_two(self):\n"
            "        self.assertEqual(mod.add(1, 1), 2)\n")
        f = Fault("X", "t", "mod.py", (("a + b", "a * b"),), ("tests.test_mod", "tests.test_two"))
        self.assertEqual(mutation.run_fault(f, self.tree, 30).detail, "tests.test_mod")
        f = Fault("X", "t", "mod.py", (("a + b", "1 if a == 1 else a + b"),), ("tests.test_mod", "tests.test_two"))
        self.assertEqual(mutation.run_fault(f, self.tree, 30).detail, "tests.test_two")

    def test_the_report_counts_planted_caught_and_survived_and_gives_a_reason_for_each_survivor(self):
        a = mutation.Outcome(Fault("A", "one", "mod.py", (), ("t",)), "caught", "t", 1.0)
        b = mutation.Outcome(Fault("B", "two", "mod.py", (), ("t",), expect="equivalent", why="because it is the same"), "survived", "x", 1.0)
        c = mutation.Outcome(Fault("C", "three", "mod.py", (), ("t",)), "survived", "x", 1.0)
        text = mutation.report([a, b, c])
        self.assertIn("planted 3, caught 1, survived 2, invalid 0", text)
        self.assertIn("survivor B (two): because it is the same", text)
        self.assertIn("survivor C (three): no reason recorded", text)


class RealFaults(unittest.TestCase):
    """A few real faults against a copy of the real tree: each is caught by the test named for it, and the real tree is untouched."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.copy = Path(cls._tmp.name) / "tree"
        cls.copy.mkdir()
        for name in COPIED:
            mutation.copy_entry(REPO / name, cls.copy / name)
        cls.mine = {f.id: f for f in FAULTS}

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_copy_is_not_inside_the_real_tree(self):
        self.assertNotIn(REPO, self.copy.resolve().parents)

    def test_four_real_faults_are_caught_by_the_tests_named_for_them(self):
        real_before = mutation.tree_hashes(REPO / "umwayi")
        for fid, expect in (("R4", "tests.serve.test_token"), ("R5", "tests.serve.test_gate_properties"),
                            ("R15", "tests.serve.test_entries"), ("R13a", "tests.serve.test_failclosed")):
            with self.subTest(fault=fid):
                o = mutation.run_fault(self.mine[fid], self.copy, 120, prop_n=200)
                self.assertEqual((o.status, o.detail), ("caught", expect))
        self.assertEqual(mutation.tree_hashes(REPO / "umwayi"), real_before)
        self.assertEqual(mutation.tree_hashes(self.copy / "umwayi"), mutation.tree_hashes(REPO / "umwayi"))

    @unittest.skipUnless(shutil.which("node"), "Node is not installed")
    def test_a_fault_in_the_page_client_is_caught_by_the_node_test(self):
        o = mutation.run_fault(self.mine["C4"], self.copy, 60)
        self.assertEqual((o.status, o.detail), ("caught", "node:ui/test/client.test.mjs"))

    def test_main_refuses_an_unknown_id_and_lists_without_running(self):
        import contextlib
        import io
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli().main(["--only", "NOPE"]), 64)
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli().main(["--list"]), 0)
        self.assertEqual(len(out.getvalue().splitlines()), len(FAULTS))


if __name__ == "__main__":
    unittest.main()
