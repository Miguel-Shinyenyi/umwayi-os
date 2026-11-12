// Queue: a round sheepfold of drystone with one gap and a hurdle. Open rows are sheep waiting in single file outside;
// answered rows are stones in the cairn.
import * as THREE from 'three';
import { smoothstep } from '../engine/ease.js';
import { sceneNumbers } from '../data/snapshot.js';

export const poses = [
  { shift: 0, door: 0 },
  { shift: 0.55, door: 1 },
  { shift: 1, door: 0 },
];

export function build(kit) {
  const { M } = kit;
  const g = new THREE.Group();
  const R = 2.0, pts = [];
  for (let a = 112; a <= 428; a += 14) pts.push([Math.cos((a * Math.PI) / 180) * R, Math.sin((a * Math.PI) / 180) * R]);
  g.add(kit.wall(pts, 1.0, 0.6, 7));
  // the hurdle in the gap (the gap is on the +z side)
  const hurdle = kit.gate(1.35, 0.95);
  hurdle.position.set(-0.67, 0, R - 0.05);
  g.add(hurdle);
  const inside = [kit.sheep(0.85), kit.sheep(0.85)];
  inside[0].group.position.set(-0.5, 0, -0.2); inside[0].group.rotation.y = 2.4; inside[0].head.rotation.x = 0.7;
  inside[1].group.position.set(0.6, 0, 0.4); inside[1].group.rotation.y = 0.6;
  inside.forEach((s) => g.add(s.group));
  const door = new THREE.Vector3(0, 0, R + 0.25);
  const dir = new THREE.Vector3(-0.62, 0, 0.78).normalize().multiplyScalar(0.64);
  const yaw = Math.atan2(-dir.x, -dir.z);
  const MAX = 7, line = [];
  for (let i = 0; i < MAX + 1; i++) {
    const s = kit.sheep(0.88);
    s.group.rotation.y = yaw;
    s.group.userData.part = 'sheep';
    g.add(s.group);
    line.push(s.group);
  }
  const cairn = new THREE.Group();
  cairn.position.set(2.9, 0, 0.6);
  g.add(cairn);
  const rows = [[-0.32, 0], [0, 0], [0.32, 0], [-0.16, 1], [0.16, 1], [0, 2], [-0.48, 0], [0.48, 0]];
  const stones = rows.map(([x, row], i) => {
    const s = kit.rock(0.17 - row * 0.02, i % 2 ? M.stone : M.stoneDark, x, 0.08 + row * 0.15, 0, i + 3);
    s.visible = false;
    s.userData.part = 'stone';
    cairn.add(s);
    return s;
  });
  const unknownMark = kit.unknownMark(-2.9, -0.8);
  g.add(unknownMark);
  let open = 0, shift = 0;
  const layout = () => {
    const n = Math.min(open, MAX);
    line.forEach((s, i) => {
      s.visible = i < n || (i === n && n > 0);
      if (!s.visible) return;
      const incoming = i === n, k = incoming ? n : i;
      s.position.copy(door).addScaledVector(dir, k + 1 - shift);
      let scale = 1;
      if (i === 0 && !incoming) scale = 1 - smoothstep(0.7, 1, shift);
      if (incoming) scale = smoothstep(0.35, 1, shift);
      s.scale.setScalar(Math.max(0.0001, scale));
    });
  };
  return {
    group: g,
    apply(p) {
      shift = p.shift;
      hurdle.rotation.y = -p.door * 1.4;
      layout();
    },
    // the mapping table (data/snapshot.js): sheep for open rows, stones for answered rows; a queue that cannot be read is the mark
    setCounts(c) {
      const n = sceneNumbers(c).queue;
      open = n.sheep;
      stones.forEach((s, i) => { s.visible = i < n.stones; });
      unknownMark.visible = n.unknown;
      layout();
    },
  };
}
