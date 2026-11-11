# Web interface, the view (layer 12)

## Purpose

The view is a calm 3D hillside in a web page. Eleven stations stand around a lantern, one for each main part of umwayi-os, and a panel lists the real tests only the owner can run. It exists so the owner can see what is open, what is stopped and what still has to be checked, at a glance, without the page being able to change anything.

## Current state

**Being reworked (PR 39, not merged).** UI.1 was built as a stylised dusk meadow with eleven podiums in a ring. The owner reviewed it on Nov 11 and asked for a different look: **real life, the Kenyan highlands at dusk**. The engine, Calm mode, reduced motion, the build, the tests of those and the page rules are kept; the scene, the stations, the layout and the labels are rebuilt, and the home page content is added. This page describes what is decided; it says what is built once the rework is done. Requirements: [12.R1 to 12.R15](../.kiro/specs/umwayi-os/requirements.md), design: [Layer 12](../.kiro/specs/umwayi-os/design.md), tasks: [UI.0 to UI.5](../.kiro/specs/umwayi-os/tasks.md), dated facts and the owner's interface check: [adapters/NOTES-layer12.md](../adapters/NOTES-layer12.md), how to build it: [ui/README.md](../ui/README.md).

What is decided:

- **The page only looks.** It never writes to the repo, runs a command or calls a network. It keeps no storage. The one way state gets in is a file of counts that the owner picks in the page (product.md rule 10). The home links are plain anchors the owner clicks; the page makes no request.
- **Where it lives.** A `ui/` folder outside the `umwayi` package. The core stays standard library only. three.js 0.187.0 and esbuild 0.28.2 are pinned with a lockfile; the owner runs `npm ci --ignore-scripts` and `node build.mjs`; umwayi never runs npm. The built page, `ui/dist/index.html`, is committed, is one file under about 2 MB and makes no network request.
- **The place.** The Kenyan highlands at dusk: rolling hills with real height, a river valley, umbrella thorn acacia and African pencil cedar, grass and rock, Mount Kenya on the horizon, low warm light. Everything is generated in code: no photograph, texture file, model or font. A hanging lantern on a shepherd's staff, with a silhouette shepherd and a dog, stands at the centre and is the brightest point.
- **Eleven natural features, no podiums, paths or label boards.** Memory a spring pool; Rules a drystone wall with gates; Queue a sheepfold; Archive a cave in a rock face; Logbook a standing stone with growth rings; Automation a river with a water wheel; AI helpers a sheepdog and a herd; Workflows a stream through connected pools; Adapters a ford or bridge; Kill switch a lone gate and latch with a red lamp; Budget a rain water tank with a level. Names show only on hover or keyboard focus, and in the list view.
- **A scattered layout.** Not a circle: the features stand on hillsides, the valley floor and the river bank, nearer the lantern the more closely they work with the shepherd. Trails of light link features that work together, for the one in focus only. With a snapshot a feature moves nearer when it needs the owner now and drifts out when quiet, slowly, ending within 3 seconds, and jumps with reduced motion. The position function takes numbers only.
- **The home page.** The scene is the hero. Below it: the title and promise, a status strip (sample until a snapshot is loaded), install and first commands with Copy buttons (clipboard only on a click), and links (repo, docs; Devpost and demo video are marked "link to come").
- **The snapshot.** `umwayi view snapshot [--out PATH]` (UI.2) is read only. It writes one JSON file of counts: queue open and answered, rules by verdict, logbook entries and chain length, budget used on each of seven days, the kill switch state, the schedule state. No text from any file, no path, no secret. It runs the tamper check first, writes one logbook entry, and exits 0, 1 (tamper check failed, nothing written) or 64. An unexpected error exits 2.
- **Calm by default.** Nothing flashes or blinks, and nothing in the scene moves by itself. At rest the page asks for no animation frame. A click, a key or the cursor starts a move; every move eases out and ends within 3 seconds (5 in Calm mode). With reduced motion the camera jumps and each feature shows still poses. Calm mode lowers brightness, glow and haze contrast. Text stays at 4.5 to 1 or better. An automatic lower detail mode starts on weak machines and steps down twice on slow frames.
- **The owner checks panel** (UI.4) lists 10.21, 10.31, 11.6, the B.10 capture, 10.37 and the interface check, with steps and a place to tick and type. The page cannot tell whether a check passed.
- **Access.** Every feature has a real button over it; arrow keys and Escape work; a plain list view of the stations is the fallback when WebGL is missing.

What is not in layer 12: any button that acts, a server, live updates, text from the owner's files, saved notes, photographs or downloaded images, anything that moves by itself, and everything of layer 13.

The plan and the hours are in the design. The rework does not fit the window (about 92 hours against 60 to 72); what I propose to cut, in order, is there for the owner to decide.

### How it is checked

- `tests/test_ui_package.py` (Python, standard library): exact versions, the lockfile, `.gitignore`, `build.json`, the built page (no request, no storage, no file loader, the Content-Security-Policy, the size, the allowed addresses). It runs in the normal suite and needs no npm, node or browser.
- `node --test` in `ui/`: the engine, the layout and the position function, the stations, the home content, the detail mode, the list view fallback, the text contrast.
- The browser pass, by hand, with a headless browser outside the repo. Its results are written here after the rework, with the date, the browser and its version, and what could not be verified.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-11 | The hours: all four proposed cuts accepted (second realism pass, station detail, the last step of the low detail mode, UI.5 extras); UI.4 stays; UI.3's drift stays; no further cut unless the owner agrees. About 75 hours remain | The owner, Nov 11. |
| 2026-11-11 | UI-Q16: the scene is the hero of the home page; one page, two modes (sample world with home content, or the owner's live view); title and promise, a status strip (sample until a snapshot), install and first commands with Copy (clipboard only on a click), links (Devpost and demo video placeholders) | The owner, Nov 11. |
| 2026-11-11 | UI-Q15: a station moves closer to the lantern when it needs the owner now and drifts out when quiet; slow, eased, within 3 seconds, off under reduced motion; the position function takes numbers only | The owner, Nov 11. |
| 2026-11-11 | UI-Q14: a scattered layout by how closely each works with the shepherd, fixed default distances (a seeded layout), no overlap, keyboard reachable; streams and trails of light between related stations, no drawn paths | The owner, Nov 11. |
| 2026-11-11 | UI-Q13: the Kenyan highlands at dusk; a hanging lantern on a staff with a shepherd and a dog; no podiums, paths or label boards; the eleven as natural features named on hover or focus | The owner, Nov 11. |
| 2026-11-11 | UI-Q12: imagery that resembles real life, generated in code, one page under about 2 MB, no network, no downloaded images, an automatic lower detail mode | The owner, Nov 11. The first UI.1 look (PR 39) was not accepted. |
| 2026-11-10 | UI-Q6 to UI-Q11 accepted as proposed by the owner (PR 39 follows them): a broken logbook gives no snapshot, a file picker for the snapshot, the list view and the ring order, Calm mode starts off (on for less contrast) with text at 4.5 to 1, the Python suite plus `node --test` plus a hand browser pass, and the layer 13 view stays a sketch | The owner, Nov 10. |
| 2026-11-10 | UI-Q5: an owner checks panel with the physical tests, steps and a place to tick and type; results stay in the page and export as text; the page never writes to the repo, runs a command or calls a network | The owner's answer. The tests only the owner can run need one place. |
| 2026-11-10 | UI-Q4: calm by default, no flashing, no autoplay, motion only after input and eased to rest, reduced motion shows still frames, a Calm mode toggle, dark colours, no large white area, less congestion | The owner's answer. |
| 2026-11-10 | UI-Q3: `umwayi view snapshot` is read only, writes one JSON file of counts only, runs the tamper check, writes one logbook entry, exits 0, 1 or 64 | The owner's answer. Counts cannot leak text. |
| 2026-11-10 | UI-Q1 and UI-Q2: `ui/` outside the package; three.js 0.187.0 and esbuild 0.28.2 pinned with a lockfile; `npm ci --ignore-scripts`; umwayi never runs npm; the built page is committed and makes no network request | The owner's answer. The core stays standard library only. |
| 2026-11-10 | The web interface is layer 12 and in scope before Dec 3; it is no longer a non goal. Every safety rule stays. | The owner, Nov 10. |
| 2026-11-10 | Budget is a built station, not a "planned" ghost (spec, awaiting approval) | The budget governor was built in PR 33. B.10 is said in words. |
| 2026-11-10 | The page gets the snapshot from a file picker, not from a script tag (spec, UI-Q7, awaiting approval) | A script tag would run the file as code, and the command writes JSON. |

## Open questions

- UI.1 is being reworked on PR 39 and is not merged. UI.2 to UI.5 are not built.
- After the owner's four cuts about 75 hours remain against a window of 60 to 72 (3 to 15 hours over). Nothing more is cut unless the owner agrees; if the gap shows by Nov 17 the owner is asked.
- Realism made from code is not a photograph. The first pass is judged by the owner on the screenshots before a second pass.
- The frame rate on a real integrated GPU, Firefox, Safari, a real touch screen and a screen reader are not verified.
- The Devpost and demo video addresses are placeholders until the owner supplies them.
- The owner's checks 10.21, 10.31, 11.6, B.10, 10.37 and the interface check are not done.
