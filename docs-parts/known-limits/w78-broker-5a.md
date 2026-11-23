section: Enforced by default (W78), found while building the broker (step 5a)
title: the broker exists and is tested on its own, but nothing starts it, nothing asks it and nothing is confined
number: 333

These are facts of the code of this change.

- `umwayi/broker.py` is built alone. No supervisor starts it, no hook of Claude Code, Kiro or OpenCode connects to it, and no confinement stops a helper from writing the logbook itself. So it protects nothing yet.
- Only `check` and `answer_status` are served. `log` is not built (open question 3 of the design: recommendation, add it when a fact is found that only the hook knows).
- The cause word `broker_lost` is not added. `Handle.lost()` says the broker has ended, and `ask` gives No when no answer comes, but no task is stopped by it.
- Every request is answered in the broker's main thread, one at a time, because the logbook write must run there. A slow `check` (a logbook lock held by another process) delays the next request. A reader thread holds one of the 16 connections for up to 10 seconds, so 16 clients that send nothing keep every other client waiting for that time; the 17th is told `busy`.
- The deadline and limits are constants of the broker's code, not settings.
- A Unix socket path is short (104 bytes on macOS), so the run folder must be a short path.
- It was run on macOS here and in CI on Linux. Nothing was run in a confinement. Whether the platforms let a hook connect to the socket is not checked.
- The queue row of an Ask me first holds the run id and the action type only. The row title is `Ask me first in run RUNID`, so one run has at most one open row at a time.
- `answer_status` reads the newest row of the run; it never returns the answer text.
