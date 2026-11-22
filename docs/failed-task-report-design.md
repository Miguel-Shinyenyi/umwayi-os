# The failed-task report and the "only these files" check: design note

## Purpose

This note covers finding F1 of the 2026-11-18 recordings (`recordings/2026-11-18/FEEDBACK.md`). R1 and option (b) are built (2026-11-22); (a), (c) and R2 are not. It has two parts. A correct task fails because a plan's check says "only these files", and the report of a failed task says `Branch: (none), tip (none)` while the work exists. Nothing in this note is built. The owner picks, and then one task builds the pick.

## Current state

Read at main `6846e47`. The recordings saw F1 twice: on goal G-0001, and again on a second goal on a fresh root at `985b1b3`.

- The supervisor allows two files for every task "by right": `docs-parts/status-log/G-NNNN-T-NN.md` and `docs-parts/known-limits/G-NNNN-T-NN.md` (`gp.own_files`, `umwayi/goalpacket.py:191`). The scope check lets the builder change them (`scope_violations(..., own=self.own)`, `goalrun.py` `scope_check`). `goal show` prints them as "the last two by right".
- The planning prompt (`planning_prompt`, `goalrun.py:251`) does not mention them. The builder prompt names the status file it must write. The tester prompt (`tester_prompt`, `goalrun.py:284`) lists only the task and its checks, and no allowed files.
- So a guide can write "git status shows only hello.py and test_hello.py". The builder obeys the packet and commits the part file. The tester reads the check, sees a third file, and says fail. The task ends `failed (tests)` with cause `check_failed`. The owner pays the spend (23 UU of the task's 200 UU in both runs).
- The report line `Branch: ..., tip ...` reads `t["branch"]` and `t["tip"]` of the task file (`goal.py` `report_lines`). Those two are written only by the move to `in review` (`goalrun.py:1140`, `change_state(..., branch=, tip=)`). A task that fails in any other way never gets them, and `_files_changed` then says `not counted`. The worktree and the commit are still there: `discard_unused_worktree` keeps a worktree once a builder started.
- Both values can be computed without reading any helper text: the branch is `gp.branch_name(goal, task)` (`umwayi/g-0001-t-01`) and the worktree path is `GIT.worktree_path(root, goal, task)`.

## Part 1: what the report of a failed task should print

For a task that is `failed`, `stopped` or `needs owner` and whose builder started:

An example, with the values of the first F1 run:

```
- Branch: umwayi/g-0001-t-01, tip bb8b677 (kept, not merged)
- Worktree: <real root>-worktrees/g-0001-t-01 (exists)
- Files changed: 3
```

The tip is a hash and the paths are computed from ids, so no helper text reaches the report (W55b stays). Two ways to get the tip:

- **R1, record it when the task ends.** `finish()` adds `branch` and `tip` to the failed move when a commit exists (`GIT.head` of the worktree). One more write at the end of a run; the task file then always says where the work is, even if the worktree is later removed. The task file grows by two keys it already has. Recommended.
- **R2, read it when the report is made.** `report_lines` asks git for the head of the worktree path. No change to what a run writes. The report is wrong or empty once the worktree is gone, and a read of git at report time can fail.

Either way, `(none)` stays only for a task whose builder never started or made no commit, and the line says why (`no commit`).

## Part 2: the "only these files" check, proposals (a) to (c)

| | What it changes | For | Against |
|---|---|---|---|
| (a) tell the guide | One sentence in `planning_prompt`: the two part files are always allowed and must not be named in a "no other file" check. | Fixes the cause: the check is never written. Smallest change. | A prompt is advice. A guide can still write the check. Tested only with a fake guide. |
| (b) tell the tester | One sentence in `tester_prompt` and `check_prompt`: the files "by right" are allowed; the check is judged without them. The two names are given. | Fixes the place that fails. The tester sees the real names, and they are fixed text from `own_files`. | A tester that reads "only" literally can still fail it. It changes the meaning of a check the owner approved, so the owner's plan must state it. |
| (c) the supervisor drops or rewrites such a check | Code in `parse_plan` finds a check that says "only" and names a file set, and removes or rewrites it. | No model has to obey. | Natural language: a match by words misses some and hits others. A rewrite changes text the owner approves, and the packet is checked against its `sha256` at every start (`goalrun.py:756`). Removing a check removes a real test. Not recommended. |

A fourth way sits beside these: refuse such a plan at `parse_plan` with a fixed word, so the owner sees `check names a file set` at the plan stage and not after a failed run. It has the same word-matching problem as (c), but it changes no text.

Evidence for (a) and (b): a goal text that told the guide about the part files (R2.2, try 2) passed every check and cost 31 of the task's 200 UU. Not verified: a plan worded without that help, a Kiro tester, and a second guide model.

## Recommendation

1. Part 1 with R1. It needs no judgement and fixes the part of F1 that hides work.
2. Part 2 with (b) and (a) together, as plain text in two prompts, each with a planted fault: a fake guide that writes the "only" check and a fake tester that must judge it without the part files. (c) is not built.
3. After both, a real run with the guide given no help. Until that run passes, F1 stays open in `KNOWN-LIMITS.md`.

This is a recommendation. The owner decides.

## What building it would touch

- Part 1 (R1): `umwayi/goalrun.py` (`finish`), `umwayi/goal.py` (`report_lines`, `_files_changed`), tests in `tests/goal/test_report.py`, and a docs part. Owner-facing wording changes, so it stops for the owner.
- Part 2: `umwayi/goalrun.py` (the three prompts). A changed prompt changes what a helper is told, so it also stops for the owner.

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-22 | Design note only. Nothing is built until the owner picks. | Round 3, task 3 of the owner's message: the proposals (a) to (c) of F1 are the owner's to decide. |
| 2026-11-22 | The owner picked R1 and option (b). Built: `branch` and `tip` recorded with a failed or stopped move once the builder ran; `Worktree:` line in the report; the tester and check prompts name the two files by right. (a), (c) and R2 are not built. | The owner's message of the same day. |

## Open questions

1. Answered: R1.
2. Is (b) alone enough, or should (a) be added, or a plan with an "only" check be refused at the plan stage as well?
3. Should the report of a failed task also say that the worktree is kept and for how long?
