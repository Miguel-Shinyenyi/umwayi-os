"""Layer 13, slice 5: off by default and one setting (13.R12), `autonomy.yaml` (13.R9.4) and its change log
(13.R7.5), and `umwayi autonomy validate`.

Off means the behaviour of before: with no `autonomy.yaml`, or `enabled: false`, the answer, the exit code, the JSON
and the check's own logbook entry are byte for byte what they were without layer 13, even with 100 clean approvals
and a rule that opts in.
"""

import json
import shutil

from tests.autonomy.support import ACTION, REPO, AutonomyCase, settings_text
from tests.courts_support import sha, snapshot

BEFORE_JSON = """{
  "answer": "Ask me first",
  "rule_id": "commit-ask",
  "reason": "The owner is asked before an AI helper commits.",
  "matched": [
    "commit-ask"
  ],
  "rules_ok": true,
  "action_ok": true,
  "logged": true,
  "kill_switch": "off"
}
"""
BEFORE_TEXT = "Ask me first\nRule: commit-ask\nReason: The owner is asked before an AI helper commits.\n"
BEFORE_ENTRY = {
    "source": "umwayi check",
    "added": "Rule commit-ask gave Ask me first; action type: tool_bash",
    "checked": ("action read as a JSON object without duplicate keys: yes; rules.yaml loaded: yes (1 rules); rules "
                "matched: commit-ask"),
    "not_done": "The action was not run. The action JSON was not stored in the logbook.",
}


class OffTests(AutonomyCase):
    def assert_before(self):
        r = self.u("check", json.dumps(ACTION), "--json")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (3, BEFORE_JSON, ""))
        e = self.last_check()
        self.assertEqual({k: e[k] for k in BEFORE_ENTRY}, BEFORE_ENTRY)
        r = self.u("check", json.dumps(ACTION))
        self.assertEqual((r.returncode, r.stdout, r.stderr), (3, BEFORE_TEXT, ""))

    def test_no_file_is_the_behaviour_of_before_with_100_clean_approvals(self):
        self.chain()
        self.seed(100, 0)
        self.assert_before()
        self.assertNotIn("umwayi autonomy\n", self.logtext().replace("umwayi autonomy record", ""))

    def test_enabled_false_is_the_behaviour_of_before(self):
        self.ready(100, 0, enabled="false")
        self.assert_before()

    def test_the_example_file_is_off_and_valid(self):
        self.ready(100, 0)
        shutil.copy(REPO / "autonomy.example.yaml", self.root / "autonomy.yaml")
        self.assert_before()
        r = self.u("autonomy", "validate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("graded autonomy is off", r.stdout)

    def test_one_setting_turns_it_off_at_the_next_check_and_a_move_is_not_undone(self):
        self.ready()
        self.assertEqual(self.ask()[0], 0)
        moved = self.logtext()
        self.settings(enabled="false")
        self.assert_before()
        self.assertTrue(self.logtext().startswith(moved))
        changed = [b for b in self.entries() if b["source"] == "umwayi autonomy"][-1]
        self.assertTrue(changed["added"].endswith("): enabled true to false"), changed["added"])

    def test_off_without_a_chain_or_a_record(self):
        self.assert_before()


class SettingsLogTests(AutonomyCase):
    def settings_entries(self):
        return [b for b in self.entries() if b["source"] == "umwayi autonomy"]

    def test_first_logged_then_changed_then_removed_each_once(self):
        self.ready()
        self.ask()
        [first] = self.settings_entries()
        digest = sha((self.root / "autonomy.yaml").read_bytes())
        self.assertEqual(first["added"], f"autonomy.yaml first logged (sha256 {digest})")
        self.assertEqual(first["checked"], "autonomy.yaml was read and validated before this entry; this entry is "
                                           "written before the new values are first used; settings: version 1, "
                                           "enabled true, window_days 90, min_decisions 30, min_lower_bound 850, "
                                           "confidence_z 258, revert_weight 3, max_cost_uu 10, cooldown_days 30, "
                                           "max_moves_per_day 5")
        self.assertEqual(first["not_done"], "Only the setting names and numbers are logged. Nothing was moved by this "
                                            "entry.")
        self.ask()
        self.assertEqual(len(self.settings_entries()), 1, "logged again without a change")
        self.settings(min_lower_bound=800, max_moves_per_day=6)
        self.ask()
        digest = sha((self.root / "autonomy.yaml").read_bytes())
        self.assertEqual(self.settings_entries()[-1]["added"], f"autonomy.yaml changed (sha256 {digest}): "
                                                               "min_lower_bound 850 to 800; max_moves_per_day 5 to 6")
        (self.root / "autonomy.yaml").write_text("# a comment\n" + settings_text(min_lower_bound=800,
                                                                                   max_moves_per_day=6))
        self.ask()
        self.assertTrue(self.settings_entries()[-1]["added"].endswith("): no setting changed"))
        (self.root / "autonomy.yaml").unlink()
        self.assert_no_move(None)
        self.assertEqual(self.settings_entries()[-1]["added"], "autonomy.yaml removed")
        self.ask()
        self.assertEqual(len(self.settings_entries()), 4)

    def test_the_settings_entry_comes_before_the_check_that_uses_it(self):
        self.ready()
        self.ask()
        self.settings(min_decisions=100)
        self.assert_no_move("low-data")
        self.assertEqual([b["source"] for b in self.entries()][-2:], ["umwayi autonomy", "umwayi check"])

    def test_an_invalid_file_is_not_logged(self):
        self.ready()
        self.settings(window_days=0)
        self.assert_no_move("settings-invalid")
        self.assertEqual(self.settings_entries(), [])

    def test_a_file_that_cannot_be_logged_moves_nothing(self):
        self.ready()
        c, data, r = self.ask(fault="umwayi.autonomy:log_settings:error")
        self.assertEqual((c, data["answer"]), (3, "Ask me first"), r.stdout + r.stderr)
        self.assertEqual(self.gate_word(), "chain")
        self.assertEqual(self.settings_entries(), [])

    def test_without_a_chain_the_file_is_not_logged_and_nothing_moves(self):
        from umwayi import logbook
        logbook.append(self.root, logbook.Entry("2026-11-01", "umwayi test", "no chain", "x", "y"))
        self.settings()
        self.assert_no_move("chain")
        self.assertEqual(self.settings_entries(), [])


class ValidateTests(AutonomyCase):
    def test_valid_on_and_off(self):
        self.settings()
        r = self.u("autonomy", "validate")
        self.assertEqual((r.returncode, r.stdout), (0, "autonomy.yaml is valid: graded autonomy is on.\n"))
        self.settings(enabled="false")
        self.assertEqual(self.u("autonomy", "validate").stdout, "autonomy.yaml is valid: graded autonomy is off.\n")

    def test_no_file(self):
        r = self.u("autonomy", "validate")
        self.assertEqual((r.returncode, r.stdout), (0, "There is no autonomy.yaml: graded autonomy is off.\n"))

    def test_every_problem_with_a_line_number_and_nothing_written(self):
        self.settings(text="version: 2\nenabled: maybe\nwindow_days: 0\nmin_decisions: 30\nmin_lower_bound: 850\n"
                           "confidence_z: 258\nrevert_weight: 3\nmax_cost_uu: 10\ncooldown_days: 30\nextra: 1\n")
        before = snapshot(self.root)
        r = self.u("autonomy", "validate")
        self.assertEqual(r.returncode, 64, r.stdout + r.stderr)
        self.assertEqual(r.stdout.splitlines(), [
            "autonomy.yaml line 1: version must be 1",
            "autonomy.yaml line 2: enabled must be true or false",
            "autonomy.yaml line 3: window_days must be a whole number from 1 to 3650",
            "autonomy.yaml line 10: extra is not a setting",
            "autonomy.yaml: max_moves_per_day is missing",
            "5 problem(s) found. Graded autonomy is off until they are fixed.",
        ])
        self.assertEqual(snapshot(self.root), before)

    def test_a_yaml_error_and_a_folder(self):
        self.settings(text="version: 1\nenabled: [true\n")
        r = self.u("autonomy", "validate")
        self.assertEqual(r.returncode, 64)
        self.assertIn("autonomy.yaml line 2:", r.stdout)
        (self.root / "autonomy.yaml").unlink()
        (self.root / "autonomy.yaml").mkdir()
        r = self.u("autonomy", "validate")
        self.assertEqual(r.returncode, 64)
        self.assertIn("autonomy.yaml: not a regular file", r.stdout)

    def test_the_opt_in_rules_are_checked_too(self):
        self.settings()
        self.write_rules("rules:\n  - id: x\n    title: t\n    text: t\n    verdict: yes\n    autonomy:\n"
                         "      class: c\n      reversible: true\n      cost_uu: 1\n    matchers:\n      type: a\n")
        r = self.u("autonomy", "validate")
        self.assertEqual(r.returncode, 64)
        self.assertIn("rules.yaml: rule 'x': autonomy is allowed on an ask rule only", r.stdout)

    def test_every_range(self):
        ranges = {"window_days": (1, 3650), "min_decisions": (1, 1000000), "min_lower_bound": (1, 1000),
                  "confidence_z": (100, 400), "revert_weight": (1, 100), "max_cost_uu": (0, 1000000),
                  "cooldown_days": (1, 3650), "max_moves_per_day": (1, 1000)}
        for key, (lo, hi) in ranges.items():
            for value, ok in ((lo, True), (hi, True), (lo - 1, False), (hi + 1, False), ("true", False)):
                with self.subTest(key=key, value=value):
                    self.settings(**{key: value})
                    self.assertEqual(self.u("autonomy", "validate").returncode, 0 if ok else 64)
