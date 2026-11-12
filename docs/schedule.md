# Schedule to Dec 3

## Purpose

The plan of work up to the submission on Dec 3. It exists so the order of the remaining work, and who moved what, is in one place.

## Current state

| dates | work |
| --- | --- |
| Nov 7 to Nov 10 | Layers 1 to 11, logbook crash safety, the hash chain and the budget governor, all built (see [status-log.md](status-log.md)) |
| Nov 10 | Documentation layout (D.1): a short README and one doc per layer under `docs/` |
| Nov 10 to Nov 12 | Whole-system test and security scan (S.1, then S.2), moved up by the owner from Nov 23 to Nov 26 |
| Nov 11 to Nov 22 | Layer 12, the web interface (UI.1 to UI.5), re-estimated on Nov 11 at about 92 hours, cut by the owner the same day to about 75 (four cuts accepted, UI.4 and the drift of UI.3 stay); that is 3 to 15 hours over the window and is stated, see [interface.md](interface.md). It is no longer a non goal (the owner, Nov 10) |
| Nov 23 to Nov 28 | README, demo, Devpost text |
| Nov 29 to Dec 2 | Freeze: only fixes for defects that tests find, no new features |
| Dec 3 | Submit |

The full schedule, with the history of each move, is in [tasks.md](../.kiro/specs/umwayi-os/tasks.md), section "Schedule to Dec 3".

### Layer 13 (added 2026-11-11, in its own table to ease merging with layer 12)

| dates | work |
| --- | --- |
| Nov 11 | L13.0, the layer 13 spec (docs and specs only) |
| Nov 12 to Nov 13 | L13.1 Elections (14 h), after the owner approves the spec |
| Nov 14 to Nov 16 | L13.2 Reversal (20 h) |
| Nov 17 to Nov 19 | L13.3 Courts and the rules change log (16 h) |
| Nov 20 | L13.4 Honest tension (5 h) |
| Nov 21 to Nov 26 | L13.5 Graded autonomy (32 h) |
| Nov 27 to Nov 28 | L13.6 whole-system and security update (6 h); Nov 28 is the last day any slice is merged |

The owner stops the build where Dec 3 finds us; a slice is merged whole or not at all, and the cut is from the end. The freeze (Nov 29 to Dec 2) and the submission (Dec 3) do not move. The hours and the reasons are in [corrections.md](corrections.md) and in the design, "Hours and schedule effect".

### Goal orchestration (W9, added 2026-11-12, in its own table to ease merging)

| dates | work |
| --- | --- |
| set by the owner, before Nov 29 | W9.9 (7 h), the shared docs builder, also the owner's task W17: one status file and one limits file per task, a script builds `docs/status-log.md` and `docs/KNOWN-LIMITS.md`. The only part of W9 that may go before the freeze. Build it at a quiet moment, right after the pull request of the W6 first batch (W6.1 to W6.6) merges |
| after Dec 3 | W9.1 to W9.8 and W9.6b, the worktree per task (about 61 hours; the whole first batch with W9.9 is 68), W9.10 and W9.11; the options W9.12 to W9.16 (W9.12 `--ahead N` is 4 hours) only if the owner asks |

The freeze (Nov 29 to Dec 2) and the submission (Dec 3) do not move. No date is set for W9.9; the owner sets it. See [goals.md](goals.md).

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-12 | The worktree per task is a core rule (W9.6b): the first batch of W9 is 68 hours, 61 of them after Dec 3; W9-Q14 is unchanged | The owner, Nov 12 2026. |
| 2026-11-12 | W9-Q14: only W9.9 (the shared docs builder, also the owner's task W17) may go before the Nov 29 freeze, at a quiet moment right after the W6 first batch PR merges; the rest of W9 after Dec 3 | The owner, Nov 12 2026. |
| 2026-11-11 | Layer 12, round 2 (UI-Q17 to UI-Q22): three tiers, a public site in `site/` beside the static live view, one shared scene module, tier 2 fixes and scene additions; order UI.1b (PR 39), UI.6, UI.7 | The owner, Nov 11. The owner keeps the timeline; no scope is cut. |
| 2026-11-11 | The look of layer 12 changed (UI-Q12 to UI-Q16: the Kenyan highlands, natural features, a scattered layout, the home page); UI.1 (PR 39) is reworked, not merged; hours re-estimated | The owner, Nov 11. |
| 2026-11-10 | The web interface is layer 12 and in scope before Dec 3, planned Nov 13 to Nov 22 (UI-Q1 to UI-Q5 answered) | The owner, Nov 10. The freeze and the submission do not move. |
| 2026-11-10 | S-Q16: the scan is built right after approval, Nov 10 to Nov 12; the web interface follows it | The owner's order. |
| 2026-11-10 | L11-Q14: layer 11 built right after its spec, not Nov 14 to Nov 15 | The owner's order. |
| 2026-11-09 | L-Q6 and C-Q4: crash safety before 7c-2; the scan after the budget governor | The owner's order (since moved up by S-Q16). |

## Open questions

- The layer 12 spec (PR 38) waits for the owner's approval; the build starts after it. If it is approved after Nov 13 the dates move by the days lost, never the freeze.
