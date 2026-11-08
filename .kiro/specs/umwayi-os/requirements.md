# Requirements: umwayi-os

umwayi-os is an AI operating system for one person and their AI helpers. It keeps memory, enforces rules before an AI helper acts, tracks a queue of tasks and decisions, archives moved text with a fingerprint, and writes a logbook of every change.

It is built in layers. Each layer works alone and is tested before the next starts. Layers 1 to 8 are built (PRs 1 to 8, then hardening in PR 9). Layer 9 is planned for Nov 8 to Nov 9. Layers 10 and 11 are planned for Nov 9 to Nov 10; each is built only after the owner approves its requirements, design and tasks. The budget governor is planned for Nov 15 to Nov 21. The schedule to Dec 3 is in tasks.md.

## Glossary

- **Owner**: the one person who uses umwayi-os.
- **AI helper**: a program or model that acts for the owner. It is always draft only.
- **Answer**: one of Yes, No, Ask me first.
- **Action**: a JSON object that describes what an AI helper wants to do.
- **Root**: the folder that holds `umwayi.json`, `rules.yaml`, `queue.md` and `LOGBOOK.md`.
- **Platform**: an AI tool the owner uses that can run a hook before it acts, for example Claude Code or Kiro.
- **Adapter**: a thin program that sits between a platform's hook and `umwayi check` (layer 9).

## Cross-cutting requirements

- CC-1 Fail closed. Unknown, missing, malformed or ambiguous input gives Ask me first, or a clear error that changes nothing.
- CC-2 Every layer has automated tests.
- CC-3 CI runs the tests on every pull request.
- CC-4 Layers 1 to 5 make no network calls.
- CC-5 The repo holds no secrets, and the tool never prints secrets.
- CC-6 AI helpers never hold bank or card credentials and never move money.
- CC-7 Python with the standard library first. The core `umwayi` package stays standard library only. Third party packages are allowed only in adapter packages (layers 9 and 10), pinned and listed in that package's README.
- CC-8 There is one command line entry point named `umwayi`.
- CC-9 User text uses the words: rules, queue, archive, logbook, AI helper, Yes, No, Ask me first.
- CC-10 Docs contain no em dashes.
- CC-11 Work happens on feature branches with pull requests. Nothing is pushed to main.
- CC-12 Exit codes are the same in every command: 0 Yes or done, 1 a refusal that changed nothing, 2 No, 3 Ask me first, 64 a usage or config error. An unexpected error exits 2, never 0, 1 or 3, and does not print its message.

## Layer 1: Memory

User story: as the owner, I want my context kept as plain files and loaded as one bundle, so an AI helper starts every session with the right context and never sees private material.

Acceptance criteria:

1. Memory is a folder of plain text files: a master context file, a `projects/` folder and a `journal/` folder.
2. A loader reads these files into one context bundle in a stable order: master context, then projects, then journal, each sorted by path.
3. A config file (`umwayi.json`) lists private paths. A private path is a file, a folder or a glob.
4. A file under a private path is never put in the bundle, and its name is never printed.
5. If the config file is missing or invalid, the loader stops with an error and produces no bundle.
6. Symbolic links are never followed.
7. Files that are not valid UTF-8 text are skipped and counted, never partly read.
8. `umwayi memory bundle` prints the bundle as text or JSON.

## Layer 2: Rules

User story: as the owner, I want rules checked before an AI helper acts, so risky actions are stopped or sent to me.

Acceptance criteria:

1. Rules live in `rules.yaml`. Each rule has an id, a title and text. A rule may have a cause and matchers. Each rule also has a verdict (yes, no or ask), because a check must return an answer.
2. `umwayi check` takes an action as JSON and returns Yes, No or Ask me first, with the rule id and the reason.
3. Exit codes: 0 for Yes, 2 for No, 3 for Ask me first.
4. No matching rule gives Ask me first.
5. A missing, unreadable or broken `rules.yaml` gives Ask me first.
6. Invalid action JSON, an action that is not an object, or an action with duplicate keys gives Ask me first.
7. When several rules match, No beats Ask me first, and Ask me first beats Yes.
8. A rule without matchers never matches. It is documentation only.
9. Usage errors never use exit codes 0, 2 or 3 as a rules answer.

## Layer 3: Queue

User story: as the owner, I want one list of tasks and decisions, so I see what waits for me.

Acceptance criteria:

1. `queue.md` holds tasks and decisions as rows with an id, a kind, a title, a status, a recommendation, an answer and the date answered.
2. `umwayi queue list`, `add`, `answer`, `close` and `migrate` work on that file.
3. `answer` needs answer text, with the same limits as a recommendation. An open row has an empty answer, an answered row has an answer, a closed row keeps what it had.
4. `close` works on open and answered rows.
5. Ids are never reused, even if a row is removed by hand. `add` uses one more than the highest id in `queue.md` and in the logbook, and refuses if the logbook cannot be read.
6. Every change writes an entry to the logbook.
7. A malformed `queue.md` stops the command with an error and changes nothing. The old six column layout is refused with a message that names `umwayi queue migrate`.

## Layer 4: Archive

User story: as the owner, I want to move old text out of a file without losing it, so files stay short and nothing is lost.

Acceptance criteria:

1. `umwayi archive move` takes a source file, a line range or a start and end marker, and a required reason. It cuts that exact block out of the file and writes it to its own file in `archive/`.
2. `archive/INDEX.md` is a plain Markdown table with id, source file, date moved, reason, word count and the SHA-256 fingerprint of the exact bytes of the archive file.
3. The source file keeps one pointer line with the id and the archive path.
4. Ids look like A-0001 and are never reused: one more than the highest id in the index and in the logbook. If the logbook cannot be read, `move` refuses.
5. `move` refuses and changes nothing if the source is missing, is a symbolic link, is a private path from `umwayi.json`, the range is empty or outside the file, the markers are missing or appear twice, or the reason is empty.
6. The source, the archive file and the index all change or none do. A failed logbook write undoes the move.
7. Every move writes one logbook entry with date, source, what was added, what was checked and what was not done.
8. `umwayi archive verify` recomputes every SHA-256 fingerprint and reports each id as ok, changed, missing or not in the index. It exits 0 only when all are ok, otherwise 1. It never changes a file.
9. A malformed index is an error with a clear message and no change.
10. The output of `move` says which command would put the block back. That command is not built yet.

## Layer 5: Logbook

User story: as the owner, I want a record of every change, so I can trust and audit the system.

Acceptance criteria:

1. `LOGBOOK.md` is append only. The tool never edits earlier lines.
2. Each entry has a date, a source, what was added, what was checked and what was not done.
3. Layers 2 to 4 write entries through one shared checked append.
4. After every append, the SHA-256 of the whole logbook is recorded in `.umwayi/logbook.sha256`. Before every append it is recomputed, and the append is refused with a clear message if it does not match.
5. An existing logbook without a record is refused until the owner runs `umwayi logbook seal`, which records the current hash and writes an entry that says it was sealed and by whom. Nothing is sealed automatically.
6. `umwayi logbook verify` parses every entry and reports each problem with a line number, never the line text: a partial or broken entry, a missing field, an entry not in the format, text outside the header and entries. It exits 0 only when the format is valid and the recorded hash matches, otherwise 1. It never changes a file.
7. Entry dates are real dates and never go backwards. A backwards date is a verify problem and an append refusal.
8. `umwayi check` appends one entry per check with the rule id and answer. It never writes the action JSON, only its type if that is a short plain string. If the entry cannot be written, a No stays No (exit 2), a Yes becomes Ask me first (exit 3), and the reason says why. `--no-log` skips the entry for a dry run and says nothing was logged.
9. A lock file stops two appends from interleaving. A held lock gives a clear message.

## Layer 6: Automation

User story: as the owner, I want the layers to run on a schedule, so routine work happens without me.

Acceptance criteria:

1. `umwayi run JOBFILE` runs one job from a jobs file read with the existing YAML reader. A job has a name, a command word from a fixed allow list inside umwayi (report, check, queue-list) and a minimum gap in days between runs. There are no shell strings and no arbitrary commands.
2. Every run asks `umwayi check` first. No stops the job with exit 2, Ask me first with exit 3.
3. Every run adds one logbook entry through the checked append. If the logbook cannot be written, the job does not run.
4. A run before the minimum gap has passed is refused.
5. `umwayi report --since DATE` reads git history through one fixed git log command with no network, and writes a new numbered draft under drafts/. It never overwrites a file. It counts commits per day and lists subjects, with no author emails.
6. `umwayi publish-draft DRAFT` copies a draft to outbox/ as text for the owner to post by hand. It never pushes, never uses the network and never runs git write commands. The starter rules make publishing Ask me first.
7. The README shows a cron line. umwayi installs no schedule.
8. Exit codes: 0 Yes or done, 2 No, 3 Ask me first, 64 usage error, 1 for a refusal that changed nothing.

## Layer 7: Helpers

User story: as the owner, I want AI helpers that prepare work for me, so I only approve.

Acceptance criteria:

1. One helper base is used by every helper. Each action a helper wants to take goes through the same check as `umwayi check`.
2. No stops the helper with exit 2. Ask me first stops it with exit 3 and adds a queue item of kind decision for the owner. Only Yes continues.
3. Every step adds one logbook entry through the checked append.
4. A helper can never set an approval. Helper code does not accept, build or pass `--approved-by`.
5. A broken or missing rules file means no helper runs.
6. Steward (`umwayi steward`) reads queue.md and the logbook, then writes one proposal under drafts/ with open items, items waiting longer than a set number of days, and suggested next tasks. It never edits the queue, never answers an item and never runs other commands.
7. The social helper (`umwayi social draft ARTICLE_FILE`) reads one local article and writes numbered post drafts under drafts/, one per channel name in the `social_channels` allow list in umwayi.json. It uses fixed templates only (no model call, no network). Each post is short and plain, with no hashtags and no em dashes, and has a link line from the article front matter. It never posts. Publishing stays `umwayi publish-draft`, which is Ask me first.
8. The starter rules make helper reads and drafts Yes and any post, send or publish action from a helper No.
9. Helpers write no file outside drafts/, except their logbook entries and, for Ask me first, the queue item.

## Layer 8: Workflows

User story: as the owner, I want named workflows that AI helpers run as drafts, with one switch that stops everything.

Acceptance criteria:

1. A workflow is a file `workflows/NAME.yaml` read with the existing YAML reader, with a name and ordered steps. Each step is one command word from a fixed allow list inside umwayi (report, steward, social-draft, queue-list, check) with fixed arguments. There are no shell strings and no arbitrary commands.
2. `umwayi workflow validate NAME` reports every problem with a line number and exits 64 on a bad file.
3. `umwayi workflow run NAME` runs the steps in order. The content loop is collect (queue-list), brief (steward), draft (social-draft from one article path set in the file) and approve.
4. The approve step never approves anything. It adds a queue item of kind decision listing the drafts and stops the workflow with exit 3 until the owner answers. Publishing stays `umwayi publish-draft`, which is Ask me first.
5. Every step goes through the helper base and the rules. No stops with exit 2, Ask me first with exit 3. Each step adds one logbook entry. A failed logbook stops the run.
6. A workflow cannot set an approval: the file has no such key and the commands have no `--approved-by`.
7. The kill switch `.umwayi/KILL` (`umwayi kill on`, `umwayi kill off`, `umwayi kill status`) makes every AI helper, job and workflow stop before doing anything, with exit 3 and one logbook entry. A state of the kill file that cannot be read fails closed (stop).
8. Workflows write no file outside drafts/, except the queue and the logbook.

## Layer 9: Adapters

Status: built. Part 1 (the notes, the shared code, the Claude Code adapter) in PR 11; part 2 (the Kiro adapter, the generic stdin and stdout adapter, the kill switch in all adapters) in PR 12. Planned for Nov 8 to Nov 9. Open: starter rules in the repo rules.yaml, and the whole-system test with the adapters (Nov 11 to Nov 14).

User story: as the owner, I want the AI platforms I already use to ask umwayi before they act, so the same rules, queue and logbook cover them, and a broken adapter never lets an action through.

Acceptance criteria:

1. There is one thin adapter per platform. It turns the platform's hook input into `umwayi check` input, and turns the answer back into the platform's allow, deny or ask.
2. Targets, in this order: Claude Code PreToolUse hooks, Kiro hooks, and a generic stdin and stdout adapter.
3. Before any adapter is built, the official Claude Code hook documentation and the Kiro hook actions and hook types pages are read, and what they say about input fields, output format and which exit code blocks is written down with links.
4. Yes passes (allow). No blocks (deny).
5. Ask me first maps to the platform's ask where the platform has one. Where it does not, it maps to deny plus one queue item of kind decision for the owner.
6. A missing or broken rules file blocks.
7. Every adapter catches every error and blocks (exit 2, or deny). On Claude Code exit 1 blocks nothing, so an adapter never exits 1, and a crash never looks like allow.
8. Adapter packages may use third party packages, pinned and listed in their own README. The core `umwayi` package stays standard library only.
9. Each adapter has tests: No blocks, Ask me first asks or denies, Yes passes, a broken rules file blocks, a crash blocks.
10. Every check an adapter makes goes through `umwayi check`, so it writes one logbook entry like any other check.
11. While the kill switch is on, or its state cannot be read, every adapter denies every action (owner decision, 9.12). The logbook entry says the kill switch gave No.
12. The umwayi root is given on the adapter's command line (`--root`), never taken from the hook input.
13. Where Ask me first becomes a queue item, a repeated call adds no second item while the first is open (same kind, same title).
14. The generic adapter reads `{"tool_name", "tool_input"}` on stdin, writes one JSON line `{"decision", "reason"}` on stdout, and exits 0 for allow, 2 for deny, 3 for ask (or deny plus a queue item with `--no-ask`). The platform name comes from its command line only.
15. No adapter creates or changes a platform settings or hook file (`.claude`, `.kiro/hooks`); its README shows the snippet the owner adds.

## Layer 10: Own command line and chat

Status: approved by the owner on Nov 8 (tasks.md 10.0), with every open question answered as proposed. Parts 1 and 2 are built in PR 14: 10.R2 (agents.yaml), 10.R1.3 to 10.R1.5 (`list`, `check`, `validate`), 10.R5.1 and 10.R5.7 (argument lists), 10.R6 (gate checks). Part 3 is built in PR 15: `umwayi agent run` for Claude Code (10.R1.1, 10.R3, 10.R4, 10.R5.2, 10.R5.8, 10.R5.9, 10.R8 for run). Part 4 is built in PR 16: `umwayi agent run` for Kiro (10.R5.4, 10.R6.2 before every Kiro start). Part 5 is built in PR 17: `umwayi agent chat` with transport cli for Claude Code and Kiro (10.R1.2, 10.R5.3, 10.R5.5, 10.R7.1). Part 6 is built in PR 18: ACP chat for Kiro (10.R5.6, 10.R7.2 to 10.R7.7), in `umwayi/acp.py`. All six parts of layer 10 are built. Still open: the KNOWN-LIMITS items that first real runs may settle (10.20) and the whole-system test with a real run of each platform (10.21, Nov 11 to Nov 14). Part 7, Claude Code over ACP (10.R11), is specified and waiting for owner approval; it is not built. What the platform docs say, with links and the date read: `adapters/NOTES-layer10.md`.

User story: as the owner, I want one front door that starts any of my AI agents, so the queue, rules and logbook are always in front of them, and an agent umwayi cannot put a gate in front of is never started.

Items marked "proposed" depended on an open question in design.md (layer 10); the owner accepted every one as proposed on Nov 8.

Words used below: an **agent** is an AI platform's own program (`claude`, `kiro-cli`) started by umwayi; the **gate** is the layer 9 adapter hook for that platform; **gated** means umwayi has confirmed, before it starts the agent, that every tool call the agent makes goes through the gate.

### 10.R1 One front door

The owner starts every agent the same way: `umwayi agent run NAME` for one task, `umwayi agent chat NAME` for a conversation. `umwayi agent list` and `umwayi agent check NAME` show what is defined and whether it can be gated, without starting anything.

Acceptance criteria:

1. `umwayi agent run NAME` (with `--prompt TEXT`, `--prompt-file PATH`, or the prompt on stdin with `-`) starts the agent named NAME once, waits for it, and exits.
2. `umwayi agent chat NAME` starts the agent for a conversation with the owner on the terminal and exits when the conversation ends.
3. `umwayi agent list` prints every agent in agents.yaml with its platform and transport, and starts nothing.
4. `umwayi agent check NAME` runs every check that `run` and `chat` run before a start (10.R4, 10.R6), prints each result, and starts nothing. It exits 0 only if the agent can be gated.
5. `umwayi agent validate` reads agents.yaml, prints every problem with its line number and exits 64, or prints `ok` and exits 0.
6. Every subcommand takes `--root DIR` like the rest of umwayi; the agents file is `agents.yaml` in the root unless `--agents PATH` is given.
7. The front door starts agents only through their own command line or ACP (10.R5). It contains no model client: it opens no network connection, holds no model key, and imports no network module.

### 10.R2 Agent definitions in agents.yaml

Acceptance criteria:

1. agents.yaml is read with `umwayi/miniyaml.py`, the same strict reader as rules.yaml. Tabs, anchors, flow mappings and every other construct miniyaml rejects are errors.
2. The file has one top key, `agents`, a list. Each agent has exactly these keys, and no other key is accepted: `name` (required), `platform` (required), `command` (required), `transport` (optional, default `cli`), `workdir` (required), `kiro_agent`, `trust_tools`, `max_turns`, `timeout_minutes` (all optional).
3. `name` is 1 to 32 characters, a lowercase letter then lowercase letters, digits and `-`, and unique in the file.
4. `platform` is one of a fixed list in the code: `claude-code` or `kiro`. Any other value is an error, so an unknown platform is never started.
5. `command` is one word from a fixed allow list per platform in the code: `claude` for `claude-code`, `kiro-cli` for `kiro`. A path, a word with a space, a shell character, or any other word is an error. There is no field for free command line arguments, and no shell string anywhere.
6. `transport` is `cli` or `acp`. `acp` is accepted only for `kiro` (10.R5).
7. `workdir` is an absolute path to an existing folder with no `..` part. It must not be the umwayi root, inside it, or contain it (proposed, design open question 5).
8. `kiro_agent` (only for `kiro`, and not with `transport: acp`) is 1 to 64 letters, digits, `_` or `-`. `trust_tools` (only for `kiro`, `run`) is a list of tool IDs, each from a fixed list in the code of the built-in IDs the Kiro docs name. `max_turns` (only for `claude-code`) is a whole number from 1 to 200. `timeout_minutes` is a whole number from 1 to 720, default 30.
9. A missing, unreadable or invalid agents.yaml makes every `agent` subcommand except `validate` exit 64 and start nothing. Error messages carry a line number but never the text of the line.

### 10.R3 Rules, queue and logbook in front of every start

Acceptance criteria:

1. Before any check of the platform, the front door asks the rules with the action `{"type": "agent_run", "agent": NAME, "platform": P, "mode": "run"|"chat", "transport": "cli"|"acp"}`, through the same check as `umwayi check`, with one logbook entry.
2. Yes goes on. No stops with exit 2. Ask me first stops with exit 3 and adds one queue item of kind decision, `Start agent NAME (MODE)?`, unless an open item with that title already exists (proposed, design open question 2). Answering the item does not start the agent; the owner adds a Yes rule for that. A broken rules.yaml gives Ask me first, as everywhere.
3. Every start adds one logbook entry naming the agent, the platform, the transport and the full path of the command it ran. Every end adds one entry with the agent's exit code and how long it ran. Every refusal (10.R6) adds one entry with the reason. The prompt and the conversation are never written to the logbook.
4. If the logbook cannot be written, nothing is started (exit 2), as for helpers and workflows.
5. While the agent runs, every tool call it makes goes through its layer 9 adapter (`adapters/claude_code/hook.py` or `adapters/kiro/hook.py`) with `--root` set to the same root, so it is checked by the rules and written to the logbook, and Ask me first becomes the platform's ask or a deny plus a queue item, exactly as in layer 9.
6. `agent run` and `agent chat` take the shared run lock (`.umwayi/run.lock`) for as long as the agent runs. If it is held, they stop with exit 3 and start nothing (proposed, design open question 1).

### 10.R4 The kill switch stops every agent

Acceptance criteria:

1. If the kill switch is on, or its state cannot be read, when `run` or `chat` is called, nothing is started: exit 3 and one logbook entry, as for helpers.
2. While an agent runs, the front door checks the kill switch at least once a second (built in part 3; it also checks that the logbook can still be written, and stops the agent with exit 2 when it cannot). When it is on or unknown, it stops the agent (SIGTERM, then SIGKILL after 10 seconds), writes one logbook entry "The kill switch stopped agent NAME", and exits 3.
3. Independently, every tool call the agent tries while the switch is on is denied by its layer 9 adapter (decision 9.12), so a call made before the agent stops is still denied.

### 10.R5 How each agent is started

Acceptance criteria:

1. The command word is found on `PATH` when the front door runs, and the full path found is the one started and logged. The agent is started as a child process with an argument list, never through a shell.
2. Claude Code, `run`: `claude -p --permission-mode default --settings JSON [--max-turns N] PROMPT`, in `workdir`. JSON is built by umwayi from a fixed template: `disableAllHooks: false` and one `PreToolUse` hook, matcher `*`, exec form (`command` is the Python running umwayi, `args` is the layer 9 hook path, `--root`, the root), `timeout: 30`, `onFailure: "block"`. No settings file is created or changed. A prompt that starts with `-` is refused with exit 64, because the Claude Code docs do not say how to end the flags.
3. Claude Code, `chat`: `claude --permission-mode default --settings JSON`, interactive, with the owner's terminal passed straight through.
4. Kiro, `run`: `kiro-cli chat --v3 --no-interactive [--agent KIRO_AGENT] [--trust-tools=ID,...]`, in `workdir`, with the prompt on stdin. `--trust-all-tools` is never passed (proposed, design open question 3).
5. Kiro, `chat` with `transport: cli`: `kiro-cli chat --v3 [--agent KIRO_AGENT]`, interactive, with the owner's terminal passed straight through.
6. Kiro, `chat` with `transport: acp`: `kiro-cli acp --agent-engine=v3`, with umwayi as the ACP client (10.R7).
7. Never passed, by any code path: `--bare`, `--dangerously-skip-permissions`, `--allow-dangerously-skip-permissions`, `bypassPermissions`, `--setting-sources`, a second `--settings`, `--trust-all-tools`, `--cloud`, `--bg`. A test checks every argument list the code can build.
8. The agent's environment is the owner's environment, unchanged except that nothing umwayi adds holds a secret. umwayi never reads, logs or stores a model key or sign-in token.
9. `run` stops the agent after `timeout_minutes` (SIGTERM, then SIGKILL after 10 seconds) and exits 2.

### 10.R6 An agent that cannot be gated is refused, not run ungated

Acceptance criteria:

1. Before every start, the front door runs these checks, in this order, and refuses on the first that fails: the command word is on PATH; its version can be read and is new enough (Claude Code 2.1.295 or later, for `onFailure`; Kiro CLI 2.27.1 or later, for hooks in V3 headless runs); the layer 9 hook script for the platform exists; the hook starts and blocks a self-test event with exit 2 within 5 seconds (no rule is checked, nothing is logged by the hook); for Kiro, a hook file is found (10.R6.2).
2. Kiro: a JSON file in `WORKDIR/.kiro/hooks/` or `~/.kiro/hooks/` has a hook with trigger `PreToolUse`, no `matcher` (or `*`), and a command action whose command is exactly `PYTHON HOOK --root ROOT` with HOOK the absolute path of `adapters/kiro/hook.py`, ROOT the absolute root and PYTHON `python3` or an absolute path to a Python. The front door only reads these files; it never writes them.
3. A refusal prints which check failed and what the owner can do, adds one logbook entry, starts nothing, and exits 2 (No).
4. A platform not in the fixed list is never started (10.R2.4); there is no option to start an agent ungated, and no flag skips a check.
5. What the front door cannot check is listed in `docs/KNOWN-LIMITS.md` when it is built (for example a managed Claude Code policy that blocks non-managed hooks, see NOTES-layer10.md).

### 10.R7 Chat is a thin pass through

Acceptance criteria:

1. With `transport: cli`, the front door prints the open queue (how many items wait for the owner, and the oldest id), then hands the terminal to the agent and does nothing else until the agent exits, except the kill switch check (10.R4.2). It does not read, change or log the conversation.
2. With `transport: acp` (Kiro only), umwayi is a small ACP v1 client over stdio, standard library only. It sends `initialize` with protocol version 1 and no `fs` and no `terminal` capability, so it never reads, writes or runs anything for the agent. If the agent answers with another version, umwayi stops (exit 2).
3. Each line the owner types is sent as one `session/prompt`. Agent text is printed with terminal control sequences, and bidirectional, zero-width and tag characters, made visible. Tool calls are shown as one line each.
4. A `session/request_permission` is answered through the rules with the action `{"type": "acp_permission", "agent": NAME, "platform": "kiro", "kind": KIND, "tool": NAME_IF_GIVEN}` (one logbook entry). Yes selects an `allow_once` option; No selects a `reject_once` option; Ask me first asks the owner on the terminal, and only an explicit `y` selects `allow_once` (proposed, design open question 6). umwayi never selects `allow_always` or `reject_always`, never invents an option, and answers `reject_once` (or `cancelled` if there is no reject option) when there is no matching option or anything is unclear.
5. Any other request from the agent gets a JSON-RPC "method not found" error. A line from the agent that is not one valid JSON-RPC message ends the chat (exit 2).
6. umwayi's own chat commands start with `:` (`:queue`, `:quit`) so they cannot be mistaken for the agent's slash commands. Ctrl-C sends `session/cancel` and answers open permission requests with `cancelled`.
7. The ACP permission answer is a second gate. The first gate is still the layer 9 Kiro hook, which 10.R6 requires before the chat starts.

### 10.R8 Exit codes and fail closed

Acceptance criteria:

1. `umwayi agent run` and `umwayi agent chat` exit 0 only when the rules said Yes, the agent was gated, and the agent exited 0.
2. Exit 2 (No): the rules said No; the agent cannot be gated (10.R6); the logbook cannot be written; the agent exited non-zero (proposed, design open question 8); the agent hit its timeout; an ACP error; any crash in umwayi.
3. Exit 3 (Ask me first): the rules said Ask me first; the kill switch is on or unknown, before or during the run; the run lock is held.
4. Exit 64 (usage error): bad arguments; agents.yaml missing or invalid; an unknown agent name; a prompt that cannot be passed safely.
5. They never exit 1, and an error never leaves the agent running: on any exit path the agent is stopped first.
6. `umwayi agent check` exits 0 if the agent can be gated, 2 if not, 64 for a usage error.

### 10.R9 Standard library core, pinned packages only in adapter packages

Acceptance criteria:

1. Everything layer 10 adds to the core `umwayi` package uses the Python standard library only, and the core still never imports `adapters`.
2. If a layer 10 adapter package (under `adapters/`) ever needs a third party package, it is pinned to an exact version and listed in that package's own README, and it is not needed by the core or its tests. The plan for Dec 3 needs none.
3. A test checks that no core module imports a network module or a third party package.

### 10.R10 Tests

Acceptance criteria:

1. Every rule above has tests that run `umwayi agent ...` as a real child process, with fake `claude` and `kiro-cli` programs (small Python scripts put first on `PATH` in a temporary folder) that record their arguments, working folder and stdin, and that call the hook from `--settings` or the hook file the way the docs describe.
2. Planted faults (for example: the gate check skipped, the kill switch ignored, `--settings` left out, a Yes given for Ask me first) each make the tests fail, and are listed in the pull request.
3. Mutation checks on every new rule, as for layer 9, with the count caught listed in the pull request.
4. No test needs a network, a real agent, a model key or a sign-in.

### 10.R11 Claude Code over ACP (part 7: spec written Nov 8, waiting for owner approval)

This settles approved answer 9 of 10.0 ("Claude Code over ACP: decided later"). The owner decided on Nov 8: the spec now, the build only after the owner approves it; sign-in is verified first; no API key or token is ever written to agents.yaml, the repo, the logbook or the queue; the adapter is a pinned third party package and lives in an adapter folder only (owner decision H-079); the core `umwayi` package stays standard library only; umwayi never installs anything itself; spend limits stay with the budget governor (H-078). Doc and source facts with links: `adapters/NOTES-layer10.md`, section "Claude Code over ACP". Items marked "proposed" depend on an open question in design.md (layer 10, part 7).

User story: as the owner, I want to chat with Claude Code over ACP the way I chat with Kiro, with the rules answering every permission request, and with the layer 9 hook in front of every tool call confirmed before the chat starts.

Acceptance criteria:

1. agents.yaml accepts `platform: claude-code` with `transport: acp`. `command` stays `claude` (used by `agent run`, which stays headless `claude -p`); an ACP chat does not run `claude` from PATH, it runs the pinned adapter with `node` (10.R11.6). `kiro_agent` and `trust_tools` stay Kiro only; `max_turns` is not used by an ACP chat.
2. The start steps and exit codes are those of a Kiro ACP chat (10.R7, 10.R8): kill switch (3), rules `{"type": "agent_run", "agent": NAME, "platform": "claude-code", "mode": "chat", "transport": "acp"}` (No 2, Ask me first 3 and one queue item `Start agent NAME (chat)?`, once), run lock (3), every gate check (2), the start entry, the queue summary, the ACP session; the kill switch, the logbook and `timeout_minutes` during the chat; exit 0 only after `:quit` or the end of the owner's input and a clean agent exit; never 1.
3. It reuses `umwayi/acp.py`, `_Run`, `permission_action`, `permission_verdict` and `select_outcome`; nothing is copied. Every `session/request_permission` is answered by the rules as for Kiro (one logbook entry; the title never in the action; only `allow_once` or `reject_once`, never an `*_always` option, never an invented one; `platform` in the action is `claude-code`).
4. **The first gate is confirmed before the chat is used, or the chat is refused with exit 2 (fail closed).** The first gate is the layer 9 Claude Code hook (`adapters/claude_code/hook.py`), given to the adapter in the inline settings of `_meta.claudeCode.options.settings` (the flag-settings layer, the same as `claude --settings` in `agent run`) with `disableAllHooks: false` and `onFailure: "block"`, and `allowDangerouslySkipPermissions: false`. It counts as confirmed only when a `SessionStart` canary hook, given in the same inline settings, has run in this session before the first prompt is sent (it creates a file named by a fresh random token in a private temporary folder that umwayi made for this start and removes on every way out). If the canary is not seen within 30 seconds of `session/new`, the chat ends before any prompt is sent: exit 2, one logbook entry "Refused agent NAME: the first gate could not be confirmed in the ACP session".
5. What the gates are, said plainly. When the canary is seen, the first gate is the layer 9 hook (it sees the command and the path), and the second is umwayi's answer to permission requests (it sees only the kind and the tool name). When the canary is not seen, the only gate left would be the permission answer, and the adapter decides which calls it asks about (in `acceptEdits`, `auto` or `bypassPermissions` mode many calls are never asked). **Proposed: refuse, with no owner setting to allow it in part 7** (design open question 1).
6. A startup self-test that needs no model, as part of the gate checks (and of `umwayi agent check NAME`), in this order, the first failure refusing with exit 2: `node` on PATH (absolute path kept); `node --version` at least 22; the installed adapter file exists at the fixed path and is a regular file; its installed `package.json` has exactly the pinned name and version; `NODE ADAPTER --version` prints exactly the pinned version; `NODE ADAPTER --cli --version` prints a Claude Code version of at least 2.1.295; sign-in (10.R11.8); the layer 9 hook script and its self-test (10.R6). Each program runs with an argument list, no shell, a timeout, stdin empty, and the allow-listed environment (10.R11.9).
7. **Where the package lives:** `adapters/claude_acp/` holds `package.json` (one dependency, `@agentclientprotocol/claude-agent-acp`, an exact version with no range), `package-lock.json` (with integrity hashes), and a `README.md` with the owner's one install command, run in that folder (`npm ci --ignore-scripts`, proposed), and what it installs. umwayi never runs npm, npx or any installer; `node_modules/` is never committed (`.gitignore`). umwayi starts `[NODE, ABS/adapters/claude_acp/node_modules/@agentclientprotocol/claude-agent-acp/dist/index.js]`: no shell, no npx, no `#!/usr/bin/env node` lookup, nothing downloaded at run time. The pinned version is a constant in `umwayi/agents.py` and in `adapters/claude_acp/package.json`; a test checks they are equal.
8. **Sign-in is verified first and never read:** before the start, `NODE ADAPTER --cli auth status` (the bundled Claude CLI's `auth status`, which exits 0 when signed in) must exit 0 within 15 seconds; its output is discarded, never parsed, printed or logged. If it does not, the chat is refused with exit 2 and the message "Sign in to Claude Code first (claude, then /login), then try again." umwayi never reads, copies, stores or logs a credential, an API key or a token, and never runs a login for the owner. No key or token is ever accepted in agents.yaml, written to the repo, the logbook or the queue.
9. **The child environment is an allow list,** not umwayi's whole environment: `HOME`, `USER`, `LOGNAME`, `PATH`, `SHELL`, `LANG`, `LANGUAGE`, `LC_ALL`, `LC_CTYPE`, `LC_MESSAGES`, `TZ`, `TMPDIR`, `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_CACHE_HOME`, `XDG_STATE_HOME`, `XDG_RUNTIME_DIR`, `CLAUDE_CONFIG_DIR`, `HTTPS_PROXY`, `HTTP_PROXY`, `NO_PROXY` (and their lowercase forms), `NODE_EXTRA_CA_CERTS`, `SSL_CERT_FILE`, `SSL_CERT_DIR`, each passed only if set; plus `CLAUDE_AGENT_ACP_PROTOCOL=v1` set by umwayi. Never passed, even if set: `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `CLAUDE_CODE_EXECUTABLE`, `CLAUDE_AGENT_LOGS`, `IS_SANDBOX`, `NODE_OPTIONS`, `NODE_PATH`, any `npm_config_*`, and everything else not on the list (proposed, design open question 3). The same list is used for the self-test programs.
10. umwayi offers the adapter `clientCapabilities: {}` (no fs, no terminal, no auth, no elicitation), and `session/new` gets `cwd: WORKDIR`, `mcpServers: []` and the `_meta.claudeCode.options` of 10.R11.4. Right after `session/new`, umwayi sends `session/set_mode` with `modeId: "default"`; an error answer ends the chat with exit 2 (proposed, design open question 2), so a `defaultMode` from the owner's settings cannot start the session in a mode that approves calls without asking.
11. **Stop:** the adapter runs in its own session and process group. Every stop (the kill switch, the logbook, the timeout, an error, umwayi's SIGTERM, the end of the chat after 10 seconds without a clean exit) closes its stdin and then signals its process group and every descendant umwayi has seen in `/proc` (SIGTERM, SIGKILL after 10 seconds), because background commands keep running after `session/cancel` and their process group is not documented.
12. **Spend:** no spend limit is set by layer 10 (no `maxBudgetUsd` in `_meta`): spend limits stay with the budget governor (H-078).
13. **Standard library core:** the core `umwayi` package stays standard library only and never imports `adapters`; the only third party code is the npm package in `adapters/claude_acp/`, pinned, listed in its README, and never needed by the core or its tests (the tests use a fake `node`).
14. **Tests,** as for every part: real child processes, a fake `node` (a Python script on PATH) that answers the version, the CLI version and the sign-in check, and in ACP mode acts like the adapter (it runs the `SessionStart` canary and the `PreToolUse` hook from the inline settings of `_meta.claudeCode.options`, the way the Claude Code docs describe); planted faults and mutation checks with the counts in the pull request; no network, no real Node, no real Claude Code, no key.

### Out of scope for layer 10 (Dec 3)

- A model client, model keys, or any network call by umwayi.
- Any ACP agent or platform other than Kiro and, once part 7 is approved and built, Claude Code through the pinned `claude-agent-acp` adapter (10.R11): Codex, Gemini CLI and others are refused as not gated.
- Kiro or Claude Code cloud sessions, background sessions, resuming or listing sessions, MCP configuration, model or effort choice.
- More than one agent at a time, and agents talking to each other.
- Spend limits (budget governor, Nov 15 to 21) and sandboxing (layer 11).
- Windows and macOS.
- Changing any `.claude` or `.kiro` file.

## Layer 11: Linux-like features (outline)

Status: not started. Planned for Nov 9 to Nov 10. Built only after the owner approves its requirements, design and tasks.

User story: as the owner, I want umwayi-os to schedule, watch, limit and remember like an operating system, using the tools Linux already has.

Outline:

- Scheduling, file watching, process limits, a small database and terminal sessions.
- Reuse cron or systemd timers, inotify, SQLite, tmux, Unix permissions, and bubblewrap or containers.
- Do not build a new scheduler, file system or shell.

## Budget governor (outline)

Status: not started. Planned for Nov 15 to Nov 21. The owner decided to build it before Dec 3. Built only after the owner approves its requirements, design and tasks.

Outline:

- A limit on how much the AI helpers may use, so a runaway run is stopped. What is counted and what the limits are is decided in its requirements.
- It follows the same rules as every layer: fail closed, every change in the logbook, tests before it is used.

## Non goals for Dec 3

- Finance and marketing loops
- Web interface
