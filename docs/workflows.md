# Workflows, the kill switch and one run at a time (layer 8)

## Purpose

A workflow runs a fixed list of steps from `workflows/NAME.yaml`, each asked of the rules. This layer also holds the kill switch, which stops every AI helper, job and workflow, and the run lock, which lets only one of them run at a time. They exist so a chain of steps stops at the first No or Ask me first, and so the owner can stop everything at once.

## Current state

A workflow is a file `workflows/NAME.yaml` with a name and steps in order. Each step is one command from a fixed list inside umwayi, with its arguments written in the file:

| command | arguments |
| --- | --- |
| `queue-list` | `status` (optional) |
| `steward` | `waiting_days` (optional, default 7) |
| `social-draft` | `article` (a local article file) |
| `report` | `since_days` |
| `check` | `action_type` |
| `approve` | none, and only as the last step |

There is no way to put a shell command, another program or an approval in a workflow.

```
umwayi workflow validate content-loop
umwayi workflow run content-loop [--date 2026-11-07]
```

- `validate` prints every problem with its line number and exits 64, or `ok` and exits 0.
- `run` asks the rules for every step (action type `workflow_step`). No stops it (exit 2), Ask me first stops it (exit 3). Every step adds one logbook entry. If the logbook cannot be written, the run stops.
- The shipped content loop (`workflows/content-loop.yaml`) runs collect (`queue-list`), brief (`steward`), draft (`social-draft` from `articles/example.md`) and approve.
- The approve step never approves anything. It adds a queue item of kind decision that lists the drafts, and stops the workflow with exit 3. The workflow will not run again until you answer or close that item. To publish a draft, you run `umwayi publish-draft DRAFT`, which is Ask me first.
- Workflows write only under `drafts/`, plus the queue and the logbook.

### Kill switch

```
umwayi kill on [--reason "taking a break"]
umwayi kill status
umwayi kill off
```

While the switch is on (the file `.umwayi/KILL` exists), every AI helper, job and workflow stops before doing anything, with exit 3 (Ask me first) and one logbook entry. If umwayi cannot tell whether the switch is on (for example `.umwayi` is not a normal folder), it stops too. `kill on` works even when the logbook is broken. `kill off` keeps the switch on if the logbook cannot record it. Your own commands (queue, archive, check, report, publish-draft) are not stopped. The layer 9 adapters are: they deny every tool call while the switch is on.

### One run at a time

AI helpers, jobs and workflows share one lock, `.umwayi/run.lock`. If one is running and you start another, the second one does not wait: it answers Ask me first (exit 3), writes one logbook entry, and changes nothing. If locking is not available on your system, they all answer Ask me first. Your own commands (queue, check, archive, report, publish-draft) are not locked.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-08 | The run lock `.umwayi/run.lock` never waits: a second run answers Ask me first (H.2) | Hardening, PR 9: two runs at once must not race. |
| 2026-11-08 | An unknown kill switch state fails closed (8.3) | Layer 8, PR 8: if umwayi cannot tell, it stops. |
| 2026-11-08 | The approve step never approves: it adds a decision and stops with exit 3 (8.2) | Layer 8, PR 8: only the owner approves. |

## Open questions

- The kill switch is a file anyone with write access can remove ([KNOWN-LIMITS](KNOWN-LIMITS.md) item 2).
- YAML syntax errors show only the first problem ([KNOWN-LIMITS](KNOWN-LIMITS.md) item 6).
- Inside a workflow, the social step is one rules check for all channels ([KNOWN-LIMITS](KNOWN-LIMITS.md) item 7).
