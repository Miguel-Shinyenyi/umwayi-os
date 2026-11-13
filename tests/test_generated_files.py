"""W21: the list of generated files (tools/generated_files.json), its strict reader and the regenerate hint that the
stale-file tests end their messages with. Standard library only."""
import copy
import json
import unittest
from pathlib import Path

from tools import generated_files as gf

REPO = Path(__file__).resolve().parents[1]
RAW = json.loads((REPO / "tools" / "generated_files.json").read_text(encoding="utf-8"))
CMD = {"argv": ["python", "-c", "pass"]}


def one(**extra):
    return {"version": 1, "files": [{"path": "docs/a.md", "regenerate": [CMD], "verify": [CMD], **extra}]}


class RealListTests(unittest.TestCase):
    def setUp(self):
        self.entries = gf.load()

    def test_the_real_list_loads_and_names_the_seven_files_in_this_order(self):
        self.assertEqual([e["path"] for e in self.entries],
                         ["docs/status-log.md", "docs/KNOWN-LIMITS.md", "tools/ci_map.json", "tools/ci_shards.json", "docs/testing.md",
                          "ui/dist/progress.html", "ui/dist/build.json"])

    def test_every_listed_file_exists(self):
        for e in self.entries:
            self.assertTrue((REPO / e["path"]).is_file(), e["path"])

    def test_every_command_is_the_one_the_task_names(self):
        by = {e["path"]: e for e in self.entries}
        docs = [["python", "-m", "umwayi", "goal", "docs", "build"]]
        self.assertEqual([c["argv"] for c in by["docs/status-log.md"]["regenerate"]], docs)
        self.assertEqual([c["argv"] for c in by["docs/KNOWN-LIMITS.md"]["verify"]], [["python", "-m", "umwayi", "goal", "docs", "check"]])
        self.assertEqual([c["argv"] for c in by["docs/testing.md"]["regenerate"]], [["python", "-m", "tools.ci_map", "table", "--write"]])
        self.assertEqual([c["argv"] for c in by["tools/ci_shards.json"]["regenerate"]], [["python", "-m", "tools.ci_shards", "assign-missing"]])
        self.assertEqual([c["argv"] for c in by["tools/ci_shards.json"]["verify"]], [["python", "-m", "tools.ci_shards", "check"]])
        self.assertEqual([(c["argv"], c["cwd"]) for c in by["ui/dist/progress.html"]["regenerate"]],
                         [(["npm", "ci", "--ignore-scripts"], "ui"), (["node", "build.mjs"], "ui")])
        self.assertEqual([c["argv"] for c in by["ui/dist/build.json"]["verify"]], [["python", "-m", "unittest", "tests.test_progress_page"]])

    def test_the_testing_md_entry_is_a_block_and_the_markers_are_in_the_file(self):
        block = next(e for e in self.entries if e["path"] == "docs/testing.md")["block"]
        text = (REPO / "docs" / "testing.md").read_text(encoding="utf-8")
        self.assertTrue(any(ln.startswith(block["begin"]) for ln in text.split("\n")))
        self.assertTrue(any(ln.startswith(block["end"]) for ln in text.split("\n")))

    def test_the_list_is_the_layout_the_file_has(self):
        self.assertEqual(sorted(RAW), ["files", "version"])


class StrictReaderTests(unittest.TestCase):
    def refused(self, data, word):
        with self.assertRaises(gf.ListError) as cm:
            gf.parse(data)
        self.assertIn(word, str(cm.exception))

    def test_a_good_minimal_list_parses(self):
        out = gf.parse(one())
        self.assertEqual((out[0]["path"], out[0]["writes"], out[0]["block"]), ("docs/a.md", [], None))

    def test_unknown_keys_are_refused_at_every_level(self):
        self.refused({**one(), "extra": 1}, "nothing else")
        self.refused(one(colour="red"), "does not know: colour")
        bad = one()
        bad["files"][0]["verify"] = [{"argv": ["python"], "shell": True}]
        self.refused(bad, "command")
        self.refused(one(block={"begin": "a", "end": "b", "x": "c"}), "block")

    def test_a_missing_key_and_a_wrong_version_are_refused(self):
        for key in ("path", "regenerate", "verify"):
            data = one()
            del data["files"][0][key]
            self.refused(data, key)
        self.refused({"version": 2, "files": []}, "version")

    def test_a_repeated_path_is_refused(self):
        data = one()
        data["files"].append(copy.deepcopy(data["files"][0]))
        self.refused(data, "listed twice")

    def test_paths_that_are_not_plain_relative_are_refused(self):
        for bad in ("", "/etc/passwd", "../x", "a/../b", "./a", "a/./b", "a//b", "a/", "a\\b", "C:/x", "a\0b", 5, None):
            data = one()
            data["files"][0]["path"] = bad
            self.refused(data, "plain relative path")
        for bad in ("../x", "/abs"):
            self.refused(one(writes=[bad]), "writes")
        data = one()
        data["files"][0]["regenerate"] = [{"argv": ["python"], "cwd": "../up"}]
        self.refused(data, "cwd")

    def test_a_command_that_starts_a_shell_is_refused(self):
        for shell in ("sh", "bash", "/bin/sh", "cmd.exe", "powershell"):
            data = one()
            data["files"][0]["regenerate"] = [{"argv": [shell, "-c", "echo hi"]}]
            self.refused(data, "shell")

    def test_a_bad_argv_is_refused(self):
        for argv in ([], [""], "python -c pass", [1], ["a", ""]):
            data = one()
            data["files"][0]["verify"] = [{"argv": argv}]
            self.refused(data, "argv")

    def test_an_unreadable_file_is_a_list_error(self):
        with self.assertRaises(gf.ListError):
            gf.load(REPO / "tools" / "no-such-list.json")


class HintTests(unittest.TestCase):
    def test_the_hint_is_the_exact_regenerate_command(self):
        self.assertEqual(gf.regenerate_hint("tools/ci_shards.json"), "To fix it, run: python -m tools.ci_shards assign-missing")
        self.assertEqual(gf.regenerate_hint("tools/ci_map.json"), "To fix it, run: python -m tools.ci_map update")
        self.assertEqual(gf.regenerate_hint("docs/testing.md"), "To fix it, run: python -m tools.ci_map table --write")
        self.assertEqual(gf.regenerate_hint("docs/status-log.md"), "To fix it, run: python -m umwayi goal docs build")
        self.assertEqual(gf.regenerate_hint("ui/dist/progress.html"),
                         "To fix it, run: (cd ui && npm ci --ignore-scripts && node build.mjs)")

    def test_the_message_ends_with_the_command(self):
        text = gf.stale_message("docs/KNOWN-LIMITS.md", ["first problem", "second problem"])
        self.assertEqual(text.split("\n"), ["first problem", "second problem", "To fix it, run: python -m umwayi goal docs build"])
        self.assertTrue(gf.stale_message("tools/ci_map.json", "one problem").endswith("python -m tools.ci_map update"))

    def test_an_unlisted_path_is_an_error_not_a_made_up_command(self):
        with self.assertRaises(gf.ListError):
            gf.regenerate_hint("README.md")

    def test_commands_in_different_folders_are_grouped_by_folder(self):
        entries = gf.parse({"version": 1, "files": [{"path": "a", "verify": [CMD], "regenerate": [
            {"argv": ["x", "1"]}, {"argv": ["y", "2"], "cwd": "d"}, {"argv": ["z", "a b"], "cwd": "d"}]}]})
        self.assertEqual(gf.command_text(entries[0]), "x 1 && (cd d && y 2 && z 'a b')")

    def test_every_listed_file_has_a_hint(self):
        for e in gf.load():
            self.assertTrue(gf.regenerate_hint(e["path"]).startswith("To fix it, run: "), e["path"])


if __name__ == "__main__":
    unittest.main()
