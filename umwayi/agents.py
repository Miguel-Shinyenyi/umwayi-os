"""Layer 10, parts 1 and 2: agents.yaml, the gate checks and the argument lists.

    umwayi agent validate [--agents PATH]     every problem with a line number: 0 or 64
    umwayi agent list [--agents PATH]         the agents in the file: 0 or 64
    umwayi agent check NAME [--agents PATH]   can NAME be gated? 0 yes, 2 no, 64 usage

No agent is started by this module. The gate checks run two short programs: the
agent's own version command (`claude -v`, `kiro-cli --version`) and the layer 9
hook script with a self-test event that every hook blocks before it reads a rule.
Both run with an argument list, never a shell, with a timeout and stdin given.

The argument lists the front door will use (parts 3 to 5) are built here, from the
fixed platform table and the validated fields only. Nothing from agents.yaml is
pasted into a string, and no list may hold a flag on FORBIDDEN_FLAGS.

The core knows where the layer 9 hook scripts are, but never imports `adapters`.
See design.md (layer 10) and adapters/NOTES-layer10.md.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from umwayi import kill, miniyaml
from umwayi.errors import ConfigError, UsageError

AGENTS_FILE = "agents.yaml"
MAX_FILE_BYTES = 64 * 1024
MAX_AGENTS = 50
MAX_PATH = 1024
MAX_PROMPT_BYTES = 100 * 1024
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
    "claude-code": Platform("claude-code", ("claude",), ("cli",), "adapters/claude_code/hook.py",
                            (2, 1, 295), "-v", "onFailure: block needs Claude Code 2.1.295 or later"),
    "kiro": Platform("kiro", ("kiro-cli",), ("cli", "acp"), "adapters/kiro/hook.py",
                     (2, 27, 1), "--version", "V3 headless runs load hooks from Kiro CLI 2.27.1"),
}

# The built-in Kiro tool IDs the Kiro hook docs name (adapters/NOTES.md). Nothing else may be trusted.
KIRO_TOOL_IDS = ("read_file", "grep_search", "execute_bash", "execute_pwsh",
                 "fs_write", "fs_append", "str_replace", "delete_file")

# Never in an argument list (requirements 10.R5.7). Checked on every list that is built.
FORBIDDEN_FLAGS = ("--bare", "--dangerously-skip-permissions", "--allow-dangerously-skip-permissions",
                   "--setting-sources", "--trust-all-tools", "--cloud", "--bg")
FORBIDDEN_TEXT = ("bypassPermissions",)

KEYS = ("name", "platform", "command", "transport", "workdir", "kiro_agent", "trust_tools",
        "max_turns", "timeout_minutes")
REQUIRED = ("name", "platform", "command", "workdir")
RUN, CHAT = "run", "chat"
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
        transport = item.get("transport", CLI)
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
        if len(problems) == before:
            parsed.append(Agent(name, pname, cmd, transport, item["workdir"], kiro_agent,
                                tuple(tools) if isinstance(tools, list) else (), max_turns, timeout, line("agents", i)))
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


def claude_settings(python: str, hook: Path, root: Path) -> str:
    """The --settings JSON for Claude Code, from a fixed template (design.md, layer 10)."""
    settings = {
        "disableAllHooks": False,
        "hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{
            "type": "command", "command": python, "args": [str(hook), "--root", str(root)],
            "timeout": CLAUDE_HOOK_TIMEOUT, "onFailure": "block",
        }]}]},
    }
    return json.dumps(settings, separators=(",", ":"))


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
    return argv


def build_argv(agent: Agent, mode: str, command_path: str, root: Path, python: str,
               prompt: str | None = None, src: Path | None = None) -> tuple:
    """(argument list, stdin text or None). The only place an agent's command line is made."""
    if mode not in (RUN, CHAT):
        raise UsageError("agent: the mode must be run or chat")
    root = Path(root)
    if agent.platform == "claude-code":
        settings = claude_settings(python, hook_path("claude-code", src), root)
        if mode == RUN:
            argv = [command_path, "-p", "--permission-mode", "default", "--settings", settings]
            if agent.max_turns is not None:
                argv += ["--max-turns", str(agent.max_turns)]
            argv.append(check_prompt(prompt, agent.platform))
            return _assert_allowed(argv, skip=len(argv) - 1), None
        return _assert_allowed([command_path, "--permission-mode", "default", "--settings", settings]), None
    if agent.platform == "kiro":
        if mode == RUN:
            argv = [command_path, "chat", "--v3", "--no-interactive"]
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

    @property
    def gated(self) -> bool:
        return bool(self.checks) and all(c.ok for c in self.checks)

    def reason(self) -> str:
        for c in self.checks:
            if not c.ok:
                return f"{c.name}: {c.detail}"
        return ""


def _run_child(argv: list, stdin: bytes, timeout: float, cwd: str) -> tuple:
    """(exit code or None, stdout bytes). The only place this module starts a program.

    None means it could not start or did not finish in time (it is then killed).
    """
    try:
        proc = subprocess.run(argv, input=stdin, capture_output=True, timeout=timeout, cwd=cwd,
                              shell=False, check=False)
    except subprocess.TimeoutExpired:
        return None, b""
    except (OSError, ValueError):
        return None, b""
    return proc.returncode, proc.stdout


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


def gate_checks(agent: Agent, root, src: Path | None = None, home: Path | None = None) -> Gate:
    """Every check from 10.R6.1, in order. The first that fails ends it; the rest are 'not run'."""
    root = _root(root)
    plat = PLATFORMS[agent.platform]
    gate = Gate()
    order = ["command", "version", "hook script", "hook self-test"] + (["kiro hook file"] if agent.platform == "kiro" else [])

    def done(name: str, ok: bool, detail: str) -> bool:
        gate.checks.append(Check(name, ok, detail))
        if not ok:
            for rest in order[order.index(name) + 1:]:
                gate.checks.append(Check(rest, None, "an earlier check failed"))
        return ok

    found = shutil.which(agent.command)
    if not found or not os.path.isabs(found):
        done("command", False, f"{agent.command} was not found on PATH")
        return gate
    gate.command_path = found
    done("command", True, f"{agent.command} found at {found}")

    code, out = _run_child([found, plat.version_flag], b"", VERSION_TIMEOUT, agent.workdir)
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

    hook = hook_path(agent.platform, src)
    try:
        hst = os.lstat(hook)
        hook_ok = stat.S_ISREG(hst.st_mode)
    except OSError:
        hook_ok = False
    if not done("hook script", hook_ok, f"{hook}" + ("" if hook_ok else " is missing or not a regular file")):
        return gate

    python = python_path()
    if python is None:
        done("hook self-test", False, "the path of the Python running umwayi is not known")
        return gate
    code, _ = _run_child([python, str(hook), "--root", str(root)], SELFTEST_INPUT, SELFTEST_TIMEOUT, str(root))
    if code != SELFTEST_EXIT:
        what = f"did not answer within {SELFTEST_TIMEOUT:.0f} s or could not start" if code is None else f"exited {code}"
        done("hook self-test", False, f"the hook {what}; it must block the self-test event with exit {SELFTEST_EXIT}")
        return gate
    done("hook self-test", True, f"the hook started and blocked the self-test event (exit {SELFTEST_EXIT})")

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
    st = kill.state(root)
    lines.append(f"kill switch: {st}" + ("" if st == kill.OFF else " (a start would stop now with exit 3)"))
    for c in gate.checks:
        mark = "ok" if c.ok else ("no" if c.ok is False else "not run")
        lines.append(f"{mark}: {c.name}: {c.detail}")
    if not gate.gated:
        lines.append(f"Not gated: agent {agent.name} would be refused (exit 2). Nothing was started.")
        return Result(2, lines)
    python = python_path()
    modes = [RUN, CHAT]
    for mode in modes:
        argv, stdin = build_argv(agent, mode, gate.command_path, root, python,
                                 prompt="PROMPT" if mode == RUN else None)
        shown = json.dumps(argv)
        lines.append(f"{mode} would start: {shown}" + (" with the prompt on stdin" if stdin is not None else ""))
    lines.append(f"Gated: agent {agent.name} can be started. Nothing was started.")
    return Result(0, lines)
