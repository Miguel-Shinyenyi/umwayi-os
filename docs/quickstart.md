# Quickstart for a tester

## Purpose

A stranger who installs umwayi-os from the public repo can try it safely in about fifteen minutes, with nothing at risk. It uses only commands that exist today, and every command in it was run on a copy of the repo before it was written down. The test `tests/test_quickstart.py` keeps the quoted commands true.

## Current state

### What it is

umwayi-os is an AI operating system for one person and their AI helpers. Before an AI helper acts, umwayi asks your rules for Yes, No or Ask me first, and it writes every change to an append only logbook. It also keeps a queue of tasks and decisions, a budget per run and per day, and a kill switch that stops everything at once.

### Install

You need Python 3.10 or later and git. There are no other packages.

```setup
git clone https://github.com/Miguel-Shinyenyi/umwayi-os.git
cd umwayi-os
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Check it:

```umwayi
umwayi --version
```

```text
umwayi 0.1.0
```

If you would rather not install it, run `python -m umwayi` from the repo folder instead of `umwayi`. Everything below works the same way.

```umwayi
python -m umwayi --version
```

### A first safe run on a scratch folder

umwayi works in a root folder that holds `rules.yaml` and `umwayi.json`. There is no `init` command today, so you make a scratch root by copying three files. Nothing outside the scratch folder is touched.

```setup
mkdir ../umwayi-scratch
cp rules.yaml umwayi.json jobs.yaml ../umwayi-scratch
cd ../umwayi-scratch
```

Add a task to the queue and read it back. The first command makes `queue.md`:

```umwayi
umwayi queue add --kind task "Try umwayi on a scratch folder"
umwayi queue list
```

```text
Added Q-0001 (task): Try umwayi on a scratch folder
Q-0001  task      open      -           Try umwayi on a scratch folder
```

Ask the rules about three actions. The exit code is the answer: 0 Yes, 2 No, 3 Ask me first.

```umwayi
umwayi check '{"type": "payment", "amount": 5}'
umwayi check '{"type": "something_new"}'
umwayi check '{"type": "read_memory"}'
```

```text
No
Rule: no-money
Reason: AI helpers never move money or use bank or card credentials. Cause: Safety rule for all AI helpers.
Ask me first
Rule: (none)
Reason: No rule matches this action.
Yes
Rule: read-memory
Reason: Reading the memory folder through the loader is allowed.
```

An action no rule names is always Ask me first. Each check writes one logbook entry (`LOGBOOK.md`) that holds the rule id and the answer, never the action. Run one of the safe jobs and check the logbook:

```umwayi
umwayi run jobs.yaml --job open-queue
umwayi logbook verify
```

```text
Job open-queue ran.
1 rows with status open:
Q-0001  task      open      Try umwayi on a scratch folder
ok: 6 entries, the format is valid and the hash matches the record
info: the hash chain is not started (umwayi logbook seal --chain --by NAME starts it)
```

The entry count depends on what you ran; `ok:` is what matters.

### The kill switch

The kill switch is one file, `.umwayi/KILL`, in the root. While it exists, every AI helper, job and workflow stops before it does anything.

```umwayi
umwayi kill on --reason "taking a break"
umwayi kill status
umwayi run jobs.yaml --job open-queue
umwayi kill off
umwayi kill status
```

```text
The kill switch is on. Every AI helper, job and workflow stops until 'umwayi kill off'.
on
The kill switch is on (.umwayi/KILL exists). Turn it off with 'umwayi kill off'.
Ask me first
Rule: (none)
Reason: The kill switch is on (.umwayi/KILL exists). Turn it off with 'umwayi kill off'.
The job did not run. Nothing was read.
The kill switch is off.
off
```

`kill status` exits 0 when it is off and 3 when it is on or cannot be read. A run that umwayi cannot tell about stops too. An agent start (`umwayi agent run`) stops the same way, and so does an adapter hook, which asks `umwayi check --kill-switch`. A plain `umwayi check` does not look at the switch: it only answers from the rules.

### What it ships with

- **Ask me first on every shell command.** The rules in `rules.yaml` name a shell command for Claude Code (`cc-ask-shell`), Kiro (`kiro-ask-shell`) and OpenCode (`oc-ask-shell`). An action with no rule is Ask me first, so any other tool is the same. No: money, pushing to main, publishing, and editing the guard files.

```umwayi
umwayi check '{"type": "tool_bash", "platform": "claude-code", "command": "ls"}'
```

```text
Ask me first
Rule: cc-ask-shell
Reason: The owner confirms every shell command. This covers deleting, installing, publishing and sending. Cause: A shell command can do anything, so the owner looks first.
```

- **Graded autonomy is off.** It is on only if you write an `autonomy.yaml`.

```umwayi
umwayi autonomy status
```

```text
graded autonomy: off (no autonomy.yaml). inputs: cannot be read (the hash chain has not started), so no class is moved and no score is shown. kill switch: off.
```

- **Budget caps.** With no `units.yaml`, every start reserves 100 UU (one UU is one US cent of estimated list price) and the day limit is 500 UU. A subscription is not billed by it.

```umwayi
umwayi budget status
```

```text
Budget for 2026-11-13 (1 UU is one US cent of estimated list price; a subscription is not billed by it)
per_day: used 0 UU, reserved 0 UU, left 500 UU (limit 500 UU)
per_run: 100 UU reserved for every start; unknown_worst_case: 100 UU
Of used: nothing was used on this day
There is no units.yaml: every reading is unknown and the limits are the placeholders.
Nothing was started or written.
```

- **Agents ask first.** `umwayi agent run` for an agent with no Yes rule is Ask me first (exit 3) and adds one queue item. Answering the item does not start the agent; you add a Yes rule yourself.

### One agent in a worktree, with a cap

This needs Claude Code or Kiro installed and signed in. Without one, `agent check` says so and nothing starts. The commands and outputs below were run with a stand-in program, so your `agent check` lines may differ, and on a real Claude Code a run reports its own cost.

An agent is named in `agents.yaml` in the root. Its `workdir` must be a real folder that is not the root or inside it:

```yaml
agents:
  - name: reviewer
    platform: claude-code
    command: claude
    workdir: /home/you/umwayi-work
```

```umwayi
umwayi agent validate
umwayi agent check reviewer
```

```text
ok: 1 agent(s): reviewer (claude-code, cli)
Agent reviewer: claude-code, transport cli, workdir /home/you/umwayi-work
kill switch: off
no: command: claude was not found on PATH
Not gated: agent reviewer would be refused (exit 2). Nothing was started.
```

(That is the output without Claude Code installed; with it, every line is `ok:` and the last is `Gated: agent reviewer can be started. Nothing was started.`)

`--workdir` makes the agent work in a git worktree instead of that folder. It accepts only the exact path `ROOT-worktrees/g-NNNN-t-NN`, next to the root, made as below. The root needs a git repo with a `main` branch, and the worktree folder must be mode 0700:

```setup
git init -b main
git add rules.yaml umwayi.json jobs.yaml
git -c user.name=me -c user.email=me@example.invalid commit -m "scratch root"
mkdir -m 700 ../umwayi-scratch-worktrees
git worktree add -b umwayi/g-0001-t-01 ../umwayi-scratch-worktrees/g-0001-t-01 main
```

Use the full path (change `/home/you` to where your scratch folder is); the first output below is shortened to its last line. Any other path is refused with exit 64 and nothing starts:

```umwayi
umwayi agent check reviewer --workdir /home/you/umwayi-scratch-worktrees/g-0001-t-01
umwayi agent check reviewer --workdir /tmp
```

```text
Gated: agent reviewer can be started. Nothing was started.
umwayi: error: agent: --workdir takes only a worktree that umwayi made under its worktree root. Nothing was started.
```

Add two Yes rules to `rules.yaml` for the one agent (the second is for its budget), then run it with a cap of 20 UU:

```yaml
  - id: scratch-agent-run
    title: The scratch reviewer may start
    text: The reviewer agent may start in the scratch root.
    verdict: yes
    matchers:
      type: agent_run
      agent: reviewer

  - id: scratch-agent-budget
    title: The scratch reviewer may spend within the limits
    text: The reviewer agent may reserve budget, within the limits of umwayi budget status.
    verdict: yes
    matchers:
      type: budget_check
      agent: reviewer
```

```umwayi
umwayi agent run reviewer --cap-uu 20 --workdir /home/you/umwayi-scratch-worktrees/g-0001-t-01 --prompt "Say hello"
```

```text
Agent reviewer finished (exit 0) after 0 s.
Budget: run RUNID settled, unknown 100 UU (1000000 micros).
```

`--cap-uu 20` lowers the reservation and the stop level of this run to 20 UU. A run that sends no cost report is still counted at 100 UU, the safe side. The start entry in the logbook names the folder as `working folder: worktree g-0001-t-01`, never the path. Run the same command with the kill switch on and it stops with exit 3.

### What to send back

Not yet available: the feedback path (an issue template and an export of a logbook summary with no file contents) is being built as W26. Until it is there, tell the owner in your own words what you ran, what you expected and what happened. Do not send `LOGBOOK.md`, `rules.yaml` or any file from a real project.

### The goal commands

Not yet available: `umwayi goal` start, run and status are not on main. Today `umwayi goal` has only `docs` and `guard`, which are for the people who build umwayi. Do not use it.

### Known limits, in plain words

- The kill switch is a file. Anyone or any program that can write the root folder can remove it. It stops runaway helpers, not a person with your permissions ([KNOWN-LIMITS](KNOWN-LIMITS.md) 2).
- The logbook shows tampering, it does not prevent it. Someone who edits both the logbook and its hash record is not caught until you start the hash chain (KNOWN-LIMITS 3).
- Ask me first on shell commands is a rule in your `rules.yaml`. If you change the rule, it changes.
- Kiro sends no cost, so nothing can stop a Kiro run in the middle for its cost; only its timeout does (KNOWN-LIMITS 117).
- The real Claude Code and Kiro runs by the owner (10.21, 10.31) and the cost capture (B.10) are not done, so what the agent section says about a real run is from the vendors' documentation and a stand-in program.
- Python 3.10 is end of life (KNOWN-LIMITS 133). Linux is the system tested. macOS and Windows were not tried.

The full list is [KNOWN-LIMITS](KNOWN-LIMITS.md). The layers behind each command: [rules](rules.md), [queue](queue.md), [logbook](logbook.md), [workflows and the kill switch](workflows.md), [budget governor](budget-governor.md), [agent front door](agent-front-door.md).

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-13 | The quickstart documents only commands that run on main, marks the feedback path and `umwayi goal` as not yet available, and a test parses every quoted command against the real command line | W25. A tester must not be given a command that does not exist, and a command in the page that stops parsing should fail a test. |

## Open questions

- Replace the feedback placeholder with the real path when W26 merges, and the goal section when W9.8 merges.
- There is no `umwayi init`. Recommendation: add one later, so a tester does not copy three files by hand.
