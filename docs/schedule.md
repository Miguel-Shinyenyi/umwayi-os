# Schedule to Dec 3

## Purpose

The plan of work up to the submission on Dec 3. It exists so the order of the remaining work, and who moved what, is in one place.

## Current state

| dates | work |
| --- | --- |
| Nov 7 to Nov 10 | Layers 1 to 11, logbook crash safety, the hash chain and the budget governor, all built (see [status-log.md](status-log.md)) |
| Nov 10 | Documentation layout (D.1): a short README and one doc per layer under `docs/` |
| Nov 10 to Nov 12 | Whole-system test and security scan (S.1, then S.2), moved up by the owner from Nov 23 to Nov 26 |
| Nov 13 to Nov 22 | Layer 12, the web interface (UI.1 to UI.5, about 50 hours), after the owner approves the UI.0 spec; see [interface.md](interface.md). It is no longer a non goal (the owner, Nov 10) |
| Nov 23 to Nov 28 | README, demo, Devpost text |
| Nov 29 to Dec 2 | Freeze: only fixes for defects that tests find, no new features |
| Dec 3 | Submit |

The full schedule, with the history of each move, is in [tasks.md](../.kiro/specs/umwayi-os/tasks.md), section "Schedule to Dec 3".

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-10 | The web interface is layer 12 and in scope before Dec 3, planned Nov 13 to Nov 22 (UI-Q1 to UI-Q5 answered) | The owner, Nov 10. The freeze and the submission do not move. |
| 2026-11-10 | S-Q16: the scan is built right after approval, Nov 10 to Nov 12; the web interface follows it | The owner's order. |
| 2026-11-10 | L11-Q14: layer 11 built right after its spec, not Nov 14 to Nov 15 | The owner's order. |
| 2026-11-09 | L-Q6 and C-Q4: crash safety before 7c-2; the scan after the budget governor | The owner's order (since moved up by S-Q16). |

## Open questions

- The layer 12 spec (PR 38) waits for the owner's approval; the build starts after it. If it is approved after Nov 13 the dates move by the days lost, never the freeze.
