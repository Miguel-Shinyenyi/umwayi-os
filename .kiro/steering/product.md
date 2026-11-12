# umwayi-os product steering

Read this before any work in this repo. Later sessions must follow it.

## Product

- Name: **umwayi-os** (lowercase in code, the command is `umwayi`).
- What it is: an AI operating system for one person and their AI helpers.
- It keeps memory, enforces rules before an AI helper acts, tracks a queue of tasks and decisions, archives moved text with a fingerprint, and writes a logbook of every change.
- All code in this repo is new and written from Nov 7 2026.

## Words to use in user text

Use these exact words in messages, docs and CLI output:

- rules
- queue
- archive
- logbook
- AI helper
- Yes
- No
- Ask me first

Do not use em dashes in docs or user text. Use commas, colons or periods.

## Safety rules

1. Fail closed. Unknown, missing, malformed or ambiguous input means **Ask me first**.
2. Never print secrets. Private paths are never put in a context bundle, and errors never echo file content.
3. Never push to main. Work on a feature branch and open a pull request.
4. Helpers draft only. An AI helper never publishes, never holds bank or card credentials and never moves money.
5. No network calls in layers 1 to 5. No module of the core package imports a network library (the system test checks every module).
6. No secrets in the repo.
7. Every helper action passes `umwayi check` first.
8. A crash blocks. Every unexpected error exits 2, never 0, 1 or 3. An adapter (layer 9) catches every error and blocks, because on Claude Code exit 1 blocks nothing.
9. The core `umwayi` package stays standard library only. Only adapter packages (layer 9, and layer 10 adapter packages) may use third party packages, pinned and listed in their own README. The one other place is the `ui/` folder of layer 12, outside the package, under rule 10. Since Nov 11 (round 2) the public site in `site/` of layer 12 is a second such place, outside the package, under rule 10. The OpenCode plugin (`adapters/opencode/plugin/`, layer 10 part 8) is umwayi's only JavaScript in a gate: plain JavaScript that imports only Node built-ins (`node:`), with no npm package, and umwayi never runs npm, Bun or an OpenCode plugin install for it.
10. The web interface (layer 12) only looks. It never writes to the repo, never runs a command and never calls a network. It gets state only from a snapshot of counts: no text from any file, no paths, no secrets. Its third party packages (three.js and esbuild, pinned, with a lockfile) are build tools in `ui/`, installed by the owner with `npm ci --ignore-scripts`; umwayi never runs npm. The built page is committed, stays under about 2 MB and makes no network request. Its home links are plain anchors the owner clicks. The public site of layer 12 (`site/`, decided by the owner on Nov 11, round 2) is the one exception to "never calls a network": it is served from its own host and fetches only its own files from that host; it shows sample counts until a visitor opens a snapshot file of their own, which the browser reads and never sends, stores or uploads (UI.3), and it has no analytics or tracking. The owner's live view keeps every word of this rule.

## Exit codes (every command)

- 0 = Yes, or done
- 1 = a refusal: something was checked and found wrong, nothing was changed
- 2 = No, and every unexpected error (a crash blocks)
- 3 = Ask me first
- 64 = a usage or config error (wrong arguments, a value that is not allowed, a bad `umwayi.json`, jobs file or workflow file)
- A missing or broken `rules.yaml` gives Ask me first, not 64.

## Build order

Each layer works alone and is tested before the next starts. A layer that is not started begins only when the owner says so. Status and tasks: `.kiro/specs/umwayi-os/tasks.md`. Known limits: `docs/KNOWN-LIMITS.md`.

Done (PRs 1 to 8, then hardening and the whole-system test in PR 9, 556 tests, Python 3.10 to 3.13):

1. Memory: plain files (master context, projects, journal), a loader that builds one context bundle, private paths from a config file.
2. Rules: `rules.yaml`, `umwayi check`.
3. Queue: `queue.md`, `umwayi queue list|add|answer|close`.
4. Archive: `umwayi archive move|verify`, SHA-256 fingerprints, pointer left behind.
5. Logbook: `LOGBOOK.md`, append only. Layers 2 to 4 write here once it exists.
6. Automation: scheduled scripts, weekly progress report from git history, draft-only publish step that never pushes.
7. Helpers: Steward and a social helper, draft only.
8. Workflows: named workflow files, content loop (collect, brief, draft, approve), kill switch flag.

Built since (tasks.md has the status of every task):

9. Adapters (PRs 11 and 12): a thin adapter per AI platform (Claude Code PreToolUse hooks, Kiro hooks, a generic stdin and stdout adapter) turns hook input into `umwayi check` input and the answer back into allow, deny or ask.
10. Own command line and chat (PRs 13 to 29): one front door that starts Claude Code and Kiro through their own CLI or the Agent Client Protocol, with the queue, rules and logbook in front, subscription first. No model client. Open: the owner's first real run (10.31). Part 8, OpenCode over ACP (10.R13), is specified (PR 44) and, once the owner approves it, is built before Dec 3 (the owner, Nov 11; the owner sets its dates). Muse Spark Open as an OpenCode model (10.R14) is spec only and follows OpenCode.
- Logbook crash safety (PR 27).

Not started, each only after the owner approves its requirements, design and tasks:

11. Linux-like features: approved (PR 30), built now (PR 31). Scope for Dec 3: scheduled runs through systemd user timers that call the existing front doors; file watching and tmux cut, SQLite and a sandbox deferred to after Dec 3. No new scheduler, file system or shell.
- The logbook hash chain (approved) and the budget governor (approved).
12. Web interface, the view (layer 12): in scope before Dec 3 (it was a non goal until Nov 10). A realistic 3D scene of the Kenyan highlands at dusk (decided by the owner on Nov 11), generated in code with no downloaded image, with eleven natural features as the stations and a lantern on a shepherd's staff at the centre. It is also the hero of the umwayi-os home page. It shows counts from a read only snapshot (`umwayi view snapshot`), moves a station nearer when it needs the owner, and has an owner checks panel. Calm by default. Spec approved (UI.0, PR 38) and changed on Nov 11 (UI-Q12 to UI-Q16). Phases UI.1 to UI.5 are built one pull request each; the first UI.1 look (PR 39) was not accepted and is being reworked. On Nov 11 (round 2, UI-Q17 to UI-Q22) the owner added three tiers chosen in the browser (List, Standard, High), a public site in `site/` (Next.js on Vercel, no analytics, no tracking) beside the owner's live view, which stays one static file with no network request, one scene module shared by both, and a forest, flowing water, a Maasai shepherd and real looking animals. Rule 10 holds for the live view; the public site may fetch only its own files from its own host.

## Schedule to Dec 3

The schedule in `.kiro/specs/umwayi-os/tasks.md` ("Schedule to Dec 3") is the one to follow. In short:

- Nov 10 to Nov 11: layer 11 (moved up from Nov 14 to Nov 15)
- Nov 16: logbook hash chain
- Nov 17 to Nov 22: budget governor
- Nov 23 to Nov 26: whole-system test again and a security scan (moved up to Nov 10 to Nov 12)
- Nov 11 to Nov 22: web interface, layer 12, phases UI.1 to UI.5 (re-estimated on Nov 11 at about 92 hours; the owner accepted four cuts, leaving about 75)
- Nov 23 to Nov 28: README, demo, Devpost text
- Nov 29 to Dec 2: freeze, only fixes for defects that tests find
- Dec 3: submit

## Engineering rules

- Python, standard library first. One entry point named `umwayi`.
- Every layer has tests. CI runs tests on every pull request.
- Specs live in `.kiro/specs/umwayi-os/` (requirements, design, tasks).

## Non goals for Dec 3

Finance and marketing loops.

## Layer 13: correction and graded autonomy (in scope before Dec 3, the owner, Nov 11)

This section is added at the end so it merges cleanly with the layer 12 changes. It replaces the older sentence in item 12 of the build order that says nothing of layer 13 is built or planned: layer 13 is now planned.

- **What it is.** Four ways to correct and one score, built in this order, each slice shipping alone, merged whole or not at all, and stopped where Dec 3 finds us: (1) Elections: a `review_by` date on Yes rules and standing approvals, past it the rule falls back to Ask me first, `umwayi rules due` lists them, the fallback is logged; (2) Reversal: a closed decision is reopened with a reason, as a new logbook entry that links the old entry by its hash, the old entry never changed or marked, and every decision records what would change my mind; (3) Courts: an AI helper may petition against a No, the petition becomes a queue item and never changes the verdict, and a rules change is logged before it is used; (4) Honest tension: stop criteria and a plain note in the docs that no state is perfect; (5) Graded autonomy: a score per action class from the owner's record (approved as proposed, edited, rejected, reverted), shipped with its behaviour.
- **Status.** Spec in the L13.0 pull request. It is built (L13.1 to L13.6) only after the owner approves that spec. The last day a slice can be merged is Nov 28. Specs: `.kiro/specs/umwayi-os/` (requirements 13.R1 to 13.R15, design "Layer 13", tasks L13.0 to L13.6).
- **Safety rules added by layer 13** (the rules 1 to 10 above are unchanged and still apply):
  11. Layer 13 never changes a No and never writes to the logbook except by appending a new entry. A correction is a new entry, never an edit.
  12. Graded autonomy can only move Ask me first to Yes, only where a rule explicitly opts that action class in, and it fails closed: low data, an irreversible or costly action, a No, a broken or missing hash chain, the kill switch on, an unknown state, a dry run or a failed logbook write always mean Ask me first. It never reads text, only counts. Every move is logged with its inputs. It is off by default and one setting turns it off. It never applies to money, publishing, a schedule install, a spending approval or the start or permission of an agent.
  13. Nothing claims a state is perfect, safe or proven. The docs say that no state is perfect, and a test searches the layer 13 docs and output for claims of perfection.
- **Stays a non goal for Dec 3:**
  - any change to the web interface for layer 13 (the review, reopened and petition stations of 12.R8 only if the owner asks after layer 13 exists);
  - a way for an AI helper to change a rule, an answer or its own score;
  - learning from text, a model or any statistics beyond the counts and one interval;
  - automatic approval of a petition, and any automatic edit of `rules.yaml` or `autonomy.yaml`;
  - holding a rules change until the owner accepts it, and an outside signature of the owner's record;
  - an expiry on installed schedules (they run through Yes rules, which can expire).
- **The words of layer 13** are the product words above: rules, queue, archive, logbook, AI helper, Yes, No, Ask me first. No em dash.
