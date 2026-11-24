"""G7, the read only part: pr-queue.md, `umwayi pr queue list` and `next` (umwayi/prqueue.py).

The file is strict (every fault below is an error with a line number and never the text of the line). The commands only read: a test shows
that no file changes, and that `next` waits while a row is open, pushes the first local row by order with its steps and its owner stop,
says nothing is to push, and says `queue low` against keep_ready when tasks are pending.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from umwayi import prqueue as pq

REPO = Path(__file__).resolve().parent.parent
HEAD = "| branch | title | order | stops | status | pr | head |\n|---|---|---|---|---|---|---|\n"


def doc(*rows, keep=None):
    return (f"keep_ready: {keep}\n\n" if keep is not None else "") + HEAD + "".join(r + "\n" for r in rows)


A = "| a-branch | First task | 1 | yes: units.yaml | local | - | abc1234 |"
B = "| b-branch | Second task | 2 | no | local | - | - |"
O = "| o-branch | The open one | 1 | no | open | 215 | 8029c7c |"
M = "| m-branch | Done | 3 | no | merged | 190 | deadbee |"


class ParseTests(unittest.TestCase):
    def test_a_good_file_parses_with_the_default_keep_ready(self):
        d = pq.parse(doc(A, B, O.replace("1 |", "3 |", 1)))
        self.assertEqual((d.keep_ready, len(d.rows), d.rows[0].owner_stop, d.rows[1].owner_stop), (2, 3, True, False))
        self.assertEqual(pq.parse(doc(A, keep=0)).keep_ready, 0)
        self.assertEqual(pq.parse(doc(A, keep=9)).keep_ready, 9)

    def test_planted_faults_each_is_an_error_with_a_line_number_and_no_text_of_the_line(self):
        cases = {
            "a bad header": doc(A).replace("| head |", "| tip |", 1),
            "no separator": HEAD.split("\n")[0] + "\n" + A + "\n",
            "no table": "keep_ready: 2\nnothing here\n",
            "a bad status": doc(A.replace("local", "waiting")),
            "an open row without a pr": doc(O.replace("215", "-")),
            "a local row with a pr": doc(A.replace("- | abc1234", "7 | abc1234")),
            "a bad head": doc(A.replace("abc1234", "xyz")),
            "a bad order": doc(A.replace("| 1 |", "| first |")),
            "stops not no or yes with a reason": doc(A.replace("yes: units.yaml", "maybe")),
            "an empty reason": doc(A.replace("yes: units.yaml", "yes: ")),
            "a bad branch": doc(A.replace("a-branch", "a branch")),
            "a branch with ..": doc(A.replace("a-branch", "a..b")),
            "a row with too few columns": doc("| a-branch | First | 1 | no | local |"),
            "an em dash": doc(A).replace("First task", "First—task"),
            "a tab": doc(A).replace("First task", "First\ttask"),
            "keep_ready twice": "keep_ready: 1\nkeep_ready: 2\n" + doc(A),
            "keep_ready not a number": "keep_ready: many\n" + doc(A),
            "keep_ready 10": "keep_ready: 10\n" + doc(A),
            "the same branch twice": doc(A, A.replace("| 1 |", "| 2 |")),
            "two local rows with one order": doc(A, B.replace("| 2 |", "| 1 |")),
            "two open rows": doc(O, O.replace("o-branch", "p-branch").replace("215", "216")),
            "two tables": doc(A) + "\ntext\n\n" + doc(B),
        }
        for label, text in cases.items():
            with self.subTest(label):
                with self.assertRaises(pq.PrQueueError) as cm:
                    pq.parse(text)
                msg = str(cm.exception)
                self.assertNotIn("First task", msg)
                self.assertNotIn("units.yaml", msg)

    def test_the_error_names_the_line(self):
        with self.assertRaises(pq.PrQueueError) as cm:
            pq.parse(doc(A, B.replace("local", "waiting")))
        self.assertIn("line 4", str(cm.exception))  # the header is line 1, the separator 2, the first row 3


class NextTests(unittest.TestCase):
    def test_a_row_that_is_open_means_wait_and_names_the_pull_request(self):
        lines = pq.next_lines(pq.parse(doc(O, A.replace("| 1 |", "| 2 |"))), [])
        self.assertTrue(lines[0].startswith("wait: pull request 215 (o-branch) is open"))
        self.assertIn("tools.pr_green 215", lines[0])
        self.assertEqual(len(lines), 1)  # keep_ready 2, one local, no tasks pending: nothing to add

    def test_with_nothing_open_the_first_local_row_by_order_is_pushed_with_its_steps_and_stop(self):
        lines = pq.next_lines(pq.parse(doc(B, A)), [])
        self.assertTrue(lines[0].startswith("push: a-branch (stops for the owner: units.yaml)"))
        self.assertEqual(len(lines), 6)
        self.assertIn("git push -u origin a-branch", lines[3])
        self.assertIn("merge_main", lines[1])
        self.assertTrue(pq.next_lines(pq.parse(doc(B)), [])[0].startswith("push: b-branch (no owner stop)"))

    def test_nothing_local_and_nothing_open_says_nothing_and_names_nothing_to_push(self):
        self.assertEqual(pq.next_lines(pq.parse(doc(M)), []), ["nothing: no row is local and none is open."])
        self.assertEqual(pq.next_lines(pq.parse(doc()), []), ["nothing: no row is local and none is open."])

    def test_planted_fault_the_queue_is_low_when_fewer_than_keep_ready_are_local_and_tasks_are_pending(self):
        lines = pq.next_lines(pq.parse(doc(O, keep=2)), ["Build the next thing", "Another"])
        self.assertEqual(lines[-1], "queue low: 0 of 2 branches ready, 2 task(s) pending: build Build the next thing next. "
                                    "Nothing is started by this command.")
        lines = pq.next_lines(pq.parse(doc(A, keep=2)), ["Only task"])
        self.assertTrue(lines[-1].startswith("queue low: 1 of 2 branches ready, 1 task(s) pending"))

    def test_planted_fault_two_pending_tasks_and_no_ready_branch_name_the_first_task(self):
        lines = pq.next_lines(pq.parse(doc(keep=2)), ["First pending task", "Second pending task"])
        self.assertEqual(lines[-1], "queue low: 0 of 2 branches ready, 2 task(s) pending: build First pending task next. "
                                    "Nothing is started by this command.")

    def test_a_blocked_task_is_named_and_skipped_and_the_next_free_one_is_built(self):
        pending = ["Needs an answer [blocked: the owner's choice of option A, B or C]", "Free one", "Another free one"]
        lines = pq.next_lines(pq.parse(doc(A, keep=2)), pending)
        self.assertEqual(lines[-2], "blocked: Needs an answer needs the owner's choice of option A, B or C")
        self.assertTrue(lines[-1].startswith("queue low: 1 of 2 branches ready, 3 task(s) pending: build Free one next"))
        self.assertEqual(pq.split_blocked(pending)[0], ["Free one", "Another free one"])

    def test_when_every_pending_task_is_blocked_it_says_so_and_asks_for_an_answer(self):
        lines = pq.next_lines(pq.parse(doc(keep=2)), ["One [blocked: text]", "Two [blocked: a file]"])
        self.assertEqual(lines[0], "nothing: no row is local and none is open.")
        self.assertEqual(lines[1:3], ["blocked: One needs text", "blocked: Two needs a file"])
        self.assertIn("every pending task is blocked: answer one of them", lines[-1])

    def test_a_title_that_only_looks_blocked_is_not(self):
        self.assertEqual(pq.split_blocked(["[blocked: x]", "Free [blocked:]", "Free blocked: x", "Mid [blocked: x] more"])[1], [])

    def test_no_queue_low_line_when_enough_are_ready_or_no_task_is_pending_or_keep_ready_is_zero(self):
        self.assertFalse(any("queue low" in l for l in pq.next_lines(pq.parse(doc(A, B, keep=2)), ["T"])))
        self.assertFalse(any("queue low" in l for l in pq.next_lines(pq.parse(doc(A, keep=2)), [])))
        self.assertFalse(any("queue low" in l for l in pq.next_lines(pq.parse(doc(keep=0)), ["T"])))

    def test_without_a_file_it_says_so_and_still_warns_when_tasks_are_pending(self):
        self.assertEqual(pq.next_lines(None, []), ["nothing: there is no pr-queue.md."])
        self.assertTrue(pq.next_lines(None, ["T"])[-1].startswith("queue low: 0 of 2"))


class NeedsBuildTests(unittest.TestCase):
    """B-0012: `next --check` says that the session has not finished: the queue is low and a free task is pending."""

    def test_planted_fault_two_pending_free_tasks_and_no_ready_branch_need_a_build(self):
        self.assertTrue(pq.needs_build(pq.parse(doc(keep=2)), ["First", "Second"]))
        self.assertTrue(pq.needs_build(pq.parse(doc(O, A, keep=2)), ["First"]))  # one ready of two
        self.assertTrue(pq.needs_build(None, ["First"]))

    def test_enough_ready_no_task_only_blocked_tasks_or_keep_ready_zero_need_nothing(self):
        self.assertFalse(pq.needs_build(pq.parse(doc(A, B, keep=2)), ["First"]))
        self.assertFalse(pq.needs_build(pq.parse(doc(keep=2)), []))
        self.assertFalse(pq.needs_build(pq.parse(doc(keep=2)), ["One [blocked: an answer]", "Two [blocked: a file]"]))
        self.assertFalse(pq.needs_build(pq.parse(doc(keep=0)), ["First"]))
        self.assertFalse(pq.needs_build(None, []))

    def test_one_free_task_among_blocked_ones_needs_a_build(self):
        self.assertTrue(pq.needs_build(pq.parse(doc(keep=1)), ["One [blocked: an answer]", "Free one"]))


class ListTests(unittest.TestCase):
    def test_list_puts_the_open_row_first_then_local_rows_by_order(self):
        lines = pq.list_lines(pq.parse(doc(B, A, O.replace("| 1 |", "| 4 |"))))
        self.assertIn("o-branch", lines[0])
        self.assertIn("PR 215", lines[0])
        self.assertIn("a-branch", lines[1])
        self.assertIn("owner stop", lines[1])
        self.assertEqual(lines[-1], "3 rows, 2 local, keep_ready 2.")

    def test_list_without_a_file_or_rows(self):
        self.assertEqual(pq.list_lines(None), ["There is no pr-queue.md. Nothing is queued."])
        self.assertIn("has no rows", pq.list_lines(pq.parse(doc()))[0])


class CommandTests(unittest.TestCase):
    def run_cmd(self, root, *args):
        p = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(root), "pr", "queue", *args], cwd=REPO, capture_output=True,
                           text=True, timeout=60)
        return p

    def test_the_real_commands_read_the_file_and_change_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "pr-queue.md").write_text(doc(O, A.replace("| 1 |", "| 2 |"), keep=2), encoding="utf-8")
            before = (root / "pr-queue.md").read_bytes()
            p = self.run_cmd(root, "next")
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("wait: pull request 215", p.stdout)
            p = self.run_cmd(root, "list")
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("a-branch", p.stdout)
            self.assertEqual((root / "pr-queue.md").read_bytes(), before)
            self.assertEqual(sorted(x.name for x in root.iterdir()), ["pr-queue.md"])  # no logbook entry, no other file

    def test_next_check_is_exit_3_when_the_queue_is_low_and_still_changes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "pr-queue.md").write_text(doc(O, keep=2), encoding="utf-8")
            subprocess.run([sys.executable, "-m", "umwayi", "--root", str(root), "queue", "add", "--kind", "task", "Build the next piece"],
                           cwd=REPO, capture_output=True, text=True, timeout=60, check=True)
            before = sorted((x.name, x.read_bytes()) for x in root.iterdir() if x.name == "pr-queue.md")
            plain = self.run_cmd(root, "next")
            checked = self.run_cmd(root, "next", "--check")
            self.assertEqual((plain.returncode, checked.returncode), (0, 3))
            self.assertEqual(plain.stdout, checked.stdout)  # the same lines; only the exit code differs
            self.assertIn("queue low: 0 of 2 branches ready", checked.stdout)
            self.assertEqual(sorted((x.name, x.read_bytes()) for x in root.iterdir() if x.name == "pr-queue.md"), before)
            (root / "pr-queue.md").write_text(doc(A, B, keep=2), encoding="utf-8")
            self.assertEqual(self.run_cmd(root, "next", "--check").returncode, 0)

    def test_a_bad_file_is_exit_64_and_a_missing_file_is_exit_0(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.assertEqual(self.run_cmd(root, "next").returncode, 0)
            (root / "pr-queue.md").write_text(doc(A.replace("local", "waiting")), encoding="utf-8")
            p = self.run_cmd(root, "list")
            self.assertEqual(p.returncode, 64)
            self.assertIn("line 3", p.stderr + p.stdout)

    def test_next_counts_the_open_tasks_of_queue_md_as_pending(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "pr-queue.md").write_text(doc(O, keep=2), encoding="utf-8")
            add = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(root), "queue", "add", "--kind", "task", "Build the next piece"],
                                 cwd=REPO, capture_output=True, text=True, timeout=60)
            self.assertEqual(add.returncode, 0, add.stderr)
            p = self.run_cmd(root, "next")
            self.assertIn("queue low: 0 of 2 branches ready, 1 task(s) pending: build Build the next piece next", p.stdout)


if __name__ == "__main__":
    unittest.main()
