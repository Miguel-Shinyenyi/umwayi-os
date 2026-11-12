// The High plants (12.R16.3): far more grass, in clumps, with finer blades; the forest across the river at its High count with
// finer trees; and the acacias and standalone cedars rebuilt from many small parts in the places the Standard ones stand.
// Every plant keeps clear of every place a station can stand, of the river and of the shepherd, as in Standard.
import * as THREE from 'three';
import { mergeGeometries, mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';
import { heightAt, RIVER_HALF_WIDTH } from '../world/height.js';
import { nearestOnRiver, acrossRiver } from '../world/river.js';
import { reachable, SHEPHERD_SPACE, stationPositions, TABLE } from '../world/layout.js';
import { forestSpots, FOREST_COUNT, NEAR_SIDE_FROM } from '../world/forest.js';
import { overviewShot, cameraPosition } from '../world/shots.js';
import { facingAt } from '../engine/placement.js';
import { ANTELOPE_PATH, ANTELOPE_SCALE } from './wildlife.js';
import { mulberry32 } from '../world/random.js';
import { fbm } from '../world/noise.js';

export const HIGH_GRASS = 48000;
const slopeAt = (x, z) => Math.hypot(heightAt(x + 0.8, z) - heightAt(x - 0.8, z), heightAt(x, z + 0.8) - heightAt(x, z - 0.8)) / 1.6;

// a blade: six rows, narrowing to a point, curving over towards its tip, darker at the root
function bladeGeometry() {
  const h = 0.55, w = 0.055, rows = 6, pos = [], col = [], idx = [];
  for (let i = 0; i <= rows; i++) {
    const t = i / rows, half = (w * (1 - Math.pow(t, 1.4) * 0.96)) / 2 + 0.0008, bend = t * t * 0.2, shade = 0.35 + 0.8 * Math.pow(t, 0.8);
    pos.push(-half, t * h * (1 - 0.12 * t), bend, half, t * h * (1 - 0.12 * t), bend);
    col.push(shade, shade, shade, shade, shade, shade);
    if (i < rows) idx.push(i * 2, i * 2 + 1, i * 2 + 2, i * 2 + 1, i * 2 + 3, i * 2 + 2);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
  geo.setIndex(idx);
  geo.computeVertexNormals();
  return geo;
}

// clumps of blades: a clump centre, then blades leaning out from it, so the grass grows in tussocks as it does on the highlands
export function buildHighGrass(count = HIGH_GRASS) {
  const keep = reachable(), rnd = mulberry32(121);
  const mesh = new THREE.InstancedMesh(bladeGeometry(), new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.92, side: THREE.DoubleSide }), count);
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler(), sc = new THREE.Vector3(), c = new THREE.Color(), v = new THREE.Vector3();
  let n = 0;
  for (let tries = 0; tries < count * 3 && n < count; tries++) {
    const r = 3 + Math.sqrt(rnd()) * 72, a = rnd() * Math.PI * 2;
    const cx = Math.cos(a) * r, cz = Math.sin(a) * r;
    if (rnd() > 1 - Math.min(0.8, r / 110)) continue; // thinner further out
    if (keep.some((k) => Math.hypot(cx - k.x, cz - k.z) < k.r + 0.25)) continue;
    if (nearestOnRiver({ x: cx, z: cz }).distance < RIVER_HALF_WIDTH + 1.4) continue;
    if (Math.hypot(cx, cz) < SHEPHERD_SPACE + 0.6) continue;
    const cy = heightAt(cx, cz);
    if (slopeAt(cx, cz) > 0.6 || cy > 38) continue;
    const dry = fbm(cx * 0.045 + 4, cz * 0.045 + 4, 3) * 1.4;
    const blades = 3 + Math.floor(rnd() * 6), spread = 0.06 + rnd() * 0.12, tall = 0.6 + rnd() * 1.0;
    for (let b = 0; b < blades && n < count; b++) {
      const ba = rnd() * Math.PI * 2, br = Math.sqrt(rnd()) * spread;
      const x = cx + Math.cos(ba) * br, z = cz + Math.sin(ba) * br;
      // lean away from the clump centre
      e.set(Math.cos(ba) * (0.15 + rnd() * 0.35), ba + Math.PI / 2 + (rnd() - 0.5) * 0.8, Math.sin(ba) * (0.15 + rnd() * 0.35));
      q.setFromEuler(e);
      const k = tall * (0.75 + rnd() * 0.5);
      m.compose(v.set(x, heightAt(x, z) - 0.03, z), q, sc.set(0.8 + rnd() * 0.6, k, 1));
      mesh.setMatrixAt(n, m);
      const d = dry + (rnd() - 0.5) * 0.3;
      c.setHSL(d > 0.55 ? 0.1 + rnd() * 0.03 : 0.2 + rnd() * 0.04, d > 0.55 ? 0.45 : 0.32, 0.24 + d * 0.1 + rnd() * 0.06);
      mesh.setColorAt(n, c);
      n++;
    }
  }
  mesh.count = n;
  mesh.userData.total = n;
  mesh.receiveShadow = true;
  mesh.name = 'high:grass';
  return mesh;
}

// a crown part: a sphere of the given detail pushed out by lumps, so it reads as a mass of leaves and not as a ball
function lumpy(detail, amount, seed) {
  const g = new THREE.IcosahedronGeometry(1, detail);
  g.deleteAttribute('uv'); g.deleteAttribute('normal');
  const p = g.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i), y = p.getY(i), z = p.getZ(i);
    const k = 1 + amount * (fbm(x * 2.3 + seed, z * 2.3 + y * 1.7, 3) - 0.5) * 2 + 0.08 * Math.sin(x * 11 + seed) * Math.sin(z * 9 + y * 7);
    p.setXYZ(i, x * k, y * k * (y < 0 ? 0.55 : 1), z * k);
  }
  const m = mergeVertices(g, 1e-4);
  m.computeVertexNormals();
  return m;
}

// a pencil cedar: nine ragged, drooping tiers of foliage on a straight trunk
function highCedarGeometry(seed = 1) {
  const tiers = [], rnd = mulberry32(seed);
  for (let t = 0; t < 9; t++) {
    const rad = 1.55 - t * 0.15, cone = new THREE.ConeGeometry(rad, 1.5, 16, 2, true);
    const p = cone.attributes.position;
    for (let i = 0; i < p.count; i++) {
      const x = p.getX(i), y = p.getY(i), z = p.getZ(i), ang = Math.atan2(z, x);
      const rag = 1 + 0.16 * Math.sin(ang * 7 + t * 1.3) + 0.1 * Math.sin(ang * 13 + t) + (rnd() - 0.5) * 0.12;
      const droop = y < 0 ? -0.18 * Math.hypot(x, z) : 0;
      p.setXYZ(i, x * rag, y + droop, z * rag);
    }
    cone.translate(0, 0.9 + t * 0.85, 0);
    cone.deleteAttribute('uv');
    tiers.push(cone.toNonIndexed());
  }
  const merged = mergeGeometries(tiers);
  merged.computeVertexNormals();
  return merged;
}

// one broadleaf tree: seven lumpy crown parts, as one geometry
function broadleafGeometry() {
  const parts = [[0, 5.6, 0, 2.4, 1.5], [1.6, 5.1, 0.7, 1.7, 1.2], [-1.4, 5.3, -0.8, 1.8, 1.3], [0.3, 6.7, -0.4, 1.6, 1.1], [-0.6, 4.6, 1.3, 1.4, 1.0], [1.1, 4.5, -1.3, 1.3, 0.95], [-1.7, 4.4, 0.6, 1.2, 0.9]];
  const geos = parts.map(([x, y, z, r, h], i) => lumpy(3, 0.32, i * 3.1 + 1).scale(r, h, r).translate(x, y, z).toNonIndexed());
  const merged = mergeGeometries(geos);
  merged.computeVertexNormals();
  return merged;
}

// A tree of spot s stands between the default view and the antelope at p: the sight line passes within its crown while
// below its top (t.r and t.top, or from the forest's size k). Used to keep the younger High trees out of that line (and by the tests).
const VIEW = (() => { const s = overviewShot(1440 / 750); return { x: 0, y: s.ty + s.dist * Math.sin(s.pitch), z: s.tz + s.dist * Math.cos(s.pitch) }; })();
export function blocksAntelope(t, p, cam = VIEW) {
  const top = { x: p.x, y: heightAt(p.x, p.z) + 1.2 * ANTELOPE_SCALE, z: p.z }; // the head, at the drawn size
  const dx = top.x - cam.x, dz = top.z - cam.z, L2 = dx * dx + dz * dz;
  const u = ((t.x - cam.x) * dx + (t.z - cam.z) * dz) / L2;
  if (u <= 0 || u >= 0.98) return false;
  const d = Math.hypot(t.x - cam.x - dx * u, t.z - cam.z - dz * u);
  // the size of a forest tree of either tier: a cedar is about 10.2 k tall and 2 k wide, a broadleaf 8.6 k tall and 3.8 k wide
  const cedar = t.kind === 'cedar';
  const r = t.r ?? (cedar ? 2.0 : 3.8) * t.k + 0.3, high = t.top ?? t.y - 0.2 + (cedar ? 10.2 : 8.6) * t.k;
  return d < r && cam.y + (top.y - cam.y) * u < high;
}

// The view of each station: the line from where the camera stands to the station, for a wide screen and a phone, at every
// place the station can stand. A younger High tree never stands in it, so no station view starts inside a tree.
export function stationViews() {
  const out = [];
  for (const row of TABLE) for (const need of [0, 0.2, 0.4, 0.6, 0.8, 1]) {
    const pos = stationPositions({ [row.id]: need });
    const others = TABLE.map((r) => ({ id: r.id, pos: pos[r.id], footprint: r.footprint }));
    const p = pos[row.id];
    const st = { id: row.id, pos: p, footprint: row.footprint, river: !!row.river, facing: facingAt(row, p.x, p.z) };
    for (const aspect of [1440 / 750, 390 / 700]) {
      const c = cameraPosition(st, aspect, others);
      out.push({ ax: c.x, az: c.z, bx: p.x, bz: p.z });
    }
  }
  return out;
}
const segDist = (x, z, s) => {
  const dx = s.bx - s.ax, dz = s.bz - s.az, l2 = dx * dx + dz * dz || 1;
  const u = Math.min(1, Math.max(0, ((x - s.ax) * dx + (z - s.az) * dz) / l2));
  return Math.hypot(x - s.ax - dx * u, z - s.az - dz * u);
};
export const VIEW_CLEAR = 1.5; // metres kept between a crown and the line of a station view
export const inStationView = (t, views) => views.some((s) => segDist(t.x, t.z, s) < (t.kind === 'cedar' ? 2.0 : 3.8) * t.k + VIEW_CLEAR);

// Where the High forest grows: every Standard tree in its Standard place, then younger trees between them and further up the
// far slope, a little closer together (1.3 m between trunks against 2.1 m), in the same band along the river and lower on the slope, until the High count. Seeded and fixed, clear of every
// place a station can stand, of the river and of the lantern side close in, like the Standard forest.
export function highForestSpots(count = FOREST_COUNT.high) {
  const base = forestSpots();
  const out = base.slice(), keep = reachable(), views = stationViews(), rnd = mulberry32(161), APART = 1.3;
  const grid = new Map(), cell = 2;
  const key = (x, z) => `${Math.floor(x / cell)},${Math.floor(z / cell)}`;
  const put = (o) => { const k = key(o.x, o.z); if (!grid.has(k)) grid.set(k, []); grid.get(k).push(o); };
  const near = (x, z) => {
    const cx = Math.floor(x / cell), cz = Math.floor(z / cell);
    for (let i = -1; i <= 1; i++) for (let j = -1; j <= 1; j++) for (const o of grid.get(`${cx + i},${cz + j}`) || []) if (Math.hypot(x - o.x, z - o.z) < APART) return true;
    return false;
  };
  base.forEach(put);
  for (let t = 0; t < count * 80 && out.length < count; t++) {
    const x = (rnd() - 0.5) * 220, z = (rnd() - 0.5) * 220, r = Math.hypot(x, z);
    if (r > 105) continue;
    const dr = nearestOnRiver({ x, z }).distance;
    if (dr < RIVER_HALF_WIDTH + 1.8 || dr > 28) continue; // no further from the river than the Standard band, so the hills above stay open
    const across = acrossRiver({ x, z });
    if (!across && (r < NEAR_SIDE_FROM || dr > 18)) continue;
    if (rnd() > 1.15 - dr / 60) continue;
    if (keep.some((k) => Math.hypot(x - k.x, z - k.z) < k.r + 1.6)) continue;
    const y = heightAt(x, z);
    if (y > 12 + 4 * rnd()) continue; // lower than the Standard trees reach: the hills above, Mount Kenya and the ridge still show
    if (near(x, z)) continue;
    const o = { x, z, y, kind: rnd() < 0.55 ? 'cedar' : 'broadleaf', k: 0.55 + rnd() * 0.6, turn: rnd() * Math.PI * 2, tone: rnd() };
    if (ANTELOPE_PATH.some((p) => blocksAntelope(o, p)) || inStationView(o, views)) continue;
    out.push(o);
    put(o);
  }
  return out;
}

const foliageMaterial = () => new THREE.MeshStandardMaterial({ roughness: 0.95, side: THREE.DoubleSide });

export function buildHighForest() {
  const spots = highForestSpots();
  const g = new THREE.Group();
  g.name = 'high:forest';
  const cedars = spots.filter((s) => s.kind === 'cedar'), broad = spots.filter((s) => s.kind === 'broadleaf');
  const cedar = new THREE.InstancedMesh(highCedarGeometry(3), foliageMaterial(), cedars.length);
  const crowns = new THREE.InstancedMesh(broadleafGeometry(), foliageMaterial(), broad.length);
  const trunkGeo = new THREE.CylinderGeometry(0.12, 0.3, 4.4, 9, 3).translate(0, 2.2, 0);
  const tp = trunkGeo.attributes.position;
  for (let i = 0; i < tp.count; i++) tp.setX(i, tp.getX(i) + 0.05 * Math.sin(tp.getY(i) * 1.7)); // trunks are never quite straight
  trunkGeo.computeVertexNormals();
  const trunks = new THREE.InstancedMesh(trunkGeo, new THREE.MeshStandardMaterial({ color: 0x231912, roughness: 1 }), spots.length);
  trunks.name = 'high:trunks';
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), sc = new THREE.Vector3(), c = new THREE.Color(), up = new THREE.Vector3(0, 1, 0), v = new THREE.Vector3();
  cedars.forEach((s, i) => {
    q.setFromAxisAngle(up, s.turn);
    m.compose(v.set(s.x, s.y - 0.2, s.z), q, sc.set(s.k * 0.95, s.k * 1.2, s.k * 0.95));
    cedar.setMatrixAt(i, m);
    c.setHSL(0.36 + s.tone * 0.08, 0.27, 0.07 + s.tone * 0.045);
    cedar.setColorAt(i, c);
  });
  broad.forEach((s, i) => {
    q.setFromAxisAngle(up, s.turn);
    m.compose(v.set(s.x, s.y - 0.2, s.z), q, sc.setScalar(s.k * 1.1));
    crowns.setMatrixAt(i, m);
    c.setHSL(0.2 + s.tone * 0.07, 0.3, 0.07 + s.tone * 0.045);
    crowns.setColorAt(i, c);
  });
  spots.forEach((s, i) => {
    q.setFromAxisAngle(up, s.turn);
    m.compose(v.set(s.x, s.y - 0.2, s.z), q, sc.set(s.k, s.k * (s.kind === 'cedar' ? 0.7 : 1.3), s.k));
    trunks.setMatrixAt(i, m);
  });
  for (const o of [cedar, crowns, trunks]) { o.castShadow = true; o.receiveShadow = true; g.add(o); }
  return g;
}

// The acacias rebuilt in place: the Standard crown parts are flat ellipsoids; each becomes a flat topped spread of small leaf
// clusters on a few branches, so the umbrella has gaps and a ragged edge. stdCrown is the Standard InstancedMesh of crown parts.
export function buildHighAcaciaCrowns(stdCrown) {
  const clusters = 26, rnd = mulberry32(141);
  const leafGeo = lumpy(2, 0.35, 5);
  const mesh = new THREE.InstancedMesh(leafGeo, new THREE.MeshStandardMaterial({ roughness: 0.95 }), stdCrown.count * clusters);
  const m = new THREE.Matrix4(), part = new THREE.Matrix4(), q = new THREE.Quaternion(), c = new THREE.Color();
  const pos = new THREE.Vector3(), scl = new THREE.Vector3(), v = new THREE.Vector3(), s = new THREE.Vector3();
  let n = 0;
  for (let i = 0; i < stdCrown.count; i++) {
    stdCrown.getMatrixAt(i, part);
    part.decompose(pos, q, scl);
    stdCrown.getColorAt(i, c);
    for (let k = 0; k < clusters; k++) {
      // a point on the upper half of the flat ellipsoid, more of them towards the rim
      const a = rnd() * Math.PI * 2, rr = Math.pow(rnd(), 0.6) * 0.95;
      v.set(Math.cos(a) * rr * scl.x, (0.15 + 0.5 * (1 - rr * rr)) * scl.y * (0.6 + rnd() * 0.5), Math.sin(a) * rr * scl.z).applyQuaternion(q).add(pos);
      const size = (0.35 + rnd() * 0.35) * Math.min(scl.x, 4) * 0.32;
      m.compose(v, q, s.set(size * 1.25, size * 0.5, size * 1.25));
      mesh.setMatrixAt(n, m);
      mesh.setColorAt(n, c.clone().offsetHSL(0, 0, (rnd() - 0.5) * 0.03));
      n++;
    }
  }
  mesh.count = n;
  mesh.castShadow = mesh.receiveShadow = true;
  mesh.name = 'high:acacia';
  return mesh;
}

// The standalone cedars rebuilt in place: the same instance matrices and colours on the finer cedar.
export function buildHighCedars(stdCedar) {
  const mesh = new THREE.InstancedMesh(highCedarGeometry(7), foliageMaterial(), stdCedar.count);
  const m = new THREE.Matrix4(), c = new THREE.Color();
  for (let i = 0; i < stdCedar.count; i++) {
    stdCedar.getMatrixAt(i, m);
    mesh.setMatrixAt(i, m);
    stdCedar.getColorAt(i, c);
    mesh.setColorAt(i, c);
  }
  mesh.castShadow = mesh.receiveShadow = true;
  mesh.name = 'high:cedars';
  return mesh;
}
