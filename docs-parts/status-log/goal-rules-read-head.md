date: 2026-11-26
pr: 273
what: A small fix to `tools/goal_rules.py` found by using it on the umwayi-os self-build root: it now reads the repo's rules.yaml from git HEAD (`git show HEAD:rules.yaml`, with a fallback to the file when there is no commit), so a goal root whose own rules.yaml was changed and marked skip-worktree rebuilds the same rules. Before, the rebuild refused with "no single rule cc-ask-write". Owner stop (a tools script).
tests: tests/test_goal_rules.py, 16 tests (2 new: the committed text is read, and the file is the fallback); all passed on a local run (0.35 s). CI is the main check.
