"""Layer 13, slice 2: Reversal (requirements 13.R4 and 13.R5, design.md "Slice 2: Reversal", tasks L13.2.1).

`umwayi decision reopen ID_OR_HASH --reason TEXT --by NAME [--date D]` writes one new logbook entry that says it is
a reopen and names the old entry by its hash, and opens one new decision row, in one queue commit. The old entry,
the old row and every other logbook line are never changed or marked. `umwayi queue answer` needs `--revisit-if`
for a decision and refuses it for a task.

Every command under test runs as a real child process (`python -m umwayi ...`) with HOME in a temporary folder.
The fixture root is built once through the real commands and copied for each test. The only entries written by
hand are the ones that stand for an answer from before layer 13, and the planted faults.

The Chain value is computed again here from the rule in the requirements, not by umwayi/logbook.py:

    Chain = sha256(previous Chain value + "\\n" + entry text).hexdigest()
"""

import ast
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.adapters.support import SITECUSTOMIZE
from umwayi import logbook
from umwayi.errors import UmwayiError

REPO = Path(__file__).resolve().parent.parent
EM_DASH = "\u2014"
SECRET = "SENTINEL-REASON-TEXT-7f3a"
YES = '{"type": "read_memory"}'  # the repo's starter rules say Yes
D1, D2, D3, D4, D5, D6, D7 = (f"2026-11-0{n}" for n in range(1, 8))
LOCKS = (".umwayi/logbook.lock", ".umwayi/reopen.lock")
_HEX = re.compile(r"[0-9a-f]{64}")

REOPEN_SOURCE = "umwayi decision reopen"
NOT_DONE = "The old entry, the old row {id} and the rules were not changed or marked. Nothing was decided again."


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def blocks(text: str) -> list:
    """Every entry of a logbook text, read here by the format rule (not by umwayi): a dict per entry."""
    lines = text.split("\n")
    out = []
    for h, line in enumerate(lines):
        if not line.startswith("## "):
            continue
        if h + 5 >= len(lines):
            continue  # an entry cut off at the end (a planted fault): not read
        fields = {}
        for label, key in (("Source", "source"), ("Added", "added"), ("Checked", "checked"), ("Not done", "not_done")):
            fields[key] = lines[h + 2 + len(fields)][len(f"- {label}: "):]
        nxt = lines[h + 6] if h + 6 < len(lines) else ""
        fields["chain"] = nxt[len("- Chain: "):] if nxt.startswith("- Chain: ") else None
        fields["date"] = line[3:]
        fields["text"] = "".join(x + "\n" for x in lines[h:h + 6])
        fields["heading"] = h
        out.append(fields)
    return out


def chain_ok(text: str) -> bool:
    """The chain of the whole text, recomputed here."""
    lines = text.split("\n")
    prev = None
    for b in blocks(text):
        if b["chain"] is None:
            if prev is not None:
                return False
            continue
        if prev is None:
            prev = sha("".join(x + "\n" for x in lines[:b["heading"] - 1]).encode("utf-8"))
        if b["chain"] != sha((prev + "\n" + b["text"]).encode("utf-8")):
            return False
        prev = b["chain"]
    return True


def snapshot(root: Path) -> dict:
    """Every file of the root, by relative path, with its bytes; the two lock files (flock, no data) left out."""
    out = {}
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            full = Path(dp) / f
            rel = full.relative_to(root).as_posix()
            if rel not in LOCKS and "__pycache__" not in rel:
                out[rel] = full.read_bytes()
    return out


class ReopenCase(unittest.TestCase):
    """A root with a chained logbook and these rows, built once through the real commands:

    Q-0001 decision, answered on D3 (chained) with --revisit-if "the name is taken"
    Q-0002 task, answered on D3 (chained)
    Q-0003 decision, answered on D1 with --revisit-if none, before the chain started (unchained)
    Q-0004 decision, open
    Q-0005 decision, answered on D3 with --revisit-if none, then closed on D3 (two closing entries)
    and one `umwayi check` entry on D3 (chained).
    """

    template: Path = None

    @classmethod
    def setUpClass(cls):
        cls._ctmp = tempfile.TemporaryDirectory(prefix="umwayi-reopen-tpl-")
        base = Path(os.path.realpath(cls._ctmp.name))
        cls.template = base / "root"
        cls.template.mkdir()
        shutil.copy(REPO / "rules.yaml", cls.template / "rules.yaml")
        home = base / "home"
        home.mkdir()
        env = cls._env_for(home, base / "site")

        def u(*args):
            r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(cls.template), *args],
                               capture_output=True, text=True, timeout=120, env=env, cwd=str(base))
            if r.returncode != 0:
                raise AssertionError(f"fixture step {args} failed: {r.returncode} {r.stdout} {r.stderr}")

        u("queue", "add", "--kind", "decision", "Pick a name", "--date", D1)
        u("queue", "add", "--kind", "task", "Write docs", "--date", D1)
        u("queue", "add", "--kind", "decision", "Old choice", "--date", D1)
        u("queue", "answer", "Q-0003", "--answer", "Yes", "--revisit-if", "none", "--date", D1)
        u("logbook", "seal", "--chain", "--by", "Owner", "--date", D2)
        u("queue", "answer", "Q-0001", "--answer", "Use umwayi", "--revisit-if", "the name is taken", "--date", D3)
        u("queue", "answer", "Q-0002", "--answer", "done", "--date", D3)
        u("queue", "add", "--kind", "decision", "Open one", "--date", D3)
        u("queue", "add", "--kind", "decision", "Twice", "--date", D3)
        u("queue", "answer", "Q-0005", "--answer", "Yes", "--revisit-if", "none", "--date", D3)
        u("queue", "close", "Q-0005", "--date", D3)
        u("check", YES, "--date", D3)

    @classmethod
    def tearDownClass(cls):
        cls._ctmp.cleanup()

    @staticmethod
    def _env_for(home: Path, site: Path, fault=None, extra=None) -> dict:
        site.mkdir(exist_ok=True)
        (site / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
        env = {k: v for k, v in os.environ.items()
               if k not in ("PYTHONPATH", "UMWAYI_FAULT", "UMWAYI_FAULT_AFTER", "UMWAYI_FAULT_PAUSE", "HOME",
                            "XDG_CONFIG_HOME")}
        env["HOME"] = str(home)
        env["XDG_CONFIG_HOME"] = str(home / ".config")
        env["PYTHONPATH"] = os.pathsep.join([str(site), str(REPO)])
        if fault:
            env["UMWAYI_FAULT"] = fault
            env["UMWAYI_FAULT_TEXT"] = SECRET
        env.update(extra or {})
        return env

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="umwayi-reopen-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(os.path.realpath(self._tmp.name))
        self.root = self.tmp / "root"
        shutil.copytree(self.template, self.root)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.site = self.tmp / "site"
        self.log = self.root / "LOGBOOK.md"
        self.q = self.root / "queue.md"
        self.rec = self.root / ".umwayi" / "logbook.sha256"

    def env(self, fault=None, extra=None):
        return self._env_for(self.home, self.site, fault, extra)

    def u(self, *args, fault=None, extra=None):
        return subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), *args], capture_output=True,
                              text=True, timeout=120, env=self.env(fault, extra), cwd=str(self.tmp))

    def reopen(self, target, reason="New facts came in", by="Owner", date=D5, fault=None, extra=None):
        args = ["decision", "reopen", target, "--reason", reason, "--by", by]
        if date is not None:
            args += ["--date", date]
        return self.u(*args, fault=fault, extra=extra)

    # ------------------------------------------------------------------ helpers

    def logtext(self) -> str:
        return self.log.read_text(encoding="utf-8")

    def entries(self) -> list:
        return blocks(self.logtext())

    def hash_of(self, source, added_prefix) -> str:
        found = [b for b in self.entries() if b["source"] == source and b["added"].startswith(added_prefix)]
        self.assertTrue(found, f"no entry of {source} starting with {added_prefix}")
        return found[-1]["chain"]

    def rows(self) -> list:
        return [l for l in self.q.read_text(encoding="utf-8").splitlines() if l.startswith("| Q-")]

    def row(self, rid) -> str:
        [r] = [l for l in self.rows() if l.startswith(f"| {rid} |")]
        return r

    def rerecord(self):
        self.rec.write_text(sha(self.log.read_bytes()) + "\n", encoding="ascii")

    def assert_refused(self, r, code, *fragments):
        """The exit code, the fragments in stderr, no traceback, no secret, no em dash."""
        text = r.stdout + r.stderr
        self.assertEqual(r.returncode, code, text)
        for f in fragments:
            self.assertIn(f, r.stderr)
        self.assertNotIn("Traceback", text)
        self.assertNotIn(SECRET, text)
        self.assertNotIn(EM_DASH, text)

    def assert_nothing_changed(self, before, r, code, *fragments):
        self.assert_refused(r, code, *fragments)
        self.assertEqual(snapshot(self.root), before, "a refused command changed a file")


# ============================================================ the planted fault: a reopen of a missing entry


class MissingEntryTests(ReopenCase):
    """13.R4.5 and the exit code table: refused with nothing changed, 1 for a record that does not fit, 64 for a
    target that is not an id or a hash."""

    def test_an_unknown_hash_is_refused_with_exit_1(self):
        before = snapshot(self.root)
        self.assert_nothing_changed(before, self.reopen("ab" * 32, reason=SECRET), 1, "no entry of the logbook")

    def test_a_hash_of_63_or_65_characters_or_in_uppercase_is_a_usage_error(self):
        h = self.hash_of("umwayi queue answer", "Q-0001 ")
        before = snapshot(self.root)
        for bad in (h[:63], h + "0", h.upper(), "g" * 64, "", "q-0001", "Q-1", "Q-0001x", "Q-0001 ", "../Q-0001"):
            with self.subTest(target=bad):
                self.assert_nothing_changed(before, self.reopen(bad, reason=SECRET), 64)

    def test_a_hash_of_an_entry_that_is_not_a_closing_entry_is_refused(self):
        before = snapshot(self.root)
        for source, prefix in (("umwayi check", ""), ("umwayi queue add", "Q-0004 "), ("umwayi logbook seal", "")):
            with self.subTest(source=source):
                h = self.hash_of(source, prefix)
                self.assert_nothing_changed(before, self.reopen(h, reason=SECRET), 1,
                                            "not a closing entry of a decision")

    def test_a_hash_of_an_older_closing_entry_is_refused(self):
        h = self.hash_of("umwayi queue answer", "Q-0005 ")  # Q-0005 was closed after it was answered
        before = snapshot(self.root)
        self.assert_nothing_changed(before, self.reopen(h, reason=SECRET), 1, "not the newest closing entry of Q-0005")

    def test_an_id_that_does_not_exist_is_refused(self):
        before = snapshot(self.root)
        self.assert_nothing_changed(before, self.reopen("Q-0099", reason=SECRET), 1, "no row with id Q-0099")

    def test_a_task_is_refused_by_id_and_by_hash(self):
        before = snapshot(self.root)
        self.assert_nothing_changed(before, self.reopen("Q-0002", reason=SECRET), 1, "Q-0002 is a task")
        h = self.hash_of("umwayi queue answer", "Q-0002 ")
        self.assert_nothing_changed(before, self.reopen(h, reason=SECRET), 1, "Q-0002 is a task")

    def test_an_open_decision_is_refused(self):
        before = snapshot(self.root)
        self.assert_nothing_changed(before, self.reopen("Q-0004", reason=SECRET), 1, "Q-0004 is open")

    def test_an_entry_written_before_the_chain_started_is_refused(self):
        before = snapshot(self.root)
        self.assert_nothing_changed(before, self.reopen("Q-0003", reason=SECRET), 1, "before the hash chain started")

    def test_a_decision_answered_by_hand_with_no_closing_entry_is_refused(self):
        text = self.q.read_text(encoding="utf-8").replace("| Q-0004 | decision | Open one | open |  |  |  |",
                                                          "| Q-0004 | decision | Open one | answered |  | Yes | 2026-11-04 |")
        self.assertIn("| Q-0004 | decision | Open one | answered |", text)
        self.q.write_text(text, encoding="utf-8")
        before = snapshot(self.root)
        self.assert_nothing_changed(before, self.reopen("Q-0004", reason=SECRET), 1, "no closing entry")

    def test_a_logbook_whose_chain_has_not_started_is_refused(self):
        root = self.tmp / "unchained"
        root.mkdir()
        for args in (["queue", "add", "--kind", "decision", "One", "--date", D1],
                     ["queue", "answer", "Q-0001", "--answer", "Yes", "--revisit-if", "none", "--date", D1]):
            r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(root), *args], capture_output=True,
                               text=True, env=self.env(), cwd=str(self.tmp))
            self.assertEqual(r.returncode, 0, r.stderr)
        before = snapshot(root)
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(root), "decision", "reopen", "Q-0001",
                            "--reason", SECRET, "--by", "Owner", "--date", D5], capture_output=True, text=True,
                           env=self.env(), cwd=str(self.tmp))
        self.assert_refused(r, 1, "the hash chain has not started", "umwayi logbook seal --chain")
        self.assertEqual(snapshot(root), before)

    def test_no_logbook_or_no_queue_is_refused(self):
        self.q.unlink()
        before = snapshot(self.root)
        self.assert_nothing_changed(before, self.reopen("Q-0001", reason=SECRET), 1, "queue.md")
        root = self.tmp / "empty"
        root.mkdir()
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(root), "decision", "reopen", "Q-0001",
                            "--reason", "r", "--by", "Owner"], capture_output=True, text=True, env=self.env(),
                           cwd=str(self.tmp))
        self.assert_refused(r, 1, "the hash chain has not started")
        self.assertEqual(os.listdir(root), [])  # not even a lock file or a .umwayi folder

    def test_a_queue_md_that_does_not_parse_is_refused(self):
        self.q.write_text(self.q.read_text(encoding="utf-8") + "| Q-0009 | decision | broken |\n", encoding="utf-8")
        before = snapshot(self.root)
        self.assert_nothing_changed(before, self.reopen("Q-0001", reason=SECRET), 1, "queue.md line")


# ============================================================ the planted fault: a broken chain


class BrokenRecordTests(ReopenCase):
    """13.R4.6: a logbook that fails the tamper check or the chain, a changed hash record, a torn tail: exit 1 and
    nothing is written."""

    def refused(self, *fragments):
        before = snapshot(self.root)
        self.assert_nothing_changed(before, self.reopen("Q-0001", reason=SECRET), 1, *fragments)
        h = self.hash_of("umwayi queue answer", "Q-0001 ")
        self.assert_nothing_changed(before, self.reopen(h, reason=SECRET), 1, *fragments)

    def test_an_old_chained_entry_edited_with_the_record_rewritten(self):
        text = self.logtext().replace("- Added: Q-0002 marked answered", "- Added: Q-0002 marked ANSWERED")
        self.log.write_text(text, encoding="utf-8")
        self.rerecord()
        self.refused("the hash chain is broken")

    def test_a_deleted_chained_entry_with_the_record_rewritten(self):
        b = [x for x in self.entries() if x["source"] == "umwayi queue add" and x["added"].startswith("Q-0004 ")][0]
        lines = self.logtext().split("\n")
        del lines[b["heading"] - 1:b["heading"] + 7]  # its blank line, heading, blank, four fields and Chain
        self.log.write_text("\n".join(lines), encoding="utf-8")
        self.rerecord()
        self.assertEqual(self.u("logbook", "verify").returncode, 1)
        self.refused("the hash chain is broken")

    def test_an_edit_without_the_record(self):
        self.log.write_text(self.logtext().replace("as open: Open one", "as open: Open two"), encoding="utf-8")
        self.refused("does not match its recorded hash")

    def test_a_changed_hash_record(self):
        self.rec.write_text("0" * 64 + "\n", encoding="ascii")
        self.refused("does not match its recorded hash")
        self.rec.write_text("not a hash\n", encoding="ascii")
        self.refused("malformed")

    def test_a_torn_tail(self):
        before_bytes = self.log.read_bytes()

        class Killed(BaseException):
            pass

        with mock.patch.object(logbook, "_record_hash", side_effect=Killed):
            with self.assertRaises(Killed):
                logbook.append(self.root, logbook.Entry(D4, "umwayi test", "a write that stops", "x", "y"))
        self.log.write_bytes(self.log.read_bytes()[:len(before_bytes) + 10])  # only 10 bytes reached the disk
        self.refused("part of an entry")

    def test_a_tail_cut_inside_an_entry_with_the_record_rewritten(self):
        self.log.write_bytes(self.log.read_bytes()[:-30])
        self.rerecord()
        self.refused("format problem")

    def test_a_recoverable_interrupted_write_is_read_as_the_file_it_left(self):
        """Not refused: the same checks as read_checked. The append of the reopen recovers it first (one recovery
        entry, then the reopen entry), as every write does."""

        class Killed(BaseException):
            pass

        with mock.patch.object(logbook, "_record_hash", side_effect=Killed):
            with self.assertRaises(Killed):
                logbook.append(self.root, logbook.Entry(D4, "umwayi test", "a write that stops", "x", "y"))
        before = self.log.read_bytes()
        r = self.reopen("Q-0001")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        after = self.log.read_bytes()
        self.assertTrue(after.startswith(before))
        self.assertEqual([b["source"] for b in blocks(after[len(before):].decode("utf-8"))],
                         [logbook.RECOVER_SOURCE, REOPEN_SOURCE])
        self.assertEqual(self.u("logbook", "verify").returncode, 0)


# ============================================================ the happy path


class HappyPathTests(ReopenCase):
    def test_one_entry_is_appended_and_names_the_old_entry_by_its_full_hash(self):
        h = self.hash_of("umwayi queue answer", "Q-0001 ")
        a = self.u("logbook", "anchor")
        self.assertEqual(a.returncode, 0, a.stderr)
        anchor = a.stdout.splitlines()[0]
        before_log = self.log.read_bytes()
        before_q = self.q.read_text(encoding="utf-8")
        before = snapshot(self.root)
        r = self.reopen("Q-0001")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

        after_log = self.log.read_bytes()
        self.assertTrue(after_log.startswith(before_log), "an earlier logbook byte was changed")
        new = blocks(after_log[len(before_log):].decode("utf-8"))
        self.assertEqual(len(new), 1, "more than one entry was appended")
        [e] = new
        self.assertEqual(after_log[len(before_log):].decode("utf-8"),
                         "\n" + e["text"] + f"- Chain: {e['chain']}\n", "the block is not exactly one entry")
        self.assertEqual(e["date"], D5)
        self.assertEqual(e["source"], REOPEN_SOURCE)
        self.assertEqual(e["added"], f"Reopen of entry {h} (Q-0001 answered on {D3}); new decision Q-0006 opened by "
                                     "Owner; reason: New facts came in")
        self.assertTrue(e["added"].startswith("Reopen of entry "))
        self.assertEqual(e["checked"], f"the hash chain was intact before this entry; {h} is a chained entry of "
                                       "source umwayi queue answer for Q-0001; Q-0001 is a decision that is not open; "
                                       "revisit if recorded then: the name is taken")
        self.assertEqual(e["not_done"], NOT_DONE.format(id="Q-0001"))
        self.assertTrue(_HEX.fullmatch(e["chain"]))
        self.assertTrue(chain_ok(self.logtext()))

        after_q = self.q.read_text(encoding="utf-8")
        self.assertEqual(after_q, before_q + "| Q-0006 | decision | Reopen decision Q-0001 | open | Reopened on "
                                              f"{D5} by Owner: New facts came in |  |  |\n")
        self.assertEqual(self.row("Q-0001"), "| Q-0001 | decision | Pick a name | answered |  | Use umwayi | 2026-11-03 |")

        changed = {k for k in set(before) | set(snapshot(self.root)) if before.get(k) != snapshot(self.root).get(k)}
        self.assertEqual(changed, {"LOGBOOK.md", "queue.md", ".umwayi/logbook.sha256"})

        self.assertEqual(self.u("logbook", "verify").returncode, 0)
        v = self.u("logbook", "verify", "--anchor", anchor)
        self.assertEqual(v.returncode, 0, v.stdout)

        self.assertIn("Reopened Q-0001 as Q-0006", r.stdout)
        self.assertIn(h, r.stdout)
        self.assertIn("Revisit if recorded then: the name is taken", r.stdout)
        self.assertNotIn(EM_DASH, r.stdout)

    def test_the_hash_works_like_the_id(self):
        h = self.hash_of("umwayi queue answer", "Q-0001 ")
        r = self.reopen(h)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.entries()[-1]["added"].startswith(f"Reopen of entry {h} (Q-0001 answered on {D3}); "))

    def test_a_closed_decision_links_its_close_entry_and_shows_the_revisit_of_its_answer(self):
        h = self.hash_of("umwayi queue close", "Q-0005 ")
        r = self.reopen("Q-0005")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        e = self.entries()[-1]
        self.assertEqual(e["added"], f"Reopen of entry {h} (Q-0005 closed on {D3}); new decision Q-0006 opened by "
                                     "Owner; reason: New facts came in")
        self.assertEqual(e["checked"], f"the hash chain was intact before this entry; {h} is a chained entry of "
                                       "source umwayi queue close for Q-0005; Q-0005 is a decision that is not open; "
                                       "revisit if recorded then: none")
        self.assertIn("Revisit if recorded then: none", r.stdout)

    def test_a_decision_closed_without_an_answer_records_no_revisit_text(self):
        self.assertEqual(self.u("queue", "close", "Q-0004", "--date", D4).returncode, 0)
        r = self.reopen("Q-0004")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.entries()[-1]["checked"].endswith(
            "revisit if recorded then: not recorded, closed without an answer"))

    def test_the_longest_reason_and_name_are_taken_whole(self):
        reason, by = "r" * 299 + "s", "N" * 40
        r = self.reopen("Q-0001", reason=reason, by=by)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.entries()[-1]["added"].endswith(f"opened by {by}; reason: {reason}"))
        self.assertIn(f"| Reopened on {D5} by {by}: {reason} |", self.row("Q-0006"))

    def test_the_new_id_is_never_reused_even_if_the_row_is_deleted_by_hand(self):
        self.assertEqual(self.reopen("Q-0001").returncode, 0)
        self.q.write_text("".join(l + "\n" for l in self.q.read_text(encoding="utf-8").splitlines()
                                  if not l.startswith("| Q-0006 ")), encoding="utf-8")
        r = self.u("queue", "add", "--kind", "task", "Next", "--date", D6)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Added Q-0007", r.stdout)

    def test_a_reopen_row_deleted_by_hand_is_not_recreated(self):
        self.assertEqual(self.reopen("Q-0001").returncode, 0)
        self.q.write_text("".join(l + "\n" for l in self.q.read_text(encoding="utf-8").splitlines()
                                  if not l.startswith("| Q-0006 ")), encoding="utf-8")
        before = snapshot(self.root)
        self.assert_nothing_changed(before, self.reopen("Q-0001", reason=SECRET, date=D6), 1,
                                    "queue.md and the logbook disagree")

    def test_a_reopen_changes_no_rule_and_no_answer(self):
        rules_before = (self.root / "rules.yaml").read_bytes()
        c1 = self.u("check", YES, "--no-log", "--json")
        self.assertEqual(self.reopen("Q-0001").returncode, 0)
        self.assertEqual((self.root / "rules.yaml").read_bytes(), rules_before)
        c2 = self.u("check", YES, "--no-log", "--json")
        self.assertEqual((c1.returncode, c1.stdout), (c2.returncode, c2.stdout))


class AgainTests(ReopenCase):
    """13.R4.5 (already reopened) and 13.R4.8 (reopened again, the chain of reopens followed by hash)."""

    def test_a_second_reopen_while_the_first_row_is_open_is_refused(self):
        self.assertEqual(self.reopen("Q-0001").returncode, 0)
        h = self.hash_of("umwayi queue answer", "Q-0001 ")
        before = snapshot(self.root)
        for target in ("Q-0001", h):
            with self.subTest(target=target):
                self.assert_nothing_changed(before, self.reopen(target, reason=SECRET, date=D6), 1,
                                            "already reopened as Q-0006, which is still open")
        r = self.reopen(h, reason=SECRET, date=D6)
        self.assertNotIn("the name is taken", r.stdout + r.stderr)  # no revisit text in an error

    def test_after_the_reopen_row_is_answered_the_next_reopen_links_its_answer(self):
        self.assertEqual(self.reopen("Q-0001").returncode, 0)
        first = self.entries()[-1]
        a = self.u("queue", "answer", "Q-0006", "--answer", "Keep it", "--revisit-if", "a rival appears",
                   "--date", D6)
        self.assertEqual(a.returncode, 0, a.stderr)
        h2 = self.hash_of("umwayi queue answer", "Q-0006 ")
        for target in ("Q-0001", "Q-0006"):
            with self.subTest(target=target):
                before_q = self.q.read_text(encoding="utf-8")
                before_log = self.log.read_bytes()
                r = self.reopen(target, date=D7)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                e = self.entries()[-1]
                self.assertEqual(e["added"], f"Reopen of entry {h2} (Q-0006 answered on {D6}); new decision Q-0007 "
                                             "opened by Owner; reason: New facts came in")
                self.assertTrue(e["checked"].endswith("revisit if recorded then: a rival appears"))
                self.assertIn("| Q-0007 | decision | Reopen decision Q-0006 | open |", self.q.read_text("utf-8"))
                # the chain of reopens, by hash, from the newest entry back to the first
                hops, link = [], e
                while link is not None:
                    target_hash = re.match(r"Reopen of entry ([0-9a-f]{64}) ", link["added"]).group(1)
                    [old] = [b for b in self.entries() if b["chain"] == target_hash]
                    hops.append(old["added"].split(" ")[0])
                    rid = old["added"].split(" ")[0]
                    opener = [b for b in self.entries() if b["source"] == REOPEN_SOURCE
                              and f"; new decision {rid} opened by " in b["added"]]
                    link = opener[0] if opener else None
                self.assertEqual(hops, ["Q-0006", "Q-0001"])
                self.assertEqual(first["added"].split(" ")[3], self.hash_of("umwayi queue answer", "Q-0001 "))
                # put the root back for the next target
                self.q.write_text(before_q, encoding="utf-8")
                self.log.write_bytes(before_log)
                self.rerecord()

    def test_a_reopen_of_the_reopen_row_while_it_is_open_is_refused(self):
        self.assertEqual(self.reopen("Q-0001").returncode, 0)
        before = snapshot(self.root)
        self.assert_nothing_changed(before, self.reopen("Q-0006", reason=SECRET, date=D6), 1, "Q-0006 is open")

    def test_after_the_reopen_row_is_closed_without_an_answer(self):
        self.assertEqual(self.reopen("Q-0001").returncode, 0)
        self.assertEqual(self.u("queue", "close", "Q-0006", "--date", D6).returncode, 0)
        h = self.hash_of("umwayi queue close", "Q-0006 ")
        r = self.reopen("Q-0001", date=D7)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        e = self.entries()[-1]
        self.assertTrue(e["added"].startswith(f"Reopen of entry {h} (Q-0006 closed on {D6}); new decision Q-0007 "))
        self.assertTrue(e["checked"].endswith("revisit if recorded then: not recorded, closed without an answer"))


# ============================================================ --revisit-if (13.R5)


class RevisitTests(ReopenCase):
    def test_a_decision_needs_revisit_if(self):
        before = snapshot(self.root)
        r = self.u("queue", "answer", "Q-0004", "--answer", "Yes", "--date", D4)
        self.assert_nothing_changed(before, r, 64, "--revisit-if")
        self.assertIn("| Q-0004 | decision | Open one | open |", self.row("Q-0004"))

    def test_a_task_refuses_revisit_if(self):
        self.assertEqual(self.u("queue", "add", "--kind", "task", "Another", "--date", D4).returncode, 0)
        before = snapshot(self.root)
        for value in ("none", "when it rains"):
            with self.subTest(value=value):
                r = self.u("queue", "answer", "Q-0006", "--answer", "done", "--revisit-if", value, "--date", D4)
                self.assert_nothing_changed(before, r, 64, "--revisit-if is only for a decision")

    def test_none_is_accepted_and_written_to_the_answer_entry(self):
        added = [b["added"] for b in self.entries() if b["source"] == "umwayi queue answer"]
        self.assertIn("Q-0005 marked answered on 2026-11-03 (status open to answered, 3 characters of answer); "
                      "revisit if: none", added)
        self.assertIn("Q-0001 marked answered on 2026-11-03 (status open to answered, 10 characters of answer); "
                      "revisit if: the name is taken", added)
        self.assertIn("Q-0002 marked answered on 2026-11-03 (status open to answered, 4 characters of answer)", added)

    def test_the_revisit_text_is_not_written_to_queue_md(self):
        self.assertNotIn("the name is taken", self.q.read_text(encoding="utf-8"))
        r = self.u("queue", "list")
        self.assertNotIn("the name is taken", r.stdout)

    def test_bad_revisit_values_are_usage_errors(self):
        before = snapshot(self.root)
        for bad in ("x" * 201, "a|b", "two\nlines", "", "   ", "tab\there"):
            with self.subTest(value=bad[:20]):
                r = self.u("queue", "answer", "Q-0004", "--answer", "Yes", "--revisit-if", bad, "--date", D4)
                self.assert_nothing_changed(before, r, 64)
        r = self.u("queue", "answer", "Q-0004", "--answer", "Yes", "--revisit-if", "y" * 200, "--date", D4)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.entries()[-1]["added"].endswith("; revisit if: " + "y" * 200))

    def test_a_row_that_is_not_open_is_still_refused_as_before(self):
        before = snapshot(self.root)
        r = self.u("queue", "answer", "Q-0001", "--answer", "again", "--date", D4)
        self.assert_nothing_changed(before, r, 1, "only an open row can be answered")

    def test_close_of_an_open_decision_needs_no_revisit_text(self):
        r = self.u("queue", "close", "Q-0004", "--date", D4)
        self.assertEqual(r.returncode, 0, r.stderr)

    def hand_answer(self, added):
        """Q-0004 answered as the code before layer 13 did: the row by hand, the entry in the old shape."""
        text = self.q.read_text(encoding="utf-8").replace("| Q-0004 | decision | Open one | open |  |  |  |",
                                                          "| Q-0004 | decision | Open one | answered |  | Yes | 2026-11-04 |")
        self.q.write_text(text, encoding="utf-8")
        logbook.append(self.root, logbook.Entry(
            D4, "umwayi queue answer", added, "queue.md parsed with no errors (5 rows); Q-0004 exists and was open",
            "No other row was changed. The answer text is stored in queue.md and not copied here."))

    def test_an_answer_from_before_layer_13_reads_not_recorded(self):
        self.hand_answer("Q-0004 marked answered on 2026-11-04 (status open to answered, 3 characters of answer)")
        r = self.reopen("Q-0004")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.entries()[-1]["checked"].endswith("revisit if recorded then: not recorded before layer 13"))
        self.assertIn("Revisit if recorded then: not recorded before layer 13", r.stdout)

    def test_revisit_text_in_another_shape_is_not_read(self):
        self.hand_answer("Q-0004 marked answered on 2026-11-04 (status open to answered); revisit if: forged words")
        r = self.reopen("Q-0004")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.entries()[-1]["checked"].endswith("revisit if recorded then: not recorded before layer 13"))
        self.assertNotIn("forged words", r.stdout)


# ============================================================ arguments, crashes and two at once


class ArgumentTests(ReopenCase):
    def test_bad_reason_name_or_date_is_a_usage_error_and_changes_nothing(self):
        before = snapshot(self.root)
        cases = [dict(reason="a|b"), dict(reason="two\nlines"), dict(reason="x" * 301), dict(reason=""),
                 dict(reason="   "), dict(by=""), dict(by="N" * 41), dict(by="a;b"), dict(by="a|b"),
                 dict(by="two\nlines"), dict(date="2026-13-01"), dict(date="tomorrow")]
        for case in cases:
            with self.subTest(**{k: v[:20] for k, v in case.items()}):
                self.assert_nothing_changed(before, self.reopen("Q-0001", **case), 64)

    def test_missing_arguments_are_usage_errors(self):
        before = snapshot(self.root)
        for argv in (["decision"], ["decision", "reopen"], ["decision", "reopen", "Q-0001", "--by", "Owner"],
                     ["decision", "reopen", "Q-0001", "--reason", "r"], ["decision", "nope"]):
            with self.subTest(argv=argv):
                self.assert_nothing_changed(before, self.u(*argv), 64)

    def test_a_date_before_the_last_entry_is_refused_and_queue_md_is_put_back(self):
        before = snapshot(self.root)
        self.assert_nothing_changed(before, self.reopen("Q-0001", reason=SECRET, date=D2), 1, "Dates never go backwards")

    def test_the_help_text_has_no_em_dash(self):
        for argv in (["decision", "--help"], ["decision", "reopen", "--help"], ["queue", "answer", "--help"]):
            r = self.u(*argv)
            self.assertEqual(r.returncode, 0)
            self.assertNotIn(EM_DASH, r.stdout)
        self.assertIn("--revisit-if", self.u("queue", "answer", "--help").stdout)


class CrashTests(ReopenCase):
    def test_a_crash_in_the_queue_commit_puts_queue_md_back_and_exits_2(self):
        before = snapshot(self.root)
        r = self.reopen("Q-0001", fault="umwayi.logbook:append:crash")
        self.assert_nothing_changed(before, r, 2, "stopped by an unexpected error (RuntimeError)")

    def test_a_failed_logbook_write_in_the_commit_puts_queue_md_back_and_exits_1(self):
        before = snapshot(self.root)
        r = self.reopen("Q-0001", fault="umwayi.logbook:append:error_after", extra={"UMWAYI_FAULT_AFTER": "0"})
        self.assert_nothing_changed(before, r, 1, "the queue change was undone")

    def test_a_crash_while_reading_exits_2_and_changes_nothing(self):
        before = snapshot(self.root)
        for target in ("umwayi.logbook:read_chained", "umwayi.taskqueue:parse", "umwayi.taskqueue:add_with_entry"):
            with self.subTest(target=target):
                self.assert_nothing_changed(before, self.reopen("Q-0001", fault=f"{target}:crash"), 2,
                                            "stopped by an unexpected error")

    def test_a_crash_in_queue_answer_with_revisit_if_puts_queue_md_back(self):
        before = snapshot(self.root)
        r = self.u("queue", "answer", "Q-0004", "--answer", "Yes", "--revisit-if", "none", "--date", D4,
                   fault="umwayi.logbook:append:crash")
        self.assert_nothing_changed(before, r, 2)

    def test_two_reopens_at_once_open_one_row(self):
        """Both pass the argument checks; the reopen lock lets one at a time read, check and write. The pause
        holds the first between its checks and its commit."""
        env = self.env("umwayi.taskqueue:add_with_entry:pause", {"UMWAYI_FAULT_PAUSE": "1.5"})
        argv = [sys.executable, "-m", "umwayi", "--root", str(self.root), "decision", "reopen", "Q-0001",
                "--reason", "at once", "--by", "Owner", "--date", D5]
        procs = [subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
                                  cwd=str(self.tmp)) for _ in range(2)]
        results = []
        for p in procs:
            out, err = p.communicate(timeout=120)
            results.append((p.returncode, out, err))
        self.assertEqual(sorted(c for c, _, _ in results), [0, 1], results)
        [(_, _, err)] = [x for x in results if x[0] == 1]
        self.assertIn("already reopened as Q-0006", err)
        self.assertEqual(len([b for b in self.entries() if b["source"] == REOPEN_SOURCE]), 1)
        self.assertEqual(len([r for r in self.rows() if "Reopen decision" in r]), 1)
        self.assertEqual(self.u("logbook", "verify").returncode, 0)


# ============================================================ logbook.read_chained


class ReadChainedTests(ReopenCase):
    """In process: the reader itself, with the same checks and errors as read_checked."""

    def test_it_returns_every_entry_with_its_chain_value(self):
        pairs = logbook.read_chained(self.root)
        self.assertEqual([e for e, _c in pairs], logbook.read_checked(self.root))
        self.assertEqual([c for _e, c in pairs], [b["chain"] for b in self.entries()])
        self.assertEqual([c is None for _e, c in pairs][:5], [True] * 4 + [False])  # four entries before the seal
        self.assertTrue(all(_HEX.fullmatch(c) for _e, c in pairs[4:]))

    def test_no_logbook_gives_an_empty_list(self):
        empty = self.tmp / "none"
        empty.mkdir()
        self.assertEqual(logbook.read_chained(empty), [])

    def test_it_refuses_what_read_checked_refuses_with_the_same_message(self):
        good = self.log.read_bytes()
        plants = [
            ("edit", lambda: self.log.write_bytes(good.replace(b"as open: Open one", b"as open: Open two"))),
            ("chain", lambda: (self.log.write_bytes(good.replace(b"Q-0002 marked answered", b"Q-0002 marked ANSWERED")),
                               self.rerecord())),
            ("format", lambda: (self.log.write_bytes(good[:-30]), self.rerecord())),
            ("record", lambda: self.rec.write_text("bad\n")),
        ]
        for name, plant in plants:
            with self.subTest(plant=name):
                self.log.write_bytes(good)
                self.rerecord()
                plant()
                before = snapshot(self.root)
                with self.assertRaises(UmwayiError) as a:
                    logbook.read_checked(self.root)
                with self.assertRaises(UmwayiError) as b:
                    logbook.read_chained(self.root)
                self.assertEqual(str(a.exception), str(b.exception))
                self.assertEqual(snapshot(self.root), before)


# ============================================================ the adapters' example rules (13.R14.3)


class AdapterGuardTests(unittest.TestCase):
    """The example rules of the three adapters refuse an AI helper's shell command that runs umwayi decision."""

    CASES = [
        ("claude_code", {"type": "tool_bash", "platform": "claude-code", "tool": "Bash"}, "command",
         "cc-no-guard-shell"),
        ("kiro", {"type": "tool_execute_bash", "platform": "kiro", "tool": "execute_bash"}, "input_command",
         "kiro-no-guard-shell"),
        ("stdio", {"type": "tool_bash", "platform": "stdio", "tool": "bash"}, "input_command",
         "stdio-no-owner-commands"),
    ]

    def test_a_helper_cannot_run_umwayi_decision(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            for adapter, action, field, rule in self.CASES:
                for command in ("umwayi decision reopen Q-0001 --reason x --by me",
                                "python -m umwayi --root . decision reopen Q-0001 --reason x --by me"):
                    with self.subTest(adapter=adapter, command=command[:30]):
                        r = subprocess.run(
                            [sys.executable, "-m", "umwayi", "--root", tmp, "check", json.dumps({**action, field: command}),
                             "--rules", str(REPO / "adapters" / adapter / "rules.example.yaml"), "--no-log", "--json"],
                            capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=str(REPO), HOME=tmp))
                        data = json.loads(r.stdout)
                        self.assertEqual((r.returncode, data["answer"], data["rule_id"]), (2, "No", rule))


# ============================================================ code guards


class CodeGuardTests(unittest.TestCase):
    SRC = REPO / "umwayi" / "decisions.py"
    ALLOWED = {"__future__", "errno", "os", "re", "time", "contextlib", "dataclasses", "pathlib", "fcntl",
               "umwayi", "umwayi.errors", "umwayi.logbook", "umwayi.taskqueue"}

    def imports(self):
        names = set()
        for node in ast.walk(ast.parse(self.SRC.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                names.add(node.module or "")
                if node.module == "umwayi":
                    names |= {f"umwayi.{a.name}" for a in node.names}
        return names

    def test_decisions_imports_only_the_standard_library_the_logbook_and_the_queue(self):
        self.assertLessEqual(self.imports(), self.ALLOWED)
        for later in ("umwayi.rulelog", "umwayi.petition", "umwayi.autonomy", "umwayi.rules", "subprocess",
                      "socket", "urllib", "http"):
            self.assertNotIn(later, self.imports())

    def test_decisions_has_no_code_path_that_writes_a_file_itself(self):
        src = self.SRC.read_text(encoding="utf-8")
        for word in ("write_bytes", "write_text", "truncate", "atomic_write", "unlink", "logbook.append",
                     "_commit", "os.write", "pwrite", "rename", "O_WRONLY", "O_APPEND", "O_TRUNC", "mkdir"):
            self.assertNotIn(word, src, f"decisions.py uses {word}")
        self.assertIsNone(re.search(r"(?<![.\w])open\(", src), "decisions.py opens a file with open()")
        self.assertEqual(src.count("os.open("), 1)  # the reopen lock, opened read and write, never written
        self.assertIn("taskqueue.add_with_entry(", src)  # its one write: the queue commit

    def test_no_em_dash_in_the_new_code(self):
        for p in (self.SRC, REPO / "umwayi" / "taskqueue.py", REPO / "umwayi" / "logbook.py", REPO / "umwayi" / "cli.py"):
            self.assertNotIn(EM_DASH, p.read_text(encoding="utf-8"), p.name)


if __name__ == "__main__":
    unittest.main()
