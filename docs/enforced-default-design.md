# Enforced by default (W78, design note)

## Purpose

The owner's words: enforcement is not cooperative but actually enforced, as the default. A user can switch to cooperative enforcement if they want. The helpers must be strongly guided. This is the design note of task W78. It turns the options of [enforcement.md](enforcement.md) (W41 A, B1, B2, C1, C2) into one product setting with a default, a fail closed rule, a platform table, a build order and a guidance design. **Nothing on this page is built.** Until the minimum profile of section 6 exists and one real enforced run has finished a goal, enforcement is cooperative today and enforced where built, and every page says so. Docs only: no code, rule, steering file, safety check, workflow or exit code changes with this note.

Sources: [enforcement.md](enforcement.md) (W41), [network-credentials.md](network-credentials.md) (W69), [untrusted-content.md](untrusted-content.md) (W68), [threat-model.md](threat-model.md) (W67), [enforce-audit-design.md](enforce-audit-design.md) (W62), [rules-library.md](rules-library.md) (W76), `umwayi/agents.py` (W64: `AGENT_SOCKET_ENV`, `kiro_env`, `claude_env`).

## Current state

Enforcement is cooperative today. umwayi checks an action only when something asks it: the hooks of Claude Code, Kiro and OpenCode, and umwayi's own commands. It refuses to start an agent it cannot gate (10.R6), passes an allow listed environment to the ACP and OpenCode programs, removes the SSH agent and credential names from every helper environment (W64), and checks the worktree after a goal run. It confines no helper process. Step 1A of the build order is built (Nov 17): the `enforcement` setting in `.umwayi/enforcement.yaml`, `umwayi enforce check` and `umwayi enforce set`, with the mode shown in the goal status line, the goal prompts and the start entry. Nothing is enforced yet: every part of enforced reads `refused` with its reason, and the pages still say enforcement is cooperative today and enforced where built. The guard lists, the deny rules and the terminal checks of step 1B are not changed. The full list of gaps is in [enforcement.md](enforcement.md) and [KNOWN-LIMITS.md](KNOWN-LIMITS.md).

## Product

umwayi-os runs by itself, with its own supervisor, and never assumes an outside guide. Every start of a helper goes through `umwayi agent run` or a goal run, so umwayi owns the launch, the environment, the confinement and the check after the run. Nothing in this design needs an AI guide, a person or a network service to work. The owner is the one person at a real terminal ([threat-model.md](threat-model.md)); the supervisor and every helper are not.

### 1. The mode

One setting, `enforcement`, with two values: `enforced` (the default) and `cooperative`.

- **Where it lives.** In a guard file the helper cannot write, `.umwayi/enforcement.yaml` in the root (the file name is fixed in task 1 of the build order). Under confinement the file is outside the writable folders. The file joins the W41 C1 watched list, so a change nobody explains is a finding. In `cooperative` mode, where nothing confines the helper, the file is protected by a deny rule and by C1 only, and the note says so.
- **Who switches it.** Only the owner, from a real terminal. Switching to `cooperative` is Ask me first (exit 3) from any context that is not the owner's terminal, with nothing changed. At the owner's terminal the command asks for a typed confirmation, writes the file and writes one logbook entry. The supervisor and the helpers can never switch it, and no rule can answer Yes to it.
- **Switching back** to `enforced` is allowed at any time and also writes one logbook entry. It needs no confirmation.
- **Narrow switches.** The owner may set `cooperative` for one agent in `agents.yaml` (`enforcement: cooperative` with a required `until:` date) or for one goal (in the goal's own file, with `until:`). When the date passes, the agent or goal is `enforced` again with no action. There is no silent global switch: a global `cooperative` is a visible, logged setting and is printed everywhere.
- **Where it is shown.** In the status line, in every goal packet, and in the start entry of every run (`enforcement: enforced` or `enforcement: cooperative (agent, until DATE)`). A reader of the logbook can always tell which mode a run had.

### 2. What enforced means

All of these, for a helper that umwayi starts:

1. **A launcher with a scrubbed environment and a run marker** (W41 A). W64 already removes the SSH agent names and the credential names. The build replaces "everything else is passed" with an allow list, `env_keep` per agent, and a `UMWAYI_RUN=<run id>` marker. The allow listed environment of W68 option 3 is built once, here.
2. **OS confinement.** For Claude Code, the platform sandbox (B1) with `failIfUnavailable`. For every helper, including Kiro and OpenCode, a confined process (B2): Landlock on Linux, Seatbelt on macOS, with the broker below so the guard files are protected.
3. **Detect after every run** (C1 watched files, C2 tool calls no hook checked). A finding stops the task.
4. **Network off, or on an allow list, with scoped credentials** the owner hands over once per run (W69 options 1, 2 and 4). A helper holds no credential the owner did not hand over.
5. **Ask me first after an untrusted read** (W68 option 2): an action after external content was read that touches a secret, the network or a rule file is Ask me first, and Ask me first beats the owner's Yes rules.

Items 1 to 5 are the whole of "enforced". An item that cannot be set up on this machine is not skipped; see section 3.

### The broker (design)

The problem. Inside a confinement the hook must still write the logbook and read the rules. If those are writable by the helper's process, the helper can edit them. The tamper check and the chain show an edit; they do not prevent one. So the guard files must be writable only by a process outside the confinement.

The design. The broker is a separate small process, written as its own note first (Q6) and built after it. In a goal run the supervisor starts it before the helper. It is a standard library Python process of a few hundred lines.

- **Outside the confinement.** The broker is not confined. It holds the only write access to `LOGBOOK.md`, `LOGBOOK.record`, `.umwayi/` and the guard files (`rules.yaml`, `autonomy.yaml`, `agents.yaml`, `units.yaml`, `guidance.yaml`, `.kiro/steering/umwayi`, the tools folder). The confined helper has read access to what it needs and write access to the worktree, its own config and cache folders and one private temporary folder.
- **One channel.** The broker and the confined process share one inherited socket pair (a file descriptor passed at start). There is no socket path on disk to guess or replace. The hook, which runs inside the confinement, sends the one request it already makes (`umwayi check`) and gets the verdict back. The broker runs the check and writes the logbook entry itself.
- **A fixed set of requests.** `check`, `log` (a fixed entry shape, names from fixed lists, never a value), `answer_status` (read only). The broker refuses everything else, and a refusal is a log entry. It never runs a command for the helper, never reads a file the helper names, and never passes back file contents.
- **A request carries the run id.** The run id was made by the supervisor and is in the broker's table. A request from a run that is not in the table is refused.
- **If the broker dies.** The hook gets no answer, and no answer is No (fail closed). The supervisor sees the broker end and stops the task with a cause word.
- **What it does not do.** It does not make the owner's commands safe. The commands that change a rule, an approval or a budget stay owner only, and are denied to helpers by the rules change of build step 1.

### 3. Fail closed

If enforced cannot be set up for a helper on this machine, the start is refused: exit 2, "not confined", with a reason from a fixed list (`unavailable`, `kernel`, `dependency`, `profile`, `platform`, `broker`, `network`). The message names the switch ("set `enforcement: cooperative` for this agent with an `until` date, at your terminal"). It never falls back to `cooperative` by itself, and never starts the helper first and confines later.

A read only command, `umwayi enforce check`, prints what this machine can enforce, per configured agent: the platform, each of items 1 to 5 as `ready` or `refused (reason)`, and the mode in force. It writes nothing, starts nothing and reads no credential.

### 4. Platforms

| platform | enforced | not enforced | note |
| --- | --- | --- | --- |
| Linux | A, C1, C2 (Claude Code), B1 (needs `bubblewrap` and `socat` that the owner installs), B2 by Landlock (kernel 5.13 or later with Landlock on; TCP rules need ABI 4, kernel 6.7 or later) | Reads of `$HOME` outside the allow list are refused. Network by host name is not enforced without a proxy (decided: none in the first build). | CI runs on Linux and tests B2 there. |
| macOS | A, C1, C2 (Claude Code), B1 (built in), B2 by Seatbelt | Apple marks Seatbelt (`sandbox-exec`) deprecated and does not document the profile language. Whether a profile allows the Keychain sign in of Claude Code has not been checked. | CI has no macOS. Step 7 of the build order needs the owner's real check on his Mac, with steps and expected output. |
| Windows | nothing | everything | Out (F6): Linux and macOS now, Python 3.10 minimum. Said in the limits. |

A helper whose platform cannot be confined is refused in `enforced` mode unless the owner sets `cooperative` for that agent. Claude Code has B1. Kiro and OpenCode have no platform sandbox like B1 (the repo records none), so they need B2 or the per agent switch.

### 5. Strongly guided helpers (both modes)

Guidance is not enforcement. A model can ignore text in its context, and umwayi cannot see whether it read the text. So guidance lowers how often the helper hits a rule. It is never counted as a rule. Each item below is a fixed rule of umwayi, not a hope:

- **(a) The goal packet restates the rules in force, the scope card and the mode** at the start of every task, in a fixed order and fixed words, so the helper's context begins with them.
- **(b) The `guidance.yaml` entries are chosen for the task by a fixed rule** (by the task's allowed paths and action types, not by a model) and injected. W62 binds each advise entry to a deterministic check or a stated reason, so a piece of advice with neither cannot ship.
- **(c) One task per session**, with the W42 handoff note, so a long session does not drift from the packet.
- **(d) Every refusal carries the reason and the allowed next step, in one fixed shape:** `refused: REASON. Allowed next: STEP.` Both come from fixed lists, never from the helper's input.
- **(e) `goalwatch` reads repeated refusals as a signal.** The same refusal three times in one task is a loop, and the task moves to `needs owner` with its cause word.
- **(f) A check after the work by a different agent** (W73), so the writer does not mark its own work.
- **(g) Counts only, in the logbook:** refusals, Ask me first and detect after findings per task. A count is not proof of obedience: a helper with zero refusals may have never tried, and the count says nothing about what was not asked.

### 6. The default flip

It ships as `enforced`. Until the minimum profile exists (A, C1, B1 for Claude Code, the mode switch and `umwayi enforce check`) and one real enforced run (W40) has finished a goal, every status line, README line and post says enforcement is cooperative today and enforced where built. No post says sandboxed or enforced before that run. A test fails if the README or `what-it-is.md` says "enforced by default" while the build record shows that run missing.

### Build order

Each item is its own task. None starts before Dec 3: the Kiroween freeze is Nov 29 to Dec 2 and the submission is Dec 3. This note is allowed before.

1. **Mode setting and the rules.** The `enforcement` setting and its guard file, `umwayi enforce check`, the refusal wording with a next step (5d), and the one owner approved rules change: deny the owner's commands to helpers; guard lists for `guidance.yaml`, `units.yaml`, `agents.yaml`, the tools folder and `.kiro/steering/umwayi`; a terminal check on `umwayi queue answer`. The task says how the pseudo-terminal case and sessions opened outside umwayi are closed, or stay limits (open question 1).
2. **W41 A**: scrubbed environment, run marker, `env_keep`, with the W68 allow listed environment built once here.
3. **W41 C1**: the watched list, which includes the mode file.
4. **W41 B1**: the Claude Code platform sandbox.
5. **The broker**: its own design note first ([enforcement-broker-design.md](enforcement-broker-design.md), 2026-11-22), then the build.
6. **B2 on Linux**, tested in CI.
7. **B2 on macOS**, after the owner checks on his Mac.
8. **W41 C2**: tool calls no hook checked.
9. **Guidance items (a) to (g)**, with W62 and W42.
10. **Flip the default** with the README, `what-it-is.md`, KNOWN-LIMITS, the narrative and the write-up in one release.

### Build-time note

Kiro web sessions cannot be confined or inspected by umwayi-os. The outside guide checks this note by reading it and checks the tests by running them. That is a fact about how the note was written, not about the product: the product never assumes a guide.

## Exit codes

Only 0, 2, 3 and 64.

- **`umwayi enforce check`:** 0 every configured agent can be enforced as its mode asks; 2 at least one cannot (with the fixed reason) or an unexpected error; 3 the mode file is missing, or does not match the last mode entry in the logbook (the owner must look); 64 a malformed `agents.yaml`, mode file or `until` date.
- **`umwayi enforce set`** (the switch): 0 done and logged; 3 Ask me first (not at the owner's terminal, or the typed confirmation was not given), with nothing changed; 2 refused or an unexpected error; 64 usage, or a missing or past `until` for `cooperative`.
- **`umwayi agent run` and the goal commands:** 2 for "not confined" with a reason from the fixed list, as for any refused start. A detect after finding is a task state (`needs owner`), not a new exit code.
- **The broker:** no exit code of its own. A refused request is a `check` verdict (2 or 3) at the hook.
- Never 1.

## A planted fault for every rule

Each rule below gets a test, and a planted fault the test must catch. Real child processes, a temporary root, no network, standard library only. Rules W78.R1 to W78.R14 are the lines added to the spec (see the next section).

| rule | what it says | planted fault the test must catch |
| --- | --- | --- |
| W78.R1 | the default mode is `enforced`, and a missing mode file is `enforced` | default read as `cooperative`; a missing file read as `cooperative` |
| W78.R2 | only the owner at a terminal switches to `cooperative`; elsewhere it is exit 3 with nothing changed | the switch accepted from a pipe; the switch accepted from a helper's environment; the file written before the confirmation |
| W78.R3 | a switch writes one logbook entry, and every start entry, goal packet and status line shows the mode | a switch with no entry; a packet that omits the mode; a status line that shows `enforced` while the file says `cooperative` |
| W78.R4 | `cooperative` per agent or goal needs `until`, and expires with no action | an `until` ignored; an expired date still cooperative; a global switch made by a narrow one |
| W78.R5 | the mode file is on the C1 watched list | the file left off the list; a changed mode file not a finding |
| W78.R6 | the environment is an allow list plus `env_keep`, with the run marker | a planted `S78_SECRET_TOKEN` reaches the child; `env_keep` read as values; the marker left out |
| W78.R7 | for Claude Code the platform sandbox is on, with `failIfUnavailable` and `allowUnsandboxedCommands: false` | `failIfUnavailable` left out; a missing `bwrap` started anyway |
| W78.R8 | in `enforced` mode a helper is confined (B2) and only the broker writes the guard files | the ruleset not applied before `exec`; `$HOME` writable; a write to `rules.yaml` from the helper that succeeds; a refusal turned into an unconfined start |
| W78.R9 | the broker accepts only fixed requests from a run id in its table | an unknown request type served; a run id not in the table served; a request that returns file contents; the broker's death read as Yes |
| W78.R10 | a detect after finding stops the task (C1, C2) | a finding that does not stop the next step; a missing telemetry stream read as "all checked" |
| W78.R11 | network off or an allow list, with a credential only if the owner handed it over | a metadata address reachable; a credential variable not handed over reaches the child; a token written to a file or an entry |
| W78.R12 | an action after an untrusted read that touches a secret, the network or a rule file is Ask me first | the marker lost between two calls; an owner Yes rule that beats the Ask me first |
| W78.R13 | a start that cannot be enforced is refused (exit 2, fixed reason), never started cooperative | a fallback to `cooperative`; a reason outside the fixed list; the helper started before the refusal |
| W78.R14 | `umwayi enforce check` writes nothing and exits only 0, 2, 3 or 64 | a file written by the check; an exit code 1; a check that says `ready` when the probe failed |
| W78.R15 | guidance (a) to (g) is fixed text and fixed rules, with counts only in the logbook | a packet missing the rules in force; a refusal without a next step; guidance chosen by a model; a value or a command in a count |
| W78.R16 | no page says enforced or sandboxed before the minimum profile and one real run exist | a README line "enforced by default" while the build record has no real run |

A whole system scenario in `GoalWholeSystemTests` runs one task in `enforced` mode with a fake helper that tries to write `rules.yaml`, read `~/.ssh` and connect out, and expects three refusals, three counts and no change.

## Spec lines it would add or change

- A new section **W78.R1 to W78.R16** after W41.R6 in `requirements.md`, one rule per row of the table above.
- `docs/what-it-is.md`, the line "Not a sandbox. It does not stop a process that never asks it." and the line "No enforcement on a process that skips the hooks. Enforcement is cooperative today ...": each gets a sentence naming the default and what stays cooperative. Both change only in build step 10.
- `README.md`: one line that says enforcement is cooperative today and enforced where built, until the flip.
- 10.R2 (`agents.yaml`): `enforcement` and `until` per agent, and `env_keep`.
- 10.R6.1 and W9.R7.4 (the agent can be gated): add "and, in `enforced` mode, confined".
- 10.R12.6 and 10.R12.13: the environment is the allow list of W41.R2 plus `env_keep`.
- W9.R6.2: the cause words `guard_file_changed`, `unchecked_tool_call` and `not_confined`.
- The goal packet (goalpacket): the `enforcement` field and the restated rules of 5(a).
- `docs/exit-codes.md`, `docs/goals.md`, `docs/security.md` and `docs/enforcement.md`: the new commands, the mode and a link to this note.
- A limits part per build step, written when it is built.

## What it does not prove

- **Not that the helper obeyed.** Guidance is text the model may ignore. A count of refusals is not proof of obedience.
- **Not that every effect is stopped.** Inside the folders the helper may write, and inside the network it may use, it can do harm that no check sees.
- **Not that a confinement has no hole.** A kernel or Seatbelt bug, a profile mistake, or a vendor's own connection (which must be allowed) can leave one.
- **Not macOS.** Seatbelt is deprecated and CI has no macOS, so nothing about macOS is proved until the owner's check.
- **Not an agent the owner starts by hand,** or a Kiro session opened outside umwayi. Their effect on a watched file is seen after the next umwayi run starts, and no more.
- **Not that the owner's terminal is the owner.** A helper that fakes a pseudo-terminal is a W67 threat that stays a limit until confinement is built (open question 1).
- **Not that the numbers are right on this machine until `umwayi enforce check` ran there.** The table in section 4 is what the docs say, not what this machine does.
- **Not Kiro web.** Kiro web sessions cannot be confined or inspected, so nothing here was tested against them.

## Decided

| # | Decision |
| --- | --- |
| Q1 | The default flips to `enforced` with the minimum profile (A, C1, B1 for Claude Code, the mode switch, `umwayi enforce check`) and one real enforced run (W40) that finished a goal. |
| Q2 | A helper that cannot be confined in `enforced` mode is refused, and the message offers the per agent `cooperative` switch. |
| Q3 | Only the owner at the terminal switches, per agent or per goal with an expiry, logged and shown everywhere. |
| Q4 | Linux and macOS now, Windows out (F6), Python 3.10 minimum. Said in the limits. |
| Q5 | A detect after finding stops the task. |
| Q6 | The broker is a separate small process, designed first as its own note. |
| more | No proxy server in the first network build: an allow list only. A scoped GitHub token without merge right is approved separately. Restarts default to 0, and `helper_restart` stays on the never list. |

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-17 | Design note only; Q1 to Q6 and the proxy, token and restart choices recorded as decided. | The owner's words of Nov 17 for W78. |

## Open questions

1. **The pseudo-terminal case and sessions opened outside umwayi.** The owner terminal check for `umwayi enforce set` and `umwayi queue answer` can be fooled by a helper that opens a pseudo-terminal, and a session the owner opens outside umwayi has no run marker. **Recommendation:** accept a request only when the controlling terminal's session is not a descendant of a process that carries a `UMWAYI_RUN` marker, and when the caller's environment has no marker. Under B2 the helper cannot reach the owner's terminal device at all, which closes the case. Until B2 is built, list it as a known limit. Build step 1 states which half is closed and which stays a limit.
2. **Network by host name, with no proxy.** Landlock limits TCP by port (ABI 4), not by host. Seatbelt can limit by host. So on Linux an allow list by host name is not enforced in the first build, though Kiro and Claude Code must reach their vendor. **Recommendation:** in the first build `enforced` gives each helper either no network (testers, read only helpers) or port 443 only (builders), and the limits part says that any host on 443 is reachable. Refuse with reason `network` when a helper needs more than that and the kernel has no ABI 4.
3. **Landlock below ABI 4.** Many kernels have Landlock but not the TCP rules. **Recommendation:** file confinement needs ABI 1 or later. A helper that must have no network on an older kernel is refused (`kernel`), not started with the network open.
4. **How long may `cooperative` last?** The `until` date has no limit today. **Recommendation:** a limit of 30 days per agent or goal, a default of 7, and a status line that counts the days left. A longer time is a new switch at the terminal.
5. **The mode file location.** `.umwayi/enforcement.yaml` is inside the root, so a helper that is not confined (in `cooperative` mode) can reach it. **Recommendation:** keep it in the root so it moves with the project, and rely on the deny rule and C1 in `cooperative` mode. Under B2 the broker alone writes it.
