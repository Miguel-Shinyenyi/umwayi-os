# Queue (layer 3)

## Purpose

The queue is `queue.md`, a Markdown table of tasks and decisions that the owner and umwayi both read. It exists so every Ask me first and every open decision has one place where the owner sees it and records the answer.

## Current state

`queue.md` is a Markdown table you can read and edit by hand. The columns are id, kind (task or decision), title, status (open, answered, closed), recommendation, answer, and the date answered.

```
umwayi queue list [--status open|answered|closed] [--kind task|decision]
umwayi queue add --kind task "Write the spec" [--recommendation "Do it today"] [--date 2026-11-07]
umwayi queue answer Q-0001 --answer "Yes, go ahead" [--date 2026-11-07]
umwayi queue close Q-0001 [--date 2026-11-07]
umwayi queue migrate [--date 2026-11-07]
```

- `answer` needs `--answer` (one line, no `|`, up to 500 characters, the same limits as a recommendation). It works only on an open row. An open row has an empty answer, an answered row has an answer and the date answered.
- `add --if-not-open` adds nothing if an open row of the same kind with exactly the same title exists, and prints `Already open, nothing added: Q-...` (the adapters use it, so a repeated Ask me first does not fill the queue).
- `close` works on an open or answered row and keeps its answer and date.
- Ids are never reused. `add` uses one more than the highest id found in `queue.md` and in the logbook, even if you delete a row by hand. If `LOGBOOK.md` exists but cannot be read, `add` refuses and says why.
- A queue.md in the old six column layout (no answer column) is refused with a message. Run `umwayi queue migrate` once to convert it. Old answered rows get the text `not recorded before migration`.
- Without `--date` the system clock is used. A malformed `queue.md` is an error with a line number, and nothing is changed. Only the row a command touches is rewritten.
- Every change appends an entry to `LOGBOOK.md` (date, source, added, checked, not done). Earlier logbook lines are never edited. The logbook records the length of an answer, not its text.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-08 | `queue add --if-not-open` adds nothing while an open item of the same kind and title exists (9.6) | Layer 9, PR 12: a repeated Ask me first from an adapter must not fill the queue. |
| 2026-11-07 | An `answer` column and a required `--answer`; `close` keeps the answer and date (3.8, 3.9) | Layer 3, PR 3: an answered decision keeps its answer. |
| 2026-11-07 | Ids are never reused: the highest id in `queue.md` and in the logbook plus one (3.10) | Layer 3, PR 3: a deleted row must not let an id mean two things. |
| 2026-11-07 | The old six column layout is refused; `umwayi queue migrate` converts it once and logs it (3.11) | Layer 3, PR 3: an old file is never rewritten silently. |

## Open questions

None open.
