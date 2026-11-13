"""Layer 10, parts 1 to 3: agents.yaml, the gate checks, the argument lists, and `agent run`.

    umwayi agent validate [--agents PATH]     every problem with a line number: 0 or 64
    umwayi agent list [--agents PATH]         the agents in the file: 0 or 64
    umwayi agent check NAME [--agents PATH]   can NAME be gated? 0 yes, 2 no, 64 usage
    umwayi agent run NAME (--prompt TEXT | --prompt-file PATH | -)
                                              start NAME once (Claude Code or Kiro): 0, 2, 3 or 64
    umwayi agent chat NAME [--agents PATH]    a chat on your terminal (transport cli), or umwayi's own
                                              ACP client for Kiro or Claude Code (transport acp): 0, 2, 3 or 64

`agent run` takes these steps in order and the first that fails ends it: read
agents.yaml and the prompt (64), the kill switch (3), the rules, action agent_run
(No 2, Ask me first 3 with one queue item), the run lock (3), every gate check
(2), the budget governor (units.yaml 64, its change entry 2, the limits 3, the
rules for budget_check, the telemetry receiver of a Claude Code start, the
reserve entry), the start entry, the start. While the agent runs, the kill
switch, the logbook and the per-run cap are checked every second and the
timeout is watched. After the agent is stopped, on every way out, the run is
settled with one `umwayi budget` entry (umwayi/budget.py, umwayi/telemetry.py). The agent is
stopped (SIGTERM to its process group, SIGKILL after 10 seconds) on every exit
path. Every start, end, stop and refusal is one logbook entry through the
checked append; the prompt and the conversation never are.

Before `agent run`, the gate checks run two short programs: the
agent's own version command (`claude -v`, `kiro-cli --version`) and the layer 9
hook script with a self-test event that every hook blocks before it reads a rule.
Both run with an argument list, never a shell, with a timeout and stdin given.

The argument lists the front door will use (parts 3 to 5) are built here, from the
fixed platform table and the validated fields only. Nothing from agents.yaml is
pasted into a string, and no list may hold a flag on FORBIDDEN_FLAGS.

Part 7a (10.R11): agents.yaml accepts claude-code with transport acp, and `agent check`
runs the gate checks of a Claude Code ACP chat (node, the pinned adapter in
adapters/claude_acp/, the bundled Claude Code version, sign-in by exit code, the hook),
each program with the allow-listed environment of child_env(). Part 7b: `agent chat`
starts [NODE, ADAPTER] with that environment, hands it the agent run hook and a
SessionStart canary in _meta of session/new, sends nothing of the owner before the canary
file exists, sets mode default, and stops its process group and every seen descendant.

The core knows where the layer 9 hook scripts and the adapter are, but never imports `adapters`.
See design.md (layer 10) and adapters/NOTES-layer10.md.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from umwayi import __version__, acp, budget, kill, logbook, miniyaml, rules, runlock, taskqueue, telemetry, units
from umwayi.errors import ConfigError, UmwayiError, UsageError

AGENTS_FILE = "agents.yaml"
MAX_FILE_BYTES = 64 * 1024
MAX_AGENTS = 50
MAX_PATH = 1024
MAX_PROMPT_BYTES = 100 * 1024
# W9.6: the three options of `agent run`. A model word and an effort level are the only new words an argument list may
# hold; both are checked here and again in _assert_allowed.
MODEL_RE = re.compile(r"[A-Za-z0-9._:/-]{1,64}")
CAP_RE = re.compile(r"[1-9][0-9]{0,8}")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
MAX_HOOK_FILE_BYTES = 256 * 1024
VERSION_TIMEOUT = 10.0  # seconds for `claude -v` or `kiro-cli --version`
SELFTEST_TIMEOUT = 5.0  # seconds for the hook self-test
MAX_VERSION_OUTPUT = 4096  # bytes of version output that are looked at
DEFAULT_TIMEOUT_MINUTES = 30
CLAUDE_HOOK_TIMEOUT = 30  # seconds, in the --settings JSON (longer than the hook's own 10 s wait)

# The self-test event. Both layer 9 hooks block every event other than PreToolUse with
# exit 2 before they read rules.yaml, so this proves Python and the hook start, and logs nothing.
SELFTEST_INPUT = json.dumps({"hook_event_name": "UmwayiSelfTest", "tool_name": "x", "tool_input": {}}).encode("utf-8")
SELFTEST_EXIT = 2


@dataclass(frozen=True)
class Platform:
    name: str
    commands: tuple  # the only words `command` may be
    transports: tuple
    hook: str  # the layer 9 hook, relative to the umwayi-os checkout
    min_version: tuple
    version_flag: str
    why_version: str


PLATFORMS = {
    "claude-code": Platform("claude-code", ("claude",), ("cli", "acp"), "adapters/claude_code/hook.py",
                            (2, 1, 295), "-v", "onFailure: block needs Claude Code 2.1.295 or later"),
    "kiro": Platform("kiro", ("kiro-cli",), ("cli", "acp"), "adapters/kiro/hook.py",
                     (2, 27, 1), "--version", "V3 headless runs load hooks from Kiro CLI 2.27.1"),
    # Part 8 (10.R13): OpenCode over ACP only. The "hook" is the layer 9 generic adapter, which the umwayi plugin
    # runs for every tool call (design.md part 8). 2.2.3 is the first release that honours every policy used.
    "opencode": Platform("opencode", ("opencode",), ("acp",), "adapters/stdio/hook.py",
                         (2, 2, 3), "--version", "integration.use, mcp.use and plugin.use need OpenCode 2.2.3 or later"),
}

# Part 7: Claude Code over ACP (10.R11). The adapter is a pinned npm package in adapters/claude_acp/,
# installed by the owner (`npm ci --ignore-scripts`); umwayi never runs npm. An ACP chat runs
# [NODE, ADAPTER]; `command: claude` stays for `agent run` and the cli chat.
CLAUDE_ACP_PACKAGE = "@agentclientprotocol/claude-agent-acp"
CLAUDE_ACP_VERSION = "0.101.0"  # also in adapters/claude_acp/package.json and its lockfile (a test checks)
NODE_MIN = (22, 0, 0)
CLAUDE_ACP_DIR = "adapters/claude_acp"
CLAUDE_ACP_PACKAGE_DIR = CLAUDE_ACP_DIR + "/node_modules/" + CLAUDE_ACP_PACKAGE
CLAUDE_ACP_ADAPTER = CLAUDE_ACP_PACKAGE_DIR + "/dist/index.js"
CLAUDE_ACP_CANARY = CLAUDE_ACP_DIR + "/canary.py"
NODE_COMMAND = "node"
SIGNIN_TIMEOUT = 15.0  # seconds for the login check (`auth status --json`)
SIGNIN_TEXT = ("Sign in to Claude Code with your Claude subscription first (claude, then /login, choose the Claude "
               "account), then try again.")
CLAUDE_ACP_MODE = "default"  # sent with session/set_mode once the canary is seen
CANARY_TIMEOUT = 10  # seconds, the SessionStart canary hook's timeout in the inline settings
CANARY_PREFIX = "umwayi-canary-"
OPENCODE_CANARY_NAME = "canary"  # the file the umwayi plugin writes in the private folder (10.R13.10)
OPENCODE_CANARY_READ = 129  # bytes read of that file: the token is 32 characters, one more is already too many
OPENCODE_SIGN_IN = "Run opencode auth login first, then try again."
CLAUDE_ACP_PROBES = {  # the self-test programs after `node --version`, each [NODE, ADAPTER, *tail]
    "adapter version": ("--version",),
    "claude code version": ("--cli", "--version"),
    "login": ("--cli", "auth", "status", "--json"),
}
_NODE_VERSION = re.compile(rb"v(\d{1,6})\.(\d{1,6})\.(\d{1,6})\s*")

# The child environment of every Claude Code ACP program (10.R11.9): only these names, each only if
# set, then CLAUDE_AGENT_ACP_PROTOCOL=v1. Everything else is dropped, among them ANTHROPIC_API_KEY,
# ANTHROPIC_AUTH_TOKEN, ANTHROPIC_BASE_URL, CLAUDE_CODE_EXECUTABLE, CLAUDE_AGENT_LOGS, IS_SANDBOX,
# NODE_OPTIONS, NODE_PATH and every npm_config_*.
CHILD_ENV_NAMES = ("HOME", "USER", "LOGNAME", "PATH", "SHELL", "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE",
                   "LC_MESSAGES", "TZ", "TMPDIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
                   "XDG_STATE_HOME", "XDG_RUNTIME_DIR", "CLAUDE_CONFIG_DIR",
                   "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy", "no_proxy",
                   "NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE", "SSL_CERT_DIR")
CHILD_ENV_SET = {"CLAUDE_AGENT_ACP_PROTOCOL": "v1"}

# Part 7c (10.R12.6): credentials that would make a Claude Code run or cli chat pay by something other than the
# owner's Claude subscription. Removed from umwayi's environment for `agent run` and the cli chat; values never read.
CLAUDE_CREDENTIAL_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_OAUTH_TOKEN",
                         "CLAUDE_CODE_OAUTH_REFRESH_TOKEN", "CLAUDE_CODE_OAUTH_SCOPES", "CLAUDE_CODE_USE_BEDROCK",
                         "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY", "ANTHROPIC_PROFILE",
                         "ANTHROPIC_FEDERATION_RULE_ID", "ANTHROPIC_ORGANIZATION_ID", "ANTHROPIC_IDENTITY_TOKEN_FILE")

# Part 7c (10.R12.3): the login check reads the exit code and these five fields of `auth status --json` and nothing else. The output
# also names the person (email, organisation); that is never read into anything.
LOGIN_FIELDS = ("loggedIn", "authMethod", "apiKeySource", "apiProvider", "subscriptionType")
MAX_LOGIN_OUTPUT = 64 * 1024  # bytes of `auth status --json` that are looked at
_PLAN = re.compile(r"^[a-z0-9 _-]{1,40}$")
_KEY_SOURCES = {"ANTHROPIC_API_KEY": "ANTHROPIC_API_KEY", "apiKeyHelper": "an apiKeyHelper",
                "env": "the environment"}
LOGIN_FIX_KEY = ("unset that variable in your shell, or remove apiKeyHelper or the env entry from your Claude Code "
                 "settings file, then try again. umwayi uses only your Claude subscription.")
LOGIN_FIX_CONSOLE = ("Console is API billing; sign in with your Claude account instead (claude, then /login, choose "
                     "the Claude account), then try again.")
LOGIN_FIX_PROVIDER = ("unset CLAUDE_CODE_USE_BEDROCK, CLAUDE_CODE_USE_VERTEX and CLAUDE_CODE_USE_FOUNDRY, and sign "
                      "out of any gateway, then try again. umwayi uses only your Claude subscription.")
LOGIN_UNCONFIRMED = "could not be confirmed (the login check gave no answer umwayi can read). " + SIGNIN_TEXT

# Part 7c-2 (10.R12.9): `umwayi agent login NAME`. The sign-in runs on the owner's terminal with no pipe to umwayi, so
# umwayi never sees its output, a URL, a code or a token; then the login check decides.
CLAUDE_LOGIN_TAIL = ("--cli", "auth", "login", "--claudeai")  # after [NODE, ADAPTER]; never another word
LOGIN_TIMEOUT = 600.0  # seconds: a fixed limit for one sign-in (timeout_minutes in agents.yaml is for agents)
# The names a browser sign-in needs, passed on top of child_env() and each only if set (design.md part 7c):
# the terminal, the browser opener (xdg-open and the desktop it hands over to) and the remote markers that switch
# the login to the manual URL and code. Never CLAUDE_CODE_OAUTH_REFRESH_TOKEN, CLAUDE_CODE_OAUTH_SCOPES or
# CLAUDE_CODE_REMOTE.
LOGIN_ENV_NAMES = ("TERM", "COLORTERM", "BROWSER", "DISPLAY", "WAYLAND_DISPLAY", "XDG_CURRENT_DESKTOP",
                   "XDG_DATA_DIRS", "DESKTOP_SESSION", "DBUS_SESSION_BUS_ADDRESS",
                   "SSH_TTY", "SSH_CONNECTION", "SSH_CLIENT", "NO_BROWSER")
# Never in any argument list (10.R12.9, 10.R12.13): another login method, a named account, a long-lived token,
# a sign-out, or a client that answers token requests. A word "WORD=..." counts too.
LOGIN_FORBIDDEN = ("--console", "--email", "--sso", "setup-token", "logout", "--license", "--identity-provider",
                   "--social", "--auth-method")
LOGIN_ONLY = ("agent login is only for platform claude-code with transport acp, or platform kiro. "
              "Nothing was started.")
LOGIN_ASK_RECOMMENDATION = ("Keep it stopped unless you want this agent signed in. To allow it, add a Yes rule for "
                            "agent_login to rules.yaml; answering this item does not start the login.")

# Part 7c-2 (10.R12.13): Kiro, subscription first as far as Kiro can be checked. Every Kiro login pays from the
# subscription's credits, but a key is a long-lived credential that may belong to another account: only the
# owner's own browser login is used. The value is never read.
KIRO_CREDENTIAL_ENV = ("KIRO_API_KEY",)
KIRO_SIGNIN_TEXT = "Sign in to Kiro first (kiro-cli login), then try again."

# The built-in Kiro tool IDs the Kiro hook docs name (adapters/NOTES.md). Nothing else may be trusted.
KIRO_TOOL_IDS = ("read_file", "grep_search", "execute_bash", "execute_pwsh",
                 "fs_write", "fs_append", "str_replace", "delete_file")

# Never in an argument list (requirements 10.R5.7). Checked on every list that is built.
FORBIDDEN_FLAGS = ("--bare", "--dangerously-skip-permissions", "--allow-dangerously-skip-permissions",
                   "--setting-sources", "--trust-all-tools", "--cloud", "--bg")
FORBIDDEN_TEXT = ("bypassPermissions",)

# Part 8: OpenCode over ACP (10.R13, tasks 10.43 and 10.44; design.md part 8, facts in NOTES-layer10.md, 10.42).
# umwayi never installs OpenCode and never runs npm or Bun. Everything below is a pure function of its arguments.
OPENCODE_PLUGIN_DIR = "adapters/opencode/plugin"  # the umwayi plugin, written in 10.45
OPENCODE_CONFIG_VAR = "OPENCODE_CONFIG_CONTENT"  # the one OPENCODE_ name the child gets, set by umwayi
# The child environment of every OpenCode program (10.R13.4): the names of 10.R11.9 without the two Claude Code
# ones (CLAUDE_CONFIG_DIR, CLAUDE_AGENT_ACP_PROTOCOL), each only if set. Nothing else is passed: no provider key,
# no cloud variable, no OPENCODE_ name (among them OPENCODE_API_KEY, OPENCODE_CONFIG, OPENCODE_CONFIG_DIR,
# OPENCODE_DB, OPENCODE_PASSWORD and OPENCODE_DISABLE_PROJECT_CONFIG), no NODE_OPTIONS, NODE_PATH or BUN_ name.
OPENCODE_ENV_NAMES = ("HOME", "USER", "LOGNAME", "PATH", "SHELL", "LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE",
                      "LC_MESSAGES", "TZ", "TMPDIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
                      "XDG_STATE_HOME", "XDG_RUNTIME_DIR",
                      "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy", "no_proxy",
                      "NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE", "SSL_CERT_DIR")
# The routes (10.R13.6): provider -> (the integration.use resource that is allowed, the default base URL of a local
# server or None). The signed-out free tier is the bare `opencode`, so a signed-in Console account (opencode#ACCOUNT)
# is not used; a subscription sign-in is the connected-account form `NAME#*`, never the bare name, which is an
# environment key. A local provider gets settings.baseURL and nothing else: a `models` entry under a built-in
# local provider breaks the route (10.42, provider.no-route).
OPENCODE_ROUTES = {
    "opencode": ("opencode", None),
    "ollama": ("ollama", "http://127.0.0.1:11434/v1"),
    "lmstudio": ("lmstudio", "http://127.0.0.1:1234/v1"),
    "vllm": ("vllm", "http://127.0.0.1:8000/v1"),
    "openai": ("openai#*", None),
    "github-copilot": ("github-copilot#*", None),
}
OPENCODE_GO = "opencode-go"  # refused (OC13): its billing could not be told apart from Console credits (10.42)
OPENCODE_GO_TEXT = ("agent: provider opencode-go (OpenCode Go) is not offered yet: 10.42 could not tell its billing "
                    "apart from Console credits (design.md, OC13). Nothing was started.")
OPENCODE_PAYG_TEXT = ("the free tier (opencode), a local server (ollama, lmstudio, vllm) and a subscription sign-in "
                      "(openai, github-copilot) are offered; pay as you go is not offered, it waits for the budget "
                      "governor. Nothing was started.")
# The gate checks (10.R13.8, task 10.46). The managed places are module constants so that a test can point them at
# folders of its own: the real ones (/etc/opencode, the macOS folders) are never read by a test.
OPENCODE_VERSION_TIMEOUT = 15.0  # seconds for `opencode --version`
OPENCODE_MANAGED_DIRS = ("/etc/opencode", "/Library/Application Support/opencode")
OPENCODE_MANAGED_PLIST_ROOT = "/Library/Managed Preferences"
OPENCODE_MANAGED_PLIST = "ai.opencode.managed.plist"
OPENCODE_PROJECT_NAMES = ("opencode.json", "opencode.jsonc", ".opencode")  # from the workdir up to /
OPENCODE_GLOBAL_FILES = ("opencode.json", "opencode.jsonc")  # in $XDG_CONFIG_HOME/opencode, else ~/.config/opencode
OPENCODE_GLOBAL_ENTRIES = ("plugins", "plugin", "agents", "agent")  # entries of that folder that add code or agents
OPENCODE_GLOBAL_KEYS = ("permissions", "permission", "policies", "plugins", "plugin", "agents", "agent", "experimental",
                        "enabled_providers", "disabled_providers")  # quoted words in those files that can widen the gate
OPENCODE_MAX_GLOBAL_CONFIG = 1024 * 1024  # a larger global config file is refused unread
OPENCODE_MAX_SHOWN_NAMES = 5  # names of other files in the plugin folder that a refusal shows
_OPENCODE_PROVIDER = re.compile(r"^[a-z0-9][a-z0-9._-]{0,39}$")
_OPENCODE_MODEL = re.compile(r"^[a-z0-9][a-z0-9._-]{0,39}/[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$")
_OPENCODE_TOKEN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
# OpenCode replaces {env:NAME} and {file:PATH} in the inline config before it reads it (NOTES, Nov 11).
_OPENCODE_SUBSTITUTION = re.compile(r"\{(?:env|file):", re.IGNORECASE)

KEYS = ("name", "platform", "command", "transport", "workdir", "kiro_agent", "trust_tools",
        "max_turns", "timeout_minutes", "provider", "model")
REQUIRED = ("name", "platform", "command", "workdir")
RUN, CHAT, LOGIN = "run", "chat", "login"  # LOGIN: `umwayi agent login NAME` (10.R12.9, part 7c-2)
CLI, ACP = "cli", "acp"

_NAME = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
_KIRO_AGENT = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_PLAIN_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,39}$")
_YAML_LINE = re.compile(r"^line (\d+): (.*)$")
_VERSION = re.compile(rb"(\d{1,6})\.(\d{1,6})\.(\d{1,6})")


@dataclass(frozen=True)
class Agent:
    name: str
    platform: str
    command: str
    transport: str
    workdir: str
    kiro_agent: str | None = None
    trust_tools: tuple = ()
    max_turns: int | None = None
    timeout_minutes: int = DEFAULT_TIMEOUT_MINUTES
    line: int = 0
    provider: str | None = None  # platform opencode only (10.R13.2)
    model: str | None = None  # platform opencode only: provider/model-id


@dataclass(frozen=True)
class Problem:
    line: int
    message: str

    def render(self) -> str:
        return f"line {self.line}: {self.message}"


@dataclass(frozen=True)
class Result:
    code: int
    lines: list


# ------------------------------------------------------------- part 1: the file


def check_name(name) -> str:
    if not isinstance(name, str) or not _NAME.match(name):
        raise UsageError("agent: the name must be a lowercase letter, then lowercase letters, digits and '-' (up to 32)")
    return name


def agents_path(root: Path, given: str | None) -> Path:
    return Path(given) if given else Path(root) / AGENTS_FILE


def read_file(path: Path) -> str:
    """The text of agents.yaml. Missing, a link, too big or not UTF-8: a config error (exit 64)."""
    shown = path.name
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        raise ConfigError(f"agent: {shown} was not found") from None
    except OSError:
        raise ConfigError(f"agent: {shown} cannot be read") from None
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise ConfigError(f"agent: {shown} must be a regular file, not a link or a folder")
    if st.st_size > MAX_FILE_BYTES:
        raise ConfigError(f"agent: {shown} is larger than {MAX_FILE_BYTES} bytes")
    try:
        data = path.read_bytes()
    except OSError:
        raise ConfigError(f"agent: {shown} cannot be read") from None
    if len(data) > MAX_FILE_BYTES:
        raise ConfigError(f"agent: {shown} is larger than {MAX_FILE_BYTES} bytes")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise ConfigError(f"agent: {shown} is not valid UTF-8") from None


def _line_map(text: str) -> dict:
    """Where the top key, each agent and each agent key is, as 1-based line numbers.

    Only called after miniyaml.loads has accepted the text, so the structure is regular.
    """
    toks = miniyaml._tokenize(text)
    found: dict = {}
    if not toks:
        return found
    top = toks[0][0]
    i = 0
    while i < len(toks):
        ind, t, n = toks[i]
        kv = miniyaml._split_key(t) if ind == top and not miniyaml._is_item(t) else None
        if kv is None:
            i += 1
            continue
        found[(kv[0],)] = n
        i += 1
        if kv[0] != "agents":
            continue
        idx, item_ind = 0, None
        while i < len(toks) and (toks[i][0] > top or (toks[i][0] == top and miniyaml._is_item(toks[i][1]))):
            jind, jt, jn = toks[i]
            if miniyaml._is_item(jt) and (item_ind is None or jind == item_ind):
                item_ind = jind
                idx += 1
                found[("agents", idx)] = jn
                rest = jt[1:].strip()
                kv2 = miniyaml._split_key(rest) if rest else None
                if kv2:
                    found[("agents", idx, kv2[0])] = jn
            elif idx:
                kv2 = miniyaml._split_key(jt)
                if kv2 and jind > item_ind:
                    found.setdefault(("agents", idx, kv2[0]), jn)
            i += 1
    return found


def _key_text(key) -> str:
    return f"'{key}'" if isinstance(key, str) and _PLAIN_KEY.match(key) else "a key"


def _whole(value, low: int, high: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def _real(path: str) -> str:
    return os.path.realpath(path)


def _inside(child: str, parent: str) -> bool:
    """True if child is parent or below it (both real paths)."""
    return child == parent or child.startswith(parent.rstrip("/") + "/")


def _workdir_problem(value, root_real: str) -> str | None:
    """None if workdir is acceptable, else what is wrong (never the value itself)."""
    if not isinstance(value, str) or not value:
        return "workdir must be an absolute path to a folder"
    if len(value) > MAX_PATH or not value.isprintable():
        return f"workdir must be a plain path of at most {MAX_PATH} characters"
    if not value.startswith("/"):
        return "workdir must be an absolute path (it starts with /)"
    if ".." in PurePosixPath(value).parts:
        return "workdir must not contain '..'"
    if not os.path.isdir(value):
        return "workdir must be an existing folder"
    real = _real(value)
    if _inside(real, root_real):
        return "workdir must not be the umwayi root or a folder inside it"
    if _inside(root_real, real):
        return "workdir must not contain the umwayi root"
    return None


def check_text(text: str, root: Path) -> tuple:
    """(list of Agent or None, problems). Every problem has a line number, never the text of a line."""
    try:
        data = miniyaml.loads(text)
    except miniyaml.YamlError as e:
        m = _YAML_LINE.match(str(e))
        return None, [Problem(int(m.group(1)), m.group(2)) if m else Problem(1, "the file cannot be read as YAML")]
    where = _line_map(text)
    root_real = _real(str(root))

    def line(*path) -> int:
        for k in range(len(path), 0, -1):
            if path[:k] in where:
                return where[path[:k]]
        return 1

    problems: list = []

    def problem(message: str, *path) -> None:
        problems.append(Problem(line(*path), message))

    if not isinstance(data, dict):
        return None, [Problem(1, "the file must be a mapping with one key, agents")]
    for key in data:
        if key != "agents":
            problem(f"{_key_text(key)} is not allowed at the top, only agents", key)
    items = data.get("agents")
    if "agents" not in data:
        problem("the file needs a list of agents")
        items = []
    elif not isinstance(items, list) or not items:
        problem("agents must be a list with at least one agent", "agents")
        items = []
    elif len(items) > MAX_AGENTS:
        problem(f"the file has at most {MAX_AGENTS} agents", "agents")

    parsed: list = []
    names: set = set()
    for i, item in enumerate(items, 1):
        label = f"agent {i}"
        if not isinstance(item, dict):
            problem(f"{label} must be a mapping with name, platform, command and workdir", "agents", i)
            continue
        before = len(problems)
        for key in item:
            if key not in KEYS:
                problem(f"{label}: {_key_text(key)} is not allowed", "agents", i, key)
        for key in REQUIRED:
            if key not in item:
                problem(f"{label} needs {key}", "agents", i)
        name = item.get("name")
        if "name" in item:
            if not isinstance(name, str) or not _NAME.match(name):
                problem(f"{label}: name must be a lowercase letter, then lowercase letters, digits and '-' (up to 32)",
                        "agents", i, "name")
            elif name in names:
                problem(f"{label}: the name is used twice", "agents", i, "name")
            else:
                names.add(name)
        pname = item.get("platform")
        plat = PLATFORMS.get(pname) if isinstance(pname, str) else None
        if "platform" in item and plat is None:
            problem(f"{label}: platform must be one of: {', '.join(PLATFORMS)}", "agents", i, "platform")
        cmd = item.get("command")
        if "command" in item and plat is not None and not (isinstance(cmd, str) and cmd in plat.commands):
            problem(f"{label}: command must be one word from the allow list for {plat.name}: "
                    f"{', '.join(plat.commands)} (no path, no arguments)", "agents", i, "command")
        # a platform with one possible transport (OpenCode: acp) does not need it written (OC17)
        transport = item.get("transport", plat.transports[0] if plat is not None and len(plat.transports) == 1 else CLI)
        if "transport" in item and transport not in (CLI, ACP):
            problem(f"{label}: transport must be cli or acp", "agents", i, "transport")
        elif plat is not None and transport not in plat.transports:
            problem(f"{label}: transport {transport} is not possible for {plat.name} "
                    f"(only {', '.join(plat.transports)})", "agents", i, "transport")
        if "workdir" in item:
            wrong = _workdir_problem(item["workdir"], root_real)
            if wrong:
                problem(f"{label}: {wrong}", "agents", i, "workdir")
        kiro_agent = item.get("kiro_agent")
        if "kiro_agent" in item:
            if pname != "kiro":
                problem(f"{label}: kiro_agent is only for platform kiro", "agents", i, "kiro_agent")
            elif transport == ACP:
                problem(f"{label}: kiro_agent cannot be used with transport acp", "agents", i, "kiro_agent")
            elif not isinstance(kiro_agent, str) or not _KIRO_AGENT.match(kiro_agent):
                problem(f"{label}: kiro_agent must be 1 to 64 letters, digits, '_' or '-'", "agents", i, "kiro_agent")
        tools = item.get("trust_tools", [])
        if "trust_tools" in item:
            if pname != "kiro":
                problem(f"{label}: trust_tools is only for platform kiro", "agents", i, "trust_tools")
            elif not isinstance(tools, list):
                problem(f"{label}: trust_tools must be a list of Kiro tool IDs", "agents", i, "trust_tools")
            else:
                bad = [t for t in tools if not (isinstance(t, str) and t in KIRO_TOOL_IDS)]
                if bad:
                    problem(f"{label}: trust_tools may only hold these tool IDs: {', '.join(KIRO_TOOL_IDS)}",
                            "agents", i, "trust_tools")
                elif len(set(tools)) != len(tools):
                    problem(f"{label}: trust_tools names a tool twice", "agents", i, "trust_tools")
        max_turns = item.get("max_turns")
        if "max_turns" in item:
            if pname != "claude-code":
                problem(f"{label}: max_turns is only for platform claude-code", "agents", i, "max_turns")
            elif not _whole(max_turns, 1, 200):
                problem(f"{label}: max_turns must be a whole number from 1 to 200", "agents", i, "max_turns")
        timeout = item.get("timeout_minutes", DEFAULT_TIMEOUT_MINUTES)
        if "timeout_minutes" in item and not _whole(timeout, 1, 720):
            problem(f"{label}: timeout_minutes must be a whole number from 1 to 720", "agents", i, "timeout_minutes")
        provider, model = item.get("provider"), item.get("model")
        for key in ("provider", "model"):
            if pname == "opencode" and key not in item:
                problem(f"{label} needs {key}", "agents", i)
            elif pname != "opencode" and key in item:
                problem(f"{label}: {key} is only for platform opencode", "agents", i, key)
        if pname == "opencode":
            # the shape only (OC16): whether a route is offered is decided at the start, with exit 2
            provider_ok = isinstance(provider, str) and _OPENCODE_PROVIDER.fullmatch(provider) is not None
            if "provider" in item and not provider_ok:
                problem(f"{label}: provider must be 1 to 40 lowercase letters, digits, '.', '_' or '-', "
                        "starting with a letter or a digit", "agents", i, "provider")
            if "model" in item:
                if not (isinstance(model, str) and _OPENCODE_MODEL.fullmatch(model)):
                    problem(f"{label}: model must be provider/model-id, for example ollama/qwen3-coder "
                            "(the provider part in lowercase)", "agents", i, "model")
                elif provider_ok and model.split("/", 1)[0] != provider:
                    problem(f"{label}: model must start with the same provider as provider, followed by '/'",
                            "agents", i, "model")
        if len(problems) == before:
            parsed.append(Agent(name, pname, cmd, transport, item["workdir"], kiro_agent,
                                tuple(tools) if isinstance(tools, list) else (), max_turns, timeout, line("agents", i),
                                provider if pname == "opencode" else None, model if pname == "opencode" else None))
    if problems:
        return None, sorted(problems, key=lambda p: p.line)
    return parsed, []


def _root(root) -> Path:
    r = Path(root)
    if not r.is_dir():
        raise UsageError("agent: the umwayi root (--root) must be an existing folder")
    return r.resolve()


def load(root, given: str | None = None) -> list:
    """Every agent, or a config error (exit 64) that says how many problems the file has."""
    root = _root(root)
    path = agents_path(root, given)
    agents, problems = check_text(read_file(path), root)
    if problems:
        raise ConfigError(f"agent: {path.name} has {len(problems)} problem(s), see 'umwayi agent validate'. "
                          "Nothing was started.")
    return agents


def find(agents: list, name: str) -> Agent:
    check_name(name)
    for a in agents:
        if a.name == name:
            return a
    raise UsageError(f"agent: there is no agent named {name} in the agents file")


def validate_file(root, given: str | None = None) -> Result:
    """`umwayi agent validate`. Reads only. 0 when valid, 64 with every problem otherwise."""
    root = _root(root)
    path = agents_path(root, given)
    agents, problems = check_text(read_file(path), root)
    if problems:
        return Result(64, [f"problem: {p.render()}" for p in problems]
                      + [f"{len(problems)} problem(s) found in {path.name}"])
    names = ", ".join(f"{a.name} ({a.platform}, {a.transport})" for a in agents)
    return Result(0, [f"ok: {len(agents)} agent(s): {names}"])


def list_agents(root, given: str | None = None) -> Result:
    """`umwayi agent list`. Reads only and starts nothing."""
    agents = load(root, given)
    lines = [f"{a.name}  {a.platform}  {a.transport}  {a.command}  {a.workdir}" for a in agents]
    return Result(0, lines + [f"{len(agents)} agent(s). Nothing was started."])


# --------------------------------------------- part 2: argument lists (10.R5)


def umwayi_src() -> Path:
    """The umwayi-os checkout this package is in. The layer 9 hooks are found from here."""
    return Path(__file__).resolve().parents[1]


def hook_path(platform: str, src: Path | None = None) -> Path:
    return (src or umwayi_src()) / PLATFORMS[platform].hook


def claude_acp_path(relative: str, src: Path | None = None) -> Path:
    """A fixed path in adapters/claude_acp/ (the adapter, its package.json, the canary)."""
    return (src or umwayi_src()) / relative


def is_claude_acp(agent: Agent, mode: str | None) -> bool:
    """A Claude Code ACP chat: node and the pinned adapter, not `claude`. `agent run` stays `claude -p`."""
    return agent.platform == "claude-code" and agent.transport == ACP and mode != RUN


def child_env(environ) -> dict:
    """The allow-listed environment for every Claude Code ACP program (10.R11.9). Nothing else is passed."""
    env = {k: environ[k] for k in CHILD_ENV_NAMES if isinstance(environ.get(k), str)}
    env.update(CHILD_ENV_SET)
    return env


def claude_acp_session_meta(python: str, root: Path, folder: str, token: str, src: Path | None = None) -> dict:
    """The _meta of session/new for a Claude Code ACP chat (design.md part 7, 10.R11.4).

    The PreToolUse entry is the one `agent run` passes with --settings (the same claude_settings());
    the SessionStart canary writes FOLDER/TOKEN when command hooks from these settings run.
    """
    settings = json.loads(claude_settings(python, hook_path("claude-code", src), Path(root)))
    settings["hooks"]["SessionStart"] = [{"hooks": [{
        "type": "command", "command": python,
        "args": [str(claude_acp_path(CLAUDE_ACP_CANARY, src)), "--dir", folder, "--token", token],
        "timeout": CANARY_TIMEOUT,
    }]}]
    meta = {"claudeCode": {"options": {"allowDangerouslySkipPermissions": False, "settings": settings}}}
    text = json.dumps(meta)
    if any(t in text for t in FORBIDDEN_TEXT) or any(f in text for f in FORBIDDEN_FLAGS):
        raise RuntimeError("agent: the session settings held a forbidden word; nothing was started")
    return meta


def _canary_folder() -> str:
    """A private folder for one start's canary (mode 0700, made by tempfile). The only folder agents.py makes."""
    return tempfile.mkdtemp(prefix=CANARY_PREFIX)


def _remove_canary_folder(folder: str) -> None:
    """The canary folder goes on every way out. The only thing agents.py removes."""
    shutil.rmtree(folder, ignore_errors=True)


def login_env(environ) -> dict:
    """The environment of the claude.ai sign-in (10.R12.9): child_env() plus LOGIN_ENV_NAMES, each only if set."""
    env = child_env(environ)
    env.update({k: environ[k] for k in LOGIN_ENV_NAMES if isinstance(environ.get(k), str)})
    return env


def kiro_env(environ) -> dict:
    """umwayi's environment minus KIRO_API_KEY (10.R12.13), for every Kiro start, `whoami` and `login`."""
    return {k: v for k, v in environ.items() if k not in KIRO_CREDENTIAL_ENV}


def can_login(agent: Agent) -> bool:
    """`umwayi agent login` is for a Claude Code agent with transport acp, or any Kiro agent."""
    return (agent.platform == "claude-code" and agent.transport == ACP) or agent.platform == "kiro"


def claude_env(environ) -> dict:
    """umwayi's environment minus the credential names of 10.R12.6, for `agent run` and the cli chat of Claude Code.

    Every OTEL_* name, BETA_TRACING_ENDPOINT, CLAUDE_CODE_ENHANCED_TELEMETRY_BETA and CLAUDE_CODE_ENABLE_TELEMETRY
    are removed too (B.R2.2), so no export goes elsewhere; a start then adds telemetry.telemetry_env() for its own
    receiver.
    """
    return {k: v for k, v in environ.items() if k not in CLAUDE_CREDENTIAL_ENV and not telemetry.removed(k)}


class OpenCodeRefused(RuntimeError):
    """An OpenCode environment or config cannot be made safely (10.R13.5, 10.R13.6). The text is fixed words plus,
    at most, a provider name that matched the plain pattern; it never holds a path, a token or file content. A
    start turns it into a refusal (exit 2) with nothing started; an unexpected error exits 2 as well."""


def _refuse(why: str):
    raise OpenCodeRefused(f"agent: {why} Nothing was started.")


def opencode_route(provider) -> tuple:
    """(the integration.use resource that is allowed, the default base URL or None) for an offered provider (10.R13.6).

    Pure. Console credits, provider API keys and every other provider are refused: pay as you go is not offered,
    and OpenCode Go waits for a sign-in that shows its billing (OC13).
    """
    if isinstance(provider, str) and provider in OPENCODE_ROUTES:
        return OPENCODE_ROUTES[provider]
    if provider == OPENCODE_GO:
        raise OpenCodeRefused(OPENCODE_GO_TEXT)
    shown = provider if isinstance(provider, str) and _OPENCODE_PROVIDER.fullmatch(provider) else "that provider"
    raise OpenCodeRefused(f"agent: provider {shown} is not offered: " + OPENCODE_PAYG_TEXT)


def opencode_env(environ, content) -> dict:
    """The allow-listed environment of every OpenCode program (10.R13.4), with the inline config as the one
    OPENCODE_ variable. `environ` is not changed. A planted OPENCODE_CONFIG_CONTENT is replaced, never passed on."""
    if not isinstance(content, str) or "\x00" in content:
        _refuse("the OpenCode inline config must be text without a NUL character.")
    env = {k: environ[k] for k in OPENCODE_ENV_NAMES if isinstance(environ.get(k), str)}
    env[OPENCODE_CONFIG_VAR] = content
    return env


def _opencode_path(label: str, value) -> str:
    text = os.fspath(value) if isinstance(value, (str, os.PathLike)) else None
    if not isinstance(text, str) or "\x00" in text or not os.path.isabs(text):
        _refuse(f"the {label} path for the OpenCode config must be an absolute path (not empty, no NUL character).")
    return text


def opencode_inline_config(agent: Agent, root, token, folder, python, src=None) -> str:
    """The one JSON document umwayi passes in OPENCODE_CONFIG_CONTENT (10.R13.5, design.md "The inline config").

    Pure: the same agent, token and paths give the same bytes (sorted keys, compact, ASCII only), and nothing is
    read, checked or written. It holds `permissions` (ask for everything), `policies` (every provider and
    integration denied, then the agent's route allowed), `model`, `plugins` (the umwayi plugin with its three
    options) and, for a local route, `providers` with settings.baseURL only. Refuses (OpenCodeRefused) an agent that
    is not an OpenCode agent, a route that is not offered, a path that is not absolute, a token that is not plain,
    and any value that would hold {env: or {file:, because OpenCode would replace it.
    """
    if getattr(agent, "platform", None) != "opencode":
        _refuse("the OpenCode config is made only for an agent with platform opencode.")
    provider, model = agent.provider, agent.model
    if not (isinstance(provider, str) and _OPENCODE_PROVIDER.fullmatch(provider)):
        _refuse("the OpenCode agent has no valid provider.")
    if not (isinstance(model, str) and _OPENCODE_MODEL.fullmatch(model)) or model.split("/", 1)[0] != provider:
        _refuse("the OpenCode agent's model is missing, malformed or of another provider.")
    integration, url = opencode_route(provider)
    if not (isinstance(token, str) and _OPENCODE_TOKEN.fullmatch(token)):
        _refuse("the canary token must be 16 to 128 letters, digits, '_' or '-'.")
    root_text = _opencode_path("root", root)
    folder_text = _opencode_path("canary folder", folder)
    python_text = _opencode_path("Python", python)
    src_text = _opencode_path("umwayi source", src if src is not None else umwayi_src())
    hook = str(hook_path("opencode", Path(src_text)))
    plugin = str(Path(src_text) / OPENCODE_PLUGIN_DIR)
    config = {
        "permissions": [{"action": "*", "resource": "*", "effect": "ask"}],
        "policies": [
            {"action": "provider.use", "resource": "*", "effect": "deny"},
            {"action": "provider.use", "resource": provider, "effect": "allow"},
            {"action": "integration.use", "resource": "*", "effect": "deny"},
            {"action": "integration.use", "resource": integration, "effect": "allow"},
        ],
        "model": model,
        "plugins": [{"package": plugin, "options": {
            "hook": [python_text, hook, "--root", root_text, "--platform", "opencode"],
            "canary": os.path.join(folder_text, "canary"),
            "token": token,
        }}],
    }
    if url is not None:
        config["providers"] = {provider: {"settings": {"baseURL": url}}}
    text = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    if _OPENCODE_SUBSTITUTION.search(text):
        _refuse("the OpenCode config would hold '{env:' or '{file:' text, which OpenCode replaces with a variable or a "
                "file; use a path without it for umwayi, its root and the temporary folder.")
    return text


def login_check(code, out: bytes) -> tuple:
    """(passed, detail, plan word or None) for `auth status --json` (10.R12.3, design part 7c). Pure.

    Only the five named keys of LOGIN_FIELDS are taken from the JSON; the dict is dropped on return and no other
    field is ever read. Every detail is fixed text plus, at most, a value from a fixed set.
    """
    if code is None:
        return False, "could not be confirmed (no answer within 15 s). " + SIGNIN_TEXT, None
    if not isinstance(out, bytes) or len(out) > MAX_LOGIN_OUTPUT:
        return False, LOGIN_UNCONFIRMED, None
    try:
        data = json.loads(out.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return False, LOGIN_UNCONFIRMED, None
    if not isinstance(data, dict):
        return False, LOGIN_UNCONFIRMED, None
    f = {k: data[k] for k in LOGIN_FIELDS if k in data}
    del data
    logged_in, method = f.get("loggedIn"), f.get("authMethod")
    if code != 0:
        if logged_in is False or method == "none":
            return False, "not signed in. " + SIGNIN_TEXT, None
        return False, LOGIN_UNCONFIRMED, None
    if logged_in is not True:
        return False, ("not signed in. " + SIGNIN_TEXT) if logged_in is False else LOGIN_UNCONFIRMED, None
    if method != "claude.ai":
        if method == "api_key":
            return False, "an API key pays, not your Claude subscription; " + LOGIN_FIX_KEY, None
        if method == "api_key_helper":
            return False, "an apiKeyHelper in a settings file pays, not your Claude subscription; " + LOGIN_FIX_KEY, None
        if method == "oauth_token":
            return False, ("CLAUDE_CODE_OAUTH_TOKEN pays (a long-lived token from claude setup-token), which umwayi "
                           "does not use; " + LOGIN_FIX_KEY), None
        if method == "third_party":
            return False, "a cloud provider or gateway pays, not your Claude subscription; " + LOGIN_FIX_PROVIDER, None
        if method == "none":
            return False, "not signed in. " + SIGNIN_TEXT, None
        return False, LOGIN_UNCONFIRMED, None
    if "apiKeySource" in f:
        source = f["apiKeySource"]
        if source == "/login managed key":
            return False, "an API key from a Console login pays, not your Claude subscription. " + LOGIN_FIX_CONSOLE, None
        if isinstance(source, str) and source in _KEY_SOURCES:
            return False, (f"an API key from {_KEY_SOURCES[source]} pays, not your Claude subscription; "
                           + LOGIN_FIX_KEY), None
        if isinstance(source, str):
            return False, "an API key pays, not your Claude subscription; " + LOGIN_FIX_KEY, None
        return False, LOGIN_UNCONFIRMED, None
    if "apiProvider" in f and f["apiProvider"] != "firstParty":
        if isinstance(f["apiProvider"], str):
            return False, "a cloud provider or gateway pays, not your Claude subscription; " + LOGIN_FIX_PROVIDER, None
        return False, LOGIN_UNCONFIRMED, None
    plan = f.get("subscriptionType")
    if not (isinstance(plan, str) and _PLAN.match(plan)):
        return False, "no Claude subscription was reported. " + SIGNIN_TEXT, None
    return True, f"Claude subscription (plan: {plan})", plan


def probe_argv(node: str, adapter: Path, name: str) -> list:
    """The argument list of one self-test program of a Claude Code ACP chat (design.md, part 7)."""
    if name == "node version":
        return _assert_allowed([node, "--version"])
    return _assert_allowed([node, str(adapter), *CLAUDE_ACP_PROBES[name]])


def claude_settings(python: str, hook: Path, root: Path) -> str:
    """The --settings JSON for Claude Code, from a fixed template (design.md, layer 10)."""
    settings = {
        "disableAllHooks": False,
        "forceLoginMethod": "claudeai",  # 10.R12.7: a second line; the login check is the first
        "hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{
            "type": "command", "command": python, "args": [str(hook), "--root", str(root)],
            "timeout": CLAUDE_HOOK_TIMEOUT, "onFailure": "block",
        }]}]},
    }
    return json.dumps(settings, separators=(",", ":"))


@dataclass(frozen=True)
class RunOptions:
    """--cap-uu, --model and --effort of `agent run` (W9.6). All None: the run is exactly what it was before."""
    cap_uu: int | None = None
    model: str | None = None
    effort: str | None = None

    @property
    def used(self) -> bool:
        return self.cap_uu is not None or self.model is not None or self.effort is not None

    def text(self) -> str:
        parts = [f"cap {self.cap_uu} UU" if self.cap_uu is not None else None,
                 f"model {self.model}" if self.model is not None else None,
                 f"effort {self.effort}" if self.effort is not None else None]
        return ", ".join(p for p in parts if p)


def check_model(model) -> str:
    if not isinstance(model, str) or not MODEL_RE.fullmatch(model) or model.startswith("-") \
            or any(t in model for t in FORBIDDEN_TEXT):
        raise UsageError("agent: --model must be 1 to 64 characters from letters, digits and . _ : / - "
                         "and must not start with '-'. Nothing was started.")
    return model


def check_effort(effort) -> str:
    if effort not in EFFORTS:
        raise UsageError("agent: --effort must be one of " + ", ".join(EFFORTS) + ". Nothing was started.")
    return effort


def check_options(agent: Agent, cap_uu=None, model=None, effort=None) -> RunOptions:
    """The options of one `agent run` as given on the command line (text), or a usage error (64) before anything is
    read or started. The cap against limits.per_run is checked by the caller that can read units.yaml."""
    cap = None
    if cap_uu is not None:
        if not isinstance(cap_uu, str) or not CAP_RE.fullmatch(cap_uu):
            raise UsageError("agent: --cap-uu must be a whole number of UU, at least 1. Nothing was started.")
        cap = int(cap_uu)
    if model is not None:
        check_model(model)
    if effort is not None:
        check_effort(effort)
        if agent.platform not in ("claude-code", "kiro"):
            raise UsageError(f"agent: --effort is not offered for a {agent.platform} agent. Nothing was started.")
    return RunOptions(cap, model, effort)


def check_prompt(prompt, platform: str) -> str:
    """A prompt that can be passed safely, or a usage error (exit 64)."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise UsageError("agent: the prompt is empty")
    if "\x00" in prompt:
        raise UsageError("agent: the prompt must not contain a NUL character")
    if len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
        raise UsageError(f"agent: the prompt is larger than {MAX_PROMPT_BYTES} bytes")
    if platform == "claude-code" and prompt.startswith("-"):
        raise UsageError("agent: a Claude Code prompt must not start with '-' "
                         "(the Claude Code docs do not say how to end the flags)")
    return prompt


def _assert_allowed(argv: list, skip: int | None = None) -> list:
    """Every list passes through here. A forbidden flag is a bug: refuse to build the list."""
    for i, word in enumerate(argv):
        if i == skip:
            continue  # the prompt is the owner's text, not a flag
        if not isinstance(word, str) or word in FORBIDDEN_FLAGS or any(t in word for t in FORBIDDEN_TEXT):
            raise RuntimeError("agent: an argument list held a forbidden flag; nothing was started")
        if word.split("=", 1)[0] in LOGIN_FORBIDDEN:
            raise RuntimeError("agent: an argument list held a forbidden login word; nothing was started")
        if word in ("--model", "--effort"):  # W9.6: the only new words, each followed by a checked value
            value = argv[i + 1] if i + 1 < len(argv) and i + 1 != skip else None
            try:
                check_model(value) if word == "--model" else check_effort(value)
            except UsageError:
                raise RuntimeError("agent: an argument list held a model or effort that is not allowed; "
                                   "nothing was started") from None
    return argv


def build_argv(agent: Agent, mode: str, command_path: str, root: Path, python: str,
               prompt: str | None = None, src: Path | None = None, model: str | None = None,
               effort: str | None = None) -> tuple:
    """(argument list, stdin text or None). The only place an agent's command line is made.

    model and effort (W9.6) are for `agent run` of Claude Code and Kiro only; None adds nothing."""
    if mode not in (RUN, CHAT, LOGIN):
        raise UsageError("agent: the mode must be run, chat or login")
    if (model is not None or effort is not None) and (mode != RUN or agent.platform not in ("claude-code", "kiro")):
        raise UsageError("agent: --model and --effort are only for agent run of a Claude Code or Kiro agent")
    extra = []
    if model is not None:
        extra += ["--model", check_model(model)]
    if effort is not None:
        extra += ["--effort", check_effort(effort)]
    root = Path(root)
    if mode == LOGIN:  # the sign-in, never an agent (10.R12.9, 10.R12.13)
        if agent.platform == "claude-code" and agent.transport == ACP:
            return _assert_allowed([command_path, str(claude_acp_path(CLAUDE_ACP_ADAPTER, src)),
                                    *CLAUDE_LOGIN_TAIL]), None
        if agent.platform == "kiro":
            return _assert_allowed([command_path, "login"]), None
        raise UsageError(LOGIN_ONLY)
    if agent.platform == "opencode":  # only the chat: `agent run` and `agent login` refuse it before this point
        if mode != CHAT:
            raise UsageError("agent: an OpenCode agent has a chat only")
        return _assert_allowed([command_path, "acp"]), None
    if is_claude_acp(agent, mode):
        # command_path is node here; the adapter is the fixed path, never looked up through PATH or npx
        return _assert_allowed([command_path, str(claude_acp_path(CLAUDE_ACP_ADAPTER, src))]), None
    if agent.platform == "claude-code":
        settings = claude_settings(python, hook_path("claude-code", src), root)
        if mode == RUN:
            argv = [command_path, "-p", "--permission-mode", "default", "--settings", settings]
            if agent.max_turns is not None:
                argv += ["--max-turns", str(agent.max_turns)]
            argv += extra
            argv.append(check_prompt(prompt, agent.platform))
            return _assert_allowed(argv, skip=len(argv) - 1), None
        return _assert_allowed([command_path, "--permission-mode", "default", "--settings", settings]), None
    if agent.platform == "kiro":
        if mode == RUN:
            argv = [command_path, "chat", "--v3", "--no-interactive", *extra]
            if agent.kiro_agent:
                argv += ["--agent", agent.kiro_agent]
            if agent.trust_tools:
                argv.append("--trust-tools=" + ",".join(agent.trust_tools))
            return _assert_allowed(argv), check_prompt(prompt, agent.platform)
        if agent.transport == ACP:
            return _assert_allowed([command_path, "acp", "--agent-engine=v3"]), None
        argv = [command_path, "chat", "--v3"]
        if agent.kiro_agent:
            argv += ["--agent", agent.kiro_agent]
        return _assert_allowed(argv), None
    raise UsageError("agent: unknown platform")


# --------------------------------------------- part 2: gate checks (10.R6)


@dataclass
class Check:
    name: str
    ok: bool | None  # None: not run, because an earlier check failed
    detail: str


@dataclass
class Gate:
    checks: list = field(default_factory=list)
    command_path: str | None = None
    version: tuple | None = None
    plan: str | None = None  # Claude Code: the plan word the login check read (10.R12.4)

    @property
    def gated(self) -> bool:
        return bool(self.checks) and all(c.ok for c in self.checks)

    def reason(self) -> str:
        for c in self.checks:
            if not c.ok:
                return f"{c.name}: {c.detail}"
        return ""


def _run_child(argv: list, stdin: bytes, timeout: float, cwd: str, env: dict | None = None,
               keep_output: bool = True) -> tuple:
    """(exit code or None, stdout bytes). The only place this module starts a short program.

    None means it could not start or did not finish in time (it is then killed). env None: umwayi's
    environment; else exactly env. keep_output False: stdout goes to /dev/null and is never read.
    stderr is never read.
    """
    try:
        proc = subprocess.run(argv, input=stdin, stdout=subprocess.PIPE if keep_output else subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=timeout, cwd=cwd, env=env,
                              shell=False, check=False)
    except subprocess.TimeoutExpired:
        return None, b""
    except (OSError, ValueError):
        return None, b""
    return proc.returncode, (proc.stdout or b"") if keep_output else b""


def parse_version(output: bytes) -> tuple | None:
    m = _VERSION.search(output[:MAX_VERSION_OUTPUT])
    return tuple(int(x) for x in m.groups()) if m else None


def _show(version: tuple) -> str:
    return ".".join(str(x) for x in version)


def python_path() -> str | None:
    """The Python running umwayi, used to run the hook. Must be an absolute path."""
    exe = sys.executable
    return exe if exe and os.path.isabs(exe) else None


def kiro_hook_command(python: str, hook: Path, root: Path) -> str:
    return f"{python} {hook} --root {root}"


def _python_word_ok(word: str) -> bool:
    if word == "python3":
        return True
    return (word.startswith("/") and ".." not in PurePosixPath(word).parts
            and PurePosixPath(word).name.startswith("python"))


def _hook_matches(hook, want_hook: str, want_root: str) -> bool:
    if not isinstance(hook, dict) or hook.get("trigger") != "PreToolUse":
        return False
    if "matcher" in hook and hook["matcher"] != "*":
        return False
    action = hook.get("action")
    if not isinstance(action, dict) or action.get("type") != "command" or not isinstance(action.get("command"), str):
        return False
    words = action["command"].split(" ")
    return (len(words) == 4 and _python_word_ok(words[0]) and words[1] == want_hook
            and words[2] == "--root" and words[3] == want_root)


def find_kiro_hook(workdir: str, root: Path, src: Path | None = None, home: Path | None = None) -> tuple:
    """(path of the matching hook file or None, list of files that were skipped and why). Reads only."""
    want_hook, want_root = str(hook_path("kiro", src)), str(root)
    home = home if home is not None else Path(os.path.expanduser("~"))
    skipped: list = []
    for folder in (Path(workdir) / ".kiro" / "hooks", home / ".kiro" / "hooks"):
        try:
            names = sorted(os.listdir(folder))
        except FileNotFoundError:
            continue
        except OSError:
            skipped.append(f"{folder} cannot be read")
            continue
        for fname in names:
            if not fname.endswith(".json"):
                continue
            p = folder / fname
            try:
                st = os.lstat(p)
            except OSError:
                skipped.append(f"{p} cannot be read")
                continue
            if not stat.S_ISREG(st.st_mode):
                skipped.append(f"{p} is not a regular file")
                continue
            if st.st_size > MAX_HOOK_FILE_BYTES:
                skipped.append(f"{p} is larger than {MAX_HOOK_FILE_BYTES} bytes")
                continue
            try:
                data = json.loads(p.read_bytes().decode("utf-8"))
            except (OSError, UnicodeDecodeError, ValueError, RecursionError):
                skipped.append(f"{p} is not valid JSON")
                continue
            if not isinstance(data, dict) or data.get("version") != "v1" or not isinstance(data.get("hooks"), list):
                continue
            if any(_hook_matches(h, want_hook, want_root) for h in data["hooks"]):
                return p, skipped
    return None, skipped


def _recorder(gate: Gate, order: list):
    def done(name: str, ok: bool, detail: str) -> bool:
        gate.checks.append(Check(name, ok, detail))
        if not ok:
            for rest in order[order.index(name) + 1:]:
                gate.checks.append(Check(rest, None, "an earlier check failed"))
        return ok
    return done


def _hook_checks(platform: str, root: Path, src: Path | None, done, env: dict | None = None) -> bool:
    """The layer 9 hook script and its self-test (10.R6), the same for every platform and transport."""
    hook = hook_path(platform, src)
    try:
        hst = os.lstat(hook)
        hook_ok = stat.S_ISREG(hst.st_mode)
    except OSError:
        hook_ok = False
    if not done("hook script", hook_ok, f"{hook}" + ("" if hook_ok else " is missing or not a regular file")):
        return False
    python = python_path()
    if python is None:
        return done("hook self-test", False, "the path of the Python running umwayi is not known")
    code, _ = _run_child([python, str(hook), "--root", str(root)], SELFTEST_INPUT, SELFTEST_TIMEOUT, str(root),
                         env=env)
    if code != SELFTEST_EXIT:
        what = f"did not answer within {SELFTEST_TIMEOUT:.0f} s or could not start" if code is None else f"exited {code}"
        return done("hook self-test", False,
                    f"the hook {what}; it must block the self-test event with exit {SELFTEST_EXIT}")
    return done("hook self-test", True, f"the hook started and blocked the self-test event (exit {SELFTEST_EXIT})")


def _login_gate(argv: list, cwd: str, env: dict, gate: Gate, done) -> bool:
    """Run `auth status --json` and record the login check. Its output is never printed, logged or kept."""
    code, out = _run_child(argv, b"", SIGNIN_TIMEOUT, cwd, env=env)
    ok, detail, plan = login_check(code, out[:MAX_LOGIN_OUTPUT + 1])
    del out
    if ok:
        gate.plan = plan
    return done("login", ok, detail)


def _kiro_login_gate(kiro: str, cwd: str, env: dict, done) -> bool:
    """The Kiro login check (10.R12.13): `kiro-cli whoami` by its exit code only.

    Its output goes to /dev/null and is never read: the field names are not documented and it holds the email.
    """
    code, _ = _run_child(_assert_allowed([kiro, "whoami"]), b"", SIGNIN_TIMEOUT, cwd, env=env, keep_output=False)
    if code == 0:
        return done("login", True, "Kiro is signed in (kiro-cli whoami exited 0)")
    how = f"no answer within {SIGNIN_TIMEOUT:.0f} s" if code is None else f"kiro-cli whoami exited {code}"
    return done("login", False, f"Kiro is not signed in ({how}). {KIRO_SIGNIN_TEXT}")


CLAUDE_ACP_ORDER = ["node", "node version", "adapter file", "adapter package", "adapter version",
                    "claude code version", "login", "hook script", "hook self-test"]


def _regular_file(path: Path) -> bool:
    """A regular file, and no link anywhere in the path (the real path is the path itself)."""
    try:
        st = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISREG(st.st_mode) and os.path.realpath(path) == str(path)


def _claude_acp_checks(agent: Agent, root: Path, src: Path | None, gate: Gate, login_only: bool = False) -> Gate:
    """The gate checks of a Claude Code ACP chat, in the order of design.md part 7 (10.R11.6).

    login_only (`umwayi agent login`): the checks up to and with the login check; no hook checks, because the
    sign-in runs no agent and no tool. A failed login check is then what the login is for, not a refusal.
    """
    order = CLAUDE_ACP_ORDER[:CLAUDE_ACP_ORDER.index("login") + 1] if login_only else CLAUDE_ACP_ORDER
    done = _recorder(gate, order)
    env = child_env(os.environ)

    # 1. node on PATH, an absolute path
    node = shutil.which(NODE_COMMAND)
    if not node or not os.path.isabs(node):
        done("node", False, f"{NODE_COMMAND} was not found on PATH (Node.js {NODE_MIN[0]} or later is needed)")
        return gate
    gate.command_path = node
    done("node", True, f"{NODE_COMMAND} found at {node}")

    # 2. node --version: vN.N.N, at least 22
    code, out = _run_child(probe_argv(node, Path(), "node version"), b"", VERSION_TIMEOUT, agent.workdir, env=env)
    m = _NODE_VERSION.fullmatch(out[:MAX_VERSION_OUTPUT]) if code == 0 else None
    version = tuple(int(x) for x in m.groups()) if m else None
    if code is None:
        ok = done("node version", False, f"node --version did not answer within {VERSION_TIMEOUT:.0f} s")
    elif code != 0:
        ok = done("node version", False, f"node --version exited {code}")
    elif version is None:
        ok = done("node version", False, "node --version did not print a version like v22.0.0")
    elif version < NODE_MIN:
        ok = done("node version", False, f"{_show(version)} is older than {_show(NODE_MIN)} "
                                         f"(the adapter needs Node.js {NODE_MIN[0]})")
    else:
        ok = done("node version", True, f"{_show(version)} (at least {_show(NODE_MIN)})")
    if not ok:
        return gate

    # 3. the adapter file, at the fixed path, a regular file and not a link
    adapter = claude_acp_path(CLAUDE_ACP_ADAPTER, src)
    adapter_ok = _regular_file(adapter)
    if not done("adapter file", adapter_ok,
                f"{adapter}" + ("" if adapter_ok else
                                " is missing, a link or not a regular file. Install it yourself: in "
                                f"{CLAUDE_ACP_DIR}/ run npm ci --ignore-scripts (see its README.md)")):
        return gate

    # 4. its package.json: exactly the pinned name and version
    pkg = claude_acp_path(CLAUDE_ACP_PACKAGE_DIR + "/package.json", src)
    data = None
    if _regular_file(pkg):
        try:
            if os.lstat(pkg).st_size <= MAX_FILE_BYTES:
                with open(pkg, "rb") as f:
                    raw = f.read(MAX_FILE_BYTES + 1)
                if len(raw) <= MAX_FILE_BYTES:
                    data = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, ValueError, RecursionError):
            data = None
    if not isinstance(data, dict):
        done("adapter package", False, f"{pkg} is missing, a link, too big or not valid JSON")
        return gate
    if data.get("name") != CLAUDE_ACP_PACKAGE or data.get("version") != CLAUDE_ACP_VERSION:
        done("adapter package", False, f"the installed package is not {CLAUDE_ACP_PACKAGE} {CLAUDE_ACP_VERSION}; "
                                       f"in {CLAUDE_ACP_DIR}/ run npm ci --ignore-scripts")
        return gate
    done("adapter package", True, f"{CLAUDE_ACP_PACKAGE} {CLAUDE_ACP_VERSION}")

    # 5. NODE ADAPTER --version prints exactly the pin
    code, out = _run_child(probe_argv(node, adapter, "adapter version"), b"", VERSION_TIMEOUT, agent.workdir,
                           env=env)
    if code != 0 or out[:MAX_VERSION_OUTPUT].rstrip(b"\r\n") != CLAUDE_ACP_VERSION.encode("ascii"):
        what = ("did not answer in time or could not start" if code is None else
                f"exited {code}" if code != 0 else f"did not print exactly {CLAUDE_ACP_VERSION}")
        done("adapter version", False, f"the adapter --version {what}")
        return gate
    done("adapter version", True, f"the adapter says {CLAUDE_ACP_VERSION}")

    # 6. NODE ADAPTER --cli --version: the bundled Claude Code, at least 2.1.295
    plat = PLATFORMS["claude-code"]
    code, out = _run_child(probe_argv(node, adapter, "claude code version"), b"", VERSION_TIMEOUT, agent.workdir,
                           env=env)
    version = parse_version(out) if code == 0 else None
    if code is None:
        ok = done("claude code version", False, f"the adapter --cli --version did not answer within "
                                                f"{VERSION_TIMEOUT:.0f} s")
    elif code != 0:
        ok = done("claude code version", False, f"the adapter --cli --version exited {code}")
    elif version is None:
        ok = done("claude code version", False, "no version number in the output of the adapter --cli --version")
    elif version < plat.min_version:
        ok = done("claude code version", False, f"{_show(version)} is older than {_show(plat.min_version)} "
                                                f"({plat.why_version})")
    else:
        gate.version = version
        ok = done("claude code version", True, f"{_show(version)} (at least {_show(plat.min_version)})")
    if not ok:
        return gate

    # 7. the login check (10.R12.3): a Claude subscription must be what pays; only six fields are read
    if not _login_gate(probe_argv(node, adapter, "login"), agent.workdir, env, gate, done) or login_only:
        return gate

    # 8. the layer 9 Claude Code hook and its self-test, with the same environment
    _hook_checks("claude-code", root, src, done, env=env)
    return gate


def _opencode_shown(name: str) -> str | None:
    """A file name that is safe to show in a refusal: short and plain printable text. None otherwise."""
    return name if len(name) <= 60 and name.isprintable() else None


def _opencode_files(src: Path | None) -> tuple:
    """(ok, detail). The layer 9 generic adapter's hook.py and the plugin's index.js are regular files inside the umwayi
    source tree with no link on the way, and the plugin folder holds index.js and nothing else (OC21): OpenCode
    loads `server` before `index` from a folder without a package.json, so another file there could replace the gate."""
    base = str(src or umwayi_src())
    real_base = os.path.realpath(base)
    files = []
    for rel in (PLATFORMS["opencode"].hook, OPENCODE_PLUGIN_DIR + "/index.js"):
        path = os.path.join(base, *rel.split("/"))
        try:
            st = os.lstat(path)
        except OSError:
            return False, f"{path} is missing or not a regular file"
        if stat.S_ISLNK(st.st_mode):
            return False, f"{path} is a link; it must be a regular file inside the umwayi source tree"
        if not stat.S_ISREG(st.st_mode):
            return False, f"{path} is missing or not a regular file"
        if os.path.realpath(path) != os.path.join(real_base, *rel.split("/")):
            return False, f"{path} is reached through a link or lies outside the umwayi source tree"
        files.append(path)
    folder = os.path.join(base, *OPENCODE_PLUGIN_DIR.split("/"))
    try:
        others = sorted(n for n in os.listdir(folder) if n != "index.js")
    except OSError:
        return False, f"{folder} cannot be listed"
    if others:
        shown = [n for n in others if _opencode_shown(n)][:OPENCODE_MAX_SHOWN_NAMES]
        hidden = len(others) - len(shown)
        more = f" and {hidden} other name(s)" if hidden else ""
        return False, f"{folder} holds more than index.js: {', '.join(shown)}{more}"
    return True, f"{files[0]} and {files[1]} are regular files inside {base}, and the plugin folder holds index.js only"


def _opencode_managed() -> str | None:
    """None, or the managed OpenCode place that exists (OC4). A managed config outranks the one umwayi passes."""
    found = None
    for path in OPENCODE_MANAGED_DIRS:
        if os.path.lexists(path):
            found = path
            break
    if found is None:
        candidates = [os.path.join(OPENCODE_MANAGED_PLIST_ROOT, OPENCODE_MANAGED_PLIST)]
        try:
            with os.scandir(OPENCODE_MANAGED_PLIST_ROOT) as it:
                for n, entry in enumerate(it):
                    if n >= 1000:
                        break
                    if entry.is_dir(follow_symlinks=False):
                        candidates.append(os.path.join(entry.path, OPENCODE_MANAGED_PLIST))
        except OSError:
            pass
        found = next((c for c in candidates if os.path.lexists(c)), None)
    if found is None:
        return None
    return f"{found} exists; a managed OpenCode configuration outranks the one umwayi passes"


def _opencode_other_config(workdir: str, home: str) -> str | None:
    """None, or why another OpenCode config could widen the gate (OC7). A text match on names and quoted words, never a
    parse; only names, sizes and the fixed words are ever shown, never the text of a file."""
    seen = set()
    for start in (workdir, os.path.realpath(workdir)):  # the path as given, then the real one
        folder = start
        while True:
            if folder not in seen:
                seen.add(folder)
                for name in OPENCODE_PROJECT_NAMES:
                    path = os.path.join(folder, name)
                    if os.path.lexists(path):
                        return f"{path} exists in the workdir or a folder above it"
            parent = os.path.dirname(folder)
            if parent == folder:
                break
            folder = parent
    path = os.path.join(home, ".opencode")
    if os.path.lexists(path):
        return f"{path} exists in the home folder"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    folder = os.path.join(xdg if xdg and os.path.isabs(xdg) else os.path.join(home, ".config"), "opencode")
    for name in OPENCODE_GLOBAL_ENTRIES:
        path = os.path.join(folder, name)
        if os.path.lexists(path):
            return f"{path} exists in the global OpenCode folder"
    for name in OPENCODE_GLOBAL_FILES:
        path = os.path.join(folder, name)
        try:
            st = os.lstat(path)
        except FileNotFoundError:
            continue
        except OSError:
            return f"{path} cannot be read"
        if not stat.S_ISREG(st.st_mode):
            return f"{path} is a link or not a regular file"
        if st.st_size > OPENCODE_MAX_GLOBAL_CONFIG:
            return f"{path} is larger than {OPENCODE_MAX_GLOBAL_CONFIG} bytes"
        try:
            with open(path, "rb") as f:
                text = f.read(OPENCODE_MAX_GLOBAL_CONFIG + 1).decode("utf-8")
        except (OSError, UnicodeDecodeError):
            return f"{path} cannot be read as UTF-8 text"
        if len(text.encode("utf-8")) > OPENCODE_MAX_GLOBAL_CONFIG:
            return f"{path} is larger than {OPENCODE_MAX_GLOBAL_CONFIG} bytes"
        for key in OPENCODE_GLOBAL_KEYS:
            if f'"{key}"' in text:
                return f'{path} holds the key "{key}"'
    return None


def _opencode_checks(agent: Agent, plat: Platform, gate: Gate, src: Path | None, home: Path | None) -> Gate:
    """The six checks of an OpenCode agent (10.R13.8), in order, the first failure ends it: command, version, files,
    managed config, other config, route. Reads only. `opencode --version` runs in the workdir with the allow-listed
    environment and an empty inline config (the version flag starts no server)."""
    order = ["command", "version", "files", "managed config", "other config", "route"]
    done = _recorder(gate, order)
    found = shutil.which(agent.command)
    if not found or not os.path.isabs(found):
        done("command", False, f"{agent.command} was not found on PATH")
        return gate
    gate.command_path = found
    done("command", True, f"{agent.command} found at {found}")

    code, out = _run_child([found, plat.version_flag], b"", OPENCODE_VERSION_TIMEOUT, agent.workdir,
                           env=opencode_env(os.environ, "{}"))
    version = parse_version(out) if code == 0 else None
    if code is None:
        ok = done("version", False, f"{agent.command} {plat.version_flag} did not answer within "
                                    f"{OPENCODE_VERSION_TIMEOUT:.0f} s")
    elif code != 0:
        ok = done("version", False, f"{agent.command} {plat.version_flag} exited {code}")
    elif version is None:
        ok = done("version", False, f"no version number in the output of {agent.command} {plat.version_flag}")
    elif version < plat.min_version:
        ok = done("version", False, f"{_show(version)} is older than {_show(plat.min_version)} ({plat.why_version})")
    else:
        gate.version = version
        ok = done("version", True, f"{_show(version)} (at least {_show(plat.min_version)})")
    if not ok:
        return gate

    files_ok, detail = _opencode_files(src)
    if not done("files", files_ok, detail):
        return gate

    managed = _opencode_managed()
    if not done("managed config", managed is None, managed or "no managed OpenCode configuration found"):
        return gate

    home_text = str(home) if home else os.path.expanduser("~")
    other = _opencode_other_config(agent.workdir, home_text)
    if not done("other config", other is None, other or "no other OpenCode configuration found that can widen the gate"):
        return gate

    try:
        integration, _ = opencode_route(agent.provider)
    except OpenCodeRefused as e:
        done("route", False, str(e).removeprefix("agent: ").removesuffix(" Nothing was started."))
        return gate
    done("route", True, f"provider {agent.provider} (integration.use allows {integration})")
    return gate


def gate_checks(agent: Agent, root, src: Path | None = None, home: Path | None = None,
                mode: str | None = None) -> Gate:
    """Every check from 10.R6.1 (or 10.R11.6 for a Claude Code ACP chat), in order.

    The first that fails ends it; the rest are 'not run'. mode RUN for a Claude Code agent with
    transport acp: the checks of `claude -p`, because `agent run` stays headless `claude -p`.
    """
    root = _root(root)
    plat = PLATFORMS[agent.platform]
    gate = Gate()
    if mode == LOGIN and not can_login(agent):
        raise UsageError(LOGIN_ONLY)
    if agent.platform == "opencode":  # the six checks of 10.R13.8
        return _opencode_checks(agent, plat, gate, src, home)
    if is_claude_acp(agent, mode):
        return _claude_acp_checks(agent, root, src, gate, login_only=mode == LOGIN)
    claude = agent.platform == "claude-code"
    kiro = agent.platform == "kiro"
    order = ["command", "version", "login"] + ([] if mode == LOGIN else
                                               ["hook script", "hook self-test"] + (["kiro hook file"] if kiro else []))
    done = _recorder(gate, order)
    # the environment the agent itself will get: without the credential names (10.R12.6, 10.R12.13)
    env = claude_env(os.environ) if claude else kiro_env(os.environ)

    found = shutil.which(agent.command)
    if not found or not os.path.isabs(found):
        done("command", False, f"{agent.command} was not found on PATH")
        return gate
    gate.command_path = found
    done("command", True, f"{agent.command} found at {found}")

    code, out = _run_child([found, plat.version_flag], b"", VERSION_TIMEOUT, agent.workdir, env=env)
    version = parse_version(out) if code == 0 else None
    if code is None:
        ok = done("version", False, f"{agent.command} {plat.version_flag} did not answer within {VERSION_TIMEOUT:.0f} s")
    elif code != 0:
        ok = done("version", False, f"{agent.command} {plat.version_flag} exited {code}")
    elif version is None:
        ok = done("version", False, f"no version number in the output of {agent.command} {plat.version_flag}")
    elif version < plat.min_version:
        ok = done("version", False, f"{_show(version)} is older than {_show(plat.min_version)} ({plat.why_version})")
    else:
        gate.version = version
        ok = done("version", True, f"{_show(version)} (at least {_show(plat.min_version)})")
    if not ok:
        return gate

    if claude and not _login_gate(_assert_allowed([found, "auth", "status", "--json"]), agent.workdir, env, gate,
                                  done):
        return gate
    if kiro and not _kiro_login_gate(found, agent.workdir, env, done):
        return gate
    if mode == LOGIN:
        return gate

    if not _hook_checks(agent.platform, root, src, done):
        return gate
    hook = hook_path(agent.platform, src)

    if agent.platform == "kiro":
        want = kiro_hook_command("python3", hook, root)
        if " " in str(hook) or " " in str(root):
            done("kiro hook file", False, "the hook path or the root has a space, and a Kiro command hook runs "
                                          "in a shell; move umwayi-os or the root to a path without spaces")
            return gate
        path, skipped = find_kiro_hook(agent.workdir, root, src, home)
        note = f" (skipped: {'; '.join(skipped)})" if skipped else ""
        if path is None:
            done("kiro hook file", False,
                 f"no PreToolUse hook for every tool runs exactly '{want}' in {agent.workdir}/.kiro/hooks/ or "
                 f"~/.kiro/hooks/. Add the hook file from adapters/kiro/README.md yourself{note}")
            return gate
        done("kiro hook file", True, f"{path}{note}")
    return gate


def check_agent(root, name: str, given: str | None = None, home: Path | None = None) -> Result:
    """`umwayi agent check NAME`: every gate check, one line each. Starts no agent and writes nothing.

    0: the agent can be gated. 2: it cannot. 64: a usage or config error.
    """
    root = _root(root)
    agent = find(load(root, given), name)
    gate = gate_checks(agent, root, home=home)
    lines = [f"Agent {agent.name}: {agent.platform}, transport {agent.transport}, workdir {agent.workdir}"]
    if is_claude_acp(agent, CHAT):
        lines.append("These are the checks of a Claude Code ACP chat (node and the pinned adapter "
                     f"{CLAUDE_ACP_PACKAGE} {CLAUDE_ACP_VERSION}); 'umwayi agent run' for this agent "
                     "starts claude -p and runs the checks of transport cli.")
    st = kill.state(root)
    lines.append(f"kill switch: {st}" + ("" if st == kill.OFF else " (a start would stop now with exit 3)"))
    for c in gate.checks:
        mark = "ok" if c.ok else ("no" if c.ok is False else "not run")
        lines.append(f"{mark}: {c.name}: {c.detail}")
    if not gate.gated:
        lines.append(f"Not gated: agent {agent.name} would be refused (exit 2). Nothing was started.")
        return Result(2, lines)
    if agent.platform == "opencode":  # the six checks of 10.R13.8; the chat itself is 10.R13.10 to 10.R13.12
        argv, _ = build_argv(agent, CHAT, gate.command_path, root, python_path())
        lines.append(f"chat would start: {json.dumps(argv)} with the allow-listed environment and the inline config; "
                     "the chat goes on only after the plugin has written the canary in the session")
        lines.append(f"Gated: the checks for an OpenCode chat of agent {agent.name} passed. Nothing was started.")
        return Result(0, lines)
    python = python_path()
    if is_claude_acp(agent, CHAT):
        argv, _ = build_argv(agent, CHAT, gate.command_path, root, python)
        lines.append(f"chat would start: {json.dumps(argv)} with the allow-listed environment; the chat goes on only "
                     "after the SessionStart canary has run in the session")
        lines.append(f"Gated: the checks for a Claude Code ACP chat of agent {agent.name} passed. Nothing was started.")
        return Result(0, lines)
    modes = [RUN, CHAT]
    for mode in modes:
        argv, stdin = build_argv(agent, mode, gate.command_path, root, python,
                                 prompt="PROMPT" if mode == RUN else None)
        shown = json.dumps(argv)
        lines.append(f"{mode} would start: {shown}" + (" with the prompt on stdin" if stdin is not None else ""))
    lines.append(f"Gated: agent {agent.name} can be started. Nothing was started.")
    return Result(0, lines)


# --------------------------------------------- part 3: `umwayi agent run` (10.R3, 10.R4, 10.R8)

SOURCE = "umwayi agent run"
SECONDS_PER_MINUTE = 60
WATCH_INTERVAL = 1.0  # seconds between kill switch, logbook and timeout checks while an agent runs
STOP_GRACE = 10.0  # seconds between SIGTERM and SIGKILL
TELEMETRY_GRACE = 6.0  # seconds, at most, for a report still being received after the agent was stopped (B.R2)
ASK_RECOMMENDATION = ("Keep it stopped unless you trust this agent for this kind of task. To allow it, add a Yes "
                      "rule for action type agent_run with this agent in rules.yaml. Answering this item does not "
                      "start the agent.")
NOT_LOGGED = "The prompt and the conversation are not written to the logbook."
BUDGET_ASK_RECOMMENDATION = ("Keep it stopped unless this spend is fine. To allow it, add a Yes rule for budget_check "
                             "to rules.yaml; answering this item does not start the agent.")
LOGIN_NOT_LOGGED = "What the login printed was not read and is not written to the logbook."


def read_prompt(prompt: str | None, prompt_file: str | None, from_stdin: bool, stdin) -> str:
    """The prompt, given in exactly one way. Anything else is a usage error (exit 64). Never logged."""
    ways = (prompt is not None) + (prompt_file is not None) + bool(from_stdin)
    if ways != 1:
        raise UsageError("agent: give the prompt in exactly one way: --prompt TEXT, --prompt-file PATH, "
                         "or - to read it from stdin")
    if prompt is not None:
        return prompt
    if prompt_file is not None:
        try:
            st = os.lstat(prompt_file)
        except OSError:
            raise UsageError("agent: the prompt file was not found or cannot be read") from None
        if not stat.S_ISREG(st.st_mode):
            raise UsageError("agent: the prompt file must be a regular file, not a link or a folder")
        if st.st_size > MAX_PROMPT_BYTES:
            raise UsageError(f"agent: the prompt is larger than {MAX_PROMPT_BYTES} bytes")
        try:
            with open(prompt_file, "rb") as f:
                data = f.read(MAX_PROMPT_BYTES + 1)
        except OSError:
            raise UsageError("agent: the prompt file cannot be read") from None
    else:
        try:
            data = stdin.read(MAX_PROMPT_BYTES + 1)
        except Exception:
            raise UsageError("agent: the prompt could not be read from stdin") from None
    if len(data) > MAX_PROMPT_BYTES:
        raise UsageError(f"agent: the prompt is larger than {MAX_PROMPT_BYTES} bytes")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise UsageError("agent: the prompt is not valid UTF-8") from None


def _one_line(text: str, limit: int = 300) -> str:
    """Safe for one logbook field: printable, one line, no spaces at the ends."""
    text = "".join(ch if ch.isprintable() else "?" for ch in str(text)).strip()
    return (text[: limit - 3] + "...") if len(text) > limit else (text or "-")


def _exit_text(code: int) -> str:
    return f"by signal {-code}" if code < 0 else f"with code {code}"


QUEUE_SUMMARY_ROWS = 5  # open queue items listed by name before a chat starts


def _proc_stat(pid) -> tuple | None:
    """(state, parent pid, start time) from /proc/PID/stat, or None if it cannot be read (Linux only)."""
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            rest = f.read().rsplit(b")", 1)[1].split()
        return rest[0].decode("ascii", "replace"), int(rest[1]), int(rest[19])
    except (OSError, IndexError, ValueError):
        return None


def _descendants(root_pid: int) -> dict:
    """pid -> start time of every live, non-zombie descendant of root_pid, from one pass over /proc."""
    children: dict = {}
    try:
        names = os.listdir("/proc")
    except OSError:
        return {}
    for name in names:
        if not name.isdigit():
            continue
        st = _proc_stat(name)
        if st is not None and st[0] != "Z":
            children.setdefault(st[1], []).append((int(name), st[2]))
    found, todo = {}, [root_pid]
    while todo:
        for pid, start in children.get(todo.pop(), []):
            if pid not in found:
                found[pid] = start
                todo.append(pid)
    return found


def _same_process(pid: int, start: int) -> bool:
    """True if pid is still the process seen before (same start time, not a zombie): a reused pid is never signalled."""
    st = _proc_stat(pid)
    return st is not None and st[0] != "Z" and st[2] == start


def _signal_pid(pid: int, sig: int) -> None:
    try:
        os.kill(pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _feed(pipe, data: bytes) -> None:
    """Write the prompt to the agent's stdin and close it, so the agent sees the end of the instruction."""
    try:
        pipe.write(data)
    except (OSError, ValueError):
        pass  # the agent closed its stdin or was stopped: its exit is logged
    finally:
        try:
            pipe.close()
        except (OSError, ValueError):
            pass


class _Signalled(BaseException):
    """umwayi itself got SIGTERM or SIGHUP. A BaseException, so no `except Exception` swallows it."""

    def __init__(self, signum: int):
        super().__init__(signum)
        self.signum = signum


class _Run:
    """One `umwayi agent run`, `umwayi agent chat` or `umwayi agent login`. go() returns a Result; the agent (or
    the sign-in) is stopped on every path out.

    run:  the agent gets /dev/null or the prompt on stdin, in its own session and process group, and is
          stopped by signalling that group.
    chat: the agent gets the owner's terminal unchanged (stdin, stdout and stderr inherited) and stays in
          umwayi's process group, because an interactive screen needs the controlling terminal. It is
          stopped by signalling its pid and every descendant umwayi has seen (read from /proc once a
          second), never umwayi's own group. While it runs, Ctrl-C is caught by a no-op handler in umwayi,
          so it reaches the agent only; the old handler is put back on every path.
    login: the sign-in (10.R12.9) gets the owner's terminal like a cli chat and is stopped the same way. umwayi
          has no pipe to it, so it never sees what it prints; afterwards the login check decides.
    """

    def __init__(self, root: Path, agent: Agent, prompt: str | None, clock, mode: str = RUN, out=None,
                 options: RunOptions | None = None):
        self.options = options or RunOptions()  # W9.6: all None unless `agent run` was given an option
        self.root = root
        self.agent = agent
        self.prompt = prompt
        self.clock = clock  # today's date, asked again for every entry (a run can pass midnight)
        self.mode = mode
        self.out = out  # chat: where the queue summary goes before the agent starts
        self.proc = None
        self.started = None
        self.signalled = False
        self.seen = {}  # chat: pid -> start time of every descendant of the agent seen so far
        self.tty = None  # chat: (fd, termios attributes) to put back after the agent
        self.canary = None  # Claude Code ACP chat: (private folder, token) of this start
        self.meta = None  # Claude Code ACP chat: the _meta of session/new
        self.opencode_config = None  # OpenCode chat: the inline config, passed in OPENCODE_CONFIG_CONTENT
        self.gate = None  # login: the gate of the checks before the sign-in (the program found, for the check after)
        self.budget = None  # budget governor: the reservation of this start (run id, micros, units, receiver)

    # ------------------------------------------------------------ logbook

    def log(self, added: str, checked: str, not_done: str) -> str | None:
        """One entry through the checked append. Returns None, or why it could not be written."""
        try:
            logbook.append(self.root, logbook.Entry(self.clock(), SOURCE, _one_line(added), _one_line(checked),
                                                    _one_line(not_done)))
        except UmwayiError as e:
            return str(e).rstrip(". ")
        return None

    @staticmethod
    def result(code: int, lines: list, why: str | None = None) -> Result:
        if why is not None:
            lines = lines + [f"The logbook could not be written ({why}). Nothing was logged."]
        return Result(code, lines)

    # ------------------------------------------------------------ signals

    _old_sigint = None

    @staticmethod
    def _sigint_while_chatting(_signum, _frame):
        """Ctrl-C goes to the whole foreground group: the agent handles it, umwayi does nothing.

        A Python handler, not SIG_IGN: an ignored signal stays ignored in the child after exec, so
        SIG_IGN would also stop the agent from seeing Ctrl-C.
        """

    def _save_terminal(self) -> None:
        try:
            import termios
            if os.isatty(0):
                self.tty = (0, termios.tcgetattr(0))
        except Exception:
            self.tty = None

    def _restore_terminal(self) -> None:
        """An interactive agent stopped by a signal can leave the terminal in raw mode; put back what it was."""
        if self.tty is None:
            return
        try:
            import termios
            termios.tcsetattr(self.tty[0], termios.TCSADRAIN, self.tty[1])
        except Exception:
            pass
        self.tty = None

    def _on_signal(self, signum, _frame):
        if self.signalled:
            return  # stopping already; a second signal must not interrupt the stop
        self.signalled = True
        raise _Signalled(signum)

    def go(self) -> Result:
        previous = {}
        for sig in (signal.SIGTERM, signal.SIGHUP):
            previous[sig] = signal.signal(sig, self._on_signal)
        try:
            with ExitStack() as stack:
                try:
                    try:
                        result = self._steps(stack)
                    except _Signalled as s:
                        result = self._stopped_by(f"umwayi got {signal.Signals(s.signum).name}")
                    except KeyboardInterrupt:
                        result = self._stopped_by("umwayi was interrupted (Ctrl-C)")
                    except BaseException as e:
                        self.stop_agent()
                        self.log(f"Agent {self.agent.name} stopped: umwayi hit an unexpected error "
                                 f"({type(e).__name__})", "the agent was stopped before umwayi exited", NOT_LOGGED)
                        self._settle(None)  # a crash settles too, after the stop and before the lock is released
                        raise
                    finally:
                        self.stop_agent()  # on every path, and anything it left in its process group; before the lock is released
                except _Signalled as s:  # a signal while stopping or logging: the agent is stopped by now
                    result = self._stopped_by(f"umwayi got {signal.Signals(s.signum).name}")
                return self._settle(result)  # every way out settles the reservation, after the agent is stopped
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
            if self._old_sigint is not None:
                signal.signal(signal.SIGINT, self._old_sigint)
                self._old_sigint = None
            self._restore_terminal()

    def _stopped_by(self, what: str) -> Result:
        was_running = self.proc is not None
        self.stop_agent()
        a = self.agent
        head = what[:1].upper() + what[1:]
        if was_running:
            whom = "the agent and its descendants" if self._shares_terminal() else "the agent and its process group"
            why = self.log(f"Agent {a.name} was stopped: {what}", f"{whom} were stopped "
                           "(SIGTERM, then SIGKILL after 10 s)", NOT_LOGGED)
            return self.result(2, [f"{head}, so agent {a.name} was stopped (exit 2)."], why)
        why = self.log(f"Agent {a.name} did not start: {what}", "nothing had been started", "Nothing was started.")
        return self.result(2, [f"{head} before agent {a.name} started. Nothing was started (exit 2)."], why)

    # ------------------------------------------------------------ steps

    def _steps(self, stack: ExitStack) -> Result:
        a, root = self.agent, self.root
        not_started = f"Agent {a.name} was not started."

        # 2. the kill switch, before anything else
        st = kill.state(root)
        if kill.stopped(st):
            why = self.log(f"Agent {a.name} did not start: {kill.short(st)}",
                           "the kill switch was checked before anything else",
                           "Nothing was started. No rule was asked and no queue item was added.")
            return self.result(3, [rules.ASK, "Rule: (none)", f"Reason: {kill.reason(st)}", not_started], why)

        # 3. the rules, action agent_run, one entry through the same check as `umwayi check`
        if self.mode == LOGIN:  # 10.R12.9: its own action type, so a rule for starts never allows a sign-in
            action = {"type": "agent_login", "agent": a.name, "platform": a.platform, "transport": a.transport}
        else:
            action = {"type": "agent_run", "agent": a.name, "platform": a.platform, "mode": self.mode,
                      "transport": a.transport}
        decision, logged = rules.check_and_log(json.dumps(action), root / "rules.yaml", root, self.clock(),
                                               kill_state=st)
        verdict = [decision.answer, f"Rule: {decision.rule_id or '(none)'}", f"Reason: {decision.reason}"]
        if not logged:
            return Result(2, verdict + [f"{not_started} The logbook could not record the check, so nothing "
                                        "is started (exit 2)."])
        if decision.answer == rules.NO:
            return Result(2, verdict + [not_started])
        if decision.answer != rules.YES:
            return Result(3, verdict + [not_started, self._ask_owner()])

        # 4. the run lock
        try:
            stack.enter_context(runlock.held(root))
        except (runlock.RunLockBusy, runlock.RunLockUnavailable) as e:
            busy = isinstance(e, runlock.RunLockBusy)
            reason = runlock.BUSY_REASON if busy else runlock.unavailable_reason(e)
            short = "another umwayi run holds the run lock" if busy else "the run lock could not be taken"
            why = self.log(f"Agent {a.name} did not start: {short}", "the kill switch, the rules, then the run lock",
                           "Nothing was started.")
            return self.result(3, [rules.ASK, "Rule: (none)", f"Reason: {reason}", not_started], why)

        # 5. every gate check, again, just before the start
        gate = gate_checks(a, root, mode=self.mode)
        if self.mode == LOGIN:
            return self._login(gate, decision)
        if not gate.gated:
            why = self.log(f"Refused agent {a.name}: not gated ({gate.reason()})",
                           "the kill switch, the rules (Yes), the run lock, then the gate checks", "Nothing was started.")
            lines = [f"{'ok' if c.ok else ('no' if c.ok is False else 'not run')}: {c.name}: {c.detail}"
                     for c in gate.checks]
            lines.append(f"Refused: agent {a.name} cannot be gated, so it was not started (exit 2).")
            if gate.reason().startswith("login: ") and can_login(a):  # run and chat never sign in themselves
                lines.append(f"Run umwayi agent login {a.name} to sign in.")
            return self.result(2, lines, why)

        # 5b. Claude Code ACP chat or OpenCode chat: the private canary folder, a fresh token and the inline settings
        if self._claude_acp() or self._opencode():
            problem = self._prepare_canary(stack)
            if problem is not None:
                why = self.log(f"Refused agent {a.name}: not gated ({problem})",
                               "the kill switch, the rules (Yes), the run lock, the gate checks, then the canary",
                               "Nothing was started.")
                return self.result(2, [f"Refused: {problem}, so agent {a.name} was not started (exit 2)."], why)

        # 5c. the budget governor (B.R3.1): the logbook, units.yaml and its change entry, the limits, budget_check,
        # the telemetry receiver of a Claude Code start, then the reserve entry. The start entry comes after it.
        refused = self._reserve()
        if refused is not None:
            return refused

        # 6. the argument list, from the platform table only
        argv, stdin_text = build_argv(a, self.mode, gate.command_path, root, python_path(), prompt=self.prompt,
                                      model=self.options.model, effort=self.options.effort)

        # 7. the start entry first, then the start
        how = f"{a.platform}, {a.transport}" + (", chat" if self.mode == CHAT else "")
        why = self.log(f"Started agent {a.name} ({how}): {gate.command_path}",
                       f"rule {decision.rule_id or '(none)'} gave Yes for agent_run ({self.mode}); the run lock is held; "
                       f"every gate check passed (version {_show(gate.version)}"
                       + (f", plan: {gate.plan})" if gate.plan else ")")
                       + (f"; options: {self.options.text()}" if self.options.used else ""), NOT_LOGGED)
        if why is not None:
            return self.result(2, [f"{not_started} The logbook could not record the start, so nothing is started "
                                   "(exit 2)."], why)
        if self.mode == CHAT:
            self._queue_summary()
        try:
            self._start(argv, a.workdir, stdin_text)
        except OSError:
            why = self.log(f"Agent {a.name} could not start", "the program could not be started", "Nothing ran.")
            return self.result(2, [f"Agent {a.name} could not be started (exit 2)."], why)

        # 8. watch, 9. the end
        return self._watch()

    # ------------------------------------------------------------ the budget governor (B.R1, B.R2, B.R3)

    def _budget_log(self, added: str, checked: str, not_done: str) -> str | None:
        """One `umwayi budget` entry through the checked append. None, or why it could not be written."""
        try:
            logbook.append(self.root, budget.entry(self.clock(), added, checked, not_done))
        except UmwayiError as e:
            return str(e).rstrip(". ")
        return None

    def _reserve(self) -> Result | None:
        """The budget steps before the start entry. None when the run may start (self.budget is set), else the
        refusal. Nothing is reserved until the reserve entry is written, so a refusal here has nothing to settle."""
        a, root = self.agent, self.root
        not_started = f"Agent {a.name} was not started."
        # 1. the logbook is intact and writable (2): the ledger is read with read_checked (the whole-file hash and the
        # chain), and every entry below goes through the checked append, which refuses a logbook it cannot write.
        # 2. units.yaml (64) and the ledger (2); a change is logged before it is first used (2 if it cannot be)
        try:
            u = units.load(root, self.clock())
        except ConfigError as e:
            why = self.log(f"Refused agent {a.name}: units.yaml is not valid", "the gate checks passed, then units.yaml "
                           "was validated", "Nothing was started.")
            return self.result(64, [str(e)], why)
        cap_uu = self.options.cap_uu
        if cap_uu is not None:  # units.yaml may have changed since run_agent read it: the cap is checked again
            problem = budget.cap_problem(u, cap_uu)
            if problem is not None:
                why = self.log(f"Refused agent {a.name}: {problem}", "the gate checks passed, then --cap-uu was "
                               "checked against units.yaml", "Nothing was started.")
                return self.result(64, [f"agent: {problem}. {not_started}"], why)
        try:
            led = budget.read_ledger(root)
        except UmwayiError as e:
            return Result(2, [f"{str(e).rstrip('. ')}. {not_started} (exit 2)"])
        change = budget.pending_change(u, led)
        if change is not None:
            why = self._log_change(change)
            if why is not None:
                return Result(2, [f"units.yaml changed, but the change could not be logged ({why}), so the new values "
                                  f"are not used. {not_started} (exit 2)"])
        # 3. the reservation against per_day, per_agent_per_day and per_platform_per_day (3)
        day = self.clock()
        f = budget.fit(led, u, a.name, a.platform, day, cap_uu)
        if not f.ok:
            text = budget.refused_text(a.name, f)
            why = self.log(text, "the kill switch, the rules (Yes), the run lock, the gate checks, then the budget "
                           "limits", "Nothing was started.")
            return self.result(3, [f"{text}. {not_started} (exit 3) See umwayi budget status."], why)
        if cap_uu is not None and a.platform != "claude-code":
            # W9.R15.5: umwayi reads no cost from this platform, so the cap is only the reservation. A run whose
            # declared or worst-case reading is above the cap is refused here, before the budget_check rule.
            reading = units.reading(u, a.platform, None, True, f.need)
            if reading.micros > f.need:
                text = budget.cap_refused_text(a.name, a.platform, cap_uu, reading)
                why = self.log(text, "the kill switch, the rules (Yes), the run lock, the gate checks, the budget "
                               "limits, then the reading of this platform against the cap", "Nothing was started.")
                return self.result(3, [rules.ASK, "Rule: (none)", f"Reason: {text}", f"{not_started} (exit 3) See "
                                       "umwayi budget status."], why)
        # 4. budget_check in the rules (Yes on; No 2; Ask me first 3 with one queue item, once)
        need_uu = units.uu(f.need)
        action = {"type": "budget_check", "agent": a.name, "platform": a.platform, "reserve_uu": need_uu,
                  "left_today_uu": f.left_today_uu()}
        decision, logged = rules.check_and_log(json.dumps(action), root / "rules.yaml", root, self.clock(),
                                               kill_state=kill.state(root))
        verdict = [decision.answer, f"Rule: {decision.rule_id or '(none)'}", f"Reason: {decision.reason}"]
        if not logged:
            return Result(2, verdict + [f"{not_started} The logbook could not record the budget check, so nothing "
                                        "is started (exit 2)."])
        if decision.answer == rules.NO:
            return Result(2, verdict + [not_started])
        if decision.answer != rules.YES:
            return Result(3, verdict + [not_started, self._ask_budget(need_uu)])
        # 5. the receiver of a Claude Code start, then the reserve entry
        receiver = None
        if a.platform == "claude-code":
            receiver = telemetry.Receiver(secrets.token_hex(telemetry.SECRET_BYTES),
                                          os.environ.get(telemetry.CAPTURE_ENV) or None)
            try:
                receiver.start()
            except OSError:
                receiver.stop()
                what = ("the telemetry capture file could not be made (it must be a new file with an absolute path)"
                        if os.environ.get(telemetry.CAPTURE_ENV) else "the telemetry receiver could not start")
                why = self.log(f"Refused agent {a.name}: {what}", "the budget limits and budget_check passed, then "
                               "127.0.0.1 was asked for a free port", "Nothing was started.")
                return self.result(2, [f"Refused: {what}, so agent {a.name} was not started (exit 2)."], why)
        run = secrets.token_hex(8)
        why = self._budget_log(budget.reserve_text(run, a.name, a.platform, f.need),
                               f"the limits per_day, per_agent_per_day and per_platform_per_day fit; rule "
                               f"{decision.rule_id or '(none)'} gave Yes for budget_check",
                               "Nothing is spent until the agent runs; the rest is released when the run is settled.")
        if why is not None:
            if receiver is not None:
                receiver.stop()
            return self.result(2, [f"{not_started} The reservation could not be logged, so nothing is started "
                                   "(exit 2)."], why)
        self.budget = {"run": run, "micros": f.need, "units": u, "receiver": receiver}
        return None

    def _log_change(self, change: str) -> str | None:
        e = budget.change_entry(self.clock(), change)
        return self._budget_log(e.added, e.checked, e.not_done)

    def _ask_budget(self, need_uu: int) -> str:
        title = f"Spend up to {need_uu} UU on agent {self.agent.name}?"
        try:
            row, added = taskqueue.add_once(self.root, "decision", title, BUDGET_ASK_RECOMMENDATION, self.clock())
        except UmwayiError as e:
            return f"The queue item could not be added ({str(e).rstrip('. ')})."
        if not added:
            return f"Queue item {row.id} already asks the owner about this. Nothing was added."
        return (f"Added queue item {row.id} (decision) for the owner. Answering it does not start the agent; add a "
                "Yes rule for budget_check to allow it.")

    def _budget_report(self) -> dict | None:
        b = self.budget
        return b["receiver"].totals.report() if b and b["receiver"] is not None else None

    def _budget_tick(self):
        """While the agent runs: None, ("telemetry", why) for an invalid report (2), or ("budget",) above the cap (3)."""
        report = self._budget_report()
        if report is None:
            return None
        if report["invalid"]:
            return ("telemetry", report["invalid"])
        if units.current_micros(self.budget["units"], self.agent.platform, report) > self.budget["micros"]:
            return ("budget",)
        return None

    def _settle(self, result: Result | None) -> Result | None:
        """After the agent was stopped, on every way out: the last reports, then one settle entry (B.R1.6, B.R2.5)."""
        b = self.budget
        if b is None or b.get("settled"):
            return result
        b["settled"] = True
        self.signalled = True  # a signal now must not interrupt the settle; umwayi exits right after it
        a = self.agent
        report = None
        if b["receiver"] is not None:
            b["receiver"].drain(TELEMETRY_GRACE)  # the agent is stopped: only a report still in flight can arrive
            b["receiver"].stop()
            report = b["receiver"].totals.report()
        u = b["units"]
        reading = units.reading(u, a.platform, report, self.proc is not None, b["micros"])
        why = self._budget_log(budget.settle_text(b["run"], a.name, a.platform, b["micros"], reading, report),
                               budget.settle_checked(u, reading, report), budget.SETTLE_NOT_DONE)
        if result is None:
            return None
        lines, code = list(result.lines), result.code
        if why is not None:
            return Result(code or 2, lines + [
                f"The settle of run {b['run']} could not be logged ({why}); its reservation counts in full until "
                "umwayi budget settle-lost --by NAME" + ("." if code else " (exit 2).")])
        lines.append(f"Budget: run {b['run']} settled, {reading.tag} {units.uu(reading.micros)} UU "
                     f"({reading.micros} micros).")
        if report is not None and report["invalid"] and code == 0:
            lines.append(f"The telemetry of agent {a.name} was not valid ({report['invalid']}), so its run is settled "
                         "at the full reservation (exit 2).")
            code = 2
        return Result(code, lines)

    def _claude_acp(self) -> bool:
        """A Claude Code ACP chat (the canary, the inline settings, the ACP client). Never the sign-in."""
        return self.mode == CHAT and is_claude_acp(self.agent, self.mode)

    def _opencode(self) -> bool:
        """An OpenCode chat (the plugin's canary, the inline config, the ACP client). Run and login never get here."""
        return self.mode == CHAT and self.agent.platform == "opencode"

    def _prepare_canary(self, stack: ExitStack) -> str | None:
        """The canary of this start (10.R11.4, 10.R13.10). None, or why it cannot be prepared (then nothing starts).

        The folder is removed when the stack closes: on every way out, after the agent was stopped.
        """
        if not self._opencode():
            canary = claude_acp_path(CLAUDE_ACP_CANARY)
            if not _regular_file(canary):
                return f"the canary hook {canary} is missing, a link or not a regular file"
        python = python_path()
        if python is None:
            return "the path of the Python running umwayi is not known"
        try:
            folder = _real(_canary_folder())  # the real path: the canary refuses '..' and links are not followed
        except OSError:
            return "the private canary folder could not be made"
        stack.callback(_remove_canary_folder, folder)
        try:
            st = os.lstat(folder)
        except OSError:
            return "the private canary folder could not be made"
        if (not stat.S_ISDIR(st.st_mode) or stat.S_IMODE(st.st_mode) != 0o700 or st.st_uid != os.getuid()
                or _inside(folder, _real(str(self.root))) or _inside(folder, _real(self.agent.workdir))):
            return "the private canary folder is not a private folder outside the root and the workdir"
        token = secrets.token_hex(16)
        self.canary = (folder, token)
        if self._opencode():
            try:
                self.opencode_config = opencode_inline_config(self.agent, self.root, token, folder, python)
            except OpenCodeRefused as e:
                return str(e).rstrip(". ")
            return None
        self.meta = claude_acp_session_meta(python, self.root, folder, token)
        return None

    def _gate_ready(self) -> bool:
        """The first gate is confirmed when the canary file of this start exists. Its content is never read."""
        return self.canary is not None and os.path.exists(os.path.join(self.canary[0], self.canary[1]))

    def _opencode_ready(self) -> bool:
        """The plugin's canary is confirmed when the file in the private folder holds exactly the token of this start.

        A regular file only (no link), at most OPENCODE_CANARY_READ bytes read; a different or longer text is not it.
        """
        if self.canary is None:
            return False
        path = os.path.join(self.canary[0], OPENCODE_CANARY_NAME)
        try:
            if not stat.S_ISREG(os.lstat(path).st_mode):
                return False
            with open(path, "rb") as f:
                data = f.read(OPENCODE_CANARY_READ)
        except OSError:
            return False
        return data == self.canary[1].encode("ascii")

    def _ask_owner(self) -> str:
        if self.mode == LOGIN:
            title, recommendation = f"Log in agent {self.agent.name}?", LOGIN_ASK_RECOMMENDATION
        else:
            title, recommendation = f"Start agent {self.agent.name} ({self.mode})?", ASK_RECOMMENDATION
        try:
            row, added = taskqueue.add_once(self.root, "decision", title, recommendation, self.clock())
        except UmwayiError as e:
            return f"The queue item could not be added ({str(e).rstrip('. ')})."
        if not added:
            return f"Queue item {row.id} already asks the owner about this. Nothing was added."
        if self.mode == LOGIN:
            return (f"Added queue item {row.id} (decision) for the owner. Answering it does not start the login; "
                    "add a Yes rule for agent_login to allow it.")
        return (f"Added queue item {row.id} (decision) for the owner. Answering it does not start the agent; "
                "add a Yes rule for agent_run to allow it.")

    def _queue_lines(self) -> list:
        """The open queue in a few lines (the chat summary, and `:queue` in an ACP chat). Never raises for a bad queue."""
        try:
            rows = taskqueue.list_rows(self.root, status="open") if (self.root / taskqueue.QUEUE_NAME).exists() else []
            lines = [f"Open in the queue: {len(rows)} item(s)."]
            lines += [f"  {r.id} ({r.kind}): {_one_line(r.title, 120)}" for r in rows[:QUEUE_SUMMARY_ROWS]]
            if len(rows) > QUEUE_SUMMARY_ROWS:
                lines.append(f"  ... and {len(rows) - QUEUE_SUMMARY_ROWS} more: umwayi queue list --status open")
        except UmwayiError as e:
            lines = [f"The queue could not be read ({_one_line(str(e).rstrip('. '), 200)})."]
        return lines

    def _queue_summary(self) -> None:
        """Chat: what waits for the owner, printed before the agent starts. Never blocks the chat."""
        lines = self._queue_lines()
        if self.agent.transport == ACP:
            lines.append(f"Starting an ACP chat with agent {self.agent.name}. Every tool call it makes is checked by "
                         "the layer 9 hook, and every permission it asks for by the rules. Nothing of the "
                         "conversation is logged.")
            if self._claude_acp():
                lines.append(f"Nothing you type is sent until the hook is confirmed in the session (at most "
                             f"{acp.GATE_WAIT:.0f} s).")
            if self._opencode():
                lines.append(f"Nothing you type is sent until the plugin is confirmed in the session (at most "
                             f"{acp.GATE_WAIT:.0f} s).")
        else:
            lines.append(f"Starting a chat with agent {self.agent.name}. Every tool call it makes is checked by the "
                         "layer 9 hook. Nothing of the conversation is logged.")
        out = self.out or sys.stdout
        out.write("\n".join(lines) + "\n")
        out.flush()

    # ------------------------------------------------------------ the child

    def _start(self, argv: list, cwd: str, stdin_text: str | None) -> None:
        """The only place this module starts an agent: an argument list, no shell.

        run: its own session and process group, stdin /dev/null or the prompt.
        chat, transport cli: the owner's terminal unchanged and umwayi's process group; Ctrl-C reaches the agent only.
        chat, transport acp: its own session and process group, stdin and stdout are the ACP pipes, stderr is
        umwayi's; umwayi keeps the terminal and handles Ctrl-C itself (session/cancel).
        """
        shares_terminal = self._shares_terminal()
        if shares_terminal:
            self._save_terminal()
            self._old_sigint = signal.signal(signal.SIGINT, self._sigint_while_chatting)
        new_session = not shares_terminal
        if shares_terminal:
            stdin, stdout = None, None
        elif self.mode == CHAT:  # ACP
            stdin, stdout = subprocess.PIPE, subprocess.PIPE
        else:
            stdin, stdout = (subprocess.DEVNULL if stdin_text is None else subprocess.PIPE), None
        if self.mode == LOGIN and self.agent.platform == "claude-code":
            env = login_env(os.environ)  # the allow list plus only what a browser sign-in needs (10.R12.9)
        elif self._opencode():
            env = opencode_env(os.environ, self.opencode_config)  # the allow list of 10.R13.4 and the inline config
        elif self._claude_acp():
            env = child_env(os.environ)  # the allow list of 10.R11.9
        elif self.agent.platform == "claude-code":
            env = claude_env(os.environ)  # umwayi's environment minus the credential names (10.R12.6)
        else:
            env = kiro_env(os.environ)  # umwayi's environment minus KIRO_API_KEY (10.R12.13)
        receiver = self.budget["receiver"] if self.budget else None
        if receiver is not None:  # B.R2.2: this run's own receiver; claude_env and child_env carry no other OTEL_*
            env.update(telemetry.telemetry_env(receiver.server.server_address[1], receiver.secret))
        self.proc = subprocess.Popen(argv, cwd=cwd, shell=False, start_new_session=new_session, stdin=stdin,
                                     stdout=stdout, env=env)
        self.started = time.monotonic()
        if stdin_text is not None:
            # Written by a helper thread: a prompt bigger than the pipe buffer, sent to an agent that does not
            # read it, would otherwise block here, and the watcher (kill switch, timeout) would never run.
            threading.Thread(target=_feed, args=(self.proc.stdin, stdin_text.encode("utf-8")),
                             name="umwayi-agent-stdin", daemon=True).start()

    def _shares_terminal(self) -> bool:
        """The cli chat and the sign-in get the owner's terminal unchanged: umwayi has no pipe to them."""
        return self.mode == LOGIN or (self.mode == CHAT and self.agent.transport == CLI)

    def _group_alive(self) -> bool:
        try:
            os.killpg(self.proc.pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def _signal_group(self, sig: int) -> None:
        try:
            os.killpg(self.proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass

    def _track(self) -> None:
        """Chat: remember every descendant of the agent now running, so it can be stopped even after it is orphaned."""
        if self.proc is not None:
            self.seen.update(_descendants(self.proc.pid))

    def _stop_chat(self) -> None:
        """Chat: SIGTERM to the agent's pid and every descendant seen, SIGKILL after STOP_GRACE. Never umwayi's group."""
        p = self.proc
        if p.poll() is None:
            self._track()
        others = {pid: t for pid, t in self.seen.items() if _same_process(pid, t)}
        if p.returncode is None or others:
            for pid in ([p.pid] if p.returncode is None else []) + list(others):
                _signal_pid(pid, signal.SIGTERM)
            deadline = time.monotonic() + STOP_GRACE
            while time.monotonic() < deadline:
                p.poll()
                if p.returncode is None:
                    self._track()  # it may still start something while it stops
                others = {pid: t for pid, t in self.seen.items() if _same_process(pid, t)}
                if p.returncode is not None and not others:
                    break
                time.sleep(0.05)
            else:
                if p.poll() is None:
                    _signal_pid(p.pid, signal.SIGKILL)
                for pid, t in self.seen.items():
                    if _same_process(pid, t):
                        _signal_pid(pid, signal.SIGKILL)
        try:
            p.wait(timeout=STOP_GRACE)
        except subprocess.TimeoutExpired:
            pass

    def stop_agent(self) -> None:
        """Stop the agent and what it started: SIGTERM, then SIGKILL after STOP_GRACE. Idempotent.

        run: the agent's whole process group. chat: the agent's pid and its descendants (see _stop_chat).
        """
        p = self.proc
        if p is None:
            return
        if self._shares_terminal():
            self._stop_chat()
            return
        if self._claude_acp() or self._opencode():  # the 7b stop (design.md part 8: "the 7b stop")
            self._stop_group_and_seen()
            return
        if self.mode == CHAT and p.stdin is not None:
            # ACP: the end of its input. Not in run mode: the prompt thread may be blocked writing to a full pipe
            # and holds the pipe's lock, so a close here would wait for it; stopping the agent ends that write.
            # Never stdout: the ACP reader may be in it.
            try:
                p.stdin.close()
            except (OSError, ValueError):
                pass
        p.poll()
        if p.returncode is None or self._group_alive():
            self._signal_group(signal.SIGTERM)
            deadline = time.monotonic() + STOP_GRACE
            while time.monotonic() < deadline:
                p.poll()
                if p.returncode is not None and not self._group_alive():
                    break
                time.sleep(0.05)
            else:
                self._signal_group(signal.SIGKILL)
        try:
            p.wait(timeout=STOP_GRACE)
        except subprocess.TimeoutExpired:
            pass

    def _stop_group_and_seen(self) -> None:
        """Claude Code ACP chat (10.R11.11) and OpenCode chat (10.R13, item 8): close its stdin, then SIGTERM its process group and every descendant
        seen in /proc, SIGKILL after STOP_GRACE. Background commands outlive session/cancel and may leave the group."""
        p = self.proc
        if p.stdin is not None:
            try:
                p.stdin.close()
            except (OSError, ValueError):
                pass
        if p.poll() is None:
            self._track()

        def others() -> dict:
            return {pid: t for pid, t in self.seen.items() if _same_process(pid, t)}

        if p.returncode is None or self._group_alive() or others():
            signalled = set()
            self._signal_group(signal.SIGTERM)  # once: a program may start its cleanup again on every SIGTERM
            deadline = time.monotonic() + STOP_GRACE
            while True:
                for pid in set(others()) - signalled:  # each seen descendant once, also those seen while stopping
                    _signal_pid(pid, signal.SIGTERM)
                    signalled.add(pid)
                p.poll()
                if p.returncode is None:
                    self._track()  # it may still start something while it stops
                if p.returncode is not None and not self._group_alive() and not others():
                    break
                if time.monotonic() >= deadline:
                    self._signal_group(signal.SIGKILL)
                    for pid in others():
                        _signal_pid(pid, signal.SIGKILL)
                    break
                time.sleep(0.05)
        try:
            p.wait(timeout=STOP_GRACE)
        except subprocess.TimeoutExpired:
            pass

    def _tick(self):
        """One watcher pass. None, or why the agent must stop now: ("kill", state), ("logbook", e), ("timeout",)."""
        if self._shares_terminal() or self._claude_acp():
            self._track()
        st = kill.state(self.root)
        if kill.stopped(st):
            return ("kill", st)
        try:
            logbook.check_writable(self.root, self.clock())
        except UmwayiError as e:
            return ("logbook", e)
        token = self._budget_tick()
        if token is not None:
            return token
        limit = LOGIN_TIMEOUT if self.mode == LOGIN else self.agent.timeout_minutes * SECONDS_PER_MINUTE
        if time.monotonic() >= self.started + limit:
            return ("timeout",)
        return None

    def _tick_stop(self, token) -> Result:
        """Stop the agent for what _tick found, write the entry, give the exit code."""
        a = self.agent
        self.stop_agent()
        whom = f"the login for agent {a.name}" if self.mode == LOGIN else f"agent {a.name}"
        not_logged = LOGIN_NOT_LOGGED if self.mode == LOGIN else NOT_LOGGED
        if token[0] == "kill":
            st = token[1]
            why = self.log(f"The kill switch stopped {whom}", f"kill switch: {st}, checked every second", not_logged)
            return self.result(3, [rules.ASK, "Rule: (none)", f"Reason: {kill.reason(st)}",
                                   f"The kill switch stopped {whom} (exit 3)."], why)
        if token[0] == "logbook":
            return Result(2, [f"The logbook can no longer be written ({str(token[1]).rstrip('. ')}), so {whom} "
                              "was stopped: its checks could not be recorded (exit 2). Nothing was logged."])
        if token[0] == "budget":  # B.R1.9: the measured cost passed the per-run cap; stopped like the timeout
            cap = units.uu(self.budget["micros"])
            why = self.log(f"Agent {a.name} was stopped: it passed its budget of {cap} UU for one run",
                           "the agent's own report was checked every second against "
                           + (f"the cap of this run (--cap-uu {self.options.cap_uu})" if self.options.cap_uu is not None
                              else "limits.per_run"), NOT_LOGGED)
            return self.result(3, [f"Agent {a.name} was stopped: it passed its budget of {cap} UU for one run "
                                   "(exit 3)."], why)
        if token[0] == "telemetry":  # B.R2: a report umwayi will not count; the run is settled at the full reservation
            why = self.log(f"Agent {a.name} was stopped: its telemetry report was not valid ({token[1]})",
                           "the receiver refused to count a report of the agent's own", NOT_LOGGED)
            return self.result(2, [f"Agent {a.name} was stopped: its telemetry report was not valid ({token[1]}), so "
                                   "its run is settled at the full reservation (exit 2)."], why)
        if token[0] == "billing":  # 10.R12.8: the adapter said a subscription no longer pays
            why = self.log(f"Agent {a.name} was stopped: the Claude Code login changed and a subscription no longer "
                           "pays", "the adapter's _auth/status_update named another payer; the adapter and every "
                           "seen descendant were stopped", NOT_LOGGED)
            return self.result(2, [f"The Claude Code login changed and a subscription no longer pays, so agent "
                                   f"{a.name} was stopped (exit 2)."], why)
        if self.mode == LOGIN:
            minutes = f"{LOGIN_TIMEOUT / 60:g} min"
            why = self.log(f"The login for agent {a.name} was stopped after its limit of {minutes}",
                           "the fixed limit of a sign-in was reached", not_logged)
            return self.result(2, [f"The login for agent {a.name} was stopped after its limit of {minutes} (exit 2)."],
                               why)
        why = self.log(f"Agent {a.name} stopped after its timeout of {a.timeout_minutes} min",
                       "the timeout from agents.yaml was reached", NOT_LOGGED)
        return self.result(2, [f"Agent {a.name} was stopped after its timeout of {a.timeout_minutes} min (exit 2)."],
                           why)

    def _watch(self) -> Result:
        if self.mode == CHAT and self.agent.transport == ACP:
            return self._acp_chat()
        while True:
            try:
                code = self.proc.wait(timeout=WATCH_INTERVAL)
                break
            except subprocess.TimeoutExpired:
                pass
            token = self._tick()
            if token is not None:
                return self._tick_stop(token)
        return self._end(code)

    # ------------------------------------------------------------ the sign-in (part 7c-2, 10.R12.9)

    def _ok_text(self, plan: str | None) -> str:
        return f"Claude subscription OK (plan: {plan})" if self.agent.platform == "claude-code" else "Kiro login OK"

    def _login(self, gate: Gate, decision) -> Result:
        """`umwayi agent login`: the checks before the login check must pass; then the login check decides whether
        a sign-in is needed at all; then the sign-in on the owner's terminal, watched like a cli chat."""
        a = self.agent
        lines = [f"{'ok' if c.ok else ('no' if c.ok is False else 'not run')}: {c.name}: {c.detail}"
                 for c in gate.checks]
        login = next((c for c in gate.checks if c.name == "login"), None)
        if login is None or not all(c.ok for c in gate.checks if c.name != "login"):
            why = self.log(f"Refused login for agent {a.name}: not gated ({gate.reason()})",
                           "the kill switch, the rules (Yes), the run lock, then the gate checks before the login",
                           "Nothing was started.")
            return self.result(2, lines + [f"Refused: the login for agent {a.name} cannot be started (exit 2). "
                                           "Nothing was started."], why)
        if login.ok:
            ok = self._ok_text(gate.plan)
            why = self.log(f"Login for agent {a.name} not needed: {ok}", "the login check passed before any sign-in",
                           "Nothing was started.")
            return self.result(0, [f"{ok}. Nothing was started."], why)
        self.gate = gate
        argv, _ = build_argv(a, LOGIN, gate.command_path, self.root, python_path())
        how = "claude.ai" if a.platform == "claude-code" else "kiro-cli login"
        why = self.log(f"Started login for agent {a.name} ({how})",
                       f"rule {decision.rule_id or '(none)'} gave Yes for agent_login; the run lock is held; every gate "
                       f"check before the login passed; the login check found: {login.detail}", LOGIN_NOT_LOGGED)
        if why is not None:
            return self.result(2, [f"The logbook could not record the start of the login for agent {a.name}, so "
                                   "nothing is started (exit 2)."], why)
        try:
            self._start(argv, a.workdir, None)
        except OSError:
            why = self.log(f"The login for agent {a.name} could not start", "the program could not be started",
                           "Nothing ran.")
            return self.result(2, [f"The login for agent {a.name} could not be started (exit 2)."], why)
        return self._watch()

    def _login_end(self, code: int) -> Result:
        """The sign-in exited, whatever its code: the login check runs again with the agent's start environment."""
        a, gate = self.agent, Gate()
        done = _recorder(gate, ["login"])
        if a.platform == "claude-code":
            node = self.gate.command_path
            _login_gate(probe_argv(node, claude_acp_path(CLAUDE_ACP_ADAPTER), "login"), a.workdir,
                        child_env(os.environ), gate, done)
        else:
            _kiro_login_gate(self.gate.command_path, a.workdir, kiro_env(os.environ), done)
        check = gate.checks[0]
        if check.ok:
            ok = self._ok_text(gate.plan)
            short = f"subscription OK (plan: {gate.plan})" if a.platform == "claude-code" else "Kiro login OK"
            why = self.log(f"Login for agent {a.name} ended: {short}",
                           f"the login exited {_exit_text(code)}; then the login check passed", LOGIN_NOT_LOGGED)
            return self.result(0, [f"{ok}."], why)
        why = self.log(f"Login for agent {a.name} ended: not gated (login: {check.detail})",
                       f"the login exited {_exit_text(code)}; then the login check failed", LOGIN_NOT_LOGGED)
        return self.result(2, [f"Refused: login: {check.detail} (exit 2)."], why)

    # ------------------------------------------------------------ ACP chat (part 6)

    def _permission(self, tool_call: dict) -> str:
        """An ACP permission request, asked of the rules like `umwayi check` (one logbook entry).

        The action never holds the agent-written title. While the kill switch is on (or unknown) the
        answer is No. A check that could not be logged, or any error, is a reject.
        """
        action = permission_action(self.agent.name, tool_call, self.agent.platform)
        try:
            st = kill.state(self.root)
            stop = kill.reason(st) if kill.stopped(st) else None
            decision, logged = rules.check_and_log(json.dumps(action), self.root / "rules.yaml", self.root,
                                                   self.clock(), kill_state=st, stop_reason=stop)
        except Exception:
            return acp.REJECT
        if not logged:
            return acp.REJECT
        verdict = permission_verdict(decision.answer)
        if verdict == acp.ALLOW and self.agent.platform == "opencode" and not _has_tool_name(tool_call):
            return acp.ASK  # 10.R13.9: OpenCode had no tool for the request, so no rule is trusted to say Yes
        return verdict

    def _acp_chat(self) -> Result:
        a = self.agent
        claude = self._claude_acp()  # Kiro: no _meta, no waiting, no session/set_mode
        opencode = self._opencode()  # OpenCode: no _meta, waits for the canary, checks the model, no set_mode
        chat = acp.Chat(self.proc, out=self.out or sys.stdout, owner=_owner_input(), workdir=a.workdir,
                        permission=self._permission, tick=self._tick, queue_lines=self._queue_lines,
                        client_version=__version__, tick_interval=WATCH_INTERVAL,
                        session_meta=self.meta if claude else None, gate_ready=(self._gate_ready if claude else self._opencode_ready if opencode else None),
                        set_mode=CLAUDE_ACP_MODE if claude else None, on_auth=_billing_watch if claude else None,
                        expect_model=a.model if opencode else None, sign_in=OPENCODE_SIGN_IN if opencode else None)
        # Ctrl-C belongs to umwayi here (the agent is in its own session): it cancels the turn, never kills umwayi
        self._old_sigint = signal.signal(signal.SIGINT, lambda _s, _f: chat.interrupt())
        outcome = chat.run()
        if outcome[0] == "stopped":
            return self._tick_stop(outcome[1])
        if outcome[0] == "failed":
            self.stop_agent()
            if outcome[1] == acp.GATE_NOT_CONFIRMED:
                why = self.log(f"Refused agent {a.name}: {outcome[1]}", "the canary did not run in the session "
                               f"within {acp.GATE_WAIT:.0f} s of session/new; the agent was stopped",
                               "No prompt was sent.")
            else:
                why = self.log(f"ACP chat with agent {a.name} ended: {outcome[1]}", "the agent was stopped", NOT_LOGGED)
            return self.result(2, list(outcome[2]), why)
        # the owner ended it (:quit or the end of input): the agent gets the end of its stdin and should exit
        if claude or opencode:
            self._track()  # what it started, before its exit orphans it
        try:
            self.proc.stdin.close()
        except (OSError, ValueError):
            pass
        try:
            code = self.proc.wait(timeout=STOP_GRACE)
        except subprocess.TimeoutExpired:
            self.stop_agent()
            why = self.log(f"Agent {a.name} did not exit within {STOP_GRACE:.0f} s after the chat ended",
                           "the agent was stopped (SIGTERM, then SIGKILL after 10 s)", NOT_LOGGED)
            return self.result(2, [f"Agent {a.name} did not exit after the chat ended, so it was stopped (exit 2)."],
                               why)
        return self._end(code)

    def _end(self, code: int) -> Result:
        if self.mode == LOGIN:
            return self._login_end(code)
        a = self.agent
        seconds = round(time.monotonic() - self.started)
        why = self.log(f"Agent {a.name} exited {_exit_text(code)} after {seconds} s",
                       "the agent ran with every tool call checked by the layer 9 hook", NOT_LOGGED)
        if why is not None:
            return self.result(2, [f"Agent {a.name} exited {_exit_text(code)}, but the end could not be logged "
                                   "(exit 2)."], why)
        if code != 0:
            return Result(2, [f"Agent {a.name} exited {_exit_text(code)} (exit 2)."])
        return Result(0, [f"Agent {a.name} finished (exit 0) after {seconds} s."])


_PLAIN_KIND = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_PLAIN_TOOL = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")


def permission_action(agent_name: str, tool_call, platform: str) -> dict:
    """The action for an ACP permission request. kind and tool only when they are short plain words.

    platform is the agent's (kiro or claude-code). The title is written by the agent (ACP says not
    to approve on it), so it is never in the action.
    """
    if platform not in PLATFORMS:
        raise UsageError("agent: unknown platform")
    action = {"type": "acp_permission", "agent": agent_name, "platform": platform}
    if isinstance(tool_call, dict):
        kind, tool = tool_call.get("kind"), tool_call.get("name")
        if isinstance(kind, str) and _PLAIN_KIND.match(kind):
            action["kind"] = kind
        if isinstance(tool, str) and _PLAIN_TOOL.match(tool):
            action["tool"] = tool
    return action


def _has_tool_name(tool_call) -> bool:
    """True if the permission request names its tool (a non-empty text `name`)."""
    return isinstance(tool_call, dict) and isinstance(tool_call.get("name"), str) and bool(tool_call["name"])


def permission_verdict(answer) -> str:
    """Yes is allow, Ask me first is ask the owner, No and anything else are reject."""
    if answer == rules.YES:
        return acp.ALLOW
    if answer == rules.ASK:
        return acp.ASK
    return acp.REJECT


def _billing_watch(kind: str):
    """A Claude Code ACP chat goes on only while the adapter says a subscription pays (10.R12.8, kind "account")."""
    return None if kind == "account" else ("billing",)


def _owner_input():
    """The owner's input: the file descriptor of stdin, read raw by umwayi.acp."""
    return sys.stdin.fileno()


def _opencode_chat_only(agent: Agent, command: str) -> None:
    """`agent run` and `agent login` are never offered for OpenCode (10.R13.1): a usage error (64), before the
    kill switch, the rules or the logbook, so nothing is written and nothing is started."""
    if agent.platform == "opencode":
        raise UsageError(f"{command}: only 'umwayi agent chat' is offered for OpenCode agents. Nothing was started.")


def chat_agent(root, name: str, clock, given: str | None = None, out=None) -> Result:
    """`umwayi agent chat NAME`: the same steps as run, then the owner's terminal (transport cli, part 5)
    or umwayi's own ACP client (transport acp: part 6 for Kiro, part 7 for Claude Code through the pinned
    adapter, with the inline settings and the canary)."""
    root = _root(root)
    agent = find(load(root, given), name)
    if agent.platform not in PLATFORMS:
        raise UsageError("agent: unknown platform. Nothing was started.")
    if agent.transport == ACP and agent.platform not in ("kiro", "claude-code", "opencode"):
        raise UsageError("agent: ACP chat is only for platforms kiro, claude-code and opencode. Nothing was started.")
    return _Run(root, agent, None, clock, mode=CHAT, out=out).go()


def login_agent(root, name: str, clock, given: str | None = None) -> Result:
    """`umwayi agent login NAME` (10.R12.9, 10.R12.13): the claude.ai sign-in of a Claude Code ACP agent, or
    `kiro-cli login` for a Kiro agent, on the owner's terminal; then the login check. 0, 2, 3 or 64."""
    root = _root(root)
    agent = find(load(root, given), name)
    _opencode_chat_only(agent, "agent login")
    if not can_login(agent):
        raise UsageError(LOGIN_ONLY)
    return _Run(root, agent, None, clock, mode=LOGIN).go()


def run_agent(root, name: str, prompt: str, clock, given: str | None = None, cap_uu: str | None = None,
              model: str | None = None, effort: str | None = None) -> Result:
    """`umwayi agent run NAME`, for Claude Code (part 3) and Kiro (part 4). The same steps for both.

    cap_uu, model and effort (W9.6) are the text of the options; none given means the run is as it was before."""
    root = _root(root)
    agent = find(load(root, given), name)
    _opencode_chat_only(agent, "agent run")
    if agent.platform not in PLATFORMS:
        raise UsageError("agent: unknown platform. Nothing was started.")
    prompt = check_prompt(prompt, agent.platform)
    options = check_options(agent, cap_uu, model, effort)
    if options.cap_uu is not None:  # above limits.per_run is 64, before the kill switch, the rules or the logbook
        try:
            problem = budget.cap_problem(units.load(root, clock()), options.cap_uu)
        except ConfigError:
            problem = None  # an invalid units.yaml is refused (64, one entry) by the run itself
        if problem is not None:
            raise UsageError(f"agent: {problem}. Nothing was started.")
    return _Run(root, agent, prompt, clock, options=options).go()
