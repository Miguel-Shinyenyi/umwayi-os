"""Layer 10 part 8, task 10.48: the OpenCode chat start (requirement 10.R13 items 10 to 12, design.md part 8).

Written before the code. Every test runs `python -m umwayi agent chat o` as a real child process, with the fake
`opencode acp` of tests/agents/fake_opencode.py (task 10.47) first on PATH and a copy of the umwayi source tree. The
fake reads the inline config umwayi passes, writes the canary the way the plugin does, and records every ACP message it
gets, so a test can say exactly what was sent and when.

What a start does: the kill switch, the rules, the run lock and the six gate checks (10.46), then a private folder
(0700, outside the root and the workdir) and a fresh token, the inline config, `opencode acp` with the allow-listed
environment (and OPENCODE_CONFIG_CONTENT), `initialize` with `clientCapabilities: {}`, `session/new` with no _meta,
and then the wait of at most 30 s for the canary file to hold exactly the token. Only then does the owner's first line
go to the agent. The `model` config option of the `session/new` answer must equal the agent's model.

Each failure below gives: the exit code, one refusal entry, nothing of the owner sent to the agent, nothing alive, and
the folder gone. The folder is also gone after a normal end, the kill switch, SIGTERM and a crash of the agent.
"""

import json
import os
import re
import signal
import subprocess
import sys
import time
import unittest
from pathlib import Path

from umwayi import acp, agents

from tests.agents.support import SECRET, alive
from tests.agents.test_agents_opencode_gate import GateCase, YES_RULE

HEX32 = re.compile(r"^[0-9a-f]{32}$")
REFUSED_GATE = "Refused agent o: the first gate could not be confirmed in the ACP session"
NOT_SENT = "The first gate could not be confirmed in the ACP session. Nothing was sent."
SIGN_IN = "Run opencode auth login first, then try again."


class ChatCase(GateCase):
    def setUp(self):
        super().setUp()
        self.write_rules(YES_RULE)
        self.roomy_budget()  # several starts in one test must not meet the budget limit
        self.tmpdir = self.tmp / "tmpdir"  # TMPDIR of umwayi, so a leftover canary folder can be seen
        self.tmpdir.mkdir()

    def spec(self, acp_spec=None):
        self.fake_opencode(acp=acp_spec or {})

    def env_extra(self, extra=None):
        return dict({"TMPDIR": str(self.tmpdir)}, **(extra or {}))

    def run_chat(self, owner="", extra=None, fault=None, acp_spec=None):
        if acp_spec is not None:
            self.spec(acp_spec)
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "chat", "o"],
                           input=owner, capture_output=True, text=True, timeout=180,
                           env=self.env(self.env_extra(extra), fault), cwd=str(self.tmp))
        self.assertIn(r.returncode, {0, 2, 3, 64}, r.stdout + r.stderr)
        self.alive_at_exit = self.agent_pids_alive()
        self.wait_root_quiet()
        return r

    def start_chat(self, extra=None):
        p = subprocess.Popen([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "chat", "o"],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             env=self.env(self.env_extra(extra)), cwd=str(self.tmp))
        self.addCleanup(self._reap, p)
        return p

    def _reap(self, p):
        if p.poll() is None:
            p.kill()
        p.communicate(timeout=30)
        for c in self.calls():
            if c.get("pid") and alive(c["pid"]):
                os.kill(c["pid"], signal.SIGKILL)

    def finish(self, p, timeout=90):
        p.wait(timeout=timeout)
        self.alive_at_exit = self.agent_pids_alive()
        for pid in self.alive_at_exit:
            os.kill(pid, signal.SIGKILL)
        self.wait_root_quiet()
        if p.stdin is not None and p.stdin.closed:
            p.stdin = None
        out, err = p.communicate(timeout=30)
        return p.returncode, out, err

    def wait_for(self, pred, what, timeout=60):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            for c in self.calls():
                if pred(c):
                    return c
            time.sleep(0.05)
        self.fail(f"timed out waiting for {what}; calls: {self.calls()}")

    # ------------------------------------------------------------ what the fake saw

    def sent(self, method=None):
        msgs = [c["msg"] for c in self.calls() if c.get("event") == "acp_in"]
        return [m for m in msgs if method is None or m.get("method") == method]

    def methods(self):
        return [m.get("method") for m in self.sent() if "method" in m]

    def start_record(self):
        [rec] = [c for c in self.calls() if c.get("mode") == "acp"]
        return rec

    def plugin_options(self):
        return json.loads(self.start_record()["config_content"])["plugins"][0]["options"]

    def leftovers(self):
        return sorted(p.name for p in self.tmpdir.iterdir() if p.name.startswith(agents.CANARY_PREFIX))

    def log_text(self):
        p = self.root / "LOGBOOK.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def kill_on(self):
        (self.root / ".umwayi").mkdir(exist_ok=True)
        (self.root / ".umwayi" / "KILL").write_text("", encoding="utf-8")

    def assert_agent_gone(self):
        self.assertEqual(self.alive_at_exit, [], "an agent process was still running when umwayi exited")
        pids = [c["pid"] for c in self.calls() if c.get("mode") == "acp" or c.get("event") == "spawn"]
        self.assertTrue(pids)
        for pid in pids:
            self.assertFalse(alive(pid), f"pid {pid} is still alive")

    def assert_nothing_left(self):
        self.assertEqual(self.leftovers(), [], "a canary folder was left behind")

    def refusals(self):
        return [e.added for e in self.run_entries() if e.added.startswith("Refused agent")]

    def assert_refused_in_session(self, r, entry, text):
        """Exit 2, one entry, nothing of the owner sent, nothing alive, folder gone."""
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(text, r.stdout)
        self.assertEqual([e.added for e in self.run_entries() if not e.added.startswith("Started")],
                         [entry], "exactly one entry besides the start")
        self.assertNotIn("session/prompt", self.methods())
        self.assertNotIn("you said", r.stdout)
        self.assertNotIn(SECRET, self.log_text())
        self.assert_nothing_left()
        self.assert_agent_gone()


# ------------------------------------------------------------------------------------------------ the start


class StartTests(ChatCase):
    def test_a_whole_chat_with_the_canary_seen(self):
        self.spec()
        r = self.run_chat(f"hello {SECRET}\n:quit\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.methods(), ["initialize", "session/new", "session/prompt"])  # no set_mode, no authenticate
        [init] = self.sent("initialize")
        self.assertEqual(init["params"]["clientCapabilities"], {})
        [new] = self.sent("session/new")
        self.assertEqual(new["params"], {"cwd": str(self.deep), "mcpServers": []})  # no _meta
        self.assertIn(f"you said: hello {SECRET}", r.stdout)
        self.assertIn("Connected.", r.stdout)
        [prompt] = self.sent("session/prompt")
        self.assertEqual(prompt["params"]["prompt"], [{"type": "text", "text": f"hello {SECRET}"}])
        started = [e.added for e in self.run_entries()]
        self.assertTrue(started[0].startswith("Started agent o (opencode, acp, chat): "), started)
        self.assertEqual(len(started), 2, started)  # the start and the end
        self.assertTrue(started[1].startswith("Agent o exited with code 0 after "), started)
        self.assert_nothing_left()
        self.assert_agent_gone()

    def test_the_fake_is_started_as_opencode_acp_in_its_own_session_with_the_workdir(self):
        self.spec()
        self.run_chat(":quit\n")
        rec = self.start_record()
        self.assertEqual(rec["argv"], ["acp"])
        self.assertEqual(rec["cwd"], str(self.deep))
        self.assertEqual(rec["sid"], rec["pid"])  # a session of its own
        self.assertEqual(rec["pgid"], rec["pid"])

    def test_the_environment_is_the_allow_list_and_the_config_is_umwayis_own(self):
        planted = {"ANTHROPIC_API_KEY": SECRET, "OPENAI_API_KEY": SECRET, "OPENCODE_API_KEY": SECRET,
                   "OPENCODE_CONFIG": "/evil", "OPENCODE_CONFIG_DIR": "/evil", "OPENCODE_DB": "/evil",
                   "OPENCODE_PASSWORD": SECRET, "OPENCODE_DISABLE_PROJECT_CONFIG": "1", "AWS_SECRET_ACCESS_KEY": SECRET,
                   "GITHUB_TOKEN": SECRET, "NODE_OPTIONS": "--require=/evil.js", "UMWAYI_FAULT_X": SECRET,
                   "OPENCODE_CONFIG_CONTENT": '{"permissions":[]}'}
        self.spec()
        r = self.run_chat(":quit\n", extra=planted)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rec = self.start_record()
        allowed = set(agents.OPENCODE_ENV_NAMES) | {"OPENCODE_CONFIG_CONTENT"}
        self.assertLessEqual(set(rec["env_keys"]), allowed, sorted(set(rec["env_keys"]) - allowed))
        self.assertIn("OPENCODE_CONFIG_CONTENT", rec["env_keys"])
        for name in planted:
            if name != "OPENCODE_CONFIG_CONTENT":
                self.assertNotIn(name, rec["env_keys"])
        self.assertNotIn(SECRET, rec["config_content"])
        self.assertNotIn("/evil", rec["config_content"])

    def test_the_inline_config_is_the_one_of_10_44_for_this_folder_and_token(self):
        self.spec()
        self.run_chat(":quit\n")
        opts = self.plugin_options()
        token = opts["token"]
        self.assertRegex(token, HEX32)
        folder = os.path.dirname(opts["canary"])
        self.assertEqual(os.path.basename(opts["canary"]), "canary")
        self.assertTrue(os.path.basename(folder).startswith(agents.CANARY_PREFIX))
        self.assertEqual(os.path.dirname(folder), str(self.tmpdir))
        agent = agents.find(agents.load(self.root), "o")
        want = agents.opencode_inline_config(agent, self.root, token, folder, sys.executable, self.src)
        self.assertEqual(self.start_record()["config_content"], want)
        self.assertFalse(os.path.exists(folder))

    def test_the_folder_is_private_and_outside_the_root_and_the_workdir_while_the_chat_runs(self):
        self.spec({"turns": [[{"wait_cancel": True}]]})
        p = self.start_chat()
        p.stdin.write("go\n")
        p.stdin.flush()
        self.wait_for(lambda c: c.get("event") == "acp_in" and c["msg"].get("method") == "session/prompt", "the prompt")
        folder = os.path.dirname(self.plugin_options()["canary"])
        st = os.lstat(folder)
        self.assertEqual(st.st_mode & 0o777, 0o700)
        self.assertEqual(st.st_uid, os.getuid())
        self.assertEqual(os.lstat(os.path.join(folder, "canary")).st_mode & 0o777, 0o600)
        self.assertEqual(Path(os.path.join(folder, "canary")).read_text(), self.plugin_options()["token"])
        for other in (self.root, self.deep):
            self.assertFalse(folder.startswith(str(other) + os.sep))
        self.kill_on()
        code, out, _ = self.finish(p)
        self.assertEqual(code, 3, out)
        self.assertFalse(os.path.exists(folder))

    def test_every_start_has_its_own_folder_and_token(self):
        self.spec()
        seen = []
        for _ in range(2):
            self.fake_log.unlink(missing_ok=True)
            self.run_chat(":quit\n")
            opts = self.plugin_options()
            seen.append((opts["token"], opts["canary"]))
        self.assertNotEqual(seen[0][0], seen[1][0])
        self.assertNotEqual(seen[0][1], seen[1][1])

    def test_a_late_canary_within_the_wait_is_accepted_and_the_prompt_comes_after_it(self):
        self.spec({"canary": "late", "canary_delay": 3})
        r = self.run_chat("hello\n:quit\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        [canary] = [c for c in self.calls() if c.get("event") == "canary"]
        [prompt] = [c for c in self.calls() if c.get("event") == "acp_in" and c["msg"].get("method") == "session/prompt"]
        self.assertLess(canary["t"], prompt["t"])
        self.assertIn("you said: hello", r.stdout)

    def test_the_summary_names_the_wait(self):
        self.spec()
        r = self.run_chat(":quit\n")
        self.assertIn("Nothing you type is sent until the plugin is confirmed in the session (at most 30 s).", r.stdout)
        self.assertIn("Nothing of the conversation is logged.", r.stdout)

    def test_the_gate_wait_is_30_seconds(self):
        self.assertEqual(acp.GATE_WAIT, 30.0)

    def test_nothing_of_the_conversation_the_token_or_the_config_is_in_the_logbook(self):
        self.spec()
        self.run_chat(f"hello {SECRET}\n:quit\n")
        text = self.log_text()
        self.assertNotIn(SECRET, text)
        self.assertNotIn(self.plugin_options()["token"], text)
        self.assertNotIn("OPENCODE_CONFIG_CONTENT", text)
        self.assertNotIn('"plugins"', text)
        self.assertNotIn("you said", text)

    def test_agent_check_shows_the_start(self):
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        [line] = [ln for ln in r.stdout.splitlines() if ln.startswith("chat would start: ")]
        argv = json.loads(line[len("chat would start: "):].split(" with the allow-listed environment")[0])
        self.assertEqual(argv, [str(self.bin / "opencode"), "acp"])
        self.assertIn("only after the plugin has written the canary", line)
        self.assertIn("Gated: the checks for an OpenCode chat of agent o passed. Nothing was started.", r.stdout)
        self.assertNotIn("not built", r.stdout)
        self.assertEqual(self.started(), [])


# ------------------------------------------------------------------------------------------------ refusals


class CanaryTests(ChatCase):
    def test_never_seen(self):
        self.spec({"canary": "never"})
        r = self.run_chat(f"hello {SECRET}\n:quit\n", extra={"UMWAYI_TEST_GATE_WAIT": "3"})
        self.assert_refused_in_session(r, REFUSED_GATE, NOT_SENT)
        self.assertEqual(self.refusals(), [REFUSED_GATE])

    def test_seen_only_after_the_wait_is_over(self):
        self.spec({"canary": "late", "canary_delay": 8})
        r = self.run_chat("hello\n:quit\n", extra={"UMWAYI_TEST_GATE_WAIT": "3"})
        self.assert_refused_in_session(r, REFUSED_GATE, NOT_SENT)

    def test_a_wrong_token(self):
        self.spec({"canary": "wrong"})
        r = self.run_chat("hello\n:quit\n", extra={"UMWAYI_TEST_GATE_WAIT": "3"})
        self.assert_refused_in_session(r, REFUSED_GATE, NOT_SENT)
        [canary] = [c for c in self.calls() if c.get("event") == "canary"]
        self.assertFalse(canary["token_ok"])

    def test_a_canary_written_only_at_the_first_prompt_is_too_late(self):
        self.spec({"canary": "first_prompt"})
        r = self.run_chat("hello\n:quit\n", extra={"UMWAYI_TEST_GATE_WAIT": "3"})
        self.assert_refused_in_session(r, REFUSED_GATE, NOT_SENT)
        self.assertEqual([c for c in self.calls() if c.get("event") == "canary"], [])

    def test_the_token_plus_more_is_not_the_token(self):
        # a file that merely starts with the token, or holds it twice, is not the plugin's write
        self.spec({"canary": "never"})
        p = self.start_chat(extra={"UMWAYI_TEST_GATE_WAIT": "4"})
        p.stdin.write("hello\n")
        p.stdin.flush()
        self.wait_for(lambda c: c.get("event") == "acp_in" and c["msg"].get("method") == "session/new", "session/new")
        opts = self.plugin_options()
        Path(opts["canary"]).write_text(opts["token"] + "\n" + opts["token"], encoding="utf-8")
        code, out, _ = self.finish(p)
        self.assertEqual(code, 2, out)
        self.assertIn(NOT_SENT, out)
        self.assertNotIn("session/prompt", self.methods())

    def test_a_canary_link_to_a_file_that_holds_the_token_is_not_the_token(self):
        self.spec({"canary": "never"})
        p = self.start_chat(extra={"UMWAYI_TEST_GATE_WAIT": "4"})
        p.stdin.write("hello\n")
        p.stdin.flush()
        self.wait_for(lambda c: c.get("event") == "acp_in" and c["msg"].get("method") == "session/new", "session/new")
        opts = self.plugin_options()
        real = self.tmp / "token.txt"
        real.write_text(opts["token"], encoding="utf-8")
        os.symlink(real, opts["canary"])
        code, out, _ = self.finish(p)
        self.assertEqual(code, 2, out)
        self.assertIn(NOT_SENT, out)
        self.assertNotIn("session/prompt", self.methods())


class ModelTests(ChatCase):
    def test_another_model_is_refused_before_the_first_prompt(self):
        self.spec({"model": "ollama/other"})
        r = self.run_chat(f"hello {SECRET}\n:quit\n")
        entry = "ACP chat with agent o ended: the agent reported another model than the one of the agent"
        self.assert_refused_in_session(r, entry, "The agent reported another model than ollama/m. The chat ended (exit 2).")
        self.assertNotIn("ollama/other", r.stdout)  # what the agent said is never shown
        self.assertNotIn("ollama/other", self.log_text())

    def test_the_agents_own_model_is_accepted_for_every_route(self):
        from tests.agents.test_agents_opencode_file import ROUTES
        for provider, model in ROUTES.items():
            with self.subTest(provider=provider):
                self.write_agent(provider, model)
                self.spec()
                self.fake_log.unlink(missing_ok=True)
                r = self.run_chat("hi\n:quit\n")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                [new] = [c for c in self.calls() if c.get("mode") == "acp"]
                self.assertEqual(json.loads(new["config_content"])["model"], model)

    def test_a_model_with_a_different_case_or_a_suffix_is_another_model(self):
        for other in ("OLLAMA/M", "ollama/m ", "ollama/m2", "ollama"):
            with self.subTest(other=other):
                self.fake_log.unlink(missing_ok=True)
                self.spec({"model": other})
                r = self.run_chat("hi\n:quit\n")
                self.assertEqual(r.returncode, 2, r.stdout)
                self.assertNotIn("session/prompt", self.methods())


class AuthTests(ChatCase):
    def test_auth_required_at_session_new(self):
        self.spec({"auth_required": "session_new"})
        r = self.run_chat(f"hello {SECRET}\n:quit\n")
        entry = "ACP chat with agent o ended: the agent needs a sign in"
        self.assert_refused_in_session(r, entry, SIGN_IN)
        self.assertNotIn("kiro-cli", r.stdout)
        self.assertNotIn("authenticate", self.methods())

    def test_auth_required_at_the_first_prompt(self):
        self.spec({"auth_required": "prompt"})
        r = self.run_chat("hello\n:quit\n")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(SIGN_IN, r.stdout)
        self.assertNotIn("authenticate", self.methods())
        self.assertEqual([e.added for e in self.run_entries() if not e.added.startswith("Started")],
                         ["ACP chat with agent o ended: the agent needs a sign in"])
        self.assert_nothing_left()
        self.assert_agent_gone()

    def test_an_error_that_is_not_auth_is_not_called_a_sign_in(self):
        self.spec({"init": {"error": {"code": -32603, "message": "boom"}}})
        r = self.run_chat("hello\n")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn("auth login", r.stdout)
        self.assert_nothing_left()


class InitTests(ChatCase):
    def test_garbage_or_another_protocol_version_ends_with_2(self):
        for init in ("garbage", {"protocolVersion": 2}):
            with self.subTest(init=init):
                self.fake_log.unlink(missing_ok=True)
                self.spec({"init": init})
                r = self.run_chat("hello\n", extra={"UMWAYI_TEST_GATE_WAIT": "3"})
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertNotIn("session/prompt", self.methods())
                self.assert_nothing_left()
                self.assert_agent_gone()

    def test_tmpdir_inside_the_workdir_is_refused_and_nothing_is_started(self):
        inside = self.deep / "tmp"
        inside.mkdir()
        self.spec()
        r = self.run_chat("hello\n", extra={"TMPDIR": str(inside)})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("outside the root and the workdir", r.stdout)
        self.assertEqual(self.started(), [])
        self.assertEqual(list(inside.iterdir()), [])
        self.assertEqual(len(self.refusals()), 1)

    def test_tmpdir_inside_the_root_is_refused_and_nothing_is_started(self):
        inside = self.root / "tmp"
        inside.mkdir()
        self.spec()
        r = self.run_chat("hello\n", extra={"TMPDIR": str(inside)})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("outside the root and the workdir", r.stdout)
        self.assertEqual(self.started(), [])
        self.assertEqual(list(inside.iterdir()), [])

    def test_a_folder_path_that_opencode_would_substitute_is_refused_and_nothing_is_started(self):
        odd = self.tmp / "t{env:HOME}"  # OpenCode replaces {env:NAME} in its config, so umwayi refuses such a path
        odd.mkdir()
        self.spec()
        r = self.run_chat("hello\n", extra={"TMPDIR": str(odd)})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("{env:", r.stdout)
        self.assertEqual(self.started(), [])
        self.assertEqual(list(odd.iterdir()), [])
        self.assertEqual(len(self.refusals()), 1)

    def test_a_failing_gate_check_makes_no_folder_and_starts_nothing(self):
        (self.deep / "opencode.json").write_text("{}", encoding="utf-8")
        self.spec()
        r = self.run_chat("hello\n")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(self.started(), [])
        self.assert_nothing_left()

    def test_the_rules_say_no(self):
        self.write_rules("rules:\n  - id: o-no\n    title: t\n    text: t\n    verdict: no\n    matchers:\n"
                         "      type: agent_run\n      agent: o\n")
        self.spec()
        r = self.run_chat("hello\n")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(self.started(), [])
        self.assert_nothing_left()

    def test_the_kill_switch_before_the_start(self):
        self.kill_on()
        self.spec()
        r = self.run_chat("hello\n")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertEqual(self.started(), [])
        self.assert_nothing_left()


# ------------------------------------------------------------------------------------------------ every way out


class StopTests(ChatCase):
    """The folder is gone and nothing is alive after a normal end, the kill switch, SIGTERM and a crash."""

    def running(self, turn, **spec):
        self.spec(dict({"turns": [turn]}, **spec))
        p = self.start_chat()
        p.stdin.write("go\n")
        p.stdin.flush()
        n = sum(1 for a in turn if "spawn" in a)
        end = time.monotonic() + 60
        while len([c for c in self.calls() if c.get("event") == "spawn"]) < n:
            if time.monotonic() > end:
                self.fail(f"the fake did not start its children; calls: {self.calls()}")
            time.sleep(0.05)
        self.wait_for(lambda c: c.get("event") == "acp_in" and c["msg"].get("method") == "session/prompt", "the prompt")
        time.sleep(2.5)  # at least two watcher passes, so umwayi has seen the children in /proc
        return p

    def test_a_normal_end(self):
        self.spec()
        r = self.run_chat("hello\n:quit\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_nothing_left()
        self.assert_agent_gone()

    def test_the_end_of_input_ends_the_chat(self):
        self.spec()
        r = self.run_chat("hello\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_nothing_left()

    def test_an_agent_that_ignores_the_end_of_its_input_is_stopped(self):
        self.spec({"ignore_eof": True})
        r = self.run_chat("hello\n:quit\n")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("did not exit after the chat ended", r.stdout)
        self.assert_nothing_left()
        self.assert_agent_gone()

    def test_the_kill_switch_stops_the_group_and_every_descendant(self):
        p = self.running([{"spawn": True}, {"wait_cancel": True}], ignore_eof=True)
        self.kill_on()
        code, out, _ = self.finish(p)
        self.assertEqual(code, 3, out)
        self.assertIn("The kill switch stopped agent o (exit 3).", out)
        self.assert_agent_gone()
        self.assert_nothing_left()

    def test_quit_stops_a_command_left_by_a_clean_exit(self):
        self.spec({"turns": [[{"spawn": True}, {"chunk": "started it"}]]})
        r = self.run_chat("hello\n:quit\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_agent_gone()
        self.assert_nothing_left()

    def test_quit_stops_a_command_in_its_own_session_left_by_a_clean_exit(self):
        self.spec({"turns": [[{"spawn_setsid": True}, {"chunk": "started it"}]]})
        r = self.run_chat("hello\n:quit\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_agent_gone()
        self.assert_nothing_left()

    def test_sigterm_to_umwayi(self):
        p = self.running([{"spawn": True}, {"wait_cancel": True}])
        p.send_signal(signal.SIGTERM)
        code, out, _ = self.finish(p)
        self.assertEqual(code, 2, out)
        self.assertEqual(self.run_entries()[-1].added, "Agent o was stopped: umwayi got SIGTERM")
        self.assert_agent_gone()
        self.assert_nothing_left()

    def test_the_agent_crashes_in_a_turn(self):
        self.spec({"turns": [[{"chunk": "x"}, {"exit": 7}]]})
        r = self.run_chat("hello\n:quit\n")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn(SECRET, self.log_text())
        self.assert_nothing_left()
        self.assert_agent_gone()

    def test_the_agent_dies_before_session_new_is_answered(self):
        self.spec({"auth_required": "session_new", "stderr": "boom"})
        r = self.run_chat("hello\n")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assert_nothing_left()
        self.assert_agent_gone()

    def test_the_timeout_stops_everything(self):
        self.write_agents(self.agent_text(timeout=1))
        p_extra = {"UMWAYI_TEST_MINUTE": "15"}
        self.spec({"turns": [[{"wait_cancel": True}]]})
        p = self.start_chat(extra=p_extra)
        p.stdin.write("go\n")
        p.stdin.flush()
        code, out, _ = self.finish(p, timeout=120)
        self.assertEqual(code, 2, out)
        self.assertIn("timeout of 1 min", out)
        self.assert_agent_gone()
        self.assert_nothing_left()

    def agent_text(self, timeout):
        from tests.agents.test_agents_opencode_file import oc
        return oc(provider="ollama", model="ollama/m", workdir=str(self.deep), extra=f"    timeout_minutes: {timeout}\n")


if __name__ == "__main__":
    unittest.main()
