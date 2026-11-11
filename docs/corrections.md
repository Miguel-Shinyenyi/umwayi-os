# Corrections (layer 13): elections, reversal, courts

## Purpose

Layer 13 lets the owner correct umwayi without rewriting its record: a standing approval runs out unless the owner renews it, a closed decision can be reopened, an AI helper can object to a No without changing it, and every rules change is logged before it is used. It exists so that trust can be taken back and a wrong state can be found and dated. Graded autonomy, the fifth part of the layer, has its own page: [autonomy.md](autonomy.md).

## Current state

**Reversal is built (L13.2); the other parts are specified, not built.** The spec was merged in the L13.0 pull request (PR 40). `umwayi decision reopen` and `umwayi queue answer --revisit-if` exist; the other commands on this page do not yet, and no `rules.yaml` may use `review_by` before the Elections slice is merged (the current code calls a rules file with an unknown field malformed, so every check would give Ask me first). Requirements: [13.R1 to 13.R15](../.kiro/specs/umwayi-os/requirements.md), design: [Layer 13](../.kiro/specs/umwayi-os/design.md), tasks: [L13.0 to L13.6](../.kiro/specs/umwayi-os/tasks.md).

The parts are built in this order, each one shipping alone. The owner stops the build where Dec 3 finds us, and the last day a slice can be merged is Nov 28.

### What never changes

- A No is never changed by anything in this layer.
- Every part here only moves toward Ask me first. Only graded autonomy can move toward Yes, and only Ask me first to Yes ([autonomy.md](autonomy.md)).
- Any input that is missing, malformed or unreadable gives Ask me first, or a refusal with nothing changed.
- Every change is one logbook entry. No part edits, deletes or marks an existing entry.

### Elections (L13.1)

- A Yes rule may carry `review_by: YYYY-MM-DD`. The rule is in force through that day. From the next day it counts as an Ask me first rule for every check. The file is not edited.
- The date of a check is the latest of the system date, `--date` and the newest date in the logbook, so a clock set back does not bring a rule back.
- The fallback is logged in the check's own logbook entry, with the rule id and its date.
- `umwayi rules due [--within DAYS]` lists the rules that lapsed and the ones due soon. It changes nothing. It exits 0 when no rule lapsed and 3 when one did.
- `review_by` is not allowed on a No rule. A rule without it never lapses; that is the owner's choice.

### Reversal (L13.2, built)

```
umwayi decision reopen ID_OR_HASH --reason TEXT --by NAME [--date D]
umwayi queue answer Q-0007 --answer TEXT --revisit-if TEXT|none [--date D]
```

- `decision reopen` reopens a decision that is answered or closed. The target is its queue id (`Q-0007`) or the hash of its newest closing entry (64 lowercase hex characters, the entry's `Chain` value). An id is resolved to the newest `queue answer` or `queue close` entry of that id.
- It writes one new logbook entry that says it is a reopen and names the old entry by its full hash. The old entry, the old row and every other logbook line are never changed or marked: after the command the logbook is the old file with one entry appended. A new open decision row, `Reopen decision Q-0007`, is opened in the same queue commit as the entry (both, or neither). The recommendation holds the date, the name and the reason.
- Refused with exit 1 and nothing changed: a hash no entry has; an entry that is not the newest closing entry of a decision; an id that does not exist, is a task or is still open; an entry from before the hash chain started; a logbook whose chain has not started; a decision whose reopening row is still open; a logbook that fails the tamper check or the chain; a `queue.md` that does not parse or that disagrees with the logbook. `--reason` (1 to 300 characters, no `|`) and `--by` (1 to 40, no `|` or `;`) are checked first, and a bad value exits 64.
- Once the reopening row is answered or closed, the decision can be reopened again, by either id. The link then names the newest closing entry of the reopening row, so each closing entry is reopened at most once and the reopens can be followed by hash from the newest entry back to the first.
- Answering a decision needs `--revisit-if TEXT` (what would change my mind, 1 to 200 characters, no `|`) or `--revisit-if none`. A task refuses it. Both mistakes exit 64. The text is kept in the logbook entry of the answer, never in `queue.md`, so it cannot be edited later. A reopen shows it again in its entry and its output. An answer from before layer 13 shows `not recorded before layer 13`, and a decision closed without an answer shows `not recorded, closed without an answer`. Nothing watches for the condition to come true.
- A reopen changes no rule, no answer and no verdict. It asks the question again. One reopen runs at a time (`.umwayi/reopen.lock`, a kernel lock that holds no data).
- The example rules of the Claude Code, Kiro and generic adapters refuse a shell command of an AI helper that names `umwayi decision` or `decision reopen`.

### Courts (L13.3)

- `umwayi petition RULE_ID --helper NAME --reason TEXT` lets an AI helper object to a No. The petition becomes a queue item for the owner. It never changes the verdict, and the rules file is not touched.
- The reason is untrusted text from a helper. It is shown in the queue marked as such, and it is never copied to the logbook or read by any code.
- Limits against spam: one open petition for a helper and rule, 3 open for a helper, 10 open in all, and a daily cap. A refused petition writes nothing.
- Every change of `rules.yaml` is logged before the new rules are used: the file's SHA-256, the rule ids added or removed, and each changed verdict or date, never rule text. If the entry cannot be written, no Yes comes out of the new rules for that check.

### Stop criteria

| what | stops when | who acts |
| --- | --- | --- |
| the build of a slice | an acceptance test or a planted fault fails, or it is not merged by Nov 28 | the slice is not merged; it stays specified, not built |
| the layer | the owner says stop, or Dec 3 | the slices before it stay |
| an election | a rule without `review_by` never lapses | the owner adds the date |
| a reopen | it is a question, not a change | the owner answers |
| a petition | a limit is reached | the command refuses |

### No state is perfect

The owner wants umwayi to correct itself and to be safe. Each way to correct something is also a way to be wrong: a date can be set too far ahead, a reopen can be forgotten, a petition can be a bad idea, a score can be built on careless approvals. umwayi makes each state visible and dated, and falls back to Ask me first when it is not sure. It does not make any state perfect, and nothing in these pages says it does.

Known limits of this layer are numbered from 160 in [KNOWN-LIMITS.md](KNOWN-LIMITS.md) when each slice is built.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-11 | Reversal built (L13.2) with the proposals of L13-Q1 (a new row, the old one untouched), L13-Q2 (the revisit text in the answer entry) and L13-Q17 (the hash chain is needed) | The L13.2 pull request; the questions are open and the build uses their proposals. |
| 2026-11-11 | Build the four correction mechanisms and the graded autonomy score in order (elections, reversal, courts, honest tension, graded autonomy); stop where Dec 3 finds us; each slice ships alone | The owner, Nov 11. |
| 2026-11-11 | A reopen writes a new logbook entry that states it is a reopen and links the old entry by its hash; the old entry is never changed or marked; each decision records what would change my mind | The owner, Nov 11. |
| 2026-11-11 | A petition becomes a queue item and never changes the verdict; rule changes are logged before use | The owner, Nov 11. |
| 2026-11-11 | A `review_by` date on standing approvals and Yes rules; past it the rule falls back to Ask me first; `umwayi rules due` lists them; the fallback is logged | The owner, Nov 11. |
| 2026-11-11 | Stop criteria, and a plain note that no state is perfect; nothing claims otherwise | The owner, Nov 11. |

## Open questions

L13-Q1 to L13-Q18 are open, each with a proposed answer in [design.md](../.kiro/specs/umwayi-os/design.md) ("Open questions for the owner (layer 13)"). The ones that touch this page:

- L13-Q1: a reopen adds a new row and leaves the old row as it was.
- L13-Q2: the revisit text is stored in the logbook entry, not in a new `queue.md` column.
- L13-Q9, L13-Q10, L13-Q15, L13-Q16: the exit codes of `rules due`, how far ahead `review_by` may be, no queue item for a lapsed rule, and a lapsed Yes beside a fresh Yes gives Ask me first.
- L13-Q11, L13-Q12: a weakened rule is logged and used at once; the petition limits and a free text reason.
- L13-Q14, L13-Q17: a standing approval is a Yes rule; reopen needs the hash chain.
