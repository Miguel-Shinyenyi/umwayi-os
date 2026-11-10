import * as THREE from 'three';
// Kill switch: a lane with a wattle hurdle between two posts. Down, the sheep walk through. Up, the posts glow red and
// the next sheep halts. Unknown is drawn as on, because if umwayi cannot tell, it stops.
import { TOKENS } from '../world/palette.js';
import { lerp } from '../engine/ease.js';

export const poses = [
  { hurdle: 0, red: 0, a: -2.3, b: -3.6 },
  { hurdle: 0, red: 0, a: 2.3, b: -3.6 },
  { hurdle: 1, red: 1, a: 2.3, b: -0.95 },
];

export function build(kit) {
  const { M } = kit;
  const g = new THREE.Group();
  g.rotation.y = -0.35;
  // the lane: two low strips of fence
  for (const z of [-0.85, 0.85]) {
    const pts = Array.from({ length: 7 }, (_, i) => new THREE.Vector3(-2.2 + i * 0.73, 0, z));
    pts.forEach((p) => g.add(kit.post(0.32, 0.03, M.wood, p.x, p.z)));
    for (let i = 0; i < 6; i++) g.add(kit.beam(pts[i].clone().setY(0.26), pts[i + 1].clone().setY(0.26), 0.025, M.wood));
  }
  const capMat = kit.glow(TOKENS.red, 2.6, 0);
  for (const z of [-0.72, 0.72]) {
    g.add(kit.post(1.2, 0.07, M.woodDark, 0, z));
    g.add(kit.ball(0.095, capMat, 0, 1.28, z, 12, 8));
  }
  const hurdle = new THREE.Group();
  for (let i = 0; i < 6; i++) hurdle.add(kit.box(0.06, 0.07, 1.36, M.wood, 0, 0.14 + i * 0.1, 0));
  for (let i = 0; i < 7; i++) hurdle.add(kit.box(0.08, 0.7, 0.05, M.woodDark, 0, 0.35, -0.65 + i * 0.217));
  g.add(hurdle);
  const a = kit.sheep(0.9), b = kit.sheep(0.9);
  for (const s of [a, b]) {
    s.group.rotation.y = Math.PI / 2;
    g.add(s.group);
  }
  let on = false;
  const restParams = () => (on ? { hurdle: 1, red: 1, a: 2.3, b: -0.95 } : { hurdle: 0, red: 0, a: 2.3, b: -3.6 });
  return {
    group: g,
    apply(p) {
      hurdle.position.y = lerp(-0.74, 0, p.hurdle);
      hurdle.visible = p.hurdle > 0.01;
      kit.level(capMat, p.red);
      a.group.position.set(p.a, 0, 0);
      b.group.position.set(p.b, 0, 0);
    },
    // counts: { kill_switch: 'on' | 'off' | 'unknown' }; anything but off is drawn as on
    setCounts(c) {
      on = !(c && c.kill_switch === 'off');
    },
    rest: () => restParams(),
  };
}
