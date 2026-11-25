# The first real enforced run: what it needs, and what it would prove (G-0049)

## Purpose

The owner asked (2026-11-25) not to wait for a date for the first real enforced run: dates only count when they speed work up. This note says,
for each machine, what a real run needs and what is already built, so that the next pull requests (macOS Seatbelt behind a refusal, then the
run itself) are small and each says what it proves. It is docs only. Nothing here runs anything. `REAL_ENFORCED_RUN_DONE` in `umwayi/enforce.py`
stays False until the owner sets it after a run.

## Current state

Checked on 2026-11-25 against the code on main and the notes named below.

**Built and merged:** the mode setting and `umwayi enforce check`; the Claude Code platform sandbox (B1, `--settings` with the fixed sandbox
block); the broker; tool calls that no hook checked (C2); the scrubbed environment and run marker (W41 A); the watched list; and a Landlock run:
a `claude -p` run of an agent with `confine: true`, under a mode file that says `enforced`, starts through `umwayi/confine.py`. Confinement is
off by default. The Seatbelt module `umwayi/seatbelt.py` is built and refused: `CHECKED_ON_MAC` is False and `agents.py` does not use it.

### On a Linux machine

- A kernel with Landlock. Any ABI confines files; the option that refuses TCP needs ABI 4 (kernel 6.7). The CI runner reports ABI 8.
- `bwrap` and `socat` for the Claude Code platform sandbox (B1); without them the start is refused, reason `dependency`.
- Claude Code installed and signed in by the owner (umwayi never reads a sign-in), the mode file `enforced`, and the agent set `confine: true`.
- This is the machine where the six bypass tests already run, in CI only. A run here would be the first real goal run, not the first kernel proof.

### On the owner's Mac

- No Landlock. A confined run is refused with reason `platform`, which is the right answer today.
- Two layers exist for a Mac: the Claude Code platform sandbox (B1 allows macOS and needs no extra program there), and Seatbelt for the
  confinement of the helper. Seatbelt needs the owner's check first: the steps are in [the Seatbelt check](seatbelt-check.md) (a self test, the
  module's tests including `RealMacTests`, and a version command run under the profile). `sandbox-exec` is deprecated by Apple and its profile
  language is not documented, so an update of macOS can change what the check shows.
- CI has no macOS. A pull request that wires Seatbelt can show only the tests that run on Linux; the Mac tests are skipped there, and a skip is
  not a pass. The owner's Mac check is the proof, and the pull request must say what the owner has to check.

### The network (limit 344)

A confined run has the network open. The option that refuses TCP refuses all of it, so a helper that must reach its model over HTTPS cannot use
it, and a port allow list (443 only) is not built; port 443 reaches any host. A real run proves nothing about the network until that changes.

### Which agents

- Claude Code: the only agent with a confined `claude -p` start today. First.
- OpenCode: the goal helper run exists (PR 174) but has no confined start. Second, after a design of its paths.
- Muse: after M2 part 2 (the start through `agents.py`). Third.
- Kiro: paused by the owner; its last run failed on the service, not on umwayi.

### Older gaps to close with the run (queue item 10)

- **W36**, the whole system test that failed on a Mac because it read `/proc`: `tests/whole_system_support.py` is fixed (it uses `ps` where
  there is no `/proc`). `tests/agents/support.py` is not: `wait_root_quiet` lists `/proc` with no fallback, so five agent tests error on a Mac
  (`FileNotFoundError: /proc`). A tests-only change fixes it; it is the next small pull request.
- **Kiro** failed on its own service (`ModelRegistryUnavailable`). Not umwayi's fault; paused.
- **G-0002**, the tiny goal that is in review and not merged: the step "a goal merged" has not been tried.

### What the first run would prove, and what it would not

It would show that one tiny goal ran on Claude Code with the confinement on, with a logbook of what happened, and that the run left the
folders it was allowed to write and nothing else. It would not prove: that the network is blocked (limit 344); that a push with a stored token
is refused (not tried); anything for OpenCode, Muse or Kiro; a long goal; or Seatbelt, if the run is on a Linux machine. Each pull request
that follows says which of these it covers.

## Decisions log

- 2026-11-25 (owner, 11:07, through the guide G-0050): build macOS Seatbelt behind a refusal that fails closed, not a Linux VM on the Mac.
- 2026-11-25 (this note): the order is this note, the tests-only `/proc` fix, Seatbelt behind a refusal (owner stop, with the Mac check named in
  the pull request), then the run on Claude Code, then OpenCode, then Muse after M2.

## Open questions

- **Q-r1.** May the first run be on a Linux machine if the owner has one, while Seatbelt waits for the Mac check? Recommendation: yes, a Linux
  run is the stronger proof of the kernel layer and does not wait for the Mac; the Mac run follows the owner's check.
- **Q-r2.** Should the first run say plainly that the network is open? Recommendation: yes, in the report and in the logbook of the run, as
  limit 344, with no claim about the network.
- **Q-r3.** Which tiny goal? Recommendation: a docs-only change to a scratch file in a throwaway repo, so a failure costs nothing.
