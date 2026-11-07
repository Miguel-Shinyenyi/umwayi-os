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
- [x] 3.8 `answer` column and required `--answer` on `umwayi queue answer`
- [x] 3.9 `close` works on open or answered rows (tested, including that answer and date are kept)
- [x] 3.10 Ids are never reused: highest id in `queue.md` and in the logbook plus one, refuse to add if the logbook is unreadable
- [x] 3.11 Old six column layout refused with a message that names the migration; `umwayi queue migrate` converts it once and logs it

## Layer 4: Archive

- [x] 4.1 Archive folder and `INDEX.md` format, strict index parser
- [x] 4.2 `umwayi archive move` (line range or markers, pointer line left behind)
- [x] 4.3 `umwayi archive verify` (ok, changed, missing, not in the index; exit 0 only when all ok; read only)
- [x] 4.4 One logbook entry per move; a failed logbook write undoes the move
- [x] 4.5 Tests (`tests/test_archive.py`): every refusal, the id guard, the pointer line, three file rollback, verify after a hand edit
- [x] 4.6 Shared atomic writer `umwayi/fsutil.py`; `logbook.logged_ids` takes an id prefix

Not built (later): `umwayi archive restore`. The output of `move` already names it.

## Layer 5: Logbook

- [x] 5.1 Append only writer and entry format (done early, in layer 3)
- [x] 5.2 Tamper check: SHA-256 record in `.umwayi/logbook.sha256`, checked before and written after every append
- [x] 5.3 `umwayi logbook seal --by NAME`: the only way to accept an unrecorded or edited logbook, never automatic
- [x] 5.4 Reader and validator for every entry; `umwayi logbook verify` (line numbers, never line text; read only)
- [x] 5.5 Real dates that never go backwards (verify problem and append refusal)
- [x] 5.6 Layer 2 wired: one entry per `umwayi check`, no action JSON, Ask me first if the logbook cannot be written, `--no-log` dry run
- [x] 5.7 Lock file `.umwayi/logbook.lock` so two appends cannot interleave
- [x] 5.8 Layers 3 and 4 use the same checked append
- [x] 5.9 Tests (`tests/test_logbook.py`, `tests/test_check_log.py`, `tests/test_logbook_integration.py`)

Review gate: stop here for owner review.

Still open after layer 5 (not in this layer's scope):

- A lock for `queue.md` and the archive files themselves. The logbook lock only covers the logbook append, so two queue or archive commands at once can still race on their own files.
- A stale lock (left by a killed process) is not removed automatically. The owner deletes it, as the message says.
- The record lives next to the logbook. Someone who edits the logbook and also rewrites the record is not detected. Sealing state outside the repo, or signing it, is not built.
- `umwayi archive restore` (named by `archive move`, not built).

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
