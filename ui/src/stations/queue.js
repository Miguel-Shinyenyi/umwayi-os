import * as THREE from 'three';
// Queue: sheep wait in single file at a hut. Open rows are sheep in the line; answered rows are stones in the cairn.
import { TOKENS } from '../world/palette.js';
import { smoothstep } from '../engine/ease.js';

export const poses = [
  { shift: 0, door: 0 },
  { shift: 0.55, door: 1 },
  { shift: 1, door: 0 },
];

export function build(kit) {
  const { M } = kit;
  const g = new THREE.Group();
  // hut
  const hut = new THREE.Group();
  hut.position.set(1.3, 0, -0.65);
  g.add(hut);
  hut.add(kit.box(1.1, 0.7, 0.85, M.woodDark, 0, 0.35, 0));
  const roof = kit.mesh(new THREE.ConeGeometry(0.95, 0.55, 4).rotateY(Math.PI / 4).scale(1, 1, 0.85), M.thatch, 0, 0.97, 0);
  hut.add(roof);
  const inside = kit.glow(TOKENS.amber, 1.6, 0);
  hut.add(kit.mesh(new THREE.BoxGeometry(0.4, 0.5, 0.02), inside, 0.15, 0.3, 0.43));
  const doorPivot = new THREE.Group();
  doorPivot.position.set(-0.05, 0, 0.45);
  doorPivot.add(kit.box(0.42, 0.52, 0.04, M.wood, 0.21, 0.28, 0));
  hut.add(doorPivot);
  // the door of the hut in the group's frame, and the direction the line runs away from it
  const door = new THREE.Vector3(1.45, 0, -0.1);
  const dir = new THREE.Vector3(-0.9, 0, 0.5).normalize().multiplyScalar(0.64);
  const yaw = Math.atan2(-dir.x, -dir.z);
  const MAX = 7;
  const sheep = [];
  for (let i = 0; i < MAX + 1; i++) {
    const s = kit.sheep(0.88);
    s.group.rotation.y = yaw;
    g.add(s.group);
    sheep.push(s.group);
  }
  // a signpost with two arrows (a task and a decision) and the cairn of answered stones
  const sign = new THREE.Group();
  sign.position.set(-1.75, 0, -0.8);
  sign.add(kit.post(1.1, 0.05, M.woodDark));
  sign.add(kit.box(0.6, 0.15, 0.04, M.wood, 0.28, 0.92, 0));
  sign.add(kit.box(0.6, 0.15, 0.04, M.wood, -0.28, 0.66, 0));
  g.add(sign);
  const cairn = new THREE.Group();
  cairn.position.set(0.0, 0, -1.3);
  g.add(cairn);
  const stones = [];
  const rows = [[-0.3, 0], [0.0, 0], [0.3, 0], [-0.15, 1], [0.15, 1], [0, 2], [-0.45, 0], [0.45, 0]];
  rows.forEach(([x, row], i) => {
    const s = kit.rock(0.17 - row * 0.02, M.stone, x, 0.1 + row * 0.15, 0, i + 3);
    s.visible = false;
    cairn.add(s);
    stones.push(s);
  });

  let open = 0;
  let shift = 0;
  const layout = () => {
    const n = Math.min(open, MAX);
    sheep.forEach((s, i) => {
      s.visible = i < n || (i === n && n > 0 && n <= MAX);
      if (!s.visible) return;
      const incoming = i === n;
      const k = incoming ? n : i;
      const slot = k + 1 - shift;
      s.position.copy(door).addScaledVector(dir, slot);
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
      doorPivot.rotation.y = -p.door * 1.35;
      kit.level(inside, p.door);
      layout();
    },
    setCounts(c) {
      open = c && c.queue ? c.queue.open : 0;
      const answered = c && c.queue ? Math.min(c.queue.answered, rows.length) : 0;
      stones.forEach((s, i) => { s.visible = i < answered; });
      layout();
    },
  };
}
