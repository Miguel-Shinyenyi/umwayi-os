// AI helpers: a sheepdog beside a small herd. The dog carries the draft to a row of white stones and stops. The draft goes
// on to a flat stone, where you publish it. A helper drafts; it never publishes.
import * as THREE from 'three';
import { lerp } from '../engine/ease.js';

export const poses = [
  { s: 0, d: 0 },
  { s: 1, d: 1 },
  { s: 2, d: 1 },
];

export function build(kit) {
  const { M } = kit;
  const g = new THREE.Group();
  const dog = kit.dog(1);
  dog.rotation.y = Math.PI / 2;
  g.add(dog);
  for (let i = 0; i < 7; i++) g.add(kit.rock(0.16, M.line, 0.05, 0.08, -1.5 + i * 0.5, i + 3, 1.1, 0.5, 1)); // the white stones
  g.add(kit.rock(0.62, M.stone, 1.5, 0.16, 0, 17, 1.2, 0.35, 1)); // the flat stone
  // the herd, grazing at the edge
  [[-1.6, -1.7, 0.4, 0.9], [-0.7, -2.1, 3.5, 0.8], [0.4, -2.0, 2.0, 0.95], [-2.3, -0.9, 1.2, 0.85], [1.2, -1.8, 4.4, 0.9]].forEach(([x, z, yaw, s], i) => {
    const sh = kit.sheep(s);
    sh.group.position.set(x, 0, z);
    sh.group.rotation.y = yaw;
    sh.head.rotation.x = i % 2 ? 0.85 : 0.2;
    g.add(sh.group);
  });
  const scroll = kit.cyl(0.07, 0.07, 0.34, M.parchment, 0, 0, 0, 14);
  scroll.rotation.z = Math.PI / 2;
  const carried = new THREE.Group();
  carried.add(scroll);
  g.add(carried);
  return {
    group: g,
    apply(p) {
      const dx = -1.5 + p.d * 0.88;
      const bob = p.d > 0 && p.d < 1 ? Math.abs(Math.sin(p.d * Math.PI * 8)) * 0.05 : 0;
      dog.position.set(dx, bob, 0.25);
      if (p.s <= 1) carried.position.set(dx + 0.62, 0.6 + bob, 0.25);
      else {
        const u = p.s - 1;
        carried.position.set(lerp(0, 1.5, u), lerp(0.6, 0.36, u) + Math.sin(Math.PI * u) * 0.5, lerp(0.25, 0, u));
      }
    },
    setCounts() {},
  };
}
