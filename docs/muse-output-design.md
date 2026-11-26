# Muse output: print only the answer, and settle from the usage line

## Purpose

The real Muse run of 2026-11-25 (recorded as `umwayi-muse-real-check-mac`) showed two things in how umwayi handles what `muse exec --json` prints. umwayi echoed the whole stream (54 lines, about 30 KB) to the terminal, and it settled the run as `unknown 100 UU, tokens input 0` although Muse printed its own token counts. This note says what the stream holds, and gives options with a recommendation. Docs only: nothing is built, and no second Muse run was made for it.

## Current state

**What the stream holds** (read from the recording, Muse Code 1.4.25, `--json`, one JSON object per line):

- Every line has `schema_version`, `id`, `stream`, `sequence`, `recorded_at`, `record_type`, `durability`, `causation_id`, `payload_type`, `payload_schema_version` and `payload`.
- The answer is in the line with `payload_type` `run.terminal.completed`: `payload.terminal` is `completed` and `payload.text` is the final text (the run said `2`). A run that did not complete would have another `terminal` word and a `reason`; those words are not known yet.
- One line has `payload_type` `run.usage`, with `payload.models[]` (each `model`, `input_tokens`, `cached_tokens`, `output_tokens`, `reasoning_tokens`, `calls`), the totals `calls`, `completed_calls`, `failed_calls`, `cancelled_calls`, `children_included` and `allowance` (null in that run).
- The model named in the usage line was `muse-spark-1.3-contributor` although `--contributor-mode off` was passed.
- Two lines before the stream, on standard error or standard output, say `workspace root`, the untrusted workspace and the MCP warning. They are not JSON.

**What umwayi does today:** it prints the child's output as it comes, and settles with the reading it has for the platform. For Muse there is no telemetry receiver, so the reading is `unknown` and the full reservation (100 UU) counts. The limit is safe but coarse.

### Options

#### For the output

1. **Print only the final text.** umwayi reads the lines, finds `run.terminal.completed`, prints `payload.text` and one count line (lines read, lines that were not JSON). The raw stream goes nowhere on the terminal; a flag `--raw` keeps it for the owner.
   For: a person sees the answer. Against: a change to the output parser can hide a line the owner wanted, so the count line and `--raw` are needed.
2. **Leave it as it is.** Cheapest, and the raw stream stays visible. Against: 30 KB for one word.

#### For the settle

1. **Read `run.usage` for the settle** and tag the spend `declared` (Muse says it, umwayi did not measure it), priced by a `run_micros` or per-token rate the owner writes in `units.yaml` for `muse`. While the owner has written no rate, the run stays `unknown`, as today.
   For: the ledger learns something real, as for Claude Code. Against: the price of a free credit is not a list price; the number would be a stand-in, and the note and the ledger line must say so.
2. **Keep `unknown 100 UU`.** The guide's word of 2026-11-26 (G-0092) is to keep it as a safe overestimate until the credit page shows a movement. Against: nothing is learned.

#### Recommendation

Output option 1 with `--raw`, and settle option 2 until a credit reading moves. The four credit readings of the first run showed no movement (14401 UU each time), so a declared rate would be a guess. Revisit the settle when a run moves the page.

Both are code changes (the output parser and the settle path in `agents.py`, which has mutation tests that count anchors), so each is an owner stop and its own pull request, and neither starts before the guide says so.

## Decisions log

- 2026-11-26 (this note): options and a recommendation; nothing built.
- 2026-11-26 (the guide, G-0092): keep the 100 UU `unknown` settlement as a safe overestimate; before any next Muse run the guide reads the credits.

## Open questions

- **Q-o1.** Which `terminal` words does Muse use for a run that fails, is stopped or reaches its step cap? Recommendation: read them from `muse exec --help` and the docs first; a recorded run with the cap of 1 step (owner's yes, it spends credits) shows one.
- **Q-o2.** Is `payload.text` always the whole final answer, or can it be cut? Recommendation: print the text as given and label it as Muse's word; do not claim it is complete until a long answer is seen.
