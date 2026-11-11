"""Layer 10 part 8, task 10.44: `opencode_env()` and `opencode_inline_config()` (requirement 10.R13.4 to 10.R13.6,
design.md part 8, "The inline config"). Both functions are pure: they read no file, start nothing and write nothing.

Written before the code. What is checked:

* the exact bytes of the inline config for every route (the free tier, ollama, lmstudio, vllm, openai and
  github-copilot), against literal text with only the route's own values filled in, so a test never rebuilds the
  answer with the code it tests;
* what the config holds and does not hold: the order of the policies, no `models` entry under a built-in local
  provider (10.42: it breaks the route), `openai#*` and never the bare `openai`, nothing else;
* the same agent and token give the same bytes, also in a fresh interpreter with another hash seed;
* a root path, folder, Python path or source path that holds `{env:` or `{file:` is refused (OpenCode would replace
  it, NOTES Nov 11), and so is every input the config must not carry (a relative path, a short token, an agent that
  is not an OpenCode agent, a route that is not offered, Go);
* the environment is an allow list: every provider credential, every `OPENCODE_*` name of 10.R13.4 and every cloud
  variable is planted in a real child process's environment and is absent from what `opencode_env()` returns there.
"""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from umwayi import agents

from tests.agents.support import REPO, SECRET

ROOT = Path("/home/me/umwayi")
SRC = Path("/home/me/umwayi-os")
FOLDER = "/tmp/umwayi-opencode-abcd"
PYTHON = "/usr/bin/python3"
TOKEN = "0123456789abcdef0123456789abcdef"

# One literal template. Only the five marked places change from route to route.
TEMPLATE = (
    '{"model":"%(model)s",'
    '"permissions":[{"action":"*","effect":"ask","resource":"*"}],'
    '"plugins":[{"options":{"canary":"/tmp/umwayi-opencode-abcd/canary","hook":["/usr/bin/python3",'
    '"/home/me/umwayi-os/adapters/stdio/hook.py","--root","/home/me/umwayi","--platform","opencode"],'
    '"token":"%(token)s"},"package":"/home/me/umwayi-os/adapters/opencode/plugin"}],'
    '"policies":[{"action":"provider.use","effect":"deny","resource":"*"},'
    '{"action":"provider.use","effect":"allow","resource":"%(provider)s"},'
    '{"action":"integration.use","effect":"deny","resource":"*"},'
    '{"action":"integration.use","effect":"allow","resource":"%(integration)s"}]%(providers)s}'
)


def local(provider: str, url: str) -> str:
    return ',"providers":{"%s":{"settings":{"baseURL":"%s"}}}' % (provider, url)


# provider, model, the integration.use resource that is allowed, the providers fragment
ROUTES = [
    ("opencode", "opencode/big-pickle", "opencode", ""),
    ("ollama", "ollama/qwen3-coder", "ollama", local("ollama", "http://127.0.0.1:11434/v1")),
    ("lmstudio", "lmstudio/openai/gpt-oss-20b", "lmstudio", local("lmstudio", "http://127.0.0.1:1234/v1")),
    ("vllm", "vllm/qwen3-coder-30b", "vllm", local("vllm", "http://127.0.0.1:8000/v1")),
    ("openai", "openai/gpt-5", "openai#*", ""),
    ("github-copilot", "github-copilot/gpt-4o", "github-copilot#*", ""),
]


def agent(provider: str | None = "ollama", model: str | None = "ollama/qwen3-coder", platform: str = "opencode"):
    commands = {"opencode": "opencode", "claude-code": "claude", "kiro": "kiro-cli"}
    return agents.Agent("o", platform, commands[platform], "acp", "/w", provider=provider, model=model)


def config(a=None, **over) -> str:
    args = dict(root=ROOT, token=TOKEN, folder=FOLDER, python=PYTHON, src=SRC)
    args.update(over)
    return agents.opencode_inline_config(a if a is not None else agent(), **args)


def want(provider, model, integration, providers, token=TOKEN) -> str:
    return TEMPLATE % {"model": model, "token": token, "provider": provider, "integration": integration,
                       "providers": providers}


class ExactBytesTests(unittest.TestCase):
    def test_every_route_gives_exactly_these_bytes(self):
        for provider, model, integration, providers in ROUTES:
            with self.subTest(provider=provider):
                self.assertEqual(config(agent(provider, model)), want(provider, model, integration, providers))

    def test_the_design_example_for_ollama_is_these_bytes_written_out_in_full(self):
        self.assertEqual(
            config(),
            '{"model":"ollama/qwen3-coder","permissions":[{"action":"*","effect":"ask","resource":"*"}],'
            '"plugins":[{"options":{"canary":"/tmp/umwayi-opencode-abcd/canary","hook":["/usr/bin/python3",'
            '"/home/me/umwayi-os/adapters/stdio/hook.py","--root","/home/me/umwayi","--platform","opencode"],'
            '"token":"0123456789abcdef0123456789abcdef"},"package":"/home/me/umwayi-os/adapters/opencode/plugin"}],'
            '"policies":[{"action":"provider.use","effect":"deny","resource":"*"},'
            '{"action":"provider.use","effect":"allow","resource":"ollama"},'
            '{"action":"integration.use","effect":"deny","resource":"*"},'
            '{"action":"integration.use","effect":"allow","resource":"ollama"}],'
            '"providers":{"ollama":{"settings":{"baseURL":"http://127.0.0.1:11434/v1"}}}}')

    def test_the_free_tier_is_these_bytes_written_out_in_full(self):
        self.assertEqual(
            config(agent("opencode", "opencode/big-pickle")),
            '{"model":"opencode/big-pickle","permissions":[{"action":"*","effect":"ask","resource":"*"}],'
            '"plugins":[{"options":{"canary":"/tmp/umwayi-opencode-abcd/canary","hook":["/usr/bin/python3",'
            '"/home/me/umwayi-os/adapters/stdio/hook.py","--root","/home/me/umwayi","--platform","opencode"],'
            '"token":"0123456789abcdef0123456789abcdef"},"package":"/home/me/umwayi-os/adapters/opencode/plugin"}],'
            '"policies":[{"action":"provider.use","effect":"deny","resource":"*"},'
            '{"action":"provider.use","effect":"allow","resource":"opencode"},'
            '{"action":"integration.use","effect":"deny","resource":"*"},'
            '{"action":"integration.use","effect":"allow","resource":"opencode"}]}')

    def test_a_subscription_route_allows_only_a_connected_account(self):
        for provider, model in (("openai", "openai/gpt-5"), ("github-copilot", "github-copilot/gpt-4o")):
            with self.subTest(provider=provider):
                text = config(agent(provider, model))
                self.assertIn('{"action":"integration.use","effect":"allow","resource":"%s#*"}' % provider, text)
                parsed = json.loads(text)
                resources = [p["resource"] for p in parsed["policies"] if p["action"] == "integration.use"]
                self.assertEqual(resources, ["*", provider + "#*"])  # never the bare name (an environment key)

    def test_the_free_tier_allows_the_bare_opencode_only(self):
        parsed = json.loads(config(agent("opencode", "opencode/big-pickle")))
        resources = [p["resource"] for p in parsed["policies"] if p["action"] == "integration.use"]
        self.assertEqual(resources, ["*", "opencode"])  # so a signed-in Console account (opencode#ACCOUNT) is not used

    def test_the_key_order_is_sorted_and_the_text_is_compact_ascii(self):
        for provider, model, _, _ in ROUTES:
            with self.subTest(provider=provider):
                text = config(agent(provider, model))
                self.assertTrue(text.isascii())
                self.assertNotIn(" ", text)
                self.assertNotIn("\n", text)
                self.assertEqual(json.dumps(json.loads(text), sort_keys=True, separators=(",", ":")), text)

    def test_the_default_source_is_this_checkout(self):
        text = config(src=None)
        parsed = json.loads(text)
        [plugin] = parsed["plugins"]
        self.assertEqual(plugin["package"], str(REPO / "adapters" / "opencode" / "plugin"))
        self.assertEqual(plugin["options"]["hook"][:2], [PYTHON, str(REPO / "adapters" / "stdio" / "hook.py")])


class WhatTheConfigHoldsTests(unittest.TestCase):
    def parsed(self, provider="ollama", model="ollama/qwen3-coder"):
        return json.loads(config(agent(provider, model)))

    def walk(self, node):
        yield node
        if isinstance(node, dict):
            for v in node.values():
                yield from self.walk(v)
        elif isinstance(node, list):
            for v in node:
                yield from self.walk(v)

    def test_exactly_these_top_level_keys(self):
        for provider, model, _, providers in ROUTES:
            with self.subTest(provider=provider):
                keys = set(self.parsed(provider, model))
                self.assertEqual(keys, {"model", "permissions", "plugins", "policies"}
                                 | ({"providers"} if providers else set()))

    def test_one_ask_rule_for_everything(self):
        self.assertEqual(self.parsed()["permissions"], [{"action": "*", "resource": "*", "effect": "ask"}])

    def test_the_policies_are_in_this_order(self):
        for provider, model, integration, _ in ROUTES:
            with self.subTest(provider=provider):
                got = [(p["action"], p["effect"], p["resource"]) for p in self.parsed(provider, model)["policies"]]
                self.assertEqual(got, [("provider.use", "deny", "*"), ("provider.use", "allow", provider),
                                       ("integration.use", "deny", "*"), ("integration.use", "allow", integration)])

    def test_the_model_is_the_agents_model(self):
        for provider, model, _, _ in ROUTES:
            self.assertEqual(self.parsed(provider, model)["model"], model)

    def test_one_plugin_with_the_three_options(self):
        [plugin] = self.parsed()["plugins"]
        self.assertEqual(set(plugin), {"package", "options"})
        self.assertEqual(plugin["package"], "/home/me/umwayi-os/adapters/opencode/plugin")
        self.assertEqual(set(plugin["options"]), {"hook", "canary", "token"})
        self.assertEqual(plugin["options"]["hook"], [PYTHON, "/home/me/umwayi-os/adapters/stdio/hook.py",
                                                     "--root", "/home/me/umwayi", "--platform", "opencode"])
        self.assertEqual(plugin["options"]["canary"], FOLDER + "/canary")
        self.assertEqual(plugin["options"]["token"], TOKEN)

    def test_the_token_is_in_the_text_once(self):
        self.assertEqual(config().count(TOKEN), 1)

    def test_a_local_route_has_a_base_url_and_never_a_models_entry(self):
        # 10.42: a `models` entry under a built-in local provider breaks the route (provider.no-route)
        for provider, url in (("ollama", "http://127.0.0.1:11434/v1"), ("lmstudio", "http://127.0.0.1:1234/v1"),
                              ("vllm", "http://127.0.0.1:8000/v1")):
            with self.subTest(provider=provider):
                parsed = self.parsed(provider, f"{provider}/m")
                self.assertEqual(parsed["providers"], {provider: {"settings": {"baseURL": url}}})
        for provider, model, _, _ in ROUTES:
            for node in self.walk(self.parsed(provider, model)):
                if isinstance(node, dict):
                    self.assertNotIn("models", node)

    def test_a_route_with_an_account_has_no_providers_entry(self):
        for provider, model in (("opencode", "opencode/big-pickle"), ("openai", "openai/gpt-5"),
                                ("github-copilot", "github-copilot/gpt-4o")):
            self.assertNotIn("providers", self.parsed(provider, model))

    def test_no_secret_field_and_nothing_of_the_agent_but_its_route_and_model(self):
        text = config(agent("openai", "openai/gpt-5"))
        for word in ("apiKey", "api_key", "password", "secret", "env", "OPENCODE", "ANTHROPIC", '"/w"',
                     "Authorization", "enabled_providers", "disabled_providers", "experimental", "agents",
                     "instructions", "mcp", "autoupdate", "share", "snapshot", "options\":{\"apiKey"):
            self.assertNotIn(word, text, word)

    def test_a_non_ascii_path_is_escaped_and_comes_back_whole(self):
        root = "/home/m\u00e9/umwayi"
        text = config(root=root)
        self.assertTrue(text.isascii())
        self.assertIn("\\u00e9", text)
        self.assertEqual(json.loads(text)["plugins"][0]["options"]["hook"][3], root)

    def test_a_path_with_a_quote_a_backslash_or_a_newline_stays_one_json_string(self):
        for root in ('/home/a"b', "/home/a\\b", "/home/a\nb", "/home/a b"):
            with self.subTest(root=root):
                text = config(root=root)
                self.assertEqual(json.loads(text)["plugins"][0]["options"]["hook"][3], root)
                self.assertNotIn("\n", text)

    def test_the_hook_runs_the_layer_9_generic_adapter_for_the_opencode_platform(self):
        hook = json.loads(config())["plugins"][0]["options"]["hook"]
        self.assertEqual(hook[-2:], ["--platform", "opencode"])
        self.assertNotIn("--no-ask", hook)  # an ask is answered by the permission request, not turned into a deny


class SameBytesTests(unittest.TestCase):
    def test_the_same_agent_and_token_give_the_same_bytes(self):
        a = agent()
        self.assertEqual(config(a), config(a))
        self.assertEqual(config(agent()), config(agent()))

    def test_another_token_changes_only_the_token(self):
        other = "f" * 32
        self.assertEqual(config(token=other), config().replace(TOKEN, other))
        self.assertNotEqual(config(token=other), config())

    def test_a_fresh_interpreter_with_other_hash_seeds_gives_the_same_bytes(self):
        code = ("import sys; from pathlib import Path; from umwayi import agents; "
                "a = agents.Agent('o', 'opencode', 'opencode', 'acp', '/w', provider='vllm', model='vllm/qwen3-coder-30b'); "
                "sys.stdout.write(agents.opencode_inline_config(a, root=Path('/home/me/umwayi'), "
                f"token='{TOKEN}', folder='{FOLDER}', python='{PYTHON}', src=Path('/home/me/umwayi-os')))")
        outputs = set()
        for seed in ("0", "1", "2", "random"):
            r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60,
                               env={"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(REPO),
                                    "PYTHONHASHSEED": seed})
            self.assertEqual(r.returncode, 0, r.stderr)
            outputs.add(r.stdout)
        self.assertEqual(outputs, {want("vllm", "vllm/qwen3-coder-30b", "vllm",
                                        local("vllm", "http://127.0.0.1:8000/v1"))})


class RefusalTests(unittest.TestCase):
    def refused(self, *args, words=None, **kw):
        with self.assertRaises(agents.OpenCodeRefused) as cm:
            config(*args, **kw)
        msg = str(cm.exception)
        self.assertTrue(msg.endswith("Nothing was started."), msg)
        if words:
            self.assertIn(words, msg)
        return msg

    def test_a_substitution_token_in_any_path_is_refused(self):
        for token in ("{env:HOME}", "{file:/etc/passwd}", "{ENV:HOME}", "{File:x}", "{env:", "{file:"):
            for field, value in (("root", f"/home/{token}/umwayi"), ("folder", f"/tmp/{token}"),
                                 ("python", f"/usr/{token}/python3"), ("src", Path(f"/srv/{token}/umwayi-os"))):
                with self.subTest(token=token, field=field):
                    msg = self.refused(**{field: value}, words="{env:")
                    self.assertIn("{file:", msg)
                    if token not in ("{env:", "{file:"):  # the message names the two prefixes, never the value
                        self.assertNotIn(token, msg)
                    self.assertNotIn("passwd", msg)
                    self.assertNotIn("HOME", msg)
                    self.assertNotIn(str(value), msg)

    def test_a_brace_that_is_not_a_substitution_is_not_refused(self):
        text = config(root="/home/me/{not-a-token}/umwayi")
        self.assertIn("{not-a-token}", text)
        self.assertIn("{env", config(root="/home/{env/umwayi"))  # no colon: OpenCode does not replace it

    def test_a_relative_path_is_refused(self):
        for field, value in (("root", "umwayi"), ("folder", "tmp/x"), ("python", "python3"), ("src", Path("umwayi-os"))):
            with self.subTest(field=field):
                self.refused(**{field: value}, words="absolute")

    def test_an_empty_or_odd_path_is_refused(self):
        for field in ("root", "folder", "python"):
            for value in ("", "/a\x00b", 5, None):
                with self.subTest(field=field, value=value):
                    self.refused(**{field: value})

    def test_a_bad_token_is_refused(self):
        for token in ("", "short", "has space 0123456789abc", "{env:HOME}0123456789abcdef", "a" * 129, None, 5,
                      "0123456789abcdef0123456789abcde/", "0123456789abcdef0123456789abcde\n"):
            with self.subTest(token=token):
                self.refused(token=token, words="token")

    def test_an_agent_that_is_not_an_opencode_agent_is_refused(self):
        for platform in ("claude-code", "kiro"):
            with self.subTest(platform=platform):
                self.refused(agent(platform=platform), words="OpenCode")

    def test_an_agent_without_provider_or_model_is_refused(self):
        self.refused(agent(provider=None))
        self.refused(agent(model=None))
        self.refused(agent(provider=None, model=None))

    def test_a_model_of_another_provider_or_a_bad_model_is_refused(self):
        self.refused(agent("ollama", "vllm/qwen3"), words="model")
        for model in ("qwen3", "ollama/", "Ollama/x", "ollama/-x", "ollama/a b", "ollama/{env:X}", "ollama/a" + "b" * 121):
            with self.subTest(model=model):
                self.refused(agent("ollama", model), words="model")

    def test_a_bad_provider_is_refused(self):
        for provider in ("", "Ollama", "a/b", "a b", "{env:X}", "p" * 41):
            with self.subTest(provider=provider):
                self.refused(agent(provider, f"{provider}/m"))

    def test_pay_as_you_go_routes_are_refused(self):
        for provider in ("openrouter", "anthropic", "together", "fireworks", "groq", "huggingface", "amazon-bedrock",
                         "google", "azure", "mistral", "deepseek", "xai"):
            with self.subTest(provider=provider):
                msg = self.refused(agent(provider, f"{provider}/some-model"), words="pay as you go is not offered")
                self.assertIn(provider, msg)

    def test_opencode_go_is_refused_with_its_own_line(self):
        msg = self.refused(agent("opencode-go", "opencode-go/some-model"), words="OpenCode Go")
        self.assertNotIn("pay as you go is not offered", msg)

    def test_the_route_function_is_the_one_table(self):
        self.assertEqual(sorted(agents.OPENCODE_ROUTES), sorted(p for p, *_ in ROUTES))
        for provider, _, integration, providers in ROUTES:
            route_integration, url = agents.OPENCODE_ROUTES[provider]
            self.assertEqual(route_integration, integration)
            self.assertEqual(bool(url), bool(providers))


# --------------------------------------------------------------------------- the environment (10.R13.4)

LISTED = {  # the names the allow list passes, each with a value
    "HOME": "/h", "USER": "u", "LOGNAME": "u", "PATH": "/bin", "SHELL": "/bin/sh", "LANG": "C.UTF-8",
    "LANGUAGE": "en", "LC_ALL": "C.UTF-8", "LC_CTYPE": "C.UTF-8", "LC_MESSAGES": "C", "TZ": "UTC",
    "TMPDIR": "/tmp", "XDG_CONFIG_HOME": "/xdg/c", "XDG_DATA_HOME": "/xdg/d", "XDG_CACHE_HOME": "/xdg/k",
    "XDG_STATE_HOME": "/xdg/s", "XDG_RUNTIME_DIR": "/run/u", "HTTPS_PROXY": "http://p:1", "HTTP_PROXY": "http://p:2",
    "NO_PROXY": "localhost", "https_proxy": "http://p:3", "http_proxy": "http://p:4", "no_proxy": "lo",
    "NODE_EXTRA_CA_CERTS": "/ca.pem", "SSL_CERT_FILE": "/c.pem", "SSL_CERT_DIR": "/certs",
}
DROPPED = {  # planted in the environment, never passed
    # 10.R13.4, by name
    "OPENCODE_API_KEY": SECRET, "OPENCODE_CONFIG": "/evil/opencode.json", "OPENCODE_CONFIG_DIR": "/evil/dir",
    "OPENCODE_DB": "/evil/opencode.db", "OPENCODE_PASSWORD": SECRET, "OPENCODE_DISABLE_PROJECT_CONFIG": "1",
    # every other OPENCODE_ name, known or made up (nothing else that starts with OPENCODE_ is passed)
    "OPENCODE_CONFIG_PROJECT_DISABLE": "1", "OPENCODE_MODELS_URL": "http://evil", "OPENCODE_MODELS_PATH": "/evil",
    "OPENCODE_SIMULATE": "1", "OPENCODE_GIT_BASH_PATH": "/evil", "OPENCODE_CLI_CONFIG_CONTENT": "{}",
    "OPENCODE_FILEWATCHER_DISABLE": "1", "OPENCODE_DISABLE_CLAUDE_CODE": "1", "OPENCODE_SOMETHING_NEW": "x",
    "OPENCODE": "1",
    # provider credentials
    "ANTHROPIC_API_KEY": SECRET, "ANTHROPIC_AUTH_TOKEN": SECRET, "ANTHROPIC_BASE_URL": "https://" + SECRET,
    "OPENAI_API_KEY": SECRET, "OPENAI_BASE_URL": "https://" + SECRET, "OPENROUTER_API_KEY": SECRET,
    "TOGETHER_API_KEY": SECRET, "FIREWORKS_API_KEY": SECRET, "GROQ_API_KEY": SECRET, "HF_TOKEN": SECRET,
    "HUGGINGFACE_API_KEY": SECRET, "MISTRAL_API_KEY": SECRET, "DEEPSEEK_API_KEY": SECRET, "XAI_API_KEY": SECRET,
    "GEMINI_API_KEY": SECRET, "GOOGLE_API_KEY": SECRET, "GITHUB_TOKEN": SECRET, "GH_TOKEN": SECRET,
    "COPILOT_GITHUB_TOKEN": SECRET, "CEREBRAS_API_KEY": SECRET, "PERPLEXITY_API_KEY": SECRET,
    "META_API_KEY": SECRET, "EXA_API_KEY": SECRET, "TAVILY_API_KEY": SECRET,
    # cloud credentials
    "AWS_BEARER_TOKEN_BEDROCK": SECRET, "AWS_ACCESS_KEY_ID": SECRET, "AWS_SECRET_ACCESS_KEY": SECRET,
    "AWS_SESSION_TOKEN": SECRET, "AWS_PROFILE": "p", "AWS_WEB_IDENTITY_TOKEN_FILE": "/t", "AWS_REGION": "r",
    "GOOGLE_APPLICATION_CREDENTIALS": "/g.json", "GOOGLE_CLOUD_PROJECT": "p", "AZURE_RESOURCE_NAME": "r",
    "AZURE_API_KEY": SECRET, "AZURE_CLIENT_SECRET": SECRET, "CLOUDFLARE_API_TOKEN": SECRET,
    # the Claude Code ones of the 10.R11.9 list that OpenCode does not need
    "CLAUDE_CONFIG_DIR": "/claude", "CLAUDE_AGENT_ACP_PROTOCOL": "v9", "CLAUDE_CODE_OAUTH_TOKEN": SECRET,
    # runtime and loader names
    "NODE_OPTIONS": "--require=/evil.js", "NODE_PATH": "/evil", "BUN_INSTALL": "/evil", "BUN_CONFIG_REGISTRY": "x",
    "npm_config_registry": "http://evil", "NPM_CONFIG_USERCONFIG": "/evil", "LD_PRELOAD": "/evil.so",
    "LD_LIBRARY_PATH": "/evil", "PYTHONPATH_OTHER": "x", "EDITOR": "vi", "BROWSER": "firefox", "DISPLAY": ":0",
    "SSH_AUTH_SOCK": "/s", "GIT_SSH_COMMAND": "evil", "http_PROXY": "x", "Https_Proxy": "x",
}


class EnvAllowListTests(unittest.TestCase):
    def test_the_list_is_the_one_of_10_r13_4(self):
        want_names = {"HOME", "USER", "LOGNAME", "PATH", "SHELL", "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE",
                      "LC_MESSAGES", "TZ", "TMPDIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
                      "XDG_STATE_HOME", "XDG_RUNTIME_DIR", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy",
                      "http_proxy", "no_proxy", "NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE", "SSL_CERT_DIR"}
        self.assertEqual(set(agents.OPENCODE_ENV_NAMES), want_names)
        self.assertEqual(len(agents.OPENCODE_ENV_NAMES), len(want_names))
        self.assertEqual(set(LISTED), want_names)  # the fixture is the list
        # 10.R11.9 without the two Claude Code names
        self.assertEqual(set(agents.OPENCODE_ENV_NAMES), set(agents.CHILD_ENV_NAMES) - {"CLAUDE_CONFIG_DIR"})
        self.assertNotIn("CLAUDE_AGENT_ACP_PROTOCOL", agents.OPENCODE_ENV_NAMES)

    def test_no_name_on_the_list_starts_with_a_name_the_task_forbids(self):
        for name in agents.OPENCODE_ENV_NAMES:
            self.assertFalse(name.upper().startswith(("OPENCODE", "ANTHROPIC", "OPENAI", "CLAUDE", "AWS_", "AZURE",
                                                      "GOOGLE", "NODE_OPTIONS", "NODE_PATH", "BUN_", "NPM_CONFIG")),
                             name)
            self.assertFalse(name.endswith(("_KEY", "_TOKEN", "_SECRET", "_PASSWORD")), name)

    def test_only_listed_names_that_are_set_and_the_one_config_variable(self):
        given = dict(LISTED, **DROPPED)
        env = agents.opencode_env(given, '{"a":1}')
        self.assertEqual(env, dict(LISTED, OPENCODE_CONFIG_CONTENT='{"a":1}'))

    def test_a_listed_name_that_is_not_set_is_not_invented(self):
        self.assertEqual(agents.opencode_env({}, "{}"), {"OPENCODE_CONFIG_CONTENT": "{}"})
        self.assertEqual(agents.opencode_env({"HOME": "/h"}, "{}"), {"HOME": "/h", "OPENCODE_CONFIG_CONTENT": "{}"})

    def test_a_value_that_is_not_text_is_not_passed(self):
        env = agents.opencode_env({"HOME": "/h", "PATH": None, "TZ": 5, "LANG": b"x", "USER": ["u"]}, "{}")
        self.assertEqual(env, {"HOME": "/h", "OPENCODE_CONFIG_CONTENT": "{}"})

    def test_a_config_variable_in_umwayis_own_environment_is_replaced_never_passed_on(self):
        env = agents.opencode_env({"OPENCODE_CONFIG_CONTENT": '{"permissions":[]}', "HOME": "/h"}, '{"mine":true}')
        self.assertEqual(env["OPENCODE_CONFIG_CONTENT"], '{"mine":true}')
        self.assertEqual(env, {"HOME": "/h", "OPENCODE_CONFIG_CONTENT": '{"mine":true}'})

    def test_the_content_is_passed_exactly(self):
        text = config()
        self.assertEqual(agents.opencode_env({}, text)["OPENCODE_CONFIG_CONTENT"], text)

    def test_the_input_is_not_changed(self):
        given = dict(LISTED, **DROPPED)
        before = dict(given)
        agents.opencode_env(given, "{}")
        self.assertEqual(given, before)

    def test_the_content_must_be_text_without_a_nul(self):
        for content in (None, 5, b"{}", ["{}"], "{}\x00"):
            with self.subTest(content=content):
                with self.assertRaises(agents.OpenCodeRefused) as cm:
                    agents.opencode_env({}, content)
                self.assertTrue(str(cm.exception).endswith("Nothing was started."))

    def test_every_dropped_name_is_absent_one_by_one(self):
        for name, value in DROPPED.items():
            with self.subTest(name=name):
                env = agents.opencode_env({name: value, "HOME": "/h"}, '{"c":1}')
                self.assertNotIn(name, env)
                self.assertNotIn(value, env.values())

    def test_no_other_name_starting_with_opencode_ever_gets_through(self):
        for name in ("OPENCODE_A", "OPENCODE_CONFIG", "OPENCODE_CONFIG_CONTENT_2", "opencode_config_content",
                     "OpenCode_Config_Content"):
            env = agents.opencode_env({name: "x"}, "{}")
            self.assertEqual(env, {"OPENCODE_CONFIG_CONTENT": "{}"}, name)

    def test_case_matters_for_the_listed_names(self):
        env = agents.opencode_env({"home": "/h", "Path": "/p", "http_proxy": "p", "HTTP_proxy": "q"}, "{}")
        self.assertEqual(env, {"http_proxy": "p", "OPENCODE_CONFIG_CONTENT": "{}"})


class EnvInARealChildProcessTests(unittest.TestCase):
    """The names are planted in the environment of a real Python process, and `os.environ` is what is passed in."""

    def run_child(self, content_code: str, extra: dict | None = None) -> dict:
        planted = dict(LISTED, **DROPPED)
        planted.update(extra or {})
        planted["PYTHONPATH"] = str(REPO)  # not on the list: it must not come back either
        code = ("import json, os; from umwayi import agents; "
                f"print(json.dumps(agents.opencode_env(os.environ, {content_code})))")
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=planted, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(SECRET, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def test_every_planted_name_is_gone_and_every_listed_one_is_there(self):
        env = self.run_child("'{\"x\":1}'")
        self.assertEqual(env, dict(LISTED, OPENCODE_CONFIG_CONTENT='{"x":1}'))

    def test_a_planted_config_variable_does_not_survive(self):
        env = self.run_child("'{\"mine\":1}'", {"OPENCODE_CONFIG_CONTENT": '{"permissions":[],"policies":[]}'})
        self.assertEqual(env["OPENCODE_CONFIG_CONTENT"], '{"mine":1}')

    def test_each_name_of_10_r13_4_is_named_and_absent(self):
        env = self.run_child("'{}'")
        for name in ("OPENCODE_API_KEY", "OPENCODE_CONFIG", "OPENCODE_CONFIG_DIR", "OPENCODE_DB", "OPENCODE_PASSWORD",
                     "OPENCODE_DISABLE_PROJECT_CONFIG", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY",
                     "AWS_BEARER_TOKEN_BEDROCK", "AWS_ACCESS_KEY_ID", "GOOGLE_APPLICATION_CREDENTIALS",
                     "AZURE_RESOURCE_NAME", "HF_TOKEN", "GITHUB_TOKEN"):
            self.assertIn(name, DROPPED)
            self.assertNotIn(name, env)

    def test_an_empty_environment_gives_only_the_config(self):
        code = "import json; from umwayi import agents; print(json.dumps(agents.opencode_env({}, '{}')))"
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60,
                           env={"PYTHONPATH": str(REPO)})
        self.assertEqual(json.loads(r.stdout), {"OPENCODE_CONFIG_CONTENT": "{}"})


class CodeGuardTests(unittest.TestCase):
    def source(self):
        return (REPO / "umwayi" / "agents.py").read_text(encoding="utf-8")

    def test_the_two_functions_exist_and_are_plain_functions(self):
        import ast
        tree = ast.parse(self.source())
        names = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        self.assertIn("opencode_env", names)
        self.assertIn("opencode_inline_config", names)

    def test_the_two_functions_use_no_file_process_clock_or_global_environment(self):
        import ast
        tree = ast.parse(self.source())
        for fn in tree.body:
            if isinstance(fn, ast.FunctionDef) and fn.name in ("opencode_env", "opencode_inline_config", "opencode_route"):
                for n in ast.walk(fn):
                    if isinstance(n, ast.Attribute):
                        self.assertNotIn(n.attr, {"environ", "getenv", "run", "Popen", "open", "exists", "isfile", "isdir",
                                                  "read_text", "read_bytes", "write_text", "mkdtemp", "which", "lstat",
                                                  "stat", "time", "monotonic", "urandom", "token_hex", "realpath"},
                                         f"{fn.name} uses {n.attr}")
                    if isinstance(n, ast.Name):
                        self.assertNotIn(n.id, {"open", "print"}, f"{fn.name} uses {n.id}")

    def test_the_config_is_made_by_json_dumps_with_sorted_keys_and_ascii(self):
        src = self.source()
        self.assertEqual(src.count("json.dumps(config, sort_keys=True, separators=(\",\", \":\"), ensure_ascii=True)"), 1)


if __name__ == "__main__":
    unittest.main()
