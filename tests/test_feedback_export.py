"""W33: `umwayi feedback export`, the logbook summary for a feedback issue.

A real logbook is built in a temporary root with the real commands (check, queue add, rules change) and with entries
written through the logbook's own writer. Every entry carries sentinel words: a secret, a path, a command, a rule id, a
rule text, a title. None of them may ever appear in the output. The command must write nothing, append no entry, and give
exit 2 with no summary for a logbook that was edited by hand. Standard library only.
"""
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from umwayi import budget, feedback, logbook, units
from umwayi.cli import main

REPO = Path(__file__).resolve().parents[1]
SECRET = "sk-live-FEEDBACKSECRET"
SENTINELS = ("FEEDBACKSECRET", "PATHSENTINEL", "COMMANDSENTINEL", "ruleidsentinel", "RULETEXTSENTINEL", "RULETITLESENTINEL",
             "QTITLESENTINEL", "SOURCESENTINEL", "ENTRYTEXTSENTINEL", "/home/", "rm -rf")
RULES = f"""rules:
  - id: ruleidsentinel-yes
    title: RULETITLESENTINEL yes
    text: RULETEXTSENTINEL yes {SECRET}
    verdict: yes
    matchers:
      type: read_memory
  - id: ruleidsentinel-no
    title: RULETITLESENTINEL no
    text: RULETEXTSENTINEL no
    verdict: no
    matchers:
      type: payment
"""
DAY = "2026-11-12"
LATER = "2026-11-13"


def run_main(root, *argv, today=LATER):
    out, err = io.StringIO(), io.StringIO()
    old = sys.stderr
    sys.stderr = err
    try:
        with mock.patch("umwayi.cli._today", return_value=today):
            code = main(["--root", str(root), *argv], out=out)
    finally:
        sys.stderr = old
    return code, out.getvalue(), err.getvalue()


def tree(root):
    """Every file and folder under the root with its hash, so any write at all shows."""
    out = {}
    for p in sorted(Path(root).rglob("*")):
        rel = p.relative_to(root).as_posix()
        out[rel] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "dir"
    return out


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="umwayi-fbx-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "umwayi.json").write_text(json.dumps({"memory_dir": "memory", "private_paths": []}))
        (self.root / "rules.yaml").write_text(RULES)

    def check(self, action, today=LATER):
        return run_main(self.root, "check", json.dumps(action), today=today)

    def build(self):
        """A logbook with checks of every verdict, a queue entry, a budget reservation and entries that hold sentinels."""
        self.assertEqual(self.check({"type": "read_memory", "path": "/home/PATHSENTINEL/x", "command": "rm -rf COMMANDSENTINEL"}, DAY)[0], 0)
        self.assertEqual(self.check({"type": "read_memory"}, DAY)[0], 0)
        self.assertEqual(self.check({"type": "payment"}, DAY)[0], 2)
        self.assertEqual(self.check({"type": "something_new"}, DAY)[0], 3)
        self.assertEqual(run_main(self.root, "queue", "add", "--kind", "task", "QTITLESENTINEL " + SECRET, today=DAY)[0], 0)
        logbook.append(self.root, logbook.Entry(DAY, "umwayi SOURCESENTINEL", f"ENTRYTEXTSENTINEL {SECRET} /home/PATHSENTINEL",
                                                "rm -rf COMMANDSENTINEL", "ENTRYTEXTSENTINEL"))
        logbook.append(self.root, budget.entry(DAY, budget.reserve_text("aaaaaaaaaaaaaaaa", "claude-main", "claude", 5 * units.MICROS_PER_UU),
                                               "units.yaml was read", "Only names and numbers are logged."))
        logbook.append(self.root, budget.entry(LATER, budget.reserve_text("bbbbbbbbbbbbbbbb", "claude-main", "claude", 2 * units.MICROS_PER_UU),
                                               "units.yaml was read", "Only names and numbers are logged."))

    def export(self):
        return run_main(self.root, "feedback", "export")


class SummaryTests(Base):
    def setUp(self):
        super().setUp()
        self.build()
        self.code, self.out, self.err = self.export()

    def test_it_exits_0_and_prints_the_summary_to_stdout_only(self):
        self.assertEqual((self.code, self.err), (0, ""))
        self.assertTrue(self.out.startswith("umwayi feedback export: counts and dates only"))

    def test_the_count_of_entries_is_the_logbook_s_count(self):
        n = len(logbook.read_checked(self.root))
        self.assertIn(f"entries: {n}\n", self.out)

    def test_the_counts_per_kind_are_right_and_an_unknown_source_is_other(self):
        self.assertIn("  umwayi check: 4\n", self.out)
        self.assertIn("  umwayi queue add: 1\n", self.out)
        self.assertIn("  umwayi budget: 2\n", self.out)
        self.assertIn("  other: 1\n", self.out)
        self.assertNotIn("SOURCESENTINEL", self.out)
        kinds = re.findall(r"^  (umwayi [a-z -]+|other): (\d+)$", self.out.split("checks by verdict")[0], re.M)
        self.assertEqual(sum(int(n) for _, n in kinds), len(logbook.read_checked(self.root)))

    def test_the_counts_per_verdict_are_right(self):
        verdicts = self.out.split("checks by verdict (umwayi check):\n")[1].split("dates:")[0]
        self.assertEqual(verdicts, "  Yes: 2\n  No: 1\n  Ask me first: 1\n  unreadable: 0\n")

    def test_the_date_range_is_the_first_and_last_entry_date(self):
        dates = sorted(e.date for e in logbook.read_checked(self.root))
        self.assertIn(f"dates: first {dates[0]}, last {dates[-1]}\n", self.out)
        self.assertEqual(dates[-1], "2026-11-13")

    def test_the_budget_is_the_sum_of_all_days_in_uu_with_an_open_reservation_counted_in_full(self):
        self.assertIn("budget spent: 7 UU", self.out)

    def test_the_chain_is_not_started_until_the_owner_starts_it_and_then_it_is_counted(self):
        self.assertIn("chain: not started\n", self.out)
        self.assertEqual(run_main(self.root, "logbook", "seal", "--by", "test", "--chain")[0], 0)
        self.assertEqual(self.check({"type": "read_memory"})[0], 0)
        code, out, _ = self.export()
        self.assertEqual(code, 0)
        self.assertRegex(out, r"chain: intact, [1-9]\d* entries in the chain\n")

    def test_nothing_that_is_not_a_fixed_word_a_number_or_a_date_is_printed(self):
        allowed = re.compile(r"^(umwayi feedback export: counts and dates only; no paths, commands, rules or file contents\.|"
                             r"entries: \d+|entries by kind:|  (umwayi [a-z-]+(?: [a-z-]+)*|other): \d+|  none|"
                             r"checks by verdict \(umwayi check\):|  (Yes|No|Ask me first|unreadable): \d+|"
                             r"dates: (first \d{4}-\d{2}-\d{2}, last \d{4}-\d{2}-\d{2}|none)|"
                             r"chain: (not started|intact, \d+ entries in the chain)|"
                             r"budget spent: \d+ UU \(an open reservation counts in full\))$")
        for line in self.out.rstrip("\n").split("\n"):
            self.assertRegex(line, allowed)
        for name in re.findall(r"^  (umwayi [a-z -]+):", self.out, re.M):
            self.assertIn(name, feedback.KINDS)


class NothingLeaksTests(Base):
    def test_a_secret_word_planted_in_an_entry_never_appears_in_the_output(self):
        self.build()
        code, out, err = self.export()
        self.assertEqual(code, 0)
        text = (out + err).lower()
        for word in SENTINELS:
            self.assertNotIn(word.lower(), text, word)
        self.assertNotIn(str(self.root).lower(), text)
        self.assertNotIn(SECRET, out + err)
        # the sentinels are really in the logbook, so the test could fail
        book = (self.root / "LOGBOOK.md").read_text(encoding="utf-8")
        for word in ("FEEDBACKSECRET", "PATHSENTINEL", "COMMANDSENTINEL", "ruleidsentinel", "ENTRYTEXTSENTINEL", "SOURCESENTINEL"):
            self.assertIn(word, book, word)

    def test_a_secret_in_a_source_that_looks_like_a_known_kind_is_counted_as_other(self):
        logbook.append(self.root, logbook.Entry(LATER, "umwayi check " + SECRET, "x", "y", "z"))
        logbook.append(self.root, logbook.Entry(LATER, "umwayi check", f"Rule {SECRET} gave Maybe; action type: x", "y", "z"))
        code, out, _ = self.export()
        self.assertEqual(code, 0)
        self.assertNotIn("FEEDBACKSECRET", out)
        self.assertIn("  other: 1\n", out)
        self.assertIn("  unreadable: 1\n", out)

    def test_every_named_kind_is_a_fixed_word_without_a_path_or_a_secret(self):
        for kind in feedback.KINDS:
            self.assertRegex(kind, r"^umwayi [a-z][a-z-]*(?: [a-z][a-z-]*)*$")


class ReadOnlyTests(Base):
    def test_it_writes_no_file_and_appends_no_entry(self):
        self.build()
        before = tree(self.root)
        entries = len(logbook.read_checked(self.root))
        for _ in range(2):
            self.assertEqual(self.export()[0], 0)
        self.assertEqual(tree(self.root), before)
        self.assertEqual(len(logbook.read_checked(self.root)), entries)

    def test_it_creates_nothing_in_a_root_that_has_no_logbook(self):
        before = tree(self.root)
        code, out, err = self.export()
        self.assertEqual((code, out), (2, ""))
        self.assertIn("no logbook", err)
        self.assertEqual(tree(self.root), before)

    def test_the_module_has_no_write_call_and_no_logbook_append(self):
        text = (REPO / "umwayi" / "feedback.py").read_text(encoding="utf-8")
        code = "\n".join(ln for ln in text.split("\n") if not ln.lstrip().startswith("#"))
        for word in ("write_text", "write_bytes", "open(", "logbook.append", "append_with", "atomic_write", "os.remove", "unlink",
                     "subprocess", "socket", "urllib", "http"):
            self.assertNotIn(word, code, word)
        self.assertNotIn("\u2014", text)

    def test_it_uses_only_the_standard_library_and_this_package(self):
        text = (REPO / "umwayi" / "feedback.py").read_text(encoding="utf-8")
        for mod in re.findall(r"^(?:from|import) ([\w.]+)", text, re.M):
            self.assertIn(mod.split(".")[0], {"__future__", "re", "dataclasses", "pathlib", "umwayi"}, mod)


class FailClosedTests(Base):
    def assertRefused(self):
        before = tree(self.root)
        code, out, err = self.export()
        self.assertEqual((code, out), (2, ""))
        self.assertIn("no summary was made", err)
        self.assertNotIn("entries:", err)
        for word in SENTINELS:
            self.assertNotIn(word.lower(), err.lower())
        self.assertEqual(tree(self.root), before)

    def test_a_hand_edited_logbook_gives_exit_2_and_no_summary(self):
        self.build()
        path = self.root / "LOGBOOK.md"
        path.write_text(path.read_text(encoding="utf-8").replace("gave Yes", "gave No", 1), encoding="utf-8")
        self.assertRefused()

    def test_an_edit_that_removes_an_entry_gives_exit_2(self):
        self.build()
        path = self.root / "LOGBOOK.md"
        text = path.read_text(encoding="utf-8")
        path.write_text(text[: text.rindex("\n## ")] + "\n", encoding="utf-8")
        self.assertRefused()

    def test_a_broken_chain_gives_exit_2(self):
        self.build()
        self.assertEqual(run_main(self.root, "logbook", "seal", "--by", "test", "--chain")[0], 0)
        self.assertEqual(self.check({"type": "read_memory"})[0], 0)
        path = self.root / "LOGBOOK.md"
        path.write_text(re.sub(r"(- Chain: )([0-9a-f])", lambda m: m.group(1) + ("0" if m.group(2) != "0" else "1"),
                               path.read_text(encoding="utf-8"), count=1), encoding="utf-8")
        self.assertRefused()

    def test_a_logbook_that_is_not_text_and_one_with_a_format_problem_give_exit_2(self):
        self.build()
        path = self.root / "LOGBOOK.md"
        good = path.read_bytes()
        for bad in (good + b"\xff\xfe\x00", good + b"\n## not-a-date\n- Source: x\n"):
            path.write_bytes(bad)
            self.assertRefused()
        path.write_bytes(good)
        self.assertEqual(self.export()[0], 0)

    def test_a_malformed_budget_entry_gives_exit_2_and_no_summary(self):
        self.build()
        logbook.append(self.root, logbook.Entry(LATER, "umwayi budget", f"Reserved run r9 for agent a ({SECRET}): x micros", "y", "z"))
        before = tree(self.root)
        code, out, err = self.export()
        self.assertEqual((code, out), (2, ""))
        self.assertNotIn("FEEDBACKSECRET", err)
        self.assertEqual(tree(self.root), before)

    def test_an_unexpected_error_is_exit_2_with_only_the_type_name(self):
        self.build()
        with mock.patch("umwayi.cli.feedback.export", side_effect=RuntimeError(SECRET)):
            code, out, err = self.export()
        self.assertEqual((code, out), (2, ""))
        self.assertNotIn(SECRET, err)
        self.assertIn("RuntimeError", err)


class UsageAndProcessTests(Base):
    def test_extra_arguments_and_a_missing_subcommand_are_exit_64(self):
        self.build()
        for argv in (("feedback",), ("feedback", "export", "--out", "x"), ("feedback", "export", "extra"), ("feedback", "send")):
            self.assertEqual(run_main(self.root, *argv)[0], 64, argv)

    def test_the_exit_code_is_never_1_or_3_in_any_case_above(self):
        codes = set()
        codes.add(self.export()[0])  # no logbook
        self.build()
        codes.add(self.export()[0])
        path = self.root / "LOGBOOK.md"
        path.write_text(path.read_text(encoding="utf-8") + "junk\n", encoding="utf-8")
        codes.add(self.export()[0])
        codes.add(run_main(self.root, "feedback")[0])
        self.assertTrue(codes <= {0, 2, 64}, codes)
        self.assertEqual(codes, {0, 2, 64})

    def test_a_real_process_prints_the_summary_and_exits_0(self):
        self.build()
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "feedback", "export"], cwd=self.root,
                           capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(REPO)})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("entries by kind:", r.stdout)
        for word in SENTINELS:
            self.assertNotIn(word.lower(), (r.stdout + r.stderr).lower())

    def test_the_summary_is_the_same_twice(self):
        self.build()
        self.assertEqual(self.export(), self.export())


if __name__ == "__main__":
    unittest.main()
