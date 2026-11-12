// Workflows: a stream down a hillside through three rock pools joined by short cascades (four was cut by the owner on
// Nov 11); a sheep crosses by stepping stones beside it. Each pool is lit as the steps pass. At the last pool a token waits for your approval.
import * as THREE from 'three';
import { TOKENS } from '../world/palette.js';
import { smoothstep } from '../engine/ease.js';
import { poolMesh, sharedPoolMaterial } from '../world/water.js';

export const poses = [
  { w: 0, token: 0 },
  { w: 0.5, token: 0 },
  { w: 1, token: 1 },
];

export function build(kit) {
  const { M } = kit;
  const g = new THREE.Group();
  const P = [[-2.0, 0.8, -0.9, 0.64], [0.0, 0.35, -0.6, 0.62], [2.0, -0.1, -0.3, 0.72]];
  const rings = [];
  P.forEach(([x, y, z, r], k) => {
    const pool = poolMesh(r, sharedPoolMaterial());
    pool.position.set(x, y + 0.05, z);
    g.add(pool);
    for (let i = 0; i < 9; i++) {
      const a = (i / 9) * Math.PI * 2 + k, rr = r + 0.14;
      g.add(kit.rock(0.2 + (i % 3) * 0.04, i % 3 ? M.stone : M.moss, x + Math.cos(a) * rr, y + 0.05, z + Math.sin(a) * rr, i + k * 9, 1.2, 0.8, 1));
    }
    const m = kit.glow(TOKENS.amber, 1.6, 0);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(r * 0.7, 0.014, 6, 36), m);
    ring.rotation.x = Math.PI / 2;
    ring.position.set(x, y + 0.08, z);
    g.add(ring);
    rings.push(m);
    if (k < 2) {
      const [x2, y2, z2] = P[k + 1];
      const fall = new THREE.Mesh(new THREE.PlaneGeometry(0.32, Math.hypot(x2 - x, z2 - z) + 0.4), new THREE.MeshBasicMaterial({ color: 0x8fa3ae, transparent: true, opacity: 0.55, side: THREE.DoubleSide, depthWrite: false }));
      fall.position.set((x + x2) / 2, (y + y2) / 2 + 0.1, (z + z2) / 2);
      fall.rotation.set(-Math.PI / 2 + 0.45, Math.atan2(x2 - x, z2 - z), 0, 'YXZ');
      fall.userData.noShadow = true;
      g.add(fall);
    }
  });
  // the stepping stones beside the stream
  const S = P.map(([x, y, z], k) => new THREE.Vector3(x - 0.2, y, z + 1.35 + 0.0 * k));
  S.forEach((v, k) => g.add(kit.rock(0.3, M.stone, v.x, v.y + 0.05, v.z, k + 60, 1.1, 0.45, 1)));
  const path = [new THREE.Vector3(-3.1, 1.15, 1.6), ...S.map((v) => v.clone().setY(v.y + 0.22)), new THREE.Vector3(3.1, -0.15, 1.0)];
  const sheep = kit.sheep(0.85);
  g.add(sheep.group);
  const tokenMat = kit.glow(TOKENS.amber, 2.2, 0);
  const token = kit.mesh(new THREE.CylinderGeometry(0.15, 0.15, 0.04, 24), tokenMat, 2.7, -0.2, 0.3);
  g.add(token);
  return {
    group: g,
    apply(p) {
      const u = p.w * (path.length - 1), i = Math.min(path.length - 2, Math.floor(u)), f = u - i;
      sheep.group.position.lerpVectors(path[i], path[i + 1], f);
      if (p.w > 0 && p.w < 1) sheep.group.position.y += Math.abs(Math.sin(u * Math.PI)) * 0.1;
      const d = new THREE.Vector3().subVectors(path[i + 1], path[i]);
      sheep.group.rotation.y = Math.atan2(d.x, d.z);
      rings.forEach((m, k) => kit.level(m, smoothstep(k + 0.7, k + 1.15, u)));
      kit.level(tokenMat, p.token);
      token.scale.setScalar(Math.max(0.0001, p.token));
    },
    setCounts() {},
  };
}
