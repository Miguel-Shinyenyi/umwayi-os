"""The logbook entries of `umwayi serve` (W6.R13, W6.R16.5). In process (the backend without a socket)."""

import json
import re
import unittest
from unittest import mock

from tests.serve.support import (SENTINEL, TOKEN, TOKEN2, TOKEN_ID, InProc, RootCase, logbook_entries, make_logbook,
                                 rules_text, servegate)
from umwayi import logbook
from umwayi.errors import UmwayiError

ADDED = re.compile(r"^Request R-[0-9a-f]{8}: (GET|POST|DELETE) ([a-z]+\.[a-z]+|no route), "
                   r"(done|refused \([a-z]+\)) \(exit (0|1|2|3|64)\), \d+ ms$")
CHECKED = re.compile(r"^Token T-[0-9a-f]{8} valid\. (Host and Origin exact|The gate refused the request)\. "
                     r"Kill switch (off|on|unknown|not read)\. Rules check (Yes|No|Ask me first|skipped|not run)\.$")
NOT_DONE = re.compile(r"^The body, the headers and the token were not recorded\.( The command was not run\.)?$")
SUMMARY = re.compile(r"^Refused (\d+) requests? before a token was checked or after the rate limit, in the last 60 "
                     r"seconds: ((?:[a-z]+ \d+)(?:, [a-z]+ \d+)*)\.$")


def serve_entries(root):
    return [e for e in logbook_entries(root) if e.source == "umwayi serve"]


class EntryBase(RootCase):
    def setUp(self):
        super().setUp()
        make_logbook(self.root)
        self.web = InProc(self.root)

    def last(self):
        return serve_entries(self.root)[-1]


class ShapeTests(EntryBase):
    def check_shape(self, e, route, outcome, kill, rules, command_ran=True):
        self.assertRegex(e.added, ADDED)
        self.assertRegex(e.checked, CHECKED)
        self.assertRegex(e.not_done, NOT_DONE)
        self.assertEqual(e.source, "umwayi serve")
        self.assertIn(f" {route}, {outcome} (", e.added)
        self.assertIn(f"Kill switch {kill}. Rules check {rules}.", e.checked)
        self.assertEqual("The command was not run." in e.not_done, not command_ran)

    def test_a_read_that_passed(self):
        r = self.web.get("/v1/queue")
        self.assertEqual((r.status, r.word), (200, "done"))
        e = self.last()
        self.assertEqual(e.checked, f"Token {TOKEN_ID} valid. Host and Origin exact. Kill switch off. Rules check Yes.")
        self.assertEqual(e.not_done, "The body, the headers and the token were not recorded.")
        self.assertRegex(e.added, r"^Request R-[0-9a-f]{8}: GET queue\.list, done \(exit 0\), \d+ ms$")
        self.assertIn(r.env["request"], e.added)

    def test_a_write_that_the_rules_turn_into_ask_me_first(self):
        (self.root / "rules.yaml").write_text(rules_text(write=None))
        r = self.web.post("/v1/queue", {"kind": "task", "title": "T"})
        self.assertEqual((r.status, r.word, r.code), (403, "ask", 3))
        self.check_shape(self.last(), "queue.add", "refused (ask)", "off", "Ask me first", command_ran=False)
        self.assertIn("(exit 3)", self.last().added)

    def test_a_write_that_the_rules_say_no_to(self):
        (self.root / "rules.yaml").write_text(rules_text(write="no"))
        r = self.web.post("/v1/queue", {"kind": "task", "title": "T"})
        self.assertEqual((r.word, r.code), ("rules", 2))
        self.check_shape(self.last(), "queue.add", "refused (rules)", "off", "No", command_ran=False)

    def test_a_write_while_the_kill_switch_is_on(self):
        self.assertEqual(self.web.post("/v1/kill/on", {}).word, "done")
        r = self.web.post("/v1/queue", {"kind": "task", "title": "T"})
        self.assertEqual((r.word, r.code), ("kill", 3))
        self.check_shape(self.last(), "queue.add", "refused (kill)", "on", "No", command_ran=False)

    def test_kill_on_skips_the_rules_check_and_says_so(self):
        (self.root / "rules.yaml").write_text(rules_text(read=None, write="no", run=None))
        r = self.web.post("/v1/kill/on", {})
        self.assertEqual((r.word, r.code), ("done", 0))
        e = self.last()
        self.assertRegex(e.checked, r"Rules check skipped\.$")
        self.assertRegex(e.added, r"POST kill\.on, done \(exit 0\)")

    def test_a_command_that_refuses_for_usage(self):
        r = self.web.post("/v1/queue", {"kind": "task", "title": "a|b"})
        self.assertEqual((r.status, r.word, r.code), (400, "usage", 64))
        self.check_shape(self.last(), "queue.add", "refused (usage)", "off", "Yes")

    def test_a_body_that_does_not_fit_is_refused_before_the_kill_switch_is_read(self):
        r = self.web.post("/v1/queue", {"nonsense": 1})
        self.assertEqual((r.status, r.word, r.code), (400, "body", 64))
        e = self.last()
        self.assertIn("Kill switch not read. Rules check not run.", e.checked)
        self.assertRegex(e.checked, CHECKED)

    def test_a_refusal_by_the_gate_after_the_token_is_logged_with_its_word(self):
        r = self.web.post("/v1/queue/Q-0001/close", {}, origin=False)
        self.assertEqual(r.word, "origin")
        e = self.last()
        self.assertRegex(e.added, r"POST no route, refused \(origin\) \(exit 2\)")
        self.assertRegex(e.checked, CHECKED)
        self.assertIn("The gate refused the request.", e.checked)
        r = self.web.post("/v1/queue/Q-0001/close", {}, drop=("Content-Length",))
        self.assertEqual(r.word, "length")
        self.assertRegex(self.last().added, r"POST queue\.close, refused \(length\) \(exit 2\)")

    def test_the_response_of_a_gate_refusal_is_the_fixed_one_and_names_no_request(self):
        r = self.web.post("/v1/queue/Q-0001/close", {}, origin=False)
        self.assertEqual(r.raw, servegate.refusal_body("origin"))
        self.assertEqual((r.env["request"], r.env["logged"]), (None, False))

    def test_one_entry_for_each_authenticated_request_and_none_for_the_others(self):
        before = len(serve_entries(self.root))
        self.web.get("/v1/queue")
        self.web.get("/v1/status")
        self.web.post("/v1/queue", {"kind": "task", "title": "T"})
        self.web.get("/v1/queue", token=TOKEN2)  # wrong token
        self.web.get("/v1/queue", drop=("Host",), extra=[("Host", "evil:1")])  # a Host that is not ours
        self.web.request("OPTIONS", "/v1/queue")
        self.web.get("/")  # the page: no token, no entry
        after = serve_entries(self.root)
        self.assertEqual(len(after) - before, 3)

    def test_the_rules_check_of_a_request_names_no_body_and_no_id(self):
        self.web.post("/v1/queue", {"kind": "task", "title": SENTINEL})
        checks = [e for e in logbook_entries(self.root) if e.source == "umwayi check"]
        self.assertTrue(checks)
        for e in checks:
            self.assertNotIn(SENTINEL, json.dumps(e.__dict__))
        self.assertIn("action type: serve_request", checks[-1].added)


class SummaryTests(EntryBase):
    def flood(self):
        for _ in range(30):
            self.web.get("/v1/queue", drop=("Host",), extra=[("Host", "evil:1")])
        for _ in range(4):
            self.web.get("/v1/queue", token=TOKEN2)
        for _ in range(2):
            self.web.request("OPTIONS", "/v1/queue")

    def test_a_summary_entry_counts_words_and_names_no_request(self):
        before = len(serve_entries(self.root))
        self.flood()
        self.assertEqual(len(serve_entries(self.root)), before)  # nothing yet: less than 60 seconds
        self.web.clock.t += 61
        self.web.get("/v1/status")
        entries = serve_entries(self.root)
        summary = [e for e in entries if e.added.startswith("Refused ")]
        self.assertEqual(len(summary), 1)
        m = SUMMARY.match(summary[0].added)
        self.assertTrue(m, summary[0].added)
        self.assertEqual(m.group(1), "36")
        self.assertEqual(m.group(2), "host 30, token 4, method 2")
        self.assertEqual(summary[0].checked, "The count is from memory since the last summary. No request is named.")
        self.assertEqual(summary[0].not_done, "No address, header or body was recorded.")

    def test_at_most_one_summary_in_60_seconds_and_none_when_the_count_is_zero(self):
        self.flood()
        self.web.clock.t += 61
        self.web.get("/v1/status")
        n = len([e for e in serve_entries(self.root) if e.added.startswith("Refused ")])
        self.web.get("/v1/queue", drop=("Host",), extra=[("Host", "evil:1")])
        self.web.get("/v1/status")
        self.assertEqual(len([e for e in serve_entries(self.root) if e.added.startswith("Refused ")]), n)
        self.web.clock.t += 61
        self.web.get("/v1/status")  # 61 seconds later, one more refusal waiting
        self.assertEqual(len([e for e in serve_entries(self.root) if e.added.startswith("Refused ")]), n + 1)
        self.web.clock.t += 61
        self.web.get("/v1/status")  # nothing counted since: no entry
        self.assertEqual(len([e for e in serve_entries(self.root) if e.added.startswith("Refused ")]), n + 1)

    def test_a_summary_is_written_once_more_at_shutdown(self):
        self.web.get("/v1/queue", drop=("Host",), extra=[("Host", "evil:1")])
        self.web.backend.flush_summary(force=True)
        s = [e for e in serve_entries(self.root) if e.added.startswith("Refused ")]
        self.assertEqual(len(s), 1)
        self.assertRegex(s[0].added, r"^Refused 1 requests? .*: host 1\.$")

    def test_the_counts_are_kept_when_the_summary_cannot_be_written(self):
        self.web.get("/v1/queue", drop=("Host",), extra=[("Host", "evil:1")])
        real = logbook.append

        def broken(root, entry):
            if entry.source == "umwayi serve":
                raise UmwayiError("logbook: planted")
            return real(root, entry)

        with mock.patch.object(logbook, "append", broken):
            self.web.backend.flush_summary(force=True)
        self.web.backend.flush_summary(force=True)
        s = [e for e in serve_entries(self.root) if e.added.startswith("Refused ")]
        self.assertEqual(len(s), 1)
        self.assertRegex(s[0].added, r": host 1\.$")

    def test_the_rate_limit_is_counted_not_logged_one_by_one(self):
        before = len(serve_entries(self.root))
        self.web.tick = 0.0
        for _ in range(40):
            self.web.get("/v1/queue")  # the bucket of all authenticated requests: burst 30
        self.assertLess(len(serve_entries(self.root)) - before, 31)
        self.web.backend.flush_summary(force=True)
        s = [e for e in serve_entries(self.root) if e.added.startswith("Refused ")]
        self.assertEqual(len(s), 1)
        self.assertRegex(s[0].added, r"rate \d+")


class SecretTests(EntryBase):
    def test_no_body_header_target_token_or_text_reaches_an_entry_or_a_response(self):
        replies = [
            self.web.post("/v1/queue", {"kind": "task", "title": SENTINEL + "-title"}),
            self.web.get("/v1/status", extra=[("X-Sentinel", SENTINEL + "-header")]),
            self.web.get("/v1/queue?zz=" + SENTINEL, extra=[]),
            self.web.get("/v1/queue", token="umt1_" + SENTINEL.replace("-", "_")[:43].ljust(43, "A")),
            self.web.get("/v1/status", extra=[("User-Agent", SENTINEL + "-agent")]),
            self.web.post("/v1/queue/Q-0001/answer", {"answer": SENTINEL + "-answer"}),
            self.web.post("/v1/queue", raw=b'{"kind":"task","title":"' + SENTINEL.encode() + b'\x00"}'),
            self.web.get("/v1/queue", drop=("Host",), extra=[("Host", SENTINEL + ":1")]),
            self.web.get("/v1/nothing/" + SENTINEL.upper()),
        ]
        self.web.backend.flush_summary(force=True)
        seen = "".join(json.dumps(e.__dict__) for e in serve_entries(self.root))
        for needle in (SENTINEL, SENTINEL.replace("-", "_")[:30], TOKEN, TOKEN2, TOKEN[5:20]):
            self.assertNotIn(needle, seen)
            for r in replies:
                self.assertNotIn(needle.encode(), r.raw)
        for r in replies:
            self.assertNotIn(b"Traceback", r.raw)
            self.assertNotIn(str(self.root).encode(), r.raw)

    def test_the_token_digest_and_the_token_are_in_no_entry(self):
        self.web.get("/v1/status")
        dump = (self.root / "LOGBOOK.md").read_text()
        self.assertNotIn(TOKEN, dump)
        from tests.serve.support import digest
        self.assertNotIn(digest(TOKEN), dump)


class DegradedTests(EntryBase):
    def failing(self):
        real = logbook.append

        def broken(root, entry):
            if entry.source == "umwayi serve":
                raise UmwayiError("logbook: planted failure")
            return real(root, entry)

        return mock.patch.object(logbook, "append", broken)

    def test_a_command_that_changed_something_and_could_not_be_logged(self):
        with self.failing():
            r = self.web.post("/v1/queue", {"kind": "task", "title": "T"})
        self.assertEqual((r.status, r.word, r.code, r.env["logged"]), (500, "logbook", 2, False))
        self.assertEqual(r.env["data"], {"changed": True})
        self.assertIn("Q-0001", (self.root / "queue.md").read_text())  # the command's own entry is the record
        self.assertTrue(any("Q-0001" in e.added for e in logbook_entries(self.root) if e.source.startswith("umwayi queue")))

    def test_after_a_failed_entry_the_server_refuses_everything_but_three_routes(self):
        with self.failing():
            self.web.post("/v1/queue", {"kind": "task", "title": "T"})
            r = self.web.get("/v1/queue")
            self.assertEqual((r.status, r.word), (500, "logbook"))
            self.assertEqual(r.env["data"] if r.env.get("data") else None, None)
            r = self.web.get("/v1/status")
            self.assertEqual((r.status, r.word, r.env["logged"]), (200, "done", False))
            self.assertTrue(r.data["degraded"])
            r = self.web.get("/")
            self.assertNotEqual(r.word, "logbook")  # the page answers (503 page when none is built, never `logbook`)
            r = self.web.post("/v1/kill/on", {})
            self.assertTrue((self.root / ".umwayi" / "KILL").exists())  # the switch is made first and logged second
            self.assertEqual(r.word, "logbook")

    def test_the_state_ends_when_the_logbook_can_be_written_again_and_one_entry_says_so(self):
        with self.failing():
            self.web.post("/v1/queue", {"kind": "task", "title": "T"})
            self.assertEqual(self.web.get("/v1/queue").word, "logbook")
        r = self.web.get("/v1/queue")
        self.assertEqual((r.status, r.word), (200, "done"))
        ended = [e for e in serve_entries(self.root) if "degraded" in e.added]
        self.assertEqual(len(ended), 1)
        self.assertFalse(self.web.get("/v1/status").data["degraded"])

    def test_a_logbook_that_fails_its_tamper_check_gives_the_degraded_state(self):
        with open(self.root / "LOGBOOK.md", "a") as f:
            f.write("\nhand edit\n")
        r = self.web.get("/v1/queue")
        self.assertEqual((r.word, r.code), ("logbook", 2))
        self.assertFalse(r.env["logged"])
        self.assertEqual(self.web.get("/v1/status").status, 200)


class VolumeTests(EntryBase):
    def test_the_logbook_verifies_after_500_requests_50_refusals_of_each_kind_and_a_restart(self):
        web = self.web
        for i in range(500):
            if i % 5 == 0:
                web.post("/v1/queue", {"kind": "task", "title": f"T{i}"})
            elif i % 5 == 1:
                web.get("/v1/status")
            else:
                web.get("/v1/queue")
        for _ in range(50):
            web.get("/v1/queue", drop=("Host",), extra=[("Host", "evil:1")])  # host: counted
            web.request("OPTIONS", "/v1/queue")  # method: counted
            web.post("/v1/queue", {"kind": "task", "title": "x"}, origin=False)  # origin, after the token: logged
            web.get("/v1/nothing")  # route, after the token: logged
            web.get("/v1/queue?zz=1")  # target, after the token: logged
        for i in range(50):
            if i % 4 == 0:
                web.clock.t += 61
            web.get("/v1/queue", token=TOKEN2)  # token: counted (never five in a minute)
        web.backend.flush_summary(force=True)
        web = InProc(self.root)  # a restart
        web.get("/v1/queue")
        report = logbook.verify(self.root)
        self.assertEqual(report.problems, [], [p.render() for p in report.problems])
        logbook.read_checked_chain(self.root)  # raises when the chain is broken


if __name__ == "__main__":
    unittest.main()
