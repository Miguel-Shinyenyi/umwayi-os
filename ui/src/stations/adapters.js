import * as THREE from 'three';
// Adapters: three kinds of fence (rail, dry stone, wire) meet at one latch post. A pulse runs from each into the latch.
import { TOKENS } from '../world/palette.js';

export const poses = [
  { a: 0, b: 0, c: 0 },
  { a: 1, b: 0, c: 0 },
  { a: 1, b: 1, c: 0 },
  { a: 1, b: 1, c: 1 },
];

export function build(kit) {
  const { M } = kit;
  const g = new THREE.Group();
  const latch = new THREE.Vector3(0.1, 0, -0.35);
  const ends = [new THREE.Vector3(-1.95, 0, 0.35), new THREE.Vector3(0.1, 0, 1.75), new THREE.Vector3(2.0, 0, 0.45)];
  const post = kit.post(1.35, 0.09, M.woodDark, latch.x, latch.z);
  g.add(post);
  const latchGlow = kit.glow(TOKENS.amber, 2.2, 0);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.15, 0.025, 8, 24), latchGlow);
  ring.position.set(latch.x, 1.0, latch.z + 0.1);
  g.add(ring);
  const along = (end, i, n) => new THREE.Vector3().lerpVectors(latch, end, 0.18 + (0.82 * i) / (n - 1));
  // rail fence
  const rail = new THREE.Group();
  const rp = Array.from({ length: 5 }, (_, i) => along(ends[0], i, 5));
  rp.forEach((p) => rail.add(kit.post(0.7, 0.04, M.wood, p.x, p.z)));
  for (let i = 0; i < 4; i++) for (const y of [0.3, 0.58]) rail.add(kit.beam(rp[i].clone().setY(y), rp[i + 1].clone().setY(y), 0.035, M.wood));
  g.add(rail);
  // dry stone wall
  const wall = new THREE.Group();
  for (let i = 0; i < 12; i++) {
    const p = along(ends[1], i, 12);
    wall.add(kit.rock(0.19, i % 2 ? M.stone : M.stoneDark, p.x + (i % 2) * 0.09, 0.12, p.z, i + 1));
    if (i % 3 !== 2) wall.add(kit.rock(0.16, M.stone, p.x - 0.05, 0.3, p.z + 0.02, i + 7));
  }
  g.add(wall);
  // wire fence
  const wire = new THREE.Group();
  const wp = Array.from({ length: 5 }, (_, i) => along(ends[2], i, 5));
  wp.forEach((p) => wire.add(kit.post(0.75, 0.025, M.metal, p.x, p.z)));
  for (let i = 0; i < 4; i++) for (const y of [0.22, 0.4, 0.58]) wire.add(kit.beam(wp[i].clone().setY(y), wp[i + 1].clone().setY(y), 0.008, M.metal));
  g.add(wire);
  // pulses
  const pulseMat = kit.glow(TOKENS.amber, 3);
  const pulses = ends.map(() => {
    const s = kit.ball(0.09, pulseMat, 0, 0, 0, 12, 8);
    s.castShadow = false;
    g.add(s);
    return s;
  });
  const from = [along(ends[0], 4, 5).setY(0.6), along(ends[1], 11, 12).setY(0.5), along(ends[2], 4, 5).setY(0.6)];
  const to = new THREE.Vector3(latch.x, 1.0, latch.z + 0.1);
  return {
    group: g,
    apply(p) {
      [p.a, p.b, p.c].forEach((v, i) => {
        const s = Math.max(0.0001, Math.sin(Math.PI * v) * 1.0);
        pulses[i].position.lerpVectors(from[i], to, v);
        pulses[i].scale.setScalar(s);
        pulses[i].visible = v > 0.001 && v < 0.999;
      });
      kit.level(latchGlow, Math.max(p.a, p.b, p.c) * 0.5 + (p.a + p.b + p.c) / 6);
    },
    setCounts() {},
  };
}
