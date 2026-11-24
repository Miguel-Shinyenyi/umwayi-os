"""M4 b: pacing. Spread what is left of a provider's allowance over its period, and say so when a goal is bigger than today's share.

`pace` is a pure function (no clock, no file, nothing spent). The tests give it the date, so a UTC or local day can never change a
result. Planted faults: a goal over the share carries the line; a goal at or under it carries none; a past `until` falls back to the
horizon; a paid provider and a five hour only subscription have no daily share.
"""
import unittest

from umwayi import units

TODAY = "2026-11-24"
BASE = "version: 1\n"


def provider(body):
    u, p = units.check_text(BASE + "providers:\n  muse:\n" + body, TODAY)
    assert not p, [x.message for x in p]
    return u.providers["muse"]


FREE = "    cost_kind: free_credits\n    limit:\n      credits_uu: 14000\n"


class PaceTests(unittest.TestCase):
    def test_free_credits_spread_over_the_days_to_until(self):
        p = provider(FREE + "    until: 2026-12-04\n")
        self.assertEqual(units.pace(p, 14000, TODAY), (1400, 10))
        self.assertEqual(units.pace(p, 14001, TODAY), (1400, 10))  # rounds down: never more than the share
        self.assertEqual(units.pace(p, 0, TODAY), (0, 10))

    def test_without_a_future_until_the_horizon_is_used_and_the_default_is_30_days(self):
        self.assertEqual(units.pace(provider(FREE), 14400, TODAY), (480, 30))
        self.assertEqual(units.pace(provider(FREE + "    horizon_days: 10\n"), 14000, TODAY), (1400, 10))
        self.assertEqual(units.pace(provider(FREE + "    until: 2026-11-01\n"), 14400, TODAY), (480, 30))  # past: the horizon
        self.assertEqual(units.pace(provider(FREE + "    until: 2026-11-24\n"), 14400, TODAY), (480, 30))  # today: not a future date

    def test_the_last_day_gets_the_whole_of_what_is_left(self):
        self.assertEqual(units.pace(provider(FREE + "    until: 2026-11-25\n"), 900, TODAY), (900, 1))

    def test_a_subscription_with_a_weekly_allowance_uses_the_days_left_in_the_week(self):
        p = provider("    cost_kind: subscription\n    limit:\n      weekly_uu: 4000\n")
        self.assertEqual(units.pace(p, 4000, TODAY), (571, 7))
        self.assertEqual(units.pace(p, 1000, TODAY, days_left_in_week=2), (500, 2))
        self.assertEqual(units.pace(p, 1000, TODAY, days_left_in_week=0), (142, 7))  # 0 means unknown: the full week

    def test_a_five_hour_only_subscription_and_a_paid_provider_have_no_daily_share(self):
        self.assertIsNone(units.pace(provider("    cost_kind: subscription\n    limit:\n      five_hour_uu: 500\n"), 500, TODAY))
        self.assertIsNone(units.pace(provider("    cost_kind: paid\n    limit:\n      cap_uu: 300\n"), 300, TODAY))

    def test_until_and_horizon_are_checked(self):
        for bad in ("    until: tomorrow\n", "    until: 2026-13-01\n", "    horizon_days: 0\n", "    horizon_days: 400\n",
                    "    horizon_days: many\n", "    horizon_days: true\n"):
            with self.subTest(bad=bad):
                u, p = units.check_text(BASE + "providers:\n  muse:\n" + FREE + bad, TODAY)
                self.assertIsNone(u)
                self.assertTrue(p)


class LineTests(unittest.TestCase):
    def test_planted_fault_a_goal_over_the_share_carries_the_line_and_the_numbers(self):
        line = units.pacing_line(1400, 10, 1500)
        self.assertEqual(line, "pacing: this goal is estimated at 1500 UU, above today's share of 1400 UU (what is left spread over 10 day(s)). "
                               "It may run; the allowance will not last the period at this rate.")

    def test_a_goal_at_or_under_the_share_carries_no_line(self):
        self.assertIsNone(units.pacing_line(1400, 10, 1400))
        self.assertIsNone(units.pacing_line(1400, 10, 25))
        self.assertIsNone(units.pacing_line(0, 10, 0))
        self.assertIsNotNone(units.pacing_line(0, 10, 1))


if __name__ == "__main__":
    unittest.main()
