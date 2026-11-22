date: 2026-11-22
pr: none
what: The default `timeout_minutes` of an agent is 60, not 30 (`DEFAULT_TIMEOUT_MINUTES` in `umwayi/agents.py`). `goal approve` refuses a builder whose timeout is under 1.5 times the largest task, so a 30 minute task needed 45 and an agent with no `timeout_minutes` was always refused; a real goal run hit it. The owner accepted the change. An agent that sets its own `timeout_minutes` is unchanged. A run that never ends is now stopped after 60 minutes, not 30, unless the agent sets less: the stall rule (30 minutes with no change) is separate and unchanged.
tests: see the pull request
