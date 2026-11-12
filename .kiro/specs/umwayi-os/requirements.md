# Requirements: umwayi-os

umwayi-os is an AI operating system for one person and their AI helpers. It keeps memory, enforces rules before an AI helper acts, tracks a queue of tasks and decisions, archives moved text with a fingerprint, and writes a logbook of every change.

It is built in layers. Each layer works alone and is tested before the next starts. Layers 1 to 8 are built (PRs 1 to 8, then hardening in PR 9). Layer 9 is built (PRs 11 and 12). A Layer 5 addendum on logbook crash safety (found Nov 9 behind a flaky test, PR 25) was approved on Nov 9 and is planned for Nov 10 to Nov 11. Layer 10 is built up to part 7c-1; parts 7c-2 and 7c-3 are planned for Nov 12 to Nov 13. Layer 11 (scheduled runs through systemd user timers; approved) is built now (PR 31), moved up from Nov 14 to Nov 15. Each is built only after the owner approves its requirements, design and tasks. The logbook hash chain is planned for Nov 16, the budget governor for Nov 17 to Nov 22, and the whole-system test and security scan for Nov 23 to Nov 26, after the governor. Layer 12 (a web interface, the view: a calm 3D hillside with eleven stations that shows counts from a read only snapshot, and an owner checks panel) is in scope before Dec 3 since Nov 10; its spec is in the UI.0 pull request and waits for the owner's approval. The schedule to Dec 3 is in tasks.md.

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

Status: built. Part 1 (the notes, the shared code, the Claude Code adapter) in PR 11; part 2 (the Kiro adapter, the generic stdin and stdout adapter, the kill switch in all adapters) in PR 12. Planned for Nov 8 to Nov 9. The whole-system test with the adapters was added in PR 36 and the starter rules in the repo rules.yaml in PR 43.

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

Status: approved by the owner on Nov 8 (tasks.md 10.0), with every open question answered as proposed. Parts 1 and 2 are built in PR 14: 10.R2 (agents.yaml), 10.R1.3 to 10.R1.5 (`list`, `check`, `validate`), 10.R5.1 and 10.R5.7 (argument lists), 10.R6 (gate checks). Part 3 is built in PR 15: `umwayi agent run` for Claude Code (10.R1.1, 10.R3, 10.R4, 10.R5.2, 10.R5.8, 10.R5.9, 10.R8 for run). Part 4 is built in PR 16: `umwayi agent run` for Kiro (10.R5.4, 10.R6.2 before every Kiro start). Part 5 is built in PR 17: `umwayi agent chat` with transport cli for Claude Code and Kiro (10.R1.2, 10.R5.3, 10.R5.5, 10.R7.1). Part 6 is built in PR 18: ACP chat for Kiro (10.R5.6, 10.R7.2 to 10.R7.7), in `umwayi/acp.py`. All six parts of layer 10 are built. Still open: the KNOWN-LIMITS items that first real runs may settle (10.20) and the whole-system test with a real run of each platform (10.21, Nov 23 to Nov 26). Part 7, Claude Code over ACP (10.R11), was approved by the owner on Nov 8 (tasks.md 10.22), with every open question answered as proposed. Part 7a is built in PR 20: 10.R11.1 (agents.yaml), 10.R11.6 (the gate checks, in `umwayi agent check`), 10.R11.7 (`adapters/claude_acp/`), 10.R11.8 (sign-in by exit code) and 10.R11.9 (the environment allow list). Part 7b is built in PR 21: the chat itself, 10.R11.2 to 10.R11.5 (the start steps, the inline settings and the canary, refused with exit 2 when the canary is not seen), 10.R11.10 (session/new with `_meta` and session/set_mode `default`) and 10.R11.11 (the stop of the process group and every seen descendant). 10.29 (the whole chat end to end with the fake) and 10.30 (the planted faults of part 7) are done in PR 29. Still open: the owner's first real run (10.31: its docs are written in PR 29; the run itself is not done, steps and a results table in `adapters/NOTES-layer10.md`, "The owner's first real run (10.31)"). Part 7c (10.R12, subscription first) was approved on Nov 9 (tasks.md 10.32); part 7c-1 is built in PR 23: the login check for every Claude Code start (10.R12.2 to 10.R12.5, 10.R12.11), the credential names removed for `agent run` and the cli chat (10.R12.6) and `forceLoginMethod` (10.R12.7). Part 7c-2 is built in PR 28: `umwayi agent login` (10.R12.9) and Kiro subscription first (10.R12.13). Part 7c-3 is built in PR 29: the ACP watch (10.R12.8). Still open: the owner's real checks folded into 10.31. Part 8, OpenCode over ACP (10.R13), and Muse Spark Open as an OpenCode model (10.R14) are specified on Nov 11 (tasks.md 10.41 and 10.40) and wait for the owner's approval; nothing of them is built. What the platform docs say, with links and the date read: `adapters/NOTES-layer10.md`.

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

### 10.R13 OpenCode over ACP (part 8: spec written Nov 11 (tasks.md 10.41), waiting for the owner's approval; the owner asked on Nov 11 for the build before Dec 3)

The owner asked on Nov 9 to include OpenCode as a platform, subscription or free first, and answered the open questions on Nov 11: OC1 to OC5 as proposed in design.md, and OC6 changed to "build before Dec 3". Nothing is built before the owner approves this spec (tasks.md 10.41). Facts with links and dates: `adapters/NOTES-layer10.md`, sections "OpenCode as a platform" (Nov 9) and "OpenCode V2: the facts checked for the adapter spec" (Nov 11). Design: design.md "Part 8: OpenCode over ACP". Items marked "proposed" depend on a new open question in design.md (OC7 to OC12); the spec is written with the proposal.

Why: OpenCode speaks ACP, which umwayi already speaks, and can run free and local models. But it has no command hook like Claude Code or Kiro, its default policy allows every tool, and its config can come from many places that outrank one another. So the gate must be built from OpenCode's own plugin hook, the start must prove that hook is loaded, and every other place that could widen it must be absent.

User story: as the owner, I want to chat with OpenCode through umwayi on a free or subscription route, with every tool call checked by my rules before it runs, and I want umwayi to refuse to start OpenCode whenever it cannot prove that.

Words used below: the **plugin** is umwayi's OpenCode plugin directory, `adapters/opencode/plugin/`; the **inline config** is the one JSON document umwayi passes in `OPENCODE_CONFIG_CONTENT`; a **route** is the provider and account that pays for the model.

Acceptance criteria:

1. **Platform and transport.** `platform: opencode` joins the fixed platform list with command word `opencode` and transport `acp` only. `umwayi agent chat NAME` starts `[OPENCODE, "acp"]` in the workdir. `umwayi agent run` and `umwayi agent login` for an OpenCode agent are refused with exit 64 and a line that says only `agent chat` is offered for OpenCode. `transport: cli` for OpenCode is a validation error (64).
2. **agents.yaml keys.** An OpenCode agent must have `provider` and `model`, and only OpenCode agents may have them (64 otherwise).
   - `provider` is one of the routes in item 6, exactly as written there.
   - `model` is `provider/model-id` with the same provider, matching `^[a-z0-9][a-z0-9._-]{0,39}/[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$`.
   - `kiro_agent`, `trust_tools` and `max_turns` stay refused for OpenCode.
3. **The start steps are the same as every chat** (10.R3, 10.R4): the kill switch, the rules with action type `agent_chat` and `platform: opencode`, the run lock, the gate checks (item 8), the start entry, the queue summary. The chat goes through `acp.py` with its stop, watch and Ctrl-C behaviour unchanged.
4. **The environment is an allow list** like 10.R11.9: the names of 10.R11.9 except `CLAUDE_CONFIG_DIR` and `CLAUDE_AGENT_ACP_PROTOCOL`, plus `OPENCODE_CONFIG_CONTENT` set by umwayi, and nothing else that starts with `OPENCODE_`. The same environment is used for `opencode --version`. Every provider credential name, `OPENCODE_API_KEY`, `OPENCODE_CONFIG`, `OPENCODE_CONFIG_DIR`, `OPENCODE_DB`, `OPENCODE_PASSWORD`, `OPENCODE_DISABLE_PROJECT_CONFIG` and every cloud credential variable are absent because they are not on the list. A test names each of them.
5. **The inline config** is generated by one pure function from the agent and is the same bytes for the same agent and token. It holds exactly:
   - `permissions`: one rule, `{"action": "*", "resource": "*", "effect": "ask"}`;
   - `policies`, in this order: `provider.use` deny `*`, then allow the agent's provider; `integration.use` deny `*`, then allow the route's integration resource (item 6);
   - `model`: the agent's `model`;
   - `plugins`: one entry, `{"package": ABSOLUTE PATH OF adapters/opencode/plugin, "options": {...}}` with the options of item 7;
   - for a local route, the provider entry of item 6;
   - nothing else.

   OpenCode replaces `{env:NAME}` and `{file:PATH}` in the inline config (NOTES, Nov 11), so the function refuses (exit 2) when any value it would write holds `{env:` or `{file:`, for example in the umwayi root path.
6. **Routes: subscription or free first, never pay as you go** (OC3 as proposed). The allowed `provider` values and what each allows:

   | provider | route | `integration.use` allows | needs |
   | --- | --- | --- | --- |
   | `opencode` | the signed-out free tier | the bare `opencode` only, so a signed-in Console account (`opencode#ACCOUNT`) is not used | nothing |
   | `ollama`, `lmstudio`, `vllm` | a local server on its default loopback port | the provider ID | the server running |
   | `openai` | ChatGPT Plus or Pro sign-in | `openai#*` only, never the bare `openai` (an environment key) | `opencode auth login` by the owner beforehand |
   | `github-copilot` | GitHub Copilot sign-in | `github-copilot#*` only | `opencode auth login` by the owner beforehand |
   | OpenCode Go | the Go subscription | refused: 10.42 found the provider ID `opencode-go` in the binary, and an integration that looks shared with Console credits; not seen with a sign-in (OC13) | the Go sign-in |

   Console credits, provider API keys and every other provider are refused with exit 2 and a line that says pay as you go is not offered (it waits for the budget governor). For `ollama`, `lmstudio` and `vllm` the provider entry is `settings.baseURL` with the documented default loopback URL and nothing else. In particular it has no `models` entry, which breaks the route (10.42).
7. **The first gate: the plugin** (OC1 as proposed, with the V2 API). `adapters/opencode/plugin/index.js` is plain JavaScript with a default export `{id: "umwayi.gate", setup}` and no import other than `node:` built-ins. Its options, set only by umwayi in the inline config, are the hook command (an argv list), the canary file and the canary token. In `setup` it registers:
   - `ctx.tool.hook("execute.before")`: for every tool call it runs the layer 9 generic adapter (`adapters/stdio/hook.py --root ROOT --platform opencode`) in exec form with `{"tool_name", "tool_input"}` on stdin and a timeout of 10 s. Exit 0 (Yes): the call goes on. Exit 3 (Ask me first): the call goes on to the permission request (item 9) only when the tool is one OpenCode asks permission for. That is a fixed list in the plugin: `read`, `glob`, `grep`, `write`, `edit`, `shell`, `webfetch`, `question` and `subagent`, the tools seen asking on 2.2.7 (10.42). For any other tool it throws, including `execute` (Code Mode) and the Code Mode tools named `opencode_*` (OC15). Exit 2, any other code, a timeout, a start error or any exception: it throws, so the call does not run.
   - `ctx.permission.hook("evaluate")`: an `allow` becomes `ask`; `ask` and `deny` stay. So a permission request reaches umwayi even if the `ask` rule of item 5 is lost.
   - `ctx.event.subscribe` for `session.created`: it writes the canary token to the canary file, once, with `O_EXCL`.
   - The plugin never reads or writes anything else, opens no network connection and prints nothing to stdout.
8. **The gate checks, in this order**, each refusing with exit 2, one logbook entry and nothing started:
   1. `opencode` on PATH;
   2. its version, read from `opencode --version` (15 s, at most 64 KB), is 2.2.3 or newer (OC5 as proposed: V1 and older V2 are refused; 2.2.3 is the first release that honours `integration.use` in its current meaning and `plugin.use`). Output umwayi cannot read is a refusal;
   3. `adapters/stdio/hook.py` and the plugin's `index.js` are regular files, not links, inside the umwayi source tree;
   4. **no managed config** (OC4 as proposed): refused when `/etc/opencode` exists (Linux), or `/Library/Application Support/opencode` or any `ai.opencode.managed.plist` under `/Library/Managed Preferences` exists (macOS);
   5. **no other config that can widen the gate** (proposed, OC7): refused when, from the workdir up to `/`, any `opencode.json`, `opencode.jsonc` or `.opencode` entry exists; or when a file in the global config directory (`$XDG_CONFIG_HOME/opencode`, else `~/.config/opencode`) named `opencode.json` or `opencode.jsonc` contains any of the quoted words `"permissions"`, `"permission"`, `"policies"`, `"plugins"`, `"plugin"`, `"agents"`, `"agent"`, `"experimental"`, `"enabled_providers"`, `"disabled_providers"`; or when that directory has a `plugins`, `plugin`, `agents` or `agent` entry. A file that cannot be read as UTF-8 text of at most 1 MB is a refusal. This is a text match, so a comment that names a key also refuses (the safe direction);
   6. the route of item 6 is allowed.
   `umwayi agent check NAME` runs the same checks and starts nothing. These checks hold at the start only. OpenCode reloads a changed config during a chat, so the starter rules in `adapters/opencode/rules.example.yaml` say No to any edit or shell command that names `opencode.json`, `opencode.jsonc` or `.opencode` (KNOWN-LIMITS 181).
9. **The second gate: permission requests.** Every `session/request_permission` is answered by the rules through the existing `permission_action` with `platform: opencode`, `kind` and `tool` only when they are short plain words (the title and `rawInput` are never in the action), with one logbook entry each. Yes is `once`, No is `reject`, Ask me first asks the owner, then `once` or `reject`. `always` is never selected. A request from a child session is answered the same way. A request with no `name` gets at most Ask me first.
10. **The canary.** After `session/new` the chat waits up to 30 s for the canary file to hold exactly the token (the 7b `gate_ready`). Not seen, or a different token: exit 2 with "could not be confirmed", one refusal entry, nothing of the owner sent, the agent stopped. The token is fresh for every start; the folder is private (0700) and removed on every path.
11. **The model is checked** (proposed, OC10): the `model` config option in the `session/new` answer must equal the agent's `model`. Otherwise exit 2 before the first prompt.
12. **No login by umwayi** (proposal 6 of design.md, unchanged by OC1 to OC5): `initialize` sends `clientCapabilities: {}`; `authenticate` is never sent. An `auth_required` error ends the chat with exit 2 and a line that says to run `opencode auth login` first.
13. **Logbook and secrets.** Nothing of the inline config, the token, the conversation, tool input or OpenCode's output is written to the logbook. Each gated tool call writes its own `umwayi check` entry (the plugin) and, when a permission request follows, one more (item 9).
14. **Tests** (10.R10), every one with a fake `opencode` started as a real child process:
   - the inline config bytes for each route, and that every name of item 4 is absent from the child environment;
   - each gate check refusing on its planted fault, and `agent check` showing the same;
   - the plugin under `node` with a small fake `ctx`: Yes, No, Ask me first for an asked and an unasked tool, a timeout, a missing hook, an exception, the evaluate hook, the canary written once;
   - a static check that `index.js` imports only `node:` modules and has no `eval`, `Function(` or network module;
   - the chat end to end: canary seen and not seen, a wrong token, the model compare, permission answers for each verdict, a child-session request, `always` never chosen, `auth_required`;
   - planted faults and mutation checks with counts in the pull request.
   The plugin tests need `node` on PATH. Without it they fail with a message, they do not skip.
15. **Known limits** are in `docs/KNOWN-LIMITS.md` items 180 to 187 and 190 (190 from 10.42), written with the spec and made true to the build in 10.51.

### 10.R14 Muse Spark Open as an OpenCode model (spec only, written Nov 11 (tasks.md 10.40); built after OpenCode and not before Dec 3 (MS5))

The owner asked on Nov 9 to include Meta's Muse Spark Open, subscription or free first, and answered on Nov 11: MS1 to MS4 as proposed in design.md, and MS5 stands (spec only, built after OpenCode). Nothing of this is built before Dec 3. Facts: `adapters/NOTES-layer10.md`, "Muse Spark Open as a platform" (Nov 9; not read again on Nov 11). Design: design.md "Muse Spark Open as an OpenCode model".

User story: as the owner, I want to run Muse Spark Open on my own machine through the same OpenCode front door, with the same gate, and never on a route that bills me by the token.

Acceptance criteria:

1. **A model, not a platform** (MS1): Muse Spark Open is an OpenCode agent, `platform: opencode`, with everything of 10.R13. No new platform name, command word or adapter.
2. **Free first means local** (MS2): one more `provider` value, `umwayi-local`, a custom OpenAI-compatible provider whose URL comes from a new agents.yaml key `base_url`, allowed only for that provider.
   - `base_url` is `http://` or `https://` with a host that is `localhost`, a loopback address, or a private address (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `fc00::/7`), a port, and an optional path; no user, password, query or fragment. Anything else is 64.
   - The provider entry in the inline config enables tool calls for the model and sets the recommended settings: temperature 1.0, top_p 1.0, and an explicit reasoning effort from a new key `reasoning_effort` (`low`, `medium` or `high`, default `medium`). The exact V2 field names are confirmed first (task 10.52); until then the route is refused.
   - `integration.use` allows `umwayi-local` only.
3. **No hosted route** for Muse Spark Open: OpenRouter, Together, Fireworks, Groq, Hugging Face and every other hosted provider are refused like every pay-as-you-go route (10.R13.6). A later paid route waits for the budget governor; OpenRouter's prepaid credits are the first candidate (they fail with 402 instead of billing beyond the balance).
4. **The licence notice** (MS4): when this ships, the README says "Built with Muse Spark Open", only after the owner has read `LICENSE.md` on Hugging Face and said so (task 10.55).
5. **Muse Code** (MS3): a separate platform for the closed Muse Spark under a Muse Code subscription, after Dec 3, with its own spec. Nothing of it is in this requirement.
6. **Tests:** the `base_url` validation (every allowed and refused shape), the inline config for `umwayi-local`, the refusal of each hosted provider, and the 10.R13 chat end to end with a fake `opencode` and `provider: umwayi-local`.

### Out of scope for layer 10 (Dec 3)

- A model client, model keys, or any network call by umwayi.
- Any ACP agent or platform other than Kiro, Claude Code through the pinned `claude-agent-acp` adapter (10.R11) and, once part 8 is approved and built, OpenCode (10.R13): Codex, Gemini CLI and others are refused as not gated.
- Kiro or Claude Code cloud sessions, background sessions, resuming or listing sessions, MCP configuration, model or effort choice. OpenCode's `model` is fixed in agents.yaml (10.R13.2) and cannot be changed during a chat.
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

## Whole-system test and security scan (S.1 and S.2)

Status: approved by the owner on Nov 10 (tasks.md S.0), with S-Q1 to S-Q16 answered as proposed (design.md, "Whole-system test and security scan", "Open questions"). Built Nov 10 to Nov 12, moved up from Nov 23 to Nov 26 (S-Q16): S.1 in one pull request, then S.2 in another. Facts with links: design.md, same section, "Facts".

User story: as the owner, I want one test that drives umwayi the way I use it, through every layer at once, and one recorded scan of umwayi's code, its adapter dependencies and its one network listener, so I know before Dec 3 what holds together, what a scan found and what nothing here can prove.

The two parts follow the rules of every layer: fail closed (a check that cannot run is "not done", never "passed"), every result written down, no secret in any output.

### S.R1 The whole-system test: what it is (S.1)

1. **Real commands, end to end.** Every step runs `python -m umwayi ...` (and the layer 9 hook scripts) as a real child process, in a fresh root, with `HOME`, `XDG_CONFIG_HOME` and `TMPDIR` in a temporary folder. Nothing is imported and called directly, except to read files back.
2. **Fakes only, no network, no account.** The agents are the existing fakes: the fake `claude` (also the fake telemetry sender), the fake `kiro-cli`, the fake `node` with the scripted ACP agent. No real Claude Code, Kiro, Node adapter, systemd, cron or network is used or needed.
3. **Across every layer at once,** in one root: memory, rules, queue, archive, the logbook with its hash chain, jobs and workflows, the AI helpers, the layer 9 hooks of Claude Code, Kiro and stdio, `umwayi agent` (check, run, and chat over cli and ACP), `umwayi schedule`, and `umwayi budget` with the telemetry receiver.
4. **One ordered day, then faults.** A scripted "owner's day" runs the layers in the order the owner uses them and checks the state after each step (S.R2). Each fault scenario of S.R3 starts from the end state of that day, in its own copy of the root, so one fault cannot hide another (proposed, S-Q2).
5. **After every scenario:** `umwayi logbook verify` exits 0 (or, for a tampered logbook, exactly 1 with the expected problem); `umwayi budget status` exits 0 or 2 as the scenario expects; no process the scenario started is still alive; only the exit codes each command may give were seen (0, 1, 2, 3, 64 per its layer; `agent`, `schedule` and `budget` never 1).
6. It includes the open whole-system items of earlier layers: 9.11 (the adapters) and the test part of 10.21 (the front door). The owner's real runs (10.21's real run of each platform, 10.31, 11.6, B.10) stay the owner's and are not part of S.1 (S-Q14).

### S.R2 The owner's day (S.1)

In this order, each step with the entries it must add to the logbook and nothing else:

1. A fresh root: `rules.yaml`, `agents.yaml`, `units.yaml`, `jobs.yaml`, `schedule.yaml` and one workflow, from the example files with the fake paths filled in.
2. Memory bundle, queue add and answer, one archive move and `archive verify`.
3. `umwayi check` for a few actions (Yes, No, Ask me first); `logbook seal --chain --by Owner`; `logbook anchor`.
4. One job run and one workflow run up to its approve step.
5. The layer 9 hooks: one Claude Code, one Kiro and one stdio hook call through the fake agents, each logged through the checked append.
6. `agent check` and `agent run` for Claude Code with a measured telemetry report; `agent run` for Kiro (declared or unknown); a cli chat and an ACP chat for Claude Code and an ACP chat for Kiro, each with one tool call through the hook and one ACP permission request.
7. `schedule validate`, `show`, `install --approved-by Owner`, `check` (installed, not enabled), the rendered `ExecStart=` run once as written, `remove`.
8. `budget status` (the measured, declared and unknown shares match the day), `budget calibrate` (not enough data), `logbook verify --anchor` with the anchor of step 3 shorter than now, and a new anchor that matches.

### S.R3 The fault scenarios (S.1)

Each from the end state of the day, in its own copy:

1. **A tampered logbook,** three ways: a hand edit of an old chained entry with the hash record rewritten (only the chain finds it); a budget settle edited so it no longer matches its shape (released not the reservation minus the reading), re-chained with the record rewritten (only the ledger shape check finds it); the same settle edited consistently (micros, UU and released together), re-chained (nothing but the anchor finds it, KNOWN-LIMITS 115); a truncated tail with the record rewritten (only the anchor finds it). For each: `verify` (1 with the expected problem, or 0 for the re-chained edit), every agent start, `check`, job, workflow, `schedule install` and `budget status` refused as their layer says; `kill on` still turning the switch on (exit 0, with the line that its entry could not be written); `schedule remove` refused with both unit files put back byte for byte, because its entry cannot be written (11.R4.2); and nothing written by any refusal.
2. **A lost reservation:** `umwayi agent run` SIGKILLed while the agent runs; the agent's process group stopped by the test; `budget status` shows the reservation counted in full; a start that no longer fits is refused (3); `settle-lost --by Owner` refuses while another run holds the run lock (3), then settles (0); the next start fits; `verify` 0.
3. **The kill switch in the middle of a run,** for each kind of start: `agent run` (Claude Code and Kiro), the cli chat and the ACP chat (Claude Code and Kiro), and a scheduled job started from its rendered `ExecStart=`. Each is stopped with exit 3 within the watcher's second plus the stop grace, nothing it started is left, the run is settled (measured, or unknown at the worst case), and `kill off` lets the next start go on.
4. **A schedule install with no systemd:** no `systemctl`, `systemd-analyze` or `crontab` on `PATH`, plus a fake `systemctl` first on `PATH` in a second pass that records any call. `install` writes the two files (0644) and prints the commands; `check` says not enabled; the fake `systemctl` was never called; the rendered service run by hand gives the job's entry; `remove` takes the files away.
5. **A limit in the middle of a chat** (B-Q6): an ACP chat passes `per_run` in its second turn; it is stopped with exit 3 and settled as measured.
6. **A crash in umwayi** during each of: an append (crash safety), a reservation, a settle and a schedule install, each through the planted fault hook; the next command recovers or refuses as its layer says, and `verify` ends at 0.

### S.R4 The security scan: what is scanned (S.2)

1. **umwayi's own code** (`umwayi/`, `adapters/*.py`, `adapters/*/hook.py`, `adapters/claude_acp/canary.py`): a static scan with a named tool (S-Q3), and umwayi's own code guards (no shell, no network import except the receiver's, program runners only in `agents.py` and `report.py`), checked again and listed.
2. **Every dependency of any adapter package.** Today that is one: `adapters/claude_acp/package-lock.json` (lockfile version 3, 115 packages, the adapter 0.101.0 and everything below it, including the Claude Agent SDK and its optional platform packages). Each is checked against public advisory databases with named tools (S-Q4), its registry signature is checked where the registry offers one, and every licence is listed (S-Q11). The core package has no dependency (`pyproject.toml`: `dependencies = []`); the scan says so and checks it.
3. **The Python interpreters** umwayi is tested on (3.10 to 3.13): each version is compared with the security releases the Python project lists (S-Q5).
4. **The telemetry receiver** (S.R5), **file modes** (S.R6), **links and paths** (S.R7) and **secrets in outputs** (S.R8), each with tests that run umwayi as a real child process.

### S.R5 The telemetry receiver (S.2)

1. **Loopback only:** it binds 127.0.0.1 and nothing else (the socket's own address read back, and a connect to every other address of the machine refused); a peer that is not loopback is refused even if it could reach it.
2. **The run header:** missing, wrong, a prefix of the secret, the secret plus one character, another run's secret, the header given twice, and a header name in another case; only the exact secret is accepted. The secret never appears in any output, entry or capture file.
3. **The size caps:** a body of exactly 1 MB is read, 1 MB plus one byte is 413 and not read; the 16 MB run total; a `Content-Length` larger than the body sent; a body larger than its `Content-Length`; chunked transfer; a compressed body.
4. **A slow client:** headers sent one byte at a time with pauses shorter than the 5 s socket timeout, and a body sent the same way. Required: no single connection holds the receiver past a fixed whole-request deadline, and the agent's run, its stop and its settle are not delayed by it (S-Q6).
5. **Many connections:** at least 200 connections opened at once and held open, from the agent's side. Required: the receiver does not start an unbounded number of threads, the run's own reports still count, and umwayi's memory and thread count stay bounded (S-Q7).
6. **After the run:** the port is closed when umwayi exits, on every way out (a normal end, the kill switch, SIGTERM, a crash).
7. Each case is a test. A case that shows a defect is fixed in S.2 with its test first (S-Q6, S-Q7), or, if the owner decides so, written into KNOWN-LIMITS.

### S.R6 File modes (S.2)

1. Every file and folder umwayi creates is listed with its mode under a umask of 022 and of 077: `LOGBOOK.md`, `.umwayi/` and everything in it (the hash record, the lock, the intent, `KILL`, the run lock), `queue.md`, the archive, drafts and the outbox, the systemd unit files, the canary folder, the telemetry capture file.
2. Proposed rule (S-Q9): a file or folder that can hold a secret or an approval-like token (the canary folder, the capture file, the intent while it holds an entry) is 0600 or 0700 whatever the umask; the unit files are exactly 0644; everything else follows the owner's umask. A test checks each.
3. umwayi never runs `chmod` on a file it did not create, and never widens a mode.

### S.R7 Links and paths (S.2)

1. For every file umwayi reads or writes, a test plants a symbolic link (to a file outside the root, to `/dev/zero`, to a folder) and a hard link where it matters, and a folder where a file is expected. Each is refused or handled as its layer says, never followed to write outside the root.
2. Every path umwayi takes from a user file or argument (`--root`, `--agents`, `--file`, `--prompt-file`, jobs files, workflow names, archive targets, `workdir`, `UMWAYI_TELEMETRY_CAPTURE`) gets `..`, an absolute path where a relative one is expected and the reverse, a name with a newline, a very long path, and a non-UTF-8 name.
3. A race (the file replaced by a link between the check and the open) is tested where umwayi opens with `O_NOFOLLOW` or `O_EXCL`, and listed as a known limit where it does not.

### S.R8 Secrets in any output or logbook entry (S.2)

1. Planted secrets in every place one can enter: the prompt (`--prompt`, `--prompt-file`, stdin), every environment variable a credential could be in (10.R12.6, `KIRO_API_KEY`, the owner's `OTEL_EXPORTER_OTLP_HEADERS`), file contents (memory, rules, the queue, an article, a jobs file, a unit file), tool inputs through the hooks, ACP messages, telemetry bodies (prompt and response attributes), the fakes' own output (`auth status` with an email), and error text from a planted crash.
2. After the day and every fault scenario, the scan searches every byte umwayi wrote or printed: stdout and stderr of every command, the logbook, the queue, drafts, the outbox, the archive index, `.umwayi/`, the unit files and the capture file. No planted secret, run header secret or canary token may appear, except where a layer says so on purpose (the prompt in a draft the owner asked for, if any; listed).
3. What umwayi cannot keep secret is listed, not hidden: the prompt in the process list for `--prompt` and for Claude Code (KNOWN-LIMITS 35, 44), the run secret in the agent's environment (KNOWN-LIMITS 110), the journal of a scheduled run.

### S.R9 Results and fail closed

1. The results are under `docs/`: one file, `docs/SECURITY-SCAN.md` (S-Q12), linked from `docs/security.md` and from the README's security row (tasks.md D.1, S.2.7): the date, each tool with its version, where it came from and how it was checked, the exact command, what it scanned, its result (or "not run" and why), each finding with its decision (fixed in PR N, accepted as KNOWN-LIMITS N, or false positive with the reason), and what the scan cannot prove (S.R10).
2. **Fail closed:** a scan that could not run (no network for an advisory database, a tool that would not install) is recorded as not run, never as a pass. A finding nobody decided on blocks the freeze (proposed, S-Q8).
3. **No new runtime dependency.** The scan tools are never a dependency of `umwayi` or of an adapter, are never committed, and run from a throwaway environment outside the repo (S-Q3, S-Q4). The CI workflow is not changed for Dec 3 (proposed, S-Q13).
4. S.1 and S.2 add tests to the normal suite (`python -m unittest discover -s tests -t .`), which still needs no network and no third party package. The scan commands themselves are not tests.

### S.R10 What the scan cannot prove (written into SECURITY-SCAN.md and KNOWN-LIMITS)

1. That there is no vulnerability: a static scan finds known patterns, an advisory scan finds known advisories for the exact versions in the lockfile, and both say nothing about defects nobody has reported.
2. Anything about code it cannot see: the prebuilt programs inside the Claude Agent SDK's platform packages, the real Claude Code and Kiro programs, the owner's Node and Python builds, and the operating system.
3. That a pinned version is honest: lockfile integrity hashes and registry signatures prove the files are the ones published, not that what was published is safe.
4. Anything against a process of the same user. umwayi, its agents and the owner's other programs run as one user; such a process can read the agent's environment (the run secret), write the logbook and its record, change unit files, or send telemetry. The chain, the anchor and the kill switch make some of this visible; none of it is prevented (the boundary of every layer, S-Q10).
5. What the real platforms do: the fakes follow the docs, and every place where the docs are silent (NOTES files) stays unproven until the owner's real runs.
6. That the tests are complete: mutation checks show the tests catch the faults that were tried, not every fault.

## Layer 12: Web interface (the view)

Status: in scope before Dec 3 (the owner, Nov 10; it was a non goal until then). **Changed by the owner on Nov 11 (UI-Q12 to UI-Q16):** the scene is the Kenyan highlands at dusk, drawn to look like real life; the eleven stations are natural features scattered by how closely each works with the shepherd; the scene is also the hero of the umwayi-os home page (12.R12 to 12.R15). PR 39 is reworked on that brief. **Changed again by the owner on Nov 11, round 2 (UI-Q17 to UI-Q22):** three tiers chosen by a device query with a visible switch (12.R16); two parts, a public site in Next.js on Vercel and the owner's live view that stays one static file, sharing one scene module (12.R17, 12.R18); fixes to the Standard scene and the home page layout (12.R19); a forest, flowing water, a Maasai shepherd and real looking animals (12.R20); the owner keeps the timeline and no scope is cut (design.md, "Hours and schedule effect"). Requirements 12.R1 to 12.R11, design.md "Layer 12" and tasks.md UI.0 to UI.5 are written in the UI.0 pull request and wait for the owner's approval; nothing is built. The owner's answers UI-Q1 to UI-Q5 are recorded (design.md, "Open questions for the owner (layer 12)"); UI-Q6 to UI-Q11 are open, each with a proposed answer. The owner's first design reference (a 3D shepherd hillside in three.js with eleven stations) was a starting point; the Nov 11 brief replaces its look. Facts with links, and the owner's interface check: `adapters/NOTES-layer12.md`.

User story: as the owner, I want to see the state of umwayi-os as a calm place I can look at, with real counts from my own root, and one panel that lists the real tests only I can run, so that I can tell at a glance what is open, what is stopped and what I still have to check, without the page being able to change anything.

The view only looks. It reads one file of counts, and it keeps notes the owner types into the page. It never writes to the repo, runs a command or calls a network (product.md rule 10).

### 12.R1 Where it lives and how it is built (UI-Q1, UI-Q2)

1. All of the interface is in a new top level folder `ui/`, outside the `umwayi` package. The one change to the core is the read only command `umwayi view snapshot` (12.R4). The core package stays standard library only (CC-7); no module of `umwayi/` imports anything from `ui/`, and `ui/` imports nothing from `umwayi/`.
2. `ui/package.json` has two dependencies, both with an exact version and no `^`, `~` or range: `three` **0.187.0** and `esbuild` **0.28.2**. `ui/package-lock.json` is committed; every package in it has a `sha512` integrity hash and comes from registry.npmjs.org, as for `adapters/claude_acp/`. `node_modules/` is never committed.
3. The owner installs with `npm ci --ignore-scripts` and builds with the command in `ui/README.md`. **umwayi never runs npm, node or a browser.** No test of the normal suite runs npm or needs it.
4. The build writes one self contained page, `ui/dist/index.html` (script, styles and every texture inline), and `ui/dist/build.json` (the SHA-256 of every file in `ui/src/`, of `ui/package-lock.json` and of `index.html`). **The built page is committed.** The repo's `.gitignore` ignores `dist/` and `build/`, so it gets an exception for `ui/dist/`.
5. The page needs no server: it works when opened from disk (`file://`).
6. **The page stays under about 2 MB** (script, styles and everything else inline). No photograph, texture file or model is embedded or downloaded: all realism is generated in code (12.R12).
7. **Since Nov 11, round 2 (UI-Q18):** the public site is a second top level folder `site/`, also outside the `umwayi` package, with its own pinned `package.json` and lockfile (12.R17). The scene code lives once, in `ui/`, as a module both the owner's page and the site use (12.R18). Points 1 to 6 stay the rules of `ui/` and of the owner's live view.

### 12.R2 The page makes no request, writes nothing and runs nothing (UI-Q2, UI-Q5)

This is the rule of **the owner's live view** (12.R18), unchanged. The public site (12.R17) is allowed one more thing only: it may fetch its own assets from its own host. Everything else in this section holds for the site too (no analytics, no storage, no third party address loaded).

1. The built page makes **no network request** of any kind: no CDN, no web font, no analytics, no `fetch`, `XMLHttpRequest`, WebSocket, beacon, image, stylesheet or script loaded from anywhere but the page itself. All fonts are system fonts.
2. The page writes nothing to the repo and nothing to any storage: no `localStorage`, `sessionStorage`, cookie or IndexedDB. Typed notes live in the page's memory only and are lost when the page closes (12.R7). The page cannot run a command or start a program.
3. The one way data gets in is a file the owner picks (12.R4.9). The page validates it as untrusted input (12.R9).
   The home page (12.R15) has plain links. A link is an anchor the owner clicks; the page itself makes no request, and nothing is prefetched. The only web addresses in the page are the XML namespace name three.js carries and the exact addresses of those links and of the install command (the repo and its docs folder); a test lists them.
4. Nothing from a snapshot or from the owner's notes is put into the page as HTML. Text is set as text, never as markup.
5. **A second lock on the same door.** The page carries a Content-Security-Policy `<meta>` tag that denies everything (`default-src 'none'`) except its own inline script and style, allowed by hash, and images from `data:`. Even if a request were written by mistake, the browser would refuse it. The page loads no texture, image or model file: textures are made in code or inlined as data, and none of three.js's file loaders (`FileLoader`, `ImageLoader`, `TextureLoader`) is bundled.

### 12.R3 The eleven stations: natural features, not buildings

1. The scene has a lantern at the centre (12.R13.3) and eleven stations around it. A station is a **natural feature of the land**, not a podium, and not a building with a sign or a board. **There are no podiums, no paths and no label boards.** Each station acts out one function of umwayi-os as a set of still poses and the short moves between them (12.R5.8), and is one module of `ui/src/stations/`.
2. The mapping (UI-Q13):

   | station | feature |
   | --- | --- |
   | Memory | a spring pool |
   | Rules | a drystone wall with gates |
   | Queue | a sheepfold |
   | Archive | a cave in a rock face |
   | Logbook | a standing stone with growth rings |
   | Automation | a river with a water wheel |
   | AI helpers | a sheepdog and a herd |
   | Workflows | a stream through connected pools |
   | Adapters | a ford or a bridge over the river |
   | Kill switch | a lone gate and latch with a red lamp |
   | Budget | a rain water tank with a level |

3. **Names appear only on hover or keyboard focus** (and in the list view and the panel). At rest nothing in the picture is written. Each feature still has a real `<button>` over it, so a screen reader and the keyboard reach all eleven (12.R6.1). A hover or focus brings the name up with a short ease and lifts a little warm light on the feature; both ease away.
4. Words are the product's words: rules, queue, archive, logbook, AI helper, Yes, No, Ask me first, kill switch. Short sentences, no em dashes.
5. Each station has a name, a state (built or planned), two short lines, the command that belongs to it and, when a snapshot is loaded, the counts of 12.R4 that belong to it. Stations and layers: Memory 1, Rules 2, Queue 3, Archive 4, Logbook 5, Automation 6 and 11 (jobs and scheduled runs), AI helpers 7, Workflows 8, Adapters 9 and 10 (the hooks and the front door), Kill switch 8, Budget the budget governor.
6. **A planned part is never shown as built.** Budget is built (PR 33); the panel says that B.10, the owner's capture, is not done. The `planned` state stays in the code (a dim, unlit version of the feature) and no station has it today (12.R8).
7. Red, mint and amber carry meaning only at Rules (the three answers), Kill switch (a red lamp when on) and Logbook (a broken chain, 12.R4.4). Everywhere else warm light is light, not a signal. The lantern's warm light is the brightest point of the picture.
8. Without a loaded snapshot the page shows a sample world and says "sample" in a small label. Sample and real counts are never mixed in one scene.
9. Counts drive the scene as follows. Queue: sheep waiting at the fold for open rows, stones in a cairn for answered. Rules: small lamps on the wall by verdict. Logbook: beads round the stone for chain length. Kill switch: the gate shut and the lamp lit for on and for unknown. Automation: lit spokes of the wheel for the schedules. Budget: the water level for today against the last seven days. Memory, Archive, Workflows, AI helpers and Adapters show no count today, because the snapshot has none for them.

### 12.R4 `umwayi view snapshot` (UI-Q3)

User story: as the owner, I want one command that writes the counts the page needs and nothing else, so the page can show my real state without ever reading my files.

```
umwayi view snapshot [--out PATH] [--date D]    read the counts, write one JSON file and one logbook entry
```

1. **Read only.** It changes nothing in any layer: not the queue, the rules, the archive, a draft, a unit file, the kill switch or the budget. It writes exactly two things: the snapshot file and one logbook entry. It calls no program and makes no network call. `umwayi/view.py` imports only the standard library and none of `subprocess`, `socket`, `urllib`, `http`, `ctypes`.
2. **Counts only.** The file holds integers, booleans, one of the fixed words below and dates made by umwayi. **No text from any file** (no title, answer, recommendation, rule id or text, schedule or job name, archive pointer, memory line, prompt or logbook line), **no path of any kind and no secret.** The file has these fields and no other:

   ```
   {
     "schema": 1,
     "date": "2026-11-10",
     "queue":       {"open": 3, "answered": 12},
     "rules":       {"yes": 7, "no": 6, "ask": 2},
     "logbook":     {"entries": 312, "chain_length": 280},
     "budget":      {"days": [{"date": "2026-11-04", "used_uu": 0}, {"date": "2026-11-05", "used_uu": 12}, ...]},
     "kill_switch": "off",
     "schedule":    {"entries": 3, "installed": 1, "enabled": 0}
   }
   ```

   - `queue`: rows with status open and with status answered in `queue.md`.
   - `rules`: rules in `rules.yaml` by verdict (`yes`, `no`, `ask`).
   - `logbook`: entries in `LOGBOOK.md`, and how many of them are in the hash chain (`chain_length` is 0 before the chain starts).
   - `budget.days`: always seven entries, oldest first, the last one is `date`; UU used on each of those logbook days, the same number `umwayi budget status` shows as used (settled plus reserved in full), as whole numbers.
   - `kill_switch`: `on`, `off` or `unknown` (a state umwayi cannot tell is `unknown`, and the page treats it as on).
   - `schedule`: entries in `schedule.yaml`, how many are installed exactly as umwayi would write them, and how many have their timer enabled (the same read as `umwayi schedule check`; nothing is run).
3. A part that cannot be read (a missing or broken `rules.yaml`, a malformed `queue.md`, a `schedule.yaml` that fails validation) is `null`, never zero and never a guess. The page shows `null` as unknown. A `schedule.yaml` that does not exist is 0 entries, not `null`. Every integer is whole, from 0 to 1000000000.
4. **The tamper check runs first.** The command checks the logbook as every writer does (the whole-file hash and the hash chain, `read_checked`). If the logbook is broken it exits **1**, prints which check failed (never a line's text), and **writes nothing**: no snapshot and no entry. Whether a broken logbook should instead produce a snapshot that says so is open (UI-Q6).
5. **One logbook entry** through the checked append, after the file is written: the source `umwayi view snapshot`, the file's name inside the root, its SHA-256 and the date. Not its content. If the entry cannot be written, the file is put back as it was (or removed if it was new) and the exit is 2.
6. **The file.** The default is `.umwayi/snapshot.json` in the root. `--out PATH` must stay inside the root, end in `.json`, be at most 1024 characters and have no `..` part. It is written through the shared atomic writer. It replaces only a regular file that was written by this command earlier (it parses and has exactly the fields above) or a path that does not exist. A link, a folder, a hard linked file or any other existing file is refused (64), so `--out rules.yaml` can never overwrite anything. The mode is 0600 whatever the umask (the owner's instruction for UI.2, Nov 11: it holds counts only, but a private file is the safer default, and the page reads it as the same user; this replaces "follows the owner's umask"). `.umwayi/snapshot.json` is added to `.gitignore`.
7. Same input, same bytes: the file has fixed key order, two spaces of indent and a final newline. `--date D` sets `date` and the end of the seven days, as for every command.
8. **Exit codes: 0 done, 1 the tamper check failed (nothing changed), 64 a usage or config error** (a bad `--out`, a bad `--date`, a file that is not ours). An unexpected error exits **2**, never 0, 1 or 3 (rule 8). It never exits 3: it asks the rules nothing and is not stopped by the kill switch, because it starts no run and the owner needs it most when the switch is on. Messages never print file contents.
9. **How the page reads it.** The owner picks the file in the page with a file picker (or drops it). The page reads it in the browser with `FileReader`, so it makes no request (UI-Q7).
10. The snapshot is only as fresh as the last command. The page shows the snapshot's `date` next to the scene, and says "sample" when there is none.

### 12.R5 Calm by default (UI-Q4)

1. **Nothing flashes or blinks.** No element changes brightness or colour in a repeating way, and nothing pulses, flickers or strobes, at any speed. The rule is stricter than the WCAG limit of three flashes a second.
2. **No autoplay.** With no input the scene is a still picture: after the first frame is drawn, the page draws nothing more and uses no animation frame. (Wind in the grass, drifting mist, fireflies, a sky that moves and sheep that walk by themselves are all gone.) **Changed by the owner on Nov 11, round 2 (UI-Q21):** the river's water flows by itself (12.R20.2) and, in High only, distant birds fly (12.R20.5). These are the only things that move without input. They stop with reduced motion, in Calm mode and while the scene is off screen or the page is hidden; the rest of this section holds.
3. **Motion only after a click or a cursor move, and it eases to rest.** A selection (click, tap, key or label) flies the camera to the station and plays that station's short action once. A cursor move gives a small slow parallax. Every motion uses an ease out curve, ends in a finished state within 3 seconds of the last input (5 seconds in calm mode), and then the page draws nothing again. "Replay" in the panel plays the station's action once more.
4. **`prefers-reduced-motion: reduce` switches off all movement and shows still frames.** No camera flight (the camera jumps), no parallax and no tween. Each station's action is a short list of still poses (for Rules: Yes, No, Ask me first), and the panel steps through them with Previous and Next buttons. The setting is read at start and when it changes while the page is open.
5. **A visible calm mode toggle** (a real button, labelled "Calm mode", reachable by keyboard, in the top bar). Calm mode lowers contrast and brightness of the scene, glow and lines, slows the easing, and hides the sky arcs. Its start state and a floor for text contrast are open (UI-Q9).
6. **Dark, low brightness colours and no large pure white area.** The palette is the nightwatch palette of design.md. In the overview, at 1440 by 900 and at 390 by 844, in normal and in calm mode: the mean luminance of the picture is at most 0.20; no connected area of more than 0.5 percent of the picture has all three channels at 240 or more; the page background is never white. Bloom is capped so a lantern does not wash out. These numbers are proposed; UI.1 may tighten them after the owner sees the screenshots, never loosen them.
7. **Clean and less congested.** Smooth, soft lit, anti-aliased, no pixelation, dither or scan lines, and few things on screen. At rest the overview shows **no label at all**, only the picture and the top bar; a name shows for the hovered or focused feature only (12.R3.3). Trails of light (12.R13.5) are drawn only for the selected, hovered or focused station and the stations it works with. There is no constellation, aurora, firefly or circuit pulse, and nothing in the scene moves by itself: no wind, no swaying grass, no drifting cloud (flowing water and, in High, distant birds are the owner's exceptions of Nov 11, round 2; 12.R5.2). Since round 2 the trails are drawn faintly at rest from the default view (12.R19.4).
8. The same station logic serves all of this: a station is a set of poses and the short moves between them (12.R3.1), so a click plays the moves and reduced motion shows the poses.

### 12.R6 Access

1. Every station has a real `<button>` placed over its feature, with the station's name. Tab reaches all eleven in the order of the list view; arrow keys move between stations, Enter or Space selects, Esc returns to the overview, and the focus is always visible (the name appears on focus). The panel is a landmark with a heading; opening it moves focus into it and closing it returns focus to the button.
2. **A list view** of the eleven stations (a plain `<ul>` with the same words, the same counts and the same state) is reachable from a link in the top bar, and is shown automatically when WebGL is missing or fails (UI-Q8). **Since Nov 11, round 2 (UI-Q17):** the list view is tier 1, not a mode of the scene page: the tier switch of 12.R16.3 replaces the List view button, and tier 1 is also what shows with no JavaScript. The page works completely, with the home content and the checks panel, without WebGL.
3. Text contrast is at least 4.5 to 1 against what is behind it in normal mode (the glass panel and labels included) and not below the floor of UI-Q9 in calm mode.
4. The phone layout at 390 pixels: the panel is a bottom sheet, the labels do not overlap, and the page holds at least 30 frames a second while moving on an integrated GPU at 1440 by 900 (it lowers the pixel ratio when it does not).
5. The page has a `lang`, a title, and a text alternative that says in words what the scene shows and where the list view is.

### 12.R7 The owner checks panel (UI-Q5)

1. A panel in the page, opened from the top bar and from the list view, lists the physical tests only the owner can run, in this order: **10.21** (one real run of each platform), **10.31** (the first real Claude Code ACP chat and the real Kiro login), **11.6** (the real systemd check), **B.10** (the capture of one real Claude Code telemetry export), **10.37** (the real field names of `auth status --json`, steps B1 to B3 of the 10.31 run) and the **interface check** (the owner's check of this page, `adapters/NOTES-layer12.md`, tasks.md UI.5).
2. Each check shows: its id and name, why it is open, its steps in order with the exact command in a code block, what to expect, and what to record. Each step has a checkbox and a text field for the result. The steps are the ones in the NOTES file named for the check (`adapters/NOTES-layer10.md`, `adapters/NOTES-layer11.md`, `adapters/NOTES-layer12.md`); every command in the page is found word for word in its NOTES file (a test checks this).
3. **The page cannot tell whether a check passed.** A check is "not done" until the owner ticks every step, and then it says "ticked by you", never "passed" or "verified". Nothing here is ever shown as done by default.
4. **Results stay in the page.** Ticks and typed results are kept in the page's memory only (12.R2.2), and the panel says so: "These notes are lost when you close this page. Export them first."
5. **Export as text.** One button writes all checks, with their steps, ticks and results, as plain text into a text area (selected for copying), with a Copy button and a Download button (the browser saves a `.txt`; the owner chooses where). The text ends with the line "These are your notes. umwayi did not run or verify anything." The export is made in the browser; nothing is sent.
6. The panel reminds the owner of the NOTES rule: record field names, exit codes and version strings, never a value. A result field that looks like a value (an email, a URL, a long token-like string) is marked with a warning; the export still works.
7. **The interface never writes to the repo, runs a command or calls a network** while doing this. The commands in the panel are text for the owner to type.

### 12.R8 A liberal society view, for later (design only; nothing of layer 13 is built)

1. Layer 13 has no requirements yet. This requirement only makes sure the view can take it later without a rewrite, and builds none of it.
2. The owner named three things the view should show once layer 13 exists: **review dates, reopened decisions and petitions**. Each would be a station, drawn only when layer 13 is built and a snapshot carries its counts. Until then no such station, ghost or label exists in the page or in the list view.
3. The extension points built now, and only these: the stations are a list of modules registered in one file; the ring layout takes any number of stations (a test lays out 14 fake ones with no overlapping label); the snapshot is versioned (`schema`), and the page accepts only schema numbers it knows; and a station has a state, built or planned.
4. The shape proposed for a later schema 2 is in design.md ("A liberal society view, for later"). It keeps the rules of 12.R4: counts and dates only, never a title, a name or the text of a petition.
5. Whether and how these stations are drawn is decided when the layer 13 spec exists (UI-Q11).

### 12.R9 Fail closed

1. The page treats the snapshot as untrusted. The file must be at most 4 KB and parse as JSON; it must have exactly the fields of 12.R4 with the right types, no extra field, and every number whole and in range. Otherwise the page shows "This file is not a snapshot of this version" and loads nothing; it never shows a partly checked file.
2. A `null`, an unknown `kill_switch` word or a missing part is drawn as unknown. Unknown is never drawn as zero or as fine.
3. Any error in the page's own code shows a plain message and the list view. It never shows a blank page, and never invents a count.
4. `umwayi view snapshot` follows 12.R4.8: any unexpected error exits 2 and leaves no half written file; the error text never holds file contents.

### 12.R12 The look: real life, generated, light enough (UI-Q12)

1. **Imagery resembles real life, with more detail, not less**: leaning photoreal. In tiers 1 and 2 (12.R16) everything is generated in code (tier 3 may load asset files from the public site's own host, 12.R16.4): terrain from noise, light from physical lights and a sky made for the scene, surfaces from procedural noise (bump, colour variation, strata), plants from instanced shapes. **No photograph, no texture file, no model file, no downloaded image, no font.** The page stays under about 2 MB (12.R1.6).
2. The picture has relief (rolling hills with real height, a river valley), a sky with soft cloud and a low warm glow, long shadows, aerial haze that softens the distance, water that reflects the sky, and surfaces with grain: grass, rock, soil, wood, wool, iron. Filmic tone mapping and a capped bloom (the lantern only) finish the picture.
3. **An automatic lower detail mode for weak machines.** The page starts in high or low detail from what it can tell (software rendering, few processor cores, little memory) and steps down at run time after sustained slow frames: first a lower pixel ratio, then no bloom and no multisampling (two steps; a third, no shadows and fewer plants, was cut by the owner on Nov 11). The low mode keeps the same scene, the same stations and the same rules of 12.R5. The address `#detail=high` or `#detail=low` forces a mode (for tests and for the owner).
4. Calm mode, reduced motion, text contrast of 4.5 to 1, no large white area and the dark, low brightness picture of 12.R5 all hold in the real life look. Realism never means bright: dusk, low light, the lantern as the one bright point.

### 12.R13 The place and the layout (UI-Q13, UI-Q14)

1. **The place is the Kenyan highlands at dusk**: rolling hills with real height, a river valley, umbrella thorn acacia and African pencil cedar, grass and rock, **Mount Kenya on the horizon** (two jagged peaks, Batian and Nelion, with snow holding the last light), low warm light.
2. The land is one function of position, `heightAt(x, z)`, shared by the ground, the plants and the stations, so everything stands on the same ground.
3. **The centre** is a **hanging lantern on a shepherd's staff**, held by a plain silhouette shepherd figure with a dog beside. It is the brightest point of the picture and the origin of the layout.
4. **Not a circle, no even angles.** The eleven stations are scattered on different ground (hillsides, the valley floor, the river bank), some close to the lantern and some far, **by how closely each works with the shepherd**. The default distances and bearings are fixed in the design (a seeded layout) and in `ui/src/world/layout.js`. No two stations overlap at any distance they can reach (12.R14), and all eleven are reachable by keyboard.
5. **Connections**: streams and trails of light link the stations that work together. There are no drawn paths. A trail is a row of small soft lights that follows the ground between two stations. Trails are shown for the selected, hovered or focused station only, ease in and out, and are hidden in Calm mode. **Changed on Nov 11, round 2 (UI-Q20):** every trail between related stations is drawn faintly and still at rest so it is clearly visible from the default view; the trails of the station in focus are brighter; Calm mode draws them fainter, not hidden (12.R19.4).
6. The camera shows the whole scene in the overview, low enough to show the horizon with Mount Kenya. Selecting a station flies to a view from the lantern side, with the station in the left third (the top third on a phone).

### 12.R14 Distance follows need (UI-Q15)

1. **When a snapshot is loaded (UI.3), a station moves closer to the lantern when it needs the owner now and drifts out when it is quiet.** Needs are numbers from 0 (quiet) to 1 (needs the owner now); examples: open queue items, an Ask me first, a budget warning, the kill switch on.
2. **The position function is built in UI.1 and takes only numbers**: `stationPositions(needs)` gives every station's ground position. UI.3 only feeds it the numbers made from the snapshot. A station without a need is at its default distance.
3. The distance is `d0 * (1.2 - 0.5 * need)`, so a need of 0.4 gives the default `d0`, a need of 1 gives 0.7 of it and a need of 0 gives 1.2. A station on the river moves along the river towards the point nearest the lantern instead. No two stations overlap: the function pushes them apart, the same way every time, and never closer to the lantern than the shepherd's own space.
4. The move is slow and eased: the stations ease from where they are to where they should be, ending within **3 seconds** (5 seconds in Calm mode), and a new set of needs in the middle of a move starts from where the stations are. **With reduced motion the stations jump** to their places. At rest nothing moves.
5. A need that is missing, not a number or outside 0 to 1 is taken as the default need (0.4), never as 0 or 1, so a bad file cannot make the picture jump about.

### 12.R15 The home page: one page, two modes (UI-Q16)

1. **This scene is the hero of the umwayi-os home page.** One page, two modes: a visitor sees the **sample world** with the home content; loading a snapshot (UI.3) makes the same page **the owner's live view**. **Changed on Nov 11, round 2 (UI-Q18, UI-Q19):** the visitor's home page is the public site (12.R17), rendered by the server; the owner's live view is the static page of `ui/` (12.R18). Both show the same home content and the same scene; only the live view loads a snapshot.
2. **Home content**, over and below the scene, in the product's words and short sentences:
   - the **title** and a **one line promise**;
   - a **status strip**: kill switch, budget used, queue open, logbook chain. Each shows the sample value with the word "sample" until a snapshot is loaded, then the real value with its date;
   - **install and first commands** with a **Copy** button for each: the clone and install lines and a few first commands (`umwayi memory bundle`, `umwayi queue add`, `umwayi check`, `umwayi logbook verify`). A copy writes to the clipboard **only on the click**; there is no network;
   - **links**: the repo, the docs, the Devpost page and the demo video. The Devpost and demo video addresses are **placeholders marked "link to come"** until the owner supplies them. A link is a plain anchor the owner clicks; the page itself makes no request.
3. The content has the same dark palette, the same 4.5 to 1 text contrast in normal and Calm mode, works without WebGL, and does not need the scene to read.
4. The home content never shows a planned part as built and never shows a sample value without the word "sample".

### 12.R16 Three tiers, chosen by a device query, with a switch (UI-Q17)

1. **Tier 1, List**: the plain list of the eleven stations with the full home content. It is for a slow network, no WebGL or no JavaScript. It is plain HTML that reads and works with no script at all.
2. **Tier 2, Standard**: the scene of 12.R12 to 12.R15, light on data (about 1 to 2 MB), with the fixes of 12.R19 and the additions of 12.R20. Its lower detail mode (12.R12.3) still works inside the tier.
3. **Tier 3, High**: much closer to photographic, with heavier assets, only for a fast network and a capable GPU. Wildlife at the edge of the scene is in High only (12.R20.5).
4. Tier 3 may load texture and model files from the public site's own host. Each file has its source and licence recorded in `adapters/NOTES-layer12.md` (free licences only, CC0 preferred). No file is loaded from any other host. The Standard scene draws first, so the page is never blank while High loads, and High falls back to Standard if a file fails.
5. **The device query** runs in the browser only. It reads what the browser offers: the processor cores (`navigator.hardwareConcurrency`), the device memory (`navigator.deviceMemory`, where present), the Network Information API (`navigator.connection`: effective type, downlink, Save-Data, where present), the GPU renderer hint (`WEBGL_debug_renderer_info`, where present), the screen size, `prefers-reduced-motion` and WebGL itself. **These hints are never sent anywhere**, never stored and never written to the address.
6. **The choice is one pure function**, `chooseTier(env, options)`, tested first (12.R10.4):
   - no WebGL, Save-Data on, or an effective type of `slow-2g` or `2g` gives List;
   - High only when every needed hint is known and good: an effective type of `4g` with a downlink of at least 10 Mbit/s, at least 8 cores, at least 8 GB of memory where it is reported, a renderer that is not a software one, a screen whose shorter side is at least 720 CSS pixels, no reduced motion and no Save-Data. A browser without the Network Information API (Safari, Firefox) gets Standard and can choose High with the switch;
   - otherwise Standard;
   - the owner's live view passes a highest tier of Standard and ignores the network (it is a file on disk).
7. **A visible switch** in the top bar (real buttons, keyboard reachable) shows the tier in use and lets the owner choose another: List, Standard and, on the public site, High. The choice is kept only in the address fragment (`#tier=list`, `#tier=standard`, `#tier=high`), which a browser never sends to a server. A choice of Standard or High with no WebGL shows List and says why in words. Choosing High where the query chose less works and says in words that it may be slow.

### 12.R17 The public site (UI-Q18)

1. **A new public site in `site/`**, a Next.js app with exact versions and a committed lockfile (as 12.R1.2), deployed on the Vercel free tier (Hobby). It is not part of the `umwayi` package; umwayi never runs npm, node or the site.
2. **No analytics and no tracking**: no analytics or speed insights package, no cookie, no storage, no third party script, font or image, no fingerprinting. Next.js telemetry is switched off for the build (`NEXT_TELEMETRY_DISABLED=1`). The device hints of 12.R16.5 never leave the browser.
3. **The server renders the home text** (title, promise, status strip marked sample, install and first commands, links) and the tier 1 list, so they show at once and work without JavaScript. The Copy buttons need JavaScript and are hidden without it; the commands stay as selectable text.
4. The server cannot draw the 3D. **The 3D draws in the browser** from the shared scene module (12.R18.3), for the tier the browser chose. The site fetches the scene script and tier 3 assets **from its own host only**; it makes no other request.
5. The site sends a Content-Security-Policy that allows its own origin only (`default-src 'self'`, no remote script, style, image, font or connection), and the security headers of the design.
6. The site shows sample counts until a visitor opens a snapshot file of their own with the file picker or by dropping it. The file is read in the browser (12.R4.9, 12.R9.1), is never sent, stored or uploaded, and no request carries it. The site never receives the owner's snapshot. (Changed in UI.3 by the owner's task of Nov 11: before it said the site never reads a snapshot.) **Changed on Nov 12 2026 by the owner (W6, approved):** the rule for the page is no longer "the interface only looks" but "the page may send the same request the command line would, to a local backend" (product.md rule 10). That page is the owner's live view when `umwayi serve` serves it from 127.0.0.1 (W6.R2). The public site is not that page: it sends nothing to a backend, local or deployed, its Content-Security-Policy stays `default-src 'self'`, and a visitor's file still never leaves the browser. A login for a deployed interface (W7) is a later decision and never opens the local backend to the internet (W6.R12). 12.R2, 12.R11 and the sentence of "The view only looks" above are read with this change from the day `umwayi serve` is built (W6.R2.6); until then nothing in the page changes.

### 12.R18 The owner's live view stays static, and the scene is shared (UI-Q19)

1. **The owner's live view is the static one file page of `ui/dist/index.html`**: no network request, the Content-Security-Policy of 12.R2.5 with `default-src 'none'`, loaded from disk, the tier 2 look, a snapshot through the file picker (UI.3). Everything in 12.R1 and 12.R2 holds for it.
2. It offers List and Standard on its switch, not High (High needs files from a host).
3. **The scene code is one module** in `ui/` that both the live view and the site use: one entry that builds the scene on a canvas for a given tier and returns the controls (select, overview, calm, reduced motion, needs). The live view bundles it into its one file; the site imports the same source. A test checks both use the same module (no copy).
4. umwayi still never runs npm or node; the owner builds both.

### 12.R19 Fixes to the Standard scene and the home page layout (UI-Q20)

1. **The rest of the page is visibly present at the bottom of the first screen**: at 1440 by 900 and 390 by 844 the top of the status strip shows above the bottom edge of the first screen, with a still cue that there is more below. The scene never covers it.
2. **The list view is tier 1** (12.R16.1), not a button of the scene page.
3. **The outer stations are further out**, so some are really far: at least three stations stand at 30 m or more from the lantern at their default places. The overview shows all eleven on a wide screen; on a phone it shows the near ones large enough to read, and the far ones are at its edges or just beyond, reached with Next station or a drag.
4. **The river and the trails of light are clearly visible from the default view**: the overview shows a long reach of the river, and every trail between related stations is drawn faintly and still at rest (brighter for the station in focus, fainter in Calm mode).
5. **No name pill covers the hero text** (the title and the promise) at either size, on hover, focus or selection.
6. **Rocks, walls and ground look less like low poly forms**: rocks are irregular, displaced shapes with strata and grain; a wall is many separate stones of different size laid in courses; the ground has small stones, tufts and soil at the stations. This brings back, for rocks, walls and ground only, part of the second realism pass the owner cut on Nov 11.

### 12.R20 Scene additions (UI-Q21), in every scene tier, with detail rising by tier

1. **A dense forest just across the river**, very visible from the default view, with the river cutting through it: montane trees of the Kenyan highlands (African pencil cedar and broadleaf trees), many and close together, darker under the canopy.
2. **Water that flows over rocks**: rapids where the river runs over rocks, foam at the rocks, and slow moving highlights. With reduced motion and in Calm mode it is still. Nothing in it flashes: foam and highlights drift, they do not switch on and off.
3. **The shepherd is a Maasai silhouette**: a tall figure wrapped in a shuka, holding the staff with the lantern; beaded details only as shape (a collar), no face detail; respectful and plain, never a caricature.
4. **Real looking animals**: a mixed flock of sheep and goats (sheep of the kinds kept in Kenya, goats with horns and upright tails), and a herding dog with real proportions.
5. **Wildlife at the edge, in High only**: distant birds and an antelope on the ridge. Nothing near the stations.
6. Every rule of 12.R5 holds, with the two exceptions of 12.R5.2 (the water, the distant birds).

### 12.R10 Tests

As for every layer: tests first. The normal suite (`python -m unittest discover -s tests -t .`) stays standard library only and needs no network, npm, Node or browser.

1. **Snapshot** (UI.2), real child processes (`python -m umwayi view snapshot`) with `HOME` and `XDG_CONFIG_HOME` in a temporary folder:
   - a fixed root gives exact bytes, twice the same;
   - the key set equals the list of 12.R4.2, and every leaf is a whole number, a boolean, one of the fixed words or a date: a structural test, not a search;
   - sentinel words planted in every file the command reads (queue titles, answers and recommendations; rule ids, titles and text; logbook lines; schedule and job names; memory private path names; archive pointers; the root's own path) never appear in the file, the output or the logbook entry beyond what 12.R4.5 allows;
   - each part unreadable alone gives `null` for that part and 0 elsewhere unchanged; no `schedule.yaml` gives 0 entries;
   - a tampered logbook, three ways as in S.R3.1: exit 1, nothing written, snapshot and logbook unchanged byte for byte;
   - `--out` cases: inside the root, outside, `..`, a link, a hard link, a folder, an existing foreign file such as `rules.yaml` (64, untouched), an earlier snapshot (replaced), a path with a newline, a path of 1025 characters, a name not ending in `.json`;
   - the logbook entry exists once, with the file's SHA-256, and no content; a logbook that fails after the file is written puts the file back (exit 2); the kill switch on and unknown still gives 0;
   - only exit codes 0, 1, 2 and 64; the command changes no other file (a snapshot of the whole root before and after, except the file and `LOGBOOK.md` with its record);
   - code guards: `view.py` imports no `subprocess`, `socket`, `urllib`, `http` or `ctypes`.
2. **The package** (UI.1), standard library: exact versions, no range, every lockfile entry has a sha512 and a registry.npmjs.org source, `node_modules` and the page are where the rules say, `.gitignore` has the exception, and `build.json` matches the sources and the page (the page was rebuilt after the last source change, and was not edited by hand).
3. **The built page** (UI.1), standard library (an address in an `<a href>` or in the install command must be one of the listed home addresses; every other address still fails): no `<script src>`, `<link href>`, `<img src>`, `@import`, `url(` with a remote address, `fetch(`, `XMLHttpRequest`, `WebSocket`, `sendBeacon`, `import(`, `//cdn`, `localStorage`, `sessionStorage`, `indexedDB`, `document.cookie`, `FileLoader`, `ImageLoader` or `TextureLoader`; any `http://` or `https://` string must be one of a short list of XML namespace addresses (three.js carries `http://www.w3.org/1999/xhtml`, which is a name, not a request); the Content-Security-Policy tag of 12.R2.5 is present and denies by default; the 11 label buttons, the `<ul>` list view, the calm mode button, the reduced motion rule and the checks panel exist in the HTML.
4. **Page logic**, Node's built in test runner with no package (`node --test`, UI.1 to UI.4): the snapshot validator (every bad shape of 12.R9.1), the mapping from counts to scene numbers, the easing and the pose player (it ends, it stops asking for frames), the checks panel's export text and warning. **The layout and the position function (tests first):** the default positions equal the fixed table; no two stations overlap at the defaults and, for thousands of seeded random needs and the extremes (all quiet, all needing), at any reachable position; a higher need never puts a station further from the lantern; the same needs give the same positions; a move ends in 3 s (5 s in Calm) and jumps with reduced motion; every station stands on land and the river ones on the river bank; and the keyboard order is the order of the list view. **The home content:** the status strip text for a sample and for a snapshot, the copy lines equal the install and command text exactly, placeholders are marked, and no sample value appears without the word sample. **The detail mode:** the choice from a set of environments, and the step down. **The tier choice (Nov 11, round 2, tests first):** `chooseTier` for no WebGL, Save-Data, each effective type, a missing Network Information API, a software renderer, a small screen, reduced motion, a strong machine, the highest tier of the live view, and each `#tier=` choice. **The far stations:** at least three at 30 m or more, still no overlap.
5. **In a browser** (UI.1 and UI.5), by hand with a headless browser kept outside the repo (like the scan tools of S.2: never a dependency, version recorded): no console error; all requests blocked and zero attempted; 11 buttons that show their name on focus and on hover, in the overview no name visible at rest, the panel opens for each, and high and low detail both draw; two screenshots 2 seconds apart at rest are identical; after one click the picture changes and then is identical again within 3 seconds (5 in calm mode); no animation frame is requested at rest; with reduced motion on, the camera jumps and the poses step; the luminance and white area limits of 12.R5.6; the home content is readable at 1440 by 900 and 390 by 844 and the Copy buttons write only on a click; the 30 frames a second check. Results go into `docs/interface.md` with the date, the browser and its version.
6. **Planted faults and mutation checks**, each killed by a named test, with the counts in the pull request: a title written into the snapshot; a path written; a count that is the wrong one; the tamper check skipped; the entry skipped; `--out` allowed over `rules.yaml`; a `fetch` added to the page; a font loaded from a CDN; a `setInterval` that redraws at rest; an infinite animation loop; reduced motion ignored; a page written by hand without a rebuild; a "passed" shown for a ticked check; a value-looking result not warned.
7. Docs: `tests/test_docs.py` passes with `docs/interface.md`.

### 12.R11 Not in layer 12

- **Anything that acts.** No button runs a command, answers the queue, changes a rule, turns the kill switch on or off, installs a schedule or starts an AI helper. The page is for looking.
- **A server, a socket or live updates.** The page does not poll. It shows the last snapshot.
- **Text from the owner's files.** No titles, names, paths or logbook lines, not even in a tooltip.
- **Layer 13** (12.R8) and every station beyond the eleven.
- **Saved notes.** The checks panel does not store results between visits.
- **Analytics, accounts, sharing and telemetry** of any kind.
- A mobile app and a desktop app. (A hosted public site is in scope since Nov 11, round 2: 12.R17.)
- **Photographs, scanned textures, downloaded images or models, and web fonts** (12.R12.1).
- **Anything that moves by itself**: swaying grass, drifting cloud, smoke (12.R5.2). Flowing water (all scene tiers) and distant birds (High only) are the owner's exceptions of Nov 11, round 2 (12.R20).
- **A drawn path, a signpost or a label board** in the scene (12.R3.1).

## Non goals for Dec 3

- Finance and marketing loops
- Shared rule packs (after Dec 3)
- File watching, an SQLite index, tmux sessions and a sandbox for agents and helpers (layer 11 proposes to cut or defer them, 11.R8)

## Layer 13: Correction and graded autonomy

Status: in scope before Dec 3 (the owner, Nov 11). Requirements 13.R1 to 13.R15, design.md "Layer 13" and tasks.md L13.0 to L13.6 are written in the L13.0 pull request and wait for the owner's approval; nothing is built. The owner's decisions of Nov 11 are recorded (design.md, "Owner decisions"); L13-Q1 to L13-Q18 are open, each with a proposed answer. Layer 13 is added as new sections at the end of the three spec files so that the layer 12 branches merge cleanly.

User story: as the owner, I want my standing approvals to run out unless I renew them, a closed decision to be reopenable without rewriting history, a way for an AI helper to object to a No without changing it, and an autonomy score that can save me from a question I have answered the same way many times, so that umwayi can correct itself and trust a little more over time, and still never act without a rule I wrote.

The layer has five parts, built in this order, each one a slice that ships alone and needs nothing from a later slice: **Elections** (13.R2, 13.R3), **Reversal** (13.R4, 13.R5), **Courts** (13.R6, 13.R7), **Honest tension** (13.R8), **Graded autonomy** (13.R9 to 13.R12). The owner stops the build where Dec 3 finds us; a slice is merged whole or not at all.

### 13.R1 What never changes (applies to every part)

1. **A No is never changed by anything in layer 13.** Not by `review_by`, a reopen, a petition, a rules change or the score. A No that matches an action is still the answer, exit 2.
2. **Every part but graded autonomy can only move toward Ask me first.** An election lapse turns a Yes into Ask me first. A reopen opens a question. A petition adds a queue item. Only graded autonomy can move an answer toward Yes, and only Ask me first to Yes, only under 13.R10 and 13.R11.
3. **Fail closed.** A missing, malformed, ambiguous or unreadable input of any part gives Ask me first (for `umwayi check`) or a refusal with nothing changed (for the other commands). No part has a default that says Yes.
4. **One logbook entry for every change**, through the checked append, in the fixed shapes of design.md. A change that cannot be logged is not made, and an answer of Yes that cannot be logged becomes Ask me first (the rule of layer 2 holds).
5. **The logbook is never edited.** No part of layer 13 changes, deletes, marks or rewrites an existing logbook line. Corrections are new entries.
6. **Exit codes.** `umwayi check` keeps 0, 2, 3 and 64. The new commands use 0 (done), 1 (refused: something was checked and found wrong, nothing was changed), 2 (an unexpected error, a crash blocks) and 64 (usage). The per command codes are in design.md.
7. **Standard library only, no network.** No module of layer 13 imports a network library or any third party package (rule 5 and rule 9 of the steering file); a code guard test checks every new module.
8. **No text in errors.** A message of a layer 13 command never prints the text of a file, an answer, a reason, a petition or a rule, only ids, dates, counts and fixed words.
9. **Words.** Messages and docs use the product words: rules, queue, archive, logbook, AI helper, Yes, No, Ask me first. No em dash.
10. **Each slice ships alone.** The code of slice N imports nothing from a slice after N, and the full suite passes with only the slices up to N merged. Where a later slice adds a step to the verdict order, the earlier order is unchanged without it.

### 13.R2 Elections: `review_by` on standing approvals and Yes rules

1. A rule may have a field `review_by` with a date `YYYY-MM-DD` (a real date; the same date check as the logbook). A **standing approval** is a Yes rule: it says Yes to a kind of action again and again until someone looks. Layer 13 adds no other kind of standing approval (L13-Q14).
2. `review_by` is allowed on a rule whose verdict is `yes`, and on a rule with verdict `ask` that carries the `autonomy` opt-in of 13.R9 (so a standing permission to be moved to Yes also runs out). On any other rule, and on every `no` rule, it makes `rules.yaml` malformed (Ask me first for every action, as for any unknown field).
3. A rule is **in force through the whole of its `review_by` day** and past it from the next day. A Yes rule that is past its `review_by` counts as an **Ask me first** rule for that check. It is not deleted, not edited and not rewritten; the file stays as the owner wrote it.
4. The date of a check for this purpose is the **latest** of the system date, the `--date` given and the newest date in the logbook. A past `--date`, or a clock set back, cannot bring a lapsed rule back.
5. **The fallback is logged.** The check's own logbook entry names every rule that fell back, with its id and its `review_by`, in the fixed shape of design.md. A check where no rule fell back writes the entry it writes today, byte for byte.
6. After the lapse the strongest rule wins as in layer 2 (No beats Ask me first, Ask me first beats Yes), with the lapsed rule counted as an Ask me first rule. So a matching No still gives No, and a lapsed Yes rule that matches gives Ask me first even when another Yes rule that has not lapsed also matches (the stricter answer wins; L13-Q16).
7. A rules file with no `review_by` anywhere behaves exactly as before layer 13, and its check output and entry are byte for byte the same.
8. Renewing is the owner's act: the owner edits `review_by` in `rules.yaml`. The edit is logged before use (13.R7).

### 13.R3 `umwayi rules due`

```
umwayi rules due [--within DAYS] [--date D]
```

1. It lists every rule that has a `review_by`, oldest first (then by id): the ones that have **lapsed** (and so are falling back to Ask me first) and the ones **due within** DAYS days (default 14, whole number from 0 to 3650). Each line holds the rule id, the `review_by` date, the number of days and one of the fixed words `lapsed` or `due`. It also prints how many Yes rules have no `review_by`. It prints no rule title, text or cause.
2. It **changes nothing**: no file and no logbook entry. It is the one place the owner looks for what needs renewing.
3. **Exit codes.** 0 when no rule has lapsed. 3 (Ask me first) when at least one rule has lapsed, or when `rules.yaml` is missing or broken (it prints that it cannot list). 64 for a bad argument. An unexpected error exits 2. It never exits 1. (L13-Q9.)
4. A `review_by` more than 366 days after today is listed with the word `far` (the date was set very far ahead); it still counts as in force (L13-Q10).

### 13.R4 Reversal: reopening a closed decision

User story: as the owner, I want to say that a decision I closed should be looked at again, and to see that in the record as a new event, so that nothing I decided earlier is rewritten.

```
umwayi decision reopen ID_OR_HASH --reason TEXT --by NAME [--date D]
```

1. A **closed decision** is a row of `queue.md` of kind `decision` whose status is `answered` or `closed`. Only a closed decision can be reopened.
2. The target is a queue id (`Q-0007`) or a **hash**: 64 lowercase hex characters, the `Chain` value of one entry of the logbook. A queue id is resolved to the newest chained entry whose source is `umwayi queue answer` or `umwayi queue close` and whose `Added` line starts with that id. The command always logs the full hash.
3. **A reopen writes a new logbook entry.** The entry states in its `Added` line that it is a reopen and names the hash of the old entry, in the fixed shape of design.md. **The old entry is never changed or marked**, and neither is any other line of the logbook: after the command the logbook is the old file with one entry appended. The old queue row is not changed either.
4. A reopen opens **one new row** in `queue.md`: kind `decision`, status `open`, a title that names the old id and a recommendation that carries the reason. The new row and the entry are written together (the existing queue commit: both, or neither).
5. **Refused, with exit 1 and nothing changed:** a hash that no entry of the logbook has; an entry that is not a closing entry of a decision, or not the newest closing entry of its decision; a queue id that does not exist, is a task, or is still open; an old entry with no `Chain` line (written before the chain started); a logbook whose chain has not started; a decision that was already reopened and whose reopening row is still open.
6. **Refused with exit 1 because the record is not intact:** a logbook that fails the tamper check or the hash chain, a hash record that does not match, an interrupted write, or a `queue.md` that does not parse. Nothing is written.
7. `--reason` is one line of plain text, 1 to 300 characters, without `|`. `--by` is one short line of plain text, 1 to 40 characters. A bad value exits 64 with nothing changed.
8. A decision can be reopened again after its reopening row is closed; the link then names the entry that closed the reopening row. The chain of reopens can be followed by hash from the newest entry back to the first, and each hop is a new entry.
9. Reopening does not change a rule, an answer or a verdict. It asks a question again.

### 13.R5 What would change my mind (`--revisit-if`)

1. Answering a row of kind `decision` requires `--revisit-if TEXT`: one line of plain text, 1 to 200 characters, without `|`, or the word `none`. `umwayi queue answer Q-... --answer ... --revisit-if ...`. Without it the command exits 64 and the row stays open.
2. `--revisit-if` on a row of kind `task` exits 64. A decision that is closed without an answer (`queue close` on an open row) records no revisit text.
3. The text is written in the logbook entry of the answer (the fixed shape of design.md), so it cannot be edited later, and it is not written to `queue.md`. The existing rule that the logbook holds the length of an answer and not its text stays; only this short condition is stored (L13-Q2).
4. A reopen shows the revisit condition that was recorded, in the new entry's `Checked` line and in the command's output. A decision answered before layer 13 shows `not recorded before layer 13`.
5. Nothing in layer 13 watches for the condition to come true. It is for the owner to read when reopening (a limit, written in KNOWN-LIMITS).

### 13.R6 Courts: a petition against a No

User story: as an AI helper that is refused by a No I think is wrong, I want a way to say so to the owner that cannot change the answer, so that a bad rule is noticed and a good rule is not argued away.

```
umwayi petition RULE_ID --helper NAME --reason TEXT [--date D]
```

1. A petition is allowed only against a rule that exists in `rules.yaml` and has the verdict `no`. Any other rule, a missing rule or an unreadable `rules.yaml` exits 1 with nothing changed.
2. The petition **becomes one queue item for the owner**: kind `decision`, status `open`, title `Petition against rule RULE_ID by HELPER` (the id and the name are validated, so the title holds no free text), and a recommendation that starts with `Petition, untrusted text from an AI helper:` followed by the reason.
3. **It never changes the verdict by itself.** After any number of petitions, answered or not, `umwayi check` gives the same answer for the same action, and `rules.yaml` is byte for byte the same. Answering the queue item changes nothing in the rules. Only the owner editing `rules.yaml` changes a rule, and that edit is logged before use (13.R7).
4. `--helper` is a name: a lowercase letter, then up to 39 of lowercase letters, digits, `_` or `-`. `--reason` is one line of plain text, 1 to 200 characters, without `|`. A bad value exits 64.
5. **Limits against spam**, all counted from `queue.md` and the logbook, never from the command line: one open petition for the same helper and rule (a second prints `Already open, nothing added: Q-...` and exits 0); at most 3 open petitions for one helper; at most 10 open petitions in all; at most 5 accepted for one helper and at most 10 accepted in all on one logbook day. Past a limit the command exits 1 with nothing written, and it says which limit. (L13-Q12.)
6. A refused petition writes no logbook entry, so a flood cannot grow the logbook. An accepted petition writes exactly one entry, in the fixed shape of design.md, with the id, the helper name and the length of the reason, not the reason.
7. The command does not run an AI helper's action and does not ask the rules. The layer 9 and layer 10 gates already ask the rules before a helper runs it (steering rule 7). The reason text is untrusted: it is shown to the owner marked as such, never copied to the logbook, and never read by any layer 13 code.
8. The owner answers the item with `umwayi queue answer Q-... --answer TEXT --revisit-if TEXT` like any decision.

### 13.R7 Rule changes are logged before use

1. Every check, and every other command that asks the rules, notices when `rules.yaml` (the exact bytes it reads) differs from the last version that was logged. Before the new rules are used for the first time, one entry is written: source `umwayi rules`, with the SHA-256 of the file, the number of rules before and after, the ids added, the ids removed, and for every rule whose verdict, `review_by` or opt-in changed the id and the old and new value. It holds no rule title, text or cause.
2. The first time layer 13 sees a `rules.yaml` it writes the same entry in its baseline form ("first logged"), and the rules are used.
3. **If that entry cannot be written** (a held lock, a broken chain, a failed tamper check), the new rules are used for No and Ask me first only: any Yes answer becomes Ask me first and the reason says why. A No stays a No.
4. A change that changes nothing a rule means (a comment, spacing, the order of rules) is still logged, with the words `no rule changed` in place of the lists, because the bytes changed.
5. The same is done for `autonomy.yaml` in graded autonomy (13.R9.4).
6. The entry does not stop the owner from weakening a rule: it makes the weakening visible and dated. Holding a weakened rule until the owner accepts it is a different design and is left to the owner (L13-Q11).

### 13.R8 Honest tension: stop criteria and the plain note

1. The docs of layer 13 (`docs/corrections.md`, `docs/autonomy.md`) carry this note, in these words or words that say the same, in a section named "No state is perfect": the owner wants correction and also safety; every correction mechanism adds a way to be wrong; umwayi makes a wrong state visible and dated and moves toward Ask me first when unsure, and it does not make any state perfect or safe.
2. **Nothing claims otherwise.** No layer 13 doc, message, `--help` text or logbook entry uses a claim of perfection or proof: the words `guarantee`, `guaranteed`, `foolproof`, `tamper proof`, `tamper-proof`, `unbreakable`, `unhackable`, `cannot fail`, `perfectly`, `100% safe`. A test searches the docs and the captured output of every layer 13 command for the list (the note itself is excluded by its exact sentence).
3. **Stop criteria for the build.** (a) A slice is merged only when all its acceptance tests and planted faults pass on Python 3.10 to 3.13 and its docs are current. (b) A slice that is not merged by Nov 28 is not merged: it stays specified, not built, in the docs. (c) No slice is merged in the freeze (Nov 29 to Dec 2) except a fix for a defect that a test finds. (d) If a slice breaks an earlier test it is not merged until that is fixed, never by changing the earlier test. (e) The owner can stop the layer at any slice, and the slices before it stay.
4. **Stop criteria at run time.** (a) Graded autonomy is off by default and has one setting (13.R12.1). (b) A `rejected` or `reverted` record stops moves for that action class for the cooldown (13.R10.7). (c) Every part falls back to Ask me first when its input is not intact (13.R11). (d) The kill switch stops moves at once (13.R11, row 4).
5. **What is stated plainly in KNOWN-LIMITS** for layer 13 (numbered from 160, the list in design.md): that `review_by` depends on the owner renewing honestly, that the score is a statistic of the past and cannot see a new context inside a class, that a process of the same user can write well formed score inputs, and that nothing here checks whether the owner's record is wise.

### 13.R9 Graded autonomy: the owner's record

User story: as the owner, I do not want to answer the same Ask me first for the hundredth time, but I want umwayi to move to Yes only where I said it may, only for actions I can undo and that cost little, and only on the evidence of my own record.

1. **Action class.** A class is a name the owner gives to a kind of action in a rule: a lowercase letter, then up to 39 of lowercase letters, digits, `_` or `-`. The class is declared by a rule, never found by reading an action's text, and the action's own fields are not used to name it (L13-Q3).
2. **The opt-in is in a rule.** A rule with verdict `ask` may have a field `autonomy` with three entries: `class` (the name), `reversible` (true or false) and `cost_uu` (a whole number from 0 to 1000000, in UU, the budget governor's unit). The rule must have a matcher `type` (equals, one or more values), so that the actions it matches have a known type. Any other shape, an `autonomy` field on a rule that is not `ask`, or two opt-in rules that give one class different `reversible` or `cost_uu`, makes `rules.yaml` malformed (Ask me first). A rule with no `autonomy` field never opts in.
3. **Types that can never be opted in:** `payment`, `transfer`, `purchase`, `withdraw`, `deposit`, `publish`, `post`, `send`, `publish_draft`, `schedule_install`, `budget_check`, `agent_run`, `agent_login` and `acp_permission`. A rule whose `type` matcher names any of them, and has `autonomy`, makes `rules.yaml` malformed. (The score may not move money, publishing, an install that runs by itself, a spending approval, or the start or permission of an agent.)
4. **Settings are the owner's, in `autonomy.yaml`** in the root, and every one is required (no hidden default): `version`, `enabled`, `window_days`, `min_decisions`, `min_lower_bound`, `confidence_z`, `revert_weight`, `max_cost_uu`, `cooldown_days`, `max_moves_per_day`. Whole numbers except `enabled` (true or false). A missing key, an extra key, a value out of range or a file that does not parse makes the file invalid, and graded autonomy is off. Any change to the file is logged before it is used (13.R7.5).
5. **The record.** The owner records one outcome at a time:

   ```
   umwayi autonomy record --class C --outcome approved|edited|rejected|reverted --by NAME [--ref Q-0007] [--date D]
   ```

   - `approved` means approved as proposed, `edited` means approved after the owner changed it, `rejected` means refused, `reverted` means undone after it was done.
   - It writes one chained logbook entry of the fixed shape in design.md. The class and the outcome are the only things the score reads from it. `--by` is a name, not read by the score.
   - It exits 1 with nothing written when the hash chain has not started, the logbook is not intact, or the same `--ref` was already recorded with the same outcome. It exits 64 for a bad class, outcome, name or ref.
   - It is an owner's command. The example rules of every adapter carry a No rule for it (13.R14), and it does not run for a helper unless the owner's rules say so.
6. **The inputs are only these entries.** The score reads the chained entries whose source is `umwayi autonomy record`, and counts them by class and outcome. An entry of that source, or of the source `umwayi autonomy`, that is not in exactly one of the fixed shapes, is not chained, or sits before the chain started, makes **every** input invalid: no class is moved anywhere (13.R11).
7. **The score never reads text.** It reads the class word, the outcome word and the date of the fixed shapes, nothing else. It does not read a queue title, an answer, a recommendation, a petition, a reason, a rule title or any other logbook line. A test plants sentinel and instruction text in all of those and the score does not change.
8. **The moves do not feed the score.** An action that was moved to Yes adds no approval. Only an outcome the owner records counts.
9. `umwayi autonomy status [--class C] [--date D]` prints, per class, the four counts, the weighted total, the bound, the thresholds, whether the class is eligible and the first reason it is not (a fixed word). It changes nothing. `umwayi autonomy validate` checks `autonomy.yaml` and the opt-in rules and prints every problem with a line number, and changes nothing.

### 13.R10 Graded autonomy: the score and the move

1. **The counts.** For one class, over the entries with a date in the last `window_days` days ending today (the election clock of 13.R2.4): `a` approved, `e` edited, `r` rejected, `v` reverted.
2. **The score** is the lower bound of the Wilson score interval, in per mille, as design.md defines it: successes `a`, failures `e + r + revert_weight * v`, total `n` the sum, the confidence `confidence_z` hundredths. It is computed with one fixed order of float operations and rounded **down** to a whole number of per mille, so a tie is never rounded up. With `n` equal to 0 the score is 0.
3. A check may move **Ask me first to Yes** only when all of the following hold, tested in the order of design.md; the first that fails leaves the answer at Ask me first:
   1. graded autonomy is on (`enabled` true) and `autonomy.yaml` is valid;
   2. the check writes a logbook entry (not `--no-log`);
   3. the kill switch is off (not on, not unknown);
   4. the logbook is intact, the hash chain has started and is unbroken, and every input is in a fixed shape;
   5. the answer was Ask me first and **every** matching rule that says Ask me first has the `autonomy` opt-in, and no matching rule lapsed (a lapsed Yes rule is final);
   6. the matching opt-in rules all give the same class;
   7. the opt-in rule has not passed its `review_by`;
   8. the class is declared `reversible: true`;
   9. the declared `cost_uu` is at most `max_cost_uu`;
   10. no `rejected` or `reverted` outcome of the class is recorded within `cooldown_days`;
   11. `n` is at least `min_decisions`;
   12. the score is at least `min_lower_bound`;
   13. fewer than `max_moves_per_day` moves of the class were logged today.
4. A matching **No** is never moved (13.R1.1). A move is never made when no rule matches. An answer of Yes is never moved to anything.
5. **Every move is logged with the score inputs**: the check entry holds the class, the four counts, the weight, `n`, the score, the thresholds, the declared reversibility and cost, and the moves counted for the day, in the fixed shape of design.md. If that entry cannot be written the answer is Ask me first.
6. **Every check that matched an opt-in rule and did not move** writes the fixed word of the first gate that failed in its entry (while graded autonomy is on), so the owner can see why.
7. **Cooldown.** A `rejected` or `reverted` outcome for a class stops all moves for that class for `cooldown_days` days from that outcome, whatever the score is.
8. A worked example, with exact numbers, is in design.md and is a test fixture.
9. **Where a move can happen.** In `umwayi check` and in every caller that logs its own check (the agent gates and the schedule). The callers that check without logging (jobs, helpers, publish and the inner checks of a workflow) are never moved: their Ask me first stays Ask me first. The election fallback of 13.R2 applies to every caller.

### 13.R11 Graded autonomy: fail closed

The following always mean **Ask me first** and never a move to Yes, each tested on its own by a child process (design.md has the table with the gate word of each):

1. graded autonomy off, `autonomy.yaml` missing, unreadable or invalid;
2. low data (`n` below `min_decisions`);
3. an irreversible action, or `reversible` missing or not true;
4. a costly action: `cost_uu` above `max_cost_uu`, or missing;
5. a No (the answer is No, not moved);
6. a broken hash chain, a chain that has not started, a failed tamper check, a logbook that cannot be read;
7. an input that is not in a fixed shape, an unchained input, a duplicate of an outcome for one `--ref`;
8. the kill switch on, or its state unknown;
9. any state umwayi cannot read or tell: the clock, `rules.yaml`, `autonomy.yaml`, the action's JSON, the class;
10. a dry run (`--no-log`), or a failed logbook write;
11. a lapsed `review_by` on the Yes rule or on the opt-in rule;
12. the cooldown or the daily cap;
13. any unexpected error inside the move: an unexpected error exits 2 like every command (rule 8), never Yes.

### 13.R12 Graded autonomy: one setting, off by default

1. **One setting turns it off:** `enabled: false` in `autonomy.yaml`. A root with no `autonomy.yaml` has graded autonomy off. Nothing turns it on except the owner writing `enabled: true` with every other setting present.
2. **Off means the behaviour of before.** With graded autonomy off, the answer, the exit code, the JSON and the logbook entry of `umwayi check` are byte for byte what they were without layer 13 (for a rules file that uses no other layer 13 field). The `autonomy` field in a rule is read and checked but has no effect.
3. Turning it off takes effect at the next check. A move already made is not undone: the owner records `reverted` if it was wrong.
4. `umwayi autonomy status` works whether it is on or off and says which.
5. The setting is the owner's. The example rules of every adapter keep a helper from writing `autonomy.yaml` (13.R14).

### 13.R13 Tests

As for every layer: tests first, real child processes (`python -m umwayi ...` with `HOME` and `XDG_CONFIG_HOME` in a temporary folder), the standard library only, no network. The acceptance tests per slice are in tasks.md. In all of them:

1. **Planted faults**, each found by a named test: a rule past its `review_by`; a petition spam; a forged score input; a reopen of a missing entry; a broken chain. Each slice adds the faults of its own part (tasks.md).
2. **Mutation checks**, with the counts in the pull request: for each slice, faults put into the code on purpose (an expiry off by one day, the fallback not logged, a petition that changes the verdict, a reopen that marks the old entry, a move that skips one gate, a score that reads text) and the tests must fail.
3. **Exit codes**: only the codes of design.md for each command, and the answer of `umwayi check` never Yes for a state in the fail closed table.
4. **Nothing else changes**: a snapshot of the whole root before and after a command, except the files the command is allowed to write.
5. **Python 3.10 to 3.13** in CI; the score fixtures give the same numbers on all four.
6. The existing tests are not changed to make a slice pass, except where this spec says a behaviour changes (13.R5.1: the answer of a decision needs `--revisit-if`).

### 13.R14 Docs

1. `docs/corrections.md` (Elections, Reversal, Courts, the rules change log and "No state is perfect") and `docs/autonomy.md` (graded autonomy) are the new pages, in the four part format, each under 300 lines, linked from the README and PROJECT.md. They are written as "specified, not built" in the L13.0 pull request and made current in each slice's pull request (DOCS_MAINTENANCE.md).
2. The other pages that change when a slice is built are listed in design.md ("Docs page plan"); each slice updates its own.
3. The example rules of the Claude Code, Kiro and generic adapters keep an AI helper from writing `autonomy.yaml` and from running `umwayi autonomy` and `umwayi decision`; `umwayi petition` is left to the owner's choice.
4. `tests/test_docs.py` passes with both pages.

### 13.R15 Not in layer 13

- **Any change to the view.** `umwayi view snapshot`, `ui/` and `site/` are not changed by layer 13. The review dates, reopened decisions and petitions of 12.R8 are drawn only if the owner asks for them after layer 13 exists (L13-Q13).
- **A way for an AI helper to change a rule, an answer or its own score.** None.
- **Learning from text.** No score, class or move is based on reading what an action says.
- **A model, an embedding or any statistics beyond the counts and the one interval of 13.R10.**
- **Automatic approval of a petition, and any automatic edit of `rules.yaml` or `autonomy.yaml`.**
- **Moves for money, publishing, an install or a spending approval** (13.R9.3), and any move to Yes of a No.
- **Holding a rules change until the owner accepts it** (L13-Q11), and an outside signature of the owner's record. Both are possible later.
- **Expiry of an installed schedule** (L13-Q14): a schedule runs through the Yes rules it asks, and those can expire.

## Local backend (W6): `umwayi serve`

Status: spec only, written on Nov 12 2026 in the W6.0 pull request. The owner decided on Nov 12 2026 (approved) that the rule changes from "the interface only looks" to "the page may send the same request the command line would, to a local backend". Steering rule 10 and requirement 12.R17.6 carry the new wording already. Nothing is built: no file under `umwayi/`, `ui/`, `site/` or `tests/` changes in this pull request. W6.R1 to W6.R18, design.md "Local backend (W6)" and tasks.md W6.0 to W6.10 wait for the owner's approval; W6-Q1 to W6-Q27 are open, each with a proposed answer. The section is added at the end of the three spec files so it merges cleanly with the other branches.

The workstream names are the owner's. W6 is this backend. W4 and W5 are the two later workstreams the owner named for the chat with Claude Code, Kiro and OpenCode and for the queue with an intake step; this spec reads them in that order (W4 the chat, W5 the queue and intake; W6-Q1 asks the owner to confirm). W7 is the login for a deployed interface. W4, W5 and W7 are not built or specified here beyond what W6 must leave ready for them.

User story: as the owner, I want to use the queue and a chat with my AI helpers from a web page on my own machine, with every request treated exactly as if I had typed the command, so that the page is a second way to give the same orders and never a second set of rules.

The owner's words, kept as the test of every choice below: the command is `umwayi serve`; it binds 127.0.0.1 only, with a token; every request goes through the same rules check, the same logbook and the same kill switch as the command line, by calling the same code and never a second copy; fail closed, so unclear means Ask me first or No; the core stays Python standard library only.

### W6.R1 What never changes (applies to every part)

1. **Same code, never a second copy.** A request calls the function that the command line calls for the same command (the table in W6.R8). A route handler holds no rule, check, path or file format of its own. Where a command line handler holds logic that is more than a call (a default, a limit, a check), that logic is moved into the core function and both call it (extract, never copy). A test proves it two ways: a spy shows each route calls the named core functions once, and a differential test shows the CLI and the request leave the same bytes in `queue.md` and the same command entry in `LOGBOOK.md`.
2. **Same rules check, same logbook, same kill switch** for every request that passes the gate (W6.R7). Nothing a request does skips one of the three, and nothing the request gate says (a token, an origin) replaces one of them. The gate answers "may this request be looked at"; the rules check answers "may this be done".
3. **Fail closed.** A request that is unclear, malformed, ambiguous, too big, too slow, unlogged or not in the route table is refused (the word No or Ask me first, W6.R15) and changes nothing. No part of W6 has a default that says Yes. An error inside the gate or the pipeline is a refusal, and an unexpected error is exit 2 for the command and a 500 with the word `error` for a request, never a success.
4. **The core stays standard library only** (rule 9). `umwayi/serve*.py` imports only the standard library. The network modules it needs (`http.server`, `socket`) are imported only inside the function that starts the server, so importing any umwayi module still loads no network library. The two guard tests (`tests/test_system.py` and `tests/test_automation.py`) get these imports on their allowlists by name, and no other module.
5. **127.0.0.1 only, always** (W6.R3). There is no flag, key or environment variable that binds another address.
6. **No secret in any output.** The token is shown once, on a terminal, at creation or rotation (W6.R4.5). It is never in the logbook, a log line, an error, a response, a queue row, an argument list, an environment variable of a child, a URL or a file other than its SHA-256 record.
7. **No text from a file in a refusal or an error.** A refusal names a fixed word and a request id, never a header value, a body, a path or a file's text.
8. **One logbook entry for every request that carried a valid token**, and a summary entry for those that did not (W6.R13). A request that cannot be logged is not done.
9. **The page can only do what the closed route table lists.** Adding a route needs the owner's approval, a row in the table of W6.R8, a test row and a spec change. The "never" list of W6.R8.4 cannot be added to by any later change without the owner changing this requirement.
10. **Words.** Messages and docs use the product words: rules, queue, archive, logbook, AI helper, Yes, No, Ask me first, kill switch. No em dash.

### W6.R2 The command, the page it serves and what changes in layer 12

1. **The command.**

   ```
   umwayi serve [--port N] [--page PATH]
   umwayi serve token create [--days N]
   umwayi serve token rotate [--days N]
   umwayi serve token revoke
   umwayi serve token status
   ```

   `umwayi serve` runs in the foreground until the owner stops it (Ctrl-C or SIGTERM). It is not a daemon and no schedule entry may run it (the schedule rules of layer 11 refuse the word `serve`; a test checks it). `--port N` is 1024 to 65535 (default 8765, W6-Q9); `--port 0` takes a free port. `--page PATH` names the built page to serve (default: `ui/dist/index.html` beside the package, if it is there).
2. **It starts only when everything is in order.** In this order: arguments (64); the root is a normal folder; the tamper check of the logbook (`read_checked_chain`; broken gives exit 1 and nothing starts); the token record exists, parses and has not expired (otherwise 64 with a fixed sentence that says to run `umwayi serve token create` or `rotate`); no other `umwayi serve` holds the lock `.umwayi/serve.lock` for this root (otherwise 64); the port can be bound on 127.0.0.1 (otherwise 64, without echoing anything but the port number). Then one logbook entry (W6.R13.4) and the line `Listening on http://127.0.0.1:PORT` on stdout. The line holds no token.
3. **The page is served by the backend, from the same origin** (W6-Q6). `GET /` returns the built page of `ui/dist/index.html` only if its SHA-256 equals the one in `ui/dist/build.json` in the same folder, the file is a regular file of at most 2.5 MB and neither the file nor a folder above it inside the checkout is a link. If any check fails the server still starts, `GET /` answers 503 with the word `page`, and the start line says "page not served". The page is served as bytes, unchanged, with the headers of W6.R6.6.
4. **The page and the backend share one origin**, `http://127.0.0.1:PORT`. This is why W6 needs no CORS at all (W6.R6). A page opened from disk (`file://`) or from any other origin makes no request to the backend: the page's client module refuses to run unless `location.origin` is exactly `http://127.0.0.1:` and a port, and says "Open this page with umwayi serve". Opened from disk it keeps every property of 12.R2.
5. **What the page needs (built in W6.9, by the owner's build).** One client module (`ui/src/api/client.js`) is the only place `fetch` may appear; it calls relative paths under `/v1/` only, sets `Authorization` itself, keeps the token in a variable in memory and nowhere else (no storage, cookie, address or history entry), and sets every response text with `textContent`. The page's Content-Security-Policy meta tag gains `connect-src 'self'` and nothing else (`default-src 'none'` stays). `tests/test_ui_package.py` and the `ui/test` checks that forbid `fetch(` are changed in W6.9 to forbid it everywhere except that one file. The site tests are not changed (the site never gets a client).
6. **What changes in layer 12, from the day `umwayi serve` is built, and not before.** Steering rule 10 and 12.R17.6 are already reworded (this pull request). Read with that change: 12.R2 (the page makes no request) holds for a page opened from disk and for the public site, and for the live view served by `umwayi serve` it becomes "makes requests to its own origin only"; the sentence "The view only looks" above 12.R1 and the bullets "Anything that acts" and "A server, a socket or live updates" of 12.R11 are replaced by W6.R8 (what the page may and may not do). The snapshot of 12.R4 is unchanged: it is a file of counts with no text. The public site (12.R17, 12.R18) is unchanged. The owner checks panel keeps its in-memory notes. Whether to edit those lines of layer 12 now or in the build pull request is W6-Q20.

### W6.R3 Binding and the network

1. **The socket is bound to the literal address `127.0.0.1`** with `socket.AF_INET`. Not `localhost`, not the all-addresses address, not `::`, not `::1`, not a name that resolves. The source holds the all-addresses string (four zeros with dots) nowhere (a test searches), there is no `--host`, no config key and no environment variable for the address (a test searches the argument parser and the source), and `umwayi.json` cannot set one.
2. **The socket's own address is read back** after the bind and is `127.0.0.1` with the chosen port, or the server stops with exit 2 (a test reads it back, and reads `/proc/net/tcp` and `tcp6` as the S.2 scan does).
3. **Every connection's peer is checked.** A peer that is not `127.0.0.1` (the socket would not let another in, but the check does not rely on that) is closed without a byte answered. The check is in the request gate (W6.R5), so it is property tested.
4. **One server per root.** `.umwayi/serve.lock` is held with `flock` for as long as the server runs (the same mechanism as the run lock; the file is never deleted). A second `umwayi serve` for the same root exits 64.
5. **No proxy, no redirect, no outgoing connection.** The server never connects out and never follows or sends a redirect. The one other local listener of umwayi, the telemetry receiver of the budget governor, keeps its own port and its own secret and is never reachable through `serve`.
6. **No TLS.** Traffic on 127.0.0.1 is plain HTTP (KNOWN-LIMITS, W6 items). A certificate for 127.0.0.1 would need a local certificate authority, and nothing in W6 builds one.

### W6.R4 The token: creation, storage, rotation

1. **What it is.** A token is 32 random bytes from `secrets.token_bytes`, written as `umt1_` followed by 43 characters of unpadded base64url (48 characters in all). The prefix lets the secrets sweep of the scan find it. It has a public id, `T-` and 8 hex characters from `secrets.token_hex(4)`; the id is not derived from the token.
2. **What is stored.** Only `.umwayi/serve.token`, a JSON file with exactly the keys `schema` (1), `id`, `sha256` (the hex SHA-256 of the full token string), `created` and `expires` (dates). The file is written through the shared atomic writer with mode 0600 whatever the umask, in a normal `.umwayi` folder, and is read with `read_regular` (a regular file of at most 1 KB; a link, a folder or a larger file is refused). The raw token is never written to disk by umwayi. `.umwayi/serve.token` and `.umwayi/serve.lock` are added to `.gitignore`.
3. **How it is checked.** On every request the server reads the record (not cached across requests), takes the SHA-256 of the presented token and compares the two digests with `hmac.compare_digest`. A missing, unreadable, unparsable, revoked, expired or different record gives the same answer to the caller as a wrong token (401, the word `token`). The expiry is judged on the election clock of 13.R2.4 (the latest of the system date and the newest logbook date), so a clock set back does not revive an expired token.
4. **How the page sends it.** In `Authorization: Bearer TOKEN`, one header, on every request to `/v1/`. Never in the address, a query, a fragment, a cookie or the body. The server sets no cookie, ever, so there is no ambient authority for another site to borrow.
5. **Creation.** `umwayi serve token create [--days N]`: `--days` is 1 to 90 (default 30, W6-Q5). It refuses (exit 1) when a record already exists, and refuses (exit 1) when standard output is not a terminal, because a token written into a pipe, a file or a CI log is a leak (the check is `isatty`). On success it writes the record, writes one logbook entry (W6.R13.4: the id and the dates, never the token), and prints the token once with the id and the expiry date. If the logbook entry fails the record is removed and nothing is printed (the order of `kill off`: act, log, undo on failure). Rule 2 of the steering file says "Never print secrets"; this printing, on the owner's own terminal, on the owner's explicit command, once, is the one exception, and W6-Q4 asks the owner to confirm it.
6. **Rotation.** `umwayi serve token rotate [--days N]` makes a new token the same way, replaces the record atomically and writes an entry that names the old and new ids. It needs an existing record (exit 1 if none). The old token stops working on the next request, including a request that is already waiting (a long poll ends with 401 at its next one-second tick). A running server needs no restart. If the entry cannot be written the old record is put back and nothing is printed.
7. **Revocation.** `umwayi serve token revoke` deletes the record and writes an entry. Every request is then refused with 401 until a new token is created. A server that is running keeps running and refuses everything but `GET /`.
8. **Status.** `umwayi serve token status` prints the id, the created and expiry dates and the days left, or "no token", and exits 0 (never 3). It prints no digest and no token.
9. **Who can do this.** Only the command line. No route creates, rotates, reads or revokes a token (W6.R8.4). The example rules of the three adapters keep an AI helper from running `umwayi serve` and from reading or writing `.umwayi/serve.token` (text matching, KNOWN-LIMITS 12 applies).
10. **Throttle.** After 5 failed token checks in 60 seconds, every request whose token fails is answered 429 with `Retry-After: 60` without being compared, until 60 seconds pass without a failure. A request with a valid token is never slowed by it. The failures are counted in memory and summarized in the logbook (W6.R13.3).
11. **Lifetime.** A token lives at most 90 days and 30 by default. `umwayi serve` prints the days left at start and warns at 7 days or fewer. The page keeps the token in memory, so the owner pastes it again after every reload (W6-Q5 asks about `sessionStorage`).
12. **Exit codes of the token commands.** 0 done, 1 refused (a record exists, none exists, not a terminal), 2 an unexpected error, 64 usage; never 3.

### W6.R5 The request gate

User story: as the owner, I want one small function that decides whether a request may even be looked at, with no file or network access of its own, so that it can be tested with thousands of generated requests.

1. **One pure function.** `decide(facts, state) -> Verdict` in `umwayi/servegate.py`. `facts` is what the server read off the connection: the HTTP version, the method, the raw target, the header lines as (name, value) pairs in order with duplicates kept, the peer address, the server's own address and port, and the declared body length. `state` is what the gate is given: the token record, the election clock date, a monotonic time and the counters of W6.R14. The function does no I/O, reads no clock, writes nothing, imports nothing that does, and returns a `Verdict`: either `Allow(route, params, body_cap)` or `Refuse(status, word)`. It never raises: any exception inside is caught by the one wrapper and becomes `Refuse(500, "error")`.
2. **The checks, in this order**, each failing closed. The first that fails decides.
   1. **Protocol:** the version is `HTTP/1.0` or `HTTP/1.1` exactly; the method is `GET`, `POST` or `DELETE` (anything else, including `OPTIONS`, `HEAD`, `PUT`, `PATCH`, `CONNECT` and `TRACE`, is 405 with the word `method`).
   2. **Peer:** the peer and the server address are both `127.0.0.1` (word `peer`).
   3. **Headers:** at most 64 header lines, each name a token of letters, digits and `-`, each value printable ASCII of at most 4096 bytes, the whole block at most 16 KB, no folded line, no bare CR or LF, no NUL. A header named `Transfer-Encoding`, `Expect`, `Upgrade`, `Content-Encoding`, `Te`, `Trailer` or `Proxy-*`, or `Connection` with any value other than `close` or `keep-alive`, is refused (word `header`). `Host`, `Origin`, `Authorization`, `Content-Length`, `Content-Type`, `Sec-Fetch-Site`, `Sec-Fetch-Mode` and `Sec-Fetch-Dest` may each appear at most once, whatever their values; a second one is refused (word `header`). Names are compared without regard to case.
   4. **Host:** exactly one `Host` header whose value is `127.0.0.1:PORT` with the server's own port (word `host`). `localhost`, another address, a different port, an empty or a missing value are refused (W6-Q7). This is the defence against DNS rebinding, and it holds even for a request that has a valid token.
   5. **Target:** the raw target is ASCII, starts with one `/`, has at most 512 characters, no `%`, no `\`, no `;`, no `#`, no control character, no `//`, no `.` or `..` segment, and no query except the keys the route lists (word `target`). An absolute-form or authority-form target (`http://...`, `host:port`) is refused.
   6. **The page:** `GET /` with no query is the one request that needs no token. It still passes checks 1 to 5, and an `Origin` header, if one is present, must pass check 8. It returns `Allow("page")`. Every other target needs a token.
   7. **Token:** exactly one `Authorization` header of the form `Bearer`, one space and a 48 character token of the allowed alphabet; its digest compared as in W6.R4.3; the throttle of W6.R4.10 applied (word `token`, status 401, or 429 while throttled). Checks 8 to 11 come after the token, so a caller without a valid token learns nothing about routes, methods, bodies or limits: an unknown `/v1/` target gets the same 401 as a wrong token.
   8. **Origin and fetch metadata:** a `GET` may omit `Origin`; a `POST` or `DELETE` must carry exactly one `Origin` equal to `http://127.0.0.1:PORT`. An `Origin` that is present on any method must equal that value; `null`, another scheme, host or port, and an empty value are refused (word `origin`). If `Sec-Fetch-Site` is present it must be `same-origin`; if `Sec-Fetch-Mode` is present it must be `cors` or `same-origin`; if `Sec-Fetch-Dest` is present it must be `empty`. These three are checked when present and not required, because a browser does not send them in every case (NOTES-w6). `Origin` is required for `POST` and `DELETE` because a browser always sends it with them (W6-Q8).
   9. **Route:** the target and method match one row of the route table exactly (W6.R8); otherwise 404 `route` for an unknown path and 405 `method` for a known path with another method. Path parameters match their pattern (queue ids `Q-` and 4 or more digits; chat, intake and permission ids 8 to 16 lowercase hex characters; an agent name of 1 to 40 characters of `a-z`, `0-9`, `-` and `_`).
   10. **Body:** a `GET` has no body (`Content-Length` absent or `0`). A `POST` has exactly one `Content-Length` of 1 to 6 digits no larger than the route's cap, and exactly one `Content-Type` that is `application/json` or `application/json; charset=utf-8`. A `DELETE` has no body. Otherwise the word is `length` (411 or 413) or `type` (415).
   11. **Rate:** the token bucket of the route's class has a token (W6.R14), otherwise 429 `rate`.
3. **The words.** A refusal carries one of a fixed set of words and nothing from the request: `method`, `peer`, `header`, `host`, `target`, `token`, `origin`, `route`, `length`, `type`, `rate`, `body`, `busy`, `page`, `kill`, `rules`, `ask`, `logbook`, `error`. The response body for a refusal is the same bytes for the same word, whatever the request (no echo, no length difference).
4. **Parsing of the body** is a second pure function, `parse_body(route, raw) -> params | Refuse`, with the same properties: UTF-8 only, no BOM, a JSON object, nesting depth at most 6, no duplicate key, no key the route does not list, `NaN`, `Infinity` and floats refused, whole numbers within the route's range, strings only within the route's length and printable character rules. A failure is 400 with the word `body`.
5. **The gate is the only way in.** The server calls `decide` for every request before it reads a body or touches any file, and a request that the gate refuses never reaches the pipeline (W6.R7). A test makes the pipeline raise if it is called with a refused request.

### W6.R6 Origin, Host, CORS and the browser

1. **No CORS, ever.** The server never sends an `Access-Control-Allow-*` header, answers no preflight (`OPTIONS` is 405 with the word `method`), and has no setting that allows another origin. A page on another origin cannot read a response, and a cross-origin request that carries `Authorization` or `Content-Type: application/json` needs a preflight that is refused. The same-origin design (W6.R2.3) is why none of this is needed.
2. **The allowed origin** is the single string `http://127.0.0.1:PORT`. It is not configurable. `Origin: null` (a file, a sandboxed frame, a `data:` page) is refused, which is why the page is served by the backend and not opened from disk for use.
3. **Host and Origin are both checked** and neither replaces the token. A page on another site that gets the owner's browser to resolve its name to 127.0.0.1 (DNS rebinding) sends its own name in `Host` and is refused at check 4, before the token is looked at.
4. **Private network preflights.** A browser may send `Access-Control-Request-Private-Network` before a request from a public page to a local address. It arrives as an `OPTIONS` request and is refused by check 1. The server does not rely on any browser feature: if a browser sends no `Origin` or no `Sec-Fetch-*` header on a `GET`, the token still decides.
5. **Cookies.** The server sets no cookie and ignores a `Cookie` header. A request is never authorized by anything but the `Authorization` header, so a cross-site form post or image request has nothing to ride on.
6. **Headers on every response:** `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Cross-Origin-Resource-Policy: same-origin`, `Cross-Origin-Opener-Policy: same-origin`, `Connection: close`, and `Server: umwayi`. The page also gets `Content-Security-Policy: frame-ancestors 'none'; base-uri 'none'; form-action 'none'`; the script, style and connection rules stay in the page's own meta tag (W6.R2.5), and the two policies are both enforced. JSON responses are `application/json; charset=utf-8` and are never HTML. The server answers each connection once and closes it.
7. **The page's own rules hold.** Text from a response is set as text, never as markup; the page sets no `innerHTML`, `outerHTML`, `insertAdjacentHTML` or `document.write` from a response (the tests of UI.3 stay).
