"""W16: the board status. One line per open pull request of Miguel-Shinyenyi/umwayi-os, for the guide's every cycle.

Standard library only. It reads the public GitHub REST API over HTTPS with urllib, with no token, and with a timeout
on every request. It never writes anything and never runs git.

  python tools/board_status.py

One line per open pull request:

  #12 | title | head-branch | last commit 2026-11-13 10:00Z | ci green | has newest main yes | mergeable

then one line that starts with "stall:". It names every branch with no new commit for 30 minutes or more, or says
"stall: none". With no open pull request it prints "no open pull requests" and "stall: none".

  ci          green (every check suite of the head commit ended well), red (any ended badly), running (any has not
              ended), none (the head commit has no check suite yet; this is not green)
  main        yes when the head commit already has every commit of origin/main (the compare says it is not behind)
  merge       mergeable, or conflict (GitHub says the merge would conflict)

Fail closed: any HTTP error, rate limit, network error, bad JSON, missing or odd field, a list longer than one page, or
a mergeable flag that GitHub has not worked out yet prints ONE line that starts with "board status failed:" and exits 2.
It never guesses a state and never prints a half result.

Exit codes: 0 done, 2 a failure of any kind (a crash blocks), 64 wrong use (any argument).
"""
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

OWNER = "Miguel-Shinyenyi"
REPO_NAME = "umwayi-os"
API = "https://api.github.com"
MAIN = "main"
TIMEOUT = 15  # seconds, on every request
PAGE = 100
STALL_MINUTES = 30
MERGEABLE_TRIES = 3  # GitHub works out "mergeable" in the background; ask again a few times
MERGEABLE_WAIT = 2.0
MAX_BODY = 5_000_000
USAGE_EXIT = 64
FAIL_EXIT = 2

RUNNING = frozenset({"queued", "in_progress", "pending", "requested", "waiting"})
GOOD = frozenset({"success", "neutral", "skipped"})
BAD = frozenset({"failure", "timed_out", "cancelled", "action_required", "startup_failure", "stale"})
_SHA = re.compile(r"[0-9a-f]{40}")
_TIME = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")


class BoardError(Exception):
    """Carries the one line that is printed. Never carries file text, a header value or a body."""


# ---------------------------------------------------------------- the HTTP layer (tests replace it)

def http_get(url, timeout=TIMEOUT):
    """(status, headers with lower case names, body bytes). Only https to api.github.com. Raises BoardError."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.netloc != "api.github.com":
        raise BoardError("refused a request outside https://api.github.com")
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "umwayi-os-board-status",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(MAX_BODY + 1)
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, body
    except urllib.error.HTTPError as e:
        try:
            body = e.read(MAX_BODY + 1)
        except Exception:
            body = b""
        return e.code, {k.lower(): v for k, v in e.headers.items()}, body
    except TimeoutError:
        raise BoardError(f"the request timed out after {timeout} seconds") from None
    except urllib.error.URLError:
        raise BoardError("the network request failed") from None
    except OSError:
        raise BoardError("the network request failed") from None


# ---------------------------------------------------------------- reading answers

def _rate_text(headers):
    reset = headers.get("x-ratelimit-reset", "")
    if reset.isdigit():
        when = datetime.fromtimestamp(int(reset), tz=timezone.utc).strftime("%Y-%m-%d %H:%MZ")
        return f"GitHub rate limit reached, try again after {when}"
    return "GitHub rate limit reached, try again later"


def get_json(fetch, path, label):
    """The decoded JSON of one GET, or a BoardError with one line. `path` starts with /."""
    status, headers, body = fetch(API + path)
    if not isinstance(status, int) or not isinstance(headers, dict) or not isinstance(body, (bytes, bytearray)):
        raise BoardError(f"{label}: the HTTP layer gave an answer of the wrong shape")
    if status == 429 or (status == 403 and (headers.get("x-ratelimit-remaining") == "0" or b"rate limit" in body.lower())):
        raise BoardError(_rate_text(headers))
    if status != 200:
        raise BoardError(f"{label}: GitHub answered HTTP {status}")
    if len(body) > MAX_BODY:
        raise BoardError(f"{label}: the answer is too large")
    try:
        return json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise BoardError(f"{label}: the answer is not valid JSON") from None


def _dig(obj, keys, label, kind):
    """obj[k1][k2]... and it must be of type `kind`; a missing key or a wrong type is a BoardError."""
    cur = obj
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            raise BoardError(f"{label}: the field {'.'.join(keys)} is missing")
        cur = cur[k]
    if isinstance(cur, bool) and kind is not bool:
        raise BoardError(f"{label}: the field {'.'.join(keys)} has the wrong type")
    if not isinstance(cur, kind):
        raise BoardError(f"{label}: the field {'.'.join(keys)} has the wrong type")
    return cur


def parse_time(text, label):
    if not isinstance(text, str) or not _TIME.fullmatch(text):
        raise BoardError(f"{label}: a time is missing or not in the form YYYY-MM-DDTHH:MM:SSZ")
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def clean(text):
    """One line of plain text: control characters and the column separator removed."""
    return " ".join("".join(ch if ch.isprintable() else " " for ch in text).replace("|", "/").split())


# ---------------------------------------------------------------- the four facts about one pull request

def ci_state(suites_doc, label):
    """green, red, running or none from the check suites of the head commit."""
    total = _dig(suites_doc, ["total_count"], label, int)
    suites = _dig(suites_doc, ["check_suites"], label, list)
    if total != len(suites):
        raise BoardError(f"{label}: there are more check suites than one page holds")
    if not suites:
        return "none"
    red = running = False
    for s in suites:
        status = _dig(s, ["status"], label, str)
        if status in RUNNING:
            running = True
        elif status == "completed":
            conclusion = _dig(s, ["conclusion"], label, str)
            if conclusion in BAD:
                red = True
            elif conclusion not in GOOD:
                raise BoardError(f"{label}: a check suite has the conclusion {clean(conclusion)[:30]!r}, which is not known")
        else:
            raise BoardError(f"{label}: a check suite has the status {clean(status)[:30]!r}, which is not known")
    return "red" if red else "running" if running else "green"


def has_main(compare_doc, label):
    """True when the head commit is not behind main."""
    behind = _dig(compare_doc, ["behind_by"], label, int)
    if behind < 0:
        raise BoardError(f"{label}: behind_by is negative")
    return behind == 0


def merge_flag(fetch, number, label, sleep):
    """mergeable or conflict. GitHub says null while it works; ask again, then fail."""
    for attempt in range(MERGEABLE_TRIES):
        doc = get_json(fetch, f"/repos/{OWNER}/{REPO_NAME}/pulls/{number}", label)
        if not isinstance(doc, dict) or "mergeable" not in doc:
            raise BoardError(f"{label}: the field mergeable is missing")
        value = doc["mergeable"]
        if value is True:
            return "mergeable"
        if value is False:
            return "conflict"
        if value is not None:
            raise BoardError(f"{label}: the field mergeable has the wrong type")
        if attempt + 1 < MERGEABLE_TRIES:
            sleep(MERGEABLE_WAIT)
    raise BoardError(f"{label}: GitHub has not worked out mergeable yet, run again in a minute")


# ---------------------------------------------------------------- the board

def collect(fetch, sleep=time.sleep):
    """A list of dicts, one per open pull request, oldest number first. Raises BoardError."""
    listing = get_json(fetch, f"/repos/{OWNER}/{REPO_NAME}/pulls?state=open&per_page={PAGE}", "pull request list")
    if not isinstance(listing, list):
        raise BoardError("pull request list: the answer is not a list")
    if len(listing) >= PAGE:
        raise BoardError(f"pull request list: {PAGE} or more open pull requests, more than one page")
    rows = []
    for item in listing:
        if not isinstance(item, dict):
            raise BoardError("pull request list: an entry is not an object")
        number = _dig(item, ["number"], "pull request list", int)
        label = f"pull request {number}"
        title = _dig(item, ["title"], label, str)
        branch = _dig(item, ["head", "ref"], label, str)
        sha = _dig(item, ["head", "sha"], label, str)
        if not _SHA.fullmatch(sha):
            raise BoardError(f"{label}: head.sha is not a commit id")
        commit = get_json(fetch, f"/repos/{OWNER}/{REPO_NAME}/commits/{sha}", label)
        pushed = parse_time(_dig(commit, ["commit", "committer", "date"], label, str), label)
        suites = get_json(fetch, f"/repos/{OWNER}/{REPO_NAME}/commits/{sha}/check-suites?per_page={PAGE}", label)
        compare = get_json(fetch, f"/repos/{OWNER}/{REPO_NAME}/compare/{MAIN}...{sha}", label)
        rows.append({
            "number": number,
            "title": clean(title),
            "branch": clean(branch),
            "pushed": pushed,
            "ci": ci_state(suites, label),
            "main": has_main(compare, label),
            "merge": merge_flag(fetch, number, label, sleep),
        })
    rows.sort(key=lambda r: r["number"])
    return rows


def render(rows, now):
    """The lines to print. `now` is an aware datetime."""
    if not rows:
        return ["no open pull requests", "stall: none"]
    lines, stalled = [], []
    for r in rows:
        lines.append(" | ".join([
            f"#{r['number']}", r["title"], r["branch"],
            "last commit " + r["pushed"].strftime("%Y-%m-%d %H:%MZ"),
            "ci " + r["ci"],
            "has newest main " + ("yes" if r["main"] else "no"),
            r["merge"],
        ]))
        minutes = int((now - r["pushed"]).total_seconds() // 60)
        if minutes >= STALL_MINUTES:
            stalled.append(f"#{r['number']} {r['branch']} ({minutes} minutes)")
    lines.append("stall: " + ("; ".join(stalled) if stalled else "none"))
    return lines


def main(argv=None, fetch=None, now=None, out=None, sleep=time.sleep):
    argv = sys.argv[1:] if argv is None else argv
    out = out or sys.stdout
    if argv:
        print("board status: this command takes no arguments, run: python tools/board_status.py", file=out)
        return USAGE_EXIT
    try:
        rows = collect(fetch or http_get, sleep)
        lines = render(rows, now or datetime.now(timezone.utc))
    except BoardError as e:
        print(f"board status failed: {e}", file=out)
        return FAIL_EXIT
    except Exception as e:  # a crash blocks: one line, no detail from a body
        print(f"board status failed: unexpected {type(e).__name__}", file=out)
        return FAIL_EXIT
    print("\n".join(lines), file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
