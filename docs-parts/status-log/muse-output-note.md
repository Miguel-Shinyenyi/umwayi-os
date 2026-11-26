date: 2026-11-26
pr: none
what: A docs note on the first real Muse run: `docs/muse-output-design.md`. The run printed a 54 line JSON stream and settled `unknown 100 UU` although Muse printed its own token counts. The note lists the fields of the stream (the final text is in `run.terminal.completed`, the counts in `run.usage`), gives options for the output (print only the final text, with a raw flag) and for the settle (declared from `run.usage`, or keep `unknown`), and recommends the output change now and the settle later, because four credit readings showed no movement. Nothing built, no second run.
tests: none new; the docs tests (the four parts, the links, the line count).
