# Design: umwayi-os

## Overview

One Python package named `umwayi`, standard library only, with one entry point (`umwayi`, also `python -m umwayi`). Each layer is its own module and depends only on lower layers. A layer never imports a higher one.

```
umwayi/
  cli.py        entry point, subcommands, exit codes
  config.py     layer 1: umwayi.json loading and validation
  memory.py     layer 1: context bundle loader
  miniyaml.py   layer 2: strict YAML subset reader (no third party YAML)
  rules.py      layer 2: rules loading and the check decision
  taskqueue.py  layer 3: queue.md parser, writer and commands
  logbook.py    layer 5: checked append, tamper check, lock, parser, verify, seal
  archive.py    layer 4: archive move and verify, INDEX.md parser
  fsutil.py     atomic file write shared by layers that write files
  jobs.py       layer 6: umwayi run, the jobs file, the gap rule
  report.py     layer 6: umwayi report, the one fixed git log command
  publish.py    layer 6: umwayi publish-draft
  drafts.py     numbered drafts under drafts/ that never overwrite (layers 6 and 7)
  helpers/      layer 7: base.py (every helper step), steward.py, social.py
  workflow.py   layer 8: workflows/NAME.yaml, umwayi workflow validate and run
  kill.py       layer 8: the kill switch .umwayi/KILL
  runlock.py    one run at a time: .umwayi/run.lock (fcntl.flock, never waits)
```

Layers 1 to 8 are built (PRs 1 to 8, hardening in PR 9). Layer 9 adapters live outside the core package, in `adapters/`, so they, and layer 10 adapter packages, may use third party packages, pinned and listed in their README, while `umwayi/` stays standard library only. Layers 10 and 11 (planned Nov 9 to Nov 10, each built only after the owner approves its requirements, design and tasks) and the budget governor (planned Nov 15 to Nov 21) are outlined at the end of this file.

Layers 2 to 8 write to the logbook through one function, `logbook.append(root, Entry)`. It takes the lock, runs the tamper check, the format check and the date check, appends, and records the new hash. No layer writes `LOGBOOK.md` any other way. The module is named `taskqueue.py`, not `queue.py`, because a file named `queue.py` inside the package would shadow the standard library `queue` when a file in the package is run directly.

## Safety model

- Fail closed everywhere. Parsers are strict: unknown keys, duplicate keys, bad types and unsupported syntax are errors, not guesses.
- Errors never echo file content. They name the problem and a line number, not the text.
- Private paths are matched case-insensitively and on every parent folder, so a rule for `memory/private` also blocks a file below it.
- Exit codes, for every command:
  - 0: Yes, or done.
  - 1: a refusal. Something was checked and found wrong (a malformed queue.md, an id that does not exist, a tampered logbook) and nothing was changed.
  - 2: No. Also every unexpected error: `main` catches every exception (and Ctrl-C) and exits 2, so a crash is never read as Yes or as a non blocking error by a hook. Inner catch blocks only catch known failures (`UmwayiError`, and `OSError` where a disk write can fail); they undo their work and let anything else through to `main`. The message is not printed, only the error type, because it may hold file content.
  - 3: Ask me first.
  - 64: a usage error or a config error. Wrong arguments, an argument value that is not allowed (for example a title with `|`, an empty reason, an id like `q-1`), or a missing or invalid `umwayi.json`, jobs file or workflow file. `ConfigError` is a kind of `UsageError`.
  - rules.yaml is not config in this sense: a missing or broken rules file gives Ask me first (3), as before.
- No network imports in layers 1 to 5.

## Layer 1: Memory

Layout under the root:

```
umwayi.json
memory/
  master.md
  projects/*.md
  journal/*.md
```

`umwayi.json`:

```json
{
  "memory_dir": "memory",
  "private_paths": ["memory/private", "memory/journal/*-private.md"]
}
```

Rules for config:

- Both keys are required. A missing file is an error, never an empty private list, because an empty list would fail open.
- Paths are relative to the root, use forward slashes, and may not be absolute or contain `..`.
- `memory_dir` must stay inside the root.

Loader:

1. Walk `memory_dir` in sorted order. Only `.md` and `.txt` files are read. Hidden names are skipped.
2. Symbolic links are skipped and counted.
3. A path is private if it, or any parent, equals a private entry or matches it as a glob. Private files are counted, not named.
4. Files that fail UTF-8 decoding are skipped and counted.
5. The bundle holds ordered sections (`master`, `projects`, `journal`) plus counts of excluded and skipped files.

Bundle text format:

```
# umwayi context bundle
## master
### memory/master.md
<file text>
## projects
...
## journal
...
```

JSON format has the same data: `{"entries": [{"section", "path", "text"}], "excluded_count", "skipped_count"}`.

## Layer 2: Rules

### rules.yaml

```yaml
rules:
  - id: no-money
    title: Never move money
    text: AI helpers never move money.
    cause: Safety rule.
    verdict: no
    matchers:
      type: [payment, transfer]
```

Fields:

| field | required | notes |
| --- | --- | --- |
| id | yes | lowercase letters, digits, `-`, `_`; unique |
| title | yes | short text |
| text | yes | the reason shown to the owner |
| verdict | yes | `yes`, `no` or `ask` |
| cause | no | why the rule exists |
| matchers | no | mapping, see below |

The spec lists id, title, text, cause and matchers. `verdict` is added because a check has to return an answer, and the answer has to come from the rule.

Matchers: all entries in a rule must match (AND).

- `field: value` matches if the action field equals the value, ignoring case.
- `field: [a, b]` matches if the action field equals any listed value. If the action field is a list, any item may match.
- `field__contains: text` matches if the action field contains the text, ignoring case.
- `field__exists: true|false` tests whether the field is present.

Fields are top level keys of the action. A missing field means no match, except for `__exists: false`. A rule without matchers never matches.

### YAML reader

The standard library has no YAML reader, and the standard library comes first. `miniyaml.py` reads only the subset used here: block mappings, block lists, inline lists of scalars, quoted and plain strings, integers, `true`, `false`, `null`, and comments. It rejects tabs, anchors, tags, block scalars, flow mappings, duplicate keys and bad indentation. `yes` and `no` stay strings (not booleans), so `verdict: no` is safe.

### Decision procedure

```
load actions JSON  -> invalid          => Ask me first
load rules.yaml    -> missing/invalid  => Ask me first
matched = rules whose matchers all match
none matched                           => Ask me first
strongest = No > Ask me first > Yes
winner = first rule in file order with the strongest verdict
```

Output:

```
No
Rule: no-money
Reason: AI helpers never move money. Cause: Safety rule.
```

`--json` prints `{"answer", "rule_id", "reason", "matched"}`. The action comes from an argument, or from standard input when the argument is `-`. Input is limited to 64 KB.

Bad inputs (the action, rules.yaml) give Ask me first. An unexpected error inside `check` (a bug, not a bad input) is not hidden as Ask me first: it reaches `main`, which exits 2, so a hook always blocks on it. (Until the hardening branch it gave Ask me first, exit 3, which a hook that blocks only on 2 would not block.)

### Logbook hook

Every check appends one logbook entry. See "Layer 5: Logbook" for the entry and for what happens when the logbook cannot be written.

## Layer 3: Queue

`queue.md` is plain Markdown with exactly one table. Text before and after the table is kept as it is.

```
| id | kind | title | status | recommendation | answer | answered |
| --- | --- | --- | --- | --- | --- | --- |
| Q-0001 | decision | Pick a name | answered | Use umwayi | Go with umwayi | 2026-11-05 |
```

- `id`: `Q-` and at least 4 digits.
- `kind`: `task` or `decision`. `status`: `open`, `answered` or `closed`.
- `recommendation`: free text, may be empty.
- `answer`: the owner's answer. An open row must have an empty answer. An answered row must have answer text. A closed row keeps whatever it had.
- `answered`: empty or a real date `YYYY-MM-DD`. An answered row must have a date, an open row must not.
- Cells cannot contain `|` or line breaks. Titles are limited to 200 characters. Recommendations and answers are limited to 500 characters each.

Parser rules (fail closed): exactly one table, exact column names in this order, 7 cells per row, unique ids, valid values, plain `\n` line endings, valid UTF-8. A violation is an error with a line number (never the text of the line), exit code 1, and no change to any file.

The old six column layout (no `answer` column) is refused by every command except `migrate`, with a message that names `umwayi queue migrate`.

### Ids are never reused

The next id is one more than the highest id found in two places: the rows of `queue.md`, and the logbook. From the logbook it takes the id at the very start of every `- Added: Q-NNNN ` line (queue add, answer, close all write one). Ids that only appear inside a title or any other text are ignored, so a title cannot inflate the counter.

- A missing `LOGBOOK.md` means no ids from the logbook.
- A logbook that exists but cannot be read (a folder, not valid UTF-8, a symbolic link) makes `add` refuse, say why, and change nothing, not even create `queue.md`.
- This covers a row, or the whole `queue.md`, deleted by hand. It does not cover someone who also edits the logbook, which layer 5's tamper check is meant to detect.

### Writing

1. Parse. Build the new text by replacing one line (answer, close) or inserting one line after the last table row (add). Every other line stays byte for byte.
2. Re-parse the result and check that only the intended row changed. If not, stop.
3. Write `queue.md` through a temporary file and `os.replace`.
4. Append to the logbook. If that fails, restore the old `queue.md` (or delete a file that `add` just created) and report an error.

### Commands

- `list [--status S] [--kind K]` reads only.
- `add --kind K TITLE [--recommendation R] [--date D]` creates `queue.md` if it is missing. The other commands need it to exist.
- `answer ID --answer TEXT [--date D]`: `--answer` is required, with the same limits as a recommendation. Works only on an open row. Stores the answer and the date. The logbook entry records the length of the answer, not the text.
- `close ID [--date D]`: works on an open or answered row. Keeps the answer and the date answered. A closed row cannot be closed again.
- `migrate [--date D]`: converts the old six column layout once.

Dates come from `--date` or the system clock, never from other rows.

### Migration

`migrate` reads the old layout with the old validation, then rewrites only the header line, the separator line and the table rows. Lines outside the table are untouched. Open and closed rows get an empty answer. Old answered rows get the fixed text `not recorded before migration`, because a current answered row must have an answer and the real text was never stored. It re-parses the result and compares every old column, writes through the same atomic write and logbook step as other commands, and refuses to run on a file that already has the current layout.

## Layer 4: Archive

```
archive/
  INDEX.md       plain Markdown table, one row per archive file
  A-0001.txt     the exact bytes of one moved block
```

`archive/INDEX.md`:

```
| id | source | moved | reason | words | sha256 |
| --- | --- | --- | --- | --- | --- |
| A-0001 | notes.md | 2026-11-07 | old stuff | 5 | 3f2c...64 hex characters |
```

- `id`: `A-` and at least 4 digits. `source`: root relative path with forward slashes, no `..`. `moved`: a real date. `reason`: non-empty. `words`: whole number. `sha256`: 64 lowercase hex characters, computed over the exact bytes of the archive file.
- The index parser is as strict as the queue's: exactly one table, exact columns in this order, unique ids, valid values, plain `\n` line endings. A violation is an error with a line number (never the text of the line), exit code 1, and no change.

### move

`umwayi archive move SOURCE --reason TEXT (--lines FIRST-LAST | --start MARKER --end MARKER) [--date D]`

Choosing the block:

- `--lines 3-4` is a 1-based, inclusive range of lines. A line is everything up to and including its `\n`, and a `\r` stays part of the line.
- `--start` and `--end` each match one whole line (compared after trimming spaces at both ends). Both marker lines are part of the block. Each marker must appear exactly once, the markers must differ, and the start must come before the end.
- Give exactly one way. Anything else is a usage error (exit 64).

Refusals (exit 1, nothing changed, nothing logged): config missing or invalid; source missing, not a regular file, a symbolic link or inside a linked folder, outside the root, or a path with `..` or `|`; source is a private path from `umwayi.json`; source is a protected file (`LOGBOOK.md`, `queue.md`, `rules.yaml`, `umwayi.json`, anything under `archive/`, `.umwayi/` or `.git/`); source is not valid UTF-8; range empty or outside the file; markers missing, repeated, equal or in the wrong order; the block has no words; reason empty, longer than 500 characters, with a line break or a `|`; the index is malformed or a symbolic link; `archive` is not a normal folder; the logbook cannot be read; the archive file for the new id already exists.

Id rule, same as the queue: one more than the highest id in the index and in the logbook (the id at the start of each `- Added: A-NNNN ` line). A missing logbook gives no ids, an unreadable logbook makes `move` refuse.

Order of work:

1. Check everything and build all three new files in memory. Re-parse the new index and compare the new source with the old one. Nothing is written yet.
2. Write the archive file (copy first), then read it back and compare its SHA-256.
3. Write the index.
4. Check that the source file is still the one that was read, then write the source with the block replaced by the pointer line (delete last).
5. Append one logbook entry.

Every write goes through a temporary file and `os.replace`. If any step fails, including step 5, the finished steps are undone in reverse order: the source and the index are written back, the archive file is removed, and an archive folder created for this move is removed. If an undo step itself fails, the error names the files that must be checked by hand.

The pointer line is `[archived A-0001: archive/A-0001.txt]` followed by the line ending of the last block line (none if the block ended the file without one). The output of `move` ends with the note `To put it back later: umwayi archive restore A-0001 (this command is not built yet)`. `restore` is not a command yet.

### verify

`umwayi archive verify` recomputes the SHA-256 of every archive file and compares it with the index. It prints one line per id and a summary, and never writes anything (no file, no logbook entry).

| status | meaning |
| --- | --- |
| ok | file exists and its fingerprint matches |
| changed | file exists but the fingerprint differs, or it is a symbolic link or not a file |
| missing | the index has the id, the file is not there |
| not in the index | a file or folder in `archive/` that the index does not list (other than `INDEX.md`) |

Exit 0 only when every line is `ok`. Otherwise exit 1. A malformed or missing index, or a missing archive folder, is an error and exits 1. The words column is not recomputed.

## Layer 5: Logbook

### Files

```
LOGBOOK.md               the logbook, append only
.umwayi/logbook.sha256   SHA-256 of the whole LOGBOOK.md after the last umwayi write
.umwayi/logbook.lock     exists only while an umwayi command is writing
```

### Format

```
# Logbook

## 2026-11-07

- Source: umwayi queue add
- Added: Q-0001 (task) as open: Write the spec
- Checked: ...
- Not done: ...
```

- Line 1 is exactly `# Logbook`. One blank line, then entries.
- An entry is a heading `## YYYY-MM-DD` (a real date), a blank line, then exactly the four fields in this order: Source, Added, Checked, Not done. Each value is one line of plain text, not empty, no spaces at either end.
- One blank line between entries. The file ends with a newline.
- Dates never go backwards. Equal dates are fine.
- Anything else is a problem: text outside the header and entries, a missing or extra blank line, a missing field, fields out of order, a cut off entry, a bad heading, a backwards date, Windows line endings.

### Checked append

`append(root, entry)`:

1. Render the entry. A bad date or a field with a line break is refused before anything is touched.
2. Take the lock: create `.umwayi/logbook.lock` with `O_CREAT | O_EXCL`. If it exists, wait up to 3 seconds, then refuse with a message that names the lock file and says to delete it only if no umwayi command is running. The lock is removed in a `finally` block, and a lock file this call did not create is never removed.
3. Tamper check. Read `LOGBOOK.md` and the record, and refuse unless one of these holds:
   - there is no logbook and no record (a new logbook), or the logbook is empty and there is no record;
   - the SHA-256 of the whole file equals the record.
   Refused states: no record for a non-empty logbook ("run umwayi logbook seal"), a hash that does not match (an earlier line was edited, deleted or added by hand), a record with no logbook (the logbook may have been deleted), and a malformed record (not 64 lowercase hex characters, a folder, or a symbolic link).
4. Format check: the whole file must parse with no problems. The new date must not be before the last entry's date.
5. Append in `ab` mode, `fsync`, then compute the SHA-256 of the whole file and write the record atomically.
6. Release the lock.

If step 5 writes the entry but cannot write the record, the error says so and the next append is refused until the owner seals. The entry is never silently left unprotected.

Every refusal names the reason and ends with "Nothing was written". The text of logbook lines never appears in a message.

### seal

`umwayi logbook seal --by NAME [--date D]` is the only way to accept a logbook that has no record, a malformed record, or a hash that does not match. It is never run automatically. It:

- refuses if there is no logbook, if the logbook is already sealed and intact, if the format has problems, if the date would go backwards, or if `--by` is empty, longer than 100 characters, or not one line;
- appends an entry with source `umwayi logbook seal`, `Seal by NAME`, the number of earlier entries, the SHA-256 of the file before this entry, and what the earlier record state was;
- records the new hash.

Sealing does not prove that earlier lines were never edited. It records that the owner accepted the file as it is now, and the entry says so.

### verify

`umwayi logbook verify` parses every entry and checks the record. It prints `ok: N entries, ...` and exits 0 only when there are no problems. Otherwise it prints `problem: line N: message` (or `problem: record: ...`, `problem: file: ...`) for each problem and exits 1. It never writes, never takes the lock, and never creates `.umwayi/`.

### Layer 2 entries

Every `umwayi check` appends one entry:

```
- Source: umwayi check
- Added: Rule no-money gave No; action type: payment
- Checked: action read as a JSON object without duplicate keys: yes; rules.yaml loaded: yes (6 rules); rules matched: no-money, no-money-amount
- Not done: The action was not run. The action JSON was not stored in the logbook.
```

- The action JSON is never written. Only its `type`, and only if it is a string of 1 to 40 characters from `A-Z a-z 0-9 _ . : -`. Otherwise the entry says `action type not recorded`.
- If the entry cannot be written (tamper check, lock, format, date, disk: any known logbook failure), the reason says "The logbook could not be written", why, and that nothing was logged. Then:
  - No stays No (exit 2) with its rule id. Turning a No into Ask me first would invite the owner to approve something a rule refuses.
  - Yes becomes Ask me first (exit 3) with rule `(none)`. A Yes is never given without its logbook entry.
  - Ask me first stays Ask me first (exit 3).
  - An unexpected error while writing the entry is not a known failure: it exits 2 and prints no answer.
- `--no-log` is a dry run: the rules answer is returned as usual, nothing is written, and the output ends with `Nothing was logged (--no-log, dry run).` With `--json` the output has `"logged": false`.
- `--date` sets the entry date. The default is the system clock.

### Layers 3 and 4

The queue and the archive call the same checked append. If it refuses, the queue change or the move is undone as before, and the error now includes the logbook's reason.

## Layer 6: Automation

Nothing in umwayi installs a schedule. A cron line (or any scheduler the owner picks) calls `umwayi run`. Exit codes for all layer 6 commands: 0 done, 1 refused or failed (nothing changed), 2 No, 3 Ask me first, 64 usage error.

### jobs.yaml and umwayi run

```yaml
jobs:
  - name: weekly-report
    command: report
    since_days: 7
    min_gap_days: 7
  - name: open-queue
    command: queue-list
    status: open
    min_gap_days: 1
```

- Read with the existing `miniyaml` reader. Strict: one `jobs` list, at least one job, unique names (lowercase letters, digits, `-`, up to 40), no unknown fields.
- `command` must be one word from the fixed allow list in `jobs.py`: `report`, `check`, `queue-list`. Each word picks a Python function inside umwayi. There is no field for a shell string, a program or arguments, so a job cannot name another program.
- `min_gap_days`: whole number from 1 to 366. Options per command: `report` needs `since_days` (1 to 366); `check` needs `action_type` (one plain word); `queue-list` may have `status`.
- `umwayi run JOBFILE [--job NAME] [--date D]`. `--job` is needed when the file has more than one job (otherwise a usage error, exit 64).

Order of work:

0. The kill switch (layer 8). If it is on or its state cannot be read, the run stops here with exit 3 and one entry, before the jobs file is read.
1. Read the jobs file and pick the job. A missing or invalid jobs file is a config error (exit 64).
2. Read the logbook through `logbook.read_checked` (tamper check and format check, no lock). If it fails, refuse (exit 1) before anything else.
3. Gap rule: the last run is the latest entry with source `umwayi run` whose Added line starts with `Job NAME ran `. Stopped runs do not count. If fewer than `min_gap_days` days have passed, refuse (exit 1, no entry). A last run after today is also refused.
4. Ask the rules with the action `{"type": "run_job", "job": NAME, "command": WORD}`. No stops the job (exit 2) and Ask me first stops it (exit 3); either way one entry `Job NAME stopped before running` is written. If that entry fails, the verdict still stands and the output says nothing was logged.
5. Do the work: build the report and write the new draft, or read the queue, or check `{"type": action_type}`. Errors here exit 1 and write nothing.
6. Append one entry `Job NAME ran (command WORD): ...`. If that fails, the draft (and a drafts folder this run made) is removed, nothing is printed and the answer is Ask me first (exit 3): a failed logbook means no run.
7. Print the result. A `check` job exits with the inner answer (0, 2 or 3).

So every run that reaches the rules writes exactly one logbook entry.

### umwayi report

`umwayi report --since DATE [--date D]` writes `drafts/report-NNNN.md`.

- The one git command, a list of arguments with `shell=False`, stdin closed, a 30 second timeout and `GIT_TERMINAL_PROMPT=0`:
  `git -C ROOT --no-pager -c core.pager=cat -c core.fsmonitor=false -c log.showSignature=false log --no-merges --no-color --date=short-local --format=%cd%x1f%s --max-count=50001`
- `git log` only reads the local repository: no network, nothing written to git.
- The format asks only for the committer date and the subject, never names or emails. Anything that looks like an email address in a subject is replaced by `[email removed]`. Control characters are removed, and subjects are cut at 200 characters.
- There is no `--since` in the git command: git stops walking at the first commit older than the date, so a commit with an older date on top would hide newer ones. Days from `--since` to today are kept in Python instead. More than 50000 commits is a refusal, never a silent cut.
- The draft lists commits per day (a table) and the subjects per day.
- Numbering: one more than the highest `report-NNNN.md` in `drafts/`. Each file is created with `O_CREAT | O_EXCL`, so an existing file is never overwritten. If a name is taken meanwhile, the next number is tried.
- One logbook entry. If it fails, the draft is removed.

### umwayi publish-draft

`umwayi publish-draft DRAFT [--approved-by NAME] [--date D]` copies the exact bytes of `drafts/NAME.md` (or `.txt`) to `outbox/NAME.txt` for the owner to post by hand.

- Refused before the rules are asked (exit 1, no entry): config missing; the draft is not directly in `drafts/`, has `..`, is a symbolic link, is not a regular file, has another extension, is a private path, is empty, is over 1 MB, is not UTF-8 text, or has a NUL; `outbox` is not a normal folder; the outbox file already exists.
- Then the rules are asked with `{"type": "publish_draft"}`. The starter rule `publish-ask` makes it Ask me first. No stops it (exit 2) even with approval. Ask me first stops it (exit 3) unless `--approved-by NAME` is given. Yes lets it go on. A stop writes one entry.
- The copy is created with `O_CREAT | O_EXCL`, then one entry is written with the SHA-256 of the bytes and who approved it. If the entry fails, the copy is removed and the answer is Ask me first (exit 3).
- It imports no program runner, so it cannot run git or anything else, and it uses no network.

`--approved-by` is the owner's word on the command line. It is not a security boundary against a program that runs as the owner. Layer 7 helpers must never pass it.

## Layer 7: Helpers

AI helpers draft only. They live in `umwayi/helpers/` and import only the standard library and a short allow list of umwayi modules (config, drafts, errors, memory, and through the base: logbook, rules, taskqueue). They never import `publish`, `report`, `jobs` or `cli`, so they cannot publish, run git or call another command. Importing them loads no program runner and no network module; a test checks this in a fresh process.

### The helper base (`helpers/base.py`)

A helper asks for one step at a time: `helper.step(type, work, channel=...)`.

1. The base builds the action `{"type": TYPE, "helper": NAME}` and adds `channel` if given. A helper can give nothing else: any other key is an error before anything is checked. So a helper can never set, build or pass an approval. The helper code does not contain the word "approved" at all, and `umwayi steward --approved-by` and `umwayi social draft --approved-by` are usage errors (exit 64). Tests check all three.
2. The action goes through `rules.check`, the same check as `umwayi check`.
3. No: one logbook entry, stop with exit 2. The work does not run.
4. Ask me first, or anything that is not Yes: one queue item of kind decision, titled `AI helper NAME asks first: may it do TYPE?`, then one logbook entry, then stop with exit 3. If an open decision with that title already exists, no second one is added. If the queue cannot be written, the helper still stops with exit 3 and says so.
5. Yes: the work runs, then one logbook entry. If the work fails with a known refusal, the entry says the step failed and the helper stops with exit 1. If it fails with an unexpected error, the failed step is logged the same way and the error goes on to exit 2. If the entry cannot be written, the work is undone (the draft is removed) and the helper stops with exit 3, or exits 2 if the cause was an unexpected error.

Every checked step adds exactly one logbook entry (source `umwayi steward` or `umwayi social`), written through the checked append. An Ask me first step also adds the queue item's own entry (source `umwayi queue add`), as every queue change does.

Before the first step, `start`:

- reads the logbook through `logbook.read_checked`. If it fails its tamper check or format check, the helper refuses with exit 1 and writes nothing;
- loads rules.yaml. If it is missing or broken, no helper runs: exit 3 (Ask me first), one logbook entry, no step, no draft, no queue item.

Answering a helper's queue item is a record for the owner. It does not let the helper go on. To allow an action, the owner adds a Yes rule in rules.yaml.

### Steward (`umwayi steward [--waiting-days N] [--date D]`)

Steps: `read_queue`, `read_logbook`, `write_draft`. It writes `drafts/steward-NNNN.md` with:

- open items, each with the date it was added (from the `umwayi queue add` logbook entry) or "added date not in the logbook";
- items open longer than N days (strictly longer; default 7, from 1 to 365);
- answered items that are not closed;
- suggested next tasks from fixed rules: answer late decisions (with their recommendation), do or close late tasks, close answered items, answer other open decisions, check rows with no added date. At most 20, then "And N more."

A missing queue.md counts as 0 rows and is not created. A malformed queue.md stops the helper at step 1 (exit 1). Steward never edits the queue, never answers an item and never runs another command. The only queue change during a Steward run can come from the base, when a step is Ask me first.

### Social helper (`umwayi social draft ARTICLE [--date D]`)

Before any step, it refuses (exit 1, nothing written) if: `umwayi.json` has no `social_channels`; the article is outside the root, has `..`, is under `.git` or `.umwayi`, is a symbolic link or inside a linked folder, is a private path, is missing or is not a regular file.

Steps: `read_article`, then one `write_draft` per channel (with `channel` in the action, so a rule can stop one channel).

- The article must start with front matter between two `---` lines with `title` and `link`, and optionally `summary`. No other keys, no repeats. The link must be one `https://` address with no spaces, quotes or `#`. The file must be UTF-8 and at most 200000 bytes.
- The summary is the front matter `summary`, or else the first paragraph after any heading.
- One fixed template: title, blank line, summary, blank line, `Read more: LINK`. Text is cleaned: markdown links become their text, em dashes and en dashes become commas, `#` is removed, `*` and backticks are removed, spacing is collapsed.
- At most 280 characters. A long summary is cut at a word with `...`; if fewer than 20 characters would be left, it is left out. If the title and link alone are too long, the step fails.
- A final check fails closed: no `#`, no em dash, plain text, at most 280 characters, ends with the link line.
- Drafts: `drafts/post-CHANNEL-NNNN.md`, numbered per channel, never overwritten. The file holds only the post text, so `umwayi publish-draft` copies exactly what the owner posts.

There is no model call and no network. The social helper never posts. Publishing stays `umwayi publish-draft`, which is Ask me first for the owner. For a helper, a `publish_draft` action is No.

### Config

`umwayi.json` may have `social_channels`: a list of 1 to 5 names of lowercase letters, digits and `-` (up to 20 characters), with no repeats. It is optional, but a bad value makes the whole config invalid, like any other key.

### Rules

The starter rules.yaml adds:

| id | matchers | verdict |
| --- | --- | --- |
| helper-read | helper present, type read_queue, read_logbook or read_article | Yes |
| helper-draft | helper present, type write_draft | Yes |
| helper-no-post | helper present, type contains post, send or publish | No |

Any other helper action matches no rule and is Ask me first. The older `write-draft` rule also gives Yes for `write_draft`, and comes first in the file, so log entries name it.

## Layer 8: Workflows

### The file

`workflows/NAME.yaml`, read with the existing miniyaml reader. NAME is lowercase letters, digits and `-` (up to 20).

```yaml
name: content-loop
steps:
  - name: collect
    command: queue-list
    status: open
  - name: brief
    command: steward
    waiting_days: 7
  - name: draft
    command: social-draft
    article: articles/week-45.md
  - name: approve
    command: approve
```

- Top keys: `name` (must equal NAME) and `steps` (1 to 20). Nothing else.
- A step has a `name` (unique, same pattern) and a `command` from the fixed allow list in `workflow.py`: `report`, `steward`, `social-draft`, `queue-list`, `check`. `approve` is a fixed step built into the runner, not a command: at most one, and only as the last step.
- Each command takes only its own fixed arguments, written in the file:

| command | arguments |
| --- | --- |
| report | `since_days` (required, 1 to 366) |
| steward | `waiting_days` (optional, 1 to 365, default 7) |
| social-draft | `article` (required, a relative path to one local file) |
| queue-list | `status` (optional: open, answered, closed) |
| check | `action_type` (required, one plain word) |
| approve | none |

- There is no field for a shell string, a program, extra arguments or an approval. Any other key is a problem, so `approved_by` cannot be set anywhere. Each step word maps to exactly one method of the runner (`STEP_FUNCTIONS`); nothing is looked up by name at run time.

### umwayi workflow validate NAME

Reads only. Reports every problem at once, each with the line number of the key or step it is about, sorted by line, then exits 64. A file that is fine prints `ok: ...` and exits 0. Line numbers come from a small line map built from the miniyaml tokens after miniyaml has accepted the text. A YAML syntax error stops parsing, so only that one problem (with its line) is reported. Unknown key names are printed only if they are plain words.

With the root, `social-draft` steps are also checked against `umwayi.json` (it must load and have `social_channels`) and against the article path (inside the root, not private, not a symbolic link, there).

A missing, unreadable, linked, over 64 KB or non UTF-8 workflow file, and a bad NAME, are config or usage errors (exit 64).

### umwayi workflow run NAME [--date D]

The runner is the helper base with the helper name `workflow` (label `Workflow NAME`):

1. `start`: the kill switch, then the logbook tamper check (exit 1), then rules.yaml (exit 3 if broken). See layer 7.
2. Load and validate the workflow file. Any problem is a config error (exit 64) and nothing runs.
3. If an open decision titled `Workflow NAME waits for the owner: ...` exists, the run stops (exit 3, one entry): the last loop still waits for the owner. A malformed queue.md stops the run (exit 1).
4. Each step is one checked action through the helper base:
   `{"type": "workflow_step", "helper": "workflow", "workflow": NAME, "step": STEP, "command": WORD}`.
   No stops with exit 2, Ask me first stops with exit 3 and adds a queue decision, Yes runs the step and adds one logbook entry (source `umwayi workflow`). The kill switch is checked again before every step. If a step's entry cannot be written, its drafts are removed and the run stops with exit 3.
5. The step work, inside umwayi:
   - `queue-list`: read the queue (a missing queue.md is 0 rows).
   - `steward`: the Steward proposal (`steward.proposal`), written to `drafts/steward-NNNN.md`.
   - `social-draft`: the social helper's article check and fixed template, one `drafts/post-CHANNEL-NNNN.md` per channel.
   - `report`: the layer 6 report, written to `drafts/report-NNNN.md`.
   - `check`: `rules.check({"type": action_type})`. Yes goes on; No stops the workflow with exit 2 and Ask me first with exit 3, after the step's own entry.
   - `approve`: see below.

So a step is one rules check and one entry, even when it writes several drafts. Inside a workflow, the Steward and social steps do not repeat their own per-read checks; the one workflow step check covers them. Drafts from earlier steps stay if a later step stops.

### The approve step

It never approves anything. It adds one queue item of kind decision:

- title `Workflow NAME waits for the owner: review N drafts from DATE`;
- recommendation: the drafts written in this run (cut with "and N more" past 300 characters), that the item approves nothing, and that publishing is `umwayi publish-draft DRAFT`, which is Ask me first.

Then the workflow stops with exit 3. Like every queue change, the item has its own `umwayi queue add` entry, next to the step's entry. While the item is open, every new run of that workflow stops at point 3. Answering or closing it only lets the next run start. It publishes nothing, and `umwayi publish-draft` stays Ask me first.

### The kill switch (`umwayi/kill.py`)

`.umwayi/KILL`. `umwayi kill on [--reason TEXT]` creates it, `umwayi kill off` removes it, `umwayi kill status` prints `off` (exit 0), `on` or `unknown` (exit 3).

| state | when |
| --- | --- |
| off | `.umwayi` is missing, or it is a readable folder with no `KILL` in it |
| on | anything named `KILL` exists in `.umwayi`: a file (any content), a folder, a link |
| unknown | `.umwayi` is a file or a link, or it or `KILL` cannot be read |

Fail closed: unknown stops runs exactly like on. Every AI helper (`start` and every step in the helper base), every job (`umwayi run`, before the jobs file is read) and every workflow (through the helper base, before the workflow file is read) stops with exit 3 (Ask me first) and one logbook entry. No rule is asked and nothing is read or written. If the entry cannot be written, the stop still happens and the output says nothing was logged.

- `kill on` creates the file first and then logs. If the logbook is broken, the switch is still on and the output says so (exit 0).
- `kill off` removes the file and then logs. If the logbook cannot record it, the file is put back and the switch stays on (exit 1). It refuses when the state is unknown, or when `KILL` is not a normal file.
- Owner commands (`queue`, `archive`, `check`, `report`, `publish-draft`, `logbook`, `workflow validate`) are not stopped by the switch.

### Rules

The starter rules.yaml adds `workflow-steps` (Yes for `workflow_step` from the helper `workflow` with a command from the allow list or `approve`) and `helper-no-post-command` (No for any helper action whose command contains post, send or publish). Any other workflow step is Ask me first.

## The run lock (`umwayi/runlock.py`)

Every AI helper (steward, social), every job (`umwayi run`) and every workflow (`umwayi workflow run`) holds `.umwayi/run.lock` for its whole run, so two of them never write at the same time. It is one lock for all four, taken with `fcntl.flock(LOCK_EX | LOCK_NB)`:

- Order at the start of a run: the kill switch, then the run lock, then everything else.
- Held by another run: the run does not wait. It answers Ask me first (exit 3), writes one logbook entry ("another umwayi run holds the run lock") and changes nothing else.
- Locking not available (no `fcntl`, for example on Windows), the OS refusing the lock, `.umwayi` not a normal folder, or `run.lock` a link or a folder: fail closed, Ask me first (exit 3), one entry.
- Released on every exit path: the helper base releases it in a `finally` (`Helper.finish`), the job runner holds it in a `with` block, and the operating system releases it if the process dies.
- The file is never deleted, because deleting a flock file lets two processes lock two different files with the same name.
- Owner commands (queue, archive, check, report, publish-draft, logbook, kill, workflow validate) do not take it.

It is separate from `.umwayi/logbook.lock`, which guards one logbook append.

## Layer 9: Adapters (built)

Planned for Nov 8 to Nov 9. Part 1 (PR 11): the notes, the shared code and the Claude Code adapter. Part 2 (PR 12): the Kiro adapter, the generic stdin and stdout adapter, and the kill switch in all three adapters. Still open: starter rules in the repo rules.yaml (9.10) and the whole-system test with the adapters (9.11).

### What the platforms say

`adapters/NOTES.md` has what the official Claude Code hooks reference and the Kiro hook pages say, with a link for every fact, and the action types the adapters send. The adapters are built from those notes. Where a page is silent or the pages disagree, the notes say so and the adapter blocks.

The facts that shape the Claude Code adapter: exit 2 blocks a PreToolUse call; exit 1 and every other code let it run; a hook that cannot start or times out also lets it run, unless the handler sets `"onFailure": "block"`; an exit 0 JSON object with `permissionDecision` allow, deny or ask decides.

The facts that shape the Kiro adapter: exit 0 allows and exit 2 blocks a Pre Tool Use call in every version of the text; the pages disagree about other exit codes (the IDE tab says any non zero blocks, the Hook types page and the CLI tab say they warn and allow); there is no ask and no JSON decision; stdout on exit 0 goes into the agent's context; the `tool_input` field names are not shown; nothing like `onFailure` is documented. So the Kiro adapter uses only exit 0 and exit 2, prints nothing on allow, and forwards every top level string field of `tool_input`.

### Layout

```
adapters/
  NOTES.md            what the platform docs say, the action types, the answer table
  common/
    umwayi_gate.py    tool call to action JSON, umwayi check as a child process, answer to allow, deny or ask
  claude_code/
    hook.py           the PreToolUse hook script
    README.md         set up, the settings snippet (shown only, never written), no packages
    rules.example.yaml
  kiro/
    hook.py           the Pre Tool Use command action: exit 0 or exit 2 only
    README.md         set up, the .kiro/hooks snippet (shown only, never written), what is not confirmed
    rules.example.yaml
  stdio/
    hook.py           the generic adapter: JSON in, one JSON line out, exit 0, 2 or 3
    README.md
    rules.example.yaml
tests/adapters/       real child process tests per adapter
```

The core `umwayi/` package stays standard library only and never imports `adapters`; the adapters never import `umwayi`, they run it as a child process. A test checks both directions. No adapter needs a third party package, so their tests run in the normal CI job; a separate job is only needed once an adapter pins a package.

### The umwayi root is given, never guessed

The hook takes `--root DIR` (required). It never uses the `cwd` field of the hook input, because an agent can change its working folder, for example into a folder with a `rules.yaml` that allows everything.

### One check, fail closed

Each adapter does the same five things:

1. Read the platform's hook input from stdin, with a size limit. Anything it cannot read blocks.
2. Turn it into an action: `{"type": "tool_bash", "platform": "claude-code", "tool": "Bash", "command": ...}`. The type is `tool_` and the tool name. For Claude Code the fields are a fixed per tool list (command, path, pattern, url, query); file contents and prompts are never sent (`tool_action`). For Kiro and the generic adapter, whose field names are not documented, every top level string field with a plain key is sent as `input_<key>` (`generic_action`); the prefix means it can never replace `type`, `platform` or `tool`. Every type and field is in `adapters/NOTES.md`. `umwayi check` logs only the type, never the action.
3. Run `umwayi check - --json --kill-switch` as a separate process, with a timeout (default 10 seconds, shorter than the 30 second hook timeout in the settings snippet).
4. Turn the answer into the platform's reply (table below).
5. Catch every error at the top and block: exit 2, or the platform's deny, whichever the platform documents as blocking.

Allow is given only for a positive, well formed answer: exit 0, answer Yes, `rules_ok` true and `kill_switch` off. Everything else is not allow.

| what umwayi says | platform with ask | platform without ask |
| --- | --- | --- |
| kill switch on or unknown | deny | deny |
| Yes (exit 0) | allow | allow |
| No (exit 2) | deny | deny |
| Ask me first (exit 3) | ask | deny, and one queue item of kind decision |
| rules.yaml missing or broken (`rules_ok` false) | deny | deny |
| a crash, a timeout, any other exit code, output that is not the expected JSON | block | block |

For the queue item where the platform has no ask, the adapter runs `umwayi queue add --kind decision TITLE --recommendation TEXT --if-not-open` with a fixed title, `Kiro asks first: may it do TYPE?` or `The NAME platform asks first: may it do TYPE?` (generic adapter with `--no-ask`). `--if-not-open` adds nothing while an open item of the same kind has exactly that title. If the queue item cannot be added, the answer is still deny and the reason says so. Answering the item does not allow the call; the owner adds a Yes rule for that.

Platform replies:

| | Claude Code | Kiro | generic |
| --- | --- | --- | --- |
| allow | exit 0, JSON `allow` | exit 0, empty stdout | exit 0, `{"decision": "allow"}` |
| deny | exit 0, JSON `deny` | exit 2, reason on stderr | exit 2, `{"decision": "deny"}` |
| ask | exit 0, JSON `ask` | exit 2 and a queue item | exit 3, `{"decision": "ask"}`; with `--no-ask` exit 2 and a queue item |
| error | exit 2, reason on stderr | exit 2 | exit 2, a deny line if it can be written |

### The kill switch stops the adapters (decision 9.12)

The owner decided that every adapter denies everything while the kill switch is on. It is checked twice:

1. Core: `umwayi check --kill-switch` answers No while `.umwayi/KILL` is on or its state is unknown. The logbook entry says "The kill switch gave No" and "kill switch: on" (or unknown). The check lives in `cli.py`, not in `rules.py`, because layer 2 must not import layer 8. Without the flag, `umwayi check` is unchanged: the owner's own commands are not stopped.
2. Adapter: `check --json` always has `"kill_switch": "off"|"on"|"unknown"`, and `decide()` denies unless it is `off`, before anything else.

Rejected: the adapter reading `.umwayi/KILL` itself (the logic twice, and no logbook entry), and a separate `umwayi kill status` child (one more process per tool call).

### Core changes for layer 9 (done)

`umwayi check --json` now also prints `rules_ok` (true only when rules.yaml was read and is valid) and `action_ok` (true only when the action was a readable JSON object), next to `answer`, `rule_id` and `logged`. An adapter reads these fields, never the reason text. No exit code changed. When the logbook cannot be written, the answer `umwayi check` gives has `rules_ok` false, so an adapter denies it; that is stricter than `umwayi check` on its own.

Part 2 adds two options, both off by default, so nothing that worked before changes:

- `umwayi check --kill-switch`: see above. `--json` gives `kill_switch` with or without the flag.
- `umwayi queue add --if-not-open`: if an open item of the same kind with exactly the same title exists, nothing is added, it prints `Already open, nothing added: Q-...` and exits 0 (`taskqueue.find_open`, `taskqueue.add_once`).

### Tests per adapter

Run as real processes with recorded hook inputs: No blocks, Ask me first asks (or denies and adds one queue item, once), Yes passes, a broken rules file blocks, the kill switch on or unknown blocks, a crash, a hang or Ctrl-C in the adapter or in `umwayi check` blocks (injected with `UMWAYI_FAULT` through a sitecustomize file, `tests/adapters/support.py`), `--root` is never taken from the input, and no file in `.claude` or `.kiro/hooks` is created. With planted faults and mutation checks (listed in PR 11 and PR 12).

### Open questions for the owner

- Answered: adapters deny everything while the kill switch is on (yes, built in PR 12).
- Which tools of each platform get which action types, and which of those are Yes in the starter rules.

## Layer 10: Own command line and chat (designed, waiting for owner approval)

Planned for Nov 9 to Nov 10, built only after the owner approves (tasks.md 10.0). Requirements: 10.R1 to 10.R10 in requirements.md. Doc facts with links: `adapters/NOTES-layer10.md`.

### The idea in one paragraph

umwayi does not talk to a model. It starts the platform's own program (`claude` or `kiro-cli`) with the layer 9 hook in front of every tool call, and it refuses to start one when it cannot confirm that hook is in place. For Claude Code, umwayi adds the hook itself for one session with `--settings`, so no file changes. For Kiro, no such flag is documented, so the owner adds the hook file once (the layer 9 README snippet) and umwayi checks it, read only, before every start. Chat is the platform's own interactive screen, or for Kiro a small ACP client in umwayi that also answers permission requests through the rules.

### Layout

```
umwayi/
  agents.py        agents.yaml loader and validator, the fixed platform table,
                   argument lists, the gate checks, start, watch and stop
  acp.py           a small ACP v1 client over stdio (Kiro chat only)
  cli.py           umwayi agent list | validate | check | run | chat
agents.example.yaml
adapters/
  NOTES-layer10.md what the docs say (written with this spec)
tests/agents/      real child process tests, fake claude and kiro-cli
```

Both new core modules are standard library only (`subprocess`, `json`, `shutil`, `signal`, `threading`, `selectors`, `re`, `pathlib`). Neither imports `adapters`: the core knows the path of each layer 9 hook script and runs it as a child process, the way the platform will. No third party package is needed for Dec 3, so no adapter package is added in this layer (10.R9).

Rejected: putting the launcher in an adapter package that the core runs (one more process and one more place a check can be skipped, and the core must own the rules check anyway); using an ACP SDK package (not needed for the few messages used, and it would make the core depend on a third party package).

### agents.yaml

```yaml
agents:
  - name: reviewer
    platform: claude-code
    command: claude
    workdir: /home/me/projects/site
    max_turns: 20
    timeout_minutes: 30

  - name: kiro-helper
    platform: kiro
    command: kiro-cli
    transport: acp
    workdir: /home/me/projects/site
    kiro_agent: site-agent
    trust_tools: [read_file, grep_search]
```

The platform table in `agents.py` is the only place that knows platforms:

| platform | allowed `command` | transports | layer 9 hook | minimum version |
| --- | --- | --- | --- | --- |
| `claude-code` | `claude` | `cli` | `adapters/claude_code/hook.py` | 2.1.295 (`onFailure`) |
| `kiro` | `kiro-cli` | `cli`, `acp` | `adapters/kiro/hook.py` | 2.27.1 (hooks in V3 headless runs) |

`trust_tools` IDs come from a fixed list of the built-in Kiro tool IDs the Kiro docs name: `read_file`, `grep_search`, `execute_bash`, `execute_pwsh`, `fs_write`, `fs_append`, `str_replace`, `delete_file`. Anything else is a validation error.

Validation follows `umwayi workflow validate`: every problem with its line number, never the line text, exit 64.

### One start, step by step

`umwayi agent run NAME` and `umwayi agent chat NAME` do the same steps; the first that fails ends it.

| step | on failure | exit |
| --- | --- | --- |
| 1. read and validate agents.yaml, find NAME, read the prompt (`run`) | message | 64 |
| 2. the kill switch is off | logbook entry | 3 |
| 3. rules: action `agent_run` (one logbook entry) | No: 2. Ask me first: queue item `Start agent NAME (MODE)?` (`taskqueue.add_once`) | 2 or 3 |
| 4. take the run lock | logbook entry | 3 |
| 5. gate checks (below) | logbook entry "Refused, not gated: REASON" | 2 |
| 6. build the argument list from the platform table | (a bug: crash) | 2 |
| 7. logbook entry "Started agent NAME", then start the child | logbook entry if it cannot start | 2 |
| 8. watch: kill switch every second, the timeout (`run`) | stop the child, logbook entry | 3 (kill), 2 (timeout) |
| 9. the child exits: logbook entry with its exit code and duration | | 0 if the child exited 0, else 2 |

The steps are wrapped so that every exception stops the child (if one is running), writes a logbook entry if it can, and exits 2. Nothing exits 1.

The order matters: the kill switch and the rules come before any process is started, including `claude -v`, so a No or a kill switch never runs platform code.

### Gate checks (10.R6)

1. **Command on PATH.** `shutil.which(command)`; the absolute path is used for everything after, and logged.
2. **Version.** Run `PATH_FOUND -v` (Claude Code) or `PATH_FOUND --version` (Kiro), no shell, 10 second timeout, stdin closed. Take the first `N.N.N` in stdout. If there is none, or it is lower than the minimum: refuse. The docs do not give the output format, so this is the check most likely to need a fix after a real run.
3. **Hook script.** The layer 9 hook file exists and is a regular file.
4. **Hook self-test.** Run `PYTHON HOOK --root ROOT` with stdin `{"hook_event_name": "UmwayiSelfTest", "tool_name": "x", "tool_input": {}}` and a 5 second timeout. Both layer 9 hooks block an event other than `PreToolUse` with exit 2 before they read any rule, so this proves Python and the hook start, and writes nothing. Anything but exit 2: refuse.
5. **Kiro hook file** (Kiro only). Read every `*.json` in `WORKDIR/.kiro/hooks/` and `~/.kiro/hooks/` (regular files under 256 KB; anything unreadable is skipped and named in the refusal). Accept if one has `version: "v1"` and a hook with `trigger: "PreToolUse"`, no `matcher` or `"*"`, and `action: {"type": "command", "command": C}` where C split on single spaces is exactly `[PY, HOOK, "--root", ROOT]`, PY being `python3` or an absolute path whose name starts with `python`. If none: refuse, and print the snippet from `adapters/kiro/README.md` with the real paths filled in. The front door never writes these files.

`umwayi agent check NAME` runs steps 1, 2 and 5 of a start (reading agents.yaml, the kill switch, the gate checks), without the rules check and the run lock, starts no agent, and prints one line per check.

### Argument lists (10.R5)

Built only in `agents.py`, as Python lists, from the platform table and the validated fields; nothing from agents.yaml is pasted into a string.

| | argument list |
| --- | --- |
| Claude Code run | `[CLAUDE, "-p", "--permission-mode", "default", "--settings", JSON, ("--max-turns", N), PROMPT]` |
| Claude Code chat | `[CLAUDE, "--permission-mode", "default", "--settings", JSON]` |
| Kiro run | `[KIRO, "chat", "--v3", "--no-interactive", ("--agent", A), ("--trust-tools=" + ",".join(IDS))]`, prompt on stdin |
| Kiro chat, cli | `[KIRO, "chat", "--v3", ("--agent", A)]` |
| Kiro chat, acp | `[KIRO, "acp", "--agent-engine=v3"]` |

The Claude Code `--settings` JSON, built with `json.dumps` from a fixed dict:

```json
{"disableAllHooks": false,
 "hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{
   "type": "command", "command": "/usr/bin/python3",
   "args": ["/path/umwayi-os/adapters/claude_code/hook.py", "--root", "/path/root"],
   "timeout": 30, "onFailure": "block"}]}]}}
```

- `disableAllHooks: false` at the command line level wins over a `true` in user, project and local settings. Hooks merge, so the owner's other hooks still run; if they disagree, the strictest answer wins (layer 9).
- `--permission-mode default` overrides a `defaultMode` from settings files, so no settings file can start the run in `bypassPermissions`.
- The Claude Code prompt is the last argument. A prompt starting with `-` is refused (exit 64): the docs say nothing about `--`. The prompt is visible to other users of the machine in the process list; KNOWN-LIMITS will say so.
- Kiro: the prompt goes on stdin (documented), never as an argument. `--v3` always, because only V3 headless runs are documented to load hooks. `--trust-all-tools` never: in a headless run a tool runs only if the rules say Yes and it is in `trust_tools`.

A test builds every list for every valid agents.yaml shape and checks that none contains a forbidden flag (10.R5.7).

### Starting, watching and stopping

- `subprocess.Popen(list, cwd=workdir, shell=False)`, environment inherited unchanged. For `run`: stdin is the prompt (Kiro) or closed (Claude Code), stdout and stderr are passed through to umwayi's own.
- `run` starts the child in a new process group (`start_new_session=True`) so umwayi can stop it and its children with `os.killpg`. `chat` with `transport: cli` keeps the child in umwayi's process group and on the terminal, because an interactive screen needs the controlling terminal; umwayi ignores SIGINT while it waits, so Ctrl-C reaches the agent only.
- A watcher thread checks `kill.state(root)` every second. On `on` or `unknown`: SIGTERM to the child (group), SIGKILL after 10 seconds. Claude Code `-p` is documented to stop cleanly on SIGTERM (exit 143); Kiro is not documented.
- If umwayi gets SIGTERM, it stops the child the same way before it exits.
- The run lock is held from step 4 to the end.

### ACP chat client (`umwayi/acp.py`, Kiro only)

Small on purpose: about the messages in NOTES-layer10.md, nothing else.

1. Start `kiro-cli acp --agent-engine=v3` with pipes; stderr goes to umwayi's stderr.
2. Read the agent's stdout line by line (each line at most 4 MB; one JSON object; else stop, exit 2). Register the handlers before `session/new`.
3. Send `initialize`: `protocolVersion: 1`, `clientCapabilities: {}` (no `fs`, no `terminal`), `clientInfo: {"name": "umwayi"}`. A version other than 1 in the answer, or an error: stop, exit 2. An authentication-required error: print "Sign in with kiro-cli login, then try again", exit 2.
4. `session/new` with `cwd: WORKDIR`, `mcpServers: []`. `kiro_agent` is not accepted with `transport: acp` (validation error), because V3 rejects `--agent` on `acp` and the docs do not say how to pick an agent in a session (open question 7).
5. Print the open queue summary, then read a line from the owner. `:quit` ends; `:queue` prints the open queue; any other line is sent as `session/prompt` with `prompt: [{"type": "text", "text": LINE}]`.
6. While the turn runs:
   - `session/update` `agent_message_chunk` text: printed after `safe_text` (C0 and C1 control characters other than newline and tab, and bidirectional, zero-width and tag characters, shown as `\u....`).
   - `tool_call`: one line, `tool: TITLE [KIND]`, through `safe_text`. Other update types are ignored.
   - `session/request_permission`: the rules decide (below).
   - Any other request: JSON-RPC error `-32601` (method not found).
   - The `session/prompt` answer ends the turn; its `stopReason` is shown.
7. Ctrl-C: send `session/cancel`, answer open permission requests with `cancelled`, wait up to 10 seconds for the prompt answer.
8. The kill switch watcher, as above: cancel, close the agent's stdin, stop it, exit 3.

Permission answer:

| rules say | umwayi selects |
| --- | --- |
| Yes | the first option with `kind: allow_once` |
| No | the first option with `kind: reject_once` |
| Ask me first | asks the owner `Allow once? [y/N]`; `y` selects `allow_once`, anything else `reject_once` |
| no option of the needed kind, anything unclear, an error | `reject_once`, or `cancelled` if there is no reject option |

The action is `{"type": "acp_permission", "agent": NAME, "platform": "kiro", "kind": KIND, "tool": NAME}` with `kind` and `tool` only when they are short plain words (`tool` is the tool call's `name`, which ACP calls informational). The agent-written `title` is never put in the action, because ACP says not to approve on the title. `allow_always` and `reject_always` are never selected, so the agent never stores a decision that would skip the next check.

### Logbook entries

All through `logbook.Entry`, written before the step they describe:

| when | entry |
| --- | --- |
| rules check | the usual check entry, action type `agent_run` or `acp_permission` |
| refused | "Refused agent NAME: not gated (REASON)" |
| start | "Started agent NAME (PLATFORM, TRANSPORT): PATH_FOUND" |
| end | "Agent NAME exited CODE after SECONDS s" |
| kill switch | "The kill switch stopped agent NAME" |
| timeout | "Agent NAME stopped after its timeout of MINUTES min" |

Never logged: the prompt, the conversation, agent output, environment values, the `--settings` JSON beyond the hook path.

### Exit codes

| | exit |
| --- | --- |
| Yes, gated, the agent exited 0 | 0 |
| No; not gated; logbook not writable; the agent exited non-zero; timeout; ACP error; umwayi crash | 2 |
| Ask me first; kill switch on or unknown (before or during); run lock held | 3 |
| bad arguments; agents.yaml missing or invalid; unknown name; a prompt that cannot be passed safely | 64 |

### Tests (tasks.md 10.x)

- Fake agents in `tests/agents/fakes/`: `claude` and `kiro-cli`, Python scripts written into a temporary folder that is put first on `PATH`. They record argv, cwd, the environment keys (not values) and stdin to a JSON file, print a version, and act like the docs:
  - fake `claude -p`: reads `--settings`, and for each tool call in a script file runs the hook from `hooks.PreToolUse` exactly as configured (exec form, stdin JSON, timeout) and records allow, deny or ask; exits 0. A mode where it ignores hooks lets a test prove that umwayi alone cannot detect that (KNOWN-LIMITS).
  - fake `kiro-cli chat --no-interactive`: reads the instruction from stdin, runs the hook command from the hook file it finds the same way Kiro would, records exit 0 or 2.
  - fake `kiro-cli acp`: a scripted ACP agent: answers `initialize` and `session/new`, sends updates, sends `session/request_permission` with given options, checks the answer, can send garbage, a wrong version or an unknown request.
- Every test runs `python -m umwayi agent ...` as a child process in a temporary root.
- Planted faults and mutation checks per part, listed in each pull request.

### Open questions for the owner

1. Run lock: should `agent run` and `agent chat` take the shared run lock (one AI run at a time, proposed), or may an agent run while jobs and helpers run?
2. Ask me first for a start: a queue item (proposed, so a job that starts an agent leaves a trace), or exit 3 only?
3. Kiro headless: only `trust_tools` (proposed), or also allow `--trust-all-tools` so the hook is the only gate?
4. Claude Code under a managed policy that blocks our hook: umwayi cannot see it. Accept it as a known limit for Dec 3 (proposed), or add a canary (for example a `SessionStart` hook in `--settings` that must write a token before umwayi lets the run continue)? The docs do not say whether `SessionStart` runs before the first tool call, so the canary is not confirmed to work.
5. `workdir` may not be or contain the umwayi root (proposed). Is there a case where you want an agent working in the root?
6. ACP chat Ask me first: ask on the terminal (proposed, you are there), or deny plus a queue item like the Kiro hook?
7. Selecting a Kiro agent in an ACP session: V3 rejects `--agent` on `acp`; the docs show `_meta.kiro.modeId` on `session/new` but do not say a mode is an agent. Leave `kiro_agent` out of ACP chat for Dec 3 (proposed) or try `modeId`?
8. An agent's own failure is exit 2 (proposed). Should it keep the agent's own exit code instead (it would break the 0, 2, 3, 64 rule)?
9. After Dec 3: Claude Code over ACP through Zed's `claude-agent-acp` adapter (a third party Node package, so an adapter package with a pinned version)?
10. `--max-budget-usd` for Claude Code runs now, or leave all spend limits to the budget governor (proposed)?

### Risks

| risk | what happens | what we do |
| --- | --- | --- |
| a managed Claude Code policy blocks non-managed hooks | the agent runs ungated and umwayi cannot see it | KNOWN-LIMITS; open question 4 |
| Kiro hooks are not loaded in a mode (ACP, a new version) | tool calls are not checked | refuse unless the hook file is found; NOTES lists ACP hooks as not confirmed; first real run checks it |
| version output format differs | every start is refused | fail closed; one function to fix |
| a fake `claude` or `kiro-cli` earlier on PATH | umwayi starts the wrong program, with our hook in front of it | the full path is printed and logged; layer 11 permissions |
| the agent edits its own guard (`.kiro/hooks`, rules.yaml) | the next start may have no hook, or a weaker rule | the gate check runs before every start; example deny rules; layer 11 Unix permissions (KNOWN-LIMITS 15) |
| the Claude Code prompt is in the process list | other local users can read it | KNOWN-LIMITS; Kiro uses stdin |
| a tool call already running when the kill switch goes on | it finishes, up to 1 second plus the stop time | adapters deny every new call at once (9.12) |
| interactive chat on the terminal | umwayi sees no tool call, only the hook does | by design: the hook is the gate; ACP chat adds a second gate |
| Kiro docs conflict (`content` and `prompt` in `session/prompt`) | the first ACP prompt fails | we follow the spec; the error ends the chat with exit 2, nothing ungated |
| schedule: layers 10 and 11 share Nov 9 to 10 | not all parts land | parts 1 and 2 need no agent and can go first; ACP chat (part 6) is the one to cut |

## Layer 11: Linux-like features (outline, planned Nov 9 to Nov 10)

Built only after the owner approves its requirements, design and tasks. Each feature reuses a tool Linux already has. umwayi only writes the configuration and keeps the rules, queue and logbook in front of it.

| feature | reuse | what umwayi adds |
| --- | --- | --- |
| scheduling | cron or systemd timers | writes the timer lines that call `umwayi run` or `umwayi workflow run`; installs nothing without the owner |
| file watching | inotify | turns a file event into a checked action, for example a new article starts the content loop |
| process limits | Unix permissions, bubblewrap or containers | runs AI helpers with fewer rights than the owner, so the kill switch and the logbook are harder to bypass |
| a small database | SQLite | an index for questions over the queue, logbook and archive; the plain files stay the source of truth |
| terminal sessions | tmux | named sessions for long running agents, started through the layer 10 front door |

No new scheduler, file system or shell is built.

## Budget governor (outline, planned Nov 15 to Nov 21)

The owner decided to build it before Dec 3. Built only after the owner approves its requirements, design and tasks. The design is written then; nothing about it is decided here except that it fails closed and logs every change like the other layers.

## Testing

- Standard library `unittest`, also run by `pytest`.
- Each layer has its own test module, using temporary folders.
- CI (`.github/workflows/ci.yml`) runs `python -m unittest discover -s tests -t .` on every pull request, on Python 3.10, 3.11, 3.12 and 3.13. After PR 9 there are 556 tests.
- `tests/test_system.py` runs the umwayi command as real processes in a fresh folder: one scripted run of every layer, and fault tests (logbook edits, broken rules, bad config, injected crashes in every command, corrupt state files, unknown actions, no network import, no approver code path).
- Mutation checks: for each layer, faults are put into the code on purpose and the tests must fail. PR 9 also showed the system test failing for three faults (no run lock, no kill switch check, check exiting 1 on an error).
- Layer 9 adapters get their own tests and CI job (see above).
