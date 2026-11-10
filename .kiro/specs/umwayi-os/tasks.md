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
| 10 Own command line and chat | in progress: spec approved (10.0); all six parts built (agents.yaml, gate checks, `umwayi agent check`, `umwayi agent run` and `umwayi agent chat` with transport cli for Claude Code and Kiro, ACP chat for Kiro); 10.20 and 10.21 open; part 7 (Claude Code over ACP, 10.22 to 10.31) approved (10.22), part 7a built (10.23 to 10.25), part 7b built (10.26 to 10.28), 10.29 and 10.30 done, 10.31 waits for the owner's first real run; part 7c approved (10.32), part 7c-1 built (10.33 to 10.35), part 7c-2 built (10.38, 10.39), part 7c-3 built (10.36), 10.37 open; OpenCode and Muse Spark Open specified (10.40, 10.41), build after Dec 3 | spec PR 13; parts 1 and 2 PR 14; part 3 PR 15; part 4 PR 16; part 5 PR 17; part 6 PR 18; part 7 spec PR 19; part 7a PR 20; part 7b PR 21; part 7c spec PR 22; part 7c-1 PR 23; part 7c-2 PR 28; part 7c-3 PR 29 | 673 after PR 14, 697 after PR 15, 719 after PR 16, 747 after PR 17, 783 after PR 18, 829 after PR 20, 854 after PR 21, 869 after PR 23, 929 after PR 28, 934 after PR 29, on Python 3.10 to 3.13 |
| 11 Linux-like features | approved (11.0); scheduled runs through systemd user timers built (11.1 to 11.5); 11.6 waits for the owner's real check; file watching and tmux cut, SQLite and a sandbox deferred | spec PR 30; build PR 31 | 978 after PR 31, on Python 3.10 to 3.13 |
| Logbook crash safety (Layer 5 addendum) | approved Nov 9 (L5.0); built Nov 10 (L5.1 to L5.5), before 7c-2 | spec PR 26; build PR 27 | 906 after PR 27, on Python 3.10 to 3.13 |
| Logbook hash chain (addendum) | approved Nov 9 (C.0); built early on Nov 7 (C.1 to C.4), planned Nov 16 | spec PR 24; build PR 32 | 1001 after PR 32, on Python 3.10 to 3.13 |
| Budget governor | approved Nov 9 (B.0); built early (B.1 to B.9 and the capture mode of B.10), planned Nov 17 to Nov 22; B.10 waits for the owner's capture of one real export | spec PR 24; build PR 33 | COUNT_TBD |
| Whole-system test and security scan | not started, planned Nov 23 to Nov 26, after the budget governor (C-Q4) | | |

Limits that are known and not fixed are listed in `docs/KNOWN-LIMITS.md` (numbered there, referred to below as KNOWN-LIMITS 1 to 28; items 12 to 28 are about the layer 9 adapters).

## Schedule to Dec 3

| dates | work |
| --- | --- |
| Nov 8 to Nov 9 | Layer 9 adapters (part 1 in PR 11, part 2 in PR 12) |
| Nov 8 to Nov 9 | Layer 10 parts 1 to 7b and 7c-1 (7c-1 built Nov 9 in PR 23) |
| Nov 10 to Nov 11 | Logbook crash safety (L5.1 to L5.5) (approved, L5.0), right after PR 26 merges |
| Nov 12 to Nov 13 | Layer 10 part 7c-2 (10.38, 10.39) and 7c-3 (10.36, 10.29 to 10.31) |
| Nov 10 to Nov 11 | Layer 11: scheduled runs (11.1 to 11.5) (approved, 11.0), moved up from Nov 14 to Nov 15 by the owner (L11-Q14) |
| Nov 14 to Nov 15 | Free (layer 11 moved up) |
| Nov 16 | Logbook hash chain (C.1 to C.4), one day (approved, C.0); built early, PR 32 |
| Nov 17 to Nov 22 | Budget governor (B.1 to B.10) (approved, B.0); built early, PR 33; B.10 waits for the owner |
| Nov 23 to Nov 26 | Whole-system test again and security scan (S.1, S.2), after the governor: the adapters, layers 10 and 11, the chain and the governor, including the telemetry receiver (C-Q4) |
| Nov 23 to Nov 28 | README, demo, Devpost text, alongside the scan |
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
- A stale `.umwayi/logbook.lock` left by a killed process is not removed automatically; the owner deletes it, as the message says. Not in `docs/KNOWN-LIMITS.md`. Closed by the crash safety addendum (L5.1 to L5.5, PR 27): the lock is a kernel lock (flock), which a killed writer cannot leave behind.

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
- [ ] 9.11 Whole-system test again with the adapters (Nov 23 to Nov 26, with the security scan, S.1)
- [x] 9.12 Decide: should adapters deny everything while the kill switch is on? The owner answered yes. Done in PR 12 for all three adapters: `umwayi check --kill-switch` answers No while the kill switch is on or unknown, and the adapter also denies unless `kill_switch` is `off`.

## Layer 10: Own command line and chat (all six parts built; 10.20 and 10.21 open; part 7 approved, parts 7a and 7b built; part 7c approved, 7c-1 built)

Planned for Nov 8 to Nov 13: parts 7c-2 and 7c-3 on Nov 12 to Nov 13, after logbook crash safety. Requirements 10.R1 to 10.R10, design in design.md, doc facts in `adapters/NOTES-layer10.md`. The owner approved 10.0 on Nov 8.

- [x] 10.0 Requirements, design and tasks written and approved by the owner. Written in PR 13 (with `adapters/NOTES-layer10.md`), **approved and merged Nov 8**. The ten open questions in design.md (layer 10) were answered as proposed:
  1. Yes: `agent run` and `agent chat` take the shared run lock.
  2. Yes: Ask me first on a start adds one queue item (`Start agent NAME (MODE)?`).
  3. Kiro headless runs use `trust_tools` only, never `--trust-all-tools`.
  4. A managed Claude Code policy that blocks our hook is accepted as a known limit for Dec 3; no canary.
  5. `workdir` must be outside the umwayi root (not the root, not inside it, not containing it).
  6. In ACP chat, Ask me first asks the owner on the terminal.
  7. No `kiro_agent` with `transport: acp`.
  8. An agent's own failure is exit 2.
  9. Claude Code over ACP (Zed's third party adapter): decided later, after Dec 3.
  10. Spend limits are left to the budget governor; no `--max-budget-usd` in layer 10.

The build is split into six parts, one pull request each, each small enough to review in about 30 minutes. Every part keeps CI green on Python 3.10 to 3.13, adds no third party package, and lists its planted faults and mutation results in its pull request. Every test runs `python -m umwayi agent ...` as a real child process in a temporary root, with fake `claude` and `kiro-cli` scripts first on `PATH`; no test needs a network, a real agent or a key.

**Which parts can be done today (Nov 8), once 10.0 is approved:** parts 1 and 2 (done, PR 14). They start no agent (only the fake version and hook self-test children in tests), touch no platform, and do not depend on any open question except 5 (workdir). Parts 3 and 4 on Nov 9, parts 5 and 6 on Nov 10. If time runs short, part 6 (ACP chat) is the one to cut; parts 1 to 5 still give one front door for run and chat.

### Part 1: agents.yaml (10.R2, 10.R1.3, 10.R1.5)

- [x] 10.1 `umwayi/agents.py`: load agents.yaml with miniyaml; validate every key and value (fixed platform table, command allow list, transport per platform, workdir rules, Kiro tool ID list, number ranges, unique names); errors with line numbers, never line text.
- [x] 10.2 `umwayi agent validate` (0 or 64) and `umwayi agent list` (0, or 64 for a bad file); `--agents PATH`; `agents.example.yaml` at the repo root, commented.
- [x] 10.3 Tests (`tests/agents/test_agents_file.py`): every accepted shape; every rejected key and value (unknown key, unknown platform, `command: /usr/bin/claude`, `command: "claude --bare"`, `command: bash`, `acp` for Claude Code, `kiro_agent` with `acp`, relative or missing workdir, workdir equal to, inside or containing the root, a `..` part, unknown Kiro tool ID, `max_turns: 0`, duplicate names, tabs, flow mappings); no line text in any message; `list` starts no process.
  - Planted faults: the command allow list skipped; an unknown platform accepted; workdir containing the root accepted.
  - Mutation checks: each validation rule removed or loosened, one at a time.
  - Result (PR 14): the 3 planted faults and 21 mutations all caught.

### Part 2: gate checks and `umwayi agent check` (10.R6, 10.R5.1, 10.R5.7, 10.R1.4)

- [x] 10.4 Gate checks in `agents.py`: command on PATH (absolute path kept), version read and compared, hook script present, hook self-test (exit 2 within 5 s, nothing logged), Kiro hook file found and matched exactly (read only).
- [x] 10.5 Argument list builders for all five rows of the design table, and the Claude Code `--settings` JSON from the fixed template.
- [x] 10.6 `umwayi agent check NAME`: one line per check, exit 0 (gated), 2 (not gated), 64 (usage); starts no agent.
- [x] 10.7 Tests (`tests/agents/test_agents_gate.py`): a missing command; an unreadable version (`claude -v` printing nothing, garbage, `2.1.294`); a missing hook; a hook that exits 0, 1 or hangs on the self-test; no Kiro hook file, a hook file with a matcher, with another root, with a relative hook path, with extra arguments, broken JSON, a 1 MB file; the hook file in `~/.kiro/hooks/` (HOME set to a temp folder) accepted; every argument list for every valid agent never contains a forbidden flag (10.R5.7) and always contains `--permission-mode default` (Claude Code) or `--v3` (Kiro); the `--settings` JSON parses and has `disableAllHooks: false`, matcher `*`, `onFailure: "block"`; no `.claude` or `.kiro` file is created or changed by any test run.
  - Planted faults: the self-test result ignored; the Kiro hook match made a substring match; `--settings` left out of the Claude Code list; `--v3` left out.
  - Mutation checks: each check skipped or inverted, each comparison loosened (version `>=` to `>` and the reverse, matcher `*` check removed).
  - Result (PR 14): the 4 planted faults and 27 mutations all caught.

### Part 3: `umwayi agent run` for Claude Code (10.R3, 10.R4, 10.R5.2, 10.R5.9, 10.R8)

- [x] 10.8 The start steps 1 to 9 from the design, with the kill switch and rules before any platform process, the queue item for Ask me first (`taskqueue.add_once`), the run lock, the logbook entries, and exit codes 0, 2, 3, 64 only.
- [x] 10.9 The watcher (a loop in the main thread, which also stops the agent when the logbook can no longer be written): kill switch every second, timeout; SIGTERM to the process group, SIGKILL after 10 s; umwayi stops the child on any exception and on its own SIGTERM.
- [x] 10.10 Prompt input: `--prompt`, `--prompt-file`, `-` for stdin; at most 100 KB; a leading `-` refused with 64.
- [x] 10.11 Tests (`tests/agents/test_agents_run.py`) with the fake `claude` (`tests/agents/fake_agent.py`) (runs the hook from `--settings` for scripted tool calls): Yes runs and the hook's allow, deny and ask are recorded; rules No and Ask me first start nothing (the fake records no call) and the queue gets one item, not two; kill switch on before start: nothing started, exit 3; kill switch turned on during a run: the fake is stopped within about 2 s, exit 3, and its next tool call is denied by the hook; timeout; the fake exiting 1, 143 or crashing gives 2; run lock held gives 3; a broken logbook gives 2 and nothing started; the prompt is never in the logbook; one start and one end entry, logbook verify ok; umwayi killed with SIGTERM leaves no fake running; never exit 1 (checked over every test).
  - Planted faults: the rules check skipped; Ask me first treated as Yes; the kill watcher not started; an exception path that leaves the child running; exit 1 on an error.
  - Mutation checks: each step's failure branch removed; the exit code map changed one entry at a time; the watcher interval made 60 s.
  - Result (PR 15): the 5 planted faults and 27 mutations all caught. One more mutation (the stop after a normal exit) did not change behaviour, because the `finally` already stops the agent; the redundant line was removed.

### Part 4: `umwayi agent run` for Kiro (10.R5.4, 10.R6.2)

- [x] 10.12 The Kiro run list (prompt on stdin, `--v3`, `--trust-tools=` from agents.yaml, never `--trust-all-tools`) through the same steps as part 3.
- [x] 10.13 Tests (`tests/agents/test_agents_kiro_run.py`) with the fake `kiro-cli` (reads the instruction from stdin, runs the hook command from the hook file it finds, denies tools not in `--trust-tools`): Yes and in `trust_tools` runs; Yes and not in `trust_tools` is denied by the fake; No from the hook blocks; the hook file removed between two runs makes the second refused; the fake exiting 3 or 4 gives 2; the kill switch stops it; the prompt never appears in the argument list.
  - Planted faults: the Kiro hook file check skipped; the prompt passed as an argument; `--trust-all-tools` added.
  - Mutation checks: as part 3, for the Kiro branch.
  - Result (PR 16): the 3 planted faults and 12 Kiro branch mutations all caught with every agents test; and the 23 part 3 step mutations (4 planted faults, 19 mutations) re-applied and all caught by the Kiro tests alone.

### Part 5: `umwayi agent chat` on the terminal (10.R7.1, 10.R5.3, 10.R5.5)

- [x] 10.14 `chat` with `transport: cli` for both platforms: the queue summary printed first, then the terminal handed to the agent; same start steps and watcher; SIGINT ignored by umwayi while the agent runs (a no-op handler, not SIG_IGN, so the agent still gets Ctrl-C; the old handler is put back on every path); no process group change. The stop signals the agent's pid and every descendant seen in /proc, never umwayi's group; the terminal mode is put back.
- [x] 10.15 Tests (`tests/agents/test_agents_chat.py`; the fake agents in a chat mode that reads lines from stdin and echoes them; the interactive tests on a real pseudo terminal, with a small job control "shell" as session leader, the others with stdin from a pipe): the queue summary appears before any agent output; the agent gets stdin unchanged; the kill switch stops it; exit codes as for run; nothing of the conversation in the logbook.
  - Planted faults: the gate checks skipped for chat only; the kill watcher not started for chat.
  - Mutation checks: the chat branch of each step removed.
  - Result (PR 17): the 2 planted faults and 18 chat branch mutations all caught with every agents test; and the 19 part 3 step mutations that apply to a chat (4 planted faults, 15 mutations) re-applied and all caught by the chat tests alone.

### Part 6: ACP chat for Kiro (10.R7.2 to 10.R7.7)

- [x] 10.16 `umwayi/acp.py`: line-delimited JSON-RPC over the child's stdin and stdout, `initialize` (version 1, no `fs`, no `terminal`), `session/new`, `session/prompt` per owner line, `session/update` printing through `safe_text`, `session/cancel` on Ctrl-C, method not found for other requests, stop on a bad line or a wrong version.
- [x] 10.17 Permission answers through the rules (`acp_permission`), never `allow_always` or `reject_always`, never an invented option, Ask me first asked on the terminal.
- [x] 10.18 `:queue` and `:quit`.
- [x] 10.19 Tests (`tests/agents/test_agents_acp.py`, the owner side on pipes) with the scripted fake ACP agent (`kiro-cli acp` in `tests/agents/fake_agent.py`, driven by `FAKE_ACP`): a whole turn; Yes, No and Ask me first (`y`, `n`, empty) answers with the expected `optionId`; only `allow_always` offered gives reject; no reject option gives `cancelled`; an unknown outcome kind; `fs/read_text_file` and `terminal/create` get `-32601` and nothing is read or run; protocol version 2 ends the chat with 2; a garbage line ends it with 2; control characters, bidi and zero-width characters in agent text are made visible; the title is never in the action; the kill switch cancels and stops; Ctrl-C answers open permissions with `cancelled`.
  - Planted faults: Ask me first selects `allow_once` without asking; `allow_always` preferred; unknown requests answered with success; `fs` advertised in `initialize`.
  - Mutation checks: each row of the permission table changed; `safe_text` made a no-op; the version check removed.
  - Result (PR 18): the 4 planted faults and 35 ACP mutations (the permission table, safe_text, the protocol, bad lines, Ctrl-C, the kill switch, exit codes) all caught; the 6 mutations of the watcher, split into `_tick` and `_tick_stop` in this part, caught by every agents test and by the ACP tests alone; and 13 part 3 start step mutations re-applied and caught by the ACP tests alone.

### After the parts

- [ ] 10.20 (Done so far: KNOWN-LIMITS 29 to 34 for parts 1 and 2, 35 to 40 for part 3, 41 to 45 for part 4, 46 to 51 for part 5, 52 to 58 for part 6, and the README section. Left: what the first real runs show, 10.21.) `docs/KNOWN-LIMITS.md` items for layer 10 (at least: a managed Claude Code policy can block our hook unseen; Kiro hooks in ACP sessions not confirmed; version output format; the Claude Code prompt in the process list; PATH can point to another program; the agent can edit its own guard files), README section, tasks and design ticked. Added in the part that makes each limit real.
- [ ] 10.21 Whole-system test with the front door (part of S.1, Nov 23 to Nov 26), and one real run of each platform by the owner, recorded in NOTES-layer10.md (what the docs did not confirm).

### Part 7: Claude Code over ACP (approved Nov 8 2026; part 7a built in PR 20, part 7b in PR 21; 10.29 and 10.30 in PR 29; 10.31 waits for the owner's first real run)

Requirement 10.R11, design.md "Part 7: Claude Code over ACP", facts in `adapters/NOTES-layer10.md` ("Claude Code over ACP"). Numbered from 10.22, because 10.20 and 10.21 are taken. Nothing below starts before the owner approves 10.22. Effort about 20 hours (hours per task in brackets; 1.5 of them are the owner's first real run). Every test runs `python -m umwayi agent ...` as a real child process with a fake `node` (`tests/agents/fake_node.py`, a Python script first on PATH) and the scripted fake ACP agent of `tests/agents/fake_agent.py` in a Claude flavour; no real Node, no real Claude Code, no network, no key.

- [x] 10.22 Requirements 10.R11, the design section and these tasks written (Nov 8) in PR 19, **approved and merged Nov 8**. The ten open questions of design.md part 7 were answered as proposed:
  1. The canary is not seen: refuse the chat; no `acp_gate: permission_only` setting in part 7.
  2. Send `session/set_mode` `default` after the canary is seen; an error answer ends the chat with exit 2.
  3. Only the owner's existing Claude Code login; `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` are never passed.
  4. The owner installs with `npm ci --ignore-scripts` in `adapters/claude_acp/`; the lockfile is made once in the build pull request; umwayi never runs npm.
  5. Pin 0.101.0; change it only in a pull request that updates NOTES, `package.json`, the lockfile and the constant together.
  6. Use the Claude CLI bundled with the pinned SDK (Claude Code 2.1.318), not the owner's `claude` through `CLAUDE_CODE_EXECUTABLE`.
  7. Keep `settingSources` user, project and local.
  8. Keep `command: claude`; an ACP chat uses a fixed `node` from PATH.
  9. The canary wait is 30 seconds after `session/new`.
  10. Schedule A: part 7 Nov 9 to 11; layer 11 Nov 12 to 13; the whole-system test and security scan Nov 14 to 16 (superseded by C-Q4: scan Nov 23 to 26); the budget governor Nov 17 to 22; README, demo and Devpost Nov 23 to 28; freeze Nov 29 to Dec 2; submit Dec 3. (Superseded Nov 9 by the addendum: see tasks.md "Schedule to Dec 3".)
- [x] 10.23 (PR 20) agents.yaml and the platform table (1.5 h): `claude-code` with `transport: acp`; `permission_action` takes the platform; the pinned name and version constants. Tests: validation accepts it, still refuses `kiro_agent` and `trust_tools` for claude-code; `agent list` and `agent check` show it; the Kiro ACP action still says `kiro`, the Claude one `claude-code`.
- [x] 10.24 (PR 20) `adapters/claude_acp/` (2 h): `package.json` with one exact dependency, `package-lock.json` made once with network access in the build pull request (`npm install --package-lock-only`), `README.md` with the owner's install command and how to update the pin, `.gitignore` for `node_modules/`, `canary.py` (standard library). Tests: the version in `package.json`, the lockfile root and `agents.CLAUDE_ACP_VERSION` are equal; no range characters; `node_modules/` is ignored and not committed; `canary.py` imports only the standard library, writes exactly one empty file with O_EXCL and refuses a token that is not 32 hex characters or a folder that is not absolute.
- [x] 10.25 (PR 20) The gate checks (3 h), in the order of design.md: node on PATH, node at least 22, the adapter file, its `package.json`, `--version`, `--cli --version` at least 2.1.295, sign-in by exit code, the layer 9 hook and its self-test; and `child_env()`, the environment allow list. Tests with the fake node: each check failing in turn (no node, `v20.11.0`, garbage, the file missing or a link, another name, `0.100.9`, `--version` differing from `package.json`, Claude Code `2.1.294`, `auth status` exiting 1 or hanging), each exit 2 with nothing started; `agent check` prints every line; the fake records the environment names it got: only allow-listed names, never `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `CLAUDE_CODE_EXECUTABLE`, `NODE_OPTIONS` even when set, and `CLAUDE_AGENT_ACP_PROTOCOL=v1` always; the sign-in output (with a planted secret) is never printed or logged; every argument list has no shell and no forbidden flag.
- [x] 10.26 (PR 21) The inline settings and the canary (2.5 h): `_meta.claudeCode.options` with `allowDangerouslySkipPermissions: false` and `settings` holding the `agent run` PreToolUse hook (the same `claude_settings` code) and the SessionStart canary; the private token folder, removed on every path. Tests: the fake receives exactly that `_meta`; the PreToolUse hook entry equals the one `agent run` passes; a fresh token each start; the folder is gone after a normal end, a refusal, the kill switch, SIGTERM and a crash.
- [x] 10.27 (PR 21) `acp.py` options (2 h): `session_meta`, `gate_ready` (30 s), `set_mode`. Tests: canary seen: the chat goes on and `session/set_mode` `default` is sent before the first prompt; canary never run: exit 2, "could not be confirmed", no `session/prompt` sent, one refusal entry; canary run only at the first prompt (a fake option): refused; `session/set_mode` answered with an error: exit 2; a Kiro ACP chat sends no `_meta`, no `set_mode` and does not wait (unchanged).
- [x] 10.28 (PR 21) The stop (1 h): process group and every seen descendant for ACP chats. Tests: a fake that starts a child in a new session and a background command that ignores `session/cancel`: the kill switch, the timeout, SIGTERM to umwayi and `:quit` leave nothing alive.
- [x] 10.29 (PR 29) The chat end to end with the fake (3 h): a whole turn; tool calls in the fake run the PreToolUse hook first (the rules Yes, No, Ask me first for `tool_bash` and `tool_read`, one `umwayi check` entry each, `platform: claude-code`), then permission requests with the adapter's shape (`name`, `kind`, `rawInput`, `title`) answered by the rules; ExitPlanMode with only `allow_always` mode switches and one `allow_once` keeps `default`; a `kind` of `switch_mode` and `think`; nothing of the conversation, the token or the sign-in output in the logbook; exit codes as 10.R8.
- [x] 10.30 (PR 29) Planted faults and mutation checks (2 h), the counts in the pull request. Planted faults: the canary wait skipped; `ANTHROPIC_API_KEY` passed to the child; the version pin not compared; `allowDangerouslySkipPermissions` left out. Mutation checks: each gate check removed or loosened (node 22 to 20, the pin compare, the CLI version compare, the sign-in exit code), each allow-list exclusion removed, the canary token not compared, the set_mode error ignored, the stop without descendants, the platform in the action left as `kiro`; the Kiro ACP tests re-run on every mutation to show it is unchanged.
- [ ] 10.31 Docs and the first real run (3 h, 1.5 of them the owner's): KNOWN-LIMITS for what is not confirmed (when `SessionStart` runs in an SDK session; that the permission answer sees no command; supply chain; the adapter's speed of change), README, design and tasks ticked; then one real chat by the owner on a machine with Node 22 and a Claude Code login, recorded in NOTES-layer10.md: whether the canary ran before the first prompt, whether hook entries appear in the logbook for every tool call, the real `--version` outputs.
  - [x] The docs (PR 29): KNOWN-LIMITS 89 to 92 (65, 60 and 59 already said the rest), README, design and tasks ticked, and the owner's steps with the expected output in `adapters/NOTES-layer10.md` ("The owner's first real run (10.31)"), which also holds the real checks of 10.37 and 10.39.
  - [ ] **Not done, the owner's:** the real Claude Code ACP chat (canary before the first prompt, a hook entry for every tool call, the real `--version` outputs), the field names of the real `auth status --json` (subscription, a placeholder key in front, a project `apiKeyHelper`), and the real Kiro login (`whoami` exit code signed in and out, `agent login helper`, a headless run without `KIRO_API_KEY`). Results go into the table in NOTES; 10.31 is ticked only after that.

### Part 7c: subscription first, login and billing check (approved Nov 9 2026; part 7c-1 built in PR 23; 7c-2 (10.38, 10.39) built in PR 28; 7c-3 (10.36, 10.29 to 10.31) built in PR 29 except the owner's first real run)

Requirement 10.R12, design.md "Part 7c: subscription first, login and billing check", facts in `adapters/NOTES-layer10.md` ("Login and billing for Claude Code"). Tasks 10.29 to 10.31 above stay as they are. Nothing below starts before the owner approves 10.32. Effort about 14 hours (hours per task in brackets). Every test runs `python -m umwayi agent ...` as a real child process with the fake `claude`, the fake `node` and the fake `kiro-cli`, which answer `auth status --json`, `auth login --claudeai`, `whoami` and `login` from a script that holds a planted email, organization, URL, code and secret. No real Claude Code or Kiro, no network, no key, no real login.

- [x] 10.32 Requirement 10.R12, the design section, these tasks and the NOTES sections written (Nov 9) in PR 22, amended the same day for the owner's decisions, **approved and merged Nov 9**. The twelve open questions of design.md part 7c were answered as proposed:
  1. Read the five named fields of `auth status --json` and its exit code; the email, organisation and raw output are never read into anything.
  2. Refuse `oauth_token` (`CLAUDE_CODE_OAUTH_TOKEN`).
  3. A deny list of credential names for `agent run` and the cli chat; the ACP allow list stays.
  4. `forceLoginMethod: "claudeai"` in the one settings template.
  5. Show the plan word ("plan: WORD") in `agent check` and the start entry.
  6. The ACP watch of `_auth/status_update`.
  7. No way to allow API billing now.
  8. The login check after the version check and before the hook checks, replacing the 7a sign-in step.
  9. Build now: 7c-1 (10.33 to 10.35), then 7c-2 (10.38, 10.39), then 7c-3 (10.36, 10.29 to 10.31). OpenCode (10.41) and Muse Spark Open (10.40) stay spec only, built after Dec 3.
  10. Kiro: remove `KIRO_API_KEY`, a `whoami` exit-code check, `agent login` for Kiro, and refuse a headless Kiro run if it needs the key.
  11. `agent login` skips the login when the check already passes.
  12. The login environment as proposed.
- [x] 10.33 (PR 23) `login_check()` and the "login" gate check (3 h):
  - the pure function over the six fields;
  - the check for every Claude Code start, in the workdir and with the agent's environment, 15 s, at most 64 KB, stderr discarded;
  - it replaces the 7a "sign-in" step of the ACP checks and goes after "version" in the cli checks;
  - `agent check` shows "plan: WORD".
  
  Tests: every row of the design table, as a unit and end to end for `agent run`, the cli chat and the ACP chat, each exit 2 with nothing started and one refusal entry; the planted email, organization and secret never in stdout, stderr, the logbook or the queue; a code guard that only the six key names are read.
- [x] 10.34 (PR 23) `claude_env()`, the credential variables removed for `agent run` and the cli chat (1 h). Tests: the fake records the absence of every listed name even when set, for the agent and for its login check; the ACP allow list is unchanged; a Kiro start gets the environment as before.
- [x] 10.35 (PR 23) `forceLoginMethod: "claudeai"` in `claude_settings()` (0.5 h). Tests: it is in the `--settings` of `agent run` and the cli chat and in the ACP inline settings; the PreToolUse entries are still equal; the 7a and 7b template tests are updated, not removed.
- [x] 10.36 (PR 29) The watch during an ACP chat (1.5 h): `on_auth` in `acp.py` (about 10 lines) and the stop in `agents.py`. Tests: the scripted Claude fake pushes `_auth/status_update` with `kind: "api_key"` mid-turn, and the chat stops with exit 2, one entry and nothing alive (the 7b stop); `account` and a push without a kind change nothing; a Kiro ACP chat is unchanged.
- [ ] 10.37 Planted faults, mutation checks and docs (2.5 h, 0.5 of them the owner's):
  - Planted faults: `authMethod` not compared; `apiKeySource` ignored (a helper next to a subscription passes); `ANTHROPIC_API_KEY` passed to `agent run`; the email printed in a refusal message.
  - Mutation checks: each field rule removed or loosened; each listed variable left in; `forceLoginMethod` left out; the watch ignoring `api_key`; the check moved after the start.
  - Counts in the pull request.
  - KNOWN-LIMITS: the undocumented fields; what `auth status` may not see; a project `apiKeyHelper` running at the check; extra usage not visible; the window between the check and the start.
  - README and the adapter README.
  - The owner's real check, recorded in NOTES-layer10.md and folded into 10.31: the real `auth status --json` field names (never the values) for the subscription login, with `ANTHROPIC_API_KEY` set, and with a project `apiKeyHelper`.
- [x] 10.38 (PR 28) `umwayi agent login NAME` (3.5 h): mode LOGIN in `_Run`; the `agent login` subcommand in `cli.py`.
  - **Steps:**
    - the start steps with action type `agent_login`, and the queue item `Log in agent NAME?` added once;
    - the gate checks up to the login check;
    - the login check first (already OK: exit 0, nothing started);
    - `build_argv` for LOGIN: exactly `[NODE, ADAPTER, "--cli", "auth", "login", "--claudeai"]`;
    - the forbidden words `--console`, `--email`, `--sso`, `setup-token`, `logout` and the Kiro login flags added to `_assert_allowed`;
    - the owner's terminal unchanged, with no pipe;
    - `login_env()` = `child_env()` plus `LOGIN_ENV_NAMES`;
    - the watcher with `LOGIN_TIMEOUT` (10 minutes) and the part 5 stop;
    - then the login check, and exactly one result line.
  - **`agent run` and `agent chat`** never start a login; their refusal names `umwayi agent login NAME`.
  - **Tests** (fake `node` as the login, a pty for the terminal cases):
    - a login that flips the status gives `Claude subscription OK (plan: max)` and 0;
    - a failed login, and an API key still in front, give 2 with the refusal line;
    - already a subscription: nothing started, 0;
    - the kill switch during the login gives 3 and nothing alive; the logbook and the limit give 2;
    - the planted secret, URL and code printed by the fake are never in the logbook or the queue;
    - the exact argv, and a scan that no argument list in any test has `--console`, `--email` or `--sso`;
    - the environment names: listed names only, `BROWSER`, `DISPLAY` and `SSH_TTY` when set, never `CLAUDE_CODE_OAUTH_REFRESH_TOKEN`, `CLAUDE_CODE_OAUTH_SCOPES`, `CLAUDE_CODE_REMOTE` or `ANTHROPIC_API_KEY`;
    - rules No, Ask me first, run lock and a failing gate check start nothing;
    - a Claude Code cli agent: 64;
    - exit codes only 0, 2, 3 and 64.
  - **Planted faults:** `--console` in place of `--claudeai`; the check after the login skipped.
  - **Mutation checks:**
    - `--email` added;
    - stdout piped and read;
    - the environment widened to `os.environ`;
    - a listed name replaced by `CLAUDE_CODE_OAUTH_REFRESH_TOKEN`;
    - the kill switch not watched during LOGIN;
    - "already OK" still starting the login;
    - the action type left as `agent_run`;
    - `agent chat` starting a login.
  - **Counts** in the pull request.
  - **KNOWN-LIMITS:**
    - `--claudeai` not in the CLI reference;
    - the login's own exit code not documented;
    - the browser opener not documented;
    - what the login prints stays in the terminal's scrollback.
- [x] 10.39 (PR 28) Kiro, subscription first (1.5 h):
  - **What changes:**
    - `kiro_env()`, with `KIRO_API_KEY` removed for every Kiro start, `whoami` and `login`;
    - the Kiro login check `[KIRO, "whoami"]` by exit code only, output discarded, 15 s, after "version";
    - `umwayi agent login NAME` for a Kiro agent: `[KIRO, "login"]`, no flags, then the `whoami` check.
  - **Tests:**
    - the fake `kiro-cli` records `KIRO_API_KEY` absent for run, cli chat, ACP chat, `whoami` and `login`, with it set in every test;
    - `whoami` exiting 1 or hanging refuses with exit 2 and starts nothing;
    - its output, with a planted email, is never shown;
    - no Kiro argument list holds `--auth-method`, `logout` or a login flag;
    - the part 4 and part 6 Kiro tests still pass.
  - **Mutation checks:** `KIRO_API_KEY` left in; the `whoami` exit code ignored; `whoami` output printed.
  - **KNOWN-LIMITS:**
    - the `whoami` exit code when signed out is not documented;
    - headless Kiro without `KIRO_API_KEY` is not confirmed (the docs conflict);
    - the plan and credits cannot be read.
  - **The owner's real check (10.31):** `kiro-cli whoami` exit code signed in and signed out, and one Kiro `agent run` without `KIRO_API_KEY`.

### Other platforms: OpenCode and Muse Spark Open (spec tasks only, written Nov 9 2026, waiting for owner approval)

design.md "OpenCode as a platform" and "Muse Spark Open as a platform"; facts in `adapters/NOTES-layer10.md` (sections of the same names). Nothing is built. Each task below writes a spec (requirement, design and build tasks) after the owner answers that section's open questions. The build is proposed for after Dec 3.

- [ ] 10.41 The spec of the OpenCode adapter (2 h, spec only), from the answers to OC1 to OC6:
  - **What it specifies:**
    - `platform: opencode` with transport acp (`[OPENCODE, "acp"]`), and agents.yaml keys `provider` and `model`;
    - the environment allow list without provider keys and without `OPENCODE_CONFIG`, `OPENCODE_CONFIG_DIR` and `OPENCODE_DB`;
    - the one generated inline config: every action `ask`, `provider.use` and `integration.use` allowing only the chosen free or subscription provider, the fixed model;
    - the first gate (the umwayi plugin with `tool.execute.before` and the `session.created` canary, or the owner's alternative);
    - the gate checks, including the managed-config refusal and the minimum version;
    - the answers to permission requests (`once` or `reject` only, never `always`);
    - the failure table and KNOWN-LIMITS.
  - **Facts to check first**, each recorded in NOTES with the date:
    - V2 support for `OPENCODE_CONFIG_CONTENT`;
    - plugin loading from an absolute path;
    - the `toolCall` fields of an OpenCode permission request;
    - `opencode debug config` in V2;
    - the first V2 version number.
- [ ] 10.40 The spec of Muse Spark Open as an OpenCode model (1.5 h, spec only, after 10.41), from the answers to MS1 to MS5:
  - the local provider entry (vLLM or another OpenAI-compatible server with tools enabled, a loopback or private URL only);
  - the recommended settings (temperature 1.0, top_p 1.0, an explicit `reasoning_effort`);
  - the refusal of any route that is not free or a subscription;
  - the later paid route behind the budget governor (OpenRouter's prepaid credits first);
  - the "Built with Muse Spark Open" notice after the owner has read `LICENSE.md`;
  - whether Muse Code becomes its own platform (MS3).

## Layer 11: Linux-like features (approved; 11.1 to 11.5 built Nov 10 in PR 31, moved up from Nov 14 to Nov 15 by L11-Q14; 11.6 waits for the owner)

Requirements 11.R1 to 11.R8, design.md "Layer 11" (the candidates, the templates, the open questions L11-Q1 to L11-Q14), facts in `adapters/NOTES-layer11.md`. Approved (11.0). Scope: scheduled runs through systemd user timers only; file watching and tmux cut, SQLite and bubblewrap deferred to after Dec 3 (11.R8). Effort about 11 hours plus 0.5 hour of the owner's. Every test runs `python -m umwayi schedule ...` as a real child process with `HOME` and `XDG_CONFIG_HOME` in a temporary folder; no systemd, cron, network or credential.

- [x] 11.0 Requirements 11.R1 to 11.R8, the design section, these tasks and `adapters/NOTES-layer11.md` written (Nov 10) in PR 30, approved by the owner (PR 30 merged). Answers:
  1. L11-Q1: only scheduled runs for Dec 3.
  2. L11-Q2: systemd user timers installed by `schedule install`; cron lines only printed by `show --cron`.
  3. L11-Q3: umwayi writes the two unit files and prints the `systemctl --user` commands; it never runs `systemctl`, `crontab` or `loginctl`.
  4. L11-Q4: starter rule `schedule-install-ask` (Ask me first, `--approved-by WHO` goes on) and `schedule-remove-yes` (Yes).
  5. L11-Q5: only jobs and workflows can be scheduled; never `agent run`, `agent chat` or `agent login`.
  6. L11-Q6: `Persistent=true`.
  7. L11-Q7: `TimeoutStartSec=30min` for every scheduled run.
  8. L11-Q8: umwayi never enables lingering; install says timers run only while the owner is logged in otherwise.
  9. L11-Q9: `umwayi run` keeps layer 6's exit 1 for a refusal, shown as a failed unit; no `SuccessExitStatus`.
  10. L11-Q10: file watching cut for Dec 3.
  11. L11-Q11: SQLite deferred to after Dec 3.
  12. L11-Q12: tmux cut from umwayi; the README shows the hand route.
  13. L11-Q13: bubblewrap deferred to its own spec after Dec 3.
  14. L11-Q14 (changed by the owner): build now, right after PR 30 merged, not on Nov 14 to Nov 15. Nov 14 to Nov 15 is free; the hash chain (Nov 16), the budget governor and the rest of the schedule do not move.
- [x] 11.1 (PR 31) `schedule.yaml` and validation (2 h): `umwayi/schedule.py` reads the file with `miniyaml`; the keys, names, `run`, `every`, `at`, `day`; the cross checks against the jobs file (`min_gap_days` against the period) and the workflow; the path rule; `umwayi schedule validate`.
  - Acceptance tests: each bad shape of the design's validate table gives 64 with its line number and all problems at once; each path rule case (space, `%`, `$`, quotes, backslash, `;`, newline, non-ASCII, `..`) gives 64 with a message that holds no control character; a valid file gives 0; nothing is written in any case (folder snapshot equal); `schedule.example.yaml` validates.
- [x] 11.2 (PR 31) Rendering and `schedule show` (2 h): the two templates exactly as in the design; ROOTID; the calendar for daily, weekly and monthly; the cron line for `--cron`.
  - Acceptance tests: the exact bytes of the service and the timer for a job and a workflow on each `every`; the cron line for each; the same input gives the same bytes twice; two roots give two ROOTIDs; `show` writes nothing; the rendered text has no `%`, no `$` and no line holding text from outside the allowed sets.
- [x] 11.3 (PR 31) `schedule install` and `schedule remove` (3 h): the order of 11.R4 (validity, already installed, kill switch, rules with `schedule_install` and `schedule_remove`, `--approved-by`, the run lock for install, `O_CREAT | O_EXCL | O_NOFOLLOW`, folder `fsync`, one entry, undo on a logbook failure); the printed `systemctl --user` commands and the lingering line; the two starter rules in `rules.yaml`.
  - Acceptance tests: install with Yes (0, both files 0644, one entry with both hashes), No (2), Ask me first (3, one queue item, still one after a second call), `--approved-by` (0, WHO in the entry), kill switch on and unknown (3, one entry, no file), run lock held by another process (3), already installed (0, no entry), a different file present (2, untouched), the unit folder a link (2), a planted fault after the service is written (2, no file left), the logbook failing (2, no file left); remove when not installed (0), with the enable link (2 and the two commands), changed (2), a drop-in (2), No and Ask me first, the logbook failing (2, both files back byte for byte), success (0, one entry); remove works while the kill switch is on.
- [x] 11.4 (PR 31) `schedule check` (1.5 h): the states of 11.R3.3, drop-ins, the enable link, left over units of this root.
  - Acceptance tests: each state alone and all together; exit 0 only when every entry is installed and identical with no drop-in and nothing left over, else 2; check writes nothing and takes no lock.
- [x] 11.5 (PR 31) The scheduled run end to end, planted faults, mutation checks and docs (2.5 h):
  - The `ExecStart=` and `Environment=` of a rendered service run as a real child process in its `WorkingDirectory=`: a `queue-list` job (0, one entry), the kill switch on (3, one entry), the run lock held (3), a workflow stopping at its approve step (3, one queue item).
  - Code guards: `schedule.py` imports only the standard library and none of `subprocess`, `socket`, `urllib`, `http`, `ctypes`; no argument list in `umwayi/` names `systemctl`, `crontab` or `loginctl`; only exit codes 0, 2, 3 and 64.
  - Planted faults and mutation checks (the design's list), each killed by a named test, with the counts in the pull request; the full suite on Python 3.10 to 3.13.
  - KNOWN-LIMITS (the design's list, numbered from 93), README (the commands, the printed `systemctl` steps, lingering, and running a chat inside tmux by hand), `schedule.example.yaml`.
- [ ] 11.6 The owner's real check (0.5 h, the owner's; **not done**: the exact steps, the expected output and a results table are in `adapters/NOTES-layer11.md`, "The owner's real check (11.6)"), on a machine with a systemd user manager:
  - `umwayi schedule install NAME`, then `systemd-analyze --user verify` on both files: no warning;
  - `systemctl --user daemon-reload` and `systemctl --user enable --now UNIT.timer`; `systemctl --user list-timers` shows the next run;
  - `systemctl --user start UNIT.service` once: the logbook has the job's entry; `umwayi schedule check` says installed and enabled;
  - `umwayi kill on`, start the service again: `systemctl --user status` shows exit 3 and the logbook one stop entry; `umwayi kill off`;
  - `systemctl --user disable --now UNIT.timer`, `systemctl --user clean --what=state UNIT.timer`, `umwayi schedule remove NAME`, `systemctl --user daemon-reload`;
  - record in NOTES-layer11.md: the enable link path, the environment names the service got, and any `verify` output.

## Logbook hash chain (addendum, approved by the owner on Nov 9 2026; one day, Nov 16, after crash safety)

Requirements: Layer 5, "Logbook hash chain". Design: Layer 5, "Hash chain". Only `umwayi/logbook.py` and `umwayi/cli.py` change. Built after logbook crash safety (L5.1 to L5.5), so C.2 adds the chain walk to step 1 of its write and the chain cases to its recovery tests.

- [x] C.0 Requirements, design and these tasks written (Nov 9) in PR 24, approved by the owner on Nov 9. Answers:
  1. C-Q1: `umwayi logbook seal --chain --by NAME`, allowed once on a logbook that is already sealed and intact (no separate `chain-start`).
  2. C-Q2: recompute the chain on every append (no cache).
  3. C-Q3: verify keeps exit codes 0 and 1.
  4. C-Q4 (changed by the owner): the whole-system test and security scan run after the budget governor is complete, Nov 23 to Nov 26; the chain stays Nov 15 and the governor Nov 17 to Nov 22. (Superseded Nov 9 by L-Q6: the chain is built Nov 16.)

- [x] C.1 (PR 32) The Chain line (2 h): `chain(prev, text)`, the five-field entry, the genesis from the file prefix, `render()` and `parse()` for four or five fields, the start of the chain through `umwayi logbook seal` (and `--chain` once on a sealed logbook, C-Q1). Tests: the first chained entry's previous value is the prefix hash; old entries untouched byte for byte; the seal entry is chained.
- [x] C.2 (PR 32) The checked append and `check_writable` (2 h): walk the chain under the lock after the whole-file hash; refuse a broken chain or a missing Chain line after the start; an agent start and a running agent stop with exit 2 through the existing checks. Tests: a planted edit in an old chained entry, the newest entry, a deleted entry, a reordered pair, a truncated tail, each refuses every append and every `agent run` and `agent chat` start (exit 2, nothing started); the kill switch still works.
- [x] C.3 (PR 32) `verify` and `anchor` (2 h): the first broken entry by number and line, never its text or Chain values; `umwayi logbook anchor` prints `COUNT:HEX`, refuses a broken logbook; `verify --anchor` finds a shorter or different chain, and a consistently rewritten whole chain (with its hash record) passes plain verify but fails against the anchor. Tests: every message; a planted secret in an entry never in any output; a malformed anchor is 64.
- [x] C.4 (PR 32) Docs, planted faults and mutation checks (1 h): KNOWN-LIMITS (without an outside anchor a writer can rewrite the whole chain; anchor weekly and before each submission in the hub repo sync log and the Kiro Notion page), README; planted faults (the previous value not used; the Chain line not checked on append; verify printing the line); mutation checks (the genesis taken from the whole file instead of the prefix, the anchor count not compared, the anchor value not compared, a missing Chain line accepted); counts in the pull request.

## Logbook crash safety (addendum, approved by the owner on Nov 9 2026; about 10.5 h, Nov 10 to Nov 11, before 7c-2)

Requirements: Layer 5, "Logbook crash safety". Design: Layer 5, "Crash safety", with open questions L-Q1 to L-Q6 (answered Nov 9). Found behind the flaky Ctrl-C and SIGHUP test (PR 25). Built right after PR 26 merges, on branch `feature/layer-5-crash-safety`. Code: `umwayi/logbook.py`, `umwayi/fsutil.py` and `umwayi/cli.py`.

- [x] L5.0 Requirements, design and these tasks written (Nov 9) in PR 26, approved by the owner on Nov 9. Answers:
  1. L-Q1: `fcntl.flock` on `.umwayi/logbook.lock`, kept and never deleted (not PID plus start time).
  2. L-Q2: the four signals blocked in the writing thread and their Python handlers deferred for the same span; logbook writes only in the main thread.
  3. L-Q3: a torn tail is refused, and `umwayi logbook recover --torn-tail --by NAME` cuts it back, only when the extra bytes are exactly a prefix of the intent's entry, and logs it.
  4. L-Q4: `read_checked` and `verify` read the two exact states as consistent while an intent is present.
  5. L-Q5: bytes appended by something else during a write are refused as a hand edit.
  6. L-Q6 (changed by the owner): built right after PR 26 merges, Nov 10 to Nov 11, before 7c-2; then 7c-2 and 7c-3 Nov 12 to Nov 13, layer 11 Nov 14 to Nov 15, the hash chain Nov 16, the governor Nov 17 to Nov 22, the scan Nov 23 to Nov 26; the rest unchanged.
- [x] L5.1 The lock (2 h): flock on `.umwayi/logbook.lock` (L-Q1), kept and never deleted, the inode check, the PID and start time for messages, the new busy message, refused where `fcntl` is missing. Tests: a writer SIGKILLed while holding the lock does not block the next; a live holder still gives the busy message after 3 s; the tests that plant a lock file (`tests/test_check_log.py`, `tests/test_logbook_integration.py`, `tests/agents/support.py`) hold a real lock instead.
- [x] L5.2 The intent and the write order (2 h): `.umwayi/logbook.pending` in its format, written whole; steps 3 to 6 as named functions; the record only when the file is exactly `after` (L-Q5); the folder fsyncs. Tests: the intent's format and its bad forms; bytes appended by something else during a held write are refused; the order of fsync, rename and append (in-process).
- [x] L5.3 Recovery (3 h): the four states of the table, the recovery as one write with its own intent, the recovery entry, recovery in `check_writable`, the readers and `verify` (L-Q4), the torn tail message and `umwayi logbook recover --torn-tail --by NAME` (L-Q3). Tests: SIGKILL after each step; the power cut cases; every other mismatch refused; a hand edit while a dead writer's intent is present refused; two writers after a crash give one recovery entry; a recovery SIGKILLed half way is resumed; no logbook text in any output.
- [x] L5.4 Signals (1 h): the four signals blocked and their handlers deferred around steps 3 to 6 and around a recovery, delivered once afterwards; a write outside the main thread refused (L-Q2). Tests: SIGTERM, SIGHUP, SIGINT and SIGQUIT during a held write leave a whole write, no intent and no recovery entry; agent run with the planted pause and Ctrl-C, SIGHUP and SIGTERM writes its stop entry and the logbook verifies (the PR 25 defect, end to end).
- [x] L5.5 Docs, planted faults and mutation checks (2.5 h): KNOWN-LIMITS (the list in the design) and item 39 updated (no stale lock any more), the Layer 5 "Still open" note above closed, README; the chain cases go to C.2 (Nov 16); mutation checks (recovery accepting any mismatch, the record written without the hash comparison, the intent not fsynced, the folder fsync dropped, the handler swap dropped, the recovery entry not written, the intent removed before the record, the torn tail cut accepting any tail); the full suite on Python 3.10 to 3.13 and the stop tests 20 times under load; counts in the pull request.

## Whole-system test and security scan (not started, planned Nov 23 to Nov 26, after the budget governor is complete)

- [ ] S.1 Whole-system test again, with the adapters, layers 10 and 11, the logbook hash chain and the budget governor including the telemetry receiver (includes 9.11 and 10.21)
- [ ] S.2 Security scan of the code and the dependencies of any adapter package, and of the telemetry receiver (loopback binding only, the run header, the size caps)

## Budget governor (approved by the owner on Nov 9 2026; build Nov 17 to Nov 22)

Requirements B.R1 to B.R3, design.md "Budget governor" (with the dated doc facts), open questions B-Q1 to B-Q6. It needs the logbook hash chain (C.1 to C.4) first, because settled readings are chained entries. Every test runs `python -m umwayi ...` as a real child process with a fake telemetry sender; no real Claude Code, no network, no key.

- [x] B.0 Requirements B.R1 to B.R3, the design section and these tasks written (Nov 9) in PR 24, approved by the owner on Nov 9, with B-Q1 to B-Q6 all as proposed:
  1. B-Q1: the ledger is read from chained logbook entries only (no `.umwayi/ledger.jsonl`).
  2. B-Q2: an unknown run counts at 100 UU, the worst case, including Kiro, until a rate is declared.
  3. B-Q3: `calibrate` only proposes; the owner edits `units.yaml`, and the change is logged (no `--apply`).
  4. B-Q4: a reservation without a settle stays counted in full until `umwayi budget settle-lost --by NAME`.
  5. B-Q5: forged telemetry reports are accepted as a known limit, written in KNOWN-LIMITS.
  6. B-Q6: the cap and the receiver also cover the terminal (cli) chat.
- [x] B.1 (PR 33) `umwayi/units.py` and `units.yaml` (3 h): the schema (platforms, models, rates with value, date and source, limits in UU), validation with line numbers (64), whole micros, `uu(micros) = ceil(micros / 10000)` only when checked or shown. Tests: every bad value with its line; floats refused; a rate without a date or source refused; a future date refused; a missing file is all unknown under the placeholders.
- [x] B.2 (PR 33) Readings and tags (2 h): `usd_micros` measured, `tokens` times rates per model and type, `credits` times a rate, `runs` times a flat value, each declared; unknown at `unknown_worst_case`, never zero; an unknown model or type is unknown. Tests: each kind, rounding up, an unknown model, a zero reading measured as zero but a missing one never zero.
- [x] B.3 (PR 33) The ledger in the logbook (3 h): the reserve, settle and change entries in their fixed shapes, chained; `budget.py` reads them back; a malformed `umwayi budget` entry is a logbook problem; a reservation without a settle counts in full (B-Q4). Tests: parse round trip; a hand-edited budget entry breaks the chain and stops starts.
- [x] B.4 (PR 33) Reserve, settle, release and the limits (4 h): the reservation against per run, per day, per agent per day and per platform per day; no start when it does not fit (exit 3, one entry, nothing started); settle on every way out (normal end, refusal after the reservation, kill switch, timeout, SIGTERM, crash); release the rest; an overrun is settled as measured. Tests: each limit refusing in turn; the kill switch and a logbook failure winning; settle after every way out.
- [x] B.5 (PR 33) Rate changes and calibration (2 h): the `units.yaml` change entry before first use (2 when it cannot be logged); `umwayi budget calibrate` proposes per run 1.5 times p95 and per day 2 times the median day after at least 20 measured runs over 7 days, with its data (B-Q3). Tests: a rate change logged once; 19 runs or 6 days give no proposal; the proposal numbers on a fixed data set.
- [x] B.6 (PR 33) The telemetry receiver (3 h): `umwayi/telemetry.py`, `ThreadingHTTPServer` on 127.0.0.1 port 0 for one run; loopback only, the two paths, the run header compared in constant time, `Content-Length` required, 1 MB per body, 16 MB per run, JSON only; counts only from `claude_code.cost.usage`, `claude_code.token.usage` and `claude_code.api_request`; the body dropped after parsing; numbers from 0 to 10^12 or the run is invalid. Tests with a fake sender: each rejection answered and counted, never read; huge, negative, float and string numbers; a body with prompt text never kept or printed.
- [x] B.7 (PR 33) The telemetry environment and the run entry (3 h): `TELEMETRY_ENV` (`CLAUDE_CODE_ENABLE_TELEMETRY=1`, `OTEL_METRICS_EXPORTER=otlp`, `OTEL_LOGS_EXPORTER=otlp`, `OTEL_EXPORTER_OTLP_PROTOCOL=http/json`, the local endpoint, the run header, 5000 ms intervals, delta temporality, `OTEL_LOG_USER_PROMPTS=0`, `OTEL_LOG_ASSISTANT_RESPONSES=0`, `OTEL_LOG_TOOL_DETAILS=0`, `OTEL_LOG_RAW_API_BODIES=0`, `OTEL_TRACES_EXPORTER=none`) for `agent run`, the cli chat and the ACP chat; every other `OTEL_*`, `BETA_TRACING_ENDPOINT` and `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA` removed; the names added to `CHILD_ENV_SET` and to the 10.R11.9 and 10.R12.6 environment tests (built: added to the agent's own start, not to `CHILD_ENV_SET`, so the gate check programs get none; design.md "Added while building"); the mid-run cap check in the watcher (stop, exit 3); the 6 s grace; one settle entry per run (run id, models, tokens by type, micros and UU, requests, tag); no report is unknown. Tests: the fake `claude` and fake ACP agent send scripted exports; the agent gets exactly these names; an owner `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` never reaches it.
- [x] B.8 (PR 33) `budget_check` and `umwayi budget status` (2 h): the action type in the rules after the reservation fits (Yes, No 2, Ask me first 3 with one queue item, once); its place in the start steps; `status` with used, reserved and left per limit and the measured, declared and unknown shares. Tests: Yes, No and Ask; status on a fixed ledger; status writes nothing.
- [x] B.9 (PR 33) The governor tests listed in B.R3.2, end to end (3 h): missing telemetry, huge numbers, a wrong header, an oversize body, a rate change, a limit hit before the start and in the middle of a run; planted faults (unknown counted as zero; the reservation skipped; the header not checked; the per-run cap not checked mid run) and mutation checks; counts in the pull request.
- [ ] B.10 (umwayi's part built in PR 33: the capture mode `UMWAYI_TELEMETRY_CAPTURE`; the owner's capture is not done) One real export (0.5 h, the owner's): run one short Claude Code `agent run` with the receiver in a capture mode that writes field names and shapes only (never values) to a scratch file; record them in NOTES-layer10.md with the date; adjust the parser if they differ from the docs.

## Non goals for Dec 3

Finance and marketing loops, web interface, shared rule packs (after Dec 3). File watching, an SQLite index, tmux sessions and a sandbox (layer 11 proposes to cut or defer them, 11.R8).
