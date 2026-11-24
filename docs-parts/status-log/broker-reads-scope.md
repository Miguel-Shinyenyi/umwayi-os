date: 2026-11-23
pr: 194
what: The enforcement broker checks the scope of a task (W9.16). A run table row may carry `scope`, the absolute path of the scope file; `agent run --scope-file` puts it there for an enforced run. For a file write outside the scope (or a scope file that cannot be read) the broker answers No and writes the entry "The scope of the task gave No", as `umwayi check --scope` does. An overlay: it never allows. A row with no scope is as before. Stops for the owner.
tests: `tests/test_broker.py` (three new tests, a real broker process); no real helper.
