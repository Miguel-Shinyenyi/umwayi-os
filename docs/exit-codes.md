# Exit codes

## Purpose

Every umwayi command answers with the same small set of exit codes, so a script, a hook or the owner can tell Yes, No, Ask me first and a usage error apart without reading the text.

## Current state

Every command uses the same codes:

| code | meaning |
| --- | --- |
| 0 | Yes, or done |
| 1 | refused: something was checked and found wrong, nothing was changed |
| 2 | No, or an unexpected error (a crash is treated like No, never like Yes) |
| 3 | Ask me first |
| 64 | usage or config error: wrong arguments, a value that is not allowed, or a missing or invalid `umwayi.json`, jobs file or workflow file |

A missing or broken `rules.yaml` is not a config error: it gives Ask me first.

### Which commands use which codes

| commands | codes |
| --- | --- |
| `umwayi check` | 0 Yes, 2 No, 3 Ask me first, 64 usage |
| `logbook verify`, `archive verify` | 0 ok, 1 a problem found |
| `umwayi agent`, `umwayi schedule`, `umwayi budget` | 0, 2, 3 or 64, never 1 |
| `umwayi rules due` | 0 no rule has lapsed, 3 a rule has lapsed or `rules.yaml` is missing or broken, 64 usage, 2 an unexpected error, never 1 |
| `umwayi view snapshot` | 0 done, 1 the logbook failed its tamper check (nothing written), 2 an unexpected error, 64 usage (a bad `--out` or `--date`); never 3 |
| any command given a path longer than the system allows | 64, a usage error that does not print the path |
| the layer 9 adapters | never 1; any error blocks (Kiro 0 or 2, generic 0, 2 or 3) |

Each layer's doc lists its own codes in full.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-11 | `umwayi rules due` uses 0, 3, 64 and 2, never 1; 3 when a rule lapsed so a scheduled job can notice (L13-Q9, proposal used) | L13.1, 13.R3.3. |
| 2026-11-11 | `umwayi view snapshot` uses 0, 1, 2 and 64 and never 3: it asks the rules nothing and the kill switch does not stop it | 12.R4.8 (UI.2). Code 1 is its tamper check refusal, as for `logbook verify`; the owner needs the counts most when the switch is on. |
| 2026-11-10 | A path longer than the system allows is a usage error (64), not an unexpected error (2) | The security scan (S.2, PR 37). |
| 2026-11-10 | Layer 11 and the budget governor follow the layer 10 codes: 0, 2, 3, 64, never 1 | 11.R6 and B.R3; the steering file's older code 1 for refusals is not used by new commands. |
| 2026-11-08 | Unexpected errors exit 2 in `umwayi check` and inside helper and workflow steps, never 1 or 3 (H.5) | Hardening, PR 9: a crash is treated like No, never like Yes. |
| 2026-11-08 | Config and usage errors exit 64 in every command (8.5) | Layer 8, PR 8: a usage error is never read as an answer. |

## Open questions

None open.
