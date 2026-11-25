"""U1 step 2: the story files of docs/stories (docs/stories-in-the-gui.md).

One file per story. The tests check what a panel will rely on: the exact keys, five scenes with a tone, a built state, every fixed word
present in the code the story names, prose of at least 100 words, no em dash and no overclaim (the honesty scan of tools/pr_story.py).
Planted faults on a copy of a real story show that each rule fails when it is broken.
"""
import copy
import json
import re
import unittest
from pathlib import Path

from tools.stories import FOLDER, load_all, problems

REPO = Path(__file__).resolve().parent.parent
FIRST_FOUR = ("broker", "fuel-gauge", "provenance", "sandbox-settings")


class RealStoriesTests(unittest.TestCase):
    def test_the_first_four_stories_exist_and_every_file_name_is_its_id(self):
        stories = load_all()
        self.assertEqual(tuple(sorted(stories)), FIRST_FOUR)
        for name, s in stories.items():
            self.assertEqual(s["id"], name)

    def test_every_story_passes_every_rule(self):
        for name, s in load_all().items():
            with self.subTest(story=name):
                self.assertEqual(problems(s), [])

    def test_the_fuel_gauge_says_that_nothing_calls_the_gate_yet(self):
        s = load_all()["fuel-gauge"]
        self.assertEqual(s["built"], "partly")
        self.assertIn("nothing calls", s["honesty"].lower())

    def test_the_fixed_words_are_the_ones_the_command_prints(self):
        want = {"fuel-gauge": {"provider_unknown", "no_acceptance", "paid_asks_every_goal", "accepted"},
                "provenance": {"unchanged", "structure", "changed", "unnamed"}}
        stories = load_all()
        for k, words in want.items():
            self.assertEqual(set(stories[k]["words"]), words)


class PlantedFaultTests(unittest.TestCase):
    def good(self):
        return copy.deepcopy(load_all()["provenance"])

    def test_the_copy_is_clean_before_any_plant(self):
        self.assertEqual(problems(self.good()), [])

    def test_a_word_the_code_does_not_print_fails(self):
        s = self.good()
        s["words"].append("a_word_no_code_prints")
        self.assertEqual(problems(s), ["the word a_word_no_code_prints is not in the code the story names"])

    def test_a_missing_code_file_fails(self):
        s = self.good()
        s["code"] = ["umwayi/no_such_file.py"]
        self.assertTrue(any("does not exist" in p for p in problems(s)))

    def test_four_scenes_or_a_wrong_tone_or_a_wrong_chip_fail(self):
        s = self.good()
        s["scenes"].pop()
        self.assertEqual(problems(s), ["there are not five scenes"])
        s = self.good()
        s["scenes"][0]["tone"] = "maybe"
        self.assertTrue(any("scene 1" in p for p in problems(s)))
        s = self.good()
        s["scenes"][1]["chip"] = "Yes please"
        self.assertTrue(any("scene 2" in p for p in problems(s)))

    def test_an_overclaim_in_any_prose_field_fails_the_honesty_scan(self):
        for phrase in ("The run is enforced by default.", "The helper is sandboxed by default.", "The helper is confined."):
            with self.subTest(phrase=phrase):
                s = self.good()
                s["scenes"][2]["caption"] = phrase
                self.assertTrue(any(p.startswith("honesty:") for p in problems(s)), phrase)

    def test_short_prose_an_em_dash_and_a_wrong_key_order_fail(self):
        s = self.good()
        for k in ("analogy", "analogy_stops"):
            s[k] = "Short."
        s["does_not"] = ["No."]
        s["owner_check"] = ["Look."]
        s["honesty"] = "Built."
        for sc in s["scenes"]:
            sc["caption"] = "Short."
        self.assertTrue(any("under 100" in p for p in problems(s)))
        s = self.good()
        s["analogy"] += " A pause—here."
        self.assertIn("there is an em dash", problems(s))
        s = self.good()
        s = {k: s[k] for k in reversed(list(s))}
        self.assertEqual(len(problems(s)), 1)

    def test_a_partly_built_story_that_does_not_say_so_fails(self):
        s = copy.deepcopy(load_all()["fuel-gauge"])
        s["honesty"] = "Built and tested. Cooperative today."
        self.assertEqual(problems(s), ["a story that is not fully built must say so in its honesty line"])


if __name__ == "__main__":
    unittest.main()
