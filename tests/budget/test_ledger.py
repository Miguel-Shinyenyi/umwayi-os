"""Budget governor, task B.3: the ledger in the logbook (B-Q1, B-Q4).

The reserve, settle and change entries in their fixed shapes, chained (the hash chain is started with
`umwayi logbook seal --chain` first, as the owner does once); budget.py reads them back; a malformed `umwayi budget`
entry stops every start; a reservation without a settle counts in full until `umwayi budget settle-lost`.
Every test runs `python -m umwayi ...` as a real child process.
"""

import json
import os
import re
import signal
import unittest

from tests.budget.support import BudgetCase, api_request, send_logs

LOOP = {"do": "loop_tools", "tool": "Read", "input": {"file_path": "/etc/hostname"}, "every": 0.2, "for": 60}


class LedgerCase(BudgetCase):
    def start_chain(self):
        r = self.u("check", json.dumps({"type": "read_memory"}))
        self.assertIn(r.returncode, (0, 3), r.stdout + r.stderr)
        r = self.u("logbook", "seal", "--chain", "--by", "Owner")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def verify(self):
        return self.u("logbook", "verify")


class RoundTripTests(LedgerCase):
    def test_reserve_and_settle_are_chained_and_read_back_by_status(self):
        self.start_chain()
        r = self.run_agent("reviewer", send_logs(api_request(cost_micros=123456)))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        [res], [st] = self.reserves(), self.settles()
        m = re.match(r"^Reserved run ([0-9a-f]{16}) for agent reviewer \(claude-code\): 1000000 micros \(100 UU\)$",
                     res.added)
        self.assertTrue(m, res.added)
        self.assertTrue(st.added.startswith(f"Settled run {m.group(1)} for agent reviewer (claude-code): measured "
                                            "123456 micros (13 UU); "), st.added)
        self.assertTrue(st.added.endswith("; requests 1; released 876544 micros"), st.added)
        text = self.log_text()
        for e in (res, st):  # each is followed by its Chain line
            i = text.index(e.added)
            self.assertTrue(text[i:].split("\n", 4)[3].startswith("- Chain: "), "a budget entry is not chained")
        v = self.verify()
        self.assertEqual(v.returncode, 0, v.stdout)
        s = self.budget("status")
        self.assertEqual(s.returncode, 0, s.stdout + s.stderr)
        self.assertIn("per_day: used 13 UU, reserved 0 UU, left 487 UU (limit 500 UU)", s.stdout)
        self.assertIn("per_agent_per_day reviewer: used 13 UU, reserved 0 UU, left 287 UU", s.stdout)
        self.assertIn("Of used: measured 100%, declared 0%, unknown 0%", s.stdout)

    def test_the_reserve_entry_comes_before_the_start_entry(self):
        self.run_agent("reviewer", {"do": "exit", "code": 0})
        added = [e.added for e in self.entries()]
        res = next(i for i, a in enumerate(added) if a.startswith("Reserved run "))
        start = next(i for i, a in enumerate(added) if a.startswith("Started agent reviewer"))
        settle = next(i for i, a in enumerate(added) if a.startswith("Settled run "))
        end = next(i for i, a in enumerate(added) if a.startswith("Agent reviewer exited"))
        self.assertLess(res, start)
        self.assertLess(end, settle)  # settled after the agent ended and was stopped


class HandEditTests(LedgerCase):
    def test_a_hand_edited_budget_entry_breaks_the_chain_and_stops_starts(self):
        self.start_chain()
        self.run_agent("reviewer", send_logs(api_request(cost_micros=500000)))
        text = self.log_text()
        edited = text.replace("measured 500000 micros (50 UU)", "measured 5 micros (1 UU)")
        self.assertNotEqual(edited, text)
        (self.root / "LOGBOOK.md").write_text(edited, encoding="utf-8")
        self.assertEqual(self.verify().returncode, 1)
        self.fake_log.unlink()
        r = self.run_agent("reviewer", {"do": "exit", "code": 0})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(self.started(), [])
        self.assertEqual(self.budget("status").returncode, 2)

    def test_a_malformed_budget_entry_with_the_chain_rewritten_still_stops_starts(self):
        self.start_chain()
        self.run_agent("reviewer", send_logs(api_request(cost_micros=500000)))
        text = self.log_text()
        # a consistent chain and record, but the settle no longer has its fixed shape: released does not match
        edited = text.replace("released 500000 micros", "released 999999 micros")
        self.assertNotEqual(edited, text)
        self.rewrite_logbook(edited)
        v = self.verify()
        self.assertEqual(v.returncode, 0, v.stdout)  # the logbook itself verifies: only the shape check finds it
        self.fake_log.unlink()
        r = self.run_agent("reviewer", {"do": "exit", "code": 0})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("is not the one settle of an earlier reservation", r.stdout)
        self.assertNotIn("released 999999", r.stdout + r.stderr)  # never the entry's text
        self.assertEqual(self.started(), [])
        s = self.budget("status")
        self.assertEqual(s.returncode, 2, s.stdout + s.stderr)
        for planted in ("Settled run 0123456789abcdef for agent x (y): spent nothing",
                        "Reserved run nothex for agent reviewer (claude-code): 1 micros (1 UU)"):
            with self.subTest(planted=planted):
                self.rewrite_logbook(text.replace(text.split("- Added: ")[-1].split("\n")[0], planted))
                self.assertEqual(self.verify().returncode, 0)
                self.assertEqual(self.budget("status").returncode, 2)
                self.assertEqual(self.run_agent("reviewer").returncode, 2)


class LostSettleTests(LedgerCase):
    def test_a_reservation_without_a_settle_counts_in_full_until_settle_lost(self):
        p = self.start_run("reviewer", LOOP)
        self.wait_for(lambda c: c.get("event") == "tool", what="the first tool call", proc=p)
        os.kill(p.pid, signal.SIGKILL)  # umwayi itself: no settle can be written
        p.wait(timeout=30)
        for pid in self.agent_pids_alive():
            os.killpg(pid, signal.SIGKILL)
        self.wait_root_quiet()
        self.assertEqual(len(self.reserves()), 1)
        self.assertEqual(self.settles(), [])
        s = self.budget("status")
        self.assertIn("per_day: used 0 UU, reserved 100 UU, left 400 UU", s.stdout)
        self.assertIn("1 reservation(s) of this day have no settle and count in full", s.stdout)
        self.limits(per_agent_per_day=150)
        r = self.run_agent("reviewer", {"do": "exit", "code": 0})
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)  # the lost reservation still counts
        self.assertIn("the budget limit per_agent_per_day has 50 UU left, a run needs 100 UU", r.stdout)
        r = self.budget("settle-lost", "--by", "Owner")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("1 lost reservation(s) settled.", r.stdout)
        [st] = self.settles()
        self.assertIn(": unknown 1000000 micros (100 UU); models none;", st.added)
        self.assertIn("settled by Owner with umwayi budget settle-lost", st.checked)
        s = self.budget("status")
        self.assertIn("per_day: used 100 UU, reserved 0 UU, left 400 UU", s.stdout)
        self.assertNotIn("have no settle", s.stdout)
        r = self.budget("settle-lost", "--by", "Owner")
        self.assertIn("No reservation is without a settle. Nothing was written.", r.stdout)

    def test_settle_lost_waits_for_a_running_agent(self):
        p = self.start_run("reviewer", LOOP)
        self.wait_for(lambda c: c.get("event") == "tool", what="the first tool call", proc=p)
        r = self.budget("settle-lost", "--by", "Owner")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("holds the run lock", r.stdout)
        p.terminate()
        self.finish(p)
        self.assertEqual(len(self.settles()), 1)  # the run settled itself on SIGTERM
        self.assertEqual(self.budget("settle-lost", "--by", "").returncode, 64)


if __name__ == "__main__":
    unittest.main()
