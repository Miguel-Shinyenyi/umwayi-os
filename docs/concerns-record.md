# Concerns record (W19, part 6): first draft

This is a first draft for the owner to review. It checks form only, not truth.

## Purpose

The builder wrote every row from a search of this repo, and the owner has not read it yet. `python -m umwayi concerns check docs/concerns-record.md` checks form only, not truth: it shows that the 111 rows are complete and that each Applies row names a real file, and it cannot tell whether a reason is right. The rules of the record are in [concerns.md](concerns.md).

How the draft was made: a row is Applies only where a file in this repo shows the concern is handled, and that file is the evidence. A row the builder was unsure about is Deferred, and its reason says what is missing. Not applicable always has a reason that fits a stdlib Python command line tool with a small web page. The owner should read the Deferred rows first, then the Applies rows, and change any answer that is wrong.

## Current state

The record, one row for each of the 111 concepts. All dates are 2026-11-13, the day of the draft.

| number | concept | answer | reason | evidence | date |
| --- | --- | --- | --- | --- | --- |
| 1 | Rate limiting | Applies | The local server limits requests per second for each route class and locks out repeated bad tokens with a 429. | umwayi/servegate.py | 2026-11-13 |
| 2 | Caching | Deferred | There is no cache; each logbook append re-reads and hashes the whole file, which KNOWN-LIMITS items 4 and 109 name, and no fix is built. |  | 2026-11-13 |
| 3 | Load balancing | Not applicable | One owner runs one process on one machine, so there is nothing to balance. |  | 2026-11-13 |
| 4 | Reverse proxies | Not applicable | The server binds 127.0.0.1 only and sits behind no proxy, and the owner's own host serves the public site. |  | 2026-11-13 |
| 5 | API gateways | Not applicable | There is one local server and no set of services to put a gateway in front of. |  | 2026-11-13 |
| 6 | CI/CD | Applies | A GitHub workflow plans, shards and runs the Python and Node tests on every pull request and every push to main, and there is no automatic deploy because the owner deploys. | .github/workflows/ci.yml | 2026-11-13 |
| 7 | Docker | Not applicable | The tool is a stdlib Python command line program that runs on the owner's machine, and the repo has no container file. |  | 2026-11-13 |
| 8 | Kubernetes | Not applicable | Nothing here runs as a cluster workload. |  | 2026-11-13 |
| 9 | Service discovery | Not applicable | The only network peers are fixed addresses (127.0.0.1 and the GitHub API), so there are no services to discover. |  | 2026-11-13 |
| 10 | Circuit breakers | Not applicable | The few outgoing calls (the board status script to GitHub) are single manual reads, not a chain of calling services. |  | 2026-11-13 |
| 11 | Timeouts | Applies | The local server cuts a slow read at 5 seconds and a whole request at 10 seconds. | umwayi/serve.py | 2026-11-13 |
| 12 | Retries | Deferred | A failed or stopped task halts the goal with no automatic retry by design, and tools/board_status.py has no retry when GitHub limits it (KNOWN-LIMITS item 253), so the owner has not decided where a retry is wanted. |  | 2026-11-13 |
| 13 | Exponential backoff | Not applicable | No retry loop exists, so there is nothing to back off, and this must be looked at again if row 12 changes. |  | 2026-11-13 |
| 14 | Idempotency | Deferred | No review has been done of whether each write command and server route is safe to run twice, and only the stop of an agent is documented as safe to repeat. |  | 2026-11-13 |
| 15 | Message queues | Not applicable | The queue is a markdown task list for the owner (queue.md), not a message broker. |  | 2026-11-13 |
| 16 | Pub/sub | Not applicable | There are no publishers and subscribers, because commands run once and exit. |  | 2026-11-13 |
| 17 | Event-driven architecture | Not applicable | The design is commands that read and write files, not events that trigger other parts. |  | 2026-11-13 |
| 18 | Distributed transactions | Not applicable | There is no database or second service, so no transaction spans systems. |  | 2026-11-13 |
| 19 | Saga pattern | Not applicable | No multi step process spans services, so no saga is needed. |  | 2026-11-13 |
| 20 | Dead letter queues | Not applicable | There is no message queue, so there is no dead letter queue. |  | 2026-11-13 |
| 21 | Cron jobs | Deferred | Scheduled runs use systemd user timers and are tested with a fake systemctl, but the owner's real check (11.6) is not done, so it is unproven on a real machine. |  | 2026-11-13 |
| 22 | WebSockets | Not applicable | The server speaks plain request and response HTTP and the page does not open a socket. |  | 2026-11-13 |
| 23 | Long polling | Not applicable | The page asks when the owner clicks, and nothing holds a request open waiting for news. |  | 2026-11-13 |
| 24 | Server-sent events | Not applicable | The server sends no event streams, and the page reads a snapshot file or makes single requests. |  | 2026-11-13 |
| 25 | Database indexing | Not applicable | There is no database, because state lives in plain files. |  | 2026-11-13 |
| 26 | Query optimization | Not applicable | There are no queries, only file reads. |  | 2026-11-13 |
| 27 | N+1 queries | Not applicable | There is no database and no object mapper, so no N+1 queries. |  | 2026-11-13 |
| 28 | Connection pooling | Not applicable | There is no database connection to pool. |  | 2026-11-13 |
| 29 | Read replicas | Not applicable | There is no database to replicate for reads. |  | 2026-11-13 |
| 30 | Sharding | Not applicable | The data is one owner's files, small enough for one disk. |  | 2026-11-13 |
| 31 | Partitioning | Not applicable | There is no database table to partition. |  | 2026-11-13 |
| 32 | Replication | Not applicable | Nothing is copied between servers, because the logbook is one local file. |  | 2026-11-13 |
| 33 | Leader election | Not applicable | Only one process holds each lock, so no election is needed. |  | 2026-11-13 |
| 34 | CAP theorem | Not applicable | The system is not spread across nodes, so there is no trade off to make. |  | 2026-11-13 |
| 35 | Eventual consistency | Not applicable | All state is on one machine, so there are no replicas to disagree. |  | 2026-11-13 |
| 36 | Optimistic locking | Not applicable | Writers are serialized by locks, and there is no version number that a writer compares and retries. |  | 2026-11-13 |
| 37 | Pessimistic locking | Applies | The logbook takes a kernel lock (flock) so two commands cannot write at once, and the lock is released if a holder dies. | umwayi/logbook.py | 2026-11-13 |
| 38 | Distributed locks | Not applicable | All locks are on one machine, so no shared lock service is used. |  | 2026-11-13 |
| 39 | Race conditions | Deferred | The logbook and the run lock are guarded, but KNOWN-LIMITS items 137 and 139 name a check before a read that can race, and no full review was done. |  | 2026-11-13 |
| 40 | Deadlocks | Deferred | The run lock never waits, but the logbook lock and the server's write lock were not reviewed together for lock order, so it cannot be said that none can deadlock. |  | 2026-11-13 |
| 41 | Memory leaks | Deferred | The local server can run for a long time, but no long run was measured for growing memory. |  | 2026-11-13 |
| 42 | Garbage collection | Not applicable | The program uses the default Python garbage collector and tunes nothing. |  | 2026-11-13 |
| 43 | Thread safety | Applies | Server handler threads only read and run the gate and hand every request that may write to the main thread, which runs them one at a time (KNOWN-LIMITS item 233). | umwayi/serve.py | 2026-11-13 |
| 44 | Backpressure | Applies | The server handles 16 requests at once, answers the 17th with 503 busy, and answers a write that does not start within 5 seconds as busy. | umwayi/serve.py | 2026-11-13 |
| 45 | Autoscaling | Not applicable | One owner uses one process, so there is nothing to scale out or in. |  | 2026-11-13 |
| 46 | Horizontal scaling | Not applicable | There is only one instance, by design. |  | 2026-11-13 |
| 47 | Vertical scaling | Not applicable | The load is one person, and no larger machine is needed. |  | 2026-11-13 |
| 48 | CDN | Not applicable | The public site loads nothing from a CDN by design (tests forbid it), and the owner's own host serves the files. |  | 2026-11-13 |
| 49 | Edge caching | Not applicable | No edge layer sits in front of the code in this repo. |  | 2026-11-13 |
| 50 | Cache invalidation | Not applicable | No cache of the program's own exists, so none can go stale. |  | 2026-11-13 |
| 51 | Feature flags | Applies | Graded autonomy sits behind one setting that is off by default and stays off until the owner writes enabled true. | autonomy.example.yaml | 2026-11-13 |
| 52 | Blue-green deployment | Not applicable | There is no running service with two live versions, because the owner updates the tool by pulling. |  | 2026-11-13 |
| 53 | Canary releases | Not applicable | There are no users to send a new version to in steps. |  | 2026-11-13 |
| 54 | Rolling deployments | Not applicable | There is no fleet of servers to update in turns. |  | 2026-11-13 |
| 55 | Rollbacks | Deferred | Changes go through pull requests that git can revert, but no rollback steps are written for the owner's data files or the deployed site. |  | 2026-11-13 |
| 56 | Health checks | Deferred | No endpoint or command is built for a monitor to poll, and umwayi logbook verify and budget status are run by hand. |  | 2026-11-13 |
| 57 | Liveness and readiness probes | Not applicable | No orchestrator starts or stops this program on a probe. |  | 2026-11-13 |
| 58 | Monitoring | Deferred | Nothing watches the tool while it runs, and the owner looks at the logbook and the board status by hand. |  | 2026-11-13 |
| 59 | Logging | Applies | Every change is written to an append only, hash chained logbook that crash safety tests cover and that never holds a secret or a prompt. | umwayi/logbook.py | 2026-11-13 |
| 60 | Distributed tracing | Not applicable | A request does not cross services, so there is no trace to follow. |  | 2026-11-13 |
| 61 | Metrics | Deferred | The budget governor counts usage units, but no metric of the tool's own health (request counts, errors, durations) is kept. |  | 2026-11-13 |
| 62 | Alerts | Deferred | The stalls check and the other checks report to standard output and exit, and nothing sends the owner a message. |  | 2026-11-13 |
| 63 | SLOs | Not applicable | No service level is promised to anyone, because the tool has one owner. |  | 2026-11-13 |
| 64 | SLIs | Not applicable | No service level exists to measure. |  | 2026-11-13 |
| 65 | Error budgets | Not applicable | No service level exists to budget errors against. |  | 2026-11-13 |
| 66 | Observability | Deferred | The logbook and the read only snapshot show what happened, but the owner has not decided if that is enough to see how it runs. |  | 2026-11-13 |
| 67 | Secrets management | Applies | Tests plant secrets and check that none reaches any file or output umwayi writes, and the serve token is kept only as a SHA-256 hash in a 0600 file. | tests/test_scan_secrets.py | 2026-11-13 |
| 68 | IAM | Not applicable | There are no accounts or cloud roles, and the rules file decides what an AI helper may do. |  | 2026-11-13 |
| 69 | OAuth | Not applicable | umwayi does not log users in, and the AI tools keep their own sign in while umwayi only checks that it exists. |  | 2026-11-13 |
| 70 | JWT rotation | Not applicable | No JWT is used, and the serve token is a random value with an expiry that can be revoked. |  | 2026-11-13 |
| 71 | TLS | Deferred | The server uses plain HTTP on 127.0.0.1 (KNOWN-LIMITS item 202), and TLS of the deployed site depends on the owner's host, which was not checked. |  | 2026-11-13 |
| 72 | Encryption at rest | Deferred | Files are plain and only the file mode (0600 for the token and capture files) protects them, and the owner has not decided if encryption is wanted. |  | 2026-11-13 |
| 73 | Encryption in transit | Deferred | Traffic on loopback is not encrypted, and nothing here checks that the deployed site is served over HTTPS. |  | 2026-11-13 |
| 74 | WAF | Not applicable | No public web application or API in this repo sits behind a firewall. |  | 2026-11-13 |
| 75 | DDoS protection | Not applicable | The server accepts only the loopback address, and the public site is served by the owner's own host. |  | 2026-11-13 |
| 76 | CORS | Applies | The server sends no CORS headers, requires an exact Host and Origin, and refuses cross site fetch metadata. | umwayi/servegate.py | 2026-11-13 |
| 77 | CSRF | Applies | A POST or DELETE needs the exact Origin and a bearer token in a header, not a cookie, so another site cannot send a request on the owner's behalf. | umwayi/servegate.py | 2026-11-13 |
| 78 | SQL injection | Not applicable | No SQL database is used. |  | 2026-11-13 |
| 79 | XSS | Applies | The page sets all text as text and never as markup, and a test fails on any markup setting call, though the public site still allows inline scripts (KNOWN-LIMITS item 140). | tests/test_ui_package.py | 2026-11-13 |
| 80 | SSRF | Not applicable | The server never fetches an address that a caller gives it. |  | 2026-11-13 |
| 81 | Database migrations | Not applicable | There is no database to migrate. |  | 2026-11-13 |
| 82 | Schema versioning | Applies | The snapshot has a schema number that is checked strictly, and a file of another version is refused. | umwayi/view.py | 2026-11-13 |
| 83 | Disaster recovery | Deferred | The logbook has a torn tail recovery, but no plan exists for a lost disk or a restore (see row 84). |  | 2026-11-13 |
| 84 | Backups | Deferred | No command or document makes or describes a backup of the logbook or the memory folders. |  | 2026-11-13 |
| 85 | Failover | Not applicable | There is one instance and nothing to fail over to. |  | 2026-11-13 |
| 86 | Multi-region deployment | Not applicable | The tool runs on one machine, so there is no multi region deployment. |  | 2026-11-13 |
| 87 | Chaos engineering | Not applicable | There is no fleet to break on purpose, and planted fault tests and mutation checks are the nearest practice. |  | 2026-11-13 |
| 88 | Cost optimization | Applies | The budget governor reserves a budget before each agent run, caps it per run and per day, and settles it at the end. | umwayi/budget.py | 2026-11-13 |
| 89 | Cold starts | Not applicable | Nothing runs as a function that starts cold. |  | 2026-11-13 |
| 90 | Serverless limits | Deferred | The repo does not say where the owner deploys site/, so it cannot be told whether any function limits apply. |  | 2026-11-13 |
| 91 | Latency | Deferred | One timing of the local server is in KNOWN-LIMITS item 201, but no target and no repeating check exist. |  | 2026-11-13 |
| 92 | Throughput | Not applicable | The load is one owner, and no throughput target is needed. |  | 2026-11-13 |
| 93 | P99 latency | Not applicable | No percentile is measured, because the tool has one user. |  | 2026-11-13 |
| 94 | Tail latency | Not applicable | No percentile is measured, because the tool has one user. |  | 2026-11-13 |
| 95 | Network partitions | Not applicable | The tool runs on one machine, so the network is only loopback. |  | 2026-11-13 |
| 96 | Clock skew | Applies | Token expiry uses the later of the system date and the newest logbook date, and rate windows use a monotonic clock, so a clock set back does not revive an expired token. | umwayi/serve.py | 2026-11-13 |
| 97 | DNS | Applies | The server accepts only the exact Host 127.0.0.1 and the port, which stops DNS rebinding. | umwayi/servegate.py | 2026-11-13 |
| 98 | TCP vs UDP | Not applicable | Only loopback TCP is used and the choice is made by the standard library. |  | 2026-11-13 |
| 99 | HTTP/2 and HTTP/3 | Not applicable | The server uses plain HTTP/1.1 from the standard library. |  | 2026-11-13 |
| 100 | gRPC | Not applicable | No gRPC is used. |  | 2026-11-13 |
| 101 | Webhooks | Not applicable | The tool receives no webhook and sends none. |  | 2026-11-13 |
| 102 | API versioning | Deferred | Responses carry a schema number, but there is no written rule for how a change to a route is announced. |  | 2026-11-13 |
| 103 | Semantic versioning | Deferred | pyproject.toml says version 0.1.0, and no rule or release process says when the number changes. |  | 2026-11-13 |
| 104 | Infrastructure as code | Not applicable | No infrastructure is created from code, and the systemd units come from the schedule command on the owner's machine. |  | 2026-11-13 |
| 105 | Terraform | Not applicable | No cloud resources are managed. |  | 2026-11-13 |
| 106 | Helm charts | Not applicable | Nothing is deployed to Kubernetes. |  | 2026-11-13 |
| 107 | Build caching | Applies | The workflow caches the npm download folder with a key made from the lockfiles and still runs a clean install. | .github/workflows/ci.yml | 2026-11-13 |
| 108 | Dependency hell | Applies | Python uses only the standard library, and the Node packages have exact versions and a lockfile with a sha512 for each package, which a test checks. | tests/test_site_package.py | 2026-11-13 |
| 109 | Production incidents | Deferred | No written steps exist for an incident on the owner's real data or deployed site, and the stall checker reads a file nobody writes yet. |  | 2026-11-13 |
| 110 | On-call | Not applicable | One person owns the tool, so there is no on call rota. |  | 2026-11-13 |
| 111 | Postmortems | Deferred | Defects are written as KNOWN-LIMITS items, but there is no postmortem template or practice. |  | 2026-11-13 |

## Decisions log

- 2026-11-13: the first draft was written by the builder for W19 part 6. The Deferred rows are where work or a decision is missing, and they are not failures of the checker. No job or schedule runs the check on this file. There is no table here on purpose: the checker reads every line that starts with a bar after the record as a row.

## Open questions

- Every answer is the builder's reading and waits for the owner. The owner decides which Deferred rows become work and which become Not applicable.
