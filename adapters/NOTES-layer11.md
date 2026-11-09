# Layer 11: what the Linux tools do (facts for the spec)

Read Nov 10 2026, from the official pages linked in each section, for the layer 11 spec (requirements.md and design.md, "Layer 11"). Nothing here was built or run by umwayi. Where a page does not say something the design needs, it is marked **not documented** or **not confirmed**, and the design does not rely on it.

What the build sandbox had, for the record (not the owner's machine): systemd 252 (`systemctl --user is-system-running` printed `offline`: no user manager in the sandbox), tmux 3.6a, bubblewrap 0.12.0, SQLite 3.40.0 in Python 3.10 to 3.13, no `crontab` and no `inotifywait`. `/proc/sys/fs/inotify/max_user_watches` was 524288.

## 1. Scheduled runs: systemd user timers

Sources: [systemd.timer(5)](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html), [systemd.service(5)](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html), [systemd.unit(5)](https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html), [systemd.time(7)](https://www.freedesktop.org/software/systemd/man/latest/systemd.time.html), [systemd.kill(5)](https://www.freedesktop.org/software/systemd/man/latest/systemd.kill.html), [systemd-run(1)](https://www.freedesktop.org/software/systemd/man/latest/systemd-run.html).

- **A timer needs a service.** Each `.timer` activates a unit, by default the `.service` with the same name. If that service is still running when the timer elapses again, it is not started a second time ([systemd.timer](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html)).
- **Calendar times.** `OnCalendar=` takes calendar events. The documented normal forms include `*-*-* 07:30:00` (every day), `Mon *-*-* 07:30:00` (every Monday) and `*-*-01 07:30:00` (the first of every month). `daily`, `weekly` and `monthly` are shorthands for midnight ([systemd.time](https://www.freedesktop.org/software/systemd/man/latest/systemd.time.html)). A time zone may be appended. `systemd-analyze calendar` checks an expression.
- **Missed runs.** `Persistent=true` stores the last trigger time on disk, and starts the service at once when the timer becomes active if a run was missed while it was inactive (for example the machine was off). Only for `OnCalendar=` timers. `systemctl clean --what=state` removes that file and should be used before a timer is uninstalled.
- **Accuracy.** `AccuracySec=` defaults to 1 minute: the timer fires at a host-specific moment within that window. `RandomizedDelaySec=` defaults to 0.
- **Suspend.** A calendar timer that elapsed while the system slept runs once after resume. `WakeSystem=` needs privileges and is generally only for the system manager.
- **Clock and DST.** The page warns that calendar timers can fire at unexpected times if the real-time clock is wrong. **Not documented on the pages read:** what a calendar timer does with a local time skipped or repeated by a daylight saving change (cron's behaviour is documented, see section 2).
- **A oneshot service.** `Type=oneshot`: the manager considers the unit up after the main process exits. Without `RemainAfterExit=` it goes from "activating" to "dead" ([systemd.service](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html)). `ExecStart=` may be given several times for oneshot; a failing command stops the rest and marks the unit failed.
- **A time limit.** `TimeoutStartSec=` "configures the time to wait for start-up". **Not confirmed:** its default for a oneshot service. The design sets it explicitly, so the default does not matter.
- **Stopping.** `KillMode=control-group` is the default: on stop, SIGTERM to every process left in the unit's control group, SIGKILL after `TimeoutStopSec=` ([systemd.kill](https://www.freedesktop.org/software/systemd/man/latest/systemd.kill.html)). So what a scheduled run starts is stopped with it.
- **Where user units live.** The user unit load path includes `$XDG_CONFIG_HOME/systemd/user`, or `$HOME/.config/systemd/user` when `XDG_CONFIG_HOME` is not set ("User configuration") ([systemd.unit, "Unit File Load Path"](https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html)). `systemd-analyze --user unit-paths` prints the real list.
- **Enabling.** The `[Install]` section is read only by `systemctl enable` and `disable`. `WantedBy=` makes `enable` create a symbolic link in the listed unit's `.wants/` directory, and `disable` removes it ([systemd.unit, "[Install] Section Options"](https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html)). For a user timer with `WantedBy=timers.target`, that is a link in `timers.target.wants/` under the same configuration folder. **Not confirmed** on the owner's machine: the exact link path; the design only reads it.
- **Drop-ins override a unit.** A folder `NAME.service.d/` with `.conf` files changes settings of `NAME.service`, `ExecStart=` included (after clearing it with an empty `ExecStart=`) ([systemd.unit, example 2](https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html)). So a unit file that umwayi wrote can be changed without touching that file.
- **Specifiers.** Unit files resolve `%` specifiers (`%h` the home folder, `%u` the user name and many more); `%%` is one percent sign ([systemd.unit, "Specifiers"](https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html)). The service manager also expands `$VAR` and `${VAR}` in command lines; `$$` is one dollar sign ([systemd-run, "Variable expansion"](https://www.freedesktop.org/software/systemd/man/latest/systemd-run.html)).
- **Not read in full:** the "Command lines" section of systemd.service(5) (quoting, escapes, prefixes such as `-` and `@`). The design avoids every special character instead of quoting.
- **Not a shell.** `ExecStart=` runs a program with arguments; shell syntax needs an explicit shell (systemd-run example 7 starts `bash -c` for that). **Not quoted from systemd.service in this read**; it follows from the systemd-run examples.
- **Logged in only, unless lingering.** The user manager (`user@.service`) starts at the first login and is stopped after the last session ends, unless lingering is enabled; then it starts at boot. Users can enable it for themselves with `loginctl enable-linger` ([systemd-run, example 5](https://www.freedesktop.org/software/systemd/man/latest/systemd-run.html)). The [loginctl page](https://www.freedesktop.org/software/systemd/man/latest/loginctl.html) could not be read in this session; the fact above is from systemd-run(1).
- **Exit status.** A service whose main process exits non-zero is "failed"; `SuccessExitStatus=` can list other codes as success ([systemd-run, example 8](https://www.freedesktop.org/software/systemd/man/latest/systemd-run.html)).
- **Sandboxing in user services is limited.** Settings that need file system namespacing (`ProtectSystem=`, `ProtectHome=`, `ReadOnlyPaths=` and others) are not available to the per-user manager on their own. They work only with `PrivateUsers=true`, which needs unprivileged user namespaces ([systemd.exec](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html)).
- **Not documented on the pages read:** the environment a user service gets from the user manager (which variables, which `PATH`). The design passes absolute paths and sets the one variable it needs (`PYTHONPATH`).

## 2. Scheduled runs: cron

Sources: [crontab(5)](https://man7.org/linux/man-pages/man5/crontab.5.html) and [crontab(1)](https://man7.org/linux/man-pages/man1/crontab.1.html), both from cronie. Debian and Ubuntu ship a different cron (Vixie cron with Debian patches); **not read**, so anything that differs there is not covered.

- Each user has one crontab; its commands run as that user. Every command line is run by `/bin/sh` (`SHELL` is set to `/bin/sh`), with `LOGNAME` and `HOME` from `/etc/passwd`; `HOME` and `SHELL` can be set in the table.
- Five time fields (minute, hour, day of month, month, day of week), then the command. cron looks at the table every minute.
- **Daylight saving:** times that do not exist on the change day never run; times that occur twice run twice.
- **Mail:** output is mailed to the owner unless `MAILTO=""`.
- **Who may use it:** `cron.allow` and `cron.deny` decide. With cronie, if neither file exists only the super user may use `crontab`; other cron implementations differ.
- `crontab FILE` or `crontab -` replaces the whole table; `-l` lists it, `-r` removes it, `-e` edits it. There is no command to add or remove a single line, so a tool that installs one line must read, change and write the whole table.
- **Not found in the passages read:** cron's handling of `%` in a command (in common cron versions it ends the command and starts stdin). The design refuses `%` anyway.

## 3. File watching: inotify

Sources: [inotify(7)](https://man7.org/linux/man-pages/man7/inotify.7.html), [systemd.path(5)](https://www.freedesktop.org/software/systemd/man/latest/systemd.path.html), [Python os module](https://docs.python.org/3/library/os.html).

- **No standard library binding.** The Python standard library has no inotify API (checked: no name with "notify" in `os` or `select` on Python 3.11). Using it from the core would mean `ctypes` calls into libc, or a third party package, or the `inotifywait` program.
- **Not recursive:** each subfolder needs its own watch, and new subfolders must be added as they appear.
- **Overflow:** when the queue passes `max_queued_events`, events are dropped and `IN_Q_OVERFLOW` is reported; the application must rebuild its view. Limits are in `/proc/sys/fs/inotify/` (`max_queued_events`, `max_user_instances`, `max_user_watches`).
- **No network file systems:** remote changes on NFS and similar are not reported; applications must fall back to polling. `/proc`, `/sys` and `/dev/pts` are not watchable. Changes through `mmap` are not reported.
- **Who did it is not known:** inotify does not say which user or process caused an event, so a watcher cannot tell its own writes (or an AI helper's writes) from anyone else's.
- **Races:** by the time an event is read, the file may already be renamed or deleted. Matching the two halves of a rename is "inherently racy". Identical events not yet read are merged, so events cannot be counted.
- **systemd path units** use inotify and have the same limits. When the service they start ends, the paths are checked again and the service may start at once; a start rate limit stops a busy loop by putting the path unit into a failed state. `PathChanged=` fires when a file opened for writing is closed; `DirectoryNotEmpty=` fires while a folder holds a file. Files whose names start with a dot are generally ignored ([systemd.path](https://www.freedesktop.org/software/systemd/man/latest/systemd.path.html)).

## 4. Queryable state: SQLite

Sources: [Python sqlite3](https://docs.python.org/3/library/sqlite3.html), [SQLite WAL](https://www.sqlite.org/wal.html), [SQLite over a network](https://www.sqlite.org/useovernet.html), [SQLite URI filenames](https://www.sqlite.org/uri.html).

- `sqlite3` is in the Python standard library, so the core may use it under its rules. The SQLite library version comes with the Python build (3.40.0 in the build sandbox for 3.10 to 3.13); it is not pinned by umwayi.
- `sqlite3.connect(..., timeout=5.0)`: a write waits up to the timeout for a lock, then raises `OperationalError`. `check_same_thread=True` by default. The default transaction handling (`autocommit=LEGACY_TRANSACTION_CONTROL`) is documented to change in a future Python release.
- **WAL mode** lets readers and one writer work at once, but all processes must be on the same machine: it does not work on a network file system. It adds `-wal` and `-shm` files next to the database.
- **Over a network file system**, the SQLite authors advise against sharing a database file at all: locking and sync may not behave as on a local disk.
- `file:PATH?mode=ro` opens read only; `immutable=1` skips locking and is wrong if the file can change.

## 5. Long chats: tmux

Source: [tmux(1)](https://man7.org/linux/man-pages/man1/tmux.1.html).

- `new-session -d -s NAME [shell-command [argument ...]]` starts a detached session. The man page calls the command a "shell command" and says `-c` runs commands "using the default shell". **Not documented:** whether several arguments are run without a shell. So a command umwayi passes through tmux may be parsed by a shell.
- **Environment:** when the server starts, tmux copies its environment into the global environment. A new window gets the global environment merged with the session environment, and `update-environment` copies chosen variables from the client. So a program in a tmux window gets the server's environment from when the server started, not umwayi's filtered one, unless umwayi starts its own server (`-L NAME` or `-S PATH`) with a clean environment.
- **The socket:** sockets live in `tmux-UID` under `TMUX_TMPDIR` or `/tmp`, a folder that must not be readable or writable by others. Any process of the same user can attach, run `send-keys` (type into a pane) and `capture-pane -p` (read what is on the screen and in its history).
- `remain-on-exit` keeps a pane after its program exits, and `pane-died` and `pane-exited` hooks run commands when it does. `new-pane -W` waits for its command and returns its exit status.
- tmux runs `#()` format commands with `/bin/sh`, and hooks can run commands; both come from the owner's tmux configuration (`~/.tmux.conf` or `$XDG_CONFIG_HOME/tmux/tmux.conf`), which umwayi does not control.

## 6. Sandboxing helpers: bubblewrap, and the alternatives

Sources: [bubblewrap README](https://github.com/containers/bubblewrap/blob/main/README.md), [bwrap(1) source](https://github.com/containers/bubblewrap/blob/main/bwrap.xml), [Claude Code: Configure the sandboxed Bash tool](https://code.claude.com/docs/en/sandboxing), [Ubuntu: Understanding AppArmor user namespace restriction](https://discourse.ubuntu.com/t/understanding-apparmor-user-namespace-restriction/58007), [Landlock](https://docs.kernel.org/userspace-api/landlock.html), [systemd.exec](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html).

- **What bubblewrap is.** An unprivileged tool that builds a sandbox from a new, empty mount namespace, using user namespaces. Its setuid mode was removed. The README says it is "not a complete, ready-made sandbox": the protection depends entirely on the arguments the caller passes.
- **Needed arguments:** `--new-session` (or a seccomp filter against `TIOCSTI`), or a program in the sandbox can type into the terminal outside it (CVE-2017-5226). Anything bound into the sandbox (for example a D-Bus socket) can be used to escape. `--die-with-parent` kills the sandbox when its parent dies. `--unshare-net` leaves only a loopback device. `--disable-userns` stops the sandbox from making more user namespaces.
- **Ubuntu restricts it by default.** Ubuntu's AppArmor restriction on unprivileged user namespaces (Ubuntu 23.10 and later) is a hardening measure. It stops `bwrap` unless a profile allows it. Claude Code's docs describe adding an AppArmor profile for `/usr/bin/bwrap` with `sudo`, or lifting the restriction with `sysctl`. So on a default Ubuntu 24.04 a bwrap sandbox needs an administrator step first.
- **Claude Code already uses bubblewrap.** On Linux, Claude Code's own Bash sandbox relies on `bubblewrap` and `socat` and is off by default. It wraps shell commands only: built-in file tools and **command hooks run outside it, with full access**, so the layer 9 hook is not inside Claude Code's sandbox. By default, when the sandbox cannot start, Claude Code runs commands unsandboxed unless `sandbox.failIfUnavailable` is true. **Not documented:** whether Claude Code's bwrap sandbox works when Claude Code itself already runs inside a bwrap sandbox (nested user namespaces).
- **Agents need the network.** Claude Code and Kiro reach their model over the network, so an agent sandbox cannot use `--unshare-net`. Only umwayi's own helpers, which use no network, could.
- **systemd user services** cannot use `ProtectHome=` and friends without `PrivateUsers=true` and unprivileged user namespaces (section 1), so on Ubuntu they hit the same restriction.
- **Landlock** is a kernel feature that lets any process restrict itself and its children (files, and TCP or UDP ports in newer ABIs), stackable with other access controls. Using it needs three system calls; Python has no standard library binding, so the core would need `ctypes`. Whether it is enabled depends on the kernel build.
- **Firejail** is a setuid tool; the bubblewrap authors argue against that design (README). Not considered further.

## What stays unknown (to check on the owner's machine before any build)

- The owner's distribution, its cron implementation and whether `cron.allow` lets the owner use `crontab`.
- Whether a systemd user manager runs on the owner's machine, and whether lingering is wanted.
- The exact enable-link path for a user timer, and `systemd-analyze --user verify` on the rendered files.
- What a calendar timer does at a daylight saving change on the owner's time zone.
- For a later sandbox: whether unprivileged user namespaces are allowed (`/proc/sys/kernel/apparmor_restrict_unprivileged_userns` on Ubuntu), and whether Claude Code and Kiro run inside bwrap with the network on.
