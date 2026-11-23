date: 2026-11-23
pr: none
what: W78 step 5 (5a3), `broker_lost`. When the enforcement broker of an enforced Claude Code run ends before the run does, `agent run` writes one entry ("Enforcement broker lost during the run of agent NAME") besides the line and exit 2. The goal supervisor reads that line and stops the task as `needs owner` (reason unclear, cause `broker_lost`) before the next step starts. Every call after the loss was refused by the hook (no answer is No). Nothing is undone. Stops for the owner.
tests: `tests/goal/test_broker_lost.py`; a real run of the fake claude, the real hook and a broker killed in the middle (`tests/agents/test_broker_wiring.py`, Linux), fake only.
