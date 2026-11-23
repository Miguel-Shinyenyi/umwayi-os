section: Scope during a run (W9.16), found while building it
title: the scope overlay stops a file-writing tool call outside the packet, and nothing else
number: 341

These are facts of the code of this change. No real Claude Code ran with it.

- Only the file-writing tools of Claude Code are checked (Write, Edit, MultiEdit, NotebookEdit). A `Bash` command that writes a file (`sed -i`, `>`, `tee`, `git checkout`) is not read. The scope check after the run still finds it and fails the task.
- Paths are compared as written, made absolute against the call's `cwd` and normalised. A link in the worktree that points outside is not followed here, so a write through it is not caught.
- Only Claude Code has it. Kiro's hook is a file the owner makes, and OpenCode's plugin is not given a scope file; `--scope-file` for them is refused (64) and the supervisor does not pass it. Their runs still get the scope check after the run.
- The scope file is written by the supervisor next to the goal's records (`.umwayi/goals/G-NNNN/scope-TASK-ROLE.json`). A helper that can write the scope file (it sits next to the goal's records) or the run table of the broker can widen its scope until confinement is on.
- A tester, a guide's check and a planning run have an empty scope, so every file write of theirs is No. A tester that is told to write a file in its prompt is stopped.
- A scope file that cannot be written ends the task before the run (`agent_cannot_be_gated`). A scope file that cannot be read by the hook makes every file write No.
- A run under a mode file that says `enforced` asks the broker, and the broker checks the scope file named in its run table row as `umwayi check --scope` does (W9.16 with step 5). It is a check, not an enforcement: A helper that can write the scope file (it sits next to the goal's records) or the run table of the broker can widen its scope until confinement is on.
