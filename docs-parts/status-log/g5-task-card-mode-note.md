date: 2026-11-23
pr: none
what: G5 (N4 of the 2026-11-23 queue). The `Mode:` line of the task card at the start of every builder, tester and check prompt said `enforcement: enforced` with no note. It now ends with the plain statement the status line already has: "Enforcement is cooperative today and enforced where built." (`enforce.TODAY_NOTE`). The words of a helper prompt change, so this stops for the owner. Nothing else in the card changed.
tests: `tests/goal/test_task_card.py`, `tests/test_enforce.py` (the pinned lines now hold the note); goal, supervisor and whole-system tests (296) pass.
