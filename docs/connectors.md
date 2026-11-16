# Connectors (W72, design note)

## Purpose

This note designs how umwayi-os could connect to outside services without giving up its rules. The source is the owner's free integrations plan (project queue doc, sections F7 and F7a). That doc is not in this repo; its summary was given with the task.

It is a design note only. Nothing here is built, and no code, rule, steering file, safety check, workflow or exit code changes with it. It uses the terms of the W67 threat model, W68 untrusted content, W69 network and credentials, and W74 shared mode, on branches `w67-threat-model`, `w68-untrusted-content`, `w69-network-credentials` and `w74-multi-user`. None of those branches is on main when this is written.

## The rule for every connection

1. **A driver with one rules gate entry.**
   - A connection is a separate program under `connectors/NAME/`, outside the `umwayi` package, as the adapters are.
   - umwayi starts it with an argument list and no shell, only after one rules check: `{"type": "connector", "connector": NAME, "use": WORD}`, with `WORD` from that connector's fixed list.
   - No Yes rule exists for it until the owner writes one, so every use is Ask me first by default.
2. **A scoped credential the owner hands over once.** It is an environment variable or an OS keychain item, named in `connectors.yaml` by its name only. The connector reads the value at the moment of use. umwayi never stores, logs or prints it, and never asks for it in a prompt.
3. **A logbook entry per use,** with the connector, the use word, a count and the result word. Never a URL path, a message body, an address or a token.
4. **Opt in, off by default.** `connectors.yaml` lists each connector with `enabled: false` until the owner sets it. A missing file means no connector runs.
5. **The core stays at zero network.**
   - The network code lives only in `connectors/`, never in `umwayi/`.
   - The guard of `tests/test_system.py` (`CodeTests.test_no_module_imports_a_network_library`) and product rule 5 stay exactly as they are.
   - A new guard test checks that `umwayi/` imports nothing from `connectors/`.
6. **Fail closed.** Any of the following means the use did not happen, gives exit 3 and one entry:
   - a missing credential, a refused rule or a disabled connector;
   - a timeout, an HTTP error or a rate limit;
   - a reply that does not parse.

   umwayi never retries in a loop and never guesses that a send went through.

An identity provider sign-in (Google or GitHub) is for identity only (W74). It never holds or hands out a credential for GitHub, Vercel, Neon, a model provider or any connector below.

## Current state

What exists today, read at main `6525606`:

- **GitHub (read only, public).** `tools/board_status.py` reads the public GitHub REST API with `urllib`, no token and a timeout. It prints one line per open pull request (CI state, whether the branch has main, whether it is mergeable) and fails closed with exit 2. It is a tool for the guide, outside the package.
- **GitHub (CI).** `.github/workflows/ci.yml` runs the tests. `progress-page.yml` builds the progress page as an artifact only. umwayi itself never pushes or merges (`umwayi/goalgit.py`).
- **Vercel.** The public site in `site/` is on the Vercel free tier (design.md, UI-Q18). By `site/README.md`, the owner builds and deploys it, and nothing in the repo deploys or touches Vercel.
- **Scans.** OSV-Scanner, `npm audit` and Bandit were run by hand once, on 2026-11-10 (`docs/SECURITY-SCAN.md`). `npm audit` tells the registry the package list (KNOWN-LIMITS 131). The owner holds further scans for later (tasks.md). Jobs can run only `report`, `check` and `queue-list` (`umwayi/jobs.py` `ALLOWED_COMMANDS`), so no scan can be scheduled today.
- **MCP.** An MCP tool call reaches the gate as `tool_mcp` with `mcp_server` and `mcp_tool` (`adapters/common/umwayi_gate.py`). No starter rule allows one, so each is Ask me first.
- **Local models.** A local OpenCode provider (`umwayi-local`, a loopback or private `base_url`) is specified (10.R14) and its confirmation steps are open (tasks.md 10.52 and after).
- **Sandbox tools.** Designed in W41 ([enforcement](enforcement.md): `bubblewrap`, `socat`, Landlock, Seatbelt), not built.
- **Keychain.** Claude Code keeps its login in the macOS Keychain (`adapters/NOTES-layer10.md`). umwayi reads no keychain.
- **Not present at all:** email, push, Notion, Sentry, Neon, a demo backend and a secret store client.

## The connections

"Free tier limits to check on the day" lists what to read before building. It states no number that was not read for this note.

### GitHub: pull requests, check status, merge

- **Purpose.** The supervisor reads the state of pull requests and checks. Merge stays the owner's.
- **Gate entry.** `connector github` with the uses `pr_list`, `pr_view`, `checks`, all read only. `merge` is not a use: umwayi never merges (W9.R23).
- **Credential.** None for a public repo (as `tools/board_status.py` does today). Otherwise a fine-grained token for one repository with read rights only (W69 option 4), named in `connectors.yaml`.
  - In the builder's sandbox, the `gh` CLI holds the owner's full account (W63 design, branch `w63-merge-ready-design`). So "read only through `gh`" would be read only by argument list, not by scope. A read-only token is the real limit.
- **Data that leaves.** Requests for the repository's pull requests and check runs.
- **Failure.** As `tools/board_status.py`: any error, rate limit or odd field is exit 3 and one line, never a half result.
- **Free tier to check on the day.** The REST rate limit for unauthenticated and for token requests.

### CI done notification

- **Purpose.** Tell the owner when the `result` check of a pull request ends.
- **Design.** Local: the GitHub connector polls `checks` at a fixed interval, and on a change calls the email or push notifier. No change to `.github/workflows/`. A workflow step that sends a message would need a secret in GitHub and a workflow change, both the owner's.
- **Gate entry.** The GitHub read use, then the notifier's own entry.
- **Failure.** A poll that fails sends nothing and says so in its entry.

### Vercel Hobby for the pages

- **Purpose.** The site and the read-only pages.
- **Gate entry.** `connector vercel` with `deploy`, Ask me first always: no starter rule may make it Yes, as `publish` is on the never list (`umwayi/rules.py` `NEVER_AUTONOMY`; `deploy` would be added).
- **Credential.** A Vercel token for one project, if the deploy is ever run by umwayi. Today the owner deploys and umwayi does not.
- **Data that leaves.** The built site, which holds none of the owner's data ([what it is and is not](what-it-is.md)).
- **Failure.** A failed deploy leaves the old one. umwayi says so and does not retry.
- **Free tier to check on the day.** Vercel Hobby's terms of use and its build and bandwidth limits.

### Neon serverless Postgres, an optional store later

- **Purpose.** The shared store of W74 (branch `w74-multi-user`). It is later and off by default; the file stays the default.
- **Gate entry.** Not a connector use per call. The store interface is chosen by the owner in the config, and a hosted store needs the owner's change to product rule 5 (W74).
- **Credential.** A database role that may only insert and select, in the server's environment.
- **Data that leaves.** Logbook rows (ids, words, counts, the chain).
- **Free tier to check on the day.** Neon's Free plan storage per project and project count. The W74 note read 1 GB per project and up to 100 projects on Nov 16. Read them again before building.

### A free host for a read-only demo backend

- **Purpose.** Let a visitor try the read routes on sample data. This is W72d, a plan only.
- **Design.** The demo runs `umwayi serve` on a sample root with no owner data, behind the host's TLS.
  - The local gate assumes 127.0.0.1 (W74). A demo on a host needs its own front, with read routes only, no token of the owner's and a rate limit.
  - No write route and no agent start.
- **Gate entry.** `connector demo` with `deploy`, Ask me first always.
- **Data that leaves.** The sample root only.
- **Free tier to check on the day.** The chosen host's limits on hours, sleep, bandwidth and its terms. No host is chosen here.

### Email notifier, through the owner's own mailbox (W72b)

- **Purpose.** One short message to the owner: a task needs them, a run ended, CI ended.
- **Design.**
  - `smtplib` (standard library) inside `connectors/email/`, with `SMTP_SSL` or `STARTTLS` required. A server that does not offer TLS is refused.
  - From and to are both the owner's own address. There is one recipient and no other.
  - Fixed templates only. A subject such as `umwayi: G-0007 T-02 needs you` holds ids and words. It never holds a path, a command, a rule text, helper output or a secret.
- **Gate entry.** `connector email` with `notify`. Graded autonomy can never move it, because `send` is on the never list.
- **Credential.** The mailbox's app password, by name in `connectors.yaml` (an environment variable or a keychain item).
- **Data that leaves.** The message, to the owner's own mail provider.
- **Failure.** No TLS, a login refused or a timeout: exit 3, one entry, no retry loop.
- **Free tier to check on the day.** The mail provider's sending limits and its app password rules.

### A free push service such as ntfy (W72e)

- **Purpose.** The same messages as email, to the owner's phone.
- **Design.**
  - One HTTPS `POST` to the owner's topic, with the same fixed templates.
  - No path, command or secret is ever in a message.
  - On a public server, anyone who knows the topic name can read it, so the topic name is treated as a credential.
- **Gate entry.** `connector push` with `notify`.
- **Credential.** The topic name, and an access token if the server has one, by name.
- **Data that leaves.** The message, to the push server.
- **Free tier to check on the day.** The server's message limits, retention and whether a topic can be protected.

### Notion, an opt-in status mirror

- **Purpose.** A page that shows the counts of `goal status`.
- **Gate entry.** `connector notion` with `mirror`.
- **Credential.** An integration token shared with one page only.
- **Data that leaves.** Counts and ids, the same as the snapshot ([interface](interface.md)), never a goal text or helper output.
- **Failure.** The mirror is left as it was, with a "last updated" time.
- **Free tier to check on the day.** Notion's API rate limit and plan rules for integrations.

### An error monitor such as Sentry

- **Purpose.** Opt in only, for umwayi's own crashes.
- **Conflict.** [What it is and is not](what-it-is.md) says "no telemetry sent anywhere" (line 26). Sending crash reports ends that, so the line must change in the same pull request.
- **Injection surface.** Reading error events through an MCP server is the attack of the W68 note (branch `w68-untrusted-content`). The connector would only send, never read events back into a helper.
- **Gate entry.** `connector errors` with `report`.
- **Data that leaves.** The exception type and the umwayi file and line, never the message text, a path of the owner's or an argument.
- **Free tier to check on the day.** The monitor's event quota and data retention.

### MCP servers, each approved once

- **Purpose.** A tool a helper uses through its platform.
- **Gate entry.** A tool call is already `tool_mcp` with `mcp_server` and `mcp_tool`. The owner approves a server once with a Yes rule naming that server and its tools.
  - The approval is bound to the server's command and arguments by a hash, as the W43 app manifests are (branch `w43-agent-apps-design`).
  - A changed server needs a new approval.
- **Data that leaves.** Whatever the server sends; it is outside umwayi. Its results are untrusted content (W68).
- **Failure.** No approval: Ask me first, as today.

### Secret stores

- **Purpose.** Where a connector's credential can live.
- **Design.** Read by item name only:
  - macOS: `security find-generic-password -s NAME -w`;
  - Linux: `secret-tool lookup service NAME`.

  Each is started with an argument list. The value goes to the connector's memory only.
- **Not built:** any write. umwayi never creates or changes an item.
- **Failure.** A missing item or a locked store: exit 3, nothing sent.

### OSV, npm audit and pip-audit on umwayi's schedule

- **Purpose.** The dependency scans of S.2, on a timer.
- **Design.** A new job command word, `scan`, that starts a connector program running one fixed scan. Its result is a count per severity, written as one entry and a draft.
- **Data that leaves.** `npm audit` sends the package list to the registry (KNOWN-LIMITS 131), and pip-audit queries an advisory service. OSV-Scanner offline needs one database download.
- **Gate entry.** `run_job` as for every job, then `connector scan` with `npm`, `pip` or `osv`.
- **Failure.** A tool that is missing or fails: a count of `unknown`, never "no finding".

### Local models and sandbox tools

- **Local models.** An OpenCode provider with a loopback or private `base_url` (10.R14) is already designed and is not a connector: no data leaves the machine.
- **Sandbox tools.** `bubblewrap`, `socat` and the OS confinement of W41 are local tools that umwayi checks for and never installs ([enforcement](enforcement.md)).

## The order of builds

1. **W72b, the email notifier.** Standard library only, one recipient, fixed templates. It also gives the CI done notification a channel.
2. **W72c, the GitHub read-only connector.** It starts from `tools/board_status.py`, moved under `connectors/github/`, with a read-only token when the repo is private.
3. **W72d, the demo deploy plan.** A plan, with the host chosen on the day and checked against its terms.
4. **W72e, the push notifier.**

Each is its own task and pull request, after the owner answers the open questions.

## The tests each connection needs

| rule | test | planted fault |
| --- | --- | --- |
| off by default | `test_no_connectors_yaml_means_no_connector_runs` | default `enabled: true` |
| one gate entry per use | `test_each_use_asks_the_rules_once_before_the_program_starts` | start before the check |
| core stays at zero network | `test_umwayi_imports_nothing_from_connectors` and the network guard unchanged | import `connectors.email` in `umwayi/` |
| credential never kept | `test_a_planted_credential_is_in_no_file_entry_or_output` | log the value |
| entry per use, words only | `test_connector_entry_has_ids_counts_and_no_body` | log the subject line's address |
| fail closed | `test_timeout_http_error_and_rate_limit_are_exit_3` | return 0 on a timeout |
| email TLS only | `test_email_refuses_a_server_without_tls` (a local fake SMTP server) | fall back to plain text |
| email one recipient | `test_email_sends_only_to_the_owner_address` | accept a second address |
| fixed templates | `test_no_path_command_or_secret_in_any_message` | put the cause text in the body |
| GitHub read only | `test_github_connector_sends_only_get` | allow `PUT` for merge |
| deploy always asks | `test_deploy_is_on_the_never_list_and_never_yes` | allow a Yes rule for deploy |
| MCP bound to a hash | `test_a_changed_mcp_server_needs_a_new_approval` | compare the name only |
| scans say unknown | `test_a_missing_scan_tool_is_unknown_not_clean` | report zero findings |
| exit codes | rows in `tests/test_exit_codes.py` | a refused use exits 1 |

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-16 | Design note only. Every connector is a driver outside the package, with one gate entry, a credential by name, an entry per use, off by default, fail closed; the order is W72b, W72c, W72d, W72e | W72, the owner's free integrations plan (F7, F7a). |

## Open questions

1. **Where do connectors live?** Recommendation: `connectors/NAME/`, outside `umwayi/`, as the adapters are, so the core's network guard and product rule 5 stay as they are. Product rule 9 (standard library in the core) then also stays.
2. **The never list.** Recommendation: add `deploy` and `connector` to `NEVER_AUTONOMY` in the same change that builds the first connector. A message, a deploy and a report out are never moved to Yes by graded autonomy.
3. **CI done: local poll or a workflow step?** Recommendation: a local poll, so no secret goes to GitHub and no workflow changes.
4. **The GitHub token.** Recommendation: no token for the public repo, as today. A fine-grained read-only token for one repository when it is private. Never the `gh` login of the owner's full account.
5. **An error monitor.** Recommendation: not now. It ends "no telemetry sent anywhere". If wanted later, send the exception type and umwayi's own file and line only.
6. **ntfy on a public server.** Recommendation: a self-hosted server or a protected topic. A public topic is readable by anyone who guesses its name.
