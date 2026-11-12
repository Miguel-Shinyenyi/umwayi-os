# umwayi-os

An AI operating system for one person and their AI helpers.

It keeps memory, enforces rules before an AI helper acts, tracks a queue of tasks and decisions, archives moved text with a fingerprint, and writes a logbook of every change. It is built in layers, and each layer works alone and is tested before the next starts.

Start with [PROJECT.md](PROJECT.md): what to read first, and where everything is.

## Status

| part | state | doc |
| --- | --- | --- |
| Layers 1 to 8 (memory, rules, queue, archive, logbook, automation, helpers, workflows) | built | [architecture](docs/architecture.md) |
| Layer 9 adapters (Claude Code, Kiro, stdin and stdout) | built | [adapters](docs/adapters.md) |
| Layer 10 front door for agents | built; the owner's real runs (10.21, 10.31) not done; part 8 (OpenCode) specified, not built | [agent front door](docs/agent-front-door.md) |
| Layer 11 scheduled runs | built; the owner's real check (11.6) not done | [scheduled runs](docs/scheduled-runs.md) |
| Logbook crash safety and hash chain | built | [logbook](docs/logbook.md) |
| Budget governor | built; the owner's capture (B.10) not done | [budget governor](docs/budget-governor.md) |
| Whole-system test (S.1) | built | [testing](docs/testing.md) |
| Layer 12 web interface (the view) | `umwayi view snapshot` built (UI.2, PR 41); the Kenyan highlands scene and home page with List and Standard tiers built (UI.1 and UI.1b, PR 39, merged); the shared scene module and the public site in `site/` with List and Standard built (UI.6, its own pull request); UI.3 (the page reads the snapshot, live view and site) built (its own pull request); the owner checks panel built (UI.4, its own pull request); UI.5 and UI.7 not started | [interface](docs/interface.md) |
| Security scan (S.2) | done 2026-11-10; Python 3.10 end of life, for the owner to decide | [security](docs/security.md), [scan record](docs/SECURITY-SCAN.md) |
| Layer 13 correction and graded autonomy | all five slices built (elections, reversal, courts and the rules change log, honest tension, graded autonomy off by default) | [corrections](docs/corrections.md), [autonomy](docs/autonomy.md) |

Every pull request and its test count: [docs/status-log.md](docs/status-log.md). The schedule to Dec 3: [docs/schedule.md](docs/schedule.md).

## Install and test

Python 3.10 or newer, no third party packages.

```
pip install -e .          # optional, gives the `umwayi` command
python -m unittest discover -s tests -t .
```

Without installing, use `python -m umwayi` from the repo root.

## Exit codes

- 0: Yes, or done.
- 1: refused, something was checked and found wrong, nothing was changed (never from `agent`, `schedule` or `budget`).
- 2: No, or an unexpected error (a crash is treated like No, never like Yes).
- 3: Ask me first. 64: a usage or config error.
- The full table and which command gives which: [docs/exit-codes.md](docs/exit-codes.md).

## Layers

| layer | what it does | doc |
| --- | --- | --- |
| 1 memory | one context bundle for an AI helper, private paths left out | [memory.md](docs/memory.md) |
| 2 rules | Yes, No or Ask me first before any action | [rules.md](docs/rules.md) |
| 3 queue | tasks and decisions in `queue.md` | [queue.md](docs/queue.md) |
| 4 archive | moved text with a fingerprint | [archive.md](docs/archive.md) |
| 5 logbook | the append only record, crash safety, the hash chain | [logbook.md](docs/logbook.md) |
| 6 automation | jobs, the progress report, publish a draft | [automation.md](docs/automation.md) |
| 7 AI helpers | Steward and the social helper, drafts only | [helpers.md](docs/helpers.md) |
| 8 workflows | steps in order, the kill switch, one run at a time | [workflows.md](docs/workflows.md) |
| 9 adapters | hooks for Claude Code, Kiro and any stdin and stdout tool | [adapters.md](docs/adapters.md) |
| 10 front door | `umwayi agent`: check, run, chat, login | [agent-front-door.md](docs/agent-front-door.md) |
| 11 scheduled runs | systemd user timers for jobs and workflows | [scheduled-runs.md](docs/scheduled-runs.md) |
| budget governor | a budget per run and per day, the telemetry receiver | [budget-governor.md](docs/budget-governor.md) |
| 12 view | a calm, realistic 3D scene of eleven natural features and the home page, that will show counts from a read only snapshot (the snapshot command, the scene, the home page and the public site are built) | [interface.md](docs/interface.md) |

How they fit together: [docs/architecture.md](docs/architecture.md). Requirements, design and tasks: `.kiro/specs/umwayi-os/`. Product rules: `.kiro/steering/product.md`.

## Security and known limits

- What umwayi protects, what it only makes visible, and how it is checked: [docs/security.md](docs/security.md). The dated scan, its tools and findings: [docs/SECURITY-SCAN.md](docs/SECURITY-SCAN.md).
- Every limit that is known and not fixed, numbered: [docs/KNOWN-LIMITS.md](docs/KNOWN-LIMITS.md).

## Contributing

- One branch and one pull request per task; nothing is pushed to `main` directly.
- Tests first, as real child processes; the full suite passes on Python 3.10 to 3.13 before a merge.
- A behaviour change and its doc update ship in the same pull request: [docs/DOCS_MAINTENANCE.md](docs/DOCS_MAINTENANCE.md).
- Standard library only in `umwayi/`; no em dashes in docs.

## Licence

See [LICENSE](LICENSE).
