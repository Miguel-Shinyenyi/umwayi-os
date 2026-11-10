"""Budget governor, task B.9: the end to end tests of B.R3.2.

Missing telemetry, huge numbers, a wrong header, an oversize body, a rate change, a limit hit before the start and
in the middle of a run, the kill switch and a logbook failure winning over the budget, and no prompt or response
text in any output. Each is one scenario of real child processes (`agent run`, then `budget status`, then
`logbook verify`), with the hash chain started as the owner does once.
"""

import json
import unittest

from tests.budget.support import (PROMPT_TEXT, SECRET, UNITS_HEAD, BudgetCase, api_request, logs, rate, send_logs,
                                  send_metrics, token_point, user_prompt_event)

END = {"do": "exit", "code": 0}
WAIT = {"do": "sleep", "s": 20}


class EndToEndTests(BudgetCase):
    def setUp(self):
        super().setUp()
        self.u("check", json.dumps({"type": "read_memory"}))
        r = self.u("logbook", "seal", "--chain", "--by", "Owner")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def tearDown(self):
        v = self.u("logbook", "verify")
        self.assertEqual(v.returncode, 0, v.stdout)  # every scenario leaves an intact, chained logbook
        self.assertIn("hash chain", v.stdout)
        self.assert_no_planted_text()

    def status(self):
        s = self.budget("status")
        self.assertEqual(s.returncode, 0, s.stdout + s.stderr)
        return s.stdout

    def test_missing_telemetry_is_unknown_at_the_worst_case(self):
        r = self.run_agent("reviewer", END)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("settled, unknown 100 UU (1000000 micros).", r.stdout)
        out = self.status()
        self.assertIn("per_day: used 100 UU, reserved 0 UU, left 400 UU", out)
        self.assertIn("Of used: measured 0%, declared 0%, unknown 100%", out)

    def test_huge_numbers_settle_the_full_reservation(self):
        r = self.run_agent("reviewer", send_logs(api_request(cost_micros=10 ** 12 + 1)), WAIT)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("its telemetry report was not valid (a count was not an integer from 0 to 10^12)", r.stdout)
        self.assertIn("per_day: used 100 UU", self.status())

    def test_a_wrong_header_is_refused_and_the_run_stays_unknown(self):
        r = self.run_agent("reviewer", {"do": "otlp", "body": logs(api_request(cost_micros=1)), "header": SECRET},
                           END)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.otlp_statuses(), [401])
        self.assertIn("settled, unknown 100 UU", r.stdout)  # a forged-looking report without the secret: not counted

    def test_an_oversize_body_stops_the_run(self):
        r = self.run_agent("reviewer", {"do": "otlp", "big": 2 << 20}, WAIT)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(self.otlp_statuses(), [413])
        self.assertIn("per_day: used 100 UU", self.status())

    def test_a_rate_change_is_logged_before_it_is_used(self):
        self.units(UNITS_HEAD + "platforms:\n  claude-code:\n    reading: usd_micros\n    fallback: tokens\nmodels:\n"
                   "  claude-sonnet-5:\n    input:" + rate(1000000) + "\n")
        self.run_agent("reviewer", send_metrics(token_points=[token_point(1000)]), END)  # 1000 micros declared
        self.units(UNITS_HEAD + "platforms:\n  claude-code:\n    reading: usd_micros\n    fallback: tokens\nmodels:\n"
                   "  claude-sonnet-5:\n    input:" + rate(5000000) + "\n")
        self.fake_log.unlink()
        r = self.run_agent("reviewer", send_metrics(token_points=[token_point(1000)]), END)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("settled, declared 1 UU (5000 micros).", r.stdout)  # the new rate
        changes = [e.added for e in self.changes()]
        self.assertEqual(len(changes), 2)
        self.assertIn("models.claude-sonnet-5.input 1000000 (", changes[1])
        added = [e.added for e in self.entries()]
        self.assertLess(added.index(changes[1]), len(added) - 4)  # before the reserve, start, end and settle
        self.assertIn("Of used: measured 0%, declared 100%, unknown 0%", self.status())

    def test_a_limit_hit_before_the_start_and_in_the_middle_of_a_run(self):
        self.limits(per_run=10, per_day=15)
        p = self.start_run("reviewer", send_logs(api_request(cost_micros=120000)), {"do": "sleep", "s": 60})
        code, out, _ = self.finish(p)
        self.assertEqual(code, 3, out)
        self.assertIn("it passed its budget of 10 UU for one run (exit 3)", out)
        self.assertIn("per_day: used 12 UU, reserved 0 UU, left 3 UU (limit 15 UU)", self.status())
        before = len(self.started())
        r = self.run_agent("second", END)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("the budget limit per_day has 3 UU left, a run needs 10 UU", r.stdout)
        self.assertEqual(len(self.started()), before)

    def test_the_kill_switch_and_a_logbook_failure_win_over_the_budget(self):
        self.limits(per_day=0)
        self.kill_on()
        r = self.run_agent("reviewer", END)
        self.assertEqual(r.returncode, 3)
        self.assertIn("kill switch", r.stdout)
        self.assertNotIn("budget limit", r.stdout)
        (self.root / ".umwayi" / "KILL").unlink()
        r = self.run_agent("reviewer", END)
        self.assertIn("budget limit per_day", r.stdout)
        self.limits(per_day=500)
        r = self.run_agent("reviewer", END, fault="umwayi.logbook:append:error_after", extra={"UMWAYI_FAULT_AFTER": "0"})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)  # the rules check could not be logged: 2 before any budget
        self.assertEqual(self.started(), [])
        self.assertEqual(self.reserves(), [])

    def test_no_prompt_or_response_text_in_any_output(self):
        r = self.run_agent("reviewer", send_logs(user_prompt_event(), api_request(cost_micros=9)), END,
                           prompt=f"{PROMPT_TEXT} {SECRET}")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("settled, measured 1 UU (9 micros).", r.stdout)  # the report was read, its text was not
        outputs = [r.stdout, r.stderr]
        for args in (("status",), ("calibrate",), ("validate",)):
            b = self.budget(*args)
            self.assertEqual(b.returncode, 0, b.stdout + b.stderr)
            outputs += [b.stdout, b.stderr]
        self.assert_no_planted_text(*outputs)


if __name__ == "__main__":
    unittest.main()
