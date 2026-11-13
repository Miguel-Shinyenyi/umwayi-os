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
| 9 Adapters | done (9.10, the repo rules.yaml, in PR 43; 9.11, the whole-system test, in PR 36) | PR 11 (part 1), PR 12 (part 2: Kiro, generic, kill switch) | 578 after PR 11, 619 after PR 12, on Python 3.10 to 3.13 |
| 10 Own command line and chat | in progress: spec approved (10.0); all six parts built (agents.yaml, gate checks, `umwayi agent check`, `umwayi agent run` and `umwayi agent chat` with transport cli for Claude Code and Kiro, ACP chat for Kiro); 10.20 and 10.21 open; part 7 (Claude Code over ACP, 10.22 to 10.31) approved (10.22), part 7a built (10.23 to 10.25), part 7b built (10.26 to 10.28), 10.29 and 10.30 done, 10.31 waits for the owner's first real run; part 7c approved (10.32), part 7c-1 built (10.33 to 10.35), part 7c-2 built (10.38, 10.39), part 7c-3 built (10.36), 10.37 open; OpenCode and Muse Spark Open specified (10.40, 10.41), build after Dec 3; part 8 (OpenCode over ACP, 10.R13) and Muse Spark Open as an OpenCode model (10.R14) specified Nov 11 (10.41, 10.40), approved (PR 44 merged); 10.42 (the facts on a real install) done; 10.43 and 10.44 built (agents.yaml and the inline config); 10.45 built (the plugin and the starter rules); 10.46 built (the gate checks); 10.47 to 10.50 built (the fake `opencode`, the chat start, the chat end to end, the planted faults and mutation checks); 10.51 open: its docs are written (Nov 13), and the owner's real check of the OpenCode chat is not done; Muse Spark Open after it | spec PR 13; parts 1 and 2 PR 14; part 3 PR 15; part 4 PR 16; part 5 PR 17; part 6 PR 18; part 7 spec PR 19; part 7a PR 20; part 7b PR 21; part 7c spec PR 22; part 7c-1 PR 23; part 7c-2 PR 28; part 7c-3 PR 29; part 8 and Muse Spark Open spec PR 44; 10.42 PR 46; 10.43 and 10.44 PR 47; 10.45 PR 53; 10.46 PR 55; 10.47 PR 62; 10.48 PR 66; 10.49 PR 71; 10.50 PR 74 | 673 after PR 14, 697 after PR 15, 719 after PR 16, 747 after PR 17, 783 after PR 18, 829 after PR 20, 854 after PR 21, 869 after PR 23, 929 after PR 28, 934 after PR 29, on Python 3.10 to 3.13 |
| 11 Linux-like features | approved (11.0); scheduled runs through systemd user timers built (11.1 to 11.5); 11.6 waits for the owner's real check; file watching and tmux cut, SQLite and a sandbox deferred | spec PR 30; build PR 31 | 978 after PR 31, on Python 3.10 to 3.13 |
| Logbook crash safety (Layer 5 addendum) | approved Nov 9 (L5.0); built Nov 10 (L5.1 to L5.5), before 7c-2 | spec PR 26; build PR 27 | 906 after PR 27, on Python 3.10 to 3.13 |
| Logbook hash chain (addendum) | approved Nov 9 (C.0); built early on Nov 7 (C.1 to C.4), planned Nov 16 | spec PR 24; build PR 32 | 1001 after PR 32, on Python 3.10 to 3.13 |
| Budget governor | approved Nov 9 (B.0); built early (B.1 to B.9 and the capture mode of B.10), planned Nov 17 to Nov 22; B.10 waits for the owner's capture of one real export | spec PR 24; build PR 33 | 1091 after PR 33, on Python 3.10 to 3.13 |
| Documentation layout (D.1) | added Nov 10 (PR 34); built Nov 10, before S.1 | spec PR 34; build PR 35 | 1104 after PR 35, on Python 3.10 to 3.13 |
| Whole-system test and security scan | approved Nov 10 (S.0, S-Q1 to S-Q16 as proposed); S.1 and S.2 built Nov 10; Python 3.10 end of life waits for the owner (KNOWN-LIMITS 133) | spec PR 34; S.1 PR 36; S.2 PR 37 | 1155 after PR 37, on Python 3.10 to 3.13 |
| 12 Web interface (the view) | in scope before Dec 3 since Nov 10; spec approved (UI.0, PR 38); look changed by the owner on Nov 11 (UI-Q12 to UI-Q16) and the hours cut (four cuts accepted); tiers, the public site and the scene additions decided in round 2 (UI-Q17 to UI-Q22); UI.1 and UI.1b (PR 39) built and merged; UI.2 (`umwayi view snapshot`) built (PR 41); UI.6 (the shared scene module and the public site, List and Standard) built (PR 50); UI.3 (PR 52) and UI.4 (PR 54) built; UI.7 (High, tier 3, on the public site) built in its own pull request; UI.5 not started | spec PR 38; UI.1 and UI.1b PR 39 (merged); UI.2 PR 41; UI.6 PR 50 | 95 Node tests in `ui/`, 25 in `site/`, 32 package tests for `ui/` and 41 for `site/`; 1200 after PR 41, on Python 3.10 to 3.13 |

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
| Nov 10 | Documentation layout (D.1): a short README and one doc per layer under `docs/`, right after PR 34 merges, before S.1 |
| Nov 10 to Nov 12 | Whole-system test and security scan (S.1, then S.2; approved, S.0), moved up by the owner from Nov 23 to Nov 26: the adapters, layers 10 and 11, the chain and the governor, including the telemetry receiver |
| Nov 11 to Nov 22 | Layer 12, the web interface, re-estimated on Nov 11 at about 92 hours still to do (does not fit about 60 to 72; design.md lists what I propose to cut): UI.1 (the highlands scene, PR 39 reworked) first, then UI.2, UI.3, UI.4, UI.5. The web interface is no longer a non goal (the owner, Nov 10) |
| Nov 23 to Nov 28 | README, demo, Devpost text (the scan moved up to Nov 10 to Nov 12) |
| set by the owner | Layer 10 part 8: OpenCode over ACP (10.42 to 10.51, about 21.5 hours plus 1.5 hours of the owner's), after the owner approves the spec (PR 44). The owner asked on Nov 11 for it to be built before Dec 3 and sets its dates. Muse Spark Open (10.52 to 10.55) follows it and is not scheduled before Dec 3 |
| set by the owner | W9.9 (7 h), the shared docs builder, also the owner's task W17: the only part of goal orchestration (W9) that may go before the freeze (W9-Q14, Nov 12). Build it at a quiet moment right after the pull request of the W6 first batch (W6.1 to W6.6) merges. The rest of W9 (W9.1 to W9.8, W9.6b and later, about 61 hours more) comes after Dec 3 |
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

## Layer 9: Adapters (done)

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
- [x] 9.10 (PR 43) Starter rules for adapter actions in the repo rules.yaml: every rule of `adapters/claude_code/rules.example.yaml`, `adapters/kiro/rules.example.yaml` and `adapters/stdio/rules.example.yaml` is in `rules.yaml` with the same id, verdict and matchers, each with a title, text and cause, plus a No for secret and key paths on Kiro and the generic adapter (`kiro-no-secrets`, `stdio-no-secrets`). Reading and listing is Yes; writing, shell commands, the web and deploys are Ask me first; wiping, pushing to main, money, the guard files and secret paths are No; no rule has `review_by`. The 15 older rules are unchanged and none conflicts. Test: `tests/test_starter_rules.py` (written first).
  - [x] 9.10b (PR 56, Nov 11) The 13 rules of `adapters/opencode/rules.example.yaml` (from 10.45, PR 53) are in the repo `rules.yaml` too, appended after the older rules: the same ids, verdicts, matchers and words, `platform: opencode`, no `review_by`; no existing rule changed (each of the 37 is pinned by a hash in `tests/test_starter_rules.py`, with 151 lines added and none removed). Code Mode (`tool_execute`, `tool_opencode_*`) has no rule on purpose (OC15, OC20), and a test fails if one is added. Tests first: the example's rules in the file, the decisions table run with the real `umwayi check` on a real root, the unchanged older rules, and planted faults (a verdict changed, a matcher dropped, a rule missing, an Ask rule for `tool_execute` added).
- [x] 9.11 (PR 36) Whole-system test again with the adapters (S.1): the Claude Code, Kiro and stdio hooks called as each platform runs them, and every agent start's tool calls through them
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
- [ ] 10.21 (The test part is done in PR 36, S.1: check, run, the cli chat and the ACP chat for Claude Code and Kiro. Left: the owner's real run.) Whole-system test with the front door, and one real run of each platform by the owner, recorded in NOTES-layer10.md (what the docs did not confirm).

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

### Other platforms: OpenCode and Muse Spark Open (spec tasks written Nov 9 2026; answered and specified Nov 11 in PR 44; waiting for the owner's approval)

design.md "OpenCode as a platform", "Muse Spark Open as a platform", "Part 8: OpenCode over ACP" and "Muse Spark Open as an OpenCode model"; requirements 10.R13 and 10.R14; facts in `adapters/NOTES-layer10.md` (the Nov 9 sections and "OpenCode V2: the facts checked for the adapter spec", Nov 11). Nothing is built. The owner answered on Nov 11: OC1 to OC5 and MS1 to MS4 as proposed; OC6 changed (OpenCode built before Dec 3, part 8 below); MS5 stands (Muse Spark Open spec only, built after OpenCode).

- [x] 10.41 (PR 44) The spec of the OpenCode adapter (2 h, spec only), from the answers to OC1 to OC6. Written Nov 11: requirement 10.R13, design.md "Part 8: OpenCode over ACP", the tasks of part 8 below, KNOWN-LIMITS 180 to 187, and the five facts in NOTES-layer10.md with dates and links. New open questions OC7 to OC14 (design.md); the spec uses each proposal. Waits for the owner's approval. What the task asked for:
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
  - **The facts, checked Nov 11** (NOTES-layer10.md): `OPENCODE_CONFIG_CONTENT` is read by the V2 source but is on no V2 docs page, and it is the weakest source for policies; a plugin loads from an absolute path only as a directory, with the V2 `ctx.tool.hook` API; the `toolCall` fields are known from the source and carry no permission action or resource; `opencode debug config` exists in V2 but asks the shared service; the first V2 release is 2.0.0 (Sep 11 2026), and the policies the design needs work from 2.2.3. Not confirmed: each of these on a real install, the `--version` text, and the Go provider ID.
- [x] 10.40 (PR 44) The spec of Muse Spark Open as an OpenCode model (1.5 h, spec only, after 10.41), from the answers to MS1 to MS5. Written Nov 11: requirement 10.R14, design.md "Muse Spark Open as an OpenCode model", tasks 10.52 to 10.55 below (not scheduled before Dec 3), KNOWN-LIMITS 188 and 189. New open questions MS6 to MS8. Waits for the owner's approval. What the task asked for:
  - the local provider entry (vLLM or another OpenAI-compatible server with tools enabled, a loopback or private URL only);
  - the recommended settings (temperature 1.0, top_p 1.0, an explicit `reasoning_effort`);
  - the refusal of any route that is not free or a subscription;
  - the later paid route behind the budget governor (OpenRouter's prepaid credits first);
  - the "Built with Muse Spark Open" notice after the owner has read `LICENSE.md`;
  - whether Muse Code becomes its own platform (MS3).

### Part 8: OpenCode over ACP (10.R13; specified Nov 11 in PR 44; the owner asked for the build before Dec 3; built only after the owner approves the spec)

Requirement 10.R13, design.md "Part 8: OpenCode over ACP". The build is about 21.5 hours plus 1.5 hours of the owner's, in the order below. Each task's tests are written before its code. Every test runs `python -m umwayi agent ...` as a real child process with a fake `opencode`, with `HOME` and `XDG_CONFIG_HOME` in a temporary folder, and no network. The plugin tests also run `node`. The owner sets the dates.

- [x] 10.42 (PR 46) Confirm the facts on a real install, before any code (1.5 h). Done Nov 11 on OpenCode 2.2.7 in a throwaway sandbox, results in NOTES-layer10.md ("OpenCode 2.2.7 on a real install").
  - Confirmed: the `--version` text (`opencode v2.2.7`); the plugin loading from the inline config, in Bun 1.4.4, with `spawnSync` and `node:fs` working; `session.created` 2 ms before the answer to `session/new`; the tools that ask; the local provider key `settings.baseURL`; the permission requests for `shell`, `read`, `edit` and a subagent.
  - Changed in the spec first: the `ASKED` list (OC9); Code Mode, a new question (OC15, KNOWN-LIMITS 190); the local provider entry, written now and without `models`; a silent model fallback, which the model compare catches (OC10); notes on OC11, OC13 and OC14.
  - Not confirmed: the Go route (the provider ID `opencode-go` only from the binary), `skill` with a real skill, `patch`, `list` and `websearch`.

  What the task asked for: In a throwaway sandbox, not on the owner's machine, install `@opencode/cli` at the newest 2.2.x with `--ignore-scripts` where possible. umwayi itself never installs it. Record in NOTES-layer10.md, with the date:
  - the exact `opencode --version` output;
  - that a plugin directory named only in `OPENCODE_CONFIG_CONTENT` loads, and that `node:child_process` `spawnSync` and `node:fs` work inside it;
  - when `session.created` reaches the plugin compared with `session/new`'s answer;
  - the V2 tool names that ask permission (the `ASKED` list);
  - the settings key for a built-in local provider's URL;
  - the provider ID and `integration.use` resource of OpenCode Go;
  - what a permission request looks like on the wire for `shell`, `read`, `edit` and a subagent.

  Any fact that differs from the spec is written in the pull request, and the spec is changed before code is written.
- [x] 10.43 (PR 47) agents.yaml (1.5 h): `opencode` in `PLATFORMS` (command `opencode`, transport `acp` only); the keys `provider` and `model`, only for OpenCode and required there; `run` and `login` refused for OpenCode. Tests: every allowed route; a missing `provider` or `model`; a `model` whose provider differs; a bad `model` pattern; `provider` on a Kiro agent; `transport: cli`; `agent run` and `agent login` give 64; `agent list` and `agent validate` show the agent.
  - Built Nov 11: `PLATFORMS["opencode"]` (command `opencode`, transport acp, minimum 2.2.3), `provider` and `model` on the record, `agent run` and `agent login` refused with 64 before the kill switch, the rules and the logbook, and `tests/agents/test_agents_opencode_file.py` (31 tests, real child processes with a spy `opencode`).
  - Two readings of the requirement, for the owner to confirm (OC16, OC17): the file checks only the shape of `provider` (a plain lowercase id), so a provider that is not an offered route is a valid agent that the route check refuses with exit 2 (10.46) and that `opencode_inline_config()` refuses now; and an omitted `transport` is acp for OpenCode, because it is the only one.
  - Until 10.46 and 10.48, `agent check` for an OpenCode agent says not gated (exit 2) without running `opencode`, and `agent chat` is still refused (64). Neither starts anything.
- [x] 10.44 (PR 47) The environment and the inline config (2 h): `opencode_env()` and `opencode_inline_config()`, both pure. Tests: the exact bytes for each route (free tier, `ollama`, `lmstudio`, `vllm`, `openai`, `github-copilot`); every name in 10.R13.4 planted in umwayi's environment and absent from the child's; a root path holding `{env:` or `{file:` is refused; the same agent and token give the same bytes.
  - Built Nov 11: `opencode_env(environ, content)`, `opencode_inline_config(agent, root, token, folder, python, src=None)`, `opencode_route()` and `OpenCodeRefused` in `umwayi/agents.py`, and `tests/agents/test_agents_opencode_config.py` (53 tests). Neither function is called yet: the start (10.48) and the gate checks (10.46) use them.
  - Planted faults: 42 faults, each caught by the new tests (the counts are in PR 47).
- [x] 10.45 (PR 53) The plugin (3.5 h): `adapters/opencode/plugin/index.js`, `tests/adapters/opencode_plugin_harness.mjs` and `adapters/opencode/rules.example.yaml`. Tests under `node`, with a fake `ctx` and a fake hook script that exits as told:
  - exit 0 lets the call run;
  - exit 2 throws;
  - exit 3 lets an asked tool run and throws for an unasked one;
  - a timeout, a missing hook and a start error each throw;
  - bad options stop `setup`;
  - the evaluate hook turns `allow` into `ask` and leaves `ask` and `deny`;
  - `session.created` twice writes the token once, with mode 0600, and an existing file is not overwritten;
  - the thrown text never holds the input.

  A Python test checks the source: only `node:` imports, no `eval`, `Function(`, `require(`, `fetch`, `http`, `net` or `dgram`. Without `node` on PATH the plugin tests fail with a message.
  - Built Nov 11: `adapters/opencode/plugin/index.js` (85 lines, imports `node:child_process`, `node:fs` and `node:path` only), `adapters/opencode/rules.example.yaml` (13 rules), `tests/adapters/opencode_plugin_harness.mjs` (a strict fake `ctx`), `tests/adapters/fake_gate_hook.py`, `tests/adapters/test_opencode_plugin.py` (76 tests, 8 of them with the real layer 9 generic adapter and a real root) and `tests/adapters/test_opencode_rules.py` (10 tests). Run under Node 18, 20, 22 and 24. GitHub's `ubuntu-latest` has Node 22.23.4 (Ubuntu 24.04) or 24.22.2 (Ubuntu 26.04), so CI needs no change.
  - Beyond the list above, fail closed: the hook's exit code and the decision in its one JSON line must agree (OC19); a tool name that is not a string, an input that is not an object, and any option that is missing or wrong throw; an `effect` that is not `ask` or `deny` becomes `ask`.
  - The rules example has no Ask rule for Code Mode (`tool_execute`, `tool_opencode_*`): Ask me first beats Yes, so such a rule would make the owner's Yes useless. They are Ask me first by default and the first gate stops them (OC20).
  - Planted faults: 50 faults in the plugin (41) and the rules example (9), 47 caught; the other 3 are checks that another check already covers (the counts are in PR 53).
  - Smoke test, not part of the suite: the real plugin, the real hook, the starter rules and the inline config of 10.44 on OpenCode 2.2.7 in a throwaway sandbox (PR 53).
- [x] 10.46 (PR 55) The gate checks (2.5 h): the six checks of 10.R13.8 in `agent check` and before every chat. Tests:
  - each check refuses on its own planted fault: no `opencode`, versions `1.18.30`, `2.2.2` and unreadable text, a link in place of `index.js`, a managed folder (the path made configurable for the test only), a project `opencode.json` and a `.opencode` folder two levels up, a global file holding `"policies"` and `"plugin"`, a global `plugins` folder, a file over 1 MB, a pay-as-you-go `provider`;
  - the refusal line names the path and never the file's text;
  - one logbook entry and nothing started each time.
  - Built Nov 12: `_opencode_checks()` in `umwayi/agents.py` (command, version, files, managed config, other config, route), used by `agent check` and before every chat, and `tests/agents/test_agents_opencode_gate.py` (72 tests, real child processes, a fake `opencode` that answers `--version`, a copy of the source tree for the planted links). `agent chat` for an OpenCode agent now takes the start steps (kill switch, rules, run lock, gate checks); a refusal writes one entry and exits 2. An agent that passes every check is still not started, with one entry that says the chat is not built (task 10.48). `tests/agents/fake_opencode.py` is the first part of the fake of 10.47 (`--version` and the call record); 10.47 adds ACP.
  - Beyond the list above (new questions OC21 to OC23): the plugin folder holds `index.js` and nothing else (OpenCode loads `server` before `index`); a `.opencode` in the home folder is refused like one in the workdir; the workdir is walked up by its real path as well as by the path given.
  - Planted faults: 37 faults in the checks and the wiring, 35 caught; the other 2 are checks that another check already covers (the counts are in PR 55).
- [x] 10.47 (PR 62) The fake `opencode` (2 h): `tests/agents/fake_opencode.py`. It answers `--version`; speaks ACP v1 (`initialize`, `session/new` with a `model` config option, `session/prompt`, `session/request_permission` with the V2 `toolCall` shape, `session/cancel`); writes the canary from the inline config's plugin options as the plugin would; and records its environment and argv for the tests. A script switches each behaviour: no canary, a late canary, a wrong token, another model, `auth_required`, a child-session request, a request with no `name`, ignoring stdin's end.
  - Built Nov 12: `tests/agents/fake_opencode.py` (`opencode acp` added to the `--version` part) and `tests/agents/test_fake_opencode.py` (52 tests; 1951 by discovery). The fake is steered by `opencode-fake.json` next to it, because umwayi gives OpenCode only an allow-listed environment; `AgentCase.fake_opencode(**cfg)` writes both files and passes ACP settings as `acp={...}`. It does not run the node plugin: it repeats the plugin's rule in Python (hook in exec form; exit 0 with `allow` goes on; exit 3 with `ask` goes on only for the nine tools OpenCode asks permission for; anything else fails the call with the fixed text and no request), and the tests drive it with the real stdio hook and the starter rules. Settings beyond the list: `ignore_config` (no plugin, no canary, the free default model), `init` (garbage, another protocol version, an error), `turns` with `chunk`, `tool`, `sleep`, `wait_cancel`, `exit` and `spawn`, `stderr`. An inline config that is not JSON ends it with exit 1.
  - Planted faults: 55 faults in the fake (canary mode, O_EXCL, wrong and late token, hook verdict, ask for tools not asked, denied text, request kinds, options, answers, child meta, no `name`, shell cwd, diff, ignored config, model, auth_required, cancel, SIGTERM, bad config, ignore_eof, records); all 55 caught, one (set_mode left unanswered) by a hang that the 100 s limit of the check ended. Three survived the first round and got tests (hook verdict cross-check, ask rule without the plugin, sleep).
- [x] 10.48 (PR 66) The chat start (2.5 h): the private folder and token; `Popen([OPENCODE, "acp"])`; `expect_model` in `acp.py`; the canary wait through `gate_ready`; `auth_required`; the 7b stop. Tests: canary seen; never seen; seen after 30 s; a wrong token; another model; `auth_required`; for each, the exit code, one entry, nothing of the owner sent and nothing alive. The folder is gone after a normal end, a refusal, the kill switch, SIGTERM and a crash.
  - Built Nov 12: in `umwayi/agents.py` the chat start of an OpenCode agent replaces the step that refused it: the private folder (0700, outside the root and the workdir, made by `_canary_folder()` and removed by the same stack as for Claude Code) and a fresh `secrets.token_hex(16)`, `opencode_inline_config()`, `Popen([opencode, "acp"])` in its own session with `opencode_env()` (the allow list plus `OPENCODE_CONFIG_CONTENT`), `initialize` with `clientCapabilities: {}`, `session/new` with no `_meta`, no `session/set_mode`, no login. `_opencode_ready()` is the canary wait: the file `canary` in the folder must be a regular file (no link) of exactly the token, read at most 129 bytes. In `umwayi/acp.py`, `Chat` takes `expect_model` (the `model` option's `currentValue` must equal the agent's model, else exit 2 before the first prompt) and `sign_in` (the line for `auth_required` at `initialize`, `session/new` or `session/prompt`: "Run opencode auth login first, then try again."). `agent check` prints the argument list that a chat would start. `build_argv` has an OpenCode branch for the chat only.
  - Tests: `tests/agents/test_agents_opencode_chat.py` (40 tests, real child processes, the fake of 10.47): canary seen, late within the wait, never seen, seen after the wait, a wrong token, written only at the first prompt, token plus more, a link; another model (four spellings); `auth_required` at `session/new` and at the first prompt; each with the exit code, one entry, nothing of the owner sent, nothing alive and the folder gone. The folder is gone after a normal end, the end of input, an agent that ignores it, the kill switch, SIGTERM, the timeout and a crash of the agent. Also: argument list, own session, allow-listed environment, the inline config byte for byte, a fresh folder and token for every start, the folder's mode, nothing of the conversation, token or config in the logbook, a TMPDIR inside the root or the workdir, and a path OpenCode would substitute (`{env:`).
  - "Seen after 30 s" is read as two tests: a canary that comes late but inside the 30 s (accepted, and the prompt comes after it) and one that comes after the wait is over (refused). The test run shortens the wait with `UMWAYI_TEST_GATE_WAIT`, as for Claude Code.
  - Two old tests were changed because they asserted the 10.46 refusal ("the OpenCode chat is not built yet"): they now assert that a passing agent starts and that a failing gate check still refuses.
  - Planted faults: 28 in the start (canary compare, link, read size, wait not wired, model not passed or compared, option id, case folding, sign-in text, environment, argument list, folder and token, root, workdir and mode checks, summary, `agent check` line, tracking, config refusal); 25 caught (5 of them by a hang that the 200 s limit of the check ended), 3 survived on the first round. One got a test (the config refusal). Two survive: the folder mode check (`tempfile.mkdtemp` always makes 0700, so the check is a second guard that no test can reach) and the last `_track()` before a clean exit (the watcher has already tracked the children by then, so the outcome is the same). The counts are in PR 66.
  - New questions: OC24 (a prompt error that mentions "auth" is shown as a sign-in request, KNOWN-LIMITS 242) and OC25 (the model compare is exact text, KNOWN-LIMITS 243).
- [x] 10.49 (PR 71) The chat end to end and the permission answers (2.5 h): a whole turn with the fake. Each tool call first runs the real plugin's hook script (the stdio adapter with `--platform opencode`), then a permission request. Cover:
  - the rules Yes, No and Ask me first, with the owner's `y` and `n`;
  - `always` never selected;
  - a child-session request;
  - a request with no `name` gives at most Ask me first;
  - one `umwayi check` entry per check, with `platform: opencode`;
  - nothing of the conversation, the token or the inline config in the logbook;
  - the kill switch mid-turn gives 3;
  - a Kiro ACP chat and a Claude Code ACP chat are unchanged.
  - Built Nov 12: `tests/agents/test_agents_opencode_turns.py` (17 tests, real child processes, the fake of 10.47 running the real stdio hook with `--platform opencode`, then the permission request): Yes, No and Ask me first with the owner's `y` and `n` (anything but `y` is a reject), `always` never selected, a child-session request, a request with no `name`, one `umwayi check` entry per check (the logbook keeps no action JSON, so `platform: opencode` is shown by the rules that match it and by the same rules for another platform matching nothing), nothing of the conversation, token, folder or inline config in the logbook or queue, and the kill switch in the middle of a turn (exit 3). One defect found by the tests: a request with no `name` could get Yes from a rule on its kind. `Run._permission` in `umwayi/agents.py` now asks the owner instead (`_has_tool_name`, KNOWN-LIMITS 248); `umwayi/acp.py` is unchanged. The test file is also in `tools/ci_shards.json` (all files rebalanced by `tools.ci_shards balance`), `tools/ci_map.json` and `docs/testing.md`, which the CI checks require. Kiro and Claude Code ACP chat tests unchanged and green.
- [x] 10.50 (PR 74) Planted faults and mutation checks (2 h), with the counts in the pull request.
  - **Planted faults:** the canary wait skipped; `OPENCODE_API_KEY` passed to the child; the version not compared; the `ask` rule left out together with the evaluate hook; the project-config check skipped.
  - **Mutation checks:** each gate check removed or loosened; each allow-list exclusion removed; each policy statement removed or reordered; the plugin's exit 3 allowed for every tool; the token not compared; `always` allowed; the model compare removed.
  - Built Nov 12: `tests/agents/opencode_mutants.py`, a helper that is not shipped. A fault is one or more text edits to `umwayi/agents.py`, `umwayi/acp.py` or the plugin. The helper copies the source (`umwayi/`, `adapters/`, `tests/`, `rules.yaml`) to a throwaway folder, applies one fault there (it refuses the real tree), checks that the mutated file compiles (`node --check` for the plugin), runs only the tests that should catch it with `unittest -f` and a time limit (a hang counts as caught), and runs a catch once more on an unmutated copy (a failure there too makes the fault `invalid`, not `caught`). `--wide` runs a survivor against the whole OpenCode suite. `python -m tests.agents.opencode_mutants --list`, `--only ID_OR_GROUP`, `--jobs N`, `--markdown FILE`. It takes about 10 minutes with 6 jobs and is not part of the suite or of CI. `tests/agents/test_opencode_mutants.py` (19 tests) keeps the table true in the suite: every anchor matches the stated number of times, every mutated file compiles, every named test exists, the runner reports caught, survived, a hang and invalid on small faults, and the real source is never touched.
  - Counts: 153 faults. 5 planted (A1 to A5) and 148 mutations: gate checks 64 (command 2, version 7, files 9, managed config 8, other config 30 with each project name, global entry, global file and quoted key one by one, route and wiring 8), allow list 25 (19 excluded names added one by one, no list, every OPENCODE_ name, a planted config variable kept, a value that is not text, a NUL character, the chat start's environment), policy statements 26 (the ask rule, each of the four policies removed, flipped or widened, four reorders, model, plugin, hook arguments, local server settings, three input checks), plugin 8, token 6, `always` 5, model compare 6, second gate 5, and the three earlier survivors 3. Result: 149 caught, 4 survived, 0 invalid, 0 hangs.
  - Round 1, with the tests as on main: 12 gaps, each now has a test in `tests/agents/test_agents_opencode_faults.py` (21 tests): a second managed folder, a dangling link at the managed plist, a workdir reached through a link (the path as given), a global config folder that cannot be examined, a plugin folder that cannot be listed, a session that names no model (the fake gained `model_option`), the kill switch and an error in `Run._permission`, a crash in the permission callback, and the three survivors of 10.48 and 10.49 (folder mode, last `_track()`, check not logged). Two more survivors of round 1 were wrong test lists in the table (the NUL check and the plugin's missing tool name), which existing tests catch once listed.
  - One defect, proved by the new test for the last `_track()`: the OpenCode chat stopped only the agent's process group, so a background command in a session of its own outlived a `:quit` and the kill switch. The design says the 7b stop (group and every seen descendant). `stop_agent` now uses `_stop_group_and_seen()` for an OpenCode chat as for Claude Code (two lines in `umwayi/agents.py`). The reason the old survivor survived was that the `_track()` before the clean exit fed a set that nothing read for OpenCode.
  - Survivors, 4, each a guard with a twin that refuses the same case: the "is a link" refusal (B3b) and `lstat` for `stat` (B3e) in the files check, and the two size checks of a global config file (B5l, B5m). Removing both of each pair is caught (B3x, B5lm). They are in KNOWN-LIMITS 250 with two smaller limits of the method (the runs are manual; one catch depends on the one-second watcher interval).
- [ ] 10.51 Docs and the owner's real check (1.5 h, plus 1.5 h of the owner's):
  - `docs/agent-front-door.md`, the adapter README and the main README;
  - KNOWN-LIMITS 180 to 187 made true to what was built;
  - design.md and these tasks ticked (10.47 to 10.50 only).

  - Docs half built Nov 13 (this task is not ticked): `docs/agent-front-door.md`, `docs/adapters.md`, the new `adapters/opencode/README.md` and the main README describe the chat as built; KNOWN-LIMITS 180 to 187 were read against `umwayi/agents.py`, `umwayi/acp.py` and the plugin and corrected in the frozen base (numbers fixed), 251 was added as a limits part, and 248 was corrected (an MCP name such as `mcp__x__y` is a plain word and is sent to the rules). Two places where the design and the code differ are in design.md "As built": OpenCode's stderr is not discarded but reaches the terminal, and umwayi gives OpenCode no private `HOME` (KNOWN-LIMITS 251). The owner's check is now a numbered list with a results table in `adapters/NOTES-layer10.md`, "The owner's real check of the OpenCode chat (10.51)". `tests/agents/opencode_mutants.py` was run once on the final tree; the result is in the pull request.

  Then the owner's own chat, recorded in NOTES-layer10.md: OpenCode 2.2.3 or newer on the owner's machine, the free tier or a local model; the canary seen; one hook entry per tool call; the real `--version` output; a refusal with a planted project `opencode.json`. On the first run the owner also looks at what OpenCode wrote in its private `HOME` (for example the downloaded `rg` in its cache, KNOWN-LIMITS 191) and records it. 10.51 is ticked only after that.

**What could be cut if time runs short.** The owner decides; nothing here is cut by the spec. Each item says what is lost.

| could be cut | saves | what is lost |
| --- | --- | --- |
| the ChatGPT and Copilot routes (part of 10.43 and 10.44) | about 1 h | only the free tier and local models work; the subscription routes wait |
| the OpenCode Go route (OC13, part of 10.42) | about 0.5 h | Go stays refused, as it is until confirmed anyway |
| the model compare (OC10, part of 10.48) | about 0.5 h | a wrong model in the inline config is not caught; the provider policy still limits who pays |
| the evaluate hook (OC8, part of 10.45) | about 0.5 h | the second gate depends on the inline `ask` rule alone; the first gate still checks every call |
| the mutation checks of 10.50 (keeping the planted faults) | about 1 h | weaker evidence that the tests catch a change that loosens the gate |
| `rules.example.yaml` (part of 10.45) | about 0.5 h | no starter rules; every OpenCode call is Ask me first until the owner writes rules |

**Not to be cut:** the plugin's `execute.before` gate; the canary and its wait; the environment allow list; the six gate checks; the fake and the end-to-end tests; the KNOWN-LIMITS items. Without any one of these the chat could run ungated, or the gate could not be shown to work.

### Muse Spark Open as an OpenCode model (10.R14; specified Nov 11 in PR 44; built after part 8, not before Dec 3 (MS5))

Requirement 10.R14, design.md "Muse Spark Open as an OpenCode model". About 6 hours plus 0.5 hour of the owner's, after part 8 is merged. Not scheduled before Dec 3.

- [ ] 10.52 Confirm the custom provider fields (1 h): on a real install, with any small local model served by vLLM or llama.cpp standing in, the V2 field names for tool calls, temperature, top_p and the reasoning effort on a custom OpenAI-compatible provider. Recorded in NOTES-layer10.md; the spec is changed first if they differ.
- [ ] 10.53 The `umwayi-local` route (2.5 h): the keys `base_url` and `reasoning_effort`; the provider entry; the refusal of every hosted provider. Tests: every allowed `base_url` shape (localhost, `127.0.0.1`, `[::1]`, `10.x`, `172.16.x` to `172.31.x`, `192.168.x`, `fc00::/7`, with and without a path); every refused one (a public address, a host name other than `localhost`, user and password, a query, a fragment, no port, `ftp://`); `base_url` on another provider; a hosted provider such as `openrouter`.
- [ ] 10.54 End to end (1.5 h): the 10.49 chat with `provider: umwayi-local` and the fake, including the inline config bytes.
- [ ] 10.55 Docs and the notice (1 h, plus 0.5 h of the owner's): the adapter README section; KNOWN-LIMITS 188 and 189; the "Built with Muse Spark Open" line in the README, added only after the owner has read `LICENSE.md` on Hugging Face and said so in the pull request.

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

## Documentation layout (D.1, the owner's first task before S.1; added Nov 10 to PR 34)

The README is 447 lines with every layer in one file. D.1 follows the documentation pattern of the owner's other projects (`routine-machine`, `Invoice-Financing`): a root `PROJECT.md` that says what to read first, a short README, and one file per component under `docs/`, each with the same four parts, kept current in the same turn as the behaviour it describes. Built as its own pull request right after PR 34 merges, before S.1. Docs only: no change to `umwayi/`, `adapters/` or any test except the new docs test. About 6 hours.

- [x] D.1 (PR 35) The short README and `docs/` (6 h):
  - **README.md, at most 120 lines:** what it is; a status table (one row per layer and addendum, its state and its pull requests, from the status table above); install and test; exit codes in five lines (the full table in `docs/exit-codes.md`); a table of the layers where each row links to its doc; security and known limits (links to `docs/security.md` and `docs/KNOWN-LIMITS.md`); contributing (branches, pull requests, tests first, `docs/DOCS_MAINTENANCE.md`).
  - **`PROJECT.md` in the root:** what umwayi-os is, what to read first (this file, then `docs/DOCS_MAINTENANCE.md`, then the doc of the part being worked on, then its section of the `.kiro` specs), and the project structure with one line per file.
  - **One file per layer under `docs/`:** `memory.md`, `rules.md`, `queue.md`, `archive.md`, `logbook.md` (with the crash safety and the hash chain), `automation.md`, `helpers.md`, `workflows.md`, `adapters.md`, `agent-front-door.md`, `scheduled-runs.md`, `budget-governor.md`; plus `exit-codes.md`, `architecture.md`, `testing.md`, `security.md`, `status-log.md` (the status table and the counts after each pull request) and `schedule.md` (the schedule to Dec 3).
  - **Each file has four parts:** Purpose (one paragraph); Current state (what is built now, moved from the README); Decisions log (a table of date, decision and reason, newest first, from the answers recorded in the `.kiro` specs, each row naming its question, for example L11-Q6); Open questions (from the specs and the owner's open checks). Each file under 300 lines; a longer one is split into linked sub-files (for example `agent-front-door.md` and `agent-front-door-acp.md`).
  - **`docs/DOCS_MAINTENANCE.md`:** a doc update ships in the same turn and pull request as the behaviour change; docs describe the current state, not the history (history goes to `status-log.md` and the Decisions logs); the four-part format; the 300-line rule; and which file to update when (a new command or exit code, a rules action type, a logbook entry shape, an adapter, a limit, a schedule change, a status change, a scan result).
  - **Lossless:** text is moved, not rewritten. No fact, number, command, exit code, link or limit is dropped. Only headings, the order and the relative link paths change. The README's example logbook entry (README line 128, "## 2026-11-07") stays inside its code block, which is marked `text` and introduced as an example entry, so no tool reads it as a heading.
  - **Kept where they are and linked:** `docs/KNOWN-LIMITS.md` (numbering unchanged), the `.kiro/specs/umwayi-os/` requirements, design and tasks, `adapters/NOTES*.md` and each adapter's README. `agents.example.yaml`, `schedule.example.yaml` and the rules examples stay where they are.
  - **`tests/test_docs.py`** (standard library only, no network): every relative link in `README.md`, `PROJECT.md` and every `docs/*.md` resolves to a file in the repo, and an `#anchor` to a heading in that file; `README.md` is at most 120 lines; no em dash in `README.md`, `PROJECT.md` or any file under `docs/`; every layer doc has the four parts in order and is under 300 lines; headings are found outside code blocks only.
  - Acceptance tests:
    - `tests/test_docs.py` passes; it fails on a planted broken link, a planted anchor that does not exist, a README of 121 lines, a planted em dash, a doc of 300 lines and a doc missing one of the four parts (each planted in a temporary copy, never in the repo);
    - the lossless check, run once and its result put in the pull request: every non-blank line of the old README outside code blocks, with link paths normalised, is found in exactly one new file, except the headings the move replaced (listed); every code block is found byte for byte; every KNOWN-LIMITS item number the old README named is still named;
    - the full suite on Python 3.10 to 3.13, with the counts in the pull request;
    - no file under `umwayi/`, `adapters/` or `tests/` changes except `tests/test_docs.py`.

## Whole-system test and security scan (spec PR 34, approved Nov 10 (S.0); built Nov 10 to Nov 12, moved up by the owner from Nov 23 to Nov 26)

Requirements S.R1 to S.R10, design.md "Whole-system test and security scan" (facts with links, the tools and what each cannot see, open questions S-Q1 to S-Q16). Approved with S-Q1 to S-Q16 as proposed (S.0). About 25 hours (design, "Hours and schedule effect"). Every test runs `python -m umwayi ...` as a real child process with `HOME`, `XDG_CONFIG_HOME` and `TMPDIR` in a temporary folder and the fake agents on `PATH`; no real agent, systemd, network or account. The scan tools run outside the repo and are never a dependency.

- [x] S.0 Requirements S.R1 to S.R10, the design section and these tasks written (Nov 10) in PR 34, approved by the owner on Nov 10 with S-Q1 to S-Q16 all as proposed:
  1. S-Q1: S.1 runs in the normal suite, so CI runs it on every pull request; the added time is measured in S.1.4.
  2. S-Q2: one ordered owner's day, then each fault scenario in its own copy of the day's end state.
  3. S-Q3: Bandit with all plugins from a throwaway virtual environment, plus the existing code guards; no Semgrep.
  4. S-Q4: OSV-Scanner offline (one database download) as the main tool, and `npm audit --package-lock-only` as a second source, accepting that it sends the package list to the registry.
  5. S-Q5: each Python version compared by hand with python.org's security releases, and recorded.
  6. S-Q6: a whole-request deadline of 10 s in the receiver; a request past it is closed, and the run is made invalid only if the run header had matched.
  7. S-Q7: the receiver handles at most 16 requests at once and closes the rest at once.
  8. S-Q8: High or Critical, Medium and reachable, and every defect a test shows must be fixed or accepted by the owner in KNOWN-LIMITS before the freeze (Nov 29).
  9. S-Q9: the canary folder 0700, the capture file 0600, the intent 0600 while it holds an entry, the unit files 0644, everything else the owner's umask.
  10. S-Q10: the same-user boundary is stated plainly and not tested against.
  11. S-Q11: every licence is listed and the SDK's "SEE LICENSE IN README.md" is pointed out for the owner to read; umwayi decides nothing.
  12. S-Q12: the results go to `docs/SECURITY-SCAN.md`, dated, with nothing secret.
  13. S-Q13: the CI workflow is not changed for Dec 3; the scan is run by hand and recorded. (Overruled on Nov 12 by the owner's request CI.1, which changes the triggers, adds cancelling and caches npm; it adds no scan.)
  14. S-Q14: the owner's real runs (10.21's real run of each platform, 10.31, 11.6, B.10) are not part of S.1 and are listed as not done.
  15. S-Q15: a defect S.1 finds in any layer is fixed in the S.1 pull request, test first, and named in it.
  16. S-Q16: built right after approval (now Nov 10 to Nov 12, moved up by the owner from Nov 23 to Nov 26), one pull request for S.1 and one for S.2.
- [x] S.1 (PR 36) Whole-system test (includes 9.11 and the test part of 10.21):
  - [x] S.1.1 (PR 36) Support (2 h): `tests/whole_system_support.py`: the root builder from the example files, the fakes on `PATH`, the copy of the day's end state per scenario, the end checks of S.R1.5 (verify, budget status, nothing alive, allowed exit codes).
    - Acceptance tests: a fresh root validates (`agent validate`, `budget validate`, `schedule validate`, `workflow validate` all 0); a copy is byte for byte the original, links kept; the end checks fail on a planted leftover process and on a planted exit code 1 from `agent`.
  - [x] S.1.2 (PR 36) The owner's day (3 h): the eight steps of S.R2 in order, each with its exit code, the logbook entries it adds (by source and shape) and the state files after it.
    - Acceptance tests: each step's entries and nothing else; the chain started in step 3 covers every later entry; the shares in `budget status` match the day (one measured, one declared or unknown); `verify --anchor` with step 3's anchor gives 0 (it is a prefix of the longer chain; corrected in PR 36, this line said 1 "shorter", which is the answer for a chain shorter than its anchor, tested in S.1.3) and with a new anchor 0.
  - [x] S.1.3 (PR 36) Faults: a tampered logbook, a lost reservation, crashes (2.5 h): S.R3.1, S.R3.2 and S.R3.6, each from a copy of the day.
    - Acceptance tests: the four tampering cases of the design's table with their exact answers, and nothing written by a refusal (snapshot equal); the lost reservation through `status`, a refused start (3), `settle-lost` refused while a run holds the lock (3) then 0, the next start 0; each planted crash recovered or refused, `verify` 0 at the end.
  - [x] S.1.4 (PR 36) Faults: the kill switch mid run, no systemd, a limit mid chat (2.5 h): S.R3.3 for each of the six kinds of start, S.R3.4 with and without a recording fake `systemctl`, S.R3.5.
    - Acceptance tests: each kind stopped with exit 3, nothing alive, one settle, the next start 0 after `kill off`; no call to `systemctl` recorded, the files 0644, `ExecStart=` by hand gives the job's entry; the chat stopped with 3 and settled measured. The suite time on 3.13 before and after S.1 is in the pull request (S-Q1).
- [x] S.2 (PR 37) Security scan (results: `docs/SECURITY-SCAN.md`; one open decision for the owner, Python 3.10, KNOWN-LIMITS 133):
  - [x] S.2.1 (PR 37) The receiver (2.5 h): `tests/test_scan_receiver.py`, every case of S.R5 through `agent run` with the fake sender's raw socket mode.
    - Acceptance tests: no connect on any non-loopback address or `::1`; only the exact header gives 200, in all seven cases; 1 MB is 200 and 1 MB plus 1 is 413 with the body not read; the 16 MB total; a short body, a long body, chunked (411), gzip (415); the slow client and the 200 connections as S-Q6 and S-Q7 decide; the port closed after a normal end, the kill switch, SIGTERM and a crash.
  - [x] S.2.2 (PR 37) Receiver fixes, only if S-Q6 and S-Q7 are answered as proposed (2 h): a whole-request deadline and a cap on handlers in `umwayi/telemetry.py`, each test first.
    - Acceptance tests: the S.2.1 cases for the slow client and many connections, which fail before the fix; the full budget suite unchanged; a planted fault for each (the deadline removed, the cap removed) killed.
  - [x] S.2.3 (PR 37) Modes, links and paths (3 h): `tests/test_scan_files.py`, the mode table under umask 022 and 077 (S-Q9), the link table, the path cases, the races of S.R7.3.
    - Acceptance tests: every row of the three tables with its expected answer; no write outside the root in any row; every row with no expectation yet is listed as a finding in SECURITY-SCAN.md.
  - [x] S.2.4 (PR 37) Secrets (2 h): `tests/test_scan_secrets.py`, the planted secrets of S.R8.1 through the owner's day and every fault scenario, and the sweep of S.R8.2.
    - Acceptance tests: no planted word, run header secret or canary token in any byte swept, except the listed allowed places; a planted leak (a test-only fault that prints the prompt) is found with its file and line.
  - [x] S.2.5 (PR 37) The static and dependency scans, run and recorded (2.5 h): Bandit on umwayi's Python; the code guards listed; OSV-Scanner offline and, if S-Q4 says so, `npm audit --package-lock-only` on `adapters/claude_acp/package-lock.json`; `npm ci --ignore-scripts` in a throwaway copy and `npm audit signatures`. Each tool's version, source and checksum, the exact command and its result go into SECURITY-SCAN.md; a tool that cannot run is "not run" with the reason.
  - [x] S.2.6 (PR 37) Interpreters and licences (1 h): each Python version against python.org's security releases (S-Q5); every licence of the npm tree listed, the SDK's pointed out (S-Q11).
  - [x] S.2.7 (PR 37) Results and docs (2 h): the scan results under `docs/`: `docs/SECURITY-SCAN.md` (S.R9.1 and S.R10, dated) and `docs/security.md` (what was scanned, with which tool, and where the results are; its Decisions log has the S-Q answers); a decision for every finding (S-Q8); KNOWN-LIMITS from 129; the README only links `docs/security.md` from its security row (D.1) and holds no scan detail; `docs/DOCS_MAINTENANCE.md` names both files; planted faults and mutation checks for the new tests; the full suite on Python 3.10 to 3.13 with the counts in the pull request.

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

## Layer 12: Web interface, the view (spec in PR 38; in scope before Dec 3; built only after the owner approves it)

Requirements 12.R1 to 12.R11, design.md "Layer 12" (what is kept from the owner's reference and what changes, the stations, the motion engine, the snapshot, the checks panel, the liberal society view for later, the open questions UI-Q1 to UI-Q11), facts in `adapters/NOTES-layer12.md`. Phases UI.1 to UI.5 map to requirements as written in each task. Effort re-estimated on Nov 11: about 92 hours still to do, then **cut to about 75 by the owner the same day** (design.md, "Hours and schedule effect"): the four proposed cuts accepted, UI.4 not cut, the drift of UI.3 not fixed, no further cut unless the owner agrees; plus 1 hour of the owner's. The normal suite stays standard library only and needs no network, npm, Node or browser. The core changes in one place only: `umwayi view snapshot` (UI.2). UI.0 was approved by the owner (PR 38 merged; UI-Q6 to UI-Q11 accepted as proposed on Nov 10).

- [x] UI.0 (5 h) Requirements 12.R1 to 12.R11, the design section, these tasks, `adapters/NOTES-layer12.md`, `docs/interface.md`, the steering change (the web interface is layer 12, not a non goal; every safety rule kept; rule 10 added) and the links from the README and PROJECT.md, written Nov 10 in PR 38. **Waits for the owner's approval (PR 38 merged).** The owner's answers, recorded Nov 10:
  1. UI-Q1: `ui/` folder outside the `umwayi` package; the core stays standard library only.
  2. UI-Q2: three.js 0.187.0 and esbuild 0.28.2, pinned with a lockfile; the owner runs `npm ci --ignore-scripts`; umwayi never runs npm; the built page is committed and makes no network request.
  3. UI-Q3: `umwayi view snapshot` is read only and writes one JSON file of counts only (queue open and answered, rules by verdict, logbook entries, chain length, budget used per day, kill switch state, schedule state), no text from any file, no paths, no secrets; it runs the tamper check, writes one logbook entry and exits 0, 1 or 64.
  4. UI-Q4: calm by default; nothing flashes or blinks; motion only after a click or cursor move and it eases to rest; no autoplay; `prefers-reduced-motion` switches off all movement and shows still frames; a visible calm mode toggle with lower contrast; dark, low brightness colours and no large pure white areas; cleaner and closer to recent games than an old video game; less congestion.
  5. UI-Q5: an owner checks panel lists the physical tests (10.21, 10.31, 11.6, B.10 capture, 10.37, the interface check) with steps and a place to tick and type results; results stay in the page and export as text; the interface never writes to the repo, runs a command or calls a network.
  6. UI-Q6 to UI-Q11 are open, each with a proposed answer (design.md). The build starts with the proposals unless the owner answers otherwise.
  - Acceptance tests: `python -m unittest tests.test_docs` passes; no em dash in any file the pull request touches; every safety rule of `.kiro/steering/product.md` is still there word for word, with rule 9 extended by one sentence and rule 10 added; the pull request changes no file under `umwayi/`, `adapters/*.py`, `tests/` or `ui/`.
- [x] UI.0b (3 h, PR 39, Nov 11) The owner reviewed the UI.1 scene (PR 39) and asked for a different look. New answers UI-Q12 to UI-Q16 recorded; requirements 12.R3 (natural features), 12.R5.7, 12.R6.1, new 12.R12 to 12.R15; design, tasks, `docs/interface.md`, `adapters/NOTES-layer12.md` and the steering file changed in their own commit. PR 39 stays open and is reworked on `ui/world`; it is not merged.
  1. UI-Q12: the look resembles real life, more detail not less, photoreal leaning, one page under about 2 MB, no network request, no downloaded images, realism from generated terrain, lighting and textures, and an automatic lower detail mode for weak machines.
  2. UI-Q13: the Kenyan highlands at dusk (hills with real height, a river valley, acacia and cedar, grass and rock, Mount Kenya, low warm light); a hanging lantern on a shepherd's staff with a silhouette shepherd and a dog, the brightest point; no podiums, no paths, no label boards; stations are natural features named only on hover or focus; the mapping of the eleven.
  3. UI-Q14: a scattered layout by how closely each works with the shepherd, default distances fixed with a seeded layout, no overlap, keyboard reachable; streams and trails of light between stations that work together, no drawn paths.
  4. UI-Q15: distance follows need (closer when the owner is needed, drifting out when quiet), slow, eased, ends within 3 seconds, off under reduced motion; the position function is built in UI.1 and UI.3 only feeds it numbers.
  5. UI-Q16: the scene is the hero of the home page: one page, two modes; title and promise, a status strip (sample until a snapshot), install and first commands with Copy buttons (clipboard only on a click), links (Devpost and demo video are marked placeholders).
  6. Owner's decision on the hours (Nov 11): all four proposed cuts accepted (the second realism pass, station detail, the last step of the low detail mode, UI.5 extras); UI.4 not cut; the drift of UI.3 not fixed to the default numbers; no further cut unless the owner agrees. About 75 hours remain against a window of 60 to 72; the gap is stated, and if it shows by Nov 17 the owner is asked.
  - **Dropped from the first UI.1:** the podium ring and its rim lights, the ring and label-declutter code and tests, the always visible name pills, the signpost, the sky arcs, the lamp posts row, the low poly look (flat dark meadow, round blob trees). **Kept:** the engine, Calm mode, reduced motion, the build, the Content-Security-Policy, `build.json`, the list view and fallback, the panel, the contrast test and their tests.
- [x] UI.1 (PR 39, reworked Nov 11; waits for the owner's look at the screenshots) The static world, as the highlands scene (42 h after the cuts, 56 before; 12.R1, 12.R2, 12.R3, 12.R5, 12.R6, 12.R8.3, 12.R12, 12.R13, 12.R14, 12.R15), with sample data and no snapshot. Its own pull request (PR 39, reworked). Stop at its end and show the owner the screenshots at 1440 by 900 and 390 by 844, in normal, Calm and reduced motion.
  - [x] UI.1.1 (PR 39) The package, the build and the page rules (2 h, kept from the first build): `ui/` exact versions, lockfile, `build.mjs`, `build.json`, Content-Security-Policy; `tests/test_ui_package.py` now also checks the page size (under 2 MB) and allows exactly the home addresses.
    - Acceptance tests: the package test passes on the repo and fails on each planted fault (a range version, a missing sha512, a changed source with no rebuild, a hand edited page, a `fetch(`, an address that is not allowed, a page over 2 MB, a missing CSP, a `<script src>`, a placeholder made into a link).
  - [x] UI.1.2 (PR 39) The engine and calm (kept; 1 h to extend): the ease out tween, following, the on demand loop, settings, the pose player; the camera rig for the new overview and station shots.
    - Acceptance tests (`node --test`): unchanged; they still pass.
  - [x] UI.1.3 (PR 39) The layout and the position function (6 h, **tests first**): `ui/src/world/layout.js` (the fixed table, the river centre line), `stationPositions(needs)`, `ui/src/engine/placement.js` (`setNeeds`, the eased move).
    - Acceptance tests (`node --test`, written first): the defaults equal the table of the design; the default gap between any two stations is at least 2.0 m; for 5000 seeded random need sets and for all quiet and all needing, no two stations overlap (footprints plus 0.8 m) and none is closer to the lantern than the shepherd's space plus its footprint; a higher need never puts a station further from the lantern when nothing pushes it; the same needs give the same positions; a missing, non number or out of range need is 0.4; river stations stay on the bank on their own side; every station stands on land of a slope its feature allows; a move ends in 2.4 s (3.84 s in Calm), a new set of needs mid move starts from where the stations are, and with reduced motion the stations jump; the keyboard order equals the list view order.
  - [x] UI.1.4 (PR 39) The ground, the river, the rock, the light and the air (12 h): `heightAt` with the valley, the river and the hills; the ground shader (gold and green grass, red soil, gravel, rock; derivative bump from noise); the river and the pools (a reflecting surface that does not flow); rock; the warm low light, the sky fill, fog tinted to the sky.
    - Acceptance tests: `heightAt` is finite, the valley floor near the lantern is within 0.3 m of 0 away from the knoll, the river bed is below the floor by about 1.6 m along the whole centre line, and the hills reach their heights (`node --test`); in the browser: the picture has relief and a visible river, mean luminance and white area limits hold.
  - [x] UI.1.5 (PR 39) The sky, the cloud and Mount Kenya (4 h; first pass only, the second realism pass is cut): the sky with a warm band, soft cloud made once from noise, faint stars, the mountain silhouette with snow.
    - Acceptance tests: in the browser the mountain is visible between the hills at the default view, and the sky never drifts (two screenshots 2 s apart identical).
  - [x] UI.1.6 (PR 39) Plants (5 h; two kinds of tree and grass, a third kind is cut): grass (instanced blades in gold and green), umbrella thorn acacia, African pencil cedar, placed by the ground and clear of the stations at every reachable position.
    - Acceptance tests: no plant inside any station footprint at the default positions or the extremes; counts per detail level; all instanced.
  - [x] UI.1.7 (PR 39) The lantern, the staff, the shepherd and the dog (3 h): a hanging lantern on a staff, a plain silhouette figure and a dog; the brightest point.
    - Acceptance tests: in the browser the brightest 0.01 percent of the picture contains the lantern.
  - [x] UI.1.8 (PR 39) The eleven stations as natural features (12 h after the cuts, 18 before): one module each, with poses and moves; no podium, no path, no sign. **Cut by the owner on Nov 11:** Adapters keeps the ford and one bridge (not three crossings, so three poses), Workflows has three pools (not four), the Automation wheel has no sluice.
    - Acceptance tests (`node --test`): each module builds, has at least two poses with the same numeric parameters and a move between each pair, ends within 2.9 s of action; Budget is built; the meta words are short, product words, no em dash; no module loads a file, keeps a timer or draws by itself.
  - [x] UI.1.9 (PR 39) Names on hover and focus, trails of light, interaction (3 h): the real buttons over the features that show their name on hover and focus, the warm lift, trails for the station in focus, arrow keys and Escape, the panel, the list view and the WebGL fallback.
    - Acceptance tests: 11 buttons and 11 list items with the same words; in the browser at rest no name is visible; focus shows the name; focus goes into the panel and back to the button; the list view shows by itself when `getContext` fails; trails hidden in Calm and drawn at once with reduced motion.
  - [x] UI.1.10 (PR 39) The detail mode (1 h after the cuts, 3 before; **tests first**): `chooseDetail(env)` and `stepDown()`, the low detail ladder of **two steps** (a lower pixel ratio, then no bloom and no multisampling); the owner cut the third step on Nov 11.
    - Acceptance tests: the choice for a set of environments (software rendering, 2 cores, 4 GB memory, a strong machine, `#detail=high`, `#detail=low`); the steps in order and the last one is the second; the page draws in both modes in the browser.
  - [x] UI.1.11 (PR 39) The home page (6 h, **tests first**): the hero text, the status strip, the install and first commands with Copy, the links with placeholders.
    - Acceptance tests (`node --test` and the Python page test): the status strip text for a sample and for a snapshot; the copy text equals the commands word for word; no clipboard call outside a click handler; Devpost and demo video are not anchors and say "link to come"; the only addresses in the page are the listed ones; the content reads without WebGL.
  - [x] UI.1.12 (PR 39) The browser pass, the screenshots and the docs (5 h): the by-hand checks of 12.R10.5 in high and low detail; screenshots at 1440 by 900 and 390 by 844, in normal, Calm and reduced motion; results with the date, the browser and its version in `docs/interface.md`; the page size.
    - Acceptance tests: no console error; zero attempted requests with all requests blocked; 11 buttons, names only on hover and focus, the panel opens for each; two screenshots 2 s apart at rest are identical; after a click the picture changes and is identical again within 3 s (5 s in Calm mode); the luminance and white area limits; 30 frames a second at 1440 by 900 on an integrated GPU, or the pixel ratio drops (not verifiable in the sandbox, which draws in software).
- [x] UI.0c (2 h, PR 39, Nov 11, round 2) The owner reviewed the reworked scene and answered UI-Q17 to UI-Q22. Requirements 12.R16 to 12.R20 added and 12.R1, 12.R2, 12.R5, 12.R6, 12.R10 to 12.R13, 12.R15 changed; design, these tasks, `docs/interface.md`, `adapters/NOTES-layer12.md` and the steering file changed in their own commit.
  1. UI-Q17: three tiers (List, Standard, High) chosen by a device query in the browser, with a visible switch.
  2. UI-Q18: a public site in `site/` (Next.js, pinned, Vercel free tier, no analytics, no tracking, hints never sent); the server renders the home text and the list; the 3D draws in the browser; it may fetch its own assets from its own host.
  3. UI-Q19: the owner's live view stays the static one file page of `ui/` (no request, CSP `default-src 'none'`, from disk, tier 2, file picker); one scene module used by both; umwayi never runs npm or node.
  4. UI-Q20: tier 2 fixes: the rest of the page shows at the bottom of the first screen; the list is tier 1; outer stations further out; river and trails visible from the default view; no name over the hero text on a phone; rocks, walls and ground less low poly.
  5. UI-Q21: a dense forest across the river; rapids, foam and moving highlights (still under reduced motion); a Maasai silhouette shepherd; a mixed flock of sheep and goats and a herding dog that look real; wildlife at the edge in High only.
  6. UI-Q22: the owner keeps the timeline; no scope cut; no question about hours; one pull request per step: UI.1b (PR 39), UI.6, UI.7.
- [ ] UI.1b (PR 39, about 30 h) The Standard tier fixes, the home page layout, the scene additions at Standard detail and the tier choice (12.R16.6, 12.R16.7 for List and Standard, 12.R19, 12.R20.1 to 12.R20.4). Stop at its end and show the owner screenshots at 1440 by 900 and 390 by 844.
  - [ ] UI.1b.1 The tier choice (**tests first**): `ui/src/engine/tier.js` (`chooseTier`) and `ui/src/engine/env.js` (`readEnv`); the switch in the top bar (List, Standard) replaces List view; `#tier=` kept in the address only; the page without JavaScript shows the list and the home content.
    - Acceptance tests (`node --test`, written first): every case of 12.R10.4 for the tier choice; (Python page test) the switch buttons exist, no List view button, the list is visible in the HTML before any script runs.
  - [ ] UI.1b.2 The layout further out (**tests first**): new default places with at least three stations at 30 m or more; the overview shows all eleven on a wide screen and the near ones on a phone.
    - Acceptance tests: the layout tests of UI.1.3 still pass on the new table, and at least three default distances are 30 m or more.
  - [ ] UI.1b.3 The home page layout and the names: the peek of the status strip and the still cue; no name pill over the hero text.
    - Acceptance tests (browser): at both sizes the top of the status strip is inside the first screen and not covered; for every station, hover, focus and selection give a name that does not cross the title or promise boxes.
  - [ ] UI.1b.4 Trails and river: every trail faint and still at rest, brighter in focus, fainter in Calm mode; the overview shows a long reach of the river.
  - [ ] UI.1b.5 Rocks, walls and ground: displaced rocks with strata, walls of separate stones in courses, small stones and tufts at the stations.
  - [ ] UI.1b.6 The forest across the river, cut by the river; clear of every station footprint.
    - Acceptance tests (`node --test`): no tree inside a station footprint at the defaults or the extremes; every forest tree is across the river from the lantern.
  - [ ] UI.1b.7 Flowing water: rapids over rocks in the bed, foam, moving highlights; still with reduced motion, in Calm mode, off screen and hidden; at most 30 frames a second.
    - Acceptance tests: (`node --test`) the flow clock stops for each of those four states and runs otherwise; (browser) with reduced motion and in Calm mode two screenshots 2 s apart are identical and no animation frame is asked for at rest.
  - [ ] UI.1b.8 The Maasai shepherd, the mixed flock of sheep and goats and the herding dog.
  - [ ] UI.1b.9 The browser pass, screenshots and docs: the checks of 12.R10.5 as changed by round 2; screenshots at 1440 by 900 and 390 by 844, normal, Calm and reduced motion; `docs/interface.md`.
- [x] UI.6 The shared scene module and the public site, List and Standard (about 24 h, 12.R16, 12.R17, 12.R18). Its own pull request, after UI.1b. Built on the branch `ui6-shared-scene-and-site`; it waits for the owner's review. Done in three commits (the shared scene module, the site, the CI step) plus the docs: `ui/src/scene.js` (`createScene`), `ui/src/boot.js` (the device query and the switch, used by `main.js` and by the site), `site/` (Next.js 16.4.6, React 19.3.1, three 0.187.0, all exact), `tests/test_site_package.py` (41 tests), `site/test` (25 Node tests), `ui/test/shared.test.mjs` (8 tests), the CI step for `node --test`. KNOWN-LIMITS 140 and 141. Open in the pull request: the script policy (UI-Q23 proposal, `'unsafe-inline'` for scripts), the site's client calling `boot.js` and `app.js` rather than `createScene` itself, the extra controls on the object `createScene` returns, no build record for `site/`, and the CI step on one Python version only.
  - Work: `ui/src/scene.js` (`createScene`) used by `ui/src/app.js`; `site/` with Next.js pinned, server rendered home text and list, the client scene for Standard, the device query, the switch, the headers; the Python tests for `site/` (exact versions, sha512 lockfile, no analytics package, no remote font or script, no copy of `ui/src`).
  - Acceptance tests: the live view page and its tests are unchanged in behaviour; the site's home text and list are in the HTML the server sends; with JavaScript off the site shows List; the device hints never appear in any request (browser pass with every request logged); the site makes requests to its own origin only.
- [x] UI.7 Tier 3, High (about 30 h, 12.R16.3, 12.R16.4, 12.R20.5). Its own pull request, after UI.6. Built on the branch `ui7-high-tier`; it waits for the owner's review.
  - Done:
    - `ui/src/high/` (assets, ground, plants, figures, wildlife, build, index) and the High path of `ui/src/boot.js` (Standard first; the fallback with words; the 15 s limit);
    - the switch with High in `site/app/home.js`, and High loaded on demand by `site/app/scene.js`;
    - five CC0 photographs from Poly Haven in `site/public/high/`, listed in `site/high-assets.json` and in NOTES-layer12.md;
    - tests first: `ui/test/wildlife.test.mjs`, `high.test.mjs` and `boot.test.mjs`, and `tests/test_site_assets.py` with planted faults; more Node tests after the mutation pass;
    - KNOWN-LIMITS 151 to 156 (156 records that the step down from High is not built).
  - Two existing tests were edited: `ui/test/stations.test.mjs` lets `src/high/assets.js` load images, and `ui/test/faults.test.mjs` (UI.5) allows the one timer of `ui/src/boot.js`, the 15 s limit on High (HIGH_TIMEOUT_MS).
  - The owner's answers on PR 58 (Nov 12): Standard's extra 4.4 KB and one request are accepted; the photographs stay Poly Haven's original files; the antelope is drawn larger so that it shows in the default view (3 times life size, KNOWN-LIMITS 153); stepping down from High to Standard after slow frames is a follow-up task (UI.8), not part of PR 58.
  - `ui/dist/index.html` was rebuilt because `boot.js` changed. The live view behaves the same (the same log and screenshot as main).
  - Work: the High scene (more trees, finer ground, detailed rocks and water, better animals), the asset files with sources and licences, distant birds and an antelope on the ridge, the fallback to Standard.
  - Acceptance tests: Standard draws first; a failed asset gives Standard; every asset file is listed with a free licence; requests go to the site's own origin only; wildlife is never within 25 m of a station.
- [ ] UI.8 High steps down to Standard by itself after slow frames (follow-up of UI.7, asked for by the owner on PR 58; **not built**, its own pull request). Today the detail ladder (`ui/src/engine/stage.js`) lowers the pixel ratio, the bloom and the amount of grass inside High, but nothing takes High off. KNOWN-LIMITS 156.
  - Work: after the ladder is at its lowest step and frames are still slow, `boot.js` removes High (`dropHigh`) and shows Standard with words saying why, and keeps that for the visit (it must not flip back). The thresholds (slow, for how long) are the same numbers as the ladder's, not new ones.
  - Acceptance tests: a fake page where frame times stay slow gives Standard with the words, once; fast frames never remove High; a visitor who chose High with the switch is told, not overruled silently; the live view is untouched (no `loadHigh`); the browser pass drives this with a throttled GPU or a long frame.
- [x] UI.2 `umwayi view snapshot` (9 h, 12.R4, 12.R9.4, 12.R10.1). Its own pull request (PR 41, Nov 11); Python only, independent of UI.1. Tests first.
  - [x] UI.2.1 Tests first (3 h): `tests/test_view.py`, every case of 12.R10.1, failing before the code.
  - [x] UI.2.2 `umwayi/view.py` and the `view` subcommand (4 h): the order of the design (arguments 64, tamper check 1, gather through each layer's reader, render, write through the shared atomic writer, one logbook entry, undo on failure); `.umwayi/snapshot.json` in `.gitignore`; `ui/test/fixtures/snapshot.json` made from the fixed root of the tests. **Not done in PR 41:** the fixture, because `ui/` belongs to the UI.1 branch (PR 39). UI.3 adds it from the fixed root of `tests/test_view.py` (`ContentTests.test_a_fixed_root_gives_exact_bytes_twice_the_same`), and the check that it equals the command's output byte for byte is part of UI.3.
  - [x] UI.2.3 Docs, planted faults and mutation checks (2 h): `docs/exit-codes.md` (the new command: 0, 1, 2, 64), `docs/testing.md`, `docs/interface.md`, the code guard for `view.py`; planted faults (a title written, a path written, a wrong count, the tamper check skipped, the entry skipped, `--out` allowed over `rules.yaml`) each killed by a named test; counts in the pull request; the full suite on Python 3.10 to 3.13. Done in PR 41: 23 planted faults, 20 killed, 3 equivalent (a second check refuses the same input); 1200 tests on Python 3.10, 3.11, 3.12 and 3.13.
  - Acceptance tests: all of 12.R10.1; the fixture equals the command's output on the fixed root byte for byte; the exit codes are only 0, 1, 2 and 64; no file outside the snapshot and the logbook with its record changes.
- [x] UI.3 The page reads the snapshot and feeds the position function (8 h, 12.R3.6, 12.R3.7, 12.R4.9, 12.R4.10, 12.R9). Its own pull request, after UI.1 and UI.2. Built on the branch `ui3-read-snapshot`; it waits for the owner's review. Both the live view and the public site use it (the owner's task: a visitor can open their own file in the browser; 12.R17.6 and rule 10 changed to say so). Needs: 0.4 quiet, Queue `0.4 + 0.6 * min(1, open / 6)`, Kill switch 1 unless off, Budget against the other six days (open question: quiet stays at the default, not past it). Tests: `ui/test/snapshot.test.mjs`, `snapshotview.test.mjs`, `drawn.test.mjs`, `wiring.test.mjs` (85, 180 in `ui/` in all), 9 planted-fault page tests in `tests/test_ui_package.py`, `FixtureTests` in `tests/test_view.py`; mutation pass 76 of 76 killed; browser pass with every request logged (0 requests). KNOWN-LIMITS 142 to 145. Edits outside the data side, kept minimal: `ui/src/scene.js` (`setCounts`, counts kept in `let`), `ui/src/app.js`, `ui/src/boot.js`, the six station modules, `ui/src/index.html`, `site/app/home.js` (picker markup and footer id) and `site/test/home.test.mjs`.
  - Work (8 h now): `ui/src/data/snapshot.js` (the file picker and drop, `FileReader`, the strict validator, the mapping from counts to scene numbers), **the mapping from the snapshot to needs, fed to `setNeeds` of UI.1.3 (nothing else changes in the position code)**, the status strip of the home page with real values and the date, the snapshot date next to the scene, the "sample" label until a snapshot is loaded, unknown drawn as unknown.
  - Acceptance tests (`node --test`): the needs from a snapshot (a queue of 6 or more gives need 1; the kill switch on or unknown gives 1; a quiet snapshot gives the defaults; a bad number gives 0.4) and the positions that follow; the fixture of UI.2 is accepted; each bad shape is refused with the one message and nothing is loaded (an extra key, a missing key, a string where a number belongs, a float, a negative, 1000000001, a file of 4097 bytes, not JSON, `schema: 2`, a nested extra object); `null` parts are drawn as unknown; `kill_switch` of `unknown` draws the hurdle up; a mapping table (counts to sheep, stones, beads, lanterns, marks, water level); "sample" is shown if and only if no snapshot is loaded; no text from the file is ever set as markup. In the browser: the real file made by `umwayi view snapshot` loads and the numbers in the panel equal the file.
- [x] UI.4 The owner checks panel (6 h, 12.R7, 12.R10.1 to 12.R10.4). Its own pull request. Built on the branch `ui4-owner-checks`; it waits for the owner's review. `ui/src/data/checks.js` (6 checks, 67 steps word for word from the NOTES files), `notes.js`, `ui/src/ui/checks.js`; five B.10 capture steps added to NOTES-layer10.md (there were none); Download is a data address, not a Blob; tests: `ui/test/notes.test.mjs`, `checksview.test.mjs`, `tests/test_checks.py` (12 planted faults), 9 planted-fault page tests; mutation pass 62 of 62 killed; browser pass with every request logged (0 requests, 5 runs); KNOWN-LIMITS 146 to 148.
  - Work: `ui/src/data/checks.js` with the six checks (10.21, 10.31, 11.6, B.10, 10.37, the interface check) and their steps from the NOTES files, the panel, the in-memory state, the export, the value warning.
  - Acceptance tests: (Python) every command in `checks.js` is found word for word in the NOTES file of its check, and every check id exists in tasks.md; (`node --test`) a check is "not done" until all its steps are ticked and then "ticked by you", never "passed"; the export of a fixed state equals a fixed text, ending in "These are your notes. umwayi did not run or verify anything."; an email, a URL, a 24 character token and a long hex string in a result are warned and a plain exit code is not; the source has no `localStorage`, `sessionStorage`, cookie or IndexedDB (the static test greps the built page); the panel works with WebGL off. In the browser: Copy and Download work under the page's Content-Security-Policy, or the panel says Copy only; zero attempted requests while ticking, typing and exporting.
- [ ] UI.5 Polish, docs, the scan of `ui/` and the owner's interface check (7 h after the cuts, 10 before; 1 of them the owner's, 12.R5, 12.R6, 12.R10.5, 12.R10.6). Its own pull request.
  - [x] **Done in the first slice (Nov 11, branch `ui5-polish-docs`):** the phone layout of the panels at 390 by 844 (the owner checks panel was 1005 pixels wide and now fits; the station panel is a bottom sheet of the first screen; not the scene), a keyboard and screen reader pass as far as the code and the Node tests show (`ui/test/access.test.mjs`: landmarks, names, heading order, Tab order, the text alternative, live regions, 24 pixel targets, focus; no screen reader was run), and a contrast check worked out from the CSS (`ui/test/contrast.test.mjs`, 6 new tests, lowest text 6.0 to 1 in Calm mode against the floor of 4.5; the 3 to 1 of the field border and the focus ring). **Cut by the owner on Nov 11:** the contrast check of the glass panel over every part of the sky, and the second device pass.
  - [ ] **Still open:** the frame rate check with the pixel ratio drop, and the scene polish of the finished scene (they wait until UI.7 is merged, since UI.7 changes `ui/src/world` and `ui/src/scene.js`).
  - [ ] The by-hand browser pass of UI.1.5 repeated on the finished page, with the numbers recorded. **Open: waits for UI.7** (the first slice recorded the panels' pass only).
  - [ ] **Open: the owner holds all security scans for later.** The scan of `ui/package-lock.json`: OSV-Scanner offline and `npm audit --package-lock-only`, `npm ci --ignore-scripts` in a throwaway copy and `npm audit signatures`, every licence listed; the result goes into `docs/SECURITY-SCAN.md` as a new dated section and `docs/security.md`, with a decision for every finding (S-Q8).
  - [x] (first slice) Docs: `docs/interface.md` current, `docs/architecture.md`, `docs/exit-codes.md`, `docs/testing.md`, `docs/security.md`, `docs/status-log.md`, the README and PROJECT.md rows, `docs/KNOWN-LIMITS.md` from item 138 (the list in the design; 149 and 150 added, UI.7 may add more), `adapters/NOTES-layer12.md` with the dated facts. Done for this slice; to be brought up to date again when UI.7 and the rest of UI.5 land.
  - [x] (first slice) Planted faults and mutation checks of 12.R10.6, each killed by a named test (`ui/test/faults.test.mjs` checks the map): this slice 28 mutants, 28 killed; the UI.4 pass 62 of 62; UI.2 in PR 41. **Still open:** the full suite on Python 3.10 to 3.13 (CI runs it on the pull request) and the browser pass of the finished page.
  - [ ] **The owner's interface check** (1 h, the owner's; **not done**: the steps, the expected result and a results table are in `adapters/NOTES-layer12.md`, "The owner's interface check (UI.5)", brought up to date on Nov 11 for the page after UI.4: 25 steps, also in the checks panel as `UI.5`): open the built page from disk, watch the network tab show no request, walk the page with the keyboard, switch on reduced motion in the system, use Calm mode, load a real snapshot, and export the checks panel as text.
  - Acceptance tests: all of 12.R10; `tests.test_docs` passes; the page and `build.json` match the sources; the pull request lists what was not done.

## CI.1: faster, less wasteful CI (the owner's request, Nov 12; its own pull request, after PR 56)

The owner's reviewer found that each push to a pull request branch started two runs (eight jobs), that nothing cancelled an older run, and that each job runs the whole suite (about 1900 tests) in 20 to 25 minutes. This overrules S-Q13 above ("the CI workflow is not changed for Dec 3"): the owner asked for it. Strictly reviewed, because CI is the record the owner trusts.

- [x] CI.1.A (PR 59) The workflow runs on `pull_request` only, and a concurrency group (the workflow name and the pull request number) cancels the older run of the same pull request when a newer push arrives. The workflow name `tests`, the job name `test`, the matrix `3.10`, `3.11`, `3.12` and `3.13`, and every test on every version are unchanged, so the check names are unchanged. Proof is in the pull request: the workflow parses and passes `actionlint` v1.7.12, and a draft pull request (`ci1-proof`, closed without merging, its branch deleted) shows a deliberately failing test turning CI red, an older run being cancelled by a newer push, and the job names.
- [x] CI.1.B (PR 59) The npm download cache (`~/.npm`, keyed on the two lockfiles) on the 3.12 job, with `npm ci --ignore-scripts` unchanged. The whole Node step took 0.4 minutes of a 24.9 minute job, so the gain is small; it is cached because the owner asked, and the number is in the pull request.
- [x] CI.1.C (PR 59) Measured, not changed: the time of each test module on Python 3.12 (70 modules, 1898 tests, 1295 s in the sandbox, which is not the CI runner). The 15 slowest modules are in the pull request.
- [x] CI.1.D (W20, the owner asked) Built: three shards per Python version with a final job that fails if any shard fails, did not run, or if the shards together do not run every test. The job names changed; the list is in [docs/testing.md](../../../docs/testing.md#ci-since-w20).


## W20: faster CI without losing coverage (the owner's request, Nov 12; its own pull request)

- [x] W20.A The map: for every Python and Node test file, the paths it reads outside its own area (`tools/ci_map.json`), a scanner and a checker test (`tests/test_ci_map.py`) that fails when a test reads a path the map does not list, and the table in `docs/testing.md`.
- [x] W20.B Path filters: the decider `tools/ci_plan.py` and its tests (`tests/test_ci_plan.py`); an unknown path, an unreadable or empty diff, and a changed workflow, filter, map or shard file run everything; a push to main runs everything on Python 3.10 to 3.13; one always-on `result` job is the single check to require.
- [x] W20.C Sharding: `tools/ci_shards.py`, `tools/ci_shards.json` (three shards, balanced by measured seconds) and `tests/test_ci_shards.py`, with planted faults for a dropped test and a test file in no shard.
- [x] W20.D `tools/affected_tests.py`: the same decider on a laptop or in a session (`tests/test_affected_tests.py`).
- [x] W20.E `.kiro/steering/builder-workflow.md`: the builder rules, short, read by every session (`tests/test_builder_workflow.py`).
- [ ] W20.F The owner changes the branch rule by hand to require `tests / result (pull_request)` (the four `tests / test (3.1x) (pull_request)` names no longer exist). Waits for the owner.

## W19 part 2: the concerns record checker (the owner's task, Nov 13; its own pull request)

- [x] W19.2.A Tests first: `tests/test_concerns.py`, one for each failure case (a missing, duplicate or out of range number, a bad answer, an empty reason, an Applies row with a missing evidence path, a malformed date), a valid record, exit 0 on valid and 2 on invalid, the 111 names numbered 1 to 111 with no gap, and evidence that cannot leave the repo (no `..`, no absolute path, no link out).
- [x] W19.2.B `umwayi/concerns.py`: a strict parser and checker for the table `number, concept, answer, reason, evidence, date`, and the fixed list of the 111 concept names. Standard library only. It checks the form and never claims the content is true.
- [x] W19.2.C `umwayi concerns check PATH`: one line per failure, exit 0, 2 or 64, never 1 or 3. Run by the owner; no job, timer or workflow starts it (a test checks).
- [x] W19.2.D Docs: `docs/concerns.md`, a status part and a limits part in `docs-parts/` built with `umwayi goal docs build`, `docs/exit-codes.md`, `docs/architecture.md`, `docs/testing.md`, PROJECT.md.

## W19 part 3b: the model routing table, the task log and their checker (the owner's task, Nov 13; its own pull request)

- [x] W19.3b.A Tests first: `tests/test_routing.py`, one for each failure case of the routing table and of the task log, exit 0, 2 and 64 and never 1 or 3, no text of the file in a failure line, and the two shipped files pass.
- [x] W19.3b.B `umwayi/routing.py` and `umwayi routing check PATH`: a strict checker for the routing table (platform, model, strengths, task types, source, source date, review_by) and the task log (task, area, model chosen, outcome, review result, credits used, date). Standard library only. It checks the form and never picks a model.
- [x] W19.3b.C `docs/model-routing.md`: 33 options from Kiro and OpenCode with the strengths their vendor pages state, a source address and date for each row, and a `review_by` date. It only proposes; the owner always chooses the model.
- [x] W19.3b.D `docs/task-log.md`: the record format and the starter rows for PRs 66 to 79 from GitHub and the status log. Model and credits are `unknown` because history does not hold them.
- [x] W19.3b.E Docs: a status part and a limits part in `docs-parts/` built with `umwayi goal docs build`, `docs/exit-codes.md`, `docs/architecture.md`, `docs/testing.md`, PROJECT.md. No guidance loader, agents file, steering rule or safety rule changed.

## Non goals for Dec 3

Finance and marketing loops, shared rule packs (after Dec 3). The web interface was a non goal until Nov 10; it is layer 12 now. File watching, an SQLite index, tmux sessions and a sandbox (layer 11 proposes to cut or defer them, 11.R8).

## Layer 13: Correction and graded autonomy (spec in the L13.0 pull request; in scope before Dec 3; built slice by slice only after the owner approves it)

Requirements 13.R1 to 13.R15, design.md "Layer 13" (the owner's decisions, the verdict order, the data shapes, the score with a worked example, the fail closed table, the failure modes, the docs page plan, the open questions L13-Q1 to L13-Q18). Five slices in the owner's order, **each shipping alone** and merged whole or not at all; the owner stops the build where Dec 3 finds us. The last day a slice can be merged is **Nov 28**; nothing is merged in the freeze except a fix for a defect that a test finds. Effort about 93 hours of build and 8 of spec. The normal suite stays standard library only and needs no network. Tests first, as real child processes, with a planted fault for each of the five the owner named (a rule past `review_by`, a petition spam, a forged score input, a reopen of a missing entry, a broken chain). Nothing is built before the owner approves L13.0. Every slice's pull request lists what it did not do, the mutation checks with their counts, and the full suite on Python 3.10 to 3.13.

- [x] L13.0 (8 h) Requirements 13.R1 to 13.R15, the design section, these tasks, `docs/corrections.md` and `docs/autonomy.md` (written as "specified, not built"), the steering change (a Layer 13 section: in scope, three safety rules, what stays a non goal), and the links from the README, PROJECT.md, architecture and the schedule and status docs, written Nov 11. Docs and specs only, added at the end of the three spec files to ease merging with the layer 12 branches. **Waits for the owner's approval.** The owner's decisions of Nov 11 are in design.md ("Owner decisions"); L13-Q1 to L13-Q18 are open, each with a proposed answer, and the build starts with the proposals unless the owner answers otherwise.
  - Acceptance tests: `python -m unittest tests.test_docs` passes; no em dash in any file the pull request touches; every safety rule of `.kiro/steering/product.md` is still there word for word; the pull request changes no file under `umwayi/`, `adapters/*.py`, `tests/`, `ui/` or `site/`.
- [x] L13.1 Elections (14 h, 13.R2, 13.R3). Its own pull request; needs nothing else of layer 13.
  - [x] L13.1.1 Tests first (4 h): `tests/test_elections.py`, every case of the design's slice 1 test list, failing before the code.
  - [x] L13.1.2 `rules.py` (4 h): the `review_by` field, its errors, the lapse of a Yes rule in `decide`, `today` passed to `check`, the election clock (latest of the system date, `--date` and the newest logbook date), `Decision.lapsed`, the entry text and the JSON key `election_fallbacks` only when not empty.
  - [x] L13.1.3 `umwayi rules due` (3 h): `umwayi/elections.py`, the subcommand, the output and the exit codes 0, 3 and 64; it writes nothing.
  - [x] L13.1.4 Docs, planted faults and mutation checks (3 h): `docs/rules.md`, `docs/corrections.md` (Elections current), `docs/exit-codes.md`, `docs/testing.md`, the example rules of the three adapters (a note on `review_by`), the status docs; the mutations of the design's list for this slice.
  - Acceptance tests (real child processes): **a rule past `review_by`** (a Yes rule with `review_by: 2026-11-01` and `check --date 2026-11-12` gives Ask me first, exit 3, the entry names the rule and the date; with `review_by: 2026-11-12` it gives Yes; with a later `--date` in the past or a logbook entry dated later it still gives Ask me first); a No rule, an Ask rule and each bad date with `review_by` make the rules malformed (Ask me first, `rules_ok` false); a lapsed Yes next to a fresh Yes gives Ask me first, next to a No gives No; the fallback applies to a job and a helper (bare `rules.check`); `rules due` prints the exact lines, exits 0 and 3, writes nothing (the root before and after), prints no rule text; a rules file with no `review_by` gives the old entry and JSON byte for byte; no module imports a network library.
- [x] L13.2 Reversal (20 h, 13.R4, 13.R5). Its own pull request; needs the hash chain (already built), nothing else of layer 13.
  - [x] L13.2.1 Tests first (6 h): `tests/test_reopen.py`, the cases of the design's slice 2 test list, failing before the code; the existing decision answer tests are updated for `--revisit-if` and listed in the pull request.
  - [x] L13.2.2 `logbook.read_chained` and the queue changes (5 h): the reader with the same checks as `read_checked`, `queue answer --revisit-if` (required for a decision, refused for a task, `none` allowed), and a way to add a row and an entry in one commit.
  - [x] L13.2.3 `umwayi decision reopen` (6 h): `umwayi/decisions.py`, the resolve step, the order of the design, the new row and the entry, the already-reopened check, the exit codes 0, 1, 2 and 64.
  - [x] L13.2.4 Docs, planted faults and mutation checks (3 h): `docs/queue.md`, `docs/logbook.md`, `docs/corrections.md` (Reversal current), `docs/exit-codes.md`, the adapter guard names for `umwayi decision`; the mutations of the design's list (the old entry marked, the old row opened, the hash not logged in full).
  - Acceptance tests (real child processes): **a reopen of a missing entry** (an unknown hash, a 63 and a 65 character hash, uppercase, a hash of a `check` entry, a hash of an older closing entry, a missing Q id, a task, an open decision, an unchained entry: exit 1 or 64 as the design says, nothing changed, no entry); **a broken chain** (an old entry edited, an entry deleted, the hash record changed, a torn tail, a chain not started: exit 1 and nothing written); the happy path (the logbook before is a byte for byte prefix of the logbook after and the rest is one entry that starts with `Reopen of entry` and names the full hash; the old row is byte for byte the same; `logbook verify` is ok; an anchor taken before still verifies); a second reopen while the first row is open is refused, and succeeds after it is closed with the new hash; a decision answered without `--revisit-if` exits 64 and the row stays open; a task with it exits 64; an answer from before the slice reopens with `not recorded before layer 13`; an injected crash between the queue write and the entry puts `queue.md` back; two reopens at once leave one row; a reason with `|`, a newline or 301 characters exits 64.
- [x] L13.3 Courts and the rules change log (16 h, 13.R6, 13.R7). Its own pull request; needs nothing else of layer 13.
  - [x] L13.3.1 Tests first (5 h): `tests/test_petition.py` and `tests/test_rulelog.py`, failing before the code.
  - [x] L13.3.2 The rules change log (4 h): `umwayi/rulelog.py`, the hash and the state summary, the entry written before the rules are used, the fallback when it cannot be written (every Yes becomes Ask me first), the 200 rule cap.
  - [x] L13.3.3 `umwayi petition` (5 h): `umwayi/petition.py`, the five limits counted from `queue.md` and the logbook, the fixed title, the queue commit, the exit codes 0, 1, 2 and 64.
  - [x] L13.3.4 Docs, planted faults and mutation checks (2 h): `docs/rules.md`, `docs/queue.md`, `docs/logbook.md`, `docs/corrections.md` (Courts current), `docs/exit-codes.md`, the example rules of the adapters (petition left to the owner); the mutations of the design's list (the petition edits the rule, a limit off by one, the entry written after use).
  - Acceptance tests (real child processes): **a petition spam** (200 petitions from one helper and 60 helper names: the open and accepted counts stop exactly at the limits, the refusals exit 1 and write nothing, the rows and entries equal the accepted count, `rules.yaml` and the answers of a fixed list of actions are byte for byte unchanged, the run ends within a generous time bound); a petition against a Yes, an Ask, a missing rule or broken rules exits 1; a reason that reads like an instruction is only in `queue.md`, the title is the fixed template, and the logbook never holds it; the owner's answer to a petition changes no rule; a weakening of `no-money` to `yes` is logged before the check that uses it (the entry order in `LOGBOOK.md`), names the id and `no to yes`, holds no rule text, and is not repeated by the next check; a comment only edit logs `no rule changed`; with the logbook lock held or the chain broken, a Yes from the new rules gives Ask me first and a No stays No.
- [x] L13.4 Honest tension (5 h, 13.R8). Its own pull request; docs and one test module.
  - [x] L13.4.1 The note and the stop criteria (2 h): the section "No state is perfect" and the stop criteria table made current in `docs/corrections.md` and `docs/autonomy.md`; KNOWN-LIMITS items 160 to 165 (and 166 to 170 are written by L13.5).
  - [x] L13.4.2 The words test (3 h): `tests/test_honest.py`, the banned list against both pages, the `--help` of every layer 13 command built so far and the output captured by the acceptance tests.
  - Acceptance tests: the exact note is in both pages; the banned list finds a planted `guaranteed` in a copy of each page and in a planted command output; the stop criteria table matches 13.R8.3 and 13.R8.4 (a test lists the rows); every KNOWN-LIMITS item of the slices built exists; `tests.test_docs` passes.
- [x] L13.5 Graded autonomy (32 h, 13.R9 to 13.R12). Its own pull request, merged whole: the behaviour ships with the score, never the display alone. It may be reviewed in two commits (the inputs and `status`, then the move) but merges as one.
  - [x] L13.5.1 Tests first (8 h): `tests/autonomy/`, the worked example, the fail closed table, the forged inputs, the text blind test, the off by default test, failing before the code.
  - [x] L13.5.2 `autonomy.yaml` (4 h): the parser (every key required, ranges), `validate`, the change entry before use, `autonomy.example.yaml`.
  - [x] L13.5.3 The opt-in in `rules.py` (3 h): the `autonomy` field with `class`, `reversible`, `cost_uu`, the type matcher requirement, the never list, the agreement of two rules for one class, `review_by` on an opt-in rule.
  - [x] L13.5.4 The record (5 h): `umwayi autonomy record`, the fixed shapes, `read_inputs` with its whole-record `INVALID`, the duplicate `--ref`.
  - [x] L13.5.5 The score and the move (6 h): the formula in the fixed order, the thirteen gates, the check entry and the JSON key `autonomy` (only when on), the callers that log versus those that do not.
  - [x] L13.5.6 `umwayi autonomy status` (2 h).
  - [x] L13.5.7 Docs, adapters, planted faults and mutation checks (4 h): `docs/autonomy.md` current, `docs/rules.md`, `docs/logbook.md`, `docs/exit-codes.md`, `docs/security.md`, the guard names in the three adapters' example rules, KNOWN-LIMITS 166 to 170, one mutation per gate and the others of the design's list.
  - Acceptance tests (real child processes): the worked example, cases 1 to 6, to the per mille, the same on Python 3.10 to 3.13; 200 fixed count tuples against precomputed scores; **every row of the fail closed table**, one test each, answer Ask me first (or No) and the gate word in the entry; off by default (100 clean approvals with no `autonomy.yaml`, and with `enabled: false`: Ask me first, and the entry and the JSON byte for byte as without layer 13); **a forged score input** (a hand appended entry: the tamper check refuses; a well formed chained entry with a wrong Checked line; an entry with a count field; an unchained input written before the chain; an unknown outcome word; a duplicate `ref`: each makes every class Ask me first); **a broken chain** (an old entry edited: Ask me first for every class and `status` prints no score); the text blind test (sentinel and instruction text in queue titles, answers, recommendations, petition reasons, rule titles and other logbook sources leaves the answer and `status` unchanged); the moves do not feed the score; each type on the never list with `autonomy` makes the rules malformed; two Ask rules with one opt-in give Ask me first; a matching No gives No; a job and a helper check are never moved; the daily cap; `--no-log`; a planted exception inside the score exits 2; the code guard (no `subprocess`, no network, no queue reader).
- [ ] L13.6 The whole-system test and the security note for layer 13 (6 h). Its own pull request, after the last slice that was merged, and only for the slices merged.
  - Work: scenarios in `tests/test_whole_system.py` (the owner's day gets a lapsed rule, a reopen, a petition and an autonomy move; fault scenarios: a lapsed rule at a scheduled job's start, a broken chain during a reopen, a petition flood, a forged input), the secrets sweep of `tests/test_scan_secrets.py` over the layer 13 output, `docs/security.md` and a dated section in `docs/SECURITY-SCAN.md` (what layer 13 adds and what it does not prove), `docs/testing.md`, the status docs.
  - Acceptance tests: after every scenario `logbook verify` is ok and only the exit codes each command may give appear; no planted secret or sentinel in any output or entry; the suite passes on Python 3.10 to 3.13; the pull request lists the slices that were not built.

### Layer 13 plan (added in the L13.0 pull request, not in the main table above, to ease merging)

| dates | work |
| --- | --- |
| Nov 11 | L13.0, the spec (this pull request) |
| Nov 12 to Nov 13 | L13.1 Elections (14 h), after the owner approves L13.0 |
| Nov 14 to Nov 16 | L13.2 Reversal (20 h) |
| Nov 17 to Nov 19 | L13.3 Courts and the rules change log (16 h) |
| Nov 20 | L13.4 Honest tension (5 h) |
| Nov 21 to Nov 26 | L13.5 Graded autonomy (32 h) |
| Nov 27 to Nov 28 | L13.6 the whole-system and security update (6 h); the last day any slice is merged |
| Nov 29 to Dec 2 | Freeze: only fixes for defects that tests find |
| Dec 3 | Submit |

The dates run in parallel with layer 12 (round 2, about 75 hours until Nov 22) and with the owner's README, demo and Devpost work (Nov 23 to Nov 28). They are a plan, not a promise: a slice that is not merged by Nov 28 is not merged, and the cut is from the end (graded autonomy first). If the owner approves the spec later than Nov 12 the dates move by the days lost and the cut moves with them; the freeze and the submission never move.

### Layer 13 status (added in the L13.0 pull request, not in the main table above, to ease merging)

| part | status | pull request | tests on main after it |
| --- | --- | --- | --- |
| 13 Correction and graded autonomy | L13.0 spec merged (PR 40); L13.1 elections built (PR 42); L13.2 Reversal built (PR 45); L13.3 Courts and the rules change log built (PR 48); L13.4 Honest tension built (PR 49); L13.5 Graded autonomy built (PR 51); L13.6 not started | PR 40 (spec); L13.1: PR 42; L13.2: PR 45; L13.3: PR 48; L13.4: PR 49; L13.5: PR 51 | |

When layer 12 and this pull request are both merged, this row moves into the main status table as its last row.

## Local backend (W6): `umwayi serve` (spec in the W6.0 pull request; built only after the owner approves it; no dates set)

Requirements W6.R1 to W6.R18, design.md "Local backend (W6)" (the owner's decision of Nov 12 mapped to the design, the shape of a request, the handler table, the gate, tokens, the fail closed table, the entries, the two refactors, the intake step, the page client, threats, failure modes, hours, W6-Q1 to W6-Q28). Added at the end of the file so it merges cleanly. The normal suite stays standard library only and needs no network beyond 127.0.0.1. Tests first, as real child processes where a process matters, with a planted fault for each of the faults of W6.R16.10. Effort, by the owner's answer of Nov 12 (W6-Q27): the first batch is W6.1 to W6.6 plus W6.9, about 53 hours; W6.10 (8 hours) follows it; W6.7 and W6.8 (13 hours, the chat refactors) wait until W4 starts. The dates are set by the owner after UI.7 merges, and nothing is placed in the schedule to Dec 3 until then; the freeze on Nov 29 does not move.

Order and pull requests (the owner's answer of Nov 12): **(a) W6.1 to W6.6** first, one pull request (the core, merged whole or not at all), then **(b) W6.9**, its own pull request. **(c) W6.10** follows as its own pull request (my reading: it is not inside the 53 hours; W6-Q27). **W6.7 and W6.8 wait until W4 starts**, one pull request each, goldens first (W6-Q17); no chat route is built before both are merged. The work of W4 (chat routes) and W5 (queue intake routes) is in their own specs and pull requests.

- [x] W6.0 (8 h) Requirements W6.R1 to W6.R18, the design section, these tasks, `docs/serve.md` (written as "specified, not built"), KNOWN-LIMITS 196 onward ("specified, not built"), `adapters/NOTES-w6.md`, the rule 10 and 12.R17.6 wording, and the links from PROJECT.md, architecture, the interface decisions log and the status log, written Nov 12. Docs and specs only. **Waits for the owner's approval.** The owner's decision of Nov 12 is at the top of the design section. The owner answered W6-Q1 to W6-Q27 on Nov 12 (all as proposed except Q12, Q15, Q22 and Q27, recorded in design.md under "Answers (owner, Nov 12)"); W6-Q28 was answered later on Nov 12 (approved as proposed: an approval for an Ask me first in a web chat is given at the console of `umwayi serve` with `Allow once? [y/N]`; with no terminal attached the request is rejected).
  - Acceptance tests: `python -m unittest tests.test_docs` passes; no em dash in any file the pull request touches; every safety rule of `.kiro/steering/product.md` other than rule 10 is word for word as it was; the pull request changes no file under `umwayi/`, `adapters/*.py`, `tests/`, `ui/` or `site/`.
- [x] W6.1 Tests first (9 h, W6.R16.1 to W6.R16.6). **Done Nov 12 in the W6 core pull request (W6.1 to W6.6).** 184 tests in `tests/serve/`; before the code 168 of them fail (ModuleNotFoundError for `umwayi.serve*`, no server to start), the 16 that pass are the tests of the test tools (`test_gen.py`) and one count of scenarios. The shape of the API the tests fix is in the docstrings of `tests/serve/support.py`. `tests/serve/`: `gen.py` (seeded generators from `getrandbits` and `random()`, the shrinker), `oracle.py` (the naive second implementation of W6.R5), the golden request for each route, the catalogue of at least 45 named mutations, the benign mutations, and the test modules listed in design.md "Files". Failing before the code; the pull request says how many fail and why.
  - W6.1.1 The generators, the shrinker and the oracle (3 h), with tests of their own (the same seed gives the same cases; the shrinker finds a planted two-header fault).
  - W6.1.2 The gate properties (3 h): total, sound against the oracle, one fault refuses, harmless changes change nothing, pure, token, no leak, the truth table, rate, the closed table, the body parser, the channel.
  - W6.1.3 The wire, token, entry, same code and fail closed modules (3 h), with the fake agents and the fixed roots they need.
  - Acceptance tests: each property runs 5000 cases for three fixed seeds and one fresh seed, finishes in under 30 seconds on the build machine, prints the seed and the shrunk case on failure, and gives the same cases on Python 3.10 to 3.13 for the fixed seeds (a test compares a digest of the first 1000 cases with a stored value).
- [x] W6.2 `umwayi/servegate.py` (6 h, W6.R5, W6.R6) **Done Nov 12 in the W6 core pull request.** All 45 tests of `tests/serve/test_gate_properties.py` pass (5000 cases for each of three fixed seeds and one drawn seed); four planted faults (Host skipped, `localhost` allowed, Origin not required on POST, token not compared) were each caught: `Facts`, `State`, `Verdict`, `decide`, `parse_body`, the route table, the buckets, the channel. Pure; imports only `hmac`, `hashlib`, `json`, `re` and `dataclasses`.
  - Acceptance tests: every property of W6.1.2 passes; a code guard shows the module imports nothing else; a table test compares the route list with `docs/serve.md`.
  - Also in the pull request that builds `umwayi serve` (W6-Q19, W6-Q20, the owner's answer of Nov 12): reword steering rule 5 to name the two loopback servers (the telemetry receiver and `umwayi serve`) that import the network modules only inside the function that starts them, and edit the layer 12 sentences that W6.R2.6 lists (12.R2, 12.R11, "The view only looks"). Acceptance: `tests/test_docs.py` passes, rule 5 and those sentences match what was built, and no other safety rule is changed.
- [x] W6.3 `umwayi/servetoken.py` and `umwayi serve token` (6 h, W6.R4) **Done Nov 12 in the W6 core pull request.** 25 of the 31 tests of `tests/serve/test_token.py` pass; the other 6 need the backend (W6.4 and W6.5). The example rules: the guard shell rule and the secrets rule of the three adapters (and the repo `rules.yaml`) now name `umwayi serve` and `serve.token`; the pinned hashes in `tests/test_starter_rules.py` of the four changed rules were updated for that: the record, create, rotate, revoke, status, the terminal check, the entries, the undo on a failed entry, `.gitignore` lines, the example rules for the three adapters, the exit codes 0, 1, 2 and 64.
  - Acceptance tests: `tests/serve/test_token.py`; a planted token is found nowhere; the record is 0600 under umasks 022, 077 and 0; a failed entry leaves the old record and prints nothing; the docs test finds the `.gitignore` lines.
- [x] W6.4 `umwayi/serve.py`, the shell (8 h, W6.R2, W6.R3, W6.R14, W6.R15) **Done Nov 12 in the W6 core pull request.** The strict reader, the handler class, the 16 slot limit and its 503, the request deadline, `.umwayi/serve.lock` (`runlock.held` takes a lock name now), the bind and its read back, the page with its `build.json` check and headers, start and stop on the main thread, the `serve` subparser, the allowlist lines of `tests/test_system.py` and `tests/test_automation.py`, `tests/test_exit_codes.py`; rule 5 and the layer 12 sentences reworded (W6-Q19, W6-Q20); W6-Q28 recorded as answered. Until W6.5 an allowed request gets 500 `error` (fail closed): the strict reader, the handler class, the semaphore and the 503, the deadline timer, the lock file, the bind and the read-back, the page with its `build.json` check and headers, start and stop (signals on the main thread), the start line, the `serve` subparser, `tests/test_exit_codes.py`, and the allowlist lines in `tests/test_system.py` and `tests/test_automation.py`.
  - Acceptance tests: `tests/serve/test_wire.py` (the bind and `/proc/net/tcp` checks, the fuzz, slowloris, 100 connections, the headers, the page cases, the exit codes and the order of the start checks); importing every umwayi module in a fresh process loads no network module; the schedule rules refuse `serve`.
- [x] W6.5 The pipeline (7 h, W6.R7, W6.R13) **Done Nov 12 in the W6 core pull request.** The request id, the body, the write lock, the kill switch, the rules check (`serve_request` is on `NEVER_AUTONOMY` and in `docs/rules.md`, `docs/autonomy.md` and the test), the command, the request entry, the summary counters, the degraded state; the handler table starts with `status` and `kill.on` and gets the rest in W6.6: the request id, the kill switch, the `serve_request` rules check (and `NEVER_AUTONOMY`, `docs/rules.md`), the writer lock, the command, the request entry, the summary counters, the degraded state.
  - Acceptance tests: the order of W6.R7 by spies; every row of the fail closed table; the entry shapes against patterns; no secret or sentinel anywhere; a logbook that cannot be written gives the degraded state; `logbook verify` is ok after 500 requests, 50 refusals of each kind and a restart.
- [x] W6.6 The first routes and the differential tests (9 h, W6.R8, W6.R1.1) **Done Nov 12 in the W6 core pull request.** The eleven handlers, `taskqueue.add_row` as the one extract (the command line calls it too), `serve.rules.example.yaml`, 41 scenarios through the command line and through a request on identical roots. The server's pipeline runs on the main thread because a logbook write can only run there (KNOWN-LIMITS 233): the handler table of design.md; the one extract (`taskqueue` function for the `--if-not-open` branch); `serve.rules.example.yaml`; 40 or more canned scenarios through the command line and through a request on identical roots.
  - Acceptance tests: `tests/serve/test_samecode.py` (the spies, the differential comparison of `queue.md`, the kill switch file and the command's entries, the code guard); a response contains no field the table does not list, with sentinels planted in every other field of every file a route reads (a path in `agents.yaml`, a title in the logbook, a line in `rules.yaml`); no route on the never list exists (a test lists every route and searches for the banned words).
- [ ] W6.7 Refactor A: the budget steps leave `_Run` (5 h, W6.R11.1, design.md "The chat routes"). Its own pull request, no change of behaviour. **Waits until W4 starts (W6-Q27).** **Goldens first, on the old code**, committed in a separate commit before the move.
  - Acceptance tests: the goldens (a clean run, a stop by the kill switch, a stop by the per-run cap, a refusal by the day cap, a telemetry error, a crash) give byte-identical ledger entries and exit codes after the move; the existing budget and agent tests pass unmodified; `budget.reserve` and `budget.settle` have unit tests of their own.
- [ ] W6.8 Refactor B: the owner's side leaves `_Run` and `acp.Chat` (8 h, design.md "The chat routes"). Its own pull request, no change of behaviour. **Waits until W4 starts (W6-Q27).** **Goldens first, on the old code.**
  - Acceptance tests: the transcripts of scripted fake ACP chats (a turn, a tool call, an Ask me first answered `y` and `n`, `:queue`, `:quit`, Ctrl-C, each stop reason) are byte-identical after the change; the existing ACP and agent tests pass unmodified; `request_stop` is what the signal handlers call; with `install_signals=False` a chat runs on a worker thread.
- [x] W6.9 The page client and its panel (8 h, W6.R2.5, W6.R6.7, design.md "The page client"). Its own pull request; the owner builds and commits the page. Changes `ui/` only (and the tests that forbid `fetch(`); `site/` is not changed. **Built Nov 12 in its own pull request (PR 72).** `ui/src/api/client.js` is the one module that sends a request (a closed table of six routes, the token in one variable, a strict reader that stops the client on any wrong answer), `ui/src/ui/backend.js` is the panel (status, queue, add, answer, close, Stop everything; no timer), the page's policy gained `connect-src 'self'`, and the bundle marks the client's region so `tests/test_ui_package.py` finds the word for sending only there. 362 Node tests of `ui/` passed (3 phone tests skipped without a Chromium), 27 of `site/`. Not tried in a real browser (that is W6.10's by-hand pass, the owner's).
  - Acceptance tests: the Node tests of the client against a fake `fetch` (every bad envelope, the requests against the route table, the token only in one variable); `tests/test_ui_package.py` finds `fetch(` only in the client's bundle region and the CSP meta tag equal to the old one plus `connect-src 'self'`; the built page is one file under about 2 MB; opened from disk it makes no request (the by-hand pass); `site/test` is unchanged and passes.
- [x] W6.10 Docs, the by-hand browser pass, planted faults and the mutation pass, the whole-system scenarios (8 h, W6.R16.9 to W6.R16.11, W6.R17). Its own pull request, after the others that were merged, and only for the parts merged. **Built Nov 12 in its own pull request, for the parts that are merged (W6.1 to W6.6 and W6.9); the by-hand browser pass is written and was NOT run.** (1) `tests/serve/test_scenarios.py`, 28 whole-system scenarios with `umwayi serve` as a real child process and a client that speaks the page client's requests, in Python and with the real `ui/src/api/client.js` run by Node (skipped without Node): the token lifecycle, a wrong or expired token, a wrong `Host` or `Origin`, the kill switch turned on mid-run and no route that turns it off, the queue (add, answer, close), a SIGKILL and a restart, the logbook entries, nothing written outside the root, loopback only. They live in `tests/serve/` and not in `tests/test_whole_system.py` (the owner, on PR 76: keep them there). The full mutation pass stays by hand before any pull request that changes the serve files, and is not in CI (the owner, PR 76). The code already existed, so they passed on their first run; their power to fail is shown by the planted faults, which several of them catch. (2) `tests/serve/faults.py` (96 planted faults in `servegate.py`, `serve.py`, `servetoken.py` and `client.js`, one or more for each fault of W6.R16.10 that can be built now), `tests/serve/mutation.py` and `mutation_cli.py` (one fault at a time in a throwaway copy of the tree, only the named tests, a time limit, a hang counts as caught, the real tree hashed before and after), `test_mutation.py` (17 tests of the tool and four real faults). Result: planted 96, caught 93, survived 3 (each shown equivalent), invalid 0. The first pass found three gaps (the query value shape, the days limit inside `servetoken`, distinct request ids), closed by `tests/serve/test_gaps.py` (7 tests) with no change of product code. (3) Docs: `docs/serve.md` (start it, what it refuses, how it is tested, the by-hand checklist), `ui/README.md`, `docs/interface.md`, `docs/security.md`, `docs/testing.md`, the README row, and the rule 10 sentence that said the page makes no request until W6.9 is merged. Not done: the chat faults of W6.R16.10 (W4), the by-hand pass in a browser, `docs/architecture.md`, `docs/exit-codes.md` and `docs/rules.md` were already made current in the build pull request.
  - Work: `docs/serve.md`, `docs/interface.md`, `docs/security.md`, `docs/architecture.md`, `docs/exit-codes.md`, `docs/rules.md`, `docs/testing.md`, `adapters/NOTES-w6.md` with the browser results (a second local origin trying `fetch` and a form post, a `Host` override, the page from disk), scenarios in `tests/serve/test_scenarios.py` (the owner's day through the page; fault scenarios: a flood of bad tokens, a broken logbook while serving, a rotated token), the secrets sweep over the backend's output, KNOWN-LIMITS corrected against what was built, the status docs.
  - Acceptance tests: after every scenario `logbook verify` is ok and only the codes each command may give appear; the mutation pass of at least 40 mutants has none surviving that is not shown equivalent; the suite passes on Python 3.10 to 3.13; the pull request lists the parts that were not built.

### W6 reserved tasks (own specs, not in the 53 hours)

- **W4 chat routes** (about 20 h): `umwayi/servechat.py`, the seven routes of W6.R9, the ring buffer, the idle timer, the events, the permission flow (the page can only reject; an approval is made at the terminal of `umwayi serve`, W6-Q12 and W6-Q28; allowing from the page needs a by-hand test of the page's threat model and the owner's approval), the page's chat view; needs W6.7, W6.8 and the core. OpenCode follows 10.48.
- **W5 queue intake routes** (about 14 h): `umwayi/intake.py` with `assess`, the five routes of W6.R10, the draft store, the page's intake view; needs the core. The questions are a fixed list judged by a pure function, no model (W6-Q15); an AI written intake is an option that the W5 spec decides.
- **W7 login for a deployed interface**: a spec of its own. Version 1 is login plus the public site with sample data and does not control a local backend (the owner, Nov 12, W6-Q22). A relay is decided after Dec 3. Nothing of it is built or promised here.

### W6 plan and status (added in the W6.0 pull request, not in the main tables above, to ease merging)

| part | status | pull request | tests on main after it |
| --- | --- | --- | --- |
| Local backend (W6) | W6.0 spec written Nov 12; the owner answered W6-Q1 to W6-Q27 on Nov 12 (four changed), W6-Q28 answered (approved as proposed); W6.1 to W6.6 built Nov 12 in one pull request (the core: the gate, the token, the server, the pipeline and the first routes); W6.9 (the page client) built Nov 12 (PR 72); W6.10 (docs, scenarios, planted faults, mutation pass) built in its own pull request, the by-hand browser pass written and not run; W6.7 and W6.8 wait for W4; dates set by the owner after UI.7 merges | W6.0: PR 61; W6.1 to W6.6: PR 64; W6.9: PR 72; W6.10: see the pull request | see the status log |

When W6 is approved and built, this row moves into the main status table as its last row.

## Goal orchestration (W9): `umwayi goal` (spec in the W9.0 pull request; built only after the owner approves it; no dates set)

Requirements W9.R1 to W9.R23, design.md "Goal orchestration (W9)" (the owner's words mapped to the design, the packet, the prompts, the states, the supervisor, the git list, the event log, approvals, the write order, the budget, the docs parts, the entries, the fail closed table, the pitfalls table, threats, hours, W9-Q1 to W9-Q14). Added at the end of the file so it merges cleanly. The normal suite stays standard library only and needs no network, no real AI helper and no browser. Tests first, with fake agents as real child processes where a process matters, and a planted fault for each pitfall. Effort: the first batch is W9.1 to W9.9 and W9.6b, about 68 hours (60 before the owner's worktree rule of Nov 12 added W9.6b, 9 hours, and took 1 hour off W9.7); W9.10 and W9.11 follow it; W9.12 to W9.16 are options that the owner may never ask for. The worktree per task is not an option: it is core, in W9.6b (W9.R8.1 and W9.R8.9 to W9.R8.16). The owner answered W9-Q1 to W9-Q14 on Nov 12, all as recommended. By W9-Q14 only W9.9 (the shared docs builder, 7 hours) may go before the Nov 29 freeze, and the rest comes after Dec 3; the freeze does not move. W9.9 is also the owner's task W17, the same task, to be built at a quiet moment right after the pull request of the W6 first batch (W6.1 to W6.6) merges. Only W9.9 has a row in the schedule table, with no date.

Order and pull requests: **(a) W9.9 first, its own pull request** (the docs script is useful alone and removes the doc conflicts of today's pull requests), then **(b) W9.1 to W9.5**, one pull request (the pure core, the logs, the state; nothing starts an AI helper), then **(c) W9.6**, its own pull request (the three options on `agent run`, goldens first), then **(d) W9.6b**, its own pull request (the worktree per task and `--workdir`, goldens first), then **(e) W9.7 and W9.8**, one pull request (the supervisor and the commands; the first code that starts an AI helper), then **(f) W9.10**, then **(g) W9.11**.

- [x] W9.0 (6 h) Requirements W9.R1 to W9.R23, the design section, these tasks, `docs/goals.md` (written as "specified, not built"), KNOWN-LIMITS 213 to 232 ("specified, not built"), `adapters/NOTES-w9.md`, and the links from PROJECT.md, README, architecture and the status log, written Nov 12. Docs and specs only; this pull request (PR 63) is not merged. The owner answered W9-Q1 to W9-Q14 on Nov 12, all approved as recommended (design.md, "Answers (owner, Nov 12)"); applied here: the Q13 paragraph in the build order of `.kiro/steering/product.md` and the Q14 schedule note. A new owner rule of the same day, the worktree per task as a core rule, supersedes the answer to W9-Q3 and is applied here too (requirements W9.R8, design "The worktree of a task", W9.6b below, KNOWN-LIMITS 229 to 232).
  - Acceptance tests: `python -m unittest tests.test_docs` passes; no em dash in any file the pull request touches; no safety rule of `.kiro/steering/product.md` is changed (rules 1 to 13 are word for word as they were; the only change to the file is the one build order paragraph of W9-Q13); the pull request changes no file under `umwayi/`, `adapters/*.py`, `tests/`, `ui/` or `site/`.
- [x] **W9.9 built** (Nov 12 2026, its own pull request; the rest of the first batch is not started) W9.9 (7 h, W9.R14) `umwayi/goaldocs.py` and `umwayi goal docs build|check`: the part formats, the strict part reader, the frozen base (`docs-parts/status-log/00-head.md`, `00-rows.md`, `00-tail.md`, `docs-parts/known-limits/00-base.md`, moved from today's files without a changed byte), the numbering, the checker of its own output, `build` and `check`, the `goal` subparser with only the `docs` sub-command, `tests/test_exit_codes.py`, and the `.gitignore` lines for nothing new. Its own pull request, first. **W9.9 is the owner's task W17: the same task, not two.** Build it at a quiet moment, right after the pull request of the W6 first batch (W6.1 to W6.6) merges, because the first build moves the text of `docs/status-log.md` and `docs/KNOWN-LIMITS.md` into `docs-parts/` and any open pull request that edits those two files would conflict with it. It is the only part of W9 that may go before the Nov 29 freeze (W9-Q14).
  - Acceptance tests: `tests/goal/test_docs_parts.py` (the first build equals today's `docs/status-log.md` and `docs/KNOWN-LIMITS.md` byte for byte; two parts in either order give the same output; a number once given never changes; 60 random sets build and agree with `tests.test_docs.check`; a bad part is refused and nothing is written; two branches that each add only their two part files merge in git without a conflict, and two that edit the shared file conflict); the planted faults of W9.R14.8; `tests/test_docs.py` passes on the output.
- [ ] **First batch** W9.1 Tests first (7 h, W9.R21). `tests/goal/`: `gen.py` (seeded generators from `getrandbits` and `random()`, the shrinker), `fake_agent.py`, `fakeroot.py`, the goldens of the status and the report, and the test modules of design.md "Tests". They fail before the code; the pull request says how many fail and why.
  - W9.1.1 The generators, the shrinker and the fake agent with its script language (3 h), with tests of their own.
  - W9.1.2 The fake root, the fake git repo (with a local `main`, an `origin/main` ref and `git worktree` support), the fake clock and the test modules for the seven pitfalls (4 h).
  - Acceptance tests: each property runs 5000 cases for three fixed seeds and one fresh seed, finishes in under 30 seconds on the build machine, prints the seed and the shrunk case on failure, and gives the same cases on Python 3.10 to 3.13 for the fixed seeds.
- [ ] **First batch** W9.2 `umwayi/goalpacket.py` (6 h, W9.R2.2, W9.R4, W9.R6.1, W9.R8.3 to W9.R8.6): `Packet`, `parse_plan`, `PROTECTED`, `scope_violations`, `TRANSITIONS`, `reason_for`, `roles_ok`, `parse_verdict`, `parse_check`, `parse_result_line`. Pure.
  - Acceptance tests: `test_packet.py`, `test_roles.py` (every pair of names), `test_verdict.py` (the nonce, the last line, total over random bytes); the state walk accepts only table transitions; 40 or more spellings of a protected path are all refused; a code guard shows the module imports only `json`, `re`, `hashlib`, `dataclasses` and `posixpath`.
- [ ] **First batch** W9.3 `umwayi/goallog.py` (5 h, W9.R12, W9.R11.2, W9.R13.6): the event shape, `valid_event`, `read`, `Writer`, the bounded line reader.
  - Acceptance tests: `test_log.py` (40 kinds of bad line, exactly one skip record each, never recorded twice, torn tail, 5000 random byte strings, linear time, the 10 MB line); the planted faults of W9.R12.6.
- [ ] **First batch** W9.4 `umwayi/goalwatch.py` (5 h, W9.R9.1, W9.R9.5, W9.R10): `signature`, `judge`, `Approval`, `expired`, the countdown text.
  - Acceptance tests: `test_watch.py` and the pure part of `test_approvals.py`; the planted faults of W9.R9.8 and W9.R10.7; a code guard shows the module reads no clock, file or process.
- [ ] **First batch** W9.5 `umwayi/goalstate.py` and `umwayi/goalbudget.py` (7 h, W9.R13, W9.R15, W9.R18, W9.R19): the state files, the strict parser of `umwayi goal` entries, the write order, `repair`, `deny_expired`, the lock, the ledger window and the caps.
  - Acceptance tests: `test_failwrite.py` (a fault at every step for every transition), `test_entries.py`, `test_files.py`, `test_budget.py`; `logbook verify` is ok after a fake goal with every kind of end; the planted faults of W9.R13.7 and W9.R15.8.
- [ ] **First batch** W9.6 `agent run --cap-uu N --model M --effort E` (6 h, W9.R15.3, W9.R15.6, design.md "Budget in detail"). Its own pull request, in `umwayi/cli.py`, `umwayi/agents.py` and `umwayi/budget.py`; no change when the options are not used. **Goldens first, on the old code**, committed in a separate commit: the argument lists, the entries and the exit codes of a clean run, a stop by the kill switch, a stop by the per-run cap and a refusal by the day cap, for both platforms.
  - Acceptance tests: the goldens are byte-identical after the change; the existing agent and budget tests pass unmodified; the new argument lists for both platforms; `--cap-uu` above `per_run` is 64; a model with a space, a leading dash or a NUL is 64; an OpenCode agent with `--effort` is 64; `docs/agent-front-door.md` and `docs/budget-governor.md` name the options.
- [ ] **First batch** W9.6b (9 h, W9.R8.1, W9.R8.9 to W9.R8.16) The worktree per task, a core rule (the owner, Nov 12), moved out of W9.12. Its own pull request, after W9.6, in `umwayi/agents.py`, `umwayi/cli.py` and the worktree half of `umwayi/goalgit.py`: `agent run NAME - --workdir PATH` and `agent check NAME --workdir PATH`, which accept only a path umwayi made under the fixed root outside the umwayi root, with the working folder rule of `agents.yaml` and the gate checks run for that folder; `goalgit.py` with the 18 argument lists, `run_git`, `worktree_path`, `check_path`, the `leftover`, `dirty` and `stale` checks, the cap of eight, and the lifecycle (make, verify, remove an unused one, remove after merged, the plan's). **Goldens first, on the old code**, in a separate commit: the argument lists, entries and exit codes of runs without the option, for both platforms.
  - W9.6b.1 `--workdir` on `agent run` and `agent check`, with the goldens (3 h).
  - W9.6b.2 `goalgit.py`: the list, the path functions, the checks and the lifecycle (3 h).
  - W9.6b.3 `tests/goal/test_worktree.py`: one group per point of W9.R8.1 and W9.R8.9 to W9.R8.16, each with its planted faults (3 h).
  - Acceptance tests: the goldens are byte-identical without the option and the existing agent tests pass unmodified; every refusal of W9.R8.10 is 64 and starts nothing; a leftover folder, a leftover branch, a dangling registration, an unregistered folder and a ninth worktree each stop the start with `leftover` and change nothing; a path outside the fixed root, a link and a worktree of another repo are refused; two tasks never share a worktree (the property test over 3 goals); cleanup only after merged and never with force; the owner's working copy is byte for byte unchanged by every command; the guard test of the 18 argument lists and the three writes; `docs/agent-front-door.md` names `--workdir`.
- [ ] **First batch** W9.7 `umwayi/goalrun.py` (9 h, W9.R7, W9.R8.2 to W9.R8.8, W9.R10.5, W9.R16, W9.R17): the seven start steps (using the worktree functions of W9.6b), the child, the watch, the fingerprint, the four prompts, the scope check, the tester and the check, `in review`, the merge observation, the cleanup call, the stop.
  - Acceptance tests: `test_kill.py`, `test_merge.py` (including the cleanup after merged), `test_git.py` (a hook in the repo does not run), `test_samecode.py` (the order of the start steps by spies; one child start; one git module; no network import; no shell), a whole fake goal with fake agents through to `in review`; the planted faults of W9.R10.7 and W9.R16.5 and W9.R17.5.
- [x] **W9.7 built** (Nov 13 2026, its own pull request, stacked on W9.6b) `umwayi/goalrun.py` and `tests/goal/test_goalrun.py` (one test file for the modules the spec names `test_kill.py`, `test_merge.py`, `test_git.py` and `test_samecode.py`): the start steps in order, the one child, the watch, the fingerprint, the four prompts, the scope check, the tester and the guide's check, `in review`, the merge observation, the cleanup call, the stop, and the guide's planning run in its own worktree. Fake agents are real child processes and each pitfall has a planted fault. Where the spec was open it took the reading that fails closed (KNOWN-LIMITS 265). Not built: W9.8 and any `umwayi goal` command, `goal_start` in `NEVER_AUTONOMY`, the status and report text, the stall entry detail. Called by no command.
- [ ] **First batch** W9.8 `umwayi/goal.py` (7 h, W9.R3, W9.R5, W9.R9.6, W9.R11, W9.R20, W9.R22): the commands `start`, `show`, `approve`, `run`, `status`, `answer`, `merged`, `stop`, `report`, the terminal check, the exit codes, the status text and the report, `goal_start` in `NEVER_AUTONOMY` with `docs/rules.md`, `goal.rules.example.yaml`, the example rules of the three adapters, `tests/test_exit_codes.py`, the allowlist guard for network imports.
  - Acceptance tests: `test_cli.py`, `test_status.py` (the golden), `test_report.py`, `test_owner_commands.py` (no terminal is exit 2 and changes nothing); the order of the steps; the schedule rules refuse the word `goal`; `tests/test_docs.py` passes.
- [ ] W9.10 Whole-system scenarios and the mutation pass (8 h, W9.R21.4 to W9.R21.6). Its own pull request, after the first batch, and only for the parts merged. `tests/test_whole_system.py`: the owner's day through `umwayi goal` with fake agents, a fault scenario for each pitfall, at least 30 mutants each killed by a named test.
  - Acceptance tests: after every scenario `logbook verify` is ok and only the codes each command may give appear; no mutant survives that is not shown equivalent; the suite passes on Python 3.10 to 3.13.
- [ ] W9.11 Docs current and the owner's by-hand run (4 h, plus the owner's time, W9.R21.7, W9.R22). The docs named in W9.R22.3 brought up to date, KNOWN-LIMITS 213 to 232 corrected against what was built, and one tiny real goal with Claude Code as the builder and Kiro as the tester (or the other way); the results in `adapters/NOTES-w9.md` with the date and versions. **Waits for the owner's real run.**
- [ ] W9.12 (option, 4 h) `--ahead N`: several tasks in review at once. The worktree per task is core since the owner's rule of Nov 12 (W9.6b), so what is left is the overlap rule on `files` (a task may start while another is in review only if their `files` do not overlap and it has no dependency), the supervisor starting the next task from the newest `main` while earlier ones wait, and the status and report lines for several tasks in review. **Needs the owner to ask for it (W9-Q4).** It is the only option left of the worktree work.
- [ ] W9.13 (option, 8 h) OpenCode as a builder, tester or guide. **Needs task 10.48 and a non-interactive ACP run first (W9-Q8).**
- [ ] W9.14 (option, 3 h) `umwayi goal retry G T`: a new task from the same packet with a new budget from the owner.
- [ ] W9.15 (option, 6 h) The snapshot counts goals that need the owner (a field in `umwayi view snapshot` and a station that moves nearer, as 12.R14 does for the queue). Counts only; no route is added.
- [ ] W9.16 (option, 8 h) The scope enforced during a run: a per-task overlay that `umwayi check` reads (W9-Q11). A change to the core check, with the layer 2 tests and a new fail closed table.

### W9 plan and status (added in the W9.0 pull request, not in the main tables above, to ease merging)

| part | status | pull request | tests on main after it |
| --- | --- | --- | --- |
| Goal orchestration (W9) | W9.0 spec written Nov 12; the owner answered W9-Q1 to W9-Q14 on Nov 12 (all as recommended); W9.9 (the shared docs builder, `umwayi goal docs build` and `check`) built Nov 12 in its own pull request; W9.1 to W9.8 and W9.6b (about 61 hours) not started; the worktree per task is core (the owner, Nov 12, superseding the answer to W9-Q3); only W9.9 (the docs script, also the owner's task W17) may go before the Nov 29 freeze, at a quiet moment right after the W6 first batch PR merges, and the rest comes after Dec 3; no dates set | W9.0: PR 63; W9.9: see the pull request | |

When W9 is approved and built, this row moves into the main status table as its last row.

## History backfill (W19)

- [x] **W19 built** (Nov 13 2026, its own pull request) `tools/backfill_history.py` and `tests/test_backfill_history.py`: a read only script that turns public pull request and CI history into derived records (counts and durations only) in a JSON lines file. In `tools/ci_map.json` and `tools/ci_shards.json`. Docs through `docs-parts`. Not built: a model field (GitHub does not record it), a token, any use of the records by rules or a routing table.

## W19: guidance.yaml and the enforce checks (the owner's task, Nov 13; two stages)

- [x] W19.1 Stage 1 (own pull request): `guidance.yaml` and `umwayi/guidance.py` (the strict loader that fails closed, the tier and `overrides` fields and `resolve`, the registry of four checks, `check_task`), `umwayi goal guard [TASKFILE]`, `tests/goal/test_guidance.py`, the docs parts and KNOWN-LIMITS 256. Design: "Guidance (W19), stage 1".
  - Also in this pull request: a required `tier` (1 to 6), `overrides`, `resolve`, a required `source_repo` (`umwayi-os` or `hub`), and the owner commands `umwayi guidance list` and `umwayi guidance verify --hub PATH`. Nine entries: four enforce, four advise, one owner. **Open:** the owner asked for six advise and three owner examples and named four and one; more wait for the owner's rule numbers. The hub hashes are those of hub commit 658a799 and `verify` may report a mismatch against a newer hub, which is correct.
  - Not done: calling `guard` from `goal start` and `goal run` (those commands are W9.8).
- W19.2 Stage 2: the concerns record checker is built in its own pull request (see "W19 part 2" above). The security checklist checks are a later task, not started here.
