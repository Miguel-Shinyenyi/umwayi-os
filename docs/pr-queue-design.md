# The PR queue (G7, design note)

## Purpose

This note designs a PR queue as a feature of the product. In rounds 5 and 6 I kept a list of finished branches by hand and pushed one at a time: build a branch, wait for the open pull request to merge, merge main into the next branch, regenerate the generated files, run the tests, push, open the pull request, number its status part. That job is the same every time and it went wrong when done from memory (a merge in the wrong folder, a check read from an older commit, one branch merged into another). umwayi-os runs by itself, so the job belongs in the product, recorded in the logbook.

The queue never pushes or merges by itself. A push publishes, so it stays an owner action or an Ask me first action through the rules gate. The queue says what to push next and why. This note builds nothing. The owner stops for the code that calls `gh` (G7).

## Current state

What exists and is reused:

- **The rule.** One pull request is open at a time, its base is main, and the next branch is merged with main before it is pushed. CI enforces the base (`tools/pr_base.py`, PR 204). the pull request template carries "Base branch is main".
- **The merge helper.** `python -m tools.merge_main` merges `origin/main` into the current branch and repairs the generated files listed in `tools/generated_files.json`. It never pushes. It stops with exit 3 when a conflict is not on the list.
- **The checks.** `python -m tools.pre_push` names and runs the tests a change can break. `python -m tools.pr_green PR` says green only for the check runs of the exact head commit. `python -m tools.pr_number` sets the number of the status part a branch adds.
- **The watcher.** A shell script in a job folder (not in the repo) polls `gh pr view` and exits on a merge, a closed pull request, the first failed check of the newest head, or all checks green. It is the first piece of the queue, but it is not product code and it does not write the logbook.
- **The queue file format.** `queue.md` has one strict table that a person can edit and a parser (`umwayi/taskqueue.py`) that rewrites only the row a command touches and logs every change. The PR queue can follow that model.

Built since (G7, read only part): `pr-queue.md` with its strict parser, `umwayi pr queue list` and `umwayi pr queue next` (`umwayi/prqueue.py`, `tests/test_prqueue.py`). They only read: no push, no merge, no `gh`, no network and no logbook entry. `next` counts the open tasks of `queue.md` as pending work; a task whose title ends with ` [blocked: REASON]` is named on a `blocked:` line and skipped, so the next task is named. `umwayi pr queue next --check` (B-0012) also exits 3 (Ask me first) when fewer than `keep_ready` branches are ready and a free task is pending, so a hook can tell that a session has not finished; it prints the same lines and stays read only. Not built: `add` (it reads git), the conflict table and the watch. You edit `pr-queue.md` by hand until `add` exists.

## The design

### 1. The file `pr-queue.md`

One strict table, like `queue.md`. Columns: `branch`, `title`, `order`, `stops` (owner stop: yes or no, and why), `status` (`local`, `open`, `merged`, `closed`), `pr`, `head` (short sha), `files` (the files the branch touches, as a count and a hash of the sorted list). A person can read and edit it. The parser refuses anything unexpected with a line number and never the text of the line, and nothing is changed. Every change is written to the logbook, and rolled back when that fails.

### 2. The commands (`umwayi pr queue ...`)

- `add BRANCH` reads the branch from git, fills title, files and head, sets `local`.
- `list` prints the table.
- `next` is read only. It says what to push now: the first `local` branch in order, when no row is `open`, and only after it has been merged with main and the generated files are current. It prints the exact steps (merge, regenerate, `pre_push`, push, open, `pr_number`). When a row is `open` it says to wait and names the pull request. When the first `local` branch stops for the owner, it says so.
- `conflicts` prints the conflict table (item 4).
- **The queue is never left empty (owner, 2026-11-24).** A setting `keep_ready` in `pr-queue.md` (the owner sets it, recommended 2) is the number of built, tested, unpushed branches to hold while the task list has open items. When fewer are ready, `next` adds a line: `queue low: 1 of 2 branches ready, 5 tasks pending: build TASK next`, naming the next pending task whose inputs exist. When that task needs an owner answer or a file, `next` prints `blocked: TASK needs ANSWER` and names the following task, so one open question does not empty the queue. `next` never starts the work. The final report of a session says `ready branches: N of keep_ready` with their head SHAs.

### 3. The watch (`umwayi pr queue watch`)

Read only polling of the open pull request through `gh`, asked as `tools/pr_green.py` asks it: the check runs of the exact head commit, never the list the pull request page shows (a watcher that read "no pending line" as "all finished" said green while the runs had not started) (the owner's own login; no token is read or printed). It uses the `pr_green` rule, so a check of an older commit is never green. On a merge it writes one logbook entry and prints the next step; on a failed check it prints which check failed; it never pushes, merges, comments or closes. It stops after a time limit and says why.

### 4. The conflict table

For each pair of queued branches, the files both touch, found with a trial merge in a throwaway checkout (`git merge-tree`, no change to any branch). Generated files are listed as "regenerated, not a conflict". The order of `next` is chosen from these facts, and a pair that conflicts outside the generated files is shown first so the order can be changed on purpose.

### 5. The rules the queue keeps

- One pull request open at a time, base main.
- The next branch is merged with main first, using `tools/merge_main`.
- The tests of `pre_push` run before a push.
- The pull request body says what stops for the owner.
- **The report is not the end of the turn (owner, 2026-11-24).** A session that has reported a pull request with a free task still pending and fewer than `keep_ready` branches ready has not finished: it builds the next task, in the same turn, and only then ends. Ending there is a stop that was not allowed. The report closes with one line, `next: TASK, started: yes or no`; a `no` while a free task is pending is the thing to look for. When every pending task is blocked, or the kill switch is on, or the owner has said stop, ending is allowed.
- A pull request that stops for the owner is not merged by the queue, and the queue does not skip it silently: it stays `open` until the owner acts.

## Build order

1. The design note (this file). Docs only.
2. Items 1, 2 and 4 (the file, `add`, `list`, `next`, `conflicts`). Read only, no network. Tests with a fake git and a planted fault for each rule above.
3. Item 3 (`watch`). It calls `gh`, so it stops for the owner.

## Decisions log

- 2026-11-23 (owner): accepted. Design note first, after the Muse design note; then 1, 2 and 4 read only; then 3.
- 2026-11-24 (this note): the queue records and advises. It never pushes or merges.
- 2026-11-24 (owner): the queue is never left empty while tasks are pending, so `next` reports `queue low` against `keep_ready`.
- 2026-11-24 (owner): a session does not end after a report while a free task is pending and the queue is low. The report ends with `next: TASK, started: yes or no`. The checks that would help a hook (`umwayi pr queue next --check`, exit 3 when the queue is low and a free task exists) and a Stop hook for the Claude Code adapter are PLANNED, each a separate owner stop pull request; nothing here is built, and nothing forces a session to follow it today (cooperative).
- 2026-11-24 (this note): `watch` reads the check runs of the head commit (the `pr_green` rule) and treats an empty list as "not yet", never as success.

## Open questions

- **Q1.** Where does `pr-queue.md` live? Recommendation: the root of the umwayi folder, next to `queue.md`, and not in the public repo's tracked files when it names private branches. The owner decides which.
- **Q2.** Does `watch` run as a scheduled job? Recommendation: no. It runs in a terminal or a goal session the owner starts, so no background process is left behind.
- **Q3.** Should `next` refuse when the open pull request is red? Recommendation: yes, with the failed check named. A red pull request is fixed, not worked around.
- **Q4.** Should a branch that stops for the owner block the queue behind it? Recommendation: yes, one pull request at a time is the rule. The note says so, and the owner can reorder by hand.
