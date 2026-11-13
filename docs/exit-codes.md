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
| `umwayi serve` | 0 stopped by Ctrl-C or SIGTERM, 1 the logbook failed its tamper check (nothing started), 2 an unexpected error, a socket that did not read back as 127.0.0.1, or a stop that could not be recorded, 64 usage or config (a bad `--port` or `--page`, a port in use, no valid token, another server holds the lock); never 3 |
| `umwayi serve token create`, `rotate` | 0 done (the token is shown once, on a terminal), 1 refused (a record exists, none exists, or the output is not a terminal), 2 an unexpected error or an entry that could not be written, 64 usage (a bad `--days`); never 3 |
| `umwayi concerns check` | 0 the record is well formed, 2 any failure (one line each), an unreadable record or an unexpected error, 64 usage; never 1 or 3 (W19) |
| `umwayi routing check` | 0 the routing table or task log is well formed, 2 any failure (one line each), an unreadable file or an unexpected error, 64 usage (a missing path, an extra argument, a bad `--date`); never 1 or 3 (W19 part 3b) |
| `umwayi goal docs build`, `check` | 0 done or up to date, 2 a refusal (a bad part, a link that does not resolve, an em dash), a difference between the files and the build, or an unexpected error, 64 usage (any other `goal` command or a wrong argument); never 1 or 3 (W9.9) |
| `umwayi serve token revoke`, `status` | `revoke` 0, 1 (no record), 2; `status` 0 (it prints "No token." too); 64 usage; never 3 |
| `umwayi decision reopen` | 0 done, 1 refused (the record does not fit or is not intact; nothing changed), 2 an unexpected error, 64 usage (a bad id, hash, reason, name or date); never 3 |
| `umwayi petition` | 0 added, or the same petition already open; 1 refused (not a No rule, a limit, a broken logbook or rules file; nothing written); 2 an unexpected error; 64 usage (a bad rule id, helper or reason); never 3 |
| `umwayi autonomy record` | 0 recorded, 1 refused (no hash chain, a logbook that is not intact, a `--ref` already recorded with the outcome; nothing written), 2 an unexpected error, 64 usage |
| `umwayi autonomy status` | 0 printed, 2 an unexpected error, 64 a bad `--class` or `--date`; never 1 or 3 |
| `umwayi autonomy validate` | 0 valid (or no file), 64 invalid (every problem with a line number), 2 an unexpected error; never 1 or 3 |
| `umwayi queue answer` | as the other queue commands; 64 also for a decision without `--revisit-if` and a task with it |
| any command given a path longer than the system allows | 64, a usage error that does not print the path |
| the layer 9 adapters | never 1; any error blocks (Kiro 0 or 2, generic 0, 2 or 3) |

Each layer's doc lists its own codes in full.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-11 | `umwayi autonomy record` uses 0, 1, 2 and 64; `status` 0, 2 and 64; `validate` 0, 2 and 64; `umwayi check` keeps 0, 2, 3 and 64, and a move gives 0 | Layer 13, L13.5 (design.md, "Commands and exit codes"). |
| 2026-11-11 | `umwayi petition` uses 0, 1, 2 and 64; the same petition already open is 0 | Layer 13, L13.3 (13.R6.5, design.md "Commands and exit codes"). |
| 2026-11-11 | `umwayi decision reopen` uses 0, 1, 2 and 64; `queue answer` gives 64 for a missing or misplaced `--revisit-if` | Layer 13, L13.2 (design.md, "Commands and exit codes"). |
| 2026-11-11 | `umwayi rules due` uses 0, 3, 64 and 2, never 1; 3 when a rule lapsed so a scheduled job can notice (L13-Q9, proposal used) | L13.1, 13.R3.3. |
| 2026-11-11 | UI.5: no new exit code. The page in `ui/` and `site/` is not a command and returns none; the owner checks panel only shows commands to type, and the exit codes it asks the owner to record are those of the commands in the NOTES files | 12.R7 |
| 2026-11-12 | `umwayi serve` and its token commands use 0, 1, 2 and 64 and never 3 | W6.R15.1 and W6.R4.12. A request through the server carries the same codes in its `code` field, and 3 is Ask me first there (the word `ask`, `kill` or `budget`). |
| 2026-11-11 | `umwayi view snapshot` uses 0, 1, 2 and 64 and never 3: it asks the rules nothing and the kill switch does not stop it | 12.R4.8 (UI.2). Code 1 is its tamper check refusal, as for `logbook verify`; the owner needs the counts most when the switch is on. |
| 2026-11-10 | A path longer than the system allows is a usage error (64), not an unexpected error (2) | The security scan (S.2, PR 37). |
| 2026-11-10 | Layer 11 and the budget governor follow the layer 10 codes: 0, 2, 3, 64, never 1 | 11.R6 and B.R3; the steering file's older code 1 for refusals is not used by new commands. |
| 2026-11-08 | Unexpected errors exit 2 in `umwayi check` and inside helper and workflow steps, never 1 or 3 (H.5) | Hardening, PR 9: a crash is treated like No, never like Yes. |
| 2026-11-08 | Config and usage errors exit 64 in every command (8.5) | Layer 8, PR 8: a usage error is never read as an answer. |

## Open questions

None open.
