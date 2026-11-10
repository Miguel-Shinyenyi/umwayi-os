"""Budget governor, task B.10 (umwayi's part): the capture mode for the owner's one real export.

With UMWAYI_TELEMETRY_CAPTURE set to a new absolute path, the receiver also writes the shape of every accepted report
to that file: field, attribute and metric names and the type of every value, never a value. The owner's real capture
is not part of these tests. Every test runs `python -m umwayi agent run ...` as a real child process.
"""

import json
import os
import stat
import unittest

from tests.budget.support import (PROMPT_TEXT, BudgetCase, api_request, cost_point, send_logs, send_metrics,
                                  token_point, user_prompt_event)


class CaptureTests(BudgetCase):
    def test_the_capture_holds_names_and_types_only(self):
        path = self.tmp / "capture.jsonl"
        r = self.run_agent("reviewer", send_logs(user_prompt_event(), api_request(cost_micros=4242, model="claude-zz-9")),
                           send_metrics([cost_point(0.25)], [token_point(777, "cacheRead")]),
                           send_logs(user_prompt_event(), api_request(cost_micros=1)), {"do": "exit", "code": 0},
                           extra={"UMWAYI_TELEMETRY_CAPTURE": str(path)})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(": measured 4243 micros (1 UU);", self.settles()[0].added)  # counting is unchanged
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        text = path.read_text(encoding="utf-8")
        lines = [json.loads(x) for x in text.splitlines()]
        self.assertEqual([x["path"] for x in lines], ["/v1/logs", "/v1/metrics"])  # the same shape once
        for name in ("resourceLogs", "logRecords", "claude_code.api_request", "claude_code.user_prompt", "event.name",
                     "cost_usd_micros", "input_tokens", "cache_creation_tokens", "claude_code.cost.usage",
                     "claude_code.token.usage", "asDouble", "asInt", "dataPoints", "<int>", "<float>", "<string>"):
            self.assertIn(name, text, name)
        for value in (PROMPT_TEXT, "claude-zz-9", "4242", "777", "0.25", "claude-code"):
            self.assertNotIn(value, text, value)

    def test_an_existing_or_relative_capture_file_starts_nothing(self):
        path = self.tmp / "exists.jsonl"
        path.write_text("keep\n", encoding="utf-8")
        for given in (str(path), "relative.jsonl"):
            with self.subTest(given=given):
                r = self.run_agent("reviewer", {"do": "exit", "code": 0}, extra={"UMWAYI_TELEMETRY_CAPTURE": given})
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("the telemetry capture file could not be made", r.stdout)
                self.assertEqual(self.started(), [])
        self.assertEqual(path.read_text(encoding="utf-8"), "keep\n")
        self.assertEqual(self.reserves(), [])


if __name__ == "__main__":
    unittest.main()
