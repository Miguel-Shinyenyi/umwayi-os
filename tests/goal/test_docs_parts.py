"""W9.9 (W9.R14): the shared docs builder, `umwayi goal docs build|check` (umwayi/goaldocs.py).

One status part and one limits part per task; a script builds docs/status-log.md and docs/KNOWN-LIMITS.md from a
frozen base and the parts. Tests first. Planted faults: a number given twice, an order that depends on the file
system, a part that overwrites the base, a bad part skipped silently, a migration that loses a byte.
Standard library only, a temporary folder per test, the system git for the merge tests.
"""

import contextlib
import dataclasses
import io
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from umwayi import goaldocs
from umwayi.cli import main
from tests import test_docs

REPO = Path(__file__).resolve().parents[2]
EM = "\u2014"

SAMPLE_STATUS = """# Status log

## Purpose

Where things stand.

## Current state

### Pull requests

| date | PR | what | tests after it (Python 3.10 to 3.13) |
| --- | --- | --- | --- |
| 2026-11-12 | 2 | second | 20 |
| 2026-11-11 | 1 | first | |

A blank count means the pull request changed no test.

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-10 | d | r |

## Open questions

None open.
"""

SAMPLE_LIMITS = """# Known limits

Intro.

## Area

### 1. First

Body one.

### 2. Second

Body two.
"""

OK_STATUS = "date: 2026-11-14\npr: none\nwhat: Did a thing.\ntests: none\n"
OK_LIMITS = "section: Sec A\ntitle: A limit\n\nBody text.\n"


def status_part(date="2026-11-14", pr="none", what="Did a thing.", tests="none", text=""):
    t = f"date: {date}\npr: {pr}\nwhat: {what}\ntests: {tests}\n"
    return t + (f"\n{text}\n" if text else "")


def limits_part(section="Sec A", title="A limit", body="Body text.", number=None):
    n = f"number: {number}\n" if number is not None else ""
    return f"section: {section}\ntitle: {title}\n{n}\n{body}\n"


def snapshot(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def put(root: Path, rel: str, text, binary=False):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text if binary else text.encode("utf-8"))


def make_root(root: Path, status=SAMPLE_STATUS, limits=SAMPLE_LIMITS) -> Path:
    """A folder with the frozen base made from the two texts, and the two files equal to the base."""
    head, rows, tail = goaldocs.split_status_log(status)
    put(root, "docs-parts/status-log/00-head.md", head)
    put(root, "docs-parts/status-log/00-rows.md", rows)
    put(root, "docs-parts/status-log/00-tail.md", tail)
    put(root, "docs-parts/known-limits/00-base.md", limits)
    put(root, "docs/status-log.md", status)
    put(root, "docs/KNOWN-LIMITS.md", limits)
    return root


def run_cli(root, *argv):
    out, err = io.StringIO(), io.StringIO()
    old = sys.stderr
    sys.stderr = err
    try:
        code = main(["--root", str(root), *argv], out=out)
    finally:
        sys.stderr = old
    return code, out.getvalue(), err.getvalue()


@contextlib.contextmanager
def listing(reverse: bool):
    """The order in which the file system lists docs-parts: ascending or descending by name."""
    real = os.listdir

    def fake(path="."):
        names = real(path)
        return sorted(names, reverse=reverse) if "docs-parts" in str(path) else names

    with mock.patch("os.listdir", fake):
        yield


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = make_root(Path(self._tmp.name) / "r")

    def status(self, name, text):
        put(self.root, f"docs-parts/status-log/{name}.md", text)

    def limits(self, name, text):
        put(self.root, f"docs-parts/known-limits/{name}.md", text)

    def built(self):
        r = goaldocs.build(self.root)
        self.assertEqual((r.code, r.lines[:1]), (0, r.lines[:1]), r.lines)
        return (self.root / "docs/status-log.md").read_text(), (self.root / "docs/KNOWN-LIMITS.md").read_text()


class StatusReaderTests(Base):
    def test_a_good_part_is_read(self):
        p = goaldocs.read_status_part("T-1.md", OK_STATUS.encode())
        self.assertEqual((p.id, p.date, p.pr, p.what, p.tests), ("T-1", "2026-11-14", "none", "Did a thing.", "none"))
        p = goaldocs.read_status_part("T-1.md", status_part(pr="66", tests="1990 on Python 3.11", text="Free.").encode())
        self.assertEqual((p.pr, p.tests), ("66", "1990 on Python 3.11"))

    def test_every_bad_part_is_refused_with_its_file_name(self):
        good = OK_STATUS
        cases = {
            "unknown key": good + "extra: x\n",
            "a number it was not given": good + "number: 5\n",
            "missing key": "date: 2026-11-14\npr: none\nwhat: x\n",
            "key twice": "date: 2026-11-14\npr: none\nwhat: x\nwhat: y\ntests: none\n",
            "keys out of order": "pr: none\ndate: 2026-11-14\nwhat: x\ntests: none\n",
            "date 30 Feb": status_part(date="2026-02-30"),
            "date short": status_part(date="2026-1-1"),
            "date other form": status_part(date="14.11.2026"),
            "pr word": status_part(pr="abc"),
            "pr zero": status_part(pr="0"),
            "pr leading zero": status_part(pr="007"),
            "pr negative": status_part(pr="-1"),
            "pr trailing space": status_part(pr="5 "),
            "pipe in what": status_part(what="a | b"),
            "pipe in tests": status_part(tests="a | b"),
            "em dash in what": status_part(what=f"a {EM} b"),
            "em dash in the free text": status_part(text=f"a {EM} b"),
            "empty value": "date: 2026-11-14\npr: none\nwhat:\ntests: none\n",
            "capital key": good.replace("date", "Date", 1),
            "crlf": good.replace("\n", "\r\n"),
            "byte order mark": "\ufeff" + good,
            "no final newline": good.rstrip("\n"),
            "two final newlines": good + "\n",
            "free text without a blank line": good + "Free text\n",
            "two blank lines before the text": good + "\n\nFree text\n",
            "nul": good.replace("Did", "D\x00id"),
            "empty file": "",
            "too big": status_part(text="x" * 70000),
        }
        for label, text in cases.items():
            with self.subTest(label):
                with self.assertRaises(goaldocs.PartError) as cm:
                    goaldocs.read_status_part("T-1.md", text.encode())
                self.assertNotIn("Did a thing", str(cm.exception))  # never echoes the content

    def test_bytes_that_are_not_utf8_are_refused(self):
        with self.assertRaises(goaldocs.PartError):
            goaldocs.read_status_part("T-1.md", OK_STATUS.encode() + b"\n\xff\xfe\n")


class LimitsReaderTests(Base):
    def test_a_good_part_is_read(self):
        p = goaldocs.read_limits_part("T-1.md", OK_LIMITS.encode())
        self.assertEqual((p.id, p.section, p.title, p.number, p.body), ("T-1", "Sec A", "A limit", None, "Body text."))
        p = goaldocs.read_limits_part("T-1.md", limits_part(number=240, body="a\n\n#### ok\n\n```\n# in code\n```").encode())
        self.assertEqual(p.number, 240)

    def test_every_bad_part_is_refused(self):
        cases = {
            "no body": "section: S\ntitle: T\n",
            "blank body": "section: S\ntitle: T\n\n\n",
            "heading 2 in body": limits_part(body="a\n## h"),
            "heading 3 in body": limits_part(body="a\n### h"),
            "heading 1 in body": limits_part(body="# h"),
            "pipe in title": limits_part(title="a | b"),
            "em dash in title": limits_part(title=f"a {EM} b"),
            "em dash in body": limits_part(body=f"a {EM} b"),
            "section with a hash": limits_part(section="# x"),
            "number zero": limits_part(number=0),
            "number with a leading zero": limits_part(number="012"),
            "number before title": "section: S\nnumber: 240\ntitle: T\n\nB\n",
            "number twice": "section: S\ntitle: T\nnumber: 240\nnumber: 241\n\nB\n",
            "unknown key": "section: S\ntitle: T\ndate: 2026-11-14\n\nB\n",
            "no section": "title: T\n\nB\n",
            "crlf": OK_LIMITS.replace("\n", "\r\n"),
            "no blank line": "section: S\ntitle: T\nBody\n",
        }
        for label, text in cases.items():
            with self.subTest(label):
                with self.assertRaises(goaldocs.PartError):
                    goaldocs.read_limits_part("T-1.md", text.encode())


class DirectoryTests(Base):
    def refused(self, kind="status-log", needle=None):
        before = snapshot(self.root)
        r = goaldocs.build(self.root)
        self.assertEqual(r.code, 2, r.lines)
        self.assertEqual(snapshot(self.root), before, "a refused build writes nothing")
        if needle:
            self.assertTrue(any(needle in line for line in r.lines), r.lines)

    def test_a_name_that_is_not_a_part_is_refused_not_skipped(self):
        for name in ("00-x.md", ".hidden.md", "a.txt", "A_b.md", "x y.md", "-a.md", "README.md", "00-head.md"):
            with self.subTest(name):
                put(self.root, f"docs-parts/known-limits/{name}", "text\n")
                self.refused(needle=name)
                (self.root / "docs-parts/known-limits" / name).unlink()

    def test_a_folder_and_a_link_are_refused(self):
        (self.root / "docs-parts/status-log/sub").mkdir()
        self.refused(needle="sub")
        (self.root / "docs-parts/status-log/sub").rmdir()
        self.status("real", OK_STATUS)
        os.symlink(self.root / "docs-parts/status-log/real.md", self.root / "docs-parts/status-log/link.md")
        self.refused(needle="link.md")

    def test_a_bad_part_next_to_a_good_one_refuses_the_build(self):
        self.status("T-1", OK_STATUS)
        self.status("T-2", OK_STATUS + "extra: x\n")
        self.refused(needle="docs-parts/status-log/T-2.md")
        self.assertEqual((self.root / "docs/status-log.md").read_text(), SAMPLE_STATUS)

    def test_ids_that_differ_only_in_case_are_two_parts_for_one_task(self):
        self.status("T-1", OK_STATUS)
        self.status("t-1", OK_STATUS)
        self.refused(needle="t-1")

    def test_a_missing_folder_or_base_file_is_refused(self):
        for rel in ("docs-parts/status-log/00-head.md", "docs-parts/status-log/00-rows.md",
                    "docs-parts/status-log/00-tail.md", "docs-parts/known-limits/00-base.md"):
            with self.subTest(rel):
                saved = (self.root / rel).read_bytes()
                (self.root / rel).unlink()
                self.refused(needle=rel)
                put(self.root, rel, saved, binary=True)
        shutil.rmtree(self.root / "docs-parts/status-log")
        self.refused()

    def test_a_damaged_base_is_refused(self):
        rel = "docs-parts/status-log/00-tail.md"
        put(self.root, rel, "something else\n")
        self.refused(needle=rel)

    def test_a_shared_file_that_is_a_link_is_refused(self):
        self.status("T-1", OK_STATUS)
        (self.root / "other.md").write_text("x\n")
        (self.root / "docs/status-log.md").unlink()
        os.symlink(self.root / "other.md", self.root / "docs/status-log.md")
        self.refused(needle="docs/status-log.md")


class StatusBuildTests(Base):
    def test_rows_come_newest_first_above_the_old_rows(self):
        self.status("a", status_part(date="2026-11-14", pr="66", what="A row."))
        self.status("b", status_part(date="2026-11-14", pr="none", what="B row."))
        self.status("c", status_part(date="2026-11-15", pr="3", what="C row.", tests="1990 on Python 3.11"))
        self.status("d", status_part(date="2026-11-14", pr="66", what="D row."))
        text, _ = self.built()
        order = ["C row.", "D row.", "A row.", "B row.", "| second |"]
        self.assertEqual(sorted(order, key=text.index), order)
        self.assertIn("| 2026-11-15 | 3 | C row. | 1990 on Python 3.11 |\n", text)
        self.assertIn("| 2026-11-14 | see the pull request | B row. | |\n", text)
        self.assertIn("\n\nA blank count means the pull request changed no test.\n", text)

    def test_nothing_else_of_the_file_changes(self):
        self.status("a", status_part())
        text, _ = self.built()
        head, rows, tail = goaldocs.split_status_log(SAMPLE_STATUS)
        self.assertTrue(text.startswith(head))
        self.assertTrue(text.endswith(rows + "\n" + tail))

    def test_a_link_that_does_not_resolve_refuses_the_build(self):
        self.status("a", status_part(what="See [x](nope.md)."))
        before = snapshot(self.root)
        r = goaldocs.build(self.root)
        self.assertEqual(r.code, 2)
        self.assertEqual(snapshot(self.root), before)
        self.status("a", status_part(what="See [x](KNOWN-LIMITS.md#1-first)."))
        self.assertEqual(goaldocs.build(self.root).code, 0)


class LimitsBuildTests(Base):
    def pair(self, name, date="2026-11-14", **kw):
        self.status(name, status_part(date=date))
        self.limits(name, limits_part(**kw))

    def test_numbers_start_after_the_base_and_at_least_213(self):
        self.pair("a", title="One")
        _, lim = self.built()
        self.assertIn("\n## Sec A\n\n### 213. One\n\nBody text.\n", lim)
        self.assertTrue(lim.startswith(SAMPLE_LIMITS))
        # a base that already passed 212 goes on from its own largest number
        root = make_root(Path(self._tmp.name) / "big", limits=SAMPLE_LIMITS + "\n### 236. Last\n\nBody.\n")
        put(root, "docs-parts/status-log/a.md", status_part())
        put(root, "docs-parts/known-limits/a.md", limits_part(title="One"))
        self.assertEqual(goaldocs.build(root).code, 0)
        self.assertIn("### 237. One", (root / "docs/KNOWN-LIMITS.md").read_text())

    def test_the_build_writes_the_number_into_the_part_and_keeps_it(self):
        self.pair("b", date="2026-11-14", title="Bee")
        self.pair("z", date="2026-11-13", title="Zed")
        self.built()
        self.assertEqual((self.root / "docs-parts/known-limits/z.md").read_text(),
                         "section: Sec A\ntitle: Zed\nnumber: 213\n\nBody text.\n")  # the older date first
        self.assertIn("number: 214\n", (self.root / "docs-parts/known-limits/b.md").read_text())
        # a part changed after its number was given keeps it; a newer part goes after; an older one does not take 213
        self.limits("z", limits_part(title="Zed changed", body="New body.", number=213))
        self.pair("m", date="2026-11-01", title="Old date")
        _, lim = self.built()
        self.assertIn("### 213. Zed changed\n\nNew body.", lim)
        self.assertIn("### 214. Bee", lim)
        self.assertIn("### 215. Old date", lim)

    def test_the_same_date_is_ordered_by_id(self):
        self.pair("b", title="Bee")
        self.pair("a", title="Ay")
        _, lim = self.built()
        self.assertLess(lim.index("### 213. Ay"), lim.index("### 214. Bee"))

    def test_sections_come_in_the_order_of_their_first_part(self):
        self.pair("a", section="Second area", title="A")
        self.pair("b", section="Third area", title="B")
        self.pair("c", section="Second area", title="C")
        _, lim = self.built()
        self.assertEqual(lim.count("## Second area"), 1)
        self.assertLess(lim.index("## Second area"), lim.index("## Third area"))

    def test_two_builds_in_a_row_are_identical_and_the_second_changes_nothing(self):
        self.pair("a")
        self.status("b", status_part(date="2026-11-15"))
        self.built()
        first = snapshot(self.root)
        r = goaldocs.build(self.root)
        self.assertEqual(r.code, 0)
        self.assertEqual(snapshot(self.root), first)

    def test_refusals_about_numbers_and_sections(self):
        cases = {
            "a number below the base": limits_part(number=2),
            "a number with a gap": limits_part(number=500),
            "a limits part without a status part": None,
            "a section the base already has": limits_part(section="Area"),
        }
        for label, text in cases.items():
            with self.subTest(label):
                self.status("a", status_part())
                if label == "a limits part without a status part":
                    (self.root / "docs-parts/status-log/a.md").unlink()
                    text = limits_part()
                self.limits("a", text)
                before = snapshot(self.root)
                self.assertEqual(goaldocs.build(self.root).code, 2)
                self.assertEqual(snapshot(self.root), before)
                (self.root / "docs-parts/known-limits/a.md").unlink()
                (self.root / "docs-parts/status-log/a.md").unlink(missing_ok=True)

    def test_two_parts_with_one_number_or_a_gap_are_refused(self):
        self.pair("a", number=213)
        self.pair("b", number=213)
        self.assertEqual(goaldocs.build(self.root).code, 2)
        self.limits("b", limits_part(number=215))
        self.assertEqual(goaldocs.build(self.root).code, 2)  # 213 and 215: 214 is missing
        self.limits("b", limits_part(number=214))
        self.assertEqual(goaldocs.build(self.root).code, 0)


class CheckTests(Base):
    def test_check_is_0_when_equal_and_2_when_not_and_writes_nothing(self):
        self.assertEqual(goaldocs.check(self.root).code, 0)  # the base alone equals the files
        put(self.root, "docs-parts/status-log/a.md", status_part())
        put(self.root, "docs-parts/known-limits/a.md", limits_part())
        before = snapshot(self.root)
        r = goaldocs.check(self.root)
        self.assertEqual(r.code, 2)
        self.assertTrue(any("not yet built" in line or "differs" in line for line in r.lines), r.lines)
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(goaldocs.build(self.root).code, 0)
        self.assertEqual(goaldocs.check(self.root).code, 0)

    def test_a_hand_edit_of_a_shared_file_is_found(self):
        self.assertEqual(goaldocs.check(self.root).code, 0)
        p = self.root / "docs/status-log.md"
        p.write_text(p.read_text().replace("| 2026-11-12 | 2 |", "| 2026-11-12 | 3 |"))
        r = goaldocs.check(self.root)
        self.assertEqual(r.code, 2)
        self.assertTrue(any("docs/status-log.md" in line for line in r.lines), r.lines)

    def test_a_missing_shared_file_is_found(self):
        (self.root / "docs/KNOWN-LIMITS.md").unlink()
        self.assertEqual(goaldocs.check(self.root).code, 2)

    def test_a_limits_part_without_its_number_is_not_built_even_if_the_files_match(self):
        put(self.root, "docs-parts/status-log/a.md", status_part())
        put(self.root, "docs-parts/known-limits/a.md", limits_part())
        self.assertEqual(goaldocs.build(self.root).code, 0)
        put(self.root, "docs-parts/known-limits/a.md", limits_part())  # the number line is lost
        r = goaldocs.check(self.root)
        self.assertEqual(r.code, 2)
        self.assertTrue(any("1 part not yet built" in line for line in r.lines), r.lines)

    def test_a_bad_part_makes_check_2(self):
        put(self.root, "docs-parts/status-log/a.md", "junk\n")
        self.assertEqual(goaldocs.check(self.root).code, 2)


class OutputCheckerTests(Base):
    def test_the_checker_finds_each_problem(self):
        ok_s, ok_l = SAMPLE_STATUS, SAMPLE_LIMITS
        self.assertEqual(goaldocs.check_output(self.root, ok_s, ok_l), [])
        bad = {
            "em dash": (ok_s + f"a {EM} b\n", ok_l),
            "dead link": (ok_s.replace("None open.", "[x](gone.md)"), ok_l),
            "dead anchor": (ok_s.replace("None open.", "[x](KNOWN-LIMITS.md#nope)"), ok_l),
            "a part missing": (ok_s.replace("## Open questions", "## Other"), ok_l),
            "parts out of order": (ok_s.replace("## Purpose", "## Open questions", 1), ok_l),
            "too long": (ok_s + "x\n" * 300, ok_l),
            "em dash in limits": (ok_s, ok_l + f"a {EM} b\n"),
        }
        for label, (s, lim) in bad.items():
            with self.subTest(label):
                self.assertTrue(goaldocs.check_output(self.root, s, lim), label)
        self.assertEqual(goaldocs.check_output(self.root, ok_s.replace("None open.", "[x](KNOWN-LIMITS.md#2-second)"), ok_l), [])

    def test_the_real_repo_plans_and_its_output_passes_the_docs_checker(self):
        plan = goaldocs.plan(REPO)
        self.assertEqual(goaldocs.check_output(REPO, plan.status, plan.limits), [])

    def test_the_checker_agrees_with_tests_test_docs_on_the_real_files(self):
        """check_output is a second copy of the rules of tests/test_docs.py; the helpers must not drift apart."""
        texts = [(REPO / "docs/status-log.md").read_text(encoding="utf-8"),
                 (REPO / "docs/KNOWN-LIMITS.md").read_text(encoding="utf-8"), SAMPLE_STATUS, SAMPLE_LIMITS]
        for text in texts:
            self.assertEqual(goaldocs._links(text), test_docs.links(text))
            self.assertEqual(goaldocs._anchors(text), test_docs.anchors(text))
            self.assertEqual(goaldocs._outside_code(text), test_docs.outside_code(text))
        self.assertEqual(goaldocs.EM_DASH, test_docs.EM_DASH)
        self.assertEqual(goaldocs.DOC_PARTS, test_docs.PARTS)
        self.assertEqual(goaldocs.MAX_STATUS_LINES, test_docs.DOC_MAX_LINES)


class MigrationTests(unittest.TestCase):
    """The first build reproduces today's two files byte for byte (W9.R14.6), on a copy of both real files."""

    def split_and_compose(self, status, limits):
        head, rows, tail = goaldocs.split_status_log(status)
        return goaldocs.compose_status(head, rows, tail, []), goaldocs.compose_limits(limits, [])

    def test_the_real_files_split_and_rebuild_byte_for_byte(self):
        status = (REPO / "docs/status-log.md").read_bytes().decode("utf-8")
        limits = (REPO / "docs/KNOWN-LIMITS.md").read_bytes().decode("utf-8")
        self.assertEqual(self.split_and_compose(status, limits), (status, limits))

    def test_the_sample_files_too(self):
        self.assertEqual(self.split_and_compose(SAMPLE_STATUS, SAMPLE_LIMITS), (SAMPLE_STATUS, SAMPLE_LIMITS))

    def test_a_text_that_does_not_split_is_refused(self):
        for text in ("no table\n", SAMPLE_STATUS.replace("A blank count means", "Other"),
                     SAMPLE_STATUS.replace("| --- | --- | --- | --- |", "| --- |", 1)):
            with self.assertRaises(goaldocs.PartError):
                goaldocs.split_status_log(text)

    def test_planted_fault_a_migration_that_loses_a_byte_is_found(self):
        real = goaldocs.split_status_log

        def lossy(text):
            head, rows, tail = real(text)
            return head, rows.rstrip("\n"), tail  # drops the last newline of the rows

        with mock.patch.object(goaldocs, "split_status_log", lossy):
            got = self.split_and_compose(SAMPLE_STATUS, SAMPLE_LIMITS)
        self.assertNotEqual(got, (SAMPLE_STATUS, SAMPLE_LIMITS))

    def test_planted_fault_a_base_with_one_changed_byte_is_found_by_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            self.assertEqual(goaldocs.check(root).code, 0)
            p = root / "docs-parts/known-limits/00-base.md"
            p.write_bytes(p.read_bytes().replace(b"Body one.", b"Body one "))
            self.assertEqual(goaldocs.check(root).code, 2)


def random_parts(root: Path, seed: int):
    rnd = random.Random(seed)
    sections = ["Alpha area", "Beta area", "Gamma area"]
    days = ["2026-11-1%d" % d for d in range(2, 8)]
    for i in range(rnd.randint(0, 7)):
        name = "G-%04d-T-%02d" % (rnd.randint(1, 9), i)
        put(root, f"docs-parts/status-log/{name}.md", status_part(
            date=rnd.choice(days), pr=rnd.choice(["none", str(rnd.randint(1, 99))]), what=f"Row {seed} {i}.",
            tests=rnd.choice(["none", "1990 on Python 3.11"]), text=rnd.choice(["", "Free text."])))
        if rnd.random() < 0.6:
            put(root, f"docs-parts/known-limits/{name}.md", limits_part(
                section=rnd.choice(sections), title=f"Limit {seed} {i}", body="Text.\n\n- one\n- two"))


def invariant_problems(base: Path) -> list:
    """Build the same parts created in two orders, with the folder listed in two orders. Empty when all is well."""
    problems = []
    outs = []
    for k, reverse in enumerate((False, True)):
        root = make_root(base / f"inv{k}")
        for name, status, limits in [
            ("a", status_part(date="2026-11-14", what="A."), limits_part(title="A", section="S1")),
            ("b", status_part(date="2026-11-14", what="B."), limits_part(title="B", section="S2")),
            ("c", status_part(date="2026-11-14", what="C."), limits_part(title="C", section="S1")),
            ("d", status_part(date="2026-11-13", what="D."), None),
        ][:: -1 if reverse else 1]:
            put(root, f"docs-parts/status-log/{name}.md", status)
            if limits:
                put(root, f"docs-parts/known-limits/{name}.md", limits)
        with listing(reverse):
            r = goaldocs.build(root)
            if r.code != 0:
                problems.append("build refused: " + " ".join(r.lines))
                continue
            first = snapshot(root)
            goaldocs.build(root)
            if snapshot(root) != first:
                problems.append("a second build changed something")
        outs.append((root / "docs/status-log.md").read_text() + (root / "docs/KNOWN-LIMITS.md").read_text())
        lim = (root / "docs/KNOWN-LIMITS.md").read_text()
        nums = re.findall(r"^### (\d+)\. ", lim, re.M)
        if len(nums) != len(set(nums)):
            problems.append("a number is used twice")
        if not lim.startswith(SAMPLE_LIMITS):
            problems.append("the limits base is not at the start")
        head, rows, tail = goaldocs.split_status_log(SAMPLE_STATUS)
        st = (root / "docs/status-log.md").read_text()
        if not (st.startswith(head) and st.endswith(rows + "\n" + tail)):
            problems.append("the status head, old rows or tail changed")
    if len(outs) == 2 and outs[0] != outs[1]:
        problems.append("the output depends on the order of the files")
    return problems


class InvariantTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def test_the_real_builder_keeps_every_invariant(self):
        self.assertEqual(invariant_problems(self.base), [])

    def test_planted_fault_a_number_written_twice_is_found(self):
        with mock.patch.object(goaldocs, "assign_numbers", lambda ids, start: {i: start for i in ids}):
            self.assertTrue(invariant_problems(self.base))

    def test_planted_fault_an_order_that_depends_on_the_file_system_is_found(self):
        def weak(part):
            return (part.date,)

        with mock.patch.object(goaldocs, "list_names", lambda d: os.listdir(d)), \
                mock.patch.object(goaldocs, "status_key", weak), \
                mock.patch.object(goaldocs, "limits_key", lambda *a: ("x",)):
            self.assertTrue(invariant_problems(self.base))

    def test_planted_fault_a_part_that_overwrites_the_base_is_found(self):
        with mock.patch.object(goaldocs, "compose_limits", lambda base, parts: "\n".join(p.title for p in parts)):
            self.assertTrue(invariant_problems(self.base))

    def test_planted_fault_a_bad_part_skipped_silently_is_found(self):
        real = goaldocs.parse_dir

        def skipping(root, kind):
            parts, _problems = real(root, kind)
            return parts, []

        root = make_root(self.base / "r")
        put(root, "docs-parts/status-log/bad.md", "junk\n")
        self.assertEqual(goaldocs.build(root).code, 2)  # the real reader refuses
        with mock.patch.object(goaldocs, "parse_dir", skipping):
            self.assertEqual(goaldocs.build(root).code, 0)  # the planted fault would build: the line above is the guard


class RandomSetTests(unittest.TestCase):
    def test_sixty_random_sets_build_and_pass_the_checker_in_any_order(self):
        for seed in range(60):
            with self.subTest(seed=seed), tempfile.TemporaryDirectory() as tmp:
                a = make_root(Path(tmp) / "a")
                b = make_root(Path(tmp) / "b")
                random_parts(a, seed)
                names = sorted(p.relative_to(a) for p in (a / "docs-parts").rglob("*.md") if not p.name.startswith("00-"))
                random.Random(seed + 1000).shuffle(names)
                for rel in names:
                    put(b, str(rel), (a / rel).read_bytes(), binary=True)
                r = goaldocs.build(a)
                self.assertEqual(r.code, 0, r.lines)
                with listing(True):
                    self.assertEqual(goaldocs.build(b).code, 0)
                for f in ("docs/status-log.md", "docs/KNOWN-LIMITS.md"):
                    self.assertEqual((a / f).read_bytes(), (b / f).read_bytes())
                plan = goaldocs.plan(a)
                self.assertEqual(goaldocs.check_output(a, plan.status, plan.limits), [])
                self.assertEqual(goaldocs.check(a).code, 0)
                self.assertEqual(snapshot(a / "docs-parts"), snapshot(b / "docs-parts"))


GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="t",
               GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")


def git(root, *args, check=True):
    r = subprocess.run(["git", *args], cwd=root, env=GIT_ENV, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise AssertionError(f"git {args}: {r.stderr}")
    return r


@unittest.skipUnless(shutil.which("git"), "git is needed")
class GitMergeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = make_root(Path(self._tmp.name))
        git(self.root, "init", "-q")
        git(self.root, "checkout", "-q", "-b", "main")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "base")

    def branch(self, name, edit):
        git(self.root, "checkout", "-q", "-b", name, "main")
        edit()
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", name)

    def test_two_branches_that_add_only_their_own_parts_merge_without_a_conflict(self):
        for n in ("t1", "t2"):
            self.branch(n, lambda n=n: (put(self.root, f"docs-parts/status-log/{n}.md", status_part(what=f"Row {n}.")),
                                        put(self.root, f"docs-parts/known-limits/{n}.md", limits_part(title=f"Limit {n}"))))
        git(self.root, "checkout", "-q", "main")
        git(self.root, "merge", "-q", "--no-edit", "t1")
        git(self.root, "merge", "-q", "--no-edit", "t2")
        self.assertEqual(goaldocs.build(self.root).code, 0)
        lim = (self.root / "docs/KNOWN-LIMITS.md").read_text()
        self.assertIn("### 213. Limit t1", lim)
        self.assertIn("### 214. Limit t2", lim)

    def test_control_the_same_branches_editing_the_shared_files_do_conflict(self):
        for n in ("t1", "t2"):
            def edit(n=n):
                p = self.root / "docs/status-log.md"
                p.write_text(p.read_text().replace("| --- | --- | --- | --- |\n", f"| --- | --- | --- | --- |\n| 2026-11-14 | none | {n} | |\n"))
            self.branch(n, edit)
        git(self.root, "checkout", "-q", "main")
        git(self.root, "merge", "-q", "--no-edit", "t1")
        self.assertNotEqual(git(self.root, "merge", "-q", "--no-edit", "t2", check=False).returncode, 0)


class CliTests(Base):
    def test_build_and_check_through_the_command(self):
        self.status("a", status_part())
        code, out, err = run_cli(self.root, "goal", "docs", "check")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("docs", err)
        code, out, err = run_cli(self.root, "goal", "docs", "build")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("docs/status-log.md", out)
        self.assertEqual(run_cli(self.root, "goal", "docs", "check")[0], 0)

    def test_a_refusal_is_exit_2_never_1_and_says_which_file(self):
        self.status("a", "junk\n")
        code, out, err = run_cli(self.root, "goal", "docs", "build")
        self.assertEqual(code, 2)
        self.assertIn("docs-parts/status-log/a.md", err)
        self.assertEqual(run_cli(self.root, "goal", "docs", "check")[0], 2)

    def test_the_goal_command_has_only_docs_and_wrong_use_is_64(self):
        for argv in (["goal"], ["goal", "docs"], ["goal", "docs", "x"], ["goal", "docs", "build", "extra"],
                     ["goal", "start", "text"], ["goal", "frobnicate"], ["goal", "docs", "build", "--out", "x"]):
            with self.subTest(argv=argv):
                before = snapshot(self.root)
                code, out, _ = run_cli(self.root, *argv)
                self.assertEqual((code, out), (64, ""))
                self.assertEqual(snapshot(self.root), before)

    def test_a_root_without_docs_parts_is_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_cli(tmp, "goal", "docs", "build")[0], 2)
            self.assertEqual(run_cli(tmp, "goal", "docs", "check")[0], 2)
            self.assertEqual(os.listdir(tmp), [])


class SourceTests(unittest.TestCase):
    def test_the_module_is_standard_library_only(self):
        src = (REPO / "umwayi/goaldocs.py").read_text()
        mods = set(re.findall(r"^(?:from|import) ([a-zA-Z_]+)", src, re.M))
        self.assertLessEqual(mods, {"__future__", "dataclasses", "os", "re", "stat", "pathlib", "datetime"} | {"umwayi"})

    def test_no_em_dash_in_the_module_or_the_parts(self):
        files = [REPO / "umwayi/goaldocs.py", Path(__file__)]
        files += [p for p in (REPO / "docs-parts").rglob("*.md")] if (REPO / "docs-parts").is_dir() else []
        for p in files:
            self.assertNotIn(EM, p.read_text(encoding="utf-8"), p.name)


if __name__ == "__main__":
    unittest.main()
