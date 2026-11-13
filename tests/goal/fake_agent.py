"""A fake AI helper for the goal tests (W9.R21.1). Run it as a program: `python tests/goal/fake_agent.py`.

It reads the prompt on standard input, then does the steps of the JSON list in the environment variable
FAKE_GOAL_SCRIPT, one after the other. A script says what it does:

  {"print": TEXT}                      print a line
  {"error": TEXT}                      print a line to standard output (the supervisor reads errors there)
  {"sleep": SECONDS}                   wait (real time, keep it short)
  {"silent": SECONDS}                  the same, named for what a test means by it
  {"write": PATH, "text": TEXT}        write a file, relative to the working folder
  {"change": PATH, "every": S, "times": N}   change a file N times, S seconds apart
  {"spend": UU}                        append a number to the file named by FAKE_GOAL_SPEND
  {"flood": BYTES, "newline": BOOL}    print BYTES bytes of one letter, with or without a final newline
  {"noise": BYTES}                     print BYTES bytes that are not UTF-8
  {"result": TAG, "body": OBJECT}      print `TAG NONCE JSON` with the nonce found in the prompt (`Nonce: HEX`);
                                       "nonce": "wrong" prints another nonce
  {"whoami": true}                     print `cwd=... session=... marker=...` (the marker is the first line of
                                       the file MARKER in the working folder, or none)
  {"ignore_sigterm": true}             ignore SIGTERM from here on
  {"git": [ARG, ...]}                  run `git ARG ...` in the working folder (hooks off, no global config); a
                                       failure is exit 99. This is how a fake builder commits.
  {"exit": CODE}                       exit with CODE

With no script it prints one line and exits 0. The session id is new for every run.
"""
import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid


def main():
    prompt = sys.stdin.read()
    m = re.search(r"Nonce: ([0-9a-f]{16})", prompt)
    nonce = m.group(1) if m else "0" * 16
    script = json.loads(os.environ.get("FAKE_GOAL_SCRIPT", "[]"))
    if not script:
        print("fake agent: nothing to do", flush=True)
        return 0
    for step in script:
        if "print" in step or "error" in step:
            print(step.get("print", step.get("error")), flush=True)
        elif "sleep" in step or "silent" in step:
            time.sleep(float(step.get("sleep", step.get("silent"))))
        elif "write" in step:
            path = step["write"]
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(step.get("text", ""))
        elif "change" in step:
            for i in range(int(step.get("times", 1))):
                with open(step["change"], "a", encoding="utf-8") as f:
                    f.write(f"{i}\n")
                time.sleep(float(step.get("every", 0)))
        elif "spend" in step:
            with open(os.environ["FAKE_GOAL_SPEND"], "a", encoding="utf-8") as f:
                f.write(f"{int(step['spend'])}\n")
        elif "flood" in step:
            sys.stdout.write("x" * int(step["flood"]) + ("\n" if step.get("newline", True) else ""))
            sys.stdout.flush()
        elif "noise" in step:
            sys.stdout.buffer.write(bytes(range(128, 256)) * (int(step["noise"]) // 128 + 1) + b"\n")
            sys.stdout.buffer.flush()
        elif "result" in step:
            use = "f" * 16 if step.get("nonce") == "wrong" else nonce
            print(f"{step['result']} {use} {json.dumps(step.get('body', {}), separators=(',', ':'))}", flush=True)
        elif "whoami" in step:
            marker = "none"
            if os.path.isfile("MARKER"):
                with open("MARKER", encoding="utf-8") as f:
                    marker = f.readline().strip()
            print(f"cwd={os.getcwd()} session={uuid.uuid4().hex} marker={marker}", flush=True)
        elif "git" in step:
            env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0",
                       GIT_AUTHOR_NAME="fake", GIT_AUTHOR_EMAIL="fake@example.invalid",
                       GIT_COMMITTER_NAME="fake", GIT_COMMITTER_EMAIL="fake@example.invalid")
            if subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *step["git"]], env=env,
                              capture_output=True).returncode != 0:
                return 99
        elif step.get("ignore_sigterm"):
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        elif "exit" in step:
            return int(step["exit"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
