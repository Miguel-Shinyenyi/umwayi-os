# Web interface, the view (layer 12)

## Purpose

The view is a calm 3D hillside in a web page. Eleven stations stand around a lantern, one for each main part of umwayi-os, and a panel lists the real tests only the owner can run. It exists so the owner can see what is open, what is stopped and what still has to be checked, at a glance, without the page being able to change anything.

## Current state

**The snapshot command is built (UI.2); the page is not.** The spec is in the UI.0 pull request. `umwayi view snapshot` exists and is tested (below). Nothing under `ui/` exists yet. Requirements: [12.R1 to 12.R11](../.kiro/specs/umwayi-os/requirements.md), design: [Layer 12](../.kiro/specs/umwayi-os/design.md), tasks: [UI.0 to UI.5](../.kiro/specs/umwayi-os/tasks.md), dated facts and the owner's interface check: [adapters/NOTES-layer12.md](../adapters/NOTES-layer12.md).

### `umwayi view snapshot [--out PATH] [--date D]`

Read only. It writes one JSON file of counts and one logbook entry, and nothing else. The code is `umwayi/view.py`; it imports only the standard library and the other layers' readers.

- **The file** (schema 1, two spaces of indent, fixed key order, a final newline, about 700 bytes): `schema`, `date`, `queue` (`open`, `answered`), `rules` (`yes`, `no`, `ask`), `logbook` (`entries`, `chain_length`), `budget.days` (seven days, oldest first, the last is `date`, each with `date` and `used_uu`), `kill_switch` (`on`, `off` or `unknown`) and `schedule` (`entries`, `installed`, `enabled`). Every leaf is a whole number from 0 to 1000000000, null, one of the three words or a date. No text from any file, no path, no secret.
- **Where the counts come from.** Each layer's own reader: `logbook.read_checked_chain` (the tamper check, the entries and the chain length from one read), `taskqueue.list_rows`, `rules.load_rules`, `budget.parse_ledger` and `budget.day_totals` (`used_uu` is settled plus reserved in full, the same used number as `umwayi budget status`, with reservations counted in full), `kill.state`, and `schedule.counts` (the same read as `umwayi schedule check`: installed means both unit files are exactly what umwayi would write and no drop-in sits next to them; enabled means the timer has its enable link). The logbook counts are those before the command's own entry.
- **A part that cannot be read is null**, never zero: a missing or malformed `queue.md`, a missing or broken `rules.yaml` (a FIFO or `/dev/zero` as `rules.yaml` is null too, it never hangs), a bad budget entry, a `schedule.yaml` that fails validation or a unit folder that is a link. A reader that raises gives null for its part. A missing `schedule.yaml` is 0, 0, 0. A kill switch state that cannot be told is `unknown`.
- **Order.** The arguments (64), then the tamper check: if the logbook is broken the exit is 1, the output names the failed check and never a line, and nothing is written. Then gather, render, write the file, write the entry. If the entry cannot be written the file is put back as it was (or removed) and the exit is 2.
- **`--out`.** Default `.umwayi/snapshot.json` in the root. A relative path is relative to the root; an absolute path must be inside it. It must end in `.json`, have at most 1024 printable characters on one line and no `..` part, and no part of it may be a link. It replaces only a regular file with one name that is an earlier snapshot of this command (it parses and has exactly the fields); anything else that exists is refused with 64 and left alone, so `--out rules.yaml` or `--out umwayi.json` can never overwrite anything. The folder must already exist (only `.umwayi` is made). The error never prints the path. The mode is 0600, whatever the umask. `.umwayi/snapshot.json` is in `.gitignore`.
- **`--date D`** sets `date` and the last of the seven days. A date before the last logbook entry is 64, because dates never go backwards in the logbook.
- **The entry.** Source `umwayi view snapshot`; Added: `Wrote a snapshot of counts to FILE (SHA-256 HEX)`, where FILE is the name inside the root; Checked: the logbook chain was intact before the write; Not done: no text, path or secret of any file is in the snapshot, the page was not opened.
- **Exit codes.** 0 done, 1 the tamper check failed, 2 an unexpected error (its text never holds file contents), 64 usage. Never 3: it asks the rules nothing and the kill switch does not stop it.
- **Tests.** `tests/test_view.py`, all real child processes (see [testing.md](testing.md)). Planted faults, each killed by a named test: a title or a path added to the file; a wrong count (answered counted as closed, No counted as Ask me first); reserved UU left out of `used_uu`; the tamper check skipped; the entry skipped; the file not put back after a failed entry; the mode following the umask; `--out` allowed over a foreign file, with a `..` part, with another ending, with a newline, or over a hard linked snapshot; an unknown kill switch read as off; a missing `schedule.yaml` read as null; a drop-in ignored; a date before the last entry accepted. Three more faults change nothing the tests could see, because a second check also refuses the same input: a link (or a link as a folder part) allowed is still refused, as its type is not a regular file or a folder; a path outside the root allowed would still be joined under the root.

What is decided:

- **The page only looks.** It never writes to the repo, runs a command or calls a network. It keeps no storage. The one way state gets in is a file of counts that the owner picks in the page (product.md rule 10).
- **Where it lives.** A new `ui/` folder outside the `umwayi` package. The core stays standard library only. three.js 0.187.0 and esbuild 0.28.2 are pinned with a lockfile; the owner runs `npm ci --ignore-scripts`; umwayi never runs npm. The built page, `ui/dist/index.html`, is committed, is one file and makes no network request.
- **The snapshot.** `umwayi view snapshot [--out PATH]` is read only. It writes one JSON file of counts: queue open and answered, rules by verdict, logbook entries and chain length, budget used on each of seven days, the kill switch state, the schedule state. No text from any file, no path, no secret. It runs the tamper check first, writes one logbook entry, and exits 0, 1 (tamper check failed, nothing written) or 64. An unexpected error exits 2.
- **Calm by default.** Nothing flashes or blinks. No autoplay: at rest the page draws nothing. Motion only follows a click or a cursor move, eases out and ends within 3 seconds. With `prefers-reduced-motion` all movement is off and each station shows still poses. A visible Calm mode button lowers brightness and contrast. Dark colours, no large white area, few things on screen.
- **Eleven stations.** Memory, Rules, Queue, Archive, Logbook, Automation, AI helpers, Workflows, Adapters, Kill switch, Budget. Budget is a built station, because the budget governor is built. A planned part is never shown as built.
- **The owner checks panel** lists 10.21, 10.31, 11.6, the B.10 capture, 10.37 and the interface check, each with steps and a place to tick and type a result. The page cannot tell whether a check passed. Results stay in the page and export as text.
- **Access.** Labels are real buttons, arrow keys and Esc work, and a plain list view of the stations is the fallback when WebGL is missing.

What is not in layer 12: any button that acts, a server, live updates, text from the owner's files, saved notes, and everything of layer 13. A view of review dates, reopened decisions and petitions is only sketched in the design, to be drawn when layer 13 exists.

The plan is Nov 13 to Nov 22 (about 50 hours, in five pull requests), after the owner approves the spec; the schedule is in [schedule.md](schedule.md).

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-11 | UI.2: the snapshot file is 0600, whatever the umask; a missing `queue.md` is null; installed excludes a unit with a drop-in; a date before the last logbook entry is 64 | The owner's instruction for UI.2 (the mode; 12.R4.6 said the umask and is changed). The rest follows 12.R4.3 and the logbook's date rule. |
| 2026-11-10 | UI-Q5: an owner checks panel with the physical tests, steps and a place to tick and type; results stay in the page and export as text; the page never writes to the repo, runs a command or calls a network | The owner's answer. The tests only the owner can run need one place. |
| 2026-11-10 | UI-Q4: calm by default, no flashing, no autoplay, motion only after input and eased to rest, reduced motion shows still frames, a Calm mode toggle, dark colours, no large white area, less congestion | The owner's answer. |
| 2026-11-10 | UI-Q3: `umwayi view snapshot` is read only, writes one JSON file of counts only, runs the tamper check, writes one logbook entry, exits 0, 1 or 64 | The owner's answer. Counts cannot leak text. |
| 2026-11-10 | UI-Q1 and UI-Q2: `ui/` outside the package; three.js 0.187.0 and esbuild 0.28.2 pinned with a lockfile; `npm ci --ignore-scripts`; umwayi never runs npm; the built page is committed and makes no network request | The owner's answer. The core stays standard library only. |
| 2026-11-10 | The web interface is layer 12 and in scope before Dec 3; it is no longer a non goal. Every safety rule stays. | The owner, Nov 10. |
| 2026-11-10 | Budget is a built station, not a "planned" ghost (spec, awaiting approval) | The budget governor was built in PR 33. B.10 is said in words. |
| 2026-11-10 | The page gets the snapshot from a file picker, not from a script tag (spec, UI-Q7, awaiting approval) | A script tag would run the file as code, and the command writes JSON. |

## Open questions

- UI-Q6: a broken logbook gives no snapshot (exit 1), so the page cannot show a broken chain. Proposed: keep it so.
- UI-Q7: the file picker. Proposed: yes.
- UI-Q8: the list view, the ring order, and layer 10 told inside the Adapters station. Proposed: yes.
- UI-Q9: Calm mode starts off, and on when the system asks for less contrast; text stays at 4.5 to 1 or better. Proposed: yes.
- UI-Q10: the Python suite checks the package and the built page; `node --test` and the browser pass run by hand. Proposed: yes; a CI Node job is the alternative.
- UI-Q11: the liberal society view is only a sketch until the layer 13 spec exists. Proposed: build only the extension points.
- The owner's checks 10.21, 10.31, 11.6, B.10, 10.37 and the interface check are not done.
