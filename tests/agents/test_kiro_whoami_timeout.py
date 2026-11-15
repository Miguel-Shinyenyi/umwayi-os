"""W59: the Kiro login check waits 30 s for `kiro-cli whoami`, and no answer is called no answer.

On a Mac `kiro-cli whoami` takes about 10 s. Here the fake `kiro-cli` sleeps: 12 s still passes the check (`umwayi agent
check`, a real child process); a whoami that never answers is still a refusal (exit 2, fail closed) and its line says the
sign-in could not be confirmed, never that the owner is not signed in. No real Kiro.
"""

import time
import unittest

from umwayi import agents

from tests.agents.support import AgentCase

AGENTS = """agents:
  - name: helper
    platform: kiro
    command: kiro-cli
    workdir: {work}
"""


class WhoamiTimeoutTests(AgentCase):
    def setUp(self):
        super().setUp()
        self.fake("kiro-cli")
        self.write_rules()
        self.write_agents(AGENTS)

    def login_line(self, r):
        return next(l for l in self.lines(r) if ": login: " in l)

    def test_the_limit_is_30_s_and_the_claude_check_keeps_15_s(self):
        self.assertEqual(agents.KIRO_WHOAMI_TIMEOUT, 30.0)
        self.assertEqual(agents.SIGNIN_TIMEOUT, 15.0)

    def test_a_whoami_that_answers_after_12_s_passes(self):
        t = time.monotonic()
        r = self.umwayi("check", "helper", extra={"FAKE_KIRO_WHOAMI_SLEEP": "12"}, timeout=90)
        self.assertGreaterEqual(time.monotonic() - t, 12)
        self.assertEqual(self.login_line(r), "ok: login: Kiro is signed in (kiro-cli whoami exited 0)")

    def test_a_whoami_that_never_answers_is_refused_with_no_answer_not_signed_out(self):
        t = time.monotonic()
        r = self.umwayi("check", "helper", extra={"FAKE_KIRO_WHOAMI_HANG": "1"}, timeout=90)
        took = time.monotonic() - t
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertGreaterEqual(took, 29)
        self.assertLess(took, 59)
        self.assertEqual(self.login_line(r), "no: login: the Kiro sign-in could not be confirmed (kiro-cli whoami gave no "
                                             "answer within 30 s). Sign in to Kiro first (kiro-cli login), then try again.")
        self.assertNotIn("not signed in", r.stdout)
        self.assertEqual([c for c in self.calls() if c.get("started")], [])

    def test_a_whoami_that_exits_1_is_still_not_signed_in(self):
        r = self.umwayi("check", "helper", extra={"FAKE_KIRO_WHOAMI_EXIT": "1"})
        self.assertEqual(r.returncode, 2)
        self.assertIn("no: login: Kiro is not signed in (kiro-cli whoami exited 1).", r.stdout)


if __name__ == "__main__":
    unittest.main()
