"""W21 goldens: what the tools did before W21 changed anything.

These pin the behaviour that W21 must keep: the bytes `ci_shards balance` writes, the words of `ci_shards check`, the
table `ci_map table` prints, the layout of the two json files, and how the docs builder numbers an unnumbered limits
part. They were written and committed before any W21 change. Standard library only.
"""
import io
import json
import re
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

from tools import ci_map
from umwayi import goaldocs

REPO = Path(__file__).resolve().parents[1]
TEST_BODY = "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_x(self):\n        pass\n"
BALANCED = """{
 "files": {
  "tests/test_a.py": {
   "seconds": 5.0,
   "shard": 1
  },
  "tests/test_b.py": {
   "seconds": 3.0,
   "shard": 2
  },
  "tests/test_c.py": {
   "seconds": 3.0,
   "shard": 2
  },
  "tests/test_d.py": {
   "seconds": 1.0,
   "shard": 1
  }
 },
 "shards": 2
}
"""


def run(module, *args, cwd=REPO):
    return subprocess.run([sys.executable, "-m", module, *args], cwd=cwd, capture_output=True, text=True,
                          env={"PYTHONPATH": str(REPO), "PATH": "/usr/bin:/bin:/usr/local/bin"})


class ShardGoldens(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "tests").mkdir()
        (self.root / "tests" / "__init__.py").write_text("")
        for n in "abcd":
            (self.root / "tests" / f"test_{n}.py").write_text(TEST_BODY)
        (self.root / "times.json").write_text('{"tests/test_a.py": 5, "tests/test_b.py": 3, "tests/test_c.py": 3}')
        self.addCleanup(self.tmp.cleanup)

    def test_balance_writes_these_exact_bytes(self):
        r = run("tools.ci_shards", "balance", "--times", str(self.root / "times.json"), "--shards", "2", "--root", str(self.root))
        self.assertEqual((r.returncode, r.stdout), (0, BALANCED))

    def test_balance_out_writes_the_same_bytes_as_stdout(self):
        out = self.root / "out.json"
        r = run("tools.ci_shards", "balance", "--times", str(self.root / "times.json"), "--shards", "2",
                "--root", str(self.root), "--out", str(out))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(out.read_text(), BALANCED)

    def test_check_passes_on_the_balanced_file_and_says_so(self):
        (self.root / "a.json").write_text(BALANCED)
        r = run("tools.ci_shards", "check", "--assignments", str(self.root / "a.json"), "--root", str(self.root))
        self.assertEqual((r.returncode, r.stdout), (0, "ci_shards: every test file is in exactly one shard\n"))

    def test_check_names_a_file_in_no_shard(self):
        data = json.loads(BALANCED)
        del data["files"]["tests/test_d.py"]
        (self.root / "a.json").write_text(json.dumps(data))
        r = run("tools.ci_shards", "check", "--assignments", str(self.root / "a.json"), "--root", str(self.root))
        self.assertEqual(r.returncode, 2)
        self.assertTrue(r.stderr.startswith("ci_shards: tests/test_d.py is in no shard"), r.stderr)

    def test_check_names_a_listed_file_that_is_gone(self):
        (self.root / "tests" / "test_d.py").unlink()
        (self.root / "a.json").write_text(BALANCED)
        r = run("tools.ci_shards", "check", "--assignments", str(self.root / "a.json"), "--root", str(self.root))
        self.assertEqual(r.returncode, 2)
        self.assertIn("ci_shards: tests/test_d.py is listed in a shard but is not a test file any more", r.stderr)

    def test_the_real_assignment_file_is_the_layout_balance_writes(self):
        text = (REPO / "tools" / "ci_shards.json").read_text(encoding="utf-8")
        self.assertEqual(text, json.dumps(json.loads(text), indent=1, sort_keys=True) + "\n")
        self.assertEqual(sorted(json.loads(text)), ["files", "shards"])

    def test_the_usage_error_is_64(self):
        self.assertEqual(run("tools.ci_shards", "nonsense").returncode, 64)


class MapGoldens(unittest.TestCase):
    def test_the_table_command_prints_the_block_docs_testing_md_holds(self):
        r = run("tools.ci_map", "table")
        self.assertEqual(r.returncode, 0)
        self.assertTrue(r.stdout.startswith(ci_map.TABLE_BEGIN + "\n"))
        self.assertTrue(r.stdout.endswith(ci_map.TABLE_END + "\n"))
        self.assertIn(r.stdout.rstrip("\n"), (REPO / "docs" / "testing.md").read_text(encoding="utf-8"))

    def test_check_says_the_map_is_true(self):
        r = run("tools.ci_map", "check")
        self.assertEqual((r.returncode, r.stdout), (0, "ci_map: the map is true\n"))

    def test_the_map_file_keeps_one_entry_per_line(self):
        text = (REPO / "tools" / "ci_map.json").read_text(encoding="utf-8")
        data = json.loads(text)
        self.assertEqual(list(data), ["version", "note", "routes", "default", "python", "node"])
        self.assertIn(' "python": {\n  "tests/adapters/test_claude_code.py": ["*", "adapters"],\n', text)
        self.assertTrue(text.endswith("\n"))
        self.assertEqual(len(data["python"]), len(set(data["python"])))


class DocsGoldens(unittest.TestCase):
    def copy(self):
        """The committed files of the repository (the docs links point at many of them) in a temporary folder."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        archive = subprocess.run(["git", "archive", "HEAD"], cwd=REPO, capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(root)
        return root

    def test_a_clean_copy_is_up_to_date_and_a_build_changes_nothing(self):
        root = self.copy()
        self.assertEqual(goaldocs.check(root).code, 0)
        before = {p: p.read_bytes() for p in (root / "docs-parts").rglob("*.md")}
        before[root / "docs" / "status-log.md"] = (root / "docs" / "status-log.md").read_bytes()
        before[root / "docs" / "KNOWN-LIMITS.md"] = (root / "docs" / "KNOWN-LIMITS.md").read_bytes()
        self.assertEqual(goaldocs.build(root).code, 0)
        self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_an_unnumbered_limits_part_gets_the_next_number_in_its_own_file(self):
        root = self.copy()
        last = max(int(x) for x in re.findall(r"^### (\d+)\.", (root / "docs" / "KNOWN-LIMITS.md").read_text(encoding="utf-8"), re.M))
        part = root / "docs-parts" / "known-limits" / "Z-new.md"
        part.write_text("section: Z section\ntitle: A new limit\n\nThe body.\n", encoding="utf-8")
        (root / "docs-parts" / "status-log" / "Z-new.md").write_text(
            "date: 2026-11-14\npr: none\nwhat: A new task.\ntests: none\n", encoding="utf-8")
        self.assertEqual(goaldocs.check(root).code, 2)
        self.assertEqual(goaldocs.build(root).code, 0)
        self.assertIn(f"number: {last + 1}\n", part.read_text(encoding="utf-8"))
        self.assertIn(f"### {last + 1}. A new limit", (root / "docs" / "KNOWN-LIMITS.md").read_text(encoding="utf-8"))
        self.assertEqual(goaldocs.check(root).code, 0)


if __name__ == "__main__":
    unittest.main()
