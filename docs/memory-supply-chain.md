# Shared memory poisoning and the app supply chain (W70, design note)

## Purpose

This note designs how umwayi-os could keep its shared memory and its notes between sessions from being poisoned, and how apps could be installed without a supply chain attack. The source is the owner's queue doc, section F4, which is not in this repo; its points were given with the task.

The rule for both: **same rules, same answer.** Every check below is a fixed function of the note's or the app's bytes and the rules, so the same input under the same rules always gets the same result.

It is a design note only. Nothing here is built, and no code, rule, steering file, safety check, workflow or exit code changes with it. Terms are those of the W67 threat model and W68 untrusted content (branches `w67-threat-model`, `w68-untrusted-content`) and of W43 agent apps (branch `w43-agent-apps-design`). None of these branches is on main when this is written. The signing design reused here is [provenance](provenance-design.md) (W49), which is on main and not built.

## Current state

### What is shared memory today, and who writes it

| store | what | who writes it today | checked how |
| --- | --- | --- | --- |
| `memory/` (master, projects, journal) | the context bundle for a helper ([memory](memory.md)) | the owner, by hand. There is no `umwayi memory add` | private paths are left out. No hash and no logbook entry. An agent's edit of `memory/` is not in the guard lists, so it is Ask me first (`cc-ask-write`), not No |
| `queue.md` | questions and answers ([queue](queue.md)) | the owner, umwayi, and helpers through the base when a step is Ask me first | strict parser; a petition's reason is marked untrusted text from an AI helper (`umwayi/petition.py`) |
| `drafts/` | proposals and posts | helpers (Steward, social) | written once with `O_EXCL`; the owner reads before publishing |
| `.umwayi/goals/` | goal state, packets, events | the supervisor only | strict shapes; edits under `/.umwayi/` are No for Claude Code (`cc-no-guard-edits`) |
| `docs-parts/` | status and limits parts, the notes a builder leaves for the next | builders, in a branch the owner merges | form only (`umwayi goal docs check`); a goal task fails on a status part that does not parse (`status_file_invalid`) |
| the packet of a goal task | the guide's handoff to the builder | the guide; the owner approves | strict parser (`goalpacket.parse_plan`); the approval holds the packet's SHA-256 |
| `.kiro/steering/`, `tasks.md` | the notes every builder session reads first | builders and the owner, in pull requests | pinned steering lines stop the guidance loader when changed (`guidance.yaml` `source_hash`); nothing else |

What none of them has:

- a record of who wrote a note;
- a hash of each note in the logbook at the time it was written;
- a check of that hash at the time the note is read.

A note changed between write and read is used as it is.

### Apps and their supply chain today

- **Apps are designed, not built** (W43, branch `w43-agent-apps-design`). In that design:
  - an app is a built-in helper or an agent of `agents.yaml`, never a command line;
  - the manifest is bound to its SHA-256;
  - the owner approves it in a terminal;
  - umwayi never installs anything.
- **What umwayi does pin today:**
  - The Claude Code ACP adapter's npm tree is a lockfile with `sha512` integrity hashes, installed with `npm ci --ignore-scripts` (`adapters/claude_acp/`; KNOWN-LIMITS 60).
  - `ui/` and `site/` have committed lockfiles.
  - The site's High photographs are listed with their SHA-256 (`site/high-assets.json`; `tests/test_site_assets.py`).
- **What it does not pin:**
  - Claude Code, Kiro CLI and OpenCode are checked for a minimum version, not a hash (`agents.PLATFORMS`).
  - OpenCode downloads `ripgrep` by itself (KNOWN-LIMITS 191).
- **Who builds the OS.** umwayi-os is built today by AI builders in branches, and merged by the owner. That is the build process, not an app. No app exists that could build or ship it.

## The design

### 1. Who may write shared memory and handoff notes

| store | may write | may never write |
| --- | --- | --- |
| `memory/` | the owner | every helper, the supervisor and every app. A new guard rule makes a write No |
| `queue.md` | the owner; umwayi's own commands; a helper only through the base (one row, fixed title) | a helper directly |
| `drafts/` | helpers, through the base | anyone else; a draft is never read back as context |
| `.umwayi/goals/` | the supervisor | helpers and apps (No today for Claude Code) |
| handoff notes (status and limits parts, the packet) | the role that owns them: a builder its two parts, the guide the packet | another role, and a note of another task |
| `.kiro/steering/`, `guidance.yaml` | the owner, in a pull request | every helper and app. A new guard rule makes a write No (the W67 open question 3) |

### 2. Hash each note in the logbook, sign the owner's

- **Written:** when a note is written by umwayi or through it, one entry holds its id, its writer's role and its SHA-256. Examples: a packet at approval (already in goal state), a status part at the scope check, a queue row. Never the note's text.
- **Read:** before a note is given to a helper, its bytes are hashed again and compared with the newest entry for it. A mismatch is a failed check (section 4).
- **Owner notes:** `memory/` files and steering lines may be signed by the owner, with the same `ssh-keygen -Y sign` design as W49. umwayi never holds a key, and a helper never signs.
- **Helper notes are hashed, never signed.** A helper has no key: since W64 it has no SSH agent, and that is the point.

### 3. Notes are data, never instructions

- **In a helper's prompt:** each note sits between fixed markers with its id and hash. The prompt's fixed text says what is between them is data. That is a prompt line, not a control (W68).
- **In umwayi's own reading:** umwayi reads a note only through a strict parser that keeps fixed fields:
  - a packet's keys;
  - a status part's four lines;
  - a queue row's seven cells;
  - a verdict word.

  A note can never name a command umwayi runs, a rule it changes or a budget it sets.
- **What this does not do:** stop a helper from following an instruction it reads in a note. Same rules, same answer holds for umwayi's checks, not for the model.

### 4. Quarantine a note that fails a check

- **The checks:**
  - the hash does not match its entry;
  - the parser refuses it;
  - its writer is not allowed for its store (section 1);
  - it is bigger than its store's limit.
- **What quarantine does:**
  - The note is moved to `.umwayi/quarantine/` with its id and the check that failed.
  - It is given to no helper.
  - One logbook entry and one queue row name the id and the check, never the text.
  - In a goal run, the task moves to `needs owner`, with a cause word such as `note_quarantined`.
- **Release:** only the owner, with a typed command in a terminal. The command writes a new hash entry, so the note passes the next check.
- **Same rules, same answer:** the check is a pure function of the note's bytes, its entry and the rules. Run twice, it gives the same result.

### 5. Install an app from a pinned source with a hash

- **The pinned source.** It is one of two things:
  - a local folder the owner copied, with the expected SHA-256 of `manifest.yaml` typed by the owner;
  - a git commit SHA of a repository the owner names, read from a local clone the owner made.

  umwayi never fetches.
- **The check.** The manifest's SHA-256 is compared with the typed or pinned value. A mismatch refuses the app (exit 2), and nothing is copied.
- **App code.** In W43, an app is a built-in helper or an agent of `agents.yaml`, so it adds no code. If a later app brings code, every file it brings is listed in the manifest with its SHA-256, checked the same way, and the approval covers all of them.
- **Platform tools.** For Claude Code, Kiro CLI and OpenCode, a version and hash pin per agent in `agents.yaml` (`sha256:` of the executable) would turn "at least version N" into "exactly this file". It is an option, not a must (open question 3).

### 6. Permissions declared by the app, approved once

- **The W43 design, unchanged:** permissions are rules action types listed in the manifest, approved once by the owner in a terminal, bound to the manifest's hash. A changed byte needs a new approval.
- **An action outside the permissions is No.** A permission is never a Yes: the rules still answer.

### 7. No app builds or ships the OS

- **What an app's manifest may never list:**
  - writes under `umwayi/`, `adapters/`, `tools/`, `connectors/`, `.github/`, `.kiro/` or `rules.yaml`;
  - the action types `publish`, `deploy` and `agent_install`;
  - a merge or a push.

  The loader refuses such a manifest (64).
- **Building and shipping umwayi-os stays the owner's process:** builder sessions and goal tasks in worktrees, merged by the owner, gated by the checks of every pull request. An app is never part of it.
- **What this does not stop:** a goal task, which is not an app, writing umwayi's code in its worktree. That is how umwayi-os is built today, and the owner's merge is the gate.

## What cannot be checked, said plainly

- **Whether a note is true or honest.** A hash shows it is unchanged, not that it is right. A builder can write a wrong status part with a matching hash.
- **Whether a note will mislead a model.** Words in a note that read like an instruction cannot be told from words that do not (W68).
- **Notes umwayi never sees.** A file a helper reads with its own tools, or text in a pull request body, is not a note of umwayi's.
- **Whether a pinned source is safe.** A hash shows the bytes are the ones pinned, not that they are harmless.

## The tests each part needs

| rule | test | planted fault |
| --- | --- | --- |
| writers per store | `test_a_helper_write_to_memory_or_steering_is_no` | leave `memory/` as Ask me first |
| hash written | `test_each_note_written_has_one_hash_entry_and_no_text` | log the text |
| hash read | `test_a_note_changed_after_its_entry_is_quarantined` | skip the read check |
| same rules, same answer | `test_the_note_check_is_the_same_for_the_same_bytes_and_rules` (run twice) | use the clock in the check |
| data, not instructions | `test_umwayi_reads_notes_only_through_their_parsers` (an import and call scan) | use a status part's text in a command |
| quarantine | `test_a_quarantined_note_reaches_no_helper_and_adds_one_row` | give it to the next prompt |
| release is the owner's | `test_release_needs_both_terminals` | accept an environment flag |
| pinned install | `test_a_manifest_with_another_hash_is_refused_and_nothing_copied` | copy first, check after |
| no fetch | `test_install_opens_no_network_module` | import `urllib` |
| no app builds the OS | `test_a_manifest_that_writes_umwayi_or_lists_publish_is_64` | allow `tools/` |
| owner signature | `test_an_owner_note_with_a_bad_signature_is_quarantined` (as W49's verify tests) | accept a missing signature |
| exit codes | rows in `tests/test_exit_codes.py` | a quarantine exits 1 |

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-16 | Design note only. Writers per store, a hash entry per note written and checked on read, notes as data, quarantine with the owner's release, apps from a pinned source with a hash, permissions approved once, and no app builds or ships the OS | W70, the owner's queue doc section F4. |

## Open questions

1. **Which part first?** Recommendation: the writer rules of section 1 (No for helper writes to `memory/`, `.kiro/steering/` and `guidance.yaml`), because they are rule changes only. Then the hash on write and read for packets and status parts, which umwayi already writes.
2. **Should `memory/` files be signed by the owner?** Recommendation: not at first. Hash them in the logbook when the bundle is built, and quarantine a file whose hash changed without an owner entry. Signing can follow W49.
3. **Pin the platform tools by hash?** Recommendation: record the hash in `umwayi agent check` output first, without refusing, for a month. Refusing on a hash would break every vendor update, so decide that only after seeing how often they change.
4. **Quarantine in a goal run: stop the task or the goal?** Recommendation: the task, with `needs owner`, as the other unclear causes do. The goal goes on only after the owner answers.
5. **What size limit for a note?** Recommendation: the limits umwayi already uses for each store (the packet's, the status part's, the queue row's), with one new limit for `memory/` files equal to the bundle's.
