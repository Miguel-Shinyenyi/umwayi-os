# Known limits

These are real limits of umwayi-os today. They are written down on purpose and are not fixed yet. Each one says what happens, why it matters and what would fix it later. Items 1 to 11 were checked on the hardening branch (Nov 8 2026) by running the commands, not only by reading the code. Items 12 to 20 come from building the layer 9 Claude Code adapter.

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

## Layer 9: the Claude Code adapter (found while building part 1, not fixed)

Facts about Claude Code below come from its hooks reference; the links are in `adapters/NOTES.md`.

### 12. Rules match plain text, not shell syntax

The adapter sends the whole Bash command as one string, and a rule like `command__contains: ["rm -rf"]` looks for that text, ignoring case. A command can be written to get past it: `rm -r -f`, a variable, a script that is written first and run later, another tool. The example rules in `adapters/claude_code/rules.example.yaml` are a first layer, not a sandbox. The Claude Code docs also call hook filtering best effort and point to Claude Code's own permission deny rules for hard limits; keep those too.

### 13. The adapter cannot block when it never gets to run

The adapter turns every error it can see into exit 2 (a block). Some failures happen before any of its code runs: Claude Code cannot start `python3`, the script path is wrong, the hook times out, or Python cannot compile `hook.py` (a bad edit, or a Python older than 3.10), which makes the interpreter exit 1. Claude Code treats all of these as a non blocking error and runs the tool, unless the handler sets `"onFailure": "block"`, which needs Claude Code v2.1.295 or later. The settings snippet in the README sets it. On older Claude Code versions these failures let the tool call run.

### 14. Yes skips Claude Code's permission prompt

umwayi's Yes becomes `allow`, and Claude Code then does not show its own permission prompt for that call. Claude Code still applies its own deny and ask permission rules. If you want Claude Code's prompt as well, do not give Yes rules for those tools.

### 15. An AI helper can try to turn off its own guard

The files that guard the adapter (`rules.yaml`, `LOGBOOK.md`, `.umwayi/`, the `.claude/settings` files) are ordinary files. The example rules deny Write and Edit calls to them and shell commands that name them, but that is text matching (item 12), so a script can still change them. Protecting them with Unix permissions (the AI helper runs as a user that cannot write them) is layer 11.

### 16. The kill switch does not stop the adapter

`umwayi kill on` stops AI helpers, jobs and workflows. The adapter does not check it, so while the switch is on, Claude Code tool calls are still answered by the rules (a Yes still allows). Whether the adapter should deny everything while the switch is on is an open question for the owner (tasks.md 9.12).

### 17. Only some tool input is checked

The adapter sends the command, path, pattern, URL, query or subagent type, depending on the tool (`adapters/NOTES.md`). It does not send what a Write puts in a file, the text of an Edit, or a subagent's prompt, so rules cannot look at them.

### 18. Two processes per tool call, and a stricter answer when the logbook fails

- Every tool call starts the adapter and then `umwayi check`, two Python processes. On the build machine that took about 150 ms per call (median of 20). Not measured elsewhere.
- When the logbook cannot be written, `umwayi check` keeps a No as No and turns a Yes into Ask me first, but its answer then has `rules_ok` false, so the adapter denies all three. Stricter than `umwayi check` alone, and a broken logbook blocks every tool call until the owner seals it.

### 19. Claude Code cases the adapter does not see or decide

- Files you mention with `@` in a prompt are added without a tool call, so no PreToolUse hook sees them.
- In a non interactive `-p` run with nobody to answer, Claude Code turns an `ask` into a denial.
- The adapter only handles `PreToolUse`; configured on another event, it blocks.

### 20. Kiro: the docs were read only as Markdown copies, and they disagree

The Kiro hook pages render with JavaScript, so the notes come from the Markdown copies that `kiro.dev/llms.txt` lists. In those copies the Pre Tool Use JSON examples are empty. The pages disagree about other exit codes (one says any non zero code blocks a Pre Tool Use call, the others say only exit 2 does) and about the default timeout (60 seconds, or 30 seconds set with `timeout_ms`). The Kiro adapter is not built yet.
