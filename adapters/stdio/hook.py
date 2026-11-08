#!/usr/bin/env python3
"""Generic stdin and stdout adapter for umwayi-os (layer 9).

For any platform or script that can run a command before it acts. One JSON
object in on stdin:

    {"tool_name": "deploy", "tool_input": {"target": "staging"}}

one JSON object out on stdout, and the exit code says the same thing:

    {"decision": "allow", "reason": "umwayi: Yes (rule ...)"}           exit 0
    {"decision": "deny",  "reason": "umwayi: No (rule ...)"}            exit 2
    {"decision": "ask",   "reason": "umwayi: Ask me first (rule ...)"}  exit 3

With --no-ask (a platform that cannot ask the user), Ask me first is a deny
(exit 2) and one queue item of kind decision waits for the owner; the answer
then has "queue": the line umwayi printed.

Every error is a deny: the JSON says so when it can be written, the reason is
on stderr, and the exit code is 2. It never exits 1.

    python3 adapters/stdio/hook.py --root /path/to/umwayi/root
        [--platform NAME] [--no-ask] [--umwayi-src DIR] [--timeout 10]

--root and --platform come from the command line only, never from the input:
the caller cannot claim to be another platform to match its rules.
"""

import sys

BLOCK = 2
CODES = {"allow": 0, "deny": 2, "ask": 3}


def _write(stream, text: str) -> None:
    stream.write(text)
    stream.flush()


def _deny(stdout, stderr, reason: str) -> int:
    import json
    try:
        _write(stdout, json.dumps({"decision": "deny", "reason": reason}) + "\n")
    except Exception:
        pass
    try:
        _write(stderr, reason.rstrip() + "\n")
    except Exception:
        pass
    return BLOCK


def main(argv, stdin, stdout, stderr) -> int:
    import json
    from pathlib import Path

    here = Path(__file__).resolve()
    sys.path.insert(0, str(here.parents[2]))  # the folder that holds the adapters package
    from adapters.common import umwayi_gate as gate

    try:
        opts = gate.parse_args(argv, extra_flags=("--platform",), extra_switches=("--no-ask",))
        platform = gate.check_platform_name(opts.get("--platform", "stdio"))
        data = gate.read_hook_input(stdin.buffer if hasattr(stdin, "buffer") else stdin)
        action = gate.generic_action(platform, data.get("tool_name"), data.get("tool_input"))
    except gate.AdapterError as e:
        return _deny(stdout, stderr, f"umwayi adapter: blocked, {e}.")
    umwayi_src = opts["umwayi_src"] or gate.find_umwayi_src(here.parent)

    verdict = gate.decide(gate.run_check(action, opts["root"], umwayi_src, opts["timeout"]))
    answer = {"decision": verdict.decision, "reason": verdict.reason}
    if verdict.decision == gate.ASK and opts.get("--no-ask"):
        label = f"The {platform} platform"
        ok, line = gate.add_queue_item(opts["root"], gate.ask_title(label, action),
                                       gate.ask_recommendation(label, verdict, action), umwayi_src)
        answer = {"decision": "deny", "reason": f"{verdict.reason} This platform has no ask, so this call is denied.",
                  "queue": line if ok else f"warning: {line}"}
    _write(stdout, json.dumps(answer) + "\n")
    if answer["decision"] == "deny":
        _write(stderr, answer["reason"] + "\n")
    return CODES[answer["decision"]]


def run() -> int:
    try:
        return main(sys.argv[1:], sys.stdin, sys.stdout, sys.stderr)
    except BaseException as e:  # Ctrl-C and SystemExit too: nothing may turn into exit 1, or into an allow
        return _deny(sys.stdout, sys.stderr, f"umwayi adapter: blocked by an unexpected error ({type(e).__name__}).")


if __name__ == "__main__":
    code = run()
    sys.exit(code if code in CODES.values() else BLOCK)
