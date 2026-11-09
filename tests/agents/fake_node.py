"""A fake `node` for the layer 10 part 7 tests: a Python script put first on PATH as `node`.

It answers the self-test programs of a Claude Code ACP chat (design.md part 7):

    node --version                         the Node version
    node ADAPTER --version                 the adapter version
    node ADAPTER --cli --version           the bundled Claude Code version
    node ADAPTER --cli auth status         the sign-in check (exit code; prints a planted secret)
    node ADAPTER                           the ACP chat: recorded as "started"; with "acp" in node.json it
                                           execs the scripted ACP agent of fake_agent.py in its Claude
                                           flavour (bin/claude-acp, same pid), with that spec as FAKE_ACP
                                           and "fake_log" as FAKE_LOG added to the environment it got

umwayi gives these programs only an allow-listed environment, so the fake cannot be steered
by environment variables. It reads its answers from `node.json` next to itself and appends
one JSON line per call to `node-calls.jsonl` next to itself: the argv, the working folder,
the names of the environment variables it got (with the value of CLAUDE_AGENT_ACP_PROTOCOL
and whether any planted secret reached it), and how many stdin bytes it read.
"""

import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULTS = {
    "node_version": "v22.23.4\n", "node_exit": 0,
    "adapter_version": "0.101.0\n", "adapter_exit": 0,
    "cli_version": "2.1.318 (Claude Code)\n", "cli_exit": 0,
    "auth_exit": 0, "auth_hang": False, "auth_output": "",
    "secret": "",
}


def main() -> int:
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads((HERE / "node.json").read_text(encoding="utf-8")))
    except FileNotFoundError:
        pass
    args = sys.argv[1:]
    is_chat = len(args) == 1 and args[0].endswith("/dist/index.js")  # stdin is the ACP pipe then: never read here
    data = sys.stdin.buffer.read() if not (is_chat or sys.stdin.isatty()) else b""
    secret = cfg["secret"]
    call = {"argv": [sys.argv[0]] + args, "cwd": os.getcwd(), "pid": os.getpid(), "stdin": len(data),
            "env": sorted(os.environ), "protocol": os.environ.get("CLAUDE_AGENT_ACP_PROTOCOL"),
            "secret_in_env": bool(secret) and any(secret in v for v in os.environ.values()),
            "started": False}

    def log(**extra):
        call.update(extra)
        with open(HERE / "node-calls.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(call) + "\n")

    if args == ["--version"]:
        log(probe="node version")
        sys.stdout.write(cfg["node_version"])
        return cfg["node_exit"]
    if not args or not args[0].endswith("/dist/index.js"):
        log(probe="unknown")
        return 9
    rest = args[1:]
    if rest == ["--version"]:
        log(probe="adapter version")
        sys.stdout.write(cfg["adapter_version"])
        return cfg["adapter_exit"]
    if rest == ["--cli", "--version"]:
        log(probe="claude code version")
        sys.stdout.write(cfg["cli_version"])
        return cfg["cli_exit"]
    if rest == ["--cli", "auth", "status"]:
        log(probe="sign-in")
        sys.stdout.write(cfg["auth_output"])
        sys.stdout.flush()
        sys.stderr.write(cfg["auth_output"])
        sys.stderr.flush()
        if cfg["auth_hang"]:
            time.sleep(120)
        return cfg["auth_exit"]
    if not rest:
        log(probe="chat", started=True)
        if "acp" in cfg:  # become the scripted ACP agent (Claude flavour), keeping this pid and environment
            env = dict(os.environ, FAKE_LOG=cfg["fake_log"], FAKE_ACP=json.dumps(cfg["acp"]), FAKE_SCRIPT="[]")
            os.execve(sys.executable, [sys.executable, str(HERE / "claude-acp"), "acp"], env)
        return 0
    log(probe="unknown")
    return 9


if __name__ == "__main__":
    sys.exit(main())
