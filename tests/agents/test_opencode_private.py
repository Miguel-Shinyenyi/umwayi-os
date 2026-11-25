"""G-0076: an OpenCode run over the free route needs the owner's public mark (`public: true` in units.yaml), else `private_repo_named` and nothing starts.
A local provider (the default of these tests, ollama) is never refused for this. Real child processes with the fake `opencode acp`; no real OpenCode is run."""
import unittest

from umwayi import agents

from tests.agents.test_agents_opencode_run import RunCase

WORD = "private_repo_named"


class RouteTests(unittest.TestCase):
    def test_only_the_signed_out_free_tier_is_a_free_route(self):
        self.assertTrue(agents.opencode_route_is_free("opencode"))
        for other in ("ollama", "lmstudio", "vllm", "opencode-go", "", None, 5, "OPENCODE"):
            self.assertFalse(agents.opencode_route_is_free(other), other)

    def test_the_word_is_the_one_of_the_muse_route(self):
        self.assertEqual(agents.PRIVATE_REPO_NAMED, "private_repo_named")


class FreeRouteRunTests(RunCase):
    def setUp(self):
        super().setUp()
        self.write_agent(provider="opencode", model="opencode/big-pickle")

    def test_without_the_mark_a_free_route_run_is_refused_and_nothing_starts(self):
        r = self.run_run("Say hello.")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(WORD, r.stdout)
        self.assertIn("public: true", r.stdout)
        self.assertEqual(self.prompts(), [])  # no prompt was sent
        self.assertEqual(self.new_sessions(), [])  # and no session was opened

    def test_the_refusal_is_in_the_logbook_with_the_word(self):
        self.run_run("Say hello.")
        self.assertIn(f"Refused agent o: {WORD}", self.log_text())

    def test_a_text_that_only_looks_like_the_mark_does_not_count(self):
        units = self.root / "units.yaml"
        units.write_text(units.read_text(encoding="utf-8") + "public: \"true\"\n", encoding="utf-8")
        r = self.run_run("Say hello.")
        self.assertEqual(r.returncode, 64, r.stdout + r.stderr)  # units.yaml is not valid: nothing is started
        self.assertEqual(self.prompts(), [])

    def test_with_the_mark_the_refusal_is_gone(self):
        units = self.root / "units.yaml"
        units.write_text(units.read_text(encoding="utf-8") + "public: true\n", encoding="utf-8")
        r = self.run_run("Say hello.")
        self.assertNotIn(WORD, r.stdout + r.stderr)


class LocalRouteTests(RunCase):
    def test_a_local_provider_is_never_refused_for_the_mark(self):
        r = self.run_run("Say hello.")  # the default agent of these tests is ollama, a local provider
        self.assertNotIn(WORD, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
