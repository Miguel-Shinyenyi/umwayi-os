// Where the eleven stations stand: a fixed table (a seeded layout), and the position function.
// The order of the distances is the order of how closely each works with the shepherd. Not a circle, no even angles.
// stationPositions(needs) takes only numbers; UI.3 feeds it numbers made from a snapshot.
import { heightAt } from './height.js';
import { SAMPLES, nearestOnRiver, riverPoint, RIVER } from './river.js';
import { IDS } from '../stations/meta.js';

export { RIVER, riverPoint, nearestOnRiver };
export const DEFAULT_NEED = 0.4;
export const SHEPHERD_SPACE = 2.0; // round the lantern
export const GAP = 0.8; // kept between two footprints

// d0: the distance at the default need; bearing: degrees from the viewer's direction (+z) towards +x;
// footprint: metres; maxSlope: the steepest ground its feature may stand on; side: for the river, -1 left, +1 right
const ROWS = {
  memory:     { d0: 15.4, bearing: -8,   footprint: 2.8, maxSlope: 0.4 },
  rules:      { d0: 9.6,  bearing: -42,  footprint: 3.9, maxSlope: 0.3 },
  queue:      { d0: 10.5, bearing: 78,   footprint: 3.7, maxSlope: 0.3 },
  archive:    { d0: 48.0, bearing: 190,  footprint: 4.2, maxSlope: 0.9 }, // across the river, a rock face at the edge of the forest
  logbook:    { d0: 12.6, bearing: -120, footprint: 2.4, maxSlope: 0.3 },
  automation: { d0: 34.0, river: true, side: -1, footprint: 3.6, maxSlope: 0.9 }, // far up the river
  helpers:    { d0: 4.8,  bearing: 24,   footprint: 2.6, maxSlope: 0.3 },
  workflows:  { d0: 15.5, bearing: -88,  footprint: 3.6, maxSlope: 0.5 },
  adapters:   { d0: 31.0, river: true, side: 1, footprint: 3.6, maxSlope: 0.9 }, // far down the river
  killswitch: { d0: 9.0,  bearing: 140,  footprint: 2.4, maxSlope: 0.3 },
  budget:     { d0: 16.0, bearing: 52,   footprint: 2.3, maxSlope: 0.4 },
};
export const TABLE = IDS.map((id) => ({ id, ...ROWS[id] })); // the order of the list view
const PRIORITY = [...TABLE].sort((a, b) => a.d0 - b.d0); // the closest to the shepherd is placed first

const NEAREST = nearestOnRiver();
const ok = (v) => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 1;
const needOf = (needs, id) => (needs && typeof needs === 'object' && ok(needs[id]) ? needs[id] : DEFAULT_NEED);
// d = d0 * (1.2 - 0.5 * need): 0.4 gives d0, 1 gives 0.7 d0, 0 gives 1.2 d0
const distanceFor = (row, need) => row.d0 * (1.2 - 0.5 * need);

// the river samples on one side of the nearest point, by distance from the lantern
const SIDE = { '-1': SAMPLES.filter((s) => s.u <= NEAREST.u).reverse(), '1': SAMPLES.filter((s) => s.u >= NEAREST.u) };

function onRiver(row, d, placed) {
  const list = SIDE[String(row.side)];
  let i = list.findIndex((s) => Math.hypot(s.x, s.z) >= Math.max(d, SHEPHERD_SPACE + row.footprint));
  if (i < 0) i = list.length - 1;
  for (; i < list.length; i++) if (clear(list[i].x, list[i].z, row, placed)) break;
  const s = list[Math.min(i, list.length - 1)];
  return { x: s.x, z: s.z };
}
function clear(x, z, row, placed) {
  if (Math.hypot(x, z) < SHEPHERD_SPACE + row.footprint) return false;
  return placed.every((p) => Math.hypot(x - p.x, z - p.z) >= p.footprint + row.footprint + GAP);
}
function onRay(row, d, placed) {
  const b = (row.bearing * Math.PI) / 180;
  const at = (dd) => ({ x: Math.sin(b) * dd, z: Math.cos(b) * dd });
  const start = Math.max(d, SHEPHERD_SPACE + row.footprint);
  let p = at(start);
  if (clear(p.x, p.z, row, placed)) return p;
  // blocked: slide outward on a fixed grid of tenths of a metre, so the same needs always give the same place
  for (let dd = Math.ceil(start * 10) / 10; dd < 400; dd += 0.1) {
    p = at(dd);
    if (clear(p.x, p.z, row, placed)) return p;
  }
  return p;
}

// needs: { id: 0..1 }. A missing or bad need is DEFAULT_NEED. Returns { id: { x, z, y } }.
// The closest stations are placed first; a later one that would overlap slides outward along its own ray (or along the river).
export function stationPositions(needs) {
  const placed = [];
  const out = {};
  for (const row of PRIORITY) {
    const d = distanceFor(row, needOf(needs, row.id));
    const p = row.river ? onRiver(row, d, placed) : onRay(row, d, placed);
    placed.push({ ...p, footprint: row.footprint });
    out[row.id] = { x: p.x, z: p.z, y: heightAt(p.x, p.z) };
  }
  return out;
}

// Every place a station can stand (a sweep over its needs), as circles. Plants and rocks keep clear of these.
export function reachable() {
  const out = [];
  for (const row of TABLE) {
    for (const need of [0, 0.2, 0.4, 0.6, 0.8, 1]) {
      const p = stationPositions({ [row.id]: need })[row.id];
      out.push({ x: p.x, z: p.z, r: row.footprint + 0.8 });
    }
  }
  return out;
}
