# What umwayi-os is and is not

## Purpose

This page says plainly what umwayi-os is, what it is not, what it does and does not do, and where it has been proven. Every point is meant to match the code and [KNOWN-LIMITS.md](KNOWN-LIMITS.md). If a point here and the code disagree, the code is right and this page is a bug.

## Current state

### What it is

- A governing layer for AI coding agents. It sits between the owner and the agents the owner runs (Claude Code, Kiro and OpenCode today).
- A Python package with no outside dependencies (standard library only, Python 3.10 or later) and a command line, `umwayi`.
- It decides what an agent may do: every action an adapter asks about gets Yes, No or Ask me first from the owner's `rules.yaml`.
- It records each decision in a logbook that is tamper-evident (it shows an edit; it does not prevent one).
- It caps spend with a budget per run and per day.
- It runs a goal as supervised tasks, each in its own git worktree, with a builder and a different tester (`umwayi goal`).
- It has a kill switch that stops every AI helper, job and workflow it starts.
- It is local first: everything it keeps is in the root folder on the owner's machine.

### What it is not

- Not a full operating system. It has no kernel, no hardware scheduler and no window system. "Operating system" in the name means the layer that runs the owner's AI helpers, not the machine.
- Not a model and not an agent. It has no model of its own; it starts the agents the owner already has.
- Not a sandbox. It does not stop a process that never asks it. An agent that skips its hook, or a program the owner runs by hand, is not checked. The options to go further are compared in [enforcement.md](enforcement.md) (W41, design only, nothing built).
- Not a security product and not a substitute for review. The owner reviews and merges every change; umwayi never merges ([security.md](security.md)).
- Not a hosted service. There is no account, no cloud part of the product and no telemetry sent anywhere. A later shared mode for several people, off by default, is only designed: [multi-user](multi-user.md) (W74). (The public site in `site/` is a page about umwayi; it holds and receives none of the owner's data.)
- Not affiliated with or endorsed by Anthropic, Amazon, Kiro, OpenCode or any agent it can run.

### What it does

- **The rules gate, fail closed.** `umwayi check` answers Yes (exit 0), No (exit 2) or Ask me first (exit 3). No matching rule, a broken or missing `rules.yaml`, or bad action JSON all give Ask me first; a crash is treated like No, never like Yes. A usage or config error is 64. The full table: [exit-codes.md](exit-codes.md), [rules.md](rules.md).
- **The logbook.** `LOGBOOK.md` is append only. Its whole-file hash is kept in `.umwayi/logbook.sha256`, so a hand edit is found by `umwayi logbook verify`. A write with a date before the last entry is refused. Once the owner starts the hash chain (`umwayi logbook seal`), an edited, deleted or reordered entry is found even if the hash record was rewritten too; rewriting the whole chain and the record together is found only against an anchor kept elsewhere (KNOWN-LIMITS 3 and 104). [logbook.md](logbook.md).
- **The budget governor.** Every agent start reserves a budget first and is settled when it ends, under limits per run and per day. A UU is an internal unit of estimated cost (one UU is one US cent of estimated list price). It moves no money and is not a bill; a subscription is not billed by it. [budget-governor.md](budget-governor.md).
- **The goal supervisor.** `umwayi goal` splits a goal into small task packets, runs each one in its own git worktree with a builder, a different tester and a check by the guide, and stops at `in review`. The owner approves the plan and the spend and merges; umwayi never pushes or merges. [goals.md](goals.md).
- **The kill switch.** `umwayi kill on` creates `.umwayi/KILL`; while it exists, every AI helper, job and workflow stops before it does anything, and a state that cannot be read counts as on. [workflows.md](workflows.md).
- **The local backend and pages.** `umwayi serve` binds 127.0.0.1 only and every request needs a token from `umwayi serve token create`. It reads status, the queue, the logbook check, the budget and the agents, and it can do a short closed list of writes: add, answer and close a queue item, run an agent check, and turn the kill switch on. It cannot turn the switch off, approve, start an agent or pay. The pages in `ui/dist/` (the live view, the command map, the goal map) send nothing except the live view's requests to that backend. [serve.md](serve.md), [interface.md](interface.md).
- **The feedback export.** `umwayi feedback export` prints a summary of the logbook (counts per kind and per verdict, the date range, the chain status, the budget spent in UU) with no paths, no commands, no rule text and no file contents, and writes nothing. [feedback.md](feedback.md).

### What it does not do

- No enforcement on a process that skips the hooks. Enforcement is cooperative today: the Claude Code, Kiro and OpenCode adapters ask umwayi before each tool call, and a process that does not ask is not checked.
- No shared memory between agents or runs beyond umwayi's own records. What carries from one run to the next is only what umwayi itself writes: the logbook, the budget ledger, the queue and the goal state files. The `memory/` folder is the owner's own notes, which `umwayi memory bundle` reads; no agent writes it through umwayi.
- No installing or managing agents as packages. The owner installs Claude Code, Kiro or OpenCode and names them in `agents.yaml`.
- umwayi itself sends nothing off the machine. Its one listening server binds 127.0.0.1, and the telemetry receiver of the budget governor takes reports from the agent it started on 127.0.0.1. The agents it starts talk to their own services as they always do.
- It handles no passwords, keys or tokens of the owner's accounts. Each agent signs in with its own tool; umwayi removes the credential variables from the environment it hands an agent (the `ANTHROPIC_*` and `CLAUDE_CODE_*` sign-in names for Claude Code, and `KIRO_API_KEY` for Kiro, which it never passes), and it does not read what a sign-in prints. Its own serve token is a local token for its own backend.
- It gives no legal, financial or security advice.
- It does not make agent output correct. A tester's pass is a claim by an AI helper (KNOWN-LIMITS 214); the owner reviews.

### Where it has been proven and where not

- Proven in tests, against fake agents and fixtures, as real child processes in temporary folders. CI runs Python 3.10 and 3.13 on every pull request and 3.10 to 3.13 on every push to main, on Linux ([testing.md](testing.md)).
- Not yet proven with real Claude Code, Kiro and OpenCode runs (the owner's checks 10.21, 10.31 and 10.51 are not done) or with a real goal run end to end (W9.11 and W40).
- Windows is not supported today: where `fcntl` does not exist, the logbook cannot be written and every start answers Ask me first (KNOWN-LIMITS 9 and 76). macOS is not tested.
- The High tier of the public site is not tested on real devices (KNOWN-LIMITS 151).

### Status

Early and experimental. Built for a hackathon. Interfaces and file formats can change. Use it on a project you can restore from git. There is no warranty; see [LICENSE](../LICENSE).

The full list of what is known and not fixed: [KNOWN-LIMITS.md](KNOWN-LIMITS.md).

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-14 | One page says what umwayi is and is not, and `tests/test_what_it_is.py` keeps its headings, and keeps the claim that it is no operating system of a machine in the "is not" part only | W39, the owner's task: a reader must not take the name for more than it is. |

## Open questions

- None about the page itself. When W40 records a real run, "Where it has been proven" changes with it.

Every limit that is known and not fixed, numbered: [KNOWN-LIMITS.md](KNOWN-LIMITS.md).
