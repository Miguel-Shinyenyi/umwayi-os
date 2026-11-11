// Adapters: two ways over the river (stepping stones and a plank bridge) lead to one gate post on the bank. A pulse runs
// from each into the post: Claude Code over the ford, Kiro over the bridge. Any stdin and stdout tool can reach the post too.
// (The rope line, a third crossing, was cut by the owner on Nov 11.)
// The river runs along x; the bank is on +z. The group stands at the water level.
import * as THREE from 'three';
import { TOKENS } from '../world/palette.js';

export const poses = [
  { a: 0, b: 0 },
  { a: 1, b: 0 },
  { a: 1, b: 1 },
];

export function build(kit) {
  const { M } = kit;
  const g = new THREE.Group();
  // the ford: flat stones across the river
  for (let i = 0; i < 7; i++) g.add(kit.rock(0.32, M.stone, -2.0 + (i % 2) * 0.12, 0.02, -3.0 + i * 1.0, i + 70, 1.1, 0.4, 1));
  // the plank bridge
  const deck = new THREE.Group();
  for (const x of [-0.14, 0.14]) deck.add(kit.box(0.08, 0.1, 7.6, M.woodDark, x + 0.4, 0.82, 0));
  for (let i = 0; i < 24; i++) deck.add(kit.box(0.62, 0.05, 0.24, M.wood, 0.4, 0.9, -3.45 + i * 0.3));
  g.add(deck);
  for (const z of [-3.6, 3.6]) for (const x of [0.12, 0.68]) g.add(kit.post(1.5, 0.05, M.woodDark, x, z));
  g.add(kit.beam(new THREE.Vector3(0.12, 1.4, -3.6), new THREE.Vector3(0.12, 1.4, 3.6), 0.035, M.wood));
  g.add(kit.beam(new THREE.Vector3(0.68, 1.4, -3.6), new THREE.Vector3(0.68, 1.4, 3.6), 0.035, M.wood));
  // the gate post on the bank, with a ring that takes the light
  const post = kit.post(1.7, 0.09, M.woodDark, 0.3, 4.2);
  post.position.y = 0.45;
  g.add(post);
  const ringMat = kit.glow(TOKENS.amber, 2.3, 0);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.16, 0.028, 8, 24), ringMat);
  ring.position.set(0.3, 1.75, 4.32);
  g.add(ring);
  for (let i = 0; i < 4; i++) g.add(kit.rock(0.5, M.stoneDark, -1.6 + i * 1.9, 0.45, 4.6, i + 80, 1.3, 0.7, 1));
  const pulseMat = kit.glow(TOKENS.amber, 3.2);
  const pulses = [0, 1].map(() => { const s = kit.ball(0.09, pulseMat, 0, 0, 0, 12, 8); s.userData.noShadow = true; g.add(s); return s; });
  const from = [new THREE.Vector3(-1.9, 0.3, 3.2), new THREE.Vector3(0.4, 1.0, 3.5)];
  const to = new THREE.Vector3(0.3, 1.75, 4.32);
  return {
    group: g,
    apply(p) {
      [p.a, p.b].forEach((v, i) => {
        pulses[i].position.lerpVectors(from[i], to, v);
        pulses[i].scale.setScalar(Math.max(0.0001, Math.sin(Math.PI * v)));
        pulses[i].visible = v > 0.001 && v < 0.999;
      });
      kit.level(ringMat, Math.max(p.a, p.b) * 0.5 + (p.a + p.b) / 4);
    },
    setCounts() {},
  };
}
