# Use per goal: a design note (M4 h, the next part)

Docs only. Nothing here is built. It settles how the governor will know what a goal has used, so that a goal share (docs/budget-governor.md,
`umwayi/goalshare.py`) can say what is left and not only what is allowed.

## Purpose

A goal has a share of a provider's allowance. Today `umwayi budget status` lists the share and the full caps, and says that use per goal
is not recorded. To make a task wait ("waiting, daily cap") or be refused ("task_larger_than_cap"), the governor needs one number per
goal and window: what the goal has used.

## Current state (read from the code, 2026-11-25)

- The ledger is the chained logbook, entries with source `umwayi budget` only, in three fixed shapes: `reserve`, `settle` and `change`
  (`umwayi/budget.py`). Anything else with that source is a ledger problem, exit 2.
- A `reserve` line names the run, the agent, the platform and the micros. It does not name a goal. A `settle` line gives the real micros.
- A day is the logbook date of the reservation. The CLI takes it from `date.today()`, the clock of the machine: Nairobi on the owner's Mac,
  UTC on a CI runner. `goalshare.nairobi_day` takes an aware time and is not wired in. The two must agree before a daily cap can stop a task.
- A run does not know its goal: the agent start (`umwayi/agents.py`) gets an agent name, not a goal name.

## Options

1. **A fourth fixed shape**, written next to the reserve: `Run R counted for goal G on provider P`. The reserve and settle shapes do not
   change, so every old logbook still parses. The reader adds the settled micros of run R (or the reserved micros while it is unsettled,
   as B-Q4 already does) to goal G.
2. **An optional suffix on the reserve line**: `... (100 UU) for goal G`. One line per run, but the strict pattern of the reserve changes,
   and a reader of the old shape must be updated at the same time.
3. **A second file** of goal use. Rejected: the approved answer B-Q1 is that there is no second ledger file.

## Recommendation

Option 1. It is additive: a logbook written before the change has no such lines and every goal reads as 0 used, which is true. A run
with no goal writes no such line. The new shape needs its own planted-fault test (a malformed line is a ledger problem, a line for an
unknown run is a ledger problem, a goal not in units.yaml is a ledger problem).

## What would be built, in order

1. The new shape and its reader: `used_by_goal(ledger, goal, window)` as a pure function (a ledger change: owner stop).
2. The start passes a goal name and the governor writes the line with the reserve (a start in `agents.py`: owner stop, and a guard file).
3. `umwayi budget status` shows used and left per goal, today, this week, this month.
4. `cap_gate` is called before a task starts: a wait writes "waiting, daily cap" to the logbook, a refusal writes `task_larger_than_cap`.

Each is its own pull request. Step 2 is where a share first stops anything, so its story must say so.

## Open questions, each with a recommendation

- **Q-g1.** Where does a run get its goal name? Recommendation: the goal supervisor passes it to the start as an argument; an agent that
  is started by hand has no goal and counts only against the provider.
- **Q-g2.** Which clock is the day? Recommendation: the Nairobi day from an aware time, set in one place and used by both the ledger and
  `goalshare`; until then the CLI date is the machine's local date and the note says so.
- **Q-g3.** Does a goal's use count the reserve or the settle? Recommendation: the settle once it exists, the reserve in full before
  that, the same as the daily limits (B-Q4).
- **Q-g4.** Does a run that spans two windows count in the window of its reservation? Recommendation: yes, the same as a day today.

## Decisions log

- 2026-11-25 (this note): option 1, a fourth fixed shape; no change to the reserve and settle shapes.
