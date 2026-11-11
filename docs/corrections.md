# Corrections (layer 13): elections, reversal, courts

## Purpose

Layer 13 lets the owner correct umwayi without rewriting its record: a standing approval runs out unless the owner renews it, a closed decision can be reopened, an AI helper can object to a No without changing it, and every rules change is logged before it is used. It exists so that trust can be taken back and a wrong state can be found and dated. Graded autonomy, the fifth part of the layer, has its own page: [autonomy.md](autonomy.md).

## Current state

**Elections (L13.1) are built. Reversal, courts and the rules change log are specified, not built.** The spec is in the L13.0 pull request. The commands of the parts not built yet do not exist. Requirements: [13.R1 to 13.R15](../.kiro/specs/umwayi-os/requirements.md), design: [Layer 13](../.kiro/specs/umwayi-os/design.md), tasks: [L13.0 to L13.6](../.kiro/specs/umwayi-os/tasks.md).

The parts are built in this order, each one shipping alone. The owner stops the build where Dec 3 finds us, and the last day a slice can be merged is Nov 28.

### What never changes

- A No is never changed by anything in this layer.
- Every part here only moves toward Ask me first. Only graded autonomy can move toward Yes, and only Ask me first to Yes ([autonomy.md](autonomy.md)).
- Any input that is missing, malformed or unreadable gives Ask me first, or a refusal with nothing changed.
- Every change is one logbook entry. No part edits, deletes or marks an existing entry.

### Elections (L13.1, built)

- A Yes rule may carry `review_by: YYYY-MM-DD`. The rule is in force through that day. From the next day it counts as an Ask me first rule for every check, in every caller of the rules. The file is not edited. `review_by` is allowed on Yes rules only; on a No rule, an Ask rule or with a date that is not real, `rules.yaml` is malformed and every check gives Ask me first. Do not write `review_by` into a rules file before the version that has this slice is installed.
- The date of a check is the latest of the system date, `--date` and the newest date in the logbook, so a clock set back does not bring a rule back.
- The fallback is logged in the check's own logbook entry (`election fallbacks: report-yes (review_by 2026-11-20)`), printed as `Election fallbacks:` and put in the JSON as `election_fallbacks`. With no fallback the entry, the JSON and the text are the same bytes as before.
- `umwayi rules due [--within DAYS] [--date D]` lists the rules that lapsed, the ones due soon and any date more than 366 days ahead (`far`). It changes nothing. It exits 0 when no rule lapsed, 3 when one did or `rules.yaml` cannot be read, 64 for a bad argument. Details and an example: [rules.md](rules.md).
- A rule without `review_by` never lapses; that is the owner's choice. There is no queue item for a lapsed rule: `rules due` is the list, and a scheduled job can run it and notice exit 3.

### Reversal (L13.2)

- `umwayi decision reopen Q-0007 --reason TEXT --by NAME` reopens a decision that is answered or closed.
- It writes a new logbook entry that says it is a reopen and names the old entry by its hash (64 hex characters, the entry's `Chain` value). The old entry is never changed or marked. A new decision row is opened in the queue; the old row is untouched.
- It needs the hash chain. A missing entry, an open decision, a task or a broken chain is refused (exit 1) and nothing changes.
- Answering a decision needs `--revisit-if TEXT` (what would change my mind, or `none`). The text is kept in the logbook entry of the answer, so it cannot be edited later, and is shown again when the decision is reopened.

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
| an election | a rule without `review_by` never lapses | the owner adds the date (built) |
| a reopen | it is a question, not a change | the owner answers |
| a petition | a limit is reached | the command refuses |

### No state is perfect

The owner wants umwayi to correct itself and to be safe. Each way to correct something is also a way to be wrong: a date can be set too far ahead, a reopen can be forgotten, a petition can be a bad idea, a score can be built on careless approvals. umwayi makes each state visible and dated, and falls back to Ask me first when it is not sure. It does not make any state perfect, and nothing in these pages says it does.

Known limits of this layer are numbered from 160 in [KNOWN-LIMITS.md](KNOWN-LIMITS.md) when each slice is built. Elections added 160 and 161.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-11 | L13.1 built with the proposals of L13-Q9 (`rules due` exits 3 when a rule lapsed), L13-Q10 (a date more than 366 days ahead is listed as `far` and still in force), L13-Q14 (a standing approval is a Yes rule), L13-Q15 (no queue item for a lapsed rule) and L13-Q16 (a lapsed Yes beside a fresh Yes gives Ask me first) | The spec says to use the proposal while a question is open. |
| 2026-11-11 | Build the four correction mechanisms and the graded autonomy score in order (elections, reversal, courts, honest tension, graded autonomy); stop where Dec 3 finds us; each slice ships alone | The owner, Nov 11. |
| 2026-11-11 | A reopen writes a new logbook entry that states it is a reopen and links the old entry by its hash; the old entry is never changed or marked; each decision records what would change my mind | The owner, Nov 11. |
| 2026-11-11 | A petition becomes a queue item and never changes the verdict; rule changes are logged before use | The owner, Nov 11. |
| 2026-11-11 | A `review_by` date on standing approvals and Yes rules; past it the rule falls back to Ask me first; `umwayi rules due` lists them; the fallback is logged | The owner, Nov 11. |
| 2026-11-11 | Stop criteria, and a plain note that no state is perfect; nothing claims otherwise | The owner, Nov 11. |

## Open questions

L13-Q1 to L13-Q18 are open, each with a proposed answer in [design.md](../.kiro/specs/umwayi-os/design.md) ("Open questions for the owner (layer 13)"). The ones that touch this page:

- L13-Q1: a reopen adds a new row and leaves the old row as it was.
- L13-Q2: the revisit text is stored in the logbook entry, not in a new `queue.md` column.
- L13-Q9, L13-Q10, L13-Q15, L13-Q16: the exit codes of `rules due`, how far ahead `review_by` may be, no queue item for a lapsed rule, and a lapsed Yes beside a fresh Yes gives Ask me first. Built with the proposals (see the Decisions log); still open for the owner to change.
- L13-Q11, L13-Q12: a weakened rule is logged and used at once; the petition limits and a free text reason.
- L13-Q14, L13-Q17: a standing approval is a Yes rule; reopen needs the hash chain.
