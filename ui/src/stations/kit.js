// Shared parts for the station models: materials, soft shapes, sheep, a dog, a platform.
// Everything is made in code. No file is loaded, so the page needs no network.
import * as THREE from 'three';
import { mergeGeometries, mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';
import { grain } from '../world/surface.js';
import { boulderGeometry, slabGeometry } from '../world/rockgeo.js';

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
  // a stone: one of six shared boulders (fine for the bigger ones, coarser for pebbles), scaled and turned
  const ROCKS = Array.from({ length: 6 }, (_, i) => boulderGeometry(i + 1, 4));
  const PEBBLES = Array.from({ length: 6 }, (_, i) => boulderGeometry(i + 21, 3));
  kit.rock = (r, mat, x, y, z, seed = 1, sx = 1.15, sy = 0.75, sz = 1) => {
    const set = r >= 0.3 ? ROCKS : PEBBLES;
    const m = mesh(set[Math.abs(Math.floor(seed)) % 6], mat, x, y, z);
    m.scale.set(r * sx, r * sy, r * sz);
    m.rotation.y = seed * 2.1;
    return m;
  };
  // a drystone wall along a polyline of [x, z] points: courses of separate flat stones of different length and height,
  // laid with broken joints, a little batter (narrower at the top), and a row of upright cope stones on top
  const SLABS = Array.from({ length: 8 }, (_, i) => slabGeometry(i + 1));
  kit.wall = (pts, h = 0.9, t = 0.55, seed = 1) => {
    const g = new THREE.Group();
    for (let i = 0; i < pts.length - 1; i++) {
      const [x0, z0] = pts[i], [x1, z1] = pts[i + 1];
      const len = Math.hypot(x1 - x0, z1 - z0), dir = Math.atan2(x1 - x0, z1 - z0);
      const ux = (x1 - x0) / len, uz = (z1 - z0) / len;
      const lay = (along, y, sl, sh, depth, k, upright = false) => {
        const st = mesh(SLABS[Math.floor(hash(k, i, seed) * 8)], hash(k, seed, 3) > 0.45 ? M.stone : M.stoneDark);
        const side = (hash(k, i, 7) - 0.5) * 0.05;
        st.position.set(x0 + ux * along - uz * side, y, z0 + uz * along + ux * side);
        st.scale.set(depth, sh, sl);
        st.rotation.set((hash(k, 2, seed) - 0.5) * 0.12, dir + (hash(k, 5, seed) - 0.5) * 0.1, (hash(k, 9, seed) - 0.5) * (upright ? 0.3 : 0.08));
        g.add(st);
      };
      let y = 0, row = 0, k = 0;
      const courseTop = h - 0.2;
      while (y < courseTop) {
        const sh = Math.min(courseTop - y, 0.13 + hash(row, i, seed) * 0.11);
        const depth = t * (1 - 0.25 * (y / h)); // the batter
        let a = row % 2 ? -0.12 - hash(row, 1, seed) * 0.12 : 0;
        while (a < len) {
          const sl = 0.26 + hash(k, row, seed) * 0.34;
          const c = Math.min(len - 0.02, a + sl / 2);
          if (c > 0.02) lay(c, y + sh / 2, Math.min(sl, (len - a) * 2), sh * 1.05, depth * (0.9 + hash(k, 4, seed) * 0.15), k++);
          a += sl * 0.96;
        }
        y += sh * 0.96;
        row++;
      }
      // the cope: stones on edge across the top
      for (let a = 0.08; a < len - 0.04; a += 0.17 + hash(a * 10, i, seed) * 0.06) {
        lay(a, y + 0.12, 0.13 + hash(a * 7, 3, seed) * 0.05, 0.26 + hash(a * 9, 1, seed) * 0.08, t * 0.72, k++, true);
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

  // ---- Animals (12.R20.4): shaped like the real ones, still, made of smooth parts. A body is a lathe turned along z, legs
  // have two parts and a hoof or paw, heads sit on a pivot so they can bow. The flock mixes the sheep kept in Kenya (the
  // Dorper, white with a black head, and the Red Maasai, red brown and fat tailed) with goats (lean, horned, tail up).
  const lathe = (profile, seg = 18) => new THREE.LatheGeometry(profile.map(([r, y]) => new THREE.Vector2(r, y)), seg);
  const along = (geo) => geo.rotateX(Math.PI / 2); // a lathe made along y, laid along +z (the head end)
  const ellip = (r, sx, sy, sz, ws = 14, hs = 10) => new THREE.SphereGeometry(r, ws, hs).scale(sx, sy, sz);
  const leg = (parts, x, z, hip, len, top, bottom, hoof, col, hoofCol) => {
    const upper = new THREE.CylinderGeometry(top * 0.8, top, len * 0.5, 8).translate(x, hip - len * 0.25, z);
    const lower = new THREE.CylinderGeometry(bottom, top * 0.75, len * 0.5, 8).translate(x, hip - len * 0.75, z + 0.01);
    parts.push(paint(upper, col, 0.05), paint(lower, col, 0.05), paint(new THREE.CylinderGeometry(bottom * 1.1, hoof, 0.05, 8).translate(x, 0.025, z + 0.01), hoofCol));
  };
  const ANIMAL = {
    dorper: { body: 0xd6cdb8, head: 0x1c1b19, len: 0.95, girth: 0.3, hip: 0.4, legLen: 0.4, tail: 'short', ears: 'flat' },
    redmaasai: { body: 0x6a3a22, head: 0x5a3220, len: 0.9, girth: 0.27, hip: 0.42, legLen: 0.42, tail: 'fat', ears: 'flat' },
    goat: { body: 0x3d2f25, head: 0x3d2f25, patch: 0xb9ae98, len: 0.82, girth: 0.22, hip: 0.5, legLen: 0.5, tail: 'up', ears: 'down', horns: true, beard: true },
  };
  function animalGeo(kind) {
    const A = ANIMAL[kind], L = A.len, G = A.girth, body = [], head = [];
    const by = A.hip + G * 0.55; // the body's centre line
    const b = along(lathe([[0.001, -L / 2], [G * 0.55, -L / 2 + 0.06], [G * 0.92, -L * 0.28], [G, 0], [G * 0.95, L * 0.25], [G * 0.7, L / 2 - 0.05], [0.001, L / 2]]));
    b.scale(1, 1.08, 1).translate(0, by, 0);
    body.push(paint(b, A.body, kind === 'dorper' ? 0.14 : 0.08));
    if (A.patch) body.push(paint(ellip(G * 0.8, 1.05, 0.8, 1.2).translate(0.03, by - 0.02, -L * 0.12), A.patch, 0.08));
    // the neck rises forward to the head pivot
    const neck = new THREE.CylinderGeometry(G * 0.32, G * 0.5, 0.36, 10).rotateX(-0.75).translate(0, by + 0.14, L / 2 - 0.02);
    body.push(paint(neck, kind === 'dorper' ? A.head : A.body, 0.06));
    for (const sx of [-1, 1]) for (const [sz, k] of [[L * 0.32, 1], [-L * 0.32, 1.1]]) leg(body, sx * G * 0.5, sz, A.hip + 0.04, A.legLen + 0.04, 0.045 * k, 0.022, 0.026, kind === 'dorper' ? 0xcfc6b2 : A.body, 0x161412);
    if (A.tail === 'fat') body.push(paint(ellip(0.1, 1.1, 1.3, 0.7).translate(0, by - 0.06, -L / 2 - 0.02), A.body, 0.05));
    if (A.tail === 'short') body.push(paint(ellip(0.05, 1, 1.6, 0.8).translate(0, by - 0.05, -L / 2 - 0.01), A.body));
    if (A.tail === 'up') body.push(paint(new THREE.ConeGeometry(0.03, 0.16, 6).rotateX(-0.5).translate(0, by + 0.1, -L / 2 + 0.01), A.body));
    // the head, in the pivot's frame: the skull, a narrower muzzle, ears, and for the goat horns and a beard
    head.push(paint(ellip(0.12, 0.8, 0.85, 1.0).translate(0, 0.02, 0.05), A.head, 0.06));
    head.push(paint(ellip(0.08, 0.75, 0.75, 1.25).translate(0, -0.04, 0.17), A.head, 0.06));
    head.push(paint(ellip(0.012, 1, 1, 1).translate(0, -0.05, 0.27), 0x0c0b0a));
    for (const sx of [-1, 1]) {
      const ear = ellip(0.06, 1.5, 0.28, 0.65).rotateZ(sx * (A.ears === 'down' ? 1.05 : 0.3)).translate(sx * 0.11, A.ears === 'down' ? -0.01 : 0.05, 0.02);
      head.push(paint(ear, A.head));
      head.push(paint(ellip(0.016, 1, 1, 0.6).translate(sx * 0.075, 0.04, 0.12), 0x0a0908)); // the eye, as shape
      if (A.horns) {
        const curve = new THREE.CatmullRomCurve3([new THREE.Vector3(sx * 0.04, 0.09, 0.04), new THREE.Vector3(sx * 0.07, 0.19, -0.03), new THREE.Vector3(sx * 0.1, 0.22, -0.13), new THREE.Vector3(sx * 0.12, 0.17, -0.2)]);
        head.push(paint(new THREE.TubeGeometry(curve, 10, 0.016, 6).toNonIndexed(), 0x6b604e, 0.1));
      }
    }
    if (A.beard) head.push(paint(new THREE.ConeGeometry(0.025, 0.09, 6).rotateX(Math.PI).translate(0, -0.11, 0.2), 0x2a221b));
    return { body: mergeGeometries(body.map((g) => (g.index ? g.toNonIndexed() : g))), head: mergeGeometries(head.map((g) => (g.index ? g.toNonIndexed() : g))), pivot: [0, by + 0.3, L / 2 + 0.1] };
  }
  const GEO = Object.fromEntries(Object.keys(ANIMAL).map((k) => [k, animalGeo(k)]));
  const animal = (kind, scale) => {
    const geo = GEO[kind], g = new THREE.Group();
    g.add(mesh(geo.body, M.animal));
    const head = new THREE.Group();
    head.position.set(...geo.pivot);
    head.add(mesh(geo.head, M.animal));
    g.add(head);
    g.scale.setScalar(scale);
    g.userData.kind = kind;
    return { group: g, head };
  };
  // the flock: each call takes the next kind in a fixed, mixed order, so a station's group is a mixed flock
  const FLOCK = ['dorper', 'goat', 'redmaasai', 'dorper', 'goat', 'redmaasai', 'goat'];
  let flockIndex = 0;
  kit.sheep = (scale = 1) => animal(FLOCK[flockIndex++ % FLOCK.length], scale);
  kit.animal = animal;

  // A herding dog with real proportions: a deep chest, a tucked waist, long legs, a long muzzle, ears half up, a low plumed
  // tail. A dark coat with pale chest, muzzle and feet.
  const dogGeo = (() => {
    const dark = 0x1d1c1a, pale = 0xa29c8c, parts = [];
    const b = along(lathe([[0.001, -0.38], [0.11, -0.34], [0.14, -0.15], [0.16, 0.06], [0.19, 0.22], [0.15, 0.36], [0.001, 0.42]]));
    b.scale(0.9, 1.05, 1).translate(0, 0.52, 0);
    parts.push(paint(b, dark, 0.06));
    parts.push(paint(ellip(0.13, 0.85, 1.1, 0.8).translate(0, 0.47, 0.27), pale, 0.05)); // the chest
    parts.push(paint(new THREE.CylinderGeometry(0.075, 0.11, 0.26, 10).rotateX(-0.6).translate(0, 0.68, 0.38), dark)); // the neck
    parts.push(paint(ellip(0.1, 0.85, 0.85, 1.0).translate(0, 0.8, 0.47), dark, 0.05)); // the skull
    parts.push(paint(ellip(0.055, 0.8, 0.7, 1.9).translate(0, 0.76, 0.6), pale, 0.04)); // the muzzle
    parts.push(paint(ellip(0.022, 1, 0.8, 1).translate(0, 0.765, 0.7), 0x0d0c0b)); // the nose
    for (const sx of [-1, 1]) {
      parts.push(paint(new THREE.ConeGeometry(0.04, 0.11, 6).rotateX(-0.25).rotateZ(sx * 0.45).translate(sx * 0.065, 0.89, 0.44), dark));
      for (const [sz, k] of [[0.22, 1], [-0.25, 1.15]]) leg(parts, sx * 0.075, sz, 0.48, 0.46, 0.04 * k, 0.022, 0.03, sz > 0 ? pale : dark, pale);
    }
    const tail = new THREE.CatmullRomCurve3([new THREE.Vector3(0, 0.55, -0.36), new THREE.Vector3(0, 0.42, -0.5), new THREE.Vector3(0, 0.3, -0.56), new THREE.Vector3(0, 0.24, -0.5)]);
    parts.push(paint(new THREE.TubeGeometry(tail, 10, 0.04, 7).toNonIndexed(), dark, 0.05));
    return mergeGeometries(parts.map((g) => (g.index ? g.toNonIndexed() : g)));
  })();
  kit.dog = (scale = 1) => {
    const g = new THREE.Group();
    g.add(mesh(dogGeo, M.animal));
    g.scale.setScalar(scale);
    return g;
  };

  return kit;
}
