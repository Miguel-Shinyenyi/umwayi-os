# Status log

## Purpose

This page says where each part of umwayi-os stands and logs every pull request with its test count. It exists so the state of the project can be read in one place.

## Current state

### Status

Status: all eight layers are built: memory, rules, queue, archive, logbook, automation, helpers and workflows. Layer 9 (adapters for Claude Code, Kiro and any stdin and stdout tool) is built, see [Layer 9](adapters.md). Layer 10 (one front door for agents) is in progress: agents.yaml, the gate checks, `umwayi agent run` and `umwayi agent chat` (on your terminal, or over ACP for Kiro) for Claude Code and Kiro are built; for Claude Code over ACP (part 7, approved) the pinned adapter package, its gate checks (part 7a) and the chat (part 7b) are built, see [Layer 10](agent-front-door.md). Layer 11 (scheduled runs through systemd user timers) is built, see [Layer 11](scheduled-runs.md). Known limits are listed in [docs/KNOWN-LIMITS.md](KNOWN-LIMITS.md). See `.kiro/specs/umwayi-os/` for requirements, design and tasks, and `.kiro/steering/product.md` for the product rules.

The full status table, with every task, is in [tasks.md](../.kiro/specs/umwayi-os/tasks.md), section "Status".

Layer 13 (correction and graded autonomy: elections, reversal, courts, the stop criteria and a graded autonomy score) is specified (L13.0, PR 40, docs and specs only). Slice 1, elections (L13.1: `review_by` on Yes rules and `umwayi rules due`), is built. Reversal, courts, honest tension and graded autonomy are not built. See [corrections](corrections.md) and [autonomy](autonomy.md).

### Pull requests

| date | PR | what | tests after it (Python 3.10 to 3.13) |
| --- | --- | --- | --- |
| 2026-11-10 | 38 | spec: layer 12, the web interface (UI.0); docs only, waits for the owner's approval | |
| 2026-11-10 | 37 | S.2: the security scan; 10 defects it found fixed | 1155 |
| 2026-11-10 | 36 | S.1: the whole-system test; a gap rule refusal now writes its entry | 1135 |
| 2026-11-10 | 35 | D.1: the short README, PROJECT.md and one doc per component under docs/ | 1104 |
| 2026-11-10 | 34 | spec: whole-system test and security scan, and D.1 | |
| 2026-11-10 | 33 | budget governor | 1091 |
| 2026-11-10 | 32 | logbook hash chain | 1001 |
| 2026-11-10 | 31 | layer 11 scheduled runs | 978 |
| 2026-11-10 | 30 | spec: layer 11 | |
| 2026-11-10 | 29 | layer 10 part 7c-3 | 934 |
| 2026-11-09 | 28 | layer 10 part 7c-2 | 929 |
| 2026-11-09 | 27 | logbook crash safety | 906 |
| 2026-11-09 | 26 | spec: logbook crash safety | |
| 2026-11-09 | 25 | tests only: the flaky Ctrl-C and SIGHUP test | |
| 2026-11-09 | 24 | spec: hash chain and budget governor | |
| 2026-11-09 | 23 | layer 10 part 7c-1 | 869 |
| 2026-11-09 | 22 | spec: layer 10 part 7c | |
| 2026-11-09 | 21 | layer 10 part 7b | 854 |
| 2026-11-08 | 20 | layer 10 part 7a | 829 |
| 2026-11-08 | 19 | spec: layer 10 part 7 | |
| 2026-11-08 | 18 | layer 10 part 6 | 783 |
| 2026-11-08 | 17 | layer 10 part 5 | 747 |
| 2026-11-08 | 16 | layer 10 part 4 | 719 |
| 2026-11-08 | 15 | layer 10 part 3 | 697 |
| 2026-11-08 | 14 | layer 10 parts 1 and 2 | 673 |
| 2026-11-08 | 13 | spec: layer 10 | |
| 2026-11-08 | 12 | layer 9 part 2: Kiro, generic, kill switch | 619 |
| 2026-11-08 | 11 | layer 9 part 1: Claude Code | 578 |
| 2026-11-08 | 10 | spec update: layers 9 to 11 | |
| 2026-11-08 | 9 | hardening and the whole-system test | 556 |
| 2026-11-08 | 4 to 8 | layers 4 to 8 | |
| 2026-11-07 | 1 to 3 | specs, layers 1 to 3 | |

A blank count means the pull request changed no test or its count was not recorded.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-10 | The status lives here and in the tasks.md status table; both change in the same pull request | DOCS_MAINTENANCE.md: docs describe the current state. |

## Open questions

None open.
