// The river: a centre line through control points, smoothed once (Catmull-Rom). u counts control points, so u = 2.5 is
// halfway between the third and the fourth. Pure, no three.js.
export const RIVER = [
  [-110, -36], [-80, -32], [-52, -30], [-34, -29], [-20, -24], [-8, -19], [4, -16], [14, -12], [22, -4], [27, 8], [36, 18], [52, 24], [80, 36], [110, 44],
].map(([x, z]) => ({ x, z }));
export const RIVER_HALF_WIDTH = 3;
export const RIVER_BANK = 3;
export const RIVER_DEPTH = 1.6;

const STEPS = 24;
const cr = (p0, p1, p2, p3, t) => 0.5 * (2 * p1 + (p2 - p0) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t);
export const SAMPLES = (() => {
  const out = [];
  const n = RIVER.length;
  for (let i = 0; i < n - 1; i++) {
    const p0 = RIVER[Math.max(0, i - 1)], p1 = RIVER[i], p2 = RIVER[i + 1], p3 = RIVER[Math.min(n - 1, i + 2)];
    for (let s = 0; s < STEPS; s++) {
      const t = s / STEPS;
      out.push({ u: i + t, x: cr(p0.x, p1.x, p2.x, p3.x, t), z: cr(p0.z, p1.z, p2.z, p3.z, t) });
    }
  }
  out.push({ u: n - 1, x: RIVER[n - 1].x, z: RIVER[n - 1].z });
  return out;
})();

export function riverPoint(u) {
  const f = Math.min(SAMPLES.length - 1, Math.max(0, u * STEPS));
  const i = Math.min(SAMPLES.length - 2, Math.floor(f)), t = f - i;
  return { x: SAMPLES[i].x + (SAMPLES[i + 1].x - SAMPLES[i].x) * t, z: SAMPLES[i].z + (SAMPLES[i + 1].z - SAMPLES[i].z) * t };
}
// The point of the river nearest to p (default: the lantern at the origin): { u, distance, x, z }.
export function nearestOnRiver(p = { x: 0, z: 0 }) {
  let best = 0, bd = Infinity;
  for (let i = 0; i < SAMPLES.length; i++) {
    const d = (SAMPLES[i].x - p.x) ** 2 + (SAMPLES[i].z - p.z) ** 2;
    if (d < bd) { bd = d; best = i; }
  }
  // refine between the neighbours of the best sample
  let u = SAMPLES[best].u;
  const lo = Math.max(0, best - 1), hi = Math.min(SAMPLES.length - 1, best + 1);
  for (let k = 0; k <= 20; k++) {
    const uu = SAMPLES[lo].u + ((SAMPLES[hi].u - SAMPLES[lo].u) * k) / 20;
    const q = riverPoint(uu);
    const d = (q.x - p.x) ** 2 + (q.z - p.z) ** 2;
    if (d < bd) { bd = d; u = uu; }
  }
  const q = riverPoint(u);
  return { u, distance: Math.sqrt(bd), x: q.x, z: q.z };
}

// Which side of the river a point is on: +1 or -1 (the sign of the turn from the river's direction to the point), 0 on the line.
export function sideOfRiver(p) {
  const n = nearestOnRiver(p);
  const a = riverPoint(Math.max(0, n.u - 0.05)), b = riverPoint(Math.min(RIVER.length - 1, n.u + 0.05));
  const cross = (b.x - a.x) * (p.z - n.z) - (b.z - a.z) * (p.x - n.x);
  return Math.abs(cross) < 1e-9 ? 0 : Math.sign(cross);
}
const LANTERN_SIDE = sideOfRiver({ x: 0, z: 0 });
// true for a point on the far side of the river from the lantern, clear of the water
export const acrossRiver = (p) => nearestOnRiver(p).distance > RIVER_HALF_WIDTH && sideOfRiver(p) === -LANTERN_SIDE;
