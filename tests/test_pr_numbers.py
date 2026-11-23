"""F2a: no status part dated on or after the cutoff may say `pr: none`, and `tools/pr_number.py` writes the number.

The real tree is checked as main holds it. The planted faults run the same function on a made-up tree: a part with `pr: none` after the
cutoff is found, an old one is not, and the helper rewrites only the `pr:` line of the parts it is given.
"""
import tempfile
import unittest
from pathlib import Path

from tools import pr_number

REPO = Path(__file__).resolve().parent.parent


def part(date="2026-11-23", pr="none"):
    return f"date: {date}\npr: {pr}\nwhat: something happened\ntests: none\n"


class RealTreeTests(unittest.TestCase):
    def test_no_part_since_the_cutoff_says_pr_none(self):
        self.assertEqual(pr_number.unnumbered(REPO), [], "run: python -m tools.pr_number --pr N after the pull request is opened")


class HelperTests(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.root = Path(self._t.name)
        (self.root / "docs-parts" / "status-log").mkdir(parents=True)

    def write(self, name, text):
        (self.root / "docs-parts" / "status-log" / name).write_text(text, encoding="utf-8")

    def test_a_new_part_with_none_is_found_and_an_old_one_or_a_numbered_one_is_not(self):
        self.write("new.md", part())
        self.write("old.md", part(date="2026-11-10"))
        self.write("done.md", part(pr="177"))
        self.assertEqual(pr_number.unnumbered(self.root), ["docs-parts/status-log/new.md"])

    def test_set_number_rewrites_only_the_pr_line_of_the_given_parts(self):
        self.write("a.md", part())
        self.write("b.md", part())
        before = (self.root / "docs-parts" / "status-log" / "a.md").read_text(encoding="utf-8")
        changed = pr_number.set_number(self.root, ["docs-parts/status-log/a.md"], 196)
        self.assertEqual(changed, ["docs-parts/status-log/a.md"])
        after = (self.root / "docs-parts" / "status-log" / "a.md").read_text(encoding="utf-8")
        self.assertEqual(after, before.replace("pr: none", "pr: 196"))
        self.assertIn("pr: none", (self.root / "docs-parts" / "status-log" / "b.md").read_text(encoding="utf-8"))

    def test_a_part_that_already_has_a_number_is_not_changed(self):
        self.write("a.md", part(pr="150"))
        self.assertEqual(pr_number.set_number(self.root, ["docs-parts/status-log/a.md"], 196), [])
        self.assertIn("pr: 150", (self.root / "docs-parts" / "status-log" / "a.md").read_text(encoding="utf-8"))

    def test_a_number_that_is_not_a_positive_whole_number_is_refused(self):
        self.write("a.md", part())
        for bad in (0, -1, "196", 1.5, True, None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                pr_number.set_number(self.root, ["docs-parts/status-log/a.md"], bad)

    def test_the_command_line_refuses_other_words_and_a_missing_pull_request(self):
        self.assertEqual(pr_number.main(["--frobnicate"], self.root), 64)
        self.assertEqual(pr_number.main(["--pr", "abc"], self.root), 64)


if __name__ == "__main__":
    unittest.main()
