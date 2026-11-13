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

Layers 1 to 8 are built (PRs 1 to 8, hardening in PR 9). Layer 9 adapters live outside the core package, in `adapters/`, so they, and layer 10 adapter packages, may use third party packages, pinned and listed in their README, while `umwayi/` stays standard library only. Layers 10 and 11 (layer 10 parts 7c-2 and 7c-3 planned Nov 12 to Nov 13, after logbook crash safety on Nov 10 to Nov 11; layer 11 planned Nov 14 to Nov 15; each built only after the owner approves its requirements, design and tasks) and the budget governor (approved Nov 9, planned Nov 17 to Nov 22, after the logbook hash chain on Nov 16) are outlined at the end of this file.

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

### Hash chain (addendum, approved by the owner on Nov 9, tasks.md C.0; built in PR 32)

Requirements: Layer 5, "Logbook hash chain". Tasks C.1 to C.4, one day on Nov 16, after crash safety (L-Q6); built early, in PR 32. Only `umwayi/logbook.py` and `umwayi/cli.py` change; nothing else writes the logbook directly.

#### Added while building (PR 32)

- The chained text is the entry's lines from its `## DATE` heading through `- Not done:`, each with its newline (the blank line after the heading included). The value is `sha256(prev + "\n" + text)`.
- The first chained entry must be a seal entry (source `umwayi logbook seal`). Any other entry with a Chain line before the start is a problem: "an entry before the start of the chain has a Chain line".
- A plain `umwayi logbook seal` of a logbook with no chain always starts it. `seal --chain` is needed only for a logbook that is already sealed and intact, and is refused once a chain exists (C-Q1).
- `seal` refuses a broken chain: "restore LOGBOOK.md from a copy you trust (for example git)". Sealing over it or starting a new chain was rejected, because it would hide the edit.
- `read_checked` (jobs, workflows and helpers) also refuses a broken chain (fail closed).
- The chain information in `verify` (started or not, its length) goes in a new `Report.chain_note`, not in `notes`, so the crash safety reports keep `notes` for interrupted writes only.
- Places: a value that does not match is reported at the entry's Chain line; a missing Chain line at the entry's heading.
- `umwayi logbook anchor` exits 2 when the logbook does not verify or has no chain; a malformed `--anchor` is 64. The chain alone does not find a truncated tail; the whole-file hash record or `verify --anchor` ("shorter") does.

#### Format

```
## 2026-11-15

- Source: umwayi queue add
- Added: Q-0042 (task) as open: Write the README
- Checked: ...
- Not done: ...
- Chain: 3f1c...e9 (64 lowercase hex)
```

- An entry has four fields (unchained, only before the first chained entry) or five fields, Chain last.
- `chain(prev, text) = sha256((prev + "\n" + text).encode("utf-8")).hexdigest()`, where `text` is the entry's lines from `## DATE` through `- Not done: ...`, each followed by `\n`. The blank lines between entries are not part of `text`; the whole-file hash still covers them.
- **Genesis:** the previous value of the first chained entry is `sha256` of the file bytes before that entry. The verifier recomputes it from that prefix, so nothing extra is stored. The seal entry already prints that same hash in its Added text ("its SHA-256 before this entry was ..."), which makes it visible to a reader too.
- `render()` adds the Chain line; `parse()` accepts four or five fields and records where chaining starts.

#### Starting the chain

- **An unsealed logbook:** `umwayi logbook seal --by NAME` writes the seal entry as the first chained entry, as it does today plus the Chain line.
- **A logbook that is already sealed and intact** (every logbook today): seal refuses it now ("already sealed and intact"). Proposed (C-Q1): `umwayi logbook seal --chain --by NAME` is allowed exactly once on such a logbook, writes a seal entry "the hash chain was started" as the first chained entry, and is refused when a chain already exists.
- Until the owner runs it, appends stay unchained, and `verify` says "the hash chain is not started".

#### Checked append and check_writable

Under the existing lock and after the whole-file hash check:

1. parse once;
2. walk the chain from its start and keep the newest Chain value;
3. refuse with "LOGBOOK.md: the hash chain is broken at entry N (line L). Nothing was written." if any value differs, or if an entry after the start has no Chain line;
4. append the new entry with `chain(newest, text)`;
5. record the whole-file hash as today.

The cost is linear in the file size; the logbook is small (C-Q2 for a cached newest value).

#### verify

- Prints one problem per finding with the entry number and line number. A broken chain prints only the first broken entry, because every later value follows from it.
- Never prints a logbook line, a field value, or the expected or found Chain value of a broken entry.
- New messages:
  - `the hash chain is not started`: information, not a problem;
  - `entry N (line L): the Chain value does not match`;
  - `entry N (line L): the entry has no Chain line but comes after the start of the chain`;
  - `entry N (line L): an entry before the start of the chain has a Chain line`.
- `--anchor COUNT:HEX`: a problem when the chain has fewer than COUNT chained entries ("the chain is shorter than the anchor"), or when the Chain value of entry COUNT differs ("the chain differs from the anchor at entry COUNT"). A malformed anchor is a usage error (64).
- Exit codes stay as in Layer 5.

#### anchor

- `umwayi logbook anchor` prints `COUNT:HEX` (the number of chained entries and the newest Chain value) and one line saying where to keep it: the hub repo sync log and the Kiro Notion page, weekly and before each submission.
- It refuses (exit 2) when the logbook does not verify, so a broken chain is never anchored. It writes nothing.

#### Agent starts

`logbook.check_writable` is already called before every agent start and every second while an agent runs (10.R3, 10.R4), so a broken chain stops a start with exit 2 and stops a running agent with exit 2 through the existing watcher, with no new code in agents.py.

#### KNOWN-LIMITS (written with C.4: docs/KNOWN-LIMITS.md items 3 and 104 to 109)

"Without an outside anchor, anyone who can write LOGBOOK.md and .umwayi/logbook.sha256 can rewrite the whole chain consistently, and verify cannot tell. Anchor weekly and before each submission: copy `umwayi logbook anchor` into the hub repository's sync log and onto the Kiro Notion page, then check with `umwayi logbook verify --anchor COUNT:HEX`. umwayi never writes to either place."

#### Open questions (chain, answered Nov 9)

- **C-Q1. Starting the chain on today's sealed logbook.** `umwayi logbook seal --chain --by NAME`, once (proposed), or a separate `umwayi logbook chain-start --by NAME`?
- **C-Q2. Speed.** Recompute the chain on every append (proposed; simple and the file is small), or cache the newest value next to the whole-file hash and check it?
- **C-Q3. Exit code of verify.** Keep Layer 5's 0 and 1 (proposed, unchanged behaviour), or move verify to 0 and 2 like the agent commands?
- **C-Q4. The day.** Nov 15 for the chain overlaps the first day of the whole-system test and security scan (Nov 15 to 16 in the part 7c schedule). Proposed: chain on Nov 15, scan on Nov 16 only and continued in the freeze as defect finding; or move the scan to Nov 16 and the first day of the governor?

Answers (owner, Nov 9): C-Q1, C-Q2 and C-Q3 as proposed. C-Q4 changed by the owner: the whole-system test and security scan run after the budget governor is complete. The chain stays on Nov 15, the governor is built Nov 17 to Nov 22, and the scan and whole-system test run Nov 23 to Nov 26, covering the adapters, layers 10 and 11, the chain and the governor (including the telemetry receiver); README, demo and Devpost text run alongside; freeze Nov 29 to Dec 2; submit Dec 3. (Superseded Nov 9 by L-Q6: the chain is built Nov 16.)

### Crash safety (addendum, approved by the owner on Nov 9, tasks.md L5.0; build Nov 10 to Nov 11)

Requirements: Layer 5, "Logbook crash safety". Tasks L5.0 to L5.5. Code that changes: `umwayi/logbook.py`, `umwayi/fsutil.py` for a folder fsync, and `umwayi/cli.py` for `umwayi logbook recover --torn-tail` (L-Q3). Tests that plant a lock file change (they must hold a real lock).

#### The defect (found Nov 9, PR 25)

`umwayi agent run` stops the agent's process group with SIGTERM, then SIGKILL after 10 s. The hook's `umwayi check` runs in that group and writes the logbook. Killed between the append and the record in `_write_and_record`, it leaves LOGBOOK.md one entry ahead of `.umwayi/logbook.sha256` and leaves `.umwayi/logbook.lock` behind. Every later write, every agent start, and the run's own stop entry are then refused until the owner deletes the lock and seals. Reproduced with a 0.15 s pause planted between the two steps: it failed 3 of 3 runs. The same window is reached by a hook timeout that kills `umwayi check`, by Ctrl-C on any umwayi command in a terminal, and by a power cut.

#### The owner's proposal: what holds and where it is weak

Kept: an intent written before the append; recovery only for two exact states and only when no writer is running; every other state a tamper refusal; one entry per recovery; signals held off around the write; the chain inside the intended bytes.

Challenged, with what this design does instead:

1. **PID plus start time (b) is weaker than a kernel lock.** `/proc/PID/stat` exists only on Linux, not on macOS. The start time counts clock ticks since boot, so after a reboot it also needs the boot id. A killed writer that its parent has not reaped yet is a zombie with the same PID and start time, and must count as dead. Two umwayi processes in different PID namespaces (a container and the host working on one folder) cannot see each other's PIDs and would take over a live lock. Today the lock file is created empty and the PID written after it, so a writer killed in between leaves a lock with no PID. Two processes that find the same dead lock at once need a second lock to decide who takes it over. `fcntl.flock` avoids all of this: the kernel releases it when the process ends, SIGKILL included, so there is never a stale lock to judge. `umwayi/runlock.py` already works this way. Approved: flock (L-Q1). The lock file still holds the PID and start time, only to name the writer in messages.
2. **pthread_sigmask (c) blocks a signal in one thread only.** In a process with more threads (the ACP chat has two reader threads), the kernel delivers the signal to a thread that does not block it, and Python then runs the handler in the main thread, inside the write. umwayi's own handlers (agent run: SIGTERM and SIGHUP raise `_Signalled`; SIGINT raises KeyboardInterrupt) would then abort the write half way. Proposed: block the signals in the writing thread and, for the same span, also replace their Python handlers with a recorder; afterwards put both back and deliver each recorded signal once (L-Q2). SIGQUIT (Ctrl-\) is added to the three: its default also ends the process.
3. **The intent needs more than the expected hash.** With the new hash alone, recovery cannot tell a torn tail (a power cut during the append) from a hand edit, cannot check that the record it finds belongs to this write, and has nothing to resume from when the recovery itself is killed. The intent holds the record at the start, the hash and length before and after, the entry bytes, and the writer.
4. **Today the record accepts whatever the file holds after the append.** `_write_and_record` re-reads the file and records its hash, so bytes that anything else appended between the read and the record are sealed in silently. With an intent, the record is written only when the file is exactly the intended result (L-Q5).
5. **An fsync of the file is not enough for a power cut.** A rename (the record, the intent) and a removal are durable only after the folder is fsynced, and `fsutil.atomic_write` does not do that. A test can check that the calls happen in the right order; it cannot prove that the disk keeps them (KNOWN-LIMITS).
6. **The recovery entry must not open a new window.** If recovery first finished the record and then appended its entry as a second write, a kill between the two would leave a recovered logbook with no recovery entry. So the recovery and its entry are one write with its own intent, whose "before" is the recovered file.
7. **Readers race too.** `read_checked` and `verify` take no lock, so during every write they can see the same mismatch for a few milliseconds (the reader side of PR 25; the budget governor reads its ledger from the logbook on every start, B-Q1). Proposed (L-Q4): while an intent is present, a reader reads the two exact states as consistent and writes nothing.
8. **"Exit 2" is not one code for every path.** A tamper refusal keeps today's codes: 2 for agent commands and the paths of `umwayi check` (its No stays No and Yes becomes Ask me first, exit 3, as Layer 5 item 8 says), 1 for `verify` (C-Q3), 2 for the other logbook commands.

#### Files

```
.umwayi/logbook.lock      flock, kept and never deleted (before: existed only while writing)
.umwayi/logbook.pending   the intent: exists only from the start to the end of one write
```

The intent is ASCII lines, then the entry bytes:

```
umwayi logbook intent 1
kind KIND            write, recover or seal (added while building: see below)
writer PID START
record HEX           the record when the write started (64 lowercase hex, or none for a new logbook)
before HEX LENGTH    the whole file before the write
after HEX LENGTH     the whole file the write intends
entry LENGTH
<exactly LENGTH bytes: the entry as it will be appended>
```

An intent that is a link or a folder, malformed, or whose lengths do not add up (after = before + entry, and the hash of before plus the entry bytes is after) is a tamper refusal. The entry bytes hold nothing the logbook would not hold (Layer 5 never writes action JSON or prompts).

#### One write

Under the lock, signals held off from step 3 to step 6:

1. Read the file and the record. If an intent is present, recover first (below). Then today's checks: record, format, date, chain.
2. Build the entry bytes and the intended hash: `sha256(file + entry)`.
3. Write the intent: temporary file, fsync, rename, fsync `.umwayi/`.
4. Append in `ab` mode, fsync. For a new logbook, fsync the root folder too.
5. Hash the whole file. Equal to `after`: write the record (temporary file, fsync, rename, fsync `.umwayi/`). Not equal: stop with the tamper message, nothing recorded, the intent stays.
6. Remove the intent, fsync `.umwayi/`.

The write is split into named functions (`_write_intent`, `_append_bytes`, `_record_hash`, `_drop_intent`) so the tests can plant a fault between any two steps.

#### Recovery

Runs in step 1 of every write and in `check_writable` (same lock), only when an intent is present. Holding the lock means no writer is running. F is the file now, R the record now, I the intent.

| F | R | state | what happens |
| --- | --- | --- | --- |
| hash and length are I.after | I.record or I.after | completed | the format and the chain of F must pass; then one write of the recovery entry with F as its before state |
| hash and length are I.before | I.record | not written | one write of the recovery entry with F as its before state |
| the first I.before bytes hash to I.before; the rest is a strict prefix of I.entry | I.record | torn tail | refused with its own message (L-Q3) |
| anything else, or the intent itself is bad | anything | tamper | refused like a hand edit, never accepted automatically |

Added while building (PR 27), so each kind of interrupted write gets its own rule: the intent names its kind. A write intent must start from its record (I.before is the hash I.record holds, or a new logbook with no record); otherwise the intent is bad. A seal that was stopped before it appended ("seal not written") is dropped without an entry, because the logbook was never sealed and still cannot take one; the owner seals again. A recovery write that was itself stopped is resumed instead of logged again: completed, its record is finished and its intent removed; not written, its own intended bytes are appended. So a recovery leaves exactly one entry.

For an ordinary write, I.before is the hash that I.record holds. For a recovery write, I.before is the recovered file and I.record the record found at that moment, so the same table resumes a recovery that was itself killed, and the result is still one recovery entry.

The recovery write is steps 2 to 6 with `record` = R and `before` = F, so when it ends the record is the hash of F plus the recovery entry. The caller's own entry follows as a normal write. The entry:

```
- Source: umwayi logbook recover
- Added: Recovered an interrupted logbook write (writer PID 4242, started 812.33 s after boot): the entry was written in full and its hash is now recorded
- Checked: the file matched the intent the writer recorded before it wrote; the earlier hash record matched the intent; the format and the hash chain are valid; no writer held the logbook lock
- Not done: The interrupted command did not finish; what it was doing was not redone.
```

The "not written" variant says "the entry was never written and the intent was dropped". The date is today; if today is before the last entry's date, the recovery is refused like any append and `verify` says so.

#### The lock (approved, L-Q1)

- `fcntl.flock(fd, LOCK_EX | LOCK_NB)` on `.umwayi/logbook.lock`, opened with `O_NOFOLLOW | O_CLOEXEC`, polled for up to 3 s as today. Never deleted, because deleting a flock file lets two processes lock two different files with the same name (as `runlock.py` says).
- After taking it, the path and the open file are compared (device and inode). If the file was replaced, let go and try again.
- Busy after 3 s: "logbook: another umwayi command (PID N) is writing the logbook. Try again in a moment. Nothing was written." It no longer tells the owner to delete the file.
- Where `fcntl` is missing (Windows), every logbook write is refused, as the run lock is today.
- Not chosen (L-Q1), kept as the record of the alternative: the owner's (b): the lock file is made whole with `os.link` from a temporary file (never empty); it holds the PID, start time, boot id (`/proc/sys/kernel/random/boot_id`) and PID namespace (`/proc/self/ns/pid`); a holder counts as dead only when the namespace is ours and the boot id differs, or the PID is gone, is a zombie, or has another start time; a lock from another namespace is never taken over; a second lock, `.umwayi/logbook.recover`, decides which of two processes takes over a dead lock. Linux only.

#### Signals (L-Q2)

A context manager around steps 3 to 6, and around a whole recovery:

- Main thread only. In another thread the write is refused: "logbook: a logbook write must run in the main thread. Nothing was written." No such write exists today.
- `signal.pthread_sigmask(SIG_BLOCK, {SIGTERM, SIGHUP, SIGINT, SIGQUIT})`, and for the same span the Python handlers of those four are replaced with a recorder.
- On leaving: handlers back, mask back, then each recorded signal is delivered once with `signal.raise_signal`, in the order received. A process with the default action then ends; agent run's handlers then stop the agent as today.
- The span is two fsyncs, two renames and one hash of the file: milliseconds. On a stalled disk, a Ctrl-C waits for it.

#### Chain

The intent's `after` covers the whole file, so it covers the new entry's Chain line. Recovery of a completed write checks the chain of F before it records anything, and the recovery entry is chained to the entry before it. This addendum is built first (L-Q6: Nov 10 to Nov 11), so C.2 (Nov 16) adds its chain walk to step 1 and the chain cases to the recovery tests.

#### Readers and verify (L-Q4)

- `read_checked` (no lock, never writes): with an intent present, F equal to I.after or to I.before, with R equal to I.record (or to I.after), is read as consistent and returns the entries of F. Anything else is refused as today.
- `verify` with an intent present prints "info: a logbook write is in progress or was interrupted; the file matches what it intended (completed) / the state before it (not written); the next write recovers it" and exits 0 for those two states. A torn tail or any other state is a problem, exit 1.

#### Messages

- Torn tail: "logbook: LOGBOOK.md ends with part of an entry that was being written when the write stopped (a power cut or a crash). Nothing was written." It adds: "Run 'umwayi logbook recover --torn-tail --by NAME' to cut it back to the last recorded entry." That command (L-Q3) refuses unless an intent is present, the first `before` bytes hash to I.before, the record is I.record, and the rest is exactly a prefix of I.entry; it then truncates to the `before` length, fsyncs, removes the intent and writes one `umwayi logbook recover` entry by NAME ("cut back a torn tail of K bytes left by writer PID N"). It never prints the cut bytes.
- Tamper with an intent present: the existing mismatch message, plus "An interrupted write was found, but the file does not match what it intended."
- No message prints a logbook line or the intent's entry bytes.

#### Tests (L5.5)

Real child processes. `UMWAYI_FAULT=umwayi.logbook:_record_hash:hang` holds a writer between the append and the record (and likewise for the other steps).

- SIGTERM, SIGHUP, SIGINT and SIGQUIT during a held write: the write finishes, the process then ends by the signal, the logbook verifies, no intent is left, no recovery entry is written.
- SIGKILL after each step (intent written, appended, recorded, intent removed): the next write recovers with the right state, writes exactly one recovery entry, then its own entry; verify passes.
- A simulated power cut: the file truncated to before plus k bytes for k = 0, 1, a middle value and entry minus 1, with and without the record and the intent. k = 0 is "not written", the others a torn tail; nothing is accepted automatically.
- Every other mismatch still refuses: a hand edit in an old entry, in the newest entry or in the tail while an intent is present; an intent whose `after` was edited; lengths that do not add up; an intent that is a link; a record that matches neither.
- A hand edit while a dead writer's intent is present: SIGKILL after the append, edit one byte, then write: refused, no recovery entry, the intent kept.
- The lock: a writer SIGKILLed while holding it does not block the next one; a live holder (a helper process holding the flock) still gives the busy message after 3 s; the tests that plant a lock file are changed to hold a real flock.
- Two writers started at once after a crash: one recovery entry.
- A recovery SIGKILLed half way: resumed, still one recovery entry.
- The defect end to end: agent run with the pause planted between append and record, then Ctrl-C, SIGHUP or SIGTERM: the stop entry is written and the logbook verifies.
- Readers: `read_checked` during a held write returns the entries; `verify` prints the information line and exits 0.
- Torn tail: `recover --torn-tail` cuts back exactly a prefix of the intended entry and logs it once; it refuses a tail that differs by one byte, a missing intent, a bad `--by`, and an intact logbook.
- Chain: added with C.2 on Nov 16, which is built after this addendum: a recovered entry keeps a valid chain and the recovery entry is chained.
- Mutation checks: recovery that accepts any mismatch; the record written without the hash comparison; the intent not fsynced, and the folder fsync dropped (an in-process test that records the order of `os.fsync`, `os.replace` and the appends; it shows the calls and their order, not that the disk keeps them); the handler swap dropped (the SIGTERM test then sees a cut write); the recovery entry not written; the intent removed before the record; the torn tail cut accepting any tail. Counts in the pull request.

#### KNOWN-LIMITS (written with L5.5)

- The intent sits next to the record. Whoever can write both can forge an "interrupted write" and have it finished. That is no new weakness beyond KNOWN-LIMITS 3; the chain and its outside anchor are the answer.
- Durability depends on the file system and the disk honouring fsync. The tests check the calls and their order, not the disk.
- A torn tail after a power cut is never repaired automatically; the owner decides (L-Q3).
- flock works on local file systems; on a network share it may not exclude. Where `fcntl` is missing, the logbook cannot be written at all. Deleting `.umwayi/logbook.lock` by hand while a write is running can let two writes overlap; no message asks for that any more.
- Signals wait for the write to finish: milliseconds, longer on a stalled disk.
- A SIGKILL between a queue or archive change and its logbook entry leaves the change without an entry. That is as today and not fixed here.
- `fsutil.atomic_write` leaves a `.umwayi-*.tmp` file when SIGKILLed. Harmless, not cleaned up.
- An older umwayi (the old lock file) and the new one running at the same time on one root do not exclude each other.

#### Open questions (crash safety, answered Nov 9)

- **L-Q1. The lock.** flock on `.umwayi/logbook.lock`, the same as the run lock (proposed: no stale lock can exist, works on Linux and macOS), or the owner's PID plus start time with the boot id, namespace, zombie and takeover rules above (Linux only)?
- **L-Q2. Signals.** Block in the writing thread and also defer the Python handlers, with writes allowed only in the main thread (proposed), or `pthread_sigmask` alone (not enough in a process with more threads)?
- **L-Q3. A torn tail.** Refuse, and add `umwayi logbook recover --torn-tail --by NAME`, which cuts the file back to the recorded length only when the extra bytes are exactly a prefix of the intent's entry, and logs it (proposed; the only place the tool would remove bytes, and only bytes no record ever covered), or refuse and leave the owner to cut the file by hand (seal refuses a file with format problems, so seal alone cannot fix it)?
- **L-Q4. Readers.** `read_checked` and `verify` read the two exact states as consistent while an intent is present (proposed), or keep refusing during a write (readers keep seeing a mismatch for milliseconds during every write)?
- **L-Q5. Bytes appended by something else during a write.** Refuse them as a hand edit (proposed), or keep today's behaviour of recording whatever the file holds after the append?
- **L-Q6. When.** About 10.5 hours. Proposed: Nov 15, before the hash chain, so the chain is built on the safe write path; the chain moves to Nov 16, which has no work today; the governor stays Nov 17 to Nov 22. Or right after approval, before 7c-2 (pushes 7c-2 and 7c-3 back by more than a day); or Nov 16, after the chain?

Answers (owner, Nov 9): L-Q1 to L-Q5 as proposed. L-Q6 changed by the owner: crash safety is built right after PR 26 merges, Nov 10 to Nov 11, before 7c-2. Then 7c-2 and 7c-3 Nov 12 to Nov 13, layer 11 Nov 14 to Nov 15, the hash chain Nov 16, the governor Nov 17 to Nov 22, the scan Nov 23 to Nov 26; README, demo and Devpost, the freeze and the submission unchanged.

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

Planned for Nov 8 to Nov 9. Part 1 (PR 11): the notes, the shared code and the Claude Code adapter. Part 2 (PR 12): the Kiro adapter, the generic stdin and stdout adapter, and the kill switch in all three adapters. The whole-system test with the adapters (9.11) was added in PR 36 and the starter rules in the repo rules.yaml (9.10) in PR 43.

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

## Layer 10: Own command line and chat (approved; all six parts built; part 7 approved, parts 7a and 7b built; part 7c approved, 7c-1 built; part 8 built to 10.50)

Approved by the owner on Nov 8 (tasks.md 10.0). Parts 1 and 2 (agents.yaml, the gate checks, the argument lists and `umwayi agent check`) are built in PR 14; part 3 (`umwayi agent run` for Claude Code) in PR 15; part 4 (`umwayi agent run` for Kiro) in PR 16; part 5 (`umwayi agent chat` with transport cli, both platforms) in PR 17; part 6 (ACP chat for Kiro, `umwayi/acp.py`) in PR 18. All six parts are built. Part 7 (Claude Code over ACP, 10.R11) was approved on Nov 8 (tasks.md 10.22); part 7a (agents.yaml, `adapters/claude_acp/`, the gate checks and `child_env()`) is built in PR 20; part 7b (the chat: the inline settings and the canary, the three `acp.py` options, the stop) in PR 21. Requirements: 10.R1 to 10.R10 in requirements.md. Doc facts with links: `adapters/NOTES-layer10.md`.

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
5. **Kiro hook file** (Kiro only). Read every `*.json` in `WORKDIR/.kiro/hooks/` and `~/.kiro/hooks/` (regular files under 256 KB; anything unreadable is skipped and named in the refusal). Accept if one has `version: "v1"` and a hook with `trigger: "PreToolUse"`, no `matcher` or `"*"`, and `action: {"type": "command", "command": C}` where C split on single spaces is exactly `[PY, HOOK, "--root", ROOT]`, PY being `python3` or an absolute path whose name starts with `python`. If none: refuse, print the exact command it looked for, and point to the snippet in `adapters/kiro/README.md`. The front door never writes these files. A hook file that is a link, a folder, larger than 256 KB or not JSON is skipped and named in the result; a good file next to it is still found. Kiro runs the command in a shell, so a hook path or root with a space is refused.

`umwayi agent check NAME` runs steps 1, 2 and 5 of a start (reading agents.yaml, the kill switch, the gate checks), without the rules check and the run lock, starts no agent, and prints one line per check.

As built in part 2:

- Each check prints `ok`, `no` or `not run` (after the first `no`, the rest are not run).
- When every check passes it also prints the `run` and `chat` argument lists it would use, as JSON, with the word `PROMPT` where a Claude Code prompt goes (a Kiro prompt goes on stdin).
- It writes nothing: no logbook entry, no queue item, no file (a test checks the files under the root, the workdir and HOME before and after; a code guard checks `agents.py` has no file write call).
- The kill switch state is printed, but it does not change the exit code: `check` answers "can this agent be gated", and a start would stop on the kill switch anyway (exit 3).
- The version command runs in `workdir`; the self-test runs in the root.
- `--root` must be an existing folder (else 64), and is resolved to its real path, which is the path put into the hook command.
- `trust_tools` is accepted for any Kiro agent and only used by `run` (interactive V3 ignores `--trust-tools`, and V3 rejects it on `acp`). An empty list means no `--trust-tools` flag, so a headless run may use no tool without approval.
- Validation messages name the key and the rule, never the value, so a secret typed into agents.yaml is not printed (a test plants one in every field).
- `agents.py` starts programs in exactly one place, `_run_child` (`subprocess.run`, argument list, `shell=False`, `input` and `timeout` always given). A code guard test checks that, and that only `report.py` and `agents.py` import `subprocess` at all.

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
- A watcher checks `kill.state(root)` every second. On `on` or `unknown`: SIGTERM to the child (group), SIGKILL after 10 seconds. Claude Code `-p` is documented to stop cleanly on SIGTERM (exit 143); Kiro is not documented.
- If umwayi gets SIGTERM, it stops the child the same way before it exits.
- The run lock is held from step 4 to the end.

As built in part 3 (`umwayi agent run`, Claude Code):

- **The watcher is a loop in the main thread**, not a separate thread: `proc.wait(timeout=1)`, then the kill switch, then the logbook, then the timeout. Signal handlers run in the main thread, so one place stops the agent whatever happens.
- **The logbook is checked every second too** (owner request for part 3): `logbook.check_writable` runs the checks an append makes (hash record, format, date order) under the logbook lock, so a hook's write in progress is never mistaken for an edit. If it fails, the agent is stopped and the run exits 2: from then on no check can be recorded, and the hook already denies every tool call. Nothing can be logged about the stop.
- **Every entry uses the date at the moment it is written**, so a run that passes midnight does not trip the "dates never go backwards" check.
- **On every way out of `go()`** (a normal end, a refusal, the kill switch, the timeout, the logbook, SIGTERM, SIGHUP, Ctrl-C, any exception) a `finally` stops the agent before the run lock is released. Stopping means SIGTERM to the whole process group, then SIGKILL after 10 seconds. That includes anything the agent left running in its group after a normal exit, for example a server it started.
- **umwayi's own SIGTERM and SIGHUP** are caught (the handler raises once, a second signal is ignored while stopping). Ctrl-C reaches umwayi only, because the agent is in its own session. All three stop the agent, add one entry and exit 2.
- **Prompt:** exactly one of `--prompt TEXT`, `--prompt-file PATH` (a regular file) or `-` (stdin); at most 100 KB; UTF-8; no NUL; a Claude Code prompt starting with `-` is refused. All of this is step 1, before the kill switch, so a bad prompt writes nothing and runs nothing (exit 64). The prompt is the last argument; it is never logged or printed.
- **The agent's stdin is `/dev/null`** for Claude Code; its stdout and stderr are umwayi's own. umwayi prints its own lines after the agent ends.
- **The rules check must be logged**: if `check_and_log` could not write its entry, nothing starts (exit 2), whatever the answer. A start entry that cannot be written also means nothing starts (exit 2). An end entry that cannot be written makes the run exit 2. A refusal, kill switch or lock entry that cannot be written keeps its exit code and says so.
- **Refused cleanly before part 6:** a chat with a Kiro agent whose transport is `acp` was a usage error (64) until part 6. (Until part 4, `agent run` for a Kiro agent was also 64; until part 5, `agent chat` did not exist.)

As built in part 4 (`umwayi agent run`, Kiro):

- **The same `_Run` steps, watcher, stop, entries and exit codes as Claude Code.** Only the argument list and stdin differ: `kiro-cli chat --v3 --no-interactive [--agent KIRO_AGENT] [--trust-tools=ID,...]`, with the prompt on stdin. `--trust-tools` lists exactly `trust_tools` from agents.yaml in their order, and is left out when the list is empty, so a headless run can then use no tool. `--trust-all-tools` is never passed; `_assert_allowed` refuses to build a list that holds it.
- **The prompt is written to stdin by a helper thread**, which then closes stdin. A prompt larger than the pipe buffer, sent to a Kiro that does not read it, would otherwise block umwayi before the watcher starts, and the kill switch and the timeout would not be checked. A test sends 100 KB to a fake that never reads it and stops it with the kill switch.
- **Kiro's exit codes:** 0 is exit 0; 1 (failure), 3 (MCP start up), 4 (agent not found) and anything else are exit 2, with the code in the end entry.
- **A Kiro agent with `transport: acp` can be used with `agent run`.** The transport only matters for `agent chat`; `run` is always the headless command line, never ACP.
- **The hook file is checked again just before every start** (gate check 5, exact match as in part 2). A file removed or changed between two runs refuses the second with exit 2. It is not watched while Kiro runs (KNOWN-LIMITS 42).

As built in part 5 (`umwayi agent chat NAME`, transport cli, Claude Code and Kiro):

- **The same `_Run` class, with `mode="chat"`**; nothing is copied. Steps in the same order: agents.yaml (64; transport acp is 64 with "ACP chat is layer 10 part 6"), the kill switch (3), the rules with `{"type": "agent_run", ..., "mode": "chat", "transport": "cli"}` (No 2; Ask me first 3 and one queue item `Start agent NAME (chat)?`), the run lock (3), every gate check (2), the start entry ("Started agent NAME (PLATFORM, cli, chat): PATH"), then the queue summary, then the start.
- **Queue summary before the agent starts:** "Open in the queue: N item(s).", the first 5 open items as `ID (kind): title`, then one line that says the chat is gated by the hook and not logged. Printed and flushed to umwayi's stdout before the agent gets the terminal. A queue that cannot be read prints why and does not stop the chat.
- **Argument lists:** Claude Code `claude --permission-mode default --settings JSON` (the same inline hook settings as run; no `-p`, no prompt, no `--max-turns`). Kiro `kiro-cli chat --v3 [--agent KIRO_AGENT]`; never `--trust-tools` or `--trust-all-tools` in a chat (interactive V3 ignores `--trust-tools`; Kiro asks the owner itself for tools it does not trust).
- **The owner's terminal, unchanged:** stdin, stdout and stderr are inherited, no pipes. The agent stays in umwayi's process group (`start_new_session=False`), so when umwayi is the foreground job, so is the agent.
- **Ctrl-C:** from the start of the agent until umwayi is done, SIGINT is handled by a no-op Python handler, so Ctrl-C (sent by the terminal to the whole foreground group) reaches the agent and does not stop umwayi. Not `SIG_IGN`: an ignored signal stays ignored in the child after exec, and the agent would never see Ctrl-C (a test checks what the agent inherited). The old handler is put back in `go()`'s `finally`, on every exit path. Before the start, Ctrl-C still stops umwayi (exit 2).
- **Stopping a chat:** umwayi never signals its own process group. Once a second the watcher reads `/proc` and records every descendant of the agent (pid and start time); on a stop it sends SIGTERM to the agent's pid and to every recorded descendant that is still the same process (same start time, not a zombie, so a reused pid is never signalled), keeps recording while they stop, and sends SIGKILL after 10 seconds. That reaches children in another session, and children whose parent already exited, as long as a watcher pass saw them.
- **The terminal mode is put back** (`termios.tcgetattr` before the start, `tcsetattr` after), so an agent stopped while its screen had the terminal in raw mode does not leave it unusable.
- **Exit codes are those of run:** 0 only if the rules said Yes, the agent was gated and it exited 0; 2 for an agent that failed, the timeout, not gated, the logbook, a crash, umwayi's SIGTERM or SIGHUP; 3 for Ask me first, the kill switch, the run lock; 64 for usage.
- **Nothing of the conversation is logged**: umwayi never reads the terminal. The entries are the check, the start and the end (or the stop).

As built in part 6 (`umwayi agent chat NAME`, transport acp, Kiro only):

- **The same `_Run` steps**, with the rules action `{"type": "agent_run", ..., "mode": "chat", "transport": "acp"}`, the Kiro hook file check, the start entry "(kiro, acp, chat)" and the queue summary; then `kiro-cli acp --agent-engine=v3` (never `--agent`, `--model`, `--effort`, `--trust-all-tools` or `--trust-tools`) in its own session and process group, with stdin and stdout as the ACP pipes and stderr going to umwayi's stderr. The watcher is split in two: `_tick()` finds a reason to stop (kill switch, logbook, timeout) and `_tick_stop()` stops and logs, so the ACP loop can cancel and close the agent's stdin in between. The ACP loop calls `_tick()` at the same `WATCH_INTERVAL` as run and cli chat.
- **`umwayi/acp.py` is protocol only**: standard library (`json`, `os.read`, `queue`, `re`, `threading`, `time`, `collections`), no program started, nothing imported from umwayi. Two daemon threads read the agent's stdout and the owner's stdin with `os.read` on the raw file descriptors, because a thread blocked in a buffered `readline` holds that buffer's lock, can make Python abort at exit, and blocks a close. One main loop handles every event. Lines from the agent are at most 4 MB.
- **The protocol, in order:** `initialize` (version 1, `clientCapabilities: {}`, `clientInfo.name: "umwayi"`); an error or any other version ends the chat (exit 2). `session/new` with `cwd` and `mcpServers: []`; an error with code -32000 or "auth" in its message prints "Sign in with kiro-cli login, then try again." (exit 2). Then each owner line is one `session/prompt` with `prompt: [{"type": "text", "text": LINE}]`, one at a time; lines typed during a turn wait their turn.
- **Owner commands** start with `:`: `:queue` prints the open queue, `:quit` ends the chat; any other `:` line is not sent. An empty line is not sent.
- **Output:** `agent_message_chunk` text and `tool_call` lines (`tool: TITLE [KIND]`) through `safe_text`; the stop reason as `[stop reason: X]`; every other update type is ignored. `safe_text` shows C0 and C1 controls (but newline and tab), DEL, and bidirectional, zero-width and tag characters as `\uXXXX` (`\UXXXXXXXX` above U+FFFF).
- **Permission requests** go to `_Run._permission`: `rules.check_and_log` (one logbook entry) with `{"type": "acp_permission", "agent": NAME, "platform": "kiro", "kind": KIND, "tool": NAME}`, `kind` and `tool` only when they are short plain words, the title never. While the kill switch is on or unknown the answer is No; a check that could not be logged, an error, or an unknown answer is a reject. Then `acp.select_outcome`: Yes takes the first `allow_once`; No the first `reject_once`; Ask me first prints the request and `Allow once? [y/N]`, and only an owner line that is exactly `y` takes `allow_once`. Never an `*_always` option, never an option the agent did not offer: without the wanted kind it is `reject_once`, and without that `cancelled`.
- **Any other request** (`fs/*`, `terminal/*`, `_kiro/...`) is answered at once from the reader thread with error -32601; nothing is read, written or run.
- **Ends:** a line that is not one JSON object, a line over 4 MB, an error answer, or the agent closing the connection ends the chat (exit 2) and is logged as a fixed reason ("ACP chat with agent NAME ended: ..."), never agent text. A prompt is never sent again.
- **Ctrl-C** belongs to umwayi here (the agent has its own session): a handler sets a flag. If a permission is waiting for the owner, it is answered `cancelled` first; then `session/cancel`, every open permission request answered `cancelled`, up to 10 seconds for the prompt answer, and back to the owner. A late answer to an abandoned turn is ignored. Ctrl-C with no turn running prints a hint. umwayi is never stopped by Ctrl-C during the chat.
- **The kill switch, the logbook and the timeout:** the loop cancels the turn, answers open permissions `cancelled`, closes the agent's stdin, then `_tick_stop()` stops the agent's process group (SIGTERM, SIGKILL after 10 s): exit 3, 2, 2.
- **The end:** after `:quit` or the end of the owner's input, umwayi closes the agent's stdin and waits up to 10 seconds. An agent that exits 0 gives exit 0 and the usual end entry; one that does not exit is stopped (exit 2).
- **Two places start a program** in `agents.py`: `_run_child` (`subprocess.run`, for the version and the self-test) and `_Run._start` (`subprocess.Popen`, `start_new_session=True`, for the agent). A code guard test checks both have `shell=False`, that the agent's list comes only from `build_argv`, and that `agents.py` opens files only to read them.

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
| end | "Agent NAME exited with code CODE after SECONDS s" (or "by signal N") |
| kill switch before the start | "Agent NAME did not start: SHORT" (only this entry: no rule is asked) |
| run lock busy | "Agent NAME did not start: another umwayi run holds the run lock" |
| kill switch | "The kill switch stopped agent NAME" |
| timeout | "Agent NAME stopped after its timeout of MINUTES min" |
| umwayi stopped by a signal or Ctrl-C | "Agent NAME was stopped: umwayi got SIGTERM" (or SIGHUP, or Ctrl-C) |
| an unexpected error in umwayi | "Agent NAME stopped: umwayi hit an unexpected error (TYPE)" |
| Ask me first | the check entry, then the queue add entry for `Start agent NAME (run)?` (once while it is open) |

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

### Open questions for the owner (answered Nov 8)

The owner approved the spec on Nov 8 with every answer as proposed (recorded in tasks.md 10.0): 1 the run lock is taken; 2 Ask me first on a start adds a queue item; 3 Kiro headless runs use `trust_tools` only; 4 a managed Claude Code policy that blocks our hook is a known limit (KNOWN-LIMITS 30), no canary; 5 `workdir` is outside the root; 6 ACP chat asks on the terminal; 7 no `kiro_agent` with ACP; 8 an agent's failure is exit 2; 9 Claude Code over ACP is decided later; 10 spend limits are left to the budget governor.

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

### Part 7: Claude Code over ACP (approved Nov 8; part 7a built in PR 20, part 7b in PR 21; the chat end to end and the planted faults in PR 29; the owner's first real run not done)

Requirement 10.R11. Facts with links, and what is not documented: `adapters/NOTES-layer10.md`, section "Claude Code over ACP" (the adapter `@agentclientprotocol/claude-agent-acp` 0.101.0, read from its README, `package.json`, the npm registry and its source at tag v0.101.0). Nothing of part 7 is built before the owner approves it.

#### The idea

The adapter is an ACP agent that drives the bundled Claude Code CLI through the Claude Agent SDK. umwayi talks to it with the same `acp.py` client and the same `_Run` steps as a Kiro ACP chat. The difference is the first gate: there is no hook file for umwayi to find, so umwayi hands the adapter the same inline settings that `agent run` gives `claude --settings` (the SDK's flag-settings layer), and adds a `SessionStart` canary hook in the same settings. The chat is used only after the canary has run in this very session, which shows that command hooks from that layer run there; otherwise it is refused.

#### Files

```
adapters/claude_acp/
  package.json        {"private": true, "dependencies": {"@agentclientprotocol/claude-agent-acp": "0.101.0"}}, exact version
  package-lock.json   generated once in the build pull request, with integrity hashes; reviewed there
  README.md           what it is, the pin, the one install command, what it installs (Node 22, about 8 platform packages of the SDK of which npm installs one), how to update the pin
  canary.py           standard library: writes one empty file named by its --token into its --dir (O_EXCL, no other output)
  .gitignore          node_modules/
umwayi/agents.py      platform table, validation, the ACP program, gate checks, env allow list, inline settings, stop
umwayi/acp.py         three small options on Chat (below)
tests/agents/fake_node.py, tests/agents/test_agents_claude_acp.py
```

The core never imports `adapters`; it knows two paths in it (the adapter's `dist/index.js` inside `node_modules`, and `canary.py`), as it knows the layer 9 hooks. Nothing in `.claude` or `.kiro/hooks` is created or changed.

#### agents.yaml and the platform table

- `claude-code` gets `transports: ("cli", "acp")`. `command` stays `claude` (for `agent run` and cli chat); an ACP chat uses the fixed program `node`, found on PATH, and the fixed adapter path. `kiro_agent` and `trust_tools` stay Kiro only.
- New constants in `agents.py`: `CLAUDE_ACP_PACKAGE = "@agentclientprotocol/claude-agent-acp"`, `CLAUDE_ACP_VERSION = "0.101.0"`, `NODE_MIN = (22, 0, 0)`, the adapter path `adapters/claude_acp/node_modules/@agentclientprotocol/claude-agent-acp/dist/index.js`, the canary path.
- `permission_action` takes the platform (it is `kiro` today) so the action says `"platform": "claude-code"`.

#### The argument list and the environment

| program | argument list |
| --- | --- |
| node version | `[NODE, "--version"]` |
| adapter version | `[NODE, ADAPTER, "--version"]` |
| Claude Code version | `[NODE, ADAPTER, "--cli", "--version"]` |
| sign-in | `[NODE, ADAPTER, "--cli", "auth", "status"]` (exit code only) |
| the chat | `[NODE, ADAPTER]` in `workdir`, own session and process group, stdin and stdout as the ACP pipes, stderr to umwayi's stderr |

All of them get the allow-listed environment of 10.R11.9 (a function `child_env(os.environ)` that copies only listed names that are set, then sets `CLAUDE_AGENT_ACP_PROTOCOL=v1`). No `ANTHROPIC_*` key, no `CLAUDE_CODE_EXECUTABLE` (so the bundled, pinned Claude CLI is used, not one from PATH), no `NODE_OPTIONS`. The argument-list test of 10.R5.7 is extended to these lists.

#### The gate checks for a Claude Code ACP chat

In this order, the first failure ends it (exit 2, one entry "Refused agent NAME: not gated (REASON)"); `umwayi agent check NAME` prints them all:

1. `node` on PATH, absolute.
2. `node --version`: the first `N.N.N` (after a `v`) at least 22.0.0.
3. The adapter file: a regular file at the fixed path (not a link).
4. Its `package.json` (read as JSON, at most 64 KB): `name` and `version` exactly the pinned ones.
5. `NODE ADAPTER --version`: stdout exactly the pinned version.
6. `NODE ADAPTER --cli --version`: a Claude Code version of at least 2.1.295 (for `onFailure: "block"`).
7. Sign-in: `NODE ADAPTER --cli auth status` exits 0 within 15 s; output discarded. Else "Sign in to Claude Code first (claude, then /login), then try again."
8. The layer 9 Claude Code hook: present, and its self-test (exit 2 for a non PreToolUse event), as for `agent run`.

Then, inside the session, the gate is confirmed by the canary (below) before any prompt.

#### session/new, the inline settings and the canary

Before the start umwayi makes a private folder (`tempfile.mkdtemp`, mode 0700, outside the root and the workdir) and a token (`secrets.token_hex(16)`, not a secret: it only proves which session ran the hook). `session/new` is:

```json
{"cwd": "WORKDIR", "mcpServers": [],
 "_meta": {"claudeCode": {"options": {
   "allowDangerouslySkipPermissions": false,
   "settings": {"disableAllHooks": false, "hooks": {
     "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "PYTHON",
        "args": ["ABS/adapters/claude_code/hook.py", "--root", "ROOT"], "timeout": 30, "onFailure": "block"}]}],
     "SessionStart": [{"hooks": [{"type": "command", "command": "PYTHON",
        "args": ["ABS/adapters/claude_acp/canary.py", "--dir", "TMPDIR", "--token", "TOKEN"], "timeout": 10}]}]}}}}}}
```

- The `PreToolUse` entry is exactly the one `claude_settings()` builds for `agent run` (same function).
- umwayi then waits up to 30 s for `TMPDIR/TOKEN` to exist (checked with `os.path.exists`, the watcher still running). Seen: the gate is confirmed; umwayi sends `session/set_mode` `{"sessionId", "modeId": "default"}` and only then reads the owner's first line. Not seen: the chat ends with exit 2 before any prompt. The folder is removed on every way out.
- `settingSources` is left as the adapter sets it (user, project, local), so the owner's own deny rules and hooks still apply; hooks merge and the strictest answer wins.

#### acp.py: three small options, nothing else

`Chat(..., session_meta=None, gate_ready=None, set_mode=None)`:

- `session_meta`: a dict sent as `_meta` of `session/new` (Kiro: `None`, unchanged).
- `gate_ready`: a callback polled in the loop after `session/new` until it returns True or 30 s pass; then `_Failed("the first gate could not be confirmed in the ACP session")` (exit 2) before any owner line is sent.
- `set_mode`: a mode id sent with `session/set_mode` after the gate is confirmed; an error answer is `_Failed` (exit 2).

About 30 lines in `acp.py`; the permission, output, Ctrl-C, kill switch and end code is unchanged. `_auth/status_update` and other unknown notifications are already ignored.

#### Stop

The adapter is started in its own session (as for Kiro ACP). Every stop closes its stdin, then signals its process group and every descendant seen in `/proc` (the part 5 tracking, now also on for ACP), SIGTERM then SIGKILL after 10 s. That covers background commands, which outlive `session/cancel` and whose process group is not documented.

#### Failure table

| failure | what the owner sees | exit |
| --- | --- | --- |
| agents.yaml: `transport: acp` with `kiro_agent` or `trust_tools` for claude-code | the problem with its line | 64 |
| kill switch on or unknown; Ask me first; run lock held | as for every start | 3 |
| rules No | as for every start | 2 |
| no `node`, or older than 22 | "not gated: node ..." | 2 |
| adapter not installed, a link, wrong name or version, `--version` differs | "not gated: the claude-agent-acp adapter ... run the install command in adapters/claude_acp/README.md" | 2 |
| bundled Claude Code older than 2.1.295, or no version | "not gated: Claude Code version ..." | 2 |
| not signed in, or `auth status` hangs | "Sign in to Claude Code first (claude, then /login), then try again." | 2 |
| the layer 9 hook missing or its self-test fails | as for `agent run` | 2 |
| `initialize` error or not version 1 | as for Kiro ACP | 2 |
| `session/new` error (sign-in expired) | "Sign in with ..." or the error line | 2 |
| canary not seen within 30 s | "The first gate could not be confirmed in the ACP session. Nothing was sent." | 2 |
| `session/set_mode` error | "The agent did not accept the default permission mode." | 2 |
| any later ACP error, bad line, dropped connection | as for Kiro ACP | 2 |
| kill switch, logbook, timeout during the chat | as for Kiro ACP | 3, 2, 2 |
| the adapter does not exit within 10 s after `:quit` | stopped | 2 |

#### Tests

A fake `node` (a Python script put first on PATH) answers `--version` with `v22.x`, `ADAPTER --version` with the pin, `--cli --version` and `--cli auth status` from variables, and with `[ADAPTER]` alone acts as the adapter: the scripted ACP agent of `fake_agent.py` in a Claude flavour that reads `_meta.claudeCode.options.settings`, runs its `SessionStart` hooks (exec form) at `session/new`, and runs its `PreToolUse` hooks for scripted tool calls before it sends a permission request, as the SDK docs order them. A fake installed package (`package.json` and an empty `dist/index.js`) is written into a copy of the source tree in each test.

#### Schedule effect

Effort, if approved: about 20 hours (tasks.md 10.23 to 10.31, of which 1.5 are the owner's first real run), that is about 2.5 working days, planned as 3. Layer 11 and part 7 cannot both fit Nov 9 to Nov 10. Two choices:

- **A (proposed):** part 7 on Nov 9 to Nov 11; layer 11 spec and build Nov 12 to Nov 13; the whole-system test and security scan Nov 14 to Nov 16 (3 days instead of 4, and the scan must cover the npm dependencies); the budget governor Nov 17 to Nov 22 (6 days instead of 7); README, demo and Devpost Nov 23 to Nov 28; freeze and submit unchanged. (Superseded Nov 9 by the addendum: see tasks.md "Schedule to Dec 3".)
- **B:** part 7 after Dec 3; the schedule stays as it is, and Claude Code chat stays on the terminal (part 5) for the submission.

#### Open questions for the owner (part 7)

1. **The canary is not seen.** Refuse the chat (proposed), or allow it with an explicit `acp_gate: permission_only` in agents.yaml, which says that the permission answer is the only gate? Proposed: refuse, no such setting in part 7.
2. **The starting permission mode.** Send `session/set_mode` `default` after the canary (proposed), so `acceptEdits`, `auto` or `bypassPermissions` from the owner's settings cannot start the session approving calls without asking; an error ends the chat with 2. Or leave the owner's mode?
3. **API keys.** Support only the Claude Code login the owner already has (claude.ai or Console, read by Claude Code itself), and never pass `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` (proposed)? Or allow an agents.yaml list of environment variable names to pass (names only, never values)?
4. **The install command.** `npm ci --ignore-scripts` in `adapters/claude_acp/`, run by the owner (proposed); the lockfile made once in the build pull request with network access and reviewed there; umwayi never runs npm.
5. **The pin and its updates.** Pin `0.101.0` (proposed); change it only in a pull request that updates NOTES-layer10.md, `package.json`, the lockfile and the constant together, after reading the changelog. The adapter publishes several preview builds a day.
6. **Which Claude Code.** The CLI bundled with the pinned SDK (proposed, pinned by the lockfile, Claude Code 2.1.318 for SDK 0.3.318), not the owner's `claude` on PATH through `CLAUDE_CODE_EXECUTABLE` (not pinned).
7. **Settings sources.** Keep user, project and local (proposed, so the owner's own deny rules apply), or `settingSources: []` so only our inline settings and managed policy apply?
8. **The command field.** Keep `command: claude` and use a fixed `node` for ACP chat (proposed), or add a field?
9. **The canary wait.** 30 seconds after `session/new` (proposed). Not documented: whether `SessionStart` runs at `session/new` or only with the first prompt. If only with the first prompt, every chat is refused under answer 1, and part 7 needs another way to confirm the gate (for example sending a first prompt that the owner wrote and refusing the chat if the canary did not run before any tool call); that would be decided after the first real run.
10. **When to build.** Schedule A (proposed) or B above.

#### Risks (part 7)

| risk | what happens | what we do |
| --- | --- | --- |
| `SessionStart` does not run before the first prompt in an SDK session | every Claude Code ACP chat is refused | fail closed; open question 9; the first real run decides |
| a managed Claude Code policy blocks non-managed hooks | the canary does not run, so the chat is refused (this check now sees what KNOWN-LIMITS 30 could not) | fail closed |
| a new adapter release changes the session options or the permission shape | the pinned version keeps working; an update can break the gate | pin, update only with a NOTES review |
| supply chain: the adapter, its four pinned dependencies and their own dependencies (not counted here; the lockfile will list them), and one native Claude CLI binary | code umwayi did not write runs with the owner's rights | exact pin, lockfile integrity, `--ignore-scripts`, the security scan (S.2) covers `adapters/claude_acp/` |
| the rules see the kind and the tool name, not the command | permission answers cannot tell `ls` from `rm` | the hook (first gate) sees the command; KNOWN-LIMITS will say so |
| sign-in expires during a chat | the adapter answers with an error | the chat ends with exit 2; sign in again |
| background commands | they outlive a cancel | stop by process group and seen descendants |

### Part 7c: subscription first, login and billing check (approved Nov 9; part 7c-1 built in PR 23: the login check, claude_env, forceLoginMethod; part 7c-2 in PR 28: agent login and Kiro; part 7c-3 in PR 29: the ACP watch)

Requirement 10.R12. Facts with links, and what is not documented: `adapters/NOTES-layer10.md`, section "Login and billing for Claude Code". Nothing of part 7c is built before the owner approves it.

#### The idea

Claude Code decides who pays from a fixed precedence, and the subscription login comes last. So "subscription first" cannot be a setting umwayi passes; it has to be a check umwayi makes:

- **Before every Claude Code start**, umwayi asks the same Claude Code that will run (`claude`, or the adapter's bundled CLI) `auth status --json`, in the same folder and with the same environment as the agent. It starts the agent only when the answer proves a claude.ai subscription login is the credential in use, and that no key, token, helper or other provider outranks it.
- **It takes the credentials it can see out of the way:** the variables are removed from the environment of `agent run` and the cli chat, as the ACP allow list already does.
- **It adds `forceLoginMethod: "claudeai"`** to the one settings template, as a second line.
- **During an ACP chat** it watches the adapter's own `_auth/status_update` and stops the chat if the payer changes.

The check reads six fields and nothing else; the email and organization in the same output are never read into anything.

#### What changes, file by file

```
umwayi/agents.py   CLAUDE_CREDENTIAL_ENV, claude_env(), login_check(), the "login" gate check for every
                   Claude Code start (replacing the 7a "sign-in" check), forceLoginMethod in claude_settings(),
                   the auth watch callback for the ACP chat, env= on the agent run and cli chat start,
                   mode LOGIN (`umwayi agent login NAME`), LOGIN_ENV_NAMES, KIRO_CREDENTIAL_ENV, the Kiro
                   whoami check
umwayi/cli.py      the `agent login NAME [--agents PATH]` subcommand
umwayi/acp.py      one option on Chat: on_auth (a callback given the kind of each _auth/status_update), about 10 lines
tests/agents/      fake_agent.py and fake_node.py answer `auth status --json` from a script, fake_node.py acts as
                   `--cli auth login --claudeai`, the fake kiro-cli answers `whoami` and `login`, and the Claude ACP
                   fake can push _auth/status_update; new test_agents_claude_login.py and test_agents_login.py
```

The core stays standard library only and never imports `adapters`. Nothing in `.claude` or `.kiro/hooks` is created or changed.

#### The login check

| start | argument list | cwd | environment |
| --- | --- | --- | --- |
| `agent run`, cli chat | `[CLAUDE, "auth", "status", "--json"]` | `workdir` | `claude_env(os.environ)` |
| ACP chat | `[NODE, ADAPTER, "--cli", "auth", "status", "--json"]` | `workdir` | `child_env(os.environ)` |

- It goes through `_run_child` with `keep_output=True`, stderr to `/dev/null`, stdin `b""`, `SIGNIN_TIMEOUT` (15 s), and only the first 64 KB of stdout are looked at.
- `login_check(code, out) -> (ok, detail)` is pure and has its own unit tests. It decodes UTF-8, needs one JSON object, and takes these six keys:

| field | must be | if not, the detail says |
| --- | --- | --- |
| exit code | 0 | exit 1 with `loggedIn` false or `authMethod` `none`: "not signed in"; otherwise "could not be confirmed" |
| `loggedIn` | `true` | "not signed in" |
| `authMethod` | `"claude.ai"` | `api_key`: "an API key pays"; `api_key_helper`: "an apiKeyHelper in a settings file pays"; `oauth_token`: "CLAUDE_CODE_OAUTH_TOKEN pays"; `third_party`: "a cloud provider or gateway pays"; anything else: "could not be confirmed" |
| `apiKeySource` | absent | "an API key from SOURCE pays", where SOURCE is shown only when it is one of `ANTHROPIC_API_KEY`, `apiKeyHelper`, `/login managed key` (Console), `env`; else "an API key pays" |
| `apiProvider` | absent or `"firstParty"` | "a cloud provider or gateway pays" |
| `subscriptionType` | 1 to 40 of `[a-z0-9 _-]` | "no Claude subscription was reported" |

- Every detail ends with its fix: sign in with the Claude account; unset the variable; remove `apiKeyHelper` from the settings file; Console is API billing.
- The dict is dropped when the function returns. No field other than the six is read, and `email`, `orgId`, `orgName` and the raw text are never put in a string.
- A code guard test checks that `login_check` reads the JSON only by those six key names.
- Order in the Claude Code ACP checks (10.R11.6): step 7 "sign-in" becomes "login", with the same place, timeout and environment. In the cli checks: command, version, **login**, hook script, hook self-test.
- `agent check` prints `ok: login: Claude subscription (plan: WORD)`, and the start entry gets "plan: WORD" (open question 5). The plan word is the only value from the output that is ever shown.

#### Credential variables (agent run and the cli chat)

```python
CLAUDE_CREDENTIAL_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                         "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_OAUTH_REFRESH_TOKEN", "CLAUDE_CODE_OAUTH_SCOPES",
                         "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
                         "CLAUDE_CODE_USE_FOUNDRY", "ANTHROPIC_PROFILE", "ANTHROPIC_FEDERATION_RULE_ID",
                         "ANTHROPIC_ORGANIZATION_ID", "ANTHROPIC_IDENTITY_TOKEN_FILE")

def claude_env(environ) -> dict:      # umwayi's environment minus those names; values never read
```

- `_start` passes `env=claude_env(os.environ)` for a Claude Code run or cli chat, and `env=child_env(os.environ)` for an ACP chat, as today. A Kiro start gets `env=kiro_env(os.environ)`, umwayi's environment minus `KIRO_API_KEY` (see "Kiro" below).
- The deny list (not the ACP allow list) is proposed for the terminal chat, because an interactive `claude` needs the owner's terminal environment (`TERM`, `COLORTERM`, editor variables) that the allow list leaves out (open question 3).
- A credential set in a **settings file** (`apiKeyHelper`, or `env` in settings) is not removed: umwayi does not edit settings. The login check sees it and refuses.

#### The settings template

`claude_settings()` gets `"forceLoginMethod": "claudeai"` next to `disableAllHooks`. It is the one template, so `agent run` (`--settings`), the cli chat and the ACP inline settings all get it. The tests that pin the template are updated. It is a second line only: whether it blocks an environment or helper credential from the flag layer is not documented (NOTES, "Restricting the login method").

#### acp.py: one more option

`Chat(..., on_auth=None)`:

- When a notification `_auth/status_update` arrives and `on_auth` is set, `_update` calls `on_auth(kind)` with `params.authStatus.kind` if it is a short plain word, and ignores it otherwise.
- `on_auth` returns None to go on, or a token; with a token the chat ends as a watcher stop (`_Stop`).
- In agents.py the callback returns `("billing", kind)` for any kind other than `"account"`. `_tick_stop` then stops the adapter (10.R11.11), logs "Agent NAME was stopped: the Claude Code login changed and a subscription no longer pays" and exits 2.
- Kiro passes None, unchanged. About 10 lines; nothing else in acp.py changes.
- The push can come in the middle of a turn that the new credential already pays for, so this limits the damage, it does not prevent it (KNOWN-LIMITS).

#### `umwayi agent login NAME` (owner decision Nov 9, option B)

```
umwayi agent login NAME [--agents PATH]   the claude.ai sign-in for a Claude Code ACP agent (or kiro-cli login
                                          for a Kiro agent) on your terminal, then the login check: 0, 2, 3 or 64
```

A third mode next to RUN and CHAT, `LOGIN`, in the same `_Run`, so every start step, the stop and the logbook code are reused, not copied:

1. **agents.yaml:** the agent must be `platform: claude-code` with `transport: acp`, or any Kiro agent; anything else is a usage error (64).
2. **The kill switch** (3).
3. **The rules:** action `{"type": "agent_login", "agent": NAME, "platform": P, "transport": T}`. No gives 2. Ask me first gives 3 and one queue item `Log in agent NAME?`, added once (`taskqueue.add_once`, as for starts).
4. **The run lock** (3).
5. **The gate checks up to the login check:** for Claude Code ACP, node, node version, adapter file, adapter package, adapter version and Claude Code version; for Kiro, command and version. The hook checks are not run: the login runs no agent and no tool.
6. **The login check first:** if it already passes, nothing is started, and umwayi prints `Claude subscription OK (plan: WORD)` (Kiro: `Kiro login OK`) and exits 0 (open question 11).
7. **One start entry, then the login:**
   - Claude Code: `build_argv(agent, LOGIN, node, ...)` returns exactly `[NODE, ADAPTER, "--cli", "auth", "login", "--claudeai"]`.
   - Kiro: `build_argv` returns `[KIRO, "login"]`.
   - `_assert_allowed` gains the forbidden words `--console`, `--email`, `--sso`, `setup-token`, `logout`, `--license`, `--identity-provider`, `--social` and `--auth-method`, checked on every list.
8. **The terminal:** `_start` treats LOGIN like a cli chat: the owner's terminal unchanged (stdin, stdout and stderr inherited), umwayi's process group, Ctrl-C to the login only (the part 5 no-op handler), the terminal mode put back. umwayi never has a pipe to it, so it cannot read its output, a URL, a code or a token.
9. **The environment:**
   - Claude Code: `login_env(os.environ)` = `child_env(os.environ)` plus `LOGIN_ENV_NAMES`, each only if set:
     ```python
     LOGIN_ENV_NAMES = ("TERM", "COLORTERM", "BROWSER", "DISPLAY", "WAYLAND_DISPLAY", "XDG_CURRENT_DESKTOP",
                        "XDG_DATA_DIRS", "DESKTOP_SESSION", "DBUS_SESSION_BUS_ADDRESS",
                        "SSH_TTY", "SSH_CONNECTION", "SSH_CLIENT", "NO_BROWSER")
     ```
   - Why each name, briefly (sources in NOTES, "Signing in from umwayi"):
     - `TERM` and `COLORTERM`: the login prints a URL and reads a code on the terminal.
     - `BROWSER`: documented by Claude Code for WSL2.
     - `DISPLAY`, `WAYLAND_DISPLAY`, `XDG_CURRENT_DESKTOP`, `XDG_DATA_DIRS` and `DESKTOP_SESSION`: what `xdg-open` reads to find the desktop and the browser.
     - `DBUS_SESSION_BUS_ADDRESS`: for the desktop opener it hands over to.
     - `SSH_TTY`, `SSH_CONNECTION`, `SSH_CLIENT` and `NO_BROWSER`: the remote markers that switch the login to the manual URL and code flow.
     - `HOME`, `PATH` and the XDG folders are already in `child_env()`.
     - The legacy `KDE_FULL_SESSION`, `KDE_SESSION_VERSION`, `GNOME_DESKTOP_SESSION_ID` and `MATE_DESKTOP_SESSION_ID` are left out: `xdg-open` reads `XDG_CURRENT_DESKTOP` first (open question 12).
   - Never passed: `CLAUDE_CODE_OAUTH_REFRESH_TOKEN`, `CLAUDE_CODE_OAUTH_SCOPES`, `CLAUDE_CODE_REMOTE`, and everything 10.R11.9 leaves out.
   - Kiro: `kiro_env(os.environ)`, the same environment as a Kiro start.
10. **While it runs:** the watcher (`_tick`) checks the kill switch, the logbook and `LOGIN_TIMEOUT` (10 minutes, a constant; `timeout_minutes` from agents.yaml is for agents) every second, and tracks descendants in `/proc`. A stop is the part 5 cli chat stop: SIGTERM to the login and every seen descendant, SIGKILL after 10 s, the terminal mode put back. Kill switch: exit 3; logbook or the limit: exit 2.
11. **Afterwards** (the login exited, whatever its code): the login check runs again with the agent's start environment (`child_env`, or `kiro_env` for Kiro). umwayi prints one line: `Claude subscription OK (plan: WORD)` (Kiro: `Kiro login OK`) with exit 0, or the refusal line of the login check (10.R12.5) with exit 2. A non-zero exit from the login itself is only named in the logbook ("the login exited with code N"); the check decides.
12. **Logbook:** "Started login for agent NAME (claude.ai)" and "Login for agent NAME ended: subscription OK (plan: WORD)" or "...: not gated (login: REASON)". Never the output.

`agent run` and `agent chat` never enter LOGIN. When their login check fails, the refusal line adds "Run umwayi agent login NAME to sign in." for a Claude Code ACP agent or a Kiro agent.

#### Kiro: subscription first as far as Kiro can be checked

Facts: NOTES-layer10.md, "Kiro: login and billing".

- **Who pays:** by the Kiro docs, a Kiro login, an API key included, is always paid from the subscription's credits. Beyond them there are only add-on credits the owner buys by hand; usage pauses when credits run out. So "subscription first" for Kiro means: use the owner's own browser login, never a key from the environment.
- **`kiro_env(os.environ)`:** umwayi's environment minus `KIRO_CREDENTIAL_ENV = ("KIRO_API_KEY",)`, for every Kiro start (run, cli chat, ACP) and for `whoami` and `login`. `KIRO_HOME` stays: it is the owner's choice of Kiro folder, not a credential.
- **The Kiro login check:** `[KIRO, "whoami"]` through `_run_child`, in the workdir, `kiro_env`, stdin `b""`, 15 s, `keep_output=False` (stdout and stderr to `/dev/null`, never parsed: the JSON field names are not documented and the output holds the email). It must exit 0, or "not gated (login: Kiro is not signed in). Sign in to Kiro first (kiro-cli login), then try again." Order in the Kiro checks: command, version, **login**, hook script, hook self-test, kiro hook file.
- **No Kiro billing check:** nothing to decide about who pays, and no documented way to read the plan or the credits outside a session. `/usage` and `_kiro/account/getUsage` run inside a Kiro session and are not used.
- **Never:** `kiro-cli acp --auth-method client` (umwayi would have to answer token requests), `kiro-cli logout`, and any login flag.
- **Not known:** whether `whoami` exits non-zero when signed out (if it exits 0, the check proves nothing and the start fails later at Kiro's own sign-in error, exit 2), and whether a headless `--no-interactive` run works without `KIRO_API_KEY` (the Kiro docs conflict). Both go to KNOWN-LIMITS and the owner's real check (10.31).

#### Failure table (added rows)

| failure | what the owner sees | exit |
| --- | --- | --- |
| not signed in | "not gated (login: not signed in). Sign in to Claude Code with your Claude subscription first (claude, then /login, choose the Claude account), then try again." | 2 |
| `ANTHROPIC_API_KEY` in a settings `env`, or a key that survives (cli start) | "not gated (login: an API key from ANTHROPIC_API_KEY pays ...)" | 2 |
| `apiKeyHelper` in user or project settings | "not gated (login: an apiKeyHelper in a settings file pays; remove it from the settings file ...)" | 2 |
| Console login | "not gated (login: an API key from a Console login pays; Console is API billing ...)" | 2 |
| `CLAUDE_CODE_OAUTH_TOKEN` (through a settings `env`) | "not gated (login: CLAUDE_CODE_OAUTH_TOKEN pays ...)" | 2 |
| cloud provider or gateway | "not gated (login: a cloud provider or gateway pays ...)" | 2 |
| no subscription reported, unknown shape, not JSON, over 64 KB, no answer in 15 s | "not gated (login: could not be confirmed ...)" | 2 |
| `_auth/status_update` kind not `account` during an ACP chat | "The Claude Code login changed and a subscription no longer pays, so agent NAME was stopped (exit 2)." | 2 |
| `agent login` for an agent that is not Claude Code ACP or Kiro | "agent login is only for platform claude-code with transport acp, or platform kiro. Nothing was started." | 64 |
| `agent login`: rules No; Ask me first; run lock; kill switch | as for every start (queue item `Log in agent NAME?`) | 2, 3, 3, 3 |
| `agent login`: a gate check before the login fails | "not gated (...)", nothing started | 2 |
| `agent login`: already a subscription | "Claude subscription OK (plan: WORD). Nothing was started." | 0 |
| `agent login`: the login ends and the check passes | "Claude subscription OK (plan: WORD)." | 0 |
| `agent login`: the login ends and the check fails (no login, Console, a key in front) | the one refusal line of the login check | 2 |
| `agent login`: kill switch, logbook, 10 minute limit during the login | stopped, terminal mode put back | 3, 2, 2 |
| Kiro: `whoami` not 0, or no answer in 15 s | "not gated (login: Kiro is not signed in). Sign in to Kiro first (kiro-cli login), then try again." | 2 |

#### Tests

- **The fakes:** `fake_agent.py` (as `claude`) and `fake_node.py` (for `ADAPTER --cli auth status --json`) print a scripted JSON object and exit code. The default is `{"loggedIn": true, "authMethod": "claude.ai", "subscriptionType": "max", "email": PLANTED, "orgName": PLANTED, "orgId": PLANTED}`. The scripted Claude ACP agent can push `_auth/status_update` with a given kind mid-turn.
- **Unit tests** for `login_check` over every row of the table, plus `null` values, booleans as strings, extra fields, a JSON list, invalid UTF-8, 64 KB plus one byte, and a `subscriptionType` with control or bidirectional characters.
- **End to end**, for `agent run`, the cli chat and the ACP chat, each failing shape:
  - refused with exit 2, the agent never started, one refusal entry;
  - the planted email, organization and secret never in stdout, stderr, the logbook or the queue;
  - the fake records that the credential variables were absent, even when set, and that the login check ran in the workdir with the same environment names as the agent.
- **`forceLoginMethod`** is in every settings JSON, and the `agent run` and ACP PreToolUse entries are still equal.
- **The auth watch:** an `api_key` push mid-chat stops the ACP chat with exit 2 and nothing alive; an `account` push and a push with no kind change nothing; a Kiro ACP chat has no watch.
- **`agent login`** (a real `python -m umwayi agent login` child on a pty for the terminal cases, as the part 5 chat tests do, and on a pipe otherwise). `fake_node.py` acts as `--cli auth login --claudeai`: it prints a planted secret, a URL and a code to stdout and stderr, reads one line from stdin, then, as scripted, rewrites the scripted `auth status` answer to a subscription, to an API key in front, or not at all, and exits 0 or 1.
  - A login that flips the status prints exactly `Claude subscription OK (plan: max)` and exits 0.
  - A failed login, and one that leaves an API key in front, each give exit 2 with the refusal line.
  - Already a subscription: no login is started, exit 0.
  - The kill switch during the login gives exit 3, nothing alive, and the terminal mode put back. The logbook stop and the 10 minute limit (shortened in tests through the test-only site hook, as `UMWAYI_TEST_MINUTE`) each give exit 2.
  - The planted secret, URL and code never appear in the logbook or the queue.
  - The fake records its argv: exactly `[NODE, ADAPTER, "--cli", "auth", "login", "--claudeai"]`. A scan of every argument list in every test asserts that none has `--console`, `--email` or `--sso`.
  - The fake records its environment names: a subset of `child_env()` names plus `LOGIN_ENV_NAMES`, with `BROWSER`, `DISPLAY` and `SSH_TTY` passed when set, and never `CLAUDE_CODE_OAUTH_REFRESH_TOKEN`, `CLAUDE_CODE_OAUTH_SCOPES`, `CLAUDE_CODE_REMOTE`, `ANTHROPIC_API_KEY` or `NODE_OPTIONS`.
  - Rules No; Ask me first with one queue item, not two on a second call; the run lock held; each failing gate check: nothing started.
  - `agent run` and `agent chat` with a failing login check start no login and name `umwayi agent login NAME`.
  - A Claude Code cli agent: 64.
- **Kiro:**
  - The fake `kiro-cli` records `KIRO_API_KEY` absent (it is set in every test) for `chat --no-interactive`, `chat`, `acp`, `whoami` and `login`.
  - `whoami` exiting 1, or hanging, refuses each Kiro start with exit 2 and nothing started; its output, with a planted email, is never shown.
  - `agent login` for a Kiro agent runs exactly `[KIRO, "login"]`, then `whoami`.
  - No Kiro argument list holds `--auth-method`, `logout` or a login flag.
- **Code guards:**
  - `login_check` reads only the six key names; one `subprocess.run` site; one `Popen` site.
  - The only login argument lists are the two built by `build_argv` for LOGIN.
  - The strings `setup-token`, `logout` and `--console` appear in agents.py only in the forbidden-words tuple.
- **Mutation checks for the login command** (the counts in the pull request):
  - `--claudeai` changed to `--console`;
  - `--email` added;
  - stdout given a pipe that umwayi reads;
  - the login environment widened to `os.environ`, or a `LOGIN_ENV_NAMES` entry replaced by `CLAUDE_CODE_OAUTH_REFRESH_TOKEN`;
  - the kill switch not watched during LOGIN;
  - the check after the login skipped (the login's exit 0 trusted);
  - the "already a subscription" step starting the login anyway;
  - the rules action type left as `agent_run`;
  - `agent chat` starting a login on a failed check;
  - Kiro `KIRO_API_KEY` left in;
  - Kiro `whoami` exit code ignored.

#### Schedule effect

Effort, if approved: about 14 hours (tasks.md 10.33 to 10.39: 9 for the check, the environment rule, the template and the watch, 3.5 for `agent login`, 1.5 for Kiro; 0.5 of them the owner's check on the real machine, folded into 10.31). That is more than the part 7 days of Schedule A can hold next to 10.29 to 10.31. Proposed: 10.33 to 10.35 and 10.38 on Nov 10 to Nov 11 with 10.29 to 10.31; 10.39 (Kiro) and 10.36 (the in-chat watch) on Nov 12; layer 11 moves to Nov 13 to Nov 14 and the whole-system test and security scan to Nov 15 to Nov 16 (two days instead of three). If time runs short, 10.36 is the one to cut (open question 9). (Superseded Nov 9 by the addendum: see tasks.md "Schedule to Dec 3".)

#### Open questions for the owner (part 7c)

1. **Parse `auth status`.** 10.R11.8 says its output is "discarded, never parsed". Read the six named fields of the JSON (proposed), or keep the exit code only and refuse nothing on billing? Proposed: read the six fields; the email, organization and raw text are never read into anything.
2. **`oauth_token`.** A `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token` is billed to the subscription too. Refuse it (proposed: a long-lived token in the environment is a secret umwayi would hand on, and the ACP allow list does not pass it anyway), or accept it as the subscription?
3. **Credential variables for `agent run` and the cli chat.** Remove the listed names and pass the rest (proposed), or use the ACP allow list of 10.R11.9 for every Claude Code start (stricter, but the terminal chat may then lose `TERM` and editor settings)?
4. **`forceLoginMethod: "claudeai"` in the template.** Add it (proposed, a second line, not confirmed to block environment credentials), or leave the template unchanged?
5. **Show the plan.** Print "plan: WORD" (for example `max`) in `agent check` and the start entry (proposed), or nothing at all from the output?
6. **The watch during an ACP chat.** Stop the chat when `_auth/status_update` says a kind other than `account` (proposed), or check only before the start?
7. **API billing on purpose.** No way to allow it in part 7c (proposed). Later, an explicit agents.yaml key (for example `billing: api`) could come with the budget governor, so that spend is capped before API billing is allowed.
8. **Where the check sits.** After the version check and before the hook checks (proposed: it needs the found program, and a refused login should not run the hook self-test), replacing the 7a "sign-in" step for ACP.
9. **When to build.** The plan under "Schedule effect" (proposed): 10.33 to 10.35 and 10.38 on Nov 10 to Nov 11 with 10.29 to 10.31, then 10.39 and 10.36 on Nov 12, with layer 11 on Nov 13 to Nov 14 and the whole-system test and security scan on Nov 15 to Nov 16. That changes approved Schedule A (answer 10 of 10.22) by one day for layer 11 and one day less for the scan. Or build only 10.33 to 10.35 and 10.38 now and move 10.36 and 10.39 after Dec 3, with KNOWN-LIMITS items, keeping Schedule A unchanged? (Superseded Nov 9 by the addendum: see tasks.md "Schedule to Dec 3".)
10. **Kiro** (replaces "Kiro unchanged"; the owner wants subscription first on every platform). By the Kiro docs every Kiro login, an API key included, pays from the subscription's credits, and nothing beyond them is spent without a purchase by hand. Proposed:
    - remove `KIRO_API_KEY` from every Kiro start, so only the owner's browser login is used;
    - add a `whoami` login check by exit code only (its JSON is not documented and holds the email);
    - offer `umwayi agent login NAME` for Kiro agents (`[KIRO, "login"]`, no flags);
    - no Kiro billing check, because there is nothing to decide about who pays, and the plan and credits cannot be read outside a session.
    
    Open within this: if a real headless Kiro run needs `KIRO_API_KEY` (the Kiro docs conflict), should Kiro `agent run` then be refused (proposed, fail closed) or be allowed the key with a KNOWN-LIMITS item?
11. **`agent login` when already signed in with a subscription.** Run the login check first and start nothing if it passes (proposed: no needless browser sign-in, and no second login stacked on the first), or always start the login when asked?
12. **The login environment.** `child_env()` plus exactly `TERM`, `COLORTERM`, `BROWSER`, `DISPLAY`, `WAYLAND_DISPLAY`, `XDG_CURRENT_DESKTOP`, `XDG_DATA_DIRS`, `DESKTOP_SESSION`, `DBUS_SESSION_BUS_ADDRESS`, `SSH_TTY`, `SSH_CONNECTION`, `SSH_CLIENT` and `NO_BROWSER` (proposed). Or also the legacy desktop names `KDE_FULL_SESSION`, `KDE_SESSION_VERSION`, `GNOME_DESKTOP_SESSION_ID` and `MATE_DESKTOP_SESSION_ID`, for older desktops where `XDG_CURRENT_DESKTOP` is not set? A login without a usable browser still works through the printed URL and the pasted code.

#### Risks (part 7c)

| risk | what happens | what we do |
| --- | --- | --- |
| `loggedIn`, `apiKeySource`, `apiProvider`, `subscriptionType` are not documented by Claude Code and can change | a newer `claude` (for `agent run`, not pinned) refuses every start | fail closed; the message says "could not be confirmed"; the ACP CLI is pinned by the lockfile |
| `auth status` does not see a project setting or a settings `env` the session would use | a check passes and the session pays otherwise | `forceLoginMethod` as a second line; the ACP watch; KNOWN-LIMITS; the owner's real check (10.31) tries an `apiKeyHelper` in a project |
| `auth status` runs a project's `apiKeyHelper` (a shell command) before any gate | a repository's command runs at the check | the agent would run it at start anyway; not documented; KNOWN-LIMITS |
| the login changes between the check and the start, or during a run | the run pays by the new credential | the window is a second; the ACP watch covers chats; not covered for `agent run` and cli chat |
| extra usage beyond the plan | billed, not seen | budget governor (H-078); KNOWN-LIMITS |
| the plan word is shown | `max` or `pro` appears on screen and in the logbook | only that word, from an allow-listed character set; open question 5 |
| `--claudeai` is not in the CLI reference table | a future CLI could refuse it | pinned bundled CLI; the adapter uses the same words; the owner's real check (10.31) |
| the login prints a token or code on the owner's terminal | it is on screen and in the terminal's scrollback | umwayi has no pipe to it and logs nothing; the same as running `claude auth login` by hand |
| a browser opened by the login is the owner's default browser, with the owner's claude.ai session | the owner may sign in to the wrong account | the check after the login names only the plan, so the owner sees `plan: WORD`; the account is the owner's choice |
| Kiro `whoami` exits 0 when signed out | the Kiro check proves nothing | the start then fails at Kiro's own sign-in error (exit 2); KNOWN-LIMITS; the owner's real check |
| a headless Kiro run needs `KIRO_API_KEY` | Kiro `agent run` fails with `KIRO_API_KEY` removed | fail closed; open question 10 |

### OpenCode as a platform (written Nov 9; answered by the owner Nov 11; the adapter is designed in "Part 8: OpenCode over ACP" below)

The owner asked on Nov 9 to include OpenCode (opencode.ai, `anomalyco/opencode`, formerly `sst/opencode`) as a platform, subscription or free first. Facts with links: `adapters/NOTES-layer10.md`, section "OpenCode as a platform". **Nothing is built.** Task 10.41 writes the adapter's spec once the open questions below are answered.

#### What OpenCode gives umwayi, and what it does not

| need (as for Claude Code and Kiro) | OpenCode | fit |
| --- | --- | --- |
| a fixed program, no shell | `opencode` (MIT), installed by the owner | yes |
| a headless run | `opencode run "PROMPT"` (never `--auto`) | yes |
| an ACP chat | `opencode acp`: ACP v1 over stdio, its own private server, exits when stdin closes | **yes, the best match**: umwayi's `acp.py` already speaks it |
| a first gate in front of every tool call | only a JS or TS plugin with `tool.execute.before`, which can throw to block. No command or exec-form hook | **partial**: it would be umwayi's first non-Python adapter code, and how a plugin loads from a path is not confirmed |
| a second gate: permission requests | ACP `session/request_permission` with `once`, `always` and `reject`, also for subagents; but only for actions whose effect is `ask`, and the base policy allows everything | **yes, if** umwayi's config makes every action `ask` |
| a way to set that config without editing the owner's files | `OPENCODE_CONFIG_CONTENT` (inline config, above the project config, below managed files), V1 precedence list; not confirmed for V2 | **not confirmed** |
| a hard limit nobody can widen | V2 `policies`: `tool.use` deny overrides `ask` and saved approvals; `provider.use` and `integration.use` restrict providers however they became known | yes, for denies |
| proof that the gate is active | none documented. A plugin could write the canary token at `session.created` | **not designed** |
| a login and billing check | no `auth status` JSON. `opencode auth list` lists accounts, including environment connections; its output format is not documented | **partial**: restrict by policy, not by reading |

#### The route proposed for the adapter spec (task 10.41)

1. **Transport acp only at first.** `[OPENCODE, "acp"]` in the workdir, with the same start steps as every chat: kill switch, rules with `platform: opencode`, run lock, gate checks, start entry, queue summary. It goes through `acp.py` unchanged, and permission requests are answered by the rules with `once` or `reject` only.
2. **The environment is an allow list** like 10.R11.9, which drops every provider key and `OPENCODE_CONFIG`, `OPENCODE_CONFIG_DIR` and `OPENCODE_DB`. umwayi passes only one generated `OPENCODE_CONFIG_CONTENT` (open question OC2) that holds:
   - `permissions`: `[{"action": "*", "resource": "*", "effect": "ask"}]`, so every tool call becomes a permission request umwayi answers;
   - `policies`: `provider.use` deny `*`, then allow only the agent's chosen provider. Free first means `opencode` (the signed-out free tier) or a local `ollama`, `vllm` or `lmstudio` provider. Subscription means `openai` with the owner's ChatGPT sign-in, or `github-copilot` (open question OC3).
   - `integration.use` deny `*` except that provider, so a saved paid account or a project `.env` key cannot be used;
   - `model`: fixed from agents.yaml (a new `model` key, validated against a plain `provider/model` pattern).
3. **The first gate** (open question OC1): an umwayi plugin in `adapters/opencode/`, plain JS with no npm dependencies, whose `tool.execute.before` runs the layer 9 hook in exec form and throws on a block. A `session.created` handler writes the 7b canary token, so the chat is refused unless the canary is seen. If plugin loading by path cannot be confirmed, the alternative is to accept the permission answer as the only gate for OpenCode, with every action `ask`. That is weaker than Claude Code and Kiro (KNOWN-LIMITS), and needs the owner's explicit yes.
4. **Gate checks:** `opencode` on PATH, its version at least the first V2 release (to be read), the hook script, the plugin file (a regular file, not a link), and the generated config round-trip (`opencode debug config` with the same environment, if it exists in V2; to be checked).
5. **Billing check:** by construction (the policy allows one provider). There is no JSON status to read. A managed `/etc/opencode` file can override umwayi's inline config, so the gate checks refuse when such a file exists (open question OC4).
6. **No login by umwayi in the first adapter.** `opencode acp` with `clientCapabilities: {}` offers only the agent auth method; the owner runs `opencode auth login` (ChatGPT or Copilot) or nothing (free tier, local) beforehand. An `umwayi agent login` for OpenCode could follow the 10.38 shape later.

#### Open questions for the owner (OpenCode)

- **OC1. The first gate.** An umwayi JS plugin with `tool.execute.before` that calls the layer 9 hook (proposed, if path loading is confirmed), or the permission answer as the only gate (every action `ask`), or no OpenCode until a command hook exists? Proposed: the plugin, and refuse the chat when the plugin canary is not seen (as in 7b).
- **OC2. Inline config.** Pass the whole strict config through `OPENCODE_CONFIG_CONTENT` (proposed), or a private config file through `OPENCODE_CONFIG` in umwayi's temporary folder (the canary folder pattern)?
- **OC3. Which routes count as "subscription or free first".** Free: the `opencode` signed-out free tier and local servers (proposed, first). Subscription: ChatGPT Plus or Pro sign-in and GitHub Copilot (proposed, allowed by an explicit agents.yaml `provider` value). OpenCode Go ($10 a month) is a third subscription (proposed: allowed the same way). Pay-as-you-go (Console credits, provider API keys): never in this adapter; only with the budget governor.
- **OC4. Managed configuration.** Refuse when `/etc/opencode/opencode.json(c)` exists, since it outranks umwayi's config (proposed), or read it and refuse only if it widens permissions?
- **OC5. Version.** Pin a minimum OpenCode version and refuse V1 (proposed: the V2 `permissions` and `policies` keys are what the gate relies on), or support both?
- **OC6. When.** Spec only now (task 10.41), build after Dec 3 (proposed: four parts of Schedule A are already full), or build before Dec 3 in place of part of layer 11?

#### The owner's answers (Nov 11)

- **OC1 to OC5: as proposed above**, as written: the umwayi plugin as the first gate with a canary; the inline config through `OPENCODE_CONFIG_CONTENT`; free and local first, then ChatGPT, Copilot and Go sign-ins, never pay as you go; refuse when a managed config exists; pin a minimum version and refuse V1.
- **OC6: changed.** OpenCode is built before Dec 3. tasks.md part 8 (10.42 to 10.51) gives the hours, the order, the tests and what can be cut if time runs short. The owner sets the dates and decides any cut; the spec cuts nothing.
- The facts checked on Nov 11 changed how some answers are built (the V2 plugin API, the place of the inline config among policies). That is in "Part 8: OpenCode over ACP" below, and it raises new questions OC7 to OC14.

### Muse Spark Open as a platform (written Nov 9; answered by the owner Nov 11; designed in "Muse Spark Open as an OpenCode model" below)

The owner asked on Nov 9 to include Meta's Muse Spark Open (open weights, released Oct 15 2026, 816B total and 42B active parameters, Muse Model License), subscription or free first, pay-as-you-go only later. Facts with links: `adapters/NOTES-layer10.md`, section "Muse Spark Open as a platform". **Nothing is built.** Task 10.40 writes the adapter's spec once the open questions below are answered.

#### What was found

- **It is a model, not an agent.** umwayi needs a harness to start it. Meta's own API does not serve it; hosted providers (OpenRouter, Together, Fireworks, Groq preview, Baseten, Modal, Nebius) and local runtimes do.
- **No subscription runs it.** The Muse Code subscription covers the closed Muse Spark, Muse Wonder and Muse Image, and OpenCode Go lists Muse Spark Contributor. Neither lists Muse Spark Open.
- **No free hosted route was confirmed on Nov 9.** An OpenRouter `:free` page appeared in a search, then returned 404. Groq is a limited preview with no stated price. Hugging Face PRO's $2 of monthly credits apply only if HF routes it (not checked).
- **The free route that is sure is local:** about 300 GB of memory for a 2-bit build, 700 GB of VRAM for NVFP4, or two 512 GB Mac Studios.
- **The licence** (read through summaries; the file is gated):
  - free for the owner's use;
  - a "Built with Muse Spark Open" notice in the README or docs once umwayi-os ships an adapter that uses it;
  - the Usage Policy;
  - not for anyone under 18;
  - the $20M model-as-a-service clause does not apply.
- **The harnesses:**
  - **OpenCode** (above) can run it through any provider or a local server, over ACP.
  - **Muse Code** has shell hooks (`PreToolUse`, `PermissionRequest`, `SessionStart`), approvals and a sandbox, but no native ACP, no documented third-party endpoint, and a default model of `muse-spark-1.2`. `META_API_KEY` outranks the subscription.
  - **Claude Code** with another base URL is rejected (10.R12).

#### The route proposed

1. **Muse Spark Open runs as an OpenCode agent**, not as a platform of its own. In agents.yaml it is `platform: opencode` with `provider` and `model` set. The OpenCode adapter (task 10.41) carries the gate, and task 10.40 adds only what Muse Spark Open needs:
   - the provider entries (local `vllm` or a custom OpenAI-compatible server with tools enabled; later hosted providers);
   - the recommended settings (temperature 1.0, top_p 1.0, an explicit `reasoning_effort`);
   - the licence notice;
   - the refusal when the chosen route is not free or a subscription.
2. **Free first:** local only, through the owner's own server URL in agents.yaml (`http://127.0.0.1:...`, refused if not loopback or a private address, open question MS2). A hosted free route is added only after the owner confirms one exists.
3. **Pay-as-you-go later:** OpenRouter, Together or Fireworks at about $1.25 / $4.25 per 1M tokens, only after the budget governor (H-078) can cap it. OpenRouter's prepaid credits fail with 402 instead of billing beyond the balance, which makes it the first paid candidate.
4. **Muse Code stays a separate, later candidate** (open question MS3). It is the only subscription route to Meta's models (the closed Muse Spark), and its shell hooks fit layer 9 better than OpenCode's JS plugins. But it has no ACP, and no documented inline hook source.

#### Open questions for the owner (Muse Spark Open)

- **MS1. Platform or model.** Treat Muse Spark Open as a model behind the OpenCode platform (proposed), or as a platform of its own with its own harness?
- **MS2. Free first means local.** Accept local-only for now (proposed; it needs about 300 GB of memory or more), or wait for a confirmed free hosted route? Which machine would run it?
- **MS3. Muse Code.** Add Muse Code as its own platform for the closed Muse Spark under a Muse Code subscription (`META_API_KEY` removed, Contributor mode off by default), after Dec 3 (proposed), or not at all?
- **MS4. The licence notice.** Put "Built with Muse Spark Open" in the README when the adapter ships (proposed), after the owner has read `LICENSE.md` on Hugging Face.
- **MS5. When.** Spec only now (task 10.40), build after Dec 3 and after OpenCode (proposed).

#### The owner's answers (Nov 11)

- **MS1 to MS4: as proposed above**, as written: a model behind OpenCode; local only for now; Muse Code as its own platform after Dec 3; the licence notice in the README when the adapter ships, after the owner reads `LICENSE.md`.
- **MS5 stands:** spec only (10.40), built after OpenCode. Its design is "Muse Spark Open as an OpenCode model" below, and its tasks (10.52 to 10.55) are not scheduled before Dec 3.

#### Risks (OpenCode and Muse Spark Open)

| risk | what happens | what we do |
| --- | --- | --- |
| OpenCode's default policy allows every tool | permission requests never come, and the rules see nothing | umwayi's inline config makes everything `ask`; refuse if that config cannot be confirmed in effect |
| a saved "Allow always" approval overrides `ask` | some calls run without a request | umwayi never answers `always`; a `tool.use` policy deny for what must never run; KNOWN-LIMITS |
| a managed `/etc/opencode` or MDM profile outranks umwayi | the strict config is overridden | refuse when a managed file exists (OC4) |
| a project `.env` or saved account holds a paid key | the session pays as you go | `integration.use` and `provider.use` allow only the chosen provider |
| the gate needs a JS plugin run by Bun | third-party runtime code inside the first gate | plain JS, no dependencies, in `adapters/opencode/`, with a canary; the owner decides (OC1) |
| OpenCode V1 and V2 differ | the config keys umwayi relies on do not exist | pin a minimum version (OC5) |
| Muse Spark Open has no confirmed free hosted route | free first is local only | MS2 |
| the licence file was read only through summaries | a duty is missed | the owner reads `LICENSE.md` (MS4) |

### Part 8: OpenCode over ACP (10.R13, task 10.41, approved in PR 44; 10.43 to 10.50 built; 10.51, the owner's real check, open)

Requirement 10.R13. Tasks 10.42 to 10.51. Facts: `adapters/NOTES-layer10.md`, "OpenCode V2: the facts checked for the adapter spec" (Nov 11). The owner answered OC1 to OC5 as proposed and asked for the build before Dec 3 (OC6). The owner approved this section (PR 44). Built: 10.43 and 10.44 (PR 47), 10.45 (PR 53), 10.46 (PR 55), 10.47 (PR 62), 10.48 (PR 66), 10.49 (PR 71), 10.50 (PR 74); "As built" at the end of this part lists where the code differs from the text above. Not done: the owner's real check of the chat (10.51), which is the only test against a real OpenCode.

#### What the facts of Nov 11 change

| Nov 9 proposal | Nov 11 fact | what part 8 does |
| --- | --- | --- |
| a plain JS plugin with `tool.execute.before` | V2 drops the V1 hook object. Hooks are registered in `setup(ctx)` with `ctx.tool.hook("execute.before")`, and a throw stops the call. A local plugin must be a directory. The loader needs only `{id, setup}`, not the npm SDK (source) | `adapters/opencode/plugin/index.js`, `export default {id, setup}`, `node:` imports only |
| a `session.created` canary | the event exists in V2 (`ctx.event.subscribe`) | kept; its timing before the first prompt is not confirmed, and the 30 s wait covers it |
| every action `ask` in the inline config | V2 runs `ctx.permission.hook("evaluate")` for `allow` and `ask`, and a plugin may raise `allow` to `ask` | the plugin also raises every `allow` to `ask` (OC8), so a lost or overridden `ask` rule does not remove the second gate |
| `provider.use` and `integration.use` in the inline config | the inline content is the **weakest** source for policies (source): a global, project, Console or managed `allow` outranks umwayi's `deny` | umwayi refuses to start when any other source could hold policies (gate check 5, OC7), and states the Console case as a known limit (OC12) |
| a round trip through `opencode debug config` | in V2 it asks the shared background service, whose environment is not umwayi's | not used. The canary is the proof that the inline config was applied: the plugin is named only there (OC11) |
| a minimum V2 version, to be read | 2.0.0 on Sep 11; `integration.use` in its current meaning and `plugin.use` from 2.2.3; latest 2.2.7 | 2.2.3 or newer (OC14) |
| permission requests answered by the rules | the `toolCall` has `name`, `kind`, `title`, `status`, `locations`, `rawInput`, `content` and `_meta`, but not the permission's action or resources | `permission_action` unchanged: `kind` and `tool` only, never the title or input |

#### What the real install showed (10.42, OpenCode 2.2.7, Nov 11)

Facts: NOTES-layer10.md, "OpenCode 2.2.7 on a real install". Each change below was made to this spec before any code.

| fact | what changed | open question |
| --- | --- | --- |
| A plugin named only in the inline config loads; it runs in Bun 1.4.4 inside the binary; `spawnSync` and an `O_EXCL` write with mode 0600 work; a throw in `execute.before` fails the call with the thrown text | nothing; the design holds | OC1 confirmed |
| `session.created` reaches the plugin 2 ms before the answer to `session/new` | nothing; the 30 s wait stays as the limit | |
| the tools that ask permission are `read`, `glob`, `grep`, `write`, `edit`, `shell`, `webfetch`, `question` and `subagent`; `execute` (Code Mode) does not ask by itself | the plugin's `ASKED` list is exactly those nine; `patch`, `list`, `websearch` and `skill` left out until seen asking, so their Ask me first throws | OC9 |
| Code Mode (`execute`) runs JavaScript with `fetch` and inner tools. Each inner tool passes `execute.before` under its own name (`opencode_worktree_list`) and asks no permission. A `fetch` asks as the `execute` tool call, with the code as `rawInput` and no URL | the starter rules have no rule for `tool_execute` and `tool_opencode_*`, so they are Ask me first by default and the first gate throws for them unless the owner writes a Yes (an Ask rule would make that Yes useless, OC20); KNOWN-LIMITS 190 | new OC15 |
| `settings.baseURL` sets the URL of `vllm`, `ollama` and `lmstudio`; a `models` entry under a built-in local provider breaks the route | the local provider entry is written (it waited for 10.42), with `settings.baseURL` only | |
| a configured model that is not found is replaced silently by another one, which `session/new` reports as `currentValue` (seen with `lmstudio`) | the model compare is the only place this is caught | OC10 |
| Go's provider ID is `opencode-go` in the binary's code, and its integration looks like the Console's own (`opencode#ACCOUNT`); not seen on the wire | Go stays refused; if it is allowed later, only `provider.use` can keep Console credits out | OC13 |
| `opencode --version` prints `opencode v2.2.7` | nothing; the first `N.N.N` is read | OC14 |
| `opencode debug config --standalone` shows the inline config as a document with no path | nothing; the canary is still the proof | OC11 |
| `tool_input` keys are `path`, `command`, `pattern`, `url`, `code` and so on; `kind` is `read`, `search`, `edit`, `execute`, `fetch`, `other` or `think` | the starter rules and the tests use these names | |

#### Files

| file | what | new or changed |
| --- | --- | --- |
| `umwayi/agents.py` | the `opencode` platform, the keys `provider` and `model`, `opencode_env()`, `opencode_inline_config()`, the gate checks, the canary folder, the model compare | changed |
| `umwayi/acp.py` | nothing new: `gate_ready` (7b) and the permission callback already exist; one option, `expect_model`, for the compare in `session/new` (10.R13.11) | changed (about 15 lines) |
| `adapters/opencode/plugin/index.js` | the plugin: two hooks and the canary | new, about 120 lines |
| `adapters/opencode/README.md` | what the owner installs (`npm i -g @opencode/cli`, 2.2.3 or newer), the agents.yaml lines for each route, what is refused and why | new |
| `adapters/opencode/rules.example.yaml` | starter rules for `platform: opencode` (tool calls and `acp_permission`), including a No for any edit or shell command that names `opencode.json`, `opencode.jsonc`, `.opencode`, `rules.yaml`, `LOGBOOK.md` or `.umwayi`, because OpenCode reloads a changed config during a chat (KNOWN-LIMITS 181); no rule on purpose for `tool_execute` and `tool_opencode_*` (Code Mode, OC15, OC20: Ask me first by default, and an Ask rule would make an owner's Yes useless because Ask beats Yes); the `kind` values seen in 10.42 for `acp_permission` | new |
| `tests/agents/fake_opencode.py` | a fake `opencode` that speaks ACP, reads its environment and runs the plugin's canary step | new |
| `tests/agents/test_agents_opencode_*.py` | the tests of 10.R13.14 | new |
| `tests/adapters/opencode_plugin_harness.mjs` | a small fake `ctx` that loads `index.js` under `node` | new |

No file under `umwayi/` gains a third-party import, and umwayi never runs npm, Bun or `opencode plugin add`.

#### The start, step by step

1. Validation (10.R13.2) and the start steps of every chat (kill switch, rules, run lock).
2. The gate checks (below).
3. A private folder `umwayi-opencode-XXXX` in the temporary directory (0700), a fresh 32-byte token, and the inline config.
4. `subprocess.Popen([OPENCODE, "acp"], cwd=WORKDIR, env=opencode_env(...), start_new_session=True)`, stdin and stdout as pipes. (As built, stderr is not discarded: see "As built".)
5. `initialize` with `clientCapabilities: {}`, then `session/new` with `cwd` (absolute) and `mcpServers: []`.
6. The answer's `model` config option is compared with the agent's `model` (OC10).
7. The canary wait (30 s): the file `canary` in the folder must hold exactly the token.
8. Only then the queue summary and the first owner line. From here it is the Kiro ACP chat (part 6) with the 7b stop.

#### The inline config

For an agent with `provider: ollama` and `model: ollama/qwen3-coder`:

```json
{
  "permissions": [{"action": "*", "resource": "*", "effect": "ask"}],
  "policies": [
    {"action": "provider.use", "resource": "*", "effect": "deny"},
    {"action": "provider.use", "resource": "ollama", "effect": "allow"},
    {"action": "integration.use", "resource": "*", "effect": "deny"},
    {"action": "integration.use", "resource": "ollama", "effect": "allow"}
  ],
  "model": "ollama/qwen3-coder",
  "providers": {"ollama": {"settings": {"baseURL": "http://127.0.0.1:11434/v1"}}},
  "plugins": [{
    "package": "/home/me/umwayi-os/adapters/opencode/plugin",
    "options": {
      "hook": ["/usr/bin/python3", "/home/me/umwayi-os/adapters/stdio/hook.py", "--root", "/home/me/umwayi", "--platform", "opencode"],
      "canary": "/tmp/umwayi-opencode-abcd/canary",
      "token": "TOKEN"
    }
  }]
}
```

- `opencode`: `integration.use` allows the bare `opencode`, so only the signed-out free tier is used. No `providers` entry.
- `openai` and `github-copilot`: `integration.use` allows `openai#*` or `github-copilot#*`, the connected-account form, and never the bare name, which is an environment key. No `providers` entry.
- Local routes: the provider entry is `{"ID": {"settings": {"baseURL": URL}}}` with the documented default loopback URL (Ollama `http://127.0.0.1:11434/v1`, LM Studio `http://127.0.0.1:1234/v1`, vLLM `http://127.0.0.1:8000/v1`). 10.42 confirmed on 2.2.7 that `settings.baseURL` sets where all three look. It also showed that a `models` entry under a built-in local provider breaks the route (`provider.no-route`), so umwayi never writes one.
- The JSON is written with sorted keys, no spaces and ASCII only, so the same agent and token give the same bytes.

#### The plugin

```js
import { spawnSync } from "node:child_process"
import { openSync, writeSync, closeSync, constants } from "node:fs"

// the tools seen asking permission on 2.2.7 (10.42); any other tool's Ask me first throws
const ASKED = new Set(["read", "write", "edit", "shell", "glob", "grep", "webfetch", "question", "subagent"])

export default {
  id: "umwayi.gate",
  async setup(ctx) {
    const { hook, canary, token } = ctx.options            // only umwayi writes these
    await ctx.tool.hook("execute.before", (event) => {
      let code = 2
      try {
        const r = spawnSync(hook[0], hook.slice(1), {
          input: JSON.stringify({ tool_name: String(event.tool), tool_input: event.input ?? {} }),
          timeout: 10000, stdio: ["pipe", "ignore", "ignore"], shell: false })
        code = r.error ? 2 : r.status
      } catch { code = 2 }
      if (code === 0) return
      if (code === 3 && ASKED.has(String(event.tool))) return   // the permission request asks the owner
      throw new Error("umwayi: this tool call was not allowed by the rules")
    })
    await ctx.permission.hook("evaluate", (event) => {
      if (event.effect === "allow") event.effect = "ask"
    })
    let written = false
    void (async () => {
      for await (const _ of ctx.event.subscribe({ types: ["session.created"] })) {
        if (written) continue
        written = true
        try {
          const fd = openSync(canary, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL, 0o600)
          writeSync(fd, token); closeSync(fd)
        } catch { /* no canary: umwayi refuses the chat */ }
      }
    })()
  },
}
```

- **Fail closed:** every path except exit 0, or exit 3 for an asked tool, throws. A missing option makes `spawnSync` fail, and that throws too. A plugin that does not load writes no canary, so the chat is refused.
- **The error text is fixed.** It never holds the tool input or the hook's output, so nothing the agent wrote comes back through it.
- The real `index.js` validates `ctx.options` first. If `hook` is not an array of strings, or `canary` or `token` is not a string, `setup` throws, so the plugin does not load and the canary is never written.

#### The gate checks (10.R13.8)

| order | check | refused when | the line names |
| --- | --- | --- | --- |
| 1 | command | `opencode` not on PATH | install `@opencode/cli` 2.2.3 or newer |
| 2 | version | no `N.N.N` in the output, or older than 2.2.3, or a 1.x | the version found and the minimum |
| 3 | files | the hook or `index.js` missing, a link, or outside the source tree | the file |
| 4 | managed config | `/etc/opencode` (Linux), `/Library/Application Support/opencode` or a managed plist (macOS) exists | the path; "a managed config outranks umwayi's" |
| 5 | other config | a project `opencode.json(c)` or `.opencode` from the workdir up to `/`; a global config file holding a listed key; a global `plugins` or `agents` directory | the path and the key, never the file's text |
| 6 | route | a `provider` that is not allowed now (pay as you go, Go before 10.42 confirms it) | the provider and "pay as you go is not offered" |

Checks 4 and 5 read only names and, in check 5, the bytes of at most two small files, searched for fixed words. They never print the content.

#### The permission answers (10.R13.9)

The existing `permission_action(agent, tool_call, "opencode")` makes `{"type": "acp_permission", "agent", "platform": "opencode", "kind", "tool"}`. A plain V2 tool name such as `shell` or `read` passes `_PLAIN_TOOL` (a letter, then up to 39 letters, digits, `_` or `-`), and so does an MCP name such as `mcp__github__create_issue`; a name with `:` or `.`, or over 40 characters, does not, so it is left out and the rules see only `kind`. `permission_verdict` is unchanged. Ask me first asks the owner on the terminal, as in a Kiro ACP chat. With the starter rules, a Yes in the first gate is often followed by a request that the rules answer Yes too (`acp_permission` with `kind: read`), so the owner is asked only for what the rules say Ask me first.

#### Failure table

| what goes wrong | what happens | exit |
| --- | --- | --- |
| `opencode` missing, V1, older than 2.2.3, or a version that cannot be read | refused before the start | 2 |
| a managed config, a project config, or a global config with a listed key | refused before the start | 2 |
| a route that is not free or a subscription | refused before the start | 2 |
| the plugin does not load (a later OpenCode ignores the inline config, a `plugin.use` deny elsewhere, a JS error) | no canary within 30 s, the agent stopped, nothing of the owner sent | 2 |
| a wrong token in the canary file | refused like no canary | 2 |
| `session/new` reports another model | refused before the first prompt | 2 |
| the hook times out, crashes or cannot start | that tool call throws and does not run; the chat goes on | |
| a tool OpenCode does not ask permission for gets Ask me first | that tool call throws; one `umwayi check` entry says Ask me first | |
| a permission request with no `name` | Ask me first at most | |
| `auth_required` from a prompt | the chat ends with "run `opencode auth login` first" | 2 |
| the kill switch turns on | the 7b stop: process group and every seen descendant | 3 |
| a connected Console workspace allows more than umwayi's policies | not detected (KNOWN-LIMITS 182) | |
| the configured model is not served, and OpenCode picks another one | the model compare at `session/new` refuses (10.42 saw this with `lmstudio`) | 2 |
| OpenCode downloads `ripgrep` into its cache on first use | not stopped and not seen by umwayi; the inline policies do not cover it (KNOWN-LIMITS 191) | |
| the model uses Code Mode (`execute`) | the first gate checks `execute` and each inner tool; Ask me first throws, because they ask no permission (KNOWN-LIMITS 190) | |

#### New open questions (OC7 to OC15), each with the proposal the spec uses

- **OC7. Other config sources.** Refuse when a project config exists or the global config holds a listed key (proposed, gate check 5). The other way is to set `OPENCODE_DISABLE_PROJECT_CONFIG=1` and point `OPENCODE_CONFIG_DIR` at an empty private folder. Both variables are read in the V2 source but are on no V2 docs page, and the second hides the owner's own global settings too.
- **OC8. The evaluate hook.** Raise every `allow` to `ask` in the plugin as well (proposed), or rely on the inline `ask` rule alone.
- **OC9. Ask me first in the first gate.** Let the call go on to the permission request for tools OpenCode asks permission for, and throw for any other (proposed). The other way is to throw on every Ask me first, so the owner is never asked during the chat and each Ask me first becomes a refused call, as on Kiro. *10.42:* the list of tools that ask is now the nine seen on 2.2.7. A tool left out fails closed (it throws), so a short list only costs the owner a question they could have answered.
- **OC10. The model compare** at `session/new` (proposed), or trust the inline config. *10.42:* OpenCode replaced a model it could not find with another one without any error, so trusting the inline config would let a chat run on a model the owner did not choose.
- **OC11. `opencode debug config`.** Not used, because the canary proves the inline config was applied (proposed). The other way is to use it with `--standalone` once that is confirmed to show a private server's view. *10.42:* `--standalone` does show the inline config, as a document with no path. The proposal is unchanged: that view comes from a second process, while the canary comes from the chat's own server.
- **OC12. A connected Console workspace.** Its policies rank right below managed ones and umwayi cannot read the database. Accept this as a known limit (proposed), or refuse when `opencode auth list` shows a Console account. That command's output format is not documented.
- **OC13. OpenCode Go.** Refused until 10.42 confirms its provider ID and integration resource (proposed), or left out of the first build. *10.42:* the provider ID is `opencode-go` in the binary's code. Its integration looks like the Console's own, so `integration.use` cannot keep Console credits out, and only `provider.use` (allow `opencode-go`, deny `opencode`) could. This was not seen with a real Go sign-in, so Go stays refused.
- **OC14. The minimum version.** 2.2.3 (proposed: the first release that honours every policy the design uses), or the latest release on the day of the build. *10.42:* only 2.2.7 was run. 2.2.3 to 2.2.6 are allowed by the proposal, but none of the 10.42 results was seen on them.
- **OC15. Code Mode** (new, from 10.42). The `execute` tool runs JavaScript that can `fetch` and call OpenCode's own tools, among them `worktree_remove`; those inner tools ask no permission. Proposed: no new mechanism. The first gate sees `execute` and each inner tool by name, and they are Ask me first by default (the starter rules leave them without a rule on purpose, OC20), so they throw unless the owner writes a Yes. The other way is to refuse the start unless Code Mode can be turned off by config. No switch for it was found in 10.42.

#### Build order, hours and what can be cut

The tasks are in tasks.md, part 8 (10.42 to 10.51): about 21.5 hours of build and 1.5 hours of the owner's, in that order. tasks.md lists what could be cut and what each cut costs. **The owner decides any cut; the spec cuts nothing.**

#### As built (tasks 10.43 to 10.50, checked against the code on Nov 13 in the docs half of 10.51)

The text above is the design as approved. The code follows it, with these differences and additions. None changes a safety rule.

- **stderr.** `Popen` is not given `stderr=DEVNULL`: OpenCode's stderr is umwayi's, so it reaches the owner's terminal (KNOWN-LIMITS 251).
- **No private `HOME`.** `opencode_env()` passes `HOME` and the `XDG_*` folders through. umwayi gives OpenCode no home of its own, so what OpenCode writes (its database, logs and the downloaded `rg`, KNOWN-LIMITS 191) goes to the owner's real folders unless the owner starts umwayi with another `HOME` (the owner's check does, `adapters/NOTES-layer10.md`).
- **MCP names.** A name such as `mcp__x__y` is a plain word and is sent to the rules as `tool` (KNOWN-LIMITS 183, 248).
- **A request with no `name`** gets at most Ask me first: `Run._permission` caps a Yes after the check (10.49, KNOWN-LIMITS 248).
- **`agent run` and `agent login`** for OpenCode give exit 64. `transport` is `acp` (the default) and `cli` is a problem in `agent validate`. The shape of `provider` and `model` is checked by `agents.yaml`; whether the route is offered is decided at the start (OC16, OC17).
- **The model compare** (`expect_model`) is an exact text compare (KNOWN-LIMITS 243); an `auth_required` answer, or a prompt error that mentions "auth", ends the chat with the sign-in line (KNOWN-LIMITS 242).
- **The stop.** An OpenCode chat uses the 7b stop (the process group and every seen descendant), as Claude Code does. Until 10.50 it stopped the group only.
- **Files that differ from the table.** `adapters/opencode/README.md` was written in 10.51. The tests are `tests/agents/test_agents_opencode_*.py` (config, file, gate, chat, turns, faults), `test_fake_opencode.py`, `tests/adapters/test_opencode_plugin.py` and `test_opencode_rules.py`, and `tests/agents/opencode_mutants.py`, a helper that is not part of the suite or CI.
- **Not built:** the Muse Spark Open route (10.52 to 10.55), a real run of any route (the ChatGPT and Copilot routes are written and tested as config bytes and with the fake, and were never seen with a real sign-in, KNOWN-LIMITS 182), the order of the evaluate hooks of other plugins (KNOWN-LIMITS 184), and any private `HOME` or network sandbox (KNOWN-LIMITS 191).

### Muse Spark Open as an OpenCode model (10.R14, task 10.40, written Nov 11; built after OpenCode, not before Dec 3)

Requirement 10.R14. Tasks 10.52 to 10.55, not scheduled before Dec 3 (MS5). Facts: NOTES-layer10.md "Muse Spark Open as a platform" (read Nov 9; not read again on Nov 11, so the hosted routes, the licence summary and the hardware figures are as of Nov 9).

#### What it adds to part 8

- **One route:** `provider: umwayi-local`, a custom OpenAI-compatible provider. Its URL comes from `base_url` in agents.yaml, a loopback or private address only (MS2).
- **The provider entry** in the inline config:

  ```json
  "providers": {"umwayi-local": {
    "package": "@opencode/ai/providers/openai-compatible",
    "settings": {"baseURL": "http://127.0.0.1:8000/v1"},
    "models": {"muse-spark-open": {"capabilities": {"tools": true},
                                   "settings": {"temperature": 1.0, "top_p": 1.0, "reasoning_effort": "medium"}}}
  }}
  ```

  `package` and `settings.baseURL` are on the V2 Policies page. `capabilities.tools` is seen in the V2 plugin docs (`model.capabilities.tools`). The `settings` keys for temperature, top_p and the reasoning effort are **not confirmed**: 10.52 confirms them on a real install, and until then the route is refused (MS6).
- **Policies:** `provider.use` and `integration.use` allow `umwayi-local` only.
- **The model ID** in `model` is `umwayi-local/NAME`, where NAME is what the owner's server serves (for example `muse-spark-open`). umwayi does not check that the served model really is Muse Spark Open; the owner's server decides.
- **Refused:** every hosted provider, as every pay-as-you-go route in part 8. The refusal line names OpenRouter's prepaid credits as the first paid candidate once the budget governor can cap a route.
- **The notice:** "Built with Muse Spark Open" in the README, written in 10.55 only after the owner has read `LICENSE.md` and said so (MS4).
- **Muse Code** (MS3): its own platform after Dec 3, with its own spec. Nothing here.

#### New open questions (MS6 to MS8)

- **MS6. Unconfirmed field names.** Refuse the `umwayi-local` route until a real install confirms the V2 field names for tools and settings on a custom provider (proposed).
- **MS7. Plain `http` to a private address.** MS2 allows loopback or private addresses. Proposed: allow `http` for both, because it is the owner's own network, and state that prompts and code then cross the LAN unencrypted (KNOWN-LIMITS 188). The other way is to require `https` for any address that is not loopback.
- **MS8. The default reasoning effort.** `medium` when `reasoning_effort` is not set (proposed), or require the key.


## Layer 11: Linux-like features (approved, tasks.md 11.0; built now, L11-Q14)

Requirements 11.R1 to 11.R8. Tasks 11.0 to 11.6. Facts with links: `adapters/NOTES-layer11.md`. Built only after the owner approves this section (11.0). Layer 6 says "Nothing in umwayi installs a schedule"; if this is approved, that stays true except for `umwayi schedule install`, which the rules ask about and the logbook records, and which writes two unit files and starts nothing.

### The candidates

The outline named five Linux tools. None was assumed to be in scope. For each: what it would give umwayi-os, what it costs, what could break, and the recommendation.

| candidate | what it gives | what it costs | what could break | recommendation |
| --- | --- | --- | --- | --- |
| scheduled runs: systemd user timers (cron as a printed alternative) | the weekly report, the open-queue job and the content loop run without the owner typing them; missed runs catch up after the machine was off (`Persistent=`); a stop ends every process of the run (`KillMode=control-group`) | about 11 hours; two unit files per schedule in `~/.config/systemd/user`; no new runner, because the timer calls `umwayi run` and `umwayi workflow run`, which already check the kill switch, the run lock, the rules and the logbook | a hand edit or a drop-in changes what runs (found by `schedule check`); timers stop when the owner logs out unless lingering is on; a run that finds the run lock held answers Ask me first and waits for the next time; the unit's environment is the user manager's, not the shell's | **include** (L11-Q1) |
| file watching: inotify | a new article could start the content loop at once instead of at the next timer | no standard library binding: `ctypes` (a bug becomes a crash, not exit 2), a third party package, or `inotifywait`; a long running watcher process, which nothing in umwayi is today | events are dropped on overflow, not recursive, missing on network file systems; inotify does not say who wrote, so a workflow's own drafts can trigger it again (a loop); systemd path units have the same limits and fail after their rate limit | **cut for Dec 3**; a timer covers it. A systemd path unit can be specified later (L11-Q10) |
| queryable state: SQLite | questions such as "every Ask me first for agent reviewer this month" without reading the whole logbook; faster budget totals | `sqlite3` is standard library (allowed), but a second copy of the truth has to be kept in step with the plain files; a schema, a rebuild command, and tests for drift | the index and the files disagree after a crash or a hand edit; WAL does not work on a network file system; the SQLite version comes with each Python build; the owner might trust the index over the logbook | **defer** after Dec 3, as a read only index rebuilt from the files (L11-Q11) |
| long chats: tmux | a chat that survives a closed terminal or an SSH drop, and can be reattached | an integration that starts `tmux new-session -d` and keeps track of sessions | tmux runs its command as a shell command (multiple arguments not documented to avoid the shell); the program gets the tmux server's environment, not umwayi's filtered one; the chat holds the run lock for hours, so every scheduled run answers Ask me first; any process of the owner's user can `send-keys` into the chat or `capture-pane` its text; the owner's `~/.tmux.conf` can run commands from hooks | **cut from umwayi**: the owner can run `tmux new -s chat` and then `umwayi agent chat NAME` inside it today, with no code (L11-Q12) |
| sandboxing: bubblewrap (systemd user sandboxing and Landlock as alternatives) | an agent that can write only its workdir and cannot read `~/.ssh` or other repos; umwayi's own helpers without the network | its own spec: the bind list, the environment, AppArmor on Ubuntu, and how the hook gets out | the layer 9 hook runs inside the agent's tree and must write `.umwayi/` and `LOGBOOK.md`, so the sandbox cannot make the logbook or the kill switch read only for the agent; agents need the network; Ubuntu's AppArmor restriction stops `bwrap` until an administrator adds a profile; Claude Code runs its own bwrap sandbox for Bash, and nesting is not documented; systemd user sandboxing needs the same user namespaces; Landlock needs `ctypes` | **defer** to its own spec after Dec 3, once the check can run outside the agent's sandbox (L11-Q13) |

### Layout (if approved)

```
umwayi/schedule.py        read schedule.yaml, render the two units and the cron line, install, remove, check
umwayi/cli.py             the schedule subcommands
schedule.example.yaml     a commented example (the owner copies it to schedule.yaml)
rules.yaml                two starter rules: schedule-install-ask (Ask me first), schedule-remove-yes (Yes)
tests/test_schedule.py    real child processes, HOME and XDG_CONFIG_HOME in a temporary folder
```

No change to `jobs.py`, `workflow.py`, `runlock.py`, `kill.py` or the logbook.

### schedule.yaml

```yaml
schedules:
  - name: weekly-report
    run: job
    jobs_file: jobs.yaml
    job: weekly-report
    every: weekly
    day: mon
    at: "07:30"
  - name: content-loop
    run: workflow
    workflow: content-loop
    every: daily
    at: "08:00"
```

Read with `miniyaml`, checked as 11.R1 says. `at` is written in quotes; a value that is not the string `HH:MM` is a problem with its line. `day` for `monthly` stops at 28, so every month has it.

### The path rule

`_SAFE_PATH = re.compile(r"^/[A-Za-z0-9/._+-]*$")`, at most 1024 characters, no path part that is `.` or `..`, and it is the real path (`os.path.realpath`), so no link in it is resolved later. It is applied to the root, the jobs file, `sys.executable` and the umwayi source folder (`agents.umwayi_src()`). With these characters only, a unit file line and a cron line need no quoting, no `%%` and no `$$`, and `/bin/sh` sees one word per path. A path outside the rule is refused with, for example, "schedule: the root path has a character a unit file cannot hold safely (allowed: letters, digits, / . _ + -). Move the root and try again." (64).

### The rendered files (exact templates)

Unit names: `umwayi-{rootid}-{name}`, where `rootid = sha256(realpath(root))[:8]`.

`umwayi-{rootid}-{name}.service`:

```
# Written by umwayi schedule install for the entry {name} of {root}/schedule.yaml.
# umwayi schedule check compares this file byte for byte: change schedule.yaml, not this file.
[Unit]
Description=umwayi scheduled run {name} ({root})

[Service]
Type=oneshot
WorkingDirectory={root}
Environment=PYTHONPATH={src}
ExecStart={python} -m umwayi --root {root} run {jobs_file} --job {job}
TimeoutStartSec=30min
TimeoutStopSec=15s
KillMode=control-group
```

For a workflow the `ExecStart=` line is `{python} -m umwayi --root {root} workflow run {workflow}`.

`umwayi-{rootid}-{name}.timer`:

```
# Written by umwayi schedule install for the entry {name} of {root}/schedule.yaml.
# umwayi schedule check compares this file byte for byte: change schedule.yaml, not this file.
[Unit]
Description=umwayi schedule {name} ({root})

[Timer]
OnCalendar={calendar}
Persistent=true
Unit=umwayi-{rootid}-{name}.service

[Install]
WantedBy=timers.target
```

`{calendar}`: daily `*-*-* HH:MM:00`; weekly `Mon *-*-* HH:MM:00` (`Mon` to `Sun` from `day`); monthly `*-*-DD HH:MM:00`, all in the normal forms systemd.time(7) documents. No `RandomizedDelaySec`, no `WakeSystem`, no time zone suffix (the owner's local time).

The cron line (`show --cron`, printed only): `MM HH * * * /usr/bin/env PYTHONPATH={src} {python} -m umwayi --root {root} run {jobs_file} --job {job}`, with day of week `1` to `7` for weekly and day of month for monthly. It is preceded by one comment line saying it is the same run as the timer and that umwayi never installs a crontab.

### install, step by step

1. Load `schedule.yaml` and the entry; apply 11.R1 and the path rule (64).
2. Render both files. If both exist in the unit folder with exactly these bytes: print "Schedule NAME is already installed. Nothing was changed." and the `systemctl` commands, exit 0, no rule asked, nothing written.
3. The kill switch (`kill.state`): on or unknown gives 3 and one entry "Schedule NAME was not installed: the kill switch is on" (or unknown).
4. The rules with the `schedule_install` action (11.R4.1). Ask me first without `--approved-by`: one queue item `Install schedule NAME?` through `taskqueue.add_once`, exit 3. With `--approved-by WHO` (one line, at most 100 characters): go on, and WHO goes into the entry. No: 2.
5. The run lock (`runlock.held`), held to the end: busy or unavailable gives 3 and one entry.
6. The unit folder: create it with its missing parents (`os.makedirs`, default mode), then `lstat` it: it must be a folder and not a link (2). For each file: `os.open(path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0o644)`, write, `fsync`, close; then `fsync` the folder (`fsutil.fsync_dir`). An existing file means a different one is there (step 2 caught the identical case): 2, nothing written. Any error after the service was written removes the service.
7. One logbook entry: "Installed schedule NAME (run, target, every): umwayi-ROOTID-NAME.service and .timer in FOLDER", checked "the rules (RULE gave ANSWER), approved by WHO; SHA-256 SERVICE_HASH and TIMER_HASH", not done "Nothing was started: the owner enables the timer with systemctl --user". If it fails, both files are removed and the answer is 2 ("The logbook could not record the install, so the files were removed").
8. Print the two paths and the commands of 11.R4.1.

### remove, step by step

1. Load the entry (64). Neither file present: "Schedule NAME is not installed. Nothing was changed.", exit 0.
2. The enable link `FOLDER/timers.target.wants/UNIT.timer` exists (`os.path.lexists`): 2, with the `disable --now` and `clean --what=state` commands.
3. A drop-in folder `UNIT.service.d` or `UNIT.timer.d`, a file that is not regular, or bytes that differ from the render: 2, "remove it by hand".
4. The rules with the `schedule_remove` action (No 2, Ask me first 3 and one queue item `Remove schedule NAME?`).
5. Read both files' bytes (for putting back), remove the timer, then the service, then `fsync` the folder.
6. One logbook entry. If it fails, both files are written back from the saved bytes (`O_EXCL`) and the answer is 2.
7. Print `systemctl --user daemon-reload`.

### check

For each entry, without a lock and without writing: `installed` (both files identical), `not installed`, `changed` (bytes differ; the line says which file), `not a regular file`, `drop-in: UNIT.d` (each), and `enabled` or `not enabled` from the link. Then each `umwayi-ROOTID-*.service` or `.timer` in the folder with no entry: `left over`. Only the umwayi folder of the load path is looked at (KNOWN-LIMITS: a unit of the same name earlier in the load path, or a drop-in in another folder, is not seen; `systemd-analyze --user cat-config` is the owner's check). Exit 0 only when every entry is `installed` with no drop-in and nothing is `left over`; otherwise 2.

### The scheduled run

The service runs the front door exactly as the owner would type it, without `--date`, so the system clock dates its entries. What happens then is layers 6 and 8, unchanged:

- `umwayi run`: the kill switch first (3, one entry), then the run lock (busy: 3, one entry), then the jobs file, the logbook check, the gap rule (1, no entry), the rules (`run_job`), the work and one entry.
- `umwayi workflow run`: the helper base takes the kill switch and the run lock first, then each step asks the rules (`workflow_step`) with one entry per step; the approve step stops with Ask me first (3) and one queue item.

umwayi's output goes to the user journal (systemd's default for a service). systemd marks the unit failed for any code but 0 (11.R5.5).

### Failure table

| failure | what the owner sees | exit |
| --- | --- | --- |
| `schedule.yaml` missing, too big, a link, not UTF-8, not valid | each problem with its line | 64 |
| an unknown job or workflow, or `min_gap_days` longer than the period | the line and the reason | 64 |
| a path outside the path rule | which path (root, jobs file, Python, source) and the allowed characters | 64 |
| install: already installed, identical | "already installed. Nothing was changed." | 0 |
| install: kill switch on or unknown | Ask me first, the reason, one entry | 3 |
| install: rules No | No, the rule, the reason | 2 |
| install: rules Ask me first, no `--approved-by` | Ask me first, one queue item `Install schedule NAME?` | 3 |
| install: run lock held | Ask me first, one entry | 3 |
| install: unit folder a link or not a folder; a different file already there | the reason, nothing written | 2 |
| install: the logbook cannot record it | the files were removed | 2 |
| remove: not installed | "not installed. Nothing was changed." | 0 |
| remove: the timer is enabled | the `disable --now` and `clean --what=state` commands | 2 |
| remove: changed by hand, a drop-in, not a regular file | "remove it by hand" | 2 |
| remove: the logbook cannot record it | the files were put back | 2 |
| check: anything but every entry installed and identical | one line per entry | 2 |
| any unexpected error | "stopped by an unexpected error (TYPE)", nothing half written | 2 |

### Tests (11.R7)

- **Fakes:** none for systemd. Every test sets `HOME` and `XDG_CONFIG_HOME` to a temporary folder and runs `python -m umwayi schedule ...` as a real child process.
- **validate:** a table of bad files (each key missing, unknown key, bad name, duplicate, `run: shell`, `every: hourly`, `at: 24:00`, `at: 7:3`, `day` on daily, `day: 29` on monthly, `day: monday`, a jobs file outside the root, a job with `min_gap_days: 7` on a daily schedule, a missing workflow, 21 entries, 64 KB plus one byte, a link, invalid UTF-8), each 64 with its line, nothing written.
- **The path rule:** a root containing a space, `%`, `$`, `'`, `"`, `\`, `;`, a newline, a non-ASCII letter, a `..` part; each 64, and the message holds no control character.
- **show:** the exact bytes of the service and timer for daily, weekly and monthly, a job and a workflow; the cron line for each; two runs give the same bytes; two roots give two ROOTIDs.
- **install:** Yes; No (2); Ask me first (3, one queue item, the same after a second call); `--approved-by` (0, WHO in the entry); kill switch on and unknown (3, one entry, no file); run lock held by a helper process (3); already installed (0, no entry); a different file present (2, untouched); the unit folder a link (2); a planted fault after the service is written (2, no file left); a logbook that cannot be written (2, no file left); mode 0644; the output holds both `systemctl --user` commands and the lingering line.
- **remove:** not installed (0); the enable link present (2, both commands printed); changed (2); a drop-in (2); No and Ask me first; a logbook failure (2, both files back byte for byte); success (0, one entry, both gone).
- **check:** every state of 11.R3.3, alone and together; it writes nothing (the folder snapshot is equal before and after).
- **The scheduled run end to end:** the test reads the rendered service, takes `ExecStart=` split on spaces (the path rule guarantees one word per path) and `Environment=`, and runs it as a real child in `WorkingDirectory=`: a `queue-list` job exits 0 with one entry; with the kill switch on it exits 3 with one entry; with the run lock held by another process it exits 3; a workflow run stops at its approve step with 3 and one queue item.
- **Code guards:** `schedule.py` imports only standard library modules and none of `subprocess`, `socket`, `urllib`, `http`, `ctypes`; no string `systemctl`, `crontab` or `loginctl` is in any argument list in `umwayi/`; the strings appear only in printed text.
- **Exit codes:** every test asserts the code is in {0, 2, 3, 64}.
- **Planted faults and mutation checks (11.5):** the path rule removed; `O_EXCL` dropped (an existing file overwritten); the kill switch not checked; the rules not asked; Ask me first treated as Yes without `--approved-by`; the run lock not taken; the logbook failure not undone; remove ignoring the enable link; remove deleting a changed file; check not seeing a drop-in; `TimeoutStartSec` or `KillMode` left out; `Persistent` set false; the agent front door allowed as a target.

### KNOWN-LIMITS (written with 11.5, numbered from 93)

- Timers run only while the owner is logged in, unless the owner enables lingering; umwayi never does.
- Anyone who can write `~/.config/systemd/user` can change a schedule, add a drop-in, or add a unit that runs anything. `schedule check` sees the umwayi folder only, not a unit or drop-in of the same name earlier in the load path.
- A scheduled run that finds the run lock held (a long chat, another job) answers Ask me first and is not retried until its next time.
- A run stopped at the start limit writes no entry; the journal has it.
- umwayi's output goes to the user journal, which the owner (and administrators) can read.
- `umwayi run` keeps its layer 6 code 1 for a refusal (the gap rule), which shows as a failed unit.
- The calendar is local time; what a timer does at a daylight saving change is not documented on the pages read.
- A SIGKILL during install between the two files leaves the service without its timer; `schedule check` reports it.
- The unit folder must be a real folder: a dotfiles setup that links `~/.config/systemd/user` is refused.

### Schedule effect

About 11 hours (tasks.md 11.1 to 11.5) plus 0.5 hour of the owner's (11.6): it fits Nov 14 to Nov 15 as planned. Nothing else moves: the hash chain on Nov 16, the budget governor Nov 17 to Nov 22, the whole-system test and security scan Nov 23 to Nov 26 (which then covers `schedule.py` and the rendered unit files), README, demo and Devpost Nov 23 to Nov 28, the freeze Nov 29 to Dec 2, submit Dec 3. If the owner approves after Nov 13, layer 11 moves after Dec 3 rather than pushing the chain or the governor (L11-Q14).

### Risks (layer 11)

| risk | what happens | what we do |
| --- | --- | --- |
| a unit file changed by hand or by an agent | a timer runs something other than umwayi | `schedule check` byte compare; KNOWN-LIMITS; the rules see `tool_bash` commands that write there (layer 9) |
| a drop-in next to the unit | the same, without touching the file umwayi wrote | `check` and `remove` look for `UNIT.d/` |
| the user manager's environment differs from the shell | `python -m umwayi` cannot import, or finds another umwayi | an absolute interpreter and `PYTHONPATH` in the unit; the owner's real check (11.6) |
| a scheduled run collides with a chat | the run answers Ask me first and is skipped | KNOWN-LIMITS; the owner picks times |
| the owner never enables the timer | nothing runs | install prints the exact commands; `check` shows `not enabled` |
| systemd changes its unit syntax | a unit fails to load | only long-standing settings are used (for example `OnCalendar=` since systemd 197, `Persistent=` since 212, `KillMode=` since 187); `systemd-analyze --user verify` in 11.6 |

### Open questions for the owner (layer 11, answered)

1. **L11-Q1. Scope for Dec 3.** Only scheduled runs (proposed). Or add one of the deferred candidates now, in place of time elsewhere?
2. **L11-Q2. Which scheduler.** systemd user timers installed by `schedule install`, and cron lines only printed by `show --cron` (proposed). Or install a crontab line too (umwayi would have to rewrite the whole table), or support cron only?
3. **L11-Q3. Who runs systemctl.** umwayi writes the two files and prints the `systemctl --user` commands; it never runs `systemctl` itself (proposed: nothing outside umwayi's files changes unless the owner types it, and the tests need no systemd). Or let `install` run `daemon-reload` and `enable --now`?
4. **L11-Q4. Approving an install.** A starter rule makes `schedule_install` Ask me first, and `--approved-by WHO` lets it go on, as for `publish-draft` (proposed; self-declared, KNOWN-LIMITS 1). A starter rule makes `schedule_remove` Yes. Or require a Yes rule for each schedule?
5. **L11-Q5. What may be scheduled.** Jobs and workflows only; never `agent run`, `agent chat` or `agent login` (proposed). Or allow `agent run` after the budget governor is built?
6. **L11-Q6. Missed runs.** `Persistent=true`, so a run missed while the machine was off runs at the next start; the layer 6 gap rule still stops a job that ran too recently (proposed). Or `false`?
7. **L11-Q7. The start limit.** `TimeoutStartSec=30min` for every scheduled run (proposed; jobs take seconds, a workflow minutes). Or a per-entry value?
8. **L11-Q8. Lingering.** umwayi never runs `loginctl enable-linger`; install says that timers then run only while the owner is logged in (proposed). Or document lingering as the recommended setup?
9. **L11-Q9. Exit code 1 from `umwayi run`.** Keep layer 6's code 1 for a refusal, shown as a failed unit (proposed: no change to layer 6). Or add `SuccessExitStatus=1` so a gap rule refusal does not show as failed?
10. **L11-Q10. File watching.** Cut for Dec 3; a timer covers the content loop (proposed). Later: a systemd path unit spec. Or a `ctypes` inotify watcher now?
11. **L11-Q11. SQLite.** Defer to after Dec 3, as a read only index rebuilt from the plain files (proposed). Or build a first `umwayi index` now?
12. **L11-Q12. tmux.** Cut from umwayi; the README shows the owner how to run `umwayi agent chat` inside tmux by hand (proposed). Or a `umwayi agent chat NAME --tmux` later?
13. **L11-Q13. Sandboxing.** Defer bubblewrap to its own spec after Dec 3, whose first question is how the check runs outside the agent's sandbox (proposed). Or an opt-in `sandbox: bwrap` for `agent run` now, with the logbook writable inside it?
14. **L11-Q14. When.** Build Nov 14 to Nov 15 if approved by Nov 13; otherwise after Dec 3, never pushing the hash chain (Nov 16) or the budget governor (proposed).

Answers (owner): L11-Q1 to L11-Q13 as proposed. L11-Q14 changed by the owner: build now, right after PR 30 merged, not on Nov 14 to Nov 15; the hash chain, the budget governor and the rest of the schedule do not move.

## Budget governor (approved by the owner on Nov 9, tasks.md B.0; build Nov 17 to Nov 22, built early in PR 33; tested in the whole-system test Nov 23 to Nov 26)

Requirements B.R1 to B.R3. Tasks B.0 to B.10. It fails closed and logs every change like the other layers. The core stays standard library only.

### Added while building (PR 33)

- **units.yaml uses block mappings.** The YAML reader of umwayi (miniyaml) refuses flow mappings, so a rate is written as `value:`, `date:` and `source:` on their own lines, not `{value: ..., date: ..., source: ...}`. A source is `owner` or an https URL without spaces, commas, semicolons or brackets, so the change entry can be read back.
- **Limits are plain numbers in UU** with no date or source, as in the units.yaml above; rates carry both. A change to a limit is dated by its change entry (KNOWN-LIMITS 123).
- **The `credits` reading** needs `credits_per_run` (a count the owner declares) next to `credit_micros`, because umwayi reads no credit count from Kiro. `umwayi budget validate` was added to list every units.yaml problem with its line.
- **Start step 1** (the logbook is writable and its chain intact) is the ledger read with `read_checked` (the whole-file hash and the chain) and the checked append of every entry after it, not a separate `check_writable` call. A separate call would have hit the five layer 10 tests that plant a crash in `check_writable` to reach the watcher before the start. The order of the other steps is as above; the canary of a Claude Code ACP chat is prepared after the gate checks and before the budget steps.
- **left_today_uu** is the smallest of what is left under per_day, per_agent_per_day and per_platform_per_day, before this reservation.
- **A run counts on the day of its reservation**, also when it is settled after midnight.
- **The receiver** also answers 400 (not JSON, or not the OTLP shape) and 415 (not `application/json`, or compressed). Any refusal after the run header matched (400, 411, 413, 415) marks the run invalid, because part of its cost would be missing; a refusal before it (401, 404) is only counted. An invalid report stops the run within a second (exit 2) and settles the full reservation; one found only after the agent ended turns an exit 0 into 2.
- **cost_usd** (a double) is read when an `api_request` event has no `cost_usd_micros`; an event with neither is invalid.
- **No negative cost on any path** (found in the owner's review of PR 33): a negative whole number in `asDouble`, `asInt`, `cost_usd` or `cost_usd_micros` is invalid like a negative double (400, the run stopped with exit 2, the full reservation settled), so no report can subtract from a run. Before the fix a negative cost was accepted on the `asDouble` and `cost_usd` paths, and its negative settle then made the ledger malformed, so every later start was refused.
- **The grace** after the agent is stopped lasts while a report is still being received, at most 6 s (TELEMETRY_GRACE). Once the agent's processes are gone no new export can start, so it does not wait the full 6 s (KNOWN-LIMITS 118).
- **The telemetry names are not in CHILD_ENV_SET.** That set goes to every Claude Code ACP program, so the gate checks would also have exported telemetry; the names are added to the agent's own start only, and the allow-list tests now expect them there (KNOWN-LIMITS 126). `claude_env()` removes every `OTEL_*`, `BETA_TRACING_ENDPOINT`, `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA` and `CLAUDE_CODE_ENABLE_TELEMETRY` for every Claude Code program, the gate checks included.
- **The one network import.** `umwayi/telemetry.py` imports `http.server` inside the function that starts a receiver; the network guards of tests/test_system.py and tests/test_automation.py allow exactly that import (KNOWN-LIMITS 125).
- **settle-lost** takes the run lock (3 while a run holds it) and settles each lost reservation as unknown at `unknown_worst_case` (KNOWN-LIMITS 121).
- **Budget entries are chained once the chain is started.** umwayi does not refuse a start on an unchained logbook (KNOWN-LIMITS 114).
- **A start prints one more line**, `Budget: run R settled, TAG U UU (M micros).`, or that the settle could not be logged (then the reservation counts in full until settle-lost, and an exit 0 becomes 2).
- **B.10, umwayi's part:** `UMWAYI_TELEMETRY_CAPTURE=/absolute/new/file` makes the receiver also write the shape of every accepted report (names and value types, never a value) to a new file with mode 0600. An existing or relative path starts nothing (exit 2).
- **The layer 10 tests** get a `budget_check` Yes rule from `write_rules` (tests/agents/support.py) and, in four tests that start one agent more than three times, roomy limits in units.yaml.

### Facts (read Nov 9 2026)

From [Claude Code, Monitoring](https://code.claude.com/docs/en/monitoring-usage):
- **Telemetry is on** with `CLAUDE_CODE_ENABLE_TELEMETRY=1`, and is exported with `OTEL_METRICS_EXPORTER` and `OTEL_LOGS_EXPORTER` set to `otlp`.
- **`OTEL_EXPORTER_OTLP_PROTOCOL`** has no default and accepts `grpc`, `http/json` or `http/protobuf`. For the HTTP protocols each request carries a `Content-Length`.
- **Intervals:** `OTEL_METRIC_EXPORT_INTERVAL` defaults to 60000 ms; `OTEL_LOGS_EXPORT_INTERVAL` defaults to 5000 ms. `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE` defaults to `delta`.
- **Endpoints and headers:** `OTEL_EXPORTER_OTLP_HEADERS` takes `name=value` headers. Per-signal endpoint and protocol variables override the generic ones, and per-signal headers merge with them.
- **Metrics:** `claude_code.cost.usage` (USD) and `claude_code.token.usage` (tokens), with a `type` attribute of `input`, `output`, `cacheRead` or `cacheCreation`, and `model`.
- **The `claude_code.api_request` event** (`event.name` `api_request`) carries `model`, `cost_usd` ("Estimated cost in USD"), `cost_usd_micros` ("Estimated cost in millionths of a US dollar, emitted as an integer"), `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `duration_ms` and `request_id`.
- **"Cost metrics are approximations."**
- **Content gates:** `OTEL_LOG_USER_PROMPTS` is off by default. `OTEL_LOG_ASSISTANT_RESPONSES` falls back to `OTEL_LOG_USER_PROMPTS` when unset. `OTEL_LOG_TOOL_DETAILS` and `OTEL_LOG_RAW_API_BODIES` add tool arguments and whole request bodies. Traces need `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA` and `OTEL_TRACES_EXPORTER`.
- **Managed settings can lock the OTLP destination** and then remove developer-set telemetry variables. On such a machine umwayi's receiver gets nothing, which is the unknown case.

Not confirmed until B.10: the exact OTLP JSON nesting Claude Code emits (`resourceMetrics` and `resourceLogs`, attribute value shapes), and whether metrics arrive before a short run exits.

### Files

```
units.yaml               the owner's rates and limits (validated like agents.yaml, line numbers, exit 64)
umwayi/units.py          units.yaml, micros and UU, readings and tags
umwayi/budget.py         reserve, settle, release, limits, status; reads the ledger from the logbook
umwayi/telemetry.py      the one-run OTLP/HTTP JSON receiver (http.server, threading)
umwayi/agents.py         the reservation step, the telemetry environment, the mid-run check, settle on every way out
umwayi/cli.py            umwayi budget status, umwayi budget calibrate
```

### units.yaml

```yaml
version: 1
platforms:
  claude-code:
    reading: usd_micros            # measured, from telemetry
    fallback: tokens               # if events carry tokens but no cost
  kiro:
    reading: runs
    run_micros: {value: 400000, date: 2026-11-09, source: owner}
models:                            # micros per million tokens, by type
  claude-sonnet-5:
    input:          {value: 3000000,  date: 2026-11-09, source: https://...}
    output:         {value: 15000000, date: 2026-11-09, source: https://...}
    cache_read:     {value: 300000,   date: 2026-11-09, source: https://...}
    cache_creation: {value: 3750000,  date: 2026-11-09, source: https://...}
limits:                            # UU
  per_run: 100
  per_day: 500
  per_agent_per_day: 300
  per_platform_per_day: 400
  unknown_worst_case: 100
```

- Whole numbers only, no floats; values from 0 to 10^12.
- Every rate has `value`, `date` (a real date, not in the future) and `source` (an https URL or `owner`).
- An unknown platform, model or type is a reading of `unknown`, not an error at run time.
- A missing `units.yaml` means every reading is unknown, under the placeholder limits.

**Change detection:** the settle entry of every run records the SHA-256 of `units.yaml`. Before a reservation, if the file's hash differs from the newest recorded one, umwayi first writes one entry "units.yaml changed", listing each rate or limit that changed with its old value, new value, date and source (names and numbers only). If that entry cannot be written, nothing starts (exit 2).

### The ledger in the logbook

Three entry kinds, source `umwayi budget`, each one line per field, chained:

| entry | Added (fixed format) |
| --- | --- |
| reserve | `Reserved run R for agent A (P): 1000000 micros (100 UU)` |
| settle | `Settled run R for agent A (P): measured 123456 micros (13 UU); models m1, m2; tokens input I, output O, cache_read CR, cache_creation CC; requests N; released 876544 micros` |
| change | `units.yaml changed: limits.per_day 500 to 600; ...` |

- Model names are kept only when they match `[A-Za-z0-9._:/-]{1,64}`, otherwise `other`.
- The run id is `secrets.token_hex(8)`.
- `budget.py` parses only entries with source `umwayi budget` and these fixed shapes. Anything else with that source is a logbook problem, refused like a broken chain.
- A reservation with no settle (umwayi was SIGKILLed) counts as fully settled at the reserved amount, tagged `unknown`, until the owner runs `umwayi budget settle-lost --by NAME` (B-Q4).

### Start steps

Kill switch (3), rules `agent_run`, run lock (3), gate checks (2), then the new steps, then the start entry and the start:

1. **Logbook writable and chain intact** (2): `check_writable`, as today.
2. **units.yaml** valid (64), with any change logged first (2 if it cannot be).
3. **The reservation:** used + reserved today + per_run must fit per_day, per_agent_per_day and per_platform_per_day. Otherwise exit 3, one entry "Refused agent A: the budget limit LIMIT has N UU left, a run needs M UU", and nothing is started.
4. **`budget_check`** in the rules (Yes on; No 2; Ask me first 3 and one queue item, once).
5. **The reserve entry,** then the start entry, then the start.

### Telemetry (Claude Code only)

- `telemetry.Receiver(secret, caps)` is a `ThreadingHTTPServer(("127.0.0.1", 0), Handler)` in a daemon thread, started before the agent and stopped after the stop of the agent (on every way out, in the same `ExitStack` as the canary folder).
- **The handler checks, in order:**
  - the peer is loopback;
  - the path is one of the two;
  - `x-umwayi-run` equals the secret (`hmac.compare_digest`);
  - `Content-Length` is present and at most 1 MB;
  - the run total is at most 16 MB;
  - the content type is JSON.
  
  Only then does it read the body, `json.loads` it, walk only the named paths and fold the numbers into a `Totals` object (integers; `cost_usd_micros` summed; requests counted by event). It answers 200 with `{}` and drops the body.
- Rejections are counted by reason, never logged with content.
- **Numbers:** an integer from 0 to 10^12, or for `claude_code.cost.usage` a non-negative finite double converted to micros rounded up. Anything else marks the run `invalid`, which settles the full reservation.
- **Which source counts:**
  - the `api_request` events (integers) are the measured reading;
  - if no event arrived but `claude_code.cost.usage` did, the metric is the reading (still measured);
  - if only token counts arrived, the declared rates of `units.yaml` give a declared reading;
  - nothing at all is unknown, at the worst case.
- **Environment:**
  - `claude_env()` removes the owner's `OTEL_*`, `BETA_TRACING_ENDPOINT` and `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA`, then adds `TELEMETRY_ENV(port, secret)`;
  - `child_env()` adds the same set for ACP;
  - the names go into `CHILD_ENV_SET`'s tests and the 10.R11.9 allow-list tests.
- **During the run:** the watcher (`_tick`) also checks `Totals.micros_so_far`. Above the per-run cap, it stops the agent like the timeout, exit 3: "Agent A was stopped: it passed its budget of 100 UU for one run".
- **After the run:** a 6 s grace (more than one export interval) for the last export before the receiver stops, then the settle entry. Any way out settles: normal end, refusal after the reservation, the kill switch, the timeout, SIGTERM, a crash.

### Other platforms

- Kiro, and OpenCode later, have no telemetry umwayi reads. Their reading is whatever `units.yaml` declares (`runs`, or `credits` when the owner can enter a count), otherwise unknown at the worst case.
- `budget status` shows the share that was unknown, so the owner sees how much of the number is a guess.

### status and calibrate

- **`umwayi budget status [--date D]`:** one line per limit, `used U UU, reserved R UU, left L UU`, then `measured X%, declared Y%, unknown Z%` of used. It reads only. Exit 0, or 2 when the logbook or units.yaml cannot be read.
- **`umwayi budget calibrate`:** prints, when at least 20 measured runs over at least 7 days exist, the proposed `per_run = ceil(1.5 * p95)` and `per_day = ceil(2 * median day)`, with the run count, the days and the percentile values. It changes nothing (B-Q3). Fewer runs: it says how many more are needed.

### Exit codes

- 0: done.
- 2: logbook or chain broken, units.yaml change not loggable, rules No, invalid telemetry stop.
- 3: a limit (before or during), Ask me first, the kill switch, the run lock.
- 64: units.yaml invalid.
- Never 1.

### Open questions (governor, answered Nov 9: all as proposed)

- **B-Q1. The ledger.** Read it from chained logbook entries only (proposed: one source of truth, already tamper evident), or keep a separate `.umwayi/ledger.jsonl` for speed?
- **B-Q2. Unknown at the worst case.** 100 UU per unknown run, so a day allows at most 4 unknown Kiro runs under the 400 per-platform placeholder (proposed), or a lower declared `run_micros` for Kiro from the start?
- **B-Q3. Who applies a calibration.** `calibrate` only proposes and the owner edits `units.yaml`, whose change is then logged (proposed), or `calibrate --apply --by NAME`?
- **B-Q4. A lost settle.** A reservation without a settle (SIGKILL) stays counted at the full reservation until `umwayi budget settle-lost --by NAME` (proposed), or it is released after a day?
- **B-Q5. Forged reports.** The run secret is in the agent's environment, so a tool call could send its own report. A report only adds to the total, but a forged small report could turn an unknown run into a measured cheap one. Accept and say so in KNOWN-LIMITS (proposed), or treat a run with any report from an unexpected `service.name` as invalid?
- **B-Q6. A cli chat.** The cap and the receiver also cover the terminal chat (proposed), where a long chat can reach the cap and be stopped mid-conversation; or only `agent run` and the ACP chat?

### Risks (governor)

| risk | what happens | what we do |
| --- | --- | --- |
| managed settings pin the OTLP destination | no report reaches umwayi | unknown at the worst case; status shows the share |
| the export interval loses the last report | a short run looks unknown or low | 6 s grace; unknown is never zero; B.10 checks it |
| `cost_usd` is an estimate | UU differs from a real bill | the unit is defined as estimated list price; said in status and KNOWN-LIMITS |
| placeholder limits are wrong | needless refusals or too much room | calibration after 20 runs and 7 days |
| the agent forges a report | an unknown run looks measured | B-Q5; KNOWN-LIMITS |
| the logbook grows with three entries per run | slower appends | linear and small; C-Q2 |

## Whole-system test and security scan (approved Nov 10, tasks.md S.0; built Nov 10 to Nov 12)

Requirements S.R1 to S.R10. Tasks S.0 to S.2.7. The documentation layout (tasks.md D.1) is built first, so S.1 and S.2 write their docs into `docs/` (`testing.md`, `security.md`, `SECURITY-SCAN.md`), not the README. Approved by the owner on Nov 10 with S-Q1 to S-Q16 all as proposed (answers below the questions). No code, no test and no scan was run for this spec.

### Facts (read Nov 10 2026)

- **npm audit** sends a description of the project's dependencies to the configured registry and asks for known vulnerabilities; it needs a `package-lock.json` by default ([npm-audit](https://docs.npmjs.com/cli/v9/commands/npm-audit), [Auditing package dependencies](https://docs.npmjs.com/auditing-package-dependencies-for-security-vulnerabilities)). So it needs the network and tells the registry what the adapter uses. It checks direct, dev, bundled and optional dependencies, not peer dependencies (same page). The npm CLI can also verify the registry signatures of downloaded packages (`npm audit signatures`, [npm-audit man page](https://manpages.ubuntu.com/manpages/noble/man1/npm-audit.1.html)); that needs the packages installed.
- **OSV-Scanner** (Google) extracts packages from a lockfile and matches them against OSV databases. Its offline mode uses previously downloaded local databases and then sends nothing anywhere; `--download-offline-databases` fetches them first ([Offline Mode](https://google.github.io/osv-scanner/usage/offline-mode/), [Usage](https://google.github.io/osv-scanner/usage/)). It is a separate program, not an npm or PyPI package.
- **Bandit** builds an AST of each Python file and runs security plugins against it; it is distributed on PyPI ([bandit on PyPI](https://pypi.org/project/bandit/), [Getting Started](https://bandit.readthedocs.io/en/latest/start.html)). It needs no network once installed and sees only Python source.
- **pip-audit** scans Python environments using the Python Packaging Advisory Database through the PyPI JSON API, or OSV; both need the network ([pip-audit on PyPI](https://pypi.org/p/pip-audit/), [issue 698](https://github.com/pypa/pip-audit/issues/698)). umwayi has no Python dependency, so there is nothing for it to scan except the scan tools themselves.
- **This repo, read Nov 10:** `pyproject.toml` has `dependencies = []`. The only adapter package is `adapters/claude_acp/` (`package.json` pins `@agentclientprotocol/claude-agent-acp` 0.101.0; `package-lock.json` is lockfile version 3 with 115 packages, among them `@anthropic-ai/claude-agent-sdk` 0.3.318 with eight optional platform packages, `express` 5, `hono` 4, `@modelcontextprotocol/sdk`, `zod` and `cross-spawn`). The SDK and its platform packages give their licence as "SEE LICENSE IN README.md" or "LICENSE.md"; every other package names an open licence. The receiver (`umwayi/telemetry.py`) uses `ThreadingHTTPServer` with daemon threads, a 5 s socket timeout per handler (`READ_TIMEOUT`) and no limit on connections (KNOWN-LIMITS 122).
- **This sandbox, Nov 10:** `node` and `npm` are installed; `osv-scanner`, `bandit` and `pip-audit` are not. Network access for an advisory database was not tried.

Not read for this spec: the content of the platform packages (they were not installed), the current advisories for any package, and the Python security release pages (S-Q5 says how they are read in S.2).

### Layout (if approved)

```
tests/test_whole_system.py      S.1: the owner's day and the fault scenarios (S.R2, S.R3)
tests/whole_system_support.py   the root builder, the fakes on PATH, the copy of the day's end state, the sweeps
tests/test_scan_receiver.py     S.R5: the receiver cases with a raw socket client
tests/test_scan_files.py        S.R6, S.R7: modes, links and paths
tests/test_scan_secrets.py      S.R8: the planted secrets and the sweep over every byte written or printed
docs/SECURITY-SCAN.md           S.R9: the recorded scan, its findings and decisions, and S.R10
```

No new file in `umwayi/` unless a test of S.R5 to S.R8 shows a defect (S-Q6, S-Q7); then the fix goes into the module it belongs to, test first.

### Added while building S.1 (PR 36)

- **The snapshot is restored into the same folder.** The day writes absolute paths (the agents' workdir, the Kiro hook file's `--root`, the unit files and their ROOTID, logbook entries), so a copy of the root at another path would not be the day's end state. Each fault test restores the snapshot of the whole temporary folder into the same place first (S-Q2's "its own copy", kept by restoring it).
- **The fault tests share the day.** One class runs `test_01` to `test_08` in order and saves the snapshot; each fault test (`test_20` and later) runs any day step not run yet, then restores the snapshot. A day step that failed skips the rest with its reason.
- **The commands run from the temporary folder,** so a jobs file is given by its absolute path (`umwayi run` reads it from the current folder, as the README's cron line shows).
- **The day's units.yaml has roomy day limits** (the day starts each agent more than three times) and declares Kiro at 40 UU a run, so its shares are measured and declared with nothing unknown.
- **The first start of the day also writes the `units.yaml changed` entry** (B.R1.5), so its entries are checked with that one in place.
- **The morning's anchor still verifies in the evening** (exit 0): a chain longer than its anchor, whose value at the anchor's count matches, is the same chain grown. A shorter chain (the truncated tail) and a different one (the consistent settle edit) give 1. tasks.md S.1.2 is corrected.
- **`schedule remove` with a broken logbook** stops at the rules check, which cannot be logged, before it touches a file (exit 2, both unit files unchanged); 11.R4.2's "put back" is the path where the removal's own entry fails.
- **The lock files are left out of "nothing written by a refusal":** a writer that takes `.umwayi/logbook.lock` or `run.lock` writes its pid there for messages (L-Q1); they hold no state.
- **The kill switch and a scheduled job:** a job checks the kill switch at its start only (KNOWN-LIMITS 129), so the scheduled case is the switch on at the run's start (3, one entry), then off (0).
- **The no-systemd pass** uses a `PATH` of the fakes only (this machine has `/usr/bin/systemctl`), and the second pass puts recording `systemctl`, `systemd-analyze`, `crontab` and `loginctl` first; none was ever called.
- **The defect S.1 found** (S-Q15, fixed in PR 36, test first): a job refused by the gap rule wrote no logbook entry, so a scheduled run refused by it left no trace in the logbook, against KNOWN-LIMITS 98. It now writes one entry (`Job NAME did not run: the gap rule (...)`) and keeps exit 1 (L11-Q9); the entry never counts as a run.

### S.1, the owner's day

- One test class builds the root once (`setUpClass`) and runs the steps of S.R2 in order as real child processes, asserting after each step the exit code, the new logbook entries by source and shape, and the state files. Ordered steps run in one test method each, named `test_01_...` to `test_08_...`, and a failed step skips the rest (they depend on it) with the reason.
- The end state is copied (`shutil.copytree`, links kept as links) once per fault scenario, so each fault starts from the same day.
- The fakes are put first on `PATH` as today (`tests/agents/support.py`); the fake `node` serves the Claude Code ACP chat; the fake `claude` sends the telemetry; the layer 9 hooks are the real scripts.
- The day ends with the checks of S.R1.5, run again after every fault scenario.

### S.1, the fault scenarios

| scenario | how | expected |
| --- | --- | --- |
| tampered: old chained entry | edit one field, rewrite the hash record | `verify` 1, "the Chain value does not match" at that entry; every start, check, job, workflow, schedule install and budget status refused; `kill on` 0 with the "could not be written" line; `schedule remove` 2 with both files back; no byte written by a refusal |
| tampered: budget settle, shape broken | change released only, re-chain, rewrite the record | `verify` 0; every agent start and `budget status` 2 (the ledger shape check) |
| tampered: budget settle, consistent | change micros, UU and released together, re-chain, rewrite the record | `verify` 0, starts go on, `status` shows the edited number (KNOWN-LIMITS 115); only `verify --anchor` with the day's anchor gives 1 |
| tampered: truncated tail | cut the last entries, rewrite the record | `verify` 0; `verify --anchor` 1 "shorter"; starts go on (nothing else can tell) |
| lost reservation | SIGKILL `umwayi agent run` while the fake agent loops; kill its group | `status` counts it in full; a start that no longer fits 3; `settle-lost` 3 while a run holds the lock, then 0; next start 0; `verify` 0 |
| kill switch mid run | `kill on` while each kind of start runs (run, cli chat, ACP chat, for both platforms; a scheduled job from `ExecStart=`) | exit 3 within 1 s plus the 10 s stop grace; nothing left alive; one settle; `kill off`, the next start 0 |
| schedule with no systemd | `PATH` without `systemctl`, `systemd-analyze`, `crontab`; then a fake `systemctl` that records calls | `install` 0, files 0644, the commands printed; `check` 2 (not enabled); no call recorded; `ExecStart=` by hand gives the job's entry; `remove` 0 |
| limit mid chat | ACP chat with `per_run: 1`, the second turn reports 20000 micros | exit 3, "it passed its budget", settled measured |
| crash in umwayi | the planted fault hook (`UMWAYI_FAULT`) in `logbook.append`, `agents._Run._reserve`, the settle, and `schedule.install` after the service file | the next command recovers or refuses as its layer says; no unit file left half; `verify` 0 at the end |

### Added while building S.2 (PR 37)

- **The scan found 10 defects, all fixed test first (S-Q8):**
  1. `rules.yaml` as `/dev/zero` hung `umwayi check`;
  2. `umwayi.json` as `/dev/zero` got umwayi killed;
  3. a hard link at the logbook lock let the holder's pid write reach an outside file;
  4. a link swapped in before the append, or a hard link at `LOGBOOK.md`, was written through;
  5. the intent was not 0600;
  6. a new `queue.md` was 0600;
  7. a too long path was an unexpected error;
  8. the receiver had no whole-request deadline;
  9. the receiver had no cap on threads;
  10. the receiver read only the first of a header given twice and ignored a Transfer-Encoding.

  `docs/SECURITY-SCAN.md` section 5 lists each with its fix.
- **Two readers follow a link on purpose.** `rules.yaml` and `umwayi.json` may be links to a regular file (a dotfiles setup) but must be regular files of at most 1 MB and 64 KB, read with one shared reader (`fsutil.read_regular`: `O_NONBLOCK`, a check of the open file, a bounded read). Every other config file was already refused when it is a link.
- **The append keeps `open(path, "ab")`** with an `opener` that adds `O_NOFOLLOW`, so the crash safety tests that intercept `open` see the same call. A folder in place of `LOGBOOK.md` keeps its old message ("cannot be read").
- **The receiver's 503** is sent from the accepting thread, before any handler thread starts, and counted with the other refusals. A request cut at the deadline before its run header matched is not the agent's report and does not make the run invalid; one cut after it does (S-Q6). The `socket` module is imported in the same function as `http.server`, so importing umwayi still loads no network module.
- **The many-connections test trickles.** 200 idle connections were mostly reset by the kernel (a listen backlog of 5) before the receiver saw them, which hid the missing cap; each held connection now sends a byte a second, so each holds a handler.
- **`npm audit` counts 102 of the 115 as peer packages,** which its docs say it does not check; OSV-Scanner, offline, read all 112, so the result rests on it (KNOWN-LIMITS 131).
- **Python 3.10 is end of life (2026-10-01).** The scan does not change the supported versions; the owner decides (KNOWN-LIMITS 133).
- **The planted faults:** 15, each caught by its scan test (the PR lists them).

### S.2, the tools (proposed, S-Q3, S-Q4, S-Q5)

| target | tool | what it needs | what it cannot see |
| --- | --- | --- | --- |
| umwayi's Python code | Bandit (PyPI), all plugins, in a throwaway virtual environment outside the repo | Python, one `pip install` from PyPI (network once), no network for the scan | anything that is not a known pattern; logic errors; what the code does at run time; the adapters' JavaScript |
| umwayi's own rules | the code guards already in the suite (`test_system.CodeTests`, `test_automation.CodeGuardTests`, `test_agents_gate.CodeGuardTests`), listed in SECURITY-SCAN.md | nothing new | the same as any static check |
| the adapter's npm tree | OSV-Scanner on `adapters/claude_acp/package-lock.json`, offline mode with a database downloaded once | the OSV-Scanner release binary, its checksum checked against the release page; the network once for the database | advisories not in OSV; the contents of prebuilt programs; whether a vulnerable function is reachable |
| the same tree, a second source | `npm audit --package-lock-only` in a copy of the folder | npm and the network; it tells the registry the package list | the same as OSV-Scanner, from GitHub's advisories |
| registry signatures | `npm ci --ignore-scripts` in a throwaway copy, then `npm audit signatures` | npm, the network, about the size of the tree on disk | whether the published files are safe, only that they are the published ones |
| licences | read from `package-lock.json` and each installed `package.json` | the throwaway install above | licence text in a README (the SDK); whether a licence allows the owner's use (the owner decides, S-Q11) |
| Python interpreters | the version of each interpreter (3.10.20, 3.11.15, 3.12.13, 3.13.13 in this sandbox, and the owner's) compared by hand with python.org's security releases | the network to read the pages | vulnerabilities fixed but not yet listed; the owner's distribution patches |

No tool is committed, installed into the repo, or added to `pyproject.toml`, `package.json` or CI. Each command, version and checksum goes into SECURITY-SCAN.md so the owner can run it again.

### S.2, the receiver tests (S.R5)

All through `umwayi agent run` with the fake `claude`, whose `otlp` step gets a raw socket mode for these cases (a test helper, no change to umwayi):

- **binding:** the fake reads `OTEL_EXPORTER_OTLP_ENDPOINT`, then tries the same port on every non-loopback address of the machine and on `::1`; each connect is refused.
- **header:** the seven cases of S.R5.2; only the exact secret gives 200.
- **sizes:** 1 MB exactly (200), 1 MB plus 1 (413, the test checks the body was not read by sending it only after the status line arrives), the 16 MB total, a short body (400 after the 5 s timeout, run invalid), a long body (the extra bytes ignored, the connection closed), `Transfer-Encoding: chunked` without a length (411), `Content-Encoding: gzip` (415).
- **slow client:** headers at one byte every 4 s. Today each `recv` gets its own 5 s timeout, so such a client can hold a handler thread for as long as it keeps sending. Expected after S-Q6: the request is cut at a whole-request deadline (proposed 10 s) and answered 408 or closed; the run is not made invalid by a client that never sent the header (it cannot be the agent's own report).
- **many connections:** 200 sockets opened and held. Today each gets a thread. Expected after S-Q7: at most a fixed number of handlers (proposed 16) at once, the rest closed at once; the agent's own report sent after them still gives 200; the thread count of umwayi read from `/proc/PID/status` stays under the cap plus a margin.
- **closed after:** the port refuses connections after umwayi exits, for a normal end, the kill switch, SIGTERM and a planted crash.

### S.2, modes, links and paths (S.R6, S.R7)

- **modes:** one test runs the owner's day under `umask 022` and once under `077` and lists every path under the root, `$XDG_CONFIG_HOME/systemd/user`, the canary folder and the capture file with its mode. The expected table (S-Q9) is in the test.
- **links:** a table test, one row per file umwayi opens (the logbook, the record, the intent, the lock, `KILL`, the run lock, `queue.md`, the archive index and targets, drafts, the outbox, `rules.yaml`, `agents.yaml`, `units.yaml`, `schedule.yaml`, jobs files, workflows, memory files, the unit folder and files, the capture file): a link to outside the root, a link to `/dev/zero`, a folder, and for writes a hard link to a file outside the root. Each row states the expected answer (refused with its layer's code, or read as allowed, never a write outside the root); a row with no expectation yet is a finding.
- **paths:** each argument of S.R7.2 with each bad shape; the answer is 64 (or the layer's refusal), the message never holds the path's control characters.
- **races:** where umwayi opens with `O_NOFOLLOW` or `O_EXCL` (the unit files, `KILL`, the capture file), a test swaps the file for a link between a planted pause and the open; elsewhere the race is listed in KNOWN-LIMITS.

### S.2, secrets (S.R8)

- A fixed list of planted secrets, each a unique word (for example `S2-SECRET-PROMPT`, `S2-SECRET-ENV-ANTHROPIC_API_KEY`), set in every entry place of S.R8.1 during the owner's day and every fault scenario.
- The sweep reads every byte of S.R8.2 and fails on any planted word, any run header secret (read from the fake's record of its environment) and any canary token, with the file and line (never the text around it).
- The allowed places are a short list in the test, each with the layer that allows it.

### Results and the freeze

- `docs/SECURITY-SCAN.md` (S-Q12) has the sections of S.R9.1, one table per target, and S.R10 word for word.
- A finding is High or Critical (the tool's own rating), or Medium and reachable from umwayi's own use, or any defect a test of S.R5 to S.R8 shows: it is fixed in S.2 (test first) or the owner accepts it in KNOWN-LIMITS (S-Q8). Everything else is listed with its decision.
- A dependency fix means a new pin of the adapter, which is a layer 10 change: the owner approves it, and its gate check (the pinned version in `agents.py`, `package.json` and the lockfile) changes in the same PR.

### Failure table

| what goes wrong | what happens |
| --- | --- |
| a step of the owner's day fails | the later steps are skipped with the reason; the test fails |
| a fault scenario leaves a process alive | the test kills it and fails |
| a scan tool cannot be installed or has no network | SECURITY-SCAN.md says "not run" with the reason; S.2 is not ticked (S.R9.2) |
| two advisory sources disagree | both are listed; the stricter one decides |
| a planted secret is found | the test fails with the file and line; it is fixed before S.2 is ticked |
| a receiver case shows a defect | the defect is fixed test first, or written into KNOWN-LIMITS if the owner decides so |

### KNOWN-LIMITS (written with S.2.7: items 130 to 137; S.1 wrote 129)

At least: S.R10 items 1 to 6 in short; the advisory scan was true on its date only; `npm audit` tells the registry the package list; the receiver cases that stay limits after S-Q6 and S-Q7; every link or path race left open by S.R7.3.

### Hours and schedule effect

| task | hours |
| --- | --- |
| S.1.1 support: root builder, copies, sweeps | 2 |
| S.1.2 the owner's day | 3 |
| S.1.3 fault scenarios: tampered logbook, lost reservation, crashes | 2.5 |
| S.1.4 fault scenarios: kill switch mid run (six kinds), no systemd, limit mid chat | 2.5 |
| S.2.1 receiver tests | 2.5 |
| S.2.2 receiver fixes, if S-Q6 and S-Q7 say so | 2 |
| S.2.3 modes, links, paths | 3 |
| S.2.4 secrets sweep | 2 |
| S.2.5 static and dependency scans, run and recorded | 2.5 |
| S.2.6 interpreters and licences | 1 |
| S.2.7 SECURITY-SCAN.md and security.md under docs/, KNOWN-LIMITS, the README link, mutation checks, the full suite | 2 |
| **total** | **25** |

That is about three working days: Nov 10 to Nov 12 (S-Q16, moved up by the owner from Nov 23 to Nov 26). The web interface follows it with its own spec; README, demo and Devpost, the freeze Nov 29 to Dec 2 and the submission on Dec 3 do not move.

### Risks

| risk | what happens | what we do |
| --- | --- | --- |
| the whole-system test is slow | the suite takes much longer than about 14 min per Python | one day of state copied for the faults instead of rebuilt; the mid-run cases share one wait; measure and report the time (S-Q1) |
| the test is flaky under load | a timing case fails now and then | every wait is for an event with a generous timeout, never a short sleep, as in the layer 10 tests |
| the scan needs the network and the sandbox has none | S.2.5 cannot finish | recorded as not run; the owner runs the listed commands (S-Q4) |
| an advisory hits the pinned adapter | the ACP chat for Claude Code is affected | a new pin is a layer 10 change with the owner's approval, or the chat is turned off until then |
| a fix to the receiver changes its behaviour | the governor tests change | the fix comes with its tests first and the full suite on 3.10 to 3.13 |
| the scan is taken as proof | the owner trusts more than was shown | S.R10 in SECURITY-SCAN.md, KNOWN-LIMITS and the PR |

### Open questions for the owner (S.1 and S.2, answered Nov 10: all as proposed)

1. **S-Q1. Where S.1 runs.** In the normal suite, so CI runs it on every pull request (proposed; about 5 to 8 more minutes per Python, measured in S.1.4). Or a separate command that only runs before a release?
2. **S-Q2. One root or many.** One ordered owner's day, then each fault in its own copy of the day's end state (proposed). Or every scenario from an empty root (slower, but no step depends on another)?
3. **S-Q3. The static scan of umwayi's code.** Bandit with all plugins, from a throwaway virtual environment, plus the existing code guards (proposed). Or also Semgrep (more rules, but its rule registry needs the network and an account for some rules)?
4. **S-Q4. The dependency scan.** OSV-Scanner offline (one database download) as the main tool, and `npm audit --package-lock-only` as a second source, accepting that it sends the package list to the registry (proposed). Or OSV-Scanner only, so nothing about the tree leaves the machine?
5. **S-Q5. The interpreters.** Compare each Python version by hand with python.org's security releases and record it (proposed). Or leave the interpreter to the owner's operating system and only record the versions?
6. **S-Q6. A slow client.** Add a whole-request deadline of 10 s to the receiver and close a request that passes it, without making the run invalid unless the run header had matched (proposed; a change to `telemetry.py` with its tests). Or record it as a known limit?
7. **S-Q7. Many connections.** Cap the receiver at 16 handlers at once and close the rest at once (proposed). Or record it as a known limit next to item 122?
8. **S-Q8. What blocks the freeze.** High or Critical, Medium and reachable, and every defect a test shows, must be fixed or accepted by the owner in KNOWN-LIMITS before Nov 29 (proposed). Or only High and Critical?
9. **S-Q9. File modes.** The canary folder 0700, the capture file 0600, the intent 0600 while it holds an entry, the unit files 0644, everything else the owner's umask (proposed). Or 0600 and 0700 for everything under `.umwayi/`?
10. **S-Q10. The same-user boundary.** State it plainly and test nothing against it (proposed: every layer runs as the owner, and only a sandbox, deferred by L11-Q13, could change that). Or add tests that show which same-user attacks the chain and the anchor make visible?
11. **S-Q11. Licences.** List every licence and point out the SDK's "SEE LICENSE IN README.md" for the owner to read, with no decision by umwayi (proposed). Or treat any package without an open licence as a finding that blocks?
12. **S-Q12. Where the results go.** `docs/SECURITY-SCAN.md` in the repo, dated, without anything secret (proposed). Or only in the pull request body?
13. **S-Q13. CI.** Leave the CI workflow as it is for Dec 3; the scan is run by hand and recorded (proposed: CI would need third party actions and the network). Or add a scan job now?
14. **S-Q14. The owner's real runs.** Not part of S.1; 10.21 (a real run of each platform), 10.31, 11.6 and B.10 stay open as the owner's checks, and SECURITY-SCAN.md lists them as not done (proposed). Or make one of them a condition for ticking S.1?
15. **S-Q15. Fixes found by S.1.** A defect S.1 finds in any layer is fixed in the S.1 pull request, test first, and named in it (proposed). Or a separate fix pull request per defect?
16. **S-Q16. When.** Build right after approval, one pull request for S.1 and one for S.2 (proposed, about 25 hours). Or keep Nov 23 to Nov 26, or one pull request for both?

Answers (owner, Nov 10): S-Q1 to S-Q16 as proposed. S.1 and S.2 are built right after PR 34 merges, Nov 10 to Nov 12, in two pull requests (S.1 first); the web interface follows the scan, with its own spec first; README, demo and Devpost stay Nov 23 to Nov 28.

## Layer 12: Web interface, the view (spec approved Nov 10; the look changed by the owner on Nov 11, UI-Q12 to UI-Q16; tiers, the public site and the scene additions on Nov 11, round 2, UI-Q17 to UI-Q22)

Requirements 12.R1 to 12.R20. Tasks UI.0 to UI.5. Facts with links, and the owner's interface check: `adapters/NOTES-layer12.md`. It was a non goal until Nov 10; the owner moved it into scope before Dec 3. Layer 12 changes the core in one place only: the read only command `umwayi view snapshot` (`umwayi/view.py`). Everything else is in `ui/`, outside the package. The order is UI.1 (the static world: the highlands scene, the stations, the layout, the home content), UI.2 (the snapshot command), UI.3 (the page reads it and feeds the position function), UI.4 (the owner checks panel), UI.5 (polish, docs, the scan, the owner's check).

### The owner's references, and what changed on Nov 11

The first reference was a screenshot and a design document of a 3D shepherd hillside (three.js, eleven stations on podiums in a ring round a lantern). UI.1 was built from it (PR 39) and the owner reviewed it on Nov 11 and **asked for a different look** (UI-Q12 to UI-Q16): real life instead of a stylised game scene; the Kenyan highlands at dusk; stations that are natural features, not podiums; a scattered layout, not a circle; and the scene as the hero of the home page.

**Kept** (they were not the problem): the engine (the ease out tween, following, the on demand loop, settings, the pose player and its time limits), Calm mode, reduced motion, the build, the Content-Security-Policy, `build.json`, the list view and its fallback, the panel, the text contrast test, the sheep and dog shapes, and every test of those.

**Dropped** (the owner can ask for any back):
- the ring of eleven evenly spaced podiums with their rim lights, the ring layout code, the label declutter code and their tests;
- the always visible name pills, the signpost, the amber arcs in the sky, the row of lamp posts;
- the stylised look: a flat dark meadow, a ridge of one dark colour, round blob trees.

| in the first scene | in the highlands scene | why |
| --- | --- | --- |
| a flat dark meadow with faint contour lines | relief: rolling hills with real height, a river valley cut into them, rock | UI-Q12, UI-Q13 |
| a generic dusk sky and a brown ridge | a sky with soft cloud and a warm glow low in the west, long shadows, haze, and **Mount Kenya** on the horizon | UI-Q13 |
| blob trees | umbrella thorn acacia and African pencil cedar, grass in dry gold and green, rock | UI-Q13 |
| a lamp post at the centre | a **hanging lantern on a shepherd's staff**, a plain silhouette shepherd and a dog; the brightest point | UI-Q13 |
| 11 podiums on a circle | 11 natural features scattered on hillsides, the valley and the river bank; distance by how closely each works with the shepherd | UI-Q13, UI-Q14 |
| sky arcs to dependent stations | trails of light along the ground, for the selected, hovered or focused station only | UI-Q14 |
| fixed positions | positions from a function of needs (closer when it needs the owner now); UI.3 feeds the numbers | UI-Q15 |
| a scene on a page with two buttons | the hero of the home page: title, promise, status strip, install and first commands with Copy, links | UI-Q16 |

### What changed on Nov 11, round 2 (UI-Q17 to UI-Q22)

The owner reviewed the reworked scene on PR 39 and answered UI-Q17 to UI-Q22 the same day. PR 39 stays open; it carries step 1 below.

| before | now | answer |
| --- | --- | --- |
| one page; a List view button | three tiers (List, Standard, High) chosen by a device query in the browser, with a visible switch; the list is tier 1 | UI-Q17 |
| one static page for visitors and the owner | two parts: a public site in `site/` (Next.js on the Vercel free tier, server rendered home text, no analytics) and the owner's live view, the static page of `ui/` | UI-Q18, UI-Q19 |
| the scene code only in the page | one scene module in `ui/` used by both | UI-Q19 |
| the home content below a full screen scene | the top of the status strip shows at the bottom of the first screen, with a still cue | UI-Q20 |
| outer stations within about 25 m | at least three stations at 30 m or more | UI-Q20 |
| trails only for the station in focus; a faint river | every trail drawn faintly at rest; a long reach of the river in the overview | UI-Q20 |
| the Rules name over the promise on a phone | no name over the hero text | UI-Q20 |
| low poly rocks and walls | displaced rocks with strata, walls of separate stones, ground with stones and tufts | UI-Q20 |
| a few trees | a dense forest across the river | UI-Q21 |
| still water | rapids over rocks, foam, moving highlights; still with reduced motion and in Calm mode | UI-Q21 |
| a plain silhouette shepherd | a Maasai silhouette in a shuka with the staff, beads only as shape | UI-Q21 |
| simple sheep | a mixed flock of sheep and goats and a herding dog with real proportions; wildlife at the edge in High only | UI-Q21 |
| hours cut to fit a window | the owner keeps the timeline; no scope is cut; no question about hours | UI-Q22 |

**The order of the work (UI-Q22)**, one pull request each:
1. **UI.1b, in PR 39**: the Standard tier fixes, the home page layout, the scene additions at Standard detail, and the tier choice function (tests first). The live view uses the function with a highest tier of Standard, so the switch offers List and Standard.
2. **UI.6**: the shared scene module and the Next.js site serving List and Standard, with the device query.
3. **UI.7**: tier 3, High.

I read "the scene additions, all tiers" as part of step 1 at Standard detail, because the live view is the Standard look and step 2 should only move code into a module, not change the picture. Wildlife is High only, so it is in step 3.

**My choices where the brief leaves room, the calmer one each time:**
- The water is still in Calm mode as well as with reduced motion. It also stops while the scene is off screen or the page is hidden, and it draws at most 30 frames a second while it flows.
- High is chosen by itself only when the network is known to be fast. Safari and Firefox do not offer the Network Information API, so they get Standard and the switch offers High.
- The switch keeps a choice only in the address fragment, never in storage, so 12.R2.2 holds.
- The owner's four cuts of Nov 11 stand, except that the realism of rocks, walls and ground (part of the second realism pass) comes back because the owner asks for it now.

### The tier choice (12.R16)

`ui/src/engine/tier.js`, pure, no browser call inside:

```
chooseTier(env, { maxTier = 3, local = false, requested = null }) -> { tier, reason, warn }
env = { webgl, cores, memory, connection: { effectiveType, downlink, saveData } | null,
        renderer, screen: { w, h }, reducedMotion }
```

In order:
1. no WebGL: List (`reason: "no-webgl"`), whatever was requested.
2. a requested tier (from `#tier=`) is used, capped by `maxTier`; `warn` is set when it is above the automatic choice.
3. Save-Data on, or an effective type of `slow-2g` or `2g` (ignored when `local`): List.
4. High when `maxTier` is 3 and all of: not `local`; a connection is known with effective type `4g` and downlink at least 10; cores at least 8; memory at least 8 when reported; the renderer is known and not software (`SwiftShader`, `llvmpipe`, `softpipe`, `Software`, `Microsoft Basic Render`); the shorter screen side at least 720; no reduced motion.
5. Otherwise Standard.

`readEnv()` in `ui/src/engine/env.js` reads the browser into `env` and is the only file that touches `navigator`; it never sends or stores what it reads. The detail mode (`chooseDetail`) still picks high or low detail inside Standard.

### The public site (12.R17), built in UI.6

```
site/
  package.json package-lock.json (exact versions: next, react, react-dom), next.config.mjs, README.md
  app/layout.js app/page.js     server components: home text, status strip (sample), install and first commands, links, the tier 1 list
  app/scene.js                  a client component: reads the env, calls chooseTier, imports the shared scene for Standard or High
  public/high/                  tier 3 assets (UI.7), each listed in NOTES with source and licence
```

- The page is static at build time (no server code runs per request), so the free tier is enough and nothing per visitor is computed on the server.
- Headers in `next.config.mjs`: `Content-Security-Policy: default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'` (Next.js inline scripts get a hash or nonce, settled in UI.6), `Referrer-Policy: no-referrer`, `Permissions-Policy` with everything off but clipboard write, `X-Content-Type-Options: nosniff`.
- No `@vercel/analytics`, no `@vercel/speed-insights`, no `next/font/google`, no `next/script` from a remote host; a test in the Python suite reads `site/package.json`, the lockfile and the source and fails on any of them.
- **A known limit, stated:** the site's host sees which files a browser asks for, so its request logs can tell which tier was loaded. That is a property of serving files, not tracking; nothing else about the device is sent.

### The shared scene module (12.R18), built in UI.6

`ui/src/scene.js` exports `createScene(canvas, { tier, detail, settings, onSelect })` and returns `{ select, overview, setNeeds, setCalm, setReducedMotion, dispose }`. `ui/src/app.js` (the live view) and `site/app/scene.js` both call it. The live view's build bundles it into the one file as now; the site imports it through a relative path set in `next.config.mjs`. A Python test checks that `site/` has no copy of any file of `ui/src/`.

### The scene additions (12.R20), how they are made

- **Forest**: a band of instanced trees on the far bank, 30 to 90 m from the lantern behind the river, several hundred trees in Standard: pencil cedars (tall narrow cones of layered foliage) and broadleaf trees (clustered crowns), with a darker understorey and ground under them. The river leaves the forest through a gap, so it cuts through it. Kept clear of every station footprint.
- **Water**: the river surface carries a flow direction along the centre line; the shader moves two layers of noise along it at different speeds for the highlights, and foam gathers around rocks placed in the bed and where the bed drops (rapids). One time uniform drives it; with reduced motion, in Calm mode, off screen or hidden, the time stops and the loop asks for no frame.
- **The Maasai shepherd**: a tall, slim standing figure; a shuka wrapped over one shoulder and falling to below the knee (deep red, in shadow at dusk); a beaded collar as a flat disc at the neck; the staff in one hand with the lantern; no face detail. Made from smooth shapes, not boxes.
- **Animals**: sheep of the kinds kept in Kenya (the Red Maasai with a red brown coat, the Dorper with a white body and a black head), goats (lean, horns, an upright tail, mixed colours) and a herding dog with real proportions (a long muzzle, ears, a tail). Each is a few smooth shapes with a coat grain, posed still; they move only as part of a station's action.
- **Rocks, walls, ground**: rocks from a subdivided sphere displaced by noise and flattened, with strata; a wall from many separate stones of different size laid in courses with a capping row; the ground near each station gets small stones and tufts.

### Layout of the files

```
umwayi/view.py              umwayi view snapshot (UI.2): gather the counts, render, write, one logbook entry
umwayi/cli.py               the view subcommand
tests/test_view.py          the snapshot, real child processes (UI.2)
tests/test_ui_package.py    package.json, lockfile, .gitignore, build.json, the built page, its size and addresses
ui/
  package.json package-lock.json README.md .gitignore build.mjs
  src/
    index.html style.css main.js app.js
    engine/                 ease, follow, motion, loop, settings, poses, rig (camera), stage (renderer), detail (the detail mode), placement (moves the stations), tier (the tier choice), env (reads the device hints)
    world/                  noise.js, river.js, height.js (the ground), layout.js (the fixed table and the position function), sky.js (sky, cloud, Mount Kenya), terrain.js, water.js, plants.js (grass, acacia, cedar), rocks.js, lantern.js (lantern, staff, shepherd, dog), trails.js, palette.js
    stations/               meta.js (the words), kit.js (shared parts: sheep, dog, rock, wood, wall, gate), one module per station, index.js
    data/                   sample.js, counts.js, home.js (the status strip, install and first commands, links; UI.3 adds the snapshot mapping)
    ui/                     labels.js (the buttons over the features), panel.js, fallback.js (the list view), home.js (Copy, status strip)
  test/                     node --test
  dist/index.html dist/build.json
```

`ui/` imports nothing from `umwayi/` and `umwayi/` nothing from `ui/`. From UI.6 the public site lives in `site/` and imports the scene from `ui/src/scene.js`; it imports nothing from `umwayi/`.

### The place

The scene is a river valley in the Laikipia and Mount Kenya highlands at dusk, seen from a slope on the south west. One function, `heightAt(x, z)` (metres, the same for the ground, the plants and the stations), gives:
- a wide **valley floor** at about 0 m with a gentle roll of under half a metre, the lantern on a low **knoll** of 1.2 m, and the bowl round the lantern kept level to about 17 m;
- the **river** cut 1.6 m below the floor along a smoothed curve, 6 m wide, with banks that slope up over 3 m; the water surface sits at -0.4 m and does not flow;
- **hills** that rise away from the valley (from about 14 m off the river and 17 m off the lantern), broad swells with a few sharp ridges, higher on the left, reaching 35 to 60 m;
- the Archive's rock face, which is a big rock mass built with the station on the left hillside.

Mount Kenya stands at the far back, a little right of straight behind the lantern, drawn as a silhouette of two sharp peaks (Batian, Nelion) and a lower shoulder, with snow on the upper slopes that holds the last pink light, about 6 degrees above the horizon so it shows between the hills and the sky. Facts and sources: `adapters/NOTES-layer12.md`.

The light is a low warm glow from the west behind the left hills, just after sunset: a dim warm directional light with long shadows, a blue sky fill from above, haze that lifts and softens the distance, and the lantern as the only strong point light. The sky has a warm band at the horizon, a deep blue top, a few soft clouds made once from noise and never drifting, and a few faint stars.

### The layout: scattered, by how closely each works with the shepherd

The lantern is the origin (0, 0), x to the right and z towards the viewer. Each station has a default distance `d0` and a bearing (degrees from the viewer's direction, towards +x), fixed here, in `ui/src/world/layout.js` and in the layout test. The order of the distances is the order of how closely each works with the shepherd: the AI helpers walk with him; he consults the rules, the kill switch and the queue all the time; the logbook is written beside him; memory, workflows and the budget are tended now and then; the adapters and the scheduled runs work at the river's edge; the archive is far, a place he goes to rarely.

| station | feature | ground | `d0` m | bearing | footprint m | default position (x, z) |
| --- | --- | --- | --- | --- | --- | --- |
| AI helpers | sheepdog and herd | valley floor, by the lantern | 4.8 | 24 | 2.6 | (1.95, 4.4) |
| Kill switch | lone gate and latch | low rise, back right | 9.0 | 140 | 2.4 | (5.8, -6.9) |
| Rules | drystone wall with gates | gentle slope, left front | 9.6 | -42 | 3.9 | (-6.4, 7.1) |
| Queue | sheepfold | valley floor, right | 10.5 | 78 | 3.7 | (10.3, 2.2) |
| Logbook | standing stone | knoll, back left | 12.6 | -120 | 2.4 | (-10.9, -6.3) |
| Memory | spring pool | hollow at the foot of the front hill | 15.4 | -8 | 2.8 | (-2.1, 15.3) |
| Workflows | stream through connected pools | left hillside, with a feeder stream | 15.5 | -88 | 3.6 | (-15.5, 0.5) |
| Budget | rain water tank | right front, on the slope | 16.0 | 52 | 2.3 | (12.6, 9.9) |
| Adapters | ford and bridge | the river, right | 20.5 | on the river | 3.6 | (19.0, -7.8) |
| Automation | river with a water wheel | the river, left | 22.5 | on the river | 3.6 | (-11.0, -20.1) |
| Archive | cave in a rock face | steep left hillside | 24.0 | -112 | 4.2 | (-22.3, -9.0) |

The river runs from the back left, behind the lantern, to the front right. Its centre line passes through the control points (-110, -36), (-80, -32), (-52, -30), (-34, -29), (-20, -24), (-8, -19), (4, -16), (14, -12), (22, -4), (27, 8), (36, 18), (52, 24), (80, 36), (110, 44), smoothed once (Catmull-Rom). Its nearest point to the lantern is about 16.5 m away, at (4.9, -15.7). The river stations stand on the river's centre line, because the wheel and the ford span the water. The default gap between any two features (centre distance minus both footprints) is 2.0 m at the least, which a test checks. Free stations stand where the ground is not steeper than their feature allows (the Archive's hillside is the steepest, 0.65); a test checks the slope under each station at the defaults and at 300 random need sets.

### The position function (12.R14): built now, UI.3 feeds numbers

```
stationPositions(needs) -> { id: { x, z, y } }      needs: { id: 0..1 }, a missing or bad value is 0.4
```

1. For a free station: `d = d0 * (1.2 - 0.5 * need)` along its bearing from the lantern. For a river station: a position along the river centre line, `d` measured the same way but kept on the bank on its own side of the nearest point (Automation to the left, Adapters to the right); `need` slides it towards the nearest point and away from it.
2. `d` is never less than `shepherdSpace + footprint` (2.0 m plus the footprint), so nothing stands on the lantern.
3. **No overlap**: every pair is kept at least `footprintA + footprintB + 0.8 m` apart. The stations are placed one by one, the closest to the shepherd first; one that would overlap a station already placed slides outward along its own bearing (a river station along the river) on a fixed grid of a tenth of a metre until it is clear. The same needs always give the same positions. (Built this way because it cannot fail to end; pushing pairs apart for a number of rounds, the first idea, could.)
4. `y` is `heightAt(x, z)`.
5. `createPlacement({ stations, motion })` holds the current positions and has `setNeeds(needs)`: it eases every station from where it is to its new place (`Motion`, ease out, 2400 ms, 1.6 times in Calm, a jump with reduced motion), cancels a move in progress and starts from where the stations are. At rest nothing moves. UI.3 maps the snapshot to needs (below) and calls `setNeeds`; it changes nothing else.
6. Proposed needs from a snapshot (UI.3 to confirm): Queue `min(1, open / 6)`; Kill switch 1 when on or unknown, else 0; Budget the share by which today's use is above the average of the other six days, 1 once it is above 1.5 times that average; Rules, Logbook, Automation, Archive, Memory, Workflows, AI helpers and Adapters 0.4 (the default) until the snapshot has a number for them. A bad number is 0.4.

### The stations: natural features, poses, moves and counts

A station is an ordered list of poses and the short ease out moves between them (unchanged). A click plays the moves of the selected station once and stops on the last pose, then eases back to rest when it is left. Reduced motion shows the poses one at a time. The count drives the numbers of the first pose.

| station | what you see | poses (still frames) | count from the snapshot |
| --- | --- | --- | --- |
| Memory | a small spring pool ringed with mossy stones; flat pebbles at the edge | the pool low; the pool full and still, a ring of light on the water; a flat stone laid over the pebbles (private paths stay out) | none |
| Rules | a drystone wall along the slope with a gate in it, a sheep at the gate and a hanging lamp on the gate post; small lamps on the wall top | Yes (gate open, lamp mint, sheep through), No (gate shut, lamp red, sheep turned back), Ask me first (gate half open, lamp amber, sheep waits) | `rules`: lamps on the wall top by verdict |
| Queue | a round sheepfold of drystone with one gap; sheep waiting in line outside; a cairn | the line; the front sheep at the gap with the hurdle lifted; the hurdle down and the line moved up | `queue.open`: sheep; `queue.answered`: stones in the cairn |
| Archive | a dark cave mouth in a rock face, a flat stone slab at the foot, a small cairn | the tablet at the slab; the tablet lifted towards the cave; the tablet inside, a stone with a seal added to the cairn, a flag at the slab | none |
| Logbook | a tall standing stone with rings cut into its top and a helix of small beads round it | chain intact; one bead added; one bead altered and the rest dark, a seal ring sweeps up | `logbook.chain_length`: beads, `entries` in the panel |
| Automation | the river with a timber water wheel (no sluice: cut on Nov 11) | the wheel at three angles (morning, noon, evening); spokes lit for the schedules | `schedule`: spokes lit for entries, installed and enabled |
| AI helpers | a sheepdog beside a small herd, a row of white stones, a flat stone | the dog with the draft; the dog stopped at the white stones; the draft on the flat stone (you publish) | none |
| Workflows | a stream down the hillside through three rock pools joined by short cascades (four was cut on Nov 11), a sheep on stepping stones | the first pool lit; the middle pool lit; a token at the last pool (approve) | none |
| Adapters | a stone ford with stepping stones and a plank foot bridge over the river, one gate post on the bank (the rope line was cut on Nov 11) | a pulse from the ford, then from the bridge, into the post; the last caption says any stdin and stdout tool can reach it too | none |
| Kill switch | a lone gate in an open field and a latch post with a red lamp | the gate open; a sheep passes; the gate shut, the lamp lit red, the next sheep halts | `kill_switch`: shut and lit for on or unknown |
| Budget | a corrugated iron rain water tank on a timber stand with a sight tube; seven notches on the stand | the tube low; today's mark; at the limit | `budget.days`: the seven notches, the level at the last |

Red, mint and amber mean something only at Rules, Kill switch and Logbook. Counts the snapshot does not hold are not shown; the panel says so. The panel shows: the name, built or planned, two short lines, the command, the counts with the date; Budget also says that B.10 is not done; Rules says that unknown is drawn as Ask me first.

### The scene, the look and the motion engine

- **First realism pass only** (the owner cut the second pass on Nov 11): no more work on cloud shapes, snow detail, rock strata or a third kind of plant. The cloud, the snow and the strata that the first pass has stay as they are.
- **Everything is generated.** The ground is a mesh of the height function with a shader that blends dry gold grass, green grass, red soil, gravel and rock by height, slope and noise, and adds fine relief with a derivative bump made from noise (no texture). Rock is displaced icospheres with layered strata. Wood has grain from stretched noise. Wool, iron and water have their own simple shaders. Grass is thousands of instanced blades in the gold and green of red oat grass; acacia is a thin trunk with a flat, wide, layered crown; cedar is a dark narrow cone of layered tiers. Plants stand only where the ground and distance allow, and never inside a station's footprint at any place the station can reach.
- **Light and air:** one dim warm directional light with a shadow map over the stations, a blue hemisphere fill, a warm point light in the lantern, fog tinted to the sky at the horizon, filmic tone mapping, a bloom that only the lantern and a few lit parts reach.
- **Water** is a shader surface: dark, with the sky reflected by a Fresnel curve, a soft warm streak where the sky glows, and a little noise. It does not flow. A station's pool and the river are drawn the same way.
- **Nothing moves by itself**: no wind, no flow, no cloud drift. Motion is only the tweens (12.R5.3).
- **Hover and focus** ease a small warm light up on the feature and show its name above it; both ease away. With reduced motion they switch at once.
- **Trails of light** for the selected, hovered or focused station: for each station it works with (the `deps` of meta.js), a row of about 30 small soft lights following the ground between the two features, fading in over 600 ms. Hidden in Calm mode and drawn at once (no fade) with reduced motion.
- **No free running frame loop, one ease out, no repeating timer** (unchanged), Calm mode (lower glow, bloom, light and haze contrast, slower moves, no trails), reduced motion (jumps, poses by hand).
- **Camera.** The overview is low enough to show the horizon and Mount Kenya and wide enough to show every station at every default position and at the nearest and furthest they can reach. Selecting flies to the lantern side of the station, the station in the left third (the top third on a phone). Arrow keys move between stations, Esc returns, drag orbits within limits.
- **The detail mode** (12.R12.3): `chooseDetail(env)` picks high or low at start from the renderer name (software rendering is low), the processor core count (4 or fewer is low), the memory hint (4 GB or less is low) and `#detail=`; `stepDown()` goes one step lower after 24 slow frames: pixel ratio down to 1, then bloom and multisampling off. **Two steps, not three: the owner cut the last step (no shadows and fewer plants) on Nov 11.** Low detail starts at the second step. The choice and the steps are pure functions with Node tests.
- **Palette:** dusk colours from the scene (warm gold, red soil, olive, cool blue shadow, slate sky, the lantern's amber) and the UI tokens of the nightwatch palette (base `#0E1310`, ink `#EEE8DB` for text only, amber, mint, red, glass).

### The home page (12.R15)

**Since Nov 11, round 2:** the top bar has the tier switch (List, Standard, and High on the public site) instead of List view; the hero is the first screen less a peek, so the top of the status strip and a still "More below" cue show at the bottom of the first screen at 1440 by 900 and 390 by 844; no name pill is placed over the hero text. One page. Top to bottom: the top bar (a small wordmark, List view, Calm mode); the **hero**, the scene filling the first screen, with the title "umwayi-os" and the promise "An AI operating system for one person. Your rules come before every AI helper acts, and every change is written down." over the sky at the left; below it, scrolling normally:

1. **Status strip**: four items, each `name`, value, and the word "sample" (or the date of the snapshot once UI.3 loads one): *Kill switch* off, *Budget used today* a number of UU, *Queue open* a count, *Logbook* a chain length. Items are text, so they read without the scene.
2. **Install and first commands**: a short block of text for each step with a Copy button: `git clone https://github.com/Miguel-Shinyenyi/umwayi-os.git`, `cd umwayi-os`, `pip install -e .`, then `umwayi memory bundle`, `umwayi queue add --kind task "Write the spec"`, `umwayi check '{"type": "payment", "amount": 5}'` (it answers No), `umwayi logbook verify`. The Copy button writes to the clipboard on its click only (`navigator.clipboard.writeText`); where that is not allowed it selects the text and says "Press Ctrl+C". The button says "Copied" for a moment, with no motion.
3. **Links**: Repo, Docs (the repo's docs folder), Devpost and Demo video. The last two are text with "link to come" and are not links until the owner supplies the addresses (one line in `home.js` each).
4. A footer line: "A sample world." until UI.2 and UI.3 are built; after that it says how to load your own snapshot.

The scene and the home content share the page's Calm mode and the 4.5 to 1 contrast. The canvas lives in the hero and scrolls away with it; nothing is drawn while it is off screen. The panel and the pose buttons stay in the hero. A vertical swipe over the scene scrolls the page; a horizontal drag orbits.

### `umwayi view snapshot`

- **Where each count comes from.** The snapshot reuses each layer's own reader and parses none of those files itself: `logbook.read_checked` for the tamper check and the entries, the chain state for `chain_length`, the queue reader of layer 3, the rules reader of layer 2, `budget.read_ledger` and `budget.day_totals` for each day, `kill.state`, and the same read as `schedule.check`. A reader that raises gives `null` for its part (an unexpected error in the command itself still exits 2).
- **Order.** Arguments (64), the tamper check (1), gather, render, write the file, the logbook entry (undo the file and exit 2 if it fails). No run lock: the command starts no run. No rules question and no kill switch check: it is not an action of an AI helper, and the owner needs it while the switch is on. A helper that runs it through a tool still passes the layer 9 `tool_bash` check.
- **The entry** (shape like the other layers): `Source: umwayi view snapshot`, `Added: Wrote a snapshot of counts to FILE (SHA-256 HEX)`, `Checked: the logbook chain was intact before the write`, `Not done: no text, path or secret of any file is in the snapshot; the page was not opened`. FILE is the name inside the root.
- **Types.** The structural test accepts these leaf types only: whole numbers from 0 to 1000000000, booleans, `null`, the words `on`, `off`, `unknown`, and dates `YYYY-MM-DD`. A string of any other shape fails the test, which is stronger than searching for known sentinel words.
- **Size.** About 600 bytes. The page rejects a file over 4 KB.
- **The page's reader.** `FileReader.readAsText` on the picked file, `JSON.parse`, then the strict validator of 12.R9.1 (exact key set per `schema`, types, ranges). Only `schema: 1` is known. A file that fails shows one message and changes nothing.

### The owner checks panel

- The data is `ui/src/data/checks.js`: for each check an id, a title, the reason it is open, the NOTES file and heading it comes from, and its steps (text, an optional command, what to record). The six checks and their sources:

  | id | check | source |
  | --- | --- | --- |
  | 10.21 | one real run of each platform | `adapters/NOTES-layer10.md`: A3 to A5 for Claude Code, C4 for Kiro |
  | 10.31 | the first real Claude Code ACP chat, the real Kiro login | `adapters/NOTES-layer10.md`: 0, A and C of "The owner's first real run (10.31)" |
  | 11.6 | the real systemd check | `adapters/NOTES-layer11.md`: "The owner's real check (11.6)" |
  | B.10 | the capture of one real telemetry export | `adapters/NOTES-layer10.md`: "Budget governor: Claude Code telemetry (B.10, the owner's capture)" and tasks.md B.10 |
  | 10.37 | the real `auth status --json` field names | `adapters/NOTES-layer10.md`: B1 to B3 |
  | UI | the interface check | `adapters/NOTES-layer12.md`: "The owner's interface check (UI.5)" |

  tasks.md folds 10.37 into the 10.31 run (they share section B of the NOTES). The panel lists 10.37 as its own check so its result is recorded once, and 10.31 points to it for section B.
- A test (Python, standard library) reads `ui/src/data/checks.js` as text, takes every command of a step and finds it word for word in the NOTES file named for that check. A command changed in NOTES and not in the page, or the reverse, fails the suite. Prose is not compared.
- **State.** A plain object in memory: `{checkId: {stepIndex: {ticked, result}}}`. Nothing is written to any storage (12.R2.2, and the static test of 12.R10.3).
- **Export.** One function builds the text from the state: for each check its id and name, then each step as `[x]` or `[ ]`, its text and the typed result, and the last line "These are your notes. umwayi did not run or verify anything." A check with every step ticked is listed as "ticked by you", otherwise "not done". The text goes into a read only `<textarea>`. Copy uses `navigator.clipboard` when it exists and otherwise selects the text. Download clicks an `<a download>` whose address holds the text (a data address, built in UI.4 instead of a Blob, because the page tests forbid `createObjectURL`) after the owner's click; it was checked under the page's Content-Security-Policy, and where a browser cannot save a file the panel says Copy only.
- **The value warning.** A result is marked when it contains `@`, `://`, a run of 24 or more letters and digits, or a long hex string. It is a hint, never a block.

### A liberal society view, for later (nothing of layer 13 is built)

Layer 13 has no requirements, design or tasks in this repo. What follows is from the three things the owner named (review dates, reopened decisions, petitions) and must be checked again against the layer 13 spec when it exists (UI-Q11).

- **Stations, when layer 13 exists.** They would stand as a second small group on the lower slope, by the path from the Queue station, because they are about decisions the queue holds:
  - *Review*: a boundary stone with date notches; how many reviews are due, how many are late, and the days until the next. Light only, amber for due, never red.
  - *Reopened*: a gate that was shut and stands open again beside its shut twin; how many decisions were reopened.
  - *Petitions*: a notice board at the edge of the pasture with letters pinned; how many are open and how many answered.
- **Snapshot schema 2** would add one section per station, counts and day numbers only: `review: {"due": N, "late": N, "next_in_days": N or null}`, `reopened: {"count": N}`, `petitions: {"open": N, "answered": N}`. Never a title, a name, the text of a petition or a reason. A schema 1 page refuses schema 2, and a schema 2 page accepts schema 1 and shows no layer 13 station.
- **Not drawn until built.** Before layer 13 is built there is no ghost, no label and no list entry for them, so nothing planned is shown as built. A station has the state `planned` in the code (the dashed style and "planned" in the label), used only if the owner later asks for a planned station to be drawn.
- **Built now for this, and nothing more:** the station list in one file, the ring layout for any number of stations (tested with 14 fake ones), the schema number in the snapshot and a validator keyed by schema, and the station state field.
- **The same rules hold:** calm, no autoplay, a click plays the moves, reduced motion shows poses, counts only.
- **Risks to settle with the owner then:** a petition is something a person wrote, so even the number of open petitions can say something; whether a due review should ever turn red is a question for the layer 13 spec.

### Tests (12.R10)

- **Snapshot:** `tests/test_view.py`, listed in 12.R10.1. All of it real child processes, with the planted sentinel words and the structural leaf test.
- **Package and page:** `tests/test_ui_package.py`, 12.R10.2 and 12.R10.3. The allowed addresses are a short named list: the XML namespace name three.js carries (`http://www.w3.org/1999/xhtml`) and the home links (the repo, its docs folder); anything else fails. The page is also checked for its size (under 2 MB). This is a static check, so UI.5's browser pass also blocks every request and counts the attempts, which must be zero.
- **`build.json`:** the test recomputes the SHA-256 of every source and compares. A changed source with no rebuild, or an edited page, fails, with no npm in the test.
- **Node:** `ui/test/*.test.mjs` with `node --test`, written before the code they test where the task says so: the layout table and the position function (defaults equal the table, no overlap at any reachable need, monotone in need, deterministic, river stations on the river, slope), the placement moves (3 s, 5 s in Calm, a jump with reduced motion, a new set of needs mid move), the detail mode (the choice and the steps), the home content (status strip, copy lines equal the commands, placeholders marked), and the unchanged engine, station and contrast tests.
- **Browser:** by hand, in a headless browser outside the repo (12.R10.5), in high and in low detail.
- **CI:** the CI workflow runs only the Python suite today (UI-Q10).
- **Planted faults and mutation checks:** the list in 12.R10.6 plus: the need clamp removed, the slide outward removed, a station placed on the lantern, a name visible at rest, a clipboard write on page load, a placeholder link made a real address, a sample value without the word sample, the detail step skipped.

### KNOWN-LIMITS (written with UI.5, numbered from 138)

- The page cannot run a command, answer the queue or change anything. That is the design, not a defect.
- The snapshot is only as fresh as the last `umwayi view snapshot`. The page shows its date and does not poll.
- A broken logbook gives no snapshot (exit 1), so the page cannot draw a broken chain (UI-Q6).
- A snapshot file can be forged or edited by anyone who can write the file. The page validates its shape, not its truth. The logbook chain and `umwayi logbook verify` are the check.
- The page is checked in one or two browsers by hand. The Python suite cannot run it.
- The built page is about 0.5 to 1 MB and is a generated file in the repo, kept honest by `build.json` and not by a rebuild in CI (until UI-Q10).
- The owner's notes in the checks panel are lost when the page closes.
- The npm tree (three, esbuild and its platform binary) is outside the S.2 scan until the scan is run again on `ui/package-lock.json` (UI.5).
- A browser that ignores `prefers-reduced-motion` shows the click motion.
- The lower detail mode has two steps. A machine that cannot draw the page at the second step still sees the list view and the home content, but not a lighter picture (the owner cut the third step on Nov 11).
- The picture is a first realism pass: simple cloud shapes, simple snow, one kind of rock strata and two kinds of tree (the owner cut the second pass on Nov 11).

### Hours and schedule effect

Re-estimated on Nov 11 for the highlands rework, honestly, then cut by the owner the same day. The first scene took about 16 hours of work for what it was; the new brief is a different order of work: real relief, a valley, Mount Kenya, plants, rock, water and light made from code, eleven stations that are each a natural feature, a layout and a position function, trails, a detail mode, and a home page.

| task | hours before the cuts | hours now |
| --- | --- | --- |
| UI.0 spec | 5 (done) | 5 (done) |
| UI.0b the Nov 11 spec change | 3 | 3 |
| UI.1 the static world, as the highlands scene | 56 | 42 |
| UI.2 `umwayi view snapshot` | 9 | 9 |
| UI.3 the page reads the snapshot and feeds the position function | 8 | 8 |
| UI.4 the owner checks panel | 6 | 6 |
| UI.5 polish, docs, the scan of `ui/`, the owner's interface check | 10 (and 1 of the owner's) | 7 (and 1 of the owner's) |

Before the cuts: about 92 hours still to do (97 with UI.0). **After the cuts: about 75 hours still to do (80 with UI.0), plus 1 of the owner's.** The window is Nov 11 to Nov 22, about 12 days; at 5 to 6 hours a day that is 60 to 72 hours. README, demo and Devpost stay Nov 23 to Nov 28, the freeze Nov 29 to Dec 2 and submit Dec 3.

**The owner's decision (Nov 11): all four proposed cuts are accepted, and nothing else is cut.**
1. **The second realism pass** (6 h of UI.1) is cut: no more work on soft cloud shapes, snow detail, rock strata detail or a third kind of plant. The first pass stays: the relief, the light, the haze, the river, the acacia, the cedar, the grass and the rock.
2. **Station detail** (6 h of UI.1) is cut: the Adapters feature keeps the ford and one bridge, not three crossings; the Workflows stream has three pools, not four; the Automation wheel has no sluice.
3. **The low detail mode's last step** (2 h of UI.1.10) is cut: the mode has two steps (a lower pixel ratio, then no bloom and no multisampling), not three. A very weak machine gets no further relief; this is a known limit.
4. **UI.5 extras** (3 h) are cut: the contrast check of the glass panel over every part of the sky, and the second device pass.

**Round 2 (Nov 11, UI-Q22): the owner keeps the timeline. No scope is cut and no question about hours is asked.** The estimates below are for planning only: UI.1b about 30 h, UI.6 about 24 h, UI.7 about 30 h.

**UI.4, the owner checks panel, is not cut** (6 h), and **the drift of UI.3 is not fixed to the default numbers** (the position function is fed real numbers from the snapshot). Both stay in scope. **No further cut is made unless the owner agrees.** What is left is about 75 hours against 60 to 72, which is 3 to 15 hours over the window. That gap is stated, not hidden: if it shows by Nov 17, I ask the owner what to do rather than cut on my own.

### Risks (layer 12)

| risk | what happens | what we do |
| --- | --- | --- |
| a count leaks text | a title or path appears in the page or the file | the structural leaf test, sentinel words, and a view module that reads through the layers' readers only |
| the page makes a request | the no network rule is broken | the static test, the zero attempt browser pass, no `fetch` in the source, no file loader bundled, and a Content-Security-Policy tag with `default-src 'none'`; links are anchors and nothing is prefetched |
| the real life look is heavy | a weak machine stutters or fails | the detail mode (start low from what it can tell, step down twice on slow frames), draw only on demand, a pixel ratio cap, the list view; a machine too weak for the low step still has the list view |
| the real life look is bright or busy | it stops being calm | luminance and white area limits kept, nothing moves by itself, trails only for the station in focus, no labels at rest |
| realism from code is not a photograph | the owner expects more than it can give | said plainly in the PR with screenshots; there is only a first pass (the second was cut), so what the owner sees is what is built |
| the page is large | over 2 MB | a size test; all realism is generated, nothing embedded |
| stations overlap or hide when they move | a feature is lost | the position function pushes apart, tested for thousands of random needs and the extremes |
| a station on the river cannot move like the others | it jumps or leaves the bank | river stations slide along the river; tested to stay on the bank |
| names only on hover | a visitor cannot find the features | a short hint, real buttons for the keyboard and screen readers, the list view, and the panel on a click |
| a Copy button reads or writes without a click | a surprise | it writes only in its click handler; a test fails a clipboard call anywhere else |
| a placeholder link looks real | a visitor clicks nothing | placeholders are text marked "link to come" and are not anchors |
| the built page differs from its source | the reviewed code is not the shipped code | `build.json` checked in the suite; the owner rebuilds with a pinned lockfile |
| an npm package is hijacked or runs a script | the owner's machine runs foreign code | exact versions, a lockfile with sha512, `npm ci --ignore-scripts`, esbuild's binary from its platform package, the S.2 scan repeated on `ui/` |
| a planned thing looks built | the owner is misled | a station has a state; Budget is built and B.10 is said in words; nothing of layer 13 is drawn |
| a checks panel result reads as proof | the owner trusts the page for a test it cannot run | "not done" until every step is ticked, "ticked by you" and never "passed", and the closing line of the export |
| WebGL missing or slow | a blank page | the list view and the home content work without it; the detail mode steps down |
| the public site leaks device facts | a visitor is tracked | the hints are read in the browser only; no analytics, cookie or storage; the only signal is which files are asked for, stated as a known limit |
| flowing water breaks calm | the scene feels busy or uses power at rest | slow drift, no flashing; still with reduced motion, in Calm mode, off screen and hidden; at most 30 frames a second |
| a Maasai figure becomes a costume | disrespect | a plain silhouette, beads only as shape, no face detail, no exaggeration; the owner reviews the screenshot |
| High assets are heavy or fail | a long blank page | Standard draws first; High replaces it when ready and falls back on any failure |
| the scene code is copied into the site | two versions drift | one module, a test that finds no copy |
| the snapshot is stale | the page shows yesterday | the date next to the scene and the status strip; KNOWN-LIMITS |

### Open questions for the owner (layer 12)

UI-Q1 to UI-Q22 are answered (UI-Q6 to UI-Q11 accepted as proposed on Nov 10; UI-Q12 to UI-Q16 on Nov 11; UI-Q17 to UI-Q22 on Nov 11, round 2).

1. **UI-Q1. Where the code lives.** `ui/` at the repo root, outside the `umwayi` package; the core stays standard library only (answered).
2. **UI-Q2. The toolchain.** three.js 0.187.0 and esbuild 0.28.2 pinned with a lockfile; the owner runs `npm ci --ignore-scripts`; umwayi never runs npm; the built page is committed and makes no network request (answered).
3. **UI-Q3. The snapshot.** `umwayi view snapshot` is read only and writes one JSON file of counts only (queue open and answered, rules by verdict, logbook entries, chain length, budget used per day, kill switch state, schedule state), no text, no path, no secret; it runs the tamper check, writes one logbook entry and exits 0, 1 or 64 (answered; an unexpected error exits 2 by rule 8).
4. **UI-Q4. How it feels.** Calm by default: nothing flashes or blinks; motion only after a click or cursor move and it eases to rest; no autoplay; `prefers-reduced-motion` switches off all movement and shows still frames; a visible calm mode toggle with lower contrast; dark, low brightness colours and no large pure white areas; cleaner and closer to a recent game than an old video game; less congestion (answered).
5. **UI-Q5. The owner checks panel.** It lists the physical tests (10.21, 10.31, 11.6, B.10 capture, 10.37, the interface check) with steps and a place to tick and type results; results stay in the page and export as text; the interface never writes to the repo, runs a command or calls a network (answered).
6. **UI-Q6. A broken logbook and the snapshot.** The command exits 1 and writes nothing, as UI-Q3 says, so the page can never show a broken chain from a snapshot (proposed: keep it so; the owner sees the refusal in the terminal, and `umwayi logbook verify` says where). Or write a snapshot with `"logbook": {"state": "broken"}` and no logbook entry, so the page can show a red bead (UI-Q3 says one entry, and a broken logbook cannot take one).
7. **UI-Q7. How the page gets the file.** A file picker (and drop) in the page, read with `FileReader` (proposed: no request, no script executed, works from disk). Or `snapshot.js` loaded by a script tag, as in the reference (the file would run as code, and the command would write JavaScript, not JSON).
8. **UI-Q8. The list view and the ring.** A list view of the eleven stations, shown on request and when WebGL fails (proposed). The ring order: neighbours that depend on each other sit next to each other, in the order Memory, Rules, Queue, Archive, Logbook, Automation, AI helpers, Workflows, Adapters, Kill switch, Budget (proposed). Layer 10, the front door, has no station of its own and is told inside Adapters. Or a twelfth station for it.
9. **UI-Q9. Calm mode.** It starts off, and starts on when the system says `prefers-contrast: less` (proposed). Text keeps at least 4.5 to 1 against its background even in calm mode, because lower contrast must not make words unreadable. Or a lower floor for the scene's own labels.
10. **UI-Q10. How the page is checked.** The Python suite checks the package, the lockfile and the built page; `node --test` and the headless browser pass are run by hand and recorded (proposed, like the scan of S.2). Or add a CI job that runs `npm ci --ignore-scripts`, builds, and fails if `ui/dist` differs, which needs `actions/setup-node` and the registry.
11. **UI-Q11. The liberal society view.** The design above is only a sketch (proposed: nothing is built, only the extension points of 12.R8.3, and the sketch is checked again when the layer 13 spec exists). Or the owner describes layer 13 first and this section is rewritten before UI.1.

12. **UI-Q12. The look** (answered Nov 11). Imagery that resembles real life, more detail, not less; photoreal leaning; one self contained page under about 2 MB; no network request; no downloaded images; realism from generated terrain, lighting and textures; an automatic lower detail mode for weak machines.
13. **UI-Q13. The place and the features** (answered Nov 11). The Kenyan highlands at dusk: rolling hills with real height, a river valley, acacia and cedar, grass and rock, Mount Kenya on the horizon, low warm light. A hanging lantern on a shepherd's staff at the centre, with a plain silhouette shepherd and a dog; the brightest point. No podiums, no paths, no label boards: stations are natural features named only on hover or focus (and in the list view). Memory a spring pool; Rules a drystone wall with gates; Queue a sheepfold; Archive a cave in a rock face; Logbook a standing stone with growth rings; Automation a river with a water wheel; AI helpers a sheepdog and herd; Workflows a stream through connected pools; Adapters a ford or bridge over the river; Kill switch a lone gate and latch with a red lamp; Budget a rain water tank with a level.
14. **UI-Q14. The layout and the connections** (answered Nov 11). Not a circle, no even angles: the eleven scattered on different ground (hillsides, the valley, the river bank), some close to the lantern and some far, by how closely each works with the shepherd; default distances fixed in the design with a seeded layout; no overlap; each reachable by keyboard. Streams and trails of light link stations that work together; no drawn paths.
15. **UI-Q15. Distance follows need** (answered Nov 11). With a snapshot (UI.3) a station moves closer to the lantern when it needs the owner now (open queue items, an Ask me first, a budget warning) and drifts out when quiet; slow, eased, ends within 3 seconds, off under reduced motion; the position function is designed now so UI.3 only feeds it numbers.
16. **UI-Q16. The home page** (answered Nov 11). The scene is the hero of the umwayi-os home page. One page, two modes: visitors see the sample world plus home content; loading a snapshot makes it the owner's live view. Home content: title and one line promise; a status strip (kill switch, budget used, queue open, logbook chain, shown as sample until a snapshot is loaded); install and first commands with copy buttons (clipboard write only on a click, no network); links (repo, docs, Devpost, demo video; placeholders marked until the owner supplies the URLs). Links are plain anchors the owner clicks; the page itself still makes no request.

17. **UI-Q17. Three tiers** (answered Nov 11, round 2). Chosen on the public site by querying the device first (cores, device memory, the Network Information API where present, GPU renderer hints, screen size, `prefers-reduced-motion`, Save-Data), with a visible switch so the owner can override. Tier 1, List: for slow networks, no WebGL or no JavaScript; the plain list of the eleven with the full home content. Tier 2, Standard: the current scene, light on data (about 1 to 2 MB), with the fixes of UI-Q20. Tier 3, High: much closer to photorealism, heavier assets, only for fast networks and capable GPUs.
18. **UI-Q18. The public site** (answered Nov 11, round 2). Its own folder `site/`, Next.js with pinned versions and a lockfile, on the Vercel free tier, no analytics, no tracking; device hints are read in the browser and never sent. The server renders the home text, the status strip, the install steps and the links so they show at once and work without JavaScript, and serves the tier that fits; it may fetch its own assets from its own host (the public site only). The 3D draws in the browser from the shared scene code.
19. **UI-Q19. The owner's live view** (answered Nov 11, round 2). It stays the static one file page: no network request, CSP `default-src 'none'`, loaded from disk, the tier 2 look, a snapshot through the file picker. The scene code is one module both use. umwayi never runs npm or node.
20. **UI-Q20. Fixes to tier 2** (answered Nov 11, round 2). The rest of the page visibly present at the bottom of the first screen; the list view is tier 1, not a mode of the page; the outer stations further out, some really far; the river and the trails clearly visible from the default view; the phone overlap fixed; rocks, walls and ground less like low poly forms.
21. **UI-Q21. Scene additions** (answered Nov 11, round 2), in all scene tiers with detail rising by tier: a dense forest across the river, the river cutting through it; water over rocks (rapids, foam, moving highlights, still under reduced motion); a Maasai silhouette shepherd (shuka, staff, beads only as shape, respectful); a mixed flock of sheep and goats and a herding dog that look real; wildlife at the edge in High only (distant birds, an antelope on the ridge, nothing near the stations).
22. **UI-Q22. Schedule** (answered Nov 11, round 2). The owner handles the timelines; no scope is cut; no question about hours. One pull request per step, in order: (1) the tier 2 fixes and the home page layout in PR 39; (2) the shared scene module and the Next.js site with tiers 1 and 2 and the device query; (3) tier 3 High.

All the rules stay: calm by default, nothing flashes, motion only after a click or cursor move, reduced motion with still poses, Calm mode, 4.5 to 1 text contrast, no large white areas, the WebGL fallback list view.

Answers (owner): UI-Q1 to UI-Q5 on Nov 10 as recorded above; UI-Q6 to UI-Q11 accepted as proposed on Nov 10; UI-Q12 to UI-Q16 on Nov 11; UI-Q17 to UI-Q22 on Nov 11, round 2. PR 39 stays open and is reworked on its branch; it is not merged.


## Testing

- Standard library `unittest`, also run by `pytest`.
- Each layer has its own test module, using temporary folders.
- CI (`.github/workflows/ci.yml`) runs `python -m unittest discover -s tests -t .` on every pull request, on Python 3.10, 3.11, 3.12 and 3.13. After PR 9 there were 556 tests; after PR 14 (layer 10 parts 1 and 2) there were 673; after PR 15 (part 3) there were 697; after PR 16 (part 4) there were 719; after PR 17 (part 5) there were 747; after PR 18 (part 6) there are 783.
- `tests/test_system.py` runs the umwayi command as real processes in a fresh folder: one scripted run of every layer, and fault tests (logbook edits, broken rules, bad config, injected crashes in every command, corrupt state files, unknown actions, no network import, no approver code path).
- Mutation checks: for each layer, faults are put into the code on purpose and the tests must fail. PR 9 also showed the system test failing for three faults (no run lock, no kill switch check, check exiting 1 on an error).
- Layer 9 adapters get their own tests and CI job (see above).

## Layer 13: Correction and graded autonomy (spec in the L13.0 pull request, tasks.md L13.0; built only after the owner approves it, slice by slice)

Requirements 13.R1 to 13.R15. Tasks L13.0 to L13.6. Five slices in the owner's order, each shipping alone: Elections (L13.1), Reversal (L13.2), Courts (L13.3), Honest tension (L13.4), Graded autonomy (L13.5), then the whole-system update (L13.6). The owner stops the build where Dec 3 finds us. Layer 13 is added after the "Testing" section on purpose, so that the layer 12 branches (PR 39 and the UI.2 branch), which edit the layer 12 sections, merge without a conflict.

### Owner decisions (Nov 11)

Decided, not open:

1. Build all four correction mechanisms and the graded autonomy score, in this order, and stop where the deadline (Dec 3) finds us. Shape every slice so it ships alone.
2. Elections: a `review_by` date on standing approvals and Yes rules; when it passes the rule falls back to Ask me first; `umwayi rules due` lists them; the fallback is logged.
3. Reversal: a closed decision can be reopened with a reason. Reopening writes a **new** logbook entry that states it is a reopen and links to the old entry by its hash. The old entry is never changed or marked. Each decision records what would change my mind.
4. Courts: a helper can petition against a No; the petition becomes a queue item for the owner; it never changes the verdict by itself; rule changes are logged before use.
5. Honest tension: stop criteria, and a plain note in the docs that no state is perfect. Nothing claims otherwise.
6. Graded autonomy: a score per action class from the owner's record (approved as proposed, edited, rejected, reverted), with a cautious lower bound, reversibility and cost, and owner defined thresholds. It ships with its behaviour, not as a display only, and fails closed. It can move Ask me first to Yes only where a rule explicitly opts that action class in. Low data, irreversible or costly actions, a No, a broken chain, the kill switch on or an unknown state always mean Ask me first. Every move is logged with the score inputs. The score never reads text, only counts. One setting turns it off, and it is off by default.

### Facts (read Nov 11 2026, in the code of main at 5cd03a8)

- `rules.py` has a closed set of rule fields (`_RULE_KEYS`: id, title, text, cause, verdict, matchers). A field outside it makes `rules.yaml` malformed, and every check gives Ask me first. So `review_by` and `autonomy` are unknown fields until slices 1 and 5 add them: **the owner must not write them into `rules.yaml` before the slice is merged.** A rules file that uses them is then read by the new code only.
- `rules.check(action_text, rules_path)` is called without a root by the jobs, the helpers, `publish` and the inner checks of a workflow. `rules.check_and_log(...)` (a root, a date, an entry) is called by `umwayi check`, the agent gates (`agent_run`, `agent_login`, `budget_check`) and the schedule. Elections must therefore live in `check` (every caller), and graded autonomy only in `check_and_log` (13.R10.9).
- `umwayi check` already reads the kill switch on every call (`kill.state(root)`), and the adapters read only `answer`, `rule_id` and `rules_ok` from `--json`. A new key in the JSON does not break an adapter.
- Exit codes today: `UmwayiError` is 1 (a refusal, nothing changed), a crash 2, usage 64, `check` 0, 2 and 3. The layer 13 commands that refuse use 1, like `queue answer` and `view snapshot`.
- The logbook entry has three free lines (Added, Checked, Not done) that must be one line of plain printable text. With the hash chain, an entry's `Chain` value is the SHA-256 of the previous value, a newline and the entry's text, so it names the entry and everything before it. `read_checked` returns entries without their Chain value; `parse` has it (`ParsedEntry.chain`). The queue's `_commit` writes `queue.md` and one entry together or neither. The budget governor's `pending_change` is the model for logging a changed file before use (a SHA-256 and a state summary in the entry).
- The queue has kinds `task` and `decision` and statuses `open`, `answered`, `closed`. Titles, recommendations and answers hold no `|` and no line break, up to 500 characters for the last two. Ids are never reused.
- The example rules of the adapters already refuse a shell command that names `rules.yaml`, `LOGBOOK.md`, `.umwayi` or `umwayi kill` (`cc-no-guard-shell`) and any write to those paths (`cc-no-guard-edits`). Layer 13 extends those lists (13.R14.3).

### Layout

```
umwayi/rules.py          review_by and autonomy fields, the lapse of a Yes rule, the election clock, the verdict order   (L13.1, L13.5)
umwayi/elections.py      due(): the list for `umwayi rules due`, the clock                                              (L13.1)
umwayi/decisions.py      `umwayi decision reopen`; resolves an id or a hash through logbook.read_chained                  (L13.2)
umwayi/rulelog.py        the rules change entry, the last logged rules, the state summary                                (L13.3)
umwayi/petition.py       `umwayi petition`, the limits                                                                  (L13.3)
umwayi/autonomy.py       autonomy.yaml, the inputs reader, the score, the gates, `status`, `validate`, `record`          (L13.5)
umwayi/taskqueue.py      `answer(..., revisit_if=)` and a way to add a row and an entry in one commit                     (L13.2, L13.3)
umwayi/logbook.py        read_chained(root): (Entry, Chain value) pairs under the same checks as read_checked           (L13.2)
umwayi/cli.py            the subcommands: rules due, decision reopen, petition, autonomy status|validate|record
autonomy.example.yaml    the settings with suggested values, enabled: false                                              (L13.5)
tests/test_elections.py  tests/test_reopen.py  tests/test_rulelog.py  tests/test_petition.py  tests/test_honest.py
tests/autonomy/          support.py  test_score.py  test_gates.py  test_inputs.py  test_off.py  test_text_blind.py
docs/corrections.md      docs/autonomy.md
```

`umwayi/view.py` and `ui/` are not changed (13.R15). Each module is standard library only; a code guard test lists the imports of the four new modules.

### The verdict order, with the new steps

`umwayi check` and `check_and_log` today: kill switch (with `--kill-switch`), parse the action, load the rules, match, strongest wins, log. Layer 13 adds steps; a step exists only when its slice is built, and without it the order is the one before.

| step | what | slice | answer if it fails or is unsure |
| --- | --- | --- | --- |
| 1 | the kill switch with `--kill-switch`: on or unknown turns any answer into No | before | No (unchanged) |
| 2 | the action is read: a bad action is Ask me first | before | Ask me first |
| 3 | `rules.yaml` is read; a missing, broken, too big or unknown field file is Ask me first (this now includes a bad `review_by` or `autonomy`) | before, 1, 5 | Ask me first |
| 4 | **the rules change is logged** (`rulelog`): if the bytes differ from the last logged version, one `umwayi rules` entry is written first | 3 | the new rules are used for No and Ask me first only; every Yes becomes Ask me first |
| 5 | the election clock is set: the latest of the system date, `--date` and the newest logbook date | 1 | the system date and `--date`; the logbook write then fails like any other |
| 6 | the matching rules are found; **a Yes rule past its `review_by` counts as an Ask me first rule**, and its id is kept for the entry | 1 | Ask me first for that rule |
| 7 | the strongest wins: No, then Ask me first, then Yes (layer 2, unchanged) | before | |
| 8 | **graded autonomy**: only when the answer is Ask me first and the call is `umwayi check` or a logging caller; the thirteen gates in order; the first that fails leaves Ask me first | 5 | Ask me first |
| 9 | the check's entry is written, with the fallback and the move in their fixed shapes. If it cannot be written: No stays No, a Yes (a move included) becomes Ask me first | before, 1, 5 | as layer 2 |

Notes: step 4 comes before step 6 so a rule is logged before it is used; step 6 comes before step 8 so a lapse is final (a lapsed Yes rule matching means no move); step 8 never runs for a No, for no match, or for a Yes.

### Data shapes

**`rules.yaml`** (slices 1 and 5 add the two fields):

```yaml
rules:
  - id: report-yes
    title: The weekly report job may run
    text: The report job only reads files and writes one draft.
    verdict: yes
    review_by: 2026-12-01            # slice 1: a real date; yes rules, or ask rules with autonomy
    matchers:
      type: run_job
      command: report

  - id: commit-ask
    title: A commit on a feature branch is asked
    text: The owner is asked before an AI helper commits.
    verdict: ask
    review_by: 2027-02-01
    autonomy:                         # slice 5: the opt-in
      class: git-commit
      reversible: true
      cost_uu: 2
    matchers:
      type: tool_bash
      command__contains: git commit
```

**`autonomy.yaml`** (slice 5; every key required; `autonomy.example.yaml` is the copy with `enabled: false`):

```yaml
version: 1
enabled: false          # the one setting; no file, or false, means off
window_days: 90         # outcomes older than this are not counted (1 to 3650)
min_decisions: 30       # n must be at least this (1 to 1000000)
min_lower_bound: 850    # the score in per mille, 1 to 1000
confidence_z: 258       # hundredths: 258 is 2.58, about 99 percent (100 to 400)
revert_weight: 3        # one revert counts as this many failures (1 to 100)
max_cost_uu: 10         # a class declared above this is never moved (0 to 1000000)
cooldown_days: 30       # after a rejected or reverted outcome (1 to 3650)
max_moves_per_day: 5    # moves of one class on one logbook day (1 to 1000)
```

**Logbook entries** (every entry is three lines of plain text; the chain adds the fourth). The readers match the whole line against a fixed pattern. A line that does not match is not read.

| source | slice | `Added` | `Checked` | `Not done` |
| --- | --- | --- | --- | --- |
| `umwayi check` (unchanged parts as today) | 1 | `Rule ID gave Ask me first; action type: T` | today's text, then `; election fallbacks: ID (review_by DATE), ID2 (review_by DATE2)` only when a Yes rule lapsed (at most 10 named, then `and N more`) | unchanged |
| `umwayi check` | 5 | `Rule ID gave Ask me first and autonomy moved it to Yes; action type: T` | today's text, then `; autonomy: moved to Yes; class C; approved A; edited E; rejected R; reverted V; weight W; n N; score S per mille; needs n NMIN and score SMIN; reversible yes; cost U of UMAX UU; moves today K of KMAX`. When it did not move: `; autonomy: no move (GATE)` | unchanged |
| `umwayi rules` | 3 | `rules.yaml changed (sha256 HEX); rules 14 to 15; added a-id; removed b-id; changed c-id verdict no to ask, d-id review_by none to 2026-12-01` or `rules.yaml first logged (sha256 HEX); rules 15` or `...; no rule changed` | `rules.yaml was read and parsed before this entry; this entry is written before the new rules are first used; state: ID verdict[ review_by DATE][ autonomy CLASS]; ...` | `Only rule ids, verdicts, dates and counts are logged, not rule text. No action was checked by this entry.` |
| `umwayi decision reopen` | 2 | `Reopen of entry HEX (Q-0007 answered on 2026-11-05); new decision Q-0012 opened by NAME; reason: TEXT` | `the hash chain was intact before this entry; HEX is a chained entry of source umwayi queue answer for Q-0007; Q-0007 is a decision that is not open; revisit if recorded then: TEXT` | `The old entry, the old row Q-0007 and the rules were not changed or marked. Nothing was decided again.` |
| `umwayi queue answer` (a decision) | 2 | today's text, then `; revisit if: TEXT` | unchanged | unchanged |
| `umwayi petition` | 3 | `Q-0031 (decision) as open: Petition against rule ID by HELPER` | `rule ID exists with verdict No; limits held (open for this helper 1 of 3, open in all 4 of 10, accepted today for this helper 1 of 5, in all 4 of 10); reason N characters` | `The rule, rules.yaml and every answer were not changed. The reason text is in queue.md and not copied here.` |
| `umwayi autonomy record` | 5 | `outcome OUTCOME for class C recorded by NAME` plus `; ref Q-0007` when given | `the hash chain was intact before this entry; the class and the outcome were checked against the allowed words` | `Nothing was moved or changed by this entry. The score is computed when a check runs, not here.` |
| `umwayi autonomy` | 5 | `autonomy.yaml changed (sha256 HEX): KEY OLD to NEW; ...`, or `autonomy.yaml first logged (sha256 HEX)`, or `autonomy.yaml removed` | `autonomy.yaml was read and validated before this entry; this entry is written before the new values are first used` | `Only the setting names and numbers are logged. Nothing was moved by this entry.` |

`NAME` and `HELPER` are plain words without `;`. The first line of each shape starts with a fixed word, so a reader finds it by `fullmatch` and never searches inside free text. The `reason` and `revisit if` texts are the only free text, and each is last on its line.

### Slice 1: Elections

- **Parse.** `review_by` is a string made by the miniyaml reader and checked with `logbook.real_date` (so `2026-2-1`, `2026-13-01`, a number, a list and an empty value are errors). On a `no` rule, on an `ask` rule without `autonomy`, and (until slice 5 exists) on any `ask` rule, it is an error: `rules.yaml` is malformed and every check gives Ask me first. With slice 5 the `ask` plus `autonomy` case is allowed.
- **Clock.** `today = max(system date, --date, newest logbook date)`. The newest logbook date comes from the same read the check does anyway; if the logbook cannot be read the first two are used and the entry write fails, so a Yes cannot come out. `rules.check` takes `today` as an argument (default the system date) so the callers without a root are covered.
- **Lapse.** A Yes rule with `review_by < today` is treated as `ASK` in `decide`, with its id added to `Decision.lapsed`. The strongest wins as before. A Yes rule with `review_by == today` is in force (the last day).
- **Entry and JSON.** `Decision.lapsed` is put in the entry's `Checked` line (shape above) and, only when not empty, in the JSON as `"election_fallbacks": ["id"]`. With none, the JSON and the entry are the same bytes as before.
- **`rules due`.** Reads `rules.yaml` with the same loader, sorts by `review_by` then id, and prints:

  ```
  lapsed  2026-11-01  report-yes  10 days ago
  due     2026-11-20  commit-ask  in 9 days
  far     2030-01-01  old-yes     in 1146 days
  Yes rules without review_by: 5
  ```

  `lapsed` is `review_by < today`; `due` is `today <= review_by <= today + DAYS`; `far` is more than 366 days ahead and is shown instead of `due`. Exit 0, or 3 if a rule lapsed or the rules cannot be read. It writes nothing.
- **Why this shape.** The date is on the rule, not in a second file, so the rule and its expiry cannot drift. The rule is not edited when it lapses, so the file is always what the owner wrote and the fallback is a property of the date.

### Slice 2: Reversal

- **`logbook.read_chained(root)`.** The same checks as `read_checked` (tamper check, format, chain), returning `(Entry, chain value or None)` for every entry. Read only, no lock. Used by `decision reopen`.
- **Resolve.** The closing entries of one decision are the entries with source `umwayi queue answer` or `umwayi queue close` whose `Added` matches `^(Q-\d{4,}) `. The newest one for the id, with a `Chain` value, is *the* old entry. An id argument is resolved to it; a hash argument must equal its `Chain` value. Anything else is refused (13.R4.5).
- **Order of `reopen`.** Arguments (64), the lock, the tamper and chain check (1), `queue.md` parse (1), resolve the old entry (1), the row is a decision that is not open (1), no earlier reopen of this hash with an open row (1), build the new row and the entry, one queue commit (queue.md and the logbook entry; both or neither), print.
- **The new row.** Kind `decision`, status `open`, title `Reopen decision Q-0007`, recommendation `Reopened on DATE by NAME: REASON` (cut to 500 characters, never mid-word). The old row is untouched.
- **Already reopened.** The command scans the chained entries for `Reopen of entry HEX (` with the same HEX and takes the new id from `new decision (Q-\d{4,}) opened`; if that row is still `open` in `queue.md`, it refuses. A reopen of a reopening row is the normal path: the closing entry of the new row is the newest closing entry for that id.
- **`--revisit-if`.** `queue answer` takes it, requires it for a decision, and appends `; revisit if: TEXT` to `Added`. It is validated like an answer (one line, no `|`) up to 200 characters, or the word `none`. The reopen reads it back with `fullmatch` on `^Q-\d{4,} marked answered on \d{4}-\d{2}-\d{2} \(status open to answered, \d+ characters of answer\); revisit if: (.{1,200})$`; no match (an answer from before layer 13) gives `not recorded before layer 13`. An entry that has the text but a different shape is not read.
- **What the old entry keeps.** Nothing in the code path opens the old entry for writing; the logbook is only appended. A test compares the file before and after: the first part is byte for byte the same and the rest is exactly one entry.

### Slice 3: Courts and the rules change log

- **Petition order.** Arguments (64), the lock, tamper and chain check (1), read `rules.yaml` (1 if unreadable), the rule exists and its verdict is `no` (1), the five limits (1), the same open petition (prints `Already open, nothing added`, 0), add the row and write the entry in one queue commit.
- **Counting the limits.** Open petitions are the `queue.md` rows of kind `decision` and status `open` whose title matches `^Petition against rule ([a-z0-9][a-z0-9_-]*) by ([a-z][a-z0-9_-]{0,39})$`. Accepted today are the `umwayi petition` entries of the current logbook date, read with the fixed shapes. A helper cannot beat a limit by a new name for the total limits (10 open, 10 a day); the per helper limits are bounded by the totals.
- **Verdict never changes.** `petition.py` imports `rules` only to read the rule's verdict (through `load_rules`), writes nothing to `rules.yaml` and has no code path that does. A test hashes `rules.yaml` and the answers of a fixed list of actions before and after 200 petitions and after the owner's answers.
- **Rules change log (`rulelog`).** On every `check`, after the rules load: SHA-256 of the exact bytes read; find the newest chained-or-not entry of source `umwayi rules` in the shape above (one read of the logbook, shared with the election clock and, in slice 5, the inputs); if its hash is the same, nothing; otherwise build the diff against its `state:` list, write one entry through the checked append, then go on. Rules with `review_by` or `autonomy` show them in the state (`report-yes yes review_by 2026-12-01`). More than 200 rules: the entry holds the hash and counts and `state: too many rules to list`, and the next change is logged as a baseline. A rules file that fails to parse is not logged (it is not used).
- **If the entry cannot be written** the check goes on with `rules_logged = false`: a Yes becomes Ask me first. This is the same effect as the existing "the logbook cannot be written" case, so nothing new has to be tested for the entry's own check write.
- **Not blocked.** A weakened rule is used at once. The entry says `changed no-money verdict no to yes` in the logbook, dated, in the chain. The owner finds it with `umwayi logbook verify` and by reading the log; a hold-until-accepted design is L13-Q11.

### Slice 4: Honest tension

- **Stop criteria** are written in 13.R8.3 and 13.R8.4 and in a table in `docs/corrections.md`:

  | what | stop criterion | who acts |
  | --- | --- | --- |
  | build of a slice | a failing acceptance test or planted fault, or not merged by Nov 28 | the slice is not merged; it stays "specified, not built" |
  | the layer | the owner says stop, or Dec 3 | slices before it stay |
  | an election | none to stop; a rule without `review_by` never lapses | the owner adds the date |
  | a reopen | none; it is a question, not a change | the owner answers |
  | a petition | the limits of 13.R6.5 | the command refuses |
  | graded autonomy, now | `enabled: false`, or the file removed | the owner, at the next check |
  | graded autonomy, by itself | a rejected or reverted outcome (cooldown), the daily cap, an input that is not intact, the kill switch | the gates |
- **The plain note**, in `docs/corrections.md` and `docs/autonomy.md`, section "No state is perfect": "The owner wants umwayi to correct itself and to be safe. Each way to correct something is also a way to be wrong: a date can be set too far ahead, a reopen can be forgotten, a petition can be a bad idea, a score can be built on careless approvals. umwayi makes each state visible and dated, and falls back to Ask me first when it is not sure. It does not make any state perfect, and nothing in these pages says it does."
- **The words test** (`tests/test_honest.py`): the banned list of 13.R8.2 against `docs/corrections.md`, `docs/autonomy.md`, the `--help` of every layer 13 command, and the captured output and logbook entries of the acceptance tests. The exact sentence of the note is removed before the search; a planted `guaranteed` in a copy of each page is found.
- **KNOWN-LIMITS for layer 13**, as written (updated in the L13.5 pull request to match `docs/KNOWN-LIMITS.md`; it first planned 160 to 170 in one run): 160 `review_by` depends on the owner renewing honestly, and a rule with none never lapses; 161 a clock set far ahead lapses every rule (a safe error) and the election clock never goes back (both L13.1); 162 a reopen links to a hash and needs the chain, entries before the chain cannot be linked; 163 the revisit condition is the owner's words, and nothing watches for it (both written in L13.4); 164 and 165 are not used, because the petition names and the weakened rule they were planned for were written in L13.3 as 192 and 193, after layer 10 had taken 180 to 191 (192 petition limits stop a flood, not a patient helper; 193 the rules change log shows a weakening and does not hold it; 194 only ids, verdicts and review dates are listed; 195 a dry run neither logs a rules change nor falls back); 166 a process of the same user can write well formed, chained score inputs (item 135 again); 167 the score is a statistic of the past and a class that is too wide mixes histories; 168 reversibility and cost are the owner's declaration; 169 careless approving builds a high score; 170 the moves of one day are capped but a wrong move is still a wrong move (166 to 170, L13.5). 171 to 179 are free.

### Slice 5: Graded autonomy

**The inputs.** `autonomy.read_inputs(entries)` takes the output of `logbook.read_checked` plus the chain values and returns counts per `(class, outcome)` and the dates of the rejected and reverted ones, or `INVALID`. It only looks at entries whose source starts with `umwayi autonomy`. Each such entry must have all three lines equal to one of the fixed shapes of the table above (a `fullmatch` on each line), a `Chain` value, and a date not before the chain started. One entry that fails makes the whole result `INVALID`, and then no class is moved (13.R11). It also counts the check entries of the day with the move shape (source `umwayi check`, `Added` matching `^Rule [a-z0-9][a-z0-9_-]* gave Ask me first and autonomy moved it to Yes; action type: [A-Za-z0-9_.:-]{1,40}$`, and the class in `Checked`) to know the moves of the day. No other line of any entry is read: not a queue title, not an answer, not a reason.

A `--ref` is unique per outcome: a second `approved` record for `Q-0007` makes `record` refuse (1), and the reader treats a duplicate it finds as `INVALID`. A `reverted` for a ref needs no earlier `approved` for it: the record is a count, and the owner may revert something a human approved outside the tool.

**The score.** For one class over the window, with the weights of `autonomy.yaml`:

```
s = a                              # approved as proposed
f = e + r + revert_weight * v      # edited, rejected, and each revert counted revert_weight times
n = s + f
z = confidence_z / 100
if n == 0: score = 0
p      = s / n
centre = p + z*z / (2*n)
spread = z * sqrt( p*(1-p)/n + z*z / (4*n*n) )
bound  = (centre - spread) / (1 + z*z / n)
score  = floor(bound * 1000), kept between 0 and 1000
```

It is the lower end of the Wilson score interval for the share of proposals the owner accepted as proposed. It is cautious in two ways: few records give a wide interval and so a low bound, and the confidence z is the owner's (2.58 is about 99 percent). Only `+`, `-`, `*`, `/` and `sqrt` on 64 bit floats are used, in this order, so the result is the same on Python 3.10 to 3.13. The result is rounded down. A revert counts on top of its own approval on purpose: the approval stays a success and the revert adds `revert_weight` failures, which is the cautious side. An edit is a failure of the proposal as proposed (L13-Q7).

**Worked example.** `autonomy.yaml` as above (window 90, min 30, bound 850, z 2.58, weight 3, max cost 10, cooldown 30, 5 moves a day). Rule `commit-ask` opts in the class `git-commit`, reversible, cost 2. Today is 2026-12-01. The owner's record in the window:

| case | a | e | r | v | s | f | n | p | centre | spread | bound | score | gate that stops it | answer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 70 | 3 | 1 | 0 | 70 | 4 | 74 | 0.945946 | 0.990922 | 0.081377 | 0.834482 | 834 | score 834 is below 850 (`low-score`) | Ask me first |
| 2 | 80 | 2 | 0 | 0 | 80 | 2 | 82 | 0.975610 | 1.016198 | 0.059825 | 0.884568 | 884 | none: n 82 at least 30, score at least 850, reversible, cost 2 of 10, no cooldown, 0 of 5 moves today | **Yes** (moved, logged) |
| 3 | 80 | 2 | 0 | 1 (dated 2026-11-30) | 80 | 5 | 85 | 0.941176 | 0.980332 | 0.076607 | 0.838093 | 838 | cooldown until 2026-12-30 (`cooldown`); after it, score 838 is below 850 (`low-score`) | Ask me first |
| 4 | as case 2, but the rule says `reversible: false` | | | | | | | | | | | 884 | `irreversible`, whatever the score | Ask me first |
| 5 | as case 2, but the rule says `cost_uu: 11` | | | | | | | | | | | 884 | `cost` (11 above 10) | Ask me first |
| 6 | 20 | 0 | 0 | 0 | 20 | 0 | 20 | 1.000000 | | | | 750 | `low-data` (n 20 below 30) | Ask me first |

The numbers of cases 1 to 3 are computed with the order above and are test fixtures. In case 2 the move is logged as `Rule commit-ask gave Ask me first and autonomy moved it to Yes; action type: tool_bash` with `class git-commit; approved 80; edited 2; rejected 0; reverted 0; weight 3; n 82; score 884 per mille; needs n 30 and score 850; reversible yes; cost 2 of 10 UU; moves today 1 of 5`. One later revert (case 3) takes the class out for a month and then holds it under the bound, and 100 clean approvals later it would be above the bound again: the owner's record alone moves it.

**The gates, in order.** Each has a fixed word that the entry and `status` print.

| # | gate | word | stays Ask me first when |
| --- | --- | --- | --- |
| 1 | on and valid | `autonomy-off`, `settings-invalid` | no `autonomy.yaml`, `enabled` not true, or the file is invalid |
| 2 | logging | `no-log` | the call is a dry run (`--no-log`) or a caller that does not log |
| 3 | kill switch | `kill-switch` | the state is on or unknown (read on every call, with or without `--kill-switch`) |
| 4 | the record is intact | `chain`, `inputs-invalid` | the logbook cannot be read, fails the tamper check, has no chain, has a broken chain, or one input is out of shape, unchained or duplicate |
| 5 | the rules | `not-opted-in`, `election-lapsed` | there is no matching rule, a matching Ask rule has no opt-in, or a Yes rule lapsed |
| 6 | one class | `class-mismatch` | the matching opt-in rules give different classes |
| 7 | the opt-in's own review | `opt-in-lapsed` | the opt-in rule is past its `review_by` |
| 8 | reversible | `irreversible` | `reversible` is not true |
| 9 | cost | `cost` | `cost_uu` is above `max_cost_uu` |
| 10 | cooldown | `cooldown` | a rejected or reverted outcome of the class is within `cooldown_days` |
| 11 | data | `low-data` | `n` is below `min_decisions` |
| 12 | score | `low-score` | the score is below `min_lower_bound` |
| 13 | daily cap | `daily-cap` | `max_moves_per_day` moves of the class are already logged today |

The two cheapest gates that need no logbook (1, 2) come first; the gates that read the logbook (4) are before the numbers (10 to 13) so a forged or broken record never reaches the score. Gate 5 is last of the rule gates so that a lapse or a missing opt-in shows its own word.

**Fail closed table.** The rows of 13.R11, each with the gate and the child process test that plants it (tests/autonomy/test_gates.py):

| 13.R11 | planted state | gate | answer, exit |
| --- | --- | --- | --- |
| 1 | no `autonomy.yaml` / `enabled: false` / a key missing / a value out of range / a YAML error | `autonomy-off` / `settings-invalid` | Ask me first, 3 |
| 2 | 29 clean approvals with `min_decisions: 30` | `low-data` | Ask me first, 3 |
| 3 | `reversible: false`; the field missing (the rule is malformed) | `irreversible` / rules broken | Ask me first, 3 |
| 4 | `cost_uu` 11 with max 10; missing (malformed) | `cost` / rules broken | Ask me first, 3 |
| 5 | a matching No rule and an opt-in Ask rule with 500 clean approvals | no step 8 | No, 2 |
| 6 | an old chained entry edited; a deleted entry; the hash record changed; a chain not started; a torn tail; `LOGBOOK.md` unreadable | `chain` | Ask me first, 3 (the logbook refusal of layer 5 holds) |
| 7 | a forged input: a well formed entry with a wrong Checked line; an entry with a count field; an unchained input written before the chain; an unknown outcome word; a duplicate `ref` | `inputs-invalid` | Ask me first, 3 |
| 8 | `.umwayi/KILL` present; `.umwayi` a file (unknown) | `kill-switch` | Ask me first, 3 (No with `--kill-switch`) |
| 9 | `rules.yaml` unreadable; `autonomy.yaml` a directory; a bad action JSON; a clock that is not a date (`--date` is refused at 64) | rules or file errors | Ask me first, 3 |
| 10 | `--no-log`; a held logbook lock; a full disk is not tested | `no-log` / the layer 2 write rule | Ask me first, 3 |
| 11 | the Yes rule past `review_by` matching the same action; the opt-in rule past `review_by` | `election-lapsed` / `opt-in-lapsed` | Ask me first, 3 |
| 12 | a `rejected` ten days ago with a perfect score; 5 moves already logged today | `cooldown` / `daily-cap` | Ask me first, 3 |
| 13 | a planted crash (an exception) inside the score | none | exit 2 |

**`autonomy status`** prints one block per class declared by a rule or present in the record:

```
class git-commit   rule commit-ask   reversible yes   cost 2 of 10 UU
  approved 80  edited 2  rejected 0  reverted 1  weight 3  n 85  score 838 per mille  (needs n 30, score 850)
  cooldown until 2026-12-30   moves today 0 of 5   state: Ask me first (cooldown)
graded autonomy: on. inputs: intact (146 outcomes). kill switch: off.
```

Exit 0. When off it prints `graded autonomy: off` and the counts as a display. When the inputs are invalid it says so and prints no score.

**The adapters.** The example rules of the three adapters add, to the guard lists: the paths `autonomy.yaml` and `autonomy.example.yaml`, and the shell commands `umwayi autonomy`, `umwayi decision`. A helper can still run `umwayi petition` (owner's choice).

### Commands and exit codes

| command | 0 | 1 | 2 | 3 | 64 |
| --- | --- | --- | --- | --- | --- |
| `umwayi check` | Yes | | No, a crash | Ask me first | usage |
| `umwayi rules due` | no rule lapsed | | a crash | a rule lapsed, or the rules cannot be read | bad `--within` or `--date` |
| `umwayi decision reopen` | done | refused, nothing changed (13.R4.5, 13.R4.6) | a crash | | bad id, hash, reason or name |
| `umwayi queue answer` | done | as today | a crash | | a decision without `--revisit-if`, a bad value, a task with it |
| `umwayi petition` | added, or already open | refused (13.R6.1, 13.R6.5) | a crash | | bad rule id, helper or reason |
| `umwayi autonomy status` | printed | | a crash | | bad `--class` or `--date` |
| `umwayi autonomy validate` | valid | | a crash | | invalid (every problem printed with a line number) |
| `umwayi autonomy record` | recorded | refused (13.R9.5) | a crash | | bad class, outcome, name or ref |

### Failure modes

| failure | what happens |
| --- | --- |
| `review_by` is not a real date, or is on a No rule | `rules.yaml` is malformed: every check is Ask me first until fixed; `rules due` exits 3 and says so |
| `rules.yaml` has `review_by` before slice 1 is merged | the old code calls the file malformed (Ask me first for all); the docs say not to add it early |
| the system clock jumps forward | rules lapse early (safe); they renew when the owner edits the date |
| the system clock jumps back | the newest logbook date still counts, so nothing revives; new entries are refused as going backwards (a Yes becomes Ask me first) |
| a lapsed rule is the only one that approved a scheduled job | the job's check gives Ask me first and the job stops with its queue item; `rules due` warns 14 days ahead |
| reopen of a hash with no entry, of an open or task row, of an unchained entry | exit 1, nothing changed, no entry |
| reopen with a broken chain | exit 1, nothing changed; `umwayi logbook verify` names the line |
| `queue.md` and the logbook disagree (a row hand deleted) | exit 1; the row is not recreated |
| a crash between the queue write and the entry | the queue commit puts `queue.md` back; exit 2 |
| a petition flood | the limits refuse with exit 1; no entry, no row |
| a petition reason with instructions in it | it is untrusted text in `queue.md` only, marked as such; no code reads it; the owner reads it as a claim, not an order (a risk below) |
| `rules.yaml` changed while the logbook is locked | the new rules give no Yes for this check; the next check logs the change |
| `autonomy.yaml` invalid | graded autonomy is off; `validate` prints the problems |
| a hand edited logbook | every write and every check that logs is refused by layer 5 as today; no move |
| `status` run with a broken chain | prints that the inputs cannot be read and no score |
| a very large logbook | one pass of the file per check, shared by the clock, the rules log and the inputs; the acceptance test runs a 5000 entry logbook (KNOWN-LIMITS 124 for the same cost in the governor) |

### Tests (13.R13)

All as real child processes in a temporary root. Each slice has a support module that builds a root with a chained logbook, a rules file and the fixtures, and writes records through the real commands, not by hand, except for the forged inputs, which are written on purpose through `logbook.append` or by editing the file.

- **Slice 1** (`tests/test_elections.py`): the rule past `review_by` (the planted fault): `check --date` the day after is Ask me first (3) with the fallback in the entry; the same day is Yes; a past `--date` or a logbook entry dated later does not revive it; a No rule, an Ask rule without opt-in and each bad date (`2026-13-01`, `2026-2-1`, `tomorrow`, `20261101`, a list) make the rules malformed; a lapsed Yes beside a fresh Yes gives Ask me first; a lapsed Yes beside a No gives No; `rules due` output byte for byte, exit 0 and 3, no write (root snapshot), no rule text printed (sentinels in title, text, cause); bare `rules.check` callers (a job, a helper) fall back too; a rules file with no `review_by` gives the old bytes (a golden file of an entry and the JSON).
- **Slice 2** (`tests/test_reopen.py`): the reopen of a missing entry (the planted fault): an unknown hash, a 63 and a 65 character hash, uppercase hex, a hash of a `check` entry, a hash of an older closing entry, a Q id that does not exist, a task, an open decision, an unchained entry: exit 1 or 64 as the table says, nothing changed; the broken chain (the planted fault): an old entry edited, a deleted entry, a changed hash record, a torn tail, a chain not started: exit 1, nothing written; the happy path: one entry appended, the file before is a byte for byte prefix of the file after, the entry names the hash in full and starts with `Reopen of entry`, the new row is open and the old row is byte for byte the same, `logbook verify` is ok, the anchor still verifies; a second reopen while the first row is open is refused, and after closing it succeeds with the new hash; `--revisit-if` required for a decision, refused for a task, `none` accepted, a pre layer 13 answer reads `not recorded before layer 13`; the injected crash in the queue commit; two reopens at once; the reason with `|`, a newline, 301 characters.
- **Slice 3** (`tests/test_petition.py`, `tests/test_rulelog.py`): the petition spam (the planted fault): 200 petitions from one helper and 60 helper names, with the counts of open and accepted exactly at the limits of 13.R6.5, the exit codes, the number of rows and entries, the time bounded, `rules.yaml` and the answers of a fixed set of actions unchanged; a petition against a Yes, an Ask, a missing rule or with broken rules: exit 1; a reason that reads like an instruction appears only in `queue.md`, never in the logbook, the title is the fixed template; the owner's answer does not change a rule; a rules edit before use (the weakening of `no-money` to `yes`): the `umwayi rules` entry is in the logbook before the check entry of the same call, names the id and `no to yes`, holds no rule text, and is not repeated by the next check; a comment only edit logs `no rule changed`; with the logbook locked or the chain broken the new Yes rule gives Ask me first and a No stays No.
- **Slice 4** (`tests/test_honest.py`): the note is in both pages; the banned list finds a planted word in a copy; the KNOWN-LIMITS items exist; the stop criteria table is in the page.
- **Slice 5** (`tests/autonomy/`): the worked example, cases 1 to 6, to the per mille, on Python 3.10 to 3.13; 200 fixed tuples against precomputed scores; every row of the fail closed table; off by default (100 clean approvals, no file or `enabled: false`: Ask me first, and the entry and JSON byte for byte as without layer 13); a forged score input (the planted fault) in the five ways of row 7; the text blind test (sentinels and instruction text in queue titles, answers, recommendations, petitions, reasons, rule titles, other logbook sources: `status` output and the answer are the same); the moves do not feed the score (100 moves, `n` the same); every class on the never list with `autonomy` makes the rules malformed; two Ask rules with one opt-in: Ask me first; a matching No: No; the daily cap; the dry run; a caller that does not log (a job): no move; a code guard (the module imports no `queue`, no `subprocess`, no network).
- **Mutation checks** (13.R13.2): at least these faults, each killed by a named test, counts in the pull request: expiry `<` for `<=`; the clock from `--date` only; the fallback not logged; the old entry marked; a reopen that opens the old row; a petition that edits the rule; a petition limit off by one; the rules entry written after use; a gate skipped (one mutation per gate); the score rounded up; a revert not counted; a score that reads a queue title; `enabled` ignored; an unchained input accepted.

### Docs page plan

| page | what | when |
| --- | --- | --- |
| `docs/corrections.md` (new) | Purpose; Current state (Elections, Reversal, Courts, the rules change log, stop criteria, "No state is perfect"); Decisions log (the owner's decisions of Nov 11); Open questions | written "specified, not built" in L13.0; each slice makes its part current |
| `docs/autonomy.md` (new) | the score, `autonomy.yaml`, the opt-in, `record`, `status`, the gates and the fail closed table, the worked example, "No state is perfect" | L13.0 (specified); current in L13.5 |
| `docs/rules.md` | `review_by`, `rules due`, the `autonomy` field, the rules change log, the election clock | L13.1, L13.3, L13.5 |
| `docs/queue.md` | `--revisit-if`, a petition item, a reopen item | L13.2, L13.3 |
| `docs/logbook.md` | the new entry shapes; "a reopen is a new entry; the old one is never marked" | L13.2, L13.3, L13.5 |
| `docs/exit-codes.md` | the table of Commands and exit codes | each slice |
| `docs/adapters.md` and the three adapter READMEs | the new guard names in the example rules | L13.1 (rules due), L13.5 |
| `docs/architecture.md`, `docs/testing.md`, `docs/security.md` | the layer 13 line, the test modules, the boundary (item 135) | each slice |
| `docs/KNOWN-LIMITS.md` | items 160 to 163, 166 to 170 and 192 to 195 (164 and 165 not used) | the slice that causes each |
| `docs/status-log.md`, `docs/schedule.md`, the status table in tasks.md, README, PROJECT.md | the status and the pull requests | each slice |
| `docs/interface.md` | one line if the owner asks for the layer 13 stations (L13-Q13) | not in layer 13 |
| `autonomy.example.yaml` | the settings with `enabled: false` | L13.5 |

### Hours and schedule effect

| task | hours |
| --- | --- |
| L13.0 spec | 8 |
| L13.1 Elections | 14 |
| L13.2 Reversal | 20 |
| L13.3 Courts and the rules change log | 16 |
| L13.4 Honest tension | 5 |
| L13.5 Graded autonomy | 32 |
| L13.6 whole-system update | 6 |

About 93 hours of build and 8 of spec. The layer 12 round 2 plan is about 75 hours in the same weeks (PR 39, UI.2 and later), so the two together are about 170 hours between Nov 11 and Nov 28. That does not fit one person at a normal pace, and the owner has said to stop where the deadline finds us. The plan, if the spec is approved on Nov 12: L13.1 Nov 12 to Nov 13, L13.2 Nov 14 to Nov 16, L13.3 Nov 17 to Nov 19, L13.4 Nov 20, L13.5 Nov 21 to Nov 26, L13.6 Nov 27 to Nov 28. The last day a slice can be merged is **Nov 28**. Nothing on the main schedule moves: README, demo and Devpost text Nov 23 to Nov 28, the freeze Nov 29 to Dec 2, submit Dec 3. A slice that is not merged by Nov 28 is not merged (13.R8.3), so the cut is always from the end: graded autonomy first, then the whole-system update, then Honest tension, and so on. After any slice the product is whole: the earlier slices do not depend on the later ones. The hours of L13.5 are the least certain (the gates are many, each with a test); if the owner wants the safer cut, L13.5 is built after Nov 22 only if L13.1 to L13.4 are merged and green, which is the plan.

### Risks (layer 13)

| risk | what happens | what we do |
| --- | --- | --- |
| a lapse stops a scheduled job at night | the job asks and waits | `rules due` 14 days ahead; the queue shows the Ask me first; a lapse is never silent |
| the owner renews by habit | `review_by` moves forward without a look | stated in KNOWN-LIMITS 160; `rules due` lists what lapsed; an election is only as good as the person |
| a petition is a prompt injection | the owner (or an AI helper that reads the queue) follows text a helper wrote | the title is a fixed template; the reason is marked untrusted; no code reads it; the logbook never holds it; the steering rule 4 holds (a helper drafts only) |
| petition spam hides a real petition | the owner stops reading them | the limits of 13.R6.5; the cap on open petitions means a spammer fills the cap and no more |
| the score rewards careless approving | a high score from habit | the bound is cautious, a revert weighs 3 and starts a cooldown, a class is narrow by the rule's matchers, the owner's record is the input and is stated as the limit (KNOWN-LIMITS 169) |
| a class is too wide | one score for different things | the class is the owner's name in a rule with its own matchers; `status` shows the counts so a wide class is visible (L13-Q3) |
| a forged score input | a move that the owner did not earn | fixed shapes, chain, tamper check, a whole record invalid on one bad entry, text never read; a same-user writer with the chain logic is the item 135 boundary, not prevented |
| an AI helper opens the autonomy door | a helper writes `autonomy.yaml` or records outcomes | the guard names in the example rules of every adapter; the settings are logged before use; `enabled` is off by default |
| the logbook read on every check slows a hook | a hook times out | one pass shared by every step; the 5000 entry test; if too slow the entry reader is cached by file size and hash, in a later change |
| the existing tests break (`queue answer` needs `--revisit-if`) | red CI | the tests of decisions are updated in L13.2 with the reason in the pull request; nothing else of the earlier tests is changed |
| the spec of layer 12 and 13 disagree | confusion about the view | layer 13 changes nothing in the view (13.R15); 12.R8 and UI-Q11 stay the place where the owner decides |
| rules were weakened and used at once | a helper edited the rules | the entry names the id and the change, dated; the guard rules forbid a helper to touch `rules.yaml`; L13-Q11 is the stricter option |

### Open questions for the owner (layer 13)

The owner's decisions of Nov 11 are above and are not asked again. Each question below has the answer proposed; the build uses the proposal unless the owner answers otherwise.

1. **L13-Q1. What a reopen does to the queue.** It adds a new open row and leaves the old row as it was (proposed, like the logbook). Or it flips the old row to open.
2. **L13-Q2. Where "what would change my mind" is stored.** In the logbook entry of the answer, as `; revisit if: TEXT` (proposed: it cannot be edited later, and no migration). Or a new column in `queue.md`, visible in `queue list`, which needs a migration like the answer column did.
3. **L13-Q3. What an action class is.** A name the opt-in rule gives (`class: git-commit`), with the rule's own matchers saying which actions belong (proposed: it is narrow, it is the owner's, and no action text names it). Or the action's `type` (wide, so a `tool_bash` score would mix everything).
4. **L13-Q4. Where reversibility and cost are declared.** In the opt-in rule, next to the class (proposed: one place, and they can lapse with the rule's `review_by`). Or per class in `autonomy.yaml`.
5. **L13-Q5. Defaults for the thresholds.** None: every setting is required and `autonomy.example.yaml` carries suggested values (proposed: "owner defined" means no hidden default). Or defaults in the code.
6. **L13-Q6. How outcomes are recorded.** With `umwayi autonomy record` (proposed: explicit, one chained entry each). Or as a flag on `queue answer` (`--outcome approved`), which is easier to use and is a later addition.
7. **L13-Q7. The weights.** Only `approved` is a success; `edited` and `rejected` are one failure each; a revert is `revert_weight` (3) failures on top of its approval (proposed, cautious). Or an edit counts as half.
8. **L13-Q8. Confidence and suggested thresholds.** z 2.58 (about 99 percent), `min_decisions` 30, `min_lower_bound` 850 per mille, so a class needs 38 clean approvals, or 60 with two failures among them, to pass (proposed: cautious). Or z 1.96, which needs fewer.
9. **L13-Q9. `rules due` exit codes.** 3 when a rule lapsed (proposed: a scheduled job can notice), else 0. Or always 0.
10. **L13-Q10. How far ahead `review_by` may be.** No limit, but a date more than 366 days ahead is listed as `far` (proposed). Or a date that far makes the rules malformed.
11. **L13-Q11. A weakened rule.** Logged before use and used at once (proposed, as the owner decided for Courts). Or held at Ask me first until the owner runs `umwayi rules accept --by NAME`, which is a stricter design for after Dec 3.
12. **L13-Q12. Petition limits and the reason.** One open per helper and rule, 3 open per helper, 10 open in all, 5 accepted a day per helper, 10 in all, a free text reason of 200 characters (proposed). Or a fixed list of grounds and no free text, which has no injection path and says less.
13. **L13-Q13. The view.** Layer 13 changes nothing in the view; the owner decides on the review, reopened and petition stations (12.R8, UI-Q11) when layer 13 is built (proposed). Or a counts only snapshot schema 2 is added in L13.6.
14. **L13-Q14. What a standing approval is.** A Yes rule (proposed). An installed schedule runs through the Yes rules it asks (`run_job`, `workflow_step`), so it lapses when they do. Or `schedule.yaml` entries get their own `review_by`.
15. **L13-Q15. A queue item for a lapsed rule.** No: `rules due` is the list, and a scheduled job can run it (proposed). Or `rules due --queue` adds one decision per lapsed rule.
16. **L13-Q16. A lapsed Yes next to a fresh Yes.** Ask me first, the stricter answer (proposed). Or the lapsed rule is ignored and the fresh Yes stands.
17. **L13-Q17. The chain.** Reopen and `autonomy record` need the hash chain to have started (proposed; the owner runs `umwayi logbook seal --chain` once). Or they work without it, linking an unchained entry by the SHA-256 of its text, a weaker link.
18. **L13-Q18. Cooldown and the daily cap.** A rejected or reverted outcome stops moves for the class for `cooldown_days` (30), and at most 5 moves a class a day (proposed). Or a revert alone triggers the cooldown.

Answers (owner, Nov 11): decisions 1 to 6 above. L13-Q1 to L13-Q18 are open.

## Local backend (W6): `umwayi serve` (spec in the W6.0 pull request, tasks.md W6.0; built only after the owner approves it)

This section is added at the end of the file so it merges cleanly with the other branches. It designs requirements W6.R1 to W6.R18. Nothing is built. The chat routes (W4) and the intake routes (W5) are designed to the level the backend must leave room for; W4 and W5 write their own specs. W7 (login for a deployed interface) is only constrained here.

### Owner decision of Nov 12 2026 (approved) and how each word lands

> The rule changes from "the interface only looks" to "the page may send the same request the command line would, to a local backend." Command: `umwayi serve`, bound to 127.0.0.1 only, with a token. Every request goes through the same rules check, the same logbook and the same kill switch as the command line, by calling the same code, never a second copy. Fail closed: unclear means Ask me first or No. The core stays Python standard library only.

| the owner's words | where it lands |
| --- | --- |
| the same request the command line would | the route table is the command table (W6.R8.1); a response is a subset of what the command prints (W6.R8.2); a differential test per route |
| a local backend, `umwayi serve` | W6.R2; one foreground command, no daemon |
| bound to 127.0.0.1 only | W6.R3; the literal address, read back, no flag, no config key |
| with a token | W6.R4 and check 7 of the gate |
| the same rules check | step 4 of the pipeline: `rules.check_and_log` with the action `serve_request` (W6.R7.1.4) |
| the same logbook | step 5 (the core function's own entry) and step 6 (the request entry) |
| the same kill switch | step 3 (`kill.state`), and the one-second watch for chats |
| by calling the same code, never a second copy | W6.R1.1; the handler table below; the spy, differential and code guard tests (W6.R16.3) |
| fail closed, unclear means Ask me first or No | the gate refuses by default; the table "The fail closed table" |
| the core stays standard library only | `http.server` and `socket` imported inside one function; the guard tests get the name `umwayi/serve.py` |

What I decided where the words left room, each asked as a question at the end: the rules check applies to every request and not only where the command line has one (W6-Q2); writes are stopped by the kill switch although the command line's owner commands are not (W6-Q3); the page is served by the backend so there is no CORS (W6-Q6); `Origin` is required on `POST` (W6-Q8); reads are logged (W6-Q10).

### The shape of a request

```
browser page, served from http://127.0.0.1:PORT (same origin), fetch('/v1/...') with Authorization: Bearer TOKEN
    |
    v  umwayi serve, bound to 127.0.0.1 only
 1  read the request into Facts           own strict reader, no stdlib header parsing
 2  servegate.decide(facts, state)        pure: no file, no clock, no network; Allow(route) or Refuse(word)
 3  servegate.parse_body(route, bytes)    pure
 4  kill.state(root)                      the function the agents call; a stopped route needs "off"
 5  rules.check_and_log(serve_request)    the function `umwayi check` calls; logs its own entry
 6  the route's core function             the function the command line calls; writes its own entry
 7  logbook.append(request entry)         the function every writer calls
 8  response: the fixed envelope          the same bytes for the same refusal word
```

A refusal at step 2 ends the request. Nothing after step 2 runs for a request the gate refused, and nothing before step 2 reads a file, so an unauthenticated caller can make the server do the work of steps 1 and 2 only.

### Files

| file | what | notes |
| --- | --- | --- |
| `umwayi/servegate.py` | `Facts`, `State`, `Verdict`, `decide`, `parse_body`, the route table, the buckets | pure; imports only `hmac`, `hashlib`, `json`, `re` and `dataclasses`; no `os`, `socket`, `time` or `http` |
| `umwayi/servetoken.py` | create, rotate, revoke, status, `verify` | the record file through `fsutil`; the entries through `logbook.append` |
| `umwayi/serve.py` | the reader, the handler class, the pipeline, the handler table, the page, start and stop, the summary counters, the degraded state | `http.server` and `socket` imported inside `run_server` only |
| `umwayi/cli.py` | a `serve` subparser (with an optional `token` sub-command) and `_cmd_serve` | the import of `umwayi.serve` is inside `_cmd_serve`; exit 2 on any unexpected error is added to `tests/test_exit_codes.py` |
| `umwayi/rules.py` | `serve_request` added to `NEVER_AUTONOMY` | one word, with its test and the line in `docs/rules.md` |
| `umwayi/budget.py`, `umwayi/agents.py` | W6.7 and W6.8 (refactors, no behaviour change) | before any chat route |
| `tests/serve/` | `gen.py`, `oracle.py`, `test_gate_properties.py`, `test_wire.py`, `test_samecode.py`, `test_token.py`, `test_entries.py`, `test_failclosed.py` | standard library only |
| `ui/src/api/client.js`, `ui/src/ui/backend.js` | the one client module and the panel | W6.9; the owner builds; the live view only |
| `docs/serve.md`, `serve.rules.example.yaml`, `adapters/NOTES-w6.md` | the page, the example rules, the dated browser facts | `docs/serve.md` is in this pull request, the others later |
| `.gitignore` | `.umwayi/serve.token`, `.umwayi/serve.lock` | with the test in `tests/test_docs.py` style |
| the three adapters' example rules | deny `umwayi serve` and the token file for an AI helper | text matching, KNOWN-LIMITS 12 |

### The same code: the handler table

Each handler is a few lines. It reads parameters the gate and `parse_body` already checked, calls the core function named below, and returns `(code, data)` using the same mapping the command line handler uses. The "extract" column is the logic that sits in the command line handler today and moves into the core so that both call it. This list was found by reading `umwayi/cli.py`; the build checks it again.

| route | core call | extract before the build |
| --- | --- | --- |
| status | `kill.state(root)`, `servetoken.status` | none |
| snapshot | `logbook.read_checked_chain(root)`, `view.gather(root, when, entries, chain_length)` | none: `view.snapshot` already is "gather then write the file" |
| queue.list | `taskqueue.list_rows(root, status, kind)` | none |
| logbook.verify | `logbook.verify(root, None)` | the wording of the output stays in the command; the route sends counts and check names |
| budget.status | `budget.status(root, day, today)` | none (returns `(code, lines)`) |
| agents.list | `agents.load(root, None)`, then `name`, `platform`, `transport` | none; the route sends less than `list_agents` prints |
| agents.check | `agents.check_agent(root, name, None, None)` | none |
| queue.add | `taskqueue.add_once` when `if_not_open`, else `taskqueue.add` | the `if cmd == "add" and args.if_not_open` branch of `_cmd_queue` becomes one function in `taskqueue`, called by both |
| queue.answer | `taskqueue.answer(root, id, answer, when, revisit_if=...)` | none |
| queue.close | `taskqueue.close(root, id, when)` | none |
| kill.on | `kill.turn_on(root, when, why)` | none |

**Where the command line is thinner than the web request**, which is why "the same" needs a decision. The command line's owner commands (`queue add`, `answer`, `close`, `kill on`) ask no rules and are not stopped by the kill switch; `umwayi check` asks the kill switch only with `--kill-switch`; the agent code always passes the kill state (`agents.py`, `_Run._permission`). A request from a page is not the owner at the keyboard (a script in the page, a stolen token and a mistaken click are all possible), so the web door uses the stricter of the two: the rules check and the kill switch for every request but `kill.on`. This is W6-Q2 and W6-Q3.

**The action the rules see.** `{"type": "serve_request", "route": "queue.answer", "class": "write", "platform": "web"}`. A rule can match `type`, `route`, `class` and `platform` like any other field (layer 2's matchers). `serve.rules.example.yaml` has the starter set: `serve-read` (Yes, `class` equals `read`), `serve-write` (Ask me first, `class` equals `write`), `serve-run` (Ask me first, `class` equals `run`). With no rule at all every request is Ask me first (the answer of layer 2 for no match), so the page is unusable until the owner writes a rule, and the server prints a hint at start (W6.R15.5). `review_by` (13.R2) works on these rules like any Yes rule.

### The request gate in detail (`umwayi/servegate.py`)

**Where the facts come from.** The stdlib `BaseHTTPRequestHandler` is used only for the socket loop. Its `parse_request` and `self.headers` are not used, because they accept an HTTP/0.9 request line, fold and merge headers and hide duplicates. The handler overrides `handle_one_request`: it reads the request line with `rfile.readline(8193)` (a longer line is refused), splits it with one regular expression (`^(GET|POST|DELETE|[A-Z]{1,16}) (\S{1,512}) (HTTP/1\.[01])\r\n$`, anything else becomes an empty `Facts` that the gate refuses with `target` or `method`), then reads header lines with `readline(4097)` until the empty line, at most 65 lines, keeping every line as a (name, value) pair in order, and refusing a line that starts with a space or tab (a fold). It never calls `email` or `http.client` header parsing. The facts are therefore exactly the bytes on the wire, and the pure gate sees what the property tests generate.

**`Facts`** (frozen): `version`, `method`, `target`, `headers` (a tuple of pairs), `peer` and `server` (host and port strings), `declared_length` (an int or `None`, computed by the gate, not the reader). **`State`** (frozen, replaced under a lock): `record` (the token record or `None`), `date` (the election clock date), `mono` (monotonic seconds), `auth_bucket`, `class_buckets`, `fail_window`, `port`. **`decide(facts, state)`** returns `(verdict, next_state)`: `Allow(route, params, body_cap)` or `Refuse(status, word)`, and a new state with the buckets and the failure window updated. The server swaps the state in under one lock. The properties of W6.R16.1 are stated over this signature.

**Why a token check before the route check.** Routes, methods, body limits and parameter shapes are information. A caller without a valid token gets 401 for every `/v1/` target, whether the route exists or not, so the table cannot be mapped from outside. `GET /` is the only target answered without a token.

**The token comparison.** `hmac.compare_digest(sha256(presented).digest(), bytes.fromhex(record.sha256))`. A presented token is first shape-checked (48 characters, `umt1_` prefix, base64url alphabet) so the digest work is bounded; a token of the wrong shape counts as a failure and gets the same 401. The record is read by the server shell for each request, not by the gate.

**Origin and Host, in a table** (a request needs all of the row to be Allow; "absent" means no such header):

| Host | Origin | method | answer |
| --- | --- | --- | --- |
| `127.0.0.1:PORT` | absent | `GET` | pass (a browser omits `Origin` on a same-origin `GET`) |
| `127.0.0.1:PORT` | absent | `POST`, `DELETE` | `origin` (a browser always sends it) |
| `127.0.0.1:PORT` | `http://127.0.0.1:PORT` | any | pass |
| `127.0.0.1:PORT` | `null`, other host, other port, `https://...`, empty, two values | any | `origin` |
| anything else, missing or doubled | any | any | `host` |

`Sec-Fetch-Site` must be `same-origin` when present (for `GET /` also `none`, which a browser sends for a typed address). The MDN pages say a browser adds `Origin` to same-origin requests other than `GET` and `HEAD`, and that fetch metadata headers go only to potentially trustworthy URLs; whether a browser treats `http://127.0.0.1` that way is not verified here, which is why those headers are checked when present and never relied on (`adapters/NOTES-w6.md`).

**The page response** is the file's bytes with the headers of W6.R6.6. The page file is read once at start and again for each request (the owner may rebuild it), and its SHA-256 compared with `build.json` each time; a mismatch is 503 `page`.

**What the stdlib server does that the gate cannot see.** `ThreadingHTTPServer` sets `daemon_threads` (a thread per connection, bounded by the semaphore of W6.R14.1); `allow_reuse_address` is false (a port in use is a 64 at start); `handle_error` is a no-op (no traceback with request content); `log_message` is a no-op; every response sets `Connection: close` and the handler closes the socket. A deadline timer cuts the connection at 10 seconds (30 for the long poll), as the telemetry receiver does.

### Tokens in detail (`umwayi/servetoken.py`)

- **Record.** `{"schema": 1, "id": "T-91ab02cd", "sha256": "<64 hex>", "created": "2026-11-12", "expires": "2026-12-12"}`, two spaces of indent, a final newline, mode 0600, through `fsutil.atomic_write(path, data, mode=0o600)`. The reader accepts exactly these keys, a date that is a real date, an `expires` after `created` and at most 90 days after it, and a `sha256` of 64 lowercase hex characters; anything else is "no valid token", which refuses every request. `.umwayi` must be a normal folder (the check `runlock.held` and `logbook._lock` already make).
- **Create.** Refuse if stdout is not a terminal (exit 1). Refuse if a record exists (exit 1). Make the token. Write the record. Append the entry. If the append raises, remove the record and exit 2 with nothing printed. Print `Token: umt1_...`, `Id: T-...`, `Expires: DATE` and the line "Shown once. umwayi keeps only a fingerprint of it." Exit 0.
- **Rotate.** Needs a record. Make the new token. Keep the old record text in memory. Replace the record. Append the entry. If the append raises, write the old text back and exit 2. Print as above. The running server reads the file on the next request.
- **Revoke.** Remove the record, append the entry; if the append raises, write the record back and exit 2.
- **Status.** Read only. Prints `Token T-...: created DATE, expires DATE, N days left` or `No token.` Exit 0. It does not check the logbook and writes nothing.
- **Why a digest file in the repo folder is acceptable.** The digest of 32 random bytes is not reversible; an AI helper that can read `.umwayi/serve.token` learns the id and the dates and cannot make a request. The raw token exists in the owner's terminal scrollback and in the page's memory, and nowhere else.
- **Why not a per-start token.** It would remove the file and the rotation commands. But the page could then never be bookmarked with a token, a second terminal could not call `token status`, and every restart would print a secret again. W6-Q5 keeps the stored digest as the proposal.

### The pipeline's table: what happens when something is wrong

The fail closed table. Each row is one test in `tests/serve/test_failclosed.py`; "no change" means the root is byte for byte the same afterwards, except the entries named.

| situation | word | code | what changes |
| --- | --- | --- | --- |
| any gate check fails (W6.R5.2) | the gate's word | 2 | nothing; counted in the summary if no valid token |
| the token record is missing, unreadable, malformed, expired or revoked | `token` | 2 | nothing |
| the gate raises | `error` | 2 | nothing |
| `rules.yaml` missing or broken | `ask` | 3 | one queue decision (`add_once`) and the check's entry |
| the rules check says No | `rules` | 2 | the check's entry and the request entry |
| the rules check says Ask me first | `ask` | 3 | one queue decision, the check's entry and the request entry |
| the rules check answered Yes but could not be logged | `logbook` | 2 | nothing |
| the kill switch is on or unknown and the route is stopped | `kill` | 3 | the check's entry (No by the switch) and the request entry |
| the date is before the newest logbook entry | `logbook` | 2 | nothing (the append refuses) |
| the logbook fails its tamper check | writes: `logbook` 2; `snapshot` and `logbook.verify`: `refused` 1 | | nothing |
| `queue.md` is malformed | `refused` | 1 | nothing |
| the core function raises `UsageError` | `usage` | 64 | nothing |
| the core function raises `UmwayiError` | `refused` or `error`, as the command | 1 or 2 | as the command |
| the core function raises anything else | `error` | 2 | whatever the command left (it is atomic, like the command line) |
| the request entry cannot be written after the command | `logbook` | 2 | the command's change stays; the response says `"changed": true`; the server is degraded |
| degraded and the request is not `GET /`, `status` or `kill.on` | `logbook` | 2 | nothing |
| the body fails `parse_body` | `body` | 64 | nothing |
| 17 requests at once | `busy` | 2 | nothing |
| the write lock is not free in 5 seconds | `busy` | 2 | nothing |
| the page file differs from `build.json` | `page` | 2 | nothing |
| a chat start is refused by the budget | `budget` | 3 | what `agent chat` writes for the same refusal |
| a chat start finds the run lock held | an event `stopped` with code 3 | 3 | what `agent chat` writes |
| an agent needs a terminal (`transport: cli`) | `usage` | 64 | nothing |
| a permission is not answered in 300 seconds | `reject_once`, an event | | one entry |
| a chat has no request for 10 minutes | an event `stopped` (`idle`) | | the chat's own end entry |
| SIGTERM or Ctrl-C | the server stops accepting, stops each chat, settles it, appends the stop entry | 0 | as listed |
| the stop entry cannot be written | | 2 | the chats are already stopped |

### The entries (examples, W6.R13)

A read that passed:

```
Source:   umwayi serve
Added:    Request R-0b17c2de: GET queue.list, done (exit 0), 6 ms
Checked:  Token T-91ab02cd valid. Host and Origin exact. Kill switch off. Rules check Yes.
Not done: The body, the headers and the token were not recorded.
```

A write the rules turned into Ask me first:

```
Source:   umwayi serve
Added:    Request R-4d90aa13: POST queue.answer, refused (ask) (exit 3), 11 ms
Checked:  Token T-91ab02cd valid. Host and Origin exact. Kill switch off. Rules check Ask me first.
Not done: The body, the headers and the token were not recorded. The queue row was not changed.
```

A summary:

```
Source:   umwayi serve
Added:    Refused 37 requests before a token was checked or after the rate limit, in the last 60 seconds: host 30, token 4, method 2, rate 1.
Checked:  The count is from memory since the last summary. No request is named.
Not done: No address, header or body was recorded.
```

The route and word values come from fixed lists; a test builds every possible entry and checks it against a pattern.

### The chat routes (W4): what W6 must leave ready

From reading `umwayi/agents.py` and `umwayi/acp.py` (Nov 12): `chat_agent` builds a `_Run` and calls `go()`. `go()` installs SIGTERM and SIGHUP handlers, which only works on the main thread, and restores the terminal. The ACP chat (`acp.Chat`) reads owner lines from a file descriptor (`_owner_input()` is `sys.stdin.fileno()`), prints text to `out`, and asks the owner "Allow once? [y/N]" by reading the next owner line. There is no public `reserve()` or `settle()`: the budget steps are `_Run._reserve` and `_Run._settle`. Two refactors make a chat drivable by the backend without a second copy. Both come first, with no change of behaviour.

- **W6.7, the budget steps leave `_Run`.** `_Run._reserve` (units, ledger, the pending change entry, `budget.fit`, the `budget_check` rules call, the telemetry receiver for Claude Code, the run id, the reserve entry) and `_Run._settle` become `budget.reserve(...)` and `budget.settle(...)` with the receiver start passed in as a function, and `_Run` calls them. **Tests first, on the old code:** scripted fake-agent runs (a clean run, a stop by the kill switch, a stop by the per-run cap, a refusal by the day cap, a telemetry error, a crash) are run and their ledger entries and exit codes recorded as goldens; the same scripts must give byte-identical entries after the move. The existing budget and agent tests pass unmodified.
- **W6.8, the owner's side leaves `_Run`.** `_Run` and `acp.Chat` take an optional `owner` (where lines come from and where an Ask me first is answered) and `sink` (where text, tool calls and notices go), and `_Run` takes `install_signals` and `terminal` flags. The defaults reproduce today's behaviour exactly: the fd reader, text lines to `out`, signal handlers, the terminal restore. A new `request_stop(reason)` on `_Run` is what the signal handlers and a web `chats.stop` both call. **Tests first, on the old code:** the transcript (the exact text written to `out`) of scripted fake ACP chats is recorded for a normal turn, a tool call, an Ask me first answered `y` and `n`, `:queue`, `:quit`, Ctrl-C and each stop reason, and must be byte-identical after the change; the existing ACP tests pass unmodified.

With those two in place, a `ChatSession` (in `umwayi/servechat.py`, W4) does this:

- `chats.start` checks the rules and the kill switch like any request, then starts one worker thread that calls `agents.chat_agent(..., owner=web_owner, sink=web_sink, install_signals=False, terminal=False)`. It answers 202 with the chat id; every later outcome, including a refusal of the gate checks or the budget, arrives as an event with the exit code that `agent chat` would have given.
- `web_sink` appends events to the ring buffer under a lock and notifies a `threading.Condition`; `chats.events` waits on it for at most 25 seconds.
- `web_owner` is a queue of owner lines. `chats.message` puts a line on it (only when the chat is between turns). A permission request that needs the owner puts a `permission_request` event in the buffer and shows the `Allow once? [y/N]` prompt on the console of `umwayi serve`. The first answer wins: a console `y` or `n`, a `chats.permission` reject from the page (the only decision the page may send, W6-Q12), or nothing for 300 seconds, which is `reject_once`. With no terminal on the console the request is rejected at once. How an approval reaches a web chat is W6-Q28.
- `chats.cancel` calls `chat.interrupt()` (what Ctrl-C does). `chats.stop` calls `request_stop("quit")`.
- The server's main thread owns the signals. On SIGTERM or Ctrl-C it stops accepting, calls `request_stop("quit")` on each chat, joins the worker with a 15 second limit, then writes the stop entry. A worker that does not join leaves its reservation for `umwayi budget settle-lost` and the server exits 2.
- An idle timer thread (one for all chats, a one-second tick) stops a chat with no request for 10 minutes.

The run lock is held by the worker thread through the same `runlock.held` context as on the command line, so a scheduled run, `umwayi run` or a command line chat meets the same busy answer (exit 3) while a web chat lives. The telemetry receiver for a Claude Code chat starts inside `budget.reserve` on its own port with its own secret, as today.

**What the page sees of an agent.** Text through `acp.safe_text`; a tool call as a kind word and a short cleaned title; a permission request as a tool word and one button, Reject. Raw protocol messages, tool input, the argument list, the environment and every path are not in any event (a test plants sentinels in a scripted agent's messages and metadata and finds none in the events). The page draws agent text in a box labelled "AI helper says" and draws umwayi's own notices and permission requests in a different, labelled component, so text from an agent cannot pass for an Ask me first prompt. A reject needs a click on a button that exists only while the server has that permission id pending; there is no button that allows.

### The intake step (W5): what W6 must leave ready

Pure logic in `umwayi/intake.py` (W5): `assess(draft) -> (state, open_questions)`. The draft holds the kind, the intent, and the answers by question number. The questions of the first slice are a fixed list (what, why, done when, by when, does it spend money, publish, delete or touch someone else's data), so the function needs no model and can be property tested: total over any draft; an empty, whitespace, very short (under 3 characters) or over-long answer never counts as an answer; "unsure" to the last question is a question again, never a yes or no; adding an answer never reopens a question that was answered; the state `clear` needs every question answered; and no input makes `assess` return `clear` and `asking` together. The server keeps drafts in a dictionary under a lock, caps them (8 live, 24 hours idle), and drops them at stop. `intake.commit` recomputes `assess`, compares the `confirm` hash with the SHA-256 of the title and recommendation it would add, and only then calls `taskqueue.add`. The routes are `write` class for their rules check and rate, change no file before the commit, and log counts.

If W5 later lets an AI helper write the questions, the helper runs as a chat (W6.R9) with its own `agent_run` check and budget reservation, its questions arrive as events, and the owner's answers go back as messages. `assess` stays the only judge of "clear", so the helper can ask but cannot declare the intent clear.

### The page client (W6.9)

- `ui/src/api/client.js` exports `createClient({location, fetchImpl})`. It returns a client only if `location.origin` matches `^http://127\.0\.0\.1:[0-9]{2,5}$`; otherwise it returns a frozen object whose `available` is false and the panel says "Open this page with umwayi serve". It builds every request from a table of route ids (the same ids as the server), never from text. Each call sets `Authorization`, `Content-Type: application/json` for a body, `credentials: 'omit'`, `cache: 'no-store'`, `redirect: 'error'` and `referrerPolicy: 'no-referrer'`.
- The envelope is read strictly, the way `snapshot.js` reads a snapshot: exact keys, `schema` 1, `code` in the fixed set, `word` in the fixed list, `request` null or `R-` and 8 hex, `data` only when `ok`. Anything else shows one message, "umwayi did not answer in the expected shape", and nothing else.
- The token is typed into a password field, copied into a closure variable, and the field is cleared. It is never written to storage, the address, history, `postMessage`, the console, or any element's text. A reload forgets it.
- The words get plain sentences in one table: `ask` "Ask me first. The rules want you to decide; an item was added to the queue", `kill` "The kill switch is on", `budget` "The budget stops this", `token` "The token is wrong or has run out", and so on. No `word` reaches the page as markup.
- The panel (live view only) shows the status (kill switch, token days left), the queue, forms for add, answer and close, and a "Stop everything" button for `kill.on`. There is no button for anything on the never list. A timer in the page never asks the backend for state (W6.R14.6).
- Tests: the Node suite runs the client against a fake `fetch`, including a fake that returns every kind of bad envelope, and checks the requests it made (method, path, headers, body) against the route table; `tests/test_ui_package.py` checks the built page contains `fetch(` only in the client module's bundle region and the CSP meta tag is the old tag plus `connect-src 'self'`.

### Budget governor in the web door

The requests are free of UU; the chats are not. After W6.7 the web start reserves through `budget.reserve`, the same function and the same limits as the command line, and a refusal is the same text and exit code. `GET /v1/budget` is `budget.status` (a read). No route writes the limits file. See W6.R11 for the rules; the new risk is a page that starts and stops chats in a loop to churn reservations, which the `run` rate (1 a second, 6 starts an hour) and the day cap bound.

### Login for a deployed interface (W7): the fit

```
today (W6):        browser ---- http://127.0.0.1:PORT ----> umwayi serve        (same machine only)
a deployed site:   browser ---- https://site ----> site            (never calls 127.0.0.1; CSP default-src 'self')
W7 version 1:      deployed login + public site with sample data; no call to any local backend
only if decided after Dec 3:
                   umwayi (outbound only) ----> relay <---- deployed login ---- browser
                   the relay carries requests with channel = relay into the same gate and pipeline,
                   through a smaller route table; nothing listens on the internet
```

W6 does three things so W7 cannot be added by loosening W6: a `channel` that is a closed set of one value; a `Principal` in the pipeline; and a refusal of any local request whose `Host` is not the exact local address. The owner decided on Nov 12 (W6-Q22) that W7 version 1 is login plus the public site with sample data and controls no local backend. A relay is decided after Dec 3; the questions it must answer first are in W6.R12.

### Threats and what meets them

| threat | what meets it | where it is tested |
| --- | --- | --- |
| another website in the owner's browser sends a request | no cookies, token in a header, `Origin` exact, no CORS, preflights refused | the gate matrix; the by-hand browser pass with a second local origin |
| DNS rebinding | `Host` exact before the token | the gate matrix; the wire test with a `Host` override |
| another user of the machine | 256 bit token, throttle, the record 0600, the raw token never on disk | token tests; a second user cannot be tested in CI, so the by-hand pass notes it |
| a process of the same user | the raw token is not on disk and not in a child's environment; the adapters' example rules deny `umwayi serve` and the token file; the rest is a known limit | token tests; an environment test on a chat child; KNOWN-LIMITS |
| an AI helper that reads the page or the token | the helper's environment is the allowlist of `child_env`; the page is not exposed to it; a helper that can read the owner's terminal is a known limit | environment test |
| agent text that pretends to be umwayi | text only, a labelled box, a separate component for permissions, ids issued by the server | Node tests with hostile event text |
| a stolen token approving an AI helper's tool | the page can only reject; an approval is made at the terminal of `umwayi serve` (W6-Q12) | the route test: any decision but `reject_once` is `body`; the console test |
| request smuggling, header tricks | own strict reader, one request per connection, no `Transfer-Encoding`, one `Content-Length`, duplicates refused | the fuzz and the mutation catalogue |
| a flood from a local process | the 16 handler cap, the deadlines, the rates; the 17th gets 503 | the wire tests |
| the logbook filled by refusals | summary entries; the authenticated rate bucket | entry tests |
| token guessing | 256 bits, the throttle, the same answer for every wrong shape | token and gate properties |
| timing and size differences | `compare_digest` on digests; the same bytes for a refusal word | gate properties |
| a changed page | the SHA-256 against `build.json` each time | wire test; known limit that both sit together |
| a path or a name from a request used on disk | no route takes a path; ids match patterns; names are looked up in files the core already reads | the never list test; sentinel tests |
| the port carried out by a tunnel | `Host` exact; the docs say not to | gate matrix; known limit |
| replay or sniffing on loopback | none beyond the token's lifetime; no TLS | known limit |
| clickjacking | `frame-ancestors 'none'` | wire test (the header); not run in a browser here |

### What can go wrong in running (failure modes)

- **The server is killed with SIGKILL, or the machine loses power.** No stop entry. An open chat reservation stays until `umwayi budget settle-lost`. The next start runs the tamper check and the recovery of the logbook as every command does. The lock is a kernel lock and is released.
- **`rules.yaml` is broken.** Every request is Ask me first. The page can still read nothing; the owner fixes the file at the terminal.
- **The logbook is edited by hand.** The next start refuses (exit 1). While running, the next append is refused, the server goes degraded and says so in `status`.
- **The clock is set back.** Tokens that expired stay expired; writes are refused by the logbook's date rule; the rate buckets use a monotonic clock and are not affected.
- **The token is rotated during a chat.** The chat keeps running (it is not a request), the page's next request gets 401, the owner pastes the new token and the page continues with the same chat id.
- **Two tabs.** Both can hold the token. Two long polls on one chat are allowed (counted against the 4); a permission answered twice is refused the second time.
- **The port is taken.** Exit 64. A second `umwayi serve` for the same root exits 64 before it tries the port.
- **`queue.md` is changed by the command line while the page is open.** The page shows what it was told at the last request; the next request shows the new state. Writes are atomic and logged, as when two command lines meet (KNOWN-LIMITS 9).

### Hours, and what it does to the schedule

Estimates, without a margin. W6.0 (this spec) is about 8 hours and is this pull request.

| task | hours |
| --- | --- |
| W6.1 tests first: the generators, the oracle, the mutation catalogue, the golden requests | 9 |
| W6.2 `servegate.py`: `decide`, `parse_body`, the table, the buckets | 6 |
| W6.3 `servetoken.py` and the `serve token` commands | 6 |
| W6.4 `serve.py`: the reader, the handler, limits, the page, start and stop, the guards | 8 |
| W6.5 the pipeline: kill switch, rules check, command, entry, the summary, the degraded state, `serve_request` on the never list | 7 |
| W6.6 the first routes and the differential tests against the command line | 9 |
| W6.9 the page client and its panel, the CSP change, the page tests (the owner builds) | 8 |
| **First batch: W6.1 to W6.6 and W6.9** | **53** |
| W6.10 follows the first batch: the by-hand browser pass, the planted faults and the mutation pass, the whole-system scenarios (the docs are updated in each pull request) | 8 |
| W6.7 and W6.8 the two refactors; they wait until W4 starts | 13 |
| W4 chat routes (own spec) | about 20 |
| W5 queue intake routes (own spec) | about 14 |

The owner's answer of Nov 12 (W6-Q27): the build order is W6.1 to W6.6 plus W6.9 first, about 53 hours; W6.7 and W6.8 wait until W4 starts; the dates are set by the owner after UI.7 merges. The schedule to Dec 3 had no window for this when it was written (layer 12 about 75 hours until Nov 22, README, demo and Devpost Nov 23 to Nov 28, L13.6 on Nov 27 to 28, the freeze on Nov 29), and I have not placed W6 in the schedule table. W6.1 to W6.6 are one unit that ships whole or not at all, as layer 13's slices do, and W6.9 is its own pull request after it. I read the 53 hours as not including W6.10 (8 hours); that is one of the points to confirm in W6-Q27.

### Docs page plan

`docs/serve.md` is written in this pull request as "specified, not built" with the four parts, the route table, the commands, the words and codes, the limits and the open questions. In the build pull requests: `docs/interface.md` (the page may send requests to its own backend), `docs/security.md` (the backend's guards, the token, the limits), `docs/architecture.md`, `docs/exit-codes.md`, `docs/rules.md` (`serve_request`, the never list), `docs/testing.md`, `docs/status-log.md`, `adapters/NOTES-w6.md` (the browser facts: `Origin` on same-origin non-GET requests, fetch metadata to potentially trustworthy URLs, private network preflights, with links and dates, and the by-hand results), `serve.rules.example.yaml`, and the example rules of the three adapters.

### Open questions for the owner (W6-Q1 to W6-Q28), with the owner's answers of Nov 12

Each had a proposed answer. The owner answered W6-Q1 to W6-Q27 on Nov 12: all as proposed except W6-Q12, W6-Q15, W6-Q22 and W6-Q27, where the item now holds the owner's answer. Each item ends with its status. W6-Q28 came up while applying W6-Q12 and was answered later on Nov 12 (approved as proposed).

1. **W6-Q1. The workstream names.** I read W4 as the chat with Claude Code, Kiro and OpenCode, W5 as the queue with the intake step, W6 as this backend and W7 as the login for a deployed interface (proposed). The repo does not define them; tell me if the numbers mean something else. **Answered Nov 12: approved. W4 is the chat, W5 the queue with intake, W6 the backend, W7 the deployed interface with login.**
2. **W6-Q2. Does every request get a rules check?** Yes: each request is checked as `serve_request`, stricter than the command line, where `queue add` asks no rules; `kill.on` is the one exemption, because an emergency stop does not wait for a rule (proposed). Or only where the command line asks (then queue writes need no rule). **Answered Nov 12: approved as proposed.**
3. **W6-Q3. The kill switch and the page.** While the switch is on or unknown every write and run route is refused, reads and `kill.on` work, and the page can never turn the switch off (proposed). Or the page may turn it off (not proposed: a leaked token could then undo the emergency stop). **Answered Nov 12: approved as proposed.**
4. **W6-Q4. Showing the token.** Rule 2 says never print secrets. `serve token create` and `rotate` print the token once, only on a terminal (proposed). Or they write it to a 0600 file that the owner reads and deletes. **Answered Nov 12: approved as proposed.**
5. **W6-Q5. How long a token lives and where the page keeps it.** 30 days by default, 90 at most, and the page keeps it in memory so a reload asks again (proposed). Or `sessionStorage`, which survives a reload but can be read by any script in the page, and which the page tests forbid today. **Answered Nov 12: approved as proposed.**
6. **W6-Q6. The page comes from the backend.** `umwayi serve` serves `ui/dist/index.html` from its own origin, so there is no CORS (proposed). Or the page is opened from disk and the backend allows the origin `null`, which every sandboxed frame and `data:` page also has (not proposed). **Answered Nov 12: approved as proposed.**
7. **W6-Q7. Which `Host` is accepted.** Only `127.0.0.1:PORT` (proposed). Or `localhost:PORT` too, which may resolve to `::1` where nothing listens. **Answered Nov 12: approved as proposed.**
8. **W6-Q8. `Origin` on `POST` and `DELETE`.** Required (proposed), so a `curl` call without it is refused and scripts use the command line. Or a second token class for scripts. **Answered Nov 12: approved as proposed.**
9. **W6-Q9. The default port.** 8765, and `--port 0` takes a free one (proposed). Or a random port every start. **Answered Nov 12: approved as proposed.**
10. **W6-Q10. Reads.** A read is rules-checked and logged like a write (proposed, the owner's "every request"). Or reads skip the rules check and the entry, which cuts the logbook volume. **Answered Nov 12: approved as proposed. The logbook volume is to be looked at again after the build (KNOWN-LIMITS 201).**
11. **W6-Q11. Requests with no valid token, and requests turned away by the rate limit.** Counted in one summary entry a minute (proposed). Or one entry each, which any local process could use to fill the logbook. **Answered Nov 12: approved as proposed.**
12. **W6-Q12. Answering Ask me first in a chat from the page.** The page can only reject. Approvals stay at the terminal until the page's threat model has been tested by hand. (The proposal was that the page could also allow; it is replaced.) **Answered Nov 12: changed by the owner.** Applied in W6.R9.8 and W6.R9.12, KNOWN-LIMITS 211; how an approval reaches a web chat is W6-Q28.
13. **W6-Q13. The idle stop.** A chat with no request for 10 minutes is stopped (proposed). Or never, or a different time. **Answered Nov 12: approved as proposed.**
14. **W6-Q14. One chat at a time.** Yes, the run lock allows it (proposed, it is how it is today). **Answered Nov 12: approved as proposed.**
15. **W6-Q15. Who asks the intake questions.** A fixed list of questions with a pure judge of "clear", no model. An intake written by an AI helper becomes an option in the W5 spec. **Answered Nov 12: approved with that change.** Applied in W6.R10.4.
16. **W6-Q16. When the intent stays unclear.** After 8 rounds nothing is added and the owner may add a decision by hand (proposed). Or the unclear intent is added as a decision automatically. **Answered Nov 12: approved as proposed.**
17. **W6-Q17. Touching `agents.py` and `budget.py`.** W6.7 and W6.8 change the largest and most sensitive module with goldens recorded before the change and no change of behaviour (proposed). Or the backend gets its own copy of the chat steps, which breaks "never a second copy" and is not proposed. **Answered Nov 12: approved as proposed: goldens first, no change of behaviour, one pull request each.**
18. **W6-Q18. Property based tests without a package.** Seeded generators and a shrinker in the standard library (proposed). Or `hypothesis` as a test-only package, which breaks "the normal suite stays standard library only". **Answered Nov 12: approved as proposed.**
19. **W6-Q19. Rule 5 is already out of date.** It says no module of the core package imports a network library, but `umwayi/telemetry.py` does (allowed by name in the guard tests), and `umwayi/serve.py` will too. I did not change rule 5 in this pull request. Proposed: reword it to name the two loopback servers and say they import the network modules only inside the function that starts them. **Answered Nov 12: approved as proposed, and the edit is made in the pull request that builds `umwayi serve`, not now.**
20. **W6-Q20. The other layer 12 sentences.** Only rule 10 and 12.R17.6 are reworded now; 12.R2, 12.R11 and "The view only looks" are read with the change by a pointer (W6.R2.6). Proposed: edit them in the pull request that builds `umwayi serve`. Or edit them now. **Answered Nov 12: approved as proposed: both edits (rule 5 in W6-Q19, these layer 12 sentences) are made in the pull request that builds `umwayi serve`, not now.**
21. **W6-Q21. The public site.** It sends nothing to any backend (my reading of "the page"; proposed). Or it may call a local backend, which needs CORS and a private network preflight and is not proposed. **Answered Nov 12: approved as proposed.**
22. **W6-Q22. W7.** W7 version 1 is login plus the public site with sample data and does not control a local backend. A relay is decided after Dec 3. **Answered Nov 12: changed by the owner** (the proposal was to settle the shape of remote control now). Applied in W6.R12 and KNOWN-LIMITS 212.
23. **W6-Q23. The numbers of W6.R14.** 16 handlers, 4 long polls, 10 requests a second overall (burst 30), 5 token failures a minute, a 10 second request deadline, 25 second long poll, bodies up to 9000 bytes, 500 queue rows, a chat idle stop at 10 minutes, a permission wait of 300 seconds, 6 chat starts an hour (proposed). They are guesses; the build measures the logbook cost per append and may change the rates. **Answered Nov 12: approved as proposed.**
24. **W6-Q24. Which platforms chat over the web first.** Claude Code and Kiro over ACP; OpenCode when 10.48 builds its ACP chat (proposed). **Answered Nov 12: approved as proposed.**
25. **W6-Q25. One server per root.** Yes, `.umwayi/serve.lock` (proposed). Or several ports. **Answered Nov 12: approved as proposed.**
26. **W6-Q26. Later routes.** `decision reopen` and `petition` may be added with the owner's approval; `publish-draft`, `run`, `schedule install`, `autonomy record` and everything on the never list may not (proposed). **Answered Nov 12: approved as proposed.**
27. **W6-Q27. Build order, hours and dates.** W6.1 to W6.6 plus W6.9 first, about 53 hours. W6.7 and W6.8 (the chat refactors, 13 hours) wait until W4 starts. The owner sets the dates after UI.7 merges. **Answered Nov 12: changed by the owner.** Applied in tasks.md and the hours table above. I read the 53 hours as leaving out W6.10 (8 hours), which follows as its own pull request; please say if W6.10 should be inside the first batch.
28. **W6-Q28. How an approval reaches a web chat (new, from applying W6-Q12).** The console of `umwayi serve` shows the same `Allow once? [y/N]` prompt as a command line chat and reads the answer from its own standard input when that is a terminal; with no terminal the request is rejected (proposed). Or an approval is a command in a second terminal (a new command and a pending record, more to build and to guard). Or there is no approval at all for now, so an Ask me first in a web chat is always rejected and a chat can only use tools that a Yes rule allows. **Answered Nov 12 (owner): approved as proposed.** An approval for an Ask me first request in a web chat is given at the console of `umwayi serve` with the prompt `Allow once? [y/N]`; with no terminal attached the request is rejected. The page can still only reject (W6-Q12). Nothing of it is built in W6.1 to W6.6; it belongs to the chat routes (W4).

Answers (owner, Nov 12), recorded as given:

- Approved as proposed: W6-Q1 (W4 chat, W5 queue with intake, W6 backend, W7 deployed interface with login), Q2, Q3, Q4, Q5, Q6, Q7, Q8, Q9, Q10 (revisit the logbook volume after the build, KNOWN-LIMITS 201), Q11, Q13, Q14, Q16, Q17 (goldens first, no behaviour change, one pull request each), Q18, Q19 and Q20 (both edits are made in the pull request that builds serve, not now), Q21, Q23, Q24, Q25, Q26.
- Changed by the owner: **Q12** the page can only reject an Ask me first inside a chat, and approvals stay at the terminal until the page's threat model is tested by hand; **Q15** the intake step uses a fixed list of questions and a pure judge of "clear", no model, and an AI written intake becomes an option in the W5 spec; **Q22** W7 version 1 is login plus the public site with sample data and does not control a local backend, and a relay is decided after Dec 3; **Q27** the build order is W6.1 to W6.6 plus W6.9 first (about 53 hours), W6.7 and W6.8 wait until W4 starts, and the owner sets the dates after UI.7 merges.
- Answered later on Nov 12: **W6-Q28**, raised while applying Q12: approved as proposed (the console of `umwayi serve`, the prompt `Allow once? [y/N]`, rejected with no terminal attached).

Where each change landed: Q12 in requirements W6.R9.1, R9.5, R9.8 and R9.12, this file (the chat section, the threats table), tasks W4, `docs/serve.md` and KNOWN-LIMITS 196 and 211; Q15 in W6.R10.4 and the intake section above; Q22 in W6.R12, the W7 section above, tasks W7 and KNOWN-LIMITS 212; Q27 in the hours section above and in tasks.md.

## Goal orchestration (W9): `umwayi goal` (spec in the W9.0 pull request, tasks.md W9.0; built only after the owner approves it)

This section is added at the end of the file so it merges cleanly with the other branches. It designs requirements W9.R1 to W9.R23. Nothing is built. It reuses what exists and adds one family of modules (`umwayi/goal*.py`), three small options on `agent run` (W9.6), and a docs script (W9.9) that is useful on its own.

### The owner's words and where each lands

| the owner's words | where it lands |
| --- | --- |
| `umwayi goal`: the owner gives a goal, the system splits it into task packets, runs them one at a time through umwayi's own gate, and reports | W9.R3 (the commands), W9.R5 (the split), W9.R7 and W9.R8 (the runs), W9.R20 (the report); "umwayi's own gate" is `rules.check_and_log` plus `umwayi agent run`, never a second path |
| the owner approves and merges | `goal approve` (needs a terminal), W9.R9 (approvals), W9.R17 (the system observes a merge and never makes one) |
| the guide splits goals and checks results | the planning run and the check run of one `agents.yaml` agent (W9.R5, W9.R8.6); it writes nothing |
| builders do one task each | W9.R8.2; a builder run is one `agent run` for one packet |
| one task gets one worktree, made by umwayi from the newest main, a fresh helper session per task, no helper in a shared checkout (the owner's rule of Nov 12, core) | W9.R8.1 and W9.R8.9 to W9.R8.16; the git list gains `worktree add` and `worktree remove`; `agent run --workdir` takes only a path umwayi made (W9.6b); "The worktree of a task" below |
| a tester that is not the builder checks each result | W9.R2.2 (the names differ, tested for every pair), W9.R8.5 (a verdict for every check, parsed strictly) |
| packet: goal, context files, acceptance checks, where the outcome is recorded, size about 60 builder minutes, model and effort chosen by the owner, files the task may touch | W9.R4.1 (the table of the ten fields); size 15 to 90, the owner's model, effort and budget, blank until approved |
| states queued, running, in review, needs owner, merged, failed, stopped | W9.R6 (a closed transition table and a closed list of reason words) |
| pitfall 1 to 7 | W9.R9 to W9.R15, each with a test and planted faults; the table "Pitfalls: requirement, test, planted fault" below |
| every start passes the rules check, fail closed, exit codes 0, 2, 3, 64 unchanged | W9.R1.1, W9.R1.2, W9.R7 |
| every state change is a logbook entry | W9.R13.1 (the entry is the change, written before the files), W9.R18 |
| the kill switch stops all goals | W9.R16 |
| the owner merges, never the system | W9.R1.5, W9.R17, the git list below, a code guard |
| Python standard library only | W9.R1.6; `git` and `umwayi agent run` are programs it starts, not packages |

What I decided where the words left room, each asked as a question at the end: tester and guide must differ from the builder by agent name (W9-Q2); each task has its own git worktree, made by umwayi from the newest main (W9-Q3, superseded by the owner's rule of Nov 12); a task waits for the merge of the one before it, so a run does one task (W9-Q4); a failed task halts the goal with no retry (W9-Q5); what counts as progress and as an error (W9-Q6); the deadlines of approvals (W9-Q7); the owner commands need a terminal (W9-Q9); the shared docs files are rebuilt by the system as the last step of a goal (W9-Q10); scope is checked after the run and not during it (W9-Q11).

### Facts read in the code of main at 508a1f8 (Nov 12 2026)

- **`agents.run_agent(root, name, prompt, clock, agents_file)`** is what `umwayi agent run NAME -` calls. Its steps are the kill switch, the rules (`agent_run`), the run lock, the gate checks, the budget reservation (`budget_check`), the argument list from the platform table, the start entry, the start, and a one-second watch (`_tick`: kill switch, `logbook.check_writable`, the governor's cap, the agent's `timeout_minutes`, default 30, up to 720). SIGTERM stops the agent group, settles the budget and exits 2. The prompt is read from standard input (`read_prompt`, at most 100 KB) and is never logged. In run mode the agent's standard output is inherited (`stdout=None`), so a parent that gives the child a pipe reads the agent's output lines.
- **`Agent` has no `model` or `effort` field** except for OpenCode (`provider`, `model`), and `build_argv` makes the argument list from a fixed table with an allow-list (`_assert_allowed`). So W9 must add `--model` and `--effort` there for Claude Code and Kiro (adapters/NOTES-w9.md). An OpenCode agent is refused by `agent run` today (step 5a), so OpenCode is not a builder until task 10.48 and a non-interactive ACP run exist.
- **`rules.check_and_log(action_text, rules_path, root, when, kill_state=...)`** gives the decision and whether it was logged; a Yes that cannot be logged becomes Ask me first. `NEVER_AUTONOMY` holds `agent_run`, `budget_check`, `acp_permission` and others; `goal_start` joins it.
- **`taskqueue.add_once(root, kind, title, recommendation, when)`** adds an open row unless one with the same kind and title is open, and returns `(row, added)`. It writes its own logbook entry. It is how every Ask me first becomes visible today.
- **The budget ledger** is the logbook: `budget.read_ledger(root)` returns reserves and settles by run id; `budget.fit` checks a reservation against the day limits; the placeholders are `per_run` 100 UU and `per_day` 500 UU.
- **`kill.state(root)`** is `off`, `on` or `unknown`; `runlock.held(root)` is a context manager that raises `RunLockBusy`; `logbook.append`, `logbook.check_writable` and `logbook.read_checked_chain` are the writer, the pre-check and the tamper-checked reader; `fsutil.atomic_write(path, data, mode)` and `fsutil.read_regular(path, limit)` are the file functions; `acp.safe_text` makes agent text safe for a terminal.
- **`umwayi/report.py` already runs one fixed `git log` command** by argument list (layer 6), so `git` as a program the core starts is not new; what is new is three writes (`git worktree add -b`, `git worktree add --detach` and `git worktree remove`) and the checks that make them safe.
- **`git worktree`** (git-scm.com, read Nov 12; adapters/NOTES-w9.md): a linked worktree shares everything with its repository except per-worktree files such as HEAD and the index; `add -b` refuses a branch that already exists; `add --detach` makes a worktree with no branch; `remove` refuses an unclean worktree unless `--force` is given; `list --porcelain` is the machine readable list.
- **`agents._workdir_problem`** requires an agent's `workdir` to be an absolute existing folder that is neither the umwayi root, nor inside it, nor containing it. Today a working folder is fixed per agent in `agents.yaml`, and `agent run` has no way to name another one. That is why the worktree root of W9 is a sibling folder outside the umwayi root, and why `--workdir` must apply the same rule.
- **`docs/status-log.md` and `docs/KNOWN-LIMITS.md` are edited by hand in almost every pull request,** which is why they conflict (PR 58 and PR 62 are open now and both touch docs). `tests/test_docs.py` checks every `docs/**/*.md` for links and em dashes, checks the four parts and 300 lines only for direct children of `docs/`, and checks that direct children can be reached by links. The part files therefore live outside `docs/`, in `docs-parts/`: a part under `docs/` would be scanned with its own folder as the base of every relative link, and would need nothing a part has. The build checks its own output for the two things a part can break (a link that does not resolve, an em dash) with a small checker of its own, because the core cannot import from `tests/`; a differential test runs `tests.test_docs.check` on the built output and requires the two to agree on 60 generated sets of parts.

### The picture

```
owner                        umwayi goal (the supervisor, a program)                         AI helpers (agents.yaml)
  |  goal start "TEXT"  -----> rules: goal_start -> agent run guide (stdin prompt) ------------> guide: prints UMWAYI-PLAN <nonce> {...}
  |                            parse_plan (strict), checks, plan.json, one entry, approval record (7 days)
  |  goal approve (terminal)-> roles, model, effort, budgets, packet hashes; tasks queued; one entry
  |  goal run -----------------> for the next task whose turn has come:
  |                              kill switch -> rules goal_start -> checks -> budget cap -> start entry
  |                              git worktree add -b branch PATH BASE (BASE = main now) -> agent run builder --workdir PATH ----> builder works in its own worktree, commits, writes its 2 files
  |                              watch every second: kill, log writable, judge(progress, errors), budget
  |                              scope check (git, read only) -> agent run tester -----------------> tester: UMWAYI-RESULT <nonce> {...}
  |                              agent run guide check ------------------------------------------> guide: UMWAYI-CHECK <nonce> {...}
  |                              entry: running -> in review; report; return
  |  merge (the owner) -------> goal run: git merge-base --is-ancestor TIP main -> merged (observed) -> next task
  |  goal merged G T (terminal) -> the owner's declaration for squash merges
  |  goal docs build (last step) -> docs/status-log.md, docs/KNOWN-LIMITS.md from the part files
```

### Files

| file | what | notes |
| --- | --- | --- |
| `umwayi/goalpacket.py` | the packet, `parse_plan`, the protected list, `scope_violations`, the state table, the roles rule | pure; imports `json`, `re`, `hashlib`, `dataclasses` and `posixpath` only |
| `umwayi/goalwatch.py` | `signature`, `judge`, `expired`, the deadline and approval records | pure; no clock, file or process |
| `umwayi/goallog.py` | the event shape, `read`, `Writer` (append, probe, cap), the bounded line reader | the only code that touches an event log |
| `umwayi/goalstate.py` | the state files, the strict parser of `umwayi goal` entries, `repair`, the write order | uses `logbook`, `fsutil`, `taskqueue` |
| `umwayi/goalbudget.py` | the ledger window, `spent`, `cap` | pure over a `budget.Ledger` |
| `umwayi/goalgit.py` | the list of git argument lists, `run_git`, `worktree_path` and the path checks, the worktree lifecycle | the only place git is started; a code guard checks it (W9.6b) |
| `umwayi/goalrun.py` | the supervisor: the start steps, the child, the watch, the roles, the prompts, the verdict parsers | the only place an AI helper is started |
| `umwayi/goal.py` | the `goal` commands and their exit codes | imported inside `_cmd_goal` |
| `umwayi/goaldocs.py` | part files, `build`, `check`, numbering, the migration | standard library only |
| `umwayi/agents.py`, `umwayi/cli.py`, `umwayi/budget.py` | `agent run --cap-uu N --model M --effort E` (W9.6) and `agent run` and `agent check --workdir PATH` for a path umwayi made (W9.6b) | goldens first, no change without the options |
| `umwayi/rules.py` | `goal_start` in `NEVER_AUTONOMY` | one word, its test and its line in `docs/rules.md` |
| `docs-parts/status-log/`, `docs-parts/known-limits/` | the part files, one pair per task | W9.9 and the tasks |
| `tests/goal/` | `gen.py`, `fake_agent.py`, `fakeroot.py`, `test_*.py` | standard library only |
| `.umwayi/goals/G-0007/` | the state of a goal | in `.gitignore`, mode 0700 |
| `.umwayi/goal.lock` | the supervisor lock | in `.gitignore`, mode 0600 |
| `ROOT-worktrees/` (a sibling folder of the umwayi root) | the worktrees: `g-0007-t-02/`, `g-0007-plan/` | mode 0700, outside the root, made by umwayi (W9.R8.11) |
| `goal.rules.example.yaml` | the example rules for `goal_start` | later; the owner copies lines |
| the three adapters' example rules | deny the owner commands to an AI helper | text matching, KNOWN-LIMITS 12 |

### The packet as the guide writes it, and as it is approved

The guide's `UMWAYI-PLAN` object (one line, here wrapped):

```
{"tasks": [
  {"goal": "Add the pure packet parser with its tests.",
   "context": ["umwayi/taskqueue.py", ".kiro/specs/umwayi-os/requirements.md"],
   "checks": ["A plan with an unknown field is refused with the word field.",
              "A plan of nine packets is refused."],
   "size": 60,
   "files": ["umwayi/goalpacket.py", "tests/goal/test_packet.py"]},
  ...
]}
```

There is no `id`, `outcome`, `model`, `effort` or `budget_uu` in the guide's object; one of them present is a refusal (`field`). After `approve` the stored packet is:

```
{"id": "T-01", "goal": "...", "context": [...], "checks": [...],
 "outcome": {"status_file": "docs-parts/status-log/G-0007-T-01.md", "limits_file": "docs-parts/known-limits/G-0007-T-01.md", "branch": "umwayi/g-0007-t-01"},
 "size": 60, "model": "sonnet", "effort": "high", "files": [...], "budget_uu": 30}
```

The ten fields and no others. The roles (builder, tester, guide) are the goal's, kept in `goal.json`, not in a packet. The packet's `sha256` is kept beside it in the task file: the SHA-256 of the canonical JSON of the packet (sorted keys, no spaces). `scope_violations(changed, allowed)` works on `posixpath.normpath` forms: a changed path is allowed if it equals an allowed file, or sits under an allowed folder (an entry ending in `/`), or is one of the task's two files; a path that is absolute, has `..` after normalizing, has a backslash or a NUL, or is not valid UTF-8 is always a violation; comparing is case sensitive and also fails a path that equals an allowed one only by case (a case-insensitive file system could alias it). The protected list is compared the same way and also by `casefold`.

### The prompts (fixed templates in `goalrun.py`)

All four are fixed text with slots, never built from text the AI helper wrote earlier, and go on standard input. Each ends with a line `Nonce: <16 hex characters>`. Slots hold packet text, the branch and counts only.

- **Planning prompt:** "You are the guide. Split this goal into 1 to 8 tasks. Each task: one sentence of goal, up to 12 files to read, 1 to 8 acceptance checks that someone who did not write the code can answer pass or fail, a size of 15 to 90 minutes (aim for 60), and the files it may touch. Do not write any file. Do not choose a model, an effort or a budget. Print exactly one last line: `UMWAYI-PLAN <nonce> <json>`." The goal text is in a block fenced and labelled as the owner's text.
- **Builder prompt:** the packet's goal, context, checks, files, the branch name ("you are on it; commit on it; do not push; do not merge; do not touch other files"), the two files it must write with their formats (W9.R14.2), "when you are done, stop", and the nonce.
- **Tester prompt:** the packet's goal and numbered checks, the branch and its tip, "check each one with your own tools; change no file; if you cannot tell, say unclear", and "print exactly one last line: `UMWAYI-RESULT <nonce> {"checks":[{"n":1,"verdict":"pass","evidence":"..."}]}`".
- **Check prompt:** the packet, the number of files changed, the tester's verdict words and evidence, "answer accept, reject or unclear", and "print exactly one last line: `UMWAYI-CHECK <nonce> {"verdict":"accept","reason":"..."}`".

The nonce is made by `secrets.token_hex(8)` for each run, kept in memory, and written to no file and no entry. A result line with another nonce, or none, is not read. A builder never sees a tester's or guide's nonce because they do not exist until after it is gone. It stops a forged line left in the repo or in an earlier run from being read, and does not stop a tester that is talked into printing one (KNOWN-LIMITS 214 and 227).

### The states and what moves them

```
                        approve               start (7 steps)             exit 0 + scope + tests + guide accepts
 (plan) ----------------> queued ------------------------> running --------------------------------------------> in review --(owner merges, observed or declared)--> merged
                             |  ^                              |  \ failed (builder, outcome, scope, tests, rejected, stalled, looping, budget, timeout, readonly)
              ask/busy/dirty |  | owner answers yes            |   \ stopped (kill, owner, log, signal, supervisor)
              /config        v  |                              |    \ needs owner (ask, unclear, config)
                        needs owner <--------------------------+
                             | deadline (24 h) or answer no
                             v
                          stopped (unanswered or owner)
```

- A reason word is chosen by exactly one function for each cause (`goalrun.reason_for(event)`), tested for every cause in the lists of W9.R6.2.
- **When a task fails or stops, the goal halts:** `run` writes the report, exits 2 (or 3), and starts nothing more. Later tasks stay `queued`.
- **`needs owner` and the queue.** Entering it adds one queue decision through `add_once`, before the change. The title is fixed text with ids: `Goal G-0007 task T-03 needs you (unclear)`; the recommendation says what to do and that answering the queue item does not start anything; the real answer is `umwayi goal answer`. Leaving it closes the row with the answer text `Yes` or `No: ...` through `taskqueue.answer`/`close`, the functions the command line uses.

### The supervisor, step by step (`goal run G-0007`)

1. Arguments (64). The root is a normal folder.
2. `goal.lock` (3 if held).
3. The tamper check of the logbook (`read_checked_chain`); then the strict parse of `umwayi goal` entries (W9.R18.3). Either failing is exit 2 and nothing starts.
4. Repair the state files from the logbook (W9.R13.5).
5. `expired(approvals, now)`: every deadline that passed is denied and logged (W9.R9.5).
6. A lost supervisor is found: any task `running` with `goal.lock` free is made `stopped` (`supervisor`).
7. The kill switch (W9.R16). On: mark every active goal stopped, exit 3.
8. Observe merges for tasks `in review` (W9.R17.2).
9. Pick the task: the first not `merged` in plan order. If it is `queued` and every earlier one is merged, go on. If it is `in review`, `needs owner`, `failed` or `stopped`, report and return (0 for in review, 3 for needs owner, 2 for the others).
10. Run the task: the seven start steps (W9.R7, which include the worktree), then builder, scope check, tester, guide's check (W9.R8), all in the task's worktree. Each run is one child; each leaves its own entries; the loop below watches each.
11. Report (W9.R20), return.

**The watch of one child.** Start `Popen([sys.executable, "-m", "umwayi", "agent", "run", NAME, "-", flags...], stdin=PIPE, stdout=PIPE, stderr=DEVNULL, start_new_session=True, env=...)` and feed the prompt by a thread (as `_feed` does). The child gets the supervisor's environment unchanged; `agent run` builds the AI helper's own environment from it (the credential names removed, 10.R12.6). A reader thread takes lines with the bounded reader of W9.R12.5 and puts events on a queue. The main loop wakes every second and: checks the kill switch, `logbook.check_writable` and the goal folder probe; every 30 seconds takes the work fingerprint; drains the events (writes `output` aggregates every 5 seconds, `error` per error line); calls `judge`; if `judge` says `Stop`, runs the stop of W9.R10.5; if the child exited, reads its exit code and goes on. A `poll` event is written every 30 seconds and is not real (W9.R11.2). Everything the loop writes goes through `goallog.Writer`, which raises on any failure; the loop's one handler for that exception is the stop of W9.R13.2.

### The git commands (`goalgit.py`, the whole list)

All run as `["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-C", DIR, ...]` with `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_NOSYSTEM=1`, `GIT_TERMINAL_PROMPT=0` and no shell, with a 20 second timeout and an output cap of 1 MB. `DIR` is the umwayi root for the commands about the repository and the task's worktree for the commands about its tree.

| name | DIR | arguments | writes | used for |
| --- | --- | --- | --- | --- |
| `is_repo` | root | `rev-parse --is-inside-work-tree` | no | approval, every start |
| `has_main` | root | `rev-parse --verify --quiet refs/heads/main` | no | approval |
| `base` | root | `rev-parse refs/heads/main` | no | BASE, read at each start |
| `has_origin_main` | root | `rev-parse --verify --quiet refs/remotes/origin/main` | no | the `stale` check |
| `behind_origin` | root | `rev-list --count refs/heads/main..refs/remotes/origin/main` | no | the `stale` check |
| `branch_exists` | root | `rev-parse --verify --quiet refs/heads/BRANCH` | no | the `leftover` check |
| `worktree_list` | root | `worktree list --porcelain -z` | no | leftover, no sharing, the cap, the sweep |
| `worktree_add` | root | `worktree add -b BRANCH PATH BASE` | **yes** | a task's worktree and branch |
| `worktree_add_detached` | root | `worktree add --detach PATH BASE` | **yes** | the plan's worktree |
| `worktree_remove` | root | `worktree remove PATH` | **yes** | cleanup after merged, an unused worktree, the plan's |
| `toplevel` | worktree | `rev-parse --show-toplevel` | no | the path check |
| `common_dir` | worktree | `rev-parse --git-common-dir` | no | the path check |
| `head` | worktree | `rev-parse HEAD` | no | the tip, the fingerprint |
| `status` | worktree | `status --porcelain=v1 -z --untracked-files=all` | no | clean tree, fingerprint |
| `count_ahead` | worktree | `rev-list --count BASE..HEAD` | no | at least one commit |
| `changed` | worktree | `diff --name-status -z --no-ext-diff --no-renames BASE HEAD` | no | the scope check |
| `is_ancestor` | root | `merge-base --is-ancestor TIP refs/heads/main` | no | merged, observed |
| `commit_exists` | root | `cat-file -e SHA^{commit}` | no | merged, declared |

`BRANCH`, `BASE`, `TIP` and `SHA` match a fixed pattern before they enter an argument list (`umwayi/g-\d{4,}-t-\d{2}`, and 40 or 64 hex characters); `PATH` comes only from `worktree_path` and passes the checks of "The worktree of a task". Words such as `main` are literals. A guard test reads the module and compares every argument as a whole word: it fails if any argument list other than these 18 exists, if any argument is `push`, `merge`, `rebase`, `pull`, `fetch`, `reset`, `clean`, `checkout`, `switch`, `branch`, `tag`, `stash`, `commit`, `prune`, `lock`, `move`, `repair`, `--force` or `-f` (`merge-base` is a different word and is allowed in `is_ancestor` only), or if any of the three writes appears more than once. `git` may still read the repo's own config (filters, `diff.external` are neutralized by the flags and `--no-ext-diff`; others are a known limit, KNOWN-LIMITS 221).

### The worktree of a task

```
<parent>/umwayi-os/                 the umwayi root: rules.yaml, queue.md, LOGBOOK.md, .umwayi/, and the repository's .git
<parent>/umwayi-os-worktrees/       the fixed worktree root, mode 0700, made by umwayi
    g-0007-plan/                    detached at BASE: the guide's planning run; removed when the plan is decided
    g-0007-t-01/                    branch umwayi/g-0007-t-01 at BASE_1: builder, then tester, then the guide's check
    g-0007-t-02/                    branch umwayi/g-0007-t-02 at BASE_2, made after t-01 was merged
```

**`worktree_path(root, goal, task)`** is pure. It takes the real path of the umwayi root, ids that matched `^G-\d{4,}$` and `^T-\d{2}$`, and returns `realpath(root) + "-worktrees/" + "g-0007-t-02"`. `check_path(root, path)` then requires: the path equals that string; its parent exists, is a real folder, not a link, owned by the owner, mode 0700, and is neither the umwayi root nor inside it; the path itself, when it exists, is a real folder and not a link. `agent run --workdir` calls the same two functions (the agent code imports them, not a copy) and adds `rev-parse --show-toplevel` equal to the path and `--git-common-dir` equal to the root repo's.

**Making one (inside start step 8, after the start entry):**

1. Read BASE with `base`, and check `has_origin_main` and `behind_origin` (`stale` if above 0). BASE is in the start entry, so the record comes before the write.
2. Check `leftover` once more (`worktree_list`, `branch_exists`, the folder, the task files of every goal, the cap of eight): time has passed since step 6.
3. Make the worktree root if it is missing (one folder, mode 0700, the parent must exist).
4. `worktree_add`. Failure: `needs owner` (`config`), nothing else is touched.
5. Verify: `toplevel` equals the path, `common_dir` equals the root repo's, `head` equals BASE, `status` is empty. Failure: the unused worktree is removed (`worktree_remove`, no force) and the task is `needs owner` (`dirty`).
6. Write the `worktree` event and the entry "Worktree made".
7. `agents.check_agent` with `--workdir` for the helper about to start (the gate checks are those of this folder). Failure: remove the unused worktree, `needs owner` (`config`).
8. The `started` event, then the child with `--workdir PATH`.

**Using it.** The builder runs in it. When the builder exits 0 the supervisor runs the scope check against BASE and takes the tip. The tester and the guide's check run in the same worktree, after `status` is empty and `head` equals the tip the scope check passed (`dirty` otherwise). Nothing ever runs two helpers in it at once (the run lock).

**Ending it.**

| the task | the worktree |
| --- | --- |
| `merged` | removed after the `merged` entry, when `status` is empty, by `worktree_remove` without force; if git refuses it stays and is listed; the branch stays |
| `failed`, `stopped`, `needs owner`, `in review` | stays, with its work, until the owner removes it or the task is merged |
| any state, and no builder `started` event ever written | removed at once (the supervisor's undo, or the next command after a crash), when clean at BASE |
| the plan's | removed when the plan is approved, denied or discarded; kept and listed when the guide changed it (`readonly`) |

`status` and `report` list the worktrees that are left over (a path and the command to remove it) and the disk each uses (the sum of file sizes, computed only for listed worktrees and capped at 10 000 files). Removing one by hand with `git worktree remove` is always allowed; the next command sees it gone.

**Why a sibling folder.** `agents._workdir_problem` refuses a working folder that is the umwayi root or inside it, so that a helper's folder does not hold `rules.yaml`, the logbook or the queue. A worktree under `.umwayi/` would break that rule or need an exception. A sibling folder keeps the rule as it is, and the worktree gets nothing of the root's state: the tracked files of BASE only.

**What a worktree lacks.** Untracked and ignored files of the owner's folder: `node_modules`, build folders, caches, `.env`, local config, a Kiro hook file the owner did not commit. They are not copied or linked. A helper that needs them makes them, and a gate check that needs one fails as `config`. The `.git` metadata (objects, refs, config) is shared with the root repo, so a helper that can run git write commands could change refs of the shared repo; the gate (`rules.yaml`) is what stops that (KNOWN-LIMITS 232).

**Several tasks at once (W9.12) is the only part left to build later.** With `--ahead N` the supervisor would start a task while another is in review, if their `files` do not overlap. Nothing in the worktree design changes for it: each task already has its own worktree.

### The work fingerprint

`SHA-256(head || NUL || the status lines sorted || NUL || for each changed path in the status, sorted: path || NUL || SHA-256 of its bytes (read with a 2 MB cap, a larger file counts its size and mtime))`. Left out: the task's status and limits files, `.umwayi/`, and any path the worktree's `.gitignore` ignores (git does not list them). It is a hash, so it can be stored and compared without keeping a file. Reading the files is read-only. A change in a file between two reads shows as a change, which is progress; a file the tool rewrites with the same bytes does not.

### The event log

`T-02.events.jsonl`, one JSON object per line, at most 4096 bytes, keys exactly `n`, `at`, `kind`, `data`, `crc`:

```
{"n":12,"at":"2026-11-12T10:15:30Z","kind":"error","data":{"sig":"3fa91c20b1c4d5e6"},"crc":"1a2b3c4d"}
```

`crc` is the CRC-32 (`zlib.crc32`) of the canonical JSON of `n`, `at`, `kind` and `data`, in 8 hex characters. It finds a torn or garbled line; it is not a defence against someone who rewrites a line (KNOWN-LIMITS 224). The kinds and their `data`:

| kind | data | real |
| --- | --- | --- |
| `state` | `from`, `to`, `reason`, `recovered` (bool) | yes |
| `started` | `role`, `agent`, `cap_uu`, `pid` | yes |
| `output` | `lines`, `bytes`, `skipped` (counts since the last one) | yes |
| `error` | `sig` | yes |
| `fingerprint` | `changed` (bool), `files` | only when `changed` |
| `approval_requested`, `approval_answered` | `kind`, `answer` (for answered) | yes |
| `check_result` | `n`, `verdict` | yes |
| `skipped` | `line`, `offset`, `length`, `reason`, `sha256` | yes |
| `stopped` | `reason` | yes |
| `worktree` | `action` (`made` or `removed`), `base` (8 hex characters) | yes |
| `poll` | none | no |
| `waiting` | `left_s` | no |

The reader checks each line with one function `valid_event(obj)` and a table of the keys of each kind. `Writer.append` builds the line, appends it with one `os.write` on a file opened `O_APPEND`, and calls `fsync` for `state` and `stopped` events; a short write or any `OSError` raises `LogWriteFailed`. The cap of 8 MB is checked before each write.

### The status text (W9.R11), an example

```
Waiting for you
  Goal G-0007 task T-03 needs you (unclear). Asked 3 h ago, denied in 21 h.
  Answer with: umwayi goal answer G-0007 T-03 yes   (or no)
Goal G-0007  active  (2 of 5 tasks merged, 1 in review)
  Task T-04  running  builder claude-build  started 41 min ago
  Last event: fingerprint changed (3 files), 7 min ago   QUIET for 7 min
  Supervisor: alive (last poll 12 s ago). Builder: running.
  Spent: 12 of 40 UU on this task, 96 of 300 UU on the goal.
  Skipped log lines: 0
Docs: 2 parts not yet built
```

"Last event" is always printed before the supervisor line. If no real event exists yet it prints `Last event: none yet (task started 3 min ago)`. The test compares the text with a golden.

### Approvals, in detail

`goalwatch.Approval` is a frozen record: `kind`, `goal`, `task`, `asked` (UTC seconds), `deadline` (UTC seconds, required, larger than `asked`), `default` (always `"no"`, not settable). `Approval(...)` raises if the deadline is missing or not later than `asked`. `expired(approvals, now)` returns those with `deadline <= now` and no answer. Every goal command begins with `deny_expired(root, now)`: it reads the approvals from the goal files (an approval lives in `goal.json` for the plan, and in the task file for `needs owner`), and for each expired one runs the same transition and entry as an owner `no`, with the entry's reason `unanswered` and the deadline's time in the text. `answer yes` and `approve` call `expired` on their own record first, so they cannot succeed after the deadline even if no command ran in between. The `waiting` events in a running `run` print the countdown; a `needs owner` found by `run` ends the run (it does not wait for the owner inside the process), so the wait is always on the clock and in files, never in a hidden loop.

### The write order and what a crash leaves

| the process stops (or a write fails) | what is on disk | what the next command does |
| --- | --- | --- |
| before step 0 | nothing changed | nothing |
| after step 0 (queue row added) | an open queue row, the old state | nothing; the row is harmless and `add_once` will not add a second |
| after step 2 (the entry is written) | the entry says the new state, the file the old | repairs the file from the entry, adds a `state` event with `recovered` |
| after step 3 (the file is written) | the file is right, the event is missing | adds the event with `recovered` |
| after the start entry, before the child | state `running`, no child | the supervisor is lost: `stopped` with `supervisor` |
| after `worktree add`, before the child | `running`, a worktree, no child | the supervisor is lost: `stopped` with `supervisor`; a worktree in which no builder ever started is removed when clean at BASE |
| during the child | `running`, a child, a worktree | if `goal.lock` is free the supervisor is lost; the child ends by itself (its timeout, kill switch watch) or stays and holds the run lock |
| a failed write at any step | as the row for that step | the same stop (exit 2), the same repair |

`tests/goal/test_failwrite.py` raises at each of these points for each transition and checks the right-hand column, with a fake clock.

### Budget in detail

`goalbudget.spent(ledger_before, ledger_after, agent)` takes the run ids of reserves that appear in `after` and not in `before` for that agent and adds, for each, its settle (`Settle` micros) or its reserve (`Reserve` micros) if no settle exists. `cap(task_left, goal_left, per_run, day_left)` returns `min` of the four in whole UU, rounded down; under 1 means no run. The supervisor stores `before` as the set of run ids when it writes the `started` event, so a restart recomputes the same window. `per_run` and `day_left` come from `units` and `budget` (`budget.fit` is the check the child makes itself; the supervisor's number is only smaller or equal). The three options on `agent run`:

- `--cap-uu N`: a whole number from 1 to `per_run`; above `per_run` is 64. It replaces `per_run` in the reservation and the per-run watch of that run only.
- `--model M`: `^[A-Za-z0-9._:/-]{1,64}$`; Claude Code gets `--model M`, Kiro `--model M` (after `chat --v3 --no-interactive`), OpenCode is refused today by `agent run` anyway.
- `--effort E`: one of `low`, `medium`, `high`, `xhigh`, `max`; Claude Code gets `--effort E`, Kiro `--effort E`; an OpenCode agent gets 64.

The allow-list `_assert_allowed` gets these two flag names and their values as the only new words; a test shows an argument list from a value with a space, a leading dash or a NUL is refused. Goldens come first: the argument lists and entries of runs without the options must be byte-identical after the change.

### The docs parts and the script (`goaldocs.py`)

A status part, `docs-parts/status-log/G-0007-T-02.md`:

```
date: 2026-11-14
pr: none
what: Added the packet parser and its tests (W9.2).
tests: 1990 on Python 3.11

Free text for a human, not copied into the table.
```

A limits part, `docs-parts/known-limits/G-0007-T-02.md`:

```
section: Goal orchestration (W9), found while building W9.2
title: A plan of one packet cannot be split further

The text of the limit, in Markdown, in the same four-sentence style as the others.
```

**Frozen base.** The first change moves the text of today's files into `docs-parts/status-log/00-head.md` (everything above the first table row), `00-rows.md` (the existing rows) and `00-tail.md` (from "A blank count means" on), and `docs-parts/known-limits/00-base.md` (the whole of today's file). `build` writes: head, then the rows of the status parts newest first (by `date`, then `pr`, then id), then the old rows, then the tail; and for limits, the base, then for each new `section` in the order of the first part that uses it a heading `## <section>`, then each of its parts as `### N. <title>` and the body. A status part with `pr: none` shows `see the pull request`. A test builds from the base alone and compares with `git show HEAD:` of the real files. Numbers: a part without `number:` gets `max(212, the largest number in the base and the parts) + 1`, in the order of `date` then id, and `build` writes `number: N` into the part. A part whose number collides with another is refused.

**What `build` refuses** (nothing is written, exit 2, a fixed message with the part's file name): a part that does not parse, has an unknown key, has a pipe or em dash in `what` or `title`, has a number it was not given, has a link that does not resolve (the docs checker runs on the built output in a temporary copy first), or two parts with the same id. `check` builds in memory and compares bytes.

**Who runs it.** Not a task. As the last step of a goal (W9-Q10) `umwayi goal docs build` is run by the owner, or by the system on its own `docs/rebuild-G-0007` branch from the newest main through the same fixed git list plus the commit the owner approves; the first batch builds the command only and leaves who runs it to the owner (the recommendation is that the system prepares the branch and the owner opens the pull request, because the system never pushes).

### The logbook entries (W9.R18), exact shapes

```
Source:   umwayi goal
Added:    Goal G-0007 task T-02: queued to running (reason start), role builder, agent claude-build, cap 30 UU
Checked:  Kill switch off. Rules check Yes (goal_start). Packet 3fa91c20 unchanged. Run lock free. Spent 0 of 40 UU.
Not done: The goal text, the prompt and the helper's output were not recorded.
```

```
Source:   umwayi goal
Added:    Goal G-0007 task T-02: running to in review (reason checked), branch umwayi/g-0007-t-02, tip 9f1c2e0a
Checked:  Scope: 3 files, all allowed. Tester kiro-test: 2 of 2 checks pass. Guide claude-guide: accept. Spent 27 of 40 UU.
Not done: No diff, file content or helper output was recorded. Nothing was pushed or merged.
```

```
Source:   umwayi goal
Added:    Approval requested: task T-03 of goal G-0007 needs the owner (reason unclear), deadline 2026-11-13 14:00 UTC
Checked:  Queue row added first. Default answer No.
Not done: Nothing was started and nothing was answered.
```

```
Source:   umwayi goal
Added:    Goal G-0007 task T-02: worktree made, base 9f1c2e0a, branch umwayi/g-0007-t-02
Checked:  main is not behind origin/main. No leftover. Clean at base. Gate checks passed for the worktree. Worktrees in the root: 1 of 8.
Not done: Nothing was pushed or merged. The owner's working copy was not touched.
```

```
Source:   umwayi goal
Added:    Goal G-0007 task T-01: worktree removed after merged (observed)
Checked:  The worktree was clean. git worktree remove ran without force. The branch umwayi/g-0007-t-01 was kept.
Not done: No branch was deleted and nothing was forced.
```

Other shapes: goal planned (`Goal G-0007 planned by agent NAME: 5 packets, 270 minutes, goal text 212 characters sha256 ab12cd34`), plan approved, approval answered or denied (`Approval denied: ... (timed out)`), goal stopped, docs built, merged observed or declared. Every number, id, word and name comes from a pattern in `goalstate.py`; a test builds every combination.

### The fail closed table

| situation | result | what changes |
| --- | --- | --- |
| `rules.yaml` missing or broken | Ask me first, exit 3, the task `needs owner` (`ask`) | one queue row, the check's entry |
| the rules check says No | exit 2, the task `stopped` (`owner`) | the check's entry, the state entry |
| the check could not be logged | exit 2 | nothing |
| the kill switch is `on` or `unknown` | exit 3, goals `stopped` (`kill`) | one entry each |
| the logbook fails its tamper check | exit 2 | nothing |
| a `umwayi goal` entry does not match a shape | exit 2 | nothing |
| the packet file differs from its hash | `needs owner` (`unclear`) | one queue row |
| the plan does not parse or fails a check | exit 2; the goal stays in `plan` with no packets | one entry naming the problem word |
| the run lock is held | retried, then `needs owner` (`busy`) | one queue row after the fifth try |
| the local `main` is behind `origin/main` | `needs owner` (`stale`) | one queue row |
| a worktree, branch or folder of the task is left over, or eight worktrees exist | `needs owner` (`leftover`), exit 3, nothing removed | one queue row |
| a worktree is not clean when a helper is about to start in it | `needs owner` (`dirty`) | one queue row |
| `worktree add` fails, or the new worktree does not check out right | `needs owner` (`config`), the unused worktree removed | the entries |
| `--workdir` is not a path umwayi made | exit 64, nothing starts | nothing |
| the budget cap is under 1 UU | `failed` (`budget`) or goal `stopped` (`budget`) | the entries |
| `agent run` exits 3 | `needs owner` (`ask`) | the queue row `agent run` added, ours |
| `agent run` exits 2 on its own | `failed` (`builder`) | the entries |
| `agent run` exits 64 | `needs owner` (`config`) | one queue row |
| a result line is missing, doubled, or has a bad nonce | `needs owner` (`unclear`) | one queue row |
| the tester or guide changed the tree | `failed` (`readonly`) | the entries |
| the tip changed after the tester | `needs owner` (`unclear`) | one queue row |
| a log or state write fails | the child is stopped, exit 2 | as the crash table |
| the owner command has no terminal | exit 2 | nothing |
| the approval is past its deadline | refused, exit 2; denied and logged | the denial entry |
| `merged --commit` not on `main` | exit 2 | nothing |
| `docs build` finds a bad part | exit 2 | nothing |

### Pitfalls: requirement, test, planted fault

| pitfall | requirement | test module | the planted faults it must catch |
| --- | --- | --- | --- |
| 1 an approval that waits silently | W9.R9 | `test_approvals.py` | no deadline; deadline ignored; timeout answered Yes; queue row skipped; `status` line missing; enforcement only inside `run` |
| 2 a stalled or looping builder | W9.R10 | `test_watch.py` | stall timed from output; 3600 s; three errors; signatures keep digits; judge reads the clock; the child's group not stopped |
| 3 status shows only connected | W9.R11 | `test_status.py` | status from the pid only; a poll counted as real; a future time shown as fresh; helper text in the line |
| 4 one malformed line stalls the log | W9.R12 | `test_log.py` | reader stops at the first bad line; skip not recorded; skip recorded twice; bad text in the record; the logbook made tolerant |
| 5 a failed log write lets work continue | W9.R13 | `test_failwrite.py` | entry after the file; failed event ignored; probe skipped; child left running; repair prefers the file |
| 6 parallel edits of shared files | W9.R14 | `test_docs_parts.py` | a number written twice; order depends on the file system; a part overwrites the base; the scope check does not list the shared files |
| 7 cost grows with autonomy | W9.R15 | `test_budget.py` | cap from the helper's own report; the tester not counted; planning not counted; goal budget checked only at approval; day limits ignored |

### Threats and what meets them

| threat | what meets it | where it is tested |
| --- | --- | --- |
| text in the repo steers the guide, builder or tester (prompt injection) | fixed prompt templates, the nonce, the supervisor's own deterministic checks (scope, tree, budget), the owner's merge; the rest is a known limit | the nonce tests; KNOWN-LIMITS 214 and 227 |
| a builder touches files outside its packet | the scope check after the run; the gate (`rules.yaml`) during it; the protected list | `test_packet.py` (spellings), the scope scenarios |
| a builder runs `umwayi goal approve` or `merged` | terminal needed, example rules deny, `goal.lock`, the run lock | `test_owner_commands.py` |
| a builder pushes or merges | rules (Ask me first for push), the supervisor never does; the owner's merge | the git guard; the example rules |
| a tester that is the builder in disguise | different names enforced; weak independence warned | `test_roles.py` over pairs |
| a forged result line | nonce per run, last line only | `test_verdict.py` |
| a flood of output or one huge line | bounded reader, aggregated events, event cap | `test_log.py`, the fake agent |
| a loop that costs money | the judge, the per-run cap, the task and goal budgets | `test_watch.py`, `test_budget.py` |
| an approval forgotten | deadlines, the queue row, `status` | `test_approvals.py` |
| a crash between a change and its record | the write order and repair | `test_failwrite.py` |
| docs conflicts and numbering races | per-task part files, one builder of the shared files, numbers assigned once | `test_docs_parts.py` |
| git hooks and config run code | `core.hooksPath`, the global config off, `--no-ext-diff`; repo-local config is a known limit | `test_git.py` (a repo with a hook that leaves a marker file: the marker is not made) |
| a helper works in a shared or wrong folder | one worktree per task, `--workdir` takes only a path umwayi made under the fixed root, the path and the repo checked | `test_worktree.py` |
| worktrees pile up and use disk | the cap of eight, a leftover stops the start, cleanup after merged, `status` lists them | `test_worktree.py` |
| a moved branch or a rewritten history after review | the tip is recorded, a changed tip voids the result | `test_merge.py` |
| a second goal or a second supervisor | `goal.lock`, the run lock | `test_files.py` |

### What can go wrong in running (failure modes)

- **The owner is working in the root repo.** A goal never touches the owner's working copy (no `switch`, no `checkout`); it adds a branch and a worktree next to it. The owner's uncommitted files are not in any worktree.
- **The local `main` is old.** A start is refused as `stale` only if the remote-tracking ref `origin/main` shows it is behind; with no remote or an old fetch it cannot know (KNOWN-LIMITS 220).
- **Leftover worktrees.** A failed or stopped task keeps its worktree, and a crash can leave one; the next start for that task is refused as `leftover`, and the cap of eight stops a pile. The owner removes them with `git worktree remove`.
- **The disk.** Each worktree is a full checkout of the tracked files of BASE (KNOWN-LIMITS 229).
- **The local `main` is old.** A merge is not observed until the owner updates it, so the next task waits. `status` says "in review, merge not seen".
- **A squash merge.** `is-ancestor` is false for the branch tip; the owner declares it with `goal merged G T --commit SHA`.
- **A fast child.** A builder that ends with exit 0 and no commit is `failed` (`outcome`) at once.
- **A tester that never answers.** The stall rule stops it at 30 minutes.
- **The ledger window is long.** A run of the same agent from the schedule in the window is counted in the task (KNOWN-LIMITS 218).
- **Two owners' terminals.** `goal.lock` and the run lock arbitrate; the second gets exit 3.
- **The clock moves.** Deadlines use the election clock and `time.time()` once per command; a clock set back never revives an approval, a clock set forward expires approvals early, which is the safe direction.
- **The event log is rewritten by a process of the same user.** The logbook is the record of state (chained); the event log is operational (KNOWN-LIMITS 224).

### Tests (W9.R21), files

`tests/goal/`: `gen.py` (seeded generators, the shrinker), `fake_agent.py`, `fakeroot.py` (a temporary root with a fake `agents.yaml`, `units.yaml`, `rules.yaml` and a git repo), `test_packet.py`, `test_roles.py`, `test_verdict.py`, `test_worktree.py` (the sixteen points of W9.R8: BASE, the owner's copy untouched, `stale`, the path checks, `--workdir`, leftover, dirty, cleanup after merged, no sharing, the plan worktree, what a worktree lacks), `test_watch.py`, `test_log.py`, `test_status.py`, `test_approvals.py`, `test_failwrite.py`, `test_budget.py`, `test_docs_parts.py`, `test_merge.py`, `test_git.py`, `test_kill.py`, `test_entries.py`, `test_files.py`, `test_owner_commands.py`, `test_report.py`, `test_cli.py` (exit codes, the order of the start steps), and `test_samecode.py` (spies: each start calls `kill.state`, `rules.check_and_log` and the child in the order of W9.R7; code guards: one child start, one git module, no network import, no shell, no `shell=True`). The normal suite stays standard library only.

### KNOWN-LIMITS (written now, numbered 213 to 232)

213 owner commands trust a terminal; 214 a tester is an AI helper and a pass is a claim; 215 scope is checked after the run; 216 error recognition is a list of line markers; 217 progress is a changed tree and can be faked; 218 cost is attributed by a window; 219 deadlines are enforced when a command next runs; 220 merges are seen only on the local main; 221 git is trusted; 222 shared docs are stale until rebuilt, and the status paragraph stays by hand; 223 a model word is checked for shape only; 224 the event log is not tamper evident; 225 one goal, one task, the owner is the wait; 226 OpenCode is not a builder yet; 227 plan quality and prompt injection are not judged; 228 a killed supervisor leaves a child; 229 each worktree is a full checkout and uses disk; 230 leftover worktrees stay until removed; 231 untracked and ignored files (`node_modules`, build folders, local config) are not in a worktree; 232 worktrees share the repository's metadata. Full text in `docs/KNOWN-LIMITS.md`.

### Hours, and what it does to the schedule

Estimates, without a margin. W9.0 (this spec) is about 6 hours and is this pull request.

| task | hours |
| --- | --- |
| W9.1 tests first: generators, fake agent, fake root, the golden status and report | 7 |
| W9.2 `goalpacket.py`: packet, plan parser, protected list, scope check, state table, roles rule | 6 |
| W9.3 `goallog.py`: events, the total reader, the writer, the bounded line reader | 5 |
| W9.4 `goalwatch.py`: signature, judge, approvals, `expired` | 5 |
| W9.5 `goalstate.py` and `goalbudget.py`: files, entries, the write order, repair, the ledger window | 7 |
| W9.6 `agent run --cap-uu --model --effort` with goldens first | 6 |
| W9.6b the worktree per task: `agent run` and `agent check --workdir`, the worktree git list, the fixed root, the checks, the lifecycle, `test_worktree.py` | 9 |
| W9.7 `goalrun.py`: the supervisor, the watch, the roles, the prompts | 9 |
| W9.8 `goal.py`: the commands, exit codes, status, report, answer, merged, stop; example rules | 7 |
| W9.9 `goaldocs.py`: parts, build, check, the migration (its own pull request, first) | 7 |
| **First batch: W9.1 to W9.9 and W9.6b** | **68** |
| W9.10 the whole-system scenarios, the mutation pass | 8 |
| W9.11 docs current and the owner's by-hand run with real helpers | 4, plus the owner's time |
| W9.12 `--ahead N`: several tasks in review at once (the worktree per task is core, W9.6b) | 4 |
| W9.13 OpenCode as a builder (after 10.48) | 8 |
| W9.14 `goal retry` | 3 |
| W9.15 the snapshot counts goals that need the owner | 6 |
| W9.16 the scope enforced during the run by a rules overlay | 8 |

The schedule to Dec 3 has no window for this (layer 12 and W6 are not placed either, and the freeze is Nov 29), and I have not placed W9 in the schedule table; the owner sets any dates (W9-Q14, answered). W9.9 is useful alone, removes the doc conflicts that every pull request has today, and is the one piece that may go before Dec 3 (the owner's answer to W9-Q14, Nov 12: only W9.9 before the freeze, the rest after Dec 3). W9.9 is also the owner's task W17: they are the same task. Build it at a quiet moment, right after the pull request of the W6 first batch (W6.1 to W6.6) merges: the first build moves the text of `docs/status-log.md` and `docs/KNOWN-LIMITS.md` into `docs-parts/`, so any open pull request that still edits those two files would conflict with it; with the W6 batch merged and few pull requests open, that is least likely. The build is in four pull requests after W9.9: W9.1 to W9.5 (nothing starts an AI helper), W9.6 (the three options, goldens first), W9.6b (the worktree per task and `--workdir`, goldens first), W9.7 and W9.8 (the supervisor and the commands). No code starts an AI helper before the fourth.

### Docs page plan

`docs/goals.md` is written in this pull request as "specified, not built" with the four parts. In the build pull requests: `docs/exit-codes.md`, `docs/rules.md`, `docs/architecture.md`, `docs/security.md`, `docs/testing.md`, `docs/budget-governor.md` and `docs/agent-front-door.md` (the three options), `docs/status-log.md` (a part file, then the rebuilt table), `adapters/NOTES-w9.md` (the by-hand results), `goal.rules.example.yaml`, and the example rules of the three adapters.

### Open questions for the owner (W9-Q1 to W9-Q14), with the owner's answers of Nov 12

Each had a recommendation, and the spec was written with it. The owner answered all fourteen on Nov 12 2026: every one approved as recommended. Each item ends with its status; the answers are recorded as given after the list.

1. **W9-Q1. The name.** The repo defines W4 to W7 and not W8. I used W9 as you named it and left W8 unused. Recommendation: keep W9; tell me if W8 means something I should read. **Answered Nov 12: approved, keep W9. W8 is progress dashboards on the owner's board and is not in the repo.**
2. **W9-Q2. The tester and the guide are not the builder.** The agent names must differ, checked at approval and at every start; the same platform and model gives a warning, not a refusal. Or also require a different platform or model (stronger, but an owner with one platform and one model could not run a goal). Recommendation: names differ, warn on the same platform and model. **Answered Nov 12: approved as recommended.**
3. **W9-Q3. Where the helpers work.** All three roles use the same dedicated checkout (their `workdir` in `agents.yaml` is the same folder, a clone of its own, not your working copy), and umwayi makes the task branch with `git switch -c`. Or a git worktree per task, which needs an `agent run --workdir` and is needed anyway for working ahead (W9.12). Or your own working copy (not proposed). Recommendation: one dedicated checkout now, worktrees with W9.12. **Answered Nov 12: first approved as recommended (one dedicated checkout now, worktrees with W9.12). Then changed by a new owner rule the same day: the worktree per task is core, not an option, and it supersedes the one dedicated checkout. One task gets one worktree, made by umwayi from the newest main, with a fresh helper session per task; no helper works in a shared checkout. Applied in W9.R8.1 and W9.R8.9 to W9.R8.16, this section ("The worktree of a task"), tasks.md (W9.6b) and `docs/goals.md`.**
4. **W9-Q4. Waiting for the merge.** The next task starts only after the one before it is merged, so one `goal run` does one task and you are the pace. Or several tasks in review at once (`--ahead N`) when their files do not overlap, which needs W9.12 (10 hours, and a worktree per task). Recommendation: wait for the merge now; add `--ahead` only if the waiting hurts. **Answered Nov 12: approved as recommended. After the worktree rule (Q3) W9.12 is `--ahead N` only, 4 hours: the worktree per task is already core.**
5. **W9-Q5. When a task fails.** The goal halts, the report says why, later tasks stay queued, and you start again or ask for a retry (W9.14). Or one automatic fix attempt with the tester's findings, which costs more and is a second builder run. Recommendation: halt, no automatic retry. **Answered Nov 12: approved as recommended.**
6. **W9-Q6. Progress, errors and the numbers.** Progress is a changed work tree (the task's own two files excluded), measured every 30 seconds, and 30 minutes without it stops the run. An error is a line starting with one of nine markers, and two identical signatures in a row (other output and edits between do not reset it) stop the run. Or reset the count whenever the tree changes, which tolerates a builder that edits and hits the same error again. Recommendation: the literal reading, and the numbers 30 minutes, 2, 30 seconds. **Answered Nov 12: approved as recommended (the literal reading, 30 minutes, 2, 30 seconds).**
7. **W9-Q7. Approval deadlines.** A plan waits 7 days, a task that needs you 24 hours, both changeable per goal from 1 hour to 7 days, and both answer No when they pass. A task in review has no deadline. Recommendation: as written. **Answered Nov 12: approved as recommended (7 days and 24 hours, the answer is No when they pass).**
8. **W9-Q8. Platforms.** Claude Code and Kiro through `agent run` in the first batch. OpenCode as a builder waits for task 10.48 and a non-interactive ACP run (W9.13). An effort for an OpenCode agent is refused until a flag is confirmed on a real install. Recommendation: as written. **Answered Nov 12: approved as recommended (Claude Code and Kiro first, OpenCode after 10.48).**
9. **W9-Q9. Owner commands need a terminal.** `approve`, `answer` and `merged` refuse unless standard input and output are terminals, so a script or an AI helper's tool cannot run them. Or they work from a script with the rules as the only guard (as `kill off` does today). Recommendation: terminal required; `kill off` is not changed here. **Answered Nov 12: approved as recommended.**
10. **W9-Q10. Who rebuilds the shared docs.** The system prepares a docs-only branch as the last step of a goal and you open and merge the pull request; the base text of today's files is frozen into `00-*` parts so the first build is byte for byte today's file. Or a task does it, which brings the conflict back. Or CI does it, which needs write access this repo does not give CI. Recommendation: the system prepares the branch; you merge. **Answered Nov 12: approved as recommended (the system prepares the docs branch, the owner merges).**
11. **W9-Q11. Scope during the run.** Version 1 checks the files after the run and relies on `rules.yaml` during it. Or a per-task overlay that `umwayi check` reads while the task runs (W9.16, 8 hours, a change to the core check). Recommendation: after the run now; the overlay later, if a builder strays in practice. **Answered Nov 12: approved as recommended (checked after the run).**
12. **W9-Q12. Which repo.** Version 1 works on this repo (umwayi-os) and its docs layout only. Another root without `docs-parts/status-log/` records the outcome under `.umwayi/goals/` and has no docs parts. Recommendation: this repo first. **Answered Nov 12: approved as recommended (this repo first).**
13. **W9-Q13. Steering.** Add W9 to the build order of `.kiro/steering/product.md` when you approve the spec. No safety rule is changed: rules 3, 4, 5, 7 and 9 already cover a goal (branches only, drafts only, no network, every helper action through `umwayi check`, standard library). Recommendation: a short paragraph in the build order only; no change to rules 1 to 13. **Answered Nov 12: approved as recommended. Applied in this pull request: one paragraph in the build order of `.kiro/steering/product.md`, no change to rules 1 to 13.**
14. **W9-Q14. Dates.** Nothing is placed in the schedule. Recommendation: W9.9 (7 hours) before the freeze of Nov 29 if you have the time; everything else after Dec 3, because the first batch is about 60 hours and the freeze does not move. **Answered Nov 12: approved as recommended. With the worktree rule the first batch is 68 hours (W9.6b added, 9 hours, and W9.7 down by 1), so the rest after Dec 3 is 61 hours. Only W9.9 (the shared docs builder, 7 hours) may go before the Nov 29 freeze; the rest after Dec 3. Applied in this pull request: the schedule note in `docs/schedule.md` and the schedule table of tasks.md. The owner adds that W9.9 is also the owner's task W17 (see the answers below).**

Answers (owner, Nov 12), recorded as given:

- Approved as recommended: W9-Q1 (keep W9; W8 is progress dashboards on the owner's board, not in the repo), Q2 (names differ, warn on the same platform and model), Q4 (wait for the merge), Q5 (halt, no automatic retry), Q6 (the literal reading, 30 minutes, 2, 30 seconds), Q7 (7 days and 24 hours, answer No when they pass), Q8 (Claude Code and Kiro first, OpenCode after 10.48), Q9 (terminal required), Q10 (the system prepares the docs branch, the owner merges), Q11 (check after the run), Q12 (this repo first), Q13 (a short paragraph in the build order of `.kiro/steering/product.md` only, no change to rules 1 to 13), Q14 (only W9.9, the shared docs builder, 7 hours, may go before the Nov 29 freeze; the rest after Dec 3).
- Changed by the owner (a new rule, later on Nov 12): **Q3**. The worktree per task is core, not an option, and it supersedes the answer "one dedicated checkout now, worktrees with W9.12". One task gets one worktree, made by umwayi from the newest main, with a fresh helper session per task; no helper works in a shared checkout. The worktree is part of the core design: the git list gains `worktree add` and `worktree remove`, the task branch lives in its own worktree, the worktree path is under a fixed root and is checked, a dirty or leftover worktree stops the start, and cleanup happens only after the owner's merged. `agent run --workdir` for a path umwayi made and the worktree per task move out of W9.12 into the first batch (W9.6b); `--ahead N` stays in W9.12 as the only option. The first batch is 68 hours (it was 60).
- Additional: **W9.9 is also the owner's task W17** (one status file and one limits file per task; a script builds `docs/status-log.md` and `docs/KNOWN-LIMITS.md`). W9.9 and W17 are the same task: one piece of work, not two. It is to be built at a quiet moment, right after the pull request of the W6 first batch (W6.1 to W6.6) merges.
- Nothing was changed by the answers of the first round except as follows (the worktree rule above is the one change after them). Q1 changed the wording of the name note (requirements, `docs/goals.md`). Q13 and Q14 were applied (steering paragraph, schedule note). The W17 note and the quiet moment were added to W9.R14.9, W9.9, the hours section above and `docs/goals.md`. No requirement, packet field, state, number or exit code changed.

Where each answer landed (the worktree rule, Q3, is listed in the changed bullet above and in W9.R8, tasks.md W9.6b and W9.12, KNOWN-LIMITS 215, 221, 225 and 229 to 232, and `docs/goals.md`): Q1 in requirements (the intro of the W9 section) and `docs/goals.md`; Q13 in `.kiro/steering/product.md` (build order, one bullet, rules 1 to 13 untouched); Q14 and W17 in tasks.md (the schedule table, W9.9, the W9 plan row), `docs/schedule.md`, the hours section above, requirements W9.R14.9 and `docs/goals.md`; the status of all fourteen in this list, tasks.md, `docs/goals.md` and the status log.

## Guidance (W19), stage 1

Added in the W19.1 pull request. Stage 2 (the concerns record checker and the security checklist checks) is a later task and is not started.

**What it is.** `guidance.yaml` at the repo root is a checked list of rules for the goal flow. Each entry has an `id`, a `source` (a file and a rule number), a `text` (one sentence), a `kind` (`enforce`, `advise` or `owner`), an `applies_to` (`goal`, `task`, `pr` or `release`) and a `source_hash`. An `enforce` entry also has a `check` (the name of a registered function), an `advise` entry a `prompt_line` (one line for an AI helper's prompt), an `owner` entry neither. The code checks that a record exists and is well formed. It never claims that the content is true.

**The loader** (`umwayi/guidance.py`) reads the file with the strict reader `umwayi/miniyaml.py` (no tabs, anchors, tags, block scalars or duplicate keys; the stage 1 brief asked for a small strict parser, and this one already exists and is tested, so it is used instead of a second copy) and then checks every key and value against a closed table in `parse`: exactly the keys `version` (1) and `guidance`, at most 200 entries, ids of 3 to 48 characters, text of 10 to 200 printable characters with no em dash, a 64 character hash, a tier, a source repo. It fails closed:

| situation | result |
| --- | --- |
| unknown kind, an enforce entry with no check or an unregistered check, a duplicate id, an unknown or missing key, a bad value, a file over 256 KB, not UTF-8, an em dash | `GuidanceError`, exit 64 |
| `guidance.yaml` missing or unreadable | `AskFirst`, exit 3 |
| a `source_hash` that no longer matches its source line, a source file or rule that cannot be found exactly once, a source outside the repo | `SourceChanged` (an `AskFirst`), exit 3: stop and ask the owner |
| any other error | exit 2 |

**Tiers.** Every entry has a required whole number `tier` from 1 to 6 (a missing, non integer or out of range tier is exit 64). The lower number wins: 1 safety (rules gate, kill switch, fail closed, Ask me first); 2 owner decisions and standing rules; 3 hub hard rules (core-rules, understanding-first); 4 builder rules; 5 practices (agent-practices, the 111 concerns, Kiro ten); 6 advisory prompt lines. An entry may have `overrides`, a list of entry ids. A lower tier may never relax a higher one, so the loader refuses (exit 64) an entry whose `overrides` names an entry with a lower tier number, and also an unknown id, itself, a repeated id, or more than 20. `resolve(entries, id_a, id_b)` returns the winner: the lower tier number wins; in the same tier enforce beats advise; two enforce entries of the same tier, any other pair in one tier, and an id that is not an entry raise `AskFirst` (exit 3, one line, no ids in it). `overrides` is recorded and checked but does not change `resolve` in stage 1. The tiers of the starting entries are in "Entries" below.

**Source and hash.** `source` is `PATH#N` or `PATH#HEADING#N`: the numbered line `N. ...` of the file, inside the section whose heading starts with `HEADING` when one is given. It must exist on exactly one line (code fences do not count). `source_hash` is the SHA-256 of that line. A hand edited hash, or an edited, moved or removed rule, stops the loader. Messages are fixed words and never carry text of either file.

**The registry** `CHECKS` has four functions that take a task record (a dict) and return `None` or a one line reason: `goal_sentence_present` (`goal`), `consequences_and_undo_present` (`consequences` and `undo`), `acceptance_checks_present` (`acceptance_checks`, a non empty list of non blank strings) and `one_open_pr` (`open_prs`, a list the caller fills, at most one item; no network call is made here). A missing field, a wrong type, an empty string and a string of white space are all refused.

**The seam in the goal flow.** `check_task(entries, record)` runs every enforce entry whose `applies_to` is `goal`, `task` or `pr`; `release` is for a later flow. `umwayi goal guard [TASKFILE]` loads the file and, given a JSON task record, refuses a task that breaks an enforce rule: exit 3 Ask me first and one line with the first reason. Without a file it only checks `guidance.yaml`. Exit codes: 0, 2, 3, 64, never 1. The goal commands of W9.8 (`start`, `approve`, `run`) call the same function before they do anything else; until W9.8 exists the command is the only caller.

**Source repo and the hub.** Every entry has a required `source_repo`, `umwayi-os` or `hub`. The rules of understanding-first, core-rules and agent-practices live in the owner's private hub repo, and the owner decides what goes into this public repo, so those files are never copied here and no rule text is invented. For `umwayi-os` the loader checks `source_hash` against the line in this repo, as above. For `hub` the loader reads nothing: `source` is `FILE.md#N` (the hub file name and the rule number; a practice that has a name and no number, such as `agent-practices.md#verification-first`, uses the name) and `source_hash` is the SHA-256 of the whole hub file as recorded at hub commit 658a799 (a local clone that may be behind the real hub). Two hub entries for one file must carry the same hash. `umwayi guidance verify --hub PATH` (an owner command) compares each stored hash with the real file and exits 3 Ask me first on a mismatch or a missing file, with one line that names entry ids and no file text; a path that is not a folder is 64. `umwayi guidance list [--hub PATH]` prints one line per entry (id, kind, tier, source repo, status) and shows a hub entry as `unverified` unless `--hub` was given and its file matches, never as verified otherwise; a mismatch makes it exit 3. Nothing is stored about a past verify.

**Entries.** Nine, with the wording in our own words and the source and rule number exact. Enforce: goal sentence (understanding-first rule 3, tier 3), consequences and undo (understanding-first rule 13, tier 3), acceptance checks before the work (agent-practices verification-first, tier 3 by the owner's assignment), one open pull request per task (`umwayi-os`, builder workflow rule 1, tier 4). Advise, tier 6: record what is true now (rule 12), check the output against the goal sentence (rule 4), do not accept output you cannot explain (rule 1), rewrite a broken base (rule 7). Owner, tier 2: batch interruptions (rule 8). The brief asked for six advise and three owner examples; the owner named four and one, and no rule was invented to fill the gap.

**Tests.** `tests/goal/test_guidance.py`: each fail closed case of the loader, the hub entries, `verify` and `list`, a hand edited hash, each of the four checks (pass, missing, empty, white space only, wrong type), the committed file (loads, no em dash), and the command with its exit codes. KNOWN-LIMITS 254.
