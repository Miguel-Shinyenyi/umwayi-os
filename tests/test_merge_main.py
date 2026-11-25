"""W21: `python -m tools.merge_main` against real git in temporary folders.

Every scenario has a bare repository as origin (a folder on disk, no network) and two clones, A and B, that stand for two
parallel sessions. The repository under test is the committed tree of this repository, with the W21 tools laid over it, made
consistent once per class. A pushes first (the test does the push, merge_main never does); then B runs merge_main.

The ui scenarios need node and npm. When node is missing they are skipped and the reason is printed; CI has node.
Standard library only, and no network except what `npm ci` itself needs.
"""
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
       "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid", "GIT_COMMITTER_NAME": "Test",
       "GIT_COMMITTER_EMAIL": "test@example.invalid", "PYTHONDONTWRITEBYTECODE": "1"}
HAS_NODE = bool(shutil.which("node") and shutil.which("npm"))
NEEDS_NODE = unittest.skipUnless(HAS_NODE, "node or npm is missing, so the ui scenarios are skipped (CI has node)")
if not HAS_NODE:
    print("test_merge_main: SKIPPED the ui scenarios because node or npm is missing", file=sys.stderr)
TEST_BODY = "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_x(self):\n        pass\n"


def git(cwd, *args, check=True, env=None):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=env or ENV)
    if check and r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {cwd}: {r.stderr}")
    return r


def snapshot(root):
    """Every file under the work tree (not .git) with its hash, plus HEAD and the porcelain status."""
    files = {}
    for p in sorted(Path(root).rglob("*")):
        rel = p.relative_to(root).as_posix()
        if rel == ".git" or rel.startswith(".git/") or "node_modules" in p.parts or not p.is_file():
            continue
        files[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return {"files": files, "head": git(root, "rev-parse", "HEAD").stdout, "status": git(root, "status", "--porcelain").stdout}


def put(repo, files, message):
    for rel, text in files.items():
        p = Path(repo) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    git(repo, "add", "--", *files)
    git(repo, "commit", "-qm", message)


def status_part(date="2026-11-14"):
    return f"date: {date}\npr: none\nwhat: {{what}}\ntests: none\n"


def limits_part(section, title):
    return f"section: {section}\ntitle: {title}\n\nA body for {title}.\n"


_SEED = {}


def build_seed():
    """The committed tree of this repository with the W21 tools laid over it, made consistent and committed as `main`.
    Built once for the whole module (W47c): every test only clones it (into a bare origin), so no test can change it."""
    if "path" not in _SEED:
        _SEED["dir"] = tempfile.TemporaryDirectory(prefix="umwayi-mm-")
        _SEED["path"] = _make_seed(Path(_SEED["dir"].name))
    return _SEED["path"]


def tearDownModule():
    if "dir" in _SEED:
        _SEED.pop("dir").cleanup()
        _SEED.pop("path", None)


def _make_seed(base):
    seed = base / "seed"
    seed.mkdir()
    archive = subprocess.run(["git", "archive", "HEAD"], cwd=REPO, capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(seed)
    for name in ("generated_files.py", "generated_files.json", "merge_main.py", "ci_map.py", "ci_shards.py", "ci_map_table.md"):
        shutil.copy2(REPO / "tools" / name, seed / "tools" / name)
    for args in (("tools.ci_map", "update"), ("tools.ci_shards", "assign-missing"), ("tools.ci_shards", "rebalance"), ("tools.ci_map", "table", "--write")):
        r = subprocess.run([sys.executable, "-m", *args], cwd=seed, capture_output=True, text=True, env=ENV)
        assert r.returncode == 0, (args, r.stderr)
    git(seed, "init", "-q", "-b", "main")
    git(seed, "add", "-A")
    git(seed, "commit", "-qm", "seed")
    return seed


class MergeMainBase(unittest.TestCase):
    seed = None

    @classmethod
    def setUpClass(cls):
        cls.seed = build_seed()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="umwayi-mm-case-")
        self.addCleanup(self.tmp.cleanup)
        tmp = Path(self.tmp.name)
        self.origin = tmp / "origin.git"
        git(tmp, "clone", "-q", "--bare", str(self.seed), str(self.origin))
        self.a, self.b = tmp / "a", tmp / "b"
        for repo, branch in ((self.a, "branch-a"), (self.b, "branch-b")):
            git(tmp, "clone", "-q", str(self.origin), str(repo))
            git(repo, "checkout", "-q", "-b", branch)
        self.gitlog = tmp / "git.log"
        fake = tmp / "fakebin"
        fake.mkdir()
        real = shutil.which("git")
        (fake / "git").write_text(f'#!/bin/sh\necho "$@" >> "{self.gitlog}"\nexec "{real}" "$@"\n')
        (fake / "git").chmod(0o755)
        self.fakebin = fake

    def merge_main(self, repo, path=None, check_log=True):
        env = {**ENV, "PATH": f"{self.fakebin}{os.pathsep}{path if path is not None else ENV['PATH']}"}
        r = subprocess.run([sys.executable, "-m", "tools.merge_main"], cwd=repo, capture_output=True, text=True, env=env, timeout=900)
        if check_log and self.gitlog.exists():
            for line in self.gitlog.read_text().splitlines():
                words = line.split()
                self.assertFalse({"push", "reset", "clean", "--force", "-f"} & set(words), f"merge_main ran git {line}")
        return r

    def py(self, repo, *args):
        return subprocess.run([sys.executable, "-m", *args], cwd=repo, capture_output=True, text=True, env=ENV)

    def land(self, repo):
        """What the owner does after a session: the branch becomes main on origin."""
        git(repo, "push", "-q", "origin", "HEAD:main")

    def assertUntouched(self, repo, before, r, code):
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        self.assertEqual(snapshot(repo), before)
        self.assertFalse((Path(repo) / ".git" / "MERGE_HEAD").exists())

    def advance_main(self, files, message="main moves"):
        put(self.a, files, message)
        self.land(self.a)


class NothingToDoTests(MergeMainBase):
    def test_a_clean_up_to_date_tree_is_kept_and_nothing_is_committed(self):
        head = git(self.b, "rev-parse", "HEAD").stdout
        r = self.merge_main(self.b)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(git(self.b, "rev-parse", "HEAD").stdout, head)
        for path in ("docs/status-log.md", "docs/KNOWN-LIMITS.md", "tools/ci_map.json", "tools/ci_shards.json", "tools/ci_map_table.md",
                     "ui/dist/build.json"):
            self.assertRegex(r.stdout, rf"(?m)^kept {re.escape(path)}: ")
        self.assertIn("already merged", r.stdout)

    def test_a_branch_behind_main_gets_a_merge_commit_and_no_second_commit(self):
        self.advance_main({"README.md": (self.a / "README.md").read_text(encoding="utf-8") + "\nA line from main.\n"})
        r = self.merge_main(self.b)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(git(self.b, "log", "-1", "--format=%P").stdout.split()), 2)
        self.assertTrue(git(self.b, "log", "-1", "--format=%s").stdout.startswith("Merge"))
        self.assertEqual(git(self.b, "status", "--porcelain").stdout, "")
        self.assertIn("A line from main.", (self.b / "README.md").read_text(encoding="utf-8"))


class PartsTests(MergeMainBase):
    """Two branches that each add a status part and a limits part, and never run the build themselves."""

    def add_parts(self, repo, name, section):
        put(repo, {f"docs-parts/status-log/{name}.md": status_part().format(what=f"Task {name} is done."),
                   f"docs-parts/known-limits/{name}.md": limits_part(section, f"Limit of {name}")}, f"parts {name}")

    def test_two_branches_that_both_add_parts_get_both_rows_once_and_distinct_numbers_in_order(self):
        self.add_parts(self.a, "Wa-one", "Section one")
        self.add_parts(self.b, "Wb-two", "Section two")
        ra = self.merge_main(self.a)
        self.assertEqual(ra.returncode, 0, ra.stdout + ra.stderr)
        self.land(self.a)
        rb = self.merge_main(self.b)
        self.assertEqual(rb.returncode, 0, rb.stdout + rb.stderr)
        self.assertRegex(rb.stdout, r"(?m)^regenerated docs/status-log.md: ")
        self.assertRegex(rb.stdout, r"(?m)^regenerated docs/KNOWN-LIMITS.md: ")
        status = (self.b / "docs" / "status-log.md").read_text(encoding="utf-8")
        limits = (self.b / "docs" / "KNOWN-LIMITS.md").read_text(encoding="utf-8")
        self.assertEqual(status.count("Task Wa-one is done."), 1)
        self.assertEqual(status.count("Task Wb-two is done."), 1)
        numbers = {t: int(m.group(1)) for t in ("Limit of Wa-one", "Limit of Wb-two")
                   for m in [re.search(rf"^### (\d+)\. {t}$", limits, re.M)]}
        for title in ("Limit of Wa-one", "Limit of Wb-two"):
            self.assertEqual(len(re.findall(rf"^### \d+\. {title}$", limits, re.M)), 1)
        self.assertEqual(numbers["Limit of Wb-two"], numbers["Limit of Wa-one"] + 1)
        self.assertLess(limits.index("Limit of Wa-one"), limits.index("Limit of Wb-two"))
        self.assertEqual(self.py(self.b, "umwayi", "goal", "docs", "check").returncode, 0)
        self.assertEqual(git(self.b, "status", "--porcelain").stdout, "")
        subjects = git(self.b, "log", "--format=%s", "-3").stdout.splitlines()
        self.assertEqual(subjects[0], "regenerate generated files after merging main")
        self.assertTrue(subjects[1].startswith("Merge"), subjects)

    def test_w47a_two_branches_that_both_built_their_limits_part_get_distinct_numbers(self):
        # what happened on W26, W27, W33 and W37: each branch ran the build, so both parts carry the same number
        for repo, name in ((self.a, "Wa-one"), (self.b, "Wb-two")):
            self.add_parts(repo, name, f"Section {name}")
            self.assertEqual(self.py(repo, "umwayi", "goal", "docs", "build").returncode, 0)
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", f"built {name}")
        same = [re.search(r"^number: (\d+)$", (r / "docs-parts" / "known-limits" / f"{n}.md").read_text(), re.M).group(1)
                for r, n in ((self.a, "Wa-one"), (self.b, "Wb-two"))]
        self.assertEqual(same[0], same[1])
        self.land(self.a)
        main_part = (self.a / "docs-parts" / "known-limits" / "Wa-one.md").read_bytes()
        r = self.merge_main(self.b)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout, rf"(?m)^renumbered docs-parts/known-limits/Wb-two.md: number {same[0]} is taken on main; ")
        self.assertEqual((self.b / "docs-parts" / "known-limits" / "Wa-one.md").read_bytes(), main_part)  # main's kept
        mine = re.search(r"^number: (\d+)$", (self.b / "docs-parts" / "known-limits" / "Wb-two.md").read_text(), re.M)
        self.assertEqual(int(mine.group(1)), int(same[0]) + 1)
        limits = (self.b / "docs" / "KNOWN-LIMITS.md").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(rf"^### {same[0]}\. ", limits, re.M)), 1)
        self.assertEqual(self.py(self.b, "umwayi", "goal", "docs", "check").returncode, 0)
        self.assertEqual(git(self.b, "status", "--porcelain").stdout, "")

    def test_w47a_a_branch_number_that_does_not_clash_is_left_alone(self):
        self.add_parts(self.b, "Wb-two", "Section two")
        self.assertEqual(self.py(self.b, "umwayi", "goal", "docs", "build").returncode, 0)
        git(self.b, "add", "-A")
        git(self.b, "commit", "-qm", "built")
        before = (self.b / "docs-parts" / "known-limits" / "Wb-two.md").read_bytes()
        self.advance_main({"README.md": (self.a / "README.md").read_text(encoding="utf-8") + "\nmain moves\n"})
        r = self.merge_main(self.b)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("renumbered", r.stdout)
        self.assertEqual((self.b / "docs-parts" / "known-limits" / "Wb-two.md").read_bytes(), before)

    def test_a_conflict_in_the_status_log_is_cleared_by_the_build(self):
        # both branches ran the build for their own status part, so docs/status-log.md conflicts
        for repo, name in ((self.a, "Wa-one"), (self.b, "Wb-two")):
            put(repo, {f"docs-parts/status-log/{name}.md": status_part().format(what=f"Task {name} is done.")}, f"part {name}")
            self.assertEqual(self.py(repo, "umwayi", "goal", "docs", "build").returncode, 0)
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", f"built {name}")
        self.land(self.a)
        r = self.merge_main(self.b)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"(?m)^regenerated docs/status-log.md: main's version taken")
        status = (self.b / "docs" / "status-log.md").read_text(encoding="utf-8")
        self.assertNotIn("<<<<<<<", status)
        self.assertEqual((status.count("Task Wa-one is done."), status.count("Task Wb-two is done.")), (1, 1))
        self.assertEqual(self.py(self.b, "umwayi", "goal", "docs", "check").returncode, 0)
        self.assertEqual(git(self.b, "status", "--porcelain").stdout, "")
        self.assertEqual(len(git(self.b, "log", "-1", "--format=%P").stdout.split()), 2)  # one merge commit


class TestFileTests(MergeMainBase):
    def new_test(self, repo, name):
        put(repo, {f"tests/{name}": TEST_BODY}, f"add {name}")

    def checks(self, repo):
        for args in (("tools.ci_shards", "check"), ("tools.ci_map", "check"), ("tools.ci_map", "table", "--check")):
            r = self.py(repo, *args)
            self.assertEqual(r.returncode, 0, (args, r.stdout, r.stderr))

    def assertListedOnce(self, repo, *names):
        data = json.loads((repo / "tools" / "ci_shards.json").read_text(encoding="utf-8"))
        text = (repo / "tools" / "ci_shards.json").read_text(encoding="utf-8")
        for n in names:
            self.assertIn(f"tests/{n}", data["files"])
            self.assertEqual(text.count(f'"tests/{n}"'), 1)

    def test_two_branches_that_both_add_a_test_file_list_both_once(self):
        self.new_test(self.a, "test_w21_one.py")
        self.new_test(self.b, "test_w21_two.py")
        self.assertEqual(self.merge_main(self.a).returncode, 0)
        self.land(self.a)
        r = self.merge_main(self.b)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"(?m)^regenerated tools/ci_shards.json: stale")
        self.assertListedOnce(self.b, "test_w21_one.py", "test_w21_two.py")
        self.checks(self.b)
        self.assertEqual(git(self.b, "status", "--porcelain").stdout, "")

    def test_two_branches_that_each_updated_the_generated_files_by_hand_conflict_and_are_cleared(self):
        for repo, name in ((self.a, "test_w21_one.py"), (self.b, "test_w21_two.py")):
            self.new_test(repo, name)
            for args in (("tools.ci_shards", "assign-missing"), ("tools.ci_shards", "rebalance"), ("tools.ci_map", "update"), ("tools.ci_map", "table", "--write")):
                self.assertEqual(self.py(repo, *args).returncode, 0)
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", f"generated for {name}")
        self.land(self.a)
        r = self.merge_main(self.b)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for path in ("tools/ci_shards.json", "tools/ci_map_table.md"):
            text = (self.b / path).read_text(encoding="utf-8")
            self.assertNotIn("<<<<<<<", text, path)
        self.assertListedOnce(self.b, "test_w21_one.py", "test_w21_two.py")
        self.checks(self.b)
        self.assertEqual(git(self.b, "status", "--porcelain").stdout, "")
        self.assertEqual(len(git(self.b, "log", "-1", "--format=%P").stdout.split()), 2)

    def test_a_deleted_test_file_loses_its_entry(self):
        victim = "tests/test_exit_codes.py"
        git(self.b, "rm", "-q", victim)
        git(self.b, "commit", "-qm", "delete a test file")
        self.advance_main({"README.md": (self.a / "README.md").read_text(encoding="utf-8") + "\nA line.\n"})
        r = self.merge_main(self.b)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn(victim, json.loads((self.b / "tools" / "ci_shards.json").read_text(encoding="utf-8"))["files"])
        self.checks(self.b)


class UiTests(MergeMainBase):
    def build_ui(self, repo):
        for argv in (["npm", "ci", "--ignore-scripts"], ["node", "build.mjs"]):
            r = subprocess.run(argv, cwd=repo / "ui", capture_output=True, text=True, env=ENV)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def two_branches_that_changed_ui_sources(self):
        """A changes one ui source and rebuilds, then lands. B changes another and does not rebuild: its build.json is stale."""
        for repo, name, rebuild in ((self.a, "ease", True), (self.b, "tier", False)):
            path = repo / "ui" / "src" / "engine" / f"{name}.js"
            path.write_text(path.read_text(encoding="utf-8") + f"\n// W22 test line in {name}\n", encoding="utf-8")
            if rebuild:
                self.build_ui(repo)
            git(repo, "add", "-A")
            git(repo, "commit", "-qm", f"change {name}")
        self.land(self.a)

    @NEEDS_NODE
    def test_two_branches_that_both_change_ui_sources_get_build_json_regenerated(self):
        self.two_branches_that_changed_ui_sources()
        self.assertNotEqual(self.py(self.b, "unittest", "tests.test_ui_package").returncode, 0)  # B did not rebuild
        r = self.merge_main(self.b)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"(?m)^regenerated ui/dist/build.json: .*; ran npm ci --ignore-scripts \(in ui/\) then node build.mjs")
        data = json.loads((self.b / "ui" / "dist" / "build.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(data), ["cliMapPage", "files", "goalMapPage", "page"])  # no hash of the progress page (W38 added the committed goal map page)
        self.assertEqual(self.py(self.b, "unittest", "tests.test_ui_package").returncode, 0)
        self.assertEqual(git(self.b, "status", "--porcelain").stdout, "")  # the built progress page is ignored, not committed

    def test_node_missing_is_exit_3_and_the_tree_is_as_it_was(self):
        # a stale build.json needs node to regenerate. The scenario is built with the real node, run without it.
        if not HAS_NODE:
            self.skipTest("node is missing, so the conflict cannot be built here (CI has node)")
        self.two_branches_that_changed_ui_sources()
        before = snapshot(self.b)
        bare = Path(self.tmp.name) / "bare-path"
        bare.mkdir()
        (bare / "git").symlink_to(shutil.which("git"))
        r = self.merge_main(self.b, path=str(bare))
        self.assertUntouched(self.b, before, r, 3)
        self.assertIn("is not installed", r.stderr)
        self.assertIn("node and npm", r.stderr)


class RefusalTests(MergeMainBase):
    def test_a_conflict_in_a_file_that_is_not_generated_aborts_and_changes_nothing(self):
        readme = (self.a / "README.md").read_text(encoding="utf-8")
        put(self.a, {"README.md": readme + "\nline from A\n"}, "a edits readme")
        put(self.a, {"docs-parts/status-log/Wa.md": status_part().format(what="Task Wa is done.")}, "a part")
        self.assertEqual(self.py(self.a, "umwayi", "goal", "docs", "build").returncode, 0)
        git(self.a, "add", "-A")
        git(self.a, "commit", "-qm", "a built")
        put(self.b, {"README.md": readme + "\nline from B\n"}, "b edits readme")
        put(self.b, {"docs-parts/status-log/Wb.md": status_part().format(what="Task Wb is done.")}, "b part")
        self.assertEqual(self.py(self.b, "umwayi", "goal", "docs", "build").returncode, 0)
        git(self.b, "add", "-A")
        git(self.b, "commit", "-qm", "b built")
        self.land(self.a)
        before = snapshot(self.b)
        r = self.merge_main(self.b)
        self.assertUntouched(self.b, before, r, 3)
        self.assertIn("refused README.md", r.stderr)
        self.assertIn("Ask me first", r.stderr)
        self.assertNotIn("refused docs/status-log.md", r.stderr)  # a generated file that conflicts too is not what stops it

    def test_a_dirty_tree_is_refused_and_nothing_changes(self):
        self.advance_main({"README.md": (self.a / "README.md").read_text(encoding="utf-8") + "\nmain moves\n"})
        (self.b / "docs" / "testing.md").write_text("edited by the owner\n", encoding="utf-8")
        (self.b / "untracked.txt").write_text("mine\n", encoding="utf-8")
        before = snapshot(self.b)
        r = self.merge_main(self.b)
        self.assertUntouched(self.b, before, r, 3)
        self.assertIn("Ask me first", r.stderr)
        main_tip = git(self.a, "rev-parse", "HEAD").stdout.strip()
        self.assertNotEqual(git(self.b, "cat-file", "-e", main_tip, check=False).returncode, 0)  # not even fetched

    def test_a_staged_change_and_a_detached_head_are_refused(self):
        (self.b / "x.txt").write_text("x\n")
        git(self.b, "add", "x.txt")
        before = snapshot(self.b)
        self.assertUntouched(self.b, before, self.merge_main(self.b), 3)
        git(self.b, "rm", "-qf", "--cached", "x.txt")
        (self.b / "x.txt").unlink()
        git(self.b, "checkout", "-q", "--detach")
        before = snapshot(self.b)
        self.assertUntouched(self.b, before, self.merge_main(self.b), 3)

    def test_arguments_are_a_usage_error(self):
        r = subprocess.run([sys.executable, "-m", "tools.merge_main", "--push"], cwd=self.b, capture_output=True, text=True, env=ENV)
        self.assertEqual(r.returncode, 64)


class FailureTests(MergeMainBase):
    def plant(self, repo, mutate):
        path = repo / "tools" / "generated_files.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        mutate(data)
        put(repo, {"tools/generated_files.json": json.dumps(data, indent=1) + "\n"}, "plant a fault in the list")

    def stale_shards(self):
        """Main moves with a new test file nobody assigned, so ci_shards.json is stale after the merge."""
        self.advance_main({"tests/test_w21_stale.py": TEST_BODY})

    def entry(self, data, path):
        return next(e for e in data["files"] if e["path"] == path)

    def run_planted(self, mutate, code):
        self.stale_shards()
        self.plant(self.b, mutate)
        before = snapshot(self.b)
        r = self.merge_main(self.b)
        self.assertUntouched(self.b, before, r, code)
        return r

    def test_a_failing_regenerate_is_exit_2_and_the_tree_is_restored(self):
        def mutate(d):
            self.entry(d, "tools/ci_shards.json")["regenerate"] = [
                {"argv": ["python", "-c", "print('boom one'); print('boom two'); raise SystemExit(5)"]}]
        r = self.run_planted(mutate, 2)
        self.assertIn("regenerate for tools/ci_shards.json failed", r.stderr)
        self.assertIn("boom two", r.stderr)
        self.assertIn("-c", r.stderr)

    def test_only_the_last_20_lines_of_a_failure_are_printed(self):
        def mutate(d):
            self.entry(d, "tools/ci_shards.json")["regenerate"] = [
                {"argv": ["python", "-c", "[print('line', i) for i in range(100)]; raise SystemExit(1)"]}]
        r = self.run_planted(mutate, 2)
        self.assertIn("line 99", r.stderr)
        self.assertIn("line 80", r.stderr)
        self.assertNotIn("line 79\n", r.stderr)

    def test_a_failing_verify_after_the_regenerate_is_exit_2(self):
        def mutate(d):
            self.entry(d, "tools/ci_shards.json")["verify"] = [{"argv": ["python", "-c", "raise SystemExit(1)"]}]
        r = self.run_planted(mutate, 2)
        self.assertIn("verify for tools/ci_shards.json failed", r.stderr)

    def test_a_list_that_names_a_missing_file_is_exit_64(self):
        def mutate(d):
            d["files"].append({"path": "docs/not-there.md", "regenerate": [{"argv": ["python", "-c", "pass"]}],
                               "verify": [{"argv": ["python", "-c", "pass"]}]})
        r = self.run_planted(mutate, 64)
        self.assertIn("docs/not-there.md", r.stderr)

    def test_a_path_with_dot_dot_is_exit_64(self):
        def mutate(d):
            self.entry(d, "tools/ci_map.json")["path"] = "tools/../tools/ci_map.json"
        self.assertIn("not a plain relative path", self.run_planted(mutate, 64).stderr)

    def test_a_repeated_path_is_exit_64(self):
        def mutate(d):
            d["files"].append(dict(self.entry(d, "tools/ci_map.json")))
        self.assertIn("listed twice", self.run_planted(mutate, 64).stderr)

    def test_an_unknown_key_and_a_shell_are_exit_64(self):
        self.run_planted(lambda d: self.entry(d, "tools/ci_map.json").update({"colour": "red"}), 64)

    def test_a_regenerate_that_writes_a_different_file_than_listed_is_found_by_verify(self):
        def mutate(d):
            self.entry(d, "tools/ci_shards.json")["regenerate"] = [
                {"argv": ["python", "-c", "open('docs/other.txt', 'w').write('x')"]}]
        r = self.run_planted(mutate, 2)
        self.assertIn("verify for tools/ci_shards.json failed", r.stderr)
        self.assertFalse((self.b / "docs" / "other.txt").exists())

    def test_a_file_written_that_is_not_on_the_list_is_found_even_when_verify_passes(self):
        def mutate(d):
            self.entry(d, "tools/ci_shards.json")["regenerate"].append(
                {"argv": ["python", "-c", "open('docs/other.txt', 'w').write('x')"]})
        r = self.run_planted(mutate, 2)
        self.assertIn("docs/other.txt", r.stderr)
        self.assertFalse((self.b / "docs" / "other.txt").exists())


SITE = (
    "import os, sys\n"
    "if sys.orig_argv[1:4] == ['-m', 'unittest', 'tests.test_ui_package']:\n"
    "    count = os.environ['UMWAYI_MM_COUNT']\n"
    "    first = not os.path.exists(count)\n"
    "    open(count, 'a').write('x\\n')\n"
    "    if first and os.environ.get('UMWAYI_MM_TOUCH'):\n"
    "        open('ui/dist/progress.html', 'a').write('<!-- touched while it ran -->')\n"
    "    os._exit(0)\n"
)
RULE = "    return before is not None and now is not None and before == now"


class SkipUiVerifyTests(MergeMainBase):
    """W47d. The final pass skips the ui verify when no file of its path list changed since it passed, and runs it
    otherwise. A stand-in for `python -m unittest tests.test_ui_package` (a sitecustomize in PYTHONPATH) counts the runs
    and passes at once, so no scenario runs the real ui tests. The planted faults are copies of merge_main.py with the
    one rule of `same_state` changed: each must make a scenario fail."""

    def setUp(self):
        super().setUp()
        site = Path(self.tmp.name) / "site"
        site.mkdir()
        (site / "sitecustomize.py").write_text(SITE, encoding="utf-8")
        self.count = Path(self.tmp.name) / "count.txt"
        path = os.pathsep.join(filter(None, [str(site), ENV.get("PYTHONPATH", "")]))
        patch = mock.patch.dict(ENV, {"PYTHONPATH": path, "UMWAYI_MM_COUNT": str(self.count)})
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(lambda: ENV.pop("UMWAYI_MM_TOUCH", None))

    def runs(self):
        return len(self.count.read_text().split()) if self.count.exists() else 0

    def merge_counting(self, repo=None, plant=None):
        repo = repo or self.b
        if plant is not None:
            path = repo / "tools" / "merge_main.py"
            source = path.read_text(encoding="utf-8")
            self.assertIn(RULE, source)
            path.write_text(source.replace(RULE, plant), encoding="utf-8")
            git(repo, "commit", "-qam", "planted fault")
        if self.count.exists():
            self.count.unlink()
        r = self.merge_main(repo)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def touch_while_it_runs(self):
        ENV["UMWAYI_MM_TOUCH"] = "1"

    def unreadable(self):
        os.mkfifo(self.b / "ui" / "dist" / "pipe")  # a file of a kind the state cannot be read from

    # rule 1: a ui file changed, so the verify runs again
    def test_a_ui_file_changed_since_the_verify_passed_runs_it_again(self):
        self.touch_while_it_runs()
        r = self.merge_counting()
        self.assertEqual(self.runs(), 2)
        self.assertNotIn("skipped the last verify", r.stdout)

    def test_planted_fault_always_skip_is_caught_by_the_changed_file_scenario(self):
        self.touch_while_it_runs()
        self.merge_counting(plant="    return True")
        self.assertEqual(self.runs(), 1)  # the scenario above expects 2, so it would fail

    # rule 2: no ui file changed, so the second verify is skipped
    def test_no_ui_file_changed_skips_the_second_verify_and_says_so(self):
        r = self.merge_counting()
        self.assertEqual(self.runs(), 1)
        self.assertRegex(r.stdout, r"(?m)^skipped the last verify of python -m unittest tests\.test_ui_package: ")
        self.assertRegex(r.stdout, r"(?m)^kept ui/dist/build\.json: ")

    def test_planted_fault_never_skip_is_caught_by_the_unchanged_scenario(self):
        self.merge_counting(plant="    return False")
        self.assertEqual(self.runs(), 2)  # the scenario above expects 1, so it would fail

    # rule 3: the tool cannot tell, so the verify runs
    def test_a_state_that_cannot_be_read_does_not_skip(self):
        self.unreadable()
        r = self.merge_counting()
        self.assertEqual(self.runs(), 2)
        self.assertNotIn("skipped the last verify", r.stdout)

    def test_planted_fault_unknown_read_as_unchanged_is_caught_by_the_cannot_tell_scenario(self):
        self.unreadable()
        self.merge_counting(plant="    return before == now")
        self.assertEqual(self.runs(), 1)  # the scenario above expects 2, so it would fail


class StateOfTests(unittest.TestCase):
    """W47d: the path list, the state and the one rule, without a merge."""

    def setUp(self):
        sys.path.insert(0, str(REPO))
        self.addCleanup(sys.path.remove, str(REPO))
        from tools import merge_main
        self.mm = merge_main
        self.tmp = tempfile.TemporaryDirectory(prefix="umwayi-mm-state-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "tools").mkdir()
        self.cmd = {"argv": ["python", "-m", "unittest", "tests.test_x"], "cwd": ""}

    def list_in_ci_map(self, text):
        (self.root / "tools" / "ci_map.json").write_text(text, encoding="utf-8")

    def test_the_path_list_is_the_one_ci_map_holds_for_that_test(self):
        self.list_in_ci_map(json.dumps({"python": {"tests/test_x.py": ["a", "ui"]}}))
        self.assertEqual(self.mm.verify_paths(self.root, self.cmd), ["a", "ui"])
        real = json.loads((REPO / "tools" / "ci_map.json").read_text(encoding="utf-8"))["python"]["tests/test_ui_package.py"]
        self.assertEqual(self.mm.verify_paths(REPO, {"argv": ["python", "-m", "unittest", "tests.test_ui_package"], "cwd": ""}), real)

    def test_no_list_means_cannot_tell(self):
        self.assertIsNone(self.mm.verify_paths(self.root, self.cmd))  # no ci_map.json
        self.list_in_ci_map("{not json")
        self.assertIsNone(self.mm.verify_paths(self.root, self.cmd))
        self.list_in_ci_map(json.dumps({"python": {"tests/test_y.py": ["a"]}}))
        self.assertIsNone(self.mm.verify_paths(self.root, self.cmd))  # no entry for this test
        self.list_in_ci_map(json.dumps({"python": {"tests/test_x.py": []}}))
        self.assertIsNone(self.mm.verify_paths(self.root, self.cmd))
        self.list_in_ci_map(json.dumps({"python": {"tests/test_x.py": ["a"]}}))
        for argv, cwd in ((["python", "-m", "tools.ci_map", "check"], ""), (["node", "build.mjs"], ""),
                          (["python", "-m", "unittest", "tests.test_x"], "ui")):
            self.assertIsNone(self.mm.verify_paths(self.root, {"argv": argv, "cwd": cwd}))

    def test_the_state_changes_with_content_and_not_with_a_rewrite_of_the_same_bytes(self):
        (self.root / "ui").mkdir()
        f = self.root / "ui" / "a.js"
        f.write_text("one", encoding="utf-8")
        before = self.mm.state_of(self.root, ["ui", "missing.txt"])
        f.write_text("one", encoding="utf-8")
        self.assertEqual(self.mm.state_of(self.root, ["ui", "missing.txt"]), before)
        f.write_text("two", encoding="utf-8")
        self.assertNotEqual(self.mm.state_of(self.root, ["ui", "missing.txt"]), before)
        (self.root / "missing.txt").write_text("x", encoding="utf-8")
        self.assertNotEqual(self.mm.state_of(self.root, ["ui", "missing.txt"]), before)

    def test_a_file_of_another_kind_cannot_be_read(self):
        (self.root / "ui").mkdir()
        os.mkfifo(self.root / "ui" / "pipe")
        self.assertIsNone(self.mm.state_of(self.root, ["ui"]))

    def test_only_two_known_equal_states_are_the_same(self):
        self.assertTrue(self.mm.same_state("a", "a"))
        self.assertFalse(self.mm.same_state("a", "b"))
        self.assertFalse(self.mm.same_state(None, None))
        self.assertFalse(self.mm.same_state("a", None))
        self.assertFalse(self.mm.same_state(None, "a"))


class SourceGuardTests(unittest.TestCase):
    def test_merge_main_never_pushes_forces_or_resets(self):
        import ast
        source = (REPO / "tools" / "merge_main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and node.body and isinstance(node.body[0], ast.Expr) \
                    and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
                docstrings.add(id(node.body[0].value))
        words = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings}
        for forbidden in ("push", "reset", "--hard", "--force", "-f", "-fd", "--force-with-lease", "clean", "rebase", "stash"):
            self.assertNotIn(forbidden, words)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
                self.assertNotRegex(node.value, r"\b(push|reset|rebase)\b|--hard|--force|git clean", node.value)

    def test_no_em_dash_in_the_new_files(self):
        for name in ("tools/merge_main.py", "tools/generated_files.py", "tools/generated_files.json", "tests/test_merge_main.py",
                     "tests/test_generated_files.py"):
            self.assertNotIn("\u2014", (REPO / name).read_text(encoding="utf-8"), name)


if __name__ == "__main__":
    unittest.main()
