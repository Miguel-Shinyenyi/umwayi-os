"""M4 f, first part: `credits.yaml` (a rounded number and a date per provider) and its lines in `umwayi budget status` (umwayi/credits.py)."""
import os
import tempfile
import unittest
from pathlib import Path

from umwayi import credits, units
from umwayi.errors import ConfigError

REPO = Path(__file__).resolve().parents[2]
GOOD = "version: 1\ncredits:\n  muse:\n    left_uu: 14000\n    read: 2026-11-25\n"
UNITS = units.check_text("version: 1\nproviders:\n  muse:\n    cost_kind: free_credits\n    limit:\n      credits_uu: 10000\n", "2026-11-25")[0]


class ParseTests(unittest.TestCase):
    def test_a_reading_loads(self):
        self.assertEqual(credits.parse(GOOD), {"muse": credits.Reading(14000, "2026-11-25")})

    def test_nothing_but_the_number_and_the_date_is_accepted(self):
        for bad in (GOOD.replace("    read: 2026-11-25\n", "    read: 2026-11-25\n    card: x\n"),
                    GOOD.replace("    left_uu: 14000\n", ""),
                    GOOD.replace("version: 1\n", "version: 1\nnote: x\n"),
                    GOOD.replace("version: 1", "version: 2")):
            with self.assertRaises(credits.CreditsError):
                credits.parse(bad)

    def test_a_bad_number_date_or_name_is_refused(self):
        for bad in (GOOD.replace("14000", "14000.5"), GOOD.replace("14000", "-1"), GOOD.replace("14000", "true"), GOOD.replace("14000", "abc"),
                    GOOD.replace("2026-11-25", "2026-13-40"), GOOD.replace("2026-11-25", "yesterday"), GOOD.replace("muse:", "Muse:"),
                    "credits: 5\n", "", "[]"):
            with self.assertRaises(credits.CreditsError, msg=bad):
                credits.parse(bad)

    def test_an_error_never_carries_text_of_the_file(self):
        with self.assertRaises(credits.CreditsError) as cm:
            credits.parse(GOOD.replace("14000", "SECRET-TEXT"))
        self.assertNotIn("SECRET-TEXT", str(cm.exception))


class ReadTests(unittest.TestCase):
    def test_no_file_is_no_readings(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(credits.read(d), {})

    def test_a_file_is_read_and_a_link_or_a_folder_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "credits.yaml").write_text(GOOD, encoding="utf-8")
            self.assertIn("muse", credits.read(d))
            (Path(d) / "credits.yaml").unlink()
            (Path(d) / "other").write_text(GOOD, encoding="utf-8")
            os.symlink(Path(d) / "other", Path(d) / "credits.yaml")
            with self.assertRaises(ConfigError):
                credits.read(d)

    def test_a_file_that_is_too_big_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "credits.yaml").write_text(GOOD + "#" * 20000, encoding="utf-8")
            with self.assertRaises(ConfigError):
                credits.read(d)


class StaleTests(unittest.TestCase):
    def test_a_fresh_reading_is_current_and_an_old_or_future_one_is_not(self):
        r = credits.Reading(14000, "2026-11-25")
        self.assertFalse(credits.is_stale(r, "2026-11-25"))
        self.assertFalse(credits.is_stale(r, "2026-11-27"))  # exactly STALE_DAYS old
        self.assertTrue(credits.is_stale(r, "2026-11-28"))
        self.assertTrue(credits.is_stale(r, "2026-11-24"))  # dated in the future: not trusted

    def test_the_lines_say_stale_and_never_show_an_old_figure_as_current(self):
        (line,) = credits.lines(UNITS, {"muse": credits.Reading(14000, "2026-11-01")}, "2026-11-25")
        self.assertIn("STALE, not current", line)
        (fresh,) = credits.lines(UNITS, {"muse": credits.Reading(14000, "2026-11-25")}, "2026-11-25")
        self.assertIn("0 day(s) old", fresh)
        self.assertNotIn("STALE", fresh)

    def test_the_line_says_billing_lags_and_the_spend_since_is_not_counted(self):
        (line,) = credits.lines(UNITS, {"muse": credits.Reading(14000, "2026-11-25")}, "2026-11-25")
        self.assertIn("lag by up to an hour", line)
        self.assertIn("not counted per provider yet", line)

    def test_a_provider_that_units_yaml_does_not_name_is_said_so(self):
        (line,) = credits.lines(UNITS, {"other": credits.Reading(1000, "2026-11-25")}, "2026-11-25")
        self.assertIn("not in units.yaml", line)


class WiringTests(unittest.TestCase):
    def test_the_status_command_shows_the_lines_and_ignores_a_bad_file_with_a_message(self):
        src = (REPO / "umwayi" / "budget.py").read_text(encoding="utf-8")
        self.assertIn("credits.lines(u, credits.read(root), today)", src)
        self.assertIn("The reading is ignored.", src)

    def test_the_committed_file_is_valid_rounded_and_holds_only_a_number_and_a_date(self):
        text = (REPO / "credits.yaml").read_text(encoding="utf-8")
        got = credits.parse(text)
        self.assertEqual(set(got), {"muse"})
        self.assertEqual(got["muse"].left_uu % 1000, 0)  # rounded, never the exact figure of the page
        self.assertEqual(len(text.strip().splitlines()), 5)

    def test_nothing_gates_on_the_reading_yet(self):
        for p in (REPO / "umwayi").glob("*.py"):
            if p.name in ("credits.py", "budget.py"):
                continue
            self.assertNotIn("umwayi import credits", p.read_text(encoding="utf-8").replace("from umwayi import credits,", "XX"), p.name)


if __name__ == "__main__":
    unittest.main()
