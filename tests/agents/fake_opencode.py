"""A fake `opencode` for the layer 10 part 8 tests (tasks 10.46 and 10.47). Never imported: copied behind a shebang into
a PATH folder.

umwayi gives OpenCode only an allow-listed environment (10.R13.4), so this fake cannot be steered or told where to log
by environment variables. It reads its settings from `opencode-fake.json` next to itself: {"fake_log": PATH,
"version": TEXT, "exit": N, "hang": bool, "big": N, "no_newline": bool, "acp": {...}}. It records every call and every
event to the JSON lines file named by `fake_log`.

`opencode --version` (10.46): records started=False, prints `version` (default `opencode v2.2.7`), exits `exit`. `hang`
makes it hang. `big` makes it print that many bytes of text before the version. `no_newline` leaves out the newline.

`opencode acp` (10.47): a scripted ACP v1 agent as OpenCode 2.2.7 was seen to behave (adapters/NOTES-layer10.md,
"OpenCode 2.2.7 on a real install" and the V2 ACP reference). It reads OPENCODE_CONFIG_CONTENT, and when the inline
config names the umwayi plugin it behaves as the plugin does: it writes the canary token at session/new (the plugin
does it on session.created, 2 ms before the answer), and before every tool call it runs the hook of the plugin's options
(exec form, the tool call as JSON on stdin, 10 s) and applies index.js's rule: exit 0 with an "allow" line lets the call
go on, exit 3 with an "ask" line lets it go on only for the nine tools OpenCode asks permission for, anything else fails
the call with the fixed text and no permission request. A tool that OpenCode asks permission for then gets a
session/request_permission (the V2 toolCall shape of 10.42) when an ask rule or the plugin is in the config.

"acp" settings (all optional):
  canary            "session_new" (default) | "never" | "late" (after canary_delay seconds) | "wrong" (another token) |
                    "first_prompt"
  canary_delay      seconds, for "late"
  model             the model the session reports, instead of the one in the inline config
  ignore_config     OpenCode ignores the inline config: no plugin, no canary, no ask rule, the free default model
  auth_required     "session_new" | "prompt": that call answers with the ACP auth_required error
  init              "garbage" | {"protocolVersion": N} | {"error": {...}}
  turns             one list of actions per session/prompt; actions: {"chunk": TEXT}, {"tool": NAME, "input": {...},
                    "child": true, "no_name": true, "call_id": TEXT}, {"sleep": S}, {"wait_cancel": true},
                    {"exit": N}, {"spawn": true}
  ignore_eof        keep running when stdin is closed
  stderr            text written to stderr at the start
"""
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time

ARGS = sys.argv[1:]
HERE = os.path.dirname(os.path.realpath(sys.argv[0]))
with open(os.path.join(HERE, "opencode-fake.json"), encoding="utf-8") as f:
    CFG = json.load(f)

DENIED = "umwayi: this tool call was not allowed by the rules"
ASKED = {"read", "glob", "grep", "write", "edit", "shell", "webfetch", "question", "subagent"}
KIND = {"read": "read", "glob": "search", "grep": "search", "write": "edit", "edit": "edit", "shell": "execute",
        "webfetch": "fetch", "question": "other", "execute": "other", "subagent": "think"}
OPTIONS = [{"optionId": "once", "kind": "allow_once", "name": "Allow once"},
           {"optionId": "always", "kind": "allow_always", "name": "Always allow"},
           {"optionId": "reject", "kind": "reject_once", "name": "Reject"}]
FREE_DEFAULT = "opencode/big-pickle"


def rec(**kw):
    kw.setdefault("prog", "opencode")
    kw["t"] = time.time()
    with open(CFG["fake_log"], "a", encoding="utf-8") as f:
        f.write(json.dumps(kw) + "\n")


# ------------------------------------------------------------------------------------------------ --version

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

if ARGS != ["acp"]:
    rec(argv=ARGS, cwd=os.getcwd(), started=True, pid=os.getpid(), env_keys=sorted(os.environ))
    sys.exit(0)

# ------------------------------------------------------------------------------------------------ opencode acp

SPEC = CFG.get("acp", {})
inbox = queue.Queue()
rec(argv=ARGS, cwd=os.getcwd(), started=True, mode="acp", pid=os.getpid(), pgid=os.getpgid(0), sid=os.getsid(0),
    env_keys=sorted(os.environ), config_content=os.environ.get("OPENCODE_CONFIG_CONTENT"))


def reader():  # records every line the moment it arrives, so a test sees it even if a signal ends us next
    for line in sys.stdin:
        msg = json.loads(line)
        rec(event="acp_in", msg=msg)
        if msg.get("method") == "session/cancel":
            rec(event="got_cancel")
        inbox.put(msg)
    rec(event="acp_eof")
    inbox.put(None)


threading.Thread(target=reader, daemon=True).start()


def on_term(signum, frame):
    rec(event="term")
    time.sleep(0.3)
    os._exit(143)


signal.signal(signal.SIGTERM, on_term)
if SPEC.get("stderr"):
    sys.stderr.write(SPEC["stderr"] + "\n")
    sys.stderr.flush()
pending = []


def send(obj):
    sys.stdout.write((obj if isinstance(obj, str) else json.dumps(obj)) + "\n")
    sys.stdout.flush()


def recv():
    msg = inbox.get()
    if msg is None:
        if SPEC.get("ignore_eof"):
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


def error(m, code, message):
    send({"jsonrpc": "2.0", "id": m["id"], "error": {"code": code, "message": message}})


# --- the inline config, and the plugin it names

raw_config = os.environ.get("OPENCODE_CONFIG_CONTENT")
config = {}
if raw_config is not None and not SPEC.get("ignore_config"):
    try:
        config = json.loads(raw_config)
    except ValueError:  # V2 stops on an inline config it cannot parse (source, 10.41)
        sys.stderr.write("Error: OPENCODE_CONFIG_CONTENT is not valid JSON\n")
        rec(event="config_invalid")
        sys.exit(1)
plugin = None
for entry in config.get("plugins", []) if isinstance(config, dict) else []:
    opts = entry.get("options") if isinstance(entry, dict) else None
    if isinstance(opts, dict) and isinstance(opts.get("hook"), list) and isinstance(opts.get("canary"), str) \
            and isinstance(opts.get("token"), str):
        plugin = opts
ask_rule = any(r.get("action") == "*" and r.get("effect") == "ask" for r in config.get("permissions", [])) \
    if isinstance(config, dict) else False
model = SPEC.get("model") or (config.get("model") if isinstance(config, dict) and config.get("model") else FREE_DEFAULT)


def write_canary(token):
    try:
        fd = os.open(plugin["canary"], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(token)
        rec(event="canary", written=True, token_ok=token == plugin["token"])
    except OSError as e:
        rec(event="canary", written=False, error=type(e).__name__)


def canary_now():
    if plugin is None:
        return
    mode = SPEC.get("canary", "session_new")
    if mode == "session_new":
        write_canary(plugin["token"])
    elif mode == "wrong":
        write_canary("0" * len(plugin["token"]))
    elif mode == "late":
        threading.Timer(float(SPEC.get("canary_delay", 1)), write_canary, args=(plugin["token"],)).start()


def hook_verdict(tool, tool_input):
    """The plugin's `ask()`: 'allow', 'ask' or 'deny'. Exit code and the decision in the one JSON line must agree."""
    try:
        r = subprocess.run(plugin["hook"], input=json.dumps({"tool_name": tool, "tool_input": tool_input}).encode(),
                           capture_output=True, timeout=10, shell=False)
        decision = json.loads(r.stdout.decode("utf-8")).get("decision")
    except Exception:
        return "deny"
    if r.returncode == 0 and decision == "allow":
        return "allow"
    return "ask" if r.returncode == 3 and decision == "ask" else "deny"


# --- the protocol

m = next_msg(lambda x: x.get("method") == "initialize")
init = SPEC.get("init", {})
if init == "garbage":
    send("this is not json")
elif "error" in init:
    send({"jsonrpc": "2.0", "id": m["id"], "error": init["error"]})
else:
    send({"jsonrpc": "2.0", "id": m["id"], "result": {
        "protocolVersion": init.get("protocolVersion", 1),
        "agentCapabilities": {"loadSession": True, "mcpCapabilities": {"http": True, "sse": False},
                              "promptCapabilities": {"embeddedContext": True, "image": True}},
        "authMethods": [{"id": "opencode-login", "name": "Login with opencode"}]}})

m = next_msg(lambda x: x.get("method") == "session/new")
cwd = (m.get("params") or {}).get("cwd")
if not (isinstance(cwd, str) and os.path.isabs(cwd)):
    error(m, -32602, "Invalid params: cwd must be an absolute path")
    sys.exit(0)
if SPEC.get("auth_required") == "session_new":
    error(m, -32000, "auth_required")
    sys.exit(0)
SID = "ses_fake0000000001"
canary_now()
send({"jsonrpc": "2.0", "id": m["id"], "result": {"sessionId": SID, "configOptions": [
    {"id": "model", "name": "Model", "category": "model", "type": "select", "currentValue": model,
     "options": [{"value": model, "name": model}]},
    {"id": "effort", "name": "Effort", "category": "thought_level", "type": "select", "currentValue": "default",
     "options": [{"value": v, "name": v.title()} for v in ("low", "medium", "high", "default")]},
    {"id": "mode", "name": "Session Mode", "category": "mode", "type": "select", "currentValue": "build",
     "options": [{"value": "build", "name": "Build"}, {"value": "plan", "name": "Plan"}]}]}})

turns = list(SPEC.get("turns", []))
rid = 1000
call_n = [0]


def update(u):
    send({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": SID, "update": u}})


def title_of(tool, inp):
    if tool in ("read", "write", "edit"):
        return str(inp.get("path", tool))
    if tool == "shell":
        return str(inp.get("command", tool))
    if tool in ("grep", "glob"):
        return str(inp.get("pattern", tool))
    if tool == "webfetch":
        return str(inp.get("url", tool))
    return tool


def tool_call(tool, inp, call_id, child, no_name):
    path = inp.get("path")
    locations = ([{"path": path}] if isinstance(path, str) else []) if tool in ("read", "write", "edit", "grep", "glob") \
        else ([{"path": cwd}] if tool == "shell" else [])
    title = title_of(tool, inp)
    call = {"toolCallId": call_id, "name": tool, "title": ("look: " + title) if child else title,
            "kind": KIND.get(tool, "other"), "status": "pending", "locations": locations,
            "rawInput": dict(inp, cwd=cwd) if tool == "shell" and "cwd" not in inp else inp}
    if tool in ("write", "edit"):
        call["content"] = [{"type": "diff", "path": path, "newText": "(diff)"}]
    if child:
        call["_meta"] = {"opencode/child-session": {"id": "ses_child0000000001", "parentID": SID, "depth": 1,
                                                    "title": "look"}}
    if no_name:  # OpenCode had no tool for the request (10.42, from the source)
        del call["name"]
        del call["rawInput"]
    return call


def run_tool(act):
    """One tool call: the plugin's hook first, then the permission request, then the result."""
    global rid
    tool, inp = act["tool"], act.get("input", {})
    call_n[0] += 1
    call_id = act.get("call_id") or (f"ses_child0000000001:call_{call_n[0]}" if act.get("child") else f"call_{call_n[0]}")
    call = tool_call(tool, inp, call_id, act.get("child"), act.get("no_name"))
    update(dict(call, sessionUpdate="tool_call"))
    verdict = hook_verdict(tool, inp) if plugin is not None else None
    rec(event="tool", tool=tool, verdict=verdict, call_id=call_id)
    if verdict == "deny" or (verdict == "ask" and tool not in ASKED):
        # the plugin throws: the call fails with the fixed text and no permission request is made
        update({"sessionUpdate": "tool_call_update", "toolCallId": call_id, "status": "failed",
                "content": [{"type": "content", "content": {"type": "text", "text": DENIED}}]})
        return
    outcome = "once"
    if tool in ASKED and (plugin is not None or ask_rule):
        rid += 1
        send({"jsonrpc": "2.0", "id": rid, "method": "session/request_permission",
              "params": {"sessionId": SID, "toolCall": call, "options": OPTIONS}})
        rec(event="request_sent", tool=tool, call_id=call_id)
        r = next_msg(lambda x, rid=rid: x.get("id") == rid and "method" not in x)
        chosen = ((r.get("result") or {}).get("outcome") or {})
        outcome = chosen.get("optionId") if chosen.get("outcome") == "selected" else "cancelled"
        rec(event="permission_answer", tool=tool, call_id=call_id, outcome=outcome, answer=r)
    if outcome in ("once", "always"):
        update({"sessionUpdate": "tool_call_update", "toolCallId": call_id, "status": "completed",
                "content": [{"type": "content", "content": {"type": "text", "text": f"(fake) {tool} done"}}]})
    else:
        update({"sessionUpdate": "tool_call_update", "toolCallId": call_id, "status": "failed",
                "content": [{"type": "content", "content": {"type": "text", "text": "The user rejected this tool call."}}]})


first_prompt = True
while True:
    m = next_msg(lambda x: x.get("method") in ("session/prompt", "session/set_mode", "session/cancel"))
    if m["method"] == "session/cancel":
        continue
    if m["method"] == "session/set_mode":
        send({"jsonrpc": "2.0", "id": m["id"], "result": {}})
        continue
    if SPEC.get("auth_required") == "prompt":
        error(m, -32000, "auth_required")
        continue
    if first_prompt and SPEC.get("canary") == "first_prompt" and plugin is not None:
        write_canary(plugin["token"])
    first_prompt = False
    text = m["params"]["prompt"][0]["text"]
    actions = turns.pop(0) if turns else [{"chunk": f"you said: {text}"}]
    stop = "end_turn"
    for act in actions:
        if "chunk" in act:
            update({"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": act["chunk"]}})
        if "tool" in act:
            run_tool(act)
        if "sleep" in act:
            time.sleep(act["sleep"])
        if "wait_cancel" in act:
            next_msg(lambda x: x.get("method") == "session/cancel")
            stop = "cancelled"
        if "spawn" in act:
            p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
            rec(event="spawn", pid=p.pid)
        if "exit" in act:
            rec(event="exit", code=act["exit"])
            sys.exit(act["exit"])
    send({"jsonrpc": "2.0", "id": m["id"], "result": {"stopReason": stop, "usage": {
        "inputTokens": 10, "outputTokens": 5, "totalTokens": 15}, "_meta": {}}})
