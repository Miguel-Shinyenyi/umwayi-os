# Security

## Purpose

This page says what umwayi does to keep the owner in control (fail closed, rules before every action, no secret in any output) and how it is checked. It exists so the owner can see what is protected, what is only made visible, and what is not covered.

## Current state

- Fail closed: no matching rule, a broken file, an unknown kill switch state or a logbook that cannot be written never give Yes ([rules.md](rules.md), [workflows.md](workflows.md), [logbook.md](logbook.md)).
- The core makes no network connection except the budget governor's telemetry receiver, on 127.0.0.1 for one Claude Code run ([budget-governor.md](budget-governor.md)).
- An agent is started only through the front door, gated by the layer 9 hook, its login checked (subscription first) and its budget reserved ([agent-front-door.md](agent-front-door.md)).
- Logbook entries never hold an action's JSON, a prompt, a conversation or a credential; the hash chain and an outside anchor make edits visible ([logbook.md](logbook.md)).
- Everything that is known and not fixed is in [KNOWN-LIMITS](KNOWN-LIMITS.md).
- The security scan (S.2) is not run yet. Its results will be `docs/SECURITY-SCAN.md`, dated, with what the scan cannot prove ([requirements.md](../.kiro/specs/umwayi-os/requirements.md), S.R9 and S.R10).

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-10 | S-Q3 to S-Q5: Bandit and the code guards for umwayi's code; OSV-Scanner offline and `npm audit --package-lock-only` for the adapter's npm tree; the interpreters compared with python.org's security releases | Approved in PR 34. |
| 2026-11-10 | S-Q6, S-Q7, S-Q9: a 10 s whole-request deadline and at most 16 requests at once in the receiver; the file mode rule | Approved in PR 34. |
| 2026-11-10 | S-Q8, S-Q10 to S-Q13: what blocks the freeze; the same-user boundary stated, not tested; licences listed; results in `docs/`; no CI change for Dec 3 | Approved in PR 34. |

## Open questions

- S.2, the security scan, is not built yet ([tasks.md](../.kiro/specs/umwayi-os/tasks.md), S.2).
