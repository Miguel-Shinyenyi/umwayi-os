// Budget: a corrugated iron rain water tank on a timber stand. A sight tube on its front shows the level: today's use against
// the day's limit. Seven notches on the stand are the last seven days. A run that would pass the limit does not start.
import * as THREE from 'three';
import { TOKENS } from '../world/palette.js';
import { lerp } from '../engine/ease.js';
import { sceneNumbers } from '../data/snapshot.js';

export const poses = [{ level: 0.22 }, { level: 0.62 }, { level: 1 }];

const LIMIT = 0.86;

export function build(kit) {
  const { M } = kit;
  const g = new THREE.Group();
  const standH = 0.75, tankH = 1.7, R = 0.88;
  for (const x of [-0.7, 0.7]) for (const z of [-0.7, 0.7]) g.add(kit.post(standH, 0.07, M.woodDark, x, z));
  g.add(kit.box(1.8, 0.1, 1.8, M.woodDark, 0, standH, 0));
  const tank = new THREE.Group();
  tank.position.y = standH + 0.05;
  tank.add(kit.cyl(R, R, tankH, M.rust, 0, tankH / 2, 0, 28));
  for (let i = 0; i <= 8; i++) {
    const rib = new THREE.Mesh(new THREE.TorusGeometry(R + 0.012, 0.025, 6, 32), M.rust);
    rib.rotation.x = Math.PI / 2; rib.position.y = 0.05 + i * (tankH - 0.1) / 8; rib.castShadow = true;
    tank.add(rib);
  }
  const lid = new THREE.Mesh(new THREE.SphereGeometry(R, 24, 8, 0, Math.PI * 2, 0, Math.PI * 0.22).scale(1, 0.55, 1), M.rust);
  lid.position.y = tankH; lid.castShadow = true;
  tank.add(lid);
  g.add(tank);
  // the sight tube on the front (+z)
  const tubeH = 1.45, tubeY = standH + 0.2;
  const glass = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, tubeH, 10), new THREE.MeshStandardMaterial({ color: 0x9fb4ba, roughness: 0.1, transparent: true, opacity: 0.35 }));
  glass.position.set(0.0, tubeY + tubeH / 2, R + 0.12);
  g.add(glass);
  const waterMat = kit.glow(0x6aa8b8, 0.7, 1);
  const column = new THREE.Mesh(new THREE.CylinderGeometry(0.036, 0.036, 1, 10).translate(0, 0.5, 0), waterMat);
  column.position.set(0, tubeY, R + 0.12);
  g.add(column);
  g.add(kit.box(0.2, 0.012, 0.06, kit.glow(TOKENS.amber, 1.8), 0, tubeY + tubeH * LIMIT, R + 0.16)); // the limit line
  for (const y of [tubeY, tubeY + tubeH]) g.add(kit.box(0.14, 0.06, 0.1, M.iron, 0, y, R + 0.12));
  // the roof sheet that feeds it, and a pipe
  const sheet = kit.box(1.9, 0.04, 1.2, M.rust, -1.6, 2.35, -0.2);
  sheet.rotation.z = -0.35;
  g.add(sheet);
  for (const x of [-2.3, -0.9]) g.add(kit.post(2.2, 0.05, M.woodDark, x, -0.6));
  g.add(kit.beam(new THREE.Vector3(-0.85, 2.15, -0.1), new THREE.Vector3(-0.4, tankH + standH + 0.1, 0.2), 0.05, M.iron));
  // seven notches on a board: the last seven days
  g.add(kit.box(1.5, 0.9, 0.05, M.wood, 0, 0.5, 1.65));
  g.add(kit.post(0.5, 0.05, M.woodDark, -0.7, 1.6));
  g.add(kit.post(0.5, 0.05, M.woodDark, 0.7, 1.6));
  const notches = [];
  for (let i = 0; i < 7; i++) {
    const m = kit.glow(TOKENS.amber, 1.1, i === 6 ? 1 : 0.55);
    const n = kit.mesh(new THREE.BoxGeometry(0.1, 1, 0.04).translate(0, 0.5, 0), m, -0.57 + i * 0.19, 0.12, 1.69);
    n.userData.part = 'mark';
    g.add(n);
    notches.push(n);
  }
  const unknownMark = kit.unknownMark(1.9, 1.1);
  g.add(unknownMark);
  let restLevel = 0.22;
  return {
    group: g,
    apply(p) {
      column.scale.y = Math.max(0.001, p.level * tubeH * LIMIT * 1.12);
    },
    // the mapping table (data/snapshot.js): seven marks, each day against the busiest, and the water level at today against the
    // busiest day; a budget that cannot be read is the mark, flat marks and the lowest level
    setCounts(c) {
      const n = sceneNumbers(c).budget;
      notches.forEach((m, i) => { m.scale.y = Math.max(0.03, n.marks[i] * 0.6); });
      restLevel = lerp(0.12, LIMIT * 0.8, n.level);
      unknownMark.visible = n.unknown;
    },
    rest: () => ({ level: restLevel }),
  };
}
