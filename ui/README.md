# ui: the umwayi-os view (layer 12)

A calm 3D hillside in one web page. Eleven stations stand around a lantern, one for each main part of umwayi-os. The page
only looks: it never writes to the repo, runs a command or calls a network (product.md, rule 10). The core `umwayi`
package never imports anything from here, and nothing here imports `umwayi`.

Status (UI.1, the static world): the page shows sample counts and says "sample". Reading a real snapshot is UI.3, the
snapshot command is UI.2 and the owner checks panel is UI.4. Requirements: 12.R1 to 12.R11 in
`.kiro/specs/umwayi-os/requirements.md`. Design: "Layer 12" in `design.md`. Facts with links: `adapters/NOTES-layer12.md`.
The doc: `docs/interface.md`.

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
| `dist/index.html` | the whole page: script, styles and every shape inline, about 660 KB. No other file is loaded. |
| `dist/build.json` | the SHA-256 of every file the page was built from and of the page, so `tests/test_ui_package.py` finds a source changed without a rebuild, or a page edited by hand, without npm |

Open `dist/index.html` from disk. No server is needed.

## No network request

The page loads no file, font, image, script or style from anywhere. It carries a Content-Security-Policy that denies
everything except its own inline script and style (allowed by hash). No file loader of three.js is bundled. The one
`http://` string in the page is the XML namespace name `http://www.w3.org/1999/xhtml` that three.js carries; it names a
vocabulary and is never fetched. `tests/test_ui_package.py` checks all of this on the built page.

## Tests

```
python -m unittest tests.test_ui_package       # the package, the lockfile, build.json, the built page (standard library)
node --test                                    # in ui/: the engine, the stations, the layout (no package needed)
```

The Python suite needs no npm, node or browser. The browser pass (no console error, zero requests, still at rest, the
look and the labels) is run by hand with a headless browser kept outside the repo; its results are in `docs/interface.md`.

## Files

```
build.mjs          bundles src/ into dist/index.html and writes dist/build.json
src/index.html     the page template (labels and the list view are made from stations/meta.js)
src/style.css      the palette, Calm mode, reduced motion
src/main.js        entry; falls back to the list view when the 3D view cannot start
src/app.js         joins the world, camera, labels and panel; decides when to draw
src/engine/        ease, tween (motion), follow, the on demand loop, settings, poses, camera rig, layout, stage
src/world/         sky, mountains, land, grass, trees, lantern, arcs, palette
src/stations/      meta.js (the words), kit.js (shared parts), one module per station, index.js
src/data/          sample.js (made up counts), counts.js (counts to text)
src/ui/            labels and the panel
test/              node --test
```
