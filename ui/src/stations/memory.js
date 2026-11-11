// Memory: a spring pool among mossy stones. The pebbles at its edge stand for private paths; a flat stone covers them.
import * as THREE from 'three';
import { TOKENS } from '../world/palette.js';
import { poolMesh, sharedPoolMaterial } from '../world/water.js';

export const poses = [
  { level: 0.2, ring: 0, cover: 0 },
  { level: 1, ring: 1, cover: 0 },
  { level: 1, ring: 0.2, cover: 1 },
];

export function build(kit) {
  const { M } = kit;
  const g = new THREE.Group();
  const water = poolMesh(1.3, sharedPoolMaterial());
  g.add(water);
  for (let i = 0; i < 14; i++) {
    const a = (i / 14) * Math.PI * 2 + 0.2, r = 1.5 + (i % 3) * 0.06, s = 0.3 + (i % 4) * 0.05;
    g.add(kit.rock(s, i % 3 === 0 ? M.moss : i % 2 ? M.stone : M.stoneDark, Math.cos(a) * r, 0.1 + (i % 2) * 0.05, Math.sin(a) * r, i + 1, 1.2, 0.8, 1));
  }
  [[-1.2, -1.7, 1.1], [0.6, -2.0, 0.9], [1.7, -1.5, 1.2]].forEach(([x, z, r], i) => g.add(kit.rock(r, i === 1 ? M.moss : M.stone, x, r * 0.35, z, i + 20, 1.1, 0.85, 1)));
  const pebbleSpots = [[2.0, 0.9], [2.25, 1.15], [1.8, 1.25], [2.35, 0.75], [2.1, 1.5], [1.7, 0.8]];
  pebbleSpots.forEach(([x, z], i) => g.add(kit.rock(0.11 + (i % 3) * 0.02, M.stoneDark, x, 0.06, z, i + 40, 1.2, 0.6, 1)));
  const slab = kit.rock(0.6, M.stone, 3.1, 0.14, 1.0, 55, 1.35, 0.2, 1.05);
  g.add(slab);
  const ringMat = kit.glow(TOKENS.amber, 1.6, 0);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(1, 0.018, 6, 64), ringMat);
  ring.rotation.x = Math.PI / 2;
  g.add(ring);
  return {
    group: g,
    apply(p) {
      water.position.y = 0.04 + p.level * 0.2;
      ring.position.y = water.position.y + 0.02;
      ring.scale.setScalar(0.35 + 0.75 * p.ring);
      ring.visible = p.ring > 0.02;
      kit.level(ringMat, p.ring * (1 - 0.5 * p.ring));
      slab.position.x = 3.1 - 1.15 * p.cover;
      slab.position.y = 0.14 + 0.1 * Math.sin(Math.PI * p.cover);
    },
    setCounts() {},
  };
}
