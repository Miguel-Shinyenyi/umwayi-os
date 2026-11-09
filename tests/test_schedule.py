"""Layer 11: scheduled runs through systemd user timers (tasks.md 11.1 to 11.5, requirements 11.R1 to 11.R7).

Every test runs `python -m umwayi ... schedule ...` (or the rendered ExecStart= line) as a real child process.
HOME and XDG_CONFIG_HOME point into a temporary folder, so the real ~/.config is never touched. No systemd,
cron, network or credential is needed or used, and nothing here runs systemctl, crontab or loginctl.
"""

import ast
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.adapters.support import SITECUSTOMIZE
from umwayi import logbook, schedule, taskqueue

REPO = Path(__file__).resolve().parent.parent
CODES = {0, 2, 3, 64}
SCHEDULE = """schedules:
  - name: open-queue
    run: job
    job: open-queue
    every: daily
    at: "07:30"
  - name: weekly-report
    run: job
    jobs_file: jobs.yaml
    job: weekly-report
    every: weekly
    day: wed
    at: "08:05"
  - name: monthly-report
    run: job
    job: weekly-report
    every: monthly
    day: 3
    at: "23:59"
  - name: content-loop
    run: workflow
    workflow: content-loop
    every: daily
    at: "00:00"
"""
QUEUE = ("# Queue\n\n| id | kind | title | status | recommendation | answer | answered |\n"
         "| --- | --- | --- | --- | --- | --- | --- |\n")
ASK_INSTALL = "verdict: ask\n    matchers:\n      type: schedule_install"
YES_REMOVE = "verdict: yes\n    matchers:\n      type: schedule_remove"


def real(p) -> str:
    return os.path.realpath(p)


class ScheduleCase(unittest.TestCase):
    root_name = "root"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="umwayi-schedule-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(real(self._tmp.name))
        self.root = self.tmp / self.root_name
        self.root.mkdir()
        for name in ("rules.yaml", "jobs.yaml", "umwayi.json"):
            shutil.copy(REPO / name, self.root / name)
        for folder in ("workflows", "articles", "memory"):
            if (REPO / folder).is_dir():
                shutil.copytree(REPO / folder, self.root / folder)
        (self.root / "schedule.yaml").write_text(SCHEDULE, encoding="utf-8")
        (self.root / "queue.md").write_text(QUEUE, encoding="utf-8")
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.xdg = self.tmp / "xdg"
        self.units = self.xdg / "systemd" / "user"
        self.site = self.tmp / "site"
        self.site.mkdir()
        (self.site / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")

    # ------------------------------------------------------------ running

    def env(self, extra=None, fault=None, xdg=True):
        env = {k: v for k, v in os.environ.items()
               if k not in ("PYTHONPATH", "UMWAYI_FAULT", "XDG_CONFIG_HOME", "HOME")}
        env["HOME"] = str(self.home)
        if xdg:
            env["XDG_CONFIG_HOME"] = str(self.xdg)
        env["PYTHONPATH"] = os.pathsep.join([str(self.site), str(REPO)])
        if fault:
            env["UMWAYI_FAULT"] = fault
        env.update(extra or {})
        return env

    def run_cli(self, *args, root=None, extra=None, fault=None, xdg=True, date=None):
        argv = [sys.executable, "-m", "umwayi", "--root", str(root or self.root), "schedule", *args]
        if args and args[0] in ("install", "remove") and date:
            argv += ["--date", date]
        r = subprocess.run(argv, capture_output=True, text=True, timeout=120, env=self.env(extra, fault, xdg),
                           cwd=str(self.tmp))
        self.assertIn(r.returncode, CODES, f"exit {r.returncode} is not allowed\n{r.stdout}\n{r.stderr}")
        return r

    # ------------------------------------------------------------ files

    def rules(self, install="ask", remove="yes"):
        text = (REPO / "rules.yaml").read_text(encoding="utf-8")
        text = text.replace(ASK_INSTALL, f"verdict: {install}\n    matchers:\n      type: schedule_install")
        text = text.replace(YES_REMOVE, f"verdict: {remove}\n    matchers:\n      type: schedule_remove")
        (self.root / "rules.yaml").write_text(text, encoding="utf-8")

    def schedule_text(self, text):
        (self.root / "schedule.yaml").write_text(text, encoding="utf-8")

    def base(self, name, root=None):
        rid = hashlib.sha256(real(root or self.root).encode("utf-8")).hexdigest()[:8]
        return f"umwayi-{rid}-{name}"

    def unit(self, name, kind):
        return self.units / f"{self.base(name)}.{kind}"

    def entries(self):
        return logbook.read_checked(self.root)

    def schedule_entries(self):
        return [e for e in self.entries() if e.source == "umwayi schedule"]

    def snapshot(self):
        out = {}
        for top in (self.root, self.home, self.xdg):
            for dp, dn, fn in os.walk(top):
                for d in dn:
                    out[os.path.join(dp, d)] = "dir"
                for f in fn:
                    p = os.path.join(dp, f)
                    out[p] = Path(p).read_bytes() if not os.path.islink(p) else "link"
        return {k: v for k, v in out.items() if not k.endswith(".umwayi/logbook.lock")}

    def install_yes(self, name="open-queue"):
        self.rules(install="yes")
        r = self.run_cli("install", name)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def expected(self, name, every, calendar, command):
        root, src = real(self.root), real(REPO)
        head = (f"# Written by umwayi schedule install for the entry {name} of {root}/schedule.yaml.\n"
                "# umwayi schedule check compares this file byte for byte: change the schedule file, not this file.\n")
        service = (head + "[Unit]\n" + f"Description=umwayi scheduled run {name} ({root})\n\n[Service]\n"
                   "Type=oneshot\n" + f"WorkingDirectory={root}\n" + f"Environment=PYTHONPATH={src}\n"
                   + f"ExecStart={command}\n" + "TimeoutStartSec=30min\nTimeoutStopSec=15s\nKillMode=control-group\n")
        timer = (head + "[Unit]\n" + f"Description=umwayi schedule {name} ({root})\n\n[Timer]\n"
                 + f"OnCalendar={calendar}\n" + "Persistent=true\n" + f"Unit={self.base(name)}.service\n"
                 + "\n[Install]\nWantedBy=timers.target\n")
        return service, timer


# =================================================================== 11.1 validate


class ValidateTests(ScheduleCase):
    ENTRY = '  - name: x\n    run: job\n    job: open-queue\n    every: daily\n    at: "07:30"\n'

    def bad(self, text, line, fragment):
        self.schedule_text(text)
        before = self.snapshot()
        r = self.run_cli("validate")
        self.assertEqual(r.returncode, 64, r.stdout + r.stderr)
        self.assertIn(f"problem: line {line}: ", r.stdout)
        self.assertIn(fragment, r.stdout)
        self.assertEqual(self.snapshot(), before, "validate wrote something")
        return r

    def test_the_test_schedule_and_the_example_are_valid(self):
        r = self.run_cli("validate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ok: 4 schedule(s): open-queue (job open-queue, daily)", r.stdout)
        r = self.run_cli("validate", "--file", str(REPO / "schedule.example.yaml"), root=REPO)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_every_bad_shape_with_its_line(self):
        h = "schedules:\n"
        cases = {
            "name missing": (h + '  - run: job\n    job: open-queue\n    every: daily\n    at: "07:30"\n', 2, "'name' is missing"),
            "unknown key": (h + self.ENTRY + "    shell: ls\n", 7, "'shell' is not allowed"),
            "bad name": (h + self.ENTRY.replace("name: x", "name: Bad_Name"), 2, "name must be"),
            "duplicate": (h + self.ENTRY + self.ENTRY, 7, "already used"),
            "run shell": (h + self.ENTRY.replace("run: job", "run: shell"), 3, "run must be job or workflow"),
            "run agent": (h + self.ENTRY.replace("run: job", "run: agent"), 3, "an agent cannot be scheduled"),
            "every hourly": (h + self.ENTRY.replace("daily", "hourly"), 5, "every must be daily, weekly or monthly"),
            "at 24:00": (h + self.ENTRY.replace("07:30", "24:00"), 6, "at must be a local time"),
            "at 7:3": (h + self.ENTRY.replace('"07:30"', '"7:3"'), 6, "at must be a local time"),
            "day on daily": (h + self.ENTRY + "    day: mon\n", 7, "day is not used with every: daily"),
            "day 29": (h + self.ENTRY.replace("daily", "monthly") + "    day: 29\n", 7, "from 1 to 28"),
            "day monday": (h + self.ENTRY.replace("daily", "weekly") + "    day: monday\n", 7, "one of mon, tue"),
            "weekly no day": (h + self.ENTRY.replace("daily", "weekly"), 5, "a weekly entry needs day"),
            "jobs file outside": (h + self.ENTRY + "    jobs_file: ../jobs.yaml\n", 7, "inside the root"),
            "jobs file absolute": (h + self.ENTRY + "    jobs_file: /etc/passwd\n", 7, "relative path"),
            "unknown job": (h + self.ENTRY.replace("job: open-queue", "job: nope"), 4, "no job with this name"),
            "gap longer than the period": (h + self.ENTRY.replace("job: open-queue", "job: weekly-report"), 5,
                                           "min_gap_days (7) is longer than the daily period"),
            "missing workflow": (h + '  - name: w\n    run: workflow\n    workflow: nope\n    every: daily\n'
                                 '    at: "07:30"\n', 4, "no valid workflow"),
            "workflow with job key": (h + '  - name: w\n    run: workflow\n    workflow: content-loop\n    job: x\n'
                                      '    every: daily\n    at: "07:30"\n', 5, "'job' is not allowed"),
            "21 entries": (h + "".join(self.ENTRY.replace("name: x", f"name: x{i}") for i in range(21)), 1,
                           "at most 20 entries"),
            "wrong top key": ("jobs:\n  - name: x\n", 1, "exactly one top key"),
            "empty list": ("schedules: []\n", 1, "at least one entry"),
        }
        for name, (text, line, fragment) in cases.items():
            with self.subTest(case=name):
                self.bad(text, line, fragment)

    def test_all_problems_are_found_at_once(self):
        self.schedule_text("schedules:\n" + self.ENTRY.replace("daily", "hourly")
                           + self.ENTRY.replace("name: x", "name: y").replace("07:30", "25:00"))
        r = self.run_cli("validate")
        self.assertEqual(r.returncode, 64)
        self.assertIn("problem: line 5: every must be", r.stdout)
        self.assertIn("problem: line 11: at must be", r.stdout)
        self.assertIn("2 problem(s) found", r.stdout)

    def test_bad_files(self):
        path = self.root / "schedule.yaml"
        outside = self.tmp / "outside.yaml"
        outside.write_text(SCHEDULE, encoding="utf-8")
        cases = {
            "missing": (lambda: path.unlink(), "was not found"),
            "too big": (lambda: path.write_bytes(b"#" * (64 * 1024 + 1)), "larger than"),
            "a link": (lambda: (path.unlink(), path.symlink_to(outside)), "regular file"),
            "a folder": (lambda: (path.unlink(), path.mkdir()), "regular file"),
            "not utf-8": (lambda: path.write_bytes(b"schedules:\n  - name: \xff\n"), "not valid UTF-8"),
        }
        for name, (make, fragment) in cases.items():
            with self.subTest(case=name):
                if path.is_dir() and not path.is_symlink():
                    path.rmdir()
                elif path.exists() or path.is_symlink():
                    path.unlink()
                path.write_text(SCHEDULE, encoding="utf-8")
                make()
                r = self.run_cli("validate")
                self.assertEqual(r.returncode, 64, r.stdout + r.stderr)
                self.assertIn(fragment, r.stderr)
        r = self.run_cli("validate", "--file", str(outside))
        self.assertEqual(r.returncode, 64)
        self.assertIn("inside the umwayi root", r.stderr)


class PathRuleTests(unittest.TestCase):
    def test_a_root_with_any_unsafe_character_is_refused_and_named_by_its_role(self):
        for bad in ("ro ot", "ro%ot", "ro$ot", "ro'ot", 'ro"ot', "ro\\ot", "ro;ot", "ro\not", "ro\u00e9ot", "ro*ot"):
            with self.subTest(root=repr(bad)):
                case = ScheduleCase(methodName="run")
                case.root_name = bad
                case.setUp()
                try:
                    before = case.snapshot()
                    r = case.run_cli("validate")
                    self.assertEqual(r.returncode, 64, r.stdout + r.stderr)
                    self.assertIn("problem: path: the root path has a character a unit file cannot hold safely",
                                  r.stdout)
                    self.assertNotIn(bad, r.stdout)
                    for command in (("show",), ("install", "open-queue"), ("check",)):
                        r = case.run_cli(*command)
                        self.assertEqual(r.returncode, 64, (command, r.stdout, r.stderr))
                    self.assertEqual(case.snapshot(), before)
                finally:
                    case.doCleanups()

    def test_the_rule_itself(self):
        good = ("/a", "/home/u/umwayi-os", "/opt/py/bin/python3.13", "/x/a_b+c-d.e")
        bad = ("", "a/b", "/a b", "/a/../b", "/a/./b", "/a/%h", "/a/$X", "/a\n", "/" + "a" * 1024, "/a/b\u00e9")
        for p in good:
            self.assertTrue(schedule._safe_path(p), p)
        for p in bad:
            self.assertFalse(schedule._safe_path(p), repr(p))
        paths = schedule.Paths("/r", "/r/schedule.yaml", "/bad path/python", "/src")
        [problem] = schedule.path_problems(paths)
        self.assertIn("the path of the Python running umwayi", problem.message)


# =================================================================== 11.2 show


class ShowTests(ScheduleCase):
    def test_the_exact_bytes_for_each_every_a_job_and_a_workflow(self):
        root, py = real(self.root), real(sys.executable)
        job = f"{py} -m umwayi --root {root} run {root}/jobs.yaml --job"
        want = {
            "open-queue": self.expected("open-queue", "daily", "*-*-* 07:30:00", f"{job} open-queue"),
            "weekly-report": self.expected("weekly-report", "weekly", "Wed *-*-* 08:05:00", f"{job} weekly-report"),
            "monthly-report": self.expected("monthly-report", "monthly", "*-*-03 23:59:00", f"{job} weekly-report"),
            "content-loop": self.expected("content-loop", "daily", "*-*-* 00:00:00",
                                          f"{py} -m umwayi --root {root} workflow run content-loop"),
        }
        for name, (service, timer) in want.items():
            with self.subTest(entry=name):
                r = self.run_cli("show", name)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(r.stdout, f"Schedule {name}: {self.base(name)}.service and {self.base(name)}.timer "
                                           f"in {self.units}\n--- {self.units}/{self.base(name)}.service\n{service}"
                                           f"--- {self.units}/{self.base(name)}.timer\n{timer}")
                for text in (service, timer):
                    self.assertNotIn("%", text)
                    self.assertNotIn("$", text)

    def test_the_cron_lines(self):
        root, py, src = real(self.root), real(sys.executable), real(REPO)
        r = self.run_cli("show", "--cron")
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.splitlines()
        self.assertEqual(len(lines), 8)
        self.assertEqual(lines[0], f"# umwayi schedule open-queue: the same run as the timer "
                                   f"{self.base('open-queue')}.timer. umwayi never installs a crontab.")
        job = f"/usr/bin/env PYTHONPATH={src} {py} -m umwayi --root {root} run {root}/jobs.yaml --job"
        self.assertEqual(lines[1], f"30 7 * * * {job} open-queue")
        self.assertEqual(lines[3], f"5 8 * * 3 {job} weekly-report")
        self.assertEqual(lines[5], f"59 23 3 * * {job} weekly-report")
        self.assertEqual(lines[7], f"0 0 * * * /usr/bin/env PYTHONPATH={src} {py} -m umwayi --root {root} "
                                   "workflow run content-loop")

    def test_deterministic_two_roots_two_ids_and_nothing_written(self):
        before = self.snapshot()
        a, b = self.run_cli("show"), self.run_cli("show")
        self.assertEqual(a.stdout, b.stdout)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.xdg.exists(), "show made the unit folder")
        other = self.tmp / "other"
        shutil.copytree(self.root, other)
        c = self.run_cli("show", "open-queue", root=other)
        self.assertNotEqual(self.base("open-queue"), self.base("open-queue", other))
        self.assertIn(self.base("open-queue", other), c.stdout)
        self.assertEqual(self.run_cli("show", "nope").returncode, 64)

    def test_the_unit_folder_without_xdg_config_home(self):
        r = self.run_cli("show", "open-queue", xdg=False)
        self.assertIn(f"in {self.home}/.config/systemd/user\n", r.stdout)
        r = self.run_cli("show", "open-queue", extra={"XDG_CONFIG_HOME": "relative/path"})
        self.assertIn(f"in {self.home}/.config/systemd/user\n", r.stdout)


# =================================================================== 11.3 install


class InstallTests(ScheduleCase):
    def files(self, name="open-queue"):
        return [self.unit(name, "service"), self.unit(name, "timer")]

    def assert_no_files(self, name="open-queue"):
        for p in self.files(name):
            self.assertFalse(os.path.lexists(p), f"{p.name} was left")

    def test_yes_writes_both_files_0644_with_one_entry_and_the_commands(self):
        r = self.install_yes()
        shown = self.run_cli("show", "open-queue").stdout
        for p in self.files():
            self.assertEqual(stat.S_IMODE(os.lstat(p).st_mode), 0o644)
            self.assertIn(p.read_text(encoding="utf-8").rstrip("\n"), shown)
        [entry] = self.schedule_entries()
        self.assertTrue(entry.added.startswith(f"Installed schedule open-queue (job open-queue, daily): "
                                               f"{self.base('open-queue')}.service and "), entry.added)
        for p in self.files():
            self.assertIn(f"{p.name} SHA-256 {hashlib.sha256(p.read_bytes()).hexdigest()}", entry.checked)
        self.assertIn("rule schedule-install-ask gave Yes", entry.checked)
        self.assertIn("  systemctl --user daemon-reload", r.stdout)
        self.assertIn(f"  systemctl --user enable --now {self.base('open-queue')}.timer", r.stdout)
        self.assertIn("unless you enable lingering yourself (loginctl enable-linger); umwayi never does.", r.stdout)
        checks = [e for e in self.entries() if e.source == "umwayi check"]
        self.assertEqual(len(checks), 1)
        self.assertIn("action type: schedule_install", checks[0].added)

    def test_no_gives_2_and_writes_nothing(self):
        self.rules(install="no")
        r = self.run_cli("install", "open-queue")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("Rule: schedule-install-ask", r.stdout)
        self.assert_no_files()

    def test_ask_me_first_adds_one_queue_item_and_approved_by_goes_on(self):
        for _ in range(2):
            r = self.run_cli("install", "open-queue")
            self.assertEqual(r.returncode, 3, r.stdout)
            self.assert_no_files()
        self.assertIn("already asks the owner", r.stdout)
        rows = taskqueue.list_rows(self.root, status="open")
        self.assertEqual([x.title for x in rows], ["Install schedule open-queue?"])
        r = self.run_cli("install", "open-queue", "--approved-by", "Miguel")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Approved by: Miguel", r.stdout)
        self.assertIn("gave Ask me first, approved by Miguel", self.schedule_entries()[-1].checked)
        for bad in ("", "   ", "x" * 101, "two\nlines"):
            with self.subTest(approved_by=bad):
                self.assertEqual(self.run_cli("install", "weekly-report", "--approved-by", bad).returncode, 64)

    def test_the_kill_switch_on_or_unknown_gives_3_one_entry_and_no_file(self):
        self.rules(install="yes")
        (self.root / ".umwayi").mkdir()
        (self.root / ".umwayi" / "KILL").write_text("", encoding="utf-8")
        r = self.run_cli("install", "open-queue")
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("The kill switch is on", r.stdout)
        self.assertEqual([e.added for e in self.schedule_entries()],
                         ["Schedule open-queue was not installed: the kill switch is on"])
        self.assertEqual([e for e in self.entries() if e.source == "umwayi check"], [])  # no rule was asked
        shutil.rmtree(self.root / ".umwayi")
        (self.root / ".umwayi").write_text("not a folder", encoding="utf-8")
        r = self.run_cli("install", "open-queue")
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("could not be read", r.stdout)
        self.assert_no_files()

    def test_the_run_lock_held_gives_3(self):
        self.rules(install="yes")
        code = ("import sys, time\nfrom pathlib import Path\nfrom umwayi import runlock\n"
                "with runlock.held(Path(sys.argv[1])):\n    print('held', flush=True)\n    time.sleep(60)\n")
        holder = subprocess.Popen([sys.executable, "-c", code, str(self.root)], stdout=subprocess.PIPE, text=True,
                                  env=self.env())
        self.addCleanup(lambda: (holder.kill(), holder.wait(timeout=30), holder.stdout.close()))
        self.assertEqual(holder.stdout.readline().strip(), "held")
        r = self.run_cli("install", "open-queue")
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("holds the run lock", r.stdout)
        self.assertEqual(self.schedule_entries()[-1].added,
                         "Schedule open-queue was not installed: another umwayi run holds the run lock")
        self.assert_no_files()

    def test_already_installed_is_0_with_no_entry(self):
        self.install_yes()
        before = (self.root / "LOGBOOK.md").read_bytes()
        r = self.run_cli("install", "open-queue")
        self.assertEqual(r.returncode, 0)
        self.assertIn("already installed. Nothing was changed.", r.stdout)
        self.assertEqual((self.root / "LOGBOOK.md").read_bytes(), before)

    def test_a_different_file_already_there_is_never_overwritten(self):
        self.rules(install="yes")
        self.units.mkdir(parents=True)
        self.unit("open-queue", "timer").write_text("[Timer]\nOnCalendar=minutely\n", encoding="utf-8")
        r = self.run_cli("install", "open-queue")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("is never overwritten", r.stderr)
        self.assertEqual(self.unit("open-queue", "timer").read_text(), "[Timer]\nOnCalendar=minutely\n")
        self.assertFalse(self.unit("open-queue", "service").exists())

    def test_a_unit_file_that_is_a_link_or_a_folder_is_refused(self):
        self.rules(install="yes")
        self.units.mkdir(parents=True)
        target = self.tmp / "elsewhere.service"
        self.unit("open-queue", "service").symlink_to(target)
        r = self.run_cli("install", "open-queue")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertFalse(target.exists(), "the link was followed")
        self.assertFalse(self.unit("open-queue", "timer").exists())

    def test_the_unit_folder_a_link_is_refused(self):
        self.rules(install="yes")
        (self.xdg / "systemd").mkdir(parents=True)
        real_folder = self.tmp / "dotfiles"
        real_folder.mkdir()
        self.units.symlink_to(real_folder)
        r = self.run_cli("install", "open-queue")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("not a normal folder", r.stderr)
        self.assertEqual(list(real_folder.iterdir()), [])

    def test_a_crash_after_the_files_are_written_leaves_no_file(self):
        self.rules(install="yes")
        r = self.run_cli("install", "open-queue", fault="umwayi.schedule:fsync_dir:crash")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("stopped by an unexpected error (RuntimeError)", r.stderr)
        self.assert_no_files()

    def test_a_logbook_that_cannot_record_the_install_leaves_no_file(self):
        self.rules(install="yes")
        r = self.run_cli("install", "open-queue", fault="umwayi.logbook:append:error_after",
                         extra={"UMWAYI_FAULT_AFTER": "1"})  # the rules' entry works, the install's does not
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("could not record the install", r.stdout)
        self.assertIn("so the files were removed", r.stdout)
        self.assert_no_files()
        self.assertEqual(logbook.verify(self.root).problems, [])

    def test_a_partial_install_is_finished_keeping_the_identical_file(self):
        self.install_yes()
        timer = self.unit("open-queue", "timer")
        data = timer.read_bytes()
        self.unit("open-queue", "service").unlink()
        r = self.run_cli("install", "open-queue")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(timer.read_bytes(), data)
        self.assertTrue(self.unit("open-queue", "service").exists())


# =================================================================== 11.3 remove


class RemoveTests(ScheduleCase):
    def test_not_installed_is_0(self):
        r = self.run_cli("remove", "open-queue")
        self.assertEqual(r.returncode, 0)
        self.assertIn("not installed. Nothing was changed.", r.stdout)
        self.assertFalse(self.xdg.exists())

    def test_success_removes_both_with_one_entry_and_works_with_the_kill_switch_on(self):
        self.install_yes()
        (self.root / ".umwayi" / "KILL").write_text("", encoding="utf-8")
        r = self.run_cli("remove", "open-queue")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("  systemctl --user daemon-reload", r.stdout)
        for kind in ("service", "timer"):
            self.assertFalse(self.unit("open-queue", kind).exists())
        self.assertTrue(self.schedule_entries()[-1].added.startswith(
            f"Removed schedule open-queue: {self.base('open-queue')}.timer, {self.base('open-queue')}.service from "))

    def test_an_enabled_timer_is_refused_with_the_commands(self):
        self.install_yes()
        wants = self.units / "timers.target.wants"
        wants.mkdir()
        (wants / f"{self.base('open-queue')}.timer").symlink_to(self.unit("open-queue", "timer"))
        r = self.run_cli("remove", "open-queue")
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn(f"  systemctl --user disable --now {self.base('open-queue')}.timer", r.stdout)
        self.assertIn(f"  systemctl --user clean --what=state {self.base('open-queue')}.timer", r.stdout)
        self.assertTrue(self.unit("open-queue", "timer").exists())

    def test_a_changed_file_or_a_drop_in_is_refused(self):
        self.install_yes()
        timer = self.unit("open-queue", "timer")
        good = timer.read_bytes()
        timer.write_bytes(good.replace(b"07:30", b"07:31"))
        r = self.run_cli("remove", "open-queue")
        self.assertEqual(r.returncode, 2)
        self.assertIn("is not what umwayi wrote. Remove it by hand.", r.stdout)
        timer.write_bytes(good)
        (self.units / f"{self.base('open-queue')}.service.d").mkdir()
        r = self.run_cli("remove", "open-queue")
        self.assertEqual(r.returncode, 2)
        self.assertIn(".service.d is a drop-in", r.stdout)
        self.assertTrue(timer.exists())

    def test_no_and_ask_me_first(self):
        self.install_yes()
        self.rules(install="yes", remove="no")
        self.assertEqual(self.run_cli("remove", "open-queue").returncode, 2)
        self.rules(install="yes", remove="ask")
        r = self.run_cli("remove", "open-queue")
        self.assertEqual(r.returncode, 3)
        self.assertIn("Remove schedule open-queue?", [x.title for x in taskqueue.list_rows(self.root, status="open")])
        self.assertTrue(self.unit("open-queue", "service").exists())

    def test_a_logbook_that_cannot_record_the_removal_puts_both_files_back(self):
        self.install_yes()
        before = {k: self.unit("open-queue", k).read_bytes() for k in ("service", "timer")}
        r = self.run_cli("remove", "open-queue", fault="umwayi.logbook:append:error_after",
                         extra={"UMWAYI_FAULT_AFTER": "1"})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("so the files were put back", r.stdout)
        for kind, data in before.items():
            self.assertEqual(self.unit("open-queue", kind).read_bytes(), data)
            self.assertEqual(stat.S_IMODE(os.lstat(self.unit("open-queue", kind)).st_mode), 0o644)


# =================================================================== 11.4 check


class CheckTests(ScheduleCase):
    def line(self, r, name):
        return next(x for x in r.stdout.splitlines() if x.startswith(f"{name} ("))

    def test_every_state(self):
        r = self.run_cli("check")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not installed; not enabled", self.line(r, "open-queue"))
        self.install_yes("open-queue")
        r = self.run_cli("check", "open-queue")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("installed; not enabled", self.line(r, "open-queue"))
        wants = self.units / "timers.target.wants"
        wants.mkdir()
        (wants / f"{self.base('open-queue')}.timer").symlink_to(self.unit("open-queue", "timer"))
        self.assertIn("installed; enabled", self.line(self.run_cli("check", "open-queue"), "open-queue"))
        timer = self.unit("open-queue", "timer")
        good = timer.read_bytes()
        timer.write_bytes(good + b"# edited\n")
        r = self.run_cli("check", "open-queue")
        self.assertEqual(r.returncode, 2)
        self.assertIn("the timer is changed by hand", self.line(r, "open-queue"))
        timer.write_bytes(good)
        (self.units / f"{self.base('open-queue')}.timer.d").mkdir()
        r = self.run_cli("check", "open-queue")
        self.assertEqual(r.returncode, 2)
        self.assertIn(f"drop-in {self.base('open-queue')}.timer.d next to it can override it", r.stdout)
        (self.units / f"{self.base('open-queue')}.timer.d").rmdir()
        self.unit("open-queue", "service").unlink()
        self.unit("open-queue", "service").mkdir()
        r = self.run_cli("check", "open-queue")
        self.assertIn("the service is not a regular file", self.line(r, "open-queue"))
        self.unit("open-queue", "service").rmdir()
        self.assertIn("the service is not installed", self.line(self.run_cli("check", "open-queue"), "open-queue"))

    def test_left_over_units_and_all_together_and_nothing_written(self):
        self.rules(install="yes")
        for name in ("open-queue", "weekly-report", "monthly-report", "content-loop"):
            self.assertEqual(self.run_cli("install", name).returncode, 0)
        r = self.run_cli("check")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("All schedules are installed as umwayi wrote them.", r.stdout)
        other_root = f"umwayi-00000000-gone.timer"
        (self.units / f"{self.base('gone')}.timer").write_text("x", encoding="utf-8")
        (self.units / other_root).write_text("x", encoding="utf-8")  # another root's unit is not ours to report
        before = self.snapshot()
        r = self.run_cli("check")
        self.assertEqual(r.returncode, 2)
        self.assertIn(f"left over: {self.base('gone')}.timer (no entry in the schedule file)", r.stdout)
        self.assertNotIn(other_root, r.stdout)
        self.assertEqual(self.snapshot(), before)

    def test_the_unit_folder_a_link_is_2(self):
        (self.xdg / "systemd").mkdir(parents=True)
        self.units.symlink_to(self.tmp)
        r = self.run_cli("check")
        self.assertEqual(r.returncode, 2)
        self.assertIn("is not a normal folder", r.stdout)


# =================================================================== 11.5 the scheduled run


class ScheduledRunTests(ScheduleCase):
    def run_unit(self, name, extra=None):
        """Run the rendered service the way systemd would start it: its ExecStart=, Environment= and
        WorkingDirectory=, as one real child process (the path rule means one word per path)."""
        self.install_yes(name)
        lines = self.unit(name, "service").read_text(encoding="utf-8").splitlines()
        value = {k: v for k, _, v in (x.partition("=") for x in lines if "=" in x and not x.startswith("#"))}
        argv = value["ExecStart"].split(" ")
        var, _, val = value["Environment"].partition("=")
        env = {"HOME": str(self.home), "PATH": os.environ.get("PATH", "/usr/bin:/bin"), var: val}
        env.update(extra or {})
        r = subprocess.run(argv, capture_output=True, text=True, timeout=300, env=env, cwd=value["WorkingDirectory"])
        return r

    def run_entries(self, source):
        return [e for e in self.entries() if e.source == source]

    def test_a_job_runs_with_its_entry(self):
        r = self.run_unit("open-queue")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        [ran] = self.run_entries("umwayi run")
        self.assertTrue(ran.added.startswith("Job open-queue ran (command queue-list)"), ran.added)

    def test_the_kill_switch_on_stops_the_run_with_3_and_one_entry(self):
        self.install_yes("open-queue")
        (self.root / ".umwayi" / "KILL").write_text("", encoding="utf-8")
        r = self.run_unit("open-queue")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        stops = self.run_entries("umwayi run")
        self.assertEqual(len(stops), 1)
        self.assertIn("kill switch", stops[0].added)

    def test_the_run_lock_held_stops_the_run_with_3(self):
        self.install_yes("open-queue")
        code = ("import sys, time\nfrom pathlib import Path\nfrom umwayi import runlock\n"
                "with runlock.held(Path(sys.argv[1])):\n    print('held', flush=True)\n    time.sleep(60)\n")
        holder = subprocess.Popen([sys.executable, "-c", code, str(self.root)], stdout=subprocess.PIPE, text=True,
                                  env=self.env())
        self.addCleanup(lambda: (holder.kill(), holder.wait(timeout=30), holder.stdout.close()))
        self.assertEqual(holder.stdout.readline().strip(), "held")
        r = self.run_unit("open-queue")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("run lock", self.run_entries("umwayi run")[-1].added)

    def test_a_workflow_stops_at_its_approve_step_with_3_and_one_queue_item(self):
        r = self.run_unit("content-loop")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        rows = [x for x in taskqueue.list_rows(self.root, status="open") if x.title.startswith("Workflow content-loop")]
        self.assertEqual(len(rows), 1, [x.title for x in taskqueue.list_rows(self.root)])


# =================================================================== code guards and units


class CodeGuardTests(unittest.TestCase):
    FORBIDDEN_IMPORTS = {"subprocess", "socket", "urllib", "http", "ctypes", "multiprocessing", "pty", "requests"}

    def test_schedule_py_imports_only_the_standard_library_and_no_program_runner(self):
        tree = ast.parse((REPO / "umwayi" / "schedule.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [(node.module or "").split(".")[0]]
            else:
                if isinstance(node, ast.Attribute) and node.attr in ("system", "popen", "execv", "execve", "execvp",
                                                                     "spawnv", "spawnl", "posix_spawn", "fork"):
                    self.fail(f"schedule.py uses os.{node.attr}")
                continue
            for name in names:
                self.assertNotIn(name, self.FORBIDDEN_IMPORTS)
                self.assertTrue(name == "umwayi" or name in sys.stdlib_module_names or name == "__future__", name)

    def test_no_argument_list_anywhere_names_systemctl_crontab_or_loginctl(self):
        for path in (REPO / "umwayi").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.List, ast.Tuple)):
                    for e in node.elts:
                        if isinstance(e, ast.Constant) and isinstance(e.value, str):
                            self.assertNotIn(e.value.split("/")[-1], ("systemctl", "crontab", "loginctl"),
                                             f"{path.name} line {node.lineno}")

    def test_no_test_here_starts_systemctl_crontab_or_loginctl(self):
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in
                    ("run", "Popen", "call", "check_call", "check_output") and node.args):
                first = node.args[0]
                if isinstance(first, (ast.List, ast.Tuple)) and first.elts:
                    head = first.elts[0]
                    self.assertFalse(isinstance(head, ast.Constant) and str(head.value).split("/")[-1] in
                                     ("systemctl", "crontab", "loginctl"), f"line {node.lineno}")

    def test_the_cli_schedule_handler_never_returns_1(self):
        src = (REPO / "umwayi" / "cli.py").read_text(encoding="utf-8")
        body = src[src.index("def _cmd_schedule"):src.index("def main(")]
        self.assertNotIn("EXIT_ERROR", body)
        self.assertNotIn("return 1", body)


class UnitTests(unittest.TestCase):
    def entry(self, every, day, at="07:05"):
        return schedule.Entry("n", "job", "j", "jobs.yaml", every, at, day, 1)

    def test_calendar(self):
        self.assertEqual(schedule.calendar(self.entry("daily", None)), "*-*-* 07:05:00")
        self.assertEqual(schedule.calendar(self.entry("weekly", "sun")), "Sun *-*-* 07:05:00")
        self.assertEqual(schedule.calendar(self.entry("monthly", 28)), "*-*-28 07:05:00")

    def test_unit_dir(self):
        self.assertEqual(schedule.unit_dir({"XDG_CONFIG_HOME": "/x", "HOME": "/h"}), Path("/x/systemd/user"))
        self.assertEqual(schedule.unit_dir({"XDG_CONFIG_HOME": "rel", "HOME": "/h"}), Path("/h/.config/systemd/user"))
        self.assertEqual(schedule.unit_dir({"HOME": "/h"}), Path("/h/.config/systemd/user"))
        for env in ({}, {"HOME": "rel"}):
            with self.assertRaises(schedule.UmwayiError):
                schedule.unit_dir(env)

    def test_a_target_that_is_not_a_job_or_a_workflow_cannot_be_rendered(self):
        paths = schedule.Paths("/r", "/r/schedule.yaml", "/py", "/src")
        with self.assertRaises(schedule.ConfigError):
            schedule.render(paths, schedule.Entry("n", "agent", "reviewer", None, "daily", "07:00", None, 1))


if __name__ == "__main__":
    unittest.main()
