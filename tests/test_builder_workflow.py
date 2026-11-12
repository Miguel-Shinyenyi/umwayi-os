"""W20 Part E: the builder rules live in the repo, short, and name the command that exists."""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PATH = REPO / ".kiro" / "steering" / "builder-workflow.md"


class BuilderWorkflowTests(unittest.TestCase):
    def test_the_file_exists_and_is_short(self):
        self.assertTrue(PATH.is_file())
        self.assertLess(len(PATH.read_text(encoding="utf-8").splitlines()), 60)

    def test_it_is_always_included(self):
        self.assertFalse(PATH.read_text(encoding="utf-8").startswith("---"), "front matter would change when it is included")

    def test_no_em_dash(self):
        self.assertNotIn("\u2014", PATH.read_text(encoding="utf-8"))

    def test_it_names_the_command_once_and_the_command_exists(self):
        text = PATH.read_text(encoding="utf-8")
        self.assertEqual(text.count("tools/affected_tests.py"), 1)
        self.assertTrue((REPO / "tools" / "affected_tests.py").is_file())

    def test_the_ten_rules_are_numbered_in_order(self):
        nums = re.findall(r"^(\d+)\. ", PATH.read_text(encoding="utf-8"), re.M)
        self.assertEqual(nums, [str(i) for i in range(1, 11)])

    def test_the_key_rules_are_there(self):
        text = PATH.read_text(encoding="utf-8")
        for needle in ("Never merge", "Never review your own work", "origin/main", "next free number", "tests first",
                       "FULL SUITE", "GitHub CI is the record", "recommendation", "Could not verify", "steering rules 1 to 13",
                       "30 minutes"):
            self.assertIn(needle, text)

    def test_the_product_steering_is_untouched_in_name(self):
        self.assertTrue((REPO / ".kiro" / "steering" / "product.md").is_file())
        self.assertNotIn("builder-workflow", (REPO / ".kiro" / "steering" / "product.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
