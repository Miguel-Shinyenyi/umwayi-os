#!/usr/bin/env python3
"""A fake gate hook for the OpenCode plugin tests (task 10.45). Not umwayi code. The plugin runs it as it would run the
layer 9 generic adapter: argument list, no shell, the tool call as one JSON object on stdin.

    fake_gate_hook.py [--exit N] [--say MODE] [--sleep SECONDS] [--log FILE] [--stderr TEXT] [any other word]

It records every call to FILE (one JSON line: pid, the arguments, what it got on stdin). Then it sleeps, prints its
answer and exits with N. MODE says what it prints on stdout:

    auto       the real adapter's line for the exit code: 0 allow, 3 ask, anything else deny
    allow, ask, deny     that decision, whatever the exit code
    garbage    text that is not JSON          empty      nothing at all
    nodecision {"reason": "x"}                array      [1]          null    null          number    5
    huge       a valid allow line of 200000 characters
    secret     the auto line with a reason that holds the text in SECRET
    kill       the process kills itself with SIGKILL before it prints anything
"""
import json
import os
import signal
import sys
import time

SECRET = "sk-live-PLUGIN-TEST-SECRET"

args = sys.argv[1:]
opts = {"--exit": "0", "--say": "auto", "--sleep": "0", "--log": None, "--stderr": ""}
i = 0
while i < len(args):
    if args[i] in opts and i + 1 < len(args):
        opts[args[i]] = args[i + 1]
        i += 2
    else:
        i += 1

raw = sys.stdin.buffer.read()
if opts["--log"]:
    with open(opts["--log"], "ab") as f:
        f.write(json.dumps({"pid": os.getpid(), "argv": args, "stdin": raw.decode("utf-8", "replace")}).encode() + b"\n")
time.sleep(float(opts["--sleep"]))
code = int(opts["--exit"])
auto = {0: "allow", 3: "ask"}.get(code, "deny")
mode = opts["--say"]
if mode == "kill":
    os.kill(os.getpid(), signal.SIGKILL)
line = {
    "auto": json.dumps({"decision": auto, "reason": "umwayi: fake"}),
    "allow": json.dumps({"decision": "allow", "reason": "umwayi: fake"}),
    "ask": json.dumps({"decision": "ask", "reason": "umwayi: fake"}),
    "deny": json.dumps({"decision": "deny", "reason": "umwayi: fake"}),
    "garbage": "this is not json",
    "empty": "",
    "nodecision": json.dumps({"reason": "x"}),
    "array": "[1]",
    "null": "null",
    "number": "5",
    "huge": json.dumps({"decision": "allow", "reason": "x" * 200000}),
    "secret": json.dumps({"decision": auto, "reason": "umwayi: " + SECRET}),
}[mode]
if line:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()
if opts["--stderr"]:
    sys.stderr.write(opts["--stderr"] + "\n")
sys.exit(code)
