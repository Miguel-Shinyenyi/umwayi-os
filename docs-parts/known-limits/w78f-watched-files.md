section: Enforced by default (W78), found while building step 3
title: the watched files are read twice, so a change made and undone, and a change by another process, are not told apart
number: 331

- The files are read before the helper starts and after it ends. A change that is made and undone inside the run is not seen. Nothing stops the change as it happens, and nothing undoes it afterwards: it is seen at the end, and the task stops there.
- The finding does not say who changed the file. The owner, a script or another goal can change a watched file while a helper runs, and the finding is the same. That is the stricter way: the owner decides.
- Only the files of the list are read: the mode file, `guidance.yaml`, `units.yaml`, `agents.yaml`, `rules.yaml`, `autonomy.yaml`, `.kiro/steering/umwayi` and the `tools/` folder. The hook files of Kiro and the Claude Code settings files, `umwayi.json`, `.git/config` and `.git/hooks/` of W41 C1 are not on it. The list is fixed in `umwayi/watched.py`.
- A folder is read as a whole (every file by name and content, links not followed). More than 2000 files, or a file over 32 MiB, are not read in full: a change in the part that is not read is not seen, and a file that cannot be read counts as changed when it was readable before.
- A planning run that changes a file has its plan refused (`guard`), and the plan worktree is removed when it is clean, as for any refused plan.
- A watched file changed by the helper inside its own worktree (a copy of the repository) is not the file of the root and is not seen here; the scope check of the task refuses a protected path in the worktree.
- C2 (a tool call that no hook checked) is not built, and `umwayi enforce check` still reports `detect-after` as refused.
