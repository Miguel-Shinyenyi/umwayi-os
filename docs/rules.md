# Rules (layer 2)

## Purpose

The rules layer answers Yes, No or Ask me first for every action before an AI helper, job, workflow, adapter or agent takes it, from the owner's `rules.yaml`. It exists so nothing acts without a rule the owner wrote, and so a missing or broken rule never means Yes.

## Current state

Rules live in `rules.yaml`. Each rule has an id, a title, text, a verdict (`yes`, `no` or `ask`), and optionally a cause and matchers.

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

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-10 | The rules file is read only as a regular file of at most 1 MB | The security scan (S.2, PR 37): a rules file that was a link to /dev/zero made `umwayi check` read forever. |
| 2026-11-08 | `umwayi check --kill-switch` answers No while the kill switch is on or unknown (9.12) | Layer 9, PR 12: the owner answered that adapters deny everything while the kill switch is on. |
| 2026-11-08 | `umwayi check --json` gives `answer`, `rule_id`, `rules_ok`, `action_ok` and `logged` (9.2) | Layer 9, PR 11: an adapter never reads the reason text. |
| 2026-11-08 | When the logbook cannot be written, a No stays No (exit 2) (6.5) | Layer 6, PR 6: a refusal is never weakened by a logbook failure. |
| 2026-11-07 | Fail closed: no matching rule, a broken or missing `rules.yaml`, or bad action JSON give Ask me first; No beats Ask me first beats Yes (2.3) | Layer 2, PR 1: an unknown case is never a Yes. |

## Open questions

- 9.10: starter rules for adapter actions in the repo `rules.yaml`. Example rules exist in each adapter folder; the repo `rules.yaml` is unchanged ([tasks.md](../.kiro/specs/umwayi-os/tasks.md), layer 9).
