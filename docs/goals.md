# Goal orchestration (W9): `umwayi goal`

## Purpose

`umwayi goal` lets the owner give one goal in plain words. umwayi splits it into small task packets, runs them one at a time through its own gate (the rules check, the kill switch, the budget governor and the logbook) with a builder and a different tester, and reports. The owner approves the plan and merges the results. The system never merges.

## Current state

**Specified, not built.** This page was written in the W9.0 pull request (Nov 12 2026, docs and specs only). Nothing below exists in `umwayi/` yet. It is made current in each build pull request ([tasks.md](../.kiro/specs/umwayi-os/tasks.md), W9.1 to W9.16). The spec: [requirements W9.R1 to W9.R23](../.kiro/specs/umwayi-os/requirements.md), [design "Goal orchestration (W9)"](../.kiro/specs/umwayi-os/design.md), the platform facts in [NOTES-w9.md](../adapters/NOTES-w9.md). The owner has not answered W9-Q1 to W9-Q14 yet; each has a recommendation, and the spec is written with the recommendations. No dates are set.

### The roles

| role | who | does |
| --- | --- | --- |
| owner | you | gives the goal, approves the plan and the spend, picks the builder, tester, model and effort, answers what needs you, merges |
| guide | an agent from `agents.yaml` | splits the goal into packets, and checks each result against its packet; writes nothing |
| builder | an agent from `agents.yaml` | does one task on its own branch, inside the files its packet lists |
| tester | an agent from `agents.yaml`, never the builder | checks each acceptance check and says pass, fail or unclear; changes nothing |
| supervisor | umwayi itself | every deterministic check (files touched, tree changes, budget, progress, the states, the logs) |

### The commands

```
umwayi goal start TEXT [--guide NAME]
umwayi goal show G-0007
umwayi goal approve G-0007 --builder NAME --tester NAME [--model M] [--effort E] [--task-budget-uu N] [--goal-budget-uu N]
umwayi goal run G-0007
umwayi goal status [G-0007]
umwayi goal answer G-0007 T-02 yes|no
umwayi goal merged G-0007 T-02 [--commit SHA]
umwayi goal stop G-0007
umwayi goal report G-0007
umwayi goal docs build | check
```

Exit codes: 0 done, 2 No or an unexpected error, 3 Ask me first, 64 usage; never 1. `approve`, `answer` and `merged` need a terminal. `run` does the next task whose turn has come and returns: the next task starts only after the owner merged the one before it.

### The task packet

Ten fields: the goal in one sentence, context files, acceptance checks (1 to 8), where the outcome is recorded (the task's own status file and branch), a size of 15 to 90 builder minutes (aim for 60), the model and the effort (the owner's, blank until approved), the files the task may touch (never the protected ones: `rules.yaml`, `agents.yaml`, `units.yaml`, the logbook, the steering files, the CI workflow, `docs/status-log.md`, `docs/KNOWN-LIMITS.md`), and the budget in UU (the owner's).

### The states

`queued`, `running`, `in review`, `needs owner`, `merged`, `failed`, `stopped`. A closed table of moves, a closed list of reason words, and one logbook entry for every change, written before the file that holds the state. A failed or stopped task halts the goal; there is no automatic retry.

### Every start

The kill switch, the state, the rules (`goal_start`, then `agent_run` and `budget_check` inside `agent run`), the gate checks, the independence of tester and builder, the run lock and a clean checkout, the budget cap, then one start entry and the child `umwayi agent run NAME -`. No rule means Ask me first.

### The seven pitfalls, each with a test

| pitfall | what the spec does | requirement |
| --- | --- | --- |
| an approval that waits silently | every approval has a deadline and defaults to No; it is a logbook entry, a queue row, the top of `status` and a line on the terminal; every command enforces the deadline first | W9.R9 |
| a stalled or looping builder | stop after 30 minutes with no change of the work tree, or after two identical errors in a row | W9.R10 |
| a status that shows only "connected" | `status` prints the last real event and its age before anything about the process, and says QUIET | W9.R11 |
| one malformed log line stalling the log | the event log reader skips a bad line, records it once and goes on; the logbook itself is never skipped past | W9.R12 |
| a failed log write that lets work continue | every write is checked; a failure stops the child and the goal (exit 2) | W9.R13 |
| parallel edits of shared files | one status part file and one limits part file per task; `umwayi goal docs build` makes `docs/status-log.md` and `docs/KNOWN-LIMITS.md` | W9.R14 |
| cost growing with autonomy | a budget in UU per task and per goal, a cap handed to every run, the goal stops when spent | W9.R15 |

### How it is tested

Property based tests with seeded generators and no outside package, fake agents as real child processes, a temporary git repo, fault injection at every step of a state change, a golden `status` and `report`, a mutation pass of at least 30 mutants, and one by-hand run with real helpers. Details: requirement W9.R21.

### Known limits

Written now as expected limits, items 213 to 228 in [KNOWN-LIMITS.md](KNOWN-LIMITS.md); the build confirms or corrects them. The main ones: a tester is an AI helper and a pass is a claim; files are checked after the run, not during it; error recognition is a list of line markers; a squash merge is not seen and needs your `goal merged`; the shared docs are stale until rebuilt.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-12 | The goal orchestration is specified as `umwayi goal`, with the roles, the packet, the states and the seven pitfalls designed out, as W9. Nothing is built and no safety rule changes. | The owner asked for the spec on Nov 12 2026 (W9.0). |
| 2026-11-12 | The recommendations used by the spec until the owner answers: tester and guide differ from the builder by name; one dedicated checkout; wait for the merge; halt on failure; 30 minutes and two errors; deadlines of 7 days and 24 hours; Claude Code and Kiro first; a terminal for owner commands; the system prepares the docs rebuild; files checked after the run. | W9-Q2 to W9-Q11, design.md. |

## Open questions

W9-Q1 to W9-Q14 are open (design.md, "Open questions for the owner (W9-Q1 to W9-Q14)"), each with a recommendation:

- Q1 the name W9 (W8 is not defined in the repo); Q2 the tester and the guide are not the builder, by name; Q3 one dedicated checkout for the three roles; Q4 wait for the merge before the next task; Q5 halt on a failed task, no automatic retry; Q6 what counts as progress and as an error, and the numbers 30 minutes, 2 and 30 seconds; Q7 the approval deadlines; Q8 the platforms of the first batch (OpenCode waits for task 10.48); Q9 a terminal for the owner commands; Q10 who rebuilds the shared docs; Q11 files checked after the run, not during it; Q12 this repo only; Q13 a line in the steering build order, no safety rule changed; Q14 dates (W9.9 before the freeze if there is time, the rest after Dec 3).
