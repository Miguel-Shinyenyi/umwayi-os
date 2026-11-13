import ast
import re
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import after_rules, entry_text, log_rules, without_run_lock, write_sealed_logbook
from umwayi import jobs, logbook, publish, report
from umwayi.cli import main
from umwayi.errors import UmwayiError, UsageError
from umwayi.logbook import parse

REPO = Path(__file__).resolve().parent.parent
PKG = REPO / "umwayi"

RULES = """
rules:
  - id: run-safe-jobs
    title: Jobs
    text: Read and draft jobs are fine.
    verdict: yes
    matchers:
      type: run_job
      command: [report, check, queue-list]
  - id: publish-ask
    title: Publishing
    text: Publishing is Ask me first.
    verdict: ask
    matchers:
      type: publish_draft
  - id: no-money
    title: Money
    text: Never move money.
    verdict: no
    matchers:
      type: payment
  - id: read-ok
    title: Reads
    text: Reads are fine.
    verdict: yes
    matchers:
      type: read
"""

JOBS = """
jobs:
  - name: weekly-report
    command: report
    since_days: 7
    min_gap_days: 7
  - name: open-queue
    command: queue-list
    status: open
    min_gap_days: 1
  - name: money-check
    command: check
    action_type: payment
    min_gap_days: 1
  - name: read-check
    command: check
    action_type: read
    min_gap_days: 1
"""

QUEUE = (
    "# Queue\n\n| id | kind | title | status | recommendation | answer | answered |\n"
    "| --- | --- | --- | --- | --- | --- | --- |\n"
    "| Q-0001 | task | Open one | open | | | |\n"
    "| Q-0002 | task | Done one | closed | | | |\n"
)
SECRET_EMAIL = "secret.person@example.org"


def git(root, *args, date="2026-11-05T12:00:00+0000"):
    env = dict(os.environ, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date,
               GIT_AUTHOR_NAME="Secret Person", GIT_AUTHOR_EMAIL=SECRET_EMAIL,
               GIT_COMMITTER_NAME="Secret Person", GIT_COMMITTER_EMAIL=SECRET_EMAIL,
               GIT_CONFIG_NOSYSTEM="1", HOME=str(root))
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=env)


def commit(root, subject, date):
    git(root, "commit", "-q", "--allow-empty", "-m", subject, date=date)


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "rules.yaml").write_text(RULES, encoding="utf-8")
        (self.root / "jobs.yaml").write_text(JOBS, encoding="utf-8")
        (self.root / "queue.md").write_text(QUEUE, encoding="utf-8")
        (self.root / "umwayi.json").write_text(json.dumps({"memory_dir": "memory", "private_paths": ["drafts/private-*"]}))
        self.log = self.root / "LOGBOOK.md"
        for patcher in (mock.patch.object(logbook, "LOCK_WAIT_SECONDS", 0), mock.patch.dict(os.environ, {"TZ": "UTC"})):
            patcher.start()
            self.addCleanup(patcher.stop)
        if hasattr(__import__("time"), "tzset"):
            __import__("time").tzset()
            self.addCleanup(__import__("time").tzset)

    def make_git(self, commits=(("First change", "2026-11-03T12:00:00+0000"),)):
        git(self.root, "init", "-q")
        for subject, date in commits:
            commit(self.root, subject, date)

    def cli(self, *argv, clock="2026-11-07"):
        out, err = io.StringIO(), io.StringIO()
        old = sys.stderr
        sys.stderr = err
        try:
            with mock.patch("umwayi.cli._today", return_value=clock):
                code = main(["--root", str(self.root), *argv], out=out)
        finally:
            sys.stderr = old
        return code, out.getvalue(), err.getvalue()

    def run_job(self, name, clock="2026-11-07", jobfile=None):
        return self.cli("run", str(jobfile or self.root / "jobs.yaml"), "--job", name, clock=clock)

    def entries(self):
        if not self.log.exists():
            return []
        return [p.entry for p in parse(self.log.read_text(encoding="utf-8"))[0]]

    def snap(self):
        out = {}
        for dp, dn, fn in os.walk(self.root):
            if ".git" in Path(dp).relative_to(self.root).parts:
                continue
            for d in dn:
                if d != ".git":
                    out[os.path.relpath(os.path.join(dp, d), self.root) + "/"] = None
            for f in fn:
                out[os.path.relpath(os.path.join(dp, f), self.root)] = Path(dp, f).read_bytes()
        return without_run_lock(out)

    def assert_refused(self, argv, code, fragment, clock="2026-11-07"):
        before = self.snap()
        c, out, err = self.cli(*argv, clock=clock)
        self.assertEqual(c, code, out + err)
        self.assertIn(fragment, out + err)
        self.assertEqual(self.snap(), before, "a refused command changed something")
        return out + err


# =============================================================== jobs file


class JobsFileTests(unittest.TestCase):
    def test_parses_all_three_commands(self):
        js = jobs.parse_jobs(JOBS)
        self.assertEqual([(j.name, j.command, j.min_gap_days) for j in js], [
            ("weekly-report", "report", 7), ("open-queue", "queue-list", 1),
            ("money-check", "check", 1), ("read-check", "check", 1)])
        self.assertEqual(js[0].options, {"since_days": 7})
        self.assertEqual(js[1].options, {"status": "open"})
        self.assertEqual(js[2].options, {"action_type": "payment"})

    def test_queue_list_status_is_optional(self):
        js = jobs.parse_jobs("jobs:\n  - name: q\n    command: queue-list\n    min_gap_days: 1\n")
        self.assertEqual(js[0].options, {})

    def job(self, **fields):
        base = {"name": "j", "command": "report", "since_days": 7, "min_gap_days": 1}
        base.update(fields)
        lines = ["jobs:", "  - " + "\n    ".join(f"{k}: {v}" for k, v in base.items() if v is not None)]
        return "\n".join(lines) + "\n"

    def test_refusals(self):
        bad = {
            "not yaml": "jobs: [\n",
            "empty": "",
            "wrong top": "tasks: []\n",
            "extra top key": "jobs:\n  - name: j\n    command: queue-list\n    min_gap_days: 1\nother: 1\n",
            "empty list": "jobs: []\n",
            "not a list": "jobs: 5\n",
            "item not mapping": "jobs:\n  - just text\n",
            "missing name": self.job(name=None),
            "bad name": self.job(name="Bad_Name"),
            "long name": self.job(name="a" * 41),
            "duplicate name": self.job() + "  - name: j\n    command: queue-list\n    min_gap_days: 1\n",
            "command not allowed": self.job(command="shell"),
            "command is a shell string": self.job(command='"rm -rf /"'),
            "command git push": self.job(command='"git push"'),
            "command publish": self.job(command="publish-draft"),
            "missing command": self.job(command=None),
            "missing gap": self.job(min_gap_days=None),
            "zero gap": self.job(min_gap_days=0),
            "negative gap": self.job(min_gap_days=-1),
            "huge gap": self.job(min_gap_days=367),
            "gap is text": self.job(min_gap_days="weekly"),
            "gap is bool": self.job(min_gap_days="true"),
            "gap is float": self.job(min_gap_days=1.5),
            "missing since_days": self.job(since_days=None),
            "since_days zero": self.job(since_days=0),
            "since_days too big": self.job(since_days=367),
            "unknown field": self.job(shell='"echo hi"'),
            "args field": self.job(args="[a, b]"),
            "option of another command": self.job(status="open"),
            "check without action_type": "jobs:\n  - name: c\n    command: check\n    min_gap_days: 1\n",
            "check bad action_type": "jobs:\n  - name: c\n    command: check\n    action_type: \"a b\"\n    min_gap_days: 1\n",
            "check action_type list": "jobs:\n  - name: c\n    command: check\n    action_type: [a]\n    min_gap_days: 1\n",
            "queue bad status": "jobs:\n  - name: q\n    command: queue-list\n    status: done\n    min_gap_days: 1\n",
        }
        for name, text in bad.items():
            with self.subTest(name=name):
                with self.assertRaises(UmwayiError):
                    jobs.parse_jobs(text)

    def test_select(self):
        js = jobs.parse_jobs(JOBS)
        self.assertEqual(jobs.select(js, "open-queue").command, "queue-list")
        with self.assertRaises(UsageError):
            jobs.select(js, None)
        with self.assertRaises(UsageError):
            jobs.select(js, "nope")
        one = jobs.parse_jobs("jobs:\n  - name: q\n    command: queue-list\n    min_gap_days: 1\n")
        self.assertEqual(jobs.select(one, None).name, "q")


# ===================================================================== run


class RunTests(Base):
    def test_queue_list_job_runs_and_logs_one_entry(self):
        code, out, err = self.run_job("open-queue")
        self.assertEqual(code, 0, err)
        self.assertIn("Job open-queue ran.", out)
        self.assertIn("Q-0001", out)
        self.assertNotIn("Q-0002", out)
        e = after_rules(self.entries())  # L13.3 (13.R7.2): the rules are logged before their first use
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0].source, "umwayi run")
        self.assertEqual(e[0].added, "Job open-queue ran (command queue-list): listed 1 rows with status open")
        self.assertIn("rule run-safe-jobs gave Yes for action type run_job", e[0].checked)
        self.assertEqual(self.cli("logbook", "verify")[0], 0)

    def test_report_job_writes_a_draft_and_logs_one_entry(self):
        self.make_git()
        code, out, err = self.run_job("weekly-report")
        self.assertEqual(code, 0, err)
        self.assertIn("Wrote drafts/report-0001.md (1 commits from 2026-10-31 to 2026-11-07)", out)
        self.assertTrue((self.root / "drafts" / "report-0001.md").exists())
        e = after_rules(self.entries())  # L13.3 (13.R7.2): the rules are logged before their first use
        self.assertEqual(len(e), 1)
        self.assertTrue(e[0].added.startswith("Job weekly-report ran (command report): wrote drafts/report-0001.md"))

    def test_check_job_returns_the_inner_answer(self):
        for name, code, answer in [("money-check", 2, "No"), ("read-check", 0, "Yes")]:
            with self.subTest(name=name):
                c, out, _ = self.run_job(name)
                self.assertEqual(c, code)
                self.assertIn(f"Job {name} ran.\n{answer}\n", out)
                self.assertIn(f"gave {answer} for action type", self.entries()[-1].added)

    def test_one_entry_per_run_and_earlier_bytes_kept(self):
        seen = b""
        for n, clock in enumerate(["2026-11-01", "2026-11-02", "2026-11-03"], 1):
            self.assertEqual(self.run_job("open-queue", clock=clock)[0], 0)
            now = self.log.read_bytes()
            self.assertTrue(now.startswith(seen))
            self.assertEqual(len(self.entries()), n + 1)  # L13.3 (13.R7.2): the rules are logged before their first use
            seen = now

    def test_only_one_job_in_the_file_needs_no_name(self):
        f = self.root / "one.yaml"
        f.write_text("jobs:\n  - name: q\n    command: queue-list\n    min_gap_days: 1\n", encoding="utf-8")
        code, out, _ = self.cli("run", str(f))
        self.assertEqual(code, 0)

    # -- the gap rule

    def test_gap_rule(self):
        self.make_git()
        self.assertEqual(self.run_job("weekly-report", clock="2026-11-01")[0], 0)
        for clock, days in (("2026-11-01", 0), ("2026-11-04", 3), ("2026-11-07", 6)):
            with self.subTest(clock=clock):
                before = {k: v for k, v in self.snap().items() if not k.endswith(("LOGBOOK.md", "logbook.sha256"))}
                n = len(self.entries())
                code, out, err = self.cli("run", str(self.root / "jobs.yaml"), "--job", "weekly-report", clock=clock)
                self.assertEqual(code, 1, out + err)  # layer 6 keeps exit 1 for a refusal (L11-Q9)
                self.assertIn("the minimum gap is 7 day(s)", out + err)
                self.assertIn("The job did not run", out + err)
                after = {k: v for k, v in self.snap().items() if not k.endswith(("LOGBOOK.md", "logbook.sha256"))}
                self.assertEqual(after, before, "a refused job changed something other than the logbook")
                # S.1 found that a refusal by the gap rule left no entry, so a scheduled run refused by it left no trace
                # in the logbook (KNOWN-LIMITS 98 says the logbook says which). Now it writes one, like every other
                # refusal of a run.
                [e] = self.entries()[n:]
                self.assertEqual((e.date, e.source), (clock, "umwayi run"))
                self.assertEqual(e.added, f"Job weekly-report did not run: the gap rule (it ran {days} day(s) ago on "
                                          "2026-11-01; the minimum gap is 7 day(s))")
        self.assertEqual(self.run_job("weekly-report", clock="2026-11-08")[0], 0)  # exactly 7 days later: refusals
        self.assertEqual(sorted(os.listdir(self.root / "drafts")), ["report-0001.md", "report-0002.md"])  # not runs

    def test_a_gap_refusal_that_cannot_be_logged_still_refuses(self):
        self.assertEqual(self.run_job("open-queue")[0], 0)
        with open(self.log, "a", encoding="utf-8") as f:
            f.write("edited by hand\n")
        code, out, err = self.run_job("open-queue")
        self.assertEqual(code, 1, out + err)
        self.assertIn("The job did not run", out + err)

    def test_gap_counts_from_the_latest_run(self):
        self.make_git()
        self.assertEqual(self.run_job("weekly-report", clock="2026-11-01")[0], 0)
        self.assertEqual(self.run_job("weekly-report", clock="2026-11-08")[0], 0)
        _, _, err = self.run_job("weekly-report", clock="2026-11-10")
        self.assertIn("ran 2 day(s) ago on 2026-11-08", err)

    def test_gap_is_per_job(self):
        self.assertEqual(self.run_job("open-queue")[0], 0)
        self.assertEqual(self.run_job("read-check")[0], 0)
        self.assertEqual(self.run_job("open-queue")[0], 1)

    def test_stopped_runs_do_not_count_as_runs(self):
        (self.root / "rules.yaml").write_text("rules: []\n", encoding="utf-8")
        self.assertEqual(self.run_job("open-queue")[0], 3)
        (self.root / "rules.yaml").write_text(RULES, encoding="utf-8")
        self.assertEqual(self.run_job("open-queue")[0], 0)

    def test_gap_reads_the_logbook_not_other_text(self):
        write_sealed_logbook(self.root, "# Logbook\n" + entry_text(date="2026-11-07", source="umwayi queue add",
                                                                     added="Job open-queue ran (fake)"))
        self.assertEqual(self.run_job("open-queue")[0], 0)  # same day, but not from umwayi run, so it does not count
        write_sealed_logbook(self.root, "# Logbook\n" + entry_text(date="2026-11-07", source="umwayi run",
                                                                     added="Job open-queue ran (command queue-list): x"))
        self.assertEqual(self.run_job("open-queue")[0], 1)

    def test_last_run_after_today_is_refused(self):
        write_sealed_logbook(self.root, "# Logbook\n" + entry_text(date="2026-12-01", source="umwayi run",
                                                                     added="Job open-queue ran (command queue-list): x"))
        self.assert_refused(["run", str(self.root / "jobs.yaml"), "--job", "open-queue"], 1, "after today")

    # -- the rules gate

    def test_no_stops_the_job_with_exit_2_and_one_entry(self):
        (self.root / "rules.yaml").write_text(RULES + "  - id: no-jobs\n    title: t\n    text: No jobs today.\n"
                                              "    verdict: no\n    matchers:\n      type: run_job\n", encoding="utf-8")
        self.make_git()
        code, out, _ = self.run_job("weekly-report")
        self.assertEqual(code, 2)
        self.assertTrue(out.startswith("No\nRule: no-jobs\n"))
        self.assertIn("Job weekly-report did not run.", out)
        self.assertFalse((self.root / "drafts").exists())
        e = after_rules(self.entries())  # L13.3 (13.R7.2): the rules are logged before their first use
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0].added, "Job weekly-report stopped before running (command report): rule no-jobs gave No")

    def test_ask_me_first_stops_the_job_with_exit_3(self):
        for rules_text in ("rules: []\n", "rules:\n  - id: ask-jobs\n    title: t\n    text: t\n    verdict: ask\n"
                           "    matchers:\n      type: run_job\n", "broken: [\n"):
            with self.subTest(rules=rules_text[:20]):
                (self.root / "rules.yaml").write_text(rules_text, encoding="utf-8")
                code, out, _ = self.run_job("open-queue")
                self.assertEqual(code, 3)
                self.assertTrue(out.startswith("Ask me first\n"))
                self.assertNotIn("Q-0001", out)
                self.assertIn("stopped before running", self.entries()[-1].added)

    def test_missing_rules_file_is_ask_me_first(self):
        (self.root / "rules.yaml").unlink()
        self.assertEqual(self.run_job("open-queue")[0], 3)

    def test_the_rules_see_the_job_and_command(self):
        seen = []
        real = jobs.rules.check

        def spy(text, path):
            seen.append(json.loads(text))
            return real(text, path)
        with mock.patch("umwayi.jobs.rules.check", spy):
            self.run_job("open-queue")
        self.assertEqual(seen[0], {"type": "run_job", "job": "open-queue", "command": "queue-list"})

    def test_stop_still_returns_its_verdict_when_the_logbook_fails(self):
        (self.root / "rules.yaml").write_text(RULES + "  - id: no-jobs\n    title: t\n    text: t\n"
                                              "    verdict: no\n    matchers:\n      type: run_job\n", encoding="utf-8")
        with mock.patch("umwayi.jobs.logbook.append", side_effect=UmwayiError("boom")):
            code, out, _ = self.run_job("open-queue")
        self.assertEqual(code, 2)
        self.assertIn("The logbook could not be written (boom). Nothing was logged.", out)

    # -- a failed logbook means no run

    def test_failed_logbook_means_no_run_for_every_command(self):
        self.make_git()
        log_rules(self.root)  # L13.3 (13.R7.2): the rules are logged before their first use, so the refusals change nothing
        for name in ("weekly-report", "open-queue", "read-check", "money-check"):
            with self.subTest(job=name):
                before = self.snap()
                with mock.patch("umwayi.jobs.logbook.append", side_effect=UmwayiError("disk full")):
                    code, out, _ = self.run_job(name)
                self.assertEqual(code, 3)
                self.assertTrue(out.startswith("Ask me first\nRule: (none)\n"))
                self.assertIn(f"Nothing was logged, so job {name} did not run", out)
                self.assertIn("disk full", out)
                self.assertNotIn("Q-0001", out)
                self.assertNotIn("Job " + name + " ran.", out)
                self.assertEqual(self.snap(), before)  # the draft was removed again
        self.assertFalse((self.root / "drafts" / "report-0001.md").exists())

    def test_tampered_logbook_means_no_run_and_no_rules_call(self):
        write_sealed_logbook(self.root, "# Logbook\n" + entry_text(date="2026-11-01"))
        self.log.write_text(self.log.read_text().replace("- Added: x", "- Added: EDITED"), encoding="utf-8")
        with mock.patch("umwayi.jobs.rules.check") as check:
            out = self.assert_refused(["run", str(self.root / "jobs.yaml"), "--job", "open-queue"], 1, "does not match")
        check.assert_not_called()
        self.assertIn("The job did not run", out)

    def test_unsealed_or_malformed_logbook_means_no_run(self):
        self.log.write_text("# Logbook\n" + entry_text(date="2026-11-01"), encoding="utf-8")
        self.assert_refused(["run", str(self.root / "jobs.yaml"), "--job", "open-queue"], 1, "no hash record")
        write_sealed_logbook(self.root, "# Logbook\nstray\n")
        self.assert_refused(["run", str(self.root / "jobs.yaml"), "--job", "open-queue"], 1, "format problem")

    def test_draft_cannot_be_removed_after_a_failed_log_is_reported_loudly(self):
        self.make_git()
        log_rules(self.root)  # L13.3: logged before the patch below, which makes every os.unlink fail
        with mock.patch("umwayi.jobs.logbook.append", side_effect=UmwayiError("x")), \
                mock.patch("umwayi.report.os.unlink", side_effect=OSError("busy")):
            code, _, err = self.run_job("weekly-report")
        self.assertEqual(code, 1)
        self.assertIn("could not be removed, delete it by hand", err)

    # -- refusals and usage errors

    def test_refusals_exit_1_and_change_nothing(self):
        # a missing or bad jobs file is a config error (64); a failure while running is a refusal (1)
        log_rules(self.root)  # L13.3 (13.R7.2): the rules are logged before their first use, so the refusals change nothing
        self.assert_refused(["run", str(self.root / "nope.yaml"), "--job", "x"], 64, "was not found")
        self.assert_refused(["run", str(self.root / "jobs.yaml"), "--job", "weekly-report"], 1, "git log failed")
        bad = self.root / "bad.yaml"
        bad.write_text("jobs:\n  - name: x\n    command: rm\n    min_gap_days: 1\n", encoding="utf-8")
        self.assert_refused(["run", str(bad)], 64, "not on the allow list")
        (self.root / "queue.md").write_text("broken\n", encoding="utf-8")
        self.assert_refused(["run", str(self.root / "jobs.yaml"), "--job", "open-queue"], 1, "queue.md")

    def test_jobs_file_symlink_and_folder(self):
        target = self.root / "real.yaml"
        target.write_text(JOBS, encoding="utf-8")
        link = self.root / "link.yaml"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not supported")
        self.assert_refused(["run", str(link), "--job", "open-queue"], 64, "symbolic link")
        (self.root / "dir.yaml").mkdir()
        self.assert_refused(["run", str(self.root / "dir.yaml"), "--job", "open-queue"], 64, "was not found")

    def test_usage_errors_exit_64(self):
        before = self.snap()
        for argv in (["run"], ["run", str(self.root / "jobs.yaml")], ["run", str(self.root / "jobs.yaml"), "--job", "nope"],
                     ["run", str(self.root / "jobs.yaml"), "--job", "open-queue", "--date", "2026-02-30"],
                     ["run", str(self.root / "jobs.yaml"), "--job", "open-queue", "--shell", "ls"]):
            with self.subTest(argv=argv[1:]):
                self.assertEqual(self.cli(*argv)[0], 64)
        self.assertEqual(self.snap(), before)

    def test_explicit_date_is_used(self):
        self.cli("run", str(self.root / "jobs.yaml"), "--job", "open-queue", "--date", "2027-01-02", clock="2026-11-07")
        self.assertEqual(self.entries()[0].date, "2027-01-02")


# =================================================================== report


class ReportTests(Base):
    COMMITS = (
        ("Add the queue", "2026-11-02T12:00:00+0000"),
        ("Fix a bug, thanks to secret.person@example.org", "2026-11-03T09:00:00+0000"),
        ("Add archive", "2026-11-03T15:00:00+0000"),
        ("Old work before since", "2026-10-20T12:00:00+0000"),
    )

    def test_counts_per_day_and_subjects_and_no_emails(self):
        self.make_git(self.COMMITS)
        code, out, err = self.cli("report", "--since", "2026-11-01")
        self.assertEqual(code, 0, err)
        self.assertIn("Wrote drafts/report-0001.md: 3 commits from 2026-11-01 to 2026-11-07.", out)
        text = (self.root / "drafts" / "report-0001.md").read_text(encoding="utf-8")
        self.assertIn("| 2026-11-02 | 1 |", text)
        self.assertIn("| 2026-11-03 | 2 |", text)
        self.assertIn("- Add the queue", text)
        self.assertIn("- Add archive", text)
        self.assertIn("Fix a bug, thanks to [email removed]", text)
        self.assertNotIn("Old work before since", text)
        self.assertNotIn("@", text)
        self.assertNotIn("Secret Person", text)
        self.assertNotIn("example.org", text)
        self.assertIn("Commits: 3", text)
        self.assertIn("This is a draft", text)

    def test_exact_render(self):
        commits = [report.Commit("2026-11-03", "b"), report.Commit("2026-11-02", "a"), report.Commit("2026-11-03", "c")]
        self.assertEqual(report.render("2026-11-01", "2026-11-07", commits), (
            "# Progress report (draft)\n\nFrom 2026-11-01 to 2026-11-07. Commits: 3 (merge commits are not counted).\n\n"
            "## Commits per day\n\n| day | commits |\n| --- | --- |\n| 2026-11-02 | 1 |\n| 2026-11-03 | 2 |\n\n"
            "## Subjects\n\n### 2026-11-02\n\n- a\n\n### 2026-11-03\n\n- b\n- c\n\n"
            "This is a draft for the owner. Nothing was published or pushed.\n"))

    def test_an_older_commit_on_top_does_not_hide_newer_ones(self):
        # git log --since would stop at the first commit older than the date
        self.make_git((("new one", "2026-11-04T12:00:00+0000"), ("dated in the past", "2026-09-01T12:00:00+0000")))
        self.cli("report", "--since", "2026-11-01")
        text = (self.root / "drafts" / "report-0001.md").read_text()
        self.assertIn("Commits: 1", text)
        self.assertIn("- new one", text)
        self.assertNotIn("dated in the past", text)

    def test_commits_dated_after_today_are_left_out(self):
        self.make_git((("today", "2026-11-07T12:00:00+0000"), ("future", "2026-12-01T12:00:00+0000")))
        self.cli("report", "--since", "2026-11-01")
        text = (self.root / "drafts" / "report-0001.md").read_text()
        self.assertIn("Commits: 1", text)
        self.assertNotIn("future", text)

    def test_too_much_history_is_refused_not_cut(self):
        lines = b"".join(b"2026-11-02\x1fx\n" for _ in range(report.MAX_COMMITS + 1))
        fake = subprocess.CompletedProcess([], 0, stdout=lines, stderr=b"")
        with mock.patch("umwayi.report.subprocess.run", return_value=fake):
            self.assert_refused(["report", "--since", "2026-11-01"], 1, "more than 50000 commits")

    def test_failed_log_also_removes_a_drafts_folder_it_made_but_keeps_an_existing_one(self):
        self.make_git()
        with mock.patch("umwayi.report.logbook.append", side_effect=UmwayiError("x")):
            self.cli("report", "--since", "2026-11-01")
        self.assertFalse((self.root / "drafts").exists())
        (self.root / "drafts").mkdir()
        with mock.patch("umwayi.report.logbook.append", side_effect=UmwayiError("x")):
            self.cli("report", "--since", "2026-11-01")
        self.assertEqual(os.listdir(self.root / "drafts"), [])

    def test_no_commits(self):
        self.make_git((("Old", "2026-01-01T12:00:00+0000"),))
        self.assertEqual(self.cli("report", "--since", "2026-11-01")[0], 0)
        self.assertIn("No commits in this period.", (self.root / "drafts" / "report-0001.md").read_text())

    def test_merge_commits_are_left_out(self):
        self.make_git((("base", "2026-11-02T12:00:00+0000"),))
        git(self.root, "checkout", "-q", "-b", "side")
        commit(self.root, "on side", "2026-11-03T12:00:00+0000")
        git(self.root, "checkout", "-q", "-")
        commit(self.root, "on main", "2026-11-03T13:00:00+0000")
        git(self.root, "merge", "-q", "--no-ff", "-m", "Merge side", "side", date="2026-11-04T12:00:00+0000")
        self.cli("report", "--since", "2026-11-01")
        text = (self.root / "drafts" / "report-0001.md").read_text()
        self.assertIn("Commits: 3", text)
        self.assertNotIn("Merge side", text)

    def test_clean_subject(self):
        self.assertEqual(report.clean_subject("  a\tb  c "), "a b c")
        self.assertEqual(report.clean_subject("mail a.b@c.io and <x@y.com>"), "mail [email removed] and <[email removed]>")
        self.assertEqual(report.clean_subject(""), "(no subject)")
        self.assertEqual(len(report.clean_subject("x" * 500)), 200)
        self.assertEqual(report.clean_subject("bell\x07here"), "bell here")

    def test_draft_numbering_never_overwrites(self):
        self.make_git()
        for n in range(1, 4):
            self.cli("report", "--since", "2026-11-01")
        names = sorted(os.listdir(self.root / "drafts"))
        self.assertEqual(names, ["report-0001.md", "report-0002.md", "report-0003.md"])
        # a gap in the numbers is not filled; other files are ignored
        (self.root / "drafts" / "report-0002.md").unlink()
        (self.root / "drafts" / "report-0009.md").write_text("mine, keep me\n")
        (self.root / "drafts" / "notes.md").write_text("mine too\n")
        (self.root / "drafts" / "report-12.md").write_text("not a report name\n")
        self.cli("report", "--since", "2026-11-01")
        self.assertIn("report-0010.md", os.listdir(self.root / "drafts"))
        self.assertEqual((self.root / "drafts" / "report-0009.md").read_text(), "mine, keep me\n")

    def test_create_draft_skips_a_name_taken_meanwhile(self):
        folder = self.root / "drafts"
        folder.mkdir()
        real_open = os.open
        calls = {"n": 0}

        def racing_open(path, flags, mode=0o777):
            calls["n"] += 1
            if calls["n"] == 1:  # someone creates report-0001.md just before us
                Path(path).write_text("theirs\n")
            return real_open(path, flags, mode)
        with mock.patch("umwayi.report.os.open", racing_open):
            d = report.create_draft(self.root, "ours\n")
        self.assertEqual(d.rel, "drafts/report-0002.md")
        self.assertFalse(d.made_folder)
        self.assertEqual((folder / "report-0001.md").read_text(), "theirs\n")

    def test_one_logbook_entry_and_failed_log_removes_the_draft(self):
        self.make_git()
        self.cli("report", "--since", "2026-11-01")
        self.assertEqual([e.source for e in self.entries()], ["umwayi report"])
        before = self.snap()
        with mock.patch("umwayi.report.logbook.append", side_effect=UmwayiError("nope")):
            code, _, err = self.cli("report", "--since", "2026-11-01")
        self.assertEqual(code, 1)
        self.assertIn("the draft was removed: nope", err)
        self.assertEqual(self.snap(), before)

    def test_refusals(self):
        self.assert_refused(["report", "--since", "2026-11-01"], 1, "git log failed")  # not a repo
        self.make_git()
        self.assert_refused(["report", "--since", "2026-11-08"], 64, "--since is after today")
        (self.root / "drafts").write_text("a file\n")
        self.assert_refused(["report", "--since", "2026-11-01"], 1, "drafts must be a normal folder")

    def test_usage_errors(self):
        for argv in (["report"], ["report", "--since", "2026-02-30"], ["report", "--since", "last week"]):
            with self.subTest(argv=argv):
                self.assertEqual(self.cli(*argv)[0], 64)

    def test_git_missing_or_slow(self):
        with mock.patch("umwayi.report.subprocess.run", side_effect=FileNotFoundError):
            self.assert_refused(["report", "--since", "2026-11-01"], 1, "git is not installed")
        with mock.patch("umwayi.report.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 30)):
            self.assert_refused(["report", "--since", "2026-11-01"], 1, "longer than 30 seconds")

    def test_unreadable_git_output_is_refused(self):
        fake = subprocess.CompletedProcess([], 0, stdout=b"not a date\x1fsubject\n", stderr=b"")
        with mock.patch("umwayi.report.subprocess.run", return_value=fake):
            self.assert_refused(["report", "--since", "2026-11-01"], 1, "could not be read")

    def test_the_one_fixed_git_command(self):
        fake = subprocess.CompletedProcess([], 0, stdout=b"", stderr=b"")
        with mock.patch("umwayi.report.subprocess.run", return_value=fake) as run:
            report.read_git_log(self.root, "2026-11-01", "2026-11-07")
        argv = run.call_args.args[0]
        kwargs = run.call_args.kwargs
        self.assertEqual(argv, [
            "git", "-C", str(self.root), "--no-pager", "-c", "core.pager=cat", "-c", "core.fsmonitor=false",
            "-c", "log.showSignature=false", "log", "--no-merges", "--no-color", "--date=short-local",
            "--format=%cd%x1f%s", "--max-count=50001"])
        self.assertIs(kwargs["shell"], False)
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(kwargs["env"]["GIT_TERMINAL_PROMPT"], "0")
        self.assertNotIn("%ae", " ".join(argv))
        self.assertNotIn("%an", " ".join(argv))

    def test_report_never_writes_to_git(self):
        self.make_git()
        before = subprocess.run(["git", "-C", str(self.root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout
        status_before = subprocess.run(["git", "-C", str(self.root), "status", "--porcelain", "--ignored"],
                                       capture_output=True, text=True).stdout
        self.cli("report", "--since", "2026-11-01")
        after = subprocess.run(["git", "-C", str(self.root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout
        self.assertEqual(before, after)
        status_after = subprocess.run(["git", "-C", str(self.root), "status", "--porcelain", "--ignored"],
                                      capture_output=True, text=True).stdout
        new = set(status_after.splitlines()) - set(status_before.splitlines())
        self.assertTrue(all(l.endswith(("drafts/", "LOGBOOK.md", ".umwayi/")) for l in new), new)


# ================================================================== publish


class PublishTests(Base):
    def setUp(self):
        super().setUp()
        (self.root / "drafts").mkdir()
        self.draft = self.root / "drafts" / "report-0001.md"
        self.draft.write_text("# Draft\n\nHello world.\n", encoding="utf-8")

    def pub(self, *argv, clock="2026-11-07"):
        return self.cli("publish-draft", *argv, clock=clock)

    def test_ask_me_first_without_approval_copies_nothing(self):
        code, out, _ = self.pub("drafts/report-0001.md")
        self.assertEqual(code, 3)
        self.assertTrue(out.startswith("Ask me first\nRule: publish-ask\n"))
        self.assertIn("--approved-by", out)
        self.assertFalse((self.root / "outbox").exists())
        e = after_rules(self.entries())  # L13.3 (13.R7.2): the rules are logged before their first use
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0].added, "publish of drafts/report-0001.md stopped before copying: rule publish-ask gave Ask me first")

    def test_owner_approval_copies_the_exact_bytes_and_logs_one_entry(self):
        code, out, err = self.pub("drafts/report-0001.md", "--approved-by", "Miguel")
        self.assertEqual(code, 0, err)
        self.assertIn("Copied drafts/report-0001.md to outbox/report-0001.txt", out)
        self.assertIn("Nothing was published, sent or pushed.", out)
        self.assertEqual((self.root / "outbox" / "report-0001.txt").read_bytes(), self.draft.read_bytes())
        e = after_rules(self.entries())  # L13.3 (13.R7.2): the rules are logged before their first use
        self.assertEqual(len(e), 1)
        self.assertIn("approved by Miguel after rule publish-ask gave Ask me first", e[0].added)
        self.assertIn(logbook.sha256_hex(self.draft.read_bytes()), e[0].added)
        self.assertIn("No git command and no network were used", e[0].not_done)
        self.assertTrue(self.draft.exists())  # the draft stays

    def test_absolute_path_inside_drafts_works(self):
        self.assertEqual(self.pub(str(self.draft), "--approved-by", "Miguel")[0], 0)

    def test_no_stops_even_with_approval(self):
        (self.root / "rules.yaml").write_text("rules:\n  - id: never\n    title: t\n    text: Not today.\n    verdict: no\n"
                                              "    matchers:\n      type: publish_draft\n", encoding="utf-8")
        code, out, _ = self.pub("drafts/report-0001.md", "--approved-by", "Miguel")
        self.assertEqual(code, 2)
        self.assertTrue(out.startswith("No\nRule: never\n"))
        self.assertFalse((self.root / "outbox").exists())

    def test_yes_copies_without_approval(self):
        (self.root / "rules.yaml").write_text("rules:\n  - id: ok\n    title: t\n    text: t\n    verdict: yes\n"
                                              "    matchers:\n      type: publish_draft\n", encoding="utf-8")
        self.assertEqual(self.pub("drafts/report-0001.md")[0], 0)

    def test_no_rule_or_broken_rules_is_ask_me_first(self):
        for text in ("rules: []\n", "broken: [\n"):
            with self.subTest(rules=text):
                (self.root / "rules.yaml").write_text(text, encoding="utf-8")
                self.assertEqual(self.pub("drafts/report-0001.md")[0], 3)
                self.assertFalse((self.root / "outbox").exists())

    def test_never_overwrites(self):
        self.pub("drafts/report-0001.md", "--approved-by", "Miguel")
        (self.root / "outbox" / "report-0001.txt").write_text("edited by the owner\n")
        self.assert_refused(["publish-draft", "drafts/report-0001.md", "--approved-by", "Miguel"], 1, "already exists")
        self.assertEqual((self.root / "outbox" / "report-0001.txt").read_text(), "edited by the owner\n")

    def test_existing_target_is_refused_before_the_rules_are_asked(self):
        (self.root / "outbox").mkdir()
        (self.root / "outbox" / "report-0001.txt").write_text("owner copy\n")
        with mock.patch("umwayi.publish.rules.check") as check:
            self.assert_refused(["publish-draft", "drafts/report-0001.md", "--approved-by", "M"], 1, "already exists")
        check.assert_not_called()

    def test_target_created_while_asking_the_rules_is_not_overwritten(self):
        real = publish.rules.check

        def racing_check(text, path):
            (self.root / "outbox").mkdir(exist_ok=True)
            (self.root / "outbox" / "report-0001.txt").write_text("someone else\n")
            return real(text, path)
        with mock.patch("umwayi.publish.rules.check", racing_check):
            code, _, err = self.pub("drafts/report-0001.md", "--approved-by", "Miguel")
        self.assertEqual(code, 1)
        self.assertIn("already exists", err)
        self.assertEqual((self.root / "outbox" / "report-0001.txt").read_text(), "someone else\n")
        self.assertEqual(after_rules(self.entries()), [])  # L13.3 (13.R7.2): the rules are logged before their first use

    def test_failed_logbook_removes_the_copy(self):
        log_rules(self.root)  # L13.3 (13.R7.2): the rules are logged before their first use, so the refusal changes nothing
        before = self.snap()
        with mock.patch("umwayi.publish.logbook.append", side_effect=UmwayiError("disk full")):
            code, out, _ = self.pub("drafts/report-0001.md", "--approved-by", "Miguel")
        self.assertEqual(code, 3)
        self.assertIn("nothing was copied", out)
        self.assertFalse((self.root / "outbox" / "report-0001.txt").exists())
        self.assertEqual({k for k in self.snap() if not k.startswith("outbox")}, set(before))

    def test_tampered_logbook_means_nothing_is_copied(self):
        write_sealed_logbook(self.root, "# Logbook\n" + entry_text(date="2026-11-01"))
        self.log.write_text("changed", encoding="utf-8")
        code, out, _ = self.pub("drafts/report-0001.md", "--approved-by", "Miguel")
        self.assertEqual(code, 3)
        self.assertFalse((self.root / "outbox" / "report-0001.txt").exists())

    def test_refusals_exit_1_and_change_nothing(self):
        (self.root / "drafts" / "sub").mkdir()
        (self.root / "drafts" / "sub" / "x.md").write_text("x\n")
        (self.root / "drafts" / "private-plan.md").write_text("secret plan\n")
        (self.root / "drafts" / "empty.md").write_text("  \n")
        (self.root / "drafts" / "bin.md").write_bytes(b"\xff\xfe")
        (self.root / "drafts" / "nul.md").write_bytes(b"a\x00b")
        (self.root / "drafts" / "big.md").write_bytes(b"x" * (publish.MAX_DRAFT_BYTES + 1))
        (self.root / "drafts" / "script.sh").write_text("echo hi\n")
        (self.root / "drafts" / "dir.md").mkdir()
        (self.root / "notes.md").write_text("outside drafts\n")
        cases = [
            ("drafts/nope.md", "not found"),
            ("notes.md", "directly inside the drafts folder"),
            ("drafts/sub/x.md", "directly inside the drafts folder"),
            ("drafts/../notes.md", "'..'"),
            ("/etc/passwd", "directly inside the drafts folder"),
            ("drafts/private-plan.md", "private path"),
            ("drafts/empty.md", "is empty"),
            ("drafts/bin.md", "not valid UTF-8"),
            ("drafts/nul.md", "not plain text"),
            ("drafts/big.md", "larger than"),
            ("drafts/script.sh", "ending in .md or .txt"),
            ("drafts/dir.md", "regular file"),
        ]
        for draft, fragment in cases:
            with self.subTest(draft=draft):
                self.assert_refused(["publish-draft", draft, "--approved-by", "Miguel"], 1, fragment)

    def test_symlinks_refused(self):
        try:
            (self.root / "drafts" / "link.md").symlink_to(self.draft)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not supported")
        self.assert_refused(["publish-draft", "drafts/link.md", "--approved-by", "M"], 1, "symbolic link")
        (self.root / "elsewhere").mkdir()
        (self.root / "outbox").symlink_to(self.root / "elsewhere")
        self.assert_refused(["publish-draft", "drafts/report-0001.md", "--approved-by", "M"], 1, "outbox must be a normal folder")

    def test_config_is_required(self):
        (self.root / "umwayi.json").unlink()
        self.assert_refused(["publish-draft", "drafts/report-0001.md", "--approved-by", "M"], 64, "config")

    def test_bad_approver_and_usage(self):
        for by in ("", "  ", "x" * 101, "a\nb"):
            with self.subTest(by=by[:5]):
                self.assert_refused(["publish-draft", "drafts/report-0001.md", "--approved-by", by], 64, "--approved-by")
        self.assertEqual(self.pub()[0], 64)
        self.assertEqual(self.pub("drafts/report-0001.md", "--push")[0], 64)


# ======================================================== code guarantees


def _tree(name):
    return ast.parse((PKG / name).read_text(encoding="utf-8"))


class CodeGuardTests(unittest.TestCase):
    MODULES = sorted(p.relative_to(PKG).as_posix() for p in PKG.rglob("*.py"))

    def test_no_network_import_anywhere(self):
        banned = {"socket", "ssl", "urllib", "http", "requests", "ftplib", "smtplib", "poplib", "imaplib",
                  "telnetlib", "xmlrpc", "asyncio", "aiohttp", "httpx", "webbrowser"}
        for name in self.MODULES:
            for node in ast.walk(_tree(name)):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    mods = [node.module]
                for m in mods:
                    with self.subTest(module=name, imports=m):
                        if name == "telemetry.py" and m in ("http.server", "socket"):
                            continue  # the budget governor's one-run receiver on 127.0.0.1 (B.R2.1); see test_system
                        if name == "serve.py" and m in ("http.server", "socket"):
                            continue  # the local backend on 127.0.0.1 (W6), inside _classes; see test_system
                        self.assertNotIn(m.split(".")[0], banned)

    def test_subprocess_only_in_report_and_agents(self):
        # Multiline: before layer 10 this pattern had no (?m), so it only looked at the first line and matched nothing.
        pattern = r"(?m)^\s*(import|from)\s+subprocess"
        users = sorted(n for n in self.MODULES if re.search(pattern, (PKG / n).read_text(encoding="utf-8")))
        self.assertEqual(users, ["agents.py", "goalgit.py", "report.py"],
                         "only report.py (git log), agents.py (layer 10 gate checks) and goalgit.py (W9.6b, the fixed "
                         "git list of goal orchestration) may start a program")

    def test_no_shell_anywhere(self):
        for name in self.MODULES:
            src = (PKG / name).read_text(encoding="utf-8")
            with self.subTest(module=name):
                for bad in ("os.system", "os.popen", "os.exec", "os.spawn", "shell=True", "pty.", "commands."):
                    self.assertNotIn(bad, src)

    def test_exactly_one_subprocess_call_and_it_is_the_fixed_git_log(self):
        calls = [n for n in ast.walk(_tree("report.py"))
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and isinstance(n.func.value, ast.Name) and n.func.value.id == "subprocess"
                 and n.func.attr not in ("TimeoutExpired",)]
        self.assertEqual([c.func.attr for c in calls], ["run"])
        call = calls[0]
        self.assertIsInstance(call.args[0], ast.Call)
        self.assertEqual(call.args[0].func.id, "git_log_argv")
        shell = [k for k in call.keywords if k.arg == "shell"]
        self.assertEqual(len(shell), 1)
        self.assertIs(shell[0].value.value, False)

    def test_git_command_is_read_only(self):
        self.assertEqual(report.GIT_LOG_ARGS.count("log"), 1)
        for word in ("push", "commit", "fetch", "pull", "clone", "remote", "config", "add", "reset", "tag",
                     "--exec", "!"):
            self.assertNotIn(word, report.GIT_LOG_ARGS)

    def test_publish_and_jobs_never_start_programs(self):
        for name in ("publish.py", "jobs.py"):
            with self.subTest(module=name):
                imported = set()
                for node in ast.walk(_tree(name)):
                    if isinstance(node, ast.Import):
                        imported |= {a.name.split(".")[0] for a in node.names}
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        imported.add(node.module.split(".")[0])
                self.assertFalse(imported & {"subprocess", "pty", "shutil", "multiprocessing"}, imported)

    def test_allow_list_is_fixed(self):
        self.assertEqual(jobs.ALLOWED_COMMANDS, ("report", "check", "queue-list"))


class StarterFilesTests(unittest.TestCase):
    def test_repo_jobs_file_parses(self):
        js = jobs.load_jobs(REPO / "jobs.yaml")
        self.assertTrue(all(j.command in jobs.ALLOWED_COMMANDS for j in js))

    def test_repo_rules_publishing_is_ask_me_first_and_jobs_are_yes(self):
        from umwayi import rules
        d = rules.check('{"type": "publish_draft"}', REPO / "rules.yaml")
        self.assertEqual((d.answer, d.rule_id), ("Ask me first", "publish-ask"))
        for cmd in jobs.ALLOWED_COMMANDS:
            d = rules.check(json.dumps({"type": "run_job", "job": "x", "command": cmd}), REPO / "rules.yaml")
            self.assertEqual(d.answer, "Yes")
        d = rules.check('{"type": "run_job", "job": "x", "command": "shell"}', REPO / "rules.yaml")
        self.assertEqual(d.answer, "Ask me first")


if __name__ == "__main__":
    unittest.main()
