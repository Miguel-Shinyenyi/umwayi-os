"""W78 step 3 (W41 C1) for `umwayi agent run` and the cli chat: a watched file that changed while the agent ran.

The goal supervisor has its own check per role (tests/goal/test_guard_files.py). A plain `agent run` reads the watched files
(umwayi/watched.py) after the start entry and again after the agent ended: a change is one logbook entry, one queue item, and
exit 2 even when the run itself ended well. Nothing is undone, and the names are the fixed ones of the list.
"""
import subprocess
import sys

from tests.agents.support import RULES, AgentCase


class GuardRunTests(AgentCase):
    def setUp(self):
        super().setUp()
        self.fake("claude")
        self.write_rules(RULES.replace("agent: [reviewer, slow, stubborn, quick]", "agent: [reviewer]"))
        self.write_agents("agents:\n  - name: reviewer\n    platform: claude-code\n    command: claude\n    workdir: {work}\n")
        self.roomy_budget()

    def run_agent(self, *steps):
        extra = self.script(*steps, {"do": "exit", "code": 0})
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "run", "reviewer",
                            "--prompt", "hello"], capture_output=True, text=True, timeout=120, env=self.env(extra),
                           cwd=str(self.tmp))
        self.assertIn(r.returncode, (0, 2, 3, 64), r.stdout + r.stderr)
        return r

    def write(self, name, text="# changed by the agent\n"):
        return {"do": "write", "path": str(self.root / name), "text": text}

    def log(self):
        return (self.root / "LOGBOOK.md").read_text(encoding="utf-8")

    def test_a_change_to_a_watched_file_is_exit_2_with_one_entry_and_one_queue_item(self):
        r = self.run_agent(self.write("tools/tool.py"))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("A guard file changed during the run: tools. Nothing was undone.", r.stdout)
        self.assertEqual(self.log().count("Guard files changed during the run of agent reviewer: tools"), 1)
        rows = (self.root / "queue.md").read_text(encoding="utf-8")
        self.assertIn("Guard files changed during a run of agent reviewer", rows)
        self.assertTrue((self.root / "tools" / "tool.py").exists())  # nothing was undone

    def test_each_watched_name_is_a_finding(self):
        for name in ("units.yaml", "guidance.yaml", "autonomy.yaml", ".umwayi/enforcement.yaml", ".kiro/steering/umwayi",
                     "tools/x.py"):
            with self.subTest(name=name):
                self.setUp()
                self.write_rules(RULES.replace("agent: [reviewer, slow, stubborn, quick]", "agent: [reviewer]"))
                if name == "units.yaml":
                    continue  # a bad units.yaml refuses the next start by itself; it is covered by the unit tests
                r = self.run_agent(self.write(name))
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                shown = "tools" if name.startswith("tools/") else name
                self.assertIn(f"Guard files changed during the run of agent reviewer: {shown}", self.log())

    def test_a_run_that_changes_nothing_is_not_a_finding(self):
        r = self.run_agent({"do": "sleep", "s": 0})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("Guard files changed", self.log())

    def test_a_file_that_is_not_watched_is_not_a_finding(self):
        r = self.run_agent(self.write("README.md"), self.write("docs/status-log.md"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_second_change_with_the_first_item_still_open_adds_no_second_item(self):
        self.run_agent(self.write("tools/a.py", "a\n"))
        self.run_agent(self.write("tools/a.py", "b\n"))
        rows = (self.root / "queue.md").read_text(encoding="utf-8")
        self.assertEqual(rows.count("Guard files changed during a run of agent reviewer"), 1)

    def test_the_names_never_hold_a_path_or_a_word_of_the_agent(self):
        r = self.run_agent(self.write("tools/SECRET-NAME-never-shown.py"))
        self.assertNotIn("SECRET-NAME-never-shown", r.stdout + self.log() + (self.root / "queue.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    import unittest
    unittest.main()
