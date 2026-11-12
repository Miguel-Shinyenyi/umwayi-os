"""W20, Part A: the map of what each test file reads outside its own area (tools/ci_map.json) and the checker that
fails when a test file reads a path the map does not list for it, so the map cannot go stale."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools import ci_map

REPO = Path(__file__).resolve().parent.parent
DATA = ci_map.load_map()
SCANS = (ci_map.scan_python(REPO), ci_map.scan_node(REPO))  # the tree is scanned once for all the checks below


def tree(files):
    tmp = tempfile.TemporaryDirectory(prefix="umwayi-cimap-")
    root = Path(tmp.name)
    for name, text in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return tmp, root


HEAD = "from pathlib import Path\nimport os\nREPO = Path(__file__).resolve().parent.parent\n"


class ScannerTests(unittest.TestCase):
    def scan(self, body, extra=None):
        tmp, root = tree({"tests/__init__.py": "", "tests/test_x.py": HEAD + body, **(extra or {})})
        self.addCleanup(tmp.cleanup)
        return ci_map.scan_python(root).get("tests/test_x.py", set())

    def test_a_path_join_with_the_repo_is_a_read(self):
        self.assertEqual(self.scan('P = REPO / "ui" / "src" / "a.js"\n'), {"ui"})

    def test_ui_dist_is_its_own_entry(self):
        self.assertEqual(self.scan('P = REPO / "ui" / "dist" / "index.html"\n'), {"ui", "ui/dist"})

    def test_an_fstring_and_os_path_join_are_reads(self):
        self.assertEqual(self.scan('P = f"{REPO}/docs/x.md"\nQ = os.path.join(REPO, "site", "a")\n'), {"docs", "site"})

    def test_a_root_file_is_a_read(self):
        self.assertEqual(self.scan('P = REPO / "README.md"\nQ = (REPO / ".kiro" / "specs").read_text()\n'), {"README.md", ".kiro"})

    def test_a_name_in_a_temporary_root_is_not_a_read(self):
        self.assertEqual(self.scan('def f(root):\n    return root / "docs" / "x.md", root / "rules.yaml"\n'), set())

    def test_a_word_in_a_message_is_not_a_read(self):
        self.assertEqual(self.scan('MSG = "see the docs and the site"\nD = {"ui": 1}\n'), set())

    def test_importing_the_adapters_package_is_a_read(self):
        self.assertEqual(self.scan("from adapters.kiro import hook\n"), {"adapters"})
        self.assertEqual(self.scan("import adapters.common.umwayi_gate\n"), {"adapters"})

    def test_walking_the_whole_repo_is_a_star(self):
        self.assertEqual(self.scan('X = list(REPO.rglob("settings*.json"))\n'), {"*"})
        self.assertEqual(self.scan('import subprocess\nsubprocess.run(["git", "ls-files"], cwd=REPO)\n'), {"*"})

    def test_walking_the_package_is_not_a_star(self):
        self.assertEqual(self.scan('X = list((REPO / "umwayi").rglob("*.py"))\n'), set())

    def test_a_helper_module_read_counts_for_the_test_that_imports_it(self):
        extra = {"tests/helper.py": HEAD + 'P = REPO / "docs"\n'}
        self.assertEqual(self.scan("from tests import helper\nfrom tests.helper import P\n", extra), {"docs"})
        self.assertEqual(self.scan("import tests.helper\n", extra), {"docs"})

    def test_a_name_imported_from_a_helper_keeps_being_a_repo_anchor(self):
        extra = {"tests/helper.py": HEAD}
        self.assertEqual(self.scan('from tests.helper import REPO\nP = REPO / "site"\n', extra), {"site"})

    def test_a_syntax_error_is_reported_not_skipped(self):
        tmp, root = tree({"tests/__init__.py": "", "tests/test_x.py": "def (:\n"})
        self.addCleanup(tmp.cleanup)
        with self.assertRaises(ci_map.MapError):
            ci_map.scan_python(root)


class NodeScannerTests(unittest.TestCase):
    def scan(self, text, name="ui/test/a.test.mjs"):
        tmp, root = tree({name: text})
        self.addCleanup(tmp.cleanup)
        return ci_map.scan_node(root).get(name, set())

    def test_a_relative_import_out_of_the_package_is_a_read(self):
        self.assertEqual(self.scan("import { A } from '../../site/app/x.js';\n"), {"site/app/x.js"})

    def test_its_own_package_is_not_a_read(self):
        self.assertEqual(self.scan("import { A } from '../src/x.js';\nconst a = join(ROOT, 'src', 'x');\n"), set())

    def test_a_path_named_in_a_string_is_a_read(self):
        self.assertEqual(self.scan("const f = 'tests/test_ui_package.py: the title';\n"), {"tests/test_ui_package.py"})

    def test_a_path_in_a_comment_is_not_a_read(self):
        self.assertEqual(self.scan("// see docs/interface.md and tests/test_x.py\nconst a = 1;\n"), set())

    def test_parent_traversal_in_join_is_a_read_of_the_named_path(self):
        self.assertEqual(self.scan("const t = readFileSync(join(root, 'ui', 'dist', 'index.html'), 'utf8');\n",
                                   "site/test/b.test.mjs"), {"ui/dist/index.html"})


class RealMapTests(unittest.TestCase):
    def test_the_map_loads(self):
        self.assertEqual(DATA["version"], 1)

    def test_nothing_in_the_map_is_stale(self):
        self.assertEqual(ci_map.stale(DATA, REPO, SCANS), [])

    def test_every_test_file_has_an_entry_and_no_entry_is_for_a_missing_file(self):
        have = {p.relative_to(REPO).as_posix() for p in (REPO / "tests").rglob("test*.py")}
        self.assertEqual(set(DATA["python"]), have)
        node = {p.relative_to(REPO).as_posix() for d in ("ui/test", "site/test") for p in (REPO / d).glob("*.test.mjs")}
        self.assertEqual(set(DATA["node"]), node)

    def test_the_starting_points_of_the_guide_are_verified(self):
        py = DATA["python"]
        for f in ("tests/test_checks.py", "tests/test_site_assets.py", "tests/test_site_package.py",
                  "tests/test_ui_package.py", "tests/serve/test_wire.py"):
            self.assertTrue({"ui", "site"} & set(py[f]), f)
        self.assertIn("ui/dist", py["tests/test_ui_package.py"])
        self.assertIn(".kiro", py["tests/test_checks.py"])
        self.assertIn("docs", py["tests/test_docs.py"])
        self.assertIn("README.md", py["tests/test_docs.py"])
        self.assertIn("PROJECT.md", py["tests/test_docs.py"])
        adapters = [f for f, t in py.items() if "adapters" in t]
        kiro = [f for f, t in py.items() if ".kiro" in t]
        self.assertGreaterEqual(len(adapters), 20)
        self.assertGreaterEqual(len(kiro), 3)  # the other .kiro mentions are Kiro's own home folder in temporary roots
        self.assertEqual(sorted(f for f, t in py.items() if "*" in t),
                         ["tests/adapters/test_claude_code.py", "tests/agents/test_claude_acp_package.py"])

    def test_node_tests_that_read_outside_their_package(self):
        node = DATA["node"]
        self.assertIn("tests/test_ui_package.py", node["ui/test/faults.test.mjs"])
        self.assertTrue(any(t.startswith("ui/src") for t in node["site/test/home.test.mjs"]))
        self.assertIn("ui/dist/index.html", node["site/test/home.test.mjs"])
        self.assertEqual(node["ui/test/engine.test.mjs"], [])

    def test_docs_testing_md_holds_the_current_table(self):
        text = (REPO / "docs" / "testing.md").read_text(encoding="utf-8")
        table = ci_map.table_markdown(DATA)
        self.assertTrue(table in text, "docs/testing.md is stale: run `python -m tools.ci_map table` and paste it between the markers")
        self.assertTrue(ci_map.TABLE_BEGIN in text and ci_map.TABLE_END in text)

    def test_no_em_dash_in_the_map_or_tools(self):
        for p in list((REPO / "tools").glob("*")) + [REPO / ".github" / "workflows" / "ci.yml"]:
            if p.is_file() and p.suffix in (".py", ".json", ".yml"):
                self.assertNotIn("\u2014", p.read_text(encoding="utf-8"), p.name)


class PlantedFaultTests(unittest.TestCase):
    """The map must not go stale: each fault below must make the checker fail."""

    def test_PLANTED_FAULT_an_entry_missing_for_a_file_that_reads_ui(self):
        bad = copy.deepcopy(DATA)
        del bad["python"]["tests/test_ui_package.py"]
        problems = ci_map.stale(bad, REPO, SCANS)
        self.assertTrue(any("tests/test_ui_package.py" in p and "no entry" in p for p in problems), problems)

    def test_PLANTED_FAULT_an_entry_that_lacks_ui(self):
        for f in ("tests/test_ui_package.py", "tests/test_checks.py", "tests/serve/test_wire.py", "tests/test_site_assets.py"):
            bad = copy.deepcopy(DATA)
            bad["python"][f] = [t for t in bad["python"][f] if t not in ("ui", "ui/dist")]
            problems = ci_map.stale(bad, REPO, SCANS)
            self.assertTrue(any(f in p and "'ui'" in p for p in problems), (f, problems))

    def test_PLANTED_FAULT_a_node_test_that_reads_a_new_path(self):
        bad = copy.deepcopy(DATA)
        bad["node"]["site/test/home.test.mjs"] = []
        self.assertTrue(any("site/test/home.test.mjs" in p for p in ci_map.stale(bad, REPO, SCANS)))

    def test_PLANTED_FAULT_a_new_test_file_with_no_entry(self):
        tmp, root = tree({"tests/__init__.py": "", "tests/test_new.py": HEAD + 'P = REPO / "ui"\n'})
        self.addCleanup(tmp.cleanup)
        problems = ci_map.stale({**DATA, "python": {}, "node": {}}, root)
        self.assertTrue(any("tests/test_new.py" in p and "no entry" in p for p in problems), problems)

    def test_an_entry_for_a_file_that_is_gone_is_stale(self):
        bad = copy.deepcopy(DATA)
        bad["python"]["tests/test_gone.py"] = []
        self.assertTrue(any("test_gone.py" in p for p in ci_map.stale(bad, REPO, SCANS)))

    def test_an_unknown_token_is_refused_by_the_loader(self):
        bad = copy.deepcopy(DATA)
        bad["python"]["tests/test_rules.py"] = ["somewhere"]
        with self.assertRaises(ci_map.MapError):
            ci_map.validate_map(bad)

    def test_a_bad_shape_is_refused_by_the_loader(self):
        for mutate in (lambda d: d.update(version=2), lambda d: d.pop("routes"), lambda d: d.update(python=[]),
                       lambda d: d["python"].update({"tests/test_rules.py": "ui"}), lambda d: d["routes"][0].update(python="sometimes"),
                       lambda d: d["routes"][0].update(match="")):
            bad = copy.deepcopy(DATA)
            mutate(bad)
            with self.assertRaises(ci_map.MapError):
                ci_map.validate_map(bad)


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "tools.ci_map", *args], cwd=REPO, capture_output=True, text=True)

    def test_check_exits_0_on_the_real_repo(self):
        r = self.run_cli("check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_table_prints_the_table(self):
        r = self.run_cli("table")
        self.assertEqual(r.returncode, 0)
        self.assertIn("tests/test_ui_package.py", r.stdout)

    def test_usage_error_exits_64(self):
        self.assertEqual(self.run_cli("nope").returncode, 64)
        self.assertEqual(self.run_cli().returncode, 64)


if __name__ == "__main__":
    unittest.main()
