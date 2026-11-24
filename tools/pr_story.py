"""L7: a pull request that stops for the owner must carry a story; every pull request is scanned for overclaims.

The rule (owner, 2026-11-23, P1 and P3): a pull request has two parts in this order, the story in plain words and then the technical
record. CI refuses an owner-stop pull request whose story is empty or too short; other pull requests get a warning. The honesty scan
refuses text that claims more than the feature does. The check proves a story EXISTS and that no overclaim phrase is in the text. It does
not prove the story is good: the owner and the guide read it.

    python -m tools.pr_story --event-file "$GITHUB_EVENT_PATH"

It reads the body only from the event file (never from a shell expression, so a body cannot run anything). Print format: one line per
finding, `::error::` for a failure and `::warning::` for a warning, so the Actions page shows them.

An owner-stop pull request is one whose body has the line `Owner stop: yes`. A body with no such line is a warning, not a failure
(the pull request may not use the template), and so is a push (not checked at all). A draft pull request is checked like any other.
Exit codes: 0 no failure (warnings may print), 2 a failure, 64 usage.
"""
from __future__ import annotations

import json
import re
import sys

MIN_STORY_WORDS = 100
STORY_HEADING = re.compile(r"(?mi)^##\s+story\s*$")
HEADING = re.compile(r"(?m)^##\s+\S")
OWNER_STOP = re.compile(r"(?mi)^\s*owner stop:\s*(yes|no)\b")
COMMENT = re.compile(r"<!--.*?-->", re.S)
# Phrases that overclaim today (P3): fail on these in any pull request. The cooperative sentence is taken out first.
OVERCLAIM = re.compile(
    r"enforced by default|enforcement is enforced|sandboxed by default|is fully enforced|are fully enforced|"
    r"is now enforced|are now enforced|is enforced\b(?! where built)|are enforced\b(?! where built)|"
    r"is sandboxed|are sandboxed|is confined|are confined", re.I)
TODAY_NOTE = re.compile(r"enforcement is cooperative today and enforced where built", re.I)
NEGATED = re.compile(r"\b(?:not|never|is not|are not|nor)\s+(?:yet\s+)?(?:fully\s+)?(?:enforced|sandboxed|confined)\b", re.I)
WORDS = re.compile(r"(?i)\b(enforced|sandboxed|confined)\b")


def story_of(body: str) -> str:
    """The text under the `## Story` heading up to the next `##` heading, without placeholder lines and comments."""
    body = COMMENT.sub("", body or "")
    m = STORY_HEADING.search(body)
    if not m:
        return ""
    rest = body[m.end():]
    n = HEADING.search(rest)
    text = rest[:n.start()] if n else rest
    lines = [l for l in text.split("\n") if not (l.strip().startswith("(") and l.strip().endswith(")"))
             and not OWNER_STOP.match(l) and not re.match(r"(?i)\s*(video|limits and honesty):", l)]
    return "\n".join(lines).strip()


def words(text: str) -> int:
    return len(re.findall(r"\S+", text))


def check(event: str, body) -> tuple:
    """(failures, warnings), two lists of lines. A push or another event passes with nothing."""
    if event != "pull_request":
        return [], []
    if not isinstance(body, str):
        body = ""
    fails, warns = [], []
    story = story_of(body)
    n = words(story)
    stop = OWNER_STOP.search(COMMENT.sub("", body))
    if stop is None:
        warns.append("the body has no `Owner stop: yes` or `Owner stop: no` line, so the story rule was not applied")
    short = f"the story (the text under `## Story`) has {n} words; an owner-stop pull request needs at least {MIN_STORY_WORDS}"
    if stop is not None and stop.group(1).lower() == "yes":
        if n < MIN_STORY_WORDS:
            fails.append(short)
    elif n < MIN_STORY_WORDS:
        warns.append(short.replace("an owner-stop pull request needs at least", "a story is advised, at least"))
    clean = NEGATED.sub("", TODAY_NOTE.sub("", COMMENT.sub("", body)))
    found = sorted({m.group(0).lower() for m in OVERCLAIM.finditer(clean)})
    if found:
        fails.append("the text claims more than the feature does (" + "; ".join(found) + "): say cooperative today, enforced where built")
    bare = sorted({m.group(1).lower() for m in WORDS.finditer(clean)} - {w.split()[-1] for w in found})
    if bare:
        warns.append("the words " + ", ".join(bare) + " are in the text: check that each is about a built, real enforced run, or is negated")
    return fails, warns


def read_event_file(path: str) -> tuple:
    """(event name, body). An unreadable file is a pull request with no body, which fails the story rule only when it says owner stop."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return "pull_request", None
    if not isinstance(data, dict) or "pull_request" not in data:
        return "push", None
    pr = data["pull_request"]
    return "pull_request", pr.get("body") if isinstance(pr, dict) else None


def main(argv) -> int:
    if len(argv) != 2 or argv[0] != "--event-file":
        print("usage: python -m tools.pr_story --event-file FILE", file=sys.stderr)
        return 64
    event, body = read_event_file(argv[1])
    fails, warns = check(event, body)
    for w in warns:
        print("::warning::" + w)
    for f in fails:
        print("::error::" + f)
    if not fails and not warns:
        print("pr_story: nothing to report")
    return 2 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
