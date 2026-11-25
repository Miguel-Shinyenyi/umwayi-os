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


class GatesTests(unittest.TestCase):
    """`muse.gates`: the three gates before a run, in order, pure."""

    TODAY = "2026-11-25"
    BASE = "version: 1\n"
    PROVIDER = "providers:\n  muse:\n    cost_kind: free_credits\n    limit:\n      credits_uu: 10000\n"
    ACCEPT = "    acceptance:\n      accepted_free: true\n      date: 2026-11-23\n      amount_uu: 10000\n      source: owner\n"

    def units(self, public=True, provider=True, accepted=True):
        from umwayi import units
        text = self.BASE + ("public: true\n" if public else "") + (self.PROVIDER + (self.ACCEPT if accepted else "") if provider else "")
        u, problems = units.check_text(text, self.TODAY)
        self.assertEqual(problems, [])
        return u

    def reading(self, left=9000, date="2026-11-25"):
        from umwayi import credits
        return {"muse": credits.Reading(left, date)}

    def gate(self, u, readings):
        r = muse.gates(u, readings, self.TODAY)
        return None if r is None else r[:2]

    def test_everything_in_place_means_no_refusal(self):
        self.assertIsNone(self.gate(self.units(), self.reading()))

    def test_no_mark_is_private_repo_named_with_exit_2(self):
        self.assertEqual(self.gate(self.units(public=False), self.reading()), (2, "private_repo_named"))

    def test_no_provider_or_no_acceptance_asks_with_exit_3(self):
        self.assertEqual(self.gate(self.units(provider=False), self.reading()), (3, "provider_unknown"))
        self.assertEqual(self.gate(self.units(accepted=False), self.reading()), (3, "no_acceptance"))

    def test_no_reading_or_a_stale_one_asks_and_a_future_one_is_not_trusted(self):
        self.assertEqual(self.gate(self.units(), {}), (3, "use_unknown"))
        self.assertEqual(self.gate(self.units(), self.reading(date="2026-11-01")), (3, "use_unknown"))
        self.assertEqual(self.gate(self.units(), self.reading(date="2026-12-31")), (3, "use_unknown"))

    def test_the_stop_line_is_5_percent_of_the_amount_at_acceptance(self):
        self.assertEqual(self.gate(self.units(), self.reading(left=500)), (2, "credits_low"))
        self.assertIsNone(self.gate(self.units(), self.reading(left=501)))

    def test_the_order_is_mark_then_acceptance_then_stop_line(self):
        self.assertEqual(self.gate(self.units(public=False, provider=False), {}), (2, "private_repo_named"))
        self.assertEqual(self.gate(self.units(accepted=False), self.reading(left=1)), (3, "no_acceptance"))

    def test_every_refusal_has_a_text_with_its_word_and_a_next_step(self):
        for u, readings in ((self.units(public=False), {}), (self.units(provider=False), {}), (self.units(accepted=False), {}),
                            (self.units(), {}), (self.units(), self.reading(left=1))):
            code, reason, text = muse.gates(u, readings, self.TODAY)
            self.assertTrue(text.startswith(reason + ": "), text)
            self.assertIn(code, (2, 3))


if __name__ == "__main__":
    unittest.main()
