"""Layer 12, UI.2: `umwayi view snapshot` (12.R4, 12.R9.4, 12.R10.1). Tests first.

Every test runs `python -m umwayi --root ROOT view snapshot ...` as a real child process, with HOME in a temporary
folder. The roots are temporary folders whose own names hold a sentinel word, and the files the command reads hold
sentinel words and a fake secret. None of them may ever appear in the snapshot, in the output or in the logbook
entry. The leaf test is structural: every leaf of the JSON must be a whole number, a boolean, null or one of a
fixed list of strings (the three kill switch words and real dates), at the places where the schema allows them.
"""

import ast
import errno
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from tests.adapters.support import SITECUSTOMIZE
from tests.helpers import entry_text, write_sealed_logbook
from umwayi import logbook

REPO = Path(__file__).resolve().parent.parent
DAY = "2026-11-11"
SECRET = "sk-live-SECRETSENTINEL"
# compared case blind: rule ids are lower case
SENTINELS = ("QTITLESENTINEL", "QRECOMSENTINEL", "QANSWERSENTINEL", "RULEIDSENTINEL", "RULETITLESENTINEL",
             "RULETEXTSENTINEL", "LOGLINESENTINEL", "schedsentinel", "PRIVSENTINEL", "ARCHIVEPOINTERSENTINEL",
             "MEMORYSENTINEL", "ROOTSENTINEL", "HOMESENTINEL", "ENVSENTINEL", SECRET)
SNAP = ".umwayi/snapshot.json"
KEYS = ["schema", "date", "queue", "rules", "logbook", "budget", "kill_switch", "schedule"]
WORDS = {"on", "off", "unknown"}
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

RULES = f"""rules:
  - id: ruleidsentinel-yes-one
    title: RULETITLESENTINEL one
    text: RULETEXTSENTINEL one {SECRET}
    verdict: yes
    matchers:
      type: read_memory
  - id: ruleidsentinel-yes-two
    title: RULETITLESENTINEL two
    text: RULETEXTSENTINEL two
    verdict: yes
    matchers:
      type: schedule_install
  - id: ruleidsentinel-yes-three
    title: RULETITLESENTINEL five
    text: RULETEXTSENTINEL five
    verdict: yes
    matchers:
      type: write_draft
  - id: ruleidsentinel-no
    title: RULETITLESENTINEL three
    text: RULETEXTSENTINEL three
    verdict: no
    matchers:
      type: payment
  - id: ruleidsentinel-no-two
    title: RULETITLESENTINEL six
    text: RULETEXTSENTINEL six
    verdict: no
    matchers:
      type: transfer
  - id: ruleidsentinel-ask
    title: RULETITLESENTINEL four
    text: RULETEXTSENTINEL four
    verdict: ask
    matchers:
      type: publish_thing
"""
QUEUE = (
    "# Queue\n\n| id | kind | title | status | recommendation | answer | answered |\n"
    "| --- | --- | --- | --- | --- | --- | --- |\n"
    "| Q-0001 | task | QTITLESENTINEL open one | open | QRECOMSENTINEL one | | |\n"
    "| Q-0002 | decision | QTITLESENTINEL open two | open | | | |\n"
    f"| Q-0003 | task | QTITLESENTINEL answered | answered | QRECOMSENTINEL two | QANSWERSENTINEL {SECRET} | 2026-11-09 |\n"
    "| Q-0004 | task | QTITLESENTINEL closed | closed | | | 2026-11-09 |\n"
    "| Q-0005 | task | QTITLESENTINEL answered two | answered | | QANSWERSENTINEL two | 2026-11-10 |\n"
)
SCHEDULE = """schedules:
  - name: schedsentinelone
    run: job
    job: open-queue
    every: daily
    at: "08:00"
  - name: schedsentineltwo
    run: job
    jobs_file: jobs.yaml
    job: weekly-report
    every: weekly
    day: mon
    at: "07:30"
  - name: schedsentinelthree
    run: job
    job: open-queue
    every: monthly
    day: 5
    at: "09:00"
"""
# budget entries by hand (the fixed shapes of umwayi/budget.py): the run r1 is settled on 2026-11-09 (13 UU), the run
# r2 is open on 2026-11-11 (100 UU in full), the run r3 is settled on 2026-11-11 (5 UU)
R1, R2, R3 = "1111111111111111", "2222222222222222", "3333333333333333"
TOK = "tokens input 0, output 0, cache_read 0, cache_creation 0; requests 0"


def budget_entry(when, added):
    return entry_text(date=when, source="umwayi budget", added=added, checked="c", not_done="n")


HAND = (
    "# Logbook\n"
    + entry_text(date="2026-11-08", source="hand", added=f"LOGLINESENTINEL one {SECRET}",
                 checked="LOGLINESENTINEL two", not_done="LOGLINESENTINEL three")
    + budget_entry("2026-11-09", f"Reserved run {R1} for agent steward (claude-code): 1000000 micros (100 UU)")
    + budget_entry("2026-11-09", f"Settled run {R1} for agent steward (claude-code): measured 123456 micros (13 UU); "
                                 f"models none; {TOK}; released 876544 micros")
    + budget_entry("2026-11-11", f"Reserved run {R2} for agent steward (claude-code): 1000000 micros (100 UU)")
    + budget_entry("2026-11-11", f"Reserved run {R3} for agent steward (claude-code): 1000000 micros (100 UU)")
    + budget_entry("2026-11-11", f"Settled run {R3} for agent steward (claude-code): measured 50000 micros (5 UU); "
                                 f"models none; {TOK}; released 950000 micros")
)
USED = {"2026-11-09": 13, "2026-11-11": 105}  # UU: settled plus reserved in full


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def leaves(obj, path=()):
    """(path, leaf) of every leaf. A list index is written as '*'."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from leaves(v, path + (k,))
    elif isinstance(obj, list):
        for v in obj:
            yield from leaves(v, path + ("*",))
    else:
        yield path, obj


def real_date(text) -> bool:
    try:
        date.fromisoformat(text)
    except (TypeError, ValueError):
        return False
    return bool(_DATE.match(text))


def week_ending(day: str) -> list:
    d = date.fromisoformat(day)
    return [(d - timedelta(days=6 - i)).isoformat() for i in range(7)]


class World:
    """One umwayi root, one HOME and one fault injector, in a temporary folder."""

    def __init__(self, tmp: Path, name="root"):
        self.tmp = tmp
        self.root = tmp / f"{name}-ROOTSENTINEL"
        self.home = tmp / "HOMESENTINEL"
        self.site = tmp / "site"
        self.root.mkdir()
        self.home.mkdir(exist_ok=True)
        self.site.mkdir(exist_ok=True)
        (self.site / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
        self.log = self.root / "LOGBOOK.md"
        self.rec = self.root / ".umwayi" / "logbook.sha256"
        self.snap = self.root / ".umwayi" / "snapshot.json"

    def env(self, fault=None, extra=None):
        env = {k: v for k, v in os.environ.items()
               if k not in ("PYTHONPATH", "UMWAYI_FAULT", "HOME", "XDG_CONFIG_HOME", "UMWAYI_FAULT_AFTER")}
        env["HOME"] = str(self.home)
        env["PYTHONPATH"] = os.pathsep.join([str(self.site), str(REPO)])
        if fault:
            env["UMWAYI_FAULT"] = fault
            env["UMWAYI_FAULT_TEXT"] = SECRET
        env.update(extra or {})
        return env

    def u(self, *args, fault=None, extra=None, umask=None, timeout=120):
        pre = (lambda: os.umask(umask)) if umask is not None else None
        return subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), *args], capture_output=True,
                              text=True, timeout=timeout, env=self.env(fault, extra), cwd=str(self.tmp),
                              preexec_fn=pre)

    def view(self, *args, **kw):
        return self.u("view", "snapshot", *args, **kw)

    def put(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def files(self):
        """Light fixture: every file the command reads, with the sentinel words and a secret in it."""
        shutil.copy(REPO / "jobs.yaml", self.root / "jobs.yaml")
        shutil.copytree(REPO / "workflows", self.root / "workflows")
        cfg = json.loads((REPO / "umwayi.json").read_text(encoding="utf-8"))
        cfg["private_paths"] = ["memory/private-PRIVSENTINEL"] + cfg["private_paths"]
        self.put("umwayi.json", json.dumps(cfg))
        self.put("rules.yaml", RULES)
        self.put("queue.md", QUEUE)
        self.put("schedule.yaml", SCHEDULE)
        self.put("memory/master.md", f"MEMORYSENTINEL {SECRET}\n")
        self.put("memory/private-PRIVSENTINEL/x.md", f"MEMORYSENTINEL {SECRET}\n")
        self.put("archive/INDEX.md", "| ARCHIVEPOINTERSENTINEL | archive/ARCHIVEPOINTERSENTINEL.md |\n")
        self.put(".env", f"ENVSENTINEL={SECRET}\n")

    def build(self, install=False):
        self.files()
        write_sealed_logbook(self.root, HAND)
        self.ok(self.u("logbook", "seal", "--chain", "--by", "Owner", "--date", DAY))
        for _ in range(2):
            self.ok(self.u("check", '{"type": "read_memory"}', "--date", DAY))
        if install:
            for name in ("schedsentinelone", "schedsentineltwo"):
                self.ok(self.u("schedule", "install", name, "--approved-by", "Owner", "--date", DAY))
            units = self.home / ".config" / "systemd" / "user"
            for f in sorted(units.glob("umwayi-*-schedsentineltwo.service")):
                f.write_text(f.read_text(encoding="utf-8") + "# edited by hand\n", encoding="utf-8")  # not installed
            wants = units / "timers.target.wants"
            wants.mkdir()
            for f in sorted(units.glob("umwayi-*.timer")):
                os.symlink(f, wants / f.name)  # both are enabled
        return self

    def ok(self, r):
        assert r.returncode == 0, (r.args, r.returncode, r.stdout, r.stderr)

    def tree(self):
        out = {}
        for p in sorted(self.root.rglob("*")):
            rel = p.relative_to(self.root).as_posix()
            st = os.lstat(p)
            if stat.S_ISLNK(st.st_mode):
                out[rel] = ("link", os.readlink(p))
            elif stat.S_ISDIR(st.st_mode):
                out[rel] = ("dir",)
            elif stat.S_ISREG(st.st_mode):
                out[rel] = ("file", p.read_bytes(), stat.S_IMODE(st.st_mode))
            else:
                out[rel] = ("other",)
        return out

    def read(self):
        return json.loads(self.snap.read_text(encoding="utf-8"))

    def log_counts(self):
        text = self.log.read_text(encoding="utf-8") if self.log.exists() else ""
        return len(re.findall(r"(?m)^## \d{4}-\d{2}-\d{2}$", text)), len(re.findall(r"(?m)^- Chain: ", text))

    def expected(self, day=DAY, schedule=(3, 0, 0), **override):
        """The snapshot a run has written, read from the logbook after it: its own entry is not in the counts."""
        entries, chain = self.log_counts()
        entries, chain = entries - 1, max(0, chain - 1)
        days = [{"date": d, "used_uu": USED.get(d, 0)} for d in week_ending(day)]
        want = {"schema": 1, "date": day, "queue": {"open": 2, "answered": 2},
                "rules": {"yes": 3, "no": 2, "ask": 1}, "logbook": {"entries": entries, "chain_length": chain},
                "budget": {"days": days}, "kill_switch": "off",
                "schedule": None if schedule is None else
                {"entries": schedule[0], "installed": schedule[1], "enabled": schedule[2]}}
        want.update(override)
        return want


class Case(unittest.TestCase):
    """A light root per test, copied from one built once: the logbook is chained, and the snapshot is not yet run."""

    @classmethod
    def setUpClass(cls):
        cls._base_tmp = tempfile.TemporaryDirectory(prefix="umwayi-view-base-")
        cls.base = World(Path(os.path.realpath(cls._base_tmp.name)), "base").build()

    @classmethod
    def tearDownClass(cls):
        cls._base_tmp.cleanup()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="umwayi-view-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(os.path.realpath(self._tmp.name))
        self.w = World(self.tmp)
        shutil.rmtree(self.w.root)
        shutil.copytree(self.base.root, self.w.root, symlinks=True)

    def run_ok(self, *args, **kw):
        r = self.w.view("--date", DAY, *args, **kw)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def refused(self, code, *args, **kw):
        before = self.w.tree()
        r = self.w.view(*args, **kw)
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        self.assertEqual(self.w.tree(), before, "a refused call changed something")
        self.assertNotIn("Traceback", r.stderr)
        for word in SENTINELS:
            self.assertNotIn(word.lower(), (r.stdout + r.stderr).lower())
        return r


# ===================================================================== the content


class ContentTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="umwayi-view-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(os.path.realpath(self._tmp.name))

    def test_a_fixed_root_gives_exact_bytes_twice_the_same(self):
        outs = []
        for name in ("one", "two"):
            (self.tmp / name).mkdir()
            w = World(self.tmp / name, name).build(install=True)
            r = w.view("--date", DAY)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            data = w.snap.read_bytes()
            self.assertEqual(data, (json.dumps(w.expected(schedule=(3, 1, 2)), indent=2) + "\n").encode("ascii"))
            outs.append(data)
        self.assertEqual(outs[0], outs[1])
        text = outs[0].decode("ascii")
        self.assertTrue(text.startswith('{\n  "schema": 1,\n  "date": "2026-11-11",\n  "queue": {\n'), text[:80])
        self.assertTrue(text.endswith("}\n"))
        self.assertLess(len(outs[0]), 1200)

    def test_the_counts_come_from_the_layers_readers(self):
        w = World(self.tmp).build()
        self.assertEqual(w.log_counts(), (9, 3))  # six by hand, then the seal and two checks
        self.assertEqual(w.view("--date", DAY).returncode, 0)
        got = w.read()
        self.assertEqual(got["logbook"], {"entries": 9, "chain_length": 3})
        self.assertEqual(got["queue"], {"open": 2, "answered": 2})
        self.assertEqual(got["rules"], {"yes": 3, "no": 2, "ask": 1})
        self.assertEqual([d["used_uu"] for d in got["budget"]["days"]], [0, 0, 0, 0, 13, 0, 105])
        self.assertEqual([d["date"] for d in got["budget"]["days"]], week_ending(DAY))
        self.assertEqual(got["kill_switch"], "off")
        self.assertEqual(got["schedule"], {"entries": 3, "installed": 0, "enabled": 0})

    def test_a_drop_in_next_to_an_installed_unit_is_not_installed_exactly_as_umwayi_wrote_it(self):
        w = World(self.tmp).build(install=True)
        units = self.tmp / "HOMESENTINEL" / ".config" / "systemd" / "user"
        self.assertEqual(w.view("--date", DAY).returncode, 0)
        self.assertEqual(w.read()["schedule"], {"entries": 3, "installed": 1, "enabled": 2})
        [one] = sorted(units.glob("umwayi-*-schedsentinelone.service"))
        (units / (one.name + ".d")).mkdir()
        self.assertEqual(w.view("--date", DAY).returncode, 0)
        self.assertEqual(w.read()["schedule"], {"entries": 3, "installed": 0, "enabled": 2})

    def test_the_schedule_numbers_are_those_of_umwayi_schedule_check(self):
        w = World(self.tmp).build(install=True)
        r = w.u("schedule", "check")
        self.assertEqual(r.returncode, 2, r.stdout)  # one is changed by hand
        self.assertEqual(len(re.findall(r": installed; ", r.stdout)), 1)
        self.assertEqual(len(re.findall(r"; enabled$", r.stdout, re.M)), 2)

    def test_the_week_ends_at_date(self):
        w = World(self.tmp).build()
        self.assertEqual(w.view("--date", "2026-11-13").returncode, 0)
        got = w.read()
        self.assertEqual(got["date"], "2026-11-13")
        self.assertEqual([d["date"] for d in got["budget"]["days"]], week_ending("2026-11-13"))
        self.assertEqual([d["used_uu"] for d in got["budget"]["days"]], [0, 0, 13, 0, 105, 0, 0])

    def test_the_default_date_is_today(self):
        w = World(self.tmp)
        before = date.today().isoformat()
        self.assertEqual(w.view().returncode, 0)
        after = date.today().isoformat()
        self.assertIn(w.read()["date"], {before, after})

    def test_an_empty_root_gives_zeros_and_nulls_and_the_default_path(self):
        w = World(self.tmp)
        r = w.view("--date", DAY)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(w.read(), w.expected(queue=None, rules=None, schedule=(0, 0, 0),
                                              budget={"days": [{"date": d, "used_uu": 0} for d in week_ending(DAY)]}))
        self.assertEqual(w.log_counts(), (1, 0))  # its own entry; the chain is not started
        self.assertEqual(w.read()["logbook"], {"entries": 0, "chain_length": 0})
        self.assertIn(".umwayi/snapshot.json", r.stdout)


class LeafTests(Case):
    def test_every_leaf_is_a_number_a_boolean_null_or_one_of_a_fixed_list_of_strings(self):
        for build_null in (False, True):
            with self.subTest(null_parts=build_null):
                if build_null:
                    (self.w.root / "queue.md").unlink()
                    (self.w.root / "rules.yaml").write_text("rules: [", encoding="utf-8")
                    (self.w.root / "schedule.yaml").write_text("nope: [", encoding="utf-8")
                self.run_ok()
                got = self.w.read()
                self.assertEqual(list(got), KEYS)
                self.assertEqual(got["schema"], 1)
                for path, leaf in leaves(got):
                    where = ".".join(path)
                    if leaf is None or isinstance(leaf, bool):
                        continue
                    if isinstance(leaf, int):
                        self.assertTrue(0 <= leaf <= 1_000_000_000, where)
                    elif isinstance(leaf, str):
                        if path == ("kill_switch",):
                            self.assertIn(leaf, WORDS, where)
                        else:
                            self.assertIn(path, (("date",), ("budget", "days", "*", "date")), where)
                            self.assertTrue(real_date(leaf), where)
                    else:
                        self.fail(f"{where}: a leaf of type {type(leaf).__name__}")

    def test_the_key_set_is_exactly_the_list(self):
        self.run_ok()
        got = self.w.read()
        self.assertEqual(list(got["queue"]), ["open", "answered"])
        self.assertEqual(list(got["rules"]), ["yes", "no", "ask"])
        self.assertEqual(list(got["logbook"]), ["entries", "chain_length"])
        self.assertEqual(list(got["budget"]), ["days"])
        self.assertEqual(len(got["budget"]["days"]), 7)
        self.assertTrue(all(list(d) == ["date", "used_uu"] for d in got["budget"]["days"]))
        self.assertEqual(list(got["schedule"]), ["entries", "installed", "enabled"])


class SentinelTests(unittest.TestCase):
    def test_no_planted_word_secret_or_path_is_in_the_file_the_output_or_the_entry(self):
        with tempfile.TemporaryDirectory(prefix="umwayi-view-ROOTSENTINEL-") as t:
            tmp = Path(os.path.realpath(t))
            w = World(tmp).build(install=True)
            before = w.log.read_text(encoding="utf-8")
            for args in ((), ("--out", "outdir/snap.json")):
                (w.root / "outdir").mkdir(exist_ok=True)
                r = w.view("--date", DAY, *args)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                after = w.log.read_text(encoding="utf-8")
                self.assertTrue(after.startswith(before))
                entry, before = after[len(before):], after
                target = w.root / (args[1] if args else SNAP)
                data = target.read_text(encoding="ascii")
                for word in SENTINELS + (str(tmp), str(w.root), str(w.home), os.path.basename(str(w.root))):
                    for what, text in (("file", data), ("stdout", r.stdout), ("stderr", r.stderr)):
                        self.assertNotIn(word.lower(), text.lower(), f"{word!r} in the {what}")
                    self.assertNotIn(word.lower(), entry.lower(), f"{word!r} in the logbook entry")
                self.assertNotIn("/", data)  # no path of any kind
                self.assertNotIn(SECRET, entry + data + r.stdout + r.stderr)


# ===================================================================== a part that cannot be read is null


class PartTests(Case):
    def check_null(self, part, **kw):
        self.run_ok(**kw)
        got = self.w.read()
        self.assertIsNone(got[part], part)
        self.assertEqual(got, self.w.expected(**{part: None}))

    def test_a_missing_queue_a_malformed_queue_and_a_link(self):
        for how in ("missing", "malformed", "link", "fifo", "folder"):
            with self.subTest(how=how):
                self.setUp()
                q = self.w.root / "queue.md"
                if how == "missing":
                    q.unlink()
                elif how == "malformed":
                    q.write_text(QUEUE + "| Q-0009 | task | x | wrong | | | |\n", encoding="utf-8")
                elif how == "link":
                    other = self.w.root / "other.md"
                    other.write_text(QUEUE, encoding="utf-8")
                    q.unlink()
                    os.symlink(other, q)
                elif how == "fifo":
                    q.unlink()
                    os.mkfifo(q)
                else:
                    q.unlink()
                    q.mkdir()
                self.check_null("queue", timeout=30)

    def test_a_missing_a_broken_a_fifo_and_a_dev_zero_rules_file(self):
        for how in ("missing", "broken", "fifo", "devzero", "folder", "binary"):
            with self.subTest(how=how):
                self.setUp()
                r = self.w.root / "rules.yaml"
                r.unlink()
                if how == "broken":
                    r.write_text("rules: [\n", encoding="utf-8")
                elif how == "fifo":
                    os.mkfifo(r)
                elif how == "devzero":
                    os.symlink("/dev/zero", r)
                elif how == "folder":
                    r.mkdir()
                elif how == "binary":
                    r.write_bytes(b"\xff\xfe\x00")
                self.check_null("rules", timeout=30)

    def test_a_bad_budget_entry_gives_null_budget_only(self):
        logbook.append(self.w.root, logbook.Entry(DAY, "umwayi budget", "Reserved nothing at all", "c", "n"))
        self.check_null("budget")
        self.assertEqual(self.w.u("logbook", "verify").returncode, 0)

    def test_a_schedule_file_that_fails_validation_a_link_and_a_missing_unit_folder(self):
        for how in ("invalid", "link", "folder", "binary"):
            with self.subTest(how=how):
                self.setUp()
                s = self.w.root / "schedule.yaml"
                if how == "invalid":
                    s.write_text(SCHEDULE.replace("every: daily", "every: hourly", 1), encoding="utf-8")
                elif how == "link":
                    other = self.w.root / "other.yaml"
                    other.write_text(SCHEDULE, encoding="utf-8")
                    s.unlink()
                    os.symlink(other, s)
                elif how == "folder":
                    s.unlink()
                    s.mkdir()
                else:
                    s.write_bytes(b"\xff\xfe\x00")
                self.check_null("schedule")

    def test_no_schedule_file_is_zero_entries_not_null(self):
        (self.w.root / "schedule.yaml").unlink()
        self.run_ok()
        self.assertEqual(self.w.read(), self.w.expected(schedule=(0, 0, 0)))

    def test_a_unit_folder_that_is_a_link_makes_the_schedule_null(self):
        units = self.w.home / ".config" / "systemd"
        units.mkdir(parents=True)
        os.symlink(self.tmp, units / "user")
        self.check_null("schedule")

    def test_a_reader_that_crashes_gives_null_for_its_part_and_exit_0(self):
        for part, target in (("queue", "umwayi.taskqueue:list_rows"), ("rules", "umwayi.rules:load_rules"),
                             ("budget", "umwayi.budget:parse_ledger"), ("schedule", "umwayi.schedule:counts")):
            with self.subTest(part=part):
                self.setUp()
                self.check_null(part, fault=f"{target}:crash")

    def test_a_kill_switch_that_cannot_be_told_is_unknown_and_on_is_on(self):
        self.run_ok(fault="umwayi.kill:state:crash")
        got = self.w.read()
        self.assertEqual(got["kill_switch"], "unknown")
        self.assertNotIn(SECRET, json.dumps(got))
        self.setUp()
        self.assertEqual(self.w.u("kill", "on", "--reason", "test", "--date", DAY).returncode, 0)
        self.run_ok()
        self.assertEqual(self.w.read()["kill_switch"], "on")

    def test_the_kill_switch_does_not_stop_it(self):
        self.assertEqual(self.w.u("kill", "on", "--date", DAY).returncode, 0)
        r = self.run_ok()
        self.assertNotIn("Ask me first", r.stdout)


# ===================================================================== the tamper check


class TamperTests(Case):
    def tamper_ways(self):
        text = self.w.log.read_text(encoding="utf-8")
        heads = [m.start() for m in re.finditer(r"(?m)^## \d{4}-\d{2}-\d{2}$", text)]
        edited = text.replace("LOGLINESENTINEL one", "edited by hand")
        self.assertNotEqual(edited, text)
        # the first check entry (the second chained entry) taken out
        cut = text[:heads[-2]] + text[heads[-1]:]
        return {
            "an edit, the hash record not updated": (edited, False),
            "an edit, the hash record updated (only the chain finds it)": (edited, True),
            "a chained entry taken out, the hash record updated": (cut, True),
            "a line that is not an entry, the hash record updated": (text + "\nnot an entry\n", True),
        }

    def test_a_broken_logbook_exits_1_and_writes_nothing_three_ways_and_more(self):
        for earlier in (False, True):
            for name in self.tamper_ways():
                with self.subTest(earlier=earlier, way=name):
                    self.setUp()
                    if earlier:
                        self.run_ok()
                    new, rerecord = self.tamper_ways()[name]
                    self.w.log.write_text(new, encoding="utf-8")
                    if rerecord:
                        self.w.rec.write_text(sha(self.w.log.read_bytes()) + "\n", encoding="ascii")
                    self.assertEqual(self.w.u("logbook", "verify").returncode, 1)
                    r = self.refused(1, "--date", DAY)
                    self.assertEqual(r.stdout.count("\n") + r.stderr.count("\n") >= 1, True)
                    self.assertRegex(r.stdout + r.stderr, r"(?i)hash|chain|logbook")
                    self.assertNotIn("edited by hand", r.stdout + r.stderr)
                    self.assertEqual(self.w.snap.exists(), earlier)

    def test_a_broken_logbook_is_checked_before_a_bad_date_is_looked_at_but_after_the_arguments(self):
        text = self.w.log.read_text(encoding="utf-8")
        self.w.log.write_text(text.replace("LOGLINESENTINEL one", "edited"), encoding="utf-8")
        self.refused(64, "--out", "../outside.json")  # the arguments first
        self.refused(1)

    def test_a_crash_while_reading_the_logbook_is_2_never_1(self):
        r = self.refused(2, "--date", DAY, fault="umwayi.logbook:read_checked_chain:crash")
        self.assertIn("unexpected error (RuntimeError)", r.stderr)
        self.assertNotIn(SECRET, r.stdout + r.stderr)


# ===================================================================== --out


class OutTests(Case):
    def test_these_are_refused_with_64_and_change_nothing(self):
        root = self.w.root
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "target.json").write_text("{}", encoding="utf-8")
        (root / "folder.json").mkdir()
        os.symlink(root / "rules.yaml", root / "link-to-rules.json")
        os.symlink(outside / "target.json", root / "link-outside.json")
        os.symlink(outside, root / "linkdir")
        os.link(root / "rules.yaml", root / "hard.json")
        (root / "notasnapshot.json").write_text('{"schema": 1}', encoding="utf-8")
        (root / "notjson.json").write_text("rules:\n", encoding="utf-8")
        (root / "big.json").write_text(" " * 5000 + "{}", encoding="utf-8")
        os.mkfifo(root / "fifo.json")
        self.run_ok("--out", "earlier.json")
        os.link(root / "earlier.json", root / "second-name.json")  # a real snapshot with a second name
        good = json.loads((root / "earlier.json").read_text(encoding="utf-8"))
        good["extra"] = 1
        (root / "extra.json").write_text(json.dumps(good), encoding="utf-8")
        del good["extra"]
        good["queue"]["open"] = -1
        (root / "negative.json").write_text(json.dumps(good), encoding="utf-8")
        good["queue"]["open"] = True
        (root / "bool.json").write_text(json.dumps(good), encoding="utf-8")
        cases = {
            "outside the root": str(outside / "new.json"),
            "outside, relative": "../outside/new.json",
            "dotdot inside": "folder.json/../x.json",
            "dotdot at the start": "../x.json",
            "a link to rules.yaml": "link-to-rules.json",
            "a link to a file outside": "link-outside.json",
            "a folder behind a link": "linkdir/new.json",
            "a hard link": "hard.json",
            "a snapshot with a second name": "earlier.json",
            "a snapshot with a second name, the other name": "second-name.json",
            "a folder": "folder.json",
            "a foreign file, umwayi.json": "umwayi.json",
            "a foreign file, rules.yaml": "rules.yaml",
            "a json file that is not a snapshot": "notasnapshot.json",
            "not json at all": "notjson.json",
            "a file over 4 KB": "big.json",
            "a fifo": "fifo.json",
            "a snapshot with an extra key": "extra.json",
            "a snapshot with a negative count": "negative.json",
            "a snapshot with a boolean as a count": "bool.json",
            "a newline": "a\nb.json",
            "a tab": "a\tb.json",
            "an escape character": "a\x1bb.json",
            "too long": "a" * 1020 + ".json",
            "a name that is too long for the file system": "a" * 300 + ".json",
            "no .json": "snap",
            "another ending": "snap.txt",
            "json in the middle": "snap.json.bak",
            "upper case": "snap.JSON",
            "empty": "",
            "a folder that does not exist": "nope/snap.json",
            "a file as a folder": "rules.yaml/snap.json",
            "the root's own folder": ".",
        }
        before_files = {k: (root / k).read_bytes() for k in ("rules.yaml", "umwayi.json", "notasnapshot.json")}
        for name, given in cases.items():
            with self.subTest(case=name):
                self.refused(64, "--date", DAY, "--out", given, timeout=30)
        self.assertEqual({k: (root / k).read_bytes() for k in before_files}, before_files)
        self.assertEqual(sorted(os.listdir(outside)), ["target.json"])
        self.assertEqual((outside / "target.json").read_text(encoding="utf-8"), "{}")
        self.assertTrue(os.path.islink(root / "link-to-rules.json"))

    def test_a_link_as_the_default_file_or_folder_is_refused(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "target.json").write_text("{}", encoding="utf-8")
        os.symlink(outside / "target.json", self.w.snap)
        self.refused(64, "--date", DAY)
        self.assertEqual((outside / "target.json").read_text(encoding="utf-8"), "{}")
        os.unlink(self.w.snap)
        os.symlink("rules.yaml", self.w.snap)
        before = (self.w.root / "rules.yaml").read_bytes()
        self.refused(64, "--date", DAY)
        self.assertEqual((self.w.root / "rules.yaml").read_bytes(), before)

    def test_these_are_accepted(self):
        root = self.w.root
        (root / "out").mkdir()
        for given, name in (("out/snap.json", "out/snap.json"), ("./out//snap.json", "out/snap.json"),
                            (str(root / "out" / "abs.json"), "out/abs.json"), ("top.json", "top.json"),
                            (str(Path(os.path.realpath(root)) / "real.json"), "real.json"), (SNAP, SNAP)):
            with self.subTest(given=given):
                r = self.w.view("--date", DAY, "--out", given)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                data = (root / name).read_bytes()
                self.assertEqual(json.loads(data)["schema"], 1)
                self.assertIn(f"Wrote a snapshot of counts to {name} (SHA-256 {sha(data)})",
                              self.w.log.read_text(encoding="utf-8"))
                self.assertIn(name, r.stdout)
        self.assertFalse((root / "out" / "snap.json").is_symlink())

    def test_an_earlier_snapshot_is_replaced_and_a_file_that_is_not_ours_is_not(self):
        self.run_ok()
        first = self.w.snap.read_bytes()
        os.chmod(self.w.snap, 0o644)
        self.run_ok()
        second = self.w.snap.read_bytes()
        self.assertNotEqual(first, second)  # its own entry was counted the second time
        self.assertEqual(json.loads(second)["logbook"]["entries"], json.loads(first)["logbook"]["entries"] + 1)
        self.assertEqual(stat.S_IMODE(os.stat(self.w.snap).st_mode), 0o600)

    def test_the_default_path_and_the_mode_are_0600_whatever_the_umask(self):
        for umask in (0o000, 0o022, 0o077):
            with self.subTest(umask=oct(umask)):
                self.setUp()
                self.assertFalse(self.w.snap.exists())
                r = self.w.view("--date", DAY, umask=umask)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                st = os.lstat(self.w.snap)
                self.assertTrue(stat.S_ISREG(st.st_mode))
                self.assertEqual(stat.S_IMODE(st.st_mode), 0o600)
                self.assertEqual(st.st_nlink, 1)
        other = self.w.root / "other.json"
        self.assertEqual(self.w.view("--date", DAY, "--out", "other.json", umask=0).returncode, 0)
        self.assertEqual(stat.S_IMODE(os.stat(other).st_mode), 0o600)

    def test_no_temporary_file_is_left(self):
        self.run_ok()
        left = [p for p in self.w.root.rglob("*") if p.name.endswith(".tmp")]
        self.assertEqual(left, [])


# ===================================================================== the logbook entry


ENTRY = re.compile(
    r"\n## 2026-11-11\n\n- Source: umwayi view snapshot\n"
    r"- Added: Wrote a snapshot of counts to (?P<file>[^\n]+) \(SHA-256 (?P<sha>[0-9a-f]{64})\)\n"
    r"- Checked: the logbook chain was intact before the write\n"
    r"- Not done: no text, path or secret of any file is in the snapshot; the page was not opened\n"
    r"- Chain: [0-9a-f]{64}\n\Z")


class EntryTests(Case):
    def test_one_entry_with_the_name_and_the_sha_256_and_no_content(self):
        before = self.w.log.read_text(encoding="utf-8")
        self.run_ok()
        after = self.w.log.read_text(encoding="utf-8")
        self.assertTrue(after.startswith(before))
        m = ENTRY.match(after[len(before):])
        self.assertTrue(m, after[len(before):])
        self.assertEqual(m.group("file"), SNAP)
        self.assertEqual(m.group("sha"), sha(self.w.snap.read_bytes()))
        self.assertEqual(self.w.u("logbook", "verify").returncode, 0)
        self.assertEqual(self.w.log_counts(), (10, 4))

    def test_the_snapshot_counts_the_logbook_before_its_own_entry(self):
        self.run_ok()
        self.assertEqual(self.w.read()["logbook"], {"entries": 9, "chain_length": 3})

    def test_a_logbook_that_fails_after_the_file_is_written_puts_the_file_back(self):
        for fault, extra in (("umwayi.logbook:append:crash", None),
                             ("umwayi.logbook:append:error_after", {"UMWAYI_FAULT_AFTER": "0"})):
            for earlier in (False, True):
                with self.subTest(fault=fault, earlier=earlier):
                    self.setUp()
                    if earlier:
                        self.run_ok()
                        os.chmod(self.w.snap, 0o640)
                    before = self.w.tree()
                    r = self.w.view("--date", "2026-11-12", fault=fault, extra=extra)
                    self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                    self.assertNotIn(SECRET, r.stdout + r.stderr)
                    self.assertNotIn("Traceback", r.stderr)
                    after = self.w.tree()
                    after.pop(".umwayi/logbook.lock", None)
                    before.pop(".umwayi/logbook.lock", None)
                    self.assertEqual(after, before)

    def test_a_crash_while_writing_the_file_leaves_nothing(self):
        before = self.w.tree()
        r = self.w.view("--date", DAY, fault="umwayi.fsutil:atomic_write:crash")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("unexpected error (RuntimeError)", r.stderr)
        self.assertNotIn(SECRET, r.stdout + r.stderr)
        self.assertEqual(self.w.tree(), before)

    def test_the_entry_is_not_written_when_the_file_cannot_be_(self):
        before = self.w.log.read_bytes()
        self.w.view("--date", DAY, fault="umwayi.fsutil:atomic_write:crash")
        self.assertEqual(self.w.log.read_bytes(), before)


# ===================================================================== arguments, exit codes, changes


class ExitTests(Case):
    def test_usage_errors_exit_64(self):
        for args in (("view",), ("view", "snapshot", "extra"), ("view", "snapshot", "--bogus"),
                     ("view", "snapshot", "--out"), ("view", "snapshot", "--date", "2026-02-30"),
                     ("view", "snapshot", "--date", "tomorrow"), ("view", "snapshot", "--date", "2026-1-1"),
                     ("view", "other")):
            with self.subTest(args=args):
                before = self.w.tree()
                r = self.w.u(*args)
                self.assertEqual(r.returncode, 64, r.stdout + r.stderr)
                self.assertEqual(self.w.tree(), before)

    def test_a_date_before_the_last_logbook_entry_or_too_early_is_64(self):
        self.refused(64, "--date", "2026-11-10")
        w = World(self.tmp, "empty")
        r = w.view("--date", "0001-01-03")
        self.assertEqual(r.returncode, 64, r.stdout + r.stderr)
        self.assertFalse(w.snap.exists())

    def test_only_the_codes_0_1_2_and_64_are_ever_given(self):
        seen = set()
        calls = [("--date", DAY), ("--date", "2026-11-10"), ("--out", "../x.json"), ("--date", "nope")]
        for args in calls:
            seen.add(self.w.view(*args).returncode)
        seen.add(self.w.view("--date", "2026-11-12", fault="umwayi.fsutil:atomic_write:crash").returncode)
        self.w.log.write_text(self.w.log.read_text(encoding="utf-8") + "x\n", encoding="utf-8")
        seen.add(self.w.view("--date", DAY).returncode)
        self.assertLessEqual(seen, {0, 1, 2, 64})
        self.assertTrue({0, 1, 2, 64} <= seen, seen)

    def test_it_changes_no_other_file(self):
        before = self.w.tree()
        self.run_ok()
        after = self.w.tree()
        changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)} - {".umwayi/logbook.lock"}
        self.assertEqual(changed, {"LOGBOOK.md", ".umwayi/logbook.sha256", SNAP})

    def test_it_changes_no_other_file_even_with_the_kill_switch_on_and_a_schedule(self):
        self.w.u("kill", "on", "--date", DAY)
        before = self.w.tree()
        self.run_ok()
        after = self.w.tree()
        changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)} - {".umwayi/logbook.lock"}
        self.assertEqual(changed, {"LOGBOOK.md", ".umwayi/logbook.sha256", SNAP})
        self.assertEqual(self.w.read()["kill_switch"], "on")

    def test_the_output_is_one_plain_line_without_control_characters(self):
        r = self.run_ok()
        self.assertEqual(r.stderr, "")
        self.assertEqual(len(r.stdout.splitlines()), 1)
        self.assertTrue(r.stdout.endswith("\n") and r.stdout[:-1].isprintable())


class CodeGuardTests(unittest.TestCase):
    BANNED = {"subprocess", "socket", "urllib", "http", "ctypes", "ssl", "requests", "asyncio", "multiprocessing",
              "webbrowser", "ftplib", "smtplib", "xmlrpc"}

    def imports(self):
        tree = ast.parse((REPO / "umwayi" / "view.py").read_text(encoding="utf-8"))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names.add((node.module or "").split(".")[0])
        return tree, names

    def test_view_py_imports_only_the_standard_library_and_umwayi(self):
        _tree, names = self.imports()
        self.assertTrue(names)
        for name in names:
            self.assertTrue(name == "umwayi" or name in sys.stdlib_module_names or name == "__future__", name)

    def test_view_py_imports_no_process_or_network_module(self):
        _tree, names = self.imports()
        self.assertEqual(names & self.BANNED, set())

    def test_view_py_does_not_run_a_program_or_open_a_page(self):
        text = (REPO / "umwayi" / "view.py").read_text(encoding="utf-8")
        for word in ("os.system", "os.popen", "os.exec", "os.spawn", "__import__", "eval(", "exec(", "urlopen"):
            self.assertNotIn(word, text)

    def test_view_py_has_no_em_dash(self):
        self.assertNotIn("\u2014", (REPO / "umwayi" / "view.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
