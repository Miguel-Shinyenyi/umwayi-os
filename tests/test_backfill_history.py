"""W19: tools/backfill_history.py against a local fake GitHub server on 127.0.0.1. No real network."""
import io
import json
import os
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from tools import backfill_history as bh

NOW = datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc)
SHA = "c" * 40
SECRET = "PLANTED-PRIVATE-SENTENCE the owner's bank is at 12 Hidden Road"
LIST_PATH = "/repos/Miguel-Shinyenyi/umwayi-os/pulls"


class Fake(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), Handler)
        self.routes = {}  # path -> (status, headers, body bytes) or a callable returning that
        self.seen = []  # (path, headers dict)
        self.thread = threading.Thread(target=lambda: self.serve_forever(poll_interval=0.02), daemon=True)
        self.thread.start()

    def handle_error(self, request, client_address):
        pass  # a client that timed out and left is expected

    def stop(self):
        self.shutdown()
        self.server_close()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        self.server.seen.append((self.path, dict(self.headers)))
        route = self.server.routes.get(path)
        if callable(route):
            route = route(self)
        if route is None:
            route = (404, {}, b"{}")
        status, headers, body = route
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def j(doc, status=200, headers=None):
    return status, headers or {}, json.dumps(doc).encode()


def pr_path(n, tail=""):
    return f"/repos/Miguel-Shinyenyi/umwayi-os/pulls/{n}{tail}"


def pr_doc(n=5, title="W16: " + SECRET, **over):
    doc = {
        "number": n, "title": title, "body": SECRET, "merged": True,
        "created_at": "2026-11-12T10:00:00Z", "merged_at": "2026-11-12T12:30:00Z",
        "changed_files": 4, "additions": 100, "deletions": 20, "commits": 3, "review_comments": 2,
        "labels": [{"name": "docs", "description": SECRET}],
        "head": {"ref": "branch-" + SECRET.split()[0], "sha": SHA},
        "user": {"login": "someone-private"},
    }
    doc.update(over)
    return doc


def runs_doc(runs):
    return {"total_count": len(runs), "check_runs": runs}


def run_doc(name, conclusion, started, rid):
    return {"name": name, "conclusion": conclusion, "started_at": started, "id": rid}


class Base(unittest.TestCase):
    def setUp(self):
        self.server = Fake()
        self.addCleanup(self.server.stop)
        base = f"http://127.0.0.1:{self.server.server_address[1]}"
        p = mock.patch.object(bh, "_resolve", lambda url: url.replace("https://api.github.com", base, 1))
        p.start()
        self.addCleanup(p.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = os.path.join(self.tmp.name, "history.jsonl")

    def add_pr(self, n, pr=None, reviews=None, runs=None):
        r = self.server.routes
        r[pr_path(n)] = j(pr if pr is not None else pr_doc(n))
        r[pr_path(n, "/reviews")] = j(reviews if reviews is not None else [{"body": SECRET, "state": "APPROVED"}])
        r[f"/repos/Miguel-Shinyenyi/umwayi-os/commits/{SHA}/check-runs"] = j(
            runs if runs is not None else runs_doc([run_doc("test", "success", "2026-11-12T10:05:00Z", 1)]))

    def list_prs(self, numbers):
        self.server.routes[LIST_PATH] = j([{"number": n, "title": SECRET} for n in numbers])

    def run_main(self, extra=None, timeout=5):
        buf = io.StringIO()
        code = bh.main(["--out", self.out] + (extra or []), now=NOW, stdout=buf, timeout=timeout)
        return code, buf.getvalue()

    def lines(self):
        return [json.loads(x) for x in Path(self.out).read_text().splitlines()]


class Normal(Base):
    def test_normal_pr(self):
        self.list_prs([5])
        self.add_pr(5, runs=runs_doc([
            run_doc("a", "failure", "2026-11-12T10:05:00Z", 1),
            run_doc("a", "success", "2026-11-12T10:20:00Z", 2),
            run_doc("b", "success", "2026-11-12T10:05:00Z", 3),
            run_doc("c", "failure", "2026-11-12T10:05:00Z", 4),
            run_doc("d", "skipped", "2026-11-12T10:05:00Z", 5),
        ]))
        code, out = self.run_main()
        self.assertEqual(code, 0, out)
        header, rec = self.lines()
        self.assertEqual(header, {"schema_version": 1, "date": "2026-11-13", "complete": True})
        self.assertEqual(list(rec), list(bh.FIELDS))
        self.assertEqual(rec, {
            "number": 5, "merged": True, "created": "2026-11-12", "merged_date": "2026-11-12",
            "files_changed": 4, "lines_added": 100, "lines_removed": 20, "commits": 3, "reviews": 1,
            "review_comments": 2, "checks_success": 2, "checks_failure": 1, "checks_other": 1,
            "checks_rerun_after_failure": 1, "minutes_to_merge": 150, "labels": ["docs"], "task_kind": "W16",
        })

    def test_unmerged_pr_has_null_merge_fields(self):
        self.list_prs([5])
        self.add_pr(5, pr_doc(5, merged=False, merged_at=None))
        self.assertEqual(self.run_main()[0], 0)
        rec = self.lines()[1]
        self.assertIs(rec["merged"], False)
        self.assertIsNone(rec["merged_date"])
        self.assertIsNone(rec["minutes_to_merge"])

    def test_task_kinds(self):
        for title, kind in [("W9.9: x", "W9"), ("UI.3 look", "UI"), ("CI: x", "CI"), ("docs: x", "docs"),
                            ("Docs fix", "docs"), ("L13.2 x", "L13"), ("Add a thing", "unknown"),
                            ("Wonder", "unknown"), ("WIP W9", "unknown"), ("", "unknown")]:
            self.assertEqual(bh.task_kind(title), kind, title)


class Unknown(Base):
    def test_missing_fields_give_unknown(self):
        self.list_prs([7])
        self.add_pr(7, {"number": 7}, reviews=[], runs=runs_doc([]))
        self.server.routes[pr_path(7)] = j({"number": 7})  # no head sha either: no check runs request
        code, out = self.run_main()
        self.assertEqual(code, 0, out)
        rec = self.lines()[1]
        for key in bh.FIELDS:
            if key == "number":
                self.assertEqual(rec[key], 7)
            elif key == "reviews":
                self.assertEqual(rec[key], 0)
            elif key == "labels":
                self.assertEqual(rec[key], "unknown")
            else:
                self.assertEqual(rec[key], "unknown", key)
        self.assertNotIn("model", rec)

    def test_wrong_types_give_unknown(self):
        self.list_prs([7])
        self.add_pr(7, pr_doc(7, changed_files="4", additions=True, deletions=-1, created_at="yesterday"))
        self.assertEqual(self.run_main()[0], 0)
        rec = self.lines()[1]
        for key in ("files_changed", "lines_added", "lines_removed", "created", "minutes_to_merge"):
            self.assertEqual(rec[key], "unknown", key)

    def test_odd_label_is_unknown_not_copied(self):
        self.list_prs([7])
        self.add_pr(7, pr_doc(7, labels=[{"name": SECRET}, {"name": "ci"}]))
        self.assertEqual(self.run_main()[0], 0)
        self.assertEqual(self.lines()[1]["labels"], ["ci", "unknown"])

    def test_check_runs_cut_off_give_unknown(self):
        self.list_prs([7])
        doc = runs_doc([run_doc("a", "success", "2026-11-12T10:05:00Z", 1)])
        doc["total_count"] = 150
        self.add_pr(7, runs=doc)
        self.assertEqual(self.run_main()[0], 0)
        rec = self.lines()[1]
        self.assertEqual([rec[k] for k in ("checks_success", "checks_failure", "checks_other",
                                           "checks_rerun_after_failure")], ["unknown"] * 4)


class FailClosed(Base):
    def test_rate_limit_stops_cleanly_with_partial_file(self):
        self.list_prs([1, 2])
        self.add_pr(1)
        self.server.routes[pr_path(1)] = j(pr_doc(1), headers={"X-RateLimit-Remaining": "2"})
        self.add_pr(2)
        code, out = self.run_main()
        self.assertEqual(code, 2)
        self.assertIn("rate limit", out)
        self.assertIn("--after", out)
        lines = self.lines()
        self.assertFalse(lines[0]["complete"])
        self.assertEqual([r["number"] for r in lines[1:]], [1])
        # no request was made for pull request 2 after the budget ran out
        self.assertFalse(any("/pulls/2" in p for p, _ in self.server.seen))

    def test_rate_limit_answer_before_any_record_writes_nothing(self):
        self.server.routes[LIST_PATH] = j({"message": "API rate limit exceeded"}, 403,
                                          {"X-RateLimit-Remaining": "0"})
        code, out = self.run_main()
        self.assertEqual(code, 2)
        self.assertIn("rate limit", out)
        self.assertFalse(os.path.exists(self.out))

    def test_429_stops(self):
        self.server.routes[LIST_PATH] = j({}, 429)
        code, out = self.run_main()
        self.assertEqual(code, 2)
        self.assertFalse(os.path.exists(self.out))

    def test_timeout_fails_closed(self):
        self.server.routes[LIST_PATH] = lambda h: (time.sleep(0.8), j([]))[1]
        code, out = self.run_main(timeout=0.2)
        self.assertEqual(code, 2)
        self.assertTrue(out.startswith("backfill history failed:"), out)
        self.assertIn("timed out", out)
        self.assertFalse(os.path.exists(self.out))

    def test_malformed_json_fails_closed(self):
        self.server.routes[LIST_PATH] = (200, {}, b"{not json")
        code, out = self.run_main()
        self.assertEqual(code, 2)
        self.assertIn("not valid JSON", out)
        self.assertFalse(os.path.exists(self.out))

    def test_wrong_shape_fails_closed(self):
        self.server.routes[LIST_PATH] = j({"not": "a list"})
        self.assertEqual(self.run_main()[0], 2)
        self.list_prs([5])
        self.server.routes[pr_path(5)] = j([1, 2])
        self.assertEqual(self.run_main()[0], 2)
        self.assertFalse(os.path.exists(self.out))

    def test_http_error_fails_closed(self):
        self.list_prs([5])  # the pull request itself answers 404
        code, out = self.run_main()
        self.assertEqual(code, 2)
        self.assertIn("HTTP 404", out)

    def test_redirect_is_not_followed(self):
        self.server.routes[LIST_PATH] = (302, {"Location": "https://evil.example/x"}, b"")
        code, out = self.run_main()
        self.assertEqual(code, 2)
        self.assertEqual(len(self.server.seen), 1)

    def test_host_other_than_github_is_refused(self):
        for url in ["https://evil.example/x", "http://api.github.com/x", "https://api.github.com.evil.example/x",
                    "https://user@api.github.com/x", "https://api.github.com:8443/x", "https://127.0.0.1/x",
                    "file:///etc/passwd"]:
            with self.assertRaises(bh.BackfillError, msg=url):
                bh.http_get(url)
        self.assertEqual(self.server.seen, [])

    def test_unexpected_error_exits_2(self):
        def boom(url):
            raise RuntimeError(SECRET)
        buf = io.StringIO()
        code = bh.main(["--out", self.out], fetch=boom, now=NOW, stdout=buf)
        self.assertEqual(code, 2)
        self.assertNotIn("PLANTED", buf.getvalue())


class Privacy(Base):
    def test_planted_text_never_in_output_bytes(self):
        self.list_prs([5, 6])
        file_name = "secret-" + SECRET.replace(" ", "_") + ".py"
        for n in (5, 6):
            doc = pr_doc(n, title="W9: " + SECRET)
            doc["head"]["ref"] = SECRET
            doc["files"] = [{"filename": file_name}]
            self.add_pr(n, doc, reviews=[{"body": SECRET, "user": {"login": SECRET}, "state": "COMMENTED"}])
        self.server.routes["/repos/Miguel-Shinyenyi/umwayi-os/pulls/5/comments"] = j([{"body": SECRET}])
        code, out = self.run_main()
        self.assertEqual(code, 0, out)
        data = Path(self.out).read_bytes()
        for needle in (b"PLANTED", b"Hidden Road", b"bank", b"secret-", b"someone-private", b"branch-", b".py"):
            self.assertNotIn(needle, data)
        self.assertNotIn(b"PLANTED", out.encode())
        self.assertEqual(self.lines()[1]["task_kind"], "W9")

    def test_only_allowed_keys(self):
        self.list_prs([5])
        self.add_pr(5)
        self.run_main()
        for rec in self.lines()[1:]:
            self.assertEqual(list(rec), list(bh.FIELDS))
        self.assertEqual(list(self.lines()[0]), list(bh.HEADER_FIELDS))
        with self.assertRaises(bh.BackfillError):
            bh.render([{"number": 1, "title": "x"}], True, "2026-11-13")

    def test_no_token_is_read_or_sent(self):
        self.list_prs([5])
        self.add_pr(5)
        env = {"GITHUB_TOKEN": "tok-SENTINEL", "GH_TOKEN": "tok-SENTINEL", "HTTPS_PROXY": "http://127.0.0.1:9"}
        with mock.patch.dict(os.environ, env):
            self.assertEqual(self.run_main()[0], 0)
        self.assertTrue(self.server.seen)
        for path, headers in self.server.seen:
            self.assertNotIn("SENTINEL", json.dumps(headers))
            self.assertFalse(any(k.lower() == "authorization" for k in headers))
        src = Path(bh.__file__).read_text()
        for word in ("os.environ", "getenv", "import os", "Authorization"):
            self.assertNotIn(word, src.replace("never reads the environment", ""))


class Stable(Base):
    def test_sorted_and_stable_across_two_runs(self):
        self.list_prs([9, 3, 6])
        for n in (9, 3, 6):
            self.add_pr(n)
        self.assertEqual(self.run_main()[0], 0)
        first = Path(self.out).read_bytes()
        self.assertEqual([r["number"] for r in self.lines()[1:]], [3, 6, 9])
        Path(self.out).unlink()
        self.assertEqual(self.run_main()[0], 0)
        self.assertEqual(first, Path(self.out).read_bytes())
        self.assertNotIn(b"\xe2\x80\x94", first)

    def test_after_and_max(self):
        self.list_prs([1, 2, 3, 4])
        for n in (1, 2, 3, 4):
            self.add_pr(n)
        self.assertEqual(self.run_main(["--after", "1", "--max", "2"])[0], 0)
        self.assertEqual([r["number"] for r in self.lines()[1:]], [2, 3])


class Usage(unittest.TestCase):
    def test_usage_exit_64(self):
        for argv in ([], ["--out"], ["--out", "a", "b"], ["--max", "3"], ["--out", "a", "--max", "0"],
                     ["--out", "a", "--max", "x"], ["--out", "a", "--after", "-1"], ["--out", "a", "--out", "b"],
                     ["--bogus"], ["--out", "--max"]):
            buf = io.StringIO()
            self.assertEqual(bh.main(argv, fetch=lambda u: self.fail("no request"), stdout=buf), 64, argv)


if __name__ == "__main__":
    unittest.main()
