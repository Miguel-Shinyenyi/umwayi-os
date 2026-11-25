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

    def test_the_repository_file_is_not_marked_by_this_change(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[2] / "units.yaml").read_text(encoding="utf-8")
        self.assertNotIn("public:", text)  # the owner writes the mark by hand; nobody else does


if __name__ == "__main__":
    unittest.main()
