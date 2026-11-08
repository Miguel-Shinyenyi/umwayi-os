# Requirements: umwayi-os

umwayi-os is an AI operating system for one person and their AI helpers. It keeps memory, enforces rules before an AI helper acts, tracks a queue of tasks and decisions, archives moved text with a fingerprint, and writes a logbook of every change.

It is built in eight layers. Each layer works alone and is tested before the next starts.

## Glossary

- **Owner**: the one person who uses umwayi-os.
- **AI helper**: a program or model that acts for the owner. It is always draft only.
- **Answer**: one of Yes, No, Ask me first.
- **Action**: a JSON object that describes what an AI helper wants to do.
- **Root**: the folder that holds `umwayi.json`, `rules.yaml`, `queue.md` and `LOGBOOK.md`.

## Cross-cutting requirements

- CC-1 Fail closed. Unknown, missing, malformed or ambiguous input gives Ask me first, or a clear error that changes nothing.
- CC-2 Every layer has automated tests.
- CC-3 CI runs the tests on every pull request.
- CC-4 Layers 1 to 5 make no network calls.
- CC-5 The repo holds no secrets, and the tool never prints secrets.
- CC-6 AI helpers never hold bank or card credentials and never move money.
- CC-7 Python with the standard library first. Any third party dependency needs a written reason in the design.
- CC-8 There is one command line entry point named `umwayi`.
- CC-9 User text uses the words: rules, queue, archive, logbook, AI helper, Yes, No, Ask me first.
- CC-10 Docs contain no em dashes.
- CC-11 Work happens on feature branches with pull requests. Nothing is pushed to main.

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

User story: as the owner, I want named workflows that helpers run as drafts, with one switch that stops everything.

Acceptance criteria:

1. Workflows are named files. The first is the content loop: collect, brief, draft, approve.
2. Helpers run workflows as drafts. The approve step is always the owner.
3. A kill switch flag stops every run. If the flag state is unknown, runs stop.
4. Each run writes to the logbook.

## Non goals for Dec 3

- Budget governor
- Finance and marketing loops
- Web interface
