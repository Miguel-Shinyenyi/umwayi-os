section: Progress page (W8 slice), found while building
title: The progress page counts boxes and copies the first sentence of rows, and it is only as new as the last build
number: 265

`ui/dist/progress.html` (built, not committed) shows work done and open per group, the latest ten status log rows, the highest known limit number and the date it was built. It is a reading aid, with these limits.

- A task is a line that starts with a checkbox in `.kiro/specs/umwayi-os/tasks.md`, counted under the nearest heading that starts with two hash marks. A task written in another form, such as a table row or plain text, is not counted. The Status table at the top of that file has no checkboxes, so it has no group on the page. Sub-headings with three hash marks count inside their group.
- The group name is the heading cut at its first bracket, so the words in brackets (dates, PR numbers) are not on the page.
- The latest ten rows are the first ten rows of the pull request table in `docs/status-log.md`, in file order. The file is newest first, but one row has an older date above a newer one, so file order and date order can differ. The page does not sort.
- Each row shows only its first sentence (cut at 240 characters), not the tests column.
- The highest limit number is the largest number in a heading of `docs/KNOWN-LIMITS.md`. A gap in the numbers is not shown.
- Since W22 the page is built by `node build.mjs` and is not committed: `ui/dist/progress.html` is in `.gitignore`, and `ui/dist/build.json` holds no hash of the page or of what it shows. A pull request that adds a status row, ticks a box or adds a limit therefore changes no committed ui file and cannot fail CI as stale. The page exists only after a build (`npm ci --ignore-scripts` then `node build.mjs` in `ui/`); a checkout that has not been built has no page. Nothing in this repository builds or publishes it at deploy time yet: there is no deploy workflow, so whoever deploys must run the build step.
- The two readers (one in `ui/src/data/progress.js`, one in `tests/test_progress_page.py`) are separate code that has to agree. `tests/test_progress_page.py` runs the JavaScript one with node (no npm) on the real sources and compares the string with its own; when node is missing that test is skipped and says so. A matching string shows the two readers agree, not that the page text is right. The node test `ui/test/progress.test.mjs` runs the build and checks the page it wrote.
- The date is the day of the build and is not checked against anything. Because the page is not committed, a rebuild of unchanged sources changes no committed file.
- The page was not looked at in a real phone or browser, and no phone audit was run on it.
