date: 2026-11-25
pr: none
what: A design note, docs only: `docs/goal-use-design.md`, how the governor will know what a goal has used (M4 h, the next part). It reads the ledger as built (three fixed shapes, no goal on a reserve line, the day from the machine's `date.today()`), compares three options and recommends a fourth fixed shape, `Run R counted for goal G on provider P`, which leaves the reserve and settle shapes alone. It lists the four steps in order (each its own pull request, the first two owner stops) and four open questions with a recommendation. Nothing is built.
tests: none new; the docs tests and the line count of the docs.
