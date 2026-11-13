"""W19 part 3b: umwayi/routing.py and `umwayi routing check PATH`.

The code checks that a model routing table or a task log exists and is well formed. It never claims the content is
true, and it never picks a model.
"""

import datetime
import io
import os
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from umwayi import routing
from umwayi.cli import main

REPO = Path(__file__).resolve().parent.parent
TODAY = datetime.date(2026, 11, 13)

R_HEADER = ("| platform | model | strengths | task types | source | source date | review_by |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n")
L_HEADER = ("| task | area | model chosen | outcome | review result | credits used | date |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n")


def rrow(platform="Kiro", model="Auto", strengths="Routes each task to a model.", types="general",
         source="https://kiro.dev/docs/models/", sdate="2026-11-13", review="2026-12-13"):
    return f"| {platform} | {model} | {strengths} | {types} | {source} | {sdate} | {review} |\n"


def rtext(rows=None, header=R_HEADER, extra=""):
    body = rows if rows is not None else rrow() + rrow(model="Haiku 5.5", types="high-volume, budget")
    return "# Routing\n\nWords.\n\n" + header + body + extra


def lrow(task="PR 1: a task", area="docs", model="unknown", outcome="merged", review="none recorded",
         credits="unknown", date="2026-11-12"):
    return f"| {task} | {area} | {model} | {outcome} | {review} | {credits} | {date} |\n"


def ltext(rows=None, header=L_HEADER, extra=""):
    body = rows if rows is not None else lrow() + lrow(task="PR 2: another")
    return "# Log\n\nWords.\n\n" + header + body + extra


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.root = Path(self._t.name).resolve()

    def write(self, text, name="table.md"):
        p = self.root / name
        p.write_text(text, encoding="utf-8")
        return p

    def failures(self, text, today=TODAY):
        return routing.check_text(text, today)

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--root", str(self.root), *argv])
        return code, out.getvalue(), err.getvalue()


class RoutingTable(Base):
    def one(self, **kw):
        return self.failures(rtext(rrow(**kw)))

    def test_valid_table(self):
        self.assertEqual(self.failures(rtext()), [])

    def test_valid_opencode_row(self):
        self.assertEqual(self.one(platform="OpenCode", model="Big Pickle", types="general, budget",
                                  source="https://opencode.ai/docs/console/models/"), [])
        self.assertEqual(self.one(platform="OpenCode", source="https://docs.opencode.ai/docs/models/"), [])

    def test_platform_must_be_kiro_or_opencode(self):
        for bad in ("kiro", "Claude", "", "Kiro CLI"):
            with self.subTest(bad=bad):
                f = self.one(platform=bad)
                self.assertTrue(any("platform" in x for x in f), f)

    def test_empty_model_or_strengths(self):
        for key in ("model", "strengths"):
            for bad in ("", "   "):
                with self.subTest(key=key, bad=bad):
                    f = self.one(**{key: bad})
                    self.assertEqual(len(f), 1, f)

    def test_task_types_come_from_the_fixed_list(self):
        for bad in ("", "coding", "general,", ", general", "general, general", "General"):
            with self.subTest(bad=bad):
                f = self.one(types=bad)
                self.assertTrue(any("task types" in x for x in f), f)

    def test_every_listed_task_type_is_accepted(self):
        self.assertEqual(self.one(types=", ".join(routing.TASK_TYPES)), [])

    def test_source_must_be_an_https_page_of_the_platform_vendor(self):
        bad = ("", "http://kiro.dev/docs/models/", "https://example.com/docs/models/", "https://kiro.dev.evil.com/x",
               "https://opencode.ai/docs/models/", "kiro.dev/docs/models", "https://kiro.dev/a b",
               "https://user@kiro.dev/x", "https://kiro.dev:8443/x", "ftp://kiro.dev/x", "https://kiro.dev",
               "https://kiro.dev/x#a", "https://kiro.dev/x?q=1")
        for src in bad:
            with self.subTest(src=src):
                f = self.one(source=src)
                self.assertTrue(any("source" in x for x in f), f)

    def test_opencode_source_must_be_an_opencode_page(self):
        f = self.one(platform="OpenCode", source="https://kiro.dev/docs/models/")
        self.assertTrue(any("source" in x for x in f), f)

    def test_dates_must_be_real(self):
        for bad in ("", "13-11-2026", "2026-02-30", "2026-1-1", "soon", "2026-11-13T10:00"):
            with self.subTest(bad=bad):
                self.assertTrue(any("source date" in x for x in self.one(sdate=bad)))
                self.assertTrue(any("review_by" in x for x in self.one(review=bad)))

    def test_source_date_not_in_the_future(self):
        f = self.one(sdate="2026-11-14", review="2026-12-14")
        self.assertTrue(any("future" in x for x in f), f)

    def test_review_by_must_come_after_the_source_date(self):
        for review in ("2026-11-13", "2026-11-12"):
            with self.subTest(review=review):
                self.assertTrue(any("after the source date" in x for x in self.one(review=review)))

    def test_review_by_must_be_within_the_longest_wait(self):
        edge = (TODAY + datetime.timedelta(days=routing.MAX_REVIEW_DAYS)).isoformat()
        self.assertEqual(self.one(review=edge), [])
        over = (TODAY + datetime.timedelta(days=routing.MAX_REVIEW_DAYS + 1)).isoformat()
        self.assertTrue(any("within" in x for x in self.one(review=over)))

    def test_a_row_past_its_review_by_date_fails(self):
        f = self.failures(rtext(rrow(review="2026-12-13")), today=datetime.date(2026, 12, 14))
        self.assertEqual(len(f), 1, f)
        self.assertIn("past", f[0])

    def test_review_by_today_is_not_yet_late(self):
        self.assertEqual(self.failures(rtext(rrow(review="2026-12-13")), today=datetime.date(2026, 12, 13)), [])

    def test_duplicate_model_on_one_platform(self):
        f = self.failures(rtext(rrow() + rrow()))
        self.assertEqual(len(f), 1, f)
        self.assertIn("duplicate", f[0])

    def test_same_model_name_on_two_platforms_is_fine(self):
        rows = rrow(model="Kimi K3") + rrow(platform="OpenCode", model="Kimi K3",
                                            source="https://opencode.ai/docs/console/models/")
        self.assertEqual(self.failures(rtext(rows)), [])

    def test_no_rows(self):
        self.assertTrue(self.failures(rtext(rows="")))

    def test_wrong_column_count(self):
        rows = "| Kiro | Auto | words | general | https://kiro.dev/docs/models/ | 2026-11-13 |\n" + rrow(model="B")
        self.assertTrue(any("columns" in x for x in self.failures(rtext(rows))))

    def test_a_row_longer_than_the_limit(self):
        f = self.one(strengths="x" * (routing.MAX_CELL + 1))
        self.assertEqual(len(f), 1, f)


class TaskLog(Base):
    def one(self, **kw):
        return self.failures(ltext(lrow(**kw)))

    def test_valid_log(self):
        self.assertEqual(self.failures(ltext()), [])

    def test_valid_filled_row(self):
        self.assertEqual(self.one(model="Claude Sonnet 5.5", outcome="closed not merged",
                                  review="changes requested", credits="12.5"), [])

    def test_empty_task_or_model(self):
        for key in ("task", "model"):
            for bad in ("", "  "):
                with self.subTest(key=key, bad=bad):
                    self.assertEqual(len(self.one(**{key: bad})), 1)

    def test_area_is_a_plain_lowercase_word(self):
        for bad in ("", "Docs", "my area", "a_b", "-x", "x" * 41):
            with self.subTest(bad=bad):
                self.assertTrue(any("area" in x for x in self.one(area=bad)))
        for good in ("docs", "ci", "w19-checker", "ui2"):
            with self.subTest(good=good):
                self.assertEqual(self.one(area=good), [])

    def test_outcome_from_the_fixed_list(self):
        for bad in ("", "Merged", "done", "closed", "merged."):
            with self.subTest(bad=bad):
                self.assertTrue(any("outcome" in x for x in self.one(outcome=bad)))
        for good in routing.OUTCOMES:
            self.assertEqual(self.one(outcome=good), [])

    def test_review_result_from_the_fixed_list(self):
        for bad in ("", "ok", "Approved", "approved by owner"):
            with self.subTest(bad=bad):
                self.assertTrue(any("review result" in x for x in self.one(review=bad)))
        for good in routing.REVIEWS:
            self.assertEqual(self.one(review=good), [])

    def test_credits_unknown_or_a_plain_number(self):
        for good in ("unknown", "0", "12", "12.5", "0.06", "1234567.25"):
            with self.subTest(good=good):
                self.assertEqual(self.one(credits=good), [])
        for bad in ("", "-1", "1.234", "1,5", "abc", "Unknown", "1e3", "12 credits", ".5", "5.", "12345678", "٣"):
            with self.subTest(bad=bad):
                self.assertTrue(any("credits used" in x for x in self.one(credits=bad)), bad)

    def test_dates(self):
        for bad in ("", "12-11-2026", "2026-02-30", "yesterday"):
            with self.subTest(bad=bad):
                self.assertTrue(any("date" in x for x in self.one(date=bad)))
        self.assertTrue(any("future" in x for x in self.one(date="2026-11-14")))
        self.assertEqual(self.one(date="2026-11-13"), [])

    def test_duplicate_task(self):
        f = self.failures(ltext(lrow() + lrow()))
        self.assertEqual(len(f), 1, f)
        self.assertIn("duplicate", f[0])

    def test_no_rows(self):
        self.assertTrue(self.failures(ltext(rows="")))

    def test_wrong_column_count(self):
        f = self.failures(ltext("| a | b | c |\n"))
        self.assertTrue(any("columns" in x for x in f))


class WhichKind(Base):
    def test_header_decides_the_kind(self):
        self.assertEqual(routing.kind_of(rtext()), "routing table")
        self.assertEqual(routing.kind_of(ltext()), "task log")
        self.assertIsNone(routing.kind_of("no table here"))

    def test_unknown_or_changed_header_fails(self):
        for header in ("| platform | model |\n| --- | --- |\n", "", R_HEADER.replace("model", "name", 1),
                       L_HEADER.replace("credits used", "credits"), R_HEADER.replace("| --- ", "| xx ", 1)):
            with self.subTest(header=header):
                self.assertTrue(self.failures(rtext(header=header)))

    def test_header_without_separator_fails(self):
        self.assertTrue(self.failures(rtext(header=R_HEADER.split("\n")[0] + "\n")))

    def test_reordered_columns_fail(self):
        self.assertTrue(self.failures(ltext(header=L_HEADER.replace("task | area", "area | task"))))

    def test_a_second_table_is_refused(self):
        self.assertTrue(self.failures(rtext(extra="\ntext\n\n" + L_HEADER + lrow())))

    def test_empty_text(self):
        self.assertTrue(self.failures(""))

    def test_text_around_the_table_is_ignored(self):
        self.assertEqual(self.failures("# t\n\n- list\n\n" + R_HEADER + rrow() + "\nAfter.\n"), [])

    def test_failure_lines_never_echo_file_content(self):
        secret = "sk-live-TOPSECRET"
        text = rtext(rrow(platform=secret, model=secret, strengths=secret, types=secret, source=secret, sdate=secret,
                          review=secret) + f"| {secret} |\n")
        text += "\n" + ltext(lrow(task=secret, area=secret, outcome=secret, review=secret, credits=secret, date=secret))
        self.assertNotIn(secret, "\n".join(self.failures(text)))
        text = ltext(lrow(task=secret, area=secret, outcome=secret, review=secret, credits=secret, date=secret)
                     + f"| {secret} |\n")
        self.assertNotIn(secret, "\n".join(self.failures(text)))

    def test_one_line_per_failure_and_no_em_dash(self):
        for line in self.failures(rtext(rrow(platform="x", sdate="y") + rrow(platform="z"))):
            self.assertNotIn("\n", line)
            self.assertNotIn("\u2014", line)


class Command(Base):
    def test_exit_0_on_a_valid_table_and_a_valid_log(self):
        for text in (rtext(), ltext()):
            with self.subTest(text=text[:12]):
                code, out, err = self.cli("routing", "check", str(self.write(text)), "--date", "2026-11-13")
                self.assertEqual((code, err), (0, ""))
                self.assertIn("Yes", out)

    def test_exit_2_with_one_line_per_failure(self):
        p = self.write(rtext(rrow(platform="x") + rrow(model="B", sdate="nope")))
        code, out, err = self.cli("routing", "check", str(p), "--date", "2026-11-13")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertEqual(len([ln for ln in err.splitlines() if ln]), 2)

    def test_the_system_clock_is_the_default_date(self):
        p = self.write(rtext(rrow(review="2026-12-13")))
        with mock.patch("umwayi.cli._today", return_value="2027-01-01"):
            self.assertEqual(self.cli("routing", "check", str(p))[0], 2)
        with mock.patch("umwayi.cli._today", return_value="2026-11-13"):
            self.assertEqual(self.cli("routing", "check", str(p))[0], 0)

    def test_missing_file_folder_non_utf8_and_too_big_are_2(self):
        (self.root / "dir").mkdir()
        bad = self.root / "bad.md"
        bad.write_bytes(b"\xff\xfe\x00bad")
        big = self.write("x" * (routing.MAX_BYTES + 1), "big.md")
        for p in (self.root / "nope.md", self.root / "dir", bad, big):
            with self.subTest(p=p.name):
                code, _, err = self.cli("routing", "check", str(p), "--date", "2026-11-13")
                self.assertEqual(code, 2)
                self.assertTrue(err.strip())

    def test_usage_errors_are_64(self):
        for argv in (["routing"], ["routing", "check"], ["routing", "check", "a", "b"], ["routing", "pick", "a"],
                     ["routing", "check", "a", "--date", "yesterday"], ["routing", "check", "a", "--date"],
                     ["routing", "check", "a", "--model", "x"]):
            with self.subTest(argv=argv):
                self.assertEqual(self.cli(*argv)[0], 64)

    def test_a_crash_is_2_and_prints_no_text(self):
        p = self.write(rtext())
        with mock.patch("umwayi.cli.routing.check_file", side_effect=RuntimeError("sk-live-TOPSECRET")):
            code, out, err = self.cli("routing", "check", str(p))
        self.assertEqual(code, 2)
        self.assertNotIn("TOPSECRET", out + err)

    def test_never_1_or_3(self):
        p = self.write(rtext())
        for exc in (RuntimeError("x"), OSError("x"), KeyboardInterrupt(), MemoryError()):
            with self.subTest(exc=type(exc).__name__), mock.patch("umwayi.cli.routing.check_file", side_effect=exc):
                self.assertEqual(self.cli("routing", "check", str(p))[0], 2)

    def test_changes_nothing(self):
        p = self.write(rtext())
        before = sorted(str(x) for x in self.root.rglob("*"))
        self.cli("routing", "check", str(p))
        self.assertEqual(before, sorted(str(x) for x in self.root.rglob("*")))
        self.assertFalse((self.root / "LOGBOOK.md").exists())

    def test_relative_path_is_read_from_the_current_folder(self):
        self.write(rtext())
        old = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, old)
        self.assertEqual(self.cli("routing", "check", "table.md", "--date", "2026-11-13")[0], 0)


class TheRealFiles(unittest.TestCase):
    """The two files this task ships pass the checker, and say what the task promised."""

    def read(self, rel):
        return (REPO / rel).read_text(encoding="utf-8")

    def test_the_routing_table_passes(self):
        self.assertEqual(routing.check_file(REPO / "docs" / "model-routing.md", TODAY), [])
        self.assertEqual(routing.kind_of(self.read("docs/model-routing.md")), "routing table")

    def test_the_task_log_passes(self):
        self.assertEqual(routing.check_file(REPO / "docs" / "task-log.md", TODAY), [])
        self.assertEqual(routing.kind_of(self.read("docs/task-log.md")), "task log")

    def test_the_table_has_kiro_and_opencode_rows_with_vendor_sources(self):
        rows = routing.table_rows(self.read("docs/model-routing.md"))
        platforms = {r[0] for r in rows}
        self.assertEqual(platforms, {"Kiro", "OpenCode"})
        for r in rows:
            self.assertTrue(r[4].startswith(("https://kiro.dev/", "https://opencode.ai/", "https://docs.opencode.ai/")))

    def test_every_kiro_row_has_the_same_source_date_as_its_page_read(self):
        rows = [r for r in routing.table_rows(self.read("docs/model-routing.md")) if r[0] == "Kiro"]
        self.assertGreaterEqual(len(rows), 20)
        self.assertTrue(any(r[1] == "Auto" for r in rows))

    def test_the_doc_says_the_owner_chooses(self):
        text = self.read("docs/model-routing.md").lower()
        self.assertIn("the owner always chooses the model", text)
        self.assertIn("only proposes", text)

    def test_the_log_has_pull_requests_66_to_79_once_each(self):
        rows = routing.table_rows(self.read("docs/task-log.md"))
        numbers = [int(m.group(1)) for r in rows if (m := re.match(r"PR (\d+): ", r[0]))]
        self.assertEqual(sorted(numbers), list(range(66, 80)))

    def test_the_log_invents_nothing_that_history_does_not_hold(self):
        for r in routing.table_rows(self.read("docs/task-log.md")):
            self.assertEqual(r[2], "unknown", r[0])
            self.assertEqual(r[5], "unknown", r[0])

    def test_no_em_dash_in_the_new_files(self):
        for rel in ("umwayi/routing.py", "tests/test_routing.py", "docs/model-routing.md", "docs/task-log.md",
                    "docs-parts/status-log/W19-3b.md", "docs-parts/known-limits/W19-3b.md"):
            self.assertNotIn("\u2014", self.read(rel), rel)


class NeverOnASchedule(unittest.TestCase):
    def test_no_schedule_file_job_or_workflow_runs_it(self):
        paths = [REPO / "jobs.yaml", REPO / "schedule.example.yaml"]
        paths += list((REPO / "workflows").glob("*"))
        paths += list((REPO / ".github" / "workflows").glob("*"))
        for p in paths:
            if p.is_file():
                self.assertNotIn("routing", p.read_text(encoding="utf-8").lower(), str(p))

    def test_module_has_no_scheduling_network_or_model_picking_code(self):
        src = (REPO / "umwayi" / "routing.py").read_text(encoding="utf-8")
        for word in ("import sched", "threading", "socket", "urllib", "http.", "subprocess", "systemd", "crontab",
                     "time.sleep", "random", "def choose", "def pick", "def recommend"):
            self.assertNotIn(word, src)

    def test_the_checker_is_not_one_of_the_actions_a_schedule_can_start(self):
        self.assertNotIn("routing", (REPO / "umwayi" / "schedule.py").read_text(encoding="utf-8"))

    def test_the_guidance_agents_steering_and_rules_files_are_not_touched(self):
        for rel in ("umwayi/guidance.py", "guidance.yaml", "umwayi/agents.py", "agents.example.yaml", "rules.yaml"):
            p = REPO / rel
            if p.exists():
                self.assertNotIn("routing", p.read_text(encoding="utf-8").lower(), rel)
        for p in (REPO / ".kiro" / "steering").glob("*.md"):
            self.assertNotIn("umwayi routing", p.read_text(encoding="utf-8"), str(p))


if __name__ == "__main__":
    unittest.main()
