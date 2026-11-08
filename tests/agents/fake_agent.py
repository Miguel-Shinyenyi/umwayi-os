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
* As kiro-cli (`chat --v3 --no-interactive`), it reads the instruction from stdin (unless
  FAKE_NO_STDIN is set), and for a "tool" step does what the Kiro hook docs describe
  (adapters/NOTES.md): every hook with trigger PreToolUse and no matcher, "*" or the tool
  ID, in a v1 JSON file in ./.kiro/hooks/ or ~/.kiro/hooks/, runs its command in a shell
  with the event JSON on stdin. Exit 2 blocks; any other exit code warns and lets the tool
  run (the more dangerous of the two readings of the Kiro docs). Then, because nobody can
  approve a tool in a headless run, a tool not in --trust-tools is denied.
* Chat (claude without -p, kiro-cli chat without --no-interactive): it runs the FAKE_SCRIPT
  steps, prints "agent ready", then reads lines from stdin and echoes each as
  "agent: LINE". "/tool NAME" makes a tool call through the hooks, "/exit N" exits N,
  "/quit" or the end of stdin exits 0. Ctrl-C (SIGINT) is recorded, not fatal. It records
  whether stdin is a terminal, the terminal name and the terminal's foreground group.
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

CHAT = ("-p" not in ARGS) if KEY == "CLAUDE" else ("--no-interactive" not in ARGS)
stdin_text = "" if (CHAT or sys.stdin is None or os.environ.get("FAKE_NO_STDIN")) else sys.stdin.read()
tty = {}
# what the agent inherited for Ctrl-C, before it sets its own handler: SIG_IGN here would mean a
# program that keeps the default action never sees Ctrl-C
INHERITED_SIGINT_IGNORED = signal.getsignal(signal.SIGINT) == signal.SIG_IGN
if CHAT:
    tty = {"stdin_tty": os.isatty(0), "stdout_tty": os.isatty(1),
           "ttyname": os.ttyname(0) if os.isatty(0) else None,
           "foreground": os.tcgetpgrp(0) if os.isatty(0) else None,
           "sigint_ignored": INHERITED_SIGINT_IGNORED}
with open("/proc/self/cmdline", "rb") as f:
    cmdline = f.read().decode("utf-8", "replace").split("\x00")
rec(argv=ARGS, cwd=os.getcwd(), started=True, pid=os.getpid(), pgid=os.getpgid(0), sid=os.getsid(0),
    stdin=stdin_text, env_keys=sorted(os.environ), cmdline=cmdline, chat=CHAT, **tty)
trusted = set()
for a in ARGS:
    if a.startswith("--trust-tools="):
        trusted |= set(x for x in a.split("=", 1)[1].split(",") if x)

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


def kiro_hooks() -> list:
    found = []
    for folder in (os.path.join(os.getcwd(), ".kiro", "hooks"), os.path.join(os.path.expanduser("~"), ".kiro", "hooks")):
        if not os.path.isdir(folder):
            continue
        for fname in sorted(os.listdir(folder)):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(folder, fname), encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            if isinstance(data, dict) and data.get("version") == "v1":
                found += [h for h in data.get("hooks", []) if isinstance(h, dict)]
    return found


def kiro_tool(name: str, inp: dict) -> str:
    answer = "no-hook"
    for h in kiro_hooks():
        if h.get("trigger") != "PreToolUse" or h.get("matcher", "*") not in ("*", name):
            continue
        action = h.get("action", {})
        if action.get("type") != "command":
            continue
        event = {"hook_event_name": "PreToolUse", "cwd": os.getcwd(), "session_id": "fake-kiro",
                 "tool_name": name, "tool_input": inp}
        try:
            r = subprocess.run(action["command"], shell=True, input=json.dumps(event).encode("utf-8"),
                               capture_output=True, timeout=h.get("timeout", 60), cwd=os.getcwd())
            code = r.returncode
        except subprocess.TimeoutExpired:
            code = None  # not documented what Kiro does; this fake lets the tool run
        if code == 2:
            answer = "deny-hook"
            break
        answer = "allow-hook" if code == 0 else "warn-hook"
    if answer == "deny-hook":
        final = "deny-hook"
    elif name not in trusted and not CHAT:  # in a chat the owner approves untrusted tools in Kiro's own prompt
        final = "deny-untrusted"
    else:
        final = "allow"
    rec(event="tool", tool=name, input=inp, decision=final, hook=answer)
    return final


def tool(name: str, inp: dict) -> str:
    if KEY == "KIRO":
        return kiro_tool(name, inp)
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
    elif kind == "raw":  # what a full screen program does to the terminal
        import tty as _tty
        _tty.setraw(0)
        rec(event="raw")
    elif kind == "spawn_orphan":  # a grandchild whose parent exits after 1.5 s, so it is orphaned while the agent runs
        code = ("import subprocess, sys, time, json\n"
                "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
                "print(p.pid, flush=True)\n"
                "time.sleep(1.5)\n")
        mid = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
        rec(event="spawn", pid=int(mid.stdout.readline()), orphan=True)
        rec(event="spawn", pid=mid.pid, intermediate=True)
    elif kind == "spawn_setsid":  # a child in its own session: out of reach of a process group signal
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], start_new_session=True)
        rec(event="spawn", pid=p.pid, setsid=True)
    elif kind == "crash":
        raise RuntimeError("the fake agent crashed")
    elif kind == "exit":
        rec(event="end")
        sys.exit(step["code"])
if CHAT:
    signal.signal(signal.SIGINT, lambda signum, frame: rec(event="sigint"))
    print("agent ready", flush=True)
    for line in sys.stdin:
        line = line.rstrip("\n")
        rec(event="line", text=line)
        if line == "/quit":
            break
        if line.startswith("/exit "):
            rec(event="end")
            sys.exit(int(line.split()[1]))
        if line.startswith("/tool "):
            print(f"tool {line.split()[1]}: {tool(line.split()[1], {})}", flush=True)
            continue
        print(f"agent: {line}", flush=True)
rec(event="end")
sys.exit(0)
