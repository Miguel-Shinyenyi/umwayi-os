# The Seatbelt check on a Mac

## Purpose

This page is what the owner (or Claude Code, with the owner's permission) runs on a Mac to see whether the Seatbelt confinement of `umwayi/seatbelt.py` works there. Nothing here starts a helper through Seatbelt, reads a key or signs in. `sandbox-exec`, which does the confining, is marked deprecated by Apple and Apple does not document its profile language, so a macOS update can change what these steps show.

## Current state

`umwayi/seatbelt.py` is built and refused: `CHECKED_ON_MAC` is False and `agents.py` asks `start_allowed` first and builds a Seatbelt start only when it says yes (G-0050), so an enforced run with `confine: true` on a Mac is refused with reason `platform`. The self test and the `run` command are for this check. `run` refuses too while `CHECKED_ON_MAC` is False, unless you type `--i-am-testing` before the `--`; the refusal names the switch. Cooperative today, enforced where built: nothing here is enforced.

The steps, from a fresh checkout of main (`git pull` in the umwayi-os folder):
1. `python3 -m umwayi.seatbelt selftest`. Expect, in the `with_network` and `no_network` blocks: `write_inside: ok`, `write_outside: refused`, `read_unlisted: refused`; and `network: refused` in the `no_network` block (`error 61` or `ok` in the `with_network` block, which only says nobody listens on that port).
2. `python3 -m unittest tests.test_seatbelt -v`. Expect every test to pass, including `RealMacTests`.
3. In a scratch folder with a throwaway git repo (never your own repo), run the claude version command under the profile. Add the folder of the claude install to the read list (`python3 -c "import os,shutil;print(os.path.dirname(os.path.realpath(shutil.which('claude'))))"`):
   `python3 /PATH/TO/umwayi-os/umwayi/seatbelt.py run --read /usr --read /bin --read /System --read /Library --read /private/etc --read /dev --read /opt --read "$HOME/.claude" --read CLAUDE_INSTALL_FOLDER --write "$PWD" --i-am-testing -- "$(which claude)" --version`. Expect a version line. Do not start a Claude Code session, do not touch the Keychain, and do not paste any token, key or sign-in.

What to send back: the exact output lines of steps 1 and 2 (shorten any path that holds a user name), pass or fail for each expectation, the macOS version (`sw_vers -productVersion`), and whether step 3 needed any read path beyond the list above.

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-23 | `run` refuses while `CHECKED_ON_MAC` is False; `--i-am-testing` is the owner's typed switch | Fixes item F3a: a hand test must be a deliberate act, not the default. |
| 2026-11-25 | `agents.py` builds a Seatbelt start through `seatbelt.confined_argv`, and only when `start_allowed` says yes; the constant stays False | G-0050: Seatbelt behind a refusal that fails closed. What is left for the owner on the Mac is a real Claude Code session, not `--version`. |
| 2026-11-23 | One check on the owner's Mac (macOS 27.0.1, Python 3.13): steps 1 to 3 passed, step 3 needed the folder of the claude install in the read list | Item S1 of the fixes file, in the Round 6 feedback. |

## Open questions

1. When all three steps pass, set `CHECKED_ON_MAC = True` in a small pull request that also wires an enforced `confine: true` run through `sandbox-exec`? Recommendation: yes, but only after a Claude Code session under the profile has been tried by the owner; the steps above do not show it.
2. Does a real session need `mach-lookup` and the Keychain? Not checked. Recommendation: the owner tries one session in a scratch folder and sends back the first refusal line.
