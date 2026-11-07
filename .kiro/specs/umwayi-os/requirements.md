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

1. `queue.md` holds tasks and decisions as rows with an id, a status, a recommendation and the date answered.
2. `umwayi queue list`, `add`, `answer` and `close` work on that file.
3. Ids are never reused.
4. Every change writes an entry to the logbook.
5. A malformed `queue.md` stops the command with an error and changes nothing.

## Layer 4: Archive

User story: as the owner, I want to move old text out of a file without losing it, so files stay short and nothing is lost.

Acceptance criteria:

1. `umwayi archive move` takes a block of text out of a file and writes it to the archive folder with an id, the reason, a word count and a SHA-256 fingerprint.
2. The source file keeps a pointer to the archive id.
3. `umwayi archive verify` recomputes every fingerprint and compares it with the index. Any mismatch or missing file gives a non zero exit code.
4. The move is safe: if writing fails, the source file is unchanged.
5. Every move writes an entry to the logbook.

## Layer 5: Logbook

User story: as the owner, I want a record of every change, so I can trust and audit the system.

Acceptance criteria:

1. `LOGBOOK.md` is append only. The tool never edits earlier lines.
2. Each entry has a date, a source, what was added, what was checked and what was not done.
3. Layers 2 to 4 write entries through one shared function.
4. Before appending, the tool checks that earlier lines are unchanged since its last write, and refuses to write if they were altered.

## Layer 6: Automation

User story: as the owner, I want the layers to run on a schedule, so routine work happens without me.

Acceptance criteria:

1. Scripts run the layers on a schedule.
2. A weekly progress report is built from git history.
3. A publish step produces drafts only. It never pushes and never publishes.
4. Every scripted action passes `umwayi check` first.

## Layer 7: Helpers

User story: as the owner, I want AI helpers that prepare work for me, so I only approve.

Acceptance criteria:

1. Steward reads the queue and proposes tasks as drafts.
2. A social helper turns an article into post drafts.
3. Every helper action passes `umwayi check` first. Anything other than Yes stops the helper.
4. Helpers never publish, never hold bank or card credentials and never move money.
5. Helper activity is written to the logbook.

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
