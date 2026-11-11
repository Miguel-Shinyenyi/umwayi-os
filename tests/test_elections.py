"""Layer 13, slice 1 (L13.1): elections. A Yes rule past its `review_by` falls back to Ask me first.

Written before the code (L13.1.1). Every case of the design's slice 1 test list, as real child processes
(`python -m umwayi ...`) in a temporary root, with HOME and XDG_CONFIG_HOME in the temporary folder. The system
clock of the child is set by a sitecustomize file (UMWAYI_TEST_TODAY), so no test depends on the real date.

Planted fault of the slice: a rule past its `review_by`. Mutation checks (counts in the pull request): the expiry
`<` for `<=`, the clock from `--date` only, the fallback not logged, and the others listed there.
"""

import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import entry_text, write_sealed_logbook

REPO = Path(__file__).resolve().parent.parent
SYSTEM = "2026-11-11"  # the system date of every child process, unless a test says otherwise

SITECUSTOMIZE = r'''
import os
t = os.environ.get("UMWAYI_TEST_TODAY")
if t:
    import umwayi.cli as _c
    import umwayi.rules as _r
    _c._today = lambda: t
    _r.system_today = lambda: t
crash = os.environ.get("UMWAYI_TEST_CRASH")
if crash:
    import importlib
    _m, _n = crash.split(":")
    _mod = importlib.import_module(_m)
    def _boom(*a, **k):
        raise RuntimeError("SENTINEL-CRASH-TEXT")
    setattr(_mod, _n, _boom)
'''

SENTINELS = ("SENTINEL-TITLE-QQ", "SENTINEL-TEXT-QQ", "SENTINEL-CAUSE-QQ")


def rule(rid, verdict="yes", review_by=None, type_="read", title=None, text=None, cause=None, matchers=None):
    lines = [
        f"  - id: {rid}",
        f"    title: {title or 'Title of ' + rid}",
        f"    text: {text or 'Text of ' + rid}",
    ]
    if cause:
        lines.append(f"    cause: {cause}")
    lines.append(f"    verdict: {verdict}")
    if review_by is not None:
        lines.append(f"    review_by: {review_by}")
    lines.append("    matchers:")
    lines.append(matchers or f"      type: {type_}")
    return "\n".join(lines) + "\n"


def rules_file(*rules):
    return "rules:\n" + "\n".join(rules)


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="umwayi-elections-")
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self.root = base / "root"
        self.root.mkdir()
        self.site = base / "site"
        self.site.mkdir()
        (self.site / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
        self.home = base / "home"
        self.home.mkdir()
        self.log = self.root / "LOGBOOK.md"

    def write_rules(self, *rules):
        (self.root / "rules.yaml").write_text(rules_file(*rules), encoding="utf-8")

    def u(self, *args, today=SYSTEM, extra_env=None, stdin=None):
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(self.site), str(REPO)]), HOME=str(self.home),
                   XDG_CONFIG_HOME=str(self.home / ".config"))
        env.pop("UMWAYI_TEST_TODAY", None)
        env.pop("UMWAYI_TEST_CRASH", None)
        if today:
            env["UMWAYI_TEST_TODAY"] = today
        env.update(extra_env or {})
        return subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), *args],
                              capture_output=True, text=True, env=env, cwd=self.root, timeout=60, input=stdin)

    def check(self, *extra, action='{"type": "read"}', today=SYSTEM):
        return self.u("check", action, *extra, today=today)

    def check_json(self, *extra, action='{"type": "read"}', today=SYSTEM):
        r = self.check("--json", *extra, action=action, today=today)
        self.assertEqual(r.stderr, "", r.stderr)
        return r.returncode, json.loads(r.stdout)

    def snapshot(self):
        out = {}
        for p in sorted(self.root.rglob("*")):
            out[p.relative_to(self.root).as_posix() + ("/" if p.is_dir() else "")] = (
                None if p.is_dir() else p.read_bytes())
        return out

    def logbook_text(self):
        return self.log.read_text(encoding="utf-8")

    def check_entries_text(self):
        """The logbook without its `umwayi rules` entries (L13.3, 13.R7.2: the first check logs the rules first).
        The check entries are compared byte for byte as before; the rules entry must be there, first."""
        text = self.logbook_text()
        blocks = text.split("\n\n## ")
        rest = [b for b in blocks[1:] if "\n\n- Source: umwayi rules\n" not in "\n" + b]
        self.assertTrue(len(blocks) > 1 and "- Source: umwayi rules\n" in blocks[1], "no rules entry first")
        return "\n\n## ".join([blocks[0]] + rest)


# ============================================================ the lapse, in `umwayi check`


class LapseTests(Base):
    def test_day_after_review_by_is_ask_me_first_and_logged(self):
        """The planted fault: a rule past its review_by. The day after, Ask me first, with the fallback in the entry."""
        self.write_rules(rule("report-yes", review_by="2026-11-20"))
        r = self.check("--date", "2026-11-21")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertTrue(r.stdout.startswith("Ask me first\nRule: report-yes\nReason: "), r.stdout)
        self.assertIn("review_by", r.stdout)
        self.assertEqual(
            self.check_entries_text(),
            "# Logbook\n\n## 2026-11-21\n\n- Source: umwayi check\n"
            "- Added: Rule report-yes gave Ask me first; action type: read\n"
            "- Checked: action read as a JSON object without duplicate keys: yes; rules.yaml loaded: yes (1 rules); "
            "rules matched: report-yes; election fallbacks: report-yes (review_by 2026-11-20)\n"
            "- Not done: The action was not run. The action JSON was not stored in the logbook.\n",
        )

    def test_last_day_is_still_in_force(self):
        self.write_rules(rule("report-yes", review_by="2026-11-20"))
        code, data = self.check_json("--date", "2026-11-20", today="2026-11-20")
        self.assertEqual((code, data["answer"], data["rule_id"]), (0, "Yes", "report-yes"))
        self.assertNotIn("election_fallbacks", data)
        self.assertNotIn("election", self.logbook_text())

    def test_the_system_date_alone_lapses_a_rule(self):
        self.write_rules(rule("report-yes", review_by="2026-11-20"))
        code, data = self.check_json("--date", "2026-11-21", today="2026-11-21")
        self.assertEqual((code, data["answer"]), (3, "Ask me first"))
        self.assertEqual(data["election_fallbacks"], ["report-yes"])

    def test_the_system_date_beats_an_earlier_date_option(self):
        """A past --date cannot bring a lapsed rule back (the clock is not from --date only)."""
        self.write_rules(rule("report-yes", review_by="2026-11-20"))
        code, data = self.check_json("--no-log", "--date", "2026-11-10", today="2026-11-25")
        self.assertEqual((code, data["answer"]), (3, "Ask me first"))
        self.assertEqual(data["election_fallbacks"], ["report-yes"])

    def test_a_later_date_option_beats_the_system_date(self):
        self.write_rules(rule("report-yes", review_by="2026-11-20"))
        code, data = self.check_json("--no-log", "--date", "2026-12-01", today="2026-11-11")
        self.assertEqual((code, data["answer"]), (3, "Ask me first"))

    def test_a_later_logbook_date_beats_both(self):
        """A clock set back cannot bring a lapsed rule back: the newest logbook date counts."""
        self.write_rules(rule("report-yes", review_by="2026-11-20"))
        write_sealed_logbook(self.root, "# Logbook\n" + entry_text("2026-11-25"))
        code, data = self.check_json("--no-log", "--date", "2026-11-12", today="2026-11-12")
        self.assertEqual((code, data["answer"]), (3, "Ask me first"))
        self.assertEqual(data["election_fallbacks"], ["report-yes"])

    def test_a_logbook_date_equal_to_review_by_is_still_in_force(self):
        self.write_rules(rule("report-yes", review_by="2026-11-25"))
        write_sealed_logbook(self.root, "# Logbook\n" + entry_text("2026-11-25"))
        code, data = self.check_json("--no-log", "--date", "2026-11-12", today="2026-11-12")
        self.assertEqual((code, data["answer"]), (0, "Yes"))

    def test_an_unreadable_logbook_uses_the_other_two_dates_and_never_gives_yes(self):
        self.write_rules(rule("report-yes", review_by="2026-11-20"), rule("other-yes", review_by="2027-01-01",
                                                                           type_="other"))
        write_sealed_logbook(self.root, "# Logbook\n" + entry_text("2026-11-25"))
        with open(self.log, "a", encoding="utf-8") as f:  # a hand edit: the hash record no longer matches
            f.write("tampered\n")
        code, data = self.check_json("--no-log", today="2026-11-30")
        self.assertEqual((code, data["answer"]), (3, "Ask me first"))
        self.assertEqual(data["election_fallbacks"], ["report-yes"])
        code, data = self.check_json("--date", "2026-11-12", action='{"type": "other"}', today="2026-11-12")
        self.assertEqual(code, 3, "a Yes without its logbook entry must not come out")
        self.assertNotEqual(data["answer"], "Yes")

    def test_the_rules_file_is_not_edited(self):
        self.write_rules(rule("report-yes", review_by="2026-11-20"))
        before = (self.root / "rules.yaml").read_bytes()
        self.check("--date", "2026-12-01")
        self.assertEqual((self.root / "rules.yaml").read_bytes(), before)

    def test_a_lapsed_yes_beside_a_fresh_yes_gives_ask_me_first(self):
        self.write_rules(rule("lapsed-yes", review_by="2026-11-01"), rule("fresh-yes", review_by="2027-01-01"),
                         rule("plain-yes"))
        code, data = self.check_json("--no-log")
        self.assertEqual((code, data["answer"], data["rule_id"]), (3, "Ask me first", "lapsed-yes"))
        self.assertEqual(data["election_fallbacks"], ["lapsed-yes"])
        self.assertEqual(data["matched"], ["lapsed-yes", "fresh-yes", "plain-yes"])

    def test_a_lapsed_yes_beside_a_no_gives_no(self):
        self.write_rules(rule("lapsed-yes", review_by="2026-11-01"), rule("a-no", verdict="no"))
        code, data = self.check_json("--no-log")
        self.assertEqual((code, data["answer"], data["rule_id"]), (2, "No", "a-no"))
        self.assertEqual(data["election_fallbacks"], ["lapsed-yes"])  # it did fall back, so it is named

    def test_a_lapsed_yes_beside_an_ask_rule_gives_ask_me_first(self):
        self.write_rules(rule("lapsed-yes", review_by="2026-11-01"), rule("an-ask", verdict="ask"))
        code, data = self.check_json("--no-log")
        self.assertEqual((code, data["answer"], data["rule_id"]), (3, "Ask me first", "lapsed-yes"))

    def test_a_lapsed_rule_that_does_not_match_is_not_named(self):
        self.write_rules(rule("lapsed-yes", review_by="2026-11-01", type_="other"), rule("fresh-yes"))
        code, data = self.check_json("--no-log")
        self.assertEqual((code, data["answer"]), (0, "Yes"))
        self.assertNotIn("election_fallbacks", data)

    def test_the_entry_names_every_rule_up_to_ten_then_counts_the_rest(self):
        self.write_rules(*[rule(f"lapsed-{i:02d}", review_by=f"2026-10-{i + 1:02d}") for i in range(12)])
        code, data = self.check_json("--date", "2026-11-12")
        self.assertEqual(code, 3)
        self.assertEqual(data["election_fallbacks"], [f"lapsed-{i:02d}" for i in range(12)])
        named = ", ".join(f"lapsed-{i:02d} (review_by 2026-10-{i + 1:02d})" for i in range(10))
        self.assertIn(f"; election fallbacks: {named}, and 2 more\n", self.logbook_text())

    def test_the_fallback_is_kept_when_the_logbook_cannot_be_written(self):
        self.write_rules(rule("lapsed-yes", review_by="2026-11-01"))
        write_sealed_logbook(self.root, "# Logbook\n" + entry_text("2026-11-10"))
        (self.root / "LOGBOOK.md").write_text("hand edited\n", encoding="utf-8")
        code, data = self.check_json()
        self.assertEqual((code, data["answer"], data["logged"]), (3, "Ask me first", False))
        self.assertEqual(data["election_fallbacks"], ["lapsed-yes"])

    def test_text_output_names_the_fallback_when_a_no_wins(self):
        self.write_rules(rule("lapsed-yes", review_by="2026-11-01"), rule("a-no", verdict="no"))
        r = self.check("--no-log")
        self.assertEqual(r.returncode, 2)
        self.assertIn("Election fallbacks: lapsed-yes (review_by 2026-11-01)\n", r.stdout)

    def test_the_kill_switch_stops_before_any_fallback_is_named(self):
        self.write_rules(rule("lapsed-yes", review_by="2026-11-01"))
        self.assertEqual(self.u("kill", "on", "--reason", "test").returncode, 0)
        code, data = self.check_json("--kill-switch")
        self.assertEqual((code, data["answer"], data["matched"]), (2, "No", []))
        self.assertNotIn("election_fallbacks", data)
        self.assertNotIn("election fallbacks", self.logbook_text())

    def test_the_reason_of_a_lapsed_rule_is_fixed_text_not_the_rule_text(self):
        self.write_rules(rule("lapsed-yes", review_by="2026-11-01", text="SENTINEL-TEXT-QQ", cause="SENTINEL-CAUSE-QQ"))
        r = self.check("--no-log")
        self.assertEqual(r.returncode, 3)
        self.assertNotIn("SENTINEL", r.stdout)


# ====================================================== a rules file with no review_by is unchanged

GOLDEN_RULES = """rules:
  - id: no-money
    title: Never move money
    text: Helpers never move money.
    verdict: no
    matchers:
      type: payment
  - id: ok-read
    title: Reads are fine
    text: Reading is fine.
    verdict: yes
    matchers:
      type: read
"""
GOLDEN_JSON = """{
  "answer": "Yes",
  "rule_id": "ok-read",
  "reason": "Reading is fine.",
  "matched": [
    "ok-read"
  ],
  "rules_ok": true,
  "action_ok": true,
  "logged": true,
  "kill_switch": "off"
}
"""
GOLDEN_TEXT_NO = "No\nRule: no-money\nReason: Helpers never move money.\n"
GOLDEN_LOGBOOK = """# Logbook

## 2026-11-07

- Source: umwayi check
- Added: Rule ok-read gave Yes; action type: read
- Checked: action read as a JSON object without duplicate keys: yes; rules.yaml loaded: yes (2 rules); rules matched: ok-read
- Not done: The action was not run. The action JSON was not stored in the logbook.

## 2026-11-07

- Source: umwayi check
- Added: Rule no-money gave No; action type: payment
- Checked: action read as a JSON object without duplicate keys: yes; rules.yaml loaded: yes (2 rules); rules matched: no-money
- Not done: The action was not run. The action JSON was not stored in the logbook.
"""


class GoldenTests(Base):
    def test_a_rules_file_with_no_review_by_gives_the_bytes_of_before(self):
        """Captured from main before layer 13 (a7ed8dc): the JSON, the text output and the logbook entries."""
        (self.root / "rules.yaml").write_text(GOLDEN_RULES, encoding="utf-8")
        r = self.u("check", "--json", "--date", "2026-11-07", '{"type":"read"}')
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, GOLDEN_JSON, ""))
        r = self.u("check", "--date", "2026-11-07", '{"type":"payment"}')
        self.assertEqual((r.returncode, r.stdout, r.stderr), (2, GOLDEN_TEXT_NO, ""))
        self.assertEqual(self.check_entries_text(), GOLDEN_LOGBOOK)

    def test_a_rule_with_a_date_that_has_not_passed_gives_the_same_bytes_as_without(self):
        (self.root / "rules.yaml").write_text(GOLDEN_RULES.replace(
            "    verdict: yes\n", "    verdict: yes\n    review_by: 2026-11-07\n"), encoding="utf-8")
        r = self.u("check", "--json", "--date", "2026-11-07", '{"type":"read"}', today="2026-11-07")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, GOLDEN_JSON, ""))
        first_entry = GOLDEN_LOGBOOK.split("\n## 2026-11-07\n\n- Source: umwayi check\n- Added: Rule no-money")[0]
        self.assertEqual(self.check_entries_text(), first_entry)


# ================================================================ a bad review_by is a malformed file


class ParseTests(Base):
    def malformed(self, rules_text):
        (self.root / "rules.yaml").write_text(rules_text, encoding="utf-8")
        code, data = self.check_json("--no-log")
        self.assertEqual(code, 3, rules_text)
        self.assertEqual((data["answer"], data["rules_ok"], data["matched"], data["rule_id"]),
                         ("Ask me first", False, [], None), rules_text)
        self.assertNotIn("election_fallbacks", data)

    def test_a_good_date_is_accepted_plain_or_quoted(self):
        for value in ("2026-12-01", '"2026-12-01"', "'2026-12-01'"):
            with self.subTest(value=value):
                self.write_rules(rule("report-yes", review_by=value))
                code, data = self.check_json("--no-log")
                self.assertEqual((code, data["rules_ok"], data["answer"]), (0, True, "Yes"))

    def test_each_bad_date_makes_the_rules_malformed(self):
        for value in ("2026-13-01", "2026-2-1", "tomorrow", "20261101", "[2026-12-01]", "[2026-12-01, 2026-12-02]",
                      "", "null", "true", "2026-02-30", "2026-12-01T00:00", "2026-12-001", "'2026-12-01 '",
                      "12/01/2026", '"2026-12-01\\n"'):
            with self.subTest(value=value):
                self.malformed(rules_file(rule("report-yes", review_by=value)))

    def test_a_no_rule_with_review_by_is_malformed(self):
        self.malformed(rules_file(rule("a-no", verdict="no", review_by="2026-12-01"), rule("ok-read")))

    def test_an_ask_rule_with_review_by_is_malformed_until_the_opt_in_exists(self):
        self.malformed(rules_file(rule("an-ask", verdict="ask", review_by="2026-12-01"), rule("ok-read")))

    def test_a_duplicate_review_by_key_is_malformed(self):
        text = rules_file(rule("report-yes", review_by="2026-12-01").replace(
            "    review_by: 2026-12-01\n", "    review_by: 2026-12-01\n    review_by: 2026-12-02\n"))
        self.malformed(text)

    def test_the_error_does_not_echo_the_rules_file(self):
        (self.root / "rules.yaml").write_text(rules_file(rule("a-no", verdict="no", review_by="SENTINEL-DATE-QQ")),
                                              encoding="utf-8")
        r = self.check("--no-log")
        self.assertEqual(r.returncode, 3)
        self.assertNotIn("SENTINEL-DATE-QQ", r.stdout + r.stderr)


# =============================================================== callers without a root fall back too


class BareCallerTests(Base):
    def setUp(self):
        super().setUp()
        (self.root / "jobs.yaml").write_text(
            "jobs:\n  - name: open-queue\n    command: queue-list\n    status: open\n    min_gap_days: 1\n",
            encoding="utf-8")
        self.u("queue", "add", "--kind", "task", "A task", "--date", "2026-11-01")
        self.write_rules(rule("run-yes", review_by="2026-11-20", type_="run_job",
                              matchers="      type: run_job\n      command: queue-list"))

    def test_a_job_does_not_run_past_the_review_by_of_its_rule(self):
        r = self.u("run", "jobs.yaml", "--job", "open-queue", "--date", "2026-11-21", today="2026-11-21")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("Ask me first", r.stdout)
        self.assertIn("did not run", r.stdout)

    def test_a_job_runs_on_the_last_day(self):
        r = self.u("run", "jobs.yaml", "--job", "open-queue", "--date", "2026-11-20", today="2026-11-20")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_job_with_a_past_date_option_does_not_revive_the_rule(self):
        """The bare check has no --date; it takes the system date, which a past --date cannot lower."""
        r = self.u("run", "jobs.yaml", "--job", "open-queue", "--date", "2026-11-10", today="2026-11-21")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)

    def test_an_ai_helper_stops_past_the_review_by_of_its_rule(self):
        self.write_rules(rule("read-queue-yes", review_by="2026-11-20", type_="read_queue"))
        r = self.u("steward", "--date", "2026-11-21", today="2026-11-21")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("Ask me first", r.stdout)
        self.assertFalse((self.root / "drafts").exists() and any((self.root / "drafts").iterdir()))

    def test_rules_check_takes_today_as_an_argument(self):
        sys.path.insert(0, str(REPO))
        try:
            from umwayi import rules
        finally:
            sys.path.pop(0)
        path = self.root / "rules.yaml"
        path.write_text(rules_file(rule("report-yes", review_by="2026-11-20")), encoding="utf-8")
        a = '{"type": "read"}'
        self.assertEqual(rules.check(a, path, today="2026-11-20").answer, rules.YES)
        d = rules.check(a, path, today="2026-11-21")
        self.assertEqual((d.answer, d.rule_id, d.lapsed), (rules.ASK, "report-yes", [("report-yes", "2026-11-20")]))
        self.assertEqual(rules.check(a, path, today="2026-11-21").to_dict()["election_fallbacks"], ["report-yes"])


# ================================================================================ umwayi rules due

DUE_RULES = (
    rule("report-yes", review_by="2026-11-01", title="SENTINEL-TITLE-QQ", text="SENTINEL-TEXT-QQ",
         cause="SENTINEL-CAUSE-QQ", type_="a")
    + rule("weekly-yes", review_by="2026-11-20", title="SENTINEL-TITLE-QQ", text="SENTINEL-TEXT-QQ", type_="b")
    + rule("old-yes", review_by="2030-01-01", type_="c")
    + rule("later-yes", review_by="2027-06-01", type_="d")  # past the window, and not far: not listed
    + rule("plain-one", type_="e")
    + rule("plain-two", type_="f")
    + rule("a-no", verdict="no", type_="g")
    + rule("an-ask", verdict="ask", type_="h")
)
DUE_OUTPUT = (
    "lapsed  2026-11-01  report-yes  10 days ago\n"
    "due     2026-11-20  weekly-yes  in 9 days\n"
    "far     2030-01-01  old-yes     in 1147 days\n"
    "Yes rules without review_by: 2\n"
)


class RulesDueTests(Base):
    def setUp(self):
        super().setUp()
        (self.root / "rules.yaml").write_text("rules:\n" + DUE_RULES, encoding="utf-8")

    def test_the_list_byte_for_byte_and_exit_3_when_a_rule_lapsed(self):
        r = self.u("rules", "due")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (3, DUE_OUTPUT, ""))

    def test_exit_0_when_no_rule_lapsed(self):
        r = self.u("rules", "due", today="2026-10-15")  # report-yes is 17 days away: outside the 14 day window
        self.assertEqual((r.returncode, r.stdout, r.stderr),
                         (0, "far     2030-01-01  old-yes  in 1174 days\nYes rules without review_by: 2\n", ""))

    def test_exit_0_output_byte_for_byte(self):
        (self.root / "rules.yaml").write_text(
            rules_file(rule("soon-yes", review_by="2026-11-25"), rule("plain-yes", type_="x")), encoding="utf-8")
        r = self.u("rules", "due")
        self.assertEqual((r.returncode, r.stdout, r.stderr),
                         (0, "due     2026-11-25  soon-yes  in 14 days\nYes rules without review_by: 1\n", ""))
        r = self.u("rules", "due", "--within", "13")
        self.assertEqual((r.returncode, r.stdout), (0, "Yes rules without review_by: 1\n"))

    def test_the_last_day_is_due_with_zero_days_not_lapsed(self):
        (self.root / "rules.yaml").write_text(rules_file(rule("today-yes", review_by=SYSTEM)), encoding="utf-8")
        r = self.u("rules", "due", "--within", "0")
        self.assertEqual((r.returncode, r.stdout), (0, f"due     {SYSTEM}  today-yes  in 0 days\nYes rules without review_by: 0\n"))
        r = self.u("rules", "due", today="2026-11-12")
        self.assertEqual((r.returncode, r.stdout), (3, f"lapsed  {SYSTEM}  today-yes  1 day ago\nYes rules without review_by: 0\n"))

    def test_the_far_limit_is_366_days(self):
        (self.root / "rules.yaml").write_text(
            rules_file(rule("edge-yes", review_by="2027-11-12", type_="a"), rule("far-yes", review_by="2027-11-13", type_="b")),
            encoding="utf-8")
        r = self.u("rules", "due", "--within", "3650")
        self.assertEqual(r.stdout, "due     2027-11-12  edge-yes  in 366 days\n"
                                   "far     2027-11-13  far-yes   in 367 days\n"
                                   "Yes rules without review_by: 0\n")
        r = self.u("rules", "due")  # a far date is listed even outside the window: it is a warning
        self.assertEqual(r.stdout, "far     2027-11-13  far-yes  in 367 days\nYes rules without review_by: 0\n")

    def test_within_moves_the_window(self):
        r = self.u("rules", "due", "--within", "8")
        self.assertNotIn("weekly-yes", r.stdout)
        r = self.u("rules", "due", "--within", "9")
        self.assertIn("weekly-yes", r.stdout)
        r = self.u("rules", "due", "--within", "3650")
        self.assertIn("later-yes", r.stdout)

    def test_the_order_is_oldest_first_then_by_id(self):
        (self.root / "rules.yaml").write_text(
            rules_file(rule("b-yes", review_by="2026-11-15", type_="a"), rule("a-yes", review_by="2026-11-15", type_="b"),
                       rule("c-yes", review_by="2026-10-01", type_="c")), encoding="utf-8")
        r = self.u("rules", "due")
        self.assertEqual([line.split()[2] for line in r.stdout.splitlines()[:3]], ["c-yes", "a-yes", "b-yes"])

    def test_the_date_option_and_a_past_date_option(self):
        r = self.u("rules", "due", "--date", "2026-12-01")
        self.assertEqual(r.returncode, 3)
        self.assertTrue(r.stdout.startswith("lapsed  2026-11-01  report-yes  30 days ago\nlapsed  2026-11-20  weekly-yes  11 days ago\n"),
                        r.stdout)
        r = self.u("rules", "due", "--date", "2026-10-01")  # earlier than the system date: no effect
        self.assertEqual(r.stdout, DUE_OUTPUT)

    def test_the_newest_logbook_date_counts(self):
        write_sealed_logbook(self.root, "# Logbook\n" + entry_text("2026-11-25"))
        r = self.u("rules", "due")
        self.assertEqual(r.returncode, 3)
        self.assertIn("lapsed  2026-11-20  weekly-yes  5 days ago\n", r.stdout)

    def test_a_broken_logbook_does_not_stop_the_list(self):
        write_sealed_logbook(self.root, "# Logbook\n" + entry_text("2026-11-25"))
        with open(self.log, "a", encoding="utf-8") as f:
            f.write("tampered\n")
        r = self.u("rules", "due")
        self.assertEqual((r.returncode, r.stdout), (3, DUE_OUTPUT))

    def test_it_changes_nothing(self):
        write_sealed_logbook(self.root, "# Logbook\n" + entry_text("2026-11-05"))
        (self.root / "queue.md").write_text("# Queue\n", encoding="utf-8")
        before = self.snapshot()
        for args in (("rules", "due"), ("rules", "due", "--within", "3650", "--date", "2026-12-01"),
                     ("rules", "due", "--within", "x")):
            self.u(*args)
            self.assertEqual(self.snapshot(), before, args)

    def test_it_changes_nothing_with_no_logbook(self):
        before = self.snapshot()
        self.u("rules", "due")
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.log.exists())
        self.assertFalse((self.root / ".umwayi").exists())

    def test_it_prints_no_title_text_or_cause(self):
        for args in (("rules", "due"), ("rules", "due", "--within", "3650"), ("rules", "due", "--date", "2030-01-01")):
            r = self.u(*args)
            for s in SENTINELS:
                self.assertNotIn(s, r.stdout + r.stderr, args)

    def test_missing_rules_give_ask_me_first_and_say_so(self):
        (self.root / "rules.yaml").unlink()
        r = self.u("rules", "due")
        self.assertEqual((r.returncode, r.stdout), (3, "Ask me first: rules.yaml is missing or broken, so umwayi cannot list the rules.\n"))
        self.assertEqual(r.stderr, "")

    def test_broken_rules_give_ask_me_first_and_echo_nothing(self):
        (self.root / "rules.yaml").write_text(
            rules_file(rule("a-no", verdict="no", review_by="SENTINEL-DATE-QQ", title="SENTINEL-TITLE-QQ")), encoding="utf-8")
        r = self.u("rules", "due")
        self.assertEqual((r.returncode, r.stdout), (3, "Ask me first: rules.yaml is missing or broken, so umwayi cannot list the rules.\n"))
        self.assertNotIn("SENTINEL", r.stdout + r.stderr)

    def test_a_bad_argument_is_64_and_writes_nothing(self):
        before = self.snapshot()
        for args in (["--within", "abc"], ["--within", "-1"], ["--within", "3651"], ["--within", "1.5"],
                     ["--within", ""], ["--within"], ["--date", "2026-13-01"], ["--date", "2026-2-1"],
                     ["--date"], ["--bogus"], ["extra"], ["--within", "5", "--within", "x"]):
            with self.subTest(args=args):
                r = self.u("rules", "due", *args)
                self.assertEqual(r.returncode, 64, r.stdout + r.stderr)
                self.assertEqual(r.stdout, "")
                self.assertEqual(self.snapshot(), before)

    def test_the_edges_of_within_are_accepted(self):
        for value in ("0", "3650"):
            self.assertIn(self.u("rules", "due", "--within", value).returncode, (0, 3), value)

    def test_rules_alone_is_a_usage_error(self):
        self.assertEqual(self.u("rules").returncode, 64)

    def test_it_never_exits_1_and_a_crash_exits_2(self):
        r = self.u("rules", "due", extra_env={"UMWAYI_TEST_CRASH": "umwayi.elections:due"})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn("SENTINEL-CRASH-TEXT", r.stdout + r.stderr)

    def test_a_rule_without_a_lapse_in_a_file_with_no_review_by_at_all(self):
        (self.root / "rules.yaml").write_text(GOLDEN_RULES, encoding="utf-8")
        r = self.u("rules", "due")
        self.assertEqual((r.returncode, r.stdout), (0, "Yes rules without review_by: 1\n"))

    def test_help_uses_the_product_words(self):
        r = self.u("rules", "due", "--help")
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("\u2014", r.stdout)


# ================================================================================ the code guard


class CodeGuardTests(unittest.TestCase):
    NETWORK = {"socket", "http", "urllib", "ssl", "smtplib", "ftplib", "xmlrpc", "requests", "asyncio", "telnetlib",
               "imaplib", "poplib", "socketserver"}
    LATER = {"decisions", "petition", "autonomy"}  # modules of slices 2 to 5 that rules.py must not import; rulelog
    # is slice 3's step 4 of the verdict order, which design.md puts inside rules.check

    def imports(self, path):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                names.add(("." * node.level) + (node.module or ""))
                names |= {f"{node.module}.{a.name}" for a in node.names}
        return names

    def test_elections_and_rules_import_only_the_standard_library_and_no_later_slice(self):
        for name in ("elections.py", "rules.py"):
            path = REPO / "umwayi" / name
            self.assertTrue(path.exists(), name)
            for imp in self.imports(path):
                top = imp.split(".")[0]
                if top == "umwayi":
                    parts = imp.split(".")
                    self.assertFalse(set(parts[1:]) & self.LATER, f"{name} imports {imp}")
                    continue
                self.assertIn(top, sys.stdlib_module_names, f"{name} imports {imp}")
                self.assertNotIn(top, self.NETWORK, f"{name} imports {imp}")

    def test_nothing_of_a_later_slice_exists_yet(self):
        # decisions.py (L13.2), rulelog.py and petition.py (L13.3) are built; slice 1 imports none of them but
        # rulelog (the test above)
        for name in ("autonomy",):
            self.assertFalse((REPO / "umwayi" / f"{name}.py").exists(), name)


if __name__ == "__main__":
    unittest.main()
