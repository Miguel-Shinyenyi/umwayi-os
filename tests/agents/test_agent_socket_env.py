"""W64: the owner's SSH agent (SSH_AUTH_SOCK, SSH_AGENT_PID) never reaches an AI helper umwayi starts.

Every builder of a helper environment in umwayi/agents.py is checked: the two deny-list builders (claude_env,
kiro_env) remove both names, and the three allow-list builders (child_env, login_env, opencode_env) never pass them.
Each check has a planted fault. Two real runs (Claude Code and Kiro, `agent run` as a child process with the fake
agent) show that the started agent's environment has neither name and keeps the rest.
"""

import ast
import inspect
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests.agents.support import RULES, AgentCase
from umwayi import agents, goalrun

SOCKETS = ("SSH_AUTH_SOCK", "SSH_AGENT_PID")
OWNER = {"HOME": "/home/me", "PATH": "/usr/bin:/bin", "USER": "me", "LANG": "C.UTF-8", "TERM": "xterm",
         "EDITOR": "vi", "SSH_AUTH_SOCK": "/tmp/ssh-x/agent.1", "SSH_AGENT_PID": "4242", "SSH_TTY": "/dev/pts/1",
         "UMWAYI_TEST_KEEP": "kept"}

# every builder of a helper environment, by platform; opencode_env takes the inline config as a second argument
BUILDERS = {
    "claude-code run and cli chat": lambda env: agents.claude_env(env),
    "claude-code acp chat": lambda env: agents.child_env(env),
    "claude-code sign-in": lambda env: agents.login_env(env),
    "kiro": lambda env: agents.kiro_env(env),
    "opencode": lambda env: agents.opencode_env(env, "{}"),
    # W78 step 2: the allow list of an enforced start, for each of the two platforms that had a deny list
    "claude-code enforced": lambda env: agents.enforced_env(env, agents.Agent("reviewer", "claude-code", "claude", "cli", "/w")),
    "kiro enforced": lambda env: agents.enforced_env(env, agents.Agent("helper", "kiro", "kiro-cli", "cli", "/w")),
}


def leaks(builders=None):
    """{platform: [socket names its builder passes on]} for a planted owner environment."""
    out = {}
    for name, build in (builders or BUILDERS).items():
        got = [k for k in SOCKETS if k in build(dict(OWNER))]
        if got:
            out[name] = got
    return out


def old_kiro_env(environ):  # the builder of before W64
    return {k: v for k, v in environ.items() if k not in agents.KIRO_CREDENTIAL_ENV}


def claude_env_one_name(environ):
    return {k: v for k, v in environ.items() if k not in agents.CLAUDE_CREDENTIAL_ENV and k != "SSH_AUTH_SOCK"}


class BuilderTests(unittest.TestCase):
    def test_the_two_names(self):
        self.assertEqual(agents.AGENT_SOCKET_ENV, SOCKETS)

    def test_no_builder_passes_either_name(self):
        self.assertEqual(leaks(), {})

    def test_either_name_alone_is_removed(self):
        for name in SOCKETS:
            env = dict(OWNER)
            env.pop(next(n for n in SOCKETS if n != name))
            for platform, build in BUILDERS.items():
                with self.subTest(platform=platform, name=name):
                    self.assertNotIn(name, build(env))

    def test_planted_fault_a_builder_that_forgets_one_platform(self):
        with mock.patch.object(agents, "kiro_env", old_kiro_env):
            self.assertEqual(leaks(), {"kiro": list(SOCKETS)})

    def test_planted_fault_a_builder_that_removes_only_one_of_the_two_names(self):
        with mock.patch.object(agents, "claude_env", claude_env_one_name):
            self.assertEqual(leaks(), {"claude-code run and cli chat": ["SSH_AGENT_PID"]})

    def test_the_deny_list_builders_keep_everything_else(self):
        rest = {k: v for k, v in OWNER.items() if k not in SOCKETS}
        self.assertEqual(agents.claude_env(dict(OWNER)), rest)
        self.assertEqual(agents.kiro_env(dict(OWNER)), rest)

    def test_the_allow_list_builders_keep_their_names(self):
        self.assertEqual(agents.child_env(dict(OWNER))["HOME"], "/home/me")
        self.assertEqual(agents.child_env(dict(OWNER))["PATH"], "/usr/bin:/bin")
        login = agents.login_env(dict(OWNER))
        self.assertEqual((login["TERM"], login["SSH_TTY"]), ("xterm", "/dev/pts/1"))  # a terminal name, not a socket
        self.assertEqual(agents.opencode_env(dict(OWNER), "{}")["LANG"], "C.UTF-8")

    def test_the_owners_environment_is_not_changed(self):
        env = dict(OWNER)
        for build in BUILDERS.values():
            build(env)
        self.assertEqual(env, OWNER)


class InventoryTests(unittest.TestCase):
    """The list above is every place: a new builder, or a start that passes umwayi's own environment, fails here."""

    def test_every_env_builder_of_agents_py_is_listed(self):
        tree = ast.parse(Path(agents.__file__).read_text(encoding="utf-8"))
        found = sorted(n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.endswith("_env"))
        self.assertEqual(found, ["child_env", "claude_env", "enforced_env", "kiro_env", "login_env", "opencode_env"])

    def test_no_start_passes_umwayis_own_environment(self):
        src = Path(agents.__file__).read_text(encoding="utf-8")
        for bad in ("env=os.environ", "env=dict(os.environ", "env=None"):
            self.assertNotIn(bad, src)
        start = inspect.getsource(agents._Run._start)
        sources = {line.split("=", 1)[1].split("(")[0].strip() for line in start.splitlines()
                   if line.strip().startswith("env = ")}
        self.assertEqual(sources, {"login_env", "opencode_env", "child_env", "enforced_env", "claude_env", "kiro_env"})

    def test_the_goal_supervisor_starts_only_umwayi_agent_run(self):
        """Its children are `umwayi agent run`, which builds the helper's environment with the builders above."""
        self.assertEqual(goalrun.CHILD_PREFIX[1:], ["-m", "umwayi", "agent", "run"])
        src = Path(goalrun.__file__).read_text(encoding="utf-8")
        self.assertEqual(src.count("subprocess.Popen("), 1)


class RealRunTests(AgentCase):
    """`umwayi agent run` as a real child process, with the fake agent recording the names of its environment."""

    def setUp(self):
        super().setUp()
        self.fake("claude")
        self.fake("kiro-cli")
        self.write_rules(RULES.replace("agent: [reviewer, slow, stubborn, quick]", "agent: [reviewer, helper]"))
        self.write_agents("agents:\n"
                          "  - name: reviewer\n    platform: claude-code\n    command: claude\n    workdir: {work}\n"
                          "  - name: helper\n    platform: kiro\n    command: kiro-cli\n    workdir: {work}\n"
                          "    trust_tools: [read_file]\n")
        self.kiro_hook_file(command=self.kiro_command(python=sys.executable))
        self.roomy_budget()

    def run_one(self, name):
        extra = dict(self.script({"do": "exit", "code": 0}), SSH_AUTH_SOCK=str(self.tmp / "agent.sock"),
                     SSH_AGENT_PID="4242", UMWAYI_TEST_KEEP="kept")
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "run", name,
                            "--prompt", "hello"], capture_output=True, text=True, timeout=120, env=self.env(extra),
                           cwd=str(self.tmp))
        return r

    def assert_no_socket(self, r):
        self.assertIn(r.returncode, (0, 2, 3), r.stdout + r.stderr)
        recorded = [c for c in self.calls() if "env_keys" in c]
        self.assertTrue(recorded, r.stdout + r.stderr)
        for c in recorded:  # the start and every check before it (version, login)
            with self.subTest(probe=c.get("probe"), argv=c.get("argv")):
                self.assertEqual(set(c["env_keys"]) & set(SOCKETS), set())
        started = [c for c in recorded if c.get("started")]
        self.assertTrue(started, r.stdout + r.stderr)
        self.assertIn("UMWAYI_TEST_KEEP", started[0]["env_keys"])  # the rest is passed as before

    def test_claude_code_run(self):
        self.assert_no_socket(self.run_one("reviewer"))

    def test_kiro_run(self):
        self.assert_no_socket(self.run_one("helper"))


if __name__ == "__main__":
    unittest.main()
