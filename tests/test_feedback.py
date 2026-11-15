"""W26, W33: the tester feedback path. The issue template asks every question, a blank issue is still allowed, docs/feedback.md is
linked from README.md and gives the steps of `umwayi feedback export` (W33; before it, the section said Not yet available), and nothing here claims a command that does not exist.
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / ".github" / "ISSUE_TEMPLATE" / "tester-feedback.md"
CONFIG = REPO / ".github" / "ISSUE_TEMPLATE" / "config.yml"
DOC = REPO / "docs" / "feedback.md"
README = REPO / "README.md"

QUESTIONS = ("What you tried", "What you expected", "What happened", "Your umwayi version", "Your Python version", "The exit code")


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.text = TEMPLATE.read_text(encoding="utf-8")

    def test_it_has_the_front_matter_github_needs(self):
        m = re.match(r"---\n(.*?)\n---\n", self.text, re.S)
        self.assertTrue(m, "no front matter")
        keys = re.findall(r"^(\w+):", m.group(1), re.M)
        self.assertTrue({"name", "about"} <= set(keys), keys)

    def test_every_required_question_is_a_heading_in_order(self):
        headings = re.findall(r"^## (.+)$", self.text, re.M)
        self.assertEqual(headings[:len(QUESTIONS)], list(QUESTIONS))

    def test_the_version_and_exit_code_questions_say_how_to_find_the_answer(self):
        self.assertIn("umwayi --version", self.text)
        self.assertIn("python --version", self.text)
        self.assertIn("echo $?", self.text)

    def test_the_secrets_checkbox_is_there_and_unchecked(self):
        boxes = re.findall(r"^- \[( |x|X)\] (.+)$", self.text, re.M)
        self.assertEqual(len(boxes), 1)
        self.assertEqual(boxes[0][0], " ")
        self.assertIn("removed secrets", boxes[0][1])

    def test_it_warns_before_the_first_question(self):
        first_heading = self.text.index("## ")
        self.assertRegex(self.text[:first_heading].lower(), r"do not paste secrets")

    def test_it_has_no_em_dash(self):
        self.assertNotIn("\u2014", self.text)

    def test_blank_issues_stay_allowed(self):
        self.assertEqual(CONFIG.read_text(encoding="utf-8").strip(), "blank_issues_enabled: true")


class DocTests(unittest.TestCase):
    def setUp(self):
        self.doc = DOC.read_text(encoding="utf-8")

    def test_readme_links_the_doc(self):
        self.assertIn("(docs/feedback.md)", README.read_text(encoding="utf-8"))

    def test_the_doc_links_the_template_and_the_exit_codes(self):
        self.assertIn("(../.github/ISSUE_TEMPLATE/tester-feedback.md)", self.doc)
        self.assertIn("(exit-codes.md)", self.doc)
        self.assertTrue((REPO / "docs" / "exit-codes.md").is_file())

    def test_the_doc_lists_the_steps_in_the_template_order(self):
        steps = self.doc.split("### How to send feedback")[1].split("### Export")[0]
        step = [steps.index(w) for w in ("what you tried", "what you expected", "what happened", "umwayi --version",
                                            "python --version", "echo $?")]
        self.assertEqual(step, sorted(step))

    def test_the_export_section_gives_the_real_command_and_steps_and_names_every_field(self):
        # W33 changed this test (it was test_the_export_is_marked_not_yet_available...): the export now exists, so the section
        # must give the command and the steps instead of the Not yet available line, and it must still name every field.
        section = self.doc.split("### Export of a logbook summary")[1].split("## Decisions log")[0]
        self.assertNotIn("Not yet available", section)
        self.assertTrue(section.lstrip().startswith("`umwayi feedback export` prints a summary"))
        for field in ("number of entries", "each kind", "each verdict", "first and last date", "hash chain", "budget spent in UU"):
            self.assertIn(field, section)
        for promise in ("never prints a path", "writes no file", "adds no entry to the logbook", "exits 2"):
            self.assertIn(promise, section)

    def test_the_doc_does_not_claim_a_command_that_does_not_exist(self):
        commands = set(re.findall(r"`umwayi ([a-z]+(?: [a-z]+)?)", self.doc))
        self.assertEqual(commands, {"feedback export", "logbook verify", "view snapshot"})
        text = (REPO / "umwayi" / "cli.py").read_text(encoding="utf-8")
        for name in ("verify", "snapshot", "export"):
            self.assertIn(f'"{name}"', text)
        self.assertNotRegex(self.doc, r"umwayi (logbook|view|report) (export|summary)")

    def test_the_doc_has_no_em_dash_and_the_four_parts(self):
        self.assertNotIn("\u2014", self.doc)
        self.assertEqual(re.findall(r"^## (.+)$", self.doc, re.M), ["Purpose", "Current state", "Decisions log", "Open questions"])


if __name__ == "__main__":
    unittest.main()
