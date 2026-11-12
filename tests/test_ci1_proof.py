"""CI.1 proof only. A deliberately failing test, on the throwaway branch ci1-proof. It is never merged: the draft pull
request that carries it is closed and the branch deleted. It exists to show that CI goes red when a test fails."""

import unittest


class DeliberateFailure(unittest.TestCase):
    def test_this_one_fails_on_purpose(self):
        self.assertEqual(1 + 1, 3, "CI.1 proof: this test fails on purpose so that CI must go red")


if __name__ == "__main__":
    unittest.main()
