# Kiro adapter (layer 9)

A Kiro Pre Tool Use hook (a shell command action) that asks `umwayi check` before every tool call. Kiro documents no JSON decision for Pre Tool Use, so the answer is the exit code only.

| umwayi says | the hook does | Kiro does (per its docs) |
| --- | --- | --- |
| Yes | exit 0, nothing on stdout | runs the tool |
| No | exit 2, the reason on stderr | blocks the tool, and the agent sees the reason |
| Ask me first | exit 2, the reason on stderr, and one queue item of kind decision for you | blocks the tool. Kiro has no ask, so the owner answers in the umwayi queue |
| the kill switch is on, or its state cannot be read | exit 2 | blocks the tool |
| rules.yaml missing or broken | exit 2 | blocks the tool |
| a timeout, a crash, bad input, anything unexpected | exit 2 | blocks the tool |

The hook only ever exits 0 or 2. Exit 2 is the one code that every version of the Kiro text says blocks a Pre Tool Use call. The Kiro pages disagree about other exit codes, so the hook never uses them. What the Kiro docs say, with links, and what they do not say: [../NOTES.md](../NOTES.md).

The queue item is added once: while an open decision with the same title is in the queue (`Kiro asks first: may it do TYPE?`), no second one is added. Answering it does not allow the call; to allow calls like it, add a Yes rule in `rules.yaml`.

## Packages

None. Python standard library only (Python 3.10 or newer). The hook runs `umwayi` as a separate process and does not import it.

## Set up

1. Have an umwayi root with a `rules.yaml`. Start from `rules.example.yaml` in this folder. **Read its header first**: the Kiro docs do not name the fields inside `tool_input`, so the adapter sends every top level string field as `input_<name>`, and the rules that use `input_command` or `input_path` only work if Kiro uses those names.
2. Check the hook by hand:

   ```
   echo '{"hook_event_name": "PreToolUse", "tool_name": "read_file", "tool_input": {"path": "/tmp/a"}}' \
     | python3 /path/to/umwayi-os/adapters/kiro/hook.py --root /path/to/umwayi-root; echo "exit $?"
   ```

3. Add a hook file yourself, for example `.kiro/hooks/umwayi-check.json` in a project, or in `~/.kiro/hooks/` for Kiro CLI V3 (global). This repo does not create or change any hook file for you. Use absolute paths without spaces (the command is run by a shell):

   ```json
   {
     "version": "v1",
     "hooks": [
       {
         "name": "umwayi check before every tool",
         "description": "Asks umwayi-os before every tool call. Exit 2 blocks the call.",
         "trigger": "PreToolUse",
         "action": {
           "type": "command",
           "command": "python3 /path/to/umwayi-os/adapters/kiro/hook.py --root /path/to/umwayi-root"
         },
         "timeout": 60
       }
     ]
   }
   ```

   - No `matcher`: the hook runs for every tool.
   - `timeout` is in seconds in the Kiro hook file schema. The CLI tab of the Kiro Hook actions page also mentions `timeout_ms` with a 30 second default. Not confirmed which one a given Kiro version reads; the adapter's own wait for `umwayi check` (10 seconds, plus up to 5 seconds for the queue item) stays under both.

## Not confirmed by the Kiro docs

- The names of the fields inside `tool_input` for built-in tools.
- What Kiro does when the hook command cannot start, or when it times out. The docs do not say whether the tool call is blocked. Unlike Claude Code, no `onFailure` setting is documented. If Python or the script is missing, the call may go ahead.
- Whether every Kiro surface treats an exit code other than 0 or 2 the same way (the pages disagree; the hook never uses one).

## Options

| option | meaning |
| --- | --- |
| `--root DIR` | required. The umwayi root with `rules.yaml`. Never taken from the hook input |
| `--umwayi-src DIR` | the folder that holds the `umwayi` package. Default: the umwayi-os checkout this script is in |
| `--timeout SECONDS` | how long to wait for `umwayi check` (default 10). After that, deny |
