# Tasks: umwayi-os

Each layer works alone and is tested before the next starts. Stop for owner review after layer 2.

## Setup

- [x] 0.1 Steering file `.kiro/steering/product.md`
- [x] 0.2 Spec documents (requirements, design, tasks)
- [x] 0.3 Package skeleton, `pyproject.toml`, `umwayi` entry point
- [x] 0.4 CI workflow that runs tests on every pull request
- [x] 0.5 `.gitignore` that keeps private memory out of the repo

## Layer 1: Memory

- [x] 1.1 Config loader and validator for `umwayi.json`
- [x] 1.2 Private path matching (exact, folder, glob, parents, case-insensitive)
- [x] 1.3 Loader that builds the context bundle
- [x] 1.4 `umwayi memory bundle` with `--format text|json`
- [x] 1.5 Tests: private paths never appear, symlinks skipped, bad config stops, order is stable

## Layer 2: Rules

- [x] 2.1 Strict YAML subset reader
- [x] 2.2 Rules loader and validator
- [x] 2.3 Matcher engine and decision procedure
- [x] 2.4 `umwayi check` with exit codes 0, 2, 3
- [x] 2.5 Starter `rules.yaml`
- [x] 2.6 Tests: no match, broken file, bad JSON, precedence, exit codes

## Layer 3: Queue

- [x] 3.1 `queue.md` format, strict parser and writer (atomic write, only the touched row is rewritten)
- [x] 3.2 `umwayi queue list` (with `--status` and `--kind` filters)
- [x] 3.3 `umwayi queue add`
- [x] 3.4 `umwayi queue answer`
- [x] 3.5 `umwayi queue close`
- [x] 3.6 Every change appends to the logbook; a failed logbook write undoes the queue change
- [x] 3.7 Tests (`tests/test_queue.py`, `tests/test_logbook.py`)

Review gate: stop here for owner review.

### Layer 5 status: what exists and what is still needed

Done in `umwayi/logbook.py` (the smallest part that layer 3 needs):

- `append(root, Entry)` adds one entry to `LOGBOOK.md`. The file is only opened in append mode, so earlier bytes are never edited.
- Entry fields: date, source, added, checked, not done. Every field must be one line of plain text, so an entry cannot forge a second entry.
- The header `# Logbook` is written only when the file is new or empty.
- A symbolic link or an unwritable `LOGBOOK.md` is refused.

Layer 5 (task 5.x) still needs:

1. The tamper check: record a hash of the logbook after each write (`.umwayi/logbook.sha256`) and refuse to append if earlier lines changed. Today nothing detects a hand edit of earlier lines.
2. A reader and validator for entries (parse them back, detect a broken entry) and a command to run the check, for example `umwayi logbook verify`.
3. Wire layer 2 (`umwayi check`) and layer 4 (archive) to call `logbook.append`. Layer 2 does not write to the logbook yet.
4. Decide what to do about concurrent writers (two commands at once). There is no file lock yet, in the queue or in the logbook.
5. Decide whether the append should also check that the new entry date is not before the last entry date.
6. Atomicity of a single append: it is one `write` plus `fsync`, but a crash in the middle could leave a partial entry. The tamper check or reader should detect that.

## Layer 4: Archive

- [ ] 4.1 Archive folder and index format
- [ ] 4.2 `umwayi archive move` with pointer left behind
- [ ] 4.3 `umwayi archive verify`
- [ ] 4.4 Logbook hook on every move
- [ ] 4.5 Tests including tamper detection and failed writes

## Layer 5: Logbook

- [x] 5.1 Append only writer and entry format (done early, in layer 3)
- [ ] 5.2 Tamper check of earlier lines (see the list under layer 3)
- [ ] 5.3 Wire layers 2 and 4 to the shared function (layer 3 is already wired)
- [ ] 5.4 Tests

## Layer 6: Automation

- [ ] 6.1 Schedule runner scripts
- [ ] 6.2 Weekly progress report from git history
- [ ] 6.3 Draft only publish step that never pushes
- [ ] 6.4 Tests

## Layer 7: Helpers

- [ ] 7.1 Helper base that sends every action through `umwayi check`
- [ ] 7.2 Steward: reads the queue, proposes tasks
- [ ] 7.3 Social helper: article to post drafts
- [ ] 7.4 Tests that prove helpers stop on No and Ask me first

## Layer 8: Workflows

- [ ] 8.1 Workflow file format
- [ ] 8.2 Content loop: collect, brief, draft, approve
- [ ] 8.3 Kill switch flag
- [ ] 8.4 Tests

## Non goals for Dec 3

Budget governor, finance and marketing loops, web interface.
