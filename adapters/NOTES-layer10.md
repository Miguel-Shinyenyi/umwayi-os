# Notes for layer 10: starting agents through their own command line or ACP

What the official docs say about starting Claude Code and Kiro from a script, and about the Agent Client Protocol (ACP), written down before any layer 10 code (tasks.md 10.0). Layer 9 hook facts are in [NOTES.md](NOTES.md) and are not repeated here.

Read on Nov 8 2026. Docs change: check the links again before you rely on a detail. Everything here is in my own words. Where a page does not say something, this file says so instead of guessing. A line marked **Not documented** means the pages I read are silent on it; a line marked **Conflict** means two pages disagree.

Pages read:

| platform | pages |
| --- | --- |
| ACP | [llms.txt index](https://agentclientprotocol.com/llms.txt), [Overview](https://agentclientprotocol.com/protocol/v1/overview.md), [Initialization](https://agentclientprotocol.com/protocol/v1/initialization.md), [Prompt Turn](https://agentclientprotocol.com/protocol/v1/prompt-turn.md), [Tool Calls](https://agentclientprotocol.com/protocol/v1/tool-calls.md), [Transports](https://agentclientprotocol.com/protocol/v1/transports.md), [Security Considerations](https://agentclientprotocol.com/protocol/v1/security.md), [Agents](https://agentclientprotocol.com/get-started/agents.md) |
| Claude Code | [CLI reference](https://code.claude.com/docs/en/cli-reference), [Run Claude Code programmatically](https://code.claude.com/docs/en/headless.md), [Settings files and precedence](https://code.claude.com/docs/en/settings.md), [Hooks reference](https://code.claude.com/docs/en/hooks.md) (configuration, disabling hooks, workspace trust) |
| Kiro | [llms.txt index](https://kiro.dev/llms.txt), [CLI commands](https://kiro.dev/docs/reference/cli-commands.md), [Headless mode](https://kiro.dev/docs/cli/headless.md), [Exit codes](https://kiro.dev/docs/reference/exit-codes.md), [ACP (CLI)](https://kiro.dev/docs/cli/acp.md), [ACP overview](https://kiro.dev/docs/acp.md), [Migrate an ACP client to CLI V3](https://kiro.dev/docs/cli/v3/acp-migration.md) |

The Kiro pages were read as the Markdown copies listed in `kiro.dev/llms.txt`, as for layer 9. No agent was started and no command from these pages was run.

## Agent Client Protocol (ACP)

### Transport and messages

- ACP is JSON-RPC 2.0. Requests get a result or an error; notifications get no answer. ([Overview](https://agentclientprotocol.com/protocol/v1/overview.md))
- The one defined transport is stdio: the client starts the agent as a child process, writes to its stdin and reads its stdout. Each message is one line ending in `\n`, with no newline inside it, in UTF-8. The agent may log to stderr. Neither side may write anything that is not an ACP message to the other's stdin or stdout. ([Transports](https://agentclientprotocol.com/protocol/v1/transports.md))
- An HTTP transport is still being specified. ([Transports](https://agentclientprotocol.com/protocol/v1/transports.md))
- All file paths in the protocol must be absolute. ([Overview](https://agentclientprotocol.com/protocol/v1/overview.md))

### The flow a client follows

1. `initialize`, with the newest protocol version the client supports (an integer, today `1`) and its capabilities. The agent answers with the same version if it supports it, or its own newest one; if the client does not support that, it should close the connection. ([Initialization](https://agentclientprotocol.com/protocol/v1/initialization.md))
2. Authentication, if the agent asks for it. ([Overview](https://agentclientprotocol.com/protocol/v1/overview.md))
3. `session/new` (or `session/load` when the agent supports it). ([Overview](https://agentclientprotocol.com/protocol/v1/overview.md))
4. `session/prompt` with `sessionId` and `prompt`, a list of content blocks such as `{"type": "text", "text": "..."}`. ([Prompt Turn](https://agentclientprotocol.com/protocol/v1/prompt-turn.md))
5. While it works, the agent sends `session/update` notifications: message chunks, `tool_call`, `tool_call_update`, plans and others. The turn ends when the agent answers the `session/prompt` request with a `stopReason`: `end_turn`, `max_tokens`, `max_turn_requests`, `refusal` or `cancelled`. ([Prompt Turn](https://agentclientprotocol.com/protocol/v1/prompt-turn.md))
6. The client may send `session/cancel` at any time; it must then answer every open permission request with the `cancelled` outcome. ([Prompt Turn](https://agentclientprotocol.com/protocol/v1/prompt-turn.md))

### Client methods the agent may call

- `session/request_permission` is the one method every client must have. File system methods (`fs/read_text_file`, `fs/write_text_file`) and terminal methods (`terminal/create` and others) are optional and only used when the client advertised the capability in `initialize`. ([Overview](https://agentclientprotocol.com/protocol/v1/overview.md))
- If the client does not offer `fs` or `terminal`, the agent cannot ask the client to read, write or run anything. ([Overview](https://agentclientprotocol.com/protocol/v1/overview.md), capabilities are opt-in)

### Permission requests: the client cannot see every tool call

- **The agent runs tool calls itself**, and it **may** ask permission first. It is not required to. ([Tool Calls](https://agentclientprotocol.com/protocol/v1/tool-calls.md), [Prompt Turn](https://agentclientprotocol.com/protocol/v1/prompt-turn.md))
- Permission requests are advisory: the agent carries out its own operations and is trusted to honour the answer. ACP does not sandbox the agent. The page lists "an Agent can act without asking" as a remaining risk. ([Security Considerations](https://agentclientprotocol.com/protocol/v1/security.md))
- A permission request has a `toolCall` (at least `toolCallId`) and a list of `options`, each with `optionId`, `name` and `kind`: `allow_once`, `allow_always`, `reject_once` or `reject_always`. The client answers `{"outcome": {"outcome": "selected", "optionId": ...}}` or `{"outcome": {"outcome": "cancelled"}}`. ([Tool Calls](https://agentclientprotocol.com/protocol/v1/tool-calls.md))
- With `allow_always` or `reject_always`, the agent remembers the choice and decides its scope. ([Tool Calls](https://agentclientprotocol.com/protocol/v1/tool-calls.md))
- Automatic approval should not rest only on the `title` or the option `name`; agents should not count an unknown outcome as approval. ([Tool Calls](https://agentclientprotocol.com/protocol/v1/tool-calls.md))
- A tool call carries `toolCallId`, `title` (written by the agent, for people), and optionally `name`, `kind` (`read`, `edit`, `delete`, `move`, `search`, `execute`, `think`, `fetch`, `switch_mode`, `other`), `locations` and `rawInput` (any JSON). The `name` is informational and grants nothing. ([Tool Calls](https://agentclientprotocol.com/protocol/v1/tool-calls.md))

**What this means for umwayi:** an ACP connection alone cannot put umwayi in front of every tool call. It can only answer the requests the agent chooses to send. So the gate for an ACP agent must still be the platform's own hook (layer 9); answering permission requests through `umwayi check` is a second gate, not the first.

### Security guidance for clients

- Treat every string, path and link from the agent as untrusted. `agentInfo` is self-reported and should not be used for security decisions; the client should know the agent from its own launch configuration. ([Security Considerations](https://agentclientprotocol.com/protocol/v1/security.md))
- A client that prints agent text to a terminal should neutralise terminal control sequences, and should show or remove bidirectional, zero-width and tag characters in commands and paths. ([Security Considerations](https://agentclientprotocol.com/protocol/v1/security.md))
- The client's own commands should stay distinguishable from the agent's slash commands. ([Security Considerations](https://agentclientprotocol.com/protocol/v1/security.md))
- An intermediary should not answer permission requests for the user except under a policy the user set. ([Security Considerations](https://agentclientprotocol.com/protocol/v1/security.md)) umwayi's rules are that policy.

### Which agents speak ACP

- The ACP agents list names Kiro CLI directly, and "Claude Agent" only through Zed's SDK adapter ([github.com/zed-industries/claude-agent-acp](https://github.com/zed-industries/claude-agent-acp)). ([Agents](https://agentclientprotocol.com/get-started/agents.md))
- **Not documented** in the Claude Code pages I read: an ACP mode in the `claude` command itself. So Claude Code over ACP would need that third-party adapter, which is out of scope for Dec 3 (design.md, layer 10).
- There is also an ACP v2 in the index; umwayi would speak v1 only. ([llms.txt](https://agentclientprotocol.com/llms.txt))

### Not documented or not confirmed for ACP

- Whether an agent's own hooks run inside an ACP session is up to each agent, not the protocol.
- How long a client should wait for an answer: the pages set no timeouts.

## Claude Code command line

### Starting a run without the interactive screen

- `claude -p "query"` (`--print`) runs once and exits. ([CLI reference](https://code.claude.com/docs/en/cli-reference))
- It exits 0 on success and non-zero when the run fails. An invalid flag is reported on stderr before the run; a failure inside the run, such as missing sign-in, is printed as the result on stdout. ([Run Claude Code programmatically](https://code.claude.com/docs/en/headless.md))
- Stopped with SIGTERM, a `-p` run exits 143, ends the process tree of a running Bash command, runs only `SessionEnd` hooks and starts no new tool call. ([Run Claude Code programmatically](https://code.claude.com/docs/en/headless.md))
- `--max-turns N` limits agentic turns in print mode; there is no limit by default. `--max-budget-usd` stops at an estimated spend, which can pass the cap. ([CLI reference](https://code.claude.com/docs/en/cli-reference))
- `--permission-mode` takes `default`, `acceptEdits`, `plan`, `auto`, `dontAsk`, `bypassPermissions` (and `manual` for `default`), and overrides `defaultMode` from settings files. `--dangerously-skip-permissions` equals `bypassPermissions`. ([CLI reference](https://code.claude.com/docs/en/cli-reference))
- `claude -v` (`--version`) prints the version number. **Not documented:** the exact format of that output. ([CLI reference](https://code.claude.com/docs/en/cli-reference))
- **Not documented:** a way to give `-p` its prompt only on stdin with no prompt argument. The reference shows piped content together with a prompt argument (`cat file | claude -p "query"`). It also does not say whether `--` ends the flags, so a prompt that starts with `-` could be read as a flag. ([CLI reference](https://code.claude.com/docs/en/cli-reference))

### Adding the layer 9 hook for one session, without editing a file

- `--settings` takes a path or an **inline JSON string**. It applies above the user, project and local settings files and below managed settings, for that session only, and writes no file. ([CLI reference](https://code.claude.com/docs/en/cli-reference), [Settings, change a setting for one session](https://code.claude.com/docs/en/settings.md))
- Hook entries **merge** across settings levels instead of replacing each other. ([Hooks reference, hook locations](https://code.claude.com/docs/en/hooks.md))
- `disableAllHooks: true` in any settings file turns hooks off. The value left after precedence wins, and `--settings` is above project and local files, so `--settings '{"disableAllHooks": false, ...}'` overrides a `true` in those files. ([Hooks reference, disable or remove hooks](https://code.claude.com/docs/en/hooks.md))
- **Managed settings can still turn our hook off and umwayi cannot see it**: `allowManagedHooksOnly` blocks user, project, local and plugin hooks, and `strictPluginOnlyCustomization` can lock hooks to plugins. Nothing in `--settings` overrides a managed key. ([Hooks reference, hook locations and limits on skill hooks](https://code.claude.com/docs/en/hooks.md), [Settings precedence](https://code.claude.com/docs/en/settings.md)) **Not documented:** whether hooks given with `--settings` count as "user" hooks for `allowManagedHooksOnly`. Assume they are blocked.
- **`--bare` skips hooks, including hooks passed with `--settings`.** The page says plainly not to use bare mode when you need them. ([Run Claude Code programmatically, bare mode](https://code.claude.com/docs/en/headless.md))
- In a `-p` run Claude Code shows no workspace trust dialog and treats the folder as trusted, so hooks from settings files run (including a project's `.claude/settings.json` hooks). ([Hooks reference, workspace trust](https://code.claude.com/docs/en/hooks.md))
- In an interactive session Claude Code holds back hooks from every settings file until the folder is trusted. **Not documented:** whether that also holds back hooks passed with `--settings`, and whether any tool can run before the trust dialog is answered. ([Hooks reference, workspace trust](https://code.claude.com/docs/en/hooks.md))
- In a `-p` run, broken user, project or local settings are skipped without a dialog and the run goes on. ([Settings, fix a broken settings file](https://code.claude.com/docs/en/settings.md)) **Not documented:** what happens when the `--settings` JSON itself is rejected. umwayi builds it from a fixed template and tests it, but cannot confirm Claude Code accepts it without a real run.
- `onFailure: "block"` (layer 9) needs Claude Code v2.1.295 or later. ([NOTES.md](NOTES.md))

### What layer 10 takes from this

| need | flag |
| --- | --- |
| one run, then exit | `-p`, prompt as the last argument |
| our hook for this session only, no file written | `--settings` with inline JSON: `disableAllHooks: false` and one `PreToolUse` hook, matcher `*`, exec form, `timeout: 30`, `onFailure: "block"` |
| no setting may skip permissions | `--permission-mode default`, always |
| never | `--bare`, `--dangerously-skip-permissions`, `--allow-dangerously-skip-permissions`, `--permission-mode bypassPermissions`, a second `--settings`, `--setting-sources` |
| a limit on turns | `--max-turns`, from agents.yaml |

## Kiro command line

### Starting a run without the interactive screen

- `kiro-cli chat --no-interactive` runs one instruction and exits. The instruction is a positional argument **or piped stdin**: when stdin is piped and there is no positional argument, Kiro reads the whole stream as the instruction. ([Headless mode](https://kiro.dev/docs/cli/headless.md))
- **Name the harness.** A local headless run that names none runs V2 (with exceptions); the page says to add `--v3` or `--v2`. ([Headless mode](https://kiro.dev/docs/cli/headless.md))
- **Hooks in headless runs:** from Kiro CLI 2.27.1, V3 non-interactive runs load hooks from the selected agent and the workspace, and a `PreToolUse` hook can deny a call. A hook that blocks is final with either trust flag. ([Headless mode, V3 hooks](https://kiro.dev/docs/cli/headless.md)) **Not documented:** whether V2 headless runs load hooks. So umwayi always passes `--v3`.
- **Nobody approves tools in a headless run.** A tool that needs approval is denied. `--trust-all-tools` approves every tool (and approves hook confirmation requests). `--trust-tools=ID,ID` approves exact internal tool IDs in non-interactive V3; interactive V3 ignores it. ([Headless mode](https://kiro.dev/docs/cli/headless.md), [CLI commands](https://kiro.dev/docs/reference/cli-commands.md))
- `--agent NAME` picks an agent; if it is not available the run exits 4. The page warns that Kiro can notice this after the turn started, so the default agent may already have made tool calls. ([Exit codes](https://kiro.dev/docs/reference/exit-codes.md))
- `--sandbox` makes a V3 headless run stop before it starts when the local command sandbox cannot start. Without it, Kiro warns and runs without the sandbox. ([Headless mode, local command sandbox](https://kiro.dev/docs/cli/headless.md))
- Headless runs need a signed-in account or `KIRO_API_KEY`. ([Headless mode](https://kiro.dev/docs/cli/headless.md)) umwayi never reads, stores or logs it.
- `kiro-cli --version` (`-V`) shows the version. **Not documented:** its output format. ([CLI commands](https://kiro.dev/docs/reference/cli-commands.md))

### Exit codes

| code | meaning ([Exit codes](https://kiro.dev/docs/reference/exit-codes.md)) |
| --- | --- |
| 0 | success |
| 1 | general failure (sign-in, bad arguments, failed operation) |
| 3 | an MCP server required by `--require-mcp-startup` did not start |
| 4 | the requested agent was not found |

- If stdout closes before the end, Kiro exits non-zero. ([Headless mode](https://kiro.dev/docs/cli/headless.md))
- **Not documented:** what Kiro does on SIGTERM, and which exit code it gives then.

### Interactive chat

- `kiro-cli chat` (or `kiro-cli`) starts the interactive chat. `--v3` picks the V3 harness for that session; from Kiro CLI 3.0.0 an interactive launch that names no harness starts V3 where it can. ([CLI commands](https://kiro.dev/docs/reference/cli-commands.md))
- **Not documented:** a flag that adds a hook for one session, like Claude Code's `--settings`. Hooks come from `.kiro/hooks/`, `~/.kiro/hooks/` (CLI V3) or the agent configuration. ([NOTES.md](NOTES.md), [Headless mode](https://kiro.dev/docs/cli/headless.md)) So umwayi cannot add the Kiro hook itself; it can only check, read only, that the owner added it.

### Kiro as an ACP agent

- `kiro-cli acp` runs Kiro as an ACP agent over stdin and stdout with JSON-RPC 2.0. `--agent-engine v3` picks the harness and overrides the `acp.agentEngine` setting. ([ACP (CLI)](https://kiro.dev/docs/cli/acp.md), [CLI commands](https://kiro.dev/docs/reference/cli-commands.md))
- For V3, the migration guide says to start `kiro-cli acp --agent-engine=v3`, and that V3 rejects `--agent`, `--model`, `--effort`, `--trust-all-tools` and `--trust-tools` on `acp`. Both server generations negotiate protocol version 1, so the version number does not tell them apart. ([Migrate an ACP client to CLI V3](https://kiro.dev/docs/cli/v3/acp-migration.md))
- Signed out, `kiro-cli acp` answers `initialize` with one authentication method and gives an authentication-required error for every other request. ([ACP (CLI)](https://kiro.dev/docs/cli/acp.md))
- V3 permission requests use the standard `options[]`, and may add `_meta.kiro.consent` (`capability`, `resource`, `workspaceRoot`). A client must never invent an option the agent did not offer. ([Migrate an ACP client to CLI V3](https://kiro.dev/docs/cli/v3/acp-migration.md))
- A client must register its `session/update` and `session/request_permission` handlers before it creates a session, must not resend a prompt after a dropped connection, and must return an explicit JSON-RPC error for agent-to-client requests it does not support. Unknown update types must not fail the session. ([Migrate an ACP client to CLI V3](https://kiro.dev/docs/cli/v3/acp-migration.md), [ACP overview](https://kiro.dev/docs/acp.md))
- **Hooks in ACP sessions:** the ACP overview says the shared harness applies the same project configuration, permissions and hooks "when available for a session", whichever client opened it. ([ACP overview](https://kiro.dev/docs/acp.md)) **Not confirmed:** that a Pre Tool Use command hook from `.kiro/hooks/` runs in a `kiro-cli acp --agent-engine=v3` session. The page qualifies it and gives no ACP specific statement.
- **Conflict:** the `session/prompt` example on the Kiro ACP page puts the message in `content`; the ACP spec names the field `prompt`. ([ACP (CLI)](https://kiro.dev/docs/cli/acp.md), [Prompt Turn](https://agentclientprotocol.com/protocol/v1/prompt-turn.md)) That example is on the page for the legacy CLI v2 server. umwayi would send `prompt`, per the spec; not confirmed against a real V3 server.
- Pre Tool Use hooks exist in the Kiro IDE and CLI, not in Web sessions. ([NOTES.md](NOTES.md))

### What layer 10 takes from this

| need | how |
| --- | --- |
| one run, then exit | `kiro-cli chat --v3 --no-interactive`, instruction on stdin (never a positional argument) |
| tools allowed in a headless run | `--trust-tools=` with the IDs from agents.yaml; never `--trust-all-tools` |
| the gate | the owner's `.kiro/hooks/*.json` (workspace) or `~/.kiro/hooks/*.json` file with the layer 9 Kiro hook, checked read only before every start |
| chat on the terminal | `kiro-cli chat --v3` |
| chat over ACP | `kiro-cli acp --agent-engine=v3`, umwayi as a small ACP client that offers no `fs` and no `terminal` |

## Summary: what umwayi can and cannot confirm before it starts an agent

| check | Claude Code | Kiro |
| --- | --- | --- |
| our hook is configured | yes: umwayi passes it itself with `--settings` | read only: umwayi finds the owner's hook file and compares the command |
| hooks are not switched off by a lower settings file | yes: `disableAllHooks: false` in `--settings` | **not documented** whether anything can switch Kiro hooks off |
| hooks are not blocked by managed policy | **no**: invisible to umwayi | **not documented** |
| the hook script starts | yes: umwayi runs it once as a self-test | yes: the same self-test |
| a hook that cannot start blocks the call | yes, with `onFailure: "block"` on v2.1.295 or later | **not documented** (layer 9, KNOWN-LIMITS 22) |
| the version is new enough | only if `claude -v` prints a version umwayi can read | only if `kiro-cli --version` prints a version umwayi can read |
| hooks run in this mode | `-p`: yes; interactive: held until the folder is trusted | headless V3 from 2.27.1: yes; interactive CLI: the Hook types page lists Pre Tool Use for the CLI ([NOTES.md](NOTES.md)); ACP: **not confirmed** |
