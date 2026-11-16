# Operations (W71): design note

## Purpose

umwayi-os runs by itself: its supervisor starts helpers, waits and records. So the supervisor and the owner need to see what runs, and to protect the machine and the record when something goes wrong. This note designs six parts: a process table, quotas beyond the budget, backup and restore, file format versions and migration, crash recovery and log rotation. For each it says what exists today (with the code), the proposal, the exit codes, the tests, what it cannot do and the open questions. It is a design note only. Nothing here is built, and no code, rule, steering file, safety check or workflow changes with it.

## Current state

Nothing of W71 is built. The facts below were read at main `6525606`. Where a fact is read from code and was not run, it says so.

### 1. A process table: `umwayi ps`

**Today.**
- `umwayi goal status [G]` already prints, per task: the state, the last real event and its age, `Supervisor: alive` or `lost` (from the goal lock), the child's pid as `running (pid is alive)` or `not running`, and `Spent: N of M UU` (`umwayi/goal.py`, around `_pid_alive` and the status lines).
- `umwayi budget status` prints the limits, used, reserved and left (`umwayi/cli.py`, `bgsub` `status`). `umwayi kill status` prints the switch.
- `_pid_alive` reads `/proc/PID/stat`. On a system without `/proc`, such as macOS, it returns False, so a live child would show `not running`. This is read from the code; it was not run on a Mac.
- There is no single view across goals, and no command lists the processes umwayi started.

**Proposal.** `umwayi ps`, read only. One line per process umwayi knows it started, from the `started` events of every running task: goal, task, role, agent, pid, state, the age of the last real event, UU spent and cap. Then one line each for the goal lock (held or free), the run lock, the serve lock and the kill switch. The pid check reads `/proc` where it exists. Elsewhere it says `pid unknown`, never `not running`. It never sends a signal and never takes a lock. A lock is probed the way `goalstate.lock_free` does.

**Exit codes.** 0 printed, and nothing needs the owner. 3 something needs the owner: a task in `needs owner`, a lost supervisor, a pid that is alive for a task that is no longer `running`, the kill switch on or unreadable. 2 an unreadable state file or an unexpected error. 64 usage.

**Tests.** A fake root with a running task and a real child process (alive line), the same after the child ends (`not running`), a lost supervisor (exit 3), `/proc` hidden by a stub (`pid unknown`, never `not running`), a snapshot of the root around the command (no byte written), and a source scan (no `kill`, no lock taken).

**Cannot do.** It sees only processes umwayi started and recorded. A pid can be reused by another program after the child ends, so "alive" is a hint, not proof.

### 2. Quotas beyond the budget: time, disk, processes

**Today.**
- *Time.* Each agent has `timeout_minutes` (default 30, `umwayi/agents.py` `DEFAULT_TIMEOUT_MINUTES`). `goal approve` refuses a builder whose timeout is under 1.5 times the largest task (`umwayi/goal.py`). The stall rule stops a run after 1800 s without progress (`umwayi/goalwatch.py` `STALL_SECONDS`). Approval waits are capped at 168 hours (`MAX_HOURS`).
- *Disk.* At most eight worktrees (`umwayi/goalgit.py` `MAX_WORKTREES`). An event log is capped at 8 MiB (`umwayi/goallog.py` `MAX_LOG`); a write past it fails, and a failed write stops the task (W9.R13). Goal and task files are capped at 8 KiB and 64 KiB (`goalstate.py`), and a git output at 1,000,000 bytes (`goalgit.OUTPUT_CAP`). `LOGBOOK.md` has no size cap. Nothing checks free disk space: `shutil.disk_usage` is not used in `umwayi/`.
- *Processes.* One supervisor at a time (the goal lock `.umwayi/goal.lock`), one helper child per task, one server per root (`.umwayi/serve.lock`). `resource` and `RLIMIT` are not used.

**Proposal.** Three limits in `umwayi.json` under `"limits"`, each checked before a start, and none ever raised by umwayi:
- `goal_hours`: the most wall-clock hours one goal may run from its approval (1 to 168, default 24). Past it, the next start is refused and the goal waits for the owner.
- `min_free_mb`: the free space that must stay on the disk of the root (default 1024), read with `shutil.disk_usage` before every start and every 30 seconds in the watch. Below it: no start, and a running helper is stopped as for a failed log write.
- `max_children`: the most processes in a helper's process group, counted from `/proc` once a second where it exists (default 64). Over it: the helper is stopped. Without `/proc` the count is `unknown`, and the owner is told once.

**Exit codes.** These are refusals inside existing commands: `goal run` gives 3 for a quota that needs the owner, 2 for a stopped task, as now. A bad value in `umwayi.json` is 64.

**Tests.** For each limit: a value out of range (64), a start refused at the limit, a stub for `disk_usage` under the floor, a fake helper that starts 65 children, and a test that no code path raises a limit.

**Cannot do.** A process that leaves its group (`setsid`) is not counted. Free space can fall between two looks. `RLIMIT_NPROC` counts every process of the user, not one helper, so it is not proposed.

### 3. Backup and restore of the logbook and the state

**Today.** There is no backup command. `umwayi logbook anchor` prints `COUNT:HEX`, and `verify --anchor` finds a rewritten chain or a cut tail (`docs/logbook.md`). A broken chain must be restored "from a copy you trust (for example git)". The state under `.umwayi/goals/` is ignored by git (`.gitignore`), so git holds no copy of it. `umwayi archive move` moves text out of a file. It is not a backup.

**Proposal.**
- `umwayi backup create --out DIR`. It holds the goal lock and the logbook lock, and refuses while a task is `running`. It copies `LOGBOOK.md`, `.umwayi/logbook.sha256`, `.umwayi/goals/`, `queue.md`, `rules.yaml`, `umwayi.json`, `agents.yaml`, `units.yaml` and `autonomy.yaml` (each only if it exists) into a new folder (0700), with a `manifest.json` of path, size and SHA-256 and the logbook anchor. It never copies `.umwayi/serve.token`, `memory/` or a path under `private_paths`. It appends one entry: the count, the total bytes and the manifest hash.
- `umwayi backup verify DIR`, read only: every hash, and the logbook chain against the anchor in the manifest.
- `umwayi backup restore DIR`, an owner command at a terminal with a typed `yes`, only while the kill switch is on. The current files are moved aside to `.umwayi/restore-old-DATE/`, never deleted. After the copy, `logbook verify` must pass, or everything is moved back. Then it appends one entry naming the manifest hash. A restore of an older logbook drops the later entries: an anchor kept elsewhere shows this as a cut tail, which is the truth.

**Exit codes.** `create`: 0 written, 2 refused (a task running, a lock held, a write that failed; nothing left behind), 3 the kill switch on, 64 usage (an `--out` that exists or is inside the root). `verify`: 0 every hash and the chain match, 2 a mismatch, 64 usage. `restore`: 0 restored, 2 refused or put back, 3 the kill switch off (the restore needs it on), 64 usage.

**Tests.** A round trip (create, change everything, restore, byte for byte equal), a flipped byte found by `verify`, a planted secret in `serve.token` and in a private path that is in no copied byte, `create` refused while a task runs, and a restore that fails half way is put back.

**Cannot do.** A backup on the same disk does not survive the disk. umwayi never copies anywhere off the machine, and never sends a backup over the network.

### 4. File format versions and migration

**Today.** `docs/what-it-is.md` (not the README) says: "Interfaces and file formats can change." The files that carry a version are `goal.json` and `T-NN.json` (`"version": 1`, and the readers refuse any other, `goalstate.py`), `units.yaml` (`version: 1`), `autonomy.yaml` and `tools/generated_files.json`. These carry none: `LOGBOOK.md`, `queue.md`, `rules.yaml`, `agents.yaml`, `schedule.yaml` and the event logs, whose shape is the version. There is no migration code.

**Proposal.**
- Every format umwayi writes gets a version. The JSON state files have one already. A Markdown or YAML file gets one first line, `format: N`, added only by a migration. A file with no line is version 1.
- A reader that meets a newer version than it knows fails closed: Ask me first (3), nothing changed.
- `umwayi migrate check`, read only: one line per known file, with the version found, the version this umwayi writes, and `ok`, `migrate` or `newer`.
- `umwayi migrate run`, an owner command at a terminal. It first makes a backup (part 3), then rewrites each file through a temporary file, under the locks, with one entry per file (path, from, to, the old and new hash). It never migrates `LOGBOOK.md` entries: old entries stay as written, and the chain covers them.

**Exit codes.** `check`: 0 everything ok, 3 a file needs a migration or is newer, 2 unreadable, 64 usage. `run`: 0 done, 2 refused or put back, 3 the kill switch on, 64 usage.

**Tests.** A file of each kind at version 1 (ok), a newer version (3, nothing changed), a migration that fails half way (put back from the backup), and the logbook bytes unchanged by `run`.

**Cannot do.** Downgrading to an older umwayi is not offered. Files the owner edits by hand can be broken in ways a migration cannot fix.

### 5. Crash recovery after a stop in the middle of a task

**Today.**
- *The logbook.* An interrupted append is finished or dropped from `.umwayi/logbook.pending`. A torn tail is cut only by `umwayi logbook recover --torn-tail` (`umwayi/logbook.py`, `docs/logbook.md`).
- *The locks* are `flock` locks, so a killed process lets go of them.
- *The goal files* are made to agree with the logbook, which wins: `goalstate.repair`.
- *A lost supervisor.* A task left `running` while no supervisor holds the lock is found by the next goal command and set to `stopped` with reason `supervisor` (`goalstate.find_lost`, `mark_lost`, W9.R19.5).
- *The worktree* of a failed or stopped task stays, and the next start stops as `leftover` until the owner removes it (`goalrun`).
- *Read from the code, not run:* the helper child is started with `start_new_session=True` (`goalrun.py`, line 113), and `mark_lost` changes only the state. So after a SIGKILL of the supervisor, the child may keep running in its own session until it ends by itself. Nothing finds or stops it.

**Proposal.**
- When `mark_lost` sets a task `stopped`, it reads the pid of the last `started` event. If that pid is alive (as `umwayi ps` decides) and its `/proc` command line is the `umwayi agent run` the supervisor started, it sends SIGTERM to its group, waits ten seconds, then sends SIGKILL, and logs the pid and the result.
- Without `/proc`, it sends nothing and reports `pid unknown` to the owner, because a reused pid could belong to another program.
- The task stays `stopped`. Starting it again needs W9.14 retry, or the gated restart of W65.

**Exit codes.** No new command: the goal commands keep theirs, and `umwayi ps` shows the result.

**Tests.** A supervisor killed with SIGKILL while a fake helper runs: the next `goal status` finds the task lost, the child is stopped, and the entry names the pid. A reused pid with another command line is never signalled. Without `/proc`, nothing is signalled.

**Cannot do.** A child that left its group, or a grandchild that started its own session, is not found. Work the helper did not commit is lost with it.

### 6. Log rotation

**Today.** `LOGBOOK.md` is append only and is re-read and hashed on every append. KNOWN-LIMITS item 4 says it will slow down over time, and it was not measured. The chain is recomputed from its start on every append (`docs/logbook.md`). An event log stops its task at 8 MiB rather than rotate. Nothing rotates anything.

**Proposal.**
- `umwayi logbook rotate`, an owner command at a terminal, only with an intact chain and no task running.
- It closes the current file as `logbook/LOGBOOK-YYYY-MM.md` (read only, 0400), with its anchor and SHA-256 in `logbook/index.json`. Then it starts a new `LOGBOOK.md` whose first entry is a seal naming the old file's anchor, so the chain continues across files.
- `logbook verify --all` checks every closed file against the index, and the links between them.
- Event logs are not rotated. A task that reaches 8 MiB stops, as now, because a log that large means something is wrong.

**Exit codes.** `rotate`: 0 done, 2 refused (a broken chain, a task running, a write that failed; nothing changed), 3 the kill switch on, 64 usage. `verify --all`: as `verify` today, 0 or 1. This is the one place a 1 already exists (`docs/exit-codes.md`), and it is not changed here.

**Tests.** Rotate, then append: the new file's first entry names the old anchor, `verify --all` is ok, a flipped byte in a closed file is found, and a removed closed file is found.

**Cannot do.** A closed file still has to be kept by the owner, and deleting one breaks `verify --all`, by design. Rotation does not make one append faster until the current file is small again.

### What all six never do

No network, no shell, no install. They never raise a budget, a cap or a quota. They never start a helper, open or merge a pull request, or create a goal. They never delete an old file: what they replace is moved aside.

### Spec lines it would add

`### W71.R1` to `### W71.R6`, one per part above, each with its command, its exit codes and its tests. They would change three lines: W9.R19.5 (stop the orphaned child as in part 5), W9.R10 (the three quotas of part 2 are checked in the watch), and the logbook spec (rotation keeps one chain across files).

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-16 | Design note only: six parts, each read only first; every command that changes something is an owner command at a terminal, and nothing is deleted | W71, the owner's task of Nov 16. |

## Open questions

1. **`umwayi ps` or a line in `goal status`.** Recommendation: a separate `umwayi ps`. It spans goals and locks, while `goal status` stays one goal's story.
2. **The quota defaults** (24 hours, 1024 MB, 64 processes). Recommendation: start there. They are guesses; nothing in the repo measures them.
3. **Stop an orphaned helper.** Recommendation: yes, only with a matching `/proc` command line. This is the one place where a recovery would signal a process, so it needs the owner's word.
4. **Where backups go.** Recommendation: a folder the owner names outside the root, never a default inside it, so a deleted root does not take its backup with it.
5. **`format: N` lines in owner files.** Recommendation: only when the first migration of that file is needed, not now. Adding a line to `rules.yaml` changes the rules file's bytes and its logged hash.
6. **Rotation by month or by size.** Recommendation: by month, by the owner's command. Measure first how slow an append is at 10,000 entries, the measurement KNOWN-LIMITS item 4 says was not made.
7. **The macOS pid check.** Recommendation: a small task to make `_pid_alive` say `unknown` without `/proc`, before `ps` is built, and the owner's check on a Mac.
