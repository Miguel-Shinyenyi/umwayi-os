"""Documentation layout (tasks.md D.1): the short README, PROJECT.md and one doc per component under docs/.

Checks, on the repo and on temporary copies with a planted fault each:
- every relative link in README.md, PROJECT.md and every docs/*.md resolves to a file in the repo, and an #anchor to a
  heading of that file (headings are read outside code blocks only, with GitHub's way of making an anchor);
- README.md is at most 120 lines;
- no em dash in README.md, PROJECT.md or any file under docs/;
- every component doc has the four parts in order (Purpose, Current state, Decisions log, Open questions) and is under
  300 lines;
- every doc under docs/ can be reached by links from README.md or PROJECT.md (nothing that cannot be traced).
Standard library only; no network: links to http and https pages are not fetched.
"""

import re
import shutil
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
README_MAX_LINES = 120
DOC_MAX_LINES = 300  # a doc must have fewer lines than this
EM_DASH = "\u2014"
PARTS = ("Purpose", "Current state", "Decisions log", "Open questions")
# docs/ files that are not component docs: they keep their own shape
NOT_COMPONENT = {"KNOWN-LIMITS.md", "DOCS_MAINTENANCE.md", "SECURITY-SCAN.md"}
REQUIRED = ("memory.md", "rules.md", "queue.md", "archive.md", "logbook.md", "automation.md", "helpers.md",
            "workflows.md", "adapters.md", "agent-front-door.md", "scheduled-runs.md", "budget-governor.md",
            "exit-codes.md", "architecture.md", "testing.md", "security.md", "status-log.md", "schedule.md",
            "DOCS_MAINTENANCE.md", "KNOWN-LIMITS.md")

_FENCE = re.compile(r"^\s{0,3}(```|~~~)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_CODE_SPAN = re.compile(r"`+[^`]*`+")


def outside_code(text: str) -> list:
    """(line number, line) of every line outside fenced code blocks."""
    out, fence = [], None
    for n, line in enumerate(text.split("\n"), 1):
        m = _FENCE.match(line)
        if m:
            if fence is None:
                fence = m.group(1)
            elif m.group(1) == fence:
                fence = None
            continue
        if fence is None:
            out.append((n, line))
    return out


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: lowercase, markup and punctuation dropped, spaces to hyphens."""
    text = re.sub(r"`([^`]*)`", r"\1", heading)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.strip().lower()
    text = "".join(ch for ch in text if ch.isalnum() or ch in " -_")
    return text.replace(" ", "-")


def anchors(text: str) -> set:
    seen: dict = {}
    out = set()
    for _n, line in outside_code(text):
        m = _HEADING.match(line)
        if not m:
            continue
        base = slug(m.group(2))
        k = seen.get(base, 0)
        out.add(base if k == 0 else f"{base}-{k}")
        seen[base] = k + 1
    return out


def headings(text: str) -> list:
    return [(len(m.group(1)), m.group(2)) for _n, line in outside_code(text) for m in [_HEADING.match(line)] if m]


def links(text: str) -> list:
    """(line number, target) of every Markdown link outside code blocks and code spans."""
    out = []
    for n, line in outside_code(text):
        for m in _LINK.finditer(_CODE_SPAN.sub("", line)):
            out.append((n, m.group(1)))
    return out


def doc_files(root: Path) -> list:
    files = [root / "README.md", root / "PROJECT.md"]
    files += sorted(p for p in (root / "docs").rglob("*.md"))
    return [p for p in files if p.exists()]


def check(root: Path) -> list:
    """Every problem of the documentation under root, as text. Empty when all is well."""
    root = Path(root).resolve()
    problems = []
    for name in ("README.md", "PROJECT.md"):
        if not (root / name).is_file():
            problems.append(f"{name} is missing")
    for name in REQUIRED:
        if not (root / "docs" / name).is_file():
            problems.append(f"docs/{name} is missing")
    texts = {p.resolve(): p.read_text(encoding="utf-8") for p in doc_files(root)}
    readme = root / "README.md"
    if readme in texts:
        count = len(texts[readme].rstrip("\n").split("\n"))
        if count > README_MAX_LINES:
            problems.append(f"README.md has {count} lines, more than {README_MAX_LINES}")
    for p, text in texts.items():
        rel = p.relative_to(root).as_posix()
        for n, line in enumerate(text.split("\n"), 1):
            if EM_DASH in line:
                problems.append(f"{rel} line {n}: an em dash")
        for n, target in links(text):
            if re.match(r"^[a-z][a-z0-9+.-]*:", target):  # http, https, mailto: not fetched
                continue
            path, _, anchor = target.partition("#")
            dest = (p.parent / path).resolve() if path else p
            try:
                dest.relative_to(root)
            except ValueError:
                problems.append(f"{rel} line {n}: the link {target} points outside the repo")
                continue
            if not dest.exists():
                problems.append(f"{rel} line {n}: the link {target} does not resolve")
                continue
            if anchor and dest.suffix == ".md" and dest.is_file():
                if anchor not in anchors(dest.read_text(encoding="utf-8")):
                    problems.append(f"{rel} line {n}: the anchor #{anchor} is not a heading of {path or rel}")
        if p.parent == root / "docs" and p.name not in NOT_COMPONENT:
            lines = len(text.rstrip("\n").split("\n"))
            if lines >= DOC_MAX_LINES:
                problems.append(f"{rel} has {lines} lines, not under {DOC_MAX_LINES}")
            found = [h for level, h in headings(text) if level == 2 and h in PARTS]
            if found != list(PARTS):
                problems.append(f"{rel}: the parts are {found}, not {list(PARTS)} in this order")
    # nothing under docs/ that cannot be traced from the README or PROJECT.md
    reached, todo = set(), [readme, root / "PROJECT.md"]
    while todo:
        p = todo.pop()
        if p in reached or p not in texts:
            continue
        reached.add(p)
        for _n, target in links(texts[p]):
            path = target.partition("#")[0]
            if path and not re.match(r"^[a-z][a-z0-9+.-]*:", path):
                todo.append((p.parent / path).resolve())
    for p in texts:
        if p.parent == root / "docs" and p not in reached:
            problems.append(f"{p.relative_to(root).as_posix()} cannot be reached by links from README.md or PROJECT.md")
    return problems


class RepoDocsTests(unittest.TestCase):
    def test_the_documentation_has_no_problem(self):
        self.assertEqual(check(REPO), [])

    def test_the_readme_example_entry_is_not_a_heading(self):
        for p in doc_files(REPO):
            for _level, h in headings(p.read_text(encoding="utf-8")):
                self.assertNotRegex(h, r"^\d{4}-\d{2}-\d{2}$", f"{p.name}: an example entry read as a heading")


class PlantedFaultTests(unittest.TestCase):
    """The checker itself: each planted fault, in a temporary copy, is found. The repo is never changed."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="umwayi-docs-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "repo"
        self.root.mkdir()
        for name in ("README.md", "PROJECT.md"):
            if (REPO / name).exists():
                shutil.copy2(REPO / name, self.root / name)
        if (REPO / "docs").is_dir():
            shutil.copytree(REPO / "docs", self.root / "docs")
        # the targets of links outside the docs, so only the planted fault can fail
        for p in doc_files(REPO):
            for _n, target in links(p.read_text(encoding="utf-8")):
                path = target.partition("#")[0]
                if not path or re.match(r"^[a-z][a-z0-9+.-]*:", path):
                    continue
                src = (p.parent / path).resolve()
                try:
                    rel = src.relative_to(REPO)
                except ValueError:
                    continue
                dest = self.root / rel
                if src.is_file() and not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                elif src.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)

    def plant(self, rel: str, text: str, append: bool = True):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        old = p.read_text(encoding="utf-8") if p.exists() and append else ""
        p.write_text(old + text, encoding="utf-8")

    def assert_found(self, fragment: str):
        problems = check(self.root)
        self.assertTrue(any(fragment in x for x in problems), f"{fragment!r} not in {problems}")

    def test_the_copy_is_clean_before_any_plant(self):
        self.assertEqual(check(self.root), [])

    def test_a_broken_link(self):
        self.plant("docs/memory.md", "\nSee [nothing](no-such-file.md).\n")
        self.assert_found("the link no-such-file.md does not resolve")

    def test_an_anchor_that_does_not_exist(self):
        self.plant("docs/memory.md", "\nSee [nothing](rules.md#no-such-heading).\n")
        self.assert_found("the anchor #no-such-heading is not a heading of rules.md")

    def test_a_link_inside_a_code_block_is_not_checked(self):
        self.plant("docs/memory.md", "\n```\n[x](no-such-file.md)\n```\n")
        self.assertEqual(check(self.root), [])

    def test_a_readme_of_121_lines(self):
        text = (self.root / "README.md").read_text(encoding="utf-8").rstrip("\n").split("\n")
        self.plant("README.md", "\n".join(text + ["x"] * (README_MAX_LINES + 1 - len(text))) + "\n", append=False)
        self.assert_found(f"README.md has {README_MAX_LINES + 1} lines")

    def test_an_em_dash(self):
        for rel in ("README.md", "PROJECT.md", "docs/rules.md", "docs/KNOWN-LIMITS.md"):
            with self.subTest(rel=rel):
                self.plant(rel, "\nA line with an em dash " + EM_DASH + " here.\n")
                self.assert_found(f"{rel} line ")

    def test_a_doc_of_300_lines(self):
        text = (self.root / "docs" / "queue.md").read_text(encoding="utf-8").rstrip("\n").split("\n")
        self.plant("docs/queue.md", "\n".join(text + ["x"] * (DOC_MAX_LINES - len(text))) + "\n", append=False)
        self.assert_found(f"docs/queue.md has {DOC_MAX_LINES} lines")

    def test_a_doc_missing_one_of_the_four_parts(self):
        for part in PARTS:
            with self.subTest(part=part):
                p = self.root / "docs" / "archive.md"
                original = p.read_text(encoding="utf-8")
                p.write_text(original.replace(f"\n## {part}\n", "\n## Something else\n"), encoding="utf-8")
                self.assert_found("docs/archive.md: the parts are")
                p.write_text(original, encoding="utf-8")

    def test_a_doc_nothing_links_to(self):
        self.plant("docs/orphan.md", "# Orphan\n\n## Purpose\n\nx\n\n## Current state\n\nx\n\n## Decisions log\n\n"
                                     "x\n\n## Open questions\n\nx\n", append=False)
        self.assert_found("docs/orphan.md cannot be reached")

    def test_a_missing_required_doc(self):
        (self.root / "docs" / "schedule.md").unlink()
        self.assert_found("docs/schedule.md is missing")


class SlugTests(unittest.TestCase):
    def test_github_anchors(self):
        self.assertEqual(slug("Layer 9: adapters"), "layer-9-adapters")
        self.assertEqual(slug("The `budget_check` rule"), "the-budget_check-rule")
        self.assertEqual(slug("Decisions log"), "decisions-log")
        self.assertEqual(anchors("# A\n## A\n```\n## B\n```\n"), {"a", "a-1"})


if __name__ == "__main__":
    unittest.main()
