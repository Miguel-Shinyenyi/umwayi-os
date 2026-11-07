import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from umwayi import taskqueue
from umwayi.cli import main
from umwayi.errors import UmwayiError
from umwayi.taskqueue import parse

REPO = Path(__file__).resolve().parent.parent

HEADER = "| id | kind | title | status | recommendation | answered |\n| --- | --- | --- | --- | --- | --- |\n"

# a hand-edited file: prose, odd padding, a later date in the LAST row
HAND = (
    "# Queue\n"
    "\n"
    "My own notes here. Keep them.\n"
    "\n"
    "| id | kind | title | status | recommendation | answered |\n"
    "|----|------|-------|--------|----------------|----------|\n"
    "| Q-0001 |  task     | Pay no one            | open     |   none   |            |\n"
    "|Q-0002|decision|Pick a name|answered|Use umwayi|2026-11-05|\n"
    "| Q-0007 | task | Old thing | closed | | 2026-12-30 |\n"
    "\n"
    "Notes after the table stay too.\n"
)


class QueueBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.q = self.root / "queue.md"
        self.log = self.root / "LOGBOOK.md"

    def put(self, text):
        self.q.write_bytes(text.encode("utf-8"))

    def qtext(self):
        return self.q.read_bytes().decode("utf-8")

    def logtext(self):
        return self.log.read_text(encoding="utf-8") if self.log.exists() else ""

    def run_cli(self, *argv, clock="2026-11-07"):
        out = io.StringIO()
        err = io.StringIO()
        old = sys.stderr
        sys.stderr = err
        try:
            with mock.patch("umwayi.cli._today", return_value=clock):
                code = main(["--root", str(self.root), "queue", *argv], out=out)
        finally:
            sys.stderr = old
        return code, out.getvalue(), err.getvalue()


class ParserTests(unittest.TestCase):
    def test_parses_hand_edited_file(self):
        doc = parse(HAND)
        self.assertEqual([r.id for r in doc.rows], ["Q-0001", "Q-0002", "Q-0007"])
        self.assertEqual(doc.rows[0].recommendation, "none")
        self.assertEqual(doc.rows[1].answered, "2026-11-05")
        self.assertEqual(doc.text(), HAND)  # round trip is exact

    def test_empty_table_is_valid(self):
        self.assertEqual(parse(HEADER).rows, [])

    def test_header_case_is_forgiven_but_not_names(self):
        parse(HEADER.replace("| id |", "| ID |"))
        with self.assertRaises(UmwayiError):
            parse(HEADER.replace("recommendation", "advice"))

    def test_malformed_files(self):
        row = "| Q-0001 | task | t | open | | |\n"
        bad = {
            "empty file": "",
            "no table": "# Queue\n\njust words\n",
            "header only line": "| id | kind | title | status | recommendation | answered |\n",
            "wrong columns": HEADER.replace(" | answered", "") + row,
            "bad separator": HEADER.replace("| --- | --- | --- | --- | --- | --- |", "| a | b | c | d | e | f |") + row,
            "two tables": HEADER + row + "\ntext\n\n" + HEADER,
            "too few cells": HEADER + "| Q-0001 | task | t | open | |\n",
            "too many cells": HEADER + "| Q-0001 | task | t | open | | | extra |\n",
            "pipe in title": HEADER + "| Q-0001 | task | a | b | open | | |\n",
            "bad id": HEADER + "| X-1 | task | t | open | | |\n",
            "short id": HEADER + "| Q-1 | task | t | open | | |\n",
            "bad kind": HEADER + "| Q-0001 | chore | t | open | | |\n",
            "bad status": HEADER + "| Q-0001 | task | t | done | | |\n",
            "empty title": HEADER + "| Q-0001 | task | | open | | |\n",
            "bad date": HEADER + "| Q-0001 | task | t | answered | | 2026-02-30 |\n",
            "date format": HEADER + "| Q-0001 | task | t | answered | | 11/05/2026 |\n",
            "answered without date": HEADER + "| Q-0001 | task | t | answered | | |\n",
            "open with date": HEADER + "| Q-0001 | task | t | open | | 2026-11-05 |\n",
            "duplicate id": HEADER + row + row,
            "row without pipes at end": HEADER + "| Q-0001 | task | t | open | | \n",
            "indented table line": HEADER + "  | Q-0001 | task | t | open | | |\n",
            "crlf": (HEADER + row).replace("\n", "\r\n"),
            "nul": HEADER + row + "\x00",
        }
        for name, text in bad.items():
            with self.subTest(name=name):
                with self.assertRaises(UmwayiError):
                    parse(text)

    def test_errors_carry_line_numbers_but_not_content(self):
        text = HEADER + "| Q-0001 | task | SECRETTITLE | nonsense | | |\n"
        with self.assertRaises(UmwayiError) as cm:
            parse(text)
        self.assertIn("line 3", str(cm.exception))
        self.assertNotIn("SECRETTITLE", str(cm.exception))
        self.assertNotIn("nonsense", str(cm.exception))


class ListTests(QueueBase):
    def test_list_all_and_filters(self):
        self.put(HAND)
        code, out, _ = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertEqual(len(out.strip().splitlines()), 3)
        self.assertIn("Q-0001", out)
        self.assertIn("[recommendation: none]", out)
        _, out, _ = self.run_cli("list", "--status", "closed")
        self.assertEqual([l.split()[0] for l in out.splitlines()], ["Q-0007"])
        _, out, _ = self.run_cli("list", "--kind", "decision")
        self.assertEqual([l.split()[0] for l in out.splitlines()], ["Q-0002"])
        _, out, _ = self.run_cli("list", "--kind", "decision", "--status", "open")
        self.assertEqual(out, "No rows.\n")

    def test_list_changes_nothing(self):
        self.put(HAND)
        before = self.q.stat().st_mtime_ns
        self.run_cli("list")
        self.assertEqual(self.qtext(), HAND)
        self.assertEqual(self.q.stat().st_mtime_ns, before)
        self.assertFalse(self.log.exists())

    def test_list_missing_file_is_error(self):
        code, out, err = self.run_cli("list")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("queue.md was not found", err)
        self.assertFalse(self.q.exists())

    def test_list_malformed_is_error(self):
        self.put(HEADER + "| Q-0001 | task | t | bogus | | |\n")
        code, out, err = self.run_cli("list")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("line 3", err)


class AddTests(QueueBase):
    def test_add_creates_file_and_logbook(self):
        code, out, _ = self.run_cli("add", "--kind", "task", "Write the spec", "--recommendation", "Do it today")
        self.assertEqual(code, 0)
        self.assertIn("Added Q-0001", out)
        doc = parse(self.qtext())
        self.assertEqual(len(doc.rows), 1)
        r = doc.rows[0]
        self.assertEqual((r.id, r.kind, r.title, r.status, r.recommendation, r.answered),
                         ("Q-0001", "task", "Write the spec", "open", "Do it today", ""))
        self.assertTrue(self.qtext().startswith("# Queue\n"))

    def test_add_logbook_line(self):
        self.run_cli("add", "--kind", "decision", "Pick a name")
        self.assertEqual(
            self.logtext(),
            "# Logbook\n\n## 2026-11-07\n\n- Source: umwayi queue add\n"
            "- Added: Q-0001 (decision) as open: Pick a name\n"
            "- Checked: queue.md did not exist, so it was created from the template; "
            "Q-0001 was not in use; text has no | character or line break\n"
            "- Not done: No other row was changed. Nothing was sent or published.\n",
        )

    def test_ids_count_up_from_the_highest_even_with_gaps_and_closed_rows(self):
        self.put(HAND)  # highest is Q-0007, which is closed
        self.run_cli("add", "--kind", "task", "Next")
        self.run_cli("add", "--kind", "task", "After")
        self.assertEqual([r.id for r in parse(self.qtext()).rows], ["Q-0001", "Q-0002", "Q-0007", "Q-0008", "Q-0009"])

    def test_add_leaves_every_other_byte_alone(self):
        self.put(HAND)
        self.run_cli("add", "--kind", "task", "Brand new")
        new = self.qtext()
        lines = new.split("\n")
        old_lines = HAND.split("\n")
        # old text with exactly one inserted line, right after the last table row
        self.assertEqual(lines[:9], old_lines[:9])
        self.assertEqual(lines[9], "| Q-0008 | task | Brand new | open |  |  |")
        self.assertEqual(lines[10:], old_lines[9:])
        self.assertEqual(lines.count("Notes after the table stay too."), 1)

    def test_add_logbook_for_existing_file(self):
        self.put(HAND)
        self.run_cli("add", "--kind", "task", "Brand new", clock="2026-11-08")
        self.assertIn("## 2026-11-08", self.logtext())
        self.assertIn("queue.md parsed with no errors (3 rows before); Q-0008 was not in use", self.logtext())

    def test_add_file_without_final_newline(self):
        self.put((HEADER + "| Q-0001 | task | t | open | | |").rstrip("\n"))
        self.run_cli("add", "--kind", "task", "two")
        text = self.qtext()
        self.assertTrue(text.startswith(HEADER + "| Q-0001 | task | t | open | | |\n| Q-0002 |"))
        self.assertEqual([r.id for r in parse(text).rows], ["Q-0001", "Q-0002"])

    def test_add_rejects_bad_text_and_changes_nothing(self):
        self.put(HAND)
        for title in ["", "   ", "has | pipe", "two\nlines", "tab\there", "x" * 201]:
            with self.subTest(title=title):
                code, _, err = self.run_cli("add", "--kind", "task", title)
                self.assertEqual(code, 1)
                self.assertEqual(self.qtext(), HAND)
                self.assertFalse(self.log.exists())
        code, _, _ = self.run_cli("add", "--kind", "task", "ok", "--recommendation", "bad | pipe")
        self.assertEqual(code, 1)
        self.assertEqual(self.qtext(), HAND)

    def test_add_to_malformed_file_changes_nothing(self):
        bad = HEADER + "| Q-0001 | task | t | bogus | | |\n"
        self.put(bad)
        code, _, err = self.run_cli("add", "--kind", "task", "x")
        self.assertEqual(code, 1)
        self.assertIn("line 3", err)
        self.assertEqual(self.qtext(), bad)
        self.assertFalse(self.log.exists())

    def test_usage_errors(self):
        for argv in (["add", "title"], ["add", "--kind", "chore", "t"], ["add", "--kind", "task"],
                     ["add", "--kind", "task", "t", "--date", "2026-02-30"],
                     ["add", "--kind", "task", "t", "--date", "tomorrow"]):
            with self.subTest(argv=argv):
                self.assertEqual(self.run_cli(*argv)[0], 64)
        self.assertFalse(self.q.exists())

    def test_explicit_date_beats_clock(self):
        self.run_cli("add", "--kind", "task", "t", "--date", "2027-01-02", clock="2026-11-07")
        self.assertIn("## 2027-01-02", self.logtext())
        self.assertNotIn("2026-11-07", self.logtext())

    def test_symlinked_queue_refused(self):
        real = self.root / "real.md"
        real.write_text(HEADER, encoding="utf-8")
        try:
            self.q.symlink_to(real)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not supported")
        self.assertEqual(self.run_cli("add", "--kind", "task", "t")[0], 1)
        self.assertEqual(real.read_text(encoding="utf-8"), HEADER)


class AnswerTests(QueueBase):
    def test_answer_sets_status_and_date_and_touches_only_that_row(self):
        self.put(HAND)
        code, out, _ = self.run_cli("answer", "Q-0001")
        self.assertEqual(code, 0)
        self.assertIn("Answered Q-0001 on 2026-11-07", out)
        old, new = HAND.split("\n"), self.qtext().split("\n")
        self.assertEqual(new[6], "| Q-0001 | task | Pay no one | answered | none | 2026-11-07 |")
        self.assertEqual(new[:6] + new[7:], old[:6] + old[7:])  # all other lines identical

    def test_answer_date_comes_from_clock_not_last_row(self):
        self.put(HAND)  # last row says 2026-12-30
        self.run_cli("answer", "Q-0001", clock="2026-11-07")
        self.assertEqual(parse(self.qtext()).rows[0].answered, "2026-11-07")

    def test_answer_explicit_date(self):
        self.put(HAND)
        self.run_cli("answer", "Q-0001", "--date", "2026-10-01")
        self.assertEqual(parse(self.qtext()).rows[0].answered, "2026-10-01")
        self.assertIn("## 2026-10-01", self.logtext())

    def test_answer_logbook_line(self):
        self.put(HAND)
        self.run_cli("answer", "Q-0001")
        self.assertEqual(
            self.logtext(),
            "# Logbook\n\n## 2026-11-07\n\n- Source: umwayi queue answer\n"
            "- Added: Q-0001 marked answered on 2026-11-07 (status open to answered)\n"
            "- Checked: queue.md parsed with no errors (3 rows); Q-0001 exists and was open\n"
            "- Not done: No other row was changed. The text of the answer is not stored in queue.md.\n",
        )

    def test_answer_errors_change_nothing(self):
        self.put(HAND)
        for argv, fragment in [
            (["answer", "Q-0099"], "no row with id Q-0099"),
            (["answer", "Q-0002"], "only an open row can be answered"),  # already answered
            (["answer", "Q-0007"], "only an open row can be answered"),  # closed
            (["answer", "q-0001"], "id must look like"),
            (["answer", "1"], "id must look like"),
            (["answer", "Q-0001; rm"], "id must look like"),
        ]:
            with self.subTest(argv=argv):
                code, out, err = self.run_cli(*argv)
                self.assertEqual((code, out), (1, ""))
                self.assertIn(fragment, err)
                self.assertEqual(self.qtext(), HAND)
                self.assertFalse(self.log.exists())

    def test_answer_malformed_file(self):
        bad = HEADER + "| Q-0001 | task | t | open | | |\n| oops |\n"
        self.put(bad)
        code, _, err = self.run_cli("answer", "Q-0001")
        self.assertEqual(code, 1)
        self.assertEqual(self.qtext(), bad)
        self.assertFalse(self.log.exists())

    def test_answer_missing_file(self):
        code, _, err = self.run_cli("answer", "Q-0001")
        self.assertEqual(code, 1)
        self.assertFalse(self.q.exists())
        self.assertFalse(self.log.exists())


class CloseTests(QueueBase):
    def test_close_open_row(self):
        self.put(HAND)
        code, out, _ = self.run_cli("close", "Q-0001")
        self.assertEqual((code, out), (0, "Closed Q-0001\n"))
        new = self.qtext().split("\n")
        self.assertEqual(new[6], "| Q-0001 | task | Pay no one | closed | none |  |")
        old = HAND.split("\n")
        self.assertEqual(new[:6] + new[7:], old[:6] + old[7:])

    def test_close_answered_row_keeps_its_date(self):
        self.put(HAND)
        self.run_cli("close", "Q-0002", "--date", "2026-11-09")
        r = parse(self.qtext()).rows[1]
        self.assertEqual((r.status, r.answered), ("closed", "2026-11-05"))
        self.assertIn("## 2026-11-09", self.logtext())

    def test_close_logbook_line(self):
        self.put(HAND)
        self.run_cli("close", "Q-0002")
        self.assertEqual(
            self.logtext(),
            "# Logbook\n\n## 2026-11-07\n\n- Source: umwayi queue close\n"
            "- Added: Q-0002 closed on 2026-11-07 (status answered to closed)\n"
            "- Checked: queue.md parsed with no errors (3 rows); Q-0002 exists and was answered\n"
            "- Not done: No other row was changed. The date answered was left as it was.\n",
        )

    def test_close_errors_change_nothing(self):
        self.put(HAND)
        for argv, fragment in [
            (["close", "Q-0099"], "no row with id Q-0099"),
            (["close", "Q-0007"], "already closed"),
            (["close", "nonsense"], "id must look like"),
        ]:
            with self.subTest(argv=argv):
                code, out, err = self.run_cli(*argv)
                self.assertEqual((code, out), (1, ""))
                self.assertIn(fragment, err)
                self.assertEqual(self.qtext(), HAND)
                self.assertFalse(self.log.exists())

    def test_close_malformed_file(self):
        bad = "# Queue\n\nno table\n"
        self.put(bad)
        self.assertEqual(self.run_cli("close", "Q-0001")[0], 1)
        self.assertEqual(self.qtext(), bad)
        self.assertFalse(self.log.exists())


class LogbookCouplingTests(QueueBase):
    def test_each_change_appends_exactly_one_entry_and_never_edits_earlier_text(self):
        self.log.write_text("# Logbook\n\n## 2026-01-01\n\n- hand written entry\n", encoding="utf-8")
        seen = self.logtext()
        steps = [
            ("add", "--kind", "task", "one"),
            ("add", "--kind", "decision", "two"),
            ("answer", "Q-0002"),
            ("close", "Q-0001"),
            ("close", "Q-0002"),
        ]
        for n, argv in enumerate(steps, 1):
            self.assertEqual(self.run_cli(*argv)[0], 0)
            now = self.logtext()
            self.assertTrue(now.startswith(seen))
            self.assertEqual(now.count("\n## "), 1 + n)
            seen = now

    def test_failed_commands_write_no_entry(self):
        self.put(HAND)
        self.run_cli("answer", "Q-0099")
        self.run_cli("close", "Q-0007")
        self.assertFalse(self.log.exists())

    def test_logbook_failure_rolls_back_an_existing_queue(self):
        self.put(HAND)
        self.log.mkdir()  # appending to a directory fails
        for argv in (["add", "--kind", "task", "x"], ["answer", "Q-0001"], ["close", "Q-0001"]):
            with self.subTest(argv=argv):
                code, _, err = self.run_cli(*argv)
                self.assertEqual(code, 1)
                self.assertIn("undone", err)
                self.assertEqual(self.qtext(), HAND)

    def test_logbook_failure_rolls_back_a_new_queue(self):
        self.log.mkdir()
        code, _, _ = self.run_cli("add", "--kind", "task", "x")
        self.assertEqual(code, 1)
        self.assertFalse(self.q.exists())

    def test_rollback_failure_is_reported_loudly(self):
        self.put(HAND)
        real = taskqueue._atomic_write
        calls = {"n": 0}

        def flaky(path, data):
            calls["n"] += 1
            if calls["n"] == 2:  # the restore
                raise OSError("disk gone")
            return real(path, data)

        self.log.mkdir()
        with mock.patch("umwayi.taskqueue._atomic_write", flaky):
            code, _, err = self.run_cli("close", "Q-0001")
        self.assertEqual(code, 1)
        self.assertIn("could not be restored", err)

    def test_no_temp_files_left_behind(self):
        self.put(HAND)
        self.run_cli("add", "--kind", "task", "x")
        self.run_cli("answer", "Q-0001")
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["LOGBOOK.md", "queue.md"])


class SubprocessTests(QueueBase):
    def test_real_process_round_trip(self):
        env = dict(os.environ, PYTHONPATH=str(REPO))

        def run(*argv):
            return subprocess.run(
                [sys.executable, "-m", "umwayi", "--root", str(self.root), "queue", *argv],
                capture_output=True, text=True, env=env, cwd=self.root,
            )

        self.assertEqual(run("add", "--kind", "task", "Real run", "--date", "2026-11-07").returncode, 0)
        self.assertEqual(run("answer", "Q-0001", "--date", "2026-11-08").returncode, 0)
        self.assertEqual(run("close", "Q-0001", "--date", "2026-11-09").returncode, 0)
        r = run("list")
        self.assertEqual(r.returncode, 0)
        self.assertIn("closed", r.stdout)
        self.assertEqual(run("close", "Q-0001").returncode, 1)
        self.assertEqual(self.logtext().count("\n## "), 3)
        # with no --date the real system clock is used
        run("add", "--kind", "task", "Clock run")
        from datetime import date
        self.assertIn(f"## {date.today().isoformat()}", self.logtext())


if __name__ == "__main__":
    unittest.main()
