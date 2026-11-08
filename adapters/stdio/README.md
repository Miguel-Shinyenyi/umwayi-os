# Generic stdin and stdout adapter (layer 9)

For any platform or script that can run a command before it acts and read its answer. One JSON object in, one JSON object out, and the exit code says the same.

```
echo '{"tool_name": "deploy", "tool_input": {"target": "staging"}}' \
  | python3 /path/to/umwayi-os/adapters/stdio/hook.py --root /path/to/umwayi-root --platform mytool
```

| umwayi says | stdout | exit |
| --- | --- | --- |
| Yes | `{"decision": "allow", "reason": "..."}` | 0 |
| No | `{"decision": "deny", "reason": "..."}` | 2 |
| Ask me first | `{"decision": "ask", "reason": "..."}` | 3 |
| Ask me first, with `--no-ask` | `{"decision": "deny", "reason": "...", "queue": "Added Q-0001 ..."}` and one queue item of kind decision for the owner (not a second one while it is open) | 2 |
| the kill switch is on or unknown, rules.yaml broken, a timeout, bad input, a crash | `{"decision": "deny", "reason": "..."}` (when it can still be written), the reason on stderr | 2 |

It never exits 1. Treat anything other than exit 0 with `"decision": "allow"` as a deny in your own code.

## Input

```json
{"tool_name": "deploy", "tool_input": {"target": "staging"}}
```

The action sent to `umwayi check` is `{"type": "tool_deploy", "platform": "mytool", "tool": "deploy", "input_target": "staging"}`: the type is `tool_` and the tool name, and every top level string field of `tool_input` with a plain key becomes `input_<key>`. A `platform` field in the input is ignored.

## Options

| option | meaning |
| --- | --- |
| `--root DIR` | required. The umwayi root with `rules.yaml`. Never taken from the input |
| `--platform NAME` | the platform name in the action (default `stdio`), lowercase letters, digits and `-`. Set by you, never by the input, so a caller cannot claim to be another platform |
| `--no-ask` | for a platform that cannot ask the user: Ask me first becomes a deny plus a queue item |
| `--umwayi-src DIR` | the folder that holds the `umwayi` package. Default: the umwayi-os checkout this script is in |
| `--timeout SECONDS` | how long to wait for `umwayi check` (default 10). After that, deny |

## Packages

None. Python standard library only (Python 3.10 or newer). Example rules: `rules.example.yaml` in this folder.
