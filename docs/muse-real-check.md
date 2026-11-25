# The real Muse check (M3): what one run proves, and how it is done

## Purpose

The owner said yes on 2026-11-25 (22:12) to one real Muse run, a note first. This note says what that single run is meant to show, what it cannot show, and the
steps, so that it is one small, recorded run and nothing more. Docs only: nothing here has been run, and no real Muse was started by umwayi so far (steps 1 to 3 of the
Muse start are in main and are tested with a fake only).

## Current state

- **In main:** a Muse agent can be checked and started through the one `_start`; before anything is reserved the run passes three gates in order (the owner's `public: true`,
  the acceptance of the provider `muse`, the stop line of 5 percent with a fresh reading of `credits.yaml`); the step cap is the agent's `max_turns` and
  `--contributor-mode off` is always passed. `muse` 's own sandbox is Muse's.
- **The owner's words (G-0085):** the repository is public (the mark is on its way in PR 265); the Muse acceptance of 10000 UU is already in `units.yaml`; yes to this check.
- **Not known, and what the run is for:** what Muse's hook receives and answers (the format of `.muse/hooks.json` is an assumption), whether the stored browser sign-in alone works with no key set,
  whether `muse exec` needs a terminal, the exit code of a finished run and its output shape (`--json` lines), and what one run costs in free credits.

### What ONE run proves, and does not

It proves: that `agent run` can start the real `muse exec` through the gates, on public work, with the key variables removed; the exit code and the shape of its output; whether a terminal is needed;
whether the stored sign-in alone is enough; and, from two readings of the billing page, about what one tiny run costs. It does NOT prove: that Muse's sandbox holds, that the hook format
is right unless a tool call is made (the run is read only and may make none), what a long goal costs, any role of M6, or anything about private work (never sent).

### The steps

1. **Before:** a fresh reading of the credits (the guide reads the billing page in Chrome when asked, read only; the number is rounded into `credits.yaml` in a scratch copy, never the exact figure).
2. **The scratch root:** a throwaway folder with a copy of the umwayi-os `units.yaml` (the owner's own mark and acceptance, copied, not written by the builder) and a fresh `credits.yaml`; an `agents.yaml` with one Muse agent
   (`max_turns: 3`, a scratch work folder holding only made-up public text), and the hook file the check names. A scratch root is NOT a new mark: it holds a copy of what the owner wrote for the public repository.
3. **The run:** one tiny read only prompt (for example: list the files of the scratch folder and reply with their number), through `umwayi agent run`, with `--max-model-steps 3` from `max_turns: 3`, no `--yolo`, no `--disable-sandbox`,
   recorded start to end under the real run rules (neutral copy, no home path, indexed).
4. **After:** the credits again at once, and again an hour later (the billing page lags by up to an hour, so one cent moving is not proof); both readings are written down.
5. **The report:** the exit code, the output shape, whether a terminal was needed, whether the stored sign-in alone worked, the two credit differences, what did not work, and what was not verified.

### Stops

A key, a token, a sign-in prompt, a password or a payment: stop and tell the owner. A run that fails twice: stop. A prompt or a file that is not public: never sent. If the gates refuse (no mark in the scratch copy, a stale reading): that is a result, recorded, not a reason to write the mark myself.

## Decisions log

- 2026-11-25 (owner, 22:12, through G-0085): yes to the real Muse check, a docs note first, public work only.
- 2026-11-25 (this note): one run, read only, three steps cap, credits read before, after and an hour later; the scratch root copies the owner's `units.yaml`, so no mark or acceptance is written by the builder.

## Open questions

- **Q-r1.** May the scratch root hold a COPY of the umwayi-os `units.yaml` (mark and acceptance)? Recommendation: yes, it is the owner's own file, and the work in the scratch folder is made up and public.
- **Q-r2.** Who writes the one Muse entry of `agents.yaml` (a guard file)? Recommendation: the scratch root's own `agents.yaml`, written by the builder, since it is not the repository's file and lives in a throwaway folder; the repository's `agents.yaml` is never touched.
- **Q-r3.** Is a read only prompt that may make no tool call enough? Recommendation: yes for the first run (it answers the sign-in, terminal and cost questions); a second run with one harmless tool call can show the hook, with the owner's yes.
