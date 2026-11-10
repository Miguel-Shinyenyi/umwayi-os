import * as THREE from 'three';
// Logbook: a stump with growth rings and a helix of linked beads. Each bead is one entry, linked to the one before.
// Mint is an intact chain. If one entry is altered, that bead turns red and every bead after it goes dark.
import { TOKENS } from '../world/palette.js';
import { lerp } from '../engine/ease.js';

export const poses = [
  { add: 0, alter: 0, seal: 0 },
  { add: 1, alter: 0, seal: 0 },
  { add: 1, alter: 1, seal: 1 },
];

const MAX = 22;

export function build(kit) {
  const { M } = kit;
  const g = new THREE.Group();
  g.add(kit.cyl(0.6, 0.68, 0.5, M.woodDark, 0, 0.25, 0, 32));
  for (const r of [0.14, 0.28, 0.42, 0.55]) {
    const ring = new THREE.Mesh(new THREE.TorusGeometry(r, 0.01, 5, 40), M.wood);
    ring.rotation.x = Math.PI / 2;
    ring.position.y = 0.505;
    g.add(ring);
  }
  const helix = (i, n) => {
    const t = i / Math.max(1, n);
    const a = t * Math.PI * 2 * 2.4;
    return new THREE.Vector3(Math.cos(a) * 0.98, 0.3 + t * 1.85, Math.sin(a) * 0.98);
  };
  const beads = new THREE.InstancedMesh(new THREE.SphereGeometry(0.08, 14, 10), new THREE.MeshBasicMaterial({ color: 0xffffff }), MAX + 1);
  beads.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  g.add(beads);
  const link = new THREE.Mesh(new THREE.BufferGeometry(), M.stone);
  g.add(link);
  const sealMat = new THREE.MeshBasicMaterial({ color: TOKENS.mint });
  const seal = new THREE.Mesh(new THREE.TorusGeometry(1.04, 0.018, 6, 64), sealMat);
  seal.rotation.x = Math.PI / 2;
  g.add(seal);

  const mint = new THREE.Color(TOKENS.mint), red = new THREE.Color(TOKENS.red), dark = new THREE.Color(0x1b221e);
  const c = new THREE.Color(), m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), one = new THREE.Vector3();
  let n = 12; // beads in the chain
  let params = { add: 0, alter: 0, seal: 0 };

  const rebuild = () => {
    const pts = [];
    for (let i = 0; i <= n; i++) pts.push(helix(i, n + 1));
    link.geometry.dispose();
    link.geometry = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 120, 0.012, 5, false);
    for (let i = 0; i <= MAX; i++) {
      const pos = helix(i, n + 1);
      const s = i < n ? 1 : i === n ? Math.max(0.0001, params.add) : 0.0001;
      m4.compose(pos, q, one.set(s, s, s));
      beads.setMatrixAt(i, m4);
    }
    beads.instanceMatrix.needsUpdate = true;
    recolor();
  };
  const recolor = () => {
    const k = Math.floor(n * 0.45);
    const glow = 1.0 * kit.getGlowScale();
    for (let i = 0; i <= n && i <= MAX; i++) {
      c.copy(mint);
      if (params.alter > 0) {
        if (i === k) c.lerp(red, params.alter);
        else if (i > k) c.lerp(dark, params.alter);
      }
      if (c !== dark) c.multiplyScalar(i > k && params.alter > 0.99 ? 1 : glow);
      beads.setColorAt(i, c);
    }
    if (beads.instanceColor) beads.instanceColor.needsUpdate = true;
    sealMat.color.copy(mint).lerp(red, params.alter).multiplyScalar(glow * 0.8);
  };
  kit.glowListeners.push(recolor);
  rebuild();
  return {
    group: g,
    apply(p) {
      params = p;
      const added = Math.max(0.0001, p.add);
      beads.getMatrixAt(n, m4);
      const pos = helix(n, n + 1);
      m4.compose(pos, q, one.set(added, added, added));
      beads.setMatrixAt(n, m4);
      beads.instanceMatrix.needsUpdate = true;
      seal.position.y = lerp(0.14, 2.25, p.seal);
      seal.visible = p.seal > 0.02;
      recolor();
    },
    // counts: { logbook: { entries, chain_length } }
    setCounts(counts) {
      const len = counts && counts.logbook && Number.isFinite(counts.logbook.chain_length) ? counts.logbook.chain_length : 12;
      n = Math.max(4, Math.min(MAX - 1, len));
      rebuild();
    },
  };
}
