# Agents as installable apps (W43, design note)

## Purpose

This note designs W43 from its task line: "Agents as installable apps: a manifest, `umwayi agent list`, `show` and `run` through the supervisor, Steward first, and the owner approves the permissions in a real terminal." It is a design note only. Nothing here is built, and no code, rule, steering file, safety check or workflow changes with it.

An app is a named piece of work with a manifest that says, before it runs, what it may ask the rules gate for, which files it may read and write, and how much it may spend. The owner reads the manifest once in a real terminal and approves it, bound to its hash. After that, `umwayi agent run NAME` runs it through the same gates as every other run, and any action outside the manifest is No.

### What it must never become

- **Not a marketplace.** There is no index, no search, no catalogue, no ratings and no publisher accounts. umwayi knows only the apps in one local folder.
- **No install from the network.** umwayi never downloads, fetches, clones or updates an app. The owner copies an app's folder from a local path by hand. umwayi has no `install` command.
- **No app outside the rules gate.** An app can only be a built-in helper whose every step umwayi checks, or an agent of `agents.yaml` whose every tool call the adapter hook checks. An arbitrary program as an app is refused, because nothing could check what it does once started.

## Current state

Nothing is built. These facts were read in the code at main `3817f2a`; "missing" means umwayi has nothing for it today, and nothing is guessed.

| what | today | where |
| --- | --- | --- |
| agents | `agents.yaml` in the root (or `--agents PATH`), at most 50 agents, keys `name, platform, command, transport, workdir, kiro_agent, trust_tools, max_turns, timeout_minutes, provider, model`; platforms `claude-code`, `kiro`, `opencode` | `umwayi/agents.py` (`KEYS`, `REQUIRED`, `PLATFORMS`, `Agent`) |
| `umwayi agent list` | exists: one line per agent (name, platform, transport, command, workdir), starts nothing, exit 0 or 64 | `agents.list_agents`; 10.R1.3 |
| `umwayi agent show` | missing | |
| `umwayi agent run` | exists: kill switch, the rules action `agent_run`, the run lock, the gate checks, the budget reserve with the rules action `budget_check`, the start entry, `Popen` with no shell, the watch (kill switch, logbook, timeout), the settle entry | `agents.run_agent`, `_Run._steps`, `_reserve`, `_start`, `_watch` |
| the goal supervisor | starts children only as `python -m umwayi agent run NAME - --cap-uu N`, no shell, holds `.umwayi/goal.lock`, asks `goal_start` first | `umwayi/goalrun.py` (`CHILD_PREFIX`, `child_argv`, `_spawn`, `supervise`) |
| Steward | a built-in helper, `umwayi steward`: steps `read_queue`, `read_logbook`, `write_draft`; reads `queue.md` and `LOGBOOK.md`; writes one `drafts/steward-NNNN.md`; calls no model and no network; no budget | `umwayi/helpers/steward.py`, `umwayi/helpers/base.py`, `docs/helpers.md`, requirements Layer 7 item 6 |
| a helper's actions | `{"type": TYPE, "helper": NAME}`, each checked with `rules.check_in_root` before the work, one logbook entry per step, source `umwayi steward` | `Helper.step`, `Helper._action` |
| a manifest, an app folder, an app approval | missing | |
| a real-terminal check | exists: stdin and stdout are both a terminal | `goal._is_terminal` and `_owner`, `feedbacksend._terminal`, `loginwizard._terminal` |
| a hash bound to an approval | exists in other forms: the packet `sha256` in goal approval, the rules change log hash, guidance `source_hash` | `umwayi/goalpacket.py`, `umwayi/rulelog.py`, `umwayi/guidance.py` |
| what the hub says about Steward | unknown: the hub is not in this repo | |

Two more facts shape the design. `umwayi steward` can exit 1 today (a logbook that fails its tamper check, or a malformed `queue.md`), while the `umwayi agent` family never exits 1 (`docs/exit-codes.md`). And for an agent of `agents.yaml`, the hook sees each tool call but not which app asked for it.

## The manifest

One file, `manifest.yaml`, read with umwayi's own strict reader (`umwayi/miniyaml.py`), at most 16 KB, regular file only, UTF-8, no unknown key, no repeated key.

| field | value | checked |
| --- | --- | --- |
| `name` | the app name, the pattern of an agent name (`^[a-z][a-z0-9-]{0,31}$`) | equals the folder name; not the name of an agent in `agents.yaml` |
| `version` | `MAJOR.MINOR.PATCH`, numbers only | form only |
| `platform` | `umwayi-helper`, `claude-code` or `kiro` | `opencode` waits for a non-interactive run (as W9.R23) |
| `entry` | for `umwayi-helper`: `helper: steward` (a name of `HELPERS`); for a platform: `agent: NAME` (an agent of `agents.yaml` with that platform) | never a command line, a path or an argument list |
| `permissions` | a list of rules action types, for example `[read_queue, read_logbook, write_draft]` | each matches `^[a-z][a-z0-9_]{0,39}$`; at most 20; none of `NEVER_AUTONOMY` except `agent_run` and `budget_check`, which every run asks anyway |
| `reads`, `writes` | lists of plain relative paths or `prefix/` folders in the root, at most 20 each | no `..`, no absolute path, no `.umwayi/`, `.git/`, `rules.yaml`, `autonomy.yaml`, `agents.yaml`, `LOGBOOK.md` in `writes` |
| `budget_uu` | a whole number from 0 to `limits.per_run` of `units.yaml` | 0 for an app that runs no model |
| `text` | one line, at most 200 characters, shown to the owner, never logged | plain text |

The manifest hash is the SHA-256 of the file's exact bytes. It is not a field in the file (a file cannot hold its own hash); umwayi computes it on every read and prints it.

## Where apps live

`.umwayi/apps/NAME/manifest.yaml`, one folder per app, nothing else in it. The owner copies the folder there from a local path with an ordinary copy. umwayi reads the folder and never writes it: no install, no update, no removal. A folder that is a link, holds anything but `manifest.yaml`, or whose name does not match the manifest is listed as `broken` and cannot run. At most 20 apps.

## The commands

| command | prints | reads | logs |
| --- | --- | --- | --- |
| `umwayi agent list` | the agents of `agents.yaml` as today, then one line per app: `app NAME VERSION PLATFORM approved` or `not approved` or `changed` (approved for another hash) or `broken` | `agents.yaml`, `.umwayi/apps/*/manifest.yaml`, the logbook | nothing |
| `umwayi agent show NAME` | every field of the manifest one per line, the hash, and the approval state with the date of the approval entry | the same, for one app | nothing |
| `umwayi agent approve NAME` | the same as `show`, then `Type the app name to approve these permissions for this exact manifest:` | the same | one approval entry, or one refusal entry |
| `umwayi agent revoke NAME` | one line | the logbook | one revoke entry |
| `umwayi agent run NAME` | as `agent run` today | the manifest, the logbook, then what the app's steps read | as `agent run` today, plus the app's id and hash in the start entry |

`list` and `show` never start anything and work while a run goes on. `approve` and `revoke` are owner commands (a real terminal, see below). `run NAME` looks up `agents.yaml` first; an app name is the same pattern, and a name in both is refused when the file is read.

## How a run goes through the gates

`umwayi agent run NAME` for an app does, in this order, and stops at the first step that is not a plain Yes:

1. Read the manifest and compute its hash. A broken manifest: exit 64.
2. Find the newest approval or revoke entry for NAME in the tamper checked logbook. No approval, a revoke after it, or an approval for another hash: exit 3 (`Ask me first: approve this app first: umwayi agent approve NAME`), nothing starts.
3. A permission whose type umwayi does not know (not a helper step type and not a tool type of the platform's adapter): exit 3, one queue item, nothing starts.
4. The kill switch, then the rules action `app_run` (`{"type": "app_run", "app": NAME, "platform": P, "manifest_sha256": H}`), then the run lock: as `agent_run` today. `app_run` is added to the never list, so graded autonomy can never move it.
5. The budget: the cap is `min(budget_uu, --cap-uu if given, per_run, day left)`, reserved with `budget_check` as today. A manifest with `budget_uu: 0` reserves nothing and may not start a model.
6. The work, through the existing path of its platform:
   - `umwayi-helper`: the helper runs in the same process. Before each step, the base checks the step's type against the approved `permissions` (not listed: No, exit 2, the step does not run) and the file it reads or writes against `reads` and `writes` (outside: No), then asks the rules as today. A permission in the manifest is never a Yes: the rules still answer.
   - `claude-code` or `kiro`: `agent run AGENT` as today, with the app id and hash passed to the hook so each tool call's action carries `"app": NAME`. A tool type not in `permissions`: No. This needs the hook change of open question 4; until it is built, a platform app cannot be approved.
7. The end: the settle entry and the exit, as `agent run` today. A helper's exit 1 is mapped to 2.

"Through the supervisor" here means the `agent run` path itself, which already watches the kill switch, the logbook and the timeout and holds the run lock. A goal role taken by an app is out of scope (open question 5).

## How the owner approves

- `umwayi agent approve NAME` runs only when stdin and stdout are both a terminal (the check of `goal._owner`). Otherwise exit 2, nothing written.
- It prints the manifest fields and the hash, then reads one line. Only the exact app name approves; anything else, an empty line or end of input is a refusal (exit 2). A supervisor's child has a pipe for stdin, so an agent can never pass this check; and no command, rule, answer or queue item can approve for the owner.
- The approval is one logbook entry, source `umwayi agent approve`: `Approved app NAME version V (sha256 H): permissions N, reads N, writes N, budget N UU.` Ids, counts and the hash only, never the manifest text, a path or the `text` field.
- The approval holds for that hash only. Any change to the manifest, one byte included, makes the app `changed` and it needs a new approval.
- `umwayi agent revoke NAME` writes `Revoked app NAME (sha256 H).` The next run is exit 3.
- The approval lives only in the logbook, so it is covered by the hash chain: an edited or deleted approval is found by `logbook verify`, and a logbook that fails its check approves nothing (exit 2).

## Steward as the first app

What its manifest would be, from what the repo records (`umwayi/helpers/steward.py`, `umwayi/helpers/base.py`, `docs/helpers.md`, `.kiro/specs/umwayi-os/design.md` "Steward"):

```yaml
name: steward
version: 1.0.0
platform: umwayi-helper
entry:
  helper: steward
permissions: [read_queue, read_logbook, write_draft]
reads: [queue.md, LOGBOOK.md]
writes: [drafts/]
budget_uu: 0
text: Reads the queue and the logbook and writes one proposal draft. Changes nothing in the queue.
```

- The version `1.0.0` is a proposal: the repo gives Steward no version. What the hub records about Steward is unknown.
- `budget_uu: 0` because Steward calls no model and imports no budget code.
- `writes: [drafts/]` because Steward writes `drafts/steward-NNNN.md` and nothing else. The run lock, the logbook and an Ask me first queue item are written by the base, not by the app, and are not in `writes`.
- `umwayi steward` keeps working as today, unapproved; only `umwayi agent run steward` needs the approval (open question 1).

## Exit codes

Only 0, 2, 3 and 64. `agent list` and `agent show`: 0 printed, 2 an unexpected error or a logbook that fails its check, 64 usage or a bad `agents.yaml`. `agent approve` and `agent revoke`: 0 written, 2 refused (not a terminal, not the exact name, a broken manifest, a logbook that cannot be written), 64 usage. `agent run NAME` for an app: 0 done, 2 No (a missing permission, a rule, a refusal) or an unexpected error, 3 Ask me first (not approved, changed, an unknown permission, the kill switch, the run lock, the budget), 64 usage or a broken manifest. Never 1.

## What it never does

No network: no fetch, no download, no update check. No install: umwayi never writes `.umwayi/apps/`. No root: nothing runs as another user and nothing asks for more rights. It never raises a budget: `budget_uu` can only lower a cap and is refused above `per_run`. It never runs an app that is not approved for this exact manifest hash. It never runs a command line from a manifest. It never lets an approval stand for a rule: every action is still asked.

## What it does not prove

- An approved app can still do harm inside its permissions: a `write_draft` app can write a misleading draft, and a platform app can do anything its permitted tool types allow, within the rules.
- The approval shows the owner read the manifest, not that the manifest is honest about the app's purpose. `text` is the app author's words.
- Enforcement stays cooperative ([what it is and is not](what-it-is.md)): a process that never asks is not checked. The manifest narrows what umwayi allows; it does not sandbox the app.
- A link inside the root is not resolved by the path checks, as for `__prefix` in [rules](rules.md).

## Spec lines it would add or change

Changed:

- 10.R1.3 becomes: "`umwayi agent list` prints every agent in agents.yaml with its platform and transport, then every app under `.umwayi/apps/` with its version, platform and approval state (W43.R3), and starts nothing."
- Layer 7 item 6 gains: "Steward may also run as the app `steward` through `umwayi agent run steward` (W43.R6); `umwayi steward` is unchanged."
- `NEVER_AUTONOMY` (13.R9.3) gains `app_run`.

Added, a new section at the end of requirements.md, `### W43.R1` to `### W43.R7`:

- **W43.R1 What it never is.** No marketplace, no network install, no app outside the rules gate; no `install` command; `.umwayi/apps/` is never written by umwayi.
- **W43.R2 The manifest.** The fields, limits and checks of the manifest table; the hash is the SHA-256 of the file bytes.
- **W43.R3 list and show.** What they print and read; they write nothing.
- **W43.R4 Approval.** A real terminal, the exact name typed, one logbook entry with ids, counts and the hash, bound to that hash; `revoke`.
- **W43.R5 Run.** The seven steps above; a type outside `permissions` is No; an unknown permission is Ask me first; `app_run` on the never list.
- **W43.R6 Steward first.** The Steward manifest above; the platform apps wait for the hook change.
- **W43.R7 Exit codes.** 0, 2, 3 and 64, as above; a helper's 1 becomes 2.

## The tests it would need

| rule | test | planted fault |
| --- | --- | --- |
| no network | `test_no_network_module` (an import scan of the new module) | import `urllib` |
| no install | `test_umwayi_never_writes_the_apps_folder` (a snapshot of `.umwayi/apps/` around every command) | `approve` copies the manifest |
| no command line entry | `test_entry_is_a_helper_or_an_agent` | accept `entry: {command: [sh, -c, x]}` |
| manifest checks | `test_each_manifest_problem_is_64` (one bad field each) | accept `..` in `writes` |
| hash binding | `test_one_changed_byte_needs_a_new_approval` | compare the version instead of the hash |
| real terminal | `test_approve_needs_both_terminals` | check stdout only |
| exact name | `test_only_the_exact_name_approves` | accept `y` |
| an agent cannot approve | `test_a_pipe_on_stdin_never_approves` | read the answer from an environment value |
| approval in the logbook only | `test_an_edited_approval_entry_is_found` | keep the approval in a file |
| ids and hashes only | `test_approval_entry_has_no_manifest_text` | write the `text` field |
| missing permission is No | `test_a_step_outside_permissions_is_no` | skip the permission check |
| unknown permission is Ask me first | `test_an_unknown_permission_is_exit_3` | treat it as No |
| a permission is not a Yes | `test_the_rules_still_answer_after_approval` | skip the rules check of an approved step |
| never raises a budget | `test_budget_uu_only_lowers_the_cap` | use `budget_uu` when it is above `--cap-uu` |
| `app_run` never moved | `test_app_run_is_on_the_never_list` | remove it from the list |
| revoke | `test_a_revoked_app_is_exit_3` | read the oldest entry |
| exit codes | rows in `tests/test_exit_codes.py` | a helper's 1 passed through |

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-16 | Design note only; an app is a built-in helper or an agent of `agents.yaml`, never a command line; the approval is a logbook entry bound to the manifest hash, typed in a real terminal | W43, the owner's task line and the reviewer's brief of Nov 16. |

## Open questions

1. **Should `umwayi steward` itself need the app approval?** Recommendation: no, not now. It is a typed owner command today with its own rules; only `agent run steward` needs the approval. Revisit when a second helper app exists.
2. **What does the owner type to approve?** Recommendation: the exact app name, as proposed. `yes` is too easy to send by habit.
3. **Is the approval a logbook entry only, or also a file?** Recommendation: the logbook only. One record, covered by the hash chain, and nothing for an app to edit.
4. **Platform apps (Claude Code, Kiro).** The hook would need to know the app of a run, for example from an environment value that `agent run` sets and the hook copies into the action. Recommendation: build Steward first (W43a) and design the hook part as its own task, as W9.16 is for a goal's scope.
5. **Apps as goal roles.** Recommendation: not in W43. A goal role is an agent of `agents.yaml` today (W9.R2); joining the two needs its own design.
6. **A version check.** Recommendation: show the version, never compare it. The hash decides.
7. **Where the hub's description of Steward fits.** Unknown here; recommendation: when the owner links it, the manifest's `text` may quote it in one line.
