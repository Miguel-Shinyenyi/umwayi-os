"""A fake `claude` (and `kiro-cli`) for the layer 10 tests. Never imported: copied behind a shebang into a PATH folder.

It records every call to the JSON lines file in FAKE_LOG.

* The version flag (`-v` or `--version`) prints FAKE_<KEY>_VERSION (or a recent version)
  and exits FAKE_<KEY>_EXIT; FAKE_<KEY>_HANG makes it hang.
* Any other call is a start. It records argv, the working folder, what it got on stdin,
  its process group and the names (never the values) of its environment variables.
  Then it runs the steps in FAKE_SCRIPT (a JSON list). A "tool" step does what the
  Claude Code hooks reference describes for PreToolUse: for every handler in the
  --settings JSON whose matcher matches, it runs `command` with `args` (exec form, no
  shell), the hook input as JSON on stdin and the handler's `timeout`, and reads the
  answer: exit 2 blocks; exit 0 with a JSON permissionDecision decides; any other
  failure blocks only when onFailure is "block". The strictest answer wins.
"""
import json
import os
import signal
import subprocess
import sys
import time

PROG = os.path.basename(sys.argv[0])
KEY = "KIRO" if PROG == "kiro-cli" else "CLAUDE"
VERSION_FLAG = "--version" if PROG == "kiro-cli" else "-v"
DEFAULT_VERSION = {"KIRO": "kiro-cli 2.40.0", "CLAUDE": "2.1.300 (Claude Code)"}[KEY]
ARGS = sys.argv[1:]
ORDER = {"deny": 4, "block": 4, "ask": 2, "allow": 1, "error-allow": 0, "no-hook": 0}


def rec(**kw):
    kw.setdefault("prog", PROG)
    kw["t"] = time.time()
    with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as f:
        f.write(json.dumps(kw) + "\n")


if ARGS == [VERSION_FLAG]:
    rec(argv=ARGS, cwd=os.getcwd(), started=False)
    if os.environ.get(f"FAKE_{KEY}_HANG"):
        time.sleep(60)
    sys.stdout.write(os.environ.get(f"FAKE_{KEY}_VERSION", DEFAULT_VERSION) + "\n")
    sys.exit(int(os.environ.get(f"FAKE_{KEY}_EXIT", "0")))

stdin_text = sys.stdin.read() if sys.stdin is not None else ""
rec(argv=ARGS, cwd=os.getcwd(), started=True, pid=os.getpid(), pgid=os.getpgid(0), sid=os.getsid(0),
    stdin=stdin_text, env_keys=sorted(os.environ))

settings = {}
if "--settings" in ARGS:
    settings = json.loads(ARGS[ARGS.index("--settings") + 1])
groups = [] if settings.get("disableAllHooks") else settings.get("hooks", {}).get("PreToolUse", [])


def run_hook(h: dict, name: str, inp: dict) -> str:
    payload = {"session_id": "fake-session", "transcript_path": "/dev/null", "cwd": os.getcwd(),
               "hook_event_name": "PreToolUse", "permission_mode": "default", "tool_name": name,
               "tool_input": inp, "tool_use_id": "toolu_fake"}
    failed = "block" if h.get("onFailure") == "block" else "error-allow"
    try:
        r = subprocess.run([h["command"], *h.get("args", [])], input=json.dumps(payload).encode("utf-8"),
                           capture_output=True, timeout=h.get("timeout", 600), shell=False)
    except (subprocess.TimeoutExpired, OSError):
        return failed
    if r.returncode == 2:
        return "deny"
    if r.returncode == 0:
        try:
            return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"]
        except Exception:
            return failed
    return failed


def tool(name: str, inp: dict) -> str:
    answers = [run_hook(h, name, inp) for g in groups if g.get("matcher") in ("*", "", None, name)
               for h in g.get("hooks", [])]
    final = max(answers, key=lambda d: ORDER[d]) if answers else "no-hook"
    rec(event="tool", tool=name, input=inp, decision=final)
    return final


term_tool = None


def on_term(signum, frame):
    rec(event="term")
    if term_tool is not None:
        tool(*term_tool)
    sys.exit(143)


signal.signal(signal.SIGTERM, on_term)

for step in json.loads(os.environ.get("FAKE_SCRIPT", "[]")):
    kind = step["do"]
    if kind == "tool":
        tool(step["tool"], step.get("input", {}))
    elif kind == "sleep":
        time.sleep(step["s"])
    elif kind == "loop_tools":
        end = time.time() + step["for"]
        while time.time() < end:
            tool(step["tool"], step.get("input", {}))
            time.sleep(step["every"])
    elif kind == "ignore_term":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        rec(event="ignoring_term")
    elif kind == "term_tool":
        term_tool = (step["tool"], step.get("input", {}))
    elif kind == "spawn":
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        rec(event="spawn", pid=p.pid)
    elif kind == "crash":
        raise RuntimeError("the fake agent crashed")
    elif kind == "exit":
        rec(event="end")
        sys.exit(step["code"])
rec(event="end")
sys.exit(0)
