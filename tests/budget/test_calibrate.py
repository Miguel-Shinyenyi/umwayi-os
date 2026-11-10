"""Budget governor, task B.5: rate changes and calibration (B.R1.5, B.R1.8, B-Q3).

A change to units.yaml is one logbook entry before its first use (2 when it cannot be logged); `umwayi budget
calibrate` proposes per_run (1.5 times the 95th percentile) and per_day (2 times the median day) after at least 20
measured runs over at least 7 days, with its data, and changes nothing. Every test runs `python -m umwayi ...` as a
real child process; the fixed data sets are written to the logbook with the checked append before the child runs.
"""

import unittest

from tests.budget.support import UNITS_HEAD, BudgetCase, days_ago, rate, today

END = {"do": "exit", "code": 0}


class ChangeTests(BudgetCase):
    def test_a_change_is_logged_once_before_its_first_use(self):
        self.limits(per_day=500)
        self.assertEqual(self.run_agent("reviewer", END).returncode, 0)
        [c] = self.changes()
        self.assertRegex(c.added, r"^units\.yaml changed \(sha256 [0-9a-f]{64}\): limits\.per_day none to 500$")
        added = [e.added for e in self.entries()]
        self.assertLess(added.index(c.added), next(i for i, a in enumerate(added) if a.startswith("Reserved run ")))
        self.assertEqual(self.run_agent("reviewer", END).returncode, 0)
        self.assertEqual(len(self.changes()), 1)  # unchanged: no second entry
        self.limits(per_day=600, per_run=50)
        self.assertEqual(self.run_agent("reviewer", END).returncode, 0)
        changes = self.changes()
        self.assertEqual(len(changes), 2)
        self.assertTrue(changes[1].added.endswith("): limits.per_day 500 to 600; limits.per_run none to 50"),
                        changes[1].added)
        self.assertIn("Reserved run ", self.reserves()[-1].added)
        self.assertTrue(self.reserves()[-1].added.endswith(": 500000 micros (50 UU)"))  # the new per_run is used

    def test_a_rate_change_names_old_and_new_with_date_and_source(self):
        when = days_ago(3)
        self.units(UNITS_HEAD + "models:\n  m1:\n    input:" + rate(3000000, when) + "\n")
        self.assertEqual(self.run_agent("reviewer", END).returncode, 0)
        self.units(UNITS_HEAD + "models:\n  m1:\n    input:" + rate(3500000, today(), "https://example.com/p") + "\n")
        self.assertEqual(self.run_agent("reviewer", END).returncode, 0)
        c = self.changes()
        self.assertTrue(c[0].added.endswith(f"): models.m1.input none to 3000000 ({when}, owner)"), c[0].added)
        self.assertTrue(c[1].added.endswith(f"): models.m1.input 3000000 ({when}, owner) to 3500000 ({today()}, "
                                            "https://example.com/p)"), c[1].added)

    def test_a_comment_only_change_and_a_removed_file_are_logged_too(self):
        self.limits(per_day=500)
        self.run_agent("reviewer", END)
        self.units(UNITS_HEAD + "# a comment\nlimits:\n  per_day: 500\n")
        self.run_agent("reviewer", END)
        (self.root / "units.yaml").unlink()
        self.run_agent("reviewer", END)
        c = [e.added for e in self.changes()]
        self.assertEqual(len(c), 3)
        self.assertTrue(c[1].endswith("): no rate or limit changed"), c[1])
        self.assertEqual(c[2], "units.yaml changed (removed): limits.per_day 500 to none")
        s = self.budget("status")
        self.assertNotIn("units.yaml changed since", s.stdout)

    def test_a_change_that_cannot_be_logged_starts_nothing(self):
        self.limits(per_day=500)
        # the first append (the agent_run check) works; the next one, the change entry, is refused
        r = self.run_agent("reviewer", END, fault="umwayi.logbook:append:error_after", extra={"UMWAYI_FAULT_AFTER": "1"})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("units.yaml changed, but the change could not be logged (planted: this write fails), so the new "
                      "values are not used. Agent reviewer was not started. (exit 2)", r.stdout)
        self.assertEqual(self.started(), [])
        self.assertEqual(self.budget_entries(), [])
        s = self.budget("status")
        self.assertIn("units.yaml changed since the last logged change", s.stdout)


class CalibrateTests(BudgetCase):
    def fixture(self, n_runs, n_days, extra=()):
        rows = []
        for i in range(1, n_runs + 1):
            rows.append((days_ago(n_days - (i % n_days)), "reviewer", "claude-code", 3000000, "measured", i * 100000))
        rows += list(extra)
        self.write_ledger(sorted(rows, key=lambda r: r[0]))

    def test_19_runs_or_6_days_give_no_proposal(self):
        self.fixture(19, 7)
        r = self.budget("calibrate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Not enough data: 19 measured run(s) over 7 day(s). Calibration needs at least 20 measured runs "
                      "over at least 7 days (1 more run(s), 0 more day(s)). Nothing was changed.", r.stdout)

    def test_6_days_give_no_proposal(self):
        self.fixture(24, 6)
        r = self.budget("calibrate")
        self.assertIn("Not enough data: 24 measured run(s) over 6 day(s).", r.stdout)
        self.assertIn("(0 more run(s), 1 more day(s))", r.stdout)

    def test_the_proposal_on_a_fixed_data_set_changes_nothing(self):
        # runs 1..20 of i * 100000 micros, run i on day i % 7; declared and unknown runs are not measured: ignored
        self.fixture(20, 7, extra=[(days_ago(1), "helper", "kiro", 1000000, "declared", 900000),
                                   (days_ago(2), "reviewer", "claude-code", 1000000, "unknown", 1000000),
                                   (days_ago(2), "reviewer", "claude-code", 1000000, None, 0)])
        before = (self.root / "LOGBOOK.md").read_bytes()
        r = self.budget("calibrate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = r.stdout
        self.assertIn("Data: 20 measured run(s) over 7 day(s)", out)
        self.assertIn("95th percentile of one measured run (nearest rank 19 of 20): 1900000 micros (190 UU).", out)
        # day totals 2.1, 2.4, 2.7, 3.0, 3.3, 3.6 and 3.9 million micros: the median is 3.0 million
        self.assertIn("Median measured day: 3000000 micros (of 7 day totals).", out)
        self.assertIn("Proposed limits.per_run: 285 UU (1.5 times the 95th percentile, rounded up; now 100 UU).", out)
        self.assertIn("Proposed limits.per_day: 600 UU (2 times the median day, rounded up; now 500 UU).", out)
        self.assertIn("Nothing was changed. To apply, edit units.yaml yourself", out)
        self.assertEqual((self.root / "LOGBOOK.md").read_bytes(), before)
        self.assertFalse((self.root / "units.yaml").exists())

    def test_an_even_number_of_days_takes_the_mean_of_the_middle_two(self):
        self.fixture(20, 8)
        r = self.budget("calibrate")
        self.assertIn("over 8 day(s)", r.stdout)
        # days: i % 8 = 0: 8, 16 (24); 1: 1, 9, 17 (27); 2: 2, 10, 18 (30); 3: 3, 11, 19 (33); 4: 4, 12, 20 (36);
        # 5: 5, 13 (18); 6: 6, 14 (20); 7: 7, 15 (22) -> 18, 20, 22, 24, 27, 30, 33, 36 (x 100000): median 25.5
        self.assertIn("Median measured day: 2550000 micros (of 8 day totals).", r.stdout)
        self.assertIn("Proposed limits.per_day: 510 UU", r.stdout)


if __name__ == "__main__":
    unittest.main()
