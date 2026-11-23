date: 2026-11-23
pr: none
what: `budget status` with no `units.yaml` now adds one line saying how to set real numbers: write a units.yaml in the root, format in `docs/budget-governor.md`. The first line is unchanged. Owner-facing wording.
tests: `tests/budget/test_status.py`, `tests/budget/test_units.py`; CI is the full run.
