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

from tools import pr_story

REPO = Path(__file__).resolve().parent.parent
FOLDER = REPO / "docs" / "stories"
KEYS = ("id", "title", "command", "prs", "built", "honesty", "analogy", "analogy_stops", "does_not", "owner_check", "words", "code", "scenes")
SCENE_KEYS = ("label", "chip", "tone", "caption")
TONES = ("yes", "ask", "no", "info")
CHIPS = {"yes": "Yes", "ask": "Ask me first", "no": "No", "info": "Info"}
BUILT = ("built", "partly", "planned")
MIN_WORDS = 100
FIRST_FOUR = ("broker", "fuel-gauge", "provenance", "sandbox-settings")


def prose(s):
    parts = [s["title"], s["honesty"], s["analogy"], s["analogy_stops"], *s["does_not"], *s["owner_check"]]
    for sc in s["scenes"]:
        parts += [sc["label"], sc["caption"]]
    return "\n".join(parts)


def problems(s, root=REPO):
    """Every rule, as a list of messages for one story dict. Empty means the story is good."""
    out = []
    if tuple(s) != KEYS:
        return [f"the keys are not {', '.join(KEYS)} in that order"]
    if not isinstance(s["id"], str) or not re.fullmatch(r"[a-z][a-z0-9-]{1,40}", s["id"]):
        out.append("the id is not a plain lower case word")
    if not isinstance(s["prs"], list) or not s["prs"] or not all(isinstance(n, int) and n > 0 for n in s["prs"]):
        out.append("prs is not a list of pull request numbers")
    if s["built"] not in BUILT:
        out.append("built is not built, partly or planned")
    for k in ("title", "command", "honesty", "analogy", "analogy_stops"):
        if not isinstance(s[k], str) or not s[k].strip():
            out.append(f"{k} is empty")
    for k in ("does_not", "owner_check", "words", "code"):
        if not isinstance(s[k], list) or not s[k] or not all(isinstance(x, str) and x.strip() for x in s[k]):
            out.append(f"{k} is not a list of lines")
    sc = s["scenes"]
    if not isinstance(sc, list) or len(sc) != 5:
        out.append("there are not five scenes")
    else:
        for i, x in enumerate(sc, 1):
            if not isinstance(x, dict) or tuple(x) != SCENE_KEYS:
                out.append(f"scene {i} does not have {', '.join(SCENE_KEYS)}")
            elif x["tone"] not in TONES or x["chip"] != CHIPS[x["tone"]] or not x["label"].strip() or not x["caption"].strip():
                out.append(f"scene {i} has a tone, a chip or a text that is wrong")
    if out:
        return out
    code = []
    for rel in s["code"]:
        p = (root / rel)
        if not (p.is_file() and p.resolve().is_relative_to(root.resolve())):
            out.append(f"the code file {rel} does not exist in the repository")
        else:
            code.append(p.read_text(encoding="utf-8"))
    for w in s["words"]:
        if not any(w in text for text in code):
            out.append(f"the word {w} is not in the code the story names")
    text = prose(s)
    if len(text.split()) < MIN_WORDS:
        out.append(f"the prose has {len(text.split())} words, under {MIN_WORDS}")
    if "—" in json.dumps(s, ensure_ascii=False):
        out.append("there is an em dash")
    fails, _ = pr_story.check("pull_request", text)
    out += [f"honesty: {f}" for f in fails]
    if s["built"] != "built" and not re.search(r"(?i)partly|not (yet )?(built|called)|nothing calls|planned", s["honesty"]):
        out.append("a story that is not fully built must say so in its honesty line")
    return out


def load_all():
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(FOLDER.glob("*.json"))}


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
