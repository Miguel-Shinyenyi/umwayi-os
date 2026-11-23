"""W78 5(a): every helper's prompt starts with the task card: the mode, the scope and the rules in force, in one fixed order
and in fixed words (umwayi/goalrun.py `task_card`, `rules_card`).

Guidance is not enforcement: the card is text a model may ignore, and the gate and the scope check decide. The words are
umwayi's own; the only text of someone else's in it is the title of a No rule, which is the owner's (cut to 80 characters, one
line). The card says that it is not the check.
"""
import types
import unittest

from tests.goal import cmdsupport as cs
from umwayi import goalpacket as gp
from umwayi import goalrun as gr

PACKET = types.SimpleNamespace(goal="Do the thing.", checks=("It works.",), files=("umwayi/a.py",), context=())
RULES = """rules:
  - id: cc-no-money
    title: Claude Code never moves money
    text: Never.
    verdict: no
    matchers:
      platform: claude-code
      type: tool_bash
  - id: cc-ask-web
    title: web needs the owner
    text: Ask.
    verdict: ask
    matchers:
      platform: claude-code
      type: tool_webfetch
  - id: cc-read
    title: reads are fine
    text: Yes.
    verdict: yes
    matchers:
      platform: claude-code
      type: tool_read
  - id: kiro-no
    title: a kiro rule
    text: Never.
    verdict: no
    matchers:
      platform: kiro
      type: tool_bash
  - id: general-no
    title: for every helper
    text: Never.
    verdict: no
    matchers:
      input_command__contains: ["rm -rf"]
"""


class RulesCardTests(cs.CmdCase):
    def card(self, platform="claude-code", text=RULES):
        (self.root / "rules.yaml").write_text(text, encoding="utf-8")
        return gr.rules_card(self.root, platform)

    def test_the_rules_of_the_platform_are_counted_and_the_no_rules_are_named_in_file_order(self):
        lines = self.card()
        self.assertEqual(lines[0], "Rules in force for claude-code (rules.yaml): 1 No, 1 Ask me first, 1 Yes, and 1 general rules for "
                                   "every helper. No beats Ask me first, Ask me first beats Yes, and a call that no rule matches is "
                                   "Ask me first.")
        self.assertEqual(lines[1:], ["- No, cc-no-money: Claude Code never moves money"])

    def test_the_rules_of_another_platform_are_not_listed(self):
        self.assertNotIn("kiro-no", "\n".join(self.card()))
        self.assertIn("kiro-no", "\n".join(self.card("kiro")))

    def test_a_long_list_is_cut_and_the_rest_counted(self):
        many = "rules:\n" + "".join(
            f"  - id: n{i}\n    title: no number {i}\n    text: x\n    verdict: no\n    matchers:\n      platform: claude-code\n      type: tool_bash\n"
            for i in range(15))
        lines = self.card(text=many)
        self.assertEqual(len(lines), 1 + gr.CARD_MAX_NO + 1)
        self.assertEqual(lines[-1], "- and 3 more No rules")

    def test_a_rules_file_that_cannot_be_read_is_said(self):
        lines = self.card(text="rules: [")
        self.assertEqual(lines, ["Rules in force: rules.yaml could not be read, so every call you make is Ask me first."])
        (self.root / "rules.yaml").unlink()
        self.assertIn("could not be read", gr.rules_card(self.root, "kiro")[0])

    def test_a_long_title_is_cut_to_one_line_of_80_characters(self):
        text = RULES.replace("Claude Code never moves money", "x" * 200)
        self.assertEqual(self.card(text=text)[1], "- No, cc-no-money: " + "x" * 80)

    def test_the_card_names_no_path_of_the_helper_and_reads_only(self):
        before = sorted(p.name for p in self.root.iterdir())
        self.card()
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), before)


class TaskCardTests(unittest.TestCase):
    OWN = gp.own_files("G-0001", "T-01")

    def test_the_order_is_the_mode_the_scope_and_the_rules(self):
        lines = gr.task_card("builder", self.OWN, "enforcement: enforced", ["Rules in force: x."])
        self.assertEqual([l.split(":")[0] for l in lines], ["Task card (fixed words from umwayi; the gate and the scope check decide, not these lines)", "Mode", "Scope", "Rules in force"])

    def test_a_builder_scope_names_the_two_files_by_right_and_the_protected_list(self):
        scope = gr.task_card("builder", self.OWN, "m", [])[2]
        for name in self.OWN:
            self.assertIn(name, scope)
        for name in gp.PROTECTED:
            self.assertIn(name, scope)

    def test_a_tester_and_a_check_change_no_file(self):
        for role in ("tester", "check"):
            self.assertIn("you change no file", gr.task_card(role, self.OWN, "m", [])[2])

    def test_a_missing_mode_is_said_not_left_out(self):
        self.assertIn("Mode: enforcement: not stated. Enforcement is cooperative today and enforced where built.", gr.task_card("tester", (), "", []))


class PromptsStartWithTheCardTests(cs.CmdCase):
    def test_each_role_prompt_has_the_card_right_after_its_first_line(self):
        (self.root / "rules.yaml").write_text(RULES, encoding="utf-8")
        rules = gr.rules_card(self.root, "claude-code")
        prompts = {
            "builder": gr.builder_prompt(PACKET, "G-0001", "T-01", "umwayi/g-0001-t-01", "2026-11-23", "N", mode="enforcement: enforced", rules=rules),
            "tester": gr.tester_prompt(PACKET, "umwayi/g-0001-t-01", "a" * 40, "N", mode="enforcement: enforced", own=gp.own_files("G-0001", "T-01"), rules=rules),
            "check": gr.check_prompt(PACKET, "umwayi/g-0001-t-01", "a" * 40, 2, ((1, "pass", "Looked at it."),), "N",
                                     own=gp.own_files("G-0001", "T-01"), mode="enforcement: enforced", rules=rules)}
        for role, text in prompts.items():
            with self.subTest(role=role):
                lines = text.splitlines()
                self.assertTrue(lines[1].startswith("Task card (fixed words from umwayi"), lines[1])
                self.assertEqual(lines[2], "Mode: enforcement: enforced. Enforcement is cooperative today and enforced where built.")
                self.assertTrue(lines[3].startswith("Scope: "))
                self.assertTrue(lines[4].startswith("Rules in force for claude-code"))
                self.assertTrue(text.endswith("Nonce: N\n"))
                self.assertEqual(text.count("Nonce:"), 1)

    def test_planted_fault_a_card_at_the_end_would_not_begin_the_context(self):
        text = gr.builder_prompt(PACKET, "G-0001", "T-01", "b", "2026-11-23", "N", mode="enforcement: enforced")
        self.assertLess(text.index("Task card"), text.index("Task: Do the thing."))
        self.assertLess(text.index("Task card"), text.index("Read these files first:"))

    def test_the_real_run_gives_the_card_to_every_role(self):
        from unittest import mock
        seen = {}
        for name in ("builder_prompt", "tester_prompt", "check_prompt"):
            real = getattr(gr, name)

            def spy(*a, _n=name, _r=real, **kw):
                text = _r(*a, **kw)
                seen[_n] = text
                return text
            mock.patch.object(gr, name, spy).start()
        self.addCleanup(mock.patch.stopall)
        goal = self.g_approved()
        from tests.goal import runsupport as rs
        scripts = [{"steps": rs.builder_steps(goal, "T-01"), "spend": 3}, {"steps": rs.tester_steps(), "spend": 2},
                   {"steps": rs.check_steps(), "spend": 1}]
        self.assertEqual(self.call("run", goal, scripts=scripts), 0, self.err)
        self.assertEqual(sorted(seen), ["builder_prompt", "check_prompt", "tester_prompt"])
        for name, text in seen.items():
            with self.subTest(prompt=name):
                self.assertIn("\nTask card (fixed words from umwayi", text)
                self.assertIn("\nMode: enforcement:", text)
                self.assertIn("\nRules in force", text)


if __name__ == "__main__":
    unittest.main()
