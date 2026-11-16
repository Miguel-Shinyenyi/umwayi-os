# A deterministic backlog with scopes and promotion (W61, design note)

## Purpose

This note designs a backlog that says, by fixed rules, which task comes next, so umwayi-os moves on rules and not on a guide's reading. It is a design note only. Nothing here is built, and no code, rule, steering file, safety check or workflow changes with it.

The owner's decisions (Nov 16), which this note keeps as given:

- A new file, `backlog.md`, not `queue.md`: the queue's strict one-table parser holds questions and answers.
- One table with the columns id, title, scope (in or out), status, blocker, owner needed, rank and hold, and one deadline line (the freeze date).
- Promotion is a pure function. When no in-scope task is queued or running, the next task is the lowest ranked out-of-scope task with owner needed off, no blocker and no hold, and never after the freeze date.
- Anything unclear or unreadable is WAITING, exit 3.
- Read only first: `umwayi backlog next` prints the next task and why, and writes nothing. Moving or assigning a task is a separate, logged command.
- Promotion only prints the next task. It never creates a goal, because a goal needs the owner's approval.

## Current state

Nothing is built. These facts were read at main `3817f2a`; "missing" means umwayi has nothing for it, and nothing is guessed.

| what | today | where |
| --- | --- | --- |
| the queue | a question and answer queue, not a backlog: columns id, kind (task or decision), title, status (open, answered, closed), recommendation, answer, answered; ids `Q-NNNN`; a strict parser with exactly one table; one row rewritten per command, logged, rolled back if the entry fails | `umwayi/taskqueue.py`, `queue.md`, [queue](queue.md) |
| the build plan | `.kiro/specs/umwayi-os/tasks.md`: checkbox lines written by hand, with `**Open: ...**` prose for what waits. At `3817f2a` it has 230 ticked and 45 unticked lines (sub items included). No code in `umwayi/` or `tools/` reads it | `.kiro/specs/umwayi-os/tasks.md` |
| the freeze date | prose and a table row: "Nov 29 to Dec 2, Freeze" | [schedule](schedule.md) |
| scope, rank, hold, blocker, owner needed | missing as data. In `tasks.md` they exist only as words (for example "after Dec 3", "waits for W34"); reading them is a guess, so this design does not | |
| the date of a check | exists: the latest of the system date, `--date` and the newest logbook date | `rules.election_clock` |
| the idle line | `goalpacket.idle_line(goal, tasks)`, W60, on branch `w60-idle-line` (PR 132); not on main at the time of writing | W9.R11.8 on that branch |

## The file: `backlog.md`

In the root, next to `queue.md`. Plain Markdown that the owner can edit by hand. At most 256 KB, a regular file, UTF-8, plain newlines, no NUL.

```
# Backlog

Deadline: 2026-11-29

| id | title | scope | status | blocker | owner needed | rank | hold |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B-0001 | The idle line in goal status | in | running | none | no | 1 | no |
| B-0002 | The backlog reader | out | open | none | no | 2 | no |
| B-0003 | Agents as apps, Steward first | out | open | B-0002 | no | 3 | no |
| B-0004 | Model routing picker | out | open | none | yes | 4 | no |
```

Parser rules. The parser is strict, as `taskqueue.parse` is. Any problem makes the whole file WAITING, with the line number and never the line's text. Nothing is guessed, and no cell is read in a second way.

1. **Exactly one deadline line**, `Deadline: YYYY-MM-DD`, before the table. It must be a real date. No line, two lines or a bad date: WAITING.
2. **Exactly one table.** Its header is these eight names in this order, compared without regard to case, followed by a separator line. Any other table, column or order: WAITING.
3. **Every cell is checked:**
   - `id`: `B-NNNN` (four or more digits), unique in the file.
   - `title`: one line, 1 to 200 characters, no `|`.
   - `scope`: `in` or `out`.
   - `status`: `open`, `queued`, `running`, `done` or `dropped`.
   - `blocker`: `none`, or one or more ids of this file joined by `, `. A row cannot block itself.
   - `owner needed`: `yes` or `no`.
   - `rank`: a whole number from 1 to 9999, unique in the file.
   - `hold`: `yes` or `no`.
4. **No other value.** An empty cell, a word in another case (`Yes`), a blocker id that is not in the file, a repeated rank or id, or a row with the wrong number of cells: WAITING.
5. **At most 500 rows.** An empty table is allowed; it gives "nothing to promote".

## The pure function

`backlog.next_task(rows, deadline, today)`, in a new `umwayi/backlog.py`. It reads no file, clock or process. `rows` are the parsed rows, `deadline` and `today` are dates, and `today` comes from `rules.election_clock`, so a clock set back cannot reopen promotion. It returns one `Next` value: a `kind`, the row `id` or none, and a fixed `why` word.

| case, checked in this order | kind | why |
| --- | --- | --- |
| the file could not be read or parsed (decided before the call) | `waiting` | `unreadable` |
| an in-scope row is `running` | `in_scope` | `running`, with the lowest ranked such id |
| an in-scope row is `queued` | `in_scope` | `queued`, with the lowest ranked such id |
| `today` is on or after `deadline` | `waiting` | `frozen` |
| among the `out` rows with status `open`, owner needed `no`, hold `no`, and every blocker `done` (or `none`), the lowest rank | `next` | `promote`, with its id |
| out-of-scope `open` rows exist, but each is held, needs the owner or is blocked | `waiting` | `owner`, `hold` or `blocked` (the reason of the lowest ranked one) |
| no out-of-scope `open` row | `none` | `empty` |

- Lowest rank wins. Ranks are unique, so there is never a tie to break.
- A blocker counts as cleared only when its row is `done`. A `dropped` blocker still blocks; the owner edits the row.
- The deadline is the first day of the freeze, so promotion is allowed only on days before it (open question 2).

## The commands

| command | prints | reads | writes and logs |
| --- | --- | --- | --- |
| `umwayi backlog next [--date D]` | one line, for example `Next: B-0002 (rank 2): out of scope, open, no blocker, no hold, owner not needed. To take it: umwayi backlog move B-0002 in`, or `In scope: B-0001 is running; nothing is promoted.`, or `WAITING: B-0003 is blocked by B-0002.`, or `WAITING: backlog.md line 7: rank must be a whole number.`, or `Frozen: the deadline 2026-11-29 is reached; nothing is promoted.` | `backlog.md`, the logbook date | nothing: no file and no logbook entry |
| `umwayi backlog list` | the rows in rank order, one per line, and the counts per scope and status | `backlog.md` | nothing |
| `umwayi backlog move ID in\|out` | one line | `backlog.md`, the logbook | rewrites that one row: `move ID in` sets scope `in` and, if the status is `open`, status `queued`; `move ID out` sets scope `out` and, if the status is `queued`, status `open`. One entry, for example `Backlog B-0002: scope out to in, status open to queued.` |
| `umwayi backlog status ID WORD` | one line | the same | rewrites that one row's status cell; one entry `Backlog B-0002: status open to queued.` |

- `move` sets the status with the scope so that a row moved in is `queued` at once. Otherwise an in-scope `open` row would not stop promotion, and the next `backlog next` would name a second task.
- `move` and `status` change one row and keep every other byte. They write through the shared atomic writer and roll back if the entry cannot be written, as `queue.md` does.
- Both are owner commands: stdin and stdout must be a terminal, as `goal approve` requires (open question 3).
- The entries hold ids, scope words, status words and counts, never a title.
- No command creates a row. The owner adds rows, sets titles, ranks, blockers, owner needed and hold by editing the file. The file is the owner's.
- "Assign" has no column of its own. In this design, assigning a task means moving it `in` (open question 4).

## How it meets the W60 idle line

The two answer different questions and stay two functions. `idle_line(goal, tasks)` speaks about the tasks of one goal; `next_task` speaks about the backlog. They meet in `goal status` (and so in `umwayi up`), once both are on main:

- When a goal has an idle or waiting line, it is printed as W60 says. The backlog is not asked.
- When no approved, unstopped goal has a task that remains (every `idle_line` result is none and no task is queued, running, in review or needs owner), `goal status` adds one line from `next_task`, for example `Backlog: next is B-0002 (rank 2).` or `Backlog: WAITING (blocked).`
- A missing `backlog.md` adds nothing.
- This line never changes the exit code of `goal status` (0 or 2) or of `umwayi up`, and it writes nothing.
- A backlog row and a goal are not linked. The owner turns a promoted row into a goal with `goal start` and `goal approve`, and moves the row with `backlog status` (open question 5).

## Exit codes

Only 0, 2, 3 and 64.

- `backlog next`: 0 a task is named (`next` or `in_scope`), 3 WAITING (unreadable, frozen, held, blocked, owner needed, or no candidate), 2 an unexpected error, 64 usage. An empty backlog is 3 too, because something must be decided by the owner.
- `backlog list`: 0 printed, 3 the file is unreadable, 2 unexpected, 64 usage.
- `backlog move` and `backlog status`: 0 written, 2 refused (not a terminal, an unknown id, the same value as before, a logbook that cannot be written; nothing changed), 3 the file is unreadable, 64 usage.
- Never 1.

## What it never does

No network and no shell. It never creates, starts or approves a goal. It never runs an agent. It never raises or sets a budget. It never edits `tasks.md`, `queue.md`, `rules.yaml` or any file but the one row of `backlog.md` that `move` or `status` names. It never reads a guide's or an agent's words to decide, and never guesses a cell.

## What it does not prove

- A rank, a scope or a blocker can still be wrong. The owner sets them, and the function only follows them.
- A row marked `running` may not be running. The status is the owner's word, not goal state.
- It does not check that a title says what the work is, or that the work is small enough for one goal.
- The deadline is the owner's line in the file. A wrong date gives wrong promotion.

## Spec lines it would add or change

Added, a new section at the end of requirements.md, `### W61.R1` to `### W61.R6`:

- **W61.R1 The file.** `backlog.md` in the root: one deadline line and one table with the eight columns, and the cell rules 1 to 5 above. A problem is WAITING with the line number, never the text.
- **W61.R2 The function.** `backlog.next_task(rows, deadline, today)`, pure, with the cases of the table above in that order. `today` comes from `rules.election_clock`.
- **W61.R3 `backlog next` and `list`.** What they print. They write nothing and add no logbook entry.
- **W61.R4 `backlog move` and `status`.** Owner commands in a terminal. `move ID in` also sets `open` to `queued`, and `move ID out` sets `queued` to `open`. One row, the atomic writer, one entry with ids and words only, and a rollback if the entry fails. No command adds or deletes a row.
- **W61.R5 Exit codes.** 0, 2, 3 and 64, as above.
- **W61.R6 What it never does.** No network, no shell, no goal, no budget, no edit of `tasks.md` or `queue.md`.

Changed:

- W9.R11.8 (W60, once merged) gains: "When no approved goal that is not stopped has a task that remains, `goal status` adds one `Backlog:` line from `backlog.next_task` (W61.R2), or nothing when `backlog.md` does not exist. The exit code does not change."
- W44.R1.7 (W60) gains: "and the `Backlog:` line of W9.R11.8."
- The never list (13.R9.3) needs no change, because no rules action is added. `backlog move` is an owner command, not an agent action (open question 3).

## The tests it would need

| rule | test | planted fault |
| --- | --- | --- |
| one deadline line | `test_deadline_line_missing_or_twice_is_waiting` | take the first of two |
| one table, exact header | `test_a_second_table_or_a_column_out_of_order_is_waiting` | accept columns in any order |
| every cell checked | `test_each_bad_cell_is_waiting_with_its_line` (one case per column) | read `Yes` as `yes` |
| unique rank and id | `test_a_repeated_rank_is_waiting` | break the tie by id |
| unknown blocker | `test_a_blocker_not_in_the_file_is_waiting` | treat it as `none` |
| in scope first | `test_a_running_in_scope_row_stops_promotion` | promote while a row is `queued` in scope |
| lowest rank | `test_the_lowest_ranked_candidate_is_next` | pick the first row in the file |
| owner needed, hold, blocker | `test_each_flag_keeps_a_row_out` | skip the hold check |
| a blocker clears only when done | `test_a_dropped_blocker_still_blocks` | clear on `dropped` |
| the freeze | `test_on_the_deadline_nothing_is_promoted` | compare with `>` |
| the clock | `test_a_past_date_does_not_reopen_promotion` | use `--date` alone |
| read only | `test_next_writes_no_byte` (a snapshot of the root around the command) | write a logbook entry |
| no goal | `test_next_never_calls_goal_start` (an import and call scan) | call `goal.dispatch` |
| move is one row | `test_move_changes_one_row_and_logs_once` | rewrite the whole table |
| a moved row stops promotion | `test_after_move_in_next_names_it_in_scope` | leave the status `open` on `move in` |
| move needs the owner | `test_move_needs_both_terminals` | check stdout only |
| rollback | `test_move_is_rolled_back_when_the_entry_fails` | write the file after the entry |
| no title in an entry | `test_entries_hold_ids_and_words_only` | log the title |
| exit codes | rows in `tests/test_exit_codes.py` | a parse error exits 1 |

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-16 | Design note only: `backlog.md` with one deadline line and one strict table; `next_task` is pure; `next` writes nothing; `move` and `status` are logged owner commands; nothing creates a goal | W61, the owner's decisions of Nov 16. |

## Open questions

1. **Should an empty backlog be exit 3 or 0?** Recommendation: 3. Nothing to do is a decision for the owner, and a script that loops on exit 0 would spin.
2. **Is the deadline the first day of the freeze, or its last?** Recommendation: the first day (`2026-11-29`). Promotion stops when the freeze starts, as [schedule](schedule.md) says "no new features".
3. **Are `move` and `status` owner-only, or may an agent call them through a rule?** Recommendation: owner-only, in a terminal, for the first version. Scope is the owner's decision, and a rules action could later be added to the never list.
4. **What does "assign" mean without a column for it?** Recommendation: moving a row `in`. If the owner means naming an agent, add a ninth column in a later task; do not reuse `blocker` or `title`.
5. **Should a row's status follow goal state?** Recommendation: not now. Linking a row to a goal id needs a tenth column and a rule for every goal state; keep the status the owner's word until a goal run has used the backlog for a week.
6. **Should the first `backlog.md` be written from `tasks.md`?** Recommendation: no automatic import. Reading `tasks.md` prose is the guess this design avoids. The owner writes the first rows, or a one-time script makes a draft the owner checks line by line.
