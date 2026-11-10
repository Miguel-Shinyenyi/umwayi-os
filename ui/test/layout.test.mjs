// UI.1.3 and UI.1.4: the ring and the labels. A real three.js camera projects the labels; none may overlap.
import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { ringPositions, ringRadius, PLATFORM_R, overviewShot, stationShot, declutter } from '../src/engine/layout.js';
import { Rig } from '../src/engine/rig.js';
import { IDS, STATIONS } from '../src/stations/meta.js';

function labelRects(n, w, h, names) {
  const pos = ringPositions(n);
  const rig = new Rig(overviewShot(w / h, n));
  const cam = new THREE.PerspectiveCamera();
  rig.apply(cam, w, h);
  const small = w < 600;
  const rects = pos.map((p, i) => {
    const v = new THREE.Vector3(p.x, 3.2, p.z).project(cam);
    const label = names[i] ?? 'Station';
    return { x: ((v.x + 1) / 2) * w, y: ((1 - v.y) / 2) * h - 14, w: (small ? 7 : 8.5) * label.length + (small ? 20 : 28), h: small ? 24 : 28 };
  });
  return { rects, rig, cam };
}
const overlap = (a, b) => Math.abs(a.x - b.x) < (a.w + b.w) / 2 && Math.abs(a.y - b.y) < (a.h + b.h) / 2;

test('stations stand on a ring with room between neighbouring platforms, for 11 and for 14', () => {
  for (const n of [11, 14]) {
    const p = ringPositions(n);
    for (let i = 0; i < n; i++) {
      const q = p[(i + 1) % n];
      assert.ok(Math.hypot(p[i].x - q.x, p[i].z - q.z) >= 2 * PLATFORM_R + 1, `n ${n}`);
      assert.ok(Math.abs(Math.hypot(p[i].x, p[i].z) - ringRadius(n)) < 1e-9);
    }
  }
});

test('the labels of 11 stations and of 14 fake stations do not overlap, at 1440 by 844 and 390 by 844', () => {
  for (const [w, h] of [[1440, 844], [1440, 900], [390, 844]]) {
    for (const n of [11, 14]) {
      const names = n === 11 ? STATIONS.map((s) => s.name) : Array.from({ length: n }, (_, i) => `Fake station ${i}`);
      const { rects } = labelRects(n, w, h, names);
      const bounds = { left: 8, right: w - 8, top: 64, bottom: h - 70 };
      const placed = declutter(rects, bounds);
      for (let i = 0; i < placed.length; i++) {
        const r = placed[i];
        assert.ok(r.x - r.w / 2 >= bounds.left - 0.5 && r.x + r.w / 2 <= bounds.right + 0.5, `${w}x${h} n${n} #${i} inside x`);
        assert.ok(r.y - r.h / 2 >= bounds.top - 0.5 && r.y + r.h / 2 <= bounds.bottom + 0.5, `${w}x${h} n${n} #${i} inside y: ${r.y}`);
        for (let j = i + 1; j < placed.length; j++) assert.ok(!overlap(r, placed[j]), `${w}x${h} n${n}: ${i} and ${j} overlap`);
      }
    }
  }
});

test('the whole ring is in view in the overview, wide and narrow', () => {
  for (const [w, h] of [[1440, 844], [390, 844], [1024, 768]]) {
    const { cam } = labelRects(11, w, h, IDS);
    for (const p of ringPositions(11)) {
      for (const [dx, dz] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
        const v = new THREE.Vector3(p.x + dx * PLATFORM_R, 0, p.z + dz * PLATFORM_R).project(cam);
        assert.ok(Math.abs(v.x) <= 1 && v.y >= -1 && v.y <= 1, `${w}x${h} (${p.x.toFixed(1)}, ${p.z.toFixed(1)})`);
      }
    }
  }
});

test('a selected station is seen from in front, in the left third (or the top third on a phone)', () => {
  for (const [w, h] of [[1440, 844], [390, 844]]) {
    const pos = ringPositions(11);
    for (const p of pos) {
      const rig = new Rig(stationShot(p, w / h));
      const cam = new THREE.PerspectiveCamera();
      rig.apply(cam, w, h);
      const v = new THREE.Vector3(p.x, 1.2, p.z).project(cam);
      const sx = ((v.x + 1) / 2) * w, sy = ((1 - v.y) / 2) * h;
      if (w > 800) assert.ok(sx > w * 0.25 && sx < w * 0.42, `x ${sx}`);
      else assert.ok(sy > h * 0.18 && sy < h * 0.4, `y ${sy}`);
    }
  }
});

test('the rig blends between shots, takes the short way round and never leaves the shots', () => {
  const rig = new Rig(overviewShot(1.7));
  const a = { ...rig.s };
  const b = stationShot(ringPositions(11)[3], 1.7);
  rig.blend(a, b, 0.5);
  assert.ok(rig.s.dist < a.dist && rig.s.dist > b.dist);
  rig.blend(a, b, 1);
  assert.ok(Math.abs(Math.sin(rig.s.yaw) - Math.sin(b.yaw)) < 1e-9 && Math.abs(Math.cos(rig.s.yaw) - Math.cos(b.yaw)) < 1e-9);
  rig.blend({ ...a, yaw: 3.0 }, { ...b, yaw: -3.0 }, 0.5);
  assert.ok(Math.abs(rig.s.yaw) > 3.0 || Math.abs(rig.s.yaw - Math.PI) < 0.2, 'crosses pi, not zero');
});
