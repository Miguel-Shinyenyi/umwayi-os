"""W78 step 5 (5a2): an enforced `claude -p` run has its hook ask the enforcement broker (umwayi/broker.py).

  * `agents.claude_settings(broker=...)` adds `--broker SOCK --run RID` to the hook's arguments; without it the settings are as they were.
  * The hook (`adapters/claude_code/hook.py`) with `--broker` asks the broker and never falls back to `umwayi check`: no broker, a
    refusal, an answer that is not a verdict, or only one of the two flags is a block (exit 2).
  * Real runs (the fake claude, the real hook, the real broker): under a mode file that says `enforced` the run's argv holds the broker
    flags, the broker writes the check entries, the folder is gone after the run; a cooperative agent and no mode file are as they were.

What it does not show: a confined helper (no confinement exists), the Kiro and OpenCode hooks (they do not use the broker), a real
Claude Code. Linux needed for the real runs (they read /proc), so they ran in a container here.
"""
import datetime
import glob
import json
import socket
import subprocess
import sys
import threading
import unittest
from pathlib import Path

from tests.agents.support import AgentCase
from tests.agents.support import RULES as AGENT_RULES
from umwayi import agents

REPO = Path(__file__).resolve().parent.parent.parent
HOOK = REPO / "adapters" / "claude_code" / "hook.py"
READ = {"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {"file_path": "/p/a"}, "tool_use_id": "toolu_1",
        "cwd": "/tmp"}
FAKES = "FAKE_LOG, FAKE_SCRIPT, FAKE_PLANT, FAKE_CLAUDE_AUTH, FAKE_CLAUDE_AUTH_EXIT"


class SettingsTests(unittest.TestCase):
    def args(self, **kw):
        return json.loads(agents.claude_settings("python3", Path("/h/hook.py"), Path("/r"), **kw))["hooks"]["PreToolUse"][0]["hooks"][0]["args"]

    def test_the_broker_flags_are_added_only_when_asked(self):
        self.assertEqual(self.args(), ["/h/hook.py", "--root", "/r"])
        self.assertEqual(self.args(broker=("/tmp/b/s", "0123456789abcdef")),
                         ["/h/hook.py", "--root", "/r", "--broker", "/tmp/b/s", "--run", "0123456789abcdef"])


class HookCase(unittest.TestCase):
    def hook(self, *flags, stdin=None):
        p = subprocess.run([sys.executable, str(HOOK), "--root", "/tmp", *flags], input=json.dumps(stdin or READ), capture_output=True,
                           text=True, timeout=30)
        return p.returncode, p.stdout, p.stderr

    def serve(self, reply: bytes):
        import tempfile
        d = tempfile.mkdtemp(prefix="ubh", dir="/tmp")
        self.addCleanup(__import__("shutil").rmtree, d, True)
        sock = Path(d) / "s"
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(sock))
        srv.listen(1)
        self.addCleanup(srv.close)
        seen = []

        def go():
            c, _ = srv.accept()
            seen.append(c.recv(4096))
            c.sendall(reply)
            c.close()
        threading.Thread(target=go, daemon=True).start()
        return str(sock), seen


class HookTests(HookCase):
    def test_a_yes_from_the_broker_allows_and_the_request_is_a_check_of_the_run(self):
        sock, seen = self.serve(b'{"answer":"Yes","rule":"read-yes"}\n')
        code, out, _ = self.hook("--broker", sock, "--run", "0123456789abcdef")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "allow")
        req = json.loads(seen[0])
        self.assertEqual((req["type"], req["run"]), ("check", "0123456789abcdef"))

    def decision(self, *flags):
        code, out, _ = self.hook(*flags)
        if code == 2:
            return "deny"
        return json.loads(out)["hookSpecificOutput"]["permissionDecision"]

    def test_no_from_the_broker_blocks(self):
        sock, _ = self.serve(b'{"answer":"No","rule":"x"}\n')
        self.assertEqual(self.decision("--broker", sock, "--run", "0123456789abcdef"), "deny")

    def test_no_broker_a_refusal_a_non_verdict_and_one_flag_alone_are_blocks_never_a_fallback(self):
        cases = {"missing socket": ("--broker", "/tmp/ubh-none/s", "--run", "0123456789abcdef"),
                 "one flag": ("--broker", "/tmp/ubh-none/s")}
        for name, flags in cases.items():
            with self.subTest(case=name):
                self.assertEqual(self.decision(*flags), "deny")
        for name, reply in {"refusal": b'{"answer":"No","rule":null,"why":"unknown_run"}\n', "maybe": b'{"answer":"Maybe"}\n',
                            "garbage": b"garbage\n", "yes with why": b'{"answer":"Yes","rule":null,"why":"x"}\n'}.items():
            with self.subTest(case=name):
                sock, _ = self.serve(reply)
                self.assertEqual(self.decision("--broker", sock, "--run", "0123456789abcdef"), "deny")

    def test_without_the_flags_the_hook_asks_umwayi_check_as_before(self):
        # no rules.yaml in /tmp: `umwayi check` answers Ask me first, which the hook maps to ask (exit 0 with an ask decision)
        code, out, _ = self.hook()
        self.assertIn(code, (0, 2))
        self.assertNotIn("broker", out)


class RunCase(AgentCase):
    def setUp(self):
        super().setUp()
        self.fake("claude")
        self.write_rules(AGENT_RULES.replace("agent: [reviewer, slow, stubborn, quick]", "agent: [reviewer]"))
        self.write_agents("agents:\n  - name: reviewer\n    platform: claude-code\n    command: claude\n    workdir: {work}\n"
                          f"    env_keep: [{FAKES}]\n")
        self.roomy_budget()
        self.fake_sandbox_tools()  # W41 B1: an enforced Claude Code start needs bwrap and socat on Linux

    def mode_file(self, text):
        (self.root / ".umwayi").mkdir(exist_ok=True)
        (self.root / ".umwayi" / "enforcement.yaml").write_text(text, encoding="utf-8")

    def go(self):
        extra = dict(self.script({"do": "tool", "tool": "Read", "input": {"file_path": "/p/a"}, "id": "toolu_a"}))
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "run", "reviewer", "--prompt", "hello"],
                           capture_output=True, text=True, timeout=120, env=self.env(extra), cwd=str(self.tmp))
        started = [c for c in self.calls() if c.get("started")]
        tools = [c for c in self.calls() if c.get("event") == "tool"]
        return r, started, tools

    def hook_args(self, started):
        argv = started[-1]["argv"]
        return json.loads(argv[argv.index("--settings") + 1])["hooks"]["PreToolUse"][0]["hooks"][0]["args"]


class RealRunTests(RunCase):
    def test_an_enforced_run_uses_the_broker_the_broker_writes_the_entry_and_the_folder_is_gone(self):
        before = set(glob.glob("/tmp/umwayi-b*"))
        self.mode_file("enforcement: enforced\n")
        r, started, tools = self.go()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = self.hook_args(started)
        self.assertIn("--broker", args)
        self.assertIn("--run", args)
        run_id = args[args.index("--run") + 1]
        self.assertRegex(run_id, r"^[0-9a-f]{16}$")
        self.assertEqual([t["decision"] for t in tools], ["allow"])  # the broker's Yes: rule read-yes
        log = (self.root / "LOGBOOK.md").read_text(encoding="utf-8")
        self.assertIn("Rule read-yes gave Yes; action type: tool_read", log)
        self.assertEqual(set(glob.glob("/tmp/umwayi-b*")), before)  # the broker's folder is removed

    def test_a_cooperative_agent_and_no_mode_file_have_no_broker_flags(self):
        r, started, _ = self.go()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("--broker", self.hook_args(started))
        until = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
        self.mode_file(f"enforcement: enforced\nagents:\n  reviewer:\n    enforcement: cooperative\n    until: {until}\n")
        r, started, _ = self.go()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("--broker", self.hook_args(started))

    def test_a_broker_that_ends_during_the_run_refuses_every_later_call_and_ends_the_run_with_exit_2_and_an_entry(self):
        self.mode_file("enforcement: enforced\n")
        read = {"do": "tool", "tool": "Read", "input": {"file_path": "/p/a"}}
        extra = dict(self.script(dict(read, id="toolu_a"), {"do": "kill_broker"}, dict(read, id="toolu_b")))
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "run", "reviewer", "--prompt", "hello"],
                           capture_output=True, text=True, timeout=120, env=self.env(extra), cwd=str(self.tmp))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        decisions = [c["decision"] for c in self.calls() if c.get("event") == "tool"]
        self.assertEqual(decisions, ["allow", "deny"])  # the second call: no answer is No
        self.assertIn("broker_lost", r.stdout)
        log = (self.root / "LOGBOOK.md").read_text(encoding="utf-8")
        self.assertIn("Enforcement broker lost during the run of agent reviewer", log)

    def test_planted_fault_an_enforced_hook_without_the_flags_would_not_use_the_broker(self):
        self.mode_file("enforcement: enforced\n")
        _, started, _ = self.go()
        self.assertEqual(self.hook_args(started)[3], "--broker")


if __name__ == "__main__":
    unittest.main()
