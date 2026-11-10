// Drawing on demand. There is no free running animation frame loop.
// invalidate() asks for one frame. The loop keeps asking only while a tween runs or a follow has not come to rest.
// At rest the page draws nothing and the GPU is idle.
import { clamp } from './ease.js';

export function createLoop({ render, motion, follows = [], raf, onFrameTime = () => {} }) {
  let pending = false;
  let last = null;
  const loop = {
    frames: 0,
    invalidate() {
      if (pending) return;
      pending = true;
      raf(frame);
    },
  };
  function frame(ts) {
    pending = false;
    const dt = last === null ? 16.7 : clamp(ts - last, 0, 50);
    last = ts;
    motion.step(dt);
    for (const f of follows) f.step(dt);
    render(dt);
    loop.frames++;
    onFrameTime(dt);
    if (motion.active || follows.some((f) => f.active)) loop.invalidate();
    else last = null;
  }
  return loop;
}
