"""tools/goal_rules.py: the rules.yaml of a goal root, built from the repo's own rules.yaml (the pinned file is not changed)."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from tools import goal_rules as gr
from umwayi.rules import ASK, NO, YES, decide, parse_rules

REPO = Path(__file__).resolve().parent.parent
TREES = "/work/proj-worktrees"
TREE = TREES + "/g-0001-t-01"
TODAY = "2026-11-26"
REPO_RULES = (REPO / "rules.yaml").read_text(encoding="utf-8")
EXAMPLE = (REPO / "goal.rules.example.yaml").read_text(encoding="utf-8")


def built(**kw):
    args = dict(worktrees=TREES, guide="g-guide", builder="g-builder", tester="g-tester")
    args.update(kw)
    return gr.build(REPO_RULES, EXAMPLE, **args)


def answer(rules, action):
    return decide(rules, action, today=TODAY).answer


def bash(cmd, cwd=TREE):
    return {"type": "tool_bash", "platform": "claude-code", "cwd": cwd, "command": cmd}


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.text = built()
        self.rules = parse_rules(self.text)
        self.old = parse_rules(REPO_RULES)

    def test_the_two_ask_rules_are_dropped_and_nothing_else_is_lost(self):
        ids = [r.id for r in self.rules]
        self.assertNotIn("cc-ask-write", ids)
        self.assertNotIn("cc-ask-shell", ids)
        self.assertEqual([r.id for r in self.rules[:len(self.old) - 2]], [r.id for r in self.old if r.id not in gr.DROP])

    def test_every_no_rule_of_the_repo_file_stays_unchanged(self):
        old_no = {r.id: r for r in self.old if r.verdict == NO}
        new_no = {r.id: r for r in self.rules if r.verdict == NO}
        for rid, r in old_no.items():
            self.assertEqual(new_no[rid], r, rid)

    def test_the_repo_rules_file_is_not_touched(self):
        self.assertEqual(hashlib.sha256((REPO / "rules.yaml").read_bytes()).hexdigest(),
                         hashlib.sha256(REPO_RULES.encode("utf-8")).hexdigest())

    def test_the_added_rules(self):
        added = [r.id for r in self.rules[len(self.old) - 2:]]
        self.assertEqual(added, ["builder-no-chain", "builder-no-git-output", "builder-write", "builder-shell",
                                 "builder-shell-bare", "builder-unittest-nobytecode", "builder-unittest-nobytecode-bare",
                                 "builder-git-read", "builder-git-read-bare", "goal-agents-run", "goal-agents-start",
                                 "goal-budget-check"])

    def test_the_worktree_folder_is_in_every_builder_rule_and_the_placeholder_is_gone(self):
        self.assertNotIn(gr.PLACEHOLDER, self.text)
        for r in self.rules:
            if r.id.startswith("builder-"):
                self.assertIn(("cwd", "prefix", (TREES,)), [(m.field, m.op, m.values) for m in r.matchers], r.id)


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.rules = parse_rules(built())

    def test_a_write_in_the_worktree_is_yes_and_elsewhere_is_ask(self):
        w = {"type": "tool_write", "platform": "claude-code", "cwd": TREE, "path": TREE + "/a.py"}
        self.assertEqual(answer(self.rules, w), YES)
        self.assertEqual(answer(self.rules, dict(w, cwd="/tmp/x", path="/tmp/x/a.py")), ASK)

    def test_the_commands_of_a_goal_task(self):
        for cmd in ("git status", "git diff main", "git add a.py", "git commit -m x", "python3 -m unittest tests.test_x",
                    "python3 -B -m unittest -v", "python3 -B -m unittest", "git log --oneline", "git show HEAD", "git ls-files"):
            self.assertEqual(answer(self.rules, bash(cmd)), YES, cmd)

    def test_other_commands_are_asked_and_chains_and_pushes_are_not_yes(self):
        self.assertEqual(answer(self.rules, bash("curl http://x")), ASK)
        self.assertEqual(answer(self.rules, bash("python3 -B -c 'print(1)'")), ASK)
        self.assertEqual(answer(self.rules, bash("git push origin umwayi/g-0001-t-01")), ASK)
        for cmd in ("git status; rm -rf x", "python3 -B -m unittest && echo hi", "git log | cat", "git show HEAD > out"):
            self.assertEqual(answer(self.rules, bash(cmd)), NO, cmd)

    def test_a_push_to_main_stays_no(self):
        self.assertEqual(answer(self.rules, bash("git push origin main")), NO)

    def test_the_named_agents_only(self):
        for agent in ("g-guide", "g-builder", "g-tester"):
            self.assertEqual(answer(self.rules, {"type": "agent_run", "agent": agent}), YES, agent)
            for role in ("guide", "builder", "tester", "check"):
                self.assertEqual(answer(self.rules, {"type": "goal_start", "agent": agent, "role": role}), YES)
        self.assertEqual(answer(self.rules, {"type": "agent_run", "agent": "someone-else"}), ASK)
        self.assertEqual(answer(self.rules, {"type": "goal_start", "agent": "someone-else", "role": "builder"}), ASK)
        self.assertEqual(answer(self.rules, {"type": "budget_check"}), YES)

    def test_goal_publish_and_a_merge_are_not_allowed_by_this_file(self):
        self.assertEqual(answer(self.rules, {"type": "goal_publish", "goal": "G-0001", "task": "T-01", "repo": "a/b",
                                             "branch": "umwayi/g-0001-t-01"}), ASK)


class ArgumentTests(unittest.TestCase):
    def test_bad_arguments_are_refused_without_echoing_them(self):
        for kw in ({"worktrees": "relative/path"}, {"worktrees": "/a/../b"}, {"worktrees": "/a//b"}, {"worktrees": "/a/b/"},
                   {"worktrees": "/a b"}, {"guide": "Bad Name"}, {"builder": ""}, {"tester": "g-guide"}):
            with self.assertRaises(gr.Usage, msg=str(kw)) as cm:
                built(**kw)
            for v in kw.values():
                if v:
                    self.assertNotIn(v, str(cm.exception))

    def test_out_is_refused_when_the_file_exists_and_written_otherwise(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "rules.yaml"
            args = ["--worktrees", TREES, "--guide", "g-guide", "--builder", "g-builder", "--tester", "g-tester", "--out", str(out)]
            self.assertEqual(gr.main(args), 0)
            self.assertEqual(out.read_text(encoding="utf-8"), built())
            self.assertEqual(gr.main(args), 64)

    def test_usage_error_is_64(self):
        self.assertEqual(gr.main(["--worktrees", TREES]), 64)


if __name__ == "__main__":
    unittest.main()


class PinnedFromHeadTests(unittest.TestCase):
    """A goal root whose rules.yaml was already changed (skip-worktree) must still give the same built rules."""

    def git(self, d, *args):
        import subprocess
        return subprocess.run(["git", "-C", str(d), *args], capture_output=True, text=True, check=True)

    def test_the_committed_text_is_read_not_the_changed_file(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.git(d, "init", "-q", "-b", "main")
            self.git(d, "config", "user.email", "t@example.invalid")
            self.git(d, "config", "user.name", "t")
            (d / "rules.yaml").write_text(REPO_RULES, encoding="utf-8")
            self.git(d, "add", "rules.yaml")
            self.git(d, "commit", "-qm", "pinned")
            (d / "rules.yaml").write_text("rules: []\n", encoding="utf-8")  # the goal root's own, already changed
            self.assertEqual(gr.pinned_rules_text(d), REPO_RULES)
            self.assertEqual(gr.build(gr.pinned_rules_text(d), EXAMPLE, TREES, "g-guide", "g-builder", "g-tester"), built())

    def test_without_a_git_commit_the_file_is_read(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "rules.yaml").write_text("rules: []\n", encoding="utf-8")
            self.assertEqual(gr.pinned_rules_text(d), "rules: []\n")
