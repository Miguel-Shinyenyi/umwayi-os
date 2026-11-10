# Schedule to Dec 3

## Purpose

The plan of work up to the submission on Dec 3. It exists so the order of the remaining work, and who moved what, is in one place.

## Current state

| dates | work |
| --- | --- |
| Nov 7 to Nov 10 | Layers 1 to 11, logbook crash safety, the hash chain and the budget governor, all built (see [status-log.md](status-log.md)) |
| Nov 10 | Documentation layout (D.1): a short README and one doc per layer under `docs/` |
| Nov 10 to Nov 12 | Whole-system test and security scan (S.1, then S.2), moved up by the owner from Nov 23 to Nov 26 |
| Nov 13 onward | Web interface, after the scan, with its own spec first; requirements.md still lists a web interface under "Non goals for Dec 3", which that spec has to change with the owner's approval |
| Nov 23 to Nov 28 | README, demo, Devpost text |
| Nov 29 to Dec 2 | Freeze: only fixes for defects that tests find, no new features |
| Dec 3 | Submit |

The full schedule, with the history of each move, is in [tasks.md](../.kiro/specs/umwayi-os/tasks.md), section "Schedule to Dec 3".

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-10 | S-Q16: the scan is built right after approval, Nov 10 to Nov 12; the web interface follows it | The owner's order. |
| 2026-11-10 | L11-Q14: layer 11 built right after its spec, not Nov 14 to Nov 15 | The owner's order. |
| 2026-11-09 | L-Q6 and C-Q4: crash safety before 7c-2; the scan after the budget governor | The owner's order (since moved up by S-Q16). |

## Open questions

- The web interface spec: it has to be written and approved before it is built.
