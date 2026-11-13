# Concerns record (W19, part 2)

## Purpose

Every project keeps a record of 111 engineering concepts (rate limiting, caching, timeouts, backups, postmortems and
so on), so that each one is looked at on purpose and not by accident. The rule comes from the hub doc
engineering-concerns: one row for each number 1 to 111; each row answers Applies, Not applicable or Deferred, with a
one sentence reason; an Applies row points at evidence, a file path that exists in the repo. `umwayi concerns check`
refuses a record that does not follow the rule.

## Current state

Built: `umwayi concerns check PATH` (`umwayi/concerns.py`). It reads a markdown table with these columns, in this order:

| number | concept | answer | reason | evidence | date |
| --- | --- | --- | --- | --- | --- |

It prints one line per failure to standard error and exits 2 if there is any. It exits 0 if there is none, 64 for a wrong
command line, and never 1 or 3. It changes nothing.

It fails on:

- a missing number, a duplicate number, a number that is not a plain whole number or is outside 1 to 111;
- a concept name that is not the fixed name of that number (the 111 names are in `umwayi/concerns.py`, numbered 1 to 111);
- an answer other than `Applies`, `Not applicable` or `Deferred` (written exactly so);
- an empty or whitespace reason;
- an Applies row with no evidence, or whose evidence is not a regular file that exists inside the repo root. A path
  with a `..` part, an absolute path, a path with a backslash, a colon or a control character, and a link that leads
  out of the repo are all refused. The repo root is `--root` (default: the current folder);
- a date that is not a real date written `YYYY-MM-DD`;
- a row without exactly six columns, a header that is not exactly the six names, or a header not followed by a separator row;
- a record that cannot be read, is larger than 1,000,000 bytes, or is not UTF-8 text.

A failure line names the line of the file and the row number. It never repeats text from the file.

What it does not do: it never claims the content is true. A reason that is wrong passes, and a file that exists is not
proof that the concern is met. It only shows that the record is complete and well formed.

It is a command the owner runs. No job, timer, workflow or schedule entry runs it, and a test checks that none names it.

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-13 | The checker exits 2 on any failure, as the owner decided for W19 part 2, although [exit-codes.md](exit-codes.md) uses 1 for a plain refusal elsewhere. | The owner's decision for this task, confirmed on Nov 13 when asked: 2 for a record that fails the check, 2 for a missing or unreadable record, 64 for bad arguments. |
| 2026-11-13 | The record has six columns: number, concept, answer, reason, evidence, date. The concept name must match its number. | The owner's column list; a name that does not match is a sign of a shifted or edited row. |

## Open questions

- None for the checker. Whether the owner wants exit 1 instead of 2 for a refused record is a decision for the owner; the recommendation is to keep 2.
