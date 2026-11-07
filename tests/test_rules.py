import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from umwayi.cli import main
from umwayi.errors import UmwayiError
from umwayi.rules import ASK, NO, YES, check, parse_rules

REPO = Path(__file__).resolve().parent.parent

RULES = """
rules:
  - id: no-money
    title: Never move money
    text: Helpers never move money.
    cause: Safety rule.
    verdict: no
    matchers:
      type: [payment, transfer]
  - id: ask-email
    title: Email needs me
    text: Ask before sending email.
    verdict: ask
    matchers:
      type: send
      channel: email
  - id: ok-read
    title: Reads are fine
    text: Reading is fine.
    verdict: yes
    matchers:
      type: read
  - id: ok-read-big
    title: Also yes for notes
    text: Notes are fine.
    verdict: yes
    matchers:
      type: read
      path__contains: notes
  - id: no-secret-path
    title: Secret paths
    text: Never touch secrets.
    verdict: no
    matchers:
      path__contains: secret
  - id: no-amount
    title: Amount present
    text: Amounts mean money.
    verdict: no
    matchers:
      amount__exists: true
  - id: doc-only
    title: No matchers
    text: Documentation only.
    verdict: yes
"""


class RulesBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.path = self.dir / "rules.yaml"
        self.path.write_text(RULES, encoding="utf-8")

    def chk(self, action):
        text = action if isinstance(action, str) else json.dumps(action)
        return check(text, self.path)


class DecisionTests(RulesBase):
    def test_yes_no_ask(self):
        d = self.chk({"type": "transfer"})
        self.assertEqual((d.answer, d.rule_id, d.exit_code), (NO, "no-money", 2))
        self.assertIn("Helpers never move money.", d.reason)
        self.assertIn("Safety rule.", d.reason)
        d = self.chk({"type": "read", "path": "memory/master.md"})
        self.assertEqual((d.answer, d.rule_id, d.exit_code), (YES, "ok-read", 0))
        d = self.chk({"type": "send", "channel": "EMAIL"})
        self.assertEqual((d.answer, d.rule_id, d.exit_code), (ASK, "ask-email", 3))

    def test_no_match_asks(self):
        d = self.chk({"type": "launch_rocket"})
        self.assertEqual((d.answer, d.rule_id, d.exit_code), (ASK, None, 3))

    def test_rule_without_matchers_never_matches(self):
        d = self.chk({})
        self.assertEqual(d.answer, ASK)
        self.assertNotIn("doc-only", d.matched)

    def test_precedence_no_beats_yes(self):
        d = self.chk({"type": "read", "path": "a/secret/file"})
        self.assertEqual((d.answer, d.rule_id), (NO, "no-secret-path"))
        self.assertEqual(d.matched, ["ok-read", "no-secret-path"])

    def test_precedence_ask_beats_yes(self):
        rules = """
rules:
  - id: a-yes
    title: t
    text: t
    verdict: yes
    matchers:
      type: go
  - id: b-ask
    title: t
    text: t
    verdict: ask
    matchers:
      type: go
"""
        self.path.write_text(rules, encoding="utf-8")
        d = self.chk({"type": "go"})
        self.assertEqual((d.answer, d.rule_id), (ASK, "b-ask"))

    def test_first_of_strongest_wins(self):
        d = self.chk({"type": "payment", "amount": 5})
        self.assertEqual(d.rule_id, "no-money")
        self.assertEqual(d.matched, ["no-money", "no-amount"])

    def test_contains_and_exists_and_lists(self):
        self.assertEqual(self.chk({"type": "read", "path": ["x", "My Secret"]}).answer, NO)
        self.assertEqual(self.chk({"amount": 0}).answer, NO)
        self.assertEqual(self.chk({"type": "read"}).answer, YES)

    def test_missing_field_does_not_match(self):
        self.assertEqual(self.chk({"channel": "email"}).answer, ASK)

    def test_non_scalar_field_values_do_not_match(self):
        self.assertEqual(self.chk({"type": {"nested": "payment"}}).answer, ASK)
        self.assertEqual(self.chk({"type": None}).answer, ASK)

    def test_case_and_whitespace_insensitive(self):
        self.assertEqual(self.chk({"type": "  PAYMENT "}).answer, NO)


class FailClosedTests(RulesBase):
    def test_bad_action_json(self):
        for text in ["", "not json", "[]", '"str"', "42", "null", '{"a":1,"a":2}', '{"a": NaN}', "{" * 5000]:
            with self.subTest(text=text[:20]):
                d = check(text, self.path)
                self.assertEqual((d.answer, d.exit_code), (ASK, 3))

    def test_no_action(self):
        self.assertEqual(check(None, self.path).answer, ASK)

    def test_huge_action(self):
        d = check(json.dumps({"type": "read", "pad": "x" * 70000}), self.path)
        self.assertEqual(d.answer, ASK)

    def test_missing_rules_file(self):
        d = check('{"type": "read"}', self.dir / "nope.yaml")
        self.assertEqual((d.answer, d.exit_code), (ASK, 3))

    def test_broken_rules_files(self):
        broken = {
            "yaml": "rules:\n  - id: a\n   title: bad",
            "no verdict": "rules:\n  - id: a\n    title: t\n    text: t\n    matchers:\n      type: read",
            "bad verdict": "rules:\n  - id: a\n    title: t\n    text: t\n    verdict: maybe",
            "dup id": ("rules:\n  - id: a\n    title: t\n    text: t\n    verdict: yes\n"
                       "  - id: a\n    title: t\n    text: t\n    verdict: yes"),
            "unknown field": "rules:\n  - id: a\n    title: t\n    text: t\n    verdict: yes\n    matcher: {}",
            "bad id": "rules:\n  - id: Bad Id\n    title: t\n    text: t\n    verdict: yes",
            "bad top": "other: 1",
            "not a list": "rules: 5",
            "empty contains": "rules:\n  - id: a\n    title: t\n    text: t\n    verdict: yes\n    matchers:\n      p__contains: ''",
            "bad exists": "rules:\n  - id: a\n    title: t\n    text: t\n    verdict: yes\n    matchers:\n      p__exists: maybe",
            "empty matcher list": "rules:\n  - id: a\n    title: t\n    text: t\n    verdict: yes\n    matchers:\n      type: []",
        }
        for name, text in broken.items():
            with self.subTest(name=name):
                self.path.write_text(text, encoding="utf-8")
                d = check('{"type": "read"}', self.path)
                self.assertEqual((d.answer, d.exit_code), (ASK, 3))
                self.assertIsNone(d.rule_id)

    def test_one_bad_rule_voids_whole_file(self):
        # a valid "yes" rule must not be honoured if another rule is broken
        self.path.write_text(
            RULES + "\n  - id: broken\n    title: t\n    text: t\n    verdict: nope\n",
            encoding="utf-8",
        )
        self.assertEqual(self.chk({"type": "read"}).answer, ASK)

    def test_invalid_utf8_rules(self):
        self.path.write_bytes(b"rules:\n  - id: \xff\xfe")
        self.assertEqual(self.chk({"type": "read"}).answer, ASK)

    def test_empty_rules_list_asks(self):
        self.path.write_text("rules: []\n", encoding="utf-8")
        self.assertEqual(self.chk({"type": "read"}).answer, ASK)
        self.path.write_text("rules:\n", encoding="utf-8")
        self.assertEqual(self.chk({"type": "read"}).answer, ASK)

    def test_reason_does_not_echo_rules_content(self):
        self.path.write_text("rules:\n  - id: a\n    title: SECRETVALUE\n    verdict: bad", encoding="utf-8")
        d = self.chk({"type": "read"})
        self.assertNotIn("SECRETVALUE", d.reason)

    def test_yes_and_no_are_not_booleans(self):
        rules = parse_rules(
            "rules:\n  - id: a\n    title: t\n    text: t\n    verdict: no\n    matchers:\n      type: no\n"
        )
        self.assertEqual(rules[0].verdict, NO)

    def test_parse_rules_raises_umwayi_error(self):
        with self.assertRaises(UmwayiError):
            parse_rules("garbage: [")


class CliTests(RulesBase):
    def run_cli(self, *argv, stdin=None):
        buf = io.StringIO()
        old = sys.stdin
        if stdin is not None:
            sys.stdin = io.StringIO(stdin)
        try:
            code = main(["check", "--rules", str(self.path), *argv], out=buf)
        finally:
            sys.stdin = old
        return code, buf.getvalue()

    def test_exit_codes_and_output(self):
        code, out = self.run_cli('{"type": "read"}')
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], "Yes")
        self.assertIn("Rule: ok-read", out)
        code, out = self.run_cli('{"type": "payment"}')
        self.assertEqual(code, 2)
        self.assertEqual(out.splitlines()[0], "No")
        code, out = self.run_cli('{"type": "dance"}')
        self.assertEqual(code, 3)
        self.assertEqual(out.splitlines()[0], "Ask me first")

    def test_stdin(self):
        code, _ = self.run_cli("-", stdin='{"type": "payment"}')
        self.assertEqual(code, 2)

    def test_missing_action_asks(self):
        code, out = self.run_cli()
        self.assertEqual(code, 3)
        self.assertTrue(out.startswith("Ask me first"))

    def test_json_output(self):
        code, out = self.run_cli('{"type": "payment"}', "--json")
        data = json.loads(out)
        self.assertEqual((code, data["answer"], data["rule_id"]), (2, "No", "no-money"))

    def test_default_rules_path_uses_root(self):
        buf = io.StringIO()
        code = main(["--root", str(self.dir), "check", '{"type": "payment"}'], out=buf)
        self.assertEqual(code, 2)

    def test_usage_error_is_not_a_rules_answer(self):
        err = io.StringIO()
        old = sys.stderr
        sys.stderr = err
        try:
            for argv in (["--nonsense"], ["bogus"], [], ["check", "--rules"]):
                with self.subTest(argv=argv):
                    self.assertEqual(main(argv, out=io.StringIO()), 64)
        finally:
            sys.stderr = old

    def test_real_process_exit_codes(self):
        env = dict(os.environ, PYTHONPATH=str(REPO))
        def run(action):
            return subprocess.run(
                [sys.executable, "-m", "umwayi", "check", "--rules", str(self.path), action],
                capture_output=True, text=True, env=env, cwd=self.dir,
            )
        self.assertEqual(run('{"type": "read"}').returncode, 0)
        self.assertEqual(run('{"type": "payment"}').returncode, 2)
        self.assertEqual(run("garbage").returncode, 3)


class StarterRulesTests(unittest.TestCase):
    """The rules.yaml shipped in the repo must load and behave."""

    def setUp(self):
        self.path = REPO / "rules.yaml"

    def test_starter_rules(self):
        cases = [
            ({"type": "transfer"}, NO),
            ({"type": "read_memory"}, YES),
            ({"type": "write_draft"}, YES),
            ({"type": "git_push", "branch": "main"}, NO),
            ({"type": "git_push", "branch": "feature/x"}, ASK),
            ({"type": "publish"}, NO),
            ({"type": "write_draft", "amount": 5}, NO),
            ({"type": "something_new"}, ASK),
        ]
        for action, want in cases:
            with self.subTest(action=action):
                self.assertEqual(check(json.dumps(action), self.path).answer, want)


if __name__ == "__main__":
    unittest.main()
