# Doc maintenance

How the docs of umwayi-os are written and kept current. Read this before changing code or docs.

## Core rule

Every change that adds, removes or changes behaviour comes with its doc update in the same turn and the same pull request. Docs describe the current state of the system, not the history of how it was built: history goes to [status-log.md](status-log.md) and to each doc's Decisions log. When something is removed or replaced, its old description is deleted, not left in place.

## Where to read first

[PROJECT.md](../PROJECT.md), then this file, then the doc of the part being worked on, then its section of the specs in `.kiro/specs/umwayi-os/`.

## When to update which file

- A new or changed command, flag or output of a layer: that layer's doc (see [architecture.md](architecture.md) for which one).
- A new or changed exit code: [exit-codes.md](exit-codes.md) and the layer's doc.
- A new rules action type: [rules.md](rules.md) and the layer that asks it.
- A new or changed logbook entry shape: [logbook.md](logbook.md) and the layer that writes it.
- A new or changed adapter: [adapters.md](adapters.md) and the adapter's own README.
- A known limit found or fixed: a limits part `docs-parts/known-limits/ID.md` (no number; `umwayi goal docs build` gives it one), see [goals.md](goals.md#the-shared-docs-builder-built-w99), and the layer's Open questions. Do not edit [KNOWN-LIMITS.md](KNOWN-LIMITS.md) by hand. Numbers are never reused.
- A change to the web interface (`ui/`, `site/` or `umwayi view snapshot`): [interface.md](interface.md), and the NOTES file `adapters/NOTES-layer12.md` for dated facts.
- A security or scan result: [security.md](security.md), and the dated scan results in `docs/SECURITY-SCAN.md`.
- A new test category or coverage decision: [testing.md](testing.md).
- A status change or a merged pull request: a status part `docs-parts/status-log/ID.md` (date, pr, what, tests; `umwayi goal docs build` makes the row in [status-log.md](status-log.md)) and the status table in `.kiro/specs/umwayi-os/tasks.md`.
- A schedule change: [schedule.md](schedule.md) and the schedule table in `.kiro/specs/umwayi-os/tasks.md`.
- An owner's decision on an open question: the Decisions log of the doc it belongs to, and the spec where it was asked.

## Format of each component doc

1. **Purpose**: one paragraph, what this part does and why it exists.
2. **Current state**: what is built now, described plainly.
3. **Decisions log**: a table of date, decision and reason, newest first, each row naming where it was decided.
4. **Open questions**: anything unresolved that affects this part.

| Date | Decision | Reason |
| --- | --- | --- |
| YYYY-MM-DD | What was decided | Why, in one sentence |

## Rules for writing

- No filler: state what exists, not what might exist.
- Plain words; no em dashes.
- Each doc under 300 lines; a longer one is split into sub-files that link to each other.
- The README stays at most 120 lines and links here for everything else.
- Do not edit `docs/status-log.md` rows or `docs/KNOWN-LIMITS.md` entries by hand: add a part (the id is the task or pull request, such as `W9-9`; a limits part needs a status part with the same id). The hand-written head of the status log is `docs-parts/status-log/00-head.md`, and a correction of an old entry is made in the frozen base `00-base.md` or `00-rows.md`; the build then rewrites the two files. Run `umwayi goal docs check` before you push.
- `tests/test_docs.py` checks the links, the README length, the em dashes, the four parts and the 300 lines.
