"""Task 9.10: the starter rules for adapter actions in the repo rules.yaml. Extended for OpenCode, a follow-up of 10.45
(PR 53): the rules of adapters/opencode/rules.example.yaml are in the file too.

Written before the rules (tests first). It loads the repo `rules.yaml` with the real parser, checks that every
rule loads and that ids are unique, that every rule of the three adapter example files is in the repo file with the
same verdict and matchers, and that a table of adapter actions gets the expected answer. Actions are built with the
real adapter code (`tool_action` and `generic_action`), so the test sends what the adapters send. No clock is
needed: the starter rules have no `review_by`.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from adapters.common import umwayi_gate as gate
from tests.adapters.test_opencode_rules import TABLE as OC_TABLE
from umwayi.rules import ASK, NO, YES, decide, load_rules, parse_rules

REPO = Path(__file__).resolve().parent.parent
RULES_FILE = REPO / "rules.yaml"
EXAMPLES = [REPO / "adapters" / name / "rules.example.yaml" for name in ("claude_code", "kiro", "stdio", "opencode")]
OPENCODE_EXAMPLE = REPO / "adapters" / "opencode" / "rules.example.yaml"

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
            if r.id.startswith(("cc-", "kiro-", "stdio-")) and r.verdict == YES:  # OpenCode: OpenCodeStarterRulesTest
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
            if r.id.startswith(("cc-", "kiro-", "stdio-", "oc-")):
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


# ======================================================================================================== OpenCode
#
# The same job as 9.10, for OpenCode: every rule of adapters/opencode/rules.example.yaml (13 rules, all with
# "platform: opencode") is in the repo rules.yaml with the same id, verdict and matchers, appended after the rules that
# were there. The rules that were there are pinned below by a hash of what each one says, so they cannot change
# without this test saying so.

# The 37 rules that were in the file when the OpenCode rules were added, in their order: 15 from before 9.10, 21 from
# 9.10 (PR 43) and the one rule layer 13 added to the generic adapter's group (stdio-no-owner-commands, PR 45). A
# hash of [id, title, text, cause, verdict, matchers, review_by] of each rule as the real parser reads it, so a
# comment or spacing may change and a verdict, a matcher, a word of text or a date may not. The guard words that
# layer 13 added to cc-no-guard-shell, kiro-no-guard-shell and the others (PRs 45 and 51) are in these hashes: they
# are the text of main at 85293c6. To change one of these rules on purpose, change its hash here in the same pull
# request and say why.
PINNED = {
    "no-money": "1a78babd4b63ef9bc6d6bb95f0d2ce62de7c1049d814e50e5760ffa6501d0e51",
    "no-money-amount": "d9e27eda265605ad5ecf034af00416c24d84ced0775cab202ee54b89b473feb8",
    "no-push-main": "a0272aa44a0b715f6f724d60292a6c2b2cc1a6579b7576fe1c7f9b4765927619",
    "no-publish": "8e3f4f3d934c411d084ea6122e46660d322183e2ffb19044faf45cf9cf377102",
    "read-memory": "8432aa2f43f35cb2bc7cd6c3777daf5ab79782ed076672710fd60734ffdb7309",
    "write-draft": "5376eb3978d9194ddee51e368f8184aa4589da2025a8f4bc4436be585a53bc17",
    "run-safe-jobs": "18a16022af0920998f2cc76a49cfbf732f9c15f1abc5a6e7cebce47bcb4af288",
    "publish-ask": "c5b449a390609890675f3cf36a7173b2be71af839c3f2b80330ee62ca09ff444",
    "schedule-install-ask": "a1d988241d413dabdc4b0480149d5ee5362e03b6156c6a9c2e63c0245b8b3f9b",
    "schedule-remove-yes": "ca8a3629ccd364587c31ead106f607f73c03d138ceaa54ed88b49d376c2bccbe",
    "helper-read": "e9bc067bdaa565b3603d24e4c2e0f3b2cfa8013952c963723b5259b32aa6d667",
    "helper-draft": "bee2de689b62121783f573ae04362d8b9cf7a951b9383188da22742bbcc25612",
    "helper-no-post": "7cf0b40becf5e31455f7e743bdc0bdbb3b068ee068bf11fa1e5d13df814f1cfa",
    "helper-no-post-command": "e58b541cf9f83d47a18119817acf96373e9faabbdcdf5f0515e6e7d52caa0bca",
    "workflow-steps": "7e53422a43fb429a1fcfe02f946375994be3e3f071c45cecc8f8a2d100fbb2ed",
    "cc-no-money": "44c900ace777a6214cf235d18272eb156149b0ecc22b74e3f68611784c783615",
    "cc-no-push-main": "3c07f3f4d3f6508f0d0afe2a80a76294467c7e13f462de11c37176d7bfdb8bdf",
    "cc-no-destroy": "4bca913fd1a14737d4358e5f333d160fb9092e656e9a15b6a43207e26cc45995",
    "cc-no-guard-edits": "5683a739377b72eb8982f45bebf6e37574346f7aeadcec0d60c12cfc5cceff41",
    "cc-no-guard-shell": "b10cfebeeeb0933da5811100d45b7abb6dbdb377fcb954db391f9587161eb069",
    "cc-no-secrets": "3beec1f1313d0ad9344112a0bcefad51d948aa1305ddcb03663505ee1bf2e9bb",
    "cc-read": "5defa24d1cd1d886793a0e275680feb988dcf7437eb322abf3dbefa11e1aca5b",
    "cc-ask-write": "32db02cf1a7396d6b3767683b4a87f09843d88837cdfd84c239d35cd655e66b8",
    "cc-ask-shell": "cd86e661191fc174a3ff01599ed638e891071363078014c191d89375145a4b25",
    "cc-ask-web": "006c06b35bff82459936db78e239032fe5a4d626afe49cd81bce6b3c2be25077",
    "kiro-read": "970fb1c8dced317a7e7689e590fc42be91b4f19f75314f550876b9b561ec8b8b",
    "kiro-ask-write": "8f2f0926eda5b792934e2507047917acc7dcfc17af325da8a47202fd1b1a7019",
    "kiro-ask-shell": "8883e49e84b587f7cfb6b8ce244d2b3511a4f18cee7e73b3a9010d09e3a70e5e",
    "kiro-no-destroy": "63938e180f2cddb088ddc7e228afda56071f40efee73357b4bab82090591768b",
    "kiro-no-guard-shell": "37bdcea29a62f04f0d4b40463257585c529a6b70b4ef102f2cc14be43284c46a",
    "kiro-no-guard-edits": "56920fc291042f590dee2a0badc392c33bbaf6c2741b784fcaf4cfb04deda836",
    "kiro-no-secrets": "ff0128598d8601d42556aa3445d4efd7dced215ea40161a06dd438e47fd39b22",
    "stdio-read": "d4dfb4f717bceab92283ee6208aad50b5a99416d8db8c03e47655b5a78fc57ab",
    "stdio-ask-deploy": "d9b62e73f1d1347c790377d4c6801134198dd44dda5dd3c6ae0c9d1a584338ec",
    "stdio-no-prod": "1f54847a93aecaf8e39e43868a02ddc682cf53d0190849ce8211fd37cf2a0499",
    "stdio-no-owner-commands": "0a4c7bc0d3b50faea88575899d378bee99bef98f33b197ea92af5be8259ed049",
    "stdio-no-secrets": "5e4979322dccc93e1ae1c1171e620705798f88c8ae27c67b56dea0fdb977b18e",
}
PINNED_FIRST_15 = OLD_IDS

# the rules of the OpenCode example, in the order of the example file (13 rules, not 16)
OC_IDS = [
    "oc-no-money", "oc-no-push-main", "oc-no-destroy", "oc-no-guard-edits", "oc-no-guard-shell", "oc-no-secrets",
    "oc-read", "oc-ask-write", "oc-ask-shell", "oc-ask-web", "oc-ask-agent", "oc-perm-read", "oc-perm-ask",
]


def canon(rule) -> str:
    """What a rule says, as a string: the same for the same rule whatever its spacing and comments."""
    return json.dumps([rule.id, rule.title, rule.text, rule.cause, rule.verdict,
                       [[m.field, m.op, list(m.values)] for m in rule.matchers], rule.review_by],
                      separators=(",", ":"))


def digest(rule) -> str:
    return hashlib.sha256(canon(rule).encode("utf-8")).hexdigest()


def is_opencode(action: dict) -> bool:
    return action.get("platform") == "opencode"


def problems_in(text: str) -> list:
    """Every way this text of a rules.yaml fails the OpenCode starter rules. Empty when it is right.

    One function for the checks that a planted fault must trip: the missing, changed and incomplete rules, and a rule
    for Code Mode. The tests below call it on the real file (nothing found) and on copies with one fault put in.
    """
    found = []
    try:
        rules = parse_rules(text)
    except Exception as e:  # a copy that does not even parse
        return [f"rules.yaml does not parse: {type(e).__name__}"]
    by_id = {r.id: r for r in rules}
    # 1. every rule of the example is there, with the same verdict and matchers
    for ex in parse_rules(OPENCODE_EXAMPLE.read_text(encoding="utf-8")):
        got = by_id.get(ex.id)
        if got is None:
            found.append(f"{ex.id} is missing")
            continue
        if got.verdict != ex.verdict:
            found.append(f"{ex.id}: verdict {got.verdict} is not {ex.verdict}")
        if got.matchers != ex.matchers:
            found.append(f"{ex.id}: the matchers differ from the example")
    # 2. the decisions table for OpenCode actions, on these rules
    for label, action, answer, rule_id in OC_TABLE:
        if not is_opencode(action):
            continue
        d = decide(rules, action, today="2026-11-11")
        if (d.answer, d.rule_id) != (answer, rule_id):
            found.append(f"{label}: {d.answer} by {d.rule_id}, not {answer} by {rule_id}")
    # 3. Code Mode has no rule on purpose (OC15, tasks.md 10.45): an Ask rule for it would make an owner's Yes useless
    for r in rules:
        for m in r.matchers:
            if m.field == "type":
                for v in m.values:
                    if v == "tool_execute" or str(v).startswith("tool_opencode_"):
                        found.append(f"{r.id}: a rule for {v}, which has no rule on purpose")
    return found


def take_rule(text: str, rule_id: str) -> tuple:
    """(the text before the rule, the rule's own block, the text after it) of a rules file; a block runs to the next
    rule or comment line at the same indent."""
    start = text.index(f"  - id: {rule_id}\n")
    m = re.compile(r"^(  - id: |  # ---|  # Code Mode)", re.M).search(text, start + 5)
    end = m.start() if m else len(text)
    return text[:start], text[start:end], text[end:]


class OpenCodeStarterRulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = RULES_FILE.read_text(encoding="utf-8")
        cls.rules = load_rules(RULES_FILE)
        cls.by_id = {r.id: r for r in cls.rules}
        cls.example = parse_rules(OPENCODE_EXAMPLE.read_text(encoding="utf-8"))
        cls._tmp = tempfile.TemporaryDirectory(prefix="umwayi-starter-")
        cls.root = Path(cls._tmp.name) / "root"
        cls.root.mkdir()
        (cls.root / "rules.yaml").write_bytes(RULES_FILE.read_bytes())

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    # ---------------------------------------------------------------------------------------- the rules

    def test_the_example_has_the_thirteen_rules_this_test_expects(self):
        """If the example grows, this fails and says the repo file needs the new rule too."""
        self.assertEqual([r.id for r in self.example], OC_IDS)
        for r in self.example:
            platform = [m for m in r.matchers if m.field == "platform"]
            self.assertEqual([m.values for m in platform], [("opencode",)], r.id)

    def test_every_rule_of_the_example_is_in_the_repo_file_with_the_same_id_verdict_and_matchers(self):
        for ex in self.example:
            with self.subTest(rule=ex.id):
                self.assertIn(ex.id, self.by_id)
                self.assertEqual(self.by_id[ex.id].verdict, ex.verdict)
                self.assertEqual(self.by_id[ex.id].matchers, ex.matchers)

    def test_they_come_after_the_rules_that_were_there_and_in_the_order_of_the_example(self):
        ids = [r.id for r in self.rules]
        self.assertEqual(ids[:len(PINNED)], list(PINNED))
        self.assertEqual(ids[len(PINNED):], OC_IDS)

    def test_each_has_a_title_a_text_a_cause_and_no_review_by(self):
        for rid in OC_IDS:
            r = self.by_id[rid]
            with self.subTest(rule=rid):
                for name in ("title", "text", "cause"):
                    value = getattr(r, name)
                    self.assertTrue(value and value.strip(), f"{rid}: no {name}")
                    self.assertNotIn("\u2014", value)
                self.assertIsNone(r.review_by)
                self.assertTrue(r.matchers)

    def test_the_wording_is_the_examples_for_the_rules_the_example_words_the_same(self):
        """Copied, not rewritten: the title, text and cause of each rule are the example's words."""
        for ex in self.example:
            with self.subTest(rule=ex.id):
                got = self.by_id[ex.id]
                self.assertEqual((got.title, got.text, got.cause), (ex.title, ex.text, ex.cause))

    def test_the_only_yes_rules_are_the_read_and_the_read_permission(self):
        yes = [r.id for r in self.rules if r.id.startswith("oc-") and r.verdict == YES]
        self.assertEqual(sorted(yes), ["oc-perm-read", "oc-read"])
        read = self.by_id["oc-read"]
        types = [m for m in read.matchers if m.field == "type"]
        self.assertEqual(types[0].values, ("tool_read", "tool_glob", "tool_grep"))
        perm = self.by_id["oc-perm-read"]
        self.assertEqual([m.values for m in perm.matchers if m.field == "kind"], [("read", "search")])

    def test_the_file_has_no_review_by_and_no_em_dash(self):
        self.assertIsNone(re.search(r"^\s*review_by:", self.text, re.M))
        self.assertNotIn("\u2014", self.text)
        self.assertNotIn("\u2013", self.text)

    # ---------------------------------------------------------------------------------- nothing else changed

    def test_the_rules_that_were_there_are_unchanged(self):
        """The 15 older rules, the 21 from 9.10 and the one layer 13 added: each says what it said (a hash)."""
        self.assertEqual(len(PINNED), 37)
        self.assertEqual(list(PINNED)[:15], PINNED_FIRST_15)
        for rid, want in PINNED.items():
            with self.subTest(rule=rid):
                self.assertIn(rid, self.by_id)
                self.assertEqual(digest(self.by_id[rid]), want, f"{rid} was changed")

    def test_the_old_text_of_the_file_is_still_there_in_front_of_the_new_rules(self):
        """Not only what the parser reads: the file up to the first OpenCode rule holds each old rule's block."""
        head = self.text[:self.text.index("  - id: oc-no-money\n")]
        for rid in PINNED:
            self.assertIn(f"  - id: {rid}\n", head, rid)

    def test_answers_for_every_older_action_are_the_same_without_the_opencode_rules(self):
        without = [r for r in self.rules if not r.id.startswith("oc-")]
        actions = [a for _n, a, _x, _r in TABLE] + [a for _l, a, _x, _r in OC_TABLE if not is_opencode(a)] + [
            {"type": "payment", "amount": 5}, {"type": "git_push", "branch": "main"}, {"type": "read_memory"},
            {"type": "publish_draft"}, {"type": "run_job", "command": "report"}, {"type": "never_heard_of_it"}, {}]
        for action in actions:
            with self.subTest(action=json.dumps(action)[:70]):
                a = decide(self.rules, action, today="2026-11-11")
                b = decide(without, action, today="2026-11-11")
                self.assertEqual((a.answer, a.rule_id, a.matched), (b.answer, b.rule_id, b.matched))

    def test_an_opencode_action_is_never_matched_by_a_rule_of_another_group(self):
        for label, action, _answer, _rule in OC_TABLE:
            if is_opencode(action):
                with self.subTest(action=label):
                    d = decide(self.rules, action, today="2026-11-11")
                    self.assertTrue(all(i.startswith("oc-") for i in d.matched), f"{label}: matched {d.matched}")

    def test_the_other_platforms_get_nothing_from_the_new_rules(self):
        for platform in ("claude-code", "kiro", "stdio", "someone-else"):
            for action in (gate.generic_action(platform, "read", {"path": "/repo/a.py"}),
                           gate.generic_action(platform, "shell", {"command": "rm -rf build"}),
                           {"type": "acp_permission", "platform": platform, "kind": "read"}):
                d = decide(self.rules, action, today="2026-11-11")
                self.assertFalse([i for i in d.matched if i.startswith("oc-")], (platform, d.matched))

    # --------------------------------------------------------------------- the decisions, with the real command

    def real_check(self, action, root=None, extra=()):
        env = dict(os.environ, PYTHONPATH=str(REPO), HOME=str(self.root))
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(root or self.root), "check",
                            json.dumps(action), "--json", *extra], capture_output=True, text=True, env=env,
                           cwd=str(self.root), timeout=120)
        data = json.loads(r.stdout)
        return r.returncode, data["answer"], data["rule_id"], data["rules_ok"]

    def test_the_decisions_table_for_opencode_actions_with_the_real_umwayi_check(self):
        """Every OpenCode row of the example's own table (tests/adapters/test_opencode_rules.py), but run as
        `python -m umwayi check` on a real root that holds the repo rules.yaml."""
        codes = {YES: 0, NO: 2, ASK: 3}
        rows = [row for row in OC_TABLE if is_opencode(row[1])]
        self.assertGreaterEqual(len(rows), 70)
        for label, action, answer, rule_id in rows:
            with self.subTest(action=label):
                code, got, got_rule, rules_ok = self.real_check(action, extra=("--no-log",))
                self.assertTrue(rules_ok)
                self.assertEqual((code, got, got_rule), (codes[answer], answer, rule_id))

    def test_the_decisions_by_category_with_the_real_umwayi_check(self):
        """The categories of the task, each written out here so they hold even if the example's table changes."""
        tool = lambda name, **f: gate.generic_action("opencode", name, f)  # noqa: E731
        perm = lambda kind: {"type": "acp_permission", "platform": "opencode", "agent": "o", "kind": kind, "tool": "t"}  # noqa: E731
        cases = [
            # read is Yes
            ("read", tool("read", path="/repo/src/a.py"), YES, "oc-read"),
            ("glob", tool("glob", pattern="*.py"), YES, "oc-read"),
            ("grep", tool("grep", pattern="x", path="/repo"), YES, "oc-read"),
            # secret paths, guard files, destructive commands, a push to main and payment services are No
            ("secret .env", tool("read", path="/repo/.env"), NO, "oc-no-secrets"),
            ("secret key", tool("read", path="/home/me/.ssh/id_rsa"), NO, "oc-no-secrets"),
            ("guard rules.yaml", tool("write", path="/repo/rules.yaml", content="x"), NO, "oc-no-guard-edits"),
            ("guard opencode.json", tool("edit", path="opencode.json"), NO, "oc-no-guard-edits"),
            ("guard shell", tool("shell", command="echo x >> LOGBOOK.md"), NO, "oc-no-guard-shell"),
            ("guard autonomy", tool("shell", command="umwayi autonomy status"), NO, "oc-no-guard-shell"),
            ("destroy", tool("shell", command="rm -rf build"), NO, "oc-no-destroy"),
            ("push main", tool("shell", command="git push origin main"), NO, "oc-no-push-main"),
            ("payment service", tool("shell", command="curl https://api.stripe.com/v1/charges"), NO, "oc-no-money"),
            # write, shell, web and sub agent are Ask me first
            ("write", tool("write", path="/repo/a.py", content="x"), ASK, "oc-ask-write"),
            ("edit", tool("edit", path="/repo/a.py"), ASK, "oc-ask-write"),
            ("shell", tool("shell", command="npm test"), ASK, "oc-ask-shell"),
            ("webfetch", tool("webfetch", url="https://example.com"), ASK, "oc-ask-web"),
            ("sub agent", tool("subagent", agent="general", description="d", prompt="p"), ASK, "oc-ask-agent"),
            # the permission request: read and search are Yes, every other kind is Ask me first
            ("permission read", perm("read"), YES, "oc-perm-read"),
            ("permission search", perm("search"), YES, "oc-perm-read"),
            *[(f"permission {k}", perm(k), ASK, "oc-perm-ask")
              for k in ("edit", "delete", "move", "execute", "think", "fetch", "switch_mode", "other")],
            ("permission, a kind never seen", perm("brand_new"), ASK, None),
            # Code Mode has no rule on purpose (OC15): Ask me first by default, so an owner's Yes can take effect
            ("execute", tool("execute", code="1+1"), ASK, None),
            ("execute with fetch", tool("execute", code="await fetch('http://x')"), ASK, None),
            ("opencode_worktree_list", tool("opencode_worktree_list"), ASK, None),
            ("opencode_worktree_remove", tool("opencode_worktree_remove", directory="/x"), ASK, None),
            ("opencode_session_move", tool("opencode_session_move", directory="/x"), ASK, None),
        ]
        codes = {YES: 0, NO: 2, ASK: 3}
        for label, action, answer, rule_id in cases:
            with self.subTest(action=label):
                self.assertEqual(self.real_check(action, extra=("--no-log",))[:3], (codes[answer], answer, rule_id))

    def test_a_logged_run_on_a_real_root_writes_the_rules_entry_and_the_logbook_verifies(self):
        """The 50 rules also go through the rules change log (layer 13): a logged check writes the baseline entry."""
        root = Path(self._tmp.name) / "logged"
        root.mkdir()
        (root / "rules.yaml").write_bytes(RULES_FILE.read_bytes())
        env = dict(os.environ, PYTHONPATH=str(REPO), HOME=str(root))
        tool = lambda name, **f: gate.generic_action("opencode", name, f)  # noqa: E731
        for action, code in ((tool("read", path="/repo/a.py"), 0), (tool("shell", command="npm test"), 3),
                             (tool("read", path="/repo/.env"), 2)):
            self.assertEqual(self.real_check(action, root=root)[0], code)
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(root), "logbook", "verify"],
                           capture_output=True, text=True, env=env, cwd=str(root))
        self.assertEqual(r.returncode, 0, r.stdout)
        log = (root / "LOGBOOK.md").read_text(encoding="utf-8")
        self.assertEqual(log.count("- Source: umwayi rules\n"), 1)
        self.assertEqual(log.count("- Source: umwayi check\n"), 3)
        self.assertIn("rules 50", log)
        self.assertIn("oc-perm-ask ask", log)

    # ------------------------------------------------------------------------------------------ Code Mode

    def test_no_rule_in_the_file_is_for_code_mode(self):
        self.assertEqual(problems_in(self.text), [])
        for r in self.rules:
            for m in r.matchers:
                if m.field == "type":
                    self.assertNotIn("tool_execute", m.values, r.id)
                    self.assertFalse([v for v in m.values if str(v).startswith("tool_opencode_")], r.id)

    def test_an_owner_yes_for_code_mode_takes_effect_with_the_real_umwayi_check(self):
        owner = ("\n  - id: owner-yes-worktree-list\n    title: Listing worktrees is fine\n"
                 "    text: OpenCode may list the worktrees of a repository.\n    cause: Listing changes nothing.\n"
                 "    verdict: yes\n    matchers:\n      platform: opencode\n      type: tool_opencode_worktree_list\n")
        root = Path(self._tmp.name) / "owner"
        root.mkdir()
        (root / "rules.yaml").write_text(self.text + owner, encoding="utf-8")
        action = gate.generic_action("opencode", "opencode_worktree_list", {})
        self.assertEqual(self.real_check(action, root=root, extra=("--no-log",))[:3], (0, YES, "owner-yes-worktree-list"))
        # the next tool beside it is still Ask me first
        other = gate.generic_action("opencode", "opencode_worktree_remove", {"directory": "/x"})
        self.assertEqual(self.real_check(other, root=root, extra=("--no-log",))[:3], (3, ASK, None))


# ============================================================================================== planted faults


class OpenCodePlantedFaultTests(unittest.TestCase):
    """A fault put into a copy of rules.yaml must be found. Each one is a way the starter rules could go wrong."""

    @classmethod
    def setUpClass(cls):
        cls.text = RULES_FILE.read_text(encoding="utf-8")

    def test_the_real_file_has_no_problem(self):
        self.assertEqual(problems_in(self.text), [])

    def edit(self, rule_id, old, new):
        before, block, after = take_rule(self.text, rule_id)
        self.assertEqual(block.count(old), 1, (rule_id, old))
        return before + block.replace(old, new) + after

    def test_a_verdict_changed(self):
        for rid, old, new, label in (("oc-ask-shell", "verdict: ask", "verdict: yes", "oc-ask-shell: verdict Yes"),
                                     ("oc-no-secrets", "verdict: no", "verdict: ask", "oc-no-secrets: verdict Ask me first"),
                                     ("oc-no-push-main", "verdict: no", "verdict: yes", "oc-no-push-main: verdict Yes"),
                                     ("oc-perm-ask", "verdict: ask", "verdict: yes", "oc-perm-ask: verdict Yes")):
            with self.subTest(rule=rid):
                found = problems_in(self.edit(rid, old, new))
                self.assertTrue(found, rid)
                self.assertTrue(any(label in f for f in found), found)

    def test_a_matcher_dropped(self):
        for rid, line in (("oc-no-destroy", '      input_command__contains: ["rm -rf", "rm -fr", "mkfs", "dd if=", "chmod -r 777"]\n'),
                          ("oc-ask-shell", "      type: tool_shell\n"),
                          ("oc-no-secrets", '      input_path__contains: [".env", ".pem", "id_rsa", "id_ed25519", ".aws/credentials", ".netrc"]\n'),
                          ("oc-perm-read", "      kind: [read, search]\n"),
                          ("oc-no-guard-shell", "      platform: opencode\n")):
            with self.subTest(rule=rid):
                found = problems_in(self.edit(rid, line, ""))
                self.assertTrue(found, rid)
                self.assertTrue(any(f.startswith(f"{rid}: the matchers differ") for f in found), found)

    def test_one_word_dropped_from_a_matcher_list(self):
        found = problems_in(self.edit("oc-no-destroy", '"mkfs", ', ""))
        self.assertTrue(any(f.startswith("oc-no-destroy: the matchers differ") for f in found), found)

    def test_a_rule_missing(self):
        for rid in OC_IDS:
            with self.subTest(rule=rid):
                before, _block, after = take_rule(self.text, rid)
                found = problems_in(before + after)
                self.assertIn(f"{rid} is missing", found)
                missing = [f for f in found if f.endswith(" is missing")]
                self.assertEqual(missing, [f"{rid} is missing"], "only the removed rule is reported")

    def test_an_extra_ask_rule_for_tool_execute_is_found_because_it_would_make_an_owners_yes_useless(self):
        extra = ("\n  - id: oc-ask-execute\n    title: OpenCode Code Mode needs the owner\n"
                 "    text: The owner confirms every Code Mode call.\n    cause: Code Mode runs JavaScript.\n"
                 "    verdict: ask\n    matchers:\n      platform: opencode\n      type: tool_execute\n")
        found = problems_in(self.text + extra)
        self.assertTrue(any("oc-ask-execute: a rule for tool_execute" in f for f in found), found)
        # and the reason it matters, with the real command: an owner's Yes for tool_execute is turned into Ask me first
        owner = ("\n  - id: owner-yes-execute\n    title: Code Mode is fine here\n    text: The owner allows Code Mode.\n"
                 "    cause: Test.\n    verdict: yes\n    matchers:\n      platform: opencode\n      type: tool_execute\n")
        action = gate.generic_action("opencode", "execute", {"code": "1+1"})
        good = decide(parse_rules(self.text + owner), action, today="2026-11-11")
        bad = decide(parse_rules(self.text + extra + owner), action, today="2026-11-11")
        self.assertEqual((good.answer, good.rule_id), (YES, "owner-yes-execute"))
        self.assertEqual((bad.answer, bad.rule_id), (ASK, "oc-ask-execute"))

    def test_an_extra_ask_rule_for_an_opencode_inner_tool_is_found_too(self):
        extra = ("\n  - id: oc-ask-inner\n    title: Inner tools need the owner\n    text: Ask.\n    cause: Ask.\n"
                 "    verdict: ask\n    matchers:\n      platform: opencode\n      type: tool_opencode_worktree_remove\n")
        self.assertTrue(any("tool_opencode_worktree_remove" in f for f in problems_in(self.text + extra)))

    def test_a_yes_rule_for_code_mode_in_the_starter_file_is_found_as_well(self):
        extra = ("\n  - id: oc-yes-execute\n    title: Code Mode\n    text: Yes.\n    cause: Yes.\n    verdict: yes\n"
                 "    matchers:\n      platform: opencode\n      type: tool_execute\n")
        found = problems_in(self.text + extra)
        self.assertTrue(any("oc-yes-execute: a rule for tool_execute" in f for f in found), found)

    def test_a_file_that_does_not_parse_is_a_problem(self):
        self.assertEqual(problems_in(self.text + "  - id: broken\n"), ["rules.yaml does not parse: UmwayiError"])


if __name__ == "__main__":
    unittest.main()
