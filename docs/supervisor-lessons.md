# Supervisor lessons (N8, L1: the numbered source)

## Purpose

These are the standing lessons of the umwayi-os supervisor, written down so that its own Claude Code supervisor can use them without an outside guide. They came from mistakes and owner decisions between 2026-11-13 and 2026-11-23. This page is the SOURCE of the guidance entries of task L1: each entry in `guidance.yaml` points at one numbered line below and holds the SHA-256 of that line, so a changed lesson stops the loader until the owner reads the change.

Each line starts with its number in its section, then in brackets the lesson id, the kind and the tier.

- **Kind.** E means enforce: a test or check exists or is planned. A means advise: a prompt line, checked at review. O means owner only.
- **Tier.** 1 safety, 2 owner decisions, 3 hub rules, 4 builder rules, 5 practices, 6 advisory lines. The lower number wins.
- Which E lessons have a test today is in [lessons-as-checks.md](lessons-as-checks.md) (A1 to A14). The others are marked E because a check is planned, not because one exists: an entry that names no test is not shown as enforced by code.

Nothing here names a private item. Employer data, companies the owner applied to, journals and account details are left out on purpose.

## Current state

The lessons, word for word from the owner's Project note of 2026-11-23, with the lesson id, kind and tier added. This page is a source for the loader, not yet read by it: the entries that point at it are the next pull request of L1.

### Lessons A (CI and merge rules)

1. [A1, E, tier 4] docs/testing.md stays under 300 lines. Fold bullets. Check: the docs test.
2. [A2, E, tier 4] Never hand edit tools/ci_shards.json. Regenerate with the shard tool, then run tests/test_ci_shards.py.
3. [A3, E, tier 4] A new test file needs its line in tools/ci_map.json.
4. [A4, E, tier 4] The text "pty." is banned in umwayi/goalrun.py. Avoid words such as "empty." at the end of a sentence there. Check: tests/test_automation.py.
5. [A5, E, tier 4] KNOWN-LIMITS numbers are unique. Take the next free number from the file when you start, and renumber if another PR took it (last used: 333).
6. [A6, E, tier 4] Keep every row of the status-log table on every rebase. Check: the row set may only grow.
7. [A7, E, tier 4] Run merge_main before every push, and on every open branch right after any merge. A merge makes every other open branch conflict in docs/status-log.md and tools/ci_shards.json.
8. [A8, E, tier 4] Run tests/adapters and the docs tests when a change touches tests, rules examples or docs, not only the new test. The affected-tests map should say so.
9. [A9, A, tier 4] Every number in a logbook entry needs a test that makes it nonzero from a real event. A planted fault that never fires proves nothing. (Source: guard_n never set, PR 176.)
10. [A10, E, tier 4] A "tested with" line says only what was run. A fake is a fake. Say "no real run" where there was none. Check: the honesty scan.
11. [A11, A, tier 4] Before reading an empty result from a Docker run, check that the Docker daemon is up.
12. [A12, E, tier 4] Recurring conflicts in generated files are cleared by tooling, not avoided by running fewer sessions (owner, 2026-11-13). Build one merge helper: regenerate ci_shards.json, union the status-log rows, then run the checks.
13. [A13, A, tier 4] Before designing a feature that needs a kernel or OS feature, probe whether the build machine has it (Landlock returned errno 38 in the container). If it does not, split the task: the part that can be tested now, then the part that needs the real kernel. State the split in the PR.
14. [A14, E, tier 4] Never claim a result from a skipped test. The CI log must show whether kernel-dependent tests ran.

### Lessons B (CI pacing)

1. [B1, O, tier 2] CI runs only on the PR that is next to merge (owner, 2026-11-15). A PR not next in line does not trigger CI. Build it with draft PRs or a "ready" label that starts the full run, plus a concurrency group with cancel-in-progress, a docs-only path that skips the full matrix, and no double run per push (push and pull_request). Reason: a free account runs about 20 jobs at once, one PR runs about 10, so four open PRs queue.
2. [B2, E, tier 4] At most two PRs run CI at once. The supervisor opens the next PR as a draft until the one ahead has merged. (Proposed by the guide on 2026-11-23, owner to confirm.)
3. [B3, A, tier 4] Separate rule, kept: if four PRs wait for the owner, stop starting new owner-stop tasks and report. Docs-only and test-only tasks do not count. B2 is about CI load, B3 is about owner load.
4. [B4, E, tier 4] Order of merges is the guide's call: docs-only first, then the smallest owner-stop PR, so each merge makes the fewest later conflicts.

### Lessons C (owner standing rules)

1. [C1, E, tier 2] Commits and PRs for umwayi-os carry no "Generated with Claude" lines and no Co-Authored-By trailers (owner, 2026-11-16). Commits use the owner's own git identity. Check: a commit and PR text scan.
2. [C2, E, tier 2] Protect main. Feature branches, good commits, pull requests. Never push to main. One task, one branch, one worktree, one fresh session.
3. [C3, E, tier 2] Every question to the owner carries a recommendation. For answers that depend on data the owner cannot test, give a best guess and describe it so he approves only if it makes sense. Recommendations are broad bands (ranges and defaults) or limited to their use case, so they do not block other implementations (owner, 2026-11-17).
4. [C4, A, tier 2] Timelines are guidelines. Work may start earlier than its dated slot. No date is dropped. The hard limits are the Devpost cut-off (Dec 4, 14:00 Pacific), the owner stops, and the honesty rule. (Owner clarification 2026-11-23.) Failure record F8: the guide read "guidelines" as "dates lifted" and had to be corrected. Lesson: when a clarification can be read two ways, restate it and get agreement before acting.
5. [C5, E, tier 2] Auto queue: the queue runs by itself, including PR review and merge. Anything that needs the owner (conflicts, open decisions) goes on an open questions list with a recommendation, and work continues (owner, 2026-11-17).
6. [C6, E, tier 2] No idle helper sessions. When one is free, give it the next queue task. When in scope tasks run out, promote out of scope tasks, unless the owner says otherwise (owner, 2026-11-16).
7. [C7, E, tier 2] Stalled or hung sessions are found by deterministic rules, using the helper's own CLI (not browser tricks), and the probe restarts a stalled session itself (owner, 2026-11-16). The design never assumes the outside guide exists. Anything that depends on the current build setup is marked as a temporary workaround.
8. [C8, E, tier 2] After every task and every stop, the builder writes a feedback entry: branch, head SHA, PR number, CI result, what stopped for the owner, limits numbers used, what it could not do, surprises, and a recommendation next to every open question. The supervisor reads it at the start of each review.
9. [C9, A, tier 2] Do it yourself first. Before asking the owner for a screenshot, check or file, confirm the system cannot do it itself. Ask only if it truly cannot.
10. [C10, A, tier 2] Do not be preemptive. No follow-up drafts, extra audits or extra reproductions until asked or a thread raises something already solved.
11. [C11, E, tier 2] Reuse each tool's strengths and build on what is provided instead of reinventing it. Question to ask in every feature: are we doing that? (owner, 2026-11-04)
12. [C12, E, tier 2] Free tier and subscription first. Pay-as-you-go API billing is only an option to consider later. Applies to every integration and model choice.
13. [C13, E, tier 2] Decisions go to the council or an LLM board with different models. The decision record names the result. The council also checks the owner's own answers. Outside criticism (an article, a post) gets the same review, and each finding becomes a queue item with a recommendation.
14. [C14, E, tier 2] Update Notion and the hub alongside the work, so a change can be reverted. The PR report has a Notion link field.
15. [C15, E, tier 2] Before any project goes live: ask whether we are really going live, then run security scans and fix what they find.
16. [C16, E, tier 2] Record every test (browser, terminal, agent and goal runs). Store the recording in the recordings folder. Keep an index that says which recording is which and which script goes with it.
17. [C17, A, tier 2] Read a page that fetch tools cannot read in the browser before judging it.
18. [C18, O, tier 2] Public content never names companies the owner applied to or interviewed with. Private items stay out of the public repo. A deny list of names is kept outside the repo. Employer data is never copied into the repo, docs or memory.
19. [C19, O, tier 2] Credentials, tokens, purchases, accounts, publishing, sign-ins: stop and report. Never type or store one. The owner submits to Devpost, nobody else.
20. [C20, E, tier 2] The honesty rule: no doc, post or video says "enforced" or "sandboxed" until one real enforced run (W40) has finished a goal. The text says "cooperative today, enforced where built". Only the owner sets REAL_ENFORCED_RUN_DONE to True.
21. [C21, E, tier 2] Do not end a turn after a report while a task is pending and the queue is low: build the next task first, then end (owner, 2026-11-24). Check: `umwayi pr queue next --check`.

### Lessons D (supervisor working lessons)

1. [D1, A, tier 6] A merge button that stays disabled with "checking" may hide real conflicts. Reload the PR page before waiting.
2. [D2, A, tier 6] Read the diff of every PR. Merge only on green CI, no conflicts, and for owner-stop PRs only on the owner's word or a standing rule.
3. [D3, A, tier 6] After any merge, check the other open PRs for conflicts and ask the builder to run merge_main.
4. [D4, A, tier 6] When CI is slow, check the queue (runner limits) before blaming the tests.
5. [D5, E, tier 4] A rule learned from a mistake becomes a rule only after it is vetted. Same mistake twice means the rule did not work: flag both failure records.
6. [D6, E, tier 4] Rules only tighten. No learned rule makes the system more permissive. Graded autonomy is the only mover toward Yes.

### How the supervisor uses the lessons

1. The lessons live in the repo as guidance entries (id, tier, kind, rule, check, source, review_by).
2. The task card for each task lists the entries that match the files the task touches (A entries for CI work, C entries always).
3. The prompt lists advise lines in tier order and drops the lowest tier first when it is too long. Enforce entries are never dropped.
4. Each entry has a `review_by` date. When it passes, `umwayi guidance list` marks the entry as due.
5. A new lesson is proposed by the supervisor after a failed CI run, a conflict or an owner correction. It is written only after the owner approves.
6. Where a rule is only a prompt line, the text says it is cooperative.

## Decisions log

- 2026-11-24 (owner): the lessons go into `guidance.yaml` in two pull requests. First this page and the loader change (`review_by` and `test`); then the entries.
- 2026-11-24 (this page): the lessons are numbered per section so that each is one line a hash can cover.

## Open questions

- **Q1.** E lessons with no test yet (most of C and D). Recommendation: the entry says `kind: advise` until a test exists, and moves to `enforce` with a `test` key in the same pull request that adds the test. The loader then never shows a lesson as enforced when nothing fails.
- **Q2.** Prompt length. Forty four lines in the prompt are too many. Recommendation: the task card lists only the entries that match the files of the task (item 2 above), and the lowest tier is dropped first (item 3).
