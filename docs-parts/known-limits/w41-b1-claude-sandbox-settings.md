section: Enforced by default (W78), found while building W41 B1
title: the Claude Code sandbox settings are passed and the tools are looked for, but nothing tests that the sandbox holds
number: 334

These are facts of the code of this change. No real Claude Code ran with the sandbox on.

- A start under a mode file that says `enforced` passes `{"enabled": true, "failIfUnavailable": true, "allowUnsandboxedCommands": false}` with `--settings`. A cooperative agent and a root with no mode file are unchanged.
- umwayi reads back the settings text it would pass and looks for `bwrap` and `socat` on PATH (Linux). It does not run them, so a tool that is on PATH and broken, or an Ubuntu AppArmor rule that blocks `bwrap`, shows up only when Claude Code itself refuses to start (`failIfUnavailable`).
- A managed setting of Claude Code, which beats `--settings`, can change the sandbox. umwayi does not read managed settings.
- The sandbox covers the shell commands Claude Code runs and what they start. The built-in Read, Edit and Write tools, hooks and MCP servers stay outside it (Claude Code's own docs). The write access of the sandbox is Claude Code's default (the working folder); umwayi sets no `filesystem` keys.
- The Claude Code ACP adapter takes no `--settings`, so an `enforced` ACP agent is refused with reason `profile`. The owner sets that agent cooperative, or uses transport cli.
- `umwayi enforce check` still reports confinement as refused for Claude Code: the sandbox is one of the parts of confinement, not all of it.
- Kiro and OpenCode have no such sandbox. They need B2.
