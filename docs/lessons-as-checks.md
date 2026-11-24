# Lessons A1 to A14 as checks (G8g)

## Purpose

The CI and merge lessons of the supervisor lessons note (A1 to A14, 2026-11-23) came from mistakes. A lesson that lives only in a note is forgotten. This page lists each lesson with the check that makes a build fail when it is broken, or says plainly why it stays text. A test (`tests/test_lessons_map.py`) reads this table and fails when a named check is missing, so the table cannot drift from the code.

"Enforced by code" is allowed here, and only here: a test that fails the build is code. It says nothing about a helper run, which stays cooperative today and enforced where built.

## Current state

Ten of the fourteen are checks. Four are text only, with the reason. Each cell is `check:` or `text only:`, then for a check the test file and a name that must appear in it.

| Id | The lesson | Check or reason |
|---|---|---|
| A1 | `docs/testing.md` stays under 300 lines | check: `tests/test_docs.py` `TestingMdMarginTests` (fails above 290 lines) |
| A2 | never hand edit `tools/ci_shards.json` | check: `tests/test_ci_shards.py` `test_the_file_is_the_fixed_point_of_balance` |
| A3 | a new test file needs its line in `tools/ci_map.json` | check: `tests/test_ci_map.py` `test_every_test_file_has_an_entry_and_no_entry_is_for_a_missing_file` |
| A4 | no `pty.` and no shell in the package | check: `tests/test_automation.py` `test_no_shell_anywhere` |
| A5 | KNOWN-LIMITS numbers are unique | check: `tests/test_limits_numbers.py` `test_no_number_is_used_twice_among_the_parts` |
| A6 | every status-log row of main stays on a rebase | check: `tests/test_lessons_as_checks.py` `test_every_status_part_of_main_is_still_here` |
| A7 | merge main before every push | check: `tests/test_lessons_as_checks.py` `test_a7_a_branch_that_is_behind_main_is_refused` (`tools/pre_push.py` stops a stale branch) |
| A8 | run the tests that read a file you changed | check: `tests/test_lessons_as_checks.py` `test_a_test_that_names_a_moved_file_is_found_even_when_the_path_is_written_in_pieces` |
| A9 | every number in a logbook entry has a test that makes it nonzero from a real event | text only: whether a planted fault can fire is a property of each feature; no general check can see it, so it is checked at review |
| A10 | a "tested with" line says only what was run | text only: no scan can compare a line with what ran. The related claim, that no doc says "enforced" before a real run, is checked in `tests/test_enforce.py` |
| A11 | check that the Docker daemon is up before reading an empty result | text only: it depends on the machine of the person, and Docker is not part of CI |
| A12 | clear conflicts in generated files by tooling | check: `tests/test_merge_main.py` `test_a_conflict_in_the_status_log_is_cleared_by_the_build` |
| A13 | probe the machine before designing on a kernel feature | text only: the probe is a judgement about a design; the PR states the split. A14 checks the outcome in CI |
| A14 | never claim a result from a skipped test | check: `tests/test_confine.py` `test_on_the_ci_runner_the_kernel_tests_run_and_do_not_skip` (fails on GitHub Actions when Landlock is missing) |

What I found already there: A1 (PR 196), A2, A3, A4, A5 (PR 197), A6 and A8 (PR 202), A12 (W21). What I built for this page: A7 (the stale branch stop in `tools/pre_push.py`) and A14 (the CI test). The guidance entries that point at these checks (task L1, `guidance.yaml`) are a separate owner stop.

## Decisions log

- 2026-11-24: ten of the fourteen are checks, as the fixes note recommended. The four text-only lessons keep a stated reason.
- 2026-11-24: A14 fails only on the Linux runner of GitHub Actions. On a Mac or any other machine the kernel tests skip as before, and the report says so.

## Open questions

- **Q1.** A10 stays text. Recommendation: keep it so, because a scan of "tested with" lines would pass lines that are false; the review reads them.
- **Q2.** Should a new lesson be accepted only with its check named in this table? Recommendation: yes, in the guidance entry as `check: NAME`, as the fixes note says.
