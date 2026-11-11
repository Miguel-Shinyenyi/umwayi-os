// UI.1b.6 (tests first): the forest across the river is dense, stays across the river (or far out where the river comes out
// of it) and never stands where a station can stand.
import test from 'node:test';
import assert from 'node:assert/strict';
import { forestSpots, FOREST_COUNT, NEAR_SIDE_FROM } from '../src/world/forest.js';
import { acrossRiver, nearestOnRiver, RIVER_HALF_WIDTH } from '../src/world/river.js';
import { reachable, stationPositions, TABLE } from '../src/world/layout.js';

const spots = forestSpots();

test('the forest is dense: the Standard count of trees, most of them across the river', () => {
  assert.equal(spots.length, FOREST_COUNT.standard);
  const across = spots.filter((s) => acrossRiver(s)).length;
  assert.ok(across / spots.length > 0.7, `${across} of ${spots.length} across the river`);
  assert.ok(spots.some((s) => s.kind === 'cedar') && spots.some((s) => s.kind === 'broadleaf'));
});

test('every tree is across the river, or on the lantern side only far out, and none stands in the water', () => {
  for (const s of spots) {
    if (!acrossRiver(s)) assert.ok(Math.hypot(s.x, s.z) >= NEAR_SIDE_FROM, `(${s.x.toFixed(1)}, ${s.z.toFixed(1)}) on the lantern side, near`);
    assert.ok(nearestOnRiver(s).distance > RIVER_HALF_WIDTH + 1, 'in the river');
  }
});

test('no tree stands where a station can stand, at the defaults or at any reachable place', () => {
  const keep = reachable();
  for (const s of spots) for (const k of keep) assert.ok(Math.hypot(s.x - k.x, s.z - k.z) >= k.r, `a tree in a station at (${k.x.toFixed(1)}, ${k.z.toFixed(1)})`);
  const pos = stationPositions({});
  for (const row of TABLE) for (const s of spots) assert.ok(Math.hypot(s.x - pos[row.id].x, s.z - pos[row.id].z) >= row.footprint + 1, row.id);
});

test('the forest is the same every time', () => {
  assert.deepEqual(forestSpots().slice(0, 20), spots.slice(0, 20));
});

import * as THREE from 'three';
import { buildRiver, rapidRocks } from '../src/world/water.js';
test('the river surface faces up, so it is drawn from above (it faced down before and only its bed showed)', () => {
  const g = buildRiver().geometry, p = g.attributes.position, ix = g.index.array;
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
  let down = 0;
  for (let i = 0; i < ix.length; i += 3) {
    a.fromBufferAttribute(p, ix[i]); b.fromBufferAttribute(p, ix[i + 1]).sub(a); c.fromBufferAttribute(p, ix[i + 2]).sub(a);
    if (b.cross(c).y <= 0) down++;
  }
  assert.equal(down, 0);
  for (const k of ['along', 'tang']) assert.ok(g.attributes[k], `${k} for the flow`);
});

test('the rocks of the rapids sit in the river and clear of every place a river station can stand', () => {
  const rocks = rapidRocks(), keep = reachable();
  assert.ok(rocks.length >= 12, `${rocks.length} rocks`);
  for (const r of rocks) {
    assert.ok(nearestOnRiver(r).distance < RIVER_HALF_WIDTH, 'in the river');
    for (const k of keep) assert.ok(Math.hypot(r.x - k.x, r.z - k.z) >= k.r + r.r - 1e-9, 'in a station');
  }
});
