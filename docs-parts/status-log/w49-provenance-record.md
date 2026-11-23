date: 2026-11-23
pr: 184
what: W49, the record only. New `umwayi/provenance.py`: one record per task with the SHA-256 and size of every file the task changed, the parsed-structure hash of each `.py` file, deleted files by path; stored once in `.umwayi/provenance/GOAL/TASK.json` (0700, 0600, never overwritten, never in the worktree); one sealed entry `umwayi provenance` with the record's hash and counts, no path. The supervisor makes it before `in review` when `umwayi.json` has `"provenance": {"record": true}` (off by default). Needs the hash chain. Not built: signing and `umwayi verify` (they need the owner's key). Stops for the owner.
tests: `tests/test_provenance.py` (23 tests, no key made, no signature checked).
