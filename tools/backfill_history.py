"""W19: backfill history. Turns the public pull request and CI history of Miguel-Shinyenyi/umwayi-os into derived records.

Standard library only. It reads the public GitHub REST API over HTTPS with urllib, to api.github.com and nothing else,
with no token (it never reads the environment), with a timeout of 15 seconds on every request, and it never follows a
redirect. It never runs git and writes nothing except the one output file the caller names.

  python tools/backfill_history.py --out history.jsonl [--max N] [--after NUMBER]

  --out FILE      the JSON lines file to write (required)
  --max N         read at most N pull requests (default 100)
  --after NUMBER  skip every pull request whose number is NUMBER or lower (to carry on after a rate limit stop)

The output is JSON lines. Line 1 is a header object: schema_version, date (UTC, the day of the run), complete (true, or
false when the rate limit stopped the run early). Then one object per pull request, sorted by number, with the keys of
FIELDS in that order and no others. Only counts, durations, dates, label names and a task kind are written. A title, a
body, a comment, a branch name, a file name or an author name is never written: the title is read only to find its
prefix. A value GitHub does not give is the string "unknown", never a guess. There is no model field because GitHub does
not record which model built a pull request.

The task kind is guessed only from the title prefix (W9, W16, L13, UI, CI, docs) and is "unknown" otherwise.

GitHub allows 60 requests an hour per address without a token. Each pull request costs 3 requests (the pull request, its
reviews, its check runs). The run stops cleanly when the limit is reached: it writes the pull requests it finished, with
complete false in the header, prints one line and exits 2.

Fail closed: an HTTP error, a timeout, a redirect, bad JSON, an answer of the wrong shape or a host other than
api.github.com prints ONE line that starts with "backfill history failed:" and exits 2 with no output file written.

Exit codes: 0 done, 2 a failure of any kind (a crash blocks), 64 wrong use.
"""
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

OWNER = "Miguel-Shinyenyi"
REPO_NAME = "umwayi-os"
API = "https://api.github.com"
HOST = "api.github.com"
SCHEMA_VERSION = 1
TIMEOUT = 15  # seconds, on every request
PAGE = 100
DEFAULT_MAX = 100
MAX_LIST_PAGES = 20
REQUESTS_PER_PR = 3
MAX_BODY = 5_000_000
USAGE_EXIT = 64
FAIL_EXIT = 2
UNKNOWN = "unknown"

# The strict allow list: the only keys that may be written for a pull request, in this order.
FIELDS = (
    "number",
    "merged",
    "created",
    "merged_date",
    "files_changed",
    "lines_added",
    "lines_removed",
    "commits",
    "reviews",
    "review_comments",
    "checks_success",
    "checks_failure",
    "checks_other",
    "checks_rerun_after_failure",
    "minutes_to_merge",
    "labels",
    "task_kind",
)
HEADER_FIELDS = ("schema_version", "date", "complete")

_TIME = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
_SHA = re.compile(r"[0-9a-f]{40}")
_KIND = re.compile(r"^\W*(W\d{1,3}|L\d{1,2}|UI|CI|DOCS)(?![A-Za-z0-9])", re.IGNORECASE)
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _.:/-]{0,39}")
_FAILED = frozenset({"failure", "timed_out"})


class BackfillError(Exception):
    """Carries the one line that is printed. Never carries a body, a header value or a title."""


class RateLimited(BackfillError):
    """The 60 requests an hour limit is reached (or about to be)."""


# ---------------------------------------------------------------- the HTTP layer (tests point it at 127.0.0.1)

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _resolve(url):
    """The address actually opened. Tests replace this to reach a fake server on 127.0.0.1; it is never changed in use."""
    return url


def http_get(url, timeout=TIMEOUT):
    """(status, headers with lower case names, body bytes). Only https to api.github.com. Raises BackfillError."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.hostname != HOST or parts.port not in (None, 443) or parts.username:
        raise BackfillError("refused a request outside https://api.github.com")
    req = urllib.request.Request(_resolve(url), headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "umwayi-os-backfill-history",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    # No proxy handler: it would read proxy settings from the environment. No redirect: it could leave api.github.com.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as resp:
            body = resp.read(MAX_BODY + 1)
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, body
    except urllib.error.HTTPError as e:
        try:
            body = e.read(MAX_BODY + 1)
        except Exception:
            body = b""
        return e.code, {k.lower(): v for k, v in e.headers.items()}, body
    except TimeoutError:
        raise BackfillError(f"the request timed out after {timeout} seconds") from None
    except OSError:  # includes URLError and a timeout wrapped by urllib
        if "timed out" in repr(sys.exc_info()[1]):
            raise BackfillError(f"the request timed out after {timeout} seconds") from None
        raise BackfillError("the network request failed") from None


class Client:
    """Wraps one fetch function; counts the budget from the rate limit headers; decodes JSON; fails closed."""

    def __init__(self, fetch):
        self.fetch = fetch
        self.remaining = None  # unknown until the first answer

    def can_afford(self, n):
        return self.remaining is None or self.remaining >= n

    def get(self, path, label):
        if self.remaining is not None and self.remaining < 1:
            raise RateLimited("GitHub rate limit reached, try again later")
        status, headers, body = self.fetch(API + path)
        if not isinstance(status, int) or not isinstance(headers, dict) or not isinstance(body, (bytes, bytearray)):
            raise BackfillError(f"{label}: the HTTP layer gave an answer of the wrong shape")
        left = headers.get("x-ratelimit-remaining", "")
        if isinstance(left, str) and left.isdigit():
            self.remaining = int(left)
        if status == 429 or (status == 403 and (self.remaining == 0 or b"rate limit" in bytes(body).lower())):
            self.remaining = 0
            raise RateLimited("GitHub rate limit reached, try again later")
        if status != 200:
            raise BackfillError(f"{label}: GitHub answered HTTP {status}")
        if len(body) > MAX_BODY:
            raise BackfillError(f"{label}: the answer is too large")
        try:
            return json.loads(bytes(body).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise BackfillError(f"{label}: the answer is not valid JSON") from None


# ---------------------------------------------------------------- small readers (a missing field is "unknown")

def _count(doc, key):
    v = doc.get(key) if isinstance(doc, dict) else None
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else UNKNOWN


def _time(text):
    if isinstance(text, str) and _TIME.fullmatch(text):
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return None


def task_kind(title):
    """W9, W16, L13, UI, CI, docs from the title prefix, else unknown. The title is read here and nowhere else."""
    if not isinstance(title, str):
        return UNKNOWN
    m = _KIND.match(title)
    if not m:
        return UNKNOWN
    kind = m.group(1).upper()
    return "docs" if kind == "DOCS" else kind


def read_labels(doc):
    """Sorted label names that look like plain tags; a label that does not is counted as "unknown"."""
    raw = doc.get("labels") if isinstance(doc, dict) else None
    if not isinstance(raw, list):
        return UNKNOWN
    names = set()
    for item in raw:
        name = item.get("name") if isinstance(item, dict) else None
        names.add(name if isinstance(name, str) and _LABEL.fullmatch(name) else UNKNOWN)
    return sorted(names)


# ---------------------------------------------------------------- one fetch per kind of fact

def fetch_pr_list(client, after=0, limit=DEFAULT_MAX):
    """The numbers of pull requests (open and closed) above `after`, oldest first, at most `limit`."""
    numbers = []
    for page in range(1, MAX_LIST_PAGES + 1):
        doc = client.get(
            f"/repos/{OWNER}/{REPO_NAME}/pulls?state=all&sort=created&direction=asc&per_page={PAGE}&page={page}",
            "pull request list")
        if not isinstance(doc, list):
            raise BackfillError("pull request list: the answer is not a list")
        for item in doc:
            n = item.get("number") if isinstance(item, dict) else None
            if not isinstance(n, int) or isinstance(n, bool) or n < 1:
                raise BackfillError("pull request list: an entry has no number")
            if n > after:
                numbers.append(n)
        if len(doc) < PAGE or len(numbers) >= limit:
            break
    return sorted(set(numbers))[:limit]


def fetch_pr(client, number):
    doc = client.get(f"/repos/{OWNER}/{REPO_NAME}/pulls/{number}", f"pull request {number}")
    if not isinstance(doc, dict):
        raise BackfillError(f"pull request {number}: the answer is not an object")
    return doc


def fetch_reviews(client, number):
    doc = client.get(f"/repos/{OWNER}/{REPO_NAME}/pulls/{number}/reviews?per_page={PAGE}", f"pull request {number} reviews")
    if not isinstance(doc, list):
        raise BackfillError(f"pull request {number} reviews: the answer is not a list")
    return doc


def fetch_check_runs(client, number, sha):
    doc = client.get(f"/repos/{OWNER}/{REPO_NAME}/commits/{sha}/check-runs?filter=all&per_page={PAGE}",
                     f"pull request {number} check runs")
    if not isinstance(doc, dict) or not isinstance(doc.get("check_runs"), list):
        raise BackfillError(f"pull request {number} check runs: the answer has the wrong shape")
    return doc


# ---------------------------------------------------------------- derived facts

def review_count(reviews):
    return len(reviews) if len(reviews) < PAGE else UNKNOWN  # a full page may hide more


def check_counts(runs_doc):
    """(success, failure, other, rerun_after_failure) of the latest run of each check, or four "unknown"."""
    runs = runs_doc["check_runs"]
    total = runs_doc.get("total_count")
    if not isinstance(total, int) or total != len(runs):
        return (UNKNOWN,) * 4
    by_name = {}
    for r in runs:
        if not isinstance(r, dict) or not isinstance(r.get("name"), str):
            return (UNKNOWN,) * 4
        started = r.get("started_at") if isinstance(r.get("started_at"), str) else ""
        rid = r.get("id") if isinstance(r.get("id"), int) else 0
        by_name.setdefault(r["name"], []).append((started, rid, r.get("conclusion")))
    ok = bad = other = rerun = 0
    for attempts in by_name.values():
        attempts.sort(key=lambda a: (a[0], a[1]))
        latest = attempts[-1][2]
        if latest == "success":
            ok += 1
            if any(a[2] in _FAILED for a in attempts[:-1]):
                rerun += 1
        elif latest in _FAILED:
            bad += 1
        else:
            other += 1
    return ok, bad, other, rerun


def derive(number, pr, reviews, runs_doc):
    """The record for one pull request, built from FIELDS only. No text from the inputs is copied except by the readers."""
    created_at = _time(pr.get("created_at"))
    merged_flag = pr.get("merged")
    merged_at = _time(pr.get("merged_at"))
    if merged_flag is True:
        merged = True
    elif merged_flag is False:
        merged = False
    else:
        merged = UNKNOWN
    if merged is False:
        merged_date, minutes = None, None
    elif merged is True and merged_at is None:
        merged_date = minutes = UNKNOWN
    elif merged is True:
        merged_date = merged_at.strftime("%Y-%m-%d")
        minutes = int((merged_at - created_at).total_seconds() // 60) if created_at else UNKNOWN
        if minutes != UNKNOWN and minutes < 0:
            minutes = UNKNOWN
    else:
        merged_date = minutes = UNKNOWN
    ok, bad, other, rerun = runs_doc if isinstance(runs_doc, tuple) else (UNKNOWN,) * 4
    rec = {
        "number": number,
        "merged": merged,
        "created": created_at.strftime("%Y-%m-%d") if created_at else UNKNOWN,
        "merged_date": merged_date,
        "files_changed": _count(pr, "changed_files"),
        "lines_added": _count(pr, "additions"),
        "lines_removed": _count(pr, "deletions"),
        "commits": _count(pr, "commits"),
        "reviews": review_count(reviews) if reviews is not None else UNKNOWN,
        "review_comments": _count(pr, "review_comments"),
        "checks_success": ok,
        "checks_failure": bad,
        "checks_other": other,
        "checks_rerun_after_failure": rerun,
        "minutes_to_merge": minutes,
        "labels": read_labels(pr),
        "task_kind": task_kind(pr.get("title")),
    }
    return {k: rec[k] for k in FIELDS}  # the allow list, in order


def head_sha(pr):
    head = pr.get("head")
    sha = head.get("sha") if isinstance(head, dict) else None
    return sha if isinstance(sha, str) and _SHA.fullmatch(sha) else None


def collect(client, after=0, limit=DEFAULT_MAX):
    """(records sorted by number, complete flag). Raises BackfillError. A rate limit after some work gives complete False."""
    numbers = fetch_pr_list(client, after, limit)
    records = []
    for number in numbers:
        if not client.can_afford(REQUESTS_PER_PR):
            return records, False
        try:
            pr = fetch_pr(client, number)
            reviews = fetch_reviews(client, number)
            sha = head_sha(pr)
            runs = check_counts(fetch_check_runs(client, number, sha)) if sha else None
        except RateLimited:
            if not records:
                raise
            return records, False
        records.append(derive(number, pr, reviews, runs))
    records.sort(key=lambda r: r["number"])
    return records, True


def render(records, complete, today):
    """The JSON lines text: a header, then one line per record. Refuses any key outside the allow list."""
    header = {"schema_version": SCHEMA_VERSION, "date": today, "complete": complete}
    lines = [json.dumps(header, separators=(",", ":"))]
    for r in records:
        if tuple(r) != FIELDS:
            raise BackfillError("a record has keys outside the allow list")
        lines.append(json.dumps(r, separators=(",", ":"), ensure_ascii=True))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- the command

def _parse(argv):
    out = None
    limit = DEFAULT_MAX
    after = 0
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--out", "--max", "--after") and i + 1 < len(argv):
            v = argv[i + 1]
            if a == "--out":
                if out is not None or not v or v.startswith("-"):
                    return None
                out = v
            else:
                if not v.isdigit() or (a == "--max" and int(v) < 1):
                    return None
                if a == "--max":
                    limit = int(v)
                else:
                    after = int(v)
            i += 2
        else:
            return None
    return (out, limit, after) if out else None


def main(argv=None, fetch=None, now=None, stdout=None, timeout=TIMEOUT):
    argv = sys.argv[1:] if argv is None else argv
    stdout = stdout or sys.stdout
    parsed = _parse(argv)
    if parsed is None:
        print("backfill history: usage: python tools/backfill_history.py --out FILE [--max N] [--after NUMBER]", file=stdout)
        return USAGE_EXIT
    path, limit, after = parsed
    if fetch is None:
        def fetch(url):
            return http_get(url, timeout)
    stopped = None
    try:
        client = Client(fetch)
        try:
            records, complete = collect(client, after, limit)
        except RateLimited as e:
            raise BackfillError(str(e)) from None
        today = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
        text = render(records, complete, today)
        if not complete:
            stopped = "GitHub rate limit reached, wrote the pull requests finished so far, carry on with --after " + (
                str(records[-1]["number"]) if records else "0")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    except BackfillError as e:
        print(f"backfill history failed: {e}", file=stdout)
        return FAIL_EXIT
    except OSError:
        print("backfill history failed: the output file could not be written", file=stdout)
        return FAIL_EXIT
    except Exception as e:  # a crash blocks: one line, no detail from a body
        print(f"backfill history failed: unexpected {type(e).__name__}", file=stdout)
        return FAIL_EXIT
    if stopped:
        print(f"backfill history failed: {stopped}", file=stdout)
        return FAIL_EXIT
    print(f"backfill history: wrote {len(records)} pull requests", file=stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
