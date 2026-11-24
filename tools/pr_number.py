"""F2a: put the pull request number into the status parts of a branch.

A status part (`docs-parts/status-log/*.md`) says `pr: none` until the pull request exists, and then nobody went back, so 37 parts of
the last two days merged with `pr: none`. This helper, run after the pull request is opened, writes the number into the parts the
branch added and rebuilds `docs/status-log.md`. `tests/test_pr_numbers.py` fails the build on any part dated on or after the cutoff
that still says `pr: none`.

    python -m tools.pr_number              the number of the pull request of the current branch, read with `gh pr view`
    python -m tools.pr_number --pr 196     a given number
    python -m tools.pr_number --check      only list the parts that would fail the test

Exit codes: 0 done (or nothing to do), 2 no number could be found or a part could not be written, 64 usage.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CUTOFF = "2026-11-22"  # parts dated on or after this day must name their pull request
PARTS = Path("docs-parts") / "status-log"
_DATE = re.compile(r"(?m)^date:\s*(\S+)\s*$")
_PR = re.compile(r"(?m)^pr:\s*(\S+)\s*$")


def unnumbered(root: Path, since: str = CUTOFF) -> list:
    """The part files (relative paths) dated on or after `since` that say `pr: none`."""
    out = []
    for p in sorted((Path(root) / PARTS).glob("*.md")):
        text = p.read_text(encoding="utf-8")
        d, n = _DATE.search(text), _PR.search(text)
        if d and n and d.group(1) >= since and n.group(1) == "none":
            out.append(str(PARTS / p.name))
    return out


def set_number(root: Path, files: list, number: int) -> list:
    """Write `pr: NUMBER` in place of `pr: none` in the given parts. Touches no other line and no other file. Returns the files changed."""
    if not (isinstance(number, int) and not isinstance(number, bool) and number > 0):
        raise ValueError("the pull request number must be a positive whole number")
    changed = []
    for rel in files:
        p = Path(root) / rel
        text = p.read_text(encoding="utf-8")
        new, n = _PR.subn(lambda m: f"pr: {number}" if m.group(1) == "none" else m.group(0), text, count=1)
        if new != text:
            p.write_text(new, encoding="utf-8")
            changed.append(rel)
    return changed


def added_parts(root: Path) -> list:
    """The status parts this branch added against origin/main, by git."""
    r = subprocess.run(["git", "diff", "--name-only", "--diff-filter=A", "origin/main...HEAD", "--", str(PARTS)], cwd=root,
                       capture_output=True, text=True, check=False)
    return [l for l in r.stdout.split("\n") if l.endswith(".md")]


def current_pr(root: Path) -> int | None:
    r = subprocess.run(["gh", "pr", "view", "--json", "number", "--jq", ".number"], cwd=root, capture_output=True, text=True, check=False)
    return int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip().isdigit() else None


def main(argv, root: Path = REPO) -> int:
    if argv == ["--check"]:
        for f in unnumbered(root):
            print(f)
        return 0
    number = None
    if argv[:1] == ["--pr"] and len(argv) == 2 and argv[1].isdigit():
        number = int(argv[1])
    elif argv:
        print("usage: python -m tools.pr_number [--pr N | --check]", file=sys.stderr)
        return 64
    else:
        number = current_pr(root)
    if number is None:
        print("pr_number: no pull request found for this branch; open it first or give --pr N", file=sys.stderr)
        return 2
    mine = [f for f in added_parts(root) if f in unnumbered(root, "0000-00-00")]
    changed = set_number(root, mine, number)
    for f in changed:
        print(f"pr_number: {f}: pr {number}")
    if changed:
        r = subprocess.run([sys.executable, "-m", "umwayi", "goal", "docs", "build"], cwd=root, capture_output=True, text=True, check=False)
        if r.returncode != 0:
            print(r.stdout + r.stderr, file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
