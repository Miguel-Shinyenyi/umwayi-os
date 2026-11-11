"""Layer 10 part 8, task 10.45: the umwayi plugin for OpenCode (requirement 10.R13.7, design.md part 8 "The plugin").

Written before the plugin. The plugin is plain JavaScript that OpenCode 2.x runs in its own process, so these tests run
it under `node`, through tests/adapters/opencode_plugin_harness.mjs: a fake `ctx` that is as strict as the real one was
seen to be on OpenCode 2.2.7 (10.42), and a fake hook script (tests/adapters/fake_gate_hook.py) that exits as told. The
last class runs the real layer 9 generic adapter (`--platform opencode`) with the starter rules of
adapters/opencode/rules.example.yaml, on a real umwayi root.

Every test that needs node fails with a message when `node` is not on PATH. It is never skipped: a gate whose tests
did not run is not tested.

What the plugin must do, and these tests check:
  * every tool call is sent to the hook as {"tool_name", "tool_input"}; exit 0 with an "allow" line lets it go on; exit 3
    with an "ask" line lets it go on only for the nine tools OpenCode asks permission for (10.42), because the permission
    request then asks the owner; everything else throws, and a throw stops the call;
  * "everything else" is every other exit code, a timeout, a start error, a signal, output that is not the one JSON line
    of the adapter or that disagrees with the exit code, a tool name that is not a string, an input that is not an
    object, and bad options; the thrown text is fixed and never holds the input, the output or an option;
  * the evaluate hook turns allow into ask; session.created writes the token once, mode 0600, without overwriting;
  * the plugin touches nothing else of ctx, prints nothing, and is small, with only node: imports.
"""

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.adapters.support import REPO, AdapterCase

PLUGIN = REPO / "adapters" / "opencode" / "plugin" / "index.js"
HARNESS = Path(__file__).with_name("opencode_plugin_harness.mjs")
FAKE_HOOK = Path(__file__).with_name("fake_gate_hook.py")
STDIO_HOOK = REPO / "adapters" / "stdio" / "hook.py"
RULES_EXAMPLE = REPO / "adapters" / "opencode" / "rules.example.yaml"

TOKEN = "0123456789abcdef0123456789abcdef"
SECRET = "sk-live-PLUGIN-TEST-SECRET"
DENIED = "umwayi: this tool call was not allowed by the rules"
BAD_OPTIONS = "umwayi: the gate options are missing or wrong"
ASKED = ["read", "glob", "grep", "write", "edit", "shell", "webfetch", "question", "subagent"]
NOT_ASKED = ["execute", "opencode_worktree_list", "opencode_worktree_remove", "opencode_session_move",
             "opencode_list_mcp_resources", "opencode_models", "patch", "list", "websearch", "skill",
             "github_create_issue", "Read", "READ", "read ", " read", "read\n", "shell2", "unknown_tool", "x"]
GO = {"ok": True, "returned": "undefined"}


class _Sentinel:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name


ABSENT = _Sentinel("ABSENT")  # the key is left out
DEFAULT = _Sentinel("DEFAULT")  # the usual good value


def need_node() -> str:
    node = shutil.which("node")
    if node is None:
        raise AssertionError("node is not on PATH. The OpenCode plugin tests run the plugin under node; "
                             "install Node 18 or later (GitHub's ubuntu runners have it).")
    return node


class PluginCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = need_node()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="umwayi-plugin-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.log = self.tmp / "hook.log"
        self.canary = self.tmp / "canary"

    # --------------------------------------------------------------- building a case

    def hook(self, exit=0, say="auto", sleep=None, stderr=None, extra=()):
        argv = [sys.executable, str(FAKE_HOOK), "--exit", str(exit), "--say", say, "--log", str(self.log), *extra]
        if sleep is not None:
            argv += ["--sleep", str(sleep)]
        if stderr is not None:
            argv += ["--stderr", stderr]
        return argv

    def options(self, hook=DEFAULT, **over):
        opts = {"hook": self.hook() if hook is DEFAULT else hook, "canary": str(self.canary), "token": TOKEN}
        opts.update(over)
        return {k: v for k, v in opts.items() if v is not ABSENT}

    def case(self, name, steps, options=DEFAULT, **flags):
        spec = dict(name=name, steps=steps, **flags)
        if options is DEFAULT:
            options = self.options()
        if options is not ABSENT:  # ABSENT: ctx.options is undefined; None: it is null
            spec["options"] = options
        return spec

    def run_cases(self, cases, timeout_ms=None, timeout=120):
        script = {"timeoutMs": timeout_ms, "cases": cases}
        r = subprocess.run([self.node, str(HARNESS), str(PLUGIN)], input=json.dumps(script), capture_output=True,
                           text=True, timeout=timeout)
        out = json.loads(r.stdout) if r.stdout.strip() else {}
        self.assertNotIn("harnessError", out, r.stderr)
        self.assertEqual(r.returncode, 0, f"{r.stdout}\n{r.stderr}")
        if timeout_ms is None:
            self.assertEqual(out["sourceSha256"], hashlib.sha256(PLUGIN.read_bytes()).hexdigest())
        # for every run: the plugin printed nothing (stdout of `opencode acp` is the ACP channel) and left nothing unhandled
        self.assertEqual(out["writes"], [])
        self.assertEqual(out["unhandled"], [])
        return out

    def run_one(self, steps, **kw):
        flags = {k: kw.pop(k) for k in ("subscribeThrows", "streamThrows") if k in kw}
        options = kw.pop("options", DEFAULT)
        out = self.run_cases([self.case("one", steps, options, **flags)], **kw)
        return out["cases"][0]

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    @staticmethod
    def tool(name, input=None, **extra):
        step = {"op": "tool", "tool": name}
        if input is not None:
            step["input"] = input
        step.update(extra)
        return step

    def assert_goes_on(self, result, msg=""):
        self.assertEqual(result["outcomes"], [GO], msg)

    def assert_throws(self, result, msg=""):
        [o] = result["outcomes"]
        self.assertTrue(o.get("threw"), f"{msg}: {o}")
        self.assertEqual(o["message"], DENIED, msg)


# ------------------------------------------------------------------------------------------------ setup


class SetupTests(PluginCase):
    def test_the_default_export_is_an_id_and_a_setup_and_nothing_else(self):
        out = self.run_cases([self.case("c", [])])
        self.assertEqual(out["exportKeys"], ["default"])
        self.assertEqual(sorted(out["defaultKeys"]), ["id", "setup"])
        self.assertEqual(out["id"], "umwayi.gate")
        self.assertEqual(out["setupType"], "function")

    def test_setup_registers_one_tool_hook_one_evaluate_hook_and_one_session_created_subscription(self):
        c = self.run_one([{"op": "setup"}])
        self.assertEqual(c["steps"][0], {"ok": True, "cleanupType": "function"})  # a cleanup function is returned
        self.assertEqual(c["registered"]["tool"], 1)
        self.assertEqual(c["registered"]["permission"], 1)
        self.assertEqual(c["registered"]["subscriptions"], [{"types": ["session.created"], "signalGiven": True}])

    def test_setup_touches_only_options_tool_permission_and_event_of_ctx(self):
        c = self.run_one([{"op": "setup"}, self.tool("read", {"path": "/a"}), {"op": "evaluate", "effect": "allow"},
                          {"op": "event", "type": "session.created"}, {"op": "cleanup"}])
        self.assertEqual(c["touched"], ["event", "options", "permission", "tool"])

    def test_setup_writes_no_canary_and_runs_no_hook(self):
        c = self.run_one([{"op": "setup"}, {"op": "stat", "path": str(self.canary)}])
        self.assertEqual(c["steps"][1], {"exists": False})
        self.assertEqual(self.calls(), [])

    def test_good_options_of_every_shape_load(self):
        for hook in ([sys.executable], [sys.executable, "--root", "/r with spaces", "--platform", "opencode"],
                     ["/usr/bin/python3", "-u"]):
            with self.subTest(hook=hook):
                c = self.run_one([{"op": "setup"}], options=self.options(hook=hook))
                self.assertEqual(c["steps"][0]["ok"], True)

    def test_bad_options_stop_setup_register_nothing_and_never_write_the_canary(self):
        good_hook = self.hook()
        bad = {
            "options missing": ABSENT,
            "options null": None,
            "options a list": [good_hook, str(self.canary), TOKEN],
            "options a string": "hook",
            "options empty": {},
            "no hook": self.options(hook=ABSENT),
            "no canary": self.options(canary=ABSENT),
            "no token": self.options(token=ABSENT),
            "hook null": self.options(hook=None),
            "hook a string": self.options(hook=" ".join(good_hook)),
            "hook empty list": self.options(hook=[]),
            "hook with a number": self.options(hook=[sys.executable, 5]),
            "hook with null": self.options(hook=[sys.executable, None]),
            "hook with an empty word": self.options(hook=[sys.executable, ""]),
            "hook with a NUL": self.options(hook=[sys.executable, "a\u0000b"]),
            "hook program relative": self.options(hook=["python3", "-V"]),
            "hook program empty": self.options(hook=["", "x"]),
            "hook nested list": self.options(hook=[[sys.executable]]),
            "canary missing string": self.options(canary=None),
            "canary empty": self.options(canary=""),
            "canary relative": self.options(canary="canary"),
            "canary with a NUL": self.options(canary="/tmp/a\u0000b"),
            "canary a number": self.options(canary=5),
            "token empty": self.options(token=""),
            "token short": self.options(token="short"),
            "token fifteen characters": self.options(token="a" * 15),
            "token too long": self.options(token="a" * 129),
            "token with a space": self.options(token="0123456789abcdef 123456789abcdef"),
            "token with a slash": self.options(token="0123456789abcdef/123456789abcdef"),
            "token with a newline": self.options(token="0123456789abcdef0123456789abcde\n"),
            "token a number": self.options(token=5),
            "token null": self.options(token=None),
        }
        cases = [self.case(name, [{"op": "setup"}, self.tool("read", {"path": "/a"}),
                                  {"op": "event", "type": "session.created"}, {"op": "stat", "path": str(self.canary)}],
                           options=options) for name, options in bad.items()]
        out = self.run_cases(cases)
        for c in out["cases"]:
            with self.subTest(case=c["name"]):
                setup, tool, _event, stat = c["steps"]
                self.assertEqual(setup["threw"], True, setup)
                self.assertEqual(setup["message"], BAD_OPTIONS)
                self.assertEqual(c["registered"], {"tool": 0, "permission": 0, "subscriptions": []})
                self.assertEqual(tool["outcomes"], [])  # nothing is registered, so nothing can let a call through
                self.assertEqual(stat, {"exists": False})
        self.assertEqual(self.calls(), [])

    def test_the_error_for_bad_options_holds_none_of_the_values(self):
        out = self.run_cases([self.case("c", [{"op": "setup"}],
                                        options={"hook": [SECRET, "--root", "/r"], "canary": SECRET, "token": SECRET})])
        [setup] = out["cases"][0]["steps"]
        self.assertEqual(setup["message"], BAD_OPTIONS)
        self.assertNotIn(SECRET, json.dumps(out))

    def test_extra_option_keys_are_ignored_and_never_used(self):
        opts = self.options()
        opts.update({"timeout": 1, "shell": True, "env": {"A": "b"}, "hookx": ["/bin/true"]})
        c = self.run_one([{"op": "setup"}, self.tool("read", {"path": "/a"})], options=opts)
        self.assert_goes_on(c["steps"][1])
        [call] = self.calls()
        self.assertEqual(call["argv"][:2], ["--exit", "0"])  # the argument list is the hook option and nothing more


# ------------------------------------------------------------------------------------------------ the gate


class ToolGateTests(PluginCase):
    def go_or_throw(self, hook, tool, input=None):
        """One fresh setup with this hook, one tool call: 'go' or 'throw' (and that the throw has the fixed text)."""
        c = self.run_one([{"op": "setup"}, self.tool(tool, input or {"path": "/a"})], options=self.options(hook=hook))
        [o] = c["steps"][1]["outcomes"]
        if o.get("threw"):
            self.assertEqual(o["message"], DENIED)
            return "throw"
        self.assertEqual(o, GO)
        return "go"

    def table(self, rows):
        """rows: (label, hook, tool, expected). One node run for all of them."""
        cases = [self.case(f"{label}|{tool}", [{"op": "setup"}, self.tool(tool, {"path": "/a"})],
                           options=self.options(hook=hook)) for label, hook, tool, _ in rows]
        out = self.run_cases(cases)
        for (label, _, tool, expected), c in zip(rows, out["cases"]):
            [o] = c["steps"][1]["outcomes"]
            got = "throw" if o.get("threw") else "go"
            with self.subTest(label=label, tool=tool):
                self.assertEqual(got, expected, o)
                if got == "throw":
                    self.assertEqual(o["message"], DENIED)
                else:
                    self.assertEqual(o, GO)

    def test_exit_0_with_an_allow_line_lets_every_tool_go_on(self):
        self.table([("yes", self.hook(0), t, "go") for t in ASKED + NOT_ASKED])

    def test_exit_3_with_an_ask_line_lets_only_the_nine_asked_tools_go_on(self):
        rows = [("ask", self.hook(3), t, "go") for t in ASKED] + [("ask", self.hook(3), t, "throw") for t in NOT_ASKED]
        self.table(rows)

    def test_the_asked_tools_are_exactly_the_nine_seen_on_2_2_7(self):
        # 10.42: read, glob, grep, write, edit, shell, webfetch, question and subagent asked; execute did not
        self.assertEqual(sorted(ASKED), sorted(["read", "glob", "grep", "write", "edit", "shell", "webfetch",
                                                "question", "subagent"]))
        self.assertEqual(len(set(ASKED)), 9)
        self.assertNotIn("execute", ASKED)

    def test_exit_2_throws_for_every_tool(self):
        self.table([("no", self.hook(2), t, "throw") for t in ASKED + NOT_ASKED])

    def test_exit_2_throws_even_when_the_line_says_allow_or_ask(self):
        rows = []
        for say in ("allow", "ask", "deny", "auto"):
            for tool in ("read", "shell", "execute"):
                rows.append((f"exit 2 say {say}", self.hook(2, say), tool, "throw"))
        self.table(rows)

    def test_every_other_exit_code_throws(self):
        rows = []
        for code in (1, 4, 5, 64, 126, 127, 128, 130, 137, 143, 255):
            for say in ("auto", "allow", "ask"):
                rows.append((f"exit {code} say {say}", self.hook(code, say), "read", "throw"))
        self.table(rows)

    def test_a_line_that_disagrees_with_the_exit_code_throws(self):
        rows = [
            ("exit 0 says ask", self.hook(0, "ask"), "read", "throw"),
            ("exit 0 says deny", self.hook(0, "deny"), "read", "throw"),
            ("exit 3 says allow", self.hook(3, "allow"), "read", "throw"),
            ("exit 3 says deny", self.hook(3, "deny"), "shell", "throw"),
        ]
        self.table(rows)

    def test_output_that_is_not_the_one_json_line_throws(self):
        rows = []
        for say in ("garbage", "empty", "nodecision", "array", "null", "number", "huge"):
            for code in (0, 3):
                rows.append((f"exit {code} say {say}", self.hook(code, say), "read", "throw"))
        self.table(rows)

    def test_a_hook_killed_by_a_signal_throws(self):
        self.table([("killed", self.hook(0, "kill"), "read", "throw")])

    def test_a_hook_that_cannot_start_throws(self):
        missing = self.tmp / "no-such-program"
        directory = self.tmp
        not_executable = self.tmp / "plain.txt"
        not_executable.write_text("hello", encoding="utf-8")
        rows = [("missing program", [str(missing)], "read", "throw"),
                ("a folder", [str(directory)], "read", "throw"),
                ("not executable", [str(not_executable)], "read", "throw"),
                ("python without the script", [sys.executable, str(self.tmp / "no-such-script.py")], "read", "throw")]
        self.table(rows)

    def test_stderr_of_the_hook_changes_nothing(self):
        rows = [("allow with stderr", self.hook(0, stderr=SECRET), "read", "go"),
                ("deny with stderr", self.hook(2, stderr=SECRET), "read", "throw")]
        self.table(rows)

    def test_the_decision_is_made_for_each_call_and_nothing_is_remembered(self):
        # one setup, hook fixed by exit code; the order of calls does not matter
        c = self.run_one([{"op": "setup"}, self.tool("read", {"path": "/a"}), self.tool("execute", {"code": "1"}),
                          self.tool("read", {"path": "/b"}), self.tool("shell", {"command": "ls"})],
                         options=self.options(hook=self.hook(3)))
        results = c["steps"][1:]
        self.assert_goes_on(results[0])
        self.assert_throws(results[1])
        self.assert_goes_on(results[2])
        self.assert_goes_on(results[3])
        self.assertEqual(len(self.calls()), 4)  # one hook run per call

    def test_the_callback_is_synchronous_so_a_throw_stops_the_call(self):
        c = self.run_one([{"op": "setup"}, self.tool("read", {"path": "/a"}), self.tool("execute", {"code": "1"})],
                         options=self.options(hook=self.hook(3)))
        self.assertEqual(c["steps"][1]["outcomes"], [GO])  # returned undefined, not a promise
        [o] = c["steps"][2]["outcomes"]
        self.assertNotIn("async", o)  # the throw is synchronous, not a rejected promise
        self.assertTrue(o["threw"])


class WhatReachesTheHookTests(PluginCase):
    def one(self, tool, input=ABSENT, **kw):
        step = {"op": "tool", "tool": tool}
        if input is not ABSENT:
            step["input"] = input
        c = self.run_one([{"op": "setup"}, step], **kw)
        return c["steps"][1]

    def test_the_hook_gets_tool_name_and_tool_input_and_nothing_else(self):
        tool_input = {"path": "/a/b.txt", "content": "text", "offset": 3, "flags": ["x"], "nested": {"k": None}}
        self.one("write", tool_input)
        [call] = self.calls()
        self.assertEqual(json.loads(call["stdin"]), {"tool_name": "write", "tool_input": tool_input})
        self.assertEqual(sorted(json.loads(call["stdin"])), ["tool_input", "tool_name"])

    def test_a_missing_input_is_sent_as_an_empty_object(self):
        self.one("opencode_worktree_list")
        [call] = self.calls()
        self.assertEqual(json.loads(call["stdin"]), {"tool_name": "opencode_worktree_list", "tool_input": {}})

    def test_a_null_input_is_sent_as_an_empty_object(self):
        step = {"op": "tool", "tool": "read", "input": None}
        self.run_one([{"op": "setup"}, step])
        self.assertEqual(json.loads(self.calls()[0]["stdin"])["tool_input"], {})

    def test_the_arguments_are_passed_as_an_argument_list_without_a_shell(self):
        marker = self.tmp / "injected"
        words = ["--root", f"/r; touch {marker}", "--platform", "$(touch %s)" % marker, "a b", "`id`", "*"]
        hook = [sys.executable, str(FAKE_HOOK), "--log", str(self.log), *words, "--exit", "0"]
        self.one("read", {"path": "/a"}, options=self.options(hook=hook))
        [call] = self.calls()
        self.assertEqual(call["argv"][2:], words + ["--exit", "0"])  # each word arrived whole
        self.assertFalse(marker.exists())

    def test_the_tool_name_is_sent_as_given_never_changed(self):
        names = ["read", "opencode_worktree_list", "github_create_issue", "A_B-c", "x" * 150]
        self.run_one([{"op": "setup"}] + [self.tool(n, {}) for n in names], options=self.options(hook=self.hook(3)))
        self.assertEqual([json.loads(c["stdin"])["tool_name"] for c in self.calls()], names)

    def test_a_tool_name_that_is_not_a_string_throws_and_the_hook_is_not_run(self):
        steps = [{"op": "setup"},
                 {"op": "tool", "input": {}},  # no tool at all
                 {"op": "tool", "tool": None, "input": {}}, {"op": "tool", "tool": 5, "input": {}},
                 {"op": "tool", "tool": "", "input": {}}, {"op": "tool", "tool": ["read"], "input": {}},
                 {"op": "tool", "tool": {"name": "read"}, "input": {}}, {"op": "tool", "tool": True, "input": {}},
                 {"op": "tool", "event": None}, {"op": "tool", "tool": "read", "event": None}]
        c = self.run_one(steps, options=self.options(hook=self.hook(0)))
        for result in c["steps"][1:]:
            self.assert_throws(result)
        self.assertEqual(self.calls(), [])

    def test_an_input_that_is_not_an_object_throws_and_the_hook_is_not_run(self):
        steps = [{"op": "setup"}] + [{"op": "tool", "tool": "read", "input": v} for v in ("x", 5, True, ["a"], [])] \
            + [{"op": "tool", "tool": "read", "inputKind": "circular"}, {"op": "tool", "tool": "read", "inputKind": "bigint"}]
        c = self.run_one(steps, options=self.options(hook=self.hook(0)))
        for result in c["steps"][1:]:
            self.assert_throws(result)
        self.assertEqual(self.calls(), [])

    def test_a_thrown_error_has_the_fixed_text_and_nothing_from_the_call(self):
        marks = [SECRET + "-path", SECRET + "-command", SECRET + "-tool"]
        cases = []
        for exit_code, say in ((2, "secret"), (1, "auto"), (3, "secret"), (0, "garbage"), (0, "kill")):  # all throw
            cases.append(self.case(f"{exit_code}-{say}", [
                {"op": "setup"},
                {"op": "tool", "tool": marks[2], "input": {"path": marks[0], "command": marks[1]}},
                {"op": "tool", "tool": "execute", "input": {"path": marks[0], "command": marks[1]}}],
                options=self.options(hook=self.hook(exit_code, say, stderr=SECRET + "-stderr"))))
        out = self.run_cases(cases)
        for c in out["cases"]:
            for result in c["steps"][1:]:
                [o] = result["outcomes"]
                self.assertEqual(o["message"], DENIED, c["name"])
                self.assertFalse(o["hasCause"], c["name"])  # a cause could carry the hook's output
                self.assertEqual(o["name"], "Error")
        self.assertNotIn(SECRET, json.dumps(out))


class TimeoutTests(PluginCase):
    def test_a_hook_that_takes_too_long_throws_and_is_killed(self):
        hook = self.hook(0, sleep=30)
        started = time.monotonic()
        c = self.run_one([{"op": "setup"}, self.tool("read", {"path": "/a"})], options=self.options(hook=hook),
                         timeout_ms=400)
        self.assertLess(time.monotonic() - started, 15)
        self.assert_throws(c["steps"][1])
        [call] = self.calls()
        self.assertFalse(alive(call["pid"]), "the slow hook was left running")

    def test_a_hook_that_answers_inside_the_limit_is_fine(self):
        c = self.run_one([{"op": "setup"}, self.tool("read", {"path": "/a"})],
                         options=self.options(hook=self.hook(0, sleep=0.1)), timeout_ms=5000)
        self.assert_goes_on(c["steps"][1])

    def test_the_real_limit_is_ten_seconds(self):
        self.assertRegex(PLUGIN.read_text(encoding="utf-8"), r"(?m)^const TIMEOUT_MS = 10000$")
        started = time.monotonic()
        c = self.run_one([{"op": "setup"}, self.tool("shell", {"command": "ls"})],
                         options=self.options(hook=self.hook(3, sleep=60)))  # no override: the file as it is
        took = time.monotonic() - started
        self.assert_throws(c["steps"][1])
        self.assertGreaterEqual(took, 9.5)
        self.assertLess(took, 25)
        [call] = self.calls()
        self.assertFalse(alive(call["pid"]))


def alive(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except (FileNotFoundError, ProcessLookupError, IndexError):
        return False


# ------------------------------------------------------------------------------------------------ evaluate


class EvaluateTests(PluginCase):
    def effects(self, *efforts, **kw):
        steps = [{"op": "setup"}] + [{"op": "evaluate", "effect": e} for e in efforts]
        return self.run_one(steps, **kw)["steps"][1:]

    def test_allow_becomes_ask(self):
        [r] = self.effects("allow")
        self.assertEqual(r["effect"], "ask")
        self.assertEqual(r["outcomes"], [{"ok": True}])

    def test_ask_and_deny_stay(self):
        a, d = self.effects("ask", "deny")
        self.assertEqual((a["effect"], d["effect"]), ("ask", "deny"))

    def test_anything_else_becomes_ask(self):
        results = self.effects("Allow", "ALLOW", "auto", "", "yes", "permit", "allow ", None, 5, True)
        self.assertEqual([r["effect"] for r in results], ["ask"] * 10)

    def test_a_missing_effect_becomes_ask(self):
        c = self.run_one([{"op": "setup"}, {"op": "evaluate"}])
        self.assertEqual(c["steps"][1]["effect"], "ask")

    def test_the_message_is_left_alone(self):
        c = self.run_one([{"op": "setup"}, {"op": "evaluate", "effect": "allow", "message": "from the rules"}])
        self.assertEqual(c["steps"][1]["message"], "from the rules")

    def test_the_callback_never_throws_even_for_an_odd_event(self):
        c = self.run_one([{"op": "setup"}, {"op": "evaluate", "event": None}])
        self.assertEqual(c["steps"][1]["outcomes"], [{"ok": True}])

    def test_it_runs_no_hook(self):
        self.effects("allow", "ask", "deny")
        self.assertEqual(self.calls(), [])


# ------------------------------------------------------------------------------------------------ canary


class CanaryTests(PluginCase):
    def stat(self):
        return {"op": "stat", "path": str(self.canary)}

    def test_nothing_is_written_before_session_created(self):
        c = self.run_one([{"op": "setup"}, self.stat(), self.tool("read", {"path": "/a"}), self.stat(),
                          {"op": "evaluate", "effect": "allow"}, self.stat()])
        for i in (1, 3, 5):
            self.assertEqual(c["steps"][i], {"exists": False}, i)

    def test_session_created_writes_the_token_with_mode_0600_and_nothing_else(self):
        c = self.run_one([{"op": "setup"}, {"op": "event", "type": "session.created"}, self.stat()])
        self.assertEqual(c["steps"][1], {"delivered": 1})
        st = c["steps"][2]
        self.assertTrue(st["exists"] and st["isFile"] and not st["isSymlink"])
        self.assertEqual(st["content"], TOKEN)  # exactly the token: no newline, nothing added
        self.assertEqual(st["size"], len(TOKEN))
        self.assertEqual(st["mode"], 0o600)
        self.assertEqual(os.stat(self.canary).st_mode & 0o7777, 0o600)

    def test_the_mode_does_not_depend_on_the_umask(self):
        old = os.umask(0)
        try:
            self.run_one([{"op": "setup"}, {"op": "event", "type": "session.created"}])
        finally:
            os.umask(old)
        self.assertEqual(os.stat(self.canary).st_mode & 0o7777, 0o600)

    def test_session_created_twice_writes_once(self):
        c = self.run_one([{"op": "setup"}, {"op": "event", "type": "session.created"}, self.stat(),
                          {"op": "event", "type": "session.created"}, {"op": "event", "type": "session.created"},
                          self.stat()])
        self.assertEqual(c["steps"][2], c["steps"][5])
        self.assertEqual(c["steps"][5]["content"], TOKEN)

    def test_the_token_is_written_once_even_if_the_file_is_taken_away_and_another_event_comes(self):
        c = self.run_one([{"op": "setup"}, {"op": "event", "type": "session.created"}, self.stat(),
                          {"op": "unlink", "path": str(self.canary)}, {"op": "event", "type": "session.created"},
                          self.stat()])
        self.assertTrue(c["steps"][2]["exists"])
        self.assertEqual(c["steps"][5], {"exists": False})  # the plugin asked for one event and then stopped listening
        self.assertEqual(c["steps"][4], {"delivered": 1})

    def test_a_second_plugin_instance_does_not_overwrite_the_first(self):
        other = "f" * 32
        cases = [self.case("first", [{"op": "setup"}, {"op": "event", "type": "session.created"}]),
                 self.case("second", [{"op": "setup"}, {"op": "event", "type": "session.created"}, self.stat()],
                           options=self.options(token=other))]
        out = self.run_cases(cases)
        self.assertEqual(out["cases"][1]["steps"][2]["content"], TOKEN)  # the file of the first instance is kept
        self.assertEqual(self.canary.read_text(encoding="utf-8"), TOKEN)

    def test_an_existing_file_is_not_overwritten_or_made_stricter(self):
        self.canary.write_text("planted", encoding="utf-8")
        self.canary.chmod(0o644)
        c = self.run_one([{"op": "setup"}, {"op": "event", "type": "session.created"}, self.stat(),
                          self.tool("read", {"path": "/a"})])
        self.assertEqual(self.canary.read_text(encoding="utf-8"), "planted")
        self.assertEqual(os.stat(self.canary).st_mode & 0o7777, 0o644)
        self.assertEqual(c["steps"][2]["content"], "planted")
        self.assert_goes_on(c["steps"][3])  # the gate itself still works

    def test_a_symlink_at_the_canary_path_is_not_followed(self):
        target = self.tmp / "victim.txt"
        target.write_text("keep me", encoding="utf-8")
        self.canary.symlink_to(target)
        self.run_one([{"op": "setup"}, {"op": "event", "type": "session.created"}])
        self.assertEqual(target.read_text(encoding="utf-8"), "keep me")
        self.assertTrue(self.canary.is_symlink())

    def test_a_dangling_symlink_is_not_followed_either(self):
        target = self.tmp / "not-yet.txt"
        self.canary.symlink_to(target)
        self.run_one([{"op": "setup"}, {"op": "event", "type": "session.created"}])
        self.assertFalse(target.exists())

    def test_a_canary_folder_that_does_not_exist_writes_nothing_and_does_not_stop_the_gate(self):
        opts = self.options(canary=str(self.tmp / "no-such-folder" / "canary"))
        c = self.run_one([{"op": "setup"}, {"op": "event", "type": "session.created"}, self.tool("read", {"path": "/a"})],
                         options=opts)
        self.assertFalse((self.tmp / "no-such-folder").exists())
        self.assert_goes_on(c["steps"][2])

    def test_a_canary_path_below_a_file_writes_nothing_and_does_not_stop_the_gate(self):
        a_file = self.tmp / "a-file"
        a_file.write_text("x", encoding="utf-8")
        c = self.run_one([{"op": "setup"}, {"op": "event", "type": "session.created"}, self.tool("read", {"path": "/a"})],
                         options=self.options(canary=str(a_file / "canary")))
        self.assertEqual(a_file.read_text(encoding="utf-8"), "x")
        self.assert_goes_on(c["steps"][2])

    def test_another_event_type_never_reaches_the_plugin_and_writes_nothing(self):
        c = self.run_one([{"op": "setup"}, {"op": "event", "type": "session.idle"},
                          {"op": "event", "type": "permission.asked"}, self.stat()])
        self.assertEqual(c["steps"][1], {"delivered": 0})
        self.assertEqual(c["steps"][3], {"exists": False})

    def test_after_cleanup_no_event_writes_a_canary(self):
        c = self.run_one([{"op": "setup"}, {"op": "cleanup", "times": 2}, {"op": "event", "type": "session.created"},
                          self.stat()])
        self.assertEqual(c["steps"][1], {"ok": True, "aborted": [True]})  # the subscription's signal was aborted
        self.assertEqual(c["steps"][3], {"exists": False})

    def test_a_failing_event_stream_or_subscribe_is_survived_and_the_gate_still_works(self):
        for flag in ("streamThrows", "subscribeThrows"):
            with self.subTest(flag=flag):
                c = self.run_one([{"op": "setup"}, {"op": "event", "type": "session.created"}, self.stat(),
                                  self.tool("read", {"path": "/a"}), self.tool("execute", {"code": "1"})],
                                 options=self.options(hook=self.hook(3)), **{flag: True})
                self.assertEqual(c["steps"][0]["ok"], True)
                self.assertEqual(c["steps"][2], {"exists": False})  # no canary: umwayi refuses the chat
                self.assert_goes_on(c["steps"][3])
                self.assert_throws(c["steps"][4])

    def test_the_token_is_not_in_any_error_text(self):
        out = self.run_cases([self.case("c", [{"op": "setup"}, self.tool("execute", {"code": "1"})],
                                        options=self.options(hook=self.hook(2)))])
        self.assertNotIn(TOKEN, json.dumps(out["cases"][0]["steps"]))


# ------------------------------------------------------------------------------------------------ the real hook


class RealHookTests(AdapterCase):
    """The plugin with the real layer 9 generic adapter, `--platform opencode`, the starter rules of
    adapters/opencode/rules.example.yaml and a real umwayi root: one logbook entry per check."""

    HOOK, RULES = STDIO_HOOK, RULES_EXAMPLE

    @classmethod
    def setUpClass(cls):
        cls.node = need_node()

    def setUp(self):
        super().setUp()
        self.kill_off()
        self.canary = self.tmp / "canary"

    def argv(self):
        return [sys.executable, str(STDIO_HOOK), "--root", str(self.root), "--platform", "opencode"]

    def run_calls(self, calls, hook=None):
        options = {"hook": hook or self.argv(), "canary": str(self.canary), "token": TOKEN}
        steps = [{"op": "setup"}] + [{"op": "tool", "tool": t, "input": i} for t, i in calls]
        script = {"timeoutMs": None, "cases": [{"name": "real", "options": options, "steps": steps}]}
        r = subprocess.run([self.node, str(HARNESS), str(PLUGIN)], input=json.dumps(script), capture_output=True,
                           text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["writes"], [])
        self.assertEqual(out["unhandled"], [])
        results = []
        for step in out["cases"][0]["steps"][1:]:
            [o] = step["outcomes"]
            results.append("throw" if o.get("threw") else "go")
            if o.get("threw"):
                self.assertEqual(o["message"], DENIED)
        return results

    TABLE = [
        # Yes: reading and listing
        ("read", {"path": "/repo/a.py"}, "go"), ("glob", {"pattern": "*.py"}, "go"),
        ("grep", {"pattern": "todo", "path": "/repo"}, "go"),
        # No: secret and key paths, the files that guard the AI helper, destructive commands
        ("read", {"path": "/repo/.env"}, "throw"), ("read", {"path": "/home/me/.ssh/id_rsa"}, "throw"),
        ("grep", {"pattern": "x", "path": "/home/me/.aws/credentials"}, "throw"),
        ("write", {"path": "/repo/rules.yaml", "content": "x"}, "throw"), ("edit", {"path": "LOGBOOK.md"}, "throw"),
        ("edit", {"path": "opencode.json"}, "throw"), ("write", {"path": "/repo/.opencode/plugins/x.js"}, "throw"),
        ("edit", {"path": "/repo/.git/config"}, "throw"), ("shell", {"command": "rm -rf build"}, "throw"),
        ("shell", {"command": "git push --force origin x"}, "throw"), ("shell", {"command": "cat opencode.json"}, "throw"),
        ("shell", {"command": "umwayi kill off"}, "throw"),
        # Ask me first, and OpenCode asks permission for the tool: the call goes on to the permission request
        ("write", {"path": "/repo/a.py", "content": "x"}, "go"), ("edit", {"path": "/repo/a.py"}, "go"),
        ("shell", {"command": "npm test"}, "go"), ("webfetch", {"url": "https://example.com"}, "go"),
        ("subagent", {"agent": "general", "description": "d", "prompt": "p"}, "go"), ("question", {"questions": []}, "go"),
        # Ask me first, and OpenCode asks nothing for the tool: it throws (Code Mode, and tools never seen asking)
        ("execute", {"code": "1+1"}, "throw"), ("opencode_worktree_list", {}, "throw"),
        ("opencode_worktree_remove", {"directory": "/x"}, "throw"), ("opencode_session_move", {"directory": "/x"}, "throw"),
        ("patch", {"path": "/repo/a.py"}, "throw"), ("websearch", {"query": "x"}, "throw"),
        ("skill", {"id": "x"}, "throw"), ("github_create_issue", {"title": "x"}, "throw"),
    ]

    def test_each_tool_call_gets_the_answer_the_starter_rules_give(self):
        results = self.run_calls([(t, i) for t, i, _ in self.TABLE])
        for (tool, _, expected), got in zip(self.TABLE, results):
            with self.subTest(tool=tool):
                self.assertEqual(got, expected)

    def test_every_check_writes_one_logbook_entry_and_the_logbook_verifies(self):
        before = len(self.entries())
        self.run_calls([(t, i) for t, i, _ in self.TABLE])
        self.assertEqual(len(self.entries()) - before, len(self.TABLE))
        out = self.umwayi("logbook", "verify")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotIn(SECRET, (self.root / "LOGBOOK.md").read_text(encoding="utf-8"))

    def test_the_logbook_names_the_starter_rule_that_decided(self):
        self.run_calls([("read", {"path": "/repo/a.py"}), ("read", {"path": "/repo/.env"}), ("execute", {"code": "1"})])
        added = self.added_lines()
        self.assertIn("Rule oc-read gave Yes; action type: tool_read", added[0])
        self.assertIn("Rule oc-no-secrets gave No; action type: tool_read", added[1])
        self.assertIn("No rule gave Ask me first; action type: tool_execute", added[2])  # Code Mode has no rule

    def test_code_mode_goes_on_when_the_owner_writes_a_yes(self):
        with open(self.root / "rules.yaml", "a", encoding="utf-8") as f:
            f.write("\n  - id: owner-yes-code-mode\n    title: Code Mode is fine\n    text: The owner allows Code Mode.\n"
                    "    cause: The owner chose it.\n    verdict: yes\n    matchers:\n      platform: opencode\n"
                    "      type: [tool_execute, tool_opencode_worktree_list]\n")
        results = self.run_calls([("execute", {"code": "1+1"}), ("opencode_worktree_list", {}),
                                  ("opencode_worktree_remove", {"directory": "/x"})])
        self.assertEqual(results, ["go", "go", "throw"])

    def test_the_kill_switch_stops_every_call_even_a_yes(self):
        self.kill_on()
        results = self.run_calls([("read", {"path": "/repo/a.py"}), ("shell", {"command": "ls"}), ("glob", {"pattern": "*"})])
        self.assertEqual(results, ["throw"] * 3)
        self.kill_off()
        self.assertEqual(self.run_calls([("read", {"path": "/repo/a.py"})]), ["go"])

    def test_an_unreadable_kill_switch_stops_every_call(self):
        self.kill_unknown()
        self.assertEqual(self.run_calls([("read", {"path": "/repo/a.py"}), ("shell", {"command": "ls"})]), ["throw"] * 2)

    def test_a_missing_or_broken_rules_file_stops_every_call(self):
        (self.root / "rules.yaml").unlink()
        self.assertEqual(self.run_calls([("read", {"path": "/repo/a.py"}), ("shell", {"command": "ls"})]), ["throw"] * 2)
        (self.root / "rules.yaml").write_text("rules:\n  - id: broken\n    verdict: maybe\n", encoding="utf-8")
        self.assertEqual(self.run_calls([("read", {"path": "/repo/a.py"}), ("shell", {"command": "ls"})]), ["throw"] * 2)

    def test_a_hook_command_with_a_wrong_root_stops_every_call(self):
        hook = [sys.executable, str(STDIO_HOOK), "--root", str(self.tmp / "no-such-root"), "--platform", "opencode"]
        self.assertEqual(self.run_calls([("read", {"path": "/repo/a.py"})], hook=hook), ["throw"])


# ------------------------------------------------------------------------------------------------ the source


class SourceTests(unittest.TestCase):
    """The plugin is umwayi's only JavaScript in a gate: it stays small, and it can reach nothing but a hook program
    and the canary file (design.md part 8, 10.R13.7, steering rule 9)."""

    @classmethod
    def setUpClass(cls):
        cls.src = PLUGIN.read_text(encoding="utf-8")

    def test_it_is_one_file_in_a_folder_of_its_own_with_no_package_file(self):
        self.assertEqual(sorted(os.listdir(PLUGIN.parent)), ["index.js"])
        self.assertTrue(PLUGIN.is_file() and not PLUGIN.is_symlink())

    def test_adapters_opencode_holds_one_javascript_file_and_no_npm_files(self):
        folder = REPO / "adapters" / "opencode"
        files = sorted(str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file())
        self.assertIn("plugin/index.js", files)
        js = [f for f in files if f.endswith((".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"))]
        self.assertEqual(js, ["plugin/index.js"])
        for name in ("package.json", "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "bun.lock", "bun.lockb",
                     "pnpm-lock.yaml", ".npmrc", "tsconfig.json"):
            self.assertFalse(any(f.endswith(name) for f in files), name)
        self.assertFalse(any("node_modules" in f for f in files))

    def test_it_is_under_the_size_the_spec_states(self):
        # design.md part 8, files table: "the plugin: two hooks and the canary, new, about 120 lines"
        lines = self.src.count("\n")
        self.assertLessEqual(lines, 120, f"{lines} lines")
        self.assertLessEqual(len(self.src.encode("utf-8")), 8000)

    def test_only_node_built_ins_are_imported_and_nothing_else_is_loaded(self):
        imports = re.findall(r"^import\s[^\n]*?\sfrom\s+\"([^\"]+)\"", self.src, re.M)
        self.assertEqual(sorted(imports), ["node:child_process", "node:fs", "node:path"])
        self.assertEqual(len(re.findall(r"^\s*import\b", self.src, re.M)), 3)  # no side-effect import, no other form
        for bad in ("import(", "require(", "require.", "module.exports", "createRequire", "process.binding", "Bun", "Deno"):
            self.assertNotIn(bad, self.src, bad)

    def test_it_has_no_eval_no_network_no_other_process_api_and_no_output(self):
        for bad in ("eval(", "Function(", "new Function", "fetch(", "http", "dgram", "WebSocket", "XMLHttpRequest",
                    "node:net", "node:tls", "node:dns", "node:vm", "node:worker_threads", "node:cluster", "node:os",
                    "node:crypto", "node:http", "node:https", "node:http2", "node:readline", "node:repl",
                    "exec(", "execSync", "execFile", "spawn(", "fork(", "shell: true", "console.", "process.stdout",
                    "process.stderr", "process.env", "process.exit", "process.on", "setInterval", "setTimeout",
                    "readFileSync", "writeFileSync", "appendFileSync", "unlinkSync", "rmSync", "chmodSync", "readdirSync",
                    "mkdirSync", "renameSync", "symlinkSync", "debugger", "import.meta"):
            self.assertNotIn(bad, self.src, bad)
        self.assertIsNone(re.search(r"\bnet\b", self.src))
        # "webfetch" is OpenCode's name of a tool in the asked list; the word fetch may appear nowhere else
        self.assertEqual(re.findall(r"\w*fetch\w*", self.src), ["webfetch"])
        self.assertIsNone(re.search(r"writeSync\(\s*[12]\s*,", self.src))  # never to stdout or stderr by number

    def test_it_runs_exactly_one_program_in_exec_form_with_a_limit_and_a_kill(self):
        self.assertEqual(self.src.count("spawnSync("), 1)
        self.assertEqual(self.src.count("shell: false"), 1)
        self.assertRegex(self.src, r"(?m)^const TIMEOUT_MS = 10000$")
        self.assertIn('killSignal: "SIGKILL"', self.src)
        self.assertIn("maxBuffer", self.src)
        self.assertEqual(len(re.findall(r"timeout:\s*TIMEOUT_MS", self.src)), 1)

    def test_it_opens_exactly_one_file_for_writing_with_o_excl_and_mode_0600(self):
        self.assertEqual(self.src.count("openSync("), 1)
        self.assertEqual(self.src.count("writeSync("), 1)
        self.assertIn("constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL, 0o600", self.src)
        self.assertNotIn("O_TRUNC", self.src)
        self.assertNotIn("O_APPEND", self.src)

    def test_it_has_one_default_export_with_the_id_and_a_setup(self):
        self.assertEqual(len(re.findall(r"^export\b", self.src, re.M)), 1)
        self.assertIn("export default {", self.src)
        self.assertIn('id: "umwayi.gate"', self.src)
        self.assertEqual(len(re.findall(r"^\s*async setup\(ctx\)", self.src, re.M)), 1)

    def test_the_asked_list_in_the_source_is_the_nine_tools(self):
        m = re.search(r"const ASKED = new Set\(\[([^\]]*)\]\)", self.src)
        self.assertIsNotNone(m)
        self.assertEqual(sorted(re.findall(r'"([^"]+)"', m.group(1))), sorted(ASKED))

    def test_it_registers_exactly_these_hooks_and_this_event(self):
        self.assertEqual(re.findall(r"ctx\.(\w+)\.(\w+)\(", self.src),
                         [("tool", "hook"), ("permission", "hook"), ("event", "subscribe")])
        self.assertEqual(re.findall(r"\.hook\(\"([^\"]+)\"", self.src), ["execute.before", "evaluate"])
        self.assertEqual(re.findall(r"types:\s*\[([^\]]*)\]", self.src), ['"session.created"'])
        self.assertEqual(sorted(set(re.findall(r"\bctx\.(\w+)", self.src))), ["event", "options", "permission", "tool"])

    def test_the_two_error_texts_are_fixed_and_hold_no_variable(self):
        self.assertIn(f'const DENIED = "{DENIED}"', self.src)
        self.assertIn(f'const BAD_OPTIONS = "{BAD_OPTIONS}"', self.src)
        for m in re.finditer(r"new Error\(([^)]*)\)", self.src):
            self.assertIn(m.group(1), ("DENIED", "BAD_OPTIONS"))
        self.assertNotIn("${", self.src)  # no template string, so nothing is put into any text
        self.assertNotIn("cause", self.src)

    def test_no_em_dash(self):
        self.assertNotIn("\u2014", self.src)
        self.assertNotIn("\u2013", self.src)

    def test_the_harness_and_the_fake_hook_are_not_in_any_gate_folder(self):
        self.assertEqual(HARNESS.parent, REPO / "tests" / "adapters")
        self.assertFalse(list((REPO / "adapters").rglob("*.mjs")))


class NodeAvailableTests(unittest.TestCase):
    def test_node_is_on_path_and_is_recent_enough(self):
        node = need_node()
        r = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=30)
        m = re.match(r"v(\d+)\.", r.stdout)
        self.assertIsNotNone(m, r.stdout)
        self.assertGreaterEqual(int(m.group(1)), 18, f"node {r.stdout.strip()} is older than 18")


if __name__ == "__main__":
    unittest.main()
