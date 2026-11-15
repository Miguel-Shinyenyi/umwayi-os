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

`umwayi feedback export` prints a summary of your logbook that you can paste into a feedback issue. It prints counts and dates only. It never prints a path, a command, the text of a rule, the content of a file or the text of any logbook entry.

1. Run it in the folder you used umwayi in (or give `--root FOLDER` before the word `feedback`): `umwayi feedback export`.
2. It prints these lines: the number of entries; the number of entries for each kind (the command that wrote the entry, for example a check or a queue add; a kind it does not know is counted as `other`); the number of checks for each verdict (Yes, No, Ask me first, and `unreadable` for a check line it could not read); the first and last date; whether the hash chain is intact and how many entries it holds, or that it is not started; and the budget spent in UU (an open reservation counts in full).
3. Read the output before you paste it. It holds no secret by design, and the check that it does not is a test, but you are the last reader.
4. If it exits 2 and prints one sentence and no summary, the logbook is missing or did not pass its check (it was edited by hand, the chain is broken, or a line is not in the format). Nothing was changed. Do not paste the logbook. Say in the issue that the export refused, and give the exit code.

What it does not do: it writes no file and adds no entry to the logbook, so running it twice gives the same answer and leaves your folder as it was. It does not repair anything and does not look at the kill switch. It cannot tell you what was in an entry, because it never prints one. The counts and dates can still show when you used umwayi and how much, and nothing else. It is not a substitute for the questions of the template: the exit code and what happened still have to be written by you.

What else exists, and is not that export:

- `umwayi logbook verify` says whether the chain is intact. Its output is a status and a count, and it names the entry where a break begins.
- `umwayi view snapshot` writes a JSON file of numbers for the page, and one entry to your logbook each time it runs. It has no count per kind or per verdict and no date range. Use the export instead.

## Decisions log

- 2026-11-13: the export was not built in the first version of this page, because no command gave the listed fields; the exporter was its own task.
- 2026-11-14: W33 built it as `umwayi feedback export`. A kind is the source of an entry from a fixed list, never free text, and a verdict is read only from a check entry in its fixed form, so no word of the owner can reach the output. A logbook that does not pass its check gives exit 2 and no summary rather than a partial one.
- 2026-11-13: the template asks for the exit code as a number and gives no place for a log or a file, so a tester is not led to paste one.

## Open questions

- Should the issue template have a label, so reports are found at once? Recommendation: yes, once the owner has chosen a label name. It is left empty now so a missing label cannot make GitHub refuse the template.
