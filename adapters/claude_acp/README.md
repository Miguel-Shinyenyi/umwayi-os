# adapters/claude_acp: Claude Code over ACP (layer 10 part 7)

This folder holds the one third party package of umwayi-os: the ACP adapter for Claude Code,
[`@agentclientprotocol/claude-agent-acp`](https://www.npmjs.com/package/@agentclientprotocol/claude-agent-acp),
pinned to exactly **0.101.0**. `umwayi agent chat NAME` will use it for an agent with
`platform: claude-code` and `transport: acp`. The core `umwayi` package stays standard library only
and never imports anything from here; it only knows two fixed paths (the adapter's `dist/index.js` and
`canary.py`). Requirement 10.R11, design.md "Part 7: Claude Code over ACP", and the facts with links in
`adapters/NOTES-layer10.md` ("Claude Code over ACP").

Status (Nov 9 2026): parts 7a and 7b are built. agents.yaml accepts the agent, `umwayi agent check NAME`
runs every gate check below, and `umwayi agent chat NAME` runs the chat: it hands the adapter the layer 9
hook and the SessionStart canary (`canary.py`) in the inline settings of `session/new`, and sends nothing
you type until the canary has run in that session (at most 30 seconds, else exit 2). No real adapter has
been run yet (docs/KNOWN-LIMITS.md, items 59 and 65).

## Files

| file | what it is |
| --- | --- |
| `package.json` | private, one dependency with an exact version (no `^`, `~` or range) |
| `package-lock.json` | made once in the build pull request with `npm install --package-lock-only --ignore-scripts`; every package has a `sha512` integrity hash and comes from registry.npmjs.org |
| `canary.py` | standard library: the `SessionStart` canary hook. It writes one empty file named by its `--token` into its `--dir` (O_EXCL), prints nothing, and exits 2 on any bad argument |
| `.gitignore` | `node_modules/`, which is never committed |

## Before you install: Node.js 22 or later

```
node --version
```

It must print `v22.0.0` or later (the adapter's `engines` says `node >=22`, and umwayi checks it).

## The one install command (run it yourself, in this folder)

```
cd adapters/claude_acp
npm ci --ignore-scripts
```

umwayi never runs npm, npx or any installer. `npm ci` installs exactly what `package-lock.json` lists and
checks every integrity hash; it fails rather than change the lockfile. `--ignore-scripts` makes sure no
package runs an install script (none of the locked packages declares one, and the flag keeps it so).

What it installs, into `adapters/claude_acp/node_modules/`:

- the adapter `@agentclientprotocol/claude-agent-acp` 0.101.0;
- the Claude Agent SDK `@anthropic-ai/claude-agent-sdk` 0.3.318, which brings the Claude Code CLI
  2.1.318 as a native binary in one platform package. The lockfile lists 8 of them (darwin arm64 and
  x64; linux arm64 and x64, each also as musl; win32 arm64 and x64); they are optional, and npm installs
  only the one for your machine;
- their dependencies: 115 packages in the lockfile in all, among them `@agentclientprotocol/sdk`,
  `@anthropic-ai/sdk`, `@modelcontextprotocol/sdk`, `express`, `hono` and `zod`. Licences: MIT, ISC,
  Apache-2.0, BSD-2-Clause, BSD-3-Clause and Unlicense; the Claude Agent SDK says "SEE LICENSE IN
  README.md" and its 8 platform packages say "SEE LICENSE IN LICENSE.md".

The chat uses the Claude Code CLI bundled with the pinned SDK, not the `claude` on your PATH: umwayi
never passes `CLAUDE_CODE_EXECUTABLE` (approved answer 6).

## Sign in first, outside umwayi

umwayi uses only your existing Claude Code login. It never runs a login, never reads, copies or logs a
credential, and never passes `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` or `ANTHROPIC_BASE_URL` to the
adapter, even when they are set (approved answer 3). So sign in beforehand:

```
claude
/login
```

The bundled CLI finds the same login through the same `HOME` (and `CLAUDE_CONFIG_DIR`, if you set one).
umwayi checks it with `node .../dist/index.js --cli auth status --json` (part 7c-1, Nov 9 2026): within
15 seconds the answer must show a Claude subscription login (`loggedIn`, `authMethod` `claude.ai`, no
`apiKeySource`, `apiProvider` absent or `firstParty`, a plan word). Only those fields are read; your email
and organisation in the same output are never read, printed or logged.

## Check it

```
python -m umwayi agent check NAME
```

For a Claude Code agent with `transport: acp` this prints, in order, and stops at the first that fails
(exit 2): `node` on PATH; `node --version` at least 22; the adapter file
`node_modules/@agentclientprotocol/claude-agent-acp/dist/index.js` is a regular file and not a link;
its `package.json` has exactly the pinned name and version; `--version` prints exactly `0.101.0`;
`--cli --version` prints a Claude Code version of at least 2.1.295; sign-in; the layer 9 Claude Code
hook and its self-test. Each program runs with an argument list (no shell), a timeout, empty stdin and
an allow-listed environment. It starts no agent.

## Updating the pin

Change the version only in one pull request that updates all four together (approved answer 5):

1. `adapters/NOTES-layer10.md`: read the new version's README, `package.json`, registry entry and
   source, and record what changed (above all: install scripts, `--version`, `--cli`, how sign-in and
   hooks work, and the bundled Claude Code version).
2. `package.json`: the new exact version.
3. `package-lock.json`: in this folder, `npm install --package-lock-only --ignore-scripts` (it writes
   only the lockfile, no `node_modules`); review the diff, the integrity hashes and any
   `hasInstallScript`.
4. `CLAUDE_ACP_VERSION` in `umwayi/agents.py`.

A test checks that the version in `package.json`, the lockfile and `CLAUDE_ACP_VERSION` are equal. After
the merge, run `npm ci --ignore-scripts` here again.
