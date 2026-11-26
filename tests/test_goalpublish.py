"""Goal publish step 1: the rules action `goal_publish` (umwayi/goalpublish.py). It builds and asks; it pushes nothing."""
import tempfile
import unittest
from pathlib import Path

from umwayi import goalpublish as gp, logbook, rules

WHEN = "2026-11-26"
GOOD = ("G-0002", "T-01", "Miguel-Shinyenyi/mpesa-statement-analyzer", "umwayi/g-0002-t-01")


def rules_text(verdict=None, repo=GOOD[2]):
    if verdict is None:
        return "rules: []\n"
    return (f"rules:\n  - id: publish-test\n    title: test\n    text: test\n    cause: test\n    verdict: {verdict}\n"
            f"    matchers:\n      type: goal_publish\n      repo: [{repo}]\n")


class ActionTests(unittest.TestCase):
    def test_the_action_has_the_fixed_fields(self):
        self.assertEqual(gp.action(*GOOD), {"type": "goal_publish", "goal": "G-0002", "task": "T-01",
                                           "repo": GOOD[2], "branch": GOOD[3]})

    def test_main_and_other_branch_names_are_refused(self):
        for branch in ("main", "master", "umwayi/main", "feature/x", "umwayi/g-0002-t-01/extra", "umwayi/G-0002-T-01", ""):
            with self.assertRaises(gp.PublishRefused, msg=branch):
                gp.action("G-0002", "T-01", GOOD[2], branch)

    def test_a_branch_of_another_task_is_refused(self):
        with self.assertRaises(gp.PublishRefused):
            gp.action("G-0002", "T-01", GOOD[2], "umwayi/g-0002-t-02")
        with self.assertRaises(gp.PublishRefused):
            gp.action("G-0002", "T-01", GOOD[2], "umwayi/g-0003-t-01")

    def test_bad_goal_task_and_repo_are_refused(self):
        for args in (("G-2", "T-01", GOOD[2], GOOD[3]), ("G-0002", "T-1", GOOD[2], GOOD[3]),
                     ("G-0002", "T-01", "no-slash", GOOD[3]), ("G-0002", "T-01", "a/b.git", GOOD[3]),
                     ("G-0002", "T-01", "a/b c", GOOD[3]), ("G-0002", "T-01", None, GOOD[3])):
            with self.assertRaises(gp.PublishRefused, msg=str(args)):
                gp.action(*args)

    def test_the_message_never_carries_the_refused_text(self):
        with self.assertRaises(gp.PublishRefused) as cm:
            gp.action("G-0002", "T-01", GOOD[2], "SECRET-BRANCH")
        self.assertNotIn("SECRET-BRANCH", str(cm.exception))

    def test_autonomy_can_never_move_goal_publish(self):
        self.assertIn("goal_publish", rules.NEVER_AUTONOMY)


class DecideTests(unittest.TestCase):
    def ask(self, text):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "rules.yaml").write_text(text, encoding="utf-8")
            answer = gp.decide(root, gp.action(*GOOD), WHEN)
            entries = [e for e in logbook.read_checked(root) if e.source == "umwayi check"]
            return answer, entries

    def test_no_rule_means_ask_and_one_entry_is_written(self):
        answer, entries = self.ask(rules_text())
        self.assertEqual(answer, "ask")
        self.assertEqual(len(entries), 1)
        self.assertIn("goal_publish", entries[0].added)

    def test_a_yes_rule_that_names_the_repo_gives_yes(self):
        self.assertEqual(self.ask(rules_text("yes"))[0], "yes")

    def test_a_yes_rule_for_another_repo_gives_ask(self):
        self.assertEqual(self.ask(rules_text("yes", repo="someone/else"))[0], "ask")

    def test_a_no_rule_gives_no(self):
        self.assertEqual(self.ask(rules_text("no"))[0], "no")

    def test_a_broken_rules_file_gives_ask(self):
        self.assertEqual(self.ask("rules: [this is not a rule]\n")[0], "ask")


if __name__ == "__main__":
    unittest.main()
