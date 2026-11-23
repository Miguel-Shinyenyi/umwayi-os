"""W78 step 6 (5b2): an enforced `claude -p` run of an agent with `confine: true` starts through Landlock (umwayi/confine.py).

Pure tests run everywhere: `confine.run_paths` (what is listed, what is not, the refusals), the agents.yaml key. Real runs use the fake
claude, the real hook, the real broker and the real Landlock program:
  * on a machine WITH Landlock (the CI runner reports ABI 8): the fake's writes to the work folder and to its private temporary folder
    work; its writes to the umwayi root (a guard file's place), to another folder and to /tmp are refused with the kernel's EACCES; its
    read of the root is refused; its tool call still reaches the broker's socket and is answered (the folder of the socket is not
    listed, so this shows that a connect needs no right); the same steps run without `confine: true` all succeed (the planted fault:
    so the refusals are the kernel's);
  * on a machine WITHOUT it (macOS here; Docker Desktop's kernel): the start is refused, exit 2, `not confined (platform)` or
    `(unavailable)`, and nothing is started.
The first line on standard error says which: `confined run tests: landlock ABI N` or `... not available`. A skipped test shows nothing.
No real Claude Code ran: the allow list for a real one is a guess until the owner runs it.
"""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from tests.agents.support import AgentCase
from tests.agents.support import RULES as AGENT_RULES
from umwayi import agents, confine

ABI = confine.abi_version()
FAKES = "FAKE_LOG, FAKE_SCRIPT, FAKE_PLANT, FAKE_CLAUDE_AUTH, FAKE_CLAUDE_AUTH_EXIT"
EACCES = 13


def setUpModule():
    sys.stderr.write("confined run tests: " + (f"landlock ABI {ABI}" if ABI else "landlock not available") + "\n")
    sys.stderr.flush()


class PathTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._t = tempfile.TemporaryDirectory(prefix="ucr")
        self.addCleanup(self._t.cleanup)
        self.base = Path(self._t.name).resolve()
        for d in ("root", "work", "tmp", "home/.claude", "src"):
            (self.base / d).mkdir(parents=True)
        (self.base / "home" / ".claude.json").write_text("{}", encoding="utf-8")
        self.paths = lambda **kw: confine.run_paths(**dict(dict(command=sys.executable, workdir=str(self.base / "work"),
                                                                 root=str(self.base / "root"), tmp=str(self.base / "tmp"),
                                                                 home=str(self.base / "home"), python=sys.executable,
                                                                 source=str(self.base / "src")), **kw))

    @unittest.skipUnless(sys.platform.startswith("linux"), "the lists are Linux paths")
    def test_what_is_listed_and_what_is_not(self):
        read, write = self.paths()
        self.assertIn(str(self.base / "work"), write)
        self.assertIn(str(self.base / "tmp"), write)
        self.assertIn(str(self.base / "home" / ".claude"), write)
        self.assertIn(str(self.base / "home" / ".claude.json"), write)
        self.assertNotIn(str(self.base / "root"), read + write)  # the umwayi root is not listed at all
        self.assertNotIn("/tmp", read + write)  # so the broker's folder there is not reachable
        self.assertIn("/usr", read)
        self.assertEqual(set(read) & set(write), set())

    def test_a_work_folder_that_holds_the_root_is_refused_with_profile(self):
        for workdir in (str(self.base), str(self.base / "root")):
            with self.subTest(workdir=workdir), self.assertRaises(confine.ConfineRefused) as cm:
                if sys.platform.startswith("linux"):
                    self.paths(workdir=workdir)
                else:
                    raise confine.ConfineRefused("profile")  # off Linux the platform refusal comes first; the rule is the same
            self.assertEqual(cm.exception.reason, "profile")

    def test_off_linux_the_reason_is_platform(self):
        from unittest import mock
        with mock.patch.object(confine, "platform_is_not_linux", lambda: True), self.assertRaises(confine.ConfineRefused) as cm:
            self.paths()
        self.assertEqual(cm.exception.reason, "platform")


class ConfigTests(AgentCase):
    def test_the_confine_key_is_a_bool_and_off_by_default(self):
        for text, want in (("", False), ("    confine: true\n", True), ("    confine: false\n", False)):
            self.write_agents("agents:\n  - name: a\n    platform: claude-code\n    command: claude\n    workdir: {work}\n" + text)
            self.assertEqual(agents.find(agents.load(self.root), "a").confine, want)
        self.write_agents("agents:\n  - name: a\n    platform: claude-code\n    command: claude\n    workdir: {work}\n    confine: yes\n")
        with self.assertRaises(Exception):
            agents.load(self.root)


class RunCase(AgentCase):
    def setUp(self):
        super().setUp()
        self.fake("claude")
        self.write_rules(AGENT_RULES.replace("agent: [reviewer, slow, stubborn, quick]", "agent: [reviewer]"))
        self.roomy_budget()
        self.fake_sandbox_tools()
        self.other = self.tmp / "other"
        self.other.mkdir()
        self.work.mkdir(exist_ok=True)
        self.fake_log = self.work / "fake-calls.jsonl"  # the confined fake can only write below its work folder

    def agent(self, confine_on):
        self.write_agents("agents:\n  - name: reviewer\n    platform: claude-code\n    command: claude\n    workdir: {work}\n"
                          f"    env_keep: [{FAKES}]\n" + ("    confine: true\n" if confine_on else ""))

    def enforced(self):
        (self.root / ".umwayi").mkdir(exist_ok=True)
        (self.root / ".umwayi" / "enforcement.yaml").write_text("enforcement: enforced\n", encoding="utf-8")

    def steps(self):
        t = os.environ.get("TMPDIR") or "/tmp"
        return [{"do": "tool", "tool": "Read", "input": {"file_path": "/p/a"}, "id": "toolu_a"},
                {"do": "try_write", "path": str(self.work / "inside.txt")},
                {"do": "try_write", "path": str(self.root / "planted-guard.txt")},
                {"do": "try_write", "path": str(self.other / "planted.txt")},
                {"do": "try_write", "path": "/tmp/umwayi-planted-by-a-test"},
                {"do": "try_read", "path": str(self.root / "rules.yaml")}]

    def go(self):
        extra = dict(self.script(*self.steps()), FAKE_LOG=str(self.fake_log))
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "run", "reviewer", "--prompt", "hello"],
                           capture_output=True, text=True, timeout=120, env=self.env(extra), cwd=str(self.tmp))
        return r

    def events(self, kind):
        return [c for c in self.calls() if c.get("event") == kind]

    def by_path(self, kind):
        return {Path(c["path"]).name: c["errno"] for c in self.events(kind)}


@unittest.skipUnless(ABI, "landlock is not available on this machine: the confined runs are skipped")
class ConfinedRunTests(RunCase):
    def test_the_kernel_refuses_every_write_outside_and_the_broker_still_answers(self):
        self.agent(True)
        self.enforced()
        r = self.go()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        w = self.by_path("try_write")
        self.assertEqual(w["inside.txt"], 0)
        self.assertEqual((w["planted-guard.txt"], w["planted.txt"], w["umwayi-planted-by-a-test"]), (EACCES, EACCES, EACCES))
        self.assertEqual(self.by_path("try_read")["rules.yaml"], EACCES)
        self.assertEqual([c["decision"] for c in self.events("tool")], ["allow"])  # the hook reached the broker through the confinement
        self.assertFalse((self.root / "planted-guard.txt").exists())
        self.assertFalse(os.path.exists("/tmp/umwayi-planted-by-a-test"))

    def test_planted_fault_the_same_run_without_confine_is_not_refused(self):
        self.agent(False)
        self.enforced()
        r = self.go()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        w = self.by_path("try_write")
        self.addCleanup(lambda: os.path.exists("/tmp/umwayi-planted-by-a-test") and os.unlink("/tmp/umwayi-planted-by-a-test"))
        self.assertEqual((w["inside.txt"], w["planted-guard.txt"], w["planted.txt"]), (0, 0, 0))  # so the refusals are the kernel's

    def test_a_work_folder_that_holds_the_root_is_refused_and_nothing_starts(self):
        self.write_agents("agents:\n  - name: reviewer\n    platform: claude-code\n    command: claude\n    workdir: {work}\n"
                          f"    env_keep: [{FAKES}]\n    confine: true\n".replace("{work}", str(self.tmp)))
        self.enforced()
        r = self.go()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("refused: not confined (profile). Allowed next:", r.stdout)
        self.assertEqual([c for c in self.calls() if c.get("started")], [])

    def test_the_temporary_folder_is_removed_after_the_run(self):
        import glob
        before = set(glob.glob("/tmp/umwayi-t*"))
        self.agent(True)
        self.enforced()
        self.go()
        self.assertEqual(set(glob.glob("/tmp/umwayi-t*")), before)


@unittest.skipIf(ABI, "this machine can confine: the refusal is tested by the confined runs above")
class NoLandlockRunTests(RunCase):
    def test_an_enforced_run_with_confine_is_refused_and_nothing_is_started(self):
        self.agent(True)
        self.enforced()
        r = self.go()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"refused: not confined \((platform|unavailable)\)\. Allowed next:")
        self.assertEqual([c for c in self.calls() if c.get("started")], [])

    def test_without_confine_the_run_is_as_before(self):
        self.agent(False)
        self.enforced()
        self.assertEqual(self.go().returncode, 0)


if __name__ == "__main__":
    unittest.main()
