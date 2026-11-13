section: Progress page (W8 slice), found while building
title: The progress page counts boxes and copies the first sentence of rows, and it is only as new as the last build
number: 265

`ui/dist/progress.html` shows work done and open per group, the latest ten status log rows, the highest known limit number and the date it was built. It is a reading aid, with these limits.

- A task is a line that starts with a checkbox in `.kiro/specs/umwayi-os/tasks.md`, counted under the nearest heading that starts with two hash marks. A task written in another form, such as a table row or plain text, is not counted. The Status table at the top of that file has no checkboxes, so it has no group on the page. Sub-headings with three hash marks count inside their group.
- The group name is the heading cut at its first bracket, so the words in brackets (dates, PR numbers) are not on the page.
- The latest ten rows are the first ten rows of the pull request table in `docs/status-log.md`, in file order. The file is newest first, but one row has an older date above a newer one, so file order and date order can differ. The page does not sort.
- Each row shows only its first sentence (cut at 240 characters), not the tests column.
- The highest limit number is the largest number in a heading of `docs/KNOWN-LIMITS.md`. A gap in the numbers is not shown.
- The page is built by `node build.mjs`, which only the owner runs. `ui/dist/build.json` holds the SHA-256 of what the page shows (the group counts, the ten rows, the highest limit number) and of the page. `tests/test_progress_page.py` reads the three sources again with its own reader and fails when that hash differs, so a change to any other line of the sources does not make the page stale, but a new status log row, a ticked task or a new limit does, and then the page has to be rebuilt. Two pull requests that both do that conflict in `ui/dist/build.json` and `ui/dist/progress.html`; the fix is to merge main and run the build again.
- The two readers (one in `ui/src/data/progress.js`, one in the test) are separate code that has to agree. If they ever differ on a source, the test fails at once, which is noise and not a wrong page. A matching hash shows the build ran after the last change of what the page shows. It does not show the page text is right for it.
- The date is the day of the build and is not checked against anything, so a rebuild of unchanged sources changes the page and the hash.
- The page was not looked at in a real phone or browser, and no phone audit was run on it.
