# Testing

## Purpose

Every layer is tested before the next starts, with the standard library `unittest`, real child processes in temporary folders, and planted faults and mutation checks that prove the tests fail when the code is wrong.

## Current state

Run every test:

```
python -m unittest discover -s tests -t .
```

- CI (`.github/workflows/ci.yml`, W20) runs on every pull request and on every push to main. The counts after each pull request are in [status-log.md](status-log.md). It is described in [CI since W20](#ci-since-w20) below.
- Each layer has its own test module (`tests/test_*.py`, `tests/agents/`, `tests/adapters/`, `tests/budget/`).
- Tests that start umwayi run `python -m umwayi ...` as a real child process with `HOME` (and where it matters `XDG_CONFIG_HOME` and `TMPDIR`) in a temporary folder. The agents are fakes put first on `PATH`: a fake `claude` (also the fake telemetry sender), a fake `kiro-cli`, a fake `node` with a scripted ACP agent. No real agent, systemd, network or account is used.
- `tests/test_ui_package.py` (layer 12, UI.1) checks the `ui/` package, its lockfile, `ui/dist/build.json` and the built page without npm, node or a browser, with a planted fault for each rule. The page's own logic (the engine, the layout and position function, the stations, the home content, the detail mode) is tested by `node --test` inside `ui/` (no package needed), and the look and the behaviour in a browser by a hand pass whose results are in [interface.md](interface.md).
- `tests/serve/` (the local backend, W6.1 to W6.6; [serve.md](serve.md)) is standard library only and needs no network beyond 127.0.0.1. `gen.py` has the seeded generators (only `getrandbits` and `random()`, so a seed means the same on Python 3.10 to 3.13), the golden request of each route, the catalogue of named faults and the shrinker; `oracle.py` is a second, naive implementation of the gate written from the text; `test_gate_properties.py` runs `UMWAYI_PROP_N` cases (default 5000) for each of three fixed seeds and one seed drawn per run (printed), and prints the seed, the case and the smallest request found on a failure; `test_wire.py` starts real servers (`UMWAYI_FUZZ_N`, default 5000, sets the size of the fuzz); `test_samecode.py` runs 41 scenarios through the command line and through a request on identical roots and compares the bytes; `test_token.py`, `test_entries.py` and `test_failclosed.py` cover the token, the entries and each row of the fail closed table. The tests of the test tools (`test_gen.py`) pass without the server.
- `tests/budget/test_run_golden.py` and `tests/budget/test_run_options.py` (W9.6, `agent run --cap-uu --model --effort`) run `agent run` as real child processes with the fake `claude` and `kiro-cli`. The golden file `tests/budget/golden/agent_run.json` was written on the code before the options existed and holds the argument lists, the logbook entries (the folders, date and run id replaced), the output and the exit codes of a clean run, the kill switch before and during a run, a stop by the per-run cap and a refusal by the day cap, for both platforms; it must not change. The options test has the new argument lists, every value that is 64, the allow-list, the reservation and the stop at the cap, the day limits against the cap, and the refusal for a platform whose cost is not watched.
- `tests/goal/test_docs_parts.py` (W9.9, the docs builder; standard library, the system `git` for two merge tests) has the strict reader with a table of bad parts, the byte for byte first build on copies of the two real files, numbering, `check`, 60 seeded random sets built in two orders, two branches that add only parts and merge in git without a conflict (and the control that edit the shared file and do), and planted faults: a number written twice, an order that depends on the file system, a part that overwrites the base, a bad part skipped silently, a migration that loses a byte, a base with one changed byte. `tests/test_exit_codes.py` lists `goal docs build` and `check`.
- `tests/goal/test_worktree_golden.py` and `tests/goal/test_worktree.py` (W9.6b, the worktree per task, `agent run --workdir` and `agent check --workdir`; the system `git` in temporary folders, skipped when it is missing or older than 2.17, and the fake `claude` and `kiro-cli` as real child processes) hold the goldens of `agent check` and `agent run` without the option, written on the old code in a separate commit and never changed (output, exit codes, argument lists, working folders, entries, both platforms), and one group per point of W9.R8.1 and W9.R8.9 to W9.R8.16: the 18 lists and the guard that no other list, no forbidden word and no force flag exists, the owner's copy byte for byte unchanged, `stale`, every refusal of a path as exit 64 with nothing started, the path property tests, `leftover`, `dirty` and the cap of eight, cleanup only after `merged`, no sharing over random sequences across three goals, the plan's worktree, and only tracked files in a worktree. Every group has planted faults (a replaced function) that its own check must catch.
- `tests/goal/test_goalrun.py` (W9.7, the supervisor `umwayi/goalrun.py`; standard library, the system `git`, `tests/goal/runsupport.py` and the fake agent of `tests/goal/fake_agent.py`) starts real child processes: the fake agent is a program that reads its prompt and its nonce on standard input, writes files, commits with `git`, prints errors and result lines, ignores SIGTERM or goes silent, and the supervisor starts it through its spawn seam in the worktree its argument list names. The clock is fake and a one-second tick of the watch is a few milliseconds. It checks the start steps in order (spies), every refusal, the five kinds of leftover and `stale`, the caps and the ledger window, the scope check and each way a builder, tester or guide ends, the stall and loop stops (the child is gone, also when it ignores SIGTERM), the kill switch and signals, every failed write, the merge observation and cleanup, the planning run, `supervise` and code guards (one child start, no shell, no network, no git word that writes). Each pitfall of the design table has a planted fault that its check must catch. The test double for git there is not the real worktree half (`umwayi/goalgit.py`, tested in `tests/goal/test_worktree.py`).
- `tests/goal/test_cli.py`, `test_owner_commands.py`, `test_status.py` and `test_report.py` (W9.8, the goal commands `umwayi/goal.py`; `tests/goal/cmdsupport.py`) call each command as a function with a fake terminal, the fake agent as a real child process and the system `git`, and a few run `python -m umwayi goal ...` as a real child process, which has no terminal. They check every exit code of W9.R3.2, that the guard comes first, every refusal of `approve` with nothing changed, the owner commands without a terminal (exit 2, a byte snapshot of the root and the worktree root), `stop` reaching a running supervisor, the status text (a golden of five goals in every state, `tests/goal/golden/status.txt`, rewritten with `UMWAYI_UPDATE_GOLDEN=1`) and the report. The planted faults of W9.R11.7 (a status from the process only, a poll counted as real, a future time shown as fresh, a helper's text in a line) each make a check fail.
- `tests/test_site_package.py` (layer 12, UI.6) checks the `site/` package the same way, with a planted fault for each rule: exact versions, a sha512 lockfile, no analytics or tracking package, no remote font or script or image, no request call or storage, no copy of `ui/src` (the site reaches the scene through the shared modules), the headers and the telemetry switch, and nothing of Vercel. The site's own Node tests (`node --test` inside `site/`, with React only) render the home text and the list the way the server does and read the headers and the client source; the pass in a browser, with every request logged, is by hand and in [interface.md](interface.md).
- `tests/test_ui_package.py` also checks the snapshot reader on the built page (UI.3): one json file picker and no other input or form, the one refusal message once, `readAsText` only, none of the calls that set text as markup or code, sample before a file, the picker hidden without a script. `tests/test_view.py` `FixtureTests` checks that `ui/test/fixtures/snapshot.json` is the command's output on the fixed root byte for byte.
- `ui/test/access.test.mjs`, the six UI.5 tests of `ui/test/contrast.test.mjs` and `ui/test/faults.test.mjs` (UI.5) check the built page's names, landmarks, heading order, Tab order, live regions and target sizes, every text colour against every ground the CSS puts it on (normal and Calm mode), the phone layout of the panels, and that each planted fault of 12.R10.6 has a test that exists. A mutation pass (28 mutants, 28 killed) is run by a script kept outside the repo with the page rebuilt for each one; its counts are in `docs/interface.md`.
- `tests/test_quickstart.py` (W25) keeps `docs/quickstart.md` true: every code block has a tag; each line of an `umwayi` block starts with `umwayi` or `python -m umwayi` and must parse against the real parser (`umwayi.cli.build_parser`), and a usage error fails the test; the few non umwayi lines of a `setup` block must start with a listed word and may not chain or pipe; the rules block loads with the real rules parser on top of the repo `rules.yaml`; planted faults (a command or option that does not exist, a line that is not umwayi, a setup line that chains, an untagged or unclosed block) must each be found. It proves that the commands parse, not that their output is what the page shows.
- `tests/test_checks.py` (UI.4) reads `ui/src/data/checks.js` as text and finds every step text, code block, command and "what to record" cell word for word in its NOTES file, and every check id in tasks.md, with a planted fault for each. `tests/test_ui_package.py` also checks the owner checks panel on the built page (hidden until opened, the notice, the read only notes box, the closing line, no storage, cookie or Blob).
- `tests/test_view.py` (UI.2) runs `umwayi view snapshot` as real child processes in a temporary root whose own name, files and logbook hold sentinel words and a fake secret that must never reach the snapshot, the output or the logbook entry. A structural test checks every JSON leaf (a whole number, a boolean, null, or one of the three kill switch words or a real date, at the places the schema allows), the broken logbook is refused four ways with nothing written, each unreadable part is null alone, and the `--out` cases (outside the root, `..`, links, a hard link, a folder, a foreign file, a FIFO, a newline, too long) are refused with 64 and change nothing. Code guards check that `view.py` imports no process or network module. Its planted faults are in the [interface doc](interface.md).
- `ui/test/stepdown.test.mjs` (UI.8) tests the High step down in three layers: the pure window of `ui/src/engine/detail.js` (a slow window leaves High, a fast run, too few frames and bad numbers do not, and the watch reports once), the frame reader `frameNotes` of `ui/src/engine/stage.js` driven with a fake stage (no WebGL), and `ui/src/boot.js` with a fake page: one notice, no second one, no return to High by itself, a new step down after the visitor chooses High again. Planted faults (a threshold changed, no notice, a watch that never ends) were each caught by hand.
- `tests/test_reopen.py` (L13.2) runs `umwayi decision reopen` and `queue answer --revisit-if` as real child processes on a root built once through the real commands and copied for each test. Its planted faults are a reopen of a missing entry (an unknown hash, a hash of the wrong length or case, a hash of a check, seal or older closing entry, an id that does not exist, a task, an open decision, an unchained entry, a chain not started) and a broken chain (an edited or deleted chained entry with the record rewritten, a changed record, a torn tail, a cut tail), each refused with nothing changed (a byte snapshot of the root). The happy path checks that the logbook before is a byte prefix of the logbook after, that exactly one entry was added in the fixed shape with the full hash, that the old row is the same bytes, and that the chain (recomputed in the test) and an anchor taken before still verify. Two reopens at once, a crash in the queue commit and the guard rules of the three adapters are tested too.
- `tests/test_rulelog.py` and `tests/test_petition.py` (L13.3, with `tests/courts_support.py`) run `umwayi check`, `umwayi run` and `umwayi petition` as real child processes. The rules change log is checked by the order of the entries in `LOGBOOK.md` (the rules entry before the check that uses it), the exact entry shapes, the 200 rule cap, four checks at once, and the fallback when the entry cannot be written (the lock held, a broken chain, a hand edit, a known error, a crash). The petition spam (200 petitions from one helper, then 60 helper names) is the planted fault: the counts stop exactly at the limits, every refusal writes nothing, and `rules.yaml` and the answers of a fixed list of actions stay the same. The mutation checks of the slice (27, all killed) are listed in its pull request.
- `tests/autonomy/` (L13.5) runs graded autonomy as real child processes: the worked example of the design to the per mille and 200 fixed score tuples (`test_score.py`), every row of the fail closed table and every gate (`test_gates.py`), the record and five kinds of forged input (`test_inputs.py`), off by default byte for byte, `autonomy.yaml`, its change log and `validate` (`test_off.py`), `status` (`test_status.py`), the text blind test with sentinel and instruction text in every other place (`test_text_blind.py`), and the adapters' guard names (`test_guards.py`). The owner's record is written through `umwayi.autonomy.record`, many outcomes in one child process; the forged inputs are written by hand on purpose.
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
- `tests/test_frontier_practices.py` (W10) reads the table of [frontier-practices.md](frontier-practices.md) and fails on a missing or repeated row, a state outside the four, an evidence file that is not there or a guidance id that is not in `guidance.yaml`. It checks form and that evidence exists, never that a state is true; planted faults prove each failure.
- Problems found while building, and what to do next time: [kiro-issues-log.md](kiro-issues-log.md).
- Mutation checks: for each layer, faults are put into the code on purpose and the tests must fail. The results are listed in each layer's pull request.

### CI since W20

CI.1 (PR 59) made one run per push and cancelled older runs. W20 makes the wait shorter without dropping a test: it runs only the jobs a change can affect, and it splits the Python suite into three shards per version.

- **Four jobs.** `plan` (always runs) reads the diff and decides. `test` is the Python suite, one job per Python version and shard. `node` is the Node tests of `ui/` and `site/`. `result` (always runs, after the others) is the one check to require.
- **The decider** is `python -m tools.ci_plan` ([tools/ci_plan.py](../tools/ci_plan.py)). Its rules: a push to main runs everything on 3.10 to 3.13, and a pull request runs 3.10 and 3.13 only, whatever it changes (W24, below); an empty or unreadable diff, a path it does not know, a path that is not a plain relative path, and any change under `.github/` or `tools/` (the workflow, the decider, the map, the shards) run everything. Otherwise each changed path follows the longest matching route in [tools/ci_map.json](../tools/ci_map.json) (table below). Which files run still follows the map (a full plan runs every file, a partial one only the files that read the change), but since W24 the versions no longer depend on the change: a pull request never runs Python 3.11 or 3.12, and a push to main always runs all four, so those two run only after the merge. This is decided only in the plan step (`ALL_VERSIONS` and `REDUCED_VERSIONS` in `tools/ci_plan.py`); `.github/workflows/ci.yml` names no version, so the matrix, the jobs and the check of `result` cannot disagree. `result` also refuses a plan whose versions do not match its event (a pull request must have 3.10 and 3.13, a push all four) and a matrix with a cell missing, in addition to a shard that failed, did not run or has no report.
- **The shards** are listed in [tools/ci_shards.json](../tools/ci_shards.json): every test file in exactly one of three shards, balanced by seconds measured on Python 3.11 (about 603 s each in the sandbox, against 1810 s of test time in one job). `python -m tools.ci_shards balance --times FILE --out tools/ci_shards.json` rewrites it deterministically; a new test file must be added to it, or `result` fails ("in no shard"). Each shard runs its files through the same loader as `unittest discover`, records which test ids it found and which really started, and writes a report.
- **The final check** (`python -m tools.ci_shards verify`) fails when the plan job failed, when a planned job was skipped, cancelled or failed, when a shard has no report, when a shard reports a test that did not start, when the shards disagree about which tests exist, when a test file is in no shard, and when the tests the shards ran are not all the tests found in the files the plan selected. A shard that silently drops a test is a failure: `tests/test_ci_shards.py` plants a test that never starts and a test file in no shard, and both fail.
- **A skipped job is never a pass.** When the plan leaves something out, the `result` summary lists it under NOT RUN, with the reason. What was left out runs on main after the merge, not on the pull request.
- **Check names.** Before: `tests / test (3.10) (pull_request)`, `tests / test (3.11) (pull_request)`, `tests / test (3.12) (pull_request)`, `tests / test (3.13) (pull_request)`. After, on a pull request: `tests / plan (pull_request)`, `tests / test (V, shard K/3) (pull_request)` for V in 3.10 and 3.13 (since W24; on main V is 3.10 to 3.13) and K in 1 to 3 (fewer when the plan selects fewer; none is created for a skipped part), `tests / node (pull_request)` (only when planned) and `tests / result (pull_request)`. The same names with `(push)` appear on main. Require only `tests / result (pull_request)`: it is always created and it fails for every reason above. The four old names no longer exist, so a branch rule that requires them waits forever until the owner changes it by hand.
- **Node.** The Node tests are their own job now (no longer a step of the 3.12 job), with the same npm download cache and the same `npm ci --ignore-scripts` then `node --test` in `ui/` and `site/`. The node job sets `UMWAYI_REQUIRE_BROWSER=1` (CI.2), so a runner without Chrome fails the phone tests instead of skipping them.
- **Not verified locally.** A workflow cannot run here. `tests/test_ci_workflow.py` pins its text; the real run on GitHub is the record.

### Run only the affected tests (sessions and laptops)

`python tools/affected_tests.py` reads what differs from `origin/main` (commits, uncommitted edits, files git does not track) and asks the same function as the CI decider (`ci_plan.build_plan`) with the same map. `tests/test_affected_tests.py` proves it prints the same plan for the same changed files.

```
python tools/affected_tests.py                      what is affected
python tools/affected_tests.py --run                run those tests (Python tests, then the Node folders)
python tools/affected_tests.py --run --python python3.10 --python python3.13
```

While building, run the affected tests. Before every push, run them on each Python version you can install. Run the whole suite only when the command prints `FULL SUITE` (a workflow, map, filter, shard or unknown-path change, or a diff it cannot read) or when asked. GitHub CI stays the record. What an affected-only run can miss: a test that reads a path the scanner cannot see (see below); a change in `umwayi/`, `tests/` or `adapters/`, which selects the whole Python suite because the map cannot say which module a change reaches (use `python -m unittest tests.test_x` for the inner loop); a base that is out of date (merge the newest `origin/main` first); the Python versions you did not run; and the Node tests when `node` or the packages are not installed (the command then fails, it does not skip). The builder rules that tell every session this are in [.kiro/steering/builder-workflow.md](../.kiro/steering/builder-workflow.md).

### Merging main

Sessions run in parallel, and several files are written by commands, so a plain `git merge origin/main` stops on conflicts nobody can judge by eye. `python -m tools.merge_main` ([tools/merge_main.py](../tools/merge_main.py), standard library only) merges and repairs them. A session uses it instead of a raw merge, before every push and whenever main moves.

What it does, in order:

1. Refuses a tree with any change, an unfinished merge or a detached head (exit 3, nothing changed).
2. `git fetch origin`, then `git merge --no-commit --no-ff origin/main`. Nothing is committed until everything below has passed.
3. Reads the list of generated files, [tools/generated_files.json](../tools/generated_files.json), from the merged tree.
4. No conflict: runs every verify of the list, regenerates a file that is stale, makes the merge commit, and commits the regenerated files as a second commit named `regenerate generated files after merging main`.
5. Conflicts only in listed files: takes main's version of each, runs the regenerate commands in file order, runs every verify, and makes one merge commit. `docs/testing.md` is only generated between two marker lines, so the two sides are merged around the block and a conflict outside the block counts as a conflict in a file that is not listed.
6. A conflict in any file that is not listed: `git merge --abort`, the paths are printed, exit 3 (`Ask me first`). Nothing is changed.
7. One line per file: `kept` (verify passed), `regenerated` (and what ran) or `refused` (and why).

The generated list, in the order the commands run (a file that feeds another comes first):

| file | regenerate | verify |
| --- | --- | --- |
| `docs/status-log.md`, `docs/KNOWN-LIMITS.md` | `python -m umwayi goal docs build` | `python -m umwayi goal docs check` |
| `tools/ci_map.json` | `python -m tools.ci_map update` | `python -m tools.ci_map check` |
| `tools/ci_shards.json` | `python -m tools.ci_shards assign-missing` | `python -m tools.ci_shards check` |
| the table block of `docs/testing.md` | `python -m tools.ci_map table --write` | `python -m tools.ci_map table --check` |
| `ui/dist/build.json` | `npm ci --ignore-scripts` then `node build.mjs`, both in `ui/` | `python -m unittest tests.test_ui_package` |

The progress page `ui/dist/progress.html` is not on the list: since W22 it is built by the same `node build.mjs` and is not committed (it is in `.gitignore`), so it cannot be stale and cannot conflict.

An entry may also list `writes` (other paths its command may write, such as the part files the docs build numbers). A command that changes any other file is a failure. The reader of the list is strict: an unknown key, a repeated path, a path that is not a plain relative path, a missing file or a command that starts a shell is exit 64. A test that fails because a generated file is stale ends its message with the exact command from the list (`tools/generated_files.py`).

Exit codes: 0 done (including nothing to do), 2 a regenerate or verify failed or a file outside the list was written (the tree is put back as it was, and the command and the last 20 lines of its output are printed), 3 ask first (a conflict outside the list, a dirty tree, a detached head, or node or npm missing when a ui file needs it; never skipped), 64 usage or a wrong list. Never 1.

What it cannot do:

- It never pushes, never forces and never resets. The only network use is `git fetch`; `npm ci` reads the npm registry or its cache by itself.
- It cannot judge a conflict in a file that is not generated, or in prose around a generated block. That is exit 3.
- `assign-missing` puts a new test file on the lightest shard and does not rebalance, so after a merge the shard file can be less balanced than `balance` would make it. `balance` stays the full rebalance and `merge_main` never runs it.
- A matching verify shows the file is current, not that its content is right.
- The numbers of two limits parts that were both built on separate branches collide; that is why a limits part is left unnumbered until the merge.

### The progress page as a workflow artifact

`.github/workflows/progress-page.yml` (W27) runs on every push to main, and on nothing else. It checks out the repository, runs the W22 build in `ui/` (`npm ci --ignore-scripts`, then `node build.mjs`) and uploads `ui/dist/progress.html` as a workflow artifact named `progress-page`, kept for 30 days. To read the page, open the run on the Actions tab and download the artifact. The workflow fails when the page is not written.

It publishes nothing. There is no Pages step, no deploy step, no secret and no write permission (`contents: read` only), because where the page is published is the owner's decision. The page is not committed (W22) and the workflow does not change the repository. `tests/test_progress_workflow.py` reads the file and fails if it stops triggering on a push to main, if it has a pages or deploy step or a secret or a write permission, or if it stops using the W22 build command. A workflow cannot run here, so that test pins the text and the first run on main is the record.

### What each test reads (the map)

The map is data ([tools/ci_map.json](../tools/ci_map.json)) and a checker: `tests/test_ci_map.py` scans every Python and Node test file and fails when a test reads a path the map does not list for it, when a test file has no entry, or when an entry is for a file that is gone. The scanner sees paths built from the repository root in test code (`REPO / "ui"`, f-strings, `os.path.join`, a root passed to a helper function), imports of `adapters`, and walks of the whole repository (`REPO.rglob`, `git ls-files`: `tests/adapters/test_claude_code.py` and `tests/agents/test_claude_acp_package.py`, which therefore run on every change); for Node, relative imports out of the package and paths named in strings or `join()`. It cannot see a path that a child process reads from its working directory or that is built from data. The starting points of the guide were checked: the five tests that read `ui/` or `site/` are in the table; 43 files import or read `adapters/` (the guide counted 27 that mention it); only 4 read `.kiro/` (the guide counted 10 mentions, the rest are Kiro's own home folder inside temporary roots); `tests/test_docs.py` reads `docs/`, `README.md` and `PROJECT.md`. This table is generated by `python -m tools.ci_map table` and `tests/test_ci_map.py` checks that it is current.


<!-- ci-map:begin (generated by `python -m tools.ci_map table`; tests/test_ci_map.py keeps it true) -->

Python test files that read a path outside `tests/` and `umwayi/` (every other Python test file reads nothing outside its own area: 23 of 129 files):

| test file | reads |
| --- | --- |
| `tests/adapters/test_claude_code.py` | `*`, `adapters` |
| `tests/adapters/test_core_for_adapters.py` | `.kiro` |
| `tests/adapters/test_kiro.py` | `adapters` |
| `tests/adapters/test_opencode_plugin.py` | `adapters` |
| `tests/adapters/test_opencode_rules.py` | `adapters` |
| `tests/adapters/test_stdio.py` | `adapters` |
| `tests/agents/test_agents_acp.py` | `adapters` |
| `tests/agents/test_agents_chain.py` | `adapters` |
| `tests/agents/test_agents_chat.py` | `adapters` |
| `tests/agents/test_agents_claude_acp_chat.py` | `adapters` |
| `tests/agents/test_agents_claude_acp_gate.py` | `adapters` |
| `tests/agents/test_agents_claude_acp_turns.py` | `adapters` |
| `tests/agents/test_agents_claude_login.py` | `adapters` |
| `tests/agents/test_agents_file.py` | `adapters`, `agents.example.yaml` |
| `tests/agents/test_agents_gate.py` | `adapters` |
| `tests/agents/test_agents_kiro_run.py` | `adapters` |
| `tests/agents/test_agents_login.py` | `adapters` |
| `tests/agents/test_agents_opencode_chat.py` | `adapters` |
| `tests/agents/test_agents_opencode_config.py` | `adapters` |
| `tests/agents/test_agents_opencode_faults.py` | `adapters` |
| `tests/agents/test_agents_opencode_file.py` | `adapters` |
| `tests/agents/test_agents_opencode_gate.py` | `adapters` |
| `tests/agents/test_agents_opencode_turns.py` | `adapters` |
| `tests/agents/test_agents_run.py` | `adapters` |
| `tests/agents/test_claude_acp_package.py` | `*`, `adapters` |
| `tests/agents/test_fake_opencode.py` | `adapters` |
| `tests/agents/test_opencode_mutants.py` | `adapters`, `rules.yaml` |
| `tests/autonomy/test_gates.py` | `rules.yaml` |
| `tests/autonomy/test_guards.py` | `adapters`, `rules.yaml` |
| `tests/autonomy/test_inputs.py` | `rules.yaml` |
| `tests/autonomy/test_off.py` | `autonomy.example.yaml`, `rules.yaml` |
| `tests/autonomy/test_status.py` | `rules.yaml` |
| `tests/autonomy/test_text_blind.py` | `rules.yaml` |
| `tests/budget/test_calibrate.py` | `adapters` |
| `tests/budget/test_capture.py` | `adapters` |
| `tests/budget/test_end_to_end.py` | `adapters` |
| `tests/budget/test_ledger.py` | `adapters` |
| `tests/budget/test_limits.py` | `adapters` |
| `tests/budget/test_readings.py` | `adapters` |
| `tests/budget/test_run_golden.py` | `adapters` |
| `tests/budget/test_run_options.py` | `adapters` |
| `tests/budget/test_status.py` | `adapters` |
| `tests/budget/test_telemetry.py` | `adapters` |
| `tests/budget/test_units.py` | `adapters` |
| `tests/goal/test_approvals.py` | `umwayi.json` |
| `tests/goal/test_cli.py` | `umwayi.json` |
| `tests/goal/test_docs_parts.py` | `.gitignore`, `PROJECT.md`, `README.md`, `docs`, `docs-parts` |
| `tests/goal/test_entries.py` | `umwayi.json` |
| `tests/goal/test_failwrite.py` | `umwayi.json` |
| `tests/goal/test_files.py` | `.gitignore`, `umwayi.json` |
| `tests/goal/test_gen.py` | `umwayi.json` |
| `tests/goal/test_goalrun.py` | `umwayi.json` |
| `tests/goal/test_guidance.py` | `.kiro`, `guidance.yaml` |
| `tests/goal/test_guidance_coverage.py` | `.kiro`, `guidance.yaml` |
| `tests/goal/test_owner_commands.py` | `umwayi.json` |
| `tests/goal/test_report.py` | `umwayi.json` |
| `tests/goal/test_status.py` | `umwayi.json` |
| `tests/goal/test_worktree.py` | `adapters`, `umwayi.json` |
| `tests/goal/test_worktree_golden.py` | `adapters` |
| `tests/serve/test_gate_properties.py` | `docs` |
| `tests/serve/test_mutation.py` | `adapters`, `docs`, `ui` |
| `tests/serve/test_samecode.py` | `serve.rules.example.yaml` |
| `tests/serve/test_scenarios.py` | `ui`, `ui/dist` |
| `tests/serve/test_token.py` | `.gitignore`, `adapters`, `rules.yaml` |
| `tests/serve/test_wire.py` | `ui`, `ui/dist` |
| `tests/test_affected_tests.py` | `tools` |
| `tests/test_automation.py` | `jobs.yaml`, `rules.yaml` |
| `tests/test_builder_workflow.py` | `.kiro`, `tools` |
| `tests/test_checks.py` | `.kiro`, `adapters`, `ui` |
| `tests/test_ci_map.py` | `.github`, `docs`, `tools` |
| `tests/test_ci_plan.py` | `tools` |
| `tests/test_ci_shards.py` | `tools` |
| `tests/test_ci_workflow.py` | `.github` |
| `tests/test_cli_map.py` | `ui`, `ui/dist` |
| `tests/test_concerns.py` | `.github`, `jobs.yaml`, `schedule.example.yaml`, `workflows` |
| `tests/test_docs.py` | `.gitignore`, `PROJECT.md`, `README.md`, `docs` |
| `tests/test_feedback.py` | `.github`, `README.md`, `docs` |
| `tests/test_frontier_practices.py` | `.kiro`, `docs`, `guidance.yaml` |
| `tests/test_generated_files.py` | `docs`, `tools` |
| `tests/test_helpers.py` | `rules.yaml` |
| `tests/test_honest.py` | `.kiro`, `adapters`, `docs`, `rules.yaml` |
| `tests/test_logbook_chain.py` | `rules.yaml` |
| `tests/test_merge_main.py` | `.kiro`, `docs`, `docs-parts`, `tools`, `ui` |
| `tests/test_petition.py` | `rules.yaml` |
| `tests/test_progress_page.py` | `.gitignore`, `.kiro`, `docs`, `ui`, `ui/dist` |
| `tests/test_progress_workflow.py` | `.github`, `ui` |
| `tests/test_quickstart.py` | `README.md`, `docs`, `rules.yaml` |
| `tests/test_reopen.py` | `adapters`, `rules.yaml` |
| `tests/test_routing.py` | `.github`, `.kiro`, `docs`, `jobs.yaml`, `schedule.example.yaml`, `workflows` |
| `tests/test_rulelog.py` | `rules.yaml` |
| `tests/test_rules.py` | `rules.yaml` |
| `tests/test_runlock.py` | `rules.yaml` |
| `tests/test_scan_files.py` | `adapters`, `articles`, `rules.yaml`, `workflows` |
| `tests/test_scan_receiver.py` | `adapters` |
| `tests/test_scan_secrets.py` | `adapters`, `articles`, `rules.yaml`, `workflows` |
| `tests/test_schedule.py` | `rules.yaml`, `schedule.example.yaml` |
| `tests/test_site_assets.py` | `adapters`, `site`, `ui`, `ui/dist` |
| `tests/test_site_package.py` | `site`, `ui` |
| `tests/test_stalls.py` | `jobs.yaml`, `schedule.example.yaml`, `workflows` |
| `tests/test_starter_rules.py` | `adapters`, `rules.yaml` |
| `tests/test_system.py` | `articles`, `umwayi.json`, `workflows` |
| `tests/test_ui_package.py` | `.gitignore`, `ui`, `ui/dist` |
| `tests/test_view.py` | `jobs.yaml`, `ui`, `umwayi.json`, `workflows` |
| `tests/test_w21_goldens.py` | `docs`, `tools` |
| `tests/test_whole_system.py` | `adapters`, `articles`, `rules.yaml`, `workflows` |
| `tests/test_workflows.py` | `rules.yaml` |

Node test files that read a path outside their own package (the others read nothing outside it):

| test file | reads |
| --- | --- |
| `site/test/client.test.mjs` | `ui/src`, `ui/src/scene.js`, `ui/src/style.css` |
| `site/test/home.test.mjs` | `ui/dist/index.html`, `ui/src/data/home.js`, `ui/src/index.html`, `ui/src/stations/meta.js` |
| `site/test/phone.test.mjs` | `ui/tools/browser.mjs`, `ui/tools/phone-audit.mjs`, `ui/tools/phone-scenario.mjs` |
| `ui/test/client.test.mjs` | `umwayi/serve.py`, `umwayi/servegate.py` |
| `ui/test/faults.test.mjs` | `site/test/phone.test.mjs`, `tests/test_ui_package.py` |

Which changed path runs which jobs (the longest matching prefix wins; a path matching none runs everything):

| changed path | python tests | node job |
| --- | --- | --- |
| `.github/` | all of them (everything, every version) | yes |
| `.gitignore` | only the files that read it (tables above) | only if a node test reads it |
| `.kiro/` | only the files that read it (tables above) | only if a node test reads it |
| `PROJECT.md` | only the files that read it (tables above) | only if a node test reads it |
| `README.md` | only the files that read it (tables above) | only if a node test reads it |
| `adapters/` | all of them | only if a node test reads it |
| `agents.example.yaml` | all of them | only if a node test reads it |
| `articles/` | all of them | only if a node test reads it |
| `autonomy.example.yaml` | all of them | only if a node test reads it |
| `docs-parts/` | only the files that read it (tables above) | only if a node test reads it |
| `docs/` | only the files that read it (tables above) | only if a node test reads it |
| `goal.rules.example.yaml` | all of them | only if a node test reads it |
| `guidance.yaml` | all of them | only if a node test reads it |
| `jobs.yaml` | all of them | only if a node test reads it |
| `memory/` | all of them | only if a node test reads it |
| `pyproject.toml` | all of them | only if a node test reads it |
| `rules.yaml` | all of them | only if a node test reads it |
| `schedule.example.yaml` | all of them | only if a node test reads it |
| `serve.rules.example.yaml` | all of them | only if a node test reads it |
| `site/` | only the files that read it (tables above) | yes |
| `tests/` | all of them | only if a node test reads it |
| `tools/` | all of them (everything, every version) | yes |
| `ui/` | only the files that read it (tables above) | yes |
| `umwayi.json` | all of them | only if a node test reads it |
| `umwayi/` | all of them | only if a node test reads it |
| `workflows/` | all of them | only if a node test reads it |
| anything else | all of them (everything, every version) | yes |

<!-- ci-map:end -->

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-12 | CI runs only the jobs a change can affect, splits the Python suite into three shards per version, and ends in one always-on `result` check; main always runs everything on 3.10 to 3.13; sessions run `tools/affected_tests.py` | W20 (CI.1.D built, after the owner asked): a filter that cannot prove a change safe runs everything, and the checks to require change to `tests / result (pull_request)`. |
| 2026-11-13 | A pull request runs Python 3.10 and 3.13 only and a push to main runs all four, so 3.11 and 3.12 run only after the merge; the versions are chosen in the plan step, and `result` checks them against the event | W24: one slow shard took 17 minutes and four versions made every pull request wait for the slowest. KNOWN-LIMITS says what is lost. |
| 2026-11-12 | CI runs on pull requests only, and a newer push cancels the older run of the same pull request; the names and the matrix stay; the npm download is cached on the 3.12 job; sharding was a proposal then (built in W20) | CI.1 (the owner's reviewer found two runs per push, no cancelling and 20 to 25 minutes a job), PR 59. It overrules S-Q13, which kept the workflow unchanged for Dec 3. |
| 2026-11-10 | The fault scenarios restore the day's snapshot into the same folder, not a copy elsewhere | S.1, PR 36: the day writes absolute paths (the workdir, the Kiro hook's `--root`, the unit files, logbook entries) that a copy at another path would make false. |
| 2026-11-10 | S-Q1, S-Q2, S-Q15: the whole-system test runs in the normal suite; one ordered owner's day, then each fault in its own copy; a defect it finds is fixed in its pull request, test first | Approved in PR 34. |
| 2026-11-08 | CI runs on Python 3.10, 3.11, 3.12 and 3.13 (H.1) | Hardening, PR 9. |

## Open questions

- The owner's real runs are not part of the whole-system test (S-Q14): 10.21 (a real run of each platform), 10.31, 11.6 and B.10 ([tasks.md](../.kiro/specs/umwayi-os/tasks.md)).
