# A deterministic merge-ready check (W63, design note)

## Purpose

The owner's point: the merge gate must not depend on the guide reading carefully. This note designs `python -m tools.merge_ready PR`. It gives pass or fail from fixed rules, with no judgement. It is meant to run as a required CI check and to be run by the guide before every merge.

It is a design note only. Nothing here is built. No code, steering file, rules gate, safety check, workflow or ruleset changes with it.

## Current state

Read at main `7bca468` and on GitHub on Nov 16, read only:

- **The ruleset.** The repo has one active ruleset, "main requires result" (id 27314271). It requires the status check `result`, refuses a non-fast-forward and a deletion of main, and has no bypass actors. `strict_required_status_checks_policy` is false, so GitHub does not require a branch to be up to date with main.
- **The `result` check.** `.github/workflows/ci.yml` has four jobs: `plan`, `test`, `node` and `result`. `result` runs `python -m tools.ci_shards verify` and is the only check the ruleset requires. The workflow has `permissions: contents: read`.
- **The builder's GitHub identity.** In the builder's sandbox, `gh api user` returns `Miguel-Shinyenyi`, the owner's account. So anything the GitHub API lets that account do is something an agent can do too. That includes a review, a label or a comment. None of them can be the owner flag (see below).
- **Commits.** The builder's commits are by `Kiro Agent` and are unsigned (`%G?` gives `N`). The sandbox has no SSH keys.
- **Existing checks the tool can call in its own process:**
  - `umwayi.goaldocs.check` (the docs check);
  - `tools/ci_map.py` (the map check);
  - `tools.ci_shards.assignment_problems` (the shards check);
  - the em dash rule of `tests/test_docs.py`.
- **Limits numbers.** A limits part gets its `number:` line from `umwayi goal docs build`, which `tools/merge_main.py` runs. So after a merge of main, the parts on a branch are numbered. The rule "unnumbered before the build" must therefore look at the part as it was first committed (rule 8 below).
- **PR body sections.** builder rule 8 asks for Built, Not built and Could not verify. Recent pull requests use What changed, Checks run and Not verified. W62 open question 5 asks the owner to pick one set.

## The rules

Every rule runs. The report has one line per rule. The exit code is the worst result: 2 beats 3, and 3 beats 0.

| # | rule | reads | decides | exit if not met | planted fault |
| --- | --- | --- | --- | --- | --- |
| 1 | the `result` check is green on the head | the check runs of the head SHA (API) | a check run named `result` with `status: completed` and `conclusion: success`, on exactly the PR's head SHA | 2 failed or cancelled; 3 queued, in progress or missing | accept a `result` of an older SHA |
| 2 | mergeable and clean | the PR (API): `mergeable`, `mergeable_state` | `mergeable` is true and `mergeable_state` is `clean`. In CI mode (`--ci`), `blocked` also passes, but only when the one required check not yet green is `merge-ready` itself | 2 `dirty` (conflicts) or `mergeable: false`; 3 `null` or `unknown` (GitHub has not computed it) | treat `unknown` as clean |
| 3 | the branch contains main | the compare of main's SHA with the head (API) | `behind_by` is 0 | 2 behind; 3 the compare cannot be read | compare against the PR's base SHA instead of main's current SHA |
| 4 | changed paths are inside the allowlist | the PR's changed paths (git) and `tools/merge_ready.json` | each path matches an `allowed` pattern and no `protected` pattern; a protected path passes only with a valid owner flag for that path at the head | 2 | match a pattern as a prefix of a longer folder name |
| 5 | no em dash in changed files | each changed file at the head (git), decoded as UTF-8 | no U+2014 in any added or changed file (a deleted file is not read) | 2, with the path and line number, never the line | read only the diff lines |
| 6 | no em dash in the PR text | the PR title and body (API) | no U+2014 | 2 | read the body only |
| 7 | the PR body has the sections, and no attribution | the PR body (API) and the commit messages of the PR (git) | every section heading of the allowlist file is there, once, as a `##` line. No line contains "Generated with" followed by Claude or Claude Code, in any case. No commit has a `Co-Authored-By:` trailer naming Claude | 2 | find the heading anywhere in a line |
| 8 | limits parts unnumbered before the build | for each `docs-parts/known-limits/*.md` the PR adds, its content in the first commit that adds it (git) | that first version has no `number:` line | 2 | read the head version, which the build has numbered |
| 9 | tests registered | `tools/ci_map.json`, `tools/ci_shards.json` and the test files at the head | the map check and the shards check of today pass, called in the same process | 2 | call the map check only |
| 10 | docs check clean | the docs parts and the generated files at the head | `goaldocs.check` returns 0 | 2 | skip the limits file |
| 11 | the PR is open and not a draft | the PR (API): `state`, `draft` | open and not a draft | 2 | accept a draft |

Usage and config problems give 64 before any rule runs: a bad PR number, a missing or malformed `tools/merge_ready.json`, or no git repository.

## Where the PR data comes from

- **The GitHub REST API, read only, `GET` only:**
  - `GET /repos/{owner}/{repo}/pulls/{n}`: `state`, `draft`, `title`, `body`, `head.sha`, `head.ref`, `base.ref`, `mergeable`, `mergeable_state`.
  - `GET /repos/{owner}/{repo}/commits/{head_sha}/check-runs`: `name`, `head_sha`, `status`, `conclusion`.
  - `GET /repos/{owner}/{repo}/branches/main`: `commit.sha`.
  - `GET /repos/{owner}/{repo}/compare/{main_sha}...{head_sha}`: `behind_by`.
- **The token.** It is read from `GITHUB_TOKEN` (CI's read-only token) or `GH_TOKEN`. It is never printed or logged. The requests use the standard library (`urllib.request`), with a 10 second timeout per request and at most 8 requests.
- **Git, read only:** `git diff --name-only BASE...HEAD`, `git show SHA:PATH`, `git log --format=... BASE..HEAD` and `git log --diff-filter=A --format=%H -- PATH`. The arguments are a list and no shell is used. In CI the checkout needs the full history (`fetch-depth: 0`).
- **Fail closed.** No network, a timeout, an HTTP error, a rate limit (403 or 429 with `x-ratelimit-remaining: 0`), a reply that is not JSON, or a field that is missing or has the wrong type all give exit 3: "cannot decide, stop and ask". Never pass and never fail on a guess.
- **Where the code lives.** It lives in `tools/`, not in `umwayi/`. The core package stays free of network modules (`tests/test_system.py` `CodeTests.test_no_module_imports_a_network_library`). It would be the first network reader in `tools/` (open question 4).

## The allowlist

One file, `tools/merge_ready.json`, read strictly (unknown key, repeated key or wrong type is 64):

```json
{
  "version": 1,
  "allowed": ["umwayi/", "tests/", "tools/", "docs/", "docs-parts/", "ui/", "site/", "adapters/", "articles/",
              ".kiro/specs/", "README.md", "PROJECT.md", "pyproject.toml", "guidance.yaml", "rules.yaml",
              "agents.example.yaml", "autonomy.example.yaml", "goal.rules.example.yaml", "LICENSE"],
  "protected": [".kiro/steering/", ".github/", "rules.yaml", "umwayi/rules.py", "umwayi/kill.py",
                "adapters/common/umwayi_gate.py", "adapters/claude_code/hook.py", "adapters/kiro/hook.py",
                "adapters/stdio/hook.py", "adapters/opencode/plugin/", "guidance.yaml", "tools/merge_ready.json",
                "tools/merge_ready.py", "tools/ci_shards.py", "tools/ci_plan.py", "owner-approvals/"],
  "sections": ["What changed", "Checks run", "Not verified"]
}
```

- A pattern that ends in `/` is a folder and matches the paths under it. Any other pattern is one exact path. There are no wildcards.
- A path in no `allowed` pattern fails. A path in a `protected` pattern needs the owner flag, even when it is also allowed.
- The file protects itself. The tool and the shard verifier that `result` runs are protected too.
- The exact lists are the owner's decision (open question 2). The list above is a starting proposal. "The rules gate" is read as the rules file, the reader, the kill switch and the adapter hooks. "The safety checks" are read as the files that decide or verify a pass.

## The owner flag

The owner flag must be something an agent cannot make. A GitHub review, label or comment does not qualify: the builder's token is the owner's account. GitHub also does not let an author approve their own PR.

The proposal is a **signed approval record**:

- **The record.** A file `owner-approvals/BRANCH.txt` in the PR, with one line per protected path: `path SHA` (the git blob SHA of that path at the approved state, or `deleted`).
- **The signature.** The commit that last changed the record must be signed with a key listed in `.github/owner_signers` (git's allowed signers format). The tool checks it with `git verify-commit` and `gpg.ssh.allowedSignersFile`, a git read command. The owner signs on their own machine, by typing the commit there. The key never reaches a sandbox.
- **What passes.** For each protected path the PR changes, the record names that path with the same blob SHA as at the head. A later change to the path after approval breaks the match, and the rule fails again.
- **The signers file.** `.github/owner_signers` is protected. A change to it needs a record signed by a key from the old file.
- **Not trusted:** an unsigned record, a record signed by another key, a record for another branch, or a path not listed in it.

## Exit codes

Only 0, 2, 3 and 64:

- 0: every rule is met; merge-ready.
- 2: a rule is broken, or an unexpected error happened.
- 3: cannot decide (no network, a rate limit, a check still running, `mergeable` not computed, a git object missing).
- 64: usage or config.
- Never 1.

## What it logs

It prints one line per rule: the rule number, `pass`, `fail` or `cannot decide`, and counts. For example, `4 fail: 2 protected paths without an owner record`, or `5 fail: docs/x.md line 12`. Never a file's content, a line of the PR body, a commit message or the token.

In CI the same lines go to the job summary. It writes no file in the repo and no logbook entry. CI has no umwayi root, and the guide's local run is read only.

## What it never does

- It never merges, approves, comments, labels or writes anything to GitHub. It only sends `GET` requests.
- It runs no shell, and no process except the git read commands listed above.
- It never changes a ruleset, a workflow, the allowlist or a steering file.
- It never fetches or pushes git refs.
- It never decides on a guess. An unreadable value is 3.
- It is never a reason to skip the owner's or the reviewer's reading.

## What it cannot decide

These stay with the owner or the reviewer, and the tool says so in its last line:

- whether a claim in a design note, a status part or a PR body is true or invented;
- whether a test proves what its name says, or tests the right thing;
- whether a design, a rule or a trade-off is wise;
- whether the allowlist, the protected list or the required sections are right;
- whether an owner-signed change to a protected path is safe (the signature shows who approved, not that it is good);
- whether the work is the task that was asked for, or more or less than it.

## Spec lines it would add or change

Added, a new section at the end of requirements.md, `### W63.R1` to `### W63.R6`:

- **W63.R1 The command.** `python -m tools.merge_ready PR [--ci] [--repo OWNER/NAME]`, with the eleven rules of the table, every rule run and reported.
- **W63.R2 The data.** The four `GET` endpoints and the git read commands above. Anything unreadable is exit 3, never a pass.
- **W63.R3 The allowlist.** `tools/merge_ready.json` with `allowed`, `protected` and `sections`, read strictly. The file and the tool are protected.
- **W63.R4 The owner flag.** A record in `owner-approvals/`, in a commit signed by a key of `.github/owner_signers`, binding each protected path to its blob SHA. A GitHub review, label or comment is never the owner flag.
- **W63.R5 Exit codes and output.** 0, 2, 3 and 64. One line per rule with ids and counts only.
- **W63.R6 What it never does,** and what it cannot decide, as above.

Changed, only when the owner approves open question 1:

- `docs/testing.md`, "CI since W20": a fifth job `merge-ready`, after `result`, required by the ruleset.
- W62 (`tools/pr_body.py`, the PR body check) is merged into rule 7 here, so the PR body is checked in one place.

## The tests it would need

All of them use recorded JSON replies and a temporary git repo, so no test uses the network.

| rule | test | planted fault |
| --- | --- | --- |
| 1 | `test_result_must_be_green_on_the_head_sha` | accept a green `result` of an older SHA |
| 1 | `test_a_running_result_is_3` | treat `in_progress` as green |
| 2 | `test_unknown_mergeable_state_is_3` | treat `unknown` as clean |
| 2 | `test_blocked_passes_in_ci_only_when_merge_ready_is_the_one_missing_check` | pass `blocked` with another check red |
| 3 | `test_a_branch_behind_main_fails` | compare with the base SHA |
| 4 | `test_a_protected_path_without_a_record_fails` | skip the protected list when the path is allowed |
| 4 | `test_a_pattern_is_a_folder_or_an_exact_path` | `docs/` matching `docsx/a.md` |
| 4 | `test_an_unsigned_or_foreign_signed_record_fails` | accept any signature |
| 4 | `test_a_path_changed_after_approval_fails` | compare paths, not blob SHAs |
| 5 | `test_an_em_dash_in_an_unchanged_line_of_a_changed_file_fails` | read only diff lines |
| 6 | `test_an_em_dash_in_the_title_fails` | read the body only |
| 7 | `test_each_section_heading_is_required_once` | find a heading inside a sentence |
| 7 | `test_generated_with_and_co_authored_by_claude_fail` | case sensitive match |
| 8 | `test_a_part_numbered_in_its_first_commit_fails` | read the head version |
| 9 | `test_an_unregistered_test_file_fails` | run only the map check |
| 10 | `test_a_stale_generated_doc_fails` | skip the limits file |
| 11 | `test_a_draft_fails` | accept a draft |
| data | `test_no_network_rate_limit_and_bad_json_are_3` | return 0 on a timeout |
| never | `test_only_get_requests_and_git_read_commands` (an `ast` scan and a spy) | send a `POST` |
| output | `test_no_token_body_or_file_text_in_the_output` | print the body line that failed |
| exit codes | `test_exit_codes_are_0_2_3_64_only` | a crash exits 1 |

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-16 | Design note only. Eleven fixed rules. Unreadable data is exit 3. The owner flag is a signed record, because the builder's token is the owner's GitHub account. The tool only reads | W63, the owner's point of Nov 16. |

## Open questions

1. **Should `merge-ready` run as a required CI check?** That needs a new job in `.github/workflows/ci.yml` (after `result`, with `fetch-depth: 0`, `contents: read` and `pull-requests: read`) and a change to the ruleset "main requires result", so that it requires `merge-ready` too. Both stop for the owner and are not changed here. Recommendation: yes, after the tool has run by hand on five merged pull requests without a false fail. Keep `result` required as it is.
2. **The allowlist and the protected list.** Recommendation: start with the lists above, and let the owner cut or add before the build. Changing the file later needs an owner record, because it protects itself.
3. **The owner flag.** A signed record needs the owner to sign one commit per protected change on their own machine. Recommendation: yes, as proposed. A GitHub review cannot work while the builder's token is the owner's account. If the builder later gets its own GitHub account, an owner review on the head SHA could replace the record. That is a new decision.
4. **A network reader in `tools/`.** Recommendation: allow it for this one tool, by name, and add a test that no other file in `tools/` imports a network module. The core package stays as it is.
5. **The required sections.** Recommendation: What changed, Checks run and Not verified, as recent pull requests use. Decide W62 open question 5 at the same time, because builder rule 8 names other headings and is a steering line.
6. **Should a merge commit made by GitHub be signed?** Not needed for these rules. GitHub signs its own merge commits (`%G?` gives `E` here, because the key is not known locally). Recommendation: leave it.
