# Model routing from our own records (W48, design note)

## Purpose

This note designs how `umwayi goal` could choose the agent and model for each role from umwayi's own records, not from public benchmarks alone. It is a design note only: nothing here is built, and no code, rule, steering file or workflow changes with it. The order of the work is fixed by the owner: the record format first (W48a), then the table (W48b), then the picker (W48c). Each part is its own task and pull request, and each needs the owner's approval of this note first.

The owner's words (Nov 15): per agent and model, count review rounds per task, tester failures, small-facts-wrong issues and task size (files, lines, context), from the logbook and the goal state. Set a size cap per model below the point where its failure rate rises. Use the strongest model on specs, plans and reviews (Claude as supervisor and guide; in umwayi-os the supervisor is umwayi's own program, `umwayi/goalrun.py`, and "Claude" here means a Claude Code agent of `agents.yaml` in the guide and check roles), and cheaper or free models (the OpenCode free route, Kiro Auto) on small, well-specified packets. The tester is always a different agent than the builder. Unknown model or no data means the smallest cap and Ask me first. No route may raise a budget cap.

## Current state

Nothing is built. Today the owner names every role and model by hand (`goal start --guide`, `goal approve --builder --tester --model --effort`, `umwayi/goal.py`), and two spec lines say so: the owner row of the W9.R2 table, and the W9.R23 bullet "A model, a score or learning from the owner's past answers to choose a builder or a size" (not in W9). [model-routing.md](model-routing.md) (W19 3b) is a table of vendor claims that only proposes; [task-log.md](task-log.md) is a hand-kept table per pull request that nothing reads.

### What data exists today, and what is missing

Every value below was found in the code at main `3b75b1d`. "Missing" means umwayi does not record it today; nothing is guessed.

| value | today | where |
| --- | --- | --- |
| goal, task, state, reason | recorded | `.umwayi/goals/G-NNNN/goal.json` and `T-NN.json` (`umwayi/goalstate.py`), and every `umwayi goal` logbook entry |
| the agent of each role | recorded, one per role for the whole goal | `goal.json` keys `guide`, `builder`, `tester`; the `started` event (`role`, `agent`, `cap_uu`) in `T-NN.events.jsonl` (`umwayi/goallog.py`) |
| platform of an agent | recorded at run time | `agents.yaml`; the `agent run` start entry and the budget entries name it |
| model asked for | recorded, as the word the owner typed (blank means the platform default) | `packet.model`, `goal.json` `tester_model` and `guide_model`; the `agent run` start entry (`options: model M, effort E`) |
| model actually used | Claude Code only | the budget settle entry `models m1, m2` from the telemetry receiver (`umwayi/budget.py`). Kiro sends nothing (`declared` or `unknown`, `models none`), so the model behind Kiro Auto is unknown |
| failure cause | recorded on a move to `failed` | `Cause: WORD.` in the entry; the words are the keys of `CAUSES` in `umwayi/goalpacket.py` (for example `check_failed`, `guide_rejected`, `file_outside_packet`, `task_budget_spent`) |
| tester result | recorded per check | `check_result {n, verdict}` events, and `Tester NAME: p of m checks pass.` in the in-review entry |
| guide verdict | recorded | `Guide NAME: accept, reject or unclear.` in the in-review entry |
| review rounds | missing: always 1 | `failed` has no way out (`TRANSITIONS`, `umwayi/goalpacket.py`); a rejected task is not run again. Retry is W9.14 |
| small facts wrong | missing | no field, no event, no entry. Only the verdict words pass, fail and unclear exist |
| files listed in the packet | recorded | `packet.files`, 1 to 20 paths |
| files changed | recorded as a count | `Scope: n files, all allowed.` (from `git diff --name-status`, `umwayi/goalgit.py`) |
| lines added and removed | missing | no `--numstat` in `umwayi/goalgit.py` |
| context size | missing as stored data | context bytes are checked against 200 KB when the plan is read and not kept; no token count before a run |
| guide's size estimate | recorded | `packet.size`, 15 to 90 minutes |
| tokens used | Claude Code only | the settle entry (`tokens input, output, cache_read, cache_creation`) |
| spend | recorded per task, not per role | `T-NN.json` `spent_uu` (all roles together); the per-role sum is kept only in memory (`_Run.spent`, `umwayi/goalrun.py`). Settle entries carry no goal or task, and are matched by agent and time window |
| whether the owner merged | recorded | `goal merged` moves the task to `merged` |

Two more facts shape the design. OpenCode cannot take a goal role yet (W9.R23, waiting for W9.13), so the "OpenCode free route" cannot be picked until W9.13 is built. And `goal_start` has no `model` field, so a rule cannot match a model today.

## The record format (W48a)

One routing record per role run of a task, written once, when the task reaches a final state (`merged`, `failed` or `stopped`), as one `umwayi goal` logbook entry of the new kind `route_record`. No new file: the logbook already has the hash chain, so a record cannot be edited without `logbook verify` finding it. Every value is an id, a word, a count or a hash, never text from a packet, a prompt, a diff or helper output (the rule of W9.R18).

| field | value | where it comes from | checkable outside the transcript |
| --- | --- | --- | --- |
| `goal`, `task` | `G-NNNN`, `T-NN` | goal state | yes: goal files and the logbook |
| `role` | `guide`, `builder`, `tester`, `check` | the `started` event | yes |
| `agent`, `platform` | names from `agents.yaml` | `goal.json`, `agents.yaml` | yes |
| `model_asked` | the owner's word, or `default` | packet or `goal.json` | yes: the `agent run` start entry |
| `model_seen` | the models of the settle entries, or `unknown` | budget settle entries of the run window | Claude Code: as far as its telemetry is true; Kiro: always `unknown` |
| `outcome` | `merged`, `failed`, `stopped` | final state | yes |
| `cause` | a `CAUSES` word, or `none` | the `failed` entry | yes |
| `round` | `1` | always 1 until W9.14 | yes |
| `checks`, `checks_failed`, `checks_unclear` | counts | `check_result` events (tester row only) | yes: the events file |
| `guide` | `accept`, `reject`, `unclear`, `none` | the in-review entry (check row only) | yes |
| `small_facts` | a count, or `unknown` | the owner, after merge (see below) | yes, as the owner's own entry; it is a judgement, not a measure |
| `files_listed` | count | packet | yes |
| `files_changed`, `lines_added`, `lines_removed` | counts | `git diff --numstat BASE COMMIT` (new, read only) | yes: anyone can rerun the diff from `base` and `commit` in `T-NN.json` |
| `context_bytes` | count | the sum of the packet's context files at plan time (new: kept, not only checked) | yes: the files at `base` |
| `size_minutes` | 15 to 90 | packet | yes |
| `tokens_in`, `tokens_out` | counts, or `unknown` | settle entries | Claude Code only |
| `spent_uu`, `cap_uu` | counts | the run's own spend (new: kept per role) and its cap | yes: the settle entries and the start entry |

What W48a adds to the code: one read-only git list (`diff --numstat`), keeping `context_bytes` and the per-role spend, the `route_record` entry shape, and one owner command for small facts: `umwayi goal facts G-NNNN T-NN --wrong N` after `merged`, which writes one entry and nothing else (refused before `merged`, or twice for one task). Until the owner uses it, `small_facts` is `unknown`, never 0.

## The table (W48b)

The table is not a file. It is computed from the `route_record` entries each time it is read, so it cannot drift from the records and cannot be edited on its own. `umwayi goal routes [--json]` prints it, and the same function feeds the picker. If `logbook verify` fails, there is no table: every pick is Ask me first.

One row per (`platform`, `agent`, `model`, `role`), where `model` is `model_seen` when known and otherwise `model_asked` with the mark `asked`:

| column | meaning |
| --- | --- |
| `runs` | number of records |
| `merged`, `failed`, `stopped` | counts by outcome |
| `failed_scope`, `failed_tests`, `failed_rejected`, `failed_other` | failures by the reason of their cause |
| `check_fail_rate` | failed checks over all checks (tester rows) |
| `small_facts` | sum of the owner's counts, and how many records are still `unknown` |
| `by_size` | for each size class: runs and failures |
| `cap` | the largest size class this row may take (below) |
| `data` | `enough` or `too_few` |
| `from`, `to`, `chain` | the first and last entry used and the chain value of the last, so anyone can rebuild the same table |

Size classes are set from what is known before a run, because the picker must decide before a run: `S` (at most 3 files listed, at most 32 KB of context, at most 30 minutes), `M` (at most 8 files, 96 KB, 60 minutes) and `L` (the packet limits: 20 files, 200 KB, 90 minutes). A packet is the smallest class that holds all three of its numbers. The lines changed after the run are kept to check later whether the classes predict well; they do not set the class.

The cap of a row: start at `S`. Move up one class only while the class below has at least 10 records and a failure rate (`failed` over `merged` plus `failed`) at most 10 points above the row's rate in `S`. Stop at the first class that does not pass. A row with fewer than 10 records in `S` has `data: too_few` and the cap `S`. The numbers 10, 10 points and the class bounds are proposals for the owner (Open questions).

## The picker (W48c)

The picker runs inside `goal approve` and proposes; the owner's approval is still the act that names the roles (recommended, see Open questions). It never runs an agent, and it reads only `agents.yaml`, a new owner file `routes.yaml` and the table.

`routes.yaml` (in the root, written only by the owner) lists the candidates per role, strongest first, and a `tier` for each: `strong` or `small`. For example the guide and check may list only Claude Code agents, and the builder a Kiro Auto agent before a Claude one. The tier is the owner's word, not a benchmark; [model-routing.md](model-routing.md) may help the owner write it, and nothing reads that table.

Rules, in order:

1. **Guide and check** take the first `strong` candidate that passes `umwayi agent check`. No `strong` candidate: Ask me first.
2. **Builder:** for each packet, the first candidate (in the owner's order) whose table `cap` holds the packet's size class. A `small` candidate is tried only for a packet whose class it holds.
3. **Unknown model or no data:** a row with `data: too_few`, or a model that is `unknown` and has no `asked` row, has the cap `S`. A packet above `S` with no other candidate: Ask me first.
4. **The tester is not the builder:** the tester is the first candidate whose agent name differs from the builder's (W9.R2.2, unchanged). If its platform and model are also the builder's, the warning of W9-Q2 is shown, as today.
5. **No route raises a budget:** the picker proposes agents and models only. It never writes or changes `--task-budget-uu`, `--goal-budget-uu`, `--budget`, `--plan-budget-uu`, `units.yaml` or a cap, and the run cap stays `min(task left, goal left, per_run, day left)` (W9.R15).
6. **OpenCode** is never picked for a goal role until W9.13 is built; a `routes.yaml` that lists one for a role is a config problem.
7. **The rules still decide:** every start still asks `goal_start`; a pick is never a Yes. `goal_start` gains a `model` field (the model asked), so the owner can write a rule on it.

Refusals and their answers:

| case | answer |
| --- | --- |
| no `routes.yaml`, or no candidate passes `agent check` | Ask me first, one queue item, the owner names the roles by hand as today |
| a packet larger than every candidate's cap | Ask me first for that packet |
| the logbook chain is broken, or the table cannot be read | Ask me first; no pick is made |
| the kill switch is on, or its state is unknown | as every goal command today: nothing starts (exit 3) |
| `routes.yaml` malformed (unknown key, unknown agent, an OpenCode role, a tier that is not `strong` or `small`, a list longer than 8) | exit 64, nothing changed |

### Exit codes

Only 0, 2, 3 and 64. `goal routes`: 0 printed, 2 an unexpected error, 64 usage or a bad `routes.yaml`. `goal approve --route`: 0 the proposal was shown and approved, 2 refused as `approve` is today (nothing changed), 3 Ask me first (a refusal of the table above), 64 usage or config. `goal facts`: 0 written, 2 refused (wrong state, given twice), 64 usage. Never 1.

### What it logs

- One `route_record` entry per role run at a final state (W48a).
- One `small_facts` entry per `goal facts` (W48a).
- One `route_pick` entry per approved proposal: for each role and packet the agent, the model asked, the size class, the row's `runs` and `cap`, and the rule number that chose it, with the table's `to` and `chain`, so the pick can be replayed. `goal routes` writes nothing.

### What it never does

No network and no shell: it runs no command except the fixed read-only git lists of `umwayi/goalgit.py`, and starts no agent. It never reads a transcript, a prompt or helper output. It never raises or sets a budget, never moves an Ask me first to Yes, never writes `rules.yaml`, `agents.yaml` or `routes.yaml`, never picks the builder as the tester, and never uses a public benchmark or the W19 table to decide.

## Spec lines it would add or change

Changed (requirements.md, W9):

- W9.R2 table, owner row: "picks the builder, tester, model and effort" becomes "picks the builder, tester, model and effort, or approves the ones `goal approve --route` proposes (W48.R3)".
- W9.R2.1: add "A proposed role is approved by the same act; a proposal names nobody by itself."
- W9.R23, the bullet "A model, a score or learning from the owner's past answers to choose a builder or a size" becomes "A model or a score that chooses a builder or a size without the owner's approval, or from anything but the route records of W48.R1".
- W9.R18: add the entry kinds `route_record`, `small_facts` and `route_pick`, with the fields above.
- The `goal_start` action (W9.R7.3): add `"model": "<model asked or default>"`.

Added:

- **W48.R1 The route record.** 1. One `route_record` entry per role run at a final state, with exactly the fields of the record table. 2. Every value is an id, a word, a count or a hash. 3. `unknown` is written for a value that is not measured, never 0. 4. `goal facts` writes the owner's small-facts count once per merged task.
- **W48.R2 The route table.** 1. Computed from the records on every read, never stored. 2. The size classes and the cap rule as above. 3. A broken chain gives no table.
- **W48.R3 The picker.** 1. The seven rules above. 2. The refusals table. 3. Exit codes 0, 2, 3 and 64. 4. One `route_pick` entry per approval.

## The tests it would need

Each rule has a planted fault that a named test must catch:

| rule | test | planted fault |
| --- | --- | --- |
| a record per role run, ids and counts only | `test_route_record_shape` | write the packet's `goal` text into the entry |
| `unknown` is never 0 | `test_unknown_stays_unknown` | write `small_facts 0` before `goal facts` |
| lines from git, read only | `test_numstat_is_read_only` | use a `diff` with `--output` |
| the table is the records | `test_table_rebuilds_byte_for_byte` | cache the table in a file |
| broken chain means no table | `test_broken_chain_asks` | skip the verify |
| the cap rule | `test_cap_moves_up_only_with_ten_good_records` | move up with 9 records, or with a rate 11 points worse |
| unknown model gets `S` | `test_unknown_model_smallest_cap` | give an unknown model the cap `M` |
| strong for guide and check | `test_guide_is_strong` | let a `small` candidate be guide |
| tester is not builder | `test_tester_differs_from_builder` | pick the same name for both |
| no route raises a budget | `test_pick_never_changes_a_budget` | let the pick set `--task-budget-uu` higher |
| no OpenCode role before W9.13 | `test_opencode_role_is_config_error` | accept an OpenCode builder |
| a pick is never a Yes | `test_pick_still_asks_goal_start` | skip the `goal_start` check after a pick |
| no network, no shell | `test_no_network_no_shell` (an import and call scan, as `tests/test_system.py` does for `umwayi/goal*.py`) | add a `subprocess` call with `shell=True` |
| exit codes | `tests/test_exit_codes.py` rows | a crash exits 1 |

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-16 | Design note only: the record format first (W48a), then the table (W48b), then the picker (W48c); the picker proposes and the owner approves | W48, the owner's words of Nov 15. |

## Open questions

1. **Does the owner approve the pick, or does the picker name the roles by itself?** Recommendation: the owner approves, at `goal approve --route`. It keeps W9.R2.1 and the never list as they are, and a wrong table costs one look, not one run.
2. **The cap numbers** (10 records, 10 points, the class bounds). Recommendation: keep them as proposed for the first month, and review them in `docs/model-routing-design.md` once 30 records exist.
3. **Where small facts come from.** Recommendation: only the owner, with `goal facts`, after merge. A tester or guide count would be an AI's judgement of an AI.
4. **Kiro Auto's real model is unknown.** Recommendation: record it as `kiro/auto` with the mark `asked`, so it earns a cap from its own results like any model, and say in `goal routes` that the model behind it can change.
5. **Should the tester also differ by model, not only by name?** Recommendation: yes, as a rule of the picker (not of approval), when another candidate exists; otherwise the W9-Q2 warning, as today.
6. **Per-role spend is only in memory today.** Recommendation: keep it in the record (W48a), and do not change the task total in `T-NN.json`.
7. **OpenCode free route.** Recommendation: do not design its row further until W9.13 lets OpenCode take a goal role.
