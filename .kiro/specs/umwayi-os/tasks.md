# Tasks: umwayi-os

Each layer works alone and is tested before the next starts. A layer that is not started begins only when the owner says so.

## Status

| layer | status | pull request | tests on main after it |
| --- | --- | --- | --- |
| 1 Memory | done | PR 1 | 50 (with layer 2) |
| 2 Rules | done | PR 1 | 50 |
| 3 Queue | done | PR 2, then PR 3 (answer column, id guard, migrate) | 98 after PR 2, 134 after PR 3 |
| 4 Archive | done | PR 4 | 217 |
| 5 Logbook | done | PR 5 | 322 |
| 6 Automation | done | PR 6 (with the layer 2 fix: a No stays No) | 393 |
| 7 Helpers | done | PR 7 | 461 |
| 8 Workflows | done | PR 8 (with exit codes 64 and 2) | 532 |
| Hardening and whole-system test | done | PR 9 (merge commit 18146f6) | 556, on Python 3.10, 3.11, 3.12 and 3.13 |
| 9 Adapters | done, except 9.10 (repo rules.yaml) and 9.11 (with the whole-system test) | PR 11 (part 1), PR 12 (part 2: Kiro, generic, kill switch) | 578 after PR 11, 619 after PR 12, on Python 3.10 to 3.13 |
| 10 Own command line and chat | not started, planned Nov 9 to Nov 10, after the owner approves requirements, design and tasks | | |
| 11 Linux-like features | not started, planned Nov 9 to Nov 10, after the owner approves requirements, design and tasks | | |
| Whole-system test and security scan | not started, planned Nov 11 to Nov 14 | | |
| Budget governor | not started, planned Nov 15 to Nov 21 (owner decided yes) | | |

Limits that are known and not fixed are listed in `docs/KNOWN-LIMITS.md` (numbered there, referred to below as KNOWN-LIMITS 1 to 28; items 12 to 28 are about the layer 9 adapters).

## Schedule to Dec 3

| dates | work |
| --- | --- |
| Nov 8 to Nov 9 | Layer 9 adapters (part 1 in PR 11, part 2 in PR 12) |
| Nov 9 to Nov 10 | Layers 10 and 11. Each is built only after the owner approves its requirements, design and tasks |
| Nov 11 to Nov 14 | Whole-system test again (with the adapters and layers 10 and 11) and a security scan |
| Nov 15 to Nov 21 | Budget governor (the owner decided to build it before Dec 3), after the owner approves its requirements, design and tasks |
| Nov 22 to Nov 28 | README, demo, Devpost text |
| Nov 29 to Dec 2 | Freeze: only fixes for defects that tests find, no new features |
| Dec 3 | Submit |

## Setup

- [x] 0.1 Steering file `.kiro/steering/product.md`
- [x] 0.2 Spec documents (requirements, design, tasks)
- [x] 0.3 Package skeleton, `pyproject.toml`, `umwayi` entry point
- [x] 0.4 CI workflow that runs tests on every pull request
- [x] 0.5 `.gitignore` that keeps private memory out of the repo

## Layer 1: Memory (done, PR 1)

- [x] 1.1 Config loader and validator for `umwayi.json`
- [x] 1.2 Private path matching (exact, folder, glob, parents, case-insensitive)
- [x] 1.3 Loader that builds the context bundle
- [x] 1.4 `umwayi memory bundle` with `--format text|json`
- [x] 1.5 Tests: private paths never appear, symlinks skipped, bad config stops, order is stable

Still open:

- There is no `umwayi memory add` command; memory is plain files the owner writes (KNOWN-LIMITS 10).

## Layer 2: Rules (done, PR 1)

- [x] 2.1 Strict YAML subset reader
- [x] 2.2 Rules loader and validator
- [x] 2.3 Matcher engine and decision procedure
- [x] 2.4 `umwayi check` with exit codes 0, 2, 3
- [x] 2.5 Starter `rules.yaml`
- [x] 2.6 Tests: no match, broken file, bad JSON, precedence, exit codes

## Layer 3: Queue (done, PR 2 and PR 3)

- [x] 3.1 `queue.md` format, strict parser and writer (atomic write, only the touched row is rewritten)
- [x] 3.2 `umwayi queue list` (with `--status` and `--kind` filters)
- [x] 3.3 `umwayi queue add`
- [x] 3.4 `umwayi queue answer`
- [x] 3.5 `umwayi queue close`
- [x] 3.6 Every change appends to the logbook; a failed logbook write undoes the queue change
- [x] 3.7 Tests (`tests/test_queue.py`, `tests/test_logbook.py`)
- [x] 3.8 `answer` column and required `--answer` on `umwayi queue answer` (PR 3)
- [x] 3.9 `close` works on open or answered rows (tested, including that answer and date are kept) (PR 3)
- [x] 3.10 Ids are never reused: highest id in `queue.md` and in the logbook plus one, refuse to add if the logbook is unreadable (PR 3)
- [x] 3.11 Old six column layout refused with a message that names the migration; `umwayi queue migrate` converts it once and logs it (PR 3)

## Layer 4: Archive (done, PR 4)

- [x] 4.1 Archive folder and `INDEX.md` format, strict index parser
- [x] 4.2 `umwayi archive move` (line range or markers, pointer line left behind)
- [x] 4.3 `umwayi archive verify` (ok, changed, missing, not in the index; exit 0 only when all ok; read only)
- [x] 4.4 One logbook entry per move; a failed logbook write undoes the move
- [x] 4.5 Tests (`tests/test_archive.py`): every refusal, the id guard, the pointer line, three file rollback, verify after a hand edit
- [x] 4.6 Shared atomic writer `umwayi/fsutil.py`; `logbook.logged_ids` takes an id prefix

Still open:

- `umwayi archive restore` is not built. The output of `archive move` already names it. Not in `docs/KNOWN-LIMITS.md`.

## Layer 5: Logbook (done, PR 5)

- [x] 5.1 Append only writer and entry format (done early, in layer 3)
- [x] 5.2 Tamper check: SHA-256 record in `.umwayi/logbook.sha256`, checked before and written after every append
- [x] 5.3 `umwayi logbook seal --by NAME`: the only way to accept an unrecorded or edited logbook, never automatic
- [x] 5.4 Reader and validator for every entry; `umwayi logbook verify` (line numbers, never line text; read only)
- [x] 5.5 Real dates that never go backwards (verify problem and append refusal)
- [x] 5.6 Layer 2 wired: one entry per `umwayi check`, no action JSON, `--no-log` dry run
- [x] 5.7 Lock file `.umwayi/logbook.lock` so two appends cannot interleave
- [x] 5.8 Layers 3 and 4 use the same checked append
- [x] 5.9 Tests (`tests/test_logbook.py`, `tests/test_check_log.py`, `tests/test_logbook_integration.py`)

Still open:

- Editing both `LOGBOOK.md` and its hash record is not detected (KNOWN-LIMITS 3).
- Large logbooks are re-read on every append (KNOWN-LIMITS 4).
- Owner commands (queue, archive) do not take the run lock, so two of them at once can still race on `queue.md` or the archive files (KNOWN-LIMITS 9). Each write is atomic and logged.
- A stale `.umwayi/logbook.lock` left by a killed process is not removed automatically; the owner deletes it, as the message says. Not in `docs/KNOWN-LIMITS.md`.

## Layer 6: Automation (done, PR 6)

- [x] 6.1 Schedule runner: `umwayi run JOBFILE [--job NAME]`, `jobs.yaml`, fixed allow list (report, check, queue-list), gap rule, rules asked first, one logbook entry per run
- [x] 6.2 Weekly progress report from git history: `umwayi report --since DATE`, one fixed git log command, numbered drafts that never overwrite, no emails
- [x] 6.3 Draft only publish step: `umwayi publish-draft DRAFT` to `outbox/`, rule `publish-ask` (Ask me first), `--approved-by`
- [x] 6.4 Tests (`tests/test_automation.py`) with mutation checks
- [x] 6.5 Layer 2 fix (separate commit): when the logbook cannot be written, a No stays No (exit 2)

Still open:

- `--approved-by` is self-declared (KNOWN-LIMITS 1). No AI helper, job or workflow passes it; the system test checks this.
- `umwayi report` run directly does not check the kill switch (KNOWN-LIMITS 5).
- A failed publish can leave an empty `outbox/` folder (KNOWN-LIMITS 8).
- A deleted last draft number can be used again (numbering reads `drafts/`, not the logbook). Not in `docs/KNOWN-LIMITS.md`.

## Layer 7: Helpers (done, PR 7)

- [x] 7.1 Helper base (`umwayi/helpers/base.py`): every step through the rules, No exit 2, Ask me first exit 3 with a queue decision, only Yes continues, one logbook entry per step, no way to set an approval
- [x] 7.2 Steward: `umwayi steward [--waiting-days N]`, read only, one proposal under drafts/
- [x] 7.3 Social helper: `umwayi social draft ARTICLE_FILE`, fixed template, one draft per channel in `social_channels`
- [x] 7.4 Tests (`tests/test_helpers.py`) with mutation checks
- [x] 7.5 Shared `umwayi/drafts.py` (moved out of report.py); optional `social_channels` in umwayi.json; helper rules in rules.yaml

Still open:

- Social drafts use the same text for every channel (KNOWN-LIMITS 7).
- Answering a helper's queue item does not let it go on; to allow an action the owner changes rules.yaml. This is on purpose. Not in `docs/KNOWN-LIMITS.md`.
- If a later step stops, drafts from earlier steps stay (each has its own logbook entry). Not in `docs/KNOWN-LIMITS.md`.

## Layer 8: Workflows (done, PR 8)

- [x] 8.1 Workflow file format `workflows/NAME.yaml` (miniyaml), fixed allow list, `umwayi workflow validate NAME` (every problem with a line number, exit 64)
- [x] 8.2 Content loop `workflows/content-loop.yaml` (collect, brief, draft, approve) and `umwayi workflow run NAME`; approve adds a decision and stops with exit 3
- [x] 8.3 Kill switch `.umwayi/KILL`: `umwayi kill on|off|status`; stops every AI helper, job and workflow; unknown state fails closed
- [x] 8.4 Tests (`tests/test_workflows.py`) with mutation checks
- [x] 8.5 Separate commit: config and usage errors exit 64 in every command; unexpected errors exit 2 (`tests/test_exit_codes.py`)

Still open:

- The kill switch is a file anyone with write access can remove (KNOWN-LIMITS 2).
- YAML syntax errors show only the first problem (KNOWN-LIMITS 6).
- Inside a workflow, the social step is one rules check for all channels, so a per channel rule only works with `umwayi social draft` (KNOWN-LIMITS 7).

## Hardening and whole-system test (done, PR 9)

- [x] H.1 CI runs on Python 3.10, 3.11, 3.12 and 3.13
- [x] H.2 Run lock `.umwayi/run.lock` (`umwayi/runlock.py`, `fcntl.flock`, never waits): two AI helper, job or workflow runs at once give Ask me first (exit 3) and one logbook entry; no locking means fail closed (`tests/test_runlock.py`, with two real processes)
- [x] H.3 Whole-system test `tests/test_system.py`: one scripted run of the umwayi command as real processes, 38 logbook entries, `logbook verify` ok
- [x] H.4 Fault tests in the same file: logbook edits, broken rules, bad config and workflow files, crashes and corrupt state in every command, unknown actions, no network import, no approver code path
- [x] H.5 Fix: unexpected errors exit 2 in `umwayi check` and inside helper and workflow steps, never 1 or 3
- [x] H.6 Fix: a `memory` folder that is a link loop is a config error (64), not a crash
- [x] H.7 Proof that the tests fail: removing the lock, removing the kill switch check, and making check exit 1 on an error each make the system test fail
- [x] H.8 `docs/KNOWN-LIMITS.md`
- Not tested yet: Windows, macOS, network file systems for the run lock, the installed `umwayi` script (KNOWN-LIMITS 9 and 11)

## Layer 9: Adapters (done, 9.10 and 9.11 open)

Planned for Nov 8 to Nov 9. Part 1 of 2 (PR 11): the notes, the shared adapter code and the Claude Code adapter. Part 2 of 2 (PR 12): the Kiro adapter, the generic stdin and stdout adapter, and the kill switch in all three adapters.

- [x] 9.1 Read the official Claude Code hook documentation (PreToolUse) and the Kiro hook types and hook actions pages, and write down, with a link for every fact, the input fields, the output format, how to allow, deny or ask, and which exit code blocks: `adapters/NOTES.md`. The Kiro pages were read as the Markdown copies listed in kiro.dev/llms.txt; where they are silent or disagree, the notes say so.
- [x] 9.2 Core: `umwayi check --json` gives `answer`, `rule_id`, `rules_ok` and `action_ok` (and `logged`), so an adapter never reads the reason text. Standard library only; no exit code changed.
- [x] 9.3 Claude Code adapter (PreToolUse): `adapters/claude_code/hook.py`, with the shared code in `adapters/common/umwayi_gate.py`
- [x] 9.4 Kiro adapter (Pre Tool Use command action): `adapters/kiro/hook.py`. Exit 0 with empty stdout allows, exit 2 with the reason on stderr blocks; no other code is used, because the Kiro pages disagree about them. The `tool_input` field names are not documented, so every top level string field is sent as `input_<key>` (`generic_action`).
- [x] 9.5 Generic stdin and stdout adapter: `adapters/stdio/hook.py`. One JSON object in, one JSON line out (`decision`, `reason`, `queue`), exit 0 allow, 2 deny, 3 ask; `--platform` and `--no-ask` from the command line only.
- [x] 9.6 Ask me first where the platform has no ask: deny, and add one queue item of kind decision (Kiro always, the generic adapter with `--no-ask`). Core: `umwayi queue add --if-not-open` adds nothing while an open item of the same kind and title exists, so a repeated call does not fill the queue. Claude Code has ask, so it needs no queue item.
- 9.7 Every adapter catches every error and blocks, and never exits 1:
  - [x] Claude Code: exit 0 with a JSON decision, or exit 2 with the reason on stderr
  - [x] Kiro: exit 0 or exit 2 only. Generic: exit 0, 2 or 3, and on an error a deny line and exit 2
- 9.8 Each adapter package has its own README, with any third party package pinned:
  - [x] Claude Code: `adapters/claude_code/README.md`, no packages, the settings snippet shown there only
  - [x] Kiro and generic: `adapters/kiro/README.md` (the hook file snippet is shown there only; nothing in `.kiro` or `.claude` is created or changed) and `adapters/stdio/README.md`. No packages
- 9.9 Tests per adapter, as real child processes, with planted faults:
  - [x] Claude Code: `tests/adapters/test_claude_code.py` (No blocks, Ask me first asks, Yes allows, a broken rules file does not allow, a crash in the adapter or in umwayi check blocks, bad or empty stdin blocks, a timeout blocks, one logbook entry per check and logbook verify ok). Three planted faults make them fail.
  - [x] Kiro and generic: `tests/adapters/test_kiro.py` and `tests/adapters/test_stdio.py`, plus `tests/adapters/test_core_for_adapters.py` for `--kill-switch` and `--if-not-open`, and kill switch tests for Claude Code. Planted faults and 28 mutations, all caught, are listed in PR 12.
- [ ] 9.10 Starter rules for adapter actions in the repo rules.yaml. Done so far: example rules in `adapters/claude_code/rules.example.yaml`, `adapters/kiro/rules.example.yaml` and `adapters/stdio/rules.example.yaml`; the repo rules.yaml is unchanged.
- [ ] 9.11 Whole-system test again with the adapters (Nov 11 to Nov 14, with the security scan)
- [x] 9.12 Decide: should adapters deny everything while the kill switch is on? The owner answered yes. Done in PR 12 for all three adapters: `umwayi check --kill-switch` answers No while the kill switch is on or unknown, and the adapter also denies unless `kill_switch` is `off`.

## Layer 10: Own command line and chat (not started, planned Nov 9 to Nov 10)

Outline only. Built only after the owner approves its requirements, design and tasks.

- [ ] 10.0 Requirements, design and tasks written and approved by the owner

- [ ] 10.1 One front door that starts any agent through its own CLI or the Agent Client Protocol (ACP)
- [ ] 10.2 The queue, rules and logbook stay in front of every agent it starts (through the layer 9 adapters)
- [ ] 10.3 Reuse the platforms' CLIs and ACP. No model client is built.
- [ ] 10.4 Layer 10 adapter packages may use third party packages, pinned and listed in their own README. The core `umwayi` package stays standard library only.

## Layer 11: Linux-like features (not started, planned Nov 9 to Nov 10)

Outline only. Built only after the owner approves its requirements, design and tasks.

- [ ] 11.0 Requirements, design and tasks written and approved by the owner

- [ ] 11.1 Scheduling with cron or systemd timers (no new scheduler)
- [ ] 11.2 File watching with inotify
- [ ] 11.3 Process limits with Unix permissions, bubblewrap or containers
- [ ] 11.4 A small database with SQLite
- [ ] 11.5 Terminal sessions with tmux
- [ ] 11.6 No new scheduler, file system or shell is built

## Whole-system test and security scan (not started, planned Nov 11 to Nov 14)

- [ ] S.1 Whole-system test again, with the adapters and layers 10 and 11 (includes 9.11)
- [ ] S.2 Security scan of the code and the dependencies of any adapter package

## Budget governor (not started, planned Nov 15 to Nov 21)

The owner decided to build it before Dec 3. Built only after the owner approves its requirements, design and tasks.

- [ ] B.0 Requirements, design and tasks written and approved by the owner

## Non goals for Dec 3

Finance and marketing loops, web interface.
