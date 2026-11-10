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

## Layer 10: Own command line and chat (approved; all six parts built; part 7 approved, parts 7a and 7b built; part 7c approved, 7c-1 built)

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

### OpenCode as a platform (spec only, written Nov 9, waiting for owner approval)

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

### Muse Spark Open as a platform (spec only, written Nov 9, waiting for owner approval)

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

## Layer 12: Web interface, the view (spec in the UI.0 pull request, tasks.md UI.0; built only after the owner approves it)

Requirements 12.R1 to 12.R11. Tasks UI.0 to UI.5. Facts with links, and the owner's interface check: `adapters/NOTES-layer12.md`. It was a non goal until Nov 10; the owner moved it into scope before Dec 3. Layer 12 changes the core in one place only: the read only command `umwayi view snapshot` (`umwayi/view.py`). Everything else is in `ui/`, outside the package. If the owner approves, the order is UI.1 (the static world), UI.2 (the snapshot command), UI.3 (the page reads it), UI.4 (the owner checks panel), UI.5 (polish, docs, the owner's check).

### The owner's reference, and what this design keeps and changes

The owner supplied a screenshot and a design document of a 3D shepherd hillside (three.js, eleven stations around a lantern). `main.js` and `package.json` of the reference were not available; the design document describes them. The reference and its prompt are not in the repo; this section carries what the build needs. It is a starting point, not a copy.

| in the reference | in layer 12 | why |
| --- | --- | --- |
| eleven stations around a lantern, a station is a small model that acts out one function | kept; each station is a module made of still poses and the short moves between them | the poses give reduced motion its still frames (UI-Q4) |
| Budget drawn as a dashed ghost labelled "planned" | Budget is a built station | the budget governor was built in PR 33; showing it as planned would be wrong. B.10 (the owner's capture) is said in words |
| sample motion plays on its own, a "Play motion" button | no autoplay, motion after a click or cursor move, "Replay" in the panel | UI-Q4 |
| about 50,000 swaying grass blades, drifting mist, fireflies, aurora, constellation with packets, river light, circuit pulses | cut; sparse still grass, one fixed layer of fog, a still moon | calm and less congested (UI-Q4); every one of them moves or glows by itself |
| arcs between all stations at once | arcs only for the selected station and the stations it depends on; hidden in calm mode | less congestion |
| labels that look like game tags with a dot | eleven labels that are real buttons, quiet at rest | access (12.R6) |
| the state comes from `snapshot.js` loaded with a script tag | the owner picks `snapshot.json` in the page | UI-Q3 says one JSON file; a `fetch` of a file is a network call and a script tag would execute the file (UI-Q7) |
| pointer parallax, drag to orbit, slow sway | parallax and orbit only while the cursor or finger moves, easing to rest; no sway | UI-Q4 |
| the Fraunces and Karla fonts, Georgia and system fallbacks | system fonts only (a serif stack for titles, a sans stack for text) | no font file is loaded, so there is nothing to fetch |
| a no-WebGL page that says so and stops | the list view, with everything but the 3D scene | 12.R6.2 |

### Layout

```
umwayi/view.py              umwayi view snapshot: gather the counts, render, write, one logbook entry
umwayi/cli.py               the view subcommand
tests/test_view.py          the snapshot, real child processes
tests/test_ui_package.py    package.json, lockfile, .gitignore, build.json, the built page (standard library)
ui/
  package.json              three 0.187.0 and esbuild 0.28.2, exact versions
  package-lock.json         committed; sha512 for every package
  README.md                 the pinned versions, npm ci --ignore-scripts, the build command
  .gitignore                node_modules/
  build.mjs                 bundles src/ with esbuild into one page, writes dist/build.json
  src/
    index.html style.css main.js
    engine/                 on demand renderer, tween with ease out, pose player, reduced motion, calm mode
    world/                  sky, mountains, land, sparse grass, trees, lantern
    stations/               one module per station (memory.js ... budget.js) and index.js, the one list of stations
    data/                   snapshot.js (validate, map to scene numbers), sample.js, checks.js (the owner checks)
    ui/                     labels, panel, list view, checks panel, top bar
  test/                     node --test, no package
  dist/index.html           the built page, committed
  dist/build.json           SHA-256 of every src file, of package-lock.json and of index.html
```

`ui/` imports nothing from `umwayi/` and `umwayi/` nothing from `ui/`. The repo's `.gitignore` ignores `dist/` and `build/`; it gets an exception for `ui/dist/` so the page and `build.json` are committed, and a line for `.umwayi/snapshot.json` so the owner's counts are not.

### The stations: poses, moves and counts

A station is an ordered list of poses (a full arrangement of its parts) and moves (short ease out tweens between two poses). A click plays the moves of the selected station once and stops on the last pose. Reduced motion shows the poses only, one at a time. The count drives the numbers of the first pose (how many sheep, stones, beads).

| station | what you see | poses (still frames) | count from the snapshot |
| --- | --- | --- | --- |
| Memory | a fenced pasture, and a walled plot with a lid | grazing; the lid closed over a few pebbles (private paths are left out) | none |
| Rules | a gate with a lantern and a sheep at it | Yes (mint lantern, gate open, sheep through), No (red lantern, gate shut, sheep turned back), Ask me first (amber lantern, gate half open, sheep waits) | `rules`: lanterns of each colour by verdict |
| Queue | sheep in single file to a hut, a signpost | line; front sheep at the door; door closed behind it | `queue.open`: sheep; `queue.answered`: stones in a cairn by the hut |
| Archive | a tablet beside a stone slab, a cairn | tablet at the slab; tablet lifted; stone added with a seal, flag left at the slab | none |
| Logbook | a stump with growth rings and a helix of linked beads | chain intact; one bead added; one bead altered and the rest dark, the seal sweeps up the chain | `logbook.chain_length`: beads, `entries` in the panel |
| Automation | a sundial under an arc | morning; noon; evening, shadow turning | `schedule`: marks for entries, installed and enabled |
| AI helpers | a sheepdog, a white line, a stool with a lantern | scroll at the dog; scroll at the line, dog stopped; scroll on the stool (you publish) | none |
| Workflows | stepping stones to an arch with a lantern | first stone lit; middle stone lit; token left at the arch (approve adds a queue item) | none |
| Adapters | three kinds of fence (rail, dry stone, wire) on one latch post | each fence pulses into the latch in turn | none |
| Kill switch | a lane with a wattle hurdle between two posts | hurdle down, a sheep passes; hurdle up, posts glow red, the sheep halts | `kill_switch`: down for off, up for on or unknown |
| Budget | a trough inside a scaffold | level low; level at today's mark; level over the line | `budget.days`: seven marks, the water at the last |

Red, mint and amber mean something only at Rules, Kill switch and Logbook. Everywhere else the same colours are light and carry no signal. Counts the snapshot does not hold (Memory, Archive, Workflows, AI helpers, Adapters) are not shown; the sheep and stones there are decoration, and the panel says no count is shown. The reference's amber collar for decisions is dropped, because the snapshot has no decision count.

The panel shows, for the selected station: the name, built or planned, two short lines, the command, and the counts with the snapshot's date. At Budget it also says that B.10, the capture of one real export, is not done. At Rules it says that unknown is drawn as Ask me first.

### The scene and the motion engine

- **Layers kept:** a dusk sky (gradient, glow behind the mountains, a still moon), mountains, one land mesh with soft contour lines, sparse still grass, about 30 trees with smooth shapes, a lantern. **Cut:** wind, mist planes, fireflies, aurora, constellation, river, circuit pulses (12.R5.7).
- **Rendering style:** MSAA on, ACES filmic tone mapping, one soft directional light with soft shadows, a hemisphere light, distance fog, pixel ratio up to 2. Bloom only on the lantern and on lit station parts, capped. No pixelation, dither or scan lines.
- **No file loaders.** Textures are made in code or inlined as data. None of three.js's file loaders is imported, so the bundle holds no `fetch`. (Checked on Nov 10 in a bundle of the renderer, the composer and the bloom pass: no `fetch(`, `XMLHttpRequest`, `WebSocket`, `sendBeacon`, `localStorage`, `sessionStorage`, `indexedDB` or `document.cookie`, and one `http://` string, the XML namespace `http://www.w3.org/1999/xhtml`.)
- **On demand drawing.** There is no free running `requestAnimationFrame`. `invalidate()` asks for a frame; the loop draws while a tween is running and stops when none is. At rest the page draws nothing and the GPU is idle. A hover or a resize invalidates once.
- **Ease out.** Every tween is `1 - (1 - t)^3`. A camera flight lasts 1.4 s (2.2 s in calm mode), a station move 0.8 s to 1.6 s, the parallax settles in 0.6 s after the cursor stops. The whole chain ends in at most 3 s after the last input (5 s in calm mode). Nothing repeats.
- **Reduced motion.** `matchMedia("(prefers-reduced-motion: reduce)")` is read at start and on `change`. When on, `tween()` jumps to its end value, parallax is off, and the panel has Previous and Next for the poses. When it changes while a move runs, the move completes at once.
- **Calm mode.** A toggle in the top bar. It scales the scene's light, bloom and line brightness down, lowers contrast, slows the tweens, and hides the arcs. Panel and label text keep at least the floor of UI-Q9. It starts off, and starts on when the system asks for less contrast (`prefers-contrast: less`), proposed in UI-Q9.
- **Camera.** Overview at a low angle that shows the horizon. Select (click, tap, key, label): fly to a front view with the station in the left third and the panel on the right (a bottom sheet on a phone). Arrow keys move between stations, Esc returns. Drag orbits within limits.
- **Frame rate.** The page holds 30 frames a second while moving on an integrated GPU at 1440 by 900; after sustained slow frames it lowers the pixel ratio to 1. Phone: a wider field of view and the camera pulled back.
- **Palette** (the nightwatch tokens of the reference). base `#0E1310`, ink `#EEE8DB` (text only, never a large area), amber `#E0A965`, mint `#9CC39A`, red `#E07A6F`, glass `rgba(20,26,23,.62)` with a 14 to 22 px blur. Calm mode: the same hues at lower lightness; its values are fixed in UI.1 from the screenshots and checked against the 4.5 to 1 floor for text.

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
- **Export.** One function builds the text from the state: for each check its id and name, then each step as `[x]` or `[ ]`, its text and the typed result, and the last line "These are your notes. umwayi did not run or verify anything." A check with every step ticked is listed as "ticked by you", otherwise "not done". The text goes into a read only `<textarea>`. Copy uses `navigator.clipboard` when it exists and otherwise selects the text. Download makes a Blob and clicks an `<a download>` after the owner's click; UI.4 checks that it works under the page's Content-Security-Policy, and if it does not, Copy is the way.
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
- **Package and page:** `tests/test_ui_package.py`, 12.R10.2 and 12.R10.3. The allowed `http://` strings are a short named list (the XML namespace addresses three.js carries; today `http://www.w3.org/1999/xhtml`); anything else fails. This is a static check, so UI.5's browser pass also blocks every request and counts the attempts, which must be zero.
- **`build.json`:** the test recomputes the SHA-256 of every file under `ui/src/`, of `ui/package-lock.json` and of `ui/dist/index.html` and compares. A changed source with no rebuild, or an edited page, fails, with no npm in the test.
- **Node:** `ui/test/*.test.mjs` with `node --test`; run by the owner and recorded in the pull request, not by the Python suite.
- **Browser:** by hand, in a headless browser outside the repo (12.R10.5).
- **CI:** the CI workflow runs only the Python suite today. A Node job is open (UI-Q10).
- **Planted faults and mutation checks:** the list in 12.R10.6, counts in the pull requests.

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

### Hours and schedule effect

| task | hours |
| --- | --- |
| UI.0 spec | 5 |
| UI.1 the static world | 16 |
| UI.2 `umwayi view snapshot` | 9 |
| UI.3 the page reads the snapshot | 6 |
| UI.4 the owner checks panel | 6 |
| UI.5 polish, docs, the scan of `ui/`, the owner's interface check | 8 (and 1 of the owner's) |

About 50 hours, plus 1 hour of the owner's. The plan is Nov 13 to Nov 22: UI.1 Nov 13 to Nov 14, UI.2 Nov 15 to Nov 16, UI.3 Nov 17, UI.4 Nov 18 to Nov 19, UI.5 Nov 20 to Nov 22, in separate pull requests, UI.1 first, with its screenshots shown to the owner at the end of UI.1 (UI.2 is Python only and does not wait for them). Nothing else on the schedule moves: README, demo and Devpost Nov 23 to Nov 28, the freeze Nov 29 to Dec 2, submit Dec 3. If the spec is approved after Nov 13 the dates move by the days lost, and anything not done by Nov 22 is cut by the owner's choice, never by moving the freeze. UI.2 does not depend on UI.1, so the two can run in either order.

### Risks (layer 12)

| risk | what happens | what we do |
| --- | --- | --- |
| a count leaks text | a title or path appears in the page or the file | the structural leaf test, sentinel words, and a view module that reads through the layers' readers only |
| the page makes a request | the no network rule is broken | the static test, the zero attempt browser pass, no `fetch` in the source, no file loader bundled, and a Content-Security-Policy tag with `default-src 'none'` |
| the built page differs from its source | the reviewed code is not the shipped code | `build.json` checked in the suite; the owner rebuilds with a pinned lockfile |
| an npm package is hijacked or runs a script | the owner's machine runs foreign code | exact versions, a lockfile with sha512, `npm ci --ignore-scripts`, esbuild's binary from its platform package, the S.2 scan repeated on `ui/` |
| the page looks busy or flashes | the owner is uncomfortable | no loop at rest, one ease out per input, the luminance and overlap tests, the owner's screenshots at the end of UI.1 |
| a planned thing looks built | the owner is misled | a station has a state; Budget is built and B.10 is said in words; nothing of layer 13 is drawn |
| a checks panel result reads as proof | the owner trusts the page for a test it cannot run | "not done" until every step is ticked, "ticked by you" and never "passed", and the closing line of the export |
| WebGL missing or slow | a blank page | the list view and the checks panel work without it; the pixel ratio drops |
| the snapshot is stale | the page shows yesterday | the date next to the scene; KNOWN-LIMITS |

### Open questions for the owner (layer 12)

UI-Q1 to UI-Q5 are answered. UI-Q6 to UI-Q11 are open, each with the answer proposed.

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

Answers (owner, Nov 10): UI-Q1 to UI-Q5 as recorded above. UI-Q6 to UI-Q11 are open.

## Testing

- Standard library `unittest`, also run by `pytest`.
- Each layer has its own test module, using temporary folders.
- CI (`.github/workflows/ci.yml`) runs `python -m unittest discover -s tests -t .` on every pull request, on Python 3.10, 3.11, 3.12 and 3.13. After PR 9 there were 556 tests; after PR 14 (layer 10 parts 1 and 2) there were 673; after PR 15 (part 3) there were 697; after PR 16 (part 4) there were 719; after PR 17 (part 5) there were 747; after PR 18 (part 6) there are 783.
- `tests/test_system.py` runs the umwayi command as real processes in a fresh folder: one scripted run of every layer, and fault tests (logbook edits, broken rules, bad config, injected crashes in every command, corrupt state files, unknown actions, no network import, no approver code path).
- Mutation checks: for each layer, faults are put into the code on purpose and the tests must fail. PR 9 also showed the system test failing for three faults (no run lock, no kill switch check, check exiting 1 on an error).
- Layer 9 adapters get their own tests and CI job (see above).
