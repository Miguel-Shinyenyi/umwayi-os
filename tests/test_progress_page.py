"""W8 slice, W22: the progress page stays read only, and it is built at build time and never committed.

The page ui/dist/progress.html is written by `node build.mjs` (in ui/) from three files: docs/status-log.md,
docs/KNOWN-LIMITS.md and the tasks.md of the spec. Since W22 it is in .gitignore and ui/dist/build.json no longer holds
its hashes, so a pull request that adds a status row changes no committed ui file and cannot make CI fail on a stale page.
These tests check:
- the page is not committed, and build.json holds no hash of it or of what it shows,
- a pull request that adds a status row leaves every file under ui/ as it was and the ui package test passing,
- the second reader here (written apart from ui/src/data/progress.js) gives the same string as the JavaScript one,
- the page rules (no script, form, link, request; a policy of default-src 'none' plus one style hash) hold for a sample
  page made from ui/src/progress.html, for the page the build wrote when there is one, and the checker finds planted faults.
Standard library only; the reader comparison needs node (no npm) and is skipped, with the reason printed, when node is missing.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

from umwayi import goaldocs

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


def rule_problems(html: str) -> list:
    problems = [f"the page contains {m.group(0)!r}" for m in FORBIDDEN.finditer(html)]
    if "\u2014" in html:
        problems.append("the page contains an em dash")
    if not re.search(r"default-src 'none'; style-src 'sha256-[^']+'; base-uri 'none'; form-action 'none'", html):
        problems.append("the page policy is not default-src 'none' plus one style hash")
    return problems


def sample_page() -> str:
    """ui/src/progress.html with its placeholders filled by plain words, as the build fills them (the build itself needs npm)."""
    html = (REPO / "ui" / "src" / "progress.html").read_text(encoding="utf-8")
    fill = {"csp": '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'sha256-abc=\'; '
                   'base-uri \'none\'; form-action \'none\'">',
            "style": "body{margin:0}", "totals": "1 tasks done and 1 open, in 1 groups.", "groups": "<li>a</li>", "rows": "<li>b</li>",
            "limit": "Highest known limit number: 1", "date": "2026-01-01"}
    for key, value in fill.items():
        html = html.replace(f"<!--@{key}-->", value)
    return html


def tree_hashes(root: Path) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if p.is_file() and "node_modules" not in p.parts and not rel.startswith(".git/"):
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


class CommittedFilesTests(unittest.TestCase):
    def test_the_page_is_ignored_and_not_in_the_index(self):
        self.assertIn("ui/dist/progress.html", (REPO / ".gitignore").read_text(encoding="utf-8").split("\n"))
        if not (REPO / ".git").exists():
            self.skipTest("not a git checkout")
        ignored = subprocess.run(["git", "check-ignore", "-q", "--no-index", "ui/dist/progress.html"], cwd=REPO)
        self.assertEqual(ignored.returncode, 0)
        indexed = subprocess.run(["git", "cat-file", "-e", ":ui/dist/progress.html"], cwd=REPO, capture_output=True)
        self.assertNotEqual(indexed.returncode, 0, "ui/dist/progress.html is committed again; it is built, not committed")

    def test_build_json_holds_no_hash_of_the_page_or_of_what_it_shows(self):
        data = json.loads(BUILD.read_text(encoding="utf-8"))
        self.assertEqual(sorted(data), ["cliMapPage", "files", "page"])
        self.assertFalse([n for n in data["files"] if "progress" in n and not n.startswith("src/")])

    def test_the_build_script_writes_the_page_and_does_not_hash_it_into_build_json(self):
        code = (REPO / "ui" / "build.mjs").read_text(encoding="utf-8")
        self.assertIn("writeFileSync(join(dist, 'progress.html')", code)
        self.assertNotIn("progressPage", code)
        self.assertNotIn("progressShown", code)


class StatusRowDoesNotFailCiTests(unittest.TestCase):
    """The reason for W22: a pull request that adds a status row must not make a committed file stale."""

    def test_adding_a_status_row_changes_no_committed_file_under_ui_and_the_ui_package_test_still_passes(self):
        archive = subprocess.run(["git", "archive", "HEAD"], cwd=REPO, capture_output=True, check=True).stdout
        with tempfile.TemporaryDirectory(prefix="umwayi-w22-") as tmp:
            root = Path(tmp)
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                tar.extractall(root)
            before = tree_hashes(root)
            part = root / "docs-parts" / "status-log" / "W22-sample.md"
            part.write_text("date: 2026-11-20\npr: none\nwhat: A sample task that adds one row.\ntests: none\n", encoding="utf-8")
            result = goaldocs.build(root)
            self.assertEqual(result.code, 0, result.lines)
            after = tree_hashes(root)
            changed = sorted(n for n in set(before) | set(after) if before.get(n) != after.get(n))
            self.assertEqual(changed, ["docs-parts/status-log/W22-sample.md", "docs/status-log.md"])
            self.assertIn("A sample task that adds one row.", (root / "docs" / "status-log.md").read_text(encoding="utf-8"))
            ui_before = {n: h for n, h in before.items() if n.startswith("ui/")}
            self.assertEqual({n: h for n, h in after.items() if n.startswith("ui/")}, ui_before)
            r = subprocess.run([sys.executable, "-m", "unittest", "tests.test_ui_package"], cwd=root, capture_output=True, text=True,
                               env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            self.assertEqual(goaldocs.check(root).code, 0)


class ReaderTests(unittest.TestCase):
    NODE = shutil.which("node")

    def test_the_two_readers_give_the_same_string(self):
        if not self.NODE:
            print("test_progress_page: SKIPPED the reader comparison because node is missing", file=sys.stderr)
            self.skipTest("node is missing (CI has node)")
        script = ("import { readFileSync } from 'node:fs';"
                  "import { model, shown } from './src/data/progress.js';"
                  "const r = (n) => readFileSync('../' + n, 'utf8');"
                  f"process.stdout.write(shown(model({{ statusLog: r('{STATUS}'), limits: r('{LIMITS}'), tasks: r('{TASKS}') }})));")
        out = subprocess.run([self.NODE, "--input-type=module", "-e", script], cwd=REPO / "ui", capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout, shown(REPO))

    def test_the_second_reader_counts_a_new_row_a_new_box_and_a_new_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in (STATUS, TASKS, LIMITS):
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_bytes((REPO / name).read_bytes())
            base = shown(root)
            status = root / STATUS
            lines = status.read_text(encoding="utf-8").split("\n")
            first = next(i for i, ln in enumerate(lines) if re.match(r"\| \d{4}-\d{2}-\d{2} \|", ln))
            lines.insert(first, "| 2027-01-01 | 1 | a new row | x |")
            status.write_text("\n".join(lines), encoding="utf-8")
            self.assertTrue(shown(root) != base)
            self.assertEqual(json.loads(shown(root))["rows"][0]["what"], "a new row")


class PageRuleTests(unittest.TestCase):
    def test_a_sample_page_made_from_the_source_follows_the_page_rules(self):
        self.assertEqual(rule_problems(sample_page()), [])

    def test_the_page_the_build_wrote_follows_the_page_rules_when_there_is_one(self):
        if not PAGE.is_file():
            print("test_progress_page: no built page here (run node build.mjs in ui); the node tests check it in CI", file=sys.stderr)
            self.skipTest("ui/dist/progress.html has not been built here")
        self.assertEqual(rule_problems(PAGE.read_text(encoding="utf-8")), [])
        self.assertRegex(PAGE.read_text(encoding="utf-8"), r"Built on \d{4}-\d{2}-\d{2}\.")

    def test_a_script_form_request_or_looser_policy_is_found(self):
        good = sample_page()
        for bad in (good.replace("</body>", "<script src='a.js'></script></body>"),
                    good.replace("</body>", "<form action='x'></form></body>"),
                    good.replace("</body>", "<p>fetch('http://x')</p></body>"),
                    good.replace("default-src 'none'", "default-src *"),
                    good.replace("</body>", "<p>a \u2014 b</p></body>")):
            self.assertNotEqual(rule_problems(bad), [])


if __name__ == "__main__":
    unittest.main()
