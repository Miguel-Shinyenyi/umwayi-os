date: 2026-11-25
pr: 265
what: G-0085, the owner's word. `units.yaml` at the root of the PUBLIC umwayi-os repository gets the top level line `public: true`, with a comment that the owner wrote the word at 22:12 on 2026-11-25 for the public umwayi-os repo only. It satisfies the first gate of the Muse route and of the OpenCode free route (`private_repo_named`) for this root only. It does not start anything: a Muse run still needs a fresh credit reading and the owner's Yes (the real check M3), and no agents.yaml entry lets Muse run. Another repository is not marked by this. units.yaml is a guard file: owner stop.
tests: `tests/budget/test_public_mark.py` (the repository file carries the one mark, parses, and says who wrote it, when and for what, in the comment above it).
