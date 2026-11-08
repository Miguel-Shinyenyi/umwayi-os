#!/usr/bin/env python3
"""Kiro Pre Tool Use hook for umwayi-os (layer 9).

Kiro runs this as a shell command action before a tool call, with the hook event
as JSON on stdin. The script asks `umwayi check` and answers with the exit code
only, because Kiro documents no JSON decision for Pre Tool Use:

  * exit 0, nothing on stdout: allow
  * exit 2, the reason on stderr: deny. Exit 2 is the one code that every
    version of the Kiro docs says blocks a Pre Tool Use call
  * Ask me first: Kiro has no ask, so the call is denied (exit 2) and one queue
    item of kind decision waits for the owner (not a second one while it is open)

It never exits 1, and never anything but 0 or 2: the Kiro docs disagree about
what other exit codes do. See adapters/NOTES.md.

    python3 adapters/kiro/hook.py --root /path/to/umwayi/root
        [--umwayi-src /path/to/umwayi-os] [--timeout 10]
"""

import sys

BLOCK = 2  # the only non zero exit code this script uses
LABEL = "Kiro"


def _block(stderr, reason: str) -> int:
    try:
        stderr.write(reason.rstrip() + "\n")
        stderr.flush()
    except Exception:
        pass
    return BLOCK


def main(argv, stdin, stdout, stderr) -> int:
    from pathlib import Path

    here = Path(__file__).resolve()
    sys.path.insert(0, str(here.parents[2]))  # the folder that holds the adapters package
    from adapters.common import umwayi_gate as gate

    try:
        opts = gate.parse_args(argv)
        data = gate.read_hook_input(stdin.buffer if hasattr(stdin, "buffer") else stdin)
        if data.get("hook_event_name") != "PreToolUse":
            raise gate.AdapterError("this hook only handles PreToolUse")
        action = gate.generic_action("kiro", data.get("tool_name"), data.get("tool_input"))
    except gate.AdapterError as e:
        return _block(stderr, f"umwayi hook: blocked, {e}.")
    umwayi_src = opts["umwayi_src"] or gate.find_umwayi_src(here.parent)

    verdict = gate.decide(gate.run_check(action, opts["root"], umwayi_src, opts["timeout"]))
    if verdict.decision == gate.ALLOW:
        return 0  # nothing on stdout: Kiro adds a successful hook's stdout to the agent's context
    if verdict.decision == gate.ASK:
        ok, line = gate.add_queue_item(opts["root"], gate.ask_title(LABEL, action),
                                       gate.ask_recommendation(LABEL, verdict, action), umwayi_src)
        note = line if ok else f"warning: {line}"
        return _block(stderr, f"{verdict.reason} Kiro has no ask, so this call is denied. {note}")
    return _block(stderr, verdict.reason)


def run() -> int:
    """Every error, including a failed import, blocks with exit 2."""
    try:
        return main(sys.argv[1:], sys.stdin, sys.stdout, sys.stderr)
    except BaseException as e:  # Ctrl-C and SystemExit too: nothing may turn into exit 1, or into an allow
        return _block(sys.stderr, f"umwayi hook: blocked by an unexpected error ({type(e).__name__}).")


if __name__ == "__main__":
    code = run()
    sys.exit(code if code in (0, BLOCK) else BLOCK)
