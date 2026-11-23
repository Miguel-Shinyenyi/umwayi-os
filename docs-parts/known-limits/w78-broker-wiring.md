section: Enforced by default (W78), found while wiring the broker (step 5a2)
title: an enforced Claude Code run asks the broker, but the helper can still write the logbook itself
number: 337

These are facts of the code of this change. No real Claude Code ran with it.

- Only a `claude -p` run under a mode file that says `enforced` uses the broker. Chats, the ACP adapter, Kiro and OpenCode do not.
- Nothing confines the helper, so it can still write `LOGBOOK.md` or call `umwayi check` itself. The broker adds an answer path that confinement will need; it adds no protection by itself.
- The socket is in a folder of 0700 in `/tmp` and its path is known to the helper (it must be). What protects the broker is the fixed request set and the run table, not the path.
- The run table holds one row, for this run, with task `none`. A goal run does not give the broker its task id yet.
- A broker that dies during a run makes every later hook call No. The run ends with exit 2 and a line that says so; the cause word `broker_lost` and the stop of the goal task are not built.
- The `umwayi agent check` output does not show the broker.
- The hook of the broker path does not add the tool_use_id to the check entry unless the C2 change (PR 183) is in.
