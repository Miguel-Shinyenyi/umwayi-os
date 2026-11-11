// The camera shots: the overview fits every place a station can stand; a selected station is seen from the lantern side.
import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { overviewShot, stationShot, cameraPosition, KEEP_FROM_SHEPHERD } from '../src/world/shots.js';
import { reachable, stationPositions } from '../src/world/layout.js';
import { facingAt } from '../src/engine/placement.js';
import { Rig } from '../src/engine/rig.js';
import { TABLE } from '../src/world/layout.js';

const project = (shot, w, h, x, y, z) => {
  const rig = new Rig(shot), cam = new THREE.PerspectiveCamera();
  rig.apply(cam, w, h);
  const v = new THREE.Vector3(x, y, z).project(cam);
  return { x: ((v.x + 1) / 2) * w, y: ((1 - v.y) / 2) * h, ndc: v };
};
const fakeStation = (row, p) => { const st = { id: row.id, river: !!row.river, footprint: row.footprint, pos: { ...p } }; st.facing = facingAt(st, p.x, p.z); return st; };

test('the overview shows every place a station can stand on a wide screen, and every default place on a phone, with the sky above', () => {
  const defaults = stationPositions({});
  for (const [w, h] of [[1440, 900], [1440, 844], [1024, 768], [390, 844]]) {
    const shot = overviewShot(w / h);
    const spots = w < 600 ? TABLE.map((r) => ({ x: defaults[r.id].x, z: defaults[r.id].z, r: r.footprint })) : reachable();
    for (const s of spots) {
      for (const [dx, dz] of [[s.r, 0], [-s.r, 0], [0, s.r], [0, -s.r]]) {
        const p = project(shot, w, h, s.x + dx, 0, s.z + dz);
        assert.ok(Math.abs(p.ndc.x) <= 0.97 && p.ndc.y >= -0.9, `${w}x${h} (${s.x.toFixed(1)}, ${s.z.toFixed(1)})`);
        assert.ok(p.ndc.y <= 0.52, `${w}x${h} leaves the top for the sky`);
      }
    }
  }
});

test('a selected station is seen from its lantern side with the station in the left third (the top third on a phone)', () => {
  const pos = stationPositions({});
  const all = TABLE.map((row) => fakeStation(row, pos[row.id]));
  for (const [w, h] of [[1440, 900], [390, 844]]) {
    for (const row of TABLE) {
      const st = all.find((x) => x.id === row.id);
      const p = project(stationShot(st, w / h, all), w, h, st.pos.x, (st.river ? -0.4 : st.pos.y) + 1.2, st.pos.z);
      if (w > 800) assert.ok(p.x > w * 0.22 && p.x < w * 0.45, `${row.id} x ${p.x.toFixed(0)}`);
      else assert.ok(p.y > h * 0.12 && p.y < h * 0.42, `${row.id} y ${p.y.toFixed(0)}`);
      assert.ok(Math.abs(p.ndc.x) < 1 && Math.abs(p.ndc.y) < 1);
    }
  }
});

test('a free station faces the lantern; a river station lies along the river with its bank side towards the lantern', () => {
  const pos = stationPositions({});
  for (const row of TABLE) {
    const st = fakeStation(row, pos[row.id]);
    const toLantern = { x: -st.pos.x, z: -st.pos.z };
    const dot = st.facing.x * toLantern.x + st.facing.z * toLantern.z;
    assert.ok(dot > 0, `${row.id} faces away from the lantern`);
    assert.ok(Math.abs(Math.hypot(st.facing.x, st.facing.z) - 1) < 1e-9);
    if (!row.river) assert.ok(dot / Math.hypot(toLantern.x, toLantern.z) > 0.999, `${row.id} does not face the lantern`);
  }
});

import { trailOpacity, liftIntensity } from '../src/world/trails.js';
test('trails of light are shown for the feature in focus only, and Calm mode hides them', () => {
  assert.equal(trailOpacity(0, 0), 0, 'no focus, no trails');
  assert.ok(trailOpacity(1, 0) > 0.5 && trailOpacity(1, 0) < 1, 'soft, not bright');
  assert.equal(trailOpacity(1, 1), 0, 'Calm mode hides them');
  assert.ok(trailOpacity(1, 0.5) < trailOpacity(1, 0));
  assert.equal(liftIntensity(0, 0), 0);
  assert.ok(liftIntensity(1, 1) < liftIntensity(1, 0) && liftIntensity(1, 1) > 0, 'Calm lowers the lift, it does not remove it');
});

test('the camera of a selected station is never in the shepherd or in another feature, at the defaults and when stations are near', () => {
  const rnd = (await_seed => { let a = await_seed; return () => (a = (a * 1664525 + 1013904223) % 4294967296) / 4294967296; })(9);
  for (let n = 0; n < 60; n++) {
    const needs = {};
    for (const row of TABLE) needs[row.id] = n === 0 ? 0.4 : n === 1 ? 1 : rnd();
    const pos = stationPositions(needs);
    const all = TABLE.map((row) => fakeStation(row, pos[row.id]));
    for (const st of all) for (const aspect of [1.6, 0.46]) {
      const c = cameraPosition(st, aspect, all);
      assert.ok(Math.hypot(c.x, c.z) >= 4.5 - 1e-6, `${st.id} camera ${Math.hypot(c.x, c.z).toFixed(1)} m from the shepherd (set ${n})`); // the number from the design, not the constant under test
      for (const o of all) if (o.id !== st.id) assert.ok(Math.hypot(c.x - o.pos.x, c.z - o.pos.z) >= o.footprint + 1.2 - 1e-6, `${st.id} camera inside ${o.id} (set ${n})`);
    }
  }
});

test('the distance the camera keeps from the shepherd is the one in the design', () => assert.equal(KEEP_FROM_SHEPHERD, 4.5));
