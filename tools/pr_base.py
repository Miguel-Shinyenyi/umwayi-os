"""F4b: a pull request whose base is not main fails a check ("base is not main; one PR at a time").

The rule of 2026-11-23 replaces the stacking rule: one pull request is open at a time and its branch is merged with main, so the base of
every pull request is main. Merging one open branch into another made GitHub close a pull request as merged without its own review (PR 189).
The CI `plan` job runs this before it decides the plan; a failure fails `plan`, and so `result`.

    python -m tools.pr_base --event-file "$GITHUB_EVENT_PATH"
    python -m tools.pr_base --event pull_request --base-ref main

A push is not a pull request and passes. An event file that cannot be read, or a pull request event with no base, fails closed.
Exit codes: 0 the base is main (or this is not a pull request), 2 it is not, or the event cannot be read, 64 usage.
"""
from __future__ import annotations

import json
import sys

MESSAGE = "base is not main; one PR at a time"


def check(event: str, base_ref) -> tuple:
    """(ok, line). A pull request passes only when its base ref is exactly `main`."""
    if event != "pull_request":
        return True, f"not a pull request ({event}): nothing to check"
    if base_ref == "main":
        return True, "base is main"
    return False, f"{MESSAGE} (base: {base_ref if isinstance(base_ref, str) and base_ref.isprintable() and len(base_ref) < 100 else 'unreadable'})"


def read_event_file(path: str) -> tuple:
    """(event name, base ref) from a GitHub event file: a `pull_request` key means a pull request event."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return "pull_request", None  # unreadable: treated as a pull request with no base, which fails
    if not isinstance(data, dict):
        return "pull_request", None
    if "pull_request" not in data:
        return "push", None
    pr = data["pull_request"]
    base = pr.get("base") if isinstance(pr, dict) else None
    return "pull_request", base.get("ref") if isinstance(base, dict) else None


def main(argv) -> int:
    if len(argv) == 2 and argv[0] == "--event-file":
        event, base = read_event_file(argv[1])
    elif len(argv) == 4 and argv[0] == "--event" and argv[2] == "--base-ref":
        event, base = argv[1], argv[3]
    else:
        print("usage: python -m tools.pr_base --event-file FILE | --event NAME --base-ref REF", file=sys.stderr)
        return 64
    ok, line = check(event, base)
    print(line, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
