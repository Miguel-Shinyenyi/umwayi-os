"""U1 step 3: `umwayi stories list` and `export` (umwayi/stories.py), read only.

The export is one JSON document with the stories exactly as written. A file that is not well formed refuses the whole export (exit 64, the
file name and a fixed problem, never text of the file), so a page never shows half a folder. Nothing is written. Planted faults cover each
structural rule on a copy of a real story.
"""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from umwayi import stories as sc

REPO = Path(__file__).resolve().parent.parent
REAL = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((REPO / "docs" / "stories").glob("*.json"))}


def make_root(files):
    d = tempfile.TemporaryDirectory()
    root = Path(d.name)
    (root / "docs" / "stories").mkdir(parents=True)
    for name, data in files.items():
        (root / "docs" / "stories" / name).write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return d, root


class StructureTests(unittest.TestCase):
    def one(self, story, name="provenance.json"):
        d, root = make_root({name: story})
        self.addCleanup(d.cleanup)
        return sc.story_files(root)

    def good(self):
        return copy.deepcopy(REAL["provenance"])

    def test_the_real_stories_pass_the_structure_check_and_come_back_as_written(self):
        out = sc.story_files(REPO)
        self.assertEqual([s["id"] for s in out], sorted(REAL))
        self.assertEqual({s["id"]: s for s in out}, REAL)

    def test_planted_faults_each_refuses_with_the_file_name_and_never_the_text(self):
        def mutate(f):
            s = self.good()
            f(s)
            return s
        cases = {
            "a missing key": mutate(lambda s: s.pop("honesty")),
            "keys in another order": {k: self.good()[k] for k in reversed(list(self.good()))},
            "an id that is not the file name": mutate(lambda s: s.__setitem__("id", "other")),
            "a built state that is not one": mutate(lambda s: s.__setitem__("built", "done")),
            "four scenes": mutate(lambda s: s["scenes"].pop()),
            "a wrong tone": mutate(lambda s: s["scenes"][0].__setitem__("tone", "maybe")),
            "a chip that does not match its tone": mutate(lambda s: s["scenes"][1].__setitem__("chip", "Yes please")),
            "prs not numbers": mutate(lambda s: s.__setitem__("prs", ["184"])),
            "an empty title": mutate(lambda s: s.__setitem__("title", " ")),
            "words not a list": mutate(lambda s: s.__setitem__("words", "unchanged")),
        }
        for label, story in cases.items():
            with self.subTest(label):
                with self.assertRaises(sc.StoryError) as cm:
                    self.one(story)
                self.assertIn("docs/stories/provenance.json", str(cm.exception))
                self.assertNotIn(self.good()["analogy"][:30], str(cm.exception))

    def test_a_file_that_is_not_json_or_is_not_an_object_refuses(self):
        for bad in ("{", "[]", '"text"', ""):
            with self.subTest(bad=bad):
                with self.assertRaises(sc.StoryError):
                    self.one(bad)

    def test_no_folder_and_no_files_are_no_stories_and_other_files_are_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sc.story_files(d), [])
        d, root = make_root({"notes.txt": "x"})
        self.addCleanup(d.cleanup)
        self.assertEqual(sc.story_files(root), [])
        self.assertEqual(sc.list_lines([]), ["There are no stories in docs/stories."])


class OutputTests(unittest.TestCase):
    def test_the_export_is_one_json_document_with_the_note_the_count_and_the_stories(self):
        doc = json.loads(sc.export_document(sc.story_files(REPO)))
        self.assertEqual(list(doc), ["note", "count", "stories"])
        self.assertEqual(doc["count"], len(REAL))
        self.assertIn("The terminal stays the source of truth", doc["note"])
        self.assertEqual({s["id"]: s for s in doc["stories"]}, REAL)

    def test_the_list_shows_the_id_the_built_state_and_the_title(self):
        lines = sc.list_lines(sc.story_files(REPO))
        self.assertTrue(lines[0].startswith("broker"))
        self.assertIn("partly", [l for l in lines if l.startswith("fuel-gauge")][0])
        self.assertTrue(lines[-1].startswith(f"{len(REAL)} stories."))


class CommandTests(unittest.TestCase):
    def run_cmd(self, root, *args):
        return subprocess.run([sys.executable, "-m", "umwayi", "--root", str(root), "stories", *args], cwd=REPO, capture_output=True,
                              text=True, timeout=60)

    def test_the_real_commands_read_only_and_change_nothing(self):
        d, root = make_root({f"{k}.json": v for k, v in REAL.items()})
        self.addCleanup(d.cleanup)
        before = sorted((p.name, p.read_bytes()) for p in (root / "docs" / "stories").iterdir())
        p = self.run_cmd(root, "list")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("fuel-gauge", p.stdout)
        p = self.run_cmd(root, "export")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["count"], len(REAL))
        self.assertEqual(sorted((q.name, q.read_bytes()) for q in (root / "docs" / "stories").iterdir()), before)
        self.assertEqual(sorted(x.name for x in root.iterdir()), ["docs"])  # no logbook, no other file

    def test_a_bad_story_is_exit_64_with_nothing_on_stdout(self):
        bad = copy.deepcopy(REAL["broker"])
        bad["scenes"].pop()
        d, root = make_root({"broker.json": bad, "provenance.json": REAL["provenance"]})
        self.addCleanup(d.cleanup)
        for cmd in ("list", "export"):
            p = self.run_cmd(root, cmd)
            self.assertEqual(p.returncode, 64, p.stderr)
            self.assertEqual(p.stdout, "")
            self.assertIn("docs/stories/broker.json", p.stderr)

    def test_no_stories_folder_is_exit_0(self):
        with tempfile.TemporaryDirectory() as d:
            p = self.run_cmd(d, "list")
            self.assertEqual((p.returncode, p.stdout.strip()), (0, "There are no stories in docs/stories."))
            self.assertEqual(json.loads(self.run_cmd(d, "export").stdout)["count"], 0)


if __name__ == "__main__":
    unittest.main()
