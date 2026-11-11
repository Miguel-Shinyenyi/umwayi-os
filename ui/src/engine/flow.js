// The clock of the flowing water (12.R20.2), the one thing besides a station's action that moves without input (the
// owner's exception, Nov 11 round 2). It runs only when the water may move: not with reduced motion, not in Calm mode,
// not while the page is hidden or the scene is off screen, and not in the List tier ("flat"). While it runs the loop
// draws at most one frame every FLOW_FRAME_MS (30 frames a second at most).
export const FLOW_FRAME_MS = 31; // every second frame at 60 Hz, every fifth at 144 Hz: never more than 30 a second
const KEYS = ['reduced', 'calm', 'hidden', 'offscreen', 'flat'];

export function createFlow({ wake = () => {}, onChange = () => {} } = {}) {
  const state = Object.fromEntries(KEYS.map((k) => [k, false]));
  let last = -Infinity;
  const flow = {
    time: 0, // seconds of flow; the water shader reads it
    get active() { return KEYS.every((k) => !state[k]); },
    set(patch) {
      const was = flow.active;
      for (const k of KEYS) if (k in patch) state[k] = !!patch[k];
      if (!was && flow.active) { last = -Infinity; wake(); }
      if (was !== flow.active) onChange(flow.active);
    },
    step(dt) { if (flow.active) flow.time += dt / 1000; },
    // true when a frame for the water alone should be drawn at time ts (ms)
    due(ts) {
      if (ts - last < FLOW_FRAME_MS) return false;
      last = ts;
      return true;
    },
  };
  return flow;
}
