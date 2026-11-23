"""W78 step 8 (W41 C2): a tool call the platform reported and no hook checked is a finding, after the run.

  * telemetry: the `tool_result` and `tool_decision` events keep an id and a tool name and nothing else (no input, no
    parameter, no prompt). A bad id is counted, not kept.
  * rules: the Checked line of a `umwayi check` entry names the call's `tool_use_id` when it is a plain one; the JSON answer
    does not change.
  * `toolcheck.review`: found, ok, or cannot tell. A missing report is never "all checked".
  * Real runs (`agent run` with the fake claude, the real hook, the real receiver) under a mode file that says `enforced`: one
    call with no hook is one finding (one entry, one queue row, exit 2); every call checked is none; no report is "cannot tell"
    and exit 0; a cooperative agent and a root with no mode file are as they were.

What it does not show: that real Claude Code names its calls as the fake does. No real Claude Code ran. It detects after the
call; it does not stop it.
"""
import datetime
import json
import unittest

from tests.agents.support import SECRET
from tests.budget import support as bs
from umwayi import rules, telemetry, toolcheck

AGENT = ("agents:\n  - name: reviewer\n    platform: claude-code\n    command: claude\n    workdir: {work}\n"
         "    env_keep: [FAKE_LOG, FAKE_SCRIPT, FAKE_PLANT, FAKE_CLAUDE_AUTH, FAKE_CLAUDE_AUTH_EXIT]\n")


def tool_event(tid, name="Bash", kind="tool_result", extra=()):
    attrs = [bs._attr("event.name", kind), bs._attr("tool_name", name), bs._attr("tool_use_id", tid),
             bs._attr("tool_input", "SECRET-INPUT " + SECRET), bs._attr("prompt", bs.PROMPT_TEXT), *extra]
    return {"timeUnixNano": "1", "body": {"stringValue": "claude_code." + kind}, "attributes": attrs}


class FoldTests(unittest.TestCase):
    def fold(self, *records):
        t = telemetry.Totals()
        t.fold_logs(bs.logs(*records))
        return t.report()

    def test_an_id_and_a_name_are_kept_and_nothing_else(self):
        r = self.fold(tool_event("toolu_a", "Bash"), tool_event("toolu_b", "Edit", "tool_decision"))
        self.assertEqual(r["tools"], {"toolu_a": "Bash", "toolu_b": "Edit"})
        self.assertNotIn("SECRET-INPUT", json.dumps(r))
        self.assertNotIn(bs.PROMPT_TEXT, json.dumps(r))

    def test_a_bad_id_or_name_is_counted_not_kept(self):
        r = self.fold(tool_event("bad id!"), tool_event("x" * 65), tool_event("toolu_ok", "no good name"))
        self.assertEqual(r["tools"], {})
        self.assertEqual(r["tools_bad"], 3)

    def test_the_cap_is_a_count_not_a_crash(self):
        old, telemetry.MAX_TOOL_IDS = telemetry.MAX_TOOL_IDS, 2
        self.addCleanup(setattr, telemetry, "MAX_TOOL_IDS", old)
        r = self.fold(*(tool_event(f"toolu_{i}") for i in range(4)))
        self.assertEqual(len(r["tools"]), 2)
        self.assertEqual(r["tools_bad"], 2)

    def test_an_api_request_next_to_a_tool_event_is_still_counted(self):
        r = self.fold(bs.api_request(), tool_event("toolu_a"))
        self.assertEqual(r["requests"], 1)
        self.assertEqual(r["tools"], {"toolu_a": "Bash"})


class RulesEntryTests(unittest.TestCase):
    def entry(self, tid):
        action = {"type": "tool_bash", "platform": "claude-code", "tool": "Bash"}
        if tid is not None:
            action["tool_use_id"] = tid
        d = rules.check(json.dumps(action), __import__("pathlib").Path("/nonexistent/rules.yaml"))
        return d, rules.log_entry(d, "2026-11-23")

    def test_a_plain_id_is_in_the_checked_line_and_not_in_the_answer(self):
        d, e = self.entry("toolu_01ABC")
        self.assertTrue(e.checked.endswith("; tool use id: toolu_01ABC"), e.checked)
        self.assertNotIn("toolu_01ABC", json.dumps(d.__dict__.get("reason", "")))

    def test_no_id_and_a_bad_id_leave_the_line_as_it_was(self):
        for tid in (None, "bad id", "x" * 70, "a;b"):
            with self.subTest(tid=tid):
                self.assertNotIn("tool use id", self.entry(tid)[1].checked)

    def test_the_id_is_found_again_by_toolcheck(self):
        m = toolcheck._ID.search("rules matched: none; tool use id: toolu_01ABC")
        self.assertEqual(m.group(1), "toolu_01ABC")


class ReviewTests(bs.BudgetCase):
    def report(self, tools, **kw):
        return dict({"requests": 1, "invalid": None, "tools_bad": 0, "tools": tools}, **kw)

    def log_check(self, tid):
        from umwayi import logbook
        logbook.append(self.root, logbook.Entry("2026-11-23", "umwayi check", "Rule x gave Yes; action type: tool_bash",
                                                f"rules matched: x; tool use id: {tid}", "The action was not run."))

    def test_ok_found_and_the_order(self):
        since = toolcheck.mark(self.root)
        self.log_check("toolu_a")
        self.assertEqual(toolcheck.review(self.root, since, self.report({"toolu_a": "Bash"})), (toolcheck.OK, []))
        got = toolcheck.review(self.root, since, self.report({"toolu_a": "Bash", "toolu_z": "Edit", "toolu_m": "Bash"}))
        self.assertEqual(got, (toolcheck.FOUND, [("toolu_m", "Bash"), ("toolu_z", "Edit")]))

    def test_an_entry_before_the_mark_does_not_check_a_later_call(self):
        self.log_check("toolu_old")
        since = toolcheck.mark(self.root)
        self.assertEqual(toolcheck.review(self.root, since, self.report({"toolu_old": "Bash"}))[0], toolcheck.FOUND)

    def test_cannot_tell_is_never_ok(self):
        since = toolcheck.mark(self.root)
        for name, rep, mark in (("no report", None, since), ("no log arrived", self.report({}, requests=0), since),
                                ("invalid", self.report({}, invalid="x"), since), ("bad ids", self.report({}, tools_bad=1), since),
                                ("no mark", self.report({}), None)):
            with self.subTest(case=name):
                self.assertEqual(toolcheck.review(self.root, mark, rep)[0], toolcheck.CANNOT_TELL)

    def test_the_entry_names_ten_and_counts_the_rest(self):
        missing = [(f"toolu_{i:02d}", "Bash") for i in range(13)]
        added, checked = toolcheck.entry_lines("reviewer", missing)
        self.assertEqual(added, "Unchecked tool calls during the run of agent reviewer: 13")
        self.assertIn("toolu_09 (Bash)", checked)
        self.assertNotIn("toolu_10", checked)
        self.assertTrue(checked.endswith("and 3 more"))


class RunCase(bs.BudgetCase):
    def setUp(self):
        super().setUp()
        self.write_agents(AGENT)
        self.roomy_budget()
        if hasattr(self, "fake_sandbox_tools"):
            self.fake_sandbox_tools()

    def mode(self, text):
        (self.root / ".umwayi").mkdir(exist_ok=True)
        (self.root / ".umwayi" / "enforcement.yaml").write_text(text, encoding="utf-8")

    def enforced(self):
        self.mode("enforcement: enforced\n")

    def go(self, *steps):
        r = self.run_agent("reviewer", *steps)
        self.assertIn(r.returncode, (0, 2, 3), r.stdout + r.stderr)
        return r

    def read_tool(self, tid, **kw):
        return dict({"do": "tool", "tool": "Read", "input": {"file_path": "/p/a"}, "id": tid}, **kw)

    def report(self, *ids):
        return bs.send_logs(bs.api_request(), *(tool_event(i, "Read") for i in ids))

    def findings(self):
        return [e for e in self.entries() if e.added.startswith("Unchecked tool calls during the run")]


class RealRunTests(RunCase):
    def test_one_call_with_no_hook_is_one_finding_with_one_entry_one_row_and_exit_2(self):
        self.enforced()
        r = self.go(self.read_tool("toolu_a"), self.read_tool("toolu_b", skip_hook=True), self.report("toolu_a", "toolu_b"))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        (f,) = self.findings()
        self.assertEqual(f.added, "Unchecked tool calls during the run of agent reviewer: 1")
        self.assertIn("toolu_b (Read)", f.checked)
        self.assertNotIn("toolu_a", f.checked)
        self.assertIn("1 tool call(s) ran without a check entry", r.stdout)
        queue = (self.root / "queue.md").read_text(encoding="utf-8")
        self.assertIn("Unchecked tool calls during a run of agent reviewer", queue)

    def test_every_call_checked_is_no_finding_and_exit_0(self):
        self.enforced()
        r = self.go(self.read_tool("toolu_a"), self.read_tool("toolu_b"), self.report("toolu_a", "toolu_b"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.findings(), [])
        self.assertNotIn("cannot tell", r.stdout)

    def test_no_report_is_cannot_tell_never_all_checked(self):
        self.enforced()
        r = self.go(self.read_tool("toolu_a", skip_hook=True))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("cannot tell", r.stdout)
        self.assertEqual(self.findings(), [])

    def test_a_cooperative_agent_and_no_mode_file_are_as_they_were(self):
        steps = (self.read_tool("toolu_b", skip_hook=True), self.report("toolu_b"))
        r = self.go(*steps)  # no mode file
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        until = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
        self.mode(f"enforcement: enforced\nagents:\n  reviewer:\n    enforcement: cooperative\n    until: {until}\n")
        r = self.go(*steps)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.findings(), [])

    def test_planted_fault_a_check_that_ignored_the_ids_would_find_nothing(self):
        """The same call, checked by the hook this time: no finding. So the finding above comes from the missing entry."""
        self.enforced()
        r = self.go(self.read_tool("toolu_b"), self.report("toolu_b"))
        self.assertEqual(self.findings(), [])
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
