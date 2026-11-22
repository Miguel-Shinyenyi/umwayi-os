date: 2026-11-22
pr: none
what: W78 build step 2 (W41 A). An agent in `enforced` mode gets an allow list instead of the owner's whole environment minus a deny list: the list of the ACP chat plus `TERM` and `COLORTERM`, plus the names in the agent's new `env_keep` (plain names, never values, at most 32; credentials, the SSH agent, telemetry names and `UMWAYI_` names are refused). Every `agent run` and chat gets `UMWAYI_RUN=<run id>`. A `cooperative` agent keeps the W64 deny lists and gets the marker. `enforce.mode_of` reads the mode and treats a missing, expired or unreadable file as enforced. `agent check` uses the same list as the start. Safety change: stops for the owner. Not checked against a real Claude Code or Kiro run.
tests: see the pull request
