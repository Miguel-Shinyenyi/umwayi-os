date: 2026-11-23
pr: 179
what: Fix of PR 176. The `counts` entry of a task read `guard_n` and nothing set it, so a task that stopped on `guard_file_changed` said "0 guard findings". `finish_guard` in `umwayi/goalrun.py` now adds one where the finding is recorded. No fixed word changed. The task text named `umwayi/goal.py`; the code is in `umwayi/goalrun.py`.
tests: `tests/goal/test_guard_count.py`, a real run of the fake helpers; no real helper.
