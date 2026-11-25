date: 2026-11-25
pr: none
what: W36, tests only. `wait_root_quiet` of the agent tests listed `/proc` with no fallback, so five agent tests errored on a Mac with `FileNotFoundError: /proc`. It now uses a `command_lines` helper that reads `/proc` where there is one and `ps` where there is none, the same as `tests/whole_system_support.py`. No code of umwayi changes.
tests: `tests/agents/test_proc_fallback.py` (the `ps` path listing this process with `/proc` hidden, and the `/proc` path); the agent tests that call `wait_root_quiet`.
