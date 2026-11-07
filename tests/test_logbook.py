import tempfile
import unittest
from pathlib import Path

from umwayi import logbook
from umwayi.errors import UmwayiError
from umwayi.logbook import Entry, append, render


def entry(**kw):
    base = dict(
        date="2026-11-07",
        source="umwayi test",
        added="one thing",
        checked="a check",
        not_done="nothing else",
    )
    base.update(kw)
    return Entry(**base)


class LogbookTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.path = self.root / "LOGBOOK.md"

    def test_creates_file_with_header_and_entry(self):
        append(self.root, entry())
        self.assertEqual(
            self.path.read_text(encoding="utf-8"),
            "# Logbook\n\n## 2026-11-07\n\n- Source: umwayi test\n- Added: one thing\n"
            "- Checked: a check\n- Not done: nothing else\n",
        )

    def test_append_never_edits_earlier_bytes(self):
        append(self.root, entry())
        first = self.path.read_bytes()
        append(self.root, entry(date="2026-11-08", added="second"))
        second = self.path.read_bytes()
        self.assertTrue(second.startswith(first))
        self.assertIn(b"- Added: second", second[len(first):])
        append(self.root, entry(date="2026-11-09"))
        self.assertTrue(self.path.read_bytes().startswith(second))

    def test_existing_hand_written_file_is_kept_byte_for_byte(self):
        original = "# My logbook\n\nsome  odd   spacing\r\nno final newline"
        self.path.write_bytes(original.encode("utf-8"))
        append(self.root, entry())
        data = self.path.read_bytes()
        self.assertTrue(data.startswith(original.encode("utf-8")))
        self.assertNotIn(b"# Logbook\n", data[len(original):])  # header only for new files
        self.assertTrue(data.endswith(b"- Not done: nothing else\n"))

    def test_rejects_bad_entries_and_writes_nothing(self):
        bad = [
            entry(date="2026-13-45x"),
            entry(date="07-11-2026"),
            entry(added=""),
            entry(checked="   "),
            entry(source="line one\nline two"),
            entry(not_done="tab\there"),
        ]
        for e in bad:
            with self.subTest(e=e):
                with self.assertRaises(UmwayiError):
                    append(self.root, e)
                self.assertFalse(self.path.exists())

    def test_cannot_forge_a_second_entry_with_a_line_break(self):
        with self.assertRaises(UmwayiError):
            append(self.root, entry(added="x\n\n## 2020-01-01\n- Source: forged"))

    def test_symlink_refused(self):
        target = self.root / "real.md"
        target.write_text("keep\n", encoding="utf-8")
        try:
            self.path.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not supported")
        with self.assertRaises(UmwayiError):
            append(self.root, entry())
        self.assertEqual(target.read_text(encoding="utf-8"), "keep\n")

    def test_directory_in_the_way_is_an_error(self):
        self.path.mkdir()
        with self.assertRaises(UmwayiError):
            append(self.root, entry())

    def test_render_is_pure(self):
        self.assertEqual(render(entry()), render(entry()))
        self.assertFalse(self.path.exists())

    def test_module_only_opens_in_append_mode(self):
        # guard: the writer must never use a truncating or editing mode
        src = Path(logbook.__file__).read_text(encoding="utf-8")
        self.assertIn('"a+b"', src)
        for mode in ('"w"', '"wb"', '"r+b"', '"w+b"', "write_text", "unlink", "os.replace"):
            self.assertNotIn(mode, src)


if __name__ == "__main__":
    unittest.main()
