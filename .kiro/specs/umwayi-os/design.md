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
```

Layers 2 to 8 write to the logbook through one function, `logbook.append(root, Entry)`. It takes the lock, runs the tamper check, the format check and the date check, appends, and records the new hash. No layer writes `LOGBOOK.md` any other way. The module is named `taskqueue.py`, not `queue.py`, because a file named `queue.py` inside the package would shadow the standard library `queue` when a file in the package is run directly.

## Safety model

- Fail closed everywhere. Parsers are strict: unknown keys, duplicate keys, bad types and unsupported syntax are errors, not guesses.
- Errors never echo file content. They name the problem and a line number, not the text.
- Private paths are matched case-insensitively and on every parent folder, so a rule for `memory/private` also blocks a file below it.
- Exit codes, for every command:
  - 0: Yes, or done.
  - 1: a refusal. Something was checked and found wrong (a malformed queue.md, an id that does not exist, a tampered logbook) and nothing was changed.
  - 2: No. Also every unexpected error: `main` catches every exception (and Ctrl-C) and exits 2, so a crash is never read as Yes or as a non blocking error by a hook. The message is not printed, only the error type, because it may hold file content.
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
5. Yes: the work runs, then one logbook entry. If the work fails, the entry says the step failed and the helper stops with exit 1. If the entry cannot be written, the work is undone (the draft is removed) and the helper stops with exit 3.

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

## Testing

- Standard library `unittest`, also run by `pytest`.
- Each layer has its own test module, using temporary folders.
- CI (`.github/workflows/ci.yml`) runs `python -m unittest discover -s tests -t .` on every pull request, on several Python versions.
