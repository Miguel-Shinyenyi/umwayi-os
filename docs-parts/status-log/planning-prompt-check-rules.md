date: 2026-11-22
pr: 170
what: The planning prompt now says that each acceptance check is one sentence of 10 to 200 characters, with no second sentence and no line break. The numbers are taken from the parser's constants, so the prompt and the parser cannot drift. Found by real goal runs: the guide's plan was refused as `checks` in 3 of 9 tries because the prompt did not say it. Owner-facing prompt wording, so the pull request stops for the owner. The other refusal seen in those runs, `context: ... private`, was a fault of the scratch root (no `umwayi.json`, so every path counted as private), not of the guide, and the prompt is not changed for it.
tests: see the pull request
