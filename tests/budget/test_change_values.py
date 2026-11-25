"""The change entries of units.yaml in the budget ledger: the reader accepts every value shape that `units.Units.state` writes.

Found by CI on the Muse gates (2026-11-25): an acceptance is written as `10000 UU (2026-11-23, owner)`, a provider `until` as a date and a provider name may hold
digits or a hyphen, but the reader only took a bare number with the owner's `(date, source)`, a lowercase word without digits, and no date. So after the first
start with an acceptance in units.yaml every start was refused ("is not a units.yaml change entry"). The strictness stays: an odd value is still refused."""
import tempfile
import unittest
from pathlib import Path

from umwayi import budget, logbook, units

TODAY = "2026-11-25"
SHA = "a" * 64
FULL = """version: 1
public: true
providers:
  muse-free2:
    cost_kind: free_credits
    limit:
      credits_uu: 10000
    until: 2026-12-31
    acceptance:
      accepted_free: true
      date: 2026-11-23
      amount_uu: 10000
      source: owner
goals:
  big-goal:
    provider: muse-free2
    share: 60
"""


class ValueShapeTests(unittest.TestCase):
    def read_back(self, text):
        u, problems = units.check_text(text, TODAY, SHA)
        self.assertEqual(problems, [])
        with tempfile.TemporaryDirectory() as d:
            added = budget.pending_change(u, budget.Ledger())
            logbook.append(Path(d), budget.change_entry(TODAY, added))
            led = budget.read_ledger(Path(d))  # raises LedgerError for a value the reader does not know
            return u, led

    def test_every_value_state_writes_is_read_back_and_the_state_matches(self):
        u, led = self.read_back(FULL)
        self.assertEqual(led.units_state, u.state())
        self.assertEqual(led.units_state["providers.muse-free2.acceptance"], "10000 UU (2026-11-23, owner)")
        self.assertEqual(led.units_state["providers.muse-free2.until"], "2026-12-31")
        self.assertEqual(led.units_state["goals.big-goal.provider"], "muse-free2")

    def test_the_item_pattern_takes_the_shapes_and_refuses_odd_values(self):
        ok = ("providers.m.acceptance none to 10000 UU (2026-11-23, owner)", "providers.m.until none to 2026-12-31",
              "goals.g.provider none to a-b2", "limits.per_day 500 to 600", "public none to true")
        for item in ok:
            self.assertIsNotNone(budget._ITEM.match(item), item)
        bad = ("x none to 10000 UU (2026-11-23, owner", "x none to 10000 UU (bad, owner)", "x none to 10000 uu", "x none to A", "x none to 1 2",
               "x none to 10000 UU (2026-11-23, owner;x)", "x none to ")
        for item in bad:
            self.assertIsNone(budget._ITEM.match(item), item)

    def test_a_change_entry_with_an_odd_value_still_stops_every_start(self):
        with tempfile.TemporaryDirectory() as d:
            added = f"units.yaml changed (sha256 {SHA}): providers.m.acceptance none to 10000 UU (2026-11-23, owner"
            logbook.append(Path(d), budget.change_entry(TODAY, added))
            with self.assertRaises(budget.LedgerError):
                budget.read_ledger(Path(d))


if __name__ == "__main__":
    unittest.main()
