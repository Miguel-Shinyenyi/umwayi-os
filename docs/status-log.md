# Status log

## Purpose

This page says where each part of umwayi-os stands and logs every pull request with its test count. It exists so the state of the project can be read in one place.

## Current state

### Status

Status: all eight layers are built: memory, rules, queue, archive, logbook, automation, helpers and workflows. Layer 9 (adapters for Claude Code, Kiro and any stdin and stdout tool) is built, see [Layer 9](adapters.md). Layer 10 (one front door for agents) is in progress: agents.yaml, the gate checks, `umwayi agent run` and `umwayi agent chat` (on your terminal, or over ACP for Kiro) for Claude Code and Kiro are built; for Claude Code over ACP (part 7, approved) the pinned adapter package, its gate checks (part 7a) and the chat (part 7b) are built, see [Layer 10](agent-front-door.md). Part 8 of layer 10 (OpenCode over ACP) and Muse Spark Open as an OpenCode model are specified, not built; the owner asked for OpenCode to be built before Dec 3. Layer 11 (scheduled runs through systemd user timers) is built, see [Layer 11](scheduled-runs.md). Known limits are listed in [docs/KNOWN-LIMITS.md](KNOWN-LIMITS.md). See `.kiro/specs/umwayi-os/` for requirements, design and tasks, and `.kiro/steering/product.md` for the product rules.

The full status table, with every task, is in [tasks.md](../.kiro/specs/umwayi-os/tasks.md), section "Status".

Layer 13 (correction and graded autonomy: elections, reversal, courts, the stop criteria and a graded autonomy score) is specified (L13.0, PR 40, docs and specs only). Slice 1, elections (L13.1: `review_by` on Yes rules and `umwayi rules due`), is built. Slice 2, reversal (L13.2: `umwayi decision reopen` and `queue answer --revisit-if`), is built. Slice 3, courts and the rules change log (L13.3: `umwayi petition`, the `umwayi rules` entries), is built. Slice 4, honest tension (L13.4: the stop criteria, the plain note and the words test), is built. Slice 5, graded autonomy (L13.5: `umwayi autonomy record`, `status` and `validate`, the opt-in and the thirteen gates), is built and off by default. See [corrections](corrections.md) and [autonomy](autonomy.md).

The local backend (W6, `umwayi serve`) was specified in W6.0 (PR 61, docs and specs only). Its core is built (W6.1 to W6.6, one pull request, Nov 12): the gate, the token, the server, the pipeline and the first routes. The page client (W6.9) is not built, so the page still makes no request. See [serve.md](serve.md).

Goal orchestration (W9, `umwayi goal`: a goal split into task packets, run one at a time through the gate by a builder and a different tester, the owner approves and merges) is specified (W9.0, PR 63, docs and specs only) and not built. The owner answered W9-Q1 to W9-Q14 on Nov 12, all as recommended; only W9.9 (the shared docs builder, also the owner's task W17) may go before the Nov 29 freeze. By a later owner rule of the same day, each task runs in its own git worktree made by umwayi from the newest main. See [goals.md](goals.md).

### Pull requests

| date | PR | what | tests after it (Python 3.10 to 3.13) |
| --- | --- | --- | --- |
| 2026-11-12 | 71 | 10.49: the OpenCode chat end to end with the fake (hook first, then the permission request; Yes, No, Ask me first with the owner's y and n; `always` never; child session; one check entry per check) and a permission request with no `name` is at most Ask me first (KNOWN-LIMITS 247) | see the pull request |
| 2026-11-12 | 67 | CI: path filters, a test map, three shards per Python version and one always-on `result` check (`tools/ci_plan.py`, `tools/ci_map.py`, `tools/ci_shards.py`), `tools/affected_tests.py` for sessions, and `.kiro/steering/builder-workflow.md`; no product code changed | 2370 |
| 2026-11-12 | 66 | 10.48: the OpenCode chat start (a private folder and a fresh token, `opencode acp` with the allow-listed environment and the inline config, the wait for the plugin's canary, the model compare, `auth_required`); `agent check` prints the start | 2211 |
| 2026-11-12 | 63 | W9.0: spec for goal orchestration (`umwayi goal`: a goal split into task packets, run one at a time through the rules check, kill switch, budget governor and logbook by a builder and a different tester; the owner approves and merges). Requirements W9.R1 to W9.R23, design, tasks W9.0 to W9.16, `docs/goals.md`, KNOWN-LIMITS 213 to 232, `adapters/NOTES-w9.md`; seven pitfalls designed out, each with a requirement and a test; docs and specs only. The owner answered W9-Q1 to W9-Q14 on Nov 12, all as recommended; W9.9 is also the owner's task W17 and the only part that may go before the freeze; one build order paragraph added to the steering file (no safety rule changed), schedule note in `docs/schedule.md`. New owner rule the same day, superseding the answer to W9-Q3: the worktree per task is core (W9.6b, first batch now 68 hours; `--ahead N` stays in W9.12) | 1899 on Python 3.11 (no code changed) |
| 2026-11-12 | 62 | 10.47: the fake `opencode acp` (a scripted OpenCode 2.2.7 over ACP that runs the real hook and the starter rules and writes the canary) and its 52 tests; no umwayi code changed | 1951 |
| 2026-11-12 | 64 | W6.1 to W6.6: the core of `umwayi serve` in one pull request (the gate `servegate.py`, the token `servetoken.py` and `umwayi serve token`, the server and the pipeline `serve.py`, the first eleven routes, `serve.rules.example.yaml`, 190 tests in `tests/serve/`); W6-Q28 recorded as answered; rule 5 and the layer 12 sentences reworded; KNOWN-LIMITS 233 to 236 | 2171 |
| 2026-11-12 | 61 | W6.0: spec for the local backend (`umwayi serve`: 127.0.0.1 only, a token, the same rules check, logbook and kill switch as the command line). Steering rule 10 and 12.R17.6 reworded by the owner's decision of Nov 12; requirements W6.R1 to W6.R18, design, tasks W6.0 to W6.10, `docs/serve.md`, KNOWN-LIMITS 196 to 212, `adapters/NOTES-w6.md`; docs and specs only. The owner answered W6-Q1 to W6-Q27 on Nov 12 (four changed: the page can only reject in a chat, intake without a model, W7 version 1 controls no local backend, first batch about 53 hours); W6-Q28 open | 1899 on Python 3.11 (no code changed) |
| 2026-11-12 | 59 | CI.1: CI runs on pull requests only and a newer push cancels the older run (one run, four jobs, per push; the names and the matrix unchanged), the npm download is cached on the 3.12 job; the per module test times are measured and a sharding plan is proposed, not built. Workflow, `docs/testing.md` and `tasks.md` only | see the pull request |
| 2026-11-12 | 58 | UI.7: High, tier 3, on the public site only (`ui/src/high/`, the High path of `boot.js`, the switch with High, five CC0 photographs listed in `site/high-assets.json`), `tests/test_site_assets.py`; the live view unchanged in behaviour; KNOWN-LIMITS 151 to 156 | see the pull request |
| 2026-11-11 | 57 | UI.5, first slice: access and contrast tests, the owner checks panel fits a phone, the fault map and mutation pass of 12.R10.6, the docs of UI.5, the interface check text brought up to date (25 steps); KNOWN-LIMITS 149 and 150. UI.5 is not finished: the lockfile scan, the scene polish and the owner's check wait | see the pull request |
| 2026-11-12 | 56 | The 13 OpenCode starter rules in the repo `rules.yaml` (a follow-up of 9.10 and 10.45), and their tests in `tests/test_starter_rules.py` | see the pull request |
| 2026-11-12 | 55 | 10.46: the six gate checks of an OpenCode agent (command, version, files, managed config, other config, route) in `agent check` and before `agent chat`; the chat itself is not built yet | 1872 |
| 2026-11-11 | 54 | UI.4: the owner checks panel (`ui/src/data/checks.js`, `notes.js`, `ui/src/ui/checks.js`) on the live view and the site, five B.10 capture steps in NOTES-layer10.md, `tests/test_checks.py`; KNOWN-LIMITS 146 to 148 | see the pull request |
| 2026-11-11 | 53 | 10.45: the OpenCode plugin (`adapters/opencode/plugin/index.js`, node: imports only), its starter rules and its tests under node | 1775 |
| 2026-11-11 | 52 | UI.3: the page reads the snapshot (`ui/src/data/snapshot.js`, the strict reader, the needs, the mapping table), the picker and drop on the live view and the site, unknown drawn as unknown; 12.R17.6 and rule 10 changed; KNOWN-LIMITS 142 to 145 | see the pull request |
| 2026-11-11 | 51 | L13.5: graded autonomy, off by default: the opt-in, `umwayi autonomy record`, `status` and `validate`, the thirteen gates and the move (layer 13, slice 5) | 1635 |
| 2026-11-11 | 50 | UI.6: the shared scene module (`ui/src/scene.js`) and the public site in `site/` (List and Standard, Next.js 16.4.6), `node --test` in the CI workflow; KNOWN-LIMITS 140 and 141 | see the pull request |
| 2026-11-11 | 49 | L13.4: honest tension, the stop criteria, the plain note and `tests/test_honest.py` (layer 13, slice 4) | 1500 |
| 2026-11-11 | 48 | L13.3: courts and the rules change log, `umwayi petition` and the `umwayi rules` entry (layer 13, slice 3) | 1465 |
| 2026-11-11 | 47 | 10.43 and 10.44: an OpenCode agent in agents.yaml (`provider`, `model`, acp only; `agent run` and `agent login` refused) and the pure `opencode_env()` and `opencode_inline_config()`; nothing starts OpenCode yet | 1405 |
| 2026-11-11 | 46 | 10.42: the OpenCode facts confirmed on 2.2.7 in a throwaway sandbox, and the spec changed where they differed (OC9, OC10, OC15); docs only | |
| 2026-11-11 | 45 | Layer 13 slice 2, Reversal: `umwayi decision reopen`, `queue answer --revisit-if`, `logbook.read_chained` | 1321 |
| 2026-11-11 | 44 | spec: layer 10 part 8, OpenCode over ACP (10.41), and Muse Spark Open as an OpenCode model (10.40); docs only, waits for the owner's approval | |
| 2026-11-11 | 43 | 9.10: starter rules for the adapter actions in the repo `rules.yaml`, and `tests/test_starter_rules.py` | 1265 |
| 2026-11-11 | 42 | L13.1: elections, `review_by` on Yes rules and `umwayi rules due` (layer 13, slice 1) | 1254 |
| 2026-11-11 | 41 | UI.2: `umwayi view snapshot`, the read only snapshot of counts for the web interface | 1200 |
| 2026-11-11 | 39 | UI.1 and UI.1b (merged): the first build was a stylised meadow; the owner asked for a different look on Nov 11 and it was reworked as the Kenyan highlands scene with the home content, the List and Standard tiers and the scene additions | see the pull request |
| 2026-11-10 | 38 | spec: layer 12, the web interface (UI.0); docs only, waits for the owner's approval | |
| 2026-11-10 | 37 | S.2: the security scan; 10 defects it found fixed | 1155 |
| 2026-11-10 | 36 | S.1: the whole-system test; a gap rule refusal now writes its entry | 1135 |
| 2026-11-10 | 35 | D.1: the short README, PROJECT.md and one doc per component under docs/ | 1104 |
| 2026-11-10 | 34 | spec: whole-system test and security scan, and D.1 | |
| 2026-11-10 | 33 | budget governor | 1091 |
| 2026-11-10 | 32 | logbook hash chain | 1001 |
| 2026-11-10 | 31 | layer 11 scheduled runs | 978 |
| 2026-11-10 | 30 | spec: layer 11 | |
| 2026-11-10 | 29 | layer 10 part 7c-3 | 934 |
| 2026-11-09 | 28 | layer 10 part 7c-2 | 929 |
| 2026-11-09 | 27 | logbook crash safety | 906 |
| 2026-11-09 | 26 | spec: logbook crash safety | |
| 2026-11-09 | 25 | tests only: the flaky Ctrl-C and SIGHUP test | |
| 2026-11-09 | 24 | spec: hash chain and budget governor | |
| 2026-11-09 | 23 | layer 10 part 7c-1 | 869 |
| 2026-11-09 | 22 | spec: layer 10 part 7c | |
| 2026-11-09 | 21 | layer 10 part 7b | 854 |
| 2026-11-08 | 20 | layer 10 part 7a | 829 |
| 2026-11-08 | 19 | spec: layer 10 part 7 | |
| 2026-11-08 | 18 | layer 10 part 6 | 783 |
| 2026-11-08 | 17 | layer 10 part 5 | 747 |
| 2026-11-08 | 16 | layer 10 part 4 | 719 |
| 2026-11-08 | 15 | layer 10 part 3 | 697 |
| 2026-11-08 | 14 | layer 10 parts 1 and 2 | 673 |
| 2026-11-08 | 13 | spec: layer 10 | |
| 2026-11-08 | 12 | layer 9 part 2: Kiro, generic, kill switch | 619 |
| 2026-11-08 | 11 | layer 9 part 1: Claude Code | 578 |
| 2026-11-08 | 10 | spec update: layers 9 to 11 | |
| 2026-11-08 | 9 | hardening and the whole-system test | 556 |
| 2026-11-08 | 4 to 8 | layers 4 to 8 | |
| 2026-11-07 | 1 to 3 | specs, layers 1 to 3 | |

A blank count means the pull request changed no test or its count was not recorded.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-10 | The status lives here and in the tasks.md status table; both change in the same pull request | DOCS_MAINTENANCE.md: docs describe the current state. |

## Open questions

None open.
