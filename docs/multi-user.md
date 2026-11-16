# A later shared mode for several people (W74, design note)

## Purpose

This note checks every part of umwayi-os for the case where several people share one account. It says what a later shared mode would need, and what it could not do. It is a design note only: nothing here is built, and no code, rule, steering file, safety check, workflow or exit code changes with it.

The owner's decisions (Nov 16), kept as given:

- `umwayi serve` stays local for now.
- A shared mode is later, and off by default.
- The local file stays the default store.

It uses the terms of three other notes, none of them on main when this is written: the W67 threat model (branch `w67-threat-model`: owner, supervisor, helper, tool output, other agents), W68 untrusted content (branch `w68-untrusted-content`) and W69 network and credentials (branch `w69-network-credentials`).

## Current state

umwayi-os is built for one person, and it says so:

- The README calls it "An AI operating system for one person and their AI helpers".
- [What it is and is not](what-it-is.md) says it is local first: everything it keeps is in the root folder on the owner's machine.
- There is one owner. The owner is whoever has a terminal (`goal._owner`, the W67 note), or whoever holds the serve token (KNOWN-LIMITS 196).
- There is one `rules.yaml`, one `units.yaml`, one `LOGBOOK.md` with its hash chain, and one kill switch file, `.umwayi/KILL` (`umwayi/kill.py`).
- `umwayi serve` binds 127.0.0.1 only and checks a token, the peer, `Host` and `Origin` ([serve](serve.md)). 127.0.0.1 is shared by every user of a machine (KNOWN-LIMITS 198).

## The parts, checked for shared use

### Identity

- **Today:** none. The terminal and the serve token stand in for the owner.
- **Shared mode needs:** a person id for every request and every entry. The proposal is sign-in through an identity provider such as Google or GitHub, used for identity only.
- **What the provider must not be used for:** credentials for GitHub, Vercel, Neon or a model provider. Signing in with GitHub proves who someone is. It must not hand umwayi a token to act on GitHub. Each helper still signs in with its own tool, as today (the W69 note, option 4).
- **Cannot do:** prove that the person at the keyboard is the one who signed in, or stop a member from sharing a session.

### Roles

- **Proposal:** `owner` (one per account; changes rules, budgets and members), `member` (starts work, answers what is theirs), `viewer` (reads), plus one supervisor per group (below).
- **Cannot do:** make a role wise. A member with a wide Yes rule can still do harm inside it.

### Rules and budgets, per person and per group

- **Today:** one rules file and one set of limits (`units.yaml`: per run, per day, per agent per day, per platform per day).
- **Shared mode:**
  - Rules are layered: the account's rules, then the group's, then the person's.
  - No beats Ask me first beats Yes across all layers, as today ([rules](rules.md)), so a person's Yes can never undo a group's No.
  - Budgets are per person, per group and per account. A run's cap is the smallest that applies.
  - **The hard cap never rises by itself.** No rule, answer, role or member raises it (W9.R15.7 today). Only the owner's typed change does, and it is logged first.
- **Cannot do:** stop a member spending their own budget badly.

### The logbook

- **Today:** `LOGBOOK.md`, append only, with a hash chain, an intent record against crashes and an outside anchor (`umwayi logbook verify --anchor`; [logbook](logbook.md)).
- **Shared mode:** an append only table with the same chain:
  - each row holds the hash of the row before it, and the person id;
  - the database role umwayi uses may insert and select, never update or delete;
  - an outside anchor (the newest chain value) is kept by the owner, as today.
- **The store:** behind an interface with two implementations, the file (the default, as today) and a table. Neon serverless Postgres is a candidate for the table. Its Free plan gives 1 GB of storage per project and up to 100 projects, by [Neon's pricing page](https://neon.com/pricing) and [its free plan FAQ](https://neon.com/faqs/free-plan-limits-and-quotas), read on Nov 16; prices and limits change.
- **Cannot do:** the chain shows an edit and does not stop one. A database administrator can rewrite both the rows and the chain; only an anchor kept elsewhere finds that, as today.
- **A conflict with product rule 5:** reaching a hosted database is a network call from the core. Product rule 5 and `tests/test_system.py` allow only two loopback servers, so the table store needs the owner's change to that rule.

### Kill switch scope

- **Today:** one file, global for the root. "On" or "unknown" denies every tool call.
- **Shared mode:** three scopes, person, group and global. A check reads all three that apply, and any "on" or "unknown" denies.
- **Who may turn each on or off:**
  - Anyone may turn their own on.
  - A group's is turned on by any member and off by the owner.
  - The global one is the owner's only.
  - "Off" stays an owner command, never a route of the page ([serve](serve.md)).
- **Cannot do:** stop a helper that does not ask (cooperative, as today).

### Who may change a rule

- **Today:** whoever can write `rules.yaml`. The change is logged before it is used ([rules](rules.md), the rules change log).
- **Shared mode:**
  - The account's rules are changed by the owner only.
  - A group's rules are changed by the owner, or by a member the owner names for that group.
  - A person's own rules are changed by that person, but may never be weaker than the group's (the layering above).
  - Every change is logged with the person id before it is used.
  - A helper and a supervisor never change a rule.

### The supervisor

- **One per group, with its own identity.** Its entries are told apart from every person's.
- **Its actions go through the rules gate,** as a helper's do today (`agent run`, `goal_start`, the hooks).
- **It can never approve its own Ask me first.** An approval needs a person's signed-in session. A supervisor id is refused for every approval, answer and merge.
  - Today the terminal check can be passed by a pseudo-terminal (the W67 note). Shared mode replaces it with the person id, which a helper cannot make.
- **Content it reads is data** (the W68 note). It cannot raise a budget, sign, merge or change a rule by any route.

### Secrets

- **Never stored in the clear by umwayi,** as today. Today umwayi stores only the SHA-256 of the serve token (`umwayi/servetoken.py`).
- **Shared mode:**
  - A session token is kept by its hash.
  - A per-run token a person hands over is kept in that run's memory only (the W69 note, option 4).
  - The database password is the deployment's secret, read from the environment of the server, never from a request and never logged.
- **Cannot do:** protect a secret a member pastes into a prompt or a rule.

### Tenant isolation

- **Between accounts:**
  - Every row carries the account id.
  - Every query is filtered by it in one function of the store interface, and the database also enforces it with row-level security.
  - One project per account is also possible with Neon's project limit.
- **Within an account:** groups see only their own goals, queue and drafts. The account's logbook is shown per group, unless the owner reads all of it.
- **Cannot do:** isolate helpers. They still run as the person's own OS user on that person's machine (W41, [enforcement](enforcement.md)). Shared mode shares the governing state, not the machines.

### The attacker model

- **The local gate assumes 127.0.0.1.** It checks the peer, `Host`, `Origin` and one token, and is built to keep other sites and other users of one machine out ([serve](serve.md); KNOWN-LIMITS 196 to 198).
- **A hosted gate must instead have:**
  - authentication on every request (a person's session, never a shared token);
  - TLS only;
  - rate limits per person and per account, not per server;
  - a lock-out after failed sign-ins;
  - CSRF protection on every change;
  - no cookie readable by a script;
  - every request checked against the person's role before the same core functions run.
- **The local gate is not reused as it is.** Its loopback checks would be wrong behind a hosted proxy.
- **Cannot do:** stop a person who is signed in from doing what their role allows.

### Privacy and consent

- **What would leave a person's machine:** entries with ids, words and counts (as the logbook holds today, never a prompt or a conversation), queue rows and their answers, and drafts if shared.
- **Consent:**
  - Each member agrees to that when they join, with the list of what is shared.
  - The owner can see the group's entries; the member is told so.
  - Nothing a helper reads or writes on a member's machine is sent unless that member's shared mode is on.
- **Leaving:** a member who leaves keeps their local root. Their rows in the shared log stay, because append only means nothing is deleted. The person id can be replaced by a fixed word where the law asks for erasure, which is an open question.

### Backups

- **Today:** the owner copies the root. The chain and the anchor show a restore that lost entries.
- **Shared mode:**
  - The provider's backups (for Neon, its point-in-time restore, whose window depends on the plan; not checked here).
  - An export of the table to a file in the same shape as `LOGBOOK.md`, so `logbook verify` can check it offline.
  - The anchor kept outside both.

### Migration from file to table

- **One-way and owner-run:** a new owner command (not built; the logbook exporter W26 documents gives counts, not entries) reads the file's entries with the checked reader. The table is filled in the same order, with the same chain values. The first table row names the file's last chain value, so the chain continues.
- **Check:** after the move, `verify` of the table equals `verify` of the file, entry for entry.
- **Never automatic, and never both at once:** while the table is the store, the file is read only.

## The lines that say there is no hosted service

These stay true until shared mode ships. They must be changed in the same pull request that ships it:

- `README.md` line 3: "An AI operating system for one person and their AI helpers."
- `README.md` line 30: "... all on your own machine." and "... not a hosted service."
- `PROJECT.md` line 5: "An AI operating system for one person and their AI helpers."
- `docs/what-it-is.md` line 18: "It is local first: everything it keeps is in the root folder on the owner's machine."
- `docs/what-it-is.md` line 26: "Not a hosted service. There is no account, no cloud part of the product and no telemetry sent anywhere."
- `docs/what-it-is.md` line 44: "umwayi itself sends nothing off the machine."
- `site/app/layout.js` line 6: the description "An AI operating system for one person."
- `.kiro/steering/product.md` line 8 ("for one person"), and rules 5 and 10 (no network in layers 1 to 5; a local backend and nothing else). These are steering lines and the owner's; they are listed, not changed.

## Options

| option | what | cannot do |
| --- | --- | --- |
| A: separate roots | each person runs their own local umwayi, as today; a group shares only a repo and pull requests | no shared budget, no group kill switch, no shared logbook |
| B: a shared store, local gates | each person keeps the local gate; the logbook, rules, queue and budgets live in a shared table behind the store interface | the store must be reached over the network, which changes product rule 5; local gates still trust their own machine |
| C: a hosted gate | a hosted service with sign-in, roles and the shared store; local helpers ask it | everything of the attacker model above must hold first; the biggest change, and it ends "not a hosted service" |

Recommendation: A until a second person really uses one account. Then B, and C only if B is not enough.

## The tests each part needs

| rule | test | planted fault |
| --- | --- | --- |
| a person id on every entry | `test_every_shared_entry_names_its_person` | write an entry without one |
| identity only from the provider | `test_sign_in_keeps_no_provider_token` | keep the provider's access token |
| layered rules keep No | `test_a_person_yes_never_undoes_a_group_no` | let the person layer win |
| the cap never rises by itself | `test_no_rule_role_or_answer_raises_a_cap` | let a member's answer raise it |
| append only table | `test_the_umwayi_role_cannot_update_or_delete` (against a local Postgres in CI) | grant update |
| the chain across the move | `test_the_first_table_row_continues_the_file_chain` | start a new chain |
| kill switch scopes | `test_any_on_or_unknown_scope_denies` | read only the global one |
| supervisor never approves | `test_a_supervisor_id_is_refused_for_every_approval` | accept it for `answer` |
| tenant isolation | `test_a_query_without_the_account_filter_is_refused` | forget the filter in one query |
| hosted requests | `test_every_route_needs_a_session_and_tls` | allow one route without it |
| no clear secrets | `test_no_secret_value_in_any_row_or_output` (a planted value swept) | log the database password |
| the lines change together | `test_hosted_mode_and_the_readme_lines_agree` | ship hosted mode with "not a hosted service" still in the README |
| exit codes | rows in `tests/test_exit_codes.py` | a refused request exits 1 |

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-16 | Design note only. `umwayi serve` stays local, shared mode is later and off by default, the file stays the default store; option A until a second person needs it | W74, the owner's decisions of Nov 16. |

## Open questions

1. **Which option first, and when?** Recommendation: none before Dec 3. Option A as it is until a second person shares an account, then B.
2. **Product rule 5 and the store.** A shared store is a network call from the core. Recommendation: when B is built, name the store client as a third exception by name, as the two loopback servers are named, behind the store interface only.
3. **Which identity provider?** Recommendation: GitHub first, because the owner and the builders already use it, for identity only and with the smallest scope that gives an id. Google as the second.
4. **Erasure of a member's id in an append only log.** Recommendation: keep the rows, replace the person id by `left-NNNN` in a separate map table that is not part of the chain. Check this with someone who knows the law that applies before shared mode ships.
5. **One Neon project per account, or one table with account ids?** Recommendation: one project per account while the Free plan's project count is enough, because a project boundary is simpler to reason about than row-level security alone. Keep row-level security as well.
6. **The supervisor's identity.** Recommendation: a fixed id per group (`supervisor-GROUP`), refused by every approval path in one function, with a test that lists every approval path.
