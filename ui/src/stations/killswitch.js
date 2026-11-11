// Kill switch: a lone gate in an open field, and a latch post with a red lamp. Open, the sheep pass. Shut, the lamp is red
// and the next sheep halts. Unknown is drawn as on, because if umwayi cannot tell, it stops.
import * as THREE from 'three';
import { TOKENS } from '../world/palette.js';
import { sceneNumbers } from '../data/snapshot.js';

export const poses = [
  { shut: 0, red: 0, a: 2.0, b: 4.6 },
  { shut: 0, red: 0, a: -2.2, b: 4.6 },
  { shut: 1, red: 1, a: -2.2, b: 1.25 },
];

export function build(kit) {
  const { M } = kit;
  const g = new THREE.Group();
  for (const x of [-0.8, 0.8]) {
    g.add(kit.post(1.35, 0.09, M.woodDark, x, 0));
    g.add(kit.rock(0.16, M.stone, x, 1.4, 0, 8, 1, 0.8, 1));
  }
  const leaf = kit.gate(1.55, 1.1);
  leaf.position.set(-0.75, 0, 0);
  g.add(leaf);
  // the latch post stands a little beside the gate, with the red lamp on top
  const latch = new THREE.Group();
  latch.position.set(1.25, 0, 0.1);
  latch.add(kit.post(1.9, 0.07, M.woodDark));
  latch.add(kit.box(0.34, 0.05, 0.05, M.iron, -0.17, 1.15, 0));
  const lamp = kit.glow(TOKENS.red, 3.0, 0);
  latch.add(kit.mesh(new THREE.CylinderGeometry(0.1, 0.08, 0.2, 10), lamp, 0, 2.02, 0));
  latch.add(kit.mesh(new THREE.ConeGeometry(0.14, 0.1, 10), M.iron, 0, 2.17, 0));
  g.add(latch);
  const a = kit.sheep(0.9), b = kit.sheep(0.9);
  g.add(a.group, b.group);
  const unknownMark = kit.unknownMark(-1.9, 0.9);
  g.add(unknownMark);
  let on = true;
  return {
    group: g,
    apply(p) {
      leaf.rotation.y = (1 - p.shut) * 1.45;
      kit.level(lamp, p.red);
      a.group.position.set(0, 0, p.a); a.group.rotation.y = Math.PI;
      b.group.position.set(0.05, 0, p.b); b.group.rotation.y = Math.PI;
    },
    // the mapping table (data/snapshot.js): on and unknown are drawn as on (shut and lit), only off is open; unknown also shows the mark
    setCounts(c) {
      const n = sceneNumbers(c).killswitch;
      on = n.shut;
      unknownMark.visible = n.unknown;
    },
    rest: () => (on ? { shut: 1, red: 1, a: -2.2, b: 1.25 } : { shut: 0, red: 0, a: -2.2, b: 4.6 }),
  };
}
