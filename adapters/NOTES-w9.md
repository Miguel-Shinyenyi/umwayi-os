# W9 notes: goal orchestration (`umwayi goal`)

Facts read on Nov 12 2026 for the spec in the W9.0 pull request (requirements W9.R1 to W9.R23, design.md "Goal orchestration (W9)"). Nothing here is built and none of it was tried on a real install: every flag below comes from the vendor's documentation, in my own words. The by-hand check of W9.11 goes at the end of this file, with the date and the versions.

## Model and effort on the command line (why `agent run` gets `--model` and `--effort`, W9.6)

- **Claude Code.** The CLI reference lists `--model` (an alias such as `sonnet`, `opus` or `haiku`, or a full model name) and `--effort` with the levels `low`, `medium`, `high`, `xhigh`, `max` and `ultracode`. `ultracode` needs a recent version (v2.1.203 or later, as the page says) and is not used by W9: the spec allows the first five only. `--print` (`-p`) is the print mode that `umwayi agent run` uses today. ([Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference))
- **Kiro.** `kiro-cli chat` takes `--model MODEL` (it overrides the agent's model and the saved default), `--effort LEVEL` (`low`, `medium`, `high`, `xhigh`, `max`) and `--no-interactive`, which `umwayi agent run` already uses. `--list-models` prints the models. On `kiro-cli acp` the same two flags are marked V2 only, and umwayi starts the V3 server, so W9 does not use them for a Kiro chat over ACP. ([Kiro CLI commands](https://kiro.dev/docs/reference/cli-commands/))
- **OpenCode.** The commands page shows `opencode run --model provider/model "prompt"` ([OpenCode CLI commands](https://opencode.ai/docs/cli/commands/); read as a search summary only, the page was not fetched). umwayi does not run `opencode run` today: an OpenCode agent is refused for `agent run`, and its chat is task 10.48. No documented effort flag for OpenCode was found, so W9 refuses an effort for an OpenCode agent until one is confirmed on a real install (W9-Q8).

## What this means for the spec

- A model is a word that the platform accepts or refuses. umwayi checks its shape (`^[A-Za-z0-9._:/-]{1,64}$`) and nothing else, and does not know whether the platform honors it (KNOWN-LIMITS 223).
- Both platforms accept the five effort levels `low`, `medium`, `high`, `xhigh` and `max` on the command line. The levels a given model supports can differ ("available levels depend on the model", Claude Code CLI reference). A refusal by the platform shows as the agent's own non-zero exit, and the task fails with the reason `builder`.

## What was not looked at

- Whether `--effort` works together with `-p` on every Claude Code version, and the exit code each platform gives for an unknown model or an unsupported effort level.
- Any OpenCode flag beyond `--model`.
- The by-hand results of W9.11 go here.
