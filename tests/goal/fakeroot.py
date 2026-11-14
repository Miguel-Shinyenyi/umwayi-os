"""A temporary umwayi root, a fake git repo and a fake clock for the goal tests (W9.R21.2).

Standard library only. The git repo is made with the system `git` in a temporary folder: a local `main`, an
`origin/main` ref made by a second temporary repo, and support for `git worktree`. A test that needs git calls
`needs_git()` first, which skips with a clear message when git is missing or older than 2.17 (the version that
added `git worktree remove`).
"""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# The date the test helpers write their logbook entries with: today's UTC date, computed when this module is imported
# (W34). The supervisor and the goal commands date their own entries by the election clock (the later of the system
# date and the newest entry), and the logbook refuses an entry dated before its last one, so a fixed day broke every
# test that mixes the two once the clock passed it.
DATE = datetime.now(timezone.utc).date().isoformat()
EPOCH = 1_794_000_000  # a fixed time of day for the fake clock: 2026-11-06 UTC, far from any test date
GIT_ENV = {
    "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


class FakeClock:
    """A clock that only moves when a test says so. `now` is seconds since the epoch (UTC)."""

    def __init__(self, now=EPOCH):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds
        return self.now


def git_version():
    try:
        out = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"(\d+)\.(\d+)", out)
    return (int(m.group(1)), int(m.group(2))) if m else None


def needs_git():
    v = git_version()
    if v is None:
        raise unittest.SkipTest("git is not installed, so this test is skipped")
    if v < (2, 17):
        raise unittest.SkipTest("git is older than 2.17 (no `git worktree remove`), so this test is skipped")


def git(cwd, *args, check=True):
    env = dict(os.environ)
    env.update(GIT_ENV)
    p = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, env=env, timeout=60)
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {p.stderr.strip()}")
    return p.stdout.strip()


class FakeGit:
    """A repo with a local `main` and, if asked, an `origin/main` ref made from a second repo."""

    def __init__(self, base, name="repo"):
        needs_git()
        self.path = Path(base) / name
        self.path.mkdir(parents=True)
        git(self.path, "init", "-q", "-b", "main")
        (self.path / "README.md").write_text("fake repo\n", encoding="utf-8")
        git(self.path, "add", "README.md")
        git(self.path, "commit", "-q", "-m", "first")
        self.origin = None

    def commit(self, name, text="x\n", message="change"):
        p = self.path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        git(self.path, "add", name)
        git(self.path, "commit", "-q", "-m", message)
        return git(self.path, "rev-parse", "HEAD")

    def add_origin(self):
        """Make `origin/main` equal to the local main now (a second repo, fetched once)."""
        self.origin = self.path.parent / (self.path.name + "-origin")
        shutil.copytree(self.path, self.origin)
        git(self.path, "remote", "add", "origin", str(self.origin))
        git(self.path, "fetch", "-q", "origin")
        return self

    def origin_ahead(self, name="ahead.txt"):
        """Put one more commit on origin/main that the local main lacks."""
        git(self.origin, "checkout", "-q", "main")
        p = self.origin / name
        p.write_text("ahead\n", encoding="utf-8")
        git(self.origin, "add", name)
        git(self.origin, "commit", "-q", "-m", "ahead")
        git(self.path, "fetch", "-q", "origin")

    def main_tip(self):
        return git(self.path, "rev-parse", "refs/heads/main")

    def worktrees(self):
        return git(self.path, "worktree", "list", "--porcelain")


class FakeRoot(unittest.TestCase):
    """A test with a fresh umwayi root in a temporary folder: umwayi.json, an empty queue.md and the logbook on first write."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(os.path.realpath(self._tmp.name)) / "umwayi-os"
        self.root.mkdir()
        shutil.copy(REPO / "umwayi.json", self.root / "umwayi.json")
        (self.root / "memory").mkdir()
        self.clock = FakeClock()
        self.when = DATE

    def logbook_text(self):
        p = self.root / "LOGBOOK.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def entries(self):
        from umwayi import logbook
        return logbook.read_checked_chain(self.root)[0]
