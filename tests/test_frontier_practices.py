"""W10: docs/frontier-practices.md, the tracker of the ten frontier engineering practices.

Checks form and that evidence exists, never that a state is true. On the real doc, and on planted faults:
- exactly the ten numbers 1 to 10, none missing, none twice, and the ten titles in order;
- a state that is one of Covered, Partly covered, Not covered, Not applicable;
- every evidence item is an existing regular file of the repo or `guidance:ID` with an ID in guidance.yaml;
- a gap that is one non-empty line, and no em dash.
Standard library only (guidance.yaml is read with the repo's own loader).
"""

import re
import unittest
from pathlib import Path

from umwayi import guidance

REPO = Path(__file__).resolve().parents[1]
DOC = REPO / "docs" / "frontier-practices.md"
STATES = ("Covered", "Partly covered", "Not covered", "Not applicable")
HEADER = ["Number", "Practice", "State", "Evidence", "Gap"]
TITLES = (
    "You are the architect, not the typist",
    "Maximize agent time, minimize your involvement",
    "Build your codebase for agents",
    "Give agents a fast feedback loop",
    "Execution is cheap. Direction is everything.",
    "Treat code as disposable",
    "Hold AI output to human standards",
    "Trust the boundaries, not the agent",
    "Use agents for everything, not just code",
    "Continuously tune your agent setup",
)
_ITEM = re.compile(r"`([^`]+)`|(guidance:[A-Za-z0-9_-]+)")


def table_rows(text: str) -> list:
    """Cells of every row of the first table that has the header, header and separator left out."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.strip().startswith("|") and cells == HEADER:
            rows = []
            for row in lines[i + 2:]:
                if not row.strip().startswith("|"):
                    break
                rows.append([c.strip() for c in row.strip().strip("|").split("|")])
            return rows
    return []


def evidence_items(cell: str) -> list:
    return [m.group(1) or m.group(2) for m in _ITEM.finditer(cell)]


def problems(text: str, root: Path, ids: set) -> list:
    out = []
    rows = table_rows(text)
    if not rows:
        return ["no table with the header"]
    seen = []
    for cells in rows:
        if len(cells) != 5:
            out.append(f"a row has {len(cells)} columns")
            continue
        num, practice, state, evidence, gap = cells
        if not num.isdigit() or not 1 <= int(num) <= 10:
            out.append(f"bad number {num!r}")
            continue
        n = int(num)
        if n in seen:
            out.append(f"row {n} twice")
        seen.append(n)
        if practice != TITLES[n - 1]:
            out.append(f"row {n}: practice is not the title")
        if state not in STATES:
            out.append(f"row {n}: state {state!r}")
        items = evidence_items(evidence)
        if not items:
            out.append(f"row {n}: no evidence")
        for item in items:
            if item.startswith("guidance:"):
                if item[len("guidance:"):] not in ids:
                    out.append(f"row {n}: unknown guidance id {item}")
            else:
                p = root / item
                if ".." in Path(item).parts or Path(item).is_absolute() or not p.is_file():
                    out.append(f"row {n}: no file {item}")
        if not gap or "\u2014" in gap:
            out.append(f"row {n}: bad gap")
    for n in range(1, 11):
        if n not in seen:
            out.append(f"row {n} missing")
    return out


class FrontierPracticesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")
        cls.ids = {e.id for e in guidance.load(REPO)}

    def check(self, text):
        return problems(text, REPO, self.ids)

    def test_the_real_doc_passes(self):
        self.assertEqual(self.check(self.text), [])

    def test_there_are_ten_rows_in_order(self):
        self.assertEqual([r[0] for r in table_rows(self.text)], [str(i) for i in range(1, 11)])

    def test_no_em_dash(self):
        self.assertNotIn("\u2014", self.text)

    def test_the_note_says_it_is_the_builders_reading(self):
        self.assertIn("builder's reading", self.text)
        self.assertIn("for the owner to review", self.text)

    def test_a_missing_row_fails(self):
        lines = [ln for ln in self.text.split("\n") if not ln.startswith("| 7 |")]
        self.assertIn("row 7 missing", self.check("\n".join(lines)))

    def test_a_duplicated_row_fails(self):
        row = next(ln for ln in self.text.split("\n") if ln.startswith("| 3 |"))
        self.assertIn("row 3 twice", self.check(self.text.replace(row, row + "\n" + row)))

    def test_a_bad_state_fails(self):
        bad = self.text.replace("| Not covered |", "| Done |")
        self.assertTrue(any("state" in p for p in self.check(bad)))

    def test_a_missing_file_fails(self):
        bad = self.text.replace("`tools/ci_shards.py`", "`tools/no_such_file.py`")
        self.assertTrue(any("no file tools/no_such_file.py" in p for p in self.check(bad)))

    def test_a_directory_is_not_a_file(self):
        bad = self.text.replace("`tools/ci_shards.py`", "`tools`")
        self.assertTrue(any("no file tools" in p for p in self.check(bad)))

    def test_an_unknown_guidance_id_fails(self):
        bad = self.text.replace("guidance:rewrite-broken-base", "guidance:no-such-id")
        self.assertTrue(any("unknown guidance id" in p for p in self.check(bad)))

    def test_empty_evidence_and_empty_gap_fail(self):
        row = next(ln for ln in self.text.split("\n") if ln.startswith("| 6 |"))
        cells = row.strip().strip("|").split("|")
        no_evidence = "|" + "|".join(cells[:3] + [" "] + cells[4:]) + "|"
        no_gap = "|" + "|".join(cells[:4] + [" "]) + "|"
        self.assertTrue(any("no evidence" in p for p in self.check(self.text.replace(row, no_evidence))))
        self.assertTrue(any("bad gap" in p for p in self.check(self.text.replace(row, no_gap))))

    def test_a_changed_title_fails(self):
        bad = self.text.replace("Treat code as disposable", "Treat code as precious")
        self.assertTrue(any("not the title" in p for p in self.check(bad)))

    def test_a_text_with_no_table_fails(self):
        self.assertEqual(self.check("nothing here"), ["no table with the header"])


if __name__ == "__main__":
    unittest.main()
