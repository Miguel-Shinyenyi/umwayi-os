"""Layer 10 part 8, task 10.49: a whole OpenCode chat turn with the fake, and the permission answers (requirement
10.R13 item 9, design.md part 8 "The second gate").

Written before the code. Every test runs `python -m umwayi agent chat o` as a real child process, with the fake
`opencode acp` of tests/agents/fake_opencode.py first on PATH. For every tool call the fake first runs the hook that the
inline config's plugin options name: the real stdio adapter of this repository with `--platform opencode`, which runs
`umwayi check` (the first gate, one logbook entry). A tool that OpenCode asks permission for then gets a
`session/request_permission`, which umwayi answers through the rules (the second gate, one more entry) and, for Ask me
first, through the owner's `y` or `n`. Only the fake is used; the real OpenCode is the owner's task 10.51.

The answers: Yes is `once`, No is `reject`, Ask me first asks the owner and `y` is `once`, anything else is `reject`.
`always` is never selected. A request from a child session is answered the same way. A request with no `name` gets at
most Ask me first.
"""

import time
import unittest

from umwayi import agents

from tests.agents.support import SECRET
from tests.agents.test_agents_opencode_chat import ChatCase

RULES = """rules:
  - id: o-yes
    title: o may start
    text: The agent o may start.
    verdict: yes
    matchers:
      type: agent_run
      agent: o
  - id: hook-read
    title: the first gate lets a read go on
    text: Reading is allowed.
    verdict: yes
    matchers:
      platform: opencode
      type: [tool_read, tool_grep, tool_glob]
  - id: hook-shell-no
    title: the first gate stops a wipe
    text: Never.
    verdict: no
    matchers:
      platform: opencode
      type: tool_shell
      input_command__contains: ["rm -rf"]
  - id: hook-shell-ask
    title: the first gate asks about a shell command
    text: The owner confirms.
    verdict: ask
    matchers:
      platform: opencode
      type: [tool_shell, tool_write]
  - id: perm-read
    title: a request to read is Yes
    text: Allowed.
    verdict: yes
    matchers:
      platform: opencode
      type: acp_permission
      kind: read
  - id: perm-search
    title: a request to search is No in this test
    text: Never.
    verdict: no
    matchers:
      platform: opencode
      type: acp_permission
      kind: search
  - id: perm-edit
    title: a request to edit is put to the owner
    text: The owner confirms.
    verdict: ask
    matchers:
      platform: opencode
      type: acp_permission
      kind: edit
"""


def tool(name, **inp):
    return {"tool": name, "input": inp}


class TurnCase(ChatCase):
    def setUp(self):
        super().setUp()
        self.write_rules(RULES)

    def answers(self):
        return [c["outcome"] for c in self.calls() if c.get("event") == "permission_answer"]

    def verdicts(self):
        return [(c["tool"], c["verdict"]) for c in self.calls() if c.get("event") == "tool"]

    def requests(self):
        return [c["tool"] for c in self.calls() if c.get("event") == "request_sent"]

    def checks(self):
        return [e for e in self.entries() if e.source == "umwayi check"]

    def hook_checks(self):
        return [e for e in self.checks() if "action type: tool_" in e.added]

    def perm_checks(self):
        return [e for e in self.checks() if "action type: acp_permission" in e.added]

    def assert_opencode_rules(self, entries):
        """The logbook keeps no action JSON, so the platform is proved by the rules: every rule that can match a hook or
        a permission action here has `platform: opencode`, and each entry must name one (never "rules matched: none")."""
        for e in entries:
            self.assertNotIn("rules matched: none", e.checked, e.added)

    def turn(self, actions, owner, spec=None):
        self.spec(dict({"turns": [actions]}, **(spec or {})))
        return self.run_chat(owner)


# ------------------------------------------------------------------------------------------------ 1 and 2


class WholeTurnTests(TurnCase):
    def test_a_whole_turn_hook_first_then_the_rules_and_the_owners_y_and_n(self):
        actions = [{"chunk": "Working on it CHUNK-" + SECRET},
                   tool("read", path="/etc/hostname"),                      # Yes, then Yes: once
                   tool("shell", command="ls"),                             # Ask me first, then Ask me first: owner y
                   tool("shell", command="rm -rf /"),                       # No in the first gate: no request at all
                   tool("write", path="/tmp/x"),                            # Ask me first, then Ask me first: owner n
                   tool("glob", pattern="*.md"),                            # Yes, then No: reject
                   {"chunk": "all done"}]
        r = self.turn(actions, f"go PROMPT-{SECRET}\ny\nn\n:quit\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("all done", r.stdout)
        self.assertEqual(self.verdicts(), [("read", "allow"), ("shell", "ask"), ("shell", "deny"), ("write", "ask"),
                                           ("glob", "allow")])
        self.assertEqual(self.requests(), ["read", "shell", "write", "glob"])  # the denied call asked nobody
        self.assertEqual(self.answers(), ["once", "once", "reject", "reject"])
        self.assertIn("The rules say Ask me first. Allow once? [y/N]", r.stdout)
        self.assertEqual(r.stdout.count("Allow once? [y/N]"), 2)  # the shell command and the write: two questions
        self.assert_nothing_left()
        self.assert_agent_gone()

    def test_the_hook_runs_before_each_request_and_both_are_real(self):
        r = self.turn([tool("read", path="/etc/hostname")], "go\n:quit\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        order = [c["event"] for c in self.calls() if c.get("event") in ("tool", "request_sent", "permission_answer")]
        self.assertEqual(order, ["tool", "request_sent", "permission_answer"])
        [hook] = self.hook_checks()
        self.assertIn("hook-read", hook.checked)  # the rule of the real stdio adapter run, not a stand in
        [perm] = self.perm_checks()
        self.assertIn("perm-read", perm.checked)

    def test_a_user_answer_other_than_y_is_a_no(self):
        for answer in ("n", "", "yes", "Y", "always", "a", "y y"):
            with self.subTest(answer=answer):
                self.fake_log.unlink(missing_ok=True)
                r = self.turn([tool("shell", command="ls")], f"go\n{answer}\n:quit\n")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual(self.answers(), ["reject"])

    def test_the_owner_y_is_once(self):
        r = self.turn([tool("shell", command="ls")], "go\ny\n:quit\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.answers(), ["once"])


class AlwaysTests(TurnCase):
    def test_always_is_never_selected(self):
        actions = [tool("read", path="/etc/hostname"), tool("shell", command="ls"), tool("write", path="/tmp/x"),
                   tool("glob", pattern="*"), tool("shell", command="date")]
        r = self.turn(actions, "go\ny\ny\ny\n:quit\n")  # every allow the owner can give
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(self.answers()), 5)
        self.assertEqual(sorted(set(self.answers())), ["once", "reject"])
        for answer in [c["answer"] for c in self.calls() if c.get("event") == "permission_answer"]:
            self.assertEqual(answer["result"]["outcome"]["outcome"], "selected")
            self.assertIn(answer["result"]["outcome"]["optionId"], ("once", "reject"))


# ------------------------------------------------------------------------------------------------ 3


class ChildSessionTests(TurnCase):
    def child(self, name, **inp):
        return dict(tool(name, **inp), child=True)

    def test_a_request_from_a_child_session_is_answered_like_any_other(self):
        actions = [self.child("read", path="/etc/hostname"), self.child("shell", command="ls"),
                   self.child("shell", command="rm -rf /"), self.child("write", path="/tmp/x"),
                   self.child("glob", pattern="*.md")]
        r = self.turn(actions, f"go\ny\nn\n:quit\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.requests(), ["read", "shell", "write", "glob"])
        self.assertEqual(self.answers(), ["once", "once", "reject", "reject"])
        calls = [c["call_id"] for c in self.calls() if c.get("event") == "request_sent"]
        self.assertTrue(all(c.startswith("ses_child") for c in calls), calls)
        # one entry per check, and the platform is the agent's, not a child's
        self.assertEqual(len(self.hook_checks()), 5)
        self.assertEqual(len(self.perm_checks()), 4)
        perms = self.perm_checks()
        self.assert_opencode_rules(self.hook_checks() + perms[:1] + perms[2:])  # execute has no rule: Ask me first
        log = self.log_text()
        self.assertNotIn("ses_child", log)  # the child id is agent text, never in an action
        self.assertNotIn("child-session", log)

    def test_a_child_is_not_trusted_more_than_its_parent(self):
        # the same call from a parent and from a child gets the same answer
        r = self.turn([tool("shell", command="ls"), self.child("shell", command="ls")], "go\nn\nn\n:quit\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.answers(), ["reject", "reject"])
        self.assertEqual(r.stdout.count("Allow once? [y/N]"), 2)  # the child is asked as well


# ------------------------------------------------------------------------------------------------ 4


class NoNameTests(TurnCase):
    def nameless(self, name, **inp):
        return dict(tool(name, **inp), no_name=True)

    def test_a_request_with_no_name_gets_at_most_ask_me_first(self):
        # the rule perm-read says Yes to kind read; with no name it must not be Yes
        r = self.turn([self.nameless("read", path="/etc/hostname")], "go\nn\n:quit\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Allow once? [y/N]", r.stdout)  # the owner is asked
        self.assertEqual(self.answers(), ["reject"])

    def test_the_owner_may_still_allow_it_once(self):
        r = self.turn([self.nameless("read", path="/etc/hostname")], "go\ny\n:quit\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.answers(), ["once"])

    def test_no_stays_no_and_ask_stays_ask(self):
        r = self.turn([self.nameless("glob", pattern="*"), self.nameless("write", path="/tmp/x")],
                      "go\nn\n:quit\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.answers(), ["reject", "reject"])
        self.assertEqual(r.stdout.count("Allow once? [y/N]"), 1)  # search is No (not asked), edit is asked

    def test_the_action_holds_the_kind_and_no_tool(self):
        self.turn([self.nameless("read", path="/etc/hostname")], "go\nn\n:quit\n")
        [perm] = self.perm_checks()
        self.assertIn("perm-read", perm.checked)  # matched on kind alone: the rule has no tool field to match

    def test_what_counts_as_a_name(self):
        for call, named in ((None, False), ({}, False), ({"name": ""}, False), ({"name": None}, False),
                            ({"name": 5}, False), ({"name": ["read"]}, False), ({"name": "read"}, True),
                            ({"name": "mcp__x__y"}, True)):  # a name that is not plain is still a name (the rules see the kind)
            with self.subTest(call=call):
                self.assertEqual(agents._has_tool_name(call), named)

    def test_a_request_with_a_name_is_still_yes(self):
        r = self.turn([tool("read", path="/etc/hostname")], "go\n:quit\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.answers(), ["once"])
        self.assertNotIn("Allow once?", r.stdout)


# ------------------------------------------------------------------------------------------------ 5 and 6


class LogbookTests(TurnCase):
    def run_turn(self):
        actions = [{"chunk": "CHUNK-" + SECRET}, tool("read", path="/etc/hostname-" + SECRET),
                   tool("shell", command="ls TITLE-" + SECRET), tool("shell", command="rm -rf /"),
                   tool("write", path="/tmp/RAW-" + SECRET)]
        return self.turn(actions, f"go PROMPT-{SECRET}\ny\nn\n:quit\n")

    def test_one_umwayi_check_entry_per_check_with_platform_opencode(self):
        r = self.run_turn()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        hooks, perms = self.hook_checks(), self.perm_checks()
        self.assertEqual([e.added.split("action type: ")[1].split(",")[0].split("\n")[0].split(" ")[0]
                          for e in hooks], ["tool_read", "tool_shell", "tool_shell", "tool_write"])
        self.assertEqual(len(perms), 3)  # read, ls, write; the rm -rf never asked
        others = [e.added.split("action type: ")[1] for e in self.checks() if e not in hooks and e not in perms]
        self.assertEqual(sorted(others), ["agent_run", "budget_check"])  # nothing else is a check
        self.assert_opencode_rules(hooks + perms[:1] + perms[2:])
        self.assertIn("hook-shell-no", hooks[2].checked)
        self.assertIn("rules matched: none", perms[1].checked)  # execute: no rule, so Ask me first

    def test_the_platform_is_opencode_because_only_opencode_rules_match(self):
        self.write_rules(RULES.replace("platform: opencode", "platform: kiro"))  # the same rules for another platform
        r = self.turn([tool("read", path="/etc/hostname")], "go\nn\n:quit\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        checks = self.hook_checks() + self.perm_checks()
        self.assertEqual(len(checks), 2)
        for e in checks:
            self.assertIn("rules matched: none", e.checked)  # Ask me first: no rule is for opencode now
        self.assertEqual(self.answers(), ["reject"])  # the read: owner n

    def test_nothing_of_the_conversation_the_token_or_the_config_is_in_the_logbook(self):
        r = self.run_turn()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        log = self.log_text()
        queue = self.root / "queue.md"
        queue_text = queue.read_text(encoding="utf-8") if queue.exists() else ""
        opts = self.plugin_options()
        config = self.start_record()["config_content"]
        for text in ("CHUNK-" + SECRET, "PROMPT-" + SECRET, "TITLE-" + SECRET, "RAW-" + SECRET, SECRET, opts["token"],
                     config, opts["canary"], "OPENCODE_CONFIG_CONTENT", "ses_fake"):
            self.assertNotIn(text, log, f"{text[:30]} is in the logbook")
            self.assertNotIn(text, queue_text, f"{text[:30]} is in the queue")
            self.assertNotIn(text, r.stderr)
        self.assertNotIn(opts["token"], r.stdout)
        self.assertIn("CHUNK-" + SECRET, r.stdout)  # the conversation is on the owner's screen, and only there
        runs = [e.added for e in self.run_entries()]
        self.assertEqual(len(runs), 2, runs)
        self.assertTrue(runs[0].startswith("Started agent o (opencode, acp, chat): "), runs[0])
        self.assertTrue(runs[1].startswith("Agent o exited with code 0 after "), runs[1])


# ------------------------------------------------------------------------------------------------ 7


class KillSwitchTests(TurnCase):
    def test_the_kill_switch_in_the_middle_of_a_turn_gives_3(self):
        self.spec({"turns": [[tool("read", path="/etc/hostname"), {"spawn": True}, {"wait_cancel": True}]],
                   "ignore_eof": True})
        p = self.start_chat()
        p.stdin.write("go\n")
        p.stdin.flush()
        self.wait_for(lambda c: c.get("event") == "permission_answer", "the first answer")
        self.wait_for(lambda c: c.get("event") == "spawn", "the child")
        time.sleep(2.5)
        self.kill_on()
        code, out, _ = self.finish(p)
        self.assertEqual(code, 3, out)
        self.assertIn("The kill switch stopped agent o (exit 3).", out)
        self.assertEqual(self.answers(), ["once"])
        self.assert_agent_gone()
        self.assert_nothing_left()
        self.assertNotIn(SECRET, self.log_text())


if __name__ == "__main__":
    unittest.main()
