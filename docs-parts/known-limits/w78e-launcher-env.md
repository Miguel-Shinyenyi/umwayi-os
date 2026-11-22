section: Enforced by default (W78), found while building step 2
title: the allow list is a guess for Claude Code and Kiro, and an allow list cannot cover what a helper needs that nobody listed
number: 328

- The allow list is the one of the ACP chat plus `TERM` and `COLORTERM`. It was not checked against a real Claude Code or Kiro run (Kiro was out of this round; a real Claude Code run needs a sign-in). A helper or a tool it runs that needs another variable (a toolchain, a proxy name, `GH_HOST`) fails until the owner lists it in `env_keep`. Each case found in a real run belongs in `adapters/NOTES-layer10.md`.
- The default mode is `enforced`, so this changes every start of a Claude Code or Kiro agent that has no `cooperative` setting. A `cooperative` agent keeps today's deny lists. A goal set to `cooperative` does not relax an agent's start: `agent run` does not know the goal, so only the agent's own mode counts. That is the stricter way.
- `env_keep` passes the value the owner's shell holds when the start happens. It does not read any file and never logs a value. A name that is listed and not set passes nothing.
- The allow list stops secrets in the owner's environment. It does not stop secrets on disk (`~/.aws`, `~/.ssh`), network use, a hook that does not run, or an agent the owner starts by hand.
- `UMWAYI_RUN` is made by umwayi from the run id of the budget entry. A hook that reads it is not built; nothing yet uses it, so it only lets a later step tie a call to a start. A helper can read and copy it, so it is not a secret and not a proof.
- The test harness passes `FAKE_*` and `UMWAYI_TEST_*` names through the allow list in its children (`tests/adapters/support.py`, `PASS_FAKE_ENV`). Only `tests/agents/test_launch_env.py` runs with the plain allow list, so the other tests do not show it.
