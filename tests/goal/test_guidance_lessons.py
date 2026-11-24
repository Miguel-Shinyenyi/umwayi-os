"""N8, L1 (first pull request): `review_by` and `test` in guidance.yaml, and the numbered lessons page.

The loader takes two optional keys. `review_by` is a real date; a passed date marks the entry as due in `guidance list`. `test` names a test
file of the repo and optionally a name in it; an enforce entry has exactly one of `check` and `test`; a test that cannot be found is Ask
me first, so a lesson is never shown as enforced when nothing would fail. Planted faults cover each rule on a scratch repo.
"""
import tempfile
import unittest
from datetime import date
from pathlib import Path

from umwayi import guidance as g

REPO = Path(__file__).resolve().parents[2]


class LessonRepo(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.scratch = Path(d.name)
        (self.scratch / "docs").mkdir()
        (self.scratch / "tests").mkdir()
        (self.scratch / "docs" / "rules.md").write_text("# Rules\n\n## Part\n\n1. The first rule of the page.\n2. The second rule of the page.\n", encoding="utf-8")
        (self.scratch / "tests" / "test_x.py").write_text("class T:\n    def test_a_lesson_is_kept(self):\n        pass\n", encoding="utf-8")
        self.src = "docs/rules.md#Part#1"
        self.hash = g.compute_hash(self.scratch, self.src)

    def entry(self, kind="enforce", **extra):
        body = {"id": "lesson-one", "source_repo": "umwayi-os", "source": self.src, "text": "A lesson that is written as one line.",
                "kind": kind, "applies_to": "pr", "tier": 4, "source_hash": self.hash}
        if kind == "advise":
            body["prompt_line"] = "A prompt line of ten or more characters."
        body.update(extra)
        return body

    def parse(self, **kw):
        lines = ["version: 1", "guidance:"]
        e = self.entry(**kw.pop("entry", {})) if "entry" in kw else self.entry(**kw)
        first = True
        for k, v in e.items():
            lines.append(("  - " if first else "    ") + f"{k}: " + (str(v) if isinstance(v, int) else '"' + str(v) + '"'))
            first = False
        return g.parse("\n".join(lines) + "\n", self.scratch, {})


class TestKeyTests(LessonRepo):
    def test_an_enforce_entry_with_a_test_loads_and_runs_against_no_task_record(self):
        for t in ("tests/test_x.py", "tests/test_x.py test_a_lesson_is_kept", "tests/test_x.py T.test_a_lesson_is_kept"):
            with self.subTest(test=t):
                (e,) = self.parse(test=t)
                self.assertEqual((e.test, e.check), (t, None))
                self.assertEqual(g.check_task([e], object()), [])  # a test entry is checked by its test, not a task record

    def test_planted_fault_a_test_that_is_missing_or_not_in_its_file_is_ask_me_first(self):
        for t in ("tests/test_gone.py", "tests/test_x.py test_not_here"):
            with self.subTest(test=t):
                with self.assertRaises(g.AskFirst):
                    self.parse(test=t)

    def test_a_test_in_the_wrong_form_is_a_config_error_before_any_file_is_read(self):
        for t in ("test_x.py", "tests/../x.py", "/tests/test_x.py", "tests/test_x.txt", "tests/test_x.py a b", "tests/test_x.py 1bad", ""):
            with self.subTest(test=t):
                with self.assertRaises(g.GuidanceError):
                    self.parse(test=t)

    def test_an_enforce_entry_has_exactly_one_of_check_and_test(self):
        with self.assertRaises(g.GuidanceError):
            self.parse()  # neither
        with self.assertRaises(g.GuidanceError):
            g.parse(f"version: 1\nguidance:\n  - id: lesson-one\n    source_repo: umwayi-os\n    source: \"{self.src}\"\n    text: \"A lesson that is written as one line.\"\n"
                    f"    kind: enforce\n    applies_to: pr\n    tier: 4\n    source_hash: \"{self.hash}\"\n    check: one_open_pr\n    test: \"tests/test_x.py\"\n",
                    self.scratch)

    def test_an_advise_entry_may_not_carry_a_test(self):
        with self.assertRaises(g.GuidanceError):
            self.parse(kind="advise", test="tests/test_x.py")


class ReviewByTests(LessonRepo):
    def test_a_real_date_loads_and_the_listing_marks_a_passed_one_as_due(self):
        (e,) = self.parse(kind="advise", review_by="2026-12-31")
        self.assertEqual(e.review_by, "2026-12-31")
        (self.scratch / "guidance.yaml").write_text(
            "version: 1\nguidance:\n  - id: lesson-one\n    source_repo: umwayi-os\n    source: \"docs/rules.md#Part#1\"\n"
            "    text: \"A lesson that is written as one line.\"\n    kind: advise\n    prompt_line: \"A prompt line of ten or more characters.\"\n"
            f"    applies_to: pr\n    tier: 4\n    source_hash: \"{self.hash}\"\n    review_by: \"2026-12-31\"\n", encoding="utf-8")
        self.assertIn("review by 2026-12-31", g.listing(self.scratch, today=date(2026, 11, 24)).lines[0])
        self.assertNotIn("DUE", g.listing(self.scratch, today=date(2026, 12, 31)).lines[0])
        self.assertTrue(g.listing(self.scratch, today=date(2027, 1, 1)).lines[0].endswith("DUE"))

    def test_a_date_that_is_not_real_or_not_in_the_form_is_a_config_error(self):
        for d in ("2026-13-01", "2026-02-30", "26-11-24", "yesterday", "2026-1-1", ""):
            with self.subTest(d=d):
                with self.assertRaises(g.GuidanceError):
                    self.parse(kind="advise", review_by=d)

    def test_an_entry_without_review_by_lists_as_before(self):
        self.assertTrue(all(e.review_by is None and e.test is None for e in g.load(REPO)))  # no entry uses the new keys yet


class LessonsPageTests(unittest.TestCase):
    """The page is the source of the entries of the next pull request: every rule is one line a hash can cover."""
    PAGE = REPO / "docs" / "supervisor-lessons.md"

    def test_every_lesson_is_a_numbered_line_in_its_section_with_its_id_and_the_counts_are_right(self):
        text = self.PAGE.read_text(encoding="utf-8")
        for section, prefix, count in (("Lessons A", "A", 14), ("Lessons B", "B", 4), ("Lessons C", "C", 20), ("Lessons D", "D", 6)):
            for n in range(1, count + 1):
                line = g._rule_line(REPO, f"docs/supervisor-lessons.md#{section}#{n}")
                self.assertTrue(line.startswith(f"{n}. [{prefix}{n}, "), line[:30])
        self.assertNotIn("\u2014", text)

    def test_a_lesson_that_is_changed_changes_its_hash(self):
        a = g.compute_hash(REPO, "docs/supervisor-lessons.md#Lessons A#1")
        self.assertRegex(a, r"^[0-9a-f]{64}$")
        self.assertNotEqual(a, g.compute_hash(REPO, "docs/supervisor-lessons.md#Lessons A#2"))


if __name__ == "__main__":
    unittest.main()
