# The owner status screen (W77, design note)

## Purpose

Today `umwayi goal status`, `umwayi up` and the local read-only pages show state, but nothing lists, in one place, everything that waits for the owner. This note designs `umwayi owner` and a matching read-only page.

`umwayi owner` gives one list of the items that need the owner, each with:

- its id;
- what is blocked;
- the question and the recommendation;
- the exact command that answers it;
- its age.

Below the list: the budget left, the tasks in `needs owner`, the stalled sessions and the last logbook head.

It is a design note only. No code, rule, steering file, safety check, workflow or exit code changes with it.

## Current state

Read at main `25b3a47`. Each piece exists somewhere today; nothing puts them together:

| what waits | where it is today | how it is answered today |
| --- | --- | --- |
| a goal plan that waits for approval | `goal.json` (`plan.asked`, `plan.deadline`, `plan.answer` empty); shown under "Waiting for you" by `goal status` (`goal.status_lines`) | `umwayi goal approve G-NNNN ...` after `umwayi goal show G-NNNN` |
| a task in `needs owner` with an approval | `T-NN.json` (`approval` with `asked` and `deadline`; `reason`; `blocked` with rule, answer and type since W56); "Waiting for you" in `goal status`; the W60 idle line `Waiting for you: T-NN needs an answer.` | `umwayi goal answer G-NNNN T-NN yes` or `no` |
| an open decision in the queue | `queue.md` rows of kind `decision`, with a recommendation. Many are added by an Ask me first: `agent run`'s `agent_run` and `budget_check` asks, a helper step, an adapter | `umwayi queue answer Q-NNNN --answer TEXT --revisit-if TEXT\|none` |
| an open task in the queue | `queue.md` rows of kind `task` | `umwayi queue close Q-NNNN` |
| a petition against a rule | a decision row titled `Petition against rule RULE_ID by HELPER`, its reason marked untrusted | as any decision |
| a Yes rule past its `review_by` | `umwayi rules due` (exit 3 when one lapsed) | edit the date in `rules.yaml` |
| the kill switch on or unknown | `umwayi kill status` | `umwayi kill off` |
| a logbook that fails its check | `umwayi logbook verify` | read the problem lines; nothing turns it off |
| the budget left today | `umwayi budget status` | none (information) |
| a stalled or quiet task | `QUIET for N min` and `STALLED soon` in `goal status`; `umwayi stalls check` reads a JSON file that nothing produces ([stalls](stalls.md)) | `umwayi goal stop G-NNNN`, or wait |
| the logbook head | `umwayi logbook anchor` prints `COUNT:HEX` | keep it elsewhere |

Steward's draft (`umwayi steward`) lists the open queue items, the late ones and suggested next tasks, but it is a draft file, not a status screen. The work ledger of W65 is designed, not built (branch `w65-work-ledger-design`).

## The design

### What `umwayi owner` prints

```
umwayi owner [--date YYYY-MM-DD] [--json]
```

One list, then four lines. Example:

```
Waiting for you (3)
  G-0007 T-02  needs owner (ask)  blocked: rule cc-ask-shell gave Ask me first for tool_bash, command word git
    question: allow this task to go on?   recommendation: none
    answer:   umwayi goal answer G-0007 T-02 yes   (or no)            asked 3 h ago, denied in 21 h
  Q-0014       decision (Ask me first)  blocked: agent claude-build was not started (agent_run)
    question: Start agent claude-build (run)?   recommendation: add a Yes rule for agent_run
    answer:   umwayi queue answer Q-0014 --answer TEXT --revisit-if TEXT|none   asked 2 days ago
  G-0008       plan waits for approval  blocked: nothing starts until approved
    question: approve the plan?   recommendation: read it first: umwayi goal show G-0008
    answer:   umwayi goal approve G-0008 ...                            asked 40 min ago, denied in 167 h
Budget left today: 412 of 500 UU (per_day)
Tasks in needs owner: 1
Stalled: none
Logbook head: 2187:9f2c...e1a0 (chain intact)
```

- **The list is sorted by age, oldest first, then by id.** Same input, same answer:
  - the clock is the latest of the system date, `--date` and the newest logbook date (`rules.election_clock`), as for the rules;
  - the ages come from stored times only: an approval's `asked`, a queue row's `umwayi queue add` logbook entry, the plan's `asked`;
  - an item whose time cannot be read gets `age unknown` and sorts first.
- **Each item names the exact command that answers it,** with the ids filled in. umwayi never runs it. Owner commands need a terminal, as today.
- **The question and the recommendation** are copied from the record (the queue row's title and recommendation, the task's `blocked` fact) and cut to one line. A petition's reason keeps its "untrusted text from an AI helper" mark. A recommendation that does not exist prints `none`, never a made-up one.
- **What is blocked** uses only umwayi's own fixed words: a reason word, a rule id, an action type, the W55b command word. Never a helper's text.
- **The four lines:**
  - **Budget left today:** from the budget ledger in the logbook, as `budget status`.
  - **Tasks in needs owner:** a count over the goal task files.
  - **Stalled:** each running task whose last real event is older than the stall time (30 minutes), with its goal and task id, as `goal status` decides it. With the W65 work ledger built, its stall states instead.
  - **Logbook head:** the `COUNT:HEX` of `logbook anchor`, and whether the chain verifies.
- **`--json`:** the same items and lines as one JSON object with fixed keys, for the page.

### What it reads, and nothing else

- the goal files under `.umwayi/goals/` (and the W65 work ledger once built);
- `queue.md`;
- the logbook, read with its tamper check;
- `rules.yaml`, for the `review_by` dates;
- `units.yaml`;
- the kill switch state.

It makes no model call, opens no network connection, starts no process and takes no lock. It writes nothing, not even a logbook entry. It works while a goal runs and while the kill switch is on.

### Exit codes

The owner asked for:

- 0: nothing waits.
- 2: items wait.
- 3: at least one item is an Ask me first (a queue decision added by an Ask me first, or a task in `needs owner` with reason `ask`).
- 64: usage or a bad config.
- Never 1.

**One conflict to decide:** product rule 8 says every unexpected error exits 2 ("a crash blocks"), so exit 2 would mean both "items wait" and "an error". The proposal keeps the codes as asked, and says which in the output:

- an error prints one line starting `owner: could not list:` on standard error, with nothing on standard output;
- "items wait" prints the list.

A record that cannot be read becomes an item ("goal G-0007 could not be read") with exit 3, never a quiet gap (open question 1).

### How an owner's answer is recorded, and how the supervisor sees it

Nothing new is needed: each answer goes through the command that exists today, and `umwayi owner` only names it.

- **`umwayi goal answer G T yes|no`** writes `Approval answered: task T of goal G, answer yes|no` to the logbook (`goalstate.approval_answered_entry`) and closes the queue row of the approval.
  - Yes moves the task back to `queued` (reason `answered`). No moves it to `stopped` (reason `owner`).
  - The supervisor sees it at the next `umwayi goal run`, which reads the goal files after its tamper check and picks the first queued task. That start still asks `goal_start` like every start.
- **`umwayi goal approve`** writes the approval entries and queues the tasks.
- **`umwayi queue answer`** writes the answer's logbook entry, which holds its length, not its text, and the `revisit-if` text.
  - An answer never lets a stopped run go on by itself: only a Yes rule does (`tests/test_helpers.py` `test_answering_the_queue_item_does_not_let_the_helper_go_on`).
  - So for an Ask me first item, the list's recommendation names the rule to add, and the answer only records the owner's choice.
- **After any answer,** the next `umwayi owner` shows the item gone, because it reads the same records.

### The read-only page

- **A new read route in `umwayi serve`:** `owner.list`, `GET /v1/owner`, class `read`, not stopped by the kill switch, body cap 0, exit codes as the command. It calls the same function as `umwayi owner --json`.
- **The page shows the list and the four lines.** Each command is shown as text to copy into a terminal, because the owner commands need one.
- **It can answer nothing.** A queue answer stays the existing `queue.answer` route. A goal approval or answer stays the terminal's.
- **`umwayi serve` stays local** (127.0.0.1 and a token), as the owner decided for W74.

### The one function

`owner.items(records, now)` is pure: it takes the parsed records and the clock, and returns the sorted items and the four lines. `umwayi owner`, `--json` and the page call it, and `goal status` and `umwayi up` can call it later in place of their own "Waiting for you" lines, so there is one rule for what waits. This is the same shape as `goalpacket.idle_line` of W60.

## What it cannot show

- **Anything outside umwayi's own records.** It does not show pull requests waiting for review or merge, CI results, or GitHub notifications (the W72 GitHub connector would be the way). It does not show a Kiro or Claude Code permission prompt on a screen umwayi did not start, or a question a helper wrote only in its own output.
- **Whether a recommendation is good.** It copies what the record holds.
- **The time left of a queue row.** Queue rows have no deadline, only an age. Goal approvals have both.
- **Spend the platforms do not report** (Kiro and OpenCode are declared or unknown).
- **A stall of a helper umwayi did not start,** or of a goal run that is not running.
- **Anything after it printed.** It is a snapshot. Nothing watches, and nothing is sent anywhere.

## The tests it would need

| rule | test | planted fault |
| --- | --- | --- |
| one list of every kind | `test_each_kind_of_waiting_record_is_one_item` (plan, task approval, queue decision, queue task, petition, lapsed rule, kill switch, logbook problem) | skip queue tasks |
| sorted by age then id | `test_items_sort_oldest_first_then_by_id` | sort by id only |
| same input, same answer | `test_the_same_records_and_date_give_the_same_bytes` | read the wall clock inside the function |
| the exact command | `test_each_item_names_its_answer_command_with_its_ids` | print `umwayi goal answer` with no ids |
| no made-up recommendation | `test_a_missing_recommendation_prints_none` | print a fixed tip |
| fixed words only | `test_no_helper_text_reaches_the_list` (plant text in an events file) | show the last output line |
| read only | `test_owner_writes_no_byte` (a snapshot of the root around the command) | log an entry |
| no network, no model | `test_owner_imports_no_network_module_and_starts_no_process` | call `agent run` |
| exit codes | `test_exit_0_nothing_2_items_3_ask_64_usage` and rows in `tests/test_exit_codes.py` | exit 1 on an error |
| unreadable record | `test_an_unreadable_goal_file_is_an_item_and_exit_3` | skip it |
| the page | `test_owner_route_returns_the_same_json_as_the_command` | a route with its own list |

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-16 | Design note only. One pure function lists every record that waits for the owner, with the command that answers it, sorted by age then id; `umwayi owner`, its `--json` and a read route call it; answers go through the commands that exist | W77, the owner's task of Nov 16. |

## Open questions

1. **Exit 2 for "items wait" and for an error.** Recommendation: keep the codes as asked, and tell them apart by output: the list on standard output for items, one `owner: could not list:` line on standard error for an error. Or use 3 for every item and keep 2 for errors only, which matches the other commands. The owner chooses.
2. **Should `goal status` and `umwayi up` use the same function for their "Waiting for you" lines?** Recommendation: yes, in the build task, with their goldens updated, so there is one rule for what waits.
3. **Show pull requests that wait for the owner?** Recommendation: not in `umwayi owner`. It reads only umwayi's records. Add a line from the W72 GitHub connector later, marked as read from GitHub.
4. **A deadline for queue rows?** Recommendation: no change now. Show their age only, and mark a decision older than the Steward late limit (7 days by default) as `late`.
5. **The stall line before W65.** Recommendation: use the stall time of `goal status` (30 minutes since the last real event) now, and switch to the work ledger's states when W65 is built.
