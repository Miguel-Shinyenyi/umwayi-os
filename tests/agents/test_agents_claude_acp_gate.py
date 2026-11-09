"""Layer 10 part 7a, tasks 10.23 and 10.25 (the chat itself, part 7b: test_agents_claude_acp_chat.py): a Claude Code agent with transport acp, its gate checks
and the allow-listed child environment (requirement 10.R11, design.md part 7).

Every test runs `python -m umwayi agent ...` as a real child process, with a fake `node`
(tests/agents/fake_node.py) first on PATH and a fake installed adapter (`package.json` and
`dist/index.js`) in a copy of the umwayi-os source. No real Node, no Claude Code, no network.
"""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from umwayi import agents

from tests.agents.support import SECRET, AgentCase, copy_src, tree_state

NODE_SOURCE = Path(__file__).with_name("fake_node.py")

AGENTS = """agents:
  - name: reviewer
    platform: claude-code
    command: claude
    transport: acp
    workdir: {work}
    max_turns: 9
  - name: helper
    platform: kiro
    command: kiro-cli
    transport: acp
    workdir: {work}
"""

LISTED_SET = {  # allow-listed names the tests set, with values
    "LANG": "C.UTF-8", "TZ": "UTC", "HTTPS_PROXY": "http://proxy.invalid:1", "https_proxy": "http://p.invalid:1",
    "NO_PROXY": "localhost", "CLAUDE_CONFIG_DIR": "/nonexistent/claude-config", "NODE_EXTRA_CA_CERTS": "/x/ca.pem",
    "XDG_CONFIG_HOME": "/nonexistent/xdg",
}
DROPPED = {  # never passed, even when set
    "ANTHROPIC_API_KEY": SECRET, "ANTHROPIC_AUTH_TOKEN": SECRET, "ANTHROPIC_BASE_URL": "https://" + SECRET,
    "CLAUDE_CODE_EXECUTABLE": "/bin/" + SECRET, "CLAUDE_AGENT_LOGS": "/tmp/" + SECRET, "IS_SANDBOX": "1",
    "NODE_OPTIONS": "--require=/tmp/" + SECRET, "NODE_PATH": "/tmp/" + SECRET, "npm_config_registry": SECRET,
    "ANTHROPIC_MODEL": SECRET, "OPENAI_API_KEY": SECRET, "AWS_SECRET_ACCESS_KEY": SECRET,
}
ALLOWED = set(agents.CHILD_ENV_NAMES) | set(agents.CHILD_ENV_SET)
PROBES = ["node version", "adapter version", "claude code version", "sign-in"]


class ClaudeAcpCase(AgentCase):
    def setUp(self):
        super().setUp()
        self.src = copy_src(self.tmp / "src")
        self.pkg_dir = self.src / agents.CLAUDE_ACP_PACKAGE_DIR
        self.adapter = self.src / agents.CLAUDE_ACP_ADAPTER
        self.install()
        self.node = self.bin / "node"
        self.node.write_text(f"#!{sys.executable}\n" + NODE_SOURCE.read_text(encoding="utf-8"), encoding="utf-8")
        self.node.chmod(0o755)
        self.fake("claude")
        self.fake("kiro-cli")
        self.write_rules()
        self.write_agents(AGENTS)

    def install(self, name=agents.CLAUDE_ACP_PACKAGE, version=agents.CLAUDE_ACP_VERSION):
        (self.pkg_dir / "dist").mkdir(parents=True, exist_ok=True)
        self.adapter.write_text("// fake adapter, never run by node in these tests\n", encoding="utf-8")
        (self.pkg_dir / "package.json").write_text(json.dumps({"name": name, "version": version}), encoding="utf-8")

    def answers(self, **cfg):
        (self.bin / "node.json").write_text(json.dumps(cfg), encoding="utf-8")

    def node_calls(self) -> list:
        log = self.bin / "node-calls.jsonl"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]

    def check(self, extra=None):
        return self.umwayi("check", "reviewer", extra=extra)

    def marks(self, r) -> dict:
        out = {}
        for line in self.lines(r):
            for mark in ("ok", "no", "not run"):
                if line.startswith(mark + ": "):
                    out[line[len(mark) + 2:].split(":", 1)[0]] = mark
        return out

    def assert_no_chat_started(self):
        self.assertEqual([c for c in self.node_calls() if c["started"]], [], "the adapter was started")
        self.assertEqual([c for c in self.calls() if c.get("started")], [], "an agent was started")


class GatedTests(ClaudeAcpCase):
    def test_every_check_passes_in_order_and_nothing_is_started(self):
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        marks = self.marks(r)
        self.assertEqual([k for k in marks if k != "kill switch"], agents.CLAUDE_ACP_ORDER)
        self.assertTrue(all(v == "ok" for v in marks.values()), r.stdout)
        self.assertEqual([c["probe"] for c in self.node_calls()], PROBES)
        for c in self.node_calls():
            self.assertEqual(c["argv"][0], str(self.node))
            self.assertEqual(c["cwd"], str(self.work))
            self.assertEqual(c["stdin"], 0)
            if c["probe"] != "node version":
                self.assertEqual(c["argv"][1], str(self.adapter))
        line = [ln for ln in self.lines(r) if ln.startswith("chat would start: ")]
        self.assertEqual(len(line), 1)
        argv = json.loads(line[0][len("chat would start: "):].split(" with the allow-listed environment")[0])
        self.assertEqual(argv, [str(self.node), str(self.adapter)])  # no max_turns, no npx, no shell
        self.assertIn("only after the SessionStart canary has run", line[0])
        self.assertIn("ok: claude code version: 2.1.318", r.stdout)
        self.assertIn("Nothing was started.", self.lines(r)[-1])
        self.assert_no_chat_started()

    def test_validate_and_list_show_it(self):
        r = self.umwayi("validate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("reviewer (claude-code, acp)", r.stdout)
        r = self.umwayi("list")
        self.assertEqual(r.returncode, 0)
        self.assertIn(f"reviewer  claude-code  acp  claude  {self.work}", r.stdout)
        self.assertEqual(self.node_calls(), [])

    def test_the_kiro_acp_checks_are_unchanged(self):
        r = self.umwayi("check", "helper")
        self.assertEqual(self.node_calls(), [])
        self.assertIn("ok: command: kiro-cli found", r.stdout)
        self.assertIn("kiro hook file", r.stdout)


class FailingCheckTests(ClaudeAcpCase):
    """Each check failing in turn: exit 2, the later checks not run, and nothing started."""

    def refused_at(self, name: str, extra=None, words: str = ""):
        r = self.check(extra)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        marks = self.marks(r)
        order = agents.CLAUDE_ACP_ORDER
        i = order.index(name)
        self.assertEqual(marks[name], "no", r.stdout)
        for before in order[:i]:
            self.assertEqual(marks[before], "ok", r.stdout)
        for after in order[i + 1:]:
            self.assertEqual(marks[after], "not run", r.stdout)
        self.assertIn("Not gated: agent reviewer would be refused (exit 2). Nothing was started.", r.stdout)
        self.assertNotIn("would start", r.stdout)
        self.assertIn(words, r.stdout)
        probes = [c["probe"] for c in self.node_calls()]
        later = [p for p in PROBES if p in order and order.index(p) > i]
        self.assertFalse(set(probes) & set(later), f"a later program ran: {probes}")
        self.assert_no_chat_started()
        return r

    def test_no_node_on_path(self):
        self.node.unlink()
        self.refused_at("node", extra={"PATH": str(self.bin)}, words="node was not found on PATH")

    def test_node_too_old(self):
        self.answers(node_version="v20.11.0\n")
        self.refused_at("node version", words="20.11.0 is older than 22.0.0")

    def test_node_version_garbage(self):
        for out in ("garbage\n", "22.1.0\n", "v22.1\n", "v22.1.0 extra\n", ""):
            with self.subTest(out=out):
                (self.bin / "node-calls.jsonl").unlink(missing_ok=True)
                self.answers(node_version=out)
                self.refused_at("node version", words="did not print a version like v22.0.0")

    def test_node_version_exit_code(self):
        self.answers(node_exit=3)
        self.refused_at("node version", words="node --version exited 3")

    def test_node_22_is_enough(self):
        self.answers(node_version="v22.0.0\n")
        self.assertEqual(self.check().returncode, 0)

    def test_the_adapter_file_missing(self):
        self.adapter.unlink()
        self.refused_at("adapter file", words="npm ci --ignore-scripts")

    def test_the_adapter_file_is_a_link(self):
        real = self.tmp / "elsewhere.js"
        real.write_text("// elsewhere\n", encoding="utf-8")
        self.adapter.unlink()
        os.symlink(real, self.adapter)
        self.refused_at("adapter file", words="is missing, a link or not a regular file")

    def test_the_package_folder_is_a_link(self):
        moved = self.tmp / "moved-package"
        self.pkg_dir.rename(moved)
        os.symlink(moved, self.pkg_dir)
        self.refused_at("adapter file", words="is missing, a link or not a regular file")

    def test_the_adapter_file_is_a_folder(self):
        self.adapter.unlink()
        self.adapter.mkdir()
        self.refused_at("adapter file")

    def test_another_package_name(self):
        self.install(name="@evil/claude-agent-acp")
        self.refused_at("adapter package", words=f"is not {agents.CLAUDE_ACP_PACKAGE} {agents.CLAUDE_ACP_VERSION}")

    def test_another_package_version(self):
        for version in ("0.100.9", "0.101.1", "^0.101.0", "0.101.0-beta", ""):
            with self.subTest(version=version):
                self.install(version=version)
                self.refused_at("adapter package", words="npm ci --ignore-scripts")

    def test_the_package_json_missing_or_broken(self):
        pkg = self.pkg_dir / "package.json"
        pkg.unlink()
        self.refused_at("adapter package", words="is missing, a link, too big or not valid JSON")
        pkg.write_text("{not json", encoding="utf-8")
        self.refused_at("adapter package", words="not valid JSON")
        pkg.write_text(json.dumps({"name": agents.CLAUDE_ACP_PACKAGE, "version": agents.CLAUDE_ACP_VERSION,
                                   "pad": "x" * agents.MAX_FILE_BYTES}), encoding="utf-8")
        self.refused_at("adapter package", words="too big")

    def test_adapter_version_differs_from_package_json(self):
        for out in ("0.100.9\n", "0.101.0 extra\n", "v0.101.0\n", "", "0.101.00\n"):
            with self.subTest(out=out):
                self.answers(adapter_version=out)
                self.refused_at("adapter version", words=f"did not print exactly {agents.CLAUDE_ACP_VERSION}")
        self.answers(adapter_exit=1)
        self.refused_at("adapter version", words="exited 1")

    def test_claude_code_too_old(self):
        self.answers(cli_version="2.1.294 (Claude Code)\n")
        self.refused_at("claude code version", words="2.1.294 is older than 2.1.295")

    def test_claude_code_version_garbage_or_failing(self):
        self.answers(cli_version="Claude Code\n")
        self.refused_at("claude code version", words="no version number")
        self.answers(cli_exit=4)
        self.refused_at("claude code version", words="exited 4")

    def test_claude_code_2_1_295_is_enough(self):
        self.answers(cli_version="2.1.295 (Claude Code)\n")
        self.assertEqual(self.check().returncode, 0)

    def test_not_signed_in(self):
        self.answers(auth_exit=1, auth_output=f"Not logged in {SECRET}\n")
        r = self.refused_at("sign-in", words=agents.SIGNIN_TEXT)
        self.assertIn("auth status exited 1", r.stdout)

    def test_sign_in_check_hangs(self):
        self.answers(auth_hang=True, auth_output=f"{SECRET}\n")
        r = self.refused_at("sign-in", words="did not answer within 15 s")
        self.assertIn(agents.SIGNIN_TEXT, r.stdout)

    def test_the_hook_missing(self):
        (self.src / "adapters" / "claude_code" / "hook.py").unlink()
        self.refused_at("hook script", words="is missing or not a regular file")

    def test_the_hook_self_test_fails(self):
        (self.src / "adapters" / "claude_code" / "hook.py").write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
        self.refused_at("hook self-test", words="it must block the self-test event with exit 2")


class SecretTests(ClaudeAcpCase):
    def test_the_sign_in_output_is_never_shown_or_logged(self):
        self.answers(auth_output=f"Logged in as owner@example.invalid token {SECRET}\n", secret=SECRET)
        before = tree_state(self.root)
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn(SECRET, r.stdout + r.stderr)
        self.assertNotIn("owner@example.invalid", r.stdout + r.stderr)
        self.assertEqual(tree_state(self.root), before, "agent check wrote to the root")
        self.answers(auth_output=f"{SECRET}\n", auth_exit=1, secret=SECRET)
        r = self.check()
        self.assertEqual(r.returncode, 2)
        self.assertNotIn(SECRET, r.stdout + r.stderr)
        self.assertEqual(tree_state(self.root), before)

    def test_the_child_environment_is_the_allow_list(self):
        recorder = self.tmp / "hook-env.json"
        hook = self.src / "adapters" / "claude_code" / "hook.py"
        hook.write_text("import json, os, sys\n"
                        f"open({str(recorder)!r}, 'w').write(json.dumps(dict(os.environ)))\n"
                        "sys.stdin.read()\nsys.exit(2)\n", encoding="utf-8")
        self.answers(secret=SECRET)
        extra = dict(LISTED_SET)
        extra.update(DROPPED)
        extra["CLAUDE_AGENT_ACP_PROTOCOL"] = "v2"
        r = self.check(extra=extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = self.node_calls()
        self.assertEqual([c["probe"] for c in calls], PROBES)
        hook_env = json.loads(recorder.read_text(encoding="utf-8"))
        envs = [(c["probe"], set(c["env"])) for c in calls] + [("hook self-test", set(hook_env))]
        for probe, names in envs:
            with self.subTest(program=probe):
                self.assertLessEqual(names, ALLOWED)
                for name in LISTED_SET:
                    self.assertIn(name, names)
                for name in ("PATH", "HOME", "CLAUDE_AGENT_ACP_PROTOCOL"):
                    self.assertIn(name, names)
                for name in DROPPED:
                    self.assertNotIn(name, names)
                for name in ("PYTHONPATH", "FAKE_LOG", "UMWAYI_FAULT"):
                    self.assertNotIn(name, names)
        for c in calls:
            self.assertEqual(c["protocol"], "v1")
            self.assertFalse(c["secret_in_env"], c["probe"])
        self.assertEqual(hook_env["CLAUDE_AGENT_ACP_PROTOCOL"], "v1")
        self.assertFalse(any(SECRET in v for v in hook_env.values()))

    def test_the_programs_get_empty_stdin_not_umwayi_s(self):
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "check", "reviewer"],
                           input=f"owner text {SECRET}\n" * 10, capture_output=True, text=True, env=self.env(),
                           cwd=str(self.tmp), timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = self.node_calls()
        self.assertEqual([c["probe"] for c in calls], PROBES)
        self.assertEqual([c["stdin"] for c in calls], [0, 0, 0, 0])

    def test_every_argument_list_is_plain(self):
        self.check()
        for c in self.node_calls():
            with self.subTest(argv=c["argv"]):
                for bad in agents.FORBIDDEN_FLAGS:
                    self.assertNotIn(bad, c["argv"])
                self.assertFalse(any(w in ("sh", "bash", "-c", "npx", "npm") for w in c["argv"]))
                self.assertTrue(os.path.isabs(c["argv"][0]))


class ChatAndRunTests(ClaudeAcpCase):
    def test_agent_run_stays_claude_p(self):
        r = self.umwayi("run", "reviewer", "--prompt", "say hello")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.node_calls(), [])
        started = [c for c in self.calls() if c.get("started")]
        self.assertEqual(len(started), 1)
        self.assertEqual(started[0]["argv"][0], "-p")  # the fake records the arguments after the program
        self.assertIn("--max-turns", started[0]["argv"])


class ChildEnvUnitTests(unittest.TestCase):
    def test_only_listed_names_that_are_set(self):
        given = dict(LISTED_SET, **DROPPED, HOME="/h", PATH="/bin", CLAUDE_AGENT_ACP_PROTOCOL="v9", EMPTY_NOT_LISTED="")
        env = agents.child_env(given)
        self.assertEqual(env, dict(LISTED_SET, HOME="/h", PATH="/bin", CLAUDE_AGENT_ACP_PROTOCOL="v1"))
        self.assertEqual(agents.child_env({}), {"CLAUDE_AGENT_ACP_PROTOCOL": "v1"})

    def test_the_list_is_the_one_of_10_r11_9(self):
        want = {"HOME", "USER", "LOGNAME", "PATH", "SHELL", "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE", "LC_MESSAGES",
                "TZ", "TMPDIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME",
                "XDG_RUNTIME_DIR", "CLAUDE_CONFIG_DIR", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy",
                "http_proxy", "no_proxy", "NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE", "SSL_CERT_DIR"}
        self.assertEqual(set(agents.CHILD_ENV_NAMES), want)
        self.assertEqual(len(agents.CHILD_ENV_NAMES), len(want))
        for name in agents.CHILD_ENV_NAMES:
            self.assertFalse(name.startswith(("ANTHROPIC", "npm_config", "NODE_OPTIONS", "NODE_PATH")))
        self.assertEqual(agents.CHILD_ENV_SET, {"CLAUDE_AGENT_ACP_PROTOCOL": "v1"})


if __name__ == "__main__":
    unittest.main()
