// Shared parts for the station models: materials, soft shapes, sheep, a dog, a platform.
// Everything is made in code. No file is loaded, so the page needs no network.
import * as THREE from 'three';
import { mergeGeometries, mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';
import { grain } from '../world/surface.js';

const fract = (x) => x - Math.floor(x);
export const hash = (x, y = 0, z = 0) => fract(Math.sin(x * 127.1 + y * 311.7 + z * 74.7) * 43758.5453);

// Smooth normals for a shape made of separate triangles (an icosphere).
function soften(geo) {
  geo.deleteAttribute('uv');
  geo.deleteAttribute('normal');
  const merged = mergeVertices(geo, 1e-4);
  merged.computeVertexNormals();
  return merged;
}
// One flat colour per vertex, with a little variation, ready to merge.
function paint(geo, hex, jitter = 0) {
  const c = new THREE.Color(hex);
  const pos = geo.attributes.position;
  const colors = new Float32Array(pos.count * 3);
  for (let i = 0; i < pos.count; i++) {
    const k = 1 - jitter * hash(pos.getX(i) * 9, pos.getY(i) * 7, pos.getZ(i) * 5);
    colors.set([c.r * k, c.g * k, c.b * k], i * 3);
  }
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geo.deleteAttribute('uv');
  return geo.index ? geo.toNonIndexed() : geo;
}
const place = (geo, x, y, z) => geo.translate(x, y, z);

function fluff(radius, detail, amount, sx = 1, sy = 1, sz = 1) {
  const g = new THREE.IcosahedronGeometry(radius, detail);
  const p = g.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i), y = p.getY(i), z = p.getZ(i);
    const k = 1 + amount * (Math.sin(x * 14 + 1.3) * Math.sin(y * 11 + 0.4) + Math.cos(z * 12 + 2.1) * 0.6);
    p.setXYZ(i, x * k * sx, y * k * sy, z * k * sz);
  }
  return soften(g);
}

const COLORS = {
  stone: 0x9a9384, stoneDark: 0x6e695d, moss: 0x4a5a35, wood: 0x6a4d36, woodDark: 0x41301f, iron: 0x3b3f44, rust: 0x7a4a30,
  thatch: 0x8a7440, wool: 0xcfc6b2, skin: 0x2a2724, parchment: 0xc2b085, line: 0xcfc9b8, water: 0x5e8c98, gold: 0xe0a965,
};
export { COLORS };

export function makeKit() {
  const glows = [];
  let glowScale = 1;
  const kit = { glows, COLORS };

  kit.std = (color, o = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.93, metalness: 0, ...o });
  // A lit part. The material is dim; the emissive colour carries the light and feeds the bloom.
  kit.glow = (color, base = 1.4, level = 1) => {
    const m = new THREE.MeshStandardMaterial({ color: new THREE.Color(color).multiplyScalar(0.3), emissive: color, roughness: 0.6 });
    m.userData.glow = { base, level };
    m.emissiveIntensity = base * level * glowScale;
    glows.push(m);
    return m;
  };
  kit.level = (m, level) => {
    m.userData.glow.level = level;
    m.emissiveIntensity = m.userData.glow.base * level * glowScale;
  };
  kit.glowListeners = [];
  kit.getGlowScale = () => glowScale;
  kit.setGlowScale = (k) => {
    glowScale = k;
    for (const m of glows) m.emissiveIntensity = m.userData.glow.base * m.userData.glow.level * k;
    kit.glowListeners.forEach((fn) => fn(k));
  };

  // surfaces with grain made from noise
  const M = {
    stone: grain(kit.std(COLORS.stone, { roughness: 0.97 }), { freq: 2.2, bump: 0.7, vary: 0.2, strata: 0.22, seed: 3 }),
    stoneDark: grain(kit.std(COLORS.stoneDark, { roughness: 0.97 }), { freq: 2.6, bump: 0.7, vary: 0.2, strata: 0.2, seed: 8 }),
    moss: grain(kit.std(COLORS.moss), { freq: 3.5, bump: 0.5, vary: 0.35, seed: 5 }),
    wood: grain(kit.std(COLORS.wood), { freq: 3, bump: 0.4, vary: 0.2, stripe: 0.6, seed: 2 }),
    woodDark: grain(kit.std(COLORS.woodDark), { freq: 3, bump: 0.4, vary: 0.2, stripe: 0.6, seed: 6 }),
    iron: kit.std(COLORS.iron, { roughness: 0.55, metalness: 0.5 }),
    rust: grain(kit.std(COLORS.rust, { roughness: 0.7, metalness: 0.35 }), { freq: 5, bump: 0.3, vary: 0.4, seed: 4 }),
    thatch: kit.std(COLORS.thatch),
    parchment: kit.std(COLORS.parchment),
    line: kit.std(COLORS.line),
    animal: new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 1 }),
  };
  kit.M = M;

  const shadow = (o, cast = true) => {
    o.traverse((c) => {
      if (c.isMesh) {
        c.castShadow = cast && !c.userData.noShadow;
        c.receiveShadow = true;
      }
    });
    return o;
  };
  kit.shadow = shadow;
  const mesh = (geo, mat, x = 0, y = 0, z = 0) => {
    const m = new THREE.Mesh(geo, mat);
    m.position.set(x, y, z);
    m.castShadow = m.receiveShadow = true;
    return m;
  };
  kit.mesh = mesh;
  kit.box = (w, h, d, mat, x, y, z) => mesh(new THREE.BoxGeometry(w, h, d), mat, x, y, z);
  kit.cyl = (rt, rb, h, mat, x, y, z, seg = 18) => mesh(new THREE.CylinderGeometry(rt, rb, h, seg), mat, x, y, z);
  kit.ball = (r, mat, x, y, z, ws = 20, hs = 14) => mesh(new THREE.SphereGeometry(r, ws, hs), mat, x, y, z);
  kit.post = (h, r, mat, x = 0, z = 0) => mesh(new THREE.CylinderGeometry(r * 0.82, r, h, 10).translate(0, h / 2, 0), mat, x, 0, z);
  kit.beam = (a, b, t, mat) => {
    const d = new THREE.Vector3().subVectors(b, a);
    const m = mesh(new THREE.BoxGeometry(t, t, d.length()), mat);
    m.position.copy(a).addScaledVector(d, 0.5);
    m.lookAt(b);
    return m;
  };
  // a craggy stone: one of six shared displaced icospheres, scaled and turned (so a wall costs little)
  const ROCKS = Array.from({ length: 6 }, (_, i) => fluff(1, 3, 0.15, 1, 1, 1).rotateY(i * 1.3));
  kit.rock = (r, mat, x, y, z, seed = 1, sx = 1.15, sy = 0.75, sz = 1) => {
    const m = mesh(ROCKS[Math.abs(Math.floor(seed)) % 6], mat, x, y, z);
    m.scale.set(r * sx, r * sy, r * sz);
    m.rotation.y = seed * 2.1;
    return m;
  };
  // a drystone wall along a polyline of [x, z] points: courses of stones, each a little different
  kit.wall = (pts, h = 0.9, t = 0.55, seed = 1) => {
    const g = new THREE.Group();
    for (let i = 0; i < pts.length - 1; i++) {
      const [x0, z0] = pts[i], [x1, z1] = pts[i + 1];
      const len = Math.hypot(x1 - x0, z1 - z0), n = Math.max(2, Math.round(len / 0.36));
      const rows = Math.max(2, Math.round(h / 0.27));
      for (let r = 0; r < rows; r++) {
        for (let k = 0; k < n; k++) {
          const f = (k + 0.5 * (r % 2) + hash(i, k, r + seed) * 0.2) / n;
          if (f > 1) continue;
          const x = x0 + (x1 - x0) * f, z = z0 + (z1 - z0) * f;
          const s = 0.2 + hash(k, r, seed) * 0.08;
          const st = kit.rock(s, hash(k + 1, r, seed) > 0.5 ? M.stone : M.stoneDark, x + (hash(r, k, 2) - 0.5) * 0.08, 0.12 + r * 0.26, z + (hash(k, r, 4) - 0.5) * 0.1, k + r * 7 + seed, 1.15, 0.78, t / 0.42);
          st.rotation.y = Math.atan2(x1 - x0, z1 - z0) + Math.PI / 2;
          g.add(st);
        }
      }
    }
    return g;
  };
  // a wooden gate of width w, hinged at x = 0 and opening along +x. Returns the leaf; rotate it about y to open.
  kit.gate = (w = 1.5, h = 1.0) => {
    const leaf = new THREE.Group();
    for (const y of [0.18, h * 0.5, h - 0.1]) leaf.add(kit.box(w, 0.07, 0.05, M.wood, w / 2, y, 0));
    for (const x of [0.04, w - 0.04]) leaf.add(kit.box(0.07, h, 0.06, M.wood, x, h / 2, 0));
    leaf.add(kit.beam(new THREE.Vector3(0.05, 0.18, 0), new THREE.Vector3(w - 0.05, h - 0.1, 0), 0.05, M.wood));
    return leaf;
  };
  // a small hanging lamp on a bracket; lamp is the lit part
  kit.lamp = (base = 2.2) => {
    const g = new THREE.Group();
    const lamp = kit.glow(COLORS.gold, base);
    g.add(kit.mesh(new THREE.CylinderGeometry(0.07, 0.055, 0.15, 8), lamp, 0, 0, 0));
    g.add(kit.mesh(new THREE.ConeGeometry(0.1, 0.07, 8), M.iron, 0, 0.11, 0));
    g.add(kit.mesh(new THREE.CylinderGeometry(0.008, 0.008, 0.18, 4), M.iron, 0, 0.22, 0));
    return { group: g, lamp };
  };

  // Sheep: soft wool, a dark head on a pivot so it can bow.
  const sheepGeo = (() => {
    const wool = [
      paint(place(fluff(0.4, 3, 0.07, 1, 0.82, 1.3), 0, 0.52, 0), COLORS.wool, 0.16),
      paint(place(fluff(0.12, 2, 0.05), 0, 0.6, -0.52), COLORS.wool, 0.1),
    ];
    for (const sx of [-1, 1]) for (const sz of [-1, 1]) {
      wool.push(paint(place(new THREE.CylinderGeometry(0.03, 0.036, 0.32, 8), sx * 0.15, 0.16, sz * 0.27), COLORS.skin));
    }
    const head = new THREE.SphereGeometry(0.17, 14, 10).scale(0.82, 0.95, 1.15);
    const parts = [paint(place(head, 0, 0, 0.15), COLORS.skin, 0.1)];
    for (const sx of [-1, 1]) {
      const ear = new THREE.SphereGeometry(0.07, 8, 6).scale(1.3, 0.3, 0.7);
      ear.rotateZ(sx * 0.35);
      parts.push(paint(place(ear, sx * 0.17, 0.08, 0.06), COLORS.skin));
    }
    return { body: mergeGeometries(wool), head: mergeGeometries(parts) };
  })();
  kit.sheep = (scale = 1) => {
    const g = new THREE.Group();
    g.add(mesh(sheepGeo.body, M.animal));
    const head = new THREE.Group();
    head.position.set(0, 0.64, 0.42);
    head.add(mesh(sheepGeo.head, M.animal));
    g.add(head);
    g.scale.setScalar(scale);
    return { group: g, head };
  };

  // A sheepdog: dark coat, pale chest and legs.
  const dogGeo = (() => {
    const dark = 0x1f1f1d, pale = 0xaaa595;
    const parts = [
      paint(place(new THREE.SphereGeometry(0.3, 14, 10).scale(0.62, 0.62, 1.5), 0, 0.5, 0), dark, 0.08),
      paint(place(new THREE.SphereGeometry(0.2, 12, 8).scale(0.7, 0.8, 0.9), 0, 0.5, 0.32), pale, 0.05),
      paint(place(new THREE.SphereGeometry(0.14, 12, 8).scale(0.9, 0.95, 1.1), 0, 0.72, 0.58), dark),
      paint(place(new THREE.SphereGeometry(0.07, 10, 8).scale(0.9, 0.8, 1.4), 0, 0.68, 0.74), pale),
      paint(place(new THREE.ConeGeometry(0.035, 0.05, 6), 0, 0.69, 0.82).rotateX(Math.PI / 2), 0x151514),
    ];
    for (const sx of [-1, 1]) {
      parts.push(paint(place(new THREE.ConeGeometry(0.05, 0.14, 6).rotateX(-0.4).rotateZ(sx * 0.4), sx * 0.1, 0.84, 0.55), dark));
      for (const sz of [-1, 1]) parts.push(paint(place(new THREE.CylinderGeometry(0.036, 0.04, 0.36, 8), sx * 0.1, 0.18, sz * 0.26), pale));
    }
    parts.push(paint(place(new THREE.ConeGeometry(0.05, 0.42, 8).rotateX(-2.2), 0, 0.5, -0.55), dark));
    return mergeGeometries(parts);
  })();
  kit.dog = (scale = 1) => {
    const g = new THREE.Group();
    g.add(mesh(dogGeo, M.animal));
    g.scale.setScalar(scale);
    return g;
  };

  return kit;
}
