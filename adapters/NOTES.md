# Adapter notes (layer 9)

What the official platform docs say about hooks, written down before any adapter code (tasks.md 9.1), and the action types the adapters send to `umwayi check`.

Read on Nov 8 2026. Docs change: check the links again before you rely on a detail. Everything here is in my own words. Where a page does not say something, this file says so instead of guessing.

## Claude Code

Source: the hooks reference, https://code.claude.com/docs/en/hooks (sections named below). The adapter in `adapters/claude_code/` is built from these notes.

### Where hooks are configured

- Hooks live in JSON settings files: `~/.claude/settings.json` (all your projects), `.claude/settings.json` (one project, can be committed), `.claude/settings.local.json` (one project, not shared), managed policy settings, plugins, skills and subagent frontmatter. ([Hook locations](https://code.claude.com/docs/en/hooks#hook-locations))
- A config has three levels: the event (`PreToolUse`), a matcher group (which tools), and one or more handlers. A matcher of `"*"`, or no matcher, matches every tool. ([Configuration](https://code.claude.com/docs/en/hooks#configuration), [How a hook resolves](https://code.claude.com/docs/en/hooks#how-a-hook-resolves))
- A command handler can use exec form: `command` is the program and `args` its argument list, with no shell in between. ([Command hook fields](https://code.claude.com/docs/en/hooks#command-hook-fields))
- Hooks from settings files also run when a subagent calls a tool, and the input then names the subagent (`agent_id`, `agent_type`). ([Hook locations](https://code.claude.com/docs/en/hooks#hook-locations))

### When PreToolUse runs

- `PreToolUse` runs after Claude has built the tool's parameters and before the tool runs. It matches built-in tools (Bash, PowerShell, Edit, Write, Read, Glob, Grep, Agent, WebFetch, WebSearch and others) and MCP tools, but not `EndConversation`. ([PreToolUse](https://code.claude.com/docs/en/hooks#pretooluse))
- It only runs when Claude calls a tool. Files you mention with `@` in a prompt are added without a tool call, so no PreToolUse hook sees them. ([PreToolUse](https://code.claude.com/docs/en/hooks#pretooluse))

### Input fields

The hook gets one JSON object on stdin. ([Hook lifecycle](https://code.claude.com/docs/en/hooks#hook-lifecycle))

- Common fields: `session_id`, `transcript_path`, `cwd`, `hook_event_name`, and on most events `permission_mode` (`default`, `plan`, `acceptEdits`, `auto`, `dontAsk` or `bypassPermissions`). Some sessions also send `prompt_id`, `scratchpad_dir`, `effort`, `agent_id`, `agent_type`. ([Common input fields](https://code.claude.com/docs/en/hooks#common-input-fields))
- PreToolUse adds `tool_name`, `tool_input` and `tool_use_id`. MCP tool calls also carry `mcp_server`. ([PreToolUse input](https://code.claude.com/docs/en/hooks#pretooluse-input))
- For `Write`, `Edit` and `Read`, `tool_input.file_path` is always an absolute path; Claude Code expands `~` and relative paths first. On Windows it uses backslashes. ([PreToolUse input](https://code.claude.com/docs/en/hooks#pretooluse-input))
- `tool_input` per tool, the fields the adapter uses: Bash and PowerShell `command`; Write `file_path` (and `content`); Edit `file_path` (and `old_string`, `new_string`); Read `file_path`; Glob `pattern`, `path`; Grep `pattern`, `path`; WebFetch `url`; WebSearch `query`; Agent `subagent_type` (and `prompt`). ([PreToolUse input](https://code.claude.com/docs/en/hooks#pretooluse-input))

### Output: allow, deny or ask

- To decide, exit 0 and print one JSON object with `hookSpecificOutput.hookEventName` set to `"PreToolUse"` and `hookSpecificOutput.permissionDecision` set to `"allow"`, `"deny"`, `"ask"` or `"defer"`, with a `permissionDecisionReason`. ([PreToolUse decision control](https://code.claude.com/docs/en/hooks#pretooluse-decision-control))
- `allow` skips the permission prompt, with some exceptions (actions no mode approves, reads from network paths). `deny` stops the call and shows the reason to Claude. `ask` shows the user a confirmation prompt with the reason. `defer` is only for non interactive `-p` runs. ([PreToolUse decision control](https://code.claude.com/docs/en/hooks#pretooluse-decision-control))
- Claude Code's own deny and ask permission rules are still applied, whatever the hook returns. ([PreToolUse decision control](https://code.claude.com/docs/en/hooks#pretooluse-decision-control))
- If several hooks disagree, the strictest wins: deny, then defer, then ask, then allow. ([PreToolUse decision control](https://code.claude.com/docs/en/hooks#pretooluse-decision-control))
- Stdout counts as JSON only when it is one JSON object and nothing else but whitespace. ([Exit code 0](https://code.claude.com/docs/en/hooks#exit-code-0))
- Exit 0 with no output means no decision: the normal permission flow applies, and the hook has not approved anything. ([How a hook resolves](https://code.claude.com/docs/en/hooks#how-a-hook-resolves))
- The older top level `decision` and `reason` fields are deprecated for PreToolUse. ([PreToolUse decision control](https://code.claude.com/docs/en/hooks#pretooluse-decision-control))
- In a non interactive `-p` run with nobody to answer a prompt, an `ask` ends up as a denial, and Claude reads the reason. ([PreToolUse decision control](https://code.claude.com/docs/en/hooks#pretooluse-decision-control))

### Exit codes: which one blocks, and what exit 1 does

- **Exit 2 blocks.** On PreToolUse it blocks the tool call, and stderr becomes the reason Claude sees. Exit 2 blocks even if the hook also printed JSON that says allow. ([Exit code 2](https://code.claude.com/docs/en/hooks#exit-code-2), [Exit code 2 behavior per event](https://code.claude.com/docs/en/hooks#exit-code-2-behavior-per-event))
- **Exit 1, and every other code, does not block.** It is a non blocking error: the tool call goes ahead and the transcript shows a hook error notice. The same is true when the hook cannot start (a wrong path), or prints JSON that cannot be parsed. ([Exit code output](https://code.claude.com/docs/en/hooks#exit-code-output), [Other exit codes](https://code.claude.com/docs/en/hooks#other-exit-codes))
- One exception: if a hook exits with another code but prints valid JSON, the JSON decides. ([Exit code output](https://code.claude.com/docs/en/hooks#exit-code-output))
- **`onFailure: "block"`** makes a failed hook block the tool call. Failed means it could not start, exited with a code other than 0 or 2, hit its timeout, or printed invalid output. It needs Claude Code v2.1.295 or later. Without it, all of these let the tool call run. ([Common fields](https://code.claude.com/docs/en/hooks#common-fields), [Block the action when a hook fails](https://code.claude.com/docs/en/hooks#block-the-action-when-a-hook-fails))

### Timeouts

- `timeout` is in seconds. The default for a command hook is 600 seconds (lower on a few other events, not on PreToolUse). ([Common fields](https://code.claude.com/docs/en/hooks#common-fields))
- A command hook that hits its timeout is a failure: a non blocking error unless `onFailure` is `"block"`. ([Block the action when a hook fails](https://code.claude.com/docs/en/hooks#block-the-action-when-a-hook-fails))

### The `if` field is best effort

- The `if` field narrows a handler with permission rule syntax, for example `Bash(rm *)`. The docs say it is best effort and recommend the permission system, not a hook, for a hard allow or deny. ([Common fields](https://code.claude.com/docs/en/hooks#common-fields), [How if patterns match Bash commands](https://code.claude.com/docs/en/hooks#bash-if-matching))

### What this means for the adapter

| situation | what the adapter does | why |
| --- | --- | --- |
| umwayi says Yes | exit 0, `permissionDecision: allow` | allow is the documented JSON decision |
| umwayi says No | exit 0, `permissionDecision: deny` | deny is documented; the reason reaches Claude |
| umwayi says Ask me first | exit 0, `permissionDecision: ask` | Claude Code has ask, so no queue item is needed |
| anything goes wrong | exit 2, reason on stderr | exit 2 is the only code that blocks without JSON; exit 1 would let the call run |
| the hook cannot start or times out | the settings snippet sets `onFailure: "block"` and `timeout: 30` | without onFailure, a missing script or a timeout lets the call run |

## Kiro

Source pages: [Hooks](https://kiro.dev/docs/hooks/), [Hook types](https://kiro.dev/docs/hooks/types/) and [Hook actions](https://kiro.dev/docs/hooks/actions/).

**How I read them:** the HTML pages render with JavaScript, and a plain fetch returns only their title. I read the Markdown copies that the official index [kiro.dev/llms.txt](https://kiro.dev/llms.txt) lists: [hooks.md](https://kiro.dev/docs/hooks.md), [hooks/types.md](https://kiro.dev/docs/hooks/types.md) and [hooks/actions.md](https://kiro.dev/docs/hooks/actions.md). In those copies, the JSON example blocks for the Pre Tool Use event are empty, so the exact input fields are not shown there.

The Kiro adapter in `adapters/kiro/` (tasks.md 9.4 to 9.6) is built from these notes only. Re-checked on Nov 8 2026.

### Hook types and where they live

- Hooks are JSON files in `.kiro/hooks/` in the project. Kiro CLI V3 also loads global hooks from `~/.kiro/hooks/`. Each file has `version: "v1"` and a `hooks` list; each hook has a `name`, a `trigger`, an optional `matcher` and an `action`. ([Hooks](https://kiro.dev/docs/hooks.md))
- Triggers include Prompt Submit, Agent Stop, Session Start, Pre Tool Use, Post Tool Use, File Create, File Save, File Delete, Pre and Post Task Execution, and compaction hooks. Pre Tool Use exists in the IDE and the CLI, not in Web sessions. ([Hook types](https://kiro.dev/docs/hooks/types.md))
- For Pre Tool Use, the matcher picks tools by ID, category (`read`, `write`, `shell`, `web`, `spec`), source (`@mcp`, `@builtin`, `@<server>`) or regular expression. Built-in tool IDs include `read_file` and `execute_bash`; MCP tools appear as `mcp_<server>_<tool>`. ([Hook types](https://kiro.dev/docs/hooks/types.md))
- The one Pre Tool Use event example that is shown (for an MCP tool) has `hook_event_name`, `cwd`, `session_id`, `tool_name` and `tool_input`. ([Hook types, MCP tool hooks](https://kiro.dev/docs/hooks/types.md))

### Hook actions

- Two action types: an agent prompt (`"agent"`) and a shell command (`"command"`). A command gets the event as JSON on stdin and runs in the project root. ([Hook actions](https://kiro.dev/docs/hooks/actions.md), [Hooks](https://kiro.dev/docs/hooks.md))

### Can a command hook block a tool call, and with which exit code

- **Yes, with exit 2.** The Hook types page says that for Pre Tool Use, exit 0 allows the tool, exit 2 blocks it and sends stderr to the model, and any other code shows a warning and lets the tool run. The CLI tab of Hook actions says the same for exit 2 (it blocks `PreToolUse` and `PreTaskExec`) and that other codes warn and go ahead. ([Hook types, Pre Tool Use](https://kiro.dev/docs/hooks/types.md), [Hook actions](https://kiro.dev/docs/hooks/actions.md))
- **The pages do not agree about other exit codes.** The IDE tab of Hook actions says any exit code other than 0 blocks a Pre Tool Use call. The Hook types page and the CLI tab say only exit 2 blocks. The adapter will treat exit 2 as the only safe way to block, because it blocks in every version of the text.
- **No ask.** None of the three pages describes a JSON decision or an ask answer for Pre Tool Use; only exit codes. So for Kiro, Ask me first maps to deny plus one queue item of kind decision (tasks.md 9.6).
- **Nothing says what happens when the command cannot start.** The pages do not mention a setting like Claude Code's `onFailure`. Not documented, so the adapter must not count on it.

### Timeouts

- **The pages do not agree here either.** Hooks says `timeout` is in seconds, default 60, and `0` turns it off. The IDE tab of Hook actions also says 60 seconds. The CLI tab says the default is 30 seconds, set with `timeout_ms`. ([Hooks](https://kiro.dev/docs/hooks.md), [Hook actions](https://kiro.dev/docs/hooks/actions.md))
- The pages do not say whether a timeout blocks the tool call or lets it run.

### Stdout

- On exit 0, Kiro adds the command's stdout to the agent's context. So the adapter prints nothing on allow. ([Hook actions](https://kiro.dev/docs/hooks/actions.md))

### What this means for the adapter

| situation | what the adapter does | why |
| --- | --- | --- |
| umwayi says Yes | exit 0, nothing on stdout | exit 0 allows in every version of the text |
| umwayi says No | exit 2, reason on stderr | exit 2 blocks in every version of the text, and stderr reaches the model |
| umwayi says Ask me first | exit 2, reason on stderr, and one queue item of kind decision (`Kiro asks first: may it do TYPE?`, not added twice while open) | Kiro documents no ask and no JSON decision |
| the kill switch is on or unknown | exit 2 | decision 9.12 |
| anything goes wrong | exit 2 | the only code every page says blocks; exit 1 and other codes may let the call run |
| the hook cannot start or times out | **not covered**: no `onFailure` is documented. The README snippet sets `timeout: 60` and the adapter answers within about 15 seconds | not documented |

The script only ever exits 0 or 2.

### Not confirmed

- The field names inside `tool_input` for built-in tools (the JSON examples are empty in the Markdown copies). The adapter forwards every top level string field as `input_<key>`, see below, so rules on `input_command` or `input_path` only match if Kiro uses those names.
- What Kiro does when the hook command cannot start or times out.
- Which of `timeout` (seconds) and `timeout_ms` a given Kiro version reads.
- Which reading of "other exit codes" is right (the adapter avoids the question by never using one).
- Whether the Pre Tool Use input always carries `hook_event_name: "PreToolUse"`. It is in the one example shown, and the adapter blocks input without it.

## Generic stdin and stdout adapter

`adapters/stdio/hook.py` (tasks.md 9.7 to 9.9) is for any platform or script that can run a command before it acts. This is our own contract, not a platform's:

- Input on stdin: `{"tool_name": "...", "tool_input": {...}}`. Other fields are ignored, `platform` too.
- Output on stdout: one JSON line, `{"decision": "allow"|"deny"|"ask", "reason": "..."}`, plus `"queue"` when a queue item was added.
- Exit 0 allow, 2 deny, 3 ask. Never 1.
- `--platform NAME` (from the command line only, default `stdio`) names the platform in the action. `--no-ask` turns Ask me first into deny plus one queue item `The NAME platform asks first: may it do TYPE?`.
- On any error it still tries to print a deny line, writes the reason on stderr and exits 2. A caller must treat anything other than exit 0 with `"decision": "allow"` as a deny.

## The action JSON the adapters send

Two builders in `adapters/common/umwayi_gate.py`.

### Kiro and the generic adapter: `generic_action`

```json
{"type": "tool_execute_bash", "platform": "kiro", "tool": "execute_bash", "input_command": "npm test"}
```

| field | what it holds |
| --- | --- |
| `type` | `tool_` and the tool name, made the same way as below. Kiro MCP tools (`mcp_SERVER_TOOL`) become `tool_mcp_server_tool`; they are not collapsed to `tool_mcp` |
| `platform` | `kiro`, or the `--platform` name for the generic adapter |
| `tool` | the tool name, unchanged |
| `input_<key>` | every top level string field of `tool_input` whose key is a plain name (a letter, then letters, digits or `_`, up to 40). Other values (numbers, lists, objects) are not sent |

The `input_` prefix means a field in the tool input can never replace `type`, `platform` or `tool`. Unlike `tool_action`, this sends all string fields, file contents included, because the field names are not known. Nothing is cut, and the 64 KB limit of `umwayi check` still applies (bigger is denied). The logbook still gets only the type.

### Claude Code: `tool_action`

Used by `adapters/claude_code/` only, the same field list for every Claude Code tool.

```json
{"type": "tool_bash", "platform": "claude-code", "tool": "Bash", "command": "npm test", "permission_mode": "default"}
```

| field | what it holds |
| --- | --- |
| `type` | `tool_` and the tool name in lowercase with anything that is not a letter or digit made `_`: `tool_bash`, `tool_write`, `tool_read`, `tool_webfetch`. Every MCP tool is `tool_mcp`. A name longer than 35 characters is `tool_long_name`. An empty name is `tool_unknown` |
| `platform` | `claude-code` |
| `tool` | the platform's tool name, unchanged |
| `command` | Bash and PowerShell: the whole command |
| `path` | Write, Edit, MultiEdit, Read, NotebookEdit: the file path. Glob and Grep: the folder, if given |
| `pattern` | Glob and Grep: the pattern |
| `url` | WebFetch: the URL |
| `query` | WebSearch: the query |
| `subagent_type` | Agent: the subagent type |
| `mcp_server`, `mcp_tool` | MCP tools named `mcp__SERVER__TOOL` |
| `permission_mode`, `agent_type` | copied from the hook input when they are short plain words |

Rules:

- Only strings are copied, and only the fields above. File contents, edit text, prompts and other tool input are never sent.
- Nothing is cut. An action larger than `umwayi check` reads (64 KB) is refused by `umwayi check`, and the adapter denies it.
- `umwayi check` logs only the action type, never the action JSON, so a command with a secret in it does not reach the logbook.
- Example rules: `adapters/claude_code/rules.example.yaml`.

## The answer the adapters trust

`umwayi check - --json --kill-switch`, run as a child process with a timeout (default 10 seconds). It prints `answer`, `rule_id`, `rules_ok`, `action_ok` (tasks.md 9.2) and `kill_switch` (`off`, `on` or `unknown`).

The kill switch is checked twice (decision 9.12: every adapter denies everything while it is on):

1. In the core: with `--kill-switch`, `umwayi check` answers No while `.umwayi/KILL` is on or cannot be read, and the logbook entry says "The kill switch gave No". Plain `umwayi check`, without the flag, is not stopped: the owner's own commands still work.
2. In the adapter: `decide()` denies unless the child said `"kill_switch": "off"`. A missing field is a deny too.

| child | adapter |
| --- | --- |
| kill_switch not `off` | deny, before anything else |
| exit 0, answer Yes, rules_ok true | allow |
| exit 3, answer Ask me first, rules_ok true | ask (Claude Code), or deny and a queue item where the platform has no ask |
| exit 2, or answer No | deny |
| rules_ok false (rules.yaml missing or broken, or the action could not be read) | deny |
| any other exit code, a timeout, output that is not one JSON object, a child that cannot start | deny |
| an error inside the adapter | block (exit 2 on all three adapters) |

Where there is no ask, the queue item is added with `umwayi queue add --kind decision TITLE --recommendation TEXT --if-not-open` (5 second timeout). `--if-not-open` adds nothing while an open item of the same kind and the exact same title is in the queue. If the item cannot be added, the call is still denied and the reason says so.
