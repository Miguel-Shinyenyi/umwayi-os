date: 2026-11-23
pr: none
what: F3 (a, b, c). `python -m umwayi.seatbelt run` now calls `start_allowed()` and refuses (reason `platform`) while `CHECKED_ON_MAC` is False, unless the owner types the switch `--i-am-testing` before the `--`; the refusal names the switch, and the switch does not help where `sandbox-exec` is missing. The selftest is unchanged. New `docs/seatbelt-check.md`: the three steps, the expected lines, what to send back, and that `sandbox-exec` is deprecated by Apple; linked from `docs/enforced-default-design.md`. Module and docs only, no `agents.py` change, no owner stop.
tests: `tests/test_seatbelt.py` (five new tests of the refusal and the switch, with the process start mocked).
