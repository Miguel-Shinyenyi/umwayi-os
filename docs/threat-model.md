# Threat model (W67, design note)

## Purpose

This page says, part by part, what umwayi-os protects, from whom, and where the protection ends. It is meant to be read before trusting a run, and before building the next control. It is a design note only: no code, rule, steering file, safety check, workflow or exit code changes with it. Every control named below cites the file or test that shows it. Where the repo shows nothing, this page says so.

How to read it: umwayi-os is cooperative ([what it is and is not](what-it-is.md)). A program that umwayi starts, and that asks umwayi before each tool call, is checked. A program that never asks is not. Every helper runs as the owner's own user, with the owner's file permissions. There is no sandbox.

## Current state

### Actors

| actor | who | trusted for |
| --- | --- | --- |
| owner | the one person, at a real terminal | rules, approvals, budgets, merges |
| supervisor | the program `umwayi/goalrun.py` (W9.R2: "umwayi itself, a program and not an AI helper"); and, in the owner's words, the Claude session in the goal guide role that plans and checks (see "The supervisor") | following fixed rules; nothing else |
| helper | an AI agent started by umwayi (builder, tester, guide, a chat), or a built-in helper (Steward, social) | nothing; every action is checked |
| tool output | text a helper reads: a web page, a file, a command's output, an issue | nothing; it is data |
| other agents | agents and programs umwayi did not start, on the same machine or on GitHub | nothing; umwayi cannot see them |

### The parts

The sections below follow the parts of an operating system: processes, permissions, resources, audit, shared memory, apps, drivers and the front door.

## Processes

- **Assets:** the owner's machine time, the working trees, the owner's checkout of the repo.
- **Actors:** helpers, the supervisor.
- **Trust boundary:** the process umwayi starts (`agent run`) and everything that process starts itself.
- **What stops what:**
  - No shell between umwayi and a helper: every start is an argument list (`agents._Run._start`, `goalrun._spawn`; `tests/goal/test_goalrun.py` `GuardTests.test_no_shell_and_no_network_in_any_goal_module`).
  - One run at a time (the run lock, `umwayi/runlock.py`) and one goal supervisor (the goal lock, `umwayi/goalstate.py`).
  - The kill switch stops every run and denies every tool call while on, or while its state is unknown (`tests/adapters/test_claude_code.py` `KillSwitchTests`).
  - A timeout and a stall judge stop a silent or looping helper (`tests/goal/test_goalrun.py` `WatchTests.test_a_builder_that_is_silent_is_stopped_as_stalled_and_the_child_is_gone`, `test_the_same_error_twice_is_looping`).
  - Each task runs in its own git worktree, never in the owner's checkout (W9.R8; `tests/goal/test_worktree.py`).
- **What it does not stop:**
  - A helper's own child processes run as the owner and are not gated unless they ask.
  - A helper can read any file the owner's user can read, and write any file it can write, between the gate's checks if the call is not seen. Tool calls are seen; the processes a shell command starts are not.
  - No sandbox, no container, no other user (sandboxing was deferred, requirements Layer 10 "Out of scope").

## Permissions

- **Assets:** the owner's rules (`rules.yaml`), the answers Yes, No and Ask me first.
- **Actors:** helpers (asking), the owner (writing rules).
- **Trust boundary:** the rules check (`umwayi/rules.py`), reached through `umwayi check` and the adapter hooks.
- **What stops what:**
  - Fail closed: no rule, a broken file or bad JSON is Ask me first (`tests/test_rules.py` `FailClosedTests`).
  - No beats Ask me first beats Yes (`tests/test_rules.py` `DecisionTests`).
  - Starter rules refuse edits and shell commands that name the guard files, among them `rules.yaml`, `LOGBOOK.md`, `.umwayi`, the hook settings, `umwayi kill` and `umwayi decision` (`rules.yaml` `cc-no-guard-edits`, `cc-no-guard-shell`; `tests/test_starter_rules.py`).
  - A changed `rules.yaml` is logged before it is used (`tests/test_rulelog.py` `ChangeTests.test_a_weakened_no_is_logged_before_the_check_that_uses_it`).
  - Graded autonomy is off by default and never moves the types of the never list, among them `agent_run`, `budget_check` and `goal_start` (`umwayi/rules.py` `NEVER_AUTONOMY`; `tests/autonomy/test_gates.py` `FailClosedTests`).
- **What it does not stop:**
  - Matching is plain text, not a shell parser. A command can be written to get past a `__contains` matcher ([rules](rules.md)). Ask me first for every shell command is the real guard.
  - The guard lists do not name `guidance.yaml`, `units.yaml`, `agents.yaml`, `tools/`, `.kiro/steering/` or `umwayi/`. An edit of these is Ask me first (`cc-ask-write`), not No.
  - The starter rules do not deny `umwayi goal` owner commands or `umwayi queue answer` to a helper ([goals](goals.md), "Not built").

## Resources

- **Assets:** the owner's spend (UU), the budget limits.
- **Actors:** helpers spending; the owner setting limits.
- **Trust boundary:** the budget governor (`umwayi/budget.py`, `umwayi/units.py`) and the goal budget (`umwayi/goalbudget.py`).
- **What stops what:**
  - Every start reserves first and asks `budget_check`, which autonomy can never move (`NEVER_AUTONOMY`).
  - A run's cap is the smallest of the task, goal, per-run and day budgets; no rule or answer raises an approved budget (W9.R15.7, `umwayi/goalbudget.py` `cap`).
  - A changed `units.yaml` is logged (`units.yaml changed ...`, `tests/budget/support.py`).
- **What it does not stop:**
  - Only Claude Code reports measured spend. Kiro and OpenCode are declared or unknown and charged a worst case ([budget governor](budget-governor.md)).
  - A helper with a write Yes for `units.yaml` could raise a limit. The change is logged, not refused.
  - Spend inside the platform beyond what it reports is not seen.

## Audit

- **Assets:** the logbook (`LOGBOOK.md`) and its hash chain.
- **Actors:** every writer through `logbook.append`; anyone who reads it.
- **Trust boundary:** the checked append and `logbook verify`.
- **What stops what:**
  - Append only, with an intent record against crashes ([logbook](logbook.md)).
  - An edited, deleted or reordered entry breaks the chain (`tests/test_logbook_chain.py` `BrokenChainTests`). A truncated tail is found by the hash record or an outside anchor (`test_a_truncated_tail_is_found_by_the_hash_record_or_by_an_anchor`).
  - A logbook that fails its check stops helpers and goal runs (`tests/test_helpers.py` `test_tampered_or_unsealed_logbook_means_no_helper_runs_and_nothing_is_written`).
  - If the logbook cannot be written, a No stays No and a Yes becomes Ask me first ([rules](rules.md)).
- **What it does not stop:**
  - It shows an edit; it does not prevent one. Someone who replaces the logbook and its hash record together is found only by an anchor the owner keeps elsewhere.
  - It records ids and words, never a helper's text, so it shows that something was done, not what was said.

## Shared memory

- **Assets:** the context bundle (layer 1), `queue.md`, `drafts/`, the goal state under `.umwayi/goals/`.
- **Actors:** helpers reading and writing; the owner answering.
- **Trust boundary:** each file's own strict reader and writer.
- **What stops what:**
  - Private paths never go into a context bundle (`tests/test_memory.py` `BundleTests.test_private_never_in_bundle`).
  - `queue.md` is parsed strictly, and answering a queue item never lets a helper go on; only a Yes rule does (`tests/test_helpers.py` `test_answering_the_queue_item_does_not_let_the_helper_go_on`).
  - Goal state is written by the supervisor only. The guide and the tester must leave the tree unchanged or their run is void (`tests/goal/test_goalrun.py` `TesterTests.test_the_tester_that_changes_the_tree_voids_the_run`).
  - Edits under `/.umwayi/` are No for Claude Code (`cc-no-guard-edits`).
- **What it does not stop:**
  - `umwayi queue answer` has no terminal check (`umwayi/taskqueue.py`). A helper that can run it could close or answer a row; this does not start anything, but it can hide a question from the owner.
  - A draft can be wrong or misleading. The owner reads it.
  - A file a helper reads (a packet's context, a web page) can carry instructions. umwayi treats it as data in its own checks, but the helper may follow it.

## Apps

- **Assets:** the built-in helpers (Steward, social) and the owner's queue and drafts they touch.
- **Actors:** the helpers; the owner.
- **Trust boundary:** the helper base (`umwayi/helpers/base.py`): one rules check per step.
- **What stops what:**
  - Helpers draft only. A post, send or publish is No (`tests/test_helpers.py` `BaseStepTests.test_post_send_and_publish_types_are_no_for_helpers`).
  - No helper can set an approver (`tests/test_system.py` `CodeTests.test_no_helper_has_a_code_path_that_sets_an_approver`).
- **What it does not stop:**
  - Installable apps (W43) are designed, not built (`docs/agent-apps-design.md` on branch `w43-agent-apps-design`, not merged).
  - A helper's draft can still do harm if the owner publishes it unread.

## Drivers

- **Assets:** the hooks that sit between a platform and umwayi.
- **Actors:** Claude Code, Kiro, OpenCode, any stdin tool.
- **Trust boundary:** the adapter hook ([adapters](adapters.md)).
- **What stops what:**
  - A crash in the hook or in `umwayi check` blocks the call (`tests/adapters/test_claude_code.py` `CrashTests`).
  - The kill switch denies every call.
  - The root is given with `--root`, never taken from the platform's input.
  - OpenCode Code Mode has no Yes rule, so its calls are Ask me first and stopped by the first gate ([rules](rules.md)).
- **What it does not stop:**
  - A platform that runs a tool without calling the hook is not checked.
  - Some Kiro hook fields are not confirmed by Kiro's docs (KNOWN-LIMITS 21).
  - `cwd` reaches the rules from Claude Code only, and is what Claude Code reports (W57).

## Front door

- **Assets:** the starts of agents, the owner's logins, the local server.
- **Actors:** the owner typing commands; helpers; programs on the same machine.
- **Trust boundary:** `umwayi agent`, `umwayi up`, `umwayi serve`, the telemetry receiver.
- **What stops what:**
  - Every start asks `agent_run`, takes the run lock, runs the gate checks and reserves a budget (`agents._Run._steps`).
  - Claude Code starts only on a subscription login, and credential names are removed from its environment ([agent front door](agent-front-door.md); `tests/agents/test_agents_run.py`).
  - `umwayi serve` and the telemetry receiver listen on 127.0.0.1 only (`tests/serve/test_scenarios.py` `LoopbackOnly`; `tests/test_system.py` `CodeTests.test_no_module_imports_a_network_library`).
  - The owner commands of `umwayi goal` need a terminal on stdin and stdout (`tests/goal/test_owner_commands.py` `test_approve_without_a_terminal`; `tests/goal/test_cli.py` `test_the_owner_commands_without_a_terminal_are_2`).
- **What it does not stop:**
  - On main, a helper still inherits the owner's SSH agent (`SSH_AUTH_SOCK`). W64 removes it, on branch `w64-ssh-agent-env`, not merged when this was written.
  - The terminal check is a property of the process, not an identity. A pseudo-terminal passes it. A helper with a shell can make one (for example with `script`). The repo has no test for this.

## The supervisor

The repo's supervisor is the program `umwayi/goalrun.py`. It is deterministic and starts helpers only as `umwayi agent run`. In the owner's words, the system also runs with an AI session in the goal guide role that plans, checks results and picks the next step. That session is an AI and can be attacked: a goal text, a packet's context file, a web page or a tool output it reads can carry instructions.

What must hold, and whether it holds today:

| must hold | today | shown by |
| --- | --- | --- |
| its own actions go through the rules gate | **enforced** when it is started by umwayi: the guide runs through `agent run` (`agent_run`, `budget_check`, `goal_start`) and every tool call goes through the hook. **Not enforced** for a Claude session the owner opens outside umwayi: the repo cannot show whether that session has the umwayi hook | `umwayi/goalrun.py` `step_rules`; `adapters/claude_code/README.md` |
| it never approves its own Ask me first | **enforced in part.** Answering a queue item never lets a run go on; only a Yes rule does. `goal approve`, `answer` and `merged` need a terminal. **Not enforced:** a pseudo-terminal passes that check, `umwayi queue answer` has none, and no starter rule denies these commands to a helper | `tests/test_helpers.py`; `tests/goal/test_owner_commands.py`; [goals](goals.md) "Not built" |
| a hostile page or file cannot raise a budget | **enforced in part.** An approved budget is the hard cap; no rule or answer raises it (W9.R15.7), and `budget_check` is on the never list. **Not enforced:** an edit of `units.yaml` is Ask me first, not No, and is only logged | `umwayi/goalbudget.py`; `umwayi/rules.py` `NEVER_AUTONOMY` |
| it cannot sign | **not enforced on main.** The owner's SSH agent is in every helper's environment until W64 merges. Key files under `id_rsa` and `id_ed25519` names are No for Claude Code (`cc-no-secrets`); other agents (gpg-agent, a keyring) are not covered | `umwayi/agents.py` `claude_env`; `rules.yaml` |
| it cannot merge | **enforced for umwayi:** umwayi's git list has no merge and no push (`tests/goal/test_worktree.py` `ListGuardTests`), and a push to main is No for Claude Code (`cc-no-push-main`). **Not enforced** outside it: a shell `gh pr merge` is only Ask me first, and in the builder's sandbox the GitHub token is the owner's account | `umwayi/goalgit.py`; the W63 merge-ready design (branch `w63-merge-ready-design`, not merged) |
| it cannot change a rule | **enforced for `rules.yaml`** for Claude Code: an edit or a shell command that names it is No, and any change is logged before use. The Kiro and OpenCode starter rules guard the same files. **Not enforced** for `guidance.yaml` and `.kiro/steering/` (an edit is Ask me first, not No), or for a shell command that changes a file without naming it | `rules.yaml` `cc-no-guard-edits`, `cc-no-guard-shell`; `tests/test_rulelog.py` |

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-16 | A threat model per part, with the supervisor as an attackable AI; each control cited, each gap said | W67, the owner's request of Nov 16. |

## Open questions

1. **Deny the owner commands to helpers.** Should the starter rules make `umwayi goal approve|answer|merged|stop`, `umwayi queue answer` and `script` No for every platform? Recommendation: yes, as one rules change the owner approves, with the pinned starter rule hashes updated in the same pull request.
2. **A terminal check that a helper cannot fake.** Recommendation: keep the check, and add a typed one-time code the owner reads from a file only the owner's terminal session can see, or require the owner's signature as in W63. Start with the rules of question 1, which are cheap.
3. **Protect `guidance.yaml`, `units.yaml`, `agents.yaml` and `.kiro/steering/`.** Recommendation: add them to the guard lists (No for edits and named shell commands), as `rules.yaml` is, in the same rules change.
4. **The AI session outside umwayi.** Recommendation: the owner's Claude session in the guide role runs with the umwayi hook (`adapters/claude_code/README.md`) and its own `--root`, and the pull request that sets it up records that it does.
5. **Merge W64.** Recommendation: yes, before any goal runs unattended.
6. **A GitHub token per role.** Recommendation: give helpers a token without merge rights, so a merge needs the owner's own session. Until then, treat any GitHub action from a helper's session as the owner's.
7. **A sandbox.** Recommendation: not before Dec 3. Name it as the first item after, because every gap above that starts with "runs as the owner's user" closes only there.
