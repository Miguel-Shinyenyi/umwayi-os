"""The security scan (tasks.md S.2.1 and S.2.2, requirement S.R5): the telemetry receiver under attack from the agent's
side. Every test runs `python -m umwayi agent run ...` as a real child process; the fake `claude` is the client.

  binding      it listens on 127.0.0.1 only (read back from /proc/net/tcp and tcp6), and ::1 and every other
               address of this machine refuse a connection
  run header   only the exact secret, given once, is accepted; the header name may be in any case (HTTP)
  sizes        exactly 1 MB is read; 1 MB and one byte is 413 before the body is sent; a short body, a long body,
               chunked, compressed, a Content-Length given twice
  slow client  a request that trickles in is cut at a 10 s whole-request deadline (S-Q6)
  many         200 connections at once: at most 16 handled, the rest answered 503 at once, umwayi's threads stay
               bounded, and the run's own report still counts (S-Q7)
  closed       the port refuses connections after umwayi exits, on every way out
"""

import os
import signal
import socket
import time
import unittest

from tests.budget.support import BudgetCase, api_request, logs

WAIT = {"do": "sleep", "s": 4}
END = {"do": "exit", "code": 0}
GOOD = logs(api_request(cost_micros=4321))


def good(**kw):
    return dict({"do": "otlp", "path": "/v1/logs", "body": GOOD}, **kw)


def listening(port: int) -> list:
    """The local addresses that listen on this TCP port, from /proc/net/tcp and tcp6 (state 0A is LISTEN)."""
    found = []
    for name, six in (("tcp", False), ("tcp6", True)):
        try:
            with open(f"/proc/net/{name}", encoding="ascii") as f:
                lines = f.read().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            local, state = line.split()[1], line.split()[3]
            addr, p = local.split(":")
            if state != "0A" or int(p, 16) != port:
                continue
            raw = bytes.fromhex(addr)
            if six:
                raw = b"".join(raw[i:i + 4][::-1] for i in range(0, 16, 4))
                found.append(socket.inet_ntop(socket.AF_INET6, raw))
            else:
                found.append(socket.inet_ntop(socket.AF_INET, raw[::-1]))
    return found


def addresses() -> list:
    """Every address of this machine other than loopback, IPv4 and IPv6, from /proc."""
    out = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 9))
        a = s.getsockname()[0]
        s.close()
        if not a.startswith("127."):
            out.append(a)
    except OSError:
        pass
    try:
        with open("/proc/net/if_inet6", encoding="ascii") as f:
            rows = f.read().splitlines()
        for line in rows:
            h, scope = line.split()[0], line.split()[3]
            a = socket.inet_ntop(socket.AF_INET6, bytes.fromhex(h))
            if a != "::1" and scope == "00":  # global scope only; link-local needs an interface name
                out.append(a)
    except OSError:
        pass
    return out


class ReceiverScan(BudgetCase):
    def statuses(self):
        return [c.get("status") for c in self.calls() if c.get("event") == "otlp"]

    def otlp_calls(self):
        return [c for c in self.calls() if c.get("event") == "otlp"]

    def port(self) -> int:
        [start] = self.started()
        return int(start["otel"]["OTEL_EXPORTER_OTLP_ENDPOINT"].rsplit(":", 1)[1])

    def settle(self):
        [st] = self.settles()
        return st

    def run1(self, *steps, extra=None):
        self.fake_log.unlink(missing_ok=True)
        n = len(self.settles())
        r = self.run_agent("reviewer", *steps, extra=extra)
        return r, (self.settles()[n] if len(self.settles()) > n else None)


class BindingTests(ReceiverScan):
    def test_it_listens_on_127_0_0_1_only(self):
        p = self.start_run("reviewer", {"do": "sleep", "s": 30})
        start = self.wait_for(lambda c: c.get("started"), what="the agent's start", proc=p)
        port = int(start["otel"]["OTEL_EXPORTER_OTLP_ENDPOINT"].rsplit(":", 1)[1])
        self.assertEqual(listening(port), ["127.0.0.1"])
        for addr in ["::1"] + addresses():
            with self.subTest(address=addr):
                family = socket.AF_INET6 if ":" in addr else socket.AF_INET
                s = socket.socket(family, socket.SOCK_STREAM)
                s.settimeout(5)
                with self.assertRaises(OSError):
                    s.connect((addr, port))
                s.close()
        p.terminate()
        self.finish(p)

    def test_the_port_is_closed_after_every_way_out(self):
        cases = {
            "normal end": ([good(), END], None, None),
            "kill switch": ([good(), {"do": "sleep", "s": 60}], "kill", None),
            "SIGTERM": ([good(), {"do": "sleep", "s": 60}], "term", None),
            "a crash in umwayi": ([good(), {"do": "sleep", "s": 60}], None, "umwayi.units:current_micros:crash"),
        }
        self.limits(per_day=100000, per_agent_per_day=100000, per_platform_per_day=100000)
        for label, (steps, how, fault) in cases.items():
            with self.subTest(case=label):
                self.fake_log.unlink(missing_ok=True)
                (self.root / ".umwayi" / "KILL").unlink(missing_ok=True)
                p = self.start_run("reviewer", *steps, fault=fault)
                self.wait_for(lambda c: c.get("event") == "otlp", what="the report", proc=None if fault else p,
                              timeout=60)
                port = self.port()
                if how == "kill":
                    self.kill_on()
                elif how == "term":
                    p.send_signal(signal.SIGTERM)
                code, out, err = self.finish(p, timeout=120)
                s = socket.socket()
                s.settimeout(5)
                with self.assertRaises(ConnectionRefusedError):
                    s.connect(("127.0.0.1", port))
                s.close()
        (self.root / ".umwayi" / "KILL").unlink(missing_ok=True)


class RunHeaderTests(ReceiverScan):
    def test_only_the_exact_secret_given_once_is_accepted(self):
        self.limits(per_day=100000, per_agent_per_day=100000, per_platform_per_day=100000)
        refused = {
            "missing": [],
            "wrong": ["x-umwayi-run: " + "0" * 32],
            "a prefix of the secret": ["x-umwayi-run: {prefix}"],
            "the secret and one more character": ["x-umwayi-run: {plus}"],
            "the secret in upper case": ["x-umwayi-run: {upper}"],
            "given twice, the right one first": ["x-umwayi-run: {secret}", "x-umwayi-run: " + "0" * 32],
            "given twice, the right one second": ["x-umwayi-run: " + "0" * 32, "x-umwayi-run: {secret}"],
            "given twice, both right": ["x-umwayi-run: {secret}", "x-umwayi-run: {secret}"],
        }
        for label, lines in refused.items():
            with self.subTest(case=label):
                r, st = self.run1(good(run_headers=lines), END)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)  # refused before the header: not invalid
                self.assertEqual(self.statuses(), [401])
                self.assertIn(": unknown ", st.added)
        r, st = self.run1(good(run_headers=["X-UMWAYI-RUN: {secret}"]), END)  # HTTP header names ignore case
        self.assertEqual(self.statuses(), [200])
        self.assertIn(": measured 4321 micros", st.added)

    def test_another_runs_secret_is_refused(self):
        self.limits(per_day=100000, per_agent_per_day=100000, per_platform_per_day=100000)
        self.run1(END)
        [first] = self.started()
        old = first["otel"]["OTEL_EXPORTER_OTLP_HEADERS"].split("=", 1)[1]
        r, st = self.run1(good(run_headers=["x-umwayi-run: " + old]), END)
        self.assertEqual(self.statuses(), [401])
        for c in self.calls():
            if c.get("started"):
                self.assertNotEqual(c["otel"]["OTEL_EXPORTER_OTLP_HEADERS"].split("=", 1)[1], old)
        self.assertNotIn(old, r.stdout + r.stderr + self.log_text())


class SizeTests(ReceiverScan):
    def setUp(self):
        super().setUp()
        self.limits(per_day=100000, per_agent_per_day=100000, per_platform_per_day=100000)

    def test_exactly_1_mb_is_read_and_one_byte_more_is_refused_before_the_body(self):
        r, st = self.run1({"do": "otlp", "exact": 1 << 20}, END)
        self.assertEqual(self.statuses(), [200], r.stdout)
        r, st = self.run1({"do": "otlp", "exact": (1 << 20) + 1}, WAIT)
        [c] = self.otlp_calls()
        self.assertEqual((c["status"], c["why"]), (413, "answered before the body"))
        self.assertEqual(r.returncode, 2)

    def test_a_body_shorter_or_longer_than_its_length(self):
        r, st = self.run1(good(short_by=10), WAIT)
        self.assertEqual(self.statuses(), [400])  # after the 5 s socket timeout: run invalid
        self.assertEqual(r.returncode, 2)
        r, st = self.run1(good(trailing="GARBAGE-AFTER-THE-BODY"), END)
        self.assertEqual(self.statuses(), [200])  # the extra bytes are never read; the connection is closed
        self.assertIn(": measured 4321 micros", st.added)

    def test_chunked_compressed_and_a_length_given_twice(self):
        cases = {
            "chunked, no length": (good(length=None, extra_headers=["Transfer-Encoding: chunked"]), 411),
            "chunked and a length": (good(extra_headers=["Transfer-Encoding: chunked"]), 400),
            "gzip": (good(extra_headers=["Content-Encoding: gzip"]), 415),
            "a second, different Content-Length": (good(extra_headers=["Content-Length: 5"]), 400),
        }
        for label, (step, code) in cases.items():
            with self.subTest(case=label):
                r, st = self.run1(step, WAIT)
                self.assertEqual(self.statuses(), [code])
                self.assertEqual(r.returncode, 2, r.stdout)  # after the run header matched: invalid
                self.assertIn(": unknown ", st.added)


class SlowAndManyTests(ReceiverScan):
    def setUp(self):
        super().setUp()
        self.limits(per_day=100000, per_agent_per_day=100000, per_platform_per_day=100000)

    def test_a_slow_client_is_cut_at_the_whole_request_deadline(self):
        # one byte every 2 s: each read is well inside the 5 s socket timeout, so only a whole-request deadline cuts it
        t = time.monotonic()
        r, st = self.run1(good(slow=2, slow_for=40), good(), END)
        took = time.monotonic() - t
        slow, fast = self.otlp_calls()
        self.assertNotEqual(slow["why"], "gave up", "the receiver let a slow request run past 40 s")
        self.assertLess(slow["seconds"], 15)
        self.assertEqual(fast["status"], 200)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)  # cut before its run header: not the agent's report
        self.assertIn(": measured 4321 micros", st.added)
        self.assertLess(took, 45)

    def test_a_slow_body_after_the_run_header_makes_the_run_invalid(self):
        r, st = self.run1(good(slow=1, slow_for=40, run_headers=["x-umwayi-run: {secret}"]), WAIT)
        [c] = self.otlp_calls()
        self.assertLess(c["seconds"], 15, c)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn(": unknown 1000000 micros", st.added)

    def test_200_connections_at_once(self):
        r, st = self.run1(good(hold={"n": 200, "for": 6}, retry=40), END)
        [hold] = [c for c in self.calls() if c.get("event") == "otlp_hold"]
        self.assertEqual(hold["opened"], 200)
        self.assertGreaterEqual(hold["closed"], 200 - 16, hold)  # answered 503 and closed at once
        self.assertLess(hold["peak_threads"], 60, hold)  # 16 handlers and their deadlines, not 200
        [c] = self.otlp_calls()
        self.assertEqual(c["status"], 200, c)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(": measured 4321 micros", st.added)
        self.assertIn("answered 503", st.checked)


if __name__ == "__main__":
    unittest.main()
