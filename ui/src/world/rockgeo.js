// Rock shapes made in code (12.R19.6): no low poly blobs. A boulder is a finely divided sphere pushed out by 3D noise, cut by
// a few flat fracture planes and flattened at the base; a wall stone is a rounded slab with a rough face. Seeded, so the
// same seed gives the same stone, and shared between instances so a wall of many stones costs little.
import * as THREE from 'three';
import { mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';
import { mulberry32 } from './random.js';

const fract = (x) => x - Math.floor(x);
const h3 = (x, y, z) => fract(Math.sin(x * 127.1 + y * 311.7 + z * 74.7) * 43758.5453);
const fade = (t) => t * t * (3 - 2 * t);
function vnoise3(x, y, z) {
  const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z);
  const u = fade(x - xi), v = fade(y - yi), w = fade(z - zi);
  const l = (a, b, t) => a + (b - a) * t;
  const c = (i, j, k) => h3(xi + i, yi + j, zi + k);
  return l(l(l(c(0, 0, 0), c(1, 0, 0), u), l(c(0, 1, 0), c(1, 1, 0), u), v), l(l(c(0, 0, 1), c(1, 0, 1), u), l(c(0, 1, 1), c(1, 1, 1), u), v), w);
}
const fbm3 = (x, y, z, o = 4) => { let s = 0, a = 0.5, n = 0; for (let i = 0; i < o; i++) { s += a * vnoise3(x, y, z); n += a; x = x * 2.03 + 5.1; y = y * 2.03 + 1.7; z = z * 2.03 + 9.3; a *= 0.5; } return s / n; };

function finish(g) {
  g.deleteAttribute('uv');
  g.deleteAttribute('normal');
  const m = mergeVertices(g, 1e-5);
  m.computeVertexNormals();
  return m;
}

// A boulder of radius about 1, centred on 0, with a flat base at y = -0.55. detail 4 is about 2.5 thousand points, 3 about 640.
export function boulderGeometry(seed = 1, detail = 4) {
  const rnd = mulberry32(seed * 7919 + 11);
  const g = new THREE.IcosahedronGeometry(1, detail);
  const p = g.attributes.position;
  const planes = Array.from({ length: 4 + Math.floor(rnd() * 3) }, () => {
    const n = new THREE.Vector3(rnd() - 0.5, rnd() * 0.9 - 0.2, rnd() - 0.5).normalize();
    return { n, d: 0.62 + rnd() * 0.25 };
  });
  const o = rnd() * 50, v = new THREE.Vector3();
  for (let i = 0; i < p.count; i++) {
    v.fromBufferAttribute(p, i);
    const big = fbm3(v.x * 1.3 + o, v.y * 1.3, v.z * 1.3, 3), fine = fbm3(v.x * 5 + o, v.y * 5, v.z * 5, 3);
    v.multiplyScalar(0.78 + 0.42 * big + 0.07 * fine);
    for (const pl of planes) { const k = v.dot(pl.n) - pl.d; if (k > 0) v.addScaledVector(pl.n, -k * 0.92); } // fracture faces
    if (v.y < -0.55) v.y = -0.55 + (v.y + 0.55) * 0.15; // a flat base that sits in the ground
    p.setXYZ(i, v.x, v.y, v.z);
  }
  return finish(g);
}

// A wall stone, 1 by 1 by 1 before scaling: a slab with rounded edges and a rough face.
export function slabGeometry(seed = 1) {
  const rnd = mulberry32(seed * 104729 + 3);
  const g = new THREE.BoxGeometry(1, 1, 1, 6, 3, 4);
  const p = g.attributes.position, v = new THREE.Vector3(), o = rnd() * 40;
  for (let i = 0; i < p.count; i++) {
    v.fromBufferAttribute(p, i);
    // round the edges: a box with a radius on every edge and corner
    const rad = 0.2 + rnd() * 0.08, lim = 0.5 - rad;
    const ix = Math.max(-lim, Math.min(lim, v.x)), iy = Math.max(-lim, Math.min(lim, v.y)), iz = Math.max(-lim, Math.min(lim, v.z));
    const dx = v.x - ix, dy = v.y - iy, dz = v.z - iz, dl = Math.hypot(dx, dy, dz);
    if (dl > 1e-6) v.set(ix + (dx / dl) * rad, iy + (dy / dl) * rad, iz + (dz / dl) * rad);
    const n = fbm3(v.x * 3 + o, v.y * 3, v.z * 3, 3) - 0.5, f = fbm3(v.x * 9 + o, v.y * 9, v.z * 9, 2) - 0.5;
    v.x *= 1 + n * 0.22; v.y *= 1 + n * 0.3 + f * 0.08; v.z *= 1 + n * 0.18 + f * 0.1;
    p.setXYZ(i, v.x, v.y, v.z);
  }
  return finish(g);
}
