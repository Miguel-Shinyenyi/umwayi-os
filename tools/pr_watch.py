"""Wait for a pull request, and end when something needs the builder: merged, closed, a check failed, or (if asked) green.

The mistake this removes: a pull request was opened and nobody was waiting for its merge, so a merge went unnoticed for minutes and the next
branch did not open. A waiter that only wrote to a file told nobody. Run this command in the BACKGROUND of a session that is told when a
background command ends: the end of the command is the notice, so no second watcher is needed.

    python -m tools.pr_watch 247                    keeps waiting through green; ends at merged, closed or a failed check
    python -m tools.pr_watch 247 --stop-at green    also ends the first time the exact head is green (an owner stop waits for a word)

It prints one line at each change and flushes it. Exit codes: 0 the pull request is merged or closed, or green with --stop-at green;
2 a check of the exact head failed; 3 `gh` gave no answer for ten polls in a row (the waiter says so and ends instead of waiting for ever);
64 usage. It reads through `gh` and `tools.pr_green` (green only for the exact head); it never pushes, merges or comments.
"""
from __future__ import annotations

import subprocess
import sys
import time

from tools import pr_green

INTERVAL = 60
SILENT_LIMIT = 10  # polls in a row with no answer from gh


def fetch_state(pr: int):
    r = subprocess.run(["gh", "pr", "view", str(pr), "--repo", pr_green.REPO_SLUG, "--json", "state", "--jq", ".state"],
                       capture_output=True, text=True, check=False)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def fetch_green(pr: int) -> tuple:
    head, runs = pr_green.fetch(pr)
    if head is None:
        return None, "gh gave no answer for this pull request"
    return pr_green.verdict(head, runs)


def watch(pr: int, stop_at: str = "merged", state_of=fetch_state, green_of=fetch_green, sleep=time.sleep, say=None,
          interval: int = INTERVAL, max_polls=None) -> int:
    say = say or (lambda line: print(line, flush=True))
    said_green, silent, polls = False, 0, 0
    while max_polls is None or polls < max_polls:
        polls += 1
        state = state_of(pr)
        if state is None:
            silent += 1
            if silent >= SILENT_LIMIT:
                say(f"PR {pr} WATCH ENDED: gh gave no answer {SILENT_LIMIT} times in a row; check the login and the network")
                return 3
            sleep(interval)
            continue
        silent = 0
        if state != "OPEN":
            say(f"PR {pr} {state}")
            return 0
        green, why = green_of(pr)
        if green:
            if stop_at == "green":
                say(f"PR {pr} green: {why} (waiting for the owner's word)")
                return 0
            if not said_green:
                say(f"PR {pr} green: {why} (waiting for the merge)")
                said_green = True
        elif green is False and why.startswith("failed:"):
            say(f"PR {pr} CHECK FAILED: {why}")
            return 2
        else:
            said_green = False
        sleep(interval)
    return 0


def main(argv) -> int:
    stop_at = "merged"
    args = list(argv)
    if "--stop-at" in args:
        i = args.index("--stop-at")
        if i + 1 >= len(args) or args[i + 1] not in ("green", "merged"):
            print("usage: python -m tools.pr_watch PR [--stop-at green|merged]", file=sys.stderr)
            return 64
        stop_at = args[i + 1]
        del args[i:i + 2]
    if len(args) != 1 or not args[0].isdigit():
        print("usage: python -m tools.pr_watch PR [--stop-at green|merged]", file=sys.stderr)
        return 64
    return watch(int(args[0]), stop_at)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
