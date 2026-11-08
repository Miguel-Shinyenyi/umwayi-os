# Known limits

These are real limits of umwayi-os today. They are written down on purpose and are not fixed yet. Each one says what happens, why it matters and what would fix it later. Checked on the hardening branch (Nov 8 2026) by running the commands, not only by reading the code.

## Approval and the owner

### 1. `--approved-by` is self-declared

`umwayi publish-draft DRAFT --approved-by NAME` copies a draft to `outbox/` when the rules say Ask me first. Any name is accepted: `--approved-by "Not The Owner"` works. Nothing proves that the person typing it is the owner.

- What protects you today: the AI helpers, jobs and workflows have no code path that passes `--approved-by` (the system test checks the code and runs them with a spy on `publish`), and `publish-draft` only copies a file for you to post by hand. It never posts.
- What it does not protect against: any program that runs as you and calls `umwayi publish-draft --approved-by ...` itself.
- A later fix: an approval that something outside the repo signs, for example a key the AI helpers cannot read.

### 2. The kill switch is a file anyone with write access can remove

`umwayi kill on` creates `.umwayi/KILL`. Anyone, or any program, that can write the repo folder can delete it, and runs start again. `umwayi kill off` writes a logbook entry, but deleting the file by hand writes nothing.

- It stops runaway AI helpers, jobs and workflows. It is not a guard against a person or a program that has your file permissions.
- A later fix: a switch outside the repo folder, owned by another user, or checked against the logbook.

## The logbook

### 3. Editing both LOGBOOK.md and its hash record is not detected

The tamper check compares `LOGBOOK.md` with the SHA-256 in `.umwayi/logbook.sha256`. If someone edits the logbook and then writes the new SHA-256 into the record, `umwayi logbook verify` says ok. The record sits right next to the file it protects.

- A later fix: keep the hash outside the repo, chain each entry to the one before it, or sign the record.

### 4. Large logbooks are re-read on every append

Every append (every `umwayi check`, every queue change, every helper step) reads, parses and hashes the whole `LOGBOOK.md`. That is fine for thousands of entries. With many AI helper runs a day it will get slower over time, and it was not measured.

- A later fix: check only the end of the file against a stored length and hash, or start a new logbook file per month.

## Commands

### 5. `umwayi report` run directly does not check the kill switch

The kill switch stops AI helpers, jobs and workflows. `umwayi report` is an owner command, so when you run it yourself it writes a draft even while the switch is on. The `report` step inside `umwayi run` or `umwayi workflow run` is stopped, because those runners check the switch first.

- The same is true of the other owner commands (`queue`, `archive`, `check`, `publish-draft`). That is on purpose for the owner. It matters if a program, not you, runs `umwayi report`.

### 6. YAML syntax errors show only the first problem

`umwayi workflow validate NAME` reports every problem in a file that parses. A YAML syntax error (a tab, a flow mapping, an unclosed quote) stops the parser, so only that one problem is shown, with its line. Fix it and run validate again to see the rest. The same is true of `rules.yaml` and the jobs file.

### 7. Social drafts use the same text for every channel

`umwayi social draft` and the `social-draft` workflow step write one draft per channel in `social_channels`, but the text is the same in all of them: one fixed template, at most 280 characters. Nothing is tuned per channel (length, tone, links).

Inside a workflow there is a second difference: the social step is one rules check for all channels, so a rule that says No for one channel (matching `channel`) only works with `umwayi social draft`, not with the workflow step.

## Found while hardening, not fixed

### 8. A failed publish can leave an empty `outbox/` folder

If `publish-draft` copies a draft and then the logbook entry fails, the copy is removed, but the `outbox/` folder it created stays (empty). No file is left behind. Found by the system test.

### 9. The run lock needs `fcntl`, and owner commands do not take it

- The run lock (`.umwayi/run.lock`) uses `fcntl.flock`. Where `fcntl` does not exist (Windows), every AI helper, job and workflow answers Ask me first and nothing runs. That is the fail closed choice, but it means umwayi-os does not run its helpers on Windows today.
- `flock` may not work on some network file systems. Not tested.
- Owner commands (for example `umwayi queue add`) do not take the run lock, so you can change `queue.md` while Steward reads it. Each queue write is atomic and logged, but a proposal can be out of date by one change.

### 10. There is no `umwayi memory add` command

Memory is plain files that the owner writes in `memory/` (`master.md`, `projects/`, `journal/`). `umwayi memory bundle` reads them. The system test adds a memory file by hand.

### 11. What the tests do not cover

- The system test runs `python -m umwayi`, the same `main()` as the `umwayi` script, not the installed `umwayi` script itself.
- Unexpected crashes are made in the tests by patching one function in the child process. The corrupt state sweep found one real crash (a `memory` folder that is a link loop), which is fixed; there may be others.
- Tests run on Linux only, with Python 3.10 to 3.13. Windows and macOS are not tested.
- The two-process tests make the first run sleep while it holds the lock, so the two runs are sure to overlap. Races without that pause are not forced.
