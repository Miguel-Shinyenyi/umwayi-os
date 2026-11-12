# site: the umwayi-os public site (layer 12)

The public home of umwayi-os: the title and promise, a status strip of sample counts, the install and first commands, the links
and the list of the eleven stations, all written into the HTML by the server, and the 3D scene drawn in the browser. It is a
Next.js app. It is not part of the `umwayi` package: nothing here imports `umwayi`, and umwayi never runs npm, node or this
site. The owner builds it and the owner deploys it (nothing here deploys anything or touches Vercel).

Status (UI.4): the page has the owner checks panel, the same code as the live view (`ui/src/ui/checks.js`, started by `ui/src/boot.js`). It is built in the browser from `ui/src/data/checks.js`, keeps its notes in memory only, reads nothing of the visitor's device or files and sends nothing. The server sends its empty frame (hidden) in `app/home.js`. A visitor can use it as a checklist for their own machine; Copy and Download make a text file in the browser.

Status (UI.3): a visitor can open a snapshot file of their own with the button in the status section, or drop it on the page. It is read in the browser with `FileReader` and checked strictly (`ui/src/data/snapshot.js`); nothing is uploaded, no request carries it, and nothing is stored. A file that is not a snapshot of this version gives one message and loads nothing. Without a file the page shows the sample world and says "sample". The only change in `site/` is the picker markup and the footer id in `app/home.js`, so it matches `ui/src/index.html`.

Status (UI.6): List and Standard. The 3D scene and the page behaviour are the ones in `ui/src`, used through the shared modules
(`ui/src/boot.js`, which builds the picture with `ui/src/scene.js`). High (tier 3) is UI.7. Requirements: 12.R16 to 12.R18 in
`.kiro/specs/umwayi-os/requirements.md`. Design: "The public site" in `design.md`. The doc: `docs/interface.md`.

## Packages

| package | version | what for |
| --- | --- | --- |
| `next` | **16.4.6** | the server rendering and the build |
| `react` | **19.3.1** | needed by Next.js |
| `react-dom` | **19.3.1** | needed by Next.js |
| `three` | **0.187.0** | the 3D drawing; the same version as `ui/`, and the one copy the shared scene uses here |

Every version is exact, with no `^`, `~` or range. `package-lock.json` is committed; every package in it has a `sha512` hash
and comes from registry.npmjs.org. `node_modules/` and `.next/` are never committed. Node.js 20.9 or later (22 is what it was
built with). There is no analytics, speed insights, error reporting or third party script package, no cookie, no storage, no
account and no third party font, script or image.

## Build and run

```
cd site
npm ci --ignore-scripts
npm run build        # node scripts/next.mjs build
npm start            # node scripts/next.mjs start, on http://localhost:3000
node --test          # or npm test: the Node tests (no browser, no network)
```

`scripts/next.mjs` runs the Next.js command line with `NEXT_TELEMETRY_DISABLED=1`, so Next.js sends nothing about the build.
`npm run dev` works the same way for the owner's own look at a change. The build is not recorded in a file like
`ui/dist/build.json`: the design does not ask for it, `.next/` is what Next.js writes and it is not committed, and the site is
built again on the host that serves it.

## What the server sends

`/` is built once and sent as static HTML: the home text, the status strip (every value says "sample" until a visitor opens a snapshot), the install and first
commands, the links and the list of the eleven stations, with `data-tier="list"` on the html element. With JavaScript off the
page is List and stays readable. The Copy buttons and the List and Standard switch appear only when the script has run.

The server sends these headers on every path (`next.config.mjs`):

| header | value |
| --- | --- |
| Content-Security-Policy | `default-src 'self'`, scripts from `'self'` and inline (Next.js writes three small inline scripts into every page), styles, images, fonts and connections from the site's own origin, `object-src 'none'`, `base-uri 'self'`, `form-action 'self'`, `frame-ancestors 'none'` |
| Referrer-Policy | `no-referrer` |
| X-Content-Type-Options | `nosniff` |
| X-Frame-Options | `DENY` |
| Permissions-Policy | everything off except `clipboard-write=(self)` for the Copy buttons |

## The device query and the switch

In the browser, `ui/src/engine/env.js` reads what the browser offers (cores, device memory, the Network Information API where it
exists, the graphics renderer hint, the screen size, reduced motion, and whether WebGL works), and `chooseTier` picks List or
Standard. **These hints are read in the page and never sent anywhere, stored or written to the address.** The List and Standard
switch keeps its choice in the address fragment only (`#tier=list`, `#tier=standard`), which a browser never sends to a server.
The site's host sees which files a browser asks for, so its logs can tell whether the scene script was loaded; that is a
property of serving files, not tracking, and nothing else about the device is sent. The site shows sample counts until a visitor opens a snapshot file of their own, which is read in the browser only.

## No copy of the scene

The scene and the page behaviour live once, in `ui/src`. The site imports them from there (`turbopack.root` in
`next.config.mjs` is the repo root, and `three` resolves to this folder's own copy). `tests/test_site_package.py` fails if any
file of `site/` repeats a file of `ui/src`.

## Tests

```
python -m unittest tests.test_site_package    # the package, the lockfile, no analytics, no remote font or script, no copy of ui/src, the headers
node --test                                   # in site/: what the server renders, the headers, the client part (no package other than react)
```

The Python suite needs no npm, node or browser. The browser pass (every request logged, the hints never in a request, List with
JavaScript off, Standard drawing) is run by hand; its results are in `docs/interface.md`.

## Files

```
package.json package-lock.json   exact versions
next.config.mjs                  headers, build root, one copy of three
scripts/next.mjs                 runs next with telemetry off
app/layout.js app/page.js        the page; the layout uses ui/src/style.css (there is no style file here)
app/document.js app/home.js      the html element (List) and the home text and list, rendered by the server
app/scene.js                     the one client part: starts ui/src/boot.js in the browser
test/                            node --test
```
