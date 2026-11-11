// Rules: a drystone wall along the slope with a gate in it. Yes opens the gate, No shuts it, Ask me first leaves it half open.
// Small lamps on the wall top show how many rules give each answer. Unknown is drawn as Ask me first.
import * as THREE from 'three';
import { TOKENS } from '../world/palette.js';

export const poses = [
  { gate: 1, lamp: 0, z: -1.5, yaw: Math.PI },
  { gate: 0, lamp: 1, z: 2.0, yaw: 0 },
  { gate: 0.45, lamp: 2, z: 1.0, yaw: Math.PI },
];

const answer = [TOKENS.mint, TOKENS.red, TOKENS.amber];

export function build(kit) {
  const { M } = kit;
  const g = new THREE.Group();
  g.add(kit.wall([[-3.8, 0], [-0.95, 0]], 0.95, 0.6, 3));
  g.add(kit.wall([[0.95, 0], [3.8, 0]], 0.95, 0.6, 5));
  for (const x of [-0.85, 0.85]) {
    g.add(kit.post(1.45, 0.085, M.woodDark, x, 0));
    g.add(kit.rock(0.2, M.stone, x, 1.5, 0, 9, 1, 0.8, 1));
  }
  const leaf = kit.gate(1.6, 1.05);
  leaf.position.set(-0.8, 0, 0);
  g.add(leaf);
  const hang = kit.lamp(2.4);
  hang.group.position.set(1.05, 1.2, 0.12);
  g.add(hang.group);
  g.add(kit.beam(new THREE.Vector3(0.85, 1.35, 0.05), new THREE.Vector3(1.05, 1.42, 0.12), 0.025, M.iron));
  const sheep = kit.sheep(1);
  g.add(sheep.group);
  sheep.head.rotation.x = 0.08;
  const mats = answer.map((c) => kit.glow(c, 0.9));
  const beads = [];
  for (let i = 0; i < 12; i++) {
    const x = i < 6 ? -3.4 + i * 0.5 : 1.15 + (i - 6) * 0.5;
    const b = kit.ball(0.055, mats[2], x, 1.02, 0.02, 10, 8);
    b.userData.noShadow = true;
    g.add(b);
    beads.push(b);
  }
  const col = new THREE.Color(), next = new THREE.Color();
  return {
    group: g,
    apply(p) {
      leaf.rotation.y = p.gate * 1.3;
      sheep.group.position.set(0, 0, p.z);
      sheep.group.rotation.y = p.yaw;
      const i = Math.min(2, Math.floor(p.lamp)), f = p.lamp - i;
      col.set(answer[i]).lerp(next.set(answer[Math.min(2, i + 1)]), f);
      hang.lamp.emissive.copy(col);
      hang.lamp.color.copy(col).multiplyScalar(0.3);
    },
    // counts: { rules: { yes, no, ask } | null }
    setCounts(c) {
      const k = c && c.rules ? c.rules : null;
      const n = k ? [k.yes, k.no, k.ask] : [0, 0, 12];
      const total = Math.max(1, n[0] + n[1] + n[2]);
      const shown = n.map((v) => (v > 0 ? Math.max(1, Math.round((v / total) * 12)) : 0));
      while (shown[0] + shown[1] + shown[2] > 12) shown[shown.indexOf(Math.max(...shown))]--;
      let i = 0;
      shown.forEach((count, which) => { for (let j = 0; j < count; j++, i++) { beads[i].material = mats[which]; beads[i].visible = true; } });
      for (; i < 12; i++) beads[i].visible = false;
    },
  };
}
