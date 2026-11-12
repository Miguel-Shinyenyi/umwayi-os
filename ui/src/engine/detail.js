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
