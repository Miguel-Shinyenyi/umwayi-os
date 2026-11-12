// umwayi gate for OpenCode 2.x (task 10.45, requirement 10.R13.7). Plain JavaScript, Node built-ins only, no package.
// It is the first gate: every tool call is sent to the layer 9 generic adapter (the hook) before it runs, and any
// doubt throws, which stops the call. It prints nothing: stdout of `opencode acp` is the ACP channel.
import { spawnSync } from "node:child_process"
import { closeSync, constants, openSync, writeSync } from "node:fs"
import { isAbsolute } from "node:path"

const TIMEOUT_MS = 10000
const MAX_OUTPUT = 64 * 1024
// The tools seen asking permission on OpenCode 2.2.7 (10.42). For any other tool, Ask me first throws: nothing would
// ask the owner afterwards. Code Mode (`execute` and the `opencode_*` tools inside it) is not on the list.
const ASKED = new Set(["read", "glob", "grep", "write", "edit", "shell", "webfetch", "question", "subagent"])
const TOKEN = /^[A-Za-z0-9_-]{16,128}$/
const DENIED = "umwayi: this tool call was not allowed by the rules"
const BAD_OPTIONS = "umwayi: the gate options are missing or wrong"

const text = (v) => typeof v === "string" && v.length > 0 && !v.includes("\0")

// Only umwayi writes the options: the hook argument list, the canary file and the canary token.
function readOptions(o) {
  const ok = o !== null && typeof o === "object" && Array.isArray(o.hook) && o.hook.length > 0 && o.hook.every(text) &&
    isAbsolute(o.hook[0]) && text(o.canary) && isAbsolute(o.canary) && typeof o.token === "string" && TOKEN.test(o.token)
  if (!ok) throw new Error(BAD_OPTIONS)
  return { hook: [...o.hook], canary: o.canary, token: o.token }
}

// "allow", "ask" or "deny". The hook's exit code (0 allow, 3 ask) and the decision in its one JSON line must agree;
// anything else is a deny: another code, a signal, a timeout, a start error, output that is not that line.
function ask(hook, tool, input) {
  try {
    if (input !== undefined && input !== null && (typeof input !== "object" || Array.isArray(input))) return "deny"
    const r = spawnSync(hook[0], hook.slice(1), {
      input: JSON.stringify({ tool_name: tool, tool_input: input ?? {} }), encoding: "utf8", shell: false,
      timeout: TIMEOUT_MS, killSignal: "SIGKILL", maxBuffer: MAX_OUTPUT, stdio: ["pipe", "pipe", "ignore"],
    })
    if (r.error || r.signal || typeof r.stdout !== "string") return "deny"
    const decision = JSON.parse(r.stdout).decision
    if (r.status === 0 && decision === "allow") return "allow"
    return r.status === 3 && decision === "ask" ? "ask" : "deny"
  } catch {
    return "deny"
  }
}

// The canary: the token, in a new file that only the owner can read. An existing file or link is never overwritten
// or followed, and a failure is not reported: no canary means umwayi refuses the chat.
function writeCanary(path, token) {
  let fd
  try {
    fd = openSync(path, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL, 0o600)
    writeSync(fd, token)
  } finally {
    if (fd !== undefined) closeSync(fd)
  }
}

export default {
  id: "umwayi.gate",
  async setup(ctx) {
    const { hook, canary, token } = readOptions(ctx.options)
    await ctx.tool.hook("execute.before", (event) => {
      const tool = event?.tool
      if (typeof tool !== "string" || tool.length === 0) throw new Error(DENIED)
      const answer = ask(hook, tool, event.input)
      if (answer === "allow" || (answer === "ask" && ASKED.has(tool))) return
      throw new Error(DENIED)
    })
    // A permission request must reach umwayi even if the ask rule of the inline config is lost: allow becomes ask.
    await ctx.permission.hook("evaluate", (event) => {
      if (event && event.effect !== "ask" && event.effect !== "deny") event.effect = "ask"
    })
    const stop = new AbortController()
    void (async () => {
      try {
        for await (const _ of ctx.event.subscribe({ types: ["session.created"], signal: stop.signal })) {
          writeCanary(canary, token)
          break
        }
      } catch {
        // no canary: umwayi refuses the chat
      }
    })()
    return () => stop.abort()
  },
}
