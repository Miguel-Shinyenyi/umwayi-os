# Enforcement beyond cooperative

## Purpose

This page is the design note of task W41: how umwayi could hold an AI helper to the rules when the helper, or a program it runs, does not ask. It compares three options: a launcher with a scrubbed environment (A), optional confinement by the operating system (B), and a check after each run (C, detect-after). **Nothing on this page is built.** The owner picks an option, several or none, before any code is written. Until then the system works as [what-it-is.md](what-it-is.md) says: enforcement is cooperative.

## Current state

### What is cooperative today

umwayi checks an action only when something asks it. Today the askers are the layer 9 hooks inside Claude Code, Kiro and OpenCode, which run `umwayi check` before each tool call, and umwayi's own commands (`agent run`, `goal`, jobs, workflows), which ask before they start anything. Cooperative means the check holds only while the platform runs the hook and the helper works through tool calls. Two kinds of gap follow, and the repo already records each of them:

- **A hook can be skipped or can see less than happens.**
  - A rule matches the text of one tool call, not what the command does. A script written first and run later, a variable, or another spelling gets past a text rule ([KNOWN-LIMITS](KNOWN-LIMITS.md) item 12).
  - The programs a checked command starts are not checked one by one. A `python3 -m unittest` that is allowed may write, read and connect as it likes.
  - The platform decides whether the hook runs:
    - A managed Claude Code policy can turn the hook off, and umwayi cannot see it (item 30).
    - Kiro's docs do not say what Kiro does when the hook cannot start or times out (items 22 and 42).
    - In an ACP session the hook may not run at all (item 53).
  - A helper that can write `.kiro/hooks`, `rules.yaml` or the logbook can try to turn off its own guard. The example rules deny that by text only (item 15).
- **An agent can run outside the gate.**
  - umwayi refuses to start an agent it cannot gate (10.R6), but it can only refuse its own starts. The owner, or a program of the owner, can run `claude` or `kiro-cli` by hand with no hook.
  - Kiro gets the rest of umwayi's environment (item 88). So do Claude Code's `agent run` and cli chat, less the credential names of 10.R12.6. Any secret in the owner's shell reaches the helper and every command it runs.

What umwayi does already, and keeps in every option: it fails closed (a start that cannot be gated is refused, exit 2), it passes an allow-listed environment to the ACP and OpenCode programs (10.R11.9, 10.R13.4), and in a goal run it checks the worktree after the builder exits: a commit, a clean tree, only the allowed paths (W9.R8.3). That last check is a detect-after in the small. It sees what landed in the worktree, nothing outside it.

### What the real runs of Nov 15 showed

This section uses only what the repo records: the status parts, the limits parts, `docs/goals.md` and `adapters/NOTES-layer10.md`. The logbooks of those runs (`LOGBOOK.md`, `LOGBOOK.record`) are kept out of git by `.gitignore`, so they are not in the repo and were not read.

| what the repo records | where | what it says about bypass |
| --- | --- | --- |
| A real Claude Code 2.1.322 run on the owner's Mac sent token counts as `asDouble`. umwayi refused the shape, so it stopped the run (exit 2) and settled it at the full reservation | status part W45, limits part W45, `adapters/NOTES-layer10.md` | Nothing ran unchecked. The budget path failed closed. |
| A Kiro hook file named the root as `/var/...` while the resolved root is `/private/var/...`. The gate check said the agent is not gated, and the start was refused | `docs/goals.md` (First goal in a new folder), status part W46 | The gate refused rather than ran ungated. It also shows that the check is a text match on the hook file (item 32): umwayi read a file, it did not see Kiro load the hook. |
| In the first real goal runs by Claude Code, a Python program the helper ran left `__pycache__` in the worktree, so the task failed with `tree_not_clean` | status part W55a, limits part W55a | A program started by a checked command wrote files no rule was asked about. The scope check after the run found them. This is the one recorded case of an effect that went past the per-call check, and the after-run check caught it. |
| `kiro-cli whoami` takes about 10 s on a Mac (one report); its limit went from 15 s to 30 s, and no answer is still a refusal | status part W59, limits part W59 | Nothing ran unchecked: no answer means no start. |

What the repo does not record: any tool call that ran with no `umwayi check` entry, any hook that did not run, and any agent started outside umwayi. Not seeing these is not evidence that they did not happen. Nothing umwayi has today can count tool calls that never reached a hook. Option C is the part that would.

### Option A: a launcher with a scrubbed environment

Every helper start (`agent run`, the goal runs, `agent chat`) gets an allow-listed environment, the same kind the ACP chat already uses. A short list of names is passed, each only if set. Every other name is left out. The owner may add names per agent in `agents.yaml` (a new `env_keep:` list of plain names, never values). Each start also gets a run marker, `UMWAYI_RUN=<run id>`. The hooks then know which umwayi start a call belongs to, and a Kiro session that the owner started by hand can be told apart (see open question 3).

- **Stops:**
  - A secret in the owner's shell (a cloud key, a token, a database address) reaching the helper and every command it runs, unless the owner lists that name.
  - A start-time setting smuggled in by the environment (`NODE_OPTIONS`, `PYTHONPATH`, the `*_PROXY` names the owner did not keep).
  - With the marker: hook entries that cannot be tied to a umwayi start.
- **Does not stop:** secrets on disk (`~/.aws/credentials`, `~/.ssh`), what a command does, network use, a hook that does not run, or an agent the owner starts by hand.
- **Cost on a Mac and on Linux:** the same on both. Standard library only, no new process, no measurable time.
  - The risk is breakage. A helper or a tool it runs may need a name that is left out, for example `SSH_AUTH_SOCK` for a `git push`, which a builder must not do anyway, or a language toolchain's variables.
  - The terminal chat needs the owner's terminal names (`TERM`, `COLORTERM`), which the list keeps.
- **Adds to the spec:** the allow list for Claude Code `agent run` and the cli chat and for every Kiro start (it replaces the "everything else is passed" line of 10.R12.6 and `kiro_env`), `env_keep` in `agents.yaml` (10.R2), the run marker, and one new limits item for what an allow list cannot cover.

### Option B: optional OS confinement

The owner turns it on per agent (`confine: on` in `agents.yaml`). Off by default. When it is on and confinement cannot be set up, the start is refused (exit 2, "not confined"), never run unconfined. There are two ways to do it, and they can be combined:

- **B1, the platform's own sandbox.** Claude Code has a sandbox for its shell commands and the programs they start. It uses Seatbelt on macOS and `bubblewrap` with `socat` on Linux. umwayi would add `"sandbox": {"enabled": true, "allowUnsandboxedCommands": false, "failIfUnavailable": true}` to the inline settings it already passes, with write access only to the worktree. By Claude Code's docs, its built-in file and web tools, its hooks, its MCP servers and a command the owner types stay outside that sandbox ([Claude Code sandboxing](https://code.claude.com/docs/en/sandboxing)). The repo records no sandbox setting for Kiro or OpenCode, so B1 is Claude Code only until their docs show one.
- **B2, umwayi confines the whole helper process.** On macOS: `sandbox-exec` with a profile umwayi writes (Seatbelt ships with macOS. Apple marks `sandbox-exec` as deprecated, and its profile language is not documented by Apple). On Linux: Landlock, set up with `ctypes` (standard library) in the child before it runs the helper, with no root and no install. It needs a kernel of 5.13 or later and Landlock turned on, and TCP rules need ABI 4 (kernel 6.7 or later) ([landlock(7)](https://man7.org/linux/man-pages/man7/landlock.7.html)). Every process the helper starts inherits it, hooks included.
- **Stops:**
  - Writes outside the allowed folders by any process the helper starts, including a script written first and run later and the `__pycache__` kind of write. The allowed folders are the worktree, the helper's own config and cache folders and a private temporary folder.
  - With B2 on macOS, and with B1, reads of named folders (`~/.ssh`, `~/.aws`, `~/.gnupg`). Landlock lists what may be read, so on Linux reads of `$HOME` are refused except for what is listed.
  - Network, except where the profile allows it (Seatbelt; Claude Code's proxy; Landlock only TCP and only on ABI 4).
- **Does not stop:**
  - What the helper does inside the folders it may write.
  - The helper's own connection to its vendor, which must be allowed.
  - With B1: Claude Code's Read, Edit, Write and Web tools, and its hooks (the per-call rules still cover those).
  - With B2: the hook inside the confinement still has to write `LOGBOOK.md` and `.umwayi/`. If those are writable, the helper can write them too. The tamper check and the chain show an edit; they do not prevent one. B2 needs a broker (open question 2) before it can protect the guard files.
  - An agent the owner starts by hand.
- **Cost on a Mac:**
  - B1 needs nothing new.
  - B2 relies on a tool Apple marks as deprecated: a macOS update can change or remove it, and every macOS version needs the owner's real check.
  - A Seatbelt profile that blocks what a helper needs breaks its sign-in. Claude Code keeps its credentials in the Keychain, and whether a profile umwayi writes allows that has not been checked.
  - CI runs on Linux only, so no macOS confinement is tested in CI.
- **Cost on Linux:**
  - B1 needs `bubblewrap` and `socat` installed by the owner. On Ubuntu with its AppArmor rule for user namespaces it may also need a profile, which needs root. umwayi never installs or configures either. It only checks for them and refuses when they are missing.
  - B2 needs a kernel with Landlock turned on. Ubuntu has had it on since 22.04 by [one guide](https://freecodecamp.org/news/how-to-sandbox-a-linux-process-with-landlock-no-root-required); the repo has not checked this. A kernel without it means a refusal while `confine: on`.
  - About two days of build, most of it the profile, the refusal paths and the real checks.
- **Adds to the spec:**
  - A check in 10.R6.1: confinement is ready when asked for.
  - A start step in W9.R7, before the child.
  - `confine` in 10.R2.
  - The settings of B1 in the one `claude_settings()` template.
  - New limits items for what is outside the boundary.

### Option C: detect-after

After every helper run, umwayi compares what it can see with what was checked. Two parts:

- **C1, watched files.** Before the start and after the end, umwayi takes the SHA-256 of a fixed list of files: `rules.yaml`, `autonomy.yaml`, `agents.yaml`, `units.yaml`, `umwayi.json`, `guidance.yaml`, the Kiro hook files of 10.R6.2, the Claude Code settings files umwayi knows (`~/.claude/settings.json`, the project's `.claude/settings*.json`), `.git/config` and `.git/hooks/` of the root, and the root's `.umwayi/` files other than the ones umwayi itself writes during a run. A change that no umwayi entry of the run explains is a finding. The list is fixed in code, the file contents are hashed and never kept, and paths are named only from that fixed list.
- **C2, tool calls the platform reports and no hook checked.** Claude Code already sends `claude_code.tool_result` and `claude_code.tool_decision` events to umwayi's receiver on 127.0.0.1 during a run. Each event carries `tool_name`, and a `tool_use_id` that matches the id the hook gets ([Claude Code monitoring](https://code.claude.com/docs/en/monitoring-usage)). umwayi would keep only the tool name and the id, would have the hook add the id to its check entry, and after the run would list every reported call with no check entry. `OTEL_LOG_TOOL_DETAILS` stays unset, so no command or path arrives. Kiro sends umwayi nothing, so C2 is Claude Code only.
- **What a finding does:**
  - It writes one logbook entry and one queue row.
  - In a goal run, the task moves to `needs owner` with a new cause word, for example `guard_file_changed` or `unchecked_tool_call` (reason `unclear`).
  - It never undoes a change and never stops another goal.
- **Stops:** nothing as it happens. It turns a silent bypass into a visible one, at the end of the run. A changed guard file stops the goal at the next step instead of letting the next run trust it.
- **Does not stop:**
  - The effect itself (a file already sent, a command already run).
  - A change to a file not on the list.
  - A change that is made and undone within the run.
  - A run whose telemetry did not arrive. C2 then reports that it cannot tell, and never says "all checked".
- **Cost on a Mac and on Linux:** the same on both, standard library only.
  - C1 hashes a few dozen small files twice per run.
  - C2 reuses the receiver and adds a match. The receiver must keep one more event kind, which is a change to the budget governor's reader.
  - About one day of build.
- **Adds to the spec:**
  - The watched list and its finding (new W41 items).
  - The two cause words (W9.R6.2, goalpacket).
  - The hook's `tool_use_id` field for Claude Code (layer 9).
  - The event kinds the receiver keeps (B.R2).

### The comparison

| | A launcher, scrubbed environment | B1 platform sandbox | B2 umwayi confines the process | C detect-after |
| --- | --- | --- | --- | --- |
| a secret in the owner's environment | stopped unless kept by name | not stopped (inherited) | not stopped | not seen |
| a write outside the worktree by a program a command starts | not stopped | stopped (shell commands) | stopped | seen after, for watched files only |
| a read of `~/.ssh` or `~/.aws` | not stopped | stopped by a deny list | stopped (Linux: by an allow list) | not seen |
| a helper changes its own guard file | not stopped | stopped for shell commands, not for the Edit tool | not stopped until a broker exists | seen after |
| a tool call that no hook checked | not seen | not seen | not seen | seen after (Claude Code only) |
| an agent the owner starts by hand | not stopped | not stopped | not stopped | its effect on a watched file seen after the next umwayi run starts |
| platforms | all | Claude Code | all | C1 all, C2 Claude Code |
| Mac | nothing new | built in | deprecated tool, needs real checks | nothing new |
| Linux | nothing new | owner installs `bubblewrap` and `socat` | kernel 5.13+ with Landlock | nothing new |
| breakage risk | medium (missing names) | low to medium | high (sign-in, toolchains) | low (false findings) |
| build | about 0.5 day | about 1 day | about 2 days, plus the broker | about 1 day |

### What each option logs

Every entry has a fixed shape. It holds names from fixed lists and counts, never a value, a command, a path from the helper or file contents.

- **A:** the start entry gains `environment: N names passed, M left out` (counts only; never the names left out, which could hint at what the owner uses).
- **B:** the start entry gains `confinement: claude-sandbox`, `seatbelt`, `landlock ABI N` or `off`. A refusal is `Refused agent NAME: not confined (REASON)`, with REASON from a fixed list (`unavailable`, `kernel`, `dependency`, `profile`).
- **C:** one entry per run with findings: `Detect after run RUN: watched files changed: rules.yaml, .kiro/hooks/umwayi.json` (names from the fixed list only) and `tool calls reported with no check: Bash 2, Write 1` (tool names from the reported list, cut to the shape of the action types). A run with no finding writes nothing new. A run whose telemetry did not arrive says `tool calls could not be compared`.

### What no option does

- No network. C2 uses the receiver on 127.0.0.1 that exists today. Nothing is fetched, sent or checked online.
- No install. umwayi never installs `bubblewrap`, `socat`, a package or a profile into the system. It checks for them and refuses.
- No root, no `sudo`, no change to system settings (no `sysctl`, no AppArmor profile, no launch daemon).
- No new Yes. Every option only refuses more or reports more. Fail closed stays: an option that is on and cannot work refuses the start.
- No reading of conversations, prompts or file contents. C1 hashes bytes and keeps only the hash. C2 keeps a tool name and an id.
- Nothing outside the root is written, except the private temporary folder of one run.

### The spec lines each option adds or changes

- **Every option:**
  - `docs/what-it-is.md` line 24 ("Not a sandbox. It does not stop a process that never asks it. ...") and line 41 ("No enforcement on a process that skips the hooks. Enforcement is cooperative today ...") get a second sentence naming what the chosen option adds and what stays cooperative.
  - A new section **W41.R1 to W41.R6** after W44.R1 in `requirements.md`. W41.R1 is what never changes (the list above).
- **A:**
  - 10.R12.6, the bullet "Everything else is passed as today (the terminal chat needs the owner's environment)." becomes "The environment is the allow list of W41.R2, plus the names in the agent's `env_keep`."
  - 10.R12.13 (Kiro) gets the same sentence in place of "umwayi's environment minus `KIRO_API_KEY`".
  - 10.R2 gains `env_keep`.
  - New W41.R2.
- **B:**
  - 10.R6.1 gains, after the Kiro hook file check: "when the agent has `confine: on`, the confinement of W41.R3 is ready".
  - W9.R7.4 (the agent can be gated) gains the same check, and W9.R7.8 runs it again for the worktree before the child starts.
  - 10.R5.7 keeps its never list, and B1 adds `allowUnsandboxedCommands: false` to the one settings template.
  - New W41.R3 (B1) and W41.R4 (B2).
- **C:**
  - W9.R6.2 gains the cause words `guard_file_changed` and `unchecked_tool_call` (both `needs owner`, reason `unclear`).
  - W9.R8.3 gains "and the detect-after of W41.R5".
  - B.R2 gains the two event kinds the receiver keeps.
  - Layer 9 gains the hook's `tool_use_id` for Claude Code.
  - New W41.R5 (C1) and W41.R6 (C2).

### The tests each option needs

Each rule gets a test and a planted fault that the test must catch. Real child processes, a temporary root, no network, standard library only.

- **A:**
  - A fake helper prints the names of its environment. A planted `S41_SECRET_TOKEN` never appears; a name in `env_keep` does.
  - Planted faults: the allow list skipped (the whole environment passed), `env_keep` read as values, the marker left out.
  - Also: `env_keep` with a bad name is refused at validate (64).
- **B1:**
  - The settings template holds the three sandbox keys and no `allowUnsandboxedCommands: true` (a source and a golden test).
  - On Linux, a refusal when `bwrap` is not on PATH.
  - Planted faults: `failIfUnavailable` left out; a missing dependency started anyway.
- **B2:**
  - On Linux CI with Landlock, a fake helper's child writes outside the worktree and gets `EACCES`, and writes inside succeed.
  - A kernel without Landlock (faked by the probe) is refused with `not confined (kernel)`.
  - Planted faults: the ruleset not enforced before `exec`, `$HOME` allowed for writes, a refusal turned into an unconfined start.
  - macOS has no CI. It needs the owner's by-hand check, written as steps with expected output.
- **C1:**
  - A fake builder runs a child that edits `rules.yaml`. After the run the task is `needs owner` with `guard_file_changed`, there is one entry and one queue row, and the file contents are in no record.
  - Planted faults: a file of the list not hashed, the second hash taken before the child ends, a finding that does not stop the next step.
- **C2:**
  - A fake telemetry stream reports three tool calls while the hook checked two. The finding names one call with no check.
  - A stream that never arrives gives "could not be compared", never "all checked".
  - Planted faults: matching by count instead of by `tool_use_id`, a missing stream read as zero calls, a tool parameter kept.
- **Every option:** the goal and agent commands give only 0, 2, 3 and 64, and a whole-system scenario in `GoalWholeSystemTests` runs a task with the chosen option on.

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-16 | Design note only; the owner picks an option before anything is built | W41 in tasks.md, the owner's task. |

## Open questions

1. **Which option first?** **Recommendation:** C1 and A first, in one task each.
   - C1 sees the one thing the cooperative gate cannot cover at all, a helper or a hand-run agent changing a guard file, on every platform.
   - A closes the environment gap the repo already lists (item 88) at almost no cost.
   - Then B1 for Claude Code goal runs, which stops the `__pycache__` kind of write at its source.
   - B2 last, and only with a broker.
2. **B2 and the guard files:** inside a confinement the hook must still write the logbook. **Recommendation:** do not build B2 until a small broker exists: a umwayi process outside the confinement that takes `umwayi check` requests over one Unix socket and writes the logbook itself. Write that broker as its own design task.
3. **The run marker and Kiro sessions umwayi did not start:** umwayi-os runs by itself: its own supervisor starts every helper through `umwayi agent run`, so every session umwayi starts carries the `UMWAYI_RUN` marker of A. The global Kiro hook file also runs for any Kiro session on the machine that umwayi did not start, and such a session has no marker. With A, the hook could answer No to a call without the marker. **Recommendation:** log such a call as `outside a umwayi run`, and let the owner choose with one rule whether it is No. umwayi's own runs are not affected either way, because they always carry the marker.
4. **C findings in a goal run:** stop the task, or only report? **Recommendation:** stop it (`needs owner`, reason `unclear`). A goal must not build on a run whose guard files changed.
5. **The watched list:** fixed in code, or extended by the owner? **Recommendation:** fixed in code, with an owner list added later only if a real run shows a need. A list in a file the helper can write is one more guard file.
6. **C2 needs the hook to log `tool_use_id`.** It is an id, not content, but it is a new logged field. **Recommendation:** add it for Claude Code only, in the same fixed shape as the other entry fields.
