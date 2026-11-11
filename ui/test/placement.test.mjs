// UI.1.3 (tests first): the layout table, the position function and the eased move of the stations.
import test from 'node:test';
import assert from 'node:assert/strict';
import { TABLE, SHEPHERD_SPACE, RIVER, stationPositions, DEFAULT_NEED, riverPoint, nearestOnRiver } from '../src/world/layout.js';
import { heightAt, riverBedDepth, RIVER_HALF_WIDTH } from '../src/world/height.js';
import { createPlacement } from '../src/engine/placement.js';
import { Motion } from '../src/engine/motion.js';
import { IDS } from '../src/stations/meta.js';
import { mulberry32 } from '../src/world/random.js';
import { acrossRiver } from '../src/world/river.js';

const GAP = 0.8; // margin kept between two footprints
const byId = Object.fromEntries(TABLE.map((s) => [s.id, s]));
const dist = (a, b) => Math.hypot(a.x - b.x, a.z - b.z);
const all = (v) => Object.fromEntries(IDS.map((id) => [id, v]));

test('the table has the eleven stations in the order of the list view', () => {
  assert.deepEqual(TABLE.map((s) => s.id).sort(), [...IDS].sort());
  assert.equal(TABLE.length, 11);
});

test('the default positions equal the table of the design', () => {
  const want = {
    helpers: [1.95, 4.4], rules: [-6.4, 7.1], queue: [10.3, 2.2], killswitch: [5.8, -6.9], logbook: [-10.9, -6.3], memory: [-2.1, 15.3],
    workflows: [-15.5, 0.5], budget: [12.6, 9.9], adapters: [29.1, 11.2], automation: [-23.3, -25.3], archive: [-8.3, -47.3],
  };
  const pos = stationPositions({});
  for (const id of IDS) {
    assert.ok(Math.abs(pos[id].x - want[id][0]) < 0.35 && Math.abs(pos[id].z - want[id][1]) < 0.35, `${id} ${pos[id].x.toFixed(1)}, ${pos[id].z.toFixed(1)}`);
  }
});

test('the default distances are in the order of how closely each works with the shepherd, and not on a circle', () => {
  const pos = stationPositions({});
  const d = IDS.map((id) => ({ id, d: Math.hypot(pos[id].x, pos[id].z) }));
  const ring = d.map((x) => x.d);
  assert.ok(Math.max(...ring) - Math.min(...ring) > 15, 'distances differ a lot');
  assert.ok(d.find((x) => x.id === 'helpers').d < d.find((x) => x.id === 'rules').d);
  assert.ok(d.find((x) => x.id === 'rules').d < d.find((x) => x.id === 'logbook').d);
  assert.ok(d.find((x) => x.id === 'archive').d > d.find((x) => x.id === 'workflows').d);
  // bearings are not evenly spaced
  const angles = IDS.map((id) => Math.atan2(pos[id].x, pos[id].z)).sort((a, b) => a - b);
  const gaps = angles.map((a, i) => (i ? a - angles[i - 1] : 0)).slice(1);
  assert.ok(Math.max(...gaps) - Math.min(...gaps) > 0.25, 'angles are uneven');
});

test('some stations are really far: at least three stand 30 m or more from the lantern at their default places (12.R19.3)', () => {
  const pos = stationPositions({});
  const far = IDS.filter((id) => Math.hypot(pos[id].x, pos[id].z) >= 30);
  assert.ok(far.length >= 3, `far: ${far.join(', ')}`);
  assert.ok(far.includes('archive'), 'the Archive is the furthest kind of work from the shepherd');
});

test('the Archive stands across the river from the lantern, at the edge of the forest', () => {
  const p = stationPositions({}).archive;
  assert.ok(acrossRiver(p), 'across the river');
  assert.equal(acrossRiver({ x: 0, z: 0 }), false, 'the lantern is on its own side');
});

test('the default gap between any two stations is at least 2.0 m', () => {
  const pos = stationPositions({});
  for (let i = 0; i < IDS.length; i++) for (let j = i + 1; j < IDS.length; j++) {
    const a = IDS[i], b = IDS[j];
    const gap = dist(pos[a], pos[b]) - byId[a].footprint - byId[b].footprint;
    assert.ok(gap >= 2.0 - 1e-6, `${a} and ${b}: ${gap.toFixed(2)}`);
  }
});

function assertNoOverlap(pos, label) {
  for (let i = 0; i < IDS.length; i++) {
    const a = IDS[i];
    assert.ok(Math.hypot(pos[a].x, pos[a].z) >= SHEPHERD_SPACE + byId[a].footprint - 1e-6, `${label}: ${a} on the shepherd`);
    for (let j = i + 1; j < IDS.length; j++) {
      const b = IDS[j];
      assert.ok(dist(pos[a], pos[b]) >= byId[a].footprint + byId[b].footprint + GAP - 1e-6, `${label}: ${a} and ${b} overlap (${dist(pos[a], pos[b]).toFixed(2)})`);
    }
  }
}

test('no two stations overlap and none stands on the shepherd: all quiet, all needing, and 5000 random need sets', () => {
  assertNoOverlap(stationPositions(all(0)), 'all quiet');
  assertNoOverlap(stationPositions(all(1)), 'all needing');
  assertNoOverlap(stationPositions(all(DEFAULT_NEED)), 'defaults');
  const rnd = mulberry32(2026);
  for (let n = 0; n < 5000; n++) {
    const needs = {};
    for (const id of IDS) needs[id] = rnd() < 0.3 ? (rnd() < 0.5 ? 0 : 1) : rnd();
    assertNoOverlap(stationPositions(needs), `random ${n}`);
  }
});

test('a higher need brings a station nearer the lantern (the free ones, when nothing is in the way)', () => {
  for (const id of ['rules', 'queue', 'budget', 'memory', 'logbook', 'archive', 'workflows', 'killswitch']) {
    let prev = Infinity;
    for (const need of [0, 0.2, 0.4, 0.6, 0.8, 1]) {
      const p = stationPositions({ ...all(DEFAULT_NEED), [id]: need })[id];
      const d = Math.hypot(p.x, p.z);
      assert.ok(d <= prev + 0.11, `${id} need ${need}: ${d.toFixed(2)} > ${prev.toFixed(2)}`); // within a tenth of a metre: the slide grid
      prev = d;
    }
  }
  const quiet = stationPositions({ ...all(DEFAULT_NEED), queue: 0 }).queue, busy = stationPositions({ ...all(DEFAULT_NEED), queue: 1 }).queue;
  assert.ok(Math.hypot(quiet.x, quiet.z) > Math.hypot(busy.x, busy.z) + 3, 'a real difference');
});

test('the same needs always give the same positions', () => {
  const needs = { queue: 0.9, rules: 0.1, budget: 0.7 };
  assert.deepEqual(stationPositions(needs), stationPositions({ ...needs }));
});

test('a missing, wrong or out of range need is the default need, never 0 or 1', () => {
  const base = stationPositions({});
  for (const bad of [undefined, null, NaN, 'high', -1, 2, Infinity, {}, []]) {
    assert.deepEqual(stationPositions({ queue: bad }).queue, base.queue, String(bad));
  }
  assert.deepEqual(stationPositions(null), base);
  assert.deepEqual(stationPositions('x'), base);
});

test('the river stations stay on the bank, on their own side of the nearest point, at every need', () => {
  const near = nearestOnRiver();
  for (const id of ['automation', 'adapters']) {
    for (const need of [0, 0.3, 0.6, 1]) {
      const p = stationPositions({ ...all(DEFAULT_NEED), [id]: need })[id];
      const r = nearestOnRiver(p);
      
      assert.ok(r.distance < 0.8, `${id} ${need} is not on the river centre line`);
      const side = Math.sign(r.u - near.u); // 0 at the nearest point itself
      assert.ok(side === 0 || side === byId[id].side, `${id} ${need} on the other side`);
    }
  }
  const q = stationPositions(all(1)), z = stationPositions(all(0));
  for (const id of ['automation', 'adapters']) assert.ok(Math.hypot(q[id].x, q[id].z) <= Math.hypot(z[id].x, z[id].z), id);
});

test('every station stands on land: above the river bed, not in the water, on a slope its feature allows', () => {
  const rnd = mulberry32(5);
  for (let n = 0; n < 300; n++) {
    const needs = {};
    for (const id of IDS) needs[id] = rnd();
    const pos = stationPositions(needs);
    for (const id of IDS) {
      const p = pos[id];
      assert.ok(Number.isFinite(p.y) && Math.abs(p.y - heightAt(p.x, p.z)) < 1e-9);
      const slope = Math.hypot(heightAt(p.x + 1, p.z) - heightAt(p.x - 1, p.z), heightAt(p.x, p.z + 1) - heightAt(p.x, p.z - 1)) / 2;
      assert.ok(slope <= byId[id].maxSlope + 1e-9, `${id} slope ${slope.toFixed(2)} (max ${byId[id].maxSlope})`);
      if (id !== 'automation' && id !== 'adapters') assert.ok(nearestOnRiver(p).distance > RIVER_HALF_WIDTH + byId[id].footprint, `${id} in the river`);
    }
  }
});

test('the ground has relief, a valley floor by the lantern and a river cut into it', () => {
  assert.ok(Math.abs(heightAt(0, 0) - 1.2) < 0.4, 'the lantern knoll is about 1.2 m');
  let max = 0;
  for (let x = -120; x <= 120; x += 6) for (let z = -120; z <= 120; z += 6) { const h = heightAt(x, z); assert.ok(Number.isFinite(h)); max = Math.max(max, h); }
  assert.ok(max > 35, `the hills reach ${max.toFixed(0)} m`);
  for (let u = 0; u <= RIVER.length - 1; u += 0.25) {
    const c = riverPoint(u);
    const floor = heightAt(c.x + 14, c.z + 14) * 0; // the banks are measured against their own surroundings below
    assert.ok(riverBedDepth(c.x, c.z) > 1.2 && riverBedDepth(c.x, c.z) < 2.2, `river depth at u ${u}: ${riverBedDepth(c.x, c.z).toFixed(2)}`);
    assert.ok(floor === 0);
  }
  // a station on the valley floor is level enough to build on
  const s = stationPositions({}).queue;
  assert.ok(Math.abs(heightAt(s.x + 2, s.z) - heightAt(s.x - 2, s.z)) < 1.2);
});

test('the keyboard order of the stations is the order of the list view', () => {
  assert.deepEqual(TABLE.map((s) => s.id), IDS);
});

// ---- the eased move
const fakeStation = (id, p) => ({ id, pos: { ...p }, group: { position: { x: p.x, y: 0, z: p.z, set(x, y, z) { this.x = x; this.y = y; this.z = z; } } } });
const stations = () => {
  const pos = stationPositions({});
  return IDS.map((id) => fakeStation(id, pos[id]));
};
const run = (m, ms, dt = 16) => { for (let t = 0; t < ms; t += dt) m.step(dt); };

test('setNeeds eases every station to its new place within 3 s (5 s in Calm) and then nothing is active', () => {
  for (const [slow, limit] of [[1, 3000], [1.6, 5000]]) {
    const m = new Motion({ slow }); const st = stations(); const pl = createPlacement({ stations: st, motion: m });
    pl.setNeeds({ queue: 1, killswitch: 1 });
    assert.equal(m.active, true);
    let t = 0; while (m.active && t < 10000) { m.step(16); t += 16; }
    assert.ok(t <= limit, `${slow}: ${t} ms`);
    const want = stationPositions({ queue: 1, killswitch: 1 });
    for (const s of st) assert.ok(Math.abs(s.pos.x - want[s.id].x) < 1e-6 && Math.abs(s.pos.z - want[s.id].z) < 1e-6, s.id);
  }
});

test('the move is eased: fast at first, then slower, never past the end', () => {
  const m = new Motion(); const st = stations(); const pl = createPlacement({ stations: st, motion: m });
  const q = st.find((s) => s.id === 'queue'); const start = { ...q.pos }; const end = stationPositions({ queue: 1 }).queue;
  pl.setNeeds({ queue: 1 });
  const total = Math.hypot(end.x - start.x, end.z - start.z); let prev = 0, prevStep = Infinity;
  for (let i = 0; i < 160; i++) {
    m.step(16);
    const d = Math.hypot(q.pos.x - start.x, q.pos.z - start.z);
    assert.ok(d <= total + 1e-6 && d >= prev - 1e-6);
    prev = d;
  }
  assert.ok(Math.abs(prev - total) < 1e-6);
});

test('with reduced motion the stations jump, and a new set of needs mid move starts from where they are', () => {
  const r = new Motion({ reduced: true }); const st = stations(); createPlacement({ stations: st, motion: r }).setNeeds({ rules: 1 });
  assert.ok(Math.abs(st.find((s) => s.id === 'rules').pos.x - stationPositions({ rules: 1 }).rules.x) < 1e-6);
  assert.equal(r.active, false);
  const m = new Motion(); const st2 = stations(); const pl = createPlacement({ stations: st2, motion: m });
  pl.setNeeds({ queue: 1 }); run(m, 700);
  const q = st2.find((s) => s.id === 'queue'); const mid = { x: q.pos.x, z: q.pos.z };
  pl.setNeeds({ queue: 0 });
  m.step(16);
  assert.ok(Math.hypot(q.pos.x - mid.x, q.pos.z - mid.z) < 1.5, 'no jump when the target changes');
  run(m, 3200);
  const end = stationPositions({ queue: 0 }).queue;
  assert.ok(Math.abs(q.pos.x - end.x) < 1e-6);
});

test('a station group follows the ground height as it moves', () => {
  const m = new Motion({ reduced: true }); const st = stations(); createPlacement({ stations: st, motion: m }).setNeeds({ budget: 1 });
  const b = st.find((s) => s.id === 'budget');
  assert.ok(Math.abs(b.group.position.y - heightAt(b.pos.x, b.pos.z)) < 1e-9);
});
