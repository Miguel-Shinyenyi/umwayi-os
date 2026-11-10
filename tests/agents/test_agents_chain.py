"""Layer 5 addendum, the logbook hash chain (task C.2): a broken chain stops every agent start, and a running
agent, with exit 2, through the existing logbook checks; the kill switch still works.

Real child processes with the fake `claude` (tests/agents/fake_agent.py); HOME is the test's temporary folder.
"""

import hashlib
import subprocess
import sys
import unittest

from tests.agents.test_agents_run import LOOP, READ, RunCase


class BrokenChainStopsAgentsTests(RunCase):
    def seal_chain(self):
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "logbook", "seal", "--chain",
                            "--by", "Owner"], capture_output=True, text=True, env=self.env(), cwd=str(self.tmp))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def break_chain(self):
        """Edit a chained entry and rewrite the whole-file record, so only the chain can find it. Under the logbook
        lock, so a hook of a running agent is not between its append and its record meanwhile."""
        from umwayi import logbook
        log = self.root / "LOGBOOK.md"
        with logbook._lock(self.root):
            text = log.read_text(encoding="utf-8")
            last = text.rindex("- Added: ")
            log.write_text(text[:last] + "- Added: edited " + text[last + len("- Added: "):], encoding="utf-8")
            (self.root / ".umwayi" / "logbook.sha256").write_text(
                hashlib.sha256(log.read_bytes()).hexdigest() + "\n", encoding="ascii")

    def test_a_broken_chain_starts_no_run_and_no_chat(self):
        self.assertEqual(self.run_agent("reviewer", READ).returncode, 0)
        self.seal_chain()
        self.assertEqual(self.run_agent("reviewer", READ).returncode, 0)  # chained entries work
        self.assertIn("- Chain: ", (self.root / "LOGBOOK.md").read_text(encoding="utf-8"))
        self.break_chain()
        self.fake_log.unlink()
        r = self.run_agent("reviewer", READ)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("nothing is started", r.stdout)
        self.assertEqual(self.started(), [])
        r = self.umwayi("chat", "reviewer")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(self.started(), [])
        k = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "kill", "on"],
                           capture_output=True, text=True, env=self.env(), cwd=str(self.tmp))
        self.assertEqual(k.returncode, 0, k.stdout + k.stderr)

    def test_a_chain_broken_while_an_agent_runs_stops_it_with_2(self):
        self.assertEqual(self.run_agent("reviewer", READ).returncode, 0)
        self.seal_chain()
        p = self.start_run("reviewer", LOOP)
        self.first_tool(p)
        self.break_chain()
        code, out, _ = self.finish(p)
        self.assertEqual(code, 2, out)
        self.assertIn("The logbook can no longer be written", out)
        self.assertIn("the hash chain is broken", out)
        self.assert_agent_gone()


if __name__ == "__main__":
    unittest.main()
