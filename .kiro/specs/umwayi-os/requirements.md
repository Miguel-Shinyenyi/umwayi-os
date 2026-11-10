# Requirements: umwayi-os

umwayi-os is an AI operating system for one person and their AI helpers. It keeps memory, enforces rules before an AI helper acts, tracks a queue of tasks and decisions, archives moved text with a fingerprint, and writes a logbook of every change.

It is built in layers. Each layer works alone and is tested before the next starts. Layers 1 to 8 are built (PRs 1 to 8, then hardening in PR 9). Layer 9 is built (PRs 11 and 12). A Layer 5 addendum on logbook crash safety (found Nov 9 behind a flaky test, PR 25) was approved on Nov 9 and is planned for Nov 10 to Nov 11. Layer 10 is built up to part 7c-1; parts 7c-2 and 7c-3 are planned for Nov 12 to Nov 13. Layer 11 (scheduled runs through systemd user timers; approved) is built now (PR 31), moved up from Nov 14 to Nov 15. Each is built only after the owner approves its requirements, design and tasks. The logbook hash chain is planned for Nov 16, the budget governor for Nov 17 to Nov 22, and the whole-system test and security scan for Nov 23 to Nov 26, after the governor. The schedule to Dec 3 is in tasks.md.

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

### Logbook hash chain (addendum, approved by the owner on Nov 9, tasks.md C.0; planned Nov 16, built early on Nov 7 in PR 32, tasks C.1 to C.4)

User story: as the owner, I want each logbook entry tied to the one before it, so an edit anywhere in the record is found and named, and so I can prove later what the logbook held on a given day.

Acceptance criteria:

1. **A Chain line on every new entry.** After the chain is started, every new entry ends with a fifth field `- Chain: HEX`, where HEX is the lowercase SHA-256 of the previous Chain value, one newline, and the entry text (from its `## DATE` heading through its `- Not done:` line, each line ending in a newline; the Chain line itself excluded).
2. **The start of the chain.** The first chained entry uses, as its previous value, the SHA-256 of the whole file at seal time, that is, of the exact bytes of `LOGBOOK.md` before that entry was appended. It is the entry written by `umwayi logbook seal`; on a logbook that is already sealed and intact, `umwayi logbook seal --chain --by NAME`, allowed once (approved answer C-Q1). Nothing starts the chain on its own.
3. **Old entries stay unchained.** Entries before the first chained entry keep their four fields and are not rewritten. After the first chained entry, an entry without a Chain line is a verify problem and an append refusal.
4. **The whole-file hash stays.** `.umwayi/logbook.sha256` and its checks (Layer 5, items 4 and 5) stay as they are. The chain is an extra check, not a replacement.
5. **Verify names the first broken entry.** `umwayi logbook verify` recomputes the chain and reports the first entry whose Chain value does not match, by its entry number and line number, never by its text. It never prints a logbook line, a Chain value of a broken entry, or the field values. Exit codes stay as in Layer 5 item 6.
6. **An outside anchor.** `umwayi logbook anchor` prints the newest Chain value and the number of chained entries, and changes nothing. `umwayi logbook verify --anchor VALUE` also fails when the chain is shorter than the anchored point, or when the Chain value at that point differs from VALUE (so a rewritten or truncated chain is found against a copy kept elsewhere). An anchor is `COUNT:HEX`.
7. **A broken chain stops everything that writes.** While the chain does not verify, every append is refused and every agent start is refused with exit 2 and one clear message on stderr (the logbook cannot be written, so nothing is logged). The kill switch still works. The checks of Layer 5 run first; the chain check is part of the same checked append and of `logbook.check_writable`.
8. **Said plainly in KNOWN-LIMITS:** without an outside anchor, anyone who can write the files can rewrite the whole chain and the hash record together, and verify cannot tell. The owner anchors weekly and before each submission, in two places: the sync log of the hub repository, and the Kiro Notion page. umwayi prints the anchor; it never writes to either place.
9. **Tests,** as for every layer: real child processes; a planted edit in an old entry, in the newest entry, a deleted entry, a reordered pair, a truncated tail, a missing Chain line after the start, a Chain line on an old entry, a whole chain rewritten consistently (found only with `--anchor`), a wrong anchor, a shorter chain than the anchor; no logbook text in any output; planted faults and mutation checks with the counts in the pull request.

### Logbook crash safety (addendum, approved by the owner on Nov 9, tasks.md L5.0; built Nov 10 in PR 27, tasks L5.1 to L5.5)

User story: as the owner, I want a logbook write that is stopped half way (a signal, a kill, a power cut) never to leave a logbook that refuses every later write or looks like a hand edit, while a real hand edit is still refused.

Found Nov 9, behind the flaky Ctrl-C and SIGHUP test (PR 25): `umwayi agent run` stops the agent's process group, and the hook's `umwayi check` in that group can die between appending its entry and recording the new hash. The logbook is then one entry ahead of its record and `.umwayi/logbook.lock` stays, so every later write and every agent start is refused until the owner deletes the lock and seals. Design: Layer 5, "Crash safety".

Acceptance criteria:

1. **An intent before the append.** Before the first byte is appended, the writer records its intent in `.umwayi/logbook.pending`: the record value it started from, the hash and length of the whole file before, the hash and length after, the exact entry bytes, and its own PID and start time (for messages). The intent is written whole (temporary file, fsync, rename, folder fsync). Then the entry is appended and fsynced, the record written (fsync, folder fsync), and the intent removed.
2. **The record only for the intended bytes.** After the append, the record is written only when the whole file hashes to the intended value. Otherwise nothing is recorded, the intent stays and the logbook is refused as tampered. (Today the record takes whatever the file holds after the append; approved answer L-Q5.)
3. **Recovery only for two exact states, only when no writer is running.** With an intent present and the lock held by the recovering process: the file is exactly the intended result (the write completed: its record is finished) or exactly the state before (the write never happened: the intent is dropped). The record must be the one the intent started from (or, for a completed write, the intended one), and the resulting file must pass the format and hash chain checks. Every other state is a tamper refusal, exactly like a hand edit: every append is refused, every agent start and a running agent stop with exit 2, `verify` exits 1. Nothing else is ever accepted automatically; `umwayi logbook seal` stays the only way to accept it.
4. **One entry per recovery.** Each recovery writes one entry, source `umwayi logbook recover`, naming the state (completed or not written), the dead writer by PID and start time, and what was checked; never a logbook line or the intent's entry bytes. The recovery and its entry are one write with its own intent, so a recovery that is itself stopped half way is resumed by the same rules and still leaves exactly one recovery entry.
5. **No stale lock.** A lock left by a writer that has died never blocks the next writer, and a lock held by a running writer is never taken over. `fcntl.flock` on `.umwayi/logbook.lock`, which the kernel releases when the process dies, as `.umwayi/run.lock` already does (approved answer L-Q1; PID plus start time was not chosen). The busy message no longer tells the owner to delete the lock file.
6. **Signals do not cut a write.** SIGTERM, SIGHUP, SIGINT and SIGQUIT received from writing the intent to removing it are held off and delivered once afterwards, in every umwayi process, including those with more than one thread and those with umwayi's own handlers (agent run, agent chat): they are blocked in the writing thread and their Python handlers are deferred for the same span (approved answer L-Q2). A logbook write from a thread other than the main thread is refused. SIGKILL and a power cut cannot be held off; item 3 covers them.
7. **With the hash chain.** The intended hash covers the whole new entry, Chain line included. Recovery of a completed write checks the chain before it records anything, and the recovery entry is chained like any entry. Crash safety is built first (Nov 10 to Nov 11); the chain (Nov 16) adds its checks to the new write.
8. **check_writable, readers and verify.** `logbook.check_writable` recovers like a write (it holds the same lock), so a running agent is not stopped by an interrupted write that can be recovered. Readers that take no lock (`read_checked`, `verify`) read the two exact states of item 3 as consistent while an intent is present, and write nothing; `verify` prints it as information (approved answer L-Q4).
9. **A torn tail.** A file that holds the state before plus only part of the intended entry (a power cut during the append) is refused with its own message, never accepted automatically. `umwayi logbook recover --torn-tail --by NAME` cuts the file back to the recorded length, only when the extra bytes are exactly a prefix of the intent's entry, and writes one entry that says so (approved answer L-Q3).
10. **Durable on a power cut.** Every rename and removal of the record and the intent is followed by an fsync of `.umwayi/`, and creating `LOGBOOK.md` by an fsync of the root folder.
11. **Said plainly in KNOWN-LIMITS:** the intent sits next to the record, so whoever can forge the record can forge an intent (no new weakness beyond KNOWN-LIMITS 3); durability depends on the disk honouring fsync; a torn tail needs the owner; the lock works on local file systems only, and deleting it by hand during a write can still let two writes overlap; a SIGKILL between a queue or archive change and its entry leaves the change without an entry (as today).
12. **Tests,** as for every layer: real child processes; each signal during a held write; SIGKILL at each step; a simulated power cut; every other mismatch still refused; a hand edit while a dead writer's intent is present still refused; the recovery entry present once; the original defect end to end; planted faults and mutation checks with the counts in the pull request.

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

Status: built. Part 1 (the notes, the shared code, the Claude Code adapter) in PR 11; part 2 (the Kiro adapter, the generic stdin and stdout adapter, the kill switch in all adapters) in PR 12. Planned for Nov 8 to Nov 9. Open: starter rules in the repo rules.yaml, and the whole-system test with the adapters (Nov 23 to Nov 26).

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

Status: approved by the owner on Nov 8 (tasks.md 10.0), with every open question answered as proposed. Parts 1 and 2 are built in PR 14: 10.R2 (agents.yaml), 10.R1.3 to 10.R1.5 (`list`, `check`, `validate`), 10.R5.1 and 10.R5.7 (argument lists), 10.R6 (gate checks). Part 3 is built in PR 15: `umwayi agent run` for Claude Code (10.R1.1, 10.R3, 10.R4, 10.R5.2, 10.R5.8, 10.R5.9, 10.R8 for run). Part 4 is built in PR 16: `umwayi agent run` for Kiro (10.R5.4, 10.R6.2 before every Kiro start). Part 5 is built in PR 17: `umwayi agent chat` with transport cli for Claude Code and Kiro (10.R1.2, 10.R5.3, 10.R5.5, 10.R7.1). Part 6 is built in PR 18: ACP chat for Kiro (10.R5.6, 10.R7.2 to 10.R7.7), in `umwayi/acp.py`. All six parts of layer 10 are built. Still open: the KNOWN-LIMITS items that first real runs may settle (10.20) and the whole-system test with a real run of each platform (10.21, Nov 23 to Nov 26). Part 7, Claude Code over ACP (10.R11), was approved by the owner on Nov 8 (tasks.md 10.22), with every open question answered as proposed. Part 7a is built in PR 20: 10.R11.1 (agents.yaml), 10.R11.6 (the gate checks, in `umwayi agent check`), 10.R11.7 (`adapters/claude_acp/`), 10.R11.8 (sign-in by exit code) and 10.R11.9 (the environment allow list). Part 7b is built in PR 21: the chat itself, 10.R11.2 to 10.R11.5 (the start steps, the inline settings and the canary, refused with exit 2 when the canary is not seen), 10.R11.10 (session/new with `_meta` and session/set_mode `default`) and 10.R11.11 (the stop of the process group and every seen descendant). 10.29 (the whole chat end to end with the fake) and 10.30 (the planted faults of part 7) are done in PR 29. Still open: the owner's first real run (10.31: its docs are written in PR 29; the run itself is not done, steps and a results table in `adapters/NOTES-layer10.md`, "The owner's first real run (10.31)"). Part 7c (10.R12, subscription first) was approved on Nov 9 (tasks.md 10.32); part 7c-1 is built in PR 23: the login check for every Claude Code start (10.R12.2 to 10.R12.5, 10.R12.11), the credential names removed for `agent run` and the cli chat (10.R12.6) and `forceLoginMethod` (10.R12.7). Part 7c-2 is built in PR 28: `umwayi agent login` (10.R12.9) and Kiro subscription first (10.R12.13). Part 7c-3 is built in PR 29: the ACP watch (10.R12.8). Still open: the owner's real checks folded into 10.31. What the platform docs say, with links and the date read: `adapters/NOTES-layer10.md`.

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

### 10.R11 Claude Code over ACP (part 7: approved Nov 8; part 7a built in PR 20, part 7b in PR 21; 10.29 and 10.30 in PR 29; the owner's first real run (10.31) not done)

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

### 10.R12 Subscription first: the Claude Code login and billing check (part 7c: approved Nov 9 (tasks.md 10.32); part 7c-1 built in PR 23: items 2 to 7 and 11; part 7c-2 built in PR 28: items 9 and 13; part 7c-3 built in PR 29: item 8)

The owner asked on Nov 9: subscription first, with a login and billing check. Nothing of part 7c is built before the owner approves it (tasks.md 10.32). Doc and source facts with links: `adapters/NOTES-layer10.md`, section "Login and billing for Claude Code". Items marked "proposed" depend on an open question in design.md (layer 10, part 7c). When approved, item 3 replaces 10.R11.8 (sign-in by exit code only) for every Claude Code start; everything else in 10.R11 stays.

Why: Claude Code picks the credential that pays by a fixed precedence, and a Claude subscription login comes last. Any `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `apiKeyHelper`, `CLAUDE_CODE_OAUTH_TOKEN`, cloud provider variable or gateway wins over it. In `claude -p` an API key in the environment is always used. Today `umwayi agent run` and the cli chat pass umwayi's whole environment, so an API key in the owner's shell silently turns a run into pay-as-you-go API billing. A project's `.claude/settings.json` can do the same with `apiKeyHelper`, even in an ACP chat.

User story: as the owner, I want every Claude Code agent umwayi starts to be paid by my Claude subscription and nothing else, checked before the start, so that an API key in my shell or a setting in a repository never bills me by the token without my knowing.

Acceptance criteria:

1. **Scope:** every Claude Code start: `umwayi agent run`, `umwayi agent chat` with transport cli, and with transport acp; and, on the owner's request of Nov 9 that subscription comes first on every platform, every Kiro start as far as Kiro can be checked (item 13).
2. **Subscription first, fail closed:** a Claude Code agent is started only when the login check (item 3) proves that a Claude subscription login (claude.ai: Pro, Max, Ultra, Team or Enterprise) is the credential that will pay. Otherwise it is refused with exit 2 and nothing is started.
   - This covers an API key, an auth token, an `apiKeyHelper`, an OAuth token from the environment, a Console login, a cloud provider, a gateway, no login, or an answer umwayi cannot read.
   - There is no agents.yaml key or flag to allow API billing in part 7c (proposed, open question 7).
3. **The login check**, a gate check run for every Claude Code start (and by `umwayi agent check NAME`), after the version check and before the hook checks (proposed, open question 8):
   - **The program:**
     - transport acp: `[NODE, ADAPTER, "--cli", "auth", "status", "--json"]`;
     - `agent run` and the cli chat: `[CLAUDE, "auth", "status", "--json"]`, where CLAUDE is the absolute `claude` found by the gate check.
   - **How it runs:** in the agent's `workdir` (so the project settings it would load are the same); with exactly the environment the agent will get (item 6 and 10.R11.9); stdin empty; no shell; a timeout of 15 s; stderr discarded; at most 64 KB of stdout read.
   - **Passed** only when all of these hold:
     - the exit code is 0 and stdout is one JSON object;
     - `loggedIn` is `true`;
     - `authMethod` is `"claude.ai"`;
     - `apiKeySource` is absent;
     - `apiProvider` is absent or `"firstParty"`;
     - `subscriptionType` is a string of 1 to 40 characters from `a-z`, `0-9`, space, `_` and `-`.
   - Anything else, a missing field included, is a failed check. Only `authMethod` is documented by Claude Code; the other names come from the pinned adapter's source, so an unknown or changed shape fails closed.
   - Whether `authMethod` `"oauth_token"` (a `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token`, which is also billed to a subscription) may pass too is open question 2; proposed no.
4. **Nothing personal is read, printed, logged or stored:**
   - Only the six fields of item 3 are taken from the JSON.
   - The output is held in memory only for the check, then dropped.
   - `email`, `orgId`, `orgName`, any other field and the raw output never appear in a message, the logbook, the queue or an exception text.
   - Only the plan word (`subscriptionType`) may be shown: in `agent check` and in the start entry, as "plan: WORD" (proposed, open question 5).
5. **What the owner sees when it fails**, one line each, never the email (exit 2, one logbook entry "Refused agent NAME: not gated (login: ...)"):

   | the check found | the line names the fix |
   | --- | --- |
   | not signed in | "Sign in to Claude Code with your Claude subscription first (claude, then /login, choose the Claude account), then try again." |
   | an API key, auth token or helper (`api_key`, `api_key_helper`, or `apiKeySource` present) | the source kind: unset the variable, or remove `apiKeyHelper` from the settings file. The value is never shown. |
   | `oauth_token` | `CLAUDE_CODE_OAUTH_TOKEN` is set |
   | `third_party`, or an `apiProvider` other than `firstParty` | a cloud provider or gateway is selected |
   | a Console login | Console is API billing; sign in with the Claude account |
   | no answer in 15 s, or output umwayi cannot read | "could not be confirmed" |

6. **Credential variables never reach `agent run` or the cli chat** (proposed, open question 3):
   - These are removed from the environment the agent and its login check get: `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CODE_OAUTH_REFRESH_TOKEN`, `CLAUDE_CODE_OAUTH_SCOPES`, `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX`, `CLAUDE_CODE_USE_FOUNDRY`, `ANTHROPIC_PROFILE`, `ANTHROPIC_FEDERATION_RULE_ID`, `ANTHROPIC_ORGANIZATION_ID` and `ANTHROPIC_IDENTITY_TOKEN_FILE`.
   - Everything else is passed as today (the terminal chat needs the owner's environment).
   - The ACP chat keeps the allow list of 10.R11.9, which already passes none of them.
   - umwayi never reads a value of these names; it only leaves them out.
7. **A second line in the session** (proposed, open question 4): `forceLoginMethod: "claudeai"` is added to the one `claude_settings()` template. It then reaches `agent run` and the cli chat (`--settings`) and the ACP chat (inline settings). It is a second line only: not confirmed to block an environment or helper credential from that settings layer.
8. **During an ACP chat** (proposed, open question 6):
   - An `_auth/status_update` notification whose `params.authStatus.kind` is not `"account"` ends the chat as a stop: the adapter is stopped as in 10.R11.11, exit 2, and one entry "Agent NAME was stopped: the Claude Code login changed and a subscription no longer pays".
   - Only `kind` is read; the label, account, plan and email are not.
   - A notification with no readable `kind` is ignored, because the adapter sends "cannot determine" as silence.
   - There is no such watch for `agent run` or the cli chat (the CLI sends nothing umwayi can read); the check before the start is all.
9. **`umwayi agent login NAME`: the claude.ai sign-in started by umwayi, for a Claude Code agent with transport acp** (owner decision Nov 9, option B; replaces "umwayi signs in for no one"):
   - **The same start steps as a chat, in the same order, up to the login check:**
     - agents.yaml (64);
     - the kill switch (3);
     - the rules, with a new action type `{"type": "agent_login", "agent": NAME, "platform": "claude-code", "transport": "acp"}` (No 2; Ask me first 3 and one queue item `Log in agent NAME?`, once);
     - the run lock (3);
     - the gate checks of 10.R11.6 up to and not including the login check: node, node version, adapter file, adapter package, adapter version, Claude Code version (2).
   - **Already a subscription:** the login check (item 3) runs first. If it already passes, nothing is started, and umwayi prints `Claude subscription OK (plan: WORD)` and exits 0 (proposed, open question 11).
   - **The program:** `[NODE, ADAPTER, "--cli", "auth", "login", "--claudeai"]`, an argument list with no shell. It is never given `--console`, `--email`, `--sso` or any other word, and nothing from agents.yaml.
   - **The terminal:** stdin, stdout and stderr are the owner's terminal, unchanged, as in a cli chat. umwayi never reads, logs or stores the login's output, a code, a URL or any token.
   - **The environment** is `child_env()` (10.R11.9) plus only the names a browser login needs, each passed only if set: `TERM`, `COLORTERM`, `BROWSER`, `DISPLAY`, `WAYLAND_DISPLAY`, `XDG_CURRENT_DESKTOP`, `XDG_DATA_DIRS`, `DESKTOP_SESSION`, `DBUS_SESSION_BUS_ADDRESS`, `SSH_TTY`, `SSH_CONNECTION`, `SSH_CLIENT` and `NO_BROWSER`.
     - The reasons are in NOTES-layer10.md, "Signing in from umwayi".
     - Never passed: `CLAUDE_CODE_OAUTH_REFRESH_TOKEN`, `CLAUDE_CODE_OAUTH_SCOPES`, `CLAUDE_CODE_REMOTE`, and everything else 10.R11.9 leaves out.
   - **While it runs:** the kill switch, the logbook and a fixed limit of 10 minutes are watched every second (proposed). A stop sends SIGTERM to the login and every descendant seen in `/proc`, SIGKILL after 10 s (the cli chat stop of part 5), and puts the terminal mode back. Ctrl-C goes to the login, not to umwayi.
   - **Afterwards**, whatever the login's exit code, the login check (item 3) runs again. umwayi prints only `Claude subscription OK (plan: WORD)` (exit 0), or the one refusal line of item 5 (exit 2).
   - **Logbook:** one entry when the login starts, and one at its end with "subscription OK" or the refusal reason. Never its output.
   - **Exit codes:** 0 (subscription OK), 2 (rules No, a gate check failed, the login failed or was stopped by the logbook or the limit, or no subscription afterwards), 3 (kill switch, Ask me first, run lock), 64 (usage, an unknown agent, or not a Claude Code agent with transport acp). Never 1.
   - **Never on its own:** `agent run` and `agent chat` never start a login, not even when the login check fails. They refuse and point to `umwayi agent login NAME`.
   - **Still never:** `auth logout`, `setup-token`, `/login` inside a session, `--console`, ACP auth methods (`clientCapabilities` stays `{}`), and reading, copying or storing a credential, key, token or helper output.
10. **Billing beyond the subscription is not visible:** the check proves which credential pays, not how much, and not whether a plan's extra usage is on. umwayi sets no spend limit. Spend stays with the budget governor (H-078), and KNOWN-LIMITS says so.
11. **`umwayi agent check NAME`** prints the login line with the other checks, for example `ok: login: Claude subscription (plan: max)` or `no: login: signed in with an API key from the environment (ANTHROPIC_API_KEY is not passed; unset it or ...)`. It starts no agent and writes nothing.
12. **Tests**, as for every part: real child processes, no network, no real Claude Code, no key.
    - The fake `claude` and the fake `node` answer `auth status --json` from a scripted JSON object that includes a planted email, organization name and secret.
    - Each failing shape of item 5 refuses with exit 2 and starts nothing.
    - The planted email, organization and secret never appear in stdout, stderr, the logbook or the queue.
    - The credential variables of item 6 are absent from what the fake records, even when set.
    - `forceLoginMethod` is in every settings JSON.
    - An `_auth/status_update` with `kind: "api_key"` stops an ACP chat with nothing left alive.
    - `agent login`, with the fake `node` for `--cli auth login --claudeai`:
      - a successful login flips the scripted `auth status` to a subscription, and umwayi prints `Claude subscription OK (plan: max)` and exits 0;
      - a failed login, and a login that leaves an API key in front, each give exit 2 with the refusal line;
      - already a subscription: nothing is started, exit 0;
      - the kill switch during the login: exit 3 and nothing alive;
      - a planted secret, URL and code printed by the fake login never appear in the logbook or the queue, and umwayi never reads its output;
      - no argument list anywhere holds `--console`, `--email` or `--sso`;
      - the fake records only `child_env()` names plus the login names of item 9, never `CLAUDE_CODE_OAUTH_REFRESH_TOKEN`;
      - rules No and Ask me first (one queue item), the run lock, and a failing gate check each start nothing;
      - `agent run` and `agent chat` never start a login.
    - Kiro (item 13): `KIRO_API_KEY` is absent from what the fake `kiro-cli` records for run, cli chat, ACP chat, `whoami` and `login`, even when set; the `whoami` check refuses on a non-zero exit; `agent login` for a Kiro agent runs `[KIRO, "login"]` with no flags.
    - Planted faults and mutation checks with the counts in the pull request.
13. **Kiro, subscription first as far as Kiro can be checked** (owner request Nov 9; proposed, design open question 10, which replaces the earlier "Kiro unchanged"):
    - **Who pays:** by the Kiro docs, every Kiro login pays from the subscription's credits, an API key included. Beyond them, only add-on credits the owner buys by hand in the Kiro portal; when credits run out, usage pauses. So there is no separate pay-as-you-go path for umwayi to block, and no Kiro billing check is needed for "who pays". "How much" cannot be read outside a Kiro session.
    - **`KIRO_API_KEY` is removed** from the environment of every Kiro start (`agent run`, cli chat, ACP chat) and of the Kiro login check and login, so only the owner's browser login (`kiro-cli login`) is used. A key is a long-lived credential that may belong to another account. umwayi never reads its value.
    - **The Kiro login check:** `[KIRO, "whoami"]` in the workdir, with that environment, stdin empty, 15 s, output discarded and never parsed (its JSON field names are not documented and it holds the email). It must exit 0, or the start is refused with exit 2: "Sign in to Kiro first (kiro-cli login), then try again." It runs after the version check, as for Claude Code.
    - **`umwayi agent login NAME` for a Kiro agent** (any transport): the same steps as item 9 with action `{"type": "agent_login", "agent": NAME, "platform": "kiro", "transport": T}`, then `[KIRO, "login"]` with no flags, on the owner's terminal, with the Kiro start environment minus `KIRO_API_KEY`; then the `whoami` check; exit codes as item 9. Never `--license`, `--identity-provider`, `--social`, `logout`, `acp --login` or `--auth-method client`.
    - **Not known, and said so in KNOWN-LIMITS:** the plan, the credits left, the login method by field, whether `whoami` exits non-zero when signed out, and whether headless runs work without `KIRO_API_KEY` (the Kiro docs conflict: see NOTES). If they do not, a Kiro `agent run` is refused or fails with exit 2, which is fail closed.

### Out of scope for layer 10 (Dec 3)

- A model client, model keys, or any network call by umwayi.
- Any ACP agent or platform other than Kiro and, once part 7 is approved and built, Claude Code through the pinned `claude-agent-acp` adapter (10.R11): Codex, Gemini CLI and others are refused as not gated.
- Kiro or Claude Code cloud sessions, background sessions, resuming or listing sessions, MCP configuration, model or effort choice.
- More than one agent at a time, and agents talking to each other.
- Spend limits (budget governor, Nov 17 to 22) and sandboxing (layer 11 proposes to defer it to its own spec after Dec 3, 11.R8).
- Windows and macOS.
- Changing any `.claude` or `.kiro` file.

## Layer 11: Linux-like features

Status: approved by the owner (tasks.md 11.0), with L11-Q1 to L11-Q13 answered as proposed and L11-Q14 changed: built now, not on Nov 14 to Nov 15. 11.R1 to 11.R7 are built in PR 31 (`umwayi/schedule.py`, `umwayi schedule`); 11.R7.8, the owner's real check (tasks.md 11.6), is not done. Facts with links, and what the docs do not say: `adapters/NOTES-layer11.md`. The candidates and why most of them wait: design.md, "Layer 11", section "The candidates".

User story: as the owner, I want my jobs and workflows to run on a schedule while I am away, using the scheduler Linux already has, so that nothing new decides when umwayi runs and every run still goes through the kill switch, the run lock, the rules and the logbook.

Scope for Dec 3 (proposed, design open question L11-Q1): **scheduled runs through systemd user timers** (11.R1 to 11.R7). The other candidates (file watching with inotify, SQLite, tmux, bubblewrap) are deferred or cut (11.R8). No new scheduler, file system or shell is built.

Layer 11 commands follow the layer 10 exit codes: 0 done, 2 a refusal or any error, 3 Ask me first, 64 a usage or config error. Never 1. (The steering file's older code 1 for refusals is not used by new commands.)

### 11.R1 The schedule file (`schedule.yaml`)

1. `schedule.yaml` in the root (or `--file PATH` inside the root) is read with the existing `miniyaml` reader: a normal file, not a link, at most 64 KB, UTF-8. One top key `schedules`, a list of 1 to 20 entries.
2. Each entry has exactly these keys:
   - `name`: lowercase letters, digits and `-`, starting with a letter, at most 32 characters, unique in the file;
   - `run`: `job` or `workflow`;
   - for `run: job`: `job` (a job name from the jobs file) and optionally `jobs_file` (a relative path inside the root, default `jobs.yaml`);
   - for `run: workflow`: `workflow` (a name from `workflows/`);
   - `every`: `daily`, `weekly` or `monthly`;
   - `at`: local time `HH:MM` (00:00 to 23:59);
   - `day`: for `weekly` one of `mon` to `sun`, for `monthly` a day from 1 to 28; not allowed for `daily`.
   No other key, no free text schedule (no `OnCalendar` string and no cron line from the file).
3. Cross checks: the jobs file and the job exist and validate (layer 6), and the job's `min_gap_days` is not longer than the schedule's period (daily 1, weekly 7, monthly 28 days); the workflow exists and validates (layer 8).
4. **The path rule.** Every path umwayi writes into a unit file or prints in a cron line (the root, the jobs file, the Python interpreter, the umwayi source folder) must be absolute, have no `..` part, be at most 1024 characters, and use only `A-Z a-z 0-9 / . _ + -`. Otherwise the schedule is refused (64) with a line that names the path's role, never its text if it holds a control character. This avoids systemd specifiers (`%`), variable expansion (`$`), quoting, and cron and shell syntax, instead of escaping them.
5. Every problem is reported with a line number, all problems at once, as `umwayi agent validate` does (64).

### 11.R2 The files umwayi renders

1. For each entry, one systemd **user** service and one timer, from fixed templates in `umwayi/schedule.py`, named `umwayi-ROOTID-NAME.service` and `umwayi-ROOTID-NAME.timer`, where ROOTID is the first 8 hex characters of the SHA-256 of the root's real path (two roots never share a unit).
2. The service is `Type=oneshot` and runs exactly one umwayi front door, with no shell: `PYTHON -m umwayi --root ROOT run JOBS_FILE --job JOB`, or `PYTHON -m umwayi --root ROOT workflow run WORKFLOW`. PYTHON is the interpreter running `umwayi schedule install`. It sets only `PYTHONPATH` (the umwayi source folder), `WorkingDirectory=ROOT`, a start limit (`TimeoutStartSec`, proposed 30 min, L11-Q7), `TimeoutStopSec=15s` and `KillMode=control-group`, so a stop ends every process the run started.
3. The timer has one `OnCalendar=` from `every`, `day` and `at` (for example `Mon *-*-* 07:30:00`), `Persistent=true` (proposed, L11-Q6), `Unit=` naming its service, and `WantedBy=timers.target`.
4. Both files start with a comment that says umwayi wrote them, from which root and entry, and that `umwayi schedule check` compares them byte for byte.
5. `umwayi schedule show [NAME] --cron` prints the equivalent crontab line for owners without systemd. umwayi never installs a crontab (proposed, L11-Q2).
6. Rendering is deterministic: the same `schedule.yaml`, root and interpreter always give the same bytes.

### 11.R3 `umwayi schedule` commands

```
umwayi schedule validate [--file PATH]                  check schedule.yaml: 0 or 64; writes nothing
umwayi schedule show [NAME] [--cron] [--file PATH]      print the unit files (or cron lines) and where they go; writes nothing
umwayi schedule check [NAME] [--file PATH]              compare installed files with what umwayi would write: 0 or 2; writes nothing
umwayi schedule install NAME [--approved-by WHO] [--file PATH] [--date D]   write the two unit files: 0, 2, 3 or 64
umwayi schedule remove NAME [--file PATH] [--date D]    remove the two unit files umwayi wrote: 0, 2, 3 or 64
```

1. The unit folder is `$XDG_CONFIG_HOME/systemd/user`, or `$HOME/.config/systemd/user` when `XDG_CONFIG_HOME` is not set or not absolute (the user unit load path in NOTES-layer11.md). It must be a normal folder, not a link; it is created (with its missing parents) only by `install`.
2. **umwayi never runs `systemctl`, `crontab`, `loginctl` or any other program** for scheduling (proposed, L11-Q3). `install` and `remove` print the exact `systemctl --user` commands for the owner to run. `schedule.py` imports no program runner.
3. `check` reports, for each entry: installed and identical; not installed; changed by hand; not a regular file; a drop-in folder (`UNIT.d/`) next to it, which can override it; and whether the timer's enable link exists. It also lists `umwayi-ROOTID-*` units in the folder with no entry in `schedule.yaml`. It exits 0 only when every entry is installed, identical and has no drop-in, and nothing is left over.
4. `show`, `validate` and `check` write nothing, take no lock and are not stopped by the kill switch, like `umwayi logbook verify`.

### 11.R4 Install and remove: the kill switch, the rules, the run lock and the logbook

1. **install**, in this order:
   - `schedule.yaml` and the entry are valid (64);
   - the two rendered files already installed with identical bytes: "already installed", exit 0, nothing asked or written;
   - the kill switch: on or unknown stops it (3, one entry);
   - the rules, with `{"type": "schedule_install", "schedule": NAME, "run": "job"|"workflow", "target": JOB_OR_WORKFLOW, "every": EVERY}`: No stops it (2); Ask me first stops it (3, one queue item `Install schedule NAME?`, added once) unless `--approved-by WHO` is given, as for `publish-draft` (proposed, L11-Q4); Yes goes on;
   - the run lock (busy: 3, one entry);
   - each file is created with `O_CREAT | O_EXCL | O_NOFOLLOW` (an existing file that differs is never overwritten: 2), the service first, then the timer; if the timer cannot be written, the service just written is removed;
   - one logbook entry with the unit names, the folder, the SHA-256 of each file and who approved it; if it cannot be written, both files are removed and the answer is 2;
   - the output names the two files and the commands `systemctl --user daemon-reload` and `systemctl --user enable --now UNIT.timer`, and says that timers run only while the owner is logged in unless the owner enables lingering (`loginctl enable-linger`), which umwayi never does (L11-Q8).
2. **remove**, in this order:
   - the entry is valid (64); neither file present: "not installed", 0;
   - the timer's enable link exists: refused (2) with the commands `systemctl --user disable --now UNIT.timer` and `systemctl --user clean --what=state UNIT.timer` to run first;
   - a file that differs from what umwayi would write, a drop-in folder, or a file that is not a regular file: refused (2), the owner removes it by hand;
   - the rules, with `{"type": "schedule_remove", "schedule": NAME}` (proposed starter rule: Yes, because removing a schedule is the safe direction); No 2, Ask me first 3 with one queue item;
   - the timer, then the service, are removed; one logbook entry; if it cannot be written, both files are put back and the answer is 2;
   - the output says to run `systemctl --user daemon-reload`.
   remove is not stopped by the kill switch and takes no run lock, so the owner can always take a schedule away (the same reason `umwayi kill on` works with a broken logbook).
3. Messages never print the contents of a unit file, a jobs file or a workflow.

### 11.R5 What a scheduled run does, and never does

1. A timer starts only the command of 11.R2, which is an existing umwayi front door. That front door already checks, in order, the kill switch (3, one entry), the run lock (busy: 3, one entry), the rules (`run_job` or `workflow_step`) and the logbook, as layers 6 and 8 specify. Layer 11 adds no new way to run anything.
2. Only jobs and workflows can be scheduled. **Never `umwayi agent run`, `agent chat` or `agent login`** (proposed, L11-Q5): no agent runs unattended before the budget governor exists, and a sign-in needs the owner at the terminal.
3. A scheduled run gets the user manager's environment plus `PYTHONPATH`; umwayi adds no credential, and jobs and workflows start no agent and use no network.
4. When the start limit passes, systemd stops the whole run (SIGTERM, SIGKILL after 15 s). The logbook stays whole (crash safety, Layer 5 addendum); the run itself writes no entry for that stop, and the journal records it (KNOWN-LIMITS).
5. The run's exit code is the front door's: 0 done, 2 No, 3 Ask me first (kill switch, run lock, an approve step), and for `umwayi run` the layer 6 code 1 for a refusal (proposed: kept as is, L11-Q9). Any code but 0 shows the unit as failed in `systemctl --user status`.

### 11.R6 Fail closed

1. Any unexpected error in a `schedule` command exits 2 and leaves no file it created half way; the error text never holds file contents.
2. An unknown or malformed state (the unit folder a link, a unit file a folder, a drop-in folder, an unreadable file) is a refusal, never a guess.
3. `schedule.py` does not touch the network, imports no program runner, and stays standard library only.

### 11.R7 Tests

As for every layer: real child processes (`python -m umwayi schedule ...`), with `HOME` and `XDG_CONFIG_HOME` in a temporary folder, so the real `~/.config` is never touched. No systemd, cron, network or credential is needed or used.

1. Every bad `schedule.yaml` shape and every path rule case refuses with 64 and a line number, and writes nothing.
2. The exact bytes of both rendered files and of the cron line, for each `every`.
3. install and remove through every branch of 11.R4: rules Yes, No and Ask me first (one queue item, not two), `--approved-by`, the kill switch on and unknown, the run lock held, an existing different file, a linked folder, a logbook that fails (no file left), already installed, the enable link present, a changed file, a drop-in.
4. check reports each state of 11.R3.3.
5. The scheduled run end to end: the `ExecStart=` and `Environment=` lines of a rendered service are run as a real child process exactly as written; a job runs with its one entry; the kill switch on gives 3 and one entry; the run lock held by another process gives 3.
6. Code guards: `schedule.py` imports no `subprocess`, `os.system`, network or third party module, and no argument list anywhere names `systemctl`, `crontab` or `loginctl`.
7. Only exit codes 0, 2, 3 and 64 from `schedule` commands. Planted faults and mutation checks with the counts in the pull request.
8. The owner's real check on a machine with a systemd user manager (task 11.6): `systemd-analyze --user verify` on the rendered files, enable, one run, and the kill switch stopping a run. Not done until the owner runs it.

### 11.R8 Not in layer 11 for Dec 3 (proposed; the evaluation is in design.md)

- **File watching with inotify: cut** (L11-Q10). The standard library has no inotify, and `ctypes` would turn a bug into a crash that is not exit 2. inotify cannot tell an AI helper's own writes from anyone else's (a loop), drops events on overflow, is not recursive and misses network file systems. A timer covers the use case (the content loop picks up new articles on its next run). A systemd path unit may be specified after Dec 3.
- **SQLite for queryable state: deferred** (L11-Q11). No requirement before Dec 3 needs it, the plain files are small, and the logbook (with its hash chain) stays the only source of truth (B-Q1). After Dec 3: a read only index that is rebuilt from the files and never written by an AI helper.
- **tmux for long chats: cut from umwayi** (L11-Q12). The owner can already run `tmux new -s chat`, then `umwayi agent chat NAME` inside it, with no umwayi change. Starting tmux from umwayi would pass commands through a shell (not documented otherwise), give the chat the tmux server's environment instead of umwayi's filtered one, hold the run lock for hours, and let any process of the same user type into the chat (`send-keys`) or read it (`capture-pane`).
- **bubblewrap or a similar sandbox: deferred to its own spec after Dec 3** (L11-Q13). It is the most valuable candidate, but the layer 9 hook runs inside the agent's process tree and must write `.umwayi/` and `LOGBOOK.md`, so a sandbox around the agent cannot protect the logbook or the kill switch until the check moves outside it. Agents need the network, Ubuntu blocks unprivileged user namespaces by default, and Claude Code already runs its own bwrap sandbox for Bash (nesting not documented).

## Budget governor

Status: approved by the owner on Nov 9 (tasks.md B.0), with open questions B-Q1 to B-Q6 answered as proposed. Planned build Nov 17 to Nov 22, after the logbook hash chain (Nov 16); built early in PR 33 (B.1 to B.9 and umwayi's part of B.10; the owner's capture of one real export, B.10, is not done). The whole-system test and security scan on Nov 23 to Nov 26 cover it, including the telemetry receiver. It follows the same rules as every layer: fail closed, every change in the logbook, tests before it is used. Doc facts with links: design.md "Budget governor", section "Facts".

User story: as the owner, I want one unit for what every agent run costs, measured where it can be and declared or assumed at the worst case where it cannot, with limits per run and per day that stop a run before it starts or while it runs, so a runaway agent cannot spend without my knowing.

### B.R1 One unit (tasks B.1 to B.5)

1. **The unit UU is one US cent of estimated list price.** On a subscription, nothing is billed per token: UU then measures what the same use would cost at list price, so limits mean the same on every platform.
2. **The ledger stores whole micros of a dollar** (integers, never floats). UU = micros / 10000, rounded up, computed only when a limit is checked or a value is shown.
3. **`units.yaml`** in the root says how each platform's reading becomes micros. A reading is one of:
   - `usd_micros`: micros reported by the agent itself (Claude Code telemetry, B.R2);
   - `tokens`: tokens by type times a declared rate per model, in micros per million tokens;
   - `credits`: credits times a declared rate in micros per credit;
   - `runs`: one run times a declared flat value in micros.
4. **Every reading is tagged** `measured` (from the agent's own report), `declared` (from rates in `units.yaml`) or `unknown`. An unknown reading counts at the worst case value (`limits.unknown_worst_case`), never zero.
5. **Rates carry a date and a source** (a URL or "owner"). A rate or limit with no date or source is a validation problem (exit 64, with its line number). Any change to a rate or a limit is one logbook entry, written before the new value is first used. If that entry cannot be written, nothing starts (exit 2).
6. **Reserve, settle, release.** Before an agent starts, the per-run cap is reserved against every limit it counts toward. After the run, the reading is settled and the rest of the reservation is released. If the reservation does not fit, the agent is not started.
7. **Limits in UU** (placeholders until calibrated): per run 100, per day 500, per agent per day 300, per platform per day 400, unknown worst case 100. A day is the logbook date.
8. **Calibration,** only after at least 20 measured runs over at least 7 days: per run becomes 1.5 times the 95th percentile of measured runs, per day 2 times the median measured day. Each proposed change is shown with the data it came from, and each applied change is one logbook entry with that data (approved answer B-Q3: `calibrate` only proposes; the owner edits `units.yaml`, and that change is logged).
9. **Reaching a limit gives exit 3.** Before a start: the reservation does not fit. During a run: the measured cost passes the per-run cap; the agent is stopped as for the timeout (10.R4, 10.R11.11). The kill switch (exit 3) and a logbook failure (exit 2) are checked first and still win.
10. **`umwayi budget status`** shows, for today and for each limit: used, reserved and left in UU, and the share of used that was measured, declared and unknown. It starts nothing and writes nothing.
11. **Settled readings are chained logbook entries** (the Logbook hash chain addendum). The ledger is read from those entries; there is no second ledger file to drift from the logbook (approved answer B-Q1).
12. **A new action type `budget_check`** in the rules: `{"type": "budget_check", "agent": NAME, "platform": P, "reserve_uu": N, "left_today_uu": M}`, asked once per start after the reservation fits. Yes goes on; No gives exit 2; Ask me first gives exit 3 and one queue item `Spend up to N UU on agent NAME?`, once.

### B.R2 Telemetry for Claude Code (tasks B.6 and B.7)

1. **A receiver for one run.** For every Claude Code start (`agent run`, the cli chat and the ACP chat), umwayi runs a standard library `http.server` receiver on 127.0.0.1, on a random free port, for that run only, and stops it when the run ends.
2. **The agent's environment gets, set by umwayi:**
   - `CLAUDE_CODE_ENABLE_TELEMETRY=1`, `OTEL_METRICS_EXPORTER=otlp`, `OTEL_LOGS_EXPORTER=otlp`, `OTEL_EXPORTER_OTLP_PROTOCOL=http/json`;
   - `OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:PORT`;
   - `OTEL_EXPORTER_OTLP_HEADERS=x-umwayi-run=SECRET` (a fresh `secrets.token_hex(16)` per run);
   - `OTEL_METRIC_EXPORT_INTERVAL=5000` and `OTEL_LOGS_EXPORT_INTERVAL=5000`;
   - `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=delta`;
   - `OTEL_LOG_USER_PROMPTS=0`, `OTEL_LOG_ASSISTANT_RESPONSES=0`, `OTEL_LOG_TOOL_DETAILS=0`, `OTEL_LOG_RAW_API_BODIES=0`, `OTEL_TRACES_EXPORTER=none`.
   
   These names are added to the ACP allowed environment (`CHILD_ENV_SET`, 10.R11.9) and to the run and cli chat environment, with their tests. Every other `OTEL_*` name the owner set, `BETA_TRACING_ENDPOINT` and `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA` are removed, so no export goes elsewhere.
3. **What the receiver accepts:** only `POST /v1/metrics` and `POST /v1/logs`, from a loopback address, with the exact run header, `Content-Type: application/json`, a `Content-Length`, and a body of at most 1 MB (16 MB per run in all). Anything else is answered 401, 404, 411 or 413 and not read. The secret is compared in constant time.
4. **Counts only.** It reads `claude_code.cost.usage`, `claude_code.token.usage` (by `type`: input, output, cacheRead, cacheCreation) and the `claude_code.api_request` event (`cost_usd_micros`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `model`). Nothing else is read, kept or logged; a body is dropped as soon as it is parsed. `OTEL_LOG_USER_PROMPTS` stays off.
5. **One logbook entry per run:** run id, models, tokens by type, cost in micros (and UU), request count, and the tag. A run with no report is `unknown`, never zero, and counts at the worst case.
6. **`cost_usd` is an estimate** (the Claude Code docs say so). On a subscription it is the list price estimate the unit is defined by, not a bill.

### B.R3 Status, the rules and tests (tasks B.8 to B.10)

1. **B.8:** `umwayi budget status`, the `budget_check` action type, and its place in the start steps: kill switch, rules (`agent_run`), run lock, gate checks, the reservation (limits, then `budget_check`), the start entry, the start.
2. **B.9 tests**, as for every layer, with real child processes and a fake telemetry sender:
   - missing telemetry (unknown, worst case);
   - huge numbers (a value above 10^12 micros, negative, a float, or a string is invalid and settles the full reservation);
   - a wrong or missing header, a non-loopback peer, an oversize body, too many bodies;
   - a rate change (one entry before use; refused when it cannot be logged);
   - a limit hit before the start (exit 3, nothing started) and in the middle of a run (stopped, exit 3, settled);
   - the kill switch and a logbook failure winning over the budget;
   - no prompt or response text in any output.
3. **B.10:** capture one real Claude Code export by the owner and record its field names only (never values) in NOTES; the receiver's parser is checked against it.

## Non goals for Dec 3

- Finance and marketing loops
- Web interface
- Shared rule packs (after Dec 3)
- File watching, an SQLite index, tmux sessions and a sandbox for agents and helpers (layer 11 proposes to cut or defer them, 11.R8)
