date: 2026-11-23
pr: none
what: F4a. A test, `tests/test_limits_numbers.py`, reads the real tree and fails when a KNOWN-LIMITS number is used twice among the limits parts or among the headings of `docs/KNOWN-LIMITS.md`, when a part number is not a heading, or when the newest numbers have a gap. Planted faults: a made-up list, and a copy of the parts folder with one number copied onto another. It checks the tree as main holds it: 330 to 343, each once, 343 the newest (the sign-and-verify limits item). Test only, no product code.
tests: `tests/test_limits_numbers.py`.
