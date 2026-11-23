section: Enforced by default (W78), found while building the Landlock confinement (step 5b)
title: the Landlock program exists and is tested on its own, but no helper is started through it
number: 335

These are facts of the code of this change.

- `umwayi agent run` does not use `umwayi/confine.py`. Nothing is confined by it yet, and no real Claude Code, Kiro or OpenCode was run through it. The allow list a real helper needs (its interpreter and libraries, its config and cache folders, `/proc`, the broker socket) is not written.
- A path that is not listed is refused, reads included. A start with a list that misses something fails when the helper first needs it, not at the start.
- Network: only TCP bind and connect are handled, and only on ABI 4 or later (kernel 6.7). UDP, raw sockets and abstract or path Unix sockets are not restricted by what this module sets. A confined helper can still talk to the broker's Unix socket only if the folder is listed; whether the kernel's Landlock then lets a connect through is not checked here.
- Only filesystem rights and the two TCP rights the ABI knows are handled. A right a newer kernel adds is not handled and stays allowed.
- It restricts one process tree from its start. A process outside the tree (the owner's terminal, the supervisor, the broker) is not confined, and a helper cannot be confined after it started.
- `no_new_privs` is set, so a setuid program in the helper's tree does not gain privilege.
- Linux only. macOS has no Landlock; Seatbelt is step 7 and has not been checked on a Mac.
- The tests that run a real child need Landlock and skip with a fixed reason without it. The CI runner reported ABI 8 for the probe of PR 187; a skipped test shows nothing.
