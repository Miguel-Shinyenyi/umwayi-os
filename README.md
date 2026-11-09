# umwayi-os

An AI operating system for one person and their AI helpers.

It keeps memory, enforces rules before an AI helper acts, tracks a queue of tasks and decisions, archives moved text with a fingerprint, and writes a logbook of every change. It is built in layers, and each layer works alone and is tested before the next starts.

Status: all eight layers are built: memory, rules, queue, archive, logbook, automation, helpers and workflows. Layer 9 (adapters for Claude Code, Kiro and any stdin and stdout tool) is built, see [Layer 9](#layer-9-adapters). Layer 10 (one front door for agents) is in progress: agents.yaml, the gate checks, `umwayi agent run` and `umwayi agent chat` (on your terminal, or over ACP for Kiro) for Claude Code and Kiro are built; for Claude Code over ACP (part 7, approved) the pinned adapter package, its gate checks (part 7a) and the chat (part 7b) are built, see [Layer 10](#layer-10-front-door-for-agents-in-progress). Known limits are listed in [docs/KNOWN-LIMITS.md](docs/KNOWN-LIMITS.md). See `.kiro/specs/umwayi-os/` for requirements, design and tasks, and `.kiro/steering/product.md` for the product rules.

## Install and test

Python 3.10 or newer, no third party packages.

```
pip install -e .          # optional, gives the `umwayi` command
python -m unittest discover -s tests -t .
```

Without installing, use `python -m umwayi` from the repo root.

## Exit codes

Every command uses the same codes:

| code | meaning |
| --- | --- |
| 0 | Yes, or done |
| 1 | refused: something was checked and found wrong, nothing was changed |
| 2 | No, or an unexpected error (a crash is treated like No, never like Yes) |
| 3 | Ask me first |
| 64 | usage or config error: wrong arguments, a value that is not allowed, or a missing or invalid `umwayi.json`, jobs file or workflow file |

A missing or broken `rules.yaml` is not a config error: it gives Ask me first.

## Layer 1: memory

```
umwayi.json                     config: memory_dir and private_paths
memory/master.md                master context
memory/projects/*.md            one file per project
memory/journal/*.md             journal
```

```
umwayi memory bundle [--format text|json]
```

Prints one context bundle for an AI helper. Anything under a path listed in `private_paths` (a file, a folder or a glob) is left out, and its name is never printed. Only a count is shown.

## Layer 2: rules

Rules live in `rules.yaml`. Each rule has an id, a title, text, a verdict (`yes`, `no` or `ask`), and optionally a cause and matchers.

```
umwayi check '{"type": "payment", "amount": 5}'
```

Prints the answer, the rule id and the reason:

```
No
Rule: no-money
Reason: AI helpers never move money or use bank or card credentials. Cause: Safety rule for all AI helpers.
```

| answer | exit code |
| --- | --- |
| Yes | 0 |
| No | 2 |
| Ask me first | 3 |

Fail closed: no matching rule, a broken or missing `rules.yaml`, or bad action JSON all give Ask me first. If several rules match, No beats Ask me first, and Ask me first beats Yes. Usage errors exit with 64.

Matchers (all must match):

- `type: payment` equals, ignoring case
- `type: [payment, transfer]` equals any
- `path__contains: secret` contains text
- `amount__exists: true` field is present

Use `--rules PATH` for another rules file, `--json` for JSON output, and `-` as the action to read it from standard input. `--kill-switch` answers No while the kill switch is on or its state is unknown (the adapters use it; without it your own checks are not stopped).

Every check writes one logbook entry with the rule id and the answer. The action JSON is never written, only its `type` if that is a short plain word. If the logbook cannot be written (for example it was edited by hand), a No stays No (exit 2), a Yes becomes Ask me first (exit 3), and the reason says why. Use `--no-log` for a dry run that writes nothing, and `--date` to set the entry date.

## Layer 3: queue

`queue.md` is a Markdown table you can read and edit by hand. The columns are id, kind (task or decision), title, status (open, answered, closed), recommendation, answer, and the date answered.

```
umwayi queue list [--status open|answered|closed] [--kind task|decision]
umwayi queue add --kind task "Write the spec" [--recommendation "Do it today"] [--date 2026-11-07]
umwayi queue answer Q-0001 --answer "Yes, go ahead" [--date 2026-11-07]
umwayi queue close Q-0001 [--date 2026-11-07]
umwayi queue migrate [--date 2026-11-07]
```

- `answer` needs `--answer` (one line, no `|`, up to 500 characters, the same limits as a recommendation). It works only on an open row. An open row has an empty answer, an answered row has an answer and the date answered.
- `add --if-not-open` adds nothing if an open row of the same kind with exactly the same title exists, and prints `Already open, nothing added: Q-...` (the adapters use it, so a repeated Ask me first does not fill the queue).
- `close` works on an open or answered row and keeps its answer and date.
- Ids are never reused. `add` uses one more than the highest id found in `queue.md` and in the logbook, even if you delete a row by hand. If `LOGBOOK.md` exists but cannot be read, `add` refuses and says why.
- A queue.md in the old six column layout (no answer column) is refused with a message. Run `umwayi queue migrate` once to convert it. Old answered rows get the text `not recorded before migration`.
- Without `--date` the system clock is used. A malformed `queue.md` is an error with a line number, and nothing is changed. Only the row a command touches is rewritten.
- Every change appends an entry to `LOGBOOK.md` (date, source, added, checked, not done). Earlier logbook lines are never edited. The logbook records the length of an answer, not its text.

## Layer 4: archive

Moves a block of text out of a file into its own file under `archive/`, with a fingerprint, and leaves a pointer line behind.

```
umwayi archive move notes.md --lines 10-20 --reason "old plan" [--date 2026-11-07]
umwayi archive move notes.md --start "<!-- start -->" --end "<!-- end -->" --reason "old plan"
umwayi archive verify
```

- `archive/INDEX.md` is a Markdown table: id, source, moved, reason, words, sha256. `archive/A-0001.txt` holds the exact bytes of the block.
- The source gets one line in place of the block: `[archived A-0001: archive/A-0001.txt]`.
- Line ranges count from 1 and include both ends. Markers must each match one whole line, appear exactly once, and are part of the block.
- `move` refuses and changes nothing if the source is missing, a symbolic link, a private path in `umwayi.json`, or a protected file (logbook, queue, rules, config, archive, git data); if the range is empty or outside the file; if the markers are missing, repeated or in the wrong order; if the block has no words; or if the reason is empty.
- Ids look like A-0001 and are never reused: one more than the highest id in the index and in the logbook. If `LOGBOOK.md` exists but cannot be read, `move` refuses.
- The source, the archive file and the index all change or none do. If the logbook write fails, the move is undone. Each move adds one logbook entry.
- `verify` recomputes every SHA-256 and prints `ok`, `changed`, `missing` or `not in the index` for each id. It exits 0 only when all are ok, otherwise 1, and never changes a file.
- `umwayi archive restore` is not built yet. The output of `move` names it.

## Layer 5: logbook

`LOGBOOK.md` is append only. Every umwayi command that changes something adds one entry:

```
## 2026-11-07

- Source: umwayi queue add
- Added: ...
- Checked: ...
- Not done: ...
```

```
umwayi logbook verify
umwayi logbook seal --by "Your name" [--date 2026-11-07]
```

- After every write the SHA-256 of the whole file is recorded in `.umwayi/logbook.sha256`. Before every write it is checked. If you edit, delete or add a line by hand, every umwayi write is refused (and `umwayi check` answers Ask me first) until you look at the file and run `umwayi logbook seal`.
- An existing logbook with no record is refused the same way. Nothing is sealed automatically.
- `verify` prints `ok` or each problem with a line number (never the line text) and exits 0 only when the format is valid and the hash matches. It never changes a file.
- Entry dates must be real and never go backwards.
- `.umwayi/logbook.lock` stops two commands from writing at once. If a command was killed and left the lock behind, delete the file.

## Layer 6: automation

### Jobs

```
umwayi run jobs.yaml --job weekly-report [--date 2026-11-07]
```

`jobs.yaml` lists jobs. Each has a `name`, a `command` from a fixed list (`report`, `check`, `queue-list`) and `min_gap_days`. There is no way to put a shell command or another program in a job.

- The rules are asked first (action type `run_job`). No stops the job (exit 2), Ask me first stops it (exit 3).
- A job that ran fewer than `min_gap_days` days ago is refused (exit 1).
- Every run writes one logbook entry. If the logbook cannot be written, the job does not run.
- `--job` is needed when the file has more than one job.

umwayi does not install a schedule. To run the weekly report every Monday at 08:00, the owner could add a line like this with `crontab -e` (adjust the paths):

```
0 8 * * 1  cd /path/to/umwayi-os && umwayi run jobs.yaml --job weekly-report >> drafts/cron.log 2>&1
```

### Progress report

```
umwayi report --since 2026-11-01 [--date 2026-11-07]
```

Writes `drafts/report-0001.md` (then `-0002`, and so on, never overwriting) with commits per day and their subjects, from the local git history. It reads git through one fixed `git log` command: no network, no author names or emails, nothing written to git. Merge commits are not counted.

### Publish a draft

```
umwayi publish-draft drafts/report-0001.md --approved-by "Your name"
```

Copies the draft to `outbox/report-0001.txt` so you can post it by hand. It never posts, pushes, sends or runs git. The starter rule `publish-ask` makes publishing Ask me first, so without `--approved-by` it stops with exit 3. A rule that says No stops it even with approval. An existing outbox file is never overwritten.

`drafts/` and `outbox/` are in `.gitignore`.

## Layer 7: AI helpers

AI helpers draft only. Every step an AI helper wants to take goes through the rules first, the same check as `umwayi check`:

- No stops the AI helper (exit 2).
- Ask me first stops it (exit 3) and adds a queue item of kind decision for you. Answering it is your record; it does not let the AI helper go on. To allow the action, add a Yes rule in rules.yaml.
- Only Yes continues.
- Every step adds one logbook entry. If rules.yaml is missing or broken, no AI helper runs (exit 3). If the logbook fails its tamper check, no AI helper runs (exit 1).
- An AI helper can never approve anything. The helper commands have no `--approved-by` option.
- AI helpers write files only under `drafts/` (plus their logbook entries, and the queue item when they stop on Ask me first).

### Steward

```
umwayi steward [--waiting-days 7] [--date 2026-11-07]
```

Reads `queue.md` and the logbook, and writes `drafts/steward-0001.md`: open items, items waiting longer than the given number of days, answered items not closed yet, and suggested next tasks. It never changes the queue and never answers an item.

### Social helper

```
umwayi social draft articles/week-45.md [--date 2026-11-07]
```

The article starts with front matter:

```
---
title: What I learned this week
link: https://example.org/what-i-learned
summary: One line about it (optional)
---
```

It writes one draft per channel listed in `umwayi.json`, for example `"social_channels": ["linkedin", "mastodon"]`, as `drafts/post-linkedin-0001.md`. Each post comes from one fixed template: the title, the summary (or the first paragraph), and `Read more: LINK`. Posts are at most 280 characters, plain text, with no hashtags and no em dashes. There is no model call and no network. It never posts. To publish a draft, run `umwayi publish-draft drafts/post-linkedin-0001.md`, which is Ask me first.

## Layer 8: workflows

A workflow is a file `workflows/NAME.yaml` with a name and steps in order. Each step is one command from a fixed list inside umwayi, with its arguments written in the file:

| command | arguments |
| --- | --- |
| `queue-list` | `status` (optional) |
| `steward` | `waiting_days` (optional, default 7) |
| `social-draft` | `article` (a local article file) |
| `report` | `since_days` |
| `check` | `action_type` |
| `approve` | none, and only as the last step |

There is no way to put a shell command, another program or an approval in a workflow.

```
umwayi workflow validate content-loop
umwayi workflow run content-loop [--date 2026-11-07]
```

- `validate` prints every problem with its line number and exits 64, or `ok` and exits 0.
- `run` asks the rules for every step (action type `workflow_step`). No stops it (exit 2), Ask me first stops it (exit 3). Every step adds one logbook entry. If the logbook cannot be written, the run stops.
- The shipped content loop (`workflows/content-loop.yaml`) runs collect (`queue-list`), brief (`steward`), draft (`social-draft` from `articles/example.md`) and approve.
- The approve step never approves anything. It adds a queue item of kind decision that lists the drafts, and stops the workflow with exit 3. The workflow will not run again until you answer or close that item. To publish a draft, you run `umwayi publish-draft DRAFT`, which is Ask me first.
- Workflows write only under `drafts/`, plus the queue and the logbook.

### Kill switch

```
umwayi kill on [--reason "taking a break"]
umwayi kill status
umwayi kill off
```

While the switch is on (the file `.umwayi/KILL` exists), every AI helper, job and workflow stops before doing anything, with exit 3 (Ask me first) and one logbook entry. If umwayi cannot tell whether the switch is on (for example `.umwayi` is not a normal folder), it stops too. `kill on` works even when the logbook is broken. `kill off` keeps the switch on if the logbook cannot record it. Your own commands (queue, archive, check, report, publish-draft) are not stopped. The layer 9 adapters are: they deny every tool call while the switch is on.

### One run at a time

AI helpers, jobs and workflows share one lock, `.umwayi/run.lock`. If one is running and you start another, the second one does not wait: it answers Ask me first (exit 3), writes one logbook entry, and changes nothing. If locking is not available on your system, they all answer Ask me first. Your own commands (queue, check, archive, report, publish-draft) are not locked.

## Layer 9: adapters

An adapter lets an AI platform ask umwayi before it acts. Each one sends every tool call through `umwayi check` (as a separate process) and turns the answer into what the platform understands. Any error blocks, and no adapter ever exits 1.

| adapter | Yes | No | Ask me first | set up |
| --- | --- | --- | --- | --- |
| Claude Code `PreToolUse` hook | allow | deny | ask | [adapters/claude_code/README.md](adapters/claude_code/README.md) |
| Kiro Pre Tool Use hook | exit 0 | exit 2 | exit 2, and one queue item of kind decision (Kiro has no ask) | [adapters/kiro/README.md](adapters/kiro/README.md) |
| generic stdin and stdout, for any other tool or script | exit 0, `{"decision": "allow"}` | exit 2, `deny` | exit 3, `ask` (or with `--no-ask` deny and a queue item) | [adapters/stdio/README.md](adapters/stdio/README.md) |

- While the kill switch is on, or its state cannot be read, every adapter denies every tool call.
- The umwayi root is given with `--root`, never taken from the platform's input.
- This repo never creates or changes a `.claude` settings file or a `.kiro/hooks` file. Each README shows the snippet you add yourself.
- The adapters need no third party package.
- What the Claude Code and Kiro docs say about hooks, with links, and what they do not say: [adapters/NOTES.md](adapters/NOTES.md). Some Kiro details are not confirmed by its docs; they are listed in the Kiro README and in [docs/KNOWN-LIMITS.md](docs/KNOWN-LIMITS.md).

## Layer 10: front door for agents (in progress)

One front door starts every AI agent (Claude Code, Kiro) through its own command line, with the layer 9 hook in front of every tool call, and refuses an agent it cannot gate. Built: the agents file, the gate checks, `umwayi agent run` and `umwayi agent chat` for Claude Code and Kiro, with transport cli (your terminal) or, for Kiro, transport acp (umwayi's own ACP client). For Claude Code with transport acp (parts 7a and 7b), `umwayi agent chat` runs the pinned adapter `claude-agent-acp` with umwayi's own ACP client, and goes on only after the layer 9 hook is confirmed in the session.

```
umwayi agent validate [--agents PATH]      check agents.yaml, every problem with a line number
umwayi agent list [--agents PATH]          the agents in the file
umwayi agent check NAME [--agents PATH]    can NAME be gated? runs every gate check, starts no agent
umwayi agent run NAME --prompt TEXT        start NAME once (Claude Code or Kiro); or --prompt-file PATH, or - for stdin
umwayi agent chat NAME                     a chat with NAME on your terminal (transport cli), or over ACP (Kiro or Claude Code, transport acp)
```

With `transport: acp` (Kiro only), `umwayi agent chat` takes the same steps and then talks to `kiro-cli acp --agent-engine=v3` itself, with a small client in `umwayi/acp.py`. It offers the agent no file and no terminal access. Each line you type is one prompt; `:queue` shows the queue and `:quit` ends the chat. Agent text is printed with control, bidirectional and zero-width characters made visible. When Kiro asks permission for a tool, the rules answer (`{"type": "acp_permission", "kind": ..., "tool": ...}`, never the title): Yes allows once, No rejects once, Ask me first asks you `Allow once? [y/N]` and only `y` allows. umwayi never picks an "always" option. Ctrl-C cancels the turn and answers open permission requests with cancelled; it does not stop umwayi. The kill switch cancels, closes the connection and stops Kiro (exit 3). Any other request from Kiro (files, terminals) is refused, and a broken line or a dropped connection ends the chat (exit 2).

Claude Code over ACP (parts 7a and 7b, approved Nov 8). A Claude Code agent may have `transport: acp`; `command` stays `claude`, which `umwayi agent run` still uses (`claude -p`). The ACP chat runs the pinned adapter [`@agentclientprotocol/claude-agent-acp`](adapters/claude_acp/README.md) 0.101.0 as `[node, adapters/claude_acp/node_modules/@agentclientprotocol/claude-agent-acp/dist/index.js]`, with no shell and no npx. You install it yourself, once, with `npm ci --ignore-scripts` in `adapters/claude_acp/` (Node.js 22 or later); umwayi never runs npm. Sign in to Claude Code first (`claude`, then `/login`); umwayi never takes an API key. `umwayi agent check NAME` then runs, in order: `node` on PATH; `node --version` at least 22; the adapter file (a regular file, not a link); its `package.json` has exactly the pinned name and version; `--version` prints exactly `0.101.0`; `--cli --version` prints Claude Code 2.1.295 or later; `--cli auth status --json` shows a Claude subscription login within 15 seconds (part 7c-1, below; only five fields are read); the layer 9 hook and its self-test. Each program gets only an allow-listed environment (`HOME`, `PATH`, the locale, the XDG folders, `CLAUDE_CONFIG_DIR`, proxy and certificate settings) plus `CLAUDE_AGENT_ACP_PROTOCOL=v1`; `ANTHROPIC_*`, `CLAUDE_CODE_EXECUTABLE`, `NODE_OPTIONS` and everything else are dropped. `umwayi agent chat NAME` takes the same start steps as every start (the rules see `"platform": "claude-code", "mode": "chat", "transport": "acp"`), runs every check again, then starts the adapter in its own session with that environment. For every start umwayi makes a private folder (mode 0700, outside the root and the workdir) and a fresh random token, and `session/new` carries `_meta.claudeCode.options`: `allowDangerouslySkipPermissions: false` and inline settings with the same PreToolUse hook `agent run` passes, plus a SessionStart canary hook (`adapters/claude_acp/canary.py`) that creates the file named by the token. Nothing you type is sent until that file exists; if it does not within 30 seconds, the chat ends with exit 2 ("The first gate could not be confirmed in the ACP session. Nothing was sent."). Then umwayi sets the permission mode to `default` (an error answer ends the chat with exit 2) and the chat goes on as for Kiro: the rules answer every permission request (`"platform": "claude-code"`), never with an always option. Every stop closes the adapter's stdin, then sends SIGTERM to its process group and to every descendant umwayi has seen in `/proc`, SIGKILL after 10 seconds; the folder is removed on every way out. Not yet confirmed with a real adapter: that the canary runs at `session/new` (KNOWN-LIMITS 65).

Subscription first for Claude Code (part 7c-1, approved Nov 9). Before every Claude Code start (`agent run`, the terminal chat and the ACP chat), umwayi runs `claude auth status --json` (for ACP, the adapter's bundled `--cli auth status --json`) in the agent's folder with the environment the agent will get, and starts the agent only when a Claude subscription login (claude.ai: Pro, Max, Ultra, Team or Enterprise) is what pays: `loggedIn` true, `authMethod` `claude.ai`, no `apiKeySource`, `apiProvider` absent or `firstParty`, and a plan word. An API key, an auth token, an `apiKeyHelper` in a settings file, `CLAUDE_CODE_OAUTH_TOKEN`, a Console login, a cloud provider, no login, or an answer umwayi cannot read is refused with exit 2 and one line that names the fix. Only those fields are read: your email and organisation in the same output are never shown, logged or kept; `umwayi agent check` shows `ok: login: Claude subscription (plan: max)`. `agent run` and the terminal chat no longer get `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `CLAUDE_CODE_OAUTH_TOKEN`, the cloud provider switches and the other credential names (the ACP chat already got none of them), and every Claude Code settings JSON umwayi passes holds `forceLoginMethod: "claudeai"`. umwayi cannot see or cap usage beyond your plan (KNOWN-LIMITS 69 to 72).

`umwayi agent chat NAME` takes the same steps as `run`, in the same order (the rules see `"mode": "chat"`, and Ask me first adds `Start agent NAME (chat)?`). Then it prints what waits for you in the queue and hands your terminal to the agent unchanged: `claude --permission-mode default --settings HOOK`, or `kiro-cli chat --v3 [--agent A]` (no `--trust-tools` in a chat; Kiro asks you itself). Ctrl-C goes to the agent, not to umwayi. The kill switch, the logbook and `timeout_minutes` are still checked every second; a stop sends SIGTERM to the agent and everything it started (found in `/proc`), SIGKILL after 10 seconds, and puts your terminal mode back. Nothing of the conversation is logged. In a chat on the terminal the layer 9 hook is the only gate: umwayi does not see what you or the agent type.

`umwayi agent run` takes these steps in order, and the first that fails ends it:

| step | if it fails | exit |
| --- | --- | --- |
| agents.yaml and the prompt (one way, at most 100 KB, a Claude Code prompt must not start with `-`) | message | 64 |
| the kill switch | one logbook entry | 3 |
| the rules, action `{"type": "agent_run", "agent": NAME, ...}` | No: 2. Ask me first: 3 and one queue item `Start agent NAME (run)?` (not a second one while it is open) | 2 or 3 |
| the run lock | one logbook entry | 3 |
| every gate check, again | one logbook entry "Refused agent NAME: not gated (...)" | 2 |
| the start entry, then in `workdir`: Claude Code `claude -p --permission-mode default --settings HOOK ... PROMPT`; Kiro `kiro-cli chat --v3 --no-interactive [--agent A] [--trust-tools=...]` with the prompt on stdin | | |

While it runs, umwayi checks the kill switch and the logbook every second and watches `timeout_minutes`. The kill switch stops the agent with exit 3; a logbook that can no longer be written, or the timeout, with exit 2. Stopping means SIGTERM to the agent's whole process group, then SIGKILL after 10 seconds, and it happens on every way out, including when umwayi itself gets SIGTERM, SIGHUP or Ctrl-C (exit 2). The run exits 0 only when the agent exited 0; an agent that fails is exit 2. Every start, end, stop and refusal is one logbook entry; the prompt and the conversation never are. Answering the queue item does not start the agent: add a Yes rule for `agent_run` instead.

- `agents.yaml` lives in the root. Start from [agents.example.yaml](agents.example.yaml). Each agent has a fixed set of keys: `name`, `platform` (`claude-code` or `kiro`), `command` (only `claude` or `kiro-cli`, found on PATH), `transport`, `workdir` (outside the root), and a few limits. There is no key for extra arguments and no shell string.
- `check` runs, in order: the command is on PATH; its version is new enough (Claude Code 2.1.295, Kiro CLI 2.27.1); the layer 9 hook script is there; the hook starts and blocks a self-test event; for Kiro, your hook file in `WORKDIR/.kiro/hooks/` or `~/.kiro/hooks/` runs exactly the layer 9 command. It prints each result and the command lines a start would use, and writes nothing.
- Exit codes: 0 (valid, gated, or the agent finished), 2 (No, not gated, the agent failed, a logbook or timeout stop, an unexpected error), 3 (Ask me first, the kill switch, the run lock), 64 (usage or a bad agents.yaml). Never 1.
- For Claude Code, umwayi will add the hook itself for one session (`--settings`); for Kiro you add the hook file from [adapters/kiro/README.md](adapters/kiro/README.md). umwayi never writes a `.claude` or `.kiro` file.
- What the Claude Code, Kiro and ACP docs say about starting agents, and what they do not say: [adapters/NOTES-layer10.md](adapters/NOTES-layer10.md). Limits: [docs/KNOWN-LIMITS.md](docs/KNOWN-LIMITS.md) items 29 to 72. No real Claude Code or kiro-cli has been run by the tests; they use fakes that run the real hooks.
- Kiro: a headless run can only use the tools in `trust_tools`, and only when the rules also say Yes (Kiro denies untrusted tools, the hook denies the rest). `--trust-all-tools` is never used. The hook file you added is checked before every start; without it, or if it does not match exactly, the run is refused (exit 2).
- To keep a prompt out of every process list, give it with `--prompt-file` or `-`: `--prompt TEXT` puts it in umwayi's own arguments, and Claude Code gets it as an argument anyway (KNOWN-LIMITS 35 and 44).
