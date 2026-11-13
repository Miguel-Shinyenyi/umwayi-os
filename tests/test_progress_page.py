"""W8 slice: the progress page ui/dist/progress.html cannot go stale, and it stays read only.

It is built by `node build.mjs` from three files: docs/status-log.md, docs/KNOWN-LIMITS.md and the tasks.md of the spec.
ui/dist/build.json holds the SHA-256 of those three files and of the page. These tests fail when:
- one of the three sources changed since the page was built, or the page was edited by hand (run the build),
- the page has a script, a form, a link, a request or a policy that is not default-src 'none'.
Standard library only, no npm. ui/test/progress.test.mjs also compares the page with a fresh render.
"""
from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PAGE = REPO / "ui" / "dist" / "progress.html"
BUILD = REPO / "ui" / "dist" / "build.json"
SOURCES = ("docs/status-log.md", "docs/KNOWN-LIMITS.md", ".kiro/specs/umwayi-os/tasks.md")
FORBIDDEN = re.compile(r"<script|<form|<input|<button|<textarea|<select|<link|<img|<iframe|\bsrc\s*=|\bhref\s*=|fetch\(|"
                       r"XMLHttpRequest|https?://|@import|url\(", re.I)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stale(build: dict, root: Path, page: Path) -> list:
    problems = []
    have = build.get("progressSources", {})
    for name in SOURCES:
        path = root / name
        if not path.is_file():
            problems.append(f"{name} is missing")
        elif have.get(name) != sha(path.read_bytes()):
            problems.append(f"{name} changed since ui/dist/progress.html was built (run node build.mjs in ui)")
    if sorted(have) != sorted(SOURCES):
        problems.append("ui/dist/build.json does not list exactly the three sources of the progress page")
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

    def test_a_changed_source_is_found(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in SOURCES:
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_bytes((REPO / name).read_bytes())
            (root / "docs/status-log.md").write_bytes(b"changed")
            problems = stale(self.build, root, PAGE)
            self.assertTrue(any("docs/status-log.md changed" in p for p in problems), problems)

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
