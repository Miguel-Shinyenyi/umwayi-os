# Advise to enforce: an audit of guidance.yaml (W62, design note)

## Purpose

The owner's point: umwayi-os must move on deterministic rules, not on strong suggestions to agents. This note audits the 31 entries of `guidance.yaml` (4 enforce, 26 advise, 1 owner). For each advise entry it gives one of three things:

- the existing test or tool that already checks it, so only the label is wrong;
- a new deterministic check;
- the plain reason no machine check is possible.

It also designs the test that fails when an advise entry has no reason. It is a design note only. `guidance.yaml`, the steering files, the rules gate, the safety checks and the workflows are not changed by it.

## Current state

Read at main `7bca468`. `umwayi/guidance.py` defines the three kinds:

- **enforce** names a `check` from the registry `CHECKS`. `goal guard` runs it on a task record and refuses a task that breaks it.
- **advise** is a `prompt_line` for a helper's prompt. Nothing is checked.
- **owner** is for the owner only.

An `enforce` entry must name a registered check (`_entry`, exit 64 otherwise). So a rule that a CI test already proves cannot be marked `enforce` today: the loader has no way to name a test. That is why most of the entries below are labelled advise.

Entries for steering lines (`.kiro/steering/builder-workflow.md`, `.kiro/steering/product.md`) are pinned by `source_hash`. A changed steering line stops the loader (`tests/goal/test_guidance.py` `SourceHash.test_edited_source_line_is_refused`). Changing an entry's kind or adding a field does not touch the steering file.

There is no guidance entry for the worktree rule. That rule is enforced by the goal code itself: W9.R8, `umwayi/goalgit.py`, and `tests/goal/test_worktree.py` `ListGuardTests.test_no_list_holds_a_word_that_changes_the_owners_copy_or_the_network`.

## The table of all 31 entries

Proposed is one of:

- **keep**: unchanged.
- **proof**: mislabelled. Relabel to enforce with the named test.
- **proof + gap**: relabel the part that is proven. The rest needs a new check or a reason.
- **new**: a new check.
- **none**: no machine check is possible; record the reason.

| id | kind now | proposed | check, or why none | file that would hold it | size |
| --- | --- | --- | --- | --- | --- |
| goal-sentence-present | enforce | keep | `goal_sentence_present` | `umwayi/guidance.py` | none |
| consequences-and-undo-present | enforce | keep | `consequences_and_undo_present` | `umwayi/guidance.py` | none |
| acceptance-checks-present | enforce | keep | `acceptance_checks_present` | `umwayi/guidance.py` | none |
| one-open-pr-per-task | enforce | keep | `one_open_pr` | `umwayi/guidance.py` | none |
| record-state-before-change | advise | new, and proof for goal runs | a guard check `state_before_present`: the task record has a non-blank `state_before`. The goal flow already records the base commit and the work fingerprint (`tests/goal/test_goalrun.py` `FingerprintTests.test_a_changed_file_changes_the_fingerprint_and_the_same_bytes_do_not`) | `umwayi/guidance.py` | small |
| check-output-against-goal | advise | proof | the goal flow runs the tester on every check and asks the guide before `in review` (`tests/goal/test_goalrun.py` `CleanTaskTests.test_a_whole_fake_task_goes_to_in_review`, `TesterTests.test_a_failed_check_is_failed_tests_and_the_guide_is_not_asked`, `TesterTests.test_the_guide_rejects`) | `guidance.yaml` only | small |
| explain-ai-output | advise | none | whether a person can explain an output is in that person's head; no file shows it | `guidance.yaml` reason | small |
| rewrite-broken-base | advise | none | "broken" and "rewrite instead of patch" are judgements about code quality; no test can tell a needed rewrite from a fine patch | `guidance.yaml` reason | small |
| batch-interruptions | owner | keep | owner kind: no check, no prompt | none | none |
| merge-main-before-push | advise | proof + gap | proof: the generated files are current and `merge_main` behaves (`tests/test_docs.py` `RepoDocsTests.test_the_generated_docs_are_what_the_parts_build`, `tests/test_generated_files.py`, `tests/test_merge_main.py`). Gap: that a PR head contains the newest main can be checked in CI (`git merge-base --is-ancestor`); "never a raw git merge" cannot, because both leave the same kind of merge commit | `.github/workflows/ci.yml` (owner decision) | small, workflow |
| known-limits-next-free-number | advise | proof | `goal docs check` finds a hand edit of a shared file and a clash or gap in numbers (`tests/goal/test_docs_parts.py` `CheckTests.test_a_hand_edit_of_a_shared_file_is_found`, `test_two_parts_with_one_number_or_a_gap_are_refused`), and CI runs it (`tests/test_docs.py` `RepoDocsTests.test_the_generated_docs_are_what_the_parts_build`) | `guidance.yaml` only | small |
| tests-first-affected-only | advise | none | the order in which tests and code were written, and which tests ran on a laptop, leave no record in the repo; CI runs its own plan (`tools/ci_plan.py`) | `guidance.yaml` reason | small |
| no-em-dash-anywhere | advise | proof + gap | proof for the docs (`tests/test_docs.py` `RepoDocsTests.test_the_documentation_has_no_problem`), `guidance.yaml` (the loader), the generated docs (`umwayi/goaldocs.py`) and the builder steering file (`tests/test_builder_workflow.py`). Gap: every tracked text file (new test), commit messages and PR text (CI, owner decision) | `tests/test_no_em_dash.py` (new); `.github/workflows/ci.yml` | small; workflow part small |
| questions-carry-recommendation | advise | none, with an option | a question in a chat or a PR has no fixed shape to check. Option: the queue refuses a `decision` row with an empty recommendation (today it is optional, `umwayi/taskqueue.py` `_plan_add`), but that changes the queue's format (open question 3) | `guidance.yaml` reason | small, or large with the option |
| do-it-yourself-first | advise | none | whether something was tried first is not in any record | `guidance.yaml` reason | small |
| pr-description-sections | advise | new | a CI step reads the PR body from the event file GitHub gives the job (no network) and refuses one without the five headings; a script and its test | `tools/pr_body.py` (new), `.github/workflows/ci.yml` (owner decision) | small, workflow |
| ask-before-changing-safety-rule | advise | proof + gap | proof: a changed pinned steering line stops the loader (`tests/goal/test_guidance.py` `SourceHash.test_edited_source_line_is_refused`), the older starter rules are pinned by hash (`tests/test_starter_rules.py` `OpenCodeStarterRulesTest.test_the_rules_that_were_there_are_unchanged`), and the exit codes are pinned (`tests/test_exit_codes.py`). Gap: "ask the owner" and "never change what a test means" are not machine checkable | `guidance.yaml` | small |
| stop-when-stuck | advise | proof + gap | proof for goal runs: the same error twice and a stall stop the task (`tests/goal/test_goalrun.py` `WatchTests.test_the_same_error_twice_is_looping`, `WatchTests.test_a_builder_that_is_silent_is_stopped_as_stalled_and_the_child_is_gone`). Gap: a session outside a goal has no watcher | `guidance.yaml` | small |
| safety-fail-closed | advise | proof | `tests/test_rules.py` `FailClosedTests`; the guidance loader's own fail-closed tests | `guidance.yaml` only | small |
| safety-never-print-secrets | advise | proof | planted secrets swept from every byte umwayi wrote or printed (`tests/test_scan_secrets.py` `SecretSweepTests.test_no_planted_secret_in_any_byte_umwayi_wrote_or_printed`), private paths kept out of a bundle (`tests/test_memory.py` `BundleTests.test_private_never_in_bundle`), reasons that do not echo the rules (`tests/test_rules.py` `FailClosedTests.test_reason_does_not_echo_rules_content`) | `guidance.yaml` only | small |
| safety-never-push-to-main | advise | proof + gap | proof: umwayi's git lists hold no push (`tests/goal/test_worktree.py` `ListGuardTests.test_no_list_holds_a_word_that_changes_the_owners_copy_or_the_network`), and an agent's push to main is No (`tests/test_starter_rules.py`, rows `cc push main`, `cc force push`). Gap: a person's push is held only by GitHub branch protection, which the repo cannot show (unknown) | `guidance.yaml` | small |
| safety-helpers-draft-only | advise | proof | `tests/test_helpers.py` `BaseStepTests.test_post_send_and_publish_types_are_no_for_helpers`; `tests/test_system.py` `CodeTests.test_no_helper_has_a_code_path_that_sets_an_approver` | `guidance.yaml` only | small |
| safety-no-network-layers-1-5 | advise | proof | `tests/test_system.py` `CodeTests.test_no_module_imports_a_network_library` (every module, with the two named loopback servers inside a function) | `guidance.yaml` only | small |
| safety-no-secrets-in-repo | advise | new | a test over `git ls-files` that refuses known key shapes (private key headers, `AKIA` keys, `ghp_` tokens, `sk-` keys) except the exact test sentinels it lists | `tests/test_no_secrets_in_repo.py` (new) | small |
| safety-helper-action-passes-check | advise | proof | `tests/test_helpers.py` `BaseStepTests.test_the_rules_see_the_action_built_by_the_base`, `test_no_stops_with_exit_2_without_running_the_work` | `guidance.yaml` only | small |
| safety-a-crash-blocks | advise | proof | `tests/test_exit_codes.py` `CrashTests.test_a_crash_is_never_0_1_or_3`; `tests/adapters/test_claude_code.py` `CrashTests.test_a_crash_inside_the_adapter_blocks`, `test_a_crash_inside_umwayi_check_blocks` | `guidance.yaml` only | small |
| safety-core-standard-library-only | advise | proof + gap | proof: `pyproject.toml` has `dependencies = []`, and several modules are checked against `sys.stdlib_module_names` (`tests/goal/test_goalrun.py`, `tests/test_elections.py`, `tests/test_rulelog.py`, `tests/test_petition.py`, `tests/test_schedule.py`, `tests/test_view.py`). Gap: no test covers the whole package | `tests/test_stdlib_only.py` (new) | small |
| safety-web-interface-local-backend-only | advise | proof | `tests/serve/test_scenarios.py` `LoopbackOnly.test_a_request_from_a_non_loopback_address_never_reaches_a_route`, `RealPageClient.test_the_client_refuses_to_run_off_the_loopback_origin`; `tests/serve/test_samecode.py` `SpyTests.test_each_route_calls_the_named_core_functions_once_in_the_order_of_w6_r7` | `guidance.yaml` only | small |
| safety-layer13-append-only | advise | proof | `tests/autonomy/test_gates.py` `FailClosedTests.test_row_5_a_matching_no_is_never_moved`; `tests/test_reopen.py` `HappyPathTests.test_one_entry_is_appended_and_names_the_old_entry_by_its_full_hash` | `guidance.yaml` only | small |
| safety-graded-autonomy-fails-closed | advise | proof | `tests/autonomy/test_gates.py` `FailClosedTests`; `tests/autonomy/test_off.py` `OffTests` | `guidance.yaml` only | small |
| safety-no-claim-of-perfection | advise | proof + gap | proof for layer 13: `tests/test_honest.py` `PagesTests.test_no_claim_in_the_pages`. Gap: the same banned-word scan over README, PROJECT.md and the rest of `docs/` (new); whether a sentence means a claim cannot be checked | `tests/test_honest.py` (extended) | small |

The counts for the 26 advise entries:

- proof: 11;
- proof + gap: 7;
- new: 2;
- new and proof for goal runs: 1;
- none: 5, one of them with an option.

## Mislabelled entries: change the label only

These 11 are already checked by a test that runs in CI. The label is changed to `enforce` with a `proof` field (below), and nothing else changes:

- check-output-against-goal
- known-limits-next-free-number
- safety-fail-closed
- safety-never-print-secrets
- safety-helpers-draft-only
- safety-no-network-layers-1-5
- safety-helper-action-passes-check
- safety-a-crash-blocks
- safety-web-interface-local-backend-only
- safety-layer13-append-only
- safety-graded-autonomy-fails-closed

The proof paths are in the table.

Seven of these are tier 1 safety entries of `product.md`: safety-fail-closed, safety-never-print-secrets, safety-helpers-draft-only, safety-helper-action-passes-check, safety-a-crash-blocks, safety-layer13-append-only and safety-graded-autonomy-fails-closed. Changing their label is not a change to the safety rule's wording, but the builder rule says to ask before touching a safety rule. So the build of this note asks the owner once, for the whole list (open question 1).

## Entries that need a new check

| check | reads | refuses | exit |
| --- | --- | --- | --- |
| `state_before_present` (guard check) | the task record JSON given to `goal guard` | a record with no `state_before`, or a blank one | `goal guard`: 3 Ask me first, as the other guard checks |
| `tests/test_no_em_dash.py` | every file of `git ls-files` that decodes as UTF-8 | any U+2014, with the path and line number, never the line | a failing test |
| `tests/test_no_secrets_in_repo.py` | the same files | a private key header, an `AKIA` key, a `ghp_` token, an `sk-` key that is not an exact listed sentinel | a failing test |
| `tests/test_stdlib_only.py` | every `umwayi/**/*.py`, parsed with `ast` | an import whose top name is not in `sys.stdlib_module_names`, not `umwayi` and not `__future__` | a failing test |
| the honest scan, widened | README, PROJECT.md, `docs/*.md` | a banned word of 13.R8.2 outside the exact note | a failing test |
| PR head contains main (CI) | `git merge-base --is-ancestor origin/main HEAD` in the PR job | a head that does not contain the base | the job fails |
| `tools/pr_body.py` (CI) | the PR body from the job's event file | a body without the five headings of builder rule 8 | 2 refused, 0 ok, 64 usage |
| commit messages and PR text, em dash (CI) | the messages of the PR's commits, and the PR body | any U+2014 | the job fails |

The last three change `.github/workflows/ci.yml`, which is not in this task. Each is an owner decision (open question 2).

## Entries that cannot be machine checked, and why

- **explain-ai-output:** understanding is in a person's head, and no file shows it.
- **rewrite-broken-base:** "broken" and "rewrite instead of patch" are judgements.
- **tests-first-affected-only:** the order of work and what ran on a laptop leave no record.
- **do-it-yourself-first:** what was tried before asking leaves no record.
- **questions-carry-recommendation:** a question in a chat or a PR has no fixed shape. The queue part could be checked (open question 3).
- **The gaps of the proof + gap entries:**
  - "never a raw git merge" (merge-main-before-push);
  - "ask the owner" and "never change what a test means" (ask-before-changing-safety-rule);
  - a stuck session outside a goal (stop-when-stuck);
  - a person's push (safety-never-push-to-main);
  - the meaning of a sentence (safety-no-claim-of-perfection).

## The "advise needs a reason" test

- **New fields.** Two optional keys are added to the loader's table:
  - **`proof`**, on an `enforce` entry, in place of `check`. It holds one to four test ids of the form `tests/PATH.py::Class::method`, joined by `, `. The loader checks that each file exists under `tests/` and that `ast` finds that class with that method. It does not import or run the test. A missing file, class or method is exit 64. An `enforce` entry has exactly one of `check` and `proof`. `check_task` runs only the `check` entries, as today. A `proof` entry is checked by CI running the named tests.
  - **`no_check`**, on an `advise` entry. It holds one printable line of 10 to 200 characters saying why no machine check is possible, or which part is proven elsewhere and what is not.
- **The parser.** `_entry` gains the two keys in its table. Every other rule stays.
- **The test.** `tests/goal/test_guidance.py` gains `test_every_advise_entry_has_a_reason`: it loads the real `guidance.yaml` and fails, naming the ids, when an `advise` entry has no `no_check`. A second test, `test_no_enforce_entry_was_weakened`, pins the four enforce entries of today by id and check name, so none can become advise or lose its check.
- **The planted faults.**
  - A copy of `guidance.yaml` with one `no_check` removed must fail the first test.
  - A copy with `one-open-pr-per-task` turned to advise must fail the second.
  - A `proof` that names a method that does not exist must be exit 64.
- **The order of the build.** First the loader and the tests, with every advise entry given its `no_check` from the table above in the same pull request, so the test passes the day it lands. Then the relabels, owner approved. Then each new check, one task each.
- **A read-only command, optional:** `umwayi guidance audit` prints one line per entry (`proof`, `check`, `reason` or `missing`) and the counts.

## Exit codes

Only 0, 2, 3 and 64:

- **The loader** keeps its codes: 0 loaded, 3 Ask me first (a missing file or a changed source), 64 malformed (now also a bad `proof` or `no_check`).
- **`umwayi guidance audit`:** 0 every advise entry has a reason, 3 one does not, 64 the file is malformed, 2 an unexpected error.
- **`tools/pr_body.py`:** 0 ok, 2 refused, 64 usage.
- Never 1.

## What it never does

- No network and no shell. The loader reads files and parses them with `ast`; it never imports or runs a test.
- It never edits `guidance.yaml` by itself. Labels and reasons are written by a person in a pull request.
- It never weakens an enforce entry: a pinned test fails if one of the four becomes advise or loses its check.
- It never changes a steering line or its `source_hash`.

## What it does not prove

- A check existing does not prove the rule is wise, or that the check covers every case. A test proves the behaviour on the inputs it tries.
- A `proof` path proves that the named test exists, not that it still tests what the entry says. That is read in review.
- A `no_check` reason can be wrong. Something called uncheckable might be checkable later.
- A planted-secret sweep cannot find a secret of a shape it does not know.

## Spec lines it would add or change

Changed, design.md "Guidance (W19), stage 1":

- "**What it is.** ... Each entry has ... `check` (enforce) ..." becomes "... `check` or `proof` (enforce), `prompt_line` and `no_check` (advise) ...".
- The fail-closed table gains the row "a `proof` that names a test file, class or method that does not exist: `GuidanceError`, exit 64".

Added, a new section at the end of requirements.md, `### W62.R1` to `### W62.R5`:

- **W62.R1 Two fields.** `proof` (enforce, in place of `check`: one to four `tests/PATH.py::Class::method`, found by `ast`, never run by the loader) and `no_check` (advise: one line of 10 to 200 characters).
- **W62.R2 Every advise entry has a reason.** A test fails when one has no `no_check`.
- **W62.R3 No enforce entry is weakened.** The four of today are pinned by id and check.
- **W62.R4 The relabels.** The 11 entries of "Mislabelled entries" become enforce with their proof, after the owner's approval.
- **W62.R5 The new checks.** One task each, in the order of the "new check" table. The workflow ones wait for the owner.

## The tests it would need

| rule | test | planted fault |
| --- | --- | --- |
| every advise entry has a reason | `test_every_advise_entry_has_a_reason` | remove one `no_check` |
| no enforce entry weakened | `test_no_enforce_entry_was_weakened` | turn `one-open-pr-per-task` to advise |
| proof names a real test | `test_a_proof_to_a_missing_method_is_64` | point a proof at `test_does_not_exist` |
| proof and check never both | `test_enforce_has_exactly_one_of_check_and_proof` | give both |
| the loader never imports a test | `test_the_loader_imports_nothing_from_tests` (an `ast` scan) | add `importlib.import_module` |
| reason shape | `test_a_no_check_of_9_or_201_characters_is_64` | accept an empty reason |
| no em dash in tracked files | `tests/test_no_em_dash.py` | plant U+2014 in a copy of one tracked file |
| no secret in tracked files | `tests/test_no_secrets_in_repo.py` | plant a fake `AKIA` key in a temporary file |
| stdlib only | `tests/test_stdlib_only.py` | plant `import requests` in a copy of one module |
| state before | `test_state_before_present` (`tests/goal/test_guidance.py`) | a record with `state_before: " "` |
| honest scan widened | `test_no_claim_in_any_doc` | plant `guaranteed` in a copy of the README |
| audit exit codes | rows in `tests/test_exit_codes.py` | a missing reason exits 1 |

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-16 | Design note only: `proof` lets an enforce entry name a CI test, `no_check` gives every advise entry its reason, a test fails without it, and the four enforce entries are pinned | W62, the owner's point of Nov 16. |

## Open questions

1. **May the seven tier 1 entries in the mislabelled list be relabelled?** Recommendation: yes, in one owner-approved pull request. Only the label and the proof change; no steering line and no hash changes.
2. **The three CI checks** (PR head contains main, the PR body headings, an em dash in commit messages and PR text). Recommendation: approve the first two, because they are cheap and exact. Leave the commit message check for later, because a rewritten history would be needed to fix an old message.
3. **Should the queue require a recommendation on a decision row?** Recommendation: not now. It changes a file format the owner edits by hand. Whether every decision row umwayi adds today carries a recommendation was not checked for this note. Keep the rule as advise with its reason, and check that first.
4. **Should a `proof` be run by the loader?** Recommendation: no. Running tests from the goal flow would start processes and take minutes. CI runs them, and the loader checks only that they exist.
5. **Do the PR body headings of builder rule 8 match how pull requests are written?** Recent pull request bodies use What changed, Checks run and Not verified, not Built, Not built and Could not verify. Recommendation: the owner picks one set before `tools/pr_body.py` is built. Changing rule 8's wording is a steering change and the owner's.
6. **Should advise entries that are partly proven also list their `proof`?** Recommendation: yes. Allow `proof` on advise entries too, as information, so the audit shows what is covered. The test still needs `no_check` for the rest.
