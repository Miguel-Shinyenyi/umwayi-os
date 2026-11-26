date: 2026-11-26
pr: 271
what: The owner's option (c) for independence: a tool that builds the rules.yaml of a goal root from the repo's own pinned rules.yaml, `tools/goal_rules.py`. It drops `cc-ask-write` and `cc-ask-shell` and appends the builder rules for the worktree folder, `python3 -B -m unittest`, the read only `git log`, `git show` and `git ls-files`, and Yes rules for three named agents (`agent_run`, `goal_start`, `budget_check`); every No rule stays and the pinned file is not touched. The text is parsed by the real rules parser before it is printed. Nothing is read from the network; no token is touched. Owner stop.
tests: tests/test_goal_rules.py, 14 tests; all passed on a local run (0.12 s). CI is the main check.
