# Goal orchestration (W9): `umwayi goal`

## Purpose

`umwayi goal` lets the owner give one goal in plain words. umwayi splits it into small task packets, runs them one at a time through its own gate (the rules check, the kill switch, the budget governor and the logbook) with a builder and a different tester, and reports. The owner approves the plan and merges the results. The system never merges.

## Current state

**Specified, and only the docs builder is built.** This page was written in the W9.0 pull request (Nov 12 2026, docs and specs only). `umwayi goal docs build|check` (W9.9, `umwayi/goaldocs.py`) exists and is described in [The shared docs builder](#the-shared-docs-builder-built-w99). Everything else below, including the other `goal` commands, does not exist in `umwayi/` yet. The page is made current in each build pull request ([tasks.md](../.kiro/specs/umwayi-os/tasks.md), W9.1 to W9.16). The spec: [requirements W9.R1 to W9.R23](../.kiro/specs/umwayi-os/requirements.md), [design "Goal orchestration (W9)"](../.kiro/specs/umwayi-os/design.md), the platform facts in [NOTES-w9.md](../adapters/NOTES-w9.md). The owner answered W9-Q1 to W9-Q14 on Nov 12 2026, all approved as recommended. Only W9.9 (the shared docs builder, 7 hours, also the owner's task W17) may go before the Nov 29 freeze, at a quiet moment right after the pull request of the W6 first batch merges; the rest comes after Dec 3. The docs builder was built in its own pull request (W9.9, Nov 12 2026). No dates are set for the rest.

### The roles

| role | who | does |
| --- | --- | --- |
| owner | you | gives the goal, approves the plan and the spend, picks the builder, tester, model and effort, answers what needs you, merges |
| guide | an agent from `agents.yaml` | splits the goal into packets, and checks each result against its packet; writes nothing |
| builder | an agent from `agents.yaml` | does one task on its own branch, in its own git worktree, inside the files its packet lists |
| tester | an agent from `agents.yaml`, never the builder | checks each acceptance check and says pass, fail or unclear; changes nothing |
| supervisor | umwayi itself | every deterministic check (files touched, tree changes, budget, progress, the states, the logs) |

### The shared docs builder (built, W9.9)

`umwayi goal docs build` writes `docs/status-log.md` and `docs/KNOWN-LIMITS.md` from the part files in `docs-parts/`, so two pull requests never edit the same shared file. `umwayi goal docs check` builds in memory, compares bytes with the two files and writes nothing. Both exit 0 or 2 (a refusal, a difference or a part not yet built), 64 for wrong use, never 1 or 3. `goal` has no other sub-command yet.

- **Frozen base.** `docs-parts/status-log/00-head.md` (up to and including the table header and its separator line), `00-rows.md` (the old rows) and `00-tail.md` (from "A blank count means"), and `docs-parts/known-limits/00-base.md` (the whole old file). They were moved from the two files without a changed byte, and the first build with no parts equals them byte for byte. The status log is the head, the new rows (newest first by `date`, then `pr`, then id), the old rows, one blank line, the tail. KNOWN-LIMITS is the base, then each new section (in the order of its first part) with its entries.
- **A status part**, `docs-parts/status-log/ID.md`: the lines `date: YYYY-MM-DD`, `pr: N` or `none`, `what: ONE LINE`, `tests: TEXT` or `none`, in this order; then optionally one blank line and free text that is not copied into the table. `pr: none` shows "see the pull request"; `tests: none` shows an empty cell. `what` and `tests` hold no pipe.
- **A limits part**, `docs-parts/known-limits/ID.md`: `section: NAME`, `title: ONE LINE`, then one blank line and the body in Markdown (no heading of level 1 to 3 outside a code block). The id must also have a status part: the build gives numbers in the order of that part's `date`, then the id.
- **Numbers.** A limits part has no number. The build gives the next free one (after the largest in the base and the parts, at least 213) and writes `number: N` into the part, after the title. A number that is there is never changed. A number below the first free one, one used twice, or one that leaves a gap is refused.
- **Strict.** Every file in a parts folder except the base files must be a good part: `ID.md` with letters, digits, hyphens and underscores (a name starting `00-` is kept for the base), UTF-8, LF only, at most 64 KiB, one final newline, no em dash, no control character, no link or folder. A bad part refuses the whole build with a fixed message that names the file; it is never skipped, and nothing is written. A section the base already has, or a second part for one id (apart from letter case), is refused too.
- **The output is checked before it is written:** no em dash, the four parts and fewer than 300 lines for the status log, and every relative link and anchor resolves (the rules of `tests/test_docs.py`, in `check_output`).
- **Order of writing:** the numbers into the parts, then the two files, each through a temporary file. A build that stops half way is finished by running it again.
- **Who runs it:** not a task. The owner runs it, or a goal's last step does, in a docs-only change (W9-Q10). Between a merge of parts and the rebuild the two files are stale and `check` says so; so `check` is not a CI step. The suite checks that every committed part parses and that the plan passes the output checker.
- **Not built:** the logbook entry "docs built", the line "docs: N parts not yet built" in `goal status`, and the scope check that fails a task changing the two files (all need the later W9 tasks).

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

### One task, one worktree

A core rule (the owner, Nov 12), not an option. For each task umwayi makes a git worktree and a branch `umwayi/g-0007-t-02` from the local `main` as it is at that moment, in a fixed folder next to the umwayi root (`umwayi-os-worktrees/g-0007-t-02`), and runs the builder, then the tester, then the guide's check in it, each as a fresh `agent run ... --workdir PATH`. `--workdir` accepts only a path umwayi made. The owner's own working copy is never touched. The guide's planning run has a worktree of its own. A start is stopped by a leftover or dirty worktree (and by a local `main` that is behind `origin/main`, as far as the last fetch shows). A worktree is removed only after the owner's merged, never with force, and the branch is kept. Failed and stopped tasks keep theirs until you remove them with `git worktree remove`. At most eight exist under the root.

### The task packet

Ten fields: the goal in one sentence, context files, acceptance checks (1 to 8), where the outcome is recorded (the task's own status file and branch), a size of 15 to 90 builder minutes (aim for 60), the model and the effort (the owner's, blank until approved), the files the task may touch (never the protected ones: `rules.yaml`, `agents.yaml`, `units.yaml`, the logbook, the steering files, the CI workflow, `docs/status-log.md`, `docs/KNOWN-LIMITS.md`), and the budget in UU (the owner's).

### The states

`queued`, `running`, `in review`, `needs owner`, `merged`, `failed`, `stopped`. A closed table of moves, a closed list of reason words, and one logbook entry for every change, written before the file that holds the state. A failed or stopped task halts the goal; there is no automatic retry.

### Every start

The kill switch, the state, the rules (`goal_start`, then `agent_run` and `budget_check` inside `agent run`), the gate checks, the independence of tester and builder, the run lock and the worktree preconditions (the local `main` not behind `origin/main`, nothing left over), the budget cap, then one start entry, the task's worktree, and the child `umwayi agent run NAME - --workdir PATH`. No rule means Ask me first.

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

Written first as expected limits, items 213 to 232 in [KNOWN-LIMITS.md](KNOWN-LIMITS.md); the build confirms or corrects them. The main ones: a tester is an AI helper and a pass is a claim; each worktree is a full checkout and uses disk, leftover worktrees stay until removed, and `node_modules`, build folders and local config are not in a worktree; files are checked after the run, not during it; error recognition is a list of line markers; a squash merge is not seen and needs your `goal merged`; the shared docs are stale until rebuilt.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-12 | The goal orchestration is specified as `umwayi goal`, with the roles, the packet, the states and the seven pitfalls designed out, as W9. Nothing is built and no safety rule changes. | The owner asked for the spec on Nov 12 2026 (W9.0). |
| 2026-11-12 | The owner approved all fourteen answers as recommended: W9 stays the name (W8 is progress dashboards on the owner's board, not in the repo); tester and guide differ from the builder by name, warn on the same platform and model; the worktree per task (first approved as one dedicated checkout now, changed by the owner's worktree rule, see the next row); wait for the merge; halt on failure, no automatic retry; the literal reading, 30 minutes, 2 errors, 30 seconds; deadlines of 7 days and 24 hours, answer No when they pass; Claude Code and Kiro first, OpenCode after 10.48; a terminal for owner commands; the system prepares the docs branch and the owner merges; files checked after the run; this repo first; a short paragraph in the steering build order, rules 1 to 13 unchanged; only W9.9 before the freeze. | The owner, Nov 12 2026, W9-Q1 to W9-Q14 (design.md, "Answers (owner, Nov 12)"). |
| 2026-11-12 | New owner rule, which supersedes the answer to W9-Q3: the worktree per task is a core rule of the library, not an option. One task gets one worktree, made by umwayi from the newest main, with a fresh helper session per task, and no helper works in a shared checkout. The git list gains `worktree add` and `worktree remove`, the worktree lives under a fixed root outside the umwayi root and its path is checked, a dirty or leftover worktree stops the start, and cleanup happens only after the owner's merged. `agent run --workdir` and the worktree move from W9.12 into the first batch (W9.6b); `--ahead N` stays in W9.12 as the only option. The first batch is 68 hours. | The owner, Nov 12 2026. |
| 2026-11-12 | W9.9 is built: `umwayi goal docs build` and `check`, the frozen base in `docs-parts/`, the part formats and the strict reader. A limits part takes its order from the status part with the same id, because the specified limits format has no date. `pr: none` is shown as "see the pull request" in the PR column. | The spec left both open (W9.R14.2, W9.R14.4 and the design example). The owner may change either. |
| 2026-11-12 | W9.9 and the owner's task W17 are the same task. Build it at a quiet moment right after the pull request of the W6 first batch (W6.1 to W6.6) merges. | The owner, Nov 12 2026. Its first build moves the text of the two shared docs files, so an open pull request that edits them would conflict. |

## Open questions

None open. The owner answered W9-Q1 to W9-Q14 on Nov 12 2026, all approved as recommended (design.md, "Open questions for the owner (W9-Q1 to W9-Q14), with the owner's answers of Nov 12"). W8 is progress dashboards on the owner's board and is not in the repo (Q1).

W9.9 moved the text of `docs/status-log.md` and `docs/KNOWN-LIMITS.md` into `docs-parts/`. Any other pull request that edits those two files by hand is rebased by moving its text into parts (see the pull request of W9.9 for which were open). To decide later, if the waiting hurts: `--ahead` (W9.12, 4 hours, W9-Q4). To decide after the first real runs: the scope overlay during a run (W9.16, W9-Q11).

## Guidance checks (W19.1)

`guidance.yaml` at the repo root lists rules for the goal flow, each marked enforce, advise or owner. `umwayi goal guard [TASKFILE]` loads it and, given a task record (a JSON file with `goal`, `consequences`, `undo`, `acceptance_checks` and `open_prs`), refuses a task that breaks an enforce rule: exit 3 Ask me first and one line with the reason. A malformed `guidance.yaml` is exit 64, and a missing file or a source that changed since its hash was taken is exit 3, stop and ask the owner. The checks look at whether a field is there and well formed, never whether it is true ([KNOWN-LIMITS 254](KNOWN-LIMITS.md)). Design: "Guidance (W19), stage 1" in `.kiro/specs/umwayi-os/design.md`. Not built yet: the call from `goal start` and `goal run` (W9.8), the entries for consequences and undo and for acceptance checks, and the advise and owner examples.
