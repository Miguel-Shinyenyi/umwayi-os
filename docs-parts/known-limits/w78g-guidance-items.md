section: Guidance items of W78 point 5
title: The task card, the refusal step and the counts are guidance and bookkeeping, not enforcement
number: 332

These are facts of the code of this change.

- The task card is text. A model can ignore it. The gate and the scope check decide.
- The rules in the card are matched by the `platform` of a rule. A rule written with another matcher is counted as a general rule and its text is not shown.
- The `Allowed next` step is one fixed sentence for each answer. It does not say which action would be allowed.
- Refusals written by `umwayi check` itself, without the adapter gate, have no step. Only the adapters add it.
- The counts cover calls that went through `umwayi check` while the task ran. A helper whose calls never reach the gate is counted as zero. A count of zero is not proof of obedience.
