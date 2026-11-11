"""Layer 5 addendum: logbook crash safety (tasks L5.1 to L5.5).

A write stopped half way (a signal, SIGKILL, a power cut) must never leave a logbook that refuses every
later write, and must never be mistaken for a hand edit, while a real hand edit is still refused.

In-process tests stop a write between two of its steps with an exception that skips every cleanup, the
way SIGKILL would (the lock still goes, as the kernel lets go of a flock when a process dies). The
real-process tests stop `python -m umwayi check` with real signals while a planted fault holds its write
between two steps (UMWAYI_FAULT, test only).
"""

import io
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.adapters.support import SITECUSTOMIZE
from tests.helpers import entry_text, logbook_lock_held, without_logbook_lock, write_sealed_logbook
from umwayi import logbook
from umwayi.cli import main
from umwayi.errors import UmwayiError
from umwayi.logbook import Entry, append

REPO = Path(__file__).resolve().parent.parent
RULES = "rules:\n  - id: r\n    title: t\n    text: t\n    verdict: yes\n    matchers:\n      type: read\n"
SECRET = "TOPSECRETLINETEXT"
STEPS = ("_append_bytes", "_record_hash", "_drop_intent")  # the step a write is stopped before


class Killed(BaseException):
    """Stands in for SIGKILL: no except clause in umwayi catches it, so no cleanup runs."""


def entry(date="2026-11-10", added="one thing"):
    return Entry(date, "umwayi test", added, "a check", "nothing else")


class CrashBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.path = self.root / "LOGBOOK.md"
        self.rec = self.root / ".umwayi" / "logbook.sha256"
        self.pending = self.root / ".umwayi" / "logbook.pending"
        p = mock.patch.object(logbook, "LOCK_WAIT_SECONDS", 0)
        p.start()
        self.addCleanup(p.stop)

    def snap(self):
        out = {}
        for dp, _dn, fn in os.walk(self.root):
            for f in fn:
                full = os.path.join(dp, f)
                out[os.path.relpath(full, self.root)] = Path(full).read_bytes()
        return without_logbook_lock(out)

    def killed_before(self, step, fn, *args):
        """Run fn and stop it, as SIGKILL would, just before `step` of its write."""
        with mock.patch.object(logbook, step, side_effect=Killed):
            with self.assertRaises(Killed):
                fn(*args)
        self.assertFalse(logbook_lock_held(self.root))  # the lock goes with the writer

    def added(self):
        return [e.added for e in logbook.read_checked(self.root)]

    def recoveries(self):
        return [e for e in logbook.read_checked(self.root) if e.source == logbook.RECOVER_SOURCE]

    def assert_intact(self):
        self.assertEqual(logbook.verify(self.root).problems, [])
        self.assertFalse(self.pending.exists(), "the intent was left behind")
        self.assertEqual(logbook.verify(self.root).notes, [])

    def two_then_killed(self, step="_record_hash"):
        """One entry written, the second stopped before `step`. Returns the bytes before the second."""
        append(self.root, entry(added="the first"))
        before = self.path.read_bytes()
        self.killed_before(step, append, self.root, entry(added="the second"))
        return before

    def refused(self, fragment, fn=None):
        before = self.snap()
        with self.assertRaises(UmwayiError) as cm:
            (fn or (lambda: append(self.root, entry(added="refused"))))()
        self.assertIn(fragment, str(cm.exception))
        self.assertNotIn(SECRET, str(cm.exception))
        self.assertEqual(self.snap(), before, "a refusal changed something")
        return str(cm.exception)

    def cli(self, *argv, clock="2026-11-10"):
        out, err = io.StringIO(), io.StringIO()
        old = sys.stderr
        sys.stderr = err
        try:
            with mock.patch("umwayi.cli._today", return_value=clock):
                code = main(["--root", str(self.root), "logbook", *argv], out=out)
        finally:
            sys.stderr = old
        return code, out.getvalue(), err.getvalue()


# ============================================================= the intent (L5.2)


class IntentTests(CrashBase):
    def test_the_intent_names_the_record_the_hashes_the_lengths_and_the_bytes(self):
        before = self.two_then_killed()
        intent = logbook._parse_intent(self.pending.read_bytes())
        data = self.path.read_bytes()
        self.assertEqual((intent.kind, intent.pid), ("write", os.getpid()))
        self.assertEqual(intent.record, logbook.sha256_hex(before))
        self.assertEqual(self.rec.read_text().strip(), intent.record)  # the record was not touched yet
        self.assertEqual((intent.before, intent.before_len), (logbook.sha256_hex(before), len(before)))
        self.assertEqual((intent.after, intent.after_len), (logbook.sha256_hex(data), len(data)))
        self.assertEqual(intent.entry, data[len(before):])
        self.assertTrue(intent.encode().startswith(b"umwayi logbook intent 1\nkind write\nwriter "))
        self.assertEqual(intent.encode(), self.pending.read_bytes())

    def test_a_new_logbook_starts_from_no_record_and_an_empty_file(self):
        self.killed_before("_record_hash", append, self.root, entry())
        intent = logbook._parse_intent(self.pending.read_bytes())
        self.assertEqual((intent.record, intent.before_len), ("none", 0))
        self.assertTrue(intent.entry.startswith(b"# Logbook\n"))
        append(self.root, entry(added="next"))
        self.assertEqual(self.added()[0], "one thing")
        self.assert_intact()

    def test_a_bad_intent_is_refused_like_a_hand_edit_and_changes_nothing(self):
        self.two_then_killed()
        good = self.pending.read_bytes()
        lines = good.split(b"\n")

        def with_line(i, value):
            new = list(lines)
            new[i] = value
            return b"\n".join(new)
        bad = {
            "magic": with_line(0, b"umwayi logbook intent 2"),
            "kind": with_line(1, b"kind rewrite"),
            "pid": with_line(2, b"writer x unknown"),
            "start": with_line(2, b"writer 1 soon"),
            "record": with_line(3, b"record " + b"z" * 64),
            "before": with_line(4, b"before " + b"0" * 64 + b" 10"),
            "after length": with_line(5, b"after " + lines[5].split(b" ")[1] + b" 1"),
            "entry length": with_line(6, b"entry 1"),
            "entry bytes": good[:-2] + b"X\n",
            "extra byte": good + b"\n",
            "cut short": good[:40],
            "empty": b"",
            "not ascii": with_line(1, "kind wr\u00efte".encode("utf-8")),
            "write that does not start from its record": with_line(3, b"record " + b"a" * 64),
        }
        for name, raw in bad.items():
            with self.subTest(intent=name):
                self.pending.write_bytes(raw)
                self.refused("Nothing was written")
                self.assertTrue(logbook.verify(self.root).problems)
                with self.assertRaises(UmwayiError):
                    logbook.read_checked(self.root)
        self.pending.unlink()
        for name, make in (("a link", lambda: self.pending.symlink_to(self.path)), ("a folder", self.pending.mkdir)):
            with self.subTest(intent=name):
                make()
                self.refused("is malformed or not a normal file")
                self.pending.unlink() if self.pending.is_symlink() else self.pending.rmdir()

    def durable_steps(self, fn):
        """The order of the steps that make a write durable: fsyncs, folder fsyncs, atomic writes, removals."""
        events = []
        real_fsync, real_dir, real_atomic, real_unlink = os.fsync, logbook.fsync_dir, logbook.atomic_write, os.unlink

        def fsync(fd):
            name = os.path.basename(os.readlink(f"/proc/self/fd/{fd}"))
            if name == "LOGBOOK.md":
                events.append(("fsync", name))
            return real_fsync(fd)

        def fsync_dir(path):
            events.append(("fsync folder", Path(path).name if Path(path) != self.root else "root"))
            return real_dir(path)

        def atomic_write(path, data, **kw):  # kw: the intent's mode (S.2)
            events.append(("atomic write", Path(path).name))
            return real_atomic(path, data, **kw)

        def unlink(path, *a, **k):
            if Path(path).parent.name == ".umwayi":
                events.append(("remove", Path(path).name))
            return real_unlink(path, *a, **k)
        with mock.patch("os.fsync", side_effect=fsync), mock.patch("os.unlink", side_effect=unlink), \
                mock.patch.object(logbook, "fsync_dir", side_effect=fsync_dir), \
                mock.patch.object(logbook, "atomic_write", side_effect=atomic_write):
            fn()
        return events

    def test_every_step_is_durable_before_the_next_one_starts(self):
        steps = [("atomic write", "logbook.pending"), ("fsync folder", ".umwayi"), ("fsync", "LOGBOOK.md"),
                 ("atomic write", "logbook.sha256"), ("fsync folder", ".umwayi"),
                 ("remove", "logbook.pending"), ("fsync folder", ".umwayi")]
        new = steps[:3] + [("fsync folder", "root")] + steps[3:]  # creating LOGBOOK.md is a change of the root folder
        self.assertEqual(self.durable_steps(lambda: append(self.root, entry())), new)
        self.assertEqual(self.durable_steps(lambda: append(self.root, entry(added="second"))), steps)

    def test_bytes_added_by_something_else_during_a_write_are_refused_as_a_hand_edit(self):
        append(self.root, entry(added="the first"))
        record_before = self.rec.read_bytes()
        real = logbook._append_bytes

        def and_something_else(root, payload, created):
            real(root, payload, created)
            with open(self.path, "ab") as f:  # a whole, well formed entry: only the hash can tell
                f.write(entry_text(date="2026-11-10", source="something else").encode("utf-8"))
        with mock.patch.object(logbook, "_append_bytes", side_effect=and_something_else):
            with self.assertRaises(UmwayiError) as cm:
                append(self.root, entry(added="the second"))
        self.assertIn("changed while this entry was being written", str(cm.exception))
        self.assertEqual(self.rec.read_bytes(), record_before)  # nothing was recorded
        self.assertTrue(self.pending.exists())
        self.refused("an interrupted write was found, but the files do not match what it intended")
        self.assertIn("does not match what it intended", logbook.verify(self.root).problems[0].message)
        with self.assertRaises(UmwayiError):
            logbook.check_writable(self.root, "2026-11-10")
        r = logbook.seal(self.root, "2026-11-10", "Miguel")  # only the owner accepts it, and the seal says so
        self.assertEqual(r.entries_before, 3)  # the owner accepts what the file holds, the outside entry too
        self.assertIn("did not match the file and was dropped", logbook.read_checked(self.root)[-1].checked)
        self.assert_intact()


# ============================================== a write stopped at each step (L5.3)


class StoppedAtEachStepTests(CrashBase):
    def test_the_next_write_recovers_with_one_entry_for_each_step(self):
        expected = {
            "_append_bytes": "the entry was never written and the intent was dropped",
            "_record_hash": "the entry was written in full and its hash is now recorded",
            "_drop_intent": "the entry was written in full and its hash is now recorded",
        }
        for step, words in expected.items():
            with self.subTest(step=step):
                for p in (self.path, self.rec, self.pending):
                    p.unlink(missing_ok=True)
                self.two_then_killed(step)
                self.assertTrue(self.pending.exists())
                append(self.root, entry(added="the third"))
                added = self.added()
                [rec] = self.recoveries()
                self.assertIn(words, rec.added)
                self.assertIn(f"(writer PID {os.getpid()}, ", rec.added)
                self.assertEqual(rec.not_done, "The interrupted command did not finish; what it was doing was not redone.")
                kept = ["the first"] + (["the second"] if step != "_append_bytes" else [])
                self.assertEqual(added, kept + [rec.added, "the third"])
                self.assert_intact()

    def test_check_writable_recovers_too_so_a_running_agent_is_not_stopped(self):
        self.two_then_killed()
        logbook.check_writable(self.root, "2026-11-10")
        self.assertEqual(len(self.recoveries()), 1)
        self.assert_intact()

    def test_a_recovery_stopped_half_way_is_resumed_and_leaves_one_recovery_entry(self):
        for step in STEPS:
            with self.subTest(recovery_stopped_before=step):
                for p in (self.path, self.rec, self.pending):
                    p.unlink(missing_ok=True)
                self.two_then_killed("_record_hash")
                self.killed_before(step, append, self.root, entry(added="never"))  # stops the recovery write
                self.assertEqual(logbook._parse_intent(self.pending.read_bytes()).kind, "recover")
                append(self.root, entry(added="the third"))
                self.assertEqual(len(self.recoveries()), 1)
                self.assertEqual(self.added()[-1], "the third")
                self.assertNotIn("never", self.added())
                self.assert_intact()

    def test_an_interrupted_seal_that_never_wrote_leaves_the_logbook_as_it_was(self):
        self.path.write_text("# Logbook\n" + entry_text(date="2026-01-01"), encoding="utf-8")  # no record yet
        self.killed_before("_append_bytes", logbook.seal, self.root, "2026-11-10", "Miguel")
        text = self.path.read_bytes()
        with self.assertRaises(UmwayiError) as cm:
            append(self.root, entry())
        self.assertIn("no hash record", str(cm.exception))
        self.assertFalse(self.pending.exists())  # the intent of the seal that never wrote was dropped
        self.assertEqual(self.path.read_bytes(), text)  # and nothing else changed
        self.assertFalse(self.rec.exists())
        self.assertEqual(logbook.verify(self.root).problems[0].where, "record")
        logbook.seal(self.root, "2026-11-10", "Miguel")
        self.assertEqual(self.recoveries(), [])
        self.assert_intact()

    def test_an_interrupted_seal_that_wrote_its_entry_is_finished_and_logged(self):
        self.path.write_text("# Logbook\n" + entry_text(date="2026-01-01"), encoding="utf-8")
        self.killed_before("_record_hash", logbook.seal, self.root, "2026-11-10", "Miguel")
        append(self.root, entry(added="after the seal"))
        sources = [e.source for e in logbook.read_checked(self.root)]
        self.assertEqual(sources, ["hand", "umwayi logbook seal", logbook.RECOVER_SOURCE, "umwayi test"])
        self.assert_intact()

    def test_seal_recovers_a_recoverable_write_first(self):
        self.two_then_killed()
        with self.assertRaises(UmwayiError) as cm:
            logbook.seal(self.root, "2026-11-10", "Miguel")
        self.assertIn("already sealed and intact", str(cm.exception))
        self.assertEqual(len(self.recoveries()), 1)
        self.assert_intact()

    def test_the_recovery_entry_never_goes_backwards(self):
        self.two_then_killed()
        self.refused("before the date of the last entry", lambda: append(self.root, entry(date="2026-11-01")))
        self.assertTrue(self.pending.exists())

    def test_messages_never_hold_logbook_text(self):
        append(self.root, entry(added=f"the first {SECRET}"))
        self.killed_before("_record_hash", append, self.root, entry(added=f"the second {SECRET}"))
        with open(self.path, "ab") as f:
            f.write(b"x\n")
        self.refused("Nothing was written")
        for p in logbook.verify(self.root).problems:
            self.assertNotIn(SECRET, p.render())


# ======================================================= hand edits with a dead writer


class HandEditWhileAnIntentIsPresentTests(CrashBase):
    def test_every_other_mismatch_is_still_refused_with_no_recovery_entry(self):
        def edit_old():
            self.path.write_bytes(self.path.read_bytes().replace(b"the first", b"the FIRST"))

        def edit_newest():
            self.path.write_bytes(self.path.read_bytes().replace(b"the second", b"the SECOND"))

        def add_line():
            with open(self.path, "ab") as f:
                f.write(b"added by hand\n")

        def other_record():
            self.rec.write_text("0" * 64 + "\n", encoding="ascii")

        def no_record():
            self.rec.unlink()

        def no_logbook():
            self.path.unlink()

        def one_byte_of_the_intent():
            raw = bytearray(self.pending.read_bytes())
            raw[-3] = ord("Q")
            self.pending.write_bytes(bytes(raw))

        for name, change in (("an old entry", edit_old), ("the newest entry", edit_newest), ("a line at the end", add_line),
                             ("another record", other_record), ("no record", no_record), ("no logbook", no_logbook),
                             ("the intent's entry", one_byte_of_the_intent)):
            with self.subTest(edit=name):
                for p in (self.path, self.rec, self.pending):
                    p.unlink(missing_ok=True)
                self.two_then_killed()
                change()
                self.refused("Nothing was written")
                self.assertTrue(self.pending.exists(), "the intent of the dead writer must stay")
                self.assertTrue(logbook.verify(self.root).problems)
                with self.assertRaises(UmwayiError):
                    logbook.read_checked(self.root)
                with self.assertRaises(UmwayiError):
                    logbook.check_writable(self.root, "2026-11-10")
                if self.path.exists() and logbook.parse(self.path.read_text(encoding="utf-8"))[1] == []:
                    self.assertNotIn(logbook.RECOVER_SOURCE, self.path.read_text(encoding="utf-8"))


# ============================================================== a power cut (L5.3)


class PowerCutTests(CrashBase):
    def cut_to(self, before, k):
        """The second write was appending when the power went: only k of its bytes reached the disk."""
        self.path.write_bytes(self.path.read_bytes()[: len(before) + k])

    def test_nothing_or_part_of_the_entry_on_disk(self):
        for k in ("none", 1, "middle", "all but one"):
            with self.subTest(bytes_on_disk=k):
                for p in (self.path, self.rec, self.pending):
                    p.unlink(missing_ok=True)
                before = self.two_then_killed()
                size = len(self.path.read_bytes()) - len(before)
                n = {"none": 0, "middle": size // 2, "all but one": size - 1}.get(k, k)
                self.cut_to(before, n)
                if n == 0:  # the state before: the next write drops the intent, with one entry
                    append(self.root, entry(added="next"))
                    self.assertIn("never written", self.recoveries()[0].added)
                    self.assert_intact()
                    continue
                msg = self.refused("ends with part of an entry that was being written")
                self.assertIn("umwayi logbook recover --torn-tail --by NAME", msg)
                self.refused("power cut", lambda: logbook.seal(self.root, "2026-11-10", "Miguel"))
                with self.assertRaises(UmwayiError):
                    logbook.read_checked(self.root)
                self.assertIn("torn-tail", " ".join(p.message for p in logbook.verify(self.root).problems))
                r = logbook.recover_torn_tail(self.root, "2026-11-10", "Miguel")
                self.assertEqual((r.cut, r.logged), (n, True))
                [rec] = self.recoveries()
                self.assertTrue(rec.added.startswith(f"Recover by Miguel: cut back a torn tail of {n} bytes left by an "
                                                     "interrupted logbook write (writer PID "), rec.added)
                self.assertEqual(self.added(), ["the first", rec.added])
                self.assert_intact()

    def test_a_tail_that_differs_by_one_byte_is_never_cut(self):
        before = self.two_then_killed()
        self.cut_to(before, 10)
        raw = bytearray(self.path.read_bytes())
        raw[-1] = ord("#") if raw[-1] != ord("#") else ord("!")
        self.path.write_bytes(bytes(raw))
        self.refused("does not end with a torn tail",
                     lambda: logbook.recover_torn_tail(self.root, "2026-11-10", "Miguel"))
        self.refused("do not match what it intended")

    def test_a_torn_tail_without_its_intent_or_its_record_is_never_cut(self):
        before = self.two_then_killed()
        self.cut_to(before, 10)
        self.rec.unlink()
        self.refused("does not end with a torn tail",
                     lambda: logbook.recover_torn_tail(self.root, "2026-11-10", "Miguel"))
        self.pending.unlink()
        self.refused("no interrupted write", lambda: logbook.recover_torn_tail(self.root, "2026-11-10", "Miguel"))

    def test_the_command_refuses_an_intact_or_recoverable_logbook_and_bad_input(self):
        append(self.root, entry())
        self.refused("no interrupted write", lambda: logbook.recover_torn_tail(self.root, "2026-11-10", "Miguel"))
        self.killed_before("_record_hash", append, self.root, entry(added="second"))
        self.refused("the interrupted write is complete; the next write finishes it",
                     lambda: logbook.recover_torn_tail(self.root, "2026-11-10", "Miguel"))
        for by in ("", "x" * 101, "two\nlines"):
            with self.subTest(by=by):
                with self.assertRaises(UmwayiError):
                    logbook.recover_torn_tail(self.root, "2026-11-10", by)

    def test_a_torn_seal_is_cut_and_the_owner_seals_again(self):
        self.path.write_text("# Logbook\n" + entry_text(date="2026-01-01"), encoding="utf-8")
        before = self.path.read_bytes()
        self.killed_before("_record_hash", logbook.seal, self.root, "2026-11-10", "Miguel")
        self.cut_to(before, 5)
        r = logbook.recover_torn_tail(self.root, "2026-11-10", "Miguel")
        self.assertEqual((r.cut, r.logged), (5, False))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(self.pending.exists())
        logbook.seal(self.root, "2026-11-10", "Miguel")
        self.assert_intact()

    def test_cli_recover(self):
        before = self.two_then_killed()
        self.cut_to(before, 7)
        self.assertEqual(self.cli("recover", "--by", "Miguel")[0], 64)  # --torn-tail is required
        self.assertEqual(self.cli("recover", "--torn-tail", "--by", "")[0], 64)
        code, out, _ = self.cli("verify")
        self.assertEqual(code, 1)
        self.assertIn("problem: file: LOGBOOK.md ends with part of an entry", out)
        code, out, err = self.cli("recover", "--torn-tail", "--by", "Miguel")
        self.assertEqual(code, 0, err)
        self.assertIn("Cut back a torn tail of 7 bytes from LOGBOOK.md.", out)
        code, _, err = self.cli("recover", "--torn-tail", "--by", "Miguel")
        self.assertEqual(code, 1)
        self.assertIn("no interrupted write", err)
        self.assertEqual(self.cli("verify")[0], 0)


# ============================================================ readers (L5.3, L-Q4)


class ReaderTests(CrashBase):
    def test_readers_see_the_two_exact_states_as_the_file_it_left(self):
        for step, kept, words in (("_record_hash", ["the first", "the second"], "(completed)"),
                                  ("_append_bytes", ["the first"], "(not written)")):
            with self.subTest(step=step):
                for p in (self.path, self.rec, self.pending):
                    p.unlink(missing_ok=True)
                self.two_then_killed(step)
                before = self.snap()
                self.assertEqual(self.added(), kept)
                report = logbook.verify(self.root)
                self.assertEqual(report.problems, [])
                self.assertIn(words, report.notes[0])
                code, out, _ = self.cli("verify")
                self.assertEqual(code, 0)
                self.assertTrue(out.startswith(f"ok: {len(kept)} entries"))
                self.assertIn(f"info: a logbook write is in progress or was interrupted", out)
                self.assertEqual(self.snap(), before)  # readers write nothing, not even the recovery

    def test_a_reader_waits_for_a_write_it_caught_half_way(self):
        append(self.root, entry(added="the first"))
        looks = []
        real = logbook._read_logbook

        def looking(root):
            looks.append(1)
            if len(looks) == 1:  # the first look sees the file while it changes, as during a write
                return real(root) + b"half"
            return real(root)
        with mock.patch.object(logbook, "_read_logbook", side_effect=looking):
            self.assertEqual(self.added(), ["the first"])
        self.assertGreaterEqual(len(looks), 2)


# ================================================================= signals (L5.4)


class SignalsInProcessTests(CrashBase):
    def test_a_signal_during_a_write_is_held_off_and_delivered_once_after(self):
        seen = []

        def handler(signum, _frame):
            seen.append((signum, self.pending.exists(), logbook.verify(self.root).problems))
        old = signal.signal(signal.SIGTERM, handler)
        self.addCleanup(signal.signal, signal.SIGTERM, old)
        real = logbook._append_bytes

        def signalled(root, payload, created):
            os.kill(os.getpid(), signal.SIGTERM)
            os.kill(os.getpid(), signal.SIGTERM)
            real(root, payload, created)
        with mock.patch.object(logbook, "_append_bytes", side_effect=signalled):
            append(self.root, entry())
        self.assertEqual(seen, [(signal.SIGTERM, False, [])])  # once, after the whole write
        self.assertIs(signal.getsignal(signal.SIGTERM), handler)
        self.assertEqual(signal.pthread_sigmask(signal.SIG_BLOCK, []), set())
        self.assert_intact()

    def test_with_another_thread_running_the_handler_still_waits_for_the_write(self):
        # The kernel gives a process signal to a thread that does not block it; Python then runs the handler in
        # the main thread at once, in the middle of the write, unless the handler itself is held off too (L-Q2).
        import threading
        seen = []
        old = signal.signal(signal.SIGTERM, lambda *_a: seen.append(self.pending.exists()))
        self.addCleanup(signal.signal, signal.SIGTERM, old)
        stop = threading.Event()
        t = threading.Thread(target=stop.wait, args=(10,), daemon=True)  # started before the write: nothing blocked
        t.start()
        self.addCleanup(stop.set)
        real = logbook._append_bytes

        def signalled(root, payload, created):
            os.kill(os.getpid(), signal.SIGTERM)
            for _ in range(50):  # bytecode runs here: a handler that is not held off would run now
                time.sleep(0.002)
            real(root, payload, created)
        with mock.patch.object(logbook, "_append_bytes", side_effect=signalled):
            append(self.root, entry())
        self.assertEqual(seen, [False])  # once, and only after the intent was removed
        self.assert_intact()

    def test_ctrl_c_during_a_write_interrupts_only_after_it(self):
        real = logbook._record_hash

        def interrupted(root, expected):
            os.kill(os.getpid(), signal.SIGINT)
            time.sleep(0.05)  # Python would run the handler here if it were not held off
            real(root, expected)
        with mock.patch.object(logbook, "_record_hash", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                append(self.root, entry())
        self.assertIs(signal.getsignal(signal.SIGINT), signal.default_int_handler)
        self.assert_intact()
        self.assertEqual(self.added(), ["one thing"])

    def test_a_signal_during_a_failed_write_is_still_delivered(self):
        def fails(*_a):
            os.kill(os.getpid(), signal.SIGINT)
            raise OSError("disk full")
        with mock.patch.object(logbook, "_write_intent", side_effect=fails):
            with self.assertRaises(KeyboardInterrupt):
                append(self.root, entry())
        self.assertFalse(self.path.exists())
        self.assertFalse(self.pending.exists())


# ============================================================ real processes


class RealProcessTests(CrashBase):
    """`python -m umwayi check` held between two steps of its write by a planted fault, then signalled."""

    def setUp(self):
        super().setUp()
        (self.root / "rules.yaml").write_text(RULES, encoding="utf-8")
        site = self.root.parent / (self.root.name + "-site")
        site.mkdir()
        self.addCleanup(lambda: __import__("shutil").rmtree(site, ignore_errors=True))
        (site / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
        self.site = site

    def env(self, fault=None, pause="1"):
        env = {k: v for k, v in os.environ.items() if k not in ("UMWAYI_FAULT", "PYTHONPATH")}
        env["PYTHONPATH"] = os.pathsep.join([str(self.site), str(REPO)])
        if fault:
            env["UMWAYI_FAULT"] = f"umwayi.logbook:{fault}"
            env["UMWAYI_FAULT_PAUSE"] = pause
        return env

    def start(self, fault=None, **kw):
        p = subprocess.Popen([sys.executable, "-m", "umwayi", "--root", str(self.root), "check", '{"type": "read"}',
                              "--date", "2026-11-10"], env=self.env(fault, **kw), cwd=self.root,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: (p.poll() is None and p.kill(), p.communicate(timeout=30)))
        return p

    def check(self):
        p = self.start()
        out, err = p.communicate(timeout=60)
        self.assertEqual(p.returncode, 0, out + err)

    def wait(self, cond, what, p):
        end = time.monotonic() + 30
        while time.monotonic() < end:
            if cond():
                return
            if p.poll() is not None:
                self.fail(f"umwayi check exited ({p.returncode}) before {what}: {p.communicate()}")
            time.sleep(0.01)
        self.fail(f"timed out waiting for {what}")

    def intent_kind(self):
        try:
            intent = logbook._parse_intent(self.pending.read_bytes())
        except OSError:
            return None
        return intent.kind if intent else None

    def held_write(self):
        """Wait until a umwayi check is between its append and its record."""
        size = self.path.stat().st_size if self.path.exists() else 0
        return lambda: self.pending.exists() and self.path.exists() and self.path.stat().st_size > size

    def test_each_signal_during_a_held_write_leaves_a_whole_write_and_no_intent(self):
        for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT, signal.SIGQUIT):
            with self.subTest(signal=sig.name):
                self.check()
                n = len(self.added())
                p = self.start("_record_hash:pause", pause="1")
                self.wait(self.held_write(), "the held write", p)
                p.send_signal(sig)
                p.wait(timeout=30)
                self.assertNotEqual(p.returncode, 0)  # it ends by the signal, after the write
                self.assertEqual(len(self.added()), n + 1)
                self.assertEqual(self.recoveries(), [])
                self.assert_intact()

    def test_sigkill_at_each_step_is_recovered_by_the_next_write_with_one_entry(self):
        expected = {"_append_bytes": "never written", "_record_hash": "written in full",
                    "_drop_intent": "written in full"}
        for step, words in expected.items():
            with self.subTest(step=step):
                for f in (self.path, self.rec, self.pending):
                    f.unlink(missing_ok=True)
                self.check()
                size = self.path.stat().st_size
                p = self.start(f"{step}:hang")
                if step == "_append_bytes":
                    self.wait(self.pending.exists, "the intent", p)
                elif step == "_record_hash":
                    self.wait(self.held_write(), "the append", p)
                else:
                    self.wait(lambda: self.pending.exists() and self.rec.exists()
                              and self.rec.read_text().strip() == logbook.sha256_hex(self.path.read_bytes())
                              and self.path.stat().st_size > size, "the record", p)
                p.kill()
                p.wait(timeout=30)
                self.check()
                [rec] = self.recoveries()
                self.assertIn(words, rec.added)
                self.assertIn(f"(writer PID {p.pid}, started ", rec.added)
                self.assertEqual(len(self.added()), 3 + (step != "_append_bytes") + 1)  # L13.3 (13.R7.2): the rules are logged before their first use
                self.assert_intact()

    def test_two_writers_started_at_once_after_a_crash_write_one_recovery_entry(self):
        self.check()
        p = self.start("_record_hash:hang")
        self.wait(self.held_write(), "the append", p)
        p.kill()
        p.wait(timeout=30)
        procs = [self.start(), self.start()]  # each waits up to 3 s for the other's lock
        for q in procs:
            out, err = q.communicate(timeout=60)
            self.assertEqual(q.returncode, 0, out + err)
        self.assertEqual(len(self.recoveries()), 1)
        self.assertEqual(len(self.added()), 6)  # L13.3 (13.R7.2): the rules are logged before their first use
        self.assert_intact()

    def test_a_recovery_sigkilled_half_way_still_leaves_one_recovery_entry(self):
        self.check()
        p = self.start("_record_hash:hang")
        self.wait(self.held_write(), "the append", p)
        p.kill()
        p.wait(timeout=30)
        size = self.path.stat().st_size
        q = self.start("_record_hash:hang")  # its first write is the recovery: held between append and record
        self.wait(lambda: self.intent_kind() == "recover" and self.path.stat().st_size > size, "the recovery append", q)
        q.kill()
        q.wait(timeout=30)
        self.check()
        self.assertEqual(len(self.recoveries()), 1)
        self.assert_intact()


if __name__ == "__main__":
    unittest.main()
