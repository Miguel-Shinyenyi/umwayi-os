date: 2026-11-22
pr: none
what: Three test-only places that read `/proc` now fall back to `ps` on macOS (`alive`, `wait_quiet`, the fake agent command line). No product code changed. Limits item 324 records that product code still reads `/proc` and is unverified on macOS.
tests: see the pull request
