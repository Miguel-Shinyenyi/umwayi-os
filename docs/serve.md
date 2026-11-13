# Local backend (W6): `umwayi serve`

## Purpose

`umwayi serve` lets the owner's web page send the same request the command line would, to a small server on the owner's own machine. It exists so the page can show the queue and, later, host a chat with an AI helper and an intake step, without the page ever having a second set of rules: every request meets the same rules check, the same logbook and the same kill switch as the command, by calling the same code.

## Current state

**Built:** the core (W6.1 to W6.6, Nov 12 2026, one pull request): the gate (`umwayi/servegate.py`), the token (`umwayi/servetoken.py` and `umwayi serve token`), the server and the pipeline (`umwayi/serve.py`), the page and the eleven routes below, with `tests/serve/`; the page client and its panel (W6.9, Nov 12 2026: `ui/src/api/client.js` and `ui/src/ui/backend.js`); and, in W6.10, these docs, the whole-system scenarios (`tests/serve/test_scenarios.py`), the planted faults and the mutation pass (`tests/serve/faults.py`, `tests/serve/mutation_cli.py`). **Not built:** the chat routes (W4), the intake routes (W5) and the two refactors the chat needs (W6.7 and W6.8, which wait for W4). **Not done:** the by-hand pass in a real browser ([below](#the-by-hand-browser-pass-the-owners)). No browser was started for any of the W6 work, so every statement about browser behaviour comes from documentation or from Node and Python clients that send what a browser sends. The spec: [requirements W6.R1 to W6.R18](../.kiro/specs/umwayi-os/requirements.md), [design "Local backend (W6)"](../.kiro/specs/umwayi-os/design.md), the browser facts (read, not yet tried) in [NOTES-w6.md](../adapters/NOTES-w6.md), the tasks in [tasks.md](../.kiro/specs/umwayi-os/tasks.md). The owner approved the change of rule on Nov 12 2026 and answered W6-Q1 to W6-Q28 the same day.

### The rule

The page may send the same request the command line would, to a local backend and to nothing else (steering rule 10). The page still never writes to the repo or runs a command by itself. The page client (W6.9) is merged: served by `umwayi serve`, the page sends requests only through `ui/src/api/client.js`, only to the origin it came from, and only after the owner pasted the token. Opened from disk it makes no request. The public site sends nothing to any backend.

### Start it, in five steps

1. **Make a token** (once, in a terminal; it is shown once and never to a pipe or a file): `umwayi serve token create`. Copy the line that starts `umt1_`. It lives 30 days (`--days N`, at most 90). `umwayi serve token status` shows the id and the days left; `rotate` makes a new one and `revoke` removes it.
2. **Say what the page may do** (needed for writes): with no rule, every request gets Ask me first. Copy the lines you want from [serve.rules.example.yaml](../serve.rules.example.yaml) into `rules.yaml`: Yes for the read routes, Ask me first for every write and run route, nothing for `kill.on`.
3. **Start the server**, in the foreground: `umwayi serve`. It prints `Listening on http://127.0.0.1:8765` (`--port N` for another port, `--port 0` for a free one), the token's id and days left, and `(page not served)` when `ui/dist/index.html` does not match `ui/dist/build.json`. Stop it with Ctrl-C.
4. **Open the page** at that address, `http://127.0.0.1:PORT/` (not `localhost` and not another address: the server refuses them). Find "Local backend", paste the token into the password field and press "Use token". The field empties at once. The page keeps the token in memory only; a reload forgets it and you paste it again.
5. **Look and ask.** The section shows the kill switch, the days left on the token and the queue. You can Refresh, add an item, Answer or Close one, and press Stop everything. Nothing is sent without a token and nothing is asked by itself (there is no polling).

### What it refuses

A request is refused, with a fixed word and no detail, when it:

| the request | the word (HTTP status) |
| --- | --- |
| uses a method other than `GET`, `POST` or `DELETE` (so `OPTIONS` and `HEAD` too), or a version other than HTTP/1.0 and 1.1 | `method` (405) |
| does not come from 127.0.0.1 to 127.0.0.1 | `peer` (403) |
| has a repeated header that matters, `Transfer-Encoding`, `Expect`, `Upgrade`, a proxy header, more than 64 headers or a value over 4096 bytes | `header` (403) |
| names any `Host` but exactly `127.0.0.1:PORT` (`localhost`, another port, another address): this stops a page on another site from reaching the server through DNS rebinding | `host` (403) |
| has a target with `%`, `..`, `//`, a backslash, `;`, `#`, a non-ASCII character, or over 512 characters, or a query value that is not 0 to 16 of `a-z0-9_-` | `target` (403) |
| has no token, a wrong one, an expired one or a revoked one (five failures a minute lock out the failures, never a valid token) | `token` (401), then `rate` (429) |
| is a `POST` without `Origin: http://127.0.0.1:PORT`, or has another `Origin`, or fetch metadata that says cross-site | `origin` (403) |
| asks for a path that is not in the table | `route` (404) |
| has no `Content-Length` on a `POST`, or one that is too big for the route, or a body on a `GET` | `length` (411, 413) |
| is not JSON | `type` (415) |
| has a body that is not exactly the route's fields (unknown key, duplicate key, wrong type, a float) | `body` (400) |
| comes too fast | `rate` (429) |
| asks for a write or run route while the kill switch is on or unknown | `kill` (403) |
| meets a rule that says No, or Ask me first | `rules`, `ask` (403) |

It also never: sends an `Access-Control-` header or a cookie, binds any address but 127.0.0.1, turns the kill switch off (no route does), or handles a token (only the command line does). A refusal before a valid token is counted, not logged one by one.

### The commands

```
umwayi serve [--port N] [--page PATH]
umwayi serve token create [--days N]
umwayi serve token rotate [--days N]
umwayi serve token revoke
umwayi serve token status
```

- `umwayi serve` runs in the foreground until Ctrl-C or SIGTERM. It binds the literal address 127.0.0.1 (no flag, setting or variable changes it, and the socket is read back after the bind), default port 8765, `--port 0` for a free one. It serves the built page `ui/dist/index.html` from the same origin only when its SHA-256 equals the one in `ui/dist/build.json`, it is a regular file of at most 2.5 MB and nothing on the way is a link; otherwise `GET /` is 503 `page` and the start line says "page not served".
- It starts only after, in this order: the arguments (64), the root, the logbook tamper check (1), a valid token that has not expired (64), the lock `.umwayi/serve.lock` (64, one server per root), the bind (64). Then one logbook entry, and the line `Listening on http://127.0.0.1:PORT` on standard output, then the token's id and days left (a warning at 7 or fewer), and a hint when no rule matches a `serve_request` ([serve.rules.example.yaml](../serve.rules.example.yaml)).
- The token is 48 characters (`umt1_` and 43 of base64url), shown once on a terminal by `create` or `rotate` (never to a pipe or a file), kept only as a SHA-256 in `.umwayi/serve.token` (mode 0600, git-ignored). It lives 30 days by default, 90 at most, and is judged on the later of the system date and the newest logbook date. The page keeps it in memory and sends it as `Authorization: Bearer`. No route handles a token; only the command line does. A rotation or a revoke is seen by a running server on the next request.

### Every request, in order

1. The gate, a pure function: protocol, peer, headers (the ones that matter at most once, none that smuggle), `Host` exactly `127.0.0.1:PORT`, the target, the token (and a lock-out after 5 failures a minute), `Origin` exactly `http://127.0.0.1:PORT` (required on `POST` and `DELETE`), the route, the body length and type, the rate.
2. The body, parsed against the route's closed schema (UTF-8, one JSON object, no duplicate key, no unknown key, no float).
3. The kill switch (`kill.state`). A write or run route is refused (`kill`) while it is `on` or `unknown`.
4. The rules check (`rules.check_and_log`) with the action `{"type": "serve_request", "route": ID, "class": CLASS, "platform": "web"}`. With no rule the answer is Ask me first, and one decision is added to the queue. Only `kill.on` skips it. `serve_request` can never be moved to Yes by graded autonomy.
5. The route's core function, the one the command line calls.
6. One logbook entry for the request: route, outcome, exit code, milliseconds. Never the body, a header, the token or a path.

There is no CORS and no cookie. A request without a valid token is counted, not logged one by one; a summary entry is written at most once a minute and at shutdown. A request that cannot be logged is not reported as done: the server goes into a degraded state and answers only the status, the page and `kill.on` until the logbook can be written again.

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
| queue.add | `POST /v1/queue` | `queue add [--if-not-open]` | `taskqueue.add_row` (`add`, `add_once`) | write | yes | 0, 1, 2, 64 | 4096 |
| queue.answer | `POST /v1/queue/{id}/answer` | `queue answer` | `taskqueue.answer` | write | yes | 0, 1, 2, 64 | 4096 |
| queue.close | `POST /v1/queue/{id}/close` | `queue close` | `taskqueue.close` | write | yes | 0, 1, 2, 64 | 64 |
| kill.on | `POST /v1/kill/on` | `kill on` | `kill.turn_on` | write | never (it is the switch) | 0, 1, 2, 64 | 512 |

In a chat the page can only reject an Ask me first (`chats.permission` accepts `reject_once` and nothing else); an approval is made at the console of `umwayi serve` with the prompt `Allow once? [y/N]`, and with no terminal attached the request is rejected (W6-Q12 and W6-Q28, both answered Nov 12). Specified for later, each in its own spec (workstreams W4 and W5, not built): the chat routes `chats.start`, `chats.list`, `chats.events` (a long poll), `chats.message`, `chats.permission`, `chats.cancel` and `chats.stop`; and the intake routes `intake.start`, `intake.get`, `intake.answer`, `intake.commit` and `intake.discard`. The intake step asks a fixed list of questions until a pure function says the intent is clear, with no model, and adds a queue row only when the owner commits what was shown; an intake written by an AI helper is an option for the W5 spec (W6-Q15).

A response is a subset of what the command prints. `agents.list` sends the name, platform and transport and no path; `agents.check` sends the name and mark of each gate check and no detail; `queue.list` sends at most 500 rows with `id`, `kind`, `status`, `answered`, `title`, `recommendation` and `answer`.

### What the page may never do

No route, hidden parameter or body field can: turn the kill switch off; touch a token; edit `rules.yaml`, `autonomy.yaml`, `agents.yaml`, the budget limits, a schedule, `umwayi.json`, a job, a workflow, memory or the archive; approve or publish (`publish-draft`, `--approved-by`); run a job, workflow, helper or non-interactive agent; log in to a platform; seal, recover or anchor the logbook; settle or calibrate the budget; take a path, a command line, an environment variable, a URL or an upload. Adding a route needs the owner's approval and a row in this table.

### The words and codes

`umwayi serve` exits 0 (stopped cleanly), 1 (the logbook failed its tamper check, nothing started), 2 (an unexpected error), 64 (usage or config); never 3. A response is `{"schema": 1, "ok", "code", "word", "request", "logged", "data"}`. The `code` is the exit code the command would give. The words are `done`, `refused`, `usage`, `error`, `ask`, `kill`, `budget`, `rules`, `logbook`, `busy`, `page`, `body` and the gate words `method`, `peer`, `header`, `host`, `target`, `token`, `origin`, `route`, `length`, `type`, `rate`. A gate refusal is the same bytes for the same word and names no request.

### Limits

16 requests at once (the 17th gets 503 `busy`), 10 requests a second overall (burst 30; read 5 a second burst 20, write 2 burst 6, run 1 burst 3), 5 token failures a minute then 429, a 5 second read and a 10 second request deadline, bodies at most 4096 bytes (512 for `kill.on`, 64 for a check or close), a 5 second wait for a write, responses at most 1 MB. Chat limits (a long poll, an idle stop, a permission wait) come with the chat routes.

### How it is tested

`tests/serve/`, standard library only: property tests of the gate with seeded generators (5000 cases for each of three fixed seeds and one drawn per run, `UMWAYI_PROP_N`), an oracle written separately from the text, a catalogue of named single faults that must each be refused with the right word, an enumerated table of `Host`, `Origin` and fetch metadata; real child processes for the wire (a fuzz of 5000 byte strings, a slow request, 100 connections at once, the bind read from `/proc/net/tcp`); each route run through the command line and through a request on identical roots with the bytes compared; spies for the order of the steps; every row of the fail closed table.

W6.10 added three more things, all in `tests/serve/`:

- **Whole-system scenarios** (`test_scenarios.py`): `umwayi serve` as a real child process, with `HOME` in a temporary folder, and a client that sends what the page client sends (Python's `http.client`, and the real `ui/src/api/client.js` run by Node, which is skipped when Node is missing). They cover the token lifecycle (create, start, rotate and revoke while it runs, create again), a wrong, missing or expired token, a wrong `Host` or `Origin`, the kill switch turned on in the middle of a run and every route and body that might turn it off, the queue (add, answer, close, and the same queue seen at the command line), a SIGKILL and a restart, the logbook entries (one per request with a valid token, none for the others, no body, header or token), nothing written outside the root (the home folder, a sibling folder, the checkout) and loopback only (`/proc/net/tcp`, every other address of the machine refused).
- **Planted faults and a mutation pass** (`faults.py`, `mutation.py`, `mutation_cli.py`, `test_mutation.py`). `faults.py` lists 96 small faults in `servegate.py` (38), `serve.py` (33), `servetoken.py` (11) and `client.js` (14): one or more for each fault of W6.R16.10 (35 in all), and the rest are extra. `python -m tests.serve.mutation` copies the tree to a throwaway folder, applies one fault to the copy (never to the real tree, which is hashed before and after), checks that it still compiles, runs only the tests named for it with a time limit (a hang counts as caught), and prints planted, caught and survived with a reason for each survivor. Every test it uses must pass on the unchanged copy first. A run takes about 25 minutes, so it is run by hand and for each pull request that changes the four files, not by CI; CI runs `test_mutation.py`, which tests the tool on a tree of its own and runs four real faults. The chat faults of W6.R16.10 (`a chat message logged with its text`) wait for the chat routes (W4); `the kill switch not read for chats` is tried on the write routes instead.
- **Gaps the first pass found** (`test_gaps.py`): the value of a query key was not checked by any test, `servetoken` itself did not have a test for the limit of 90 days, and nothing checked that request ids are distinct. Each now has a test, and the fault that survived is caught.

Last pass (Nov 12 2026, Python 3.11, 400 cases per property): **planted 96, caught 93, survived 3, invalid 0.** The three survivors are equivalent, which is shown in the catalogue and not assumed: `G17` (a float accepted by the body parser: no route has a number field, so the type check refuses it anyway), `S14` (the port may be shared: on Linux `SO_REUSEADDR` does not share a listening port), and `S16` (the write lock not taken: every request runs one at a time on the main thread, KNOWN-LIMITS 233, so the lock is never contended; it is a second lock).

### The by-hand browser pass (the owner's)

**Not run.** No real browser was started for W6. The checklist below is for the owner; each step has the result that means it passed. Use a fresh root (or a copy of yours), a normal browser, and a token you can throw away. Write the date and the browser and its version in the table under the list and in [NOTES-w6.md](../adapters/NOTES-w6.md).

1. In a terminal: `umwayi serve token create`, copy the `umt1_` line. Then `umwayi serve`. **Expect** `Listening on http://127.0.0.1:PORT` and no `(page not served)`. If it says page not served, run the page build first and stop here.
2. Open `http://127.0.0.1:PORT/` in the browser. **Expect** the hillside picture and, below, a "Local backend" section with a password field. The developer tools Network tab shows only the page itself, and the Console shows no error.
3. Paste the token and press "Use token". **Expect** the field is empty at once, then a line "Kill switch: off. Token: 30 days left." and the queue. The Network tab shows one `GET /v1/status` and one `GET /v1/queue`, both to `127.0.0.1:PORT`, both with an `Authorization` header and no cookie.
4. Add an item (kind decision, a title). **Expect** "Done" and the item in the list. In the terminal, `umwayi queue list` shows the same item. (If your rules have no Yes for `queue.add`, you get Ask me first and a decision in the queue instead; copy the lines from `serve.rules.example.yaml` and try again.)
5. Answer the item, then Close it. **Expect** "Done" each time, the status in the list changes to answered and then closed, and `umwayi queue list` agrees.
6. Press "Stop everything". **Expect** the kill switch reads `on`, the file `.umwayi/KILL` exists, and adding another item now says the kill switch is on. There is no button to turn it off: turn it off in the terminal with `umwayi kill off`.
7. Reload the page (F5). **Expect** the section asks for the token again; the Network tab shows no request until you paste it. Paste a wrong token (`umt1_` and 43 letters) and press "Use token": **Expect** "The token is wrong or has run out" and nothing else changes.
8. Run `umwayi logbook verify`. **Expect** it passes, and the entries `Request R-...: GET status, done` and so on are there, with no token, title or answer text in the request entries.
9. Close the server (Ctrl-C), then open `ui/dist/index.html` from disk (a `file://` address). **Expect** the section says to open the page with `umwayi serve`, has no field or button, and the Network tab shows no request after the page itself.
10. Optional, for the cross-origin claim of W6.R16.9: serve any other page from another local port (`python -m http.server 9000` in a folder with a page whose script calls `fetch("http://127.0.0.1:PORT/v1/status")` and posts a form to `http://127.0.0.1:PORT/v1/queue`) while `umwayi serve` runs. **Expect** the browser blocks the read (no `Access-Control-Allow-Origin` header exists to allow it), the form post is refused (no `Origin` of ours, no token) and `umwayi queue list` shows nothing new.

| date | browser and version | steps 1 to 9 | step 10 | notes |
| --- | --- | --- | --- | --- |
| (not run yet) | | | | |

### Known limits

[KNOWN-LIMITS.md](KNOWN-LIMITS.md) items 196 to 212, 233 to 236, 249 (the page client stops until reload) and 252 (the checks are not a browser test, and the mutation pass is run by hand). The main ones: a process of the same user that learns the token is the owner as far as the backend can tell; no TLS on loopback; any local process can use up the 16 request slots; a request changes real files exactly as the command line does; requests run one at a time on the main thread (233); the browser behaviour was read, not tried (205, 252).

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-12 | W6.10: the docs, the whole-system scenarios, 96 planted faults and the mutation pass were written for the parts that are merged. The scenarios sit in `tests/serve/test_scenarios.py`, not in `tests/test_whole_system.py` as tasks.md first said. The full mutation pass is run by hand (about 25 minutes), and CI runs only the tests of the tool and four real faults. The by-hand pass in a browser is a checklist for the owner and was not run. | The pull request of W6.10; the questions are listed in it with a recommendation. |
| 2026-11-12 | An approval for an Ask me first request in a web chat is given at the console of `umwayi serve` with the prompt `Allow once? [y/N]`; with no terminal attached the request is rejected. The page can still only reject. | The owner, Nov 12 2026, W6-Q28, approved as proposed. Nothing of it is built before the chat routes (W4). |
| 2026-11-12 | W6.1 to W6.6 built. Where the spec's texts disagreed the build chose: a locked-out caller with a token of the right shape is still compared (so a valid token is never slowed) and gets `rate` 429; a refusal after the token check is logged with its request id but its response is the fixed bytes (`request: null`); a request that changed something and could not be logged answers `logbook` with `data: {"changed": true}`; all work that may write the logbook runs on the main thread. | The build pull request lists each as a question for the owner. |
| 2026-11-12 | Steering rule 5 now names the two loopback servers (the telemetry receiver and `umwayi serve`), and 12.R2, 12.R11 and "The view only looks" were edited. | The owner, Nov 12 2026, W6-Q19 and W6-Q20, in the pull request that builds serve. |
| 2026-11-12 | The rule changes from "the interface only looks" to "the page may send the same request the command line would, to a local backend". The command is `umwayi serve`, bound to 127.0.0.1 only, with a token. Every request meets the same rules check, logbook and kill switch by calling the same code. Fail closed. The core stays standard library only. | The owner, Nov 12 2026, approved. |
| 2026-11-12 | The owner answered W6-Q1 to W6-Q27: all as proposed except four. Q12: the page can only reject an Ask me first in a chat. Q15: the intake step is a fixed list and a pure judge, no model. Q22: W7 version 1 is login plus the public site with sample data and does not control a local backend. Q27: W6.1 to W6.6 plus W6.9 first; W6.7 and W6.8 wait for W4. | The owner, Nov 12 2026. |

## Open questions

W6-Q1 to W6-Q28 are answered (design.md, "Answers (owner, Nov 12)"). Open for the owner, from the build (the pull request has the numbered list with a recommendation for each): the lock-out compare (KNOWN-LIMITS 234), the broken logbook and the page (235), the serial pipeline (233), and the shape of the `changed` note and of a logged gate refusal. To look at after the build (W6-Q10): the logbook volume (KNOWN-LIMITS 201, now with numbers). Confirm: the 53 hours of W6-Q27 are read as leaving out W6.10. From W6.10, for the owner: run the by-hand pass (steps 1 to 10 above) and write the result in the table; decide whether the full mutation pass should run in CI (about 25 minutes) or stay by hand (my recommendation: by hand, before each pull request that changes `servegate.py`, `serve.py`, `servetoken.py` or `client.js`).
