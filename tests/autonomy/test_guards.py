"""Layer 13, slice 5: the guard names of the adapters (13.R12.5, 13.R14.3, design.md "The adapters"). The example rules
of the three adapters, and the starter rules of the repo `rules.yaml` that copy them, keep an AI helper from
writing `autonomy.yaml` and from running `umwayi autonomy`. The record is the owner's; a helper never feeds it."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

from tests.autonomy.support import REPO

SHELL = [
    ("claude_code", {"type": "tool_bash", "platform": "claude-code", "tool": "Bash"}, "command", "cc-no-guard-shell"),
    ("kiro", {"type": "tool_execute_bash", "platform": "kiro", "tool": "execute_bash"}, "input_command",
     "kiro-no-guard-shell"),
    ("stdio", {"type": "tool_bash", "platform": "stdio", "tool": "bash"}, "input_command", "stdio-no-owner-commands"),
]
EDIT = [
    ("claude_code", {"type": "tool_write", "platform": "claude-code", "tool": "Write"}, "path", "cc-no-guard-edits"),
    ("kiro", {"type": "tool_fs_write", "platform": "kiro", "tool": "fs_write"}, "input_path", "kiro-no-guard-edits"),
]
COMMANDS = ("umwayi autonomy record --class git-commit --outcome approved --by me",
            "python -m umwayi --root . autonomy record --class c --outcome approved --by me",
            "umwayi autonomy status", "echo 'enabled: true' > autonomy.yaml", "cp autonomy.example.yaml autonomy.yaml")
PATHS = ("/home/me/root/autonomy.yaml", "autonomy.example.yaml", "/home/me/root/AUTONOMY.YAML")


class GuardTests(unittest.TestCase):
    def check(self, rules, action):
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run([sys.executable, "-m", "umwayi", "--root", tmp, "check", json.dumps(action), "--rules",
                                str(rules), "--no-log", "--json"], capture_output=True, text=True,
                               env=dict(os.environ, PYTHONPATH=str(REPO), HOME=tmp))
            data = json.loads(r.stdout)
            return r.returncode, data["answer"], data["rule_id"]

    def test_a_helper_cannot_run_umwayi_autonomy_or_touch_autonomy_yaml_by_shell(self):
        for adapter, action, field, rule in SHELL:
            for rules in (REPO / "adapters" / adapter / "rules.example.yaml", REPO / "rules.yaml"):
                for command in COMMANDS:
                    with self.subTest(adapter=adapter, rules=rules.name, command=command[:30]):
                        self.assertEqual(self.check(rules, {**action, field: command}), (2, "No", rule))

    def test_a_helper_cannot_write_autonomy_yaml(self):
        for adapter, action, field, rule in EDIT:
            for rules in (REPO / "adapters" / adapter / "rules.example.yaml", REPO / "rules.yaml"):
                for path in PATHS:
                    with self.subTest(adapter=adapter, rules=rules.name, path=path):
                        self.assertEqual(self.check(rules, {**action, field: path}), (2, "No", rule))

    def test_a_petition_is_still_the_owners_choice(self):
        adapter, action, field, _rule = SHELL[0]
        code, answer, rule = self.check(REPO / "adapters" / adapter / "rules.example.yaml",
                                        {**action, field: "umwayi petition no-money --helper h --reason r"})
        self.assertEqual((code, answer), (3, "Ask me first"))
