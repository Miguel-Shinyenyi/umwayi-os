"""Layer 10 part 8, task 10.50: the fault table of tests/agents/opencode_mutants.py stays true to the source.

The fault runs themselves take most of an hour and are not part of the suite. What the suite checks is that the table
cannot rot unseen: every edit still has its anchor in the source, every mutated file still compiles, every test a fault
names still exists, the faults the task lists are all there, and the runner reports `caught`, `survived`, `invalid`
and a hang correctly on small faults of its own, without ever touching the real source tree.
"""

import hashlib
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from umwayi import agents

from tests.agents import opencode_mutants as m

REPO = Path(__file__).resolve().parents[2]
REAL = [m.AG, m.ACP, m.PLUGIN]


def digest():
    return {p: hashlib.sha256((m.REPO / p).read_bytes()).hexdigest() for p in REAL}


def mutated(f):
    """{path: mutated text} of fault `f`, from the real source, in memory."""
    out = {}
    for e in f.edits:
        out[e.path] = m.apply_edit(out.get(e.path) or (m.REPO / e.path).read_text(encoding="utf-8"), e)
    return out


class TableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.faults = m.all_faults()

    def test_every_anchor_is_in_the_source_the_stated_number_of_times(self):
        for f in self.faults:
            with self.subTest(fault=f.id):
                self.assertTrue(f.edits, f.id)
                mutated(f)  # raises ValueError for a missing or repeated anchor, and for an edit that changes nothing

    def test_every_mutated_python_file_compiles(self):
        for f in self.faults:
            for path, text in mutated(f).items():
                if path.endswith(".py"):
                    with self.subTest(fault=f.id, path=path):
                        compile(text, path, "exec")

    def test_every_mutated_plugin_parses_under_node(self):
        with tempfile.TemporaryDirectory() as tmp:
            for f in self.faults:
                for path, text in mutated(f).items():
                    if path.endswith(".js"):
                        with self.subTest(fault=f.id):
                            p = Path(tmp) / f"{f.id}.mjs"
                            p.write_text(text, encoding="utf-8")
                            r = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True, timeout=30)
                            self.assertEqual(r.returncode, 0, r.stderr)

    def test_every_test_a_fault_names_exists_and_has_tests(self):
        loader = unittest.TestLoader()
        for name in sorted({t for f in self.faults for t in f.tests} | set(m.WHOLE_SUITE)):
            with self.subTest(target=name):
                suite = loader.loadTestsFromName(name)
                self.assertGreater(suite.countTestCases(), 0, name)
                self.assertNotIn("_FailedTest", repr(suite), name)

    def test_ids_are_unique_and_every_fault_has_words_and_tests(self):
        ids = [f.id for f in self.faults]
        self.assertEqual(len(ids), len(set(ids)))
        for f in self.faults:
            self.assertTrue(f.title and f.group and f.tests, f.id)
            self.assertNotIn("\u2014", f.title)  # no em dash
            self.assertGreater(f.limit, 0)

    def test_the_throwaway_copy_holds_what_the_opencode_tests_read(self):
        self.assertEqual(set(m.COPIED), {"umwayi", "adapters", "tests", "rules.yaml"})
        with tempfile.TemporaryDirectory() as tmp:
            tree = m.copy_tree(Path(tmp) / "tree")
            for name in m.COPIED:
                self.assertTrue((tree / name).exists(), name)
            self.assertNotEqual(tree.resolve(), REPO)
            self.assertTrue((REPO / "adapters" / "opencode" / "plugin" / "index.js").is_file())  # what is copied is there
            self.assertTrue((REPO / "rules.yaml").is_file())
            self.assertFalse((tree / ".git").exists())

    def test_the_faults_the_task_lists_are_there(self):
        by_id = {f.id: f for f in self.faults}
        planted = [by_id[i] for i in ("A1", "A2", "A3", "A4", "A5")]
        self.assertEqual({f.group for f in planted}, {"planted"})
        self.assertEqual(len(planted[3].edits), 2)  # the ask rule and the evaluate hook go together
        self.assertEqual({e.path for e in planted[3].edits}, {m.AG, m.PLUGIN})
        groups = {f.group for f in self.faults}
        self.assertEqual(groups, {"planted", "gate", "allow list", "policy", "plugin", "token", "always", "model",
                                  "second gate", "earlier survivor"})

    def test_each_of_the_six_gate_checks_has_a_fault_removing_it_and_one_loosening_it(self):
        ids = {f.id for f in self.faults}
        for prefix in ("B1", "B2", "B3", "B4", "B5", "B6"):
            self.assertGreaterEqual(len([i for i in ids if i.startswith(prefix)]), 2, prefix)
        for removed in ("B1a", "B2c", "B3a", "B4a", "B6a", "A3", "A5"):
            self.assertIn(removed, ids)

    def test_each_allow_list_fault_names_something_the_list_leaves_out(self):
        for name, _ in m.EXCLUDED:
            self.assertNotIn(name, agents.OPENCODE_ENV_NAMES)
        names = [n for n, _ in m.EXCLUDED]
        for named in ("OPENCODE_API_KEY", "OPENCODE_CONFIG", "OPENCODE_CONFIG_DIR", "OPENCODE_DB", "OPENCODE_PASSWORD",
                      "OPENCODE_DISABLE_PROJECT_CONFIG", "NODE_OPTIONS", "NODE_PATH"):
            self.assertIn(named, names)  # 10.R13.4 by name

    def test_every_policy_statement_has_a_removing_fault_and_the_reorders_exist(self):
        titles = " | ".join(f.title for f in self.faults if f.group == "policy")
        for word in ("permissions statement", "policy 1 removed", "policy 2 removed", "policy 3 removed",
                     "policy 4 removed", "swapped", "reversed", "model statement", "plugins statement"):
            self.assertIn(word, titles)

    def test_the_survivors_of_the_earlier_rounds_are_in_the_table_with_their_new_tests(self):
        survivors = [f for f in self.faults if f.group == "earlier survivor"]
        self.assertEqual([f.id for f in survivors], ["S1", "S2", "S3"])
        for f in survivors:
            self.assertTrue(all(t.startswith(m.FAULTS_TESTS) for t in f.tests), f.id)


class RunnerTests(unittest.TestCase):
    def test_a_fault_that_a_test_catches_is_caught_and_the_real_source_is_untouched(self):
        before = digest()
        f = next(x for x in m.all_faults() if x.id == "A2")
        o = m.run_fault(f)
        self.assertEqual(o.status, "caught", o.how)
        self.assertEqual(o.how, "failed")
        self.assertTrue(o.failed and all(i.startswith("tests.agents.test_agents_opencode_") for i in o.failed), o.failed)
        self.assertEqual(digest(), before)

    def test_a_fault_that_no_listed_test_notices_survives(self):
        f = m.fault("T1", "test", "a comment changes", m.py("# the umwayi plugin, written in 10.45", "# the plugin"),
                    [m.CONFIG + ".EnvAllowListTests"])
        o = m.run_fault(f)
        self.assertEqual((o.status, o.failed), ("survived", []))

    def test_a_hang_is_caught(self):
        f = m.fault("T2", "test", "umwayi hangs on import", m.py("OPENCODE_ROUTES = {", "import time\ntime.sleep(60)\nOPENCODE_ROUTES = {"),
                    [m.CONFIG + ".EnvAllowListTests"], limit=6)
        start = time.monotonic()
        o = m.run_fault(f)
        self.assertEqual((o.status, o.how), ("caught", "hang"))
        self.assertLess(time.monotonic() - start, 30)

    def test_a_fault_that_does_not_compile_is_invalid_not_caught(self):
        f = m.fault("T3", "test", "a syntax error", m.py("OPENCODE_ROUTES = {", "OPENCODE_ROUTES = (\nOPENCODE_ROUTES = {"),
                    [m.CONFIG + ".EnvAllowListTests"])
        o = m.run_fault(f)
        self.assertEqual(o.status, "invalid")
        self.assertIn("does not compile", o.how)

    def test_an_anchor_that_is_gone_is_invalid(self):
        f = m.fault("T4", "test", "no such text", m.py("this text is nowhere in the source", "x"), [m.CONFIG])
        self.assertEqual(m.run_fault(f).status, "invalid")

    def test_a_fault_is_never_applied_to_the_real_tree(self):
        f = m.all_faults()[0]
        with self.assertRaises(ValueError):
            m.apply_fault(m.REPO, f)
        with tempfile.TemporaryDirectory() as tmp:  # a path that leaves the copy
            bad = m.fault("T5", "test", "outside", m.Edit("../outside.py", "a", "b"), [m.CONFIG])
            with self.assertRaises(Exception):
                m.apply_fault(Path(tmp), bad)

    def test_run_limited_kills_a_run_past_its_limit(self):
        start = time.monotonic()
        code, _, hung = m.run_limited(["python3", "-c", "import time; time.sleep(60)"], m.REPO, 1)
        self.assertEqual((code, hung), (None, True))
        self.assertLess(time.monotonic() - start, 20)

    def test_failing_ids_are_read_from_the_unittest_output(self):
        out = ("FAIL: test_a (tests.x.C.test_a)\nxx\nERROR: test_b (tests.x.D.test_b)\n"
               "ERROR: tests.y (unittest.loader._FailedTest.tests.y)\n")
        self.assertEqual(m.failing_ids(out), ["tests.x.C.test_a", "tests.x.D.test_b", "!import:tests.y"])

    def test_the_counts_and_the_report(self):
        f = m.all_faults()[:3]
        out = [m.Outcome(f[0], "caught", "failed", ["a.b.C.t"]), m.Outcome(f[1], "caught", "hang"),
               m.Outcome(f[2], "survived", "", wide="survived the whole OpenCode suite")]
        self.assertEqual(m.counts(out), {"planted": 3, "caught": 2, "survived": 1, "invalid": 0, "hang": 1})
        text = m.markdown(out)
        self.assertIn("Total: 3 faults, 2 caught (1 by a hang), 1 survived, 0 invalid.", text)
        self.assertIn("survived the whole OpenCode suite", text)


if __name__ == "__main__":
    unittest.main()
