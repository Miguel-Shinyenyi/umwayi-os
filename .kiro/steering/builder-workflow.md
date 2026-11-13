# umwayi-os builder workflow

Read this before any work in this repo. It is how every session works. It does not change the product rules in
`product.md` (steering rules 1 to 13), and it never overrides them.

1. One task, one pull request, one session. Never merge. Never review your own work. Stop when the pull request is open.
2. Merge the newest `origin/main` into your branch before every push and before you open the pull request, and whenever
   main moves. Do it with `python -m tools.merge_main`, never with a raw `git merge`. It merges, and when the only
   conflicts are in generated files it clears them with the command that writes them. Exit 3 means stop: it changed
   nothing and printed the paths, so ask the guide with those paths. Confirm GitHub shows no conflicts before you report.
3. `docs/KNOWN-LIMITS.md` and `docs/status-log.md` are generated: never edit them by hand. Write a part under
   `docs-parts/`. Always leave a limits part unnumbered, so the builder assigns the number (`merge_main` runs it; it
   takes the next free number after merging main).
4. Tests: write tests first for new behaviour. While building and before every push, run only the affected tests with
   `python tools/affected_tests.py --run` (add `--python python3.10` and so on for each version you can install). Run
   the full suite only when that command says FULL SUITE, or when asked. GitHub CI is the record.
5. No em dashes anywhere: code, docs, commit messages, pull request text.
6. Every question you ask the owner comes with your recommendation.
7. Do it yourself first before asking the owner for something.
8. Every pull request description has: Built, Not built, Could not verify, test counts per Python version, and open
   questions, each with a recommendation.
9. Ask before changing any safety rule (steering rules 1 to 13, the rules gate, the exit codes). Never change what an
   existing test means. When you change a steering line that `guidance.yaml` pins by hash, change its entry (text,
   prompt_line and source_hash) in the same commit.
10. If the same error happens twice, or you are stuck for 30 minutes, stop and report.
