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

## Claude Code over ACP: the claude-agent-acp adapter (part 7, spec only)

Read on Nov 8 2026, for the part 7 spec (tasks.md 10.22 and up). Nothing was installed or run: the facts come from the README, `package.json`, the npm registry and the source of the release tag. Where a line says **from the source**, it is what the code does at that tag, not a documented promise; the next release can change it. **Not documented** means neither the README nor the source answers it.

Sources:

| what | where |
| --- | --- |
| repository (Apache-2.0, default branch main, last push Nov 8 2026) | [github.com/agentclientprotocol/claude-agent-acp](https://github.com/agentclientprotocol/claude-agent-acp) |
| the release read | tag [v0.101.0](https://github.com/agentclientprotocol/claude-agent-acp/tree/v0.101.0), commit `85aec26ef984a421fe8064ce43f60138a3372384` |
| npm package | [@agentclientprotocol/claude-agent-acp](https://www.npmjs.com/package/@agentclientprotocol/claude-agent-acp), registry metadata at [registry.npmjs.org/@agentclientprotocol%2Fclaude-agent-acp](https://registry.npmjs.org/@agentclientprotocol%2Fclaude-agent-acp) |
| README | [README.md at v0.101.0](https://github.com/agentclientprotocol/claude-agent-acp/blob/v0.101.0/README.md) |
| source files cited below | under [src/ at v0.101.0](https://github.com/agentclientprotocol/claude-agent-acp/tree/v0.101.0/src) |
| Agent SDK options and permissions | [Agent SDK TypeScript reference](https://code.claude.com/docs/en/agent-sdk/typescript.md), [Configure permissions](https://code.claude.com/docs/en/agent-sdk/permissions.md) |

### The facts given in the task, confirmed or corrected

| claim | finding |
| --- | --- |
| Apache-2.0 | **Confirmed**: `license` in `package.json` and the repository license. |
| Node 22 or higher | **Confirmed**: `"engines": {"node": ">=22"}` in `package.json` (v0.101.0 and the registry entry of the latest version). |
| uses the Claude Agent SDK | **Confirmed**: dependency `@anthropic-ai/claude-agent-sdk` pinned to exactly `0.3.318`, next to `@agentclientprotocol/sdk` `2.4.0`, `diff` `9.0.0`, `zod` `4.6.7`. |
| auth by `ANTHROPIC_API_KEY` or a claude-login method | **Corrected.** The ACP `authMethods` are terminal methods only: `claude-ai-login` ("Claude Subscription", runs `--cli auth login --claudeai`) and `console-login` ("Anthropic Console", `--cli auth login --console`); on a remote machine (`SSH_CONNECTION`, `SSH_TTY`, `NO_BROWSER` and similar) `claude-login` ("Run `claude /login` in the terminal") instead of the first. **They are only offered when the client declares `clientCapabilities.auth.terminal` or `_meta["terminal-auth"]`**; a `gateway` method only with `auth._meta.gateway`. With `clientCapabilities: {}` the list is empty. (from the source, `initialize` in `src/acp-agent.ts`). `ANTHROPIC_API_KEY` is not an ACP method: the adapter passes its whole environment to the Claude CLI it starts (`env: {...process.env, ...}`), and the CLI reads the key itself (Claude Code behaviour, not documented by the adapter). |
| env vars `ANTHROPIC_BASE_URL`, `CLAUDE_CONFIG_DIR` | **Confirmed from the source**: `CLAUDE_CONFIG_DIR` (or `~/.claude`) is where it looks for user settings (`src/paths.ts`); `ANTHROPIC_BASE_URL` is read for the account and provider routing. Also read from the environment: `CLAUDE_CODE_EXECUTABLE` (use this Claude CLI instead of the bundled one, `src/claude-cli.ts`), `CLAUDE_AGENT_LOGS` (a log folder; the log can hold session details), `IS_SANDBOX` (allows bypass mode when running as root, `src/permissions/modes.ts`), `MAX_THINKING_TOKENS`, `CLAUDE_MODEL_CONFIG`, `CLAUDE_CODE_THINKING_DISPLAY`. None of these is documented in the README. |
| `CLAUDE_AGENT_ACP_PROTOCOL` for v1, v2 or auto | **Confirmed** (README, "Experimental ACP v2"): `v1` negotiates a v2 client down to v1, `v2` rejects a v1 client, `auto` (the default) serves both. |
| session options through `_meta.claudeCode.options` | **Confirmed from the source** (`NewSessionMeta` in `src/acp-agent.ts`): the object is spread into the Agent SDK `Options`. Ignored and set by the adapter: `cwd`, `includePartialMessages`, `permissionMode`, `canUseTool`, `executable`. Merged with the adapter's own: `hooks`, `mcpServers`, `disallowedTools`. `allowDangerouslySkipPermissions: false` removes bypass mode for the session. Not documented in the README. |
| terminals and client MCP servers listed as capabilities | **Partly corrected.** The README lists "Interactive (and background) terminals" and "Client MCP servers" as features. The terminals are a display extension (`_meta.terminal_info`, `terminal_output`) that a client opts into in `clientCapabilities._meta`; the adapter does **not** use ACP `terminal/create` (from the source, `src/tool-calls/renderer.ts`). Client MCP servers are the `mcpServers` of `session/new`. |
| background commands keep running after `session/cancel` | **Confirmed** (README, "Subagent sessions"): "Background commands keep running after a cancel either way." Background subagents also keep running after a parent cancel when the client uses the subagents form. |

### (a) The command to start it, and the version to pin

- **Newest version: `0.101.0`**, the npm `latest` dist-tag on Nov 8 2026. The `preview` tag is `0.101.1-preview.7` (published Nov 8 2026); preview builds are published from every push to main (README) and are not for pinning. Integrity of `0.101.0` in the registry: `sha512-c9YGBfdJrLcKiinRpXuDuibC+CRGqQpe9+ey/+TuuZ7ejHlVyEELbbvRkxHZN+Hf5XGecJD5i0kvP2opCseATA==`.
- **The old names are deprecated:** `@zed-industries/claude-code-acp` (last `0.16.2`) and `@zed-industries/claude-agent-acp` (last `0.23.1`) both say "This package has been renamed to @agentclientprotocol/claude-agent-acp" in the registry.
- **The binary:** `package.json` has `"bin": {"claude-agent-acp": "dist/index.js"}`, and `dist/index.js` starts with `#!/usr/bin/env node`. Run without a shell and without the shebang's PATH lookup, that is: `NODE dist/index.js` (an absolute `node` and the absolute path of the installed file), stdin and stdout as the ACP pipes. There are no flags needed to serve ACP (from the source, `src/index.ts`).
- **Other entry flags** (from the source, `src/index.ts`): `--version` or `-v` prints the package version and exits 0; `--cli ARGS...` runs the bundled Claude CLI with ARGS (`--cli` is checked first, so `--cli --version` prints the Claude CLI's version); `--hide-claude-auth` hides the claude.ai login and refuses sessions a subscription would pay for (`src/hide-claude-auth.ts`).
- **The Claude CLI it runs** (from the source, `src/claude-cli.ts`): `CLAUDE_CODE_EXECUTABLE` if set; else the native binary of the SDK's platform package (`@anthropic-ai/claude-agent-sdk-linux-x64`, `-linux-x64-musl`, arm64 and the other platforms, installed by npm as an optional dependency). It does **not** use the owner's `claude` from PATH unless `CLAUDE_CODE_EXECUTABLE` points to it.
- **Standalone executables** (no Node) are attached to each GitHub release (README); out of scope here, because the owner chose a pinned npm package.
- **No install scripts:** neither `@agentclientprotocol/claude-agent-acp` 0.101.0 nor `@anthropic-ai/claude-agent-sdk` 0.3.318 has a `preinstall`, `install`, `postinstall` or `prepare` script (registry metadata); the Claude CLI comes as the SDK's platform optional dependency (`@anthropic-ai/claude-agent-sdk-linux-x64` and others, each `0.3.318`). So `npm ci --ignore-scripts` should install everything; **not confirmed** by an install.
- **The bundled Claude Code version:** the SDK's registry entry for 0.3.318 has `"claudeCodeVersion": "2.1.318"`, at least the 2.1.295 that `onFailure: "block"` needs. Not documented in the adapter; checked at start with `--cli --version`.

### (b) Sign-in

- **The owner's existing Claude Code login is used as it is**, without the client touching it: the adapter starts the Claude CLI with its own environment, and the CLI reads its login itself (OAuth credentials or the system keychain; the Claude Code docs say only bare mode skips them, [Run Claude Code programmatically](https://code.claude.com/docs/en/headless.md)). The adapter's settings and identity checks use `CLAUDE_CONFIG_DIR` or `~/.claude` (`src/paths.ts`). So the same `HOME` (and `CLAUDE_CONFIG_DIR` if the owner sets one) gives the same login. Not documented by the adapter: where the credentials are stored.
- **The adapter checks sign-in itself:** it runs the CLI with `auth status --json` in the background after `initialize` (5 second limit) and pushes an `_auth/status_update` notification with the identity (from the source). The Claude Code CLI reference says `claude auth status` exits 0 when signed in and 1 when not ([CLI reference](https://code.claude.com/docs/en/cli-reference)). So `NODE ADAPTER --cli auth status` answers "signed in?" by its exit code alone, without umwayi reading its output.
- **The login methods** need a client that runs a terminal for them (see the table above). With `clientCapabilities: {}` none is offered: the owner signs in beforehand with `claude` (or `NODE ADAPTER --cli auth login`), outside umwayi.
- **Not documented:** what `session/new` or `session/prompt` answers when the owner is signed out (the source shows an `authRequired` error under `--hide-claude-auth`; without it, not documented).

### (c) Settings files and hooks inside an ACP session

- **Settings sources** (from the source): every session gets `settingSources: ["user", "project", "local"]`, placed before `_meta.claudeCode.options`, so a client could replace it. The SDK docs: user is `~/.claude/settings.json`, project `.claude/settings.json`, local `.claude/settings.local.json`; endpoint-managed policy loads in all cases ([TypeScript reference, settingSources](https://code.claude.com/docs/en/agent-sdk/typescript.md)). Managed policy env vars are applied before anything else (`src/managed-policy.ts`).
- **A route for our hook without a file:** `_meta.claudeCode.options.settings` is passed to the SDK `settings` option, which the SDK docs define as the inline settings object that "Populates the flag-settings layer", the same layer as `claude --settings` ([TypeScript reference, settings](https://code.claude.com/docs/en/agent-sdk/typescript.md)). The adapter merges its own provider settings into it (from the source). So the same inline JSON as `agent run` (`disableAllHooks: false` and one `PreToolUse` command hook, matcher `*`, `onFailure: "block"`) can go in, and nothing is written to `.claude`.
- **`_meta.claudeCode.options.hooks` is not that route:** the SDK `hooks` option takes callback functions, which cannot cross JSON-RPC (the adapter drops functions from its session fingerprint for that reason), so a command hook cannot be given there.
- **Order of checks** ([Configure permissions, How permissions are evaluated](https://code.claude.com/docs/en/agent-sdk/permissions.md)): 1 hooks (a `PreToolUse` hook can deny outright), 2 deny rules, 3 ask rules, 4 permission mode, 5 allow rules, 6 `canUseTool`, which the adapter turns into `session/request_permission`. So, by the docs, a hook runs before any permission request reaches umwayi.
- **Workspace trust:** in an SDK session Claude Code shows no trust dialog and treats the folder as trusted, so hooks from settings run ([Hooks reference, workspace trust](https://code.claude.com/docs/en/hooks.md)).
- **Not confirmed:** no page of the adapter says that a command hook from the flag-settings layer runs inside an ACP session. It follows from the SDK and Claude Code docs above and from the adapter passing `settings` through, but it has not been seen to run. A managed policy (`allowManagedHooksOnly`) can still block it unseen (KNOWN-LIMITS 30). **A model-free way to see it run:** add a `SessionStart` command hook to the same inline settings; if Claude Code runs hooks from that layer in this session, it runs that one when the session starts. Not documented: whether `SessionStart` runs at `session/new` or only with the first prompt in the SDK's streaming mode.

### (d) Client capabilities

- **It needs none.** The tools (Read, Write, Edit, Bash and the others) run inside the Claude CLI process on the local machine, not through the client. The adapter has `readTextFile` and `writeTextFile` methods that call the client, but in v0.101.0 nothing in the normal session flow calls them (from the source). Terminals are a display extension only. AskUserQuestion is turned off when the client has no form elicitation capability (`disallowedTools: ["AskUserQuestion"]`, from the source). With `clientCapabilities: {}`: no login methods, no elicitation, no display terminals, no subagent sessions; tool calls stay ordinary tool calls.
- **Not documented:** a statement in the README that it works with no capabilities; the above is from the source.

### (e) Permission requests and modes

- **Shape** (from the source, `src/tool-calls/renderer.ts` `permissionToolCall` and `src/permissions/presentation.ts`): for every client that is not JetBrains AIR (umwayi included), `toolCall` holds `toolCallId`, `name` (the Claude Code tool name, for example `Bash`, `Edit`, `mcp__server__tool`), `status: "pending"`, `rawInput`, `title`, `kind`, `content` and `locations`. `_meta.claudeCode.toolName` is added for MCP and subagent calls. AIR clients get a smaller shape; umwayi does not declare AIR.
- **Kinds used** (from the source, `src/tool-calls/reporters/`): `read`, `edit`, `execute`, `search`, `fetch`, `think`, `switch_mode`, `other`. All are short plain words, so umwayi's `acp_permission` action can carry them; tool names up to 40 characters too (longer MCP names are left out, then only the kind is in the action).
- **Options** (from the source, `src/permissions/options/`): `allow_once`, `allow_always` (a lasting rule, or a skill), `reject_once`; for ExitPlanMode the `allow_always` options switch the mode to `auto`, `bypassPermissions` or `acceptEdits`, and the only `allow_once` option keeps `default`. umwayi never takes an `allow_always` option, so a Yes there leaves the mode at `default`.
- **Something the action cannot describe:** ExitPlanMode ("Ready to code?", kind `switch_mode`) is a mode change, not a tool; `rawInput` (the command, the path) is never in umwayi's action, so rules can tell `Bash` from `Edit` but not one command from another. The hook (first gate) does see the command.
- **Modes** (from the source, `src/permissions/modes.ts`): `default` (labelled Manual), `acceptEdits`, `plan`, `dontAsk`, `auto`, `bypassPermissions`. Bypass is off when running as root (unless `IS_SANDBOX`), when settings disable it, or when `_meta.claudeCode.options.allowDangerouslySkipPermissions` is `false`. **The starting mode comes from `permissions.defaultMode` in the settings files** (escalating values from repository files are filtered out); `permissionMode` in `_meta` is ignored. A client can change the mode with the standard `session/set_mode`. In `acceptEdits`, `auto` and `bypassPermissions` many calls are approved without a permission request ([Configure permissions](https://code.claude.com/docs/en/agent-sdk/permissions.md)), so then the hook is the only check.

### (f) Protocol v1 with empty capabilities

- **Yes.** `initialize` answers `protocolVersion: 1` on the v1 path whatever the client sends (from the source); with `CLAUDE_AGENT_ACP_PROTOCOL=v1` a v2 request is also negotiated down. It also pushes `_auth/status_update` after `initialize` (umwayi ignores notifications it does not know). `session/prompt` takes the standard `prompt` field (the ACP v1 schema; the adapter is built on `@agentclientprotocol/sdk`).

### (g) Stopping, and background children

- **Stop** (from the source, `src/index.ts`): the end of stdin closes the connection, and SIGTERM and SIGINT run the same shutdown: `dispose()` tears down each session's SDK query, then the process exits 0.
- **Background children:** commands that Claude Code moved to the background keep running after `session/cancel` (README). **Not documented:** whether `dispose()` at exit stops them, and whether Claude Code puts them in their own process group or session. So umwayi must stop more than the adapter: its whole process group and, as for a cli chat, every descendant it has seen in `/proc`.

### What part 7 takes from this

| need | how |
| --- | --- |
| the package | `@agentclientprotocol/claude-agent-acp` exactly `0.101.0`, with a lockfile, in `adapters/claude_acp/`, installed by the owner |
| start | `[NODE, ADAPTERS/claude_acp/node_modules/@agentclientprotocol/claude-agent-acp/dist/index.js]`, no shell, no npx, no shebang lookup, `CLAUDE_AGENT_ACP_PROTOCOL=v1` |
| versions | `node --version` at least 22; the installed `package.json` version equal to the pin; `NODE ADAPTER --version` equal to the pin; `NODE ADAPTER --cli --version` at least 2.1.295 (for `onFailure`) |
| sign-in | `NODE ADAPTER --cli auth status`: exit 0, output discarded |
| our hook | inline `settings` in `_meta.claudeCode.options` (flag layer), plus `allowDangerouslySkipPermissions: false` |
| first gate confirmed | a `SessionStart` canary hook in the same inline settings, seen before the first prompt (not documented when it runs; refuse if not seen) |
| starting mode | `session/set_mode` to `default` after `session/new` (proposed) |
| capabilities | `{}`: none needed |
| stop | stdin closed, then the process group and every seen descendant |
