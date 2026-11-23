"""G8e: a pull request is green only when the checks are for ITS head, and `result` finished with success.

A pull request shows the checks of its newest head, but after a push the list can still show the run of the head before, and the
earlier runs I read as "green" belonged to the old commit (PRs 189 and 196). This reads the check runs of the exact head commit of the pull
request and refuses to say green unless every run in the answer carries that commit's sha, `result` is there and finished with success,
and no run failed or is still going.

    python -m tools.pr_green 196          prints green, or not green with the reason; exit 0 or 2

Exit codes: 0 green, 2 not green (or no answer), 64 usage. It reads through `gh`; it never pushes, merges or comments.
"""
from __future__ import annotations

import json
import subprocess
import sys

REPO_SLUG = "Miguel-Shinyenyi/umwayi-os"
OKAY = ("success", "skipped", "neutral")
IGNORED = ("Vercel", "Vercel Preview Comments")  # deployment checks of the host, not tests


def verdict(head_sha: str, runs: list) -> tuple:
    """(green, reason). `runs` are check runs as the API gives them: name, status, conclusion, head_sha."""
    mine = [r for r in runs if r.get("name") not in IGNORED]
    if not mine:
        return False, "no check run for this head yet"
    stale = sorted({str(r.get("head_sha"))[:7] for r in mine if r.get("head_sha") != head_sha})
    if stale:
        return False, f"a run belongs to an older commit ({', '.join(stale)}), not to the head {head_sha[:7]}"
    pending = [r["name"] for r in mine if r.get("status") != "completed"]
    if pending:
        return False, "still running: " + ", ".join(sorted(pending))
    failed = [r["name"] for r in mine if r.get("conclusion") not in OKAY]
    if failed:
        return False, "failed: " + ", ".join(sorted(failed))
    result = [r for r in mine if r.get("name") == "result"]
    if not result:
        return False, "the `result` check is not there"
    if result[0].get("conclusion") != "success":
        return False, "`result` did not finish with success"
    return True, f"green at {head_sha[:7]}"


def _gh(*args) -> str:
    r = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    return r.stdout if r.returncode == 0 else ""


def fetch(pr: int) -> tuple:
    """(head sha, check runs of that exact commit), or (None, []) when gh gives no answer."""
    head = _gh("pr", "view", str(pr), "--repo", REPO_SLUG, "--json", "headRefOid", "--jq", ".headRefOid").strip()
    if not head:
        return None, []
    raw = _gh("api", f"repos/{REPO_SLUG}/commits/{head}/check-runs?per_page=100")
    try:
        runs = json.loads(raw).get("check_runs", [])
    except ValueError:
        return head, []
    return head, [{"name": r.get("name"), "status": r.get("status"), "conclusion": r.get("conclusion"), "head_sha": r.get("head_sha")}
                  for r in runs]


def main(argv) -> int:
    if len(argv) != 1 or not argv[0].isdigit():
        print("usage: python -m tools.pr_green PR_NUMBER", file=sys.stderr)
        return 64
    head, runs = fetch(int(argv[0]))
    if head is None:
        print("not green: gh gave no answer for this pull request", file=sys.stderr)
        return 2
    ok, why = verdict(head, runs)
    print(("green" if ok else "not green") + ": " + why, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
