# Muse: the untrusted workspace, and the hook that did not run

## Purpose

The one real Muse run of 2026-11-25 showed that umwayi's gate did not see Muse's tool call. This note says exactly what was seen, what the installed Muse offers (read from
`muse exec --help`, which starts no model), and three ways to go on, with a recommendation. Docs only: nothing is built, no second Muse run was made, and no agents.yaml entry lets
Muse run. Until a run is shown to gate its tool calls, Muse stays on the label cooperative, plus Muse's own sandbox, and umwayi's gate does NOT see Muse's tool calls.

## Current state

**What the run showed** (Muse Code 1.4.25, scratch root, recorded as `umwayi-muse-real-check-mac`):

- Muse printed `Agent delegation: auto unavailable: workspace is untrusted` and `project MCP servers ... are not loaded because the workspace is untrusted; restart with --trust-workspace to load them`.
- Muse then ran one shell command (`ls -1`, then a count) and answered correctly. The logbook of the scratch root holds `umwayi check` entries only for `agent_run` and `budget_check`, none for the
  command: the project `.muse/hooks.json` was not loaded, so umwayi's gate never asked. The line `ok: hook file: .muse/hooks.json calls the gate` of `agent check` was true of the file only.
- The stored browser sign-in alone worked. The model was `muse-spark-1.3-contributor` although `--contributor-mode off` was passed.

**What `muse exec --help` says** (1.4.25, read 2026-11-26):

- `--trust-workspace`: "Load this workspace's skills and rules (this run)"; the main help adds "does not save trust". The help does NOT say that project hooks are loaded by it. The route note says hooks load "after the folder is trusted": that is an
  assumption until a run shows it.
- `--disable-shell` ("Disable workspace shell execution") and `--disable-write` ("Disable non-shell workspace filesystem writes"); `--disable-web-tools`; `--approval-mode untrusted|on-request|never` (default on-request); `--permission-profile <ID>`
  (the ids are not listed by the help; the docs name Ask me, Auto-review, Unrestricted and Read-only); `--sandbox-network` (default proxy-only); `--yolo`, `--disable-approval` and `--disable-sandbox`, which umwayi never passes.

**What is NOT known:** whether `--trust-workspace` makes Muse load `.muse/hooks.json`; the format of that file; what Muse's hook receives and answers; the ids of the permission profiles; whether `--disable-shell` and `--disable-write` hold.

### The options

1. **Trust the folder in a scripted way (`--trust-workspace`).** umwayi would pass it for a Muse run in a folder the owner controls, and a canary (a hook that writes a marker) would show whether the gate ran.
   For: it is the way to make the hook load, if the assumption holds. Against: trusting a workspace also loads the workspace's skills, rules and MCP servers, so what is in the folder can steer the helper; and it needs the hook format, which is unknown.
2. **A read only way: no tool that needs a gate.** Run Muse with `--disable-shell --disable-write` (and `--disable-web-tools`), or a read only permission profile, so that Muse cannot write or execute, and the question "did the gate see it" does not arise for those tools.
   For: it uses only flags the help names; no hook is needed. Against: Muse can still read the folder and send it to the provider (public work only, as the data rule says); and whether the flags hold is not verified.
3. **Refuse Muse when the hook is not shown to have run.** Add a canary: after the run, if the marker is missing, the run is refused as `hook_not_confirmed`; and check before the run for an untrusted folder (`folder_untrusted`, which the route note already names).
   For: it turns "assumed" into "shown" for any role. Against: it needs option 1 (a hook cannot load while the folder is untrusted), so it inherits its risks.

### Recommendation

Option 2 now, for the roles that write nothing (tester, guide): they need no gate when Muse cannot write or run a command. Option 1 plus option 3 together before any role that writes (builder), and only after a recorded run with the owner's yes shows the
canary seen on a trusted scratch folder. Until then: no Muse goal run, no agents.yaml entry for Muse, and the label stays cooperative.

## Decisions log

- 2026-11-26 (the guide, G-0091 and G-0092): no Muse goal run and no agents.yaml entry for Muse until a run is shown to gate tool calls; the label stays cooperative; this note first; no second Muse run without the owner's yes.
- 2026-11-26 (this note): three options and a recommendation; nothing built.

## Open questions

- **Q-t1.** Does `--trust-workspace` load `.muse/hooks.json`? Recommendation: find out in ONE more recorded run on a scratch folder with a canary hook, with the owner's yes (it spends free credits).
- **Q-t2.** May a Muse role be read only (option 2) for tester and guide? Recommendation: yes, and say in every PR that the flags were not shown to hold until a run shows it.
- **Q-t3.** Is a workspace's skills and rules loading (option 1) acceptable for a folder the owner controls? Recommendation: only for a scratch folder with made-up content, never for the repository.
