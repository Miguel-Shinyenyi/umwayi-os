// The High figures (12.R16.3, 12.R20.3 to 12.R20.5): a finer Maasai shepherd, a short coat on the sheep and goats, distant
// black kites and an impala. The shepherd stays a plain, respectful figure: a shuka with folds wrapped over one shoulder, the
// staff in his hand, a beaded collar only as a shape, no face detail. The sheep of Kenya (Dorper, Red Maasai) are hair sheep, so
// the coat is short hair, not wool.
import * as THREE from 'three';
import { mergeGeometries, mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';
import { fbm } from '../world/noise.js';

const V2 = (pts) => pts.map(([r, y]) => new THREE.Vector2(r, y));

// a lathe with folds: the radius changes round the figure (folds that fade towards the top) and the hem is not level
function foldedLathe(profile, { seg = 72, folds = 9, depth = 0.05, hem = 0.03, seed = 1 } = {}) {
  const g = new THREE.LatheGeometry(V2(profile), seg);
  const p = g.attributes.position;
  const y0 = profile[0][1], y1 = profile[profile.length - 1][1];
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i), y = p.getY(i), z = p.getZ(i), a = Math.atan2(z, x), r = Math.hypot(x, z);
    if (r < 1e-4) continue;
    const low = 1 - (y - y0) / (y1 - y0); // 1 at the hem, 0 at the top
    const k = 1 + depth * low * (Math.sin(a * folds + seed) * 0.7 + Math.sin(a * folds * 2.3 + seed * 2) * 0.3) + 0.02 * (fbm(a * 2 + seed, y * 6, 2) - 0.5);
    p.setXYZ(i, x * k, y - (low > 0.97 ? hem * (0.5 + 0.5 * Math.sin(a * 3 + seed)) : 0), z * k);
  }
  g.computeVertexNormals();
  return g;
}
// a limb between two points, tapered, with round ends
function limb(a, b, ra, rb, seg = 14) {
  const d = new THREE.Vector3().subVectors(b, a), len = d.length();
  // a capsule of radius 1 and length 1 turned on a lathe (three.js's CapsuleGeometry is not used: see assets.js)
  const prof = [];
  for (let k = 0; k <= 4; k++) { const a = -Math.PI / 2 + (k / 4) * (Math.PI / 2); prof.push(new THREE.Vector2(Math.cos(a), -0.5 + Math.sin(a))); }
  for (let k = 0; k <= 4; k++) { const a = (k / 4) * (Math.PI / 2); prof.push(new THREE.Vector2(Math.cos(a), 0.5 + Math.sin(a))); }
  const g = new THREE.LatheGeometry(prof, seg);
  // reshape the capsule into a taper from ra at a to rb at b
  const p = g.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const y = p.getY(i); // -1.5 .. 1.5 for a capsule of radius 1 and length 1
    const t = Math.min(1, Math.max(0, (y + 1.5) / 3));
    const r = ra + (rb - ra) * t;
    p.setXYZ(i, p.getX(i) * r, t * len, p.getZ(i) * r);
  }
  g.computeVertexNormals();
  const m = new THREE.Mesh(g);
  m.position.copy(a);
  m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.normalize());
  return m;
}

export function buildHighShepherd() {
  const g = new THREE.Group();
  g.name = 'high:shepherd';
  const skin = new THREE.MeshStandardMaterial({ color: 0x140e0b, roughness: 0.55 });
  const shuka = new THREE.MeshStandardMaterial({ color: 0x601812, roughness: 0.95, side: THREE.DoubleSide });
  const shuka2 = new THREE.MeshStandardMaterial({ color: 0x3c1e3a, roughness: 0.95, side: THREE.DoubleSide });
  const beadMats = [0x4a3a2a, 0x3a2620, 0x2e3438].map((c) => new THREE.MeshStandardMaterial({ color: c, roughness: 0.6 }));
  const sole = new THREE.MeshStandardMaterial({ color: 0x15100c, roughness: 0.9 });
  const add = (m, mat) => { m.material = mat; m.castShadow = m.receiveShadow = true; g.add(m); return m; };
  // legs: ankle, calf, knee and thigh, a little apart, the weight on the left
  for (const sx of [-1, 1]) {
    const leg = new THREE.Mesh(new THREE.LatheGeometry(V2([[0.0, 0.03], [0.033, 0.035], [0.03, 0.09], [0.05, 0.25], [0.054, 0.31], [0.04, 0.45], [0.046, 0.5], [0.058, 0.6], [0.0, 0.62]]), 16));
    leg.position.set(sx * 0.075, 0, sx * 0.01);
    leg.rotation.z = sx * 0.03;
    add(leg, skin);
    const foot = new THREE.Mesh(new THREE.SphereGeometry(0.05, 14, 8).scale(0.75, 0.32, 1.9));
    foot.position.set(sx * 0.078, 0.015, 0.045);
    add(foot, sole);
  }
  // the shuka: from the chest to below the knee, with folds and an uneven hem
  const cloth = add(new THREE.Mesh(foldedLathe([[0.0, 0.4], [0.205, 0.4], [0.215, 0.47], [0.2, 0.72], [0.18, 1.0], [0.172, 1.2], [0.155, 1.32], [0.1, 1.38], [0.0, 1.39]], { folds: 9, depth: 0.06, seed: 1 })), shuka);
  cloth.scale.set(1, 1, 0.78);
  // the second cloth, tied over the left shoulder, falling to the hip
  const drape = add(new THREE.Mesh(foldedLathe([[0.0, 0.95], [0.185, 0.96], [0.2, 1.1], [0.19, 1.28], [0.155, 1.44], [0.075, 1.5], [0.0, 1.51]], { folds: 7, depth: 0.07, hem: 0.05, seed: 4 })), shuka2);
  drape.scale.set(1.06, 1, 0.82);
  drape.rotation.z = 0.12;
  // the knot on the left shoulder and the edge of the cloth across the chest
  const knot = add(new THREE.Mesh(new THREE.SphereGeometry(0.045, 14, 10).scale(1, 0.8, 1)), shuka2);
  knot.position.set(-0.13, 1.47, 0.02);
  const edge = new THREE.CatmullRomCurve3([new THREE.Vector3(-0.13, 1.47, 0.07), new THREE.Vector3(0.0, 1.3, 0.15), new THREE.Vector3(0.12, 1.12, 0.14), new THREE.Vector3(0.17, 0.98, 0.1)]);
  add(new THREE.Mesh(new THREE.TubeGeometry(edge, 20, 0.014, 8)), shuka2);
  // the bare right shoulder and arm, the hand round the staff
  const sh = add(new THREE.Mesh(new THREE.SphereGeometry(0.075, 18, 12).scale(1, 0.9, 0.95)), skin);
  sh.position.set(0.165, 1.43, 0.0);
  add(limb(new THREE.Vector3(0.18, 1.42, 0.01), new THREE.Vector3(0.31, 1.2, 0.06), 0.043, 0.036), skin);
  add(limb(new THREE.Vector3(0.31, 1.2, 0.06), new THREE.Vector3(0.43, 1.26, 0.12), 0.036, 0.028), skin);
  const hand = add(new THREE.Mesh(new THREE.SphereGeometry(0.035, 14, 10).scale(1, 1.25, 0.9)), skin);
  hand.position.set(0.445, 1.27, 0.12);
  // the left hand shows below the drape, at the hip
  const lhand = add(new THREE.Mesh(new THREE.SphereGeometry(0.032, 12, 8).scale(0.9, 1.3, 0.9)), skin);
  lhand.position.set(-0.2, 0.98, 0.02);
  // the neck, the beaded collar as three flat rings (a shape, no pattern), the head with no face detail
  const neck = add(new THREE.Mesh(new THREE.CylinderGeometry(0.043, 0.052, 0.15, 16)), skin);
  neck.position.y = 1.555;
  [[0.12, 1.515], [0.145, 1.5], [0.17, 1.485]].forEach(([r, y], i) => {
    const ring = add(new THREE.Mesh(new THREE.TorusGeometry(r, 0.011, 8, 40).rotateX(Math.PI / 2)), beadMats[i]);
    ring.position.y = y;
    ring.scale.set(1, 1, 0.85);
  });
  const skull = add(new THREE.Mesh(new THREE.SphereGeometry(0.098, 28, 20).scale(0.9, 1.12, 1.02)), skin);
  skull.position.set(0, 1.71, -0.005);
  const jaw = add(new THREE.Mesh(new THREE.SphereGeometry(0.07, 20, 14).scale(0.95, 0.85, 1.0)), skin);
  jaw.position.set(0, 1.645, 0.03);
  for (const sx of [-1, 1]) {
    const ear = add(new THREE.Mesh(new THREE.SphereGeometry(0.022, 10, 8).scale(0.45, 1.2, 0.9)), skin);
    ear.position.set(sx * 0.088, 1.7, -0.005);
  }
  return g;
}

// A short coat for a sheep or goat: a shell just over the barrel of the body, with a fine grain of hair. (No sheen: three.js's
// MeshPhysicalMaterial would be kept in the copy of three.js that Standard visitors download; see assets.js.)
const COAT = {
  dorper: { len: 0.95, girth: 0.3, hip: 0.4, color: 0xd6cdb8 },
  redmaasai: { len: 0.9, girth: 0.27, hip: 0.42, color: 0x6a3a22 },
  goat: { len: 0.82, girth: 0.22, hip: 0.5, color: 0x3d2f25 },
};
// the barrel of the body with the shape of a real animal: shoulders and hips fuller than the waist, a straight back line, the
// belly lower behind the ribs; and a coat coloured with the small changes of real hair (darker along the back, paler below)
const coatGeometry = (kind) => {
  const A = COAT[kind], by = A.hip + A.girth * 0.55;
  const g = new THREE.IcosahedronGeometry(1, 5);
  g.deleteAttribute('uv'); g.deleteAttribute('normal');
  const p = g.attributes.position, col = [], base = new THREE.Color(A.color), c = new THREE.Color();
  for (let i = 0; i < p.count; i++) {
    let x = p.getX(i), y = p.getY(i), z = p.getZ(i);
    const shoulders = Math.exp(-((z - 0.45) ** 2) / 0.06), hips = Math.exp(-((z + 0.5) ** 2) / 0.07), waist = Math.exp(-((z + 0.05) ** 2) / 0.08);
    const girth = 1 + 0.07 * shoulders + 0.09 * hips - 0.06 * waist;
    if (y > 0.55) y = 0.55 + (y - 0.55) * 0.55; // a straighter top line
    if (y < 0) y *= 1 + 0.12 * Math.exp(-((z - 0.1) ** 2) / 0.1); // the belly, deepest behind the ribs
    const hair = 1 + 0.03 * (fbm(x * 14 + z * 4, y * 14 + z * 9, 3) - 0.5);
    p.setXYZ(i, x * A.girth * 1.06 * girth * hair, y * A.girth * 1.12 * hair + by, z * A.len * 0.44 - 0.01);
    const shade = 1 - 0.18 * Math.max(0, y) + 0.12 * Math.max(0, -y) + 0.12 * (fbm(x * 5 + 3, z * 6 + y * 4, 3) - 0.5);
    c.copy(base).multiplyScalar(shade);
    col.push(c.r, c.g, c.b);
  }
  g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
  const m = mergeVertices(g, 1e-5);
  m.computeVertexNormals();
  return m;
};
let coatCache = null;
export function makeCoat(kind) {
  if (!COAT[kind]) return null;
  coatCache ||= Object.fromEntries(Object.keys(COAT).map((k) => [k, {
    geo: coatGeometry(k),
    mat: new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 1 }),
  }]));
  const m = new THREE.Mesh(coatCache[kind].geo, coatCache[kind].mat);
  m.castShadow = m.receiveShadow = true;
  m.name = 'high:coat';
  return m;
}
export function disposeCoats() {
  if (!coatCache) return;
  for (const c of Object.values(coatCache)) { c.geo.dispose(); c.mat.dispose(); }
  coatCache = null;
}

// A black kite seen far off: a slim body, a forked tail, long wings bent at the wrist. Two wing pivots for the beat.
export function buildBird(mat) {
  const g = new THREE.Group();
  const body = new THREE.Mesh(new THREE.SphereGeometry(0.1, 12, 8).scale(0.75, 0.7, 2.6), mat);
  const tail = new THREE.Mesh(new THREE.ConeGeometry(0.09, 0.3, 4).rotateX(-Math.PI / 2).scale(1.6, 0.25, 1), mat);
  tail.position.z = -0.32;
  g.add(body, tail);
  // the wing outline as a strip between its front and back edge, meeting at the tip (no three.js Shape: see assets.js)
  const front = [[0, 0.1], [0.35, 0.14], [0.62, 0.06]], back = [[0, -0.12], [0.4, -0.1], [0.8, -0.12]], tip = [0.9, -0.05];
  const tri = [];
  for (let i = 0; i < 2; i++) tri.push(back[i], front[i + 1], front[i], back[i], back[i + 1], front[i + 1]); // counter clockwise, facing +z as a Shape did
  tri.push(back[2], tip, front[2]);
  const wingGeo = new THREE.BufferGeometry();
  wingGeo.setAttribute('position', new THREE.Float32BufferAttribute(tri.flatMap(([x, y]) => [x, y, 0]), 3));
  wingGeo.computeVertexNormals();
  wingGeo.rotateX(-Math.PI / 2);
  for (const sx of [-1, 1]) {
    const pivot = new THREE.Group();
    const w = new THREE.Mesh(wingGeo, mat);
    w.scale.x = sx;
    pivot.add(w);
    pivot.position.set(sx * 0.04, 0.02, 0.04);
    pivot.userData.side = sx;
    g.add(pivot);
  }
  g.userData.wings = g.children.filter((c) => c.userData.side);
  return g;
}

// An impala, about 0.85 m at the shoulder: a red brown back, paler flanks and a white belly, lyre shaped horns, slim legs with
// a pivot at each hip and shoulder so they swing as it walks, and a neck pivot so it lowers its head to graze.
export function buildAntelope() {
  const g = new THREE.Group();
  g.name = 'high:antelope';
  const coat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.9 });
  const dark = new THREE.MeshStandardMaterial({ color: 0x1a120d, roughness: 0.8 });
  // the body along z, coloured by height: the back red brown, the belly pale
  const body = new THREE.LatheGeometry(V2([[0.001, -0.55], [0.12, -0.5], [0.2, -0.3], [0.215, -0.05], [0.2, 0.2], [0.17, 0.42], [0.11, 0.55], [0.001, 0.58]]), 24).rotateX(Math.PI / 2);
  body.scale(0.85, 1.05, 1).translate(0, 0.86, 0);
  const paint = (geo) => {
    const p = geo.attributes.position, col = [];
    const top = new THREE.Color(0x7a4424), side = new THREE.Color(0x9a6a44), belly = new THREE.Color(0xd8cfc0), c = new THREE.Color();
    for (let i = 0; i < p.count; i++) {
      const y = p.getY(i) - 0.86;
      if (y > 0.04) c.copy(top); else if (y > -0.11) c.copy(top).lerp(side, (0.04 - y) / 0.15); else c.copy(side).lerp(belly, Math.min(1, (-0.11 - y) / 0.06));
      col.push(c.r, c.g, c.b);
    }
    geo.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
    return geo;
  };
  g.add(new THREE.Mesh(paint(body), coat));
  const tail = new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.03, 0.26, 8).rotateX(0.35), dark);
  tail.position.set(0, 0.8, -0.6);
  g.add(tail);
  // neck and head on a pivot at the withers
  const neck = new THREE.Group();
  neck.position.set(0, 0.98, 0.42);
  const neckMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.1, 0.48, 12).translate(0, 0.24, 0).rotateX(0.55), new THREE.MeshStandardMaterial({ color: 0x8a5634, roughness: 0.9 }));
  neck.add(neckMesh);
  const head = new THREE.Group();
  head.position.set(0, 0.42, 0.25);
  head.add(new THREE.Mesh(new THREE.SphereGeometry(0.075, 16, 12).scale(0.8, 0.85, 1.0), neckMesh.material));
  const muzzle = new THREE.Mesh(new THREE.SphereGeometry(0.05, 14, 10).scale(0.75, 0.75, 1.8), neckMesh.material);
  muzzle.position.set(0, -0.04, 0.1);
  head.add(muzzle);
  for (const sx of [-1, 1]) {
    const ear = new THREE.Mesh(new THREE.SphereGeometry(0.05, 10, 8).scale(0.35, 1.1, 0.25), neckMesh.material);
    ear.position.set(sx * 0.07, 0.07, -0.02);
    ear.rotation.z = sx * 0.6;
    head.add(ear);
    const horn = new THREE.CatmullRomCurve3([new THREE.Vector3(sx * 0.03, 0.06, 0.0), new THREE.Vector3(sx * 0.08, 0.2, -0.08), new THREE.Vector3(sx * 0.05, 0.36, -0.12), new THREE.Vector3(sx * 0.09, 0.48, -0.06)]);
    head.add(new THREE.Mesh(new THREE.TubeGeometry(horn, 14, 0.014, 6), dark));
  }
  neck.add(head);
  g.add(neck);
  // legs: a pivot at each hip and shoulder, an upper and a lower part and a hoof
  const legMat = new THREE.MeshStandardMaterial({ color: 0x8a5a3a, roughness: 0.9 });
  const legs = [];
  for (const [x, z, front] of [[-0.09, 0.36, 1], [0.09, 0.36, 1], [-0.09, -0.36, 0], [0.09, -0.36, 0]]) {
    const pivot = new THREE.Group();
    pivot.position.set(x, 0.8, z);
    const upper = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.024, 0.38, 8).translate(0, -0.19, 0), legMat);
    const lower = new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.014, 0.4, 8).translate(0, -0.2, 0), legMat);
    lower.position.y = -0.38;
    lower.rotation.x = front ? 0.12 : -0.18;
    const hoof = new THREE.Mesh(new THREE.CylinderGeometry(0.016, 0.02, 0.04, 8), dark);
    hoof.position.y = -0.4;
    lower.add(hoof);
    pivot.add(upper, lower);
    pivot.userData = { front, side: x > 0 ? 1 : -1 };
    legs.push(pivot);
    g.add(pivot);
  }
  g.userData = { legs, neck };
  g.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
  return g;
}
