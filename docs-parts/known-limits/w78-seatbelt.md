section: Enforced by default (W78), found while building Seatbelt (step 7)
title: Seatbelt is built and measured with a Python child on one Mac, and no helper is started through it
number: 342

These are facts of the code of this change.

- `umwayi/seatbelt.py` makes a Seatbelt profile and runs a command through `/usr/bin/sandbox-exec`. `CHECKED_ON_MAC` is False and `agents.py` does not use it: an enforced run with `confine: true` on a Mac is refused with reason `platform`. A later pull request wires it after the owner's check.
- Measured on one Mac (macOS 27.0.1, Homebrew Python 3.13): a Python child under the profile writes inside its work folder, is refused writing elsewhere and reading an unlisted file, and with `no_network` is refused a connection. A Python child needed the folders above every listed path to be readable by name (the profile lists them as `literal`), or it did not start. Claude Code 2.1.330 also ran `--version` under it, with its own install folders listed for reading. Not measured: a Claude Code session (its API calls, `node` helpers, its sign-in in the Keychain), any Kiro or OpenCode helper, other macOS versions.
- `sandbox-exec` is marked deprecated by Apple and its profile language is not documented by Apple. A macOS update can change it.
- The profile allows `mach-lookup` and `sysctl-read` without limit. Reading the names of the folders above a listed path is allowed.
- CI has no macOS, so the real-command tests are skipped there.

What the owner checks on the Mac, step by step (nothing here needs a password, a key or a sign-in):
1. `git pull`, then in the umwayi-os folder run `python3 -m umwayi.seatbelt selftest`. Expected: `write_inside: ok`, `write_outside: refused`, `read_unlisted: refused`, and `network: refused` in the `no_network` block (in the `with_network` block it is `error 61` or `ok`, not `refused`). Send the output.
2. Run `python3 -m unittest tests.test_seatbelt -v`. Expected: all pass, including `RealMacTests`.
3. To try Claude Code (not done by this change): make a scratch folder with a throwaway git repo, `cd` into it, and run
   `python3 /PATH/TO/umwayi-os/umwayi/seatbelt.py run --read /usr --read /bin --read /System --read /Library --read /private/etc --read /dev --read /opt --read "$HOME/.claude" --write "$PWD" -- "$(which claude)" --version`.
   Expected: it prints a version. It may fail (the Keychain, `node` paths): write down the message. Do not paste anything that holds a token.
4. If 1 and 2 pass and you want it wired, say so: a pull request sets `CHECKED_ON_MAC = True` and starts an enforced `confine: true` Claude Code run through `sandbox-exec` on macOS, with the allow list measured from step 3.
