"""Open a pull request the safe way, in one command, so the steps cannot be done out of order or skipped.

Steps done by hand have been skipped or reordered: a pull request opened after its own text failed the scan, an owner stop opened as
`Owner stop: no`, a second pull request opened beside one that was waiting, a push made without the number in the status part, and a waiter
started with nobody told when it ended. This does them in order and stops at the first problem, before anything is pushed or opened:

  1. the working tree is clean and the branch is not main;
  2. no other pull request is open (one at a time, drafts included);
  3. the branch has origin/main in it (otherwise: run `python -m tools.merge_main`);
     and the docs build passes and leaves nothing changed (a status part with a bad line is caught here, before the pull request exists),
     and the shard assignment is the fixed point of its balance (`python -m tools.ci_shards check-balance`);
  4. the pull request text passes the same scan as CI, with the owner stop read from the changed files (tools.pr_story, K1);
  5. push, open the pull request, write its number into the status parts (tools.pr_number), commit and push once more.

    python -m tools.pr_open --title "TITLE" --body-file FILE

Then run `python -m tools.pr_watch N --stop-at green` in the background and, after it ends, `python -m tools.pr_watch N`.

Exit codes: 0 opened; 1 the text fails the scan, or another pull request is open, or the branch is behind main (nothing was pushed or
opened); 2 a git or gh step failed (the message says which); 64 usage. It reads no token: pushing uses the git login of the machine.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from tools import pr_green, pr_story

REPO = Path(__file__).resolve().parents[1]
TITLE_MAX = 200


def sh(args, cwd=REPO):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


def main(argv, run=sh, root: Path = REPO) -> int:
    args = list(argv)
    if len(args) != 4 or args[0] != "--title" or args[2] != "--body-file" or not args[1] or len(args[1]) > TITLE_MAX:
        print('usage: python -m tools.pr_open --title "TITLE" --body-file FILE', file=sys.stderr)
        return 64
    title, body_path = args[1], Path(args[3])
    try:
        body = body_path.read_text(encoding="utf-8")
    except OSError:
        print("pr_open: the body file cannot be read", file=sys.stderr)
        return 64
    rc, branch, _ = run(["git", "branch", "--show-current"], root)
    if rc != 0 or not branch or branch == "main":
        print("STOP: this is not a feature branch (detached, or main). Nothing was pushed or opened.", file=sys.stderr)
        return 1
    rc, dirty, _ = run(["git", "status", "--porcelain"], root)
    if rc != 0 or dirty:
        print("STOP: the working tree is not clean: commit or remove the changes first. Nothing was pushed or opened.", file=sys.stderr)
        return 1
    rc, count, _ = run(["gh", "pr", "list", "--repo", pr_green.REPO_SLUG, "--state", "open", "--json", "number", "--jq", "length"], root)
    if rc != 0 or not count.isdigit():
        print("STOP: gh gave no answer about the open pull requests. Nothing was pushed or opened.", file=sys.stderr)
        return 1
    if int(count) > 0:
        print(f"STOP: {count} pull request(s) already open: one at a time, drafts included. Nothing was pushed or opened.", file=sys.stderr)
        return 1
    run(["git", "fetch", "-q", "origin"], root)
    if run(["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"], root)[0] != 0:
        print("STOP: this branch does not hold origin/main yet. Run: python -m tools.merge_main. Nothing was pushed or opened.", file=sys.stderr)
        return 1
    rc, out, err = run([sys.executable, "-m", "umwayi", "goal", "docs", "build"], root)
    _, stale, _ = run(["git", "status", "--porcelain"], root)
    if rc != 0 or stale:
        print("STOP: the docs build was refused or the generated docs are out of date:", (out + err)[-300:] or stale[:200], file=sys.stderr)
        print("Fix the status part (the tests line is at most 200 characters), rebuild, commit. Nothing was pushed or opened.", file=sys.stderr)
        return 1
    rc, out, err = run([sys.executable, "-m", "tools.ci_shards", "check-balance"], root)
    if rc != 0:
        print("STOP: the shard assignment is not balanced (the fixed point test would fail in CI):", (out + err)[-300:], file=sys.stderr)
        print("Run: python -m tools.ci_shards rebalance, commit. Nothing was pushed or opened.", file=sys.stderr)
        return 1
    _, base, _ = run(["git", "rev-parse", "origin/main"], root)
    _, head, _ = run(["git", "rev-parse", "HEAD"], root)
    changed = pr_story.changed_files(base, head, root)
    fails, warns = pr_story.check("pull_request", body, changed)
    for w in warns:
        print("warning:", w)
    if fails:
        for f in fails:
            print("STOP: the pull request text fails the scan:", f, file=sys.stderr)
        print("Nothing was pushed or opened.", file=sys.stderr)
        return 1
    rc, _, err = run(["git", "push", "-q", "-u", "origin", branch], root)
    if rc != 0:
        print("pr_open: the push failed (a 403 means the git login of this machine has no write access):", err[-200:], file=sys.stderr)
        return 2
    rc, out, err = run(["gh", "pr", "create", "--repo", pr_green.REPO_SLUG, "--base", "main", "--head", branch, "--title", title,
                        "--body-file", str(body_path)], root)
    m = re.search(r"/pull/([0-9]+)\s*$", out)
    if rc != 0 or not m:
        print("pr_open: the pull request was not opened:", err[-200:], file=sys.stderr)
        return 2
    number = int(m.group(1))
    print(f"opened: pull request {number}")
    rc, out, err = run([sys.executable, "-m", "tools.pr_number", "--pr", str(number)], root)
    if rc != 0:
        print("pr_open: the number could not be written into the status part:", (out + err)[-200:], file=sys.stderr)
        return 2
    _, dirty, _ = run(["git", "status", "--porcelain"], root)
    if dirty:
        for step in (["git", "add", "-A"], ["git", "commit", "-q", "-m", "Name the pull request in the status part"],
                     ["git", "push", "-q", "origin", branch]):
            rc, _, err = run(step, root)
            if rc != 0:
                print("pr_open: a step after opening failed:", " ".join(step[:2]), err[-200:], file=sys.stderr)
                return 2
    print(f"next: run in the background: python -m tools.pr_watch {number} --stop-at green")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
