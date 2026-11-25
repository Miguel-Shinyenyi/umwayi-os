# OpenCode as a goal helper (W9.13, design note)

## Purpose

This is the design note of task W9.13: OpenCode as a builder, tester or guide of a goal, through a non-interactive ACP run. Today a goal uses Claude Code and Kiro only (W9-Q8, W9.R23), because `umwayi agent run` refuses an OpenCode agent and only the chat start of task 10.48 exists. **Built 2026-11-22** (the pull request of W9.13), on the owner's accepted recommendations below; the owner's stops 6 and 7 stay open. When this note was written it was docs only. The owner decides the stops at the end before any code is written.

umwayi-os runs by itself with its own supervisor. Nothing in this design needs an outside guide, a person watching the run or a network service of umwayi. The only person is the owner at a real terminal, and only for the stops listed at the end.

## Current state

What exists, with the code that shows it:

- **The refusal (until W9.13).** `_opencode_chat_only` in `umwayi/agents.py` gave exit 64 for `agent run` and `agent login` of an OpenCode agent. Since W9.13 it refuses `agent login` only; `agent run` takes an OpenCode agent through `_opencode_run_options` (an effort is 64, a model must be the agent's own).
- **The chat start (10.48, built).** `umwayi agent chat NAME` for `platform: opencode` starts `opencode acp` with the allow-listed environment (`opencode_env`) and the inline config (`opencode_inline_config`, the umwayi plugin from `adapters/opencode/plugin/` as the first gate), waits for the plugin's canary through `gate_ready`, compares the model of the `session/new` answer with the agent's `model` as text, and answers `auth_required`. The six gate checks of 10.R13.8 (`_opencode_checks`) run before every chat and in `agent check`. umwayi offers no `fs` and no `terminal` capability, so OpenCode cannot ask umwayi to read, write or run anything (`adapters/NOTES-layer10.md`).
- **The goal runs.** `umwayi/goalrun.py` starts every role through `agent run` with a prompt (`builder_prompt`, `tester_prompt`, `planning_prompt`, `check_prompt`) and reads one tagged last line (`UMWAYI-PLAN`, `UMWAYI-RESULT`, `UMWAYI-CHECK`) within `TAG_LIMITS`. `PLATFORM_OPTIONS = ("claude-code", "kiro")` lists the platforms that take a model and an effort.
- **The budget.** `docs/budget-governor.md`: a reading is `measured` (Claude Code's own report), `declared` (rates in `units.yaml`) or `unknown` (counts at `unknown_worst_case`, never zero). Kiro sends umwayi nothing, so a Kiro run is what `units.yaml` declares.
- **The real install.** 10.42 confirmed the ACP facts on OpenCode 2.2.7. The real check of 10.51 was run and recorded on 2026-11-22 on OpenCode 2.3.0 (`adapters/NOTES-layer10.md`, PR 164); the owner ticks 10.51. The build is tested with a fake `opencode acp` and that check; no real goal has run with an OpenCode role.
- **Enforcement.** `docs/enforced-default-design.md` (W78): OpenCode has no platform sandbox like B1, so in `enforced` mode it needs B2 or the owner's per agent `cooperative` switch. Step 1A of W78 records the mode but gates no start yet.

## The six W9.13 questions

The repo names W9.13 and its condition (W9-Q8: task 10.48 and a non-interactive ACP run first) but does not list its questions. These six are the decisions the build cannot make by itself. Each answer is written so that it does not block other work: it changes nothing for Claude Code and Kiro, and it does not wait for W78, W48 or W62.

1. **Which way does umwayi run OpenCode without a terminal: `opencode acp` or `opencode run`?**
   **Recommendation:** `opencode acp`, through the chat start of 10.48 with the owner's terminal taken out: the same environment, inline config, plugin, canary, model compare and gate checks, and one prompt in place of the chat loop. `opencode run` is not used: its hook path, output shape and exit codes are not confirmed, and it would be a second start path with its own checks. *Does not block:* the Claude Code and Kiro paths of `agent run` are untouched; a later `opencode run` path, if the owner wants it, is its own task.

2. **What is one run?**
   **Recommendation:** `initialize`, `session/new` (the model compared), the canary seen, one `session/prompt` with the role's prompt, then the end at the first `stopReason`, then the process is stopped as the chat is stopped today (the 7b stop). The agent's `timeout_minutes`, the kill switch and the budget stop it the same way as an `agent run` of Kiro. No second prompt, no follow-up, no retry. *Does not block:* the chat keeps its loop; `agent run` for OpenCode is a new mode of the same `_Run`, not a change of the chat.

3. **Who answers a permission request when nobody is at the terminal?**
   **Recommendation:** the gate only, as in the chat: every `session/request_permission` is checked by the rules (`umwayi check`). Yes allows the one call. No rejects it. Ask me first rejects it and the run goes on, and in a goal the task moves to `needs owner` with the blocked line of W56 when the run ends. There is no approval during the run, and an option that allows "always" is never chosen. *Does not block:* the rules file and the starter rules are not changed; the owner adds Yes rules for an OpenCode builder by hand, the same as for Kiro.

4. **Where does the tagged last line come from?**
   **Recommendation:** from the `agent_message_chunk` text of the one session, joined in order, with terminal control and bidirectional characters removed as the chat does, cut at the role's `TAG_LIMITS`, and the last non-empty line parsed by the existing `parse_*` functions. Tool output and thought chunks never count. No tag, a second tag or a tag over the limit is the same failure word as for Kiro today. *Does not block:* the parsers and the tags do not change.

5. **Model and effort.**
   **Recommendation:** the model is the agent's `provider/model` from `agents.yaml`. An approval or a `--model` that differs from it is refused (64), because the inline config is built from the agent and the model compare checks the agent's model. An effort is refused (64) for OpenCode until a flag is confirmed on a real install (W9-Q8), and `PLATFORM_OPTIONS` stays without OpenCode until then. *Does not block:* W48 model routing may list OpenCode once W9.13 is built; until then its rule "no OpenCode role" stays (`docs/model-routing-design.md`).

6. **Which roles, and in what order?**
   **Recommendation:** the same code serves all three roles, and the owner turns each on by a Yes rule for `goal_start` that names the agent and the role (`goal.rules.example.yaml` shows the shape; nothing is Yes by default). Recommended order of use, not of build: tester and guide first (they write no file), builder after five clean tester runs. The weak independence warning of W9 still applies when two roles use the same provider and model. *Does not block:* no role, rule or check of Claude Code and Kiro changes.

## Exit codes

Only 0, 2, 3 and 64, never 1, the same as `umwayi agent` today:

| code | what it means for an OpenCode run |
| --- | --- |
| 0 | The run reached its `stopReason` and was stopped cleanly. The goal supervisor then reads the tagged line; a missing or bad tag is a task failure word, not an exit code of the run. |
| 2 | No, or the run could not be trusted: a rule said No to `agent_run`, a gate check failed (not gated), the canary was not seen in time, the model in `session/new` differs, `auth_required`, the logbook could not record the start, the budget stopped the run, the timeout passed, the process crashed, or an unexpected error. |
| 3 | Ask me first: the kill switch is on or unreadable, a rule said Ask me first to `agent_run`, the budget needs the owner's word, or `rules.yaml` is missing or broken. Nothing was started. |
| 64 | Usage or config: a bad `agents.yaml`, an effort given for OpenCode, a model that is not the agent's, a role or option the platform does not take. Nothing was started and nothing was written. |

## Budget bands

OpenCode spend is **declared or unknown, never measured.** umwayi reads no usage report from OpenCode, so it never tags an OpenCode reading `measured`.

- **The band:** 5 to 40 UU per run. This is the owner's best guess, not a measurement.
- **The declared rate:** about 150000 micros per run (15 UU), the same as the owner's figure for Kiro, written in `units.yaml` as a `run_micros` rate with `source: owner` and a comment saying it is a best guess to replace after the first 10 real runs:

  ```yaml
  platforms:
    opencode:
      reading: runs
      run_micros:             # source: owner, best guess; replace after the first 10 real runs
        value: 150000
        date: 2026-11-17
        source: owner
  ```

- **The cap of one role run** is the top of the band, 40 UU, unless the owner approves less. The reserve is the cap, as for every run.
- **Without the rate** the reading is `unknown` and counts at `unknown_worst_case`, never zero.
- **After 10 real runs** the owner compares the band with what the provider's own bill says and changes the rate by hand. `budget calibrate` needs measured runs, so it never proposes an OpenCode rate.


### Per role, as planning guesses (2026-11-25, G-0068)

The guide's best guess of 2026-11-17, now named here: a reviewer run about **5 UU**, a tester run about **8 UU**, a builder run about **25 UU**. They are labelled guesses,
not measurements. They sit inside the band above, so the cap of one run stays 40 UU and the declared rate stays 15 UU. No code reads the three numbers: they are for the
estimate a person reads before approving a goal. After 10 real runs the owner replaces them with what the provider's own bill shows.

## The rules and their planted faults

Each rule gets a test and a planted fault the test must catch. Real child processes, a fake `opencode` that speaks ACP, a temporary root, no network, standard library only.

| # | rule | planted fault the test must catch |
| --- | --- | --- |
| R1 | `agent run` of an OpenCode agent starts `opencode acp`, never `opencode run` and never a shell | the argument list built with `run`; a shell string |
| R2 | it uses the 10.48 start unchanged: allow-listed environment, inline config, the plugin as first gate, the six gate checks | a gate check skipped for `agent run`; the owner's environment passed whole |
| R3 | no prompt is sent before the canary is seen; no canary in time is exit 2 | the prompt sent first; a missing canary read as seen |
| R4 | the model of `session/new` must equal the agent's model; another one is exit 2 | the compare skipped; a compare with case folding |
| R5 | exactly one `session/prompt`, ended at the first `stopReason`, then the process is stopped | a second prompt; the process left running |
| R6 | every permission request goes through the rules; Ask me first and No are rejected; "always" is never chosen | an Ask me first allowed; an "always" option chosen |
| R7 | umwayi offers no `fs` and no `terminal` capability | a capability advertised |
| R8 | the tagged line comes only from the session's message text, cut at the role's limit | a tag taken from tool output; the limit not applied |
| R9 | an effort for OpenCode is exit 64, and so is a model that is not the agent's | an effort passed through; a model from the approval used |
| R10 | the reading is `declared` or `unknown`, never `measured`; unknown counts at the worst case | an OpenCode reading tagged measured; unknown counted as zero |
| R11 | the timeout, the kill switch and the budget stop an OpenCode run as they stop Kiro | the kill switch not watched during the run |
| R12 | the exit codes are 0, 2, 3 and 64 only | a 1 for a refusal |
| R13 | the start entry names the platform, the transport and the mode (W78.R3) | the start entry without the mode |
| R14 | no OpenCode role starts without a Yes rule that names the agent and the role | a goal that starts OpenCode with no rule |

## What the owner's real check must confirm before the build

Task 10.51, on the owner's Mac, is the real check. The build does not start until it is recorded in `adapters/NOTES-layer10.md`:

1. **The version:** OpenCode 2.2.3 or newer, the real `opencode --version` output.
2. **One non-interactive run** through `opencode acp` with the umwayi plugin: one prompt, one `stopReason`, the process stopped.
3. **The exit code** of `opencode acp` when it is stopped after the `stopReason`, and when it ends by itself.
4. **The output shape:** that the reply comes as `agent_message_chunk` text, in what order, and whether a tool's output can appear in it.
5. **Whether it needs a terminal:** the run with standard input, output and error not on a terminal, and whether OpenCode prints to stderr or asks anything.
6. **The plugin and the canary** in that run: the canary seen, one hook entry per tool call.
7. **What it writes** in its private `HOME`, and whether anything reaches the owner's real config.
8. **An effort flag:** whether a documented effort or reasoning option exists on that version. If none is confirmed, R9 stays.

## Free routes and a private repository (2026-11-25, G-0068 and G-0076)

The rule of the owner's acceptance (D-93) is that work sent over a free route may be used by the provider, so a free route takes PUBLIC work only. For OpenCode today:

- **Covered:** the signed-out free tier, the provider `opencode` of `agents.yaml` (`OPENCODE_ROUTES`). Its terms are not read here: treat it as a free route.
- **Not covered:** a local provider (`ollama`, `lmstudio`, `vllm`): its content goes to the owner's own machine. A connected-account subscription sign-in is not offered today.
- **The fixed refusal, proposed:** `private_repo_named`, the same word as the Muse route (`docs/muse-route-design.md`), exit 2, raised at `agent run` for a covered route when the root is not
  marked public. The line says the next step ("only a root the owner marked public may go over a free route") and nothing is started. A local provider is never refused for this.
- **The mark:** the owner writes `public: true` by hand and the code reads it and never writes it (G-0046 for Muse). It is never inferred from a repository name or a remote.
- **Tests to write first:** a free route with no mark is refused and starts nothing; the same with the mark runs; a local provider with no mark runs; a mark that is `"true"` as text or `1` is no mark.
- **Built (G-0076, 2026-11-25).** `agent run` of an OpenCode agent on the free tier is refused with `private_repo_named` (exit 2, before the budget reservation, nothing started) unless `units.yaml` has the top level key `public: true`, written by the owner. It covers `agent run` and `agent chat` alike: both go through the budget step where the check sits. Not covered: Muse (its own refusal is Muse step 3). The repository's own `units.yaml` is not marked.

## What it does not prove

- It does not measure OpenCode's spend. The band is a guess until the owner compares it with a bill.
- It does not confine OpenCode. Without W78 B2, a program an allowed command starts can do what the owner's user can do.
- It does not prove a model obeyed the prompt. The tester and the guide's check judge the result; the tags only carry it.
- It does not cover a provider that changes the model behind the same name.
- It says nothing about OpenCode versions the owner's check did not run.

## Stops for the owner

This would be the first code that lets OpenCode start as a goal helper, so each of these is the owner's word before the build:

1. Approve the six recommendations above, or change them.
2. Record the real check of 10.51 on the Mac (the eight points above).
3. Approve the budget band and the declared rate, labelled as a best guess.
4. Approve that an effort stays refused for OpenCode unless point 8 confirms a flag.
5. Decide how OpenCode runs while W78 is not built: as now (cooperative, the gate and the plugin only), or not as a builder until B2 exists. Recommendation: tester and guide now, builder after B2 or after five clean tester runs.
6. Add, by hand, the Yes rules for the OpenCode roles you want. umwayi adds none.
7. Review the first real goal run with an OpenCode role before a second one starts.

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-17 | Design note only; the six questions, the budget band and the stops wait for the owner. | W9.13 in tasks.md, after 10.48 (W9-Q8). |
| 2026-11-22 | The owner accepted the recommendations of the six questions, the open questions below, the budget band, an effort refused for OpenCode, and tester and guide first, then a builder after five clean tester runs. W9.13 is built: `agent run` of an OpenCode agent (`acp.Run`, `agents.py` `_acp_run`), `goal approve` and `goal show` for an OpenCode role, a blank effort in a packet, the planted-fault tests, one whole-system scenario with a fake `opencode acp`. Not built: a rule that enforces "five clean runs"; that is advice. The owner still adds the Yes rules by hand (stop 6) and reviews the first real goal run (stop 7). | The owner's message of the same day, after the real check of 10.51 (PR 164). |
| 2026-11-25 | W9.13 is already built (2026-11-22), so the guide's list of 2026-11-25 (a design note, then a build) is met except two things, written here as design: the per role planning guesses and the fixed refusal of a private repository on a free route. The tick of W9.13 in `tasks.md` was stale and is now ticked. | G-0068 asked for a note and a build; the note and the build exist. |
| 2026-11-25 | The refusal is built (G-0076): the mark is one top level `public: true` in `units.yaml` (the recommendation of open question 4), and a free route is the provider `opencode` (open question 5). The owner's merge word confirms both. | G-0076: OpenCode on free models must not touch a private repository. |

## Open questions

1. **Is "the owner's figure for Kiro" 150000 micros?** `docs/budget-governor.md` shows 400000 micros for Kiro as an example. **Recommendation:** use 150000 for OpenCode as the owner said, and leave the Kiro example as it is.
2. **Five clean tester runs before a builder:** is five the right number? **Recommendation:** five, counted from the logbook, and the owner can lower it by saying so.
3. **A provider that is free:** a free tier still counts at the declared rate. **Recommendation:** keep the declared rate, so the day limits still hold, and let the owner set a lower `run_micros` with `source: owner` if wanted.
4. **Where is the `public: true` mark kept for a root?** G-0046 puts it on the `muse` provider in `units.yaml`; the OpenCode free tier is not a `units.yaml` provider. **Recommendation:** one mark per root, a top level `public: true` in `units.yaml`, read by both routes, written only by the owner.
5. **Is the signed-out OpenCode free tier a free route under D-93?** Its terms are not read in this repository. **Recommendation:** yes, treat it as one, until the owner reads its terms and says otherwise.
