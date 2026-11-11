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

A rules change and a petition are new entries too, in fixed shapes:

```text
- Source: umwayi rules
- Added: rules.yaml changed (sha256 HEX); rules 14 to 15; added a-id; removed b-id; changed c-id verdict no to ask
- Checked: rules.yaml was read and parsed before this entry; this entry is written before the new rules are first used; state: ID VERDICT[ review_by DATE]; ...
- Not done: Only rule ids, verdicts, dates and counts are logged, not rule text. No action was checked by this entry.

- Source: umwayi petition
- Added: Q-0031 (decision) as open: Petition against rule ID by HELPER
- Checked: rule ID exists with verdict No; limits held (open for this helper 1 of 3, open in all 4 of 10, accepted today for this helper 1 of 5, in all 4 of 10); reason N characters
- Not done: The rule, rules.yaml and every answer were not changed. The reason text is in queue.md and not copied here.
```

- The other rules shapes are `rules.yaml first logged (sha256 HEX); rules N` (the baseline) and the endings `no rule changed`, `the rules are not listed (more than 200)` and `the earlier state was not listed, so this entry is a new baseline`. The state is `no rules` or `too many rules to list` when there is nothing to list or too much.
- A rules entry is read back only when all three of its lines match these shapes exactly. The entry is decided under the logbook lock (`logbook.append_with`), so two checks that see one change write one entry.
- The reason of a petition is never written to the logbook, only its length.

Graded autonomy adds three shapes, each read back only when every line matches:

```text
- Source: umwayi autonomy record
- Added: outcome approved for class git-commit recorded by NAME; ref Q-0007
- Checked: the hash chain was intact before this entry; the class and the outcome were checked against the allowed words
- Not done: Nothing was moved or changed by this entry. The score is computed when a check runs, not here.

- Source: umwayi autonomy
- Added: autonomy.yaml changed (sha256 HEX): min_lower_bound 850 to 800
- Checked: autonomy.yaml was read and validated before this entry; this entry is written before the new values are first used; settings: version 1, enabled true, ...
- Not done: Only the setting names and numbers are logged. Nothing was moved by this entry.

- Source: umwayi check
- Added: Rule commit-ask gave Ask me first and autonomy moved it to Yes; action type: tool_bash
- Checked: ...; rules matched: commit-ask; autonomy: moved to Yes; class git-commit; approved 80; edited 2; rejected 0; reverted 0; weight 3; n 82; score 884 per mille; needs n 30 and score 850; reversible yes; cost 2 of 10 UU; moves today 1 of 5
```

- The settings entry is also `autonomy.yaml first logged (sha256 HEX)` and `autonomy.yaml removed`. A check that matched an opt-in rule and did not move ends its `Checked` line with `; autonomy: no move (WORD)`; with graded autonomy off, the check's entry is the same bytes as before.
- One entry of the sources `umwayi autonomy record` or `umwayi autonomy` that is out of shape or not chained makes the whole record invalid: no class moves until the logbook is restored from a copy the owner trusts.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-11 | The record, the settings and the move entries of graded autonomy; one entry out of shape invalidates the whole record | Layer 13, L13.5 (13.R9.5, 13.R9.6, 13.R10.5). |
| 2026-11-11 | The rules change and the petition entries; a rules entry is decided under the lock | Layer 13, L13.3 (13.R6.6, 13.R7). |
| 2026-11-11 | A reopen is a new entry that links the old one by its hash; the old one is never marked | Layer 13, L13.2 (13.R4.3; L13-Q17 as proposed: the hash chain is needed). |
| 2026-11-10 | `LOGBOOK.md` and its lock refuse a second name; the append never follows a link; the intent is 0600 | The security scan (S.2, PR 37): a hard link at the lock let its pid write reach an outside file, and a link swapped in before the append was written through (S-Q9 for the mode). |
| 2026-11-10 | The hash chain (C.1 to C.4, PR 32): a seal entry starts it; `seal --chain` once (C-Q1); recompute the chain on every append (C-Q2); `verify` keeps exit codes 0 and 1 (C-Q3) | Approved Nov 9 in PR 24; built in PR 32. |
| 2026-11-10 | A broken chain cannot be sealed; restore from a copy you trust | PR 32: sealing over it would hide the edit ([KNOWN-LIMITS](KNOWN-LIMITS.md) item 105). |
| 2026-11-09 | Crash safety: `flock` on `.umwayi/logbook.lock` (L-Q1); the four signals held during a write (L-Q2); a torn tail refused and cut only by `recover --torn-tail` (L-Q3); readers see the two exact states as consistent (L-Q4); bytes appended by something else are a hand edit (L-Q5) | Approved Nov 9 in PR 26; built in PR 27. |
| 2026-11-08 | `umwayi logbook seal --by NAME` is the only way to accept an edited or unrecorded logbook, never automatic (5.3) | Layer 5, PR 5: a hand edit is never accepted without the owner. |

## Open questions

- The anchor copies are the owner's job: `umwayi logbook anchor` weekly and before each submission, kept in the hub repository's sync log and on the Kiro Notion page ([tasks.md](../.kiro/specs/umwayi-os/tasks.md), C.4).
