# umwayi-os

## What this is

An AI operating system for one person and their AI helpers. It keeps memory, enforces the owner's rules before an AI helper, job, workflow or agent acts, tracks a queue of tasks and decisions, archives moved text with a fingerprint, and writes a logbook of every change. It is built in layers; each layer works alone and is tested before the next starts.

## What to read first

1. This file.
2. [docs/DOCS_MAINTENANCE.md](docs/DOCS_MAINTENANCE.md): how the docs are kept current.
3. The doc of the part being worked on (the list below).
4. Its section in the specs: [requirements.md](.kiro/specs/umwayi-os/requirements.md), [design.md](.kiro/specs/umwayi-os/design.md) and [tasks.md](.kiro/specs/umwayi-os/tasks.md).
5. [docs/KNOWN-LIMITS.md](docs/KNOWN-LIMITS.md) for what is known and not fixed.

That is enough to continue work in a new session without the whole history.

## Project structure

```
umwayi-os/
  README.md                 short overview, status, install, links
  PROJECT.md                this file: what to read first
  umwayi/                   the core package, standard library only
  adapters/                 layer 9 hooks and the pinned Claude Code ACP adapter, outside the core
  ui/                       layer 12: the web interface (sources, pinned build tools, the built page), outside the core
  site/                     layer 12: the public site (Next.js, pinned), outside the core; it imports the scene from ui/src
  tests/                    every test; python -m unittest discover -s tests -t .
  docs/
    DOCS_MAINTENANCE.md     how the docs are written and kept current
    architecture.md         how the layers fit together, where each one lives
    memory.md               layer 1
    rules.md                layer 2
    queue.md                layer 3
    archive.md              layer 4
    logbook.md              layer 5, crash safety and the hash chain
    automation.md           layer 6: jobs, the report, publish a draft
    helpers.md              layer 7: Steward and the social helper
    workflows.md            layer 8, the kill switch and the run lock
    adapters.md             layer 9
    agent-front-door.md     layer 10: umwayi agent
    scheduled-runs.md       layer 11: systemd user timers
    budget-governor.md      UU, the ledger, the telemetry receiver
    interface.md            layer 12: the view, a web page that only looks (the snapshot command, the highlands scene, the home page, the public site, the snapshot reading and the owner checks panel are built; UI.5 is half done)
    exit-codes.md           every exit code and which command gives it
    testing.md              how everything is tested
    security.md             what is protected and how it is checked
    corrections.md          layer 13: elections, reversal, courts and the rules change log, the stop criteria and the plain note (built)
    autonomy.md             layer 13: graded autonomy, the score and its gates (built, off by default)
    serve.md                W6: umwayi serve, the local backend the page may send requests to (the core is built; the page client is not)
    goals.md                W9: umwayi goal, a goal split into task packets and run one at a time through the gate (specified; only the docs builder `goal docs` is built)
    status-log.md           the status and every pull request with its test count
    schedule.md             the schedule to Dec 3
    KNOWN-LIMITS.md         every known limit, numbered
  .kiro/specs/umwayi-os/    requirements, design and tasks of every layer
  .kiro/steering/           the product rules
```

The facts each adapter relies on, with links, are in [adapters/NOTES.md](adapters/NOTES.md), [adapters/NOTES-layer10.md](adapters/NOTES-layer10.md) and [adapters/NOTES-layer11.md](adapters/NOTES-layer11.md) and [adapters/NOTES-layer12.md](adapters/NOTES-layer12.md) and [adapters/NOTES-w6.md](adapters/NOTES-w6.md) and [adapters/NOTES-w9.md](adapters/NOTES-w9.md).
