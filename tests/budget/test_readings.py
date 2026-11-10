"""Budget governor, task B.2: readings and tags (measured, declared, unknown at the worst case, never zero).

Every test runs `python -m umwayi agent run ...` as a real child process. The fake `claude` sends the scripted
OTLP reports to the receiver of its run; the fake `kiro-cli` sends nothing (umwayi reads no telemetry from Kiro).
"""

import unittest

from tests.budget.support import (UNITS_HEAD, BudgetCase, api_request, cost_point, rate, send_logs, send_metrics,
                                  token_point)

RATES = UNITS_HEAD + f"""platforms:
  claude-code:
    reading: usd_micros
    fallback: tokens
models:
  claude-sonnet-5:
    input:{rate(3000000)}
    output:{rate(15000000)}
"""


class ReadingTests(BudgetCase):
    def settled(self):
        [s] = self.settles()
        return s.added

    def test_api_request_events_are_measured_and_rounded_up_to_uu(self):
        r = self.run_agent("reviewer", send_logs(api_request(cost_micros=12345), api_request(cost_micros=1)))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        added = self.settled()
        self.assertIn(": measured 12346 micros (2 UU); models claude-sonnet-5; tokens input 200, output 40, "
                      "cache_read 10, cache_creation 2; requests 2; released 987654 micros", added)
        self.assertIn("Budget: run ", r.stdout)
        self.assertIn("settled, measured 2 UU (12346 micros).", r.stdout)

    def test_a_zero_reading_is_measured_as_zero(self):
        r = self.run_agent("reviewer", send_logs(api_request(cost_micros=0, input_tokens=0, output_tokens=0,
                                                             cache_read=0, cache_creation=0)))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(": measured 0 micros (0 UU); ", self.settled())

    def test_a_missing_reading_is_never_zero(self):
        r = self.run_agent("reviewer", {"do": "exit", "code": 0})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        added = self.settled()
        self.assertIn(": unknown 1000000 micros (100 UU); models none; tokens input 0, output 0, cache_read 0, "
                      "cache_creation 0; requests 0; released 0 micros", added)
        [s] = self.settles()
        self.assertIn("reading: no report arrived", s.checked)

    def test_the_cost_metric_alone_is_measured(self):
        r = self.run_agent("reviewer", send_metrics([cost_point(0.0123)]))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(": measured 12300 micros (2 UU); models claude-sonnet-5;", self.settled())

    def test_token_counts_alone_are_declared_at_the_rates_and_rounded_up(self):
        self.units(RATES)
        r = self.run_agent("reviewer", send_metrics(token_points=[token_point(1, "input"), token_point(1, "output")]))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # 1 input token at 3000000 and 1 output token at 15000000 micros per million: 18 micros, 1 UU
        self.assertIn(": declared 18 micros (1 UU); models claude-sonnet-5; tokens input 1, output 1,", self.settled())

    def test_token_counts_of_an_unknown_model_or_type_are_unknown(self):
        self.units(RATES)
        r = self.run_agent("reviewer", send_metrics(token_points=[token_point(5, "input", model="claude-other-9")]))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(": unknown 1000000 micros (100 UU); models claude-other-9;", self.settled())
        self.assertIn("token counts arrived for a model or type without a rate", self.settles()[0].checked)
        self.fake_log.unlink()
        r = self.run_agent("reviewer", send_metrics(token_points=[token_point(5, "cacheRead")]))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(": unknown 1000000 micros (100 UU);", self.settles()[-1].added)

    def test_without_a_fallback_token_counts_alone_are_unknown(self):
        r = self.run_agent("reviewer", send_metrics(token_points=[token_point(5, "input")]))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(": unknown 1000000 micros (100 UU);", self.settled())

    def test_a_model_name_that_is_not_plain_is_other(self):
        r = self.run_agent("reviewer", send_logs(api_request(cost_micros=5, model="model with spaces; and more")))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("; models other; ", self.settled())

    def test_kiro_runs_are_declared_at_run_micros(self):
        self.units(UNITS_HEAD + "platforms:\n  kiro:\n    reading: runs\n    run_micros:" + rate(400000) + "\n")
        r = self.run_agent("helper")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Settled run ", self.settled())
        self.assertIn("for agent helper (kiro): declared 400000 micros (40 UU); models none;", self.settled())
        self.assertIn("no telemetry receiver for this platform", self.settles()[0].checked)

    def test_kiro_credits_are_credits_per_run_times_the_credit_rate(self):
        self.units(UNITS_HEAD + "platforms:\n  kiro:\n    reading: credits\n    credit_micros:" + rate(40000)
                   + "\n    credits_per_run:" + rate(3) + "\n")
        r = self.run_agent("helper")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("for agent helper (kiro): declared 120000 micros (12 UU);", self.settled())

    def test_kiro_with_nothing_declared_is_unknown_at_the_worst_case(self):
        self.units(UNITS_HEAD + "limits:\n  unknown_worst_case: 70\n")
        r = self.run_agent("helper")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("for agent helper (kiro): unknown 700000 micros (70 UU);", self.settled())
        self.assertIn("units.yaml declares nothing for kiro", self.settles()[0].checked)


if __name__ == "__main__":
    unittest.main()
