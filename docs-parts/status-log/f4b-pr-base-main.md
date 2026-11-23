date: 2026-11-23
pr: none
what: F4b and F4c. The stacking rule is retired in code: the CI `plan` job runs `python -m tools.pr_base --event-file "$GITHUB_EVENT_PATH"` before it decides the plan, and a pull request whose base is not `main` fails it with "base is not main; one PR at a time" (a push passes; an unreadable event or one with no base fails closed), so `result` fails too. The pull request template gains "Story" and "Record" headings (the story above the record) and the line "Base branch is main". A change to a workflow file: owner stop.
tests: `tests/test_pr_base.py` (the real command on event files, with a planted event on another base), `tests/test_ci_workflow.py` and `tests/test_ci_plan.py` unchanged and passing.
