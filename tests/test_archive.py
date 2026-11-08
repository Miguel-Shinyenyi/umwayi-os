import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from umwayi import archive
from umwayi.archive import parse_index
from umwayi.cli import main
from umwayi.errors import UmwayiError
from tests.helpers import entry_text, write_sealed_logbook

REPO = Path(__file__).resolve().parent.parent
REAL_WRITE = archive.atomic_write

SRC = (
    "# Notes\n"
    "keep one\n"
    "old alpha beta\n"
    "old gamma\n"
    "keep two\n"
)

INDEX_HEAD = "| id | source | moved | reason | words | sha256 |\n| --- | --- | --- | --- | --- | --- |\n"
SHA_A = "a" * 64


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ArchiveBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.write("umwayi.json", json.dumps({
            "memory_dir": "memory",
            "private_paths": ["secret.md", "memory/private", "journal/*-private.md"],
        }))
        self.write("notes.md", SRC)
        self.log = self.root / "LOGBOOK.md"
        self.idx = self.root / "archive" / "INDEX.md"

    # -- helpers
    def write(self, rel, data):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return p

    def read(self, rel):
        return (self.root / rel).read_bytes()

    def snap(self, mtimes=False):
        """Every file (bytes) and folder under the root."""
        files, dirs = {}, set()
        for dp, dn, fn in os.walk(self.root):
            for d in dn:
                dirs.add(os.path.relpath(os.path.join(dp, d), self.root))
            for f in fn:
                full = os.path.join(dp, f)
                rel = os.path.relpath(full, self.root)
                if os.path.islink(full):
                    files[rel] = ("link", os.readlink(full))
                else:
                    files[rel] = (Path(full).read_bytes(), os.stat(full).st_mtime_ns if mtimes else None)
        return files, dirs

    def run_cli(self, *argv, clock="2026-11-07"):
        out, err = io.StringIO(), io.StringIO()
        old = sys.stderr
        sys.stderr = err
        try:
            with mock.patch("umwayi.cli._today", return_value=clock):
                code = main(["--root", str(self.root), "archive", *argv], out=out)
        finally:
            sys.stderr = old
        return code, out.getvalue(), err.getvalue()

    def move(self, *argv, **kw):
        return self.run_cli("move", *argv, **kw)

    def ok_move(self, *argv, **kw):
        code, out, err = self.move(*argv, **kw)
        self.assertEqual(code, 0, err)
        return out

    def assert_refused(self, argv, fragment, clock="2026-11-07", code=1):
        before = self.snap()
        got, out, err = self.run_cli(*argv, clock=clock)
        self.assertEqual((got, out), (code, ""), err)
        self.assertIn(fragment, err)
        self.assertEqual(self.snap(), before, "a refused command changed something")

    def index_rows(self):
        return parse_index(self.idx.read_text(encoding="utf-8")).rows


# ============================================================ index parser


class IndexParserTests(unittest.TestCase):
    ROW = f"| A-0001 | notes.md | 2026-11-07 | why | 3 | {SHA_A} |\n"

    def test_template_and_row_round_trip(self):
        self.assertEqual(parse_index(archive.TEMPLATE).rows, [])
        text = archive.TEMPLATE + self.ROW
        doc = parse_index(text)
        self.assertEqual(doc.rows[0].words, 3)
        self.assertEqual(doc.text(), text)

    def test_malformed(self):
        bad = {
            "empty": "",
            "no table": "# Index\n\nwords\n",
            "wrong column": (INDEX_HEAD.replace("reason", "why")) + self.ROW,
            "columns out of order": INDEX_HEAD.replace("source | moved", "moved | source") + self.ROW,
            "bad separator": INDEX_HEAD.replace("| --- | --- | --- | --- | --- | --- |", "| a | b | c | d | e | f |") + self.ROW,
            "two tables": INDEX_HEAD + self.ROW + "\ntext\n\n" + INDEX_HEAD,
            "too few cells": INDEX_HEAD + "| A-0001 | notes.md | 2026-11-07 | why | 3 |\n",
            "too many cells": INDEX_HEAD + self.ROW.rstrip("\n") + " x |\n",
            "bad id": INDEX_HEAD + self.ROW.replace("A-0001", "Q-0001"),
            "short id": INDEX_HEAD + self.ROW.replace("A-0001", "A-1"),
            "empty source": INDEX_HEAD + self.ROW.replace("notes.md", ""),
            "absolute source": INDEX_HEAD + self.ROW.replace("notes.md", "/etc/passwd"),
            "dotdot source": INDEX_HEAD + self.ROW.replace("notes.md", "a/../b.md"),
            "bad date": INDEX_HEAD + self.ROW.replace("2026-11-07", "2026-02-30"),
            "empty reason": INDEX_HEAD + self.ROW.replace("why", ""),
            "words not a number": INDEX_HEAD + self.ROW.replace("| 3 |", "| three |"),
            "negative words": INDEX_HEAD + self.ROW.replace("| 3 |", "| -3 |"),
            "short sha": INDEX_HEAD + self.ROW.replace(SHA_A, "a" * 63),
            "uppercase sha": INDEX_HEAD + self.ROW.replace(SHA_A, "A" * 64),
            "non hex sha": INDEX_HEAD + self.ROW.replace(SHA_A, "g" * 64),
            "duplicate id": INDEX_HEAD + self.ROW + self.ROW,
            "crlf": (INDEX_HEAD + self.ROW).replace("\n", "\r\n"),
            "nul": INDEX_HEAD + self.ROW + "\x00",
            "unterminated row": INDEX_HEAD + "| A-0001 | notes.md | 2026-11-07 | why | 3 | " + SHA_A + "\n",
        }
        for name, text in bad.items():
            with self.subTest(name=name):
                with self.assertRaises(UmwayiError):
                    parse_index(text)

    def test_errors_have_line_numbers_not_content(self):
        text = INDEX_HEAD + self.ROW.replace("why", "SECRETREASON").replace("2026-11-07", "nonsense-date")
        with self.assertRaises(UmwayiError) as cm:
            parse_index(text)
        self.assertIn("line 3", str(cm.exception))
        self.assertNotIn("SECRETREASON", str(cm.exception))
        self.assertNotIn("nonsense-date", str(cm.exception))


# ======================================================== move: the block


class MoveByLinesTests(ArchiveBase):
    def test_exact_block_archive_file_index_pointer_and_output(self):
        out = self.ok_move("notes.md", "--lines", "3-4", "--reason", "old stuff")
        block = b"old alpha beta\nold gamma\n"
        self.assertEqual(self.read("archive/A-0001.txt"), block)
        self.assertEqual(
            self.read("notes.md").decode(),
            "# Notes\nkeep one\n[archived A-0001: archive/A-0001.txt]\nkeep two\n",
        )
        rows = self.index_rows()
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r.id, r.source, r.moved, r.reason, r.words, r.sha256),
                         ("A-0001", "notes.md", "2026-11-07", "old stuff", 5, sha(block)))
        self.assertEqual(
            out,
            "Moved lines 3-4 of notes.md to archive/A-0001.txt\n"
            "Id: A-0001\nWords: 5\n"
            f"SHA-256: {sha(block)}\n"
            "Pointer line left in notes.md: [archived A-0001: archive/A-0001.txt]\n"
            "To put it back later: umwayi archive restore A-0001 (this command is not built yet)\n",
        )

    def test_everything_outside_the_block_is_byte_identical(self):
        body = "".join(f"line {i} word\n" for i in range(1, 21))
        self.write("long.md", body)
        self.ok_move("long.md", "--lines", "5-9", "--reason", "r")
        new = self.read("long.md").decode().split("\n")
        old = body.split("\n")
        self.assertEqual(new[:4], old[:4])
        self.assertEqual(new[4], "[archived A-0001: archive/A-0001.txt]")
        self.assertEqual(new[5:], old[9:])

    def test_first_line_last_line_single_line_and_whole_file(self):
        for rng, expect in [
            ("1-1", "[archived A-0001: archive/A-0001.txt]\nkeep one\nold alpha beta\nold gamma\nkeep two\n"),
            ("5-5", "# Notes\nkeep one\nold alpha beta\nold gamma\n[archived A-0001: archive/A-0001.txt]\n"),
            ("1-5", "[archived A-0001: archive/A-0001.txt]\n"),
        ]:
            with self.subTest(rng=rng):
                self.write("notes.md", SRC)
                if (self.root / "archive").exists():
                    import shutil
                    shutil.rmtree(self.root / "archive")
                    shutil.rmtree(self.root / ".umwayi")  # start again with no logbook and no record
                    self.log.unlink()
                self.ok_move("notes.md", "--lines", rng, "--reason", "r")
                self.assertEqual(self.read("notes.md").decode(), expect)

    def test_no_trailing_newline_in_the_block(self):
        self.write("tail.md", "head\nlast words")
        self.ok_move("tail.md", "--lines", "2-2", "--reason", "r")
        self.assertEqual(self.read("archive/A-0001.txt"), b"last words")
        self.assertEqual(self.read("tail.md"), b"head\n[archived A-0001: archive/A-0001.txt]")

    def test_crlf_source_keeps_its_line_endings(self):
        self.write("win.md", b"a one\r\nold two\r\nb three\r\n")
        self.ok_move("win.md", "--lines", "2-2", "--reason", "r")
        self.assertEqual(self.read("archive/A-0001.txt"), b"old two\r\n")
        self.assertEqual(self.read("win.md"), b"a one\r\n[archived A-0001: archive/A-0001.txt]\r\nb three\r\n")

    def test_unicode_and_word_count(self):
        self.write("u.md", "intro\ncafé  naïve\n\n  tabs\tand   spaces \nend\n")
        self.ok_move("u.md", "--lines", "2-4", "--reason", "r")
        self.assertEqual(self.index_rows()[0].words, 5)
        self.assertEqual(self.read("archive/A-0001.txt").decode(), "café  naïve\n\n  tabs\tand   spaces \n")

    def test_two_moves(self):
        self.ok_move("notes.md", "--lines", "3-4", "--reason", "one")
        self.ok_move("notes.md", "--lines", "4-4", "--reason", "two")
        self.assertEqual(
            self.read("notes.md").decode(),
            "# Notes\nkeep one\n[archived A-0001: archive/A-0001.txt]\n[archived A-0002: archive/A-0002.txt]\n",
        )
        self.assertEqual([r.id for r in self.index_rows()], ["A-0001", "A-0002"])
        self.assertEqual(self.read("archive/A-0002.txt"), b"keep two\n")

    def test_nested_pointer_can_be_archived_again(self):
        self.ok_move("notes.md", "--lines", "3-4", "--reason", "one")
        self.ok_move("notes.md", "--lines", "3-3", "--reason", "move the pointer itself")
        self.assertEqual(self.read("archive/A-0002.txt"), b"[archived A-0001: archive/A-0001.txt]\n")

    def test_archive_files_get_normal_permissions(self):
        self.ok_move("notes.md", "--lines", "3-4", "--reason", "r")
        mask = os.umask(0)
        os.umask(mask)
        for rel in ("archive/A-0001.txt", "archive/INDEX.md"):
            self.assertEqual(stat.S_IMODE(os.stat(self.root / rel).st_mode), 0o666 & ~mask)

    def test_existing_source_permissions_are_kept(self):
        os.chmod(self.root / "notes.md", 0o640)
        self.ok_move("notes.md", "--lines", "3-4", "--reason", "r")
        self.assertEqual(stat.S_IMODE(os.stat(self.root / "notes.md").st_mode), 0o640)

    def test_source_in_a_subfolder_and_absolute_path_inside_root(self):
        self.write("docs/deep/a.md", "x\nmove me now\ny\n")
        self.ok_move(str(self.root / "docs" / "deep" / "a.md"), "--lines", "2-2", "--reason", "r")
        self.assertEqual(self.index_rows()[0].source, "docs/deep/a.md")

    def test_no_temp_files_left_behind(self):
        self.ok_move("notes.md", "--lines", "3-4", "--reason", "r")
        names = sorted(os.listdir(self.root / "archive")) + sorted(os.listdir(self.root))
        self.assertEqual(sorted(n for n in names if n.startswith(".umwayi-")), [])


class MoveByMarkersTests(ArchiveBase):
    MARK = "intro\n<!-- start -->\nold one\nold two\n<!-- end -->\noutro\n"

    def test_markers_are_included_in_the_block(self):
        self.write("m.md", self.MARK)
        out = self.ok_move("m.md", "--start", "<!-- start -->", "--end", "<!-- end -->", "--reason", "r")
        self.assertEqual(self.read("archive/A-0001.txt").decode(), "<!-- start -->\nold one\nold two\n<!-- end -->\n")
        self.assertEqual(self.read("m.md").decode(), "intro\n[archived A-0001: archive/A-0001.txt]\noutro\n")
        self.assertIn("Moved lines 2-5 of m.md", out)

    def test_marker_matches_a_whole_line_ignoring_outer_spaces(self):
        self.write("m.md", "a\n   BEGIN  \nbody text\nEND\t\nz\n")
        self.ok_move("m.md", "--start", "BEGIN", "--end", "END", "--reason", "r")
        self.assertEqual(self.read("archive/A-0001.txt").decode(), "   BEGIN  \nbody text\nEND\t\n")

    def test_marker_must_be_the_whole_line(self):
        self.write("m.md", "a\nxx BEGIN yy\nbody\nEND\n")
        self.assert_refused(["move", "m.md", "--start", "BEGIN", "--end", "END", "--reason", "r"],
                            "start marker was not found")

    def test_marker_refusals(self):
        cases = [
            ("start missing", "a\nbody\nEND\n", ["--start", "BEGIN", "--end", "END"], "start marker was not found"),
            ("end missing", "BEGIN\nbody\n", ["--start", "BEGIN", "--end", "END"], "end marker was not found"),
            ("start twice", "BEGIN\nx\nBEGIN\ny\nEND\n", ["--start", "BEGIN", "--end", "END"], "start marker appears more than once"),
            ("end twice", "BEGIN\nx\nEND\ny\nEND\n", ["--start", "BEGIN", "--end", "END"], "end marker appears more than once"),
            ("end before start", "END\nx\nBEGIN\n", ["--start", "BEGIN", "--end", "END"], "end marker comes before"),
            # the marker text itself is not allowed: a usage error (64)
            ("same marker", "X\nbody\nX\n", ["--start", "X", "--end", "X"], "must be different"),
            ("empty start", "BEGIN\nEND\n", ["--start", "  ", "--end", "END"], "start marker must not be empty"),
            ("empty end", "BEGIN\nEND\n", ["--start", "BEGIN", "--end", ""], "end marker must not be empty"),
            ("multi line marker", "BEGIN\nEND\n", ["--start", "BE\nGIN", "--end", "END"], "one short line"),
        ]
        usage = {"same marker", "empty start", "empty end", "multi line marker"}
        for name, text, args, fragment in cases:
            with self.subTest(name=name):
                self.write("m.md", text)
                self.assert_refused(["move", "m.md", *args, "--reason", "r"], fragment, code=64 if name in usage else 1)

    def test_marker_error_does_not_echo_the_marker(self):
        self.write("m.md", "a\n")
        code, _, err = self.run_cli("move", "m.md", "--start", "SECRETMARKER", "--end", "END", "--reason", "r")
        self.assertEqual(code, 1)
        self.assertNotIn("SECRETMARKER", err)


# ============================================================== refusals


class RefusalTests(ArchiveBase):
    def test_source_missing(self):
        self.assert_refused(["move", "nope.md", "--lines", "1-1", "--reason", "r"], "source file was not found")

    def test_source_is_a_directory(self):
        (self.root / "adir").mkdir()
        self.assert_refused(["move", "adir", "--lines", "1-1", "--reason", "r"], "regular file")

    def test_source_is_a_symlink(self):
        try:
            os.symlink(self.root / "notes.md", self.root / "link.md")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not supported")
        self.assert_refused(["move", "link.md", "--lines", "3-4", "--reason", "r"], "symbolic link")
        self.assertEqual(self.read("notes.md").decode(), SRC)

    def test_source_inside_a_symlinked_folder(self):
        real = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(real, ignore_errors=True))
        (real / "x.md").write_text("one two\nthree four\n", encoding="utf-8")
        try:
            os.symlink(real, self.root / "linked")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not supported")
        self.assert_refused(["move", "linked/x.md", "--lines", "1-1", "--reason", "r"], "symbolic link")
        self.assertEqual((real / "x.md").read_text(encoding="utf-8"), "one two\nthree four\n")

    def test_source_outside_the_root(self):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(outside, ignore_errors=True))
        (outside / "o.md").write_text("one two\n", encoding="utf-8")
        self.assert_refused(["move", str(outside / "o.md"), "--lines", "1-1", "--reason", "r"], "inside the root")
        self.assert_refused(["move", "../x.md", "--lines", "1-1", "--reason", "r"], "'..'")
        self.assert_refused(["move", "sub/../notes.md", "--lines", "3-4", "--reason", "r"], "'..'")
        self.assertEqual((outside / "o.md").read_text(encoding="utf-8"), "one two\n")

    def test_source_is_a_private_path(self):
        self.write("secret.md", "top secret words\nmore words\n")
        self.write("memory/private/deep/x.md", "private words\nmore words\n")
        self.write("journal/2026-11-07-private.md", "diary words\nmore words\n")
        self.write("Secret.md", "case words\nmore words\n")  # other case of a private name
        for src in ["secret.md", "memory/private/deep/x.md", "journal/2026-11-07-private.md", "Secret.md"]:
            with self.subTest(src=src):
                self.assert_refused(["move", src, "--lines", "1-1", "--reason", "r"], "private path")

    def test_private_content_never_reaches_the_archive_or_logbook(self):
        self.write("secret.md", "TOPSECRETWORDS here\n")
        self.run_cli("move", "secret.md", "--lines", "1-1", "--reason", "r")
        self.assertFalse((self.root / "archive").exists())
        self.assertFalse(self.log.exists())

    def test_protected_files(self):
        self.write("LOGBOOK.md", "# Logbook\n\n## 2026-01-01\n\n- some words here\n")
        self.write("queue.md", "# Queue\n\nsome words\n")
        self.write("rules.yaml", "rules: []\n")
        self.write(".git/config", "[core]\n")
        self.write("archive/A-0001.txt", "archived words here\n")
        self.write("archive/INDEX.md", archive.TEMPLATE)
        for src in ["LOGBOOK.md", "queue.md", "rules.yaml", "umwayi.json", ".git/config",
                    "archive/A-0001.txt", "archive/INDEX.md"]:
            with self.subTest(src=src):
                self.assert_refused(["move", src, "--lines", "1-1", "--reason", "r"], "protected")

    def test_missing_or_broken_config_refuses(self):
        for text in [None, "{broken", '{"memory_dir": "memory"}']:
            with self.subTest(config=text):
                cfg = self.root / "umwayi.json"
                good = cfg.read_bytes()
                if text is None:
                    cfg.unlink()
                else:
                    cfg.write_text(text, encoding="utf-8")
                self.assert_refused(["move", "notes.md", "--lines", "3-4", "--reason", "r"], "config", code=64)
                self.write("umwayi.json", good)

    def test_reason_refusals(self):
        for reason, fragment in [
            ("", "reason must not be empty"),
            ("   ", "reason must not be empty"),
            ("a | b", "must not contain the | character"),
            ("two\nlines", "one line of plain text"),
            ("x" * 501, "longer than 500"),
        ]:
            with self.subTest(reason=reason[:10]):
                self.assert_refused(["move", "notes.md", "--lines", "3-4", "--reason", reason], fragment, code=64)
                # it must be refused up front, not caught later by the index re-check
                _, _, err = self.run_cli("move", "notes.md", "--lines", "3-4", "--reason", reason)
                self.assertNotIn("archive index", err)
                self.assertNotIn("internal check", err)

    def test_reason_at_the_limit_is_fine(self):
        self.ok_move("notes.md", "--lines", "3-4", "--reason", "x" * 500)

    def test_range_refusals(self):
        for rng, fragment in [
            ("4-3", "range is empty"),
            ("0-2", "outside the file"),
            ("1-6", "outside the file"),
            ("6-7", "outside the file"),
            ("99-100", "outside the file"),
        ]:
            with self.subTest(rng=rng):
                self.assert_refused(["move", "notes.md", "--lines", rng, "--reason", "r"], fragment)

    def test_empty_source_file(self):
        self.write("empty.md", "")
        self.assert_refused(["move", "empty.md", "--lines", "1-1", "--reason", "r"], "outside the file")

    def test_block_without_words(self):
        self.write("blank.md", "a b\n\n   \n\t\nc d\n")
        self.assert_refused(["move", "blank.md", "--lines", "2-4", "--reason", "r"], "no words")

    def test_source_not_utf8(self):
        self.write("bin.md", b"ok words\n\xff\xfe\n")
        self.assert_refused(["move", "bin.md", "--lines", "1-1", "--reason", "r"], "not valid UTF-8")

    def test_source_path_with_a_pipe(self):
        self.write("a|b.md", "some words\n")
        self.assert_refused(["move", "a|b.md", "--lines", "1-1", "--reason", "r"], "| character")

    def test_malformed_index_refuses(self):
        self.write("archive/INDEX.md", INDEX_HEAD + "| A-0001 | broken |\n")
        self.assert_refused(["move", "notes.md", "--lines", "3-4", "--reason", "r"], "archive index line 3")

    def test_index_symlink_and_archive_not_a_folder(self):
        self.write("archive", "i am a file\n")
        self.assert_refused(["move", "notes.md", "--lines", "3-4", "--reason", "r"], "normal folder")

    def test_orphan_archive_file_with_the_next_id(self):
        self.write("archive/A-0001.txt", "orphan words\n")
        self.write("archive/INDEX.md", archive.TEMPLATE)
        self.assert_refused(["move", "notes.md", "--lines", "3-4", "--reason", "r"], "already exists")

    def test_bad_date(self):
        code, _, _ = self.run_cli("move", "notes.md", "--lines", "3-4", "--reason", "r", "--date", "2026-02-30")
        self.assertEqual(code, 64)

    def test_usage_errors(self):
        before = self.snap()
        for argv in (
            ["move", "notes.md", "--lines", "3-4"],  # no reason
            ["move", "notes.md", "--reason", "r"],  # no range or markers
            ["move", "notes.md", "--lines", "3-4", "--start", "a", "--end", "b", "--reason", "r"],  # both
            ["move", "notes.md", "--start", "a", "--reason", "r"],  # only start
            ["move", "notes.md", "--end", "a", "--reason", "r"],  # only end
            ["move", "--lines", "3-4", "--reason", "r"],  # no source
            ["move", "notes.md", "--lines", "5", "--reason", "r"],
            ["move", "notes.md", "--lines", "a-b", "--reason", "r"],
            ["move", "notes.md", "--lines", "-3-5", "--reason", "r"],
            ["move", "notes.md", "--lines", "3-", "--reason", "r"],
            [],
            ["restore", "A-0001"],  # restore is not built
        ):
            with self.subTest(argv=argv):
                self.assertEqual(self.run_cli(*argv)[0], 64)
        self.assertEqual(self.snap(), before)


# ================================================================ id guard


class IdGuardTests(ArchiveBase):
    def test_next_ids_count_up(self):
        for n, rng in enumerate(["3-3", "3-3", "3-3"], 1):
            self.ok_move("notes.md", "--lines", rng, "--reason", "r")
        self.assertEqual([r.id for r in self.index_rows()], ["A-0001", "A-0002", "A-0003"])

    def _three(self):
        self.write("big.md", "".join(f"w{i} x\n" for i in range(1, 10)))
        for _ in range(3):
            self.ok_move("big.md", "--lines", "1-1", "--reason", "r")

    def test_not_reused_after_the_last_index_row_is_deleted_by_hand(self):
        self._three()
        kept = [l for l in self.idx.read_text(encoding="utf-8").split("\n") if "| A-0003 |" not in l]
        self.idx.write_text("\n".join(kept), encoding="utf-8")
        (self.root / "archive" / "A-0003.txt").unlink()
        self.assertEqual([r.id for r in self.index_rows()], ["A-0001", "A-0002"])
        self.ok_move("big.md", "--lines", "1-1", "--reason", "r")
        self.assertEqual([r.id for r in self.index_rows()], ["A-0001", "A-0002", "A-0004"])

    def test_not_reused_after_all_rows_are_deleted_by_hand(self):
        self._three()
        kept = [l for l in self.idx.read_text(encoding="utf-8").split("\n") if not l.startswith("| A-")]
        self.idx.write_text("\n".join(kept), encoding="utf-8")
        for n in (1, 2, 3):
            (self.root / "archive" / f"A-000{n}.txt").unlink()
        self.ok_move("big.md", "--lines", "1-1", "--reason", "r")
        self.assertEqual([r.id for r in self.index_rows()], ["A-0004"])

    def test_not_reused_after_the_whole_archive_folder_is_deleted(self):
        self._three()
        import shutil
        shutil.rmtree(self.root / "archive")
        self.ok_move("big.md", "--lines", "1-1", "--reason", "r")
        self.assertEqual([r.id for r in self.index_rows()], ["A-0004"])

    def test_highest_in_the_logbook_wins(self):
        write_sealed_logbook(self.root, "# Logbook\n" + entry_text(added="A-0040 moved from old.md"))
        self.ok_move("notes.md", "--lines", "3-4", "--reason", "r")
        self.assertEqual(self.index_rows()[0].id, "A-0041")

    def test_highest_in_the_index_wins(self):
        self.write("archive/INDEX.md", archive.TEMPLATE + f"| A-0020 | old.md | 2026-01-01 | why | 3 | {SHA_A} |\n")
        self.ok_move("notes.md", "--lines", "3-4", "--reason", "r")
        self.assertEqual([r.id for r in self.index_rows()], ["A-0020", "A-0021"])

    def test_queue_ids_do_not_count(self):
        write_sealed_logbook(self.root, "# Logbook\n" + entry_text(added="Q-0500 (task) as open: x"))
        self.ok_move("notes.md", "--lines", "3-4", "--reason", "r")
        self.assertEqual(self.index_rows()[0].id, "A-0001")

    def test_ids_in_reasons_and_paths_do_not_inflate_the_counter(self):
        self.write("A-9999.md", "one two\nthree four\nfive six\n")
        self.ok_move("A-9999.md", "--lines", "1-1", "--reason", "see A-8888 and A-7777")
        self.ok_move("A-9999.md", "--lines", "2-2", "--reason", "r")
        self.assertEqual([r.id for r in self.index_rows()], ["A-0001", "A-0002"])

    def test_missing_logbook_is_fine(self):
        self.assertFalse(self.log.exists())
        self.ok_move("notes.md", "--lines", "3-4", "--reason", "r")

    def test_unreadable_logbook_refuses_and_says_why(self):
        self.log.mkdir()
        self.assert_refused(["move", "notes.md", "--lines", "3-4", "--reason", "r"], "cannot be read")
        code, _, err = self.move("notes.md", "--lines", "3-4", "--reason", "r")
        self.assertIn("cannot move", err)
        self.assertIn("never reused", err)
        self.log.rmdir()
        self.log.write_bytes(b"# Logbook\n\xff\xfe\n")
        self.assert_refused(["move", "notes.md", "--lines", "3-4", "--reason", "r"], "not valid UTF-8")
        self.log.unlink()
        target = self.write("elsewhere.md", "# Logbook\n")
        try:
            os.symlink(target, self.log)
        except (OSError, NotImplementedError):
            return
        self.assert_refused(["move", "notes.md", "--lines", "3-4", "--reason", "r"], "symbolic link")

    def test_unreadable_logbook_creates_no_archive_folder(self):
        self.log.mkdir()
        self.move("notes.md", "--lines", "3-4", "--reason", "r")
        self.assertFalse((self.root / "archive").exists())


# ================================================== dates and the logbook


class DateAndLogbookTests(ArchiveBase):
    def test_explicit_date_beats_clock(self):
        self.ok_move("notes.md", "--lines", "3-4", "--reason", "r", "--date", "2027-01-02", clock="2026-11-07")
        self.assertEqual(self.index_rows()[0].moved, "2027-01-02")
        self.assertIn("## 2027-01-02", self.log.read_text(encoding="utf-8"))

    def test_clock_is_used_and_not_the_last_index_row(self):
        self.write("archive/INDEX.md", archive.TEMPLATE + f"| A-0001 | old.md | 2030-01-01 | why | 3 | {SHA_A} |\n")
        self.ok_move("notes.md", "--lines", "3-4", "--reason", "r", clock="2026-11-07")
        self.assertEqual(self.index_rows()[1].moved, "2026-11-07")

    def test_one_exact_logbook_entry_per_move(self):
        self.ok_move("notes.md", "--lines", "3-4", "--reason", "old stuff")
        block = b"old alpha beta\nold gamma\n"
        self.assertEqual(
            self.log.read_text(encoding="utf-8"),
            "# Logbook\n\n## 2026-11-07\n\n- Source: umwayi archive move\n"
            f"- Added: A-0001 moved from notes.md (lines 3 to 4, 5 words, {len(block)} bytes) to archive/A-0001.txt "
            f"with SHA-256 {sha(block)}; index row and one pointer line added\n"
            "- Checked: source is a regular file inside the root, not a symbolic link, not private, not protected; "
            "block is non-empty valid UTF-8; index parsed with no errors (0 rows before); "
            "A-0001 is one more than the highest id in the index and the logbook; "
            "the archive file was read back and its SHA-256 matched\n"
            "- Not done: No text outside the block was changed. Nothing was deleted: the block is in the archive file. "
            "It was not restored anywhere (restore is not built yet).\n",
        )

    def test_logbook_is_only_appended_to(self):
        write_sealed_logbook(self.root, "# Logbook\n" + entry_text(date="2026-01-01"))
        before = self.log.read_bytes()
        self.ok_move("notes.md", "--lines", "3-3", "--reason", "r")
        after = self.log.read_bytes()
        self.assertTrue(after.startswith(before))
        self.assertEqual(after.count(b"\n## "), 2)
        self.ok_move("notes.md", "--lines", "3-3", "--reason", "r")
        self.assertTrue(self.log.read_bytes().startswith(after))
        self.assertEqual(self.log.read_bytes().count(b"\n## "), 3)

    def test_refused_moves_write_no_entry(self):
        self.run_cli("move", "notes.md", "--lines", "9-9", "--reason", "r")
        self.run_cli("move", "nope.md", "--lines", "1-1", "--reason", "r")
        self.assertFalse(self.log.exists())

    def test_verify_writes_no_entry(self):
        self.ok_move("notes.md", "--lines", "3-4", "--reason", "r")
        before = self.log.read_bytes()
        self.run_cli("verify")
        self.assertEqual(self.log.read_bytes(), before)


# ======================================================= three file rollback


class RollbackTests(ArchiveBase):
    def failing_write(self, fail_from, only_one=True, hook=None):
        calls = {"n": 0}

        def wrapper(path, data):
            calls["n"] += 1
            if calls["n"] == fail_from or (not only_one and calls["n"] > fail_from):
                raise OSError("disk gone")
            REAL_WRITE(path, data)
            if hook:
                hook(calls["n"])
        return wrapper

    def run_move(self):
        return self.run_cli("move", "notes.md", "--lines", "3-4", "--reason", "r")

    def test_each_failing_write_leaves_everything_as_it_was_new_archive(self):
        for n in (1, 2, 3):
            with self.subTest(failing_write=n):
                before = self.snap()
                with mock.patch("umwayi.archive.atomic_write", self.failing_write(n)):
                    code, out, err = self.run_move()
                self.assertEqual((code, out), (1, ""))
                self.assertIn("undone", err)
                self.assertEqual(self.snap(), before)
                self.assertFalse((self.root / "archive").exists())  # a folder made for this move is removed

    def test_each_failing_write_leaves_everything_as_it_was_existing_archive(self):
        self.ok_move("notes.md", "--lines", "3-3", "--reason", "first")
        for n in (1, 2, 3):
            with self.subTest(failing_write=n):
                before = self.snap()
                with mock.patch("umwayi.archive.atomic_write", self.failing_write(n)):
                    code, _, err = self.run_move()
                self.assertEqual(code, 1)
                self.assertIn("undone", err)
                self.assertEqual(self.snap(), before)

    def test_logbook_failure_undoes_all_three_files(self):
        for existing in (False, True):
            with self.subTest(existing_archive=existing):
                if existing:
                    self.ok_move("notes.md", "--lines", "3-3", "--reason", "first")
                before = self.snap()
                with mock.patch("umwayi.archive.logbook.append", side_effect=UmwayiError("boom")):
                    code, out, err = self.run_move()
                self.assertEqual((code, out), (1, ""))
                self.assertIn("logbook write failed, so the move was undone", err)
                self.assertEqual(self.snap(), before)

    def test_keyboard_interrupt_also_undoes_and_propagates(self):
        before = self.snap()
        with mock.patch("umwayi.archive.logbook.append", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                archive.move(self.root, "notes.md", "r", "2026-11-07", lines=(3, 4))
        self.assertEqual(self.snap(), before)

    def test_source_changed_while_moving_is_detected_and_not_overwritten(self):
        edited = SRC + "typed meanwhile\n"

        def hook(n):
            if n == 2:  # right after the index is written
                self.write("notes.md", edited)

        before_archive = self.snap()[1]
        with mock.patch("umwayi.archive.atomic_write", self.failing_write(99, hook=hook)):
            code, _, err = self.run_move()
        self.assertEqual(code, 1)
        self.assertIn("source file changed while it was being moved", err)
        self.assertEqual(self.read("notes.md").decode(), edited)  # the other edit is kept
        self.assertFalse((self.root / "archive").exists())
        self.assertEqual(self.snap()[1], before_archive)

    def test_archive_file_that_does_not_read_back_is_undone(self):
        def corrupt(n):
            if n == 1:
                (self.root / "archive" / "A-0001.txt").write_bytes(b"corrupted")

        before = self.snap()
        with mock.patch("umwayi.archive.atomic_write", self.failing_write(99, hook=corrupt)):
            code, _, err = self.run_move()
        self.assertEqual(code, 1)
        self.assertIn("read back", err)
        self.assertEqual(self.snap(), before)

    def test_restore_failure_is_reported_loudly_and_the_rest_is_still_restored(self):
        before = self.snap()
        # calls: 1 archive, 2 index, 3 source, then the logbook fails; call 4 is the source restore
        calls = {"n": 0}

        def wrapper(path, data):
            calls["n"] += 1
            if calls["n"] == 4:
                raise OSError("disk gone")
            REAL_WRITE(path, data)

        with mock.patch("umwayi.archive.atomic_write", wrapper), mock.patch(
            "umwayi.archive.logbook.append", side_effect=UmwayiError("boom")
        ):
            code, _, err = self.run_move()
        self.assertEqual(code, 1)
        self.assertIn("could not be restored", err)
        self.assertIn("source file", err)
        now = self.snap()
        # only the source differs (it still holds the pointer line); index and archive file were undone
        self.assertFalse((self.root / "archive" / "A-0001.txt").exists())
        self.assertNotEqual(now[0]["notes.md"], before[0]["notes.md"])
        self.assertIn(b"[archived A-0001", now[0]["notes.md"][0])

    def test_no_temp_files_after_a_failure(self):
        with mock.patch("umwayi.archive.atomic_write", self.failing_write(3)):
            self.run_move()
        leftovers = [p for p in self.root.rglob("*") if p.name.startswith(".umwayi-")]
        self.assertEqual(leftovers, [])


# ================================================================= verify


class VerifyTests(ArchiveBase):
    def setUp(self):
        super().setUp()
        self.write("big.md", "".join(f"w{i} x\n" for i in range(1, 10)))
        for _ in range(3):
            self.ok_move("big.md", "--lines", "1-1", "--reason", "r")

    def verify(self):
        return self.run_cli("verify")

    def statuses(self, out):
        return {l.split("  ")[0]: l.split("  ")[1] for l in out.splitlines() if not l.startswith("Checked")}

    def test_all_ok_exit_0(self):
        code, out, err = self.verify()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(self.statuses(out), {"A-0001": "ok", "A-0002": "ok", "A-0003": "ok"})
        self.assertIn("Checked 3 archive files: 3 ok, 0 changed, 0 missing, 0 not in the index", out)

    def test_hand_edit_of_an_archive_file_is_reported_as_changed(self):
        p = self.root / "archive" / "A-0002.txt"
        p.write_bytes(p.read_bytes() + b"x")
        code, out, _ = self.verify()
        self.assertEqual(code, 1)
        self.assertEqual(self.statuses(out), {"A-0001": "ok", "A-0002": "changed", "A-0003": "ok"})

    def test_even_a_one_character_or_line_ending_edit_is_caught(self):
        p = self.root / "archive" / "A-0001.txt"
        original = p.read_bytes()
        for new in [original.replace(b"w1", b"w2"), original.rstrip(b"\n"), original + b"\n", original.replace(b"\n", b"\r\n"), b""]:
            with self.subTest(new=new):
                p.write_bytes(new)
                self.assertEqual(self.verify()[0], 1)
        p.write_bytes(original)
        self.assertEqual(self.verify()[0], 0)

    def test_missing_file(self):
        (self.root / "archive" / "A-0003.txt").unlink()
        code, out, _ = self.verify()
        self.assertEqual(code, 1)
        self.assertEqual(self.statuses(out)["A-0003"], "missing")

    def test_file_not_in_the_index(self):
        self.write("archive/A-0009.txt", "stray words\n")
        self.write("archive/stray.txt", "other words\n")
        (self.root / "archive" / "folder").mkdir()
        code, out, _ = self.verify()
        self.assertEqual(code, 1)
        st = self.statuses(out)
        self.assertEqual(st["A-0009"], "not in the index")
        self.assertEqual(st["stray.txt"], "not in the index")
        self.assertEqual(st["folder"], "not in the index")
        self.assertIn("3 not in the index", out)

    def test_row_deleted_from_the_index_by_hand_shows_the_file_as_not_in_the_index(self):
        kept = [l for l in self.idx.read_text(encoding="utf-8").split("\n") if "| A-0002 |" not in l]
        self.idx.write_text("\n".join(kept), encoding="utf-8")
        code, out, _ = self.verify()
        self.assertEqual(code, 1)
        self.assertEqual(self.statuses(out)["A-0002"], "not in the index")

    def test_fingerprint_edited_in_the_index_is_changed(self):
        text = self.idx.read_text(encoding="utf-8")
        real = self.index_rows()[0].sha256
        self.idx.write_text(text.replace(real, "0" * 64), encoding="utf-8")
        code, out, _ = self.verify()
        self.assertEqual(code, 1)
        self.assertEqual(self.statuses(out)["A-0001"], "changed")

    def test_mixed_results_and_summary(self):
        (self.root / "archive" / "A-0001.txt").unlink()
        p = self.root / "archive" / "A-0002.txt"
        p.write_bytes(b"edited")
        self.write("archive/A-0007.txt", "stray\n")
        code, out, _ = self.verify()
        self.assertEqual(code, 1)
        self.assertEqual(self.statuses(out), {"A-0001": "missing", "A-0002": "changed", "A-0003": "ok", "A-0007": "not in the index"})
        self.assertIn("1 ok, 1 changed, 1 missing, 1 not in the index", out)

    def test_symlinked_archive_file_is_changed(self):
        p = self.root / "archive" / "A-0001.txt"
        data = p.read_bytes()
        p.unlink()
        other = self.write("elsewhere.txt", data)
        try:
            os.symlink(other, p)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not supported")
        code, out, _ = self.verify()
        self.assertEqual(code, 1)
        self.assertEqual(self.statuses(out)["A-0001"], "changed")

    def test_verify_never_changes_any_file(self):
        (self.root / "archive" / "A-0001.txt").unlink()
        (self.root / "archive" / "A-0002.txt").write_bytes(b"edited")
        self.write("archive/A-0009.txt", "stray\n")
        before = self.snap(mtimes=True)
        for _ in range(2):
            self.verify()
        self.assertEqual(self.snap(mtimes=True), before)

    def test_verify_never_changes_files_when_all_ok_either(self):
        before = self.snap(mtimes=True)
        self.assertEqual(self.verify()[0], 0)
        self.assertEqual(self.snap(mtimes=True), before)

    def test_malformed_index_is_an_error_and_changes_nothing(self):
        for text in ["", "no table here\n", INDEX_HEAD + "| A-0001 | x |\n", archive.TEMPLATE + f"| A-0001 | a.md | 2026-13-01 | r | 1 | {SHA_A} |\n"]:
            with self.subTest(text=text[:20]):
                self.idx.write_text(text, encoding="utf-8")
                before = self.snap(mtimes=True)
                code, out, err = self.verify()
                self.assertEqual((code, out), (1, ""))
                self.assertIn("archive index", err)
                self.assertEqual(self.snap(mtimes=True), before)

    def test_missing_index_or_folder_is_an_error(self):
        self.idx.unlink()
        code, out, err = self.verify()
        self.assertEqual((code, out), (1, ""))
        self.assertIn("INDEX.md was not found", err)
        import shutil
        shutil.rmtree(self.root / "archive")
        code, out, err = self.verify()
        self.assertEqual((code, out), (1, ""))
        self.assertIn("no archive folder", err)

    def test_empty_index_with_no_files_is_ok(self):
        import shutil
        shutil.rmtree(self.root / "archive")
        self.write("archive/INDEX.md", archive.TEMPLATE)
        code, out, _ = self.verify()
        self.assertEqual(code, 0)
        self.assertIn("Checked 0 archive files", out)

    def test_verify_extra_args_are_usage_errors(self):
        self.assertEqual(self.run_cli("verify", "--fix")[0], 64)


class SubprocessTests(ArchiveBase):
    def test_real_process_move_verify_and_tamper(self):
        env = dict(os.environ, PYTHONPATH=str(REPO))

        def run(*argv):
            return subprocess.run(
                [sys.executable, "-m", "umwayi", "--root", str(self.root), "archive", *argv],
                capture_output=True, text=True, env=env, cwd=self.root,
            )

        r = run("move", "notes.md", "--start", "old alpha beta", "--end", "old gamma", "--reason", "real run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("umwayi archive restore A-0001", r.stdout)
        self.assertEqual(run("verify").returncode, 0)
        p = self.root / "archive" / "A-0001.txt"
        p.write_text("tampered\n", encoding="utf-8")
        r = run("verify")
        self.assertEqual(r.returncode, 1)
        self.assertIn("A-0001  changed", r.stdout)
        self.assertEqual(run("restore", "A-0001").returncode, 64)
        self.assertEqual(run("move", "notes.md", "--lines", "9-9", "--reason", "r").returncode, 1)


if __name__ == "__main__":
    unittest.main()
