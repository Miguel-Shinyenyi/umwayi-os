"""W9.1.1: tests of the test helpers themselves: the generators, the shrinker, the fake agent, the fake root and the clock.

They need no code of W9.2 to W9.5. If these fail, the other goal tests cannot be trusted.
"""

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.goal import gen
from tests.goal.fakeroot import FakeClock, FakeGit, git
from tests.goal.fake_agent import __doc__ as _doc  # noqa: F401  (the script is importable and documented)

PINNED_BITS = [34, 145, 216, 205, 195, 16]
AGENT = str(Path(gen.__file__).with_name("fake_agent.py"))


def run_agent(script, prompt="Nonce: 0123456789abcdef\n", cwd=None, timeout=20):
    env = dict(os.environ, FAKE_GOAL_SCRIPT=json.dumps(script))
    return subprocess.run([sys.executable, AGENT], input=prompt, capture_output=True, text=True, env=env,
                          cwd=cwd, timeout=timeout)


class GeneratorTests(unittest.TestCase):
    def test_same_seed_same_cases(self):
        a, b = gen.Gen(7), gen.Gen(7)
        self.assertEqual([a.json_value() for _ in range(50)], [b.json_value() for _ in range(50)])
        self.assertEqual(a.data(0, 30), b.data(0, 30))

    def test_fixed_seed_values_are_pinned(self):
        # getrandbits is defined by the Mersenne Twister, so these are the same on Python 3.10 to 3.13
        g = gen.Gen(1)
        self.assertEqual([g.bits(8) for _ in range(6)], PINNED_BITS)

    def test_below_between_pick_stay_in_range(self):
        g = gen.Gen(3)
        for _ in range(2000):
            self.assertTrue(0 <= g.below(7) < 7)
            self.assertTrue(5 <= g.between(5, 9) <= 9)
            self.assertIn(g.pick("abc"), "abc")
        self.assertEqual(g.below(1), 0)

    def test_seeds_are_three_fixed_and_one_fresh(self):
        self.assertEqual(gen.SEEDS[:3], (1, 2, 3))
        self.assertEqual(len(gen.SEEDS), 4)

    def test_sentence_has_the_asked_length(self):
        g = gen.Gen(4)
        for _ in range(500):
            s = g.sentence(10, 60)
            self.assertTrue(10 <= len(s) <= 60, s)

    def test_a_property_that_holds_passes_quickly(self):
        start = time.monotonic()
        gen.run_property(self, lambda g: g.data(0, 20), lambda b: isinstance(b, bytes), cases=5000, seeds=gen.FIXED_SEEDS)
        self.assertLess(time.monotonic() - start, 30)

    def test_a_failing_property_prints_the_seed_and_a_shrunk_case(self):
        with self.assertRaises(AssertionError) as cm:
            gen.run_property(self, lambda g: g.text("ab", 5, 40), lambda s: "b" not in s, cases=200, seeds=(9,))
        msg = str(cm.exception)
        self.assertIn("seed 9", msg)
        self.assertIn("shrunk case 'b'", msg)


class ShrinkerTests(unittest.TestCase):
    def test_a_string_shrinks_to_the_smallest_failing_one(self):
        small = gen.shrink("aaaXaaaYaaa", lambda s: "X" in s and "Y" in s)
        self.assertTrue("X" in small and "Y" in small and len(small) <= 5)

    def test_bytes_list_dict_and_int(self):
        self.assertEqual(gen.shrink(b"abcdef", lambda b: b"c" in b), b"c")
        self.assertEqual(gen.shrink([1, 2, 3, 4], lambda v: 3 in v), [3])
        self.assertEqual(gen.shrink({"a": 1, "b": 2}, lambda d: "b" in d), {"b": 2})
        self.assertTrue(3 <= gen.shrink(1000, lambda n: n >= 3) < 6)

    def test_an_exception_counts_as_failing(self):
        def boom(v):
            raise ValueError("x")
        self.assertEqual(gen.shrink("abc", boom), "")


class FakeAgentTests(unittest.TestCase):
    def test_no_script_prints_one_line(self):
        p = run_agent([])
        self.assertEqual((p.returncode, p.stdout.strip()), (0, "fake agent: nothing to do"))

    def test_print_error_exit_and_result_with_the_nonce(self):
        p = run_agent([{"print": "hello"}, {"error": "Error: boom"},
                       {"result": "UMWAYI-RESULT", "body": {"checks": []}}, {"exit": 4}])
        self.assertEqual(p.returncode, 4)
        lines = p.stdout.splitlines()
        self.assertEqual(lines[:2], ["hello", "Error: boom"])
        self.assertEqual(lines[2], 'UMWAYI-RESULT 0123456789abcdef {"checks":[]}')

    def test_a_wrong_nonce_is_printed_when_asked(self):
        p = run_agent([{"result": "UMWAYI-CHECK", "nonce": "wrong", "body": {}}])
        self.assertIn("UMWAYI-CHECK ffffffffffffffff", p.stdout)

    def test_write_change_and_whoami_use_the_working_folder_and_a_new_session_each_time(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "MARKER").write_text("marker-1\n", encoding="utf-8")
            a = run_agent([{"write": "sub/f.txt", "text": "x"}, {"change": "g.txt", "every": 0, "times": 3},
                           {"whoami": True}], cwd=d)
            b = run_agent([{"whoami": True}], cwd=d)
            self.assertEqual(Path(d, "sub", "f.txt").read_text(), "x")
            self.assertEqual(Path(d, "g.txt").read_text(), "0\n1\n2\n")
            la, lb = a.stdout.strip(), b.stdout.strip()
            self.assertIn("marker=marker-1", la)
            self.assertIn(f"cwd={os.path.realpath(d)}", la)
            self.assertNotEqual(la.split("session=")[1].split()[0], lb.split("session=")[1].split()[0])

    def test_spend_flood_and_noise(self):
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, FAKE_GOAL_SCRIPT=json.dumps([{"spend": 7}, {"spend": 3}]),
                       FAKE_GOAL_SPEND=os.path.join(d, "spend"))
            subprocess.run([sys.executable, AGENT], input="", env=env, timeout=20)
            self.assertEqual(Path(d, "spend").read_text().split(), ["7", "3"])
        p = run_agent([{"flood": 100000, "newline": False}])
        self.assertEqual(len(p.stdout), 100000)
        q = subprocess.run([sys.executable, AGENT], input=b"", capture_output=True, timeout=20,
                           env=dict(os.environ, FAKE_GOAL_SCRIPT=json.dumps([{"noise": 300}])))
        with self.assertRaises(UnicodeDecodeError):
            q.stdout.decode("utf-8")

    def test_ignore_sigterm(self):
        env = dict(os.environ, FAKE_GOAL_SCRIPT=json.dumps([{"ignore_sigterm": True}, {"print": "up"}, {"sleep": 3}]))
        p = subprocess.Popen([sys.executable, AGENT], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=env)
        p.stdin.close()
        self.assertEqual(p.stdout.readline().strip(), "up")
        p.send_signal(signal.SIGTERM)
        time.sleep(0.2)
        self.assertIsNone(p.poll())
        p.kill()
        p.wait()
        p.stdout.close()


class FakeRootTests(unittest.TestCase):
    def test_the_clock_only_moves_when_told(self):
        c = FakeClock(100)
        self.assertEqual((c(), c()), (100, 100))
        self.assertEqual(c.advance(5), 105)

    def test_fake_git_has_main_origin_and_worktree_support(self):
        with tempfile.TemporaryDirectory() as d:
            r = FakeGit(d).add_origin()
            tip = r.main_tip()
            self.assertEqual(git(r.path, "rev-parse", "refs/remotes/origin/main"), tip)
            self.assertEqual(git(r.path, "rev-list", "--count", "refs/heads/main..refs/remotes/origin/main"), "0")
            r.origin_ahead()
            self.assertEqual(git(r.path, "rev-list", "--count", "refs/heads/main..refs/remotes/origin/main"), "1")
            wt = Path(d) / "repo-worktrees" / "g-0001-t-01"
            git(r.path, "worktree", "add", "-b", "umwayi/g-0001-t-01", str(wt), "main")
            self.assertIn(os.path.realpath(wt), r.worktrees())
            git(r.path, "worktree", "remove", str(wt))
            self.assertNotIn("g-0001-t-01", r.worktrees())


if __name__ == "__main__":
    unittest.main()
