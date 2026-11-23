date: 2026-11-23
pr: 199
what: F2 (a, c, d). Every status part dated 2026-11-22 or later said `pr: none` when it merged (37 parts); each now names its pull request, found from the files each merged pull request changed. A test, `tests/test_pr_numbers.py`, fails on any such part, and `python -m tools.pr_number` (after the pull request is opened) writes the number into the parts the branch added and rebuilds the status log. The scope check is described as "checked while its helper runs" and no longer as enforced (the module, its test, the status row, the broker row), and the two limits lines about who can widen the scope now say it in one wording. Docs, a helper and a test; no product code.
tests: `tests/test_pr_numbers.py`; the docs build.
