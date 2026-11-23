date: 2026-11-22
pr: 163
what: W78d, test helper only. `tests/ptysupport.py` `run_at_terminal` takes `umask` and passes it to the child as `subprocess.Popen` does, and `run` passes its `umask` on the terminal path too. Before, a command that ran on a terminal ignored the umask. New `tests/test_ptysupport.py`: a short `python3 -c` child on a terminal with umask 0o077 creates a file of mode 0o600. No change to umwayi/, rules, steering, autonomy, guidance, guard lists or workflows.
tests: see the pull request
