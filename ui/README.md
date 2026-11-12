# ui: the umwayi-os view (layer 12)

A calm 3D hillside in one web page. Eleven stations stand around a lantern, one for each main part of umwayi-os. The page
only looks: it never writes to the repo, runs a command or calls a network (product.md, rule 10). The core `umwayi`
package never imports anything from here, and nothing here imports `umwayi`.

Status (W1, mobile first): the top bar takes its room in the page on a phone, a touch screen and a short window, so it cannot cover the title; every control is 44 pixels or more there; wide screens with a mouse look as before. New: `test/phone.test.mjs` renders this page in a real Chromium at 375 by 667, 390 by 844, 412 by 915 and 360 by 640, upright and on its side, and fails on overlapping text, sideways overflow, a small control or a header out of Tab order. It needs a Chromium (`UMWAYI_BROWSER` names one; without one it skips; `UMWAYI_REQUIRE_BROWSER=1` makes that a failure). `tools/` holds its driver (`browser.mjs`, DevTools protocol over Node's own WebSocket, no package), the audit and the walk; the site's test uses them too. See `../docs/interface.md` and KNOWN-LIMITS 233 to 237.

Status (UI.5, first slice): the docs, the access and contrast checks, the phone layout of the panels and the fault map of 12.R10.6 are done; the scan of the lockfile (held by the owner) and the scene polish, frame rate check and by-hand browser pass (after UI.7) are not. New: `test/access.test.mjs` (names, landmarks, headings, Tab order, live regions, 24 pixel targets, the phone layout of the panels), six contrast tests worked out from `src/style.css`, `test/faults.test.mjs` (the map from each planted fault to the test that kills it). The CSS now keeps the owner checks panel inside a 390 pixel screen and gives the fields a 3 to 1 border and a readable placeholder.

Status (UI.4, the owner checks panel): "Owner checks" in the top bar and in the list view opens a panel with the six checks only the owner can run (`src/data/checks.js`, each step word for word from its NOTES file), a tick and a result field for each step, and an export as text with Copy and Download. A check is "not done" until every step is ticked, then "ticked by you", never "passed". The notes are kept in memory only (`src/data/notes.js`) and are lost when the page closes. A result that looks like an email, a URL, a token or a hex string is warned. The panel runs nothing, makes no request and works with no WebGL.

Status (UI.3, the snapshot): the page reads a snapshot file the owner picks or drops (`src/data/snapshot.js` reads it with `FileReader.readAsText` and checks it strictly; `src/ui/snapshot.js` is the picker, the drop and the one message). A file that is not a snapshot of this version gives "This file is not a snapshot of this version" and loads nothing. A loaded snapshot sets the status strip, the date next to the scene (instead of "sample"), the footer, the panels, what each feature draws (the mapping table in `docs/interface.md`) and, through `setNeeds`, the places of Queue, Kill switch and Budget. A null part is drawn as unknown. Nothing is uploaded, sent or kept, and the page still makes no request. The real file for the tests is `test/fixtures/snapshot.json`, the output of `umwayi view snapshot` on the fixed root of `tests/test_view.py`.

Status (UI.6, the shared scene): the scene code is one module, `src/scene.js` (`createScene`), used by `src/app.js` here and by the public site in `../site`, which imports it from this folder. The device query and the List and Standard switch are one module too, `src/boot.js`. This page behaves and looks as before (a screenshot at 1440 by 900 is pixel for pixel the same as before the move). See `../site/README.md`.

Status (UI.1, PR 39, reworked on Nov 11 after the owner's review): the page is the Kenyan highlands at dusk, drawn to look
like real life from code only, with eleven natural features, a shepherd with a lantern, Mount Kenya on the horizon, and the
home content below the picture. It shows made up counts and says "sample". Reading a real snapshot and moving the features
by need is UI.3 (the position function `stationPositions` is built and tested now and takes only numbers), the snapshot
command is UI.2 and the owner checks panel is UI.4. Requirements: 12.R1 to 12.R15 in `.kiro/specs/umwayi-os/requirements.md`.
Design: "Layer 12" in `design.md`. Facts with links: `adapters/NOTES-layer12.md`. The doc: `docs/interface.md`.

## The two packages

| package | version | what for |
| --- | --- | --- |
| `three` | **0.187.0** | the 3D drawing (bundled into the page) |
| `esbuild` | **0.28.2** | the build only (not in the page) |

Both have an exact version, no `^`, `~` or range. `package-lock.json` is committed; every package in it has a `sha512`
hash and comes from registry.npmjs.org. `node_modules/` is never committed. Node.js 22 or later.

## Build

```
cd ui
npm ci --ignore-scripts
node build.mjs
```

`--ignore-scripts` is enough for esbuild: its program comes from an optional platform package, not from a script.
**umwayi never runs npm, node or a browser.** The build writes two files, and both are committed:

| file | what it is |
| --- | --- |
| `dist/index.html` | the whole page: script, styles and every shape inline, about 680 KB (the limit is about 2 MB). No other file is loaded and nothing is downloaded. |
| `dist/build.json` | the SHA-256 of every file the page was built from and of the page, so `tests/test_ui_package.py` finds a source changed without a rebuild, or a page edited by hand, without npm |

Open `dist/index.html` from disk. No server is needed.

## No network request

The page loads no file, font, image, script or style from anywhere. It carries a Content-Security-Policy that denies
everything except its own inline script and style (allowed by hash). No file loader of three.js is bundled. The addresses in
the page are the XML namespace name `http://www.w3.org/1999/xhtml` that three.js carries (never fetched), and the repo and
docs addresses of the home page: two plain links the owner clicks and the clone command. Devpost and the demo video are text
marked "link to come" until the owner supplies the addresses (`src/data/home.js`). The page makes no request.

## The detail mode

The page starts in high or low detail from what it can tell (software rendering, 4 cores or fewer, 4 GB or less) and steps
down twice at most after slow frames: a lower pixel ratio, then no bloom and no multisampling. `#detail=high` or
`#detail=low` in the address forces and keeps a mode. `tests/test_ui_package.py` checks all of this on the built page.

## Tests

```
python -m unittest tests.test_ui_package       # the package, the lockfile, build.json, the built page (standard library)
node --test                                    # in ui/ (261 tests): the engine, the layout and position function, the stations, the home content, the detail mode (no package needed)
```

The Python suite needs no npm, node or browser. The browser pass (no console error, zero requests, still at rest, the
look and the labels) is run by hand with a headless browser kept outside the repo; its results are in `docs/interface.md`.

## Files

```
build.mjs          bundles src/ into dist/index.html and writes dist/build.json
src/index.html     the page template (labels and the list view are made from stations/meta.js)
src/style.css      the palette, Calm mode, reduced motion
src/main.js        entry of the live view; calls boot with a highest tier of Standard and the network ignored
src/boot.js        the device query, the List and Standard switch and the start of the picture; used by main.js and by the site
src/scene.js       createScene: the world, camera, loop, pointer and Calm mode on a canvas; used by app.js and by the site
src/app.js         the page's own parts: the buttons over the features, the panel, the keyboard; joined to the scene by hooks
src/engine/        ease, tween (motion), follow, the on demand loop, settings, poses, camera rig, stage, detail, placement, tier (the tier choice), env (the device hints), flow (the water clock)
src/world/         height (the ground), river, layout (the fixed table and the position function), shots, sky and Mount Kenya, terrain, water, plants, lantern (shepherd), trails, palette, noise, glsl
src/stations/      meta.js (the words), kit.js (shared parts), one module per natural feature, index.js
src/data/          sample.js (made up counts), counts.js (counts to text), home.js (the home content)
src/ui/            the buttons over the features, the panel, the list view fallback, the home behaviours (Copy), snapshot.js (the picker and the drop), checks.js (the owner checks panel)
test/              node --test; test/fixtures/snapshot.json is a real snapshot; access.test.mjs, faults.test.mjs
```

## High (tier 3, the public site only)

`src/high/` is the High tier of the public site (UI.7). The live view never imports it (`test/high.test.mjs` walks the
imports from `src/main.js`), so `dist/index.html` has no part of it. `src/high/assets.js` is the only module of `src/`
that loads a file: five photographs, from the site's own host under `/high/`, as images. High may use only the
three.js classes Standard already uses (`test/high.test.mjs`), so Standard visitors download no more of three.js.
