// Where the forest grows (12.R20.1): a dense band of montane trees just across the river from the lantern, and, far out to
// each side, on both banks, so the river comes out of the forest and cuts through it. Pure: no three.js, seeded, fixed.
import { heightAt } from './height.js';
import { nearestOnRiver, acrossRiver, riverPoint, RIVER, RIVER_HALF_WIDTH } from './river.js';
import { reachable } from './layout.js';
import { mulberry32 } from './random.js';

export const FOREST_COUNT = { standard: 800, high: 1800 };
export const NEAR_SIDE_FROM = 50; // on the lantern's side the forest starts this far from the lantern
const APART = 2.1; // metres between two trunks
const CELL = APART;

// [{ x, z, y, kind: 'cedar' | 'broadleaf', k: size, turn }]
export function forestSpots(count = FOREST_COUNT.standard, seed = 61) {
  const rnd = mulberry32(seed), keep = reachable(), out = [];
  const grid = new Map(); // a coarse grid so the spacing check stays fast
  const key = (x, z) => `${Math.floor(x / CELL)},${Math.floor(z / CELL)}`;
  const near = (x, z) => {
    const cx = Math.floor(x / CELL), cz = Math.floor(z / CELL);
    for (let i = -1; i <= 1; i++) for (let j = -1; j <= 1; j++) {
      for (const o of grid.get(`${cx + i},${cz + j}`) || []) if (Math.hypot(x - o.x, z - o.z) < APART) return true;
    }
    return false;
  };
  for (let t = 0; t < count * 40 && out.length < count; t++) {
    // a point beside the river: somewhere along it, then out to one side
    const u = rnd() * (RIVER.length - 1), c = riverPoint(u), a = riverPoint(Math.max(0, u - 0.05)), b = riverPoint(Math.min(RIVER.length - 1, u + 0.05));
    const l = Math.hypot(b.x - a.x, b.z - a.z) || 1, off = (rnd() < 0.5 ? -1 : 1) * (RIVER_HALF_WIDTH + 1.8 + rnd() * 28);
    const x = c.x - ((b.z - a.z) / l) * off, z = c.z + ((b.x - a.x) / l) * off;
    const r = Math.hypot(x, z);
    if (r > 100) continue;
    const dr = nearestOnRiver({ x, z }).distance;
    if (dr < RIVER_HALF_WIDTH + 1.8 || dr > 30) continue; // a band along the far bank; the hills above stay open
    const across = acrossRiver({ x, z });
    if (!across && (r < NEAR_SIDE_FROM || dr > 16)) continue;
    // thicker near the water, thinning up the slopes
    if (rnd() > 1.05 - dr / 85) continue;
    if (keep.some((k) => Math.hypot(x - k.x, z - k.z) < k.r + 1.6)) continue;
    const y = heightAt(x, z);
    if (y > 16 + 6 * rnd()) continue; // the lower slopes: the hills above stay open and Mount Kenya shows over them
    if (near(x, z)) continue;
    const kind = rnd() < 0.55 ? 'cedar' : 'broadleaf';
    const o = { x, z, y, kind, k: 0.7 + rnd() * 0.55, turn: rnd() * Math.PI * 2, tone: rnd() };
    out.push(o);
    const kk = key(x, z);
    if (!grid.has(kk)) grid.set(kk, []);
    grid.get(kk).push(o);
  }
  return out;
}
