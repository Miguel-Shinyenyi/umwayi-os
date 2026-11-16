# A deterministic merge-ready check (W63, design note)

## Purpose

umwayi-os runs by itself, with its own internal supervisor, and it never assumes an outside reader. So the decision "may this pull request be merged" must come from one deterministic command, not from someone reading carefully. This note designs that command, `python -m tools.merge_ready PR`. It prints pass or fail for each rule, with the reason, and exits 0, 2, 3 or 64. It has no judgement and no second reading of a value. The supervisor or the owner runs it. The merge itself stays the owner's: the command only reads.

It is a design note only. Nothing here is built. No code, steering file, rules gate, safety check, workflow or ruleset changes with it.

## Current state

Read at main `b247b66` and on GitHub on Nov 16, read only:

- **The ruleset.** One active ruleset, "main requires result" (id 27314271). It requires the status check `result`, refuses a non-fast-forward and a deletion of main, and has no bypass actors. `strict_required_status_checks_policy` is false, so GitHub does not require a branch to contain main.
- **The `result` check.** `.github/workflows/ci.yml` has the jobs `plan`, `test`, `node` and `result`, with `permissions: contents: read`. `result` runs `python -m tools.ci_shards verify`, and it is the only required check. The suite it gates includes `tests/test_docs.py` (the generated docs match their parts), `tests/test_ci_map.py` and `tests/test_ci_shards.py` (every test registered).
- **In-process checks the command can reuse:** `umwayi.goaldocs` (the parts and their numbers), the em dash rule of `tests/test_docs.py`, and `tools.ci_shards`.
- **How a limits part gets its number.** `umwayi goal docs build` writes `number: N` into every new part, and `umwayi goal docs check` fails while a part has none ("1 part not yet built"). `tools/merge_main.py` renumbers a part whose number main took. So on every branch the part is numbered at its head, and usually in the commit that first adds it.
- **The network.** The core package `umwayi/` may import no network module (`tests/test_system.py`, `test_no_module_imports_a_network_library`). `tools/` has no network reader yet.
- **What runs it today.** Nothing. W65 (branch `w65-work-ledger-design`) proposes a `ready` cell in its work ledger, recorded per head.

## The command

```
python -m tools.merge_ready PR [--repo OWNER/NAME]
```

It runs every rule, prints one line per rule (`N pass`, `N fail: REASON` or `N cannot decide: REASON`), then a last line `merge-ready: pass`, `merge-ready: fail` or `merge-ready: cannot decide`. The exit code is the worst result: 2 beats 3, and 3 beats 0.

**Who runs it.** The owner, by typing it. Or the supervisor, as a child process with this fixed argument list, only when the owner has turned on the network probe (`umwayi.json` `"work": {"probe": true}`, W65). The core never imports the network code, and only `tools/` does. The result goes into the work ledger through the logged `umwayi work record TASK ready pass|fail --head SHA` (W65), never into a GitHub write. A pass for one head says nothing about a later head.

**The product equivalent.** There is no second implementation. The same command is the product's check, because umwayi-os works on one repository (W9-Q12) and the rules are about its pull requests.

## The rules

| # | rule | reads | passes when | exit if not met | planted fault |
| --- | --- | --- | --- | --- | --- |
| 1 | the `result` check is green on the head | the PR's head SHA and its check runs (API) | one check run named `result`, `status` completed, `conclusion` success, on exactly the head SHA | 2 failed or cancelled; 3 queued, in progress or missing | accept a green `result` of an older SHA |
| 2 | mergeable and clean | the PR (API): `state`, `draft`, `mergeable`, `mergeable_state` | open, not a draft, `mergeable` true, `mergeable_state` `clean` | 2 closed, a draft, `dirty` or `mergeable` false; 3 `null` or `unknown` | treat `unknown` as clean |
| 3 | the branch contains main | main's SHA (API) and the compare of main with the head (API) | `behind_by` is 0 against main's current SHA | 2 behind; 3 unreadable | compare with the PR's base SHA |
| 4 | changed paths are inside the allowlist | the changed paths (git) and `tools/merge_ready.json` | each path matches an `allowed` pattern; a path that matches a `protected` pattern also has an owner flag for its blob at the head | 2, with the count and each path | match `docs/` against `docsx/a.md` |
| 5 | no em dash | each added or changed file at the head (git, UTF-8), and the PR title and body (API) | no U+2014 in any of them | 2, with the path and line number, or "title" or "body", never the line | read only the diff lines, or the body only |
| 6 | the PR body has its sections and no attribution | the PR body (API) and the PR's commit messages (git) | every heading of `sections` is a `##` line, once. No line says "Generated with" Claude or Claude Code, in any case; the template's own line `Made with umwayi-os` (W51) is allowed. No commit has a `Co-Authored-By:` trailer naming Claude | 2, with the missing heading or the kind of line | find a heading inside a sentence; a case-sensitive match |
| 7 | limits parts are numbered by the build, not by hand | each `docs-parts/known-limits/*.md` the PR adds (git) and main's parts at the head's merge base | with its `number:` line taken out, `goaldocs` gives the part exactly the number it has | 2, with the part's id | trust any number that is not taken |

Rules 1 and 2 need the network, and so does reading the PR body for rules 5 and 6. Rules 3 to 7 also read git. Every rule runs, also after an earlier one failed, so the report is whole.

**Why rule 7 is worded so.** The owner's rule is "limits parts unnumbered": a builder must not pick a number. But a part cannot stay unnumbered: `goal docs check` fails until the build numbers it, and `merge_main` renumbers it. Reading the part as first committed (the earlier version of this note) would fail every branch that ran the build before its first commit, which the builder rules ask for. Rule 7 checks what the rule is for instead: the number is the one the build gives, so no number was chosen by hand. The owner decides between the two readings (open question 4). The PR is required by rule 3 to contain main, so "main's parts" are the parts at the merge base.

**Not repeated here.** Test registration and the generated docs are already part of the suite that `result` gates (rule 1), so they get no rule of their own.

## Where the data comes from

- **The GitHub REST API, `GET` only:** `/repos/{o}/{r}/pulls/{n}` (`state`, `draft`, `title`, `body`, `head.sha`, `mergeable`, `mergeable_state`), `/repos/{o}/{r}/commits/{sha}/check-runs` (`name`, `head_sha`, `status`, `conclusion`), `/repos/{o}/{r}/branches/main` (`commit.sha`), and `/repos/{o}/{r}/compare/{main}...{head}` (`behind_by`).
- **The token** comes from `GITHUB_TOKEN` or `GH_TOKEN`. It is never printed or logged. `urllib.request` from the standard library, a 10 second timeout, at most 8 requests.
- **Git, read only, argument lists, no shell:** `git diff --name-only BASE...HEAD`, `git show SHA:PATH`, `git log --format=%B BASE..HEAD`, `git merge-base main HEAD`. It never fetches: the owner or the supervisor's caller makes sure the head is present, and a missing object is 3.
- **Fail closed.** No network, a timeout, an HTTP error, a rate limit (403 or 429 with `x-ratelimit-remaining: 0`), a reply that is not JSON, or a field missing or of the wrong type: 3, "cannot decide". Never a pass and never a fail on a guess.

## The allowlist and the owner flag

One file, `tools/merge_ready.json`, read strictly (an unknown key, a repeated key or a wrong type is 64):

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

- A pattern ending in `/` is a folder; any other is one exact path. No wildcards. A path in no `allowed` pattern fails.
- `protected` holds the four kinds the owner named: steering (`.kiro/steering/`), the rules gate (the rules file, its reader, the kill switch and the adapter hooks), the safety checks (the files that decide or verify a pass, this tool and its file included) and the workflows (`.github/`). The exact lists are the owner's (open question 2).
- **The owner flag** must be something no helper can make. Any token on the machine where helpers run can be used by a helper, so a GitHub review, label or comment never counts. The flag is a record `owner-approvals/BRANCH.txt` with one line per protected path, `path BLOBSHA` (or `deleted`). The commit that last changed it must be signed by a key in `.github/owner_signers` (git's allowed signers format), checked with `git verify-commit` and `gpg.ssh.allowedSignersFile`, a git read. The owner signs on their own machine. A later change to the path breaks the blob match, and the rule fails again. `.github/owner_signers` is protected, so changing it needs a record signed by a key from the old file.

## Exit codes and output

- 0: every rule passes.
- 2: a rule fails, or an unexpected error.
- 3: cannot decide.
- 64: usage or config (a bad PR number, a bad `--repo`, a missing or malformed `tools/merge_ready.json`, no git repository), before any rule runs.
- Never 1.

Each line names the rule, the result and counts or paths, never file content, a body line, a commit message or the token. It writes no file and no logbook entry. When the supervisor runs it, the only record is the `work record` entry (W65), with the PR number, the head and the word `pass` or `fail`.

## What it never does

It never merges, approves, comments, labels or writes to GitHub: it sends only `GET`. It runs no shell and no process except the git reads above. It never fetches or pushes. It never changes a ruleset, a workflow, the allowlist or a steering file. It never decides on a guess.

## What it cannot decide

These stay with the owner, and the last line of the output says so:

- whether a claim in a design note, a status part or a PR body is true;
- whether a test proves what its name says;
- whether a design, a rule or a trade-off is wise;
- whether the allowlist, the protected list or the sections are right;
- whether an owner-signed change to a protected path is safe (a signature shows who approved, not that it is good);
- whether the work is the task that was asked for.

## Spec lines it would add or change

Added, `### W63.R1` to `### W63.R6` at the end of requirements.md:

- **W63.R1 The command.** `python -m tools.merge_ready PR [--repo OWNER/NAME]`, the seven rules of the table, every rule run and reported, run by the owner or by the supervisor as a child with a fixed argument list when `work.probe` is on.
- **W63.R2 The data.** The four `GET` endpoints and the git reads; anything unreadable is 3.
- **W63.R3 The allowlist.** `tools/merge_ready.json`, read strictly, the four protected kinds; the file and the tool protect themselves.
- **W63.R4 The owner flag.** A record in `owner-approvals/`, in a commit signed by a key of `.github/owner_signers`, binding each protected path to its blob; a GitHub review, label or comment is never the flag.
- **W63.R5 Exit codes and output.** 0, 2, 3 and 64; one line per rule with ids, paths and counts only.
- **W63.R6 Never, and cannot decide,** as above.

Changed: W65.R5 (once merged) gains "the `ready` cell is recorded only from a `tools.merge_ready` result for the same head". If the owner approves open question 1: `docs/testing.md` "CI since W20" gains a `merge-ready` job after `result`, and the ruleset requires it. W62's PR body check folds into rule 6.

## The tests it would need

All use recorded JSON replies and a temporary git repo, so no test uses the network.

| rule | test | planted fault |
| --- | --- | --- |
| 1 | `test_result_must_be_green_on_the_head_sha` | accept a green `result` of an older SHA |
| 1 | `test_a_running_result_is_3` | treat `in_progress` as green |
| 2 | `test_unknown_mergeable_state_is_3` | treat `unknown` as clean |
| 2 | `test_a_draft_or_closed_pr_fails` | accept a draft |
| 3 | `test_a_branch_behind_main_fails` | compare with the base SHA |
| 4 | `test_a_protected_path_without_a_record_fails` | skip `protected` when the path is allowed |
| 4 | `test_a_pattern_is_a_folder_or_an_exact_path` | `docs/` matching `docsx/a.md` |
| 4 | `test_an_unsigned_or_foreign_signed_record_fails` | accept any signature |
| 4 | `test_a_path_changed_after_approval_fails` | compare paths, not blobs |
| 5 | `test_an_em_dash_in_an_unchanged_line_of_a_changed_file_fails` | read only diff lines |
| 5 | `test_an_em_dash_in_the_title_fails` | read the body only |
| 6 | `test_each_section_heading_is_required_once` | find a heading inside a sentence |
| 6 | `test_attribution_lines_fail_in_any_case` | a case-sensitive match |
| 6 | `test_a_co_authored_by_claude_trailer_fails` | read the PR body only |
| 7 | `test_a_hand_picked_free_number_fails` | accept any number that is not taken |
| 7 | `test_a_number_given_by_the_build_or_by_merge_main_passes` | read the part as first committed |
| all | `test_every_rule_runs_after_a_failure` | stop at the first fail |
| data | `test_no_network_rate_limit_and_bad_json_are_3` | return 0 on a timeout |
| never | `test_only_get_requests_and_git_reads` (an `ast` scan and a spy) | send a `POST`, or run `git fetch` |
| output | `test_no_token_body_or_file_text_in_the_output` | print the failing body line |
| core | `test_umwayi_never_imports_tools_merge_ready` | import it from the supervisor |
| codes | `test_exit_codes_are_0_2_3_64_only` | a crash exits 1 |

## Temporary: today's build setup (not product)

This section describes how umwayi-os is built today, and goes when that setup goes.

- In the build sandbox, `gh api user` returns `Miguel-Shinyenyi`, the owner's account, and commits are by `Kiro Agent`, unsigned (`%G?` gives `N`), with no SSH keys. This is why the owner flag cannot be a GitHub action: here an agent holds the owner's token.
- Today an outside reviewer opens and merges pull requests. The command does not depend on that: it gives the same answer to whoever runs it.

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-16 | Rewritten for the runtime: one command run by the supervisor or the owner, seven rules as the owner listed them, rule 7 checks that the build gave the number, the build-time facts moved to a temporary section | The owner's task of Nov 16: umwayi-os runs by itself and never assumes an outside guide. |
| 2026-11-16 | Design note only. Unreadable data is exit 3. The owner flag is a signed record. The tool only reads | W63, the owner's point of Nov 16. |

## Open questions

1. **A required CI check.** A `merge-ready` job in `.github/workflows/ci.yml` (after `result`, `fetch-depth: 0`, `contents: read`, `pull-requests: read`) and the ruleset requiring it. Both stop for the owner. Recommendation: yes, after the command has run on five merged pull requests without a false fail. Keep `result` required.
2. **The allowlist and the protected list.** Recommendation: start with the lists above; the owner cuts or adds before the build. A later change needs an owner record.
3. **The owner flag.** Recommendation: the signed record. A GitHub review could replace it only if helpers never hold a token of the owner's account, which is not true today.
4. **"Unnumbered" or "numbered by the build".** Recommendation: rule 7 as written. The literal reading fails every branch that follows the builder rules.
5. **The sections.** Recommendation: What changed, Checks run and Not verified, as recent pull requests use. Decide W62 open question 5 at the same time, because builder rule 8 names other headings and is a steering line.
6. **A network reader in `tools/`.** Recommendation: allow it for this one tool, by name, with a test that no other file in `tools/` imports a network module.
