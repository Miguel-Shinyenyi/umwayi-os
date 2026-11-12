# Graded autonomy (layer 13)

## Purpose

Graded autonomy is a score per action class, built from the owner's own record, that can move Ask me first to Yes where a rule explicitly allows it. It exists so the owner is not asked the same question for the hundredth time, and it is built to give up at the first doubt: any state it cannot read, or does not trust, means Ask me first.

## Current state

**Built (L13.5), off by default.** Without an `autonomy.yaml`, or with `enabled: false`, nothing on this page changes an answer, and `umwayi check` gives the bytes it gave before layer 13. Requirements: [13.R9 to 13.R12](../.kiro/specs/umwayi-os/requirements.md), design: [Slice 5](../.kiro/specs/umwayi-os/design.md), tasks: [L13.5](../.kiro/specs/umwayi-os/tasks.md). The other parts of the layer are on [corrections.md](corrections.md).

```
umwayi autonomy record --class C --outcome approved|edited|rejected|reverted --by NAME [--ref Q-0007] [--date D]
umwayi autonomy status [--class C] [--date D]
umwayi autonomy validate
```

### What it does

- With graded autonomy on, a check that would give Ask me first may give Yes instead. Nothing else moves: a No stays No, a Yes stays Yes, and no matching rule stays Ask me first. Only `umwayi check` and the callers that log their own check (the agent gates and the schedule) can move; a job, a helper, `publish-draft` and the inner check of a workflow never do. A dry run (`--no-log`) never moves.
- **A rule opts in.** An `ask` rule carries `autonomy` with `class`, `reversible` (true or false) and `cost_uu` (a whole number from 0 to 1000000), and a `type` matcher (equals). Without the field the rule never moves. An `autonomy` field on a Yes or No rule, another shape, a type of the never list (`payment`, `transfer`, `purchase`, `withdraw`, `deposit`, `publish`, `post`, `send`, `publish_draft`, `schedule_install`, `budget_check`, `agent_run`, `agent_login`, `acp_permission`, `serve_request`), or two opt-in rules that give one class a different `reversible` or `cost_uu`, makes `rules.yaml` malformed, so every check gives Ask me first. An opt-in rule may have `review_by`. The opt-in is in the rules change log ([rules](rules.md)).
- **The record.** `umwayi autonomy record` writes one chained logbook entry in a fixed shape. `approved` is approved as proposed, `edited` approved after a change, `rejected` refused, `reverted` undone after it was done. It needs the hash chain (exit 1 without it or with a logbook that is not intact) and refuses a `--ref` already recorded with the same outcome (exit 1). A bad class, outcome, name, ref or date exits 64.
- **The inputs.** Only the chained entries of the sources `umwayi autonomy record` and `umwayi autonomy` are read, and the end of a check entry that has the move shape (for the moves of the day). Each line must match its fixed shape exactly. One entry that does not, an unchained one, or a duplicate `--ref`, makes the whole record invalid, and no class moves anywhere until the owner restores the logbook from a copy they trust.
- **The score.** The lower bound of the Wilson interval, in per mille, over the last `window_days` days: successes are the approved as proposed, failures are the edited, the rejected and each revert counted `revert_weight` times. It is rounded down. Few records give a low score.
- **Thirteen gates**, in the order of the design. The first that fails leaves Ask me first, and its word is written at the end of the check's `Checked` line (`; autonomy: no move (WORD)`) and in the JSON (`"autonomy": {"moved": false, "gate": WORD}`): `settings-invalid`, `kill-switch`, `chain`, `inputs-invalid`, `election-lapsed`, `not-opted-in`, `class-mismatch`, `opt-in-lapsed`, `irreversible`, `cost`, `cooldown`, `low-data`, `low-score`, `daily-cap`. A word is written only when a rule that opts in matched and `autonomy.yaml` exists; off (`autonomy-off`) and a dry run (`no-log`) write nothing new, and `status` shows them.
- **Every move is logged with its inputs**: the check's entry says `Rule ID gave Ask me first and autonomy moved it to Yes`, and its `Checked` line ends with the class, the four counts, the weight, n, the score, the thresholds, the declared reversibility and cost, and the moves of the day. If that entry cannot be written, the answer is Ask me first.
- **The score never reads text.** It reads the class word, the outcome word and the date of the fixed entries. Not a queue title, an answer, a recommendation, a reason, a petition, a rule title, text or cause, or any other logbook line.
- **Its own moves do not feed it.** Only an outcome the owner records counts.
- **The cooldown** runs through its last day: a `rejected` or `reverted` on 2026-11-30 with 30 days holds the class through 2026-12-30.

### Settings: `autonomy.yaml`

One setting turns it off: `enabled: false`, or no file. It is off by default. Every setting is required and there is no hidden default: `version` (1), `enabled`, `window_days` (1 to 3650), `min_decisions` (1 to 1000000), `min_lower_bound` (1 to 1000), `confidence_z` (hundredths, 100 to 400), `revert_weight` (1 to 100), `max_cost_uu` (0 to 1000000), `cooldown_days` (1 to 3650), `max_moves_per_day` (1 to 1000). A missing or extra key, a value out of range or a YAML error makes the file invalid, and graded autonomy is off; `umwayi autonomy validate` prints every problem with a line number and exits 64. `autonomy.example.yaml` has suggested values and `enabled: false`.

The file is logged before it is first used: one `umwayi autonomy` entry with its SHA-256 and every setting the first time, then each changed setting (`min_lower_bound 850 to 800`) or `no setting changed`, and `autonomy.yaml removed` when it goes. It is logged only once the hash chain has started; before that graded autonomy cannot move anything. If the entry cannot be written, nothing moves in that check (`chain`). Turning it off takes effect at the next check; a move already made is not undone, and the owner records `reverted` if it was wrong.

### `umwayi autonomy status`

One block per class that a rule declares or the record holds, then one line for the whole: the rule ids, the declared reversibility and cost, the four counts, the weight, n, the score and the thresholds, the cooldown, the moves of the day, and the first gate that holds the class (or `eligible`). It changes nothing. When graded autonomy is off it says so, and shows the score as a display if the settings are valid. When the inputs are invalid or cannot be read it says so and shows no score.

```
class git-commit   rule commit-ask   reversible yes   cost 2 of 10 UU
  approved 80  edited 2  rejected 0  reverted 1  weight 3  n 85  score 838 per mille  (needs n 30, score 850)
  cooldown until 2026-12-30   moves today 0 of 5   state: Ask me first (cooldown)
graded autonomy: on. inputs: intact (83 outcomes). kill switch: off.
```

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

### Stop criteria

The run time stop criteria of 13.R8.4, then the stop of graded autonomy by itself. The build criteria (13.R8.3) are on the [corrections page](corrections.md).

| criterion | what stops | stops when | who acts |
| --- | --- | --- | --- |
| 13.R8.4 (a) | graded autonomy | it is off by default: `enabled: false`, or no `autonomy.yaml` | the owner turns it on, with every setting present |
| 13.R8.4 (b) | moves of one action class | a `rejected` or `reverted` record, for the cooldown | the gates; the owner's record decides |
| 13.R8.4 (c) | every part | its input is not intact | the part falls back to Ask me first, or refuses with nothing changed |
| 13.R8.4 (d) | moves of graded autonomy | the kill switch is on or its state is unknown | the kill switch, at once |
| graded autonomy, by itself | a move | the cooldown, the daily cap, an input that is not intact or the kill switch | the gates, at the next check |

### No state is perfect

The owner wants umwayi to correct itself and to be safe. Each way to correct something is also a way to be wrong: a date can be set too far ahead, a reopen can be forgotten, a petition can be a bad idea, a score can be built on careless approvals. umwayi makes each state visible and dated, and falls back to Ask me first when it is not sure. It does not make any state perfect, and nothing in these pages says it does.

For this part in particular: the score is a statistic of the past and cannot see that today's action differs from the last eighty. A class that is too wide mixes histories. Reversibility and cost are the owner's declaration. A process of the same user can write well formed, chained inputs. The score is only as careful as the owner's record. These limits are items 166 to 170 of [KNOWN-LIMITS.md](KNOWN-LIMITS.md).

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-11 | Graded autonomy built (L13.5) with the proposals of L13-Q3 to L13-Q8, L13-Q17 and L13-Q18; the new L13-Q21 to L13-Q24 are open with their proposals used (Open questions) | The L13.5 pull request. |
| 2026-11-11 | Graded autonomy ships with its behaviour, not as a display only, and fails closed: it moves Ask me first to Yes only where a rule opts the class in; low data, irreversible or costly actions, a No, a broken chain, the kill switch on or an unknown state always mean Ask me first; every move is logged with the score inputs; the score reads counts only; one setting turns it off, off by default | The owner, Nov 11. |
| 2026-11-11 | The score is per action class, from the owner's record (approved as proposed, edited, rejected, reverted), with a cautious lower bound, reversibility, cost and owner defined thresholds | The owner, Nov 11. |

## Open questions

L13-Q1 to L13-Q18 are open, each with a proposed answer in [design.md](../.kiro/specs/umwayi-os/design.md). The ones that touch this page:

- L13-Q3: a class is a name the opt-in rule gives, not the action's `type`.
- L13-Q4, L13-Q5: reversibility and cost are declared in the rule; every threshold is required.
- L13-Q6, L13-Q7, L13-Q8: outcomes are recorded with `umwayi autonomy record`; an edit and a rejection are one failure each and a revert counts 3; z 2.58, 30 decisions and a score of 850.
- L13-Q17, L13-Q18: the hash chain is required; the cooldown is 30 days and at most 5 moves a day.
- L13-Q21 (new, L13.5): the `umwayi autonomy` entry lists every setting in its `Checked` line, so the next change can name the old value. The design's shape lists none. The other choice is to name only the changed keys and not their old values.
- L13-Q22 (new, L13.5): the cooldown is held through its last day (the outcome's date plus `cooldown_days`, inclusive), the cautious reading of "until". The other choice ends it the day before.
- L13-Q23 (new, L13.5): a gate word is written only when a rule that opts in matched and `autonomy.yaml` exists; with no file or `enabled: false` the check's entry stays the bytes of before. The other choice writes `autonomy-off` too, which would change those bytes.
- L13-Q24 (new, L13.5): the inputs are the two exact sources `umwayi autonomy record` and `umwayi autonomy` (13.R9.6), not every source that starts with `umwayi autonomy` (the design's wording).
