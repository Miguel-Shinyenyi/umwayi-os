"""W78 step 2 (W41 A, W68 option 3): a start under a mode file that says `enforced` passes an allow list, the owner's
`env_keep` names and a run marker. A start with no mode file (today's default) and a cooperative one keep the old environment
and get no marker: the default reads as enforced, but no part of enforced is built yet, so it is not applied to a start.

  * `enforced_env`: the allow list of names, each only if set, plus the names of `env_keep`. A planted secret of any kind
    (a cloud key, a token, NODE_OPTIONS, PYTHONPATH, a billing credential) is not passed. A name that umwayi never passes
    is not passed even if `env_keep` lists it, and `agents.yaml` refuses it (exit 64).
  * `with_run_marker`: UMWAYI_RUN=<run id>, made by umwayi. A planted UMWAYI_RUN is replaced or removed.
  * `enforce.mode_of`: a missing mode file, an expired date and a file that cannot be read are all `enforced`.
    `enforce.explicit_mode_of` and `agents.scrub_applies`: no mode file is None and no scrub; a file that says enforced, or
    cannot be read, is the scrub.
  * Real runs (`agent run` as a child process with the fake agent): with a mode file that says `enforced` the started program
    has the allow list, the kept name and the marker (the run id of the budget entry). With no mode file and with a
    `cooperative` agent it keeps KEEP_ME and every other name of today's environment and gets no UMWAYI_RUN.

Each rule has a planted fault.
"""
import datetime
import re
import subprocess
import sys
import unittest
from unittest import mock

from tests.agents.support import RULES, AgentCase
from umwayi import agents, enforce

OWNER = {"HOME": "/home/me", "PATH": "/usr/bin:/bin", "USER": "me", "LANG": "C.UTF-8", "TERM": "xterm",
         "CLAUDE_CONFIG_DIR": "/home/me/.claude", "HTTPS_PROXY": "http://proxy.example:3128",
         # planted: none of these may reach a helper unless the owner lists it, and some never
         "GH_TOKEN": "ghp_PLANTED", "AWS_SECRET_ACCESS_KEY": "aws-PLANTED", "SENTRY_AUTH_TOKEN": "sentry-PLANTED",
         "S78_SECRET_TOKEN": "s78-PLANTED", "NODE_OPTIONS": "--require /tmp/evil.js", "PYTHONPATH": "/tmp/evil",
         "ANTHROPIC_API_KEY": "sk-PLANTED", "KIRO_API_KEY": "kiro-PLANTED", "SSH_AUTH_SOCK": "/tmp/agent.1",
         "OTEL_EXPORTER_OTLP_ENDPOINT": "http://evil.example", "UMWAYI_RUN": "planted-run", "S78_KEEP": "kept-value"}
PLANTED = ("GH_TOKEN", "AWS_SECRET_ACCESS_KEY", "SENTRY_AUTH_TOKEN", "S78_SECRET_TOKEN", "NODE_OPTIONS", "PYTHONPATH",
           "ANTHROPIC_API_KEY", "KIRO_API_KEY", "SSH_AUTH_SOCK", "OTEL_EXPORTER_OTLP_ENDPOINT", "S78_KEEP")


def agent(platform="claude-code", keep=()):
    command = "claude" if platform == "claude-code" else "kiro-cli"
    return agents.Agent("reviewer", platform, command, "cli", "/w", env_keep=tuple(keep))


class EnforcedEnvTests(unittest.TestCase):
    def test_no_planted_name_is_passed_and_the_allow_list_is(self):
        for platform in ("claude-code", "kiro"):
            env = agents.enforced_env(dict(OWNER), agent(platform))
            with self.subTest(platform=platform):
                self.assertEqual(sorted(set(PLANTED) & set(env)), [])
                for name in ("HOME", "PATH", "USER", "LANG", "TERM", "HTTPS_PROXY"):
                    self.assertEqual(env[name], OWNER[name])

    def test_the_name_the_supervisor_sets_for_its_builder_and_tester_passes(self):
        """The first real goal run failed with readonly_role_changed_tree: the allow list dropped PYTHONDONTWRITEBYTECODE, so the
        tester's Python wrote a __pycache__ into the worktree. The supervisor sets it (goalrun.run_child) and it is not a secret."""
        for platform in ("claude-code", "kiro"):
            env = agents.enforced_env(dict(OWNER, PYTHONDONTWRITEBYTECODE="1"), agent(platform))
            self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertEqual(agents.SUPERVISOR_ENV, ("PYTHONDONTWRITEBYTECODE",))

    def test_planted_fault_an_allow_list_without_the_supervisors_name(self):
        without = tuple(n for n in agents.enforced_names("claude-code") if n not in agents.SUPERVISOR_ENV)
        with mock.patch.object(agents, "enforced_names", lambda platform: without):
            env = agents.enforced_env(dict(OWNER, PYTHONDONTWRITEBYTECODE="1"), agent())
        self.assertNotIn("PYTHONDONTWRITEBYTECODE", env)  # what the first real run hit

    def test_claude_config_dir_is_claude_codes_own(self):
        self.assertIn("CLAUDE_CONFIG_DIR", agents.enforced_env(dict(OWNER), agent("claude-code")))
        self.assertNotIn("CLAUDE_CONFIG_DIR", agents.enforced_env(dict(OWNER), agent("kiro")))

    def test_planted_fault_a_deny_list_builder_passes_the_planted_names(self):
        with mock.patch.object(agents, "enforced_env", lambda environ, a: agents.claude_env(environ)):
            got = set(PLANTED) & set(agents.enforced_env(dict(OWNER), agent()))
        self.assertTrue({"GH_TOKEN", "AWS_SECRET_ACCESS_KEY", "S78_SECRET_TOKEN", "NODE_OPTIONS"} <= got, got)

    def test_env_keep_passes_a_listed_name_only_if_it_is_set(self):
        env = agents.enforced_env(dict(OWNER), agent(keep=("S78_KEEP", "NOT_SET_ANYWHERE")))
        self.assertEqual(env["S78_KEEP"], "kept-value")
        self.assertNotIn("NOT_SET_ANYWHERE", env)
        self.assertNotIn("GH_TOKEN", env)  # a name that is not listed stays out

    def test_a_name_umwayi_never_passes_is_not_passed_even_if_env_keep_lists_it(self):
        never = ("ANTHROPIC_API_KEY", "KIRO_API_KEY", "SSH_AUTH_SOCK", "OTEL_EXPORTER_OTLP_ENDPOINT", "UMWAYI_RUN")
        env = agents.enforced_env(dict(OWNER), agent(keep=never))
        self.assertEqual(sorted(set(never) & set(env)), [])

    def test_planted_fault_env_keep_read_as_values(self):
        """env_keep holds names. A value written into the list is a plain name that is never set, so it passes nothing."""
        env = agents.enforced_env(dict(OWNER), agent(keep=("ghp_PLANTED",)))
        self.assertNotIn("ghp_PLANTED", env)
        self.assertNotIn("ghp_PLANTED", env.values())

    def test_the_owners_environment_is_not_changed(self):
        env = dict(OWNER)
        agents.enforced_env(env, agent(keep=("S78_KEEP",)))
        self.assertEqual(env, OWNER)

    def test_the_other_allow_lists_pass_none_of_the_planted_names_either(self):
        for build in (agents.child_env, lambda e: agents.opencode_env(e, "{}")):
            self.assertEqual(sorted(set(PLANTED) & set(build(dict(OWNER)))), [])


class RunMarkerTests(unittest.TestCase):
    def test_the_marker_is_the_run_id(self):
        self.assertEqual(agents.with_run_marker({"A": "1"}, "0123456789abcdef"), {"A": "1", "UMWAYI_RUN": "0123456789abcdef"})

    def test_a_planted_marker_is_replaced_or_removed(self):
        self.assertEqual(agents.with_run_marker({"UMWAYI_RUN": "planted"}, "abc")["UMWAYI_RUN"], "abc")
        self.assertNotIn("UMWAYI_RUN", agents.with_run_marker({"UMWAYI_RUN": "planted"}, None))
        self.assertNotIn("UMWAYI_RUN", agents.with_run_marker({"UMWAYI_RUN": "planted"}, ""))


class ParseTests(unittest.TestCase):
    """`env_keep` in agents.yaml: names, never values, a fixed never-keep list, at most 32."""

    def check(self, tail):
        text = ("agents:\n  - name: reviewer\n    platform: claude-code\n    command: claude\n    workdir: /tmp\n" + tail)
        return agents.check_text(text, "/nonexistent-root")

    def test_a_good_list_is_read(self):
        found, problems = self.check("    env_keep: [S78_KEEP, GH_HOST]\n")
        self.assertEqual([p.render() for p in problems if "workdir" not in p.message and "env_keep" in p.message], [])
        if found is not None:
            self.assertEqual(found[0].env_keep, ("S78_KEEP", "GH_HOST"))

    def messages(self, tail):
        return [p.message for p in self.check(tail)[1] if "env_keep" in p.message]

    def test_a_bad_list_is_a_config_problem_that_names_the_entry_and_never_a_value(self):
        cases = {
            "    env_keep: GH_HOST\n": "must be a list",
            "    env_keep: [A, A]\n": "twice",
            "    env_keep: [\"bad name\"]\n": "not a plain name",
            "    env_keep: [1abc]\n": "not a plain name",
            "    env_keep: [SSH_AUTH_SOCK]\n": "never passes",
            "    env_keep: [ANTHROPIC_API_KEY]\n": "never passes",
            "    env_keep: [KIRO_API_KEY]\n": "never passes",
            "    env_keep: [UMWAYI_RUN]\n": "never passes",
            "    env_keep: [UMWAYI_ANYTHING]\n": "never passes",
            "    env_keep: [OTEL_EXPORTER_OTLP_ENDPOINT]\n": "never passes",
            "    env_keep: [OPENCODE_CONFIG_CONTENT]\n": "never passes",
            "    env_keep: [" + ", ".join(f"N{i}" for i in range(33)) + "]\n": "at most 32",
        }
        for tail, word in cases.items():
            with self.subTest(tail=tail[:40]):
                got = self.messages(tail)
                self.assertTrue(got and word in got[0], got)

    def test_planted_fault_a_never_keep_name_that_is_accepted(self):
        with mock.patch.object(agents, "keep_problem", lambda name: None):
            self.assertEqual(self.messages("    env_keep: [SSH_AUTH_SOCK]\n"), [])

    def test_no_env_keep_means_an_empty_tuple(self):
        found, _ = self.check("")
        if found is not None:
            self.assertEqual(found[0].env_keep, ())


class ModeOfTests(unittest.TestCase):
    TODAY = "2026-11-22"

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory(prefix="umwayi-modeof-")
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name

    def write(self, text):
        import os
        os.makedirs(self.root + "/.umwayi", exist_ok=True)
        with open(self.root + "/.umwayi/enforcement.yaml", "w", encoding="utf-8") as f:
            f.write(text)

    def mode(self, agent="reviewer"):
        return enforce.mode_of(self.root, agent, today=self.TODAY)

    def test_a_missing_file_is_enforced_for_the_mode_but_not_for_the_scrub(self):
        self.assertEqual(self.mode(), enforce.ENFORCED)
        self.assertIsNone(enforce.explicit_mode_of(self.root, "reviewer", today=self.TODAY))
        self.assertFalse(agents.scrub_applies(self.root, "reviewer", self.TODAY))

    def test_planted_fault_the_default_read_as_a_scrub(self):
        with mock.patch.object(enforce, "explicit_mode_of", lambda root, agent=None, goal=None, today=None: enforce.mode_of(root, agent, goal, today)):
            self.assertTrue(agents.scrub_applies(self.root, "reviewer", self.TODAY))  # what the old tests must never see

    def test_a_file_that_says_enforced_is_the_scrub(self):
        self.write("enforcement: enforced\n")
        self.assertEqual(enforce.explicit_mode_of(self.root, "reviewer", today=self.TODAY), enforce.ENFORCED)
        self.assertTrue(agents.scrub_applies(self.root, "reviewer", self.TODAY))

    def test_a_cooperative_agent_is_cooperative_until_its_date_and_enforced_after(self):
        self.write("enforcement: enforced\nagents:\n  reviewer:\n    enforcement: cooperative\n    until: 2026-11-25\n")
        self.assertEqual(self.mode(), enforce.COOPERATIVE)
        self.assertFalse(agents.scrub_applies(self.root, "reviewer", self.TODAY))
        self.assertTrue(agents.scrub_applies(self.root, "helper", self.TODAY))  # another agent is not relaxed
        self.assertTrue(agents.scrub_applies(self.root, "reviewer", "2026-11-26"))  # after the date it is enforced again

    def test_a_file_that_cannot_be_read_is_enforced_never_cooperative(self):
        for text in ("a: [\n", "enforcement: sometimes\n", "enforcement: cooperative\n", "- a list\n"):
            self.write(text)
            with self.subTest(text=text):
                self.assertEqual(self.mode(), enforce.ENFORCED)
                self.assertTrue(agents.scrub_applies(self.root, "reviewer", self.TODAY))

    def test_planted_fault_an_error_read_as_cooperative(self):
        self.write("a: [\n")
        with mock.patch.object(enforce, "read", side_effect=OSError("planted")):
            self.assertEqual(self.mode(), enforce.ENFORCED)


class RealRunTests(AgentCase):
    """`umwayi agent run` as a real child process, with the fake agent recording what it was started with."""

    FAKES = "FAKE_LOG, FAKE_SCRIPT, FAKE_PLANT, FAKE_KIRO_STATE, FAKE_CLAUDE_AUTH, FAKE_CLAUDE_AUTH_EXIT"

    def setUp(self):
        super().setUp()
        self.fake("claude")
        self.fake("kiro-cli")
        self.write_rules(RULES.replace("agent: [reviewer, slow, stubborn, quick]", "agent: [reviewer, helper]"))
        self.write_agents("agents:\n"
                          "  - name: reviewer\n    platform: claude-code\n    command: claude\n    workdir: {work}\n"
                          f"    env_keep: [S78_KEEP, {self.FAKES}]\n"
                          "  - name: helper\n    platform: kiro\n    command: kiro-cli\n    workdir: {work}\n"
                          f"    trust_tools: [read_file]\n    env_keep: [{self.FAKES}]\n")
        self.kiro_hook_file(command=self.kiro_command(python=sys.executable))
        self.roomy_budget()
        self.fake_sandbox_tools()  # W41 B1: an enforced Claude Code start needs bwrap and socat on Linux

    def mode_file(self, text):
        (self.root / ".umwayi").mkdir(exist_ok=True)
        (self.root / ".umwayi" / "enforcement.yaml").write_text(text, encoding="utf-8")

    def enforced(self):
        self.mode_file("enforcement: enforced\n")

    def cooperative(self, name):
        until = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
        self.mode_file(f"enforcement: enforced\nagents:\n  {name}:\n    enforcement: cooperative\n    until: {until}\n")

    def run_one(self, name, extra_env=None):
        planted = {k: v for k, v in OWNER.items() if k in PLANTED and k not in ("PYTHONPATH", "UMWAYI_RUN")}
        extra = dict(self.script({"do": "exit", "code": 0}), KEEP_ME="old-environment", **planted, **(extra_env or {}))
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "run", name,
                            "--prompt", "hello"], capture_output=True, text=True, timeout=120, env=self.env(extra),
                           cwd=str(self.tmp))
        started = [c for c in self.calls() if c.get("started")]
        self.assertTrue(started, r.stdout + r.stderr)
        return r, started[-1]

    def run_id(self):
        found = re.findall(r"run ([0-9a-f]{16})", (self.root / "LOGBOOK.md").read_text(encoding="utf-8"))
        self.assertTrue(found)
        return found[0]

    SECRETS = {"GH_TOKEN", "AWS_SECRET_ACCESS_KEY", "SENTRY_AUTH_TOKEN", "S78_SECRET_TOKEN", "NODE_OPTIONS"}

    def test_an_enforced_claude_code_run_has_the_allow_list_the_kept_name_and_the_marker(self):
        self.enforced()
        r, started = self.run_one("reviewer")
        keys = set(started["env_keys"])
        self.assertEqual(sorted(keys & (self.SECRETS | {"SSH_AUTH_SOCK", "ANTHROPIC_API_KEY", "KIRO_API_KEY", "KEEP_ME"})), [], r.stdout)
        self.assertIn("S78_KEEP", keys)
        self.assertIn("PATH", keys)
        self.assertEqual(started["run_marker"], self.run_id())

    def test_an_enforced_kiro_run_has_the_allow_list_and_the_marker(self):
        self.enforced()
        r, started = self.run_one("helper")
        keys = set(started["env_keys"])
        self.assertEqual(sorted(keys & (self.SECRETS | {"S78_KEEP", "KIRO_API_KEY", "KEEP_ME"})), [], r.stdout)
        self.assertEqual(started["run_marker"], self.run_id())

    def test_the_gate_checks_see_the_same_allow_list_when_enforced(self):
        self.enforced()
        self.run_one("reviewer")
        probes = [c for c in self.calls() if c.get("probe")]
        self.assertTrue(probes)
        for c in probes:
            with self.subTest(probe=c["probe"]):
                self.assertNotIn("GH_TOKEN", c["env_keys"])

    def test_with_no_mode_file_the_old_environment_is_kept_and_there_is_no_marker(self):
        """Today's default. KEEP_ME and the planted names reach the helper as before; the W64 names are still removed."""
        for name in ("reviewer", "helper"):
            with self.subTest(agent=name):
                r, started = self.run_one(name)
                keys = set(started["env_keys"])
                self.assertIn("KEEP_ME", keys)
                self.assertIn("GH_TOKEN", keys)
                self.assertNotIn("SSH_AUTH_SOCK", keys)
                self.assertIsNone(started["run_marker"])
                self.assertNotIn("UMWAYI_RUN", keys)

    def test_a_cooperative_agent_keeps_the_old_environment_and_gets_no_marker(self):
        self.cooperative("reviewer")
        r, started = self.run_one("reviewer")
        keys = set(started["env_keys"])
        self.assertIn("KEEP_ME", keys)  # today's behaviour for a cooperative agent
        self.assertIn("GH_TOKEN", keys)
        self.assertNotIn("SSH_AUTH_SOCK", keys)  # the W64 deny list still holds
        self.assertNotIn("ANTHROPIC_API_KEY", keys)
        self.assertIsNone(started["run_marker"])
        self.assertNotIn("UMWAYI_RUN", keys)

    def test_an_enforced_agent_next_to_a_cooperative_one_is_still_scrubbed(self):
        self.cooperative("reviewer")
        r, started = self.run_one("helper")  # the file exists and helper is not cooperative: enforced
        self.assertNotIn("KEEP_ME", started["env_keys"])
        self.assertEqual(started["run_marker"], self.run_id())

    def test_a_mode_file_that_cannot_be_read_is_enforced(self):
        self.mode_file("a: [\n")
        r, started = self.run_one("reviewer")
        self.assertNotIn("GH_TOKEN", started["env_keys"])
        self.assertNotIn("KEEP_ME", started["env_keys"])

    def test_a_planted_marker_in_the_owners_environment_is_replaced_by_the_run_id_when_enforced(self):
        self.enforced()
        r, started = self.run_one("reviewer", {"UMWAYI_RUN": "planted-run"})
        self.assertEqual(started["run_marker"], self.run_id())

    def test_a_real_start_passes_the_name_the_supervisor_sets_in_both_modes(self):
        for setup in (lambda: None, self.enforced):
            setup()
            r, started = self.run_one("reviewer", {"PYTHONDONTWRITEBYTECODE": "1"})
            with self.subTest(enforced=(setup == self.enforced)):
                self.assertIn("PYTHONDONTWRITEBYTECODE", started["env_keys"])


if __name__ == "__main__":
    unittest.main()
