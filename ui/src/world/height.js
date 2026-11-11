// The ground, in metres. One pure function used by the ground, the plants and the stations.
// A wide flat valley with a river cut into it and the lantern on a low knoll; hills rise away from the valley,
// higher on the left; the far hills carry the horizon.
import { smoothstep, lerp } from '../engine/ease.js';
import { fbm, ridged } from './noise.js';
import { nearestOnRiver, RIVER_HALF_WIDTH, RIVER_BANK, RIVER_DEPTH } from './river.js';

export { RIVER_HALF_WIDTH, RIVER_BANK, RIVER_DEPTH };
export const KNOLL = 1.2;

// how far the river channel is cut below the valley floor at distance d from the centre line
export const channel = (d) => RIVER_DEPTH * (1 - smoothstep(RIVER_HALF_WIDTH * 0.55, RIVER_HALF_WIDTH + RIVER_BANK, d));
export function riverBedDepth(x, z) {
  return channel(nearestOnRiver({ x, z }).distance);
}

export function heightAt(x, z) {
  const r = Math.hypot(x, z);
  const dRiver = nearestOnRiver({ x, z }).distance;
  const valley = smoothstep(11, 40, dRiver); // 0 on the valley floor, 1 up on the hills
  const away = smoothstep(19, 42, r); // the bowl round the lantern stays level
  // the hills: broad swells and a few sharp ridges; the left side climbs higher
  const swell = fbm(x * 0.012 + 3, z * 0.012 - 1, 4);
  const crest = ridged(x * 0.021 - 5, z * 0.021 + 2, 3);
  const left = smoothstep(-12, -44, x) * smoothstep(-34, 10, z);
  // the foreground (towards the viewer) stays low so the valley and its features can be seen from the slope in front
  const front = 1 - 0.96 * smoothstep(6, 34, z);
  const hills = (18 * swell + 16 * crest + 24 * left) * valley * away * front;
  // a gentle roll on the floor, less than half a metre, so the valley is not a table
  const roll = 0.5 * (fbm(x * 0.045 + 8, z * 0.045 + 4, 3) - 0.5) * 2 * (1 - 0.6 * smoothstep(34, 70, r));
  // the lantern knoll
  const knoll = KNOLL * Math.exp(-(r * r) / (2 * 2.6 * 2.6));
  return hills + roll + knoll - channel(dRiver);
}
export const WATER_LEVEL = -0.4; // the river surface; it does not flow
export { lerp };
