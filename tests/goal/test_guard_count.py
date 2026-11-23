"""W78 5(g): the `counts` entry of a task holds the number of guard findings of that task, from a real finding.

PR 176 read `guard_n` and nothing set it, so a task that stopped on `guard_file_changed` wrote "0 guard findings". The
supervisor now adds one where the guard check records the finding. A guard finding of the builder, the tester or the check
is one finding in the entry of that move.
"""
import re
import unittest

from tests.goal.test_guard_files import GuardCase
from umwayi import goalstate as gs
from umwayi import logbook


def counts_lines(root):
    return [e.checked for e in logbook.read_checked(root) if e.source == gs.SOURCE and e.added.endswith(": counts")]


class GuardCountTests(GuardCase):
    def guards(self):
        found = [int(re.search(r"(\d+) guard findings", c).group(1)) for c in counts_lines(self.root)]
        return found

    def test_one_guard_stop_of_the_builder_counts_one(self):
        self.run_goal(builder=[self.edit("rules.yaml")])
        self.assertEqual(self.guards(), [1])

    def test_a_task_with_no_guard_stop_counts_zero(self):
        goal, code = self.run_goal()
        self.assertEqual(code, 0, self.err)
        self.assertEqual(self.guards(), [0])

    def test_a_guard_stop_of_the_tester_counts_one(self):
        self.run_goal(tester=[self.edit("rules.yaml")])
        self.assertEqual(self.guards(), [1], counts_lines(self.root))

    def test_a_guard_stop_of_the_check_counts_one(self):
        self.run_goal(check=[self.edit("rules.yaml")])
        self.assertEqual(self.guards(), [1], counts_lines(self.root))

    def test_planted_fault_a_guard_stop_that_does_not_count_reads_zero(self):
        """The same stop, with the setting taken out of finish_guard, writes 0: so the tests above would fail without it."""
        from unittest import mock
        from umwayi import goalrun

        def without_the_count(run, role, names):
            shown = ", ".join(names)
            run.finish("guard_file_changed", facts=[("cause", {"word": "guard_file_changed"}), ("guard_files", {"names": shown})],
                       recommendation="A guard file changed.")
        with mock.patch.object(goalrun._Run, "finish_guard", without_the_count):
            self.run_goal(builder=[self.edit("rules.yaml")])
        self.assertEqual(self.guards(), [0])


if __name__ == "__main__":
    unittest.main()
