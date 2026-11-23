"""The UTC day one behind the local day (02:41 in Nairobi is still the day before in UTC).

A goal command takes the UTC day as its date. `rules.election_clock` then takes the latest of the system date, that day and
the newest logbook date, so a UTC day behind the local day can never bring a lapsed rule back or write an entry older than
the logbook.
"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from umwayi import rules


class UtcBehindLocalTests(unittest.TestCase):
    def test_the_local_day_wins_over_a_utc_day_one_behind(self):
        with mock.patch.object(rules, "system_today", return_value="2026-11-18"):
            self.assertEqual(rules.election_clock(None, "2026-11-17"), "2026-11-18")

    def test_the_newest_logbook_day_wins_over_both(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(rules, "system_today", return_value="2026-11-18"), \
                mock.patch.object(rules, "_newest_logbook_date", return_value="2026-11-19"):
            self.assertEqual(rules.election_clock(Path(d), "2026-11-17"), "2026-11-19")

    def test_a_utc_day_ahead_of_local_is_used(self):
        with mock.patch.object(rules, "system_today", return_value="2026-11-17"):
            self.assertEqual(rules.election_clock(None, "2026-11-18"), "2026-11-18")

    def test_a_goal_command_dates_by_the_local_day_when_utc_is_behind(self):
        from datetime import datetime, timezone
        from umwayi import goal
        now = datetime(2026, 11, 17, 23, 41, tzinfo=timezone.utc).timestamp()  # 02:41 on the 18th in Nairobi
        ctx = goal.Ctx(Path("."), int(now), lambda s: None, lambda s: None)
        with mock.patch.object(rules, "system_today", return_value="2026-11-18"), \
                mock.patch.object(rules, "_newest_logbook_date", return_value=None):
            self.assertEqual(ctx.when, "2026-11-18")

    def test_planted_fault_a_clock_that_took_the_given_day_first_would_go_backwards(self):
        with mock.patch.object(rules, "system_today", return_value="2026-11-18"):
            self.assertNotEqual(rules.election_clock(None, "2026-11-17"), "2026-11-17")


if __name__ == "__main__":
    unittest.main()
