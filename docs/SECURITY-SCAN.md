# Security scan (S.2)

The recorded scan of umwayi-os, task S.2 of `.kiro/specs/umwayi-os/tasks.md` (requirements S.R4 to S.R10, the answers S-Q1 to S-Q16). How it is kept current: [DOCS_MAINTENANCE.md](DOCS_MAINTENANCE.md). What umwayi protects and how: [security.md](security.md).

- **Date:** 2026-11-10, in the Kiro sandbox (Linux x86_64), on branch `scan/security` from main b661ffd (PR 37).
- **Fail closed (S.R9.2):** a scan that could not run would be written here as "not run". Every scan below ran.
- **No new dependency (S.R9.3):** every tool ran from a throwaway folder outside the repo (`/projects/sandbox/work/scan`). None is committed, installed into the repo or added to `pyproject.toml`, `package.json` or CI.

## 1. What was scanned

| target | how | result |
| --- | --- | --- |
| umwayi's Python code: `umwayi/`, the layer 9 hooks, `adapters/common`, the canary | Bandit, all plugins | 18 Low, 0 Medium, 0 High: each decided below |
| umwayi's own code guards | the guard tests already in the suite | pass; listed in section 3 |
| the core package's dependencies | `pyproject.toml` | none (`dependencies = []`) |
| the one adapter package's tree: `adapters/claude_acp/package-lock.json` (lockfile version 3, 115 entries, 112 distinct packages) | OSV-Scanner offline; `npm audit --package-lock-only`; `npm audit signatures` | no known vulnerability; all 115 signatures verified |
| licences of that tree | each installed `package.json` and the SDK's licence file | 106 open licences; 9 Anthropic SDK packages under Anthropic's terms, for the owner to read |
| the Python interpreters | python.org's version status and its release folders | 3.10 is end of life; every interpreter here is behind its branch's newest patch |
| the telemetry receiver, file modes, links and paths, secrets in outputs | tests in the normal suite: `tests/test_scan_receiver.py`, `tests/test_scan_files.py`, `tests/test_scan_secrets.py` | 10 defects found and fixed in PR 37 (section 6) |

## 2. The tools, where they came from, how they were checked

| tool | version | from | checked by | command |
| --- | --- | --- | --- | --- |
| Bandit | 1.9.4 | PyPI, in a new virtual environment (`python3 -m venv`, Python 3.11.15) | the wheel's SHA-256 `f89ffa663767f5a0585ea075f01020207e966a9c0f2b9ef56a57c7963a3f6f8e` equals the one PyPI publishes for `bandit-1.9.4-py3-none-any.whl` | `bandit -r umwayi adapters/claude_code adapters/kiro adapters/stdio adapters/common adapters/claude_acp/canary.py adapters/__init__.py -f json` |
| OSV-Scanner | 2.7.1 (osv-scalibr 0.5.3, commit 02f96a40691c2d155fdda799af436e111231e365), released 2026-11-09 | the GitHub release `osv-scanner_linux_amd64` | its SHA-256 `fb7dab19a8bd9bbe5c3189f09d4b7ee1820c9553a23bac202648a56efd2f6ee8` equals the line in the release's `osv-scanner_SHA256SUMS` and GitHub's own digest of the asset | 1: `osv-scanner scan source --offline --download-offline-databases -L package-lock.json` (fetches the npm database); 2: `osv-scanner scan source --offline -L package-lock.json --format json` (the recorded run: local data only) |
| the OSV npm database | `osv-scalibr/npm/all.zip`, 231,619 advisories, newest changed 2026-11-10T17:30Z, SHA-256 `0286f3cec042475af18c78cd90cd0f32a9250e4060b79fd11844588aa6f8879d` | osv-vulnerabilities.storage.googleapis.com, through the first command | the newest `modified` time inside it | |
| npm | 11.4.2 (Node 22.23.4), registry `https://registry.npmjs.org/` | already in the sandbox | | `npm audit --package-lock-only --json` in a copy of the folder; `npm ci --ignore-scripts` in another copy, then `npm audit signatures` |

## 3. Results

### umwayi's Python code (Bandit)

39 files, 9,734 lines, no `# nosec` anywhere. 0 High, 0 Medium, 18 Low:

| id | what | where | decision |
| --- | --- | --- | --- |
| B105 hardcoded password string | `COST_METRIC = "claude_code.cost.usage"` | `umwayi/telemetry.py` | false positive: a metric name |
| B110 try, except, pass (9) | a write to stderr or stdout in an error path, and putting the terminal mode back | the three hooks (4), `umwayi/cli.py` (4), `umwayi/agents.py` (1) | by design: the answer is already decided (a deny, exit 2); a failed write of the message must not change it |
| B404 import subprocess (3) | the program runners | `adapters/common/umwayi_gate.py`, `umwayi/agents.py`, `umwayi/report.py` | by design: the only three, pinned by the code guards below |
| B603 subprocess without a shell (5) | every program start | the same three files | by design: an argument list from fixed tables, never a shell; this is the form the guards require |

### umwayi's own code guards (S.R4.1)

All in the normal suite, and passing:

- no shell anywhere, and program runners only in `agents.py` and `report.py` (`tests/test_automation.py`, `CodeGuardTests`);
- no network module anywhere except the receiver's `http.server` and `socket`, imported inside the one function that starts it, and importing any umwayi module loads none (`tests/test_system.py`, `CodeTests`);
- the canary folder is the only folder `agents.py` makes and removes, and no argument list holds a forbidden flag (`tests/agents/test_agents_gate.py`, `CodeGuardTests`);
- `schedule.py` imports no program runner, and nothing names `systemctl`, `crontab` or `loginctl` in an argument list (`tests/test_schedule.py`, `CodeGuardTests`);
- umwayi changes a file mode only on a file it has just made (`tests/test_scan_files.py`, `ChmodGuardTests`, new).

### The adapter's npm tree

| source | packages it read | result |
| --- | --- | --- |
| OSV-Scanner, offline | 112 (every distinct name and version in the lockfile) | 0 known vulnerabilities |
| `npm audit --package-lock-only` | 115 entries: 6 prod, 8 optional, 102 peer | 0 (info, low, moderate, high, critical all 0) |
| `npm audit signatures` | 115 installed | 115 verified registry signatures; 20 also have verified attestations |

The two advisory sources agree. `npm audit` counts 102 of the 115 as peer dependencies (the lockfile marks them `peer`), and its documentation says it does not check peer dependencies, so it may have checked only the other 13. OSV-Scanner read all 112, so it is the source this result rests on (KNOWN-LIMITS 131).

### Licences (S-Q11)

| licence | packages |
| --- | --- |
| MIT | 90 |
| ISC | 7 |
| Apache-2.0 | 4 |
| BSD-3-Clause | 3 |
| BSD-2-Clause | 1 |
| Unlicense | 1 |
| "SEE LICENSE IN LICENSE.md" or "SEE LICENSE IN README.md": `@anthropic-ai/claude-agent-sdk` and its 8 platform packages (2 installed here, 6 for other platforms read from the lockfile) | 9 |

The SDK's `LICENSE.md` says "© Anthropic PBC. All rights reserved. Use is subject to the Legal Agreements" at `https://code.claude.com/docs/en/legal-and-compliance`, and its README points to Anthropic's Commercial Terms of Service. It is not an open licence. As S-Q11 decided, umwayi decides nothing here: **the owner reads those terms**.

### The Python interpreters (S-Q5)

From python.org's [Status of Python versions](https://devguide.python.org/versions/) and its release folders (`https://www.python.org/ftp/python/`, each newest release checked to have its source tarball), read 2026-11-10:

| version tested here | branch status | newest release of the branch |
| --- | --- | --- |
| 3.10.20 | **end of life since 2026-10-01**: no more security fixes | 3.10.22 |
| 3.11.15 | security fixes only, until 2027-10 | 3.11.18 |
| 3.12.13 | security fixes only, until 2028-10 | 3.12.16 |
| 3.13.13 | security fixes only, until 2029-10 | 3.13.18 |

Every interpreter in this sandbox is behind its branch's newest patch release. That is this sandbox, not umwayi: CI's `setup-python` takes the newest patch of each version, and the owner's own interpreters were not seen. The release notes were not read item by item, so this record does not say which fixes the missing releases carry.

**Decision needed from the owner:** umwayi says `requires-python = ">=3.10"` and CI tests 3.10, which no longer gets security fixes (KNOWN-LIMITS 133). Nothing was changed here; the choice (keep 3.10 to Dec 3, or drop it now) is the owner's.

## 4. The receiver, modes, links, paths and secrets (S.R5 to S.R8)

Each case is a test in the normal suite that runs umwayi as a real child process.

- **The receiver** (`tests/test_scan_receiver.py`, 10 tests):
  - It listens on 127.0.0.1 only, read back from `/proc/net/tcp` and `tcp6`, and `::1` and every other address of the machine refuse a connection.
  - The port refuses connections after umwayi exits: a normal end, the kill switch, SIGTERM and a crash.
  - Only the exact run header, given once, is accepted. Missing, wrong, a prefix, one character more, upper case, another run's secret, and given twice are all 401; the header name may be in any case, as in HTTP.
  - Exactly 1 MB is read; one byte more is 413, answered before the body is sent.
  - A short body (400 after the socket timeout) and a long body (the rest never read). Chunked without a length is 411; chunked with a length, gzip, and a second Content-Length are 400 or 415.
  - A slow client is cut at the 10 s whole-request deadline (S-Q6). A slow body after the run header makes the run invalid.
  - 200 trickling connections: at most 16 are handled, the rest are answered 503 at once, umwayi's thread count stays bounded, and the run's own report still counts (S-Q7).
- **Modes** (`tests/test_scan_files.py`, `ModeTests`), under umask 022 and 077:

  | file | mode |
  | --- | --- |
  | the canary folder | 0700 |
  | the canary file, the capture file, the intent while it holds an entry | 0600 |
  | the unit files | exactly 0644 |
  | everything else umwayi makes: `LOGBOOK.md`, `.umwayi/` and the record, the locks and `KILL`, `queue.md`, the archive, drafts, the outbox, the unit folder | the owner's umask |

- **Links** (`LinkTests`): a symbolic link to a file outside the root, to `/dev/zero` and to a folder, in place of each of 17 files umwayi reads or writes. Each is refused or skipped as its layer says, with no hang and no write outside the root. A hard link to an outside file in place of the logbook lock, `LOGBOOK.md`, `queue.md`, the hash record and the archive index never carries a write outside.
- **Races** (`RaceTests`): `LOGBOOK.md` swapped for a link between the check and the append; links planted where umwayi creates with `O_EXCL` (a unit file, the capture file, a draft).
- **Paths** (`PathTests`): `--root`, `--agents`, `schedule --file`, `--prompt-file`, a jobs file, a workflow name, an archive source, an article, a draft, `--rules` and `UMWAYI_TELEMETRY_CAPTURE`, each given `..`, a newline, 5,000 characters, a non-UTF-8 name and an absolute path outside the root. Each is refused, with no traceback, no control character in the output and nothing written outside the root. A prompt file outside the root is allowed, as it is the owner's own prompt.
- **Secrets** (`tests/test_scan_secrets.py`):
  - Planted secrets go into every place one can enter: the prompt as an argument, a file and stdin; all 14 credential names umwayi knows and the owner's `OTEL_EXPORTER_OTLP_HEADERS`; private memory, a rules comment, a queue answer, an article, a jobs comment, a hand edit of a unit file; tool inputs through all three hooks; ACP messages; a telemetry prompt attribute; the fakes' email; and the text of two planted crashes.
  - Then every byte umwayi printed, and every file under the root, the unit folder, TMPDIR and the capture file, was swept for those words, for every run header secret and for every canary token. None was found outside these allowed places:

    | allowed place | why |
    | --- | --- |
    | the owner's own files (memory, `rules.yaml`, `jobs.yaml`, articles) | they are the owner's |
    | the answer in `queue.md` | layer 3 keeps it there; the logbook records its length only |
    | the hand-edited unit file | `schedule check` and `remove` refuse it without printing it |
    | the agent's text in an ACP chat, and the agent's echo in a cli chat | that is the agent's output on the owner's terminal |

## 5. Findings and decisions (S-Q8)

| # | finding | severity | decision |
| --- | --- | --- | --- |
| 1 | `rules.yaml` (or `--rules PATH`) that is `/dev/zero` or a FIFO: `umwayi check` read it forever | defect a test shows | fixed in PR 37: read only as a regular file of at most 1 MB; anything else is a broken rules file (Ask me first) |
| 2 | `umwayi.json` that is `/dev/zero`: umwayi read it until the system killed it (SIGKILL) | defect a test shows | fixed in PR 37: a regular file of at most 64 KB, otherwise 64 |
| 3 | the logbook lock writes the holder's pid into `.umwayi/logbook.lock`; a hard link there let that write reach a file outside the root | defect a test shows | fixed in PR 37: a lock file with a second name is refused before the write |
| 4 | the append opened `LOGBOOK.md` with `open(path, "ab")`: a link swapped in after the checks, or a hard link, was written through | defect a test shows | fixed in PR 37: `O_NOFOLLOW` and a check of the open file (a regular file with one name) |
| 5 | the intent followed the umask (0644 under 022), not 0600 (S-Q9) | defect a test shows | fixed in PR 37 |
| 6 | a new `queue.md` was 0600 (`mkstemp`'s mode), not the owner's umask (S-Q9) | defect a test shows | fixed in PR 37: the shared atomic writer |
| 7 | a path longer than the system allows was "stopped by an unexpected error" (exit 2) | defect a test shows | fixed in PR 37: a usage error (64) that names no path |
| 8 | the receiver had no whole-request deadline: a client sending a byte every 4 s held a thread for as long as it kept sending (S-Q6) | defect a test shows | fixed in PR 37: 10 s per request |
| 9 | the receiver started one thread per connection with no cap: 200 trickling connections made 202 threads (S-Q7) | defect a test shows | fixed in PR 37: at most 16 at once, the rest answered 503 at once |
| 10 | the receiver read only the first of a header given twice (the run header, Content-Length) and ignored a Transfer-Encoding | defect a test shows | fixed in PR 37: each must come exactly once; a Transfer-Encoding is refused |
| 11 | 18 Low Bandit findings | Low | each decided in section 3: 1 false positive, 17 by design |
| 12 | `npm audit` may not check 102 peer packages | tool limit | accepted: OSV-Scanner read all 112 (KNOWN-LIMITS 131) |
| 13 | 9 SDK packages are under Anthropic's terms, not an open licence | for the owner (S-Q11) | listed; **the owner reads the terms** |
| 14 | Python 3.10 is end of life | environment | **open: the owner decides** (KNOWN-LIMITS 133) |
| 15 | the sandbox's interpreters are behind their newest patch releases | environment | recorded; not umwayi's code |

Planted faults for the fixes: 15 of 15 caught (the PR 37 description lists each).

## 6. What the scan cannot prove (S.R10)

1. That there is no vulnerability. A static scan finds known patterns; an advisory scan finds known advisories for the exact versions in the lockfile. Neither says anything about defects nobody has reported.
2. Anything about code it cannot see: the prebuilt programs inside the Claude Agent SDK's platform packages, the real Claude Code and Kiro programs, the owner's Node and Python builds, and the operating system.
3. That a pinned version is honest. Lockfile integrity hashes and registry signatures prove the files are the ones published, not that what was published is safe.
4. Anything against a process of the same user. umwayi, its agents and the owner's other programs run as one user. Such a process can read the agent's environment (the run secret), write the logbook and its record, change unit files, or flood the receiver. The chain, the anchor and the kill switch make some of this visible; none of it is prevented (S-Q10).
5. What the real platforms do. The fakes follow the docs, and every place where the docs are silent (the NOTES files) stays unproven until the owner's real runs (10.21, 10.31, 11.6, B.10), which are not done.
6. That the tests are complete. The planted faults show the tests catch the faults that were tried, not every fault.

The advisory results are true on 2026-11-10 only; a new advisory for one of the 112 packages can appear any day (KNOWN-LIMITS 130).

## Run it again

From a folder outside the repo, with the network once:

```
python3 -m venv bandit-env && bandit-env/bin/pip install bandit
bandit-env/bin/bandit -r UMWAYI/umwayi UMWAYI/adapters/claude_code UMWAYI/adapters/kiro UMWAYI/adapters/stdio UMWAYI/adapters/common UMWAYI/adapters/claude_acp/canary.py
# OSV-Scanner: download osv-scanner_linux_amd64 and osv-scanner_SHA256SUMS from its GitHub release, check the SHA-256
OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY=$PWD/osvdb ./osv-scanner scan source --offline --download-offline-databases -L UMWAYI/adapters/claude_acp/package-lock.json
OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY=$PWD/osvdb ./osv-scanner scan source --offline -L UMWAYI/adapters/claude_acp/package-lock.json
cp -r UMWAYI/adapters/claude_acp a && (cd a && npm audit --package-lock-only)
cp -r UMWAYI/adapters/claude_acp b && (cd b && npm ci --ignore-scripts && npm audit signatures)
```
