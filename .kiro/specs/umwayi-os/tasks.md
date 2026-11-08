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
| 10 Own command line and chat | in progress: spec approved (10.0); all six parts built (agents.yaml, gate checks, `umwayi agent check`, `umwayi agent run` and `umwayi agent chat` with transport cli for Claude Code and Kiro, ACP chat for Kiro); 10.20 and 10.21 open; part 7 (Claude Code over ACP, 10.22 to 10.31) specified, waiting for owner approval | spec PR 13; parts 1 and 2 PR 14; part 3 PR 15; part 4 PR 16; part 5 PR 17; part 6 PR 18 | 673 after PR 14, 697 after PR 15, 719 after PR 16, 747 after PR 17, 783 after PR 18, on Python 3.10 to 3.13 |
| 11 Linux-like features | not started, planned Nov 9 to Nov 10, after the owner approves requirements, design and tasks | | |
| Whole-system test and security scan | not started, planned Nov 11 to Nov 14 | | |
| Budget governor | not started, planned Nov 15 to Nov 21 (owner decided yes) | | |

Limits that are known and not fixed are listed in `docs/KNOWN-LIMITS.md` (numbered there, referred to below as KNOWN-LIMITS 1 to 28; items 12 to 28 are about the layer 9 adapters).

## Schedule to Dec 3

| dates | work |
| --- | --- |
| Nov 8 to Nov 9 | Layer 9 adapters (part 1 in PR 11, part 2 in PR 12) |
| Nov 9 to Nov 10 | Layers 10 and 11. Each is built only after the owner approves its requirements, design and tasks. Layer 10 spec approved Nov 8; parts 1 and 2 built Nov 8 (PR 14) |
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

## Layer 10: Own command line and chat (all six parts built; 10.20 and 10.21 open)

Planned for Nov 9 to Nov 10. Requirements 10.R1 to 10.R10, design in design.md, doc facts in `adapters/NOTES-layer10.md`. The owner approved 10.0 on Nov 8.

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
- [ ] 10.21 Whole-system test with the front door (part of S.1, Nov 11 to Nov 14), and one real run of each platform by the owner, recorded in NOTES-layer10.md (what the docs did not confirm).

### Part 7: Claude Code over ACP (spec written Nov 8 2026, waiting for owner approval)

Requirement 10.R11, design.md "Part 7: Claude Code over ACP", facts in `adapters/NOTES-layer10.md` ("Claude Code over ACP"). Numbered from 10.22, because 10.20 and 10.21 are taken. Nothing below starts before the owner approves 10.22. Effort about 20 hours (hours per task in brackets; 1.5 of them are the owner's first real run). Every test runs `python -m umwayi agent ...` as a real child process with a fake `node` (`tests/agents/fake_node.py`, a Python script first on PATH) and the scripted fake ACP agent of `tests/agents/fake_agent.py` in a Claude flavour; no real Node, no real Claude Code, no network, no key.

- [ ] 10.22 Requirements 10.R11, the design section and these tasks written (Nov 8), **waiting for owner approval**, with the ten open questions of design.md part 7 answered.
- [ ] 10.23 agents.yaml and the platform table (1.5 h): `claude-code` with `transport: acp`; `permission_action` takes the platform; the pinned name and version constants. Tests: validation accepts it, still refuses `kiro_agent` and `trust_tools` for claude-code; `agent list` and `agent check` show it; the Kiro ACP action still says `kiro`, the Claude one `claude-code`.
- [ ] 10.24 `adapters/claude_acp/` (2 h): `package.json` with one exact dependency, `package-lock.json` made once with network access in the build pull request (`npm install --package-lock-only`), `README.md` with the owner's install command and how to update the pin, `.gitignore` for `node_modules/`, `canary.py` (standard library). Tests: the version in `package.json`, the lockfile root and `agents.CLAUDE_ACP_VERSION` are equal; no range characters; `node_modules/` is ignored and not committed; `canary.py` imports only the standard library, writes exactly one empty file with O_EXCL and refuses a token that is not 32 hex characters or a folder that is not absolute.
- [ ] 10.25 The gate checks (3 h), in the order of design.md: node on PATH, node at least 22, the adapter file, its `package.json`, `--version`, `--cli --version` at least 2.1.295, sign-in by exit code, the layer 9 hook and its self-test; and `child_env()`, the environment allow list. Tests with the fake node: each check failing in turn (no node, `v20.11.0`, garbage, the file missing or a link, another name, `0.100.9`, `--version` differing from `package.json`, Claude Code `2.1.294`, `auth status` exiting 1 or hanging), each exit 2 with nothing started; `agent check` prints every line; the fake records the environment names it got: only allow-listed names, never `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `CLAUDE_CODE_EXECUTABLE`, `NODE_OPTIONS` even when set, and `CLAUDE_AGENT_ACP_PROTOCOL=v1` always; the sign-in output (with a planted secret) is never printed or logged; every argument list has no shell and no forbidden flag.
- [ ] 10.26 The inline settings and the canary (2.5 h): `_meta.claudeCode.options` with `allowDangerouslySkipPermissions: false` and `settings` holding the `agent run` PreToolUse hook (the same `claude_settings` code) and the SessionStart canary; the private token folder, removed on every path. Tests: the fake receives exactly that `_meta`; the PreToolUse hook entry equals the one `agent run` passes; a fresh token each start; the folder is gone after a normal end, a refusal, the kill switch, SIGTERM and a crash.
- [ ] 10.27 `acp.py` options (2 h): `session_meta`, `gate_ready` (30 s), `set_mode`. Tests: canary seen: the chat goes on and `session/set_mode` `default` is sent before the first prompt; canary never run: exit 2, "could not be confirmed", no `session/prompt` sent, one refusal entry; canary run only at the first prompt (a fake option): refused; `session/set_mode` answered with an error: exit 2; a Kiro ACP chat sends no `_meta`, no `set_mode` and does not wait (unchanged).
- [ ] 10.28 The stop (1 h): process group and every seen descendant for ACP chats. Tests: a fake that starts a child in a new session and a background command that ignores `session/cancel`: the kill switch, the timeout, SIGTERM to umwayi and `:quit` leave nothing alive.
- [ ] 10.29 The chat end to end with the fake (3 h): a whole turn; tool calls in the fake run the PreToolUse hook first (the rules Yes, No, Ask me first for `tool_bash` and `tool_read`, one `umwayi check` entry each, `platform: claude-code`), then permission requests with the adapter's shape (`name`, `kind`, `rawInput`, `title`) answered by the rules; ExitPlanMode with only `allow_always` mode switches and one `allow_once` keeps `default`; a `kind` of `switch_mode` and `think`; nothing of the conversation, the token or the sign-in output in the logbook; exit codes as 10.R8.
- [ ] 10.30 Planted faults and mutation checks (2 h), the counts in the pull request. Planted faults: the canary wait skipped; `ANTHROPIC_API_KEY` passed to the child; the version pin not compared; `allowDangerouslySkipPermissions` left out. Mutation checks: each gate check removed or loosened (node 22 to 20, the pin compare, the CLI version compare, the sign-in exit code), each allow-list exclusion removed, the canary token not compared, the set_mode error ignored, the stop without descendants, the platform in the action left as `kiro`; the Kiro ACP tests re-run on every mutation to show it is unchanged.
- [ ] 10.31 Docs and the first real run (3 h, 1.5 of them the owner's): KNOWN-LIMITS for what is not confirmed (when `SessionStart` runs in an SDK session; that the permission answer sees no command; supply chain; the adapter's speed of change), README, design and tasks ticked; then one real chat by the owner on a machine with Node 22 and a Claude Code login, recorded in NOTES-layer10.md: whether the canary ran before the first prompt, whether hook entries appear in the logbook for every tool call, the real `--version` outputs.

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
