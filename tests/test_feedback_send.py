"""W29: `umwayi feedback send`, the opt-in feedback bundle, written to a file after a typed yes and sent by hand.

A real logbook is built in a temporary root with the real commands, dated with today's UTC date (never a fixed day). The
command is called in process with a fake terminal and a fake answer, and once as a real child process in a pseudo
terminal (and once without one). Planted tokens, emails, home paths, the tester's home folder, the root path and the
user name must never reach the screen, the file or the logbook. Standard library only.
"""
import getpass
import hashlib
import io
import json
import os
import re
import select
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from umwayi import feedback, feedbacksend, kill, logbook
from umwayi.cli import main

REPO = Path(__file__).resolve().parents[1]
TODAY = datetime.now(timezone.utc).date().isoformat()
SECRETS = {
    "openai key": "sk-proj-W29abcDEF1234567890xyzSECRET",
    "anthropic key": "sk-ant-api03-W29abcdefghijklmnopqrstuv",
    "github token": "ghp_W29abcdefghijklmnopqrstuvwxyz0123",
    "github pat": "github_pat_11W29ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "aws key id": "AKIAW29ABCDEFGHIJKLM",
    "slack token": "xoxb-1234567890-W29abcdefghij",
    "umwayi serve token": "umt1_W29aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "google key": "AIzaW29abcdefghijklmnopqrstuvwxyz012345",
    "a long random word": "Q29tcGxleFczOVNlY3JldEtleVZhbHVlMTIzNDU2Nzg",
}
EMAIL = "tester.w29@example.com"
PATHS = ["/Users/w29tester/projects/x.py", "/home/w29tester/.config/umwayi", "~/secret/w29notes.txt",
         "C:\\Users\\w29tester\\Desktop\\a.txt"]
NOTE = ("I ran the quickstart and the check said Ask me first, as I expected. "
        f"My key is {SECRETS['openai key']} and password=hunter2W29 and Authorization: Bearer abcdefghW29xyz123456 "
        f"and mail me at {EMAIL}. The file was {PATHS[0]} and {PATHS[1]}.")


def run_main(root, *argv, today=TODAY, tty=True, answer="yes", home=None):
    out, err = io.StringIO(), io.StringIO()
    asked = []

    def ask(prompt):
        asked.append(prompt)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    old = sys.stderr
    sys.stderr = err
    try:
        with mock.patch("umwayi.cli._today", return_value=today), \
                mock.patch("umwayi.feedbacksend._terminal", return_value=tty), \
                mock.patch("umwayi.feedbacksend._ask", side_effect=ask), \
                mock.patch.dict(os.environ, {"HOME": str(home)} if home else {}):
            code = main(["--root", str(root), *argv], out=out)
    finally:
        sys.stderr = old
    return code, out.getvalue(), err.getvalue(), asked


def tree(root):
    out = {}
    for p in sorted(Path(root).rglob("*")):
        rel = p.relative_to(root).as_posix()
        out[rel] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "dir"
    return out


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="umwayi-fbsend-")
        self.addCleanup(tmp.cleanup)
        self.home = Path(os.path.realpath(tmp.name)) / "home-w29tester"
        self.home.mkdir()
        self.root = self.home / "work-w29root"
        self.root.mkdir()
        (self.root / "umwayi.json").write_text(json.dumps({"memory_dir": "memory", "private_paths": []}))
        (self.root / "rules.yaml").write_text("rules:\n  - id: r-yes\n    title: t\n    text: x\n    verdict: yes\n"
                                              "    matchers:\n      type: read_memory\n")
        run_main(self.root, "check", '{"type": "read_memory"}')
        run_main(self.root, "check", '{"type": "something_else"}')

    def send(self, *extra, **kw):
        kw.setdefault("home", self.home)
        return run_main(self.root, "feedback", "send", *extra, **kw)

    def bundles(self):
        d = self.root / ".umwayi" / "feedback"
        return sorted(d.glob("*.txt")) if d.is_dir() else []

    def entries(self):
        return logbook.read_checked(self.root)


class FilterTests(unittest.TestCase):
    def test_every_planted_token_is_hidden(self):
        for name, secret in SECRETS.items():
            out, n = feedback.redact(f"before {secret} after")
            self.assertNotIn(secret, out, name)
            self.assertIn("[hidden secret]", out, name)
            self.assertTrue(out.startswith("before ") and out.endswith(" after"), (name, out))
            self.assertGreaterEqual(n, 1)

    def test_a_secret_after_a_key_word_bearer_and_a_url_with_a_password_are_hidden(self):
        for text, gone in (("password=hunter2W29", "hunter2W29"), ("api_key: abcW29xyz", "abcW29xyz"),
                           ("TOKEN = zzW29zz", "zzW29zz"), ("Authorization: Bearer abcdefghW29xyz123456", "abcdefghW29xyz123456"),
                           ("https://bob:pa55W29@example.com/x", "pa55W29"), ("secret:topW29", "topW29")):
            out, _ = feedback.redact(text)
            self.assertNotIn(gone, out, text)

    def test_a_private_key_block_line_is_hidden_whole(self):
        out, _ = feedback.redact("-----BEGIN OPENSSH PRIVATE KEY-----")
        self.assertEqual(out, "[hidden secret]")

    def test_emails_are_hidden(self):
        for e in (EMAIL, "a@b.co", "First.Last+tag@sub.example.org"):
            out, _ = feedback.redact(f"write to {e}, thanks")
            self.assertEqual(out, "write to [hidden email], thanks", e)

    def test_home_paths_on_mac_linux_and_windows_are_hidden(self):
        for p in PATHS:
            out, _ = feedback.redact(f"look at {p} please")
            self.assertEqual(out, "look at [hidden path] please", p)
        out, _ = feedback.redact("in /root/x and /Users and /home/")
        self.assertNotIn("/root/x", out)

    def test_the_tester_s_own_home_root_and_user_name_are_hidden(self):
        home, root = "/srv/people/qq-w29", "/data/qq-w29work"
        out, _ = feedback.redact(f"ran in {root}/sub from {home}/x as qqw29user", home=home, root=root, user="qqw29user")
        self.assertNotIn("qq-w29", out)
        self.assertNotIn("qqw29user", out)

    def test_ordinary_words_numbers_dates_and_the_export_lines_are_kept_as_they_are(self):
        lines = ["umwayi feedback export: counts and dates only; no paths, commands, rules or file contents.",
                 "entries: 12", "  umwayi check: 4", "dates: first 2026-11-14, last 2026-11-15",
                 "chain: intact, 7 entries in the chain", "budget spent: 30 UU (an open reservation counts in full)",
                 "Version 0.1.0 on Python 3.12.4, exit code 3, it took 2 min.", "I typed umwayi agent check helper."]
        for line in lines:
            self.assertEqual(feedback.redact(line), (line, 0), line)

    def test_control_characters_are_made_spaces(self):
        self.assertEqual(feedback.redact("a\x1b[31mred\x07b")[0], "a [31mred b")


class RefusalTests(Base):
    def assertNothing(self, before, entries):
        self.assertEqual(tree(self.root), before)
        self.assertEqual(len(self.entries()), entries)
        self.assertEqual(self.bundles(), [])

    def test_without_a_terminal_it_is_refused_with_exit_2_and_nothing_written(self):
        before, n = tree(self.root), len(self.entries())
        code, out, err, asked = self.send("--note", NOTE, tty=False)
        self.assertEqual(code, 2)
        self.assertIn("needs a real terminal", err)
        self.assertEqual(asked, [])
        self.assertNothing(before, n)

    def test_the_kill_switch_on_or_unknown_blocks_it(self):
        kill.turn_on(self.root, TODAY, "test")
        before, n = tree(self.root), len(self.entries())
        code, out, err, asked = self.send("--note", "hello")
        self.assertEqual((code, asked), (2, []))
        self.assertIn("kill switch", err)
        self.assertNothing(before, n)
        with mock.patch("umwayi.feedbacksend.kill.state", return_value="unknown"):
            code, *_ = self.send("--note", "hello")
        self.assertEqual(code, 2)

    def test_a_hand_edited_logbook_is_refused_with_no_bundle(self):
        p = self.root / "LOGBOOK.md"
        p.write_text(p.read_text(encoding="utf-8").replace("gave Yes", "gave No", 1), encoding="utf-8")
        before = tree(self.root)
        code, out, err, asked = self.send("--note", "hello")
        self.assertEqual((code, asked), (2, []))
        self.assertIn("no summary was made", err)
        self.assertEqual(tree(self.root), before)

    def test_every_answer_but_yes_writes_nothing_and_is_exit_0(self):
        before, n = tree(self.root), len(self.entries())
        for answer in ("no", "", "YES", "y", "yes please", " no ", EOFError(), KeyboardInterrupt()):
            code, out, err, asked = self.send("--note", "hello", answer=answer)
            self.assertEqual(code, 0, repr(answer))
            self.assertEqual(len(asked), 1)
            self.assertIn("Nothing was written and nothing was sent.", out)
        self.assertNothing(before, n)

    def test_usage_errors_are_64_before_anything_is_shown(self):
        (self.root / "taken.txt").write_text("x")
        big = self.root.parent / "big.txt"
        big.write_text("x" * (feedbacksend.MAX_NOTE_BYTES + 1))
        for argv in (("--note", "a", "--note-file", str(big)), ("--note-file", str(big)),
                     ("--note-file", str(self.root.parent / "missing.txt")), ("--out", str(self.root / "taken.txt")),
                     ("--out", str(self.root / "no-such-folder" / "f.txt")), ("--out", str(self.root / "f.json")),
                     ("extra",)):
            code, out, err, asked = self.send(*argv)
            self.assertEqual((code, asked), (64, []), argv)

    def test_the_exit_code_is_never_1_or_3(self):
        codes = {self.send("--note", "a", tty=False)[0], self.send("--note", "a", answer="no")[0],
                 self.send("--note", "a", answer="yes")[0], self.send("--bogus")[0]}
        self.assertEqual(codes, {0, 2, 64})


class YesTests(Base):
    def test_yes_writes_exactly_what_was_shown_and_logs_only_its_hash(self):
        n = len(self.entries())
        code, out, err, asked = self.send("--note", NOTE)
        self.assertEqual(code, 0, err)
        [path] = self.bundles()
        data = path.read_bytes()
        shown = out.split(feedbacksend.SHOW_BEGIN + "\n", 1)[1].split("\n" + feedbacksend.SHOW_END, 1)[0] + "\n"
        self.assertEqual(data.decode("utf-8"), shown)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertIn(str(path), out)
        self.assertIn("Nothing was sent", out)
        self.assertIn("by hand", out)
        new = self.entries()[n:]
        self.assertEqual([e.source for e in new], ["umwayi feedback send"])
        digest = hashlib.sha256(data).hexdigest()
        self.assertIn(f"feedback_send: ", new[0].added)
        self.assertIn(digest, new[0].added)
        book = (self.root / "LOGBOOK.md").read_text(encoding="utf-8")
        for word in ("quickstart", path.name, str(self.root), "hunter2W29"):
            self.assertNotIn(word, book.split("umwayi feedback send", 1)[1], word)

    def test_the_bundle_holds_the_export_the_versions_and_the_note_and_no_secret(self):
        self.send("--note", NOTE)
        text = self.bundles()[0].read_text(encoding="utf-8")
        self.assertTrue(text.startswith("umwayi feedback bundle, version 1\n"))
        self.assertIn("entries by kind:", text)
        self.assertIn("  umwayi check: 2", text)
        self.assertIn(f"python: {sys.version.split()[0]}", text)
        self.assertIn("I ran the quickstart and the check said Ask me first", text)
        self.assertTrue(text.endswith("end of the bundle\n"))
        for word in [*SECRETS.values(), EMAIL, "w29tester", "hunter2W29", "abcdefghW29xyz123456", str(self.home),
                     str(self.root), "home-w29tester", "work-w29root"]:
            self.assertNotIn(word, text, word)

    def test_nothing_secret_reaches_the_screen_or_the_logbook_either(self):
        code, out, err, asked = self.send("--note", NOTE)
        book = (self.root / "LOGBOOK.md").read_text(encoding="utf-8")
        shown = out.split(feedbacksend.SHOW_BEGIN, 1)[1]
        for word in [*SECRETS.values(), EMAIL, "hunter2W29", "abcdefghW29xyz123456"]:
            self.assertNotIn(word, out + err + "".join(asked) + book, word)
        self.assertNotIn(str(self.home), shown.split(feedbacksend.SHOW_END)[0])
        self.assertRegex(out, r"\d+ things were hidden")

    def test_a_note_file_is_read_and_filtered_and_no_note_is_allowed(self):
        f = self.root.parent / "note.txt"
        f.write_text(f"line one\nline two with {SECRETS['github token']}\n", encoding="utf-8")
        self.assertEqual(self.send("--note-file", str(f))[0], 0)
        text = self.bundles()[0].read_text(encoding="utf-8")
        self.assertIn("line one\nline two with [hidden secret]\n", text)
        code, *_ = self.send()
        self.assertEqual(code, 0)
        texts = [p.read_text(encoding="utf-8") for p in self.bundles()]
        self.assertEqual(len(texts), 2)
        self.assertEqual(sum("(no note)" in x for x in texts), 1)

    def test_a_chosen_out_file_is_written_and_never_overwritten(self):
        out_path = self.root.parent / "my-feedback.txt"
        self.assertEqual(self.send("--note", "hello", "--out", str(out_path))[0], 0)
        first = out_path.read_bytes()
        code, *_ = self.send("--note", "again", "--out", str(out_path))
        self.assertEqual(code, 64)
        self.assertEqual(out_path.read_bytes(), first)

    def test_an_entry_that_cannot_be_written_takes_the_file_back_and_is_exit_2(self):
        with mock.patch("umwayi.feedbacksend.logbook.append", side_effect=logbook.UmwayiError("x")):
            code, out, err, asked = self.send("--note", "hello")
        self.assertEqual(code, 2)
        self.assertEqual(self.bundles(), [])
        self.assertIn("Nothing was written and nothing was sent.", err)

    def test_the_export_counts_the_new_kind(self):
        self.send("--note", "hello")
        code, out, *_ = run_main(self.root, "feedback", "export")
        self.assertEqual(code, 0)
        self.assertIn("  umwayi feedback send: 1\n", out)

    def test_the_module_sends_nothing_over_a_network(self):
        text = (REPO / "umwayi" / "feedbacksend.py").read_text(encoding="utf-8") + (REPO / "umwayi" / "feedback.py").read_text(encoding="utf-8")
        for word in ("socket", "urllib", "http.client", "smtplib", "subprocess", "requests"):
            self.assertNotIn(word, text, word)
        self.assertNotIn("\u2014", text)


@unittest.skipUnless(hasattr(os, "openpty") and sys.platform != "win32", "needs a pseudo terminal")
class RealTerminalTests(Base):
    def child(self, *argv, typed=None, pty=True):
        env = {**os.environ, "PYTHONPATH": str(REPO), "HOME": str(self.home)}
        if not pty:
            return subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), *argv], input=typed or "",
                                  capture_output=True, text=True, env=env, timeout=60)
        master, slave = os.openpty()
        p = subprocess.Popen([sys.executable, "-m", "umwayi", "--root", str(self.root), *argv], stdin=slave, stdout=slave,
                             stderr=slave, env=env, close_fds=True)
        os.close(slave)
        buf, sent, end = b"", False, time.monotonic() + 60
        while time.monotonic() < end:
            r, _, _ = select.select([master], [], [], 0.5)
            if r:
                try:
                    chunk = os.read(master, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
                if not sent and b"Type yes" in buf:
                    os.write(master, (typed + "\n").encode())
                    sent = True
            elif p.poll() is not None:
                break
        p.wait(30)
        os.close(master)
        return p.returncode, buf.decode("utf-8", "replace")

    def test_a_typed_yes_in_a_real_terminal_writes_the_bundle(self):
        code, text = self.child("feedback", "send", "--note", NOTE, typed="yes")
        self.assertEqual(code, 0, text)
        self.assertEqual(len(self.bundles()), 1)
        for word in (SECRETS["openai key"], EMAIL, "hunter2W29"):
            self.assertNotIn(word, text)

    def test_a_typed_no_in_a_real_terminal_writes_nothing(self):
        code, text = self.child("feedback", "send", "--note", "hello", typed="no")
        self.assertEqual(code, 0, text)
        self.assertEqual(self.bundles(), [])

    def test_a_pipe_is_not_a_terminal_even_with_yes_on_it(self):
        r = self.child("feedback", "send", "--note", "hello", typed="yes\n", pty=False)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertEqual(self.bundles(), [])


if __name__ == "__main__":
    unittest.main()
