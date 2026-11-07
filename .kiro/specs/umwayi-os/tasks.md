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

Review gate: stop here for owner review.

## Layer 3: Queue

- [ ] 3.1 `queue.md` format, parser and writer (atomic write)
- [ ] 3.2 `umwayi queue list`
- [ ] 3.3 `umwayi queue add`
- [ ] 3.4 `umwayi queue answer`
- [ ] 3.5 `umwayi queue close`
- [ ] 3.6 Logbook hook on every change
- [ ] 3.7 Tests

## Layer 4: Archive

- [ ] 4.1 Archive folder and index format
- [ ] 4.2 `umwayi archive move` with pointer left behind
- [ ] 4.3 `umwayi archive verify`
- [ ] 4.4 Logbook hook on every move
- [ ] 4.5 Tests including tamper detection and failed writes

## Layer 5: Logbook

- [ ] 5.1 Append only writer and entry format
- [ ] 5.2 Tamper check of earlier lines
- [ ] 5.3 Wire layers 2 to 4 to the shared function
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
