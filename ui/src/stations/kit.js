// Shared parts for the station models: materials, soft shapes, sheep, a dog, a platform.
// Everything is made in code. No file is loaded, so the page needs no network.
import * as THREE from 'three';
import { mergeGeometries, mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';
import { SCENE, TOKENS } from '../world/palette.js';

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

export function makeKit() {
  const glows = [];
  let glowScale = 1;
  const kit = { glows };

  kit.std = (color, o = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.92, metalness: 0, ...o });
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

  const M = {
    stone: kit.std(SCENE.stone), stoneDark: kit.std(SCENE.stoneDark), wood: kit.std(SCENE.wood), woodDark: kit.std(SCENE.woodDark),
    thatch: kit.std(SCENE.thatch), roof: kit.std(SCENE.roof), lawn: kit.std(SCENE.lawn), parchment: kit.std(SCENE.parchment),
    line: kit.std(SCENE.line), metal: kit.std(SCENE.metal, { roughness: 0.55, metalness: 0.4 }),
    animal: new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 1 }),
  };
  kit.M = M;

  const shadow = (o) => {
    o.traverse((c) => {
      if (c.isMesh) {
        c.castShadow = true;
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
  // A post standing on y = 0.
  kit.post = (h, r, mat, x = 0, z = 0) => mesh(new THREE.CylinderGeometry(r * 0.82, r, h, 10).translate(0, h / 2, 0), mat, x, 0, z);
  // A bar between two points.
  kit.beam = (a, b, t, mat) => {
    const d = new THREE.Vector3().subVectors(b, a);
    const m = mesh(new THREE.BoxGeometry(t, t, d.length()), mat);
    m.position.copy(a).addScaledVector(d, 0.5);
    m.lookAt(b);
    return m;
  };
  // A low smooth stone.
  kit.rock = (r, mat, x, y, z, seed = 1) => {
    const g = fluff(r, 2, 0.1, 1.15, 0.72, 1);
    g.rotateY(seed * 2.1);
    return mesh(g, mat, x, y, z);
  };

  // A fence along an arc. Returns a group.
  kit.fenceArc = (cx, cz, r, a0, a1, n, h = 0.5, mat = M.wood) => {
    const g = new THREE.Group();
    const pts = [];
    for (let i = 0; i < n; i++) {
      const a = a0 + ((a1 - a0) * i) / (n - 1);
      pts.push(new THREE.Vector3(cx + Math.cos(a) * r, 0, cz + Math.sin(a) * r));
      g.add(kit.post(h, 0.045, mat, pts[i].x, pts[i].z));
    }
    for (let i = 0; i < n - 1; i++) {
      for (const y of [h * 0.55, h * 0.9]) {
        g.add(kit.beam(pts[i].clone().setY(y), pts[i + 1].clone().setY(y), 0.03, mat));
      }
    }
    return g;
  };

  // A platform the station stands on: dark stone, a mossy top and a faint rim of light (decoration, not a signal).
  const rimMat = kit.glow(SCENE.rim, 0.16);
  kit.platform = () => {
    const g = new THREE.Group();
    g.add(kit.cyl(2.5, 2.66, 0.22, M.stoneDark, 0, 0.11, 0, 56));
    g.add(kit.cyl(2.34, 2.34, 0.04, M.lawn, 0, 0.24, 0, 56));
    const rim = new THREE.Mesh(new THREE.TorusGeometry(2.43, 0.016, 6, 96), rimMat);
    rim.rotation.x = Math.PI / 2;
    rim.position.y = 0.245;
    g.add(rim);
    return g;
  };
  kit.PLATFORM_TOP = 0.26;

  // A lantern on a post. lamp is the lit part (its colour can change).
  kit.lantern = (h = 1.5, base = 2.2) => {
    const g = new THREE.Group();
    g.add(kit.post(h, 0.045, M.metal));
    const lamp = kit.glow(TOKENS.amber, base);
    g.add(kit.mesh(new THREE.CylinderGeometry(0.1, 0.075, 0.2, 8), lamp, 0, h + 0.1, 0));
    g.add(kit.mesh(new THREE.ConeGeometry(0.15, 0.1, 8), M.metal, 0, h + 0.25, 0));
    return { group: g, lamp };
  };

  // Sheep: soft wool, a dark head on a pivot so it can bow.
  const sheepGeo = (() => {
    const wool = [
      paint(place(fluff(0.4, 3, 0.07, 1, 0.82, 1.3), 0, 0.52, 0), SCENE.wool, 0.16),
      paint(place(fluff(0.12, 2, 0.05), 0, 0.6, -0.52), SCENE.wool, 0.1),
    ];
    for (const sx of [-1, 1]) for (const sz of [-1, 1]) {
      wool.push(paint(place(new THREE.CylinderGeometry(0.03, 0.036, 0.32, 8), sx * 0.15, 0.16, sz * 0.27), SCENE.skin));
    }
    const head = new THREE.SphereGeometry(0.17, 14, 10).scale(0.82, 0.95, 1.15);
    const parts = [paint(place(head, 0, 0, 0.15), SCENE.skin, 0.1)];
    for (const sx of [-1, 1]) {
      const ear = new THREE.SphereGeometry(0.07, 8, 6).scale(1.3, 0.3, 0.7);
      ear.rotateZ(sx * 0.35);
      parts.push(paint(place(ear, sx * 0.17, 0.08, 0.06), SCENE.skin));
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
