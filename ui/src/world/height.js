// The ground. One pure function, so tests can check that the stations stand on flat land.
import { smoothstep } from '../engine/ease.js';

const wave = (x, z) =>
  Math.sin(x * 0.11 + 1.3) * Math.cos(z * 0.09 - 0.4) + 0.55 * Math.sin(x * 0.043 - z * 0.057 + 2.0) + 0.3 * Math.sin(x * 0.23 + z * 0.19);

// Flat inside the ring (r < 14.5), a small mound under the lantern, then rolling land that climbs into hills.
export function heightAt(x, z) {
  const r = Math.hypot(x, z);
  const mound = 0.55 * Math.exp(-(r * r) / (2 * 2.3 * 2.3));
  const rolling = smoothstep(14.5, 26, r) * (0.9 + 0.8 * wave(x, z));
  const rise = Math.pow(smoothstep(28, 78, r), 1.5) * (5 + 3 * (0.5 + 0.5 * wave(x * 1.7 + 9, z * 1.7 - 4)));
  return mound + rolling + rise;
}
export const MOUND = heightAt(0, 0);
