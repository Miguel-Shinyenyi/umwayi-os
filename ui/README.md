# ui: the umwayi-os view (layer 12)

A calm 3D hillside in one web page. Eleven stations stand around a lantern, one for each main part of umwayi-os. The page
only looks: it never writes to the repo, runs a command or calls a network (product.md, rule 10). The core `umwayi`
package never imports anything from here, and nothing here imports `umwayi`.

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
node --test                                    # in ui/ (95 tests): the engine, the layout and position function, the stations, the home content, the detail mode (no package needed)
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
src/ui/            the buttons over the features, the panel, the list view fallback, the home behaviours (Copy)
test/              node --test
```
