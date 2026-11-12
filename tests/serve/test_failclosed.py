"""The fail closed table of the pipeline (design.md "The pipeline's table", W6.R16.6): one test for each row that can
be reached without a chat. Each one checks the word, the code and the status, and that the files of the root are byte
for byte as they were (the logbook only gains the entries the row names).

Rows not tested here: the three chat rows (a budget refusal of a chat start, a run lock held, an agent that needs a
terminal), the permission and idle rows, and the chat stop on SIGTERM. They belong to the chat routes (W4). "17 requests
at once" and "SIGTERM or Ctrl-C" are real-process tests in test_wire.py.
"""

import io
import json
import threading
import unittest
from contextlib import redirect_stderr
from unittest import mock

from tests.serve.support import (SENTINEL, TOKEN, TOKEN2, InProc, RootCase, logbook_entries, make_logbook, record,
                                 rules_text, servegate, state_files)
from umwayi import logbook
from umwayi.errors import UmwayiError


class FailClosed(RootCase):
    def setUp(self):
        super().setUp()
        make_logbook(self.root)
        self.web = InProc(self.root)
        self.before = state_files(self.root)

    def assertRefused(self, r, status, word, code, changed=False):
        self.assertEqual((r.status, r.word, r.code), (status, word, code), r)
        self.assertFalse(r.ok)
        if not changed:
            self.assertEqual(state_files(self.root), self.before)

    def add(self, title="T"):
        return self.web.post("/v1/queue", {"kind": "task", "title": title})


class GateRows(FailClosed):
    def test_any_gate_check_that_fails_changes_nothing_and_the_summary_counts_it(self):
        for kw in ({"drop": ("Host",), "extra": [("Host", "evil:1")]}, {"token": TOKEN2}, {"token": None},
                   {"extra": [("Expect", "100-continue")]}):
            with self.subTest(kw=kw):
                r = self.web.post("/v1/queue", {"kind": "task", "title": "T"}, **kw)
                self.assertIn(r.status, (401, 403))
                self.assertEqual(state_files(self.root), self.before)
        self.assertEqual(self.web.request("OPTIONS", "/v1/queue").status, 405)
        self.assertEqual(state_files(self.root), self.before)

    def test_a_token_record_that_is_missing_unreadable_malformed_expired_or_revoked(self):
        p = self.root / ".umwayi" / "serve.token"
        good = p.read_text()
        for name, text in (("malformed", "{"), ("expired", json.dumps(record(TOKEN, expires="2026-11-01"))),
                           ("wrong keys", json.dumps({"sha256": "00" * 32}))):
            p.write_text(text)
            before = state_files(self.root)
            r = self.add()
            self.assertEqual((r.status, r.word, r.code), (401, "token", 2), name)
            self.assertEqual(state_files(self.root), before)
        p.unlink()  # revoked
        before = state_files(self.root)
        r = self.add()
        self.assertEqual((r.status, r.word), (401, "token"))
        self.assertEqual(state_files(self.root), before)
        p.write_text(good)

    def test_the_gate_raising_gives_500_error_and_changes_nothing(self):
        with mock.patch.object(servegate.module(), "_run_checks", side_effect=RuntimeError(SENTINEL)):
            r = self.add()
        self.assertRefused(r, 500, "error", 2)
        self.assertNotIn(SENTINEL.encode(), r.raw)


class RulesRows(FailClosed):
    def queue_text(self):
        return (self.root / "queue.md").read_text()

    def test_rules_yaml_missing_or_broken_is_ask_me_first_and_adds_one_queue_decision(self):
        for text in (None, "this: [is not\nrules"):
            (self.root / "queue.md").write_text(self.before["queue.md"].decode())
            if text is None:
                (self.root / "rules.yaml").unlink(missing_ok=True)
            else:
                (self.root / "rules.yaml").write_text(text)
            r = self.add("must not be added")
            self.assertEqual((r.status, r.word, r.code), (403, "ask", 3))
            self.assertNotIn("must not be added", self.queue_text())
            rows = [ln for ln in self.queue_text().splitlines() if "The web page asks first" in ln]
            self.assertEqual(len(rows), 1)
            self.assertIn("queue.add", rows[0])
            self.assertIn("decision", rows[0])
            self.add("again")
            self.assertEqual(len([ln for ln in self.queue_text().splitlines() if "The web page asks first" in ln]), 1)

    def test_a_no_answer_is_word_rules_code_2_and_adds_nothing(self):
        (self.root / "rules.yaml").write_text(rules_text(write="no"))
        before = state_files(self.root)
        r = self.add()
        self.assertEqual((r.status, r.word, r.code), (403, "rules", 2))
        self.assertEqual(state_files(self.root), before)
        sources = [e.source for e in logbook_entries(self.root)]
        self.assertIn("umwayi check", sources)
        self.assertEqual(sources[-1], "umwayi serve")

    def test_ask_me_first_adds_one_queue_decision_the_checks_entry_and_the_request_entry(self):
        (self.root / "rules.yaml").write_text(rules_text(write="ask"))
        r = self.add()
        self.assertEqual((r.status, r.word, r.code), (403, "ask", 3))
        self.assertEqual(len([ln for ln in self.queue_text().splitlines() if "The web page asks first" in ln]), 1)
        self.assertEqual([e.source for e in logbook_entries(self.root)][-3:], ["umwayi check", "umwayi queue add", "umwayi serve"])

    def test_a_yes_that_cannot_be_logged_is_not_given(self):
        real = logbook.append

        def broken(root, entry):
            if entry.source == "umwayi check":
                raise UmwayiError("logbook: planted failure")
            return real(root, entry)

        with mock.patch.object(logbook, "append", broken):
            r = self.add()
        self.assertEqual((r.status, r.word, r.code), (500, "logbook", 2))
        self.assertEqual(state_files(self.root), self.before)

    def test_the_kill_switch_on_or_unknown_stops_a_write_with_word_kill(self):
        for state in ("on", "unknown"):
            with mock.patch("umwayi.kill.state", return_value=state):
                r = self.add()
            self.assertEqual((r.status, r.word, r.code), (403, "kill", 3), state)
            self.assertEqual(state_files(self.root), self.before)
        self.web.post("/v1/kill/on", {})
        self.before = state_files(self.root)
        r = self.add()
        self.assertEqual((r.word, r.code), ("kill", 3))
        self.assertEqual(state_files(self.root), self.before)
        self.assertEqual(self.web.get("/v1/queue").word, "done")  # a read is not stopped
        self.assertEqual(self.web.get("/v1/status").word, "done")
        self.assertEqual(self.web.post("/v1/kill/on", {}).word, "done")  # kill.on is never stopped

    def test_a_date_before_the_newest_logbook_entry_is_a_logbook_refusal(self):
        web = InProc(self.root, today="2026-11-01")
        before = state_files(self.root)
        r = web.post("/v1/queue", {"kind": "task", "title": "T"})
        self.assertEqual((r.status, r.word, r.code), (500, "logbook", 2))
        self.assertEqual(state_files(self.root), before)

    def test_a_logbook_that_fails_its_tamper_check(self):
        with open(self.root / "LOGBOOK.md", "a") as f:
            f.write("\nhand edit\n")
        for r in (self.add(), self.web.get("/v1/snapshot"), self.web.get("/v1/logbook")):
            self.assertEqual((r.status, r.word, r.code), (500, "logbook", 2), r)
        self.assertEqual(state_files(self.root), self.before)
        self.assertEqual(self.web.get("/v1/status").status, 200)

    def test_a_malformed_queue_is_a_refusal_with_code_1(self):
        (self.root / "queue.md").write_text("# Queue\n\nthis is not a table\n| id |\n")
        before = state_files(self.root)
        r = self.web.get("/v1/queue")
        self.assertEqual((r.status, r.word, r.code), (409, "refused", 1))
        self.assertEqual(state_files(self.root), before)


class CommandRows(FailClosed):
    def test_a_usage_error_is_word_usage_code_64(self):
        self.assertRefused(self.add("a|b"), 400, "usage", 64)

    def test_a_body_that_does_not_fit_is_word_body_code_64_and_changes_nothing(self):
        r = self.web.post("/v1/queue", {"kind": "task", "title": "T", "extra": 1})
        self.assertRefused(r, 400, "body", 64)
        r = self.web.post("/v1/queue", raw=b"not json")
        self.assertRefused(r, 400, "body", 64)

    def test_the_body_is_read_only_after_the_gate_allowed_it(self):
        self.web.body_reads.clear()
        self.web.post("/v1/queue", {"kind": "task", "title": "T"}, token=TOKEN2)
        self.web.post("/v1/queue", {"kind": "task", "title": "T"}, origin=False)
        self.web.request("OPTIONS", "/v1/queue")
        self.assertEqual(self.web.body_reads, [])
        self.add()
        self.assertEqual(len(self.web.body_reads), 1)

    def test_a_umwayi_error_is_the_command_codes_1_for_the_queue_and_2_for_agents_and_budget(self):
        for target, path, body, code, word in (
                ("umwayi.taskqueue.close", "/v1/queue/Q-0001/close", {}, 1, "refused"),
                ("umwayi.taskqueue.answer", "/v1/queue/Q-0001/answer", {"answer": "x"}, 1, "refused"),
                ("umwayi.kill.turn_on", "/v1/kill/on", {}, 1, "refused"),
                ("umwayi.agents.check_agent", "/v1/agents/helper/check", {}, 2, "error"),
                ("umwayi.budget.status", "/v1/budget", None, 2, "error")):
            with self.subTest(target=target), mock.patch(target, side_effect=UmwayiError("planted " + SENTINEL)):
                r = self.web.request("GET" if body is None else "POST", path, body)
            self.assertEqual((r.code, r.word), (code, word), target)
            self.assertNotIn(SENTINEL.encode(), r.raw)
            self.assertEqual(state_files(self.root), self.before)

    def test_any_other_exception_is_word_error_code_2_and_only_the_type_name_reaches_stderr(self):
        err = io.StringIO()
        with mock.patch("umwayi.taskqueue.add", side_effect=RuntimeError(SENTINEL)), redirect_stderr(err):
            r = self.add()
        self.assertEqual((r.status, r.word, r.code), (500, "error", 2))
        self.assertNotIn(SENTINEL.encode(), r.raw)
        self.assertNotIn(SENTINEL, err.getvalue())
        self.assertIn("RuntimeError", err.getvalue())

    def test_an_exception_that_is_not_an_exception_subclass_does_not_reach_the_caller(self):
        with mock.patch("umwayi.taskqueue.add", side_effect=KeyboardInterrupt()):
            r = self.add()
        self.assertEqual((r.status, r.word), (500, "error"))


class LimitRows(FailClosed):
    def test_a_write_lock_that_is_not_free_in_time_is_word_busy(self):
        web = InProc(self.root, lock_wait=0.05)
        held = threading.Event()
        release = threading.Event()

        def hold():
            with web.backend.write_lock:
                held.set()
                release.wait(5)

        t = threading.Thread(target=hold, daemon=True)
        t.start()
        self.assertTrue(held.wait(5))
        before = state_files(self.root)
        try:
            r = web.post("/v1/queue", {"kind": "task", "title": "T"})
            self.assertEqual((r.status, r.word, r.code), (503, "busy", 2))
            self.assertEqual(web.get("/v1/queue").word, "done")  # reads do not take the lock
        finally:
            release.set()
            t.join(5)
        self.assertEqual(state_files(self.root), before)

    def test_the_page_file_that_differs_from_build_json_is_word_page(self):
        import hashlib
        page = self.tmp / "dist"
        page.mkdir()
        (page / "index.html").write_bytes(b"<html>page</html>")
        (page / "build.json").write_text(json.dumps({"page": hashlib.sha256(b"<html>page</html>").hexdigest()}))
        web = InProc(self.root, page=page / "index.html")
        r = web.get("/")
        self.assertEqual((r.status, r.raw), (200, b"<html>page</html>"))
        (page / "index.html").write_bytes(b"<html>pagE</html>")
        r = web.get("/")
        self.assertEqual((r.status, r.word, r.code), (503, "page", 2))

    def test_a_stop_entry_that_cannot_be_written_still_stops_and_says_so(self):
        real = logbook.append

        def broken(root, entry):
            if entry.source == "umwayi serve":
                raise UmwayiError("logbook: planted failure")
            return real(root, entry)

        with mock.patch.object(logbook, "append", broken):
            ok = self.web.backend.shutdown("sigterm")
        self.assertFalse(ok)
        ok = self.web.backend.shutdown("sigterm")
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
