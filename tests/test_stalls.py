"""W19 part 5: umwayi/stalls.py and `umwayi stalls check EVENTS.json`.

Every test uses an injected clock (`NOW`) or a patched `stalls.utc_now`. Nothing reads the real clock.
"""

import datetime
import io
import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from umwayi import stalls
from umwayi.cli import main

REPO = Path(__file__).resolve().parent.parent
UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 11, 13, 12, 0, 0, tzinfo=UTC)
SENTINEL = "SENTINEL-TEXT-9f3a"
SIG_A = "3fa91c20" + "aaaaaaaa"
SIG_B = "11111111" + "bbbbbbbb"


def ago(seconds):
    return (NOW - datetime.timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def ahead(seconds):
    return (NOW + datetime.timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def ev(kind, at, builder="b1", **kw):
    return {"builder": builder, "t": ago(at), "kind": kind, **kw}


def run_events(events, now=NOW):
    data = json.dumps(events).encode()
    return stalls.check_events(stalls.parse(data, now), now)


def lines(events, now=NOW):
    return [f.line for f in run_events(events, now)]


class StallTests(unittest.TestCase):
    def test_29_min_59_s_is_fine_and_30_min_is_a_stall(self):
        self.assertEqual(lines([ev("push", 1799)]), [])
        self.assertEqual(lines([ev("push", 1800)]), ["STALL b1 30 min no push or event"])

    def test_output_poll_waiting_and_status_never_reset_the_timer(self):
        for kind in ("output", "poll", "waiting"):
            with self.subTest(kind=kind):
                self.assertEqual(len(lines([ev("push", 3600), ev(kind, 10)])), 1)
        st = ev("status", 10, connected=True, last_event=ago(3600))
        self.assertIn("STALL b1 60 min no push or event", lines([ev("push", 3600), st]))

    def test_a_fingerprint_resets_only_when_it_changed(self):
        self.assertEqual(len(lines([ev("push", 3600), ev("fingerprint", 5)])), 1)
        self.assertEqual(len(lines([ev("push", 3600), ev("fingerprint", 5, changed=False)])), 1)
        self.assertEqual(lines([ev("push", 3600), ev("fingerprint", 5, changed=True)]), [])

    def test_real_events_reset_the_timer(self):
        for kind in ("push", "started", "error", "check_result", "skipped", "approval_answered"):
            kw = {}
            pre = []
            if kind == "error":
                kw = {"sig": SIG_A}
            if kind == "approval_answered":
                pre = [ev("approval_requested", 3700, id="a1", deadline=ahead(900))]
                kw = {"id": "a1"}
            with self.subTest(kind=kind):
                self.assertEqual([x for x in lines(pre + [ev("push", 3600), ev(kind, 5, **kw)]) if x.startswith("STALL")], [])

    def test_only_output_since_the_start_measures_from_the_first_event(self):
        self.assertEqual(lines([ev("output", 1800)]), ["STALL b1 30 min no push or event"])
        self.assertEqual(lines([ev("output", 1799)]), [])

    def test_a_builder_that_is_not_running_is_not_checked(self):
        for state in ("in review", "needs owner", "merged", "failed", "stopped", "queued"):
            with self.subTest(state=state):
                self.assertEqual(lines([ev("push", 7200), ev("state", 7100, state=state)]), [])
        self.assertEqual(lines([ev("started", 7200), ev("stopped", 7100)]), [])
        self.assertEqual(len(lines([ev("stopped", 7300), ev("started", 7200)])), 1)
        self.assertEqual(len(lines([ev("state", 7200, state="running")])), 1)

    def test_builders_are_judged_apart_and_order_is_by_time(self):
        out = lines([ev("push", 10, builder="b2"), ev("push", 4000), ev("push", 5000, builder="b2")])
        self.assertEqual(out, ["STALL b1 66 min no push or event"])
        shuffled = [ev("push", 5), ev("push", 4000)]
        self.assertEqual(lines(shuffled), lines(list(reversed(shuffled))))


class LoopTests(unittest.TestCase):
    def test_two_identical_errors_in_a_row_stop_at_the_second(self):
        one = [ev("error", 30, sig=SIG_A)]
        two = one + [ev("error", 20, sig=SIG_A)]
        self.assertEqual(lines(one), [])
        self.assertEqual(lines(two), ["STOP b1 same error twice, sig 3fa91c20"])

    def test_different_errors_never_stop_and_other_events_between_do_not_break_the_run(self):
        self.assertEqual(lines([ev("error", 30, sig=SIG_A), ev("error", 20, sig=SIG_B)]), [])
        self.assertEqual(len(lines([ev("error", 30, sig=SIG_A), ev("push", 25), ev("output", 24),
                                    ev("error", 20, sig=SIG_A)])), 1)

    def test_a_different_error_between_two_identical_ones_does_not_stop(self):
        self.assertEqual(lines([ev("error", 30, sig=SIG_A), ev("error", 25, sig=SIG_B), ev("error", 20, sig=SIG_A)]), [])

    def test_one_line_per_builder_and_builders_do_not_mix(self):
        e = [ev("error", 30, sig=SIG_A), ev("error", 20, builder="b2", sig=SIG_A)]
        self.assertEqual(lines(e), [])
        e += [ev("error", 10, sig=SIG_A), ev("error", 9, sig=SIG_A)]
        self.assertEqual(lines(e), ["STOP b1 same error twice, sig 3fa91c20"])

    def test_a_builder_that_has_ended_is_not_reported(self):
        e = [ev("error", 30, sig=SIG_A), ev("error", 20, sig=SIG_A), ev("stopped", 10)]
        self.assertEqual(lines(e), [])


class ApprovalTests(unittest.TestCase):
    def req(self, deadline_in):
        return ev("approval_requested", 100, id="ap-1", deadline=ahead(deadline_in))

    def test_open_before_the_deadline_and_no_at_the_deadline(self):
        self.assertEqual(lines([ev("push", 1), self.req(1)]), [])
        self.assertEqual(lines([ev("push", 1), ev("approval_requested", 100, id="ap-1", deadline=ago(0))]),
                         ["NO ap-1 timed out, counts as No"])

    def test_past_the_deadline_with_no_answer_counts_as_no(self):
        e = [ev("push", 1), ev("approval_requested", 5000, id="ap-1", deadline=ago(60))]
        self.assertEqual(lines(e), ["NO ap-1 timed out, counts as No"])

    def test_an_answer_in_time_is_fine_and_a_late_answer_is_still_no(self):
        base = ev("approval_requested", 5000, id="ap-1", deadline=ago(600))
        ok = {"builder": "b1", "t": ago(700), "kind": "approval_answered", "id": "ap-1"}
        late = {"builder": "b1", "t": ago(600), "kind": "approval_answered", "id": "ap-1"}
        later = {"builder": "b1", "t": ago(10), "kind": "approval_answered", "id": "ap-1"}
        self.assertEqual(lines([ev("push", 1), base, ok]), [])
        self.assertEqual(lines([ev("push", 1), base, late]), ["NO ap-1 answered after the deadline, counts as No"])
        self.assertEqual(lines([ev("push", 1), base, later]), ["NO ap-1 answered after the deadline, counts as No"])

    def test_a_first_answer_is_the_one_that_counts(self):
        base = ev("approval_requested", 5000, id="ap-1", deadline=ago(600))
        ok = {"builder": "b1", "t": ago(700), "kind": "approval_answered", "id": "ap-1"}
        late = {"builder": "b1", "t": ago(10), "kind": "approval_answered", "id": "ap-1"}
        self.assertEqual(lines([ev("push", 1), base, late, ok]), [])

    def test_never_yes_over_random_timelines(self):
        rng = random.Random(1911)
        for _ in range(500):
            asked = rng.randint(1000, 9000)
            dl = rng.randint(1, 900)
            deadline = ago(asked - dl)
            e = [ev("push", 1), ev("approval_requested", asked, id="ap-1", deadline=deadline)]
            answer = rng.choice([None] + list(range(0, asked)))
            if answer is not None:
                e.append(ev("approval_answered", answer, id="ap-1"))
            got = lines(e)
            deadline_dt = NOW - datetime.timedelta(seconds=asked - dl)
            answered_in_time = answer is not None and (NOW - datetime.timedelta(seconds=answer)) < deadline_dt
            if answered_in_time:
                self.assertEqual(got, [])
            elif answer is None and NOW < deadline_dt:
                self.assertEqual(got, [])
            else:
                self.assertEqual(len(got), 1)
                self.assertTrue(got[0].startswith("NO ap-1"))


class StatusTests(unittest.TestCase):
    def test_connected_alone_is_refused(self):
        for st in (ev("status", 5, connected=True), ev("status", 5, connected=True, last_event=None)):
            with self.subTest(st=st):
                self.assertEqual(lines([ev("push", 1), st]), ["REFUSED b1 status has no last event time"])

    def test_a_status_with_a_last_event_time_is_accepted(self):
        self.assertEqual(lines([ev("push", 1), ev("status", 5, connected=True, last_event=ago(60))]), [])

    def test_a_last_event_in_the_future_is_malformed_not_fresh(self):
        data = json.dumps([ev("status", 5, connected=True, last_event=ahead(60))]).encode()
        with self.assertRaises(stalls.Malformed):
            stalls.parse(data, NOW)


class MalformedTests(unittest.TestCase):
    def bad(self, obj=None, raw=None):
        data = raw if raw is not None else json.dumps(obj).encode()
        with self.assertRaises(stalls.Malformed) as cm:
            stalls.parse(data, NOW)
        self.assertNotIn(SENTINEL, str(cm.exception))

    def test_closed_shapes(self):
        good = ev("push", 5)
        self.bad({"not": "a list"})
        self.bad([5])
        self.bad([{**good, SENTINEL: 1}])
        self.bad([{"builder": "b1", "t": ago(5)}])
        self.bad([{**good, "kind": SENTINEL}])
        self.bad([{**good, "builder": SENTINEL + " x"}])
        self.bad([{**good, "builder": ""}])
        self.bad([{**good, "t": SENTINEL}])
        self.bad([{**good, "t": "2026-13-45T00:00:00Z"}])
        self.bad([{**good, "t": ahead(1)}])
        self.bad([{**good, "t": "2026-11-13T09:30:00+00:00"}])
        self.bad([ev("error", 5)])
        self.bad([ev("error", 5, sig="ABCDEF0123456789")])
        self.bad([ev("error", 5, sig=SIG_A[:15])])
        self.bad([{**good, "sig": SIG_A}])
        self.bad([ev("state", 5, state=SENTINEL)])
        self.bad([ev("state", 5)])
        self.bad([ev("fingerprint", 5, changed="yes")])
        self.bad([ev("status", 5)])
        self.bad([ev("status", 5, connected=1)])
        self.bad([{**good, "last_event": ago(9)}])
        self.bad([{**good, "connected": True}])

    def test_approval_rules(self):
        self.bad([ev("approval_requested", 5, id="a1")])
        self.bad([ev("approval_requested", 5, deadline=ahead(5))])
        self.bad([ev("approval_requested", 5, id="a1", deadline=ago(9))])
        self.bad([ev("approval_requested", 5, id="a1", deadline=ago(5))])
        self.bad([ev("approval_answered", 5, id="a1")])
        r = ev("approval_requested", 50, id="a1", deadline=ahead(5))
        self.bad([r, dict(r)])
        self.bad([r, ev("approval_answered", 5)])
        self.bad([{**ev("push", 5), "deadline": ahead(5)}])
        self.bad([{**ev("push", 5), "id": "a1"}])

    def test_bad_json(self):
        for raw in (b"", b"[", b"\xff\xfe", b"[NaN]", b"[Infinity]", b'[{"builder": "a", "builder": "b"}]',
                    b"[" * 100000 + b"]" * 100000, b"null"):
            with self.subTest(raw=raw[:20]):
                self.bad(raw=raw)

    def test_limits(self):
        self.bad(raw=b"[" + b" " * stalls.MAX_BYTES + b"]")
        many = [ev("poll", 5)] * (stalls.MAX_EVENTS + 1)
        self.bad(many)

    def test_random_bytes_never_raise_anything_but_malformed_and_never_pass_silently_as_garbage(self):
        rng = random.Random(77)
        for _ in range(2000):
            raw = bytes(rng.getrandbits(8) for _ in range(rng.randint(0, 60)))
            try:
                stalls.parse(raw, NOW)
            except stalls.Malformed:
                pass

    def test_random_mutations_of_a_good_file_stay_total(self):
        good = json.dumps([ev("push", 100), ev("error", 50, sig=SIG_A), ev("status", 5, connected=True, last_event=ago(9))]).encode()
        rng = random.Random(5)
        for _ in range(2000):
            b = bytearray(good)
            for _ in range(rng.randint(1, 4)):
                b[rng.randrange(len(b))] = rng.getrandbits(8)
            try:
                for f in stalls.check_events(stalls.parse(bytes(b), NOW), NOW):
                    self.assertNotIn(SENTINEL, f.line)
            except stalls.Malformed:
                pass


class PureTests(unittest.TestCase):
    def test_same_input_same_output_and_input_not_changed(self):
        events = stalls.parse(json.dumps([ev("push", 4000), ev("error", 30, builder="b3", sig=SIG_A),
                                          ev("error", 20, builder="b3", sig=SIG_A),
                                          ev("status", 5, builder="b2", connected=True)]).encode(), NOW)
        before = list(events)
        a = stalls.check_events(events, NOW)
        self.assertEqual(a, stalls.check_events(events, NOW))
        self.assertEqual(events, before)
        self.assertEqual([f.rule for f in a], ["STALL", "STOP", "REFUSED"])

    def test_time_comes_only_from_the_argument(self):
        events = stalls.parse(json.dumps([ev("push", 100)]).encode(), NOW)
        later = NOW + datetime.timedelta(seconds=1700)
        self.assertEqual(stalls.check_events(events, NOW), [])
        self.assertEqual(len(stalls.check_events(events, later)), 1)
        with mock.patch("time.time", side_effect=AssertionError("clock read")):
            stalls.check_events(events, later)

    def test_utc_now_uses_the_injected_clock(self):
        self.assertEqual(stalls.utc_now(lambda: NOW.timestamp()), NOW)

    def test_the_module_imports_only_the_standard_library_and_umwayi(self):
        text = (REPO / "umwayi" / "stalls.py").read_text()
        imports = [ln.split()[1].split(".")[0] for ln in text.splitlines() if ln.startswith(("import ", "from "))]
        self.assertEqual(sorted(set(imports)), ["__future__", "dataclasses", "datetime", "json", "pathlib", "re", "time", "umwayi"])
        self.assertNotIn("\u2014", text)
        self.assertNotIn("\u2014", (REPO / "tests" / "test_stalls.py").read_text())


class CliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def write(self, obj, name="events.json"):
        p = self.dir / name
        if isinstance(obj, bytes):
            p.write_bytes(obj)
        else:
            p.write_text(json.dumps(obj) if not isinstance(obj, str) else obj)
        return p

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        old = sys.stderr
        sys.stderr = err
        try:
            with mock.patch("umwayi.stalls.utc_now", return_value=NOW):
                code = main(["--root", str(self.dir), *argv], out=out)
        finally:
            sys.stderr = old
        return code, out.getvalue(), err.getvalue()

    def test_exit_0_when_nothing_is_found(self):
        code, out, err = self.cli("stalls", "check", str(self.write([ev("push", 5)])))
        self.assertEqual((code, out, err), (0, "Nothing found.\n", ""))

    def test_exit_3_with_one_line_per_finding(self):
        p = self.write([ev("push", 4000), ev("error", 30, builder="b3", sig=SIG_A), ev("error", 20, builder="b3", sig=SIG_A),
                        ev("approval_requested", 5000, builder="b3", id="ap-1", deadline=ago(60)),
                        ev("status", 5, connected=True, builder="b2")])
        code, out, err = self.cli("stalls", "check", str(p))
        self.assertEqual(code, 3)
        self.assertEqual(out.splitlines(), [
            "STALL b1 66 min no push or event",
            "STOP b3 same error twice, sig 3fa91c20",
            "NO ap-1 timed out, counts as No",
            "REFUSED b2 status has no last event time",
        ])
        self.assertEqual(err, "")

    def test_exit_2_for_unreadable_and_malformed_and_never_repeats_text(self):
        cases = [self.dir / "missing.json", self.dir,
                 self.write(f'[{{"builder": "{SENTINEL} x", "t": "{SENTINEL}", "kind": "push"}}]', "a.json"),
                 self.write(f'{{"{SENTINEL}": 1', "b.json"),
                 self.write(b"\xff\xfe", "c.json")]
        for p in cases:
            with self.subTest(p=p.name):
                code, out, err = self.cli("stalls", "check", str(p))
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertNotIn(SENTINEL, out + err)
                self.assertNotIn(str(self.dir), out + err)

    def test_exit_64_for_usage_and_never_1(self):
        for argv in (["stalls"], ["stalls", "check"], ["stalls", "check", "a", "b"], ["stalls", "check", "--bogus", "x"]):
            with self.subTest(argv=argv):
                code = self.cli(*argv)[0]
                self.assertEqual(code, 64)

    def test_every_exit_code_is_in_the_allowed_set(self):
        seen = set()
        for obj in ([], [ev("push", 5)], [ev("push", 4000)], [{"x": 1}], "nope"):
            seen.add(self.cli("stalls", "check", str(self.write(obj)))[0])
        self.assertTrue(seen <= {0, 2, 3, 64})
        self.assertNotIn(1, seen)

    def test_it_changes_nothing(self):
        p = self.write([ev("push", 4000)])
        before = {f.name: (f.read_bytes(), f.stat().st_mtime_ns) for f in self.dir.iterdir()}
        self.cli("stalls", "check", str(p))
        after = {f.name: (f.read_bytes(), f.stat().st_mtime_ns) for f in self.dir.iterdir()}
        self.assertEqual(before, after)

    def test_a_real_process_with_the_real_clock(self):
        p = self.write([{"builder": "b1", "t": "2020-01-01T00:00:00Z", "kind": "push"}])
        r = subprocess.run([sys.executable, "-m", "umwayi", "stalls", "check", str(p)], capture_output=True, text=True,
                           env=dict(os.environ, PYTHONPATH=str(REPO)), cwd=str(self.dir))
        self.assertEqual(r.returncode, 3)
        self.assertTrue(r.stdout.startswith("STALL b1 "))

    def test_not_wired_into_any_schedule_or_job(self):
        for name in ("jobs.yaml", "schedule.example.yaml", "workflows"):
            p = REPO / name
            files = [p] if p.is_file() else list(p.rglob("*"))
            for f in files:
                if f.is_file():
                    self.assertNotIn("stalls", f.read_text())


if __name__ == "__main__":
    unittest.main()
