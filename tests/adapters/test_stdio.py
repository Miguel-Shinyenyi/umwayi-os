"""The generic stdin and stdout adapter, run as a real child process."""

import json
import time
import unittest

from tests.adapters.support import REPO, SECRET, AdapterCase

HOOK = REPO / "adapters" / "stdio" / "hook.py"
RULES = REPO / "adapters" / "stdio" / "rules.example.yaml"
CODES = {"allow": 0, "deny": 2, "ask": 3}

READ = {"tool_name": "read", "tool_input": {"path": "/p/a"}}
DEPLOY = {"tool_name": "deploy", "tool_input": {"target": "staging"}}
PROD = {"tool_name": "deploy", "tool_input": {"target": "prod-eu"}}


class StdioCase(AdapterCase):
    HOOK, RULES = HOOK, RULES

    def hook(self, payload, **kw):
        code, out, err = self.raw(payload, **kw)
        # the contract, for every run: one JSON answer whose decision matches the exit code; never exit 1
        self.assertIn(code, (0, 2, 3), f"exit {code}\n{out}\n{err}")
        answer = json.loads(out)
        self.assertEqual(CODES[answer["decision"]], code)
        self.assertIsInstance(answer["reason"], str)
        if code == 2:
            self.assertTrue(err.strip())
        self.assertNotIn(SECRET, out + err)
        self.assertNotIn("Traceback", err)
        return code, answer, err


class AnswerTests(StdioCase):
    def test_yes_no_ask(self):
        self.assertEqual(self.hook(READ)[:2], (0, {"decision": "allow", "reason": "umwayi: Yes (rule stdio-read). Reading is allowed."}))
        code, answer, _ = self.hook(PROD)
        self.assertEqual((code, answer["decision"]), (2, "deny"))
        self.assertIn("rule stdio-no-prod", answer["reason"])
        code, answer, _ = self.hook(DEPLOY)
        self.assertEqual((code, answer["decision"]), (3, "ask"))
        self.assertEqual(self.queue_rows(), [])  # it can ask, so no queue item

    def test_no_ask_platform_gets_deny_plus_one_queue_item(self):
        args = ["--root", str(self.root), "--no-ask"]
        code, answer, _ = self.hook(DEPLOY, args=args)
        self.assertEqual((code, answer["decision"]), (2, "deny"))
        self.assertEqual(answer["queue"], "Added Q-0001 (decision): The stdio platform asks first: may it do tool_deploy?")
        self.hook(DEPLOY, args=args)
        self.assertEqual(len(self.queue_rows()), 1)
        self.assertEqual(self.hook(READ, args=args)[0], 0)  # a Yes is still a Yes

    def test_the_platform_comes_from_the_command_line_not_the_input(self):
        self.assertEqual(self.hook({**READ, "platform": "something-else"})[0], 0)  # ignored
        code, _, _ = self.hook(READ, args=["--root", str(self.root), "--platform", "other"])
        self.assertEqual(code, 3)  # rules for platform stdio do not match "other": Ask me first
        for bad in ("Bad", "a b", "x" * 21, ""):
            with self.subTest(platform=bad):
                self.assertEqual(self.hook(READ, args=["--root", str(self.root), "--platform", bad])[0], 2)


class FailClosedTests(StdioCase):
    def test_broken_rules_deny(self):
        (self.root / "rules.yaml").write_text("rules: [\n")
        for p in (READ, DEPLOY, PROD):
            code, answer, _ = self.hook(p)
            self.assertEqual(code, 2)
            self.assertIn("rules.yaml could not be used", answer["reason"])

    def test_a_crash_inside_the_adapter_denies(self):
        for target in ("adapters.common.umwayi_gate:decide", "adapters.common.umwayi_gate:generic_action",
                       "adapters.common.umwayi_gate:run_check", "adapters.common.umwayi_gate:parse_args",
                       "adapters.common.umwayi_gate:add_queue_item"):
            for effect in ("crash", "interrupt"):
                with self.subTest(target=target, effect=effect):
                    args = ["--root", str(self.root), "--no-ask"]
                    code, answer, _ = self.hook(DEPLOY, args=args, fault=f"{target}:{effect}")
                    self.assertEqual((code, answer["decision"]), (2, "deny"))
                    self.assertIn("blocked by an unexpected error", answer["reason"])

    def test_a_crash_inside_umwayi_denies(self):
        for target in ("umwayi.rules:decide", "umwayi.logbook:render"):
            with self.subTest(target=target):
                self.assertEqual(self.hook(READ, fault=f"{target}:crash")[0], 2)

    def test_bad_input_and_arguments_deny(self):
        for payload in ("{bad", "", [1], {"tool_input": {}}, {"tool_name": "x", "tool_input": []}, b"\xff"):
            with self.subTest(payload=str(payload)[:20]):
                self.assertEqual(self.hook(payload)[0], 2)
        for args in ([], ["--root"], ["--root", str(self.root), "--timeout", "-1"], ["--root", str(self.root), "--yes"]):
            with self.subTest(args=args):
                self.assertEqual(self.hook(READ, args=args)[0], 2)

    def test_a_missing_root_is_refused_by_name(self):
        code, answer, err = self.hook(READ, args=["--platform", "stdio"])
        self.assertEqual(code, 2)
        self.assertIn("blocked, --root is required", answer["reason"])
        self.assertNotIn("unexpected error", err)

    def test_a_timeout_denies_in_time(self):
        start = time.monotonic()
        code, answer, _ = self.hook(READ, args=["--root", str(self.root), "--timeout", "1"], fault="umwayi.rules:load_rules:hang")
        self.assertLess(time.monotonic() - start, 10)
        self.assertEqual(code, 2)


class KillSwitchTests(StdioCase):
    def test_on_or_unknown_denies_everything(self):
        self.kill_on()
        for p in (READ, DEPLOY):
            for args in (None, ["--root", str(self.root), "--no-ask"]):
                code, answer, _ = self.hook(p, args=args)
                self.assertEqual((code, answer["decision"]), (2, "deny"))
                self.assertIn("kill switch", answer["reason"])
        self.assertEqual(self.queue_rows(), [])
        self.kill_off()
        self.assertEqual(self.hook(READ)[0], 0)
        self.kill_unknown()
        self.assertEqual(self.hook(READ)[0], 2)


class LogbookTests(StdioCase):
    def test_one_entry_per_check_and_verify_stays_ok(self):
        for n, p in enumerate([READ, DEPLOY, PROD, {"tool_name": "x", "tool_input": {"token": SECRET}}], 1):
            self.hook(p)
            self.assertEqual(len([e for e in self.entries() if e == "- Source: umwayi check"]), n)
        self.assertEqual(self.umwayi("logbook", "verify").returncode, 0)
        self.assertNotIn(SECRET, self.log.read_text())


if __name__ == "__main__":
    unittest.main()
