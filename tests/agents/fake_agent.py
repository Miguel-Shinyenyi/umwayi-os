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
* As `kiro-cli acp`: a scripted ACP agent on stdin and stdout, driven by the JSON in FAKE_ACP
  (see run_acp). Every message it gets is recorded as an "acp_in" event, every answer to
  one of its requests as "permission_answer" or "request_answer".
* As `claude-acp acp` (exec'd by tests/agents/fake_node.py for `node ADAPTER`): the same
  scripted ACP agent in a Claude flavour, as the claude-agent-acp adapter and the Claude Agent
  SDK docs describe it: it reads `_meta.claudeCode.options.settings` of session/new, runs the
  SessionStart command hooks there in exec form (command and args, the event JSON on stdin,
  the handler's timeout) when the session starts (FAKE_ACP "canary": "session_new", the
  default; or "first_prompt", or "never"), answers session/set_mode, and for a "claude_tool"
  action runs the PreToolUse hooks of those settings before it sends a permission request;
  a deny or block from a hook means no permission request is sent.
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

if KEY == "CLAUDE" and ARGS == ["auth", "status", "--json"]:
    # the login check (10.R12.3): a scripted JSON answer that also names the person, as the real one does
    rec(argv=ARGS, cwd=os.getcwd(), started=False, probe="auth", env_keys=sorted(os.environ))
    if os.environ.get("FAKE_CLAUDE_AUTH_HANG"):
        time.sleep(60)
    sys.stdout.write(os.environ.get("FAKE_CLAUDE_AUTH", json.dumps({
        "loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "max",
        "email": "owner@example.invalid", "orgId": "org-PLANTED", "orgName": "Planted Org"})) + "\n")
    sys.stderr.write("auth stderr owner@example.invalid\n")
    sys.exit(int(os.environ.get("FAKE_CLAUDE_AUTH_EXIT", "0")))

if KEY == "KIRO" and ARGS == ["whoami"]:
    # the Kiro login check (10.R12.13): umwayi reads only the exit code. The output names the person, so it is
    # planted here to prove it is never shown. Signed in once FAKE_KIRO_STATE exists (a fake login wrote it).
    rec(argv=ARGS, cwd=os.getcwd(), started=False, probe="whoami", env_keys=sorted(os.environ))
    if os.environ.get("FAKE_KIRO_WHOAMI_HANG"):
        time.sleep(60)
    sys.stdout.write(json.dumps({"email": "owner@example.invalid", "note": os.environ.get("FAKE_PLANT", "")}) + "\n")
    state = os.environ.get("FAKE_KIRO_STATE")
    sys.exit(0 if state and os.path.exists(state) else int(os.environ.get("FAKE_KIRO_WHOAMI_EXIT", "0")))

if KEY == "KIRO" and ARGS == ["login"]:
    # `umwayi agent login` for Kiro: a sign-in on the owner's terminal that prints a planted URL, code and secret
    rec(argv=ARGS, cwd=os.getcwd(), started=False, probe="kiro login", login=True, pid=os.getpid(),
        env_keys=sorted(os.environ), tty=os.isatty(1))
    sys.stdout.write(f"Open https://login.example.invalid/?code=PLANTED-CODE {os.environ.get('FAKE_PLANT', '')}\n")
    sys.stdout.flush()
    if os.environ.get("FAKE_KIRO_LOGIN_HANG"):
        time.sleep(60)
    code = int(os.environ.get("FAKE_KIRO_LOGIN_EXIT", "0"))
    if code == 0 and os.environ.get("FAKE_KIRO_STATE"):
        open(os.environ["FAKE_KIRO_STATE"], "w").close()
    sys.exit(code)

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
def run_session_start(settings: dict, source: str) -> None:
    """The SessionStart command hooks of the inline settings, in exec form, one after another."""
    if settings.get("disableAllHooks"):
        return
    payload = {"session_id": "fake-session", "transcript_path": "/dev/null", "cwd": os.getcwd(),
               "hook_event_name": "SessionStart", "source": source}
    for g in settings.get("hooks", {}).get("SessionStart", []):
        for h in g.get("hooks", []):
            if h.get("type") != "command":
                continue
            try:
                r = subprocess.run([h["command"], *h.get("args", [])], input=json.dumps(payload).encode("utf-8"),
                                   capture_output=True, timeout=h.get("timeout", 600), shell=False)
                code = r.returncode
            except (subprocess.TimeoutExpired, OSError):
                code = None
            rec(event="session_start_hook", source=source, args=h.get("args", []), code=code)


def run_acp():
    """A scripted ACP agent. FAKE_ACP: {"init": {...} | "garbage", "new": {...}, "turns": [[action, ...], ...],
    "ignore_eof": bool, "stderr": text, and for the Claude flavour "canary": "session_new" | "first_prompt" |
    "never", "canary_delay": seconds, "set_mode_error": bool}. Actions: chunk, tool_call, update, permission,
    request, garbage, big, sleep, wait_cancel, ignore_cancel, exit, spawn, spawn_setsid, spawn_stubborn, stop,
    and claude_tool ({"tool": NAME, "input": {...}}, the PreToolUse hooks first, then its permission if any)."""
    global groups
    import queue as _queue
    import threading as _threading
    from collections import deque
    spec = json.loads(os.environ.get("FAKE_ACP", "{}"))
    inbox = _queue.Queue()

    def reader():  # records every line the moment it arrives, so a test sees it even if a signal ends us next
        for line in sys.stdin:
            msg = json.loads(line)
            rec(event="acp_in", msg=msg)
            if msg.get("method") == "session/cancel":
                rec(event="got_cancel")
            inbox.put(msg)
        rec(event="acp_eof")
        inbox.put(None)

    _threading.Thread(target=reader, daemon=True).start()

    def on_term_acp(signum, frame):
        rec(event="term")
        time.sleep(0.3)  # let the reader thread record what is still arriving
        os._exit(143)

    signal.signal(signal.SIGTERM, on_term_acp)
    if spec.get("stderr"):
        sys.stderr.write(spec["stderr"] + "\n")
        sys.stderr.flush()
    pending = deque()

    def send(obj):
        sys.stdout.write((obj if isinstance(obj, str) else json.dumps(obj)) + "\n")
        sys.stdout.flush()

    def recv():
        msg = inbox.get()
        if msg is None:
            if spec.get("ignore_eof"):
                time.sleep(120)
            rec(event="end")
            sys.exit(0)
        return msg

    def next_msg(pred):
        for m in list(pending):
            if pred(m):
                pending.remove(m)
                return m
        while True:
            m = recv()
            if pred(m):
                return m
            pending.append(m)

    m = next_msg(lambda x: x.get("method") == "initialize")
    init = spec.get("init", {"protocolVersion": 1})
    if init == "garbage":
        send("this is not json")
    elif "error" in init:
        send({"jsonrpc": "2.0", "id": m["id"], "error": init["error"]})
    else:
        send({"jsonrpc": "2.0", "id": m["id"], "result": {"protocolVersion": init.get("protocolVersion", 1),
              "agentCapabilities": {"loadSession": False}, "agentInfo": {"name": "fake-kiro"}, "authMethods": []}})
    m = next_msg(lambda x: x.get("method") == "session/new")
    claude = PROG != "kiro-cli"
    meta = (m.get("params") or {}).get("_meta") or {}
    inline = ((meta.get("claudeCode") or {}).get("options") or {}).get("settings") or {} if claude else {}
    groups = [] if inline.get("disableAllHooks") else inline.get("hooks", {}).get("PreToolUse", [])
    canary = spec.get("canary", "session_new") if claude else "never"
    new = spec.get("new", {})
    if "error" in new:
        send({"jsonrpc": "2.0", "id": m["id"], "error": new["error"]})
    else:
        send({"jsonrpc": "2.0", "id": m["id"], "result": {"sessionId": new.get("sessionId", "sess-1")}})
    if canary == "session_new":
        time.sleep(spec.get("canary_delay", 0))
        run_session_start(inline, "startup")
    sid = new.get("sessionId", "sess-1")
    turns = deque(spec.get("turns", []))
    rid = 1000

    def update(u):
        send({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": sid, "update": u}})

    while True:
        m = next_msg(lambda x: x.get("method") in ("session/prompt", "session/set_mode"))
        if m["method"] == "session/set_mode":
            rec(event="set_mode", mode=m["params"].get("modeId"))
            if spec.get("set_mode_error"):
                send({"jsonrpc": "2.0", "id": m["id"], "error": {"code": -32602, "message": "Invalid mode"}})
            else:
                send({"jsonrpc": "2.0", "id": m["id"], "result": {}})
            continue
        if canary == "first_prompt":
            canary = "done"
            run_session_start(inline, "startup")
        text = m["params"]["prompt"][0]["text"]
        actions = turns.popleft() if turns else [{"chunk": f"you said: {text}"}]
        stop, answer = "end_turn", True
        for act in actions:
            if "chunk" in act:
                update({"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": act["chunk"]}})
            if "tool_call" in act:
                update(dict({"sessionUpdate": "tool_call", "toolCallId": "call-1", "status": "pending"}, **act["tool_call"]))
            if "update" in act:
                update(act["update"])
            blocked = False
            if "claude_tool" in act:  # the PreToolUse hooks run before any permission request
                blocked = tool(act["claude_tool"]["tool"], act["claude_tool"].get("input", {})) in ("deny", "block")
            if ("permission" in act or "request" in act) and not blocked:
                rid += 1
                if "permission" in act:
                    method, params = "session/request_permission", dict({"sessionId": sid}, **act["permission"])
                else:
                    method, params = act["request"]["method"], act["request"].get("params", {})
                send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
                rec(event="request_sent", method=method)
                r = next_msg(lambda x, rid=rid: x.get("id") == rid and "method" not in x)
                rec(event="permission_answer" if "permission" in act else "request_answer", method=method, answer=r)
            if "garbage" in act:
                send(act["garbage"])
            if "big" in act:
                send("x" * act["big"])
            if "sleep" in act:
                time.sleep(act["sleep"])
            if "wait_cancel" in act:
                next_msg(lambda x: x.get("method") == "session/cancel")
                stop = "cancelled"
            if "ignore_cancel" in act:
                time.sleep(act["ignore_cancel"])
                answer = False
            if "spawn" in act:
                p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
                rec(event="spawn", pid=p.pid)
            if "spawn_setsid" in act:  # a background command in its own session: out of reach of the group
                p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], start_new_session=True)
                rec(event="spawn", pid=p.pid, setsid=True)
            if "spawn_orphan" in act:  # a grandchild in its own session whose parent exits after 1.5 s
                code = ("import subprocess, sys, time\n"
                        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], "
                        "start_new_session=True)\n"
                        "print(p.pid, flush=True)\n"
                        "time.sleep(1.5)\n")
                mid = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
                rec(event="spawn", pid=int(mid.stdout.readline()), orphan=True, setsid=True)
                rec(event="spawn", pid=mid.pid, intermediate=True)
            if "spawn_stubborn" in act:  # its own session, and it ignores SIGTERM
                p = subprocess.Popen([sys.executable, "-c", "import signal, time; signal.signal(signal.SIGTERM, "
                                      "signal.SIG_IGN); print('ready', flush=True); time.sleep(120)"],
                                     start_new_session=True, stdout=subprocess.PIPE, text=True)
                p.stdout.readline()  # it ignores SIGTERM from here on
                rec(event="spawn", pid=p.pid, setsid=True, stubborn=True)
            if "exit" in act:
                rec(event="end")
                sys.exit(act["exit"])
            if "stop" in act:
                stop = act["stop"]
        if answer:
            send({"jsonrpc": "2.0", "id": m["id"], "result": {"stopReason": stop}})


if CHAT and ARGS[:1] == ["acp"]:
    run_acp()

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
