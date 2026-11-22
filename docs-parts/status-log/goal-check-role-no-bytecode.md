date: 2026-11-22
pr: none
what: The goal supervisor now gives every helper role `PYTHONDONTWRITEBYTECODE=1`, not only the builder and the tester (W55a). The first real goal run failed with `readonly_role_changed_tree` in the guide's check step: the check is a read-only role, its Python wrote a `__pycache__` into the worktree and the task failed although the tester had passed all six checks. One line in `umwayi/goalrun.py` and one test. Not a regression of an open change: it was on main.
tests: see the pull request
