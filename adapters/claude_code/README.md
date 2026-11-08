# Claude Code adapter (layer 9)

A Claude Code `PreToolUse` hook that asks `umwayi check` before every tool call and turns the answer into Claude Code's allow, deny or ask.

| umwayi says | Claude Code gets |
| --- | --- |
| Yes | `allow` |
| No | `deny` (Claude sees the reason) |
| Ask me first | `ask` (you see the reason in the permission prompt) |
| rules.yaml missing or broken | `deny` |
| the kill switch is on, or its state cannot be read | `deny` |
| a timeout, a crash, bad input, anything unexpected | blocked (exit 2, reason on stderr) |

The script never exits 1: on Claude Code exit 1 lets the tool call run. What Claude Code documents, with links: [../NOTES.md](../NOTES.md).

## Packages

None. The adapter is Python standard library only (Python 3.10 or newer), like the core `umwayi` package. It runs `umwayi check` as a separate process and does not import the `umwayi` package.

## Set up

1. Have an umwayi root: a folder with `rules.yaml` (and later `queue.md`, `LOGBOOK.md`). Start from `rules.example.yaml` in this folder: copy the rules you want into your `rules.yaml`.
2. Check the hook by hand:

   ```
   echo '{"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {"file_path": "/tmp/a"}}' \
     | python3 /path/to/umwayi-os/adapters/claude_code/hook.py --root /path/to/umwayi-root
   ```

3. Add the hook to a Claude Code settings file yourself (`~/.claude/settings.json` for all projects, or `.claude/settings.json` in one project). This repo does not change any settings file for you. Use absolute paths:

   ```json
   {
     "hooks": {
       "PreToolUse": [
         {
           "matcher": "*",
           "hooks": [
             {
               "type": "command",
               "command": "python3",
               "args": [
                 "/path/to/umwayi-os/adapters/claude_code/hook.py",
                 "--root",
                 "/path/to/umwayi-root"
               ],
               "timeout": 30,
               "onFailure": "block"
             }
           ]
         }
       ]
     }
   }
   ```

   - `"matcher": "*"` sends every tool call through umwayi.
   - `command` and `args` (exec form) start Python with no shell in between.
   - `"onFailure": "block"` matters: without it, Claude Code lets the tool call run when the hook cannot start (for example a wrong path) or times out. It needs Claude Code v2.1.295 or later.
   - `"timeout": 30` is longer than the adapter's own wait for `umwayi check` (10 seconds by default), so the adapter answers first and a slow check is denied, not left to Claude Code.

## Options

| option | meaning |
| --- | --- |
| `--root DIR` | required. The umwayi root with `rules.yaml`. Never taken from the hook input, because an agent can change its working folder |
| `--umwayi-src DIR` | the folder that holds the `umwayi` package. Default: the umwayi-os checkout this script is in |
| `--timeout SECONDS` | how long to wait for `umwayi check` (default 10). After that, deny |

## What is logged

Every tool call that reaches `umwayi check` adds one logbook entry with the action type (for example `tool_bash`) and the answer. The command, the path and the rest of the tool input are not written to the logbook.

## Limits

See [../../docs/KNOWN-LIMITS.md](../../docs/KNOWN-LIMITS.md). In short: rules match plain text, not shell syntax, so keep hard limits in Claude Code's own permission deny rules too; and a `Yes` from umwayi skips Claude Code's permission prompt (Claude Code's own deny and ask rules still apply).
