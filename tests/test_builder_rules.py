"""W57: the startswith and prefix matchers, cwd in the Claude Code action, and the builder rules example.

The operators are tested with the real parser and decide(); the example is tested with the real Claude Code hook and
the real `umwayi check`, on a root whose rules.yaml is the repo starter rules with the builder rules added.
"""

import hashlib
import re
import unittest
from pathlib import Path

from umwayi.errors import UmwayiError
from umwayi.rules import ASK, NO, YES, decide, parse_rules

from tests.adapters.test_claude_code import AdapterBase, call

REPO = Path(__file__).resolve().parent.parent
EXAMPLE = REPO / "goal.rules.example.yaml"
PLACEHOLDER = "/path/to/umwayi-root-worktrees"
TODAY = "2026-11-15"
# The bytes of the repo rules.yaml, pinned: W57 adds operators but leaves every starter rule as it was. Changed once on
# purpose by W78 step 1B (the owner's rules change of Nov 17), which appends twelve No rules after every old rule.
RULES_SHA256 = "af91f13171ba4d0bd7f19596e3f54c0e5674e47f561e3b223ed1be853f681ced"


def rule(matchers: str, verdict: str = "yes", rid: str = "r1") -> str:
    return (f"rules:\n  - id: {rid}\n    title: T\n    text: X.\n    verdict: {verdict}\n    matchers:\n"
            + "".join(f"      {line}\n" for line in matchers.strip().splitlines()))


def answer(text: str, action: dict) -> str:
    return decide(parse_rules(text), action, today=TODAY).answer


def builder_rules(worktrees: str) -> str:
    """The commented builder rules of the example file, uncommented, with the placeholder replaced."""
    lines = EXAMPLE.read_text(encoding="utf-8").splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("# Builder rules (W57)"))
    start = next(i for i in range(start, len(lines)) if lines[i] == "# rules:")
    out = [l[2:] if l.startswith("# ") else l[1:] for l in lines[start:]]
    return "\n".join(out).replace(PLACEHOLDER, worktrees) + "\n"


def without(text: str, *ids: str) -> str:
    for rid in ids:
        text, n = re.subn(rf"\n  - id: {re.escape(rid)}\n(?:    .*\n|\n)*?(?=  - id: |  #)", "\n", text)
        assert n == 1, rid
    return text


class StartsWithTests(unittest.TestCase):
    TEXT = rule('type: tool_bash\ncommand__startswith: ["git status ", "git diff "]')

    def test_matches_the_start_only(self):
        self.assertEqual(answer(self.TEXT, {"type": "tool_bash", "command": "git status --short"}), YES)
        self.assertEqual(answer(self.TEXT, {"type": "tool_bash", "command": "git diff HEAD"}), YES)
        self.assertEqual(answer(self.TEXT, {"type": "tool_bash", "command": "echo git status x"}), ASK)
        self.assertEqual(answer(self.TEXT, {"type": "tool_bash", "command": "git difftool x"}), ASK)

    def test_case_and_spaces_as_written(self):
        self.assertEqual(answer(self.TEXT, {"type": "tool_bash", "command": "GIT status x"}), ASK)
        self.assertEqual(answer(self.TEXT, {"type": "tool_bash", "command": " git status x"}), ASK)

    def test_one_printable_line_only(self):
        for cmd in ("git status x\nrm -rf y", "git status x\rrm y", "git status\tx", "git status x\x00"):
            self.assertEqual(answer(self.TEXT, {"type": "tool_bash", "command": cmd}), ASK, repr(cmd))

    def test_not_text_never_matches(self):
        for v in (None, 5, True, ["x"], {"a": 1}):
            self.assertEqual(answer(self.TEXT, {"type": "tool_bash", "command": v}), ASK, v)
        self.assertEqual(answer(self.TEXT, {"type": "tool_bash"}), ASK)

    def test_a_list_field_matches_when_one_item_does(self):
        self.assertEqual(answer(self.TEXT, {"type": "tool_bash", "command": ["ls", "git diff a"]}), YES)

    def test_bad_values_are_refused_at_load(self):
        for bad in ('""', '"  "', "5", "true", "[]", '["ok", 3]', '"a\\nb"', '"a\\tb"', "{a: 1}"):
            with self.assertRaises(UmwayiError, msg=bad):
                parse_rules(rule(f"command__startswith: {bad}"))


class PrefixTests(unittest.TestCase):
    TEXT = rule("type: tool_write\npath__prefix: [/w/trees, /other/]")

    def test_at_or_below_the_folder(self):
        for p in ("/w/trees", "/w/trees/", "/w/trees/g-0001-t-01/a.py", "/other/x"):
            self.assertEqual(answer(self.TEXT, {"type": "tool_write", "path": p}), YES, p)

    def test_outside_the_folder(self):
        for p in ("/w/treesx/a", "/w/tree", "/w", "/", "w/trees/a", "trees/a", "/W/trees/a", "/otherx"):
            self.assertEqual(answer(self.TEXT, {"type": "tool_write", "path": p}), ASK, p)

    def test_a_path_that_is_not_clean_never_matches(self):
        for p in ("/w/trees/../../etc/passwd", "/w/trees/./a", "/w/trees//a", "//w/trees/a", "/w/trees/a\nb", ""):
            self.assertEqual(answer(self.TEXT, {"type": "tool_write", "path": p}), ASK, repr(p))

    def test_not_text_never_matches(self):
        for v in (None, 5, ["x"]):
            self.assertEqual(answer(self.TEXT, {"type": "tool_write", "path": v}), ASK, v)

    def test_root_folder(self):
        self.assertEqual(answer(rule("path__prefix: /"), {"path": "/a/b"}), YES)

    def test_bad_folders_are_refused_at_load(self):
        for bad in ("w/trees", "./w", "/w/../x", "/w/./x", "//w", "/w//x", '""', "5", "[]", '"/a\\nb"'):
            with self.assertRaises(UmwayiError, msg=bad):
                parse_rules(rule(f"path__prefix: {bad}"))


class OldOperatorTests(unittest.TestCase):
    """The operators of before behave as they did: equals and contains ignore case and outer spaces."""

    def test_equals_contains_exists(self):
        text = rule("type: TOOL_BASH\ncommand__contains: Rm -Rf\nplatform__exists: true")
        self.assertEqual(answer(text, {"type": " tool_bash ", "command": "sudo RM -rf /", "platform": "x"}), YES)
        self.assertEqual(answer(text, {"type": "tool_bash", "command": "sudo RM -rf /"}), ASK)
        with self.assertRaises(UmwayiError):
            parse_rules(rule("command__contains: '  '"))


class UnknownOperatorTests(unittest.TestCase):
    """An unknown `__word` is not refused at load (it was not before W57 either): it is read as an equals matcher on a
    field with that whole name. No adapter sends such a field, so it never matches an adapter's action."""

    def test_loads_and_never_matches_a_real_action(self):
        for op in ("not", "endswith", "regex", "STARTSWITH", "prefixx", "startswith_"):
            text = rule(f"type: tool_bash\ncommand__{op}: git")
            rules = parse_rules(text)
            self.assertEqual(rules[0].matchers[1].field, f"command__{op}")
            self.assertEqual(rules[0].matchers[1].op, "equals")
            for cmd in ("git", "git status", "rm -rf /", "x git"):
                self.assertEqual(answer(text, {"type": "tool_bash", "platform": "claude-code", "command": cmd}), ASK)


class StarterRulesUnchangedTests(unittest.TestCase):
    def test_rules_yaml_bytes_are_pinned(self):
        self.assertEqual(hashlib.sha256((REPO / "rules.yaml").read_bytes()).hexdigest(), RULES_SHA256)

    def test_starter_rules_use_no_new_operator(self):
        for r in parse_rules((REPO / "rules.yaml").read_text(encoding="utf-8")):
            for m in r.matchers:
                self.assertIn(m.op, ("equals", "contains", "exists"), r.id)


class ExampleTests(unittest.TestCase):
    def test_the_example_reads_as_no_rules(self):
        self.assertEqual(parse_rules(EXAMPLE.read_text(encoding="utf-8")), [])

    def test_builder_rules_parse(self):
        rules = parse_rules(builder_rules("/w/trees"))
        self.assertEqual([r.id for r in rules],
                         ["builder-no-chain", "builder-no-git-output", "builder-write", "builder-shell",
                          "builder-shell-bare"])
        self.assertEqual([r.verdict for r in rules], [NO, NO, YES, YES, YES])
        for r in rules:
            self.assertIn(("cwd", "prefix", ("/w/trees",)), [(m.field, m.op, m.values) for m in r.matchers], r.id)

    def test_the_no_chain_list(self):
        no = parse_rules(builder_rules("/w/trees"))[0]
        want = {"&", ";", "|", "`", "$(", ">"}
        self.assertEqual(set(next(m.values for m in no.matchers if m.op == "contains")), want)


class BuilderHookTests(AdapterBase):
    """The real Claude Code hook and the real `umwayi check`, with Claude Code's documented hook input."""

    def setUp(self):
        super().setUp()
        self.trees = str(self.tmp / "home-worktrees")
        self.tree = self.trees + "/g-0001-t-01"
        self.starter = (REPO / "rules.yaml").read_text(encoding="utf-8")
        self.use(without(self.starter, "cc-ask-write", "cc-ask-shell"))

    def use(self, text):
        (self.root / "rules.yaml").write_text(text.rstrip("\n") + "\n" + builder_rules(self.trees).split("\n", 1)[1],
                                              encoding="utf-8")

    def ask(self, tool, tool_input, cwd="tree"):
        payload = call(tool, tool_input)
        if cwd == "tree":
            payload["cwd"] = self.tree
        elif cwd is None:
            del payload["cwd"]
        else:
            payload["cwd"] = cwd
        return self.decision(self.hook(payload))

    def test_cwd_changes_the_answer(self):
        self.assertEqual(self.ask("Bash", {"command": "git status"}), "allow")
        self.assertEqual(self.ask("Bash", {"command": "git status"}, cwd="/tmp"), "ask")
        self.assertEqual(self.ask("Bash", {"command": "git status"}, cwd=None), "ask")

    def test_a_cwd_that_is_not_clean_is_left_out(self):
        for cwd in (self.tree + "/../../x", self.tree + "/./a", "relative/" + self.tree, "/" + self.tree, 5,
                    self.tree + "\n", ["/x"]):
            self.assertEqual(self.ask("Bash", {"command": "git status"}, cwd=cwd), "ask", repr(cwd))

    def test_the_five_commands(self):
        for cmd in ("git status", "git status --short", "git diff", "git diff HEAD~1", "git add a.py",
                    "git commit -m 'W1: a change'", "python3 -m unittest", "python3 -m unittest tests.test_x"):
            self.assertEqual(self.ask("Bash", {"command": cmd}), "allow", cmd)

    def test_other_commands_are_asked(self):
        for cmd in ("ls", "git difftool", "git log", "python3 x.py", "git statusx", "git status x\nrm y"):
            self.assertEqual(self.ask("Bash", {"command": cmd}), "ask", cmd)

    def test_chain_characters_are_no(self):
        for cmd in ("git status && rm x", "git status & rm x", "git status; rm x", "git diff | sh",
                    "git commit -m `id`", "git commit -m $(id)", "git diff > /etc/x", "git diff --output=/etc/x"):
            self.assertEqual(self.ask("Bash", {"command": cmd}), "deny", cmd)

    def test_writes(self):
        self.assertEqual(self.ask("Write", {"file_path": self.tree + "/a.py", "content": "x"}), "allow")
        self.assertEqual(self.ask("Edit", {"file_path": self.tree + "/a.py", "old_string": "x", "new_string": "y"}),
                         "allow")
        self.assertEqual(self.ask("Write", {"file_path": "/tmp/a.py", "content": "x"}), "ask")
        self.assertEqual(self.ask("Write", {"file_path": self.tree + "/../../a.py", "content": "x"}), "ask")
        self.assertEqual(self.ask("Write", {"file_path": self.tree + "/a.py", "content": "x"}, cwd="/tmp"), "ask")

    def test_starter_no_rules_still_win(self):
        self.assertEqual(self.ask("Write", {"file_path": self.tree + "/.git/config", "content": "x"}), "deny")
        self.assertEqual(self.ask("Write", {"file_path": self.tree + "/.env", "content": "x"}), "deny")
        self.assertEqual(self.ask("Bash", {"command": "git commit -m 'edit rules.yaml'"}), "deny")

    def test_with_the_starter_ask_rules_kept_nothing_is_allowed(self):
        self.use(self.starter)
        self.assertEqual(self.ask("Bash", {"command": "git status"}), "ask")
        self.assertEqual(self.ask("Write", {"file_path": self.tree + "/a.py", "content": "x"}), "ask")
        self.assertEqual(self.ask("Bash", {"command": "git status; rm x"}), "deny")


if __name__ == "__main__":
    unittest.main()
