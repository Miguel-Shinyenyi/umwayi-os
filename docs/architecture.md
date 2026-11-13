# Architecture

## Purpose

umwayi-os is built in layers, each one working alone and tested before the next starts. This page says how the layers fit together and where each one lives, so a reader can find the code and the doc of any part.

## Current state

The core is the `umwayi` package, standard library only (`pyproject.toml`: `dependencies = []`). Adapters live outside it, in `adapters/`, and may use pinned third party packages listed in their README; the core never imports `adapters`.

| layer | what it does | code | doc |
| --- | --- | --- | --- |
| 1 memory | the context bundle, private paths left out | `umwayi/memory.py`, `umwayi/config.py` | [memory.md](memory.md) |
| 2 rules | Yes, No or Ask me first for every action | `umwayi/rules.py`, `umwayi/miniyaml.py` | [rules.md](rules.md) |
| 3 queue | tasks and decisions in `queue.md` | `umwayi/taskqueue.py` | [queue.md](queue.md) |
| 4 archive | moved text with a fingerprint | `umwayi/archive.py`, `umwayi/fsutil.py` | [archive.md](archive.md) |
| 5 logbook | the append only record, crash safety, the hash chain | `umwayi/logbook.py` | [logbook.md](logbook.md) |
| 6 automation | jobs, the report, publish a draft | `umwayi/jobs.py`, `umwayi/report.py`, `umwayi/publish.py` | [automation.md](automation.md) |
| 7 AI helpers | Steward and the social helper, drafts only | `umwayi/helpers/` | [helpers.md](helpers.md) |
| 8 workflows | steps in order, the kill switch, the run lock | `umwayi/workflow.py`, `umwayi/kill.py`, `umwayi/runlock.py` | [workflows.md](workflows.md) |
| 9 adapters | hooks for Claude Code, Kiro and stdio | `adapters/` | [adapters.md](adapters.md) |
| 10 front door | `umwayi agent`: check, run, chat, login | `umwayi/agents.py`, `umwayi/acp.py` | [agent-front-door.md](agent-front-door.md) |
| 11 scheduled runs | systemd user timers for jobs and workflows | `umwayi/schedule.py` | [scheduled-runs.md](scheduled-runs.md) |
| budget governor | UU, the ledger, the telemetry receiver | `umwayi/units.py`, `umwayi/budget.py`, `umwayi/telemetry.py` | [budget-governor.md](budget-governor.md) |
| 12 view (snapshot, scene, public site, snapshot reading and the owner checks panel built; access and docs half done) | a web page that only looks, the same scene on a public site, and the read only snapshot of counts it will read | `ui/`, `site/`, `umwayi/view.py` | [interface.md](interface.md) |
| W6 local backend (first routes and the page client built; the chat and intake routes are not) | `umwayi serve`: a server on 127.0.0.1 with a token that lets the page send the same request the command line would; the gate is a pure function, every request goes through the kill switch, the rules check and the logbook | `umwayi/servegate.py`, `umwayi/servetoken.py`, `umwayi/serve.py` | [serve.md](serve.md) |
| W19 concerns record (part 2 built) | `umwayi concerns check PATH`: a record with one well formed row for each of 111 engineering concepts, each with an allowed answer and a reason; run by the owner, never on a schedule | `umwayi/concerns.py` | [concerns.md](concerns.md) |
| W19 model routing table and task log (part 3b built) | `umwayi routing check PATH`: a table of model options with vendor sources and `review_by` dates, and the task log of how umwayi-os is built; it checks the form only, never picks a model, and runs only when the owner runs it | `umwayi/routing.py` | [model-routing.md](model-routing.md), [task-log.md](task-log.md) |
| W19 stall checks (part 5 built) | `umwayi stalls check EVENTS.json`: four small pure checks over a JSON list of builder events (a stall, the same error twice, an approval past its deadline, a status with no last event time); it reads one file, changes nothing, never repeats file text and is on no schedule | `umwayi/stalls.py` | [stalls.md](stalls.md) |
| W9 goal orchestration (specified; only the docs builder is built) | `umwayi goal`: a goal split into task packets, run one at a time through the rules check, the kill switch and the budget governor by a builder and a different tester; the owner approves and merges | `umwayi/goalpacket.py`, `umwayi/goallog.py`, `umwayi/goalwatch.py`, `umwayi/goalstate.py`, `umwayi/goalbudget.py`, `umwayi/goalgit.py`, `umwayi/goalrun.py`, `umwayi/goal.py`, `umwayi/goaldocs.py` (built, W9.9: the part files, `umwayi goal docs build\|check`; the others planned) | [goals.md](goals.md) |

Shared by every layer:

- Every change is one logbook entry through the one checked append (`umwayi/logbook.py`); a write that cannot be logged is not made.
- Every action of a helper, job, workflow, adapter or agent is asked of the rules first, the same check as `umwayi check`.
- The kill switch (`.umwayi/KILL`) and the run lock (`.umwayi/run.lock`) are described in [workflows.md](workflows.md).
- The command line is `umwayi/cli.py`; the exit codes are in [exit-codes.md](exit-codes.md).
- The requirements, design and tasks of every layer are in [requirements.md](../.kiro/specs/umwayi-os/requirements.md), [design.md](../.kiro/specs/umwayi-os/design.md) and [tasks.md](../.kiro/specs/umwayi-os/tasks.md).
- Layer 13 (all five slices built: elections, reversal, courts with the rules change log, honest tension, and graded autonomy in `autonomy.py`, off by default): correction and graded autonomy. It changes `umwayi/rules.py` (built in slice 1), `umwayi/taskqueue.py` (`--revisit-if` and `add_with_entry`, slice 2) and `umwayi/logbook.py` (`read_chained`, slice 2), and adds `elections.py` (built), `decisions.py` (built), `rulelog.py`, `petition.py` and `autonomy.py` to the core; it changes nothing in `ui/`. See [corrections.md](corrections.md) and [autonomy.md](autonomy.md).

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-10 | One doc per component under `docs/`, a short README and `PROJECT.md` (D.1) | The owner's documentation pattern; the README had grown to 447 lines. |
| 2026-11-08 | Adapters and layer 10 adapter packages live outside the core package; the core stays standard library only | design.md, layer 9: third party code stays pinned and outside `umwayi/`. |

## Open questions

- A sandbox for agents and helpers is deferred to its own spec after Dec 3 (L11-Q13).
- An SQLite index is deferred to after Dec 3 (L11-Q11).
