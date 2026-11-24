# Stories in the GUI (U1, step 1: design note)

## Purpose

The GUI here is the browser layer that sits on top of the umwayi commands (item 16 of the promoted queue). It is NOT the 3D scene page.

Each feature of umwayi-os has a story: what was missing, one analogy and where it stops being true, what the feature does and does not do, and what the owner checks by hand. Today a story is written for a pull request (the template asks for it, `tools/pr_story.py` checks that it exists) and, when the owner asks, for a video. This note designs one more use of the SAME story: a panel in the browser layer that sits on top of the terminal. One story per feature, written once, used three times: in the pull request text, in a video, and in the GUI.

The terminal stays the source of truth. The GUI calls the same commands and reads the same files. It decides nothing the terminal does not decide and has no new power. Videos do not wait for the GUI: both are made from the same story file in parallel, and posting a video is the owner's act. This note is docs only and builds nothing.

## Current state

What exists, checked on 2026-11-24:

- **The local backend.** `umwayi serve` (W6, `docs/serve.md`) answers the owner's page on `127.0.0.1` only, with a token and the rules gate. The page never writes to the repository or runs a command by itself.
- **Pages.** `ui/src` holds the 3D scene (`index.html`), the command map (`cli-map.html`, built from the real command parser), the goal map (`goal-map.html`) and the progress page. All are built with `node build.mjs` into `ui/dist`.
- **Stories as text.** The pull request template has a Story and a Record part and `tools/pr_story.py` fails an owner-stop pull request whose story is too short. `docs/story-guide.md` is the guide for articles and videos. The first concept video of this kind (the fuel gauge, PR 215) and its script live outside the repository, in the owner's video pack.
- **Not in the repository:** a story file format, a folder of stories, a panel, a list view of stories, and a command that exports stories for a page. The brief also names a base rules library with toggles that the panels sit after; I did not find it in the repository, so this note does not rely on it.

### The rules the GUI keeps

1. **The terminal is the source of truth.** A panel shows the real output of the command it explains and the exact command to type ("show me in the terminal"), so the GUI teaches the terminal and never replaces it.
2. **The words on screen are the words the command prints.** A story names its fixed words (for example `provider_unknown`, `no_acceptance`, `unchanged`, `changed`). A test checks that each word appears in the code the story names.
3. **Built or planned is always shown.** A story says `built`, `partly` or `planned`, and "cooperative today" is shown wherever it is true. No story, caption or panel says enforced, sandboxed or confined until one real enforced run (W40) has finished a goal. The honesty scan runs on every story.
4. **Local only.** `umwayi serve` stays local. There is no hosted or multi user claim.

### What a story gives a panel

- the story itself: what was missing, one analogy and a line on where it stops being true;
- the real output of the command, in a terminal style box;
- five scenes as steps, each with a label, a chip and a caption;
- a "does not do" line and a "what you check by hand" list;
- chips with the fixed words and tones: yes, ask, no and info, matching Yes, Ask me first and No;
- a built, partly or planned badge, and the exact command to type.

A plain list view comes first (no 3D, no WebGL), then the panels.

### The story file (proposed)

One file per story, `docs/stories/ID.json` (JSON is in the standard library, and a page can read it through a script tag with no network): `id`, `title`, `command` (the exact terminal command or the module), `prs`, `built` (`built`, `partly` or `planned`), `honesty` (one sentence), `analogy`, `analogy_stops`, `does_not` (a list), `owner_check` (a list), `words` (the fixed words) and `scenes` (five: label, chip, tone, caption).

Tests planned with the files, each with a planted fault: the five scenes exist; every word in `words` appears in the code the story names (a story with a word the code does not print fails); the honesty scan passes; no em dash; at least 100 words in the prose fields.

### The first four stories and their commands

| Story | Command or module | State |
|---|---|---|
| The broker (PRs 185, 186): the gate in its own process | `umwayi/broker.py` and the hook that asks it | built; cooperative today unless the owner runs an enforced mode on a machine that supports it |
| Sandbox settings (PR 182): no sandbox, no start | `umwayi agent check` on an enforced Claude Code agent | built |
| Provenance (PR 184): what changed since the record | `umwayi verify PATH` (the module function is `provenance.compare`; there is no command named `provenance compare`) | built; signing with the owner's own key is the owner's step |
| The fuel gauge (PR 215): learn the size of the tank first | `units.provider_gate` | partly: nothing calls the gate yet |

The video scripts hold the scenes for these four and are reused for the story files.

### What this does not prove

It does not prove that a story is good (the owner and the guide read it), that a panel shows live state (a later step: counts only, never content, through a read only snapshot), or that anything is enforced. A panel is a way to read what the terminal already says.

## Decisions log

- 2026-11-24 (owner): the stories that make a video also build the GUI on top of the terminal. The videos do not wait. Posting stays the owner's act.
- 2026-11-24 (this note): the order of work, one pull request open at a time. (1) This note, docs only. (2) The four story files and their tests. (3) A read only command that exports the stories for the page (a new command: owner stop). (4) The list view and the panels (owner stop). (5) Later, live state through a read only snapshot.

## Open questions

- **Q1.** Where do the stories live? Recommendation: `docs/stories/ID.json`, one file per story, so a story is reviewed like any other file and the export command reads one folder.
- **Q2.** The brief says `provenance compare`. The command is `umwayi verify PATH`. Recommendation: the panel uses `umwayi verify`; the story names the module function only in its prose.
- **Q3.** Is JSON right, since a story has prose? Recommendation: yes for step 2, because the standard library reads it and a test can check each field; if the prose is hard to edit in JSON, add a Markdown front end later that compiles to the same JSON.
- **Q4.** The base rules library with toggles. Recommendation: do not wait for it. The list view and panels need only the stories and the command output, and the library can add a panel later.
- **Q5.** One story or one per audience (owner, a judge, a tester)? Recommendation: one story, three views of it (the pull request, the video, the panel), as the owner asked.
