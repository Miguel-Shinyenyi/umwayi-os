"""Budget governor, task B.4: reserve, settle, release and the limits (B.R1.6, B.R1.7, B.R1.9).

Each limit refusing in turn (exit 3, one entry, nothing started); the kill switch and a logbook failure winning;
a settle after every way out: the normal end, a refusal after the reservation, the kill switch, the timeout, SIGTERM
and a crash in umwayi. Every test runs `python -m umwayi ...` as a real child process.
"""

import json
import os
import signal
import unittest

from tests.budget.support import BudgetCase, api_request, send_logs

LOOP = {"do": "loop_tools", "tool": "Read", "input": {"file_path": "/etc/hostname"}, "every": 0.2, "for": 60}
END = {"do": "exit", "code": 0}


class LimitTests(BudgetCase):
    def refused(self, name, limit, left):
        before = len(self.started())
        r = self.run_agent(name, END)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        text = f"Refused agent {name}: the budget limit {limit} has {left} UU left, a run needs 100 UU"
        self.assertIn(text + f". Agent {name} was not started. (exit 3)", r.stdout)
        self.assertEqual(len(self.started()), before, "an agent was started")
        self.assertEqual([e.added for e in self.entries()].count(text), 1)
        return r

    def test_per_day_refuses(self):
        self.limits(per_day=150)
        self.assertEqual(self.run_agent("reviewer", END).returncode, 0)  # unknown: 100 UU used
        self.refused("helper", "per_day", 50)
        self.assertEqual(len(self.reserves()), 1)  # a refusal reserves nothing

    def test_per_agent_per_day_refuses_and_another_agent_still_runs(self):
        self.limits(per_agent_per_day=150)
        self.assertEqual(self.run_agent("reviewer", send_logs(api_request(cost_micros=600000))).returncode, 0)
        self.refused("reviewer", "per_agent_per_day", 90)
        self.assertEqual(self.run_agent("second", END).returncode, 0)

    def test_per_platform_per_day_refuses_and_another_platform_still_runs(self):
        self.limits(per_platform_per_day=150)
        self.assertEqual(self.run_agent("reviewer", END).returncode, 0)
        self.refused("second", "per_platform_per_day", 50)
        self.assertEqual(self.run_agent("helper").returncode, 0)

    def test_the_first_limit_that_does_not_fit_is_named(self):
        self.limits(per_day=100, per_agent_per_day=100, per_platform_per_day=100)
        self.assertEqual(self.run_agent("reviewer", send_logs(api_request(cost_micros=10000))).returncode, 0)
        self.refused("reviewer", "per_day", 99)

    def test_a_reservation_that_fits_exactly_starts(self):
        self.limits(per_day=200)
        self.assertEqual(self.run_agent("reviewer", END).returncode, 0)
        self.assertEqual(self.run_agent("second", END).returncode, 0)  # 100 + 100 = 200 fits
        self.refused("helper", "per_day", 0)

    def test_the_kill_switch_wins_over_the_budget(self):
        self.limits(per_day=0)
        self.kill_on()
        r = self.run_agent("reviewer", END)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("Reason: The kill switch is on", r.stdout)
        self.assertNotIn("budget limit", r.stdout)
        self.assertEqual(self.budget_entries(), [])
        self.assertEqual(self.started(), [])

    def test_a_logbook_failure_wins_over_the_budget(self):
        self.limits(per_day=0)
        self.run_agent("reviewer", END)  # refused by the budget, with an entry: the logbook exists now
        with open(self.root / "LOGBOOK.md", "a", encoding="utf-8") as f:
            f.write("edited by hand\n")
        r = self.run_agent("reviewer", END)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn("budget limit", r.stdout)
        self.assertEqual(self.started(), [])


class SettleOnEveryWayOutTests(BudgetCase):
    def assert_settled(self, tag_and_micros):
        [st] = self.settles()
        self.assertIn(f": {tag_and_micros} micros", st.added)
        self.assertEqual(self.budget("settle-lost", "--by", "Owner").stdout.strip(),
                         "No reservation is without a settle. Nothing was written.")
        return st

    def test_normal_end(self):
        self.assertEqual(self.run_agent("reviewer", send_logs(api_request(cost_micros=7))).returncode, 0)
        self.assert_settled("measured 7")

    def test_the_agent_failing(self):
        self.assertEqual(self.run_agent("reviewer", {"do": "exit", "code": 4}).returncode, 2)
        self.assert_settled("unknown 1000000")

    def test_a_refusal_after_the_reservation(self):
        r = self.run_agent("reviewer", END, extra={"FAKE_CLAUDE_GONE_AFTER_AUTH": "1"})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("Agent reviewer could not be started (exit 2).", r.stdout)
        st = self.assert_settled("declared 0")
        self.assertTrue(st.added.endswith("released 1000000 micros"), st.added)
        self.assertIn("the agent never started", st.checked)

    def test_the_start_entry_failing_leaves_the_reservation_counted_in_full(self):
        r = self.run_agent("reviewer", END, extra={"UMWAYI_TEST_BREAK_LOGBOOK_AFTER_RESERVE": "1",
                                                   "UMWAYI_TEST_ROOT": str(self.root)})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("The logbook could not record the start, so nothing is started", r.stdout)
        self.assertIn("could not be logged", r.stdout)
        self.assertIn("its reservation counts in full until umwayi budget settle-lost --by NAME", r.stdout)
        self.assertEqual(self.started(), [])

    def test_the_kill_switch_while_it_runs(self):
        p = self.start_run("reviewer", send_logs(api_request(cost_micros=42)), LOOP)
        self.wait_for(lambda c: c.get("event") == "tool", what="the first tool call", proc=p)
        self.kill_on()
        code, out, _ = self.finish(p)
        self.assertEqual(code, 3, out)
        self.assertIn("The kill switch stopped agent reviewer (exit 3).", out)
        self.assert_settled("measured 42")

    def test_the_timeout(self):
        p = self.start_run("slow", LOOP, extra={"UMWAYI_TEST_MINUTE": "2"})
        code, out, _ = self.finish(p, timeout=90)
        self.assertEqual(code, 2, out)
        self.assertIn("was stopped after its timeout of 1 min", out)
        self.assert_settled("unknown 1000000")

    def test_sigterm_to_umwayi(self):
        p = self.start_run("reviewer", LOOP)
        self.wait_for(lambda c: c.get("event") == "tool", what="the first tool call", proc=p)
        p.send_signal(signal.SIGTERM)
        code, out, _ = self.finish(p)
        self.assertEqual(code, 2, out)
        self.assertIn("Umwayi got SIGTERM, so agent reviewer was stopped (exit 2).", out)
        self.assert_settled("unknown 1000000")

    def test_a_crash_in_umwayi(self):
        p = self.start_run("reviewer", LOOP, fault="umwayi.units:current_micros:crash")
        code, out, err = self.finish(p)
        self.assertEqual(code, 2, out + err)
        self.assertIn("stopped by an unexpected error (RuntimeError)", err)
        self.assertIn("umwayi hit an unexpected error (RuntimeError)", [e.added for e in self.entries()][-2])
        self.assert_settled("unknown 1000000")

    def test_ctrl_c_to_umwayi(self):
        p = self.start_run("reviewer", LOOP)
        self.wait_for(lambda c: c.get("event") == "tool", what="the first tool call", proc=p)
        os.kill(p.pid, signal.SIGINT)
        code, out, _ = self.finish(p)
        self.assertEqual(code, 2, out)
        self.assert_settled("unknown 1000000")


class ReleaseTests(BudgetCase):
    def test_the_rest_is_released_and_left_grows_back(self):
        self.limits(per_day=150)
        self.assertEqual(self.run_agent("reviewer", send_logs(api_request(cost_micros=100))).returncode, 0)
        s = self.budget("status")
        self.assertIn("per_day: used 1 UU, reserved 0 UU, left 149 UU (limit 150 UU)", s.stdout)
        self.assertEqual(self.run_agent("second", END).returncode, 0)  # 1 + 100 fits 150

    def test_the_budget_check_action_has_the_numbers(self):
        self.limits(per_day=450)
        self.write_rules((self.root / "rules.yaml").read_text(encoding="utf-8").replace(
            "agent: [reviewer, second, helper, slow]", "agent: [second, helper, slow]") + """  - id: budget-reviewer
    title: reviewer with exactly these numbers
    text: Allowed.
    verdict: yes
    matchers:
      type: budget_check
      agent: reviewer
      platform: claude-code
      reserve_uu: 100
      left_today_uu: 300
""")
        r = self.run_agent("reviewer", END)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)  # left today: min(450, 300, 400) = 300
        checks = [e for e in self.entries() if e.source == "umwayi check" and "budget_check" in e.added]
        self.assertEqual(len(checks), 1)
        self.assertIn("Rule budget-reviewer gave Yes; action type: budget_check", checks[0].added)
        self.assertNotIn(json.dumps({"type": "budget_check"})[:10], self.log_text())


if __name__ == "__main__":
    unittest.main()
