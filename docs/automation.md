# Automation (layer 6)

## Purpose

Automation runs a fixed list of jobs from `jobs.yaml`, writes the weekly progress report from the local git history, and copies an approved draft to `outbox/` for the owner to post by hand. It exists so routine work runs through the rules and the logbook and never posts anything itself.

## Current state

### Jobs

```
umwayi run jobs.yaml --job weekly-report [--date 2026-11-07]
```

`jobs.yaml` lists jobs. Each has a `name`, a `command` from a fixed list (`report`, `check`, `queue-list`) and `min_gap_days`. There is no way to put a shell command or another program in a job.

- The rules are asked first (action type `run_job`). No stops the job (exit 2), Ask me first stops it (exit 3).
- A job that ran fewer than `min_gap_days` days ago is refused (exit 1), with one logbook entry `Job NAME did not run: the gap rule (...)`, so a scheduled run refused by it shows in the logbook too. That entry never counts as a run.
- Every run writes one logbook entry. If the logbook cannot be written, the job does not run.
- `--job` is needed when the file has more than one job.

umwayi does not install a schedule. To run the weekly report every Monday at 08:00, the owner could add a line like this with `crontab -e` (adjust the paths):

```
0 8 * * 1  cd /path/to/umwayi-os && umwayi run jobs.yaml --job weekly-report >> drafts/cron.log 2>&1
```

### Progress report

```
umwayi report --since 2026-11-01 [--date 2026-11-07]
```

Writes `drafts/report-0001.md` (then `-0002`, and so on, never overwriting) with commits per day and their subjects, from the local git history. It reads git through one fixed `git log` command: no network, no author names or emails, nothing written to git. Merge commits are not counted.

### Publish a draft

```
umwayi publish-draft drafts/report-0001.md --approved-by "Your name"
```

Copies the draft to `outbox/report-0001.txt` so you can post it by hand. It never posts, pushes, sends or runs git. The starter rule `publish-ask` makes publishing Ask me first, so without `--approved-by` it stops with exit 3. A rule that says No stops it even with approval. An existing outbox file is never overwritten.

`drafts/` and `outbox/` are in `.gitignore`.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-10 | A gap rule refusal writes one logbook entry and keeps exit 1 | Found by the whole-system test (S.1, PR 36): a scheduled run refused by the gap rule left no trace in the logbook (KNOWN-LIMITS 98). |
| 2026-11-08 | A job's `command` comes from a fixed list (`report`, `check`, `queue-list`); no shell (6.1) | Layer 6, PR 6: a job can never run another program. |
| 2026-11-08 | `publish-draft` copies to `outbox/` only; the starter rule `publish-ask` makes it Ask me first, and `--approved-by` lets it go on (6.3) | Layer 6, PR 6: the owner publishes, never a helper. |
| 2026-11-08 | The report reads git through one fixed `git log` command, with no author names or emails (6.2) | Layer 6, PR 6: no network and no personal data. |

## Open questions

- `--approved-by` is self-declared ([KNOWN-LIMITS](KNOWN-LIMITS.md) item 1).
- `umwayi report` run directly does not check the kill switch ([KNOWN-LIMITS](KNOWN-LIMITS.md) item 5).
- A failed publish can leave an empty `outbox/` folder ([KNOWN-LIMITS](KNOWN-LIMITS.md) item 8).
- A deleted last draft number can be used again: numbering reads `drafts/`, not the logbook ([tasks.md](../.kiro/specs/umwayi-os/tasks.md), layer 6).
