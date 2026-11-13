# Task log (W19, part 3b)

## Purpose

This page is the record of how umwayi-os was built, one row for each task, so the process is its own data. For each task
it keeps what was done, in which area, which model was used, how it ended, what the review found, how many credits it
used and the day. Later it can show which model suited which kind of task. The owner reads it. Nothing reads it to pick a
model, and the owner always chooses the model (see [model-routing.md](model-routing.md)).

## Current state

Built: the record format below, a starter file of rows for pull requests 66 to 79, and `umwayi routing check PATH`
(`umwayi/routing.py`), which checks the table. It prints one line for each failure to standard error and exits 0 if the
file is well formed, 2 on any failure, 64 for a wrong command line, and never 1 or 3. It changes nothing and runs only
when the owner runs it.

One row for each task. The columns, in this order, and what each may hold:

- task: what was done, starting with `PR N:` for a pull request. Not empty. Not the same as another row.
- area: one lowercase word, digits and hyphens allowed, at most 40 characters, such as `ci`, `docs` or `opencode`.
- model chosen: the model the owner chose for the task, in plain words, or `unknown` if it was not recorded.
- outcome: `merged`, `closed not merged` or `open`.
- review result: `approved`, `changes requested` or `none recorded`.
- credits used: `unknown`, or a plain number with at most two decimals, such as `12.5`.
- date: the day the task ended (the day a pull request was merged or closed), written YYYY-MM-DD and not in the future.

The checker also refuses a header that is not exactly the seven names, a row with another number of columns, a second
table, a cell over 600 characters, and a file that is unreadable, too big or not UTF-8. It never claims a row is true.

Where the starter rows come from: the pull requests of Miguel-Shinyenyi/umwayi-os (titles, merge or close day in UTC and
outcome, read from GitHub on 2026-11-13) and the status log. Neither the git history nor the status log records which
model a session used or how many credits it took. So every starter row says `unknown` for both, and I did not guess. No
pull request from 66 to 79 has a GitHub review, so every review result is `none recorded`. The owner merged them, and
no review is recorded on GitHub. PR 68 and PR 69 were throwaway proofs of the CI plan, closed on purpose.

From now on a builder session adds its own row in its pull request and fills in the model and the credits if it knows them.

| task | area | model chosen | outcome | review result | credits used | date |
| --- | --- | --- | --- | --- | --- | --- |
| PR 66: 10.48 the OpenCode chat start | opencode | unknown | merged | none recorded | unknown | 2026-11-12 |
| PR 67: W20 faster CI without losing coverage | ci | unknown | merged | none recorded | unknown | 2026-11-12 |
| PR 68: proof docs-only (close) | ci | unknown | closed not merged | none recorded | unknown | 2026-11-12 |
| PR 69: proof ui-only (close) | ci | unknown | closed not merged | none recorded | unknown | 2026-11-12 |
| PR 70: W9.9 the shared docs builder | docs | unknown | merged | none recorded | unknown | 2026-11-12 |
| PR 71: 10.49 the OpenCode chat end to end and the permission answers | opencode | unknown | merged | none recorded | unknown | 2026-11-12 |
| PR 72: W6.9 the page client and its panel | ui | unknown | merged | none recorded | unknown | 2026-11-12 |
| PR 73: CI.2 the node job requires a browser | ci | unknown | merged | none recorded | unknown | 2026-11-13 |
| PR 74: 10.50 planted faults and mutation checks for the OpenCode chat | opencode | unknown | merged | none recorded | unknown | 2026-11-13 |
| PR 75: 10.51 docs half, the OpenCode chat as built | docs | unknown | merged | none recorded | unknown | 2026-11-13 |
| PR 76: W6.10 docs, whole-system scenarios, planted faults and mutation pass | serve | unknown | merged | none recorded | unknown | 2026-11-13 |
| PR 77: W16 board status script | tools | unknown | merged | none recorded | unknown | 2026-11-13 |
| PR 78: OpenCode examples in agents.example.yaml | docs | unknown | merged | none recorded | unknown | 2026-11-13 |
| PR 79: W19 part 2 concerns record checker | concerns | unknown | merged | none recorded | unknown | 2026-11-13 |

## Decisions log

- 2026-11-13: Unknown model and unknown credits are written `unknown`, never guessed. Reason: the history does not hold
  them, and a made up value would look like data.
- 2026-11-13: A review means a review recorded on GitHub, or a result the owner writes in the row. Reason: no GitHub review
  is recorded for these pull requests, and the checker cannot tell a careful read from none.
- 2026-11-13: The model cell is free text, not checked against the routing table. Reason: the model used may be one that
  the table does not list, and a check would force a wrong name into the log.

## Open questions

- Who fills in the model and the credits for a task: the builder, or the owner after the merge? Recommendation: the builder
  writes the model if it knows it, and the owner writes the credits from the Kiro usage page, since a builder cannot see its
  own bill.
- Should the rows for PRs 66 to 79 be filled in by the owner from memory or from the Kiro usage history? Recommendation: only
  from the usage history. Leave `unknown` where it cannot be found.
- Should the log also hold tasks that have no pull request, such as a question answered in chat? Recommendation: no. One
  task, one pull request, one row.
