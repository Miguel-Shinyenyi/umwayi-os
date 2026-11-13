# Kiro issues log

## Purpose

This page records problems the builder sessions hit while working on umwayi-os, one section for each, so the same mistake is not made twice. Each entry says what happened, what was done and what to do next time. The owner reads it. Nothing reads it to decide anything. It is linked from [testing.md](testing.md).

## Current state

Four entries, newest first. Each has a status: fixed, fixed and watched, or open.

### 4. PR 92: guidance.yaml pins steering lines by hash

- What happened: PR 92 changed rules 2 and 3 of `.kiro/steering/builder-workflow.md`. `guidance.yaml` pins both lines by hash (entries `merge-main-before-push` and `known-limits-next-free-number`), so the loader stopped with `SourceChanged` and CI went red on all four Python versions.
- Fix: new text, prompt_line and source_hash for both entries, in a second commit.
- Lesson: change a steering line and its guidance entry in the same commit. Rule 9 of the builder workflow now says so.
- A limit of the pin: the hash covers only the first line of a rule. A sentence on a later line of the same rule changes no hash, so the loader would not notice it.
- Status: fixed.

### 3. PR 91: a golden test depended on the length of its path

- What happened: a golden test of the worktree work (PR 91) compared a logbook line that umwayi cuts at 300 characters. How much of the line was kept depended on the length of the path the test ran in, so it passed in one place and failed in another.
- Fix: the test compares the line up to the shorter of the two cuts (commit 6c76b85).
- Lesson: a test that compares text cut by length must not depend on where the test runs.
- Status: fixed.

### 2. A stale progress page failed CI

- What happened: `ui/dist/progress.html` was committed, and `ui/dist/build.json` held the hash of what it shows. Every pull request that added a status row, ticked a box or added a limit made the page stale, so CI failed on a file the pull request did not mean to touch.
- Fix (W22, PR 94): the page is built by `node build.mjs` and is not committed. `build.json` holds no hash of it.
- Not done: no deploy workflow exists, so nothing yet builds or publishes the page.
- Status: fixed. Limits 265 and the W22 limit say what is left.

### 1. The climap-phone ENOTEMPTY flake

- What happened: `ui/test/climap-phone.test.mjs` sometimes failed when it removed a temporary folder while the browser was still closing (ENOTEMPTY).
- Fix: the browser close retries the removal (PR 90, `ui/test/browserclose.test.mjs` checks it).
- Status: fixed and watched. If it comes back, the close retry is the first place to look.

## Decisions log

- 2026-11-13: one page for all entries, newest first, one section for each, so a later entry is added at the top of Current state and the numbers keep counting up.
- 2026-11-13: the entries were written by the builder from the pull requests and the CI logs. The owner has not reviewed them.

## Open questions

- Should the page also list the CI run and the commit for each entry? Recommendation: yes, once there are more than ten entries; for four it adds noise.
