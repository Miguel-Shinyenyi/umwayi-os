"""W58a: `umwayi rules validate [--rules PATH]`, read only.

Each failure kind of the rules reader gives exit 64 and one line with the line number and the rule id of the first problem, and
the reader's own words. A good file gives 0. Nothing is written (no logbook, no queue). The rule language, the matchers, the
starter rules and the gate are unchanged: the repo rules.yaml still loads to the same rules, and every check of `umwayi check`
answers as before. Real child processes for the command line, the function for the table of failures.
"""

import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from umwayi import rules, rulesvalidate

REPO = Path(__file__).resolve().parents[1]
RULE = "  - id: {id}\n    title: t\n    text: x.\n    verdict: {verdict}\n    matchers:\n      type: read\n"
GOOD = "rules:\n" + RULE.format(id="first", verdict="yes")

# (name, text, the line, the rule id or None, words of the reader that must be in the line)
CASES = [
    ("a tab", "rules:\n\t- id: a\n", 2, None, "tabs are not allowed"),
    ("an unterminated quote", GOOD + '  - id: "b\n', 8, None, "unterminated quoted string"),
    ("top level is not rules", "things:\n  - 1\n", 1, None, "top level must be a single 'rules' list"),
    ("rules is not a list", "rules: 5\n", 1, None, "'rules' must be a list"),
    ("a rule that is not a mapping", GOOD + "  - just text\n", 8, None, "rule #2 must be a mapping"),
    ("a bad id", GOOD + RULE.format(id="Bad Id", verdict="yes"), 8, None, "rule #2 has a missing or bad id"),
    ("a missing id", GOOD + "  - title: t\n    text: x.\n    verdict: yes\n", 8, None, "rule #2 has a missing or bad id"),
    ("a duplicate id", GOOD + RULE.format(id="first", verdict="no"), 8, "first", "duplicate rule id 'first'"),
    ("an unknown field", GOOD + RULE.format(id="second", verdict="yes") + "    colour: red\n", 8, "second",
     "unknown field(s)"),
    ("a bad verdict", GOOD + RULE.format(id="second", verdict="maybe"), 8, "second", "verdict must be yes, no or ask"),
    ("a cause that is not text", GOOD + RULE.format(id="second", verdict="no") + "    cause: [1]\n", 8, "second",
     "cause must be text"),
    ("matchers that are not a mapping", GOOD + "  - id: second\n    title: t\n    text: x.\n    verdict: no\n"
     "    matchers: [1]\n", 8, "second", "matchers must be a mapping"),
    ("a matcher with no field name", GOOD + "  - id: second\n    title: t\n    text: x.\n    verdict: no\n    matchers:\n"
     "      __contains: rm\n", 8, "second", "bad matcher name"),
    ("a matcher value that is not plain", GOOD + "  - id: second\n    title: t\n    text: x.\n    verdict: no\n    matchers:\n"
     "      command:\n        - [a]\n", 8, "second", "matcher values must be plain values"),
    ("__exists that is not true or false", GOOD + "  - id: second\n    title: t\n    text: x.\n    verdict: no\n"
     "    matchers:\n      amount__exists: maybe\n", 8, "second", "__exists needs true or false"),
    ("an empty __contains", GOOD + "  - id: second\n    title: t\n    text: x.\n    verdict: no\n    matchers:\n"
     "      command__contains: \"\"\n", 8, "second", "__contains needs non-empty text"),
    ("a missing title", GOOD + "  - id: second\n    text: x.\n    verdict: no\n", 8, "second", "'title' is required"),
    ("a missing text", GOOD + "  - id: second\n    title: t\n    verdict: no\n", 8, "second", "'text' is required"),
    ("review_by on a No rule", GOOD + RULE.format(id="second", verdict="no") + "    review_by: 2030-01-01\n", 8, "second",
     "review_by is allowed on a Yes rule"),
    ("a review_by that is not a date", GOOD + RULE.format(id="second", verdict="yes") + "    review_by: 2030-02-30\n", 8,
     "second", "review_by must be a real date"),
    ("autonomy on a Yes rule", GOOD + RULE.format(id="second", verdict="yes") + "    autonomy:\n      class: c\n"
     "      reversible: true\n      cost_uu: 1\n", 8, "second", "autonomy is allowed on an ask rule only"),
    ("autonomy with a missing key", GOOD + RULE.format(id="second", verdict="ask") + "    autonomy:\n      class: c\n", 8,
     "second", "autonomy must have exactly class, reversible and cost_uu"),
    ("two classes declared two ways", GOOD + RULE.format(id="second", verdict="ask") + "    autonomy:\n      class: c\n"
     "      reversible: true\n      cost_uu: 1\n" + RULE.format(id="third", verdict="ask") + "    autonomy:\n      class: c\n"
     "      reversible: false\n      cost_uu: 1\n", 18, "third", "another rule gives class c a different reversible"),
]


class Folder(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def write(self, text, name="rules.yaml"):
        p = self.root / name
        p.write_text(text, encoding="utf-8")
        return p

    def cli(self, *args):
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "rules", "validate", *args],
                           capture_output=True, text=True, cwd=str(REPO), timeout=60)
        self.assertNotIn(r.returncode, (1, 3), r.stdout + r.stderr)
        return r


class FailureTests(Folder):
    def test_every_failure_kind_gives_64_the_line_and_the_rule_id(self):
        for name, text, line, rid, words in CASES:
            with self.subTest(name):
                r = rulesvalidate.validate(self.write(text))
                self.assertEqual(r.code, 64, r.lines)
                first = r.lines[0]
                self.assertTrue(first.startswith(f"no: {self.root / 'rules.yaml'}: line {line}: "), first)
                if rid:
                    self.assertIn(f": rule {rid}: ", first)
                self.assertIn(words, first)
                with self.assertRaises(Exception):  # the gate reader refuses the same file (nothing was loosened)
                    rules.load_rules(self.root / "rules.yaml")

    def test_a_file_that_cannot_be_read_is_64_with_no_line(self):
        r = rulesvalidate.validate(self.root / "rules.yaml")
        self.assertEqual(r.code, 64)
        self.assertIn("line unknown: no rule: rules.yaml: cannot read the file", r.lines[0])
        (self.root / "rules.yaml").mkdir()
        self.assertIn("not a regular file", rulesvalidate.validate(self.root / "rules.yaml").lines[0])
        (self.root / "rules.yaml").rmdir()
        (self.root / "rules.yaml").write_bytes(b"rules:\n  - id: \xff\n")
        self.assertIn("not valid UTF-8", rulesvalidate.validate(self.root / "rules.yaml").lines[0])
        (self.root / "rules.yaml").write_bytes(b"#" * (rules.MAX_RULES_BYTES + 1))
        self.assertIn("larger than", rulesvalidate.validate(self.root / "rules.yaml").lines[0])

    def test_the_command_line_gives_64_and_writes_nothing(self):
        self.write(GOOD + RULE.format(id="second", verdict="maybe"))
        r = self.cli()
        self.assertEqual(r.returncode, 64, r.stdout + r.stderr)
        self.assertIn("line 8: rule second: rule 'second': verdict must be yes, no or ask", r.stdout)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["rules.yaml"], "something was written")

    def test_usage_errors_are_64(self):
        self.write(GOOD)
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "rules", "validate", "extra"],
                           capture_output=True, text=True, cwd=str(REPO), timeout=60)
        self.assertEqual(r.returncode, 64)


class GoodTests(Folder):
    def test_a_good_file_is_0(self):
        self.write(GOOD + RULE.format(id="second", verdict="ask"))
        r = self.cli()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(), f"ok: {self.root / 'rules.yaml'}: it loads and its 2 rule(s) are well formed. "
                                           "Nothing was changed.")
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["rules.yaml"])

    def test_an_empty_list_and_another_path_are_0(self):
        p = self.write("rules: []\n", "other.yaml")
        r = self.cli("--rules", str(p))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("its 0 rule(s)", r.stdout)

    def test_the_repo_rules_file_is_well_formed(self):
        r = rulesvalidate.validate(REPO / "rules.yaml")
        self.assertEqual(r.code, 0, r.lines)


class TodayTests(Folder):
    def test_a_matcher_name_with_an_unknown_operator_loads_today_and_never_matches(self):
        """What the reader does today, unchanged by W58a: `command__startswith` is not an operator, so it is read as an equals
        matcher on a field of that name, which no action has. The rule loads and never matches. A later task (W57) decides
        whether an unknown operator becomes a refusal; validate reports what the gate does."""
        p = self.write(GOOD + "  - id: second\n    title: t\n    text: x.\n    verdict: no\n    matchers:\n"
                       "      command__startswith: git\n")
        self.assertEqual(rulesvalidate.validate(p).code, 0)
        [_, second] = rules.load_rules(p)
        self.assertFalse(rules.rule_matches(second, {"command": "git push"}))


class NothingChangedTests(unittest.TestCase):
    def test_the_repo_rules_still_load_to_the_same_rules(self):
        """The reader was split into one function per rule for the line number; what it accepts and returns is the same."""
        text = (REPO / "rules.yaml").read_text(encoding="utf-8")
        loaded = rules.parse_rules(text)
        self.assertEqual(len(loaded), len(set(r.id for r in loaded)))
        self.assertEqual([r.id for r in loaded], [line.split("id:", 1)[1].strip() for line in text.splitlines()
                                                  if line.strip().startswith("- id:")])
        for r in loaded:
            self.assertIn(r.verdict, (rules.YES, rules.NO, rules.ASK))

    def test_the_error_words_are_the_readers_own_and_unchanged(self):
        with self.assertRaises(Exception) as cm:
            rules.parse_rules(GOOD + RULE.format(id="second", verdict="maybe"))
        self.assertEqual(str(cm.exception), "rule 'second': verdict must be yes, no or ask")
        self.assertEqual(cm.exception.rule_index, 2)

    def test_the_starter_rules_file_is_not_touched_by_this_change(self):
        # the pinned hashes of tests/test_starter_rules.py are the record; this only proves validate reads and never writes
        before = hashlib.sha256((REPO / "rules.yaml").read_bytes()).hexdigest()
        rulesvalidate.validate(REPO / "rules.yaml")
        self.assertEqual(hashlib.sha256((REPO / "rules.yaml").read_bytes()).hexdigest(), before)


if __name__ == "__main__":
    unittest.main()
