"""Layer 10 part 2: gate checks, argument lists and `umwayi agent check` (tasks.md 10.4 to 10.7).

Child process tests run `python -m umwayi ... agent check NAME` with fake claude and
kiro-cli first on PATH. No test starts an agent: the fakes record every call, and every
test that reaches the platform checks that only the version flag was used.
"""

import itertools
import json
import os
import time
import unittest
from pathlib import Path

from umwayi import agents
from umwayi.errors import UsageError

from tests.agents.support import CLAUDE_AGENT, KIRO_AGENT, REPO, SECRET, AgentCase, copy_src, tree_state


def kiro_agent_text(transport: str = "cli") -> str:
    return KIRO_AGENT.replace("{transport}", transport)


class ClaudeGateTests(AgentCase):
    def setUp(self):
        super().setUp()
        self.fake("claude")
        self.write_agents(CLAUDE_AGENT)

    def check(self, **kw):
        return self.umwayi("check", "reviewer", **kw)

    def test_gated_claude_code_prints_every_check_and_starts_nothing(self):
        before = tree_state(self.root, self.work, self.home)
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for name in ("command", "version", "hook script", "hook self-test"):
            self.assertIn(f"ok: {name}: ", r.stdout)
        self.assertNotIn("kiro hook file", r.stdout)
        self.assertIn("Gated: agent reviewer can be started. Nothing was started.", r.stdout)
        self.assertEqual([c["argv"] for c in self.calls()], [["-v"]])
        self.assert_nothing_started()
        self.assertEqual(tree_state(self.root, self.work, self.home), before)
        self.assertFalse((self.root / "LOGBOOK.md").exists())
        self.assertFalse(any(p.name == ".claude" for p in self.tmp.rglob("*")))

    def test_the_version_runs_in_the_workdir_with_the_found_path(self):
        r = self.check()
        self.assertEqual(self.calls()[0]["cwd"], str(self.work))
        self.assertIn(f"ok: command: claude found at {self.bin / 'claude'}", r.stdout)

    def test_missing_command_is_refused_and_nothing_runs(self):
        (self.bin / "claude").unlink()
        r = self.check(extra={"PATH": str(self.bin)})
        self.assertEqual(r.returncode, 2)
        self.assertIn("no: command: claude was not found on PATH", r.stdout)
        self.assertIn("not run: version", r.stdout)
        self.assertIn("would be refused (exit 2)", r.stdout)
        self.assertEqual(self.calls(), [])

    def test_versions_that_cannot_be_read_or_are_too_old_are_refused(self):
        cases = {"": "no version number", "Claude Code": "no version number", "garbage 2.1": "no version number",
                 "2.1.294 (Claude Code)": "older than 2.1.295", "1.99.999": "older than 2.1.295",
                 "2.0.300": "older than 2.1.295"}
        for out, words in cases.items():
            with self.subTest(output=out):
                r = self.check(extra={"FAKE_CLAUDE_VERSION": out})
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertIn("no: version: ", r.stdout)
                self.assertIn(words, r.stdout)
                self.assertIn("not run: hook script", r.stdout)

    def test_the_lowest_allowed_version_and_newer_ones_pass(self):
        for out in ("2.1.295", "2.1.295 (Claude Code)", "claude 2.2.0", "3.0.0", "10.0.1"):
            with self.subTest(output=out):
                self.assertEqual(self.check(extra={"FAKE_CLAUDE_VERSION": out}).returncode, 0)

    def test_a_version_command_that_fails_is_refused(self):
        r = self.check(extra={"FAKE_CLAUDE_EXIT": "1"})
        self.assertEqual(r.returncode, 2)
        self.assertIn("claude -v exited 1", r.stdout)

    def test_a_version_command_that_hangs_is_refused_after_the_timeout(self):
        start = time.monotonic()
        r = self.check(extra={"FAKE_CLAUDE_HANG": "1"})
        self.assertEqual(r.returncode, 2)
        self.assertIn("did not answer within 10 s", r.stdout)
        self.assertLess(time.monotonic() - start, 30)

    def test_the_argument_lists_have_the_gate_and_no_forbidden_flag(self):
        r = self.check()
        run, chat = self.argv_line(r, "run"), self.argv_line(r, "chat")
        self.assertEqual(run[0], str(self.bin / "claude"))
        self.assertEqual(run[1:4], ["-p", "--permission-mode", "default"])
        self.assertEqual(run[-1], "PROMPT")
        self.assertEqual(run[-3:-1], ["--max-turns", "20"])
        self.assertEqual(chat[1:3], ["--permission-mode", "default"])
        for argv in (run, chat):
            settings = json.loads(argv[argv.index("--settings") + 1])
            self.assertIs(settings["disableAllHooks"], False)
            [group] = settings["hooks"]["PreToolUse"]
            self.assertEqual(group["matcher"], "*")
            [hook] = group["hooks"]
            self.assertEqual(hook["onFailure"], "block")
            self.assertEqual(hook["timeout"], 30)
            self.assertEqual(hook["args"], [str(REPO / "adapters" / "claude_code" / "hook.py"), "--root", str(self.root)])
            self.assertTrue(os.path.isabs(hook["command"]))
            for bad in agents.FORBIDDEN_FLAGS:
                self.assertNotIn(bad, argv)
            self.assertNotIn("bypassPermissions", " ".join(argv))

    def test_the_kill_switch_is_shown_but_check_changes_nothing(self):
        (self.root / ".umwayi").mkdir()
        (self.root / ".umwayi" / "KILL").write_text("", encoding="utf-8")
        r = self.check()
        self.assertEqual(r.returncode, 0)
        self.assertIn("kill switch: on (a start would stop now with exit 3)", r.stdout)
        self.assertTrue((self.root / ".umwayi" / "KILL").exists())
        self.assert_nothing_started()


class HookFaultTests(AgentCase):
    """Break the layer 9 hook in a copy of the code, never in the repo."""

    def setUp(self):
        super().setUp()
        self.src = copy_src(self.tmp / "src")
        self.hook = self.src / "adapters" / "claude_code" / "hook.py"
        self.fake("claude")
        self.write_agents(CLAUDE_AGENT)

    def check(self):
        return self.umwayi("check", "reviewer")

    def test_the_copy_is_gated_before_it_is_broken(self):
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(str(self.hook), r.stdout)

    def test_a_missing_hook_is_refused(self):
        self.hook.unlink()
        r = self.check()
        self.assertEqual(r.returncode, 2)
        self.assertIn("no: hook script: ", r.stdout)
        self.assertIn("is missing or not a regular file", r.stdout)
        self.assertIn("not run: hook self-test", r.stdout)

    def test_a_hook_that_is_a_link_is_refused(self):
        real = self.hook.with_name("real_hook.py")
        self.hook.rename(real)
        os.symlink(real, self.hook)
        self.assertEqual(self.check().returncode, 2)

    def test_a_hook_that_allows_fails_or_hangs_on_the_self_test_is_refused(self):
        cases = {"import sys\nsys.exit(0)\n": "exited 0", "import sys\nsys.exit(1)\n": "exited 1",
                 "import sys\nsys.exit(3)\n": "exited 3", "raise SystemExit('boom')\n": "exited 1",
                 "this is not python\n": "exited 1", "import time\ntime.sleep(60)\n": "did not answer within 5 s"}
        for body, words in cases.items():
            with self.subTest(hook=body.splitlines()[0]):
                self.hook.write_text(body, encoding="utf-8")
                start = time.monotonic()
                r = self.check()
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertIn("no: hook self-test: ", r.stdout)
                self.assertIn(words, r.stdout)
                self.assertLess(time.monotonic() - start, 30)
        self.assert_nothing_started()

    def test_the_self_test_logs_nothing_and_checks_no_rule(self):
        (self.root / "rules.yaml").write_text("rules: []\n", encoding="utf-8")
        r = self.check()
        self.assertEqual(r.returncode, 0)
        self.assertFalse((self.root / "LOGBOOK.md").exists())
        self.assertFalse((self.root / "queue.md").exists())


class KiroGateTests(AgentCase):
    def setUp(self):
        super().setUp()
        self.fake("kiro-cli")
        self.write_agents(kiro_agent_text())

    def check(self, **kw):
        return self.umwayi("check", "helper", **kw)

    def assert_refused(self, words: str = "no PreToolUse hook for every tool"):
        r = self.check()
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("no: kiro hook file: ", r.stdout)
        self.assertIn(words, r.stdout)
        self.assert_nothing_started()
        return r

    def test_no_hook_file_is_refused_with_the_command_to_add(self):
        r = self.assert_refused()
        self.assertIn(self.kiro_command(), r.stdout)
        self.assertIn("adapters/kiro/README.md", r.stdout)
        self.assertFalse((self.work / ".kiro").exists())  # never created
        self.assertFalse((self.home / ".kiro").exists())

    def test_the_owner_hook_file_in_the_workdir_is_accepted_and_not_changed(self):
        p = self.kiro_hook_file()
        before = tree_state(self.root, self.work, self.home)
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"ok: kiro hook file: {p}", r.stdout)
        self.assertEqual(tree_state(self.root, self.work, self.home), before)
        self.assertEqual([c["argv"] for c in self.calls()], [["--version"]])

    def test_a_hook_file_in_home_is_accepted(self):
        p = self.kiro_hook_file(folder=self.home / ".kiro" / "hooks")
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn(str(p), r.stdout)

    def test_an_absolute_python_and_a_star_matcher_are_accepted(self):
        hook = {"trigger": "PreToolUse", "matcher": "*",
                "action": {"type": "command", "command": self.kiro_command(python="/usr/bin/python3.12")}}
        self.kiro_hook_file(hook=hook)
        self.assertEqual(self.check().returncode, 0)

    def test_hook_files_that_do_not_gate_every_tool_are_refused(self):
        good = self.kiro_command()
        hook_path = self.src / "adapters" / "kiro" / "hook.py"
        bad = {
            "a matcher for one tool": {"trigger": "PreToolUse", "matcher": "execute_bash",
                                       "action": {"type": "command", "command": good}},
            "an empty matcher": {"trigger": "PreToolUse", "matcher": "",
                                 "action": {"type": "command", "command": good}},
            "another trigger": {"trigger": "PostToolUse", "action": {"type": "command", "command": good}},
            "an agent action": {"trigger": "PreToolUse", "action": {"type": "agent", "command": good}},
            "another root": {"trigger": "PreToolUse",
                             "action": {"type": "command", "command": self.kiro_command(root=self.work)}},
            "a relative hook path": {"trigger": "PreToolUse",
                                     "action": {"type": "command", "command": f"python3 adapters/kiro/hook.py --root {self.root}"}},
            "the Claude Code hook": {"trigger": "PreToolUse", "action": {"type": "command", "command":
                                     f"python3 {self.src / 'adapters' / 'claude_code' / 'hook.py'} --root {self.root}"}},
            "extra arguments": {"trigger": "PreToolUse", "action": {"type": "command", "command": good + " --timeout 1"}},
            "a second command after it": {"trigger": "PreToolUse", "action": {"type": "command", "command": good + "; true"}},
            "a command before it": {"trigger": "PreToolUse", "action": {"type": "command", "command": "true && " + good}},
            "two spaces": {"trigger": "PreToolUse", "action": {"type": "command", "command": good.replace(" --root", "  --root")}},
            "bash as the program": {"trigger": "PreToolUse",
                                    "action": {"type": "command", "command": f"bash {hook_path} --root {self.root}"}},
            "a relative python": {"trigger": "PreToolUse",
                                  "action": {"type": "command", "command": f"bin/python3 {hook_path} --root {self.root}"}},
            "the command as a list": {"trigger": "PreToolUse", "action": {"type": "command", "command": good.split(" ")}},
        }
        for label, hook in bad.items():
            with self.subTest(case=label):
                self.kiro_hook_file(hook=hook)
                self.assert_refused()

    def test_files_that_are_not_v1_hook_files_are_refused(self):
        good_hook = {"trigger": "PreToolUse", "action": {"type": "command", "command": self.kiro_command()}}
        for label, data in {"no version": {"hooks": [good_hook]}, "version v2": {"version": "v2", "hooks": [good_hook]},
                            "hooks not a list": {"version": "v1", "hooks": good_hook}, "a list": [good_hook]}.items():
            with self.subTest(case=label):
                self.kiro_hook_file(data=data)
                self.assert_refused()

    def test_broken_big_and_linked_files_are_skipped_and_named(self):
        self.kiro_hook_file(data="{not json", name="broken.json")
        r = self.assert_refused()
        self.assertIn("broken.json is not valid JSON", r.stdout)
        self.kiro_hook_file(data=" " * (1024 * 1024) + "{}", name="big.json")
        r = self.assert_refused()
        self.assertIn("big.json is larger than", r.stdout)
        real = self.kiro_hook_file(folder=self.tmp / "elsewhere")
        os.symlink(real, self.work / ".kiro" / "hooks" / "linked.json")
        r = self.assert_refused()
        self.assertIn("linked.json is not a regular file", r.stdout)

    def test_a_good_file_next_to_a_broken_one_is_still_found(self):
        self.kiro_hook_file(data="{not json", name="a-broken.json")
        self.kiro_hook_file(name="b-good.json")
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("skipped:", r.stdout)

    def test_files_not_ending_in_json_are_ignored(self):
        self.kiro_hook_file(name="umwayi.json.off")
        self.assert_refused()

    def test_a_root_with_a_space_is_refused_for_kiro(self):
        root = self.tmp / "my root"
        root.mkdir()
        (root / "agents.yaml").write_text(kiro_agent_text().replace("{work}", str(self.work)), encoding="utf-8")
        self.kiro_hook_file(command=self.kiro_command(root=root))
        r = self.umwayi("check", "helper", root=root)
        self.assertEqual(r.returncode, 2)
        self.assertIn("has a space", r.stdout)

    def test_kiro_versions(self):
        for out, code in (("kiro-cli 2.27.0", 2), ("2.27.1", 0), ("kiro-cli 3.0.0", 0), ("kiro-cli", 2)):
            with self.subTest(output=out):
                self.kiro_hook_file()
                self.assertEqual(self.check(extra={"FAKE_KIRO_VERSION": out}).returncode, code)

    def test_the_kiro_argument_lists(self):
        self.kiro_hook_file()
        r = self.check()
        run, chat = self.argv_line(r, "run"), self.argv_line(r, "chat")
        self.assertEqual(run, [str(self.bin / "kiro-cli"), "chat", "--v3", "--no-interactive",
                               "--trust-tools=read_file,grep_search"])
        self.assertIn("with the prompt on stdin", r.stdout)
        self.assertNotIn("PROMPT", run)
        self.assertEqual(chat, [str(self.bin / "kiro-cli"), "chat", "--v3"])

    def test_acp_chat_uses_the_v3_acp_server(self):
        self.write_agents(kiro_agent_text("acp"))
        self.kiro_hook_file()
        r = self.check()
        self.assertEqual(self.argv_line(r, "chat"), [str(self.bin / "kiro-cli"), "acp", "--agent-engine=v3"])


class ArgumentListTests(unittest.TestCase):
    """In process: every list the builders can make, for every valid agent shape (10.R5.7)."""

    ROOT = Path("/srv/umwayi-root")
    PY = "/usr/bin/python3"

    def shapes(self):
        for max_turns, timeout in itertools.product((None, 1, 200), (1, 30, 720)):
            yield agents.Agent("a", "claude-code", "claude", "cli", "/w", max_turns=max_turns, timeout_minutes=timeout)
        for transport, kiro_agent, tools in itertools.product(
                ("cli", "acp"), (None, "site-agent"), ((), ("read_file",), agents.KIRO_TOOL_IDS)):
            if transport == "acp" and kiro_agent:
                continue
            yield agents.Agent("k", "kiro", "kiro-cli", transport, "/w", kiro_agent=kiro_agent, trust_tools=tools)

    def test_no_list_holds_a_forbidden_flag_and_each_has_its_gate(self):
        n = 0
        for agent in self.shapes():
            for mode in (agents.RUN, agents.CHAT):
                for prompt in ("fix the tests", "please run --bare and bypassPermissions --trust-all-tools"):
                    argv, stdin = agents.build_argv(agent, mode, "/bin/x", self.ROOT, self.PY,
                                                    prompt=prompt if mode == agents.RUN else None)
                    n += 1
                    with self.subTest(agent=agent, mode=mode, prompt=prompt):
                        flags = argv[:-1] if agent.platform == "claude-code" and mode == agents.RUN else argv
                        for bad in agents.FORBIDDEN_FLAGS:
                            self.assertNotIn(bad, flags)
                        self.assertNotIn("bypassPermissions", " ".join(flags))
                        self.assertEqual(argv[0], "/bin/x")
                        if agent.platform == "claude-code":
                            self.assertEqual(argv[argv.index("--permission-mode") + 1], "default")
                            self.assertEqual(argv.count("--settings"), 1)
                            self.assertIsNone(stdin)
                            if mode == agents.RUN:
                                self.assertEqual(argv[-1], prompt)
                        elif mode == agents.RUN:
                            self.assertEqual(argv[1:4], ["chat", "--v3", "--no-interactive"])
                            self.assertEqual(stdin, prompt)
                            self.assertNotIn(prompt, argv)
                        elif agent.transport == "acp":
                            self.assertEqual(argv[1:], ["acp", "--agent-engine=v3"])
                        else:
                            self.assertEqual(argv[1:3], ["chat", "--v3"])
        self.assertGreater(n, 50)

    def test_trust_tools_never_widens_to_all(self):
        a = agents.Agent("k", "kiro", "kiro-cli", "cli", "/w", trust_tools=agents.KIRO_TOOL_IDS)
        argv, _ = agents.build_argv(a, agents.RUN, "/bin/k", self.ROOT, self.PY, prompt="x")
        self.assertEqual(argv[-1], "--trust-tools=" + ",".join(agents.KIRO_TOOL_IDS))
        a = agents.Agent("k", "kiro", "kiro-cli", "cli", "/w")
        argv, _ = agents.build_argv(a, agents.RUN, "/bin/k", self.ROOT, self.PY, prompt="x")
        self.assertFalse(any(w.startswith("--trust") for w in argv))

    def test_the_settings_json_is_the_fixed_template(self):
        s = json.loads(agents.claude_settings(self.PY, Path("/u/adapters/claude_code/hook.py"), self.ROOT))
        self.assertEqual(s, {"disableAllHooks": False, "hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{
            "type": "command", "command": self.PY, "args": ["/u/adapters/claude_code/hook.py", "--root", str(self.ROOT)],
            "timeout": 30, "onFailure": "block"}]}]}})

    def test_prompts_that_cannot_be_passed_safely_are_usage_errors(self):
        claude = agents.Agent("a", "claude-code", "claude", "cli", "/w")
        kiro = agents.Agent("k", "kiro", "kiro-cli", "cli", "/w")
        for agent, prompt in ((claude, "-p hello"), (claude, "--bare"), (claude, ""), (claude, "   "),
                              (claude, None), (claude, "a\x00b"), (kiro, "a\x00b"), (kiro, ""),
                              (claude, "x" * (100 * 1024 + 1)), (kiro, "é" * (60 * 1024))):
            with self.subTest(platform=agent.platform, prompt=(prompt or "")[:10]):
                with self.assertRaises(UsageError):
                    agents.build_argv(agent, agents.RUN, "/bin/x", self.ROOT, self.PY, prompt=prompt)
        argv, stdin = agents.build_argv(kiro, agents.RUN, "/bin/x", self.ROOT, self.PY, prompt="-starts with a dash")
        self.assertEqual(stdin, "-starts with a dash")  # on stdin a dash is harmless

    def test_a_forbidden_flag_stops_the_build(self):
        for word in agents.FORBIDDEN_FLAGS + ("--permission-mode=bypassPermissions",):
            with self.subTest(word=word):
                with self.assertRaises(RuntimeError):
                    agents._assert_allowed(["/bin/claude", word])
        self.assertEqual(agents._assert_allowed(["/bin/claude", "--bare"], skip=1), ["/bin/claude", "--bare"])

    def test_the_platform_table_is_fixed(self):
        self.assertEqual(sorted(agents.PLATFORMS), ["claude-code", "kiro"])
        self.assertEqual(agents.PLATFORMS["claude-code"].commands, ("claude",))
        self.assertEqual(agents.PLATFORMS["kiro"].commands, ("kiro-cli",))
        self.assertEqual(agents.PLATFORMS["claude-code"].transports, ("cli",))
        self.assertEqual(agents.PLATFORMS["claude-code"].min_version, (2, 1, 295))
        self.assertEqual(agents.PLATFORMS["kiro"].min_version, (2, 27, 1))
        for p in agents.PLATFORMS.values():
            self.assertTrue((REPO / p.hook).is_file())

    def test_parse_version(self):
        self.assertEqual(agents.parse_version(b"2.1.300 (Claude Code)"), (2, 1, 300))
        self.assertEqual(agents.parse_version(b"kiro-cli 2.27.1\n"), (2, 27, 1))
        self.assertIsNone(agents.parse_version(b"v2.1"))
        self.assertIsNone(agents.parse_version(b"x" * 5000 + b" 9.9.9"))  # only the first 4096 bytes are read


class CodeGuardTests(unittest.TestCase):
    def _calls(self):
        """Every subprocess.X(...) call in agents.py, with the name of the function it is in."""
        import ast
        tree = ast.parse((REPO / "umwayi" / "agents.py").read_text(encoding="utf-8"))
        found = []
        for fn in ast.walk(tree):
            if isinstance(fn, ast.FunctionDef):
                for n in ast.walk(fn):
                    if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                            and isinstance(n.func.value, ast.Name) and n.func.value.id == "subprocess"):
                        found.append((fn.name, n.func.attr, {k.arg: k.value for k in n.keywords}))
        return tree, found

    def test_two_program_starts_each_with_an_argument_list_and_no_shell(self):
        _, calls = self._calls()
        self.assertEqual(sorted((f, attr) for f, attr, _ in calls), [("_run_child", "run"), ("_start", "Popen")])
        for fname, attr, kw in calls:
            with self.subTest(call=f"{fname}: subprocess.{attr}"):
                self.assertIs(kw["shell"].value, False)
                if attr == "run":
                    self.assertIn("timeout", kw)
                    self.assertIn("input", kw)
                else:
                    self.assertIs(kw["start_new_session"].value, True)  # its own process group, so all of it can be stopped
        src = (REPO / "umwayi" / "agents.py").read_text(encoding="utf-8")
        for bad in ("os.system", "os.popen", "os.exec", "os.spawn", "shell=True", "pty."):
            self.assertNotIn(bad, src)
        self.assertNotRegex(src, r"(?m)^\s*(import|from)\s+adapters")

    def test_the_agent_argument_list_comes_only_from_build_argv(self):
        import ast
        tree, _ = self._calls()
        starts = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                  and n.func.attr == "_start"]
        self.assertEqual(len(starts), 1)
        self.assertEqual(starts[0].args[0].id, "argv")
        src = (REPO / "umwayi" / "agents.py").read_text(encoding="utf-8")
        self.assertEqual(src.count("argv, stdin_text = build_argv("), 1)

    def test_agents_py_never_writes_a_file_itself(self):
        import ast
        tree = ast.parse((REPO / "umwayi" / "agents.py").read_text(encoding="utf-8"))
        writes = {"write_text", "write_bytes", "mkdir", "unlink", "rmdir", "rename", "touch", "chmod",
                  "symlink_to", "replace", "makedirs", "remove"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                self.assertNotIn(node.attr, writes)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
                self.assertEqual(node.args[1].value, "rb", "agents.py may only open files to read them")


if __name__ == "__main__":
    unittest.main()
