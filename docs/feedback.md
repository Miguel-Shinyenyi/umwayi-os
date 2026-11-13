# Feedback from testers

## Purpose

This page tells a tester how to report what happened when they tried umwayi, and what to leave out. It is the only place that says so. The owner reads the reports.

## Current state

### How to send feedback

1. Open a new issue in the repository on GitHub and choose Tester feedback ([the template](../.github/ISSUE_TEMPLATE/tester-feedback.md)). A blank issue is also allowed.
2. Answer the questions: what you tried, what you expected, what happened, your umwayi version (`umwayi --version`), your Python version (`python --version`) and the exit code (`echo $?` right after the command).
3. Read everything you paste. Remove secrets, tokens, keys, private paths, the text of your rules and anything from your logbook or memory. Then tick the box that says you did.
4. The exit codes are explained in [exit-codes.md](exit-codes.md). Quote the number, because the number says which kind of problem it was.

### Export of a logbook summary

Not yet available. There is no command that exports a summary of the logbook (counts per entry kind, counts per verdict, the date range, the chain status and the budget spent in UU) with no file content. It is a separate task after W9.8. Until it exists, do not paste your logbook, and do not paste its lines.

What exists today, and is not that export:

- `umwayi logbook verify` says whether the chain is intact. Its output is a status and a count, not a summary, and it names the entry where a break begins.
- `umwayi view snapshot` writes a JSON file of numbers (the number of logbook entries, the length of the chain, the budget used in UU for seven days, and a few other counts). It holds no per kind or per verdict count and no date range of the logbook, and it writes one entry to your logbook each time it runs. Do not treat it as the export, and read the file before you share it.

## Decisions log

- 2026-11-13: the export was not built here, because the first check of the code on main found no command that gives the listed fields, and the exporter is its own task.
- 2026-11-13: the template asks for the exit code as a number and gives no place for a log or a file, so a tester is not led to paste one.

## Open questions

- Should the issue template have a label, so reports are found at once? Recommendation: yes, once the owner has chosen a label name. It is left empty now so a missing label cannot make GitHub refuse the template.
