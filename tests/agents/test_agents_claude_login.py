"""Layer 10 part 7c-1, tasks 10.33 to 10.35: subscription first for Claude Code (requirement 10.R12 items 2 to 7).

The login check reads `auth status --json` (fake `claude`, or fake `node` for `--cli auth status --json`) and
starts a Claude Code agent only when a Claude subscription login is what pays. The scripted answers name a
planted email, organisation and secret, which must never reach the screen, the logbook or the queue.
Every end-to-end test runs `python -m umwayi agent ...` as a real child process. No real Claude Code, no network,
no key.
"""

import ast
import json
import subprocess
import sys
import unittest

from umwayi import agents

from tests.agents.support import REPO, SECRET, AgentCase
from tests.agents.test_agents_claude_acp_gate import ClaudeAcpCase

EMAIL = "owner@example.invalid"
ORG = "Planted Org Name"
SUB = {"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "max", "email": EMAIL, "orgId": SECRET,
       "orgName": ORG}
AGENTS = """agents:
  - name: reviewer
    platform: claude-code
    command: claude
    workdir: {work}
"""
CREDENTIALS = {name: f"{SECRET}-{name}" for name in agents.CLAUDE_CREDENTIAL_ENV}


def j(obj) -> bytes:
    return json.dumps(obj).encode("utf-8")


def with_(**kw) -> dict:
    d = dict(SUB)
    for k, v in kw.items():
        if v is None:
            d.pop(k, None)
        else:
            d[k] = v
    return d


# (label, exit code, output, words in the detail)
REFUSED = [
    ("not signed in, exit 1", 1, j({"loggedIn": False, "authMethod": "none", "email": EMAIL}), "not signed in"),
    ("not signed in, exit 0", 0, j(with_(loggedIn=False)), "not signed in"),
    ("authMethod none", 0, j(with_(authMethod="none")), "not signed in"),
    ("an API key", 0, j(with_(authMethod="api_key")), "an API key pays"),
    ("an apiKeyHelper", 0, j(with_(authMethod="api_key_helper")), "an apiKeyHelper in a settings file pays"),
    ("oauth_token is refused", 0, j(with_(authMethod="oauth_token")), "CLAUDE_CODE_OAUTH_TOKEN pays"),
    ("third party", 0, j(with_(authMethod="third_party")), "a cloud provider or gateway pays"),
    ("an unknown method", 0, j(with_(authMethod="sso-magic")), "could not be confirmed"),
    ("a helper next to a subscription", 0, j(with_(apiKeySource="apiKeyHelper")), "an API key from an apiKeyHelper pays"),
    ("ANTHROPIC_API_KEY source", 0, j(with_(apiKeySource="ANTHROPIC_API_KEY")),
     "an API key from ANTHROPIC_API_KEY pays"),
    ("a Console login", 0, j(with_(apiKeySource="/login managed key")), "Console is API billing"),
    ("an unknown key source", 0, j(with_(apiKeySource="somewhere")), "an API key pays"),
    ("a null key source", 0, j(with_(apiKeySource=None) | {"apiKeySource": None}), "could not be confirmed"),
    ("bedrock", 0, j(with_(apiProvider="bedrock")), "a cloud provider or gateway pays"),
    ("a null provider", 0, j(with_() | {"apiProvider": None}), "could not be confirmed"),
    ("no subscription", 0, j(with_(subscriptionType=None)), "no Claude subscription was reported"),
    ("an empty plan", 0, j(with_(subscriptionType="")), "no Claude subscription was reported"),
    ("a plan with a control character", 0, j(with_(subscriptionType="max\x1b[2J")), "no Claude subscription"),
    ("a plan with a bidi character", 0, j(with_(subscriptionType="max\u202e")), "no Claude subscription"),
    ("a plan of 41 characters", 0, j(with_(subscriptionType="a" * 41)), "no Claude subscription"),
    ("a plan that is a number", 0, j(with_(subscriptionType=5)), "no Claude subscription"),
    ("loggedIn as a string", 0, j(with_(loggedIn="true")), "could not be confirmed"),
    ("loggedIn missing", 0, j(with_(loggedIn=None)), "could not be confirmed"),
    ("authMethod missing", 0, j(with_(authMethod=None)), "could not be confirmed"),
    ("a JSON list", 0, j([SUB]), "could not be confirmed"),
    ("not JSON", 0, b"Logged in as " + EMAIL.encode(), "could not be confirmed"),
    ("JSON then text", 0, j(SUB) + b" trailing", "could not be confirmed"),
    ("invalid UTF-8", 0, b'{"loggedIn": true, "x": "\xff"}', "could not be confirmed"),
    ("over 64 KB", 0, j(with_(pad="x" * agents.MAX_LOGIN_OUTPUT)), "could not be confirmed"),
    ("an odd exit code", 3, j(SUB), "could not be confirmed"),
    ("no answer", None, b"", "no answer within 15 s"),
]


class LoginCheckUnitTests(unittest.TestCase):
    def test_a_subscription_passes_and_gives_only_the_plan_word(self):
        ok, detail, plan = agents.login_check(0, j(SUB))
        self.assertTrue(ok)
        self.assertEqual((detail, plan), ("Claude subscription (plan: max)", "max"))
        for plan_word in ("pro", "max", "team", "enterprise", "claude max 20x", "ultra_1-x"):
            self.assertEqual(agents.login_check(0, j(with_(subscriptionType=plan_word)))[2], plan_word)
        self.assertTrue(agents.login_check(0, j(with_(apiProvider="firstParty")))[0])
        self.assertTrue(agents.login_check(0, j(with_(extra={"a": [1, 2]}, configDirectory="/x")))[0])

    def test_every_refused_shape(self):
        for label, code, out, words in REFUSED:
            with self.subTest(case=label):
                ok, detail, plan = agents.login_check(code, out)
                self.assertFalse(ok)
                self.assertIsNone(plan)
                self.assertIn(words, detail)
                for planted in (EMAIL, ORG, SECRET, "somewhere", "sso-magic", "x" * 100):
                    self.assertNotIn(planted, detail)

    def test_every_refusal_names_its_fix(self):
        fixes = {"not signed in": agents.SIGNIN_TEXT, "an API key": "unset", "Console": "Claude account",
                 "a cloud provider": "CLAUDE_CODE_USE_BEDROCK", "could not be confirmed": agents.SIGNIN_TEXT}
        for _label, code, out, _words in REFUSED:
            detail = agents.login_check(code, out)[1]
            self.assertTrue(any(k in detail and v in detail for k, v in fixes.items())
                            or "no Claude subscription" in detail or "CLAUDE_CODE_OAUTH_TOKEN" in detail
                            or "apiKeyHelper" in detail, detail)

    def test_claude_env_removes_only_the_credential_names(self):
        environ = dict(CREDENTIALS, PATH="/bin", HOME="/h", TERM="xterm", EDITOR="vi", KIRO_API_KEY="k")
        env = agents.claude_env(environ)
        self.assertEqual(env, {"PATH": "/bin", "HOME": "/h", "TERM": "xterm", "EDITOR": "vi", "KIRO_API_KEY": "k"})
        self.assertEqual(set(agents.CLAUDE_CREDENTIAL_ENV), {
            "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_OAUTH_TOKEN",
            "CLAUDE_CODE_OAUTH_REFRESH_TOKEN", "CLAUDE_CODE_OAUTH_SCOPES", "CLAUDE_CODE_USE_BEDROCK",
            "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY", "ANTHROPIC_PROFILE", "ANTHROPIC_FEDERATION_RULE_ID",
            "ANTHROPIC_ORGANIZATION_ID", "ANTHROPIC_IDENTITY_TOKEN_FILE"})
        # the ACP allow list already leaves every one of them out
        self.assertFalse(set(agents.CLAUDE_CREDENTIAL_ENV) & set(agents.CHILD_ENV_NAMES))

    def test_force_login_method_is_in_the_one_template(self):
        s = json.loads(agents.claude_settings("/usr/bin/python3", REPO / "adapters/claude_code/hook.py", REPO))
        self.assertEqual(s["forceLoginMethod"], "claudeai")
        meta = agents.claude_acp_session_meta("/usr/bin/python3", REPO, "/tmp/x", "0" * 32)
        settings = meta["claudeCode"]["options"]["settings"]
        self.assertEqual(settings["forceLoginMethod"], "claudeai")
        self.assertEqual(settings["hooks"]["PreToolUse"], s["hooks"]["PreToolUse"])


class CodeGuardTests(unittest.TestCase):
    def test_login_check_reads_only_the_named_fields(self):
        src = (REPO / "umwayi" / "agents.py").read_text(encoding="utf-8")
        self.assertEqual(agents.LOGIN_FIELDS, ("loggedIn", "authMethod", "apiKeySource", "apiProvider",
                                               "subscriptionType"))
        for name in ('"email"', '"orgId"', '"orgName"', "'email'", "'orgId'", "'orgName'"):
            self.assertNotIn(name, src)
        tree = ast.parse(src)
        [fn] = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "login_check"]
        uses = [n for n in ast.walk(fn) if isinstance(n, ast.Name) and n.id == "data"]
        # json.loads target, the isinstance check, the one comprehension over LOGIN_FIELDS (twice) and the del
        self.assertEqual(len(uses), 5)
        # every field read from the copy f is one of the named fields
        read = set()
        for n in ast.walk(fn):
            if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id == "f":
                read.add(n.slice.value)
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "get"
                    and isinstance(n.func.value, ast.Name) and n.func.value.id == "f"):
                read.add(n.args[0].value)
            if isinstance(n, ast.Compare) and isinstance(n.left, ast.Constant) and any(
                    isinstance(c, ast.Name) and c.id == "f" for c in n.comparators):
                read.add(n.left.value)
        self.assertTrue(read)
        self.assertLessEqual(read, set(agents.LOGIN_FIELDS))

    def test_only_the_two_fixed_sign_ins_and_never_a_forbidden_login_word(self):
        """Part 7c-2 (10.R12.9) replaced "umwayi signs in for no one": the sign-in is exactly
        [NODE, ADAPTER, --cli, auth, login, --claudeai] or [KIRO, login], and the words of another method,
        a named account, a token or a sign-out appear only in the list that forbids them."""
        import ast
        src = (REPO / "umwayi" / "agents.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden = set(agents.LOGIN_FORBIDDEN)
        allowed_nodes = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "LOGIN_FORBIDDEN" for t in node.targets):
                allowed_nodes = {id(n) for n in ast.walk(node)}
        self.assertTrue(allowed_nodes)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in forbidden:
                self.assertIn(id(node), allowed_nodes, f"{node.value!r} outside LOGIN_FORBIDDEN (line {node.lineno})")
        self.assertEqual(agents.CLAUDE_LOGIN_TAIL, ("--cli", "auth", "login", "--claudeai"))
        self.assertEqual(src.count('"auth", "login"'), 1)  # CLAUDE_LOGIN_TAIL only
        self.assertEqual(src.count('[command_path, "login"]'), 1)  # the Kiro sign-in only
        self.assertEqual(src.count('"auth", "status", "--json"'), 2)  # cli and ACP: the only auth status lists


class RunAndCliChatTests(AgentCase):
    def setUp(self):
        super().setUp()
        self.fake("claude")
        self.write_rules()
        self.write_agents(AGENTS)

    def auth(self, answer=None, code=0) -> dict:
        return {"FAKE_CLAUDE_AUTH": answer if isinstance(answer, str) else json.dumps(answer or SUB),
                "FAKE_CLAUDE_AUTH_EXIT": str(code)}

    def leaked(self, r) -> str:
        queue = self.root / "queue.md"
        log = self.root / "LOGBOOK.md"
        text = r.stdout + r.stderr + (log.read_text(encoding="utf-8") if log.exists() else "")
        return text + (queue.read_text(encoding="utf-8") if queue.exists() else "")

    def chat(self, extra):
        r = subprocess.run([sys.executable, "-m", "umwayi", "--root", str(self.root), "agent", "chat", "reviewer"],
                           input="/quit\n", capture_output=True, text=True, timeout=120, env=self.env(extra),
                           cwd=str(self.tmp))
        self.assertIn(r.returncode, (0, 2, 3, 64), r.stdout + r.stderr)
        return r

    def test_agent_run_with_a_subscription_starts_and_the_plan_is_logged(self):
        r = self.umwayi("run", "reviewer", "--prompt", "hello", extra=self.auth())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(self.started()), 1)
        started = [e for e in self.run_entries() if e.added.startswith("Started agent reviewer")]
        self.assertEqual(len(started), 1)
        self.assertIn("plan: max", started[0].checked)
        for planted in (EMAIL, ORG, SECRET):
            self.assertNotIn(planted, self.leaked(r))

    def test_every_refused_shape_starts_nothing_for_run_and_cli_chat(self):
        shapes = [("api key", with_(authMethod="api_key")), ("helper", with_(apiKeySource="apiKeyHelper")),
                  ("console", with_(apiKeySource="/login managed key")), ("oauth", with_(authMethod="oauth_token")),
                  ("signed out", {"loggedIn": False, "authMethod": "none", "email": EMAIL}),
                  ("bedrock", with_(apiProvider="bedrock")), ("no plan", with_(subscriptionType=None))]
        for label, answer in shapes:
            for how in ("run", "chat"):
                with self.subTest(case=label, how=how):
                    self.fake_log.unlink(missing_ok=True)
                    extra = self.auth(answer, 1 if answer.get("loggedIn") is False else 0)
                    r = (self.umwayi("run", "reviewer", "--prompt", "hello", extra=extra) if how == "run"
                         else self.chat(extra))
                    self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                    self.assertEqual(self.started(), [], "an agent was started")
                    self.assertIn("no: login: ", r.stdout)
                    self.assertIn("not run: hook script", r.stdout)
                    refused = [e for e in self.run_entries() if e.added.startswith("Refused agent reviewer")]
                    self.assertTrue(refused)
                    self.assertTrue(refused[-1].added.startswith("Refused agent reviewer: not gated (login: "))
                    for planted in (EMAIL, ORG, SECRET):
                        self.assertNotIn(planted, self.leaked(r))

    def test_a_hanging_login_check_is_refused(self):
        r = self.umwayi("run", "reviewer", "--prompt", "hello", extra=dict(self.auth(), FAKE_CLAUDE_AUTH_HANG="1"))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("no answer within 15 s", r.stdout)
        self.assertEqual(self.started(), [])

    def test_the_credential_names_never_reach_the_agent_or_its_login_check(self):
        extra = dict(self.auth(), **CREDENTIALS, KEEP_ME="1")
        r = self.umwayi("run", "reviewer", "--prompt", "hello", extra=extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        [probe] = [c for c in self.calls() if c.get("probe") == "auth"]
        [agent] = self.started()
        version = [c for c in self.calls() if c.get("argv") == ["-v"]]
        self.assertEqual(probe["cwd"], str(self.work))
        for names in (set(probe["env_keys"]), set(agent["env_keys"])):
            self.assertFalse(names & set(agents.CLAUDE_CREDENTIAL_ENV), names & set(agents.CLAUDE_CREDENTIAL_ENV))
            self.assertIn("KEEP_ME", names)  # the deny list removes only the credential names
        self.assertEqual(set(probe["env_keys"]), set(agent["env_keys"]))
        self.assertTrue(version)
        r = self.chat(extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        chat = [c for c in self.started() if c.get("chat")][-1]
        self.assertFalse(set(chat["env_keys"]) & set(agents.CLAUDE_CREDENTIAL_ENV))

    def test_force_login_method_reaches_run_and_cli_chat(self):
        self.assertEqual(self.umwayi("run", "reviewer", "--prompt", "hello", extra=self.auth()).returncode, 0)
        self.assertEqual(self.chat(self.auth()).returncode, 0)
        for c in self.started():
            settings = json.loads(c["argv"][c["argv"].index("--settings") + 1])
            self.assertEqual(settings["forceLoginMethod"], "claudeai")

    def test_agent_check_shows_the_plan_and_never_the_person(self):
        r = self.umwayi("check", "reviewer", extra=self.auth())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ok: login: Claude subscription (plan: max)", r.stdout)
        for planted in (EMAIL, ORG, SECRET):
            self.assertNotIn(planted, r.stdout + r.stderr)
        self.assertFalse((self.root / "LOGBOOK.md").exists())


class AcpLoginTests(ClaudeAcpCase):
    def test_the_acp_checks_refuse_an_api_key_and_never_show_the_person(self):
        self.answers(auth_json=with_(authMethod="api_key", orgName=SECRET))
        r = self.check()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("no: login: an API key pays", r.stdout)
        self.assertIn("not run: hook script", r.stdout)
        for planted in (EMAIL, SECRET):
            self.assertNotIn(planted, r.stdout + r.stderr)
        [login] = [c for c in self.node_calls() if c["probe"] == "login"]
        self.assertEqual(login["argv"][1:], [str(self.adapter), "--cli", "auth", "status", "--json"])
        self.assertEqual(login["cwd"], str(self.work))
        self.assertFalse(set(login["env"]) & set(agents.CLAUDE_CREDENTIAL_ENV))

    def test_the_acp_checks_pass_with_a_subscription_and_show_the_plan(self):
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("ok: login: Claude subscription (plan: max)", r.stdout)


if __name__ == "__main__":
    unittest.main()
