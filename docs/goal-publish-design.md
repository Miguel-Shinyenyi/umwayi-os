# Goal publish: umwayi-os pushes its own task branch and opens the pull request

## Purpose

On 2026-11-26 the owner built Project A (a public repo, `mpesa-statement-analyzer`) through `umwayi goal`. The builder's branch exists only on the owner's Mac. The owner said umwayi-os should push such a branch and open the pull request by itself, without the owner or the builder asking. Today it cannot: the supervisor never pushes. This note says what exists, gives options, and recommends one. Docs only: nothing is built.

## Current state

- **The supervisor never pushes.** `umwayi/goalrun.py` says in its first lines that it never runs `git push`, `merge`, `rebase`, `pull`, `fetch`, `reset`, `clean`, `checkout`, `switch` or `branch` (the builder's worktree and branch are made by `goalgit.py` through a fixed list of git questions). A finished task stays on a local branch `umwayi/G-T`, with a report that says what waits for the owner.
- **`umwayi pr queue` never pushes or merges** either; it lists and says what to do next.
- **A helper's `git push` is already refused:** the starter rule `cc-no-push-main` is No for a push to main, and the builder rules allow only `git status`, `git diff`, `git add`, `git commit` and the tests.
- **What the owner saw:** after a recorded build of Project A task T-01, no branch and no pull request on GitHub, and no CI, because the repo has no workflow file (a workflow is its own task).
- **What has been done by hand instead** is the builder (a Claude Code session) pushing and opening the pull request. That is the thing the owner does not want: a person or a chat in the middle.

### Options

1. **The supervisor publishes after the guide accepts.** When a task reaches `in review` (builder done, tester passed, guide check `accept`), umwayi pushes the branch `umwayi/G-T` (never `main`) and opens a draft pull request whose text is built from the goal report and the story files (counts only, no helper output). A new rules action `goal_publish` (with `goal`, `task`, `repo`, `branch`) is asked first; no rule means Ask me first, so nothing is published until the owner writes a Yes rule for that repo. Credentials: umwayi uses the owner's own `gh` login and never reads or stores a token.
   For: it is what the owner asked for, and the gate, the logbook and the owner's rule stay in the loop. Against: it is the first time umwayi pushes, so it is an owner stop, a new rules action, a change to a guard file (the never list in `goalrun.py`) and mutation tests; a push to a public repo publishes the content, so the rule must name the repo and the check that the repo is public.
2. **An owner command.** `umwayi goal publish G T` on the owner's terminal pushes and opens the draft pull request. For: smaller; the owner types one line. Against: it is still the owner or a chat in the middle, which is what he said he does not want.
3. **Status quo.** The builder session pushes. Against: it is the thing to remove.

### Recommendation

Option 1, as a small chain of pull requests, each an owner stop: (a) the `goal_publish` action and its test (no push yet), (b) the push of a branch other than `main`, behind the action, (c) the draft pull request text from the report. CI for the target repo stays its own task, built through a goal like any other change.

## Decisions log

- 2026-11-26 (owner, in chat): umwayi-os should push and open the pull request on its own. Not yet decided: which option, and the rule that allows it.

## Open questions

- **Q-p1.** Option 1 or 2? Recommendation: option 1 with a Yes rule per repo that the owner writes by hand.
- **Q-p2.** May umwayi use the owner's `gh` login for the push? Recommendation: yes, through the `gh` command only; umwayi never reads, copies or logs a token.
- **Q-p3.** Should a task be published before the guide's check says accept? Recommendation: no, only after accept, so an unreviewed build is not public.
