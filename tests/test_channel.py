"""M1g, step 2: the feedback channel (umwayi/channel.py), `umwayi feedback inbox` and `ack`.

The table is strict. The inbox shows EVERY open entry addressed to the reader, marks the ones with no ack line as new, and writes
nothing. `ack` writes exactly one logbook line (the id and the reader, never the text) and changes nothing in the folder. The text is
shown as data under a line that says so. A planted fault: an inbox that drops an open entry must be caught by the completeness check.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from umwayi import channel as ch
from umwayi import logbook

REPO = Path(__file__).resolve().parent.parent
HEAD = "| date | from | to | id | text | status |\n|---|---|---|---|---|---|\n"


def row(i="G-0001", to="builder", status="open", text="Do the thing. Recommendation: yes.", frm="guide", day="2026-11-24"):
    return f"| {day} | {frm} | {to} | {i} | {text} | {status} |\n"


def table(*rows):
    return HEAD + "".join(rows)


def missing_from_inbox(entries, me, lines):
    """The ids of the open entries for `me` that no inbox line shows. The completeness check; empty means none was dropped."""
    shown = " ".join(lines)
    return [e.id for e in entries if e.to == me and e.status == "open" and e.id not in shown]


class ParseTests(unittest.TestCase):
    def test_a_good_table_parses_in_file_order(self):
        es = ch.parse(table(row("G-0001"), row("B-0002", to="guide", frm="builder", status="answered")))
        self.assertEqual([(e.id, e.to, e.status) for e in es], [("G-0001", "builder", "open"), ("B-0002", "guide", "answered")])
        self.assertEqual(ch.parse(""), [])
        self.assertEqual(ch.parse(HEAD), [])

    def test_planted_faults_each_is_an_error_with_a_line_number_and_never_the_text_of_the_line(self):
        cases = {
            "a bad header": table(row()).replace("| status |", "| state |", 1),
            "no separator": HEAD.split("\n")[0] + "\n" + row(),
            "text but no table": "just notes\n",
            "a date that is not real": table(row(day="2026-13-40")),
            "a person that is not one": table(row(frm="robot")),
            "an id of the wrong form": table(row(i="g-1")),
            "an id used twice": table(row("G-0001"), row("G-0001")),
            "a status that is not one": table(row(status="pending")),
            "an empty text": table(row(text=" ")),
            "a text over 400 characters": table(row(text="x" * 401)),
            "a row with too few columns": HEAD + "| 2026-11-24 | guide | builder | G-0001 | text |\n",
            "an em dash": table(row(text="A note—here")),
            "a tab": table(row(text="A\tnote")),
            "a row that does not close": HEAD + "| 2026-11-24 | guide | builder | G-0001 | text | open\n",
        }
        for label, text in cases.items():
            with self.subTest(label):
                with self.assertRaises(ch.ChannelError) as cm:
                    ch.parse(text)
                self.assertNotIn("Recommendation", str(cm.exception))
                self.assertRegex(str(cm.exception), r"line \d+|no table|no separator|id is used twice|em dash")

    def test_the_error_names_the_line(self):
        with self.assertRaises(ch.ChannelError) as cm:
            ch.parse(table(row("G-0001"), row("G-0002", status="pending")))
        self.assertIn("line 4", str(cm.exception))


class InboxTests(unittest.TestCase):
    def setUp(self):
        self.entries = ch.parse(table(row("G-0001"), row("G-0002", to="guide", frm="builder"), row("G-0003", status="answered"),
                                      row("G-0004"), row("G-0005", status="done"), row("G-0006", to="owner")))

    def test_it_shows_every_open_entry_for_the_reader_and_nothing_else(self):
        lines = ch.inbox_lines(self.entries, "builder", set())
        self.assertIn("2 open (2 new)", lines[0])
        self.assertIn(ch.DATA_LINE, lines[0])
        self.assertEqual([l.split()[1] for l in lines[1:]], ["G-0001", "G-0004"])
        self.assertEqual(missing_from_inbox(self.entries, "builder", lines), [])
        self.assertEqual([l.split()[1] for l in ch.inbox_lines(self.entries, "guide", set())[1:]], ["G-0002"])

    def test_planted_fault_an_inbox_that_drops_an_open_entry_is_caught(self):
        lines = ch.inbox_lines(self.entries, "builder", set())
        broken = [l for l in lines if "G-0004" not in l]  # the fault: one open entry is not shown
        self.assertEqual(missing_from_inbox(self.entries, "builder", broken), ["G-0004"])
        self.assertEqual(missing_from_inbox(self.entries, "builder", lines), [])

    def test_an_acknowledged_entry_is_marked_read_and_still_shown_while_it_is_open(self):
        lines = ch.inbox_lines(self.entries, "builder", {"G-0001"})
        self.assertIn("2 open (1 new)", lines[0])
        self.assertTrue(lines[1].startswith("read") and "G-0001" in lines[1])
        self.assertTrue(lines[2].startswith("new") and "G-0004" in lines[2])

    def test_no_open_entry_for_the_reader_says_so(self):
        self.assertEqual(ch.inbox_lines(self.entries, "owner", set())[0].startswith("Inbox of the owner: 1 open"), True)
        self.assertEqual(ch.inbox_lines([], "builder", set()), ["Inbox of the builder: no open entries."])

    def test_the_text_is_cut_and_has_no_control_characters(self):
        long = ch.parse(table(row(text="a" * 400)))
        self.assertLessEqual(len(ch.inbox_lines(long, "builder", set())[1]), 300 + 40)
        self.assertTrue(ch.inbox_lines(long, "builder", set())[1].endswith("..."))
        self.assertEqual(ch._show("a\x1b[31mred\x07"), "a [31mred ")


class CommandTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name) / "root"
        self.folder = Path(d.name) / "folder"
        self.root.mkdir()
        self.folder.mkdir()
        (self.folder / "CHANNEL.md").write_text(table(row("G-0001"), row("B-0002", to="guide", frm="builder")), encoding="utf-8")

    def run_cmd(self, *args):
        return subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "feedback", *args, "--folder", str(self.folder)],
                              cwd=REPO, capture_output=True, text=True, timeout=60)

    def test_inbox_reads_only_and_ack_writes_one_line_without_the_text_and_changes_nothing_in_the_folder(self):
        before = (self.folder / "CHANNEL.md").read_bytes()
        p = self.run_cmd("inbox")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("1 open (1 new)", p.stdout)
        self.assertEqual(sorted(x.name for x in self.root.iterdir()), [])  # the inbox wrote nothing
        p = self.run_cmd("ack", "G-0001", "--date", "2026-11-24")
        self.assertEqual(p.returncode, 0, p.stderr)
        entries = [e for e in logbook.read_checked(self.root) if e.source == ch.SOURCE]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].added, "channel entry G-0001 read by builder")
        for part in (entries[0].added, entries[0].checked, entries[0].not_done):
            self.assertNotIn("Recommendation", part)  # the text of the entry is never copied
        self.assertEqual((self.folder / "CHANNEL.md").read_bytes(), before)
        p = self.run_cmd("inbox")
        self.assertIn("1 open (0 new)", p.stdout)
        self.assertTrue(p.stdout.split("\n")[1].startswith("read"))

    def test_ack_of_an_unknown_entry_or_an_entry_for_someone_else_is_exit_64_and_writes_nothing(self):
        for args in (("ack", "G-0099"), ("ack", "B-0002"), ("ack", "bad id")):
            with self.subTest(args=args):
                p = self.run_cmd(*args, "--date", "2026-11-24")
                self.assertEqual(p.returncode, 64, p.stdout + p.stderr)
        self.assertEqual(sorted(x.name for x in self.root.iterdir()), [])
        p = self.run_cmd("ack", "B-0002", "--me", "guide", "--date", "2026-11-24")
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_a_bad_channel_file_a_missing_folder_and_a_missing_file(self):
        (self.folder / "CHANNEL.md").write_text(table(row(status="pending")), encoding="utf-8")
        self.assertEqual(self.run_cmd("inbox").returncode, 64)
        (self.folder / "CHANNEL.md").unlink()
        p = self.run_cmd("inbox")
        self.assertEqual((p.returncode, p.stdout.strip()), (0, "Inbox of the builder: no open entries."))
        p = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "feedback", "inbox", "--folder", str(self.folder / "nope")],
                           cwd=REPO, capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 64)


if __name__ == "__main__":
    unittest.main()
