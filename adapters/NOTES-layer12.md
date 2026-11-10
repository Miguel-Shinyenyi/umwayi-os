# Layer 12 notes: the web interface (the view)

Facts read or tried on Nov 10 2026, for the spec in PR 38 (requirements 12.R1 to 12.R11, design.md "Layer 12"). Nothing here is built yet. Facts are in my own words. Tried means run in a throwaway folder, not in the repo.

## The packages

- **three.js 0.187.0**: licence MIT; the registry shows it last modified on 2026-10-30 ([npm: three](https://www.npmjs.com/package/three)).
- **esbuild 0.28.2**: licence MIT; its `package.json` has a `postinstall` script (`node install.js`) and 26 optional dependencies, one platform package per operating system and processor ([npm: esbuild](https://www.npmjs.com/package/esbuild)).
- **Tried, with `--ignore-scripts`:** on Linux x64 with Node 22.23.4 and npm 11.4.2, `npm install --ignore-scripts --save-exact` of these two versions added 28 packages, including `@esbuild/linux-x64`, and esbuild then bundled three.js in about 100 ms. So `npm ci --ignore-scripts` is enough for esbuild: the binary comes from the platform package, not from the postinstall script. It would fail if the optional packages are skipped (`--no-optional`), which is what esbuild's own error text warns about ([esbuild issue 3478](https://github.com/evanw/esbuild/issues/3478), [backstage issue 11079](https://github.com/backstage/backstage/issues/11079)).
- **Tried, the bundle:** the renderer, `EffectComposer`, `UnrealBloomPass` and `OutputPass`, bundled and minified into one script, were 554 KB. The script contained none of `fetch(`, `XMLHttpRequest`, `WebSocket`, `sendBeacon`, `import(`, `localStorage`, `sessionStorage`, `indexedDB`, `document.cookie`, `//cdn` or an `https://` string. It contained exactly one `http://` string: `http://www.w3.org/1999/xhtml`, an XML namespace name that three.js passes to `createElementNS`. It is not a request, so the static test of 12.R10.3 keeps a short list of allowed namespace names instead of banning every `http://`.
- **Not tried:** a bundle that imports one of three.js's file loaders. Those use `fetch`, which is why the design imports none (12.R2.5).

## The browser

- `prefers-reduced-motion: reduce` is a setting for less non-essential motion; it has been available across browsers since January 2020 ([MDN](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/prefers-reduced-motion)).
- `prefers-contrast` takes `more`, `less`, `custom` or `no-preference` ([MDN](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/prefers-contrast)). The design uses `less` only to start Calm mode on (UI-Q9).
- `FileReader.readAsText` reads a file the user picked, in the browser, with no request ([MDN](https://developer.mozilla.org/en-US/docs/Web/API/FileReader)). This is how the page gets the snapshot (UI-Q7).
- WCAG 2.2 has 2.3.1 Three Flashes or Below Threshold, 2.3.3 Animation from Interactions and 1.4.3 Contrast (Minimum) ([WCAG 2.2](https://www.w3.org/TR/WCAG22/)). The design is stricter than 2.3.1 (no flashing at all). The 4.5 to 1 text floor is the 1.4.3 level AA ratio.

## Not confirmed (the owner's interface check and UI.1 to UI.5 settle these)

- That a Download of a text Blob works under a Content-Security-Policy with `default-src 'none'` in the owner's browser.
- That `navigator.clipboard` works for a page opened from disk (it needs a secure context; the page falls back to selecting the text).
- That the build gives the same bytes on the owner's machine as on the machine that committed it (`build.json` would differ if esbuild output depended on the platform).
- How the owner's system exposes reduced motion and less contrast.
- Whether 30 frames a second holds on the owner's integrated GPU at 1440 by 900.

## The owner's interface check (UI.5): steps, expected output, results (NOT DONE YET)

Written Nov 10 2026 with the spec. Nothing here has been run. It is the owner's, on the owner's machine, with the finished page from UI.5. It is also the `UI` entry of the checks panel in the page.

Rules for this check:

- Record yes or no, counts and version strings. Never paste a value from your own files into a result.
- umwayi never runs npm or opens a browser; every command below is typed by the owner.

### 0. Prepare

1. `node --version` prints `v22.` or later.
2. In `ui/`: `npm ci --ignore-scripts`, then the build command in `ui/README.md`. Expected: `git status` shows no change to `ui/dist/index.html` or `ui/dist/build.json` (the build is the committed build). Record whether it changed.
3. In the umwayi root: `umwayi view snapshot; echo "exit $?"`. Expected: a line naming the snapshot file, and `exit 0`.

### 1. The page

1. Open `ui/dist/index.html` from disk. Expected: the hillside at dusk, a small "sample" label in a corner, nothing moving. Wait 10 seconds. Nothing flashes, blinks or drifts.
2. Open the browser's developer tools, the network tab, and reload. Expected: no request except the page itself.
3. Click a station. Expected: the camera eases to it, the panel opens, the motion ends within 3 seconds and the picture is still again. Press Esc: back to the overview.
4. Keyboard only: Tab to a label, use the arrow keys between stations, Enter to select, Esc to go back. Expected: the focus is always visible and the panel takes the focus and gives it back.
5. Switch on reduced motion in the system settings and reload. Expected: a click on a station jumps the camera, and the panel's Previous and Next step through still poses.
6. Press Calm mode. Expected: lower brightness and contrast, and the words stay easy to read.
7. Narrow the window to about 390 pixels. Expected: the panel is a bottom sheet and no label covers another.

### 2. Your own state

1. In the page, pick `.umwayi/snapshot.json`. Expected: the "sample" label is gone and the date next to the scene is today's.
2. The queue sheep equal `umwayi queue list --status open` (count the rows); the Logbook panel shows the entries count of `LOGBOOK.md`; the Kill switch hurdle matches `umwayi kill status`.
3. `umwayi kill on --reason "UI check"`, then `umwayi view snapshot`, load the new file: the hurdle is up. Then `umwayi kill off` and a new snapshot.
4. Pick a file that is not a snapshot (for example `rules.yaml`). Expected: one message, nothing changes in the scene.

### 3. The checks panel

1. Open the checks panel. Expected: six checks, each "not done".
2. Tick one step and type a result with names only. Expected: the check still says "not done" until all its steps are ticked, and then "ticked by you", never "passed".
3. Type an email address into a result. Expected: a warning on that field.
4. Export. Expected: the text lists every check with its steps and ends with "These are your notes. umwayi did not run or verify anything." Copy it. Close the page and open it again. Expected: the notes are gone.

### Results (to be filled in by the owner; all NOT DONE)

| step | what to record | result |
| --- | --- | --- |
| 0.2 | did the build change `ui/dist/`? | not done |
| 0.3 | exit code of `umwayi view snapshot` | not done |
| 1.1 | anything that moved, flashed or blinked in 10 seconds | not done |
| 1.2 | number of requests in the network tab | not done |
| 1.3 | seconds until the picture was still after a click | not done |
| 1.4 | focus visible, panel focus in and out | not done |
| 1.5 | camera jump and pose steps with reduced motion on | not done |
| 1.6 | Calm mode: readable or not | not done |
| 1.7 | bottom sheet and no overlap at 390 pixels | not done |
| 2.1 | "sample" gone, the date | not done |
| 2.2 | queue, logbook and kill switch match the commands | not done |
| 2.3 | hurdle up with the kill switch on | not done |
| 2.4 | a non snapshot file refused | not done |
| 3.1 to 3.4 | six checks, "ticked by you", the warning, the export text, notes gone after closing | not done |
