import * as THREE from 'three';
import { mulberry32 } from './random.js';

// Three ridges, far to near. Plain dark shapes that the fog turns blue and soft.
export function buildMountains() {
  const g = new THREE.Group();
  const layers = [
    { r: 160, h: 26, color: 0x23323a, seed: 3 },
    { r: 132, h: 19, color: 0x1b2a2e, seed: 5 },
    { r: 108, h: 12, color: 0x15221f, seed: 9 },
  ];
  for (const L of layers) {
    const rnd = mulberry32(L.seed);
    const n = 220;
    const phase = [rnd() * 6, rnd() * 6, rnd() * 6];
    const pos = [], idx = [];
    for (let i = 0; i <= n; i++) {
      const a = (i / n) * Math.PI * 2;
      const e = 0.55 + 0.3 * Math.sin(a * 3 + phase[0]) + 0.2 * Math.sin(a * 7 + phase[1]) + 0.12 * Math.sin(a * 17 + phase[2]);
      const h = L.h * Math.max(0.15, e);
      pos.push(Math.sin(a) * L.r, -6, Math.cos(a) * L.r, Math.sin(a) * L.r, h, Math.cos(a) * L.r);
      if (i < n) idx.push(i * 2, i * 2 + 1, i * 2 + 2, i * 2 + 1, i * 2 + 3, i * 2 + 2);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    geo.setIndex(idx);
    g.add(new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: L.color, side: THREE.DoubleSide })));
  }
  return g;
}
