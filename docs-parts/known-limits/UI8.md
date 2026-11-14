section: Web interface (UI.8), found while building
title: The High step down is a frame time rule, so it can step down a good device and miss a bad one

`ui/src/engine/stage.js` takes High off after a slow window (KNOWN-LIMITS 156). The rule is small on purpose, and it is wrong in both directions sometimes.

- A window is 20 frames that the loop reports while the picture moves, averaging over 34 ms. A tab that was in the background, a machine busy with something else, or a first frame that compiles shaders can fill a window with slow frames, and a good device then loses High until the visitor asks for it again.
- A device that draws High slowly only at rest, or only when it is not moving, is never measured: the loop reports no frame time then.
- The step down is not undone when the machine speeds up. One slow window ends High for the session. The visitor can click High again; nothing else will.
- The notice is one line of text in the page. A screen reader that is not reading the notice area will not announce it, and the pressed state of the switch is what changes for it.
- A forced detail mode in the address (`#detail=high` or `#detail=low`) is kept, so a visitor who forces one never steps down, even on a very slow device.
- The 20 frames and the 34 ms are starting values, chosen with the ladder's own 34 ms. They were not tuned on a real device. The tests use fake frame times and a fake page; the change was not run in a real browser.
