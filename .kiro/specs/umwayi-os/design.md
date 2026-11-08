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
  helpers/      layer 7 (later)
  workflows/    layer 8 (later)
```

Layers 2 to 6 write to the logbook through one function, `logbook.append(root, Entry)`. It takes the lock, runs the tamper check, the format check and the date check, appends, and records the new hash. No layer writes `LOGBOOK.md` any other way. The module is named `taskqueue.py`, not `queue.py`, because a file named `queue.py` inside the package would shadow the standard library `queue` when a file in the package is run directly.

## Safety model

- Fail closed everywhere. Parsers are strict: unknown keys, duplicate keys, bad types and unsupported syntax are errors, not guesses.
- Errors never echo file content. They name the problem and a line number, not the text.
- Private paths are matched case-insensitively and on every parent folder, so a rule for `memory/private` also blocks a file below it.
- Exit codes of `umwayi check` are reserved: 0 Yes, 2 No, 3 Ask me first. All other usage errors exit 64, and runtime errors of other commands exit 1.
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

`check` never raises. Any unexpected error is turned into Ask me first.

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
- If the entry cannot be written for any reason (tamper check, lock, format, date, disk, an unexpected error), the reason says "The logbook could not be written", why, and that nothing was logged. Then:
  - No stays No (exit 2) with its rule id. Turning a No into Ask me first would invite the owner to approve something a rule refuses.
  - Yes becomes Ask me first (exit 3) with rule `(none)`. A Yes is never given without its logbook entry.
  - Ask me first stays Ask me first (exit 3).
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

1. Read the jobs file and pick the job.
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

## Layers 7 and 8 (planned)

- Helpers: each helper action is built as an action JSON and sent to `umwayi check`. Only Yes continues, and even then the result is a draft.
- Workflows: files in `workflows/` listing steps. A flag file `KILL_SWITCH` stops every run. If the flag cannot be read, the run stops.

## Testing

- Standard library `unittest`, also run by `pytest`.
- Each layer has its own test module, using temporary folders.
- CI (`.github/workflows/ci.yml`) runs `python -m unittest discover -s tests -t .` on every pull request, on several Python versions.
