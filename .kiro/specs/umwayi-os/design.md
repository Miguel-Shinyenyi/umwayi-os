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
  queue.py      layer 3 (later)
  archive.py    layer 4 (later)
  logbook.py    layer 5 (later)
  automation/   layer 6 (later)
  helpers/      layer 7 (later)
  workflows/    layer 8 (later)
```

Layer 5 is built after layers 3 and 4, but layers 2 to 4 are written so they call one function, `logbook.append(...)`. Until it exists, layers 2 to 4 take an optional `on_change` callback that defaults to nothing. Layer 5 then supplies the real function without changing the earlier layers' behavior.

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

`check` does not write to the logbook in layer 2, because the logbook is layer 5. The `on_change` hook is reserved for it.

## Layer 3: Queue (planned)

`queue.md` is a Markdown table: `id | kind | title | status | recommendation | answered`. `kind` is task or decision. Statuses: open, answered, closed. Ids are `Q-0001` style and never reused (the next id is max plus one, and closed rows stay). Writes go to a temp file and are renamed. Each command calls the logbook hook.

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
