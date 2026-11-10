import * as THREE from 'three';
// AI helpers: a sheepdog carries the draft to a white line and stops. The draft goes on to the stool, where you publish it.
import { TOKENS } from '../world/palette.js';
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
  g.add(kit.box(0.07, 0.012, 2.6, M.line, 0.05, 0.015, 0));
  // stool, lantern and staff
  const stool = new THREE.Group();
  stool.position.set(1.45, 0, 0);
  stool.add(kit.cyl(0.3, 0.3, 0.06, M.wood, 0, 0.5, 0, 20));
  for (let i = 0; i < 3; i++) {
    const a = (i / 3) * Math.PI * 2 + 0.5;
    stool.add(kit.beam(new THREE.Vector3(Math.cos(a) * 0.24, 0.5, Math.sin(a) * 0.24), new THREE.Vector3(Math.cos(a) * 0.33, 0, Math.sin(a) * 0.33), 0.05, M.woodDark));
  }
  g.add(stool);
  const lantern = kit.lantern(0.95, 1.8);
  lantern.group.position.set(1.95, 0, -0.55);
  g.add(lantern.group);
  g.add(kit.beam(new THREE.Vector3(1.75, 0.02, 0.5), new THREE.Vector3(1.95, 1.5, 0.28), 0.04, M.woodDark));
  const scroll = new THREE.Group();
  scroll.add(kit.cyl(0.075, 0.075, 0.36, M.parchment, 0, 0, 0, 14));
  scroll.rotation.z = Math.PI / 2;
  const carried = new THREE.Group();
  carried.add(scroll);
  g.add(carried);
  const LINE = 0.05;
  return {
    group: g,
    apply(p) {
      const dx = -1.5 + p.d * 0.88;
      const bob = p.d > 0 && p.d < 1 ? Math.abs(Math.sin(p.d * Math.PI * 8)) * 0.05 : 0;
      dog.position.set(dx, bob, 0.25);
      if (p.s <= 1) carried.position.set(dx + 0.62, 0.62 + bob, 0.25);
      else {
        const u = p.s - 1;
        carried.position.set(lerp(LINE - 0.05, 1.45, u), lerp(0.62, 0.6, u) + Math.sin(Math.PI * u) * 0.55, lerp(0.25, 0, u));
      }
    },
    setCounts() {},
  };
}
