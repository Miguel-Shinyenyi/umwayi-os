section: Goal orchestration (W9), found while building the F1 follow-ups
title: option (a) is advice to the guide, and the worktree line states the rule of the code at the time of the report
number: 328

- The sentence in the planning prompt is advice. A guide can still list a part file in `files` (the plan is then refused as `protected`) or write a "no other file" check (the plan is accepted, and the tester is told in option (b) to judge it without the part files). Nothing refuses such a check at the plan stage, by decision: word matching misses and hits wrongly.
- Only a real run with a guide that gets no help shows whether (a) and (b) together remove the failure. None was made.
- The `Worktree:` line says what the code does at the moment the report is made: a failed, stopped or needs-owner task keeps its worktree, and a task in review loses it after the merge when the tree is clean. A later change to the cleanup would make the line wrong until it is changed too; the test `test_a_failed_tasks_worktree_is_still_there_after_another_run_and_the_report_says_so` fails then.
- A merged task whose worktree could not be removed (not clean, or git refused) shows `exists` with no rule.
