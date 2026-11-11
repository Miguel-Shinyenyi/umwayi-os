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
- `tests/test_site_package.py` (layer 12, UI.6) checks the `site/` package the same way, with a planted fault for each rule: exact versions, a sha512 lockfile, no analytics or tracking package, no remote font or script or image, no request call or storage, no copy of `ui/src` (the site reaches the scene through the shared modules), the headers and the telemetry switch, and nothing of Vercel. The site's own Node tests (`node --test` inside `site/`, with React only) render the home text and the list the way the server does and read the headers and the client source; the pass in a browser, with every request logged, is by hand and in [interface.md](interface.md).
- `tests/test_view.py` (UI.2) runs `umwayi view snapshot` as real child processes in a temporary root whose own name, files and logbook hold sentinel words and a fake secret that must never reach the snapshot, the output or the logbook entry. A structural test checks every JSON leaf (a whole number, a boolean, null, or one of the three kill switch words or a real date, at the places the schema allows), the broken logbook is refused four ways with nothing written, each unreadable part is null alone, and the `--out` cases (outside the root, `..`, links, a hard link, a folder, a foreign file, a FIFO, a newline, too long) are refused with 64 and change nothing. Code guards check that `view.py` imports no process or network module. Its planted faults are in the [interface doc](interface.md).
- `tests/test_reopen.py` (L13.2) runs `umwayi decision reopen` and `queue answer --revisit-if` as real child processes on a root built once through the real commands and copied for each test. Its planted faults are a reopen of a missing entry (an unknown hash, a hash of the wrong length or case, a hash of a check, seal or older closing entry, an id that does not exist, a task, an open decision, an unchained entry, a chain not started) and a broken chain (an edited or deleted chained entry with the record rewritten, a changed record, a torn tail, a cut tail), each refused with nothing changed (a byte snapshot of the root). The happy path checks that the logbook before is a byte prefix of the logbook after, that exactly one entry was added in the fixed shape with the full hash, that the old row is the same bytes, and that the chain (recomputed in the test) and an anchor taken before still verify. Two reopens at once, a crash in the queue commit and the guard rules of the three adapters are tested too.
- `tests/test_rulelog.py` and `tests/test_petition.py` (L13.3, with `tests/courts_support.py`) run `umwayi check`, `umwayi run` and `umwayi petition` as real child processes. The rules change log is checked by the order of the entries in `LOGBOOK.md` (the rules entry before the check that uses it), the exact entry shapes, the 200 rule cap, four checks at once, and the fallback when the entry cannot be written (the lock held, a broken chain, a hand edit, a known error, a crash). The petition spam (200 petitions from one helper, then 60 helper names) is the planted fault: the counts stop exactly at the limits, every refusal writes nothing, and `rules.yaml` and the answers of a fixed list of actions stay the same. The mutation checks of the slice (27, all killed) are listed in its pull request.
- `tests/test_honest.py` (L13.4) is the words test of layer 13. It searches `docs/corrections.md`, `docs/autonomy.md`, the layer 13 items of KNOWN-LIMITS, the `--help` of every layer 13 command built so far, the captured output and the logbook of a real run of those commands (done, refused and usage errors), and the messages in the layer 13 modules, for the claims of 13.R8.2 (`guarantee`, `foolproof`, `tamper-proof` and the rest). The plain note is taken out by its exact sentence first. It also checks that the note is on both pages in the design's words, that the stop criteria table has exactly the rows of 13.R8.3 and 13.R8.4 with the words each must hold, and that every KNOWN-LIMITS item of the built slices exists once. The scanner is tested against planted words in a copy of each page, in a help text, in a command output and in the logbook, and against the note's own exclusion.
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
- `tests/test_elections.py` (layer 13, slice 1) runs `check`, `run`, `steward` and `rules due` as child processes with the system date set by a `sitecustomize.py` (`UMWAYI_TEST_TODAY`): the day after `review_by`, the last day, the three clocks, bad dates, a golden file of the bytes of a rules file with no `review_by`, the exact output of `rules due`, a snapshot of the root before and after (nothing written), and a code guard on the imports.
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
