"""M2, first part: the pure Muse route (umwayi/muse.py), with fakes only. No `muse` is started and no network is used."""
import json
import tempfile
import unittest
from pathlib import Path

from umwayi import muse

GATE = "python3 -m umwayi check --muse-hook"


class CommandTests(unittest.TestCase):
    def test_the_step_cap_and_the_contributor_flag_are_always_there(self):
        argv = muse.command(30, "prompt.txt")
        self.assertEqual(argv[:2], ["muse", "exec"])
        self.assertEqual(argv[argv.index("--max-model-steps") + 1], "30")
        self.assertEqual(argv[argv.index("--contributor-mode") + 1], "off")
        self.assertIn("--json", argv)
        self.assertEqual(argv[argv.index("--prompt-file") + 1], "prompt.txt")

    def test_no_step_cap_or_a_bad_one_is_refused(self):
        for bad in (None, 0, -1, 1001, 2.5, True, "30"):
            with self.assertRaises(muse.MuseRefused) as c:
                muse.command(bad, "p.txt")
            self.assertEqual(c.exception.reason, "step_cap_missing")

    def test_yolo_and_disable_sandbox_are_refused_in_every_spelling(self):
        for flag in ("--yolo", "--disable-sandbox", "--YOLO", "--yolo=true", "--disable-sandbox=1"):
            with self.assertRaises(muse.MuseRefused) as c:
                muse.command(10, "p.txt", [flag])
            self.assertEqual(c.exception.reason, "yolo_refused", flag)

    def test_disable_approval_is_refused_until_the_sandbox_can_be_confirmed(self):
        with self.assertRaises(muse.MuseRefused) as c:
            muse.command(10, "p.txt", ["--disable-approval"])
        self.assertEqual(c.exception.reason, "sandbox_unconfirmed")

    def test_the_caller_cannot_set_the_step_cap_or_the_contributor_flag(self):
        for flag in ("--max-model-steps", "--contributor-mode=on", "--contributor-mode"):
            with self.assertRaises(ValueError):
                muse.command(10, "p.txt", [flag])

    def test_an_odd_argument_is_a_value_error_and_never_passed_on(self):
        for bad in ("; rm -rf /", "$(x)", "a\nb", "", "`x`"):
            with self.assertRaises(ValueError):
                muse.command(10, "p.txt", [bad])
        with self.assertRaises(ValueError):
            muse.command(10, "p;x.txt")

    def test_a_refusal_says_the_reason_and_the_next_step(self):
        try:
            muse.command(10, "p.txt", ["--yolo"])
        except muse.MuseRefused as e:
            self.assertTrue(str(e).startswith("yolo_refused: "))
            self.assertIn("Remove the flag", str(e))


class EnvTests(unittest.TestCase):
    def test_key_variables_are_removed_and_only_names_are_returned(self):
        env = {"PATH": "/usr/bin", "HOME": "/h", "META_API_KEY": "SECRET-VALUE-1", "MUSE_API_KEY": "SECRET-VALUE-2",
               "MUSE_TOKEN": "SECRET-VALUE-3", "META_SESSION_SECRET": "SECRET-VALUE-4", "MUSE_HOME": "/m", "METADATA": "x"}
        clean, removed = muse.child_env(env)
        self.assertEqual(removed, ["META_API_KEY", "META_SESSION_SECRET", "MUSE_API_KEY", "MUSE_TOKEN"])
        self.assertEqual(sorted(clean), ["HOME", "METADATA", "MUSE_HOME", "PATH"])
        self.assertNotIn("SECRET-VALUE", repr(removed))

    def test_the_input_is_not_changed(self):
        env = {"META_API_KEY": "x", "PATH": "/p"}
        muse.child_env(env)
        self.assertEqual(env, {"META_API_KEY": "x", "PATH": "/p"})

    def test_no_key_variables_removes_nothing(self):
        self.assertEqual(muse.child_env({"PATH": "/p"}), ({"PATH": "/p"}, []))


class HookTests(unittest.TestCase):
    def test_the_hook_text_has_one_pretooluse_command(self):
        doc = json.loads(muse.muse_hooks_text(GATE))
        (entry,) = doc["hooks"]["PreToolUse"]
        self.assertEqual(entry["hooks"], [{"type": "command", "command": GATE}])

    def test_a_gate_command_of_more_than_one_line_or_empty_is_refused(self):
        for bad in ("", "  ", "a\nb", None):
            with self.assertRaises(ValueError):
                muse.muse_hooks_text(bad)

    def test_the_check_passes_for_the_file_that_the_text_makes(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".muse").mkdir()
            (Path(d) / ".muse" / "hooks.json").write_text(muse.muse_hooks_text(GATE), encoding="utf-8")
            muse.check_hook_file(d, GATE)

    def test_a_missing_file_a_wrong_command_and_broken_files_are_hook_file_missing(self):
        with tempfile.TemporaryDirectory() as d:
            def refused():
                with self.assertRaises(muse.MuseRefused) as c:
                    muse.check_hook_file(d, GATE)
                self.assertEqual(c.exception.reason, "hook_file_missing")
            refused()  # no folder .muse at all
            (Path(d) / ".muse").mkdir()
            refused()  # no file
            hooks = Path(d) / ".muse" / "hooks.json"
            for text in (muse.muse_hooks_text("echo other"), "not json", "[]", '{"hooks": {"PreToolUse": 5}}', '{"hooks": {}}'):
                hooks.write_text(text, encoding="utf-8")
                refused()


class FactTests(unittest.TestCase):
    def test_only_an_exact_true_mark_is_public(self):
        muse.check_public(True)
        for bad in (None, False, "true", 1, "yes", [], {}):
            with self.assertRaises(muse.MuseRefused) as c:
                muse.check_public(bad)
            self.assertEqual(c.exception.reason, "private_repo_named")

    def test_muse_missing_when_the_path_has_none(self):
        muse.check_on_path(lambda name: "/usr/local/bin/muse")
        with self.assertRaises(muse.MuseRefused) as c:
            muse.check_on_path(lambda name: None)
        self.assertEqual(c.exception.reason, "muse_missing")


class BoundaryTests(unittest.TestCase):
    def test_this_module_starts_no_process_and_uses_no_network(self):
        src = (Path(__file__).resolve().parents[1] / "umwayi" / "muse.py").read_text(encoding="utf-8")
        for word in ("subprocess", "Popen", "os.system", "os.exec", "socket", "urllib", "requests"):
            self.assertNotIn(word, src, word)

    def test_only_agents_py_calls_it_and_only_for_the_checks_yet(self):
        import re
        root = Path(__file__).resolve().parents[1]
        pat = re.compile(r"from umwayi import[^\n]*\bmuse\b|umwayi\.muse\b|import muse\b")
        callers = [p.name for p in (root / "umwayi").glob("*.py") if p.name != "muse.py" and pat.search(p.read_text(encoding="utf-8"))]
        self.assertEqual(callers, ["agents.py"])  # step 1 of M2 part 2: agents.py checks a Muse agent; no start calls it (a later step)

    def test_a_built_command_never_carries_a_forbidden_flag(self):
        argv = muse.command(10, "p.txt")
        for flag in ("--yolo", "--disable-sandbox", "--disable-approval"):
            self.assertNotIn(flag, argv)


if __name__ == "__main__":
    unittest.main()
