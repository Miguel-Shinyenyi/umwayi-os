# Web interface, the view (layer 12)

## Purpose

The view is a calm 3D hillside in a web page. Eleven stations stand around a lantern, one for each main part of umwayi-os, and a panel lists the real tests only the owner can run. It exists so the owner can see what is open, what is stopped and what still has to be checked, at a glance, without the page being able to change anything.

## Current state

**Specified, not built.** The spec is in the UI.0 pull request and waits for the owner's approval. Nothing under `ui/` exists yet, and `umwayi view snapshot` does not exist yet. Requirements: [12.R1 to 12.R11](../.kiro/specs/umwayi-os/requirements.md), design: [Layer 12](../.kiro/specs/umwayi-os/design.md), tasks: [UI.0 to UI.5](../.kiro/specs/umwayi-os/tasks.md), dated facts and the owner's interface check: [adapters/NOTES-layer12.md](../adapters/NOTES-layer12.md).

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
