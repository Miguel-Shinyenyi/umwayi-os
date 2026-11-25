# Starting Muse through umwayi: the touch points and the order (M2 part 2)

## Purpose

`umwayi/muse.py` (M2 part 1) builds the command line and the checks as pure functions and starts nothing. This note settles how a Muse run is
started through `umwayi/agents.py`, which has about two dozen branches for the platforms it knows, so that the change is a few small pull requests and
not one large one. Docs only: nothing here is built. A real Muse run needs the owner's yes and waits for the real check (M3).

## Current state

Read from `umwayi/agents.py` on 2026-11-25. Every start of an agent goes through these places, and a platform is a branch in each:

- **`PLATFORMS`** (a table of name, the one word `command` may be, transports, the hook script, a minimum version). Muse has no row. The agents.yaml
  check refuses a platform that is not a row.
- **`build_argv`** is "the only place an agent's command line is made", and every list passes through **`_assert_allowed`**, which refuses a word in
  `FORBIDDEN_FLAGS` (today `--bare`, `--dangerously-skip-permissions` and others of Claude Code). `--yolo` and `--disable-sandbox` of Muse are not in it.
- **`check_agent`** runs the checks of an agent (command, version, login, hook script, hook self-test, and for Claude Code the sandbox settings) and
  `agent check` shows them. Muse has no checks. Part 1 of this route has `muse.check_hook_file`, `check_public` and `check_on_path`.
- **The environment**: an enforced start uses `enforced_env` (an allow list) and the other starts remove credential names (`claude_env`, `kiro_env`).
  `muse.child_env` removes the Muse and Meta key variables and returns only their names.
- **The budget**: for a platform other than Claude Code, umwayi reads no cost, so the cap is only the reservation and a worst case is booked (`agent
  run` refuses a cap under the worst case, as for Kiro).
- **`_start`** is the one place a process is made (`subprocess.Popen`), and `tests/agents/test_agents_gate.py` lists the process starts and the
  temporary folders of `agents.py`. A Muse run through `_start` adds no process start, which is the reason to use it.
- **Not known**: what Muse's hook receives and answers (the format of `.muse/hooks.json` is assumed, not confirmed), whether the stored sign-in can be
  checked with a command that makes no model call (`muse_not_signed_in` says "exit code only"), and how a run reports its cost. These are the
  facts M3 must find, with the owner's yes, so the first parts must not depend on them.

### The order of the pull requests

1. **A row and the checks, starting nothing.** A `muse` row in `PLATFORMS` (`command` `muse`, transport `cli`), the agents.yaml check, `agent check` for
   a Muse agent (command found, version, hook file present and calling the gate, the `public` mark, key variable names only), and `--yolo` and
   `--disable-sandbox` added to `FORBIDDEN_FLAGS`. `agent run` for Muse stays refused with a fixed reason until step 2. Owner stop (a guard list and
   `agents.py`).
2. **The start, tested with a fake `muse` script.** `build_argv` calls `muse.command`; the run goes through `_start`; the child environment is
   `muse.child_env`; the budget books the worst case; the fake prints JSONL and exits 0, 1, 2 or 130 and the run reports each. Owner stop (a start in
   `agents.py`).
3. **The gates before a run.** `provider_gate` (the acceptance), `stop_gate` (with the reading of `credits.yaml`), and the `public: true` key on the
   `muse` provider in `units.yaml`, written by the owner and read, never written, by the code (G-0046). Owner stop (the `units.yaml` format).
4. **The real check (M3)**, with the owner's yes: one tiny read-only `muse exec` in a scratch folder with `--max-model-steps 3`, the credits read
   before and after, recorded on video. It answers the "not known" items above.

Each step says in its pull request that the label stays cooperative, plus Muse's own sandbox, and that no real Muse was run until step 4.

## Decisions log

- 2026-11-25 (this note): four small steps in the order above; the start goes through `_start`, so no new process start and no new entry in the guard test
  of process starts.
- 2026-11-25 (G-0046, earlier): the `public: true` mark is a key on the `muse` provider in `units.yaml`, written by the owner.

- 2026-11-25 (step 2 built): a run is `muse exec` with the prompt as the LAST argument (Q-m1, as recommended), the step cap is the agent's `max_turns` (a Muse agent without one is not started, `step_cap_missing`), the child environment is the whole environment minus the Muse and Meta key variables (names only are logged), and a chat, a login, `--model` and `--effort` are refused. `--yolo` and `--disable-sandbox` stay out of `FORBIDDEN_FLAGS` for now: `muse.exec_argv` never builds them and nine tests loop over that tuple.

## Open questions

- **Q-m1.** How does the prompt reach `muse exec`: as an argument, or from a file in a private folder (`--prompt-file`)? An argument is visible to other
  processes of the same user; a file needs a temporary folder, which the guard test of `agents.py` counts. Recommendation: the argument, as for
  Claude Code, in step 2 with the fake, and revisit it in step 4 when a real run shows whether `--prompt-file` is worth a folder.
- **Q-m2.** Does a Muse agent need `confine: true` before it may run? Recommendation: no, not in step 2: Muse brings its own sandbox, and umwayi's confinement
  is Landlock or Seatbelt for Claude Code; say so in the label and decide after step 4.
