#!/usr/bin/env python3
"""Claude Code PreToolUse hook for umwayi-os (layer 9).

Claude Code runs this before every tool call it is configured for, with the
hook input as JSON on stdin. The script asks `umwayi check` and answers:

  * exit 0 and one JSON object on stdout with permissionDecision allow, deny or ask
  * exit 2 and the reason on stderr, when anything goes wrong

It never exits 1: on Claude Code exit 1 is a non blocking error and the tool
call would go ahead. See adapters/NOTES.md for what the Claude Code docs say.

    python3 adapters/claude_code/hook.py --root /path/to/umwayi/root
        [--umwayi-src /path/to/umwayi-os] [--timeout 10]

--root is required: the folder with rules.yaml, queue.md and LOGBOOK.md. It is
never taken from the hook input (an agent could change the working folder to
one with rules that allow everything).
"""

import sys

BLOCK = 2  # the only non zero exit code this script uses


def _block(stderr, reason: str) -> int:
    try:
        stderr.write(reason.rstrip() + "\n")
        stderr.flush()
    except Exception:
        pass
    return BLOCK


def main(argv, stdin, stdout, stderr) -> int:
    import json
    from pathlib import Path

    here = Path(__file__).resolve()
    sys.path.insert(0, str(here.parents[2]))  # the folder that holds the adapters package
    from adapters.common import umwayi_gate as gate

    # --- arguments, without argparse (argparse exits 2 and prints usage; we want our own message)
    args = list(argv)
    root = umwayi_src = None
    timeout = gate.DEFAULT_TIMEOUT
    while args:
        flag = args.pop(0)
        if flag not in ("--root", "--umwayi-src", "--timeout") or not args:
            return _block(stderr, f"umwayi hook: blocked, unknown or incomplete argument {flag[:40]!r}.")
        value = args.pop(0)
        if flag == "--root":
            root = Path(value)
        elif flag == "--umwayi-src":
            umwayi_src = Path(value)
        else:
            try:
                timeout = float(value)
            except ValueError:
                return _block(stderr, "umwayi hook: blocked, --timeout must be a number of seconds.")
            if not 0 < timeout <= 600:
                return _block(stderr, "umwayi hook: blocked, --timeout must be from 0 to 600 seconds.")
    if root is None:
        return _block(stderr, "umwayi hook: blocked, --root is required (the umwayi folder with rules.yaml).")
    if not root.is_dir():
        return _block(stderr, "umwayi hook: blocked, the --root folder does not exist.")
    if umwayi_src is None:
        umwayi_src = gate.find_umwayi_src(here.parent)

    # --- the hook input
    try:
        data = gate.read_hook_input(stdin.buffer if hasattr(stdin, "buffer") else stdin)
        if data.get("hook_event_name") != "PreToolUse":
            raise gate.AdapterError("this hook only handles PreToolUse")
        extra = {k: data.get(k) for k in ("permission_mode", "agent_type")}
        action = gate.tool_action("claude-code", data.get("tool_name"), data.get("tool_input"), extra)
    except gate.AdapterError as e:
        return _block(stderr, f"umwayi hook: blocked, {e}.")

    # --- ask umwayi, map the answer
    verdict = gate.decide(gate.run_check(action, root.resolve(), umwayi_src, timeout))
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": verdict.decision,
            "permissionDecisionReason": verdict.reason,
        }
    }
    stdout.write(json.dumps(out) + "\n")
    stdout.flush()
    return 0


def run() -> int:
    """Every error, including a failed import, blocks with exit 2."""
    try:
        return main(sys.argv[1:], sys.stdin, sys.stdout, sys.stderr)
    except BaseException as e:  # Ctrl-C and SystemExit too: nothing may turn into exit 1, or into 0 without a decision
        return _block(sys.stderr, f"umwayi hook: blocked by an unexpected error ({type(e).__name__}).")


if __name__ == "__main__":
    code = run()
    try:
        sys.stdout.flush()
    except Exception:
        code = BLOCK  # the decision may not have reached Claude Code
    sys.exit(code if code in (0, BLOCK) else BLOCK)
