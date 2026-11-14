"""W9.3 / W9.R12 (pitfall 4): one malformed log line must not stall the log.

Tests first. The module under test is umwayi/goallog.py: the event shape, the total reader, the writer and the
bounded line reader. The logbook is not one of these logs and still fails closed (last test).
"""

import errno
import hashlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.goal.fakeroot import DATE
from tests.goal import gen
from umwayi import goallog
from umwayi.errors import UmwayiError

AT = "2026-11-13T10:15:30Z"


def line(n, kind="output", data=None, at=AT):
    data = {"lines": 1, "bytes": 10, "skipped": 0} if data is None and kind == "output" else (data or {})
    return goallog.make_line(n, at, kind, data)


def good_log(count=6):
    lines = [line(i) for i in range(1, count + 1)]
    return lines


def with_bad(lines, pos, bad):
    return b"".join(lines[:pos]) + bad + b"".join(lines[pos:])


def raw(obj, newline=True):
    return json.dumps(obj, separators=(",", ":")).encode() + (b"\n" if newline else b"")


def bad_lines(prev_n):
    """Forty or more kinds of bad line. Each ends with a newline. `prev_n` is the number of the last good event."""
    ok = json.loads(line(prev_n + 1))
    good_n = prev_n + 1

    def tweak(**kw):
        d = dict(ok)
        d.update(kw)
        return raw(d)

    def minus(key):
        d = dict(ok)
        del d[key]
        return raw(d)

    def recrc(**kw):
        n, at, kind, data = kw.pop("n", good_n), kw.pop("at", AT), kw.pop("kind", "output"), kw.pop("data", ok["data"])
        d = {"n": n, "at": at, "kind": kind, "data": data, "crc": goallog._crc(n, at, kind, data)}
        d.update(kw)
        return raw(d)

    out = {
        "invalid utf8 byte": b"\xff\xfe\n",
        "invalid utf8 inside json": b'{"n":' + str(good_n).encode() + b',"at":"\xff"}\n',
        "truncated utf8": b"\xe2\x82\n",
        "lone continuation": b"\x80\n",
        "overlong utf8": b"\xc0\xaf\n",
        "too long": b"x" * 4097 + b"\n",
        "much too long": b"y" * 100000 + b"\n",
        "long valid json": raw({"pad": "z" * 5000}),
        "empty line": b"\n",
        "spaces only": b"   \n",
        "not json": b"hello world\n",
        "half json": b'{"n":1,"at":\n',
        "trailing comma": b'{"n":1,}\n',
        "single quotes": b"{'n': 1}\n",
        "json list": b"[1,2,3]\n",
        "json number": b"42\n",
        "json string": b'"text"\n',
        "json null": b"null\n",
        "json true": b"true\n",
        "bom first": b"\xef\xbb\xbf" + line(good_n),
        "nul bytes": b"\x00\x00\x00\n",
        "extra key": tweak(extra=1),
        "missing n": minus("n"),
        "missing at": minus("at"),
        "missing kind": minus("kind"),
        "missing data": minus("data"),
        "missing crc": minus("crc"),
        "n is a string": tweak(n=str(good_n)),
        "n is a float": tweak(n=float(good_n)),
        "n is a bool": tweak(n=True),
        "n is zero": recrc(n=0),
        "n is negative": recrc(n=-3),
        "n repeats the last": recrc(n=prev_n) if prev_n >= 1 else b"\n",
        "n is lower than the last": recrc(n=max(prev_n - 1, 0)),
        "at is an int": tweak(at=5),
        "at is not a time": recrc(at="yesterday"),
        "at has month 13": recrc(at="2026-13-01T00:00:00Z"),
        "at has no Z": recrc(at="2026-11-13T10:15:30"),
        "kind is an int": tweak(kind=5),
        "unknown kind": recrc(kind="launch"),
        "data is a list": tweak(data=[]),
        "data has an extra key": recrc(data={"lines": 1, "bytes": 1, "skipped": 0, "text": "leak"}),
        "data lacks a key": recrc(data={"lines": 1}),
        "data has a string count": recrc(data={"lines": "1", "bytes": 1, "skipped": 0}),
        "data has a negative count": recrc(data={"lines": -1, "bytes": 1, "skipped": 0}),
        "crc is wrong": tweak(crc="00000000" if ok["crc"] != "00000000" else "00000001"),
        "crc is upper case": tweak(crc=ok["crc"].upper() if ok["crc"].upper() != ok["crc"] else "ZZZZZZZZ"),
        "crc is short": tweak(crc=ok["crc"][:6]),
        "crc is an int": tweak(crc=12345678),
        "data changed after the crc": tweak(data={"lines": 2, "bytes": 10, "skipped": 0}),
    }
    return out


class ShapeTests(unittest.TestCase):
    def test_make_line_is_one_line_with_a_crc(self):
        b = goallog.make_line(12, AT, "error", {"sig": "3fa91c20b1c4d5e6"})
        self.assertTrue(b.endswith(b"\n") and b.count(b"\n") == 1)
        o = json.loads(b)
        self.assertEqual(list(o), ["n", "at", "kind", "data", "crc"])
        self.assertTrue(goallog.valid_event(o))
        self.assertEqual(len(o["crc"]), 8)

    def test_every_kind_of_the_table_is_valid_with_its_data(self):
        samples = {
            "state": {"from": "queued", "to": "running", "reason": "start", "recovered": False},
            "started": {"role": "builder", "agent": "claude-build", "cap_uu": 30, "pid": 4242},
            "output": {"lines": 14, "bytes": 900, "skipped": 0},
            "error": {"sig": "3fa91c20b1c4d5e6"},
            "fingerprint": {"changed": True, "files": 3},
            "approval_requested": {"kind": "needs-owner"},
            "approval_answered": {"kind": "needs-owner", "answer": "no"},
            "check_result": {"n": 1, "verdict": "pass"},
            "skipped": {"line": 4, "offset": 120, "length": 7, "reason": "json", "sha256": "a" * 64},
            "stopped": {"reason": "kill"},
            "worktree": {"action": "made", "base": "9f1c2e0a"},
            "poll": {},
            "waiting": {"left_s": 3600},
        }
        self.assertEqual(set(samples), set(goallog.KINDS))
        for i, (kind, data) in enumerate(samples.items(), 1):
            o = json.loads(goallog.make_line(i, AT, kind, data))
            self.assertTrue(goallog.valid_event(o), kind)

    def test_real_and_not_real_events(self):
        mk = lambda kind, data: json.loads(goallog.make_line(1, AT, kind, data))  # noqa: E731
        self.assertFalse(goallog.is_real(mk("poll", {})))
        self.assertFalse(goallog.is_real(mk("waiting", {"left_s": 5})))
        self.assertFalse(goallog.is_real(mk("fingerprint", {"changed": False, "files": 0})))
        self.assertTrue(goallog.is_real(mk("fingerprint", {"changed": True, "files": 2})))
        for kind, data in (("state", {"from": "queued", "to": "running", "reason": "start", "recovered": False}),
                           ("error", {"sig": "a" * 16}), ("output", {"lines": 1, "bytes": 1, "skipped": 0}),
                           ("stopped", {"reason": "kill"})):
            self.assertTrue(goallog.is_real(mk(kind, data)), kind)

    def test_valid_event_is_total(self):
        def check(v):
            return isinstance(goallog.valid_event(v), bool)

        gen.run_property(self, lambda g: g.json_value(), check, cases=2000, seeds=gen.SEEDS)

    def test_make_line_refuses_what_it_cannot_make_valid(self):
        for args in ((0, AT, "poll", {}), (1, "now", "poll", {}), (1, AT, "bogus", {}), (1, AT, "poll", {"x": 1}),
                     (True, AT, "poll", {})):
            with self.assertRaises(ValueError):
                goallog.make_line(*args)


class ReaderTests(unittest.TestCase):
    def test_a_clean_log_reads_whole(self):
        events, skipped = goallog.read(b"".join(good_log()))
        self.assertEqual([e["n"] for e in events], [1, 2, 3, 4, 5, 6])
        self.assertEqual(skipped, [])

    def test_an_empty_log(self):
        self.assertEqual(goallog.read(b""), ([], []))

    def test_forty_kinds_of_bad_line_at_every_position(self):
        for pos in range(0, 7):
            kinds = bad_lines(pos)  # the last good event before position pos has number pos
            self.assertGreaterEqual(len(kinds), 40)
            for name, bad in kinds.items():
                lines = good_log()
                data = with_bad(lines, pos, bad)
                events, skipped = goallog.read(data)
                self.assertEqual([e["n"] for e in events], [1, 2, 3, 4, 5, 6], (pos, name))
                self.assertEqual(len(skipped), 1, (pos, name))
                s = skipped[0]
                self.assertEqual(s.line, pos + 1, (pos, name))
                self.assertEqual(s.offset, sum(len(x) for x in lines[:pos]), (pos, name))
                self.assertEqual(s.length, len(bad.rstrip(b"\n")) if bad.endswith(b"\n") else len(bad), (pos, name))
                self.assertEqual(s.sha256, hashlib.sha256(bad[:-1]).hexdigest(), (pos, name))
                self.assertIn(s.reason, goallog.SKIP_REASONS, (pos, name))

    def test_two_bad_lines_in_a_row_give_two_skips(self):
        data = with_bad(good_log(), 2, b"junk\n\xff\n")
        events, skipped = goallog.read(data)
        self.assertEqual(len(events), 6)
        self.assertEqual([s.line for s in skipped], [3, 4])

    def test_specific_reasons(self):
        r = lambda b: goallog.read(line(1) + b)[1][0].reason  # noqa: E731
        self.assertEqual(r(b"\xff\n"), "utf8")
        self.assertEqual(r(b"x" * 5000 + b"\n"), "long")
        self.assertEqual(r(b"nope\n"), "json")
        self.assertEqual(r(b"[]\n"), "shape")
        self.assertEqual(r(goallog.make_line(1, AT, "poll", {})), "order")
        bad_crc = json.loads(line(2))
        bad_crc["crc"] = "00000000"
        self.assertEqual(r(raw(bad_crc)), "crc")

    def test_a_gap_in_the_numbers_is_allowed(self):
        events, skipped = goallog.read(line(1) + line(5) + line(9))
        self.assertEqual(([e["n"] for e in events], skipped), ([1, 5, 9], []))

    def test_a_line_of_exactly_4096_bytes_is_not_long_and_4097_is(self):
        pad = 4096 - len(raw({"pad": ""}).rstrip(b"\n"))
        edge = raw({"pad": "p" * pad})
        self.assertEqual(len(edge.rstrip(b"\n")), 4096)
        self.assertEqual(goallog.read(edge)[1][0].reason, "shape")  # not long: it parsed and was the wrong shape
        self.assertEqual(goallog.read(raw({"pad": "p" * (pad + 1)}))[1][0].reason, "long")

    def test_torn_last_line_is_waiting_not_bad(self):
        data = b"".join(good_log(3)) + b'{"n":4,"at":"2026'
        res = goallog.read_full(data)
        self.assertEqual(len(res.events), 3)
        self.assertEqual(res.skipped, [])
        self.assertTrue(res.torn)
        self.assertEqual(res.torn_offset, len(b"".join(good_log(3))))
        self.assertFalse(goallog.read_full(b"".join(good_log(3))).torn)
        self.assertFalse(goallog.read_full(b"").torn)

    def test_a_complete_event_without_its_newline_is_still_only_waiting(self):
        data = b"".join(good_log(2)) + line(3).rstrip(b"\n")
        res = goallog.read_full(data)
        self.assertEqual((len(res.events), res.torn), (2, True))

    def test_5000_random_byte_strings_never_raise(self):
        def check(data):
            events, skipped = goallog.read(data)
            return isinstance(events, list) and isinstance(skipped, list)

        gen.run_property(self, lambda g: g.data(0, 300), check, cases=1250, seeds=gen.SEEDS)  # 4 seeds, 5000 in all

    def test_random_mixes_of_good_and_bad_lines_keep_every_good_line(self):
        def make(g):
            out, good = [], 0
            for _ in range(g.between(0, 12)):
                if g.chance(0.6):
                    good += 1
                    out.append(("good", good))
                else:
                    out.append(("bad", g.data(0, 30).replace(b"\n", b"x")))
            return out

        def check(spec):
            data = b"".join(line(v) if k == "good" else v + b"\n" for k, v in spec)
            events, skipped = goallog.read(data)
            want = [v for k, v in spec if k == "good"]
            # a random byte string can by chance be a valid JSON object of the wrong shape; it is skipped, never an event
            return [e["n"] for e in events] == want

        gen.run_property(self, make, check, cases=800, seeds=gen.SEEDS)

    def test_reading_is_linear_in_the_size(self):
        junk = (b"not a valid event line, just text of some length\n" * 22000)[:1_000_000]
        t = time.monotonic()
        events, skipped = goallog.read(junk)
        one = time.monotonic() - t
        self.assertLess(one, 5.0)
        self.assertGreater(len(skipped), 20000)
        t = time.monotonic()
        goallog.read(junk * 4)
        four = time.monotonic() - t
        self.assertLess(four, max(one * 16, 1.0))  # not quadratic

    def test_a_ten_megabyte_line_is_one_skip_in_bounded_time(self):
        data = line(1) + b"q" * 10_000_000 + b"\n" + line(2)
        t = time.monotonic()
        events, skipped = goallog.read(data)
        self.assertLess(time.monotonic() - t, 5.0)
        self.assertEqual([e["n"] for e in events], [1, 2])
        self.assertEqual((len(skipped), skipped[0].length, skipped[0].reason), (1, 10_000_000, "long"))


class LineReaderTests(unittest.TestCase):
    def feed(self, chunks):
        r = goallog.LineReader()
        out = []
        for c in chunks:
            out += r.feed(c)
        out += r.flush()
        return out

    def test_lines_across_chunks(self):
        self.assertEqual(self.feed([b"ab", b"c\nde", b"f\n", b"gh"]), [("abc", False), ("def", False), ("gh", False)])

    def test_over_long_line_is_cut_to_4096_and_flagged_and_the_rest_thrown_away(self):
        out = self.feed([b"a" * 10000, b"b" * 10000 + b"\nnext\n"])
        self.assertEqual(out[0][1], True)
        self.assertEqual(len(out[0][0]), 4096)
        self.assertEqual(out[1], ("next", False))
        self.assertEqual(len(out), 2)

    def test_not_utf8_is_replaced_and_flagged(self):
        out = self.feed([b"ok \xff\xfe bad\n"])
        self.assertEqual(out[0][1], True)
        self.assertIn("\ufffd", out[0][0])

    def test_ten_megabytes_without_a_newline_is_read_in_bounded_memory(self):
        r = goallog.LineReader()
        for _ in range(100):
            r.feed(b"z" * 100_000)
            self.assertLessEqual(r.buffered(), 4096)
        out = r.feed(b"\nError: after the flood\n")
        self.assertEqual(out[-1], ("Error: after the flood", False))

    def test_a_child_that_prints_a_flood_noise_and_a_valid_error_line_is_still_read(self):
        import subprocess
        import sys
        agent = Path(__file__).with_name("fake_agent.py")
        script = [{"flood": 3_000_000, "newline": False}, {"noise": 20000}, {"error": "Error: the real one"}]
        env = dict(os.environ, FAKE_GOAL_SCRIPT=json.dumps(script))
        p = subprocess.Popen([sys.executable, str(agent)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)
        p.stdin.close()
        r, seen = goallog.LineReader(), []
        while True:
            chunk = p.stdout.read(65536)
            if not chunk:
                break
            seen += r.feed(chunk)
            self.assertLessEqual(r.buffered(), 4096)
        seen += r.flush()
        p.wait()
        p.stdout.close()
        self.assertIn(("Error: the real one", False), seen)
        self.assertTrue(any(flag for _t, flag in seen))

    def test_random_bytes_never_raise_and_never_buffer_more_than_4096(self):
        def check(chunks):
            r = goallog.LineReader()
            for c in chunks:
                r.feed(c)
                if r.buffered() > 4096:
                    return False
            r.flush()
            return True

        gen.run_property(self, lambda g: [g.data(0, 200) for _ in range(g.between(0, 8))], check, cases=800, seeds=gen.SEEDS)


class WriterTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(os.path.realpath(self._tmp.name))
        self.path = self.dir / "T-02.events.jsonl"
        self.t = [1_794_000_000]

    def writer(self):
        return goallog.Writer(self.path, lambda: self.t[0]).open()

    def test_append_numbers_events_from_one_and_creates_the_file_0600(self):
        w = self.writer()
        w.append("started", {"role": "builder", "agent": "claude-build", "cap_uu": 30, "pid": 1})
        w.append("poll", {})
        events, skipped = goallog.read(self.path.read_bytes())
        self.assertEqual([e["n"] for e in events], [1, 2])
        self.assertEqual(skipped, [])
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)
        self.assertEqual(events[0]["at"], "2026-11-06T21:20:00Z")

    def test_a_second_writer_continues_the_numbers(self):
        self.writer().append("poll", {})
        w = self.writer()
        w.append("poll", {})
        self.assertEqual([e["n"] for e in goallog.read(self.path.read_bytes())[0]], [1, 2])

    def test_append_refuses_an_invalid_event(self):
        w = self.writer()
        for kind, data in (("bogus", {}), ("poll", {"x": 1}), ("error", {"sig": "short"})):
            with self.assertRaises(ValueError):
                w.append(kind, data)
        self.assertFalse(self.path.exists())

    def test_every_bad_line_gets_exactly_one_skip_record_and_never_a_second(self):
        for name, bad in bad_lines(3).items():
            with self.subTest(name):
                self.path.write_bytes(with_bad(good_log(6), 3, bad))
                w = self.writer()
                self.assertEqual(w.record_skips(), 1)
                self.assertEqual(w.record_skips(), 0)
                events, skipped = goallog.read(self.path.read_bytes())
                recs = [e for e in events if e["kind"] == "skipped"]
                self.assertEqual(len(recs), 1)
                self.assertEqual(recs[0]["data"]["offset"], skipped[0].offset)
                self.assertEqual(recs[0]["data"]["sha256"], skipped[0].sha256)
                # reading and reopening again records nothing new
                w2 = self.writer()
                self.assertEqual(w2.record_skips(), 0)
                self.assertEqual(len([e for e in goallog.read(self.path.read_bytes())[0] if e["kind"] == "skipped"]), 1)

    def test_the_record_never_holds_the_text_of_the_bad_line(self):
        secret = b"SENTINEL-SECRET-TEXT-" + b"k" * 20
        self.path.write_bytes(b"".join(good_log(2)) + secret + b"\n" + line(3))
        w = self.writer()
        w.record_skips()
        self.assertEqual(self.path.read_bytes().count(b"SENTINEL"), 1)  # only the original bad line itself

    def test_two_bad_lines_two_records(self):
        self.path.write_bytes(with_bad(good_log(4), 2, b"a\nb\n"))
        self.assertEqual(self.writer().record_skips(), 2)

    def test_a_torn_tail_gets_a_newline_and_one_torn_record_at_the_next_start(self):
        good = b"".join(good_log(3))
        self.path.write_bytes(good + b'{"n":4,"at":"20')
        w = self.writer()
        self.assertTrue(self.path.read_bytes().startswith(good + b'{"n":4,"at":"20\n'))
        events, skipped = goallog.read(self.path.read_bytes())
        recs = [e for e in events if e["kind"] == "skipped"]
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["data"]["reason"], "torn")
        self.assertEqual(recs[0]["data"]["offset"], len(good))
        self.assertEqual(w.record_skips(), 0)  # the torn line is now a skipped line that is already recorded
        self.assertEqual(self.writer().record_skips(), 0)
        self.assertEqual(len([e for e in goallog.read(self.path.read_bytes())[0] if e["kind"] == "skipped"]), 1)
        self.assertEqual([e["n"] for e in events if e["kind"] != "skipped"], [1, 2, 3])

    def test_the_cap_is_a_failed_write_not_a_truncation(self):
        with mock.patch.object(goallog, "MAX_LOG", 600):
            w = self.writer()
            n = 0
            with self.assertRaises(goallog.LogWriteFailed):
                for _ in range(100):
                    w.append("poll", {})
                    n += 1
            self.assertGreater(n, 2)
            size = self.path.stat().st_size
            self.assertLessEqual(size, 600)
            self.assertEqual(len(goallog.read(self.path.read_bytes())[0]), n)

    def test_the_default_cap_is_8_megabytes(self):
        self.assertEqual(goallog.MAX_LOG, 8 * 1024 * 1024)
        self.assertEqual(goallog.MAX_LINE, 4096)

    def test_a_write_error_raises_log_write_failed(self):
        w = self.writer()
        with mock.patch.object(goallog, "_write", side_effect=OSError(errno.ENOSPC, "No space left on device")):
            with self.assertRaises(goallog.LogWriteFailed):
                w.append("poll", {})
        with mock.patch.object(goallog, "_write", return_value=3):  # a short write
            with self.assertRaises(goallog.LogWriteFailed):
                w.append("poll", {})

    def test_log_write_failed_is_an_umwayi_error_and_never_quotes_the_path(self):
        w = self.writer()
        with mock.patch.object(goallog, "_write", side_effect=OSError(errno.EIO, str(self.dir))):
            with self.assertRaises(goallog.LogWriteFailed) as cm:
                w.append("poll", {})
        self.assertIsInstance(cm.exception, UmwayiError)
        self.assertNotIn(str(self.dir), str(cm.exception))

    def test_fsync_for_state_and_stopped_only(self):
        w = self.writer()
        with mock.patch.object(goallog, "_fsync") as fs:
            w.append("poll", {})
            w.append("output", {"lines": 1, "bytes": 1, "skipped": 0})
            self.assertEqual(fs.call_count, 0)
            w.append("state", {"from": "queued", "to": "running", "reason": "start", "recovered": False})
            w.append("stopped", {"reason": "kill"})
            self.assertEqual(fs.call_count, 2)

    def test_probe_writes_in_the_folder_and_fails_loudly(self):
        w = self.writer()
        w.probe()
        self.assertEqual([p.name for p in self.dir.iterdir() if p.name != self.path.name], [])  # left no file behind
        with mock.patch.object(goallog, "_write", side_effect=OSError(errno.EROFS, "read-only")):
            with self.assertRaises(goallog.LogWriteFailed):
                w.probe()

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root can write to a read-only folder")
    def test_probe_fails_in_a_read_only_folder(self):
        w = self.writer()
        os.chmod(self.dir, 0o500)
        self.addCleanup(os.chmod, self.dir, 0o700)
        with self.assertRaises(goallog.LogWriteFailed):
            w.probe()

    def test_a_link_in_place_of_the_log_is_refused(self):
        target = self.dir / "elsewhere"
        target.write_bytes(b"")
        os.symlink(target, self.path)
        with self.assertRaises(UmwayiError):
            self.writer().append("poll", {})
        self.assertEqual(target.read_bytes(), b"")


class PlantedFaultTests(unittest.TestCase):
    """Each planted fault of W9.R12.6 is caught by a check that the real code passes."""

    def contract(self, reader, record_skips=None):
        lines = good_log(5)
        data = with_bad(lines, 2, b"garbage\n")
        events, skipped = reader(data)
        self.assertEqual([e["n"] for e in events], [1, 2, 3, 4, 5])  # lines after the bad one are read
        self.assertEqual(len(skipped), 1)

    def test_the_contract_passes_on_the_real_reader(self):
        self.contract(goallog.read)

    def test_fault_reader_stops_at_the_first_bad_line(self):
        def faulty(data):
            events, skipped = [], []
            for i, part in enumerate(data.split(b"\n")[:-1]):
                try:
                    events.append(json.loads(part))
                except ValueError:
                    skipped.append(i)
                    break
            return events, skipped

        with self.assertRaises(AssertionError):
            self.contract(faulty)

    def make_path(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "e.jsonl"
        path.write_bytes(with_bad(good_log(4), 2, b"junk\n"))
        return path

    def check_record_once(self, writer_cls):
        path = self.make_path()
        w = writer_cls(path, lambda: 1_794_000_000).open()
        w.record_skips()
        w.record_skips()
        recs = [e for e in goallog.read(path.read_bytes())[0] if e["kind"] == "skipped"]
        self.assertEqual(len(recs), 1)
        self.assertEqual(path.read_bytes().count(b"junk"), 1)  # the bad line's text only where it already was

    def test_the_record_check_passes_on_the_real_writer(self):
        self.check_record_once(goallog.Writer)

    def test_fault_skip_not_recorded(self):
        class NoRecord(goallog.Writer):
            def record_skips(self):
                return 0

        with self.assertRaises(AssertionError):
            self.check_record_once(NoRecord)

    def test_fault_skip_recorded_twice(self):
        class Twice(goallog.Writer):
            def record_skips(self):
                self._recorded = set()  # forgets what it recorded
                return super().record_skips()

        with self.assertRaises(AssertionError):
            self.check_record_once(Twice)

    def test_fault_bad_line_text_in_the_record(self):
        class Leaks(goallog.Writer):
            def record_skips(self):
                n = super().record_skips()
                with open(self.path, "ab") as f:
                    f.write(b"junk\n")  # the text of the bad line copied into the log
                return n

        with self.assertRaises(AssertionError):
            self.check_record_once(Leaks)


class LogbookStaysStrictTests(unittest.TestCase):
    """W9.R12.1: the logbook is not one of these logs. A hand edited entry still stops every start."""

    def test_an_edited_logbook_entry_fails_closed_and_is_never_skipped(self):
        from umwayi import logbook
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for i in range(3):
                logbook.append(root, logbook.Entry(DATE, "umwayi goal", f"Goal G-000{i} started", "Checked.", "Nothing."))
            logbook.seal(root, DATE, "test", start_chain=True)
            p = root / "LOGBOOK.md"
            p.write_text(p.read_text().replace("G-0001", "G-0099"), encoding="utf-8")
            with self.assertRaises(UmwayiError):
                logbook.read_checked(root)


if __name__ == "__main__":
    unittest.main()
