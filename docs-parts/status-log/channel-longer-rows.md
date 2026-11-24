date: 2026-11-24
pr: 226
what: A fix to `umwayi feedback inbox` found by using it on the real folder. The text of a row of `CHANNEL.md` was limited to 400 characters, but eight real rows written by both the guide and the builder were 429 to 713 characters (a question or an answer with its recommendation), so the whole inbox refused to show anything (`line 16: the text is empty, over 400 characters`). The limit is now 1000 characters (`MAX_TEXT`), a valid row is shown whole, and `docs/feedback-channel.md` says 1000. A planted test parses rows of 429, 541, 713 and 1000 characters and refuses 1001. A change to the behaviour of a command that merged on the owner's word: owner stop.
tests: `tests/test_channel.py` (the limit, the long real rows, a valid row shown whole).
