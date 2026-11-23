"""W78 step 3 (W41 C1, W78.R5): the watched files. A pure module: it reads files and writes nothing.

Each rule has a planted fault: the test asserts what the rule says, and the fault is the opposite of it (a file left off the
list, a changed file that is not a finding, a name that is not one of the fixed ones).
"""
import os
import tempfile
import unittest
from unittest import mock

from umwayi import watched

GUARD_FILES_OF_THE_DESIGN = (".umwayi/enforcement.yaml", "guidance.yaml", "units.yaml", "agents.yaml", ".kiro/steering/umwayi")


class Root(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="umwayi-watched-")
        self.addCleanup(self._tmp.cleanup)
        self.root = os.path.realpath(self._tmp.name)

    def put(self, name, text="x\n"):
        path = os.path.join(self.root, *name.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path


class ListTests(unittest.TestCase):
    def test_the_mode_file_and_every_guard_file_of_the_design_are_on_the_list(self):
        """W78.R5: the mode file is on the watched list. The design names guidance, units, agents, the steering and the tools."""
        for name in GUARD_FILES_OF_THE_DESIGN + ("tools",):
            self.assertIn(name, watched.NAMES)

    def test_rules_and_autonomy_are_watched_too(self):
        self.assertIn("rules.yaml", watched.NAMES)
        self.assertIn("autonomy.yaml", watched.NAMES)

    def test_every_name_is_plain_and_relative(self):
        for name in watched.NAMES:
            self.assertFalse(name.startswith("/") or ".." in name.split("/"), name)

    def test_planted_fault_a_list_without_the_mode_file_misses_a_change_to_it(self):
        with tempfile.TemporaryDirectory() as d:
            before = {n: v for n, v in watched.snapshot(d).items() if n != ".umwayi/enforcement.yaml"}
            os.makedirs(os.path.join(d, ".umwayi"))
            with open(os.path.join(d, ".umwayi", "enforcement.yaml"), "w") as f:
                f.write("enforcement: cooperative\n")
            after = {n: v for n, v in watched.snapshot(d).items() if n != ".umwayi/enforcement.yaml"}
            self.assertEqual(watched.changed(before, after), [])  # what the real list must never do
            self.assertEqual(watched.changed(watched.snapshot(d), watched.snapshot(d)), [])


class SnapshotTests(Root):
    def test_nothing_changed_is_no_finding_even_when_the_files_are_absent(self):
        a = watched.snapshot(self.root)
        self.assertEqual(watched.changed(a, watched.snapshot(self.root)), [])
        self.assertTrue(all(v == watched.ABSENT for v in a.values()))

    def test_a_change_to_each_file_is_named(self):
        for name in watched.FILES:
            with self.subTest(name=name):
                before = watched.snapshot(self.root)
                self.put(name, "one\n")
                mid = watched.snapshot(self.root)
                self.assertEqual(watched.changed(before, mid), [name])
                self.put(name, "two\n")  # a second edit is a change again
                self.assertEqual(watched.changed(mid, watched.snapshot(self.root)), [name])
                os.remove(os.path.join(self.root, *name.split("/")))

    def test_a_deleted_file_is_a_finding(self):
        self.put("units.yaml")
        before = watched.snapshot(self.root)
        os.remove(os.path.join(self.root, "units.yaml"))
        self.assertEqual(watched.changed(before, watched.snapshot(self.root)), ["units.yaml"])

    def test_a_change_in_the_tools_folder_is_named_tools(self):
        self.put("tools/a.py", "a\n")
        before = watched.snapshot(self.root)
        self.put("tools/a.py", "b\n")
        self.assertEqual(watched.changed(before, watched.snapshot(self.root)), ["tools"])
        mid = watched.snapshot(self.root)
        self.put("tools/sub/new.py", "n\n")
        self.assertEqual(watched.changed(mid, watched.snapshot(self.root)), ["tools"])
        end = watched.snapshot(self.root)
        os.remove(os.path.join(self.root, "tools", "a.py"))
        self.assertEqual(watched.changed(end, watched.snapshot(self.root)), ["tools"])

    def test_the_steering_may_be_a_file_or_a_folder(self):
        self.put(".kiro/steering/umwayi/rule1.md", "r\n")
        before = watched.snapshot(self.root)
        self.put(".kiro/steering/umwayi/rule1.md", "changed\n")
        self.assertEqual(watched.changed(before, watched.snapshot(self.root)), [".kiro/steering/umwayi"])

    def test_a_file_that_is_not_on_the_list_is_not_a_finding(self):
        before = watched.snapshot(self.root)
        for name in ("README.md", "docs/status-log.md", "memory/notes.md", "umwayi/x.py", "toolsbox/a.py", "LOGBOOK.md"):
            self.put(name)
        self.assertEqual(watched.changed(before, watched.snapshot(self.root)), [])

    def test_a_link_is_not_followed_and_a_new_target_is_a_finding(self):
        self.put("elsewhere.yaml", "a\n")
        os.symlink(os.path.join(self.root, "elsewhere.yaml"), os.path.join(self.root, "units.yaml"))
        before = watched.snapshot(self.root)
        self.assertTrue(before["units.yaml"].startswith("link:"))
        self.put("elsewhere.yaml", "b\n")  # the content behind the link is not read
        self.assertEqual(watched.changed(before, watched.snapshot(self.root)), [])
        os.remove(os.path.join(self.root, "units.yaml"))
        os.symlink(os.path.join(self.root, "other"), os.path.join(self.root, "units.yaml"))
        self.assertEqual(watched.changed(before, watched.snapshot(self.root)), ["units.yaml"])

    def test_a_file_that_becomes_unreadable_is_a_finding_and_nothing_raises(self):
        path = self.put("units.yaml", "a\n")
        before = watched.snapshot(self.root)
        os.chmod(path, 0)
        self.addCleanup(os.chmod, path, 0o600)
        after = watched.snapshot(self.root)
        if os.geteuid() != 0:  # root can read anything
            self.assertEqual(watched.changed(before, after), ["units.yaml"])

    def test_the_names_of_a_finding_are_the_fixed_ones_and_in_list_order(self):
        before = watched.snapshot(self.root)
        for name in ("tools/z.py", "agents.yaml", "units.yaml"):
            self.put(name)
        got = watched.changed(before, watched.snapshot(self.root))
        self.assertEqual(got, [n for n in watched.NAMES if n in ("agents.yaml", "units.yaml", "tools")])
        self.assertTrue(set(got) <= set(watched.NAMES))

    def test_a_folder_with_too_many_files_is_not_read_without_end(self):
        with mock.patch.object(watched, "MAX_TREE_FILES", 3):
            for i in range(5):
                self.put(f"tools/f{i}.py")
            self.assertEqual(watched.snapshot(self.root)["tools"], "many:3")

    def test_the_module_writes_nothing(self):
        before = sorted(os.listdir(self.root))
        watched.snapshot(self.root)
        self.assertEqual(sorted(os.listdir(self.root)), before)


if __name__ == "__main__":
    unittest.main()
