# Graded autonomy (layer 13)

## Purpose

Graded autonomy is a score per action class, built from the owner's own record, that can move Ask me first to Yes where a rule explicitly allows it. It exists so the owner is not asked the same question for the hundredth time, and it is built to give up at the first doubt: any state it cannot read, or does not trust, means Ask me first.

## Current state

**Specified, not built.** The spec is in the L13.0 pull request and waits for the owner's approval; it is the last slice of layer 13 (L13.5) and is merged whole or not at all. No command on this page exists yet. Requirements: [13.R9 to 13.R12](../.kiro/specs/umwayi-os/requirements.md), design: [Slice 5](../.kiro/specs/umwayi-os/design.md), tasks: [L13.5](../.kiro/specs/umwayi-os/tasks.md). The other parts of the layer are on [corrections.md](corrections.md).

### What it does

- With graded autonomy on, a check that would give Ask me first may give Yes instead. Nothing else moves: a No stays No, a Yes stays Yes, and no matching rule stays Ask me first.
- **A rule opts in.** An `ask` rule carries `autonomy: {class, reversible, cost_uu}`. Without it the rule never moves. Money, publishing, a schedule install, a spending approval and the start or permission of an agent can never be opted in.
- **The record.** The owner records outcomes with `umwayi autonomy record --class C --outcome approved|edited|rejected|reverted --by NAME`. Each is one chained logbook entry in a fixed shape.
- **The score.** The lower bound of the Wilson interval, in per mille, over the last `window_days`: successes are the approved as proposed, failures are the edited, the rejected and each revert counted `revert_weight` times. It is rounded down. Few records give a low score.
- **Thirteen gates**, in order. The first that fails leaves Ask me first and its word is written in the check's logbook entry: `autonomy-off`, `settings-invalid`, `no-log`, `kill-switch`, `chain`, `inputs-invalid`, `not-opted-in`, `election-lapsed`, `class-mismatch`, `opt-in-lapsed`, `irreversible`, `cost`, `cooldown`, `low-data`, `low-score`, `daily-cap`.
- **Every move is logged with its inputs**: the class, the four counts, the weight, n, the score, the thresholds, the declared reversibility and cost, and the moves of the day.
- **The score never reads text.** It reads the class word, the outcome word and the date of the fixed entries. Not a queue title, an answer, a reason or a rule title.
- **Its own moves do not feed it.** Only an outcome the owner records counts.

### Settings: `autonomy.yaml`

One setting turns it off: `enabled: false`, or no file. It is off by default. When it is on, every threshold is required (no hidden default): `window_days`, `min_decisions`, `min_lower_bound`, `confidence_z`, `revert_weight`, `max_cost_uu`, `cooldown_days`, `max_moves_per_day`. The example file `autonomy.example.yaml` is added with the build and has `enabled: false`. A change to the file is logged before it is used.

### A worked example

Settings: window 90 days, `min_decisions` 30, `min_lower_bound` 850, z 2.58, `revert_weight` 3. The class `git-commit` is reversible and costs 2 UU. Today is 2026-12-01.

| record (approved, edited, rejected, reverted) | n | score | answer |
| --- | --- | --- | --- |
| 70, 3, 1, 0 | 74 | 834 | Ask me first (`low-score`) |
| 80, 2, 0, 0 | 82 | 884 | Yes, moved and logged |
| 80, 2, 0, 1 (the revert on 2026-11-30) | 85 | 838 | Ask me first (`cooldown` until 2026-12-30, then `low-score`) |
| 20, 0, 0, 0 | 20 | 750 | Ask me first (`low-data`) |
| 80, 2, 0, 0 but the rule says `reversible: false` | 82 | 884 | Ask me first (`irreversible`) |

The full steps of the formula are in the design.

### Fail closed

Always Ask me first, never a move: off or an invalid `autonomy.yaml`; low data; an irreversible or costly action; a No; a missing or broken hash chain, a failed tamper check or an unreadable logbook; an input that is out of shape, not chained or repeated; the kill switch on or unknown; any state umwayi cannot read; a dry run or a failed logbook write; a lapsed `review_by`; the cooldown after a rejected or reverted outcome; the daily cap. An unexpected error exits 2, never Yes.

### No state is perfect

The owner wants umwayi to correct itself and to be safe. Each way to correct something is also a way to be wrong: a date can be set too far ahead, a reopen can be forgotten, a petition can be a bad idea, a score can be built on careless approvals. umwayi makes each state visible and dated, and falls back to Ask me first when it is not sure. It does not make any state perfect, and nothing in these pages says it does.

For this part in particular: the score is a statistic of the past and cannot see that today's action differs from the last eighty. A class that is too wide mixes histories. Reversibility and cost are the owner's declaration. A process of the same user can write well formed, chained inputs. The score is only as careful as the owner's record. These limits are numbered from 166 in [KNOWN-LIMITS.md](KNOWN-LIMITS.md) when the slice is built.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-11 | Graded autonomy ships with its behaviour, not as a display only, and fails closed: it moves Ask me first to Yes only where a rule opts the class in; low data, irreversible or costly actions, a No, a broken chain, the kill switch on or an unknown state always mean Ask me first; every move is logged with the score inputs; the score reads counts only; one setting turns it off, off by default | The owner, Nov 11. |
| 2026-11-11 | The score is per action class, from the owner's record (approved as proposed, edited, rejected, reverted), with a cautious lower bound, reversibility, cost and owner defined thresholds | The owner, Nov 11. |

## Open questions

L13-Q1 to L13-Q18 are open, each with a proposed answer in [design.md](../.kiro/specs/umwayi-os/design.md). The ones that touch this page:

- L13-Q3: a class is a name the opt-in rule gives, not the action's `type`.
- L13-Q4, L13-Q5: reversibility and cost are declared in the rule; every threshold is required.
- L13-Q6, L13-Q7, L13-Q8: outcomes are recorded with `umwayi autonomy record`; an edit and a rejection are one failure each and a revert counts 3; z 2.58, 30 decisions and a score of 850.
- L13-Q17, L13-Q18: the hash chain is required; the cooldown is 30 days and at most 5 moves a day.
