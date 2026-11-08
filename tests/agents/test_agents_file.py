"""Layer 10 part 1: agents.yaml, `umwayi agent validate` and `umwayi agent list` (tasks.md 10.1 to 10.3).

Every test runs `python -m umwayi ... agent ...` as a real child process.
"""

import os
import re
import unittest

from tests.agents.support import CLAUDE_AGENT, KIRO_AGENT, REPO, SECRET, AgentCase

GOOD_SHAPES = {
    "claude minimal": """agents:
  - name: a
    platform: claude-code
    command: claude
    workdir: {work}
""",
    "claude all fields": """agents:
  - name: reviewer-2
    platform: claude-code
    command: claude
    transport: cli
    workdir: {work}
    max_turns: 200
    timeout_minutes: 720
""",
    "kiro cli with agent and block list": """agents:
  - name: k
    platform: kiro
    command: kiro-cli
    workdir: {work}
    kiro_agent: Site_agent-1
    trust_tools:
      - read_file
      - fs_write
    timeout_minutes: 1
""",
    "kiro acp": """agents:
  - name: k
    platform: kiro
    command: kiro-cli
    transport: acp
    workdir: {work}
""",
    "kiro empty trust list": """agents:
  - name: k
    platform: kiro
    command: kiro-cli
    workdir: {work}
    trust_tools: []
""",
    "two agents": CLAUDE_AGENT + """  - name: helper
    platform: kiro
    command: kiro-cli
    workdir: {work}
""",
}


def agent(extra: str = "", platform: str = "claude-code", command: str = "claude", workdir: str = "{work}",
          name: str = "a") -> str:
    return f"""agents:
  - name: {name}
    platform: {platform}
    command: {command}
    workdir: {workdir}
{extra}"""


class ValidShapesTests(AgentCase):
    def test_every_accepted_shape_validates_and_lists(self):
        for label, text in GOOD_SHAPES.items():
            with self.subTest(shape=label):
                self.write_agents(text)
                r = self.umwayi("validate")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertTrue(r.stdout.startswith("ok: "), r.stdout)
                r = self.umwayi("list")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn("Nothing was started.", r.stdout)

    def test_list_shows_name_platform_transport_command_and_workdir(self):
        self.write_agents(KIRO_AGENT.replace("{transport}", "acp"))
        r = self.umwayi("list")
        self.assertEqual(self.lines(r)[0], f"helper  kiro  acp  kiro-cli  {self.work}")

    def test_validate_and_list_start_no_program(self):
        self.fake("claude")
        self.fake("kiro-cli")
        self.write_agents(GOOD_SHAPES["two agents"])
        self.umwayi("validate")
        self.umwayi("list")
        self.assertEqual(self.calls(), [])

    def test_agents_option_reads_another_file(self):
        p = self.write_agents(CLAUDE_AGENT, name="other.yaml")
        self.assertEqual(self.umwayi("validate").returncode, 64)  # no agents.yaml in the root
        r = self.umwayi("validate", "--agents", str(p))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_example_file_is_valid_once_its_folders_exist(self):
        text = (REPO / "agents.example.yaml").read_text(encoding="utf-8")
        text = re.sub(r"workdir: \S+", "workdir: {work}", text)
        self.write_agents(text)
        r = self.umwayi("validate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


REJECTED = [
    # (label, text, expected words in the problem, line)
    ("unknown top key", "agents: []\nextra: 1\n", "'extra' is not allowed at the top", 2),
    ("no agents key", "other: 1\n", "the file needs a list of agents", 1),
    ("agents not a list", "agents: 3\n", "agents must be a list with at least one agent", 1),
    ("empty list", "agents: []\n", "agents must be a list with at least one agent", 1),
    ("item not a mapping", "agents:\n  - just-a-word\n", "agent 1 must be a mapping", 2),
    ("not a mapping at all", "- a\n- b\n", "the file must be a mapping with one key, agents", 1),
    ("unknown agent key", agent("    args: [--bare]\n"), "'args' is not allowed", 6),
    ("shell key", agent("    shell: true\n"), "'shell' is not allowed", 6),
    ("missing name", "agents:\n  - platform: claude-code\n    command: claude\n    workdir: {work}\n", "needs name", 2),
    ("missing platform", "agents:\n  - name: a\n    command: claude\n    workdir: {work}\n", "needs platform", 2),
    ("missing command", "agents:\n  - name: a\n    platform: claude-code\n    workdir: {work}\n", "needs command", 2),
    ("missing workdir", "agents:\n  - name: a\n    platform: claude-code\n    command: claude\n", "needs workdir", 2),
    ("upper case name", agent(name="Reviewer"), "name must be a lowercase letter", 2),
    ("name too long", agent(name="a" * 33), "name must be a lowercase letter", 2),
    ("name starts with a digit", agent(name="1a"), "name must be a lowercase letter", 2),
    ("unknown platform", agent(platform="codex"), "platform must be one of: claude-code, kiro", 3),
    ("command is a path", agent(command="/usr/bin/claude"), "command must be one word from the allow list", 4),
    ("command with a flag", agent(command='"claude --bare"'), "command must be one word from the allow list", 4),
    ("command is a shell", agent(command="bash"), "command must be one word from the allow list", 4),
    ("kiro command for claude", agent(command="kiro-cli"), "allow list for claude-code: claude", 4),
    ("claude command for kiro", agent(platform="kiro", command="claude"), "allow list for kiro: kiro-cli", 4),
    ("command is a list", agent(command="[claude, -p]"), "command must be one word from the allow list", 4),
    ("kiro_agent for claude acp", agent("    transport: acp\n    kiro_agent: x\n"),
     "kiro_agent is only for platform kiro", 7),
    ("trust_tools for claude acp", agent("    transport: acp\n    trust_tools: [read_file]\n"),
     "trust_tools is only for platform kiro", 7),
    ("unknown transport", agent("    transport: http\n"), "transport must be cli or acp", 6),
    ("kiro_agent with acp", agent("    transport: acp\n    kiro_agent: x\n", platform="kiro", command="kiro-cli"),
     "kiro_agent cannot be used with transport acp", 7),
    ("kiro_agent for claude", agent("    kiro_agent: x\n"), "kiro_agent is only for platform kiro", 6),
    ("bad kiro_agent", agent("    kiro_agent: a/b\n", platform="kiro", command="kiro-cli"),
     "kiro_agent must be 1 to 64 letters", 6),
    ("relative workdir", agent(workdir="work"), "workdir must be an absolute path", 5),
    ("missing workdir folder", agent(workdir="{work}/nope"), "workdir must be an existing folder", 5),
    ("workdir with ..", agent(workdir="{work}/../work"), "workdir must not contain '..'", 5),
    ("workdir is the root", agent(workdir="{root}"), "must not be the umwayi root or a folder inside it", 5),
    ("workdir inside the root", agent(workdir="{root}/inner"), "must not be the umwayi root or a folder inside it", 5),
    ("workdir contains the root", agent(workdir="{root}/.."), "workdir must not contain '..'", 5),
    ("unknown kiro tool", agent("    trust_tools: [read_file, web_fetch]\n", platform="kiro", command="kiro-cli"),
     "trust_tools may only hold these tool IDs", 6),
    ("trust_tools for claude", agent("    trust_tools: [read_file]\n"), "trust_tools is only for platform kiro", 6),
    ("trust_tools not a list", agent("    trust_tools: read_file\n", platform="kiro", command="kiro-cli"),
     "trust_tools must be a list", 6),
    ("trust_tools twice", agent("    trust_tools: [read_file, read_file]\n", platform="kiro", command="kiro-cli"),
     "trust_tools names a tool twice", 6),
    ("max_turns 0", agent("    max_turns: 0\n"), "max_turns must be a whole number from 1 to 200", 6),
    ("max_turns 201", agent("    max_turns: 201\n"), "max_turns must be a whole number from 1 to 200", 6),
    ("max_turns true", agent("    max_turns: true\n"), "max_turns must be a whole number from 1 to 200", 6),
    ("max_turns text", agent("    max_turns: '5'\n"), "max_turns must be a whole number from 1 to 200", 6),
    ("max_turns for kiro", agent("    max_turns: 5\n", platform="kiro", command="kiro-cli"),
     "max_turns is only for platform claude-code", 6),
    ("timeout 0", agent("    timeout_minutes: 0\n"), "timeout_minutes must be a whole number from 1 to 720", 6),
    ("timeout 721", agent("    timeout_minutes: 721\n"), "timeout_minutes must be a whole number from 1 to 720", 6),
    ("tab", "agents:\n\t- name: a\n", "tab", 2),
    ("flow mapping", "agents: [{name: a}]\n", "", 1),
]


class RejectedTests(AgentCase):
    def setUp(self):
        super().setUp()
        (self.root / "inner").mkdir()

    def test_every_rejected_key_and_value_gives_64_with_its_line(self):
        for label, text, words, line in REJECTED:
            with self.subTest(case=label):
                self.write_agents(text)
                r = self.umwayi("validate")
                self.assertEqual(r.returncode, 64, r.stdout + r.stderr)
                problems = [ln for ln in self.lines(r) if ln.startswith("problem: ")]
                self.assertTrue(problems, r.stdout)
                self.assertTrue(any(words in p for p in problems), f"{words!r} not in {problems}")
                self.assertTrue(any(p.startswith(f"problem: line {line}:") and words in p for p in problems),
                                f"line {line} expected in {problems}")
                self.assertRegex(self.lines(r)[-1], r"^\d+ problem\(s\) found in agents.yaml$")
                r = self.umwayi("list")
                self.assertEqual(r.returncode, 64)
                self.assertIn("see 'umwayi agent validate'", r.stderr)

    def test_duplicate_names_point_at_the_second(self):
        self.write_agents(CLAUDE_AGENT + CLAUDE_AGENT.replace("agents:\n", ""))
        r = self.umwayi("validate")
        self.assertEqual(r.returncode, 64)
        self.assertIn("problem: line 7: agent 2: the name is used twice", r.stdout)

    def test_every_problem_is_reported_not_only_the_first(self):
        self.write_agents(agent("    max_turns: 0\n    timeout_minutes: 0\n", command="bash"))
        r = self.umwayi("validate")
        self.assertEqual(r.returncode, 64)
        self.assertIn("3 problem(s) found", r.stdout)

    def test_workdir_that_contains_the_root_is_refused(self):
        self.write_agents(agent(workdir=str(self.tmp)))
        r = self.umwayi("validate")
        self.assertEqual(r.returncode, 64)
        self.assertIn("workdir must not contain the umwayi root", r.stdout)

    def test_workdir_link_into_the_root_is_refused(self):
        os.symlink(self.root / "inner", self.tmp / "sneaky")
        self.write_agents(agent(workdir=str(self.tmp / "sneaky")))
        r = self.umwayi("validate")
        self.assertEqual(r.returncode, 64)
        self.assertIn("must not be the umwayi root or a folder inside it", r.stdout)

    def test_more_than_fifty_agents(self):
        items = "".join(f"  - name: a{i}\n    platform: claude-code\n    command: claude\n    workdir: {{work}}\n"
                        for i in range(51))
        self.write_agents("agents:\n" + items)
        r = self.umwayi("validate")
        self.assertEqual(r.returncode, 64)
        self.assertIn("at most 50 agents", r.stdout)

    def test_no_line_text_and_no_value_is_ever_printed(self):
        for text in (agent(command=SECRET), agent(name=SECRET), agent(platform=SECRET), agent(workdir=SECRET),
                     agent(f"    {SECRET}: 1\n"), agent(f"    kiro_agent: {SECRET}/x\n"),
                     agent(f"    trust_tools: [{SECRET}]\n", platform="kiro", command="kiro-cli"),
                     f"agents:\n  - name: a\n    command: '{SECRET}\n"):
            with self.subTest(text=text.splitlines()[-1]):
                self.write_agents(text)
                for sub in ("validate", "list"):
                    r = self.umwayi(sub)
                    self.assertEqual(r.returncode, 64)
                    self.assertNotIn(SECRET, r.stdout + r.stderr)
                    self.assertNotIn("sk-live", r.stdout + r.stderr)


class FileTests(AgentCase):
    def test_missing_file(self):
        for sub in ("validate", "list"):
            r = self.umwayi(sub)
            self.assertEqual(r.returncode, 64)
            self.assertIn("agents.yaml was not found", r.stderr)
        r = self.umwayi("check", "reviewer")
        self.assertEqual(r.returncode, 64)

    def test_link_folder_big_and_not_utf8_files(self):
        real = self.write_agents(CLAUDE_AGENT, name="real.yaml")
        os.symlink(real, self.root / "agents.yaml")
        self.assertIn("must be a regular file", self.umwayi("validate").stderr)
        (self.root / "agents.yaml").unlink()
        (self.root / "agents.yaml").mkdir()
        self.assertIn("must be a regular file", self.umwayi("validate").stderr)
        (self.root / "agents.yaml").rmdir()
        (self.root / "agents.yaml").write_text("# x\n" * 20000, encoding="utf-8")
        self.assertIn("larger than", self.umwayi("validate").stderr)
        (self.root / "agents.yaml").write_bytes(b"agents:\n  - name: \xff\n")
        r = self.umwayi("validate")
        self.assertEqual(r.returncode, 64)
        self.assertIn("not valid UTF-8", r.stderr)

    def test_root_must_exist(self):
        r = self.umwayi("validate", root=self.tmp / "nowhere")
        self.assertEqual(r.returncode, 64)
        self.assertIn("must be an existing folder", r.stderr)

    def test_unknown_or_bad_agent_name_is_64(self):
        self.write_agents(CLAUDE_AGENT)
        self.assertEqual(self.umwayi("check", "other").returncode, 64)
        self.assertEqual(self.umwayi("check", "Bad Name").returncode, 64)

    def test_no_subcommand_and_unknown_subcommands_are_64(self):
        self.assertEqual(self.umwayi().returncode, 64)
        for later in ("run", "chat", "start"):  # run and chat come in parts 3 and 5
            with self.subTest(sub=later):
                self.assertEqual(self.umwayi(later, "reviewer").returncode, 64)


class CrashTests(AgentCase):
    def test_a_crash_or_ctrl_c_is_exit_2_never_1(self):
        self.write_agents(CLAUDE_AGENT)
        for sub, target in (("validate", "umwayi.agents:check_text"), ("list", "umwayi.agents:load"),
                            ("check", "umwayi.agents:gate_checks")):
            for effect in ("crash", "interrupt"):
                with self.subTest(sub=sub, effect=effect):
                    args = (sub, "reviewer") if sub == "check" else (sub,)
                    r = self.umwayi(*args, fault=f"{target}:{effect}", extra={"UMWAYI_FAULT_TEXT": SECRET})
                    self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                    self.assertIn("Nothing was started", r.stderr)
                    self.assertNotIn(SECRET, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
