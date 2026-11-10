# Memory (layer 1)

## Purpose

The memory layer turns the owner's plain Markdown files into one context bundle for an AI helper, and keeps private paths out of it. It exists so a helper gets the context it needs and never the files the owner marked private.

## Current state

```
umwayi.json                     config: memory_dir and private_paths
memory/master.md                master context
memory/projects/*.md            one file per project
memory/journal/*.md             journal
```

```
umwayi memory bundle [--format text|json]
```

Prints one context bundle for an AI helper. Anything under a path listed in `private_paths` (a file, a folder or a glob) is left out, and its name is never printed. Only a count is shown.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-08 | A `memory` folder that is a link loop is a config error (64), not a crash (H.6) | Hardening, PR 9: every bad configuration gives a usage error, never a traceback. |
| 2026-11-07 | Private paths (a file, a folder or a glob) are left out and their names are never printed; only a count is shown (1.2, 1.5) | Layer 1, PR 1: a private file must not reach a helper, not even by name. |
| 2026-11-07 | Memory is plain files the owner writes; there is no `umwayi memory add` | Layer 1, PR 1; [KNOWN-LIMITS](KNOWN-LIMITS.md) item 10. |

## Open questions

None open.
