# Frontier practices tracker (W10)

This is the builder's reading, for the owner to review. The owner has not read it.

## Purpose

A coverage view of the ten practices on [kiro.dev/topics/frontier-engineering](https://kiro.dev/topics/frontier-engineering) against what this repo already does. It builds nothing new. The builder read the page and the steering, guidance, docs and tools of this repo, and marked a row Covered only where a real file or test shows it. Anything the builder could not show is Partly covered or Not covered.

`tests/test_frontier_practices.py` checks the form of the table and that each evidence file and guidance id exists. It does not check that a state is true or that the evidence proves it. No job or schedule runs it beyond the normal test run, and nothing in `umwayi/` reads this file. See [KNOWN-LIMITS 262](KNOWN-LIMITS.md).

## Current state

States: Covered, Partly covered, Not covered, Not applicable. Evidence is a repo file, or `guidance:ID` for an entry of `guidance.yaml`.

| Number | Practice | State | Evidence | Gap |
| --- | --- | --- | --- | --- |
| 1 | You are the architect, not the typist | Partly covered | `.kiro/steering/builder-workflow.md`, `docs/goals.md`, guidance:ask-before-changing-safety-rule | Rules keep the owner as approver and merger, but the goal flow that splits a goal into task packets is specified and not built. |
| 2 | Maximize agent time, minimize your involvement | Partly covered | `docs/scheduled-runs.md`, `docs/stalls.md`, guidance:batch-interruptions | Timers and a stall check exist, but no unattended run of several tasks is built. |
| 3 | Build your codebase for agents | Partly covered | `PROJECT.md`, `docs/DOCS_MAINTENANCE.md`, `tests/test_docs.py` | Docs and steering are kept current and tested, but nothing checks that an agent finds its way around the code. |
| 4 | Give agents a fast feedback loop | Covered | `tools/affected_tests.py`, `tests/test_affected_tests.py`, `tools/ci_shards.py`, guidance:tests-first-affected-only | Nothing I found fails when the affected test run gets slower. |
| 5 | Execution is cheap. Direction is everything. | Partly covered | `tests/goal/test_guidance.py`, guidance:goal-sentence-present, guidance:acceptance-checks-present | The checks only see that the fields are there, and the goal start step does not call them yet. |
| 6 | Treat code as disposable | Not covered | guidance:rewrite-broken-base | It is one advice line, and no tool or test makes throwing away and redoing a branch easy. |
| 7 | Hold AI output to human standards | Partly covered | `.github/workflows/ci.yml`, `.kiro/steering/builder-workflow.md`, guidance:explain-ai-output | CI runs the tests and a rule bans self review, but nothing shows that a person read the diff. |
| 8 | Trust the boundaries, not the agent | Covered | `rules.yaml`, `adapters/common/umwayi_gate.py`, `tests/test_whole_system.py`, guidance:safety-helper-action-passes-check | No operating system sandbox is built, and the gate covers only agents that run through an adapter. |
| 9 | Use agents for everything, not just code | Partly covered | `docs/helpers.md`, `docs/automation.md` | AI helpers draft for two jobs only, and no planning, review or triage use is built. |
| 10 | Continuously tune your agent setup | Partly covered | `guidance.yaml`, `docs/corrections.md`, `docs/concerns-record.md` | The owner edits rules and guidance by hand, and nothing measures which lines help. |

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-13 | The ten titles are taken from the ten pages linked from the frontier engineering page, in its order. | The page itself lists no titles. |
| 2026-11-13 | Evidence may be a file or a guidance id, and a file must be on main. | The owner's task rules for W10. |

## Open questions

- Whether the owner agrees with each state. Recommendation: read rows 1, 3 and 7 first, the builder is least sure of them.
