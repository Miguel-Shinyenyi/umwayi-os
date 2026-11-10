# Web interface, the view (layer 12)

## Purpose

The view is a calm 3D hillside in a web page. Eleven stations stand around a lantern, one for each main part of umwayi-os, and a panel lists the real tests only the owner can run. It exists so the owner can see what is open, what is stopped and what still has to be checked, at a glance, without the page being able to change anything.

## Current state

**UI.1, the static world, is built (PR 39).** The page, `ui/dist/index.html`, shows the eleven stations with **sample counts** and says "sample". `umwayi view snapshot` (UI.2), reading a snapshot (UI.3), the owner checks panel (UI.4) and the polish and scan (UI.5) are not built. Requirements: [12.R1 to 12.R11](../.kiro/specs/umwayi-os/requirements.md), design: [Layer 12](../.kiro/specs/umwayi-os/design.md), tasks: [UI.0 to UI.5](../.kiro/specs/umwayi-os/tasks.md), dated facts and the owner's interface check: [adapters/NOTES-layer12.md](../adapters/NOTES-layer12.md), how to build it: [ui/README.md](../ui/README.md).

What the page does now:

- **One file, no request.** `ui/dist/index.html` is about 660 KB, with script and styles inline, and works from disk. It carries a Content-Security-Policy that denies everything except its own hashed script and style. `ui/dist/build.json` holds the SHA-256 of every source and of the page. three.js 0.187.0 and esbuild 0.28.2 are pinned with a lockfile; the owner runs `npm ci --ignore-scripts` and `node build.mjs`; umwayi never runs npm.
- **Calm by default.** A dusk hillside, a still moon, sparse grass, a few trees, one lantern. No wind, mist, fireflies or sky motion. At rest the page asks for no animation frame and draws nothing. A click, a key or the cursor starts a move; every move eases out and ends within 3 seconds (5 in Calm mode). Arcs to the stations a station depends on appear only while it is selected.
- **Eleven stations**, each a set of still poses and the short moves between them (Memory, Rules, Queue, Archive, Logbook, Automation, AI helpers, Workflows, Adapters, Kill switch, Budget). Budget is built. Sample counts drive the sheep, stones, beads, lamps, studs and the water level; stations without a count in the snapshot show none and say so.
- **Reduced motion** (from the system, read live): the camera jumps, the cursor does nothing, and the panel steps through the still poses with Previous pose and Next pose.
- **Calm mode** (a button, and on at start when the system asks for less contrast): lower glow, bloom, light and lines, slower moves, no arcs. Text stays at 4.5 to 1 or better in both modes (a Node test checks the colours).
- **Access.** The 11 labels are real buttons that are in the page before any script runs; arrow keys move between stations, Escape returns, focus goes into the panel and back to the label. The list view (a plain list of the same stations) opens from the top bar and shows by itself when WebGL is missing.

What is not in layer 12: any button that acts, a server, live updates, text from the owner's files, saved notes, and everything of layer 13. A view of review dates, reopened decisions and petitions is only sketched in the design.

### How it is checked

- `tests/test_ui_package.py` (Python, standard library): exact versions, the lockfile, `.gitignore`, `build.json`, and the built page (no request, no storage, no file loader, the Content-Security-Policy and its hashes, the labels and the list view). It runs in the normal suite and needs no npm, node or browser.
- `node --test` in `ui/` (40 tests, no package): the tween, following, the on demand loop, settings, the pose player and its time limits, the 11 stations built and every pose applied, the ring and the label layout (also with 14 fake stations), the list view fallback, the text contrast. Nine planted faults (a loop that never rests, a tween that never ends, reduced motion ignored, a follow that never snaps, an action over 3 s, a `setInterval`, a `fetch`, a Calm text colour below 4.5 to 1, Budget drawn as planned) were each caught by a named test.
- **The browser pass**, by hand, on Nov 10 2026: Chrome for Testing 151.0.7922.10 (chrome-headless-shell of Playwright's chromium-1232) on Linux, drawing with SwiftShader (software WebGL2), driven over the DevTools protocol by a script kept outside the repo. All requests blocked and counted. Results:

| check | result |
| --- | --- |
| console messages (errors, warnings, Content-Security-Policy violations) | none, in every run |
| requests attempted | 0 |
| animation frames requested at rest over 3 s | 0 |
| two screenshots 2 s apart at rest | identical (0 differing pixels) |
| click each of the 11 labels: panel opens, focus in the panel | yes, all 11 |
| time to rest after a click, measured on the page's own clock | 2883 to 2933 ms (limit 3000), back to the overview 1400 to 1433 ms |
| Calm mode: switch on, select Kill switch, back, switch off | 950, 4633, 2267 and 600 ms (limit 5000) |
| picture after the overview is restored, overlays hidden | identical to the first (0 differing pixels) |
| reduced motion | 0 ms, one frame per step, the stepper shows all 3 poses of Rules and the caption follows; switching it on while open works |
| keyboard | Tab order is the list button, Calm mode, then the 11 labels; Enter, arrows and Escape work; focus returns to the label |
| no WebGL | the list view shows by itself, with 11 items and a notice; no console error |
| mean luminance (0 black, 1 white) | 0.009 to 0.045 in all six views |
| largest area with all channels at 240 or more | 0.008 percent at most (the lantern) |
| labels overlapping each other or leaving the screen | 0, at 1440 by 844 and 390 by 844, in normal, Calm and reduced motion |

**Not verified:** the 30 frames a second on an integrated GPU (the sandbox draws in software at about 1 to 3 frames a second, so frame times say nothing about a real GPU; the page lowers its pixel ratio after slow frames, and UI.5 and the owner's interface check settle it), Firefox and Safari, a real touch screen, a screen reader, and the owner's eyes. The look is judged on the screenshots in the pull request.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-10 | UI-Q6 to UI-Q11 accepted as proposed by the owner (PR 39 follows them): a broken logbook gives no snapshot, a file picker for the snapshot, the list view and the ring order, Calm mode starts off (on for less contrast) with text at 4.5 to 1, the Python suite plus `node --test` plus a hand browser pass, and the layer 13 view stays a sketch | The owner, Nov 10. |
| 2026-11-10 | UI-Q5: an owner checks panel with the physical tests, steps and a place to tick and type; results stay in the page and export as text; the page never writes to the repo, runs a command or calls a network | The owner's answer. The tests only the owner can run need one place. |
| 2026-11-10 | UI-Q4: calm by default, no flashing, no autoplay, motion only after input and eased to rest, reduced motion shows still frames, a Calm mode toggle, dark colours, no large white area, less congestion | The owner's answer. |
| 2026-11-10 | UI-Q3: `umwayi view snapshot` is read only, writes one JSON file of counts only, runs the tamper check, writes one logbook entry, exits 0, 1 or 64 | The owner's answer. Counts cannot leak text. |
| 2026-11-10 | UI-Q1 and UI-Q2: `ui/` outside the package; three.js 0.187.0 and esbuild 0.28.2 pinned with a lockfile; `npm ci --ignore-scripts`; umwayi never runs npm; the built page is committed and makes no network request | The owner's answer. The core stays standard library only. |
| 2026-11-10 | The web interface is layer 12 and in scope before Dec 3; it is no longer a non goal. Every safety rule stays. | The owner, Nov 10. |
| 2026-11-10 | Budget is a built station, not a "planned" ghost (spec, awaiting approval) | The budget governor was built in PR 33. B.10 is said in words. |
| 2026-11-10 | The page gets the snapshot from a file picker, not from a script tag (spec, UI-Q7, awaiting approval) | A script tag would run the file as code, and the command writes JSON. |

## Open questions

- UI.2 to UI.5 are not built: the snapshot command, reading it in the page, the owner checks panel, and the polish, the frame rate on a real GPU, the scan of `ui/package-lock.json` and the owner's interface check.
- The look has one reviewer so far (the screenshots in PR 39). Anything the owner finds too bright, too busy or too plain is changed in UI.5 or sooner.
- The owner's checks 10.21, 10.31, 11.6, B.10, 10.37 and the interface check are not done.
