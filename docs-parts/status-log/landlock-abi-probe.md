date: 2026-11-23
pr: 187
what: Test only, `tests/test_landlock_probe.py`: it reads the Landlock ABI version of the kernel with `landlock_create_ruleset` and writes one line to standard error, so the CI log shows whether the GitHub runner has Landlock and which ABI. It builds no ruleset and restricts nothing. It is skipped, with the reason, where Landlock is not there (macOS; Docker Desktop's kernel returned ENOSYS). No product code changed.
tests: the probe itself, on macOS (skipped) and in CI (the log line is the result).
