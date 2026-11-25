# Projects A and B: the specs, and how any harness builds or tests them

## Purpose

Two small projects whose specs and tests were written first, so that any harness that umwayi-os can run (Claude Code, OpenCode, Muse; Kiro is on
pause) can build the code or test it, and every run can be recorded. The work itself happens in two private repositories; this note is the one
page that says what is where, what each harness may do, and what is still open. Docs only: nothing here is built, and no code of either project
exists yet.

## Current state

Checked on 2026-11-25 against the two repositories.

| | Project A | Project B |
|---|---|---|
| What it is | an M-Pesa statement analyzer | a link checker for Markdown |
| Repository | `Miguel-Shinyenyi/mpesa-statement-analyzer` (private) | `Miguel-Shinyenyi/link-checker` (private) |
| Spec and tests | `SPEC.md` and `tests/test_analyzer.py`, **on `main`** (PR 3, merged 2026-11-25 14:08 Nairobi) | `SPEC.md` and `tests/test_linkcheck.py` in **PR 1, open**, not on `main` yet |
| Tests | 17, on made-up transactions only | 17, on made-up folders in a temporary directory |
| Code | none: the tests fail with `No module named mpesa_analyzer` | none: the tests fail with `No module named linkcheck` |
| Never bends | no network, nothing written, no real statement in the repo (`*.csv` is ignored) | no network, nothing written, a file outside the folder is never opened |

**A in plain words.** `python3 -m mpesa_analyzer STATEMENT.csv --categories CATEGORIES.json [--top N]` reads an M-Pesa statement saved as a CSV, keeps the
rows whose status is `Completed`, sorts the money that went out into the categories the user wrote (the first category whose keyword is in the details,
ignoring case, else `Uncategorized`), and prints the monthly totals and the counterparties paid the most, in the exact format of `SPEC.md`. A bad file is
one `error:` line and exit 2, with no traceback and never the text of a row.

**B in plain words.** `python3 -m linkcheck ROOT [--paths P ...]` reads the Markdown files under a folder and prints one line per problem
(`PATH:LINE: KIND: TARGET`): a link to a file that is not there, an image that is not there, a heading anchor that is not there, a target that leaves the
folder, an empty link. Web addresses are never fetched. Exit 0 with no problem, 1 with problems, 2 for a bad argument.

**The 17 tests of each, by group.** A: parse (5), categorize (3), totals and top spenders (4), the command (3), the rules of the repo (2). B: extraction (3),
checks (9), the command (4), the rules of the repo (1). The test names are in the test files; the spec is the contract and the tests are its
checks. They were never run against an implementation, so a test could contradict the spec.

### The task card, the same for any harness

1. **Read `SPEC.md` and the tests together before any code.** If a test contradicts the spec, stop and report it; do not choose silently.
2. **Builder.** Write the package so that `python3 -m unittest` passes. Do not edit the spec or the tests. Report the real output of the run.
3. **Tester.** Run the suite on the builder's branch and report every failure with its exact message. A new test goes in a separate branch and is labelled as
   added by the tester.
4. **Reviewer.** Read the diff against the rules that never bend, and against the spec's exact output and exit codes.
5. **Every run is recorded** under the real run rules (`REAL-ENFORCED-RUN`), and the FEEDBACK block says, per harness, which roles it filled and what it cost.

### The data rule

Muse on free credits and OpenCode on its free models take PUBLIC work only (the owner's acceptance, D-93). Both repositories are private, so as they stand only Claude Code
may build or test them. The specs and the tests hold no private data (every row is made up), so a public copy would break no rule, but the owner has chosen
private for both. This is the first open question below.

## Decisions log

- 2026-11-25 (the guide, G-0068 and G-0070): the specs are harness neutral, one pull request, before any other new pull request; A and B run on Claude Code,
  OpenCode and Muse while Kiro is on pause (G-0067).
- 2026-11-25 (owner): B lives in its own private repository, `link-checker`.

## Open questions

- **Q-p1.** May OpenCode and Muse work on A and B? The rule says public work only and both repositories are private. Recommendation: make B public (a link checker
  holds no private data and could be shown in a video), keep A private and build A with Claude Code; or, for A, a public copy of the spec and the made-up tests only.
- **Q-p2.** B's spec is not on its `main` yet (PR 1). Recommendation: the owner merges PR 1 so every harness starts from the same files.
- **Q-p3.** The guide asked for about ten tests each; there are 17 each, because the exact output, the error cases and the no-network rule are each worth a test.
  Recommendation: keep 17.
