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

Built since (G7, read only part): `pr-queue.md` with its strict parser, `umwayi pr queue list` and `umwayi pr queue next` (`umwayi/prqueue.py`, `tests/test_prqueue.py`). They only read: no push, no merge, no `gh`, no network and no logbook entry. `next` counts the open tasks of `queue.md` as pending work; a task whose title ends with ` [blocked: REASON]` is named on a `blocked:` line and skipped, so the next task is named. Not built: `add` (it reads git), the conflict table and the watch. You edit `pr-queue.md` by hand until `add` exists.

## The design

### 1. The file `pr-queue.md`

One strict table, like `queue.md`. Columns: `branch`, `title`, `order`, `stops` (owner stop: yes or no, and why), `status` (`local`, `open`, `merged`, `closed`), `pr`, `head` (short sha), `files` (the files the branch touches, as a count and a hash of the sorted list). A person can read and edit it. The parser refuses anything unexpected with a line number and never the text of the line, and nothing is changed. Every change is written to the logbook, and rolled back when that fails.

### 2. The commands (`umwayi pr queue ...`)

- `add BRANCH` reads the branch from git, fills title, files and head, sets `local`.
- `list` prints the table.
- `next` is read only. It says what to push now: the first `local` branch in order, when no row is `open`, and only after it has been merged with main and the generated files are current. It prints the exact steps (merge, regenerate, `pre_push`, push, open, `pr_number`). When a row is `open` it says to wait and names the pull request. When the first `local` branch stops for the owner, it says so.
- `conflicts` prints the conflict table (item 4).

### 3. The watch (`umwayi pr queue watch`)

Read only polling of the open pull request through `gh` (the owner's own login; no token is read or printed). It uses the `pr_green` rule, so a check of an older commit is never green. On a merge it writes one logbook entry and prints the next step; on a failed check it prints which check failed; it never pushes, merges, comments or closes. It stops after a time limit and says why.

### 4. The conflict table

For each pair of queued branches, the files both touch, found with a trial merge in a throwaway checkout (`git merge-tree`, no change to any branch). Generated files are listed as "regenerated, not a conflict". The order of `next` is chosen from these facts, and a pair that conflicts outside the generated files is shown first so the order can be changed on purpose.

### 5. The rules the queue keeps

- One pull request open at a time, base main.
- The next branch is merged with main first, using `tools/merge_main`.
- The tests of `pre_push` run before a push.
- The pull request body says what stops for the owner.
- A pull request that stops for the owner is not merged by the queue, and the queue does not skip it silently: it stays `open` until the owner acts.

## Build order

1. The design note (this file). Docs only.
2. Items 1, 2 and 4 (the file, `add`, `list`, `next`, `conflicts`). Read only, no network. Tests with a fake git and a planted fault for each rule above.
3. Item 3 (`watch`). It calls `gh`, so it stops for the owner.

## Decisions log

- 2026-11-23 (owner): accepted. Design note first, after the Muse design note; then 1, 2 and 4 read only; then 3.
- 2026-11-24 (this note): the queue records and advises. It never pushes or merges.

## Open questions

- **Q1.** Where does `pr-queue.md` live? Recommendation: the root of the umwayi folder, next to `queue.md`, and not in the public repo's tracked files when it names private branches. The owner decides which.
- **Q2.** Does `watch` run as a scheduled job? Recommendation: no. It runs in a terminal or a goal session the owner starts, so no background process is left behind.
- **Q3.** Should `next` refuse when the open pull request is red? Recommendation: yes, with the failed check named. A red pull request is fixed, not worked around.
- **Q4.** Should a branch that stops for the owner block the queue behind it? Recommendation: yes, one pull request at a time is the rule. The note says so, and the owner can reorder by hand.
