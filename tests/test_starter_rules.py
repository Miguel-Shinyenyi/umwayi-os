"""Task 9.10: the starter rules for adapter actions in the repo rules.yaml.

Written before the rules (tests first). It loads the repo `rules.yaml` with the real parser, checks that every
rule loads and that ids are unique, that every rule of the three adapter example files is in the repo file with the
same verdict and matchers, and that a table of adapter actions gets the expected answer. Actions are built with the
real adapter code (`tool_action` and `generic_action`), so the test sends what the adapters send. No clock is
needed: the starter rules have no `review_by`.
"""

import re
import unittest
from pathlib import Path

from adapters.common import umwayi_gate as gate
from umwayi.rules import ASK, NO, YES, decide, load_rules, parse_rules

REPO = Path(__file__).resolve().parent.parent
RULES_FILE = REPO / "rules.yaml"
EXAMPLES = [REPO / "adapters" / name / "rules.example.yaml" for name in ("claude_code", "kiro", "stdio")]

# The rules that were in the file before 9.10, in their order. They must stay first and unchanged.
OLD_IDS = [
    "no-money", "no-money-amount", "no-push-main", "no-publish", "read-memory", "write-draft", "run-safe-jobs",
    "publish-ask", "schedule-install-ask", "schedule-remove-yes", "helper-read", "helper-draft", "helper-no-post",
    "helper-no-post-command", "workflow-steps",
]


def cc(tool, **fields):
    return gate.tool_action("claude-code", tool, fields)


def kiro(tool, **fields):
    return gate.generic_action("kiro", tool, fields)


def stdio(tool, **fields):
    return gate.generic_action("stdio", tool, fields)


# (name, action, expected answer, expected rule id or None for "no rule matches")
TABLE = [
    # Claude Code: reading and listing
    ("cc read", cc("Read", file_path="/repo/src/a.py"), YES, "cc-read"),
    ("cc glob", cc("Glob", pattern="**/*.py"), YES, "cc-read"),
    ("cc grep", cc("Grep", pattern="todo", path="/repo/src"), YES, "cc-read"),
    # Claude Code: writing
    ("cc write", cc("Write", file_path="/repo/src/a.py"), ASK, "cc-ask-write"),
    ("cc edit", cc("Edit", file_path="/repo/src/a.py"), ASK, "cc-ask-write"),
    ("cc multiedit", cc("MultiEdit", file_path="/repo/src/a.py"), ASK, "cc-ask-write"),
    ("cc notebookedit", cc("NotebookEdit", notebook_path="/repo/n.ipynb"), ASK, "cc-ask-write"),
    # Claude Code: shell and web
    ("cc bash", cc("Bash", command="npm test"), ASK, "cc-ask-shell"),
    ("cc powershell", cc("PowerShell", command="Get-ChildItem"), ASK, "cc-ask-shell"),
    ("cc webfetch", cc("WebFetch", url="https://example.com"), ASK, "cc-ask-web"),
    ("cc websearch", cc("WebSearch", query="python"), ASK, "cc-ask-web"),
    ("cc install", cc("Bash", command="pip install requests"), ASK, "cc-ask-shell"),
    ("cc delete one file", cc("Bash", command="rm old.txt"), ASK, "cc-ask-shell"),
    # Claude Code: No
    ("cc push main", cc("Bash", command="git push origin main"), NO, "cc-no-push-main"),
    ("cc force push", cc("Bash", command="git push --force origin feature"), NO, "cc-no-push-main"),
    ("cc rm -rf", cc("Bash", command="rm -rf build"), NO, "cc-no-destroy"),
    ("cc rm -rf upper case", cc("Bash", command="RM -RF build"), NO, "cc-no-destroy"),
    ("cc money", cc("Bash", command="curl https://api.stripe.com/v1/charges"), NO, "cc-no-money"),
    ("cc write rules.yaml", cc("Edit", file_path="/repo/rules.yaml"), NO, "cc-no-guard-edits"),
    ("cc write logbook", cc("Write", file_path="/repo/LOGBOOK.md"), NO, "cc-no-guard-edits"),
    ("cc write hook settings", cc("Write", file_path="/repo/.claude/settings.json"), NO, "cc-no-guard-edits"),
    ("cc write .umwayi", cc("Write", file_path="/repo/.umwayi/kill_switch"), NO, "cc-no-guard-edits"),
    ("cc write .git", cc("Write", file_path="/repo/.git/config"), NO, "cc-no-guard-edits"),
    ("cc shell names rules.yaml", cc("Bash", command="sed -i s/no/yes/ rules.yaml"), NO, "cc-no-guard-shell"),
    ("cc shell kill switch", cc("Bash", command="umwayi kill off"), NO, "cc-no-guard-shell"),
    ("cc read .env", cc("Read", file_path="/repo/.env"), NO, "cc-no-secrets"),
    ("cc read pem", cc("Read", file_path="/home/me/server.pem"), NO, "cc-no-secrets"),
    ("cc read id_rsa", cc("Read", file_path="/home/me/.ssh/id_rsa"), NO, "cc-no-secrets"),
    ("cc read id_ed25519", cc("Read", file_path="/home/me/.ssh/id_ed25519"), NO, "cc-no-secrets"),
    ("cc read aws", cc("Read", file_path="/home/me/.aws/credentials"), NO, "cc-no-secrets"),
    ("cc read netrc", cc("Grep", pattern="x", path="/home/me/.netrc"), NO, "cc-no-secrets"),
    ("cc write .env", cc("Write", file_path="/repo/.env"), NO, "cc-no-secrets"),
    # Claude Code: not listed, so Ask me first
    ("cc mcp tool", cc("mcp__github__create_issue"), ASK, None),
    ("cc subagent", cc("Agent", subagent_type="general"), ASK, None),
    ("cc new tool", cc("BrandNewTool"), ASK, None),
    # Kiro
    ("kiro read_file", kiro("read_file", path="src/a.py"), YES, "kiro-read"),
    ("kiro grep_search", kiro("grep_search", query="todo"), YES, "kiro-read"),
    ("kiro fs_write", kiro("fs_write", path="src/a.py"), ASK, "kiro-ask-write"),
    ("kiro fs_append", kiro("fs_append", path="src/a.py"), ASK, "kiro-ask-write"),
    ("kiro str_replace", kiro("str_replace", path="src/a.py"), ASK, "kiro-ask-write"),
    ("kiro delete_file", kiro("delete_file", path="src/a.py"), ASK, "kiro-ask-write"),
    ("kiro execute_bash", kiro("execute_bash", command="npm test"), ASK, "kiro-ask-shell"),
    ("kiro execute_pwsh", kiro("execute_pwsh", command="Get-ChildItem"), ASK, "kiro-ask-shell"),
    ("kiro rm -rf", kiro("execute_bash", command="rm -rf build"), NO, "kiro-no-destroy"),
    ("kiro shell names rules.yaml", kiro("execute_bash", command="cat rules.yaml"), NO, "kiro-no-guard-shell"),
    ("kiro shell names hooks", kiro("execute_bash", command="rm .kiro/hooks/a.json"), NO, "kiro-no-guard-shell"),
    ("kiro write rules.yaml", kiro("fs_write", path="rules.yaml"), NO, "kiro-no-guard-edits"),
    ("kiro write hooks", kiro("str_replace", path=".kiro/hooks/a.json"), NO, "kiro-no-guard-edits"),
    ("kiro read .env", kiro("read_file", path="/repo/.env"), NO, "kiro-no-secrets"),
    ("kiro read id_rsa", kiro("read_file", path="/home/me/.ssh/id_rsa"), NO, "kiro-no-secrets"),
    ("kiro mcp tool", kiro("mcp_github_create_issue"), ASK, None),
    ("kiro other tool", kiro("web_search", query="x"), ASK, None),
    # generic stdin and stdout adapter (platform name stdio)
    ("stdio read", stdio("read", path="notes.txt"), YES, "stdio-read"),
    ("stdio deploy staging", stdio("deploy", target="staging"), ASK, "stdio-ask-deploy"),
    ("stdio deploy prod", stdio("deploy", target="prod"), NO, "stdio-no-prod"),
    ("stdio read .env", stdio("read", path="/repo/.env"), NO, "stdio-no-secrets"),
    ("stdio read key", stdio("read", path="/home/me/.ssh/id_rsa"), NO, "stdio-no-secrets"),
    ("stdio unknown tool", stdio("wipe", target="staging"), ASK, None),
    # a platform name that has no rules is not trusted
    ("other platform read", gate.tool_action("someone-else", "Read", {"file_path": "/repo/a.py"}), ASK, None),
]


class StarterRulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = RULES_FILE.read_text(encoding="utf-8")
        cls.rules = load_rules(RULES_FILE)
        cls.by_id = {r.id: r for r in cls.rules}

    def test_every_rule_loads_and_ids_are_unique(self):
        ids = [r.id for r in self.rules]
        self.assertEqual(len(ids), len(set(ids)), "duplicate rule ids")
        self.assertEqual(len(parse_rules(self.text)), len(ids))
        for oid in OLD_IDS:
            self.assertIn(oid, ids)
        self.assertGreater(len(ids), len(OLD_IDS))

    def test_old_rules_stay_first_and_in_order(self):
        self.assertEqual([r.id for r in self.rules][: len(OLD_IDS)], OLD_IDS)

    def test_every_rule_has_title_text_and_cause_in_plain_words(self):
        for r in self.rules:
            if r.id in OLD_IDS:
                continue  # the old rules are unchanged, whatever they have
            for name in ("title", "text", "cause"):
                value = getattr(r, name)
                self.assertTrue(value and value.strip(), f"{r.id}: no {name}")
            self.assertTrue(r.matchers, f"{r.id}: no matchers, it would never match")

    def test_no_em_dash_and_no_review_by_in_the_file(self):
        self.assertNotIn("\u2014", self.text)
        self.assertNotIn("\u2013", self.text)
        for r in self.rules:
            self.assertIsNone(r.review_by, f"{r.id}: review_by is not wanted on a starter rule")
        self.assertIsNone(re.search(r"^\s*review_by:", self.text, re.M))

    def test_no_secret_in_the_file_and_only_known_verdicts(self):
        for r in self.rules:
            self.assertIn(r.verdict, (YES, NO, ASK))

    def test_every_example_rule_is_in_the_repo_file_with_the_same_verdict_and_matchers(self):
        for path in EXAMPLES:
            examples = parse_rules(path.read_text(encoding="utf-8"))
            self.assertTrue(examples, path.name)
            for ex in examples:
                with self.subTest(rule=ex.id):
                    self.assertIn(ex.id, self.by_id, f"{ex.id} from {path.parent.name} is not in rules.yaml")
                    self.assertEqual(self.by_id[ex.id].verdict, ex.verdict)
                    self.assertEqual(self.by_id[ex.id].matchers, ex.matchers)

    def test_yes_rules_of_the_adapters_are_reads_only(self):
        for r in self.rules:
            if r.id.startswith(("cc-", "kiro-", "stdio-")) and r.verdict == YES:
                types = [m for m in r.matchers if m.field == "type"]
                self.assertEqual(len(types), 1, r.id)
                for v in types[0].values:
                    self.assertRegex(str(v).lower(), r"read|glob|grep", r.id)

    def test_table_of_adapter_actions(self):
        for name, action, answer, rule_id in TABLE:
            with self.subTest(action=name):
                d = decide(self.rules, action, today="2026-11-11")
                self.assertEqual(d.answer, answer, f"{name}: {d.answer} by {d.rule_id}")
                if rule_id is None:
                    self.assertIsNone(d.rule_id, f"{name}: matched {d.matched}")
                else:
                    self.assertEqual(d.rule_id, rule_id, f"{name}: matched {d.matched}")

    def test_unknown_actions_still_give_ask_me_first(self):
        for action in ({"type": "never_heard_of_it"}, {"type": "tool_mcp", "platform": "claude-code"},
                       {"platform": "kiro"}, {}, {"type": "tool_read", "platform": "other"}):
            with self.subTest(action=action):
                d = decide(self.rules, action, today="2026-11-11")
                self.assertEqual(d.answer, ASK)
                self.assertIsNone(d.rule_id)

    def test_adapter_rules_never_match_actions_of_another_platform(self):
        for r in self.rules:
            if r.id.startswith(("cc-", "kiro-", "stdio-")):
                self.assertTrue(any(m.field == "platform" for m in r.matchers) or r.id == "cc-no-money", r.id)

    def test_old_rules_still_answer_as_before(self):
        cases = [
            ({"type": "payment", "amount": 5}, NO, "no-money"),
            ({"type": "git_push", "branch": "main"}, NO, "no-push-main"),
            ({"type": "read_memory"}, YES, "read-memory"),
            ({"type": "publish_draft"}, ASK, "publish-ask"),
            ({"type": "run_job", "command": "report"}, YES, "run-safe-jobs"),
        ]
        for action, answer, rule_id in cases:
            d = decide(self.rules, action, today="2026-11-11")
            self.assertEqual((d.answer, d.rule_id), (answer, rule_id))


if __name__ == "__main__":
    unittest.main()
