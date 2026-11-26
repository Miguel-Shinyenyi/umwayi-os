# GitHub access for umwayi-os: watch, review CI, merge and fix

## Purpose

The owner asked (2026-11-26, rows G-0115 to G-0119) that umwayi-os itself watch its pull requests, read their CI, merge them and fix what fails, so that a person or a chat session is not in the middle. This note designs that in four steps, each its own later owner stop pull request, and labels every layer honestly. Docs only: no code, no token, no `gh` call, nothing is built. It goes with [the goal publish note](goal-publish-design.md), which covers the push of a task branch.

## Current state

- **The supervisor never pushes, merges, fetches or pulls** (`umwayi/goalrun.py`). A finished task stays a local branch. Step 1 of goal publish (PR 270) only adds the rules action `goal_publish`; it publishes nothing.
- **A helper cannot push to `main`:** the starter rule `cc-no-push-main` is No, and the builder rules allow only five commands.
- **Who watches pull requests today:** the builder tools `tools/pr_open.py`, `tools/pr_watch.py` and `tools/merge_main.py` are run by a Claude Code chat session on the owner's Mac, with the owner's own `gh` login. They are not part of the `umwayi` runtime, and nobody merges but the guide or the owner.
- **GitHub's own rules (as the guide reported them on 2026-11-26, not checked by this note):** umwayi-os has an active ruleset on `main` with the required check `result`, no force push, no deletion and an empty bypass list. mpesa-statement-analyzer has an active ruleset with no deletion, no force push, a pull request required and 0 approvals, but no required check, because that repo has no CI yet. This is GitHub enforcing; umwayi-os does not enforce it.
- **The W9 rule today:** a failed or stopped task halts the goal and nothing retries (`docs/goals.md`, 2026-11-12). Step 4 below changes that for fix tasks only.

### The four steps (each an owner stop pull request, in order)

1. **Watch, read only.** umwayi runs `gh pr list` and `gh pr checks` through the `gh` command and writes nothing to GitHub. A new read action asks the rules first; no rule is Ask me first.
2. **Review CI.** umwayi records, in the logbook and as counts only, the state of each required check and whether the pull request has conflicts. It never copies a check's log text into a file or a prompt except as data in step 4.
3. **Merge.** A new rules action `goal_merge` (goal, task, repo, pull request number). No rule is Ask me first; a Yes needs a rule the owner writes that names the repo; graded autonomy can never move it. Before any merge umwayi **reads the repo's ruleset** (`gh api`, read only) and refuses with a fixed reason if the ruleset is missing, not active, or lacks the required check; no ruleset means Ask me first, never Yes. It merges only when the required check is green, there are no conflicts and the base is `main`. A pull request that changes code, a tool, a command, a workflow, a rule file, a guard file, a prompt or a budget file is an owner stop and never merges without the owner's word; only docs only and test only pull requests merge on green (the rule of 2026-11-24). One logbook entry per ruleset read and per merge. The kill switch stops every step.
4. **Fix.** A failed required check or a conflict starts a **fix task**: a normal goal task, under the gate and the budget governor, in a worktree of the pull request branch. At most 2 fix tries per pull request, then it stops and tells the owner. Never a force push, never a change to `main`. A fix may not edit or delete a test, a workflow, a rule or a budget file to get green. A conflict in a guard file stops for the owner. `main` is merged into the branch only by a fix task, with a logbook entry. Each fix has its own budget cap. The failing check text is shown to the agent as data, never as instructions.

### The layers, and what is true today

| Layer | What it is | Label today |
| --- | --- | --- |
| 1. GitHub side | Branch rules on `main`: required check `result`, no force push, no deletion, no merge with conflicts. The owner or guide sets them in the repo settings; umwayi reads them. | Enforced by GitHub where the ruleset is active; umwayi enforces nothing here. |
| 2. Push and merge in the supervisor | The push and the merge run in the supervisor process, never in the agent; the agent gets no `gh` login and no network. | Cooperative today. The helper's network is open (limit 344) and its environment is scrubbed only in enforced mode, which is not built on this Mac. |
| 3. Fix agents in a confined run | Fix agents run in the Landlock run on Linux (PR 190). | Built for Linux, but no real enforced run has been done: `REAL_ENFORCED_RUN_DONE` is False, so no text may say enforced. |
| 4. Credential | The owner's own `gh` login, or a fine grained token limited to named repos. umwayi never reads or stores it. | Not built. |

**The Mac gap, said plainly.** The owner works on a Mac. There is no Landlock on a Mac, and the Seatbelt route is refused until the owner's Mac check. So on the Mac a fix agent is guarded only by the hook gate, which is cooperative, plus the sandbox of its own platform. Nothing here may be called enforced on the Mac. The honest options are in the open questions.

## Decisions log

- 2026-11-26 (owner, 09:20 to 09:30, rows G-0115 to G-0119): umwayi-os should watch, review CI, merge and fix; the design should be enforced where it can be and say plainly where it is not; umwayi must read the repo's ruleset before any merge. This note is the design only.
- 2026-11-26 (this note): four steps, each its own owner stop pull request; the W9 no-retry rule changes only for fix tasks, at most 2 tries, and only with the owner's yes.

## Open questions

- **Q-g1.** May a fix task retry at all, given the W9 rule of 2026-11-12 (halt on failure, no automatic retry)? Recommendation: yes, as a new kind of task with its own cap of 2 tries and a stop that tells the owner, and the rule text in `docs/goals.md` says so in the same pull request.
- **Q-g2.** Credential: the owner's full `gh` login, or a fine grained token limited to named repos? Recommendation: the fine grained token, limited to the repos that opt in, with only the permissions the step needs (read for steps 1 and 2; pull requests and contents write for steps 3 and 4), passed by name from the owner's keychain and never written to a file or a log. The full login stays out of umwayi.
- **Q-g3.** On the Mac, fix agents are cooperative only. Which way? Recommendation: run fix agents on a Linux machine (a CI runner or a container) where Landlock exists, and keep the Mac to steps 1 to 3 (read and merge in the supervisor, no agent); until a real enforced run, say cooperative.
- **Q-g4.** Which repos opt in first? Recommendation: umwayi-os, then mpesa-statement-analyzer once it has CI and a required check in its ruleset.
- **Q-g5.** Docs only pull requests may merge on green by rule; does the owner want even those to wait for a rule per repo? Recommendation: yes, the `goal_merge` rule is per repo and the owner writes it by hand.
