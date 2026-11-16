"""W44: `umwayi up`, the front door, a thin layer over the commands that exist.

A root is made in a temporary folder: umwayi.json, rules.yaml, an agents file whose working folder is outside the root, a
guidance.yaml that loads, and a git repo with a main branch. The login probes of the agents are replaced by fixed answers
(loginwizard.status_of), so no agent program is needed; one test runs the real command as a child process with no agent
program on PATH. Every rule of umwayi up has a planted fault: the state that breaks the rule is put in place and the test
checks that up refuses with the right exit code and starts nothing. Dates are today's UTC date, never a fixed day.
"""
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.goal.fakeroot import GIT_ENV, git, needs_git
from umwayi import agents, kill, logbook, loginwizard, up
from umwayi.cli import main

REPO = Path(__file__).resolve().parents[1]
TODAY = datetime.now(timezone.utc).date().isoformat()
GUIDANCE = """version: 1
guidance:
  - id: goal-sentence-present
    source_repo: hub
    source: "understanding-first.md#3"
    text: "A task states its goal in one sentence before any work starts."
    kind: enforce
    check: goal_sentence_present
    applies_to: task
    tier: 3
    source_hash: "2f0405e879b6615f34c5168161153363896e26eab43981dc6db1d96b0c1f6bc0"
"""


def tree(root):
    out = {}
    for p in sorted(Path(root).rglob("*")):
        rel = p.relative_to(root).as_posix()
        if rel.startswith(".git/") or rel == ".git":
            continue
        out[rel] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "dir"
    return out


def fixed(kinds):
    """A replacement for loginwizard.status_of: the kind of each agent by name (ok when not named)."""
    def status_of(root, agent):
        kind = kinds.get(agent.name, loginwizard.OK)
        return loginwizard.Status(agent, kind, "a fixed answer of the test")
    return status_of


class Base(unittest.TestCase):
    def setUp(self):
        needs_git()
        tmp = tempfile.TemporaryDirectory(prefix="umwayi-up-")
        self.addCleanup(tmp.cleanup)
        base = Path(os.path.realpath(tmp.name))
        self.root = base / "root"
        self.root.mkdir()
        work = base / "work"
        work.mkdir()
        (self.root / "umwayi.json").write_text(json.dumps({"memory_dir": "memory", "private_paths": []}))
        (self.root / "rules.yaml").write_text((REPO / "rules.yaml").read_text(encoding="utf-8"))
        (self.root / "agents.yaml").write_text(
            "agents:\n"
            f"  - name: guide\n    platform: kiro\n    command: kiro-cli\n    workdir: {work}\n"
            f"  - name: builder\n    platform: kiro\n    command: kiro-cli\n    workdir: {work}\n")
        (self.root / "guidance.yaml").write_text(GUIDANCE)
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "first")
        self.kinds = {}

    def up(self, *argv, start=None):
        """Run umwayi up in process. `start` replaces goal.dispatch (a spy) for the --goal tests."""
        out, err = io.StringIO(), io.StringIO()
        old = sys.stderr
        sys.stderr = err
        patches = [mock.patch("umwayi.up.loginwizard.status_of", side_effect=fixed(self.kinds)),
                   mock.patch("umwayi.cli._today", return_value=TODAY)]
        if start is not None:
            patches.append(mock.patch("umwayi.goal.dispatch", side_effect=start))
        try:
            for p in patches:
                p.start()
            code = main(["--root", str(self.root), "up", *argv], out=out)
        finally:
            for p in patches:
                p.stop()
            sys.stderr = old
        return code, out.getvalue(), err.getvalue()

    def assertNothingWritten(self, before):
        self.assertEqual(tree(self.root), before)
        self.assertFalse((self.root / "LOGBOOK.md").exists())


class ReadyTests(Base):
    def test_a_ready_root_is_exit_0_with_one_line_per_check_in_order_and_the_next_step(self):
        code, out, err = self.up()
        self.assertEqual(code, 0, out + err)
        names = [l.split(": ")[1].split(" ")[0] if l.split(": ")[1].startswith("agent ") else l.split(": ")[1]
                 for l in out.splitlines() if re.match(r"^(ok|no|ask|info): ", l)]
        self.assertEqual(names, ["root", "logbook", "kill switch", "agent", "agent", "guidance", "git", "goals"])
        self.assertIn("ok: agent guide: ok:", out)
        self.assertIn("Ready. Next: umwayi goal start", out)
        self.assertIn("umwayi serve --page ui/dist/goal-map.html", out)
        self.assertIn("No goals.", out)

    def test_without_goal_it_writes_nothing_and_makes_no_logbook(self):
        before = tree(self.root)
        self.assertEqual(self.up()[0], 0)
        self.assertNothingWritten(before)

    def test_with_an_existing_logbook_it_adds_no_entry(self):
        logbook.append(self.root, logbook.Entry(TODAY, "tests", "start", "start", "start"))
        n = len(logbook.read_checked(self.root))
        before = tree(self.root)
        self.assertEqual(self.up()[0], 0)
        self.assertEqual(len(logbook.read_checked(self.root)), n)
        self.assertEqual(tree(self.root), before)

    def test_an_opencode_agent_is_info_and_does_not_change_the_code(self):
        self.kinds = {"builder": loginwizard.NOT_OFFERED}
        code, out, _ = self.up()
        self.assertEqual(code, 0)
        self.assertIn("info: agent builder: not offered:", out)


class PlantedFaultTests(Base):
    """One planted fault for each rule. Each test puts in place the state that breaks the rule and checks the refusal."""

    def test_PLANTED_FAULT_a_hand_edited_logbook_is_exit_2(self):
        logbook.append(self.root, logbook.Entry(TODAY, "tests", "start", "start", "start"))
        p = self.root / "LOGBOOK.md"
        p.write_text(p.read_text(encoding="utf-8").replace("start", "begin", 1), encoding="utf-8")
        before = tree(self.root)
        code, out, _ = self.up()
        self.assertEqual(code, 2)
        self.assertIn("no: logbook:", out)
        self.assertEqual(tree(self.root), before)

    def test_PLANTED_FAULT_the_kill_switch_on_is_ask_me_first(self):
        kill.turn_on(self.root, TODAY, "test")
        code, out, _ = self.up()
        self.assertEqual(code, 3)
        self.assertIn("ask: kill switch: on", out)

    def test_PLANTED_FAULT_a_kill_switch_that_cannot_be_read_is_ask_me_first(self):
        with mock.patch("umwayi.up.kill.state", return_value="unknown"):
            code, out, _ = self.up()
        self.assertEqual(code, 3)
        self.assertIn("ask: kill switch: unknown", out)

    def test_PLANTED_FAULT_an_agent_that_needs_a_sign_in_is_exit_2_and_no_sign_in_is_started(self):
        self.kinds = {"builder": loginwizard.NEEDS}
        with mock.patch("umwayi.agents.login_agent", side_effect=AssertionError("a sign-in was started")):
            code, out, _ = self.up()
        self.assertEqual(code, 2)
        self.assertIn("no: agent builder: needs a sign-in:", out)
        self.assertIn("Run umwayi login to sign in.", out)

    def test_PLANTED_FAULT_an_agent_that_cannot_be_checked_is_exit_2(self):
        self.kinds = {"guide": loginwizard.BROKEN}
        code, out, _ = self.up()
        self.assertEqual(code, 2)
        self.assertIn("no: agent guide: cannot be checked:", out)

    def test_PLANTED_FAULT_an_agents_file_with_no_agent_is_64(self):
        (self.root / "agents.yaml").write_text("agents: []\n")
        code, out, err = self.up()
        self.assertEqual(code, 64)
        self.assertIn("agents.yaml has 1 problem", err)

    def test_PLANTED_FAULT_a_missing_guidance_yaml_is_ask_me_first(self):
        (self.root / "guidance.yaml").unlink()
        code, out, _ = self.up()
        self.assertEqual(code, 3)
        self.assertIn("ask: guidance:", out)

    def test_PLANTED_FAULT_a_folder_that_is_not_a_git_repo_is_exit_2(self):
        import shutil
        shutil.rmtree(self.root / ".git")
        code, out, _ = self.up()
        self.assertEqual(code, 2)
        self.assertIn("no: git: this folder is not a git repo", out)

    def test_PLANTED_FAULT_a_repo_without_main_is_exit_2(self):
        git(self.root, "branch", "-m", "main", "trunk")
        code, out, _ = self.up()
        self.assertEqual(code, 2)
        self.assertIn("no: git: this git repo has no main branch", out)

    def test_PLANTED_FAULT_a_missing_rules_yaml_is_ask_me_first(self):
        (self.root / "rules.yaml").unlink()
        code, out, _ = self.up()
        self.assertEqual(code, 3)
        self.assertIn("ask: root:", out)

    def test_PLANTED_FAULT_a_goal_folder_that_cannot_be_read_is_exit_2(self):
        (self.root / ".umwayi").mkdir()
        (self.root / ".umwayi" / "goals").write_text("not a folder")
        code, out, _ = self.up()
        self.assertEqual(code, 2)
        self.assertIn("no: goals:", out)

    def test_PLANTED_FAULT_two_problems_give_2_over_3(self):
        kill.turn_on(self.root, TODAY, "test")
        self.kinds = {"builder": loginwizard.NEEDS}
        self.assertEqual(self.up()[0], 2)


class UsageTests(Base):
    def test_PLANTED_FAULT_a_bad_or_missing_config_is_64_and_stops_at_once(self):
        for name, text in (("umwayi.json", None), ("umwayi.json", "{not json"), ("agents.yaml", None),
                           ("agents.yaml", "agents:\n  - name: x\n"), ("guidance.yaml", "version: 2\n")):
            with self.subTest(file=name, text=text):
                saved = (self.root / name).read_bytes()
                if text is None:
                    (self.root / name).unlink()
                else:
                    (self.root / name).write_text(text)
                code, out, err = self.up()
                self.assertEqual(code, 64, out + err)
                self.assertIn("umwayi: error:", err)
                self.assertNotIn("Ready.", out)
                (self.root / name).write_bytes(saved)

    def test_PLANTED_FAULT_the_goal_options_go_together(self):
        for argv in (("--goal", "Build the hello page with care."), ("--guide", "guide"), ("--plan-budget-uu", "5"),
                     ("--goal", "Build the hello page with care.", "--guide", "guide"),
                     ("--guide-model", "sonnet"), ("--plan-budget-uu", "x"), ("--bogus",)):
            with self.subTest(argv=argv):
                self.assertEqual(self.up(*argv)[0], 64)

    def test_the_exit_code_is_only_0_2_3_or_64(self):
        codes = {self.up()[0], self.up("--bogus")[0]}
        kill.turn_on(self.root, TODAY, "t")
        codes.add(self.up()[0])
        self.kinds = {"guide": loginwizard.NEEDS}
        codes.add(self.up()[0])
        self.assertEqual(codes, {0, 2, 3, 64})


class GoalStartTests(Base):
    GOAL = ("--goal", "Build the hello page with its test.", "--guide", "guide", "--plan-budget-uu", "5")

    def test_with_every_check_ok_it_calls_goal_start_once_with_the_typed_arguments(self):
        calls = []

        def spy(ctx, args):
            calls.append(args)
            return 0

        code, out, _ = self.up(*self.GOAL, "--guide-effort", "high", start=spy)
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        a = calls[0]
        self.assertEqual((a.goal_command, a.text, a.guide, a.plan_budget_uu, a.guide_model, a.guide_effort),
                         ("start", "Build the hello page with its test.", "guide", 5, None, "high"))
        self.assertIn("umwayi up runs umwayi goal start now", out)

    def test_the_code_of_goal_start_is_the_code_of_up(self):
        for rc in (0, 2, 3, 64):
            with self.subTest(rc=rc):
                self.assertEqual(self.up(*self.GOAL, start=lambda ctx, args, rc=rc: rc)[0], rc)

    def test_PLANTED_FAULT_a_check_that_is_not_ok_means_goal_start_is_never_called(self):
        def never(ctx, args):
            raise AssertionError("goal start was called")

        for plant, want in ((lambda: kill.turn_on(self.root, TODAY, "t"), 3),
                            (lambda: self.kinds.update({"guide": loginwizard.NEEDS}), 2),
                            (lambda: (self.root / "guidance.yaml").unlink(), 3)):
            with self.subTest(want=want):
                self.setUp()
                plant()
                before = tree(self.root)
                code, out, err = self.up(*self.GOAL, start=never)
                self.assertEqual(code, want)
                self.assertIn(up.NOT_STARTED, err)
                self.assertEqual(tree(self.root), before)

    def test_goal_start_is_the_real_command_and_its_own_checks_still_run(self):
        # no spy: the real goal start runs its own guard and kill switch check first. The switch is turned on between
        # up's checks and goal start, so goal start's own check is what stops it, and the exit is 3 with nothing made.
        real_kill = up.kill.state
        seen = {"n": 0}

        def flip(root):
            seen["n"] += 1
            if seen["n"] == 1:
                return real_kill(root)
            return kill.ON

        with mock.patch("umwayi.up.kill.state", side_effect=flip), mock.patch("umwayi.goal.kill.state", return_value=kill.ON):
            code, out, err = self.up(*self.GOAL)
        self.assertEqual(code, 3, out + err)
        self.assertFalse((self.root / ".umwayi" / "goals").exists())


class SourceTests(unittest.TestCase):
    def test_the_module_has_no_network_shell_install_merge_sign_in_server_or_write(self):
        text = (REPO / "umwayi" / "up.py").read_text(encoding="utf-8")
        code = "\n".join(l for l in text.split("\n") if not l.lstrip().startswith("#"))
        body = code.split('"""', 2)[2]  # without the module docstring
        for word in ("socket", "urllib", "http", "subprocess", "shell=True", "os.system", "Popen", "pip", "npm", "merge",
                     "login_agent", "serve.run", "approve", "kill.turn_off", "write_text", "write_bytes", "open(",
                     "logbook.append", "atomic_write", "unlink", "rmtree"):
            self.assertNotIn(word, body, word)
        self.assertNotIn("\u2014", text)

    def test_up_calls_only_the_existing_functions_it_names(self):
        text = (REPO / "umwayi" / "up.py").read_text(encoding="utf-8")
        calls = set(re.findall(r"\b(agents|goalgit|guidance|kill|logbook|loginwizard|goal)\.([a-z_]+)\(", text))
        self.assertEqual(calls, {("agents", "load"), ("goalgit", "is_repo"), ("goalgit", "has_main"), ("guidance", "guard"),
                                 ("kill", "state"), ("kill", "stopped"), ("kill", "reason"), ("logbook", "verify"),
                                 ("loginwizard", "status_of"), ("goal", "make_ctx"), ("goal", "status_lines"),
                                 ("goal", "dispatch")})


class RealProcessTests(Base):
    def test_a_real_child_with_no_agent_program_says_the_agents_cannot_be_checked(self):
        env = {**os.environ, "PYTHONPATH": str(REPO), "PATH": "/usr/bin:/bin", **GIT_ENV}
        before = tree(self.root)
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "up"], capture_output=True, text=True,
                           env=env, timeout=120)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("no: agent guide: cannot be checked:", r.stdout)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(tree(self.root), before)


if __name__ == "__main__":
    unittest.main()
