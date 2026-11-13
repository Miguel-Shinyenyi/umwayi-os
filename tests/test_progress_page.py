"""W8 slice: the progress page ui/dist/progress.html cannot go stale, and it stays read only.

It is built by `node build.mjs` from three files: docs/status-log.md, docs/KNOWN-LIMITS.md and the tasks.md of the spec.
ui/dist/build.json holds the SHA-256 of what the page shows (the group counts, the ten rows, the highest limit number) and of
the page. A second reader here works the same string out of the three files. These tests fail when:
- what the page shows changed in a source since the page was built, or the page was edited by hand (run the build); a change to
  other lines of the sources does not make it stale,
- the page has a script, a form, a link, a request or a policy that is not default-src 'none'.
Standard library only, no npm. A matching hash shows the build was run after the last change of what the page shows; it does not show the
page text is right for it, because only the build renders it.
"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PAGE = REPO / "ui" / "dist" / "progress.html"
BUILD = REPO / "ui" / "dist" / "build.json"
STATUS, TASKS, LIMITS = "docs/status-log.md", ".kiro/specs/umwayi-os/tasks.md", "docs/KNOWN-LIMITS.md"
FORBIDDEN = re.compile(r"<script|<form|<input|<button|<textarea|<select|<link|<img|<iframe|\bsrc\s*=|\bhref\s*=|fetch\(|"
                       r"XMLHttpRequest|https?://|@import|url\(", re.I)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# A second reader of the three sources, written apart from ui/src/data/progress.js. It must give the same string as the build
# (progress.shown), so a difference between the two readers also shows here as a stale page.
def read_limit(text: str) -> int:
    return max([0] + [int(m.group(1)) for m in re.finditer(r"^### (\d+)\.", text, re.M)])


def read_rows(text: str) -> list:
    rows = []
    for line in text.split("\n"):
        if not line.startswith("| "):
            continue
        body = re.sub(r"\s*\|\s*$", "", re.sub(r"^\|\s*", "", line))
        cells = re.split(r"\s\|\s", body)
        if len(cells) < 3 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cells[0].strip()):
            continue
        rows.append({"date": cells[0].strip(), "pr": cells[1].strip(), "what": cells[2].strip()})
    return rows[:10]


def read_groups(text: str) -> list:
    groups, cur = [], None
    for line in text.split("\n"):
        h = re.match(r"## (.+?)\s*$", line)
        if h:
            name = re.sub(r":$", "", re.sub(r"\s+\(.*$", "", h.group(1)))
            cur = {"name": name, "done": 0, "open": 0}
            groups.append(cur)
            continue
        t = re.match(r"\s*- \[([ xX])\]", line)
        if t and cur is not None:
            cur["open" if t.group(1) == " " else "done"] += 1
    return [g for g in groups if g["done"] + g["open"] > 0]


def shown(root: Path) -> str:
    """What the page shows, from the three files: the group counts, the ten rows and the highest limit number."""
    read = lambda name: (root / name).read_text(encoding="utf-8")  # noqa: E731
    model = {"groups": read_groups(read(TASKS)), "rows": read_rows(read(STATUS)), "limit": read_limit(read(LIMITS))}
    return json.dumps(model, separators=(",", ":"), ensure_ascii=False)


def stale(build: dict, root: Path, page: Path) -> list:
    problems = []
    try:
        now = sha(shown(root).encode("utf-8"))
    except OSError as e:
        return [f"a source of the progress page cannot be read: {e}"]
    if build.get("progressShown") != now:
        problems.append("what the sources show (group counts, ten status rows, highest limit) changed since "
                        "ui/dist/progress.html was built (run node build.mjs in ui)")
    if not page.is_file():
        problems.append("ui/dist/progress.html is missing")
    elif build.get("progressPage") != sha(page.read_bytes()):
        problems.append("ui/dist/progress.html is not the page that was built (edited by hand, or not rebuilt)")
    return problems


def rule_problems(html: str) -> list:
    problems = [f"the page contains {m.group(0)!r}" for m in FORBIDDEN.finditer(html)]
    if "\u2014" in html:
        problems.append("the page contains an em dash")
    if not re.search(r"default-src 'none'; style-src 'sha256-[^']+'; base-uri 'none'; form-action 'none'", html):
        problems.append("the page policy is not default-src 'none' plus one style hash")
    return problems


class ProgressPageTests(unittest.TestCase):
    def setUp(self):
        self.build = json.loads(BUILD.read_text(encoding="utf-8"))

    def test_the_page_is_the_one_built_from_the_sources_now(self):
        self.assertEqual(stale(self.build, REPO, PAGE), [])

    def test_the_page_follows_the_page_rules(self):
        self.assertEqual(rule_problems(PAGE.read_text(encoding="utf-8")), [])

    def test_the_page_says_when_it_was_built(self):
        self.assertRegex(PAGE.read_text(encoding="utf-8"), r"Built on \d{4}-\d{2}-\d{2}\.")

    def copy_sources(self, root: Path):
        for name in (STATUS, TASKS, LIMITS):
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_bytes((REPO / name).read_bytes())

    def edit(self, root: Path, name: str, fn):
        path = root / name
        path.write_text(fn(path.read_text(encoding="utf-8")), encoding="utf-8")

    def test_a_change_to_what_the_page_shows_makes_it_stale(self):
        first_row = lambda t: t.replace("| 2026-11-1", "| 2027-11-1", 1)  # noqa: E731  (the first row of the table)
        first_box = lambda t: t.replace("- [x]", "- [ ]", 1)  # noqa: E731
        new_limit = lambda t: t + "\n### 999999. A new limit\n"  # noqa: E731
        for name, fn in ((STATUS, first_row), (TASKS, first_box), (LIMITS, new_limit)):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.copy_sources(root)
                self.edit(root, name, fn)
                self.assertTrue(any("changed since" in p for p in stale(self.build, root, PAGE)), name)

    def test_a_change_to_other_lines_does_not_make_it_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.copy_sources(root)
            # an eleventh and older row, a new paragraph, a limit body line, a task line outside any group heading
            self.edit(root, STATUS, lambda t: t.replace("# Status log\n", "# Status log\n\nA new line of words.\n", 1)
                      + "\n| 2020-01-01 | 1 | an old row below the ten | x |\n")
            self.edit(root, LIMITS, lambda t: t.replace("\n### ", "\nWords added to the page.\n\n### ", 1))
            self.edit(root, TASKS, lambda t: "- [ ] 0.0 a task before any group\n" + t)
            self.assertEqual(stale(self.build, root, PAGE), [])

    def test_a_source_that_cannot_be_read_is_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(stale(self.build, Path(tmp), PAGE))

    def test_a_page_edited_by_hand_is_found(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "progress.html"
            page.write_bytes(PAGE.read_bytes() + b"<!-- x -->")
            self.assertTrue(any("not the page that was built" in p for p in stale(self.build, REPO, page)))

    def test_a_script_form_request_or_looser_policy_is_found(self):
        good = PAGE.read_text(encoding="utf-8")
        for bad in (good.replace("</body>", "<script src='a.js'></script></body>"),
                    good.replace("</body>", "<form action='x'></form></body>"),
                    good.replace("</body>", "<p>fetch('http://x')</p></body>"),
                    good.replace("default-src 'none'", "default-src *")):
            self.assertNotEqual(rule_problems(bad), [])


if __name__ == "__main__":
    unittest.main()
