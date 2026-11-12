"""Planted faults and mutation checks for the OpenCode chat (Layer 10 part 8, task 10.50).

This is a test helper, not shipped code. It answers one question: if somebody loosens the OpenCode gate, does a test
fail? Each fault is one or more text edits to umwayi's source. The helper

  1. copies the source tree to a throwaway folder (the real files are never edited),
  2. applies one fault to the copy,
  3. runs only the tests that should catch it, in the copy, with a time limit (a hang counts as caught),
  4. reports `caught` or `survived`.

A catch is checked once more: the failing tests are run again on an unmutated copy. A test that fails there too is
not evidence, and the fault is reported as `invalid`, not `caught`.

Run it (it is slow, minutes to an hour; it is not part of the test suite):

    python -m tests.agents.opencode_mutants --list
    python -m tests.agents.opencode_mutants --only A1 --only H1
    python -m tests.agents.opencode_mutants --jobs 4 --wide --markdown report.md

`--wide` runs every fault that survived its own tests against the whole OpenCode suite too, so a survivor is
reported as "survived everywhere" or "caught only by a test that was not on its list".

tests/agents/test_opencode_mutants.py keeps this table honest in the suite: every anchor still matches exactly the
number of times it says, every mutated file still compiles, every test target still exists, and the runner itself
is run on a small fault.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
AG = "umwayi/agents.py"
ACP = "umwayi/acp.py"
PLUGIN = "adapters/opencode/plugin/index.js"
SKIP_DIRS = {"node_modules", "__pycache__", ".mypy_cache", ".pytest_cache"}
DEFAULT_LIMIT = 300  # seconds for one fault; the longest targeted run on an unmutated tree is about 200 s

T = "tests.agents.test_agents_opencode_"
CONFIG = T + "config"
CHAT = T + "chat"
GATE = T + "gate"
TURNS = T + "turns"
PLUGIN_TESTS = "tests.adapters.test_opencode_plugin"
FAKE = "tests.agents.test_fake_opencode"
FAULTS_TESTS = T + "faults"  # the tests that task 10.50 added for survivors
GAPS = FAULTS_TESTS + ".GateGapTests"
WHOLE_SUITE = [CONFIG, CHAT, GATE, TURNS, T + "file", PLUGIN_TESTS, "tests.adapters.test_opencode_rules", FAKE,
               FAULTS_TESTS]


@dataclass(frozen=True)
class Edit:
    path: str
    old: str
    new: str
    count: int = 1  # how many times `old` must be in the file (after `after`); the edit replaces all of them
    after: str = ""  # a text that is in the file once: only what comes after it is looked at (the same line of code
    #                  is in the Kiro and Claude Code checks too)
    until: str = ""  # with `after`: the look ends where this text starts


@dataclass(frozen=True)
class Fault:
    id: str
    group: str
    title: str
    edits: tuple
    tests: tuple  # unittest names: a module, a class or a test
    limit: int = DEFAULT_LIMIT
    note: str = ""  # why it is expected to survive, for a fault that did survive earlier


def fault(id, group, title, edits, tests, **kw):
    edits = tuple(edits) if isinstance(edits, (list, tuple)) else (edits,)
    return Fault(id, group, title, edits, tuple(tests), **kw)


def py(old, new, count=1, after="", until=""):
    return Edit(AG, old, new, count, after, until)


# ----------------------------------------------------------------------------------------------- the fault table


def _planted():
    return [
        fault("A1", "planted", "the canary wait is skipped: no gate_ready is passed for OpenCode",
              py("self._gate_ready if claude else self._opencode_ready if opencode else None",
                 "self._gate_ready if claude else None"),
              [CHAT + ".CanaryTests", CHAT + ".StartTests"]),
        fault("A2", "planted", "OPENCODE_API_KEY is passed to the child",
              py("OPENCODE_ROUTES = {", 'OPENCODE_ENV_NAMES = OPENCODE_ENV_NAMES + ("OPENCODE_API_KEY",)\nOPENCODE_ROUTES = {'),
              [CONFIG + ".EnvAllowListTests", CONFIG + ".EnvInARealChildProcessTests", CHAT + ".StartTests"]),
        fault("A3", "planted", "the version is not compared",
              py("elif version < plat.min_version:", "elif False:", count=1, after="def _opencode_checks(", until="def gate_checks("), [GATE + ".VersionTests"]),
        fault("A4", "planted", "the ask rule is left out together with the evaluate hook",
              [py('"permissions": [{"action": "*", "resource": "*", "effect": "ask"}],', '"permissions": [],'),
               Edit(PLUGIN, 'await ctx.permission.hook("evaluate", (event) => {\n'
                            '      if (event && event.effect !== "ask" && event.effect !== "deny") event.effect = "ask"\n'
                            '    })', "")],
              [CONFIG + ".ExactBytesTests", CONFIG + ".WhatTheConfigHoldsTests", PLUGIN_TESTS + ".SetupTests",
               PLUGIN_TESTS + ".EvaluateTests"]),
        fault("A5", "planted", "the project-config check is skipped",
              py("other = _opencode_other_config(agent.workdir, home_text)", "other = None"),
              [GATE + ".ProjectConfigTests", GATE + ".OrderTests"]),
    ]


def _gate_checks():
    f = []
    version = [GATE + ".VersionTests"]
    # 1 command
    f += [
        fault("B1a", "gate", "command check removed: a missing opencode is not refused",
              py("if not found or not os.path.isabs(found):", "if False:", after="def _opencode_checks(", until="def gate_checks("), [GATE + ".CommandTests"]),
        fault("B1b", "gate", "command check loosened: a relative path from PATH is accepted",
              py("if not found or not os.path.isabs(found):", "if not found:", after="def _opencode_checks(", until="def gate_checks("), [GATE + ".CommandTests"]),
    ]
    # 2 version
    f += [
        fault("B2a", "gate", "version check loosened: only major and minor are compared",
              py("elif version < plat.min_version:", "elif version[:2] < plat.min_version[:2]:", after="def _opencode_checks(", until="def gate_checks("), version),
        fault("B2b", "gate", "version check loosened: the minimum is 2.2.2",
              py('(2, 2, 3), "--version"', '(2, 2, 2), "--version"'), version),
        fault("B2c", "gate", "version check removed: an exit code other than 0 is not refused as such",
              py('elif code != 0:\n        ok = done("version"', 'elif False:\n        ok = done("version"', after="def _opencode_checks(", until="def gate_checks("), version),
        fault("B2d", "gate", "version check removed: output with no version number is not refused as such",
              py('elif version is None:\n        ok = done("version"', 'elif False:\n        ok = done("version"',
                 after="def _opencode_checks(", until="def gate_checks("), version),
        fault("B2e", "gate", "version check removed: no answer in time is not refused as such",
              py('if code is None:\n        ok = done("version"', 'if False:\n        ok = done("version"', after="def _opencode_checks(", until="def gate_checks("), version),
        fault("B2f", "gate", "--version runs with umwayi's whole environment",
              py('env=opencode_env(os.environ, "{}"))', "env=dict(os.environ))"),
              [GATE + ".AllPassTests", GATE + ".VersionTests"]),
        fault("B2g", "gate", "the first failing check does not end the checks",
              py('    if not ok:\n        return gate\n\n    files_ok, detail', '    files_ok, detail'),
              [GATE + ".VersionTests", GATE + ".OrderTests"]),
    ]
    # 3 files
    files = [GATE + ".FilesTests"]
    f += [
        fault("B3a", "gate", "files check removed",
              py("files_ok, detail = _opencode_files(src)", 'files_ok, detail = True, "skipped"'), files),
        fault("B3b", "gate", "files check: a link is not refused as a link",
              py('if stat.S_ISLNK(st.st_mode):\n            return False, f"{path} is a link;',
                 'if False:\n            return False, f"{path} is a link;'), files,
              note="redundant: a link is not a regular file, so the next check refuses it (only the wording differs)"),
        fault("B3c", "gate", "files check: a file that is not a regular file is not refused",
              py('if not stat.S_ISREG(st.st_mode):\n            return False, f"{path} is missing or not a regular file"',
                 'if False:\n            return False, f"{path} is missing or not a regular file"'), files),
        fault("B3d", "gate", "files check: the real path is not compared (a link higher up)",
              py('if os.path.realpath(path) != os.path.join(real_base, *rel.split("/")):', "if False:"), files),
        fault("B3e", "gate", "files check: links are followed (lstat becomes stat)",
              py('st = os.lstat(path)\n        except OSError:\n            return False, f"{path} is missing or not a regular file"',
                 'st = os.stat(path)\n        except OSError:\n            return False, f"{path} is missing or not a regular file"'),
              files, note="redundant: the real-path check refuses a link whose target has another path"),
        fault("B3f", "gate", "files check: other files in the plugin folder are not refused",
              py("if others:\n        shown =", "if False:\n        shown ="), files),
        fault("B3g", "gate", "files check: a hidden file in the plugin folder is not counted",
              py('if n != "index.js")', 'if n != "index.js" and not n.startswith("."))'), files),
        fault("B3h", "gate", "files check: a plugin folder that cannot be listed is accepted",
              py('except OSError:\n        return False, f"{folder} cannot be listed"',
                 "except OSError:\n        others = []"), files + [GAPS]),
        fault("B3x", "gate", "files check: the three guards against a link (is a link, not regular, real path) are all removed",
              [py('if stat.S_ISLNK(st.st_mode):\n            return False, f"{path} is a link;',
                  'if False:\n            return False, f"{path} is a link;'),
               py('if not stat.S_ISREG(st.st_mode):\n            return False, f"{path} is missing or not a regular file"',
                  'if False:\n            return False, f"{path} is missing or not a regular file"'),
               py('if os.path.realpath(path) != os.path.join(real_base, *rel.split("/")):', "if False:")], files),
    ]
    # 4 managed config
    managed = [GATE + ".ManagedConfigTests"]
    f += [
        fault("B4a", "gate", "managed config check removed", py("managed = _opencode_managed()", "managed = None"),
              managed),
        fault("B4b", "gate", "managed config: only the first managed folder is looked at",
              py("for path in OPENCODE_MANAGED_DIRS:", "for path in OPENCODE_MANAGED_DIRS[:1]:"), managed + [GAPS]),
        fault("B4c", "gate", "managed config: the first managed folder is not looked at",
              py("for path in OPENCODE_MANAGED_DIRS:", "for path in OPENCODE_MANAGED_DIRS[1:]:"), managed + [GAPS]),
        fault("B4d", "gate", "managed config: the macOS plist is not looked for",
              py("if found is None:\n        candidates =", "if False:\n        candidates ="), managed),
        fault("B4e", "gate", "managed config: the plist at the top of the managed folder is not looked for",
              py("candidates = [os.path.join(OPENCODE_MANAGED_PLIST_ROOT, OPENCODE_MANAGED_PLIST)]", "candidates = []"),
              managed),
        fault("B4f", "gate", "managed config: the plist in a subfolder is not looked for",
              py("if entry.is_dir(follow_symlinks=False):", "if False:"), managed),
        fault("B4g", "gate", "managed config: a broken link in a managed folder is not seen (lexists becomes exists)",
              py("if os.path.lexists(path):\n            found = path", "if os.path.exists(path):\n            found = path"),
              managed),
        fault("B4h", "gate", "managed config: a broken link at the plist is not seen",
              py("if os.path.lexists(c)), None)", "if os.path.exists(c)), None)"), managed + [GAPS]),
    ]
    # 5 other config
    project = [GATE + ".ProjectConfigTests"]
    glob = [GATE + ".GlobalConfigTests"]
    f += [
        fault("B5a", "gate", "other config: folders above the workdir are not looked at",
              py("folder = parent\n    path = os.path.join(home, \".opencode\")",
                 "break\n    path = os.path.join(home, \".opencode\")"), project),
        fault("B5b", "gate", "other config: the real path of the workdir is not walked",
              py("for start in (workdir, os.path.realpath(workdir)):", "for start in (workdir,):"), project),
        fault("B5c", "gate", "other config: the path as given is not walked, only the real one",
              py("for start in (workdir, os.path.realpath(workdir)):", "for start in (os.path.realpath(workdir),):"),
              project + [GAPS]),
    ]
    for i, name in enumerate(("opencode.json", "opencode.jsonc", ".opencode")):
        f.append(fault(f"B5d{i + 1}", "gate", f"other config: {name} is not looked for in the workdir and above",
                       py("_OPENCODE_PROVIDER = re.compile(",
                          f'OPENCODE_PROJECT_NAMES = tuple(n for n in OPENCODE_PROJECT_NAMES if n != "{name}")\n'
                          "_OPENCODE_PROVIDER = re.compile("), project))
    f += [
        fault("B5e", "gate", "other config: .opencode in the home folder is not looked for",
              py('if os.path.lexists(path):\n        return f"{path} exists in the home folder"',
                 'if False:\n        return f"{path} exists in the home folder"'), project + glob),
        fault("B5f", "gate", "other config: XDG_CONFIG_HOME is ignored",
              py('folder = os.path.join(xdg if xdg and os.path.isabs(xdg) else os.path.join(home, ".config"), "opencode")',
                 'folder = os.path.join(home, ".config", "opencode")'), glob),
    ]
    for name in ("plugins", "plugin", "agents", "agent"):
        f.append(fault(f"B5g-{name}", "gate", f"other config: a global {name} entry is not looked for",
                       py("_OPENCODE_PROVIDER = re.compile(",
                          f'OPENCODE_GLOBAL_ENTRIES = tuple(n for n in OPENCODE_GLOBAL_ENTRIES if n != "{name}")\n'
                          "_OPENCODE_PROVIDER = re.compile("), glob))
    for name in ("opencode.json", "opencode.jsonc"):
        f.append(fault(f"B5h-{name}", "gate", f"other config: the global {name} is not read",
                       py("_OPENCODE_PROVIDER = re.compile(",
                          f'OPENCODE_GLOBAL_FILES = tuple(n for n in OPENCODE_GLOBAL_FILES if n != "{name}")\n'
                          "_OPENCODE_PROVIDER = re.compile("), glob))
    for key in ("permissions", "permission", "policies", "plugins", "plugin", "agents", "agent", "experimental",
                "enabled_providers", "disabled_providers"):
        f.append(fault(f"B5i-{key}", "gate", f'other config: the word "{key}" in the global file is not looked for',
                       py("_OPENCODE_PROVIDER = re.compile(",
                          f'OPENCODE_GLOBAL_KEYS = tuple(n for n in OPENCODE_GLOBAL_KEYS if n != "{key}")\n'
                          "_OPENCODE_PROVIDER = re.compile("), glob))
    f += [
        fault("B5j", "gate", "other config: a global file that is a link or not regular is accepted",
              py('if not stat.S_ISREG(st.st_mode):\n            return f"{path} is a link or not a regular file"',
                 'if False:\n            return f"{path} is a link or not a regular file"'), glob),
        fault("B5k", "gate", "other config: a global file that cannot be examined is skipped",
              py('except OSError:\n            return f"{path} cannot be read"', "except OSError:\n            continue"),
              glob + [GAPS]),
        fault("B5l", "gate", "other config: a global file over 1 MB is read",
              py("if st.st_size > OPENCODE_MAX_GLOBAL_CONFIG:", "if False:"), glob,
              note="redundant: the size is checked again after the read, which refuses the same file"),
        fault("B5m", "gate", "other config: the size is not checked again after the read",
              py('if len(text.encode("utf-8")) > OPENCODE_MAX_GLOBAL_CONFIG:', "if False:"), glob,
              note="redundant: the size is checked before the read, which refuses the same file; this one only matters "
                   "if the file grows between the two"),
        fault("B5lm", "gate", "other config: both size checks removed, a global file of any size is read",
              [py("if st.st_size > OPENCODE_MAX_GLOBAL_CONFIG:", "if False:"),
               py('if len(text.encode("utf-8")) > OPENCODE_MAX_GLOBAL_CONFIG:', "if False:")], glob),
        fault("B5n", "gate", "other config: a global file that is not UTF-8 text is skipped",
              py('except (OSError, UnicodeDecodeError):\n            return f"{path} cannot be read as UTF-8 text"',
                 "except (OSError, UnicodeDecodeError):\n            continue"), glob),
    ]
    # 6 route
    route = [GATE + ".RouteTests", CONFIG + ".RefusalTests"]
    f += [
        fault("B6a", "gate", "route check removed",
              py("integration, _ = opencode_route(agent.provider)", 'integration = "opencode"'), route),
        fault("B6b", "gate", "route check loosened: any provider is offered",
              py('raise OpenCodeRefused(f"agent: provider {shown} is not offered: " + OPENCODE_PAYG_TEXT)',
                 "return (provider, None)"), route),
        fault("B6c", "gate", "route check loosened: opencode-go is not set apart",
              py("if provider == OPENCODE_GO:\n        raise OpenCodeRefused(OPENCODE_GO_TEXT)",
                 "if False:\n        raise OpenCodeRefused(OPENCODE_GO_TEXT)"), route),
        fault("B6d", "gate", "route: openai uses the bare name (an environment key) instead of a sign-in",
              py('"openai": ("openai#*", None)', '"openai": ("openai", None)'), route),
        fault("B6e", "gate", "route: github-copilot uses the bare name instead of a sign-in",
              py('"github-copilot": ("github-copilot#*", None)', '"github-copilot": ("github-copilot", None)'), route),
        fault("B6f", "gate", "route: the free tier allows every integration",
              py('"opencode": ("opencode", None)', '"opencode": ("*", None)'), route),
        fault("B6g", "gate", "the gate checks are not run before a chat (a failed check is ignored)",
              py("        if not gate.gated:\n            why = self.log(f\"Refused agent {a.name}: not gated",
                 "        if False:\n            why = self.log(f\"Refused agent {a.name}: not gated"),
              [GATE + ".FilesTests", GATE + ".ProjectConfigTests", GATE + ".RouteTests"]),
        fault("B6h", "gate", "the model may belong to another provider than the agent's",
              py('or model.split("/", 1)[0] != provider:', "or False:"), [CONFIG + ".RefusalTests"]),
    ]
    return f


# every name the allow list leaves out (10.R13.4): each is added to the list, one fault each
EXCLUDED = [
    ("OPENCODE_API_KEY", "the OpenCode API key"), ("OPENCODE_CONFIG", "a config file path"),
    ("OPENCODE_CONFIG_DIR", "a config folder"), ("OPENCODE_DB", "a database path"),
    ("OPENCODE_PASSWORD", "a server password"), ("OPENCODE_DISABLE_PROJECT_CONFIG", "the project config switch"),
    ("OPENCODE_SOMETHING_NEW", "any other OPENCODE_ name"),
    ("ANTHROPIC_API_KEY", "an Anthropic key"), ("OPENAI_API_KEY", "an OpenAI key"),
    ("GITHUB_TOKEN", "a GitHub token"), ("AWS_ACCESS_KEY_ID", "an AWS key"),
    ("GOOGLE_APPLICATION_CREDENTIALS", "a Google credentials file"), ("AZURE_API_KEY", "an Azure key"),
    ("NODE_OPTIONS", "Node options"), ("NODE_PATH", "the Node module path"), ("BUN_INSTALL", "a Bun name"),
    ("CLAUDE_CONFIG_DIR", "the Claude Code config folder"), ("CLAUDE_AGENT_ACP_PROTOCOL", "the Claude ACP switch"),
    ("LD_PRELOAD", "a preload library"),
]


def _allow_list():
    env_tests = [CONFIG + ".EnvAllowListTests", CONFIG + ".EnvInARealChildProcessTests"]
    f = []
    for n, (name, what) in enumerate(EXCLUDED, 1):
        f.append(fault(f"C{n}", "allow list", f"exclusion removed: {name} ({what}) is passed to the child",
                       py("OPENCODE_ROUTES = {", f'OPENCODE_ENV_NAMES = OPENCODE_ENV_NAMES + ("{name}",)\n'
                                                  "OPENCODE_ROUTES = {"), env_tests))
    n = len(EXCLUDED)
    f += [
        fault(f"C{n + 1}", "allow list", "no allow list: the child gets umwayi's whole environment",
              py("env = {k: environ[k] for k in OPENCODE_ENV_NAMES if isinstance(environ.get(k), str)}",
                 "env = dict(environ)"), env_tests),
        fault(f"C{n + 2}", "allow list", "every OPENCODE_ name is passed",
              py("env = {k: environ[k] for k in OPENCODE_ENV_NAMES if isinstance(environ.get(k), str)}",
                 'env = {k: v for k, v in environ.items() if k in OPENCODE_ENV_NAMES or k.startswith("OPENCODE_")}'),
              env_tests),
        fault(f"C{n + 3}", "allow list", "a planted OPENCODE_CONFIG_CONTENT is kept instead of umwayi's",
              [py("OPENCODE_ROUTES = {", 'OPENCODE_ENV_NAMES = OPENCODE_ENV_NAMES + ("OPENCODE_CONFIG_CONTENT",)\n'
                                         "OPENCODE_ROUTES = {"),
               py("env[OPENCODE_CONFIG_VAR] = content", "env.setdefault(OPENCODE_CONFIG_VAR, content)")],
              env_tests + [CHAT + ".StartTests"]),
        fault(f"C{n + 4}", "allow list", "a value that is not text is passed",
              py("if isinstance(environ.get(k), str)}", "if k in environ}", after="def opencode_env("), env_tests),
        fault(f"C{n + 5}", "allow list", "a NUL character in the inline config is accepted",
              py('if not isinstance(content, str) or "\\x00" in content:', "if not isinstance(content, str):"),
              [CONFIG + ".EnvAllowListTests"]),
        fault(f"C{n + 6}", "allow list", "the chat start gives the child umwayi's whole environment",
              py("env = opencode_env(os.environ, self.opencode_config)  # the allow list",
                 "env = dict(os.environ, OPENCODE_CONFIG_CONTENT=self.opencode_config)  # the allow list"),
              [CHAT + ".StartTests"]),
    ]
    return f


CFG_PERM = '"permissions": [{"action": "*", "resource": "*", "effect": "ask"}],\n'
CFG_P1 = '            {"action": "provider.use", "resource": "*", "effect": "deny"},\n'
CFG_P2 = '            {"action": "provider.use", "resource": provider, "effect": "allow"},\n'
CFG_P3 = '            {"action": "integration.use", "resource": "*", "effect": "deny"},\n'
CFG_P4 = '            {"action": "integration.use", "resource": integration, "effect": "allow"},\n'


def _policy():
    cfg = [CONFIG + ".ExactBytesTests", CONFIG + ".WhatTheConfigHoldsTests", CONFIG + ".SameBytesTests"]
    perm = '        "permissions": [{"action": "*", "resource": "*", "effect": "ask"}],'

    def policy_block(*lines):
        return "".join(lines)

    f = [
        fault("D1", "policy", "the permissions statement (ask for everything) is removed",
              py(perm, '        "permissions": [],'), cfg),
        fault("D2", "policy", "the permissions statement allows everything",
              py(perm, perm.replace('"ask"', '"allow"')), cfg),
        fault("D3", "policy", "the permissions statement is for one action only",
              py(perm, perm.replace('"action": "*"', '"action": "tool.run"')), cfg),
        fault("D4", "policy", "policy 1 removed: providers are not denied by default",
              py(CFG_P1, ""), cfg),
        fault("D5", "policy", "policy 2 removed: the agent's provider is not allowed",
              py(CFG_P2, ""), cfg),
        fault("D6", "policy", "policy 3 removed: integrations are not denied by default",
              py(CFG_P3, ""), cfg),
        fault("D7", "policy", "policy 4 removed: the agent's integration is not allowed",
              py(CFG_P4, ""), cfg),
        fault("D8", "policy", "policies 1 and 2 swapped (allow before deny)",
              py(CFG_P1 + CFG_P2, CFG_P2 + CFG_P1), cfg),
        fault("D9", "policy", "policies 3 and 4 swapped (allow before deny)",
              py(CFG_P3 + CFG_P4, CFG_P4 + CFG_P3), cfg),
        fault("D10", "policy", "integration policies before provider policies",
              py(CFG_P1 + CFG_P2 + CFG_P3 + CFG_P4, CFG_P3 + CFG_P4 + CFG_P1 + CFG_P2), cfg),
        fault("D11", "policy", "the policy list reversed",
              py(CFG_P1 + CFG_P2 + CFG_P3 + CFG_P4, CFG_P4 + CFG_P3 + CFG_P2 + CFG_P1), cfg),
        fault("D12", "policy", "policy 1 allows instead of denies",
              py(CFG_P1, CFG_P1.replace('"deny"', '"allow"')), cfg),
        fault("D13", "policy", "policy 3 allows instead of denies",
              py(CFG_P3, CFG_P3.replace('"deny"', '"allow"')), cfg),
        fault("D14", "policy", "policy 2 allows every provider",
              py(CFG_P2, CFG_P2.replace("provider, ", '"*", ')), cfg),
        fault("D15", "policy", "policy 4 allows every integration",
              py(CFG_P4, CFG_P4.replace("integration, ", '"*", ')), cfg),
        fault("D16", "policy", "policy 4 allows the provider name instead of the integration",
              py(CFG_P4, CFG_P4.replace("integration, ", "provider, ")), cfg),
        fault("D17", "policy", "the model statement is removed", py('        "model": model,\n', ""), cfg),
        fault("D18", "policy", "the plugins statement (the umwayi plugin) is removed",
              py('        "plugins": [{"package": plugin, "options": {', '        "plugins_x": [{"package": plugin, "options": {'),
              cfg),
        fault("D19", "policy", "the plugin does not get the token option",
              py('            "token": token,\n', ""), cfg),
        fault("D20", "policy", "the hook runs without --platform opencode",
              py(', "--root", root_text, "--platform", "opencode"]', ', "--root", root_text]'), cfg),
        fault("D21", "policy", "the hook runs without --root",
              py('[python_text, hook, "--root", root_text, "--platform", "opencode"]',
                 '[python_text, hook, "--platform", "opencode"]'), cfg),
        fault("D22", "policy", "the local server settings are left out",
              py('config["providers"] = {provider: {"settings": {"baseURL": url}}}', "pass"), cfg),
        fault("D23", "policy", "a {env: or {file: text in a path is not refused",
              py("if _OPENCODE_SUBSTITUTION.search(text):", "if False:"), [CONFIG + ".RefusalTests"]),
        fault("D24", "policy", "a token that is not plain is accepted",
              py("if not (isinstance(token, str) and _OPENCODE_TOKEN.fullmatch(token)):", "if False:"),
              [CONFIG + ".RefusalTests"]),
        fault("D25", "policy", "a path that is not absolute is accepted",
              py('if not isinstance(text, str) or "\\x00" in text or not os.path.isabs(text):', "if False:"),
              [CONFIG + ".RefusalTests"]),
        fault("D26", "policy", "the sort order of the keys is dropped (same agent, other bytes)",
              py("json.dumps(config, sort_keys=True,", "json.dumps(config, sort_keys=False,"), [CONFIG + ".ExactBytesTests"]),
    ]
    return f


def _plugin():
    tests = [PLUGIN_TESTS + ".ToolGateTests", PLUGIN_TESTS + ".WhatReachesTheHookTests"]
    return [
        fault("E1", "plugin", "exit 3 (ask) is allowed for every tool, not only the nine that OpenCode asks about",
              Edit(PLUGIN, 'if (answer === "allow" || (answer === "ask" && ASKED.has(tool))) return',
                   'if (answer === "allow" || answer === "ask") return'), tests),
        fault("E2", "plugin", "the evaluate hook does nothing (an allow stays allow)",
              Edit(PLUGIN, 'event.effect = "ask"\n', "event.effect = event.effect\n"),
              [PLUGIN_TESTS + ".EvaluateTests"]),
        fault("E3", "plugin", "Code Mode (execute) joins the tools that ask",
              Edit(PLUGIN, 'new Set(["read",', 'new Set(["execute", "read",'), tests),
        fault("E4", "plugin", "the hook's exit code is not compared with its decision for allow",
              Edit(PLUGIN, 'if (r.status === 0 && decision === "allow") return "allow"',
                   'if (decision === "allow") return "allow"'), tests + [PLUGIN_TESTS + ".RealHookTests"]),
        fault("E5", "plugin", "the hook's exit code is not compared with its decision for ask",
              Edit(PLUGIN, 'return r.status === 3 && decision === "ask" ? "ask" : "deny"',
                   'return decision === "ask" ? "ask" : "deny"'), tests),
        fault("E6", "plugin", "a call with no tool name is not stopped",
              Edit(PLUGIN, 'if (typeof tool !== "string" || tool.length === 0) throw new Error(DENIED)', ""),
              tests),
        fault("E7", "plugin", "a hook that times out or fails to start is read as allow",
              Edit(PLUGIN, 'if (r.error || r.signal || typeof r.stdout !== "string") return "deny"',
                   'if (r.error || r.signal || typeof r.stdout !== "string") return "allow"'),
              [PLUGIN_TESTS + ".TimeoutTests", PLUGIN_TESTS + ".ToolGateTests"]),
        fault("E8", "plugin", "the tool hook is not registered",
              Edit(PLUGIN, 'await ctx.tool.hook("execute.before", (event) => {', 'await ctx.tool.hook("execute.after", (event) => {'),
              tests),
    ]


def _token():
    ready = [CHAT + ".CanaryTests"]
    return [
        fault("F1", "token", "the token is not compared: any non-empty canary file is accepted",
              py('return data == self.canary[1].encode("ascii")', "return len(data) > 0"), ready),
        fault("F2", "token", "the token is not compared: the file only has to be readable",
              py('return data == self.canary[1].encode("ascii")', "return True"), ready),
        fault("F3", "token", "the token is compared as a prefix: token plus more is accepted",
              py('return data == self.canary[1].encode("ascii")', 'return data.startswith(self.canary[1].encode("ascii"))'),
              ready),
        fault("F4", "token", "the canary read is 32 bytes: token plus more is cut to the token",
              py("OPENCODE_CANARY_READ = 129", "OPENCODE_CANARY_READ = 32"), ready),
        fault("F5", "token", "the canary may be a link",
              py("if not stat.S_ISREG(os.lstat(path).st_mode):\n                return False",
                 "if False:\n                return False"), ready),
        fault("F6", "token", "the token is the same at every start",
              py("token = secrets.token_hex(16)", 'token = "0" * 32'), [CHAT + ".StartTests"]),
    ]


def _always():
    t = [TURNS + ".AlwaysTests", TURNS + ".WholeTurnTests", "tests.agents.test_agents_acp"]
    loop = 'for kind in ((want, "reject_once") if want == "allow_once" else ("reject_once",)):'
    return [
        fault("G1", "always", "allow_always is the second choice after allow_once",
              Edit(ACP, loop, 'for kind in ((want, "allow_always", "reject_once") if want == "allow_once" else ("reject_once",)):'),
              t),
        fault("G2", "always", "allow_always is chosen before allow_once",
              Edit(ACP, loop, 'for kind in (("allow_always", want, "reject_once") if want == "allow_once" else ("reject_once",)):'),
              t),
        fault("G3", "always", "any option whose kind starts with allow is taken",
              Edit(ACP, 'o.get("kind") == kind and', 'str(o.get("kind", "")).startswith(kind.split("_")[0]) and'), t),
        fault("G4", "always", "the first option is taken whatever its kind",
              Edit(ACP, 'if isinstance(o, dict) and o.get("kind") == kind and isinstance(o.get("optionId"), str):',
                   'if isinstance(o, dict) and isinstance(o.get("optionId"), str):'), t),
        fault("G5", "always", "with no allow_once offered, the answer is not cancelled but the first option",
              Edit(ACP, 'return {"outcome": "cancelled"}\n\n\ndef read_lines',
                   'return {"outcome": "selected", "optionId": options[0]["optionId"]} if options else {"outcome": "cancelled"}\n\n\ndef read_lines'),
              t),
    ]


def _model():
    t = [CHAT + ".ModelTests"]
    return [
        fault("H1", "model", "the model compare is removed: any model that is a text is accepted",
              Edit(ACP, "current == self.expect_model)", "True)"), t),
        fault("H2", "model", "the model check is not called",
              Edit(ACP, "if self.expect_model is not None:  # before anything of the owner is sent",
                   "if False:  # before anything of the owner is sent"), t),
        fault("H3", "model", "the agent's model is not passed to the chat",
              py("expect_model=a.model if opencode else None", "expect_model=None"), t),
        fault("H4", "model", "the compare ignores case",
              Edit(ACP, "current == self.expect_model)", "current.lower() == self.expect_model.lower())"), t),
        fault("H5", "model", "a session that names no model is accepted",
              Edit(ACP, "if not (isinstance(current, str) and current == self.expect_model):",
                   "if current is not None and current != self.expect_model:"), t + [FAULTS_TESTS + ".NoModelTests"]),
        fault("H6", "model", "the compare ignores spaces around the model",
              Edit(ACP, "current == self.expect_model)", "current.strip() == self.expect_model)"), t),
    ]


def _second_gate():
    t = [TURNS]
    return [
        fault("I1", "second gate", "a request with no name may get Yes (the cap is removed)",
              py('if verdict == acp.ALLOW and self.agent.platform == "opencode" and not _has_tool_name(tool_call):',
                 "if False:"), [TURNS + ".NoNameTests"]),
        fault("I2", "second gate", "the kill switch does not turn a permission into No",
              py("stop = kill.reason(st) if kill.stopped(st) else None", "stop = None"), [TURNS + ".KillSwitchTests", FAULTS_TESTS + ".PermissionGuardTests"]),
        fault("I3", "second gate", "any answer but y is allowed (the owner's n is not a no)",
              Edit(ACP, 'outcome = select_outcome(options, "allow_once" if answer.strip() == "y" else "reject_once")',
                   'outcome = select_outcome(options, "reject_once" if answer.strip() == "n" else "allow_once")'),
              [TURNS + ".WholeTurnTests", TURNS + ".AlwaysTests"]),
        fault("I4", "second gate", "an error while asking the rules is an Ask me first, not a reject",
              py("except Exception:\n            return acp.REJECT\n        if not logged:",
                 "except Exception:\n            return acp.ASK\n        if not logged:"), t + [FAULTS_TESTS + ".PermissionGuardTests"]),
        fault("I5", "second gate", "an error in the permission callback is a Yes",
              Edit(ACP, "except Exception:\n                verdict = REJECT", "except Exception:\n                verdict = ALLOW"),
              ["tests.agents.test_agents_acp", TURNS, FAULTS_TESTS + ".CallbackCrashTests"]),
    ]


def _survivors():
    """The three that survived rounds 10.48 and 10.49. Task 10.50 tries to catch them with tests/agents/
    test_agents_opencode_faults.py; whatever still survives is documented in KNOWN-LIMITS."""
    return [
        fault("S1", "earlier survivor", "the private folder's mode is not checked",
              py("or stat.S_IMODE(st.st_mode) != 0o700 ", "or False "), [FAULTS_TESTS + ".FolderTests"],
              note="tempfile.mkdtemp always makes 0700"),
        fault("S2", "earlier survivor", "the last _track() before a clean exit is removed",
              py("if claude or opencode:\n            self._track()  # what it started, before its exit orphans it",
                 "if claude:\n            self._track()  # what it started, before its exit orphans it"),
              [FAULTS_TESTS + ".LastTrackTests"], note="the watcher has already tracked the children"),
        fault("S3", "earlier survivor", "a check that was not logged is not a reject",
              py("        if not logged:\n            return acp.REJECT\n", "        if False:\n            return acp.REJECT\n"),
              [FAULTS_TESTS + ".NotLoggedTests"], note="check_and_log already turns a Yes into Ask me first"),
    ]


def all_faults() -> list:
    out = (_planted() + _gate_checks() + _allow_list() + _policy() + _plugin() + _token() + _always() + _model()
           + _second_gate() + _survivors())
    ids = [f.id for f in out]
    assert len(ids) == len(set(ids)), "a fault id is used twice"
    return out


# ------------------------------------------------------------------------------------------------ applying a fault


def apply_edit(text: str, edit: Edit) -> str:
    head, tail, rest = "", text, ""
    if edit.after:
        if text.count(edit.after) != 1:
            raise ValueError(f"{edit.path}: the 'after' anchor is not there exactly once: {edit.after[:70]!r}")
        cut = text.index(edit.after)
        head, tail = text[:cut], text[cut:]
        if edit.until:
            end = tail.index(edit.until, 1)
            tail, rest = tail[:end], tail[end:]
    found = tail.count(edit.old)
    if found != edit.count:
        raise ValueError(f"{edit.path}: the anchor is there {found} time(s), not {edit.count}: {edit.old[:70]!r}")
    new = head + tail.replace(edit.old, edit.new) + rest
    if new == text:
        raise ValueError(f"{edit.path}: the edit changes nothing: {edit.old[:70]!r}")
    return new


def apply_fault(root: Path, f: Fault) -> None:
    """Apply `f` to the files under `root`, which must be a copy and never the real tree."""
    root = Path(root).resolve()
    if root == REPO:
        raise ValueError("a fault is never applied to the real source tree")
    texts = {}
    for e in f.edits:
        path = (root / e.path).resolve()
        if root not in path.parents:
            raise ValueError(f"{e.path} is outside the copy")
        texts[e.path] = apply_edit(texts.get(e.path) or path.read_text(encoding="utf-8"), e)
    for rel, text in texts.items():
        (root / rel).write_text(text, encoding="utf-8")


def check_syntax(root: Path, f: Fault) -> str | None:
    """None, or why a mutated file does not compile (such a fault would be 'caught' by an import error, which is no evidence)."""
    for rel in sorted({e.path for e in f.edits}):
        path = Path(root) / rel
        if rel.endswith(".py"):
            try:
                compile(path.read_text(encoding="utf-8"), rel, "exec")
            except SyntaxError as e:
                return f"{rel}: {e}"
        elif rel.endswith(".js"):
            tmp = path.with_suffix(".check.mjs")
            shutil.copy(path, tmp)
            try:
                r = subprocess.run(["node", "--check", str(tmp)], capture_output=True, text=True, timeout=30)
            finally:
                tmp.unlink()
            if r.returncode != 0:
                return f"{rel}: {r.stderr.strip()[:200]}"
    return None


COPIED = ("umwayi", "adapters", "tests", "rules.yaml")  # what the OpenCode tests read of the repository


def copy_tree(dest: Path) -> Path:
    """A copy of what the OpenCode tests need: the package, the adapters, the tests and the starter rules."""
    def ignore(_dir, names):
        return [n for n in names if n in SKIP_DIRS or n.endswith(".pyc")]

    dest.mkdir(parents=True)
    for name in COPIED:
        src = REPO / name
        if src.is_dir():
            shutil.copytree(src, dest / name, ignore=ignore, symlinks=True)
        else:
            shutil.copy2(src, dest / name)
    return dest


# ------------------------------------------------------------------------------------------------ running tests


def run_limited(argv: list, cwd: Path, limit: float, env: dict | None = None) -> tuple:
    """(returncode or None, output, hung). A run past `limit` seconds is killed with its process group: hung is True."""
    proc = subprocess.Popen(argv, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            start_new_session=True, env=env)
    try:
        out, _ = proc.communicate(timeout=limit)
        return proc.returncode, out, False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        out, _ = proc.communicate()
        return None, out or "", True


def unittest_argv(targets, failfast=True) -> list:
    return [sys.executable, "-m", "unittest"] + (["-f"] if failfast else []) + list(targets)


def child_env() -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "UMWAYI_FAULT")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


_FAILED = re.compile(r"^(?:FAIL|ERROR): (\S+) \(([^)]+)\)", re.M)


def failing_ids(output: str) -> list:
    """The ids of the tests that failed or errored, as `module.Class.test`. A module that did not import is shown as
    `unittest.loader._FailedTest`; it is returned with a marker so the caller can treat it as broken, not as a catch."""
    ids = []
    for name, where in _FAILED.findall(output):
        ids.append("!import:" + name if where.startswith("unittest.loader") else where)
    return ids


@dataclass
class Outcome:
    fault: Fault
    status: str  # caught, survived, invalid
    how: str = ""  # failed, hang, or why it is invalid
    failed: list = field(default_factory=list)
    seconds: float = 0.0
    wide: str = ""  # for a survivor with --wide: what the whole OpenCode suite said


def run_fault(f: Fault, wide: bool = False, work: Path | None = None) -> Outcome:
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="umwayi-mutant-", dir=work) as tmp:
        tree = copy_tree(Path(tmp) / "tree")
        try:
            apply_fault(tree, f)
        except ValueError as e:
            return Outcome(f, "invalid", f"the edit does not apply: {e}", seconds=time.monotonic() - start)
        bad = check_syntax(tree, f)
        if bad:
            return Outcome(f, "invalid", f"the mutated file does not compile: {bad}", seconds=time.monotonic() - start)
        code, out, hung = run_limited(unittest_argv(f.tests), tree, f.limit, child_env())
        if hung:
            return Outcome(f, "caught", "hang", seconds=time.monotonic() - start)
        if code == 0:
            outcome = Outcome(f, "survived", "", seconds=time.monotonic() - start)
            if wide:
                wcode, wout, whung = run_limited(unittest_argv(WHOLE_SUITE), tree, 900, child_env())
                if whung or wcode != 0:
                    outcome.wide = "caught by the whole OpenCode suite: " + ", ".join(failing_ids(wout)[:3] or ["hang"])
                else:
                    outcome.wide = "survived the whole OpenCode suite"
            return outcome
        ids = failing_ids(out)
        if not ids or any(i.startswith("!import:") for i in ids):
            return Outcome(f, "invalid", "a test target did not import or no failing test was named: " + out[-300:],
                           ids, time.monotonic() - start)
        # the same tests on an unmutated copy: a test that fails there is not evidence
        clean = copy_tree(Path(tmp) / "clean")
        code2, out2, hung2 = run_limited(unittest_argv(ids, failfast=False), clean, f.limit, child_env())
        if hung2 or code2 != 0:
            return Outcome(f, "invalid", "the failing test also fails on the unmutated tree: " + ", ".join(ids),
                           ids, time.monotonic() - start)
        return Outcome(f, "caught", "failed", ids, time.monotonic() - start)


def baseline(targets) -> tuple:
    """(ok, output): the targets pass on an unmutated copy."""
    with tempfile.TemporaryDirectory(prefix="umwayi-mutant-") as tmp:
        tree = copy_tree(Path(tmp) / "tree")
        code, out, hung = run_limited(unittest_argv(targets, failfast=False), tree, 900, child_env())
        return (code == 0 and not hung), out[-600:]


# ------------------------------------------------------------------------------------------------ report


def counts(outcomes) -> dict:
    c = {"planted": len(outcomes), "caught": 0, "survived": 0, "invalid": 0, "hang": 0}
    for o in outcomes:
        c[o.status] += 1
        if o.how == "hang":
            c["hang"] += 1
    return c


def markdown(outcomes) -> str:
    lines = ["| id | group | fault | result | by |", "|---|---|---|---|---|"]
    for o in outcomes:
        by = o.how if o.status != "caught" or o.how == "hang" else (o.failed[0].split(".", 3)[-1] if o.failed else "")
        if o.status == "survived":
            by = o.wide or o.fault.note
        if o.status == "invalid":
            by = o.how
        lines.append(f"| {o.fault.id} | {o.fault.group} | {o.fault.title} | {o.status} | {by} |")
    groups = {}
    for o in outcomes:
        g = groups.setdefault(o.fault.group, {"total": 0, "caught": 0, "survived": 0, "invalid": 0})
        g["total"] += 1
        g[o.status] += 1
    lines += ["", "| group | faults | caught | survived | invalid |", "|---|---|---|---|---|"]
    for name, g in groups.items():
        lines.append(f"| {name} | {g['total']} | {g['caught']} | {g['survived']} | {g['invalid']} |")
    c = counts(outcomes)
    lines += ["", f"Total: {c['planted']} faults, {c['caught']} caught ({c['hang']} by a hang), {c['survived']} survived, "
                  f"{c['invalid']} invalid."]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--list", action="store_true", help="list the faults and stop")
    ap.add_argument("--only", action="append", default=[], help="a fault id (repeat) or a group name")
    ap.add_argument("--jobs", type=int, default=2, help="faults run at the same time (default 2)")
    ap.add_argument("--wide", action="store_true", help="run each survivor against the whole OpenCode suite too")
    ap.add_argument("--baseline", action="store_true", help="first check that every target passes unmutated")
    ap.add_argument("--markdown", help="write the report to this file")
    ap.add_argument("--json", help="write the outcomes to this file")
    args = ap.parse_args(argv)
    faults = all_faults()
    if args.only:
        faults = [f for f in faults if f.id in args.only or f.group in args.only]
    if args.list:
        for f in faults:
            print(f"{f.id:10} {f.group:16} {f.title}")
        print(f"{len(faults)} faults")
        return 0
    if args.baseline:
        targets = sorted({t for f in faults for t in f.tests})
        ok, out = baseline(targets)
        print("baseline:", "ok" if ok else "FAILED\n" + out)
        if not ok:
            return 2
    outcomes = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = {pool.submit(run_fault, f, args.wide): f for f in faults}
        for fut in concurrent.futures.as_completed(futures):
            o = fut.result()
            outcomes.append(o)
            print(f"{o.fault.id:10} {o.status:9} {o.how[:60]:60} {o.seconds:6.1f}s  {o.fault.title}", flush=True)
    order = {f.id: i for i, f in enumerate(faults)}
    outcomes.sort(key=lambda o: order[o.fault.id])
    report = markdown(outcomes)
    print("\n" + report)
    if args.markdown:
        Path(args.markdown).write_text(report + "\n", encoding="utf-8")
    if args.json:
        Path(args.json).write_text(json.dumps([{"id": o.fault.id, "status": o.status, "how": o.how, "failed": o.failed,
                                                "seconds": round(o.seconds, 1), "wide": o.wide} for o in outcomes],
                                               indent=1) + "\n", encoding="utf-8")
    return 0 if all(o.status != "invalid" for o in outcomes) else 2


if __name__ == "__main__":
    sys.exit(main())
