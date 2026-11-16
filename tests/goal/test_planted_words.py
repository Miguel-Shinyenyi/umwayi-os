"""W55b: what is logged and shown of a blocked call and of a refused plan, and that a planted secret never gets there.

A blocked shell call names its rule id, its action type and the first word of its command only (for example `git` or
`curl`), never the whole command and never an argument. A refused plan names the place of its first bad context entry
and why (private, missing, bad path), never the path text. No file content is logged. A planted secret in a command or
a path never appears in the logbook, an event log, `goal status` or `goal report`.
"""

import json
import unittest

from tests.goal import cmdsupport as cs
from tests.goal import runsupport as rs
from tests.goal import test_blocked as tb
from umwayi import goal as gl
from umwayi import goalpacket as gp
from umwayi import goalstate as gs
from umwayi import logbook, rules

SECRET = "S55B-SECRET-never-in-a-record"
LOWER_SECRET = "s55b-lower-secret-arg"


def shell(command):
    return {"tool_name": "execute_bash", "tool_input": {"command": command}}


class CommandWordTests(unittest.TestCase):
    def word(self, command, kind="tool_bash", field="command"):
        return rules.command_word({"type": kind, field: command})

    def test_only_the_first_word_is_kept(self):
        self.assertEqual(self.word(f"git push https://x/{SECRET}"), "git")
        self.assertEqual(self.word(f"curl -H 'Authorization: {SECRET}' https://x", "tool_execute_bash", "input_command"), "curl")
        self.assertEqual(self.word("python3 -m pytest"), "python3")

    def test_assignments_are_skipped_and_a_path_keeps_its_last_part(self):
        self.assertEqual(self.word(f"TOKEN={SECRET} HOME=/x git push"), "git")
        self.assertEqual(self.word(f"/opt/{SECRET}/bin/curl x"), "curl")

    def test_a_word_that_could_be_a_secret_or_a_path_is_other(self):
        for command in (SECRET, f"{SECRET} x", "ghp_ABCDEF123456 x", "deadbeef1234 x", "'git' x", "./", "",
                        "A=1 B=2 C=3 D=4 E=5 F=6 G=7 H=8 I=9 git", "x" * 30):
            with self.subTest(command=command):
                self.assertEqual(self.word(command), rules.COMMAND_WORD_OTHER)

    def test_the_goal_records_know_every_shell_type_of_the_rules(self):
        self.assertEqual(set(gs.BLOCK_SHELL_TYPES), set(rules.SHELL_TYPES))
        self.assertTrue(set(rules.SHELL_TYPES) <= set(gs.BLOCK_TYPES))

    def test_other_actions_have_no_command_word(self):
        self.assertIsNone(rules.command_word({"type": "tool_read", "command": "git"}))
        self.assertIsNone(rules.command_word({"type": "tool_bash"}))
        self.assertIsNone(rules.command_word({"type": "tool_bash", "command": 7}))

    def test_the_entry_names_the_word_only_for_a_no_or_an_ask(self):
        def added(answer, **kw):
            d = rules.Decision(answer, "r1", "why", action_ok=True, rules_ok=True, action_type="tool_bash",
                               command_word="git", **kw)
            return rules.log_entry(d, "2026-11-15").added
        self.assertEqual(added(rules.NO), "Rule r1 gave No; action type: tool_bash; command word: git")
        self.assertEqual(added(rules.ASK), "Rule r1 gave Ask me first; action type: tool_bash; command word: git")
        self.assertEqual(added(rules.YES), "Rule r1 gave Yes; action type: tool_bash")
        self.assertEqual(added(rules.NO, stopped_by="the kill switch"), "The kill switch gave No; action type: tool_bash")
        self.assertNotIn("command word", rules.Decision(rules.NO, "r1", "why", command_word="git").to_dict().values())
        self.assertNotIn("command_word", rules.Decision(rules.NO, "r1", "why", command_word="git").to_dict())


class BlockedShellCallTests(rs.RunCase):
    def setUp(self):
        super().setUp()
        (self.root / "rules.yaml").write_text(tb.RULES, encoding="utf-8")

    def run_builder(self, steps):
        goal = self.approved(1)
        return goal, self.run_task(goal, "T-01", [{"steps": steps, "spend": 5}])

    def records_and_views(self, goal):
        ctx = gl.Ctx(self.root, int(self.clock()), self.out.append, self.out.append, tty=lambda: False,
                     gate=lambda root, name, workdir=None: None, env_kw={})
        parts = [(self.root / "LOGBOOK.md").read_text(encoding="utf-8")]
        parts += [p.read_text(encoding="utf-8") for p in gs.goal_dir(self.root, goal).iterdir()]  # task file, event logs
        if (self.root / "queue.md").exists():
            parts.append((self.root / "queue.md").read_text(encoding="utf-8"))
        parts += gl.status_lines(ctx) + gl.report_lines(ctx, goal) + self.out
        return "\n".join(parts)

    def test_a_planted_secret_in_a_command_never_reaches_a_record_or_a_view(self):
        for command, word in ((f"git push https://example.invalid/{SECRET} {LOWER_SECRET}", "git"),
                              (f"TOKEN={SECRET} curl {LOWER_SECRET}", "curl"),
                              (f"/home/{SECRET}/bin/curl {LOWER_SECRET}", "curl"),
                              (f"{SECRET} --flag {LOWER_SECRET}", "other")):
            with self.subTest(word=word, command=command[:12]):
                self.setUp()
                goal, out = self.run_builder([{"hook": shell(command)}, {"exit": 2}])
                self.assertEqual((out.exit, out.state, out.word), (3, "needs owner", "tool_blocked_by_rule"))
                b = gs.read_task(self.root, goal, "T-01")[gs.BLOCKED_KEY]
                self.assertEqual(b, {"rule": "kiro-ask-shell", "answer": "Ask me first", "type": "tool_execute_bash",
                                     "command": word})
                checks = [e.added for e in logbook.read_checked(self.root) if e.source == "umwayi check"]
                self.assertIn(f"Rule kiro-ask-shell gave Ask me first; action type: tool_execute_bash; command word: {word}",
                              checks)
                text = self.records_and_views(goal)
                self.assertIn(f"Blocked: rule kiro-ask-shell gave Ask me first for action type tool_execute_bash, "
                              f"command word {word}", text)
                self.assertNotIn(SECRET, text)
                self.assertNotIn(LOWER_SECRET, text)

    def test_a_planted_secret_in_a_path_never_reaches_a_record_or_a_view(self):
        goal, out = self.run_builder([{"hook": {"tool_name": "delete_file", "tool_input": {"path": f"umwayi/{SECRET}.py"}}},
                                      {"exit": 2}])
        self.assertEqual(gs.read_task(self.root, goal, "T-01")[gs.BLOCKED_KEY],
                         {"rule": "kiro-no-delete", "answer": "No", "type": "tool_delete_file"})
        self.assertNotIn(SECRET, self.records_and_views(goal))

    def test_a_command_word_on_a_type_that_is_not_a_shell_is_dropped_and_a_bad_one_is_refused(self):
        self.assertNotIn("command", gs.block_words("r", "No", "tool_read_file", {"r"}, "git"))
        self.assertEqual(gs.block_words("r", "No", "tool_bash", {"r"}, SECRET)["command"], "other")
        bad = {"rule": "r", "answer": "No", "type": "tool_bash", "command": SECRET}
        with self.assertRaises(gs.GoalError):
            gs.blocked_fact(bad)
        with self.assertRaises(gs.GoalError):
            gs.blocked_fact(dict(bad, type="tool_read_file", command="git"))


class RefusedContextTests(cs.CmdCase):
    def start_with_context(self, context):
        line = cs.plan_line()
        line["body"]["tasks"][0]["context"] = context
        code = self.call("start", cs.GOAL_TEXT, "claude-guide", 20, scripts=[{"steps": [line], "spend": 4}])
        self.assertEqual(code, 2, self.err)
        return gs.list_goals(self.root)[-1]

    def views(self, goal):
        self.out.clear()
        self.assertEqual(self.call("status", goal), 0)
        status = "\n".join(self.out)
        self.out.clear()
        self.assertEqual(self.call("report", goal), 0)
        return status, "\n".join(self.out)

    def everything(self, goal, status, report):
        parts = [self.logbook_text(), status, report, "\n".join(self.err)]
        parts += [p.read_text(encoding="utf-8") for p in gs.goal_dir(self.root, goal).iterdir() if p.is_file()]
        if (self.root / "queue.md").exists():
            parts.append((self.root / "queue.md").read_text(encoding="utf-8"))
        return "\n".join(parts)

    def test_the_place_and_the_word_of_the_first_bad_context_entry_are_logged_and_shown(self):
        for context, entry, why in ((["README.md", f"docs/{SECRET}.md"], 2, "missing"),
                                    ([f"memory/private/{SECRET}.md", "README.md"], 1, "private"),
                                    (["README.md", "README.md", f"../{SECRET}"], 3, "bad path"),
                                    ([f"/etc/{SECRET}"], 1, "bad path")):
            with self.subTest(why=why, entry=entry):
                self.setUp()
                goal = self.start_with_context(context)
                g = gs.read_goal(self.root, goal)
                self.assertEqual((g["refused"], g[gs.REFUSED_CONTEXT_KEY]), ("context", {"task": 1, "entry": entry, "why": why}))
                words = f"context: task 1, entry {entry}, {why}"
                self.assertIn(f"was refused ({words})", "\n".join(self.err))
                self.assertIn(f"Context entry {entry} of task 1: {why}.", self.logbook_text())
                status, report = self.views(goal)
                self.assertIn(f"  The plan was refused ({words}).", status)
                self.assertIn(f"the plan was refused ({words})", report)
                self.assertNotIn(SECRET, self.everything(goal, status, report))

    def test_a_plan_refused_for_another_reason_names_no_context_entry(self):
        code = self.call("start", cs.GOAL_TEXT, "claude-guide", 20, scripts=[{"steps": [{"print": "no plan"}], "spend": 4}])
        self.assertEqual(code, 2)
        g = gs.read_goal(self.root, gs.list_goals(self.root)[-1])
        self.assertEqual(g["refused"], "unclear")
        self.assertNotIn(gs.REFUSED_CONTEXT_KEY, g)

    def test_the_parser_gives_the_place_and_never_the_path(self):
        tasks = [{"goal": "Do the numbered piece of work number 1 now.", "context": ["a.md", f"b/{SECRET}"],
                  "checks": ["Check number 1 of the piece can be answered pass or fail."], "size": 40, "files": ["x.py"]}]
        with self.assertRaises(gp.PlanError) as cm:
            gp.parse_plan(json.dumps({"tasks": tasks}).encode(), file_size=lambda p: 1 if p == "a.md" else None)
        self.assertEqual((cm.exception.word, cm.exception.index, cm.exception.entry, cm.exception.why),
                         ("context", 1, 2, "missing"))
        self.assertNotIn(SECRET, str(cm.exception))

    def test_a_goal_file_with_a_bad_refused_context_does_not_read(self):
        goal = self.start_with_context([f"docs/{SECRET}.md"])
        path = gs.goal_dir(self.root, goal) / "goal.json"
        g = json.loads(path.read_text(encoding="utf-8"))
        for bad in ({"task": 1, "entry": 1, "why": SECRET}, {"task": 0, "entry": 1, "why": "missing"},
                    {"task": 1, "entry": 1, "why": "missing", "path": SECRET}, "missing"):
            with self.subTest(bad=bad):
                path.write_text(json.dumps(dict(g, refused_context=bad)), encoding="utf-8")
                with self.assertRaises(gs.GoalError):
                    gs.read_goal(self.root, goal)


if __name__ == "__main__":
    unittest.main()
