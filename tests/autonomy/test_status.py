"""Layer 13, slice 5: `umwayi autonomy status` (13.R9.9, design.md "autonomy status"). It prints, per class, the four
counts, the weighted total, the score, the thresholds, the cooldown, the moves of the day and the first gate that
holds the class, and it changes nothing."""

from tests.autonomy.support import AutonomyCase, opt_in_rule, rules_text
from tests.courts_support import snapshot

CASE_3 = [
    "class git-commit   rule commit-ask   reversible yes   cost 2 of 10 UU",
    "  approved 80  edited 2  rejected 0  reverted 1  weight 3  n 85  score 838 per mille  (needs n 30, score 850)",
    "  cooldown until 2026-12-30   moves today 0 of 5   state: Ask me first (cooldown)",
    "graded autonomy: on. inputs: intact (83 outcomes). kill switch: off.",
]


class StatusTests(AutonomyCase):
    def status(self, *extra, code=0, **kw):
        r = self.u("autonomy", "status", *extra, **kw)
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        return r.stdout.splitlines()

    def case_3(self):
        self.chain()
        self.seed(80, 2, 0, 1, dates={"approved": "2026-10-01", "edited": "2026-10-02", "reverted": "2026-11-30"})
        self.settings()

    def test_the_design_example_line_by_line_and_nothing_written(self):
        self.case_3()
        before = snapshot(self.root)
        self.assertEqual(self.status(), CASE_3)
        self.assertEqual(snapshot(self.root), before)

    def test_an_eligible_class(self):
        self.ready()
        lines = self.status()
        self.assertEqual(lines[1], "  approved 80  edited 2  rejected 0  reverted 0  weight 3  n 82  score 884 per "
                                   "mille  (needs n 30, score 850)")
        self.assertEqual(lines[2], "  no cooldown   moves today 0 of 5   state: eligible")

    def test_off_shows_the_counts_as_a_display(self):
        self.case_3()
        (self.root / "autonomy.yaml").unlink()
        self.assertEqual(self.status(), [
            "class git-commit   rule commit-ask   reversible yes   cost 2 UU",
            "  approved 80  edited 2  rejected 0  reverted 1  (every outcome recorded; no settings, so no score)",
            "graded autonomy: off (no autonomy.yaml). inputs: intact (83 outcomes). kill switch: off.",
        ])
        self.settings(enabled="false")
        lines = self.status()
        self.assertEqual(lines[2], "  cooldown until 2026-12-30   moves today 0 of 5   state: Ask me first (autonomy-off)")
        self.assertEqual(lines[-1], "graded autonomy: off (enabled: false). inputs: intact (83 outcomes). kill switch: off.")

    def test_invalid_settings(self):
        self.case_3()
        self.settings(window_days=0)
        lines = self.status()
        self.assertIn("state: Ask me first (settings-invalid)", lines[2] if len(lines) > 2 else lines[-1] + " ".join(lines))
        self.assertEqual(lines[-1], "graded autonomy: off (autonomy.yaml is invalid, see umwayi autonomy validate). "
                                    "inputs: intact (83 outcomes). kill switch: off.")

    def test_the_kill_switch(self):
        self.ready()
        (self.root / ".umwayi" / "KILL").write_text("on\n")
        lines = self.status()
        self.assertTrue(lines[2].endswith("state: Ask me first (kill-switch)"), lines)
        self.assertTrue(lines[-1].endswith("kill switch: on."))

    def test_a_record_that_cannot_be_read(self):
        self.ready()
        self.log.write_text(self.logtext() + "\n", encoding="utf-8")
        lines = self.status()
        self.assertEqual(lines, ["class git-commit   rule commit-ask   reversible yes   cost 2 of 10 UU",
                                 "graded autonomy: on. inputs: cannot be read (the logbook is not intact), so no class "
                                 "is moved and no score is shown. kill switch: off."])

    def test_no_chain(self):
        self.settings()
        lines = self.status()
        self.assertIn("inputs: cannot be read (the hash chain has not started)", lines[-1])

    def test_a_class_without_a_rule_and_the_class_filter(self):
        self.chain()
        self.seed(5, 0, cls="other-class")
        self.seed(40, 0, dates={"approved": "2026-11-25"})
        self.settings()
        lines = self.status()
        self.assertIn("class other-class   rule none   (no rule opts this class in)", lines)
        self.assertIn("  no cooldown   moves today 0 of 5   state: Ask me first (not-opted-in)", lines)
        only = self.status("--class", "other-class")
        self.assertEqual(only[0], "class other-class   rule none   (no rule opts this class in)")
        self.assertNotIn("git-commit", "\n".join(only))
        self.assertEqual(self.status("--class", "nothing-here")[0], "class nothing-here: no rule opts it in and no "
                                                                     "outcome is recorded")

    def test_two_rules_of_one_class_and_an_irreversible_class(self):
        self.write_rules(rules_text(opt_in_rule(reversible="false"),
                                    opt_in_rule("bash-ask", reversible="false", matchers="      type: tool_bash\n")))
        self.ready()
        lines = self.status()
        self.assertEqual(lines[0], "class git-commit   rule commit-ask, bash-ask   reversible no   cost 2 of 10 UU")
        self.assertTrue(lines[2].endswith("state: Ask me first (irreversible)"))

    def test_bad_arguments_are_usage_errors(self):
        for extra in (["--class", "Bad Name"], ["--date", "2026-02-30"]):
            self.status(*extra, code=64)
