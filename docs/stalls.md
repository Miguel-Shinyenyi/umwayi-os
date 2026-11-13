# Stall checks (W19 part 5): `umwayi stalls check`

## Purpose

Four lessons from the Kiro Crew, as checks the owner can run on a list of builder events. They come from the W9 goal orchestration spec (W9.R9, W9.R10 and W9.R11, see [goals.md](goals.md)). The command only reports. It never stops a builder, answers an approval or changes a file.

## Current state

Built: `umwayi stalls check EVENTS.json` ([umwayi/stalls.py](../umwayi/stalls.py)). It reads one JSON list of events and prints one line for each finding.

The findings:

- `STALL b1 31 min no push or event`: a running builder with no push and no real event for 30 minutes (1800 seconds) or more. Output, poll, waiting, status and a fingerprint that did not change do not count as progress. A builder whose last state is not running, or whose last event is stopped, is not checked.
- `STOP b1 same error twice, sig 3fa91c20`: two error events in a row with the same signature. Other events between them do not break the run. A different error between them does.
- `NO ap-1 timed out, counts as No`: an approval with no answer at or past its deadline. `NO ap-1 answered after the deadline, counts as No`: the answer came at or after the deadline. Silence and late answers are never Yes.
- `REFUSED b2 status has no last event time`: a status that shows only connected. Every status must carry the last event time.

Exit codes: 0 nothing found, 3 Ask me first (any finding), 2 an unreadable or malformed file, 64 usage. Never 1.

The input is a JSON list of objects. Allowed keys: `builder`, `t`, `kind`, `sig`, `id`, `deadline`, `connected`, `last_event`, `state`, `changed`. Times are UTC like `2026-11-13T09:30:00Z`. A builder or approval id is 1 to 40 letters, digits, dots, dashes or underscores. A `sig` is 16 lower case hex characters and only on an error. Kinds: push, state, started, output, error, fingerprint, approval_requested, approval_answered, check_result, skipped, stopped, status, poll, waiting. An approval request needs an id and a deadline after its time. A status needs `connected` and may carry `last_event` (null counts as missing). Anything else, a repeated key, a time in the future, a file over 1,000,000 bytes or more than 20,000 events gives exit 2.

The command reads the system clock once. The functions in the module take the time as an argument, and the tests inject it. It is not in `jobs.yaml`, `schedule.example.yaml` or any workflow, and nothing runs it on a schedule.

## Decisions log

- 2026-11-13: The owner approved eight choices on the builder's recommendations: the event shape above, errors carried as a signature only, which events reset the stall timer, an explicit deadline on each approval, any finding gives exit 3, the system clock for the command, a future time is malformed (exit 2) and only running builders are checked for a stall.
- 2026-11-13: The same running-only rule is applied to the loop check, so a builder that already stopped is not reported again. Reason: the supervisor has already acted on it.
- 2026-11-13: A fingerprint event resets the stall timer only when it carries `changed: true`. Without the key it counts as no change. Reason: W9.R11.2 says a fingerprint with no change is not a real event.
- 2026-11-13: A builder with only non-progress events is measured from its first event. Reason: there is no other time to measure from.
- 2026-11-13: The file limits (1,000,000 bytes, 20,000 events) were chosen by the builder. The first matches `umwayi routing check`.

## Open questions

- Who writes the events file? Nothing produces it yet, because the W9 event log (`goallog`) is not built. Recommendation: when it is built, add a small exporter that writes this shape, and keep this checker reading only that.
- Should a late answer of No be reported as a finding? It is now, because the owner approved exit 3 for any approval past its deadline. Recommendation: keep it.
