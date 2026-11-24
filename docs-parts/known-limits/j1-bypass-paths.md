section: Bypass paths (J1), found while writing the design note
title: A confined run has the network open, because the run path does not ask for no-tcp
number: 344

These are facts of the code of this change.

- `confine.argv` has a `no_tcp` option that makes the kernel refuse a TCP connect (Landlock ABI 4 or newer), and a kernel test shows it works in the wrapper. `umwayi/agents.py` builds the command of a confined enforced run with `confine.argv(read, write, argv)` and never passes it, so inside a run with `confine: true` a TCP connection is not refused: a command could reach the network without the broker, and a `git push` with a stored login is limited only by GitHub (no push to main, a required check) and by what the run is allowed to read.
- Even with the option, UDP and Unix sockets are not blocked by it, and the option needs a kernel with Landlock ABI 4 or newer.
- Confinement is off by default (`confine: false`) and no real enforced goal run has finished (W40). Read with the six paths of `docs/bypass-resistance-design.md`: three have a kernel test in the wrapper (write outside, read an unlisted file, a child inherits the limit); the network path has the option but not the wiring; a stored-token push and the credential read of a real run are not proven.
