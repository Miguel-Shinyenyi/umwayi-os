section: OpenCode as a goal helper (W9.13), found while building it
title: an OpenCode role was tested against a fake only, its spend must be declared, and nothing confines it
number: 330

- No goal was run with a real OpenCode in a role. The run of `agent run` and the goal scenarios use the fake `opencode acp` of `tests/agents/fake_opencode.py`. The real check of 10.51 (OpenCode 2.3.0, 2026-11-22, `adapters/NOTES-layer10.md`) shows `opencode acp` over pipes, one prompt, one `stopReason` and exit 0 when standard input closes; it was not run through `agent run`. The first real goal run with an OpenCode role is the owner's stop 7.
- A run is never measured. With no `run_micros` for `opencode` in `units.yaml` it settles as `unknown` and counts at `limits.unknown_worst_case` (100 UU by default), which is more than most task budgets: the budget then stops the task. Declare a rate first (the note proposes 150000 micros, 15 UU, labelled a best guess).
- Ask me first is rejected in a run, not queued as a question: nobody is at the terminal. A task whose OpenCode role was blocked ends at the supervisor's own checks (no tag, or the tester's verdict), not at a prompt.
- The supervisor's own rules decide what a tag is (the nonce of the prompt, one tag, the role's limit), and an OpenCode role is read like a Kiro one: no tag, a second tag or a tag over the limit is the same failure word. A reply that quotes a tag line of its own is read by the same rules.
- Descendants are tracked through `/proc` once a second, as in the chat (limit 324): where `/proc` is missing (macOS) only the agent itself is stopped.
- Nothing confines the helper (W78 B2 is not built). A program an allowed command starts can do what the owner's user can do. "Tester and guide first, a builder after five clean tester runs" is advice; no rule or check enforces it.
- `agent check` of an OpenCode agent still says "chat" in its last lines; the checks are the ones a run uses.
- `PLATFORM_OPTIONS` (the platforms that take a model and an effort from `goal approve`) is unchanged. A model for an OpenCode role comes from `agents.yaml`; an effort is refused until a documented flag is confirmed on a real install (it was not, on 2.3.0).
