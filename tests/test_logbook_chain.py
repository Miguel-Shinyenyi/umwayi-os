"""Layer 5 addendum: the logbook hash chain (tasks.md C.1 to C.4, requirements "Logbook hash chain").

Every test runs `python -m umwayi ...` as a real child process, with HOME in a temporary folder. The chain is
computed again here, independently of umwayi/logbook.py, from the rule in the requirements:

    Chain = sha256(previous Chain value + "\n" + entry text).hexdigest()

where the entry text is the lines from `## DATE` through `- Not done: ...`, each followed by a newline, and the
previous value of the first chained entry is the SHA-256 of the whole file before that entry.

Tamper cases that only the chain can find also rewrite `.umwayi/logbook.sha256`, as a writer who can write
both files would; without that, the whole-file hash (Layer 5) finds them first.
"""

import hashlib
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.adapters.support import SITECUSTOMIZE
from tests.helpers import entry_text, write_sealed_logbook

REPO = Path(__file__).resolve().parent.parent
SECRET = "TOPSECRETCHAINTEXT"
OLD = "# Logbook\n" + entry_text(date="2026-01-01", added="old one") + entry_text(date="2026-01-02", added="old two")
YES = '{"type": "read_memory"}'  # the repo's starter rules say Yes
DAY = "2026-11-16"
_HEX = re.compile(r"[0-9a-f]{64}")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def chain(prev: str, text: str) -> str:
    return sha((prev + "\n" + text).encode("utf-8"))


def entries_of(text: str) -> list:
    """(heading index, entry text, Chain value or None) for each entry, by the rule above (not by umwayi)."""
    lines = text.split("\n")
    out = []
    for h, line in enumerate(lines):
        if line.startswith("## "):
            body = "".join(x + "\n" for x in lines[h:h + 6])
            c = lines[h + 6][len("- Chain: "):] if h + 6 < len(lines) and lines[h + 6].startswith("- Chain: ") else None
            out.append((h, body, c))
    return out


def rechain(text: str) -> str:
    """Every Chain value computed again, as a writer who rewrites the whole chain consistently would."""
    lines = text.split("\n")
    prev = None
    for h, body, c in entries_of(text):
        if c is None:
            continue
        if prev is None:
            prev = sha("".join(x + "\n" for x in lines[:h - 1]).encode("utf-8"))
        new = chain(prev, body)
        lines[h + 6] = "- Chain: " + new
        prev = new
    return "\n".join(lines)


class ChainCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="umwayi-chain-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(os.path.realpath(self._tmp.name))
        self.root = self.tmp / "root"
        self.root.mkdir()
        self.home = self.tmp / "home"
        self.home.mkdir()
        shutil.copy(REPO / "rules.yaml", self.root / "rules.yaml")
        self.log = self.root / "LOGBOOK.md"
        self.rec = self.root / ".umwayi" / "logbook.sha256"
        self.site = self.tmp / "site"
        self.site.mkdir()
        (self.site / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")

    def env(self, fault=None):
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "UMWAYI_FAULT", "HOME")}
        env["HOME"] = str(self.home)
        env["PYTHONPATH"] = os.pathsep.join([str(self.site), str(REPO)])
        if fault:
            env["UMWAYI_FAULT"] = fault
        return env

    def u(self, *args, fault=None):
        return subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), *args], capture_output=True,
                              text=True, timeout=120, env=self.env(fault), cwd=str(self.tmp))

    def check(self):
        return self.u("check", YES, "--date", DAY)

    def chained(self, appends=3):
        """Two old unchained entries, the chain started by seal --chain, then `appends` chained entries."""
        write_sealed_logbook(self.root, OLD)
        r = self.u("logbook", "seal", "--chain", "--by", "Owner", "--date", DAY)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for _ in range(appends):
            self.assertEqual(self.check().returncode, 0)
        return self.log.read_text(encoding="utf-8")

    def rerecord(self):
        """Write the whole-file hash record for the file as it is now (a writer who can write both files)."""
        self.rec.write_text(sha(self.log.read_bytes()) + "\n", encoding="ascii")

    def tamper(self, new_text):
        self.log.write_text(new_text, encoding="utf-8")
        self.rerecord()

    def verify(self, *extra):
        return self.u("logbook", "verify", *extra)

    def anchor(self):
        r = self.u("logbook", "anchor")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout.splitlines()[0]


# ===================================================================== C.1 the Chain line and the start


class StartTests(ChainCase):
    def test_seal_chain_starts_the_chain_from_the_hash_of_the_file_before_it(self):
        write_sealed_logbook(self.root, OLD)
        before = self.log.read_bytes()
        r = self.u("logbook", "seal", "--chain", "--by", "Owner", "--date", DAY)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        after = self.log.read_bytes()
        self.assertTrue(after.startswith(before), "an earlier byte was changed")
        block = after[len(before):].decode("utf-8")
        self.assertTrue(block.startswith("\n## 2026-11-16\n\n- Source: umwayi logbook seal\n"), block)
        lines = block[1:].split("\n")
        self.assertTrue(lines[2].startswith("- Added: Seal by Owner: the hash chain was started with 2 earlier "
                                            f"entries; its SHA-256 before this entry was {sha(before)}"), lines[2])
        text = "".join(x + "\n" for x in lines[:6])
        self.assertEqual(lines[6], "- Chain: " + chain(sha(before), text))
        self.assertEqual(lines[7:], [""])
        self.assertEqual(self.verify().returncode, 0)

    def test_seal_chain_is_allowed_once(self):
        self.chained(appends=0)
        before = self.log.read_bytes()
        r = self.u("logbook", "seal", "--chain", "--by", "Owner", "--date", DAY)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("the hash chain is already started", r.stderr)
        self.assertEqual(self.log.read_bytes(), before)
        r = self.u("logbook", "seal", "--by", "Owner", "--date", DAY)
        self.assertIn("already sealed and intact", r.stderr)

    def test_a_plain_seal_of_an_unsealed_logbook_starts_the_chain(self):
        self.log.write_text(OLD, encoding="utf-8")  # no record
        r = self.u("logbook", "seal", "--by", "Owner", "--date", DAY)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        [*_, (h, body, c)] = entries_of(self.log.read_text(encoding="utf-8"))
        self.assertEqual(c, chain(sha(OLD.encode("utf-8")), body))
        self.assertEqual(self.verify().returncode, 0)

    def test_every_entry_after_the_start_is_chained_to_the_one_before(self):
        text = self.chained(appends=4)
        found = entries_of(text)
        self.assertEqual([c is None for _, _, c in found], [True, True, False, False, False, False, False])
        lines = text.split("\n")
        prev = sha("".join(x + "\n" for x in lines[:found[2][0] - 1]).encode("utf-8"))
        for _, body, c in found[2:]:
            self.assertEqual(c, chain(prev, body))
            prev = c
        r = self.verify()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("info: the hash chain is intact: 5 chained entries", r.stdout)

    def test_until_the_chain_is_started_entries_stay_unchained(self):
        for _ in range(2):
            self.assertEqual(self.check().returncode, 0)
        self.assertNotIn("- Chain: ", self.log.read_text(encoding="utf-8"))
        r = self.verify()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("info: the hash chain is not started", r.stdout)
        self.assertNotEqual(self.u("logbook", "anchor").returncode, 0)


# ===================================================================== C.2 a broken chain refuses every write


class BrokenChainTests(ChainCase):
    def refused_everywhere(self, line_fragment):
        """verify finds it (exit 1), every append is refused and nothing changes, no logbook text is printed."""
        before = (self.log.read_bytes(), self.rec.read_bytes())
        r = self.verify()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(line_fragment, r.stdout)
        self.assertNotIn(SECRET, r.stdout + r.stderr)
        for h in _HEX.findall(r.stdout):
            self.assertNotIn(h, self.log.read_text(encoding="utf-8"), "verify printed a Chain value")
        c = self.check()
        self.assertEqual(c.returncode, 3, c.stdout + c.stderr)  # Yes becomes Ask me first: nothing was logged
        self.assertIn("the hash chain is broken at entry", c.stdout)
        self.assertNotIn(SECRET, c.stdout + c.stderr)
        r = self.u("logbook", "seal", "--by", "Owner", "--date", DAY)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("the hash chain is broken", r.stderr)
        self.assertEqual(self.u("logbook", "anchor").returncode, 2)
        self.assertEqual((self.log.read_bytes(), self.rec.read_bytes()), before, "a refusal changed something")
        r = self.u("kill", "on", "--reason", "x")  # the kill switch still works
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.root / ".umwayi" / "KILL").exists())

    def test_an_edit_in_an_old_chained_entry(self):
        text = self.chained()
        found = entries_of(text)
        h = found[3][0]  # the first chained entry after the seal
        lines = text.split("\n")
        lines[h + 3] = lines[h + 3] + " " + SECRET
        self.tamper("\n".join(lines))
        self.refused_everywhere(f"problem: entry 4 (line {h + 7}): the Chain value does not match")

    def test_an_edit_in_the_newest_entry(self):
        text = self.chained()
        h = entries_of(text)[-1][0]
        lines = text.split("\n")
        lines[h + 3] = "- Added: " + SECRET
        self.tamper("\n".join(lines))
        self.refused_everywhere(f"problem: entry 6 (line {h + 7}): the Chain value does not match")

    def test_an_edit_in_an_unchained_entry_before_the_start_breaks_the_genesis(self):
        text = self.chained()
        self.tamper(text.replace("old one", "old " + SECRET, 1))
        self.refused_everywhere("problem: entry 3 (line")

    def test_a_deleted_entry(self):
        text = self.chained()
        found = entries_of(text)
        lines = text.split("\n")
        h, nxt = found[3][0], found[4][0]
        del lines[h:nxt]
        self.tamper("\n".join(lines))
        self.refused_everywhere(f"problem: entry 4 (line {h + 7}): the Chain value does not match")

    def test_a_reordered_pair(self):
        text = self.chained()
        found = entries_of(text)
        lines = text.split("\n")
        a, b, end = found[3][0], found[4][0], found[5][0]
        lines[a:end] = lines[b:end] + lines[a:b]
        self.tamper("\n".join(lines))
        self.refused_everywhere("problem: entry 4 (line")

    def test_a_missing_chain_line_after_the_start(self):
        text = self.chained()
        h = entries_of(text)[4][0]
        lines = text.split("\n")
        del lines[h + 6]
        self.tamper("\n".join(lines))
        self.refused_everywhere(f"problem: entry 5 (line {h + 1}): the entry has no Chain line but comes after the "
                                "start of the chain")

    def test_a_chain_line_on_an_entry_before_the_start(self):
        write_sealed_logbook(self.root, OLD)
        lines = OLD.split("\n")
        h = entries_of(OLD)[1][0]
        lines.insert(h + 6, "- Chain: " + "a" * 64)
        self.tamper("\n".join(lines))
        r = self.verify()
        self.assertEqual(r.returncode, 1)
        self.assertIn(f"problem: entry 2 (line {h + 1}): an entry before the start of the chain has a Chain line",
                      r.stdout)
        self.assertEqual(self.check().returncode, 3)

    def test_a_malformed_chain_line_is_a_format_problem(self):
        text = self.chained()
        h = entries_of(text)[-1][0]
        lines = text.split("\n")
        lines[h + 6] = "- Chain: NOT-HEX"
        self.tamper("\n".join(lines))
        r = self.verify()
        self.assertEqual(r.returncode, 1)
        self.assertIn(f"problem: line {h + 7}: the Chain field is not 64 lowercase hex characters", r.stdout)
        self.assertEqual(self.check().returncode, 3)

    def test_a_truncated_tail_is_found_by_the_hash_record_or_by_an_anchor(self):
        text = self.chained()
        mark = self.anchor()
        h = entries_of(text)[-1][0]
        cut = "\n".join(text.split("\n")[:h - 1]) + "\n"
        self.log.write_text(cut, encoding="utf-8")  # the record is not rewritten: the whole-file hash finds it
        self.assertEqual(self.verify().returncode, 1)
        self.assertEqual(self.check().returncode, 3)
        self.rerecord()  # rewritten too: the chain is consistent and only the anchor can tell
        self.assertEqual(self.verify().returncode, 0)
        r = self.verify("--anchor", mark)
        self.assertEqual(r.returncode, 1)
        self.assertIn("problem: anchor: the chain is shorter than the anchor (3 of 4 chained entries)", r.stdout)


# ===================================================================== C.3 anchor and verify --anchor


class AnchorTests(ChainCase):
    def test_anchor_prints_count_and_the_newest_value_and_writes_nothing(self):
        text = self.chained(appends=2)
        before = {p: p.read_bytes() for p in (self.log, self.rec)}
        r = self.u("logbook", "anchor")
        self.assertEqual(r.returncode, 0, r.stderr)
        first, *rest = r.stdout.splitlines()
        self.assertEqual(first, f"3:{entries_of(text)[-1][2]}")
        self.assertIn("hub repository", " ".join(rest))
        self.assertIn("Kiro Notion page", " ".join(rest))
        self.assertEqual({p: p.read_bytes() for p in (self.log, self.rec)}, before)
        self.assertFalse((self.root / ".umwayi" / "logbook.pending").exists())

    def test_verify_against_a_good_anchor_and_an_old_one(self):
        self.chained(appends=1)
        old = self.anchor()
        self.assertEqual(self.check().returncode, 0)
        new = self.anchor()
        for mark in (old, new):
            with self.subTest(anchor=mark):
                r = self.verify("--anchor", mark)
                self.assertEqual(r.returncode, 0, r.stdout)

    def test_a_whole_chain_rewritten_consistently_passes_plain_verify_but_not_the_anchor(self):
        text = self.chained()
        mark = self.anchor()
        self.tamper(rechain(text.replace("old one", "old " + SECRET, 1)))
        self.assertEqual(self.verify().returncode, 0, "the consistent rewrite should pass plain verify")
        r = self.verify("--anchor", mark)
        self.assertEqual(r.returncode, 1)
        self.assertIn(f"problem: anchor: the chain differs from the anchor at chained entry {mark.split(':')[0]}",
                      r.stdout)
        self.assertNotIn(SECRET, r.stdout)

    def test_an_anchor_beyond_the_chain_is_shorter(self):
        self.chained(appends=0)
        count, value = self.anchor().split(":")
        r = self.verify("--anchor", f"{int(count) + 1}:{value}")
        self.assertEqual(r.returncode, 1)
        self.assertIn("the chain is shorter than the anchor", r.stdout)

    def test_a_malformed_anchor_is_a_usage_error(self):
        self.chained(appends=0)
        for bad in ("abc", "1", "0:" + "a" * 64, "-1:" + "a" * 64, "1:" + "A" * 64, "1:" + "a" * 63,
                    "1:" + "a" * 65, "1:" + "a" * 64 + "\n", "01:" + "a" * 64):
            with self.subTest(anchor=repr(bad)):
                self.assertEqual(self.verify("--anchor", bad).returncode, 64)

    def test_anchor_refuses_a_logbook_that_does_not_verify_or_has_no_chain(self):
        write_sealed_logbook(self.root, OLD)
        r = self.u("logbook", "anchor")
        self.assertEqual(r.returncode, 2)
        self.assertIn("the hash chain is not started", r.stderr)
        self.u("logbook", "seal", "--chain", "--by", "Owner", "--date", DAY)
        self.log.write_text(self.log.read_text(encoding="utf-8") + "stray\n", encoding="utf-8")
        r = self.u("logbook", "anchor")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(r.stdout, "")


# ===================================================================== crash safety still holds with the chain


class CrashSafetyTests(ChainCase):
    def test_a_chained_write_killed_after_its_append_is_recovered_with_a_chained_entry(self):
        self.chained(appends=1)
        size = self.log.stat().st_size
        pending = self.root / ".umwayi" / "logbook.pending"
        p = subprocess.Popen([sys.executable, "-m", "umwayi", "--root", str(self.root), "check", YES, "--date", DAY],
                             env=self.env("umwayi.logbook:_record_hash:hang"), cwd=str(self.tmp),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: p.poll() is None and p.kill())
        end = time.monotonic() + 60
        while not (pending.exists() and self.log.stat().st_size > size):
            self.assertIsNone(p.poll(), "umwayi check exited before its append")
            self.assertLess(time.monotonic(), end, "the held write was not seen")
            time.sleep(0.01)
        self.assertIn(b"\n- Chain: ", pending.read_bytes(), "the intent does not cover the Chain line")
        os.kill(p.pid, signal.SIGKILL)
        p.wait(timeout=30)
        self.assertEqual(self.check().returncode, 0)
        r = self.verify()
        self.assertEqual(r.returncode, 0, r.stdout)
        found = entries_of(self.log.read_text(encoding="utf-8"))
        self.assertTrue(all(c for _, _, c in found[2:]), "an entry after the start has no Chain line")
        self.assertIn("Source: umwayi logbook recover", self.log.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
