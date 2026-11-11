"""Layer 10 part 8, task 10.43: an OpenCode agent in agents.yaml (requirement 10.R13.1 and 10.R13.2, design.md part 8).

Written before the code. Every test runs `python -m umwayi ... agent ...` as a real child process, with a spy
`opencode` first on PATH (the layer 10 fake, which records every call): the spy proves that validating, listing,
checking or refusing an OpenCode agent never starts a program. Only the table of platforms is read in process.

What 10.43 builds: `opencode` in the platform table (command word `opencode`, transport acp only), the keys
`provider` and `model` (required for OpenCode, refused for every other platform), and `agent run` and `agent login`
refused with 64. Gate checks (10.46) and the chat (10.48) are not built: `agent check` says not gated (exit 2) and
`agent chat` is still refused (64), and neither starts anything.
"""

import unittest

from umwayi import agents

from tests.agents.support import CLAUDE_AGENT, KIRO_AGENT, REPO, AgentCase

ROUTES = {  # provider -> a model of that provider (10.R13.6)
    "opencode": "opencode/big-pickle",
    "ollama": "ollama/qwen3-coder",
    "lmstudio": "lmstudio/openai/gpt-oss-20b",
    "vllm": "vllm/qwen3-coder-30b",
    "openai": "openai/gpt-5",
    "github-copilot": "github-copilot/gpt-4o",
}


def oc(extra: str = "", provider: str | None = "ollama", model: str | None = "ollama/qwen3-coder",
       transport: str | None = "acp", name: str = "o", platform: str = "opencode", command: str = "opencode",
       workdir: str = "{work}") -> str:
    """An agents file with one OpenCode agent. Lines: 1 agents, 2 name, 3 platform, 4 command, then the rest."""
    lines = ["agents:", f"  - name: {name}", f"    platform: {platform}", f"    command: {command}"]
    if transport is not None:
        lines.append(f"    transport: {transport}")
    lines.append(f"    workdir: {workdir}")
    if provider is not None:
        lines.append(f"    provider: {provider}")
    if model is not None:
        lines.append(f"    model: {model}")
    return "\n".join(lines) + "\n" + extra


def line_of(text: str, key: str) -> int:
    for n, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith(key + ":"):
            return n
    raise AssertionError(f"no line for {key}")


class OpenCodeCase(AgentCase):
    def setUp(self):
        super().setUp()
        self.fake("opencode")  # a spy: every call is recorded, and a test says what it expects
        self.fake("claude")
        self.fake("kiro-cli")
        (self.root / "inner").mkdir()

    def assert_nothing_ran(self):
        self.assertEqual(self.calls(), [], "a program was started")


class PlatformTableTests(unittest.TestCase):
    def test_opencode_is_in_the_fixed_table_with_acp_only(self):
        p = agents.PLATFORMS["opencode"]
        self.assertEqual(p.name, "opencode")
        self.assertEqual(p.commands, ("opencode",))
        self.assertEqual(p.transports, ("acp",))
        self.assertEqual(p.min_version, (2, 2, 3))  # OC14: the first release that honours every policy used
        self.assertEqual(p.version_flag, "--version")
        self.assertTrue((REPO / p.hook).is_file())
        self.assertEqual(p.hook, "adapters/stdio/hook.py")  # the plugin runs the layer 9 generic adapter

    def test_the_other_two_platforms_are_unchanged(self):
        self.assertEqual(sorted(agents.PLATFORMS), ["claude-code", "kiro", "opencode"])
        self.assertEqual(agents.PLATFORMS["claude-code"].transports, ("cli", "acp"))
        self.assertEqual(agents.PLATFORMS["kiro"].transports, ("cli", "acp"))
        self.assertEqual(agents.PLATFORMS["claude-code"].commands, ("claude",))
        self.assertEqual(agents.PLATFORMS["kiro"].commands, ("kiro-cli",))

    def test_the_keys_are_fixed(self):
        self.assertEqual(agents.KEYS, ("name", "platform", "command", "transport", "workdir", "kiro_agent",
                                       "trust_tools", "max_turns", "timeout_minutes", "provider", "model"))
        self.assertEqual(agents.REQUIRED, ("name", "platform", "command", "workdir"))

    def test_the_agent_record_has_provider_and_model_with_no_default(self):
        a = agents.Agent("k", "kiro", "kiro-cli", "acp", "/w")
        self.assertIsNone(a.provider)
        self.assertIsNone(a.model)


class ValidShapeTests(OpenCodeCase):
    def test_every_allowed_route_validates_and_lists(self):
        for provider, model in ROUTES.items():
            with self.subTest(provider=provider):
                self.write_agents(oc(provider=provider, model=model))
                r = self.umwayi("validate")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual(self.lines(r), ["ok: 1 agent(s): o (opencode, acp)"])
                r = self.umwayi("list")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual(self.lines(r)[0], f"o  opencode  acp  opencode  {self.work}")
                self.assertIn("1 agent(s). Nothing was started.", r.stdout)
        self.assert_nothing_ran()

    def test_a_provider_that_is_not_a_route_is_a_valid_agent_the_route_check_refuses_later(self):
        # OC16: the file checks the shape; whether a route is offered is decided at the start (10.46, exit 2)
        for provider in ("opencode-go", "openrouter", "anthropic", "together", "x.y_z-1"):
            with self.subTest(provider=provider):
                self.write_agents(oc(provider=provider, model=f"{provider}/some-model"))
                r = self.umwayi("validate")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_nothing_ran()

    def test_an_omitted_transport_is_acp_because_it_is_the_only_one(self):
        # OC17
        self.write_agents(oc(transport=None))
        r = self.umwayi("validate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.lines(r), ["ok: 1 agent(s): o (opencode, acp)"])
        self.assertEqual(self.lines(self.umwayi("list"))[0], f"o  opencode  acp  opencode  {self.work}")

    def test_the_other_platforms_still_default_to_cli(self):
        self.write_agents(CLAUDE_AGENT)
        self.assertEqual(self.lines(self.umwayi("validate")), ["ok: 1 agent(s): reviewer (claude-code, cli)"])

    def test_all_the_optional_fields_and_the_limits_of_model(self):
        long_model = "ollama/" + "a" * 120  # the id after the slash may be 120 characters
        long_provider = "p" * 40
        self.write_agents(oc("", provider="ollama", model=long_model)
                          + "    timeout_minutes: 720\n")
        r = self.umwayi("validate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.write_agents(oc(provider=long_provider, model=long_provider + "/m"))
        self.assertEqual(self.umwayi("validate").returncode, 0)
        for model in ("ollama/a:b", "ollama/a/b/c", "ollama/Qwen3-Coder:30B", "ollama/1", "ollama/a.b_c-d"):
            with self.subTest(model=model):
                self.write_agents(oc(model=model))
                r = self.umwayi("validate")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_three_platforms_in_one_file(self):
        text = CLAUDE_AGENT + KIRO_AGENT.replace("agents:\n", "").replace("{transport}", "acp") \
            + oc().replace("agents:\n", "")
        self.write_agents(text)
        r = self.umwayi("validate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.lines(r), ["ok: 3 agent(s): reviewer (claude-code, cli), helper (kiro, acp), "
                                         "o (opencode, acp)"])

    def test_validate_and_list_start_no_program(self):
        self.write_agents(oc())
        self.umwayi("validate")
        self.umwayi("list")
        self.assert_nothing_ran()


def rejected():
    base = oc()
    yield ("provider missing", oc(provider=None), "needs provider", 2)
    yield ("model missing", oc(model=None), "needs model", 2)
    yield ("both missing", oc(provider=None, model=None), "needs provider", 2)
    yield ("model of another provider", oc(provider="ollama", model="vllm/qwen3"),
           "model must start with the same provider", line_of(base, "model"))
    yield ("model without the provider part", oc(model="qwen3-coder"), "model must be provider/model-id",
           line_of(base, "model"))
    yield ("model with an empty id", oc(model="ollama/"), "model must be provider/model-id", line_of(base, "model"))
    yield ("model with an upper case provider part", oc(provider="ollama", model="Ollama/x"),
           "model must be provider/model-id", line_of(base, "model"))
    yield ("model id starting with a dash", oc(model="ollama/-x"), "model must be provider/model-id",
           line_of(base, "model"))
    yield ("model id starting with a dot", oc(model="ollama/.x"), "model must be provider/model-id",
           line_of(base, "model"))
    yield ("model id of 121 characters", oc(model="ollama/" + "a" * 121), "model must be provider/model-id",
           line_of(base, "model"))
    yield ("model with a space", oc(model='"ollama/a b"'), "model must be provider/model-id", line_of(base, "model"))
    yield ("model with a semicolon", oc(model='"ollama/a;b"'), "model must be provider/model-id",
           line_of(base, "model"))
    yield ("model with an env token", oc(model='"ollama/{env:HOME}"'), "model must be provider/model-id",
           line_of(base, "model"))
    yield ("model with a file token", oc(model='"ollama/{file:x}"'), "model must be provider/model-id",
           line_of(base, "model"))
    yield ("model with two slashes before the id", oc(model="ollama//x"), "model must be provider/model-id",
           line_of(base, "model"))
    yield ("model a number", oc(model="5"), "model must be provider/model-id", line_of(base, "model"))
    yield ("model a list", oc(model="[ollama/x]"), "model must be provider/model-id", line_of(base, "model"))
    yield ("provider with upper case", oc(provider="Ollama", model="Ollama/x"), "provider must be",
           line_of(base, "provider"))
    yield ("provider with a slash", oc(provider="a/b", model="a/b/c"), "provider must be", line_of(base, "provider"))
    yield ("provider with a space", oc(provider='"a b"', model='"a b/c"'), "provider must be",
           line_of(base, "provider"))
    yield ("provider of 41 characters", oc(provider="p" * 41, model="p" * 41 + "/m"), "provider must be",
           line_of(base, "provider"))
    yield ("provider starting with a dash", oc(provider="-a", model="-a/m"), "provider must be",
           line_of(base, "provider"))
    yield ("provider a list", oc(provider="[ollama]"), "provider must be", line_of(base, "provider"))
    yield ("provider true", oc(provider="true"), "provider must be", line_of(base, "provider"))
    yield ("provider empty", oc(provider="''"), "provider must be", line_of(base, "provider"))
    yield ("transport cli", oc(transport="cli"), "transport cli is not possible for opencode (only acp)",
           line_of(base, "transport"))
    yield ("transport http", oc(transport="http"), "transport must be cli or acp", line_of(base, "transport"))
    yield ("command is claude", oc(command="claude"), "allow list for opencode: opencode", 4)
    yield ("command is a path", oc(command="/usr/bin/opencode"), "command must be one word from the allow list", 4)
    yield ("command with a flag", oc(command='"opencode --auto"'), "command must be one word from the allow list", 4)
    yield ("kiro_agent for opencode", oc("    kiro_agent: x\n"), "kiro_agent is only for platform kiro",
           len(base.splitlines()) + 1)
    yield ("trust_tools for opencode", oc("    trust_tools: [read_file]\n"), "trust_tools is only for platform kiro",
           len(base.splitlines()) + 1)
    yield ("max_turns for opencode", oc("    max_turns: 5\n"), "max_turns is only for platform claude-code",
           len(base.splitlines()) + 1)
    yield ("unknown key for opencode", oc("    args: [--auto]\n"), "'args' is not allowed", len(base.splitlines()) + 1)
    yield ("base_url is not a key yet", oc("    base_url: http://127.0.0.1:8000/v1\n"), "'base_url' is not allowed",
           len(base.splitlines()) + 1)
    yield ("timeout 0", oc("    timeout_minutes: 0\n"), "timeout_minutes must be a whole number from 1 to 720",
           len(base.splitlines()) + 1)
    # provider and model on the other platforms
    yield ("provider for claude", CLAUDE_AGENT + "    provider: ollama\n", "provider is only for platform opencode", 7)
    yield ("model for claude", CLAUDE_AGENT + "    model: ollama/x\n", "model is only for platform opencode", 7)
    yield ("provider for kiro", KIRO_AGENT.replace("{transport}", "acp") + "    provider: ollama\n",
           "provider is only for platform opencode", 8)
    yield ("model for kiro", KIRO_AGENT.replace("{transport}", "cli") + "    model: ollama/x\n",
           "model is only for platform opencode", 8)
    yield ("provider and model for an unknown platform", oc(platform="codex", command="codex"),
           "platform must be one of: claude-code, kiro, opencode", 3)


REJECTED = list(rejected())


class RejectedTests(OpenCodeCase):
    def test_every_rejected_shape_gives_64_with_its_line(self):
        for label, text, words, line in REJECTED:
            with self.subTest(case=label):
                self.write_agents(text)
                r = self.umwayi("validate")
                self.assertEqual(r.returncode, 64, r.stdout + r.stderr)
                problems = [ln for ln in self.lines(r) if ln.startswith("problem: ")]
                self.assertTrue(problems, r.stdout)
                self.assertTrue(any(p.startswith(f"problem: line {line}:") and words in p for p in problems),
                                f"line {line} with {words!r} expected in {problems}")
                self.assertEqual(self.umwayi("list").returncode, 64)
        self.assert_nothing_ran()

    def test_a_provider_that_is_a_valid_id_but_differs_from_the_model_is_refused(self):
        self.write_agents(oc(provider="'5'", model="ollama/x"))
        r = self.umwayi("validate")
        self.assertEqual(r.returncode, 64, r.stdout)
        self.assertIn("model must start with the same provider", r.stdout)

    def test_a_bad_provider_does_not_also_report_a_mismatch(self):
        self.write_agents(oc(provider="Ollama", model="ollama/x"))
        r = self.umwayi("validate")
        problems = [ln for ln in self.lines(r) if ln.startswith("problem: ")]
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("provider must be", problems[0])

    def test_no_problem_text_holds_the_value_that_was_wrong(self):
        secret = "SECRET-PROVIDER-VALUE"
        self.write_agents(oc(provider=f'"{secret}"', model=f'"{secret}/m"'))
        r = self.umwayi("validate")
        self.assertEqual(r.returncode, 64)
        self.assertNotIn(secret, r.stdout + r.stderr)

    def test_every_problem_is_reported_not_only_the_first(self):
        self.write_agents(oc("    max_turns: 0\n", provider="Bad", model="x", transport="cli"))
        r = self.umwayi("validate")
        problems = [ln for ln in self.lines(r) if ln.startswith("problem: ")]
        self.assertGreaterEqual(len(problems), 4, problems)


class RefusedCommandTests(OpenCodeCase):
    """agent run and agent login are refused for OpenCode before anything else happens (10.R13.1)."""

    def setUp(self):
        super().setUp()
        self.write_agents(oc())

    def assert_refused(self, r, word):
        self.assertEqual(r.returncode, 64, r.stdout + r.stderr)
        text = r.stdout + r.stderr
        self.assertIn(f"{word}: only 'umwayi agent chat' is offered for OpenCode agents", text)
        self.assertIn("Nothing was started.", text)
        self.assert_nothing_ran()

    def test_agent_run_gives_64(self):
        self.assert_refused(self.umwayi("run", "o", "--prompt", "hello"), "agent run")

    def test_agent_login_gives_64(self):
        self.assert_refused(self.umwayi("login", "o"), "agent login")

    def test_a_rule_that_says_yes_does_not_change_it(self):
        self.write_rules("rules:\n  - id: all\n    title: t\n    text: t\n    verdict: yes\n    matchers:\n"
                         "      type: [agent_run, agent_login, agent_chat]\n      platform: opencode\n")
        self.assert_refused(self.umwayi("run", "o", "--prompt", "hello"), "agent run")
        self.assert_refused(self.umwayi("login", "o"), "agent login")

    def test_nothing_is_written(self):
        self.umwayi("run", "o", "--prompt", "hello")
        self.umwayi("login", "o")
        for name in ("LOGBOOK.md", "queue.md", ".umwayi"):
            self.assertFalse((self.root / name).exists(), name)

    def test_the_other_platforms_still_start_their_login_path(self):
        self.write_agents(CLAUDE_AGENT)
        r = self.umwayi("login", "reviewer")
        self.assertNotIn("OpenCode", r.stdout + r.stderr)  # claude cli: refused by LOGIN_ONLY, not by this rule


class ParsedRecordTests(unittest.TestCase):
    """What the parser hands on to the later tasks (10.44, 10.46, 10.48): provider and model on the record."""

    def parse(self, text):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="umwayi-oc-") as d:
            from pathlib import Path
            root, work = Path(d) / "root", Path(d) / "work"
            root.mkdir()
            work.mkdir()
            return agents.check_text(text.replace("{work}", str(work)), root)

    def test_an_opencode_agent_carries_its_provider_model_and_transport(self):
        [a], problems = self.parse(oc(provider="vllm", model="vllm/qwen3-coder-30b", transport=None))
        self.assertEqual(problems, [])
        self.assertEqual((a.platform, a.command, a.transport), ("opencode", "opencode", "acp"))
        self.assertEqual((a.provider, a.model), ("vllm", "vllm/qwen3-coder-30b"))
        self.assertEqual((a.kiro_agent, a.trust_tools, a.max_turns), (None, (), None))

    def test_the_other_platforms_carry_none(self):
        found, problems = self.parse(CLAUDE_AGENT + KIRO_AGENT.replace("agents:\n", "").replace("{transport}", "cli"))
        self.assertEqual(problems, [])
        for a in found:
            self.assertEqual((a.provider, a.model), (None, None))

    def test_an_invalid_file_gives_no_agents_at_all(self):
        found, problems = self.parse(oc(provider=None))
        self.assertIsNone(found)
        self.assertEqual(len(problems), 1)


class PatternTests(unittest.TestCase):
    """The two patterns of 10.R13.2, with the characters the YAML tests cannot carry (a hash, braces, a NUL)."""

    def test_provider(self):
        for good in ("ollama", "a", "0", "x.y_z-1", "p" * 40, "github-copilot"):
            self.assertTrue(agents._OPENCODE_PROVIDER.fullmatch(good), good)
        for bad in ("", "Ollama", "-a", ".a", "a/b", "a b", "a#", "a*", "p" * 41, "{env:X}", "a\nb", "a\x00", "\u00e9"):
            self.assertFalse(agents._OPENCODE_PROVIDER.fullmatch(bad), repr(bad))

    def test_model(self):
        for good in ("ollama/qwen3-coder", "lmstudio/openai/gpt-oss-20b", "a/b", "a/" + "b" * 120, "a/B:c.d_e-f/g"):
            self.assertTrue(agents._OPENCODE_MODEL.fullmatch(good), good)
        for bad in ("", "a", "a/", "/b", "A/b", "a/-b", "a/.b", "a/:b", "a//b", "a/b#c", "a/b*", "a/b c", "a/" + "b" * 121,
                    "a/{env:X}", "a/{file:/x}", "a/b\nc", "a/b\x00", "a/\u00e9", "ollama/x\n"):
            self.assertFalse(agents._OPENCODE_MODEL.fullmatch(bad), repr(bad))


class ChatAndCheckAreNotBuiltYetTests(OpenCodeCase):
    """The chat (10.48) and the gate checks (10.46) come later. Until then both fail closed and start nothing."""

    def setUp(self):
        super().setUp()
        self.write_agents(oc())

    def test_agent_chat_is_refused_with_64(self):
        r = self.umwayi("chat", "o")
        self.assertEqual(r.returncode, 64, r.stdout + r.stderr)
        self.assertIn("Nothing was started.", r.stdout + r.stderr)
        self.assert_nothing_ran()
        self.assertFalse((self.root / "LOGBOOK.md").exists())

    def test_agent_chat_is_refused_even_when_a_rule_says_yes(self):
        self.write_rules("rules:\n  - id: all\n    title: t\n    text: t\n    verdict: yes\n    matchers:\n"
                         "      type: agent_chat\n")
        r = self.umwayi("chat", "o")
        self.assertEqual(r.returncode, 64, r.stdout + r.stderr)
        self.assert_nothing_ran()

    def test_agent_check_says_not_gated_and_runs_no_program(self):
        r = self.umwayi("check", "o")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("Agent o: opencode, transport acp, workdir", r.stdout)
        self.assertIn("no: gate checks: ", r.stdout)
        self.assertIn("not built yet", r.stdout)
        self.assertIn("Not gated: agent o would be refused (exit 2). Nothing was started.", r.stdout)
        self.assert_nothing_ran()  # not even `opencode --version`

    def test_agent_check_writes_nothing(self):
        before = {p.name for p in self.root.iterdir()}
        self.umwayi("check", "o")
        self.assertEqual({p.name for p in self.root.iterdir()}, before)

    def test_the_other_platforms_still_check_as_before(self):
        self.write_agents(CLAUDE_AGENT)
        r = self.umwayi("check", "reviewer")
        self.assertIn("ok: command: claude found at", r.stdout)


if __name__ == "__main__":
    unittest.main()
