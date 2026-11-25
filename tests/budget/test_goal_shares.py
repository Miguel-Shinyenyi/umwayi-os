"""M4 g and h, first part: the caps of a goal share, the gate, the sum of shares and the Nairobi windows (umwayi/goalshare.py)."""
import unittest
from datetime import datetime, timezone

from umwayi import goalshare as g

UTC = timezone.utc


def caps60(**kw):
    base = dict(share_pct=60, month_allowance_uu=10000, weekly_allowance_uu=2100, daily_share_uu=None, horizon_days=30)
    base.update(kw)
    return g.caps(**base)


class WindowTests(unittest.TestCase):
    def test_a_time_after_21_utc_is_already_tomorrow_in_nairobi(self):
        self.assertEqual(g.nairobi_day(datetime(2026, 11, 24, 20, 59, tzinfo=UTC)), "2026-11-24")
        self.assertEqual(g.nairobi_day(datetime(2026, 11, 24, 21, 0, tzinfo=UTC)), "2026-11-25")

    def test_a_window_across_utc_midnight_but_not_nairobi_midnight_is_one_day(self):
        a = g.nairobi_day(datetime(2026, 11, 24, 22, 0, tzinfo=UTC))  # 01:00 Nairobi on the 25th
        b = g.nairobi_day(datetime(2026, 11, 25, 2, 0, tzinfo=UTC))  # 05:00 Nairobi on the 25th: past UTC midnight, same Nairobi day
        self.assertEqual(a, b)

    def test_a_naive_time_is_refused(self):
        with self.assertRaises(ValueError):
            g.nairobi_day(datetime(2026, 11, 24, 12, 0))
        with self.assertRaises(ValueError):
            g.days_left_in_week(datetime(2026, 11, 24, 12, 0))

    def test_days_left_in_the_nairobi_week(self):
        self.assertEqual(g.days_left_in_week(datetime(2026, 11, 23, 5, 0, tzinfo=UTC)), 7)  # Monday 08:00 Nairobi
        self.assertEqual(g.days_left_in_week(datetime(2026, 11, 29, 20, 59, tzinfo=UTC)), 1)  # Sunday 23:59 Nairobi: the last minute of the week
        self.assertEqual(g.days_left_in_week(datetime(2026, 11, 29, 21, 0, tzinfo=UTC)), 7)  # Monday 00:00 Nairobi: a new week
        self.assertEqual(g.days_left_in_week(datetime(2026, 11, 29, 12, 0, tzinfo=UTC)), 1)  # Sunday noon


class SharesTests(unittest.TestCase):
    def test_two_goals_at_40_and_40_refuse_the_second_with_a_20_percent_reserve(self):
        self.assertEqual(g.shares_ok([40], 40), (True, None))
        self.assertEqual(g.shares_ok([40], 41), (False, "share_over_allocated"))
        self.assertEqual(g.shares_ok([40, 30], 20), (False, "share_over_allocated"))

    def test_the_reserve_can_be_moved(self):
        self.assertEqual(g.shares_ok([40], 50, reserve_pct=10), (True, None))
        self.assertEqual(g.shares_ok([], 100, reserve_pct=0), (True, None))

    def test_a_bad_share_or_reserve_is_refused(self):
        for bad in (0, 101, -5, 1.5, True, "60"):
            with self.assertRaises(ValueError):
                g.shares_ok([], bad)
        with self.assertRaises(ValueError):
            g.shares_ok([], 10, reserve_pct=100)


class CapsTests(unittest.TestCase):
    def test_free_credits_use_the_horizon_as_the_month(self):
        c = caps60(weekly_allowance_uu=None)  # a weekly allowance of 10000 * 7 // 30 = 2333
        self.assertEqual(c["monthly_left"], 6000)
        self.assertEqual(c["weekly_left"], 1399)  # 60 percent of 2333
        self.assertEqual(c["daily_full"], 199)  # the empty day is a seventh of the empty week, rounded down

    def test_the_weekly_cap_never_passes_the_monthly_left_over_the_weeks_left(self):
        c = caps60(used_month_uu=5500, weeks_left=2)  # 500 left in the month over 2 weeks
        self.assertEqual(c["weekly_left"], 250)

    def test_the_daily_cap_is_the_weekly_left_over_the_days_left_and_not_above_the_daily_share(self):
        self.assertEqual(caps60(days_left=7, daily_share_uu=None)["daily_left"], 180)  # weekly cap 1260
        self.assertEqual(caps60(days_left=2, daily_share_uu=None)["daily_left"], 630)
        self.assertEqual(caps60(days_left=2, daily_share_uu=150)["daily_left"], 150)

    def test_a_goal_that_used_more_than_its_cap_has_zero_left_not_a_negative(self):
        c = caps60(used_month_uu=9000, used_week_uu=5000)
        self.assertEqual((c["monthly_left"], c["weekly_left"], c["daily_left"]), (0, 0, 0))

    def test_bad_numbers_are_refused(self):
        with self.assertRaises(ValueError):
            caps60(month_allowance_uu=-1)
        with self.assertRaises(ValueError):
            caps60(share_pct=0)


class GateTests(unittest.TestCase):
    def test_a_task_that_fits_goes(self):
        self.assertEqual(g.cap_gate(100, caps60()), ("yes", None))

    def test_a_task_over_the_daily_cap_waits_and_the_next_days_window_lets_it_run(self):
        c = caps60()  # daily left 180
        self.assertEqual(g.cap_gate(150, c, used_today_uu=100), ("wait", "daily cap"))
        self.assertEqual(g.cap_gate(150, c, used_today_uu=0), ("yes", None))  # the day changed: today's use is 0 again

    def test_a_task_over_the_weekly_cap_waits_past_the_day_change(self):
        c = caps60(used_week_uu=1210)  # 50 left this week
        self.assertEqual(g.cap_gate(100, c), ("wait", "weekly cap"))
        self.assertEqual(g.cap_gate(100, caps60(used_week_uu=0)), ("yes", None))  # a new week

    def test_a_task_over_the_monthly_cap_waits_for_the_month(self):
        c = caps60(used_month_uu=5950)  # 50 left in the month
        self.assertEqual(g.cap_gate(100, c), ("wait", "monthly cap"))

    def test_a_task_bigger_than_an_empty_day_is_refused_and_goes_to_the_owner(self):
        c = caps60()  # empty day is 180
        self.assertEqual(g.cap_gate(181, c), ("refuse", "task_larger_than_cap"))
        self.assertEqual(g.cap_gate(180, c), ("yes", None))

    def test_the_widest_window_that_does_not_fit_is_the_one_named(self):
        c = caps60(used_week_uu=1160, days_left=1)  # weekly 100 left, daily 100 left, monthly 6000
        self.assertEqual(g.cap_gate(150, c), ("wait", "weekly cap"))  # it must wait for the next week, not for tomorrow

    def test_the_log_lines_name_the_decision(self):
        self.assertEqual(g.log_line("wait", "daily cap", "alpha"), "goal alpha: waiting, daily cap")
        self.assertEqual(g.log_line("refuse", g.TOO_BIG, "alpha"), "goal alpha: refused, task_larger_than_cap")
        self.assertIn("fits", g.log_line("yes", None, "alpha"))

    def test_this_module_is_called_by_nothing_yet(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]
        callers = [p.name for p in (root / "umwayi").glob("*.py") if p.name != "goalshare.py" and "goalshare" in p.read_text(encoding="utf-8")]
        self.assertEqual(callers, [])  # when something wires it in, the docs and the claim must change in that change


if __name__ == "__main__":
    unittest.main()
