"""Whole-system scenarios for the local backend (W6.10, W6.R16.2 and W6.R16.10): `umwayi serve` as a real child process
and a client that speaks the page client's requests, in Python (`http.client`) and in Node (the real `ui/src/api/client.js`).

What each scenario fixes is a sentence of the owner's rule 10 and of docs/serve.md: the token lifecycle, a wrong or
expired token, a wrong Host or Origin, the kill switch turned on in the middle of a run and no route that turns it off,
the queue (add, answer, close), a crash and a restart, the logbook entries, nothing written outside the root, loopback
only. The helpers stay here, in tests/, and are not shipped.

Standard library only; the Node scenario is skipped when Node is not installed (the Node tests of `ui/` run in their own
CI job). Dates are the real ones: the server reads the system clock.
"""

import http.client
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.serve.support import (REPO, SENTINEL, TOKEN2, Server, logbook_entries, make_root, parse_response,
                                 snapshot_tree)
from tests.serve.test_wire import far, run_serve, today
from umwayi import logbook, servetoken

UNSET = object()
FORBIDDEN_IN_ROOT = ("umt1_",)  # the shape of a token: it must never be found in a file of the root


def cli(root, *args, env=None):
    """The command line, as the owner would run it, in a child process with a HOME of its own."""
    e = dict(os.environ, PYTHONPATH=str(REPO), HOME=tempfile.mkdtemp(prefix="umwayi-home-"))
    e.update(env or {})
    return subprocess.run([sys.executable, "-m", "umwayi", "--root", str(root), *args], capture_output=True, text=True,
                          timeout=60, env=e, cwd=str(REPO), stdin=subprocess.DEVNULL)


class Page:
    """A client that sends what the page client sends: `Authorization: Bearer`, `Origin` on a POST, JSON, relative paths,
    and the fetch metadata a same-origin `fetch` carries. One new connection per request, as the server closes each."""

    # The client keeps under the server's own limits (docs/serve.md: 10 a second overall, read 5, write 2) with a margin, so
    # a scenario that sends many requests tests the pipeline and not the rate limit. Failed tokens are not paced (they are
    # counted by the throttle, which a scenario can test by name).
    LIMITS = {"auth": (8.0, 20), "GET": (4.0, 14), "POST": (1.6, 4)}

    def __init__(self, server, token):
        self.server, self.token = server, token
        self.buckets = {k: [float(v[1]), time.monotonic()] for k, v in self.LIMITS.items()}

    def pace(self, method):
        for key in ("auth", "POST" if method == "POST" else "GET"):
            rate, burst = self.LIMITS[key]
            b = self.buckets[key]
            while True:
                now = time.monotonic()
                b[0] = min(float(burst), b[0] + (now - b[1]) * rate)
                b[1] = now
                if b[0] >= 1.0:
                    b[0] -= 1.0
                    break
                time.sleep((1.0 - b[0]) / rate + 0.01)

    @property
    def origin(self):
        return f"http://127.0.0.1:{self.server.port}"

    def call(self, method, path, body=None, token=UNSET, origin=UNSET, host=None, extra=None):
        token = self.token if token is UNSET else token
        if token == self.token:
            self.pace(method)
        origin = self.origin if origin is UNSET else origin
        h = {"Host": host or f"127.0.0.1:{self.server.port}", "Sec-Fetch-Site": "same-origin",
             "Sec-Fetch-Mode": "same-origin", "Sec-Fetch-Dest": "empty"}
        if token is not None:
            h["Authorization"] = f"Bearer {token}"
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
        if method != "GET" and origin is not None:
            h["Origin"] = origin
        elif method == "GET" and origin is not None and origin is not self.origin:
            h["Origin"] = origin
        h.update(extra or {})
        c = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=15)
        try:
            c.request(method, path, body=data if method == "POST" else None, headers=h)
            r = c.getresponse()
            raw = r.read()
            headers = {k.lower(): v for k, v in r.getheaders()}
            try:
                env = json.loads(raw.decode("utf-8")) if raw.startswith(b"{") else None
            except ValueError:
                env = None
            return r.status, headers, env, raw
        finally:
            c.close()

    def word(self, *a, **kw):
        st, _h, env, _raw = self.call(*a, **kw)
        return st, (env or {}).get("word")


class Scenario(unittest.TestCase):
    """A root with a token made the way the owner makes it (`servetoken.create` on a terminal), in a temporary folder."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        (self.tmp / "root").mkdir()
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.root = make_root(self.tmp / "root", token=None)
        made = servetoken.create(self.root, 30, today(), True)
        self.assertEqual(made.code, 0, made.lines)
        self.token = made.lines[0].split(": ", 1)[1]
        self.assertRegex(self.token, r"^umt1_[A-Za-z0-9_-]{43}$")

    def server(self, **kw):
        s = Server(self.root, home=self.home, **kw)
        return s

    def entries(self, source="umwayi serve"):
        return [e for e in logbook_entries(self.root) if e.source == source]

    def request_entries(self):
        return [e for e in self.entries() if e.added.startswith("Request ")]

    def queue_text(self):
        return (self.root / "queue.md").read_text()

    def no_token_in_root(self, *tokens):
        for p in sorted(Path(self.root).rglob("*")):
            if p.is_file():
                data = p.read_bytes()
                for t in tokens:
                    self.assertNotIn(t.encode(), data, f"a token is in {p}")


# ------------------------------------------------------------------------------------------------ the token


class TokenLifecycle(Scenario):
    def test_create_start_rotate_revoke_create_with_a_running_server(self):
        record_path = self.root / ".umwayi" / "serve.token"
        self.assertEqual(oct(record_path.stat().st_mode & 0o777), "0o600")
        rec = json.loads(record_path.read_text())
        self.assertEqual(sorted(rec), ["created", "expires", "id", "schema", "sha256"])
        self.assertNotIn(self.token, record_path.read_text())  # only the fingerprint is kept
        with self.server() as s:
            page = Page(s, self.token)
            st, _h, env, _raw = page.call("GET", "/v1/status")
            self.assertEqual((st, env["word"], env["data"]["token"]["id"]), (200, "done", rec["id"]))
            # rotate: the old token stops on the next request, the new one starts, no restart
            rotated = servetoken.rotate(self.root, 30, today(), True)
            self.assertEqual(rotated.code, 0)
            new = rotated.lines[0].split(": ", 1)[1]
            self.assertNotEqual(new, self.token)
            self.assertEqual(page.word("GET", "/v1/status"), (401, "token"))
            self.assertEqual(page.word("GET", "/v1/status", token=new), (200, "done"))
            # revoke: every request is refused, the server keeps running and still serves the page's refusal
            self.assertEqual(servetoken.revoke(self.root, today()).code, 0)
            self.assertFalse(record_path.exists())
            self.assertEqual(page.word("GET", "/v1/status", token=new), (401, "token"))
            self.assertEqual(page.word("GET", "/v1/queue", token=self.token), (401, "token"))
            # a new token after the revoke works at once
            again = servetoken.create(self.root, 30, today(), True)
            self.assertEqual(again.code, 0)
            newest = again.lines[0].split(": ", 1)[1]
            self.assertEqual(page.word("GET", "/v1/status", token=newest), (200, "done"))
            self.assertEqual(page.word("GET", "/v1/status", token=new), (401, "token"))
            code = s.stop()
        self.assertEqual(code, 0)
        added = [e.added for e in self.entries("umwayi serve")]
        self.assertTrue(any(a.startswith("Rotated token") for a in added), added)
        self.assertTrue(any(a.startswith("Revoked token") for a in added), added)
        self.assertEqual(sum(a.startswith("Created token") for a in added), 2)
        self.no_token_in_root(self.token, new, newest)
        for text in (*s.first_lines, s.stdout_rest, s.stderr):
            for t in (self.token, new, newest):
                self.assertNotIn(t, text)
        self.assertEqual(logbook.verify(self.root).problems, [])

    def test_the_token_is_shown_only_on_a_terminal_and_only_once(self):
        record_path = self.root / ".umwayi" / "serve.token"
        before = record_path.read_bytes()
        again = servetoken.create(self.root, 30, today(), True)
        self.assertEqual(again.code, 1)  # a record exists: nothing changes
        self.assertEqual(record_path.read_bytes(), before)
        piped = servetoken.rotate(self.root, 30, today(), False)  # not a terminal
        self.assertEqual(piped.code, 1)
        self.assertNotIn("umt1_", "\n".join(piped.lines))
        self.assertEqual(record_path.read_bytes(), before)
        r = cli(self.root, "serve", "token", "create")  # a real child process with no terminal
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertNotIn("umt1_", r.stdout + r.stderr)
        r = cli(self.root, "serve", "token", "status")
        self.assertEqual(r.returncode, 0)
        self.assertRegex(r.stdout, r"^Token T-[0-9a-f]{8}: created \d{4}-\d{2}-\d{2}, expires \d{4}-\d{2}-\d{2}, \d+ days left")
        self.assertNotIn(self.token, r.stdout + r.stderr)

    def test_no_route_handles_a_token(self):
        with self.server() as s:
            page = Page(s, self.token)
            before = (self.root / ".umwayi" / "serve.token").read_bytes()
            for method, path, body in (("POST", "/v1/token", {}), ("POST", "/v1/token/rotate", {}), ("POST", "/v1/token/revoke", {}),
                                       ("GET", "/v1/token", None), ("DELETE", "/v1/token", None),
                                       ("POST", "/v1/serve/token/create", {})):
                with self.subTest(path=path, method=method):
                    st, w = page.word(method, path, body)
                    self.assertIn(st, (404, 405))
                    self.assertIn(w, ("route", "method"))
            self.assertEqual((self.root / ".umwayi" / "serve.token").read_bytes(), before)


class WrongOrExpiredToken(Scenario):
    def test_wrong_missing_and_malformed_tokens_get_the_same_bytes(self):
        swapped = "umt1_" + self.token[5:].swapcase()
        bad = [None, TOKEN2, self.token[:-1], self.token + "x", "Bearer", "", " " + self.token, swapped]
        replies = []
        for i in range(0, len(bad), 4):  # four failures at a time: the fifth in a minute would be the lock-out
            with self.server() as s:
                page = Page(s, self.token)
                for tok in bad[i:i + 4]:
                    st, _h, env, raw = page.call("GET", "/v1/queue", token=tok)
                    self.assertEqual((st, env["word"]), (401, "token"), tok)
                    replies.append(raw)
        self.assertEqual(len(set(replies)), 1, "a refusal for a bad token must be the same bytes every time")
        self.assertNotIn(self.token.encode(), replies[0])

    def test_an_expired_token_is_refused_by_a_running_server(self):
        with self.server() as s:
            page = Page(s, self.token)
            self.assertEqual(page.word("GET", "/v1/status"), (200, "done"))
            p = self.root / ".umwayi" / "serve.token"
            rec = json.loads(p.read_text())
            from datetime import date, timedelta
            rec["created"] = (date.today() - timedelta(days=40)).isoformat()
            rec["expires"] = (date.today() - timedelta(days=10)).isoformat()
            p.write_text(json.dumps(rec, indent=2) + "\n")
            os.chmod(p, 0o600)
            self.assertEqual(page.word("GET", "/v1/status"), (401, "token"))
            self.assertEqual(page.word("POST", "/v1/queue", {"kind": "task", "title": "late"}), (401, "token"))
            # a record that is today's own expiry date is already too late
            rec["created"] = (date.today() - timedelta(days=5)).isoformat()
            rec["expires"] = date.today().isoformat()
            p.write_text(json.dumps(rec, indent=2) + "\n")
            self.assertEqual(page.word("GET", "/v1/status"), (401, "token"))
        self.assertNotIn("late", self.queue_text())

    def test_five_failures_lock_out_the_failures_and_never_a_valid_token(self):
        with self.server() as s:
            page = Page(s, self.token)
            words = [page.word("GET", "/v1/status", token=TOKEN2) for _ in range(7)]
            self.assertEqual(words[0], (401, "token"))
            self.assertEqual(words[-1], (429, "rate"))
            self.assertEqual(page.word("GET", "/v1/status"), (200, "done"))
        self.assertEqual(self.request_entries()[0].added.split(": ")[1].split(",")[0], "GET status")

    def test_a_refused_token_changes_nothing_and_writes_no_request_entry(self):
        before = snapshot_tree(self.root)
        with self.server() as s:
            page = Page(s, self.token)
            baseline = len(self.entries())
            for _ in range(3):
                self.assertEqual(page.word("POST", "/v1/queue", {"kind": "task", "title": "nope"}, token=TOKEN2), (401, "token"))
            self.assertEqual(len(self.request_entries()), 0)
            self.assertEqual(len(self.entries()), baseline)
        self.assertEqual(self.queue_text(), before["queue.md"].decode())


# ------------------------------------------------------------------------------------ Host and Origin


class HostAndOrigin(Scenario):
    def test_a_wrong_host_is_refused_even_with_a_valid_token_and_nothing_changes(self):
        with self.server() as s:
            page = Page(s, self.token)
            port = s.port
            before = snapshot_tree(self.root)
            for host in (f"localhost:{port}", f"127.0.0.1:{port + 1}", "127.0.0.1", f"[::1]:{port}", f"evil.example:{port}",
                         f"127.0.0.1:{port}.evil.example", f"0.0.0.0:{port}", f"127.0.0.2:{port}"):
                for method, path, body in (("GET", "/v1/queue", None), ("POST", "/v1/queue", {"kind": "task", "title": "rebind"})):
                    with self.subTest(host=host, method=method):
                        st, _h, env, _raw = page.call(method, path, body, host=host)
                        self.assertEqual((st, (env or {}).get("word")), (403, "host"))
            snap = snapshot_tree(self.root)
        # nothing in the root changed except the logbook files and the lock the server holds
        for k in set(before) | set(snap):
            if k.startswith(".umwayi/logbook") or k in ("LOGBOOK.md", ".umwayi/serve.lock") or k.startswith(".umwayi/serve.lock"):
                continue
            self.assertEqual(before.get(k), snap.get(k), k)
        self.assertNotIn("rebind", self.queue_text())

    def test_a_wrong_or_missing_origin_on_a_post_is_refused(self):
        with self.server() as s:
            page = Page(s, self.token)
            port = s.port
            body = {"kind": "task", "title": "cross site"}
            for origin in (None, "null", f"http://localhost:{port}", f"http://127.0.0.1:{port + 1}", "https://127.0.0.1:%d" % port,
                           f"http://127.0.0.1:{port}/", "http://evil.example"):
                with self.subTest(origin=origin):
                    st, w = page.word("POST", "/v1/queue", body, origin=origin)
                    self.assertEqual((st, w), (403, "origin"))
            for site in ("cross-site", "same-site", "none"):
                with self.subTest(site=site):
                    self.assertEqual(page.word("POST", "/v1/queue", body, extra={"Sec-Fetch-Site": site}), (403, "origin"))
            self.assertEqual(page.word("POST", "/v1/queue", body, extra={"Sec-Fetch-Mode": "navigate"}), (403, "origin"))
            # a GET carrying a foreign Origin is refused too
            self.assertEqual(page.word("GET", "/v1/queue", origin="http://evil.example"), (403, "origin"))
            self.assertNotIn("cross site", self.queue_text())
            # the same request with the right Origin passes, so the refusals above are the Origin and not something else
            self.assertEqual(page.word("POST", "/v1/queue", body), (200, "done"))

    def test_no_response_ever_carries_a_cross_origin_header_or_a_cookie(self):
        with self.server() as s:
            page = Page(s, self.token)
            for call in (("GET", "/v1/status", None, {}), ("GET", "/v1/status", None, {"token": TOKEN2}),
                         ("POST", "/v1/queue", {"kind": "task", "title": "x"}, {}),
                         ("POST", "/v1/queue", {"kind": "task", "title": "x"}, {"origin": "null"}),
                         ("GET", "/v1/nowhere", None, {}), ("DELETE", "/v1/queue", None, {})):
                _st, headers, _env, _raw = page.call(call[0], call[1], call[2], **call[3])
                for name in headers:
                    self.assertFalse(name.startswith("access-control-"), name)
                self.assertNotIn("set-cookie", headers)
            raw = s.raw(f"OPTIONS /v1/queue HTTP/1.1\r\nHost: 127.0.0.1:{s.port}\r\nOrigin: http://evil.example\r\n"
                        "Access-Control-Request-Method: POST\r\nAccess-Control-Request-Private-Network: true\r\n\r\n".encode())
            self.assertTrue(raw.startswith(b"HTTP/1.1 405"), raw[:80])
            self.assertNotIn(b"access-control", raw.lower().replace(b"access-control-request", b""))


# ------------------------------------------------------------------------------------------ kill switch


class KillSwitch(Scenario):
    def test_on_in_the_middle_of_a_run_stops_writes_and_nothing_in_the_page_turns_it_off(self):
        with self.server() as s:
            page = Page(s, self.token)
            self.assertEqual(page.word("POST", "/v1/queue", {"kind": "task", "title": "before the switch"}), (200, "done"))
            st, _h, env, _raw = page.call("GET", "/v1/status")
            self.assertEqual(env["data"]["kill_switch"], "off")
            # the owner turns it on from the command line, while the server runs
            r = cli(self.root, "kill", "on", "--reason", "scenario")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(page.call("GET", "/v1/status")[2]["data"]["kill_switch"], "on")
            frozen = self.queue_text()
            for method, path, body in (("POST", "/v1/queue", {"kind": "task", "title": "after the switch"}),
                                       ("POST", "/v1/queue/Q-0001/answer", {"answer": "yes"}),
                                       ("POST", "/v1/queue/Q-0001/close", {}),
                                       ("POST", "/v1/agents/helper/check", {})):
                with self.subTest(path=path):
                    st, w = page.word(method, path, body)
                    self.assertEqual((st, w), (403, "kill"))
            self.assertEqual(self.queue_text(), frozen)
            # a read still works (looking is allowed while the switch is on)
            self.assertEqual(page.word("GET", "/v1/queue"), (200, "done"))
            # no route and no body turns it off
            for method, path, body in (("POST", "/v1/kill/off", {}), ("DELETE", "/v1/kill", None), ("DELETE", "/v1/kill/on", None),
                                       ("POST", "/v1/kill", {"state": "off"}), ("POST", "/v1/kill/on", {"off": True}),
                                       ("POST", "/v1/kill/on", {"state": "off"}), ("GET", "/v1/status?kill=off", None),
                                       ("POST", "/v1/queue", {"kind": "task", "title": "x", "kill": "off"}),
                                       ("POST", "/v1/kill/toggle", {}), ("POST", "/v1/kill/reset", {}),
                                       ("POST", "/v1/kill/on/off", {}), ("POST", "/v1/KILL/off", {})):
                with self.subTest(path=path, method=method, body=body):
                    st, w = page.word(method, path, body)
                    self.assertNotEqual(st, 200)
            self.assertEqual(page.call("GET", "/v1/status")[2]["data"]["kill_switch"], "on")
            self.assertTrue((self.root / ".umwayi" / "KILL").exists())
            # POST kill/on again is allowed (it is the switch) and stays on
            self.assertEqual(page.word("POST", "/v1/kill/on", {"reason": "again"})[0], 200)
            self.assertTrue((self.root / ".umwayi" / "KILL").exists())
            # only the owner's command line turns it off, and the next write works
            r = cli(self.root, "kill", "off")
            if r.returncode == 0:
                self.assertEqual(page.word("POST", "/v1/queue", {"kind": "task", "title": "after off"}), (200, "done"))
                self.assertIn("after off", self.queue_text())
            else:
                self.assertTrue((self.root / ".umwayi" / "KILL").exists(), r.stderr)

    def test_the_page_can_turn_it_on_and_it_survives_a_restart(self):
        with self.server() as s:
            page = Page(s, self.token)
            st, _h, env, _raw = page.call("POST", "/v1/kill/on", {"reason": "stop everything"})
            self.assertEqual((st, env["word"], env["data"]), (200, "done", {"kill_switch": "on"}))
            self.assertEqual(page.word("POST", "/v1/queue", {"kind": "task", "title": "blocked"}), (403, "kill"))
        with self.server() as s2:
            page = Page(s2, self.token)
            self.assertEqual(page.call("GET", "/v1/status")[2]["data"]["kill_switch"], "on")
            self.assertEqual(page.word("POST", "/v1/queue", {"kind": "task", "title": "blocked"}), (403, "kill"))
        self.assertNotIn("blocked", self.queue_text())
        self.assertEqual(logbook.verify(self.root).problems, [])

    def test_an_unreadable_switch_stops_writes_too(self):
        with self.server() as s:
            page = Page(s, self.token)
            kill_path = self.root / ".umwayi" / "KILL"
            kill_path.mkdir()  # a folder where the flag should be: the state is unknown
            st, w = page.word("POST", "/v1/queue", {"kind": "task", "title": "unknown state"})
            self.assertEqual((st, w), (403, "kill"))
            self.assertNotIn("unknown state", self.queue_text())


# ---------------------------------------------------------------------------------------------- the queue


class QueueFlow(Scenario):
    def test_add_answer_close_and_the_command_line_sees_the_same_queue(self):
        with self.server() as s:
            page = Page(s, self.token)
            st, _h, env, _raw = page.call("POST", "/v1/queue", {"kind": "decision", "title": "Ship the page?", "recommendation": "Yes"})
            self.assertEqual((st, env["word"], env["logged"], env["data"]["added"]), (200, "done", True, True))
            qid = env["data"]["id"]
            self.assertRegex(qid, r"^Q-\d{4,}$")
            # --if-not-open: the same title is not added twice
            st, _h, env2, _raw = page.call("POST", "/v1/queue", {"kind": "decision", "title": "Ship the page?", "if_not_open": True})
            self.assertEqual((st, env2["data"]), (200, {"id": qid, "added": False}))
            st, _h, listed, _raw = page.call("GET", "/v1/queue?status=open&kind=decision")
            rows = listed["data"]["rows"]
            self.assertEqual([(r["id"], r["status"], r["title"], r["recommendation"]) for r in rows],
                             [(qid, "open", "Ship the page?", "Yes")])
            # the command line sees it
            cl = cli(self.root, "queue", "list")
            self.assertIn(qid, cl.stdout)
            self.assertIn("Ship the page?", cl.stdout)
            # answer, then the list shows the answer
            st, _h, env, _raw = page.call("POST", f"/v1/queue/{qid}/answer", {"answer": "Yes, ship it", "revisit_if": "the build changes"})
            self.assertEqual((st, env["word"], env["data"]["id"]), (200, "done", qid))
            row = page.call("GET", "/v1/queue")[2]["data"]["rows"][0]
            self.assertEqual((row["status"], row["answer"]), ("answered", "Yes, ship it"))
            # answering a row that does not exist, or twice, is a refusal and changes nothing
            before = self.queue_text()
            st, w = page.word("POST", "/v1/queue/Q-9999/answer", {"answer": "x"})
            self.assertEqual((st, w), (409, "refused"))
            self.assertEqual(self.queue_text(), before)
            # close
            st, _h, env, _raw = page.call("POST", f"/v1/queue/{qid}/close", {})
            self.assertEqual((st, env["data"]), (200, {"id": qid, "status": "closed"}))
            self.assertEqual(page.word("POST", f"/v1/queue/{qid}/close", {}), (409, "refused"))
            self.assertEqual(page.call("GET", "/v1/queue?status=closed")[2]["data"]["rows"][0]["id"], qid)
            # an item added at the command line shows in the page
            cli(self.root, "queue", "add", "--kind", "task", "From the command line")
            titles = [r["title"] for r in page.call("GET", "/v1/queue")[2]["data"]["rows"]]
            self.assertIn("From the command line", titles)
        self.assertEqual(logbook.verify(self.root).problems, [])

    def test_bad_input_is_a_usage_word_and_changes_nothing(self):
        with self.server() as s:
            page = Page(s, self.token)
            before = self.queue_text()
            for body in ({"kind": "task"}, {"title": "no kind"}, {"kind": "task", "title": "x", "extra": 1},
                         {"kind": "task", "title": 5}, {"kind": "task", "title": "x" * 5000}, {"kind": "banana", "title": "x"}):
                with self.subTest(body=body):
                    st, w = page.word("POST", "/v1/queue", body)
                    self.assertIn((st, w), ((400, "body"), (400, "usage"), (413, None), (413, "length")))
            for raw in (b"", b"[]", b"{", b'{"kind":"task","kind":"task","title":"x"}', b'{"kind":"task","title":"\xff"}',
                        b'{"kind":"task","title":"x","n":1.5}', b"\xef\xbb\xbf" + b'{"kind":"task","title":"bom"}'):
                with self.subTest(raw=raw):
                    page.pace("POST")
                    head = (f"POST /v1/queue HTTP/1.1\r\nHost: 127.0.0.1:{s.port}\r\nOrigin: http://127.0.0.1:{s.port}\r\n"
                            f"Authorization: Bearer {self.token}\r\nContent-Type: application/json\r\n"
                            f"Content-Length: {len(raw)}\r\n\r\n").encode()
                    st, _h, body = parse_response(s.raw(head + raw))
                    self.assertIn(st, (400, 411), body)
            self.assertEqual(self.queue_text(), before)


# ------------------------------------------------------------------------------------ a crash, a restart


class CrashAndRestart(Scenario):
    def test_a_killed_server_leaves_a_root_a_new_server_can_use(self):
        s = self.server()
        with s:
            page = Page(s, self.token)
            st, _h, env, _raw = page.call("POST", "/v1/queue", {"kind": "task", "title": "before the crash"})
            self.assertEqual(st, 200)
            qid = env["data"]["id"]
            self.assertEqual(page.word("GET", "/v1/status"), (200, "done"))
            code = s.stop(signal.SIGKILL)  # no handler runs: no stop entry, a lock file left behind
            self.assertEqual(code, -signal.SIGKILL)
        self.assertEqual(logbook.verify(self.root).problems, [])  # every entry that was written is whole
        self.assertFalse(any(e.added.startswith("Stopped") for e in self.entries()))
        with self.server() as s2:
            page = Page(s2, self.token)
            rows = page.call("GET", "/v1/queue")[2]["data"]["rows"]
            self.assertEqual([r["id"] for r in rows], [qid])  # the queue came through
            self.assertEqual(page.word("POST", "/v1/queue/%s/answer" % qid, {"answer": "after the restart"}), (200, "done"))
            self.assertEqual(page.word("GET", "/v1/status"), (200, "done"))
            self.assertEqual(s2.stop(), 0)
        added = [e.added for e in self.entries()]
        self.assertEqual(sum(a.startswith("Started on") for a in added), 2)
        self.assertEqual(sum(a.startswith("Stopped") for a in added), 1)
        self.assertEqual(logbook.verify(self.root).problems, [])
        self.no_token_in_root(self.token)

    def test_a_second_server_for_the_same_root_is_refused_while_the_first_runs(self):
        with self.server() as s:
            r = run_serve(self.root, "--port", "0")
            self.assertEqual(r.returncode, 64)
            self.assertNotIn("Listening", r.stdout)
            self.assertEqual(Page(s, self.token).word("GET", "/v1/status"), (200, "done"))

    def test_sigterm_in_the_middle_of_requests_leaves_a_whole_logbook(self):
        s = self.server()
        with s:
            page = Page(s, self.token)
            for i in range(8):
                page.call("POST", "/v1/queue", {"kind": "task", "title": f"item {i}"})
            self.assertEqual(s.stop(signal.SIGTERM), 0)
        self.assertEqual(logbook.verify(self.root).problems, [])
        self.assertEqual(len(re.findall(r"\| Q-\d+ ", self.queue_text())), 8)


# ------------------------------------------------------------------------------------------ the logbook


class LogbookEntries(Scenario):
    def test_one_entry_for_each_authenticated_request_none_for_the_others_and_no_content(self):
        with self.server() as s:
            page = Page(s, self.token)
            agent = {"User-Agent": SENTINEL, "X-Probe": SENTINEL}
            ok = [page.call("GET", "/v1/status", extra=agent), page.call("GET", "/v1/queue", extra=agent),
                  page.call("POST", "/v1/queue", {"kind": "task", "title": "T " + SENTINEL}, extra=agent)]
            qid = ok[2][2]["data"]["id"]
            ok.append(page.call("POST", f"/v1/queue/{qid}/answer", {"answer": "A " + SENTINEL}, extra=agent))
            for st, _h, env, _raw in ok:
                self.assertEqual(st, 200)
                self.assertTrue(env["logged"])
            # three refusals before a token was checked: counted, not logged one by one
            for _ in range(3):
                self.assertEqual(page.word("GET", "/v1/queue", token=TOKEN2, extra=agent), (401, "token"))
            # one refusal after a valid token (a wrong Origin): one entry of its own
            self.assertEqual(page.word("POST", "/v1/queue", {"kind": "task", "title": "x"}, origin="http://evil.example", extra=agent),
                             (403, "origin"))
            s.stop()
        reqs = self.request_entries()
        self.assertEqual(len(reqs), 5, [e.added for e in reqs])
        pattern = re.compile(r"^Request R-[0-9a-f]{8}: (GET|POST) [a-z. ]+, (done|refused \([a-z]+\)) \(exit \d+\), \d+ ms$")
        for e in reqs:
            self.assertRegex(e.added, pattern)
        self.assertEqual([e.added.split(": ")[1].split(",")[0] for e in reqs],
                         ["GET status", "GET queue.list", "POST queue.add", "POST queue.answer", "POST no route"])
        self.assertIn("refused (origin)", reqs[-1].added)
        for e in self.entries():
            for field in (e.added, e.checked, e.not_done):
                self.assertNotIn(SENTINEL, field)
                self.assertNotIn("umt1_", field)
        self.assertNotIn(SENTINEL, (self.root / "LOGBOOK.md").read_text().replace("T " + SENTINEL, "").replace("A " + SENTINEL, ""))
        summaries = [e for e in self.entries() if e.added.startswith("Refused ")]
        self.assertEqual(len(summaries), 1)
        self.assertRegex(summaries[0].added, r"^Refused 3 requests before a token was checked or after the rate limit, in the last 60 seconds: token 3\.$")
        # the response carries the id the logbook entry has
        ids = [e.added.split(" ")[1].rstrip(":") for e in reqs[:4]]
        self.assertEqual(ids, [ok[i][2]["request"] for i in range(4)])
        self.assertEqual(logbook.verify(self.root).problems, [])

    def test_the_start_and_stop_entries_and_a_chain_that_verifies_after_many_requests(self):
        with self.server() as s:
            page = Page(s, self.token)
            for i in range(40):
                page.call("GET", "/v1/status")
                if i % 8 == 0:
                    page.call("POST", "/v1/queue", {"kind": "task", "title": f"n{i}"})
            s.stop()
        added = [e.added for e in self.entries()]
        self.assertRegex(added[0], r"^Created token T-[0-9a-f]{8}")
        self.assertRegex(added[1], r"^Started on 127\.0\.0\.1:\d+\.$")
        self.assertRegex(added[-1], r"^Stopped \(sigterm\), \d+ requests served, 0 chats stopped\.$")
        rep = logbook.verify(self.root)
        self.assertEqual(rep.problems, [])
        r = cli(self.root, "logbook", "verify")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_logbook_that_cannot_be_written_is_never_reported_as_done(self):
        with self.server() as s:
            page = Page(s, self.token)
            self.assertEqual(page.word("GET", "/v1/status"), (200, "done"))
            book = self.root / "LOGBOOK.md"
            moved = self.root / "LOGBOOK.moved"
            book.rename(moved)
            book.mkdir()  # a folder where the logbook should be: it cannot be written, as root or not
            try:
                st, _h, env, _raw = page.call("POST", "/v1/queue", {"kind": "task", "title": "unlogged"})
                self.assertNotEqual(env["word"], "done")
                self.assertFalse(env["logged"])
                self.assertIs(page.call("GET", "/v1/status")[2]["data"]["degraded"], True)
                self.assertEqual(page.word("GET", "/v1/queue"), (500, "logbook"))  # degraded: only status, the page and kill.on answer
            finally:
                book.rmdir()
                moved.rename(book)


# ------------------------------------------------------------------------- outside the root, loopback


def git_status():
    """What git says about the checkout the server ran in (None when git is not there): a server that wrote a file into its
    working folder would show here, even in a folder that `listing` does not walk."""
    git = shutil.which("git")
    if not git:
        return None
    r = subprocess.run([git, "-C", str(REPO), "status", "--porcelain", "--untracked-files=all"], capture_output=True, text=True, timeout=60)
    return r.stdout if r.returncode == 0 else None


def listing(path, skip=("__pycache__", ".git", "node_modules")):
    out = {}
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for n in dirnames + filenames:
            p = Path(dirpath) / n
            try:
                st = p.lstat()
            except OSError:
                continue
            out[str(p)] = (st.st_size, st.st_mtime_ns, st.st_mode)
    return out


class OutsideTheRoot(Scenario):
    def test_a_full_session_writes_nothing_outside_the_root(self):
        sibling = self.tmp / "sibling"
        sibling.mkdir()
        (sibling / "keep.txt").write_text("keep\n")
        before_home, before_sibling, before_repo = listing(self.home), listing(sibling), listing(REPO / "umwayi")
        git_before = git_status()
        s = self.server(env={"TMPDIR": str(self.tmp / "tmp-of-server")})
        (self.tmp / "tmp-of-server").mkdir()
        with s:
            page = Page(s, self.token)
            st, _h, env, _raw = page.call("POST", "/v1/queue", {"kind": "task", "title": "inside"})
            qid = env["data"]["id"]
            for method, path, body in (("GET", "/", None), ("GET", "/v1/status", None), ("GET", "/v1/snapshot", None),
                                       ("GET", "/v1/queue", None), ("GET", "/v1/logbook", None), ("GET", "/v1/budget", None),
                                       ("GET", "/v1/agents", None), ("POST", f"/v1/queue/{qid}/answer", {"answer": "ok"}),
                                       ("POST", f"/v1/queue/{qid}/close", {}), ("POST", "/v1/kill/on", {}),
                                       ("POST", "/v1/queue", {"kind": "task", "title": "../../escape"}),
                                       ("GET", "/../../etc/passwd", None), ("GET", "/v1/queue?status=../..", None)):
                page.call(method, path, body)
            s.stop()
        self.assertEqual(listing(self.home), before_home)
        self.assertEqual(listing(sibling), before_sibling)
        self.assertEqual(listing(self.tmp / "tmp-of-server"), {})
        self.assertEqual(listing(REPO / "umwayi"), before_repo)
        self.assertEqual(git_status(), git_before)
        self.assertEqual({p.name for p in self.tmp.iterdir()}, {"root", "home", "sibling", "tmp-of-server"})
        self.assertFalse((self.root.parent / "escape").exists())
        self.assertFalse((self.root / "etc").exists())

    def test_the_files_the_session_made_in_the_root_are_the_expected_ones(self):
        with self.server() as s:
            Page(s, self.token).call("POST", "/v1/queue", {"kind": "task", "title": "x"})
            s.stop()
        names = {k for k in snapshot_tree(self.root) if not k.endswith("/")}
        self.assertTrue({"LOGBOOK.md", "queue.md", "rules.yaml", "umwayi.json"} <= names)
        allowed = {".umwayi/serve.token", ".umwayi/logbook.sha256", ".umwayi/logbook.lock", ".umwayi/serve.lock",
                   ".umwayi/logbook.pending", ".umwayi/logbook.chain", ".umwayi/logbook.head"}
        extra = {n for n in names if n.startswith(".umwayi/") and n not in allowed}
        self.assertEqual(extra, set(), "unexpected state files")


class LoopbackOnly(Scenario):
    def test_the_socket_is_127_0_0_1_only_and_there_is_no_way_to_change_it(self):
        env = {"HOST": "0.0.0.0", "UMWAYI_HOST": "0.0.0.0", "BIND": "::", "UMWAYI_BIND": "0.0.0.0"}
        with self.server(env=env) as s:
            hexport = "%04X" % s.port
            if Path("/proc/net/tcp").exists():
                tcp = Path("/proc/net/tcp").read_text().splitlines()[1:]
                listening = [ln.split()[1] for ln in tcp if ln.split()[3] == "0A" and ln.split()[1].endswith(":" + hexport)]
                self.assertEqual(listening, ["0100007F:" + hexport])
                if Path("/proc/net/tcp6").exists():
                    tcp6 = Path("/proc/net/tcp6").read_text().splitlines()[1:]
                    self.assertEqual([ln for ln in tcp6 if ln.split()[1].endswith(":" + hexport)], [])
            else:
                self.skipTest("no /proc/net/tcp on this system")
            others = set()
            try:
                for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                    others.add(info[4][0])
            except OSError:
                pass
            others.discard("127.0.0.1")
            for addr in sorted(others):
                c = socket.socket()
                c.settimeout(2)
                try:
                    self.assertNotEqual(c.connect_ex((addr, s.port)), 0, addr)
                finally:
                    c.close()
            self.assertEqual(Page(s, self.token).word("GET", "/v1/status"), (200, "done"))
        for args in (["--host", "0.0.0.0"], ["--bind", "0.0.0.0"], ["--host=::"]):
            r = run_serve(self.root, *args)
            self.assertEqual(r.returncode, 64, args)
            self.assertNotIn("Listening", r.stdout)

    def test_a_request_from_a_non_loopback_address_never_reaches_a_route(self):
        # Only the loopback address is bound, so the server cannot see any other peer. What can be tested is that a
        # request naming another address in its Host is refused (that is what a DNS rebinding page sends).
        with self.server() as s:
            page = Page(s, self.token)
            self.assertEqual(page.word("GET", "/v1/status", host=f"192.168.1.10:{s.port}"), (403, "host"))
            self.assertEqual(page.word("GET", "/v1/status", host=f"[::1]:{s.port}"), (403, "host"))


# ------------------------------------------------------------------ the real page client, in Node

NODE = shutil.which("node")
DRIVER = Path(__file__).with_name("page_client_driver.mjs")


@unittest.skipUnless(NODE, "Node is not installed; the Node tests of ui/ run in their own CI job")
class RealPageClient(Scenario):
    """ui/src/api/client.js itself, run by Node against a real server. `fetch` of Node adds no Origin and no fetch
    metadata, so the driver adds what a browser adds to a same-origin request; the paths and bodies are the client's own."""

    def run_driver(self, port, token, script):
        env = dict(os.environ, UMWAYI_PORT=str(port), UMWAYI_TOKEN=token, UMWAYI_SCRIPT=script, HOME=str(self.home))
        r = subprocess.run([NODE, str(DRIVER)], capture_output=True, text=True, timeout=60, env=env, cwd=str(REPO))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def test_the_page_client_walks_the_queue_and_the_kill_switch_against_a_real_server(self):
        with self.server() as s:
            out = self.run_driver(s.port, self.token, "session")
            s.stop()
        steps = {k: v for k, v in out["steps"].items()}
        self.assertTrue(steps["status"]["ok"], steps["status"])
        self.assertTrue(steps["add"]["ok"] and steps["add"]["data"]["added"], steps["add"])
        qid = steps["add"]["data"]["id"]
        self.assertEqual([r["id"] for r in steps["list"]["data"]["rows"]], [qid])
        self.assertTrue(steps["answer"]["ok"] and steps["close"]["ok"])
        self.assertEqual(steps["kill"]["data"], {"kill_switch": "on"})
        self.assertEqual((steps["after_kill"]["ok"], steps["after_kill"]["word"], steps["after_kill"]["stopped"]),
                         (False, "kill", False))
        self.assertEqual(steps["status_after"]["data"]["kill_switch"], "on")
        self.assertTrue(all(p.startswith("/v1/") for p in out["paths"]), out["paths"])
        self.assertTrue(all(not p.startswith("//") and "://" not in p for p in out["paths"]))
        self.assertTrue((self.root / ".umwayi" / "KILL").exists())
        self.assertEqual(logbook.verify(self.root).problems, [])
        self.assertNotIn("umt1_", (self.root / "LOGBOOK.md").read_text())

    def test_a_wrong_token_makes_the_client_forget_it_and_send_nothing_more(self):
        with self.server() as s:
            out = self.run_driver(s.port, TOKEN2, "wrong")
            s.stop()
        steps = out["steps"]
        self.assertEqual((steps["first"]["ok"], steps["first"]["word"], steps["first"]["kind"]), (False, "token", "token"))
        self.assertEqual(steps["second"]["kind"], "notoken")  # the client dropped the token: no second request was sent
        self.assertEqual(len(out["paths"]), 1)
        self.assertEqual(self.request_entries(), [])

    def test_the_client_refuses_to_run_off_the_loopback_origin(self):
        with self.server() as s:
            out = self.run_driver(s.port, self.token, "foreign")
            s.stop()
        self.assertEqual(out["steps"]["file"], {"available": False, "sent": 0})
        self.assertEqual(out["steps"]["other_host"], {"available": False, "sent": 0})
        self.assertEqual(out["steps"]["localhost"], {"available": False, "sent": 0})
        self.assertEqual(self.request_entries(), [])


if __name__ == "__main__":
    unittest.main()
