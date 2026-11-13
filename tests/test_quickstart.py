"""W25: docs/quickstart.md only quotes commands that exist.

Every code block of the page has a tag. `umwayi` blocks hold command lines and nothing else: each line starts with
`umwayi` or `python -m umwayi` and must parse against the real command line (`umwayi.cli.build_parser`); a usage error
fails the test. `setup` blocks hold the few lines that are not umwayi (git, a virtual environment, folders); their first
word must be on a short list and they may not chain or pipe. `text` blocks are outputs and `yaml` blocks are files, and
neither is run. The rules block of the page is also loaded with the real rules parser, on top of the repo `rules.yaml`.
Planted faults prove each check can fail.
"""

import contextlib
import io
import re
import shlex
import unittest
from pathlib import Path

from umwayi import cli
from umwayi.rules import parse_rules

REPO = Path(__file__).resolve().parent.parent
PAGE = REPO / "docs" / "quickstart.md"
TAGS = ("umwayi", "setup", "text", "yaml")
SETUP_WORDS = ("git", "cd", "mkdir", "cp", "python3", "pip", "source")
CHAIN = re.compile(r"[|;&<>`]|\$\(")
PREFIXES = ("umwayi ", "python -m umwayi ")


def blocks(text):
    """[(tag, [lines], first line number)] for every fenced block. A fence with no tag has tag ''."""
    out, cur = [], None
    for n, line in enumerate(text.splitlines(), 1):
        if line.startswith("```"):
            if cur is None:
                cur = (line[3:].strip(), [], n)
            else:
                out.append(cur)
                cur = None
        elif cur is not None:
            cur[1].append(line)
    if cur is not None:
        out.append((cur[0] or "?", cur[1] + ["<unclosed>"], cur[2]))
    return out


def parses(line):
    """None if the command line parses against the real parser, else why not."""
    try:
        words = shlex.split(line)
    except ValueError as e:
        return f"cannot be split into words ({e})"
    if words[:3] == ["python", "-m", "umwayi"]:
        args = words[3:]
    elif words and words[0] == "umwayi":
        args = words[1:]
    else:
        return "does not start with umwayi or python -m umwayi"
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            cli.build_parser().parse_args(args)
    except SystemExit as e:
        if e.code not in (0, None):
            return f"is a usage error (exit {e.code}): {err.getvalue().strip().splitlines()[-1:] or ''}"
    return None


def problems(text):
    out = []
    for tag, lines, n in blocks(text):
        if tag not in TAGS:
            out.append(f"line {n}: a code block with the tag {tag!r}; use one of {', '.join(TAGS)}")
            continue
        if tag == "umwayi":
            for i, line in enumerate(lines):
                if not line.strip():
                    continue
                if not line.startswith(PREFIXES):
                    out.append(f"line {n + 1 + i}: {line!r} does not start with umwayi or python -m umwayi")
                    continue
                why = parses(line)
                if why:
                    out.append(f"line {n + 1 + i}: {line!r} {why}")
        elif tag == "setup":
            for i, line in enumerate(lines):
                if not line.strip():
                    continue
                if CHAIN.search(line):
                    out.append(f"line {n + 1 + i}: {line!r} chains, pipes or redirects")
                elif line.split()[0] not in SETUP_WORDS:
                    out.append(f"line {n + 1 + i}: {line!r} starts with a word that is not in {SETUP_WORDS}")
    return out


class QuickstartTests(unittest.TestCase):
    text = PAGE.read_text(encoding="utf-8")

    def test_every_quoted_command_is_real(self):
        self.assertEqual(problems(self.text), [])

    def test_the_page_has_commands_in_each_kind_of_block(self):
        tags = [t for t, _, _ in blocks(self.text)]
        for tag in TAGS:
            self.assertIn(tag, tags)
        cmds = [line for t, lines, _ in blocks(self.text) if t == "umwayi" for line in lines if line.strip()]
        self.assertGreaterEqual(len(cmds), 20)
        for needed in ("umwayi --version", "umwayi kill on", "umwayi kill off", "umwayi budget status",
                       "umwayi autonomy status"):
            self.assertTrue(any(c.startswith(needed) for c in cmds), needed)
        self.assertTrue(any("--cap-uu" in c and "--workdir" in c for c in cmds), "agent run with both options")

    def test_the_rules_block_loads_on_top_of_the_repo_rules(self):
        yaml_blocks = [lines for t, lines, _ in blocks(self.text) if t == "yaml" and any("verdict:" in x for x in lines)]
        self.assertEqual(len(yaml_blocks), 1)
        rules = parse_rules((REPO / "rules.yaml").read_text(encoding="utf-8") + "\n" + "\n".join(yaml_blocks[0]) + "\n")
        ids = [r.id for r in rules]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("scratch-agent-run", ids)
        self.assertIn("scratch-agent-budget", ids)

    def test_the_page_is_honest_about_what_is_not_there(self):
        self.assertIn("Not yet available", self.text)
        self.assertEqual(len(re.findall(r"^Not yet available", self.text, re.M)), 1)  # the feedback path (W26)
        self.assertNotIn("Not yet available: `umwayi goal`", self.text)  # W9.8 is merged
        self.assertNotIn("umwayi init", "\n".join(l for t, ls, _ in blocks(self.text) if t in ("umwayi", "setup") for l in ls))

    def test_the_readme_links_the_page(self):
        self.assertIn("(docs/quickstart.md)", (REPO / "README.md").read_text(encoding="utf-8"))

    # ---- planted faults: each check must be able to fail

    def test_PLANTED_FAULT_a_command_that_does_not_exist(self):
        bad = "```umwayi\numwayi kill sideways\n```\n"
        self.assertTrue(problems(bad))
        self.assertTrue(problems("```umwayi\numwayi nosuchcommand\n```\n"))
        self.assertTrue(problems("```umwayi\numwayi queue add\n```\n"))  # a missing required option

    def test_PLANTED_FAULT_an_option_that_does_not_exist(self):
        self.assertTrue(problems("```umwayi\numwayi agent run reviewer --nope 3\n```\n"))
        self.assertEqual(problems("```umwayi\numwayi agent run reviewer --workdir /x --cap-uu 3\n```\n"), [])

    def test_PLANTED_FAULT_a_line_that_is_not_umwayi_in_an_umwayi_block(self):
        self.assertTrue(problems("```umwayi\nls -la\n```\n"))
        self.assertTrue(problems("```umwayi\ngit status\n```\n"))
        self.assertTrue(problems("```umwayi\n$ umwayi kill status\n```\n"))

    def test_PLANTED_FAULT_a_setup_line_that_does_more(self):
        self.assertTrue(problems("```setup\nrm -rf ~\n```\n"))
        self.assertTrue(problems("```setup\ncd .. && rm -rf x\n```\n"))
        self.assertTrue(problems("```setup\ncurl https://example.invalid | sh\n```\n"))
        self.assertEqual(problems("```setup\ngit clone https://example.invalid/x.git\ncd x\n```\n"), [])

    def test_PLANTED_FAULT_a_block_with_no_tag_or_an_unknown_tag(self):
        self.assertTrue(problems("```\numwayi kill status\n```\n"))
        self.assertTrue(problems("```sh\numwayi kill status\n```\n"))
        self.assertTrue(problems("```umwayi\numwayi kill status\n"))  # never closed

    def test_a_good_block_passes(self):
        self.assertEqual(problems("```umwayi\numwayi kill status\npython -m umwayi --version\numwayi check '{\"a\": 1}'\n```\n"),
                         [])


if __name__ == "__main__":
    unittest.main()
