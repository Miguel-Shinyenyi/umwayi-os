"""W9.4 / W9.R10 (pitfall 2): a stalled or looping builder. `signature`, `judge`, the policy, and a guard that the
module reads no clock, file or process.

Tests first. The module under test is umwayi/goalwatch.py (pure). The tests that start a real fake builder and stop its
process group belong to the supervisor (W9.7) and are not here.
"""

import ast
import hashlib
import unittest
from pathlib import Path

from tests.goal import gen
from umwayi import goalwatch as gw

REPO = Path(__file__).resolve().parents[2]
A, B = "a" * 16, "b" * 16
BUILDER = gw.Policy.for_role("builder")
TESTER = gw.Policy.for_role("tester")


class SignatureTests(unittest.TestCase):
    BASE = "Error: file '/tmp/a1/b.txt' not found at line 12, id 3fa91c20b1"

    def test_non_errors_have_no_signature(self):
        for text in ("", "   ", "ok done", "info: error in the middle", "cannot", "all good", "Errors are fine", "the Error: x",
                     "done: failed", "\t\n"):
            if text.strip().lower().startswith(("error", "errors")):
                continue
            self.assertIsNone(gw.signature(text), repr(text))

    def test_each_marker_gives_a_signature(self):
        for text in ("error: x", "ERROR boom", "Fatal: out of memory", "Traceback (most recent call last):", "Exception in thread",
                     "FAILED tests/x.py", "panic: runtime error", "npm ERR! code ENOENT", "cannot open the file",
                     "No such file or directory", "  \t error: indented"):
            s = gw.signature(text)
            self.assertIsNotNone(s, text)
            self.assertRegex(s, r"^[0-9a-f]{16}$")

    def test_the_normalization_is_pinned(self):
        want = hashlib.sha256(b"error: file P not found at line #, id H").hexdigest()[:16]
        self.assertEqual(gw.signature(self.BASE), want)

    def test_twelve_rewrites_keep_the_signature(self):
        base = gw.signature(self.BASE)
        rewrites = [
            "Error: file '/tmp/a1/b.txt' not found at line 99, id 3fa91c20b1",
            "Error: file '/tmp/a1/b.txt' not found at line 123456789, id 3fa91c20b1",
            "Error: file '/tmp/a1/b.txt' not found at line 12, id 9e8d7c6b5a4f",
            "Error: file '/var/other/c.py' not found at line 12, id 3fa91c20b1",
            'Error: file "C:\\Users\\me\\x.txt" not found at line 12, id 3fa91c20b1',
            "error: file '/tmp/a1/b.txt' not found at line 12, id 3fa91c20b1",
            "ERROR: FILE '/TMP/A1/B.TXT' NOT FOUND AT LINE 12, ID 3FA91C20B1",
            "   Error:   file  '/tmp/a1/b.txt'  not   found at line 12,   id 3fa91c20b1   ",
            "Error:\tfile '/tmp/a1/b.txt' not\tfound at line 12, id 3fa91c20b1",
            "Error: file 'x' not found at line 12, id 3fa91c20b1",
            "Error: file '' not found at line 12, id 3fa91c20b1",
            "Error: file '/tmp/a1/b.txt' not found at line 12, id 0123456789abcdef",
        ]
        self.assertEqual(len(rewrites), 12)
        for r in rewrites:
            self.assertEqual(gw.signature(r), base, r)

    def test_text_after_200_normalized_characters_is_ignored(self):
        head = "error: " + "word " * 40
        self.assertEqual(gw.signature(head + "tail one"), gw.signature(head + "a different tail"))

    def test_twelve_different_messages_differ(self):
        msgs = ["Error: disk full", "Error: permission denied", "Error: connection refused", "Fatal: out of memory",
                "Traceback (most recent call last):", "Exception: value is wrong", "FAILED: test_alpha", "panic: nil pointer",
                "npm ERR! missing script", "cannot find module alpha", "No such file or directory", "Error: syntax error near token"]
        sigs = {gw.signature(m) for m in msgs}
        self.assertEqual(len(sigs), 12)

    def test_a_word_made_of_hex_letters_is_not_masked(self):
        self.assertNotEqual(gw.signature("error: decade passed"), gw.signature("error: facade passed"))

    def test_signature_is_total(self):
        gen.run_property(self, lambda g: g.text(gen.PRINTABLE + "'\"\\\n\u00e9", 0, 80),
                         lambda s: gw.signature(s) is None or len(gw.signature(s)) == 16, cases=1500, seeds=gen.SEEDS)
        for bad in (None, 5, b"error", ["error"], 1.5):
            self.assertIsNone(gw.signature(bad))


def hist(*events):
    return list(events)


class JudgeTests(unittest.TestCase):
    def test_policy_values(self):
        self.assertEqual((BUILDER.stall_s, BUILDER.repeat, BUILDER.output_is_progress), (1800, 2, False))
        self.assertEqual((TESTER.stall_s, TESTER.repeat, TESTER.output_is_progress), (1800, 2, True))
        self.assertTrue(gw.Policy.for_role("guide").output_is_progress)
        self.assertTrue(gw.Policy.for_role("check").output_is_progress)

    def test_1799_continues_and_1800_stops_for_every_offset_and_mix_of_output(self):
        def make(g):
            start = g.between(0, 5000)
            outs = sorted(start + g.between(0, 1799) for _ in range(g.between(0, 12)))
            return start, outs

        def check(case):
            start, outs = case
            h = [("start", start)] + [("output", t) for t in outs]
            a = gw.judge(h, start + 1799, BUILDER)
            b = gw.judge(h, start + 1800, BUILDER)
            return a is gw.CONTINUE and isinstance(b, gw.Stop) and b.reason == "stalled"

        gen.run_property(self, make, check, cases=1250, seeds=gen.SEEDS)

    def test_output_without_a_change_never_resets_the_stall_timer_of_a_builder(self):
        h = [("start", 0)] + [("output", t) for t in range(0, 1800, 10)]
        self.assertEqual(gw.judge(h, 1800, BUILDER), gw.Stop("stalled"))
        self.assertIs(gw.judge(h, 1800, TESTER), gw.CONTINUE)  # for a tester, output is progress
        self.assertEqual(gw.judge(h, 1800 + 1800, TESTER), gw.Stop("stalled"))

    def test_a_progress_event_moves_the_timer(self):
        h = [("start", 0), ("progress", 1000)]
        self.assertIs(gw.judge(h, 2799, BUILDER), gw.CONTINUE)
        self.assertEqual(gw.judge(h, 2800, BUILDER), gw.Stop("stalled"))

    def test_a_builder_that_changes_a_file_every_25_seconds_is_not_stalled(self):
        h = [("start", 0)] + [("progress", t) for t in range(25, 20000, 25)]
        self.assertIs(gw.judge(h, 20000, BUILDER), gw.CONTINUE)

    def test_a_gap_that_was_once_long_stays_a_stop(self):
        h = [("start", 0), ("progress", 4000)]
        self.assertEqual(gw.judge(h, 4001, BUILDER), gw.Stop("stalled"))

    def test_two_identical_errors_in_a_row_stop_at_the_second(self):
        self.assertIs(gw.judge([("start", 0), ("error", 5, A)], 6, BUILDER), gw.CONTINUE)
        self.assertEqual(gw.judge([("start", 0), ("error", 5, A), ("error", 9, A)], 10, BUILDER), gw.Stop("looping"))
        self.assertIs(gw.judge([("start", 0), ("error", 5, A), ("error", 9, B)], 10, BUILDER), gw.CONTINUE)

    def test_a_different_error_between_two_identical_ones_does_not_stop(self):
        h = [("start", 0), ("error", 1, A), ("error", 2, B), ("error", 3, A)]
        self.assertIs(gw.judge(h, 4, BUILDER), gw.CONTINUE)

    def test_output_and_edits_between_identical_errors_do_not_break_the_run(self):
        h = [("start", 0), ("error", 1, A), ("output", 2), ("progress", 3), ("output", 4), ("error", 5, A)]
        self.assertEqual(gw.judge(h, 6, BUILDER), gw.Stop("looping"))

    def test_events_arrive_in_any_order_in_the_list(self):
        h = [("error", 9, A), ("start", 0), ("error", 5, A)]
        self.assertEqual(gw.judge(h, 10, BUILDER), gw.Stop("looping"))

    def test_events_in_the_future_of_now_are_not_yet_happened(self):
        h = [("start", 0), ("error", 5, A), ("error", 50, A)]
        self.assertIs(gw.judge(h, 10, BUILDER), gw.CONTINUE)

    def test_judge_is_total_over_garbage_histories(self):
        junk = [None, 5, "x", (), ("start",), ("error", "t", A), ("error", 1, 5), ("output", None), ("what", 3, 4),
                ("start", float("nan")), ("progress", float("inf")), ("error", -1, A), (1, 2, 3), {"a": 1}, [], b"x",
                ("start", True), ("error", 1, "z" * 1000)]

        def make(g):
            h = [g.pick(junk) if g.chance(0.5) else (g.pick(["start", "progress", "output", "error"]), g.between(-10, 4000),
                                                      g.pick([A, B, "x", 3, None])) for _ in range(g.between(0, 15))]
            return h, g.pick([0, 5, 1799, 1800, 99999, -3, float("nan"), "x", None, 2.5])

        def check(case):
            h, now = case
            r = gw.judge(h, now, BUILDER)
            return r is gw.CONTINUE or isinstance(r, gw.Stop)

        gen.run_property(self, make, check, cases=1250, seeds=gen.SEEDS, shrinkable=False)
        for bad_history in (None, 5, "x", object()):
            self.assertIn(type(gw.judge(bad_history, 10, BUILDER)), (type(gw.CONTINUE), gw.Stop))
        self.assertIn(type(gw.judge([], 10, None)), (type(gw.CONTINUE), gw.Stop))

    def test_once_stop_always_stop_for_a_later_now_and_a_longer_history(self):
        def make(g):
            h = [("start", 0)]
            for _ in range(g.between(0, 10)):
                kind = g.pick(["progress", "output", "error"])
                h.append((kind, g.between(0, 4000)) if kind != "error" else (kind, g.between(0, 4000), g.pick([A, B])))
            return h, g.between(0, 4500), g.between(0, 600)

        def check(case):
            h, now, more = case
            if gw.judge(h, now, BUILDER) is gw.CONTINUE:
                return True
            later = gw.judge(h, now + more, BUILDER)
            extended = gw.judge(h + [("progress", now + more), ("output", now + more)], now + more, BUILDER)
            return isinstance(later, gw.Stop) and isinstance(extended, gw.Stop)

        gen.run_property(self, make, check, cases=1250, seeds=gen.SEEDS)


class PlantedFaultTests(unittest.TestCase):
    """Each planted fault of W9.R10.7 is caught by a contract that the real code passes."""

    def contract(self, judge, signature=gw.signature):
        pol = gw.Policy.for_role("builder")
        # the stall is timed from progress, and from nothing else
        self.assertIs(judge([("start", 0)], 1799, pol), gw.CONTINUE)
        self.assertEqual(judge([("start", 0)], 1800, pol), gw.Stop("stalled"))
        noisy = [("start", 0)] + [("output", t) for t in range(0, 1800, 10)]
        self.assertEqual(judge(noisy, 1800, pol), gw.Stop("stalled"))
        # two identical errors stop, three are too many
        self.assertEqual(judge([("start", 0), ("error", 1, A), ("error", 2, A)], 3, pol), gw.Stop("looping"))
        self.assertIs(judge([("start", 0), ("error", 1, A)], 3, pol), gw.CONTINUE)
        # signatures ignore numbers
        self.assertEqual(signature("Error: line 12 failed"), signature("Error: line 99 failed"))

    def test_the_contract_passes_on_the_real_judge(self):
        self.contract(gw.judge)

    def stall_from_output(self, h, now, pol):
        last = max([t for k, t, *_ in h if k in ("start", "progress", "output")] or [0])
        return gw.Stop("stalled") if now - last >= pol.stall_s else gw.CONTINUE

    def test_fault_stall_timed_from_output(self):
        with self.assertRaises(AssertionError):
            self.contract(lambda h, now, pol: self.stall_from_output(h, now, pol) if not any(
                e[0] == "error" for e in h) else gw.judge(h, now, pol))

    def test_fault_3600_instead_of_1800(self):
        with self.assertRaises(AssertionError):
            self.contract(lambda h, now, pol: gw.judge(h, now, gw.Policy(stall_s=3600, repeat=pol.repeat,
                                                                          output_is_progress=pol.output_is_progress)))

    def test_fault_three_errors_instead_of_two(self):
        with self.assertRaises(AssertionError):
            self.contract(lambda h, now, pol: gw.judge(h, now, gw.Policy(stall_s=pol.stall_s, repeat=3,
                                                                          output_is_progress=pol.output_is_progress)))

    def test_fault_signatures_keep_digits(self):
        def digits_kept(line):
            return hashlib.sha256(line.lower().encode()).hexdigest()[:16]

        with self.assertRaises(AssertionError):
            self.contract(gw.judge, signature=digits_kept)

    def test_fault_judge_reads_the_real_clock(self):
        import time

        def reads_clock(h, now, pol):
            return gw.judge(h, time.time(), pol)

        with self.assertRaises(AssertionError):
            self.contract(reads_clock)


class PureModuleGuard(unittest.TestCase):
    """W9.R10.6 and the W9.4 acceptance test: the module reads no clock, file or process."""

    def test_no_clock_file_or_process(self):
        src = (REPO / "umwayi" / "goalwatch.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        names = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                names |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                names.add((n.module or "").split(".")[0])
        names.discard("__future__")
        self.assertLessEqual(names, {"re", "hashlib", "dataclasses", "math"})
        called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        for forbidden in ("open", "exec", "eval", "__import__", "input", "print"):
            self.assertNotIn(forbidden, called)
        used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        for forbidden in ("time", "os", "sys", "subprocess", "datetime", "pathlib", "random", "socket"):
            self.assertNotIn(forbidden, used)


if __name__ == "__main__":
    unittest.main()
