section: Enforced by default (W78), found while building W41 C2
title: unchecked tool calls are found after the run, from the platform's own report, and only for Claude Code
number: 333

These are facts of the code of this change. No real Claude Code ran with it; the tests use a fake `claude` that reports the events the Claude Code docs describe.

- It is applied only to a `claude -p` run under a mode file that says `enforced` (or cannot be read). A cooperative agent, a start with no mode file, a chat and Kiro and OpenCode are not checked.
- It finds a call after it ran. It does not stop it and does not show what it did.
- It depends on Claude Code sending the log events `tool_result` and `tool_decision` with `tool_use_id` and `tool_name`, and on the hook input carrying `tool_use_id`. The names were read from the Claude Code docs (part of those pages was a summary); a real run has not confirmed them. If the names are different, every run reads as "cannot tell" or finds nothing.
- Without a log report (no `api_request` event counted), or with a tool id that is not plain, the run says "cannot tell" and exits as it would have. A helper that turns off telemetry therefore hides its calls. Telemetry is set by umwayi's environment, but a managed setting of Claude Code can override it.
- `tool_result` is not emitted for a rejected call; a `tool_decision` event is. A call the hook denied has a check entry, so it is not a finding.
- A helper that never runs a hook and also never reports (both turned off) is not found. This is the same gap as with watched files: a process that does not ask is not checked.
- The cap is 20000 ids a run; a run with more reads as "cannot tell".
- Each unchecked call counts as one guard finding in the task's counts entry. A count of zero is not proof of obedience.
