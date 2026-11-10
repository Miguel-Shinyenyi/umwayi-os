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
- `tests/test_ui_package.py` (layer 12, UI.1) checks the `ui/` package, its lockfile, `ui/dist/build.json` and the built page without npm, node or a browser, with a planted fault for each rule. The page's own logic (the engine, the layout and position function, the stations, the home content, the detail mode) is tested by `node --test` inside `ui/` (no package needed), and the look and the behaviour in a browser by a hand pass whose results are in [interface.md](interface.md).
- `tests/test_system.py` runs the umwayi command as real processes in a fresh folder: one scripted run of every layer, and fault tests (logbook edits, broken rules, bad config, injected crashes, corrupt state files, unknown actions, no network import, no approver code path).
- `tests/test_whole_system.py` (S.1, with `tests/whole_system_support.py`) drives umwayi the way the owner uses it, every layer in one root. One ordered owner's day (`test_01` to `test_08`: a fresh root, memory, queue and archive, the rules and the hash chain with an anchor, a job and a workflow, the three layer 9 hooks, `agent check`, `run` and `chat` for Claude Code and Kiro over cli and ACP with telemetry, a schedule end to end, the budget and the anchors), then each fault scenario from the day's end state, restored from a snapshot into the same folder so every absolute path the day wrote stays true:
  - `test_20` to `test_23`: a tampered logbook (an old chained entry; a budget settle out of shape; the same settle edited consistently; a truncated tail), each refused or found as its layer says;
  - `test_30`: a lost reservation (umwayi SIGKILLed), counted in full until `budget settle-lost`;
  - `test_40` to `test_46`: the kill switch in the middle of `agent run`, the cli chat and the ACP chat for Claude Code and Kiro, and at a scheduled job's start;
  - `test_50`: a schedule installed, checked, run and removed with no `systemctl` on `PATH`, and with a fake one that records any call;
  - `test_60`: the per-run limit passed in the second turn of an ACP chat;
  - `test_70` to `test_73`: a planted crash in an append, before a reservation, in a settle and in a schedule install.
  After every scenario: `logbook verify`, `budget status`, nothing the scenario started still alive, and only the exit codes each command may give. A day step that fails skips the rest.
- The security scan's tests (S.2): `tests/test_scan_receiver.py` (the telemetry receiver from the agent's side: binding, the run header, sizes, a slow client, 200 connections, the port after every way out), `tests/test_scan_files.py` (modes under umask 022 and 077, links, hard links, races, path arguments, and a guard on every mode change) and `tests/test_scan_secrets.py` (planted secrets in every entry place, and a sweep of every byte umwayi printed or wrote). The tool scans themselves are not tests; their record is [SECURITY-SCAN.md](SECURITY-SCAN.md).
- `tests/test_docs.py` checks the docs: every relative link resolves, the README is at most 120 lines, no em dash, every component doc has its four parts and is under 300 lines.
- Mutation checks: for each layer, faults are put into the code on purpose and the tests must fail. The results are listed in each layer's pull request.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-10 | The fault scenarios restore the day's snapshot into the same folder, not a copy elsewhere | S.1, PR 36: the day writes absolute paths (the workdir, the Kiro hook's `--root`, the unit files, logbook entries) that a copy at another path would make false. |
| 2026-11-10 | S-Q1, S-Q2, S-Q15: the whole-system test runs in the normal suite; one ordered owner's day, then each fault in its own copy; a defect it finds is fixed in its pull request, test first | Approved in PR 34. |
| 2026-11-08 | CI runs on Python 3.10, 3.11, 3.12 and 3.13 (H.1) | Hardening, PR 9. |

## Open questions

- The owner's real runs are not part of the whole-system test (S-Q14): 10.21 (a real run of each platform), 10.31, 11.6 and B.10 ([tasks.md](../.kiro/specs/umwayi-os/tasks.md)).
