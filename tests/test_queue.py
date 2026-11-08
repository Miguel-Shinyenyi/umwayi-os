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
from tests.helpers import entry_text, write_sealed_logbook
from umwayi.taskqueue import MIGRATED_ANSWER, Row, format_row, parse

REPO = Path(__file__).resolve().parent.parent

HEADER = (
    "| id | kind | title | status | recommendation | answer | answered |\n"
    "| --- | --- | --- | --- | --- | --- | --- |\n"
)
OLD_HEADER = (
    "| id | kind | title | status | recommendation | answered |\n"
    "| --- | --- | --- | --- | --- | --- |\n"
)

# a hand-edited file: prose, odd padding, a later date in the LAST row
HAND = (
    "# Queue\n"
    "\n"
    "My own notes here. Keep them.\n"
    "\n"
    "| id | kind | title | status | recommendation | answer | answered |\n"
    "|----|------|-------|--------|----------------|--------|----------|\n"
    "| Q-0001 |  task     | Pay no one            | open     |   none   |   |            |\n"
    "|Q-0002|decision|Pick a name|answered|Use umwayi|Go with umwayi|2026-11-05|\n"
    "| Q-0007 | task | Old thing | closed | | | 2026-12-30 |\n"
    "\n"
    "Notes after the table stay too.\n"
)

# the same file in the old six column layout
OLD_HAND = (
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

    def ids(self):
        return [r.id for r in parse(self.qtext()).rows]


# ================================================================ parser


class ParserTests(unittest.TestCase):
    def test_parses_hand_edited_file(self):
        doc = parse(HAND)
        self.assertEqual([r.id for r in doc.rows], ["Q-0001", "Q-0002", "Q-0007"])
        self.assertEqual(doc.rows[0].recommendation, "none")
        self.assertEqual(doc.rows[0].answer, "")
        self.assertEqual(doc.rows[1].answer, "Go with umwayi")
        self.assertEqual(doc.rows[1].answered, "2026-11-05")
        self.assertEqual(doc.text(), HAND)  # round trip is exact

    def test_empty_table_is_valid(self):
        self.assertEqual(parse(HEADER).rows, [])

    def test_header_case_is_forgiven_but_not_names(self):
        parse(HEADER.replace("| id |", "| ID |"))
        with self.assertRaises(UmwayiError):
            parse(HEADER.replace("recommendation", "advice"))
        with self.assertRaises(UmwayiError):  # answer column in the wrong place
            parse(HEADER.replace("answer | answered", "answered | answer"))

    def test_malformed_files(self):
        row = "| Q-0001 | task | t | open | | | |\n"
        bad = {
            "empty file": "",
            "no table": "# Queue\n\njust words\n",
            "header only line": "| id | kind | title | status | recommendation | answer | answered |\n",
            "missing title column": HEADER.replace(" title |", "") + row,
            "bad separator": HEADER.replace("| --- | --- | --- | --- | --- | --- | --- |", "| a | b | c | d | e | f | g |") + row,
            "two tables": HEADER + row + "\ntext\n\n" + HEADER,
            "too few cells": HEADER + "| Q-0001 | task | t | open | | |\n",
            "too many cells": HEADER + "| Q-0001 | task | t | open | | | | extra |\n",
            "six cells in a seven column table": HEADER + "| Q-0001 | task | t | open | | |\n",
            "bad id": HEADER + "| X-1 | task | t | open | | | |\n",
            "short id": HEADER + "| Q-1 | task | t | open | | | |\n",
            "bad kind": HEADER + "| Q-0001 | chore | t | open | | | |\n",
            "bad status": HEADER + "| Q-0001 | task | t | done | | | |\n",
            "empty title": HEADER + "| Q-0001 | task | | open | | | |\n",
            "bad date": HEADER + "| Q-0001 | task | t | answered | | yes | 2026-02-30 |\n",
            "date format": HEADER + "| Q-0001 | task | t | answered | | yes | 11/05/2026 |\n",
            "answered without date": HEADER + "| Q-0001 | task | t | answered | | yes | |\n",
            "answered without answer": HEADER + "| Q-0001 | task | t | answered | | | 2026-11-05 |\n",
            "open with date": HEADER + "| Q-0001 | task | t | open | | | 2026-11-05 |\n",
            "open with answer": HEADER + "| Q-0001 | task | t | open | | sneaky | |\n",
            "duplicate id": HEADER + row + row,
            "row without pipes at end": HEADER + "| Q-0001 | task | t | open | | | \n",
            "indented table line": HEADER + "  | Q-0001 | task | t | open | | | |\n",
            "crlf": (HEADER + row).replace("\n", "\r\n"),
            "nul": HEADER + row + "\x00",
        }
        for name, text in bad.items():
            with self.subTest(name=name):
                with self.assertRaises(UmwayiError):
                    parse(text)

    def test_closed_rows_keep_whatever_they_had(self):
        for tail in ("| | |", "| why | |", "| why | 2026-11-05 |", "| | 2026-11-05 |"):
            with self.subTest(tail=tail):
                doc = parse(HEADER + f"| Q-0001 | task | t | closed | rec {tail}\n")
                self.assertEqual(doc.rows[0].status, "closed")

    def test_old_layout_is_refused_and_names_the_migration_step(self):
        with self.assertRaises(UmwayiError) as cm:
            parse(OLD_HAND)
        self.assertIn("old six column layout", str(cm.exception))
        self.assertIn("umwayi queue migrate", str(cm.exception))

    def test_errors_carry_line_numbers_but_not_content(self):
        text = HEADER + "| Q-0001 | task | SECRETTITLE | nonsense | | | |\n"
        with self.assertRaises(UmwayiError) as cm:
            parse(text)
        self.assertIn("line 3", str(cm.exception))
        self.assertNotIn("SECRETTITLE", str(cm.exception))
        self.assertNotIn("nonsense", str(cm.exception))

    def test_legacy_parse_rejects_the_current_layout(self):
        with self.assertRaises(UmwayiError):
            parse(HAND, legacy=True)
        self.assertEqual(len(parse(OLD_HAND, legacy=True).rows), 3)


# ================================================================== list


class ListTests(QueueBase):
    def test_list_all_and_filters(self):
        self.put(HAND)
        code, out, _ = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertEqual(len(out.strip().splitlines()), 3)
        self.assertIn("[recommendation: none]", out)
        self.assertIn("[answer: Go with umwayi]", out)
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
        self.put(HEADER + "| Q-0001 | task | t | bogus | | | |\n")
        code, out, err = self.run_cli("list")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("line 3", err)


# =================================================================== add


class AddTests(QueueBase):
    def test_add_creates_file_and_logbook(self):
        code, out, _ = self.run_cli("add", "--kind", "task", "Write the spec", "--recommendation", "Do it today")
        self.assertEqual(code, 0)
        self.assertIn("Added Q-0001", out)
        doc = parse(self.qtext())
        self.assertEqual(doc.rows, [Row("Q-0001", "task", "Write the spec", "open", "Do it today", "", "")])
        self.assertTrue(self.qtext().startswith("# Queue\n"))
        self.assertIn("| id | kind | title | status | recommendation | answer | answered |", self.qtext())

    def test_add_logbook_line(self):
        self.run_cli("add", "--kind", "decision", "Pick a name")
        self.assertEqual(
            self.logtext(),
            "# Logbook\n\n## 2026-11-07\n\n- Source: umwayi queue add\n"
            "- Added: Q-0001 (decision) as open: Pick a name\n"
            "- Checked: queue.md did not exist, so it was created from the template; "
            "Q-0001 is one more than the highest id in queue.md and the logbook; "
            "text has no | character or line break\n"
            "- Not done: No other row was changed. Nothing was sent or published.\n",
        )

    def test_new_row_has_empty_answer_and_date(self):
        self.put(HAND)
        self.run_cli("add", "--kind", "task", "Brand new")
        r = parse(self.qtext()).rows[-1]
        self.assertEqual((r.status, r.answer, r.answered), ("open", "", ""))

    def test_add_leaves_every_other_byte_alone(self):
        self.put(HAND)
        self.run_cli("add", "--kind", "task", "Brand new")
        lines = self.qtext().split("\n")
        old_lines = HAND.split("\n")
        self.assertEqual(lines[:9], old_lines[:9])
        self.assertEqual(lines[9], "| Q-0008 | task | Brand new | open |  |  |  |")
        self.assertEqual(lines[10:], old_lines[9:])

    def test_add_logbook_for_existing_file(self):
        self.put(HAND)
        self.run_cli("add", "--kind", "task", "Brand new", clock="2026-11-08")
        self.assertIn("## 2026-11-08", self.logtext())
        self.assertIn("queue.md parsed with no errors (3 rows before); Q-0008 is one more than", self.logtext())

    def test_add_file_without_final_newline(self):
        self.put((HEADER + "| Q-0001 | task | t | open | | | |").rstrip("\n"))
        self.run_cli("add", "--kind", "task", "two")
        text = self.qtext()
        self.assertTrue(text.startswith(HEADER + "| Q-0001 | task | t | open | | | |\n| Q-0002 |"))
        self.assertEqual(self.ids(), ["Q-0001", "Q-0002"])

    def test_add_rejects_bad_text_and_changes_nothing(self):
        self.put(HAND)
        for title, fragment in [
            ("", "title must not be empty"),
            ("   ", "title must not be empty"),
            ("has | pipe", "title must not contain the | character"),
            ("two\nlines", "title must be one line of plain text"),
            ("tab\there", "title must be one line of plain text"),
            ("x" * 201, "title is longer than 200 characters"),
        ]:
            with self.subTest(title=title[:12]):
                code, _, err = self.run_cli("add", "--kind", "task", title)
                self.assertEqual(code, 64)
                self.assertIn(fragment, err)
                self.assertEqual(self.qtext(), HAND)
                self.assertFalse(self.log.exists())
        code, _, err = self.run_cli("add", "--kind", "task", "ok", "--recommendation", "bad | pipe")
        self.assertEqual(code, 64)
        self.assertIn("recommendation must not contain the | character", err)
        self.assertEqual(self.qtext(), HAND)

    def test_add_to_malformed_file_changes_nothing(self):
        bad = HEADER + "| Q-0001 | task | t | bogus | | | |\n"
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


# ============================================================ id reuse


class IdReuseTests(QueueBase):
    def add(self, title="x"):
        code, out, err = self.run_cli("add", "--kind", "task", title)
        self.assertEqual(code, 0, err)

    def test_highest_id_in_queue_plus_one_even_with_gaps_and_closed_rows(self):
        self.put(HAND)  # highest is Q-0007, which is closed
        self.add("Next")
        self.add("After")
        self.assertEqual(self.ids(), ["Q-0001", "Q-0002", "Q-0007", "Q-0008", "Q-0009"])

    def test_id_not_reused_after_the_last_row_is_deleted_by_hand(self):
        self.add("one")
        self.add("two")
        self.assertEqual(self.ids(), ["Q-0001", "Q-0002"])
        # the owner deletes the LAST row by hand
        kept = [l for l in self.qtext().split("\n") if "| Q-0002 |" not in l]
        self.q.write_text("\n".join(kept), encoding="utf-8")
        self.assertEqual(self.ids(), ["Q-0001"])
        self.add("three")
        self.assertEqual(self.ids(), ["Q-0001", "Q-0003"])  # not Q-0002 again

    def test_id_not_reused_after_all_rows_are_deleted_by_hand(self):
        self.add("one")
        self.add("two")
        kept = [l for l in self.qtext().split("\n") if not l.startswith("| Q-")]
        self.q.write_text("\n".join(kept), encoding="utf-8")
        self.assertEqual(self.ids(), [])
        self.add("three")
        self.assertEqual(self.ids(), ["Q-0003"])

    def test_id_not_reused_after_queue_md_is_deleted(self):
        self.add("one")
        self.add("two")
        self.q.unlink()
        self.add("three")
        self.assertEqual(self.ids(), ["Q-0003"])

    def test_logbook_with_a_higher_id_than_the_queue_wins(self):
        self.put(HAND)
        write_sealed_logbook(self.root, "# Logbook\n" + entry_text(added="Q-0050 (task) as open: from an older queue"))
        self.add("new")
        self.assertEqual(self.ids()[-1], "Q-0051")

    def test_queue_with_a_higher_id_than_the_logbook_wins(self):
        self.put(HAND)
        self.add("new")  # logbook only knows Q-0008 after this; queue also has Q-0007
        self.assertEqual(self.ids()[-1], "Q-0008")

    def test_ids_in_titles_do_not_inflate_the_counter(self):
        self.add("see Q-9999 and Q-0500 later")
        self.add("two")
        self.assertEqual(self.ids(), ["Q-0001", "Q-0002"])

    def test_answered_and_closed_entries_also_count(self):
        self.add("one")
        self.run_cli("answer", "Q-0001", "--answer", "yes")
        self.run_cli("close", "Q-0001")
        self.q.unlink()
        self.add("again")
        self.assertEqual(self.ids(), ["Q-0002"])

    def test_missing_logbook_is_fine(self):
        self.put(HAND)
        self.assertFalse(self.log.exists())
        self.add("new")
        self.assertEqual(self.ids()[-1], "Q-0008")

    def test_unreadable_logbook_refuses_to_add_and_says_why(self):
        self.put(HAND)
        # directory
        self.log.mkdir()
        code, out, err = self.run_cli("add", "--kind", "task", "x")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("cannot add", err)
        self.assertIn("never reused", err)
        self.assertIn("cannot be read", err)
        self.assertEqual(self.qtext(), HAND)
        self.log.rmdir()
        # invalid UTF-8
        self.log.write_bytes(b"# Logbook\n\xff\xfe\n")
        code, _, err = self.run_cli("add", "--kind", "task", "x")
        self.assertEqual(code, 1)
        self.assertIn("not valid UTF-8", err)
        self.assertEqual(self.qtext(), HAND)
        self.assertEqual(self.log.read_bytes(), b"# Logbook\n\xff\xfe\n")
        self.log.unlink()
        # symlink
        target = self.root / "elsewhere.md"
        target.write_text("# Logbook\n", encoding="utf-8")
        try:
            self.log.symlink_to(target)
        except (OSError, NotImplementedError):
            return
        code, _, err = self.run_cli("add", "--kind", "task", "x")
        self.assertEqual(code, 1)
        self.assertIn("symbolic link", err)
        self.assertEqual(self.qtext(), HAND)

    def test_unreadable_logbook_does_not_create_queue_md(self):
        self.log.mkdir()
        code, _, _ = self.run_cli("add", "--kind", "task", "x")
        self.assertEqual(code, 1)
        self.assertFalse(self.q.exists())


# ================================================================ answer


class AnswerTests(QueueBase):
    def test_answer_stores_text_status_and_date_and_touches_only_that_row(self):
        self.put(HAND)
        code, out, _ = self.run_cli("answer", "Q-0001", "--answer", "Yes, go ahead")
        self.assertEqual(code, 0)
        self.assertIn("Answered Q-0001 on 2026-11-07", out)
        old, new = HAND.split("\n"), self.qtext().split("\n")
        self.assertEqual(new[6], "| Q-0001 | task | Pay no one | answered | none | Yes, go ahead | 2026-11-07 |")
        self.assertEqual(new[:6] + new[7:], old[:6] + old[7:])

    def test_answer_is_required(self):
        self.put(HAND)
        self.assertEqual(self.run_cli("answer", "Q-0001")[0], 64)
        self.assertEqual(self.qtext(), HAND)
        self.assertFalse(self.log.exists())

    def test_answer_text_limits(self):
        self.put(HAND)
        for text, fragment in [
            ("", "answer must not be empty"),
            ("   ", "answer must not be empty"),
            ("a | b", "answer must not contain the | character"),
            ("two\nlines", "answer must be one line of plain text"),
            ("tab\there", "answer must be one line of plain text"),
            ("x" * 501, "answer is longer than 500 characters"),
        ]:
            with self.subTest(text=text[:12]):
                code, out, err = self.run_cli("answer", "Q-0001", "--answer", text)
                self.assertEqual((code, out), (64, ""))
                self.assertIn(fragment, err)
                self.assertEqual(self.qtext(), HAND)
                self.assertFalse(self.log.exists())
        code, _, _ = self.run_cli("answer", "Q-0001", "--answer", "x" * 500)  # the limit itself is fine
        self.assertEqual(code, 0)
        self.assertEqual(parse(self.qtext()).rows[0].answer, "x" * 500)

    def test_limits_match_recommendation(self):
        self.assertEqual(taskqueue.MAX_ANSWER, taskqueue.MAX_RECOMMENDATION)

    def test_answer_date_comes_from_clock_not_last_row(self):
        self.put(HAND)  # last row says 2026-12-30
        self.run_cli("answer", "Q-0001", "--answer", "ok", clock="2026-11-07")
        self.assertEqual(parse(self.qtext()).rows[0].answered, "2026-11-07")

    def test_answer_explicit_date(self):
        self.put(HAND)
        self.run_cli("answer", "Q-0001", "--answer", "ok", "--date", "2026-10-01")
        self.assertEqual(parse(self.qtext()).rows[0].answered, "2026-10-01")
        self.assertIn("## 2026-10-01", self.logtext())

    def test_answer_logbook_line_does_not_copy_the_answer(self):
        self.put(HAND)
        self.run_cli("answer", "Q-0001", "--answer", "Private words")
        self.assertEqual(
            self.logtext(),
            "# Logbook\n\n## 2026-11-07\n\n- Source: umwayi queue answer\n"
            "- Added: Q-0001 marked answered on 2026-11-07 (status open to answered, 13 characters of answer)\n"
            "- Checked: queue.md parsed with no errors (3 rows); Q-0001 exists and was open\n"
            "- Not done: No other row was changed. The answer text is stored in queue.md and not copied here.\n",
        )
        self.assertNotIn("Private words", self.logtext())

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
                code, out, err = self.run_cli(*argv, "--answer", "x")
                self.assertEqual((code, out), (64 if "id must look like" in fragment else 1, ""))
                self.assertIn(fragment, err)
                self.assertEqual(self.qtext(), HAND)
                self.assertFalse(self.log.exists())

    def test_answer_cannot_overwrite_an_existing_answer(self):
        self.put(HAND)
        code, _, _ = self.run_cli("answer", "Q-0002", "--answer", "changed my mind")
        self.assertEqual(code, 1)
        self.assertEqual(parse(self.qtext()).rows[1].answer, "Go with umwayi")

    def test_answer_malformed_file(self):
        bad = HEADER + "| Q-0001 | task | t | open | | | |\n| oops |\n"
        self.put(bad)
        code, _, err = self.run_cli("answer", "Q-0001", "--answer", "x")
        self.assertEqual(code, 1)
        self.assertEqual(self.qtext(), bad)
        self.assertFalse(self.log.exists())

    def test_answer_missing_file(self):
        code, _, _ = self.run_cli("answer", "Q-0001", "--answer", "x")
        self.assertEqual(code, 1)
        self.assertFalse(self.q.exists())
        self.assertFalse(self.log.exists())


# ================================================================= close


class CloseTests(QueueBase):
    def test_close_open_row(self):
        self.put(HAND)
        code, out, _ = self.run_cli("close", "Q-0001")
        self.assertEqual((code, out), (0, "Closed Q-0001\n"))
        new = self.qtext().split("\n")
        self.assertEqual(new[6], "| Q-0001 | task | Pay no one | closed | none |  |  |")
        old = HAND.split("\n")
        self.assertEqual(new[:6] + new[7:], old[:6] + old[7:])

    def test_close_open_row_keeps_it_unanswered(self):
        self.put(HAND)
        self.run_cli("close", "Q-0001")
        r = parse(self.qtext()).rows[0]
        self.assertEqual((r.status, r.answer, r.answered), ("closed", "", ""))

    def test_close_answered_row_keeps_its_answer_and_date(self):
        self.put(HAND)
        self.run_cli("close", "Q-0002", "--date", "2026-11-09")
        r = parse(self.qtext()).rows[1]
        self.assertEqual((r.status, r.answer, r.answered), ("closed", "Go with umwayi", "2026-11-05"))
        self.assertIn("## 2026-11-09", self.logtext())

    def test_close_logbook_line(self):
        self.put(HAND)
        self.run_cli("close", "Q-0002")
        self.assertEqual(
            self.logtext(),
            "# Logbook\n\n## 2026-11-07\n\n- Source: umwayi queue close\n"
            "- Added: Q-0002 closed on 2026-11-07 (status answered to closed)\n"
            "- Checked: queue.md parsed with no errors (3 rows); Q-0002 exists and was answered\n"
            "- Not done: No other row was changed. The answer and the date answered were left as they were.\n",
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
                self.assertEqual((code, out), (64 if "id must look like" in fragment else 1, ""))
                self.assertIn(fragment, err)
                self.assertEqual(self.qtext(), HAND)
                self.assertFalse(self.log.exists())

    def test_close_malformed_file(self):
        bad = "# Queue\n\nno table\n"
        self.put(bad)
        self.assertEqual(self.run_cli("close", "Q-0001")[0], 1)
        self.assertEqual(self.qtext(), bad)
        self.assertFalse(self.log.exists())


# =============================================================== migrate


class MigrateTests(QueueBase):
    def test_old_layout_is_refused_by_every_command_and_nothing_changes(self):
        self.put(OLD_HAND)
        for argv in (["list"], ["add", "--kind", "task", "x"], ["answer", "Q-0001", "--answer", "x"], ["close", "Q-0001"]):
            with self.subTest(argv=argv):
                code, out, err = self.run_cli(*argv)
                self.assertEqual((code, out), (1, ""))
                self.assertIn("old six column layout", err)
                self.assertIn("umwayi queue migrate", err)
                self.assertEqual(self.qtext(), OLD_HAND)
                self.assertFalse(self.log.exists())

    def test_migrate_converts_the_file(self):
        self.put(OLD_HAND)
        code, out, _ = self.run_cli("migrate")
        self.assertEqual(code, 0)
        self.assertIn("3 rows", out)
        rows = parse(self.qtext()).rows
        self.assertEqual(
            [(r.id, r.kind, r.title, r.status, r.recommendation, r.answer, r.answered) for r in rows],
            [
                ("Q-0001", "task", "Pay no one", "open", "none", "", ""),
                ("Q-0002", "decision", "Pick a name", "answered", "Use umwayi", MIGRATED_ANSWER, "2026-11-05"),
                ("Q-0007", "task", "Old thing", "closed", "", "", "2026-12-30"),
            ],
        )

    def test_migrate_leaves_lines_outside_the_table_alone(self):
        self.put(OLD_HAND)
        self.run_cli("migrate")
        new, old = self.qtext().split("\n"), OLD_HAND.split("\n")
        self.assertEqual(new[:4], old[:4])
        self.assertEqual(new[9:], old[9:])
        self.assertEqual(new[4], taskqueue.HEADER_LINE)
        self.assertEqual(new[5], taskqueue.SEPARATOR_LINE)

    def test_migrate_logbook_line(self):
        self.put(OLD_HAND)
        self.run_cli("migrate")
        self.assertEqual(
            self.logtext(),
            "# Logbook\n\n## 2026-11-07\n\n- Source: umwayi queue migrate\n"
            "- Added: answer column added to queue.md for 3 rows (1 answered rows got the text "
            "'not recorded before migration', the others an empty answer)\n"
            "- Checked: the old six column layout parsed with no errors; the result parsed in the current layout; "
            "no other column and no line outside the table changed\n"
            "- Not done: The real answers of old answered rows were not recovered. "
            "No row was added, answered or closed.\n",
        )

    def test_migrate_explicit_date(self):
        self.put(OLD_HAND)
        self.run_cli("migrate", "--date", "2026-12-01")
        self.assertIn("## 2026-12-01", self.logtext())

    def test_migrate_only_works_once(self):
        self.put(OLD_HAND)
        self.run_cli("migrate")
        after, log_after = self.qtext(), self.logtext()
        code, out, err = self.run_cli("migrate")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("already has the current layout", err)
        self.assertEqual(self.qtext(), after)
        self.assertEqual(self.logtext(), log_after)

    def test_migrate_on_a_current_file_changes_nothing(self):
        self.put(HAND)
        code, _, err = self.run_cli("migrate")
        self.assertEqual(code, 1)
        self.assertIn("already has the current layout", err)
        self.assertEqual(self.qtext(), HAND)
        self.assertFalse(self.log.exists())

    def test_migrate_missing_file(self):
        code, _, _ = self.run_cli("migrate")
        self.assertEqual(code, 1)
        self.assertFalse(self.q.exists())
        self.assertFalse(self.log.exists())

    def test_migrate_malformed_old_file_changes_nothing(self):
        for name, text in {
            "answered without date": OLD_HEADER + "| Q-0001 | task | t | answered | | |\n",
            "bad status": OLD_HEADER + "| Q-0001 | task | t | nope | | |\n",
            "duplicate id": OLD_HEADER + "| Q-0001 | task | t | open | | |\n| Q-0001 | task | t | open | | |\n",
            "five cells": OLD_HEADER + "| Q-0001 | task | t | open | |\n",
            "mixed layout": OLD_HEADER + "| Q-0001 | task | t | open | | | |\n",
            "garbage": "# Queue\n\nno table\n",
        }.items():
            with self.subTest(name=name):
                self.put(text)
                code, out, _ = self.run_cli("migrate")
                self.assertEqual((code, out), (1, ""))
                self.assertEqual(self.qtext(), text)
                self.assertFalse(self.log.exists())

    def test_migrate_logbook_failure_rolls_back(self):
        self.put(OLD_HAND)
        self.log.mkdir()
        code, _, err = self.run_cli("migrate")
        self.assertEqual(code, 1)
        self.assertIn("undone", err)
        self.assertEqual(self.qtext(), OLD_HAND)

    def test_commands_work_after_migrating(self):
        self.put(OLD_HAND)
        self.run_cli("migrate")
        self.assertEqual(self.run_cli("list")[0], 0)
        self.assertEqual(self.run_cli("add", "--kind", "task", "new")[0], 0)
        self.assertEqual(self.ids()[-1], "Q-0008")
        self.assertEqual(self.run_cli("answer", "Q-0001", "--answer", "fine")[0], 0)
        self.assertEqual(self.run_cli("close", "Q-0002")[0], 0)

    def test_migrate_empty_old_table(self):
        self.put("# Queue\n\n" + OLD_HEADER)
        self.assertEqual(self.run_cli("migrate")[0], 0)
        self.assertEqual(self.qtext(), "# Queue\n\n" + HEADER)


# ====================================================== logbook coupling


class LogbookCouplingTests(QueueBase):
    def test_each_change_appends_exactly_one_entry_and_never_edits_earlier_text(self):
        write_sealed_logbook(self.root, "# Logbook\n" + entry_text(date="2026-01-01", added="hand written entry"))
        seen = self.logtext()
        steps = [
            ("add", "--kind", "task", "one"),
            ("add", "--kind", "decision", "two"),
            ("answer", "Q-0002", "--answer", "yes"),
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
        self.run_cli("answer", "Q-0099", "--answer", "x")
        self.run_cli("close", "Q-0007")
        self.assertFalse(self.log.exists())

    def test_logbook_failure_rolls_back_an_existing_queue(self):
        self.put(HAND)
        self.log.mkdir()
        # add is refused earlier (the logbook cannot be read); answer and close fail at the append
        for argv in (["answer", "Q-0001", "--answer", "x"], ["close", "Q-0001"]):
            with self.subTest(argv=argv):
                code, _, err = self.run_cli(*argv)
                self.assertEqual(code, 1)
                self.assertIn("undone", err)
                self.assertEqual(self.qtext(), HAND)

    def test_add_logbook_failure_after_the_id_check_rolls_back(self):
        self.put(HAND)
        with mock.patch("umwayi.taskqueue.logbook.append", side_effect=UmwayiError("boom")):
            code, _, err = self.run_cli("add", "--kind", "task", "x")
        self.assertEqual(code, 1)
        self.assertIn("undone", err)
        self.assertEqual(self.qtext(), HAND)

    def test_logbook_failure_rolls_back_a_new_queue(self):
        with mock.patch("umwayi.taskqueue.logbook.append", side_effect=UmwayiError("boom")):
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
        self.run_cli("answer", "Q-0001", "--answer", "ok")
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), [".umwayi", "LOGBOOK.md", "queue.md"])
        self.assertEqual(sorted(p.name for p in (self.root / ".umwayi").iterdir()), ["logbook.sha256"])


class SubprocessTests(QueueBase):
    def test_real_process_round_trip(self):
        env = dict(os.environ, PYTHONPATH=str(REPO))

        def run(*argv):
            return subprocess.run(
                [sys.executable, "-m", "umwayi", "--root", str(self.root), "queue", *argv],
                capture_output=True, text=True, env=env, cwd=self.root,
            )

        self.assertEqual(run("add", "--kind", "task", "Real run", "--date", "2026-11-07").returncode, 0)
        self.assertEqual(run("answer", "Q-0001", "--answer", "Done it", "--date", "2026-11-08").returncode, 0)
        self.assertEqual(run("close", "Q-0001", "--date", "2026-11-09").returncode, 0)
        r = run("list")
        self.assertEqual(r.returncode, 0)
        self.assertIn("closed", r.stdout)
        self.assertIn("[answer: Done it]", r.stdout)
        self.assertEqual(run("close", "Q-0001").returncode, 1)
        self.assertEqual(self.logtext().count("\n## "), 3)

    def test_real_process_uses_the_system_clock_when_no_date_is_given(self):
        from datetime import date
        env = dict(os.environ, PYTHONPATH=str(REPO))
        r = subprocess.run(
            [sys.executable, "-m", "umwayi", "--root", str(self.root), "queue", "add", "--kind", "task", "Clock run"],
            capture_output=True, text=True, env=env, cwd=self.root,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.logtext().count("\n## "), 1)
        self.assertIn(f"## {date.today().isoformat()}\n", self.logtext())

    def test_real_process_migrate(self):
        env = dict(os.environ, PYTHONPATH=str(REPO))
        self.put(OLD_HAND)
        r = subprocess.run(
            [sys.executable, "-m", "umwayi", "--root", str(self.root), "queue", "list"],
            capture_output=True, text=True, env=env, cwd=self.root,
        )
        self.assertEqual(r.returncode, 1)
        self.assertIn("umwayi queue migrate", r.stderr)
        r = subprocess.run(
            [sys.executable, "-m", "umwayi", "--root", str(self.root), "queue", "migrate"],
            capture_output=True, text=True, env=env, cwd=self.root,
        )
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
