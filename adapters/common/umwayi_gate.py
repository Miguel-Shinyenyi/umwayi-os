"""Shared adapter code (layer 9): a platform tool call in, an allow, deny or ask out.

Three steps, used by every adapter:

  1. tool_action(): turn one tool call into the action JSON that `umwayi check` reads.
  2. run_check():   run `umwayi check - --json` as a child process, with a timeout.
  3. decide():      turn what the child said into "allow", "deny" or "ask".

Fail closed: "allow" only for exit 0 with a well formed JSON answer of Yes,
rules_ok true and kill_switch "off". "ask" only for exit 3 with a well formed
answer of Ask me first, rules_ok true and kill_switch "off". Everything else,
including a timeout, bad output, a child that cannot start, the kill switch
being on or unknown, or any exception, is "deny".

The kill switch is checked twice: `umwayi check --kill-switch` answers No while
it is on (and logs that), and decide() refuses anything whose kill_switch field
is not "off".

This module is standard library only, and it never imports the umwayi package:
umwayi runs as a separate process, so a crash on either side cannot turn into
an allow. The core umwayi package never imports adapters either.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ALLOW, DENY, ASK = "allow", "deny", "ask"
MAX_INPUT_BYTES = 1_000_000  # the hook input we are willing to read
DEFAULT_TIMEOUT = 10.0  # seconds for the umwayi check child
MAX_OUTPUT_BYTES = 64 * 1024  # what we read back from the child

_TYPE_PART = re.compile(r"[^a-z0-9]+")
_PLAIN = re.compile(r"^[A-Za-z0-9_.:@/-]{1,64}$")
MAX_TYPE_NAME = 35  # "tool_" + 35 = 40, the longest type umwayi logs

# The fields copied from tool_input into the action, per tool. Only strings are
# copied. Nothing else from tool_input (file contents, edit text, prompts) is sent.
FIELDS = {
    "bash": {"command": "command"},
    "powershell": {"command": "command"},
    "write": {"file_path": "path"},
    "edit": {"file_path": "path"},
    "multiedit": {"file_path": "path"},
    "read": {"file_path": "path"},
    "notebookedit": {"notebook_path": "path"},
    "glob": {"pattern": "pattern", "path": "path"},
    "grep": {"pattern": "pattern", "path": "path"},
    "webfetch": {"url": "url"},
    "websearch": {"query": "query"},
    "agent": {"subagent_type": "subagent_type"},
}


class AdapterError(Exception):
    """The input could not be read safely. The adapter blocks."""


@dataclass(frozen=True)
class CheckResult:
    exit_code: int | None  # None: the child did not finish (timeout, could not start)
    data: dict | None  # the parsed --json output, or None
    problem: str | None  # why the result cannot be trusted, if it cannot


@dataclass(frozen=True)
class Verdict:
    decision: str  # ALLOW, DENY or ASK
    reason: str  # one line, safe to show; never holds the tool input


# ------------------------------------------------------------ 1. the action


def type_for(tool_name: str) -> str:
    """The umwayi action type for a tool name: tool_bash, tool_write, tool_mcp, ...

    MCP tools (Claude Code names them mcp__SERVER__TOOL) all get tool_mcp, with
    the server and tool as fields. A name too long for a type gets tool_long_name,
    which no starter rule allows, so it is Ask me first.
    """
    if tool_name.startswith("mcp__"):
        return "tool_mcp"
    part = _TYPE_PART.sub("_", tool_name.lower()).strip("_")
    if not part:
        return "tool_unknown"
    if len(part) > MAX_TYPE_NAME:
        return "tool_long_name"
    return f"tool_{part}"


def tool_action(platform: str, tool_name, tool_input, extra: dict | None = None) -> dict:
    """The action JSON for one tool call."""
    if not isinstance(tool_name, str) or not tool_name.strip() or len(tool_name) > 200:
        raise AdapterError("the hook input has no usable tool_name")
    if not isinstance(tool_input, dict):
        raise AdapterError("the hook input has no tool_input object")
    action = {"type": type_for(tool_name), "platform": platform, "tool": tool_name}
    if tool_name.startswith("mcp__"):
        parts = tool_name.split("__")
        if len(parts) >= 3:
            action["mcp_server"] = parts[1]
            action["mcp_tool"] = "__".join(parts[2:])
    key = _TYPE_PART.sub("", tool_name.lower())
    for src, dst in FIELDS.get(key, {}).items():
        value = tool_input.get(src)
        if isinstance(value, str):
            action[dst] = value  # never cut: a too large action is refused by umwayi check
    for k, v in (extra or {}).items():
        if isinstance(v, str) and _PLAIN.match(v):
            action[k] = v
    return action


# ------------------------------------------------------- 2. umwayi check


def umwayi_command(root: Path, python: str | None = None) -> list:
    return [python or sys.executable, "-m", "umwayi", "--root", str(root)]


def check_command(root: Path, python: str | None = None) -> list:
    return umwayi_command(root, python) + ["check", "-", "--json", "--kill-switch"]


def _child_env(umwayi_src: Path | None) -> dict:
    env = dict(os.environ)
    if umwayi_src is not None:
        env["PYTHONPATH"] = os.pathsep.join([str(umwayi_src)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    return env


def run_check(action: dict, root: Path, umwayi_src: Path | None = None,
              timeout: float = DEFAULT_TIMEOUT, python: str | None = None) -> CheckResult:
    """Run `umwayi check - --json --kill-switch` with the action on stdin. Never raises for a child problem."""
    env = _child_env(umwayi_src)
    try:
        proc = subprocess.run(
            check_command(root, python),
            input=json.dumps(action).encode("utf-8"),
            capture_output=True,
            timeout=timeout,
            env=env,
            cwd=str(root),
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CheckResult(None, None, f"umwayi check did not answer within {timeout:g} seconds")
    except OSError:
        return CheckResult(None, None, "umwayi check could not be started")
    if len(proc.stdout) > MAX_OUTPUT_BYTES:
        return CheckResult(proc.returncode, None, "umwayi check printed more than expected")
    try:
        data = json.loads(proc.stdout.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return CheckResult(proc.returncode, None, f"umwayi check gave no JSON answer (exit {proc.returncode})")
    if not isinstance(data, dict):
        return CheckResult(proc.returncode, None, "umwayi check gave an answer that is not a JSON object")
    return CheckResult(proc.returncode, data, None)


# ----------------------------------------------------------- 3. the verdict


def _rule(data: dict) -> str:
    rid = data.get("rule_id")
    return f"rule {rid}" if isinstance(rid, str) and _PLAIN.match(rid) else "no rule"


def _text(data: dict) -> str:
    r = data.get("reason")
    if not isinstance(r, str):
        return ""
    r = " ".join(r.split())
    return r if len(r) <= 300 else r[:297] + "..."


def decide(result: CheckResult) -> Verdict:
    """Exit 0 allow, exit 2 deny, exit 3 ask; anything else is deny. Fail closed at every step."""
    if result.problem is not None or result.data is None:
        return Verdict(DENY, f"umwayi: blocked, {result.problem or 'no answer'}.")
    data, code = result.data, result.exit_code
    answer = data.get("answer")
    who = _rule(data)
    text = _text(data)
    if data.get("kill_switch") != "off":
        return Verdict(DENY, f"umwayi: blocked, the kill switch is on or its state cannot be read. {text}".strip())
    if data.get("rules_ok") is not True:
        return Verdict(DENY, f"umwayi: blocked, rules.yaml could not be used. {text}".strip())
    if code == 2 or answer == "No":
        return Verdict(DENY, f"umwayi: No ({who}). {text}".strip())
    if code == 0 and answer == "Yes":
        return Verdict(ALLOW, f"umwayi: Yes ({who}). {text}".strip())
    if code == 3 and answer == "Ask me first":
        return Verdict(ASK, f"umwayi: Ask me first ({who}). {text}".strip())
    return Verdict(DENY, f"umwayi: blocked, unexpected answer (exit {code}).")


# ------------------------------------------------------------- input


def read_hook_input(stream) -> dict:
    """Read one JSON object from a binary stream, with a size limit."""
    raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise AdapterError("the hook input is larger than the adapter reads")
    if not raw.strip():
        raise AdapterError("the hook input is empty")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise AdapterError("the hook input is not valid JSON") from None
    if not isinstance(data, dict):
        raise AdapterError("the hook input is not a JSON object")
    return data


def find_umwayi_src(start: Path) -> Path | None:
    """The folder that holds the umwayi package, if the adapter sits inside an umwayi-os checkout."""
    for parent in [start, *start.parents]:
        if (parent / "umwayi" / "__init__.py").is_file():
            return parent
    return None


# --------------------------------------------- shared by Kiro and generic


_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,39}$")
_NAME = re.compile(r"^[a-z][a-z0-9-]{0,19}$")


def generic_action(platform: str, tool_name, tool_input) -> dict:
    """The action for a platform whose tool_input fields are not documented (Kiro) or not known (generic).

    Every top level string field of tool_input with a plain key is sent as input_<key>,
    for example tool_input {"command": "ls"} becomes "input_command": "ls". The prefix
    means a field can never replace type, platform or tool. Nothing is cut.
    """
    if not isinstance(tool_name, str) or not tool_name.strip() or len(tool_name) > 200:
        raise AdapterError("the hook input has no usable tool_name")
    if not isinstance(tool_input, dict):
        raise AdapterError("the hook input has no tool_input object")
    part = _TYPE_PART.sub("_", tool_name.lower()).strip("_")
    action = {"type": "tool_unknown" if not part else ("tool_long_name" if len(part) > MAX_TYPE_NAME else f"tool_{part}"),
              "platform": platform, "tool": tool_name}
    for key, value in tool_input.items():
        if isinstance(key, str) and _KEY.match(key) and isinstance(value, str):
            action[f"input_{key}"] = value
    return action


def check_platform_name(name: str) -> str:
    if not isinstance(name, str) or not _NAME.match(name):
        raise AdapterError("--platform must be lowercase letters, digits and '-' (up to 20)")
    return name


def add_queue_item(root: Path, title: str, recommendation: str, umwayi_src: Path | None = None,
                   timeout: float = 5.0, python: str | None = None) -> tuple[bool, str]:
    """Ask me first on a platform with no ask: one open decision for the owner, never two.

    Runs `umwayi queue add --kind decision --if-not-open`. Returns (ok, the line umwayi printed or why not).
    """
    try:
        proc = subprocess.run(
            umwayi_command(root, python) + ["queue", "add", "--kind", "decision", title,
                                            "--recommendation", recommendation, "--if-not-open"],
            capture_output=True, timeout=timeout, env=_child_env(umwayi_src), cwd=str(root),
            shell=False, check=False, stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return False, "the queue item could not be added in time"
    except OSError:
        return False, "the queue item could not be added (umwayi could not be started)"
    line = proc.stdout.decode("utf-8", "replace").strip().splitlines()[:1]
    if proc.returncode != 0 or not line:
        return False, f"the queue item could not be added (exit {proc.returncode})"
    return True, line[0][:200]


def ask_title(platform_label: str, action: dict) -> str:
    return f"{platform_label} asks first: may it do {action['type']}?"


def ask_recommendation(platform_label: str, verdict: Verdict, action: dict) -> str:
    text = (f"{platform_label} has no ask answer, so umwayi denied this call ({verdict.reason}). "
            f"To allow calls like it, add a Yes rule for type {action['type']} in rules.yaml. "
            "Answering this item does not allow the call.")
    return text.replace("|", "/")[:500]


def parse_args(argv: list, extra_flags: tuple = (), extra_switches: tuple = ()) -> dict:
    """--root DIR (required), --umwayi-src DIR, --timeout SECONDS, plus the adapter's own flags.

    Raises AdapterError for anything unknown or incomplete: the adapter blocks.
    """
    args, out = list(argv), {"timeout": DEFAULT_TIMEOUT}
    flags = ("--root", "--umwayi-src", "--timeout") + tuple(extra_flags)
    while args:
        flag = args.pop(0)
        if flag in extra_switches:
            out[flag] = True
            continue
        if flag not in flags or not args:
            raise AdapterError(f"unknown or incomplete argument {flag[:40]!r}")
        value = args.pop(0)
        if flag == "--timeout":
            try:
                out["timeout"] = float(value)
            except ValueError:
                raise AdapterError("--timeout must be a number of seconds") from None
            if not 0 < out["timeout"] <= 600:
                raise AdapterError("--timeout must be from 0 to 600 seconds")
        else:
            out[flag] = value
    if "--root" not in out:
        raise AdapterError("--root is required (the umwayi folder with rules.yaml)")
    root = Path(out["--root"])
    if not root.is_dir():
        raise AdapterError("the --root folder does not exist")
    out["root"] = root.resolve()
    out["umwayi_src"] = Path(out["--umwayi-src"]) if "--umwayi-src" in out else None
    return out
