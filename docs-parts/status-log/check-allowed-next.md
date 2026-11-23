date: 2026-11-23
pr: none
what: W78 5(d), `umwayi check` says the allowed next step itself. After a No or an Ask me first the text output has one more line, `Allowed next: ...`, after `Reason:`, and the `--json` answer has a key `allowed_next` after the old keys; a Yes has neither. The step is one of two fixed sentences chosen by the answer, never by a rule's text or the action. The adapter gate says the same two sentences (a test holds them equal). The golden text of a No in `tests/test_elections.py` gains that line; its first three lines are the bytes of before. Stops for the owner (the answer of the rules gate).
tests: `tests/test_allowed_next.py`, `tests/test_elections.py`, the adapter and scanner tests.
