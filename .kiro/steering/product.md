# umwayi-os product steering

Read this before any work in this repo. Later sessions must follow it.

## Product

- Name: **umwayi-os** (lowercase in code, the command is `umwayi`).
- What it is: an AI operating system for one person and their AI helpers.
- It keeps memory, enforces rules before an AI helper acts, tracks a queue of tasks and decisions, archives moved text with a fingerprint, and writes a logbook of every change.
- All code in this repo is new and written from Nov 7 2026.

## Words to use in user text

Use these exact words in messages, docs and CLI output:

- rules
- queue
- archive
- logbook
- AI helper
- Yes
- No
- Ask me first

Do not use em dashes in docs or user text. Use commas, colons or periods.

## Safety rules

1. Fail closed. Unknown, missing, malformed or ambiguous input means **Ask me first**.
2. Never print secrets. Private paths are never put in a context bundle, and errors never echo file content.
3. Never push to main. Work on a feature branch and open a pull request.
4. Helpers draft only. An AI helper never publishes, never holds bank or card credentials and never moves money.
5. No network calls in layers 1 to 5.
6. No secrets in the repo.
7. Every helper action passes `umwayi check` first.

## Exit codes of `umwayi check`

- 0 = Yes
- 2 = No
- 3 = Ask me first
- Usage errors of other commands use 64 so they never look like a rules answer.

## Build order

Each layer works alone and is tested before the next starts.

1. Memory: plain files (master context, projects, journal), a loader that builds one context bundle, private paths from a config file.
2. Rules: `rules.yaml`, `umwayi check`.
3. Queue: `queue.md`, `umwayi queue list|add|answer|close`.
4. Archive: `umwayi archive move|verify`, SHA-256 fingerprints, pointer left behind.
5. Logbook: `LOGBOOK.md`, append only. Layers 2 to 4 write here once it exists.
6. Automation: scheduled scripts, weekly progress report from git history, draft-only publish step that never pushes.
7. Helpers: Steward and a social helper, draft only.
8. Workflows: named workflow files, content loop (collect, brief, draft, approve), kill switch flag.

## Engineering rules

- Python, standard library first. One entry point named `umwayi`.
- Every layer has tests. CI runs tests on every pull request.
- Specs live in `.kiro/specs/umwayi-os/` (requirements, design, tasks).

## Non goals for Dec 3

Budget governor, finance and marketing loops, web interface.
