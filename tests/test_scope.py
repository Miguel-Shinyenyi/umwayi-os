"""W9.16: the scope of a task, checked while its helper runs (umwayi/scope.py, `umwayi check --scope`, the Claude Code hook).

  * the scope file: strict shape; a link, a folder, a big file or the wrong keys are refused;
  * `violates`: a write inside the packet's files, folders and the own files is fine; outside the worktree, a protected path, `..`, an
    unlisted file are not; a call that is not a file write is never a violation;
  * `umwayi check --scope`: an overlay that only adds a No. A rule's Yes does not allow what the scope refuses; a rule's No stays No; the
    kill switch comes first; an unreadable scope file makes every file write No and leaves other calls to the rules; the entry says
    "The scope of the task gave No";
  * the Claude Code hook with `--scope` denies a write outside the scope.
Each rule has a planted fault. What it does not cover (a Bash command, a link that points out of the worktree, a Kiro or OpenCode run)
is written in umwayi/scope.py and in the limits.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from umwayi import scope

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "adapters" / "claude_code" / "hook.py"
RULES = """rules:
  - id: write-yes
    title: writes are fine
    text: Writing is allowed.
    verdict: yes
    matchers:
      type: tool_write
  - id: edit-no
    title: no edits
    text: Editing is refused.
    verdict: no
    matchers:
      type: tool_edit
  - id: read-yes
    title: reads are fine
    text: Reading is allowed.
    verdict: yes
    matchers:
      type: tool_read
  - id: bash-yes
    title: bash is fine
    text: x
    verdict: yes
    matchers:
      type: tool_bash
"""


class ScopeCase(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory(prefix="usc")
        self.addCleanup(self._t.cleanup)
        self.base = Path(self._t.name).resolve()
        self.root = self.base / "root"
        self.wt = self.base / "wt"
        self.root.mkdir()
        self.wt.mkdir()
        (self.root / "rules.yaml").write_text(RULES, encoding="utf-8")
        self.file = self.base / "scope.json"
        self.file.write_bytes(scope.make(str(self.wt), ["umwayi/a.py", "docs/"], ["docs-parts/status-log/G-0001-T-01.md"]))

    def action(self, typ="tool_write", path="umwayi/a.py", **kw):
        return dict({"type": typ, "platform": "claude-code", "tool": "x", "path": str(self.wt / path), "cwd": str(self.wt)}, **kw)


class FileTests(ScopeCase):
    def test_make_and_load_round_trip_and_the_shape_is_strict(self):
        sc = scope.load(self.file)
        self.assertEqual((sc["worktree"], sc["files"], sc["own"]), (str(self.wt), ["umwayi/a.py", "docs/"], ["docs-parts/status-log/G-0001-T-01.md"]))
        for bad in (b"{", b"[]", json.dumps({"version": 1}).encode(), json.dumps({"version": 2, "worktree": "/w", "files": [], "own": []}).encode(),
                    json.dumps({"version": 1, "worktree": "w", "files": [], "own": []}).encode(),
                    json.dumps({"version": 1, "worktree": "/w", "files": [1], "own": []}).encode(),
                    json.dumps({"version": 1, "worktree": "/w", "files": [], "own": [], "x": 1}).encode(), b"x" * (scope.MAX_BYTES + 1)):
            with self.subTest(bad=bad[:30]):
                p = self.base / "bad.json"
                p.write_bytes(bad)
                with self.assertRaises(scope.ScopeError):
                    scope.load(p)

    def test_a_link_a_folder_and_a_missing_file_are_refused(self):
        os.symlink(self.file, self.base / "link.json")
        for p in (self.base / "link.json", self.base, self.base / "nope.json"):
            with self.subTest(p=p.name), self.assertRaises(scope.ScopeError):
                scope.load(p)

    def test_a_worktree_that_is_not_absolute_cannot_be_made(self):
        with self.assertRaises(ValueError):
            scope.make("relative", [], [])


class ViolatesTests(ScopeCase):
    def v(self, **kw):
        return scope.violates(scope.load(self.file), self.action(**kw))

    def test_the_packets_files_folders_and_own_files_are_allowed(self):
        for path in ("umwayi/a.py", "docs/x/y.md", "docs-parts/status-log/G-0001-T-01.md"):
            with self.subTest(path=path):
                self.assertFalse(self.v(path=path))

    def test_everything_else_is_a_violation(self):
        for path in ("umwayi/b.py", "rules.yaml", "docs-parts/status-log/G-0001-T-02.md", "../outside.txt", "umwayi/../rules.yaml",
                     "tools/x.py", ".umwayi/enforcement.yaml"):
            with self.subTest(path=path):
                self.assertTrue(self.v(path=path))
        self.assertTrue(self.v(path="/etc/passwd"))  # an absolute path outside the worktree
        self.assertTrue(scope.violates(scope.load(self.file), {"type": "tool_write", "path": str(self.wt)}))  # the worktree itself

    def test_a_relative_path_is_taken_from_the_calls_cwd_and_without_one_from_the_worktree(self):
        a = {"type": "tool_write", "path": "umwayi/a.py", "cwd": str(self.wt)}
        self.assertFalse(scope.violates(scope.load(self.file), a))
        self.assertTrue(scope.violates(scope.load(self.file), dict(a, cwd=str(self.wt / "tools"))))  # tools/umwayi/a.py is not the file
        self.assertFalse(scope.violates(scope.load(self.file), {"type": "tool_write", "path": "umwayi/a.py"}))

    def test_a_call_that_is_not_a_file_write_is_never_a_violation(self):
        for typ in ("tool_read", "tool_bash", "tool_glob", "tool_webfetch"):
            self.assertFalse(self.v(typ=typ, path="rules.yaml"))
        for typ in scope.WRITE_TYPES:
            self.assertTrue(self.v(typ=typ, path="rules.yaml"))

    def test_an_empty_scope_refuses_every_file_write(self):
        self.file.write_bytes(scope.make(str(self.wt), [], []))
        self.assertTrue(self.v(path="umwayi/a.py"))

    def test_planted_fault_a_check_that_ignored_the_worktree_would_allow_a_path_outside(self):
        self.assertTrue(self.v(path="../wt-other/umwayi/a.py"))  # the same tail, another folder


class CheckCommandTests(ScopeCase):
    def check(self, action, scope_file="DEFAULT", kill=False):
        if kill:
            (self.root / ".umwayi").mkdir(exist_ok=True)
            (self.root / ".umwayi" / "KILL").write_text("", encoding="utf-8")
        args = [sys.executable, "-m", "umwayi", "--root", str(self.root), "check", "-", "--json", "--kill-switch"]
        sf = self.file if scope_file == "DEFAULT" else scope_file
        if sf is not None:
            args += ["--scope", str(sf)]
        p = subprocess.run(args, input=json.dumps(action), capture_output=True, text=True, timeout=60, env=dict(os.environ, PYTHONPATH=str(REPO)))
        self.assertIn(p.returncode, (0, 2, 3), p.stdout + p.stderr)
        return p.returncode, json.loads(p.stdout)

    def log(self):
        return (self.root / "LOGBOOK.md").read_text(encoding="utf-8")

    def test_a_write_inside_is_the_rules_answer_and_outside_is_no_whatever_the_rules_say(self):
        code, data = self.check(self.action(path="umwayi/a.py"))
        self.assertEqual((code, data["answer"], data["rule_id"]), (0, "Yes", "write-yes"))
        code, data = self.check(self.action(path="rules.yaml"))
        self.assertEqual((code, data["answer"]), (2, "No"))
        self.assertIn("The scope of the task gave No", self.log())
        self.assertIn("action type: tool_write", self.log())

    def test_the_overlay_never_allows_a_no_stays_no_inside_the_scope(self):
        code, data = self.check(self.action(typ="tool_edit", path="umwayi/a.py"))
        self.assertEqual((code, data["answer"], data["rule_id"]), (2, "No", "edit-no"))

    def test_a_call_that_is_not_a_file_write_is_left_to_the_rules(self):
        code, data = self.check(self.action(typ="tool_read", path="rules.yaml"))
        self.assertEqual((code, data["answer"]), (0, "Yes"))
        code, data = self.check({"type": "tool_bash", "platform": "claude-code", "command": "ls"})
        self.assertEqual((code, data["answer"]), (0, "Yes"))

    def test_an_unreadable_scope_file_refuses_every_file_write_and_no_other_call(self):
        for sf in (self.base / "nope.json", self.base):
            with self.subTest(sf=sf.name):
                self.assertEqual(self.check(self.action(path="umwayi/a.py"), scope_file=sf)[0], 2)
                self.assertEqual(self.check(self.action(typ="tool_read"), scope_file=sf)[0], 0)

    def test_the_kill_switch_comes_first(self):
        code, data = self.check(self.action(path="umwayi/a.py"), kill=True)
        self.assertEqual(code, 2)
        self.assertIn("The kill switch gave No", self.log())

    def test_without_the_option_the_answer_is_what_it_was(self):
        code, data = self.check(self.action(path="rules.yaml"), scope_file=None)
        self.assertEqual((code, data["answer"]), (0, "Yes"))  # planted fault: no overlay, the rules' Yes stands

    def test_a_scope_stop_is_not_moved_to_yes_by_autonomy(self):
        self.assertEqual(self.check(self.action(path="rules.yaml"))[1]["answer"], "No")


class SettingsTests(unittest.TestCase):
    def test_the_hook_gets_the_scope_flag_only_when_given(self):
        from umwayi import agents
        args = lambda **kw: json.loads(agents.claude_settings("python3", Path("/h/hook.py"), Path("/r"), **kw))["hooks"]["PreToolUse"][0]["hooks"][0]["args"]
        self.assertNotIn("--scope", args())
        self.assertEqual(args(scope="/s.json")[-2:], ["--scope", "/s.json"])

    def test_agent_run_refuses_a_scope_file_for_kiro_and_without_a_worktree(self):
        from umwayi.errors import UsageError
        from umwayi import agents
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "agents.yaml").write_text("agents:\n  - name: k\n    platform: kiro\n    command: kiro-cli\n    workdir: " + d
                                              + "/w\n    trust_tools: [read_file]\n  - name: c\n    platform: claude-code\n    command: claude\n    workdir: "
                                              + d + "/w\n", encoding="utf-8")
            (root / "w").mkdir()
            for name, wd in (("k", str(root / "w")), ("c", None)):
                with self.subTest(agent=name), self.assertRaises(UsageError):
                    agents.run_agent(root, name, "hi", lambda: "2026-11-23", scope_file="/x/s.json", workdir=wd)


class HookTests(ScopeCase):
    def hook(self, path, *flags):
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Write", "tool_input": {"file_path": str(self.wt / path)},
                   "cwd": str(self.wt)}
        p = subprocess.run([sys.executable, str(HOOK), "--root", str(self.root), *flags], input=json.dumps(payload), capture_output=True,
                           text=True, timeout=60)
        if p.returncode == 2:
            return "deny"
        return json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"]

    def test_the_hook_with_scope_denies_a_write_outside_and_allows_one_inside(self):
        self.assertEqual(self.hook("umwayi/a.py", "--scope", str(self.file)), "allow")
        self.assertEqual(self.hook("rules.yaml", "--scope", str(self.file)), "deny")

    def test_planted_fault_the_same_hook_without_scope_allows_it(self):
        self.assertEqual(self.hook("rules.yaml"), "allow")


if __name__ == "__main__":
    unittest.main()
