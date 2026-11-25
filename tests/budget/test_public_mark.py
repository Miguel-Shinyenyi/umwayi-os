"""G-0076 / G-0046: the owner's `public: true` mark in units.yaml. Only the exact boolean true is a mark; nothing infers it and no code writes it."""
import unittest

from umwayi import units

TODAY = "2026-11-25"
BASE = "version: 1\n"


def check(text):
    return units.check_text(text, TODAY)


class PublicMarkTests(unittest.TestCase):
    def test_no_mark_is_a_private_root(self):
        u, p = check(BASE)
        self.assertEqual((p, u.public), ([], False))

    def test_public_true_is_the_mark_and_shows_in_the_state(self):
        u, p = check(BASE + "public: true\n")
        self.assertEqual((p, u.public), ([], True))
        self.assertEqual(u.state()["public"], "true")

    def test_anything_but_the_boolean_true_is_refused_with_its_line(self):
        for bad in ("false", '"true"', "1", "yes", "'public'", "[]"):
            u, p = check(BASE + f"public: {bad}\n")
            self.assertIsNone(u, bad)
            self.assertEqual(len(p), 1, bad)
            self.assertIn("public must be true", p[0].message, bad)
            self.assertEqual(p[0].line, 2, bad)

    def test_a_private_root_has_no_public_line_in_its_state(self):
        u, _ = check(BASE)
        self.assertNotIn("public", u.state())

    def test_the_repository_file_carries_the_owners_mark_and_says_who_wrote_it_when_and_for_what(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[2] / "units.yaml").read_text(encoding="utf-8")
        u, p = units.check_text(text, "2026-11-25")
        self.assertEqual([x.message for x in p], [])
        self.assertTrue(u.public)
        self.assertEqual([l for l in text.split("\n") if l.startswith("public:")], ["public: true"])  # one mark, the exact word
        head = text[:text.index("public: true")]
        for words in ("The owner wrote the word public", "22:12 on 2026-11-25", "public umwayi-os repo only"):
            self.assertIn(words, head)  # the comment above the mark says who wrote it, when, and for what

if __name__ == "__main__":
    unittest.main()
