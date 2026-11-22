section: Goal orchestration (W9), found while building the failed-task report
title: the tip of a failed task is read when it ends, and option (b) is advice to a model
number: 326

- The branch and tip of a failed or stopped task are written when the task ends, by reading the head of the kept worktree. A task that failed before this change keeps `(none)` in its file and report. A failure with no commit, or a worktree that is gone or cannot be read, also records nothing, and the report says `(no commit was recorded)` when a builder ran.
- The tip is the head at the moment the task ended. It is not checked against what the scope check or the tester saw, so a head that moved after a failed check is shown as it is.
- `Worktree:` shows `(exists)` or `(removed)` by looking at the path once, when the report is made. It does not show that the worktree is clean or that it is the one the builder used.
- Option (b) is text in two prompts. A tester can still read "only" literally and fail a check, and it can say pass for a task that changed another file. The guide's wording of the check is not changed (option (a) is not built). Only a real run with an unhelped guide shows whether the problem is gone; none was made.
- A stopped task whose builder was killed in the middle can record a head that holds half of the work.
