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
| 2026-11-13 | see the pull request | 10.51 docs half: the OpenCode chat as built (10.43 to 10.50) in docs/agent-front-door.md, docs/adapters.md, the new adapters/opencode/README.md and the main README; KNOWN-LIMITS 180 to 187 made true to the code and 251 added (OpenCode runs with the owner's HOME, its stderr reaches the terminal); 248 corrected (an MCP name such as mcp__x__y is sent to the rules); design.md and tasks.md ticked for 10.47 to 10.50; the owner's real check written as a numbered list in adapters/NOTES-layer10.md. 10.51 stays open until the owner records the result. No code changed. | docs checks only |
| 2026-11-12 | 74 | 10.50: planted faults and mutation checks for the OpenCode chat. A helper (`tests/agents/opencode_mutants.py`, not shipped) applies one fault to a throwaway copy of the source, runs only the tests that should catch it with a time limit, and reports caught or survived: 153 faults (5 planted, 148 mutations), 149 caught, 4 survived (each a guard with a twin that refuses the same case). Round 1 found 12 gaps (9 new, 3 from 10.48 and 10.49); each got a test. One was a defect: the OpenCode chat stopped only the agent's process group, so a background command that left the group outlived a quit or the kill switch; `stop_agent` now uses the 7b stop (group and seen descendants) for OpenCode. `tests/agents/test_agents_opencode_faults.py` (21 tests), `tests/agents/test_opencode_mutants.py` (19 tests). | 2479 on Python 3.11 after the merge of main (3 shards, 40 new); GitHub CI for 3.10 to 3.13 |
| 2026-11-12 | 72 | W6.9: the page client and its panel (ui/ only). `ui/src/api/client.js` is the one place that sends a request: it runs only on `http://127.0.0.1:PORT`, builds each request from a closed table that is a subset of the server's, keeps the token in one variable, reads every answer strictly and stops (forgets the token, sends nothing more) on any bad envelope, wrong status or failed request. `ui/src/ui/backend.js` is the panel (status, queue, add, answer, close, Stop everything), live view only. The page's policy is the old one plus `connect-src 'self'`; the bundle marks the client's region and `tests/test_ui_package.py` finds the word fetch only there. Not built: docs, the by-hand browser pass and the other routes (W6.10), the chat and intake routes. | ui Node 362 pass, 3 phone skipped (no Chromium here); site Node 27 pass, 2 skipped; full Python suite not finished locally, CI is the record |
| 2026-11-12 | 71 | 10.49: the OpenCode chat end to end with the fake (the real stdio hook with `--platform opencode` first, then the permission request; Yes, No and Ask me first with the owner's y and n; `always` never selected; a child session; one check entry per check; nothing of the conversation in the logbook; the kill switch mid turn gives 3). A permission request with no `name` is now at most Ask me first. `tests/agents/test_agents_opencode_turns.py`, 17 tests. | 2386 on Python 3.11 before the merge of main (full suite as the three shards); GitHub CI for 3.10 to 3.13 |
| 2026-11-12 | 70 | W9.9 (also the owner's task W17): the shared docs builder. `umwayi goal docs build` and `check` (`umwayi/goaldocs.py`) make this file and KNOWN-LIMITS.md from `docs-parts/`: one status part and one limits part per task, a strict reader that refuses a bad part, the text of both files moved into a frozen base without a changed byte, numbers given once by the build, and the output checked before it is written. `tests/goal/test_docs_parts.py` with planted faults; `tests/test_exit_codes.py` lists the two commands; goals.md, DOCS_MAINTENANCE.md, exit-codes.md, testing.md and tasks.md updated. From now on a pull request adds a part and does not edit the two files by hand. | 2421 on Python 3.12 (full suite) |
| 2026-11-12 | 65 | W1: mobile-first rework of the live view and the public site: the top bar takes its room in the page on a phone, a touch screen and a short window (it no longer covers the title), 44 pixel controls there, the hero, station panel and owner checks panel fitted at 375x667, 390x844, 412x915 and 360x640 upright and on their side; wide screens with a mouse unchanged; `ui/dist` rebuilt; 4 new Node tests that render the page in a real Chromium (`ui/test/phone.test.mjs`, `site/test/phone.test.mjs`; they skip without a Chromium); KNOWN-LIMITS 237 to 241 | 2438 on Python 3.10 and 3.13 (3 shards each; the 3 CI map tests fixed and rerun, then the affected modules again); 317 Node tests in ui/, 29 in site/ |
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
