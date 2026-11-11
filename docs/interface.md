# Web interface, the view (layer 12)

## Purpose

The view is a calm 3D hillside in a web page. Eleven stations stand around a lantern, one for each main part of umwayi-os, and a panel lists the real tests only the owner can run. It exists so the owner can see what is open, what is stopped and what still has to be checked, at a glance, without the page being able to change anything.

## Current state

**Round 2 (Nov 11, UI-Q17 to UI-Q22), being built.** The owner decided three tiers chosen in the browser (List, Standard, High) with a visible switch; a public site in `site/` (Next.js on the Vercel free tier, server rendered home text, no analytics, no tracking, device hints never sent) beside the owner's live view, which stays the static one file page of `ui/` with no network request; one scene module shared by both; fixes to the Standard scene (the rest of the page shows at the bottom of the first screen, stations further out, the river and trails visible, no name over the hero text, less low poly rocks and walls); and a dense forest across the river, flowing water over rocks, a Maasai silhouette shepherd, a mixed flock of sheep and goats and a herding dog. The order is UI.1b in PR 39, then UI.6 (the site, List and Standard), then UI.7 (High). The owner keeps the timeline and no scope is cut. The text below describes UI.1 before round 2 until UI.1b is done.

**UI.1 is built, as the Kenyan highlands scene (PR 39, reworked on Nov 11, not merged).** The first build was a stylised meadow with podiums; the owner reviewed it on Nov 11 and asked for a different look. The engine, Calm mode, reduced motion, the build, the page rules and their tests were kept; the scene, the stations, the layout and the labels were rebuilt, and the home content was added. `umwayi view snapshot` (UI.2), reading a snapshot and feeding the position function real numbers (UI.3), the owner checks panel (UI.4) and the polish and scan (UI.5) are not built. Requirements: [12.R1 to 12.R15](../.kiro/specs/umwayi-os/requirements.md), design: [Layer 12](../.kiro/specs/umwayi-os/design.md), tasks: [UI.0 to UI.5](../.kiro/specs/umwayi-os/tasks.md), dated facts and the owner's interface check: [adapters/NOTES-layer12.md](../adapters/NOTES-layer12.md), how to build it: [ui/README.md](../ui/README.md).

What the page does now, on made up counts that it marks "sample":

- **A real life look made from code.** Rolling hills with real height, a river valley with a still, sky-reflecting river, umbrella thorn acacia, African pencil cedar, gold and green grass, rock, a low warm light with long shadows, haze, soft cloud and Mount Kenya with snow on the horizon. A shepherd's silhouette with a staff, a hanging lantern and a dog stand at the centre; the lantern is the brightest point. No photograph, texture file, model or font; the page is about 680 KB.
- **Eleven natural features, scattered.** A spring pool, a drystone wall with gates, a sheepfold, a cave in a rock face, a standing stone, a water wheel on the river, a sheepdog and herd, a stream through three pools, a ford and bridge, a lone gate with a red lamp, a rain water tank. No podium, path or board. Their places are a fixed table by how closely each works with the shepherd (`ui/src/world/layout.js`); `stationPositions(needs)` takes only numbers and moves a feature nearer when it needs the owner (UI.3 will feed it). Names show only on hover or keyboard focus.
- **Trails of light** to the features that work together, for the one in focus only; hidden in Calm mode.
- **Calm by default.** Nothing flashes, and nothing in the scene moves by itself. At rest the page asks for no animation frame. A click, a key or the cursor starts a move; every move eases out and ends within 3 seconds (5 in Calm mode). With reduced motion the camera jumps and each feature shows still poses. Calm mode lowers brightness, glow and haze.
- **The home content** below the picture: the title and promise, a status strip (all four values say "sample"), install and first commands with a Copy button each (written to the clipboard only on a click), and links (the repo and the docs; Devpost and the demo video are text marked "link to come").
- **A lower detail mode** that starts on weak machines and steps down twice on slow frames; `#detail=high` or `#detail=low` forces and keeps one. **Access:** a real button over every feature, arrows and Escape, and a plain list view that shows by itself when WebGL is missing.

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

What is not in layer 12 (and what the owner's cuts of Nov 11 left out): a second realism pass, a rope crossing at the ford, a fourth pool, a sluice at the wheel, the last step of the lower detail mode; any button that acts, a server, live updates, text from the owner's files, saved notes, photographs or downloaded images, anything that moves by itself, and everything of layer 13.

The plan and the hours are in the design. The rework does not fit the window (about 92 hours against 60 to 72); what I propose to cut, in order, is there for the owner to decide.

### How it is checked

- `tests/test_ui_package.py` (Python, standard library, 31 tests): exact versions, the lockfile, `.gitignore`, `build.json`, and the built page: no request, no storage, no file loader, the Content-Security-Policy and its hashes, the size (under 2 MB), the only addresses, the home sections, the placeholders, the buttons that are invisible at rest. It runs in the normal suite and needs no npm, node or browser.
- `node --test` in `ui/` (69 tests, no package): the engine, the layout and the position function (5000 random need sets, the extremes, the river, the slope), the eased move, the camera shots, the 11 features built with every pose applied, the home content, the detail mode, the list view fallback, the text contrast. Seventeen planted faults (the push apart removed, a bad need accepted, the wrong distance formula, a slow move, a name visible at rest, a clipboard write on load, a placeholder made a link, a sample value without the word sample, a third detail step, a file loader, the camera in the shepherd, trails left on in Calm mode, reduced motion ignored, a river feature off the river, and others) were each caught by a named test; the one survivor was an equivalent mutant (the same guard stood twice).
- **The browser pass**, by hand, on Nov 11 2026: Chrome for Testing 151.0.7922.10 (chrome-headless-shell of Playwright's chromium-1232) on Linux, drawing with SwiftShader (software WebGL2), driven over the DevTools protocol by a script kept outside the repo; every request blocked and counted. High detail was forced and kept with `#detail=high` for the screenshots; the other checks ran at `#detail=low`. Results:

| check | result |
| --- | --- |
| console messages (errors, warnings, Content-Security-Policy violations) | none, in every run |
| requests attempted | 0, also after clicking Copy and opening the list view |
| animation frames requested at rest over 4 s; two screenshots 2.5 s apart | 0; identical |
| names visible at rest | 0 of 11 |
| hover over a feature; cursor leaves; focus on a button | its name only; none; its name only |
| click each of the 11 buttons: panel opens, focus in the panel, one name shown | yes, all 11 |
| time to rest after a click, on the page's own clock | 2900 to 2933 ms (limit 3000); back to the overview 1400 to 1417 ms |
| Calm mode: switch on, select Kill switch, back | 983, 4633 and 2233 ms (limit 5000) |
| reduced motion | 0 ms, one frame per step, the stepper walks the poses |
| keyboard | Tab order is the list button, Calm mode, then the 11 buttons in list order; Enter, arrows and Escape work; focus returns to the button |
| Copy: before any click; after the click on the check command | 0 writes; exactly `umwayi check '{"type": "payment", "amount": 5}'` |
| links | Repo and Docs are links; Devpost and Demo video are text, not links |
| no WebGL | the list view and the home content show by themselves, no console error |
| mean luminance (0 black, 1 white), high detail | 0.032 to 0.072 in all twelve views at 1440 by 900 and 390 by 844; no area near white |
| page size | about 680 KB |

**Not verified:** the 30 frames a second on an integrated GPU (the sandbox draws in software at 1 to 3 frames a second, so frame times say nothing about a real GPU), Firefox, Safari, a real touch screen, a screen reader, and the owner's eyes. The look is judged on the screenshots in the pull request; it is a first realism pass, not a photograph.

## Decisions log

Newest first. Each row names where it was decided.

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-11 | UI-Q22: the owner keeps the timeline, no scope is cut, no question about hours; one pull request per step: UI.1b (PR 39), UI.6 (the site, List and Standard), UI.7 (High) | owner, round 2 |
| 2026-11-11 | UI-Q21: a dense forest across the river; rapids, foam and moving highlights, still with reduced motion (and, my calmer choice, in Calm mode); a Maasai silhouette shepherd with beads only as shape; a mixed flock of sheep and goats and a herding dog; wildlife at the edge in High only | owner, round 2 |
| 2026-11-11 | UI-Q20: the top of the status strip shows at the bottom of the first screen; the list is tier 1; at least three stations at 30 m or more; every trail faint at rest and the river visible; no name over the hero text; rocks, walls and ground less low poly | owner, round 2 |
| 2026-11-11 | UI-Q19: the owner's live view stays the static one file page (no request, CSP `default-src 'none'`, from disk, Standard, the file picker); one scene module used by the live view and the site | owner, round 2 |
| 2026-11-11 | UI-Q18: a public site in `site/`, Next.js pinned with a lockfile, Vercel free tier, no analytics or tracking, hints read in the browser only; the server renders the home text and the list; it may fetch only its own files from its own host | owner, round 2 |
| 2026-11-11 | UI-Q17: three tiers (List, Standard, High) chosen by `chooseTier` from the device hints, with a visible switch kept in the address fragment only; High by itself only on a known fast network | owner, round 2; the High rule is my calmer choice |
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

- UI.1 is being reworked on PR 39 and is not merged; UI.1b (round 2) is being built there. UI.2 to UI.7 are not built.
- The owner keeps the timeline (UI-Q22); no scope is cut.
- The public site's host sees which files a browser asks for, so its logs can tell which tier was loaded. Nothing else about the device is sent.
- Realism made from code is not a photograph. The first pass is judged by the owner on the screenshots before a second pass.
- The frame rate on a real integrated GPU, Firefox, Safari, a real touch screen and a screen reader are not verified.
- The Devpost and demo video addresses are placeholders until the owner supplies them.
- The owner's checks 10.21, 10.31, 11.6, B.10, 10.37 and the interface check are not done.
