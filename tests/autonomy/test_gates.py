"""Layer 13, slice 5: the move and the thirteen gates (13.R10, 13.R11, design.md "The gates, in order" and "Fail
closed table"), as real child processes.

The worked example of the design is the fixture: `autonomy.yaml` with window 90, min 30, bound 850, z 2.58, weight
3, max cost 10, cooldown 30, 5 moves a day; the rule `commit-ask` opts in the class `git-commit`, reversible, cost
2; today is 2026-12-01. Every row of the fail closed table is planted on its own, and none of them gives Yes.
"""

import json
import os
import shutil

from tests.autonomy.support import (ACTION, TODAY, AutonomyCase, opt_in_rule, plain_rule, rules_text)
from tests.helpers import hold_logbook_lock

BASE_CHECKED = ("action read as a JSON object without duplicate keys: yes; rules.yaml loaded: yes (1 rules); "
                "rules matched: commit-ask")
MOVED = ("; autonomy: moved to Yes; class git-commit; approved 80; edited 2; rejected 0; reverted 0; weight 3; n 82; "
         "score 884 per mille; needs n 30 and score 850; reversible yes; cost 2 of 10 UU; moves today {k} of 5")
NO_RULE = plain_rule("no-commit", "no", "      type: tool_bash\n")


# ============================================================ the worked example


class WorkedExampleTests(AutonomyCase):
    def test_case_2_moves_to_yes_and_logs_every_input(self):
        self.ready()
        before = self.log.read_bytes()
        code, data, r = self.ask()
        self.assertEqual((code, data["answer"], data["rule_id"], data["logged"]), (0, "Yes", "commit-ask", True),
                         r.stdout + r.stderr)
        self.assertEqual(data["autonomy"], {"moved": True, "class": "git-commit", "score": 884, "gate": None})
        self.assertIn("moved it to Yes", data["reason"])
        self.assertTrue(self.log.read_bytes().startswith(before))
        e = self.last_check()
        self.assertEqual(e["added"], "Rule commit-ask gave Ask me first and autonomy moved it to Yes; action type: "
                                     "tool_bash")
        self.assertEqual(e["checked"], BASE_CHECKED + MOVED.format(k=1))
        self.assertEqual(e["not_done"], "The action was not run. The action JSON was not stored in the logbook.")
        self.assertEqual(self.u("logbook", "verify").returncode, 0)
        r = self.u("check", json.dumps(ACTION))
        self.assertEqual(r.returncode, 0)
        self.assertTrue(r.stdout.startswith("Yes\nRule: commit-ask\nReason: "), r.stdout)
        self.assertEqual(self.last_check()["checked"], BASE_CHECKED + MOVED.format(k=2))

    def test_the_settings_are_logged_before_the_first_move(self):
        self.ready()
        self.ask()
        tail = [b["source"] for b in self.entries()][-3:]
        self.assertEqual(tail, ["umwayi rules", "umwayi autonomy", "umwayi check"])
        e = [b for b in self.entries() if b["source"] == "umwayi autonomy"][0]
        self.assertTrue(e["added"].startswith("autonomy.yaml first logged (sha256 "), e["added"])

    def test_case_1_low_score(self):
        self.chain()
        self.seed(70, 3, 1, dates={"rejected": "2026-09-10"})  # outside the cooldown
        self.settings()
        self.assert_no_move("low-score")

    def test_case_3_a_revert_yesterday_is_a_cooldown(self):
        self.chain()
        self.seed(80, 2, 0, 1, dates={"approved": "2026-10-01", "edited": "2026-10-02", "reverted": "2026-11-30"})
        self.settings()
        self.assert_no_move("cooldown")

    def test_case_3_after_the_cooldown_the_score_holds_it(self):
        self.chain()
        self.seed(80, 2, 0, 1, dates={"approved": "2026-10-01", "edited": "2026-10-02", "reverted": "2026-11-30"})
        self.settings(window_days=120)
        c, data, r = self.ask(None, "--date", "2026-12-31", today="2026-12-31")
        self.assertEqual((c, self.gate_word()), (3, "low-score"), r.stdout + r.stderr)

    def test_the_cooldown_runs_through_its_last_day(self):
        self.chain()
        self.seed(80, 2, 1, dates={"approved": "2026-11-01", "edited": "2026-11-02", "rejected": "2026-11-01"})
        self.settings(revert_weight=1, min_lower_bound=800)
        c, data, r = self.ask(None, "--date", "2026-12-01", today="2026-12-01")  # 11-01 + 30 = 12-01: still on
        self.assertEqual(self.gate_word(), "cooldown")
        c, data, r = self.ask(None, "--date", "2026-12-02", today="2026-12-02")
        self.assertEqual((c, data["answer"]), (0, "Yes"), r.stdout)

    def test_case_4_irreversible(self):
        self.write_rules(rules_text(opt_in_rule(reversible="false")))
        self.ready()
        self.assert_no_move("irreversible")

    def test_case_5_costly(self):
        self.write_rules(rules_text(opt_in_rule(cost=11)))
        self.ready()
        self.assert_no_move("cost")

    def test_case_5_the_cost_at_the_limit_moves(self):
        self.write_rules(rules_text(opt_in_rule(cost=10)))
        self.ready()
        self.assertEqual(self.ask()[0], 0)

    def test_the_score_at_its_exact_edge(self):
        """37 clean approvals score 847: a bound of 847 moves, 848 does not (one per mille below)."""
        self.ready(37, 0, min_lower_bound=848)
        self.assert_no_move("low-score")
        self.settings(min_lower_bound=847)
        self.assertEqual(self.ask()[0], 0)

    def test_case_6_low_data(self):
        self.ready(20, 0)
        self.assert_no_move("low-data")

    def test_outcomes_older_than_the_window_are_not_counted(self):
        self.chain()
        self.seed(80, 2, dates={"approved": "2026-08-20", "edited": "2026-08-21"})  # 102 days before
        self.settings()
        self.assert_no_move("low-data")
        self.settings(window_days=200)
        self.assertEqual(self.ask()[0], 0)

    def test_another_class_does_not_count(self):
        self.chain()
        self.seed(80, 2, cls="other-class")
        self.settings()
        self.assert_no_move("low-data")


# ============================================================ the fail closed table (13.R11), row by row


class FailClosedTests(AutonomyCase):
    def test_row_1_off_or_invalid_settings(self):
        self.ready()
        os.unlink(self.root / "autonomy.yaml")
        self.assert_no_move(None)
        self.settings(enabled="false")
        self.assert_no_move(None)
        for over, why in ((dict(max_cost_uu=None), "a key missing"), (dict(window_days=0), "out of range"),
                          (dict(confidence_z=99), "out of range"), (dict(enabled="yes"), "not true or false"),
                          (dict(extra_key=1), "an extra key"), (dict(min_decisions="30.5"), "not a whole number")):
            with self.subTest(why=why):
                self.settings(**over)
                self.assert_no_move("settings-invalid")
        self.settings(text="version: 1\nenabled: [true\n")
        self.assert_no_move("settings-invalid")

    def test_row_2_twenty_nine_clean_approvals(self):
        self.ready(29, 0)
        self.assert_no_move("low-data")

    def test_row_2_thirty_eight_clean_approvals_move(self):
        self.ready(38, 0)
        self.assertEqual(self.ask()[0], 0)

    def test_rows_3_and_4_a_missing_field_makes_the_rules_malformed(self):
        self.ready()
        for auto in ("    autonomy:\n      class: git-commit\n      cost_uu: 2",
                     "    autonomy:\n      class: git-commit\n      reversible: true"):
            with self.subTest(auto=auto[-12:]):
                self.write_rules(rules_text(opt_in_rule(autonomy=auto)))
                c, data, r = self.ask()
                self.assertEqual((c, data["answer"], data["rules_ok"]), (3, "Ask me first", False))
                self.assertNotIn("autonomy", data)

    def test_row_5_a_matching_no_is_never_moved(self):
        self.write_rules(rules_text(opt_in_rule(), NO_RULE))
        self.chain()
        self.seed(500, 0)
        self.settings()
        c, data, r = self.ask()
        self.assertEqual((c, data["answer"], data["rule_id"]), (2, "No", "no-commit"))
        self.assertNotIn("autonomy", data)
        self.assertNotIn("autonomy", self.last_check()["checked"])

    def test_row_6_a_broken_record_gives_no_move(self):
        cases = {
            "an old chained entry edited": lambda: (self.log.write_text(self.logtext().replace(
                "for class git-commit recorded by Owner", "for class git-commit recorded by Owen", 1)),
                self.rerecord()),
            "a deleted entry": lambda: (self.delete_one_record(), self.rerecord()),
            "the hash record changed": lambda: self.rec.write_text("0" * 64 + "\n"),
            "a torn tail": lambda: self.log.write_bytes(self.log.read_bytes() + b"\n## 2026-12-01\n\n- Sou"),
        }
        for name, plant in cases.items():
            with self.subTest(case=name):
                self.tearDown_root()
                self.ready()
                plant()
                before = self.log.read_bytes()
                c, data, r = self.ask()
                self.assertEqual((c, data["answer"], data["logged"]), (3, "Ask me first", False), r.stdout)
                self.assertEqual(self.log.read_bytes(), before)

    def test_row_6_a_chain_that_has_not_started(self):
        from umwayi import logbook as lb
        lb.append(self.root, lb.Entry("2026-11-01", "umwayi test", "no chain here", "x", "y"))
        self.settings()
        self.assert_no_move("chain")

    def test_row_6_an_unreadable_logbook(self):
        self.ready()
        os.chmod(self.log, 0)
        self.addCleanup(os.chmod, self.log, 0o644)
        if os.access(self.log, os.R_OK):
            self.skipTest("running as a user that reads any file")
        c, data, r = self.ask()
        self.assertEqual((c, data["answer"], data["logged"]), (3, "Ask me first", False))

    def test_row_8_the_kill_switch(self):
        self.ready()
        (self.root / ".umwayi" / "KILL").write_text("on\n")
        self.assert_no_move("kill-switch")
        c, data, r = self.ask(None, "--kill-switch")
        self.assertEqual((c, data["answer"]), (2, "No"))
        self.assertNotIn("autonomy", data)

    def test_row_8_a_kill_switch_state_that_cannot_be_read(self):
        self.ready()
        shutil.rmtree(self.root / ".umwayi")
        (self.root / ".umwayi").write_text("not a folder\n")
        c, data, r = self.ask()
        self.assertEqual((c, data["answer"]), (3, "Ask me first"))
        self.assertNotIn("moved it to Yes", self.logtext())

    def test_row_9_unreadable_inputs(self):
        self.ready()
        c, data, r = self.ask('{"type": "tool_bash", "type": "x"}')
        self.assertEqual((c, data["answer"]), (3, "Ask me first"))
        os.unlink(self.root / "autonomy.yaml")
        (self.root / "autonomy.yaml").mkdir()
        self.assert_no_move("settings-invalid")
        os.rmdir(self.root / "autonomy.yaml")
        self.settings()
        self.write_rules("rules: [\n")
        c, data, r = self.ask()
        self.assertEqual((c, data["answer"], data["rules_ok"]), (3, "Ask me first", False))
        self.assertEqual(self.u("check", json.dumps(ACTION), "--date", "2026-13-01").returncode, 64)

    def test_row_10_a_dry_run_and_a_held_lock(self):
        self.ready()
        before = self.log.read_bytes()
        c, data, r = self.ask(None, "--no-log")
        self.assertEqual((c, data["answer"], data["logged"]), (3, "Ask me first", False))
        self.assertNotIn("autonomy", data)
        self.assertEqual(self.log.read_bytes(), before)
        self.ask()  # logs the rules and the settings, and moves
        release = hold_logbook_lock(self.root)
        try:
            c, data, r = self.ask()
        finally:
            release()
        self.assertEqual((c, data["answer"], data["logged"]), (3, "Ask me first", False))

    def test_row_10_a_move_that_cannot_be_logged_is_not_made(self):
        self.ready()
        self.ask()
        n = len(self.entries())
        c, data, r = self.ask(fault="umwayi.logbook:append:error")
        self.assertEqual((c, data["answer"], data["logged"]), (3, "Ask me first", False), r.stdout + r.stderr)
        self.assertEqual(len(self.entries()), n)

    def test_row_11_a_lapsed_yes_rule_and_a_lapsed_opt_in(self):
        self.write_rules(rules_text(opt_in_rule(), plain_rule("old-yes", "yes", "      type: tool_bash\n",
                                                              review_by="2026-11-01")))
        self.ready()
        self.assert_no_move("election-lapsed")
        self.write_rules(rules_text(opt_in_rule(review_by="2026-11-15")))
        self.assert_no_move("opt-in-lapsed")
        self.write_rules(rules_text(opt_in_rule(review_by="2026-12-01")))  # in force through its day
        self.assertEqual(self.ask()[0], 0)

    def test_row_12_a_rejection_ten_days_ago_with_a_perfect_score(self):
        self.chain()
        self.seed(500, 0, 1, dates={"approved": "2026-10-01", "rejected": "2026-11-21"})
        self.settings()
        self.assert_no_move("cooldown")

    def test_row_12_the_daily_cap(self):
        self.ready()
        for k in range(1, 6):
            c, data, r = self.ask()
            self.assertEqual((c, data["answer"]), (0, "Yes"), (k, r.stdout))
            self.assertTrue(self.last_check()["checked"].endswith(f"moves today {k} of 5"))
        self.assert_no_move("daily-cap")
        c, data, r = self.ask(None, "--date", "2026-12-02", today="2026-12-02")
        self.assertEqual(c, 0)  # a new logbook day
        self.assertTrue(self.last_check()["checked"].endswith("moves today 1 of 5"))

    def test_row_13_a_crash_inside_the_score_exits_2(self):
        self.ready()
        before = self.log.read_bytes()
        r = self.u("check", json.dumps(ACTION), fault="umwayi.autonomy:wilson:crash")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("stopped by an unexpected error (RuntimeError)", r.stderr)
        self.assertNotIn("moved it to Yes", self.logtext()[len(before.decode()):])

    # ------------------------------------------------------------ helpers

    def tearDown_root(self):
        for p in list(self.root.iterdir()):
            if p.name != "rules.yaml":
                shutil.rmtree(p) if p.is_dir() else p.unlink()

    def delete_one_record(self):
        lines = self.logtext().split("\n")
        for i, line in enumerate(lines):
            if line == "- Source: umwayi autonomy record":
                del lines[i - 3:i + 5]
                break
        self.log.write_text("\n".join(lines), encoding="utf-8")


# ============================================================ the rule gates


class RuleGateTests(AutonomyCase):
    def test_two_ask_rules_of_which_one_opts_in(self):
        self.write_rules(rules_text(opt_in_rule(), plain_rule("other-ask", "ask", "      type: tool_bash\n")))
        self.ready()
        self.assert_no_move("not-opted-in")

    def test_two_opt_in_rules_of_two_classes(self):
        self.write_rules(rules_text(opt_in_rule(), opt_in_rule("bash-ask", "any-bash",
                                                               matchers="      type: tool_bash\n")))
        self.ready()
        self.assert_no_move("class-mismatch")

    def test_two_opt_in_rules_of_one_class_move(self):
        self.write_rules(rules_text(opt_in_rule(), opt_in_rule("bash-ask", matchers="      type: tool_bash\n")))
        self.ready()
        c, data, r = self.ask()
        self.assertEqual((c, data["answer"]), (0, "Yes"), r.stdout)

    def test_a_yes_is_never_moved_and_no_match_writes_nothing_new(self):
        self.write_rules(rules_text(opt_in_rule(), plain_rule("ok-read", "yes", "      type: read\n")))
        self.ready()
        c, data, r = self.ask({"type": "read"})
        self.assertEqual((c, data["answer"]), (0, "Yes"))
        self.assertNotIn("autonomy", data)
        self.assertNotIn("autonomy", self.last_check()["checked"])
        c, data, r = self.ask({"type": "launch"})
        self.assertEqual((c, data["answer"], data["rule_id"]), (3, "Ask me first", None))
        self.assertNotIn("autonomy", data)

    def test_a_yes_rule_beside_the_opt_in_still_lets_it_move(self):
        self.write_rules(rules_text(opt_in_rule(), plain_rule("bash-yes", "yes", "      type: tool_bash\n")))
        self.ready()
        c, data, r = self.ask()
        self.assertEqual((c, data["answer"], data["rule_id"]), (0, "Yes", "commit-ask"), r.stdout)


# ============================================================ callers


class CallerTests(AutonomyCase):
    def test_a_job_never_moves(self):
        self.write_rules(rules_text(opt_in_rule(matchers="      type: tool_bash\n"),
                                    plain_rule("run-check", "yes", "      type: run_job\n")))
        self.ready()
        (self.root / "jobs.yaml").write_text("jobs:\n  - name: probe\n    command: check\n    action_type: tool_bash\n"
                                             "    min_gap_days: 1\n", encoding="utf-8")
        r = self.u("run", str(self.root / "jobs.yaml"), "--job", "probe")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("Rule: commit-ask", r.stdout)
        self.assertNotIn("moved it to Yes", self.logtext())

    def test_the_moves_do_not_feed_the_score(self):
        self.ready()
        for _ in range(5):
            self.assertEqual(self.ask()[0], 0)
        r = self.u("autonomy", "status")
        self.assertIn("approved 80  edited 2  rejected 0  reverted 0  weight 3  n 82  score 884 per mille", r.stdout)
        self.assertIn("moves today 5 of 5", r.stdout)
