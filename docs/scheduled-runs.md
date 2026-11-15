# Scheduled runs (layer 11)

## Purpose

Scheduled runs let the owner's jobs and workflows run on a schedule through systemd user timers: umwayi writes two unit files and prints the `systemctl --user` commands, and never runs `systemctl` itself. It exists so routine runs happen while the owner is away, through the same kill switch, run lock, rules and logbook as a command typed by hand.

## Current state

Your jobs (`jobs.yaml`) and workflows (`workflows/`) can run on a schedule through systemd user timers, the scheduler Linux already has. umwayi writes the two unit files and prints the `systemctl --user` commands; it never runs `systemctl`, `crontab` or `loginctl` itself, and it builds no scheduler of its own. Only jobs and workflows can be scheduled, never an agent.

```
umwayi schedule validate [--file PATH]          check schedule.yaml, every problem with a line number
umwayi schedule show [NAME] [--cron]            the two unit files install would write (or the crontab lines)
umwayi schedule check [NAME]                    are the installed files exactly what umwayi would write?
umwayi schedule install NAME [--approved-by YOU]  write the two unit files (asks the rules); starts nothing
umwayi schedule remove NAME                     remove the two unit files umwayi wrote (asks the rules)
```

Copy [schedule.example.yaml](../schedule.example.yaml) to `schedule.yaml` in your root:

```yaml
schedules:
  - name: weekly-report
    run: job
    job: weekly-report
    every: weekly        # daily, weekly (day: mon to sun) or monthly (day: 1 to 28)
    day: mon
    at: "07:30"          # local time
```

- The files go to `~/.config/systemd/user` (or `$XDG_CONFIG_HOME/systemd/user`) as `umwayi-ID-NAME.service` and `.timer`, where ID comes from your root's path. The service is a oneshot that runs `python -m umwayi --root ROOT run JOBS --job JOB` (or `workflow run NAME`) with no shell, stops after 30 minutes, and stops everything it started. The timer has `Persistent=true`, so a run missed while the machine was off happens at the next start.
- Every path in them must use only letters, digits and `/ . _ + - @`; otherwise `validate` refuses it and says which path. Then nothing needs quoting.
- `install` stops at the kill switch, asks the rules (`schedule_install`; the starter rule is Ask me first, so pass `--approved-by YOUR_NAME`), takes the run lock, writes each file only if it is new, and writes one logbook entry; if that entry fails, the files are removed. Then run what it prints:

  ```
  systemctl --user daemon-reload
  systemctl --user enable --now umwayi-ID-NAME.timer
  ```

  Timers run only while you are logged in unless you enable lingering yourself (`loginctl enable-linger`).
- `remove` refuses while the timer is enabled (it prints `systemctl --user disable --now` and `clean --what=state` to run first), and refuses a file changed by hand or a drop-in next to it. It works while the kill switch is on.
- A scheduled run is the same command you would type, so it goes through the kill switch, the run lock, the rules and the logbook every time (layers 6 and 8). Its output goes to the user journal (`journalctl --user -u umwayi-ID-NAME`).
- Exit codes of `schedule` commands: 0, 2 (No, a refusal, any error), 3 (Ask me first, the kill switch, the run lock), 64 (usage or a bad schedule file). Never 1.
- A long chat that should survive a closed terminal: umwayi does not start tmux, but you can: `tmux new -s chat`, then `umwayi agent chat NAME` inside it. While the chat runs it holds the run lock, so scheduled runs answer Ask me first.
- File watching, an SQLite index and a sandbox are not built (layer 11 spec, 11.R8). Facts and links: [adapters/NOTES-layer11.md](../adapters/NOTES-layer11.md). Limits: KNOWN-LIMITS 93 to 103.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-10 | L11-Q14 (changed by the owner): build now, right after PR 30, not Nov 14 to Nov 15 | The owner's schedule. |
| 2026-11-10 | L11-Q10 to L11-Q13: file watching cut, SQLite deferred, tmux cut from umwayi, bubblewrap deferred to its own spec after Dec 3 | Approved in PR 30 (design.md, layer 11, the candidates). |
| 2026-11-10 | L11-Q5 to L11-Q9: only jobs and workflows, never an agent; `Persistent=true`; `TimeoutStartSec=30min`; umwayi never enables lingering; `umwayi run` keeps its exit 1 | Approved in PR 30. |
| 2026-11-10 | L11-Q1 to L11-Q4: only scheduled runs for Dec 3; systemd user timers, cron lines only printed; umwayi never runs `systemctl`, `crontab` or `loginctl`; `schedule_install` Ask me first with `--approved-by`, `schedule_remove` Yes | Approved in PR 30; built in PR 31. |

## Open questions

- 11.6: the owner's real check on a machine with a systemd user manager (`adapters/NOTES-layer11.md`, "The owner's real check (11.6)").
