date: 2026-11-25
pr: 246
what: J2 and J3, the table first, docs only. `docs/bypass-paths.md` lists the six bypass paths with the layer that refused each, the test, a status (proven in the wrapper, the read proven and the push not tried, or not blocked), and the two plain columns Works today and Needs proof. It says which paths the word blocked may be used for (3, 4, 5 and 6 in the confined wrapper on a kernel with Landlock, and the read of path 2) and that it may not be used for path 1, a push or a real run. The design note links to it. The scan that makes the word enforced sit next to a link to the table (J2) and the wider scan (K2) are code and wait for their own pull requests.
tests: none new; the docs tests (the four parts, the links, the line count).
