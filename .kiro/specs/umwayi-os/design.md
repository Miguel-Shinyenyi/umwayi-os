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
  logbook.py    layer 5 (minimal append writer exists, built with layer 3)
  archive.py    layer 4 (later)
  automation/   layer 6 (later)
  helpers/      layer 7 (later)
  workflows/    layer 8 (later)
```

Layers 2 to 4 write to the logbook through one function, `logbook.append(root, Entry)`. The smallest append-only version of it was built with layer 3 because every queue change must be logged. Layer 5 adds the tamper check and the rest (see tasks.md). The module is named `taskqueue.py`, not `queue.py`, because a file named `queue.py` inside the package would shadow the standard library `queue` when a file in the package is run directly.

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

`check` does not write to the logbook yet. Layer 5 wires it to `logbook.append`.

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

## Layer 4: Archive (planned)

`archive/index.json` maps id to `{source, reason, words, sha256, created}`. Each block is stored as `archive/<id>.txt`. `move` writes the archive file and index first, then replaces the block in the source with a pointer line `[archived: <id>]`. If any step fails, the source is untouched. `verify` re-reads every archive file and compares SHA-256.

## Layer 5: Logbook (planned)

`LOGBOOK.md` is opened in append mode only. The logbook keeps a hash of its current content in `.umwayi/logbook.sha256`. Before appending, it checks the existing content against that hash and refuses to write if earlier lines changed. Entry format: date, source, added, checked, not done.

## Layers 6 to 8 (planned)

- Automation: scripts plus a schedule file. The weekly report reads `git log` and writes a draft file. The publish step writes drafts to a folder and never calls `git push`.
- Helpers: each helper action is built as an action JSON and sent to `umwayi check`. Only Yes continues, and even then the result is a draft.
- Workflows: files in `workflows/` listing steps. A flag file `KILL_SWITCH` stops every run. If the flag cannot be read, the run stops.

## Testing

- Standard library `unittest`, also run by `pytest`.
- Each layer has its own test module, using temporary folders.
- CI (`.github/workflows/ci.yml`) runs `python -m unittest discover -s tests -t .` on every pull request, on several Python versions.
