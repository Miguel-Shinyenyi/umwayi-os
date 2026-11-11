"""Layer 13, slice 5: the owner's record and the inputs reader (13.R9.5, 13.R9.6, design.md "The inputs").

`umwayi autonomy record` writes one chained entry in a fixed shape. The reader reads only entries whose source is
`umwayi autonomy record` or `umwayi autonomy`, line by line with `fullmatch`. One entry out of shape, unchained or a
duplicate makes the whole record invalid, and no class moves anywhere: the planted fault of this slice, a forged
score input, in the five ways of the design.
"""

import json

from tests.autonomy.support import ACTION, AutonomyCase, opt_in_rule, rules_text
from tests.courts_support import snapshot
from umwayi import logbook

SOURCE = "umwayi autonomy record"
CHECKED = "the hash chain was intact before this entry; the class and the outcome were checked against the allowed words"
NOT_DONE = "Nothing was moved or changed by this entry. The score is computed when a check runs, not here."


class RecordTests(AutonomyCase):
    def record(self, *extra, cls="git-commit", outcome="approved", by="Owner", date="2026-11-30"):
        return self.u("autonomy", "record", "--class", cls, "--outcome", outcome, "--by", by, "--date", date, *extra)

    def test_one_record_is_one_chained_entry_in_the_fixed_shape(self):
        self.chain()
        before = self.log.read_bytes()
        r = self.record("--ref", "Q-0007")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Recorded outcome approved for class git-commit", r.stdout)
        after = self.log.read_bytes()
        self.assertTrue(after.startswith(before))
        [e] = self.entries()[-1:]
        self.assertEqual((e["date"], e["source"]), ("2026-11-30", SOURCE))
        self.assertEqual(e["added"], "outcome approved for class git-commit recorded by Owner; ref Q-0007")
        self.assertEqual((e["checked"], e["not_done"]), (CHECKED, NOT_DONE))
        self.assertIsNotNone(e["chain"])
        self.record(outcome="reverted", date="2026-11-30")
        self.assertEqual(self.entries()[-1]["added"], "outcome reverted for class git-commit recorded by Owner")
        self.assertEqual(self.u("logbook", "verify").returncode, 0)

    def test_every_outcome_word_and_a_revert_needs_no_approval(self):
        self.chain()
        for outcome in ("approved", "edited", "rejected", "reverted"):
            self.assertEqual(self.record("--ref", "Q-0001", outcome=outcome).returncode, 0, outcome)

    def test_refused_without_a_chain_or_with_a_broken_logbook(self):
        logbook.append(self.root, logbook.Entry("2026-11-01", "umwayi test", "not chained", "x", "y"))
        before = snapshot(self.root)
        r = self.record()
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("hash chain has not started", r.stderr)
        self.assertEqual(snapshot(self.root), before)
        self.chain(date="2026-11-02")
        self.log.write_text(self.logtext() + "\n", encoding="utf-8")
        before = snapshot(self.root)
        r = self.record()
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("not intact", r.stderr)
        self.assertEqual(snapshot(self.root), before)

    def test_a_ref_recorded_twice_with_the_same_outcome_is_refused(self):
        self.chain()
        self.assertEqual(self.record("--ref", "Q-0007").returncode, 0)
        before = snapshot(self.root)
        r = self.record("--ref", "Q-0007")
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("Q-0007 was already recorded as approved", r.stderr)
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(self.record("--ref", "Q-0007", outcome="reverted").returncode, 0)

    def test_bad_arguments_are_usage_errors(self):
        self.chain()
        before = snapshot(self.root)
        for extra, kw in (([], dict(cls="Git")), ([], dict(cls="1x")), ([], dict(cls="a" * 41)),
                          ([], dict(outcome="blessed")), ([], dict(by="")), ([], dict(by="a;b")), ([], dict(by="a|b")),
                          ([], dict(by="n" * 41)), ([], dict(by="two\nlines")), (["--ref", "Q-1"], {}),
                          (["--ref", "q-0001"], {}), ([], dict(date="2026-13-01"))):
            with self.subTest(extra=extra, **{k: v[:10] for k, v in kw.items()}):
                r = self.record(*extra, **kw)
                self.assertEqual(r.returncode, 64, r.stdout + r.stderr)
        self.assertEqual(snapshot(self.root), before)

    def test_a_crash_in_the_record_exits_2_and_writes_nothing(self):
        self.chain()
        before = snapshot(self.root)
        r = self.u("autonomy", "record", "--class", "git-commit", "--outcome", "approved", "--by", "Owner",
                   fault="umwayi.logbook:append_with:crash")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(snapshot(self.root), before)


class ForgedInputTests(AutonomyCase):
    """The planted fault: a forged score input. Each is a well formed logbook entry, chained by the real append,
    that a writer could add; the reader finds it and the whole record is invalid."""

    def forge(self, added, checked=CHECKED, not_done=NOT_DONE, source=SOURCE, date="2026-11-25"):
        logbook.append(self.root, logbook.Entry(date, source, added, checked, not_done))

    def assert_invalid(self):
        self.assert_no_move("inputs-invalid")
        r = self.u("autonomy", "status")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("inputs: invalid", r.stdout)
        self.assertNotIn("per mille", r.stdout)

    def test_a_well_formed_entry_with_a_wrong_checked_line(self):
        self.ready()
        self.forge("outcome approved for class git-commit recorded by Owner", checked="trust me")
        self.assert_invalid()

    def test_an_entry_with_a_count_field(self):
        self.ready()
        self.forge("outcome approved for class git-commit recorded by Owner; count 500")
        self.assert_invalid()

    def test_an_unchained_input_written_before_the_chain(self):
        self.forge("outcome approved for class git-commit recorded by Owner", date="2026-07-01")
        self.ready()
        self.assert_invalid()

    def test_an_unknown_outcome_word(self):
        self.ready()
        self.forge("outcome blessed for class git-commit recorded by Owner")
        self.assert_invalid()

    def test_a_duplicate_ref(self):
        self.ready()
        for _ in range(2):
            self.forge("outcome approved for class git-commit recorded by Owner; ref Q-0007")
        self.assert_invalid()

    def test_a_settings_entry_out_of_shape(self):
        self.ready()
        self.forge("autonomy.yaml changed by hand", checked="x", not_done="y", source="umwayi autonomy")
        self.assert_invalid()

    def test_a_forged_move_entry_out_of_shape(self):
        self.ready()
        self.forge("Rule commit-ask gave Ask me first and autonomy moved it to Yes; action type: tool_bash",
                   checked="action read; autonomy: moved to Yes; class git-commit; whatever", not_done="x",
                   source="umwayi check", date="2026-12-01")
        self.assert_invalid()

    def test_an_entry_of_another_source_is_never_read(self):
        """The same words under another source are not an input: they neither count nor make the record invalid."""
        self.ready(37, 0)
        for _ in range(5):
            self.forge("outcome approved for class git-commit recorded by Owner", source="umwayi note")
        self.assert_no_move("low-score")

    def test_a_valid_record_reads_the_same_after_the_forgery_is_gone(self):
        self.ready()
        good = self.log.read_bytes()
        self.forge("outcome approved for class git-commit recorded by Owner; count 500")
        self.assert_invalid()
        self.log.write_bytes(good)
        self.rerecord()
        c, data, r = self.ask()
        self.assertEqual((c, data["answer"]), (0, "Yes"), r.stdout)


class OptInParseTests(AutonomyCase):
    """13.R9.2 and 13.R9.3: the `autonomy` field of a rule. Every bad shape makes rules.yaml malformed: every check
    is Ask me first, with or without graded autonomy."""

    NEVER = ("payment", "transfer", "purchase", "withdraw", "deposit", "publish", "post", "send", "publish_draft",
             "schedule_install", "budget_check", "agent_run", "agent_login", "acp_permission")

    def malformed(self, text, why):
        self.write_rules(text)
        r = self.u("check", json.dumps(ACTION), "--json", "--no-log")
        data = json.loads(r.stdout)
        self.assertEqual((r.returncode, data["answer"], data["rules_ok"]), (3, "Ask me first", False), why)

    def test_every_type_of_the_never_list_with_an_opt_in_is_malformed(self):
        for t in self.NEVER:
            with self.subTest(type=t):
                self.malformed(rules_text(opt_in_rule(matchers=f"      type: [tool_bash, {t}]\n")), t)
                self.malformed(rules_text(opt_in_rule(matchers=f"      type: {t.upper()}\n")), t)

    def test_bad_shapes_are_malformed(self):
        cases = {
            "on a yes rule": rules_text(opt_in_rule().replace("verdict: ask", "verdict: yes")),
            "on a no rule": rules_text(opt_in_rule().replace("verdict: ask", "verdict: no")),
            "no type matcher": rules_text(opt_in_rule(matchers="      command__contains: git commit\n")),
            "a type that is not equals": rules_text(opt_in_rule(matchers="      type__contains: bash\n")),
            "reversible as a word": rules_text(opt_in_rule(reversible="yes")),
            "cost as a boolean": rules_text(opt_in_rule(cost="true")),
            "cost negative": rules_text(opt_in_rule(cost=-1)),
            "cost too big": rules_text(opt_in_rule(cost=1000001)),
            "cost a float": rules_text(opt_in_rule(cost="2.5")),
            "a bad class": rules_text(opt_in_rule(cls="Git Commit")),
            "an extra key": rules_text(opt_in_rule(autonomy="    autonomy:\n      class: git-commit\n      reversible: "
                                                           "true\n      cost_uu: 2\n      score: 900")),
            "not a mapping": rules_text(opt_in_rule(autonomy="    autonomy: git-commit")),
            "two rules of one class that disagree": rules_text(
                opt_in_rule(), opt_in_rule("bash-ask", cost=3, matchers="      type: tool_bash\n")),
            "review_by on an ask rule without an opt-in": rules_text(opt_in_rule(autonomy="").replace(
                "    verdict: ask\n", "    verdict: ask\n    review_by: 2027-01-01\n")),
        }
        for why, text in cases.items():
            with self.subTest(why=why):
                self.malformed(text, why)

    def test_good_shapes_parse(self):
        for text in (rules_text(opt_in_rule(cost=0)), rules_text(opt_in_rule(cost=1000000)),
                     rules_text(opt_in_rule(reversible="false")), rules_text(opt_in_rule(review_by="2027-01-01")),
                     rules_text(opt_in_rule(matchers="      type: [tool_bash, tool_powershell]\n"))):
            with self.subTest(text=text[-60:]):
                self.write_rules(text)
                r = self.u("check", json.dumps(ACTION), "--json", "--no-log")
                self.assertTrue(json.loads(r.stdout)["rules_ok"], r.stdout)

    def test_the_opt_in_is_in_the_rules_change_log(self):
        self.write_rules(rules_text(opt_in_rule(review_by="2027-01-01")))
        self.u("check", json.dumps(ACTION))
        e = [b for b in self.entries() if b["source"] == "umwayi rules"][-1]
        self.assertTrue(e["checked"].endswith("state: commit-ask ask review_by 2027-01-01 autonomy git-commit "
                                              "reversible yes cost 2"), e["checked"])
        self.write_rules(rules_text(opt_in_rule(review_by="2027-01-01", reversible="false")))
        self.u("check", json.dumps(ACTION))
        e = [b for b in self.entries() if b["source"] == "umwayi rules"][-1]
        self.assertTrue(e["added"].endswith("; changed commit-ask autonomy git-commit reversible yes cost 2 to "
                                            "git-commit reversible no cost 2"), e["added"])
