"""W46: the Kiro hook file must name the resolved root path, and the refusal says so.

On macOS `/var` is a link to `/private/var`, so a root under `/var` resolves to `/private/var/...`. umwayi resolves the root
itself (`agents._root`) and compares the hook command word for word, so a hook file written with the path through the link is
not the hook umwayi looks for. Here a root reached through a link stands for that case: `umwayi agent check` with the root
given through the link refuses a hook file that names the link path, and its line names the resolved path and `pwd -P`; a hook
file that names the resolved path passes. Real child processes and the fake `kiro-cli`; no real Kiro.
"""

import os

from tests.agents.support import AgentCase

AGENTS = """agents:
  - name: helper
    platform: kiro
    command: kiro-cli
    workdir: {work}
"""


class HookRootTests(AgentCase):
    def setUp(self):
        super().setUp()
        self.fake("kiro-cli")
        self.write_rules()
        self.write_agents(AGENTS)
        self.link = self.tmp / "root-link"  # stands for /var on macOS, a link to the real folder
        os.symlink(self.root, self.link)

    def test_a_hook_file_with_the_link_path_is_refused_and_the_line_names_the_resolved_path(self):
        self.kiro_hook_file(command=self.kiro_command(python="python3", root=self.link))
        r = self.umwayi("check", "helper", root=self.link)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        line = next(l for l in self.lines(r) if l.startswith("no: kiro hook file: "))
        self.assertIn(f"--root {self.root}'", line, "the command it looks for names the resolved root")
        self.assertIn(f"The root must be written as its resolved path, {self.root} (pwd -P in the root prints it; "
                      "on macOS /var is /private/var)", line)
        self.assertNotIn(f"--root {self.link}", line)
        self.assertEqual([c for c in self.calls() if c.get("started")], [])

    def test_a_hook_file_with_the_resolved_path_passes_even_when_the_root_is_given_through_the_link(self):
        self.kiro_hook_file(command=self.kiro_command(python="python3", root=self.root))
        r = self.umwayi("check", "helper", root=self.link)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ok: kiro hook file: ", r.stdout)

    def test_the_setup_doc_says_pwd_p_and_private_var(self):
        text = (self.src / "adapters" / "kiro" / "README.md").read_text(encoding="utf-8")
        self.assertIn("pwd -P", text)
        self.assertIn("/private/var", text)


if __name__ == "__main__":
    import unittest
    unittest.main()
