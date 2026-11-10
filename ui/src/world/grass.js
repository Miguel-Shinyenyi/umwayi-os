import * as THREE from 'three';
import { heightAt } from './height.js';
import { mulberry32 } from './random.js';

// Sparse still grass: a few thousand soft blades, kept off the platforms. Nothing sways.
export function buildGrass(keepOut, count = 4200) {
  const h = 0.4, w = 0.045;
  const pos = [], col = [], idx = [];
  const rows = 4;
  for (let i = 0; i <= rows; i++) {
    const t = i / rows;
    const half = (w * (1 - t)) / 2 + 0.002;
    const bend = t * t * 0.1;
    const shade = 0.5 + 0.55 * t;
    pos.push(-half, t * h, bend, half, t * h, bend);
    col.push(shade, shade, shade, shade, shade, shade);
    if (i < rows) idx.push(i * 2, i * 2 + 1, i * 2 + 2, i * 2 + 1, i * 2 + 3, i * 2 + 2);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
  geo.setIndex(idx);
  geo.computeVertexNormals();
  const mat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 1, side: THREE.DoubleSide });
  const mesh = new THREE.InstancedMesh(geo, mat, count);
  const rnd = mulberry32(21);
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler(), s = new THREE.Vector3(), p = new THREE.Vector3(), c = new THREE.Color();
  let placed = 0, tries = 0;
  while (placed < count && tries++ < count * 6) {
    const r = 3 + Math.pow(rnd(), 0.8) * 34, a = rnd() * Math.PI * 2;
    const x = Math.cos(a) * r, z = Math.sin(a) * r;
    if (keepOut.some((k) => Math.hypot(x - k.x, z - k.z) < 2.9)) continue;
    e.set((rnd() - 0.5) * 0.35, rnd() * Math.PI * 2, (rnd() - 0.5) * 0.35);
    q.setFromEuler(e);
    const k = 0.75 + rnd() * 0.8;
    p.set(x, heightAt(x, z) - 0.02, z);
    m.compose(p, q, s.set(k, k * (0.8 + rnd() * 0.6), k));
    mesh.setMatrixAt(placed, m);
    c.setHSL(0.36 + rnd() * 0.05, 0.26, 0.15 + rnd() * 0.06);
    mesh.setColorAt(placed, c);
    placed++;
  }
  mesh.count = placed;
  mesh.receiveShadow = true;
  return mesh;
}
