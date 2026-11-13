"""W16: tools/board_status.py with a fake HTTP layer. No network: every request goes to the fake."""
import io
import json
import unittest
import urllib.error
from datetime import datetime, timezone
from unittest import mock

from tools import board_status as bs

SHA1 = "a" * 40
SHA2 = "b" * 40
NOW = datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc)
BASE = "https://api.github.com/repos/Miguel-Shinyenyi/umwayi-os"


def ok(doc):
    return 200, {}, json.dumps(doc).encode()


def pr_item(number=5, title="Add a thing", branch="w16-x", sha=SHA1):
    return {"number": number, "title": title, "head": {"ref": branch, "sha": sha}}


def suite(status="completed", conclusion="success"):
    return {"status": status, "conclusion": conclusion}


def board(prs, details):
    """details: {sha: dict(date=, suites=[...], behind=int, mergeable=)}; returns (fetch, calls)."""
    calls = []

    def fetch(url):
        calls.append(url)
        if url == f"{BASE}/pulls?state=open&per_page=100":
            return ok(prs)
        for number, sha, d in details:
            if url == f"{BASE}/commits/{sha}":
                return ok({"commit": {"committer": {"date": d["date"]}}})
            if url == f"{BASE}/commits/{sha}/check-suites?per_page=100":
                return ok({"total_count": len(d["suites"]), "check_suites": d["suites"]})
            if url == f"{BASE}/compare/main...{sha}":
                return ok({"behind_by": d["behind"]})
            if url == f"{BASE}/pulls/{number}":
                return ok({"mergeable": d["mergeable"]})
        return 404, {}, b"{}"
    return fetch, calls


def run(fetch, now=NOW):
    out = io.StringIO()
    code = bs.main([], fetch=fetch, now=now, out=out, sleep=lambda s: None)
    return code, out.getvalue()


def detail(date="2026-11-13T11:55:00Z", suites=None, behind=0, mergeable=True):
    return {"date": date, "suites": [suite()] if suites is None else suites, "behind": behind, "mergeable": mergeable}


class Normal(unittest.TestCase):
    def test_two_pull_requests_one_line_each_then_the_stall_line(self):
        fetch, _ = board(
            [pr_item(7, "Second | one", "w16-b", SHA2), pr_item(5)],
            [(5, SHA1, detail()), (7, SHA2, detail(date="2026-11-13T11:00:00Z", suites=[suite(), suite("in_progress", None)],
                                                    behind=3, mergeable=False))])
        code, text = run(fetch)
        self.assertEqual(code, 0)
        self.assertEqual(text.splitlines(), [
            "#5 | Add a thing | w16-x | last commit 2026-11-13 11:55Z | ci green | has newest main yes | mergeable",
            "#7 | Second / one | w16-b | last commit 2026-11-13 11:00Z | ci running | has newest main no | conflict",
            "stall: #7 w16-b (60 minutes)",
        ])

    def test_no_stall_when_every_push_is_recent(self):
        fetch, _ = board([pr_item()], [(5, SHA1, detail(date="2026-11-13T11:31:00Z"))])
        self.assertEqual(run(fetch)[1].splitlines()[-1], "stall: none")

    def test_exactly_thirty_minutes_is_a_stall(self):
        fetch, _ = board([pr_item()], [(5, SHA1, detail(date="2026-11-13T11:30:00Z"))])
        self.assertEqual(run(fetch)[1].splitlines()[-1], "stall: #5 w16-x (30 minutes)")

    def test_only_api_github_com_https_is_called(self):
        fetch, calls = board([pr_item()], [(5, SHA1, detail())])
        run(fetch)
        self.assertTrue(calls and all(c.startswith("https://api.github.com/") for c in calls))

    def test_title_control_characters_are_removed(self):
        fetch, _ = board([pr_item(title="a\nb\x1b[31m")], [(5, SHA1, detail())])
        first = run(fetch)[1].splitlines()[0]
        self.assertNotIn("\x1b", first)
        self.assertTrue(first.startswith("#5 | a b [31m | "))


class Empty(unittest.TestCase):
    def test_no_open_pull_requests(self):
        fetch, calls = board([], [])
        self.assertEqual(run(fetch), (0, "no open pull requests\nstall: none\n"))
        self.assertEqual(len(calls), 1)


class Checks(unittest.TestCase):
    def test_no_checks_is_none_and_never_green(self):
        fetch, _ = board([pr_item()], [(5, SHA1, detail(suites=[]))])
        code, text = run(fetch)
        self.assertEqual(code, 0)
        self.assertIn("| ci none |", text)
        self.assertNotIn("green", text)

    def test_a_red_check_makes_the_state_red_even_with_green_and_running(self):
        fetch, _ = board([pr_item()], [(5, SHA1, detail(suites=[suite(), suite("queued", None), suite("completed", "failure")]))])
        self.assertIn("| ci red |", run(fetch)[1])

    def test_skipped_and_neutral_are_green(self):
        fetch, _ = board([pr_item()], [(5, SHA1, detail(suites=[suite(conclusion="skipped"), suite(conclusion="neutral")]))])
        self.assertIn("| ci green |", run(fetch)[1])

    def test_cancelled_is_red(self):
        fetch, _ = board([pr_item()], [(5, SHA1, detail(suites=[suite(conclusion="cancelled")]))])
        self.assertIn("| ci red |", run(fetch)[1])

    def test_an_unknown_conclusion_fails_closed(self):
        fetch, _ = board([pr_item()], [(5, SHA1, detail(suites=[suite(conclusion="surprise")]))])
        code, text = run(fetch)
        self.assertEqual(code, 2)
        self.assertEqual(len(text.splitlines()), 1)

    def test_more_suites_than_one_page_fails_closed(self):
        def fetch(url):
            if url.endswith("per_page=100") and "pulls?" in url:
                return ok([pr_item()])
            if "check-suites" in url:
                return ok({"total_count": 150, "check_suites": [suite()] * 100})
            if url.endswith(SHA1):
                return ok({"commit": {"committer": {"date": "2026-11-13T11:55:00Z"}}})
            return ok({})
        self.assertEqual(run(fetch)[0], 2)


class Failures(unittest.TestCase):
    def assert_one_line_failure(self, fetch):
        code, text = run(fetch)
        self.assertEqual(code, 2)
        self.assertEqual(len(text.splitlines()), 1)
        self.assertTrue(text.startswith("board status failed: "))
        return text

    def test_rate_limited_with_reset_time(self):
        fetch = lambda url: (403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1794571200"}, b'{"message":"API rate limit exceeded"}')
        text = self.assert_one_line_failure(fetch)
        self.assertIn("rate limit", text)
        self.assertIn("2026-11-13", text)

    def test_rate_limited_429(self):
        self.assertIn("rate limit", self.assert_one_line_failure(lambda url: (429, {}, b"")))

    def test_rate_limited_in_the_middle_prints_no_partial_result(self):
        inner, _ = board([pr_item()], [(5, SHA1, detail())])

        def fetch(url):
            if "check-suites" in url:
                return 403, {"x-ratelimit-remaining": "0"}, b"{}"
            return inner(url)
        self.assertIn("rate limit", self.assert_one_line_failure(fetch))

    def test_bad_json(self):
        self.assertIn("not valid JSON", self.assert_one_line_failure(lambda url: (200, {}, b"{not json")))

    def test_bad_utf8(self):
        self.assert_one_line_failure(lambda url: (200, {}, b"\xff\xfe"))

    def test_http_500(self):
        self.assertIn("HTTP 500", self.assert_one_line_failure(lambda url: (500, {}, b"boom")))

    def test_http_404_on_the_detail(self):
        inner, _ = board([pr_item()], [])
        self.assertIn("HTTP 404", self.assert_one_line_failure(inner))

    def test_a_list_that_is_an_object(self):
        self.assert_one_line_failure(lambda url: ok({"message": "x"}))

    def test_a_missing_field(self):
        item = pr_item()
        del item["head"]["sha"]
        fetch, _ = board([item], [])
        self.assertIn("head.sha is missing", self.assert_one_line_failure(fetch))

    def test_a_wrong_type(self):
        fetch, _ = board([pr_item(number="5")], [])
        self.assert_one_line_failure(fetch)

    def test_a_bool_is_not_a_number(self):
        fetch, _ = board([pr_item(number=True)], [])
        self.assert_one_line_failure(fetch)

    def test_a_bad_commit_id(self):
        fetch, _ = board([pr_item(sha="xyz")], [])
        self.assert_one_line_failure(fetch)

    def test_a_bad_time(self):
        fetch, _ = board([pr_item()], [(5, SHA1, detail(date="yesterday"))])
        self.assert_one_line_failure(fetch)

    def test_missing_behind_by(self):
        inner, _ = board([pr_item()], [(5, SHA1, detail())])

        def fetch(url):
            if "/compare/" in url:
                return ok({"status": "ahead"})
            return inner(url)
        self.assertIn("behind_by", self.assert_one_line_failure(fetch))

    def test_mergeable_never_worked_out_fails_closed_after_retries(self):
        fetch, calls = board([pr_item()], [(5, SHA1, detail(mergeable=None))])
        self.assertIn("mergeable", self.assert_one_line_failure(fetch))
        self.assertEqual(sum(1 for c in calls if c.endswith("/pulls/5")), bs.MERGEABLE_TRIES)

    def test_mergeable_worked_out_on_the_second_try(self):
        inner, _ = board([pr_item()], [(5, SHA1, detail())])
        answers = iter([None, True])

        def fetch(url):
            if url.endswith("/pulls/5"):
                return ok({"mergeable": next(answers)})
            return inner(url)
        code, text = run(fetch)
        self.assertEqual(code, 0)
        self.assertIn("| mergeable\n", text)

    def test_mergeable_field_missing(self):
        inner, _ = board([pr_item()], [(5, SHA1, detail())])
        fetch = lambda url: ok({}) if url.endswith("/pulls/5") else inner(url)
        self.assertIn("mergeable is missing", self.assert_one_line_failure(fetch))

    def test_a_full_page_of_pull_requests_fails_closed(self):
        self.assertIn("more than one page", self.assert_one_line_failure(lambda url: ok([pr_item(i) for i in range(100)])))

    def test_the_http_layer_raising_a_board_error(self):
        def fetch(url):
            raise bs.BoardError("the request timed out after 15 seconds")
        self.assertIn("timed out", self.assert_one_line_failure(fetch))

    def test_any_other_crash_blocks_with_one_line_and_no_detail(self):
        def fetch(url):
            raise RuntimeError("secret-looking detail")
        text = self.assert_one_line_failure(fetch)
        self.assertNotIn("secret-looking", text)

    def test_the_wrong_shape_from_the_http_layer(self):
        self.assert_one_line_failure(lambda url: "nope")


class RealLayer(unittest.TestCase):
    """http_get itself, with urllib.request.urlopen replaced; still no network."""

    def test_a_timeout_is_set_on_every_request(self):
        seen = {}

        class Resp:
            status = 200
            headers = {"X-A": "1"}

            def read(self, n):
                return b"[]"

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None):
            seen["timeout"] = timeout
            seen["url"] = req.full_url
            seen["auth"] = req.get_header("Authorization")
            return Resp()
        with mock.patch("urllib.request.urlopen", fake_urlopen):
            status, headers, body = bs.http_get(BASE + "/pulls")
        self.assertEqual((status, body, headers), (200, b"[]", {"x-a": "1"}))
        self.assertEqual(seen["timeout"], bs.TIMEOUT)
        self.assertIsNone(seen["auth"])

    def test_http_error_becomes_a_status(self):
        err = urllib.error.HTTPError(BASE, 403, "forbidden", {"X-RateLimit-Remaining": "0"}, io.BytesIO(b"{}"))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            status, headers, _ = bs.http_get(BASE + "/pulls")
        self.assertEqual((status, headers["x-ratelimit-remaining"]), (403, "0"))

    def test_timeout_and_url_error_become_one_line(self):
        for exc in (TimeoutError(), urllib.error.URLError("dns"), ConnectionResetError()):
            with mock.patch("urllib.request.urlopen", side_effect=exc):
                with self.assertRaises(bs.BoardError):
                    bs.http_get(BASE + "/pulls")

    def test_refuses_any_other_host_or_http(self):
        for url in ("http://api.github.com/x", "https://example.com/x", "file:///etc/passwd"):
            with mock.patch("urllib.request.urlopen") as m:
                with self.assertRaises(bs.BoardError):
                    bs.http_get(url)
                m.assert_not_called()


class Usage(unittest.TestCase):
    def test_an_argument_is_a_usage_error(self):
        out = io.StringIO()
        self.assertEqual(bs.main(["--repo", "x"], fetch=lambda u: 1 / 0, out=out), 64)
        self.assertEqual(len(out.getvalue().splitlines()), 1)

    def test_no_em_dash_in_the_script(self):
        with open(bs.__file__, encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("\u2014", text)


if __name__ == "__main__":
    unittest.main()
