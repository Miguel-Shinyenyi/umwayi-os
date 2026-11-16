# The work ledger and stall handling (W65): design note

## Purpose

This note designs how umwayi-os keeps track of its own work when it runs by itself. Its own Claude session is the supervisor, in the guide role under `umwayi goal`, and nothing else is assumed: not the outside guide that helps build umwayi-os today, and not the Kiro web tabs. The note is written for the owner and for that internal supervisor. It adds five pure functions with no judgement: one ledger across goals, the next helper assignment, the next pull request, the branches that lack main, and a fixed clock rule for an idle or stalled helper. It also adds three commands. It is a design note only. Nothing here is built, and no code, rule, steering file, safety check or workflow changes with it.

Product rule: the supervisor (`umwayi/goalrun.py`) starts every helper through `umwayi agent run`. So it owns each helper's process and sees its last event, its state and its exit. umwayi-os is command line based and has no GUI, so the product probes and interrupts a helper only through the helper's own command line (see "The helper's own command line"). What exists only in today's build setup is in the last section, marked temporary; that browser view does not shape the product.

## Current state

Nothing of W65 is built. Read at main `0c6d07e` and on two branches on Nov 16. "Missing" means umwayi has nothing for it; nothing is guessed.

| what | today | where |
| --- | --- | --- |
| task states and goal files | `plan`, `queued`, `running`, `in review`, `merged`, `failed`, `stopped`, `needs owner`, each with fixed reason words; files under `.umwayi/goals/G-0007/` (`goal.json`, `plan.json`, `T-02.json`); the goal lock `.umwayi/goal.lock` | `umwayi/goalstate.py`, `umwayi/goalpacket.py` `REASONS` |
| the event log of a task | `T-02.events.jsonl`, kinds `state`, `started`, `output`, `error`, `fingerprint`, `check_result`, `stopped`, `worktree` and others, each line with `at` (UTC) and a CRC; a total reader that skips bad lines | `umwayi/goallog.py` `KINDS`, `read` |
| the stall and loop judge | pure `judge(history, now, policy)`: a gap of `STALL_SECONDS` = 1800 between progress points is `stalled`, two equal error signatures are `looping`. A builder's progress is a changed tree; a tester's or guide's is any output | `umwayi/goalwatch.py`, `Policy.for_role` |
| what a stall does now | the supervisor stops the child and the task ends `failed` (reason `stalled`, cause `no_progress`). `failed` is terminal, and the goal halts | `goalrun.after_stop`, `goalpacket.CAUSES` |
| retry | not built. W9.14 `umwayi goal retry G T` is an option (3 h) on the tasks list | `.kiro/specs/umwayi-os/tasks.md` |
| budgets | a cap per task and per goal, read from the budget ledger in the logbook, never from a helper | `umwayi/goalbudget.py` |
| the idle line | `goalpacket.idle_line(goal, tasks)` (W60, merged): "Idle: N tasks queued and nothing is running" or "Waiting for you" | `umwayi/goalpacket.py` |
| the backlog | `backlog.md` and `backlog.next_task` (W61), design only, on branch `origin/w61-backlog-design`, `docs/backlog-design.md` | not on main |
| the merge-ready check | `python -m tools.merge_ready PR` (W63), eleven rules, design only, on branch `origin/w63-merge-ready-design`, `docs/merge-ready-design.md` | not on main |
| `umwayi stalls check` | reads a JSON file of events that nothing produces, and nothing runs it on a schedule | `umwayi/stalls.py`, [stalls.md](stalls.md) |
| git reads | 18 fixed argument lists; `is_ancestor` asks whether a tip is on main, not whether a branch contains main; no list reads `refs/remotes/origin/BRANCH` | `umwayi/goalgit.py` |
| network in the core | not allowed: `tests/test_system.py` `test_no_module_imports_a_network_library` | `umwayi/` |
| pull requests | missing. No umwayi file holds a PR number, a branch head on origin or a CI result | |
| more than one helper at a time | missing. One task runs at a time (W9-Q4); W9.12 `--ahead N` is an option | |
| measured task durations | the owner's figure, 8 minutes to 1 h 23 min; I found no record of it in the repo, so its source is unknown | |

## The ledger file

`.umwayi/work/ledger.md` under the umwayi root, beside the work and never inside it, folder 0700 and file 0600. It holds only what umwayi cannot read locally: the delivered head, the PR number and the two check results. Everything else (the state, the helper, the times) comes from the goal files and event logs when the ledger is read. Only `umwayi work record` writes it. The owner may read it, and a hand edit is caught by the parser like any other bad cell.

```
# Work ledger

| task | branch | head | pr | checks | ready | at |
| --- | --- | --- | --- | --- | --- | --- |
| G-0007/T-02 | umwayi/g-0007-t-02 | 3f9c...40 hex | 140 | green | pass | 2026-11-16T10:02:11Z |
| G-0007/T-03 | umwayi/g-0007-t-03 | none | none | unknown | unknown | 2026-11-16T11:40:00Z |
```

Parser rules, strict as `taskqueue.parse` and W61 are. A bad cell makes its row WAITING, with the line number and never the text. A bad header or file makes the whole ledger WAITING. Nothing is guessed, and no cell is read in a second way.

1. A regular file, UTF-8, plain newlines, at most 256 KB, exactly one table with these seven names in this order, then a separator line.
2. `task`: `G-NNNN/T-NN` of a goal that exists, unique in the file.
3. `branch`: exactly the branch `goalgit` gives that task (`umwayi/g-0007-t-02`).
4. `head`: 40 or 64 lower case hex characters, or `none`.
5. `pr`: a whole number from 1 to 999999, or `none`. A number is used by one row only.
6. `checks`: `unknown`, `pending`, `green` or `red`. `ready`: `unknown`, `pass` or `fail`. Both say something about `head` only. `checks` and `ready` other than `unknown` need a `head`, and `ready` other than `unknown` needs a `pr`.
7. `at`: a real UTC time `YYYY-MM-DDTHH:MM:SSZ`, not later than the clock of the read.
8. At most 2,000 rows. Any other value, an empty cell, `Green` for `green`, or the wrong number of cells: WAITING.

The owner's stall setting goes in `umwayi.json`: `"work": {"stall_minutes": 30, "restarts": 1}`. `stall_minutes` is a whole number from 5 to 240, `restarts` from 0 to 3. A bad value is a config error (64), as for every other key of `umwayi.json`. Without the key the defaults apply.

## The pure functions

All in a new `umwayi/work.py`. None of them reads a file, the clock or a process, and none starts anything. `now` is passed in and comes from `rules.election_clock`, so a clock set back cannot hide a stall.

**(1) `ledger(goals, events, rows, git)`** gives one row per kept task of every goal: goal, task, state, reason, role and agent of the last `started` event, the time of the last real event (`goallog.is_real`), the time of the last `fingerprint` with `changed: true`, the time of the last `check_result`, and the ledger cells. `git` holds, per branch, the local head, whether the branch contains main, and the origin head as the last fetch left it, each `None` when unknown. A ledger row for a task that does not exist, or a task in `in review` with no ledger row, is a row with status WAITING and a fixed word.

**(2) `next_assignment(rows, slots, backlog_next)`** gives the next move for a helper, checked in this order:

| case | kind | why |
| --- | --- | --- |
| any row is WAITING | `waiting` | `unreadable` |
| a task is `running` and the slots are full (1 today) | `busy` | the running task |
| a task needs the owner | `waiting` | `owner`, with the ids |
| a task is `failed` or `stopped` (the goal halted) | `waiting` | `halted`, with the id |
| an approved goal that is not stopped has a `queued` task | `run` | the goal id: `python -m umwayi goal run G-0007` (the W60 idle rule) |
| no goal has a task left, and the W61 backlog names a task | `promote` | the backlog id: the owner turns it into a goal |
| otherwise | `none` | `empty`, or the W61 waiting word |

**(3) `next_pr(rows)`** gives the one branch whose turn it is. CI runs only on the PR that is next to merge, so at most one PR may be open.

| case | kind | why |
| --- | --- | --- |
| a ledger row is WAITING | `waiting` | `unreadable` |
| two or more rows have a PR and are not `merged` | `waiting` | `two_open`, with both numbers |
| one open PR: `ready pass`, `checks green` for the same head, and the branch contains main | `merge` | the owner merges it |
| one open PR, otherwise | `wait` or `fix` | `pending`, `red`, `fail`, `behind` (run `merge_main`), or `unknown` |
| no open PR: among `in review` tasks with a `head` (delivered) that contains main, the oldest by `at`, then goal and task id | `open` | the branch and head: the owner opens its PR |
| no open PR and every delivered branch lacks main | `fix` | `behind`, with the first branch |
| otherwise | `none` | `empty` |

**(4) `stale_branches(rows)`** gives every delivered branch that is not merged and does not contain main, oldest first, each with its step: in its worktree, `python -m tools.merge_main`, then push, then `work record ... delivered --head NEW`. A branch whose answer is unknown is listed as `unknown`, never as fine.

**(5) `helper_state(row, now, stall_minutes)`** is the fixed clock rule. For a `running` task, quiet = `now` minus the newest of three times: the last real event, the last changed tree and the last check result. Then:

- `WORKING` when quiet is under `stall_minutes`;
- `STALLED` when quiet is `stall_minutes` or more;
- `UNKNOWN` when none of the three times can be read (WAITING in `work next`);
- `IDLE` for a goal that `idle_line` calls idle; nothing otherwise.

It is the same rule as `goalwatch.judge`, which keeps its role policy, with `stall_s` = `stall_minutes` times 60. One number then rules both the supervisor and the report. A STALLED row also says whether the goal lock is held. A running task with a free lock means the supervisor itself is gone, and the task needs the owner.

**The default.** I recommend 30 minutes. It is the value of `STALL_SECONDS` and of `umwayi stalls check` today, so the default changes no behaviour. The owner's figure of 8 minutes to 1 h 23 min is the length of whole tasks, not the longest quiet gap inside one. A gap is what the rule measures, and no gap was measured (open question 1).

## What STALLED does in the product

The supervisor, in its watch loop, already sees the stall. It asks the rules gate before it acts:

1. **The stop.** It asks `{"type": "helper_stalled", "goal": G, "task": T, "role": R, "agent": A, "quiet_s": N}`. Yes, or Ask me first, or no rule: the supervisor stops the helper (SIGTERM, ten seconds, SIGKILL to its group, as now). Stopping fails closed, because a helper nobody watches must not run on. No: it lets the helper run and asks again after another `stall_minutes`. Each answer and each stop is one entry with the ids, the quiet seconds and the rule id.
2. **The cause.** The task ends `failed`, reason `stalled`, cause `no_progress`, as today. The event log and the report name the cause.
3. **The restart (the owner's addition, Nov 16).** Then the supervisor asks `{"type": "helper_restart", "goal": G, "task": T, "agent": A, "restarts_done": K}`. Only on Yes, and only while `K` is under `restarts`, it restarts the task through W9.14 retry, with the budget left of the task's approved cap and never more. The restart is a new `umwayi agent run` with every start step and gate check of today. For a Kiro builder it resumes the stopped session in the same worktree, with one fixed continue instruction (next section); where a resume is not possible, it starts a fresh attempt from the same packet. The new attempt starts with an entry `restart K+1 of G-0007 T-02 after stalled (rule ID)`. No, Ask me first, no rule, the limit reached or no budget left: no restart, and the task waits for the owner.
4. **Nothing else starts.** The next task does not start until the restarted attempt reaches `in review` or the owner answers. A restart is never silent: it needs a Yes, it is logged with its cause, and it counts against the limit. `helper_restart` joins `NEVER_AUTONOMY`, so graded autonomy can never turn an Ask into a restart.

**The dependency.** Steps 1 and 2 can be built now. Step 3 needs W9.14 retry first, because today `failed` is terminal and there is no way to start a task again. Until W9.14 is built, step 3 is "the task waits for the owner".

## The helper's own command line (Kiro)

The probe and the interrupt use `kiro-cli` only. The facts below are from the Kiro docs ([CLI commands](https://kiro.dev/docs/reference/cli-commands), [Session management](https://kiro.dev/docs/cli/chat/session-management)), read on Nov 16, and from what the repo already records in `adapters/NOTES-layer10.md` ("Kiro command line"). **None of them was tried on a machine. Each is unconfirmed.**

| fact (unconfirmed) | how the design uses it |
| --- | --- |
| `umwayi agent run` already starts `kiro-cli chat --v3 --no-interactive` with the prompt on stdin, in the task's worktree (`docs/agent-front-door.md`) | the supervisor owns that process; nothing new is needed to see it end or to stop it |
| sessions are saved after every turn, per directory, in a database under `~/.kiro/` that is owner-only; a session id is a UUID | each task has its own worktree, so the task's sessions are the ones of its folder. umwayi never opens that database |
| `kiro-cli chat --list-sessions` lists the saved sessions of the current directory | the session probe, run by the supervisor with the worktree as its folder. **What fields it prints is unknown.** Until the owner runs it once and pastes the output, the probe reads nothing from it and relies on the event log |
| `--resume` resumes the newest session of the directory, and the page says the same rule applies to `--no-interactive --resume` | the resume of a stalled task, since a task's worktree holds only that task's sessions |
| `--resume-id SESSION_ID` resumes a local or cloud session | a resume by id. **Whether it works with `--no-interactive` is unknown**, so it is used only after the owner's test shows it does |
| `--delete-session ID` | never used: the session is the owner's record |
| `/session-id` and `/sessions` exist only inside an interactive chat | not usable by the supervisor, which runs no interactive chat |
| `kiro-cli whoami`, and `kiro-cli diagnostic` with `--format json` | `whoami` is already the sign-in check (W59, 30 s). `diagnostic` could add facts to the probe; **its fields are unknown** |
| `kiro-cli acp --agent-engine v3` | the existing ACP chat; not used for goals |
| no event or notification hook is documented | there is no push signal from Kiro, so a stall is found by the clock rule, never by a message from the helper |
| the repo records that Kiro's behaviour on SIGTERM is not documented (`NOTES-layer10.md`) | the stop stays SIGTERM, ten seconds, then SIGKILL to the group. A turn cut off may be lost, since saving happens per turn (not confirmed) |

The interrupt, in order: the `helper_stalled` gate answer; the stop of the `kiro-cli` process the supervisor owns; the cause recorded; then, only on a `helper_restart` Yes, a new `agent run` in the same worktree with `--resume` (or `--resume-id ID` once confirmed) and the fixed instruction "You were stopped after N minutes without progress. Continue the same task in this folder, within the same files and rules. Do not start over." The resume flags join the fixed argument lists of `umwayi/agents.py` (`_assert_allowed`); `--delete-session` joins its forbidden words. umwayi passes no flag it has not listed.

The commands the owner runs once and pastes, so the design can stop saying unknown:

1. `kiro-cli chat --list-sessions` in a goal worktree, after one `agent run` there: the fields and their format.
2. `printf 'say ok\n' | kiro-cli chat --v3 --no-interactive --resume-id ID` with an id from step 1: whether `--resume-id` works headless, and its exit code.
3. `kiro-cli diagnostic --format json`: the field names, never the values.

Claude Code helpers get the same shape once their own resume flags are checked; that is not done here (unknown).

## The producer for the stalls check (E6)

`umwayi stalls check EVENTS.json` ([stalls.md](stalls.md)) reads a JSON file that nothing writes. The producer is umwayi-os's own supervisor, at runtime. No outside guide and no browser tab is involved.

**The choice.** `umwayi stalls check` gains a second input, `--goals`, and the old `EVENTS.json` input stays as it is. The supervisor already records everything the check needs, so the producer is the supervisor's own records, not a report that an adapter sends. Reading each helper's own session command line (the replacement) is not chosen now: none of those outputs is confirmed (table below). A session fact joins the input only after the owner pins its format.

**Inputs**, all read only, for each task in `running`:

- `length`: the total `bytes` of the task's `output` events (`umwayi/goallog.py`). It is the runtime form of "the text length of a session", counted by the supervisor as the child writes, never sent by the helper;
- `head`: the worktree's `HEAD`, from the existing `goalgit` list `head`;
- the times of the last real event, the last `fingerprint` with `changed: true`, and the last `check_result` (`goallog.is_real`);
- `stall_minutes` from `umwayi.json` (W65.R2).

**Output**, one JSON list on stdout with `--json`, else one line per session:

```json
[{"session": "G-0007/T-02", "length": 48213, "head": "3f9c...", "minutes_unchanged": 34, "verdict": "stalled"}]
```

`minutes_unchanged` is the whole minutes since the newest of these: a change of `length`, a change of `head`, a changed fingerprint, a check result. `verdict` is `working` (under `stall_minutes`), `stalled` (at or over it, the `helper_state` rule) or `idle` (no task running and a goal that `idle_line` calls idle). A value that cannot be read leaves the session out of the list and gives exit 2, never a guess.

**Exit codes:** 0 every session is `working` or `idle`; 3 any session is `stalled` (Ask me first, as every finding of the check is today); 2 an unreadable event log, state file or git answer, or an unexpected error; 64 usage (both inputs given, or neither). Never 1. It writes nothing and takes no lock. The supervisor acts on `stalled` only through the `helper_stalled` gate question above.

**What each helper can report:**

| helper | what umwayi can see at runtime | what the helper cannot report |
| --- | --- | --- |
| Claude Code (`claude -p`, started by `agent run`) | the process and its exit; stdout bytes; one `umwayi check` logbook entry per tool call, through the layer 9 hook; the spend through the telemetry receiver (`umwayi/telemetry.py`). The hook input carries `session_id` and `transcript_path` (`adapters/NOTES.md`), which umwayi does not keep | whether it is thinking or hung; a list of its sessions from the command line (not checked); the format of the transcript file (not documented in the repo, so not read) |
| Kiro (`kiro-cli chat --v3 --no-interactive`) | the process and its exit; stdout bytes; one `umwayi check` entry per tool call, when the owner's Kiro hook file is in place | whether it is thinking or hung; its spend per run (units.yaml counts Kiro by runs); a progress event (no event hook is documented); the fields of `--list-sessions` (unknown until the owner pastes them) |
| OpenCode (`opencode acp`, chat only today) | the process; every ACP `session/update` (message chunks, `tool_call`, `tool_call_update`, `NOTES-layer10.md`); one `umwayi check` entry per tool call through the plugin; each permission request | a run without a terminal: `agent run` refuses OpenCode (W9.13 waits for the owner), so it cannot take a goal role and has nothing to report to a goal; whether a quiet session is thinking or hung; a session list (whether OpenCode offers one over ACP is not checked) |

The `umwayi check` entries carry no goal or task id. They count as a sign of life only by time, which is safe while one task runs at a time.

## Delivery and CI signals

- **Delivered.** The helper's process exit, which the supervisor sees, and then the branch head on origin. umwayi never pushes and never fetches. In the product the owner, or a script of the owner's, pushes the branch and records it: `umwayi work record G-0007 T-02 delivered --head SHA`. The record command checks that SHA is the local branch head, with a git read.
- **CI done, option A (proposed).** A read only, opt in probe of the PR's check runs. It uses the network, so it is off by default and run only by the owner or the owner's script. It cannot live in `umwayi/`, because the core may import no network module. It would be `python -m tools.work_probe`, which reuses the W63 reader (`GET` the PR, its head's check runs, main's SHA) when W63 is built. It prints what it read and the exact `umwayi work record` lines to run. It writes nothing itself.
- **CI done, option B (described only).** A step in `.github/workflows/ci.yml` after `result` that sends a done notification. This is a workflow change, so it stops for the owner. It has nowhere to send to: `umwayi serve` listens only on 127.0.0.1, so a notification from GitHub cannot reach umwayi, and the only place umwayi could read it is GitHub, through the same probe. GitHub's own notifications already reach the owner. I recommend not doing B (open question 3).

## The commands

| command | does | writes | exit |
| --- | --- | --- | --- |
| `umwayi work next [--date D]` | prints the ledger in short (one line per open task), then the next moves and why: `next_assignment`, `next_pr`, `stale_branches`, every STALLED or UNKNOWN helper | nothing: no file, no entry, no lock taken | 0 a move is named and nothing is STALLED or WAITING; 3 WAITING, STALLED, owner needed, or nothing to do; 2 unexpected; 64 usage or config |
| `python -m tools.work_probe` (asked for as `umwayi work probe`, open question 2) | opt in: `"work": {"probe": true}` and the flag `--network`. For each open PR and delivered branch, `git ls-remote` for the origin head and `GET` the check runs. Prints the facts and the record lines | nothing | 0 read; 3 cannot decide (no network, timeout, rate limit, bad reply); 64 not enabled, or usage; 2 unexpected |
| `umwayi work record TASK delivered --head SHA` / `pr N` / `checks pending\|green\|red --head SHA` / `ready pass\|fail --head SHA` | owner command, terminal on stdin and stdout. Rewrites one row through the atomic writer, rolls back if the entry fails. A new head resets `checks` and `ready` to `unknown`. A value for another head is refused | one row and one entry of source `umwayi work`: ids, words, the PR number, heads and counts, never a title or text | 0 written; 2 refused (not a terminal, unknown task, a head that is not the branch head, the same value, the logbook check failed; nothing changed); 3 the kill switch on or unreadable, or the ledger WAITING; 64 usage |

Merged is not recorded here: `goal merged` and the merge observation of W9.R17 already move a task to `merged`, and the ledger reads that state. Only 0, 2, 3 and 64, never 1.

## What it never does

It never starts a helper by itself, outside the gated restart above. It never opens, approves or merges a PR, never creates or approves a goal, never raises a budget or a cap, and never pushes, fetches or pulls. It runs no shell. Its only processes are git read commands: the 18 lists of `goalgit`, plus two new read lists, `contains_main` (`merge-base --is-ancestor refs/heads/main {TIP}`) and `origin_head` (`rev-parse --verify --quiet refs/remotes/origin/{BRANCH}`). The probe adds `ls-remote`, and only in `tools/`. It never reads a helper's words to decide anything. It never opens Kiro's session database under `~/.kiro/` and never deletes a session.

## Spec lines it would add or change

Added, `### W65.R1` to `### W65.R8` at the end of requirements.md:

- **W65.R1 The ledger file.** `.umwayi/work/ledger.md`, the seven columns and parser rules 1 to 8; a bad cell is WAITING with its line number.
- **W65.R2 The setting.** `umwayi.json` `work.stall_minutes` (5 to 240, default 30), `work.restarts` (0 to 3, default 1), `work.probe` (default false); a bad value is 64.
- **W65.R3 The functions.** `ledger`, `next_assignment`, `next_pr`, `stale_branches`, `helper_state`: pure, with the case tables above in that order.
- **W65.R4 STALLED.** The `helper_stalled` gate question, a stop on Yes, Ask me first or no rule, the cause recorded, the `helper_restart` gate question, a restart only through W9.14 within `restarts` and the budget left, never a silent restart; for Kiro a resume in the same worktree with the fixed continue instruction, and the session probe through `kiro-cli chat --list-sessions` only once its output is known.
- **W65.R5 The commands.** `work next` (writes nothing), `tools.work_probe` (opt in, network, writes nothing), `work record` (owner, logged, one row).
- **W65.R6 Exit codes.** 0, 2, 3 and 64, as in the table.
- **W65.R7 What it never does,** as above.
- **W65.R8 Tests,** the table below.
- **W65.R9 The stalls producer (E6).** `umwayi stalls check --goals [--json]` reads the supervisor's own records (output bytes, the worktree head, the event times) and prints one entry per running task with `session`, `length`, `head`, `minutes_unchanged` and `verdict`; 0, 2, 3 and 64; it writes nothing.

Changed:

- **W9.R10:** `stall_s` comes from `work.stall_minutes`; the supervisor asks `helper_stalled` before it stops a stalled helper.
- **W9.14** gains the restart caller, the limit and "the budget left, never more".
- **W9.R19:** `.umwayi/work/` is a file of the root and is ignored by git.
- **W9.R8.9 and `goalgit`:** two new read lists, 20 in all, and no new write.
- **13.R9.3:** `helper_restart` joins `NEVER_AUTONOMY`.
- **10.R5 (`agents.py` argument lists):** `--resume` and, once confirmed, `--resume-id ID` (a UUID) for a Kiro `agent run`; `--list-sessions` as a probe list; `--delete-session` a forbidden word.
- **stalls.md:** the `EVENTS.json` input stays; the new `--goals` input of W65.R9 is its producer, and its open question "who writes the events file?" is answered by the supervisor's own records.

## The tests it would need

Dates and times come from today's UTC clock in the test, never a fixed day.

| rule | test | planted fault |
| --- | --- | --- |
| R1 header | `test_a_column_out_of_order_is_waiting` | accept any order |
| R1 cells | `test_each_bad_cell_is_waiting_with_its_line` (one per column) | read `Green` as `green` |
| R1 head pairing | `test_checks_without_a_head_is_waiting` | accept `green` with head `none` |
| R1 future time | `test_an_at_after_the_clock_is_waiting` | clamp it to now |
| R2 setting | `test_stall_minutes_out_of_range_is_64` | clamp to 240 |
| R3 assignment | `test_a_running_task_fills_the_one_slot` | allow a second start |
| R3 halted | `test_a_failed_task_halts_assignment` | skip to the next goal |
| R3 two open PRs | `test_two_open_prs_is_waiting` | pick the lower number |
| R3 merge | `test_merge_needs_green_and_pass_on_the_same_head` | accept `green` of an older head |
| R3 behind | `test_a_branch_without_main_is_fix_not_open` | open it anyway |
| R3 stale unknown | `test_an_unknown_contains_main_is_listed` | treat unknown as contains main |
| R3 stall rule | `test_quiet_at_exactly_n_minutes_is_stalled` | compare with `>` |
| R3 three signals | `test_a_new_check_result_resets_quiet` | use the last event only |
| R3 dead supervisor | `test_running_with_a_free_lock_needs_the_owner` | report WORKING |
| R4 stop fails closed | `test_no_rule_for_helper_stalled_stops_the_helper` | keep it running |
| R4 restart gate | `test_restart_only_on_yes_and_within_the_limit` | restart on Ask me first |
| R4 budget | `test_a_restart_gets_the_budget_left_never_more` | give the full cap again |
| R4 no silent restart | `test_every_restart_has_an_entry_with_its_cause` | restart before the entry |
| R4 next waits | `test_the_next_task_waits_for_the_restarted_one` | start the next task |
| R4 resume argv | `test_a_kiro_resume_is_one_fixed_argument_list` (the fake `kiro-cli` records its argv) | pass the continue text as an argument |
| R4 no delete | `test_delete_session_is_a_forbidden_word` | allow it in a probe list |
| R4 unknown fields | `test_the_session_probe_reads_nothing_until_its_format_is_pinned` | parse the output by guess |
| R5 next writes nothing | `test_work_next_writes_no_byte` (snapshot of the root) | write an entry |
| R5 probe off | `test_probe_without_the_setting_is_64` | probe by default |
| R5 probe fail closed | `test_a_rate_limited_reply_is_3` (recorded replies) | report checks green |
| R5 record one row | `test_record_changes_one_row_and_logs_once` | rewrite the table |
| R5 record head | `test_a_head_that_is_not_the_branch_head_is_refused` | trust the typed SHA |
| R5 rollback | `test_record_is_rolled_back_when_the_entry_fails` | write the file first |
| R9 length | `test_new_output_bytes_reset_minutes_unchanged` | read the helper's own word for its length |
| R9 unreadable | `test_an_unreadable_event_log_is_2_not_working` | report `working` |
| R9 one input | `test_both_inputs_or_neither_is_64` | prefer one silently |
| R6 codes | rows in `tests/test_exit_codes.py` | a bad cell exits 1 |
| R7 never | a source scan of `umwayi/work.py` | a socket import, a shell, a push list, a `goal.dispatch` call |

## What it does NOT prove

- It cannot tell a hung helper from one that is thinking. A long quiet gap is a fact; what it means is not.
- It cannot tell whether the work is good. `in review`, green checks and a passed merge-ready check are facts, not quality, and the owner or the reviewer decides that.
- The ledger cells are only as true as the last `work record`. The origin head is only as fresh as the owner's last fetch, or the last probe.
- A restart can fail the same way again. The limit bounds the cost; it does not fix the cause.
- Without W9.14, nothing restarts.

## Temporary: today's build setup (not product)

This section describes the way umwayi-os is built today, with an outside guide and Kiro web sessions. It is not part of the product and goes when that setup goes.

- umwayi-os cannot see a Kiro web session: there is no API it can read. A commit stays in the session's sandbox until the session pushes it. A hung session needs a person to reload its tab.
- The workaround uses the same signals with no event log. Read the branch head on origin, the PR check runs and the clock. `helper_state` then gets only two times (the last new origin head and the last check result), and a session quiet for `stall_minutes` is reported STALLED by `work next`, or by the probe, so that someone reloads the tab.
- A Kiro web session at app.kiro.dev has its session id in the tab URL, and the docs say `kiro-cli --resume-id` resumes a cloud session. Whether that reaches, lists or interrupts a web session is unknown. It is an owner test, not a claim of this design.
- The owner's addition (Nov 16), for this build setup only: the browser agent that runs the probe reloads the stalled session itself. It reloads the same tab at the same URL, never a new tab, and then sends one continue message to the session.
- **This part is outside umwayi-os.** umwayi-os cannot drive a browser: it starts no browser, holds no session cookie and has no browser module, and the core may not use the network. What would have to exist for umwayi-os to do it is unknown. I do not know whether Kiro web offers an API or an automation path for reloading a session or sending it a message, or whether its terms allow one. I also do not know what a reload does to a session's unpushed sandbox commits. Nothing in this design depends on it.
- The temporary path still never opens or merges a PR and never raises a budget. The continue message is the only thing it sends.

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-16 | Design note only; STALLED stops the helper under the rules gate and restarts it only through W9.14 under a second gate answer; the probe and the interrupt use the helper's own command line (`kiro-cli`), never a GUI; the tab reload is temporary and outside umwayi-os | W65, the owner's rule and two additions of Nov 16. |

## Open questions

1. **The stall default.** Recommendation: 30 minutes, the value umwayi uses today, until one goal run records the longest quiet gap per role. Then set it a little over that.
2. **Where the probe lives.** `python -m tools.work_probe` (this design), or `umwayi work probe` with a network exception in the core. Recommendation: `tools/`. The core's no-network test is a safety check, and changing it is the owner's decision.
3. **CI option B.** Recommendation: no workflow step. A notification has no local receiver, and the probe reads the same facts.
4. **Restarts.** `restarts` default 1, and the Ask answer does not restart. Recommendation: keep both. A second stall of the same task is more likely a cause than bad luck.
5. **`umwayi stalls check`.** Recommendation: keep both inputs. The `--goals` input is the runtime producer, and the `EVENTS.json` input stays for the owner's own files.
6. **Resume or start fresh.** Recommendation: resume the Kiro session in the same worktree, because its commits and saved turns are kept; start fresh only when the owner's test shows a resume does not work headless.
7. **Slots.** Recommendation: 1 until W9.12 `--ahead` is asked for. The functions take `slots`, so nothing changes in them later.
