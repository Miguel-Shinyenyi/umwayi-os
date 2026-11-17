# Independent verification (W73, design note)

## Purpose

This note designs how a piece of work in umwayi-os is checked by someone other than its writer, and what may then be said about it in public. The source is the owner's queue doc, sections F8 and F12. That doc is not in this repo; its points were given with the task.

It is a design note only. Nothing here is built, and no code, rule, steering file, safety check, workflow or exit code changes with it. Terms are those of the W67 threat model and W68 untrusted content (branches `w67-threat-model`, `w68-untrusted-content`), and of the W48 routing design, which is on main as [model routing design](model-routing-design.md).

## Current state

What the repo shows at main `6525606`, in the two ways work is done today.

### In a goal run (`umwayi goal`)

- **The checks are written before the work, by another role.** The guide writes each task's acceptance checks in the plan. The owner approves them, and a guard check refuses a task without them (`guidance.yaml` `acceptance-checks-present`). The builder does not write them.
- **The tester is not the builder.** The tester's agent name must differ from the builder's, and so must the guide's. This is checked at approval and at every start (`goalpacket.roles_ok`; `tests/goal/test_goalrun.py` `test_the_tester_and_the_guide_must_not_be_the_builder`).
  - The same platform and model for both gives a warning only (`goalpacket.weak_independence`, W9-Q2).
  - The owner names the tester at `goal approve`. The builder never does.
- **The tester and the guide may change nothing.** The tree's fingerprint is taken before and after their runs; a change voids the run (`tests/goal/test_goalrun.py` `TesterTests.test_the_tester_that_changes_the_tree_voids_the_run`).
- **What the tester gets** (`goalrun.tester_prompt`): the task sentence, the numbered checks, and the branch and commit. It runs in the worktree, which holds the builder's commit, including the builder's status and limits parts.
  - So the tester can read the builder's notes. It is not given them as instructions, but they are there.
- **What the guide's check gets** (`goalrun.check_prompt`): the task, the count of changed files, the checks, and the tester's verdicts with the tester's evidence text.
- **What is logged:** one in-review entry with `Tester NAME: p of m checks pass.` and `Guide NAME: accept|reject|unclear.`, each naming the agent (`umwayi/goalstate.py` `FACTS`). The model is not in the entry. It is the owner's word at approval, and is measured only for Claude Code (the W48 note).

### In a builder session (how umwayi-os itself is built today)

- AI builder sessions write the code and its tests in a branch.
- The CI check `result` must be green before a merge (the ruleset "main requires result").
- A reviewer reads the pull request, and the owner merges. The review is the owner's process and is not recorded in the repo.
- The mutation passes the repo records were run by the builder of that change, on its own tests, with the results listed in its pull request ([testing](testing.md); for example W9.10, 48 mutants, in [goals](goals.md)).
  - So the writer chose the faults and saw the results.
- These sessions do not run through umwayi's gate. They follow the written builder rules (`.kiro/steering/builder-workflow.md`), and nothing in the repo shows that each of their tool calls was checked by umwayi.

## The design

### 1. The writer never marks its own test

- **In a goal run, this holds today.** The checks come from the guide and the owner, and the verdicts from a tester that is not the builder.
- **Added:** the tester and the guide must also differ from the builder by model where the model is known. Today the same platform and model is a warning only. With the W48 picker, the tester is picked by a rule (below), and the warning becomes a refusal when another candidate exists.
- **In a builder session:** the builder's own tests and planted faults stay, as the builder's work. They are never counted as the check of that work. The check is CI, the independent mutation pass (section 4) and the owner.

### 2. The checker is a different agent, chosen by a rule

- **The rule, not the builder, picks the checker.** It uses the W48 routing table: the first tester candidate in the owner's `routes.yaml` whose agent name differs from the builder's and whose model family differs. "Family" is the vendor of the model, for example Anthropic, OpenAI, Moonshot or Zhipu.
- **No such candidate:** the pick falls back to a different agent of the same family with a warning entry. If there is no different agent at all, it is Ask me first. Never the builder.
- **The builder can never name, suggest or veto its checker.** No field of the builder's output reaches the pick.

### 3. The checker gets the diff and the rules, not the builder's notes

- **What the checker gets:**
  - the task sentence;
  - the acceptance checks;
  - the base and the tip;
  - the diff as umwayi computes it (the changed paths, then the content of each change);
  - the rules that apply: `rules.yaml` and the guidance entries of the task.
- **What it does not get:** the builder's status and limits parts, the builder's commit messages and the builder's pull request text.
- **How:** the tester runs in a second, fresh worktree at the tip, with those paths removed before it starts. The removal is listed in its entry. The two parts are checked by the supervisor's own parser instead.
- **The guide's check** gets the tester's verdict words and the check numbers only, never the tester's evidence text. That closes a path for text of one helper to steer another (W68).

### 4. A planted fault run the builder cannot see

- **What:** after the tester, the supervisor runs a mutation pass on the changed code.
  - It applies fixed mutation operators of its own to the changed lines: a comparison flipped, a constant changed, a branch removed, a call to the rules check dropped. It uses the AST, standard library only.
  - It runs the tests the task added or changed, once per mutant, in a throwaway copy of the worktree.
  - A mutant that no test catches is a finding.
- **Hidden from the builder:**
  - The operators, the seed and the list of mutants are chosen after the builder's commit.
  - They are kept under `.umwayi/`, which the builder cannot read in its worktree.
  - They are never in any prompt.
- **What the result means:** a surviving mutant means a test did not check something. It does not prove the others did, and an equivalent mutant can survive with no fault.
- **Failure:** a surviving mutant moves the task to `needs owner` with the cause word `mutant_survived`. It does not fail the task, because an equivalent mutant is possible and only the owner can judge that.
- **For builder sessions:** the same pass, run by the reviewer or in CI on the pull request's diff. This adds a CI job, which is the owner's decision.

### 5. Results go to the logbook with the checker's identity

- **One entry per check**, in a fixed shape:
  - the checker's agent name, platform and model (asked, and measured where known);
  - the role;
  - the counts (checks passed, failed, unclear; mutants made, killed, survived);
  - the base and the tip.

  Never evidence text, a diff or a prompt.
- **The builder's identity** is in the same task's start entry, so a reader can see that the two differ.

## What may be claimed in public

Today the repo shows enough for this sentence:

> umwayi-os is built by AI builder sessions that follow written rules, checked by CI on every pull request, and merged by its owner.

After this design is built, and only for work it covered:

> Built under its own rules: each task was started through umwayi's gate, checked by a different agent and model family that was picked by a rule, put through a mutation pass the builder could not see, and merged by the owner. The record of each check is in the logbook.

What must not be claimed:

- **"Built under its own rules" for work done in a builder session.** Those sessions do not run through umwayi's gate today.
- **"Independently verified", "audited", "proven" or "safe".** The checker is another AI, not an independent party, and a check proves only what it tried. The banned-word scan of layer 13 already refuses some of these words in layer 13's pages (`tests/test_honest.py`). It should cover the README and the site too (W62).
- **A count of mutants as a measure of quality.** It says which faults were tried and caught, nothing more.

## What cannot be checked, said plainly

- **Whether two models really think differently.** A different family lowers the chance of the same blind spot. It does not remove it, and it cannot be measured here.
- **Whether a test proves what its name says.** A mutation pass finds a test that misses a planted fault. It cannot find a test that checks the wrong thing correctly.
- **Whether the checks themselves are the right ones.** The guide writes them and the owner approves them. A wrong check passes wrong work.
- **Whether the checker read what it says it read.** Its evidence is its own text, and umwayi keeps only the verdict words.
- **Whether a design or a claim in a note is wise or true.** That stays with the owner and the reviewer (the W63 design says the same for merges).

## The tests each part needs

| rule | test | planted fault |
| --- | --- | --- |
| builder never its own checker | `test_the_pick_never_returns_the_builder` | let the pick fall back to the builder |
| different family when one exists | `test_the_pick_prefers_another_model_family` | compare agent names only |
| no candidate is Ask me first | `test_no_other_agent_asks_the_owner` | warn and go on |
| builder cannot steer the pick | `test_no_builder_output_field_reaches_the_pick` (an import and call scan) | read a field of the status part |
| checker gets no builder notes | `test_the_checker_worktree_has_no_status_or_limits_part_of_the_builder` | copy the worktree as it is |
| guide gets verdict words only | `test_the_check_prompt_has_no_tester_evidence` | pass the evidence through |
| hidden mutation pass | `test_mutants_are_chosen_after_the_commit_and_never_in_a_prompt` | build the list before the builder runs |
| a survivor needs the owner | `test_a_surviving_mutant_moves_the_task_to_needs_owner` | fail the task instead |
| the pass catches what it should | `test_each_operator_is_caught_by_a_planted_test` | an operator that changes nothing |
| identity in the logbook | `test_each_check_entry_names_the_checker_and_no_text` | log the evidence |
| public claims | `test_no_banned_claim_in_readme_or_site` (W62's widened scan) | `independently verified` in the README |
| exit codes | rows in `tests/test_exit_codes.py` | a survivor exits 1 |

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-16 | Design note only. The checker is picked by a rule, never by the builder, and is from another model family when one exists. It gets the diff and the rules, not the builder's notes. A hidden mutation pass runs after the commit. Results are logged with the checker's identity. Public claims are limited to what the repo shows | W73, the owner's queue doc sections F8 and F12. |

## Open questions

1. **Refuse or warn when the tester shares the builder's model family?** Recommendation: refuse when another candidate exists, warn when none does. A goal should not stop only because the owner has one vendor.
2. **Remove the builder's notes from the tester's worktree?** Recommendation: yes. The supervisor checks the parts itself, and the tester's job is the code against the checks.
3. **Where does the hidden mutation pass run for builder sessions?** Recommendation: as a CI job on the pull request's diff, after `result`, once the owner approves the workflow change. Until then the reviewer runs it by hand, and the pull request says so.
4. **What does a surviving mutant do?** Recommendation: `needs owner`, as proposed, with the mutant's operator and line number in the queue row and never the code.
5. **The public sentence today.** Recommendation: use only the first sentence above in the README and the write-up until goal runs build umwayi-os's own tasks, and say which tasks those were.
