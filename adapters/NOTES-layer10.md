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
