# Network reach and credentials for helpers (W69, design note)

## Purpose

This note designs how umwayi-os could limit what an AI helper can reach on the network, and which credentials it holds. The owner's reason (Nov 16): Felony Bench counts harm to third parties reported for frontier agents, and most of it went through credentials and the network. So a file system sandbox alone is not enough. That report is the owner's; it was not checked for this note.

umwayi-os runs with its own supervisor, so the note covers helpers started by the supervisor as well as by the owner. It is a design note only. No code, rule, steering file, safety check, workflow or exit code changes with it.

It reuses the terms of the W67 threat model (branch `w67-threat-model`: owner, supervisor, helper, tool output, other agents; "enforced" and "not enforced") and of the W68 note on untrusted content (branch `w68-untrusted-content`: an external read, Options 1 to 3). Neither branch is on main when this is written. The options build on the W41 design, [enforcement](enforcement.md): option A (a launcher with an allow-listed environment), B (OS confinement, B1 the platform's sandbox, B2 umwayi confines the process) and C (detect-after).

## Current state

### What a helper can reach today

- **The network: everything the owner's user can reach.**
  - umwayi sets no network limit on a helper.
  - umwayi's own core opens no network connection except two servers on 127.0.0.1: the telemetry receiver and `umwayi serve` (`tests/test_system.py` `CodeTests.test_no_module_imports_a_network_library`; KNOWN-LIMITS 125). That limits umwayi, not the helper.
  - A helper's shell commands are Ask me first in the starter rules. Web fetch and web search are Ask me first. MCP tools have no rule, so they are Ask me first too ([rules](rules.md)). The owner's own Yes rules can allow any of them.
  - The programs a checked command starts connect as they like (KNOWN-LIMITS 12; [enforcement](enforcement.md)).
  - OpenCode fetched `ripgrep` from the network by itself (KNOWN-LIMITS 191).
- **Cloud metadata addresses.** Nothing names `169.254.169.254` or any metadata host. On a cloud machine, a helper can ask it for the machine's credentials like any other address.
- **Credentials in the environment:**
  - Claude Code `agent run` and the cli chat get the owner's environment minus a fixed list: the Anthropic and Claude Code credential names (`agents.CLAUDE_CREDENTIAL_ENV`) and the telemetry names (`claude_env`).
  - Kiro gets the owner's environment minus `KIRO_API_KEY` (`kiro_env`; KNOWN-LIMITS 88).
  - So any `GITHUB_TOKEN`, `GH_TOKEN`, `AWS_*`, `SENTRY_*` or database address in the owner's shell reaches those helpers and every command they run.
  - The ACP chat (`child_env`) and OpenCode (`opencode_env`) get allow lists without them. The allow lists do pass the proxy and certificate names (KNOWN-LIMITS 63).
- **The owner's SSH agent** (`SSH_AUTH_SOCK`) reaches every helper on main. W64 removes it, on its branch.
- **Credentials on disk.** A helper runs as the owner's user and can read `~/.aws`, `~/.config/gh`, `~/.ssh` and `~/.netrc`. A tool call that names `.aws/credentials`, `.netrc`, `id_rsa` or `id_ed25519` is No for Claude Code (`cc-no-secrets`). A shell command or a program that reads them without naming them is not seen.
- **The owner's GitHub account.** In the builder's sandbox, the GitHub token is the owner's account (W63 design, branch `w63-merge-ready-design`). A helper there can act on GitHub as the owner.

## Options

### Option 1: a per-helper network allow list, through the launcher (W41 option A)

- **What.**
  - Each agent in `agents.yaml` gets `network:`, a list of host names (for example `api.anthropic.com`, `github.com`).
  - The launcher starts a small proxy on 127.0.0.1 for the run. It sets `HTTPS_PROXY` and `HTTP_PROXY` to it in the allow-listed environment of W41 A, and sets `NO_PROXY` to nothing.
  - The proxy allows a `CONNECT` only to a listed host on port 443, after resolving it, and refuses any other host.
  - It logs one entry at the end of the run with counts per listed host and the count refused, never a URL or a path.
- **What it cannot stop.**
  - A program that ignores the proxy names and opens its own socket. Without Option 2 the list is cooperative, like the hooks.
  - What is sent to an allowed host, for example data posted to `github.com`.
  - A listed host that is itself used to reach a third party (an API that sends mail or opens issues).
- **Cost.**
  - The proxy is network code in umwayi. Product rule 5 says no module of the core package imports a network library except two named exceptions, and `tests/test_system.py` allows only those two by file. A third one needs the owner's approval, by name, as the first two had.
  - A helper's vendor host must be on its list, or the helper cannot run at all.

### Option 2: OS-level egress limits (W41 option B)

- **What.** The helper process, and everything it starts, may open network connections only to the proxy of Option 1 on 127.0.0.1. Everything else is refused by the operating system. This is the shape Claude Code's own sandbox uses for its shell commands (B1; [enforcement](enforcement.md)).
- **Platform differences:**
  - **Linux:**
    - Landlock can limit TCP `connect` by port only, and only from ABI 4 (kernel 6.7 or later). It cannot name a host or an address. So it can allow only the proxy's port and refuse the rest. A different program on the same port is reachable.
    - A network namespace with no route out (as `bubblewrap` makes, with `socat` bridging to the proxy) refuses everything else by address. It needs user namespaces, which some distributions limit; on Ubuntu, AppArmor may need a profile, which needs root.
    - Firewall rules per user (`nftables`, `iptables`) need root. umwayi never uses root.
  - **macOS:** a Seatbelt profile can refuse outbound connections and allow one local address. `sandbox-exec` is marked deprecated by Apple, and its profile language is not documented by Apple. Whether a profile can allow a host by name was not checked for this note. CI runs on Linux only.
- **What it cannot stop.**
  - Traffic to the proxy, which Option 1 must judge.
  - A helper's own connection to its vendor, which must be allowed.
  - A Unix socket to another local program (a browser, a desktop agent, a database) that has network access, unless the profile also refuses those sockets.
- **Cost.** About the B2 cost of [enforcement](enforcement.md), with the same refusal rule: when the limit is asked for and cannot be set up, the start is refused (exit 2), never run open.

### Option 3: a ban on cloud metadata addresses

- **What:**
  - The proxy of Option 1 refuses any link-local address (`169.254.0.0/16`, `fe80::/10`) and `fd00:ec2::254`, whatever the host name resolves to.
  - A starter rule makes a tool call No when its command or URL names `169.254.169.254` or `metadata.google.internal`. This is text matching, a second line only.
  - With Option 2, the OS limit refuses those addresses for every process.
- **What it cannot stop.**
  - Without Option 2: a program that connects directly, or builds the address in a way the text rule does not see (KNOWN-LIMITS 12).
  - Credentials the machine exposes another way, such as a file or an environment variable set by the cloud's agent.
- **Cost.** Small for the proxy part. The rule part changes the starter rules, whose old rules are pinned by hash (`tests/test_starter_rules.py`), so it is the owner's decision.

### Option 4: short-lived scoped tokens, handed over once and never stored

- **What:**
  - The owner makes a token with the provider (for example a fine-grained GitHub token for one repository, with an expiry date), and gives it to one run when the run starts. `agent run NAME --token-name GH_TOKEN` reads the value once from a real terminal, without echo.
  - umwayi puts it in that run's environment only, under that one name. It never writes it to a file, a logbook entry or a queue row, and never prints it.
  - The run's entry says `token: GH_TOKEN given (value not kept)`.
  - With the allow-listed environment of W41 A, no other credential reaches the run.
- **What it cannot stop.**
  - Use of the token within its scope and its lifetime, including by any program the helper starts.
  - The helper sending the token somewhere. Option 2 limits where.
  - A provider whose scopes are wider than they look. The owner must check what a scope allows (for example whether a write scope also allows a merge), and umwayi cannot.
  - A real terminal check that a helper fakes with a pseudo-terminal (the W67 threat model).
- **Cost.** Small. The owner's work per run is real friction, which is the point.

### Option 5: detect-after in the logbook (W41 option C)

- **What.**
  - At the end of each run, one entry adds: the proxy's counts per host and refusals (Option 1); the network command words the hooks saw (`curl`, `wget`, `gh`, `ssh`, `git` with `push`, `fetch` or `clone`, the W55b command word); and the tool calls Claude Code reported with no check (W41 C2).
  - A refused metadata address or an unlisted host in a goal run moves the task to `needs owner` with a new cause word, for example `network_refused`.
- **What it cannot stop.** Anything, as it happens. It shows a connection after the run, and only one that went through the proxy or a hook. A direct connection without Option 2 is not seen.
- **Cost.** Small, with Option 1 in place. Without it, only the command words and telemetry are seen.

### How the options fit

Option 2 is what makes Option 1 hold. Option 1 is what makes Option 2 useful, because a helper with no network cannot reach its vendor. Option 3 is one line in Option 1's proxy and one in Option 2's limit. Option 4 is independent: it lowers what a stolen credential is worth. Option 5 records what the others saw.

The W68 note's Option 3 (an allow-listed `agent run` environment) is the same change as W41 A, and is the first step for Options 1 and 4.

## The tests each option needs

| option | rule | test | planted fault |
| --- | --- | --- | --- |
| 1 | only listed hosts | `test_proxy_refuses_an_unlisted_host_and_allows_a_listed_one` | compare the host as a suffix (`evilgithub.com`) |
| 1 | the run gets the proxy | `test_run_environment_points_to_the_proxy_and_no_proxy_is_empty` | keep the owner's `NO_PROXY` |
| 1 | counts only | `test_proxy_entry_has_counts_and_no_url` | log the path |
| 1 | the proxy is loopback only | the `tests/test_system.py` network guard extended by name | bind `0.0.0.0` |
| 2 | other connections refused (Linux CI with Landlock ABI 4) | `test_child_connect_to_another_port_is_refused` | apply the ruleset after `exec` |
| 2 | no limit, no start | `test_limit_unavailable_refuses_the_start` | start unlimited |
| 2 | macOS | the owner's by-hand steps with expected output | none in CI |
| 3 | link-local refused | `test_proxy_refuses_169_254_and_fe80_after_resolving` | check the name, not the address |
| 3 | the text rule | `test_metadata_address_in_a_command_is_no` | match only the IPv4 form |
| 4 | never stored | `test_token_value_is_in_no_file_entry_or_output` (a planted value swept from the root, TMPDIR and the output) | write it to the start entry |
| 4 | one name only | `test_token_reaches_only_that_run_under_that_name` | pass it to the next run |
| 4 | a real terminal | `test_token_needs_a_terminal_and_no_echo` | read it from an environment variable |
| 5 | the run entry | `test_detect_after_entry_names_hosts_and_command_words_only` | include an argument |
| 5 | a refusal stops the goal task | `test_network_refused_moves_the_task_to_needs_owner` | only log it |
| all | exit codes | rows in `tests/test_exit_codes.py` | a refused start exits 1 |

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-16 | Design note only. The environment allow list first (W41 A, W68 Option 3), then tokens handed over per run, then the proxy with an OS limit, with the metadata ban in both | W69, the owner's request of Nov 16. |

## Open questions

1. **Which option first?** Recommendation:
   - First, the allow-listed environment (W41 A), so no credential the owner did not name reaches a run, and Option 4 on top of it.
   - Then Options 1 and 2 together, because each alone is weak.
   - Option 3 inside them. Option 5 last.
2. **A third loopback server (the proxy).** Product rule 5 and `tests/test_system.py` name the two that exist. Recommendation: the owner approves the proxy by name, inside the launcher, with the same guard test as the telemetry receiver.
3. **Linux without Landlock ABI 4, or without user namespaces.** Recommendation: refuse the start when the owner asked for the limit, as W41 B does, and say which part is missing. Never fall back to an open network silently.
4. **macOS.** Recommendation: Option 2 on macOS only after the owner's by-hand check on each macOS version used, because `sandbox-exec` is deprecated. Until then macOS gets Options 1, 3, 4 and 5, and the run entry says `network limit: off`.
5. **Which hosts does each platform need?** Not recorded in the repo. Recommendation: record them from the owner's real runs in `adapters/NOTES-layer10.md` before any list is enforced, and start each agent's list from that record.
6. **The builder's GitHub account.** Recommendation: give helpers a fine-grained token for one repository with no merge right (Option 4), so that merging needs the owner's own session. This also answers W67 open question 6.
