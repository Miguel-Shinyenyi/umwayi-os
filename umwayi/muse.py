"""M2, the first part: the Muse route as pure functions, tested with a fake only. Nothing here starts a process.

`muse exec` is Meta's Muse Code in headless mode. This module builds its command line, scrubs the child environment, writes the text of
`.muse/hooks.json` and checks the facts a run needs. It refuses with the fixed words of docs/muse-route-design.md. It never starts
`muse`: the start goes through the process path of umwayi/agents.py in a later part (an owner stop of its own, with a fake `muse` script).

What it enforces and what it does not: it builds a command that always carries `--max-model-steps` and `--contributor-mode off` and that never
carries `--yolo` or `--disable-sandbox`. It does not confirm Muse's own sandbox (no read-only command says whether it is on: the design note,
M3), so it refuses `--disable-approval`. The label until W40 shows a real enforced run: cooperative, plus Muse's own sandbox. The format of
`.muse/hooks.json` below is assumed to be the one of Claude Code hooks and is NOT confirmed against a real Muse until M3.

Content sent to Muse on free credits may be used by Meta for product improvement (owner's acceptance, D-93): public umwayi-os work only.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from umwayi import fsutil

MUSE_MISSING = "muse_missing"
HOOK_FILE_MISSING = "hook_file_missing"
KEY_VARIABLE_FOUND = "key_variable_found"
PRIVATE_REPO_NAMED = "private_repo_named"
YOLO_REFUSED = "yolo_refused"
SANDBOX_UNCONFIRMED = "sandbox_unconfirmed"  # new word: --disable-approval is refused until M3 can confirm the sandbox
STEP_CAP_MISSING = "step_cap_missing"  # new word: a run without a step cap is not built

NEXT_STEP = {
    MUSE_MISSING: "Install Muse Code and put `muse` on the PATH, then try again.",
    HOOK_FILE_MISSING: "Write .muse/hooks.json in the run folder with `muse_hooks_text`, then try again.",
    KEY_VARIABLE_FOUND: "umwayi removes the variable from the child; nothing to do, the name is logged.",
    PRIVATE_REPO_NAMED: "Only a root the owner marked public may go to Muse. Do not send this work to Muse.",
    YOLO_REFUSED: "umwayi never removes Muse's sandbox or approvals. Remove the flag.",
    SANDBOX_UNCONFIRMED: "No read-only command confirms Muse's sandbox yet (M3). Run with Muse's default approvals.",
    STEP_CAP_MISSING: "Give the goal a step cap, a whole number from 1 to 1000.",
}
FORBIDDEN_FLAGS = ("--yolo", "--disable-sandbox")
APPROVAL_FLAG = "--disable-approval"
MAX_STEPS = 1000
KEY_WORDS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
_SAFE_ARG = re.compile(r"^[A-Za-z0-9._/@:=+,-][A-Za-z0-9._/@:=+, -]{0,300}$")
HOOK_BYTES = 64 * 1024


class MuseRefused(Exception):
    """A refusal with a fixed reason word and the next step. `str(e)` is `reason: next step`."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"{reason}: {NEXT_STEP[reason]}")


def command(max_steps, prompt_file: str, extra=()) -> list:
    """The `muse exec` argument list. Always `--max-model-steps N` and `--contributor-mode off`; `--json` so a reader can parse the run.

    `extra` is a list of further arguments. `--yolo` and `--disable-sandbox` are refused (YOLO_REFUSED), also when written as
    `--flag=value`; `--disable-approval` is refused until the sandbox can be confirmed (SANDBOX_UNCONFIRMED). Any other argument must be a
    plain word without a shell character; an odd one is a ValueError, never passed on."""
    if isinstance(max_steps, bool) or not isinstance(max_steps, int) or not 1 <= max_steps <= MAX_STEPS:
        raise MuseRefused(STEP_CAP_MISSING)
    if not isinstance(prompt_file, str) or not _SAFE_ARG.match(prompt_file):
        raise ValueError("the prompt file is a plain path")
    for arg in extra:
        word = str(arg).split("=", 1)[0].lower()
        if word in FORBIDDEN_FLAGS:
            raise MuseRefused(YOLO_REFUSED)
        if word == APPROVAL_FLAG:
            raise MuseRefused(SANDBOX_UNCONFIRMED)
    for arg in extra:
        if not isinstance(arg, str) or not _SAFE_ARG.match(arg):
            raise ValueError("an extra argument is a plain word")
        if arg.lower().split("=", 1)[0] in ("--max-model-steps", "--contributor-mode"):
            raise ValueError("the step cap and the contributor flag are set by umwayi, not by the caller")
    return ["muse", "exec", "--max-model-steps", str(max_steps), "--contributor-mode", "off", "--json", "--prompt-file", prompt_file,
            *extra]


def is_key_variable(name: str) -> bool:
    """A MUSE or META variable whose name says it holds a key, a token or a secret."""
    up = name.upper()
    return up.startswith(("MUSE", "META")) and any(w in up for w in KEY_WORDS)


def child_env(environ) -> tuple:
    """(env, removed): a copy of `environ` without the Muse and Meta key variables, and the sorted NAMES removed (never a value)."""
    removed = sorted(k for k in environ if is_key_variable(k))
    return {k: v for k, v in environ.items() if k not in removed}, removed


def muse_hooks_text(gate_command: str) -> str:
    """The text of `.muse/hooks.json`: one PreToolUse hook that runs `gate_command`, the umwayi gate, which answers Yes, No or Ask me first.

    The format is assumed to match Claude Code's and is unconfirmed against a real Muse (M3). The gate fails closed: a missing or
    failing command must be treated by the hook as a No."""
    if not isinstance(gate_command, str) or not gate_command.strip() or "\n" in gate_command:
        raise ValueError("the gate command is one line")
    doc = {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": gate_command}]}]}}
    return json.dumps(doc, indent=2) + "\n"


def check_hook_file(run_folder, gate_command: str) -> None:
    """Refuse with HOOK_FILE_MISSING unless `.muse/hooks.json` of the run folder exists, is JSON and has a PreToolUse command that is
    exactly `gate_command`. Reads one small file; writes nothing."""
    path = Path(run_folder) / ".muse" / "hooks.json"
    try:
        doc = json.loads(fsutil.read_regular(path, HOOK_BYTES).decode("utf-8"))
        entries = doc["hooks"]["PreToolUse"]
        ok = any(h.get("command") == gate_command for e in entries for h in e["hooks"])
    except (OSError, fsutil.TooBig, ValueError, KeyError, TypeError, AttributeError):
        ok = False
    if not ok:
        raise MuseRefused(HOOK_FILE_MISSING)


def check_public(public_mark) -> None:
    """Refuse with PRIVATE_REPO_NAMED unless the owner's mark is exactly True. The route never infers it: a missing mark, "true" as text
    and 1 are all a refusal. Where the owner writes the mark is an open question (docs/muse-route-design.md, Q-c)."""
    if public_mark is not True:
        raise MuseRefused(PRIVATE_REPO_NAMED)


def check_on_path(which) -> None:
    """Refuse with MUSE_MISSING when `which("muse")` finds nothing. `which` is `shutil.which` or a fake."""
    if not which("muse"):
        raise MuseRefused(MUSE_MISSING)
