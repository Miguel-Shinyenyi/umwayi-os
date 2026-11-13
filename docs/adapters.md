# Adapters (layer 9)

## Purpose

The adapters let an AI platform (Claude Code, Kiro, OpenCode, or any tool that speaks JSON on stdin and stdout) ask umwayi before every tool call, and turn the answer into what that platform understands. They exist so an agent's own tool calls go through the owner's rules, the logbook and the kill switch.

## Current state

An adapter lets an AI platform ask umwayi before it acts. Each one sends every tool call through `umwayi check` (as a separate process) and turns the answer into what the platform understands. Any error blocks, and no adapter ever exits 1.

| adapter | Yes | No | Ask me first | set up |
| --- | --- | --- | --- | --- |
| Claude Code `PreToolUse` hook | allow | deny | ask | [adapters/claude_code/README.md](../adapters/claude_code/README.md) |
| Kiro Pre Tool Use hook | exit 0 | exit 2 | exit 2, and one queue item of kind decision (Kiro has no ask) | [adapters/kiro/README.md](../adapters/kiro/README.md) |
| generic stdin and stdout, for any other tool or script | exit 0, `{"decision": "allow"}` | exit 2, `deny` | exit 3, `ask` (or with `--no-ask` deny and a queue item) | [adapters/stdio/README.md](../adapters/stdio/README.md) |
| OpenCode 2.2.3 or newer, a plugin that runs the generic adapter with `--platform opencode` before every tool call | the call goes on | the call is stopped with a fixed message | the call goes on to OpenCode's permission request, which the rules answer and the owner confirms, but only for the nine tools OpenCode asks about; any other tool is stopped | [adapters/opencode/README.md](../adapters/opencode/README.md) |

- While the kill switch is on, or its state cannot be read, every adapter denies every tool call.
- The umwayi root is given with `--root`, never taken from the platform's input.
- This repo never creates or changes a `.claude` settings file or a `.kiro/hooks` file. Each README shows the snippet you add yourself.
- The adapters need no third party package. The OpenCode plugin (`adapters/opencode/plugin/index.js`) is plain JavaScript that imports only Node built-ins; umwayi never runs npm, Bun or an OpenCode plugin install for it.
- The OpenCode plugin is loaded only by `umwayi agent chat` for an agent with `platform: opencode`: umwayi names it in the inline config it passes (`OPENCODE_CONFIG_CONTENT`) and writes no OpenCode file. If OpenCode does not load it, no canary is written and the chat is refused (exit 2). The same plugin writes the canary that `umwayi agent chat` waits for ([agent front door](agent-front-door.md)).
- The repo `rules.yaml` has starter rules for what the Claude Code, Kiro, generic and OpenCode adapters send: reading is Yes, writing and shell commands are Ask me first, and wiping, pushing to main, the guard files and secret paths are No. OpenCode's Code Mode has no rule on purpose. See [rules](rules.md).
- What the Claude Code and Kiro docs say about hooks, with links, and what they do not say: [adapters/NOTES.md](../adapters/NOTES.md). Some Kiro details are not confirmed by its docs; they are listed in the Kiro README and in [docs/KNOWN-LIMITS.md](KNOWN-LIMITS.md).

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-12 | The OpenCode adapter is built (10.45 to 10.50): the plugin as the first gate, the permission request as the second, a canary before the first prompt; the real OpenCode is the owner's check (10.51) | Tasks 10.43 to 10.50, PR 47 to PR 74. |
| 2026-11-11 | The repo `rules.yaml` holds the 13 OpenCode starter rules too, taken from `adapters/opencode/rules.example.yaml`; Code Mode has no rule on purpose (see [rules](rules.md)) | The OpenCode starter rules pull request (PR 56), a follow-up of 9.10 and 10.45. |
| 2026-11-11 | 9.10 done: the repo `rules.yaml` holds the starter rules for the three adapters, taken from their example files (see [rules](rules.md)) | PR 43. |
| 2026-11-10 | 9.11 done: the whole-system test calls the three hooks as each platform runs them, and sends every agent start's tool calls through them | S.1, PR 36. |
| 2026-11-08 | Every adapter denies every tool call while the kill switch is on or unknown (9.12) | Layer 9, PR 12: the owner answered yes. |
| 2026-11-08 | Where a platform has no ask, Ask me first is a deny plus one queue item (9.6) | Layer 9, PR 12: Kiro has no ask. |
| 2026-11-08 | The Kiro adapter uses exit 0 or 2 only (9.4) | Layer 9, PR 12: the Kiro pages disagree about the other codes. |
| 2026-11-08 | No adapter ever exits 1; any error blocks (9.7) | Layer 9, PR 11: an error must never allow. |

## Open questions

None.
