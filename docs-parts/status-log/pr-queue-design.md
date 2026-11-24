date: 2026-11-24
pr: none
what: G7, design note, docs only: `docs/pr-queue-design.md`. A PR queue as a feature of the product: a strict table `pr-queue.md` (branch, order, owner stop, status, PR, head, files), `umwayi pr queue add, list, next, conflicts` (read only, no network), then a read only `watch` that uses the exact-head check rule and writes one logbook entry on a merge. It records and advises; it never pushes or merges. Build order 1, 2 and 4 first, then 3 (a `gh` call, owner stop). Nothing is built. A README row names it as planned.
tests: the docs tests (headings, links, no em dashes, stale statements).
