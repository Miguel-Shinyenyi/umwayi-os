"""G8g: docs/lessons-as-checks.md lists each of the lessons A1 to A14, and every check it names is real.

The page is the map. This test reads its table and fails when: a lesson is missing or listed twice; a row is neither `check:` nor
`text only:` with a reason; a check names a test file that does not exist or a name that is not in that file; or fewer than ten lessons
are checks (the fixes note recommended at least ten of the fourteen).
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PAGE = REPO / "docs" / "lessons-as-checks.md"
IDS = [f"A{n}" for n in range(1, 15)]
MIN_CHECKS = 10


def rows(text: str) -> list:
    """(id, kind, rest) for each table row whose first cell is A1 to A99."""
    out = []
    for line in text.split("\n"):
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.startswith("| A") else []
        if len(cells) >= 3 and re.fullmatch(r"A\d+", cells[0]):
            cell = "|".join(cells[2:])
            kind = "check" if cell.startswith("check:") else "text only" if cell.startswith("text only:") else "bad"
            out.append((cells[0], kind, cell.split(":", 1)[1].strip() if ":" in cell else ""))
    return out


def problems(text: str, root: Path = REPO) -> list:
    got, found = rows(text), []
    ids = [r[0] for r in got]
    for i in IDS:
        if ids.count(i) != 1:
            found.append(f"{i} is listed {ids.count(i)} times, not once")
    for i in sorted(set(ids) - set(IDS)):
        found.append(f"{i} is not one of A1 to A14")
    for lesson, kind, rest in got:
        if kind == "bad":
            found.append(f"{lesson}: the last cell starts with neither `check:` nor `text only:`")
        elif kind == "text only" and len(rest) < 20:
            found.append(f"{lesson}: a text only lesson needs its reason")
        elif kind == "check":
            tokens = re.findall(r"`([^`]+)`", rest)
            files = [t for t in tokens if t.endswith(".py")]
            if not files:
                found.append(f"{lesson}: a check names no test file")
                continue
            path = root / files[0]
            if not path.is_file():
                found.append(f"{lesson}: {files[0]} does not exist")
                continue
            body = path.read_text(encoding="utf-8")
            for name in [t for t in tokens if t != files[0] and re.fullmatch(r"\w+", t)]:
                if name not in body:
                    found.append(f"{lesson}: `{name}` is not in {files[0]}")
    if sum(1 for r in got if r[1] == "check") < MIN_CHECKS:
        found.append(f"fewer than {MIN_CHECKS} lessons are checks")
    return found


class MapTests(unittest.TestCase):
    def test_the_real_page_has_no_problem(self):
        self.assertEqual(problems(PAGE.read_text(encoding="utf-8")), [])

    def test_planted_fault_a_check_with_a_name_that_is_not_in_the_file_is_found(self):
        text = PAGE.read_text(encoding="utf-8").replace("TestingMdMarginTests", "TestingMdNoSuchTests", 1)
        self.assertEqual(problems(text), ["A1: `TestingMdNoSuchTests` is not in tests/test_docs.py"])

    def test_planted_fault_a_missing_lesson_a_missing_file_and_a_reasonless_text_only_are_found(self):
        text = PAGE.read_text(encoding="utf-8")
        cut = "\n".join(l for l in text.split("\n") if not l.startswith("| A13 "))
        self.assertIn("A13 is listed 0 times, not once", problems(cut))
        self.assertIn("A2: tests/test_nonexistent.py does not exist", problems(text.replace("tests/test_ci_shards.py", "tests/test_nonexistent.py", 1)))
        short = re.sub(r"(\| A9 \|[^|]*\| )text only:[^|]*\|", r"\1text only: n/a |", text)
        self.assertIn("A9: a text only lesson needs its reason", problems(short))

    def test_planted_fault_fewer_than_ten_checks_are_found(self):
        text = PAGE.read_text(encoding="utf-8").replace("| check: `tests/test_docs.py`", "| text only: this one was changed to text for the test only", 1)
        self.assertIn("fewer than 10 lessons are checks", problems(text))


if __name__ == "__main__":
    unittest.main()
