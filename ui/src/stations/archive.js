import * as THREE from 'three';
// Archive: text sits on a tablet at a slab; it is moved out, a sealed stone joins the cairn and a flag stays behind.
import { TOKENS } from '../world/palette.js';
import { lerp, smoothstep } from '../engine/ease.js';

export const poses = [
  { tab: 0, stone: 0, flag: 0 },
  { tab: 0.6, stone: 0, flag: 0 },
  { tab: 1, stone: 1, flag: 1 },
];

export function build(kit) {
  const { M } = kit;
  const g = new THREE.Group();
  const slab = kit.box(0.4, 1.45, 0.95, M.stone, -1.45, 0.72, -0.05);
  slab.rotation.y = 0.2;
  g.add(slab);
  g.add(kit.box(0.5, 0.12, 1.05, M.stoneDark, -1.45, 0.06, -0.05));
  // the cairn
  const cairn = new THREE.Group();
  cairn.position.set(1.2, 0, -0.1);
  g.add(cairn);
  [[-0.32, 0.12, 0.05, 0.3], [0.3, 0.12, -0.08, 0.28], [0, 0.12, 0.28, 0.26], [-0.1, 0.34, 0, 0.26], [0.14, 0.52, 0.02, 0.2]].forEach(([x, y, z, r], i) => {
    cairn.add(kit.rock(r, i % 2 ? M.stone : M.stoneDark, x, y, z, i + 4));
  });
  const sealMat = kit.glow(TOKENS.amber, 2, 0);
  const newStone = new THREE.Group();
  newStone.position.set(0, 0.74, 0);
  newStone.add(kit.rock(0.19, M.stone, 0, 0, 0, 9));
  const seal = new THREE.Mesh(new THREE.TorusGeometry(0.17, 0.014, 6, 36), sealMat);
  seal.rotation.x = Math.PI / 2;
  seal.position.y = 0.06;
  newStone.add(seal);
  cairn.add(newStone);
  // the tablet
  const tablet = new THREE.Group();
  tablet.add(kit.box(0.6, 0.4, 0.06, M.parchment, 0, 0, 0));
  tablet.add(kit.mesh(new THREE.BoxGeometry(0.42, 0.02, 0.07), kit.glow(TOKENS.amber, 0.9), 0, 0.07, 0));
  tablet.add(kit.mesh(new THREE.BoxGeometry(0.34, 0.02, 0.07), kit.glow(TOKENS.amber, 0.9), 0, -0.03, 0));
  g.add(tablet);
  // the flag left at the slab
  const flag = new THREE.Group();
  flag.position.set(-1.05, 0, 0.55);
  flag.add(kit.post(0.9, 0.025, M.woodDark));
  const cloth = kit.box(0.34, 0.2, 0.015, kit.std(0x8a6a44), 0.17, 0, 0);
  flag.add(cloth);
  g.add(flag);
  const from = new THREE.Vector3(-0.95, 0.55, 0.45);
  const to = new THREE.Vector3(1.2, 1.5, 0.15);
  return {
    group: g,
    apply(p) {
      tablet.position.lerpVectors(from, to, p.tab);
      tablet.position.y += Math.sin(Math.PI * p.tab) * 0.55;
      tablet.rotation.y = lerp(0.35, 0, p.tab);
      tablet.scale.setScalar(Math.max(0.0001, 1 - smoothstep(0.82, 1, p.tab)));
      newStone.scale.setScalar(Math.max(0.0001, p.stone));
      kit.level(sealMat, p.stone);
      cloth.position.y = lerp(0.2, 0.78, p.flag);
      cloth.visible = p.flag > 0.02;
    },
    setCounts() {},
  };
}
