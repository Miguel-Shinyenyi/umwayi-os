section: Test support without /proc
title: product code still reads /proc and is unverified on macOS; the tests no longer need it
number: 324

- Three test helpers used to read `/proc` and now fall back to `ps` where `/proc` is missing: `alive` in `tests/agents/support.py`, `wait_quiet` in `tests/whole_system_support.py`, and the fake agent in `tests/agents/fake_agent.py`. Where `/proc` exists (Linux) they read it exactly as before.
- Product code still reads `/proc` and is Linux only: `umwayi/agents.py` (descendant scan), `umwayi/logbook.py` (the writer's start time, `unknown` without it) and `umwayi/goal.py` (`_pid_alive` and the lock holder). What these do on macOS is not verified. Items 48 and 302 describe the effect.
- Other tests also read `/proc` and are not changed: `tests/test_scan_receiver.py`, `tests/serve/*`, `tests/adapters/test_opencode_plugin.py`, `tests/goal/wholesupport.py`.
