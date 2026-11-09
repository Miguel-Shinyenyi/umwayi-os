"""Layer 10 part 6: a small ACP v1 client over stdio, for `umwayi agent chat` with Kiro (transport acp).

Only the messages written down in adapters/NOTES-layer10.md, nothing else:

  * line-delimited JSON-RPC 2.0 on the agent's stdin and stdout (one JSON object per line);
  * initialize (protocol version 1, no client capabilities: no fs, no terminal, so the agent can
    never ask umwayi to read, write or run anything), session/new, session/prompt per owner line,
    session/cancel on Ctrl-C;
  * session/update: agent text and tool call lines are printed through safe_text; every other
    update type is ignored and never fails the session;
  * session/request_permission: answered through a callback (the rules, in agents.py) and, for
    Ask me first, the owner. Only allow_once or reject_once is ever selected, never an *_always
    option, never an option the agent did not offer; when in doubt reject_once, or cancelled if
    there is no reject_once option;
  * any other request from the agent gets JSON-RPC error -32601 and nothing is done;
  * a line that is not one JSON object (or longer than 4 MB), an error answer, another protocol
    version or a dropped connection ends the chat. A prompt is never sent twice.
  * part 7 (Claude Code), three options, all off for Kiro: session_meta is sent as _meta of
    session/new; gate_ready is polled after session/new for up to 30 s, and the chat ends before
    any owner line is sent if it never says True; set_mode is sent as session/set_mode before
    the first owner line, and an error answer ends the chat.

This module starts no program and imports nothing from umwayi: agents.py starts the agent, owns
the rules, the logbook and the stop, and calls Chat.run().
"""

from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
from collections import deque

PROTOCOL_VERSION = 1
MAX_LINE = 4 * 1024 * 1024  # bytes in one line from the agent
CANCEL_WAIT = 10.0  # seconds to wait for the prompt answer after session/cancel
POLL = 0.1  # seconds between looks at the events
METHOD_NOT_FOUND = -32601
AUTH_REQUIRED = -32000
ALLOW, REJECT, ASK = "allow", "reject", "ask"
SIGN_IN = "Sign in with kiro-cli login, then try again."
GATE_WAIT = 30.0  # seconds after session/new for gate_ready (part 7: the Claude Code canary)
GATE_NOT_CONFIRMED = "the first gate could not be confirmed in the ACP session"
MODE_REFUSED = "the agent did not accept the default permission mode"

_INVISIBLE = ({0x061C, 0x200E, 0x200F, 0x2028, 0x2029, 0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x180E}
              | set(range(0x202A, 0x202F)) | set(range(0x2066, 0x206A)) | set(range(0x2061, 0x2065)))
_SESSION_ID = re.compile(r"^[A-Za-z0-9_.:@/+=-]{1,200}$")


def safe_text(text) -> str:
    """Agent text made safe for a terminal.

    C0 and C1 control characters (other than newline and tab), DEL, and bidirectional,
    zero-width and tag characters are shown as \\uXXXX (\\UXXXXXXXX above U+FFFF), so they can
    neither move the cursor nor hide or reorder what the owner reads.
    """
    out = []
    for ch in str(text):
        o = ord(ch)
        if ch in "\n\t":
            out.append(ch)
        elif o < 0x20 or 0x7F <= o <= 0x9F or o in _INVISIBLE or 0xE0000 <= o <= 0xE007F:
            out.append(f"\\u{o:04x}" if o <= 0xFFFF else f"\\U{o:08x}")
        else:
            out.append(ch)
    return "".join(out)


def select_outcome(options, want: str) -> dict:
    """The permission outcome for `want` (allow_once or reject_once). Never an *_always option, never invented.

    No option of the wanted kind: reject_once if offered, else cancelled.
    """
    def first(kind):
        if isinstance(options, list):
            for o in options:
                if isinstance(o, dict) and o.get("kind") == kind and isinstance(o.get("optionId"), str):
                    return o["optionId"]
        return None

    for kind in ((want, "reject_once") if want == "allow_once" else ("reject_once",)):
        chosen = first(kind)
        if chosen is not None:
            return {"outcome": "selected", "optionId": chosen}
    return {"outcome": "cancelled"}


def read_lines(fd: int, limit: int):
    """Lines (with their newline) from a file descriptor, read with os.read.

    Raw reads take no buffer lock, so a thread blocked here never stops the interpreter from
    exiting and never blocks a close. A line longer than `limit` is given as it is, so the caller
    can refuse it; the last piece without a newline is given at the end.
    """
    buf = b""
    while True:
        i = buf.find(b"\n")
        if i >= 0:
            yield buf[:i + 1]
            buf = buf[i + 1:]
            continue
        if len(buf) > limit:
            yield buf
            return
        chunk = os.read(fd, 65536)
        if not chunk:
            if buf:
                yield buf
            return
        buf += chunk


class _Stop(Exception):
    """The watcher said stop (kill switch, logbook, timeout). token is what the watcher returned."""

    def __init__(self, token):
        super().__init__("stop")
        self.token = token


class _Failed(Exception):
    """The chat cannot go on. why is for the logbook (fixed text, never agent text); lines are for the owner."""

    def __init__(self, why: str, lines: list):
        super().__init__(why)
        self.why = why
        self.lines = lines


class Chat:
    """One ACP chat. run() returns ("done", how) | ("failed", why, lines) | ("stopped", token)."""

    def __init__(self, proc, out, owner, workdir: str, permission, tick, queue_lines, client_version: str,
                 tick_interval: float = 1.0, session_meta=None, gate_ready=None, set_mode=None):
        self.proc = proc
        self.out = out  # the owner's screen
        self.owner = owner  # the owner's input, a file descriptor (stdin)
        self.workdir = workdir
        self.permission = permission  # callback(tool_call dict) -> ALLOW | REJECT | ASK
        self.tick = tick  # callback() -> None, or a token that means stop now
        self.queue_lines = queue_lines  # callback() -> lines for :queue
        self.client_version = client_version
        self.events = queue.Queue()
        self.wlock = threading.Lock()
        self.next_id = 0
        self.responses = {}
        self.lines = deque()  # owner lines not used yet
        self.owner_done = False
        self.perms = deque()  # permission requests not answered yet
        self.turn = None  # the id of the session/prompt in flight
        self.abandoned = set()  # prompt ids whose answer is no longer awaited
        self.sid = None
        self.interrupted = False
        self.mid_line = False
        self.tick_interval = tick_interval  # the same interval as the watcher in agents.py
        self.last_tick = time.monotonic()
        # part 7 (Claude Code); all None for Kiro: no _meta, no waiting, no session/set_mode
        self.session_meta = session_meta  # a dict sent as _meta of session/new
        self.gate_ready = gate_ready  # callback() -> True once the first gate is confirmed
        self.set_mode = set_mode  # a mode id sent with session/set_mode once the gate is confirmed

    # ------------------------------------------------------------ called from the SIGINT handler

    def interrupt(self) -> None:
        self.interrupted = True

    # ------------------------------------------------------------ output

    def say(self, text: str) -> None:
        if self.mid_line and not text.startswith("\n"):
            text = "\n" + text
        self.out.write(text)
        self.out.flush()
        self.mid_line = not text.endswith("\n")

    # ------------------------------------------------------------ writing to the agent

    def _send(self, msg: dict) -> None:
        line = json.dumps(msg, ensure_ascii=False, separators=(",", ":")) + "\n"  # never an embedded newline
        try:
            with self.wlock:
                self.proc.stdin.write(line.encode("utf-8"))
                self.proc.stdin.flush()
        except (OSError, ValueError):
            raise _Failed("the connection to the agent was lost",
                          ["The connection to the agent was lost. The chat ended (exit 2)."]) from None

    def _request(self, method: str, params: dict) -> int:
        self.next_id += 1
        self._send({"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params})
        return self.next_id

    def _notify(self, method: str, params: dict) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _answer(self, req_id, result: dict) -> None:
        self._send({"jsonrpc": "2.0", "id": req_id, "result": result})

    # ------------------------------------------------------------ the two readers

    def _read_agent(self) -> None:
        try:
            for raw in read_lines(self.proc.stdout.fileno(), MAX_LINE):
                if len(raw) > MAX_LINE + 1 or (len(raw) > MAX_LINE and not raw.endswith(b"\n")):
                    self.events.put(("bad", "a line longer than 4 MB"))
                    return
                try:
                    msg = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, ValueError, RecursionError):
                    msg = None
                if not isinstance(msg, dict):
                    self.events.put(("bad", "a line that is not one JSON object"))
                    return
                if "method" in msg and "id" in msg:
                    if msg.get("method") == "session/request_permission":
                        self.events.put(("permission", msg))
                    else:  # fs/*, terminal/*, anything else: refused, nothing is read or run
                        try:
                            with self.wlock:
                                self.proc.stdin.write((json.dumps({"jsonrpc": "2.0", "id": msg["id"], "error": {
                                    "code": METHOD_NOT_FOUND, "message": "Method not found"}}) + "\n").encode("utf-8"))
                                self.proc.stdin.flush()
                        except (OSError, ValueError, TypeError):
                            pass
                elif "method" in msg:
                    self.events.put(("notify", msg))
                elif "id" in msg:
                    self.events.put(("response", msg))
                else:
                    self.events.put(("bad", "a message that is not a request, an answer or a notification"))
                    return
        except (OSError, ValueError):
            pass
        self.events.put(("eof",))

    def _read_owner(self) -> None:
        try:
            for raw in read_lines(self.owner, 1024 * 1024):
                self.events.put(("owner", raw.decode("utf-8", "replace").rstrip("\r\n")))
        except (OSError, ValueError):
            pass
        self.events.put(("owner_eof",))

    # ------------------------------------------------------------ events

    def _pump(self):
        """Handle at most one event; run the watcher once a second. Raises _Stop or _Failed."""
        now = time.monotonic()
        if now - self.last_tick >= self.tick_interval:
            self.last_tick = now
            token = self.tick()
            if token is not None:
                raise _Stop(token)
        try:
            ev = self.events.get(timeout=POLL)
        except queue.Empty:
            return
        kind = ev[0]
        if kind == "owner":
            self.lines.append(ev[1])
        elif kind == "owner_eof":
            self.owner_done = True
        elif kind == "notify":
            self._update(ev[1])
        elif kind == "permission":
            self.perms.append(ev[1])
        elif kind == "response":
            self.responses[ev[1].get("id")] = ev[1]
        elif kind == "eof":
            raise _Failed("the agent closed the connection",
                          ["The agent closed the connection. The chat ended (exit 2); no prompt is sent again."])
        else:
            raise _Failed(f"the agent sent {ev[1]}", [f"The agent sent {ev[1]}. The chat ended (exit 2)."])

    def _call(self, method: str, params: dict) -> dict:
        rid = self._request(method, params)
        while rid not in self.responses:
            self._pump()
            self.interrupted = False  # nothing to cancel before the session exists
        return self.responses.pop(rid)

    def _update(self, msg: dict) -> None:
        params = msg.get("params")
        if msg.get("method") != "session/update" or not isinstance(params, dict):
            return
        u = params.get("update")
        if not isinstance(u, dict):
            return
        kind = u.get("sessionUpdate")
        if kind == "agent_message_chunk":
            c = u.get("content")
            if isinstance(c, dict) and c.get("type") == "text" and isinstance(c.get("text"), str):
                text = safe_text(c["text"])
                self.out.write(text)
                self.out.flush()
                self.mid_line = bool(text) and not text.endswith("\n") or (self.mid_line and not text)
        elif kind == "tool_call":
            title = u.get("title") if isinstance(u.get("title"), str) else "(no title)"
            tkind = u.get("kind") if isinstance(u.get("kind"), str) else "other"
            self.say(f"tool: {safe_text(title)} [{safe_text(tkind)}]\n")
        # every other update type is ignored

    # ------------------------------------------------------------ permission requests

    def _owner_answer(self) -> str | None:
        """The next owner line, '' at the end of input, None after Ctrl-C."""
        while True:
            if self.interrupted:
                return None
            if self.lines:
                return self.lines.popleft()
            if self.owner_done:
                return ""
            self._pump()

    def _serve_permission(self, msg: dict, cancel: bool = False) -> None:
        req_id = msg.get("id")
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        options = params.get("options")
        tool_call = params.get("toolCall") if isinstance(params.get("toolCall"), dict) else {}
        cancel_turn = False
        if cancel:
            outcome = {"outcome": "cancelled"}
        else:
            try:
                verdict = self.permission(tool_call)
            except Exception:
                verdict = REJECT
            if verdict == ALLOW:
                outcome = select_outcome(options, "allow_once")
            elif verdict == ASK:
                title = tool_call.get("title") if isinstance(tool_call.get("title"), str) else "(no title)"
                tkind = tool_call.get("kind") if isinstance(tool_call.get("kind"), str) else "other"
                self.say(f"The agent asks to use a tool: {safe_text(title)} [{safe_text(tkind)}]\n"
                         "The rules say Ask me first. Allow once? [y/N] ")
                answer = self._owner_answer()
                if answer is None:  # Ctrl-C: this request is answered cancelled first, then the turn is cancelled
                    self.say("\n")
                    outcome = {"outcome": "cancelled"}
                    cancel_turn = True
                else:
                    self.mid_line = False
                    outcome = select_outcome(options, "allow_once" if answer.strip() == "y" else "reject_once")
            else:  # REJECT, or anything unknown
                outcome = select_outcome(options, "reject_once")
        if req_id is not None:
            self._answer(req_id, {"outcome": outcome})
        if cancel_turn:
            self._cancel_turn()

    # ------------------------------------------------------------ Ctrl-C

    def _cancel_turn(self) -> None:
        """session/cancel, every open permission answered cancelled, then up to CANCEL_WAIT for the prompt answer."""
        self.interrupted = False
        if self.turn is None:
            self.say("(Ctrl-C: no turn is running. Type :quit to end the chat.)\n")
            return
        self._notify("session/cancel", {"sessionId": self.sid})
        deadline = time.monotonic() + CANCEL_WAIT
        while self.turn not in self.responses and time.monotonic() < deadline:
            while self.perms:
                self._serve_permission(self.perms.popleft(), cancel=True)
            self._pump()
            self.interrupted = False
        while self.perms:
            self._serve_permission(self.perms.popleft(), cancel=True)
        if self.turn in self.responses:
            self._end_turn()
        else:
            self.say(f"The agent did not answer the cancel within {CANCEL_WAIT:.0f} s. Back to you.\n")
            self.abandoned.add(self.turn)
            self.turn = None

    def _end_turn(self) -> None:
        msg = self.responses.pop(self.turn)
        self.turn = None
        if "error" in msg:
            raise _Failed("the agent answered a prompt with an error",
                          ["The agent answered the prompt with an error. The chat ended (exit 2)."])
        result = msg.get("result") if isinstance(msg.get("result"), dict) else {}
        reason = result.get("stopReason") if isinstance(result.get("stopReason"), str) else "(none)"
        self.say(f"[stop reason: {safe_text(reason)}]\n")

    def _cleanup(self) -> None:
        """Before a stop: cancel the turn, answer open permissions cancelled, close the agent's stdin. Best effort."""
        try:
            if self.turn is not None and self.sid is not None:
                self._notify("session/cancel", {"sessionId": self.sid})
            while self.perms:
                self._serve_permission(self.perms.popleft(), cancel=True)
        except _Failed:
            pass
        try:
            self.proc.stdin.close()
        except (OSError, ValueError):
            pass

    # ------------------------------------------------------------ the chat

    def _start_session(self) -> None:
        init = self._call("initialize", {"protocolVersion": PROTOCOL_VERSION, "clientCapabilities": {},
                                         "clientInfo": {"name": "umwayi", "version": self.client_version}})
        self._check_error(init, "initialize")
        version = (init.get("result") or {}).get("protocolVersion") if isinstance(init.get("result"), dict) else None
        if not (isinstance(version, int) and not isinstance(version, bool) and version == PROTOCOL_VERSION):
            raise _Failed("the agent answered another protocol version than 1",
                          [f"The agent answered protocol version {safe_text(repr(version)[:40])}; umwayi speaks only "
                           "version 1. The chat ended (exit 2)."])
        params = {"cwd": self.workdir, "mcpServers": []}
        if self.session_meta is not None:
            params["_meta"] = self.session_meta
        new = self._call("session/new", params)
        self._check_error(new, "session/new")
        sid = (new.get("result") or {}).get("sessionId") if isinstance(new.get("result"), dict) else None
        if not (isinstance(sid, str) and _SESSION_ID.match(sid)):
            raise _Failed("the agent gave no usable session id",
                          ["The agent gave no usable session id. The chat ended (exit 2)."])
        self.sid = sid
        if self.gate_ready is not None:  # nothing of the owner is sent before the gate is confirmed
            deadline = time.monotonic() + GATE_WAIT
            while not self.gate_ready():
                if time.monotonic() >= deadline:
                    raise _Failed(GATE_NOT_CONFIRMED, ["The first gate could not be confirmed in the ACP session. "
                                                       "Nothing was sent."])
                self._pump()  # the watcher still runs; owner lines wait in self.lines
                self.interrupted = False
        if self.set_mode is not None:
            answer = self._call("session/set_mode", {"sessionId": self.sid, "modeId": self.set_mode})
            if "error" in answer:
                raise _Failed(MODE_REFUSED, ["The agent did not accept the default permission mode."])

    @staticmethod
    def _check_error(msg: dict, method: str) -> None:
        err = msg.get("error")
        if err is None:
            return
        code = err.get("code") if isinstance(err, dict) else None
        text = err.get("message") if isinstance(err, dict) and isinstance(err.get("message"), str) else ""
        if code == AUTH_REQUIRED or "auth" in text.lower():
            raise _Failed("the agent needs a sign in", [SIGN_IN])
        raise _Failed(f"the agent answered {method} with an error",
                      [f"The agent answered {method} with an error. The chat ended (exit 2)."])

    def run(self):
        threading.Thread(target=self._read_agent, name="umwayi-acp-agent", daemon=True).start()
        threading.Thread(target=self._read_owner, name="umwayi-acp-owner", daemon=True).start()
        try:
            self._start_session()
            self.say("Connected. Type a message, :queue to see the queue, or :quit to end the chat.\n")
            while True:
                if self.interrupted:
                    self._cancel_turn()
                    continue
                if self.perms:
                    self._serve_permission(self.perms.popleft())
                    continue
                if self.turn is not None and self.turn in self.responses:
                    self._end_turn()
                    continue
                for rid in [r for r in self.responses if r in self.abandoned]:
                    self.responses.pop(rid)  # a late answer to a cancelled turn
                    self.abandoned.discard(rid)
                if self.turn is None and self.lines:
                    line = self.lines.popleft()
                    if line.startswith(":"):
                        cmd = line.strip()
                        if cmd == ":quit":
                            return ("done", "quit")
                        if cmd == ":queue":
                            self.say("\n".join(self.queue_lines()) + "\n")
                        else:
                            self.say("Unknown umwayi command. Use :queue or :quit.\n")
                    elif line.strip():
                        self.turn = self._request("session/prompt", {
                            "sessionId": self.sid, "prompt": [{"type": "text", "text": line}]})
                    continue
                if self.turn is None and self.owner_done:
                    return ("done", "end of input")
                self._pump()
        except _Stop as s:
            self._cleanup()
            return ("stopped", s.token)
        except _Failed as f:
            self._cleanup()
            return ("failed", f.why, f.lines)
