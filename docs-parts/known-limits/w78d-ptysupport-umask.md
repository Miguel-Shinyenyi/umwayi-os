section: Enforced by default (W78d), found while fixing the umask of the terminal test helper
title: the terminal test helper passes the umask only where Popen does, and only to the child it starts
number: 327

- `tests/ptysupport.py` now gives `umask` to the child on both paths. The umask is the one `subprocess.Popen` sets in the child after the fork. It does not change the umask of the test process, and a grandchild that sets its own umask is not affected.
- `subprocess.Popen(umask=...)` needs Python 3.9 or later. The CI runs 3.10 and 3.13.
- The test shows the mode of a file made by a `python3 -c` child. It does not run `umwayi` on a terminal with a umask, so a mode of a file written by umwayi itself on that path is not checked here.
