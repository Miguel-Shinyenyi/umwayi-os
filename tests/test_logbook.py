import ast
import io
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import entry_text, hold_logbook_lock, logbook_lock_held, without_logbook_lock, write_sealed_logbook
from umwayi import logbook
from umwayi.cli import main
from umwayi.errors import UmwayiError
from umwayi.logbook import Entry, append, parse, render

REPO = Path(__file__).resolve().parent.parent

BASE = "# Logbook\n" + entry_text(date="2026-01-01") + entry_text(date="2026-01-02")
SECRET = "TOPSECRETLINETEXT"


def entry(**kw):
    base = dict(date="2026-11-07", source="umwayi test", added="one thing", checked="a check", not_done="nothing else")
    base.update(kw)
    return Entry(**base)


class LogbookBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.path = self.root / "LOGBOOK.md"
        self.rec = self.root / ".umwayi" / "logbook.sha256"
        self.lock = self.root / ".umwayi" / "logbook.lock"
        patcher = mock.patch.object(logbook, "LOCK_WAIT_SECONDS", 0)
        patcher.start()
        self.addCleanup(patcher.stop)

    def snap(self):
        """Every file and its bytes and mtime, without the logbook lock file (kept by design, holds no data)."""
        out = {}
        for dp, _dn, fn in os.walk(self.root):
            for f in fn:
                full = os.path.join(dp, f)
                out[os.path.relpath(full, self.root)] = (Path(full).read_bytes(), os.stat(full).st_mtime_ns)
        return without_logbook_lock(out)

    def run_cli(self, *argv, clock="2026-11-07"):
        out, err = io.StringIO(), io.StringIO()
        old = sys.stderr
        sys.stderr = err
        try:
            with mock.patch("umwayi.cli._today", return_value=clock):
                code = main(["--root", str(self.root), "logbook", *argv], out=out)
        finally:
            sys.stderr = old
        return code, out.getvalue(), err.getvalue()

    def refuse(self, e, fragment):
        before = self.snap()
        with self.assertRaises(UmwayiError) as cm:
            append(self.root, e)
        self.assertIn(fragment, str(cm.exception))
        self.assertEqual(self.snap(), before, "a refused append changed something")


# =================================================================== render


class RenderTests(unittest.TestCase):
    def test_render_exact(self):
        self.assertEqual(
            render(entry()),
            "\n## 2026-11-07\n\n- Source: umwayi test\n- Added: one thing\n- Checked: a check\n- Not done: nothing else\n",
        )

    def test_rejects_bad_entries(self):
        for e in [
            entry(date="2026-13-45"), entry(date="07-11-2026"), entry(date="2026-11-7"),
            entry(added=""), entry(checked="   "), entry(source="line one\nline two"),
            entry(not_done="tab\there"), entry(added=" leading space"), entry(added="trailing space "),
        ]:
            with self.subTest(e=e):
                with self.assertRaises(UmwayiError):
                    render(e)


# ===================================================================== parse


class ParseTests(unittest.TestCase):
    def test_valid_logbook(self):
        entries, problems = parse(BASE)
        self.assertEqual(problems, [])
        self.assertEqual([(p.line, p.entry.date) for p in entries], [(3, "2026-01-01"), (10, "2026-01-02")])
        self.assertEqual(entries[0].entry.source, "hand")

    def test_header_only_is_valid(self):
        self.assertEqual(parse("# Logbook\n"), ([], []))

    def test_equal_dates_are_fine(self):
        text = "# Logbook\n" + entry_text(date="2026-01-01") + entry_text(date="2026-01-01")
        self.assertEqual(parse(text)[1], [])

    def where(self, text):
        return [p.where for p in parse(text)[1]]

    def lines(self):
        return BASE.split("\n")

    def test_a_deleted_line(self):
        ls = self.lines()
        del ls[6]  # the Checked line of the first entry (line 7)
        self.assertIn("line 7", self.where("\n".join(ls)))

    def test_every_single_deleted_line_is_detected(self):
        ls = self.lines()[:-1]  # drop the final empty piece after the last newline
        for i in range(len(ls)):
            with self.subTest(deleted_line=i + 1):
                text = "\n".join(ls[:i] + ls[i + 1:]) + "\n"
                self.assertNotEqual(parse(text)[1], [], "deleting a line went unnoticed")

    def test_partial_entry_cut_off_in_the_last_field(self):
        ls = self.lines()
        text = "\n".join(ls[:14]) + "\n"  # the last entry loses its Not done line
        self.assertEqual(self.where(text), ["line 14"])
        self.assertIn("Not done", parse(text)[1][0].message)

    def test_partial_entry_cut_off_mid_line(self):
        text = BASE[:-5]
        problems = parse(text)[1]
        self.assertTrue(problems)
        self.assertTrue(any("newline" in p.message for p in problems))

    def test_entry_cut_off_right_after_the_heading(self):
        problems = parse("# Logbook\n\n## 2026-01-01\n")[1]
        self.assertEqual([p.where for p in problems], ["line 3"])
        self.assertIn("cut off", problems[0].message)

    def test_missing_field_in_every_position(self):
        for label in ("Source", "Added", "Checked", "Not done"):
            with self.subTest(label=label):
                text = "\n".join(l for l in BASE.split("\n") if not l.startswith(f"- {label}:")) 
                self.assertNotEqual(parse(text)[1], [])

    def test_fields_out_of_order(self):
        ls = self.lines()
        ls[4], ls[5] = ls[5], ls[4]
        self.assertIn("line 5", self.where("\n".join(ls)))

    def test_text_after_an_entry(self):
        self.assertEqual(self.where(BASE + f"{SECRET}\n"), ["line 16"])

    def test_text_between_the_header_and_the_first_entry(self):
        ls = self.lines()
        ls.insert(1, SECRET)
        self.assertEqual(self.where("\n".join(ls)), ["line 2"])

    def test_text_outside_when_there_are_no_entries(self):
        self.assertEqual(self.where(f"# Logbook\n{SECRET}\n"), ["line 2"])

    def test_missing_blank_line_between_entries(self):
        ls = self.lines()
        del ls[8]  # the blank line before the second heading
        self.assertIn("line 8", self.where("\n".join(ls)))

    def test_extra_blank_line_is_a_problem(self):
        ls = self.lines()
        ls.insert(8, "")
        self.assertNotEqual(parse("\n".join(ls))[1], [])

    def test_bad_headings(self):
        for heading in ("## 2026-13-45", "## 2026-1-1", "##2026-01-01", "## 2026-01-01 extra", "## ", "### 2026-01-01"):
            with self.subTest(heading=heading):
                text = BASE.replace("## 2026-01-01", heading, 1)
                self.assertIn("line 3", self.where(text))

    def test_a_backwards_date(self):
        text = "# Logbook\n" + entry_text(date="2026-01-02") + entry_text(date="2026-01-01")
        problems = parse(text)[1]
        self.assertEqual([p.where for p in problems], ["line 10"])
        self.assertIn("backwards", problems[0].message)

    def test_one_backwards_entry_does_not_hide_the_next_good_one(self):
        text = "# Logbook\n" + entry_text(date="2026-01-05") + entry_text(date="2026-01-01") + entry_text(date="2026-01-06")
        self.assertEqual(len(parse(text)[1]), 1)

    def test_wrong_header_and_empty_file(self):
        self.assertIn("line 1", self.where(BASE.replace("# Logbook", "# My logbook", 1)))
        self.assertTrue(parse("")[1])
        self.assertTrue(parse("\n")[1])

    def test_empty_or_untidy_values(self):
        self.assertNotEqual(parse(BASE.replace("- Added: x", "- Added:", 1))[1], [])
        self.assertNotEqual(parse(BASE.replace("- Added: x", "- Added: ", 1))[1], [])
        self.assertNotEqual(parse(BASE.replace("- Added: x", "- Added: x ", 1))[1], [])
        self.assertNotEqual(parse(BASE.replace("- Added: x", "- Added:  x", 1))[1], [])
        self.assertNotEqual(parse(BASE.replace("- Added: x", "- added: x", 1))[1], [])

    def test_windows_line_endings(self):
        self.assertNotEqual(parse(BASE.replace("\n", "\r\n"))[1], [])

    def test_problems_never_contain_line_text(self):
        bad = BASE.replace("- Added: x", f"- Added: x{SECRET}", 1).replace("- Checked: y", f"{SECRET} stray", 1)
        bad += f"{SECRET} at the end\n"
        for p in parse(bad)[1]:
            self.assertNotIn(SECRET, p.render())


# ===================================================================== append


class AppendTests(LogbookBase):
    def test_creates_file_with_header_entry_and_record(self):
        append(self.root, entry())
        self.assertEqual(
            self.path.read_text(encoding="utf-8"),
            "# Logbook\n\n## 2026-11-07\n\n- Source: umwayi test\n- Added: one thing\n"
            "- Checked: a check\n- Not done: nothing else\n",
        )
        self.assertEqual(self.rec.read_text(encoding="ascii"), logbook.sha256_hex(self.path.read_bytes()) + "\n")
        self.assertEqual(parse(self.path.read_text(encoding="utf-8"))[1], [])

    def test_every_append_keeps_earlier_bytes_and_updates_the_record(self):
        seen = b""
        for n in range(1, 6):
            append(self.root, entry(date=f"2026-11-0{n}", added=f"thing {n}"))
            now = self.path.read_bytes()
            self.assertTrue(now.startswith(seen))
            self.assertEqual(self.rec.read_text(encoding="ascii").strip(), logbook.sha256_hex(now))
            seen = now
        self.assertEqual(len(parse(seen.decode())[0]), 5)

    def test_record_and_logbook_get_normal_permissions(self):
        import stat
        append(self.root, entry())
        mask = os.umask(0)
        os.umask(mask)
        for p in (self.path, self.rec):
            self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o666 & ~mask)

    def test_no_intent_or_temp_file_left_behind_and_the_lock_is_free(self):
        append(self.root, entry())
        self.assertEqual(sorted(p.name for p in (self.root / ".umwayi").iterdir()), ["logbook.lock", "logbook.sha256"])
        self.assertFalse(logbook_lock_held(self.root))

    # -- tamper check

    def sealed_base(self):
        write_sealed_logbook(self.root, BASE)

    def test_a_sealed_logbook_accepts_appends(self):
        self.sealed_base()
        append(self.root, entry(date="2026-02-01"))
        self.assertEqual(len(parse(self.path.read_text(encoding="utf-8"))[0]), 3)

    def test_hand_edit_of_an_earlier_line_is_refused(self):
        self.sealed_base()
        edited = BASE.replace("- Added: x", "- Added: y", 1)
        self.path.write_text(edited, encoding="utf-8")
        self.refuse(entry(date="2026-02-01"), "does not match its recorded hash")
        self.assertEqual(self.path.read_text(encoding="utf-8"), edited)

    def test_one_character_edit_is_refused(self):
        self.sealed_base()
        self.path.write_bytes(BASE.encode().replace(b"hand", b"hanD", 1))
        self.refuse(entry(date="2026-02-01"), "does not match")

    def test_deleted_line_is_refused(self):
        self.sealed_base()
        ls = BASE.split("\n")
        del ls[6]
        self.path.write_text("\n".join(ls), encoding="utf-8")
        self.refuse(entry(date="2026-02-01"), "does not match")

    def test_deleted_entry_is_refused(self):
        self.sealed_base()
        self.path.write_text("# Logbook\n" + entry_text(date="2026-01-01"), encoding="utf-8")
        self.refuse(entry(date="2026-02-01"), "does not match")

    def test_line_added_by_hand_at_the_end_is_refused(self):
        self.sealed_base()
        self.path.write_text(BASE + "- sneaky\n", encoding="utf-8")
        self.refuse(entry(date="2026-02-01"), "does not match")

    def test_replaced_logbook_is_refused(self):
        self.sealed_base()
        self.path.write_text("# Logbook\n", encoding="utf-8")
        self.refuse(entry(date="2026-02-01"), "does not match")

    def test_emptied_logbook_is_refused_when_a_record_exists(self):
        self.sealed_base()
        self.path.write_bytes(b"")
        self.refuse(entry(date="2026-02-01"), "does not match")

    def test_missing_record_for_an_existing_logbook_is_refused(self):
        self.path.write_text(BASE, encoding="utf-8")
        self.refuse(entry(date="2026-02-01"), "no hash record")
        self.assertFalse(self.rec.exists())  # and it was not created or sealed automatically

    def test_message_names_the_seal_command(self):
        self.path.write_text(BASE, encoding="utf-8")
        with self.assertRaises(UmwayiError) as cm:
            append(self.root, entry(date="2026-02-01"))
        self.assertIn("umwayi logbook seal", str(cm.exception))

    def test_deleted_logbook_with_a_record_is_refused(self):
        self.sealed_base()
        self.path.unlink()
        self.refuse(entry(date="2026-02-01"), "may have been deleted")
        self.assertFalse(self.path.exists())

    def test_bad_record_files_are_refused(self):
        self.sealed_base()
        good = self.rec.read_bytes()
        for name, content in {
            "garbage": b"not a hash\n",
            "short": b"abc\n",
            "uppercase": good.upper(),
            "two lines": good + good,
            "empty": b"",
            "binary": b"\xff\xfe\x00",
        }.items():
            with self.subTest(name=name):
                self.rec.write_bytes(content)
                self.refuse(entry(date="2026-02-01"), "malformed")
        self.rec.unlink()
        self.rec.mkdir()
        self.refuse(entry(date="2026-02-01"), "malformed")
        self.rec.rmdir()
        other = self.root / "elsewhere"
        other.write_bytes(good)
        try:
            self.rec.symlink_to(other)
        except (OSError, NotImplementedError):
            return
        self.refuse(entry(date="2026-02-01"), "malformed")

    def test_wrong_hash_in_the_record_is_refused(self):
        self.sealed_base()
        self.rec.write_text("0" * 64 + "\n", encoding="ascii")
        self.refuse(entry(date="2026-02-01"), "does not match")

    def test_empty_file_with_no_record_is_just_a_new_logbook(self):
        self.path.write_bytes(b"")
        append(self.root, entry())
        self.assertTrue(self.path.read_text(encoding="utf-8").startswith("# Logbook\n"))

    def test_symlinked_logbook_refused(self):
        target = self.root / "real.md"
        target.write_text("keep\n", encoding="utf-8")
        try:
            self.path.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not supported")
        self.refuse(entry(), "symbolic link")

    def test_directory_in_the_way(self):
        self.path.mkdir()
        self.refuse(entry(), "cannot be read")

    def test_invalid_utf8_logbook(self):
        write_sealed_logbook(self.root, "x")
        self.path.write_bytes(b"\xff\xfe")
        self.rec.write_text(logbook.sha256_hex(b"\xff\xfe") + "\n", encoding="ascii")
        self.refuse(entry(), "not valid UTF-8")

    # -- format and dates

    def test_sealed_but_malformed_logbook_is_refused(self):
        write_sealed_logbook(self.root, BASE + f"{SECRET}\n")
        with self.assertRaises(UmwayiError) as cm:
            append(self.root, entry(date="2026-02-01"))
        self.assertIn("format problem", str(cm.exception))
        self.assertNotIn(SECRET, str(cm.exception))

    def test_backwards_date_is_refused(self):
        write_sealed_logbook(self.root, BASE)
        self.refuse(entry(date="2026-01-01"), "before the date of the last entry (2026-01-02)")

    def test_same_date_is_fine(self):
        write_sealed_logbook(self.root, BASE)
        append(self.root, entry(date="2026-01-02"))

    def test_bad_entry_writes_nothing(self):
        for bad in (entry(date="2026-02-30"), entry(added="")):
            with self.subTest(bad=bad):
                with self.assertRaises(UmwayiError):
                    append(self.root, bad)
                self.assertFalse(self.path.exists())
                self.assertFalse(self.rec.exists())

    # -- failures in the middle

    def test_failed_record_write_is_finished_by_the_next_append_with_one_recovery_entry(self):
        append(self.root, entry(date="2026-01-01"))
        real = logbook.atomic_write

        def record_fails(path, data):
            if Path(path) == self.rec:
                raise OSError("disk full")
            return real(path, data)
        with mock.patch("umwayi.logbook.atomic_write", side_effect=record_fails):
            with self.assertRaises(UmwayiError) as cm:
                append(self.root, entry(date="2026-01-02", added="the second"))
        self.assertIn("could not be recorded", str(cm.exception))
        self.assertTrue((self.root / ".umwayi" / "logbook.pending").exists())  # the intent stays
        self.assertEqual(logbook.verify(self.root).problems, [])  # the exact completed state reads as consistent
        append(self.root, entry(date="2026-01-03", added="the third"))
        added = [e.added for e in logbook.read_checked(self.root)]
        self.assertEqual(added[:2], ["one thing", "the second"])
        self.assertTrue(added[2].startswith("Recovered an interrupted logbook write (writer PID "), added[2])
        self.assertIn("the entry was written in full and its hash is now recorded", added[2])
        self.assertEqual(added[3], "the third")
        self.assertFalse((self.root / ".umwayi" / "logbook.pending").exists())
        self.assertEqual(logbook.verify(self.root).problems, [])

    def test_failed_append_write_is_an_error_and_releases_the_lock(self):
        with mock.patch("builtins.open", side_effect=OSError("nope")):
            with self.assertRaises(UmwayiError) as cm:
                append(self.root, entry())
        self.assertIn("Nothing was written", str(cm.exception))
        self.assertFalse(logbook_lock_held(self.root))
        self.assertFalse((self.root / ".umwayi" / "logbook.pending").exists())  # nothing was appended: no intent left

    def test_lock_is_released_after_a_refusal(self):
        write_sealed_logbook(self.root, BASE)
        self.path.write_text(BASE + "x\n", encoding="utf-8")
        with self.assertRaises(UmwayiError):
            append(self.root, entry(date="2026-02-01"))
        self.assertFalse(logbook_lock_held(self.root))

    def test_cannot_forge_a_second_entry_with_a_line_break(self):
        with self.assertRaises(UmwayiError):
            append(self.root, entry(added="x\n\n## 2020-01-01\n- Source: forged"))
        self.assertFalse(self.path.exists())

    def test_state_folder_in_the_way(self):
        (self.root / ".umwayi").write_text("i am a file", encoding="utf-8")
        self.refuse(entry(), ".umwayi must be a normal folder")


# ====================================================================== lock


class LockTests(LogbookBase):
    """The lock is fcntl.flock on .umwayi/logbook.lock (L5.1): held only while a writer runs, never deleted."""

    def hold(self):
        release = hold_logbook_lock(self.root)
        self.addCleanup(release)
        return release

    def test_held_lock_refuses_with_a_clear_message_and_changes_nothing(self):
        append(self.root, entry(date="2026-01-01"))
        self.hold()
        before = self.snap()
        with self.assertRaises(UmwayiError) as cm:
            append(self.root, entry(date="2026-01-02"))
        msg = str(cm.exception)
        self.assertIn("another umwayi command (PID 4242) holds the logbook lock (.umwayi/logbook.lock)", msg)
        self.assertIn("Nothing was written", msg)
        self.assertNotIn("delete", msg)  # the owner is never told to delete the lock file any more
        self.assertEqual(self.snap(), before)
        self.assertTrue(self.lock.exists())

    def test_seal_and_check_writable_also_respect_the_lock(self):
        self.path.write_text(BASE, encoding="utf-8")
        self.hold()
        with self.assertRaises(UmwayiError) as cm:
            logbook.seal(self.root, "2026-02-01", "me")
        self.assertIn("another umwayi command", str(cm.exception))
        with self.assertRaises(UmwayiError):
            logbook.check_writable(self.root, "2026-02-01")

    def test_waits_for_a_lock_that_is_released(self):
        release = self.hold()
        threading.Timer(0.15, release).start()
        with mock.patch.object(logbook, "LOCK_WAIT_SECONDS", 3):
            append(self.root, entry())
        self.assertEqual(len(parse(self.path.read_text(encoding="utf-8"))[0]), 1)

    def test_gives_up_after_the_wait(self):
        self.hold()
        start = time.monotonic()
        with mock.patch.object(logbook, "LOCK_WAIT_SECONDS", 0.2):
            with self.assertRaises(UmwayiError):
                append(self.root, entry())
        self.assertGreaterEqual(time.monotonic() - start, 0.2)

    def test_a_lock_file_left_by_an_old_umwayi_or_a_dead_writer_does_not_block(self):
        (self.root / ".umwayi").mkdir()
        self.lock.write_text("4242\n", encoding="ascii")  # the old lock file of a killed writer: nobody holds it
        append(self.root, entry())
        self.assertEqual(logbook.verify(self.root).problems, [])

    def test_a_writer_killed_while_holding_the_lock_does_not_block_the_next(self):
        code = ("import os, sys, time\nfrom pathlib import Path\nfrom tests.helpers import hold_logbook_lock\n"
                "hold_logbook_lock(Path(sys.argv[1]))\nprint('held', flush=True)\ntime.sleep(60)\n")
        env = dict(os.environ, PYTHONPATH=str(REPO))
        p = subprocess.Popen([sys.executable, "-c", code, str(self.root)], env=env, stdout=subprocess.PIPE, text=True)
        self.addCleanup(lambda: p.poll() is None and p.kill())
        self.assertEqual(p.stdout.readline().strip(), "held")
        self.assertTrue(logbook_lock_held(self.root))
        with self.assertRaises(UmwayiError):
            append(self.root, entry())
        p.kill()
        p.wait(timeout=30)
        p.stdout.close()
        append(self.root, entry())  # the kernel let go of the lock when the holder died
        self.assertEqual(len(logbook.read_checked(self.root)), 1)

    def test_a_replaced_lock_file_is_noticed(self):
        (self.root / ".umwayi").mkdir()
        real_flock = logbook.fcntl.flock
        calls = []

        def flock_then_replace(fd, op):
            real_flock(fd, op)
            calls.append(op)
            if len(calls) == 1:  # the first time only: someone replaces the file right after we locked it
                os.unlink(self.lock)
                self.lock.write_text("", encoding="ascii")
        with mock.patch.object(logbook.fcntl, "flock", side_effect=flock_then_replace):
            with mock.patch.object(logbook, "LOCK_WAIT_SECONDS", 3):
                append(self.root, entry())
        self.assertEqual(len(calls), 2)  # the lock on the replaced file guarded nothing, so it locked again
        self.assertEqual(len(logbook.read_checked(self.root)), 1)

    def test_no_file_locking_means_no_write(self):
        with mock.patch.object(logbook, "fcntl", None):
            with self.assertRaises(UmwayiError) as cm:
                append(self.root, entry())
        self.assertIn("file locking is not available", str(cm.exception))
        self.assertFalse(self.path.exists())

    def test_a_write_from_another_thread_is_refused_and_writes_nothing(self):
        errors = []

        def work():
            try:
                append(self.root, entry())
            except UmwayiError as e:
                errors.append(str(e))
        t = threading.Thread(target=work)
        t.start()
        t.join()
        self.assertEqual(len(errors), 1)
        self.assertIn("a logbook write must run in the main thread. Nothing was written.", errors[0])
        self.assertFalse(self.path.exists())
        self.assertFalse((self.root / ".umwayi" / "logbook.pending").exists())
        self.assertFalse(logbook_lock_held(self.root))

    def test_processes_appending_at_once_do_not_interleave(self):
        code = (
            "import sys\n"
            "from pathlib import Path\n"
            "from umwayi import logbook\n"
            "logbook.LOCK_WAIT_SECONDS = 60\n"
            "w = sys.argv[2]\n"
            "for i in range(5):\n"
            "    logbook.append(Path(sys.argv[1]), logbook.Entry('2026-11-07', 's', f'proc {w} item {i}', 'c', 'n'))\n"
        )
        env = dict(os.environ, PYTHONPATH=str(REPO))
        procs = [
            subprocess.Popen([sys.executable, "-c", code, str(self.root), str(w)], env=env, stderr=subprocess.PIPE)
            for w in range(4)
        ]
        for p in procs:
            _out, err = p.communicate(timeout=120)
            self.assertEqual(p.returncode, 0, err.decode())
        entries, problems = parse(self.path.read_text(encoding="utf-8"))
        self.assertEqual(problems, [])
        self.assertEqual(len(entries), 20)
        self.assertEqual(logbook.verify(self.root).problems, [])
        self.assertFalse(logbook_lock_held(self.root))


# ====================================================================== seal


class SealTests(LogbookBase):
    def test_seals_a_logbook_with_no_record(self):
        self.path.write_text(BASE, encoding="utf-8")
        old_hash = logbook.sha256_hex(BASE.encode())
        r = logbook.seal(self.root, "2026-02-01", "Miguel")
        self.assertEqual(r.entries_before, 2)
        text = self.path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(BASE))
        self.assertEqual(
            text[len(BASE):],
            "\n## 2026-02-01\n\n- Source: umwayi logbook seal\n"
            f"- Added: Seal by Miguel: the logbook was sealed with 2 earlier entries; its SHA-256 before this entry was {old_hash}\n"
            "- Checked: the format of every earlier entry is valid and no date goes backwards; the earlier hash record was missing\n"
            "- Not done: The earlier entries were not rewritten or judged. Sealing records what the file holds now, "
            "it does not prove the file was never edited before.\n",
        )
        self.assertEqual(self.rec.read_text(encoding="ascii").strip(), r.sha256)
        self.assertEqual(r.sha256, logbook.sha256_hex(self.path.read_bytes()))
        self.assertEqual(logbook.verify(self.root).problems, [])
        append(self.root, entry(date="2026-02-02"))  # appends work after sealing

    def test_never_seals_automatically(self):
        self.path.write_text(BASE, encoding="utf-8")
        before = self.snap()
        for action in (lambda: append(self.root, entry(date="2026-02-01")), lambda: logbook.verify(self.root)):
            try:
                action()
            except UmwayiError:
                pass
        self.assertEqual(self.snap(), before)
        self.assertFalse(self.rec.exists())

    def test_seals_after_a_hand_edit_and_says_so(self):
        write_sealed_logbook(self.root, BASE)
        edited = BASE.replace("- Added: x", "- Added: changed by hand", 1)
        self.path.write_text(edited, encoding="utf-8")
        logbook.seal(self.root, "2026-02-01", "Miguel")
        self.assertIn("did not match the file (earlier lines may have been edited by hand)", self.path.read_text(encoding="utf-8"))
        self.assertEqual(logbook.verify(self.root).problems, [])

    def test_seals_a_malformed_record(self):
        write_sealed_logbook(self.root, BASE)
        self.rec.write_text("junk", encoding="utf-8")
        logbook.seal(self.root, "2026-02-01", "Miguel")
        self.assertIn("record was malformed", self.path.read_text(encoding="utf-8"))

    def test_refusals_change_nothing(self):
        cases = []
        # nothing to seal
        cases.append(("no logbook", lambda: None, ("2026-02-01", "me"), "no logbook to seal"))
        # already sealed and intact
        cases.append(("intact", lambda: write_sealed_logbook(self.root, BASE), ("2026-02-01", "me"), "already sealed and intact"))
        # format problems
        cases.append(("broken format", lambda: self.path.write_text(BASE + f"{SECRET}\n", encoding="utf-8"), ("2026-02-01", "me"), "cannot be sealed"))
        # backwards date
        cases.append(("backwards", lambda: self.path.write_text(BASE, encoding="utf-8"), ("2026-01-01", "me"), "before the date of the last entry"))
        # bad inputs
        for by in ("", "   ", "x" * 101, "two\nlines"):
            cases.append((f"by={by[:6]!r}", lambda: self.path.write_text(BASE, encoding="utf-8"), ("2026-02-01", by), "--by must be"))
        cases.append(("bad date", lambda: self.path.write_text(BASE, encoding="utf-8"), ("2026-02-30", "me"), "real date"))
        for name, setup, args, fragment in cases:
            with self.subTest(name=name):
                import shutil
                shutil.rmtree(self.root / ".umwayi", ignore_errors=True)
                if self.path.exists():
                    self.path.unlink()
                setup()
                before = self.snap()
                with self.assertRaises(UmwayiError) as cm:
                    logbook.seal(self.root, *args)
                self.assertIn(fragment, str(cm.exception))
                self.assertNotIn(SECRET, str(cm.exception))
                self.assertEqual(self.snap(), before)

    def test_deleted_logbook_with_a_record_cannot_be_sealed(self):
        write_sealed_logbook(self.root, BASE)
        self.path.unlink()
        with self.assertRaises(UmwayiError):
            logbook.seal(self.root, "2026-02-01", "me")
        self.assertFalse(self.path.exists())

    def test_header_only_logbook_can_be_sealed(self):
        self.path.write_text("# Logbook\n", encoding="utf-8")
        r = logbook.seal(self.root, "2026-02-01", "me")
        self.assertEqual(r.entries_before, 0)


# ==================================================================== verify


class VerifyTests(LogbookBase):
    def test_ok(self):
        write_sealed_logbook(self.root, BASE)
        report = logbook.verify(self.root)
        self.assertEqual((report.entries, report.problems), (2, []))

    def test_problems_for_missing_logbook_and_record(self):
        self.assertEqual([p.where for p in logbook.verify(self.root).problems], ["file"])
        self.path.write_text(BASE, encoding="utf-8")
        self.assertEqual([p.where for p in logbook.verify(self.root).problems], ["record"])
        self.rec.parent.mkdir()
        self.rec.write_text("0" * 64 + "\n", encoding="ascii")
        self.assertIn("recorded hash", logbook.verify(self.root).problems[0].message)

    def test_invalid_utf8_and_symlink_and_directory(self):
        self.path.write_bytes(b"\xff\xfe")
        self.assertTrue(logbook.verify(self.root).problems)
        self.path.unlink()
        self.path.mkdir()
        self.assertTrue(logbook.verify(self.root).problems)

    def test_never_changes_any_file_in_any_state(self):
        states = [
            lambda: None,
            lambda: write_sealed_logbook(self.root, BASE),
            lambda: self.path.write_text(BASE + "stray\n", encoding="utf-8"),
            lambda: self.path.unlink(),
            lambda: (self.root / ".umwayi" / "logbook.sha256").write_text("junk"),
        ]
        for i, setup in enumerate(states):
            with self.subTest(state=i):
                setup()
                before = self.snap()
                logbook.verify(self.root)
                self.assertEqual(self.snap(), before)
        self.assertFalse(self.lock.exists())

    def test_does_not_create_the_state_folder(self):
        self.path.write_text(BASE, encoding="utf-8")
        logbook.verify(self.root)
        self.assertFalse((self.root / ".umwayi").exists())

    def test_reports_every_problem_with_line_numbers_and_no_content(self):
        ls = BASE.split("\n")
        ls[4] = f"- Source{SECRET}"
        ls[13] = f"{SECRET}"
        write_sealed_logbook(self.root, "\n".join(ls))
        report = logbook.verify(self.root)
        self.assertGreaterEqual(len(report.problems), 2)
        for p in report.problems:
            self.assertNotIn(SECRET, p.render())
        self.assertTrue(all(p.where.startswith("line ") for p in report.problems))


class CliTests(LogbookBase):
    def test_verify_ok_and_problem_exit_codes(self):
        write_sealed_logbook(self.root, BASE)
        code, out, err = self.run_cli("verify")
        self.assertEqual((code, err), (0, ""))
        self.assertTrue(out.startswith("ok: 2 entries"))
        self.path.write_text(BASE.replace("- Added: x", f"- Added: x {SECRET}", 1), encoding="utf-8")
        before = self.snap()
        code, out, _ = self.run_cli("verify")
        self.assertEqual(code, 1)
        self.assertIn("problem: record:", out)
        self.assertIn("1 problem(s) found", out)
        self.assertNotIn(SECRET, out)
        self.assertEqual(self.snap(), before)

    def test_verify_line_problems_are_printed_with_line_numbers(self):
        write_sealed_logbook(self.root, BASE + f"{SECRET}\n")
        code, out, _ = self.run_cli("verify")
        self.assertEqual(code, 1)
        self.assertIn("problem: line 16: unexpected text after the entry", out)
        self.assertNotIn(SECRET, out)

    def test_seal_cli(self):
        self.path.write_text(BASE, encoding="utf-8")
        code, out, _ = self.run_cli("seal", "--by", "Miguel")
        self.assertEqual(code, 0)
        self.assertIn("Sealed LOGBOOK.md: 2 earlier entries", out)
        self.assertIn("## 2026-11-07", self.path.read_text(encoding="utf-8"))
        code, _, err = self.run_cli("seal", "--by", "Miguel")
        self.assertEqual(code, 1)
        self.assertIn("already sealed", err)

    def test_seal_explicit_date(self):
        self.path.write_text(BASE, encoding="utf-8")
        self.run_cli("seal", "--by", "Miguel", "--date", "2026-03-04")
        self.assertIn("## 2026-03-04", self.path.read_text(encoding="utf-8"))

    def test_usage_errors(self):
        for argv in (["seal"], ["seal", "--by", "x", "--date", "2026-02-30"], [], ["verify", "--fix"], ["frobnicate"]):
            with self.subTest(argv=argv):
                self.assertEqual(self.run_cli(*argv)[0], 64)
        self.assertFalse(self.path.exists())

    def test_real_process(self):
        env = dict(os.environ, PYTHONPATH=str(REPO))
        self.path.write_text(BASE, encoding="utf-8")

        def run(*a):
            return subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "logbook", *a],
                                  capture_output=True, text=True, env=env, cwd=self.root)
        self.assertEqual(run("verify").returncode, 1)
        self.assertEqual(run("seal", "--by", "me", "--date", "2026-05-01").returncode, 0)
        self.assertEqual(run("verify").returncode, 0)
        self.path.write_text(self.path.read_text().replace("hand", "HAND", 1), encoding="utf-8")
        self.assertEqual(run("verify").returncode, 1)


# ================================================================ code guards


class CodeGuardTests(unittest.TestCase):
    def test_the_logbook_file_is_only_read_or_appended(self):
        tree = ast.parse(Path(logbook.__file__).read_text(encoding="utf-8"))
        modes = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
                mode = node.args[1] if len(node.args) > 1 else None
                modes.add(mode.value if isinstance(mode, ast.Constant) else None)
        self.assertEqual(modes, {"ab"})

    def test_the_only_replace_writes_go_to_the_record(self):
        src = Path(logbook.__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        targets = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "atomic_write":
                arg = node.args[0]
                targets.append(arg.func.id if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name) else None)
        self.assertEqual(sorted(targets), ["pending_path", "record_path"])  # the intent (L5.2) and the record
        for word in ("write_text", "write_bytes", "os.replace", "rename", "shutil"):
            self.assertNotIn(word, src)

    def test_bytes_are_cut_only_in_the_torn_tail_command(self):
        tree = ast.parse(Path(logbook.__file__).read_text(encoding="utf-8"))
        where = []
        for fn in ast.walk(tree):
            if isinstance(fn, ast.FunctionDef):
                for node in ast.walk(fn):
                    if isinstance(node, ast.Attribute) and node.attr in ("truncate", "ftruncate"):
                        where.append(fn.name)
        self.assertEqual(where, ["_cut_torn_tail"])

    def test_no_network_imports(self):
        src = Path(logbook.__file__).read_text(encoding="utf-8")
        for mod in ("socket", "urllib", "http", "requests", "smtplib"):
            self.assertNotRegex(src, rf"(?m)^\s*(import|from) {mod}\b")  # (?m): every line, not only the first


# ================================================================ id reader


class LoggedIdsTests(LogbookBase):
    def test_logged_ids(self):
        self.assertEqual(logbook.logged_ids(self.root), set())  # no logbook yet
        self.path.write_text(
            "# Logbook\n\n## 2026-11-07\n\n- Source: s\n- Added: Q-0003 (task) as open: see Q-0099 here\n"
            "- Checked: Q-0042 mentioned here\n- Not done: n\n"
            "- Added: Q-0010 closed on 2026-11-08\n"
            "  - Added: Q-0500 indented, not an entry line\n"
            "- Added: Q-12 too short\n"
            "- Added: Q-00007 five digits\n",
            encoding="utf-8",
        )
        self.assertEqual(logbook.logged_ids(self.root), {3, 10, 7})

    def test_logged_ids_by_prefix(self):
        self.path.write_text(
            "# Logbook\n- Added: Q-0003 (task) x\n- Added: A-0007 moved from a.md\n- Added: A-0002 moved\n",
            encoding="utf-8",
        )
        self.assertEqual(logbook.logged_ids(self.root), {3})
        self.assertEqual(logbook.logged_ids(self.root, "Q"), {3})
        self.assertEqual(logbook.logged_ids(self.root, "A"), {7, 2})
        for bad in ("", "a", "AB", "A-", ".*", "A|Q"):
            with self.assertRaises(UmwayiError):
                logbook.logged_ids(self.root, bad)

    def test_logged_ids_unreadable_is_an_error_not_an_empty_set(self):
        self.path.mkdir()
        with self.assertRaises(UmwayiError):
            logbook.logged_ids(self.root)
        self.path.rmdir()
        self.path.write_bytes(b"\xff\xfe")
        with self.assertRaises(UmwayiError):
            logbook.logged_ids(self.root)

    def test_logged_ids_does_not_change_the_file(self):
        append(self.root, entry(added="Q-0001 (task) as open: x"))
        before = self.snap()
        self.assertEqual(logbook.logged_ids(self.root), {1})
        self.assertEqual(self.snap(), before)


if __name__ == "__main__":
    unittest.main()
