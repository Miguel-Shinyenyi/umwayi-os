# Status log

## Purpose

This page says where each part of umwayi-os stands and logs every pull request with its test count. It exists so the state of the project can be read in one place.

## Current state

### Status

Status: all eight layers are built: memory, rules, queue, archive, logbook, automation, helpers and workflows. Layer 9 (adapters for Claude Code, Kiro and any stdin and stdout tool) is built, see [Layer 9](adapters.md). Layer 10 (one front door for agents) is in progress: agents.yaml, the gate checks, `umwayi agent run` and `umwayi agent chat` (on your terminal, or over ACP for Kiro) for Claude Code and Kiro are built; for Claude Code over ACP (part 7, approved) the pinned adapter package, its gate checks (part 7a) and the chat (part 7b) are built, see [Layer 10](agent-front-door.md). Part 8 of layer 10 (OpenCode over ACP) and Muse Spark Open as an OpenCode model are specified, not built; the owner asked for OpenCode to be built before Dec 3. Layer 11 (scheduled runs through systemd user timers) is built, see [Layer 11](scheduled-runs.md). Known limits are listed in [docs/KNOWN-LIMITS.md](KNOWN-LIMITS.md). See `.kiro/specs/umwayi-os/` for requirements, design and tasks, and `.kiro/steering/product.md` for the product rules.

The full status table, with every task, is in [tasks.md](../.kiro/specs/umwayi-os/tasks.md), section "Status".

Layer 13 (correction and graded autonomy: elections, reversal, courts, the stop criteria and a graded autonomy score) is specified (L13.0, PR 40, docs and specs only). Slice 1, elections (L13.1: `review_by` on Yes rules and `umwayi rules due`), is built. Slice 2, reversal (L13.2: `umwayi decision reopen` and `queue answer --revisit-if`), is built. Slice 3, courts and the rules change log (L13.3: `umwayi petition`, the `umwayi rules` entries), is built. Slice 4, honest tension (L13.4: the stop criteria, the plain note and the words test), is built. Slice 5, graded autonomy (L13.5: `umwayi autonomy record`, `status` and `validate`, the opt-in and the thirteen gates), is built and off by default. See [corrections](corrections.md) and [autonomy](autonomy.md).

The local backend (W6, `umwayi serve`) was specified in W6.0 (PR 61, docs and specs only). Its core is built (W6.1 to W6.6, one pull request, Nov 12): the gate, the token, the server, the pipeline and the first routes. The page client (W6.9) is not built, so the page still makes no request. See [serve.md](serve.md).

Goal orchestration (W9, `umwayi goal`: a goal split into task packets, run one at a time through the gate by a builder and a different tester, the owner approves and merges) is specified (W9.0, PR 63, docs and specs only) and not built. The owner answered W9-Q1 to W9-Q14 on Nov 12, all as recommended; only W9.9 (the shared docs builder, also the owner's task W17) may go before the Nov 29 freeze. By a later owner rule of the same day, each task runs in its own git worktree made by umwayi from the newest main. See [goals.md](goals.md).

### Pull requests

| date | PR | what | tests after it (Python 3.10 to 3.13) |
| --- | --- | --- | --- |
