# umwayi-os

An AI operating system for one person and their AI helpers.

It keeps memory, enforces rules before an AI helper acts, tracks a queue of tasks and decisions, archives moved text with a fingerprint, and writes a logbook of every change. It is built in layers, and each layer works alone and is tested before the next starts.

Status: all eight layers are built: memory, rules, queue, archive, logbook, automation, helpers and workflows. Known limits are listed in [docs/KNOWN-LIMITS.md](docs/KNOWN-LIMITS.md). See `.kiro/specs/umwayi-os/` for requirements, design and tasks, and `.kiro/steering/product.md` for the product rules.

## Install and test

Python 3.10 or newer, no third party packages.

```
pip install -e .          # optional, gives the `umwayi` command
python -m unittest discover -s tests -t .
```

Without installing, use `python -m umwayi` from the repo root.

## Exit codes

Every command uses the same codes:

| code | meaning |
| --- | --- |
| 0 | Yes, or done |
| 1 | refused: something was checked and found wrong, nothing was changed |
| 2 | No, or an unexpected error (a crash is treated like No, never like Yes) |
| 3 | Ask me first |
| 64 | usage or config error: wrong arguments, a value that is not allowed, or a missing or invalid `umwayi.json`, jobs file or workflow file |

A missing or broken `rules.yaml` is not a config error: it gives Ask me first.

## Layer 1: memory

```
umwayi.json                     config: memory_dir and private_paths
memory/master.md                master context
memory/projects/*.md            one file per project
memory/journal/*.md             journal
```

```
umwayi memory bundle [--format text|json]
```

Prints one context bundle for an AI helper. Anything under a path listed in `private_paths` (a file, a folder or a glob) is left out, and its name is never printed. Only a count is shown.

## Layer 2: rules

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

Fail closed: no matching rule, a broken or missing `rules.yaml`, or bad action JSON all give Ask me first. If several rules match, No beats Ask me first, and Ask me first beats Yes. Usage errors exit with 64.

Matchers (all must match):

- `type: payment` equals, ignoring case
- `type: [payment, transfer]` equals any
- `path__contains: secret` contains text
- `amount__exists: true` field is present

Use `--rules PATH` for another rules file, `--json` for JSON output, and `-` as the action to read it from standard input.

Every check writes one logbook entry with the rule id and the answer. The action JSON is never written, only its `type` if that is a short plain word. If the logbook cannot be written (for example it was edited by hand), a No stays No (exit 2), a Yes becomes Ask me first (exit 3), and the reason says why. Use `--no-log` for a dry run that writes nothing, and `--date` to set the entry date.

## Layer 3: queue

`queue.md` is a Markdown table you can read and edit by hand. The columns are id, kind (task or decision), title, status (open, answered, closed), recommendation, answer, and the date answered.

```
umwayi queue list [--status open|answered|closed] [--kind task|decision]
umwayi queue add --kind task "Write the spec" [--recommendation "Do it today"] [--date 2026-11-07]
umwayi queue answer Q-0001 --answer "Yes, go ahead" [--date 2026-11-07]
umwayi queue close Q-0001 [--date 2026-11-07]
umwayi queue migrate [--date 2026-11-07]
```

- `answer` needs `--answer` (one line, no `|`, up to 500 characters, the same limits as a recommendation). It works only on an open row. An open row has an empty answer, an answered row has an answer and the date answered.
- `close` works on an open or answered row and keeps its answer and date.
- Ids are never reused. `add` uses one more than the highest id found in `queue.md` and in the logbook, even if you delete a row by hand. If `LOGBOOK.md` exists but cannot be read, `add` refuses and says why.
- A queue.md in the old six column layout (no answer column) is refused with a message. Run `umwayi queue migrate` once to convert it. Old answered rows get the text `not recorded before migration`.
- Without `--date` the system clock is used. A malformed `queue.md` is an error with a line number, and nothing is changed. Only the row a command touches is rewritten.
- Every change appends an entry to `LOGBOOK.md` (date, source, added, checked, not done). Earlier logbook lines are never edited. The logbook records the length of an answer, not its text.

## Layer 4: archive

Moves a block of text out of a file into its own file under `archive/`, with a fingerprint, and leaves a pointer line behind.

```
umwayi archive move notes.md --lines 10-20 --reason "old plan" [--date 2026-11-07]
umwayi archive move notes.md --start "<!-- start -->" --end "<!-- end -->" --reason "old plan"
umwayi archive verify
```

- `archive/INDEX.md` is a Markdown table: id, source, moved, reason, words, sha256. `archive/A-0001.txt` holds the exact bytes of the block.
- The source gets one line in place of the block: `[archived A-0001: archive/A-0001.txt]`.
- Line ranges count from 1 and include both ends. Markers must each match one whole line, appear exactly once, and are part of the block.
- `move` refuses and changes nothing if the source is missing, a symbolic link, a private path in `umwayi.json`, or a protected file (logbook, queue, rules, config, archive, git data); if the range is empty or outside the file; if the markers are missing, repeated or in the wrong order; if the block has no words; or if the reason is empty.
- Ids look like A-0001 and are never reused: one more than the highest id in the index and in the logbook. If `LOGBOOK.md` exists but cannot be read, `move` refuses.
- The source, the archive file and the index all change or none do. If the logbook write fails, the move is undone. Each move adds one logbook entry.
- `verify` recomputes every SHA-256 and prints `ok`, `changed`, `missing` or `not in the index` for each id. It exits 0 only when all are ok, otherwise 1, and never changes a file.
- `umwayi archive restore` is not built yet. The output of `move` names it.

## Layer 5: logbook

`LOGBOOK.md` is append only. Every umwayi command that changes something adds one entry:

```
## 2026-11-07

- Source: umwayi queue add
- Added: ...
- Checked: ...
- Not done: ...
```

```
umwayi logbook verify
umwayi logbook seal --by "Your name" [--date 2026-11-07]
```

- After every write the SHA-256 of the whole file is recorded in `.umwayi/logbook.sha256`. Before every write it is checked. If you edit, delete or add a line by hand, every umwayi write is refused (and `umwayi check` answers Ask me first) until you look at the file and run `umwayi logbook seal`.
- An existing logbook with no record is refused the same way. Nothing is sealed automatically.
- `verify` prints `ok` or each problem with a line number (never the line text) and exits 0 only when the format is valid and the hash matches. It never changes a file.
- Entry dates must be real and never go backwards.
- `.umwayi/logbook.lock` stops two commands from writing at once. If a command was killed and left the lock behind, delete the file.

## Layer 6: automation

### Jobs

```
umwayi run jobs.yaml --job weekly-report [--date 2026-11-07]
```

`jobs.yaml` lists jobs. Each has a `name`, a `command` from a fixed list (`report`, `check`, `queue-list`) and `min_gap_days`. There is no way to put a shell command or another program in a job.

- The rules are asked first (action type `run_job`). No stops the job (exit 2), Ask me first stops it (exit 3).
- A job that ran fewer than `min_gap_days` days ago is refused (exit 1).
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

## Layer 7: AI helpers

AI helpers draft only. Every step an AI helper wants to take goes through the rules first, the same check as `umwayi check`:

- No stops the AI helper (exit 2).
- Ask me first stops it (exit 3) and adds a queue item of kind decision for you. Answering it is your record; it does not let the AI helper go on. To allow the action, add a Yes rule in rules.yaml.
- Only Yes continues.
- Every step adds one logbook entry. If rules.yaml is missing or broken, no AI helper runs (exit 3). If the logbook fails its tamper check, no AI helper runs (exit 1).
- An AI helper can never approve anything. The helper commands have no `--approved-by` option.
- AI helpers write files only under `drafts/` (plus their logbook entries, and the queue item when they stop on Ask me first).

### Steward

```
umwayi steward [--waiting-days 7] [--date 2026-11-07]
```

Reads `queue.md` and the logbook, and writes `drafts/steward-0001.md`: open items, items waiting longer than the given number of days, answered items not closed yet, and suggested next tasks. It never changes the queue and never answers an item.

### Social helper

```
umwayi social draft articles/week-45.md [--date 2026-11-07]
```

The article starts with front matter:

```
---
title: What I learned this week
link: https://example.org/what-i-learned
summary: One line about it (optional)
---
```

It writes one draft per channel listed in `umwayi.json`, for example `"social_channels": ["linkedin", "mastodon"]`, as `drafts/post-linkedin-0001.md`. Each post comes from one fixed template: the title, the summary (or the first paragraph), and `Read more: LINK`. Posts are at most 280 characters, plain text, with no hashtags and no em dashes. There is no model call and no network. It never posts. To publish a draft, run `umwayi publish-draft drafts/post-linkedin-0001.md`, which is Ask me first.

## Layer 8: workflows

A workflow is a file `workflows/NAME.yaml` with a name and steps in order. Each step is one command from a fixed list inside umwayi, with its arguments written in the file:

| command | arguments |
| --- | --- |
| `queue-list` | `status` (optional) |
| `steward` | `waiting_days` (optional, default 7) |
| `social-draft` | `article` (a local article file) |
| `report` | `since_days` |
| `check` | `action_type` |
| `approve` | none, and only as the last step |

There is no way to put a shell command, another program or an approval in a workflow.

```
umwayi workflow validate content-loop
umwayi workflow run content-loop [--date 2026-11-07]
```

- `validate` prints every problem with its line number and exits 64, or `ok` and exits 0.
- `run` asks the rules for every step (action type `workflow_step`). No stops it (exit 2), Ask me first stops it (exit 3). Every step adds one logbook entry. If the logbook cannot be written, the run stops.
- The shipped content loop (`workflows/content-loop.yaml`) runs collect (`queue-list`), brief (`steward`), draft (`social-draft` from `articles/example.md`) and approve.
- The approve step never approves anything. It adds a queue item of kind decision that lists the drafts, and stops the workflow with exit 3. The workflow will not run again until you answer or close that item. To publish a draft, you run `umwayi publish-draft DRAFT`, which is Ask me first.
- Workflows write only under `drafts/`, plus the queue and the logbook.

### Kill switch

```
umwayi kill on [--reason "taking a break"]
umwayi kill status
umwayi kill off
```

While the switch is on (the file `.umwayi/KILL` exists), every AI helper, job and workflow stops before doing anything, with exit 3 (Ask me first) and one logbook entry. If umwayi cannot tell whether the switch is on (for example `.umwayi` is not a normal folder), it stops too. `kill on` works even when the logbook is broken. `kill off` keeps the switch on if the logbook cannot record it. Your own commands (queue, archive, check, report, publish-draft) are not stopped.

### One run at a time

AI helpers, jobs and workflows share one lock, `.umwayi/run.lock`. If one is running and you start another, the second one does not wait: it answers Ask me first (exit 3), writes one logbook entry, and changes nothing. If locking is not available on your system, they all answer Ask me first. Your own commands (queue, check, archive, report, publish-draft) are not locked.
