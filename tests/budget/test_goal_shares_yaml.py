"""M4 h, part 2: the `goals` section of units.yaml and the lines of `umwayi budget status`. These call `check_text` and `goal_lines`
directly, so they run on any machine. Nothing here starts, stops or spends anything."""
import unittest

from umwayi import units

TODAY = "2026-11-25"
HEAD = """version: 1
providers:
  muse:
    cost_kind: free_credits
    limit:
      credits_uu: 10000
    acceptance:
      accepted_free: true
      date: 2026-11-23
      amount_uu: 10000
      source: owner
  other:
    cost_kind: paid
    limit:
      cap_uu: 500
"""


def goals(*rows):
    return HEAD + "goals:\n" + "".join(f"  {n}:\n    provider: {p}\n    share: {s}\n" for n, p, s in rows)


def parse(text):
    return units.check_text(text, TODAY)


def messages(text):
    u, p = parse(text)
    return [x.message for x in p] if p else []


class ParseTests(unittest.TestCase):
    def test_a_file_without_goals_is_as_before(self):
        u, p = parse(HEAD)
        self.assertEqual((p, u.goals), ([], {}))

    def test_a_goal_with_a_share_loads_and_is_in_the_state(self):
        u, p = parse(goals(("alpha", "muse", 60)))
        self.assertEqual(p, [])
        self.assertEqual(u.goals["alpha"], units.GoalShare("muse", 60))
        self.assertEqual(u.state()["goals.alpha.provider"], "muse")
        self.assertEqual(u.state()["goals.alpha.share"], "60")

    def test_shares_on_one_provider_add_up_to_80_and_the_next_is_refused(self):
        self.assertEqual(messages(goals(("alpha", "muse", 40), ("beta", "muse", 40))), [])
        bad = messages(goals(("alpha", "muse", 40), ("beta", "muse", 41)))
        self.assertEqual(len(bad), 1)
        self.assertIn("share_over_allocated", bad[0])

    def test_shares_on_two_providers_do_not_add_up_together(self):
        self.assertEqual(messages(goals(("alpha", "muse", 80), ("beta", "other", 80))), [])

    def test_a_bad_share_is_refused(self):
        for bad in ("0", "101", "-3", "1.5", "true", "sixty"):
            text = HEAD + f"goals:\n  alpha:\n    provider: muse\n    share: {bad}\n"
            self.assertEqual(len(messages(text)), 1, bad)

    def test_an_unknown_provider_extra_keys_and_a_bad_name_are_refused(self):
        self.assertEqual(len(messages(goals(("alpha", "nope", 10)))), 1)
        self.assertEqual(len(messages(HEAD + "goals:\n  alpha:\n    provider: muse\n    share: 10\n    note: x\n")), 1)
        self.assertEqual(len(messages(HEAD + "goals:\n  Alpha:\n    provider: muse\n    share: 10\n")), 1)
        self.assertEqual(len(messages(HEAD + "goals: 5\n")), 1)

    def test_an_error_names_a_line(self):
        u, p = parse(goals(("alpha", "muse", 90)))
        self.assertTrue(p[0].line > 0)


class LineTests(unittest.TestCase):
    def test_a_free_credit_goal_shows_the_full_caps_and_says_use_is_not_recorded(self):
        u, _ = parse(goals(("alpha", "muse", 60)))
        (line,) = units.goal_lines(u)
        self.assertIn("goal alpha: share 60% of muse", line)
        self.assertIn("at most 6000 UU in the 30 day period", line)
        self.assertIn("1399 UU a week", line)
        self.assertIn("199 UU a day", line)
        self.assertIn("not recorded yet", line)

    def test_a_goal_on_a_paid_provider_says_the_caps_are_not_computed(self):
        u, _ = parse(goals(("alpha", "other", 10)))
        (line,) = units.goal_lines(u)
        self.assertIn("the caps are not computed", line)

    def test_no_goals_no_lines(self):
        u, _ = parse(HEAD)
        self.assertEqual(units.goal_lines(u), [])


if __name__ == "__main__":
    unittest.main()
