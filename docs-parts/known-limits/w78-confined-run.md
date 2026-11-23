section: Enforced by default (W78), found while starting a run through Landlock (step 5b2)
title: a confined run needs `confine: true`, and the allow list for a real Claude Code is a guess
number: 339

These are facts of the code of this change. No real Claude Code ran confined.

- Confinement is off unless the agent has `confine: true` in `agents.yaml` and its run is `enforced`. Today's enforced runs do not change.
- The allow list is: read and execute below `/usr /lib /lib64 /bin /sbin /etc /opt /proc /dev /sys`, the folders of the command and of Python, `sys.prefix`, and the umwayi source; write below the work folder, a private temporary folder and the helper's own config (`~/.claude`, `~/.claude.json`, `CLAUDE_CONFIG_DIR`). A real Claude Code may need more (a Node install under the home folder, a cache folder, a keychain helper). When it does, it fails when it first needs the path, not at the start. The measured list for a real run is for the owner to take.
- Claude Code gets no network rule: it needs its API, so a confined run can still reach the network. The broker's Unix socket needs no right on this kernel (checked in CI, ABI 8); an older kernel was not checked.
- A work folder that holds the umwayi root, or is the root, is refused (`profile`): Landlock can not take a path out of a listed tree. A plain `agent run` in the root is therefore refused when `confine: true`. Goal runs use worktrees outside the root.
- The helper's temporary files go to its own folder (`TMPDIR`). A program that ignores `TMPDIR` and writes to `/tmp` is refused by the kernel.
- Where Landlock is missing (macOS) an enforced run with `confine: true` is refused, never run unconfined. macOS (Seatbelt) is step 7.
- Only `claude -p` runs. Chats, ACP, Kiro and OpenCode are not started through it.
- The wrapper stays as the parent of the helper. A signal to the run reaches the wrapper and is passed on.
