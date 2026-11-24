"""L8, the script part: tools/story_video.py turns a story file into the script of a concept video and a manifest line.

What is checked: the script of each real story has five scenes of four seconds, declares AI use, costs 0 units, says cooperative today, says
when a story is not fully built, and carries the words of the code; a story that breaks a rule or says enforced, sandboxed or confined on
screen is refused; the command writes only a new file; the manifest line has the fields of the pack. It renders nothing.
"""
import copy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools import story_video as sv
from tools import stories

REPO = Path(__file__).resolve().parent.parent
ALL = stories.load_all()


class ScriptTests(unittest.TestCase):
    def test_every_real_story_gives_a_script_with_the_five_scenes_and_the_fixed_lines(self):
        for name, s in ALL.items():
            with self.subTest(story=name):
                text = sv.script(s)
                lines = text.split("\n")
                self.assertTrue(lines[0].startswith(f"SCRIPT: umwayi-story-{name}.mp4 (9:16, 1080x1920, 20 s, 5 scenes of 4 s, 30 fps)"))
                scenes = [l for l in lines if l.startswith("Scene ")]
                self.assertEqual(len(scenes), 5)
                self.assertTrue(scenes[0].startswith("Scene 1 (0 to 4 s):") and scenes[4].startswith("Scene 5 (16 to 20 s):"))
                self.assertIn('AI use is declared on screen in every frame ("Made with AI")', text)
                self.assertIn("Video cost: 0 units (local render, no paid credits)", text)
                self.assertIn("Footer: Made with AI. Cooperative today.", text)
                self.assertIn("Posting is the owner's act.", text)
                for w in s["words"]:
                    self.assertIn(w, text)
                self.assertNotIn("—", text)

    def test_a_story_that_is_not_fully_built_says_so_in_the_footer(self):
        self.assertIn("Not fully built: partly built.", sv.script(ALL["fuel-gauge"]))
        self.assertNotIn("Not fully built", sv.script(ALL["provenance"]))
        self.assertIn("Footer: Made with AI. Cooperative today. Built. PR 184.", sv.script(ALL["provenance"]))

    def test_the_words_on_the_screen_of_the_real_scripts_never_say_the_banned_words(self):
        for name, s in ALL.items():
            on_screen = "\n".join(l for l in sv.script(s).split("\n") if l.startswith("Scene "))
            self.assertIsNone(sv.BANNED.search(on_screen), name)

    def test_a_chip_for_info_is_not_repeated_and_the_others_carry_their_words(self):
        text = sv.script(ALL["fuel-gauge"])
        self.assertIn("Chip: info. Caption:", text)
        self.assertIn("Chip: ask: Ask me first.", text)
        self.assertIn("Chip: yes: Yes.", text)

    def test_the_filename_is_used_in_the_script_and_the_manifest(self):
        self.assertIn("SCRIPT: umwayi-concept-21-the-gauge.mp4", sv.script(ALL["fuel-gauge"], "umwayi-concept-21-the-gauge.mp4"))
        self.assertEqual(sv.manifest_line(ALL["fuel-gauge"], "umwayi-concept-21-the-gauge.mp4"),
                         "| umwayi-concept-21-the-gauge.mp4 | docs/stories/fuel-gauge.json | 215, 221 | partly | 0 units | made with AI | posted: no |")


class RefusalTests(unittest.TestCase):
    def good(self):
        return copy.deepcopy(ALL["provenance"])

    def test_planted_fault_a_scene_that_says_enforced_sandboxed_or_confined_is_refused(self):
        for word in ("enforced", "sandboxed", "confined", "Enforced"):
            for field in ("caption", "label"):
                with self.subTest(word=word, field=field):
                    s = self.good()
                    s["scenes"][1][field] = f"The helper is {word} now"
                    with self.assertRaises(sv.Refused):
                        sv.script(s)
                    with self.assertRaises(sv.Refused):
                        sv.manifest_line(s)

    def test_a_story_that_breaks_a_rule_is_refused_with_a_fixed_reason_and_no_text_of_the_story(self):
        s = self.good()
        s["scenes"].pop()
        with self.assertRaises(sv.Refused) as cm:
            sv.script(s)
        self.assertIn("breaks a rule of tools/stories.py", str(cm.exception))
        self.assertNotIn(s["title"], str(cm.exception))
        s = self.good()
        s["words"].append("a_word_no_code_prints")
        with self.assertRaises(sv.Refused):
            sv.script(s)

    def test_the_word_sandbox_alone_is_not_banned(self):
        s = copy.deepcopy(ALL["sandbox-settings"])
        self.assertIn("sandbox", " ".join(sc["caption"] for sc in s["scenes"]).lower())
        self.assertTrue(sv.script(s))


class CommandTests(unittest.TestCase):
    def run_cmd(self, *args):
        return subprocess.run([sys.executable, "-m", "tools.story_video", *args], cwd=REPO, capture_output=True, text=True, timeout=60)

    def test_the_script_goes_to_stdout_and_nothing_is_written(self):
        p = self.run_cmd("broker")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(p.stdout.startswith("SCRIPT: umwayi-story-broker.mp4"))
        p = self.run_cmd("broker", "--manifest", "--filename", "umwayi-concept-18.mp4")
        self.assertEqual((p.returncode, p.stdout.strip()),
                         (0, "| umwayi-concept-18.mp4 | docs/stories/broker.json | 185, 186 | built | 0 units | made with AI | posted: no |"))

    def test_out_writes_a_new_file_and_never_overwrites_one(self):
        with tempfile.TemporaryDirectory() as d:
            out = str(Path(d) / "script.txt")
            self.assertEqual(self.run_cmd("provenance", "--out", out).returncode, 0)
            first = Path(out).read_text(encoding="utf-8")
            self.assertTrue(first.startswith("SCRIPT: "))
            p = self.run_cmd("broker", "--out", out)
            self.assertEqual(p.returncode, 64)
            self.assertEqual(Path(out).read_text(encoding="utf-8"), first)

    def test_usage_and_an_unknown_story_are_64(self):
        self.assertEqual(self.run_cmd().returncode, 64)
        self.assertEqual(self.run_cmd("nobody").returncode, 64)
        self.assertEqual(self.run_cmd("broker", "--filename", "../x.mp4").returncode, 64)
        self.assertEqual(self.run_cmd("broker", "--bogus").returncode, 64)


if __name__ == "__main__":
    unittest.main()
