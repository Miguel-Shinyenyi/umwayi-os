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
- **The login methods** need a client that runs a terminal for them (see the table above). With `clientCapabilities: {}` none is offered: the owner signs in beforehand with `claude` (or `NODE ADAPTER --cli auth login`), outside umwayi. (Part 7c, owner decision Nov 9: `umwayi agent login NAME` may start that sign-in on the owner's terminal; see "Signing in from umwayi" below.)
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

## Login and billing for Claude Code (part 7c, spec only)

Read on Nov 9 2026, for the part 7c spec (tasks.md 10.32 and up). Nothing was installed, signed in or run. **From the source** again means what the adapter's code does at tag v0.101.0 (commit `85aec26ef984a421fe8064ce43f60138a3372384`), not a documented promise.

Pages and files read:

| what | where |
| --- | --- |
| Claude Code sign-in, precedence, login restrictions | [Authentication](https://code.claude.com/docs/en/authentication) |
| `claude auth status`, `claude auth login --console` | [CLI reference, CLI commands](https://code.claude.com/docs/en/cli-reference) |
| `forceLoginMethod`, `forceLoginOrgUUID`, `apiKeyHelper` | [Settings reference](https://code.claude.com/docs/en/settings-reference) |
| `AccountInfo`, `accountInfo()` | [Agent SDK TypeScript reference](https://code.claude.com/docs/en/agent-sdk/typescript.md) |
| the adapter's own reading of `auth status --json`, and `_auth/status_update` | [src/auth-status.ts](https://github.com/agentclientprotocol/claude-agent-acp/blob/v0.101.0/src/auth-status.ts), `runCliAuthProbe` in [src/acp-agent.ts](https://github.com/agentclientprotocol/claude-agent-acp/blob/v0.101.0/src/acp-agent.ts) |
| the adapter's billing guard (`--hide-claude-auth`) | [src/hide-claude-auth.ts](https://github.com/agentclientprotocol/claude-agent-acp/blob/v0.101.0/src/hide-claude-auth.ts) |

### Which credential pays: the precedence

- **Claude Code picks one credential, in this order** ([Authentication, Authentication precedence](https://code.claude.com/docs/en/authentication)):
  1. cloud provider credentials, when `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX` or `CLAUDE_CODE_USE_FOUNDRY` is set;
  2. `ANTHROPIC_AUTH_TOKEN`;
  3. `ANTHROPIC_API_KEY`;
  4. the output of an `apiKeyHelper` script;
  5. `CLAUDE_CODE_OAUTH_TOKEN` (a long-lived token from `claude setup-token`);
  6. Anthropic profile and federation credentials;
  7. the subscription login from `/login`. This is the default for Pro, Max, Ultra, Team and Enterprise.
  
  A signed-in Claude apps gateway outranks all of them.
- **So a subscription login is the last choice, not the first.** Any API key, token, helper or cloud variable that is present wins over it. The page says this outright: with a subscription and `ANTHROPIC_API_KEY` both set, Claude Code uses the key once you approve it. **In non-interactive mode (`-p`), the key is always used when present** ([Authentication](https://code.claude.com/docs/en/authentication)).
- **What that means for umwayi today:**
  - `umwayi agent run` (`claude -p`) and the cli chat give `claude` umwayi's whole environment. So when the owner's shell has `ANTHROPIC_API_KEY`, an `agent run` pays by API key, not by the subscription. Nothing in umwayi notices.
  - The ACP chat (part 7a) already drops `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_BASE_URL` (the allow list of 10.R11.9). It does not drop a credential that comes from a settings file.
- **Credentials from settings files:** `apiKeyHelper` may be set in any settings file, the project's `.claude/settings.json` in the workdir included ([Settings reference, apiKeyHelper](https://code.claude.com/docs/en/settings-reference)). Claude Code runs it through `/bin/sh` and sends its output as the key. The adapter keeps settingSources user, project and local (approved answer 7), so a repository can make a session pay by API key, and the environment allow list cannot stop that. The Authentication page also names settings files that can set `CLAUDE_CODE_OAUTH_TOKEN` through their `env` key.
- **Console logins are API billing:** `claude auth login --console` signs in "with Anthropic Console for API usage billing instead of a Claude subscription" ([CLI reference](https://code.claude.com/docs/en/cli-reference)). A Console login either stores an API key (legacy) or an Anthropic profile without a key ([Authentication, Sign in without an API key](https://code.claude.com/docs/en/authentication)).

### What `claude auth status` reports

- **Documented** ([CLI reference](https://code.claude.com/docs/en/cli-reference)):
  - It shows the authentication status as JSON (`--text` for a human readable form).
  - It exits 0 when logged in and 1 when not.
  - The JSON has `configDirectory` (Claude Code 2.1.268 or later).
  - The JSON has **`authMethod`, one of `none`, `claude.ai`, `oauth_token`, `api_key`, `api_key_helper` or `third_party`**.
- **From the source, not documented by Claude Code:** the adapter reads the same output as `{loggedIn, authMethod, apiProvider, apiKeySource, email, orgId, orgName, subscriptionType}`. It notes that absent fields are left out, not null, and that a signed-out CLI still prints valid JSON while it exits 1 (`CliAuthStatus` in `src/auth-status.ts`).
  - It runs `claude auth status --json` with a 5 second limit, in the session's working folder, with its environment.
  - It puts `--settings JSON` before `auth status`, because the CLI refuses that global option after the subcommand (`runCliAuthProbe`).
- **The output names the person:** `email`, `orgId` and `orgName` are in it. A client that parses it must read only the fields it needs, and must never print, log or store the rest.
- **A helper next to a subscription:** with an `apiKeyHelper` in settings and a claude.ai login, the output has both `apiKeySource` and `subscriptionType`, and the helper's key is what pays (comment on `mapAuthFields`, from the source). So `subscriptionType` alone does not prove the subscription pays. `apiKeySource` must be absent as well.
- **Not documented:**
  - Whether `auth status` itself runs an `apiKeyHelper` to report it.
  - Whether it reads project settings from the folder it runs in.
  - Whether it reflects an `env` key in a settings file.
  
  The adapter's code assumes it reports the credential the session in that folder would use.

### How the adapter decides "a subscription pays" (its billing guard)

- `--hide-claude-auth` is the adapter's guard for the opposite case: an integration that must **never** bill a subscription. It refuses every session and turn that a subscription would pay for (`src/hide-claude-auth.ts`).
- Its test, `billsClaudeSubscription(account)` on the SDK's `AccountInfo`, is the most precise statement found of when a subscription pays. All four must hold, and an unknown value counts as "not proven":
  1. `subscriptionType` is set;
  2. `tokenSource` is absent;
  3. `apiProvider` is absent or `firstParty`;
  4. `apiKeySource` is not `ANTHROPIC_API_KEY`, `apiKeyHelper` or `/login managed key` (a key that a Console `/login` created).
- `AccountInfo` is documented as `{email?, organization?, subscriptionType?, tokenSource?, apiKeySource?}`. `accountInfo()` "Returns account information", with nothing about the values ([TypeScript reference](https://code.claude.com/docs/en/agent-sdk/typescript.md)).
- **The account can change during a session:** the SDK caches the account at `initialize`, but the CLI picks up a login or logout made in another terminal (module comment, from the source). A session that started on the subscription can go on with an API key.
- **The adapter tells the client:** a push-only notification `_auth/status_update` with `{authStatus: {kind, label, ...}}`. `kind` is `none`, `account` (a subscription; `account.plan` holds `subscriptionType`), `api_key`, `gateway` or `external` (Bedrock, Vertex and others).
  - It is sent after `initialize`, at each `session/new`, and at the start of each prompt (an asynchronous probe), and only when the payload changed (`src/auth-status.ts`).
  - Nothing waits for it, so it can arrive in the middle of a turn that is already being paid for.
  - umwayi ignores it today (part 6 ignores unknown notifications).

### Restricting the login method

- **`forceLoginMethod`**: `"claudeai"` allows only claude.ai accounts to log in, and `"console"` only Console accounts. Its scope is "Any file" ([Settings reference](https://code.claude.com/docs/en/settings-reference)).
  - Since Claude Code 2.1.212 every first-party login path applies it, the Agent SDK included. The exception is the terminal's interactive `/login` screen, which only pre-selects.
  - With `"claudeai"`, an API key from an earlier Console login does not count as a sign-in ([Authentication, Login prompt still appears](https://code.claude.com/docs/en/authentication)).
- **Environment credentials under it:** the Authentication page says `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` and `apiKeyHelper` are "blocked at startup", because "under `forceLoginMethod` the credential would stand in for the required sign-in".
  - **Not confirmed:** that page describes the managed settings case. No page says whether a `forceLoginMethod` given in the flag-settings layer (`--settings`, or the SDK `settings` option) blocks an environment or helper credential at session start. The settings reference adds that the `"claudeai"` and `"console"` values follow "which managed source supplies login keys" rules.
  - So `forceLoginMethod: "claudeai"` in umwayi's inline settings is at best a second line. The login check below is the first.
- **`forceLoginOrgUUID`** only checks organizations when it comes from a managed source; from any other file it only pre-selects ([Settings reference](https://code.claude.com/docs/en/settings-reference)). Not useful to umwayi.

### Billing beyond the subscription

- **Not documented** in the pages read: whether a subscription session can bill pay-as-you-go usage beyond the plan's limits, how a client could tell, or how to turn it off.
- `auth status` and `AccountInfo` say which credential pays, not how much, nor whether extra usage is on.
- `ModelUsage.costUSD` in SDK result messages is "a client-side estimate" ([TypeScript reference](https://code.claude.com/docs/en/agent-sdk/typescript.md)), and the adapter does not pass it to an ACP client as a field umwayi reads.
- So umwayi can make sure the subscription is the credential, but it cannot cap the spend. That stays with the budget governor (H-078).

### What part 7c takes from this

| need | how |
| --- | --- |
| prove a subscription pays before any Claude Code start | `auth status --json`, in the workdir, with the environment the agent will get: exit 0, `loggedIn` true, `authMethod` `claude.ai`, no `apiKeySource`, `apiProvider` absent or `firstParty`, `subscriptionType` a plain word; anything else refuses |
| read nothing personal | only those six fields; `email`, `orgId`, `orgName` and the raw text are never printed, logged or stored |
| keep environment credentials out of `agent run` and the cli chat | drop the precedence list's variables from their environment (the ACP allow list already does) |
| a second line inside the session | `forceLoginMethod: "claudeai"` in the inline settings (not confirmed to block environment credentials) |
| notice a change during an ACP chat | `_auth/status_update` with `kind` other than `account` ends the chat |
| sign in from umwayi (owner decision Nov 9, option B) | `umwayi agent login NAME` runs `[NODE, ADAPTER, "--cli", "auth", "login", "--claudeai"]` on the owner's terminal, after the start steps; never `--console`, never `--email`; umwayi never reads its output; then the login check (section "Signing in from umwayi" below) |
| spend | not visible; budget governor |

### Signing in from umwayi: `auth login --claudeai` and what a browser login needs

Read on Nov 9 2026, after the owner's decision (option B): umwayi may start the claude.ai sign-in for a Claude Code ACP agent, but never reads it.

- **The command:** `claude auth login` signs in to an Anthropic account. `--console` signs in for API usage billing instead of a subscription, `--sso` forces SSO, and `--email` pre-fills the address ([CLI reference](https://code.claude.com/docs/en/cli-reference)).
  - The adapter's own terminal method uses exactly `--cli auth login --claudeai` (and `--console` for its Console method), in `initialize` in `src/acp-agent.ts`, from the source.
  - `--claudeai` is **not listed** in the CLI reference table. It is used by the pinned adapter for the pinned bundled CLI, so umwayi uses the same words, and the owner's real check (tasks.md 10.31) confirms it.
  - umwayi never passes `--console`, `--email` or `--sso`.
- **What the owner sees:**
  - Claude Code opens a browser. If it does not, the URL can be copied.
  - If the browser shows a code instead of returning to `localhost`, the owner pastes it at the `Paste code here` prompt.
  - `claude auth login` reads the pasted code from standard input ([Troubleshoot, OAuth login fails in WSL2, SSH, or containers](https://code.claude.com/docs/en/troubleshoot-install.md)).
  - So the login needs the owner's terminal for stdin, stdout and stderr, and umwayi must not sit between them.
- **Where the login is stored:** Linux keeps it in `~/.claude/.credentials.json` (mode 0600); macOS uses the Keychain ([Authentication, Credential management](https://code.claude.com/docs/en/authentication)). `CLAUDE_CONFIG_DIR` picks another configuration folder with its own login. umwayi never opens that file.
- **The remote markers:** the adapter treats `NO_BROWSER`, `SSH_CONNECTION`, `SSH_CLIENT`, `SSH_TTY` and `CLAUDE_CODE_REMOTE` as "the browser redirect to localhost will not work". Its comment says this "matches the SDK's internal isRemote check", and that `auth login` then falls back to a manual URL and code flow (from the source). That flow is the right one on a remote machine, so the first four are passed when set.
  - `CLAUDE_CODE_REMOTE` is not passed. Claude Code sets it itself only in its own cloud sessions ([Environment variables](https://code.claude.com/docs/en/env-vars)).
- **`BROWSER`:** documented: on WSL2, setting `BROWSER` to a browser's path lets Claude Code open it ([Troubleshoot](https://code.claude.com/docs/en/troubleshoot-install.md)).
- **How the browser is opened on Linux: not documented** by Claude Code. The usual Linux opener, `xdg-open` (xdg-utils, [scripts at freedesktop.org](https://gitlab.freedesktop.org/xdg/xdg-utils/-/tree/master/scripts)), reads:
  - `BROWSER`, `DISPLAY`, `WAYLAND_DISPLAY`, `XDG_CURRENT_DESKTOP`, `DESKTOP_SESSION` and `XDG_DATA_DIRS`;
  - the older `KDE_FULL_SESSION`, `KDE_SESSION_VERSION`, `GNOME_DESKTOP_SESSION_ID` and `MATE_DESKTOP_SESSION_ID`;
  - plus `HOME`, `PATH`, `XDG_CONFIG_HOME` and `XDG_DATA_HOME`, which the ACP allow list already passes.
  
  The desktop programs it hands over to (for example `gio open`, `kde-open`) talk to the session bus through `DBUS_SESSION_BUS_ADDRESS`; not checked further.
- **Never for a login:** `CLAUDE_CODE_OAUTH_REFRESH_TOKEN` makes `claude auth login` exchange that token instead of opening a browser, and it needs `CLAUDE_CODE_OAUTH_SCOPES` ([Environment variables](https://code.claude.com/docs/en/env-vars)). It is a credential, so it is never passed, like everything else left out of 10.R11.9.
- **Not documented:**
  - The exit code of `claude auth login` when the owner gives up or the code is wrong.
  - Whether it ever prints a token. `claude setup-token` does print one, which is why umwayi never runs it.
  - So umwayi trusts only the login check that follows, never the login's own exit code alone.

## Kiro: login and billing (part 7c, spec only)

Read on Nov 9 2026, for the owner's request that subscription comes first on every platform. Kiro pages were read as the Markdown copies listed in [kiro.dev/llms.txt](https://kiro.dev/llms.txt). Nothing was run.

| what | where |
| --- | --- |
| sign-in methods, device flow, API keys, precedence | [Authentication](https://kiro.dev/docs/getting-started/authentication.md) |
| `kiro-cli login`, `logout`, `whoami`, `acp --login`, environment variables | [CLI commands](https://kiro.dev/docs/reference/cli-commands.md) |
| headless runs and `KIRO_API_KEY` | [Headless mode](https://kiro.dev/docs/cli/headless.md) |
| plans and credits | [Billing](https://kiro.dev/docs/billing.md), [Usage beyond plan limits](https://kiro.dev/docs/billing/add-on-credits.md), [Related questions](https://kiro.dev/docs/billing/related-questions.md) |
| API keys under an administrator | [API key governance](https://kiro.dev/docs/enterprise/governance/api-keys.md) |
| ACP sign-in, `--auth-method` | [ACP (CLI)](https://kiro.dev/docs/cli/acp.md), [Migrate an ACP client to CLI V3](https://kiro.dev/docs/cli/v3/acp-migration.md) |
| `/usage` | [Slash commands](https://kiro.dev/docs/reference/slash-commands.md) |

### How Kiro bills

- **Every plan is credits:** Free (50 a month), Pro (1,000), Pro+ (2,000), Pro Max (5,000) and Power (10,000). Credits are used fractionally per request, and models use them at different rates ([Billing](https://kiro.dev/docs/billing.md)).
- **Beyond the plan, only credits bought on purpose:**
  - Add-on credits cost $0.04 each and are bought by hand in the Kiro portal, in packs of $5 to $100, "billed immediately when you purchase them". They are not available on Free.
  - When plan and add-on credits are used up, "Kiro pauses usage" ([Usage beyond plan limits](https://kiro.dev/docs/billing/add-on-credits.md)).
  - The FAQ says that if you prefer a fixed bill, you buy no add-on credits and usage pauses at the cap ([Related questions](https://kiro.dev/docs/billing/related-questions.md)).
  - So, by the docs, Kiro has **no automatic pay-as-you-go**: spend beyond the subscription needs a purchase the owner makes in a browser.
- **An API key bills the same subscription:** `KIRO_API_KEY` (a long-lived key, `ksk_...`) works only for Pro, Pro+, Pro Max and Power subscribers. "Credits consumed using the API key are decremented from your subscription credits" ([Authentication, API key authentication](https://kiro.dev/docs/getting-started/authentication.md)).
  - So, unlike Claude Code, a Kiro API key is not a different way of paying.
  - It is still a credential that may belong to another account (a key in a CI shell).
  - Under an administrator, API keys are off unless enabled ([API key governance](https://kiro.dev/docs/enterprise/governance/api-keys.md)).
- **Organisation plans** (IAM Identity Center, "Kiro Pro" licence) are billed to the organisation through AWS ([Enterprise billing](https://kiro.dev/docs/enterprise/billing.md), listed in the index, not read further). Which credits pay is the organisation's choice, outside umwayi.
- **Not documented:** an environment variable or flag that selects another way to pay. None was found besides `KIRO_API_KEY`.

### Which login Kiro uses

- **Precedence** ([Authentication](https://kiro.dev/docs/getting-started/authentication.md)): 1, an active browser session from `kiro-cli login`; 2, `KIRO_API_KEY`; 3, none, and the CLI asks you to sign in.
  - So a key is used only when the browser login is missing or expired.
  - Interactive sessions should use the browser sign-in; the key is meant for non-interactive runs.
- **Conflict:** the Headless mode page says headless runs require `KIRO_API_KEY` ("Headless mode requires an API key"). The Authentication page puts the browser session first for every CLI use. layer 10 part 4 (`agent run` for Kiro) assumed the browser login works for `--no-interactive`. Not confirmed by a real run (KNOWN-LIMITS 41 to 45 area).
- **`kiro-cli login`** has `--license pro|free`, `--identity-provider URL`, `--region`, `--social google|github` and `--use-device-flow` ([CLI commands](https://kiro.dev/docs/reference/cli-commands.md)).
  - Locally it opens the browser portal, and the selection flags "are generally ignored". On a remote machine it uses a device code automatically.
  - If you are already signed in, it gives an "Already logged in" error.
  - How it decides "remote" is not documented.
- **`kiro-cli acp --login`** runs the Kiro sign-in in the terminal, then exits without starting the server ([CLI commands, kiro-cli acp](https://kiro.dev/docs/reference/cli-commands.md)).
  - Signed out, `kiro-cli acp` (2.37 or later) offers one auth method in `initialize`. For a client without terminal auth (umwayi), that method asks the owner to run `kiro-cli login` themselves ([ACP (CLI)](https://kiro.dev/docs/cli/acp.md)).
  - `--auth-method client` would make the client answer `_kiro/auth/getAccessToken` with tokens ([Migrate an ACP client to CLI V3](https://kiro.dev/docs/cli/v3/acp-migration.md)). umwayi must never use it.
- **`kiro-cli whoami`** shows the user and the authentication method (Builder ID, IAM Identity Center, social), the session status and the profile, including the email. `--format json` exists ([CLI commands, kiro-cli whoami](https://kiro.dev/docs/reference/cli-commands.md)).
  - **Not documented:** the JSON field names (the page shows only plain text examples), the exit code when signed out, whether it reports an API key login, and whether it reports the plan.
  - The Authentication page says to "run `kiro-cli whoami`" to see which method is active.
- **Usage:** `/usage` in a chat shows billing and credits, and in non-interactive runs prints the full breakdown ([Slash commands](https://kiro.dev/docs/reference/slash-commands.md)). The V3 ACP server can advertise `_kiro/account/getUsage` ([Migrate an ACP client to CLI V3](https://kiro.dev/docs/cli/v3/acp-migration.md)).
  - Both run inside a Kiro session. Whether `/usage` in a headless run costs credits is not documented.
  - umwayi does not use either in part 7c.
- **Kiro's own environment names** ([CLI commands, Log files](https://kiro.dev/docs/reference/cli-commands.md)):
  - `KIRO_HOME` moves the whole Kiro folder, sign-ins included. A different `KIRO_HOME` is a different login.
  - `KIRO_RUNTIME_DIR`, `KIRO_LOG_LEVEL` and `KIRO_LOG_NO_COLOR` carry no credential.

### What part 7c takes for Kiro

| question | answer |
| --- | --- |
| what can be checked | that a browser login exists: `kiro-cli whoami` exit code, with `KIRO_API_KEY` removed so a key cannot stand in. Not the plan, not the credits, and not the method by field, because the JSON names are not documented |
| environment names to strip | `KIRO_API_KEY` for every Kiro start (run, cli chat, ACP) and for `whoami`. `KIRO_HOME` is passed unchanged: it is the owner's choice of Kiro folder, not a credential |
| a Kiro billing check | not needed for "who pays": by the docs every Kiro login, a key included, is paid from the subscription's credits, and nothing beyond them is spent without a purchase. Not possible for "how much": no documented way to read credits outside a session |
| a Kiro login command | possible: `umwayi agent login NAME` for a Kiro agent runs `[KIRO, "login"]` on the owner's terminal (no flags), then the `whoami` check. Proposed in design.md part 7c |
| unknown | the `whoami` JSON fields and exit code; whether headless runs really work without `KIRO_API_KEY` (the Conflict above); how "remote" is detected for the device flow; what an organisation's plan bills |

## The owner's first real run (10.31): steps, expected output, results (NOT DONE YET)

Written Nov 10 2026 with part 7c-3 (PR 29). Everything above this section was read from docs and source, and every test uses fakes. This run is the first time a real Node, the real pinned adapter, a real Claude Code login and a real Kiro login meet umwayi. It is the owner's, on the owner's machine; nothing here was run by the build. It also holds the real checks that tasks 10.37 and 10.39 fold into 10.31.

Rules for this run:

- Record field **names**, exit codes and version strings only. Never paste a value of `auth status`, an email, an organisation, a URL, a code, a token or a key into this file, an issue or a chat.
- No API key anywhere. Where a step needs "a key is set", it uses the placeholder `not-a-real-key-umwayi-test`, which is not a key.
- umwayi never signs in or out by itself. Every login and logout below is typed by the owner.

### 0. Prepare (once)

1. `node --version` prints `v22.` or later.
2. In `adapters/claude_acp/`, run `npm ci --ignore-scripts` (see its README; umwayi never runs npm).
3. In the umwayi root, an `agents.yaml` with a scratch workdir (a folder you do not mind an agent reading):

   ```yaml
   agents:
     - name: reviewer
       platform: claude-code
       command: claude
       transport: acp
       workdir: /path/to/a/scratch/folder
     - name: helper
       platform: kiro
       command: kiro-cli
       workdir: /path/to/a/scratch/folder
   ```

4. In `rules.yaml`, your own Yes rules for `type: agent_run` with `agent: [reviewer, helper]` and for `type: agent_login` with the same agents; `tool_read` Yes and `tool_bash` Ask me first are enough for this run.
5. For Kiro: the layer 9 hook file in `/path/to/a/scratch/folder/.kiro/hooks/` (adapters/kiro/README.md).
6. In the shell you use: `unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN KIRO_API_KEY` (umwayi leaves them out anyway; this keeps the run clean).

### A. A real Claude Code ACP chat (10.31, part 7)

A0. Sign in with your Claude subscription if you are not: `umwayi agent login reviewer`. Expected: your terminal shows the claude.ai sign-in; afterwards one line `Claude subscription OK (plan: WORD).` and exit 0 (`echo $?`). If you were already signed in: `Claude subscription OK (plan: WORD). Nothing was started.`

A1. `umwayi agent check reviewer; echo "exit $?"`. Expected, in this order, then `exit 0`:

```
ok: node: node found at /.../node
ok: node version: 22.x.y (at least 22.0.0)
ok: adapter file: /.../adapters/claude_acp/node_modules/@agentclientprotocol/claude-agent-acp/dist/index.js
ok: adapter package: @agentclientprotocol/claude-agent-acp 0.101.0
ok: adapter version: the adapter says 0.101.0
ok: claude code version: 2.1.318 (at least 2.1.295)
ok: login: Claude subscription (plan: WORD)
ok: hook script: /.../adapters/claude_code/hook.py
ok: hook self-test: the hook started and blocked the self-test event (exit 2)
...
Gated: the checks for a Claude Code ACP chat of agent reviewer passed. Nothing was started.
```

A2. The real version outputs, for the record (set `A=adapters/claude_acp/node_modules/@agentclientprotocol/claude-agent-acp/dist/index.js`): `node --version`, `node $A --version`, `node $A --cli --version`.

A3. `umwayi agent chat reviewer`. Expected: the open queue lines, then `Starting an ACP chat with agent reviewer. ...`, then `Nothing you type is sent until the hook is confirmed in the session (at most 30 s).`, then within 30 s `Connected. Type a message, :queue to see the queue, or :quit to end the chat.`
   - If instead, after up to 30 s, it prints `The first gate could not be confirmed in the ACP session. Nothing was sent.` and exits 2: the SessionStart canary did not run before the first prompt (KNOWN-LIMITS 65). Record that and stop here; part 7 open question 9 then needs the owner's decision.

A4. Type one line with a word you can search for later, for example `Please read README.md and then run the shell command ls. Word: PURPLEHERON`. Expected: `tool: ...` lines; for the shell command the hook asks (your rules say Ask me first) and umwayi asks `The agent asks to use a tool: ...`; answer `y` or `n`. Then type `:quit`. Expected exit 0.

A5. `umwayi logbook verify; echo "exit $?"` prints `ok: ...` and `exit 0`. Then look at LOGBOOK.md:
   - one `Source: umwayi check` entry with `action type: tool_read` or `tool_bash` for **every** `tool:` line the chat showed (count both);
   - `action type: acp_permission` entries for the permission requests;
   - `Started agent reviewer (claude-code, acp, chat): ...` and `Agent reviewer exited with code 0 after N s`;
   - `grep -c PURPLEHERON LOGBOOK.md` prints `0` (nothing of the conversation is logged).

### B. The field names of the real `auth status --json` (10.37, folded into 10.31)

Only the sorted key names are printed; never paste the raw output.

B1. With your subscription login: `node $A --cli auth status --json | python3 -c 'import json,sys; print(sorted(json.load(sys.stdin)))'` and the same with `claude auth status --json | python3 -c '...'`.

B2. With a placeholder key in front (not a real key): `ANTHROPIC_API_KEY=not-a-real-key-umwayi-test claude auth status --json | python3 -c 'import json,sys; print(sorted(json.load(sys.stdin)))'`. Then `ANTHROPIC_API_KEY=not-a-real-key-umwayi-test umwayi agent run reviewer --prompt "say hi"; echo "exit $?"`: expected to start normally, because umwayi removes that name (10.R12.6).

B3. With a project `apiKeyHelper` in a throwaway folder (the helper prints a placeholder, not a key; `auth status` may run it, KNOWN-LIMITS 70):

```
mkdir -p /tmp/umwayi-helper-test/.claude
printf '{"apiKeyHelper": "echo not-a-real-key-umwayi-test"}\n' > /tmp/umwayi-helper-test/.claude/settings.json
(cd /tmp/umwayi-helper-test && claude auth status --json | python3 -c 'import json,sys; print(sorted(json.load(sys.stdin)))')
rm -rf /tmp/umwayi-helper-test
```

### C. A real Kiro login (10.39, folded into 10.31)

C1. Signed in: `kiro-cli whoami >/dev/null 2>&1; echo "exit $?"`. Expected `exit 0`.

C2. Signed out, by hand: `kiro-cli logout`, then `kiro-cli whoami >/dev/null 2>&1; echo "exit $?"`. Expected not 0. If it is 0, KNOWN-LIMITS 85 holds: the check proves nothing on this Kiro version.

C3. `umwayi agent login helper`. Expected: your terminal shows the Kiro sign-in; afterwards `Kiro login OK.` and exit 0.

C4. `umwayi agent check helper` shows `ok: login: Kiro is signed in (kiro-cli whoami exited 0)`. Then `env -u KIRO_API_KEY umwayi agent run helper --prompt "Say hello and use no tools"; echo "exit $?"`. Expected exit 0 if headless Kiro works without `KIRO_API_KEY`; exit 2 if it does not (KNOWN-LIMITS 86, fail closed).

### Results (to be filled in by the owner; all NOT DONE)

| step | what to record | result |
| --- | --- | --- |
| A1 | exit code; every line ok | not done |
| A2 | the three version strings | not done |
| A3 | whether the canary ran before the first prompt (Connected, or refused after 30 s) | not done |
| A5 | tool lines shown vs `tool_*` hook entries in the logbook; `PURPLEHERON` count | not done |
| B1 | key names of `auth status --json`, adapter CLI and `claude` | not done |
| B2 | key names with a key in front; exit code of the run | not done |
| B3 | key names with a project `apiKeyHelper` | not done |
| C1, C2 | `whoami` exit code signed in and signed out | not done |
| C3 | `agent login helper` result line and exit code | not done |
| C4 | exit code of a headless Kiro run without `KIRO_API_KEY` | not done |

## Muse Spark Open as a platform (spec only, read Nov 9 2026)

Read on Nov 9 2026 for the owner's request: include Meta's Muse Spark Open as another platform, subscription or free first, pay-as-you-go only later. Nothing was installed, signed in or run. Facts are in my own words. **From a secondary source** marks a page that is not Meta's, a provider's or a harness's own. Prices are as seen on the day and change without notice.

### The model

- **Muse Spark Open** is Meta Superintelligence Labs' open-weight model, released Oct 15 2026: a mixture-of-experts transformer with 816B total and 42B active parameters, 256 experts with 8 routed per token, 62 layers, a 1M-token context, text, image, video and audio in, and text out ([Meta Research, Introducing Muse Spark Open](https://research.meta.ai/blog/muse-spark-open); [model card copy at unsloth/Muse-Spark-Open-816B-A42B-GGUF](https://huggingface.co/unsloth/Muse-Spark-Open-816B-A42B-GGUF)).
  - It shares the base model with the closed Muse Spark 1.3 ([PyTorch blog, Oct 15 2026](https://pytorch.org/blog/muse-spark-open/)).
  - Recommended settings: temperature 1.0, top_p 1.0, top_k off, and reasoning effort `low`, `medium`, `high` or `xhigh` (the default is `xhigh`; any other value is an error) (model card).
- **Not on Meta's own API:** Meta's model list says Muse Spark Open has no Model API endpoint. You self-host it or call a hosted provider ([dev.meta.ai, Models](https://dev.meta.ai/docs/models)).
- **Official weights:**
  - BF16 is about 1.5 to 1.65 TB, and NVFP4 about 530 GB. The card asks for at least 700 GB of VRAM for NVFP4 and 2 TB for BF16.
  - Meta shows NVFP4 on two 512 GB M5 Ultra Mac Studios with MLX.
  - The official weights repo `meta-models/Muse-Spark-Open-816B-A42B` is gated: fetching it gave HTTP 401 on Nov 9.
  - Community GGUF builds go down to about 176 GB (1-bit) and about 300 GB (2-bit) ([musesparkopen.app](https://musesparkopen.app/), from a secondary source; [Digital Applied, Oct 16 2026](https://www.digitalapplied.com/blog/meta-muse-spark-open-open-weights-licence-hardware), from a secondary source).

### The licence, for the owner's use

- **Read only through secondary summaries:** the licence file sits behind the Hugging Face gate, so I could not fetch `LICENSE.md` myself. The owner must read it.
- **What the summaries say** (Meta Research's own post only calls it the Muse Model License, "with limited commercial terms, which allow many developers to use the model for free" ([Meta Research](https://research.meta.ai/blog/muse-spark-open))):
  - **Attribution:** any product that uses the model or a Derivative must prominently show "Built with Muse Spark Open", in the UI, the docs, the website or the settings.
  - **Derivatives** include models trained or distilled on its outputs.
  - **Model as a Service:** a provider of AI models as a service whose group revenue exceeds $20 million in any 12 months must notify Meta and sign a separate agreement first. Internal use, research, and powering features of your own product are exempt.
  - **Usage Policy:** it excludes, among other things, critical infrastructure and weapons uses, and the model is not intended for anyone under 18.
  - Sources: [dev.to summary citing sections 2 and 3, Oct 2026](https://dev.to/clydaralab/muse-spark-open-what-metas-open-weight-license-actually-lets-you-do-5dib), [Digital Applied](https://www.digitalapplied.com/blog/meta-muse-spark-open-open-weights-licence-hardware) and [ibl.ai](https://ibl.ai/blog/meta-muse-spark-open-weight-licence-self-host-reality), all from a secondary source.
- **For umwayi-os** (a solo owner's tool, far below $20M, not selling model access), the summaries put it in the exempt case. One duty remains: the attribution line in the README or docs once umwayi-os ships an adapter that uses the model.
- **This is not legal advice.** The owner reads the licence.

### Routes that cost nothing or use a subscription

| route | what it costs | runs Muse Spark Open itself? | source |
| --- | --- | --- | --- |
| **Muse Code subscription** (Meta) | flat monthly plans: Everyday, High, Power and Maximum Usage. They cover Muse Spark, Muse Wonder and Muse Image, are Contributor mode by default (more usage in exchange for Meta training on your content), and work only through the Muse Code CLI signed in with the Meta account | **No.** The plans list Muse Spark (closed 1.x), not Spark Open. Muse Code's default model is `muse-spark-1.2` | [Subscriptions](https://dev.meta.ai/docs/muse-code/subscriptions), [Configuration](https://dev.meta.ai/docs/muse-code/configuration) |
| **Meta Model API** pay-as-you-go | Muse Spark $1.25 / $4.25 per 1M tokens in and out; Contributor variants $0.10 / $0.20 | No (Spark Open has no endpoint) | [Pricing and rate limits](https://dev.meta.ai/docs/pricing-rate-limits) |
| **Meta AI / Meta Muse app** (consumer) | free tier, plus paid plans reported at $20 and $100 a month (from a secondary source) | No: a consumer app, not something umwayi can start | [c-sharpcorner, from a secondary source](https://www.c-sharpcorner.com/article/meta-muse-metas-ai-agent-app-and-models) |
| **OpenRouter** | the providers listed for `meta/muse-spark-open` (Fireworks, Makora, Modal, Together, Nebius, Baseten) all show $1.25 / $4.25 per 1M. A search result on Nov 9 showed a `meta/muse-spark-open:free` page with a price of zero and rate limits, but that page **returned 404** when I fetched it the same day. Free models are capped at 20 requests a minute and 50 a day, or 1,000 a day after $10 of credits were ever bought. Credits are prepaid, and a call without enough credit fails with 402 | Yes, paid. Free: **not confirmed** | [OpenRouter model page](https://openrouter.ai/meta/muse-spark-open), [OpenRouter limits (help centre)](https://openrouter.zendesk.com/hc/en-us/articles/39501163636379-OpenRouter-Rate-Limits-What-You-Need-to-Know), [API errors](https://openrouter.ai/docs/api/reference/limits) |
| **Groq** | "limited preview" on GroqCloud, access by request, 131,072-token context, text and image in. No price or free tier stated for this model | Yes, preview | [Groq blog, Oct 15 2026](https://groq.com/blog/meta-s-muse-spark-open-release-is-now-in-limited-preview-on-groqcloud) |
| **Together AI** | $1.25 / $4.25 per 1M; no free tier stated for this model | Yes, paid | [Together model page](https://www.together.ai/models/muse-spark-open) |
| **Hugging Face Inference Providers** | Free users get no monthly credits. PRO (a subscription) gets $2 a month of compute credits, then pay-as-you-go after a credit purchase. Whether HF routes Muse Spark Open to a provider was not checked | Not confirmed | [HF Inference Providers pricing](https://huggingface.co/docs/inference-providers/pricing) |
| **Vercel AI Gateway** (not asked; found) | $5 of credits every 30 days for accounts that never paid (search snippet, not opened) | Listed | [Vercel AI Gateway model page](https://vercel.com/ai-gateway/models/muse-spark-open) |
| **Local** (llama.cpp, vLLM, SGLang, MLX) | no money per token, but hardware: about 300 GB of memory for a 2-bit build, 700 GB of VRAM for NVFP4, or two 512 GB Mac Studios | Yes | [Meta Research](https://research.meta.ai/blog/muse-spark-open), [dev.meta.ai Run inference](https://dev.meta.ai/docs/muse-spark-open/deploy), [musesparkopen.app](https://musesparkopen.app/) (from a secondary source) |

- **The one subscription route** (Muse Code) does not run Muse Spark Open. It runs the closed Muse Spark that shares its base model.
- **No free hosted route for Spark Open was confirmed** on Nov 9.
- **The truly free route is local**, and only for an owner with roughly 300 GB or more of memory.
- **Muse Glimmer 30B**, Meta's smaller open model distilled from Muse Spark under Apache 2.0, is the local option for ordinary hardware ([dev.meta.ai, Models](https://dev.meta.ai/docs/models)). It is a different model.

### Harnesses that could start it as an umwayi agent

**1. Muse Code (`muse`)**, Meta's terminal coding agent ([Muse Code overview](https://dev.meta.ai/docs/muse-code)).
- **Login and billing** ([Authentication and billing](https://dev.meta.ai/docs/muse-code/auth)):
  - A browser sign-in or an API key. **`META_API_KEY` outranks everything**: env key first, then a stored key (`muse auth set`), and only then the browser session.
  - The subscription applies only to the Muse Code key connected during onboarding, and any other key is billed pay-as-you-go ([Subscriptions](https://dev.meta.ai/docs/muse-code/subscriptions)).
  - Pay-as-you-go is charged when a balance threshold is reached and on the first of each month.
  - `muse logout` does not unset an exported `META_API_KEY`.
- **Hooks** ([Extending and automating](https://dev.meta.ai/docs/muse-code/extending)):
  - Shell commands bound to events, among them `SessionStart`, `PreToolUse`, `PermissionRequest`, `PostToolUse` and `SessionEnd`. A hook can block an action.
  - Sources: project `.muse/hooks.json` (run only after the folder is trusted), user hooks in `~/.config/muse/settings.json`, and a managed file named by `managed_hooks_path`.
  - **Not documented** in what I read: the hook input and output format, the exit-code meaning, and an inline or per-run settings layer for hooks. `-c key=value` exists for some settings, but for hooks it was not checked.
- **Approvals and sandbox:** on from the first run. `--disable-approval`, `--yolo` (no approval and no sandbox, and it trusts the workspace), `--disable-sandbox` and `--trust-workspace` turn them down (Configuration, Extending).
- **Headless:** `muse exec "prompt"` (`--prompt-file`, `--json`, `--max-model-steps`). Exit codes: 0 completed, 1 failed or cancelled, 2 usage, 130 or 143 on signals (Extending).
- **Model:** `--model`, default `muse-spark-1.2` (Configuration). **Not documented:** whether Muse Code can use a third-party or local endpoint, so whether it can run Spark Open at all. The page `docs/muse-code/third-party-providers` gave 404 on Nov 9.
- **ACP: no native ACP** found. Community adapters exist (for example [BrokkAi/muse-acp](https://github.com/BrokkAi/muse-acp), [bex-co/muse-code-acp](https://github.com/bex-co/muse-code-acp)); they are not Meta's and were not read further.
- **Contributor mode** (Meta may train on your content) is the subscription default and can be set per run with `--contributor-mode on|off` or `MUSE_CONTRIBUTOR_MODE=1|0` ([Subscriptions](https://dev.meta.ai/docs/muse-code/subscriptions)). This is a data choice, not a billing one.

**2. OpenCode (`opencode`)**, an open-source coding agent that takes any provider and model.
- **ACP:** `opencode acp` serves ACP over stdio JSON-RPC ([OpenCode ACP](https://docs.opencode.ai/docs/acp/)). The v2 docs say `opencode acp --login` runs `opencode auth login` and exits 0 on success (search snippet of [dev.opencode.ai v2 ACP](https://dev.opencode.ai/v2/docs/cli/acp/), not opened).
- **Providers:** OpenRouter, Together, Fireworks, Groq, Ollama, and any OpenAI-compatible endpoint by `baseURL`, which covers a local llama.cpp, vLLM or SGLang server. A provider entry can name the environment variables it reads (`"env": [...]`) ([Providers](https://opencode.ai/docs/providers/)).
- **Permissions** ([Permissions](https://opencode.ai/docs/permissions/)):
  - Rules are `{action, resource, effect}` with `allow`, `deny` or `ask`; the last match wins, and `ask` "waits for a decision from the client".
  - **The default policy allows everything** (`*`, `*`, `allow`), apart from `.env` reads. So without `ask` rules there are no permission requests to answer.
  - Resources carry the command string for `shell` and the path for `edit` or `read`.
  - Answers are `once`, `always` or `reject`. `always` saves a durable project-scoped allow rule. An open issue reports that it overrides a configured `ask` in later sessions ([anomalyco/opencode #48456](https://github.com/anomalyco/opencode/issues/48456)).
  - V1 and V2 use different key names (`permission` and `permissions`).
- **Configuration layers** ([Config](https://opencode.ai/docs/config/)): managed (`/etc/opencode`, highest), global `~/.config/opencode/`, project `opencode.json(c)` and `.opencode/`. An inline config in the `OPENCODE_CONFIG_CONTENT` variable is listed in the precedence order (search snippet of [OpenCode Config, French page](https://opencode.ai/docs/fr/config/), not confirmed for V2).
- **A hook point:** plugins (JS or TS) with `tool.execute.before`, which can throw to block a tool call ([Plugins](https://docs.opencode.ai/docs/plugins/)). Plugins load from `.opencode/plugins/`, `~/.config/opencode/plugins/` or npm packages, and npm plugins are installed with Bun at startup. **Not documented:** loading a plugin from an arbitrary path given in config.
- **Billing:** whatever the chosen provider bills. A provider key in the environment or config is pay-as-you-go unless the provider's free route applies.
- **OpenCode's own offerings** (section "OpenCode" below) list Muse Spark 1.2 and 1.3 (closed, Console pay-as-you-go) and Muse Spark 1.2 and 1.3 Contributor (in the Go subscription). They do **not** list Muse Spark Open, as read Nov 9.

**3. Claude Code with another model** (via `ANTHROPIC_BASE_URL`, or a community proxy such as [Wraient/muse-cc](https://github.com/Wraient/muse-cc) that reuses a Muse Code subscription credential): **rejected**.
- It conflicts with 10.R12, which removes `ANTHROPIC_BASE_URL` and requires a claude.ai subscription.
- The Muse Code credential "is for use with Muse Code only" ([Subscriptions](https://dev.meta.ai/docs/muse-code/subscriptions)).

**4. Kiro CLI:** models come from Kiro's own catalogue; Muse Spark Open was not checked there. Out of scope.

### Can umwayi gate it as it gates Claude Code and Kiro?

| question | Muse Code | OpenCode |
| --- | --- | --- |
| a hook in front of every tool call (layer 9 style) | **Yes in principle:** `PreToolUse` and `PermissionRequest` shell hooks exist. Their input and output format is not documented in the pages read, and umwayi would need a hook source it does not have to write (user settings or a project file both need editing; a managed path is a machine setting) | **Only through a plugin:** `tool.execute.before` in JS or TS, loaded from a plugin folder or npm. That would be third-party code, and a JS file would be umwayi's first in the core path |
| permission requests umwayi can answer | no native ACP; only the community adapters | **Yes:** native ACP. With `ask` rules for every action, every tool call becomes a request whose resource is the command or path, which shows more than Claude Code's ACP permission requests do |
| a way to make the policy strict without editing files | not found | `OPENCODE_CONFIG_CONTENT` inline config (not confirmed for V2). A managed `/etc/opencode` overrides it, and saved `always` approvals may override `ask` |
| proof the gate is active (like the 7b canary) | a `SessionStart` hook would do it, as for Claude Code, if a hook source can be given | a plugin event, or the first `ask` arriving; not designed |
| headless run | `muse exec`, exit codes documented | `opencode run` (`--auto` approves everything not denied, so it is never used) |

### Environment names that switch to paid billing

- **Muse Code:**
  - `META_API_KEY` (outranks the subscription and is billed pay-as-you-go).
  - A stored key from `muse auth set` is not an environment name: umwayi cannot strip it, only detect it, and no documented status command reports it.
  - `MUSE_CONTRIBUTOR_MODE` changes data use, not billing.
- **OpenCode:**
  - the chosen provider's key;
  - `OPENCODE_API_KEY` (shown in OpenCode's ACP examples);
  - `OPENCODE_CONFIG` and `OPENCODE_CONFIG_CONTENT`, which can add a paid provider;
  - any name a provider entry lists in `env`;
  - cloud variables such as `AWS_BEARER_TOKEN_BEDROCK` and `GOOGLE_APPLICATION_CREDENTIALS` ([Providers](https://opencode.ai/docs/providers/)).
  
  The exact names each built-in provider reads (for example `OPENROUTER_API_KEY`, `TOGETHER_API_KEY`, `FIREWORKS_API_KEY`, `GROQ_API_KEY`, `HF_TOKEN`) were **not checked** against OpenCode's code. OpenRouter's own docs use `OPENROUTER_API_KEY` in their examples.
- **Hosted providers in general:** an account with prepaid credits only (OpenRouter) cannot be billed beyond its balance: a paid call fails with 402. Postpaid providers bill as you go.

### What stays unknown

- Whether a free hosted route for Muse Spark Open exists today (OpenRouter `:free` was seen in a search result and then gave 404; Groq is a limited preview with no stated price).
- Whether Muse Code can use any non-Meta endpoint, and so whether it can run Spark Open; also its hook input and output format, and an inline hook source.
- OpenCode V2's inline config, plugin loading by path, and the exact ACP permission request shape (one client reports the request arriving before `rawInput` is filled: [xenodium/agent-shell #614](https://github.com/xenodium/agent-shell/issues/614)).
- The full licence text (gated).
- The owner's hardware.
- How fast both harnesses change: OpenCode has V1 and V2 docs live at once.

## OpenCode as a platform (spec only, read Nov 9 2026)

Read on Nov 9 2026, for the owner's request to include OpenCode as a platform, subscription or free first. Nothing was installed or run.
- **Two doc trees are live at once:** opencode.ai/docs (V2: `permissions` as a rule array, `providers`) and docs.opencode.ai (V1 wording: `permission` objects, `provider`, `enabled_providers`).
- Each fact below names the page it is from. Where they differ, both are given.

### The project and its licence

- **OpenCode is an open-source coding agent by Anomaly** (the SST team). The canonical repository is [github.com/anomalyco/opencode](https://github.com/anomalyco/opencode); `github.com/sst/opencode` redirects there ([aiwiki, from a secondary source](https://www.aiwiki.ai/wiki/opencode)).
- **Licence: MIT**, "Copyright (c) 2025 opencode" ([LICENSE on the dev branch](https://raw.githubusercontent.com/anomalyco/opencode/dev/LICENSE), read Nov 9). Using it as an external program puts no duty on umwayi-os beyond keeping its notice if umwayi-os ever redistributed it (it does not).

### How it starts

- **TUI:** `opencode [project]`.
- **One prompt for scripts:** `opencode run "PROMPT"` ([CLI intro](https://opencode.ai/docs/cli/)). V1 flags include `--model provider/model`, `--agent` and `--auto` ("auto-approve permissions that are not explicitly denied") ([V1 CLI](https://docs.opencode.ai/docs/cli/)). `--auto` would remove the ask, so umwayi never passes it.
- **Background service:** by default every OpenCode client connects to one shared background server per user, which owns sessions, config, permissions and tool execution. `--standalone` runs a private one ([CLI intro](https://opencode.ai/docs/cli/)).
- **ACP:** `opencode acp` serves ACP v1 over stdio (newline-delimited JSON-RPC), and stdout carries only ACP messages ([V2 ACP reference](https://dev.opencode.ai/v2/docs/cli/acp/)).
  - It starts its **own private server**, opens no port and does not join the shared service.
  - It exits when the client closes stdin.
  - `--print-logs` sends logs to stderr.
- **ACP sessions** take the directory's whole configuration (models, agents, plugins, MCP servers) from `cwd`, which must be absolute. One prompt runs at a time, and `session/cancel` ends the prompt and rejects pending permission requests (same page).

### Login and providers

- **`opencode auth login [provider] [--method ...]`** saves a provider account through one of four methods ([Provider accounts](https://opencode.ai/docs/cli/providers)):
  - API key;
  - OAuth (browser URL or device code);
  - Command (it runs a provider's command and saves its output as a key);
  - Environment (it reads a supported variable from the server process, without saving it).
- **Where accounts live:** in the server's SQLite database (`~/.local/share/opencode/opencode.db`; `OPENCODE_DB` and `XDG_DATA_HOME` move it). A saved account outranks an environment connection for the same provider. `auth logout` cannot remove an environment connection.
- **ACP login:** `opencode acp` offers one auth method, `opencode-login`. With `clientCapabilities.auth.terminal` the client runs `opencode acp --login`, which runs `opencode auth login` and exits 0 on success ([V2 ACP reference](https://dev.opencode.ai/v2/docs/cli/acp/)). umwayi offers no capabilities, so it gets the agent method, which collects nothing. If a provider needs sign-in, a prompt fails with `auth_required`.
- **Claude Pro or Max login:** not offered.
  - OpenCode merged "Remove anthropic references per legal requests" (PR #18186) on Mar 19 2026 ([jcubic/opencode-claude-plan, from a secondary source](https://github.com/jcubic/opencode-claude-plan)).
  - Anthropic reportedly blocked Claude subscription tokens in third-party tools from Apr 4 2026 ([dev.to, from a secondary source](https://dev.to/mcrolly/anthropic-kills-claude-subscription-access-for-third-party-tools-like-openclaw-what-it-means-for-3ipc)).
  - The current Providers page lists no Claude subscription sign-in. Community plugins that restore it exist and are **rejected**: they go against Anthropic's terms as reported.
- **ChatGPT Plus or Pro:** **documented.** Connect OpenAI and choose "Sign in with ChatGPT" (or the legacy Codex methods). "Usage counts against your plan, so these models show no cost." OpenCode caps the context below the model limit by default, to match Codex ([Providers, ChatGPT](https://opencode.ai/docs/providers/)).
- **GitHub Copilot:** **documented.** Device OAuth, needs Copilot Chat access, and Copilot Free is named as a way in ([Providers, Copilot](https://opencode.ai/docs/providers/)).
- **OpenCode Go** (subscription): $10 a month (Go), $40 (Go Plus), or $20 per member (Go Teams), with monthly dollar allowances per model and a 5-hour share ([Go](https://opencode.ai/docs/console/go)).
  - The list includes open models and **Muse Spark 1.3 and 1.2 Contributor**, which train on request data and need a privacy switch.
  - It also includes some "Free" models (limited time, limited regions).
  - It does **not** list Muse Spark Open.
- **OpenCode Console** (pay-as-you-go credits; formerly Zen) ([Console models](https://opencode.ai/docs/console/models/)):
  - "Sign in, add credits, and get an API key"; charged per request.
  - A set of free models is listed (Big Pickle, GLM-5.3-Flash Free, DeepSeek V4.1 Flash Free, Nemotron 3 Ultra Free and others, mostly "for a limited time"), and "free-tier chat models require OpenCode".
  - Paid Meta models: Muse Wonder 1.0 ($4 / $20), Muse Spark 1.3 and 1.2 ($1.25 / $4.25).
  - **No Muse Spark Open.**
  - The [Policies page](https://opencode.ai/docs/policies/) names "the signed-out free tier" as the integration `opencode`, so the free models work without an account.
- **Local models:** built-in discovery for Ollama (`127.0.0.1:11434`), LM Studio (`:1234/v1`) and vLLM (`:8000/v1`). Discovered vLLM models start with tools disabled. Any other OpenAI-compatible server (llama.cpp, SGLang) is a custom provider with `baseURL` ([Providers](https://opencode.ai/docs/providers/)).
- **API keys:** any provider on models.dev, plus custom providers with an `env` list of variable names ([Providers](https://opencode.ai/docs/providers/)). The V1 CLI page says OpenCode also loads keys "defined in your environments or a .env file in your project" ([V1 CLI, auth login](https://docs.opencode.ai/docs/cli/)): **a project `.env` can supply a paid key.**

### What switches it to pay as you go

- **A provider credential in the environment of the OpenCode process**, for example:
  - `OPENROUTER_API_KEY` (named on the Providers page), `ANTHROPIC_API_KEY` (named on the Provider accounts page);
  - `AWS_BEARER_TOKEN_BEDROCK` and the AWS credential chain (`AWS_PROFILE`, `AWS_ACCESS_KEY_ID`, web identity, container credentials);
  - `GOOGLE_APPLICATION_CREDENTIALS` and ADC with a project variable;
  - `AZURE_RESOURCE_NAME` with an Entra session;
  - any name a custom provider lists in `env` ([Providers](https://opencode.ai/docs/providers/), [Provider accounts](https://opencode.ai/docs/cli/providers)).
  
  The full list of names that each built-in provider reads lives in models.dev and OpenCode's code, and was **not** collected.
- **A saved account** (API key, OAuth, or Console or Go key) in the SQLite database. It is not in the environment, so umwayi cannot remove it, only refuse with a policy (below).
- **Configuration that adds or points a provider:** `OPENCODE_CONFIG` (a custom config file), `OPENCODE_CONFIG_DIR` (a config directory with agents and plugins), `OPENCODE_CONFIG_CONTENT` (inline config), the project's `opencode.json(c)` and `.opencode/`, remote config from `.well-known/opencode`, and a project `.env` ([Config](https://docs.opencode.ai/docs/config/)).
- **Plans:**
  - ChatGPT and Copilot sign-ins count against the plan; overage behaviour is the plan's own, not documented by OpenCode.
  - The Go allowance runs out; what happens then is not read.
  - Console credits are prepaid; whether auto-reload exists was not read.
- **The tool to restrict it** (V2 [Policies](https://opencode.ai/docs/policies/)):
  - `provider.use` and `integration.use` allow or deny providers and connected accounts. "Policy applies however a provider became known", whether from environment variables, saved accounts, plugins or configuration.
  - Example: deny `*` and allow only `opencode` (the signed-out free tier) or one local provider.
  - The V1 equivalent is `enabled_providers` and `disabled_providers` ([Config](https://docs.opencode.ai/docs/config/)).

### Permissions, hooks and ACP permission requests

- **Permission rules (V2)** `{action, resource, effect}` with `allow`, `deny` or `ask`; the last match wins ([Permissions](https://opencode.ai/docs/permissions/)).
  - Actions include `read`, `edit`, `shell` (the scanned command string, each subcommand), `glob`, `grep`, `webfetch`, `websearch`, `subagent`, `skill`, `external_directory`, MCP tools and `execute`.
  - **The base policy allows everything** except `.env` reads, and with no `external_directory` rule, paths outside the project are allowed.
  - Saved "Allow always" approvals are durable project-scoped allows that never override a `deny`. An open issue reports one overriding a configured `ask` in later sessions ([#48456](https://github.com/anomalyco/opencode/issues/48456)).
- **Policies (V2)** run after rules and saved approvals and can only deny. A `tool.use` deny "overrides an ask and an 'Allow always' approval alike" ([Policies](https://opencode.ai/docs/policies/)).
  - Global and managed policies override project configuration.
  - A `plugin.use` deny stops a plugin from loading.
- **ACP permission requests** offer `once` (allow_once), `always` (allow_always) and `reject` (reject_once), with a diff for file changes ([V2 ACP reference](https://dev.opencode.ai/v2/docs/cli/acp/)).
  - Child-session (subagent) requests reach the client too, marked in `toolCall._meta`.
  - One client reports a request arriving before the tool call's `rawInput` is filled ([xenodium/agent-shell #614](https://github.com/xenodium/agent-shell/issues/614)).
  - **Not documented:** the exact `toolCall` fields (whether the permission `action` and `resource` are in it).
- **Plugins** are JS or TS modules from `.opencode/plugins/`, `~/.config/opencode/plugins/` or npm (installed with Bun at startup) ([Plugins](https://docs.opencode.ai/docs/plugins/)).
  - **`tool.execute.before`** runs before every tool call and can throw to abort it. That is the closest thing to the layer 9 PreToolUse hook.
  - Events include `permission.asked` and `permission.replied`.
  - A V2 Providers page shows a local package by an absolute `file://` URL for a provider ([Providers](https://opencode.ai/docs/providers/)). The V2 Policies page names plugins "by unversioned package name or absolute path", which suggests path loading, but loading a plugin from a path in config was **not confirmed** on a plugin page.
  - The `permission.ask` plugin hook "is defined but not triggered" ([#7006](https://github.com/anomalyco/opencode/issues/7006)).
- **So, can umwayi gate every tool call as for Claude Code and Kiro?**
  - **First gate:** a hook in front of every tool call exists only as a JS plugin (`tool.execute.before`). It would be umwayi's first non-Python adapter code, run by Bun inside OpenCode. No documented command or exec-form hook exists like Claude Code's or Kiro's.
  - **Second gate:** ACP permission requests, which umwayi already answers, but only for actions whose effect is `ask`. With the base policy allowing everything, there are none unless umwayi's config makes every action `ask`.
  - **What could make that strict without editing the owner's files:** an inline `OPENCODE_CONFIG_CONTENT` (listed in the V1 precedence order above the project config and below the managed files), plus a policy that denies every provider but the chosen one. Not confirmed for V2.
  - **Limits:** a managed `/etc/opencode` file or macOS MDM profile outranks anything umwayi passes, and saved approvals may override `ask`.
- **A canary** (to prove the gate is active before the first prompt, as in 7b): a plugin that writes the token file at `session.created`, or the first `ask` arriving. Not designed; not confirmed.

### OpenCode and Muse Spark Open

- **OpenCode can run Muse Spark Open** through any hosted provider that serves it:
  - OpenRouter: `openrouter/meta/muse-spark-open`, $1.25 / $4.25 per 1M; `:free` was seen in a search and then gave 404.
  - Together, Fireworks, Groq (preview).
  - A local OpenAI-compatible server (vLLM, llama.cpp, SGLang, MLX) as a vLLM or custom provider, with tool support switched on explicitly.
  
  Sources: section "Muse Spark Open as a platform" above, and [Providers](https://opencode.ai/docs/providers/).
- **Not through OpenCode's own subscription or free tier** (Go, Console). They list Muse Spark (closed) and Muse Spark Contributor, not Muse Spark Open.
- **So the owner's "subscription or free first" for Muse Spark Open through OpenCode comes down to:** local hardware (about 300 GB of memory or more), or a free hosted route that was not confirmed on Nov 9.

### What stays unknown

- The exact ACP `toolCall` shape of OpenCode's permission requests.
- Whether `OPENCODE_CONFIG_CONTENT` and path plugins work in V2.
- What the `opencode.db` holds for the owner (saved accounts umwayi cannot see).
- How Go and Console behave at the end of an allowance or balance.
- Overage rules of ChatGPT and Copilot plans.
- Which environment names each built-in provider reads.
- Which OpenCode version the owner runs (V1 and V2 differ in key names).
- How fast all of this changes.

The first two were checked on Nov 11; see the next section.

## OpenCode V2: the facts checked for the adapter spec (task 10.41, read Nov 11 2026)

Read on Nov 11 2026 for task 10.41, the five facts tasks.md asked for first. Nothing was installed or run: these come from the official V2 docs on opencode.ai, the npm registry, and the V2 source on the `dev` branch of [anomalyco/opencode](https://github.com/anomalyco/opencode). Where only the source says something, the note says "source only". A source fact can change in any release and is weaker than a documented one.

### 1. `OPENCODE_CONFIG_CONTENT` in V2

- **Documented: no.** The V2 [Config](https://opencode.ai/docs/config/) page lists managed, global and project files and names no `OPENCODE_CONFIG_CONTENT`, `OPENCODE_CONFIG` or `OPENCODE_CONFIG_DIR`. The only V2 page with an inline variable is the terminal settings page, and that variable, `OPENCODE_CLI_CONFIG_CONTENT`, is for `cli.json` (the TUI), not for the server config ([Settings, Inline config](https://opencode.ai/docs/cli/config/)). The V1 docs list `OPENCODE_CONFIG_CONTENT` as "runtime overrides", above project config and below managed files ([V1 Config](https://docs.dev.opencode.ai/docs/config)).
- **Source only: yes, it is read.** `packages/cli/src/server-process.ts` passes `content: process.env.OPENCODE_CONFIG_CONTENT` into the config options, next to `OPENCODE_CONFIG`, `OPENCODE_CONFIG_DIR` and `OPENCODE_DISABLE_PROJECT_CONFIG` ([server-process.ts on dev](https://github.com/anomalyco/opencode/blob/dev/packages/cli/src/server-process.ts)). `packages/core/src/config.ts` parses it as one document named `OPENCODE_CONFIG_CONTENT`, after `{env:...}` and `{file:...}` substitution, and a parse error ends the load (`Effect.orDie`) rather than skipping it ([config.ts on dev](https://github.com/anomalyco/opencode/blob/dev/packages/core/src/config.ts), last changed Nov 9 2026, commit 550bf20cb8).
- **Where it ranks for settings (source only):** the load order is managed policies, integration (Console) documents, well-known documents, the global directory, `OPENCODE_CONFIG`, direct project files, project `.opencode` directories, then the inline content, then managed settings. For ordinary settings the later one wins, so the inline content beats every user and project file and loses only to managed settings.
- **Where it ranks for policies (source only, and it matters):** policy statements are read "earliest-loaded first so it wins" (`ManagedPolicy.statements` reverses the documents; `decision` takes the last match) ([managed-policy.ts on dev](https://github.com/anomalyco/opencode/blob/dev/packages/core/src/managed-policy.ts), [config/plugin/policy.ts on dev](https://github.com/anomalyco/opencode/blob/dev/packages/core/src/config/plugin/policy.ts)). So **the inline content is the weakest place for a policy**: a `provider.use` or `integration.use` statement with `allow` in the global file, a project file, a connected Console workspace or a managed file outranks a `deny` that umwayi puts inline. This matches the documented order on [Policies, Precedence](https://opencode.ai/docs/policies/), which ranks managed preferences, the system file, the Console workspace, the global file and then project files, and does not list the inline content at all.
- **A broken config file is skipped:** an open issue on 2.2.5 reports that a `opencode.jsonc` with a missing comma was ignored with no warning and OpenCode ran on its permissive defaults ([#61447](https://github.com/anomalyco/opencode/issues/61447)). Statements that fail validation are dropped with a log warning ([Policies, Statements](https://opencode.ai/docs/policies/)).
- **Not confirmed:** that the inline content reaches the private server `opencode acp` starts (the ACP page says the private server is not the shared service, so the environment of the `opencode acp` process should apply, but no page says so); that a V2 release keeps reading it.

### 2. Loading a plugin from an absolute path

- **Documented: yes, for a directory.** V2 config takes a `plugins` array whose entries may be `"/absolute/path/plugin"` or `"file:///home/me/plugins/local"`, or an object `{"package": "...", "options": {...}}`. "Configured local paths must be directories. A path to a single file is skipped." Plugin arrays from every config file are applied from lowest to highest precedence, they do not replace one another ([Plugins, Configure](https://opencode.ai/docs/plugins/)). A V1 entry that names a file is skipped with a warning in the log ([Migrate plugins from V1](https://opencode.ai/docs/build/plugins/migrate-v1)).
- **The layout of a local plugin directory:** with no `package.json`, OpenCode uses the file names at its root, `server` (else `index`) with a `.ts`, `.tsx` or `.js` extension ([Build plugins, Load](https://opencode.ai/docs/build/plugins)).
- **The V2 hook API is not the V1 one.** V1 `tool.execute.before` becomes `ctx.tool.hook("execute.before", ...)`, registered in `setup(ctx)`. "V1 plugin implementations do not run in V2." The documented V2 example throws inside `execute.before` to stop a `read` of `.env` ([Migrate plugins from V1, Register hooks](https://opencode.ai/docs/build/plugins/migrate-v1)). `ctx.permission.hook("evaluate", ...)` runs for `allow` and `ask` decisions, never for a configured `deny`, and may change `effect` to `allow`, `ask` or `deny`; several plugins run in plugin order, and later hooks see earlier changes ([Server plugins, Hooks](https://opencode.ai/docs/build/plugins/server)). `ctx.options` holds the `options` of the config entry, and `setup` may return a cleanup function (same page).
- **No npm package is needed (source only).** The docs import `Plugin` from `@opencode/plugin`, but `Plugin.define` only returns its argument ([promise/plugin.ts on dev](https://github.com/anomalyco/opencode/blob/dev/packages/plugin/src/promise/plugin.ts)), and the loader accepts any default export with a string `id` and a `setup` (or `effect`) function, otherwise "Plugin must export a default definition with an id and an effect or setup function." ([plugin/module.ts on dev](https://github.com/anomalyco/opencode/blob/dev/packages/core/src/plugin/module.ts)). So a plain `index.js` with `export default { id, setup }` and only `node:` imports should load.
- **Policy control:** `plugin.use` denies a plugin "by unversioned package name or absolute path", and needs 2.2.3 or newer ([Policies](https://opencode.ai/docs/policies/)).
- **Not confirmed:** that a plugin path given only in the inline content loads (both facts above are true, but no page puts them together); which runtime runs it inside the `opencode` binary, and so whether `node:child_process` `spawnSync` works there; that the `session.created` event reaches a plugin before the client sends its first prompt.

### 3. The `toolCall` fields of a permission request

- **Documented:** the three options `once` (`allow_once`), `always` (`allow_always`) and `reject` (`reject_once`); a `diff` content when a file changes; `toolCall._meta["opencode/child-session"]` with `id`, `parentID`, `depth` and `title` on requests from a child session ([V2 ACP reference, Permissions and Child sessions](https://dev.opencode.ai/v2/docs/cli/acp/)). ACP itself says `toolCall` is a `ToolCallUpdate` and only `toolCallId` is required ([ACP, Requesting permission](https://agentclientprotocol.com/protocol/tool-calls)).
- **Source only, the exact fields** ([acp/permission.ts on dev](https://github.com/anomalyco/opencode/blob/dev/packages/cli/src/acp/permission.ts), last changed Oct 6 2026, and [acp/tool.ts on dev](https://github.com/anomalyco/opencode/blob/dev/packages/cli/src/acp/tool.ts)):
  - `toolCallId` (with the child session prefix `<childSessionId>:` for a child);
  - `name`: the tool's name, or absent when OpenCode has no tool for the request;
  - `title`, written from the tool name and input (agent-shaped text);
  - `kind`, mapped from the tool name;
  - `status`: `"pending"`;
  - `locations`: absolute paths from the input, or from the permission's resources for path actions;
  - `rawInput`: the tool's input, with `cwd` added for `shell`; **absent** when OpenCode has no tool for the request;
  - `content`: the diff previews, only when there are any;
  - `_meta`: only for a child session.
- **What is not in it:** the permission `action` and `resources` that the rules matched (they are on the server's `permission.asked` event, not in the ACP request). An older client report says the request can arrive before `rawInput` is filled ([xenodium/agent-shell #614](https://github.com/xenodium/agent-shell/issues/614)); in the V2 source above, `rawInput` is set on the request itself when the tool is known.
- **V1 tool names are aliased** in the ACP code: `bash` to `shell`, `task` to `subagent`, `apply_patch` to `patch` (acp/tool.ts above).

### 4. `opencode debug config` in V2

- **Exists (source):** `packages/cli/src/commands/handlers/debug/config.ts` asks a server for `config.get` at the current directory and prints the redacted result as JSON ([debug/config.ts on dev](https://github.com/anomalyco/opencode/blob/dev/packages/cli/src/commands/handlers/debug/config.ts)).
- **Its output changed:** in V2 it lists the config sources, an array of `{type, path, info}` entries (`document` or `directory`), not one merged config as in V1; reported on V2.1.4 with a sample ([ollama/ollama #19303](https://github.com/ollama/ollama/issues/19303)).
- **It talks to a server:** it resolves a server connection (`ServerConnection.resolve()`), which by default is the one shared background service per user ([CLI intro, Background service](https://opencode.ai/docs/cli/)). That service has its own environment, not the one umwayi would pass, so its answer does not show umwayi's inline content.
- **Not documented** on the V2 CLI pages read (only `opencode debug paths` and `opencode debug heap-dump` are: [CLI, Paths](https://opencode.ai/docs/cli/), [Troubleshooting](https://opencode.ai/docs/troubleshooting)). **Not confirmed:** whether `--standalone` applies to it, and so whether it can show the view of a private server started with umwayi's environment.

### 5. The first V2 version, and the versions since

- **V2 is a separate package, `@opencode/cli`**, not the `opencode-ai` package of V1. The GitHub releases page still lists V1 releases; Homebrew's `opencode` formula moved to 2.x; V1 gets only critical fixes ([#54813, a maintainer's answer](https://github.com/anomalyco/opencode/issues/54813)). The package installs two commands, `opencode` and `opencode2` ([npm, @opencode/cli 2.0.0](https://registry.npmjs.org/@opencode%2Fcli/2.0.0)).
- **First V2 release: 2.0.0, published to npm on Sep 11 2026.** Then 2.1.0 on Oct 20 and 2.2.0 on Oct 27. On Nov 11 the latest is **2.2.7** (Nov 10), the 46th stable 2.x release in two months ([npm registry, @opencode/cli](https://registry.npmjs.org/@opencode%2Fcli)).
- **Versions the design needs** ([Policies](https://opencode.ai/docs/policies/)):
  - 2.2.3 or newer for `integration.use` in its current meaning, `integration.connect`, `mcp.use`, `skill.use` and `plugin.use`; "Clients older than 2.2.3 ignore" them;
  - 2.2.6 or newer for `websearch.use`.
- **V1 refuses a V2 config:** V1 stops with "V2 permissions are not supported by OpenCode V1. Use V1 "permission" rules or run opencode2." when a config holds `permissions` (reported on an ACP start in an IDE, [#54133](https://github.com/anomalyco/opencode/issues/54133)). So a V1 `opencode` given umwayi's config fails to start rather than running ungated.
- **Not confirmed:** the exact text `opencode --version` prints in V2.

### Also read on Nov 11

- **The V2 ACP page** confirms the Nov 9 notes: `opencode acp` starts a private server, opens no port, exits when stdin closes; `cwd` must be absolute; one prompt at a time; `session/cancel` rejects pending permission requests; `session/new` answers with config options including `model` as `provider/model` ([V2 ACP reference](https://dev.opencode.ai/v2/docs/cli/acp/)). `usage_update` carries a session `cost` in USD (same page).
- **Disabling project config (source only):** `OPENCODE_DISABLE_PROJECT_CONFIG` (or `OPENCODE_CONFIG_PROJECT_DISABLE`) turns off the project walk, and `OPENCODE_CONFIG_DIR` replaces the global config directory (server-process.ts and [config/discovery.ts on dev](https://github.com/anomalyco/opencode/blob/dev/packages/core/src/config/discovery.ts)). Neither is on a V2 docs page.
- **Policies and the free tier:** with `integration.use` deny `*`, the signed-out free tier is the bare resource `opencode`, an `ANTHROPIC_API_KEY` in the environment is the bare `anthropic`, a provider from `opencode.json` is its provider ID, and a connected account is `<integration>#<account>` ([Policies, Integrations](https://opencode.ai/docs/policies/)).
- **Plugins in the system directory:** `/etc/opencode` (Linux), `/Library/Application Support/opencode` (macOS) and `%ProgramData%\opencode` (Windows) load `opencode.json(c)`, `agents/`, `commands/`, `skills/` and `plugins/` for every user, and macOS also reads managed preferences for the domain `ai.opencode.managed` ([Config, Locations](https://opencode.ai/docs/config/)).

### What could not be confirmed on Nov 11

- That V2 keeps reading `OPENCODE_CONFIG_CONTENT`: it is in the source and not in the V2 docs.
- That a plugin path given only in the inline content loads, and that a plain JS plugin with `node:` imports runs in the binary's runtime.
- When `session.created` reaches a plugin compared with the client's first prompt.
- What `opencode --version` prints.
- Whether `opencode debug config --standalone` shows a private server's view.
- The provider ID of OpenCode Go in a policy, and the `integration.use` resource of a saved API-key account compared with a ChatGPT sign-in (both are `openai`).
- Everything here on a real install: no OpenCode was run. The owner's real check (tasks.md 10.51) records it.

Most of these were checked on a real install the same day (task 10.42); see the next section.

## OpenCode 2.2.7 on a real install (task 10.42, run Nov 11 2026)

Run on Nov 11 2026 between 10:57 and 11:10 UTC for task 10.42. Nothing here is umwayi code, and umwayi installed nothing: the probes below are throwaway files outside the repository, deleted afterwards.

### Where it ran

- **A throwaway sandbox, not the owner's machine:** a Linux x86_64 container with open internet, Node v22.23.4, npm 11.4.2, Python 3.11. Everything lived in one folder outside the repository (`/projects/sandbox/.oc-sbx`), with `HOME` and the four `XDG_*` folders pointing inside it, and was removed at the end.
- **Every OpenCode command** ran with `env -i` and only `HOME`, `PATH=/usr/bin:/bin`, `LANG`, `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_STATE_HOME` and `XDG_CACHE_HOME` set (all inside the folder), plus `OPENCODE_CONFIG_CONTENT` where a run needed it. No provider key, no account and no sign-in were used.
- **The model was a fake:** a small Python OpenAI-compatible server on `127.0.0.1` that logged every request and answered with a scripted tool call or text. No hosted model was called. A custom provider pointed at it (`"package": "@opencode/ai/providers/openai-compatible"`, `settings.baseURL`).
- **The ACP client was a throwaway Python script.** It started `opencode acp` in the work folder, sent `initialize` (`clientCapabilities: {}`), `session/new` and one `session/prompt`, and answered every permission request with `once`. It logged every message with its time.
- **The plugin was a throwaway probe**, `probe/plugin/index.js`, with `node:` imports only. It logged `setup`, one `spawnSync`, one `O_EXCL` file write, every `execute.before`, every `evaluate`, and every `session.created`.

### The install

```
$ npm view @opencode/cli dist-tags --json
{ "reserved": "0.0.0-reserved", "beta": "0.0.0-beta-19507", "latest": "2.2.7", "dev": "0.0.0-dev-1169" }
$ npm view @opencode/cli versions --json      (the last 2.2.x entries)
"2.2.5" "2.2.6" "2.2.7"
$ HOME=$S/home npm install --prefix $S/prefix --ignore-scripts --no-audit --no-fund @opencode/cli@2.2.7
added 13 packages in 7s                          (exit 0)
```

- `--ignore-scripts` worked. With it, `bin/opencode.exe` is a 229-byte shell placeholder that prints "@opencode/cli's postinstall script was not run." and exits 1.
- The postinstall script (`postinstall.mjs`) only picks the platform package and copies its binary into `bin/`, so it was not run. The platform binary was run directly: `node_modules/@opencode/cli-linux-x64/bin/opencode`, 258848944 bytes, SHA-256 `589253d36810f21217edd51545cd435b328cdc3cf4f451fbe0cce6f88afcf5e1`, from `https://registry.npmjs.org/@opencode/cli-linux-x64/-/cli-linux-x64-2.2.7.tgz`.

### 1. `opencode --version`

```
$ env -i HOME=... XDG_...=... PATH=/usr/bin:/bin opencode --version
opencode v2.2.7                                  (exit 0)
$ ... opencode --version | od -c
o p e n c o d e   v 2 . 2 . 7 \n
```

One line, `opencode v` and the version, then a newline. It opened no server: no process was left, and no file was written for it.

### 2. A plugin named only in `OPENCODE_CONFIG_CONTENT`

The inline config of the first run (`cfg1.json`, passed as the bytes of `OPENCODE_CONFIG_CONTENT`):

```json
{"permissions":[{"action":"*","resource":"*","effect":"ask"}],
 "policies":[{"action":"provider.use","resource":"*","effect":"deny"},{"action":"provider.use","resource":"probe","effect":"allow"},
             {"action":"integration.use","resource":"*","effect":"deny"},{"action":"integration.use","resource":"probe","effect":"allow"}],
 "model":"probe/probe-model",
 "providers":{"probe":{"package":"@opencode/ai/providers/openai-compatible","settings":{"baseURL":"http://127.0.0.1:18001/v1"},
                      "models":{"probe-model":{"capabilities":{"tools":true}}}}},
 "plugins":[{"package":"/projects/sandbox/.oc-sbx/probe/plugin","options":{"canary":"/projects/sandbox/.oc-sbx/probe/canary","token":"T","block":["glob"]}}]}
```

Command: `python3 acp_probe.py cfg1.json`, which ran `opencode acp` with that environment. The plugin log:

```
{"ev":"setup","options":{"canary":".../probe/canary","token":"T","block":["glob"]},"version":"2.2.7","runtime":"bun 1.4.4"}
{"ev":"spawnSync","status":3,"error":null,"stdout":"spawn-ok\n"}
{"ev":"fs-excl-ok"}
{"ev":"session.created","keys":["id","created","type","durable","location","data"],"type":"session.created"}
```

- **Confirmed:** a plugin directory named only in the inline config loads, and its `options` arrive unchanged in `ctx.options`.
- **The runtime is Bun 1.4.4**, inside the binary. `node:child_process` `spawnSync` works: `/bin/sh -c "echo spawn-ok; exit 3"` returned status 3 and its stdout. `node:fs` `openSync` with `O_WRONLY | O_CREAT | O_EXCL` and mode `0o600` works; the file was created `-rw-------`.
- **`setup` runs at the first `session/new`,** not at the start of the process. It ran about 0.5 s after `initialize` was answered.
- **Throwing in `execute.before` stops the call** (run 3, `"block":["glob"]`). The tool call ended `failed` with the thrown text, `probe: blocked`, as its content, and no permission request was sent for it. The model saw that text.
- The inline config was parsed with no error on stderr (`--print-logs` was not used; stderr was empty).

### 3. When `session.created` arrives

Times from the same run (Unix seconds, from the client's log and the plugin's log):

```
out initialize            1794394746.462
in  answer to initialize  1794394746.817
out session/new           1794394746.817
plugin setup              1794394747.313
plugin session.created    1794394747.438
in  answer to session/new 1794394747.440
```

`session.created` reached the plugin 2 ms **before** the client got the answer to `session/new`. The canary is written before umwayi could send a first prompt. The 30 s wait of the design is far more than needed; it stays as the limit.

### 4. Which tools ask permission

Run 2 (`"say hi"`, the fake answers text) logged the tools OpenCode sent the model, with their required parameters:

```
edit      ['path', 'oldString', 'newString']
glob      ['pattern']
grep      ['pattern']
question  ['questions']
read      ['path']
shell     ['command']
skill     ['id']
subagent  ['agent', 'description', 'prompt']
webfetch  ['url']
write     ['path', 'content']
execute   ['code']
```

Run 3 had the fake call each tool once, with the `ask` rule for everything, and every request answered `once`. The plugin's `glob` block was on. Results:

| tool | `execute.before` | `evaluate` (action, resources) | permission request | result |
| --- | --- | --- | --- | --- |
| `read` | yes | `read`, `["a.txt"]` | yes | completed |
| `glob` | yes | (blocked by the probe first) | no | failed: `probe: blocked` |
| `grep` | yes | `grep`, `["hello"]` | yes | completed |
| `write` | yes | `edit`, `["b.txt"]` | yes | completed |
| `edit` | yes | `edit`, `["a.txt"]` | yes | completed |
| `shell` | yes | `shell`, `["echo hi > c.txt"]` | yes | completed |
| `webfetch` | yes | `webfetch`, `["http://127.0.0.1:18001/page"]` | yes | completed |
| `skill` (an unknown id) | yes | none | no | failed: `Unable to load skill nope` |
| `execute` (`1+1`) | yes | none | **no** | completed: `2` |
| `question` | yes | `question`, `["*"]` | yes | failed: the client cannot show questions |
| `subagent` | yes | `subagent`, `["general"]` | yes | completed |
| `read` in the child session | yes | `read`, `["a.txt"]` | yes | completed |

Run 4 had `glob` unblocked, and `execute` with code that calls `fetch` and an inner tool:

```
{"tool":"execute","args":{"code":"const r = await fetch('http://127.0.0.1:18001/egress-from-execute'); const w = await tools.opencode.worktree_list(); return [r.status, JSON.stringify(w)]"}}
```

```
PLUGIN execute.before glob   -> evaluate glob ["*.txt"] -> PERM glob search
PLUGIN execute.before execute
PLUGIN evaluate webfetch ["http://127.0.0.1:18001/egress-from-execute"]   -> PERM name "execute", kind "other", rawInput {"code": "..."}
PLUGIN execute.before opencode_worktree_list   (no evaluate, no permission request)
DONE   execute completed: [200, "{\"worktrees\":[]}"]
fake model log: {"get": "/egress-from-execute"}
```

- **Asked (confirmed):** `read`, `glob`, `grep`, `write`, `edit`, `shell`, `webfetch`, `question`, `subagent`.
- **Not asked by itself:** `execute`. This is Code Mode: JavaScript with `fetch` and the Code Mode tools (`tools.opencode.session_move`, `worktree_create`, `worktree_list`, `worktree_remove`, `list_mcp_resources`, `models` and others).
  - A `fetch` inside it is checked as a `webfetch` permission, but the request carries the `execute` tool call: `name: "execute"`, `kind: "other"`, and the code as `rawInput`. The URL is not in the `toolCall`.
  - Each inner tool goes through `execute.before` under its own name (`opencode_worktree_list`), and asks no permission.
- **Not confirmed:** `skill` with a real skill (an unknown id failed before any check); `patch`, `list` and `websearch` were not offered in this setup.
- **`tool_input` field names in `execute.before`:** `path` (not `filePath`), `command`, `pattern`, `url`, `code`, `agent`, `description`, `prompt`, `content`, `oldString`, `newString`. Through the stdio adapter they become `input_path`, `input_command` and so on.
- **Resources in `evaluate` are relative to the work folder** (`a.txt`), while `rawInput` and `locations` hold absolute paths.

### 5. The URL setting of a built-in local provider

Run 5 used the built-in `vllm` provider with `"providers":{"vllm":{"settings":{"baseURL":"http://127.0.0.1:18002/v1"}}}`, `model: vllm/probe-model`, and the fake on port 18002. The fake's log:

```
{"get": "/health"}
{"get": "/v1/models"}
```

- With a plain `{"data":[{"id":"probe-model"}]}` model list, `session/new` failed: `"Internal error: No models are available"`, `CatalogNotReady`.
- With a vLLM-shaped list (`owned_by: "vllm"`, `max_model_len`), the whole turn worked. The chat completions went to port 18002 with `model: "probe-model"` and the full tool list.
- Adding a `models` entry for `probe-model` under `vllm` made `session/new` succeed but the prompt fail: `"No model is available for session ..."`, `provider.no-route`.

Run 6 did the same for `ollama` (port 18003) and `lmstudio` (port 18004):

```
ollama:   {"get": "/api/tags"}        then "No models are available" (the fake does not speak Ollama's list)
lmstudio: {"get": "/api/v1/models"}   then a turn with "model": "openai/gpt-oss-20b"
```

- **Confirmed:** `providers.<id>.settings.baseURL` sets where `vllm`, `ollama` and `lmstudio` look. Discovery used the configured port for all three. For `ollama` and `lmstudio`, discovery drops the `/v1` path.
- **A built-in local provider must not get a `models` entry:** with one, the route breaks.
- **A model that is not found is replaced silently.** With `model: lmstudio/probe-model`, which the server did not list, OpenCode chose `lmstudio/openai/gpt-oss-20b` from its own catalogue. It reported that as `currentValue` of the `model` config option in the `session/new` answer, and sent that model ID to the server. No error was given.
- A discovered vLLM model was sent tools. The Nov 9 note says discovered vLLM models start with tools disabled; that was not seen on 2.2.7.

### 6. OpenCode Go

- **Not checked on the wire:** that needs a Go sign-in, and none was used.
- `opencode models --standalone` with no account listed 12 models, all `opencode/...` free models (`opencode/big-pickle`, `opencode/glm-5.3-flash-free` and others). `opencode auth list --standalone` printed `No authenticated integrations`.
- **From the 2.2.7 binary's own code** (`strings` on the binary, not documentation):
  - the provider ID is `opencode-go`;
  - `opencode auth login` sorts integrations with the order `opencode-go`, `opencode`, `openai`, `github-copilot`, `anthropic`, `google`;
  - a check reads `integrationID==="opencode"&&t.id!=="opencode-go"`, which suggests that Go's provider comes through the `opencode` integration, the same as the Console. If so, its `integration.use` resource is `opencode#ACCOUNT`, the same as Console pay-as-you-go credits, and only `provider.use` can tell them apart.
  - **Not confirmed.**

### 7. Permission requests on the wire

From run 3. The `content` diffs are shortened to their types:

```
read:     {"toolCallId":"call_0","name":"read","title":"/.../work/a.txt","kind":"read","status":"pending",
           "locations":[{"path":"/.../work/a.txt"}],"rawInput":{"path":"/.../work/a.txt"}}
write:    {"toolCallId":"call_3","name":"write","title":"/.../work/b.txt","kind":"edit","status":"pending",
           "locations":[{"path":"/.../work/b.txt"}],"rawInput":{"path":"/.../work/b.txt","content":"new"}}   content: ["diff"]
edit:     {"toolCallId":"call_4","name":"edit","title":"/.../work/a.txt","kind":"edit","status":"pending",
           "locations":[{"path":"/.../work/a.txt"}],"rawInput":{"path":"...","oldString":"hello","newString":"bye"}}   content: ["diff"]
shell:    {"toolCallId":"call_5","name":"shell","title":"echo hi > c.txt","kind":"execute","status":"pending",
           "locations":[{"path":"/.../work"}],"rawInput":{"command":"echo hi > c.txt","cwd":"/.../work"}}
subagent: {"toolCallId":"call_10","name":"subagent","title":"subagent","kind":"think","status":"pending",
           "locations":[],"rawInput":{"agent":"general","description":"look","prompt":"read a.txt"}}
child:    {"toolCallId":"ses_e35bc5959fferrPLlDQh8JrdYK:call_11","name":"read","title":"look: /.../work/a.txt","kind":"read",
           "status":"pending","locations":[{"path":"/.../work/a.txt"}],"rawInput":{"path":"/.../work/a.txt"},
           "_meta":{"opencode/child-session":{"id":"ses_e35bc5959fferrPLlDQh8JrdYK","parentID":"ses_e35bc5bb8fferyD0KwIiAVi7V5","depth":1,"title":"look"}}}
options every time: ["once", "always", "reject"]
```

- **Confirmed:** the fields match the Nov 11 source reading. `rawInput` was filled on every request seen. `shell` gets `cwd` added.
- **`kind` per tool:**

  | tool | `kind` |
  | --- | --- |
  | `read` | `read` |
  | `glob`, `grep` | `search` |
  | `write`, `edit` | `edit` |
  | `shell` | `execute` |
  | `webfetch` | `fetch` |
  | `question`, and `execute` (for a `fetch` inside it) | `other` |
  | `subagent` | `think` |

- `write` asks under the permission action `edit`.
- In a child session, the child request has the child session prefix on the ID, the child's title in front of the title, and the `_meta` key.

### Also seen

- **`opencode debug config --standalone` shows the inline config.** With `OPENCODE_CONFIG_CONTENT='{"model":"opencode/big-pickle","policies":[...]}'` it printed an array: the global config directory as `{"type":"directory","path":...}`, then the inline content as `{"type":"document","info":{...}}` with no `path`. The model was shown as `{"providerID":"opencode","model":"big-pickle"}`. Exit 0.
- **What OpenCode wrote in `HOME`:**
  - an empty `~/.config/opencode/` (no file in it);
  - `~/.local/share/opencode/opencode.db`, a log, a `repos` folder and a shell output folder;
  - `~/.cache/opencode/bin/rg`: it fetched `ripgrep` from the network on first use.
- **No OpenCode process was left** after each run. `opencode acp` exited 0 when stdin closed, and the `--standalone` commands left nothing running.

### What 10.42 could not confirm

- The Go route: the provider ID `opencode-go` comes only from the binary's code, and its integration resource and billing were not seen.
- `skill` with a real skill, and whether `patch`, `list` and `websearch` ask (they were not offered).
- The plugin's `evaluate` raising `allow` to `ask` when the config has no `ask` rule: the probe raised it, but every run had the `ask` rule as well.
- Behaviour with a real model, a real sign-in, or on macOS or Windows. The owner's real check (tasks.md 10.51) covers the owner's own machine.

## The owner's real check of the OpenCode chat (10.51): steps and results (NOT DONE YET)

Written Nov 13 2026 with the docs half of task 10.51. The code of tasks 10.43 to 10.50 is tested only against a fake `opencode` (10.47) and the plugin under `node`. This is the first time a real OpenCode meets umwayi's chat. It is the owner's, on the owner's machine; nothing here was run by the build, and 10.51 is ticked in tasks.md only after the results table below is filled in.

Rules for this check:

- Record version strings, exit codes, file names and counts only. Never paste a token, a key, an account name, an email, a URL or the text of a conversation into this file.
- Use the free tier (`provider: opencode`) or a local model. Do not use a provider key.
- Do the steps in order. Stop at the first step that fails, write what happened in the table, and tell the build.

Setup, once: install OpenCode 2.2.3 or newer yourself; put an `opencode` agent in `agents.yaml` (see `adapters/opencode/README.md`); keep a throwaway folder as its `workdir`. umwayi gives OpenCode no home folder of its own (KNOWN-LIMITS 251): it passes your `HOME` and `XDG_*` through. To keep your own files out of this, make a new empty home with `H="$(mktemp -d)"` and start every umwayi command of steps 1 to 5 as `env -u XDG_CONFIG_HOME -u XDG_DATA_HOME -u XDG_CACHE_HOME -u XDG_STATE_HOME HOME="$H" umwayi ...`. The free tier needs no sign-in; a route that does would find no account in the new home.

1. **OpenCode 2.2.3 or newer.** `opencode --version`; `umwayi agent check NAME; echo "exit $?"`. Expected: six lines `ok:` (`command`, `version`, `files`, `managed config`, `other config`, `route`), then `Gated: the checks for an OpenCode chat of agent NAME passed. Nothing was started.` and `exit 0`. Record the version and the exit code.
2. **The canary seen.** `umwayi agent chat NAME`. Expected: the queue lines, `Nothing you type is sent until the plugin is confirmed in the session (at most 30 s).`, then within 30 seconds `Connected. Type a message, :queue to see the queue, or :quit to end the chat.` If it prints `The first gate could not be confirmed in the ACP session. Nothing was sent.` and exits 2, the plugin did not load or did not write the canary: record that and stop (KNOWN-LIMITS 180, 184).
3. **One hook entry per tool call.** In the same chat type one line with a word to search for later, for example `Read README.md, then run the shell command ls. Word: PURPLEHERON`, answer `y` or `n` to any `Allow once? [y/N]`, then `:quit` (expected exit 0). Then `umwayi logbook verify; echo "exit $?"` (expected `ok:` and `exit 0`) and count in LOGBOOK.md: the `Source: umwayi check` entries with `action type: tool_` (one for every tool call the chat showed), the entries with `action type: acp_permission`, and `Started agent NAME (opencode, acp, chat)` and `Agent NAME exited with code 0`. `grep -c PURPLEHERON LOGBOOK.md` must print `0`. Record the tool lines shown against the `tool_` entries counted. Also record whether any tool call ran with no `tool_` entry, or any `tool_` entry has no tool call.
4. **The real `--version` output.** Record the whole output of `opencode --version`, exactly (on 2.2.7 it was `opencode v2.2.7`), and say whether the check of step 1 read it as that version. This confirms KNOWN-LIMITS 187.
5. **A refusal with a planted project `opencode.json`.** In the workdir run `printf '{}\n' > opencode.json`, then `umwayi agent check NAME; echo "exit $?"` and `umwayi agent chat NAME; echo "exit $?"`. Expected: `no: other config: ... opencode.json exists in the workdir or a folder above it`, `Not gated: ... would be refused (exit 2)`, `exit 2`, and no OpenCode process (`pgrep -a opencode` prints nothing). Delete the file afterwards. Record both exit codes and the `other config` line.
6. **What OpenCode wrote in HOME.** After steps 2 and 3, list that home folder with `find "$H" -type f | head -50`. Record the names, not the contents. Look for: `.local/share/opencode/opencode.db`, a log, `.config/opencode/`, and `.cache/opencode/bin/rg` (the `ripgrep` that 2.2.7 downloaded on first use, KNOWN-LIMITS 191). Say whether any of them is new since 10.42, and whether `bin/rg` was fetched in this chat.

### Results (to be filled in by the owner; all NOT DONE)

| step | what to record | result |
| --- | --- | --- |
| 1 | the version; `agent check` exit code and the six `ok:` lines | not done |
| 2 | whether `Connected.` came within 30 s; how many seconds | not done |
| 3 | tool lines shown; `tool_` entries; `acp_permission` entries; `PURPLEHERON` count; logbook verify | not done |
| 4 | the whole output of `opencode --version` | not done |
| 5 | `agent check` and `agent chat` exit codes with a planted `opencode.json`; the `other config` line; any process left | not done |
| 6 | the file names OpenCode wrote in HOME; `bin/rg` fetched or not | not done |

## Budget governor: Claude Code telemetry (B.10, the owner's capture)

Built in PR 33. What the receiver expects, from design.md "Budget governor", Facts (read Nov 9 2026, [Claude Code, Monitoring](https://code.claude.com/docs/en/monitoring-usage)):

- `POST /v1/logs` with `resourceLogs[].scopeLogs[].logRecords[]`; an `api_request` event is a record whose attribute `event.name` is `api_request` (or whose `body.stringValue` is `claude_code.api_request`), with the attributes `cost_usd_micros` (an `intValue`), `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens` (each an `intValue`) and `model` (a `stringValue`).
- `POST /v1/metrics` with `resourceMetrics[].scopeMetrics[].metrics[]`; `claude_code.cost.usage` data points with `asDouble` (or `asInt`), and `claude_code.token.usage` data points with `asInt` and the attributes `type` (`input`, `output`, `cacheRead`, `cacheCreation`) and `model`.

Not confirmed: the exact nesting and value shapes Claude Code emits, and whether a short run exports before it exits. The owner's capture (tasks.md B.10) records them.

### The capture, step by step (written Nov 11 2026 for the owner checks panel, from tasks.md B.10 and `umwayi/telemetry.py`)

Not run by the build. The capture file holds field names and types only, never a value, but record only names and types from it all the same. It needs the `reviewer` agent of the 10.31 run, signed in.

1. Choose a file name that does not exist yet, because umwayi never overwrites a capture: `ls /tmp/umwayi-capture.jsonl`. Expected: `No such file or directory`.
2. Run one short Claude Code run with the capture on: `UMWAYI_TELEMETRY_CAPTURE=/tmp/umwayi-capture.jsonl umwayi agent run reviewer --prompt "say hi"; echo "exit $?"`. Expected: the run ends and `exit 0`.
3. Look at the shapes: `cat /tmp/umwayi-capture.jsonl`. Expected: one line for each new shape, each with a `path` (`/v1/logs` or `/v1/metrics`) and a `shape` of names and types.
4. Count the lines: `wc -l /tmp/umwayi-capture.jsonl`. Record the number, the paths and the field names. If the file does not exist, a short run exported nothing before it exited: record that.
5. Take the file away: `rm /tmp/umwayi-capture.jsonl`.

- Capture: not done yet. Date: (none). Field names: (none recorded).
