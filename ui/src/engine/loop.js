// Drawing on demand. There is no free running animation frame loop.
// invalidate() asks for one frame. The loop keeps asking only while a tween runs, a follow has not come to rest, or the
// water flows (flow.js). While only the water moves it draws at most one frame every FLOW_FRAME_MS, and those frames do not
// count towards the detail mode's frame times. With the water still, at rest the page draws nothing and the GPU is idle.
import { clamp } from './ease.js';

// onBusy(moving) is told when the page starts and stops moving (not counting the water), so the page can say so in the DOM.
export function createLoop({ render, motion, follows = [], flow = null, raf, onFrameTime = () => {}, onBusy = () => {} }) {
  let pending = false, forced = false, wasBusy = false;
  let last = null;
  const busy = () => motion.active || follows.some((f) => f.active);
  const flowing = () => !!flow && flow.active;
  const schedule = () => {
    if (pending) return;
    pending = true;
    raf(frame);
  };
  const loop = {
    frames: 0,
    invalidate() { forced = true; schedule(); },
    wake() { schedule(); }, // the water starts to flow again
  };
  function frame(ts) {
    pending = false;
    const moving = forced || busy();
    if (!moving && flowing() && !flow.due(ts)) { schedule(); return; } // between two frames of the water: draw nothing
    const dt = last === null ? 16.7 : clamp(ts - last, 0, 50);
    last = ts;
    forced = false;
    motion.step(dt);
    for (const f of follows) f.step(dt);
    if (flowing()) flow.step(dt);
    render(dt);
    loop.frames++;
    if (moving) onFrameTime(dt);
    if (busy() !== wasBusy) { wasBusy = busy(); onBusy(wasBusy); }
    if (busy() || flowing()) schedule();
    else last = null;
  }
  return loop;
}
