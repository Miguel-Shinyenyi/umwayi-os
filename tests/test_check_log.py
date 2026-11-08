import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import entry_text, write_sealed_logbook
from umwayi import logbook
from umwayi.cli import main
from umwayi.logbook import parse

REPO = Path(__file__).resolve().parent.parent

RULES = """
rules:
  - id: no-money
    title: Never move money
    text: Helpers never move money.
    verdict: no
    matchers:
      type: [payment, transfer]
  - id: ok-read
    title: Reads are fine
    text: Reading is fine.
    verdict: yes
    matchers:
      type: read
  - id: ask-email
    title: Email needs me
    text: Ask first.
    verdict: ask
    matchers:
      type: send
"""
SECRET = "sk-live-TOPSECRETTOKEN-12345"


class CheckLogBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "rules.yaml").write_text(RULES, encoding="utf-8")
        self.log = self.root / "LOGBOOK.md"
        p = mock.patch.object(logbook, "LOCK_WAIT_SECONDS", 0)
        p.start()
        self.addCleanup(p.stop)

    def check(self, action, *extra, clock="2026-11-07", stdin=None):
        out, err = io.StringIO(), io.StringIO()
        old_err, old_in = sys.stderr, sys.stdin
        sys.stderr = err
        if stdin is not None:
            sys.stdin = io.StringIO(stdin)
        try:
            with mock.patch("umwayi.cli._today", return_value=clock):
                argv = ["--root", str(self.root), "check", *([action] if action is not None else []), *extra]
                code = main(argv, out=out)
        finally:
            sys.stderr, sys.stdin = old_err, old_in
        return code, out.getvalue(), err.getvalue()

    def entries(self):
        return parse(self.log.read_text(encoding="utf-8"))[0]

    def snap(self):
        return {os.path.relpath(os.path.join(dp, f), self.root): Path(dp, f).read_bytes()
                for dp, _d, fs in os.walk(self.root) for f in fs}


class LoggingTests(CheckLogBase):
    def test_one_exact_entry_per_check(self):
        code, out, _ = self.check('{"type": "payment", "amount": 5}')
        self.assertEqual(code, 2)
        self.assertTrue(out.startswith("No\n"))
        self.assertEqual(
            self.log.read_text(encoding="utf-8"),
            "# Logbook\n\n## 2026-11-07\n\n- Source: umwayi check\n"
            "- Added: Rule no-money gave No; action type: payment\n"
            "- Checked: action read as a JSON object without duplicate keys: yes; rules.yaml loaded: yes (3 rules); "
            "rules matched: no-money\n"
            "- Not done: The action was not run. The action JSON was not stored in the logbook.\n",
        )
        self.assertEqual(logbook.verify(self.root).problems, [])

    def test_each_answer_is_logged(self):
        for action, answer, rule in [
            ('{"type": "read"}', "Yes", "ok-read"),
            ('{"type": "payment"}', "No", "no-money"),
            ('{"type": "send"}', "Ask me first", "ask-email"),
            ('{"type": "dance"}', "Ask me first", None),
        ]:
            with self.subTest(action=action):
                self.check(action)
                last = self.entries()[-1].entry
                self.assertIn(f"gave {answer}", last.added)
                self.assertIn(f"Rule {rule} gave" if rule else "No rule gave", last.added)
        self.assertEqual(len(self.entries()), 4)

    def test_every_check_adds_exactly_one_entry_and_keeps_earlier_bytes(self):
        seen = b""
        for n in range(5):
            self.check('{"type": "read"}')
            now = self.log.read_bytes()
            self.assertTrue(now.startswith(seen))
            self.assertEqual(len(self.entries()), n + 1)
            seen = now

    def test_broken_inputs_are_logged_too(self):
        self.check("not json")
        self.check('{"type": "read"}', "--rules", str(self.root / "nope.yaml"))
        self.check(None)
        e = [p.entry for p in self.entries()]
        self.assertEqual(len(e), 3)
        self.assertIn("JSON object without duplicate keys: no; rules.yaml loaded: no", e[0].checked)
        self.assertIn("action type not recorded", e[0].added)
        self.assertIn("JSON object without duplicate keys: yes; rules.yaml loaded: no", e[1].checked)
        self.assertIn("action type: read", e[1].added)
        self.assertIn("gave Ask me first", e[2].added)

    def test_action_json_is_never_written(self):
        action = json.dumps({"type": "payment", "api_key": SECRET, "note": "hello " + SECRET,
                             "nested": {"password": SECRET}, "items": [SECRET]})
        self.check(action)
        text = self.log.read_text(encoding="utf-8")
        self.assertNotIn(SECRET, text)
        self.assertNotIn("api_key", text)
        self.assertNotIn("password", text)
        self.assertNotIn("hello", text)

    def test_only_a_short_plain_type_is_recorded(self):
        cases = [
            ({"type": "payment"}, "action type: payment"),
            ({"type": "git.push:main-1_x"}, "action type: git.push:main-1_x"),
            ({"type": "x" * 40}, "action type: " + "x" * 40),
            ({"type": "x" * 41}, "action type not recorded"),
            ({"type": ""}, "action type not recorded"),
            ({"type": "has space"}, "action type not recorded"),
            ({"type": "a/b"}, "action type not recorded"),
            ({"type": "caf\u00e9"}, "action type not recorded"),
            ({"type": SECRET + " extra words"}, "action type not recorded"),
            ({"type": ["payment"]}, "action type not recorded"),
            ({"type": {"a": 1}}, "action type not recorded"),
            ({"type": 5}, "action type not recorded"),
            ({"type": None}, "action type not recorded"),
            ({"kind": "payment"}, "action type not recorded"),
        ]
        for action, expected in cases:
            with self.subTest(action=str(action)[:40]):
                if self.log.exists():
                    self.log.unlink()
                    import shutil
                    shutil.rmtree(self.root / ".umwayi")
                self.check(json.dumps(action))
                self.assertIn(expected, self.entries()[-1].entry.added)
                self.assertNotIn(SECRET, self.log.read_text(encoding="utf-8"))

    def test_explicit_date_beats_clock(self):
        self.check('{"type": "read"}', "--date", "2027-02-03", clock="2026-11-07")
        self.assertEqual(self.entries()[0].entry.date, "2027-02-03")

    def test_stdin_action_is_logged_without_its_content(self):
        code, _, _ = self.check("-", stdin=json.dumps({"type": "payment", "secret": SECRET}))
        self.assertEqual(code, 2)
        self.assertNotIn(SECRET, self.log.read_text(encoding="utf-8"))

    def test_json_output_says_logged(self):
        code, out, _ = self.check('{"type": "read"}', "--json")
        data = json.loads(out)
        self.assertEqual((code, data["answer"], data["logged"]), (0, "Yes", True))

    def test_text_output_is_unchanged_when_logging(self):
        _, out, _ = self.check('{"type": "read"}')
        self.assertEqual(out, "Yes\nRule: ok-read\nReason: Reading is fine.\n")


class FailingLogbookTests(CheckLogBase):
    """If the logbook cannot be written: No stays No (exit 2), Yes and Ask me first become Ask me first (exit 3)."""

    def setup_cases(self):
        def tampered():
            write_sealed_logbook(self.root, "# Logbook\n" + entry_text(date="2026-01-01"))
            self.log.write_text(self.log.read_text().replace("- Added: x", "- Added: EDITED"), encoding="utf-8")

        def unsealed():
            self.log.write_text("# Logbook\n" + entry_text(date="2026-01-01"), encoding="utf-8")

        def deleted():
            write_sealed_logbook(self.root, "# Logbook\n" + entry_text(date="2026-01-01"))
            self.log.unlink()

        def locked():
            (self.root / ".umwayi").mkdir(exist_ok=True)
            (self.root / ".umwayi" / "logbook.lock").write_text("1\n")

        def directory():
            self.log.mkdir()

        def malformed():
            write_sealed_logbook(self.root, "# Logbook\nstray\n")

        def future_entries():
            write_sealed_logbook(self.root, "# Logbook\n" + entry_text(date="2030-01-01"))

        return {
            "hand edit of an earlier line": (tampered, "does not match its recorded hash"),
            "no hash record": (unsealed, "no hash record"),
            "logbook deleted": (deleted, "may have been deleted"),
            "lock held": (locked, "another umwayi command"),
            "logbook is a folder": (directory, "cannot be read"),
            "format problem": (malformed, "format problem"),
            "date goes backwards": (future_entries, "before the date of the last entry"),
        }

    def reset(self):
        import shutil
        shutil.rmtree(self.root / ".umwayi", ignore_errors=True)
        if self.log.is_dir():
            self.log.rmdir()
        elif self.log.exists():
            self.log.unlink()

    def test_yes_and_ask_become_ask_me_first_for_every_failure(self):
        for case, (setup, fragment) in self.setup_cases().items():
            for action in ('{"type": "read"}', '{"type": "send"}', '{"type": "dance"}'):
                with self.subTest(case=case, action=action):
                    self.reset()
                    setup()
                    before = self.snap()
                    code, out, _ = self.check(action)
                    self.assertEqual(code, 3)
                    self.assertEqual(out.splitlines()[0], "Ask me first")
                    self.assertIn("Rule: (none)", out)
                    self.assertIn("The logbook could not be written", out)
                    self.assertIn(fragment, out)
                    self.assertIn("Nothing was logged", out)
                    self.assertEqual(self.snap(), before)

    def test_no_stays_no_for_every_failure(self):
        for case, (setup, fragment) in self.setup_cases().items():
            with self.subTest(case=case):
                self.reset()
                setup()
                before = self.snap()
                code, out, _ = self.check('{"type": "payment"}')
                self.assertEqual(code, 2)
                self.assertEqual(out.splitlines()[0], "No")
                self.assertIn("Rule: no-money", out)
                self.assertIn("Helpers never move money.", out)
                self.assertIn("The logbook could not be written", out)
                self.assertIn(fragment, out)
                self.assertIn("Nothing was logged", out)
                self.assertEqual(self.snap(), before)

    def test_json_output_and_exit_code_when_the_logbook_fails(self):
        write_sealed_logbook(self.root, "# Logbook\n" + entry_text(date="2026-01-01"))
        self.log.write_text("changed", encoding="utf-8")
        code, out, _ = self.check('{"type": "payment"}', "--json")
        data = json.loads(out)
        self.assertEqual((code, data["answer"], data["rule_id"], data["logged"]), (2, "No", "no-money", False))
        code, out, _ = self.check('{"type": "read"}', "--json")
        data = json.loads(out)
        self.assertEqual((code, data["answer"], data["rule_id"], data["logged"]), (3, "Ask me first", None, False))

    def test_unexpected_error_in_the_logbook(self):
        with mock.patch("umwayi.rules.logbook.append", side_effect=RuntimeError("boom " + SECRET)):
            code, out, _ = self.check('{"type": "read"}')
            self.assertEqual(code, 3)
            self.assertIn("an unexpected error", out)
            self.assertNotIn(SECRET, out)
            code, out, _ = self.check('{"type": "payment"}')
            self.assertEqual(code, 2)
            self.assertNotIn(SECRET, out)

    def test_bad_date_for_the_entry_is_ask_me_first(self):
        # a clock that returns nonsense must not turn into Yes or No
        code, out, _ = self.check('{"type": "read"}', clock="not-a-date")
        self.assertEqual(code, 3)
        self.assertIn("Ask me first", out)

    def test_works_again_after_the_owner_seals(self):
        self.log.write_text("# Logbook\n" + entry_text(date="2026-01-01"), encoding="utf-8")
        self.assertEqual(self.check('{"type": "read"}')[0], 3)
        logbook.seal(self.root, "2026-11-07", "owner")
        self.assertEqual(self.check('{"type": "read"}')[0], 0)

    def test_real_process_exit_codes_when_the_logbook_is_tampered(self):
        write_sealed_logbook(self.root, "# Logbook\n" + entry_text(date="2026-01-01"))
        self.log.write_text("changed", encoding="utf-8")
        env = dict(os.environ, PYTHONPATH=str(REPO))

        def run(action):
            return subprocess.run(
                [sys.executable, "-m", "umwayi", "--root", str(self.root), "check", action],
                capture_output=True, text=True, env=env, cwd=self.root,
            )
        r = run('{"type": "payment"}')
        self.assertEqual(r.returncode, 2)
        self.assertTrue(r.stdout.startswith("No\n"))
        r = run('{"type": "read"}')
        self.assertEqual(r.returncode, 3)
        self.assertTrue(r.stdout.startswith("Ask me first"))


class NoLogTests(CheckLogBase):
    def test_dry_run_writes_nothing_and_says_so(self):
        for action, code in [('{"type": "read"}', 0), ('{"type": "payment"}', 2), ('{"type": "dance"}', 3)]:
            with self.subTest(action=action):
                c, out, _ = self.check(action, "--no-log")
                self.assertEqual(c, code)
                self.assertTrue(out.rstrip().endswith("Nothing was logged (--no-log, dry run)."))
        self.assertFalse(self.log.exists())
        self.assertFalse((self.root / ".umwayi").exists())

    def test_dry_run_still_works_when_the_logbook_is_tampered(self):
        write_sealed_logbook(self.root, "# Logbook\n" + entry_text(date="2026-01-01"))
        self.log.write_text("changed", encoding="utf-8")
        before = self.snap()
        code, out, _ = self.check('{"type": "payment"}', "--no-log")
        self.assertEqual(code, 2)
        self.assertEqual(self.snap(), before)

    def test_dry_run_json(self):
        code, out, _ = self.check('{"type": "read"}', "--no-log", "--json")
        data = json.loads(out)
        self.assertEqual((code, data["answer"], data["logged"]), (0, "Yes", False))
        self.assertFalse(self.log.exists())

    def test_the_default_is_to_log(self):
        self.check('{"type": "read"}')
        self.assertTrue(self.log.exists())


if __name__ == "__main__":
    unittest.main()
