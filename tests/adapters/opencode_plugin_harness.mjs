// Test harness for the umwayi OpenCode plugin (task 10.45). Not umwayi code and not part of any gate.
//
//   node opencode_plugin_harness.mjs PLUGIN_FILE < script.json
//
// It loads the real plugin file with a fake `ctx` that is as strict as OpenCode 2.2.7 was seen to be (10.42): the
// plugin may touch only ctx.options, ctx.tool, ctx.permission and ctx.event, register only the hooks it is allowed
// to, and ask for only the session.created event. It runs each case of the script (a fresh ctx and a fresh setup per
// case) and prints one JSON document with what happened. The Python tests (test_opencode_plugin.py) read it.
//
// script:  {"timeoutMs": N | null, "cases": [{"name": "...", "options": ..., "subscribeThrows": false,
//           "streamThrows": false, "steps": [step, ...]}]}
// steps:   {"op": "setup"}                        run plugin.setup(ctx)
//          {"op": "tool", "tool": ..., "input": ..., "inputKind": "circular"|"bigint", "event": null}
//                                                 call every execute.before callback the plugin registered
//          {"op": "evaluate", "effect": ..., "message": ..., "event": null}
//          {"op": "event", "type": "session.created"}   deliver an event to the subscribers that asked for it
//          {"op": "cleanup", "times": 1}          call the function setup returned
//          {"op": "stat", "path": "..."}          lstat a file (and read it if it is a regular file)
//          {"op": "unlink", "path": "..."}        remove a file (a test of "once": the canary is gone, an event comes again)
//          {"op": "wait", "ms": 20}
import { createHash } from "node:crypto"
import { lstatSync, mkdtempSync, readFileSync, rmSync, unlinkSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { pathToFileURL } from "node:url"

const pluginFile = process.argv[2]
const origOut = process.stdout.write.bind(process.stdout)
const origErr = process.stderr.write.bind(process.stderr)

// Anything the plugin writes to stdout or stderr is recorded, never shown: stdout of `opencode acp` is the ACP channel.
const writes = []
process.stdout.write = (chunk) => { writes.push(["stdout", String(chunk)]); return true }
process.stderr.write = (chunk) => { writes.push(["stderr", String(chunk)]); return true }
const unhandled = []
process.on("unhandledRejection", (e) => unhandled.push(String(e && e.message)))
process.on("uncaughtException", (e) => unhandled.push(String(e && e.message)))

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const describe = (e) => ({ threw: true, name: e && e.name, message: e && e.message, hasCause: !!(e && "cause" in e) })

function makeCtx(spec, record) {
  const real = {
    options: spec.options,
    tool: {
      hook(name, callback) {
        if (name !== "execute.before") throw new Error("fake ctx: the plugin asked for the tool hook " + name)
        record.registered.tool.push(callback)
        return Promise.resolve({ dispose() {} })
      },
    },
    permission: {
      hook(name, callback) {
        if (name !== "evaluate") throw new Error("fake ctx: the plugin asked for the permission hook " + name)
        record.registered.permission.push(callback)
        return Promise.resolve({ dispose() {} })
      },
    },
    event: {
      subscribe(opts) {
        if (spec.subscribeThrows) throw new Error("fake ctx: subscribe failed")
        const sub = { types: opts && opts.types, signalGiven: !!(opts && opts.signal), aborted: false, queue: [], waiter: null }
        record.registered.subscriptions.push(sub)
        const wake = () => { if (sub.waiter) { const w = sub.waiter; sub.waiter = null; w() } }
        if (opts && opts.signal) opts.signal.addEventListener("abort", () => { sub.aborted = true; wake() })
        sub.push = (event) => { sub.queue.push(event); wake() }
        return {
          [Symbol.asyncIterator]() {
            return {
              async next() {
                if (spec.streamThrows) throw new Error("fake ctx: the event stream failed")
                while (sub.queue.length === 0) {
                  if (sub.aborted) return { done: true, value: undefined }
                  await new Promise((resolve) => { sub.waiter = resolve })
                }
                return { done: false, value: sub.queue.shift() }
              },
              async return() { return { done: true, value: undefined } },
            }
          },
        }
      },
    },
  }
  return new Proxy(real, {
    get(target, key) {
      if (typeof key === "symbol") return undefined
      if (!(key in target)) throw new Error("fake ctx: the plugin used ctx." + String(key))
      record.touched.add(key)
      return target[key]
    },
  })
}

function toolEvent(step) {
  if (step.event === null) return null
  const event = {}
  if ("tool" in step) event.tool = step.tool
  if (step.inputKind === "circular") { const o = {}; o.self = o; event.input = o }
  else if (step.inputKind === "bigint") event.input = { n: 10n }
  else if ("input" in step) event.input = step.input
  return event
}

async function runStep(step, state, record) {
  switch (step.op) {
    case "setup": {
      try {
        state.cleanup = await state.plugin.setup(state.ctx)
        return { ok: true, cleanupType: typeof state.cleanup }
      } catch (e) { return describe(e) }
    }
    case "tool": {
      const event = toolEvent(step)
      const outcomes = []
      for (const callback of record.registered.tool) {
        try {
          const returned = callback(event)
          if (returned && typeof returned.then === "function") { await returned; outcomes.push({ ok: true, async: true }) }
          else outcomes.push({ ok: true, returned: typeof returned })
        } catch (e) { outcomes.push(describe(e)) }
      }
      return { outcomes }
    }
    case "evaluate": {
      const event = step.event === null ? null : { effect: step.effect, message: step.message, action: "shell", resources: ["x"] }
      if (event && !("effect" in step)) delete event.effect
      const outcomes = []
      for (const callback of record.registered.permission) {
        try { callback(event); outcomes.push({ ok: true }) } catch (e) { outcomes.push(describe(e)) }
      }
      return { outcomes, effect: event ? event.effect : null, message: event ? event.message : null }
    }
    case "event": {
      for (const sub of record.registered.subscriptions) {
        if (Array.isArray(sub.types) && sub.types.includes(step.type)) sub.push({ type: step.type, id: "ses_x" })
      }
      await sleep(40)
      return { delivered: record.registered.subscriptions.filter((s) => Array.isArray(s.types) && s.types.includes(step.type)).length }
    }
    case "cleanup": {
      for (let i = 0; i < (step.times || 1); i++) {
        try { state.cleanup() } catch (e) { return describe(e) }
      }
      await sleep(40)
      return { ok: true, aborted: record.registered.subscriptions.map((s) => s.aborted) }
    }
    case "stat": {
      try {
        const st = lstatSync(step.path)
        const out = { exists: true, mode: st.mode & 0o7777, size: st.size, isFile: st.isFile(), isSymlink: st.isSymbolicLink() }
        if (st.isFile()) out.content = readFileSync(step.path, "utf8")
        return out
      } catch { return { exists: false } }
    }
    case "unlink": { unlinkSync(step.path); return { ok: true } }
    case "wait": { await sleep(step.ms || 20); return { ok: true } }
    default: throw new Error("harness: unknown step " + step.op)
  }
}

async function main() {
  const script = JSON.parse(readFileSync(0, "utf8"))
  const real = readFileSync(pluginFile, "utf8")
  let source = real
  if (script.timeoutMs) {
    source = real.replace("const TIMEOUT_MS = 10000", `const TIMEOUT_MS = ${Number(script.timeoutMs)}`)
    if (source === real) throw new Error("harness: the timeout constant was not found in the plugin")
  }
  // index.js has no package.json beside it, so Node would read it as CommonJS: import an identical copy named .mjs
  const dir = mkdtempSync(join(tmpdir(), "umwayi-plugin-harness-"))
  const copy = join(dir, "plugin.mjs")
  writeFileSync(copy, source)
  const loaded = await import(pathToFileURL(copy).href)
  rmSync(dir, { recursive: true, force: true })
  const plugin = loaded.default
  const out = {
    sourceSha256: createHash("sha256").update(real).digest("hex"),
    exportKeys: Object.keys(loaded), defaultKeys: plugin ? Object.keys(plugin) : null,
    id: plugin && plugin.id, setupType: plugin && typeof plugin.setup, cases: [],
  }
  for (const spec of script.cases) {
    const record = { registered: { tool: [], permission: [], subscriptions: [] }, touched: new Set() }
    const state = { plugin, ctx: makeCtx(spec, record), cleanup: null }
    const steps = []
    for (const step of spec.steps) steps.push(await runStep(step, state, record))
    await sleep(30)
    out.cases.push({
      name: spec.name, steps,
      registered: { tool: record.registered.tool.length, permission: record.registered.permission.length,
                    subscriptions: record.registered.subscriptions.map((s) => ({ types: s.types, signalGiven: s.signalGiven })) },
      touched: [...record.touched].sort(),
    })
  }
  out.writes = writes
  out.unhandled = unhandled
  return out
}

main().then((out) => { origOut(JSON.stringify(out)); process.exit(0) })
  .catch((e) => { origErr(JSON.stringify({ harnessError: String(e && e.message) })); origOut(JSON.stringify({ harnessError: String(e && e.message) })); process.exit(3) })
