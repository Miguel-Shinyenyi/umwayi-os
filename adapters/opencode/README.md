# OpenCode adapter (layer 10, part 8)

For `umwayi agent chat NAME` with an agent of `platform: opencode`. OpenCode 2.2.3 or newer (the V2 line) is started over ACP (`opencode acp`) with the layer 9 gate in front of every tool call. There is no `agent run` and no `agent login` for OpenCode: both give exit 64. Built in tasks 10.43 to 10.50 and tested with a fake `opencode` that speaks ACP and runs the real hook. A real OpenCode has not been run by the build; that is the owner's check (task 10.51, `adapters/NOTES-layer10.md`, "The owner's real check of the OpenCode chat (10.51)").

## What you install

- OpenCode 2.2.3 or newer, yourself. umwayi never installs it and never runs npm, Bun or `opencode plugin add`. `opencode --version` must print a `N.N.N` that is at least 2.2.3 (on 2.2.7 the whole output is `opencode v2.2.7`).
- Sign in yourself if the route needs it: `opencode auth login`. umwayi never signs in for OpenCode. An `auth_required` answer ends the chat (exit 2) with "Run opencode auth login first, then try again."
- Nothing else. The plugin is `adapters/opencode/plugin/index.js` in this checkout: plain JavaScript that imports only Node built-ins, with no npm package. The gate checks refuse the chat if that folder holds any other file.

## agents.yaml

```yaml
agents:
  - name: oc-free
    platform: opencode
    command: opencode
    workdir: /home/me/projects/site
    provider: opencode
    model: opencode/big-pickle

  - name: oc-local
    platform: opencode
    command: opencode
    workdir: /home/me/projects/site
    provider: ollama
    model: ollama/qwen3-coder
```

- `command` is `opencode`, found on PATH. `transport` is `acp`, and it is the default for OpenCode (`cli` is refused).
- `provider` and `model` are required, and only for OpenCode. `model` is `PROVIDER/MODEL-ID` and its first part must equal `provider`. `agents.yaml` checks only this shape; whether the route is offered is decided at the start (exit 2).
- `workdir` is outside the umwayi root, as for every agent. The model names above are examples: use one your install lists.

## Routes

| `provider` | what pays | notes |
| --- | --- | --- |
| `opencode` | the signed-out free tier | `integration.use` allows the bare `opencode` only |
| `ollama`, `lmstudio`, `vllm` | your own machine | the inline config sets `settings.baseURL` to `http://127.0.0.1:11434/v1`, `:1234/v1` or `:8000/v1`; nothing else about the provider is written |
| `openai`, `github-copilot` | your ChatGPT or Copilot sign-in | `integration.use` allows only the connected-account form `openai#*` or `github-copilot#*`, never the bare name (an environment key) |

Refused with exit 2 and nothing started: `opencode-go` (its billing could not be told apart from Console credits), and every other provider (pay as you go is not offered; it waits for the budget governor). A route that passes the checks still has the limits in KNOWN-LIMITS 180, 182 and 187.

## What `umwayi agent check NAME` does

Six checks in order, the first failure ends it. It reads only and starts no OpenCode chat (it does run `opencode --version`).

1. `command`: `opencode` on PATH as an absolute path.
2. `version`: `opencode --version` answers within 15 seconds and its first `N.N.N` is at least 2.2.3.
3. `files`: the layer 9 hook (`adapters/stdio/hook.py`) and `plugin/index.js` are regular files inside the umwayi source tree with no link on the way, and the plugin folder holds `index.js` only.
4. `managed config`: none of `/etc/opencode`, `/Library/Application Support/opencode` or a macOS managed `ai.opencode.managed.plist` exists, because a managed config outranks the one umwayi passes.
5. `other config`: no `opencode.json`, `opencode.jsonc` or `.opencode` from the workdir up to `/` (the path as given, then the real path), none in your home folder, no `plugins`, `plugin`, `agents` or `agent` entry in the global OpenCode folder, and no global `opencode.json(c)` over 1 MiB or holding one of the quoted keys `permissions`, `permission`, `policies`, `plugins`, `plugin`, `agents`, `agent`, `experimental`, `enabled_providers`, `disabled_providers`. A refusal names the path and the key, never the text of a file.
6. `route`: the provider is one of the table above.

It then prints the argument list a chat would start (`["/path/to/opencode", "acp"]`) and exits 0. The same checks run again before every chat.

## What the chat does

1. The start steps of every chat: agents.yaml, the kill switch, the rules (the action holds `"platform": "opencode"`, `"mode": "chat"`), the run lock, the gate checks.
2. A private folder (mode 0700, outside the root and the workdir, in the temporary directory) and a fresh random token.
3. `opencode acp` in the workdir, in its own session, with an allow-listed environment and one generated variable, `OPENCODE_CONFIG_CONTENT`. No provider key and no other `OPENCODE_` name is passed, so `OPENCODE_CONFIG`, `OPENCODE_CONFIG_DIR`, `OPENCODE_DB`, `OPENCODE_API_KEY` and the like are dropped. `HOME` is passed through unchanged: umwayi does not give OpenCode a home folder of its own. OpenCode's stderr goes to your terminal.
4. `initialize` with no client capabilities, then `session/new`. The `model` option in the answer must equal your `model` exactly, or the chat ends (exit 2) before anything of yours is sent.
5. The canary: the plugin writes the token into the private folder when the session is created. Nothing you type is sent until that file holds exactly the token (at most 30 seconds). If it does not, the chat ends with exit 2 ("The first gate could not be confirmed in the ACP session. Nothing was sent.").
6. From there it is the ACP chat of Kiro and Claude Code (`:queue`, `:quit`, Ctrl-C). The folder is removed on every way out, and every stop ends the agent's process group and every descendant umwayi has seen.

## The two gates

- **The plugin, for every tool call.** Before a tool runs, the plugin runs the layer 9 generic adapter (`adapters/stdio/hook.py --root ROOT --platform opencode`) and sends `{"tool_name", "tool_input"}`. Yes lets the call go on. No stops it. Ask me first lets it go on to the permission request, but only for the nine tools OpenCode asks permission for (`read`, `glob`, `grep`, `write`, `edit`, `shell`, `webfetch`, `question`, `subagent`); for any other tool, Ask me first stops the call, because nobody would be asked. Anything else (another exit code, a timeout of 10 seconds, a bad answer) stops the call with a fixed message. The plugin also raises any permission `allow` to `ask`, so a lost `ask` rule does not remove the second gate.
- **The permission request.** The rules see `{"type": "acp_permission", "agent", "platform": "opencode", "kind", "tool"}` and never the title or the input. Yes allows once, No rejects once, Ask me first asks you `Allow once? [y/N]` and only `y` allows. umwayi never picks an `always` option. A request with no tool name never gets Yes: it asks you.

One tool call can write two `umwayi check` entries (the plugin's and the permission's). Nothing of the conversation, the token, the folder or the inline config is logged.

## Starter rules

`rules.example.yaml` in this folder has 13 rules, all `platform: opencode`. The same 13 are in the repo `rules.yaml`. Reading is Yes; writing, shell commands, the web and sub-agents are Ask me first; money, pushing to main, wiping commands, the guard files and secret paths are No. A No also covers any edit or shell command that names `opencode.json`, `.opencode`, `rules.yaml`, `LOGBOOK.md` or `.umwayi`, because OpenCode reloads a changed config during a chat (KNOWN-LIMITS 181). Code Mode (`tool_execute` and the `tool_opencode_*` tools inside it) has no rule on purpose, so it is Ask me first and the plugin stops it unless you write a Yes for it yourself (KNOWN-LIMITS 190). Without rules, every call is Ask me first.

## Packages and tests

No third party package. The plugin runs inside the `opencode` binary's own runtime; the tests run it under `node`.

- `tests/agents/fake_opencode.py` and `tests/agents/test_fake_opencode.py`: the fake and its tests.
- `tests/agents/test_agents_opencode_*.py`: the file, the config, the gate checks, the chat start, the turns and the planted faults.
- `tests/adapters/test_opencode_plugin.py`, `tests/adapters/test_opencode_rules.py`: the plugin and the rules.
- `tests/agents/opencode_mutants.py`: a helper that plants 153 faults in a copy of the source and reports which tests notice. It is run by a person, not by the suite or CI.

Known limits: [KNOWN-LIMITS](../../docs/KNOWN-LIMITS.md) 180 to 187, 190, 191, 242, 243, 248 and 250.
