// Logbook: a tall standing stone with rings cut round it, and a helix of linked beads. Each bead is one entry, linked to
// the one before. Mint is an intact chain; if one entry is altered that bead turns red and every bead after it goes dark.
import * as THREE from 'three';
import { TOKENS } from '../world/palette.js';
import { lerp } from '../engine/ease.js';
import { sceneNumbers } from '../data/snapshot.js';

export const poses = [
  { add: 0, alter: 0, seal: 0 },
  { add: 1, alter: 0, seal: 0 },
  { add: 1, alter: 1, seal: 1 },
];

const MAX = 22;

export function build(kit) {
  const { M } = kit;
  const g = new THREE.Group();
  g.add(kit.rock(1, M.stone, 0, 1.55, 0, 6, 0.5, 1.6, 0.4));
  for (const [y, r] of [[0.7, 0.56], [1.1, 0.5], [1.5, 0.46], [1.9, 0.42], [2.3, 0.36]]) {
    const ring = new THREE.Mesh(new THREE.TorusGeometry(r, 0.018, 6, 28), M.stoneDark);
    ring.rotation.x = Math.PI / 2;
    ring.position.y = y;
    ring.scale.z = 0.8;
    g.add(ring);
  }
  for (let i = 0; i < 9; i++) {
    const a = (i / 9) * Math.PI * 2;
    g.add(kit.rock(0.3, i % 2 ? M.stone : M.stoneDark, Math.cos(a) * 0.95, 0.12, Math.sin(a) * 0.95, i + 2, 1.2, 0.6, 1));
  }
  const helix = (i, n) => {
    const t = i / Math.max(1, n), a = t * Math.PI * 2 * 2.4;
    return new THREE.Vector3(Math.cos(a) * 1.25, 0.35 + t * 2.1, Math.sin(a) * 1.25);
  };
  const beads = new THREE.InstancedMesh(new THREE.SphereGeometry(0.075, 14, 10), new THREE.MeshBasicMaterial({ color: 0xffffff }), MAX + 1);
  beads.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  beads.userData.part = 'bead';
  g.add(beads);
  const unknownMark = kit.unknownMark(2.2, 1.4);
  g.add(unknownMark);
  const link = new THREE.Mesh(new THREE.BufferGeometry(), M.iron);
  g.add(link);
  const sealMat = new THREE.MeshBasicMaterial({ color: TOKENS.mint });
  const seal = new THREE.Mesh(new THREE.TorusGeometry(1.32, 0.018, 6, 64), sealMat);
  seal.rotation.x = Math.PI / 2;
  g.add(seal);
  const mint = new THREE.Color(TOKENS.mint), red = new THREE.Color(TOKENS.red), dark = new THREE.Color(0x15191a);
  const c = new THREE.Color(), m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), one = new THREE.Vector3();
  let n = 0, params = { add: 0, alter: 0, seal: 0 };
  const recolor = () => {
    const k = Math.floor(n * 0.45), glow = 1.0 * kit.getGlowScale();
    for (let i = 0; i <= n && i <= MAX; i++) {
      c.copy(mint);
      if (params.alter > 0) { if (i === k) c.lerp(red, params.alter); else if (i > k) c.lerp(dark, params.alter); }
      if (!(i > k && params.alter > 0.99)) c.multiplyScalar(glow);
      beads.setColorAt(i, c);
    }
    if (beads.instanceColor) beads.instanceColor.needsUpdate = true;
    sealMat.color.copy(mint).lerp(red, params.alter).multiplyScalar(glow * 0.8);
  };
  const rebuild = () => {
    const pts = [];
    for (let i = 0; i <= n; i++) pts.push(helix(i, n + 1));
    link.geometry.dispose();
    link.visible = n >= 1; // a curve needs two points; with no linked entry there is no thread
    link.geometry = n >= 1 ? new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 120, 0.01, 5, false) : new THREE.BufferGeometry();
    for (let i = 0; i <= MAX; i++) {
      const s = i < n ? 1 : i === n ? Math.max(0.0001, params.add) : 0.0001;
      m4.compose(helix(i, n + 1), q, one.set(s, s, s));
      beads.setMatrixAt(i, m4);
    }
    beads.instanceMatrix.needsUpdate = true;
    recolor();
  };
  kit.glowListeners.push(recolor);
  rebuild();
  return {
    group: g,
    apply(p) {
      params = p;
      const added = Math.max(0.0001, p.add);
      m4.compose(helix(n, n + 1), q, one.set(added, added, added));
      beads.setMatrixAt(n, m4);
      beads.instanceMatrix.needsUpdate = true;
      seal.position.y = lerp(0.2, 2.6, p.seal);
      seal.visible = p.seal > 0.02;
      recolor();
    },
    // the mapping table (data/snapshot.js): one bead for each linked entry, 21 at most; none before the chain starts; a log that
    // cannot be read is the mark and no bead
    setCounts(counts) {
      const m = sceneNumbers(counts).logbook;
      n = m.beads;
      unknownMark.visible = m.unknown;
      rebuild();
    },
  };
}
