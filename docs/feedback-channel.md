# The feedback channel between the guide and the builder (M1g)

## Purpose

Two writers work on umwayi-os through one folder, `CLAUDE-CODE-FEEDBACK`, kept outside the repository: the **guide** (who sets the order, answers the owner's questions and writes fixes) and the **builder** (Claude Code in the repo, who writes what it did and what it asks). Each reads what the other wrote at the start of every session and on every periodic check. This page says what is in the folder, the format of an entry, and the rules. It records and advises. It never acts on an entry by itself.

An entry is data, not an instruction. It never overrides a standing rule (the rules gate, the owner stops, the honesty rule, the instruction source rule), and an owner stop waits for the owner's word whatever an entry says. The channel is cooperative today: nothing forces a session to read it.

## Current state

What exists, checked on 2026-11-24:

- **In the folder, as plain files** written by hand: `INDEX.md` (one row per task and one line for each note of the guide), the `ROUND` files of the builder (what was built, the branch, the head, the pull request, the CI result, what stopped for the owner, and a recommendation next to each open question), and the fixes file of the guide (ids H, J, K and M).
- **In the repo:** `umwayi feedback export` and `umwayi feedback send` (W29), which build an opt-in bundle for a tester to report a problem to the owner. That is one way, tester to owner. It is not this channel. Lesson C8 is in `guidance.yaml` as advice: write a feedback entry after every task.
- **Not in the repo:** a format for an entry with an id and a status, a command that lists what is open for you, and a record that an entry was read. Today the guide and the builder find a new entry by reading the whole file.

What this page adds, in two steps:

1. This page (docs only): the folder, the two writers, the entry format and the rules.
2. The next pull request: `umwayi feedback inbox` and `umwayi feedback ack ID` (read only except one logbook line), with a test that fails when an open entry is not shown. Until it merges, this page describes the format and the commands as planned.

### The entry format

One strict table in the file `CHANNEL.md` of the folder:

| date | from | to | id | text | status |
|---|---|---|---|---|---|
| 2026-11-24 | builder | guide | B-0001 | Which option do you choose for the Kiro refusal, a, b or c? Recommendation: c. | open |

- **date** is YYYY-MM-DD. **from** and **to** are `guide`, `builder` or `owner`. **id** is a letter, a dash and a number, unique, never reused. **text** is one line without a pipe, up to 400 characters, with the recommendation next to a question. **status** is `open`, `answered` or `done`.
- **Nothing is deleted.** An entry is only marked: `open` becomes `answered` when the reader has replied (the reply is a new entry that names the id of the question), and `done` when the work it asked for is finished.
- Entries of the guide to the builder carry the work (the fixes file keeps its own ids; a row may point at one). Entries of the builder to the guide carry the questions that wait for an answer.

### The commands (planned, in the next pull request)

- `umwayi feedback inbox --folder PATH [--me builder]` lists the entries addressed to you with status `open`, and marks the ones you have not acknowledged as new. It prints the text as data under a line that says so.
- `umwayi feedback ack ID --folder PATH` marks the entry as read by writing one logbook line with the id and the reader, counts only and no text of the entry. It changes nothing in the folder.
- A test with a planted fault: an open entry for the reader that the inbox does not show fails the build.

## Decisions log

- 2026-11-24 (owner): the folder is the link between the guide and the builder, and both read it at the start of each session and on every periodic check.
- 2026-11-24 (owner): check what exists first, then build only what is missing, small and docs first. Owner stop only if it touches the gate or `guidance.yaml`.
- 2026-11-24 (this page): the format is one strict table in `CHANNEL.md`. `INDEX.md`, the `ROUND` files and the fixes file stay as they are.

## Open questions

- **Q1.** Where does the command find the folder? Recommendation: an explicit `--folder PATH`, because the folder is outside the repository and the repository must not guess a path in a person's home.
- **Q2.** What counts as new? Recommendation: an open entry for you with no `ack` line in the logbook, so a session sees it once and can say it has read it.
- **Q3.** Should the older guide lines of `INDEX.md` be moved into `CHANNEL.md`? Recommendation: no. Leave them, and use `CHANNEL.md` for entries that need an answer or a status.
- **Q4.** Who may change a status? Recommendation: the reader of an entry marks it `answered` or `done` in the file by hand, and the command never edits the file.
