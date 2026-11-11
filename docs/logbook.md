# Logbook (layer 5, with crash safety and the hash chain)

## Purpose

The logbook is `LOGBOOK.md`, append only, with one entry for every change umwayi makes, a whole-file hash record, crash safe writes and a hash chain over the entries. It exists so the owner can see what happened and can tell when the record was changed.

## Current state

`LOGBOOK.md` is append only. Every umwayi command that changes something adds one entry:

An example entry (shown as text, not a heading of this file):

```text
## 2026-11-07

- Source: umwayi queue add
- Added: ...
- Checked: ...
- Not done: ...
```

```
umwayi logbook verify
umwayi logbook seal --by "Your name" [--date 2026-11-07]
umwayi logbook recover --torn-tail --by "Your name" [--date 2026-11-07]
```

- A `umwayi check` entry ends its Checked line with `; election fallbacks: ID (review_by DATE), ...` only when a Yes rule was past its `review_by` date for that check (see [rules.md](rules.md)). Without a fallback the entry is the same as before.
- After every write the SHA-256 of the whole file is recorded in `.umwayi/logbook.sha256`. Before every write it is checked. If you edit, delete or add a line by hand, every umwayi write is refused (and `umwayi check` answers Ask me first) until you look at the file and run `umwayi logbook seal`.
- An existing logbook with no record is refused the same way. Nothing is sealed automatically.
- `verify` prints `ok` or each problem with a line number (never the line text) and exits 0 only when the format is valid and the hash matches. It never changes a file.
- Entry dates must be real and never go backwards.
- `.umwayi/logbook.lock` stops two commands from writing at once. It is a kernel lock (`flock`): a command that is killed lets go of it, so nothing is ever left behind. The file stays; never delete it while a command runs.
- `LOGBOOK.md` and `.umwayi/logbook.lock` must be regular files with one name (not a hard link): they are the two files umwayi writes in place. The append opens `LOGBOOK.md` with `O_NOFOLLOW` and checks the open file, so a link swapped in after the checks is never written through. The intent (`.umwayi/logbook.pending`) is 0600 while it holds an entry; the other files follow the owner's umask.
- A write that is stopped half way cannot break the logbook. Before appending, umwayi records its intent in `.umwayi/logbook.pending` (the hashes and lengths before and after, and the exact bytes). SIGTERM, SIGHUP, Ctrl-C and SIGQUIT wait until the write is done. After a SIGKILL or a crash, the next write finishes or drops the interrupted one, only when the files are exactly in one of the two states the intent names, and adds one entry with source `umwayi logbook recover`. Anything else is refused like a hand edit. `verify` says when a write is in progress or was interrupted, and readers see the file it left.
- A power cut during the append can leave the start of an entry at the end of the file (a torn tail). It is refused, never repaired automatically. `umwayi logbook recover --torn-tail --by NAME` cuts it back, only when the extra bytes are exactly the start of the entry that was being written, and logs the cut.

### Hash chain

```
umwayi logbook seal --chain --by "Your name" [--date 2026-11-07]
umwayi logbook anchor
umwayi logbook verify --anchor COUNT:HEX
```

- Every entry after the start of the chain has a fifth line, `- Chain: HEX`. HEX is the SHA-256 of the value before it, a newline, and the entry's lines from its `## DATE` heading through `- Not done:` (each with its newline, the blank line after the heading included). The value before the first chained entry is the SHA-256 of everything above it.
- The chain starts at a seal entry. Sealing a logbook that has no chain yet always starts it. `seal --chain` starts it on a logbook that is already sealed and intact, once; it is refused when a chain exists.
- `verify` also checks the chain and names the first broken entry by number and line (an edit, a deleted entry, a reordered pair, a missing or malformed Chain line). It still exits 0 or 1.
- A broken chain refuses every umwayi write and every job, workflow and helper start, and it cannot be sealed: restore `LOGBOOK.md` from a copy you trust (for example git).
- `anchor` prints `COUNT:HEX` (the number of chained entries and the newest value) and changes nothing. Keep it outside this machine, weekly and before each submission: in the hub repository's sync log and on the Kiro Notion page (umwayi never writes there). `verify --anchor COUNT:HEX` then also finds a rewritten chain or a cut tail. `anchor` exits 2 when the logbook does not verify or has no chain; a malformed anchor exits 64.
- Limits: [KNOWN-LIMITS](KNOWN-LIMITS.md) items 3 and 104 to 109.

### Entries of layer 13: a reopen is a new entry

A reopen never edits, deletes or marks an entry. It appends one entry of source `umwayi decision reopen`, in a fixed shape, that names the old entry by its full `Chain` value:

```text
- Added: Reopen of entry HEX (Q-0007 answered on 2026-11-05); new decision Q-0012 opened by NAME; reason: TEXT
- Checked: the hash chain was intact before this entry; HEX is a chained entry of source umwayi queue answer for Q-0007; Q-0007 is a decision that is not open; revisit if recorded then: TEXT
- Not done: The old entry, the old row Q-0007 and the rules were not changed or marked. Nothing was decided again.
```

- The answer of a decision ends its `Added` line with `; revisit if: TEXT` (or `none`). The answer itself is still only counted, never copied.
- `logbook.read_chained` gives every entry with its `Chain` value, under the same checks as the other checked readers. A reopen reads the record with it and needs the hash chain to have started.
- The id of the row a reopen opens counts as used, like an id at the start of an `Added` line, so it is never given again.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-11 | A reopen is a new entry that links the old one by its hash; the old one is never marked | Layer 13, L13.2 (13.R4.3; L13-Q17 as proposed: the hash chain is needed). |
| 2026-11-10 | `LOGBOOK.md` and its lock refuse a second name; the append never follows a link; the intent is 0600 | The security scan (S.2, PR 37): a hard link at the lock let its pid write reach an outside file, and a link swapped in before the append was written through (S-Q9 for the mode). |
| 2026-11-10 | The hash chain (C.1 to C.4, PR 32): a seal entry starts it; `seal --chain` once (C-Q1); recompute the chain on every append (C-Q2); `verify` keeps exit codes 0 and 1 (C-Q3) | Approved Nov 9 in PR 24; built in PR 32. |
| 2026-11-10 | A broken chain cannot be sealed; restore from a copy you trust | PR 32: sealing over it would hide the edit ([KNOWN-LIMITS](KNOWN-LIMITS.md) item 105). |
| 2026-11-09 | Crash safety: `flock` on `.umwayi/logbook.lock` (L-Q1); the four signals held during a write (L-Q2); a torn tail refused and cut only by `recover --torn-tail` (L-Q3); readers see the two exact states as consistent (L-Q4); bytes appended by something else are a hand edit (L-Q5) | Approved Nov 9 in PR 26; built in PR 27. |
| 2026-11-08 | `umwayi logbook seal --by NAME` is the only way to accept an edited or unrecorded logbook, never automatic (5.3) | Layer 5, PR 5: a hand edit is never accepted without the owner. |

## Open questions

- The anchor copies are the owner's job: `umwayi logbook anchor` weekly and before each submission, kept in the hub repository's sync log and on the Kiro Notion page ([tasks.md](../.kiro/specs/umwayi-os/tasks.md), C.4).
