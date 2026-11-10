# Testing

## Purpose

Every layer is tested before the next starts, with the standard library `unittest`, real child processes in temporary folders, and planted faults and mutation checks that prove the tests fail when the code is wrong.

## Current state

Run every test:

```
python -m unittest discover -s tests -t .
```

- CI (`.github/workflows/ci.yml`) runs the same command on every pull request, on Python 3.10, 3.11, 3.12 and 3.13. The counts after each pull request are in [status-log.md](status-log.md).
- Each layer has its own test module (`tests/test_*.py`, `tests/agents/`, `tests/adapters/`, `tests/budget/`).
- Tests that start umwayi run `python -m umwayi ...` as a real child process with `HOME` (and where it matters `XDG_CONFIG_HOME` and `TMPDIR`) in a temporary folder. The agents are fakes put first on `PATH`: a fake `claude` (also the fake telemetry sender), a fake `kiro-cli`, a fake `node` with a scripted ACP agent. No real agent, systemd, network or account is used.
- `tests/test_system.py` runs the umwayi command as real processes in a fresh folder: one scripted run of every layer, and fault tests (logbook edits, broken rules, bad config, injected crashes, corrupt state files, unknown actions, no network import, no approver code path).
- `tests/test_docs.py` checks the docs: every relative link resolves, the README is at most 120 lines, no em dash, every component doc has its four parts and is under 300 lines.
- Mutation checks: for each layer, faults are put into the code on purpose and the tests must fail. The results are listed in each layer's pull request.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-10 | S-Q1, S-Q2, S-Q15: the whole-system test runs in the normal suite; one ordered owner's day, then each fault in its own copy; a defect it finds is fixed in its pull request, test first | Approved in PR 34. |
| 2026-11-08 | CI runs on Python 3.10, 3.11, 3.12 and 3.13 (H.1) | Hardening, PR 9. |

## Open questions

- S.1, the whole-system test, is not built yet ([tasks.md](../.kiro/specs/umwayi-os/tasks.md), S.1).
