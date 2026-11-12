# W6 notes: the local backend (`umwayi serve`)

Facts read on Nov 12 2026 for the spec in the W6.0 pull request (requirements W6.R1 to W6.R18, design.md "Local backend (W6)"). Nothing here is built. Facts are in my own words. **Nothing in this file was tried in a browser**: every browser behaviour below comes from documentation, and the spec is written so that the server does not depend on any of it (the token, the `Host` check and the exact `Origin` on `POST` and `DELETE` decide; the other headers are checked only when present). The by-hand browser pass is task W6.10.

## What a browser sends

- **`Origin`.** MDN says a browser adds it to cross-origin requests and to same-origin requests other than `GET` and `HEAD`, so a same-origin `POST` or `DELETE` carries it and a same-origin `GET` need not. It can be `null` for a file, a `data:` page, a sandboxed frame and some redirects. It is a forbidden header, so page script cannot set or change it ([MDN: Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Origin)). This is why the gate requires `Origin` on `POST` and `DELETE`, accepts a missing one on `GET`, and refuses `null` (W6.R5.2.8).
- **Fetch metadata (`Sec-Fetch-Site`, `Sec-Fetch-Mode`, `Sec-Fetch-Dest`).** They are forbidden request headers too, and MDN says they are sent only to potentially trustworthy URLs, so a server on a plain `http://` origin may not get them ([MDN: Fetch metadata](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Fetch_metadata)). **Not verified:** whether a browser sends them to `http://127.0.0.1`. The gate therefore checks them when they are present and never needs them.
- **`Host`.** The browser sends the name and port of the address bar. A page on another site that makes the owner's browser resolve its own name to 127.0.0.1 sends that name in `Host`, which is what the `Host` check sees (W6.R6.3).

## Why the `Host` check is not optional

- The advisory for the Apollo MCP Server (GHSA-wqrj-vp8w-f8vh) says that a server on localhost that did not validate `Host` could be reached by a malicious website through DNS rebinding, bypassing the browser's same-origin rules, and that the fix was to validate `Host` against the expected localhost values with port matching. It also says running an HTTP server on localhost without authentication is not recommended ([GitHub advisory](https://github.com/apollographql/apollo-mcp-server/security/advisories/GHSA-wqrj-vp8w-f8vh)). umwayi does both: `Host` is exact (W6.R5.2.4) and a token is required.
- The search results for other advisories (the Rust MCP SDK, Microsoft UFO) describe the same pattern. They were read as search summaries only.

## Private network requests

- Chrome documented a preflight for requests from a public page to a private or local address: the request carries `Access-Control-Request-Private-Network: true` and the answer must carry `Access-Control-Allow-Private-Network: true`. The post was updated on July 7 2022 and says the rollout was staged ([Chrome: Private Network Access, introducing preflights](https://developer.chrome.com/blog/private-network-access-preflight)). Chrome later described the feature as renamed Local Network Access with a permission prompt ([Chrome: PNA permission prompt](https://developer.chrome.com/blog/pna-permission-prompt-ot-end), seen in a search summary only). **Not verified:** what Chrome 151 or any other browser does today for a public page calling 127.0.0.1.
- umwayi answers no preflight at all. An `OPTIONS` request is 405 with no `Access-Control-` header, so a page that needs the private network permission never gets it (W6.R6.4). That is the intended result: no page on another origin may call the backend.

## What was not looked at

- Safari and Firefox behaviour for any of the above.
- Whether `http://127.0.0.1` counts as a secure context for the features the page uses (it does not need any secure-context feature; the page uses `fetch`, which works on plain HTTP).
- `Cross-Origin-Resource-Policy` and `Cross-Origin-Opener-Policy` on a loopback page, and `frame-ancestors` in a header (the headers are in W6.R6.6 by the standard names; their effect is for the by-hand pass).
- The by-hand results of W6.10 go here, with the date, the browser and its version.
- **Nov 12 2026, the build of W6.1 to W6.6:** the wire tests (`tests/serve/test_wire.py`) send the headers by hand, with a raw socket and `http.client`-style requests, and no browser was started. So nothing above is tested against a browser yet; the by-hand pass is still W6.10.
