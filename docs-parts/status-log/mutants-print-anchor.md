date: 2026-11-25
pr: none
what: A repeated or missing anchor of the OpenCode mutation tests now names the whole anchor (up to 400 characters, not the first 70) and where the count runs: from the `after` anchor to the `until` anchor or to the END of the file, with the note that a function added after the `after` anchor that repeats those lines counts too. Today's failure (a new Muse function placed after the OpenCode checks made three anchors appear twice, and the message showed only 70 characters) took a long read of the log. Tests only; no behavior of the mutation run changes.
tests: `tests/agents/test_opencode_mutants.py` (a repeated anchor is named in full, with where the count runs).
