# Muse as a helper, on the owner's free credits (M1, design note)

## Purpose

This is the design note for the Muse route: Meta's Muse Code CLI (`muse`) as a helper that umwayi can start, next to Claude Code and OpenCode. Kiro is paused (M7). The owner chose the order: the CLI first, paid for by the owner's free credits; the API later. No plan and no payment is needed now.

This note is docs only. It changes no code. It settles the words, the limits and the order of the tasks M2 to M7, so that each of them can be built and checked on its own. Nothing here is enforced by umwayi today. Where a rule is only asked of the helper, the note says so.

The main point of the budget part (M4), in the owner's words of 2026-11-23: the governor exists first of all to keep a user inside the limits of their subscription or credits, so that the limit is not reached early without the user knowing. Catching an overspend after the fact is the second job.

It builds nothing, runs no model call and reads no key or token. It does not say Muse is enforced, and it does not claim the route works: M2 builds it behind a fake and M3 is the first real check.

## Current state

Checked on 2026-11-23 (task M0, read only, no model call, no key or token read):

- `muse` is on the PATH, version `Muse Code 1.4.25`. A stored sign-in works (`muse usage` exits 0). `META_API_KEY` is not set.
- `muse exec` takes `--json`, `--prompt-file`, `--permission-profile`, `--model`, `--contributor-mode`, `--workspace`, `--max-model-steps`, `--session-id`, `--disable-web-tools`, `--api-key-stdin`, `--base-url`. Exit codes: 0 turn complete, 1 failed or cancelled, 2 usage, 130 or 143 on a signal. Exit 0 does not mean the work is right: umwayi gates on its own test command.
- Muse has permission profiles (Ask me, Auto-review, Unrestricted, Read-only), approval modes, an OS sandbox on shell commands (bubblewrap on Linux, Seatbelt on macOS) and hooks (`.muse/hooks.json`, events such as `PreToolUse` and `PermissionRequest`). Hooks run outside the sandbox and MCP tools are not sandboxed. I found no read-only command that says whether the sandbox is on.
- A start in umwayi is a row in `PLATFORMS` of `umwayi/agents.py`, an argument list from `build_argv`, an environment function, the process start in `_start`, the gate checks, and for an enforced Claude Code run the broker and the confinement. A new platform means a new row, a new argv branch, a new environment function and an entry in the process-start guard of `tests/agents/test_agents_gate.py`. OpenCode (`docs/opencode-goal-helper-design.md`) is the closest model: a declared run rate, the gate through a hook, a fake for the tests and one real check by the owner.
- The governor (`docs/budget-governor.md`) knows `per_run`, `per_day`, `per_agent_per_day`, `per_platform_per_day`, `unknown_worst_case`, and the readings measured, declared or unknown. It does not know a provider's own limit, a credit balance, a weekly or monthly window, a cost kind, an acceptance by the owner, pacing, a heads up, a stop line or a goal share. Per-goal caps exist only as the plan budget and the task budgets.

### What the owner's account shows (facts, not a plan)

1. The account has no subscription. It is pay as you go with free credits in use, and the page says the balance does not rise while free credits are used. The owner writes the amount and the date in `units.yaml` when they accept (M4 a); this note does not hold it. One unit is one cent.
2. After the credits end, use is billed pay as you go to a payment method on file. The page shows a charge threshold and a billing date. The page has a "Stop using free credits" link.
3. Billing can lag by up to an hour, so one cent moving is not proof that the CLI uses the credits. This stays unproven until M3 shows two readings an hour apart (Q5).
4. Muse Code signs in by browser or by API key. Both bill the same account. umwayi never reads, prints, stores or passes on a key or a sign-in token.

### Data use on free credits

The billing page says that while free credits are in use, the content sent may be used for product improvement. This is the free-credit form of contributor mode. The `--contributor-mode` flag is for subscriptions and is not known to change it. So treat everything sent to Muse on free credits as something that may train Meta models.

Rules that follow:

- Only public umwayi-os work goes to Muse. Never code of Global Link+ or of any private or confidential repository. Never a secret, a key or a private journal entry.
- The route reads a `public: true` mark that the owner sets for the root. It never infers one. No mark, no run (refusal `private_repo_named`).
- The owner accepts this trade once, in writing, in `units.yaml` (M4 a). Until then the governor asks first.
- Every doc, post or video that mentions a Muse run says plainly: on free credits, content sent to Muse may be used by Meta for product improvement (M5).

### The gate: a hook, and what stays cooperative

umwayi enforces nothing on Muse today. Muse's own sandbox and approvals belong to Muse. umwayi checks that they are on where it can, and says so where it cannot.

- A `PreToolUse` hook in `.muse/hooks.json` asks the umwayi rules gate (Yes, No, Ask me first; fail closed). Before a run umwayi checks that the hook file is present and that the folder is trusted. If not, it refuses (`hook_file_missing`, `folder_untrusted`).
- Because I found no way to confirm the sandbox, M2 treats it as unconfirmed. It refuses `--disable-approval` unless M3 finds a way to confirm the sandbox. Until then the route runs with Muse's default approvals and the hook asking the gate.
- umwayi never passes `--yolo` or `--disable-sandbox`. `--disable-sandbox` removes confinement and forces full network; `--yolo` removes both. A request for either is refused with a fixed reason.
- The label, until W40 shows a real enforced run: **cooperative, plus Muse's own sandbox**. No doc, post or video says "enforced" for Muse.
- The hook runs outside Muse's sandbox and MCP tools are not sandboxed. A helper that spends or writes outside umwayi is not stopped by umwayi's caps. The docs say so.

### Budget by limits, credits and goal shares (M4)

This applies to every provider, not only Muse. It is checked by the umwayi governor before a task starts, so it is cooperative: a helper that spends outside umwayi is not stopped by it.

- **The provider line.** `units.yaml` gets a line per provider: `cost_kind` (`free_credits`, `subscription` or `paid`), the limit the provider sets, and an acceptance (`accepted_free: true` with the date, the amount and the source). The owner writes the acceptance; I may write it after the owner says yes in chat. No acceptance: the governor asks first.
- **Pacing before any warning.** The governor spreads the allowance over its period. A weekly allowance gives a daily share of the allowance over the days left. Free credits give the credits over the days to the next known date, or a set horizon (30 days, Q7). A goal estimate above the day's share gets a line saying so.
- **Heads up.** Once accepted, the governor does not ask again per run. It prints a line at the start of each goal (limit left, the daily share, the estimate) and a louder line when the limit left crosses 50, 20 and 10 percent of the amount at acceptance.
- **Hard stop.** A free-credit provider stops new runs at 5 percent left, so the card on file is never charged by accident. A subscription provider stops at 80 percent of the five-hour allowance or 90 percent of the weekly one. The owner raises or removes a stop by hand. A `paid` provider asks first on every goal and enforces a cap in units.
- **Reading the limit.** The CLI shows no credit balance. Claude in Chrome reads the billing page when the owner permits, and writes the number and the date into a separate `credits.yaml` (a number and a date only; Q-b). For a subscription, `muse usage` shows the allowances. Between reads umwayi counts the estimated spend of each run in the logbook and shows both numbers; a reading older than its limit is shown as stale.
- **First estimates.** Until M3 gives measured numbers, use the bands of the OpenCode best guess (reviewer 5, tester 8, builder 25 units) and say they are a guess.
- **Goal shares.** A long goal carries a share of one provider's allowance, as a percent the owner writes. From it the governor derives a monthly, weekly and daily cap and checks every task against all three. A task that does not fit the tightest cap waits (the logbook says "waiting, daily cap"); a task larger than an empty window is refused (`task_larger_than_cap`). Shares of all goals on a provider may not exceed 100 percent minus a reserve (Q9); a goal that breaks the sum is refused (`share_over_allocated`). Unused units roll into the same week and month, never past them, and used units are never given back. Windows follow the owner's local day and week (Nairobi, Q-a), not UTC. `umwayi budget status` lists, per goal, share, used, left today, this week and this month.

### Roles (M6), licence lines (M5), Kiro pause (M7)

- **Roles.** After M2 is merged and M3 is ticked: tester and guide first. A builder only after five clean tester runs in the logbook, and then the owner is asked. Tests use the fake. A real goal runs with the owner's Yes rules and permission.
- **Licence lines.** `docs/third-party.md` says what umwayi-os uses and that it ships and hosts no model. The credit line "Built with Muse Spark Open" appears only where a doc, UI or video shows a Spark Open run. No Meta logo. The data-use sentence above goes with it.
- **Kiro paused, not removed.** "Paused by the owner." Code, tests and design stay. A goal that names a Kiro role gets the fixed refusal `kiro_paused`, never a silent switch to another helper. The owner lifts the pause with one setting (Q6).

### Fixed refusal words

One fixed reason each, so a test can pin them and a person can search them. Every refusal also says the next step, as `umwayi check` does.

| Reason | When |
|---|---|
| `muse_missing` | `muse` is not on the PATH |
| `muse_not_signed_in` | the stored sign-in does not work (exit code only) |
| `credits_low` | at or under the stop line of the provider |
| `hook_file_missing` | `.muse/hooks.json` is absent or does not call the gate |
| `folder_untrusted` | Muse has not been told to trust the folder |
| `key_variable_found` | a key variable is set; umwayi removes it from the child and says only the name |
| `private_repo_named` | the root is not marked `public: true`, or a private path is named |
| `goal_share_exhausted` | the goal used its share |
| `task_larger_than_cap` | a task is bigger than an empty window |
| `share_over_allocated` | shares would exceed 100 percent minus the reserve |
| `yolo_refused` | `--yolo` or `--disable-sandbox` was asked for |
| `kiro_paused` | a goal names a Kiro role |

### The tasks, in the order I recommend

1. **M1** (this note) and **M5** (licence lines), docs only: they settle the words and the data-use lines.
2. **M7**, the Kiro pause note and `kiro_paused`: small and independent. Owner stop (a routing flag).
3. **M4**, the governor: limits, credits, shares. The biggest, and the owner's main point. It changes `units.yaml` and the governor, so it stops for the owner. Built before the route can run anything, so no Muse run starts without an acceptance and a stop line.
4. **M2**, the route behind a fake: `umwayi/muse.py` builds the `muse exec` line (always `--max-model-steps` from the step cap, always `--contributor-mode off`, never `--yolo` or `--disable-sandbox`) and starts it through the same process path as the other agents. A start in `agents.py`: owner stop.
5. **M3**, the real check on the Mac, after M2 merges: needs the owner's permission for the first run and a way to read the credits.
6. **M6**, goal roles on Muse, last. Owner stop.

## Decisions log

- 2026-11-23 (owner): CLI first, API later (`api.meta.ai/v1`, OpenAI-compatible, `muse-spark-1.3`), not built now.
- 2026-11-23 (owner): no plan and no payment; the free credits pay.
- 2026-11-23 (owner, 16:19): the governor's first job is to keep the user inside their limits.
- 2026-11-23 (owner, 16:22): goal shares, and the caps derived from them.
- 2026-11-23 (this note): the sandbox is treated as unconfirmed until M3; `--disable-approval` is refused until then.
- 2026-11-23 (this note): the account amounts are not written in this public repo; the owner writes them in `units.yaml`.

## Open questions

- **Q1.** Accept that public umwayi-os work is sent to Muse on free credits, knowing Meta may use it? Recommendation: yes for the public repo; no for anything private, confidential or from Global Link+.
- **Q2.** Hard stop at 5 percent left? Recommendation: yes, so the card on file is never charged by accident.
- **Q3.** Remove the card from the billing page until the owner decides to pay? Recommendation: leave it; the stop line is the guard. Claude in Chrome can remove it if the owner says so, and asks first, because it changes an account setting.
- **Q4.** Do free credits expire? The page showed no date. Recommendation: Claude in Chrome checks the Payment activity tab once and records any date; the pacing uses it.
- **Q5.** Does `muse exec` on the browser sign-in with no key set use the free credits? Recommendation: treat as unproven until M3 passes with two readings an hour apart.
- **Q6.** Lifting the Kiro pause. By hand, one setting, nothing automatic.
- **Q7.** Pacing horizon when no expiry is known. Recommendation: 30 days; the owner can change it.
- **Q8.** Monthly cap for a share on free credits. Recommendation: treat the pacing horizon as the month and the credits at acceptance as the month's allowance.
- **Q9.** Reserve for the owner's own use when shares are added. Recommendation: 20 percent.
- **Q10.** A share: refuse or wait when a task does not fit today? Recommendation: wait until the window opens; refuse only when a task is larger than an empty window.
- **Q-a.** The governor takes the date from the system clock. Recommendation: add `timezone: Africa/Nairobi` to `units.yaml`, compute day and week with `zoneinfo`, and test a window that straddles UTC midnight.
- **Q-b.** The credits reading would write into `units.yaml`, a guard file. Recommendation: a separate `credits.yaml` (date and number only) that the governor reads; the acceptance stays in `units.yaml`.
- **Q-c.** Data use. Recommendation: the `public: true` mark above, set by the owner, never inferred.
