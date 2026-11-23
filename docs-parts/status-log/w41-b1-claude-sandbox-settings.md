date: 2026-11-23
pr: none
what: W78 build step 4 (W41 B1). A Claude Code start under a mode file that says `enforced` passes the fixed sandbox block (`enabled`, `failIfUnavailable`, `allowUnsandboxedCommands: false`) and is refused with a fixed reason (`profile`, `platform`, `dependency`) when the block is missing, the platform cannot host it, or `bwrap` or `socat` is missing on Linux. `agent check` and the start share one gate check. A cooperative agent and no mode file keep today's start. An enforced ACP agent is refused. It reads settings and looks for tools; it does not show the sandbox holds. Stops for the owner.
tests: `tests/agents/test_sandbox_settings.py` (fake claude, fake bwrap and socat, no real Claude Code, no real sandbox).
