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
5. No network calls in layers 1 to 5. No module of the core package imports a network library (the system test checks every module).
6. No secrets in the repo.
7. Every helper action passes `umwayi check` first.
8. A crash blocks. Every unexpected error exits 2, never 0, 1 or 3. An adapter (layer 9) catches every error and blocks, because on Claude Code exit 1 blocks nothing.
9. The core `umwayi` package stays standard library only. Only adapter packages (layer 9, and layer 10 adapter packages) may use third party packages, pinned and listed in their own README.

## Exit codes (every command)

- 0 = Yes, or done
- 1 = a refusal: something was checked and found wrong, nothing was changed
- 2 = No, and every unexpected error (a crash blocks)
- 3 = Ask me first
- 64 = a usage or config error (wrong arguments, a value that is not allowed, a bad `umwayi.json`, jobs file or workflow file)
- A missing or broken `rules.yaml` gives Ask me first, not 64.

## Build order

Each layer works alone and is tested before the next starts. A layer that is not started begins only when the owner says so. Status and tasks: `.kiro/specs/umwayi-os/tasks.md`. Known limits: `docs/KNOWN-LIMITS.md`.

Done (PRs 1 to 8, then hardening and the whole-system test in PR 9, 556 tests, Python 3.10 to 3.13):

1. Memory: plain files (master context, projects, journal), a loader that builds one context bundle, private paths from a config file.
2. Rules: `rules.yaml`, `umwayi check`.
3. Queue: `queue.md`, `umwayi queue list|add|answer|close`.
4. Archive: `umwayi archive move|verify`, SHA-256 fingerprints, pointer left behind.
5. Logbook: `LOGBOOK.md`, append only. Layers 2 to 4 write here once it exists.
6. Automation: scheduled scripts, weekly progress report from git history, draft-only publish step that never pushes.
7. Helpers: Steward and a social helper, draft only.
8. Workflows: named workflow files, content loop (collect, brief, draft, approve), kill switch flag.

Built since (tasks.md has the status of every task):

9. Adapters (PRs 11 and 12): a thin adapter per AI platform (Claude Code PreToolUse hooks, Kiro hooks, a generic stdin and stdout adapter) turns hook input into `umwayi check` input and the answer back into allow, deny or ask.
10. Own command line and chat (PRs 13 to 29): one front door that starts Claude Code and Kiro through their own CLI or the Agent Client Protocol, with the queue, rules and logbook in front, subscription first. No model client. Open: the owner's first real run (10.31).
- Logbook crash safety (PR 27).

Not started, each only after the owner approves its requirements, design and tasks:

11. Linux-like features: spec written (PR 30), waiting for approval. Proposed scope for Dec 3: scheduled runs through systemd user timers that call the existing front doors; file watching and tmux cut, SQLite and a sandbox deferred to after Dec 3. No new scheduler, file system or shell.
- The logbook hash chain (approved) and the budget governor (approved).

## Schedule to Dec 3

The schedule in `.kiro/specs/umwayi-os/tasks.md` ("Schedule to Dec 3") is the one to follow. In short:

- Nov 14 to Nov 15: layer 11, only after its spec is approved
- Nov 16: logbook hash chain
- Nov 17 to Nov 22: budget governor
- Nov 23 to Nov 26: whole-system test again and a security scan
- Nov 23 to Nov 28: README, demo, Devpost text
- Nov 29 to Dec 2: freeze, only fixes for defects that tests find
- Dec 3: submit

## Engineering rules

- Python, standard library first. One entry point named `umwayi`.
- Every layer has tests. CI runs tests on every pull request.
- Specs live in `.kiro/specs/umwayi-os/` (requirements, design, tasks).

## Non goals for Dec 3

Finance and marketing loops, web interface.
