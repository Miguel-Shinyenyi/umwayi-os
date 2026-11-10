import * as THREE from 'three';
// Workflows: a sheep walks stepping stones in order. Each stone lights as it passes. At the arch a token waits for approval.
import { TOKENS } from '../world/palette.js';
import { smoothstep } from '../engine/ease.js';

export const poses = [
  { w: 0, token: 0 },
  { w: 0.5, token: 0 },
  { w: 1, token: 1 },
];

export function build(kit) {
  const { M } = kit;
  const g = new THREE.Group();
  const path = [[-1.95, 0.85], [-1.3, 0.55], [-0.5, 0.25], [0.3, -0.05], [1.0, -0.4], [1.55, -0.75]].map(([x, z]) => new THREE.Vector3(x, 0, z));
  const stones = [];
  for (let i = 1; i <= 4; i++) {
    const p = path[i];
    g.add(kit.cyl(0.34, 0.38, 0.1, M.stone, p.x, 0.05, p.z, 24));
    const lamp = kit.glow(TOKENS.amber, 1.8, 0);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(0.26, 0.014, 6, 36), lamp);
    ring.rotation.x = Math.PI / 2;
    ring.position.set(p.x, 0.105, p.z);
    g.add(ring);
    stones.push(lamp);
  }
  // the arch
  const C = path[5];
  const arch = new THREE.Group();
  arch.position.copy(C);
  const perp = new THREE.Vector3(0.38, 0, 0.92).normalize();
  arch.rotation.y = -Math.atan2(perp.z, perp.x);
  for (const s of [-1, 1]) arch.add(kit.post(1.15, 0.07, M.woodDark, s * 0.62, 0));
  const top = new THREE.Mesh(new THREE.TorusGeometry(0.62, 0.065, 8, 28, Math.PI), M.woodDark);
  top.position.y = 1.15;
  top.castShadow = true;
  arch.add(top);
  arch.add(kit.mesh(new THREE.CylinderGeometry(0.004, 0.004, 0.2, 4), M.metal, 0, 1.68, 0));
  arch.add(kit.ball(0.08, kit.glow(TOKENS.amber, 2.2), 0, 1.52, 0, 12, 8));
  g.add(arch);
  const tokenMat = kit.glow(TOKENS.amber, 2, 0);
  const token = kit.mesh(new THREE.CylinderGeometry(0.15, 0.15, 0.04, 24), tokenMat, C.x, 0.07, C.z);
  g.add(token);
  const sheep = kit.sheep(0.9);
  g.add(sheep.group);
  const seg = new THREE.Vector3();
  return {
    group: g,
    apply(p) {
      const u = p.w * 5;
      const i = Math.min(4, Math.floor(u));
      const f = u - i;
      seg.lerpVectors(path[i], path[i + 1], f);
      const dir = new THREE.Vector3().subVectors(path[i + 1], path[i]);
      sheep.group.position.copy(seg);
      sheep.group.position.y = p.w > 0 && p.w < 1 ? Math.abs(Math.sin(u * Math.PI)) * 0.1 : 0;
      sheep.group.position.y += i >= 1 && i <= 3 ? 0.1 : 0;
      sheep.group.rotation.y = Math.atan2(dir.x, dir.z);
      stones.forEach((m, k) => kit.level(m, smoothstep(k + 0.7, k + 1.05, u)));
      kit.level(tokenMat, p.token);
      const s = Math.max(0.0001, p.token);
      token.scale.set(s, s, s);
    },
    setCounts() {},
  };
}
