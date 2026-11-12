# Security

## Purpose

This page says what umwayi does to keep the owner in control (fail closed, rules before every action, no secret in any output) and how it is checked. It exists so the owner can see what is protected, what is only made visible, and what is not covered.

## Current state

- Fail closed: no matching rule, a broken file, an unknown kill switch state or a logbook that cannot be written never give Yes ([rules.md](rules.md), [workflows.md](workflows.md), [logbook.md](logbook.md)).
- The core makes no network connection except the budget governor's telemetry receiver, on 127.0.0.1 for one Claude Code run ([budget-governor.md](budget-governor.md)).
- An agent is started only through the front door, gated by the layer 9 hook, its login checked (subscription first) and its budget reserved ([agent-front-door.md](agent-front-door.md)).
- Logbook entries never hold an action's JSON, a prompt, a conversation or a credential; the hash chain and an outside anchor make edits visible ([logbook.md](logbook.md)).
- Everything that is known and not fixed is in [KNOWN-LIMITS](KNOWN-LIMITS.md).
- Files: `LOGBOOK.md` and the logbook lock must be regular files with one name, and the append never follows a link; every other write replaces through a new file or creates with `O_EXCL`. The files that can hold a secret or an approval-like token are private (the canary folder 0700; the canary file, the capture file and the intent 0600); unit files are exactly 0644; everything else follows the owner's umask. `rules.yaml` and `umwayi.json` are read only as regular files of at most 1 MB and 64 KB.
- The telemetry receiver listens on 127.0.0.1 only and accepts only the exact run header given once, one Content-Length and no Transfer-Encoding, 1 MB a body and 16 MB a run. It cuts every request at 10 s and handles at most 16 at once, answering more with 503 ([budget-governor.md](budget-governor.md)).
- **The security scan (S.2), 2026-11-10:**
  - Bandit found no Medium or High finding in umwayi's code.
  - OSV-Scanner and `npm audit` found no known vulnerability in the adapter's 112 packages, and all 115 have verified registry signatures.
  - The scan's tests found 10 defects, all fixed in PR 37.
  - The record, every tool with its version and checksum, each finding with its decision, and what the scan cannot prove: [SECURITY-SCAN.md](SECURITY-SCAN.md).
- How it is tested: `tests/test_scan_receiver.py`, `tests/test_scan_files.py`, `tests/test_scan_secrets.py` and the code guards ([testing.md](testing.md)).
- **The web interface (layer 12, `ui/` and `site/`)** only looks. The owner's live view is one file with no network request and a Content-Security-Policy of `default-src 'none'`; the public site fetches only its own files. A snapshot file or a typed note is read in the browser, checked strictly, set as text and never as markup, and kept in memory only: no storage, no cookie, nothing sent (tests over the source and the built page, and request logs in a browser, in `interface.md`). Download of the notes is a link whose address holds the text. **The scan of `ui/package-lock.json` (OSV-Scanner, `npm audit`, signatures, licences) is not done**: the owner holds all security scans for later, so that item of UI.5 stays open ([tasks.md](../.kiro/specs/umwayi-os/tasks.md)).
- Graded autonomy (layer 13) can move an Ask me first to Yes from the owner's record. The record is chained and read in fixed shapes, and a helper is kept from it by the guard names of the adapters, but a process of the same user can write well formed, chained inputs ([KNOWN-LIMITS](KNOWN-LIMITS.md) items 135 and 166). It is off by default.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-10 | The scan's 10 defects fixed in PR 37, test first: the receiver's deadline, cap and single headers; bounded reads of `rules.yaml` and `umwayi.json`; no write through a hard link or a swapped link in the logbook; the intent 0600 and `queue.md` at the umask; a too long path a usage error | S.2 (S-Q8: every defect a test shows is fixed or accepted before the freeze). |
| 2026-11-10 | S-Q3 to S-Q5: Bandit and the code guards for umwayi's code; OSV-Scanner offline and `npm audit --package-lock-only` for the adapter's npm tree; the interpreters compared with python.org's security releases | Approved in PR 34. |
| 2026-11-10 | S-Q6, S-Q7, S-Q9: a 10 s whole-request deadline and at most 16 requests at once in the receiver; the file mode rule | Approved in PR 34. |
| 2026-11-10 | S-Q8, S-Q10 to S-Q13: what blocks the freeze; the same-user boundary stated, not tested; licences listed; results in `docs/`; no CI change for Dec 3 | Approved in PR 34. |

## Open questions

- Python 3.10 is end of life since 2026-10-01: keep it to Dec 3 or drop it now? The owner decides ([KNOWN-LIMITS](KNOWN-LIMITS.md) item 133).
- The 9 Claude Agent SDK packages are under Anthropic's terms, not an open licence: the owner reads them (S-Q11, [SECURITY-SCAN.md](SECURITY-SCAN.md)).
- The owner's real runs (10.21, 10.31, 11.6, B.10) are not done; until then what the real platforms do is unproven ([SECURITY-SCAN.md](SECURITY-SCAN.md), section 6).
