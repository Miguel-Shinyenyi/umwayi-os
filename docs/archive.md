# Archive (layer 4)

## Purpose

The archive moves a block of text out of a file into `archive/` with a SHA-256 fingerprint and leaves a pointer line behind. It exists so old text can leave a working file without being lost, and so a later change to it can be found.

## Current state

Moves a block of text out of a file into its own file under `archive/`, with a fingerprint, and leaves a pointer line behind.

```
umwayi archive move notes.md --lines 10-20 --reason "old plan" [--date 2026-11-07]
umwayi archive move notes.md --start "<!-- start -->" --end "<!-- end -->" --reason "old plan"
umwayi archive verify
```

- `archive/INDEX.md` is a Markdown table: id, source, moved, reason, words, sha256. `archive/A-0001.txt` holds the exact bytes of the block.
- The source gets one line in place of the block: `[archived A-0001: archive/A-0001.txt]`.
- Line ranges count from 1 and include both ends. Markers must each match one whole line, appear exactly once, and are part of the block.
- `move` refuses and changes nothing if the source is missing, a symbolic link, a private path in `umwayi.json`, or a protected file (logbook, queue, rules, config, archive, git data); if the range is empty or outside the file; if the markers are missing, repeated or in the wrong order; if the block has no words; or if the reason is empty.
- Ids look like A-0001 and are never reused: one more than the highest id in the index and in the logbook. If `LOGBOOK.md` exists but cannot be read, `move` refuses.
- The source, the archive file and the index all change or none do. If the logbook write fails, the move is undone. Each move adds one logbook entry.
- `verify` recomputes every SHA-256 and prints `ok`, `changed`, `missing` or `not in the index` for each id. It exits 0 only when all are ok, otherwise 1, and never changes a file.
- `umwayi archive restore` is not built yet. The output of `move` names it.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-08 | The source, the archive file and the index all change or none do; a failed logbook write undoes the move (4.4, 4.5) | Layer 4, PR 4: a move is never half done. |
| 2026-11-08 | Ids are never reused: the highest id in the index and in the logbook plus one (4.2) | Layer 4, PR 4: the same rule as the queue. |
| 2026-11-08 | A shared atomic writer, `umwayi/fsutil.py` (4.6) | Layer 4, PR 4: one tested way to write a file. |

## Open questions

- `umwayi archive restore` is not built; the output of `archive move` already names it ([tasks.md](../.kiro/specs/umwayi-os/tasks.md), layer 4).
