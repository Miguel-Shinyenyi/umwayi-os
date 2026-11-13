"""Tests that close the gaps the first mutation pass of W6.10 found (tests/serve/mutation.py). Each test names the planted fault
that survived without it: G19 (the query value shape), T2 (the limit on the days of a token), S18 (the request id)."""

import re
import tempfile
import unittest
from pathlib import Path

from tests.serve import gen
from tests.serve.support import DATE, TOKEN, InProc, make_root, servegate, servetoken
from umwayi.errors import UsageError


class QueryValueShape(unittest.TestCase):
    """G19: a value in the query of queue.list is lower case letters, digits, - and _, at most 16 characters. The gate
    refuses anything else with the word `target`, so the core function never sees it."""

    def verdict(self, query):
        req = gen.good("queue.list")
        req.target = "/v1/queue" + query
        v, _state = servegate.decide(req.facts(), req.state())
        return v

    def test_good_values_pass(self):
        for query in ("", "?status=open", "?status=open&kind=task", "?kind=decision", "?status=", "?status=a-b_c9",
                      "?status=" + "a" * 16):
            with self.subTest(query=query):
                self.assertIsInstance(self.verdict(query), servegate.Allow)

    def test_a_value_of_another_shape_is_refused_with_the_word_target(self):
        for query in ("?status=OPEN", "?status=" + "a" * 17, "?status=o.p", "?status=a*", "?status=a=b", "?status==x",
                      "?kind=task?x", "?status=a,b", "?status=a+b", "?status=o'p", "?status=<x>", "?status=a|b",
                      "?status=\u00e9", "?status=a&status=b", "?status", "?&", "?status=open&", "?status=open&&kind=task"):
            with self.subTest(query=query):
                v = self.verdict(query)
                self.assertIsInstance(v, servegate.Refuse)
                self.assertEqual((v.status, v.word), (403, "target"))


    def test_a_bad_value_that_the_target_check_lets_through_is_refused_after_the_token(self):
        for query in ("?status=OPEN", "?status=" + "a" * 17, "?status=o.p", "?status=a*"):
            with self.subTest(query=query):
                v = self.verdict(query)
                self.assertEqual((v.word, v.authed, v.route), ("target", True, "queue.list"))


class DaysOfAToken(unittest.TestCase):
    """T2: `servetoken` itself limits the days to 1 to 90 (the command line also checks, but a caller of the module must
    not be able to write a record that `read_record` would refuse, which would leave a token that never works)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = make_root(Path(self._tmp.name), token=None)

    def test_days_outside_one_to_ninety_are_a_usage_error_and_write_nothing(self):
        for days in (0, -1, 91, 1000, 10 ** 9, True, False, "5", None, 30.0):
            for call in (servetoken.create, servetoken.rotate):
                with self.subTest(days=days, call=call.__name__):
                    with self.assertRaises(UsageError):
                        call(self.root, days, DATE, True)
                    self.assertFalse((self.root / ".umwayi" / "serve.token").exists())

    def test_one_and_ninety_are_allowed_and_the_record_can_be_read_back(self):
        for days in (1, 90):
            (self.root / ".umwayi" / "serve.token").unlink(missing_ok=True)
            r = servetoken.create(self.root, days, DATE, True)
            self.assertEqual(r.code, 0)
            rec = servetoken.read_record(self.root)
            self.assertIsNotNone(rec, "a record that create wrote must be one that read_record accepts")
            self.assertEqual(servetoken.days_left(rec, DATE), days)


class RequestIds(unittest.TestCase):
    """S18: every answered request has its own id of the form R-xxxxxxxx, and the id in the response is the one in the logbook."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = make_root(Path(self._tmp.name))
        self.web = InProc(self.root)

    def test_ids_are_distinct_and_have_the_shape(self):
        ids = []
        for _ in range(40):
            r = self.web.get("/v1/queue")
            self.assertEqual((r.status, r.word), (200, "done"))
            ids.append(r.env["request"])
        for rid in ids:
            self.assertRegex(rid, r"^R-[0-9a-f]{8}$")
        self.assertEqual(len(set(ids)), len(ids), "two requests got the same id")

    def test_the_id_of_the_response_is_the_id_of_its_entry(self):
        from tests.serve.support import logbook_entries
        r = self.web.get("/v1/queue")
        entries = [e for e in logbook_entries(self.root) if e.source == "umwayi serve" and e.added.startswith("Request ")]
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0].added.startswith("Request " + r.env["request"] + ":"), entries[0].added)


if __name__ == "__main__":
    unittest.main()
