"""G4: a statement in a front page that the code has outgrown fails the build.

The stale statement check of PR 167 was a search by hand. This test makes two parts of it code: (1) a list of phrases that were true once and
are not now, searched in README.md and docs/what-it-is.md; (2) for every row of the README status table that says "not built", the command
it names (`umwayi X`) must not be a command that the parser has. The planted faults run the same functions on made-up text.
"""
import re
import unittest
from pathlib import Path

from umwayi import cli

REPO = Path(__file__).resolve().parent.parent
# (regex, why it is stale): add a line here when a statement stops being true
STALE = (
    (r"only the docs builder `umwayi goal docs build`", "goal orchestration is built beyond the docs builder (W9.7 and later)"),
    (r"comes after the freeze", "the freeze is a date, not a reason a feature is missing"),
    (r"goal orchestration[^.|]*is not built", "goal orchestration is built"),
)
COMMAND = re.compile(r"`umwayi (\w+)")


def stale_phrases(name: str, text: str) -> list:
    return [f"{name}: {why}" for rx, why in STALE if re.search(rx, text, re.I)]


def parser_commands() -> set:
    p = cli.build_parser()
    return set(next(a for a in p._actions if getattr(a, "choices", None) and "check" in a.choices).choices)


def not_built_rows_for_a_command_that_exists(text: str, commands: set) -> list:
    """README table rows whose status cell begins "not built", "specified" or "designed" for a command the parser has."""
    out = []
    for line in text.split("\n"):
        cells = [c.strip() for c in line.split("|")]
        if line.startswith("|") and len(cells) > 3 and re.match(r"(not built|specified|designed|spec only)\b", cells[2], re.I):
            for name in sorted(set(COMMAND.findall(line)) & commands):
                out.append(f"README row says `{cells[2][:30]}` but `umwayi {name}` exists: {line[:50]}")
    return out


class RealTreeTests(unittest.TestCase):
    def test_the_front_pages_hold_no_stale_phrase(self):
        for name in ("README.md", "docs/what-it-is.md"):
            self.assertEqual(stale_phrases(name, (REPO / name).read_text(encoding="utf-8")), [])

    def test_no_readme_row_says_not_built_for_a_command_the_parser_has(self):
        self.assertEqual(not_built_rows_for_a_command_that_exists((REPO / "README.md").read_text(encoding="utf-8"), parser_commands()), [])

    def test_the_parser_commands_are_read(self):
        self.assertIn("goal", parser_commands())
        self.assertIn("check", parser_commands())


class PlantedFaultTests(unittest.TestCase):
    def test_the_old_goal_line_is_found(self):
        old = "| Goal orchestration (W9), `umwayi goal` | specified Nov 12 (W9.0); only the docs builder `umwayi goal docs build` is built; the rest comes after the freeze | [goals](docs/goals.md) |"
        found = stale_phrases("README.md", old)
        self.assertEqual(len(found), 2, found)
        self.assertEqual(len(not_built_rows_for_a_command_that_exists(old, {"goal"})), 1)

    def test_a_true_line_is_not_found(self):
        ok = "| Goal orchestration (W9), `umwayi goal` | built; tested with fakes |"
        self.assertEqual(stale_phrases("README.md", ok), [])
        self.assertEqual(not_built_rows_for_a_command_that_exists(ok, {"goal"}), [])


if __name__ == "__main__":
    unittest.main()
