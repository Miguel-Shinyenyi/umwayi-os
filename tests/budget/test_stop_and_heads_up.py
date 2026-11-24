"""M4 c and d: the heads up lines and the stop line, as pure functions over a provider.

A heads up is a line at the start of a goal with the limit left, today's share and the estimate, and a louder line when the limit left
crosses 50, 20 and 10 percent of the amount at acceptance. The stop line refuses NEW runs: a free credit provider at 5 percent left (so the
card on file is never charged by accident), a subscription at 80 percent of the five hour allowance or 90 percent of the weekly one. The
owner moves or removes a stop by hand. The tests give the numbers; nothing reads a clock, a file or a balance.
"""
import unittest

from umwayi import units

TODAY = "2026-11-24"
ACCEPT = "    acceptance:\n      accepted_free: true\n      date: 2026-11-23\n      amount_uu: 10000\n      source: owner\n"
FREE = "    cost_kind: free_credits\n    limit:\n      credits_uu: 10000\n" + ACCEPT
SUB = "    cost_kind: subscription\n    limit:\n      five_hour_uu: 500\n      weekly_uu: 4000\n" + ACCEPT


def provider(body):
    u, p = units.check_text("version: 1\nproviders:\n  muse:\n" + body, TODAY)
    assert not p, [x.message for x in p]
    return u.providers["muse"]


class LevelTests(unittest.TestCase):
    def test_percent_left_rounds_down_and_stays_in_range(self):
        self.assertEqual([units.percent_left(10000, n) for n in (10000, 9999, 5000, 1, 0, -5, 20000)], [100, 99, 50, 0, 0, 0, 100])
        self.assertEqual(units.percent_left(0, 100), 0)

    def test_the_level_is_the_lowest_of_50_20_and_10_that_the_percent_is_at_or_under(self):
        got = {n: units.heads_up_level(10000, n) for n in (10000, 5001, 5000, 3000, 2001, 2000, 1500, 1001, 1000, 500, 0)}
        self.assertEqual(got, {10000: None, 5001: None, 5000: 50, 3000: 50, 2001: 50, 2000: 20, 1500: 20, 1001: 20, 1000: 10, 500: 10, 0: 10})


class HeadsUpTests(unittest.TestCase):
    def test_the_first_line_gives_the_limit_left_the_share_and_the_estimate(self):
        p = provider(FREE + "    until: 2026-12-04\n")
        lines = units.heads_up(p, 8000, TODAY, estimate_uu=300)
        self.assertEqual(lines, ["heads up: 8000 of 10000 UU left (80 percent); today's share is 800 UU over 10 day(s); this goal is estimated at 300 UU."])

    def test_a_goal_over_the_share_gets_the_pacing_line_too(self):
        p = provider(FREE + "    until: 2026-12-04\n")
        lines = units.heads_up(p, 8000, TODAY, estimate_uu=900)
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[1].startswith("pacing: this goal is estimated at 900 UU, above today's share of 800 UU"))

    def test_planted_fault_crossing_each_level_adds_the_louder_line(self):
        p = provider(FREE)
        for left, level in ((5000, 50), (2000, 20), (1000, 10)):
            with self.subTest(left=left):
                lines = units.heads_up(p, left, TODAY)
                self.assertEqual(lines[-1], f"HEADS UP: under {level} percent of the amount at acceptance is left ({left} of 10000 UU).")
        self.assertFalse(any(l.startswith("HEADS UP") for l in units.heads_up(p, 5001, TODAY)))

    def test_no_estimate_no_share_and_a_provider_that_is_not_accepted_or_is_paid(self):
        sub = provider(SUB)
        self.assertEqual(units.heads_up(sub, 4000, TODAY)[0], "heads up: 4000 of 10000 UU left (40 percent); today's share is 571 UU over 7 day(s).")
        no_accept = provider("    cost_kind: free_credits\n    limit:\n      credits_uu: 10000\n")
        self.assertEqual(units.heads_up(no_accept, 8000, TODAY), [])  # the gate asks first: no heads up for what is not accepted
        paid = provider("    cost_kind: paid\n    limit:\n      cap_uu: 300\n")
        self.assertEqual(units.heads_up(paid, 300, TODAY), [])  # a paid provider asks on every goal: a heads up is not enough
        five_only = provider("    cost_kind: subscription\n    limit:\n      five_hour_uu: 500\n" + ACCEPT)
        self.assertNotIn("today's share", units.heads_up(five_only, 8000, TODAY)[0])


class StopTests(unittest.TestCase):
    def test_planted_fault_a_free_credit_provider_at_or_under_five_percent_left_is_refused(self):
        p = provider(FREE)
        self.assertEqual(units.stop_gate(p, left_uu=500), ("no", "credits_low"))  # exactly 5 percent
        self.assertEqual(units.stop_gate(p, left_uu=0), ("no", "credits_low"))
        self.assertEqual(units.stop_gate(p, left_uu=501), ("yes", "within_limits"))
        self.assertEqual(units.stop_gate(p, left_uu=10000), ("yes", "within_limits"))

    def test_the_owner_moves_or_removes_the_free_stop_by_hand(self):
        self.assertEqual(units.stop_gate(provider(FREE + "    stop_left_pct: 10\n"), left_uu=1000), ("no", "credits_low"))
        self.assertEqual(units.stop_gate(provider(FREE + "    stop_left_pct: 10\n"), left_uu=1001), ("yes", "within_limits"))
        self.assertEqual(units.stop_gate(provider(FREE + "    stop_left_pct: 0\n"), left_uu=0), ("yes", "within_limits"))

    def test_a_subscription_stops_at_80_percent_of_the_five_hour_or_90_of_the_weekly(self):
        p = provider(SUB)
        self.assertEqual(units.stop_gate(p, five_hour_used_pct=80, weekly_used_pct=10), ("no", "five_hour_stop"))
        self.assertEqual(units.stop_gate(p, five_hour_used_pct=79, weekly_used_pct=90), ("no", "weekly_stop"))
        self.assertEqual(units.stop_gate(p, five_hour_used_pct=79, weekly_used_pct=89), ("yes", "within_limits"))
        custom = provider(SUB + "    five_hour_stop_pct: 100\n    weekly_stop_pct: 50\n")
        self.assertEqual(units.stop_gate(custom, five_hour_used_pct=99, weekly_used_pct=49), ("yes", "within_limits"))
        self.assertEqual(units.stop_gate(custom, weekly_used_pct=50), ("no", "weekly_stop"))  # the removed five hour stop needs no reading

    def test_when_the_reading_the_stop_needs_is_not_known_it_asks(self):
        self.assertEqual(units.stop_gate(provider(FREE)), ("ask", "use_unknown"))
        self.assertEqual(units.stop_gate(provider("    cost_kind: free_credits\n    limit:\n      credits_uu: 10000\n"), left_uu=9000), ("ask", "use_unknown"))
        self.assertEqual(units.stop_gate(provider(SUB), five_hour_used_pct=10), ("ask", "use_unknown"))

    def test_a_paid_provider_asks_on_every_goal_and_has_no_stop_line(self):
        self.assertEqual(units.stop_gate(provider("    cost_kind: paid\n    limit:\n      cap_uu: 300\n"), left_uu=0), ("ask", "paid_asks_every_goal"))

    def test_the_stop_keys_are_checked(self):
        for bad in ("    stop_left_pct: 101\n", "    stop_left_pct: -1\n", "    five_hour_stop_pct: lots\n", "    weekly_stop_pct: true\n"):
            with self.subTest(bad=bad):
                u, p = units.check_text("version: 1\nproviders:\n  muse:\n" + FREE + bad, TODAY)
                self.assertIsNone(u)
                self.assertTrue(p)

    def test_nothing_is_changed_by_asking(self):
        p = provider(FREE)
        before = (p.stop_left_pct, p.limit, p.acceptance)
        units.stop_gate(p, left_uu=100)
        units.heads_up(p, 100, TODAY)
        self.assertEqual((p.stop_left_pct, p.limit, p.acceptance), before)


if __name__ == "__main__":
    unittest.main()
