"""W78 step 1B: the owner's commands denied to helpers, the W78 guard files, the always owner stop and the refusal shape.

Each rule has an oracle that raises AssertionError when the rules or the decide function it is given break the rule. The
repo rules.yaml and umwayi.rules must pass it, and a planted fault (one word dropped from a list, the floor removed, the
"Allowed next" cut from a text) must fail it. Real parser, real adapter actions, a real `umwayi check` child process.
Standard library only, no network.
"""
import dataclasses
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from adapters.common import umwayi_gate as gate  # noqa: E402
from umwayi import rules  # noqa: E402
from umwayi.rules import ASK, NO, YES, parse_rules  # noqa: E402

RULES = parse_rules((REPO / "rules.yaml").read_text(encoding="utf-8"))
PREFIXES = {"claude-code": "cc", "kiro": "kiro", "opencode": "oc", "stdio": "stdio"}
SHAPE = re.compile(r"^refused: .+\. Allowed next: .+\.$")
OWNER_WORDS = ["umwayi enforce set cooperative --agent a", "umwayi queue answer Q-0001 --answer yes",
               "umwayi goal approve G-0001", "umwayi goal answer G-0001 T-01 yes", "umwayi goal merged G-0001 T-01",
               "umwayi goal stop G-0001", "umwayi budget settle-lost", "umwayi kill off", "umwayi decision reopen Q-1",
               "umwayi autonomy record x", "gh pr merge 12", "script -q /dev/null umwayi goal approve G-1",
               "unbuffer umwayi queue answer Q-1", "script -q /dev/null bash", "unbuffer bash"]
GUARD_NAMES = ["guidance.yaml", "units.yaml", "agents.yaml", ".umwayi/enforcement.yaml", ".kiro/steering/umwayi/x.md"]


def shell(platform, command):
    if platform == "claude-code":
        return gate.tool_action("claude-code", "Bash", {"command": command})
    tool = {"kiro": "execute_bash", "opencode": "bash", "stdio": "shell"}[platform]
    a = gate.generic_action(platform, tool, {"command": command})
    if platform == "opencode":
        a["type"] = "tool_shell"
    return a


def edit(platform, path):
    if platform == "claude-code":
        return gate.tool_action("claude-code", "Write", {"file_path": "/repo/" + path})
    tool = {"kiro": "fs_write", "opencode": "write", "stdio": "write"}[platform]
    a = gate.generic_action(platform, tool, {"path": "/repo/" + path})
    if platform == "opencode":
        a["type"] = "tool_write"
    return a


# ----------------------------------------------------------------------------------------------- the oracles


def owner_commands_are_no(rule_list, decide):
    for platform, p in PREFIXES.items():
        for cmd in OWNER_WORDS:
            d = decide(rule_list, shell(platform, cmd), "2026-11-17")
            assert d.answer == NO, f"{platform}: {cmd!r} gave {d.answer} ({d.rule_id})"


def guard_files_are_no(rule_list, decide):
    for platform in PREFIXES:
        for name in GUARD_NAMES + ["tools/merge_main.py"]:
            d = decide(rule_list, edit(platform, name), "2026-11-17")
            assert d.answer == NO, f"{platform}: an edit of {name} gave {d.answer} ({d.rule_id})"
        for name in GUARD_NAMES:
            d = decide(rule_list, shell(platform, f"sed -i s/a/b/ {name}"), "2026-11-17")
            assert d.answer == NO, f"{platform}: a shell command naming {name} gave {d.answer} ({d.rule_id})"


def always_owner_stop(rule_list, decide):
    yes_all = parse_rules("rules:\n" + "".join(
        f"  - id: yes-{p}\n    title: t\n    text: t\n    verdict: yes\n    matchers:\n      platform: {platform}\n"
        for platform, p in PREFIXES.items()))
    for platform in PREFIXES:
        for cmd in OWNER_WORDS[:11]:  # the pseudo-terminal words are not owner commands, only denied by the rules
            d = decide(yes_all, shell(platform, cmd), "2026-11-17")
            assert d.answer == ASK and d.rule_id == rules.OWNER_STOP_ID, f"{platform}: {cmd!r} gave {d.answer} under a Yes rule"
        assert decide(yes_all, shell(platform, "ls -la"), "2026-11-17").answer == YES, "the floor lowered a plain command"
        assert decide(yes_all, edit(platform, "src/a.py"), "2026-11-17").answer == YES, "the floor lowered an edit"
    no_all = parse_rules("rules:\n  - id: n\n    title: t\n    text: t\n    verdict: no\n    matchers:\n      platform: kiro\n")
    assert decide(no_all, shell("kiro", "umwayi goal approve G-1"), "2026-11-17").answer == NO, "the floor raised a No"
    assert not rules.names_owner_command({"type": "tool_bash", "command": "umwayi goal approve G-1"}), \
        "the floor applied to an action of no helper platform"


def refusals_have_the_shape(rule_list, decide):
    new = [r for r in rule_list if r.id.endswith("-w78")]
    assert len(new) == 3 * len(PREFIXES), f"{len(new)} W78 rules"
    for r in new:
        assert SHAPE.match(r.text), f"{r.id}: {r.text!r}"
    assert SHAPE.match(rules.OWNER_STOP_REASON)


def _drop(rule_list, rule_id, word):
    out = []
    for r in rule_list:
        if r.id == rule_id:
            ms = tuple(dataclasses.replace(m, values=tuple(v for v in m.values if v != word)) for m in r.matchers)
            r = dataclasses.replace(r, matchers=ms)
        out.append(r)
    return out


def _cut_text(rule_list):
    return [dataclasses.replace(r, text=r.text.split(" Allowed next")[0]) if r.id == "kiro-no-guard-files-shell-w78" else r
            for r in rule_list]


ORACLES = {
    "owner_commands": (owner_commands_are_no, lambda: ([r for r in RULES if r.id != "oc-no-owner-commands-w78"], rules.decide)),
    "owner_commands_pty": (owner_commands_are_no, lambda: (_drop(RULES, "cc-no-owner-commands-w78", "unbuffer"), rules.decide)),
    "guard_files": (guard_files_are_no, lambda: (_drop(RULES, "kiro-no-guard-file-edits-w78", "agents.yaml"), rules.decide)),
    "guard_files_tools": (guard_files_are_no, lambda: (_drop(RULES, "cc-no-guard-file-edits-w78", "/tools/"), rules.decide)),
    "guard_shell": (guard_files_are_no, lambda: (_drop(RULES, "stdio-no-guard-files-shell-w78", "units.yaml"), rules.decide)),
    "always_owner_stop": (always_owner_stop, lambda: (RULES, rules._decide)),
    "refusal_shape": (refusals_have_the_shape, lambda: (_cut_text(RULES), rules.decide)),
}


class RulesTests(unittest.TestCase):
    pass


def _add(name, oracle, planted):
    def real(self):
        oracle(RULES, rules.decide)

    def fault(self):
        rule_list, decide = planted()
        with self.assertRaises(AssertionError, msg=f"the oracle of {name} accepted its planted fault"):
            oracle(rule_list, decide)
    setattr(RulesTests, f"test_{name}_holds", real)
    setattr(RulesTests, f"test_{name}_planted_fault_is_caught", fault)


for _n, (_o, _p) in ORACLES.items():
    _add(_n, _o, _p)


class CheckCommandTests(unittest.TestCase):
    """The answer through the real `umwayi check` child process: the exit code is 2 (No), never 1."""

    def test_an_owner_command_from_each_helper_is_exit_2(self):
        import json
        import shutil
        import tempfile
        tmp = tempfile.TemporaryDirectory(prefix="umwayi-owner-stop-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        shutil.copy2(REPO / "rules.yaml", root / "rules.yaml")  # a temporary root: the check writes its logbook there
        for platform in PREFIXES:
            r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(root), "check", "--json",
                                json.dumps(shell(platform, "umwayi enforce set cooperative"))],
                               capture_output=True, text=True, timeout=60, cwd=root,
                               env={**__import__("os").environ, "PYTHONPATH": str(REPO)})
            self.assertEqual(r.returncode, 2, (platform, r.stdout, r.stderr))
            self.assertIn("Allowed next:", json.loads(r.stdout)["reason"])

    def test_the_old_rules_are_unchanged_and_the_new_ones_come_last(self):
        ids = [r.id for r in RULES]
        new = [i for i in ids if i.endswith("-w78")]
        self.assertEqual(ids[-len(new):], new)

    def test_no_em_dash(self):
        for name in ("tests/test_owner_stop.py", "rules.yaml", "umwayi/rules.py"):
            self.assertNotIn("\u2014", (REPO / name).read_text(encoding="utf-8"), name)


if __name__ == "__main__":
    unittest.main()
