"""W9.13: an OpenCode agent as a goal builder, tester or guide (docs/opencode-goal-helper-design.md, R9).

`agent run` of an OpenCode agent is tested in tests/agents/test_agents_opencode_run.py. Here is the goal side: what the
owner's commands accept for such a role. An OpenCode role takes no effort from umwayi and no model of its own: the model
is the agent's, from agents.yaml. A `--model` that differs, or any effort, is refused. The commands of umwayi never need an
OpenCode agent to be installed here: the gate is the test's own.
"""

import unittest

from tests.goal import cmdsupport as cs
from umwayi import goalpacket as gp
from umwayi import goalrun as gr
from umwayi import goalstate as gs

OC_AGENTS = """  - name: oc-build
    platform: opencode
    command: opencode
    workdir: {work}
    timeout_minutes: 90
    provider: ollama
    model: ollama/m
  - name: oc-test
    platform: opencode
    command: opencode
    workdir: {work}
    provider: ollama
    model: ollama/t
  - name: oc-guide
    platform: opencode
    command: opencode
    workdir: {work}
    provider: ollama
    model: ollama/g
"""


class OpenCodeRoleCase(cs.CmdCase):
    def setUp(self):
        super().setUp()
        path = self.root / "agents.yaml"
        path.write_text(path.read_text(encoding="utf-8").rstrip("\n") + "\n" + OC_AGENTS.replace("{work}", str(self.work)),
                        encoding="utf-8")

    def packet(self, goal, task="T-01"):
        return gp.packet_from_dict(gs.read_task(self.root, goal, task)["packet"])


class BuilderTests(OpenCodeRoleCase):
    def test_an_opencode_builder_is_approved_with_no_model_and_no_effort_and_runs_the_agents_own_model(self):
        goal = self.g_start()
        self.assertEqual(self.g_approve(goal, builder="oc-build", model=None, effort=None), 0, self.err)
        p = self.packet(goal)
        self.assertEqual((p.model, p.effort), ("ollama/m", ""))

    def test_the_agents_own_model_may_be_given(self):
        goal = self.g_start()
        self.assertEqual(self.g_approve(goal, builder="oc-build", model="ollama/m", effort=None), 0, self.err)

    def test_another_model_or_any_effort_is_refused_and_nothing_changes(self):
        goal = self.g_start()
        before = gs.read_goal(self.root, goal)
        for kw in (dict(model="ollama/other", effort=None), dict(model=None, effort="high"), dict(model="ollama/m", effort="medium")):
            with self.subTest(**kw):
                self.err.clear()
                self.assertEqual(self.g_approve(goal, builder="oc-build", **kw), 2, self.err)
                self.assertFalse(gs.read_goal(self.root, goal)["approved"])
        self.assertEqual(gs.read_goal(self.root, goal)["builder"], before["builder"])

    def test_planted_fault_a_claude_builder_still_needs_a_model_and_an_effort(self):
        goal = self.g_start()
        self.assertEqual(self.g_approve(goal, model=None, effort=None), 64, self.err)  # missing: a usage error, as argparse was
        self.assertEqual(self.g_approve(goal, model="", effort=""), 2, self.err)  # blank: refused, as before
        self.assertEqual(self.g_approve(goal, model="sonnet", effort=""), 2, self.err)
        self.assertEqual(self.g_approve(goal), 0, self.err)

    def test_the_supervisor_gives_an_opencode_run_no_model_and_no_effort_argument(self):
        argv = gr.child_argv("oc-build", 30, "/w", gr.options_for("opencode", "ollama/m", ""))
        self.assertNotIn("--model", argv)
        self.assertNotIn("--effort", argv)
        self.assertEqual(gr.options_for("claude-code", "sonnet", "high"), ["--model", "sonnet", "--effort", "high"])

    def test_a_packet_with_a_blank_effort_is_valid_only_through_fill_packet(self):
        packet = gp.parse_plan(__import__("json").dumps({"tasks": [{
            "goal": "Do the numbered piece of work number 1 now.", "context": [],
            "checks": ["Check number 1 of the piece can be answered pass or fail."], "size": 40, "files": ["x.py"]}]}).encode(),
            file_size=lambda p: 1)[0]
        self.assertEqual(gp.fill_packet(packet, "G-0001", "ollama/m", "", 30, 500).effort, "")
        with self.assertRaises(ValueError):
            gp.fill_packet(packet, "G-0001", "ollama/m", "extreme", 30, 500)


class OtherRolesTests(OpenCodeRoleCase):
    def test_an_opencode_tester_is_approved_and_takes_no_model(self):
        goal = self.g_start()
        self.assertEqual(self.g_approve(goal, tester="oc-test"), 0, self.err)
        self.assertEqual(gs.read_goal(self.root, goal)["tester"], "oc-test")
        goal = self.g_start()
        self.assertEqual(self.g_approve(goal, tester="oc-test", tester_model="ollama/t"), 2, self.err)

    def test_an_opencode_guide_plans_a_goal(self):
        code = self.call("start", cs.GOAL_TEXT, "oc-guide", 20, scripts=[{"steps": [cs.plan_line()], "spend": 4}])
        self.assertEqual(code, 0, self.err)
        goal = gs.list_goals(self.root)[-1]
        self.assertEqual(gs.read_goal(self.root, goal)["guide"], "oc-guide")
        self.assertEqual(self.g_approve(goal, tester="oc-test"), 0, self.err)

    def test_show_makes_a_proposal_for_an_opencode_builder_with_no_model_and_effort(self):
        goal = self.g_start()
        self.out.clear()
        self.assertEqual(self.call("show", goal, builder="oc-build", tester="oc-test"), 0, self.err)
        text = "\n".join(self.out)
        self.assertIn("Proposed", text)
        self.assertIn("enforcement for builder oc-build", text)


if __name__ == "__main__":
    unittest.main()
