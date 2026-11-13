"""W9.6: `agent run --cap-uu N --model M --effort E` (W9.R15.3, W9.R15.6, design.md "Budget in detail").

The goldens of runs without the options are in test_run_golden.py and must not change. Here: the new argument lists
for both platforms, the cap that lowers the reservation and the per-run watch, the day limits checked against the
cap, the refusal of a platform whose cost cannot be watched, and every value that is a usage error (64) before
anything is read or started.
"""

import json
import unittest
from pathlib import Path

from tests.agents.support import REPO
from tests.budget.support import UNITS_HEAD, BudgetCase, api_request, rate, send_logs
from umwayi import agents
from umwayi.agents import Agent
from umwayi.errors import UsageError

END = {"do": "exit", "code": 0}
WAIT = {"do": "sleep", "s": 60}
KIRO_RUNS = UNITS_HEAD + "platforms:\n  kiro:\n    reading: runs\n    run_micros:" + rate(200000) + "\n"  # 20 UU


class OptionCase(BudgetCase):
    def opts(self, name, *options, steps=(END,), prompt="Do the task", extra=None):
        return self.umwayi("run", name, "--prompt", prompt, *options, extra=dict(self.script(*steps), **(extra or {})))

    def nothing_happened(self, r):
        self.assertEqual(r.returncode, 64, r.stdout + r.stderr)
        self.assertEqual(self.started(), [])
        self.assertFalse((self.root / "LOGBOOK.md").exists(), "a usage error wrote the logbook")

    def start_entry(self):
        return [e for e in self.entries() if e.source == "umwayi agent run" and e.added.startswith("Started")][0]


class ArgumentListTests(OptionCase):
    def test_claude_code_gets_model_and_effort_before_the_prompt(self):
        r = self.opts("reviewer", "--model", "claude-sonnet-5", "--effort", "high")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        [call] = self.started()
        argv = call["argv"]
        self.assertEqual(argv[-5:], ["--model", "claude-sonnet-5", "--effort", "high", "Do the task"])
        self.assertEqual(argv[:4], ["-p", "--permission-mode", "default", "--settings"])

    def test_claude_code_with_max_turns_puts_the_options_after_it(self):
        a = Agent(name="a", platform="claude-code", command="claude", transport="cli", workdir="/w", max_turns=20)
        argv, stdin = agents.build_argv(a, agents.RUN, "/bin/p", Path("/r"), "/usr/bin/python3", prompt="Hi",
                                        src=REPO, model="m1", effort="max")
        self.assertEqual(argv[-7:], ["--max-turns", "20", "--model", "m1", "--effort", "max", "Hi"])
        self.assertIsNone(stdin)

    def test_kiro_gets_model_and_effort_after_chat_v3_no_interactive(self):
        r = self.opts("helper", "--model", "kiro-model_1.5:x/y", "--effort", "xhigh")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        [call] = self.started()
        self.assertEqual(call["argv"], ["chat", "--v3", "--no-interactive", "--model", "kiro-model_1.5:x/y",
                                        "--effort", "xhigh", "--trust-tools=read_file"])
        self.assertEqual(call["stdin"], "Do the task")

    def test_each_option_alone(self):
        for opt, value in (("--model", "m"), ("--effort", "low")):
            with self.subTest(opt=opt):
                self.fake_log.unlink(missing_ok=True)
                r = self.opts("helper", opt, value)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual(self.started()[-1]["argv"][3:5], [opt, value])

    def test_all_five_effort_levels(self):
        self.limits(per_day=100000, per_agent_per_day=100000, per_platform_per_day=100000)
        for level in agents.EFFORTS:
            with self.subTest(level=level):
                r = self.opts("helper", "--effort", level)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual(self.started()[-1]["argv"][3:5], ["--effort", level])

    def test_the_start_entry_names_the_options_and_the_prompt_stays_out(self):
        r = self.opts("reviewer", "--model", "m1", "--effort", "low", "--cap-uu", "30", prompt="SECRET-TASK-TEXT")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("; options: cap 30 UU, model m1, effort low", self.start_entry().checked)
        self.assertNotIn("SECRET-TASK-TEXT", self.log_text())

    def test_without_options_the_start_entry_has_no_options_text(self):
        self.assertEqual(self.run_agent("reviewer", END).returncode, 0)
        self.assertNotIn("options", self.start_entry().checked)

    def test_the_options_are_not_in_the_help_of_other_commands(self):
        for sub in ("chat", "check", "login"):
            r = self.umwayi(sub, "reviewer", "--cap-uu", "5")
            self.assertEqual(r.returncode, 64, r.stdout + r.stderr)


class UsageErrorTests(OptionCase):
    def test_bad_models_are_64_and_start_nothing(self):
        for bad in ("a b", "-x", "--dangerously-skip-permissions", "", "a;b", "a\nb", "é", "x" * 65, "bypassPermissions"):
            with self.subTest(model=bad):
                self.nothing_happened(self.opts("reviewer", "--model", bad))

    def test_a_model_of_64_characters_is_allowed(self):
        self.assertEqual(self.opts("reviewer", "--model", "m" * 64).returncode, 0)

    def test_bad_models_through_the_functions(self):
        a = Agent(name="a", platform="kiro", command="kiro-cli", transport="cli", workdir="/w")
        for bad in ("a b", "-x", "a\x00b", "a\n", "x" * 65, 5):
            with self.subTest(model=bad):
                with self.assertRaises(UsageError):
                    agents.build_argv(a, agents.RUN, "/bin/p", Path("/r"), "python3", prompt="Hi", model=bad)
                with self.assertRaises(UsageError):
                    agents.check_options(a, None, bad, None)

    def test_the_allow_list_refuses_a_value_that_is_not_allowed(self):
        for argv in (["p", "--model", "a b"], ["p", "--model", "-x"], ["p", "--model", "a\x00b"], ["p", "--model"],
                     ["p", "--effort", "extreme"], ["p", "--effort"], ["p", "--effort", "--model"],
                     ["p", "--model", "--effort", "low"]):
            with self.subTest(argv=argv):
                with self.assertRaises(RuntimeError):
                    agents._assert_allowed(argv)
        self.assertEqual(agents._assert_allowed(["p", "--model", "m", "--effort", "max"]),
                         ["p", "--model", "m", "--effort", "max"])
        # the prompt is the owner's text: a prompt that reads like the flag is not a flag
        self.assertEqual(agents._assert_allowed(["p", "--model"], skip=1), ["p", "--model"])

    def test_bad_efforts_are_64(self):
        for bad in ("extreme", "HIGH", "", "high ", "1"):
            with self.subTest(effort=bad):
                self.nothing_happened(self.opts("reviewer", "--effort", bad))

    def test_bad_caps_are_64(self):
        for bad in ("0", "-1", "abc", "1.5", "+5", " 5", "5 ", "05", "", "1e2", "1" * 10, "٣"):
            with self.subTest(cap=bad):
                self.nothing_happened(self.opts("reviewer", "--cap-uu", bad))

    def test_a_cap_above_per_run_is_64_and_the_cap_equal_to_per_run_is_allowed(self):
        self.nothing_happened(self.opts("reviewer", "--cap-uu", "101"))  # the placeholder per_run is 100
        self.limits(per_run=20)
        self.nothing_happened(self.opts("reviewer", "--cap-uu", "21"))
        r = self.opts("reviewer", "--cap-uu", "20")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.reserves()[0].added.split(": ")[1], "200000 micros (20 UU)")

    def test_an_opencode_agent_with_effort_is_64(self):
        self.write_agents("agents:\n  - name: oc\n    platform: opencode\n    command: opencode\n    transport: acp\n"
                          "    workdir: {work}\n    provider: anthropic\n    model: anthropic/claude-x\n")
        for opts in (["--effort", "high"], ["--model", "m"], ["--cap-uu", "5"]):
            with self.subTest(opts=opts):
                r = self.umwayi("run", "oc", "--prompt", "Hi", *opts)
                self.assertEqual(r.returncode, 64, r.stdout + r.stderr)
        with self.assertRaises(UsageError):
            agents.check_options(Agent(name="oc", platform="opencode", command="opencode", transport="acp",
                                       workdir="/w"), None, None, "high")

    def test_the_model_and_effort_are_refused_for_chat_and_login_lists(self):
        a = Agent(name="a", platform="kiro", command="kiro-cli", transport="cli", workdir="/w")
        for mode in (agents.CHAT, agents.LOGIN):
            with self.assertRaises(UsageError):
                agents.build_argv(a, mode, "/bin/p", Path("/r"), "python3", model="m")

    def test_a_cap_with_an_invalid_units_yaml_is_refused_by_the_run_with_one_entry(self):
        self.units("version: 1\nlimits:\n  per_run: nope\n")
        r = self.opts("reviewer", "--cap-uu", "5")
        self.assertEqual(r.returncode, 64, r.stdout + r.stderr)
        self.assertEqual(self.started(), [])
        self.assertEqual([e.added for e in self.entries() if e.source == "umwayi agent run"],
                         ["Refused agent reviewer: units.yaml is not valid"])


class CapTests(OptionCase):
    def test_the_cap_is_the_reservation(self):
        r = self.opts("reviewer", "--cap-uu", "30", steps=(send_logs(api_request(cost_micros=12345)), END))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        [res] = self.reserves()
        self.assertTrue(res.added.endswith(": 300000 micros (30 UU)"), res.added)
        [st] = self.settles()
        self.assertTrue(st.added.endswith("released 287655 micros"), st.added)

    def test_the_smallest_cap_is_1_uu(self):
        r = self.opts("reviewer", "--cap-uu", "1", steps=(send_logs(api_request(cost_micros=5000)), END))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.reserves()[0].added.endswith(": 10000 micros (1 UU)"))

    def test_a_claude_code_run_past_its_cap_is_stopped_with_3(self):
        p = self.start_umwayi("run", "reviewer", "--prompt", "A long task", "--cap-uu", "30",
                              extra=self.script(send_logs(api_request(cost_micros=400000)), WAIT))
        code, out, _ = self.finish(p, timeout=60)
        self.assertEqual(code, 3, out)
        self.assertIn("Agent reviewer was stopped: it passed its budget of 30 UU for one run (exit 3).", out)
        self.assertEqual(self.alive_at_exit, [])
        [st] = self.settles()
        self.assertIn(": measured 400000 micros (40 UU);", st.added)
        stop = [e for e in self.entries() if e.added.startswith("Agent reviewer was stopped")][0]
        self.assertIn("the cap of this run (--cap-uu 30)", stop.checked)
        self.assertNotIn("limits.per_run", stop.checked)

    def test_under_its_cap_a_run_goes_on(self):
        r = self.opts("reviewer", "--cap-uu", "30", steps=(send_logs(api_request(cost_micros=300000)), {"do": "sleep",
                                                                                                         "s": 2}, END))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)  # exactly the cap is not past it

    def test_the_cap_not_per_run_is_what_the_day_limits_are_checked_against(self):
        self.limits(per_day=50)
        self.assertEqual(self.opts("reviewer", "--cap-uu", "30", steps=(send_logs(api_request(cost_micros=1)), END)
                                   ).returncode, 0)
        # 30 UU reserved (released to 1 UU when settled): 49 left, a 50 UU cap does not fit, a 49 UU one does
        r = self.opts("second", "--cap-uu", "50", steps=(END,))
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("the budget limit per_day has 49 UU left, a run needs 50 UU", r.stdout)
        self.assertEqual(self.opts("second", "--cap-uu", "49", steps=(END,)).returncode, 0)

    def test_without_the_cap_the_same_limits_refuse_the_default_reservation(self):
        self.limits(per_day=50)
        r = self.run_agent("reviewer", END)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("a run needs 100 UU", r.stdout)

    def test_a_cap_never_raises_a_day_limit(self):
        self.limits(per_day=20, per_run=100)
        r = self.opts("reviewer", "--cap-uu", "25", steps=(END,))
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertEqual(self.started(), [])
        self.assertEqual(self.reserves(), [])

    def test_the_budget_check_rule_sees_the_cap(self):
        from tests.budget.support import RULES
        self.write_rules(RULES.replace("agent: [reviewer, second, helper, slow]", "agent: [second, helper, slow]"))
        r = self.opts("reviewer", "--cap-uu", "30")  # no budget_check rule matches: Ask me first, with a queue item
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("Added queue item", r.stdout)
        self.assertEqual(self.started(), [])
        self.assertEqual(self.reserves(), [])
        listing = self.u("queue", "list").stdout
        self.assertIn("Spend up to 30 UU on agent reviewer?", listing)


class UnwatchedPlatformTests(OptionCase):
    """W9.R15.5: Kiro reports no cost, so the cap is the reservation and a reading above it is refused at the start."""

    def test_kiro_worst_case_above_the_cap_is_refused_with_3_and_reserves_nothing(self):
        r = self.opts("helper", "--cap-uu", "30")  # no units.yaml: unknown, 100 UU
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertEqual(r.stdout.splitlines()[0], "Ask me first")
        self.assertIn("the cap of 30 UU is below the 100 UU that umwayi counts for a kiro run (unknown)", r.stdout)
        self.assertIn("Agent helper was not started. (exit 3)", r.stdout)
        self.assertEqual(self.started(), [])
        self.assertEqual(self.reserves(), [])
        self.assertEqual(self.settles(), [])

    def test_kiro_declared_reading_above_the_cap_is_refused(self):
        self.units(KIRO_RUNS)  # 20 UU a run
        r = self.opts("helper", "--cap-uu", "19")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("the cap of 19 UU is below the 20 UU that umwayi counts for a kiro run (declared)", r.stdout)
        self.assertEqual(self.started(), [])

    def test_kiro_reading_equal_to_the_cap_starts(self):
        self.units(KIRO_RUNS)
        r = self.opts("helper", "--cap-uu", "20")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.reserves()[0].added.endswith(": 200000 micros (20 UU)"))
        self.assertIn(": declared 200000 micros (20 UU);", self.settles()[0].added)

    def test_kiro_without_the_cap_is_not_refused_by_this_rule(self):
        self.units(KIRO_RUNS)
        self.assertEqual(self.opts("helper").returncode, 0)

    def test_the_kill_switch_and_the_day_limit_win_over_this_refusal(self):
        self.kill_on()
        r = self.opts("helper", "--cap-uu", "30")
        self.assertEqual(r.returncode, 3)
        self.assertIn("The kill switch is on", r.stdout)
        self.assertNotIn("umwayi counts for", r.stdout)

    def test_claude_code_is_not_refused_by_this_rule(self):
        # its cost is watched while it runs (the telemetry receiver), so a worst-case reading above the cap is fine
        r = self.opts("reviewer", "--cap-uu", "30")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("settled, unknown 100 UU", r.stdout)


class NoChangeWithoutOptionsTests(unittest.TestCase):
    def test_build_argv_with_no_model_and_no_effort_adds_no_word(self):
        for platform, command in (("claude-code", "claude"), ("kiro", "kiro-cli")):
            a = Agent(name="a", platform=platform, command=command, transport="cli", workdir="/w")
            argv, _ = agents.build_argv(a, agents.RUN, "/bin/p", Path("/r"), "python3", prompt="Hi", src=REPO)
            self.assertNotIn("--model", argv)
            self.assertNotIn("--effort", argv)

    def test_run_options_default_is_unused(self):
        self.assertFalse(agents.RunOptions().used)
        self.assertEqual(agents.RunOptions(None, "m", None).text(), "model m")


if __name__ == "__main__":
    unittest.main()
