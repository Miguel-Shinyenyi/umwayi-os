# Budget governor

## Purpose

The budget governor gives every agent run one unit of cost (UU, one US cent of estimated list price), reserves a per-run cap before a start, checks it while the run goes on, and settles every run in the logbook. It exists so a runaway agent cannot spend without the owner knowing, measured where it can be and counted at the worst case where it cannot.

## Current state

Every agent start reserves a budget first, and every run is settled in the logbook when it ends. The unit is UU: one US cent of estimated list price. On a subscription nothing is billed per token; UU then says what the same use would cost at list price, so a limit means the same on every platform. It is an estimate, not a bill.

```
umwayi budget validate                    check units.yaml, every problem with a line number (writes nothing)
umwayi budget status [--date D]           used, reserved and left per limit, and how much was measured (writes nothing)
umwayi budget calibrate                   propose per_run and per_day from your measured runs (changes nothing)
umwayi budget settle-lost --by YOU        settle the reservations a killed umwayi left behind
```

- **Limits** (in UU, placeholders until you calibrate): `per_run` 100, `per_day` 500, `per_agent_per_day` 300, `per_platform_per_day` 400, and `unknown_worst_case` 100. A day is the logbook date.
- **Before a start**, after the gate checks: `units.yaml` is validated (64), any change to it is logged first (2 if it cannot be), the reservation of `per_run` must fit the three day limits (otherwise exit 3, one entry, nothing started), then the rules are asked for `budget_check`. Yes goes on, No is exit 2, and Ask me first is exit 3 with one queue item "Spend up to N UU on agent NAME?". The kill switch and a broken logbook are checked first and still win. A start then writes one reserve entry before its start entry.
- **The rules.** No rule for `budget_check` means Ask me first, so add one next to your `agent_run` rule, for example:

  ```yaml
  - id: reviewer-may-spend
    title: The reviewer may spend within the limits
    text: The limits in units.yaml decide; this rule only says the reviewer may use them.
    verdict: yes
    matchers:
      type: budget_check
      agent: reviewer
  ```

  The action is `{"type": "budget_check", "agent": NAME, "platform": P, "reserve_uu": N, "left_today_uu": M}`.
- **While Claude Code runs** (`agent run`, the cli chat and the ACP chat), umwayi runs a receiver for that run only, on 127.0.0.1 and a free port, and points Claude Code's own telemetry at it with a fresh secret header. Every `OTEL_*` variable you set, `BETA_TRACING_ENDPOINT` and `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA` are removed first, so no export goes elsewhere, and prompts, responses and tool details stay off. The receiver keeps counts only (cost, tokens by type, requests, model names) and drops every body. Above `per_run`, the agent is stopped like a timeout, with exit 3. A report umwayi cannot count (a number below 0 or above 10^12, a float or a string where a count belongs, a body over 1 MB, more than 16 MB in all) stops the run with exit 2 and settles the full reservation.
- **The receiver against a local client** (the security scan, S.2): only the exact run header, given once; one Content-Length and no Transfer-Encoding; every request cut at 10 s however slowly it arrives (S-Q6); at most 16 requests at once, one more answered 503 at once (S-Q7). A refusal after the run header matched makes the run invalid; one before it is only counted.
- **The reading** is tagged `measured` (Claude Code's own report), `declared` (rates in `units.yaml`) or `unknown`. Unknown counts at `unknown_worst_case`, never zero. Kiro sends umwayi nothing, so a Kiro run is whatever `units.yaml` declares (`runs`, or `credits` times your own credits per run), otherwise unknown.
- **The ledger is the logbook** (no second file): reserve, settle and change entries with source `umwayi budget`, in fixed shapes, chained once you started the hash chain (`umwayi logbook seal --chain`). A budget entry that is not one of those shapes stops every start (exit 2), like a broken chain. If umwayi is killed (SIGKILL) during a run, its reservation counts in full until you run `umwayi budget settle-lost --by YOU`, which settles it as unknown.
- **Calibrate** only after at least 20 measured runs over at least 7 days: it proposes `per_run` = 1.5 times the 95th percentile of one run and `per_day` = 2 times the median day, with the data. It changes nothing; you edit `units.yaml`, and that change is logged before it is used.
- **units.yaml** in the root (optional; without it every reading is unknown under the placeholders). Whole numbers only. Every rate has a value, a date (not in the future) and a source (`owner` or an https URL):

  ```yaml
  version: 1
  platforms:
    claude-code:
      reading: usd_micros       # measured from Claude Code's own report
      fallback: tokens          # only token counts arrived: use the rates below
    kiro:
      reading: runs
      run_micros:               # micros of a dollar per run (400000 is 40 UU)
        value: 400000
        date: 2026-11-09
        source: owner
  models:                       # micros per million tokens
    claude-sonnet-5:
      input:
        value: 3000000
        date: 2026-11-09
        source: https://example.com/pricing
  limits:
    per_run: 100
    per_day: 500
  ```

- Exit codes of `budget` commands and of a start: 0, 2 (No, a logbook or ledger problem, a change that cannot be logged, an invalid report), 3 (a limit, before or during a run; Ask me first; the kill switch; the run lock), 64 (usage or a bad `units.yaml`). Never 1.
- Not checked against a real Claude Code export yet: the exact JSON shape comes from the docs. Run the owner's capture first (`UMWAYI_TELEMETRY_CAPTURE`, tasks.md B.10). Limits: KNOWN-LIMITS 110 to 128.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-10 | The receiver: a 10 s whole-request deadline, at most 16 requests at once (503 for more), and the run header and Content-Length each exactly once, no Transfer-Encoding | The security scan (S.2, PR 37; S-Q6, S-Q7): a trickling client held a thread without end, 200 connections made 202 threads, and a second header was ignored. |
| 2026-11-10 | A negative cost is invalid on every path (400, the run stopped with exit 2, the full reservation settled) | The owner's review of PR 33: no report may subtract from a run. |
| 2026-11-09 | B-Q1 to B-Q3: the ledger is read from chained logbook entries only; an unknown run counts at 100 UU, including Kiro; `calibrate` only proposes | Approved in PR 24; built in PR 33. |
| 2026-11-09 | B-Q4 to B-Q6: a reservation without a settle counts in full until `settle-lost`; forged reports are a known limit; the cap and the receiver also cover the cli chat | Approved in PR 24; built in PR 33. |

## Open questions

- B.10: the owner's capture of one real Claude Code export (`adapters/NOTES-layer10.md`, "Budget governor: Claude Code telemetry").
