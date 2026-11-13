"""W9.6b: the worktree per task (W9.R8.1 and W9.R8.9 to W9.R8.16), `agent run --workdir` and `agent check --workdir`.

One group per point of the requirements, each with its planted faults. A planted fault is a replaced function; the
group's own check must fail on it (`caught`), so a test that cannot fail is found here. The tests use the system `git`
in temporary folders (skipped when it is missing or older than 2.17) and the fake `claude` and `kiro-cli` of
tests/agents as real child processes. What the supervisor does with these functions (entries, the queue row, exit 3,
the events, the child) is W9.7 and is not tested here.

The goldens of runs without the option are in test_worktree_golden.py and are not changed by this task.
"""

import ast
import contextlib
import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.budget.support import BudgetCase
from tests.goal import gen
from tests.goal.fakeroot import FakeRoot, git, needs_git
from tests.goal.goalsupport import GoalCase
from umwayi import agents
from umwayi import goalgit as gg
from umwayi import goalstate as gs
from umwayi.errors import UsageError

END = {"do": "exit", "code": 0}
G1, G2, G3 = "G-0001", "G-0002", "G-0003"
T1, T2, T3 = "T-01", "T-02", "T-03"
FORBIDDEN = ("push", "merge", "rebase", "pull", "fetch", "reset", "clean", "checkout", "switch", "branch", "tag",
             "stash", "commit", "prune", "lock", "move", "repair", "--force", "-f")
DESIGN = {  # design.md "The git commands (goalgit.py, the whole list)"
    "is_repo": ("root", "rev-parse --is-inside-work-tree", False),
    "has_main": ("root", "rev-parse --verify --quiet refs/heads/main", False),
    "base": ("root", "rev-parse refs/heads/main", False),
    "has_origin_main": ("root", "rev-parse --verify --quiet refs/remotes/origin/main", False),
    "behind_origin": ("root", "rev-list --count refs/heads/main..refs/remotes/origin/main", False),
    "branch_exists": ("root", "rev-parse --verify --quiet refs/heads/{BRANCH}", False),
    "worktree_list": ("root", "worktree list --porcelain -z", False),
    "worktree_add": ("root", "worktree add -b {BRANCH} {PATH} {BASE}", True),
    "worktree_add_detached": ("root", "worktree add --detach {PATH} {BASE}", True),
    "worktree_remove": ("root", "worktree remove {PATH}", True),
    "toplevel": ("tree", "rev-parse --show-toplevel", False),
    "common_dir": ("tree", "rev-parse --git-common-dir", False),
    "head": ("tree", "rev-parse HEAD", False),
    "status": ("tree", "status --porcelain=v1 -z --untracked-files=all", False),
    "count_ahead": ("tree", "rev-list --count {BASE}..HEAD", False),
    "changed": ("tree", "diff --name-status -z --no-ext-diff --no-renames {BASE} HEAD", False),
    "is_ancestor": ("root", "merge-base --is-ancestor {TIP} refs/heads/main", False),
    "commit_exists": ("root", "cat-file -e {SHA}^{commit}", False),
}


# ---------------------------------------------------------------------------------------------------- helpers


def snap(folder, skip=()):
    """Every path under the folder with its kind, mode and a hash of its bytes, to prove nothing was written."""
    out = {}
    for dirpath, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if os.path.join(dirpath, d) not in skip]
        for n in dirs + files:
            p = os.path.join(dirpath, n)
            if p in skip:
                continue
            st = os.lstat(p)
            if stat.S_ISLNK(st.st_mode):
                out[p] = ("link", os.readlink(p))
            elif stat.S_ISDIR(st.st_mode):
                out[p] = ("dir", stat.S_IMODE(st.st_mode))
            else:
                out[p] = ("file", stat.S_IMODE(st.st_mode), hashlib.sha256(Path(p).read_bytes()).hexdigest())
    return out


class RepoMixin:
    """The umwayi root is itself a git work tree with a local `main` (W9.R8.1)."""

    def init_repo(self):
        needs_git()
        git(self.root, "init", "-q", "-b", "main")
        (self.root / "README.md").write_text("the owner's repo\n", encoding="utf-8")
        (self.root / "src").mkdir(exist_ok=True)
        (self.root / "src" / "a.txt").write_text("a\n", encoding="utf-8")
        git(self.root, "add", "README.md", "src/a.txt")
        git(self.root, "commit", "-q", "-m", "first")

    @property
    def wtroot(self) -> str:
        return gg.worktree_root_of(gg.real_root(self.root))

    def wt(self, goal=G1, task=T1) -> str:
        return gg.worktree_path(gg.real_root(self.root), goal, task)

    def main_tip(self) -> str:
        return git(self.root, "rev-parse", "refs/heads/main")

    def commit_on_main(self, name="more.txt"):
        """The owner commits on main (the owner's own act, in the root)."""
        (self.root / name).write_text(name + "\n", encoding="utf-8")
        git(self.root, "add", name)
        git(self.root, "commit", "-q", "-m", "owner change " + name)
        return self.main_tip()

    def owner_state(self) -> dict:
        """HEAD, the index, the files of the owner's folder (everything outside .git) and the tip of main."""
        git_dir = os.path.join(str(self.root), ".git")
        return {"head": Path(git_dir, "HEAD").read_bytes(),
                "index": hashlib.sha256(Path(git_dir, "index").read_bytes()).hexdigest(),
                "files": snap(self.root, skip={git_dir}), "main": self.main_tip()}

    def add_origin(self):
        origin = self.root.parent / "origin-repo"
        shutil.copytree(self.root, origin)
        git(self.root, "remote", "add", "origin", str(origin))
        git(self.root, "fetch", "-q", "origin")
        return origin

    def origin_ahead(self, origin):
        git(origin, "checkout", "-q", "main")
        (origin / "ahead.txt").write_text("ahead\n", encoding="utf-8")
        git(origin, "add", "ahead.txt")
        git(origin, "commit", "-q", "-m", "ahead")
        git(self.root, "fetch", "-q", "origin")

    def start(self, goal=G1, task=T1):
        """start_check, then make: what the supervisor does for the worktree half of a start."""
        base = gg.start_check(self.root, goal, task)
        return gg.make(self.root, goal, task, base)

    def branches(self) -> list:
        return git(self.root, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()

    def listing(self) -> list:
        return [r["worktree"] for r in gg.listed(self.root)]

    def caught(self, check, *args, **kw):
        """A planted fault: the group's check must fail on it."""
        with self.assertRaises(AssertionError, msg="the planted fault was not caught"):
            check(*args, **kw)


class GitGoalCase(RepoMixin, GoalCase):
    def setUp(self):
        super().setUp()
        self.init_repo()

    def goals(self, n=1, tasks=5):
        for _ in range(n):
            self.approved(tasks, goal_budget=500)

    def to_running(self, goal, task, base):
        return self.move(goal, task, "running", "start", base=base)

    def to_review(self, goal, task):
        return self.move(goal, task, "in review", "checked", branch=gg.task_branch(goal, task), tip=self.main_tip())


class GitBudgetCase(RepoMixin, BudgetCase):
    """`agent run` and `agent check` as real child processes, with the umwayi root a git work tree."""

    def setUp(self):
        super().setUp()
        self.init_repo()

    def commit_kiro_hook(self):
        self.kiro_hook_file(command=self.kiro_command(python=sys.executable), folder=self.root / ".kiro" / "hooks")
        git(self.root, "add", ".kiro")
        git(self.root, "commit", "-q", "-m", "the kiro hook file")

    def run_in(self, name, path, *steps, prompt="Do the task"):
        return self.umwayi("run", name, "--prompt", prompt, "--workdir", path, extra=self.script(*(steps or (END,))))

    def check_in(self, name, path):
        return self.umwayi("check", name, "--workdir", path)


# ---------------------------------------------------------------------------------------------------- the list


class ListGuardTests(unittest.TestCase):
    """W9.R8.1: one place for git, the 18 lists, the three writes once, no force."""

    def test_the_list_is_the_design_list_word_for_word(self):
        self.assertEqual(set(gg.COMMANDS), set(DESIGN))
        self.assertEqual(len(gg.COMMANDS), 18)
        for name, (kind, text, writes) in DESIGN.items():
            self.assertEqual((gg.COMMANDS[name][0], " ".join(gg.COMMANDS[name][1]), gg.COMMANDS[name][2]),
                             (kind, text, writes), name)

    def test_no_list_holds_a_word_that_changes_the_owners_copy_or_the_network(self):
        for name, (_, words, _) in gg.COMMANDS.items():
            for w in words:
                self.assertNotIn(w, FORBIDDEN, f"{name}: {w}")
        self.assertIn("merge-base", gg.COMMANDS["is_ancestor"][1])  # a different word, allowed in this list only
        self.assertEqual([n for n, c in gg.COMMANDS.items() if "merge-base" in c[1]], ["is_ancestor"])

    def test_the_three_writes_appear_once_each(self):
        self.assertEqual(sorted(gg.WRITES), ["worktree_add", "worktree_add_detached", "worktree_remove"])
        shapes = [tuple(w for w in c[1] if w in ("worktree", "add", "remove", "-b", "--detach"))
                  for c in gg.COMMANDS.values() if c[2]]
        self.assertEqual(sorted(shapes), [("worktree", "add", "--detach"), ("worktree", "add", "-b"),
                                          ("worktree", "remove")])

    def source(self):
        return Path(gg.__file__).read_text(encoding="utf-8")

    def test_the_module_has_no_forbidden_word_no_shell_no_network_and_one_process_start(self):
        tree = ast.parse(self.source())
        words = set()  # every word of every tuple or list of strings: the places an argument list is made
        for n in ast.walk(tree):
            if isinstance(n, (ast.Tuple, ast.List)):
                words |= {e.value for e in n.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}
        self.assertIn("worktree", words)
        for w in FORBIDDEN:
            self.assertNotIn(w, words, f"the module holds the word {w!r}")
        imports = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        imports |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        self.assertFalse(imports & {"socket", "urllib", "http", "ssl", "requests", "ftplib", "smtplib", "xmlrpc"})
        text = self.source()
        self.assertNotIn("shell=True", text)
        self.assertNotIn("os.system", text)
        self.assertEqual(len(re.findall(r"subprocess\.Popen\(", text)), 1)
        self.assertEqual(len(re.findall(r"subprocess\.(run|call|check_output|check_call)\(", text)), 0)
        self.assertNotIn("chmod", text)
        self.assertNotIn("rmtree", text)

    def test_every_list_starts_with_the_same_words_and_the_clean_environment(self):
        sha = "a" * 40
        for name, (kind, words, _) in gg.COMMANDS.items():
            params = {}
            for key in re.findall(r"\{([A-Z]+)\}", " ".join(words)):
                params[key] = {"BRANCH": "umwayi/g-0001-t-01", "PATH": "/tmp/x-worktrees/g-0001-t-01"}.get(key, sha)
            argv = gg.argv_for(name, "/tmp/x", **params)
            self.assertEqual(argv[:7], ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-C",
                                        "/tmp/x"], name)
            self.assertNotIn("sh", argv)
        with mock.patch.dict(os.environ, {"AWS_SECRET": "x", "GIT_DIR": "/elsewhere", "PATH": "/usr/bin"}):
            env = gg.git_env()
        self.assertEqual(env["GIT_CONFIG_GLOBAL"], "/dev/null")
        self.assertEqual(env["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(env["GIT_TERMINAL_PROMPT"], "0")
        self.assertNotIn("AWS_SECRET", env)
        self.assertNotIn("GIT_DIR", env)

    def test_a_value_outside_its_pattern_never_enters_a_list(self):
        sha = "b" * 40
        bad = [("branch_exists", {"BRANCH": "main"}), ("branch_exists", {"BRANCH": "umwayi/g-0001-t-01; rm -rf /"}),
               ("branch_exists", {"BRANCH": "umwayi/g-0001-t-01\n"}), ("branch_exists", {"BRANCH": "umwayi/G-0001-t-01"}),
               ("branch_exists", {"BRANCH": "umwayi/g-0001-t-01 -f"}), ("branch_exists", {"BRANCH": "umwayi/g-٠٠٠١-t-01"}),
               ("count_ahead", {"BASE": "HEAD"}), ("count_ahead", {"BASE": "a" * 39}), ("count_ahead", {"BASE": "A" * 40}),
               ("count_ahead", {"BASE": sha + "\n"}), ("is_ancestor", {"TIP": "--all"}), ("commit_exists", {"SHA": "-f"}),
               ("worktree_remove", {"PATH": "relative"}), ("worktree_remove", {"PATH": "/a\x00b"}),
               ("worktree_remove", {"PATH": ""}), ("worktree_remove", {"PATH": 5}),
               ("base", {"BASE": sha}), ("worktree_remove", {})]
        for name, params in bad:
            with self.subTest(name=name, params=params):
                with self.assertRaises(ValueError):
                    gg.argv_for(name, "/tmp/x", **params)
        with self.assertRaises(ValueError):
            gg.argv_for("push", "/tmp/x")
        with self.assertRaises(ValueError):
            gg.argv_for("base", "relative")

    def test_a_planted_force_flag_is_found_by_the_guard(self):
        forced = dict(gg.COMMANDS, worktree_remove=("root", ("worktree", "remove", "--force", "{PATH}"), True))
        self.assertTrue(any(w in FORBIDDEN for c in forced.values() for w in c[1]))
        pushed = dict(gg.COMMANDS, extra=("root", ("push", "origin", "main"), False))
        self.assertNotEqual(len(pushed), 18)

    def test_git_that_is_slow_or_noisy_is_stopped(self):
        d = Path(tempfile.mkdtemp(prefix="fakegit-"))
        self.addCleanup(shutil.rmtree, d, True)
        fake = d / "git"
        fake.write_text(f"#!{sys.executable}\nimport sys, time\nmode = open({str(d / 'mode')!r}).read()\n"
                        "if mode == 'slow':\n    time.sleep(30)\nelif mode == 'big':\n"
                        "    sys.stdout.write('x' * 3000000)\nelse:\n    sys.stdout.write('true\\n')\n", encoding="utf-8")
        fake.chmod(0o755)
        with mock.patch.dict(os.environ, {"PATH": f"{d}:{os.environ['PATH']}"}), mock.patch.object(gg, "GIT_TIMEOUT", 1.0):
            (d / "mode").write_text("ok")
            self.assertEqual(gg.run_git("is_repo", str(d)).text(), "true")
            (d / "mode").write_text("big")
            with self.assertRaises(gg.GitError):
                gg.run_git("is_repo", str(d))
            (d / "mode").write_text("slow")
            with self.assertRaises(gg.GitError):
                gg.run_git("is_repo", str(d))


# ---------------------------------------------------------------------------------------------------- W9.R8.1


class OwnerCopyTests(RepoMixin, FakeRoot):
    def setUp(self):
        super().setUp()
        self.init_repo()

    def check_one_worktree_at_base(self):
        before = self.owner_state()
        listed_before, branches_before = self.listing(), self.branches()
        tip = self.main_tip()
        made = self.start()
        self.assertEqual(made.base, tip)
        self.assertEqual(made.path, self.wt())
        self.assertEqual(len(self.listing()), len(listed_before) + 1)
        self.assertEqual(sorted(self.branches()), sorted(branches_before + ["umwayi/g-0001-t-01"]))
        self.assertEqual(git(made.path, "rev-parse", "HEAD"), tip)
        self.assertEqual(git(self.root, "rev-parse", "umwayi/g-0001-t-01"), tip)
        self.assertEqual(git(made.path, "rev-parse", "--abbrev-ref", "HEAD"), "umwayi/g-0001-t-01")
        self.assertEqual(self.owner_state(), before, "the owner's working copy changed")

    def test_a_start_makes_exactly_one_worktree_and_one_branch_at_base(self):
        self.check_one_worktree_at_base()

    def check_base_is_main_not_the_owners_head(self):
        git(self.root, "checkout", "-q", "-b", "side")
        (self.root / "side.txt").write_text("side\n", encoding="utf-8")
        git(self.root, "add", "side.txt")
        git(self.root, "commit", "-q", "-m", "side work")
        side = git(self.root, "rev-parse", "HEAD")
        self.assertNotEqual(side, self.main_tip())
        before = self.owner_state()
        made = self.start()
        self.assertEqual(made.base, self.main_tip())
        self.assertNotEqual(made.base, side)
        self.assertFalse((Path(made.path) / "side.txt").exists())
        self.assertEqual(git(self.root, "rev-parse", "--abbrev-ref", "HEAD"), "side")
        self.assertEqual(self.owner_state(), before)

    def test_base_is_the_tip_of_main_and_not_the_owners_head(self):
        self.check_base_is_main_not_the_owners_head()

    def check_a_task_after_a_merge_starts_from_a_base_that_contains_it(self):
        first = self.start(G1, T1)
        (Path(first.path) / "work.txt").write_text("work\n", encoding="utf-8")
        git(first.path, "add", "work.txt")
        git(first.path, "commit", "-q", "-m", "task one")
        tip = git(first.path, "rev-parse", "HEAD")
        git(self.root, "merge", "-q", "--ff-only", "umwayi/g-0001-t-01")  # the owner merges, in the owner's way
        self.assertEqual(self.main_tip(), tip)
        second = self.start(G1, T2)
        self.assertEqual(second.base, tip)
        self.assertTrue((Path(second.path) / "work.txt").is_file())
        self.assertNotEqual(second.base, first.base)

    def test_a_task_after_a_merge_gets_a_base_that_contains_it(self):
        self.check_a_task_after_a_merge_starts_from_a_base_that_contains_it()

    def check_stale_creates_nothing(self, origin):
        self.origin_ahead(origin)
        before = snap(self.root.parent)
        with self.assertRaises(gg.Refused) as cm:
            gg.start_check(self.root, G1, T1)
        self.assertEqual(cm.exception.reason, "stale")
        self.assertIn("main is behind origin/main", str(cm.exception))
        self.assertEqual(snap(self.root.parent), before)
        self.assertFalse(os.path.exists(self.wtroot))

    def test_main_behind_origin_is_stale_and_creates_nothing(self):
        origin = self.add_origin()
        self.assertTrue(gg.start_check(self.root, G1, T1))  # equal: fine
        self.check_stale_creates_nothing(origin)

    def test_a_repo_with_no_origin_is_not_stale(self):
        self.assertFalse(gg.stale(self.root))
        self.assertEqual(gg.start_check(self.root, G1, T1), self.main_tip())

    def test_the_owner_ahead_of_origin_is_not_stale(self):
        self.add_origin()
        self.commit_on_main()
        self.assertFalse(gg.stale(self.root))

    def test_start_check_refuses_a_root_that_is_not_a_repo_or_has_no_main(self):
        plain = self.root.parent / "plain"
        plain.mkdir()
        with self.assertRaises(gg.Refused) as cm:
            gg.start_check(plain, G1, T1)
        self.assertEqual(cm.exception.reason, "config")
        git(self.root, "branch", "-q", "-m", "main", "trunk")
        with self.assertRaises(gg.Refused) as cm:
            gg.start_check(self.root, G1, T1)
        self.assertEqual(cm.exception.reason, "config")

    def test_a_failed_add_is_config_and_touches_nothing(self):
        before = snap(self.root.parent)
        with self.assertRaises(gg.Refused) as cm:
            gg.make(self.root, G1, T1, "0" * 40)
        self.assertEqual(cm.exception.reason, "config")
        self.assertEqual(self.branches(), ["main"])
        self.assertEqual(self.listing(), [str(self.root)])
        after = snap(self.root.parent)
        outside = lambda s: {k: v for k, v in s.items() if k != self.wtroot and not k.startswith(self.wtroot + "/")}
        self.assertEqual(outside(after), outside(before))  # only the worktree root itself may have been made

    def test_a_new_worktree_that_does_not_check_out_right_is_removed_and_dirty(self):
        with mock.patch.object(gg, "_verify_new", return_value=True):
            with self.assertRaises(gg.Refused) as cm:
                self.start()
        self.assertEqual(cm.exception.reason, "dirty")
        self.assertFalse(os.path.exists(self.wt()))
        self.assertEqual(self.listing(), [str(self.root)])

    def test_the_worktree_root_is_made_with_mode_0700(self):
        self.start()
        self.assertEqual(stat.S_IMODE(os.lstat(self.wtroot).st_mode), 0o700)

    def test_umwayi_runs_no_command_that_changes_the_owners_copy(self):
        """Every list run during a whole life of a task, read from the process starts, holds none of the owner's words."""
        seen = []
        real = gg._spawn

        def spy(argv):
            seen.append(list(argv))
            return real(argv)

        with mock.patch.object(gg, "_spawn", spy):
            made = self.start()
            gg.dirty(self.root, G1, T1, tip=made.base)
            gg.remove_unused(self.root, G1, T1, made.base)
        self.assertTrue(seen)
        for argv in seen:
            self.assertFalse(set(argv[7:]) & set(FORBIDDEN), argv)
            self.assertNotIn("--force", argv)
            self.assertEqual(argv[:6], ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-C"])

    # ---- planted faults

    def test_fault_the_branch_made_from_the_owners_head(self):
        with mock.patch.object(gg, "read_base", lambda root: git(root, "rev-parse", "HEAD")):
            self.caught(self.check_base_is_main_not_the_owners_head)

    def test_fault_switch_run_in_the_owners_copy(self):
        real = gg.make

        def switching(root, goal, task, base):
            made = real(root, goal, task, base)
            git(root, "checkout", "-q", "--detach", "HEAD")  # the owner's HEAD moved
            return made

        with mock.patch.object(gg, "make", switching):
            self.caught(self.check_one_worktree_at_base)

    def test_fault_base_read_once_at_approval(self):
        old = self.main_tip()
        with mock.patch.object(gg, "read_base", lambda root: old):
            self.caught(self.check_a_task_after_a_merge_starts_from_a_base_that_contains_it)

    def test_fault_stale_not_checked(self):
        origin = self.add_origin()
        with mock.patch.object(gg, "stale", lambda root: False):
            self.caught(self.check_stale_creates_nothing, origin)


# ---------------------------------------------------------------------------------------------------- W9.R8.11


def make_ids(g):
    pick = g.pick
    goal = pick([f"G-{g.below(10000):04d}", f"G-{g.below(10 ** 7)}", g.text("G-0123456789", 0, 9),
                 g.text("abcG-T0123/.\x00 ", 0, 12), "G-" + g.text("٠١٢٣4567", 4, 5), "g-0007", "G-07", ""])
    task = pick([f"T-{g.below(100):02d}", f"T-{g.below(1000)}", g.text("T-0123456789", 0, 6),
                 g.text("abT-01/.\x00", 0, 8), "T-٠١", None, ""])
    return goal, task


class PathTests(RepoMixin, FakeRoot):
    def setUp(self):
        super().setUp()
        self.init_repo()

    def check_path_always_inside_or_refused(self):
        real = gg.real_root(self.root)
        wt = real + "-worktrees"

        def check(case):
            goal, task = case
            try:
                path = gg.worktree_path(real, goal, task)
            except ValueError:
                return True
            return (os.path.dirname(path) == wt and re.fullmatch(r"g-[0-9]{4,}-(t-[0-9]{2}|plan)", os.path.basename(path))
                    is not None and path.startswith(real + "-worktrees/") and ".." not in path.split("/"))

        gen.run_property(self, make_ids, check, cases=400, seeds=gen.SEEDS)

    def test_the_path_is_always_inside_the_worktree_root_or_the_ids_are_refused(self):
        self.check_path_always_inside_or_refused()

    def test_valid_ids_give_the_documented_names(self):
        real = gg.real_root(self.root)
        self.assertEqual(gg.worktree_path(real, "G-0007", "T-02"), real + "-worktrees/g-0007-t-02")
        self.assertEqual(gg.worktree_path(real, "G-0007"), real + "-worktrees/g-0007-plan")
        self.assertEqual(gg.task_branch("G-0007", "T-02"), "umwayi/g-0007-t-02")
        self.assertEqual(gg.worktree_path(real, "G-12345", "T-99"), real + "-worktrees/g-12345-t-99")

    def test_tasks_with_the_same_number_in_two_goals_have_different_paths(self):
        real = gg.real_root(self.root)
        self.assertNotEqual(gg.worktree_path(real, G1, T1), gg.worktree_path(real, G2, T1))
        self.assertNotEqual(gg.task_branch(G1, T1), gg.task_branch(G2, T1))

    def test_a_name_is_never_read_from_text(self):
        real = gg.real_root(self.root)
        for bad in ("G-0001/../x", "G-0001 T-01", "../G-0001", "G-0001\n", "g-0001", "G-1", "G-000٣"):
            with self.assertRaises(ValueError):
                gg.worktree_path(real, bad, T1)
        for bad in ("T-1", "t-01", "T-01/..", "T-001", "T-٠١"):
            with self.assertRaises(ValueError):
                gg.worktree_path(real, G1, bad)
        for root in ("relative", "/a/../b", "/a//b", "/a/b/", "/", ""):
            with self.assertRaises(ValueError):
                gg.worktree_path(root, G1, T1)

    def test_check_path_accepts_only_the_exact_string_under_a_good_root(self):
        self.start()
        real = gg.real_root(self.root)

        def check(path):
            try:
                out = gg.check_path(self.root, path)
            except UsageError:
                return True
            return out == path and os.path.dirname(path) == real + "-worktrees" and re.fullmatch(
                r"g-[0-9]{4,}-(t-[0-9]{2}|plan)", os.path.basename(path)) is not None

        def make(g):
            base = real + "-worktrees"
            return g.pick([base + "/" + g.text("gt-0123456789plan/.", 0, 14), g.text("/.abc-", 0, 14), base + g.text("/.g", 0, 4),
                           base + "/g-0001-t-01" + g.text("/.\x00 ", 0, 3), base + "//g-0001-t-01", base + "/./g-0001-t-01",
                           real + "/" + g.text("g-0123t/", 1, 9), "", base + "/g-0001-t-01"])

        gen.run_property(self, make, check, cases=500, seeds=gen.SEEDS)
        self.assertEqual(gg.check_path(self.root, self.wt()), self.wt())

    def check_a_root_reached_through_a_link(self):
        link = self.root.parent / "link-to-root"
        os.symlink(self.root, link)
        made = self.start()
        self.assertEqual(gg.worktree_path(gg.real_root(link), G1, T1), made.path)
        self.assertEqual(gg.check_path(link, made.path), made.path)
        self.assertEqual(gg.verify_tree(link, made.path), made.path)
        self.assertEqual(gg.dirty(link, G1, T1), None)

    def test_a_root_reached_through_a_link_compares_equal_by_real_path(self):
        self.check_a_root_reached_through_a_link()

    def test_a_path_reached_through_a_link_is_not_the_path(self):
        made = self.start()
        link = self.root.parent / "link-dir"
        os.symlink(self.root.parent, link)
        through = str(link) + "/" + os.path.basename(self.wtroot) + "/" + os.path.basename(made.path)
        with self.assertRaises(gg.PathRefused):
            gg.check_path(self.root, through)

    def test_a_worktree_root_that_is_wrong_is_refused(self):
        wt = self.wtroot
        for label, make in (("link", lambda: os.symlink(self.root.parent, wt)),
                            ("file", lambda: Path(wt).write_text("x", encoding="utf-8")),
                            ("world writable", lambda: (os.mkdir(wt), os.chmod(wt, 0o777))),
                            ("group readable", lambda: (os.mkdir(wt), os.chmod(wt, 0o750))),
                            ("too narrow", lambda: (os.mkdir(wt), os.chmod(wt, 0o500)))):
            with self.subTest(label):
                if os.path.lexists(wt):
                    os.chmod(wt, 0o700) if os.path.isdir(wt) and not os.path.islink(wt) else None
                    shutil.rmtree(wt) if os.path.isdir(wt) and not os.path.islink(wt) else os.unlink(wt)
                make()
                path = self.wt()
                with self.assertRaises(gg.PathRefused) as cm:
                    gg.check_path(self.root, path)
                self.assertEqual(cm.exception.reason, "config")
                with self.assertRaises(gg.Refused) as cr:
                    gg.make(self.root, G1, T1, self.main_tip())
                self.assertIn(cr.exception.reason, ("config", "leftover"))
        os.chmod(wt, 0o700)

    def test_a_parent_folder_that_does_not_exist_is_a_refusal_that_creates_nothing(self):
        ghost = self.root.parent / "ghost" / "umwayi-os"
        with self.assertRaises(gg.Refused):
            gg._ensure_root(ghost)
        with self.assertRaises(gg.Refused):
            gg.make(ghost, G1, T1, self.main_tip())
        self.assertFalse((self.root.parent / "ghost").exists())
        self.assertFalse((self.root.parent / "ghost-worktrees").exists())

    def test_the_refusal_sentence_does_not_echo_the_path(self):
        try:
            gg.check_path(self.root, "/secret/place/g-0001-t-01")
        except gg.PathRefused as e:
            self.assertNotIn("secret", str(e))
            self.assertEqual(str(e), gg.PATH_SENTENCE)

    # ---- planted faults

    def test_fault_a_name_taken_from_the_goal_text(self):
        real = gg.real_root(self.root)
        with mock.patch.object(gg, "worktree_name", lambda goal, task=None: str(goal) + "-" + str(task)):
            self.caught(lambda: self.assertEqual(gg.worktree_path(real, "G-0001/../../x", "T-01"), None))
            self.caught(self.check_path_always_inside_or_refused)

    def test_fault_no_comparison_by_real_path(self):
        with mock.patch.object(gg, "real_root", lambda root: os.path.abspath(os.fspath(root))):
            self.caught(self.check_a_root_reached_through_a_link)


# ---------------------------------------------------------------------------------------------------- W9.R8.9, 10, 16


class WorkdirTests(GitBudgetCase):
    def make_two(self):
        base = self.main_tip()
        a = gg.make(self.root, G1, T1, base)
        b = gg.make(self.root, G2, T1, base)
        return a, b

    # ---- the genuine path is accepted

    def test_a_genuine_path_is_accepted_by_check_and_run_and_the_helper_works_there(self):
        made = self.start()
        c = self.check_in("reviewer", made.path)
        self.assertEqual(c.returncode, 0, c.stdout + c.stderr)
        self.assertIn(f"workdir {made.path}", c.stdout)
        self.assertTrue(all(call["cwd"] == made.path for call in self.calls() if "cwd" in call), self.calls())
        self.fake_log.unlink()
        r = self.run_in("reviewer", made.path)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([c["cwd"] for c in self.started()], [made.path])
        self.assertTrue(all(c["cwd"] == made.path for c in self.calls() if "cwd" in c), "a probe ran outside the worktree")
        start = [e for e in self.entries() if e.added.startswith("Started")][0]
        self.assertIn("; working folder: worktree g-0001-t-01", start.checked)
        self.assertNotIn(made.path, start.checked)

    def test_the_prompt_can_come_on_standard_input_with_a_dash(self):
        made = self.start()
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "run", "reviewer", "-",
                            "--workdir", made.path], input="Do the task", capture_output=True, text=True,
                           env=self.env(self.script(END)), cwd=str(self.tmp), timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([c["cwd"] for c in self.started()], [made.path])

    # ---- W9.R8.9: the helpers work in the task's worktree, each in a fresh session

    def test_three_runs_of_a_task_are_in_its_worktree_with_a_different_session_each(self):
        made = self.start()
        for name in ("reviewer", "second", "reviewer"):  # builder, tester, the guide's check
            self.assertEqual(self.run_in(name, made.path).returncode, 0)
        started = self.started()
        self.assertEqual(len(started), 3)
        self.assertEqual({c["cwd"] for c in started}, {made.path})
        self.assertEqual(len({c["sid"] for c in started}), 3)
        self.assertEqual(len({c["pid"] for c in started}), 3)
        self.assertNotIn(str(self.root), {c["cwd"] for c in started})
        self.assertNotIn(str(self.work), {c["cwd"] for c in started})

    def test_the_tasks_of_two_goals_are_in_two_worktrees(self):
        a, b = self.make_two()
        self.assertNotEqual(a.path, b.path)
        self.run_in("reviewer", a.path)
        self.run_in("reviewer", b.path)
        self.assertEqual([c["cwd"] for c in self.started()], [a.path, b.path])

    def test_a_marker_file_of_the_worktree_is_seen_and_the_owners_untracked_file_is_not(self):
        (self.root / "owner-only.txt").write_text("untracked\n", encoding="utf-8")
        made = self.start()
        self.assertTrue((Path(made.path) / "README.md").is_file())
        self.assertFalse((Path(made.path) / "owner-only.txt").exists())

    def test_a_rules_file_in_a_worktree_changes_no_decision(self):
        self.write_rules("rules:\n  - id: ask-second\n    title: second needs the owner\n    text: Ask.\n    verdict: ask\n"
                         "    matchers:\n      type: agent_run\n      agent: second\n")
        made = self.start()
        Path(made.path, "rules.yaml").write_text(
            "rules:\n  - id: all-yes\n    title: all\n    text: All.\n    verdict: yes\n    matchers:\n"
            "      type: agent_run\n", encoding="utf-8")
        r = self.run_in("second", made.path)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertEqual(self.started(), [])

    # ---- W9.R8.10: every refusal is 64 and starts nothing

    def refusal_paths(self) -> dict:
        made = self.start(G1, T1)
        self.start(G1, T2)
        wt = self.wtroot
        outside = self.tmp / "elsewhere"
        outside.mkdir()
        git(self.root, "worktree", "add", "-q", "-b", "outside-branch", str(outside / "g-0001-t-04"), "HEAD")
        git(self.root, "worktree", "add", "-q", "-b", "caps-branch", wt + "/G-0001-T-05", "HEAD")
        os.symlink(made.path, wt + "/g-0001-t-06")
        other = self.tmp / "other-repo"
        other.mkdir()
        git(other, "init", "-q", "-b", "main")
        (other / "f").write_text("f\n", encoding="utf-8")
        git(other, "add", "f")
        git(other, "commit", "-q", "-m", "x")
        git(other, "worktree", "add", "-q", "-b", "o", wt + "/g-0001-t-07", "HEAD")
        (self.root / "inside").mkdir()
        os.makedirs(Path(self.root, "g-0001-t-01"))
        os.makedirs(Path(made.path, "sub"))
        return {
            "a path outside the worktree root": str(outside / "g-0001-t-04"),
            "a relative path": "g-0001-t-01",
            "a relative path to the genuine one": os.path.relpath(made.path, self.tmp),
            "a path with ..": wt + "/../" + os.path.basename(wt) + "/g-0001-t-01",
            "a link to a worktree": wt + "/g-0001-t-06",
            "a folder with a right name in the umwayi root": str(self.root / "g-0001-t-01"),
            "the umwayi root itself": str(self.root),
            "a folder inside the umwayi root": str(self.root / "inside"),
            "the worktree root itself": wt,
            "a grandchild": made.path + "/sub",
            "a name in capitals": wt + "/G-0001-T-05",
            "a worktree of another repo": wt + "/g-0001-t-07",
            "an empty string": "",
            "a NUL": made.path + "\x00",
            "a trailing slash": made.path + "/",
            "a folder that does not exist": wt + "/g-0001-t-09",
            "a name that is not in the pattern": wt + "/anything",
        }

    def assert_all_refused(self, sub=True):
        agent = agents.find(agents.load(self.root), "reviewer")
        for label, path in self.refusal_paths().items():
            with (self.subTest(label) if sub else contextlib.nullcontext()):
                with self.assertRaises(UsageError, msg=label) as cm:
                    agents.with_workdir(self.root, agent, path)
                self.assertEqual(str(cm.exception), gg.PATH_SENTENCE)
        genuine = self.wt(G1, T1)
        self.assertEqual(agents.with_workdir(self.root, agent, genuine).workdir, genuine)

    def test_every_refusal_of_a_path_is_a_usage_error_with_a_fixed_sentence(self):
        self.assert_all_refused()

    def test_through_the_command_line_each_refusal_is_64_and_starts_nothing(self):
        paths = self.refusal_paths()
        paths.pop("a NUL")  # an argument cannot hold a NUL; the function test above covers it
        for label, path in paths.items():
            for sub in ("run", "check"):
                with self.subTest(label, command=sub):
                    args = ["run", "reviewer", "--prompt", "Do the task"] if sub == "run" else ["check", "reviewer"]
                    r = self.umwayi(*args, "--workdir", path, extra=self.script(END))
                    self.assertEqual(r.returncode, 64, r.stdout + r.stderr)
                    self.assertIn(gg.PATH_SENTENCE, r.stderr)
                    if path:
                        self.assertNotIn(path, r.stdout + r.stderr)
                    self.assertEqual(self.calls(), [], "a program was started")
                    self.assertFalse((self.root / "LOGBOOK.md").exists(), "a refusal wrote the logbook")

    def test_a_refused_path_does_not_hide_a_kiro_or_other_usage_error(self):
        made = self.start()
        r = self.umwayi("run", "reviewer", "--prompt", "x", "--effort", "extreme", "--workdir", made.path)
        self.assertEqual(r.returncode, 64)
        r = self.umwayi("run", "nobody", "--prompt", "x", "--workdir", made.path)
        self.assertEqual(r.returncode, 64)

    def test_the_option_is_only_for_run_and_check(self):
        made = self.start()
        for sub in ("chat", "login", "validate", "list"):
            r = self.umwayi(sub, "reviewer", "--workdir", made.path)
            self.assertEqual(r.returncode, 64, sub)

    def test_the_working_folder_rule_of_agents_yaml_applies(self):
        made = self.start()
        agent = agents.find(agents.load(self.root), "reviewer")
        with mock.patch.object(agents, "_workdir_problem", return_value="workdir must not be the umwayi root"):
            with self.assertRaises(UsageError):
                agents.with_workdir(self.root, agent, made.path)
        self.assertEqual(agents._workdir_problem(made.path, gg.real_root(self.root)), None)

    # ---- the planted faults of W9.R8.10

    def sloppy_prefix(self, root, path):
        wt = gg.real_root(root) + "-worktrees"
        if isinstance(path, str) and path.startswith(wt) and os.path.isdir(path):
            return path
        raise gg.PathRefused("path")

    def follows_links(self, root, path):
        if isinstance(path, str) and path:
            path = os.path.realpath(path)
        return gg.check_path(root, path, must_exist=True)

    def no_common_dir(self, root, path):
        path = gg.check_path(root, path, must_exist=True)
        top = gg.run_git("toplevel", root, worktree=path)
        if os.path.realpath(top.text()) != path:
            raise gg.PathRefused("path")
        return path

    def test_fault_the_prefix_compared_as_a_string_without_the_real_path(self):
        with mock.patch.object(gg, "verify_tree", self.sloppy_prefix):
            self.caught(self.assert_all_refused, sub=False)

    def test_fault_a_link_followed(self):
        with mock.patch.object(gg, "verify_tree", self.follows_links):
            self.caught(self.assert_all_refused, sub=False)

    def test_fault_the_common_dir_not_checked(self):
        with mock.patch.object(gg, "verify_tree", self.no_common_dir):
            self.caught(self.assert_all_refused, sub=False)

    # ---- W9.R8.16: the gate checks are those of the worktree

    def test_a_kiro_hook_file_the_owner_did_not_commit_fails_the_check_for_the_worktree(self):
        self.kiro_hook_file(command=self.kiro_command(python=sys.executable), folder=self.root / ".kiro" / "hooks")
        made = self.start()  # the file is untracked: the worktree lacks it
        self.assertFalse((Path(made.path) / ".kiro").exists())
        c = self.check_in("helper", made.path)
        self.assertEqual(c.returncode, 2, c.stdout + c.stderr)
        self.assertIn("no: kiro hook file", c.stdout)
        self.assertEqual(self.started(), [])
        r = self.run_in("helper", made.path)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(self.started(), [])
        removed = gg.remove_unused(self.root, G1, T1, made.base)  # the unused worktree is removed at once
        self.assertTrue(removed.removed)
        self.assertFalse(os.path.exists(made.path))

    def test_a_committed_kiro_hook_file_is_found_in_the_worktree(self):
        self.commit_kiro_hook()
        made = self.start()
        self.assertTrue((Path(made.path) / ".kiro" / "hooks" / "umwayi.json").is_file())
        c = self.check_in("helper", made.path)
        self.assertEqual(c.returncode, 0, c.stdout + c.stderr)
        r = self.run_in("helper", made.path)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([x["cwd"] for x in self.started()], [made.path])

    def test_a_claude_agent_is_gated_in_the_worktree_without_any_hook_file(self):
        made = self.start()
        c = self.check_in("reviewer", made.path)
        self.assertEqual(c.returncode, 0, c.stdout + c.stderr)

    def test_a_worktree_has_no_untracked_or_ignored_file_of_the_owners_folder(self):
        (self.root / ".gitignore").write_text("node_modules/\n.env\n", encoding="utf-8")
        git(self.root, "add", ".gitignore")
        git(self.root, "commit", "-q", "-m", "ignore")
        (self.root / "node_modules").mkdir()
        (self.root / "node_modules" / "pkg.js").write_text("x\n", encoding="utf-8")
        (self.root / ".env").write_text("SECRET=1\n", encoding="utf-8")
        (self.root / "scratch.txt").write_text("untracked\n", encoding="utf-8")
        made = self.start()
        for name in ("node_modules", ".env", "scratch.txt"):
            self.assertFalse(os.path.lexists(Path(made.path) / name), name)
        links = [p for p, _, _ in os.walk(made.path) if os.path.islink(p)]
        self.assertEqual(links, [])


# ---------------------------------------------------------------------------------------------------- W9.R8.12


class LeftoverTests(RepoMixin, FakeRoot):
    def setUp(self):
        super().setUp()
        self.init_repo()

    def assert_leftover(self, prepare, kind, goal=G1, task=T1):
        prepare()
        before = snap(self.root.parent)
        with self.assertRaises(gg.Refused) as cm:
            gg.start_check(self.root, goal, task)
        self.assertEqual(cm.exception.reason, "leftover")
        self.assertIn(kind, [k for k, _ in cm.exception.found])
        with self.assertRaises(gg.Refused):
            gg.make(self.root, goal, task, self.main_tip())
        self.assertEqual(snap(self.root.parent), before, "the repo or the root changed")

    def leftover_folder(self):
        os.makedirs(self.wt(), mode=0o700) if os.path.isdir(self.wtroot) else (os.mkdir(self.wtroot, 0o700), os.mkdir(self.wt()))

    def leftover_branch(self):
        git(self.root, "branch", "umwayi/g-0001-t-01")

    def leftover_registration(self):
        made = self.start()
        shutil.rmtree(made.path)

    def leftover_unlisted(self):
        os.mkdir(self.wtroot, 0o700)
        os.mkdir(self.wtroot + "/stray")

    def leftover_ninth(self):
        base = self.main_tip()
        for i in range(1, 9):
            gg.make(self.root, G2, f"T-{i:02d}", base)

    def test_a_leftover_folder_with_the_tasks_name(self):
        self.assert_leftover(self.leftover_folder, "folder")

    def test_a_leftover_branch_only(self):
        self.assert_leftover(self.leftover_branch, "task-branch")

    def test_a_registration_whose_folder_was_deleted(self):
        self.assert_leftover(self.leftover_registration, "registration")

    def test_an_unregistered_folder_in_the_worktree_root(self):
        self.assert_leftover(self.leftover_unlisted, "unlisted", goal=G1, task=T2)

    def test_a_ninth_worktree(self):
        self.assert_leftover(self.leftover_ninth, "cap", goal=G3, task=T1)
        self.assertEqual(len(gg.worktrees(self.root)), 8)

    def test_eight_worktrees_are_allowed_and_the_ninth_is_not(self):
        base = self.main_tip()
        for i in range(1, 8):
            gg.make(self.root, G2, f"T-{i:02d}", base)
        self.assertEqual(gg.start_check(self.root, G3, T1), base)  # the eighth fits
        gg.make(self.root, G3, T1, base)
        with self.assertRaises(gg.Refused):
            gg.start_check(self.root, G3, T2)

    def test_a_leftover_of_another_task_does_not_stop_this_one(self):
        self.start(G1, T1)
        self.assertEqual(gg.start_check(self.root, G1, T2), self.main_tip())

    def test_a_branch_checked_out_elsewhere_is_a_leftover(self):
        git(self.root, "worktree", "add", "-q", "-b", "umwayi/g-0001-t-01", str(self.root.parent / "someplace"), "HEAD")
        with self.assertRaises(gg.Refused) as cm:
            gg.start_check(self.root, G1, T1)
        self.assertIn("registration", [k for k, _ in cm.exception.found])

    def test_the_refusal_names_what_is_left_over_and_never_removes_or_reuses_it(self):
        made = self.start()
        marker = Path(made.path) / "keep.txt"
        marker.write_text("work\n", encoding="utf-8")
        with self.assertRaises(gg.Refused) as cm:
            gg.start_check(self.root, G1, T1)
        self.assertIn(("folder", made.path), cm.exception.found)
        self.assertTrue(marker.is_file())
        self.assertIn("git worktree remove", gg.SENTENCES["leftover"])

    # ---- dirty

    def test_an_uncommitted_file_is_dirty(self):
        made = self.start()
        self.assertIsNone(gg.dirty(self.root, G1, T1))
        Path(made.path, "new.txt").write_text("x\n", encoding="utf-8")
        self.assertEqual(gg.dirty(self.root, G1, T1), "uncommitted")
        Path(made.path, "new.txt").unlink()
        (Path(made.path) / "README.md").write_text("changed\n", encoding="utf-8")
        self.assertEqual(gg.dirty(self.root, G1, T1), "uncommitted")

    def check_a_tip_that_moved_is_dirty(self):
        made = self.start()
        git(made.path, "checkout", "-q", "--", ".")
        Path(made.path, "w.txt").write_text("w\n", encoding="utf-8")
        git(made.path, "add", "w.txt")
        git(made.path, "commit", "-q", "-m", "work")
        tip = git(made.path, "rev-parse", "HEAD")
        self.assertIsNone(gg.dirty(self.root, G1, T1, tip=tip))
        git(made.path, "commit", "-q", "--allow-empty", "-m", "moved")
        self.assertEqual(gg.dirty(self.root, G1, T1, tip=tip), "moved")

    def test_a_tip_that_moved_after_the_scope_check_is_dirty(self):
        self.check_a_tip_that_moved_is_dirty()

    def test_a_missing_worktree_is_reported(self):
        self.assertEqual(gg.dirty(self.root, G1, T1), "missing")

    def test_dirty_takes_only_a_tip_in_the_pattern(self):
        self.start()
        with self.assertRaises(ValueError):
            gg.dirty(self.root, G1, T1, tip="HEAD")

    # ---- planted faults

    def test_fault_a_leftover_reused(self):
        with mock.patch.object(gg, "leftover", lambda *a, **k: []):
            self.caught(self.assert_leftover, self.leftover_folder, "folder")

    def test_fault_a_leftover_removed(self):
        real = gg.leftover

        def removing(root, goal, task=None):
            found = real(root, goal, task)
            for kind, text in found:
                if kind == "folder":
                    shutil.rmtree(text)
            return found

        with mock.patch.object(gg, "leftover", removing):
            self.caught(self.assert_leftover, self.leftover_folder, "folder")

    def test_fault_force_on_add(self):
        forced = ("root", ("worktree", "add", "-f", "-b", "{BRANCH}", "{PATH}", "{BASE}"), True)
        with mock.patch.dict(gg.COMMANDS, {"worktree_add": forced}):
            self.assertTrue(any(w in FORBIDDEN for w in gg.COMMANDS["worktree_add"][1]))
            self.caught(lambda: self.assertFalse(any(w in FORBIDDEN for c in gg.COMMANDS.values() for w in c[1])))

    def test_fault_the_cap_not_counted(self):
        with mock.patch.object(gg, "MAX_WORKTREES", 1000):
            self.caught(self.assert_leftover, self.leftover_ninth, "cap", G3, T1)

    def test_fault_the_moved_tip_not_noticed(self):
        real = gg.dirty
        with mock.patch.object(gg, "dirty", lambda root, goal, task=None, tip=None: real(root, goal, task)):
            self.caught(self.check_a_tip_that_moved_is_dirty)


# ---------------------------------------------------------------------------------------------------- W9.R8.13


class CleanupTests(GitGoalCase):
    def setUp(self):
        super().setUp()
        self.goals(1, 3)

    def built(self, task=T1, goal=G1):
        """A started task with a commit of the builder's in its worktree."""
        made = self.start(goal, task)
        self.to_running(goal, task, made.base)
        Path(made.path, f"{task}.txt").write_text("work\n", encoding="utf-8")
        git(made.path, "add", ".")
        git(made.path, "commit", "-q", "-m", "work")
        return made

    def merge(self, goal=G1, task=T1):
        self.to_review(goal, task)
        return self.move(goal, task, "merged", "observed")

    def check_merged_and_clean_is_removed_and_the_branch_stays(self):
        made = self.built()
        self.merge()
        r = gg.remove_after_merged(self.root, G1, T1)
        self.assertEqual((r.removed, r.why), (True, "removed"))
        self.assertFalse(os.path.lexists(made.path))
        self.assertNotIn(made.path, self.listing())
        self.assertIn("umwayi/g-0001-t-01", self.branches())

    def test_a_merged_tasks_clean_worktree_is_removed_and_its_branch_stays(self):
        self.check_merged_and_clean_is_removed_and_the_branch_stays()

    def check_a_changed_worktree_is_kept_and_listed(self):
        made = self.built()
        self.merge()
        Path(made.path, "after-merge.txt").write_text("late\n", encoding="utf-8")
        r = gg.remove_after_merged(self.root, G1, T1)
        self.assertEqual((r.removed, r.why), (False, "not clean"))
        self.assertTrue(os.path.isfile(Path(made.path, "after-merge.txt")))
        self.assertIn(made.path, gg.worktrees(self.root))
        self.assertEqual(self.state(G1, T1), "merged")

    def test_the_same_with_a_file_changed_after_the_merge_is_kept_and_listed(self):
        self.check_a_changed_worktree_is_kept_and_listed()

    def test_a_tracked_file_changed_after_the_merge_is_kept(self):
        made = self.built()
        self.merge()
        (Path(made.path) / "README.md").write_text("edited\n", encoding="utf-8")
        self.assertFalse(gg.remove_after_merged(self.root, G1, T1).removed)

    def sweep_states(self):
        """One task in each state that keeps its worktree, each with work in it."""
        out = {}
        for task, (new, reason, kw) in {
            T1: ("in review", "checked", {"branch": gg.task_branch(G1, T1), "tip": self.main_tip()}),
            T2: ("failed", "builder", {}), T3: ("stopped", "kill", {}),
        }.items():
            made = self.built(task)
            self.move(G1, task, new, reason, **kw)
            out[task] = (new, made)
        self.goals(1, 2)  # G-0002: a task that needs the owner, and one still running
        for task, new in (("T-01", "needs owner"), ("T-02", "running")):
            made = self.built(task, G2)
            if new == "needs owner":
                self.move(G2, task, "needs owner", "ask")
            out[G2 + task] = (new, made)
        return out

    def every_removal_leaves_it(self, goal, task, made):
        self.assertFalse(gg.remove_after_merged(self.root, goal, task).removed)
        self.assertFalse(gg.remove_unused(self.root, goal, task, made.base).removed)  # it holds the builder's commit
        self.assertTrue(os.path.isdir(made.path))
        self.assertIn(made.path, self.listing())

    def check_no_command_removes_the_worktree_of_an_unmerged_task(self, sub=True):
        for key, (state, made) in self.sweep_states().items():
            goal, task = (G2, key[len(G2):]) if key.startswith(G2) else (G1, key)
            with (self.subTest(state=state, task=key) if sub else contextlib.nullcontext()):
                self.every_removal_leaves_it(goal, task, made)
                self.assertEqual(self.state(goal, task), state)

    def test_the_worktree_of_a_failed_stopped_in_review_or_needs_owner_task_is_never_removed(self):
        self.check_no_command_removes_the_worktree_of_an_unmerged_task()

    def test_a_queued_task_and_a_task_with_no_file_are_not_merged(self):
        made = self.start(G1, T1)
        self.assertEqual(gg.remove_after_merged(self.root, G1, T1).why, "not merged")
        self.assertEqual(gg.remove_after_merged(self.root, "G-0099", "T-01").why, "not merged")
        self.assertTrue(os.path.isdir(made.path))

    def test_a_worktree_made_for_a_start_that_failed_before_the_builder_is_removed_at_once(self):
        made = self.start()
        r = gg.remove_unused(self.root, G1, T1, made.base)
        self.assertEqual((r.removed, r.why), (True, "removed"))
        self.assertFalse(os.path.lexists(made.path))
        self.assertIn("umwayi/g-0001-t-01", self.branches())

    def test_an_unused_worktree_with_a_file_or_another_tip_is_kept(self):
        made = self.start()
        Path(made.path, "f").write_text("x\n", encoding="utf-8")
        self.assertEqual(gg.remove_unused(self.root, G1, T1, made.base).why, "not clean")
        Path(made.path, "f").unlink()
        git(made.path, "commit", "-q", "--allow-empty", "-m", "c")
        self.assertEqual(gg.remove_unused(self.root, G1, T1, made.base).why, "not at base")
        self.assertTrue(os.path.isdir(made.path))

    def test_a_worktree_removed_by_hand_is_gone_and_nothing_is_forced(self):
        made = self.built()
        self.merge()
        git(self.root, "worktree", "remove", made.path)
        self.assertEqual(gg.remove_after_merged(self.root, G1, T1).why, "gone")

    def test_a_locked_worktree_is_not_forced(self):
        made = self.built()
        self.merge()
        git(self.root, "worktree", "lock", made.path)
        r = gg.remove_after_merged(self.root, G1, T1)
        self.assertEqual((r.removed, r.why), (False, "git refused"))
        self.assertTrue(os.path.isdir(made.path))

    def test_no_argument_list_holds_a_force_flag(self):
        for name, (_, words, _) in gg.COMMANDS.items():
            self.assertFalse({"--force", "-f", "-ff"} & set(words), name)

    # ---- planted faults

    def test_fault_removal_at_in_review(self):
        with mock.patch.object(gg, "remove_after_merged", lambda root, goal, task: gg._remove_clean(root, goal, task, None)):
            self.caught(self.check_no_command_removes_the_worktree_of_an_unmerged_task, sub=False)

    def test_fault_removal_with_force(self):
        forced = ("root", ("worktree", "remove", "--force", "{PATH}"), True)
        with mock.patch.dict(gg.COMMANDS, {"worktree_remove": forced}), \
                mock.patch.object(gg, "_remove_clean", lambda root, goal, task, at: gg.Removal(
                    gg.run_git("worktree_remove", root, PATH=gg.worktree_path(gg.real_root(root), goal, task)).ok, "removed")):
            self.caught(self.check_a_changed_worktree_is_kept_and_listed)

    def test_fault_the_branch_deleted(self):
        real = gg.remove_after_merged

        def deleting(root, goal, task):
            r = real(root, goal, task)
            git(root, "branch", "-D", gg.task_branch(goal, task))
            return r

        with mock.patch.object(gg, "remove_after_merged", deleting):
            self.caught(self.check_merged_and_clean_is_removed_and_the_branch_stays)

    def test_fault_cleanup_of_a_failed_task(self):
        real = gg.remove_after_merged

        def eager(root, goal, task):
            return gg._remove_clean(root, goal, task, None)

        with mock.patch.object(gg, "remove_after_merged", eager):
            made = self.built()
            self.move(G1, T1, "failed", "builder")
            self.assertTrue(gg.remove_after_merged(self.root, G1, T1).removed)  # the fault: what the real one never does
        self.assertFalse(real(self.root, G1, T1).removed)


# ---------------------------------------------------------------------------------------------------- W9.R8.14


class SharingTests(GitGoalCase):
    def setUp(self):
        super().setUp()
        self.goals(3, 5)

    def check_invariants(self):
        paths = gg.worktrees(self.root)
        self.assertEqual(len(paths), len(set(paths)))
        self.assertLessEqual(len(paths), gg.MAX_WORKTREES)
        branches = [r.get("branch") for r in gg.listed(self.root) if r.get("branch") != "refs/heads/main"]
        self.assertEqual(len(branches), len(set(branches)))
        names = [os.path.basename(p) for p in paths]
        self.assertEqual(len(names), len(set(names)))
        real = gg.real_root(self.root)
        for g in (G1, G2, G3):
            for t in gs.list_tasks(self.root, g):
                if gs.read_task(self.root, g, t)["state"] not in ("queued", "merged"):
                    self.assertEqual(sum(1 for p in paths if p == gg.worktree_path(real, g, t)), 1, (g, t))

    def run_sequence(self, seed, steps=40):
        g = gen.Gen(seed)
        tasks = [(goal, f"T-{n:02d}") for goal in (G1, G2, G3) for n in range(1, 6)]
        for _ in range(steps):
            goal, task = g.pick(tasks)
            state = self.state(goal, task)
            op = g.pick(["start", "start", "stop", "fail", "review", "merge", "start-again"])
            if op in ("start", "start-again") and state == "queued":
                try:
                    base = gg.start_check(self.root, goal, task)
                    gg.make(self.root, goal, task, base)
                except gg.Refused as e:
                    self.assertEqual(e.reason, "leftover")
                    self.assertEqual(self.state(goal, task), "queued")
                else:
                    self.to_running(goal, task, base)
            elif op == "start-again" and state != "queued":
                with self.assertRaises(gg.Refused) as cm:  # a second start of a live task is refused
                    gg.start_check(self.root, goal, task)
                self.assertEqual(cm.exception.reason, "leftover")
            elif op == "stop" and state == "running":
                self.move(goal, task, "stopped", "kill")
            elif op == "fail" and state == "running":
                self.move(goal, task, "failed", "builder")
            elif op == "review" and state == "running":
                self.to_review(goal, task)
            elif op == "merge" and state == "in review":
                self.move(goal, task, "merged", "observed")
                self.assertTrue(gg.remove_after_merged(self.root, goal, task).removed)
            self.check_invariants()

    def test_no_two_live_tasks_share_a_path_a_branch_or_a_registration(self):
        for seed in (1, 2, 3):
            with self.subTest(seed=seed):
                self.run_sequence(seed)

    def test_tasks_with_the_same_number_in_two_goals_have_different_worktrees(self):
        a, b = self.start(G1, T1), self.start(G2, T1)
        self.assertNotEqual(a.path, b.path)
        self.assertEqual(len(gg.worktrees(self.root)), 2)

    def forge(self):
        obj = gs.read_task(self.root, G2, T1)
        gs.write_task(self.root, G2, T1, dict(obj, branch=gg.task_branch(G1, T1)))

    def check_another_task_file_naming_the_branch_stops_the_start(self):
        self.forge()
        with self.assertRaises(gg.Refused) as cm:
            gg.start_check(self.root, G1, T1)
        self.assertEqual(cm.exception.reason, "leftover")
        self.assertIn(("task-file", "G-0002 T-01"), cm.exception.found)

    def test_another_task_file_that_names_the_same_branch_stops_the_start(self):
        self.check_another_task_file_naming_the_branch_stops_the_start()

    def test_an_unreadable_task_file_stops_the_start(self):
        (Path(gs.goal_dir(self.root, G3)) / "T-05.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(gg.Refused) as cm:
            gg.start_check(self.root, G1, T1)
        self.assertIn(("task-file", "G-0003 T-05"), cm.exception.found)

    def test_a_task_is_not_its_own_other(self):
        base = gg.start_check(self.root, G1, T1)
        gg.make(self.root, G1, T1, base)
        self.to_running(G1, T1, base)
        obj = gs.read_task(self.root, G1, T1)
        gs.write_task(self.root, G1, T1, dict(obj, branch=gg.task_branch(G1, T1)))
        self.assertEqual(gg._other_tasks_name(self.root, G1, T1, self.wt(), gg.task_branch(G1, T1)), [])

    # ---- planted faults

    def test_fault_a_path_from_the_task_number_only(self):
        def check():
            real = gg.real_root(self.root)
            self.assertNotEqual(gg.worktree_path(real, G1, T1), gg.worktree_path(real, G2, T1))

        with mock.patch.object(gg, "worktree_name", lambda goal, task=None: task.lower()):
            self.caught(check)

    def test_fault_the_task_files_of_other_goals_not_read(self):
        with mock.patch.object(gg, "_other_tasks_name", lambda *a, **k: []):
            self.caught(self.check_another_task_file_naming_the_branch_stops_the_start)


# ---------------------------------------------------------------------------------------------------- W9.R8.15


class PlanTests(GitGoalCase):
    def check_the_plan_worktree_is_its_own_and_goes_away(self):
        before = self.owner_state()
        branches = self.branches()
        base = gg.start_check(self.root, G1)
        made = gg.make_plan(self.root, G1, base)
        self.assertEqual(made.path, self.wtroot + "/g-0001-plan")
        self.assertIsNone(made.branch)
        self.assertNotEqual(made.path, str(self.root))
        self.assertEqual(self.branches(), branches)  # no branch
        self.assertEqual(subprocess.run(["git", "-C", made.path, "symbolic-ref", "-q", "HEAD"],
                                        capture_output=True).returncode, 1)  # detached
        self.assertEqual(git(made.path, "rev-parse", "HEAD"), base)
        self.assertEqual(self.owner_state(), before)
        r = gg.remove_plan(self.root, G1, base)
        self.assertEqual((r.removed, r.why), (True, "removed"))
        self.assertFalse(os.path.lexists(made.path))
        self.assertEqual(self.branches(), branches)

    def test_a_planning_run_has_a_worktree_of_its_own_and_it_goes_away(self):
        self.check_the_plan_worktree_is_its_own_and_goes_away()

    def check_a_changed_plan_stays_and_is_listed(self):
        base = gg.start_check(self.root, G1)
        made = gg.make_plan(self.root, G1, base)
        Path(made.path, "the-guide-wrote-this.txt").write_text("x\n", encoding="utf-8")
        r = gg.remove_plan(self.root, G1)
        self.assertEqual((r.removed, r.why), (False, "not clean"))
        self.assertIn(made.path, gg.worktrees(self.root))

    def test_a_plan_whose_tree_changed_stays_as_evidence_and_is_listed(self):
        self.check_a_changed_plan_stays_and_is_listed()

    def test_the_plan_and_a_task_of_the_same_goal_do_not_collide(self):
        base = gg.start_check(self.root, G1)
        plan = gg.make_plan(self.root, G1, base)
        task = gg.make(self.root, G1, T1, gg.start_check(self.root, G1, T1))
        self.assertNotEqual(plan.path, task.path)
        self.assertEqual(len(gg.worktrees(self.root)), 2)
        with self.assertRaises(gg.Refused):
            gg.start_check(self.root, G1)

    def test_a_plan_at_another_base_than_given_is_kept(self):
        base = gg.start_check(self.root, G1)
        made = gg.make_plan(self.root, G1, base)
        git(made.path, "commit", "-q", "--allow-empty", "-m", "c")
        self.assertEqual(gg.remove_plan(self.root, G1, base).why, "not at base")

    def test_fault_the_plan_worktree_forced_away(self):
        forced = ("root", ("worktree", "remove", "--force", "{PATH}"), True)
        with mock.patch.dict(gg.COMMANDS, {"worktree_remove": forced}), \
                mock.patch.object(gg, "_remove_clean", lambda root, goal, task, at: gg.Removal(
                    gg.run_git("worktree_remove", root, PATH=gg.worktree_path(gg.real_root(root), goal, task)).ok, "removed")):
            self.caught(self.check_a_changed_plan_stays_and_is_listed)

    def test_fault_planning_in_the_root(self):
        def in_root(root, goal, base):
            return gg.Made(str(root), base, None)

        with mock.patch.object(gg, "make_plan", in_root):
            self.caught(self.check_the_plan_worktree_is_its_own_and_goes_away)


# ---------------------------------------------------------------------------------------------------- W9.R8.16 (files)


class TrackedOnlyTests(RepoMixin, FakeRoot):
    def setUp(self):
        super().setUp()
        self.init_repo()
        (self.root / ".gitignore").write_text("node_modules/\n.env\n", encoding="utf-8")
        git(self.root, "add", ".gitignore")
        git(self.root, "commit", "-q", "-m", "ignore")
        (self.root / "node_modules").mkdir()
        (self.root / "node_modules" / "pkg.js").write_text("x\n", encoding="utf-8")
        (self.root / ".env").write_text("SECRET=1\n", encoding="utf-8")
        (self.root / "scratch.txt").write_text("untracked\n", encoding="utf-8")

    def check_only_tracked_files(self):
        made = self.start()
        names = set(os.listdir(made.path)) - {".git"}
        self.assertEqual(names, {"README.md", "src", ".gitignore"})
        self.assertEqual([p for p, _, _ in os.walk(made.path) if os.path.islink(p)], [])
        self.assertEqual(gg.dirty(self.root, G1, T1), None)

    def test_a_worktree_holds_the_tracked_files_of_base_and_nothing_else(self):
        self.check_only_tracked_files()

    def test_fault_a_link_of_an_ignored_folder_into_the_worktree(self):
        real = gg.make

        def linking(root, goal, task, base):
            made = real(root, goal, task, base)
            os.symlink(os.path.join(str(root), "node_modules"), os.path.join(made.path, "node_modules"))
            return made

        with mock.patch.object(gg, "make", linking):
            self.caught(self.check_only_tracked_files)

    def test_fault_a_copy_of_an_ignored_file_into_the_worktree(self):
        real = gg.make

        def copying(root, goal, task, base):
            made = real(root, goal, task, base)
            shutil.copy(os.path.join(str(root), ".env"), made.path)
            return made

        with mock.patch.object(gg, "make", copying):
            self.caught(self.check_only_tracked_files)


if __name__ == "__main__":
    unittest.main()
