"""Budget governor, tasks B.6 and B.7: the telemetry receiver and the telemetry environment (B.R2).

The fake `claude` is the fake sender: it posts to the receiver of its run with the header, path, type and length
a test plants. Every test runs `python -m umwayi agent run|chat ...` as a real child process.
"""

import shutil
import socket
import subprocess
import sys
import unittest

from umwayi.telemetry import TELEMETRY_NAMES

from tests.agents.test_agents_claude_acp_chat import ClaudeChatCase
from tests.budget.support import (PROMPT_TEXT, SECRET, BudgetCase, api_request, cost_point, logs, send_logs,
                                  send_metrics, token_point, user_prompt_event)

END = {"do": "exit", "code": 0}
WAIT = {"do": "sleep", "s": 20}
FIXED = {"CLAUDE_CODE_ENABLE_TELEMETRY": "1", "OTEL_METRICS_EXPORTER": "otlp", "OTEL_LOGS_EXPORTER": "otlp",
         "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json", "OTEL_METRIC_EXPORT_INTERVAL": "5000",
         "OTEL_LOGS_EXPORT_INTERVAL": "5000", "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE": "delta",
         "OTEL_LOG_USER_PROMPTS": "0", "OTEL_LOG_ASSISTANT_RESPONSES": "0", "OTEL_LOG_TOOL_DETAILS": "0",
         "OTEL_LOG_RAW_API_BODIES": "0", "OTEL_TRACES_EXPORTER": "none"}
OWNER_TELEMETRY = {"OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": "https://collector.example.invalid/" + SECRET,
                   "OTEL_EXPORTER_OTLP_ENDPOINT": "https://collector.example.invalid",
                   "OTEL_EXPORTER_OTLP_HEADERS": "authorization=" + SECRET, "OTEL_LOG_USER_PROMPTS": "1",
                   "OTEL_RESOURCE_ATTRIBUTES": "team=x", "BETA_TRACING_ENDPOINT": "https://trace.example.invalid",
                   "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1", "CLAUDE_CODE_ENABLE_TELEMETRY": "0"}


def assert_env_is_ours(test, otel: dict):
    test.assertEqual(set(otel), set(TELEMETRY_NAMES))
    for k, v in FIXED.items():
        test.assertEqual(otel[k], v, k)
    test.assertRegex(otel["OTEL_EXPORTER_OTLP_ENDPOINT"], r"^http://127\.0\.0\.1:[0-9]{2,5}$")
    test.assertRegex(otel["OTEL_EXPORTER_OTLP_HEADERS"], r"^x-umwayi-run=[0-9a-f]{32}$")


def other_address():
    """A non-loopback address of this machine, or None."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 9))  # no packet is sent for a UDP connect
        addr = s.getsockname()[0]
        s.close()
        return None if addr.startswith("127.") else addr
    except OSError:
        return None


class ReceiverTests(BudgetCase):
    def settled(self):
        [s] = self.settles()
        return s

    def test_each_rejection_is_answered_counted_and_never_read(self):
        good = logs(api_request(cost_micros=777))
        r = self.run_agent("reviewer",
                           {"do": "otlp", "body": good, "header": "0" * 32},  # a wrong run header
                           {"do": "otlp", "body": good, "header": None},  # no header
                           {"do": "otlp", "body": good, "path": "/v1/traces"},
                           {"do": "otlp", "body": good, "path": "/v1/logs/../metrics"},
                           {"do": "otlp", "body": good, "method": "GET"},
                           {"do": "otlp", "body": good},  # the one that counts
                           END)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.otlp_statuses(), [401, 401, 404, 404, 404, 200])
        st = self.settled()
        self.assertIn(": measured 777 micros (1 UU);", st.added)  # the refused bodies were not counted
        self.assertIn("reports accepted 1, refused 5 (2 answered 401, 3 answered 404)", st.checked)

    def test_a_report_without_a_length_is_411_and_the_run_is_invalid(self):
        r = self.run_agent("reviewer", {"do": "otlp", "body": logs(api_request()), "length": None}, WAIT)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(self.otlp_statuses(), [411])
        self.assertIn("Agent reviewer was stopped: its telemetry report was not valid (a report came without a "
                      "Content-Length), so its run is settled at the full reservation (exit 2).", r.stdout)
        self.assertIn(": unknown 1000000 micros (100 UU);", self.settled().added)

    def test_an_oversize_body_is_413(self):
        r = self.run_agent("reviewer", {"do": "otlp", "big": 1 << 20}, WAIT)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(self.otlp_statuses(), [413])
        self.assertIn("(a report was larger than 1 MB)", r.stdout)
        self.assertIn(": unknown 1000000 micros (100 UU);", self.settled().added)

    def test_too_many_bodies_are_413(self):
        r = self.run_agent("reviewer", {"do": "otlp", "big": (1 << 20) - 100, "repeat": 17}, WAIT)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(self.otlp_statuses(), [200] * 16 + [413])
        self.assertIn("(the reports of the run were larger than 16 MB in all)", r.stdout)

    def test_not_json_is_refused(self):
        for step, code, why in (({"do": "otlp", "raw": "{\"resourceLogs\": [", "content_type": "application/json"}, 400,
                                 "a report was not JSON"),
                                ({"do": "otlp", "body": logs(), "content_type": "application/x-protobuf"}, 415,
                                 "a report was not plain JSON"),
                                ({"do": "otlp", "body": {"resourceLogs": {"not": "a list"}}}, 400,
                                 "a report did not have the OTLP JSON shape")):
            with self.subTest(why=why):
                self.roomy_budget()
                self.fake_log.unlink(missing_ok=True)
                r = self.run_agent("reviewer", step, END)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertEqual(self.otlp_statuses(), [code])
                self.assertIn(f"The telemetry of agent reviewer was not valid ({why})", r.stdout)

    def test_huge_negative_float_and_string_numbers_make_the_run_invalid(self):
        cases = {
            "huge": api_request(cost_micros=10 ** 12 + 1),
            "negative": api_request(cost_micros=-1),
            "float": api_request(raw_cost={"doubleValue": 1.5}),
            "string": api_request(raw_cost={"stringValue": "100"}),
            "string as int": api_request(raw_cost={"intValue": "100"}),
            "token string": api_request(input_tokens="5"),
            "bool": api_request(raw_cost={"intValue": True}),
        }
        self.roomy_budget()
        for label, record in cases.items():
            with self.subTest(case=label):
                self.fake_log.unlink(missing_ok=True)
                n = len(self.settles())
                r = self.run_agent("reviewer", send_logs(record), WAIT)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("Agent reviewer was stopped: its telemetry report was not valid (", r.stdout)
                self.assertEqual(self.otlp_statuses(), [400])
                st = self.settles()[n]
                self.assertIn(": unknown 1000000 micros (100 UU);", st.added)  # the full reservation
        for label, step in (("metric huge", send_metrics([cost_point(10.0 ** 7)])),
                            ("metric negative", send_metrics([cost_point(-0.5)])),
                            ("metric string", send_metrics([cost_point("0.5")])),
                            ("tokens float", send_metrics(token_points=[dict(token_point(1), asInt=1.0)]))):
            with self.subTest(case=label):
                self.fake_log.unlink(missing_ok=True)
                r = self.run_agent("reviewer", step, WAIT)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_every_negative_whole_number_cost_makes_the_run_invalid(self):
        # Review of PR 33: a negative whole number must never subtract from a run, on any path. Each case is answered
        # 400, the run is invalid (exit 2) and settled at the full reservation, like a negative float.
        self.limits(per_run=1000, per_day=100000, per_agent_per_day=100000, per_platform_per_day=100000)
        full = ": unknown 10000000 micros (1000 UU);"  # per_run 1000 UU, never less

        def point(**value):
            return dict({"attributes": [{"key": "model", "value": {"stringValue": "claude-sonnet-5"}}],
                         "timeUnixNano": "1"}, **value)

        def cost_usd(value):
            return api_request(cost_micros=None, extra=[{"key": "cost_usd", "value": value}])

        cases = {
            "metrics asDouble -3 (a whole number)": [send_metrics([point(asDouble=-3)])],
            "metrics asInt -3": [send_metrics([point(asInt=-3)])],
            "events cost_usd intValue -5": [send_logs(cost_usd({"intValue": -5}))],
            "events cost_usd doubleValue -5 (a whole number)": [send_logs(cost_usd({"doubleValue": -5}))],
            "events cost_usd_micros intValue -5": [send_logs(api_request(raw_cost={"intValue": -5}))],
        }
        def fresh():
            """Each case on its own logbook: a negative settle would make the ledger malformed and refuse every
            later start (exit 2 before the agent), which would hide the next case."""
            self.fake_log.unlink(missing_ok=True)
            (self.root / "LOGBOOK.md").unlink(missing_ok=True)
            shutil.rmtree(self.root / ".umwayi", ignore_errors=True)

        def next_start_works():
            self.fake_log.unlink(missing_ok=True)
            r = self.run_agent("reviewer", END)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)  # the settle above kept the ledger well formed

        for label, steps in cases.items():
            with self.subTest(case=label):
                fresh()
                n = len(self.settles())
                r = self.run_agent("reviewer", *steps, WAIT)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertEqual(self.otlp_statuses(), [400])
                self.assertIn("Agent reviewer was stopped: its telemetry report was not valid (", r.stdout)
                self.assertIn(full, self.settles()[n].added)
                next_start_works()
        # +2 then -1 dollars must not end as 1 dollar: in one body, and in two reports where the first one counted
        for label, steps, statuses in (
                ("one body", [send_metrics([point(asDouble=2), point(asDouble=-1)])], [400]),
                ("two reports", [send_metrics([point(asDouble=2)]), send_metrics([point(asDouble=-1)])], [200, 400]),
                ("two event reports", [send_logs(cost_usd({"intValue": 2})), send_logs(cost_usd({"intValue": -1}))],
                 [200, 400])):
            with self.subTest(case="+2 then -1, " + label):
                fresh()
                n = len(self.settles())
                r = self.run_agent("reviewer", *steps, WAIT)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertEqual(self.otlp_statuses(), statuses)
                st = self.settles()[n].added
                self.assertIn(full, st)
                self.assertNotIn("1000000 micros (100 UU)", st)
                next_start_works()

    def test_a_body_with_prompt_text_is_never_kept_or_printed(self):
        r = self.run_agent("reviewer", send_logs(user_prompt_event(), api_request(cost_micros=50)),
                           send_metrics([cost_point(0.5)], [token_point(9)]), END, prompt=PROMPT_TEXT)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(": measured 50 micros (1 UU);", self.settled().added)  # the events count, one request
        self.assertIn("; requests 1;", self.settled().added)
        self.assert_no_planted_text(r.stdout, r.stderr)

    def test_the_receiver_listens_on_loopback_only(self):
        addr = other_address()
        if addr is None:
            self.skipTest("this machine has no address other than loopback")
        r = self.run_agent("reviewer", {"do": "otlp", "body": logs(api_request()), "host": addr}, END)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        [c] = [c for c in self.calls() if c.get("event") == "otlp"]
        self.assertIsNone(c["status"])  # the connection was refused: nothing listens there
        self.assertIn(": unknown 1000000 micros (100 UU);", self.settled().added)

    def test_a_report_sent_right_before_the_agent_exits_is_counted(self):
        r = self.run_agent("reviewer", send_logs(api_request(cost_micros=31)), END)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(": measured 31 micros (1 UU);", self.settled().added)


class EnvironmentTests(BudgetCase):
    def test_a_run_gets_exactly_these_names_and_never_the_owners(self):
        r = self.run_agent("reviewer", END, extra=OWNER_TELEMETRY)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        [start] = self.started()
        assert_env_is_ours(self, start["otel"])
        self.assertNotIn("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", start["env_keys"])
        self.assertNotIn("BETA_TRACING_ENDPOINT", start["env_keys"])
        self.assertNotIn("CLAUDE_CODE_ENHANCED_TELEMETRY_BETA", start["env_keys"])
        self.assertNotIn("OTEL_RESOURCE_ATTRIBUTES", start["env_keys"])
        for c in self.calls():  # nor the version check or the login check: they get no telemetry at all
            if not c.get("started") and "env_keys" in c:
                self.assertFalse([k for k in c["env_keys"] if k.startswith("OTEL_") or "TELEMETRY" in k], c["argv"])
        secret = start["otel"]["OTEL_EXPORTER_OTLP_HEADERS"].split("=", 1)[1]
        self.assertNotIn(secret, r.stdout + r.stderr + self.log_text())
        self.assert_no_planted_text(r.stdout, r.stderr)

    def test_every_run_has_its_own_port_and_secret(self):
        self.run_agent("reviewer", END)
        self.run_agent("second", END)
        a, b = self.started()
        self.assertNotEqual(a["otel"]["OTEL_EXPORTER_OTLP_HEADERS"], b["otel"]["OTEL_EXPORTER_OTLP_HEADERS"])

    def test_a_cli_chat_gets_them_and_is_settled(self):
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "chat", "reviewer"],
                           input="hello\n/quit\n", capture_output=True, text=True, timeout=120,
                           env=self.env(dict(self.script(send_logs(api_request(cost_micros=64))), **OWNER_TELEMETRY)),
                           cwd=str(self.tmp))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        [start] = self.started()
        self.assertTrue(start["chat"])
        assert_env_is_ours(self, start["otel"])
        [st] = self.settles()
        self.assertIn(": measured 64 micros (1 UU);", st.added)

    def test_kiro_gets_no_telemetry_names_from_umwayi(self):
        r = self.run_agent("helper")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        [start] = self.started()
        self.assertEqual(start["otel"], {})


class MidRunCapTests(BudgetCase):
    def test_the_cap_passed_in_the_middle_of_a_run_stops_it_with_3_and_settles_the_overrun(self):
        self.limits(per_run=10)
        p = self.start_run("reviewer", send_logs(api_request(cost_micros=150000)), {"do": "sleep", "s": 60})
        code, out, _ = self.finish(p, timeout=60)
        self.assertEqual(code, 3, out)
        self.assertIn("Agent reviewer was stopped: it passed its budget of 10 UU for one run (exit 3).", out)
        self.assertEqual(self.alive_at_exit, [])
        [st] = self.settles()
        self.assertIn(": measured 150000 micros (15 UU);", st.added)
        self.assertTrue(st.added.endswith("released 0 micros"), st.added)
        self.assertIn("Agent reviewer was stopped: it passed its budget of 10 UU for one run",
                      [e.added for e in self.entries()])

    def test_under_the_cap_it_runs_on(self):
        self.limits(per_run=10)
        r = self.run_agent("reviewer", send_logs(api_request(cost_micros=100000)), {"do": "sleep", "s": 2}, END)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)  # exactly the cap is not past it

    def test_the_metric_counts_mid_run_when_no_event_came(self):
        self.limits(per_run=10)
        r = self.run_agent("reviewer", send_metrics([cost_point(0.2)]), {"do": "sleep", "s": 30})
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)


class AcpChatTests(ClaudeChatCase):
    def test_an_acp_chat_gets_them_counts_a_report_and_is_settled(self):
        self.spec({"turns": [[{"otlp": {"body": logs(api_request(cost_micros=88))}}, {"chunk": "done"}]]})
        r = self.chat("go\n:quit\n", extra=OWNER_TELEMETRY)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        [started] = [c for c in self.calls() if c.get("prog") == "claude-acp" and c.get("started")]
        assert_env_is_ours(self, started["otel"])
        statuses = [c.get("status") for c in self.calls() if c.get("event") == "otlp"]
        self.assertEqual(statuses, [200])
        settles = [e for e in self.entries() if e.source == "umwayi budget" and e.added.startswith("Settled run ")]
        self.assertEqual(len(settles), 1)
        self.assertIn(": measured 88 micros (1 UU);", settles[0].added)
        for c in self.node_calls():  # the gate check programs get no telemetry names
            if c["probe"] != "chat":
                self.assertFalse([k for k in c["env"] if k.startswith("OTEL_") or "TELEMETRY" in k], c["probe"])

    def test_the_cap_stops_an_acp_chat_mid_turn_with_3(self):
        (self.root / "units.yaml").write_text("version: 1\nlimits:\n  per_run: 1\n", encoding="utf-8")
        self.spec({"turns": [[{"otlp": {"body": logs(api_request(cost_micros=20000))}}, {"sleep": 30}]]})
        r = self.chat("go\n")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("it passed its budget of 1 UU for one run", r.stdout)
        self.assert_agent_gone()


if __name__ == "__main__":
    unittest.main()
