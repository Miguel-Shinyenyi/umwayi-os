# umwayi-os

An AI operating system for one person and their AI helpers.

It keeps memory, enforces rules before an AI helper acts, tracks a queue of tasks and decisions, archives moved text with a fingerprint, and writes a logbook of every change. It is built in layers, and each layer works alone and is tested before the next starts.

Status: layers 1 (memory), 2 (rules), 3 (queue) and 4 (archive) are built. See `.kiro/specs/umwayi-os/` for requirements, design and tasks, and `.kiro/steering/product.md` for the product rules.

## Install and test

Python 3.10 or newer, no third party packages.

```
pip install -e .          # optional, gives the `umwayi` command
python -m unittest discover -s tests -t .
```

Without installing, use `python -m umwayi` from the repo root.

## Layer 1: memory

```
umwayi.json                     config: memory_dir and private_paths
memory/master.md                master context
memory/projects/*.md            one file per project
memory/journal/*.md             journal
```

```
umwayi memory bundle [--format text|json]
```

Prints one context bundle for an AI helper. Anything under a path listed in `private_paths` (a file, a folder or a glob) is left out, and its name is never printed. Only a count is shown.

## Layer 2: rules

Rules live in `rules.yaml`. Each rule has an id, a title, text, a verdict (`yes`, `no` or `ask`), and optionally a cause and matchers.

```
umwayi check '{"type": "payment", "amount": 5}'
```

Prints the answer, the rule id and the reason:

```
No
Rule: no-money
Reason: AI helpers never move money or use bank or card credentials. Cause: Safety rule for all AI helpers.
```

| answer | exit code |
| --- | --- |
| Yes | 0 |
| No | 2 |
| Ask me first | 3 |

Fail closed: no matching rule, a broken or missing `rules.yaml`, or bad action JSON all give Ask me first. If several rules match, No beats Ask me first, and Ask me first beats Yes. Usage errors exit with 64.

Matchers (all must match):

- `type: payment` equals, ignoring case
- `type: [payment, transfer]` equals any
- `path__contains: secret` contains text
- `amount__exists: true` field is present

Use `--rules PATH` for another rules file, `--json` for JSON output, and `-` as the action to read it from standard input.

## Layer 3: queue

`queue.md` is a Markdown table you can read and edit by hand. The columns are id, kind (task or decision), title, status (open, answered, closed), recommendation, answer, and the date answered.

```
umwayi queue list [--status open|answered|closed] [--kind task|decision]
umwayi queue add --kind task "Write the spec" [--recommendation "Do it today"] [--date 2026-11-07]
umwayi queue answer Q-0001 --answer "Yes, go ahead" [--date 2026-11-07]
umwayi queue close Q-0001 [--date 2026-11-07]
umwayi queue migrate [--date 2026-11-07]
```

- `answer` needs `--answer` (one line, no `|`, up to 500 characters, the same limits as a recommendation). It works only on an open row. An open row has an empty answer, an answered row has an answer and the date answered.
- `close` works on an open or answered row and keeps its answer and date.
- Ids are never reused. `add` uses one more than the highest id found in `queue.md` and in the logbook, even if you delete a row by hand. If `LOGBOOK.md` exists but cannot be read, `add` refuses and says why.
- A queue.md in the old six column layout (no answer column) is refused with a message. Run `umwayi queue migrate` once to convert it. Old answered rows get the text `not recorded before migration`.
- Without `--date` the system clock is used. A malformed `queue.md` is an error with a line number, and nothing is changed. Only the row a command touches is rewritten.
- Every change appends an entry to `LOGBOOK.md` (date, source, added, checked, not done). Earlier logbook lines are never edited. The logbook records the length of an answer, not its text.

## Layer 4: archive

Moves a block of text out of a file into its own file under `archive/`, with a fingerprint, and leaves a pointer line behind.

```
umwayi archive move notes.md --lines 10-20 --reason "old plan" [--date 2026-11-07]
umwayi archive move notes.md --start "<!-- start -->" --end "<!-- end -->" --reason "old plan"
umwayi archive verify
```

- `archive/INDEX.md` is a Markdown table: id, source, moved, reason, words, sha256. `archive/A-0001.txt` holds the exact bytes of the block.
- The source gets one line in place of the block: `[archived A-0001: archive/A-0001.txt]`.
- Line ranges count from 1 and include both ends. Markers must each match one whole line, appear exactly once, and are part of the block.
- `move` refuses and changes nothing if the source is missing, a symbolic link, a private path in `umwayi.json`, or a protected file (logbook, queue, rules, config, archive, git data); if the range is empty or outside the file; if the markers are missing, repeated or in the wrong order; if the block has no words; or if the reason is empty.
- Ids look like A-0001 and are never reused: one more than the highest id in the index and in the logbook. If `LOGBOOK.md` exists but cannot be read, `move` refuses.
- The source, the archive file and the index all change or none do. If the logbook write fails, the move is undone. Each move adds one logbook entry.
- `verify` recomputes every SHA-256 and prints `ok`, `changed`, `missing` or `not in the index` for each id. It exits 0 only when all are ok, otherwise 1, and never changes a file.
- `umwayi archive restore` is not built yet. The output of `move` names it.
