"""A fake `opencode` for the layer 10 part 8 tests. Never imported: copied behind a shebang into a PATH folder.

It records every call to the JSON lines file in FAKE_LOG (argv, working folder, the names of its environment variables
and whether it was started), like tests/agents/fake_agent.py does for claude and kiro-cli.

* `--version` (task 10.46): records started=False and prints FAKE_OPENCODE_VERSION (default `opencode v2.2.7`), then
  exits FAKE_OPENCODE_EXIT. FAKE_OPENCODE_HANG makes it hang; FAKE_OPENCODE_BIG makes it print that many bytes of
  text before the version; FAKE_OPENCODE_NO_NEWLINE leaves out the newline.
* Any other call is a start: it records started=True and exits at once. Until the chat is built (10.48) and the ACP
  fake is added to this file (10.47), no test expects one; the record is how a test proves that none happened.
"""
import json
import os
import sys
import time

ARGS = sys.argv[1:]


def rec(**kw):
    kw.setdefault("prog", "opencode")
    kw["t"] = time.time()
    with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as f:
        f.write(json.dumps(kw) + "\n")


if ARGS == ["--version"]:
    rec(argv=ARGS, cwd=os.getcwd(), started=False, env_keys=sorted(os.environ),
        config_content=os.environ.get("OPENCODE_CONFIG_CONTENT"))
    if os.environ.get("FAKE_OPENCODE_HANG"):
        time.sleep(60)
    big = int(os.environ.get("FAKE_OPENCODE_BIG", "0"))
    if big:
        sys.stdout.write("x" * big + "\n")
    sys.stdout.write(os.environ.get("FAKE_OPENCODE_VERSION", "opencode v2.2.7"))
    if not os.environ.get("FAKE_OPENCODE_NO_NEWLINE"):
        sys.stdout.write("\n")
    sys.exit(int(os.environ.get("FAKE_OPENCODE_EXIT", "0")))

rec(argv=ARGS, cwd=os.getcwd(), started=True, pid=os.getpid(), env_keys=sorted(os.environ))
sys.exit(0)
