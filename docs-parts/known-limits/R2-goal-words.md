section: Goal orchestration (W9), found while building the goal command words
title: a refused protected path is named by the protected list entry, not by the path the plan gave
number: 325

These are facts of the change that made the goal commands say what they know (R2.2 and R2.3 of the 2026-11-18 recordings).

- A plan refused as `protected` names the task and the protected list entry that matched (`protected: task 2, docs-parts/`). It does not name the path the guide wrote, because that text comes from the guide (W55b). When the guide listed `docs-parts/known-limits/X.md`, the owner sees `docs-parts/`.
- Only the first protected path of a plan is named, as with a context entry. A plan with a bad `files` entry that is not protected is still only `files`.
- `goal approve` prints its summary after every check has passed and before it writes. It asks no question: the owner's approval is still the typed command at a terminal. The summary is for the owner to read in the record of the terminal; it cannot be answered.
- The enforcement lines show the mode as umwayi reads it for each agent. Nothing is enforced yet, so the lines say what is recorded, not what is stopped (item 321).
