"""Seeded generators, the property runner and the shrinker for the goal tests (W9.1, W9.R21.3).

Standard library only. Every random choice comes from `random.Random(seed)` through `getrandbits` and `random()`
only, which give the same numbers on Python 3.10 to 3.13, so a fixed seed gives the same cases everywhere.

A property runs 5000 cases for each of three fixed seeds and one fresh seed. The fresh seed is printed. On a failure
the seed, the case number and the shrunk case are in the message, so the failure can be replayed.
"""

import random
import string
import sys
import time

FIXED_SEEDS = (1, 2, 3)
CASES = 5000
FRESH_SEED = int(time.time() * 1000) % 2_000_000_000
SEEDS = FIXED_SEEDS + (FRESH_SEED,)
print(f"tests.goal.gen: fresh seed {FRESH_SEED}", file=sys.stderr)

PRINTABLE = string.ascii_letters + string.digits + " .,:;-_/()"
HEX = "0123456789abcdef"


class Gen:
    """The one source of randomness. Only getrandbits and random() are used."""

    def __init__(self, seed):
        self.seed = seed
        self.r = random.Random(seed)

    def bits(self, n):
        return self.r.getrandbits(n)

    def rand(self):
        return self.r.random()

    def below(self, n):
        if n <= 1:
            return 0
        k = (n - 1).bit_length()
        while True:
            v = self.r.getrandbits(k)
            if v < n:
                return v

    def between(self, lo, hi):
        return lo + self.below(hi - lo + 1)

    def pick(self, seq):
        seq = list(seq)
        return seq[self.below(len(seq))]

    def chance(self, p):
        return self.r.random() < p

    def text(self, alphabet, lo, hi):
        return "".join(self.pick(alphabet) for _ in range(self.between(lo, hi)))

    def hex(self, n):
        return self.text(HEX, n, n)

    def data(self, lo, hi):
        return bytes(self.bits(8) for _ in range(self.between(lo, hi)))

    def shuffled(self, seq):
        seq = list(seq)
        for i in range(len(seq) - 1, 0, -1):
            j = self.below(i + 1)
            seq[i], seq[j] = seq[j], seq[i]
        return seq

    def sentence(self, lo=10, hi=60):
        n = self.between(lo, hi)
        words = []
        while sum(len(w) + 1 for w in words) < n:
            words.append(self.text(string.ascii_lowercase, 2, 8))
        s = " ".join(words)[:n].strip()
        while len(s) < lo:
            s += "x"
        return s

    def path(self):
        parts = [self.text(string.ascii_lowercase + "_-", 1, 8) for _ in range(self.between(1, 3))]
        return "/".join(parts) + self.pick([".py", ".md", ".json", ""])

    def json_value(self, depth=0):
        k = self.below(7 if depth < 4 else 5)
        if k == 0:
            return None
        if k == 1:
            return self.chance(0.5)
        if k == 2:
            return self.between(-5, 100000)
        if k == 3:
            return self.text(PRINTABLE + "\n\t\u00e9\u2014", 0, 20)
        if k == 4:
            return self.rand()
        if k == 5:
            return [self.json_value(depth + 1) for _ in range(self.below(4))]
        return {self.text(string.ascii_lowercase, 1, 6): self.json_value(depth + 1) for _ in range(self.below(4))}


def shrink(value, failing, limit=2000):
    """Make `value` smaller while `failing(value)` stays true. Works on str, bytes, list, tuple, dict and int."""
    steps = 0
    changed = True
    while changed and steps < limit:
        changed = False
        for cand in _smaller(value):
            steps += 1
            if steps >= limit:
                break
            try:
                bad = failing(cand)
            except Exception:
                bad = True
            if bad:
                value, changed = cand, True
                break
    return value


def _smaller(v):
    if isinstance(v, (str, bytes, list, tuple)) and len(v) > 0:
        n = len(v)
        yield v[: n // 2]
        yield v[n // 2:]
        for i in range(min(n, 40)):
            yield v[:i] + v[i + 1:]
    elif isinstance(v, dict) and v:
        for k in list(v)[:40]:
            yield {kk: vv for kk, vv in v.items() if kk != k}
    elif isinstance(v, int) and not isinstance(v, bool) and v != 0:
        yield 0
        yield v // 2


def run_property(test, make, check, cases=CASES, seeds=SEEDS, shrinkable=True):
    """For each seed, make `cases` cases with `make(gen)` and require `check(case)` to be true (or to return None).

    A False result or an exception is a failure; the message holds the seed, the case number and the shrunk case.
    """
    for seed in seeds:
        g = Gen(seed)
        for i in range(cases):
            case = make(g)
            if _bad(check, case):
                small = shrink(case, lambda c: _bad(check, c)) if shrinkable else case
                test.fail(f"property failed: seed {seed}, case {i}, shrunk case {small!r}")


def _bad(check, case):
    try:
        return check(case) is False
    except Exception:
        return True
