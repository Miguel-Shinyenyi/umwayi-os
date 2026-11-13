"""W19 part 2: umwayi/concerns.py and `umwayi concerns check PATH`.

The code checks that a record exists and is well formed. It never claims the content is true.
"""

import io
import os
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from umwayi import concerns
from umwayi.cli import main

REPO = Path(__file__).resolve().parent.parent
HEADER = "| number | concept | answer | reason | evidence | date |\n| --- | --- | --- | --- | --- | --- |\n"


def row(n, answer="Not applicable", reason="This project has no such part.", evidence="", date="2026-11-13",
        concept=None):
    name = concept if concept is not None else concepts_name(n)
    return f"| {n} | {name} | {answer} | {reason} | {evidence} | {date} |\n"


def concepts_name(n):
    return concerns.CONCEPTS[n - 1] if 1 <= n <= 111 else "Outside"


def record(rows=None, header=HEADER, skip=(), extra=""):
    """A valid record text, with the numbers in skip left out and extra text added at the end."""
    body = rows if rows is not None else "".join(row(n) for n in range(1, 112) if n not in skip)
    return "# Concerns\n\nSome words.\n\n" + header + body + extra


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.root = Path(self._t.name).resolve()
        (self.root / "docs").mkdir()
        (self.root / "docs" / "proof.md").write_text("proof\n")

    def write(self, text, name="concerns.md"):
        p = self.root / name
        p.write_text(text, encoding="utf-8")
        return p

    def failures(self, text):
        return concerns.check_text(text, self.root)

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--root", str(self.root), *argv])
        return code, out.getvalue(), err.getvalue()


class TheList(unittest.TestCase):
    def test_exactly_111_entries_numbered_1_to_111_with_no_gap(self):
        self.assertEqual(len(concerns.CONCEPTS), 111)
        numbered = concerns.numbered_concepts()
        self.assertEqual([n for n, _ in numbered], list(range(1, 112)))
        self.assertEqual([name for _, name in numbered], list(concerns.CONCEPTS))

    def test_names_are_unique_and_plain(self):
        self.assertEqual(len(set(concerns.CONCEPTS)), 111)
        for name in concerns.CONCEPTS:
            self.assertEqual(name, name.strip())
            self.assertTrue(name)
            self.assertNotIn("|", name)

    def test_the_hub_doc_numbering(self):
        c = concerns.CONCEPTS
        for n, name in ((1, "Rate limiting"), (14, "Idempotency"), (34, "CAP theorem"), (57, "Liveness and readiness probes"),
                        (70, "JWT rotation"), (93, "P99 latency"), (98, "TCP vs UDP"), (99, "HTTP/2 and HTTP/3"),
                        (105, "Terraform"), (111, "Postmortems")):
            self.assertEqual(c[n - 1], name)


class Failures(Base):
    def test_valid_record_has_no_failure(self):
        self.assertEqual(self.failures(record()), [])

    def test_valid_record_with_applies_and_deferred(self):
        rows = "".join(row(n) for n in range(3, 112))
        rows = row(1, "Applies", "The gate limits calls.", "docs/proof.md") + row(2, "Deferred", "Not before launch.") + rows
        self.assertEqual(self.failures(record(rows)), [])

    def test_missing_number(self):
        f = self.failures(record(skip=(7,)))
        self.assertEqual(len(f), 1)
        self.assertIn("7", f[0])
        self.assertIn("missing", f[0])

    def test_every_number_missing_is_listed(self):
        f = self.failures(record(skip=(1, 50, 111)))
        self.assertEqual(len(f), 3)

    def test_duplicate_number(self):
        f = self.failures(record(extra=row(5)))
        self.assertEqual(len(f), 1)
        self.assertIn("duplicate", f[0])

    def test_number_outside_range(self):
        for bad in ("0", "112", "1000"):
            with self.subTest(bad=bad):
                f = self.failures(record(extra=row(bad, concept="X")))
                self.assertEqual(len(f), 1, f)
                self.assertIn("outside 1 to 111", f[0])

    def test_number_not_a_plain_number(self):
        for bad in ("abc", "-1", "1.5", "007", "", "１"):
            with self.subTest(bad=bad):
                f = self.failures(record(extra=row(bad, concept="X")))
                self.assertEqual(len(f), 1, f)

    def test_number_with_leading_zero_is_not_a_plain_number(self):
        rows = row("007", concept="Idempotency") + "".join(row(n) for n in range(1, 112) if n != 7)
        f = self.failures(record(rows))
        self.assertTrue(any("plain whole number" in line for line in f), f)

    def test_answer_outside_the_three(self):
        for bad in ("Yes", "applies", "Not Applicable", "N/A", "", "Applies.", "Not  applicable"):
            with self.subTest(bad=bad):
                rows = row(1, bad) + "".join(row(n) for n in range(2, 112))
                f = self.failures(record(rows))
                self.assertEqual(len(f), 1, f)
                self.assertIn("answer", f[0])

    def test_empty_or_whitespace_reason(self):
        for bad in ("", "   ", "\t"):
            with self.subTest(bad=repr(bad)):
                rows = row(1, reason=bad) + "".join(row(n) for n in range(2, 112))
                f = self.failures(record(rows))
                self.assertEqual(len(f), 1, f)
                self.assertIn("reason", f[0])

    def test_applies_with_no_evidence(self):
        rows = row(1, "Applies", "It does.", "") + "".join(row(n) for n in range(2, 112))
        f = self.failures(record(rows))
        self.assertEqual(len(f), 1)
        self.assertIn("evidence", f[0])

    def test_applies_with_evidence_path_that_does_not_exist(self):
        rows = row(1, "Applies", "It does.", "docs/nope.md") + "".join(row(n) for n in range(2, 112))
        f = self.failures(record(rows))
        self.assertEqual(len(f), 1)
        self.assertIn("evidence", f[0])

    def test_applies_with_a_folder_as_evidence_is_refused(self):
        rows = row(1, "Applies", "It does.", "docs") + "".join(row(n) for n in range(2, 112))
        self.assertEqual(len(self.failures(record(rows))), 1)

    def test_malformed_date(self):
        for bad in ("", "13-11-2026", "2026-13-01", "2026-02-30", "2026-1-1", "yesterday", "2026-11-13T10:00", "٢٠٢٦-١١-١٣"):
            with self.subTest(bad=bad):
                rows = row(1, date=bad) + "".join(row(n) for n in range(2, 112))
                f = self.failures(record(rows))
                self.assertEqual(len(f), 1, f)
                self.assertIn("date", f[0])

    def test_concept_name_must_match_the_number(self):
        rows = row(1, concept="Caching") + "".join(row(n) for n in range(2, 112))
        f = self.failures(record(rows))
        self.assertEqual(len(f), 1)
        self.assertIn("concept", f[0])

    def test_wrong_column_count(self):
        rows = "| 1 | Rate limiting | Deferred | later | 2026-11-13 |\n" + "".join(row(n) for n in range(2, 112))
        f = self.failures(record(rows))
        self.assertTrue(any("columns" in line for line in f))

    def test_wrong_header_or_none(self):
        for header in ("| number | concept | answer | reason | evidence |\n| --- | --- | --- | --- | --- |\n", "", HEADER.replace("number", "no")):
            with self.subTest(header=header):
                f = self.failures(record(header=header))
                self.assertTrue(f)

    def test_separator_row_is_required(self):
        f = self.failures(record(header=HEADER.split("\n")[0] + "\n"))
        self.assertTrue(f)

    def test_empty_text(self):
        self.assertTrue(self.failures(""))

    def test_a_second_table_is_refused(self):
        f = self.failures(record(extra="\ntext\n\n" + HEADER + row(1)))
        self.assertTrue(f)

    def test_failure_lines_never_echo_file_content(self):
        secret = "sk-live-TOPSECRET"
        rows = row(1, "Maybe " + secret, secret, secret, secret) + "".join(row(n) for n in range(2, 112))
        rows += row(112, concept=secret) + f"| {secret} |\n"
        out = "\n".join(self.failures(record(rows)))
        self.assertNotIn(secret, out)

    def test_one_line_per_failure_and_no_em_dash(self):
        f = self.failures(record(skip=(1, 2), extra=row(5)))
        for line in f:
            self.assertNotIn("\n", line)
            self.assertNotIn("\u2014", line)


class EvidenceStaysInTheRepo(Base):
    def applies(self, evidence):
        rows = row(1, "Applies", "It does.", evidence) + "".join(row(n) for n in range(2, 112))
        return self.failures(record(rows))

    def test_a_file_inside_the_repo_is_accepted(self):
        self.assertEqual(self.applies("docs/proof.md"), [])

    def test_parent_directory_escape_is_refused(self):
        outside = self.root.parent / "outside-evidence.txt"
        outside.write_text("x")
        self.addCleanup(outside.unlink)
        for ev in ("../outside-evidence.txt", "docs/../../outside-evidence.txt", "docs/../docs/proof.md", "./../outside-evidence.txt"):
            with self.subTest(ev=ev):
                self.assertEqual(len(self.applies(ev)), 1)

    def test_absolute_path_is_refused_even_when_it_is_inside_the_repo(self):
        self.assertEqual(len(self.applies(str(self.root / "docs" / "proof.md"))), 1)
        self.assertEqual(len(self.applies("/etc/hostname")), 1)
        self.assertEqual(len(self.applies("/etc/passwd")), 1)

    def test_symlink_out_of_the_repo_is_refused(self):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(outside, ignore_errors=True))
        (outside / "secret.txt").write_text("x")
        os.symlink(outside / "secret.txt", self.root / "docs" / "link.txt")
        os.symlink(outside, self.root / "linkdir")
        self.assertEqual(len(self.applies("docs/link.txt")), 1)
        self.assertEqual(len(self.applies("linkdir/secret.txt")), 1)

    def test_symlink_that_stays_inside_the_repo_is_accepted(self):
        os.symlink(self.root / "docs" / "proof.md", self.root / "docs" / "inner.md")
        self.assertEqual(self.applies("docs/inner.md"), [])

    def test_odd_paths_are_refused(self):
        for ev in ("~/x", "docs\\proof.md", "docs/proof.md\x00", "C:/x", "\\\\host\\share", "file:///etc/passwd"):
            with self.subTest(ev=ev):
                self.assertEqual(len(self.applies(ev)), 1)

    def test_a_dangling_symlink_is_refused(self):
        os.symlink(self.root / "nowhere", self.root / "docs" / "dangling.md")
        self.assertEqual(len(self.applies("docs/dangling.md")), 1)

    def test_evidence_is_not_read(self):
        # the checker only asks that the file exists; a fifo or other special file is not regular, so it is refused
        if not hasattr(os, "mkfifo"):
            self.skipTest("no fifo")
        os.mkfifo(self.root / "docs" / "pipe")
        self.assertEqual(len(self.applies("docs/pipe")), 1)


class Command(Base):
    def test_exit_0_on_valid(self):
        p = self.write(record())
        code, out, err = self.cli("concerns", "check", str(p))
        self.assertEqual((code, err), (0, ""))
        self.assertIn("111", out)

    def test_exit_2_on_invalid_with_one_line_per_failure(self):
        p = self.write(record(skip=(3, 4), extra=row(9)))
        code, out, err = self.cli("concerns", "check", str(p))
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertEqual(len([ln for ln in err.splitlines() if ln]), 3)

    def test_relative_path_is_read_from_the_current_folder(self):
        self.write(record())
        old = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, old)
        self.assertEqual(self.cli("concerns", "check", "concerns.md")[0], 0)

    def test_missing_file_is_2(self):
        code, _, err = self.cli("concerns", "check", str(self.root / "nope.md"))
        self.assertEqual(code, 2)
        self.assertTrue(err.strip())

    def test_a_folder_not_a_file_is_2(self):
        self.assertEqual(self.cli("concerns", "check", str(self.root / "docs"))[0], 2)

    def test_not_utf8_is_2(self):
        p = self.root / "bad.md"
        p.write_bytes(b"\xff\xfe\x00bad")
        self.assertEqual(self.cli("concerns", "check", str(p))[0], 2)

    def test_too_big_is_2(self):
        p = self.write("x" * (concerns.MAX_BYTES + 1))
        self.assertEqual(self.cli("concerns", "check", str(p))[0], 2)

    def test_usage_errors_are_64(self):
        for argv in (["concerns"], ["concerns", "check"], ["concerns", "check", "a", "b"], ["concerns", "audit", "a"]):
            with self.subTest(argv=argv):
                self.assertEqual(self.cli(*argv)[0], 64)

    def test_a_crash_is_2_and_prints_no_text(self):
        p = self.write(record())
        with mock.patch("umwayi.cli.concerns.check_file", side_effect=RuntimeError("sk-live-TOPSECRET")):
            code, out, err = self.cli("concerns", "check", str(p))
        self.assertEqual(code, 2)
        self.assertNotIn("TOPSECRET", out + err)

    def test_changes_nothing(self):
        p = self.write(record())
        before = sorted(str(x) for x in self.root.rglob("*"))
        self.cli("concerns", "check", str(p))
        self.assertEqual(before, sorted(str(x) for x in self.root.rglob("*")))


class NeverOnASchedule(unittest.TestCase):
    def test_no_schedule_file_job_or_workflow_runs_it(self):
        paths = [REPO / "jobs.yaml", REPO / "schedule.example.yaml"]
        paths += list((REPO / "workflows").glob("*"))
        paths += list((REPO / ".github" / "workflows").glob("*"))
        for p in paths:
            if p.is_file():
                self.assertNotIn("concerns", p.read_text(encoding="utf-8").lower(), str(p))

    def test_module_has_no_scheduling_or_network_code(self):
        src = (REPO / "umwayi" / "concerns.py").read_text(encoding="utf-8")
        for word in ("import sched", "threading", "socket", "urllib", "http.", "subprocess", "systemd", "crontab", "time.sleep"):
            self.assertNotIn(word, src)

    def test_the_checker_is_not_one_of_the_actions_a_schedule_can_start(self):
        src = (REPO / "umwayi" / "schedule.py").read_text(encoding="utf-8")
        self.assertNotIn("concerns", src)

    def test_no_em_dash_in_the_module(self):
        self.assertNotIn("\u2014", (REPO / "umwayi" / "concerns.py").read_text(encoding="utf-8"))
        self.assertNotIn("\u2014", (REPO / "tests" / "test_concerns.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
