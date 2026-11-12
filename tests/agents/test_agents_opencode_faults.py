"""Layer 10 part 8, task 10.50: tests for the planted faults that the earlier tests did not catch.

The fault runs of 10.48 and 10.49 left three survivors: the mode check of the private canary folder, the last
`_track()` before a clean exit, and the line that turns a check which could not be logged into a reject. FolderTests,
LastTrackTests and NotLoggedTests catch them (faults S1, S2 and S3 of `tests/agents/opencode_mutants.py`).

The fault run of 10.50 itself left more: a second managed folder, a dangling link at the managed plist, a workdir
reached through a link, a global config folder that cannot be examined, a plugin folder that cannot be listed, a
session that names no model, and three guards of the permission answer. The other classes below catch those.
"""

import json
import os
import tempfile
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

from umwayi import acp, agents
from umwayi.errors import UmwayiError

from tests.agents.support import SECRET
from tests.agents.test_agents_opencode_chat import ChatCase
from tests.agents.test_agents_opencode_gate import GateCase
from tests.agents.test_agents_opencode_turns import TurnCase, tool

RULES = """rules:
  - id: perm-read
    title: a request to read is Yes
    text: Allowed.
    verdict: yes
    matchers:
      type: acp_permission
      kind: read
"""


def opencode_agent(work: Path) -> agents.Agent:
    return agents.Agent("o", "opencode", "opencode", "acp", str(work), provider="ollama", model="ollama/m")


class FolderTests(unittest.TestCase):
    """`_prepare_canary` checks the folder it was given. `tempfile.mkdtemp` always makes mode 0700, so a chat run can
    never reach that check; the test replaces the folder maker, which is what the check guards against."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="umwayi-folder-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.root, self.work = self.tmp / "root", self.tmp / "work"
        self.root.mkdir()
        self.work.mkdir()

    def prepare(self, mode):
        folder = Path(tempfile.mkdtemp(prefix="umwayi-canary-test-", dir=self.tmp))
        os.chmod(folder, mode)
        run = agents._Run(self.root, opencode_agent(self.work), None, lambda: "2026-11-12", agents.CHAT)
        with ExitStack() as stack, mock.patch.object(agents, "_canary_folder", return_value=str(folder)):
            problem = run._prepare_canary(stack)
        return problem, run

    def test_a_private_folder_is_accepted(self):
        problem, run = self.prepare(0o700)
        self.assertIsNone(problem)
        self.assertIsNotNone(run.canary)

    def test_a_folder_that_others_can_read_is_refused(self):
        for mode in (0o755, 0o750, 0o701, 0o770, 0o777):
            with self.subTest(mode=oct(mode)):
                problem, run = self.prepare(mode)
                self.assertEqual(problem, "the private canary folder is not a private folder outside the root and the workdir")
                self.assertIsNone(run.canary)
                self.assertIsNone(run.opencode_config)  # nothing was made for a start that does not happen

    def test_the_mode_is_what_is_checked(self):
        # a stricter mode than 0700 is not 0700 either: the folder is the one tempfile makes, or it is refused
        problem, _ = self.prepare(0o500)
        self.assertIsNotNone(problem)


class NotLoggedTests(unittest.TestCase):
    """A permission request is a reject when its check could not be written to the logbook. The real `check_and_log`
    turns a Yes into Ask me first when it cannot log; the line under test makes the answer to the agent a reject,
    so the owner is not even asked about a call that has no entry."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="umwayi-notlogged-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve() / "root"
        self.root.mkdir()
        (self.root / "rules.yaml").write_text(RULES, encoding="utf-8")
        work = self.root.parent / "work"
        work.mkdir()
        self.run_ = agents._Run(self.root, opencode_agent(work), None, lambda: "2026-11-12", agents.CHAT)
        self.read = {"kind": "read", "name": "read"}

    def test_a_logged_yes_is_allowed(self):  # the control: the rule says Yes and the entry is written
        self.assertEqual(self.run_._permission(self.read), acp.ALLOW)

    def test_a_check_that_cannot_be_logged_is_a_reject(self):
        with mock.patch("umwayi.rules.logbook.append", side_effect=UmwayiError("planted: this write fails")):
            self.assertEqual(self.run_._permission(self.read), acp.REJECT)

    def test_an_ask_me_first_that_cannot_be_logged_is_a_reject_too(self):
        (self.root / "rules.yaml").write_text(RULES.replace("verdict: yes", "verdict: ask"), encoding="utf-8")
        self.assertEqual(self.run_._permission(self.read), acp.ASK)  # the control: logged, the owner is asked
        with mock.patch("umwayi.rules.logbook.append", side_effect=UmwayiError("planted: this write fails")):
            self.assertEqual(self.run_._permission(self.read), acp.REJECT)


class PermissionGuardTests(unittest.TestCase):
    """Run._permission answers No (a reject) while the kill switch is on, and for any error in the check. The watcher
    ends a chat on the kill switch at its next pass, once a second; these two lines are what answers a request that
    arrives between two passes, so the integration tests (which end at the watcher) cannot reach them."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="umwayi-guard-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve() / "root"
        self.root.mkdir()
        (self.root / "rules.yaml").write_text(RULES, encoding="utf-8")
        work = self.root.parent / "work"
        work.mkdir()
        self.run_ = agents._Run(self.root, opencode_agent(work), None, lambda: "2026-11-12", agents.CHAT)
        self.read = {"kind": "read", "name": "read"}

    def test_the_kill_switch_makes_every_request_a_reject_whatever_the_rules_say(self):
        self.assertEqual(self.run_._permission(self.read), acp.ALLOW)  # the control: the rule says Yes
        (self.root / ".umwayi").mkdir(exist_ok=True)
        (self.root / ".umwayi" / "KILL").write_text("", encoding="utf-8")
        self.assertEqual(self.run_._permission(self.read), acp.REJECT)

    def test_an_error_while_asking_the_rules_is_a_reject(self):
        with mock.patch("umwayi.rules.check_and_log", side_effect=RuntimeError("planted")):
            self.assertEqual(self.run_._permission(self.read), acp.REJECT)


class CallbackCrashTests(TurnCase):
    """A crash in umwayi's permission callback, outside its own checks, is a reject in acp.py: never an allow and never
    a question to the owner. `permission_action` is made to crash in the umwayi process only (the fake and its hook
    never get the fault)."""

    def test_a_crash_in_the_permission_callback_is_a_reject(self):
        self.spec({"turns": [[tool("read", path="/etc/hostname"), {"chunk": "done"}]]})
        r = self.run_chat("go\n:quit\n", fault="umwayi.agents:permission_action:crash",
                          extra={"UMWAYI_FAULT_TEXT": SECRET})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.requests(), ["read"])  # the first gate let it go on, so a request was made
        self.assertEqual(self.answers(), ["reject"])
        self.assertNotIn("Allow once?", r.stdout)
        self.assertNotIn(SECRET, r.stdout + r.stderr + self.log_text())


class NoModelTests(ChatCase):
    """A session/new answer that names no model is refused like another model: the model compare is the only place a
    silent fallback is caught (OC10), and an answer with no model to compare is no better than a wrong one."""

    def test_an_answer_that_names_no_model_is_refused_before_the_first_prompt(self):
        for shape in ("missing", "null", "number", "renamed", "no_options"):
            with self.subTest(shape=shape):
                self.fake_log.unlink(missing_ok=True)
                self.spec({"model_option": shape})
                r = self.run_chat(f"hello {SECRET}\n:quit\n")
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("The agent reported another model than ollama/m. The chat ended (exit 2).", r.stdout)
                self.assertNotIn("session/prompt", self.methods())
                self.assert_nothing_left()

    def test_the_control_an_answer_that_names_the_model_is_accepted(self):
        self.spec({"model_option": "none-of-the-above"})
        r = self.run_chat("hello\n:quit\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class GateGapTests(GateCase):
    """Gate check cases that the first tests of 10.46 did not reach."""

    def managed_env(self, *dirs):
        return {"UMWAYI_TEST_OPENCODE_MANAGED": json.dumps({"dirs": [str(d) for d in dirs],
                                                            "plist_root": str(self.plist_root)})}

    def test_the_second_managed_folder_counts_too(self):
        first, second = self.tmp / "m1" / "opencode", self.tmp / "m2" / "opencode"
        second.mkdir(parents=True)
        self.assert_refused("managed config", str(second), extra=self.managed_env(first, second))

    def test_the_first_managed_folder_counts_too(self):
        first, second = self.tmp / "m1" / "opencode", self.tmp / "m2" / "opencode"
        first.mkdir(parents=True)
        self.assert_refused("managed config", str(first), extra=self.managed_env(first, second))

    def test_neither_managed_folder_existing_passes(self):
        self.assert_passes(extra=self.managed_env(self.tmp / "m1" / "opencode", self.tmp / "m2" / "opencode"))

    def test_a_dangling_link_at_the_managed_plist_counts(self):
        self.plist_root.mkdir()
        (self.plist_root / "ai.opencode.managed.plist").symlink_to(self.tmp / "nowhere.plist")
        self.assert_refused("managed config", "ai.opencode.managed.plist")

    def test_a_dangling_link_at_the_plist_in_a_user_folder_counts(self):
        (self.plist_root / "alice").mkdir(parents=True)
        (self.plist_root / "alice" / "ai.opencode.managed.plist").symlink_to(self.tmp / "nowhere.plist")
        self.assert_refused("managed config", "ai.opencode.managed.plist")

    def test_a_workdir_reached_through_a_link_is_walked_by_the_path_as_given_too(self):
        # the config is above the link, not above the folder the link points to: only the path as given finds it
        real = self.tmp / "elsewhere" / "deeper" / "work"
        real.mkdir(parents=True)
        given = self.tmp / "given"
        given.mkdir()
        link = given / "link-to-work"
        link.symlink_to(real)
        (given / "opencode.json").write_text("{}", encoding="utf-8")
        self.write_agent(workdir=link)
        r = self.check()
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn(str(given / "opencode.json"), self.lines_of(r)["other config"][1])

    def test_a_global_config_folder_that_cannot_be_examined_is_refused(self):
        # ~/.config/opencode is a file, so looking for opencode.json inside it fails with "not a directory"
        self.xdg.mkdir(parents=True)
        (self.xdg / "opencode").write_text("x", encoding="utf-8")
        self.assert_refused("other config", "cannot be read")

    def test_a_plugin_folder_that_cannot_be_listed_is_refused(self):
        # a folder with the execute bit and not the read bit reaches the files but cannot be listed; as root there is
        # no such folder, so the listing itself fails here
        self.assertEqual(agents._opencode_files(self.src)[0], True)  # the control
        with mock.patch("os.listdir", side_effect=PermissionError(13, "Permission denied")):
            ok, detail = agents._opencode_files(self.src)
        self.assertFalse(ok)
        self.assertIn("cannot be listed", detail)


class LastTrackTests(ChatCase):
    """The stop of an OpenCode chat is the 7b stop (design.md part 8, items 8 and "the kill switch turns on"): the
    agent's process group and every descendant umwayi has seen, because a background command can leave the group. This
    was found by the fault run of 10.50: stop_agent used the group alone for OpenCode, so a command in a session of
    its own outlived the chat.

    A command the agent starts and the chat ends in the same moment. The watcher looks at the agent's descendants
    once a second; here the whole chat is over in less than that, so only the look that umwayi takes right before the
    agent's clean exit can see the command. Without that look the command lives on after umwayi has exited."""

    def test_a_background_command_started_in_the_last_turn_is_stopped_after_a_clean_exit(self):
        self.spec({"turns": [[{"spawn_setsid": True}, {"chunk": "started it"}]]})
        p = self.start_chat()
        p.stdin.write("go\n:quit\n")
        p.stdin.close()
        code, out, err = self.finish(p, timeout=90)  # the agents alive at the moment umwayi exits are noted here
        self.assertEqual(code, 0, out + err)
        self.assertIn("started it", out)
        spawned = [c for c in self.calls() if c.get("event") == "spawn"]
        self.assertEqual(len(spawned), 1)
        self.assert_agent_gone()
        self.assert_nothing_left()

    def test_the_kill_switch_stops_a_background_command_that_left_the_group(self):
        self.spec({"turns": [[{"spawn_setsid": True}, {"wait_cancel": True}]]})
        p = self.start_chat()
        p.stdin.write("go\n")
        p.stdin.flush()
        self.wait_for(lambda c: c.get("event") == "spawn", "the background command")
        time.sleep(1.5)  # a watcher pass or two
        self.kill_on()
        code, out, err = self.finish(p, timeout=90)
        self.assertEqual(code, 3, out + err)
        self.assert_agent_gone()
        self.assert_nothing_left()


if __name__ == "__main__":
    unittest.main()
