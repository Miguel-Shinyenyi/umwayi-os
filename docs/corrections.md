# Corrections (layer 13): elections, reversal, courts

## Purpose

Layer 13 lets the owner correct umwayi without rewriting its record: a standing approval runs out unless the owner renews it, a closed decision can be reopened, an AI helper can object to a No without changing it, and every rules change is logged before it is used. It exists so that trust can be taken back and a wrong state can be found and dated. Graded autonomy, the fifth part of the layer, has its own page: [autonomy.md](autonomy.md).

## Current state

**Elections (L13.1), Reversal (L13.2), Courts with the rules change log (L13.3) and Honest tension (L13.4, this page and the words test) are built. Graded autonomy is specified, not built.** The spec is in the L13.0 pull request (PR 40). The commands of the parts not built yet do not exist. Requirements: [13.R1 to 13.R15](../.kiro/specs/umwayi-os/requirements.md), design: [Layer 13](../.kiro/specs/umwayi-os/design.md), tasks: [L13.0 to L13.6](../.kiro/specs/umwayi-os/tasks.md).

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

### Courts and the rules change log (L13.3, built)

```
umwayi petition RULE_ID --helper NAME --reason TEXT [--date D]
```

- An AI helper objects to a No. The petition becomes one open decision in the queue, titled `Petition against rule RULE_ID by HELPER`. The rule id and the name are checked, so the title holds no free text.
- **It never changes the verdict.** `rules.yaml` is not written and no answer changes, before or after any number of petitions, and after the owner answers them. Only the owner editing `rules.yaml` changes a rule, and that edit is logged before use (below).
- Only a rule that exists with the verdict No can be petitioned. A Yes, an Ask me first, a missing rule or a `rules.yaml` that cannot be read is refused with exit 1 and nothing written.
- `--helper` is a name: a lowercase letter, then up to 39 lowercase letters, digits, `_` or `-`. `--reason` is one line of plain text, 1 to 200 characters, without `|`. A bad value exits 64.
- **The reason is untrusted text.** It is shown in `queue.md` after `Petition, untrusted text from an AI helper:`. It is never copied to the logbook (the entry holds its length) and never printed in a message, and no code reads it.
- **Limits against spam**, counted from `queue.md` (open petitions) and the logbook (petitions accepted on the day of the entry), never from the command line: one open petition for a helper and rule (a second prints `Already open, nothing added: Q-...` and exits 0), 3 open for one helper, 10 open in all, 5 accepted a day for one helper and 10 a day in all. Past a limit the command exits 1, says which limit, and writes nothing. One petition runs at a time (`.umwayi/petition.lock`).
- An accepted petition writes one row and one entry in the same queue commit. It needs no hash chain, but a logbook that fails the tamper check or the chain is refused.
- The owner answers it like any decision: `umwayi queue answer Q-... --answer TEXT --revisit-if TEXT`.
- **The rules change log.** Every command that asks the rules logs a changed `rules.yaml` before it uses it, as one `umwayi rules` entry with the hash, the counts and the changed ids, verdicts and dates, never rule text. If that entry cannot be written, every Yes from the new rules becomes Ask me first and a No stays a No. A weakened rule is used at once and is visible in the logbook (L13-Q11). Details: [rules](rules.md).
- The example rules of the adapters leave `umwayi petition` to the owner: each has a comment that says how to refuse it.

### Stop criteria

These are the stop criteria of 13.R8.3 (the build) and 13.R8.4 (run time), then the stop of each built part. Each row says what stops, when, and who acts. The run time rows are the same on the [autonomy page](autonomy.md). They are criteria, not proof that nothing goes wrong.

| criterion | what stops | stops when | who acts |
| --- | --- | --- | --- |
| 13.R8.3 (a) | the merge of a slice | its acceptance tests and planted faults do not pass on Python 3.10 to 3.13, or its docs are not current | the slice is not merged until they do |
| 13.R8.3 (b) | the merge of a slice | it is not merged by Nov 28 | it is not merged; it stays specified, not built, in the docs |
| 13.R8.3 (c) | every merge | Nov 29 to Dec 2, the freeze | nothing is merged except a fix for a defect that a test finds |
| 13.R8.3 (d) | the merge of a slice that breaks an earlier test | an earlier test fails | the slice is not merged until that is fixed, never by changing the earlier test |
| 13.R8.3 (e) | the layer | the owner says stop, or Dec 3 | the owner; the slices before it stay |
| 13.R8.4 (a) | graded autonomy (specified, not built) | it is off by default: `enabled: false`, or no `autonomy.yaml` | the owner turns it on, with every setting present |
| 13.R8.4 (b) | moves of one action class (specified, not built) | a `rejected` or `reverted` record, for the cooldown | the gates; the owner's record decides |
| 13.R8.4 (c) | every part | its input is not intact (built for elections, reversal and courts; specified for graded autonomy) | the part falls back to Ask me first, or refuses with nothing changed |
| 13.R8.4 (d) | moves of graded autonomy (specified, not built) | the kill switch is on or its state is unknown | the kill switch, at once |
| an election | a rule with no `review_by` never lapses | there is no date | the owner adds the date (built) |
| a reopen | it is a question, not a change | it is asked | the owner answers (built) |
| a petition | the petitions of one helper or in all | a limit of 13.R6.5 is reached | the command refuses (built) |

L13.3 changed the counts of 43 earlier tests for the baseline rules entry of 13.R7.2, listed in PR 48, and this is a known departure from row (d), for the owner to judge.

### No state is perfect

The owner wants umwayi to correct itself and to be safe. Each way to correct something is also a way to be wrong: a date can be set too far ahead, a reopen can be forgotten, a petition can be a bad idea, a score can be built on careless approvals. umwayi makes each state visible and dated, and falls back to Ask me first when it is not sure. It does not make any state perfect, and nothing in these pages says it does.

Known limits of this layer are in [KNOWN-LIMITS.md](KNOWN-LIMITS.md). Elections added 160 and 161; Reversal added 162 and 163; Courts added 192 to 195. The design planned 164 and 165 for the petition names and the weakened rule; those limits are items 192 and 193, because main used 180 to 191 for layer 10 before Courts was built, so 164 and 165 are not used. 166 to 170 are left for graded autonomy (L13.5), and 171 to 179 stay free.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-11 | Honest tension built (L13.4): the stop criteria table lists the rows of 13.R8.3 and 13.R8.4, the note is on both pages in the design's words, and `tests/test_honest.py` searches the pages, the help and the output of the built commands for the banned list; limits 162 and 163 are written, and 164 and 165 are not used | The L13.4 pull request. |
| 2026-11-11 | Courts and the rules change log built (L13.3) with the proposals of L13-Q11 (a weakened rule is logged and used at once) and L13-Q12 (the limits and a free text reason); the new L13-Q19 (a dry run logs no rules change and keeps its answer) and L13-Q20 (only ids, verdicts and dates are listed) are open, with their proposals used | The L13.3 pull request. |
| 2026-11-11 | Reversal built (L13.2) with the proposals of L13-Q1 (a new row, the old one untouched), L13-Q2 (the revisit text in the answer entry) and L13-Q17 (the hash chain is needed) | The L13.2 pull request; the questions are open and the build uses their proposals. |
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
- L13-Q19 (new, L13.3): a dry run (`--no-log`) writes no rules entry and answers from the rules as they are. The other choice is that a dry run of unlogged rules gives no Yes; it would change the answers of earlier dry run tests.
- L13-Q20 (new, L13.3): the change log lists ids, verdicts and `review_by`, so a change of a rule's matchers, title or text shows as `no rule changed` with a new hash. The other choice is a short hash of each rule's matchers in the state.
