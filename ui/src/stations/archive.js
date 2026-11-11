// Archive: a cave in a rock face. Text on a tablet is carried from the slab into the cave; a stone with a seal joins the
// cairn and a flag stays at the slab.
import * as THREE from 'three';
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
  // the rock face: a mass of big stones with an opening in it
  [[-2.6, 1.2, -1.9, 1.7, 1], [-1.4, 1.9, -2.1, 1.9, 2], [1.5, 1.8, -2.2, 2.0, 3], [2.7, 1.1, -1.8, 1.6, 4], [0, 3.1, -2.3, 1.7, 5], [-1.6, 3.0, -2.2, 1.4, 6], [1.7, 3.2, -2.3, 1.5, 7], [-3.3, 0.7, -1.2, 1.1, 8], [3.5, 0.6, -1.2, 1.0, 9]]
    .forEach(([x, y, z, r, s]) => g.add(kit.rock(r, s % 2 ? M.stone : M.stoneDark, x, y, z, s, 1.1, 1.0, 0.9)));
  g.add(kit.rock(0.7, M.stone, -1.15, 1.05, -1.2, 11, 0.55, 1.5, 0.7));
  g.add(kit.rock(0.7, M.stone, 1.15, 1.05, -1.2, 12, 0.55, 1.5, 0.7));
  g.add(kit.rock(0.8, M.stoneDark, 0, 2.25, -1.25, 13, 1.7, 0.45, 0.8));
  const dark = new THREE.Mesh(new THREE.CircleGeometry(0.95, 24), new THREE.MeshBasicMaterial({ color: 0x020203 }));
  dark.scale.set(0.9, 1.25, 1);
  dark.position.set(0, 1.05, -1.0);
  dark.userData.noShadow = true;
  g.add(dark);
  const sealMat = kit.glow(TOKENS.amber, 2, 0);
  const seal = new THREE.Mesh(new THREE.CircleGeometry(0.28, 20), sealMat);
  seal.position.set(0, 0.7, -0.98);
  g.add(seal);
  g.add(kit.rock(0.7, M.stone, -1.8, 0.14, 1.3, 14, 1.4, 0.2, 1.05));
  const cairn = new THREE.Group();
  cairn.position.set(2.1, 0, 1.5);
  g.add(cairn);
  [[-0.32, 0.12, 0.05, 0.3], [0.3, 0.12, -0.08, 0.28], [0, 0.12, 0.28, 0.26], [-0.1, 0.34, 0, 0.26]].forEach(([x, y, z, r], i) => cairn.add(kit.rock(r, i % 2 ? M.stone : M.stoneDark, x, y, z, i + 4, 1.1, 0.8, 1)));
  const newStone = new THREE.Group();
  newStone.position.set(0, 0.6, 0);
  newStone.add(kit.rock(0.2, M.stone, 0, 0, 0, 9));
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.17, 0.014, 6, 36), sealMat);
  ring.rotation.x = Math.PI / 2;
  ring.position.y = 0.07;
  newStone.add(ring);
  cairn.add(newStone);
  const tablet = new THREE.Group();
  tablet.add(kit.box(0.5, 0.34, 0.06, M.parchment, 0, 0, 0));
  tablet.add(kit.mesh(new THREE.BoxGeometry(0.34, 0.02, 0.07), kit.glow(TOKENS.amber, 0.9), 0, 0.06, 0));
  tablet.add(kit.mesh(new THREE.BoxGeometry(0.28, 0.02, 0.07), kit.glow(TOKENS.amber, 0.9), 0, -0.04, 0));
  g.add(tablet);
  const flag = new THREE.Group();
  flag.position.set(-2.5, 0, 1.7);
  flag.add(kit.post(1.0, 0.025, M.woodDark));
  const cloth = kit.box(0.34, 0.2, 0.015, kit.std(0x8a5a38), 0.17, 0, 0);
  flag.add(cloth);
  g.add(flag);
  const from = new THREE.Vector3(-1.8, 0.45, 1.3), to = new THREE.Vector3(0, 0.95, -0.7);
  return {
    group: g,
    apply(p) {
      tablet.position.lerpVectors(from, to, p.tab);
      tablet.position.y += Math.sin(Math.PI * p.tab) * 0.45;
      tablet.rotation.y = lerp(0.4, 0, p.tab);
      tablet.scale.setScalar(Math.max(0.0001, 1 - smoothstep(0.82, 1, p.tab)));
      newStone.scale.setScalar(Math.max(0.0001, p.stone));
      kit.level(sealMat, p.stone);
      cloth.position.y = lerp(0.2, 0.8, p.flag);
    },
    setCounts() {},
  };
}
