// The automatic lower detail mode (12.R12.3). Pure: what the machine looks like in, a step out. The page starts at
// step 0 (high) or step 2 (low) and steps down one at a time, twice at most, after sustained slow frames.
export const STEPS = [
  { name: 'high', pixelRatio: 2, bloom: true, msaa: 4, shadows: true, shadowMap: 2048, plants: 1 },
  { name: 'high, pixel ratio 1', pixelRatio: 1, bloom: true, msaa: 4, shadows: true, shadowMap: 2048, plants: 1 },
  { name: 'low', pixelRatio: 1, bloom: false, msaa: 0, shadows: true, shadowMap: 1024, plants: 1 },
];
// The owner cut a third step on Nov 11 (no shadows, fewer plants). The ladder ends at 'low'.
export const LOW_START = 2;

const SOFTWARE = /swiftshader|llvmpipe|softpipe|software|basic render|microsoft basic/i;

// env: { hash, renderer, cores, memory }. hash is location.hash ("#detail=low"); renderer is the unmasked renderer string;
// cores is navigator.hardwareConcurrency; memory is navigator.deviceMemory in GB. Anything missing is not held against the machine.
export function chooseDetail(env = {}) {
  const m = /detail=(high|low)/.exec(env.hash || '');
  if (m) return m[1] === 'low' ? LOW_START : 0;
  if (env.renderer && SOFTWARE.test(env.renderer)) return LOW_START;
  if (Number.isFinite(env.cores) && env.cores <= 4) return LOW_START;
  if (Number.isFinite(env.memory) && env.memory <= 4) return LOW_START;
  return 0;
}
// A mode forced in the address (#detail=high or #detail=low) is kept: the page does not step down from it.
export const isPinned = (hash) => /detail=(high|low)/.test(hash || '');
export const stepDown = (i) => Math.min(STEPS.length - 1, i + 1);

// A step down after SLOW_FRAMES frames averaging more than SLOW_MS (a little over 30 frames a second).
export const SLOW_FRAMES = 24;
export const SLOW_MS = 34;
export function shouldStepDown(times) {
  if (times.length < SLOW_FRAMES) return false;
  return times.reduce((a, b) => a + b, 0) / times.length > SLOW_MS;
}

// UI.8: the High tier (the picture of tier 3, built on top of Standard on the public site) steps down to Standard by itself.
// It is not a rung of the ladder above: those rungs lower the detail inside a tier, this takes the tier off. It looks at a
// shorter window than the ladder (HIGH_WINDOW frames, a little under a second at 30 frames a second) with the same measure
// (an average above SLOW_MS), and it says so once: the watch calls onSlow a single time and is done. Nothing in it puts High
// back; only the visitor's own choice of High (boot.js) arms a new watch.
export const HIGH_WINDOW = 20;
export function shouldLeaveHigh(times) {
  if (!Array.isArray(times) || times.length < HIGH_WINDOW) return false;
  const last = times.slice(-HIGH_WINDOW);
  if (!last.every((t) => Number.isFinite(t) && t >= 0)) return false; // a frame time that is not a number is not evidence
  return last.reduce((a, b) => a + b, 0) / last.length > SLOW_MS;
}
export function createHighWatch(onSlow) {
  let times = [], done = false;
  return {
    get done() {
      return done;
    },
    // true on the one frame that ended the watch
    note(dt) {
      if (done) return false;
      times.push(dt);
      if (times.length < HIGH_WINDOW) return false;
      const slow = shouldLeaveHigh(times);
      times = [];
      if (!slow) return false;
      done = true;
      onSlow();
      return true;
    },
  };
}
