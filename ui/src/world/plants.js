import * as THREE from 'three';
import { mergeVertices, mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { heightAt, RIVER_HALF_WIDTH } from './height.js';
import { nearestOnRiver } from './river.js';
import { reachable, SHEPHERD_SPACE } from './layout.js';
import { mulberry32 } from './random.js';
import { fbm } from './noise.js';
import { grain } from './surface.js';

const slopeAt = (x, z) => Math.hypot(heightAt(x + 0.8, z) - heightAt(x - 0.8, z), heightAt(x, z + 0.8) - heightAt(x, z - 0.8)) / 1.6;

// candidate spots for a kind of plant, deterministic, kept off the water, the steep rock, the shepherd and every place a station can stand
function spots({ seed, count, rMin, rMax, tries, ok, apart = 0, clearOf = 0.4 }) {
  const rnd = mulberry32(seed), keep = reachable(), out = [];
  for (let t = 0; t < tries && out.length < count; t++) {
    const r = rMin + Math.sqrt(rnd()) * (rMax - rMin), a = rnd() * Math.PI * 2;
    const x = Math.cos(a) * r, z = Math.sin(a) * r;
    if (r < SHEPHERD_SPACE + 0.6) continue;
    if (keep.some((k) => Math.hypot(x - k.x, z - k.z) < k.r + clearOf)) continue;
    if (nearestOnRiver({ x, z }).distance < RIVER_HALF_WIDTH + 1.6) continue;
    if (apart && out.some((o) => Math.hypot(x - o.x, z - o.z) < apart)) continue;
    const y = heightAt(x, z), s = slopeAt(x, z);
    if (!ok(x, z, y, s, rnd)) continue;
    out.push({ x, z, y, s, rnd: rnd() });
  }
  return out;
}

function blob(detail, amount, sx, sy, sz, seed) {
  const g = new THREE.IcosahedronGeometry(1, detail);
  g.deleteAttribute('uv'); g.deleteAttribute('normal');
  const p = g.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i), y = p.getY(i), z = p.getZ(i);
    const k = 1 + amount * (Math.sin(x * 4.1 + seed) * Math.sin(y * 3.3 + 1) + Math.cos(z * 4.7 + seed * 2) * 0.7);
    p.setXYZ(i, x * k * sx, y * k * sy, z * k * sz);
  }
  const m = mergeVertices(g, 1e-4);
  m.computeVertexNormals();
  return m;
}

// ---- grass: thousands of thin blades, still. Dry gold with green where it is wetter.
export function buildGrass(maxCount = 9000) {
  const h = 0.5, w = 0.05, rows = 4, pos = [], col = [], idx = [];
  for (let i = 0; i <= rows; i++) {
    const t = i / rows, half = (w * (1 - t * 0.92)) / 2 + 0.001, bend = t * t * 0.14, shade = 0.45 + 0.7 * t;
    pos.push(-half, t * h, bend, half, t * h, bend);
    col.push(shade, shade, shade, shade, shade, shade);
    if (i < rows) idx.push(i * 2, i * 2 + 1, i * 2 + 2, i * 2 + 1, i * 2 + 3, i * 2 + 2);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
  geo.setIndex(idx);
  geo.computeVertexNormals();
  const mesh = new THREE.InstancedMesh(geo, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 1, side: THREE.DoubleSide }), maxCount);
  const list = spots({ seed: 21, count: maxCount, rMin: 3, rMax: 62, tries: maxCount * 5, clearOf: 0.2, ok: (x, z, y, s, rnd) => s < 0.55 && y < 38 && rnd() < 1 - Math.min(0.85, Math.hypot(x, z) / 90) });
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler(), sc = new THREE.Vector3(), c = new THREE.Color();
  const rnd = mulberry32(22);
  list.forEach((s, i) => {
    e.set((rnd() - 0.5) * 0.4, rnd() * Math.PI * 2, (rnd() - 0.5) * 0.4);
    q.setFromEuler(e);
    const k = 0.7 + rnd() * 0.9;
    m.compose(new THREE.Vector3(s.x, s.y - 0.02, s.z), q, sc.set(k, k * (0.7 + rnd() * 0.8), k));
    mesh.setMatrixAt(i, m);
    const dry = fbm(s.x * 0.045 + 4, s.z * 0.045 + 4, 3) * 1.4 + (rnd() - 0.5) * 0.25;
    c.setHSL(dry > 0.55 ? 0.115 : 0.22, dry > 0.55 ? 0.5 : 0.34, 0.27 + dry * 0.12 + rnd() * 0.05);
    mesh.setColorAt(i, c);
  });
  mesh.count = list.length;
  mesh.userData.total = list.length;
  mesh.receiveShadow = true;
  return mesh;
}

// ---- umbrella thorn acacia: a thin leaning trunk and a wide, flat, layered crown
export function buildAcacia(count = 13) {
  const g = new THREE.Group();
  const list = spots({ seed: 31, count, rMin: 20, rMax: 70, tries: 3000, apart: 11, clearOf: 4,
    ok: (x, z, y, s) => s < 0.28 && y < 6 && !(z > 20 && Math.abs(x) < 28) });
  const trunk = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.1, 0.24, 3.2, 7).translate(0, 1.6, 0), grain(new THREE.MeshStandardMaterial({ color: 0x6a5238, roughness: 1 }), { freq: 4, bump: 0.8, vary: 0.3 }), list.length);
  const crownGeo = blob(2, 0.22, 1, 1, 1, 3);
  const crown = new THREE.InstancedMesh(crownGeo, grain(new THREE.MeshStandardMaterial({ roughness: 1 }), { freq: 1.1, bump: 0.7, vary: 0.35, seed: 9 }), list.length * 3);
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), sc = new THREE.Vector3(), c = new THREE.Color();
  list.forEach((s, i) => {
    const k = 0.8 + s.rnd * 0.7, lean = (s.rnd - 0.5) * 0.3;
    q.setFromEuler(new THREE.Euler(lean, s.rnd * 6, lean * 0.6));
    m.compose(new THREE.Vector3(s.x, s.y - 0.1, s.z), q, sc.set(k, k, k));
    trunk.setMatrixAt(i, m);
    const top = new THREE.Vector3(Math.sin(lean) * -1.2 * k, 3.1 * k, Math.sin(lean * 0.6) * 1.2 * k);
    [[0, 0, 0, 4.0, 0.55], [1.7, 0.25, -0.9, 3.0, 0.46], [-1.5, 0.1, 1.2, 2.9, 0.44]].forEach(([ox, oy, oz, r, fl], j) => {
      m.compose(new THREE.Vector3(s.x + top.x + ox * k, s.y + top.y + oy * k, s.z + top.z + oz * k), q, sc.set(r * k, fl * k, r * k * 0.92));
      crown.setMatrixAt(i * 3 + j, m);
      c.setHSL(0.2 + s.rnd * 0.05, 0.3, 0.075 + j * 0.012 + s.rnd * 0.02);
      crown.setColorAt(i * 3 + j, c);
    });
  });
  for (const o of [trunk, crown]) { o.castShadow = true; o.receiveShadow = true; g.add(o); }
  return g;
}

// ---- African pencil cedar: a dark, narrow, layered cone
export function buildCedar(count = 26) {
  const g = new THREE.Group();
  const list = spots({ seed: 41, count, rMin: 30, rMax: 110, tries: 6000, apart: 7, clearOf: 3,
    ok: (x, z, y, s, rnd) => s < 0.7 && (y > 2.5 || nearestOnRiver({ x, z }).distance > 22) && fbm(x * 0.03, z * 0.03, 3) > 0.42 && !(z > 24 && Math.abs(x) < 30) });
  const tiers = [];
  for (let t = 0; t < 6; t++) {
    const c = new THREE.ConeGeometry(1.6 - t * 0.22, 2.0, 9, 1, true);
    const p = c.attributes.position;
    for (let i = 0; i < p.count; i++) p.setX(i, p.getX(i) * (1 + 0.12 * Math.sin(p.getY(i) * 5 + t) + 0.1 * Math.sin(p.getZ(i) * 9)));
    c.translate(0, 1.0 + t * 1.25, 0);
    c.deleteAttribute('uv');
    tiers.push(c);
  }
  const merged = mergeGeometries(tiers.map((t) => t.toNonIndexed()));
  merged.computeVertexNormals();
  const mesh = new THREE.InstancedMesh(merged, grain(new THREE.MeshStandardMaterial({ roughness: 1, side: THREE.DoubleSide }), { freq: 1.6, bump: 0.8, vary: 0.4, seed: 12 }), list.length);
  const trunkMesh = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.12, 0.25, 2, 6).translate(0, 1, 0), new THREE.MeshStandardMaterial({ color: 0x2a2018, roughness: 1 }), list.length);
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), sc = new THREE.Vector3(), c = new THREE.Color();
  list.forEach((s, i) => {
    const k = 0.9 + s.rnd * 1.1;
    q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), s.rnd * 6);
    m.compose(new THREE.Vector3(s.x, s.y - 0.1, s.z), q, sc.set(k * 0.9, k, k * 0.9));
    mesh.setMatrixAt(i, m);
    trunkMesh.setMatrixAt(i, m);
    c.setHSL(0.4 + s.rnd * 0.06, 0.28, 0.07 + s.rnd * 0.03);
    mesh.setColorAt(i, c);
  });
  for (const o of [mesh, trunkMesh]) { o.castShadow = true; o.receiveShadow = true; g.add(o); }
  return g;
}

// ---- boulders along the banks and on the slopes
export function buildBoulders(makeRock, count = 70) {
  const g = new THREE.Group();
  const list = spots({ seed: 51, count, rMin: 8, rMax: 80, tries: 4000, clearOf: 0.6,
    ok: (x, z, y, s, rnd) => (s > 0.22 || nearestOnRiver({ x, z }).distance < RIVER_HALF_WIDTH + 5) && rnd() < 0.6 });
  list.forEach((s, i) => {
    const r = 0.4 + s.rnd * s.rnd * 2.2;
    const rock = makeRock(r, i + 3, s.x, s.y + r * 0.2, s.z);
    g.add(rock);
  });
  return g;
}
