# Local backend (W6): `umwayi serve`

## Purpose

`umwayi serve` lets the owner's web page send the same request the command line would, to a small server on the owner's own machine. It exists so the page can show the queue and, later, host a chat with an AI helper and an intake step, without the page ever having a second set of rules: every request meets the same rules check, the same logbook and the same kill switch as the command, by calling the same code.

## Current state

**Specified, not built.** This page was written in the W6.0 pull request (Nov 12 2026, docs and specs only). Nothing below exists in `umwayi/`, `ui/` or `site/` yet. It is made current in each build pull request ([tasks.md](../.kiro/specs/umwayi-os/tasks.md), W6.1 to W6.10). The spec: [requirements W6.R1 to W6.R18](../.kiro/specs/umwayi-os/requirements.md), [design "Local backend (W6)"](../.kiro/specs/umwayi-os/design.md), the browser facts in [NOTES-w6.md](../adapters/NOTES-w6.md). The owner approved the change of rule on Nov 12 2026; the spec itself waits for the owner's approval.

### The rule

The page may send the same request the command line would, to a local backend and to nothing else (steering rule 10). The page still never writes to the repo or runs a command by itself. Until `umwayi serve` is built, the page makes no request at all. The public site sends nothing to any backend.

### The commands

```
umwayi serve [--port N] [--page PATH]
umwayi serve token create [--days N]
umwayi serve token rotate [--days N]
umwayi serve token revoke
umwayi serve token status
```

- `umwayi serve` runs in the foreground. It binds the literal address 127.0.0.1 (no flag, setting or variable changes it), default port 8765, and serves the built page `ui/dist/index.html` from the same origin when its SHA-256 matches `ui/dist/build.json`.
- It starts only after: the arguments, the logbook tamper check, a valid token, the lock `.umwayi/serve.lock`, and the bind. One logbook entry says it started.
- The token is 48 characters (`umt1_` and 43 of base64url), shown once on a terminal by `create` or `rotate`, and kept only as a SHA-256 in `.umwayi/serve.token` (mode 0600). It lives 30 days by default, 90 at most. The page keeps it in memory and sends it as `Authorization: Bearer`. No route handles a token; only the command line does.

### Every request, in order

1. The gate, a pure function: protocol, peer, headers (no duplicates of the ones that matter), `Host` exactly `127.0.0.1:PORT`, the target, the token, `Origin` exactly `http://127.0.0.1:PORT` (required on `POST` and `DELETE`), the route, the body, the rate.
2. The kill switch (`kill.state`). A write or run route is refused while it is `on` or `unknown`.
3. The rules check (`rules.check_and_log`) with the action `{"type": "serve_request", "route": ID, "class": CLASS, "platform": "web"}`. With no rule the answer is Ask me first. Only `kill.on` skips it.
4. The route's core function, the one the command line calls.
5. One logbook entry for the request: route, outcome, exit code, milliseconds. Never the body, a header, the token or a path.

There is no CORS and no cookie. A request without a valid token is counted, not logged one by one; a summary entry is written at most once a minute.

### The routes (first set)

| id | request | the command line | core functions called | class | stopped by the kill switch | exit codes as the command | body cap |
| --- | --- | --- | --- | --- | --- | --- | --- |
| page | `GET /` | none (the built page) | none | page | no | none | 0 |
| status | `GET /v1/status` | `kill status` | `kill.state`, the token record | read | no | 0 | 0 |
| snapshot | `GET /v1/snapshot` | `view snapshot`, without the file | `logbook.read_checked_chain`, `view.gather` | read | no | 0, 1, 2 | 0 |
| queue.list | `GET /v1/queue?status=&kind=` | `queue list` | `taskqueue.list_rows` | read | no | 0, 1, 2 | 0 |
| logbook.verify | `GET /v1/logbook` | `logbook verify` | `logbook.verify` | read | no | 0, 1 | 0 |
| budget.status | `GET /v1/budget` | `budget status` | `budget.status` | read | no | 0, 2, 3, 64 | 0 |
| agents.list | `GET /v1/agents` | `agent list` | `agents.load` | read | no | 0, 2, 64 | 0 |
| agents.check | `POST /v1/agents/{name}/check` | `agent check NAME` | `agents.check_agent` | run | yes | 0, 2, 3, 64 | 64 |
| queue.add | `POST /v1/queue` | `queue add [--if-not-open]` | `taskqueue.add`, `taskqueue.add_once` | write | yes | 0, 1, 2, 64 | 4096 |
| queue.answer | `POST /v1/queue/{id}/answer` | `queue answer` | `taskqueue.answer` | write | yes | 0, 1, 2, 64 | 4096 |
| queue.close | `POST /v1/queue/{id}/close` | `queue close` | `taskqueue.close` | write | yes | 0, 1, 2, 64 | 64 |
| kill.on | `POST /v1/kill/on` | `kill on` | `kill.turn_on` | write | never (it is the switch) | 0, 1, 2, 64 | 512 |

Specified for later, each in its own spec (workstreams W4 and W5, not built): the chat routes `chats.start`, `chats.list`, `chats.events` (a long poll), `chats.message`, `chats.permission`, `chats.cancel` and `chats.stop`; and the intake routes `intake.start`, `intake.get`, `intake.answer`, `intake.commit` and `intake.discard`. The intake step asks fixed questions until a pure function says the intent is clear, and adds a queue row only when the owner commits what was shown.

A response is a subset of what the command prints. `agents.list` sends the name, platform and transport and no path.

### What the page may never do

No route, hidden parameter or body field can: turn the kill switch off; touch a token; edit `rules.yaml`, `autonomy.yaml`, `agents.yaml`, the budget limits, a schedule, `umwayi.json`, a job, a workflow, memory or the archive; approve or publish (`publish-draft`, `--approved-by`); run a job, workflow, helper or non-interactive agent; log in to a platform; seal, recover or anchor the logbook; settle or calibrate the budget; take a path, a command line, an environment variable, a URL or an upload. Adding a route needs the owner's approval and a row in this table.

### The words and codes

`umwayi serve` exits 0 (stopped cleanly), 1 (the logbook failed its tamper check, nothing started), 2 (an unexpected error), 64 (usage or config); never 3. A response is `{"schema": 1, "ok", "code", "word", "request", "logged", "data"}`. The `code` is the exit code the command would give. The words are `done`, `refused`, `usage`, `error`, `ask`, `kill`, `budget`, `rules`, `logbook`, `busy`, `page`, `body` and the gate words `method`, `peer`, `header`, `host`, `target`, `token`, `origin`, `route`, `length`, `type`, `rate`. A gate refusal is the same bytes for the same word.

### Limits (proposed numbers)

16 requests at once (the 17th gets 503), 4 long polls, 10 requests a second overall (burst 30), 5 token failures a minute then 429, a 10 second request deadline, a 25 second long poll, bodies at most 9000 bytes, responses at most 1 MB and 500 queue rows, a chat stopped after 10 minutes with no request, a permission request rejected after 300 seconds, 6 chat starts an hour.

### How it is tested

Property based tests of the gate with seeded generators and no outside package, an oracle written separately from the text of the requirement, a catalogue of at least 45 single faults that must each be refused, and an enumerated table of `Host`, `Origin` and fetch metadata. A live server is fuzzed and flooded. Each route is run through the command line and through a request on identical roots and the bytes compared. A mutation pass of at least 40 mutants. A by-hand pass in a headless browser, with results in [NOTES-w6.md](../adapters/NOTES-w6.md). Details: requirement W6.R16.

### Known limits

Written now as expected limits, numbered 196 onward in [KNOWN-LIMITS.md](KNOWN-LIMITS.md); the build confirms or corrects them. The main ones: a process of the same user that learns the token is the owner as far as the backend can tell; no TLS on loopback; any local process can use up the 16 request slots; a request changes real files exactly as the command line does.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-12 | The rule changes from "the interface only looks" to "the page may send the same request the command line would, to a local backend". The command is `umwayi serve`, bound to 127.0.0.1 only, with a token. Every request meets the same rules check, logbook and kill switch by calling the same code. Fail closed. The core stays standard library only. Steering rule 10 and requirement 12.R17.6 carry the wording. | The owner, Nov 12 2026, approved. |
| 2026-11-12 | The rest of the design (every request rules-checked, writes stopped by the kill switch, the page served by the backend, `Origin` required on `POST`, reads logged, summary entries for requests with no valid token) are my readings of that decision and are open as W6-Q2, Q3, Q6, Q8, Q10 and Q11. | The words left room; proposed answers in design.md. |

## Open questions

W6-Q1 to W6-Q27 in [design.md](../.kiro/specs/umwayi-os/design.md) ("Open questions for the owner (W6-Q1 to W6-Q27)"), each with a proposed answer. The ones that change the most:

- W6-Q1: are W4 the chat, W5 the queue with intake, W6 this backend and W7 the login for a deployed interface? The repo does not define the names.
- W6-Q2 and W6-Q3: does every request get a rules check, and is every write stopped by the kill switch (stricter than the command line)? Can the page never turn the switch off?
- W6-Q4: may `serve token create` print the token once, against rule 2 ("never print secrets")?
- W6-Q12: may the page answer an Ask me first inside a chat?
- W6-Q17: may W6.7 and W6.8 change `agents.py` and `budget.py` (no change of behaviour, goldens first)?
- W6-Q19: rule 5 already says no core module imports a network library, which `umwayi/telemetry.py` contradicts today; reword it?
- W6-Q22: should a deployed page ever control a local one, and may queue or chat text pass a third party (W7)?
- W6-Q27: about 61 hours for the core and 13 for the two refactors, none in the schedule. The owner sets the dates and what is cut first.
