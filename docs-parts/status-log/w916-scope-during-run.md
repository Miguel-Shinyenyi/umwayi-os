date: 2026-11-23
pr: 191
what: W9.16, the scope of a task checked while its helper runs. New `umwayi/scope.py`; `umwayi check --scope FILE` answers No to a file write (Write, Edit, MultiEdit, NotebookEdit) outside the scope, as an overlay that never allows; the Claude Code hook takes `--scope FILE`; `agent run --scope-file` (a goal worktree, Claude Code only) hands it to the hook; the goal supervisor writes a scope file for every Claude Code run: the packet's files and the task's two own files for the builder, nothing for a tester, a check or a planning run. It changes the core check. Stops for the owner.
tests: `tests/test_scope.py`, `tests/goal/test_scope_overlay.py`; fake helpers and the real hook, no real Claude Code.
