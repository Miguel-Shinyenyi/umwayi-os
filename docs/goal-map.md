# The goal map

## Purpose

This page is the contract of the goal map: one JSON document that says where the newest goal stands, for the goal map page (W38) and for the owner at the terminal. It is written by W37. The page builds on these field names, so they do not change without a new `version`.

## Current state

Built by W37 with the owner's word of Nov 15. The same document comes from two places, made by one function (`map_data` in `umwayi/goal.py`):

- `umwayi goal map` prints it. It takes no argument, changes nothing and exits 0 (2 on an unexpected error, 64 for an extra argument).
- `GET /v1/goal-map` of `umwayi serve` sends it as the `data` of the usual response. It needs the token like every route, and it is a read: it gets its rules check and its request entry in the logbook like every other read (W6.R7.7), and the kill switch does not stop it. The row `goal.map` is in the route table of [serve.md](serve.md).

There is no stream and no polling. The page asks once when the owner acts, as for every other route, because W6.R14.6 says the page does not poll and every request is logged.

### The document

```
{
 "version": 1,
 "now": "2026-11-15T06:20:50Z",
 "kill_switch": "off",
 "goal": {"id": "G-0007", "title": "...", "state": "active", "budget": {"used_uu": 34, "reserved_uu": 30, "cap_uu": 200},
          "needs_owner": true},
 "supervisor": {"alive": true, "pid_known": true, "last_event_age_s": 12, "state": "watching T-01"},
 "tasks": [{"id": "T-01", "title": "...", "state": "running", "role_now": "builder",
            "worktree": {"branch": "umwayi/g-0007-t-01", "clean": null}, "age_s": 42, "needs_owner_reason": null, "pr": null}],
 "events": [{"t": "2026-11-15T06:20:38Z", "kind": "state", "task": "T-01", "text": "state changed"}],
 "notes": []
}
```

| field | what it holds |
| --- | --- |
| `version` | always 1 |
| `now` | the time the document was made, UTC, `YYYY-MM-DDTHH:MM:SSZ` |
| `kill_switch` | `on`, `off` or `unknown` (with a note) |
| `goal` | the newest goal (the highest id), or `null` when there is none. Then `tasks` and `events` are empty |
| `goal.title` | the goal text as a label (see Labels) |
| `goal.state` | `plan`, `refused`, `active`, `waiting`, `merged`, `failed`, `stopped` (as `umwayi goal status` derives it), or `unknown` |
| `goal.budget` | `used_uu` is the plan budget once the guide ran plus what the tasks spent; `reserved_uu` is the cap of the current run of each running task; `cap_uu` is the goal budget (or the plan budget before approval). `null` when a file could not be read |
| `goal.needs_owner` | true when a plan waits for approval or a task is in `needs owner` |
| `supervisor.alive`, `pid_known` | read from the lock file, see Supervisor |
| `supervisor.last_event_age_s` | seconds since the newest event of any task of the goal (polls included), or `null` |
| `supervisor.state` | `idle`, `alive`, `watching T-NN`, `lost` (not alive while a task is running) or `unknown` |
| `tasks[].state` | `queued`, `running`, `in review`, `needs owner`, `merged`, `failed`, `stopped`, `plan`, or `unknown`. A dropped task is left out |
| `tasks[].role_now` | `builder`, `tester` or `guide` while the task runs (from its last started event; `builder` before one), else `none`. The check run shows as `none` |
| `tasks[].worktree` | `{branch, clean}` once the task has a branch, else `null`. The branch is made from the ids (`umwayi/g-0007-t-01`), never read from a file |
| `tasks[].worktree.clean` | always `null`: knowing it needs a git process, and this document starts none |
| `tasks[].age_s` | seconds since the task's last state change, or `null` |
| `tasks[].needs_owner_reason` | the reason word (`ask`, `unclear`, `busy`, `dirty`, `leftover`, `stale`, `config`) when the task needs the owner, else `null` |
| `tasks[].pr` | always `null`: the goal files record a merge commit, not a pull request number |
| `events` | the last 40 real events of all tasks of the goal, oldest first; polls and waits are left out |
| `events[].text` | a fixed label for the kind, never the event's data (for example `state changed`, `a helper started`, `the helper wrote output`) |
| `notes` | fixed sentences, one for each thing that could not be read |

### Labels

A title is the owner's goal text or the task's goal sentence from the plan. It is cut to 80 characters, and every word that could be a path, a command flag, a key or a secret is replaced by `[hidden]`: a word with a digit (a plain number of up to five digits is kept), a slash or a sign such as `=`, `$` or a backquote; a word that starts with `-`; a word of 8 or more letters with no small letter; a word longer than 24 characters. A title made only of ordinary words is shown as written.

### Unknowns, never guesses

- A logbook that does not pass its check (a hand edit, a broken chain, an entry of `umwayi goal` that is not in its form): every goal and task state is `unknown`, and a note says so. Through the route the request is refused before the map is read (500, the word `logbook`), because its rules check cannot be logged in a logbook that fails its check, as for every route; the command still prints the document with the note.
- A goal or task file that cannot be read: its state is `unknown`, its title `unreadable`, the budget `null`, and a note.
- A goal folder that is a link or not a folder: `goal` is `null` and a note says this is not the same as no goal.
- Event log lines that cannot be read are left out, with a note, and never quoted.
- A kill switch that cannot be read is `unknown`, with a note.

### Supervisor

The supervisor holds `.umwayi/goal.lock` while it runs. The map never takes that lock: it reads the file's place on disk with `lstat` and the kernel's table of file locks (`/proc/locks`, Linux), and `alive` is true when some process holds a lock on that file now. This is a best guess: it says a lock is held, not that the holder is a healthy supervisor. Where the table cannot be read (not Linux, or a sandbox without `/proc`), `alive` and `pid_known` are false, `state` is `unknown` and a note says so.

## Decisions log

- 2026-11-15: the owner agreed to the eight points of the W37 review: the route is `GET /v1/goal-map` under `/v1/`, it is logged like every other read, there is no stream and no polling, the command and the route share `map_data`, `clean` and `pr` are always null, titles are labels and event text is a fixed label, and the supervisor is read from the lock file without locking it.
- 2026-11-15: the newest goal is shown, because the page draws one goal. A later version may take a goal id, which needs a new route row.

## Open questions

- Should the page get live updates? Recommendation: only through a spec change of W6.R14.6, as a long poll that answers when the document changes or after 25 seconds, and only after the logbook volume of reads has been looked at.
