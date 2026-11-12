"""A fake `opencode` for the layer 10 part 8 tests. Never imported: copied behind a shebang into a PATH folder.

umwayi gives OpenCode only an allow-listed environment (10.R13.4), so this fake cannot be steered or told where to
log by environment variables. It reads its settings from `opencode-fake.json` next to itself: {"fake_log": PATH,
"version": TEXT, "exit": N, "hang": bool, "big": N, "no_newline": bool}. It records every call (argv, working folder,
the names of its environment variables and whether it was started) to the JSON lines file named by `fake_log`.

* `--version` (task 10.46): records started=False, prints `version` (default `opencode v2.2.7`), exits `exit`. `hang`
  makes it hang. `big` makes it print that many bytes of text before the version. `no_newline` leaves out the newline.
* Any other call is a start: it records started=True and exits at once. Until the chat is built (10.48) and the ACP
  behaviour is added to this file (10.47), no test expects one; the record is how a test proves that none happened.
"""
import json
import os
import sys
import time

ARGS = sys.argv[1:]
with open(os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), "opencode-fake.json"), encoding="utf-8") as f:
    CFG = json.load(f)


def rec(**kw):
    kw.setdefault("prog", "opencode")
    kw["t"] = time.time()
    with open(CFG["fake_log"], "a", encoding="utf-8") as f:
        f.write(json.dumps(kw) + "\n")


if ARGS == ["--version"]:
    rec(argv=ARGS, cwd=os.getcwd(), started=False, env_keys=sorted(os.environ),
        config_content=os.environ.get("OPENCODE_CONFIG_CONTENT"))
    if CFG.get("hang"):
        time.sleep(60)
    if CFG.get("big"):
        sys.stdout.write("x" * int(CFG["big"]) + "\n")
    sys.stdout.write(CFG.get("version", "opencode v2.2.7"))
    if not CFG.get("no_newline"):
        sys.stdout.write("\n")
    sys.exit(int(CFG.get("exit", 0)))

rec(argv=ARGS, cwd=os.getcwd(), started=True, pid=os.getpid(), env_keys=sorted(os.environ))
sys.exit(0)
