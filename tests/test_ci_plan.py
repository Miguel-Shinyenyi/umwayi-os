"""W20: the CI decider (tools/ci_plan.py). A table of changed-file sets and the jobs each must run, and the planted
fault that a filter wrongly skipping Python for a change in umwayi/ is caught."""
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools import ci_map, ci_plan

REPO = Path(__file__).resolve().parent.parent
ALL = ["3.10", "3.11", "3.12", "3.13"]
FEW = ["3.10", "3.13"]
DATA = ci_map.load_map()
ASSIGN = json.loads((REPO / "tools" / "ci_shards.json").read_text(encoding="utf-8"))


def plan(paths, event="pull_request", data=DATA):
    return ci_plan.build_plan(paths, event, data, ASSIGN)


def readers(*paths):
    """The python test files the map says read any of these changed paths (the star readers always)."""
    return sorted(f for f, toks in DATA["python"].items() if any(ci_map.reads_match(t, p) for t in toks for p in paths))


# Each row: name, changed paths, expected (full, python files or "all", python versions, node)
def table(data=DATA):
    r = lambda *p: sorted(f for f, toks in data["python"].items() if any(ci_map.reads_match(t, x) for t in toks for x in p))
    return [
        ("empty diff runs everything", [], (True, "all", ALL, True)),
        ("unreadable diff runs everything", None, (True, "all", ALL, True)),
        ("a workflow change runs everything", [".github/workflows/ci.yml"], (True, "all", ALL, True)),
        ("any .github file runs everything", [".github/CODEOWNERS"], (True, "all", ALL, True)),
        ("the filter script runs everything", ["tools/ci_plan.py"], (True, "all", ALL, True)),
        ("the map file runs everything", ["tools/ci_map.json"], (True, "all", ALL, True)),
        ("the shard file runs everything", ["tools/ci_shards.json"], (True, "all", ALL, True)),
        ("an unknown path runs everything", ["somewhere/new.bin"], (True, "all", ALL, True)),
        ("an unlisted root file runs everything", ["LICENSE"], (True, "all", ALL, True)),
        ("an unknown path next to a ui change runs everything", ["ui/src/main.js", "mystery.txt"], (True, "all", ALL, True)),
        ("a path that climbs out runs everything", ["ui/../umwayi/x.py"], (True, "all", ALL, True)),
        ("an absolute path runs everything", ["/etc/passwd"], (True, "all", ALL, True)),
        ("a wrong case folder is unknown", ["UI/src/main.js"], (True, "all", ALL, True)),
        ("ui only", ["ui/src/main.js"], (False, r("ui/src/main.js"), FEW, True)),
        ("ui dist only", ["ui/dist/index.html"], (False, r("ui/dist/index.html"), FEW, True)),
        ("site only", ["site/app/page.js"], (False, r("site/app/page.js"), FEW, True)),
        ("ui lockfile only", ["ui/package-lock.json"], (False, r("ui/package-lock.json"), FEW, True)),
        ("umwayi only", ["umwayi/cli.py"], (False, "all", ALL, False)),
        ("adapters only", ["adapters/kiro/hook.py"], (False, "all", ALL, False)),
        ("tests only", ["tests/test_rules.py"], (False, "all", ALL, False)),
        ("a test the Node faults test reads", ["tests/test_ui_package.py"], (False, "all", ALL, True)),
        ("pyproject only", ["pyproject.toml"], (False, "all", ALL, False)),
        ("docs only", ["docs/testing.md"], (False, r("docs/testing.md"), FEW, False)),
        ("README only", ["README.md"], (False, r("README.md"), FEW, False)),
        ("PROJECT only", ["PROJECT.md"], (False, r("PROJECT.md"), FEW, False)),
        ("the spec only", [".kiro/specs/umwayi-os/tasks.md"], (False, r(".kiro/specs/umwayi-os/tasks.md"), FEW, False)),
        ("a rename from ui to docs", ["ui/src/a.js", "docs/a.js"], (False, r("ui/src/a.js", "docs/a.js"), FEW, True)),
        ("a rename from umwayi to ui", ["umwayi/a.py", "ui/src/a.py"], (False, "all", ALL, True)),
        ("ui and docs together", ["ui/src/main.js", "docs/testing.md"], (False, r("ui/src/main.js", "docs/testing.md"), FEW, True)),
        ("python and ui together", ["umwayi/cli.py", "ui/src/main.js"], (False, "all", ALL, True)),
        ("a push to main runs everything", ("push", ["docs/testing.md"]), (True, "all", ALL, True)),
        ("any other event runs everything", ("workflow_dispatch", ["docs/testing.md"]), (True, "all", ALL, True)),
    ]


def failures(data):
    """Every row of the table the plan built from this map does not meet. Empty means the filter is right."""
    out = []
    for name, paths, (full, files, versions, node) in table(data):
        event = "pull_request"
        if isinstance(paths, tuple):
            event, paths = paths
        got = ci_plan.build_plan(paths, event, data, ASSIGN)
        want_files = None if files == "all" else files
        have = (got["full"], got["python"]["files"], got["python"]["versions"], got["node"])
        if have != (full, want_files, versions, node):
            out.append(f"{name}: got {have[0], have[2], have[3], None if have[1] is None else len(have[1])}, "
                       f"wanted {full, versions, node, None if want_files is None else len(want_files)}")
    return out


class TableTests(unittest.TestCase):
    def test_every_row_of_the_table(self):
        self.assertEqual(failures(DATA), [])

    def test_every_row_has_a_distinct_name(self):
        names = [row[0] for row in table()]
        self.assertEqual(len(names), len(set(names)))

    def test_the_readers_of_ui_and_site_are_the_ones_the_guide_found(self):
        got = readers("ui/src/main.js", "site/app/page.js")
        for f in ("tests/test_checks.py", "tests/test_site_assets.py", "tests/test_site_package.py",
                  "tests/test_ui_package.py", "tests/serve/test_wire.py"):
            self.assertIn(f, got)
        self.assertNotIn("tests/test_whole_system.py", got)
        self.assertNotIn("tests/test_rules.py", got)

    def test_a_ui_change_skips_most_of_the_python_suite(self):
        p = plan(["ui/src/main.js"])
        self.assertLess(len(p["python"]["files"]), len(DATA["python"]) // 2)
        self.assertIn("tests/test_ui_package.py", p["python"]["files"])

    def test_docs_change_runs_the_doc_tests(self):
        self.assertIn("tests/test_docs.py", plan(["docs/queue.md"])["python"]["files"])

    def test_no_node_job_for_a_python_only_change(self):
        for path in ("umwayi/cli.py", "adapters/kiro/hook.py", "tests/test_rules.py", "docs/queue.md"):
            self.assertFalse(plan([path])["node"], path)


class PlanShapeTests(unittest.TestCase):
    def test_full_plan_matrix_is_every_version_and_every_shard(self):
        p = plan([])
        n = ASSIGN["shards"]
        self.assertEqual(len(p["matrix"]["include"]), len(ALL) * n)
        self.assertEqual({(m["python-version"], m["shard"], m["of"]) for m in p["matrix"]["include"]},
                         {(v, s, n) for v in ALL for s in range(1, n + 1)})
        self.assertEqual(p["not_run"], [])

    def test_partial_plan_says_what_was_not_run(self):
        p = plan(["ui/src/main.js"])
        text = "\n".join(p["not_run"])
        self.assertIn("3.11", text)
        self.assertIn("3.12", text)
        self.assertIn("python test files", text)
        self.assertTrue(p["reason"])

    def test_a_skipped_node_job_is_reported_as_not_run(self):
        self.assertTrue(any("node" in line for line in plan(["umwayi/cli.py"])["not_run"]))

    def test_partial_matrix_has_only_shards_with_a_selected_file(self):
        p = plan(["site/app/page.js"])
        shards = {ASSIGN["files"][f]["shard"] for f in p["python"]["files"]}
        self.assertEqual({m["shard"] for m in p["matrix"]["include"]}, shards)
        self.assertEqual({m["python-version"] for m in p["matrix"]["include"]}, set(FEW))

    def test_plan_is_json_and_one_line_for_github_output(self):
        s = ci_plan.dumps(plan(["docs/queue.md"]))
        self.assertNotIn("\n", s)
        self.assertEqual(json.loads(s)["schema"], 1)

    def test_the_plan_carries_no_changed_path(self):
        p = ci_plan.dumps(plan(["docs/queue.md", "evil\";echo$(id).txt"]))
        self.assertNotIn("evil", p)
        self.assertNotIn("echo", p)

    def test_the_same_paths_in_any_order_give_the_same_plan(self):
        a = ci_plan.dumps(plan(["docs/queue.md", "ui/src/main.js", "umwayi/a.py"]))
        b = ci_plan.dumps(plan(["umwayi/a.py", "ui/src/main.js", "docs/queue.md", "docs/queue.md"]))
        self.assertEqual(a, b)

    def test_an_unreadable_diff_names_the_reason(self):
        self.assertIn("diff", plan(None)["reason"])


class ParseTests(unittest.TestCase):
    def test_rename_gives_both_paths(self):
        raw = b"R100\0ui/src/a.js\0docs/a.js\0M\0umwayi/x.py\0A\0new.txt\0D\0gone.txt\0"
        self.assertEqual(ci_plan.parse_name_status(raw), ["ui/src/a.js", "docs/a.js", "umwayi/x.py", "new.txt", "gone.txt"])

    def test_copy_gives_both_paths(self):
        self.assertEqual(ci_plan.parse_name_status(b"C75\0a\0b\0"), ["a", "b"])

    def test_empty_output_is_an_empty_list(self):
        self.assertEqual(ci_plan.parse_name_status(b""), [])

    def test_malformed_output_raises(self):
        for raw in (b"R100\0only-one\0", b"M", b"Z\0x\0", b"M\0a\0junk", b"\0\0"):
            with self.assertRaises(ValueError, msg=raw):
                ci_plan.parse_name_status(raw)

    def test_path_with_odd_characters_is_kept(self):
        self.assertEqual(ci_plan.parse_name_status("M\0ui/caf\u00e9 \"x\".js\0".encode()), ['ui/caf\u00e9 "x".js'])


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                               "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}).stdout


class GitDiffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="umwayi-ciplan-")
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        git(self.dir, "init", "-q", "-b", "main")
        (self.dir / "ui" / "src").mkdir(parents=True)
        (self.dir / "ui" / "src" / "a.js").write_text("export const a = 1;\n" * 30)
        (self.dir / "x.txt").write_text("x\n")
        git(self.dir, "add", "-A")
        git(self.dir, "commit", "-q", "-m", "one")
        self.base = git(self.dir, "rev-parse", "HEAD").strip()

    def test_a_rename_across_areas_reports_both_sides(self):
        (self.dir / "docs").mkdir()
        git(self.dir, "mv", "ui/src/a.js", "docs/a.js")
        git(self.dir, "commit", "-q", "-m", "two")
        paths = ci_plan.changed_paths(self.base, "HEAD", self.dir)
        self.assertEqual(sorted(paths), ["docs/a.js", "ui/src/a.js"])
        p = ci_plan.build_plan(paths, "pull_request", DATA, ASSIGN)
        self.assertTrue(p["node"])
        self.assertFalse(p["full"])

    def test_no_change_gives_an_empty_list_which_runs_everything(self):
        paths = ci_plan.changed_paths(self.base, "HEAD", self.dir)
        self.assertEqual(paths, [])
        self.assertTrue(ci_plan.build_plan(paths, "pull_request", DATA, ASSIGN)["full"])

    def test_an_unknown_base_is_none_which_runs_everything(self):
        self.assertIsNone(ci_plan.changed_paths("0" * 40, "HEAD", self.dir))
        self.assertTrue(ci_plan.build_plan(None, "pull_request", DATA, ASSIGN)["full"])

    def test_not_a_repository_is_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(ci_plan.changed_paths("HEAD", "HEAD", d))

    def test_a_revision_that_looks_like_an_option_is_refused(self):
        self.assertIsNone(ci_plan.changed_paths("--output=/tmp/x", "HEAD", self.dir))


class CliTests(unittest.TestCase):
    def run_cli(self, *args, env=None):
        e = {**os.environ}
        e.pop("GITHUB_OUTPUT", None)
        e.update(env or {})
        return subprocess.run([sys.executable, "-m", "tools.ci_plan", *args], cwd=REPO, capture_output=True, text=True, env=e)

    def test_push_prints_a_full_plan_and_exits_0(self):
        r = self.run_cli("--event", "push")
        self.assertEqual(r.returncode, 0, r.stderr)
        p = json.loads(r.stdout)
        self.assertTrue(p["full"])
        self.assertEqual(p["python"]["versions"], ALL)
        self.assertTrue(p["node"])

    def test_pull_request_without_a_base_runs_everything(self):
        r = self.run_cli("--event", "pull_request")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(json.loads(r.stdout)["full"])

    def test_bad_arguments_exit_64(self):
        for args in (["--event"], ["--event", "x", "--nope"], ["--event", "push", "extra"], []):
            self.assertEqual(self.run_cli(*args).returncode, 64, args)

    def test_github_output_gets_one_line_per_value(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out"
            r = self.run_cli("--event", "push", "--github-output", str(out))
            self.assertEqual(r.returncode, 0, r.stderr)
            lines = out.read_text().splitlines()
            keys = [ln.split("=", 1)[0] for ln in lines]
            self.assertEqual(keys, ["plan", "matrix", "python", "node"])
            self.assertEqual(lines[2], "python=true")
            self.assertEqual(lines[3], "node=true")
            self.assertEqual(json.loads(lines[1].split("=", 1)[1])["include"][0]["python-version"], "3.10")

    def test_a_real_diff_in_this_checkout(self):
        r = self.run_cli("--event", "pull_request", "--base", "HEAD", "--head", "HEAD")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(json.loads(r.stdout)["full"], "an empty diff runs everything")


class PlantedFaultTests(unittest.TestCase):
    """Planted fault: a filter that wrongly skips Python for a change in umwayi/. The table must catch it, and the
    map loader must refuse a map that says it."""

    def mutated(self, python):
        data = copy.deepcopy(DATA)
        for route in data["routes"]:
            if route["match"] == "umwayi/":
                route["python"] = python
        return data

    def test_the_table_catches_a_skip_of_python_for_umwayi(self):
        for python in ("none", "map"):
            bad = failures(self.mutated(python))
            self.assertTrue(any("umwayi only" in f for f in bad), (python, bad))

    def test_the_map_loader_refuses_it(self):
        for python in ("none", "map"):
            with self.assertRaises(ci_map.MapError, msg=python):
                ci_map.validate_map(self.mutated(python))

    def test_a_missing_default_route_is_refused(self):
        data = copy.deepcopy(DATA)
        data["default"] = {"python": "none", "node": False}
        with self.assertRaises(ci_map.MapError):
            ci_map.validate_map(data)

    def test_a_filter_that_drops_the_floor_prefixes_is_refused(self):
        for prefix in ("tests/", "adapters/", ".github/", "tools/"):
            data = copy.deepcopy(DATA)
            data["routes"] = [r for r in data["routes"] if r["match"] != prefix]
            with self.assertRaises(ci_map.MapError, msg=prefix):
                ci_map.validate_map(data)


if __name__ == "__main__":
    unittest.main()
