# Rules (layer 2)

## Purpose

The rules layer answers Yes, No or Ask me first for every action before an AI helper, job, workflow, adapter or agent takes it, from the owner's `rules.yaml`. It exists so nothing acts without a rule the owner wrote, and so a missing or broken rule never means Yes.

## Current state

Rules live in `rules.yaml`. Each rule has an id, a title, text, a verdict (`yes`, `no` or `ask`), and optionally a cause, matchers and, on a Yes rule, a `review_by` date.

```
umwayi check '{"type": "payment", "amount": 5}'
```

Prints the answer, the rule id and the reason:

```
No
Rule: no-money
Reason: AI helpers never move money or use bank or card credentials. Cause: Safety rule for all AI helpers.
```

| answer | exit code |
| --- | --- |
| Yes | 0 |
| No | 2 |
| Ask me first | 3 |

Fail closed: no matching rule, a broken or missing `rules.yaml`, or bad action JSON all give Ask me first. If several rules match, No beats Ask me first, and Ask me first beats Yes. Usage errors exit with 64. The rules file (`rules.yaml` or `--rules PATH`, or a link to one) is read only when it is a regular file of at most 1 MB; anything else, `/dev/zero` or a FIFO among them, is a broken rules file and gives Ask me first.

Matchers (all must match):

- `type: payment` equals, ignoring case
- `type: [payment, transfer]` equals any
- `path__contains: secret` contains text
- `amount__exists: true` field is present

Use `--rules PATH` for another rules file, `--json` for JSON output, and `-` as the action to read it from standard input. `--kill-switch` answers No while the kill switch is on or its state is unknown (the adapters use it; without it your own checks are not stopped).

Every check writes one logbook entry with the rule id and the answer. The action JSON is never written, only its `type` if that is a short plain word. If the logbook cannot be written (for example it was edited by hand), a No stays No (exit 2), a Yes becomes Ask me first (exit 3), and the reason says why. Use `--no-log` for a dry run that writes nothing, and `--date` to set the entry date.

### Starter rules for the adapters (task 9.10)

The repo `rules.yaml` ends with starter rules for the actions that the Claude Code, Kiro, generic and OpenCode adapters send. Each rule names its platform (`claude-code`, `kiro`, `stdio` or `opencode`), so a rule for one never answers for another. The ids, verdicts and matchers are the ones in `adapters/claude_code/rules.example.yaml`, `adapters/kiro/rules.example.yaml`, `adapters/stdio/rules.example.yaml` and `adapters/opencode/rules.example.yaml`. The OpenCode rules were added last, after the three groups of 9.10, and are described under the table.

| what the AI helper does | answer | rule ids |
| --- | --- | --- |
| reads, lists or searches files | Yes | `cc-read`, `kiro-read`, `stdio-read` |
| writes, edits or deletes a file | Ask me first | `cc-ask-write`, `kiro-ask-write` |
| runs a shell command (this covers installing, publishing, sending and deleting one file) | Ask me first | `cc-ask-shell`, `kiro-ask-shell` |
| fetches a web page or searches the web | Ask me first | `cc-ask-web` |
| deploys (generic adapter) | Ask me first | `stdio-ask-deploy` |
| wipes folders or disks, pushes to main or forces a push, names a payment service | No | `cc-no-destroy`, `kiro-no-destroy`, `cc-no-push-main`, `cc-no-money` |
| changes or names `rules.yaml`, `autonomy.yaml`, `LOGBOOK.md`, `.umwayi`, `.git` or the hook settings, or runs `umwayi decision` or `umwayi autonomy` | No | `cc-no-guard-edits`, `cc-no-guard-shell`, `kiro-no-guard-edits`, `kiro-no-guard-shell` |
| touches a secret or key path (`.env`, `.pem`, `id_rsa`, `id_ed25519`, `.aws/credentials`, `.netrc`) | No | `cc-no-secrets`, `kiro-no-secrets`, `stdio-no-secrets` |
| deploys to production (generic adapter) | No | `stdio-no-prod` |
| anything else (other tools, MCP tools, helpers' own sub tasks) | Ask me first | no rule matches |

- Two rules are not in the example files: `kiro-no-secrets` and `stdio-no-secrets`. They are the secret path rule of `cc-no-secrets` for the other two adapters.
- The table above is for the first three adapters. OpenCode has its own table below.
- No starter rule has a `review_by` date. A Yes rule gets one only when the owner wants it reviewed.
- Matching is plain text and not a shell parser, so a command can be written to get past it. Ask me first for every shell command is the real guard. Keep hard limits in the platform's own deny rules too.
- The Kiro rules that look at `input_command` and `input_path` work only if Kiro uses those field names (KNOWN-LIMITS 21). If it does not, a Kiro call is still Ask me first, except reads, which stay Yes.
- `tests/test_starter_rules.py` loads the file with the real parser and checks every rule, the ids, a table of adapter actions and an unknown action.

#### OpenCode

The 13 rules of `adapters/opencode/rules.example.yaml` follow the others in the file, with the same ids (all start with `oc-`), verdicts, matchers and words. Every one has `platform: opencode`. OpenCode sends two kinds of action, one for each gate (see [adapters](adapters.md) and `adapters/NOTES-layer10.md`): a tool call from the umwayi plugin (`tool_read`, `tool_shell` and so on, with `input_path` and `input_command`), and a permission request (`acp_permission` with a `kind`).

| what OpenCode does | answer | rule ids |
| --- | --- | --- |
| reads, lists or searches files (`tool_read`, `tool_glob`, `tool_grep`) | Yes | `oc-read` |
| a permission request of the kind `read` or `search` | Yes | `oc-perm-read` |
| writes or edits a file | Ask me first | `oc-ask-write` |
| runs a shell command (this covers installing, publishing, sending and deleting one file) | Ask me first | `oc-ask-shell` |
| fetches a web page | Ask me first | `oc-ask-web` |
| starts a sub agent or asks a question | Ask me first | `oc-ask-agent` |
| a permission request of any other kind (edit, delete, move, execute, think, fetch, switch_mode, other) | Ask me first | `oc-perm-ask` |
| names a payment service, pushes to main or forces a push, wipes folders or disks | No | `oc-no-money`, `oc-no-push-main`, `oc-no-destroy` |
| changes or names `rules.yaml`, `autonomy.yaml`, `LOGBOOK.md`, `.umwayi`, `.git`, `opencode.json`, `opencode.jsonc` or the `.opencode` folder, or runs `umwayi kill`, `umwayi decision` or `umwayi autonomy` | No | `oc-no-guard-edits`, `oc-no-guard-shell` |
| touches a secret or key path | No | `oc-no-secrets` |
| Code Mode (`tool_execute`) and the tools inside it (`tool_opencode_*`), and any tool not listed | Ask me first | no rule matches, on purpose |

- **Code Mode has no rule on purpose.** Ask me first beats Yes, so an Ask rule for `tool_execute` or `tool_opencode_*` would make a Yes rule of the owner's for them useless. With no rule they are Ask me first anyway, and the first gate stops them, because OpenCode asks no permission for them. To allow one, write a Yes rule for its type (the example file shows one). A test fails if the file gets a rule for these types.
- The permission rules see only the kind, never the path or the command; the first gate has already looked at those.
- Nothing about the other groups changed: no rule above this section was edited, and an action from another platform gets no answer from the `oc-` rules. A test pins each older rule by a hash of what it says.
- `tests/test_starter_rules.py` has the OpenCode checks: every example rule is in the file with the same verdict and matchers, the decisions table is run with the real `umwayi check` on a real root, the older rules are unchanged, and planted faults (a verdict changed, a matcher dropped, a rule missing, an Ask rule for `tool_execute` added) are found.

### Review dates: a Yes rule that runs out (layer 13, elections)

A Yes rule may have `review_by: 2026-12-01` (a real date, `YYYY-MM-DD`). The rule is in force through the whole of that day. From the next day it counts as an Ask me first rule in every check: `umwayi check`, the agent gates, the schedule, and the callers that have no logbook (jobs, AI helpers, `publish-draft`, the inner checks of a workflow). The file is not edited and the rule is not deleted; the owner renews it by editing the date.

- `review_by` is allowed on Yes rules only. On a No rule, on an Ask rule, or with a date that is not real (`2026-13-01`, `2026-2-1`, `20261101`, `tomorrow`, a list, an empty value), `rules.yaml` is malformed and every check gives Ask me first. Do not put `review_by` in a rules file before this version is installed: the older code calls it an unknown field.
- The date of a check is the latest of the system date, `--date` and the newest date in the logbook, so a past `--date` or a clock set back does not bring a lapsed rule back. If the logbook cannot be read, the first two are used (and the entry cannot be written, so no Yes comes out).
- Strongest wins as before, with the lapsed rule counted as Ask me first: a matching No still gives No, and a lapsed Yes beside a Yes that has not lapsed gives Ask me first.
- The fallback is logged. The check's own entry ends its Checked line with `; election fallbacks: report-yes (review_by 2026-11-20)` for every matching rule that fell back (ten are named, then `, and N more`). `--json` adds `"election_fallbacks": ["report-yes"]`, and the text output adds an `Election fallbacks:` line. When no rule fell back, the entry, the JSON and the text are the same bytes as before.
- A rule with no `review_by` never lapses. That is the owner's choice.

```
umwayi rules due [--within DAYS] [--date YYYY-MM-DD]
```

Lists every rule that has lapsed, is due within DAYS days (default 14, from 0 to 3650), or has a date more than 366 days ahead (`far`; it is still in force, the word is a warning). Oldest first, then by id, and the number of Yes rules that have no `review_by`:

```
lapsed  2026-11-01  report-yes  10 days ago
due     2026-11-20  weekly-yes  in 9 days
far     2030-01-01  old-yes     in 1147 days
Yes rules without review_by: 2
```

It writes nothing (no file, no logbook entry) and prints no rule title, text or cause. Exit 0 when no rule has lapsed. Exit 3 when one has, or when `rules.yaml` is missing or broken (it says it cannot list). Exit 64 for a bad argument, 2 for an unexpected error. It never exits 1.

### The rules change log (layer 13, courts)

Before new rules are used, the change is logged. Every check, and every other command that asks the rules (`umwayi check`, the agent gates, the schedule, `umwayi run`, the AI helpers, `publish-draft` and the inner checks of a workflow), hashes the exact bytes of `rules.yaml` it read. When the SHA-256 is not the one of the newest `umwayi rules` entry, it first writes one entry with the hash, the number of rules before and after, the ids added and removed, and each changed verdict or `review_by`, for example `changed no-money verdict no to yes`. The first time, the entry is a baseline (`rules.yaml first logged`). An edit that changes no id, verdict or date (a comment, spacing, the order) is logged as `no rule changed`, because the bytes changed. The entry holds no rule title, text or cause. More than 200 rules are counted, not listed, and the next change is logged as a new baseline.

- If the entry cannot be written (the logbook lock is held, the logbook was edited, the hash chain is broken), the new rules give No and Ask me first only: a Yes becomes Ask me first, and the reason says why. A No stays a No. The next check that can write logs the change.
- A weakened rule is used at once: the entry makes the weakening visible and dated, it does not hold it (L13-Q11). A change of a rule's title, text or matchers is seen only through the hash ([KNOWN-LIMITS](KNOWN-LIMITS.md) items 193 and 194).
- A dry run (`--no-log`) writes nothing, so it logs no change either, and it answers from the rules as they are (L13-Q19, proposal used). A dry run approves nothing.
- The change is logged only when the rules are used: an action that is not readable JSON, or a `rules.yaml` that does not parse, gives Ask me first as before and logs no rules entry.
- `rules due` and `view snapshot` only read the rules, so they log nothing.

### The autonomy opt-in (layer 13, graded autonomy)

An `ask` rule may carry `autonomy` with three entries, `class`, `reversible` and `cost_uu`, and must then have a `type` matcher (equals). It is the only way an Ask me first can ever be moved to Yes, and only while `autonomy.yaml` turns graded autonomy on ([autonomy](autonomy.md)). With it, the rule may also carry `review_by`, so a standing permission to be moved runs out too.

```yaml
  - id: commit-ask
    title: A commit on a feature branch is asked
    text: The owner is asked before an AI helper commits.
    verdict: ask
    review_by: 2027-02-01
    autonomy:
      class: git-commit
      reversible: true
      cost_uu: 2
    matchers:
      type: tool_bash
      command__contains: git commit
```

- `rules.yaml` is malformed (every check gives Ask me first) when `autonomy` is on a Yes or No rule, has another shape, is on a rule without a `type` equals matcher, names a type of the never list (`payment`, `transfer`, `purchase`, `withdraw`, `deposit`, `publish`, `post`, `send`, `publish_draft`, `schedule_install`, `budget_check`, `agent_run`, `agent_login`, `acp_permission`), or when two rules give one class a different `reversible` or `cost_uu`.
- The rules change log lists the opt-in in its state (`commit-ask ask review_by 2027-02-01 autonomy git-commit reversible yes cost 2`), so turning `reversible` to true, or a lower cost, is named in the entry.
- Only a Yes rule lapses at its `review_by` (elections). An opt-in rule past its date stays Ask me first and is held by its own gate (`opt-in-lapsed`).

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-11 | An `ask` rule may opt its class in to graded autonomy with `autonomy`; the never list and the agreement of two rules are checked when the file is read; only a Yes rule lapses at `review_by` | Layer 13, L13.5 (13.R9.2, 13.R9.3, 13.R2.2). |
| 2026-11-11 | Every caller that asks the rules logs a changed `rules.yaml` before it uses it; if that cannot be written, a Yes becomes Ask me first; a dry run logs nothing and keeps its answer | Layer 13, L13.3 (13.R7; L13-Q11 and the new L13-Q19 as proposed). |
| 2026-11-11 | The 13 rules of the OpenCode example are in the repo `rules.yaml` too, after the older ones and unchanged beside them; Code Mode has no rule, so an owner's Yes for it can take effect | The OpenCode starter rules pull request (a follow-up of 9.10 and 10.45; see [adapters](adapters.md)). |
| 2026-11-11 | The repo `rules.yaml` holds starter rules for the actions the three adapters send, taken from the example files, with the strictest verdict the examples give; `kiro-no-secrets` and `stdio-no-secrets` are added because the examples have no secret rule for those two; no starter rule has `review_by` (9.10) | Task 9.10, PR 43. |
| 2026-11-11 | A Yes rule past its `review_by` counts as Ask me first, in every caller of the rules; a lapsed Yes beside a fresh Yes gives Ask me first (L13-Q16, proposal used); `rules due` exits 3 when a rule lapsed (L13-Q9, proposal used); a date more than 366 days ahead is listed as `far` (L13-Q10, proposal used) | L13.1, 13.R2 and 13.R3. |
| 2026-11-10 | The rules file is read only as a regular file of at most 1 MB | The security scan (S.2, PR 37): a rules file that was a link to /dev/zero made `umwayi check` read forever. |
| 2026-11-08 | `umwayi check --kill-switch` answers No while the kill switch is on or unknown (9.12) | Layer 9, PR 12: the owner answered that adapters deny everything while the kill switch is on. |
| 2026-11-08 | `umwayi check --json` gives `answer`, `rule_id`, `rules_ok`, `action_ok` and `logged` (9.2) | Layer 9, PR 11: an adapter never reads the reason text. |
| 2026-11-08 | When the logbook cannot be written, a No stays No (exit 2) (6.5) | Layer 6, PR 6: a refusal is never weakened by a logbook failure. |
| 2026-11-07 | Fail closed: no matching rule, a broken or missing `rules.yaml`, or bad action JSON give Ask me first; No beats Ask me first beats Yes (2.3) | Layer 2, PR 1: an unknown case is never a Yes. |

## Open questions

None.
