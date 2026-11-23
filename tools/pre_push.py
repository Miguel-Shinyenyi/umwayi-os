"""G8b: run, before a push, the tests a change can break, and fail the push when one does.

Lessons of rounds 4 to 6 became this one command. A pull request failed in CI because a test that I had not thought of read a file I moved
(the page `docs/testing.md`, PR 196), and because a golden pinned the bytes of an answer I changed (PR 193). This lists, from the files the
branch changes:

  * always: the scanner and guard tests of the whole package (`tests.test_scan_files`, `tests.test_system`, `tests.test_automation`);
  * the guard tests of each package touched (PREFIX_TESTS: a change in `umwayi/agents.py` runs `tests/agents/test_agents_gate.py`, and so on);
  * every test file that mentions the NAME of a file the branch changes, moves or deletes (the base name, so a path written in pieces such as
    `REPO / "docs" / "testing.md"` is found too). That is the search I did too late by hand.

and runs them. Exit codes: 0 every test passed (or `--list`), 1 a test failed (the push stops), 64 usage. It never pushes.

    python -m tools.pre_push            run them against origin/main
    python -m tools.pre_push --list     only name them
    python -m tools.pre_push --install  write .git/hooks/pre-push that runs this (never overwrites a hook that is not ours)

GitHub CI is still the record; this is the check before the first push, not instead of it.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ALWAYS = ("tests.test_scan_files", "tests.test_system", "tests.test_automation")
# a change under the prefix runs the module or the whole folder of tests
PREFIX_TESTS = (
    ("umwayi/agents.py", ("tests.agents.test_agents_gate",)),
    ("umwayi/goal", ("tests.goal.test_goalrun", "tests.goal.test_cmd_run")),
    ("umwayi/confine.py", ("tests.test_confine",)),
    ("umwayi/seatbelt.py", ("tests.test_seatbelt",)),
    ("umwayi/broker.py", ("tests.test_broker",)),
    ("umwayi/rules.py", ("tests.test_rules", "tests.test_elections", "tests.autonomy.test_off", "tests.adapters.test_refusal_shape")),
    ("adapters/", ("tests.adapters.test_claude_code", "tests.adapters.test_stdio", "tests.adapters.test_kiro")),
    ("docs/", ("tests.test_docs",)),
    ("docs-parts/", ("tests.test_docs", "tests.test_pr_numbers", "tests.test_limits_numbers")),
    ("tools/", ("tests.test_ci_map", "tests.test_ci_shards", "tests.test_generated_files")),
    (".github/", ("tests.test_ci_workflow", "tests.test_ci_plan")),
    ("umwayi/cli.py", ("tests.test_cli_map", "tests.test_exit_codes")),
)
MARK = "# umwayi pre-push (tools/pre_push.py)"


def _git(*args, cwd=REPO) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    return r.stdout


def changed_paths(base: str = "origin/main", cwd: Path = REPO) -> list:
    """Paths the branch changes against `base`, committed or not: added, modified, deleted, and both names of a rename."""
    out = set()
    for args in (("diff", "--name-status", f"{base}...HEAD"), ("diff", "--name-status", "HEAD")):
        for line in _git(*args, cwd=cwd).splitlines():
            parts = line.split("\t")
            out.update(p for p in parts[1:] if p)
    out.update(l for l in _git("ls-files", "--others", "--exclude-standard", cwd=cwd).splitlines() if l)
    return sorted(out)


def _module(path: Path, root: Path) -> str:
    return ".".join(path.relative_to(root).with_suffix("").parts)


def modules_for(changed: list, root: Path = REPO) -> list:
    """The test modules to run for these changed paths: ALWAYS, the prefix table, and every test file that mentions the name of a changed
    file. A test file that was itself changed runs too. Only modules that exist are named."""
    root = Path(root)
    tests_dir = root / "tests"
    all_tests = {p: p.read_text(encoding="utf-8", errors="replace") for p in sorted(tests_dir.rglob("test_*.py"))}
    chosen = {m for m in ALWAYS if (root / (m.replace(".", "/") + ".py")).exists()}
    for prefix, mods in PREFIX_TESTS:
        if any(c.startswith(prefix) for c in changed):
            chosen.update(m for m in mods if (root / (m.replace(".", "/") + ".py")).exists())
    for c in changed:
        if c.startswith("tests/") and c.endswith(".py") and (root / c).exists() and Path(c).name.startswith("test_"):
            chosen.add(_module(root / c, root))
            continue
        name = Path(c).name
        if len(name) < 5 or c.startswith("docs-parts/"):
            continue  # a status part is read by the docs tests only; a very short name matches everything
        for p, text in all_tests.items():
            if name in text:
                chosen.add(_module(p, root))
    return sorted(chosen)


def install_hook(root: Path = REPO) -> str:
    """Write the git pre-push hook. Returns "written", "already ours" or "refused" (a hook of someone else is there)."""
    hooks = Path(_git("rev-parse", "--git-path", "hooks", cwd=root).strip())
    hooks = hooks if hooks.is_absolute() else Path(root) / hooks
    hooks.mkdir(parents=True, exist_ok=True)
    path = hooks / "pre-push"
    body = f"#!/bin/sh\n{MARK}\ncd \"$(git rev-parse --show-toplevel)\" && exec python3 -m tools.pre_push\n"
    if path.exists():
        text = path.read_text(encoding="utf-8")
        if MARK not in text:
            return "refused"
        if text == body:
            return "already ours"
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return "written"


def main(argv, root: Path = REPO) -> int:
    if argv == ["--install"]:
        r = install_hook(root)
        print(f"pre_push: hook {r}")
        return 1 if r == "refused" else 0
    if argv not in ([], ["--list"]):
        print("usage: python -m tools.pre_push [--list | --install]", file=sys.stderr)
        return 64
    mods = modules_for(changed_paths(cwd=root), root)
    print("pre_push: " + str(len(mods)) + " test module(s) for this change:")
    for m in mods:
        print("  " + m)
    if argv == ["--list"] or not mods:
        return 0
    r = subprocess.run([sys.executable, "-m", "unittest", *mods], cwd=root, check=False)
    if r.returncode != 0:
        print("pre_push: a test failed: fix it before you push", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
