# Status log archive

## Purpose

The status log (`status-log.md`) is built from part files and must stay under 300 lines. When it filled up (2026-11-26, PR 271), the 40 oldest rows moved here without a changed word. New rows still go in the status log through the part files; nothing here is edited.

## Current state

The rows below are the oldest of the log, newest first, in the same four columns: date, pull request, what, and the tests after it (Python 3.10 to 3.13).

| date | PR | what | tests after it (Python 3.10 to 3.13) |
| --- | --- | --- | --- |
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

## Decisions log

- 2026-11-26 (PR 271): the oldest rows moved out of `docs-parts/status-log/00-rows.md` because the generated status log reached 299 lines, and a test that adds two rows to a copy of it then failed. Moving rows keeps room for new parts.

## Open questions

- **Q-a1.** Should the build move the oldest rows by itself when the log nears 300 lines? Recommendation: yes, as a small owner stop pull request of its own, so no pull request has to do this by hand.
