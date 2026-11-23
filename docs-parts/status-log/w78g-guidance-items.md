date: 2026-11-23
pr: none
what: W78 5(a), 5(d) and 5(g). Every goal prompt now starts with a task card in fixed words: the mode, the scope and the rules in force for that helper's platform (`task_card`, `rules_card` in `umwayi/goalrun.py`). Every No, Ask me first and blocked answer of the shared adapter gate ends with `Allowed next: STEP.`, the step from a fixed list chosen by the answer (`adapters/common/umwayi_gate.py`, the OpenCode plugin text). When a task leaves running, one `counts` logbook entry holds three numbers: No, Ask me first and guard findings. Guidance is not enforcement, and a count is not proof of obedience.
tests: `tests/goal/test_task_card.py`, `tests/adapters/test_refusal_shape.py`, `tests/goal/test_task_counts.py`; CI is the full run.
