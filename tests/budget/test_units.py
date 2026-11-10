"""Budget governor, task B.1: units.yaml (the schema, validation with line numbers, exit 64, whole micros).

Every test runs `python -m umwayi budget validate` (or `budget status`, `agent run`) as a real child process.
"""

import unittest

from tests.budget.support import SECRET, UNITS_HEAD, BudgetCase, days_ago, rate, today

VALID = UNITS_HEAD + f"""platforms:
  claude-code:
    reading: usd_micros
    fallback: tokens
  kiro:
    reading: runs
    run_micros:{rate(400000)}
models:
  claude-sonnet-5:
    input:{rate(3000000, source="https://example.com/pricing", indent=6)}
    output:{rate(15000000, indent=6)}
limits:
  per_run: 100
  per_day: 500
"""


class ValidateTests(BudgetCase):
    def validate(self, text):
        self.units(text)
        return self.budget("validate")

    def assert_problem(self, text, line, fragment):
        r = self.validate(text)
        self.assertEqual(r.returncode, 64, r.stdout + r.stderr)
        self.assertIn(f"problem: line {line}: ", r.stdout)
        found = [x for x in r.stdout.splitlines() if x.startswith(f"problem: line {line}: ")]
        self.assertTrue(any(fragment in x for x in found), f"{fragment!r} not at line {line}:\n{r.stdout}")
        self.assertNotIn(SECRET, r.stdout + r.stderr)
        return r

    def test_a_valid_file_is_ok(self):
        r = self.validate(VALID)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ok: units.yaml is valid: 2 platform(s), 1 model(s)", r.stdout)
        self.assertIn("per_run 100 UU, per_day 500 UU, per_agent_per_day 300 UU", r.stdout)  # the rest: placeholders

    def test_a_missing_file_is_all_unknown_under_the_placeholders(self):
        r = self.budget("validate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("there is no units.yaml; every reading is unknown and counts at the worst case", r.stdout)
        self.assertIn("per_run 100 UU, per_day 500 UU, per_agent_per_day 300 UU, per_platform_per_day 400 UU, "
                      "unknown_worst_case 100 UU", r.stdout)
        s = self.budget("status")
        self.assertEqual(s.returncode, 0, s.stdout + s.stderr)
        self.assertIn("per_day: used 0 UU, reserved 0 UU, left 500 UU (limit 500 UU)", s.stdout)
        self.assertIn("There is no units.yaml: every reading is unknown and the limits are the placeholders.",
                      s.stdout)

    def test_floats_are_refused(self):
        self.assert_problem(UNITS_HEAD + "limits:\n  per_day: 5.5\n", 3, "limits.per_day must be a whole number, "
                                                                       "not a decimal")
        self.assert_problem(UNITS_HEAD + "models:\n  m1:\n    input:\n      value: 3.75\n      date: "
                            f"{today()}\n      source: owner\n", 5, "value must be a whole number, not a decimal")

    def test_every_bad_value_has_its_line(self):
        cases = [
            (UNITS_HEAD + "limits:\n  per_day: -1\n", 3, "limits.per_day must be a whole number from 0 to "),
            (UNITS_HEAD + "limits:\n  per_day: 1000000000001\n", 3, "limits.per_day must be a whole number from 0"),
            (UNITS_HEAD + "limits:\n  per_day: \"500\"\n", 3, "limits.per_day must be a whole number"),
            (UNITS_HEAD + "limits:\n  per_day: true\n", 3, "limits.per_day must be a whole number"),
            (UNITS_HEAD + "limits:\n  per_week: 5\n", 3, "'per_week' is not a limit"),
            (UNITS_HEAD + f"limits:\n  per_run: {SECRET}\n", 3, "limits.per_run must be a whole number"),
            ("version: 2\n", 1, "version must be 1"),
            (UNITS_HEAD + "budget: 5\n", 2, "'budget' is not allowed at the top"),
            (UNITS_HEAD + "platforms:\n  kiro:\n    reading: dollars\n", 4, "reading must be one of: usd_micros, "
                                                                         "tokens, credits, runs"),
            (UNITS_HEAD + "platforms:\n  kiro:\n    reading: runs\n", 3, "reading runs needs run_micros"),
            (UNITS_HEAD + "platforms:\n  kiro:\n    reading: runs\n    fallback: tokens\n    run_micros:"
             + rate(1) + "\n", 5, "fallback may only be tokens, and only with reading usd_micros"),
            (UNITS_HEAD + "platforms:\n  kiro:\n    reading: credits\n    credit_micros:" + rate(1) + "\n", 3,
             "reading credits needs credits_per_run"),
            (UNITS_HEAD + "platforms:\n  Kiro:\n    reading: runs\n", 3, "a platform name must be a lowercase"),
            (UNITS_HEAD + "models:\n  m1:\n    prompt:" + rate(1) + "\n", 4, "'prompt' is not a token type"),
            (UNITS_HEAD + "models:\n  m1:\n    input:" + rate(1) + "\n      per: million\n", 8,
             "'per' is not allowed, only value, date and source"),
        ]
        for text, line, fragment in cases:
            with self.subTest(fragment=fragment):
                self.assert_problem(text, line, fragment)

    def test_a_rate_without_a_date_or_a_source_is_refused(self):
        r = self.assert_problem(UNITS_HEAD + "models:\n  m1:\n    input:\n      value: 3\n      source: owner\n", 4,
                                "models.m1.input needs date")
        self.assertIn("1 problem(s) found in units.yaml", r.stdout)
        self.assert_problem(UNITS_HEAD + f"models:\n  m1:\n    input:\n      value: 3\n      date: {today()}\n", 4,
                            "models.m1.input needs source")
        self.assert_problem(UNITS_HEAD + f"platforms:\n  kiro:\n    reading: runs\n    run_micros:\n      value: 3\n",
                            5, "platforms.kiro.run_micros needs date")
        for source in ("http://example.com/x", "someone", f"https://example.com/{SECRET}, x", "https://a b"):
            with self.subTest(source=source):
                self.assert_problem(UNITS_HEAD + f"models:\n  m1:\n    input:\n      value: 3\n      date: {today()}\n"
                                    f"      source: {source}\n", 7, "source must be owner or an https URL")

    def test_a_future_date_is_refused_and_a_past_one_is_fine(self):
        future = "2999-01-01"
        self.assert_problem(UNITS_HEAD + f"models:\n  m1:\n    input:\n      value: 3\n      date: {future}\n"
                            "      source: owner\n", 6, "date must not be in the future")
        self.assert_problem(UNITS_HEAD + "models:\n  m1:\n    input:\n      value: 3\n      date: 2026-02-30\n"
                            "      source: owner\n", 6, "date must be a real date YYYY-MM-DD")
        r = self.validate(UNITS_HEAD + f"models:\n  m1:\n    input:\n      value: 3\n      date: {days_ago(30)}\n"
                          "      source: owner\n")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_every_problem_is_reported_in_line_order(self):
        r = self.validate(UNITS_HEAD + "limits:\n  per_day: 1.5\n  per_run: -2\nextra: 1\n")
        self.assertEqual(r.returncode, 64)
        lines = [x for x in r.stdout.splitlines() if x.startswith("problem: ")]
        self.assertEqual([x.split(":")[1].strip() for x in lines], ["line 3", "line 4", "line 5"])
        self.assertIn("3 problem(s) found in units.yaml", r.stdout)

    def test_not_yaml_a_link_and_a_folder_are_refused(self):
        r = self.validate("version: 1\n  bad: indent\n")
        self.assertEqual(r.returncode, 64)
        self.assertIn("problem: line 2: ", r.stdout)
        (self.root / "units.yaml").unlink()
        (self.tmp / "elsewhere.yaml").write_text(VALID, encoding="utf-8")
        (self.root / "units.yaml").symlink_to(self.tmp / "elsewhere.yaml")
        r = self.budget("validate")
        self.assertEqual(r.returncode, 64)
        self.assertIn("units.yaml must be a regular file, not a link or a folder", r.stderr)

    def test_an_invalid_file_starts_no_agent(self):
        self.units(UNITS_HEAD + "limits:\n  per_day: 5.5\n")
        r = self.run_agent("reviewer", {"do": "exit", "code": 0})
        self.assertEqual(r.returncode, 64, r.stdout + r.stderr)
        self.assertIn("units.yaml has 1 problem(s), see 'umwayi budget validate'. Nothing was started.", r.stdout)
        self.assertEqual(self.started(), [])
        self.assertEqual(self.reserves(), [])
        self.assertIn("Refused agent reviewer: units.yaml is not valid", [e.added for e in self.entries()])
        s = self.budget("status")
        self.assertEqual(s.returncode, 64)


if __name__ == "__main__":
    unittest.main()
