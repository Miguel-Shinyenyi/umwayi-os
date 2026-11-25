"""M2 part 2, steps 1 and 2 (docs/muse-start-design.md): a Muse agent has a row, checks and a start through the one `_start`.

Every test runs `python -m umwayi ... agent check|run ...` as a real child process, with a fake `muse` first on PATH. The fake answers `--version`, logs
its argument list and the NAMES of its environment to the file in FAKE_MUSE_LOG, prints one JSON line, and exits with the code named by `exit=N` in the
prompt. No real Muse is run and no model is called. A chat is refused with a fixed text."""
import re
import sys
import unittest

from umwayi import agents, muse

from tests.agents.support import REPO, AgentCase

AGENT = "agents:\n  - name: m\n    platform: muse\n    command: muse\n    workdir: {work}\n    max_turns: 7\n  - name: nocap\n    platform: muse\n    command: muse\n    workdir: {work}\n"
RULE = "rules:\n  - id: muse-start\n    title: the Muse agents may start\n    text: Allowed.\n    verdict: yes\n    matchers:\n      type: agent_run\n      agent: [m, nocap]\n"
FAKE = """#!{py}
import json, os, sys
a = sys.argv[1:]
if a == ['--version']:
    print('muse 0.3.1')
    sys.exit(0)
log = os.environ.get('FAKE_MUSE_LOG')
if log:
    with open(log, 'a') as f:
        f.write(json.dumps({{'argv': a, 'env': sorted(os.environ)}}) + '\\n')
print(json.dumps({{'type': 'message', 'text': 'ok'}}))
code = 0
for word in a[-1].split():
    if word.startswith('exit='):
        code = int(word[5:])
sys.exit(code)
"""


class MuseCase(AgentCase):
    def setUp(self):
        super().setUp()
        self.fake_muse()
        self.write_agents(AGENT)

    def fake_muse(self, version_exit=0):
        p = self.bin / "muse"
        text = FAKE.format(py=sys.executable)
        if version_exit:
            text = text.replace("sys.exit(0)", f"sys.exit({version_exit})", 1)
        p.write_text(text, encoding="utf-8")
        p.chmod(0o755)

    def lines_of(self, r):
        return {m.group(2): (m.group(1), m.group(3)) for m in
                (re.match(r"^(ok|no|not run): ([a-z ]+): (.*)$", ln) for ln in r.stdout.splitlines()) if m}

    def muse_units(self, public=True, accepted=True, provider=True):
        """units.yaml with the roomy limits and, as asked, the owner's public mark, the provider `muse` and its acceptance (all written by the TEST, as the owner would)."""
        text = "version: 1\nlimits:\n  per_day: 1000000\n  per_agent_per_day: 1000000\n  per_platform_per_day: 1000000\n"
        if public:
            text += "public: true\n"
        if provider:
            text += "providers:\n  muse:\n    cost_kind: free_credits\n    limit:\n      credits_uu: 10000\n"
            if accepted:
                text += "    acceptance:\n      accepted_free: true\n      date: 2026-11-23\n      amount_uu: 10000\n      source: owner\n"
        (self.root / "units.yaml").write_text(text, encoding="utf-8")

    def muse_credits(self, left=9000, days_old=0):
        import datetime
        when = (datetime.date.today() - datetime.timedelta(days=days_old)).isoformat()
        (self.root / "credits.yaml").write_text(f"version: 1\ncredits:\n  muse:\n    left_uu: {left}\n    read: {when}\n", encoding="utf-8")

    def write_hook_file(self, command):
        (self.work / ".muse").mkdir(parents=True, exist_ok=True)
        (self.work / ".muse" / "hooks.json").write_text(muse.muse_hooks_text(command), encoding="utf-8")


class TableTests(unittest.TestCase):
    def test_the_row_is_fixed_and_pins_no_version(self):
        p = agents.PLATFORMS["muse"]
        self.assertEqual((p.commands, p.transports, p.min_version), (("muse",), ("cli",), (0, 0, 0)))
        self.assertTrue((REPO / p.hook).is_file())

    def test_a_run_builds_the_exec_line_with_the_prompt_last(self):
        agent = type("A", (), {"platform": "muse", "max_turns": 7})()
        argv, stdin = agents.build_argv(agent, agents.RUN, "/usr/bin/muse", REPO, sys.executable, prompt="hello there")
        self.assertEqual(argv, ["/usr/bin/muse", "exec", "--max-model-steps", "7", "--contributor-mode", "off", "--json", "hello there"])
        self.assertIsNone(stdin)

    def test_a_chat_a_login_and_a_missing_step_cap_build_nothing(self):
        for mode, steps in ((agents.CHAT, 7), (agents.LOGIN, 7), (agents.RUN, None)):
            agent = type("A", (), {"platform": "muse", "max_turns": steps})()
            with self.assertRaises(Exception) as cm:
                agents.build_argv(agent, mode, "/usr/bin/muse", REPO, sys.executable, prompt="hello")
            self.assertIn("Nothing was started", str(cm.exception), mode)

    def test_a_prompt_that_looks_like_a_flag_is_refused(self):
        agent = type("A", (), {"platform": "muse", "max_turns": 7})()
        for bad in ("--yolo", "-p x", "", "  "):
            with self.assertRaises(Exception):
                agents.build_argv(agent, agents.RUN, "/usr/bin/muse", REPO, sys.executable, prompt=bad)


class CheckTests(MuseCase):
    def test_the_agents_file_accepts_platform_muse(self):
        r = self.umwayi("validate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_missing_command_ends_the_checks_at_the_first_line(self):
        (self.bin / "muse").unlink()
        r = self.umwayi("check", "m")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        lines = self.lines_of(r)
        self.assertEqual(lines["command"][0], "no")
        self.assertEqual(lines["version"], ("not run", "an earlier check failed"))
        self.assertIn("Nothing was started.", r.stdout)

    def test_a_version_command_that_fails_ends_the_checks(self):
        self.fake_muse(version_exit=3)
        r = self.umwayi("check", "m")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(self.lines_of(r)["version"][0], "no")

    def test_without_a_hook_file_the_check_names_the_file_and_the_command_it_must_call(self):
        r = self.umwayi("check", "m")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        lines = self.lines_of(r)
        self.assertEqual((lines["command"][0], lines["version"][0], lines["hook file"][0]), ("ok", "ok", "no"))
        self.assertIn("hook_file_missing", lines["hook file"][1])
        self.assertIn("the sign-in is not checked", lines["version"][1])
        self.assertEqual(lines["key variables"], ("not run", "an earlier check failed"))

    def test_with_the_hook_file_the_agent_is_gated_and_nothing_is_started(self):
        r = self.umwayi("check", "m")
        command = re.search(r"PreToolUse command `([^`]+)`", r.stdout).group(1)
        self.write_hook_file(command)
        r = self.umwayi("check", "m", extra={"META_API_KEY": "SECRET-VALUE-1", "MUSE_TOKEN": "SECRET-VALUE-2"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        lines = self.lines_of(r)
        self.assertEqual([lines[k][0] for k in ("command", "version", "hook file", "key variables")], ["ok"] * 4)
        self.assertIn("META_API_KEY", lines["key variables"][1])
        self.assertIn("MUSE_TOKEN", lines["key variables"][1])
        self.assertNotIn("SECRET-VALUE", r.stdout + r.stderr)  # names only, never a value
        self.assertIn("run would start:", r.stdout)
        self.assertIn("a Muse chat is not built", r.stdout)

    def test_a_hook_file_that_calls_something_else_is_refused(self):
        self.write_hook_file("echo not-the-gate")
        r = self.umwayi("check", "m")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(self.lines_of(r)["hook file"][0], "no")


class RunBase(MuseCase):
    def setUp(self):
        super().setUp()
        self.write_rules(RULE)
        self.muse_units()
        self.muse_credits()
        self.log = self.tmp / "muse-calls.jsonl"
        r = self.umwayi("check", "m")
        self.write_hook_file(re.search(r"PreToolUse command `([^`]+)`", r.stdout).group(1))

    def run_muse(self, prompt, name="m", extra=None):
        return self.umwayi("run", name, "--prompt", prompt, extra=dict({"FAKE_MUSE_LOG": str(self.log)}, **(extra or {})))

    def calls(self):
        import json
        return [json.loads(l) for l in self.log.read_text(encoding="utf-8").splitlines()] if self.log.exists() else []


class RunTests(RunBase):
    def test_a_run_starts_muse_exec_with_the_step_cap_and_the_contributor_flag_off(self):
        r = self.run_muse("exit=0 summarise")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("finished (exit 0)", r.stdout)
        (call,) = self.calls()
        self.assertEqual(call["argv"][:6], ["exec", "--max-model-steps", "7", "--contributor-mode", "off", "--json"])
        self.assertEqual(call["argv"][-1], "exit=0 summarise")
        for bad in ("--yolo", "--disable-sandbox", "--disable-approval"):
            self.assertNotIn(bad, call["argv"])

    def test_each_exit_code_of_muse_is_reported_and_none_is_called_a_success_but_0(self):
        for code in (1, 2, 130):
            r = self.run_muse(f"exit={code} work")
            self.assertEqual(r.returncode, 2, (code, r.stdout, r.stderr))
            self.assertIn(f"exited with code {code}", r.stdout, code)

    def test_the_key_variables_never_reach_muse_and_no_value_reaches_a_line(self):
        r = self.run_muse("exit=0 x", extra={"META_API_KEY": "SECRET-VALUE-1", "MUSE_TOKEN": "SECRET-VALUE-2", "MUSE_HOME": "/m"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        (call,) = self.calls()
        self.assertNotIn("META_API_KEY", call["env"])
        self.assertNotIn("MUSE_TOKEN", call["env"])
        self.assertIn("MUSE_HOME", call["env"])  # only a name that holds a key, a token or a secret is removed
        self.assertNotIn("SECRET-VALUE", r.stdout + r.stderr + "".join(e.added + e.checked + e.not_done for e in self.entries()))

    def test_an_agent_without_a_step_cap_is_not_started(self):
        r = self.run_muse("exit=0 x", name="nocap")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("step_cap_missing", r.stdout + r.stderr)
        self.assertEqual(self.calls(), [])  # the fake was never started

    def test_a_chat_is_refused_and_the_fake_is_never_started(self):
        r = self.umwayi("chat", "m", extra={"FAKE_MUSE_LOG": str(self.log)})
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.calls(), [])


class GateRunTests(RunBase):
    """M2 part 2, step 3: the public mark, the acceptance and the stop line, before anything is reserved or started. Each refusal names its fixed word and the fake is never run."""

    def refused(self, code, word):
        r = self.run_muse("exit=0 work")
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        self.assertIn(word, r.stdout + r.stderr)
        self.assertEqual(self.calls(), [])
        self.assertIn(f"Refused agent m: {word}", "".join(e.added for e in self.entries()))

    def test_without_the_public_mark_the_run_is_refused_with_private_repo_named(self):
        self.muse_units(public=False)
        self.refused(2, "private_repo_named")

    def test_without_the_provider_or_the_acceptance_the_run_asks(self):
        self.muse_units(provider=False)
        self.refused(3, "provider_unknown")
        self.muse_units(accepted=False)
        self.refused(3, "no_acceptance")

    def test_without_a_reading_or_with_a_stale_one_the_run_asks(self):
        (self.root / "credits.yaml").unlink()
        self.refused(3, "use_unknown")
        self.muse_credits(days_old=5)
        self.refused(3, "use_unknown")

    def test_at_the_stop_line_the_run_is_refused_and_one_above_it_goes(self):
        self.muse_credits(left=500)  # 5 percent of the 10000 UU of the acceptance
        self.refused(2, "credits_low")
        self.muse_credits(left=501)
        r = self.run_muse("exit=0 work")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_mark_comes_first_when_everything_is_missing(self):
        self.muse_units(public=False, provider=False)
        self.refused(2, "private_repo_named")


if __name__ == "__main__":
    unittest.main()
