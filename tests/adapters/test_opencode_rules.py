"""Layer 10 part 8, task 10.45: adapters/opencode/rules.example.yaml, the starter rules for `platform: opencode`.

Loaded with the real parser (like tests/test_starter_rules.py does for the repo rules). Actions are built with the real
code that makes them: gate.generic_action for the first gate (the plugin runs the generic adapter with
`--platform opencode`) and agents.permission_action for the permission request. The tool names and field names are the
ones seen on OpenCode 2.2.7 (adapters/NOTES-layer10.md, 10.42).
"""

import re
import unittest

from adapters.common import umwayi_gate as gate
from umwayi import agents
from umwayi.rules import ASK, NO, YES, decide, load_rules, parse_rules

from tests.adapters.support import REPO

EXAMPLE = REPO / "adapters" / "opencode" / "rules.example.yaml"


def tool(name, **fields):
    return gate.generic_action("opencode", name, fields)


def perm(kind, name=None):
    call = {"kind": kind}
    if name:
        call["name"] = name
    return agents.permission_action("o", call, "opencode")


# (label, action, answer, deciding rule or None)
TABLE = [
    # Yes: reading and listing
    ("read", tool("read", path="/repo/src/a.py"), YES, "oc-read"),
    ("glob", tool("glob", pattern="**/*.py", path="/repo"), YES, "oc-read"),
    ("grep", tool("grep", pattern="todo", path="/repo/src"), YES, "oc-read"),
    # No: secret and key paths, for every tool that has a path
    ("read .env", tool("read", path="/repo/.env"), NO, "oc-no-secrets"),
    ("read .env.local", tool("read", path="/repo/.env.local"), NO, "oc-no-secrets"),
    ("read pem", tool("read", path="/home/me/server.pem"), NO, "oc-no-secrets"),
    ("read id_rsa", tool("read", path="/home/me/.ssh/id_rsa"), NO, "oc-no-secrets"),
    ("read id_ed25519", tool("read", path="/home/me/.ssh/id_ed25519"), NO, "oc-no-secrets"),
    ("read aws", tool("read", path="/home/me/.aws/credentials"), NO, "oc-no-secrets"),
    ("grep in netrc", tool("grep", pattern="x", path="/home/me/.netrc"), NO, "oc-no-secrets"),
    ("glob in a key folder", tool("glob", pattern="*", path="/home/me/keys/id_rsa"), NO, "oc-no-secrets"),
    ("write .env", tool("write", path="/repo/.env", content="K=V"), NO, "oc-no-secrets"),
    ("read ENV upper case", tool("read", path="/repo/.ENV"), NO, "oc-no-secrets"),
    # No: the files that guard the AI helper
    ("write rules.yaml", tool("write", path="/repo/rules.yaml", content="x"), NO, "oc-no-guard-edits"),
    ("edit LOGBOOK.md", tool("edit", path="LOGBOOK.md", oldString="a", newString="b"), NO, "oc-no-guard-edits"),
    ("edit logbook lower case", tool("edit", path="/repo/logbook.md"), NO, "oc-no-guard-edits"),
    ("write .umwayi", tool("write", path=".umwayi/kill_switch", content="off"), NO, "oc-no-guard-edits"),
    ("write opencode.json", tool("write", path="/repo/opencode.json", content="{}"), NO, "oc-no-guard-edits"),
    ("write opencode.jsonc", tool("write", path="opencode.jsonc", content="{}"), NO, "oc-no-guard-edits"),
    ("write .opencode plugin", tool("write", path="/repo/.opencode/plugins/x.js", content="x"), NO, "oc-no-guard-edits"),
    ("edit .opencode config", tool("edit", path=".opencode/opencode.jsonc"), NO, "oc-no-guard-edits"),
    ("edit .git config", tool("edit", path="/repo/.git/config"), NO, "oc-no-guard-edits"),
    ("shell names rules.yaml", tool("shell", command="sed -i s/no/yes/ rules.yaml"), NO, "oc-no-guard-shell"),
    ("shell names logbook", tool("shell", command="echo x >> LOGBOOK.md"), NO, "oc-no-guard-shell"),
    ("shell names .umwayi", tool("shell", command="rm -r .umwayi"), NO, "oc-no-guard-shell"),
    ("shell names opencode.json", tool("shell", command="cat opencode.json"), NO, "oc-no-guard-shell"),
    ("shell names opencode.jsonc", tool("shell", command="echo '{}' > opencode.jsonc"), NO, "oc-no-guard-shell"),
    ("shell names .opencode", tool("shell", command="mkdir -p .opencode/plugins"), NO, "oc-no-guard-shell"),
    ("shell umwayi kill", tool("shell", command="umwayi kill off"), NO, "oc-no-guard-shell"),
    ("shell umwayi decision", tool("shell", command="umwayi decision list"), NO, "oc-no-guard-shell"),
    ("shell decision reopen", tool("shell", command="python -m umwayi decision reopen Q-1 --why x"), NO, "oc-no-guard-shell"),
    ("shell umwayi autonomy", tool("shell", command="umwayi autonomy status"), NO, "oc-no-guard-shell"),
    ("shell autonomy record", tool("shell", command="umwayi autonomy record a b"), NO, "oc-no-guard-shell"),
    ("shell names autonomy.yaml", tool("shell", command="echo x > autonomy.yaml"), NO, "oc-no-guard-shell"),
    ("shell names autonomy.example.yaml", tool("shell", command="cp autonomy.example.yaml y"), NO, "oc-no-guard-shell"),
    ("write autonomy.yaml", tool("write", path="/repo/autonomy.yaml", content="x"), NO, "oc-no-guard-edits"),
    ("edit autonomy.example.yaml", tool("edit", path="autonomy.example.yaml"), NO, "oc-no-guard-edits"),
    # No: destroying, pushing to main, money
    ("rm -rf", tool("shell", command="rm -rf build"), NO, "oc-no-destroy"),
    ("rm -rf upper case", tool("shell", command="RM -RF build"), NO, "oc-no-destroy"),
    ("mkfs", tool("shell", command="mkfs.ext4 /dev/sda1"), NO, "oc-no-destroy"),
    ("chmod 777", tool("shell", command="chmod -R 777 /"), NO, "oc-no-destroy"),
    ("push main", tool("shell", command="git push origin main"), NO, "oc-no-push-main"),
    ("push master", tool("shell", command="git push origin master"), NO, "oc-no-push-main"),
    ("force push", tool("shell", command="git push --force origin feature"), NO, "oc-no-push-main"),
    ("money", tool("shell", command="curl https://api.stripe.com/v1/charges"), NO, "oc-no-money"),
    # Ask me first: writing, the shell (installing, publishing and sending go through it), the web, helpers
    ("write", tool("write", path="/repo/src/a.py", content="x"), ASK, "oc-ask-write"),
    ("edit", tool("edit", path="/repo/src/a.py", oldString="a", newString="b"), ASK, "oc-ask-write"),
    ("shell", tool("shell", command="npm test"), ASK, "oc-ask-shell"),
    ("install", tool("shell", command="pip install requests"), ASK, "oc-ask-shell"),
    ("publish", tool("shell", command="npm publish"), ASK, "oc-ask-shell"),
    ("delete one file", tool("shell", command="rm old.txt"), ASK, "oc-ask-shell"),
    ("send", tool("shell", command="mail -s hi me@example.com"), ASK, "oc-ask-shell"),
    ("webfetch", tool("webfetch", url="https://example.com"), ASK, "oc-ask-web"),
    ("subagent", tool("subagent", agent="general", description="d", prompt="p"), ASK, "oc-ask-agent"),
    ("question", tool("question"), ASK, "oc-ask-agent"),
    # Code Mode and tools never seen asking: no rule on purpose, so Ask me first, and an owner's Yes can take effect
    ("execute", tool("execute", code="1+1"), ASK, None),
    ("execute with fetch", tool("execute", code="await fetch('http://x')"), ASK, None),
    ("worktree_list", tool("opencode_worktree_list"), ASK, None),
    ("worktree_remove", tool("opencode_worktree_remove", directory="/x"), ASK, None),
    ("session_move", tool("opencode_session_move", directory="/x"), ASK, None),
    ("patch", tool("patch", path="/repo/a.py"), ASK, None),
    ("list", tool("list", path="/repo"), ASK, None),
    ("websearch", tool("websearch", query="python"), ASK, None),
    ("skill", tool("skill", id="x"), ASK, None),
    ("mcp tool", tool("github_create_issue", title="x"), ASK, None),
    ("new tool", tool("brand_new_tool"), ASK, None),
    # the permission request (second gate)
    ("permission read", perm("read", "read"), YES, "oc-perm-read"),
    ("permission search", perm("search", "grep"), YES, "oc-perm-read"),
    ("permission edit", perm("edit", "write"), ASK, "oc-perm-ask"),
    ("permission delete", perm("delete"), ASK, "oc-perm-ask"),
    ("permission move", perm("move"), ASK, "oc-perm-ask"),
    ("permission execute", perm("execute", "shell"), ASK, "oc-perm-ask"),
    ("permission fetch", perm("fetch", "webfetch"), ASK, "oc-perm-ask"),
    ("permission think", perm("think", "subagent"), ASK, "oc-perm-ask"),
    ("permission other", perm("other", "execute"), ASK, "oc-perm-ask"),
    ("permission switch_mode", perm("switch_mode"), ASK, "oc-perm-ask"),
    ("permission a kind never seen", perm("brand_new_kind"), ASK, None),
    ("permission with no kind", agents.permission_action("o", {}, "opencode"), ASK, None),
    # a platform that is not OpenCode gets nothing from these rules
    ("kiro read", gate.generic_action("kiro", "read", {"path": "/repo/a.py"}), ASK, None),
    ("stdio read", gate.generic_action("stdio", "read", {"path": "/repo/a.py"}), ASK, None),
    ("claude-code read", gate.tool_action("claude-code", "Read", {"file_path": "/repo/a.py"}), ASK, None),
    ("kiro secret read", gate.generic_action("kiro", "read", {"path": "/repo/.env"}), ASK, None),
    ("claude permission", agents.permission_action("o", {"kind": "read"}, "claude-code"), ASK, None),
    ("kiro permission", agents.permission_action("o", {"kind": "read"}, "kiro"), ASK, None),
]


class ExampleRulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = EXAMPLE.read_text(encoding="utf-8")
        cls.rules = load_rules(EXAMPLE)

    def test_every_rule_loads_and_ids_are_unique_and_start_with_oc(self):
        ids = [r.id for r in self.rules]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(parse_rules(self.text)), len(ids))
        for rule_id in ids:
            self.assertRegex(rule_id, r"^oc-[a-z-]+$")

    def test_every_rule_has_a_title_a_text_a_cause_and_matchers_and_names_the_platform(self):
        for r in self.rules:
            with self.subTest(rule=r.id):
                for name in ("title", "text", "cause"):
                    self.assertTrue(getattr(r, name) and getattr(r, name).strip(), f"{r.id}: no {name}")
                self.assertTrue(r.matchers)
                platform = [m for m in r.matchers if m.field == "platform"]
                self.assertEqual(len(platform), 1)
                self.assertEqual(platform[0].values, ("opencode",))

    def test_no_em_dash_no_review_by_and_only_known_verdicts(self):
        self.assertNotIn("\u2014", self.text)
        self.assertNotIn("\u2013", self.text)
        self.assertIsNone(re.search(r"^\s*review_by:", self.text, re.M))
        for r in self.rules:
            self.assertIn(r.verdict, (YES, NO, ASK))
            self.assertIsNone(r.review_by)

    def test_the_only_yes_rules_are_reading_and_a_read_permission(self):
        yes = {r.id for r in self.rules if r.verdict == YES}
        self.assertEqual(yes, {"oc-read", "oc-perm-read"})

    def test_there_is_no_rule_for_code_mode_so_that_an_owners_yes_can_take_effect(self):
        # Ask me first beats Yes: an Ask rule for these types would make any Yes of the owner's useless
        types = [(m.op, v) for r in self.rules for m in r.matchers if m.field == "type" for v in m.values]
        self.assertNotIn(("equals", "tool_execute"), types)
        self.assertFalse([v for op, v in types if "tool_opencode_" in str(v)])

    def test_the_table_of_actions(self):
        for label, action, answer, rule_id in TABLE:
            with self.subTest(action=label):
                d = decide(self.rules, action, today="2026-11-11")
                self.assertEqual(d.answer, answer, f"{label}: {d.answer} by {d.rule_id}, matched {d.matched}")
                self.assertEqual(d.rule_id, rule_id, f"{label}: matched {d.matched}")

    def test_an_owner_yes_for_code_mode_takes_effect_beside_the_example_rules(self):
        owner = parse_rules(
            "rules:\n  - id: owner-yes-worktree-list\n    title: Listing worktrees is fine\n"
            "    text: OpenCode may list the worktrees of a repository.\n    cause: Listing changes nothing.\n"
            "    verdict: yes\n    matchers:\n      platform: opencode\n      type: tool_opencode_worktree_list\n")
        rules = self.rules + owner
        self.assertEqual(decide(rules, tool("opencode_worktree_list"), today="2026-11-11").answer, YES)
        self.assertEqual(decide(rules, tool("opencode_worktree_remove", directory="/x"), today="2026-11-11").answer, ASK)

    def test_a_secret_path_is_a_no_whatever_else_is_said(self):
        owner = parse_rules(
            "rules:\n  - id: owner-yes-everything\n    title: all\n    text: all\n    cause: test\n    verdict: yes\n"
            "    matchers:\n      platform: opencode\n      type: [tool_read, tool_write]\n")
        d = decide(self.rules + owner, tool("read", path="/repo/.env"), today="2026-11-11")
        self.assertEqual((d.answer, d.rule_id), (NO, "oc-no-secrets"))

    def test_every_tool_name_of_the_asked_list_has_a_rule_or_is_a_deliberate_default(self):
        # the nine tools OpenCode asks permission for: each is Yes, Ask or No by a rule, or Ask by the default
        for name in ("read", "glob", "grep", "write", "edit", "shell", "webfetch", "question", "subagent"):
            d = decide(self.rules, tool(name), today="2026-11-11")
            self.assertIn(d.answer, (YES, ASK), name)
            self.assertIsNotNone(d.rule_id, name)  # none of the nine falls to the default

    def test_the_fields_the_rules_look_at_are_the_ones_seen_on_2_2_7(self):
        used = {m.field for r in self.rules for m in r.matchers}
        self.assertEqual(used, {"platform", "type", "kind", "input_path", "input_command"})


if __name__ == "__main__":
    unittest.main()
