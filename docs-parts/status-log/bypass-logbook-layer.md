date: 2026-11-25
pr: none
what: J1 step 4, the logbook line that names the layer. A kernel test of `tests/test_bypass_paths.py` writes one line per bypass path into a real, hash-checked logbook: `layer: kernel (landlock)` for the five paths the kernel refused and `layer: none` for path 1, the finding of limit 344. It is the test that records the layer it expects next to the refusal it observed (Q2 of the design note). A real run does not write these lines yet, and the push with a stored token is still not tried (W40); the note says so.
tests: `tests/test_bypass_paths.py` (a run-everywhere check of the line, and a kernel check that runs only where Landlock exists, so on CI Linux and never on a Mac).
