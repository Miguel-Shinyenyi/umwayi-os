# Layer 12 notes: the web interface (the view)

Facts read or tried on Nov 10 and Nov 11 2026, for the spec in PR 38 and the rework in PR 39 (requirements 12.R1 to 12.R11, design.md "Layer 12"). Nothing here is built yet. Facts are in my own words. Tried means run in a throwaway folder, not in the repo.

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

## The place (read Nov 11 2026, for the highlands scene)

- **Mount Kenya** is an eroded, long extinct volcano 150 km north north east of Nairobi and about 16.5 km south of the equator. Its highest peaks are Batian at 5,199 m, Nelion at 5,188 m and Point Lenana at 4,985 m; the two highest are jagged and need technical climbing ([Wikipedia](https://en.wikipedia.org/wiki/Mount_Kenya), [Britannica](https://www.britannica.com/place/Mount-Kenya)). UNESCO counts 12 remnant glaciers, all receding, and four secondary peaks at the head of U shaped glacial valleys ([UNESCO](https://whc.unesco.org/en/decisions/5125)). The scene draws two sharp peaks with snow on the upper slopes. It does not draw the glaciers one by one.
- **Nanyuki** sits at about 1,947 m on the equator at the north western foot of the mountain, the staging town for the Laikipia plateau ([Tripbase](https://www.tripbase.com/destinations/nanyuki-kenya/nature/), a secondary source). The scene is a river valley on that plateau, looking towards the mountain. The distance and the angle of the mountain in the scene are chosen for the picture, not measured.
- **African pencil cedar** (Juniperus procera) is an evergreen conifer of the highland forests of eastern Africa, found from 1,050 to 3,000 m and mainly above 1,800 m, including the lower slopes of Mount Kenya and the Aberdares; pyramidal when young, with fine, open foliage ([World Agroforestry](https://apps.worldagroforestry.org/usefultrees/pdflib/Juniperus_procera_KEN.pdf), [Wikipedia](https://en.wikipedia.org/wiki/Juniperus_procera)). The scene draws it as a dark, narrow, layered cone.
- **Umbrella thorn acacia** (Vachellia tortilis) is the characteristic tree of the dry woodland and savanna of Kenya, often along rivers, and drought resistant ([FAO](https://www.fao.org/4/ab396e/ab396e03.htm), [Infonet Biovision](https://infonet-biovision.org/trees/umbrella-thorn-acacia)). The scene draws it with a thin trunk and a flat, wide, layered crown.
- **Grass.** Red oat grass (Themeda triandra) is a common grass of the open plains ([Amboseli](https://amboselikenya.com/plants-flora/)), and in the highlands at 2,100 to 2,700 m the land is patches of evergreen forest separated by wide expanses of short grass ([Britannica](https://www.britannica.com/place/Kenya/Plant-and-animal-life)). The scene's grass is dry gold with green, in short blades.
- All of this was used to choose shapes and colours. It is not a survey; the scene is an image of the place, not a map of it.

## Round 2 (read Nov 11 2026, for UI-Q17 to UI-Q22)

- **Next.js** 16.4.6 is the latest version on the npm registry on Nov 11 2026 (`npm view next version`); the 16 line is the current one and Next.js 15 left maintenance on Oct 21 2026 ([endoflife.date](https://endoflife.date/nextjs), [nextjs.org support policy](https://nextjs.org/support-policy)). UI.6 pins the exact version it is built with.
- **The Network Information API** (`navigator.connection`, with `effectiveType`, `downlink` and `saveData`) is experimental and mainly in Chromium browsers; Safari and Firefox do not offer it ([caniuse](https://caniuse.com/mdn-api_navigator_connection)). So the tier choice treats a missing API as unknown and never picks High from it. `navigator.deviceMemory` is also Chromium only.
- **The shuka** is the cloth wrapped round the body that the Maasai of Kenya and Tanzania wear every day; red is the most common colour, and blue, striped and checked cloths are also worn; beaded necklaces are part of the dress ([G Adventures](https://www.gadventures.com/blog/story-behind-maasais-shuka-cloth/), [Masai Mara National Reserve](https://masaimara.ke/the-maasai-shuka-a-guide-to-the-iconic-cloth/)). The figure uses only these shapes: a cloth over one shoulder, a staff, a collar as a shape; no face detail.
- **Sheep in Kenya**: the Red Maasai is the native breed of the Maasai and other peoples, and the Dorper (from South Africa, a white body and a black head) has been widely crossed with it since the 1970s ([Wikipedia](https://en.wikipedia.org/wiki/Red_Maasai_sheep), [MDPI, Animals 2023](https://www.mdpi.com/article/10.3390/ani13020300)). Goats such as the Galla are kept beside them ([MDPI, Sustainability 2021](https://www.mdpi.com/2071-1050/13/17/9629/htm)). The flock mixes these coats.

Content was rephrased for compliance with licensing restrictions.

## How the look is made (decisions of Nov 11, not facts from outside)

- No photograph, texture file, model or font is used in List, Standard or the live view (High, on the public site only, uses the five photographs listed under "The High assets" below). Terrain is a height function from noise; the ground, rock, wood, wool, iron and water are shaders and vertex colours; plants are instanced shapes; clouds are made once from noise; the mountain is a displaced mesh. This keeps the page under about 2 MB with three.js bundled (the bundle was 554 KB for the renderer, the composer and the bloom pass on Nov 10).
- A bump made from noise derivatives (the screen space change of a noise value) gives fine relief with no texture.
- three.js 0.187.0 removed `PCFSoftShadowMap` (a console warning on Nov 10), so shadows use `PCFShadowMap`.
- The automatic lower detail mode reads the renderer name (software rendering such as SwiftShader or llvmpipe is low), `navigator.hardwareConcurrency` and `navigator.deviceMemory` where the browser has them, and the measured frame times. None of these is a network request.

## Not confirmed (the owner's interface check and UI.1 to UI.5 settle these)

- That a Download of a text Blob works under a Content-Security-Policy with `default-src 'none'` in the owner's browser.
- That `navigator.clipboard` works for a page opened from disk (it needs a secure context; the page falls back to selecting the text).
- That the build gives the same bytes on the owner's machine as on the machine that committed it (`build.json` would differ if esbuild output depended on the platform).
- How the owner's system exposes reduced motion and less contrast.
- Whether 30 frames a second holds on the owner's integrated GPU at 1440 by 900, in high detail and in low detail.
- Whether the real life look reads as real enough to the owner at one page under about 2 MB. That is a judgement on the screenshots.

## The owner's interface check (UI.5): steps, expected output, results (NOT DONE YET)

Written Nov 10 2026 with the spec and brought up to date on Nov 11 2026 for the page as built after UI.4 (the tier switch, the snapshot picker, the owner checks panel, Download). Nothing here has been run. It is the owner's, on the owner's machine, with the page from `ui/dist/index.html`. It is also the `UI.5` entry of the checks panel in the page, so you can run it from the panel: every step below is a step there. The scene itself is still being finished (UI.7, High); steps 1.1 to 1.8 judge the Standard picture as it is, and are to be run again when UI.7 is merged.

Rules for this check:

- Record yes or no, counts and version strings. Never paste a value from your own files into a result.
- umwayi never runs npm or opens a browser; every command below is typed by the owner.

### 0. Prepare

1. `node --version` prints `v22.` or later.
2. In `ui/`: `npm ci --ignore-scripts`, then the build command in `ui/README.md`. Expected: `git status` shows no change to `ui/dist/index.html` or `ui/dist/build.json` (the build is the committed build). Record whether it changed.
3. In the umwayi root: `umwayi view snapshot; echo "exit $?"`. Expected: a line naming the snapshot file, and `exit 0`.

### 1. The page

1. Open `ui/dist/index.html` from disk. Expected: the Kenyan highlands at dusk with Mount Kenya on the horizon, a lantern held on a staff at the centre as the brightest point, no name written anywhere in the picture, a small "sample" label, and the home content below. Wait 10 seconds. Nothing flashes, blinks, sways or drifts.
2. Open the browser's developer tools, the network tab, and reload. Expected: no request except the page itself.
3. Move the cursor over a feature: its name appears and a little warm light lifts on it. Click it. Expected: the camera eases to it, the panel opens, the motion ends within 3 seconds and the picture is still again. Press Esc: back to the overview.
4. Keyboard only: Tab to a label, use the arrow keys between stations, Enter to select, Esc to go back. Expected: the focus is always visible and the panel takes the focus and gives it back.
5. Switch on reduced motion in the system settings and reload. Expected: a click on a station jumps the camera, and the panel's Previous and Next step through still poses.
6. Press Calm mode. Expected: lower brightness and contrast, and the words stay easy to read.
7. Narrow the window to about 390 pixels. Expected: the panel is a bottom sheet and the home content reads in one column.
8. Add `#detail=low` to the address and reload. Expected: the same scene with less detail and no bloom. Remove it and add `#detail=high`.
9. Home content: press Copy on a command and paste it somewhere. Expected: the command, exactly. Devpost and demo video say "link to come" and are not links.
10. Press List in the top bar, then Standard. Expected: List shows the title, the status strip and the eleven stations as text, with no picture; Standard shows the picture again. The address gets `#tier=list` or `#tier=standard` and nothing else.
11. Press Tab from the top of the page and count. Expected: List, Standard, Owner checks, Calm mode, then the eleven names in the order Memory, Rules, Queue, Archive, Logbook, Automation, AI helpers, Workflows, Adapters, Kill switch, Budget, and the focus is visible on each.
12. Turn on your screen reader and move through the page by landmarks and headings. Expected: one main landmark, the title, and the sections The valley, The state of this root, The eleven stations, Start, Links, each with a name; the picture is described in words and the description says where the List view is. Record anything missing or wrong.

### 2. Your own state

1. In the page, press Open a snapshot file (under the status strip) and pick `.umwayi/snapshot.json`, or drop the file on the page. Expected: the "sample" label is gone and the date next to the scene is today's.
2. The queue sheep equal `umwayi queue list --status open` (count the rows); the Logbook panel shows the entries count of `LOGBOOK.md`; the Kill switch gate matches `umwayi kill status`.
3. `umwayi kill on --reason "UI check"`, then `umwayi view snapshot`, load the new file: the gate is shut and its lamp is red. Then `umwayi kill off` and a new snapshot.
4. Pick a file that is not a snapshot (for example `rules.yaml`). Expected: one message that says the file is not a snapshot of this version, and nothing changes in the scene.

### 3. The checks panel

1. Open the checks panel. Expected: six checks, each "not done".
2. Tick one step and type a result with names only. Expected: the check still says "not done" until all its steps are ticked, and then "ticked by you", never "passed".
3. Type an email address into a result. Expected: a warning on that field.
4. Export. Expected: the text lists every check with its steps and ends with "These are your notes. umwayi did not run or verify anything." Copy it. Close the page and open it again. Expected: the notes are gone.
5. Press Download. Expected: a file `umwayi-owner-checks.txt` is saved with the same text as the box. If your browser does not save it, the page says Copy only; record that.
6. Press Close. Expected: the panel closes and the focus goes back to the button that opened it.

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
| 1.7 | bottom sheet and one column home content at 390 pixels | not done |
| 1.8 | low and high detail both draw | not done |
| 1.9 | Copy gives the exact command; placeholders are not links | not done |
| 1.10 | List and Standard both work; the address shows only the tier | not done |
| 1.11 | the Tab order and a visible focus | not done |
| 1.12 | what the screen reader said, and anything missing | not done |
| 2.1 | "sample" gone, the date | not done |
| 2.2 | queue, logbook and kill switch match the commands | not done |
| 2.3 | hurdle up with the kill switch on | not done |
| 2.4 | a non snapshot file refused | not done |
| 3.1 to 3.6 | six checks, "ticked by you", the warning, the export text, notes gone after closing, Download saved a file or said Copy only, focus back on the button | not done |

## Facts found while building UI.6 (Nov 11 2026, tried in the repo's own `site/` with Next.js 16.4.6)

- With the Content-Security-Policy `script-src 'self'`, a production build of the site does not start in the browser: Next.js puts three small inline scripts in every prerendered page, the browser blocks each one with a console error, and the page stays as the server sent it (List). The Next.js guide offers a nonce, which needs every page to render per request, or experimental subresource integrity, which hashes the script files. Neither was used; `script-src 'self' 'unsafe-inline'` was (KNOWN-LIMITS 140). Source: [nextjs.org Content Security Policy guide](https://nextjs.org/docs/app/guides/content-security-policy).
- `turbopack.resolveAlias` takes a wildcard key (`'three/addons/*'` to `./node_modules/three/examples/jsm/*`). With only the plain `three/addons` key, a build with no `ui/node_modules` failed with "Module not found"; it had passed on a machine where `ui/` was installed, because the import walked up to `ui/node_modules`. The test of this is to build with `ui/node_modules` moved away.
- `Permissions-Policy: bluetooth=()` gives a Chromium console warning (unrecognized feature), so the site does not send it.
- `next build` for this site is static for `/` (prerendered); `next start` applies the `headers()` of `next.config.mjs`. A static export would not send them, so the site is not exported.
- Headless Chromium 158.0.8127.18 (Playwright 1.65 headless shell, SwiftShader) was used for the pass; the Playwright browser tool of this sandbox could reach only the sandbox's second address, not 127.0.0.1, so the pass was driven from a script outside the repo.

## Facts found while building UI.5, first slice (Nov 11 2026)

- **What the WCAG 2.2 rules say that this slice relies on** ([WCAG 2.2](https://www.w3.org/TR/WCAG22/)): 1.4.3 Contrast (Minimum), 4.5 to 1 for text at level AA; 1.4.11 Non-text Contrast, 3 to 1 for the parts of a control and for a focus indicator; 2.5.8 Target Size (Minimum), a control is at least 24 by 24 CSS pixels unless it has room around it (new in 2.2); 2.4.7 Focus Visible; 1.3.1 Info and Relationships (landmarks, headings, names); 4.1.3 Status Messages (a message is in a live region). The page aims at AA. The 4.5 floor is the owner's UI-Q9.
- **Contrast, worked out from `ui/src/style.css` on Nov 11 2026:** normal mode, ink on the page 15.4 to 1, muted on the page 8.4 to 1; Calm mode, ink 10.0 and muted 7.0. The lowest text ratio on any ground the CSS uses (page, solid panel, glass over the page, the dark wells) is 6.9 to 1 in normal mode and 6.0 to 1 in Calm mode, both muted on the solid panel. The field border is 4.2 and 3.7 to 1 at worst, and the focus ring 7.3 and 7.2.
- **Three things the checks found and the CSS now fixes:** the tick boxes of the owner checks panel were 18 pixels (now 24); the browser's own placeholder colour is too faint on the dark fields (now the muted colour, at full opacity so Firefox does not dim it); the border of a field was the faint line colour (now `--field-line`, 3 to 1 or better). A fourth, found in the browser: at 390 pixels the owner checks panel was 1005 pixels wide, because long commands in a grid column could not shrink; the grid, its items and the text now shrink and wrap, and a code block scrolls inside its own box.
- **Headless Chromium 151 at 390 by 844, Nov 11 2026:** the owner checks panel open: document width 390, no control under 24 by 24; the station panel open at Standard: a bottom sheet 390 wide inside the first screen (its bottom is the bottom of the picture area, 674 pixels down, above the status strip), no sideways scroll.
- **Order of the keyboard:** List, Standard, Owner checks, Calm mode, then the eleven names in the order of the list view, then the station panel (reachable only while it is open), the snapshot button and the rest. The names show on focus; at rest nothing is written in the picture.
- **Not run:** a screen reader, a real GPU, Firefox, Safari, touch. The interface check above (1.12 for the screen reader) is the owner's.

## The High assets (UI.7, read and downloaded Nov 11 2026)

The High tier of the public site uses five photographs from Poly Haven, at 1k (1024 by 1024) as JPEG. Poly Haven's licence page says every asset on the site (HDRIs, textures and models) is CC0, so it may be used for any purpose with no credit needed ([Poly Haven licence](https://polyhaven.com/license)), and each asset's own page also shows CC0. The author and the date come from Poly Haven's public API (`api.polyhaven.com/info/<id>`), and the md5 of each download matched the md5 in its file list (`api.polyhaven.com/files/<id>`). The machine readable list, with sizes and SHA-256, is `site/high-assets.json`; `tests/test_site_assets.py` checks the files, this list and the code agree. The site serves the files from its own host under `/high/`; no browser fetches anything from Poly Haven.

| file | asset | author | licence | source |
| --- | --- | --- | --- | --- |
| `grass_ground_diff_1k.jpg` (colour) | Grass Ground | Charlotte Baglioni | CC0 1.0 | [polyhaven.com/a/grass_ground](https://polyhaven.com/a/grass_ground) |
| `grass_ground_nor_gl_1k.jpg` (normal map) | Grass Ground | Charlotte Baglioni | CC0 1.0 | [polyhaven.com/a/grass_ground](https://polyhaven.com/a/grass_ground) |
| `red_laterite_soil_stones_diff_1k.jpg` (colour) | Red Laterite Soil Stones | Amal Kumar | CC0 1.0 | [polyhaven.com/a/red_laterite_soil_stones](https://polyhaven.com/a/red_laterite_soil_stones) |
| `dark_rock_02_diff_1k.jpg` (colour) | Dark Rock 02 | Amal Kumar | CC0 1.0 | [polyhaven.com/a/dark_rock_02](https://polyhaven.com/a/dark_rock_02) |
| `dark_rock_02_nor_gl_1k.jpg` (normal map) | Dark Rock 02 | Amal Kumar | CC0 1.0 | [polyhaven.com/a/dark_rock_02](https://polyhaven.com/a/dark_rock_02) |

The CC0 deed is at [creativecommons.org/publicdomain/zero/1.0](https://creativecommons.org/publicdomain/zero/1.0/). The grass and the rock photographs are not of Laikipia; they were chosen for colour and grain, and the High shader tints them towards the Standard palette. Not checked: whether an asset was ever under another licence before Poly Haven published it (the page and the licence page are the only sources). Poly Haven's API has its own terms; it was read by hand for these five assets, and nothing in the repo calls it.

Content was rephrased for compliance with licensing restrictions.
