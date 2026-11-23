date: 2026-11-23
pr: none
what: G3, a real cut of `docs/testing.md`. The generated table (one row for each Python test file that reads a path outside `tests/` and `umwayi/`, 195 lines and one more with each new test file) moved out of the page into `tools/ci_map_table.md`; the page keeps a link. The page went from 299 to 105 lines. `tools/ci_map.py`, `tools/generated_files.json` and the tests that name the file follow the move. A new test fails when `docs/testing.md` has more than 290 lines, with a planted fault. Docs and test only, no product code.
tests: `tests/test_docs.py`, `tests/test_ci_map.py`, `tests/test_generated_files.py`, `tests/test_merge_main.py` (a seed of the merge helper with the new file); the shard and docs tests.
