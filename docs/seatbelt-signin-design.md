# Sign-in under Seatbelt: an owner token, passed by name (G-0059, option b)

## Purpose

A signed-in Claude Code could not find its sign-in under the Seatbelt profile (measured 2026-11-25: `Not logged in`, while the same command without
Seatbelt printed OK). The owner decided on 2026-11-25 (12:53, through the guide) that the way out is option (b): a token the owner creates, set
in the owner's own shell, passed to the helper through the scrubbed environment, never printed, logged or stored by umwayi. Option (a), a read of
the Keychain, is the fallback only if (b) fails, and only with the owner's word. This note settles how, before any code. Docs only: nothing is built,
`CHECKED_ON_MAC` stays False, and no token was created, read or asked for.

## Current state

Read from the code and the notes on 2026-11-25. Option (b) meets three rules that were made on purpose, so they are named here and not changed
silently:

- **Part 7c-1 (2026-11-09, [the agent front door](agent-front-door.md))** starts Claude Code only when a Claude subscription login pays, read from
  `claude auth status --json`, and refuses `CLAUDE_CODE_OAUTH_TOKEN`, an API key and the other credential names. A token in the environment is
  refused today.
- **`env_keep`** in `agents.yaml` lists names that an enforced start passes on, and refuses every name of `CLAUDE_CREDENTIAL_ENV`, which holds
  `CLAUDE_CODE_OAUTH_TOKEN`. So the token cannot be passed by `env_keep` today, which is right: a copied list must not be able to pass a credential.
- **`agent login`** never runs `setup-token` (it is on the forbidden list). The owner runs it, in their own terminal.

What the official documentation says (code.claude.com, authentication page, found by search on 2026-11-25, not run): `claude setup-token` creates a
long-lived OAuth token (the page says one year) for scripts and CI where a browser sign-in is not possible; it does not store the token; the person
sets it as the environment variable `CLAUDE_CODE_OAUTH_TOKEN`. I found no official statement of the token's scope and no command that lists or
revokes such tokens. Unofficial issue reports describe `401 Invalid bearer token` with `claude -p` for some accounts: not confirmed, so the first real
test must show whether it works for this account.

### The proposal

- **The name.** `CLAUDE_CODE_OAUTH_TOKEN`, as documented. The owner sets it in the shell that starts umwayi. It is never written in a file of the
  repository, a chat, a logbook line or a status part.
- **A new key, not `env_keep`.** An agent entry gets `token_env: CLAUDE_CODE_OAUTH_TOKEN` (one name, from a short fixed list). `env_keep` keeps
  refusing credential names. The name is passed only on a Seatbelt start of an agent with `confine: true`, under a mode file that says `enforced`.
- **umwayi never reads the value.** It copies the named variable from its own environment into the child's, or passes nothing if it is not set,
  and then says `refused: not signed in (token_env is set in agents.yaml but the variable is not set)`.
- **The login check.** Part 7c-1's check would still refuse the token. For exactly this case, an agent with `token_env`, the check accepts what
  `auth status --json` reports for a token login. What it reports is NOT measured (it needs the owner's token), so the accepted words are an open
  question below, to be filled from a real run.
- **The logbook** gets one fixed line per start: `token variable CLAUDE_CODE_OAUTH_TOKEN passed to the helper (the name only; the value was not read)`.
  Never a value, a length, a prefix or a hash.

### What a helper can do with it (limits, said plainly)

- A helper, and every process it starts, can read its own environment, so it can read the token. The Seatbelt profile does not hide an environment
  variable.
- The network is open in this path (limit 344), so a helper that wanted to could send the token to any host. Nothing here stops that.
- The token lasts about a year and I found no documented way to revoke it from the command line. If it leaks, the owner revokes it from the account
  page, if there is one, or by signing out everywhere. This is a risk the owner accepted by choosing (b); the note does not make it smaller.
- umwayi cannot see or cap the use on the owner's plan.

### What the owner does (documented, not run)

The steps go in [the Seatbelt check](seatbelt-check.md): run `claude setup-token` yourself in your own terminal (it opens a browser sign-in and prints
a token once), copy it only into the shell session you start umwayi from (`export CLAUDE_CODE_OAUTH_TOKEN=...` typed by you), and never paste it into
a chat, a file or a screenshot. Builder rule: never ask for the value, never print the environment.

### The build, in order, each its own pull request

1. This note (docs only).
2. The `token_env` key and its checks, with the logbook line (owner stop: `agents.yaml` and `agents.py`).
3. The login check that accepts a token login for an agent with `token_env` (owner stop: it changes a part 7c rule).
4. The Seatbelt start passes the named variable (owner stop; `CHECKED_ON_MAC` stays False).
5. One real tiny session under the profile with the owner's token, recorded, run by the owner in their own terminal so that nobody else holds the token.

## Decisions log

- 2026-11-25 (owner, 12:53): option (b), an owner token through the scrubbed environment; option (a) only as a fallback and only with the owner's word.
- 2026-11-25 (this note): a new key `token_env`, not `env_keep`; the name only in the logbook; umwayi never reads the value; the three earlier rules
  above are changed only by builds 2 and 3, each an owner stop.

## Open questions

- **Q-s1.** Which words does `auth status --json` report when the token pays? Recommendation: the owner runs step 5 in their own terminal and sends back
  the five fields that part 7c-1 already reads (never the token), and build 3 accepts exactly those.
- **Q-s2.** Who runs the first real session? Recommendation: the owner, in their own terminal, so the token is never in the builder's environment.
- **Q-s3.** Does the token work with `claude -p` for this account (the unofficial 401 reports)? Recommendation: step 5 answers it, and if it fails
  the next step is option (a), only with the owner's word.
