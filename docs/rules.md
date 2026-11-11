# Rules (layer 2)

## Purpose

The rules layer answers Yes, No or Ask me first for every action before an AI helper, job, workflow, adapter or agent takes it, from the owner's `rules.yaml`. It exists so nothing acts without a rule the owner wrote, and so a missing or broken rule never means Yes.

## Current state

Rules live in `rules.yaml`. Each rule has an id, a title, text, a verdict (`yes`, `no` or `ask`), and optionally a cause, matchers and, on a Yes rule, a `review_by` date.

```
umwayi check '{"type": "payment", "amount": 5}'
```

Prints the answer, the rule id and the reason:

```
No
Rule: no-money
Reason: AI helpers never move money or use bank or card credentials. Cause: Safety rule for all AI helpers.
```

| answer | exit code |
| --- | --- |
| Yes | 0 |
| No | 2 |
| Ask me first | 3 |

Fail closed: no matching rule, a broken or missing `rules.yaml`, or bad action JSON all give Ask me first. If several rules match, No beats Ask me first, and Ask me first beats Yes. Usage errors exit with 64. The rules file (`rules.yaml` or `--rules PATH`, or a link to one) is read only when it is a regular file of at most 1 MB; anything else, `/dev/zero` or a FIFO among them, is a broken rules file and gives Ask me first.

Matchers (all must match):

- `type: payment` equals, ignoring case
- `type: [payment, transfer]` equals any
- `path__contains: secret` contains text
- `amount__exists: true` field is present

Use `--rules PATH` for another rules file, `--json` for JSON output, and `-` as the action to read it from standard input. `--kill-switch` answers No while the kill switch is on or its state is unknown (the adapters use it; without it your own checks are not stopped).

Every check writes one logbook entry with the rule id and the answer. The action JSON is never written, only its `type` if that is a short plain word. If the logbook cannot be written (for example it was edited by hand), a No stays No (exit 2), a Yes becomes Ask me first (exit 3), and the reason says why. Use `--no-log` for a dry run that writes nothing, and `--date` to set the entry date.

### Review dates: a Yes rule that runs out (layer 13, elections)

A Yes rule may have `review_by: 2026-12-01` (a real date, `YYYY-MM-DD`). The rule is in force through the whole of that day. From the next day it counts as an Ask me first rule in every check: `umwayi check`, the agent gates, the schedule, and the callers that have no logbook (jobs, AI helpers, `publish-draft`, the inner checks of a workflow). The file is not edited and the rule is not deleted; the owner renews it by editing the date.

- `review_by` is allowed on Yes rules only. On a No rule, on an Ask rule, or with a date that is not real (`2026-13-01`, `2026-2-1`, `20261101`, `tomorrow`, a list, an empty value), `rules.yaml` is malformed and every check gives Ask me first. Do not put `review_by` in a rules file before this version is installed: the older code calls it an unknown field.
- The date of a check is the latest of the system date, `--date` and the newest date in the logbook, so a past `--date` or a clock set back does not bring a lapsed rule back. If the logbook cannot be read, the first two are used (and the entry cannot be written, so no Yes comes out).
- Strongest wins as before, with the lapsed rule counted as Ask me first: a matching No still gives No, and a lapsed Yes beside a Yes that has not lapsed gives Ask me first.
- The fallback is logged. The check's own entry ends its Checked line with `; election fallbacks: report-yes (review_by 2026-11-20)` for every matching rule that fell back (ten are named, then `, and N more`). `--json` adds `"election_fallbacks": ["report-yes"]`, and the text output adds an `Election fallbacks:` line. When no rule fell back, the entry, the JSON and the text are the same bytes as before.
- A rule with no `review_by` never lapses. That is the owner's choice.

```
umwayi rules due [--within DAYS] [--date YYYY-MM-DD]
```

Lists every rule that has lapsed, is due within DAYS days (default 14, from 0 to 3650), or has a date more than 366 days ahead (`far`; it is still in force, the word is a warning). Oldest first, then by id, and the number of Yes rules that have no `review_by`:

```
lapsed  2026-11-01  report-yes  10 days ago
due     2026-11-20  weekly-yes  in 9 days
far     2030-01-01  old-yes     in 1147 days
Yes rules without review_by: 2
```

It writes nothing (no file, no logbook entry) and prints no rule title, text or cause. Exit 0 when no rule has lapsed. Exit 3 when one has, or when `rules.yaml` is missing or broken (it says it cannot list). Exit 64 for a bad argument, 2 for an unexpected error. It never exits 1.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-11 | A Yes rule past its `review_by` counts as Ask me first, in every caller of the rules; a lapsed Yes beside a fresh Yes gives Ask me first (L13-Q16, proposal used); `rules due` exits 3 when a rule lapsed (L13-Q9, proposal used); a date more than 366 days ahead is listed as `far` (L13-Q10, proposal used) | L13.1, 13.R2 and 13.R3. |
| 2026-11-10 | The rules file is read only as a regular file of at most 1 MB | The security scan (S.2, PR 37): a rules file that was a link to /dev/zero made `umwayi check` read forever. |
| 2026-11-08 | `umwayi check --kill-switch` answers No while the kill switch is on or unknown (9.12) | Layer 9, PR 12: the owner answered that adapters deny everything while the kill switch is on. |
| 2026-11-08 | `umwayi check --json` gives `answer`, `rule_id`, `rules_ok`, `action_ok` and `logged` (9.2) | Layer 9, PR 11: an adapter never reads the reason text. |
| 2026-11-08 | When the logbook cannot be written, a No stays No (exit 2) (6.5) | Layer 6, PR 6: a refusal is never weakened by a logbook failure. |
| 2026-11-07 | Fail closed: no matching rule, a broken or missing `rules.yaml`, or bad action JSON give Ask me first; No beats Ask me first beats Yes (2.3) | Layer 2, PR 1: an unknown case is never a Yes. |

## Open questions

- 9.10: starter rules for adapter actions in the repo `rules.yaml`. Example rules exist in each adapter folder; the repo `rules.yaml` is unchanged ([tasks.md](../.kiro/specs/umwayi-os/tasks.md), layer 9).
