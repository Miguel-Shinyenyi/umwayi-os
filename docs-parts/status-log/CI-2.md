date: 2026-11-12
pr: none
what: CI.2: the node job sets UMWAYI_REQUIRE_BROWSER=1 on its Node test step (ui/ and site/), so a runner without Chrome fails the job and the W1 phone tests no longer skip there. `tests/test_ci_workflow.py` pins the env line and proves with child processes that both phone test files throw the how-to-run message when a browser is required and missing, and only skip when it is not.
tests: see the pull request
