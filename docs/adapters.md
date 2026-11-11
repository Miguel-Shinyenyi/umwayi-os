# Adapters (layer 9)

## Purpose

The adapters let an AI platform (Claude Code, Kiro, or any tool that speaks JSON on stdin and stdout) ask umwayi before every tool call, and turn the answer into what that platform understands. They exist so an agent's own tool calls go through the owner's rules, the logbook and the kill switch.

## Current state

An adapter lets an AI platform ask umwayi before it acts. Each one sends every tool call through `umwayi check` (as a separate process) and turns the answer into what the platform understands. Any error blocks, and no adapter ever exits 1.

| adapter | Yes | No | Ask me first | set up |
| --- | --- | --- | --- | --- |
| Claude Code `PreToolUse` hook | allow | deny | ask | [adapters/claude_code/README.md](../adapters/claude_code/README.md) |
| Kiro Pre Tool Use hook | exit 0 | exit 2 | exit 2, and one queue item of kind decision (Kiro has no ask) | [adapters/kiro/README.md](../adapters/kiro/README.md) |
| generic stdin and stdout, for any other tool or script | exit 0, `{"decision": "allow"}` | exit 2, `deny` | exit 3, `ask` (or with `--no-ask` deny and a queue item) | [adapters/stdio/README.md](../adapters/stdio/README.md) |

- While the kill switch is on, or its state cannot be read, every adapter denies every tool call.
- The umwayi root is given with `--root`, never taken from the platform's input.
- This repo never creates or changes a `.claude` settings file or a `.kiro/hooks` file. Each README shows the snippet you add yourself.
- The adapters need no third party package.
- The repo `rules.yaml` has starter rules for what the three adapters send: reading is Yes, writing and shell commands are Ask me first, and wiping, pushing to main, the guard files and secret paths are No. See [rules](rules.md).
- What the Claude Code and Kiro docs say about hooks, with links, and what they do not say: [adapters/NOTES.md](../adapters/NOTES.md). Some Kiro details are not confirmed by its docs; they are listed in the Kiro README and in [docs/KNOWN-LIMITS.md](KNOWN-LIMITS.md).

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-11 | 9.10 done: the repo `rules.yaml` holds the starter rules for the three adapters, taken from their example files (see [rules](rules.md)) | PR NN. |
| 2026-11-10 | 9.11 done: the whole-system test calls the three hooks as each platform runs them, and sends every agent start's tool calls through them | S.1, PR 36. |
| 2026-11-08 | Every adapter denies every tool call while the kill switch is on or unknown (9.12) | Layer 9, PR 12: the owner answered yes. |
| 2026-11-08 | Where a platform has no ask, Ask me first is a deny plus one queue item (9.6) | Layer 9, PR 12: Kiro has no ask. |
| 2026-11-08 | The Kiro adapter uses exit 0 or 2 only (9.4) | Layer 9, PR 12: the Kiro pages disagree about the other codes. |
| 2026-11-08 | No adapter ever exits 1; any error blocks (9.7) | Layer 9, PR 11: an error must never allow. |

## Open questions

None.
