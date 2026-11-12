"""The token: create, rotate, revoke, status (W6.R4, W6.R16.4). `umwayi/servetoken.py`, `umwayi serve token ...`."""

import hashlib
import io
import json
import os
import re
import stat
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from tests.serve.support import (DATE, SENTINEL, TOKEN, InProc, RootCase, TtyOut, digest, logbook_entries, make_logbook,
                                 make_root, record, servetoken, snapshot_tree)
from umwayi import logbook
from umwayi.cli import main
from umwayi.errors import UmwayiError

TOKEN_RE = re.compile(r"umt1_[A-Za-z0-9_-]{43}")
RECORD = ".umwayi/serve.token"


class TokenBase(RootCase):
    def setUp(self):
        super().setUp()
        (self.root / RECORD).unlink()  # start with no token
        make_logbook(self.root)

    def cli(self, *argv, tty=True):
        out, err = (TtyOut() if tty else io.StringIO()), io.StringIO()
        with mock.patch("umwayi.cli._today", return_value=DATE), redirect_stderr(err):
            code = main(["--root", str(self.root), "serve", "token", *argv], out=out)
        return code, out.getvalue(), err.getvalue()

    def rec(self):
        return json.loads((self.root / RECORD).read_text())

    def serve_entries(self):
        return [e for e in logbook_entries(self.root) if e.source == "umwayi serve"]

    def failing_entries(self):
        real = logbook.append

        def broken(root, entry):
            if entry.source == "umwayi serve":
                raise UmwayiError("logbook: planted failure")
            return real(root, entry)

        return mock.patch.object(logbook, "append", broken)


class CreateTests(TokenBase):
    def test_create_writes_the_record_prints_the_token_once_and_logs_the_id_only(self):
        old = os.umask(0)  # whatever the umask, the record is private
        try:
            code, out, err = self.cli("create")
        finally:
            os.umask(old)
        self.assertEqual((code, err), (0, ""))
        token = TOKEN_RE.search(out).group(0)
        self.assertEqual(len(token), 48)
        self.assertEqual(out.count(token), 1)
        rec = self.rec()
        self.assertEqual(sorted(rec), ["created", "expires", "id", "schema", "sha256"])
        self.assertEqual((rec["schema"], rec["created"], rec["expires"]), (1, DATE, "2026-12-12"))  # 30 days
        self.assertRegex(rec["id"], r"^T-[0-9a-f]{8}$")
        self.assertEqual(rec["sha256"], hashlib.sha256(token.encode()).hexdigest())
        self.assertIn(rec["id"], out)
        self.assertIn("2026-12-12", out)
        self.assertEqual(stat.S_IMODE(os.stat(self.root / RECORD).st_mode), 0o600)
        text = (self.root / RECORD).read_text()
        self.assertEqual(text, json.dumps(rec, indent=2) + "\n")
        e = self.serve_entries()
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0].added, f"Created token {rec['id']}, expires on 2026-12-12.")
        self.assertIn("0600", e[0].checked)
        self.assertIn("shown once", e[0].not_done)
        for f in (self.root / "LOGBOOK.md",):
            self.assertNotIn(token, f.read_text())
            self.assertNotIn(rec["sha256"], f.read_text())

    def test_create_when_the_output_is_not_a_terminal_writes_nothing_and_prints_no_token(self):
        before = snapshot_tree(self.root)
        code, out, err = self.cli("create", tty=False)
        self.assertEqual(code, 1)
        self.assertNotRegex(out + err, TOKEN_RE)
        self.assertEqual(snapshot_tree(self.root), before)

    def test_create_when_a_record_exists_is_refused_and_changes_nothing(self):
        self.cli("create")
        before = snapshot_tree(self.root)
        code, out, err = self.cli("create")
        self.assertEqual(code, 1)
        self.assertNotRegex(out, TOKEN_RE)
        self.assertEqual(snapshot_tree(self.root), before)

    def test_a_broken_record_also_counts_as_existing(self):
        (self.root / RECORD).write_text("not json")
        self.assertEqual(self.cli("create")[0], 1)

    def test_days(self):
        for days, expires in (("1", "2026-11-13"), ("90", "2027-02-10"), ("30", "2026-12-12")):
            (self.root / RECORD).unlink(missing_ok=True)
            code, out, _ = self.cli("create", "--days", days)
            self.assertEqual(code, 0, days)
            self.assertEqual(self.rec()["expires"], expires)
        for bad in ("0", "91", "-1", "x", "1.5", ""):
            (self.root / RECORD).unlink(missing_ok=True)
            code, out, err = self.cli("create", "--days", bad)
            self.assertEqual(code, 64, bad)
            self.assertFalse((self.root / RECORD).exists())

    def test_a_failed_entry_removes_the_record_and_prints_no_token(self):
        with self.failing_entries():
            code, out, err = self.cli("create")
        self.assertEqual(code, 2)
        self.assertNotRegex(out + err, TOKEN_RE)
        self.assertFalse((self.root / RECORD).exists())

    def test_an_unexpected_error_is_exit_2_and_prints_no_text(self):
        with mock.patch("umwayi.servetoken.secrets.token_bytes", side_effect=RuntimeError(SENTINEL)):
            code, out, err = self.cli("create")
        self.assertEqual(code, 2)
        self.assertNotIn(SENTINEL, out + err)
        self.assertFalse((self.root / RECORD).exists())

    def test_the_token_is_32_random_bytes_and_the_id_is_not_derived_from_it(self):
        seen = set()
        for _ in range(5):
            (self.root / RECORD).unlink(missing_ok=True)
            _, out, _ = self.cli("create")
            seen.add(TOKEN_RE.search(out).group(0))
            self.assertNotIn(self.rec()["id"][2:], digest(TOKEN_RE.search(out).group(0)) + TOKEN_RE.search(out).group(0))
        self.assertEqual(len(seen), 5)


class RotateTests(TokenBase):
    def test_rotate_needs_a_record(self):
        code, out, err = self.cli("rotate")
        self.assertEqual(code, 1)
        self.assertNotRegex(out, TOKEN_RE)

    def test_rotate_replaces_the_record_and_names_both_ids(self):
        _, out1, _ = self.cli("create")
        old = self.rec()
        code, out2, err = self.cli("rotate", "--days", "10")
        self.assertEqual((code, err), (0, ""))
        new = self.rec()
        self.assertNotEqual(new["id"], old["id"])
        self.assertNotEqual(new["sha256"], old["sha256"])
        self.assertEqual(new["expires"], "2026-11-22")
        t2 = TOKEN_RE.search(out2).group(0)
        self.assertNotEqual(t2, TOKEN_RE.search(out1).group(0))
        self.assertEqual(new["sha256"], digest(t2))
        self.assertEqual(stat.S_IMODE(os.stat(self.root / RECORD).st_mode), 0o600)
        self.assertEqual(self.serve_entries()[-1].added, f"Rotated token {old['id']} to {new['id']}, expires on 2026-11-22.")

    def test_the_old_token_stops_working_on_the_next_request_without_a_restart(self):
        (self.root / RECORD).write_text(json.dumps(record(TOKEN), indent=2) + "\n")
        os.chmod(self.root / RECORD, 0o600)
        web = InProc(self.root)
        self.assertEqual(web.get("/v1/queue").word, "done")
        _, out, _ = self.cli("rotate")
        new = TOKEN_RE.search(out).group(0)
        self.assertEqual((web.get("/v1/queue").status, web.get("/v1/queue").word), (401, "token"))
        self.assertEqual(web.get("/v1/queue", token=new).word, "done")

    def test_a_failed_entry_puts_the_old_record_back_byte_for_byte_and_prints_nothing(self):
        self.cli("create")
        before = (self.root / RECORD).read_bytes()
        with self.failing_entries():
            code, out, err = self.cli("rotate")
        self.assertEqual(code, 2)
        self.assertNotRegex(out + err, TOKEN_RE)
        self.assertEqual((self.root / RECORD).read_bytes(), before)
        self.assertEqual(stat.S_IMODE(os.stat(self.root / RECORD).st_mode), 0o600)

    def test_rotate_when_the_output_is_not_a_terminal(self):
        self.cli("create")
        before = snapshot_tree(self.root)
        code, out, _ = self.cli("rotate", tty=False)
        self.assertEqual(code, 1)
        self.assertEqual(snapshot_tree(self.root), before)


class RevokeAndStatusTests(TokenBase):
    def test_revoke_removes_the_record_and_logs_it(self):
        self.cli("create")
        tid = self.rec()["id"]
        code, out, _ = self.cli("revoke")
        self.assertEqual(code, 0)
        self.assertFalse((self.root / RECORD).exists())
        self.assertEqual(self.serve_entries()[-1].added, f"Revoked token {tid}.")

    def test_revoke_without_a_record_is_a_refusal(self):
        self.assertEqual(self.cli("revoke")[0], 1)

    def test_a_failed_entry_puts_the_record_back_on_revoke(self):
        self.cli("create")
        before = (self.root / RECORD).read_bytes()
        with self.failing_entries():
            code, _, _ = self.cli("revoke")
        self.assertEqual(code, 2)
        self.assertEqual((self.root / RECORD).read_bytes(), before)

    def test_every_request_gets_401_after_a_revoke_and_the_server_keeps_running(self):
        (self.root / RECORD).write_text(json.dumps(record(TOKEN), indent=2) + "\n")
        web = InProc(self.root)
        self.assertEqual(web.get("/v1/queue").word, "done")
        self.cli("revoke")
        self.assertEqual(web.get("/v1/queue").status, 401)
        self.assertEqual(web.get("/v1/status").status, 401)

    def test_status_without_a_token(self):
        code, out, _ = self.cli("status")
        self.assertEqual((code, out.strip()), (0, "No token."))

    def test_status_prints_the_id_the_dates_and_the_days_left_and_nothing_secret(self):
        _, created, _ = self.cli("create", "--days", "10")
        token = TOKEN_RE.search(created).group(0)
        code, out, err = self.cli("status", tty=False)
        self.assertEqual((code, err), (0, ""))
        self.assertIn(self.rec()["id"], out)
        self.assertIn("created 2026-11-12", out)
        self.assertIn("expires 2026-11-22", out)
        self.assertIn("10 days left", out)
        self.assertNotIn(token, out)
        self.assertNotIn(self.rec()["sha256"], out)

    def test_status_does_not_look_at_the_logbook_and_writes_nothing(self):
        self.cli("create")
        (self.root / "LOGBOOK.md").write_text("garbage")
        before = snapshot_tree(self.root)
        code, out, _ = self.cli("status")
        self.assertEqual(code, 0)
        self.assertEqual(snapshot_tree(self.root), before)

    def test_status_on_an_expired_token_says_so_and_is_still_exit_0(self):
        self.cli("create", "--days", "1")
        with mock.patch("umwayi.cli._today", return_value="2026-11-20"):
            out = TtyOut()
            code = main(["--root", str(self.root), "serve", "token", "status"], out=out)
        self.assertEqual(code, 0)
        self.assertIn("expired", out.getvalue())


class RecordReaderTests(TokenBase):
    def bad(self, text=None, make=None):
        p = self.root / RECORD
        if p.exists() or p.is_symlink():
            p.unlink()
        if make:
            make(p)
        else:
            p.write_text(text)
        return servetoken.read_record(self.root)

    def test_the_good_record_is_read(self):
        (self.root / RECORD).write_text(json.dumps(record(TOKEN), indent=2) + "\n")
        self.assertEqual(servetoken.read_record(self.root), record(TOKEN))

    def test_no_file_gives_none(self):
        self.assertIsNone(servetoken.read_record(self.root))

    def test_what_is_refused(self):
        good = record(TOKEN)
        cases = {
            "extra key": {**good, "x": 1},
            "missing key": {k: v for k, v in good.items() if k != "id"},
            "schema 2": {**good, "schema": 2},
            "schema true": {**good, "schema": True},
            "bad id": {**good, "id": "T-ZZZZZZZZ"},
            "upper case digest": {**good, "sha256": good["sha256"].upper()},
            "short digest": {**good, "sha256": good["sha256"][:60]},
            "bad date": {**good, "created": "2026-13-45"},
            "expires before created": {**good, "expires": "2026-11-11"},
            "expires on created": {**good, "expires": good["created"]},
            "91 days": {**good, "expires": "2027-02-11"},
            "not a date": {**good, "expires": "soon"},
        }
        for name, rec in cases.items():
            with self.subTest(name):
                self.assertIsNone(self.bad(json.dumps(rec)))
        for name, text in (("not json", "{"), ("a list", "[]"), ("empty", ""), ("duplicate key",
                           '{"schema":1,"schema":1,"id":"T-91ab02cd","sha256":"' + good["sha256"] + '","created":"2026-11-12","expires":"2026-12-12"}'),
                           ("nan", '{"schema":NaN}')):
            with self.subTest(name):
                self.assertIsNone(self.bad(text))

    def test_a_link_a_folder_and_a_big_file_are_refused(self):
        target = self.tmp / "elsewhere.json"
        target.write_text(json.dumps(record(TOKEN)))
        self.assertIsNone(self.bad(make=lambda p: p.symlink_to(target)))
        self.assertIsNone(self.bad(make=lambda p: p.mkdir()))
        (self.root / RECORD).rmdir()
        self.assertIsNone(self.bad(text=json.dumps(record(TOKEN)) + " " * 2048))

    def test_a_server_with_a_broken_record_refuses_every_request_as_a_wrong_token(self):
        for text in ("", "{", "[]"):
            (self.root / RECORD).write_text(text)
            web = InProc(self.root)
            self.assertEqual((web.get("/v1/status").status, web.get("/v1/status").word), (401, "token"))


class ExpiryTests(TokenBase):
    def test_expiry_is_judged_on_the_latest_of_the_date_and_the_newest_logbook_date(self):
        (self.root / RECORD).write_text(json.dumps(record(TOKEN, expires="2026-11-20"), indent=2) + "\n")
        web = InProc(self.root, today="2026-11-12")
        self.assertEqual(web.get("/v1/status").word, "done")
        # the logbook now holds a later date (another run, a later day); a clock set back does not revive the token
        logbook.append(self.root, logbook.Entry("2026-11-25", "tests", "later", "later", "later"))
        self.assertEqual(web.get("/v1/status").status, 401)

    def test_the_last_day_is_the_day_before_the_expiry_date(self):
        (self.root / RECORD).write_text(json.dumps(record(TOKEN, expires="2026-11-20"), indent=2) + "\n")
        for day, status in (("2026-11-19", 200), ("2026-11-20", 401), ("2026-11-21", 401)):
            web = InProc(self.root, today=day)
            make_ok = web.get("/v1/status", token=TOKEN)
            self.assertEqual(make_ok.status, status, day)


class NoLeakTests(TokenBase):
    def test_a_planted_token_is_found_nowhere(self):
        (self.root / RECORD).write_text(json.dumps(record(TOKEN), indent=2) + "\n")
        web = InProc(self.root)
        replies = [web.get("/v1/queue"), web.post("/v1/queue", {"kind": "task", "title": "T"}),
                   web.get("/v1/queue", token=TOKEN + "x"), web.get("/v1/nothing")]
        err = io.StringIO()
        with redirect_stderr(err):
            self.cli("status")
        for r in replies:
            self.assertNotIn(TOKEN.encode(), r.raw)
        self.assertNotIn(TOKEN, err.getvalue())
        for p in self.root.rglob("*"):
            if p.is_file():
                self.assertNotIn(TOKEN.encode(), p.read_bytes(), p)


class GuardTests(unittest.TestCase):
    """W6.R4.9, W6.R16.7: an AI helper cannot run `umwayi serve` or touch the token file (text matching, KNOWN-LIMITS 12)."""

    def test_the_example_rules_of_the_adapters_refuse_the_command_and_the_token_file(self):
        from adapters.common import umwayi_gate as gate
        from umwayi.rules import NO, decide, load_rules
        repo = Path(__file__).resolve().parents[2]
        cases = {
            "claude_code": [gate.tool_action("claude-code", "Bash", {"command": "umwayi serve token create"}),
                            gate.tool_action("claude-code", "Bash", {"command": "umwayi serve"}),
                            gate.tool_action("claude-code", "Bash", {"command": "cat x/.umwayi/serve.token"}),
                            gate.tool_action("claude-code", "Read", {"file_path": "/r/.umwayi/serve.token"}),
                            gate.tool_action("claude-code", "Write", {"file_path": "/r/.umwayi/serve.token"})],
            "kiro": [gate.generic_action("kiro", "execute_bash", {"command": "umwayi serve"}),
                     gate.generic_action("kiro", "execute_bash", {"command": "cat .umwayi/serve.token"}),
                     gate.generic_action("kiro", "fs_write", {"path": "/r/.umwayi/serve.token"})],
            "opencode": [gate.generic_action("opencode", "shell", {"command": "umwayi serve"}),
                         gate.generic_action("opencode", "read", {"path": "/r/.umwayi/serve.token"}),
                         gate.generic_action("opencode", "write", {"path": "/r/.umwayi/serve.token"})],
        }
        for name, actions in cases.items():
            for rules_file in (repo / "adapters" / name / "rules.example.yaml", repo / "rules.yaml"):
                rules = load_rules(rules_file)
                for action in actions:
                    with self.subTest(adapter=name, file=rules_file.name, action=action):
                        self.assertEqual(decide(rules, action, today="2026-11-12").answer, NO)

    def test_git_ignores_the_token_record_and_the_lock(self):
        lines = (Path(__file__).resolve().parents[2] / ".gitignore").read_text().splitlines()
        self.assertIn(".umwayi/serve.token", lines)
        self.assertIn(".umwayi/serve.lock", lines)


if __name__ == "__main__":
    unittest.main()
