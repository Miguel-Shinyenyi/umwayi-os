"""F4a: every KNOWN-LIMITS number is used once.

The docs builder already refuses a part that repeats a number or leaves a gap, but two pull requests that each took the next free number
merged in turn on one day (333 to 343 were taken by several branches at once). This test reads the real tree and fails when a number
appears twice among the limits parts, twice among the headings of docs/KNOWN-LIMITS.md, or when the two lists differ. The planted faults
run the same function on a made-up list.
"""
import re
import unittest
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HEADING = re.compile(r"(?m)^### (\d+)\.")
NUMBER = re.compile(r"(?m)^number:\s*(\d+)\s*$")


def duplicates(numbers) -> list:
    return sorted(n for n, c in Counter(numbers).items() if c > 1)


def part_numbers(root: Path) -> list:
    out = []
    for p in sorted((root / "docs-parts" / "known-limits").glob("*.md")):
        m = NUMBER.search(p.read_text(encoding="utf-8").split("\n\n", 1)[0])
        if m:
            out.append(int(m.group(1)))
    return out


def heading_numbers(root: Path) -> list:
    return [int(n) for n in HEADING.findall((root / "docs" / "KNOWN-LIMITS.md").read_text(encoding="utf-8"))]


class RealTreeTests(unittest.TestCase):
    def test_no_number_is_used_twice_among_the_parts(self):
        self.assertEqual(duplicates(part_numbers(REPO)), [])

    def test_no_number_is_used_twice_among_the_headings_of_known_limits(self):
        self.assertEqual(duplicates(heading_numbers(REPO)), [])

    def test_every_part_number_is_a_heading_of_known_limits(self):
        self.assertEqual(sorted(set(part_numbers(REPO)) - set(heading_numbers(REPO))), [])

    def test_the_newest_numbers_are_held_once_each_and_without_a_gap(self):
        parts = sorted(part_numbers(REPO))
        top = parts[-14:]
        self.assertEqual(top, list(range(top[0], top[0] + len(top))))


class PlantedFaultTests(unittest.TestCase):
    def test_a_duplicate_is_found(self):
        self.assertEqual(duplicates([340, 341, 341, 342]), [341])
        self.assertEqual(duplicates([340, 341, 342]), [])

    def test_a_copy_of_the_tree_with_a_planted_duplicate_fails(self):
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            shutil.copytree(REPO / "docs-parts" / "known-limits", root / "docs-parts" / "known-limits")
            first = sorted((root / "docs-parts" / "known-limits").glob("*.md"))
            numbered = [p for p in first if NUMBER.search(p.read_text(encoding="utf-8"))]
            a, b = numbered[-1], numbered[-2]
            b.write_text(NUMBER.sub(NUMBER.search(a.read_text(encoding="utf-8")).group(0), b.read_text(encoding="utf-8"), count=1), encoding="utf-8")
            self.assertEqual(len(duplicates(part_numbers(root))), 1)


if __name__ == "__main__":
    unittest.main()
