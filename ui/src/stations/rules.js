import * as THREE from 'three';
// Rules: a gate with a lantern and a sheep at it. Yes opens it, No shuts it, Ask me first leaves it half open.
// A row of small lamps shows how many rules give each answer. Unknown is drawn as Ask me first.
import { TOKENS } from '../world/palette.js';

export const poses = [
  { gate: 1, lamp: 0, z: -1.45, yaw: Math.PI },
  { gate: 0, lamp: 1, z: 1.9, yaw: 0 },
  { gate: 0.45, lamp: 2, z: 0.95, yaw: Math.PI },
];

const answer = [TOKENS.mint, TOKENS.red, TOKENS.amber];

export function build(kit) {
  const { M } = kit;
  const g = new THREE.Group();
  const gate = new THREE.Group();
  gate.rotation.y = 0.45;
  g.add(gate);
  for (const x of [-0.85, 0.85]) {
    gate.add(kit.post(1.25, 0.075, M.woodDark, x, 0));
    gate.add(kit.ball(0.09, M.stone, x, 1.28, 0, 10, 8));
  }
  const leaf = new THREE.Group();
  leaf.position.set(-0.85, 0, 0);
  for (const y of [0.25, 0.62, 0.98]) leaf.add(kit.box(1.7, 0.07, 0.05, M.wood, 0.85, y, 0));
  for (const x of [0.05, 0.85, 1.65]) leaf.add(kit.box(0.07, 0.95, 0.05, M.wood, x, 0.62, 0));
  leaf.add(kit.beam(new THREE.Vector3(0.05, 0.25, 0), new THREE.Vector3(1.65, 0.98, 0), 0.045, M.wood));
  gate.add(leaf);
  const lantern = kit.lantern(1.5, 2.4);
  lantern.group.position.set(1.3, 0, 0.2);
  gate.add(lantern.group);
  const sheep = kit.sheep(1);
  gate.add(sheep.group);
  sheep.head.rotation.x = 0.05;

  // the row of lamps, one colour per answer
  const beadMats = answer.map((c) => kit.glow(c, 0.85));
  const lamps = new THREE.Group();
  lamps.position.set(0, 0, 1.95);
  g.add(lamps);
  const beads = [];
  for (let i = 0; i < 12; i++) {
    const x = (i - 5.5) * 0.2;
    lamps.add(kit.post(0.2, 0.018, M.metal, x, 0));
    const b = kit.ball(0.05, beadMats[2], x, 0.23, 0, 10, 8);
    lamps.add(b);
    beads.push(b);
  }
  const col = new THREE.Color();
  return {
    group: g,
    apply(p) {
      leaf.rotation.y = p.gate * 1.3;
      sheep.group.position.set(0.0, 0, p.z);
      sheep.group.rotation.y = p.yaw;
      const i = Math.min(2, Math.floor(p.lamp));
      const f = p.lamp - i;
      col.set(answer[i]).lerp(new THREE.Color(answer[Math.min(2, i + 1)]), f);
      lantern.lamp.emissive.copy(col);
      lantern.lamp.color.copy(col).multiplyScalar(0.3);
    },
    // counts: { yes, no, ask } or null (unknown is drawn as Ask me first)
    setCounts(c) {
      const k = c && c.rules ? c.rules : null;
      const n = k ? [k.yes, k.no, k.ask] : [0, 0, 12];
      const total = Math.max(1, n[0] + n[1] + n[2]);
      const shown = n.map((v) => (v > 0 ? Math.max(1, Math.round((v / total) * 12)) : 0));
      while (shown[0] + shown[1] + shown[2] > 12) shown[shown.indexOf(Math.max(...shown))]--;
      let i = 0;
      shown.forEach((count, which) => {
        for (let j = 0; j < count; j++, i++) { beads[i].material = beadMats[which]; beads[i].visible = true; }
      });
      for (; i < 12; i++) beads[i].visible = false;
    },
  };
}
