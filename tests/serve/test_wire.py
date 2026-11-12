"""The server on the wire (W6.R16.2): real child processes, `python -m umwayi serve --port 0`, HOME in a temporary folder,
a raw socket for malformed requests. Dates are the real ones (the server reads the system clock)."""

import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import date, timedelta
from pathlib import Path

from tests.serve import gen, oracle
from tests.serve.support import (REPO, SENTINEL, TOKEN, TOKEN2, RootCase, Server, envelope, logbook_entries, make_root,
                                 parse_response, record, rules_text)
from umwayi import logbook

FUZZ_N = int(os.environ.get("UMWAYI_FUZZ_N", "5000"))
GATE_WORDS = {"method", "peer", "header", "host", "target", "token", "origin", "route", "length", "type", "rate"}


def today():
    return date.today().isoformat()


def far():
    return (date.today() + timedelta(days=60)).isoformat()


def wire_root(tmp, expires=None, token=TOKEN, rules=None):
    """A root whose token record is made for the real date (the server reads the system clock)."""
    root = make_root(Path(tmp), token=None, rules=rules)
    if token is not None:
        p = root / ".umwayi" / "serve.token"
        p.write_text(json.dumps(record(token, created=today(), expires=expires or far()), indent=2) + "\n")
        os.chmod(p, 0o600)
    return root


def run_serve(root, *args, env=None, timeout=30):
    e = dict(os.environ, PYTHONPATH=str(REPO), HOME=tempfile.mkdtemp(prefix="umwayi-home-"))
    e.update(env or {})
    return subprocess.run([sys.executable, "-m", "umwayi", "--root", str(root), "serve", *args], capture_output=True,
                          text=True, timeout=timeout, env=e, cwd=str(REPO), stdin=subprocess.DEVNULL)


class WireBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        (self.tmp / "root").mkdir()
        self.root = wire_root(self.tmp / "root")


class StartTests(WireBase):
    def test_start_line_stop_with_sigterm_and_the_two_entries(self):
        with Server(self.root) as s:
            self.assertRegex(s.first_lines[0], r"^Listening on http://127\.0\.0\.1:\d+( \(page not served\))?$")
            st, _h, body = s.request("GET", "/v1/status")
            self.assertEqual((st, envelope(body)["word"]), (200, "done"))
            code = s.stop()
        self.assertEqual(code, 0)
        console = "\n".join(s.first_lines) + "\n" + s.stdout_rest
        self.assertRegex(console, r"Token T-[0-9a-f]{8} expires on \d{4}-\d{2}-\d{2} \(\d+ days left\)")
        self.assertNotIn(TOKEN, console)
        entries = [e for e in logbook_entries(self.root) if e.source == "umwayi serve"]
        self.assertRegex(entries[0].added, r"^Started on 127\.0\.0\.1:%d\.$" % s.port)
        self.assertRegex(entries[0].checked, r"^The logbook chain was intact\. Token T-[0-9a-f]{8} expires on "
                                             r"\d{4}-\d{2}-\d{2}\. Page served: (yes \(SHA-256 matches build\.json\)|no \([a-z ]+\))\.?$")
        self.assertRegex(entries[-1].added, r"^Stopped \([a-z]+\), \d+ requests served, 0 chats stopped\.$")
        self.assertEqual(logbook.verify(self.root).problems, [])

    def test_sigint_also_stops_cleanly(self):
        import signal
        with Server(self.root) as s:
            code = s.stop(signal.SIGINT)
        self.assertEqual(code, 0)

    def test_the_console_holds_no_token_no_request_line_no_peer_and_no_header(self):
        with Server(self.root) as s:
            s.request("GET", "/v1/status", headers={"X-Sentinel": SENTINEL})
            s.request("GET", "/v1/status", token=TOKEN2)
            s.stop()
        for text in (" ".join(s.first_lines), s.stdout_rest, s.stderr):
            self.assertNotIn(TOKEN, text)
            self.assertNotIn(SENTINEL, text)
            self.assertNotIn("GET /", text)
            self.assertNotIn("Traceback", text)
            self.assertNotIn("127.0.0.1 - -", text)

    def test_a_hint_when_the_rules_have_no_serve_request_rule(self):
        (self.root / "rules.yaml").write_text("")
        with Server(self.root) as s:
            s.stop()
        self.assertIn("serve.rules.example.yaml", "\n".join(s.first_lines) + s.stdout_rest)

    def test_no_token_or_an_expired_one_is_64_and_names_the_command(self):
        (self.root / ".umwayi" / "serve.token").unlink()
        r = run_serve(self.root)
        self.assertEqual(r.returncode, 64)
        self.assertIn("umwayi serve token create", r.stderr + r.stdout)
        self.assertNotIn("Listening", r.stdout)
        (self.root / ".umwayi" / "serve.token").write_text(json.dumps(
            record(TOKEN, created=(date.today() - timedelta(days=40)).isoformat(),
                   expires=(date.today() - timedelta(days=10)).isoformat())))
        r = run_serve(self.root)
        self.assertEqual(r.returncode, 64)
        self.assertNotIn("Listening", r.stdout)

    def test_bad_arguments_are_64(self):
        for args in (["--port", "80"], ["--port", "1023"], ["--port", "65536"], ["--port", "x"], ["--port", "-1"],
                     ["--host", "0.0.0.0"], ["--bind", "::"], ["--page"], ["--page", str(self.tmp / "missing.html")],
                     ["nonsense"], ["token"], ["token", "frobnicate"]):
            with self.subTest(args=args):
                r = run_serve(self.root, *args)
                self.assertEqual(r.returncode, 64, r.stderr)
                self.assertNotIn("Listening", r.stdout)
                self.assertNotIn("invalid choice: 'serve'", r.stderr)

    def test_a_logbook_that_fails_its_tamper_check_exits_1_before_the_token_is_looked_at(self):
        (self.root / "LOGBOOK.md").write_text("# Logbook\n\ngarbage\n")
        (self.root / ".umwayi" / "serve.token").unlink()
        r = run_serve(self.root)
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Listening", r.stdout)

    def test_a_port_in_use_is_64_and_echoes_only_the_port(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        try:
            port = s.getsockname()[1]
            r = run_serve(self.root, "--port", str(port))
        finally:
            s.close()
        self.assertEqual(r.returncode, 64)
        self.assertNotIn("Listening", r.stdout)
        self.assertNotIn(str(self.root), r.stderr)
        self.assertIn(str(port), r.stderr)
        self.assertNotIn("invalid choice", r.stderr)

    def test_a_second_server_for_the_same_root_is_64(self):
        with Server(self.root):
            r = run_serve(self.root, "--port", "0")
            self.assertEqual(r.returncode, 64)
            self.assertNotIn("Listening", r.stdout)

    def test_the_lock_is_released_when_the_server_stops_and_the_file_stays(self):
        with Server(self.root):
            pass
        self.assertTrue((self.root / ".umwayi" / "serve.lock").exists())
        with Server(self.root):
            pass

    def test_the_default_port_is_8765_when_it_is_free(self):
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", 8765))
        except OSError:
            self.skipTest("port 8765 is in use on this machine")
        s.close()
        p = subprocess.Popen([sys.executable, "-m", "umwayi", "--root", str(self.root), "serve"], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env=dict(os.environ, PYTHONPATH=str(REPO), HOME=str(self.tmp)),
                             cwd=str(REPO))
        try:
            line = p.stdout.readline().decode()
            self.assertIn("http://127.0.0.1:8765", line)
        finally:
            p.terminate()
            p.wait(10)

    def test_rotation_is_seen_by_a_running_server_on_the_next_request(self):
        with Server(self.root) as s:
            self.assertEqual(s.request("GET", "/v1/status")[0], 200)
            p = self.root / ".umwayi" / "serve.token"
            p.write_text(json.dumps(record(TOKEN2, created=today(), expires=far(), tid="T-00000002"), indent=2) + "\n")
            self.assertEqual(s.request("GET", "/v1/status")[0], 401)
            self.assertEqual(s.request("GET", "/v1/status", token=TOKEN2)[0], 200)
            p.unlink()  # revoked: the server keeps running and refuses everything but the page
            self.assertEqual(s.request("GET", "/v1/status", token=TOKEN2)[0], 401)
            self.assertIn(s.request("GET", "/")[0], (200, 503))


class BindTests(WireBase):
    def test_the_socket_listens_on_127_0_0_1_only_and_no_flag_variable_or_setting_changes_it(self):
        env = {"HOST": "0.0.0.0", "UMWAYI_HOST": "0.0.0.0", "BIND": "0.0.0.0", "PORT": "9", "UMWAYI_PORT": "9"}
        with Server(self.root, env=env) as s:
            hexport = "%04X" % s.port
            tcp = Path("/proc/net/tcp").read_text().splitlines()[1:]
            listening = [ln.split()[1] for ln in tcp if ln.split()[3] == "0A" and ln.split()[1].endswith(":" + hexport)]
            self.assertEqual(listening, ["0100007F:" + hexport])
            if Path("/proc/net/tcp6").exists():
                tcp6 = Path("/proc/net/tcp6").read_text().splitlines()[1:]
                self.assertEqual([ln for ln in tcp6 if ln.split()[1].endswith(":" + hexport)], [])
            for addr in self.other_addresses():
                c = socket.socket()
                c.settimeout(2)
                try:
                    self.assertNotEqual(c.connect_ex((addr, s.port)), 0, addr)
                finally:
                    c.close()

    @staticmethod
    def other_addresses():
        found = set()
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                found.add(info[4][0])
        except OSError:
            pass
        return sorted(a for a in found if a != "127.0.0.1")

    def test_the_all_addresses_string_is_nowhere_in_the_serve_sources(self):
        files = sorted((REPO / "umwayi").glob("serve*.py"))
        self.assertGreaterEqual(len(files), 3, "the serve modules are not there yet")
        for p in files:
            text = p.read_text(encoding="utf-8")
            self.assertNotIn("0.0.0.0", text, p.name)
            self.assertNotIn("INADDR_ANY", text, p.name)
            self.assertNotIn("getenv", text, p.name)
            self.assertNotIn("environ", text, p.name)

    def test_the_parser_has_no_host_option(self):
        from umwayi.cli import build_parser
        sub = None
        for action in build_parser()._subparsers._group_actions[0].choices.items():
            if action[0] == "serve":
                sub = action[1].format_help()
        self.assertIsNotNone(sub)
        for word in ("--host", "--bind", "--address", "--listen", "--interface"):
            self.assertNotIn(word, sub)

    def test_the_source_binds_the_literal_address_and_reads_the_socket_back(self):
        src = (REPO / "umwayi" / "serve.py").read_text(encoding="utf-8")
        self.assertIn('LOOPBACK = "127.0.0.1"', src)
        self.assertEqual(src.count("server_class((LOOPBACK, "), 1)
        self.assertIn("getsockname", src)


class PageTests(WireBase):
    HEADERS = {"cache-control": "no-store", "x-content-type-options": "nosniff", "referrer-policy": "no-referrer",
               "cross-origin-resource-policy": "same-origin", "cross-origin-opener-policy": "same-origin",
               "connection": "close", "server": "umwayi"}

    def page(self, content=b"<!doctype html><title>x</title>", good=True):
        d = self.tmp / "dist"
        d.mkdir(exist_ok=True)
        (d / "index.html").write_bytes(content)
        (d / "build.json").write_text(json.dumps({"page": hashlib.sha256(content if good else b"other").hexdigest()}))
        return d / "index.html"

    def test_the_page_is_served_unchanged_only_with_a_matching_build_json(self):
        path = self.page()
        with Server(self.root, ["--page", str(path)]) as s:
            st, h, body = s.request("GET", "/", token=None)
            self.assertEqual((st, body), (200, b"<!doctype html><title>x</title>"))
            self.assertTrue(h["content-type"][0].startswith("text/html"))
            csp = h["content-security-policy"][0]
            for part in ("frame-ancestors 'none'", "base-uri 'none'", "form-action 'none'"):
                self.assertIn(part, csp)
            path.write_bytes(b"<!doctype html><title>y</title>")  # a changed byte
            st, h, body = s.request("GET", "/", token=None)
            self.assertEqual(st, 503)
            self.assertEqual(envelope(body)["word"], "page")
            self.assertEqual(s.first_lines[0].endswith("(page not served)"), False)

    def test_a_page_that_does_not_match_at_start_still_starts_and_says_page_not_served(self):
        path = self.page(good=False)
        with Server(self.root, ["--page", str(path)]) as s:
            self.assertIn("page not served", s.first_lines[0])
            self.assertEqual(s.request("GET", "/", token=None)[0], 503)
            self.assertEqual(s.request("GET", "/v1/status")[0], 200)

    def test_a_link_gives_503_page(self):
        real = self.page()
        link = self.tmp / "dist" / "link.html"
        link.symlink_to(real)
        (self.tmp / "dist" / "build.json").write_text(json.dumps({"page": hashlib.sha256(real.read_bytes()).hexdigest()}))
        with Server(self.root, ["--page", str(link)]) as s:
            self.assertEqual(s.request("GET", "/", token=None)[0], 503)
        self.assertEqual(run_serve(self.root, "--page", str(self.tmp / "nope")).returncode, 64)

    def test_a_page_over_2_5_mb_is_not_served(self):
        path = self.page(b"a" * (2_600_000))
        with Server(self.root, ["--page", str(path)]) as s:
            self.assertEqual(s.request("GET", "/", token=None)[0], 503)

    def test_the_built_page_of_the_repo_is_served_when_it_matches(self):
        with Server(self.root, ["--page", str(REPO / "ui" / "dist" / "index.html")]) as s:
            st, h, body = s.request("GET", "/", token=None)
            self.assertEqual(st, 200)
            self.assertEqual(hashlib.sha256(body).hexdigest(), json.loads((REPO / "ui/dist/build.json").read_text())["page"])

    def test_the_headers_are_on_every_response_and_no_cookie_and_no_cors_header_ever(self):
        path = self.page()
        with Server(self.root, ["--page", str(path)]) as s:
            probes = [s.request("GET", "/", token=None), s.request("GET", "/v1/status"), s.request("GET", "/v1/status", token=TOKEN2),
                      s.request("GET", "/v1/nothing"), s.request("POST", "/v1/status", body={}),
                      s.request("OPTIONS", "/v1/status"), s.request("GET", "/v1/status", headers={"Host": "evil:1"}),
                      s.request("GET", "/v1/status", headers={"Origin": "http://evil.example", "Cookie": "a=b"}),
                      parse_response(s.raw(b"garbage\r\n\r\n"))]
            for st, h, body in probes:
                self.assertNotEqual(st, 0, body)
                for k, v in self.HEADERS.items():
                    self.assertEqual(h.get(k, [None])[0], v, (st, k, body[:50]))
                self.assertFalse([k for k in h if k.startswith("access-control-")], h)
                self.assertNotIn("set-cookie", h)
                if "application/json" in h.get("content-type", [""])[0]:
                    self.assertIn("charset=utf-8", h["content-type"][0])
                self.assertEqual(int(h["content-length"][0]), len(body))


class GateOnTheWireTests(WireBase):
    def wire_bytes(self, r):
        """A Req as bytes, or None when it cannot be sent as is (a control character would break the framing)."""
        parts = [r.method, r.target, r.version]
        if any(not p.isascii() or any(ord(c) < 32 or ord(c) == 127 for c in p) or " " in p for p in parts[:2] + [r.version]):
            return None
        lines = []
        for n, v in r.headers:
            if not n or not v.isprintable() or not v.isascii() or any(c in n for c in " :\r\n\x00") or n != n.strip():
                return None
            lines.append(f"{n}: {v}")
        head = f"{r.method} {r.target} {r.version}\r\n" + "".join(ln + "\r\n" for ln in lines) + "\r\n"
        return head.encode("ascii") + r.body

    @staticmethod
    def retarget(r, port):
        r = r.clone()
        for h in r.headers:
            if h[0].lower() in ("host", "origin"):
                h[1] = h[1].replace(":%d" % gen.PORT, ":%d" % port)
        r.port = port
        r.peer = r.server = "127.0.0.1"  # a socket cannot lie about these; the pure gate tests do
        r.channel = "local"
        r.rec, r.date, r.buckets, r.fails, r.locked_until = record(TOKEN), today(), {}, (), 0.0
        return r

    def test_a_generated_corpus_through_a_live_server_is_answered_as_the_pure_function_does(self):
        batch = []
        for seed in (1, 2):
            g = gen.Gen(seed)
            for _ in range(260):
                r = gen.random_req(g)
                want = oracle.judge(*oracle.from_req(self.retarget(r, gen.PORT)))
                if want[0] == "refuse" and want[2] in ("token", "rate", "error"):
                    continue  # throttled and counted: the live state is not the generated state
                if self.wire_bytes(r) is not None:
                    batch.append(r)
        self.assertGreater(len(batch), 200)
        checked = 0
        for i in range(0, len(batch), 24):  # a new server for each 24: the rate limit is part of the server's state
            with Server(self.root) as s:
                for r in batch[i:i + 24]:
                    r = self.retarget(r, s.port)
                    want = oracle.judge(*oracle.from_req(r))
                    st, h, body = parse_response(s.raw(self.wire_bytes(r), read_timeout=12))
                    env = envelope(body) if body.startswith(b"{") else {}
                    checked += 1
                    if env.get("word") == "rate":
                        continue
                    if want[0] == "refuse":
                        self.assertEqual((st, env.get("word")), (want[1], want[2]), gen.describe(r))
                    else:
                        self.assertNotIn(env.get("word"), GATE_WORDS, gen.describe(r))
        self.assertGreater(checked, 200)

    def test_every_golden_request_is_answered_by_the_route_and_not_by_the_gate(self):
        with Server(self.root) as s:
            for rid in gen.ROUTE_IDS:
                if rid == "page":
                    continue
                method, target, body, _c = gen.GOLDEN[rid]
                st, h, raw = s.request(method, target, body=body)
                env = envelope(raw)
                self.assertNotIn(env["word"], GATE_WORDS, (rid, env))
                time.sleep(0.25)

    def test_methods_and_private_network_preflights(self):
        with Server(self.root) as s:
            for method in ("OPTIONS", "HEAD", "PUT", "PATCH", "CONNECT", "TRACE", "FOO"):
                st, h, body = s.request(method, "/v1/status", headers={"Access-Control-Request-Private-Network": "true",
                                                                       "Access-Control-Request-Method": "POST",
                                                                       "Origin": "https://evil.example"})
                self.assertEqual(st, 405, method)
                self.assertFalse([k for k in h if k.startswith("access-control-")])
                self.assertEqual(envelope(body)["word"], "method", method)

    def test_keep_alive_is_closed_anyway_and_pipelined_requests_get_one_answer(self):
        with Server(self.root) as s:
            req = (f"GET /v1/status HTTP/1.1\r\nHost: 127.0.0.1:{s.port}\r\nAuthorization: Bearer {TOKEN}\r\n"
                   f"Connection: keep-alive\r\n\r\n").encode()
            raw = s.raw(req + req)
            self.assertEqual(raw.count(b"HTTP/1.1 "), 1)
            self.assertIn(b"Connection: close", raw)

    def test_a_body_longer_than_its_length_is_ignored_and_a_shorter_one_is_cut_off(self):
        payload = b'{"kind":"task","title":"T"}'
        with Server(self.root) as s:
            head = (f"POST /v1/queue HTTP/1.1\r\nHost: 127.0.0.1:{s.port}\r\nAuthorization: Bearer {TOKEN}\r\n"
                    f"Origin: http://127.0.0.1:{s.port}\r\nContent-Type: application/json\r\n"
                    f"Content-Length: {len(payload)}\r\n\r\n").encode()
            st, _h, raw = parse_response(s.raw(head + payload + b"X" * 200))
            self.assertEqual(st, 200, raw)
            self.assertEqual(envelope(raw)["word"], "done")
            short = head.replace(b"Content-Length: %d" % len(payload), b"Content-Length: 300")
            t0 = time.monotonic()
            raw = s.raw(short + payload[:20], read_timeout=15, shutdown_write=True)
            self.assertLess(time.monotonic() - t0, 12)
            self.assertNotIn(b" 200 ", raw.split(b"\r\n")[0])
            self.assertEqual(s.request("GET", "/v1/status")[0], 200)  # still alive

    def test_slow_and_unfinished_requests_are_cut(self):
        with Server(self.root) as s:
            t0 = time.monotonic()
            c = socket.create_connection(("127.0.0.1", s.port), timeout=15)
            c.sendall(b"GET /v1/status HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n" % s.port)  # never finished
            try:
                c.recv(1000)
            except OSError:
                pass
            c.close()
            self.assertLess(time.monotonic() - t0, 12)
            self.assertEqual(s.request("GET", "/v1/status")[0], 200)
            # slowloris: one byte a second passes every single read but not the whole request deadline
            t0 = time.monotonic()
            c = socket.create_connection(("127.0.0.1", s.port), timeout=15)
            cut = False
            for ch in b"GET /v1/status HTTP/1.1\r\nHost: 127.0.0.1:1\r\nX-Slow: " + b"a" * 60:
                try:
                    c.sendall(bytes([ch]))
                except OSError:
                    cut = True
                    break
                time.sleep(1.0)
                if time.monotonic() - t0 > 16:
                    break
            if not cut:
                c.settimeout(3)
                try:
                    cut = c.recv(100) == b""
                except ConnectionError:
                    cut = True
                except socket.timeout:
                    cut = False
            c.close()
            self.assertTrue(cut, "the server did not cut a request that took more than its 10 second deadline")
            self.assertLess(time.monotonic() - t0, 17)
            self.assertEqual(s.request("GET", "/v1/status")[0], 200)

    def test_the_17th_connection_gets_503_busy_at_once_and_the_server_recovers(self):
        with Server(self.root) as s:
            conns = []
            try:
                for _ in range(100):
                    c = socket.create_connection(("127.0.0.1", s.port), timeout=5)
                    conns.append(c)
                time.sleep(0.5)
                busy = 0
                for c in conns[16:]:
                    c.settimeout(2)
                    try:
                        data = c.recv(1000)
                    except (socket.timeout, OSError):
                        continue
                    if data.startswith(b"HTTP/1.1 503"):
                        busy += 1
                        self.assertIn(b'"busy"', data)
                self.assertGreaterEqual(busy, 80)
            finally:
                for c in conns:
                    c.close()
            time.sleep(0.5)
            self.assertEqual(s.request("GET", "/v1/status")[0], 200)

    def test_a_seeded_fuzz_never_gives_a_2xx_leaves_the_server_alive_and_prints_no_traceback(self):
        g = gen.Gen(4242)
        with Server(self.root) as s:
            pieces = [b"GET ", b"POST ", b"/v1/status", b"/", b" HTTP/1.1", b"\r\n", b"Host: 127.0.0.1:%d" % s.port,
                      b"Authorization: Bearer ", b"Content-Length: ", b"%", b"\x00", b"\xff", b"..", b"//", b"\r", b"\n",
                      b": ", b"Transfer-Encoding: chunked", b"\x1b[", b"a" * 300, b"?x=1&"]
            slowest = 0.0
            for i in range(FUZZ_N):
                if g.chance(0.5):
                    data = bytes(g.bits(8) for _ in range(g.between(0, 120)))
                else:
                    data = b"".join(g.pick(pieces) for _ in range(g.between(1, 12)))
                t0 = time.monotonic()
                raw = s.raw(data, read_timeout=12, shutdown_write=True)
                slowest = max(slowest, time.monotonic() - t0)
                if raw.startswith(b"HTTP/"):
                    status = int(raw.split(b" ", 2)[1])
                    self.assertFalse(200 <= status < 300, (i, data[:80], raw[:100]))
            self.assertLess(slowest, 12)
            self.assertEqual(s.request("GET", "/v1/status")[0], 200)
            threads = int(re.search(r"Threads:\s+(\d+)", Path(f"/proc/{s.proc.pid}/status").read_text()).group(1))
            self.assertLess(threads, 40)
            s.stop()
        self.assertNotIn("Traceback", s.stderr)


if __name__ == "__main__":
    unittest.main()
